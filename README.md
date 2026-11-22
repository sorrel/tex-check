# tex-check

Proofread the prose in a LaTeX file. LaTeX commands are never reported, and
every finding points at the line and column in your `.tex` source.

```
Repeated words  the same word twice in a row ──────────────────── 1
  chapter1.tex:212:31   “the the”
                        …she put the the kettle on and \textbf{waited}…
```

It runs in four stages, which you can run together or one at a time:

| Stage | Finds |
|---|---|
| `repeats` | the same word twice in a row, even across markup (`the \textbf{the}`) |
| `punctuation` | double spaces, space before a comma, `,,` `..` `.,`, words run together (`to\textbf{The}`), unbalanced brackets |
| `spelling` | unknown words, via aspell (British English by default), with suggestions |
| `grammar` | common slips: *a apple*, *could of*, *more then*, *its a*, *your welcome*, *her's*, lower-case *i* |

## Install

Needs Python 3.12+, [uv](https://docs.astral.sh/uv/), and aspell for the spelling stage:

```
brew install aspell
uv tool install --editable .
```

## Use

```
tex-check book.tex                      # every stage
tex-check book.tex --only repeats       # one stage (or a list: punct,spell)
tex-check book.tex --skip grammar
tex-check book.tex --json               # for other tools
tex-check book.tex --web                # in the browser (see below)
```

Spelling findings are sorted into groups, likely typos first: **Likely
typos**, **Other unknown words**, **In quotations** (dialogue, dialect),
**Foreign and bold phrases**, **Names** and **Variants** (*ok*/OK,
*heathland*/heath land). A missing backslash (`bsq{word}`) is caught as a
typo. Web addresses are not spell-checked.

Exit status: 0 nothing found, 1 findings, 2 error. `tex-check --help` lists
every option.

**Word lists.** Words aspell doesn't know but you do go in one of two lists,
one per line:

- `tex-check-words.txt` beside the `.tex` file, for that book's names,
  dialect and invented words. It travels with the book.
- `words.txt` in this repository, for good words everywhere (*heathland*,
  *Ericsson*). It is in git, so mistakes show in the history.
  `--no-personal-words` leaves it out.

To start a book's list:

```
tex-check book.tex --list-unknown > tex-check-words.txt   # then delete the real typos
```

To accept place names automatically, download a gazetteer once (about
8 MB, from [GeoNames](https://www.geonames.org)):

```
tex-check --update-places --countries GB,IE      # add any countries your text needs
```

Bold capitalised words (`\textbf{Name}`) and ALL-CAPS words are not
spell-checked: `--spell-bold` and `--spell-capitals` include them. Another
dictionary: `--dict en_US` (see `aspell dicts`).

## In the browser

```
tex-check book.tex --web            # opens http://127.0.0.1:8766/
tex-check book.tex --web --no-open --port 9000
```

The groups are down the side; each finding shows its context with **Open in
Texifier**, **Add for this book** and **Add everywhere** buttons (keys:
`j`/`k` to move, `o`, `b`, `e`). Save in Texifier and the page re-checks 30
seconds after the last save; each further save restarts the wait, or press
**Re-check now**. ctrl-C stops it; it also stops after 30 minutes with the
page closed.

The server listens on 127.0.0.1 only and every request needs the token in
the address it opens, so no other web page can press its buttons.

## Jump to a finding in Texifier (macOS, optional)

`tex-check-open book.tex:212:31` opens the file in
[Texifier](https://www.texifier.com) with the text at that point selected.
To get there by Cmd-clicking a location in an [iTerm](https://iterm2.com)
report:

1. System Settings › Privacy & Security › Accessibility: turn on **iTerm**.
2. iTerm › Settings › Profiles › Advanced › Semantic History › **Run command…**:

   ```
   ~/.local/bin/tex-check-open "\(semanticHistory.path)" "\(semanticHistory.lineNumber)" "\(semanticHistory.columnNumber)"
   ```

Files other than `.tex` still open in their default app.

## Development

```
uv run pytest
```

Each stage is one module in `src/texcheck/checks/`. `CLAUDE.md` explains the
design and the decisions behind it.

Place-name data © GeoNames, [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
Code under the MIT licence.
