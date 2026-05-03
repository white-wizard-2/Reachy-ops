import numpy as np
import pytest

from robot_manage.mlx_voice_pipeline import _conversation_for_sse, _mono_rms, _scrub_short_hallucination
from robot_manage.settings import (
    mlx_whisper_condition_on_previous_text,
    mlx_whisper_min_rms,
    mlx_whisper_no_speech_threshold,
)


def test_scrub_thank_you_variants() -> None:
    assert _scrub_short_hallucination("Thank you.") == ""
    assert _scrub_short_hallucination("  Thanks!  ") == ""
    assert _scrub_short_hallucination("THANK YOU") == ""


def test_scrub_keeps_substantive() -> None:
    assert _scrub_short_hallucination("Thank you for the update.") == "Thank you for the update."
    assert _scrub_short_hallucination("Move the arm left") == "Move the arm left"


def test_mono_rms_silence_vs_tone() -> None:
    z = np.zeros(1000, dtype=np.float32)
    assert _mono_rms(z) == 0.0
    s = np.full(1000, 0.2, dtype=np.float32)
    assert _mono_rms(s) > 0.15


def test_conversation_for_sse_truncates_long_system() -> None:
    long_sys = "x" * 600
    msgs = [
        {"role": "system", "content": long_sys},
        {"role": "user", "content": "hi"},
    ]
    out = _conversation_for_sse(msgs)
    assert out[0]["role"] == "system"
    assert len(out[0]["content"]) == 481
    assert out[0]["content"].endswith("…")
    assert out[1] == {"role": "user", "content": "hi"}


def test_conversation_for_sse_mid_system_not_truncated() -> None:
    msgs = [
        {"role": "user", "content": "a"},
        {"role": "system", "content": "x" * 600},
    ]
    out = _conversation_for_sse(msgs)
    assert len(out[1]["content"]) == 600


def test_mlx_whisper_threshold_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MLX_WHISPER_NO_SPEECH_THRESHOLD", raising=False)
    monkeypatch.delenv("MLX_WHISPER_MIN_RMS", raising=False)
    monkeypatch.delenv("MLX_WHISPER_CONDITION_ON_PREVIOUS", raising=False)
    assert mlx_whisper_no_speech_threshold() == 0.82
    assert mlx_whisper_min_rms() == 0.01
    assert mlx_whisper_condition_on_previous_text() is False
