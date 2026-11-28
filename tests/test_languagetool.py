"""LanguageTool: its matches turned into findings, and its local server."""

import shutil

import pytest

from texcheck import languagetool as lt
from texcheck.checks import Settings
from texcheck.checks import languagetool as stage
from texcheck.latex import extract


def match(offset: int, length: int, rule: str, category: str, message: str = "a message",
          replacements: tuple[str, ...] = ()) -> dict:
    """One match as LanguageTool's /v2/check returns it (the parts we read)."""
    return {"offset": offset, "length": length, "message": message,
            "replacements": [{"value": r} for r in replacements],
            "rule": {"id": rule, "category": {"id": category}}}


def body(text: str) -> str:
    return "\\begin{document}\n" + text + "\n\\end{document}\n"


@pytest.fixture
def answers(monkeypatch):
    """Stand in for the server: `answers.reply(text) -> matches` per request."""
    sent: list[str] = []

    class Fake:
        reply = staticmethod(lambda text: [])

    def check(text: str, **kw) -> list[dict]:
        sent.append(text)
        return Fake.reply(text)

    monkeypatch.setattr(stage, "_check", check)
    monkeypatch.setattr(lt, "server", lambda: None)
    Fake.sent = sent
    return Fake


# ── kinds ──

@pytest.mark.parametrize(("rule", "category", "kind"), [
    ("AUXILIARY_DO_WITH_INCORRECT_VERB_FORM", "GRAMMAR", "grammar"),
    ("IT_IS", "TYPOS", "grammar"),
    ("EVERYDAY_EVERY_DAY", "CONFUSED_WORDS", "grammar"),
    ("LICENCE_LICENSE_NOUN_SINGULAR", "AMERICAN_ENGLISH", "british"),
    ("EN_GB_SIMPLE_REPLACE_ZIPPER", "STYLE", "british"),
    ("MISSING_HYPHEN", "PUNCTUATION", "hyphens"),
    ("YEAR_OLD_HYPHEN", "PUNCTUATION", "hyphens"),
    ("EN_COMPOUNDS_HITCH_HIKED", "MISC", "hyphens"),
    ("FULL_TIME", "COMPOUNDING", "hyphens"),
    ("CAFE_DIACRITIC", "TYPOGRAPHY", "hyphens"),
    ("EN_DIACRITICS_REPLACE_ORTHOGRAPHY_FETES", "TYPOS", "hyphens"),
    ("COMMA_COMPOUND_SENTENCE", "PUNCTUATION", "style"),
    ("DOUBLE_PUNCTUATION", "PUNCTUATION", "grammar"),
    ("ENGLISH_WORD_REPEAT_BEGINNING_RULE", "REPETITIONS_STYLE", "style"),
    ("RETURN_BACK", "REDUNDANCY", "style"),
    ("SOMETHING_NEW", "SOMETHING_ELSE", "grammar"),
])
def test_each_rule_has_a_kind(rule, category, kind):
    assert stage.kind_of(rule, category) == kind


# ── findings ──

def test_matches_become_findings_at_their_place_in_the_prose(answers):
    prose = extract(body("Some words first.\n\nI didn't understood why."))
    at = prose.text.index("understood")
    answers.reply = lambda text: [match(text.index("understood"), 10, "AUXILIARY_DO", "GRAMMAR",
                                        "Use the base form.", ("understand",))]
    [found] = stage.run(prose, Settings())
    assert (found.start, found.end) == (at, at + 10)
    assert found.message == "Use the base form."
    assert found.suggestions == ["understand"]
    assert found.group == "grammar"


def test_long_texts_go_in_several_requests_split_at_paragraphs(answers, monkeypatch):
    monkeypatch.setattr(stage, "CHUNK", 60)
    paragraphs = [f"Paragraph number {n} has a few words in it." for n in range(6)]
    prose = extract(body("\n\n".join(paragraphs)))
    answers.reply = lambda text: [match(text.index("few"), 3, "R", "GRAMMAR")]
    found = stage.run(prose, Settings())
    assert len(answers.sent) > 1
    assert all(not t.startswith("\n") for t in answers.sent)
    assert sorted(f.start for f in found) == [
        m for m in range(len(prose.text)) if prose.text.startswith("few", m)][:len(answers.sent)]
    assert all(prose.text[f.start:f.end] == "few" for f in found)


def test_bold_names_are_left_alone(answers):
    """House style bolds names (\\textbf{The Also People}): not grammar."""
    prose = extract(body(r"Ben's \textbf{The Also People} defined a world."))
    answers.reply = lambda text: [match(text.index("Also"), 11, "A_RB_NN", "GRAMMAR")]
    assert stage.run(prose, Settings()) == []


VERSE = "the rain was like the summertime\\\\\nwe saw it,, then left\\\\\nhe go home\\\\\n"
PROSE = ("the rain was like the summertime, and we saw it,, then left; he go home "
         "and the rest of a long paragraph of prose.")


def verse_answers(text: str) -> list[dict]:
    return [match(text.index("the"), 3, "UPPERCASE_SENTENCE_START", "CASING"),
            match(text.index("summertime"), 10, "SUMMER_TIME", "REDUNDANCY"),
            match(text.index(",,"), 2, "DOUBLE_PUNCTUATION", "PUNCTUATION"),
            match(text.index("saw"), 3, "COMMA_COMPOUND_SENTENCE", "PUNCTUATION"),
            match(text.index("go"), 2, "HE_VERB_AGR", "GRAMMAR")]


def test_verse_keeps_its_mistakes_but_not_style_suggestions(answers):
    answers.reply = verse_answers
    found = stage.run(extract(body(VERSE)), Settings())
    assert [f.message for f in found] == ["a message"] * 2
    assert {extract(body(VERSE)).text[f.start:f.end] for f in found} == {",,", "go"}


def test_prose_keeps_style_suggestions(answers):
    answers.reply = verse_answers
    assert len(stage.run(extract(body(PROSE)), Settings())) == 5


def test_what_other_stages_check_is_turned_off():
    disabled = set(stage.DISABLED_RULES)
    assert {"MORFOLOGIK_RULE_EN_GB", "ENGLISH_WORD_REPEAT_RULE", "WHITESPACE_RULE"} <= disabled
    assert "BRE_STYLE_OXFORD_SPELLING" in stage.DISABLED_CATEGORIES   # the house spells -ise


def test_not_installed_is_a_skip(monkeypatch):
    monkeypatch.setattr(lt.shutil, "which", lambda name: None)
    monkeypatch.setattr(lt, "_server", None)
    with pytest.raises(lt.Unavailable, match="brew install languagetool"):
        lt.server()


# ── the real server (slow: starts Java) ──

@pytest.mark.skipif(not shutil.which("languagetool-server"), reason="LanguageTool not installed")
def test_the_local_server_checks_text():
    matches = lt.check("I didn't understood why.", language="en-GB")
    assert any(m["rule"]["id"] == "AUXILIARY_DO_WITH_INCORRECT_VERB_FORM" for m in matches)
    assert lt.server().url.startswith("http://127.0.0.1:")


def test_the_server_stops_if_tex_check_is_killed(tmp_path):
    """The watchdog stops the server when its parent dies without cleaning up."""
    import os
    import signal
    import subprocess
    import sys
    import time

    pid_file = tmp_path / "server.pid"
    fake = tmp_path / "fake-server"   # stands in for languagetool-server
    fake.write_text(f'#!/bin/sh\necho $$ > "{pid_file}"\nexec sleep 60\n')
    fake.chmod(0o755)
    parent = subprocess.Popen([sys.executable, "-c", (
        "import subprocess, time\n"
        "from texcheck.languagetool import _WATCHDOG\n"
        f"subprocess.Popen(['/bin/sh', '-c', _WATCHDOG, {str(fake)!r}], stdin=subprocess.PIPE)\n"
        "time.sleep(60)\n")])
    deadline = time.monotonic() + 10
    while not (pid_file.exists() and pid_file.read_text().strip()) and time.monotonic() < deadline:
        time.sleep(0.05)
    server = int(pid_file.read_text())
    os.kill(parent.pid, signal.SIGKILL)
    parent.wait()
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            os.kill(server, 0)
        except ProcessLookupError:
            return
        time.sleep(0.05)
    os.kill(server, signal.SIGKILL)
    pytest.fail("the server outlived tex-check")
