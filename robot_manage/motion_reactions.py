"""Pick lightweight reaction moves during TTS.

This mirrors the *spirit* of `reachy_mini_conversation_app`: motion is not embedded
in the spoken text, and it should not interfere with audio playback.

We keep this deterministic (no randomness) so behavior is predictable.
"""

from __future__ import annotations

from robot_manage.move_catalog import validated_move


def select_reaction_move_for_speech(speech: str) -> tuple[str, str] | None:
    """Return ``(hf_dataset_id, move_name)`` for a short reaction move, or None."""

    t = (speech or "").strip().lower()
    if not t:
        return None

    # Greetings
    if any(w in t for w in ("hello", "hi", "hey", "good morning", "good afternoon", "good evening")):
        return validated_move("emotions", "welcoming1")

    # Thanks / appreciation
    if any(w in t for w in ("thank", "thanks", "appreciate")):
        return validated_move("emotions", "grateful1")

    # Questions / curiosity
    if "?" in t or any(w in t for w in ("curious", "wonder", "let's see", "hmm")):
        return validated_move("emotions", "inquiring1")

    # Positive / excitement
    if any(w in t for w in ("great", "awesome", "amazing", "nice", "love", "perfect", "good news", "fantastic")):
        return validated_move("emotions", "enthusiastic1")

    # Default gentle attentive posture (very short, not a dance)
    return validated_move("emotions", "attentive1")

