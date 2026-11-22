# OK marks, done log and reasons: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Per-use OK marks and an undoable log of every action, kept beside
the book, plus a plain-words reason for each spelling finding.

**Architecture:** `groups.reason` adds reasons; `donelog.py` owns the
append-only log and derives OK marks; `group_findings` takes the marks and
leaves matching uses out, so terminal, `--json` and browser agree. The web
session logs every action and undoes from the log.

**Tech Stack:** Python 3.12 stdlib, pytest, hand-written JS.

**Spec:** `docs/superpowers/specs/2026-11-22-ok-marks-done-log-and-reasons-design.md`

## Global Constraints

- Log file: `tex-check-done.jsonl` beside the .tex; append-only; undo is an entry.
- OK marks match on stage + flagged text + source-line context, never line number.
- No runtime dependencies; British English; terminal output per `scripts/CLAUDE.md`.
- Work continues on `feature/grouped-web-view`.

## Review Focus

1. A line in the log that is not valid JSON (hand-edited, half-written) is skipped, not fatal (Task 2 `test_bad_lines_are_skipped`).
2. Undoing an add whose word was already in the list before (append returned False) must not remove the earlier entry (Task 2 `test_undo_add_keeps_a_word_that_was_already_there`).
3. Undoing twice is harmless (Task 4 `test_undo_twice_is_harmless`).
4. Two identical sentences in the book: an OK on one also covers the other. Accepted and documented (same text, same context).
5. A word whose every use is OK'd disappears from its group and counts (Task 3 `test_all_uses_ok_removes_the_item`).

---

### Task 1: Reasons

**Files:** Modify `src/texcheck/groups.py` (`Item.reason: str`, `reason(word, suggestions, note) -> str`), `src/texcheck/report.py` (show it); Test `tests/test_groups.py`.

- [ ] Tests: `test_reason_missing_apostrophe` (Ziggys, ["Ziggy's", "Ziggy"]), `test_reason_capitals` (ok, ["OK"]), `test_reason_one_word` (heathland, ["heath land"] → "usually two words"), `test_reason_hyphen`, `test_reason_accent` (dénouement), `test_reason_american` (practiced → practised; colour forms), `test_reason_default` (lyrca → "not in the dictionary"), `test_macro_slip_reason`. Run: FAIL.
- [ ] Implement; non-spelling items get `reason = ""`. Terminal word line: `word  ×n  reason  → suggestions`.
- [ ] `uv run pytest -q`: PASS. Commit.

### Task 2: The action log

**Files:** Create `src/texcheck/donelog.py`; modify `src/texcheck/wordlists.py` (`remove_word(path, word) -> bool`); Test `tests/test_donelog.py`.

**Interfaces:**
- `LOG_NAME = "tex-check-done.jsonl"`, `log_file(tex: Path) -> Path`
- `@dataclass Entry: id, at, action, stage, word, message, text, context, line, target, added` (`added`: whether an add actually wrote the word)
- `record(path, **fields) -> Entry`; `entries(path) -> list[Entry]` (bad lines skipped); `undone(entries) -> set[str]`
- `ok_marks(path) -> set[tuple[str, str, str]]`: (stage, text, context) of OK entries not undone
- `fingerprint(stage, text, context) -> tuple[str, str, str]`

- [ ] Tests: `test_record_and_read_back`, `test_bad_lines_are_skipped`, `test_ok_marks_exclude_undone`, `test_remove_word`, `test_undo_add_keeps_a_word_that_was_already_there` (helper-level: `added=False` entries are not removed on undo — asserted in Task 4). Run: FAIL.
- [ ] Implement. Commit.

### Task 3: OK marks hide findings everywhere

**Files:** Modify `src/texcheck/groups.py` (`group_findings(run, ok=frozenset())`), `src/texcheck/report.py` (dim "N marked OK" line), `src/texcheck/cli.py` (reads the log); Test `tests/test_groups.py`, `tests/test_report.py`.

- [ ] Tests: `test_ok_mark_hides_one_use` (lyrca ×2, one marked → item has one use), `test_all_uses_ok_removes_the_item`, `test_report_says_how_many_ok`. Run: FAIL.
- [ ] Implement: context for matching is `before + hit + after` from `snippet_parts(source, loc, 110)`; `group_findings` counts hidden uses in `Group.hidden`. Commit.

### Task 4: Session and routes

**Files:** Modify `src/texcheck/web/session.py`, `src/texcheck/web/routes.py`; Test `tests/test_web_session.py`, `tests/test_web_routes.py`.

**Interfaces:**
- `Session.ok(use_id) -> None`; `Session.done() -> list[dict]` (newest first, with `undone`); `Session.undo(entry_id) -> None`
- `add_word` now records a `book`/`personal` entry with `added`.
- Payload: items gain `reason`; uses unchanged.
- Routes: `POST /api/ok {"use"}`, `GET /api/done`, `POST /api/undo {"entry"}` (unknown → 404).

- [ ] Tests: `test_ok_hides_use_and_logs`, `test_undo_ok_brings_it_back`, `test_undo_add_removes_word_and_rechecks`, `test_undo_add_keeps_a_word_that_was_already_there`, `test_undo_twice_is_harmless`, routes `test_ok_route`, `test_done_route`, `test_undo_unknown_is_404`. Run: FAIL.
- [ ] Implement: `_publish(run)` applies OK marks and late-added words; undo of OK re-publishes from the cached run; undo of an add removes the word (if `added`) and rechecks. Commit.

### Task 5: The page

**Files:** Modify `src/texcheck/web/static/{index.html,app.css,app.js}`.

- [ ] Each use is a row with context, Open, OK; item header has reason and Add buttons; Done view lists entries with Undo; keys `j`/`k` per use, `x` OK.
- [ ] Manual check on a copy of a second real book via the API (ok, done, undo) and `node --check`. Commit.

### Task 6: Docs

- [ ] README and CLAUDE.md: OK marks, the log, reasons. Commit.
