"""One-shot sentry camera pan + vision LLM scene check (Sentry Mode)."""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from robot_manage.ollama_voice import complete_vision_chat
from robot_manage.reachy_llm_tools import _encode_camera_jpeg_b64, _grab_frame
from robot_manage.voice_modes import sentry_pan_fov_u, sentry_pan_overlap_fraction

_LOG = logging.getLogger(__name__)

_SENTRY_VISION_SYSTEM = (
    "You analyze a single robot camera frame for a security-style sweep. "
    "Reply with exactly two lines and nothing else:\n"
    "Line 1: one short objective sentence describing what is visible (no poetry).\n"
    "Line 2: exactly `RISK: low` or exactly `RISK: high`. Use high only for clear danger or strong "
    "suspicion (weapons pointed at people, visible serious injury, active fire or heavy smoke, "
    "obvious break-in in progress, overt threatening behavior toward people, or other imminent harm). "
    "If uncertain, use low."
)


def _risk_line_is_high(text: str) -> bool:
    for line in text.splitlines():
        s = line.strip()
        if re.match(r"^RISK:\s*high\s*$", s, re.IGNORECASE):
            return True
    return False


def _first_nonrisk_line(text: str) -> str:
    for line in text.splitlines():
        s = line.strip()
        if not s or re.match(r"^RISK:\s*", s, re.IGNORECASE):
            continue
        return s
    return ""


def sentry_u_centers(
    *,
    span_start: float = 0.04,
    span_end: float = 0.96,
    fov_horizontal: float | None = None,
    overlap_fraction: float | None = None,
) -> list[float]:
    """Normalized horizontal image coordinates for ``look_at_image`` centers (left → right)."""

    fov = float(sentry_pan_fov_u() if fov_horizontal is None else fov_horizontal)
    ov = float(sentry_pan_overlap_fraction() if overlap_fraction is None else overlap_fraction)
    if not (0.0 < ov < 1.0):
        raise ValueError("overlap_fraction must be between 0 and 1")
    if fov <= 0.0:
        raise ValueError("fov_horizontal must be positive")
    step = fov * (1.0 - ov)
    out: list[float] = []
    u = float(span_start)
    while u <= span_end + 1e-9:
        out.append(min(u, span_end))
        u += step
    if not out:
        return [0.5]
    if out[-1] < span_end - 1e-4:
        out.append(float(span_end))
    # de-dupe nearly-equal
    deduped: list[float] = []
    for x in out:
        if not deduped or abs(x - deduped[-1]) > 1e-4:
            deduped.append(x)
    return deduped


async def run_sentry_patrol(
    mini: Any,
    client: httpx.AsyncClient,
    *,
    base_url: str,
    model: str,
    should_stop: Callable[[], bool],
    speak_alert: Callable[[str], Awaitable[None]],
) -> None:
    """Neutral pose, pan across the field of view, vision LLM per stop; optional spoken alert."""

    def _neutral() -> None:
        mini.look_at_image(0.5, 0.5, duration=1.15, perform_movement=True)

    try:
        await asyncio.to_thread(_neutral)
    except Exception as e:  # noqa: BLE001
        _LOG.warning("sentry neutral look: %s", e)
    await asyncio.sleep(0.45)
    if should_stop():
        return

    v = 0.48
    for u in sentry_u_centers():
        if should_stop():
            return
        try:

            def _look() -> None:
                mini.look_at_image(float(u), float(v), duration=0.95, perform_movement=True)

            await asyncio.to_thread(_look)
        except Exception as e:  # noqa: BLE001
            _LOG.warning("sentry look_at_image u=%s: %s", u, e)
            continue
        await asyncio.sleep(0.4)
        if should_stop():
            return

        frame = await asyncio.to_thread(_grab_frame, mini)
        if frame is None:
            _LOG.warning("sentry: no frame at u=%s", u)
            continue
        try:
            b64 = await asyncio.to_thread(_encode_camera_jpeg_b64, frame)
        except Exception as e:  # noqa: BLE001
            _LOG.warning("sentry encode: %s", e)
            continue

        user = (
            f"This is sentry sweep view {u:.2f} (horizontal gaze in normalized image coordinates). "
            "Follow the two-line format from your instructions."
        )
        try:
            raw = (
                await complete_vision_chat(
                    client,
                    base_url,
                    model,
                    system=_SENTRY_VISION_SYSTEM,
                    user=user,
                    images=[b64],
                )
            ).strip()
        except Exception as e:  # noqa: BLE001
            _LOG.warning("sentry vision LLM: %s", e)
            continue

        if _risk_line_is_high(raw):
            desc = _first_nonrisk_line(raw) or "Possible risk in view."
            alert = f"Sentry alert. {desc}"
            try:
                await speak_alert(alert[:500])
            except Exception as e:  # noqa: BLE001
                _LOG.warning("sentry speak_alert: %s", e)
