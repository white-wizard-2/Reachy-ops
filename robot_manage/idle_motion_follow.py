"""Frame-differencing motion → ``look_at_image`` (idle sweep helper)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Final

import cv2
import numpy as np

_THRESH: Final[int] = 32
_BLUR: Final[tuple[int, int]] = (7, 7)
_MIN_AREA_RATIO: Final[float] = 0.006


def largest_motion_centroid_px(prev_bgr: np.ndarray, cur_bgr: np.ndarray) -> tuple[float, float] | None:
    """Return ``(cx, cy)`` in pixel coords of dominant motion blob, or ``None``."""

    if prev_bgr.shape != cur_bgr.shape or prev_bgr.ndim != 3:
        return None
    p = cv2.cvtColor(prev_bgr, cv2.COLOR_BGR2GRAY)
    c = cv2.cvtColor(cur_bgr, cv2.COLOR_BGR2GRAY)
    p = cv2.GaussianBlur(p, _BLUR, 0)
    c = cv2.GaussianBlur(c, _BLUR, 0)
    diff = cv2.absdiff(p, c)
    _, mask = cv2.threshold(diff, _THRESH, 255, cv2.THRESH_BINARY)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8), iterations=1)
    area_min = max(200, int(_MIN_AREA_RATIO * float(mask.shape[0] * mask.shape[1])))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best: tuple[float, float, float] | None = None
    for cnt in contours:
        a = float(cv2.contourArea(cnt))
        if a < area_min:
            continue
        m = cv2.moments(cnt)
        if m["m00"] <= 1e-6:
            continue
        cx = float(m["m10"] / m["m00"])
        cy = float(m["m01"] / m["m00"])
        if best is None or a > best[2]:
            best = (cx, cy, a)
    if best is None:
        return None
    return best[0], best[1]


def follow_motion_if_any(
    mini: Any,
    prev_bgr: np.ndarray | None,
    cur_bgr: np.ndarray,
    *,
    should_continue: Callable[[], bool],
    look_duration: float = 0.95,
) -> np.ndarray:
    """If motion is seen vs ``prev_bgr``, call ``look_at_image`` toward the centroid."""

    if not should_continue():
        return cur_bgr
    if prev_bgr is not None and prev_bgr.shape == cur_bgr.shape:
        hit = largest_motion_centroid_px(prev_bgr, cur_bgr)
        if hit is not None:
            h, w = int(cur_bgr.shape[0]), int(cur_bgr.shape[1])
            u = int(np.clip(round(hit[0]), 0, w - 1))
            v = int(np.clip(round(hit[1]), 0, h - 1))
            mini.look_at_image(u, v, duration=look_duration, perform_movement=True)
    return cur_bgr
