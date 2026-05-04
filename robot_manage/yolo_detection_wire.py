"""Serialize YOLO / tracking boxes for the web UI (no MLX imports here)."""

from __future__ import annotations

import time
from typing import Any


def yolo_detections_message(
    *,
    frame_hw: tuple[int, int],
    tracks: list[dict[str, Any]],
) -> dict[str, Any]:
    """WebSocket payload for Primary Optics overlay (``type``: ``yolo_detections``)."""

    h, w = int(frame_hw[0]), int(frame_hw[1])
    return {
        "type": "yolo_detections",
        "frame_hw": [h, w],
        "tracks": tracks,
        "t_ms": int(time.time() * 1000.0),
    }


def track_row(
    *,
    xyxy: tuple[float, float, float, float],
    conf: float,
    cls_id: int,
    label: str,
    track_id: int | None,
) -> dict[str, Any]:
    x1, y1, x2, y2 = xyxy
    return {
        "id": track_id,
        "cls": int(cls_id),
        "label": str(label),
        "conf": round(float(conf), 4),
        "xyxy": [round(float(x1), 2), round(float(y1), 2), round(float(x2), 2), round(float(y2), 2)],
    }
