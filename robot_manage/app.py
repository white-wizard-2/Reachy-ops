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
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Optional
from urllib.parse import urlparse

from fastapi import FastAPI, Query
from fastapi.responses import PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from reachy_mini import ReachyMini

from robot_manage.camera_feed import MiniCameraPublisher
from robot_manage.camera_layout import build_camera_layout
from robot_manage.mic_buffer import MicCollectorThread, RobotMicRingBuffer
from robot_manage.mlx_voice_pipeline import ensure_mlx_voice_pipeline, try_create_mlx_pipeline
from robot_manage.settings import ollama_base_url, ollama_model

_MJPEG_BOUNDARY = b"frame"
_STREAM_FRAME_INTERVAL_S = 1.0 / 25.0


def create_app(
    *,
    robot_host: str,
    robot_port: int,
    connection_mode: str,
    media_backend: str,
    static_dir: Optional[Path] = None,
) -> FastAPI:
    static_path = static_dir if static_dir is not None else Path(__file__).resolve().parent / "static"
    mini_ref: list[Optional[ReachyMini]] = [None]
    pub_ref: list[Optional[MiniCameraPublisher]] = [None]
    mic_state: dict[str, Any] = {"buffer": None, "collector": None, "mlx_pipeline": None}

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
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
        if mini.media.audio is not None:
            await asyncio.to_thread(mini.media.start_recording)
            mic_buf = RobotMicRingBuffer()
            mic_collector = MicCollectorThread(mini, mic_buf)
            mic_state["buffer"] = mic_buf
            mic_state["collector"] = mic_collector
            mic_collector.start()
            mlx_pipe = try_create_mlx_pipeline(mic_buf)
            if mlx_pipe is not None:
                mic_state["mlx_pipeline"] = mlx_pipe
                await mlx_pipe.start()
        try:
            yield
        finally:
            mlx_pipe = mic_state.get("mlx_pipeline")
            if mlx_pipe is not None:
                await mlx_pipe.aclose()
                mic_state["mlx_pipeline"] = None
            col = mic_state.get("collector")
            if col is not None:
                col.stop_join()
            mic_state["collector"] = None
            mic_state["buffer"] = None
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
