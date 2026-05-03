import pytest

from robot_manage.move_catalog import (
    VoiceAssistantJsonError,
    move_instruction_appendix,
    parse_voice_assistant_json,
    validated_move,
)


def test_validated_move_emotion() -> None:
    p = validated_move("emotions", "cheerful1")
    assert p is not None
    assert p[1] == "cheerful1"


def test_validated_move_dance() -> None:
    p = validated_move("dances", "simple_nod")
    assert p is not None


def test_validated_move_invalid() -> None:
    assert validated_move("emotions", "not_a_real_move") is None


def test_parse_json_object_move() -> None:
    raw = '{"speech": "Hello there.", "move": {"library": "emotions", "id": "cheerful1"}}'
    pair, speech, hist = parse_voice_assistant_json(raw)
    assert pair is not None
    assert speech == "Hello there."
    assert '"speech": "Hello there."' in hist
    assert "cheerful1" in hist


def test_parse_json_string_move() -> None:
    raw = '{"speech":"Nod.", "move": "dances/simple_nod"}'
    pair, speech, hist = parse_voice_assistant_json(raw)
    assert pair is not None
    assert speech == "Nod."
    assert "simple_nod" in hist


def test_parse_json_null_move() -> None:
    raw = '{"speech": "Only voice.", "move": null}'
    pair, speech, hist = parse_voice_assistant_json(raw)
    assert pair is None
    assert speech == "Only voice."
    assert '"move": null' in hist


def test_parse_json_omitted_move() -> None:
    raw = '{"speech": "Hi"}'
    pair, speech, _hist = parse_voice_assistant_json(raw)
    assert pair is None
    assert speech == "Hi"


def test_parse_json_fenced() -> None:
    raw = '```json\n{"speech":"X","move":null}\n```'
    pair, speech, _hist = parse_voice_assistant_json(raw)
    assert pair is None
    assert speech == "X"


def test_parse_invalid_json_raises() -> None:
    with pytest.raises(VoiceAssistantJsonError):
        parse_voice_assistant_json("not json")


def test_parse_unknown_move_keeps_speech() -> None:
    pair, speech, hist = parse_voice_assistant_json(
        '{"speech":"Glad to hear it!","move":{"library":"emotions","id":"friendly1"}}',
    )
    assert pair is None
    assert speech == "Glad to hear it!"
    assert '"move": null' in hist


def test_parse_extra_trailing_brace_after_object() -> None:
    raw = '{"move": {"library": "emotions", "id": "proud1"}, "speech": "Glad to hear it!"}}'
    pair, speech, hist = parse_voice_assistant_json(raw)
    assert pair is not None
    assert speech == "Glad to hear it!"
    assert "proud1" in hist


def test_voice_prompt_lists_real_ids() -> None:
    ap = move_instruction_appendix()
    assert "welcoming1" in ap
    assert "cheerful1" in ap
    assert "friendly_greeting" not in ap
    assert "move MUST be non-null" in ap
    assert "How are you doing today?" in ap
