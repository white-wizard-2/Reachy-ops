"""Ensure the Reachy Mini *robot backend* is running before opening the SDK WebSocket.

The daemon HTTP server can be up while ``/api/daemon/status`` reports ``state: stopped``.
In that case ``/ws/sdk`` accepts connections but sends no joint/pose traffic, and
``ReachyMini`` times out in ``wait_for_connection``.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Literal

import httpx

logger = logging.getLogger(__name__)

DaemonStateClass = Literal["running", "stopped", "other"]


def classify_daemon_state(status: dict[str, Any]) -> DaemonStateClass:
    s = status.get("state")
    if s == "running":
        return "running"
    if s == "stopped":
        return "stopped"
    return "other"


async def ensure_reachy_mini_daemon_backend_running(
    host: str,
    port: int,
    *,
    wake_up: bool = True,
    poll_interval_s: float = 0.5,
    start_timeout_s: float = 120.0,
    client: httpx.AsyncClient | None = None,
) -> None:
    """If the HTTP daemon reports ``stopped``, call ``POST /api/daemon/start`` and poll until ``running``."""
    close_client = False
    if client is None:
        base = f"http://{host}:{port}"
        timeout = httpx.Timeout(start_timeout_s + 30.0, connect=10.0)
        client = httpx.AsyncClient(base_url=base, timeout=timeout)
        close_client = True
    try:
        try:
            r = await client.get("/api/daemon/status")
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise ConnectionError(
                f"Could not read Reachy Mini daemon status at {host}:{port}: {e}"
            ) from e

        st = r.json()
        kind = classify_daemon_state(st)
        if kind == "running":
            return
        if kind != "stopped":
            err = st.get("error")
            raise ConnectionError(
                f"Reachy Mini daemon at {host}:{port} is not ready (state={st.get('state')!r}, error={err!r}). "
                "Check the Reachy Mini app or daemon logs."
            )
        try:
            start_r = await client.post("/api/daemon/start", params={"wake_up": wake_up})
            start_r.raise_for_status()
        except httpx.HTTPError as e:
            raise ConnectionError(
                f"Reachy Mini daemon at {host}:{port} is stopped and could not be started: {e}"
            ) from e

        logger.info("Reachy Mini daemon was stopped; start requested (wake_up=%s). Waiting…", wake_up)
        deadline = time.monotonic() + start_timeout_s
        while time.monotonic() < deadline:
            try:
                r2 = await client.get("/api/daemon/status")
                r2.raise_for_status()
            except httpx.HTTPError as e:
                raise ConnectionError(f"Lost contact with Reachy Mini daemon at {host}:{port}: {e}") from e
            if classify_daemon_state(r2.json()) == "running":
                return
            await asyncio.sleep(poll_interval_s)

        raise ConnectionError(
            f"Timed out after {start_timeout_s:.0f}s waiting for Reachy Mini daemon to start at {host}:{port}."
        )
    finally:
        if close_client:
            await client.aclose()
