"""Continuous robot mic capture into a ring buffer (Reachy Mini SDK ``get_audio_sample``)."""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Deque, Optional

import numpy as np


@dataclass
class _Chunk:
    """One stereo pull from ``MediaManager.get_audio_sample``."""

    t_end: float
    sample_start: int
    sample_end: int
    data: np.ndarray


class RobotMicRingBuffer:
    """Thread-safe ring of recent mic chunks; wall-clock window for slicing."""

    SAMPLE_RATE = 16000

    def __init__(self, *, max_wall_seconds: float = 90.0) -> None:
        self._max_wall = float(max_wall_seconds)
        self._chunks: Deque[_Chunk] = deque()
        self._lock = threading.Lock()
        self._next_sample_ix: int = 0

    def push(self, sample: Optional[np.ndarray]) -> None:
        if sample is None or sample.size == 0:
            return
        if sample.ndim != 2 or sample.shape[1] != 2:
            raise ValueError(f"expected stereo (N,2), got {sample.shape}")
        now = time.monotonic()
        n = int(sample.shape[0])
        with self._lock:
            s0 = self._next_sample_ix
            s1 = s0 + n
            self._next_sample_ix = s1
            self._chunks.append(_Chunk(t_end=now, sample_start=s0, sample_end=s1, data=sample))
            self._prune_unlocked(now)

    def _prune_unlocked(self, now: float) -> None:
        while self._chunks and (now - self._chunks[0].t_end) > self._max_wall:
            self._chunks.popleft()

    def approx_buffered_seconds(self) -> float:
        with self._lock:
            total = sum(int(c.data.shape[0]) for c in self._chunks)
        return total / self.SAMPLE_RATE

    def slice_last_wall_seconds(self, wall_seconds: float) -> Optional[np.ndarray]:
        """Concatenate all chunks whose end time falls inside the last ``wall_seconds``."""
        now = time.monotonic()
        cutoff = now - float(wall_seconds)
        with self._lock:
            parts = [c.data for c in self._chunks if c.t_end > cutoff]
        if not parts:
            return None
        return np.concatenate(parts, axis=0)

    def slice_last_audio_seconds(self, seconds: float) -> Optional[np.ndarray]:
        """Last ``seconds`` of captured samples (newest tail), aligned to sample count not chunk clocks."""
        target = max(1, int(float(seconds) * self.SAMPLE_RATE))
        with self._lock:
            chunks = list(self._chunks)
        if not chunks:
            return None
        parts: list[np.ndarray] = []
        total = 0
        for c in reversed(chunks):
            parts.append(c.data)
            total += int(c.data.shape[0])
            if total >= target:
                break
        if not parts:
            return None
        parts.reverse()
        out = np.concatenate(parts, axis=0)
        if out.shape[0] > target:
            out = out[-target:, :]
        return out

    def end_sample_index(self) -> int:
        """Monotonic exclusive end index of the next sample that will be pushed."""

        with self._lock:
            return int(self._next_sample_ix)

    def slice_since_exclusive(
        self, after_exclusive: int, max_samples: int
    ) -> tuple[Optional[np.ndarray], int]:
        """Stereo float32 samples with global index ``> after_exclusive``, at most ``max_samples`` rows.

        If the ring pruned chunks before ``after_exclusive``, the cursor is advanced to the oldest
        retained sample so callers do not spin on dropped history.

        Returns ``(audio_or_none, new_cursor)`` where ``new_cursor`` is the exclusive end index of
        audio covered by this slice (advance the ASR cursor to this value only after a successful
        transcribe of ``audio``).
        """

        if max_samples < 1:
            return None, after_exclusive
        with self._lock:
            if not self._chunks:
                return None, after_exclusive
            oldest = self._chunks[0]
            cur = max(int(after_exclusive), int(oldest.sample_start))
            newest_end = int(self._chunks[-1].sample_end)
            if cur >= newest_end:
                return None, cur
            parts: list[np.ndarray] = []
            taken = 0
            glob_start: Optional[int] = None
            cur_running = cur
            for c in self._chunks:
                if c.sample_end <= cur_running:
                    continue
                row_lo = max(0, cur_running - c.sample_start)
                row_hi = int(c.data.shape[0])
                if row_lo >= row_hi:
                    continue
                seg = c.data[row_lo:row_hi]
                if seg.shape[0] == 0:
                    continue
                need = max_samples - taken
                if seg.shape[0] > need:
                    seg = seg[:need]
                if glob_start is None:
                    glob_start = int(c.sample_start + row_lo)
                parts.append(seg)
                taken += int(seg.shape[0])
                cur_running = int(c.sample_start + row_lo + seg.shape[0])
                if taken >= max_samples:
                    break
            if not parts or glob_start is None:
                return None, cur
            out = np.concatenate(parts, axis=0)
            new_cursor = glob_start + taken
            return out, new_cursor

    def meter_histogram(self, *, wall_seconds: float = 0.35, bars: int = 40) -> tuple[list[float], float]:
        """RMS per time segment over recent audio → bar heights in ``[0, 1]`` and overall peak."""
        audio = self.slice_last_audio_seconds(wall_seconds)
        if audio is None or audio.shape[0] < 8:
            return [0.0] * int(bars), 0.0
        mono = np.mean(audio.astype(np.float64), axis=1)
        n = int(mono.shape[0])
        b = int(bars)
        w = max(n // b, 1)
        levels: list[float] = []
        for i in range(b):
            seg = mono[i * w : (i + 1) * w]
            if seg.size == 0:
                levels.append(0.0)
                continue
            rms = float(np.sqrt(np.mean(np.square(seg))))
            levels.append(min(1.0, rms * 18.0))
        peak = max(levels) if levels else 0.0
        return levels, peak


class MicCollectorThread(threading.Thread):
    """Background drain of ``mini.media.get_audio_sample`` into ``RobotMicRingBuffer``."""

    def __init__(self, mini: Any, buf: RobotMicRingBuffer) -> None:
        super().__init__(name="robot_manage_mic_ring", daemon=True)
        self._mini = mini
        self._buf = buf
        self._stop = threading.Event()

    def run(self) -> None:
        while not self._stop.is_set():
            try:
                sample = self._mini.media.get_audio_sample()
                self._buf.push(sample)
            except Exception:  # noqa: BLE001 — keep collector alive if the SDK hiccups
                pass
            time.sleep(0.001)

    def stop_join(self, *, join_timeout_s: float = 3.0) -> None:
        self._stop.set()
        self.join(timeout=join_timeout_s)
