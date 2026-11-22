"""Stage: the same noticeable word again within a few lines."""

from __future__ import annotations

from texcheck.checks import Settings, near_repeats
from texcheck.prose import extract


def found(tex: str) -> list[str]:
    prose = extract("\\begin{document}\n" + tex + "\n\\end{document}\n")
    return [f.message for f in near_repeats.run(prose, Settings())]


FILLER = "and then we sat by the sea for a bit "  # 10 short words


def test_flags_a_word_used_again_soon():
    assert found("It was a beautiful morning, " + FILLER + "with a beautiful view.") == [
        "“beautiful” again, 14 words after the last"
    ]


def test_not_when_far_apart():
    assert found("A beautiful morning, " + FILLER * 5 + "a beautiful view.") == []


def test_short_and_common_words_are_left_alone():
    assert found("There would be a cat there, and it would sit there.") == []


def test_neighbours_are_left_to_the_repeats_stage():
    assert found("It was really, really good.") == []


def test_names_are_left_alone():
    assert found("\\textbf{Bowie} sang, and later \\textbf{Bowie} sang again.") == []
    assert found("Ziggy played guitar, and then Ziggy sucked up into his mind.") == []


def test_case_and_possessive_are_ignored():
    assert found("Gardens grew. " + FILLER + "the garden's wall and the gardens") == [
        "“gardens” again, 17 words after the last",
    ]


def test_window_does_not_cross_lyric_lines():
    assert found("\\begin{words}{yellow river\\\\yellow river\\\\so far away}\\end{words}") == []


def test_window_crosses_ordinary_paragraphs():
    first = "We sat on the harbour wall and watched the boats come slowly in.\n\n"
    second = "Later the harbour was quiet and the gulls had gone home to roost."
    assert found(first + second) == ["“harbour” again, 11 words after the last"]


def test_a_word_common_in_the_text_is_flagged_only_when_very_close():
    """A book's subject words (people, school) come back all the time."""
    spaced = ("The school bell rang. " + FILLER) * 7  # 7 uses, 14 words apart
    assert found(spaced) == []
    assert found(spaced + "the school, the school") == ["“school” again, 2 words after the last"]
