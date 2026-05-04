"""Idle look sweep motion (no robot)."""

from __future__ import annotations

import numpy as np
import pytest
from scipy.spatial.transform import Rotation as R

from robot_manage.idle_look_sweep import (
    _SWEEP_KEYFRAMES,
    _pose_leveled_yaw_pitch,
    run_idle_look_sweep,
    run_idle_look_sweep_pass,
)


def test_run_idle_look_sweep_pass_calls_goto_with_body_yaw(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("robot_manage.idle_look_sweep.time.sleep", lambda *_a, **_k: None)
    class _Media:
        @staticmethod
        def get_frame() -> None:
            return None

    class Mini:
        media = _Media()

        def __init__(self) -> None:
            self.goto_calls: list[dict] = []

        def get_current_head_pose(self) -> np.ndarray:
            return np.eye(4, dtype=np.float64)

        def get_current_joint_positions(self) -> tuple[list[float], list[float]]:
            return ([0.25] + [0.0] * 6, [0.0, 0.0])

        def goto_target(self, **kw: object) -> None:
            self.goto_calls.append(dict(kw))

    m = Mini()
    run_idle_look_sweep(m)
    assert len(m.goto_calls) == len(_SWEEP_KEYFRAMES)
    for c in m.goto_calls:
        assert "body_yaw" in c and isinstance(c["body_yaw"], float)


def test_pose_leveled_yaw_pitch_zeros_roll() -> None:
    init = np.eye(4, dtype=np.float64)
    init[:3, :3] = R.from_euler("ZYX", [0.12, 0.08, 0.55], degrees=False).as_matrix()
    out = _pose_leveled_yaw_pitch(init, 0.03, -0.02)
    *_, roll = R.from_matrix(out[:3, :3]).as_euler("ZYX", degrees=False)
    assert abs(roll) < 1e-9


def test_run_idle_look_sweep_pass_stops_early() -> None:
    class Mini:
        def get_current_head_pose(self) -> np.ndarray:
            return np.eye(4, dtype=np.float64)

        def get_current_joint_positions(self) -> tuple[list[float], list[float]]:
            return ([0.0] * 7, [0.0, 0.0])

        def goto_target(self, **kw: object) -> None:
            raise AssertionError("should not run")

    n = {"i": 0}

    def cont() -> bool:
        n["i"] += 1
        return False

    run_idle_look_sweep_pass(Mini(), cont)
