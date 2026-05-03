"""RobotMicRingBuffer (no robot)."""

import numpy as np

from robot_manage.mic_buffer import RobotMicRingBuffer


def test_ring_slice_concat() -> None:
    buf = RobotMicRingBuffer(max_wall_seconds=10.0)
    for _ in range(10):
        buf.push(np.zeros((500, 2), dtype=np.float32))
    out = buf.slice_last_wall_seconds(60.0)
    assert out is not None
    assert out.shape == (5000, 2)


def test_slice_last_audio_seconds_tail() -> None:
    buf = RobotMicRingBuffer()
    buf.push(np.full((1000, 2), 0.1, dtype=np.float32))
    buf.push(np.full((1000, 2), 0.2, dtype=np.float32))
    buf.push(np.full((1000, 2), 0.3, dtype=np.float32))
    out = buf.slice_last_audio_seconds(0.125)  # 2000 samples
    assert out is not None
    assert out.shape == (2000, 2)
    assert float(np.mean(out)) > 0.25


def test_approx_buffered_seconds() -> None:
    buf = RobotMicRingBuffer()
    buf.push(np.zeros((16000, 2), dtype=np.float32))
    assert abs(buf.approx_buffered_seconds() - 1.0) < 1e-6


def test_meter_histogram_peak() -> None:
    buf = RobotMicRingBuffer()
    t = np.linspace(0, 8 * np.pi, 12000, dtype=np.float32)
    s = np.sin(t) * 0.4
    stereo = np.stack([s, s], axis=1)
    buf.push(stereo)
    levels, peak = buf.meter_histogram(wall_seconds=1.0, bars=32)
    assert len(levels) == 32
    assert peak > 0.05


def test_end_sample_index_matches_pushes() -> None:
    buf = RobotMicRingBuffer()
    assert buf.end_sample_index() == 0
    buf.push(np.zeros((100, 2), dtype=np.float32))
    assert buf.end_sample_index() == 100
    buf.push(np.zeros((50, 2), dtype=np.float32))
    assert buf.end_sample_index() == 150


def test_slice_since_exclusive_incremental() -> None:
    buf = RobotMicRingBuffer()
    buf.push(np.full((100, 2), 0.1, dtype=np.float32))
    buf.push(np.full((100, 2), 0.2, dtype=np.float32))
    a1, c1 = buf.slice_since_exclusive(0, 500)
    assert a1 is not None
    assert a1.shape == (200, 2)
    assert c1 == 200
    a2, c2 = buf.slice_since_exclusive(200, 500)
    assert a2 is None
    assert c2 == 200
    buf.push(np.full((50, 2), 0.3, dtype=np.float32))
    a3, c3 = buf.slice_since_exclusive(200, 500)
    assert a3 is not None
    assert a3.shape == (50, 2)
    assert c3 == 250
