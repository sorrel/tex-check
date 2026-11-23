# Near-repeats

Design. 22 November 2026. A new stage after `repeats`.

## Why

The same noticeable word twice within a few lines ("a beautiful morning…
the beautiful view") reads as a slip. `repeats` only catches neighbours.

## Approaches

- **Exact word, counted in words, on the prose (chosen):** simple, fast,
  works on the source.
- Stems ("beautiful"/"beautifully"): needs a stemmer, more noise. Later.
- Measured in typeset lines, from the PDF: truer to "a few lines", but
  belongs with the layout checks. Later.

## Design (the builder's calls, made while the user was away; all tunable)

- A word of **5+ letters** used again within **40 words** (about three
  printed lines) is flagged at its second use: "beautiful again, 12 words
  after the last". Neighbours are left to `repeats`.
- Case and a trailing `'s` are ignored; curly and straight apostrophes match.
- Left alone: a list of common words (would, there, through, something,
  ...); bold capitalised words (house-style names); a word capitalised in
  both uses (a name, as a rule).
- **Lyrics and headings:** `\\` and headings become paragraph breaks, so
  a short paragraph (under 12 words) is treated as a line of verse or a
  heading: repeats inside it are still checked, but the window never
  reaches across it, so a chorus is not flagged. Between two ordinary
  paragraphs the window carries on.
- OK marks work as for every stage (per place, from the done log).
