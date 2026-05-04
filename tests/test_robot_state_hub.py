"""Tests for ``robot_manage.robot_state_hub``."""

from __future__ import annotations

from typing import Any

from robot_manage.robot_state_hub import RobotStateHub


def test_public_message_shape() -> None:
    async def _noop(_: dict[str, Any]) -> None:
        return None

    hub = RobotStateHub(lambda: None, _noop)
    m = hub.public_message()
    assert m["type"] == "robot_state"
    assert m["data"] is None
    assert m["error"] is None
    assert m["fetched_at"] is None
