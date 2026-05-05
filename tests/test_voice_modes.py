from robot_manage.voice_modes import (
    MODE_SILENT,
    MODE_TEACHER,
    full_voice_system_prompt,
    is_silent_mode,
)


def test_is_silent_mode() -> None:
    assert is_silent_mode(MODE_SILENT)
    assert not is_silent_mode(MODE_TEACHER)
    assert not is_silent_mode(None)


def test_full_voice_system_prompt_teacher_contains_kaira() -> None:
    t = full_voice_system_prompt(MODE_TEACHER)
    assert "Kaira" in t
