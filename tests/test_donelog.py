"""The action log beside each book: OK marks and word-list adds, undoable."""

from texcheck import donelog, wordlists


def test_record_and_read_back(tmp_path):
    log = tmp_path / donelog.LOG_NAME
    entry = donelog.record(log, action="ok", stage="repeats", text="nine nine",
                           context="bsq{nine nine nine}", line=1140)
    [read] = donelog.entries(log)
    assert read == entry
    assert read.id and read.at


def test_bad_lines_are_skipped(tmp_path):
    """A hand-edited or half-written line must not lose the rest of the log."""
    log = tmp_path / donelog.LOG_NAME
    donelog.record(log, action="ok", stage="repeats", text="a", context="a a", line=1)
    with log.open("a") as handle:
        handle.write("{not json\n\n[1, 2]\n")
    donelog.record(log, action="ok", stage="repeats", text="b", context="b b", line=2)
    assert [e.text for e in donelog.entries(log)] == ["a", "b"]


def test_ok_marks_exclude_undone(tmp_path):
    log = tmp_path / donelog.LOG_NAME
    kept = donelog.record(log, action="ok", stage="repeats", text="hah hah", context="c1", line=1)
    dropped = donelog.record(log, action="ok", stage="spelling", text="vould", context="c2", line=2)
    donelog.record(log, action="book", stage="spelling", word="vos", text="vos", context="c3", line=3)
    donelog.record(log, action="undo", target=dropped.id)
    assert donelog.ok_marks(log) == {donelog.fingerprint("repeats", "hah hah", "c1")}
    assert donelog.undone(donelog.entries(log)) == {dropped.id}
    assert kept.id not in donelog.undone(donelog.entries(log))


def test_missing_log_is_empty(tmp_path):
    assert donelog.entries(tmp_path / "absent.jsonl") == []
    assert donelog.ok_marks(tmp_path / "absent.jsonl") == set()


def test_remove_word(tmp_path):
    words = tmp_path / "w.txt"
    wordlists.append_word(words, "Ziggys")
    wordlists.append_word(words, "Daleks")
    assert wordlists.remove_word(words, "ziggys") is True
    assert wordlists.load([words]) == {"daleks"}
    assert words.read_text().startswith(wordlists.HEADER)
    assert wordlists.remove_word(words, "ziggys") is False
