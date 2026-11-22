"""tex-check-open: open FILE at LINE[:COL] in Texifier, with the text there selected.

Texifier (1.9.33) cannot be told to open a file at a line:

* its URL schemes (`texpad:`, `texfier:`) only open files;
* its AppleScript dictionary is just the standard suite;
* File › Jump to (⇧⌘O) is Tag Search: sections and labels, not lines;
* it ignores attempts to set the editor's selection through Accessibility
  (AXSelectedTextRange reports settable, but nothing changes);
* Find Next (⌘G) does not take its text from the system find pasteboard.

What does work is the editor's own find bar, which takes its text from the
system find pasteboard when it opens. So this helper:

1. picks the shortest phrase, starting at LINE:COL, that occurs only once in
   the file (growing a word at a time, right first, then left);
2. opens the file (`open -a Texifier FILE`) and waits for a Texifier window
   whose editor shows it;
3. puts the phrase on the find pasteboard, focuses the editor, then presses
   ⌘F (find bar), Return (go to the match) and Escape (close the bar, keep
   the selection).

Step 3 needs Accessibility permission for whichever app runs this (iTerm).
It replaces whatever was last searched for in any app, as any Find does.
Tested November 2026. If a Texifier update renames the editor views
("Editor", "Text View"), FIND_SCRIPT needs adjusting.

Made for iTerm's Semantic History, so a Cmd-click on `document.tex:2891:304`
in a tex-check report jumps there. Files other than .tex open in their
default app.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

APP = "Texifier"
MIN_PHRASE = 12  # characters; shorter phrases are rarely unique
MAX_PHRASE = 80

FIND_SCRIPT = """
use framework "AppKit"
use scripting additions

on run argv
    set fileName to item 1 of argv
    set phrase to item 2 of argv
    set findBoard to current application's NSPasteboard's pasteboardWithName:(current application's NSPasteboardNameFind)
    findBoard's clearContents()
    findBoard's setString:phrase forType:(current application's NSPasteboardTypeString)

    tell application "{app}" to activate
    tell application "System Events"
        tell process "{app}"
            repeat 40 times -- up to about 4 seconds for the document to open
                repeat with docWindow in (windows whose subrole is "AXStandardWindow")
                    try
                        set editorPane to text area "Editor" of splitter group 1 of docWindow
                        if value of static text 1 of toolbar 1 of editorPane is fileName then
                            perform action "AXRaise" of docWindow
                            set editorView to text area "Text View" of scroll area 1 of editorPane
                            set focused of editorView to true
                            delay 0.1
                            keystroke "f" using command down
                            delay 0.3
                            key code 36 -- Return: go to the match
                            delay 0.3
                            key code 53 -- Escape: close the find bar, keep the selection
                            delay 0.1
                            return value of attribute "AXSelectedText" of editorView
                        end if
                    end try
                end repeat
                delay 0.1
            end repeat
            error "no Texifier window is showing " & fileName
        end tell
    end tell
end run
"""


def offset_of(text: str, line: int, col: int) -> int:
    """Character offset of 1-based line and column, clamped to the line."""
    lines = text.split("\n")
    line = max(1, min(line, len(lines)))
    start = sum(len(l) + 1 for l in lines[: line - 1])
    return start + max(0, min(col - 1, len(lines[line - 1])))


def unique_phrase(text: str, line: int, col: int = 1) -> str:
    """The shortest phrase from line:col (growing right, then left) found once in text.

    It stays on the one source line, grows a whole word at a time, and never
    starts or ends with a space. If nothing on the line is unique it returns
    the longest candidate, which at least reaches the right paragraph.
    """
    pos = offset_of(text, line, col)
    line_start = text.rfind("\n", 0, pos) + 1
    line_end = text.find("\n", pos)
    line_end = len(text) if line_end == -1 else line_end

    start = pos  # from the beginning of the word the column falls in
    while start > line_start and not text[start - 1].isspace():
        start -= 1
    end = start
    best = ""
    while True:
        if end < line_end:  # take the next word to the right
            end += 1
            while end < line_end and not text[end].isspace():
                end += 1
        elif start > line_start:  # out of room on the right: take a word to the left
            start -= 1
            while start > line_start and not text[start - 1].isspace():
                start -= 1
        else:
            return best
        phrase = text[start:end].strip()
        if len(phrase) > MAX_PHRASE:
            return best or phrase[:MAX_PHRASE]
        best = phrase
        if len(phrase) >= MIN_PHRASE and text.count(phrase) == 1:
            return phrase


def parse_location(args: list[str]) -> tuple[Path, int, int]:
    """Accept `FILE LINE [COL]` or `FILE:LINE[:COL]`."""
    parts = [a for a in args if a]
    if len(parts) == 1:
        bits = parts[0].split(":")
        numbers = []
        while bits and bits[-1].isdigit() and len(numbers) < 2:
            numbers.insert(0, int(bits.pop()))
        return Path(":".join(bits)), *(numbers + [1, 1])[:2]
    numbers = [int(p) for p in parts[1:3] if p.isdigit()]
    return Path(parts[0]), *(numbers + [1, 1])[:2]


def open_at(path: Path, line: int, col: int, app: str = APP, run=subprocess.run,
            text: str | None = None) -> str | None:
    """Open `path` in `app` with the text at line:col selected.

    `text` is the file as it was when line:col was worked out. The browser
    passes the text it checked, so a paragraph added above since then does
    not move the target: the phrase searched for is still the right one.
    Returns None on success, or a one-line reason it could not be done.
    `run` is subprocess.run, replaceable in tests.
    """
    if not path.is_file():
        return f"no such file: {path}"
    if path.suffix.lower() != ".tex":
        result = run(["open", str(path)], capture_output=True, text=True)
        return None if result.returncode == 0 else f"could not open {path.name}"

    if text is None:
        text = path.read_text(encoding="utf-8", errors="replace")
    phrase = unique_phrase(text, line, col)
    opened = run(["open", "-a", app, str(path)], capture_output=True, text=True)
    if opened.returncode != 0:
        return f"could not open {path.name} in {app}: {opened.stderr.strip()}"
    if not phrase:  # an empty line: opening the file is the best we can do
        return None
    result = run(
        ["osascript", "-e", FIND_SCRIPT.format(app=app), path.name, phrase],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        return None
    reason = f"opened {path.name}, but could not jump to line {line}: {result.stderr.strip()}"
    if "assistive access" in result.stderr or "-1719" in result.stderr:
        reason += (" Allow it in System Settings › Privacy & Security › Accessibility"
                   " (turn on iTerm).")
    return reason


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="tex-check-open",
        description="Open a .tex file in Texifier with the text at LINE:COL selected. "
        "Other files open in their default app.",
    )
    p.add_argument("location", nargs="+", help="FILE LINE [COL], or FILE:LINE[:COL]")
    p.add_argument("--app", default=APP, help=f"editor to use (default: {APP})")
    p.add_argument("--dry-run", action="store_true", help="print the search phrase; open nothing")
    args = p.parse_args(argv)

    path, line, col = parse_location(args.location)
    if args.dry_run:
        if not path.is_file():
            print(f"tex-check-open: no such file: {path}", file=sys.stderr)
            return 2
        print(unique_phrase(path.read_text(encoding="utf-8", errors="replace"), line, col))
        return 0
    error = open_at(path, line, col, app=args.app)
    if error:
        print(f"tex-check-open: {error}", file=sys.stderr)
        return 2 if error.startswith("no such file") else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
