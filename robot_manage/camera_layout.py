"""Camera feed layout for the UI — derived from the live Reachy Mini media stack (no guessing on the client)."""

from __future__ import annotations

from typing import Any

from reachy_mini import ReachyMini


def build_camera_layout(mini: ReachyMini) -> dict[str, Any]:
    """Layout for ``media.get_frame()`` MJPEG when the camera device is present."""
    camera = getattr(mini.media, "camera", None)
    camera_active = camera is not None

    primary: dict[str, Any] = {
        "id": "primary",
        "label": "Primary optical",
        "channel": "VIS-01",
        "status": "live" if camera_active else "offline",
        "stream_path": "/api/camera/mjpeg" if camera_active else None,
        "detail": None if camera_active else "No camera device on this media backend.",
    }
    return {
        "feeds": [primary],
        "sdk_single_stream": True,
    }
