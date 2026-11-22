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

Left alone: common words (COMMON), bold capitalised words (this house style
bolds names), and words capitalised in both uses, which are nearly always
names. A paragraph shorter than SHORT words is taken to be a line of verse
or a heading (`\\\\` and headings become paragraph breaks): words inside it
are compared, but the window never reaches across it, so a chorus is not
flagged. Between ordinary paragraphs the window carries on.
"""

from __future__ import annotations

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
COMMON = set("""
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
    key = word.replace("’", "'").lower()
    return key[:-2] if key.endswith("'s") else key


def run(prose, settings) -> list[Finding]:
    text = prose.text
    uses = Counter(_key(m.group()) for m in WORD.finditer(text))
    found: list[Finding] = []
    window: list[tuple[int, str, re.Match, int]] = []  # (index, key, match, base)
    index = 0
    for base, para in paragraphs(text):
        words = list(WORD.finditer(para))
        short = len(words) < SHORT
        if short:
            window = []  # a verse line or heading: nothing reaches across it
        for match in words:
            key = _key(match.group())
            index += 1
            if len(key) < MIN_LETTERS or key in COMMON:
                continue
            start = base + match.start()
            if match.group()[0].isupper() and prose.bold[start]:
                continue
            window = [w for w in window if index - w[0] <= WINDOW]
            last = next((w for w in reversed(window) if w[1] == key), None)
            if last is not None:
                gap = index - last[0]
                both_capitals = last[2].group()[0].isupper() and match.group()[0].isupper()
                near = gap <= CLOSE or uses[key] <= RARE
                if gap > 1 and near and not both_capitals:
                    found.append(Finding(
                        NAME, start, base + match.end(),
                        f"“{key}” again, {gap} words after the last",
                    ))
            window.append((index, key, match, base))
        if short:
            window = []
    return found
