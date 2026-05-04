"""Reachy Mini daemon ``/api/volume`` helpers (host-side HTTP to the robot)."""

from __future__ import annotations

from typing import Any

import httpx


def _daemon_base(mini: Any) -> str:
    return f"http://{mini.client.host}:{mini.client.port}"


async def prime_daemon_audio_levels(client: httpx.AsyncClient, mini: Any, mic_state: dict[str, Any]) -> None:
    """GET current speaker + mic input volume from daemon into ``mic_state``."""

    base = _daemon_base(mini)
    try:
        r = await client.get(f"{base}/api/volume/current", timeout=4.0)
        if r.is_success:
            j = r.json()
            mic_state["daemon_speaker_volume"] = int(j["volume"])
    except Exception:
        pass
    try:
        r2 = await client.get(f"{base}/api/volume/microphone/current", timeout=4.0)
        if r2.is_success:
            j2 = r2.json()
            mic_state["daemon_mic_input_volume"] = int(j2["volume"])
    except Exception:
        pass


async def apply_daemon_audio_levels(
    client: httpx.AsyncClient,
    mini: Any,
    mic_state: dict[str, Any],
    *,
    mic_input_volume: int | None = None,
    speaker_volume: int | None = None,
) -> None:
    """POST volume changes; updates ``mic_state`` on success."""

    base = _daemon_base(mini)
    if mic_input_volume is not None:
        v = max(0, min(100, int(mic_input_volume)))
        r = await client.post(f"{base}/api/volume/microphone/set", json={"volume": v}, timeout=6.0)
        r.raise_for_status()
        mic_state["daemon_mic_input_volume"] = v
    if speaker_volume is not None:
        v = max(0, min(100, int(speaker_volume)))
        r = await client.post(f"{base}/api/volume/set", json={"volume": v}, timeout=6.0)
        r.raise_for_status()
        mic_state["daemon_speaker_volume"] = v
