"""Background capture from Reachy Mini ``media.get_frame()`` into a shared JPEG buffer."""

from __future__ import annotations

import threading
import time
from typing import Optional

import numpy as np
from reachy_mini import ReachyMini

from robot_manage.jpeg_util import bgr_frame_to_jpeg_bytes

# GStreamer can yield None briefly during preroll (same behaviour as legacy learner stack).
_FRAME_GRAB_ATTEMPTS = 90
_FRAME_GRAB_INTERVAL_S = 0.02


class MiniCameraPublisher:
    """Single worker thread grabs BGR frames and publishes the latest JPEG."""

    def __init__(
        self,
        mini: ReachyMini,
        *,
        jpeg_quality: int = 85,
        max_fps: float = 20.0,
    ) -> None:
        self._mini = mini
        self._jpeg_quality = int(jpeg_quality)
        self._period_s = 1.0 / float(max_fps) if max_fps > 0 else 0.0
        self._lock = threading.Lock()
        self._latest: Optional[bytes] = None
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="robot_manage_camera", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None

    def get_latest_jpeg(self) -> Optional[bytes]:
        with self._lock:
            return self._latest

    def _grab_frame(self) -> Optional[np.ndarray]:
        for _ in range(_FRAME_GRAB_ATTEMPTS):
            if self._stop.is_set():
                return None
            frame = self._mini.media.get_frame()
            if frame is not None:
                return frame
            time.sleep(_FRAME_GRAB_INTERVAL_S)
        return None

    def _run(self) -> None:
        while not self._stop.is_set():
            t0 = time.monotonic()
            frame = self._grab_frame()
            if frame is None:
                continue
            jpeg = bgr_frame_to_jpeg_bytes(frame, quality=self._jpeg_quality)
            with self._lock:
                self._latest = jpeg
            elapsed = time.monotonic() - t0
            sleep_left = self._period_s - elapsed
            if sleep_left > 0:
                self._stop.wait(sleep_left)
