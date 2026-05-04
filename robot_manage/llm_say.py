"""Streamed LLM output → macOS ``say`` (one sentence at a time)."""

from __future__ import annotations

import asyncio
import io
import logging
import shutil
import subprocess
from collections.abc import Callable
from typing import Final, Protocol
from uuid import uuid4

import httpx

from robot_manage.settings import ollama_voice_say_enabled, ollama_voice_say_target, ollama_voice_say_voice

log = logging.getLogger(__name__)

_TERMINATORS: Final = frozenset(".!?")
_WS: Final = frozenset(" \t\n\r")
_QUOTES: Final = frozenset("\"'")


class TtsMicHooks(Protocol):
    """Mute robot ASR while TTS plays (avoids ``say`` → speaker → mic echo)."""

    async def on_tts_begin(self) -> None: ...
    async def on_tts_end(self) -> None: ...


class _NullMicHooks:
    async def on_tts_begin(self) -> None:
        return

    async def on_tts_end(self) -> None:
        return


def pull_complete_sentences(buf: str) -> tuple[list[str], str]:
    """Return ``(complete_sentences, remainder)``.

    A sentence is complete when it ends with one or more ``.!?``, optional ASCII quotes,
    then whitespace. If punctuation reaches end-of-buffer without following whitespace,
    nothing is emitted yet (caller flushes remainder at end of stream).
    """

    sentences: list[str] = []
    i = 0
    n = len(buf)
    search = 0
    while search < n:
        found = -1
        for j in range(search, n):
            if buf[j] in _TERMINATORS:
                found = j
                break
        if found < 0:
            break
        k = found
        while k < n and buf[k] in _TERMINATORS:
            k += 1
        t = k
        while t < n and buf[t] in _QUOTES:
            t += 1
        if t >= n:
            break
        if buf[t] not in _WS:
            search = found + 1
            continue
        sent = buf[i:t].strip()
        if sent:
            sentences.append(sent)
        i = t
        while i < n and buf[i] in _WS:
            i += 1
        search = i
    return sentences, buf[i:]


def say_binary_path() -> str | None:
    """Absolute path to ``say`` when present on ``PATH``."""

    return shutil.which("say")


def say(text: str, *, voice: str | None = None) -> None:
    """Speak *text* using macOS ``say`` (blocking)."""

    b = say_binary_path()
    if not b:
        raise RuntimeError("say not found on PATH")
    cmd: list[str] = [b]
    if voice:
        cmd.extend(["-v", voice])
    cmd.append(text)
    subprocess.run(cmd, check=False, timeout=600)


class LlmSayRunner:
    """Serial queue: each sentence runs ``say`` in a worker thread.

    One ``on_tts_begin`` / ``on_tts_end`` pair per drained batch (no mic gap between
    consecutive sentences).
    """

    def __init__(
        self,
        mic_hooks: TtsMicHooks | None = None,
        *,
        reachy_host: str | None = None,
        reachy_port: int = 8000,
        is_output_muted: Callable[[], bool] | None = None,
    ) -> None:
        self._binary = say_binary_path()
        self._voice = ollama_voice_say_voice()
        self._hooks: TtsMicHooks = mic_hooks or _NullMicHooks()
        self._queue: asyncio.Queue[str | None] = asyncio.Queue()
        self._worker: asyncio.Task[None] | None = None
        self._reachy_host = reachy_host
        self._reachy_port = reachy_port
        self._is_output_muted = is_output_muted

    def start(self) -> None:
        if not ollama_voice_say_enabled():
            return
        if ollama_voice_say_target() == "macos":
            if not self._binary:
                log.warning("OLLAMA_VOICE_SAY is set but `say` was not found on PATH")
                return
        else:
            if not self._reachy_host:
                log.warning("OLLAMA_VOICE_SAY is set for reachy but no robot host was provided")
                return
        if self._worker is None:
            self._worker = asyncio.create_task(self._run(), name="mlx_llm_say")

    @property
    def running(self) -> bool:
        return self._worker is not None

    async def enqueue_sentence(self, sentence: str) -> None:
        if self._worker is None:
            return
        s = sentence.strip()
        if s:
            await self._queue.put(s)

    async def aclose(self) -> None:
        if self._worker is None:
            return
        await self._queue.put(None)
        await self._worker
        self._worker = None

    async def _run(self) -> None:
        while True:
            item = await self._queue.get()
            if item is None:
                break
            await self._hooks.on_tts_begin()
            stop_worker = False
            cur: str = item
            try:
                while True:
                    muted = self._is_output_muted is not None and self._is_output_muted()
                    if not muted:
                        if ollama_voice_say_target() == "macos":
                            assert self._binary is not None
                            await asyncio.to_thread(say, cur, voice=self._voice)
                        else:
                            await self._say_on_reachy(cur)
                    try:
                        nxt = self._queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                    if nxt is None:
                        stop_worker = True
                        break
                    cur = nxt
            finally:
                await self._hooks.on_tts_end()
            if stop_worker:
                break

    async def _say_on_reachy(self, text: str) -> None:
        host = self._reachy_host
        if not host:
            return
        try:
            from gtts import gTTS  # type: ignore[import-not-found]
        except Exception as e:  # pragma: no cover
            raise RuntimeError("gTTS is required for OLLAMA_VOICE_SAY_TARGET=reachy") from e

        # gTTS returns MP3; the Reachy daemon plays uploaded files via /api/media/play_sound.
        tts = gTTS(text=text)
        buf = io.BytesIO()
        tts.write_to_fp(buf)  # type: ignore[attr-defined]
        data = buf.getvalue()

        async with httpx.AsyncClient(base_url=f"http://{host}:{self._reachy_port}", timeout=60.0) as client:
            upload_name = f"llm_{uuid4().hex}.mp3"
            up = await client.post(
                "/api/media/sounds/upload",
                files={"file": (upload_name, data, "audio/mpeg")},
            )
            up.raise_for_status()
            path = (up.json() or {}).get("path") or ""
            filename = path.split("/")[-1] if isinstance(path, str) else ""
            if not filename:
                raise RuntimeError("Reachy daemon upload did not return a sound path")
            play = await client.post("/api/media/play_sound", json={"file": filename})
            play.raise_for_status()
