# tex-check

Proofreads the prose in LaTeX files, in stages: **repeats** ("the the"),
**punctuation** (double spaces, stray/doubled marks, words run together,
brackets), **spelling** (aspell, `en_GB-ise`), **grammar** (rule-based
heuristics). Stdlib only; aspell is the one external tool (`brew install aspell`).

## How it fits together

- `src/texcheck/prose.py`: the heart of it. Turns LaTeX into plain prose in
  which every character keeps its source offset, so checks are simple regexes
  over clean English and still report the true line:column. Command handling
  is table-driven (`DROP_ARGS`, `HEADINGS`, `NOTES`, `BOLD`, `QUOTES`, ...):
  teach it a new macro by adding it to a table, not by writing code.
  Unlisted commands vanish and their `{groups}` are read as text.
- `src/texcheck/checks/`: one module per stage (`NAME`, `TITLE`, `BLURB`,
  `run(prose, settings)`); order and registry in `checks/__init__.py`.
  New stage = new module + add it to `STAGES`.
- `report.py`: terminal layout (shared `scripts/` conventions) and `--json`.

## Decisions worth knowing

- `\\`, headings, environments and `\item` become paragraph breaks, so lyric
  lines (`\begin{words}{a\\b}`) are never joined or treated as one sentence.
- Footnotes are moved to the end of the prose and checked as their own
  paragraphs, so the sentence they interrupt reads whole.
- House style bolds names (`\textbf{The The}`): bold capitalised words are
  skipped by spelling (`--spell-bold` to include) and never count as repeats.
- Double spaces are reported only if adjacent in the source, not ones left
  behind by a removed command. TeX collapses them in print anyway.
- aspell's en_GB dictionaries lack some good words (among, learned, dreamt,
  ...): see `ALWAYS_ACCEPT` in `checks/spelling.py`.
- Place names: `tex-check --update-places [--countries GB,IE,FI]` builds
  `~/.local/share/tex-check/places.txt` (about 770,000 words, 8 MB) from
  GeoNames (CC BY 4.0): every named place in the given countries plus world
  towns of 1,000+ with their Latin-script alternate names (Trondhjem,
  Viipuri). Spelling accepts a word only if aspell rejects it, it is
  capitalised, and it is in the list. `'s` is stripped only from bases of 4+
  letters ("Her's" must not pass as the town of Her). `--no-places` turns
  it off. Add countries a text needs (e.g. FI for Finnish places).
- Locations print as `file:line:col` so iTerm can Cmd-click them.
- `tex-check-open FILE:LINE:COL` (`opener.py`) opens Texifier at a finding.
  Texifier 1.9.33 cannot be told a line: URL schemes only open files,
  AppleScript is the standard suite, File › Jump to (⇧⌘O) is Tag Search,
  setting AXSelectedTextRange is silently ignored, and ⌘G ignores the system
  find pasteboard. What works (tested 22 November 2026): put the shortest
  phrase from line:col that is unique in the file on the find pasteboard,
  focus the editor ("Text View" in "Editor"), ⌘F, Return, Escape. Focus
  matters: with the sidebar focused, ⌘F opens the sidebar search instead.
  Needs Accessibility for iTerm (granted). iTerm (3.7.9) Semantic History
  › Run command: `~/.local/bin/tex-check-open
  "\(semanticHistory.path)" "\(semanticHistory.lineNumber)"
  "\(semanticHistory.columnNumber)"`; non-.tex files fall back to `open`.
- Per-document word list: `tex-check-words.txt` beside the .tex file, read
  automatically. Bootstrap with `--list-unknown`, then prune the typos out.

## Not done yet

- A LanguageTool stage for real grammar checking. Local LanguageTool needs
  Java 17+ (this Mac has 11); the public API would send the text off the
  machine, so ask before choosing that.
- Near-repeats (the same longer word twice within a few lines) could
  become a stage.

## Running

    uv tool install --editable .     # once; gives `tex-check` on PATH
    tex-check document.tex --only repeats
    uv run pytest                    # tests
