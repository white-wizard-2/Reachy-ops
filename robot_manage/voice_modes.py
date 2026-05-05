"""Canonical voice operating modes (UI + spoken commands + system prompt)."""

from __future__ import annotations

import os
from typing import Final

from robot_manage.settings import ollama_voice_text_system_prompt

MODE_SENTRY: Final[str] = "Sentry Mode"
MODE_SILENT: Final[str] = "Silent Mode"
MODE_TEACHER: Final[str] = "Teacher Mode"

CANONICAL_MODE_LABELS: Final[frozenset[str]] = frozenset({MODE_SENTRY, MODE_SILENT, MODE_TEACHER})

_TEACHER_APPEND = (
    "\n\nTeacher session: respond in character as **Kaira**, a warm patient mentor for children "
    "(roughly ages 5–12) who are talking through this robot. Use clear simple language, encourage "
    "curiosity, never talk down, and avoid unsafe instructions. Keep replies concise."
)

_SILENT_APPEND = (
    "\n\nSilent session: the device will not read your answers aloud. Write complete replies for "
    "on-screen reading only; do not rely on the user hearing audio."
)

_SENTRY_APPEND = (
    "\n\nSentry session: a background camera sweep may be running; keep normal voice replies brief "
    "and factual when the user speaks."
)


def full_voice_system_prompt(active_mode: str | None) -> str:
    """Full Ollama system text for the MLX voice stack (base persona + mode rules)."""

    base = ollama_voice_text_system_prompt().strip()
    if active_mode == MODE_TEACHER:
        return base + _TEACHER_APPEND
    if active_mode == MODE_SILENT:
        return base + _SILENT_APPEND
    if active_mode == MODE_SENTRY:
        return base + _SENTRY_APPEND
    return base


def is_silent_mode(active_mode: str | None) -> bool:
    return active_mode == MODE_SILENT


def sentry_pan_fov_u() -> float:
    return float(os.environ.get("ROBOT_MANAGE_SENTRY_FOV_U", "0.28"))


def sentry_pan_overlap_fraction() -> float:
    """Horizontal overlap between consecutive sentry views (0–1), default ``0.1`` (10%)."""

    return float(os.environ.get("ROBOT_MANAGE_SENTRY_OVERLAP", "0.1"))
