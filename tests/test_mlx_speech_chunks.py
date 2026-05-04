"""TTS chunking and placeholder stripping for MLX voice."""

from __future__ import annotations

import asyncio

import pytest

from robot_manage.llm_say import LlmSayRunner
from robot_manage.mlx_voice_pipeline import _enqueue_speech_sentences, _sanitize_tts_chunk


def test_sanitize_tts_chunk_strips_placeholders() -> None:
    assert _sanitize_tts_chunk("  (calling tools)  ") == ""
    assert _sanitize_tts_chunk("Hi (calling tools) there.") == "Hi there."


@pytest.mark.parametrize(
    ("speech", "expected"),
    [
        ("Alpha. Beta! ", ["Alpha.", "Beta!"]),
        ("One sentence only. ", ["One sentence only."]),
    ],
)
def test_enqueue_speech_sentences_say_calls(
    monkeypatch: pytest.MonkeyPatch, speech: str, expected: list[str]
) -> None:
    monkeypatch.setenv("OLLAMA_VOICE_SAY", "1")
    calls: list[str] = []

    def fake_say(text: str, *, voice: str | None = None) -> None:
        calls.append(text)

    monkeypatch.setattr("robot_manage.llm_say.say", fake_say)
    monkeypatch.setattr("robot_manage.llm_say.say_binary_path", lambda: "/bin/true")

    async def amain() -> None:
        r = LlmSayRunner()
        r._binary = "/bin/true"
        r.start()
        await _enqueue_speech_sentences(r, speech)
        await asyncio.sleep(0.2)
        await r.aclose()

    asyncio.run(amain())
    assert calls == expected
