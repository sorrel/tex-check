import subprocess
from pathlib import Path

from texcheck.opener import open_at, parse_location, unique_phrase

TEXT = (
    "The sun was warm and the sun was out.\n"
    "The kettle was was cold by then, and the sun was warm.\n"
    "\n"
    "short\n"
)


def test_phrase_starts_at_the_column_and_is_unique():
    phrase = unique_phrase(TEXT, 2, 12)  # the first "was"
    assert phrase.startswith("was was")
    assert TEXT.count(phrase) == 1


def test_phrase_grows_left_when_the_line_runs_out():
    phrase = unique_phrase(TEXT, 2, 44)  # "sun was warm." at the end of line 2
    assert TEXT.count(phrase) == 1
    assert phrase.endswith("sun was warm.")


def test_phrase_stays_on_its_line():
    assert unique_phrase(TEXT, 4, 1) == "short"


def test_empty_line_gives_no_phrase():
    assert unique_phrase(TEXT, 3, 1) == ""


def test_parse_location_forms():
    assert parse_location(["doc.tex:12:5"]) == (Path("doc.tex"), 12, 5)
    assert parse_location(["doc.tex:12"])[1:] == (12, 1)
    assert parse_location(["doc.tex", "12", "5"])[1:] == (12, 5)
    assert parse_location(["doc.tex", "12", ""])[1:] == (12, 1)


class FakeRun:
    """Stands in for subprocess.run: records each argv, fails osascript on request."""

    def __init__(self, osascript_error: str = ""):
        self.calls: list[list[str]] = []
        self.osascript_error = osascript_error

    def __call__(self, argv, **kwargs):
        self.calls.append(list(argv))
        failed = argv[0] == "osascript" and self.osascript_error
        return subprocess.CompletedProcess(argv, 1 if failed else 0, "", self.osascript_error)


def test_open_at_opens_then_finds(tmp_path):
    tex = tmp_path / "doc.tex"
    tex.write_text(TEXT)
    run = FakeRun()
    assert open_at(tex, 2, 12, run=run) is None
    assert run.calls[0] == ["open", "-a", "Texifier", str(tex)]
    assert run.calls[1][0] == "osascript"
    assert run.calls[1][-1].startswith("was was")


def test_open_at_reports_accessibility(tmp_path):
    tex = tmp_path / "doc.tex"
    tex.write_text(TEXT)
    error = open_at(tex, 2, 12, run=FakeRun("execution error: not allowed assistive access (-1719)"))
    assert "Accessibility" in error


def test_open_at_missing_file(tmp_path):
    assert "no such file" in open_at(tmp_path / "gone.tex", 1, 1, run=FakeRun())


def test_open_at_takes_the_phrase_from_given_text(tmp_path):
    """The browser passes the text it checked, so a later edit cannot move the target."""
    tex = tmp_path / "doc.tex"
    tex.write_text("A new line above.\n" + TEXT)
    run = FakeRun()
    open_at(tex, 2, 12, run=run, text=TEXT)
    assert run.calls[1][-1].startswith("was was")
