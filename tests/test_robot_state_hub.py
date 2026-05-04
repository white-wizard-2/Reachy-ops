"""Tests for ``robot_manage.robot_state_hub``."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

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


def test_poll_once_retries_after_500() -> None:
    n = {"c": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        n["c"] += 1
        if n["c"] == 1:
            return httpx.Response(500, request=request)
        return httpx.Response(200, json={"control_mode": "ok", "body_yaw": 0.1}, request=request)

    async def _run() -> None:
        async def _emit(_: dict[str, Any]) -> None:
            return None

        hub = RobotStateHub(lambda: "http://robot.test/api/state/full", _emit)
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            await hub.poll_once(client)
        assert n["c"] == 2
        assert hub.data == {"control_mode": "ok", "body_yaw": 0.1}
        assert hub.error is None

    asyncio.run(_run())
