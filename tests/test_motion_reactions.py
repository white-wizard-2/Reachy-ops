from robot_manage.motion_reactions import select_reaction_move_for_speech


def test_select_reaction_move_greeting() -> None:
    m = select_reaction_move_for_speech("Hello there!")
    assert m is not None
    assert m[1] == "welcoming1"


def test_select_reaction_move_thanks() -> None:
    m = select_reaction_move_for_speech("Thanks, that's helpful.")
    assert m is not None
    assert m[1] == "grateful1"


def test_select_reaction_move_question() -> None:
    m = select_reaction_move_for_speech("What can you do?")
    assert m is not None
    assert m[1] == "inquiring1"


def test_select_reaction_move_positive() -> None:
    m = select_reaction_move_for_speech("That is great news.")
    assert m is not None
    assert m[1] == "enthusiastic1"


def test_select_reaction_move_default_attentive() -> None:
    m = select_reaction_move_for_speech("Let's proceed step by step.")
    assert m is not None
    assert m[1] == "attentive1"

