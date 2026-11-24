"""Lay findings out for reading in a terminal, or as JSON for other tools.

Every finding starts with `file:line:column`, the form iTerm (Cmd-click,
via Semantic History) and most editors' terminals recognise as a link. The
file is shown relative to the current directory when it lies inside it,
which keeps the column short; iTerm resolves it against the shell's
directory, so the link still works.

Spelling and layout are shown as a stage heading with groups under it
(see groups.py); every other stage is one heading and its findings.
"""

import json
import shutil
from pathlib import Path

from .differences import describe, marked
from .groups import LAST, SPELLING_GROUPS, Group, Item
from .run import Located, Run
from .terminal import Style, display_path, heading, plural, snippet

__all__ = ["Style", "as_json", "display_path", "dump_json", "print_report", "print_summary"]

#: Spelling's groups shown under its heading; LAST comes after every stage.
_SPELLING_KEYS = {key for key, _, _ in SPELLING_GROUPS} - {LAST} | {"spelling"}


def print_report(run: Run, groups: list[Group], style: Style, cwd: Path) -> None:
    """The whole report for one file, ending with the summary."""
    width = min(shutil.get_terminal_size((100, 20)).columns, 120)
    _Printer(run, groups, style, display_path(run.path, cwd), width).report()
    print_summary(run, groups, style)


class _Columns:
    """Widths shared by every row of one report, measured on plain text."""

    def __init__(self, path: str, groups: list[Group], width: int):
        items = [item for g in groups for item in g.items]
        words = [item for item in items if item.word]
        self.where = max((len(item.uses[0].where(path)) for item in items), default=0)
        self.word = min(22, max((len(item.word) for item in words), default=0))
        self.reason = max((len(item.reason) for item in words), default=0)
        # Context sits under the word, unless a long location (an absolute
        # path) would leave it too little room: then a fixed indent.
        self.indent = " " * (self.where + 4 if self.where + 4 <= width * 0.4 else 4)


class _Printer:
    """Prints one file's groups; a stage split into groups gets one heading."""

    def __init__(self, run: Run, groups: list[Group], style: Style, path: str, width: int):
        self.run, self.groups, self.style = run, groups, style
        self.path, self.width = path, width
        self.columns = _Columns(path, groups, width)
        self.headed: set[str] = set()   # stages split into groups, heading printed

    def report(self) -> None:
        print()
        print(f"{self.style.bold('tex-check')}  {self.style.cyan(self.path)}")
        print()
        for group in self.groups:
            if group.key == LAST:
                self._last(group)
            elif group.section:
                self._grouped(group, group.section, self._section_heading, self._finding, "finding")
            elif group.key in _SPELLING_KEYS:
                self._grouped(group, "spelling", self._spelling_heading, self._word, "word")
            else:
                self._stage(group)

    # ── headings ──

    def _heading(self, title: str, blurb: str, name: str, count: str, n: int, hidden: int) -> None:
        """A stage's heading, its notes, and "nothing found" if so."""
        s = self.style
        print(heading(title, blurb, count, s, self.width, s.count(n)))
        if name == "spelling":
            print_spelling_note(self.run.stats.get(name, {}), s)
        elif name == "layout":
            print_layout_note(self.run.stats.get(name, {}), s)
        if hidden:
            print(f"  {s.dim(f'{hidden} marked OK in tex-check-done.jsonl')}")
        if not n:
            print(f"  {s.dim('nothing found')}")

    def _skipped(self, title: str, blurb: str, why: str) -> None:
        print(heading(title, blurb, "skipped", self.style, self.width))
        print(f"  {self.style.yellow('skipped:')} {why}")
        print()

    # ── a stage split into groups (spelling, layout) ──

    def _grouped(self, group: Group, stage: str, print_heading, print_item, unit: str) -> None:
        """The stage's heading before its first group, then this group."""
        if stage not in self.headed:
            self.headed.add(stage)
            print_heading(stage)
        if group.items and group.key != "spelling":
            s = self.style
            count = plural(len(group.items), unit)
            print(f"  {s.bold(group.title)}  {s.dim(group.blurb + ' ·')} {s.yellow(count)}")
            for item in group.items:
                print_item(item)
            print()

    def _section_heading(self, section: str) -> None:
        stage = next(s for s, _ in self.run.results if section == s.TITLE)
        mine = [g for g in self.groups if g.section == section]
        n = sum(len(g.items) for g in mine)
        self._heading(stage.TITLE, stage.BLURB, stage.NAME, str(n), n, sum(g.hidden for g in mine))
        print()

    def _spelling_heading(self, _: str) -> None:
        stage, outcome = next((s, o) for s, o in self.run.results if s.NAME == "spelling")
        if isinstance(outcome, str):
            self._skipped(stage.TITLE, stage.BLURB, outcome)
            return
        label, words = spelling_count(self.groups)
        hidden = sum(g.hidden for g in self.groups if g.key in _SPELLING_KEYS)
        self._heading(stage.TITLE, stage.BLURB, stage.NAME, label, words, hidden)
        print()

    # ── any other stage: one heading, its findings under it ──

    def _stage(self, group: Group) -> None:
        if group.skipped is not None:
            self._skipped(group.title, group.blurb, group.skipped)
            return
        n = len(group.items)
        self._heading(group.title, group.blurb, group.key, str(n), n, group.hidden)
        for item in group.items:
            self._finding(item)
        print()

    def _last(self, group: Group) -> None:
        """Spelling's least likely mistakes, after every stage, under a heading of their own."""
        n = len(group.items)
        self._heading(group.title, group.blurb, LAST, plural(n, "word"), n, group.hidden)
        for item in group.items:
            self._word(item)
        print()

    # ── rows ──

    def _where(self, item: Item) -> str:
        return self.style.dim(item.uses[0].where(self.path).ljust(self.columns.where))

    def _context(self, item: Item) -> None:
        indent = self.columns.indent
        print(f"{indent}{snippet(self.run.source, item.uses[0], self.style, self.width - len(indent))}")

    def _finding(self, item: Item) -> None:
        note = f"  {self.style.yellow('(' + item.note + ')')}" if item.note else ""
        print(f"  {self._where(item)}  {item.message}{note}")
        self._context(item)

    def _word(self, item: Item) -> None:
        """A misspelt word: reason, suggestions, context, its other lines."""
        s, c = self.style, self.columns
        count = f"×{len(item.uses)}" if len(item.uses) > 1 else ""
        print(f"  {self._where(item)}  {s.red(item.word.ljust(c.word))} {s.dim(count.ljust(4))} "
              f"{s.yellow(item.reason.ljust(c.reason))}  {s.cyan('→')} {_suggestions(item, s)}")
        self._context(item)
        if others := sorted({use.line for use in item.uses[1:]} - {item.uses[0].line}):
            shown = ", ".join(map(str, others[:8])) + (f" +{len(others) - 8}" if len(others) > 8 else "")
            label = "also on line" + ("s " if len(others) > 1 else " ")
            print(f"{c.indent}{s.dim(label + shown)}")


def spelling_count(groups: list[Group]) -> tuple[str, int]:
    """Spelling counts words, not uses: "213 words (304 uses)"."""
    items = [item for g in groups if g.key in _SPELLING_KEYS for item in g.items]
    words, uses = len(items), sum(len(item.uses) for item in items)
    return plural(words, "word") + (f" ({uses} uses)" if uses != words else ""), words


def underline_changes(word: str, suggestion: str, style: Style) -> str:
    """The suggestion with the letters that differ from the word underlined."""
    return "".join(style.underline(text) if changed else text
                   for text, changed in marked(word, suggestion))


def _suggestions(item: Item, style: Style) -> str:
    """aspell's suggestions, changed letters underlined, and the first one's
    difference said in words: "Ecclesall (missing a c)"."""
    if not item.suggestions:
        return "no suggestions"
    shown = [underline_changes(item.word, s, style) for s in item.suggestions]
    if difference := describe(item.word, item.suggestions[0]):
        shown[0] += f" {style.dim('(' + difference + ')')}"
    return ", ".join(shown)


def print_layout_note(stats: dict, style: Style) -> None:
    """Caveats about the PDF the layout checks read."""
    if stats.get("stale"):
        print(f"  {style.yellow('note:')} {style.dim('the PDF is older than the .tex: typeset it again')}")
    if n := stats.get("unmatched"):
        print(f"  {style.dim(f'{n} not matched to the source (contents, footnotes, or text changed since)')}")


def print_spelling_note(stats: dict, style: Style) -> None:
    """Tips for a fuller spelling check, or how many place names passed."""
    if not stats:
        return
    if not stats.get("gazetteer"):
        print(f"  {style.yellow('tip:')} {style.dim('run')} tex-check --update-places "
              f"{style.dim('to stop place names being flagged')}")
    elif n := stats.get("places"):
        words = plural(n, "capitalised word")
        print(f"  {style.dim(f'{words} accepted as place names (GeoNames)')}")
    if stats.get("british") is False:
        print(f"  {style.yellow('tip:')} {style.dim('run')} tex-check --update-dictionary "
              f"{style.dim('for a larger British dictionary as a second opinion')}")


def print_summary(run: Run, groups: list[Group], style: Style) -> None:
    """One row per stage, with its groups' counts indented under it."""
    rows: list[tuple[str, str, object]] = []
    by_key = {group.key: group for group in groups}
    for stage, outcome in run.results:
        if isinstance(outcome, str):
            rows.append((stage.TITLE, "skipped", style.yellow))
            continue
        if stage.NAME == "spelling":
            label, n = spelling_count(groups)
            mine = [g for g in groups if g.key in _SPELLING_KEYS - {"spelling"}]
        elif stage.NAME in by_key:
            mine, n = [], len(by_key[stage.NAME].items)
            label = str(n)
        else:  # split into groups, like spelling
            mine = [g for g in groups if g.section == stage.TITLE]
            n = sum(len(g.items) for g in mine)
            label = str(n)
        rows.append((stage.TITLE, label, style.count(n)))
        rows += [("  " + g.title, str(len(g.items)), style.yellow) for g in mine if g.items]
    if LAST in by_key and by_key[LAST].items:
        rows.append((by_key[LAST].title, str(len(by_key[LAST].items)), style.yellow))
    title_width = max(len(title) for title, _, _ in rows)
    print(style.bold("Summary"))
    for title, value, colour in rows:
        print(f"  {title.ljust(title_width)}  {colour(value)}")
    print()


def as_json(run: Run, groups: list[Group]) -> list[dict]:
    """One flat record per use of every finding, plus one per skipped stage."""
    out = []
    for group in groups:
        if group.skipped is not None:
            out.append({"file": str(run.path), "stage": group.key, "skipped": group.skipped})
        else:
            out += [_json_record(run, group, item, loc) for item in group.items for loc in item.uses]
    return out


def _json_record(run: Run, group: Group, item: Item, loc: Located) -> dict:
    f = loc.finding
    return {
        "file": str(run.path), "stage": item.stage, "group": group.key,
        "line": loc.line, "column": loc.col,
        "end_line": loc.end_line, "end_column": loc.end_col,
        "message": f.message, "note": item.note or f.note,
        "suggestions": f.suggestions, "text": loc.text,
    }


def dump_json(items: list[dict]) -> None:
    print(json.dumps(items, ensure_ascii=False, indent=2))
