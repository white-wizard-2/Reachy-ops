"""Float32 mic buffers (Reachy Mini) → mono 16 kHz WAV bytes for Ollama / Gemma4 audio chat."""

from __future__ import annotations

import io
import wave

import numpy as np


def stereo_float32_to_mono_float32(samples: np.ndarray) -> np.ndarray:
    """Shape ``(N, 2)`` or ``(N,)`` float32 ~[-1, 1] → ``(N,)`` mono float32."""
    if samples.dtype != np.float32:
        raise TypeError("expected float32 audio")
    if samples.ndim == 1:
        mono = samples
    elif samples.ndim == 2 and samples.shape[1] == 2:
        mono = np.mean(samples, axis=1).astype(np.float32, copy=False)
    else:
        raise ValueError(f"expected (N,) or (N,2) audio, got {samples.shape}")
    return np.clip(mono, -1.0, 1.0)


def normalize_quiet_mono(mono: np.ndarray, *, target_peak: float = 0.92, gain_below: float = 0.14) -> np.ndarray:
    """Scale up quiet clips so int16/WAV carries usable energy for multimodal models."""
    if mono.size == 0:
        return mono
    peak = float(np.max(np.abs(mono)))
    if peak <= 1e-9 or peak >= gain_below:
        return mono
    scaled = mono * (target_peak / peak)
    return np.clip(scaled, -1.0, 1.0).astype(np.float32, copy=False)


def stereo_float32_to_mono_int16(samples: np.ndarray) -> np.ndarray:
    """Shape ``(N, 2)`` float32 ~[-1, 1] → ``(N,)`` int16 mono."""
    mono = normalize_quiet_mono(stereo_float32_to_mono_float32(samples))
    return (mono * 32767.0).astype(np.int16)


def pcm_mono_int16_to_wav_bytes(pcm: np.ndarray, *, sample_rate: int = 16000) -> bytes:
    """RIFF WAV (16-bit mono PCM)."""
    if pcm.dtype != np.int16:
        raise TypeError("expected int16 PCM")
    if pcm.ndim != 1:
        raise ValueError("expected 1-D PCM")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(int(sample_rate))
        wf.writeframes(pcm.tobytes())
    return buf.getvalue()


def float32_audio_to_wav_bytes(audio: np.ndarray, *, sample_rate: int = 16000) -> bytes:
    """Full path: Reachy ``get_audio_sample`` stack → WAV bytes."""
    mono = stereo_float32_to_mono_int16(audio)
    return pcm_mono_int16_to_wav_bytes(mono, sample_rate=sample_rate)
