"""Stage 2: the same noticeable word again within a few lines.

"A beautiful morning… the beautiful view." A word of five or more letters
is flagged at its second use if it comes back

* within WINDOW words (about two printed lines), when it is rare in the
  text (RARE uses or fewer): a distinctive word twice reads as a slip; or
* within CLOSE words, however common: even a book's subject words (people,
  school) jar that close.

Tuned on a 106,000-word book: without the rarity rule, 40 words flagged
1,398 places, nearly all a book's subject words coming round again; with
it, about 200. Words side by side are the `repeats` stage's business.

Left alone: a word doubled round "and" ("round and round", "faster and
faster"), a figure rather than a slip; common words (COMMON), bold capitalised words (this house style
bolds names), and words capitalised in both uses, which are nearly always
names. A paragraph shorter than SHORT words is taken to be a line of verse
or a heading (`\\\\` and headings become paragraph breaks): words inside it
are compared, but the window never reaches across it, so a chorus is not
flagged. Between ordinary paragraphs the window carries on.

Each finding's group is the stretch from the first use to the second, in
lower case ("round and round"), so a refrain that comes round several times
is one item with several places (a refrain in verse, say).
"""

import re
from collections import Counter

from ..findings import Finding
from ..prose import paragraphs

NAME = "near-repeats"
TITLE = "Near repeats"
BLURB = "the same word again within a few lines"

#: How far to look back, in words, and the shortest word worth flagging.
WINDOW = 25
CLOSE = 4
#: A word used this many times or fewer in the whole text counts as rare.
RARE = 6
MIN_LETTERS = 5
#: A paragraph with fewer words than this is a lyric line or a heading.
SHORT = 12

WORD = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*")

#: Long words that turn up everywhere; repeating them is not a slip.
COMMON = frozenset("""
about above after again against along already although always among another
anyone anything around because before behind being below between could
didn't doesn't don't every everyone everything first going little might
never nothing other perhaps quite rather really right shall should since
someone something still their there there's these thing things think those
though three through under until where which while whole without would
wouldn't couldn't shouldn't wasn't weren't isn't aren't haven't hadn't
can't won't you're they're we're you've they've you'll they'll that's
what's itself himself herself myself yourself themselves ourselves yeah
okay they'd you'd we'd she'd he'd anywhere somewhere everywhere whatever
""".split())


def _key(word: str) -> str:
    """The word as compared: straight apostrophe, lower case, no 's."""
    return word.replace("’", "'").lower().removesuffix("'s")


def _phrase(stretch: str) -> str:
    """The stretch between two uses as compared: lower case, spaces collapsed."""
    return " ".join(stretch.lower().split())


def _x_and_x(stretch: str) -> bool:
    """"round and round": the same word either side of "and", nothing else."""
    words = _phrase(stretch).split(" ")
    return len(words) == 3 and words[1] == "and"


def _flagged(gap: int, uses: int, both_capitals: bool) -> bool:
    """Whether a word's use `gap` words after its last one is a near repeat."""
    near = gap <= CLOSE or uses <= RARE
    return 1 < gap <= WINDOW and near and not both_capitals


def run(prose, settings) -> list[Finding]:
    text = prose.text
    uses = Counter(_key(m.group()) for m in WORD.finditer(text))
    found: list[Finding] = []
    # key → (word number, capitalised, offset) of its last use
    last: dict[str, tuple[int, bool, int]] = {}
    index = 0
    for base, para in paragraphs(text):
        words = list(WORD.finditer(para))
        if short := len(words) < SHORT:
            last = {}  # a verse line or heading: nothing reaches across it
        for match in words:
            index += 1
            word, key, start = match.group(), _key(match.group()), base + match.start()
            capital = word[0].isupper()
            if len(key) < MIN_LETTERS or key in COMMON or (capital and prose.bold[start]):
                continue
            if (
                (before := last.get(key))
                and _flagged(index - before[0], uses[key], before[1] and capital)
                and not _x_and_x(text[before[2]:base + match.end()])
            ):
                found.append(Finding(NAME, start, base + match.end(),
                                     f"“{key}” again, {index - before[0]} words after the last",
                                     group=_phrase(text[before[2]:base + match.end()])))
            last[key] = (index, capital, start)
        if short:
            last = {}
    return found
