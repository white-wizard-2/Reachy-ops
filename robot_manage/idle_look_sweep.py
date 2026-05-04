"""Head + body yaw + antenna sweep (Pollen SDK: current body yaw from ``head_joints[0]``)."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any, Final

import numpy as np
from scipy.spatial.transform import Rotation as R

# One ``goto_target`` per row; sleep past ``duration`` so the daemon finishes before the next
# command (avoids preemption / stacked jerks). Durations ~1.4× the old fast sweep — visible
# motion, still slower than the original ~0.75–1.0s snaps.
_SETTLE_AFTER_MOVE_S: Final[float] = 0.18

_SWEEP_KEYFRAMES: Final[
    list[tuple[float, float, float, tuple[float, float], float]]
] = [
    # hy, hp, body_db, (ant_r, ant_l), duration_s
    (0.0, 0.0, 0.0, (0.0, 0.0), 1.15),
    (0.14, 0.05, 0.18, (0.18, -0.16), 1.48),
    (0.06, 0.1, 0.28, (0.16, 0.14), 1.48),
    (-0.1, 0.04, 0.16, (-0.16, 0.18), 1.48),
    (-0.16, -0.03, -0.12, (-0.18, -0.16), 1.48),
    (-0.05, -0.1, -0.28, (0.14, -0.14), 1.48),
    (0.1, -0.05, -0.2, (-0.14, 0.12), 1.48),
    (0.05, 0.07, -0.08, (0.12, -0.12), 1.42),
    (0.0, 0.09, 0.1, (-0.14, -0.14), 1.42),
    (-0.1, -0.06, 0.22, (0.15, 0.13), 1.48),
    (0.04, 0.0, 0.0, (0.0, 0.0), 1.55),
]


def _current_body_yaw_reference(mini: Any) -> float:
    """Match Pollen ``sweep_look`` profile: first head joint tracks body yaw reference."""

    hj, _ = mini.get_current_joint_positions()
    if not hj:
        return 0.0
    return float(hj[0])


def _pose_leveled_yaw_pitch(init: np.ndarray, yaw_off: float, pitch_off: float) -> np.ndarray:
    """Apply yaw/pitch deltas in fixed ``ZYX`` Euler space and **zero roll** so the camera stays upright."""

    r0 = init[:3, :3]
    t0 = init[:3, 3]
    yaw0, pitch0, _roll0 = R.from_matrix(r0).as_euler("ZYX", degrees=False)
    r1 = R.from_euler("ZYX", [yaw0 + yaw_off, pitch0 + pitch_off, 0.0], degrees=False).as_matrix()
    out = np.eye(4, dtype=np.float64)
    out[:3, :3] = r1
    out[:3, 3] = t0
    return out


def run_idle_look_sweep_pass(mini: Any, should_continue: Callable[[], bool]) -> None:
    """One full pan: head + explicit ``body_yaw`` + antennas. Stops early if ``should_continue`` is false."""

    if not should_continue():
        return

    init = np.asarray(mini.get_current_head_pose(), dtype=np.float64)
    if init.shape != (4, 4):
        raise ValueError(f"expected 4x4 head pose, got {init.shape}")

    y0 = _current_body_yaw_reference(mini)

    for hy, hp, body_db, (ar, al), dur in _SWEEP_KEYFRAMES:
        if not should_continue():
            return
        head = _pose_leveled_yaw_pitch(init, float(hy), float(hp))
        body_yaw = y0 + float(body_db)
        d = float(dur)
        mini.goto_target(
            head=head,
            antennas=[float(ar), float(al)],
            duration=d,
            body_yaw=body_yaw,
        )
        time.sleep(d + _SETTLE_AFTER_MOVE_S)


def run_idle_look_sweep(mini: Any) -> None:
    """Single pass (no early exit); used by tests and one-shot callers."""

    run_idle_look_sweep_pass(mini, lambda: True)
