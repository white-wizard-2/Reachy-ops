"""Move catalog for the ops UI (no network; ids are allowlisted in code)."""

from __future__ import annotations

from typing import Any

from robot_manage.move_catalog import dance_ids, emotion_ids


def _emoji_for_emotion(mid: str) -> str:
    m = mid.lower()
    if "laugh" in m:
        return "😂"
    if "cheer" in m or "enthusiastic" in m or "welcoming" in m or "grateful" in m:
        return "😄"
    if "loving" in m:
        return "🥰"
    if m.startswith("yes"):
        return "👍"
    if m.startswith("no") or "go_away" in m:
        return "👎"
    if "sad" in m or "downcast" in m or "lonely" in m:
        return "😢"
    if "fear" in m or "scared" in m:
        return "😱"
    if "furious" in m or m.startswith("rage") or "frustrated" in m or "irritated" in m:
        return "😡"
    if "disgust" in m:
        return "🤢"
    if "confus" in m or "incomprehensible" in m:
        return "🤔"
    if "amazed" in m or "surpris" in m or "oops" in m:
        return "😮"
    if "tired" in m or "exhausted" in m:
        return "🥱"
    if "sleep" in m:
        return "😴"
    if "serenity" in m or "calming" in m or "relief" in m:
        return "😌"
    if "shy" in m:
        return "☺️"
    if "proud" in m or "success" in m:
        return "🏆"
    if "helpful" in m or "understanding" in m:
        return "🤝"
    if "curious" in m or "inquiring" in m or "thoughtful" in m:
        return "🧐"
    if "attentive" in m:
        return "👀"
    if "boredom" in m or "indifferent" in m:
        return "😐"
    return "🎭"


def _emoji_for_dance(mid: str) -> str:
    m = mid.lower()
    if "spin" in m or "dizzy" in m:
        return "🌀"
    if "nod" in m or "uh_huh" in m:
        return "🙆"
    if "peekaboo" in m or "glance" in m:
        return "🙈"
    if "sway" in m or "pendulum" in m:
        return "🌊"
    if "chicken" in m:
        return "🐔"
    return "🕺"


def ui_move_catalog() -> dict[str, Any]:
    """Snapshot payload for the UI emoji move picker."""

    emotions = [{"library": "emotions", "id": mid, "emoji": _emoji_for_emotion(mid)} for mid in emotion_ids()]
    dances = [{"library": "dances", "id": mid, "emoji": _emoji_for_dance(mid)} for mid in dance_ids()]
    return {"emotions": emotions, "dances": dances}

