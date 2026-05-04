"""Reachy Mini recorded-move IDs (HF emotions + dances libraries)."""

from __future__ import annotations

import json
from typing import Final

REACHY_EMOTIONS_DATASET: Final = "pollen-robotics/reachy-mini-emotions-library"
REACHY_DANCES_DATASET: Final = "pollen-robotics/reachy-mini-dances-library"

_EMOTION_NAMES: Final[frozenset[str]] = frozenset(
    {
        "amazed1",
        "anxiety1",
        "attentive1",
        "attentive2",
        "boredom1",
        "boredom2",
        "calming1",
        "cheerful1",
        "come1",
        "confused1",
        "contempt1",
        "curious1",
        "dance1",
        "dance2",
        "dance3",
        "disgusted1",
        "displeased1",
        "displeased2",
        "downcast1",
        "dying1",
        "electric1",
        "enthusiastic1",
        "enthusiastic2",
        "exhausted1",
        "fear1",
        "frustrated1",
        "furious1",
        "go_away1",
        "grateful1",
        "helpful1",
        "helpful2",
        "impatient1",
        "impatient2",
        "incomprehensible2",
        "indifferent1",
        "inquiring1",
        "inquiring2",
        "inquiring3",
        "irritated1",
        "irritated2",
        "laughing1",
        "laughing2",
        "lonely1",
        "lost1",
        "loving1",
        "no1",
        "no_excited1",
        "no_sad1",
        "oops1",
        "oops2",
        "proud1",
        "proud2",
        "proud3",
        "rage1",
        "relief1",
        "relief2",
        "reprimand1",
        "reprimand2",
        "reprimand3",
        "resigned1",
        "sad1",
        "sad2",
        "scared1",
        "serenity1",
        "shy1",
        "sleep1",
        "success1",
        "success2",
        "surprised1",
        "surprised2",
        "thoughtful1",
        "thoughtful2",
        "tired1",
        "uncertain1",
        "uncomfortable1",
        "understanding1",
        "understanding2",
        "welcoming1",
        "welcoming2",
        "yes1",
        "yes_sad1",
    }
)

_DANCE_NAMES: Final[frozenset[str]] = frozenset(
    {
        "chicken_peck",
        "chin_lead",
        "dizzy_spin",
        "grid_snap",
        "groovy_sway_and_roll",
        "head_tilt_roll",
        "interwoven_spirals",
        "jackson_square",
        "neck_recoil",
        "pendulum_swing",
        "polyrhythm_combo",
        "sharp_side_tilt",
        "side_glance_flick",
        "side_peekaboo",
        "side_to_side_sway",
        "simple_nod",
        "stumble_and_recover",
        "uh_huh_tilt",
        "yeah_nod",
    }
)


def _comma_separated_wrapped(names: frozenset[str], *, max_line: int = 118) -> str:
    """Join sorted ids with commas; start a new line before exceeding ``max_line`` characters."""

    parts = sorted(names)
    if not parts:
        return ""
    lines: list[str] = []
    cur: list[str] = []
    cur_len = 0
    for p in parts:
        piece = p if not cur else ", " + p
        if cur and cur_len + len(piece) > max_line:
            lines.append("".join(cur))
            cur = [p]
            cur_len = len(p)
        else:
            cur.append(piece)
            cur_len += len(piece)
    if cur:
        lines.append("".join(cur))
    return "\n".join(lines)


def move_id_catalog_reference() -> str:
    """Exact allowlisted ids for the voice system prompt (models must not invent new ids)."""

    return (
        "Emotion ids (use move.library \"emotions\" and move.id exactly one of):\n"
        f"{_comma_separated_wrapped(_EMOTION_NAMES)}\n\n"
        "Dance ids (use move.library \"dances\" and move.id exactly one of):\n"
        f"{_comma_separated_wrapped(_DANCE_NAMES)}"
    )


def dataset_for_kind(kind: str) -> str:
    k = kind.lower()
    if k == "emotions":
        return REACHY_EMOTIONS_DATASET
    if k == "dances":
        return REACHY_DANCES_DATASET
    raise ValueError(kind)


def validated_move(kind: str, name: str) -> tuple[str, str] | None:
    """Return ``(hf_dataset_id, move_name)`` if valid."""

    k = kind.lower()
    n = name.strip()
    if k == "emotions" and n in _EMOTION_NAMES:
        return REACHY_EMOTIONS_DATASET, n
    if k == "dances" and n in _DANCE_NAMES:
        return REACHY_DANCES_DATASET, n
    return None


class VoiceAssistantJsonError(ValueError):
    """Assistant reply was not valid JSON in the voice envelope schema."""


def _unwrap_json_fenced(raw: str) -> str:
    t = (raw or "").strip()
    if not t.startswith("```"):
        return t
    lines = t.split("\n")
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    while lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _parse_move_field(move_part: object) -> tuple[str, str] | None:
    if move_part is None:
        return None
    if isinstance(move_part, str):
        s = move_part.strip()
        if not s:
            raise VoiceAssistantJsonError("move string must be non-empty library/id")
        if "/" not in s:
            raise VoiceAssistantJsonError('move string must look like "emotions/cheerful1"')
        lib, _, mid = s.partition("/")
        pair = validated_move(lib.strip(), mid.strip())
        if not pair:
            raise VoiceAssistantJsonError(f"unknown move: {s!r}")
        return pair
    if isinstance(move_part, dict):
        lib = move_part.get("library")
        mid = move_part.get("id")
        if not isinstance(lib, str) or not isinstance(mid, str):
            raise VoiceAssistantJsonError("move.library and move.id must be strings")
        pair = validated_move(lib.strip(), mid.strip())
        if not pair:
            raise VoiceAssistantJsonError(f"unknown move: {lib!r}/{mid!r}")
        return pair
    raise VoiceAssistantJsonError("move must be null, an object, or a library/id string")


def parse_voice_assistant_json(full_text: str) -> tuple[tuple[str, str] | None, str, str]:
    """Parse the voice LLM envelope: ``(hf_move_pair|None, speech, assistant_message_for_history)``."""

    text = _unwrap_json_fenced(full_text)
    if not text:
        raise VoiceAssistantJsonError("empty assistant response")
    obj: object
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as e:
        try:
            obj, _end = json.JSONDecoder().raw_decode(text.strip())
        except json.JSONDecodeError:
            raise VoiceAssistantJsonError(f"invalid JSON: {e}") from e
    if not isinstance(obj, dict):
        raise VoiceAssistantJsonError("JSON root must be an object")
    speech = obj.get("speech")
    if not isinstance(speech, str):
        raise VoiceAssistantJsonError("speech must be a string")
    try:
        pair = _parse_move_field(obj.get("move"))
    except VoiceAssistantJsonError:
        pair = None
    if pair is not None:
        lib = "emotions" if pair[0] == REACHY_EMOTIONS_DATASET else "dances"
        canonical_move: dict[str, str] | None = {"library": lib, "id": pair[1]}
    else:
        canonical_move = None
    assistant_content = json.dumps(
        {"move": canonical_move, "speech": speech},
        ensure_ascii=False,
    )
    return pair, speech, assistant_content


def parse_voice_assistant_output(full_text: str) -> tuple[tuple[str, str] | None, str, str]:
    """Parse assistant output for the MLX voice pipeline.

    Default (``OLLAMA_VOICE_JSON_MOVES`` off): plain text — the whole reply is spoken and stored in history.
    If the model still returns a JSON object with a ``speech`` field, only ``speech`` is used; moves are ignored
    so playback is not tied to ``play_move`` during TTS.

    Legacy (``OLLAMA_VOICE_JSON_MOVES=1``): same as :func:`parse_voice_assistant_json`.
    """

    from robot_manage.settings import ollama_voice_json_moves_enabled

    if ollama_voice_json_moves_enabled():
        return parse_voice_assistant_json(full_text)

    t = _unwrap_json_fenced(full_text).strip()
    if not t:
        raise VoiceAssistantJsonError("empty assistant response")
    if t.startswith("{") and t.endswith("}"):
        try:
            obj = json.loads(t)
        except json.JSONDecodeError as e:
            raise VoiceAssistantJsonError(f"invalid JSON in plain-text mode: {e}") from e
        if isinstance(obj, dict):
            sp = obj.get("speech")
            if isinstance(sp, str):
                speech = sp.strip()
                if not speech:
                    raise VoiceAssistantJsonError("speech must be a non-empty string")
                return None, speech, speech
        raise VoiceAssistantJsonError(
            "Plain-text mode is on, but the reply looks like JSON without a usable speech string. "
            "Reply in natural language only, or set OLLAMA_VOICE_JSON_MOVES=1 for JSON+move mode."
        )
    return None, t, t


def _move_instruction_few_shots() -> str:
    """Compact valid JSON lines so the model sees non-null moves as the default."""

    return (
        "Valid reply shapes (each line is one complete JSON object; ids must appear in the catalog above):\n"
        '{"speech":"Hey! How are you doing today?","move":{"library":"emotions","id":"welcoming1"}}\n'
        '{"speech":"Hi again—what is on your mind?","move":{"library":"emotions","id":"welcoming2"}}\n'
        '{"speech":"That is great news.","move":{"library":"emotions","id":"enthusiastic1"}}\n'
        '{"speech":"Thanks, I appreciate it.","move":{"library":"emotions","id":"grateful1"}}\n'
        '{"speech":"Right, channel twelve point three.","move":null}'
    )


def move_instruction_appendix() -> str:
    """Extra system text: assistant replies are JSON only (speech + optional move)."""

    cat = move_id_catalog_reference()
    few = _move_instruction_few_shots()
    return (
        "Reply with exactly one JSON object — no markdown fences, no commentary, no text outside the object; "
        "do not append an extra closing brace after the object ends. "
        'Schema: {"speech": string, "move": null | {"library": "emotions"|"dances", "id": string} | '
        '"emotions/<id>" string}. '
        "speech is read aloud by TTS; nothing else is spoken. "
        "move drives a recorded body motion from Pollen's libraries "
        f"({REACHY_EMOTIONS_DATASET} or {REACHY_DANCES_DATASET}). "
        "Embodiment rule: if speech is social, emotional, curious, playful, thankful, encouraging, or a greeting, "
        "move MUST be non-null and chosen from the catalog. "
        "move:null is ONLY for sterile readouts (codes, numbers per line, no conversational tone) or when the user "
        "explicitly asked for stillness. "
        "move.id MUST be copied verbatim from the catalog — do not invent or rename ids.\n\n"
        f"{cat}\n\n"
        f"{few}"
    )
