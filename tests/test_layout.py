"""Layout checks on the typeset lines: lone I at the edges, stacks, runts."""

from itertools import pairwise

import pytest

from texcheck.checks import Settings, layout
from texcheck.latex import extract
from texcheck.pdfwords import Word

LEFT, RIGHT, CHAR = 40.0, 340.0, 5.0


def line(y: float, text: str, full: bool = True, indent: float = 0.0) -> list[Word]:
    """Words of one typeset line; a full line is justified to RIGHT."""
    words, x = [], LEFT + indent
    for token in text.split():
        words.append(Word(token, x, x + CHAR * len(token), y))
        x += CHAR * (len(token) + 1)
    if full and len(words) > 1:
        stretch = (RIGHT - words[-1].x1) / (len(words) - 1)
        words = [Word(w.text, w.x0 + i * stretch, w.x1 + i * stretch, w.y) for i, w in enumerate(words)]
    return words


def page(*lines: list[Word]) -> list[Word]:
    return [word for words in lines for word in words]


def hits(*pages) -> list[str]:
    return [h.message for h in layout.find(list(pages))]


def test_one_word_on_the_last_line_of_a_paragraph():
    assert hits(page(
        line(600, "we waited by the gate until the rain stopped and then we"),
        line(588, "went.", full=False),
    )) == ["one word on the last line of a paragraph: “went.”"]


def test_a_short_last_line_of_two_words_is_fine():
    assert hits(page(
        line(600, "we waited by the gate until the rain stopped and then we"),
        line(588, "went home.", full=False),
    )) == []


def test_a_one_line_paragraph_is_not_a_runt():
    assert hits(page(line(600, "Contents", full=False))) == []


def test_lone_i_at_line_edges_in_one_paragraph():
    assert hits(page(
        line(600, "it was late and so I", indent=0),
        line(588, "I went back and the road was dark but"),
        line(576, "the house was there, lit up.", full=False),
    )) == ["2 lone “I”s at line edges in this paragraph (lines 1, 2)"]


def test_one_lone_i_is_fine():
    assert hits(page(
        line(600, "it was late and the road went on so I"),
        line(588, "went back and the house was there, lit up.", full=False),
    )) == []


def test_lone_i_across_a_page():
    paragraphs = []
    y = 600
    for _ in range(3):
        paragraphs.append(line(y, "and then later in the evening, I"))
        paragraphs.append(line(y - 12, "went home again.", full=False))
        y -= 24
    found = hits(page(*paragraphs))
    assert found == ["3 lone “I”s at line edges on this page (lines 1, 3, 5)"]


def test_same_word_starting_two_lines_running():
    assert hits(page(
        line(600, "the gate was shut and the dog was barking at"),
        line(588, "the gate as if it knew we were there.", full=False),
    )) == ["“the” starts two lines running"]  # the two “gate”s overlap by only half


def test_same_word_ending_two_lines_running():
    found = hits(page(
        line(600, "we waited by the gate until it was late, and"),
        line(588, "the dog was barking and running round and"),
        line(576, "round.", full=False),
    ))
    assert "“and” ends two lines running" in found


def test_word_directly_above_the_same_word():
    upper = [Word("over", 40, 60, 600), Word("the", 100, 115, 600), Word("garden", 150, 180, 600),
             Word("wall", 320, 340, 600)]
    lower = [Word("into", 40, 60, 588), Word("a", 100, 105, 588), Word("garden", 152, 182, 588),
             Word("shed", 320, 340, 588)]
    assert hits(upper + lower) == ["“garden” directly above “garden”"]


def test_not_above_when_only_near():
    upper = [Word("over", 40, 60, 600), Word("garden", 150, 180, 600), Word("wall", 320, 340, 600)]
    lower = [Word("into", 40, 60, 588), Word("garden", 200, 230, 588), Word("shed", 320, 340, 588)]
    assert hits(upper + lower) == []


def test_page_numbers_are_ignored():
    assert hits(page(
        line(600, "we waited by the gate until the rain stopped and then we"),
        line(588, "went home.", full=False),
        line(40, "16", full=False),
    )) == []


def test_findings_are_mapped_back_to_the_source(tmp_path, monkeypatch):
    tex = tmp_path / "doc.tex"
    tex.write_text("\\begin{document}\nWe waited by the gate until the rain\nstopped and then we went.\n\\end{document}\n")
    (tmp_path / "doc.pdf").write_bytes(b"%PDF")
    monkeypatch.setattr(layout.pdfwords, "read", lambda pdf, **kw: [page(
        line(600, "We waited by the gate until the rain stopped and then we"),
        line(588, "went.", full=False),
    )])
    prose = extract(tex.read_text())
    [finding] = layout.run(prose, Settings(pdf=tmp_path / "doc.pdf"))
    assert prose.text[finding.start:finding.end] == "went"
    assert "PDF page 1" in finding.note


def test_hyphenated_words_still_map(tmp_path, monkeypatch):
    """A word split across lines (pota-/toes) must not throw the matching off."""
    src = "\\begin{document}\nThere were potatoes too and the gate was shut and so.\n\\end{document}\n"
    monkeypatch.setattr(layout.pdfwords, "read", lambda pdf, **kw: [page(
        line(600, "There were pota-"),
        line(588, "toes too and the gate was shut and"),
        line(576, "so.", full=False),
    )])
    prose = extract(src)
    found = layout.run(prose, Settings(pdf=tmp_path / "doc.pdf"))
    assert [prose.text[f.start:f.end] for f in found] == ["so"]


def test_no_pdf_skips_the_stage(tmp_path):
    with pytest.raises(layout.Skipped, match="no PDF"):
        layout.run(extract("x"), Settings(pdf=None))


def test_a_stray_mark_at_the_page_edge_does_not_move_the_margin():
    stray = [Word(".", 0, 0.5, 300)]
    assert hits(page(
        line(600, "the gate was shut and the dog was barking at"),
        line(588, "the dog as if it knew we were there and so"),
        line(576, "went home.", full=False),
        stray,
    ))[0] == "“the” starts two lines running"


def test_glued_lines_are_split_into_the_books_words():
    """PDFKit sometimes runs a whole line together with no gaps to split on."""
    glued = [Word("Leeds,inKentorDevonshire:Hatfield", 40, 230, 600)]
    vocab = {"leeds", "in", "kent", "or", "devonshire", "hatfield"}
    [words] = layout.unglue([glued], vocab)
    assert [w.text for w in words] == ["Leeds,", "in", "Kent", "or", "Devonshire:", "Hatfield"]
    assert words[0].x0 == 40 and words[-1].x1 == 230
    assert all(a.x1 <= b.x0 for a, b in pairwise(words))


def test_a_long_word_of_the_book_is_left_whole():
    word = [Word("unselfconsciously", 40, 120, 600)]
    assert layout.unglue([word], {"unselfconsciously", "un", "self"}) == [word]


def test_a_glued_line_starting_with_a_hyphenation_tail_still_splits():
    glued = [Word("ingintothenight,underthestars.", 40, 200, 600)]
    vocab = {"into", "the", "night", "under", "stars"}
    [words] = layout.unglue([glued], vocab)
    assert [w.text for w in words] == ["ing", "into", "the", "night,", "under", "the", "stars."]


def test_a_heading_is_not_a_runt():
    assert hits(page(
        line(600, "we waited by the gate until the rain stopped and then we"),
        line(588, "Preface", full=False),
    )) == []


def test_one_line_with_i_at_both_ends_says_line():
    assert hits(page(
        line(600, "I knew the road was long and so I"),
        line(588, "went.", full=False),
    )) == ["one word on the last line of a paragraph: “went.”",
           "2 lone “I”s at line edges in this paragraph (line 1)"]


def test_messages_keep_the_word_as_written():
    assert hits(page(
        line(600, "I knew the road was long and the dog"),
        line(588, "I thought, would be fine at home.", full=False),
    )) == ["2 lone “I”s at line edges in this paragraph (lines 1, 2)", "“I” starts two lines running"]


def test_titles_are_not_compared():
    """A section or chapter title is not part of the running text."""
    heading = line(588, "The Road", full=False)
    pages = [page(
        line(600, "the last words of the chapter before this one were", ),
        line(594, "the end.", full=False),
        heading,
        line(576, "The road ran on and the dog ran with it, and we ran"),
        line(564, "home.", full=False),
    )]
    titles = {id(w) for w in pages[0] if w in heading}
    assert "“The” starts two lines running" not in [h.message for h in layout.find(pages, titles)]
    assert sorted(h.message for h in layout.find(pages, titles)) == [
        "one word on the last line of a paragraph: “home.”",
        "“the” starts two lines running",
    ]


def test_prose_records_where_titles_are():
    prose = extract("\\begin{document}\n\\section{The Road}\nThe road ran on.\n\\end{document}\n")
    [(start, end)] = prose.titles
    assert prose.text[start:end] == "The Road"


def test_title_lines_are_found_through_the_source(tmp_path, monkeypatch):
    src = ("\\begin{document}\n\\section{The Walk}\n"
           "The walk was long and the dog was tired and so were we all by then.\n\\end{document}\n")
    monkeypatch.setattr(layout.pdfwords, "read", lambda pdf, **kw: [page(
        line(600, "The Walk", full=False),
        line(588, "The walk was long and the dog was tired and so were we"),
        line(576, "all by then.", full=False),
    )])
    assert layout.run(extract(src), Settings(pdf=tmp_path / "doc.pdf")) == []


def test_a_word_partly_above_at_an_angle_is_fine():
    """Only a word squarely on top of itself looks wrong; askew is fine."""
    upper = [Word("over", 40, 60, 600), Word("garden", 150, 180, 600), Word("wall", 320, 340, 600)]
    lower = [Word("into", 40, 60, 588), Word("garden", 156, 186, 588), Word("shed", 320, 340, 588)]
    assert hits(upper + lower) == []  # shifted by a fifth of its width


def _stacked(*xs: float, word: str = "garden") -> list[Word]:
    """Three-word lines with `word` in the middle at each x, from the top down."""
    firsts, lasts = ["over", "into", "past", "from"], ["wall", "shed", "gate", "lane"]
    words = []
    for n, x in enumerate(xs):
        y = 600 - 12 * n
        words += [Word(firsts[n], 40, 60, y), Word(word, x, x + 30, y), Word(lasts[n], 320, 340, y)]
    return words


def test_three_of_a_word_one_above_another_at_an_angle():
    # Each a third of its width along from the one above: too askew for a pair.
    assert hits(_stacked(150, 160, 170)) == [
        "“garden” on 3 lines running, one above another"]


def test_a_stack_squarely_on_top_is_reported_once():
    assert hits(_stacked(150, 150, 150)) == [
        "“garden” on 3 lines running, one above another"]


def test_four_running_is_one_stack():
    assert hits(_stacked(150, 160, 170, 180)) == [
        "“garden” on 4 lines running, one above another"]


def test_two_askew_is_not_a_stack():
    assert hits(_stacked(150, 160)) == []


def test_words_that_do_not_overlap_are_not_a_stack():
    assert hits(_stacked(150, 185, 220)) == []


def test_a_stack_of_first_words_is_left_to_starts():
    found = hits(page(
        line(600, "and we waited by the gate until the rain stopped"),
        line(588, "and then we walked down to the river and back"),
        line(576, "and so the day went on until it was dark"),
    ))
    assert not any("lines running, one above another" in h for h in found)
    assert "“and” starts two lines running" in found
