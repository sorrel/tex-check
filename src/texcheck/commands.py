"""What the LaTeX reader does with each command and environment, by name.

Teach the reader a new macro by adding it to a table here, not by writing
code. Commands not listed anywhere vanish, and any {group} after them is
read as ordinary text: that default suits \\emph, \\textit and most of a
document's own \\newcommand definitions.
"""

# Commands whose first N brace arguments are not prose and are thrown away.
DROP_ARGS = {
    "label": 1, "ref": 1, "pageref": 1, "eqref": 1, "cite": 1, "citep": 1,
    "citet": 1, "nocite": 1, "includegraphics": 1, "input": 1, "include": 1,
    "usepackage": 1, "url": 1, "href": 1, "hyperref": 1, "index": 1,
    "hyphenation": 1, "vspace": 1, "hspace": 1, "vskip": 0, "pagestyle": 1,
    "thispagestyle": 1, "pagenumbering": 1, "chapterstyle": 1,
    "setsecheadstyle": 1, "setbeforesecskip": 1, "setaftersecskip": 1,
    "setheadfoot": 2, "setcounter": 2, "addtocounter": 2, "setlength": 2,
    "addtolength": 2, "newcommand": 2, "renewcommand": 2, "providecommand": 2,
    "fontsize": 2, "color": 1, "textcolor": 1, "colorbox": 1, "pagecolor": 1,
    "emoji": 1, "rule": 2, "raisebox": 1, "resizebox": 2, "scalebox": 1,
    "makebox": 0, "parbox": 1, "settowidth": 2, "def": 0,
}

# Commands whose argument is set off from the running text, like a heading.
HEADINGS = {
    "part", "chapter", "section", "subsection", "subsubsection", "paragraph",
    "subparagraph", "caption", "title", "author", "date", "attrib",
    "itattrib", "epigraph",
}

# Of those, the ones that are titles rather than text set apart (an epigraph).
TITLES = {
    "part", "chapter", "section", "subsection", "subsubsection", "paragraph",
    "subparagraph", "title",
}

# Commands whose argument is a footnote-like aside, checked separately.
NOTES = {"footnote", "footnotetext", "marginpar", "endnote"}

# Commands that produce a break in the text.
BREAKS = {
    "par", "newline", "linebreak", "newpage", "clearpage", "cleardoublepage",
    "pagebreak", "item", "bigbreak", "medbreak", "smallbreak", "bigskip",
    "medskip", "smallskip", "vfill", "blankpage", "maketitle",
    "tableofcontents", "mainmatter", "frontmatter", "backmatter",
}

# Commands whose argument is printed in bold: proper names, in this house style.
BOLD = {"textbf", "italic", "textsc"}

# Commands that wrap their argument in quotation marks.
QUOTES = {"say": ("“", "”"), "bsq": ("‘", "’"), "enquote": ("“", "”")}

# Commands that stand for a piece of text.
MACROS = {
    "ldots": "…", "dots": "…", "textellipsis": "…", "LaTeX": "LaTeX",
    "TeX": "TeX", "copyright": "©", "textendash": "–", "textemdash": "—",
    "textquoteright": "’", "textquoteleft": "‘", "ss": "ß", "ae": "æ",
    "oe": "œ", "AE": "Æ", "OE": "Œ", "o": "ø", "O": "Ø", "aa": "å", "l": "ł",
    "pounds": "£", "textpounds": "£", "euro": "€", "S": "§", "P": "¶",
}

#: Every command the extractor knows by name, three letters or more. Used to
#: spot a missing backslash (`bsq{word}` read as "bsqword"); single letters
#: such as \o would match the start of half the dictionary.
KNOWN_COMMANDS = frozenset(
    name for name in (*DROP_ARGS, *HEADINGS, *NOTES, *BREAKS, *BOLD, *QUOTES, *MACROS)
    if len(name) >= 3 and name.isalpha()
)

# Environments whose whole content is skipped.
SKIP_ENVS = {
    "verbatim", "Verbatim", "lstlisting", "minted", "comment", "equation",
    "equation*", "align", "align*", "gather", "gather*", "multline",
    "multline*", "displaymath", "math", "tikzpicture", "picture",
}

# Environments that take non-prose arguments after \begin{..}.
ENV_ARGS = {
    "tabular": 1, "tabular*": 2, "tabularx": 2, "longtable": 1, "minipage": 1,
    "multicols": 1, "multicols*": 1, "wrapfigure": 2, "adjustwidth": 2,
    "list": 2,
}
