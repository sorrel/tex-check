"""Word lists: words aspell should accept, one per line.

There are two, because the words fall into two kinds:

* **The book's own** (`tex-check-words.txt` beside the .tex file): names of
  people in it, dialect, invented words. They belong to that text, travel
  and sync with it, and survive its folder being moved. In another document
  "goot" should still be flagged.
* **The personal list** (`words.txt` at the root of this repository): good
  English aspell lacks (heathland, matchday) and brands (Ericsson), wanted in
  everything. It lives in git, so a word added by mistake shows in the
  history. It is found relative to this source file, which works because
  tex-check is an editable install; a normal install falls back to the data
  folder beside the place names.

Words are compared case-insensitively, with curly apostrophes made straight.
"""

from pathlib import Path

from . import places

BOOK_NAME = "tex-check-words.txt"
PERSONAL_NAME = "words.txt"

#: The first line of a list tex-check creates.
HEADER = "# tex-check word list: one word per line, '#' starts a comment"

_REPO = Path(__file__).resolve().parents[2]


def normalise(word: str) -> str:
    return word.replace("’", "'")


def book_file(tex: Path) -> Path:
    return tex.parent / BOOK_NAME


def personal_file() -> Path:
    """The personal list: in the repository when running from one."""
    if (_REPO / "pyproject.toml").is_file():
        return _REPO / PERSONAL_NAME
    return places.data_dir() / PERSONAL_NAME


def load(paths: list[Path]) -> set[str]:
    """Every word in the given lists, lower-cased; missing files are skipped."""
    words = set()
    for path in paths:
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.split("#", 1)[0].strip()
            if line:
                words.add(normalise(line).lower())
    return words


def append_word(path: Path, word: str) -> bool:
    """Add `word` to the list at `path`, creating it if need be.

    Returns False, writing nothing, when the list already has the word.
    """
    word = normalise(word)
    if word.lower() in load([path]):
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.is_file() else HEADER + "\n"
    if existing and not existing.endswith("\n"):
        existing += "\n"
    path.write_text(existing + word + "\n", encoding="utf-8")
    return True


def remove_word(path: Path, word: str) -> bool:
    """Take `word` out of the list at `path` (for undo). False if it was not there.

    Comments, blank lines and other words are kept as they are.
    """
    if not path.is_file():
        return False
    target = normalise(word).lower()
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    kept = [
        line for line in lines
        if normalise(line.split("#", 1)[0].strip()).lower() != target
    ]
    if len(kept) == len(lines):
        return False
    path.write_text("".join(kept), encoding="utf-8")
    return True
