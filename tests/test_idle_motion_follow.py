"""Motion centroid helper for idle sweep."""

from __future__ import annotations

import numpy as np

from robot_manage.idle_motion_follow import largest_motion_centroid_px


def test_largest_motion_centroid_detects_shift() -> None:
    a = np.zeros((120, 160, 3), dtype=np.uint8)
    b = a.copy()
    a[40:80, 50:90] = (200, 200, 200)
    b[40:80, 70:110] = (200, 200, 200)
    c = largest_motion_centroid_px(a, b)
    assert c is not None
    assert c[0] > 70.0
