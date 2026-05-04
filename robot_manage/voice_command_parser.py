"""Parse spoken phrases for ``activate`` / ``deactivate`` + mode or tool name."""

from __future__ import annotations

import re
from typing import Final, Literal

Action = Literal["activate", "deactivate"]
Kind = Literal["mode", "tool"]

# (lowercase substring to find in normalized text, canonical display label)
_MODE_ALIASES: Final[tuple[tuple[str, str], ...]] = (
    ("teacher mode", "Teacher Mode"),
    ("sentry mode", "Sentry Mode"),
    ("silent mode", "Silent Mode"),
    ("guardian mode", "Guardian Mode"),
    ("mute mode", "Mute Mode"),
    ("teacher", "Teacher Mode"),
    ("sentry", "Sentry Mode"),
    ("silent", "Silent Mode"),
    ("guardian", "Guardian Mode"),
    ("mute", "Mute Mode"),
)

_TOOL_ALIASES: Final[tuple[tuple[str, str], ...]] = (
    ("thinking", "Thinking"),
    ("internet", "Internet"),
    ("actions", "Actions"),
    ("vision", "Vision"),
    ("audio", "Audio"),
)

MODE_LABELS: Final[frozenset[str]] = frozenset({label for _, label in _MODE_ALIASES})
TOOL_LABELS: Final[frozenset[str]] = frozenset({label for _, label in _TOOL_ALIASES})

_ACTIVATE_RE: Final[re.Pattern[str]] = re.compile(r"\bactivate\b", re.IGNORECASE)
_DEACTIVATE_RE: Final[re.Pattern[str]] = re.compile(r"\bdeactivate\b", re.IGNORECASE)


def _label_rightmost_end(t: str, aliases: tuple[tuple[str, str], ...]) -> dict[str, int]:
    """For each canonical label, the greatest end index of any matching alias in *t* (or absent)."""

    ends: dict[str, int] = {}
    for needle, label in aliases:
        start = 0
        while True:
            i = t.find(needle, start)
            if i < 0:
                break
            end = i + len(needle)
            ends[label] = max(ends.get(label, -1), end)
            start = i + 1
    return ends


def _pick_label(ends: dict[str, int]) -> str | None:
    """Label with the largest rightmost end (only one mode/tool should win per utterance)."""

    if not ends:
        return None
    return max(ends.items(), key=lambda kv: kv[1])[0]


def try_parse_voice_command(text: str) -> tuple[Action, Kind, str] | None:
    """If *text* contains activate/deactivate and a known mode or tool, return ``(action, kind, label)``."""

    raw = (text or "").strip()
    if not raw:
        return None
    t = re.sub(r"\s+", " ", raw.lower())
    if _ACTIVATE_RE.search(t):
        action: Action = "activate"
    elif _DEACTIVATE_RE.search(t):
        action = "deactivate"
    else:
        return None

    mode_ends = _label_rightmost_end(t, _MODE_ALIASES)
    tool_ends = _label_rightmost_end(t, _TOOL_ALIASES)
    mode_label = _pick_label(mode_ends)
    tool_label = _pick_label(tool_ends)
    if mode_label is None and tool_label is None:
        return None
    if mode_label is not None and tool_label is None:
        return action, "mode", mode_label
    if mode_label is None and tool_label is not None:
        return action, "tool", tool_label
    assert mode_label is not None and tool_label is not None
    mode_end = mode_ends[mode_label]
    tool_end = tool_ends[tool_label]
    if mode_end >= tool_end:
        return action, "mode", mode_label
    return action, "tool", tool_label


def format_command_speech(action: Action, kind: Kind, label: str) -> str:
    """Short phrase for macOS ``say`` after a voice command is applied."""

    v = "Activating" if action == "activate" else "Deactivating"
    return f"{v} {label}."
