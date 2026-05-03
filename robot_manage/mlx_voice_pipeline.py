"""MLX Whisper on silence-segmented utterances + multi-turn Ollama ``/api/chat``."""

from __future__ import annotations

import asyncio
import re
from typing import Any

import httpx
import numpy as np

from robot_manage.llm_say import LlmSayRunner, pull_complete_sentences
from robot_manage.mic_buffer import RobotMicRingBuffer
from robot_manage.ollama_voice import stream_text_chat_messages
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
    ollama_voice_say_post_ms,
    ollama_voice_text_system_prompt,
)
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
        content = str(m.get("content", ""))
        if role == "system" and i == 0 and len(content) > 480:
            content = content[:480] + "…"
        out.append({"role": role, "content": content})
    return out


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


def try_create_mlx_pipeline(buf: RobotMicRingBuffer) -> MlxLiveVoicePipeline | None:
    try:
        import mlx_whisper  # noqa: F401
    except ImportError:
        return None
    return MlxLiveVoicePipeline(buf)


async def ensure_mlx_voice_pipeline(mic_state: dict[str, Any]) -> MlxLiveVoicePipeline | None:
    """Create and start the MLX pipeline on first ``/api/voice/live`` if the mic ring exists."""

    async with _mlx_ensure_lock:
        existing = mic_state.get("mlx_pipeline")
        if existing is not None:
            return existing  # type: ignore[no-any-return]
        buf = mic_state.get("buffer")
        if buf is None:
            return None
        created = try_create_mlx_pipeline(buf)
        if created is None:
            return None
        await created.start()
        mic_state["mlx_pipeline"] = created
        return created


class MlxLiveVoicePipeline:
    def __init__(self, buf: RobotMicRingBuffer) -> None:
        self._buf = buf
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
        self._say = LlmSayRunner(mic_hooks=self)

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
        return q

    def conversation_messages_for_client(self) -> list[dict[str, str]]:
        """Snapshot of Ollama messages for HTTP restore (same truncation as SSE)."""

        return _conversation_for_sse([dict(m) for m in self._llm_messages])

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

    def _trim_history(self) -> None:
        cap = ollama_voice_max_history_messages()
        while len(self._llm_messages) > cap:
            if len(self._llm_messages) <= 2:
                break
            del self._llm_messages[1:3]

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
        self._mic_accept_event.set()
        if self._client is not None:
            await self._client.aclose()
            self._client = None

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

    async def on_tts_end(self) -> None:
        await asyncio.sleep(ollama_voice_say_post_ms() / 1000.0)
        self._mic_accept_event.set()

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
            self._llm_messages.append({"role": "user", "content": user_text})
            messages = [dict(m) for m in self._llm_messages]
            await self._broadcast(
                {
                    "event": "conversation",
                    "messages": _conversation_for_sse(self._llm_messages),
                }
            )
            reply_parts: list[str] = []
            say_buf = ""
            try:
                await self._broadcast({"event": "llm_round_start"})
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
                    say_buf += frag
                    sents, say_buf = pull_complete_sentences(say_buf)
                    for s in sents:
                        await self._say.enqueue_sentence(s)
                sents, say_buf = pull_complete_sentences(say_buf)
                for s in sents:
                    await self._say.enqueue_sentence(s)
                if say_buf.strip():
                    await self._say.enqueue_sentence(say_buf.strip())
                await self._broadcast({"event": "llm_round_end"})
            except asyncio.CancelledError:
                return
            except Exception as e:
                await self._broadcast({"event": "error", "message": f"ollama_text:{e!s}"})
                self._llm_messages.pop()
                return
            reply = "".join(reply_parts).strip()
            self._llm_messages.append({"role": "assistant", "content": reply})
            self._trim_history()
            await self._broadcast(
                {
                    "event": "conversation",
                    "messages": _conversation_for_sse(self._llm_messages),
                }
            )
