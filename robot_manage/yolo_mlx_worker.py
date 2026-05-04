"""Background YOLO-MLX ByteTrack on camera BGR frames → WebSocket overlay + optional ``look_at_image``."""

from __future__ import annotations

import asyncio
import logging
import math
import threading
import time
from collections.abc import Awaitable, Callable
from typing import Any

import numpy as np

from robot_manage.yolo_detection_wire import track_row, yolo_detections_message

_LOG = logging.getLogger(__name__)


class YoloMlxVisionWorker:
    """Runs ``yolo26mlx.YOLO.track(..., persist=True)`` on the latest camera frame (~12 Hz)."""

    def __init__(
        self,
        *,
        loop: asyncio.AbstractEventLoop,
        broadcast_json: Callable[[dict[str, Any]], Awaitable[None]],
        get_bgr: Callable[[], np.ndarray | None],
        mini_ref: list[Any],
        mic_state: dict[str, Any],
        weights_path: str,
    ) -> None:
        self._loop = loop
        self._broadcast_json = broadcast_json
        self._get_bgr = get_bgr
        self._mini_ref = mini_ref
        self._mic_state = mic_state
        self._weights_path = weights_path
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._model: Any = None
        self._prev_tid_center: dict[int, tuple[float, float]] = {}
        self._last_look_m = 0.0
        self._last_err_log_m = 0.0

    def is_alive(self) -> bool:
        t = self._thread
        return t is not None and t.is_alive()

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="robot_manage_yolo_mlx", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=8.0)
            self._thread = None
        self._model = None

    def _emit(self, payload: dict[str, Any]) -> None:
        def _done(fut: asyncio.Future[Any]) -> None:
            try:
                fut.result()
            except Exception as e:  # noqa: BLE001
                _LOG.debug("yolo ws broadcast: %s", e)

        fut = asyncio.run_coroutine_threadsafe(self._broadcast_json(payload), self._loop)
        fut.add_done_callback(_done)

    def _run(self) -> None:
        try:
            from yolo26mlx import YOLO  # noqa: PLC0415
        except Exception as e:  # noqa: BLE001
            _LOG.warning("yolo-mlx import failed (%s); vision worker exits", e)
            return

        try:
            self._model = YOLO(self._weights_path, verbose=False)
        except Exception as e:  # noqa: BLE001
            _LOG.warning("YOLO load failed (%s): %s", self._weights_path, e)
            return

        model = self._model
        period_s = 1.0 / 12.0
        min_move_px = 10.0
        look_cooldown_s = 0.55
        look_duration = 0.85

        while not self._stop.is_set():
            t0 = time.monotonic()
            if not bool(self._mic_state.get("camera_enabled", True)):
                self._stop.wait(0.12)
                continue
            mini = self._mini_ref[0]
            if mini is None:
                self._stop.wait(0.2)
                continue
            bgr = self._get_bgr()
            if bgr is None:
                self._stop.wait(0.02)
                continue
            h, w = int(bgr.shape[0]), int(bgr.shape[1])
            try:
                tracked = model.track(bgr, persist=True, conf=0.28, imgsz=512, tracker="bytetrack.yaml")[0]
            except Exception as e:  # noqa: BLE001
                now = time.monotonic()
                if now - self._last_err_log_m > 5.0:
                    _LOG.warning("yolo track failed: %s", e)
                    self._last_err_log_m = now
                self._stop.wait(period_s)
                continue

            boxes = tracked.boxes
            names_any = getattr(tracked, "names", None)
            if not isinstance(names_any, dict):
                names_any = getattr(model, "names", {})
            if not isinstance(names_any, dict):
                names_any = {}
            names: dict[Any, str] = names_any  # type: ignore[assignment]
            rows: list[dict[str, Any]] = []
            if boxes is not None and len(boxes) > 0:
                xy = boxes.xyxy
                cls_arr = boxes.cls
                cf = boxes.conf
                ids = boxes.id
                for i in range(len(boxes)):
                    cidx = int(cls_arr[i])
                    lab = str(names.get(cidx, f"class{cidx}"))
                    tid_i: int | None = int(ids[i]) if ids is not None else None
                    x1, y1, x2, y2 = float(xy[i, 0]), float(xy[i, 1]), float(xy[i, 2]), float(xy[i, 3])
                    rows.append(
                        track_row(
                            xyxy=(x1, y1, x2, y2),
                            conf=float(cf[i]),
                            cls_id=cidx,
                            label=lab,
                            track_id=tid_i,
                        )
                    )

            self._emit(yolo_detections_message(frame_hw=(h, w), tracks=rows))

            if (
                bool(self._mic_state.get("yolo_follow_enabled", True))
                and bool(self._mic_state.get("bot_awake", True))
                and boxes is not None
                and boxes.is_track
                and len(boxes) > 0
            ):
                look = self._pick_look_pixel(boxes, min_move_px=min_move_px)
                if look is not None:
                    u, v = look
                    now2 = time.monotonic()
                    if now2 - self._last_look_m >= look_cooldown_s:
                        try:
                            mini.look_at_image(u, v, duration=look_duration, perform_movement=True)
                            self._last_look_m = now2
                        except Exception as e:  # noqa: BLE001
                            if now2 - self._last_err_log_m > 5.0:
                                _LOG.warning("look_at_image: %s", e)
                                self._last_err_log_m = now2

            elapsed = time.monotonic() - t0
            self._stop.wait(max(0.001, period_s - elapsed))

    def _pick_look_pixel(self, boxes: Any, *, min_move_px: float) -> tuple[int, int] | None:
        ids = boxes.id
        if ids is None:
            return None
        xy = boxes.xyxy
        cf = boxes.conf
        snap = dict(self._prev_tid_center)
        cur: dict[int, tuple[float, float]] = {}
        best: tuple[float, int, int] | None = None
        for i in range(len(boxes)):
            tid = int(ids[i])
            x1, y1, x2, y2 = float(xy[i, 0]), float(xy[i, 1]), float(xy[i, 2]), float(xy[i, 3])
            cx = 0.5 * (x1 + x2)
            cy = 0.5 * (y1 + y2)
            cur[tid] = (cx, cy)
            ocx, ocy = snap.get(tid, (cx, cy))
            dist = math.hypot(cx - ocx, cy - ocy)
            sc = dist * float(cf[i])
            if dist >= min_move_px and (best is None or sc > best[0]):
                best = (sc, int(round(cx)), int(round(cy)))
        self._prev_tid_center.clear()
        self._prev_tid_center.update(cur)
        if best is None:
            return None
        return best[1], best[2]
