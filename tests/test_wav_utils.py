"""WAV packing for robot mic (no hardware)."""

import wave
from io import BytesIO

import numpy as np

from robot_manage.wav_utils import float32_audio_to_wav_bytes, stereo_float32_to_mono_int16


def test_stereo_float32_to_mono_int16() -> None:
    x = np.array([[1.0, -1.0], [0.0, 0.0]], dtype=np.float32)
    m = stereo_float32_to_mono_int16(x)
    assert m.dtype == np.int16
    assert m.shape == (2,)
    assert m[0] == 0


def test_wav_has_riff_header() -> None:
    t = np.linspace(0, 0.02, 400, dtype=np.float32)
    stereo = np.stack([t * 0.0, t * 0.0], axis=1)
    wav = float32_audio_to_wav_bytes(stereo)
    assert wav[:4] == b"RIFF"
    assert wav[8:12] == b"WAVE"


def test_float32_audio_to_wav_bytes_roundtrip() -> None:
    t = np.linspace(0, 0.1, 800, dtype=np.float32)
    stereo = np.stack([np.sin(t * 440 * 2 * np.pi) * 0.1, np.sin(t * 440 * 2 * np.pi) * 0.1], axis=1)
    wav = float32_audio_to_wav_bytes(stereo)
    with wave.open(BytesIO(wav), "rb") as wf:
        assert wf.getnchannels() == 1
        assert wf.getframerate() == 16000
        assert wf.getsampwidth() == 2


def test_quiet_mic_boosted_in_wav() -> None:
    quiet = np.full((800, 2), 0.002, dtype=np.float32)
    wav = float32_audio_to_wav_bytes(quiet)
    with wave.open(BytesIO(wav), "rb") as wf:
        raw = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
    assert int(np.max(np.abs(raw))) > 8000
