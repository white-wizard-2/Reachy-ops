"""FastAPI app: Reachy Mini camera MJPEG + built static UI.

All vision and microphone data go through the **Reachy Mini Python SDK** only
(``ReachyMini`` → ``media``): ``get_frame()`` for video and
``start_recording`` / ``get_audio_sample()`` for audio. Those APIs use the
daemon-side GStreamer pipelines (local IPC or WebRTC, depending on
``media_backend``); this service does not open ``/dev/video*`` or the host
mic directly.
"""

from __future__ import annotations

import asyncio
import json
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Optional
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from reachy_mini import ReachyMini

from robot_manage.app_ui_hub import AppUiHub
from robot_manage.camera_feed import MiniCameraPublisher
from robot_manage.camera_layout import build_camera_layout
from robot_manage.daemon_audio import apply_daemon_audio_levels, prime_daemon_audio_levels
from robot_manage.daemon_preflight import ensure_reachy_mini_daemon_backend_running
from robot_manage.jpeg_util import bgr_frame_to_jpeg_bytes
from robot_manage.mic_buffer import MicCollectorThread, RobotMicRingBuffer
from robot_manage.mlx_voice_pipeline import ensure_mlx_voice_pipeline, try_create_mlx_pipeline
from robot_manage.robot_state_hub import RobotStateHub, robot_state_poll_loop
from robot_manage.settings import ollama_base_url, ollama_model

_MJPEG_BOUNDARY = b"frame"
_STREAM_FRAME_INTERVAL_S = 1.0 / 25.0


def _ensure_black_jpeg(mic_state: dict[str, Any]) -> bytes:
    cached = mic_state.get("_black_jpeg")
    if isinstance(cached, (bytes, bytearray)):
        return bytes(cached)
    import numpy as np

    jpeg = bgr_frame_to_jpeg_bytes(np.zeros((64, 48, 3), dtype=np.uint8), quality=65)
    mic_state["_black_jpeg"] = jpeg
    return jpeg


class VoiceModesToolsBody(BaseModel):
    mode: Optional[str] = None
    tools: list[str] = Field(default_factory=list)


def create_app(
    *,
    robot_host: str,
    robot_port: int,
    connection_mode: str,
    media_backend: str,
    static_dir: Optional[Path] = None,
    skip_daemon_wake: bool = False,
) -> FastAPI:
    static_path = static_dir if static_dir is not None else Path(__file__).resolve().parent / "static"
    mini_ref: list[Optional[ReachyMini]] = [None]
    pub_ref: list[Optional[MiniCameraPublisher]] = [None]
    mic_state: dict[str, Any] = {
        "buffer": None,
        "collector": None,
        "mlx_pipeline": None,
        "mini": None,
        "mic_disabled": threading.Event(),
        "camera_enabled": True,
        "bot_awake": True,
        "audio_output_muted": False,
        "idle_look_sweep_enabled": False,
        "daemon_speaker_volume": 70,
        "daemon_mic_input_volume": 70,
        "_black_jpeg": None,
    }
    ui_hub = AppUiHub()
    mic_state["voice_ui_notify"] = ui_hub.voice_notify

    def _daemon_state_full_url() -> Optional[str]:
        m = mini_ref[0]
        if m is None:
            return None
        return f"http://{m.client.host}:{m.client.port}/api/state/full"

    state_hub = RobotStateHub(_daemon_state_full_url, ui_hub.broadcast_json)
    state_poll_task: list[Optional[asyncio.Task[None]]] = [None]
    ui_metrics_task: list[Optional[asyncio.Task[None]]] = [None]
    voice_live_forward_tasks: dict[int, asyncio.Task[None]] = {}

    async def broadcast_device_controls() -> None:
        md = mic_state["mic_disabled"]
        await ui_hub.broadcast_json(
            {
                "type": "device_controls",
                "mic_enabled": not md.is_set(),
                "camera_enabled": bool(mic_state.get("camera_enabled", True)),
                "bot_awake": bool(mic_state.get("bot_awake", True)),
                "audio_output_enabled": not bool(mic_state.get("audio_output_muted", False)),
                "idle_look_sweep_enabled": bool(mic_state.get("idle_look_sweep_enabled", False)),
                "daemon_speaker_volume": int(mic_state.get("daemon_speaker_volume", 70)),
                "daemon_mic_input_volume": int(mic_state.get("daemon_mic_input_volume", 70)),
            }
        )

    def _json_int_percent(v: object) -> int | None:
        if isinstance(v, bool):
            return None
        if isinstance(v, int):
            return v
        if isinstance(v, float):
            return int(round(v))
        return None

    async def apply_audio_levels_from_msg(msg: dict[str, Any]) -> None:
        mini = mini_ref[0]
        if mini is None:
            await broadcast_device_controls()
            return
        mic_v = _json_int_percent(msg.get("mic_input_volume"))
        sp_v = _json_int_percent(msg.get("speaker_volume"))
        if mic_v is None and sp_v is None:
            return
        async with httpx.AsyncClient() as c:
            await apply_daemon_audio_levels(
                c,
                mini,
                mic_state,
                mic_input_volume=mic_v,
                speaker_volume=sp_v,
            )
        await broadcast_device_controls()

    async def apply_device_toggle(dev: object) -> None:
        if not isinstance(dev, str) or dev not in (
            "mic",
            "camera",
            "bot",
            "audio_output",
            "idle_look_sweep",
        ):
            return
        mini = mini_ref[0]
        if dev == "mic":
            md = mic_state["mic_disabled"]
            if md.is_set():
                md.clear()
            else:
                md.set()
                buf = mic_state.get("buffer")
                if isinstance(buf, RobotMicRingBuffer):
                    buf.clear()
        elif dev == "camera":
            cur = bool(mic_state.get("camera_enabled", True))
            nxt = not cur
            mic_state["camera_enabled"] = nxt
            pub = pub_ref[0]
            if pub is not None:
                if nxt:
                    pub.start()
                else:
                    pub.stop()
        elif dev == "bot":
            if mini is None:
                await broadcast_device_controls()
                return
            if mic_state.get("bot_awake", True):
                await asyncio.to_thread(mini.goto_sleep)
                mic_state["bot_awake"] = False
            else:
                await asyncio.to_thread(mini.wake_up)
                mic_state["bot_awake"] = True
        elif dev == "audio_output":
            mic_state["audio_output_muted"] = not bool(mic_state.get("audio_output_muted", False))
        elif dev == "idle_look_sweep":
            was = bool(mic_state.get("idle_look_sweep_enabled", False))
            mic_state["idle_look_sweep_enabled"] = not was
            if was:
                m = mini_ref[0]
                if m is not None:
                    try:
                        m.cancel_move()
                    except Exception:
                        pass
            if not was:
                pipe = await ensure_mlx_voice_pipeline(mic_state)
                if pipe is not None:
                    pipe.trigger_idle_look_sweep()
        await broadcast_device_controls()

    async def build_ui_snapshot() -> dict[str, Any]:
        mini = mini_ref[0]
        if mini is None:
            layout: dict[str, Any] = {"feeds": [], "sdk_single_stream": True, "error": "robot_not_ready"}
        else:
            layout = build_camera_layout(mini)
        u = urlparse(ollama_base_url())
        ollama_host = u.netloc or u.path or u.geturl()
        llm_config = {"model": ollama_model(), "ollama_host": ollama_host}
        buf = mic_state.get("buffer")
        pipe = mic_state.get("mlx_pipeline")
        if buf is not None:
            pipe = await ensure_mlx_voice_pipeline(mic_state)
        if buf is None:
            voice_status = {"buffering": False, "buffered_seconds_estimate": 0.0}
            voice_meter: dict[str, Any] = {"levels": [0.0] * 40, "peak": 0.0}
        else:
            levels, peak = buf.meter_histogram(bars=40)
            voice_meter = {"levels": levels, "peak": round(float(peak), 4)}
            voice_status = {
                "buffering": True,
                "buffered_seconds_estimate": round(buf.approx_buffered_seconds(), 2),
            }
        try:
            import mlx_whisper  # noqa: F401

            mlx_ok = True
        except ImportError:
            mlx_ok = False
        voice_pipeline = {
            "mlx_whisper_import_ok": mlx_ok,
            "mlx_live_ready": pipe is not None,
        }
        if pipe is None:
            modes_tools = {"mode": None, "tools": []}
            conversation: list[Any] = []
        else:
            modes_tools = await pipe.modes_tools_snapshot()
            conversation = pipe.conversation_messages_for_client()
        robot_state = state_hub.public_message()
        md = mic_state["mic_disabled"]
        return {
            "layout": layout,
            "llm_config": llm_config,
            "voice_pipeline": voice_pipeline,
            "voice_status": voice_status,
            "voice_meter": voice_meter,
            "modes_tools": modes_tools,
            "conversation": conversation,
            "robot_state": robot_state,
            "device_controls": {
                "mic_enabled": not md.is_set(),
                "camera_enabled": bool(mic_state.get("camera_enabled", True)),
                "bot_awake": bool(mic_state.get("bot_awake", True)),
                "audio_output_enabled": not bool(mic_state.get("audio_output_muted", False)),
                "idle_look_sweep_enabled": bool(mic_state.get("idle_look_sweep_enabled", False)),
                "daemon_speaker_volume": int(mic_state.get("daemon_speaker_volume", 70)),
                "daemon_mic_input_volume": int(mic_state.get("daemon_mic_input_volume", 70)),
            },
        }

    async def ui_metrics_broadcast_loop() -> None:
        tick = 0
        while True:
            await asyncio.sleep(0.1)
            if ui_hub.n_connections() == 0:
                continue
            tick += 1
            buf = mic_state.get("buffer")
            if buf is None:
                await ui_hub.broadcast_json({"type": "voice_meter", "levels": [0.0] * 40, "peak": 0.0})
            else:
                levels, peak = buf.meter_histogram(bars=40)
                await ui_hub.broadcast_json(
                    {"type": "voice_meter", "levels": levels, "peak": round(float(peak), 4)}
                )
            if tick % 10 == 0:
                if buf is None:
                    st = {"buffering": False, "buffered_seconds_estimate": 0.0}
                else:
                    st = {
                        "buffering": True,
                        "buffered_seconds_estimate": round(buf.approx_buffered_seconds(), 2),
                    }
                await ui_hub.broadcast_json({"type": "voice_status", **st})
            if tick % 40 == 0:
                try:
                    import mlx_whisper  # noqa: F401

                    mlx_ok = True
                except ImportError:
                    mlx_ok = False
                await ui_hub.broadcast_json(
                    {
                        "type": "voice_pipeline",
                        "mlx_whisper_import_ok": mlx_ok,
                        "mlx_live_ready": mic_state.get("mlx_pipeline") is not None,
                    }
                )

    async def stop_voice_live_forward(ws_key: int) -> None:
        t = voice_live_forward_tasks.pop(ws_key, None)
        if t is None or t.done():
            return
        t.cancel()
        try:
            await t
        except asyncio.CancelledError:
            pass

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if not skip_daemon_wake:
            await ensure_reachy_mini_daemon_backend_running(robot_host, robot_port)
        mini = ReachyMini(
            host=robot_host,
            port=robot_port,
            connection_mode=connection_mode,  # type: ignore[arg-type]
            media_backend=media_backend,
        )
        pub = MiniCameraPublisher(mini)
        pub.start()
        mini_ref[0] = mini
        pub_ref[0] = pub
        mic_state["mini"] = mini
        if mini.media.audio is not None:
            await asyncio.to_thread(mini.media.start_recording)
            mic_buf = RobotMicRingBuffer()
            mic_collector = MicCollectorThread(mini, mic_buf, pause=mic_state["mic_disabled"])
            mic_state["buffer"] = mic_buf
            mic_state["collector"] = mic_collector
            mic_collector.start()

            async def _prime_daemon_audio() -> None:
                m = mini_ref[0]
                if m is None:
                    return
                try:
                    async with httpx.AsyncClient() as c:
                        await prime_daemon_audio_levels(c, m, mic_state)
                    await broadcast_device_controls()
                except Exception:
                    pass

            asyncio.create_task(_prime_daemon_audio())
            mlx_pipe = try_create_mlx_pipeline(mic_buf, mini, mic_state)
            if mlx_pipe is not None:
                mic_state["mlx_pipeline"] = mlx_pipe
                mlx_pipe.set_ws_voice_notify(ui_hub.voice_notify)
                await mlx_pipe.start()
        state_poll_task[0] = asyncio.create_task(robot_state_poll_loop(state_hub))
        ui_metrics_task[0] = asyncio.create_task(ui_metrics_broadcast_loop())
        try:
            yield
        finally:
            mt = ui_metrics_task[0]
            if mt is not None:
                mt.cancel()
                try:
                    await mt
                except asyncio.CancelledError:
                    pass
                ui_metrics_task[0] = None
            for _wid, vt in list(voice_live_forward_tasks.items()):
                if not vt.done():
                    vt.cancel()
                    try:
                        await vt
                    except asyncio.CancelledError:
                        pass
            voice_live_forward_tasks.clear()
            t = state_poll_task[0]
            if t is not None:
                t.cancel()
                try:
                    await t
                except asyncio.CancelledError:
                    pass
                state_poll_task[0] = None
            mlx_pipe = mic_state.get("mlx_pipeline")
            if mlx_pipe is not None:
                await mlx_pipe.aclose()
                mic_state["mlx_pipeline"] = None
            col = mic_state.get("collector")
            if col is not None:
                col.stop_join()
            mic_state["collector"] = None
            mic_state["buffer"] = None
            mic_state["mini"] = None
            pub.stop()
            m = mini_ref[0]
            if m is not None:
                m.__exit__(None, None, None)
                mini_ref[0] = None
            pub_ref[0] = None

    app = FastAPI(title="robot_manage", lifespan=lifespan)

    @app.get("/api/llm/config")
    def llm_config() -> dict[str, str]:
        u = urlparse(ollama_base_url())
        host = u.netloc or u.path or u.geturl()
        return {"model": ollama_model(), "ollama_host": host}

    @app.get("/api/voice/pipeline")
    def voice_pipeline_info() -> dict[str, Any]:
        mlx_ok = False
        try:
            import mlx_whisper  # noqa: F401

            mlx_ok = True
        except ImportError:
            mlx_ok = False
        return {
            "mlx_whisper_import_ok": mlx_ok,
            "mlx_live_ready": mic_state.get("mlx_pipeline") is not None,
        }

    @app.get("/api/voice/conversation")
    def voice_conversation() -> dict[str, Any]:
        """Current MLX voice → Ollama message list (for UI restore after refresh)."""

        pipe = mic_state.get("mlx_pipeline")
        if pipe is None:
            return {"messages": []}
        return {"messages": pipe.conversation_messages_for_client()}

    @app.get("/api/voice/modes-tools")
    async def voice_modes_tools_get() -> dict[str, Any]:
        pipe = mic_state.get("mlx_pipeline")
        if pipe is None:
            pipe = await ensure_mlx_voice_pipeline(mic_state)
        if pipe is None:
            return {"mode": None, "tools": []}
        return await pipe.modes_tools_snapshot()

    @app.put("/api/voice/modes-tools")
    async def voice_modes_tools_put(body: VoiceModesToolsBody) -> dict[str, Any]:
        pipe = await ensure_mlx_voice_pipeline(mic_state)
        if pipe is None:
            raise HTTPException(
                status_code=503,
                detail="MLX voice pipeline is not available.",
            )
        try:
            await pipe.replace_modes_tools(mode=body.mode, tools=body.tools)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e)) from e
        return await pipe.modes_tools_snapshot()

    @app.get("/api/voice/live")
    async def voice_live() -> StreamingResponse:
        pipe = await ensure_mlx_voice_pipeline(mic_state)
        if pipe is None:
            buf = mic_state.get("buffer")
            if buf is None:
                return PlainTextResponse(
                    "No robot microphone ring (Reachy media has no audio for this session).",
                    status_code=503,
                )
            return PlainTextResponse(
                "MLX Whisper is not available (install mlx-whisper on Apple Silicon: "
                "pip install -r requirements-robot-manage-mlx.txt).",
                status_code=503,
            )

        q = await pipe.subscribe()

        async def sse() -> AsyncIterator[str]:
            try:
                await q.put({"event": "meta", "voice": "mlx_live"})
                while True:
                    item = await q.get()
                    yield f"data: {json.dumps(item)}\n\n"
            finally:
                await pipe.unsubscribe(q)

        return StreamingResponse(sse(), media_type="text/event-stream")

    @app.get("/api/voice/status")
    def voice_status() -> dict[str, Any]:
        buf = mic_state.get("buffer")
        if buf is None:
            return {"buffering": False, "buffered_seconds_estimate": 0.0}
        return {
            "buffering": True,
            "buffered_seconds_estimate": round(buf.approx_buffered_seconds(), 2),
        }

    @app.get("/api/voice/meter")
    def voice_meter(bars: int = Query(40, ge=12, le=64)) -> dict[str, Any]:
        buf = mic_state.get("buffer")
        if buf is None:
            return {"levels": [0.0] * bars, "peak": 0.0}
        levels, peak = buf.meter_histogram(bars=bars)
        return {"levels": levels, "peak": round(float(peak), 4)}

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/camera/layout")
    def camera_layout() -> dict:
        m = mini_ref[0]
        if m is None:
            return {"feeds": [], "sdk_single_stream": True, "error": "robot_not_ready"}
        return build_camera_layout(m)

    @app.get("/api/camera/mjpeg")
    async def camera_mjpeg() -> StreamingResponse:
        async def stream() -> AsyncIterator[bytes]:
            while True:
                if not mic_state.get("camera_enabled", True):
                    chunk = _ensure_black_jpeg(mic_state)
                else:
                    pub = pub_ref[0]
                    if pub is None:
                        await asyncio.sleep(0.05)
                        continue
                    chunk = pub.get_latest_jpeg()
                if chunk is None:
                    await asyncio.sleep(0.02)
                    continue
                yield (
                    b"--"
                    + _MJPEG_BOUNDARY
                    + b"\r\nContent-Type: image/jpeg\r\n\r\n"
                    + chunk
                    + b"\r\n"
                )
                await asyncio.sleep(_STREAM_FRAME_INTERVAL_S)

        return StreamingResponse(
            stream(),
            media_type=f"multipart/x-mixed-replace; boundary={_MJPEG_BOUNDARY.decode()}",
        )

    @app.websocket("/ws/app")
    async def ws_app(websocket: WebSocket) -> None:
        """Single UI channel: snapshot, telemetry ticks, voice live stream, layout/modes commands."""
        await websocket.accept()
        await ui_hub.register(websocket)
        snap = await build_ui_snapshot()
        await websocket.send_json({"type": "snapshot", **snap})
        ws_key = id(websocket)
        try:
            while True:
                try:
                    raw = await websocket.receive_text()
                except WebSocketDisconnect:
                    break
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if not isinstance(msg, dict):
                    continue
                mtype = msg.get("type")
                if mtype == "refresh_layout":
                    mini = mini_ref[0]
                    if mini is None:
                        lay: dict[str, Any] = {
                            "feeds": [],
                            "sdk_single_stream": True,
                            "error": "robot_not_ready",
                        }
                    else:
                        lay = build_camera_layout(mini)
                    await ui_hub.broadcast_json({"type": "layout", "payload": lay})
                elif mtype == "device_toggle":
                    await apply_device_toggle(msg.get("device"))
                elif mtype == "audio_levels_set":
                    try:
                        await apply_audio_levels_from_msg(msg)
                    except Exception as e:
                        await websocket.send_json({"type": "error", "message": f"audio_levels:{e!s}"})
                elif mtype == "modes_tools_set":
                    pipe = await ensure_mlx_voice_pipeline(mic_state)
                    if pipe is None:
                        await websocket.send_json(
                            {
                                "type": "voice_live",
                                "event": "error",
                                "message": "MLX voice pipeline is not available.",
                            }
                        )
                        continue
                    tools_raw = msg.get("tools")
                    tools_list = tools_raw if isinstance(tools_raw, list) else []
                    tools_str = [str(x) for x in tools_list]
                    rm = msg.get("mode")
                    mode_val: Optional[str] = None if rm is None else str(rm)
                    try:
                        await pipe.replace_modes_tools(mode=mode_val, tools=tools_str)
                    except ValueError as e:
                        await websocket.send_json(
                            {"type": "modes_tools_error", "detail": str(e)}
                        )
                elif mtype == "voice_live_start":
                    await stop_voice_live_forward(ws_key)
                    pipe = await ensure_mlx_voice_pipeline(mic_state)
                    if pipe is None:
                        buf = mic_state.get("buffer")
                        if buf is None:
                            detail = "No robot microphone ring (Reachy media has no audio for this session)."
                        else:
                            detail = (
                                "MLX Whisper is not available (install mlx-whisper on Apple Silicon: "
                                "pip install -r requirements-robot-manage-mlx.txt)."
                            )
                        await websocket.send_json(
                            {"type": "voice_live", "event": "error", "message": detail}
                        )
                        continue

                    q = await pipe.subscribe()
                    pipe_ref = pipe

                    async def _forward() -> None:
                        try:
                            await websocket.send_json(
                                {"type": "voice_live", "event": "meta", "voice": "mlx_live"}
                            )
                            while True:
                                item = await q.get()
                                await websocket.send_json({"type": "voice_live", **item})
                        except asyncio.CancelledError:
                            raise
                        finally:
                            await pipe_ref.unsubscribe(q)

                    voice_live_forward_tasks[ws_key] = asyncio.create_task(_forward())
                elif mtype == "voice_live_stop":
                    await stop_voice_live_forward(ws_key)
        finally:
            await stop_voice_live_forward(ws_key)
            await ui_hub.unregister(websocket)

    if (static_path / "index.html").is_file():
        app.mount("/", StaticFiles(directory=str(static_path), html=True), name="static")
    else:

        @app.get("/")
        def root_no_build() -> PlainTextResponse:
            return PlainTextResponse(
                "robot_manage UI is not built. Run: cd robot_manage/web && npm install && npm run build",
                status_code=503,
            )

    return app
