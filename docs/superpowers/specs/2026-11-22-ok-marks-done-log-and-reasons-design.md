# OK marks, a done log with undo, and reasons

Design. 22 November 2026. Extends
`2026-11-22-grouped-report-and-web-view-design.md`.

## What the user wants

1. **Mark a finding OK**, one place at a time: "I need to check each one".
   OK means "this is fine here", not "add the word to a list".
2. **Remember every action** (OK, add for this book, add everywhere), so a
   wrong button press can be found again and undone.
3. **See why a word is flagged**, not only aspell's suggestions ("Ziggys":
   a missing apostrophe).

## Approaches

- **A. One append-only action log beside the book** (chosen):
  `tex-check-done.jsonl`. OK marks are derived from it, so marks and
  history cannot disagree. Undo is itself an entry in the log.
- B. Plain `tex-check-ok.txt` plus a separate history: hand-editable, but
  the two files can drift apart. Rejected for that reason.

## Design

### Reasons (`groups.reason`)

Every spelling item gets a one-line reason, worked out from the word and
aspell's suggestions, first match winning:

| Reason | When |
|---|---|
| `missing \ before \bsq?` | macro slip (existing note) |
| `missing apostrophe?` | a suggestion is the word with `'s`/`s'` (Ziggys → Ziggy's) |
| `capitals differ` | a suggestion differs only in case (ok → OK) |
| `usually one word` / `usually two words` / `usually hyphenated` | differs only by a space or hyphen |
| `accent differs` | differs only by an accent |
| `American spelling?` | a British form is a suggestion (-ize/-ise, -or/-our, -er/-re, -og/-ogue, practiced/practised) |
| `not in the dictionary` | anything else |

Other stages' message already is the reason. Terminal and browser show
**what · why · context** in that order.

### The action log (`donelog.py`)

`tex-check-done.jsonl` beside the .tex, one JSON object per line:

```
{"id": "…", "at": "2026-11-22T19:40", "action": "ok" | "book" | "personal",
 "stage": "spelling", "word": "Ziggys" | null, "message": "…",
 "text": "Ziggys", "context": "…liked Ziggys best: it…", "line": 786}
{"id": "…", "at": "…", "action": "undo", "target": "<id>"}
```

- An OK mark matches a finding by **stage + flagged text + its source-line
  context** (the same window the report shows), never by line number, so
  it survives edits elsewhere and lapses if that sentence is rewritten.
- Undoing an OK brings the finding back. Undoing an add removes the word
  from the list it went into (`wordlists.remove_word`) and re-checks.
- Undo is logged, not a deletion, so the log is the full history.

### Browser

- Each **use** is its own row: context, **Open in Texifier**, **OK**. A
  word leaves the page when every use is OK'd or the word is added to a
  list. The item header shows word, count, reason, suggestions, and the two
  Add buttons.
- A **Done** entry at the foot of the sidebar lists the log, newest first:
  time, action, word or message, line, and **Undo** (or "undone").
- Keys: `j`/`k` now move between uses; `x` marks the current use OK.

### Terminal and `--json`

OK'd findings are left out; a dim line under the heading says how many
("12 marked OK in tex-check-done.jsonl"). The reason is shown beside each
word.

## Left to the builder

Exact wording of reasons and labels; layout details.
