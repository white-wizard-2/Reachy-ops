import pytest

from robot_manage.voice_command_parser import try_parse_voice_command


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Please activate sentry mode", ("activate", "mode", "Sentry Mode")),
        ("Deactivate teacher mode", ("deactivate", "mode", "Teacher Mode")),
        ("activate mute mode", ("activate", "mode", "Silent Mode")),
        ("ACTIVATE VISION now", ("activate", "tool", "Vision")),
        ("We should deactivate audio", ("deactivate", "tool", "Voice")),
    ],
)
def test_parse_voice_command_hits(
    text: str,
    expected: tuple[str, str, str],
) -> None:
    p = try_parse_voice_command(text)
    assert p == expected


def test_parse_no_keyword() -> None:
    assert try_parse_voice_command("Turn on sentry mode") is None


def test_parse_unknown_target() -> None:
    assert try_parse_voice_command("activate turbo mode") is None


def test_parse_last_mentioned_mode_wins() -> None:
    p = try_parse_voice_command("activate sentry mode and also activate teacher mode")
    assert p is not None
    assert p[1] == "mode"
    assert p[2] == "Teacher Mode"
