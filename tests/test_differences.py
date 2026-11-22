"""How a suggestion differs from the word, said in plain words.

Near-identical spellings are hard to tell apart by eye (an extra "l"
especially), so every suggestion says what changed and marks the letters.
"""

from __future__ import annotations

import pytest

from texcheck.differences import describe, marked


@pytest.mark.parametrize(("word", "suggestion", "expected"), [
    ("Eclesall", "Ecclesall", "missing a c"),
    ("fullfil", "fulfil", "extra l"),
    ("recieve", "receive", "i and e swapped"),
    ("lyrca", "Lycra", "r and c swapped, capital L"),
    ("seperate", "separate", "a for e"),
    ("Ziggys", "Ziggy's", "missing apostrophe"),
    ("ok", "OK", "capitals OK"),
    ("heathland", "heath land", "space added"),
    ("ensuite", "en-suite", "hyphen added"),
    ("dénouement", "denouement", "no accent on e"),
    ("accomodate", "accommodate", "missing an m"),
    ("untill", "until", "extra l"),
    ("tomatos", "tomatoes", "missing an e"),
    ("lyrca", "lyric", "missing an i, extra a"),
    ("Gaeltacht", "Glaciate", ""),  # more than two changes: no description
])
def test_describe(word, suggestion, expected):
    assert describe(word, suggestion) == expected


def test_marked_shows_changed_letters_in_the_suggestion():
    assert marked("Eclesall", "Ecclesall") == [("E", False), ("c", True), ("clesall", False)]


def test_marked_swapped_letters():
    assert marked("recieve", "receive") == [("rec", False), ("ei", True), ("ve", False)]


def test_marked_extra_letter_marks_nothing_in_the_suggestion():
    """The letter is missing from the suggestion; describe() says which."""
    assert marked("fullfil", "fulfil") == [("fulfil", False)]
