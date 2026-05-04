"""MLX Whisper on silence-segmented utterances + multi-turn Ollama ``/api/chat``."""

from __future__ import annotations

import asyncio
import re
from typing import Any, Awaitable, Callable, Optional

import httpx
import numpy as np

from robot_manage.idle_look_sweep import run_idle_look_sweep_pass
from robot_manage.llm_say import LlmSayRunner, pull_complete_sentences
from robot_manage.mic_buffer import RobotMicRingBuffer
from robot_manage.motion_reactions import select_reaction_move_for_speech
from robot_manage.move_catalog import VoiceAssistantJsonError, parse_voice_assistant_output
from robot_manage.ollama_voice import (
    complete_chat_with_robot_tools,
    stream_text_chat_messages,
    yield_text_as_token_chunks,
)
from robot_manage.settings import (
    mlx_voice_min_utterance_ms,
    mlx_voice_silence_end_ms,
    mlx_voice_speech_rms,
    mlx_voice_tick_sec,
    mlx_whisper_condition_on_previous_text,
    mlx_whisper_language,
    mlx_whisper_max_chunk_sec,
    mlx_whisper_min_rms,
    mlx_whisper_no_speech_threshold,
    mlx_whisper_repo,
    ollama_base_url,
    ollama_model,
    ollama_voice_max_history_messages,
    ollama_voice_robot_tools_enabled,
    ollama_voice_say_post_ms,
    ollama_voice_text_system_prompt,
    robot_manage_reaction_moves_enabled,
)
from robot_manage.voice_command_parser import format_command_speech, try_parse_voice_command
from robot_manage.wav_utils import stereo_float32_to_mono_float32

_mlx_ensure_lock = asyncio.Lock()

_JUNK_SHORT: frozenset[str] = frozenset(
    {
        "thank you",
        "thank you.",
        "thanks",
        "thanks.",
        "thank you!",
        "thanks!",
        "ty",
        "bye",
        "bye.",
        "mm-hmm",
        "uh",
        "um",
    }
)


def _whisper_decode_kw(language: str | None) -> dict[str, Any]:
    kw: dict[str, Any] = {
        "verbose": False,
        "no_speech_threshold": mlx_whisper_no_speech_threshold(),
        "condition_on_previous_text": mlx_whisper_condition_on_previous_text(),
    }
    if language:
        kw["language"] = language
    return kw


def _mono_rms(mono: np.ndarray) -> float:
    if mono.size == 0:
        return 0.0
    x = mono.astype(np.float64, copy=False)
    return float(np.sqrt(np.mean(np.square(x))))


def _scrub_short_hallucination(text: str) -> str:
    """Drop very short single-phrase hallucinations common on silence (e.g. ``Thank you.``)."""

    t = (text or "").strip()
    if not t:
        return ""
    norm = re.sub(r"\s+", " ", t.lower()).strip(".,!?…\"' ").strip()
    if norm in _JUNK_SHORT:
        return ""
    parts = norm.split()
    if len(parts) == 2 and parts[0] == "thank" and parts[1] == "you":
        return ""
    return t


def _conversation_for_sse(messages: list[dict[str, Any]]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for i, m in enumerate(messages):
        role = str(m.get("role", ""))
        if role == "tool":
            continue
        if role == "user" and m.get("images"):
            continue
        if role == "assistant" and not str(m.get("content", "")).strip() and m.get("tool_calls"):
            continue
        content = str(m.get("content", ""))
        if role == "system" and i == 0 and len(content) > 480:
            content = content[:480] + "…"
        out.append({"role": role, "content": content})
    return out


def _sanitize_tts_chunk(text: str) -> str:
    t = text.strip()
    for sub in ("(calling tools)", "(Calling tools)", "calling tools"):
        t = t.replace(sub, "")
    return " ".join(t.split())


async def _enqueue_speech_sentences(say: LlmSayRunner, speech: str) -> None:
    """Queue TTS one sentence at a time; strip UI/tool placeholder phrases."""

    if not say.running:
        return
    raw = _sanitize_tts_chunk(speech)
    if not raw:
        return
    buf = raw if raw[-1] in " \t\n\r" else raw + " "
    sents, rem = pull_complete_sentences(buf)
    chunks = [_sanitize_tts_chunk(c) for c in sents if _sanitize_tts_chunk(c)]
    tail = _sanitize_tts_chunk(rem)
    if tail:
        chunks.append(tail)
    for c in chunks:
        if c:
            await say.enqueue_sentence(c)


def _preload_mlx_whisper_model(path_or_hf_repo: str, language: str | None) -> None:
    import mlx_whisper

    silence = np.zeros(16_000, dtype=np.float32)
    kw = _whisper_decode_kw(language)
    mlx_whisper.transcribe(silence, path_or_hf_repo=path_or_hf_repo, **kw)


def _mlx_transcribe_fn(
    mono: Any, path_or_hf_repo: str, language: str | None
) -> dict[str, Any]:
    import mlx_whisper

    kw = _whisper_decode_kw(language)
    return mlx_whisper.transcribe(mono, path_or_hf_repo=path_or_hf_repo, **kw)


def try_create_mlx_pipeline(
    buf: RobotMicRingBuffer,
    mini: Any | None = None,
    controls: dict[str, Any] | None = None,
) -> MlxLiveVoicePipeline | None:
    try:
        import mlx_whisper  # noqa: F401
    except ImportError:
        return None
    return MlxLiveVoicePipeline(buf, mini=mini, controls=controls)


async def ensure_mlx_voice_pipeline(mic_state: dict[str, Any]) -> MlxLiveVoicePipeline | None:
    """Create and start the MLX pipeline on first ``/api/voice/live`` if the mic ring exists."""

    async with _mlx_ensure_lock:
        existing = mic_state.get("mlx_pipeline")
        if existing is not None:
            return existing  # type: ignore[no-any-return]
        buf = mic_state.get("buffer")
        if buf is None:
            return None
        created = try_create_mlx_pipeline(buf, mic_state.get("mini"), mic_state)
        if created is None:
            return None
        await created.start()
        mic_state["mlx_pipeline"] = created
        sink = mic_state.get("voice_ui_notify")
        if sink is not None:
            created.set_ws_voice_notify(sink)
        return created


class MlxLiveVoicePipeline:
    def __init__(
        self,
        buf: RobotMicRingBuffer,
        *,
        mini: Any | None = None,
        controls: dict[str, Any] | None = None,
    ) -> None:
        self._buf = buf
        self._mini = mini
        self._controls: dict[str, Any] = controls if controls is not None else {}
        self._qs: set[asyncio.Queue[dict[str, Any]]] = set()
        self._q_lock = asyncio.Lock()
        self._llm_lock = asyncio.Lock()
        self._utt_sync = asyncio.Lock()
        self._mic_accept_event = asyncio.Event()
        self._mic_accept_event.set()
        self._stop = asyncio.Event()
        self._tasks: list[asyncio.Task[None]] = []
        self._asr_cursor = 0
        self._client: httpx.AsyncClient | None = None
        self._llm_queue: asyncio.Queue[str] = asyncio.Queue()
        self._llm_messages: list[dict[str, Any]] = []
        self._utt_chunks: list[np.ndarray] = []
        self._in_utt = False
        self._silence_ms = 0.0
        if mini is not None:
            self._say = LlmSayRunner(
                mic_hooks=self,
                reachy_host=getattr(getattr(mini, "client", None), "host", None),
                reachy_port=int(getattr(getattr(mini, "client", None), "port", 8000) or 8000),
                is_output_muted=lambda: bool(self._controls.get("audio_output_muted")),
            )
        else:
            self._say = LlmSayRunner(mic_hooks=self)
        self._move_spec_this_turn: tuple[str, str] | None = None
        self._move_play_task: asyncio.Task[None] | None = None
        self._modes_tools_lock = asyncio.Lock()
        self._active_mode: str | None = None
        self._tools_on: set[str] = set()
        self._ws_voice_notify: Optional[Callable[[dict[str, Any]], Awaitable[None]]] = None
        self._idle_look_sweep_task: asyncio.Task[None] | None = None

    def set_ws_voice_notify(self, fn: Optional[Callable[[dict[str, Any]], Awaitable[None]]]) -> None:
        """Optional fan-out for UI (modes/conversation/errors); not used for per-token streaming."""

        self._ws_voice_notify = fn

    async def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=512)
        async with self._q_lock:
            self._qs.add(q)
        snap = [dict(m) for m in self._llm_messages]
        try:
            q.put_nowait(
                {"event": "conversation", "messages": _conversation_for_sse(snap)}
            )
        except asyncio.QueueFull:
            pass
        async with self._modes_tools_lock:
            mt = {
                "event": "modes_tools",
                "mode": self._active_mode,
                "tools": sorted(self._tools_on),
            }
        try:
            q.put_nowait(mt)
        except asyncio.QueueFull:
            pass
        return q

    def conversation_messages_for_client(self) -> list[dict[str, str]]:
        """Snapshot of Ollama messages for HTTP restore (same truncation as SSE)."""

        return _conversation_for_sse([dict(m) for m in self._llm_messages])

    async def modes_tools_snapshot(self) -> dict[str, Any]:
        async with self._modes_tools_lock:
            return {"mode": self._active_mode, "tools": sorted(self._tools_on)}

    async def replace_modes_tools(self, *, mode: str | None, tools: list[str]) -> None:
        from robot_manage.voice_command_parser import MODE_LABELS, TOOL_LABELS

        async with self._modes_tools_lock:
            if mode is not None and mode not in MODE_LABELS:
                raise ValueError(f"unknown mode: {mode!r}")
            for t in tools:
                if t not in TOOL_LABELS:
                    raise ValueError(f"unknown tool: {t!r}")
            # At most one mode is stored; replacing clears any previous mode implicitly.
            self._active_mode = mode
            self._tools_on = set(tools)
            out = {"event": "modes_tools", "mode": self._active_mode, "tools": sorted(self._tools_on)}
        await self._broadcast(out)

    async def _handle_voice_command_text(self, text: str) -> bool:
        """Apply activate/deactivate voice command; return ``True`` to skip LLM for this utterance."""

        parsed = try_parse_voice_command(text)
        if parsed is None:
            return False
        action, kind, label = parsed
        async with self._modes_tools_lock:
            if kind == "mode":
                if action == "activate":
                    # Exactly one mode may be active; assigning replaces any previous mode.
                    self._active_mode = label
                elif self._active_mode == label:
                    self._active_mode = None
            elif action == "activate":
                self._tools_on.add(label)
            else:
                self._tools_on.discard(label)
            out = {"event": "modes_tools", "mode": self._active_mode, "tools": sorted(self._tools_on)}
        await self._broadcast(out)
        if self._say.running:
            await self._say.enqueue_sentence(format_command_speech(action, kind, label))
        return True

    async def unsubscribe(self, q: asyncio.Queue[dict[str, Any]]) -> None:
        async with self._q_lock:
            self._qs.discard(q)

    async def _broadcast(self, ev: dict[str, Any]) -> None:
        async with self._q_lock:
            qs = list(self._qs)
        for q in qs:
            try:
                q.put_nowait(ev)
            except asyncio.QueueFull:
                pass
        fn = self._ws_voice_notify
        if fn is not None:
            try:
                await fn(ev)
            except Exception:
                pass

    def _trim_history(self) -> None:
        cap = ollama_voice_max_history_messages()
        while len(self._llm_messages) > cap and len(self._llm_messages) > 2:
            del self._llm_messages[1]

    async def start(self) -> None:
        self._asr_cursor = self._buf.end_sample_index()
        self._llm_messages = [
            {"role": "system", "content": ollama_voice_text_system_prompt().strip()},
        ]
        self._utt_chunks = []
        self._in_utt = False
        self._silence_ms = 0.0
        timeout = httpx.Timeout(connect=30.0, read=300.0, write=30.0, pool=30.0)
        self._client = httpx.AsyncClient(timeout=timeout)
        await asyncio.to_thread(
            _preload_mlx_whisper_model,
            mlx_whisper_repo(),
            mlx_whisper_language(),
        )
        self._say.start()
        self._tasks = [
            asyncio.create_task(self._vad_loop(), name="mlx_vad_loop"),
            asyncio.create_task(self._llm_worker(), name="mlx_llm_worker"),
        ]

    async def aclose(self) -> None:
        self._stop.set()
        for t in self._tasks:
            t.cancel()
            try:
                await t
            except asyncio.CancelledError:
                pass
        self._tasks.clear()
        await self._say.aclose()
        await self._stop_move_playback()
        t_idle = self._idle_look_sweep_task
        if t_idle is not None and not t_idle.done():
            t_idle.cancel()
            try:
                await t_idle
            except asyncio.CancelledError:
                pass
        self._idle_look_sweep_task = None
        self._mic_accept_event.set()
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _stop_move_playback(self, *, cancel_daemon_motion: bool = True) -> None:
        """Stop optional ``RecordedMoves`` playback; optionally request daemon ``cancel_move``."""

        t = self._move_play_task
        self._move_play_task = None
        had_running_play = t is not None and not t.done()
        if had_running_play and self._mini is not None:
            try:
                self._mini.cancel_move()
            except Exception:
                pass
        if t is not None and not t.done():
            t.cancel()
            try:
                await t
            except asyncio.CancelledError:
                pass
        if (
            cancel_daemon_motion
            and not had_running_play
            and self._mini is not None
        ):
            try:
                self._mini.cancel_move()
            except Exception:
                pass

    def trigger_idle_look_sweep(self) -> None:
        """Start looping head + body + antenna sweeps until disabled (no-op without ``mini``)."""

        if self._mini is None:
            return
        t = self._idle_look_sweep_task
        if t is not None and not t.done():
            return
        self._idle_look_sweep_task = asyncio.create_task(
            self._idle_look_sweep_worker(),
            name="idle_look_sweep",
        )

    def _maybe_start_idle_look_sweep(self) -> None:
        if not bool(self._controls.get("idle_look_sweep_enabled")):
            return
        self.trigger_idle_look_sweep()

    async def _idle_look_sweep_worker(self) -> None:
        me = asyncio.current_task()
        mini = self._mini
        if mini is None:
            return
        try:
            await self._stop_move_playback(cancel_daemon_motion=False)
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
        try:

            def _sweep_armed() -> bool:
                return bool(self._controls.get("idle_look_sweep_enabled"))

            while _sweep_armed() and not self._stop.is_set():
                await asyncio.to_thread(run_idle_look_sweep_pass, mini, _sweep_armed)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            await self._broadcast({"event": "error", "message": f"idle_look_sweep:{e!s}"})
        finally:
            if self._idle_look_sweep_task is me:
                self._idle_look_sweep_task = None

    async def _play_move_worker(self, hf: str, move_name: str) -> None:
        mini = self._mini
        if mini is None:
            return
        try:
            from reachy_mini.motion.recorded_move import RecordedMoves

            rm = RecordedMoves(hf)
            mv = rm.get(move_name)
            # Dataset WAVs (if present) are skipped; this pipeline uses host TTS for speech audio.
            await asyncio.to_thread(mini.play_move, mv, sound=False)
        except asyncio.CancelledError:
            raise
        except Exception:
            pass

    async def on_tts_begin(self) -> None:
        self._mic_accept_event.clear()
        need_cancel = False
        async with self._utt_sync:
            self._asr_cursor = self._buf.end_sample_index()
            if self._in_utt:
                need_cancel = True
                self._in_utt = False
                self._utt_chunks = []
                self._silence_ms = 0.0
        if need_cancel:
            await self._broadcast({"event": "utterance_end", "text": ""})
        spec = self._move_spec_this_turn
        if spec is not None and self._mini is not None:
            hf, nm = spec
            await self._stop_move_playback()
            self._move_play_task = asyncio.create_task(
                self._play_move_worker(hf, nm),
                name="mlx_recorded_move",
            )

    async def on_tts_end(self) -> None:
        # Do not call ReachyMini.cancel_move here: it runs media_manager.stop_playing() and cuts
        # daemon speaker audio while TTS may still be playing (play_sound returns when queued).
        await asyncio.sleep(ollama_voice_say_post_ms() / 1000.0)
        self._mic_accept_event.set()
        self._move_spec_this_turn = None

    async def _vad_loop(self) -> None:
        sr = RobotMicRingBuffer.SAMPLE_RATE
        tick = mlx_voice_tick_sec()
        pull_max = max(int(sr * tick * 4), int(sr * 0.2))
        speech_rms = mlx_voice_speech_rms()
        silence_end = mlx_voice_silence_end_ms()
        min_utt_samples = int(sr * mlx_voice_min_utterance_ms() / 1000.0)
        max_utt_samples = int(sr * mlx_whisper_max_chunk_sec())
        gate_rms = mlx_whisper_min_rms()
        repo = mlx_whisper_repo()
        lang = mlx_whisper_language()
        while not self._stop.is_set():
            try:
                await asyncio.sleep(tick)
            except asyncio.CancelledError:
                break
            if self._stop.is_set():
                break

            if not self._mic_accept_event.is_set():
                need_cancel = False
                async with self._utt_sync:
                    self._asr_cursor = self._buf.end_sample_index()
                    if self._in_utt:
                        need_cancel = True
                        self._in_utt = False
                        self._utt_chunks = []
                        self._silence_ms = 0.0
                if need_cancel:
                    await self._broadcast({"event": "utterance_end", "text": ""})
                continue

            flush_chunks: list[np.ndarray] | None = None
            utterance_start = False
            async with self._utt_sync:
                st, new_c = self._buf.slice_since_exclusive(self._asr_cursor, pull_max)
                if st is None or int(st.shape[0]) == 0:
                    if self._in_utt:
                        self._silence_ms += tick * 1000.0
                        n = sum(int(x.shape[0]) for x in self._utt_chunks)
                        if self._silence_ms >= silence_end and n >= min_utt_samples:
                            flush_chunks = list(self._utt_chunks)
                            self._utt_chunks = []
                            self._in_utt = False
                            self._silence_ms = 0.0
                else:
                    self._asr_cursor = new_c
                    mono = stereo_float32_to_mono_float32(st)
                    r = _mono_rms(mono)
                    if not self._in_utt:
                        if r >= speech_rms:
                            self._in_utt = True
                            self._utt_chunks = [st]
                            self._silence_ms = 0.0
                            utterance_start = True
                    else:
                        self._utt_chunks.append(st)
                        if r >= speech_rms:
                            self._silence_ms = 0.0
                        else:
                            self._silence_ms += tick * 1000.0
                        n = sum(int(x.shape[0]) for x in self._utt_chunks)
                        if (self._silence_ms >= silence_end and n >= min_utt_samples) or n >= max_utt_samples:
                            flush_chunks = list(self._utt_chunks)
                            self._utt_chunks = []
                            self._in_utt = False
                            self._silence_ms = 0.0

            if utterance_start:
                await self._broadcast({"event": "utterance_start"})
            if flush_chunks is not None:
                await self._flush_utterance(flush_chunks, repo, lang, gate_rms)

    async def _flush_utterance(
        self, chunks: list[np.ndarray], repo: str, lang: str | None, gate_rms: float
    ) -> None:
        if not chunks:
            return
        audio = np.concatenate(chunks, axis=0)
        mono = stereo_float32_to_mono_float32(audio)
        if gate_rms > 0.0 and _mono_rms(mono) < gate_rms:
            return
        try:
            result = await asyncio.to_thread(_mlx_transcribe_fn, mono, repo, lang)
        except asyncio.CancelledError:
            return
        except Exception as e:
            await self._broadcast({"event": "error", "message": f"mlx_whisper:{e!s}"})
            return
        text = _scrub_short_hallucination((result.get("text") or "").strip())
        if not text:
            return
        await self._broadcast({"event": "utterance_end", "text": text})
        if await self._handle_voice_command_text(text):
            return
        await self._llm_queue.put(text)

    async def _llm_worker(self) -> None:
        base = ollama_base_url()
        model = ollama_model()
        while not self._stop.is_set():
            try:
                user_text = await asyncio.wait_for(self._llm_queue.get(), timeout=0.35)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            if self._stop.is_set():
                break
            await self._run_llm_turn(user_text, base=base, model=model)

    async def _run_llm_turn(self, user_text: str, *, base: str, model: str) -> None:
        client = self._client
        if client is None:
            return
        async with self._llm_lock:
            turn_base = len(self._llm_messages)
            self._llm_messages.append({"role": "user", "content": user_text})
            await self._broadcast(
                {
                    "event": "conversation",
                    "messages": _conversation_for_sse(self._llm_messages),
                }
            )
            reply_parts: list[str] = []
            self._move_spec_this_turn = None
            use_robot_tools = (
                self._mini is not None
                and ollama_voice_robot_tools_enabled()
            )
            try:
                await self._broadcast({"event": "llm_round_start"})
                if use_robot_tools:
                    joined = (
                        await complete_chat_with_robot_tools(
                            client=client,
                            base_url=base,
                            model=model,
                            conv=self._llm_messages,
                            mini=self._mini,
                        )
                    ).strip()
                    async for frag in yield_text_as_token_chunks(joined):
                        if self._stop.is_set():
                            break
                        reply_parts.append(frag)
                        await self._broadcast({"event": "llm_token", "t": frag})
                else:
                    messages = [dict(m) for m in self._llm_messages]
                    async for frag in stream_text_chat_messages(
                        client=client,
                        base_url=base,
                        model=model,
                        messages=messages,
                    ):
                        if self._stop.is_set():
                            break
                        reply_parts.append(frag)
                        await self._broadcast({"event": "llm_token", "t": frag})
                    joined = "".join(reply_parts).strip()
                if not joined.strip():
                    await self._broadcast({"event": "llm_round_end"})
                    self._maybe_start_idle_look_sweep()
                    self._trim_history()
                    await self._broadcast(
                        {
                            "event": "conversation",
                            "messages": _conversation_for_sse(self._llm_messages),
                        }
                    )
                    return
                try:
                    pair, speech, assistant_content = parse_voice_assistant_output(joined)
                except VoiceAssistantJsonError as e:
                    await self._broadcast({"event": "error", "message": f"assistant_json:{e!s}"})
                    del self._llm_messages[turn_base:]
                    return
                if self._say.running and speech.strip() and pair is not None:
                    self._move_spec_this_turn = pair
                if self._say.running and speech.strip() and self._move_spec_this_turn is None:
                    if robot_manage_reaction_moves_enabled():
                        self._move_spec_this_turn = select_reaction_move_for_speech(speech.strip())
                if speech.strip():
                    await _enqueue_speech_sentences(self._say, speech)
                await self._broadcast({"event": "llm_round_end"})
            except asyncio.CancelledError:
                return
            except Exception as e:
                await self._broadcast({"event": "error", "message": f"ollama_text:{e!s}"})
                del self._llm_messages[turn_base:]
                return
            if self._llm_messages and self._llm_messages[-1].get("role") == "assistant":
                self._llm_messages[-1]["content"] = assistant_content
            else:
                self._llm_messages.append({"role": "assistant", "content": assistant_content})
            self._trim_history()
            await self._broadcast(
                {
                    "event": "conversation",
                    "messages": _conversation_for_sse(self._llm_messages),
                }
            )
