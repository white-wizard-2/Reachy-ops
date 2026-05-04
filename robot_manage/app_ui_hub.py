"""Fan-out JSON messages to all connected ``/ws/app`` UI WebSocket clients."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import WebSocket

_VOICE_BROADCAST_EVENTS = frozenset({"modes_tools", "conversation", "error"})


class AppUiHub:
    """Broadcast telemetry and selected voice events to every connected browser tab."""

    def __init__(self) -> None:
        self._connections: list[WebSocket] = []
        self._lock = asyncio.Lock()

    def n_connections(self) -> int:
        return len(self._connections)

    async def register(self, ws: WebSocket) -> None:
        async with self._lock:
            self._connections.append(ws)

    async def unregister(self, ws: WebSocket) -> None:
        async with self._lock:
            try:
                self._connections.remove(ws)
            except ValueError:
                pass

    async def broadcast_json(self, obj: dict[str, Any]) -> None:
        async with self._lock:
            if not self._connections:
                return
            targets = list(self._connections)
        dead: list[WebSocket] = []
        for ws in targets:
            try:
                await ws.send_json(obj)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.unregister(ws)

    async def voice_notify(self, ev: dict[str, Any]) -> None:
        """Forward high-level voice state to all tabs (not per-token streaming)."""
        if ev.get("event") not in _VOICE_BROADCAST_EVENTS:
            return
        await self.broadcast_json({"type": "voice", **ev})
