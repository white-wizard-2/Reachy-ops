"""Camera feed layout for the UI — derived from the live Reachy Mini media stack (no guessing on the client)."""

from __future__ import annotations

from typing import Any, Optional

from reachy_mini import ReachyMini


def build_camera_layout(mini: ReachyMini) -> dict[str, Any]:
    """Layout for one ``media.get_frame()`` stream; secondary slot reserved for future dual-sensor APIs."""
    camera = getattr(mini.media, "camera", None)
    camera_active = camera is not None
    specs_name: Optional[str] = None
    if camera_active and hasattr(camera, "camera_specs"):
        try:
            specs_name = type(camera.camera_specs).__name__
        except Exception:  # pragma: no cover - defensive
            specs_name = None

    primary: dict[str, Any] = {
        "id": "primary",
        "label": "Primary optical",
        "channel": "VIS-01",
        "status": "live" if camera_active else "offline",
        "stream_path": "/api/camera/mjpeg" if camera_active else None,
        "detail": None if camera_active else "No camera device on this media backend.",
    }
    secondary: dict[str, Any] = {
        "id": "secondary",
        "label": "Secondary optical",
        "channel": "VIS-02",
        "status": "unavailable",
        "stream_path": None,
        "detail": (
            "The Reachy Mini SDK publishes a single video stream per session (simulator and typical hardware). "
            "A second independent feed is not exposed yet — this viewport is reserved."
        ),
        "specs_class": specs_name,
    }
    return {
        "feeds": [primary, secondary],
        "sdk_single_stream": True,
    }
