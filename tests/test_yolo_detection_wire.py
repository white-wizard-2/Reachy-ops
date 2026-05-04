"""YOLO WebSocket wire format (no MLX)."""

from __future__ import annotations

from robot_manage.yolo_detection_wire import track_row, yolo_detections_message


def test_yolo_detections_message_shape() -> None:
    m = yolo_detections_message(
        frame_hw=(480, 640),
        tracks=[
            track_row(xyxy=(10.0, 20.0, 110.0, 220.0), conf=0.91, cls_id=0, label="person", track_id=3),
        ],
    )
    assert m["type"] == "yolo_detections"
    assert m["frame_hw"] == [480, 640]
    assert len(m["tracks"]) == 1
    t0 = m["tracks"][0]
    assert t0["label"] == "person"
    assert t0["id"] == 3
    assert t0["cls"] == 0
    assert t0["xyxy"] == [10.0, 20.0, 110.0, 220.0]
