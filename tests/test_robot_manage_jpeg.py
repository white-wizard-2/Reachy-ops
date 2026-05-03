"""robot_manage JPEG helper (no robot)."""

import numpy as np

from robot_manage.jpeg_util import bgr_frame_to_jpeg_bytes


def test_bgr_frame_to_jpeg_bytes_round_trip_shape() -> None:
    frame = np.zeros((64, 48, 3), dtype=np.uint8)
    frame[:, :, 0] = 40
    frame[:, :, 1] = 120
    frame[:, :, 2] = 200
    out = bgr_frame_to_jpeg_bytes(frame, quality=90)
    assert isinstance(out, bytes)
    assert len(out) > 100
    assert out[:2] == b"\xff\xd8"
