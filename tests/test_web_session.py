"""The browser view's state: findings under opaque ids, word lists, re-checks.

A fake clock drives the 30-second wait, so nothing here sleeps.
"""

from __future__ import annotations

import os
import shutil

import pytest

from texcheck import wordlists
from texcheck.checks import STAGES
from texcheck.run import Options
from texcheck.web.session import Session, StaleId
from texcheck.web.watcher import Debouncer, Watcher

needs_aspell = pytest.mark.skipif(not shutil.which("aspell"), reason="aspell not installed")


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def bump_mtime(path, seconds=5):
    """Move a file's modification time on, as a save would."""
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + seconds * 1_000_000_000))


# ── the debounce ────────────────────────────────────────────────────────────

def test_debounce_restarts_on_second_save():
    clock = Clock()
    debouncer = Debouncer(30.0, clock)
    debouncer.touch()
    clock.now += 20
    debouncer.touch()
    clock.now += 29
    assert not debouncer.due()
    assert debouncer.seconds_left() == pytest.approx(1)
    clock.now += 1
    assert debouncer.due()
    assert not debouncer.due()  # once only
    assert debouncer.seconds_left() is None


def test_watcher_sees_save_and_fires(tmp_path):
    clock = Clock()
    tex = tmp_path / "doc.tex"
    tex.write_text("x")
    fired = []
    watcher = Watcher(lambda: [tex], Debouncer(30.0, clock), lambda: fired.append(1))
    watcher.poll()
    assert fired == []
    bump_mtime(tex)
    watcher.poll()
    clock.now += 30
    watcher.poll()
    watcher.poll()
    assert fired == [1]


def test_watcher_counts_a_new_file_as_a_save(tmp_path):
    clock = Clock()
    words = tmp_path / "tex-check-words.txt"
    debouncer = Debouncer(30.0, clock)
    watcher = Watcher(lambda: [words], debouncer, lambda: None)
    words.write_text("lyrca\n")
    watcher.poll()
    assert debouncer.seconds_left() == pytest.approx(30)


# ── the session ─────────────────────────────────────────────────────────────

@pytest.fixture
def session(tmp_path, monkeypatch):
    monkeypatch.setattr(wordlists, "personal_file", lambda: tmp_path / "personal.txt")
    tex = tmp_path / "doc.tex"
    tex.write_text("\\begin{document}\nIn lyrca, at Ericsson, in lyrca.\n\\end{document}\n")
    opened = []
    made = Session(tex, STAGES, Options(), gazetteer=None, clock=Clock(),
                   opener=lambda path, line, col, text=None: opened.append((path, line, col, text)))
    made.opened = opened
    return made


def item_for(session, word):
    for group in session.findings()["groups"]:
        for item in group["items"]:
            if item["word"] == word:
                return item
    return None


@needs_aspell
def test_findings_payload_shape(session):
    payload = session.findings()
    assert payload["version"] == 1
    assert payload["file"] == "doc.tex"
    typos = next(g for g in payload["groups"] if g["key"] == "typos")
    assert typos["count"] == 1
    use = typos["items"][0]["uses"][0]
    assert (use["line"], use["hit"]) == (2, "lyrca")


@needs_aspell
def test_open_passes_line_and_column(session):
    use = item_for(session, "lyrca")["uses"][1]
    assert session.open(use["id"]) is None
    assert session.opened[0][:3] == (session.path, 2, use["col"])


@needs_aspell
def test_add_word_removes_item_and_writes_book_list(session):
    item = item_for(session, "lyrca")
    removed = session.add_word(item["id"], "book")
    assert removed == [item["id"]]
    assert item_for(session, "lyrca") is None
    assert "lyrca" in wordlists.load([wordlists.book_file(session.path)])


@needs_aspell
def test_add_word_everywhere_writes_personal_list(session):
    session.add_word(item_for(session, "Ericsson")["id"], "personal")
    assert wordlists.load([wordlists.personal_file()]) == {"ericsson"}


@needs_aspell
def test_add_word_is_not_a_save(session):
    session.add_word(item_for(session, "lyrca")["id"], "book")
    session.watcher.poll()
    assert session.status()["state"] == "idle"


@needs_aspell
def test_save_shows_waiting_then_rechecks(session):
    bump_mtime(session.path)
    session.watcher.poll()
    status = session.status()
    assert status["state"] == "waiting" and status["seconds_left"] == 30
    session.clock.now += 30
    session.watcher.poll()
    assert session.status() == {"version": 2, "state": "idle", "seconds_left": None, "error": None}


@needs_aspell
def test_recheck_reads_new_words(session):
    wordlists.personal_file().write_text("lyrca\n")
    session.recheck()
    assert session.findings()["version"] == 2
    assert item_for(session, "lyrca") is None


@needs_aspell
def test_failed_recheck_keeps_findings(session):
    before = session.findings()
    session.path.unlink()
    session.recheck()
    assert session.status()["error"]
    assert session.findings() == before


@needs_aspell
def test_stale_id_raises(session):
    use = item_for(session, "lyrca")["uses"][0]
    session.recheck()
    with pytest.raises(StaleId):
        session.open(use["id"])
    with pytest.raises(StaleId):
        session.add_word("made-up", "book")


@needs_aspell
def test_bad_scope_is_refused(session):
    with pytest.raises(ValueError):
        session.add_word(item_for(session, "lyrca")["id"], "everywhere-else")


# ── races and staleness (from the branch review) ────────────────────────────

class _AddsWordMidCheck:
    """A stage that adds a word to a list while the check is running."""

    NAME, TITLE, BLURB = "midcheck", "Mid-check", "test only"

    def __init__(self, session, item_id):
        self.session, self.item_id = session, item_id

    def run(self, prose, settings):
        self.session.add_word(self.item_id, "book")
        return []


@needs_aspell
def test_word_added_during_a_running_check_stays_gone(session):
    item = item_for(session, "lyrca")
    session.stages = [*STAGES, _AddsWordMidCheck(session, item["id"])]
    session.recheck()
    assert item_for(session, "lyrca") is None


@needs_aspell
def test_adding_a_word_does_not_swallow_a_save(session):
    bump_mtime(session.path)  # saved in Texifier, not yet polled
    session.add_word(item_for(session, "lyrca")["id"], "book")
    session.watcher.poll()
    assert session.status()["state"] == "waiting"


@needs_aspell
def test_open_finds_the_text_that_was_checked(session):
    use = item_for(session, "lyrca")["uses"][0]
    checked = session.path.read_text()
    session.path.write_text("\\begin{document}\nA new first line.\n" + checked)
    session.open(use["id"])
    path, line, col, text = session.opened[-1]
    assert text == checked


# ── OK marks, the done log and undo ─────────────────────────────────────────

from texcheck import donelog  # noqa: E402


def uses_of(session, word):
    item = item_for(session, word)
    return item["uses"] if item else []


@needs_aspell
def test_items_carry_a_reason(session):
    assert item_for(session, "lyrca")["reason"] == "not in the dictionary"


@needs_aspell
def test_ok_hides_use_and_logs(session):
    first, second = uses_of(session, "lyrca")
    session.ok(first["id"])
    assert [u["id"] for u in uses_of(session, "lyrca")] == [second["id"]]
    [entry] = donelog.entries(donelog.log_file(session.path))
    assert (entry.action, entry.word, entry.line) == ("ok", "lyrca", 2)


@needs_aspell
def test_ok_survives_a_recheck(session):
    first, _ = uses_of(session, "lyrca")
    session.ok(first["id"])
    session.recheck()
    assert len(uses_of(session, "lyrca")) == 1


@needs_aspell
def test_done_lists_newest_first(session):
    first, _ = uses_of(session, "lyrca")
    session.ok(first["id"])
    session.add_word(item_for(session, "Ericsson")["id"], "personal")
    done = session.done()
    assert [d["action"] for d in done] == ["personal", "ok"]
    assert done[0]["word"] == "Ericsson" and done[0]["undone"] is False


@needs_aspell
def test_undo_ok_brings_it_back(session):
    first, _ = uses_of(session, "lyrca")
    session.ok(first["id"])
    session.undo(session.done()[0]["id"])
    assert len(uses_of(session, "lyrca")) == 2
    assert session.done()[0]["undone"] is True


@needs_aspell
def test_undo_add_removes_word_and_rechecks(session):
    session.add_word(item_for(session, "lyrca")["id"], "book")
    session.undo(session.done()[0]["id"])
    assert "lyrca" not in wordlists.load([wordlists.book_file(session.path)])
    assert len(uses_of(session, "lyrca")) == 2


@needs_aspell
def test_undo_add_keeps_a_word_that_was_already_there(session):
    """If the word was in the list before, undoing this add must not take it out."""
    book = wordlists.book_file(session.path)
    item = item_for(session, "lyrca")
    wordlists.append_word(book, "lyrca")  # added by hand meanwhile
    session.add_word(item["id"], "book")
    session.undo(session.done()[0]["id"])
    assert "lyrca" in wordlists.load([book])


@needs_aspell
def test_undo_twice_is_harmless(session):
    first, _ = uses_of(session, "lyrca")
    session.ok(first["id"])
    entry = session.done()[0]["id"]
    session.undo(entry)
    session.undo(entry)
    assert len([e for e in donelog.entries(donelog.log_file(session.path)) if e.action == "undo"]) == 1


@needs_aspell
def test_undo_unknown_raises(session):
    with pytest.raises(KeyError):
        session.undo("no-such-entry")
