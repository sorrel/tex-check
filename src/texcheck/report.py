"""Lay findings out for reading in a terminal, or as JSON for other tools.

Every finding starts with `file:line:column`, the form iTerm (Cmd-click,
via Semantic History) and most editors' terminals recognise as a link.

Widths are measured on plain text and colour is applied afterwards; when
output is piped, or for --json, no colour is used at all.
"""

from __future__ import annotations

import json
import shutil
from collections import defaultdict

from .findings import Finding
from .prose import Prose, Source

CONTEXT = 38  # characters of context either side of a finding


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


class Located:
    """A finding with its source position worked out."""

    def __init__(self, f: Finding, prose: Prose, source: Source):
        self.finding = f
        self.start, self.end = prose.source_span(f.start, f.end)
        self.line, self.col = source.line_col(self.start)
        self.end_line, self.end_col = source.line_col(self.end)
        self.text = source.text[self.start : self.end]

    def where(self, path: str) -> str:
        return f"{path}:{self.line}:{self.col}"


def snippet(source: Source, loc: Located, style: Style, width: int) -> str:
    """The source line around a finding, with the finding highlighted."""
    line = source.line_text(loc.line)
    left = loc.col - 1
    right = min(len(line), left + max(1, loc.end - loc.start))
    room = max(20, (width - (right - left)) // 2)
    lo, hi = max(0, left - min(CONTEXT, room)), min(len(line), right + min(CONTEXT, room))

    before, hit, after = line[lo:left], line[left:right], line[right:hi]
    if not hit.strip():  # make whitespace visible
        hit = hit.replace(" ", "␣").replace("\t", "⇥")
    head = style.dim("…") if lo > 0 else ""
    tail = style.dim("…") if hi < len(line) else ""
    clean = lambda s: s.replace("\t", " ")
    return f"{head}{clean(before)}{style.red(clean(hit))}{clean(after)}{tail}"


def heading(title: str, blurb: str, count: str, style: Style, width: int, colour=None) -> str:
    plain_left = f"{title}  {blurb} "
    plain_right = f" {count}"
    rule = "─" * max(3, width - len(plain_left) - len(plain_right))
    colour = colour or style.yellow
    return f"{style.bold(title)}  {style.dim(blurb)} {style.dim(rule)} {colour(count)}"


def stage_count(stage, findings) -> tuple[str, int]:
    """What a stage's heading and summary show: spelling counts words, not uses."""
    if stage.NAME == "spelling":
        words = len({f.group for f in findings})
        uses = len(findings)
        label = f"{words} word{'s' if words != 1 else ''}"
        return (label + (f" ({uses} uses)" if uses != words else "")), words
    return str(len(findings)), len(findings)


def print_report(path, source, prose, results, style: Style, stats: dict | None = None) -> None:
    """results: list of (stage module, findings or error string)."""
    stats = stats or {}
    width = min(shutil.get_terminal_size((100, 20)).columns, 120)
    located_by_stage = {
        stage.NAME: sorted((Located(f, prose, source) for f in outcome), key=lambda l: (l.start, l.end))
        for stage, outcome in results if isinstance(outcome, list)
    }
    where_width = max(
        (len(loc.where(path)) for locs in located_by_stage.values() for loc in locs), default=0
    )

    print()
    print(f"{style.bold('tex-check')}  {style.cyan(str(path))}")
    print()

    for stage, outcome in results:
        if isinstance(outcome, str):
            print(heading(stage.TITLE, stage.BLURB, "skipped", style, width))
            print(f"  {style.yellow('skipped:')} {outcome}")
            print()
            continue
        located = located_by_stage[stage.NAME]
        label, n = stage_count(stage, outcome)
        print(heading(stage.TITLE, stage.BLURB, label, style, width, style.green if n == 0 else None))
        if stage.NAME == "spelling":
            print_spelling_note(stats.get("spelling", {}), style)
        if not located:
            print(f"  {style.dim('nothing found')}")
        elif stage.NAME == "spelling":
            print_spelling(located, path, source, style, width, where_width)
        else:
            indent = " " * (where_width + 4)
            for loc in located:
                note = f"  {style.yellow('(' + loc.finding.note + ')')}" if loc.finding.note else ""
                print(f"  {style.dim(loc.where(path).ljust(where_width))}  {loc.finding.message}{note}")
                print(f"{indent}{snippet(source, loc, style, width - len(indent))}")
        print()

    print_summary(results, style)


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


def print_spelling(located, path, source, style, width, where_width) -> None:
    groups: dict[str, list[Located]] = defaultdict(list)
    for loc in located:
        groups[loc.finding.group].append(loc)
    word_width = min(22, max(len(w) for w in groups))
    indent = " " * (where_width + 4)
    for word, locs in sorted(groups.items(), key=lambda kv: kv[1][0].start):
        first = locs[0]
        sugg = ", ".join(first.finding.suggestions) or "no suggestions"
        count = f"×{len(locs)}" if len(locs) > 1 else ""
        print(
            f"  {style.dim(first.where(path).ljust(where_width))}  "
            f"{style.red(word.ljust(word_width))} {style.dim(count.ljust(4))} "
            f"{style.cyan('→')} {sugg}"
        )
        print(f"{indent}{snippet(source, first, style, width - len(indent))}")
        others = sorted({l.line for l in locs[1:]} - {first.line})
        if others:
            shown = ", ".join(map(str, others[:8])) + (f" +{len(others) - 8}" if len(others) > 8 else "")
            print(f"{indent}{style.dim('also on line' + ('s ' if len(others) > 1 else ' ') + shown)}")


def print_summary(results, style) -> None:
    rows = []
    for stage, outcome in results:
        if isinstance(outcome, str):
            rows.append((stage.TITLE, "skipped", style.yellow))
        else:
            label, n = stage_count(stage, outcome)
            rows.append((stage.TITLE, label, style.green if n == 0 else style.yellow))
    title_width = max(len(t) for t, _, _ in rows)
    print(style.bold("Summary"))
    for title, value, colour in rows:
        print(f"  {title.ljust(title_width)}  {colour(value)}")
    print()


def as_json(path, source, prose, results) -> list[dict]:
    out = []
    for stage, outcome in results:
        if isinstance(outcome, str):
            out.append({"file": str(path), "stage": stage.NAME, "skipped": outcome})
            continue
        for f in outcome:
            loc = Located(f, prose, source)
            out.append({
                "file": str(path), "stage": stage.NAME,
                "line": loc.line, "column": loc.col,
                "end_line": loc.end_line, "end_column": loc.end_col,
                "message": f.message, "note": f.note,
                "suggestions": f.suggestions, "text": loc.text,
            })
    return out


def dump_json(items: list[dict]) -> None:
    print(json.dumps(items, ensure_ascii=False, indent=2))
