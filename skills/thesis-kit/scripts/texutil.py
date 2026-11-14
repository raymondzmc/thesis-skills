"""Shared LaTeX text helpers for the thesis-kit scripts (standard library only).

Import from another script in this folder:

    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import texutil

    prose = texutil.to_prose(source)          # same lines as the source
    for line, sentence in texutil.sentences(prose):
        n_words = len(texutil.words(sentence))

API
    strip_comments(text) -> str
        Remove from each unescaped % to the end of the line, keep the newline.
    to_prose(text) -> str
        Same number of lines as the input; everything that is not running
        prose is blanked: comments, \\iffalse...\\fi and comment
        environments, the preamble (when \\begin{document} is present),
        display math, tables, figures, algorithms, code and \\verb,
        headings, citations, references, labels, URLs, graphics, inputs,
        spacing and macro definitions. Inline math becomes the token X.
        Text-style and unknown commands are dropped but keep the text of
        their {...} arguments (\\emph{x} -> x); footnotes stay, spaced off
        from the sentence. \\item stays as a marker that sentences() splits
        on. A line is empty exactly when the source line is blank; lines
        blanked entirely keep a space, so a display equation or a comment
        line does not end a paragraph.
        Not handled: user macros are dropped without expansion (\\gls{ntm}
        leaves "ntm"); \\input files are not followed; a % inside \\url
        that the URL pre-pass misses (braces in the URL) starts a comment.
    sentences(prose) -> [(line, sentence)]
        1-based line where each sentence starts.
    words(sentence) -> [str]
        Word tokens; "pre-trained", "don't", "0.727" and X are one word each.
    paragraphs(prose) -> [(start_line, text)]
        Paragraphs separated by empty lines, whitespace-normalized.
    LineIndex(text).line(offset) -> 1-based line of a character offset.

Command line (to see what the checkers see):

    python3 texutil.py FILE.tex [--sentences | --paragraphs] [--json]

Exit codes: 0 = ran, 2 = usage or file error.
"""

import argparse
import bisect
import json
import re
import sys

# An unescaped % starts a comment: it is preceded by an even number of
# backslashes (zero included). Group 1 keeps those backslashes.
_COMMENT_RE = re.compile(r"(?<!\\)((?:\\\\)*)%[^\r\n]*")


def strip_comments(text):
    """Remove LaTeX comments, keeping the newline that ends each line."""
    return _COMMENT_RE.sub(lambda m: m.group(1), text)


# The pre-passes (verbatim, URLs, comments) blank with this filler instead of
# spaces, so that a commented-out line is not mistaken for a blank line (a
# paragraph break) while scanning. to_prose() turns it into spaces at the end.
_FILL = "\x00"


def _fill(s):
    return re.sub(r"[^\n]", _FILL, s)


def _blank_comments(text):
    return _COMMENT_RE.sub(
        lambda m: m.group(1) + _FILL * (len(m.group(0)) - len(m.group(1))),
        text)


def _newlines(s):
    return "\n" * s.count("\n")


def _blank(s):
    """Spaces for every character of s except newlines."""
    return re.sub(r"[^\n]", " ", s)


def _find_close(text, start, delim):
    """Index of the delimiter that closes a math span, or -1.

    Math cannot contain a paragraph break, so the search stops at one.
    """
    i, n, depth = start, len(text), 0
    while i < n:
        if depth == 0 and text.startswith(delim, i):
            return i
        c = text[i]
        if c == "\\":
            i += 2
            continue
        if c == "\n":
            j = i + 1
            while j < n and text[j] in " \t":
                j += 1
            if j >= n or text[j] == "\n":
                return -1
        elif c == "{":
            depth += 1
        elif c == "}" and depth:
            depth -= 1
        i += 1
    return -1


# Control symbols (backslash + one non-letter) and what they print as prose.
_SYMBOLS = {
    "$": "$", "%": "%", "&": "&", "#": "#", "_": "_", "{": "{", "}": "}",
    " ": " ", "\t": " ", "\n": "\n", ",": " ", ";": " ", ":": " ", ">": " ",
}

_CMD_RE = re.compile(r"\\([A-Za-z]+)(\*?)")


def _skip_ws(text, i):
    """Skip spaces, comments and line ends, but never a paragraph break."""
    n = len(text)
    while i < n:
        if text[i] in " \t" + _FILL:
            i += 1
        elif text[i] == "\n":
            j = i + 1
            while j < n and text[j] in " \t":
                j += 1
            if j >= n or text[j] == "\n":
                return i              # the next line is blank
            i += 1
        else:
            break
    return i


def _brace_end(text, i):
    """Index just past the {...} group that opens at text[i], or -1."""
    depth, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == "\\":
            i += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return -1


def _bracket_end(text, i):
    """Index just past the [...] argument that opens at text[i], or -1."""
    depth, n = 0, len(text)
    i += 1
    while i < n:
        c = text[i]
        if c == "\\":
            i += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}" and depth:
            depth -= 1
        elif c == "]" and depth == 0:
            return i + 1
        i += 1
    return -1


def _skip_args(text, i, n_opt, n_mand):
    """Index after up to n_opt [...] and then n_mand {...} arguments."""
    for _ in range(n_opt):
        j = _skip_ws(text, i)
        end = _bracket_end(text, j) if text.startswith("[", j) else -1
        if end < 0:
            break
        i = end
    for _ in range(n_mand):
        j = _skip_ws(text, i)
        if text.startswith("{", j):
            end = _brace_end(text, j)
        else:                         # a single \command is an argument too
            cm = _CMD_RE.match(text, j)
            end = cm.end() if cm else -1
        if end < 0:
            break
        i = end
    return i


# Commands removed together with their arguments: name -> (optional, mandatory).
# Any command whose name contains "cite" is handled as (2, 1).
_REMOVE = {
    "ref": (0, 1), "autoref": (0, 1), "Autoref": (0, 1), "cref": (0, 1),
    "Cref": (0, 1), "eqref": (0, 1), "pageref": (0, 1), "nameref": (0, 1),
    "vref": (0, 1), "Vref": (0, 1), "subref": (0, 1), "cpageref": (0, 1),
    "Cpageref": (0, 1), "labelcref": (0, 1), "crefrange": (0, 2),
    "Crefrange": (0, 2), "label": (0, 1), "url": (0, 1),
    "includegraphics": (1, 1), "input": (0, 1), "include": (0, 1),
    "vspace": (0, 1), "hspace": (0, 1), "bibliography": (0, 1),
    "bibliographystyle": (0, 1),
    # \textcolor{red}{text}: only the colour goes, {text} stays a plain group.
    "textcolor": (1, 1), "color": (1, 1), "todo": (1, 1),
    "setlength": (0, 2), "addtolength": (0, 2), "setcounter": (0, 2),
    "addtocounter": (0, 2),
    # \ifthenelse{cond}{yes}{no}: the condition goes, both branches stay.
    "ifthenelse": (0, 1),
}

# Macro definitions: {name} [args] [default] {body} ({begin}{end} for envs).
_DEFINITIONS = {"newcommand": 1, "renewcommand": 1, "providecommand": 1,
                "DeclareMathOperator": 1, "newenvironment": 2,
                "renewenvironment": 2}

# Commands that print text.
_PRINTS = {"LaTeX": "LaTeX", "TeX": "TeX", "BibTeX": "BibTeX",
           "ldots": "...", "dots": "...", "textellipsis": "..."}

# Notes whose text is prose but not part of the surrounding sentence.
_NOTES = frozenset(["footnote", "footnotetext", "marginpar"])


HEADINGS = frozenset([
    "part", "chapter", "section", "subsection", "subsubsection",
    "paragraph", "subparagraph"])


def _command(text, m, out):
    """Handle the control word matched by m; return the next index or None."""
    name = m.group(1)
    if name == "item":                # kept as a marker for sentences()
        out.append("\\item ")
        j = _skip_ws(text, m.end())
        if text.startswith("[", j):   # \item[label]: blank the label
            end = _bracket_end(text, j)
            if end > 0:
                out.append(_blank(text[m.end():end]))
                return end
        return m.end()
    if name in HEADINGS:
        end = _skip_args(text, m.end(), 1, 1)
        out.append(_blank(text[m.start():end]))
        return end
    if name in _NOTES:
        k = _skip_ws(text, _skip_args(text, m.end(), 1, 0))
        end = _brace_end(text, k) if text.startswith("{", k) else -1
        if end > 0:
            out.append(" " + _newlines(text[m.start():k]))
            out.append(_scan(text[k + 1:end - 1]) + " ")
            return end
    if "cite" in name.lower():
        spec = (2, 1)
    else:
        spec = _REMOVE.get(name)
    if name in _DEFINITIONS:
        after_name = _skip_args(text, m.end(), 0, 1)
        end = _skip_args(text, after_name, 2, _DEFINITIONS[name])
        out.append(_newlines(text[m.start():end]))
        return end
    if spec:
        end = _skip_args(text, m.end(), *spec)
        out.append(_newlines(text[m.start():end]))
        return end
    if name in _PRINTS:
        out.append(_PRINTS[name])
        return m.end()
    # Any other command is dropped, with an adjacent [...] argument. Its
    # {...} arguments are then read as plain groups, so text-style commands
    # (\emph, \textbf, \mbox, ...) keep their content.
    if text.startswith("[", m.end()):
        end = _bracket_end(text, m.end())
        if end > 0:
            out.append(_newlines(text[m.end():end]))
            return end
    return m.end()

DISPLAY_MATH_ENVS = frozenset([
    "equation", "equation*", "align", "align*", "gather", "gather*",
    "multline", "eqnarray", "displaymath",
    "multline*", "eqnarray*", "flalign", "flalign*", "alignat", "alignat*"])
INLINE_MATH_ENVS = frozenset(["math"])
VERBATIM_ENVS = frozenset(["verbatim", "verbatim*", "Verbatim", "lstlisting",
                           "minted", "comment"])
NONPROSE_ENVS = frozenset([
    "table", "table*", "tabular", "tabularx", "figure", "figure*",
    "algorithm", "algorithmic", "tikzpicture",
    "tabular*", "longtable", "wrapfigure", "wraptable", "subfigure",
    "subtable", "sidewaystable", "sidewaysfigure", "algorithm*",
    "thebibliography"]) | VERBATIM_ENVS

_BEGIN_RE = re.compile(r"\\begin\s*\{([^{}\s]+)\}")
_VERBATIM_RE = re.compile(
    r"\\begin\s*\{(%s)\}.*?\\end\s*\{\1\}"
    % "|".join(re.escape(e) for e in sorted(VERBATIM_ENVS)), re.S)


# \verb|...| and \verb*|...| with any delimiter, on one line.
_VERB_RE = re.compile(r"\\verb\*?([^A-Za-z\s*])[^\n]*?\1")


def _blank_verbatim(text):
    """Blank verbatim-like environments and \\verb; their % and $ are code."""
    text = _VERBATIM_RE.sub(lambda m: _fill(m.group(0)), text)
    return _VERB_RE.sub(lambda m: _fill(m.group(0)), text)


# \url{...} and the URL argument of \href{...}{text}; URLs may hold a %.
_URL_RE = re.compile(r"\\(?:url|href)\s*\{[^{}\n]*\}")


def _blank_urls(text):
    return _URL_RE.sub(lambda m: _fill(m.group(0)), text)


def _env_end(text, start, env):
    """Index just past the \\end{env} closing an environment, or -1."""
    pat = re.compile(r"\\(begin|end)\s*\{" + re.escape(env) + r"\}")
    depth = 1
    for m in pat.finditer(text, start):
        depth += 1 if m.group(1) == "begin" else -1
        if depth == 0:
            return m.end()
    return -1


# Prose environments whose \begin takes mandatory arguments (a width ...).
_ENV_ARGS = {"minipage": 1, "multicols": 1, "multicols*": 1,
             "otherlanguage": 1, "adjustbox": 1, "list": 2}
_END_RE = re.compile(r"\\end\s*\{([^{}\s]+)\}")


def _environment(text, i, out):
    """Handle \\begin{...} or \\end{...} at i; return the next index or None."""
    m = _BEGIN_RE.match(text, i)
    if not m:
        m = _END_RE.match(text, i)
        if not m:
            return None
        out.append(_newlines(m.group(0)))
        return m.end()
    env = m.group(1)
    if env in DISPLAY_MATH_ENVS or env in NONPROSE_ENVS \
            or env in INLINE_MATH_ENVS:
        end = _env_end(text, m.end(), env)
        if end >= 0:
            span = text[i:end]
            out.append("X" + _newlines(span) if env in INLINE_MATH_ENVS
                       else _blank(span))
            return end
    # Any other environment: drop \begin{env} and its arguments, keep content.
    end = m.end()
    if text.startswith("[", end) or env in _ENV_ARGS:
        end = _skip_args(text, end, 3, _ENV_ARGS.get(env, 0))
    out.append(_newlines(text[i:end]))
    return end


def _math(text, i, opener, closer, inline, out):
    """Math span opened at i; returns the index after it."""
    end = _find_close(text, i + len(opener), closer)
    if end < 0:                       # unclosed: drop the opener only
        return i + len(opener)
    span = text[i:end + len(closer)]
    out.append("X" + _newlines(span) if inline else _blank(span))
    return end + len(closer)


def _backslash(text, i, out):
    """Anything starting with a backslash at i; returns the next index."""
    nxt = text[i + 1:i + 2]
    if nxt == "(":
        return _math(text, i, "\\(", "\\)", True, out)
    if nxt == "[":
        return _math(text, i, "\\[", "\\]", False, out)
    j = _environment(text, i, out)
    if j is not None:
        return j
    m = _CMD_RE.match(text, i)
    if m:
        return _command(text, m, out)
    if nxt == "\\":                   # line break, maybe \\* or \\[2pt]
        out.append(" ")
        j = i + 2
        if text.startswith("*", j):
            j += 1
        if text.startswith("[", j):
            end = _bracket_end(text, j)
            if end > 0:
                out.append(_newlines(text[j:end]))
                j = end
        return j
    # Accents, \-, \@, \/ ... print nothing; a newline is always kept.
    out.append(_SYMBOLS.get(nxt, ""))
    return i + 2


def _scan(text):
    out = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == "\\":
            i = _backslash(text, i, out)
        elif text.startswith("$$", i):
            i = _math(text, i, "$$", "$$", False, out)
        elif c == "$":
            i = _math(text, i, "$", "$", True, out)
        elif c in "{}":
            i += 1
        elif c == "~":
            out.append(" ")
            i += 1
        elif text.startswith("``", i) or text.startswith("''", i):
            out.append('"')
            i += 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


# \iffalse ... \fi hides text; nested \if.../\fi pairs are skipped over
# (\ifthenelse is a macro, not a conditional that needs \fi).
_IFFALSE_RE = re.compile(r"\\iffalse(?![A-Za-z])")
_CONDITIONAL_RE = re.compile(r"\\(if[A-Za-z]*|fi)(?![A-Za-z])")


def _blank_iffalse(text):
    parts, pos = [], 0
    for m in _IFFALSE_RE.finditer(text):
        if m.start() < pos:
            continue
        depth, end = 0, -1
        for t in _CONDITIONAL_RE.finditer(text, m.start()):
            if t.group(1) == "fi":
                depth -= 1
                if depth == 0:
                    end = t.end()
                    break
            elif t.group(1) != "ifthenelse":
                depth += 1
        if end > 0:
            parts += [text[pos:m.start()], _fill(text[m.start():end])]
            pos = end
    parts.append(text[pos:])
    return "".join(parts)


_DOC_BEGIN_RE = re.compile(r"\\begin\s*\{document\}")
_DOC_END_RE = re.compile(r"\\end\s*\{document\}")


def _blank_outside_document(text):
    """Blank the preamble and anything after \\end{document}, if present."""
    m = _DOC_BEGIN_RE.search(text)
    if not m:
        return text
    text = _fill(text[:m.end()]) + text[m.end():]
    e = _DOC_END_RE.search(text, m.end())
    if e:
        text = text[:e.start()] + _fill(text[e.start():])
    return text


def to_prose(text):
    """Blank out everything that is not running prose, keeping the lines."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    work = _blank_iffalse(_blank_comments(_blank_urls(_blank_verbatim(text))))
    out = _scan(_blank_outside_document(work))
    # Paragraph-break contract: a line is empty exactly when the source line
    # is blank; a line whose content was all blanked keeps at least a space.
    lines = []
    out = out.replace(_FILL, " ")
    for src, line in zip(text.split("\n"), out.split("\n")):
        if not src.strip():
            lines.append("")
        else:
            lines.append(line or " ")
    return "\n".join(lines)


# A word: letters/digits, joined by internal apostrophes, hyphens or periods
# ("e.g", "0.727"); digit groups may also be joined by commas ("1,000").
_WORD_RE = re.compile(
    r"\d+(?:,\d{3})+(?:\.\d+)?(?![\w'’.-])"
    r"|[^\W_]+(?:['’.-][^\W_]+)*")


_CMD_TOKEN_RE = re.compile(r"\\[A-Za-z]+")


def words(sentence):
    """Word tokens of a sentence ("pre-trained" and "don't" are one word).

    Command tokens such as the \\item marker left by to_prose() are skipped.
    """
    return _WORD_RE.findall(_CMD_TOKEN_RE.sub(" ", sentence))


class LineIndex(object):
    """Maps character offsets of a text to 1-based line numbers."""

    def __init__(self, text):
        self._starts = [0] + [m.end() for m in re.finditer("\n", text)]

    def line(self, offset):
        return bisect.bisect_right(self._starts, offset)


# A terminator run, optionally followed by closing quotes or brackets.
_SENT_END_RE = re.compile(r"[.!?]+[\"'”’)\]]*(?=\s)")
_OPENING_QUOTES = "\"'`“‘"
# A period after one of these does not end a sentence ("etc." can).
ABBREVIATIONS = frozenset([
    "e.g.", "i.e.", "al.", "cf.", "vs.", "fig.", "figs.", "eq.", "eqs.",
    "sec.", "tab.", "no.", "approx.", "resp.",
    "secs.", "nos.", "viz.", "ch.", "eqn.", "refs."])


def _is_abbreviation(prose, dot):
    j = dot
    while j > 0 and not prose[j - 1].isspace():
        j -= 1
    token = (prose[j:dot] + ".").lstrip("([{" + _OPENING_QUOTES).lower()
    return token in ABBREVIATIONS


def _boundaries(prose):
    """Offsets just after each sentence end in prose."""
    n = len(prose)
    for m in _SENT_END_RE.finditer(prose):
        if m.group(0)[0] == "." and _is_abbreviation(prose, m.start()):
            continue
        k = m.end()
        while k < n and prose[k].isspace():
            k += 1
        if k < n and (prose[k].isupper() or prose[k].isdigit()
                      or prose[k] in _OPENING_QUOTES):
            yield m.end()


def _blocks(prose):
    """(offset, text) for each run of non-empty lines (a paragraph)."""
    blocks = []
    offset, start = 0, None
    for line in prose.split("\n"):
        if not line.rstrip("\r"):
            if start is not None:
                blocks.append((start, prose[start:offset - 1]))
                start = None
        elif start is None:
            start = offset
        offset += len(line) + 1
    if start is not None:
        blocks.append((start, prose[start:]))
    return blocks


_ITEM_RE = re.compile(r"\\item(?![A-Za-z])")


def _item_pieces(block):
    """(start, end) spans of block between \\item markers."""
    spans, pos = [], 0
    for m in _ITEM_RE.finditer(block):
        spans.append((pos, m.start()))
        pos = m.end()
    spans.append((pos, len(block)))
    return spans


# Space left before punctuation where a citation or reference was removed.
_SPACE_BEFORE_PUNCT_RE = re.compile(r" +(?=[.,;:!?)\]])")


def _emit(text, start, end, offset, index, result):
    chunk = text[start:end]
    normalized = _SPACE_BEFORE_PUNCT_RE.sub("", " ".join(chunk.split()))
    if words(normalized):
        lead = len(chunk) - len(chunk.lstrip())
        result.append((index.line(offset + start + lead), normalized))


def sentences(prose):
    """[(line, sentence)] for to_prose() output; line is where it starts.

    Only an empty line is a paragraph break: to_prose() leaves spaces on the
    lines it blanks, so a display equation inside a sentence does not end it.
    """
    index = LineIndex(prose)
    result = []
    for offset, block in _blocks(prose):
        for a, b in _item_pieces(block):
            piece = block[a:b]
            start = 0
            for end in _boundaries(piece):
                _emit(piece, start, end, offset + a, index, result)
                start = end
            _emit(piece, start, len(piece), offset + a, index, result)
    return result


def paragraphs(prose):
    """[(start_line, text)] for each paragraph of to_prose() output.

    Paragraphs are separated by empty lines; the text is
    whitespace-normalized, \\item markers are removed and paragraphs
    without words are skipped.
    """
    index = LineIndex(prose)
    result = []
    for offset, block in _blocks(prose):
        block = _ITEM_RE.sub(lambda m: " " * len(m.group(0)), block)
        text = _SPACE_BEFORE_PUNCT_RE.sub("", " ".join(block.split()))
        if words(text):
            lead = len(block) - len(block.lstrip())
            result.append((index.line(offset + lead), text))
    return result


def read_tex(path):
    """Text of a .tex file (UTF-8; undecodable bytes are replaced)."""
    with open(path, encoding="utf-8", errors="replace") as handle:
        return handle.read()


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Show the prose view of a LaTeX file that the thesis-kit "
                    "checkers work on: the blanked text with line numbers, "
                    "its sentences or its paragraphs.")
    parser.add_argument("file", help="a .tex file")
    view = parser.add_mutually_exclusive_group()
    view.add_argument("--sentences", action="store_true",
                      help="list sentences with the line where each starts")
    view.add_argument("--paragraphs", action="store_true",
                      help="list paragraphs with their start lines")
    parser.add_argument("--json", action="store_true",
                        help="print JSON instead of Markdown")
    args = parser.parse_args(argv)
    try:
        prose = to_prose(read_tex(args.file))
    except OSError as err:
        print("texutil.py: cannot read %s: %s" % (args.file, err.strerror),
              file=sys.stderr)
        return 2
    if args.sentences or args.paragraphs:
        key = "sentences" if args.sentences else "paragraphs"
        items = sentences(prose) if args.sentences else paragraphs(prose)
        if args.json:
            print(json.dumps({"file": args.file, key: [
                {"line": line, "text": text} for line, text in items]},
                indent=2))
        else:
            print("# %s of %s (%d)\n" % (key.capitalize(), args.file,
                                         len(items)))
            for line, text in items:
                print("- %d: %s" % (line, text))
        return 0
    if args.json:
        print(json.dumps({"file": args.file, "prose": prose}, indent=2))
        return 0
    print("# Prose view of %s\n\n```text" % args.file)
    for number, line in enumerate(prose.split("\n"), 1):
        print(("%4d | %s" % (number, line)).rstrip())
    print("```")
    return 0


if __name__ == "__main__":
    sys.exit(main())
