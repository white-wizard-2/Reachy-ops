"""camera_layout (no robot — simple stand-ins)."""

from unittest.mock import MagicMock

from robot_manage.camera_layout import build_camera_layout


class _Specs:
    pass


class _Cam:
    camera_specs = _Specs()


def test_build_camera_layout_live_primary() -> None:
    mini = MagicMock()
    mini.media.camera = _Cam()
    out = build_camera_layout(mini)
    assert out["sdk_single_stream"] is True
    assert len(out["feeds"]) == 1
    assert out["feeds"][0]["stream_path"] == "/api/camera/mjpeg"
    assert out["feeds"][0]["status"] == "live"


def test_build_camera_layout_offline_when_no_camera() -> None:
    mini = MagicMock()
    mini.media.camera = None
    out = build_camera_layout(mini)
    assert out["feeds"][0]["status"] == "offline"
    assert out["feeds"][0]["stream_path"] is None
