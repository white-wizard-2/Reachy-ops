import asyncio

import pytest

from robot_manage.llm_say import LlmSayRunner, pull_complete_sentences


def test_pull_empty() -> None:
    assert pull_complete_sentences("") == ([], "")


def test_pull_one_sentence_with_trailing_space() -> None:
    s, r = pull_complete_sentences("Hello world. ")
    assert s == ["Hello world."]
    assert r == ""


def test_pull_two_sentences() -> None:
    s, r = pull_complete_sentences('First. Second! ')
    assert s == ["First.", "Second!"]
    assert r == ""


def test_pull_incomplete_no_trailing_ws() -> None:
    s, r = pull_complete_sentences("Hello.")
    assert s == []
    assert r == "Hello."


def test_pull_decimal_not_split_early() -> None:
    s, r = pull_complete_sentences("Pi is 3.14 today. ")
    assert s == ["Pi is 3.14 today."]
    assert r == ""


def test_pull_optional_quote_then_space() -> None:
    s, r = pull_complete_sentences('She said "stop." now ')
    assert s == ['She said "stop."']
    assert r == "now "


def test_pull_remainder_after_complete() -> None:
    s, r = pull_complete_sentences("Done. Tail")
    assert s == ["Done."]
    assert r == "Tail"


def test_llm_say_hooks_one_batch_two_sentences(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_VOICE_SAY", "1")
    monkeypatch.setattr("robot_manage.llm_say.say", lambda text, voice=None: None)
    monkeypatch.setattr("robot_manage.llm_say.say_binary_path", lambda: "/bin/true")
    calls: list[str] = []

    class H:
        async def on_tts_begin(self) -> None:
            calls.append("b")

        async def on_tts_end(self) -> None:
            calls.append("e")

    async def main() -> None:
        r = LlmSayRunner(mic_hooks=H())
        r._binary = "/bin/true"
        r.start()
        await r.enqueue_sentence("First.")
        await r.enqueue_sentence("Second.")
        await asyncio.sleep(0.05)
        await r.aclose()

    asyncio.run(main())
    assert calls == ["b", "e"]
