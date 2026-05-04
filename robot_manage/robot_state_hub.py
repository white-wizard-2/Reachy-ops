"""Poll Reachy Mini daemon ``/api/state/full`` and notify the UI hub."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Final

import httpx

# ``with_doa`` / passive / full target matrices have triggered HTTP 500 on some daemon builds.
# Try a small set first (enough for ``RobotStatePanel``), then strip further, then bare GET.
_STATE_FULL_QUERY_TRIES: Final[tuple[dict[str, str], ...]] = (
    {
        "with_control_mode": "true",
        "with_head_pose": "true",
        "with_head_joints": "true",
        "with_body_yaw": "true",
        "with_antenna_positions": "true",
        "use_pose_matrix": "false",
    },
    {
        "with_control_mode": "true",
        "with_head_pose": "true",
        "with_head_joints": "true",
        "with_body_yaw": "true",
    },
    {},
)


class RobotStateHub:
    """HTTP poll against the robot daemon; push snapshots via ``on_update``."""

    POLL_INTERVAL_S = 10.0

    def __init__(
        self,
        get_state_full_url: Callable[[], str | None],
        on_update: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        self._get_state_full_url = get_state_full_url
        self._on_update = on_update
        self._lock = asyncio.Lock()
        self.data: dict[str, Any] | None = None
        self.error: str | None = None
        self.fetched_at: str | None = None

    def public_message(self) -> dict[str, Any]:
        return {
            "type": "robot_state",
            "data": self.data,
            "error": self.error,
            "fetched_at": self.fetched_at,
        }

    async def poll_once(self, client: httpx.AsyncClient) -> None:
        url = self._get_state_full_url()
        if url is None:
            async with self._lock:
                self.error = "robot_not_connected"
                self.fetched_at = datetime.now(timezone.utc).isoformat()
            await self._on_update(self.public_message())
            return

        new_data: dict[str, Any] | None = None
        err: str | None = None
        for params in _STATE_FULL_QUERY_TRIES:
            try:
                r = await client.get(url, params=params, timeout=8.0)
                r.raise_for_status()
                new_data = r.json()
                err = None
                break
            except Exception as e:  # noqa: BLE001
                err = f"{type(e).__name__}: {e}"

        async with self._lock:
            if new_data is not None:
                self.data = new_data
                self.error = None
            else:
                self.error = err
            self.fetched_at = datetime.now(timezone.utc).isoformat()

        await self._on_update(self.public_message())


async def robot_state_poll_loop(hub: RobotStateHub) -> None:
    """Poll daemon every ``POLL_INTERVAL_S``; cancel the task to stop."""
    async with httpx.AsyncClient() as client:
        while True:
            await hub.poll_once(client)
            await asyncio.sleep(hub.POLL_INTERVAL_S)
