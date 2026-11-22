from pathlib import Path

from texcheck.opener import parse_location, unique_phrase

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
