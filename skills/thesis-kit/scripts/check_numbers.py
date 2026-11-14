#!/usr/bin/env python3
r"""Check that every number in a thesis chapter appears in its source papers.

A faithfulness check. A number in the chapter that no source contains is a
typo, a number taken from the wrong table row, or derived arithmetic.
Derived numbers (relative gains, differences, averages, conversions such as
0.727 -> 72.7%) are never in the source, so they show as UNSUPPORTED: the
caller decides whether each one is legitimate arithmetic, and should
recompute it from the supported numbers it comes from.

Usage:
    python3 check_numbers.py CHAPTER.tex --source SRC [--source SRC ...]
                             [--min-digits 2] [--ignore TOKENS] [--all] [--json]

SRC is a .txt, .md or .tex file, a .pdf (read with `pdftotext -layout`), or
a directory (its .tex and .txt files, recursively, skipping a .txt that sits
beside a .tex of the same name). LaTeX sources are masked like the chapter,
so their comments and citation keys do not count as support. Point SRC at
the paper's text, such as a folder written by paper_text.py; keep notes out
of it (or in .md files), or they will count as support too.

Every number outside LaTeX markup is checked, years included, if it has at
least --min-digits digits (default 2, so single digits are skipped).
Ignored: comments, \label, \ref- and \cite-style commands, URLs, graphics
and \input paths, lengths (3pt, 0.48\linewidth, \vspace, \setlength,
\arraystretch), tabular column specs, the first two arguments of
\multicolumn and \multirow, \cline and \cmidrule ranges, and colour specs.
Files pulled in with \input are not followed; check them separately.

A token matches a source number with the same value at a numeric boundary
(0.72 does not match inside 0.727, nor 727 inside 0.727), whatever the
spelling: \% or % or no percent sign, a leading zero (.727 = 0.727),
trailing zeros (90.50 = 90.5, 2.0 = 2), thousands separators (1,000 = 1000
= 1{,}000) and Unicode minus signs. A minus sign must match (-0.5 is not
0.5), but an unsigned chapter number may match a signed source number.

Output: a Markdown table of the UNSUPPORTED tokens (every token with
--all): chapter line, token, about 40 characters of context each side, and
the status, which is SRC:line of the first match (with the page for PDF
text, whose pages are separated by form feeds) or UNSUPPORTED. A summary
line follows: N tokens checked, M unsupported.

Exit codes: 0 every checked number was found; 1 some are unsupported;
2 usage error, unreadable input, or pdftotext missing for a PDF source.
"""

import argparse
import bisect
import collections
import json
import os
import re
import shutil
import subprocess
import sys

Token = collections.namedtuple("Token", "line start end text")

TOKEN_RE = re.compile(
    r"""
    # a unary sign: not after a word, a closing bracket, a dash or a dot,
    # so 2019--2021, x-12 and 1-2 have no sign
    (?:(?<![\w)\]}.+\-\u2212\u2013])[-+\u2212\u2013])?
    (?<![\d.])                       # never start inside another number
    (?:
        \d+(?:\.\d+){2,}(?!\d)                           # 1.13.1, 2021.05.12
      | \d{1,3}(?:(?:,|\{,\}|\\,)\d{3})+(?!\d)(?:\.\d+)?  # 1,000 1{,}000 1\,000
      | \d+(?:\.\d+)?                                    # 12, 0.727
      | (?<!\w)\.\d+                                     # .727 but not Fig.12
    )
    (?:\\?%)?                        # 12.5% or 12.5\%
    """,
    re.VERBOSE,
)


MINUS_SIGNS = "-\u2212\u2013"  # hyphen-minus, Unicode minus, en dash

# % preceded by an even number of backslashes starts a comment (\\% is a
# line break followed by a comment, \% is a literal percent sign)
COMMENT_RE = re.compile(r"(?<!\\)(?:\\\\)*(%[^\n]*)")
COMMENT_ENV_RE = re.compile(r"\\begin\s*\{comment\}.*?\\end\s*\{comment\}", re.DOTALL)
# a URL argument may contain % (data%20x), which is not a comment there; it
# is masked before comments are (only the URL of \href, not its link text)
URL_RE = re.compile(r"\\(?:url|nolinkurl|href)\s*\{[^{}\n]*\}")


def _blank(text):
    """Spaces in place of every character except line breaks."""
    return re.sub(r"[^\n]", " ", text)


def _blank_spans(text, spans):
    """Blank the (start, end) spans of text, keeping its length and lines."""
    if not spans:
        return text
    parts = []
    last = 0
    for start, end in sorted(spans):
        start = max(start, last)
        if start >= end:
            continue
        parts.append(text[last:start])
        parts.append(_blank(text[start:end]))
        last = end
    parts.append(text[last:])
    return "".join(parts)


def _group_end(text, i):
    """text[i] opens a {...}, [...] or (...) group; return the index just
    past its matching close, or None if it is unbalanced."""
    opener = text[i]
    closer = {"{": "}", "[": "]", "(": ")"}[opener]
    braces = 1 if opener == "{" else 0
    j = i + 1
    while j < len(text):
        char = text[j]
        if char == "\\":
            j += 2  # \{ \} \] are escaped characters
            continue
        if char == "{":
            braces += 1
        elif char == "}":
            braces -= 1
            if braces < 0:
                return None
            if braces == 0 and opener == "{":
                return j + 1
        elif char == closer and braces == 0:
            return j + 1
        j += 1
    return None


CONTROL_SEQUENCE_RE = re.compile(r"\\(?:[A-Za-z]+|.)")


def _arguments_end(text, i, mandatory, parens=False):
    """Skip the arguments of a command whose name ends at i.

    Optional [...] groups (and (...) groups when parens is true) may come
    before or between the `mandatory` arguments, each a {...} group or a
    control sequence (\\setlength\\tabcolsep{3pt}). Returns the index after
    the last mandatory argument, or None if they are not all there.
    """
    count = 0
    while count < mandatory:
        while i < len(text) and text[i] in " \t\n":
            i += 1
        if i >= len(text):
            return None
        char = text[i]
        if char == "[" or (parens and char == "("):
            end = _group_end(text, i)
        elif char == "{":
            end = _group_end(text, i)
            count += 1
        elif char == "\\":
            end = CONTROL_SEQUENCE_RE.match(text, i).end()
            count += 1
        else:
            return None
        if end is None:
            return None
        i = end
    return i


# (command names, mandatory arguments to blank, takes (...) groups)
ARGUMENT_COMMANDS = [
    (r"label", 1, False),
    (r"(?:auto|c|C|eq|page|name|v|V|cpage|Cpage|labelc|sub)?ref", 1, False),
    (r"[cC](?:page)?refrange", 2, False),
    # \cite \citep \citet \citealp \citeauthor \citeyear \parencite ...
    (r"[A-Za-z]*cite[A-Za-z]*", 1, False),
    (r"includegraphics", 1, False),
    (r"input|include", 1, False),
    (r"vspace|hspace|scalebox|linespread|setstretch", 1, False),
    (r"setlength|addtolength|fontsize|setcounter|addtocounter", 2, False),
    (r"multicolumn|multirow", 2, False),
    (r"cline|cdashline", 1, False),
    (r"cmidrule", 1, True),
    # colour specs; \textcolor and \colorbox keep their text argument
    (r"rowcolor|cellcolor|columncolor|color|pagecolor|textcolor|colorbox", 1, False),
    (r"fcolorbox", 2, False),
    (r"definecolor|rowcolors", 3, False),
]
ARGUMENT_COMMAND_RES = [
    (re.compile(r"\\(?:%s)(?![A-Za-z])\*?" % names), mandatory, parens)
    for names, mandatory, parens in ARGUMENT_COMMANDS
]


_NUMBER = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)"
# (pattern, group to blank)
LENGTH_RES = [
    # 3pt, 1.5em, -2mm written as markup: after [, {, = or a control word,
    # as in \\[3pt], {1pt}, margin=1in, \kern 2pt. In prose ("a gain of
    # 3pt", "150bp reads") the number is content and stays checked.
    (re.compile(
        r"(?:[\[{=]|\\[A-Za-z]+)\s*(%s(?:pt|pc|in|bp|cm|mm|dd|cc|sp|em|ex|mu))"
        r"(?![A-Za-z])" % _NUMBER
    ), 1),
    # 0.48\linewidth, 2\baselineskip, 1.5\tabcolsep
    (re.compile(
        r"(?<![\w.])%s\s*\\[A-Za-z]*(?:width|height|skip|sep|size|indent|depth)"
        r"(?![A-Za-z])" % _NUMBER
    ), 0),
    # \renewcommand{\arraystretch}{1.25}, \def\arraystretch{1.25}
    (re.compile(
        r"\\(?:(?:re)?newcommand\s*\{?|def)\s*\\(?:arraystretch|baselinestretch)"
        r"\s*\}?\s*\{[^{}]*\}"
    ), 0),
]


# \begin{ENV} followed by its column spec (after the width for tabularx)
TABULAR_RES = [
    (re.compile(r"\\begin\s*\{(?:tabular|array|longtable|supertabular|xtabular"
                r"|NiceTabular|NiceArray|tblr|longtblr|talltblr)\}"), 1),
    (re.compile(r"\\begin\s*\{(?:tabular\*|tabularx|tabulary|xltabular"
                r"|NiceTabular\*|NiceTabularX)\}"), 2),
]


def _argument_command_spans(text):
    spans = []
    for pattern, mandatory, parens in ARGUMENT_COMMAND_RES:
        for match in pattern.finditer(text):
            end = _arguments_end(text, match.end(), mandatory, parens)
            if end is not None:
                spans.append((match.start(), end))
    for pattern, mandatory in TABULAR_RES:
        for match in pattern.finditer(text):
            end = _arguments_end(text, match.end(), mandatory)
            if end is not None:
                spans.append((match.start(), end))
    return spans


def strip_comments(text):
    """Blank LaTeX comments and comment environments, keeping the length
    and line breaks of `text`. A % inside a URL argument is kept."""
    protected = _blank_spans(text, [m.span() for m in URL_RE.finditer(text)])
    text = _blank_spans(text, [m.span(1) for m in COMMENT_RE.finditer(protected)])
    return _blank_spans(text, [m.span() for m in COMMENT_ENV_RE.finditer(text)])


def mask_latex(text):
    """Blank the parts of LaTeX source whose numbers are not content.

    The result has the same length and line breaks as `text`, so positions
    and line numbers found in it are valid in the original.
    """
    return _mask_markup(strip_comments(text))


def _mask_markup(text):
    """mask_latex for text whose comments are already blanked."""
    text = _blank_spans(text, [m.span() for m in URL_RE.finditer(text)])
    text = _blank_spans(text, _argument_command_spans(text))
    for pattern, group in LENGTH_RES:
        text = _blank_spans(text, [m.span(group) for m in pattern.finditer(text)])
    return text


def canonical(token):
    """Return one spelling for all the ways of writing the same number.

    Drops percent signs, thousands separators and a plus sign; writes every
    minus as "-"; adds a leading zero (.727 -> 0.727); trims trailing
    decimal zeros (90.50 -> 90.5, 2.0 -> 2). Dotted versions such as 1.10.0
    are kept as written.
    """
    text = token.replace("\\%", "").replace("%", "")
    for separator in ("{,}", "\\,", ","):
        text = text.replace(separator, "")
    sign = ""
    if text[:1] in MINUS_SIGNS:
        sign, text = "-", text[1:]
    elif text[:1] == "+":
        text = text[1:]
    if text.count(".") == 1:
        if text.startswith("."):
            text = "0" + text
        text = text.rstrip("0").rstrip(".")
    return sign + text


def find_tokens(text):
    """Return the numeric tokens of `text` with 1-based line numbers."""
    line_starts = [0] + [m.end() for m in re.finditer("\n", text)]
    tokens = []
    for match in TOKEN_RE.finditer(text):
        line = bisect.bisect_right(line_starts, match.start())
        tokens.append(Token(line, match.start(), match.end(), match.group(0)))
    return tokens


Match = collections.namedtuple("Match", "source line page")


def _minus_before(text, start):
    """True if a minus sign sits right before text[start], as in x-0.5,
    but not a range dash such as 10-12 or 2019--2021."""
    if start < 1 or text[start - 1] not in MINUS_SIGNS:
        return False
    before = text[start - 2] if start >= 2 else " "
    return not (before.isdigit() or before in MINUS_SIGNS)


def build_index(sources):
    """Index the numbers of the sources.

    sources: list of (label, text). Returns {canonical form: Match} holding
    the first occurrence of each number. A signed source number also counts
    for the unsigned chapter number (a "drop of 0.5" may quote "-0.5"), but
    not the other way round. Pages are counted from form feeds, which
    pdftotext writes between pages; page is None for text without them.
    """
    index = {}
    for label, text in sources:
        feeds = [m.start() for m in re.finditer("\f", text)]
        for token in find_tokens(text):
            form = canonical(token.text)
            forms = [form]
            if form.startswith("-"):
                forms.append(form[1:])
            elif _minus_before(text, token.start):
                forms.append("-" + form)
            page = bisect.bisect_right(feeds, token.start) + 1 if feeds else None
            for each in forms:
                index.setdefault(each, Match(label, token.line, page))
    return index


def lookup(index, token):
    """Return the first Match of a chapter token in the index, or None."""
    return index.get(canonical(token))


def _context(text, start, end, width=40):
    """About `width` characters each side of text[start:end], on one line."""
    return " ".join(text[max(0, start - width):end + width].split())


def check(chapter_text, index, min_digits=2, ignore=()):
    """Look up every numeric token of a LaTeX chapter in a source index.

    Returns (results, skipped): one dict per checked token, in chapter
    order, and the number of tokens skipped for having fewer than
    `min_digits` digits or being listed in `ignore`.
    """
    uncommented = strip_comments(chapter_text)
    masked = _mask_markup(uncommented)
    results = []
    skipped = 0
    for token in find_tokens(masked):
        digits = sum(char.isdigit() for char in token.text)
        if digits < min_digits or canonical(token.text) in ignore:
            skipped += 1
            continue
        match = lookup(index, token.text)
        results.append({
            "line": token.line,
            "token": token.text,
            "context": _context(uncommented, token.start, token.end),
            "match": match,
        })
    return results, skipped


def _read_text(path):
    with open(path, encoding="utf-8", errors="replace") as handle:
        return handle.read()


def _pdf_text(path):
    result = subprocess.run(
        ["pdftotext", "-layout", "-enc", "UTF-8", path, "-"],
        capture_output=True, check=True,
    )
    return result.stdout.decode("utf-8", errors="replace")


def _source_text(path):
    """The text of one source file. A PDF is converted with pdftotext
    -layout; LaTeX is masked like the chapter, so a number in a comment or
    a citation key does not count as support."""
    if path.lower().endswith(".pdf"):
        return _pdf_text(path)
    text = _read_text(path)
    if path.endswith(".tex"):
        text = mask_latex(text)
    return text


def _same_file(a, b):
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False


def load_sources(paths):
    """Return [(label, text)] for the --source arguments, in order.

    A directory contributes its .tex and .txt files, recursively and sorted;
    a .txt beside a .tex of the same name is skipped as a copy (paper_text.py
    writes flattened LaTeX to both source.tex and source.txt, and only the
    .tex copy is masked).
    """
    sources = []
    for path in paths:
        if os.path.isdir(path):
            for root, dirs, files in os.walk(path):
                dirs[:] = sorted(d for d in dirs if not d.startswith("."))
                for name in sorted(files):
                    stem, ext = os.path.splitext(name)
                    if ext not in (".tex", ".txt") or name.startswith("."):
                        continue
                    if ext == ".txt" and stem + ".tex" in files:
                        continue
                    full = os.path.join(root, name)
                    sources.append((full, _source_text(full)))
        else:
            sources.append((path, _source_text(path)))
    return sources


def _status(result):
    match = result["match"]
    if match is None:
        return "UNSUPPORTED"
    status = "%s:%d" % (match.source, match.line)
    if match.page is not None:
        status += " (page %d)" % match.page
    return status


def _cell(text):
    """Escape a Markdown table cell."""
    return text.replace("|", "\\|")


def format_markdown(results, skipped, min_digits, show_all):
    unsupported = [r for r in results if r["match"] is None]
    shown = results if show_all else unsupported
    lines = []
    if shown:
        lines.append("| line | token | context | status |")
        lines.append("|---:|---|---|---|")
        for result in shown:
            lines.append("| %d | %s | %s | %s |" % (
                result["line"], _cell(result["token"]), _cell(result["context"]),
                _cell(_status(result))))
        lines.append("")
    lines.append(
        "%d tokens checked, %d unsupported (%d skipped: fewer than %d digits "
        "or in --ignore)." % (len(results), len(unsupported), skipped, min_digits)
    )
    return "\n".join(lines)


def report_json(chapter, sources, results, skipped, show_all):
    tokens = []
    for result in results:
        match = result["match"]
        if match is not None and not show_all:
            continue
        tokens.append({
            "line": result["line"],
            "token": result["token"],
            "value": canonical(result["token"]),
            "context": result["context"],
            "supported": match is not None,
            "source": match.source if match else None,
            "source_line": match.line if match else None,
            "source_page": match.page if match else None,
        })
    return {
        "chapter": chapter,
        "sources": list(sources),
        "checked": len(results),
        "unsupported": sum(1 for r in results if r["match"] is None),
        "skipped": skipped,
        "tokens": tokens,
    }


SOURCE_TYPES = (".txt", ".md", ".tex", ".pdf")
INSTALL_HINT = (
    "Install Poppler: `brew install poppler` on macOS, "
    "`apt install poppler-utils` on Debian/Ubuntu."
)


def _error(message):
    print("check_numbers: " + message, file=sys.stderr)


def _input_problem(chapter, sources):
    """Return a message for the first unusable input, or None."""
    if not os.path.isfile(chapter):
        return "no such chapter file: %s" % chapter
    for path in sources:
        if os.path.isdir(path):
            continue
        if not os.path.isfile(path):
            return "no such source: %s" % path
        if not path.lower().endswith(SOURCE_TYPES):
            return "unsupported source type: %s (use %s files or a directory)" % (
                path, ", ".join(SOURCE_TYPES))
    if any(p.lower().endswith(".pdf") for p in sources) and not shutil.which("pdftotext"):
        return "pdftotext is needed to read PDF sources but is not on PATH. " + INSTALL_HINT
    return None


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("chapter", metavar="CHAPTER.tex", help="the chapter to check")
    parser.add_argument(
        "--source", action="append", required=True, metavar="SRC",
        help="a source paper: .txt, .md, .tex, .pdf or a directory (repeatable)",
    )
    parser.add_argument(
        "--min-digits", type=int, default=2, metavar="N",
        help="skip tokens with fewer digits (default: 2, so single digits)",
    )
    parser.add_argument(
        "--ignore", action="append", default=[], metavar="TOKENS",
        help="comma-separated numbers to skip, compared after normalization "
        "(1000 also skips 1,000; .5 skips 0.50); repeatable",
    )
    parser.add_argument(
        "--all", action="store_true", help="list every token, not only unsupported ones"
    )
    parser.add_argument(
        "--json", action="store_true", help="print a JSON report instead of Markdown"
    )
    args = parser.parse_args(argv)
    ignore = {
        canonical(item.strip())
        for value in args.ignore for item in value.split(",") if item.strip()
    }

    problem = _input_problem(args.chapter, args.source)
    if problem:
        _error(problem)
        return 2
    try:
        # A file is never its own support (a conclusion listed among its
        # sources would confirm its own wrong numbers).
        sources = [(label, text) for label, text in load_sources(args.source)
                   if not _same_file(label, args.chapter)]
        index = build_index(sources)
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.decode("utf-8", errors="replace").strip()
        _error("pdftotext failed on %s: %s" % (exc.cmd[-2], detail))
        return 2
    results, skipped = check(_read_text(args.chapter), index, args.min_digits, ignore)
    if args.json:
        print(json.dumps(
            report_json(args.chapter, args.source, results, skipped, args.all), indent=2))
    else:
        print(format_markdown(results, skipped, args.min_digits, args.all))
    return 1 if any(r["match"] is None for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
