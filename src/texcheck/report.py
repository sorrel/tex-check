"""Lay findings out for reading in a terminal, or as JSON for other tools.

Every finding starts with `file:line:column`, the form iTerm (Cmd-click,
via Semantic History) and most editors' terminals recognise as a link. The
file is shown relative to the current directory when it lies inside it,
which keeps the column short; iTerm resolves it against the shell's
directory, so the link still works.

Spelling is shown in groups (see groups.py), likely typos first.

Widths are measured on plain text and colour is applied afterwards; when
output is piped, or for --json, no colour is used at all.
"""

from __future__ import annotations

import json
import shutil
import os
from pathlib import Path

from .groups import SPELLING_GROUPS, Group, Item
from .prose import Source
from .run import Located, Run, snippet_parts



class Style:
    def __init__(self, colour: bool):
        self.colour = colour

    def _wrap(self, code: str, text: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.colour and text else text

    def bold(self, t): return self._wrap("1", t)
    def dim(self, t): return self._wrap("2", t)
    def red(self, t): return self._wrap("1;91", t)
    def yellow(self, t): return self._wrap("93", t)
    def cyan(self, t): return self._wrap("96", t)
    def green(self, t): return self._wrap("92", t)


def display_path(path: Path, cwd: Path) -> str:
    """`path` relative to `cwd` when it lies inside it, else absolute."""
    absolute = Path(os.path.abspath(path))
    try:
        return str(absolute.relative_to(Path(os.path.abspath(cwd))))
    except ValueError:
        return str(absolute)


def snippet(source: Source, loc: Located, style: Style, width: int) -> str:
    """The source line around a finding, with the finding highlighted."""
    cut_left, before, hit, after, cut_right = snippet_parts(source, loc, width)
    head = style.dim("…") if cut_left else ""
    tail = style.dim("…") if cut_right else ""
    return f"{head}{before}{style.red(hit)}{after}{tail}"


def heading(title: str, blurb: str, count: str, style: Style, width: int, colour=None) -> str:
    plain_left = f"{title}  {blurb} "
    plain_right = f" {count}"
    rule = "─" * max(3, width - len(plain_left) - len(plain_right))
    colour = colour or style.yellow
    return f"{style.bold(title)}  {style.dim(blurb)} {style.dim(rule)} {colour(count)}"


_SPELLING_KEYS = {key for key, _, _ in SPELLING_GROUPS} | {"spelling"}


def spelling_count(groups: list[Group]) -> tuple[str, int]:
    """Spelling counts words, not uses: "213 words (304 uses)"."""
    items = [item for g in groups if g.key in _SPELLING_KEYS for item in g.items]
    words, uses = len(items), sum(len(item.uses) for item in items)
    label = f"{words} word{'s' if words != 1 else ''}"
    return label + (f" ({uses} uses)" if uses != words else ""), words


def ok_note(hidden: int, style: Style) -> None:
    """The dim line saying how many findings are marked OK, if any."""
    if hidden:
        print(f"  {style.dim(f'{hidden} marked OK in tex-check-done.jsonl')}")


class _Layout:
    """Widths shared by every row of one report, measured on plain text."""

    def __init__(self, path: str, groups: list[Group], width: int):
        self.path = path
        self.width = width
        self.where = max(
            (len(item.uses[0].where(path)) for g in groups for item in g.items), default=0
        )
        words = [item.word for g in groups for item in g.items if item.word]
        self.word = min(22, max(map(len, words), default=0))
        self.reason = max((len(i.reason) for g in groups for i in g.items if i.word), default=0)
        # Context sits under the word, unless a long location (an absolute
        # path) would leave it too little room: then a fixed indent.
        self.indent = " " * (self.where + 4 if self.where + 4 <= width * 0.4 else 4)


def print_report(run: Run, groups: list[Group], style: Style, cwd: Path) -> None:
    width = min(shutil.get_terminal_size((100, 20)).columns, 120)
    shown = display_path(run.path, cwd)
    layout = _Layout(shown, groups, width)
    spelling_keys = {key for key, _, _ in SPELLING_GROUPS} | {"spelling"}

    print()
    print(f"{style.bold('tex-check')}  {style.cyan(shown)}")
    print()

    spelling_started = False
    for group in groups:
        if group.key in spelling_keys:
            if not spelling_started:
                spelling_started = True
                _print_spelling_heading(run, groups, style, width)
            if group.key != "spelling" and group.items:
                _print_subheading(group, style)
                for item in group.items:
                    _print_word(item, run.source, style, layout)
                print()
            continue
        if group.skipped is not None:
            print(heading(group.title, group.blurb, "skipped", style, width))
            print(f"  {style.yellow('skipped:')} {group.skipped}")
            print()
            continue
        n = len(group.items)
        print(heading(group.title, group.blurb, str(n), style, width, style.green if n == 0 else None))
        ok_note(group.hidden, style)
        if not group.items:
            print(f"  {style.dim('nothing found')}")
        for item in group.items:
            _print_finding(item, run.source, style, layout)
        print()

    print_summary(run, groups, style)


def _print_spelling_heading(run: Run, groups: list[Group], style: Style, width: int) -> None:
    stage, outcome = next((s, o) for s, o in run.results if s.NAME == "spelling")
    if isinstance(outcome, str):
        print(heading(stage.TITLE, stage.BLURB, "skipped", style, width))
        print(f"  {style.yellow('skipped:')} {outcome}")
        print()
        return
    label, words = spelling_count(groups)
    print(heading(stage.TITLE, stage.BLURB, label, style, width,
                  style.green if not words else None))
    print_spelling_note(run.stats.get("spelling", {}), style)
    ok_note(sum(g.hidden for g in groups if g.key in _SPELLING_KEYS), style)
    if not words:
        print(f"  {style.dim('nothing found')}")
    print()


def _print_subheading(group: Group, style: Style) -> None:
    n = len(group.items)
    count = f"{n} word{'s' if n != 1 else ''}"
    print(f"  {style.bold(group.title)}  {style.dim(group.blurb + ' ·')} {style.yellow(count)}")


def _print_finding(item: Item, source: Source, style: Style, layout: _Layout) -> None:
    loc = item.uses[0]
    note = f"  {style.yellow('(' + item.note + ')')}" if item.note else ""
    print(f"  {style.dim(loc.where(layout.path).ljust(layout.where))}  {item.message}{note}")
    print(f"{layout.indent}{snippet(source, loc, style, layout.width - len(layout.indent))}")


def _print_word(item: Item, source: Source, style: Style, layout: _Layout) -> None:
    first = item.uses[0]
    sugg = ", ".join(item.suggestions) or "no suggestions"
    count = f"×{len(item.uses)}" if len(item.uses) > 1 else ""
    print(
        f"  {style.dim(first.where(layout.path).ljust(layout.where))}  "
        f"{style.red(item.word.ljust(layout.word))} {style.dim(count.ljust(4))} "
        f"{style.yellow(item.reason.ljust(layout.reason))}  {style.cyan('→')} {sugg}"
    )
    print(f"{layout.indent}{snippet(source, first, style, layout.width - len(layout.indent))}")
    others = sorted({use.line for use in item.uses[1:]} - {first.line})
    if others:
        shown = ", ".join(map(str, others[:8])) + (f" +{len(others) - 8}" if len(others) > 8 else "")
        label = "also on line" + ("s " if len(others) > 1 else " ")
        print(f"{layout.indent}{style.dim(label + shown)}")


def print_spelling_note(stats: dict, style: Style) -> None:
    if not stats:
        return
    if not stats.get("gazetteer"):
        print(f"  {style.yellow('tip:')} {style.dim('run')} tex-check --update-places "
              f"{style.dim('to stop place names being flagged')}")
    elif stats.get("places"):
        n = stats["places"]
        words = "word" if n == 1 else "words"
        print(f"  {style.dim(f'{n} capitalised {words} accepted as place names (GeoNames)')}")


def print_summary(run: Run, groups: list[Group], style: Style) -> None:
    rows: list[tuple[str, str, object]] = []
    by_key = {group.key: group for group in groups}
    for stage, outcome in run.results:
        if isinstance(outcome, str):
            rows.append((stage.TITLE, "skipped", style.yellow))
            continue
        if stage.NAME == "spelling":
            label, n = spelling_count(groups)
            rows.append((stage.TITLE, label, style.green if n == 0 else style.yellow))
            for group in groups:
                if group.key in _SPELLING_KEYS - {"spelling"} and group.items:
                    rows.append(("  " + group.title, str(len(group.items)), style.yellow))
            continue
        n = len(by_key[stage.NAME].items)
        rows.append((stage.TITLE, str(n), style.green if n == 0 else style.yellow))
    title_width = max(len(title) for title, _, _ in rows)
    print(style.bold("Summary"))
    for title, value, colour in rows:
        print(f"  {title.ljust(title_width)}  {colour(value)}")
    print()


def as_json(run: Run, groups: list[Group]) -> list[dict]:
    out = []
    for group in groups:
        if group.skipped is not None:
            out.append({"file": str(run.path), "stage": group.key, "skipped": group.skipped})
            continue
        for item in group.items:
            for loc in item.uses:
                f = loc.finding
                out.append({
                    "file": str(run.path), "stage": item.stage, "group": group.key,
                    "line": loc.line, "column": loc.col,
                    "end_line": loc.end_line, "end_column": loc.end_col,
                    "message": f.message, "note": item.note or f.note,
                    "suggestions": f.suggestions, "text": loc.text,
                })
    return out


def dump_json(items: list[dict]) -> None:
    print(json.dumps(items, ensure_ascii=False, indent=2))
