# Second-opinion dictionaries and spelled-out letter differences

Design. 22 November 2026. Extends the grouped-report and OK-marks designs.

## Why

aspell's en_GB-ise dictionary is small: good British words (synthesisers,
accoutrement, heathland, laundrette) crowd the likely typos. And the user
finds near-identical spellings hard to tell apart (an extra "l" especially),
so a list of suggestions alone does not show what is wrong.

## Approaches

Tested against words from real books:

- **macOS's British spellchecker** (NSSpellChecker, en_GB): broadest; rejects
  American forms; but also accepts words "learned" on this Mac and a few
  slips (Ziggys, ok). No install.
- **SCOWL size 70, GB -ise** (wordlist.aspell.net): strictest (rejects
  practiced); misses newer compounds. 1.6 MB download, permissive licence.
- LibreOffice's en_GB via hunspell: thorough, but a second spellchecker to
  install and maintain, and mostly overlaps macOS. Not now.

Chosen: **both macOS and SCOWL, as second opinions**, never as the judge.

## Design

- `tex-check --update-dictionary` downloads SCOWL (size 70, GB -ise,
  variants level 1) to `~/.local/share/tex-check/british.txt`, header
  stripped. `--no-british` / `--no-macos` turn either off.
- After aspell, the words it rejects are put to both: SCOWL by lookup, macOS
  in one bounded `osascript` call (AppleScriptObjC, NSSpellChecker en_GB),
  skipped off macOS or on failure.
- A word either accepts goes to a new last group, **Known to other
  dictionaries**, noted "in the larger British list", "known to macOS" or
  both, unless it has a strong reason (missing apostrophe, capitals differ,
  American spelling?, missing backslash), which keeps it where it was.
- **Letter differences:** every suggestion carries a plain description of
  how it differs from the word, for differences of up to two edits:
  "missing a c", "extra l", "i and e swapped", "a for e", "missing
  apostrophe", "capital L", "space added", "hyphen added". The changed letters
  are marked: underlined in the terminal, bold, underlined and coloured in
  the browser. The terminal shows the top suggestion's description.
