"""BGR frame → JPEG bytes (shared by stream server and tests)."""

from __future__ import annotations

import cv2
import numpy as np


def bgr_frame_to_jpeg_bytes(frame: np.ndarray, *, quality: int = 85) -> bytes:
    """Encode a BGR ``uint8`` image as JPEG."""
    if frame.dtype != np.uint8:
        raise TypeError(f"Expected uint8 BGR frame, got dtype={frame.dtype!r}")
    if frame.ndim != 3 or frame.shape[2] != 3:
        raise ValueError(f"Expected HxWx3 BGR, got shape={frame.shape!r}")
    ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)])
    if not ok:
        raise RuntimeError("OpenCV failed to JPEG-encode the frame")
    return buf.tobytes()
