"""Prose measurements for LaTeX chapters, so a critic can see objectively
where prose is bogged down or where the same wording keeps coming back.

Usage:
    python3 prose_metrics.py FILE.tex [FILE.tex ...] [--long 35] [--openers 3]
        [--ngram 5] [--min-files 2] [--lexicon FILE] [--json]

Per file:
  - sentence and word counts; mean, median and 90th-percentile (nearest
    rank) sentence length in words;
  - long sentences (more than --long words): line, length, first 12 words;
  - repeated openers: first two words (lowercased) starting at least
    --openers sentences, and the sentences that start with "In this
    chapter" or "This chapter";
  - banned patterns: em-dashes (--- or a typed em-dash) and spaced en-dashes
    used as dashes ("word -- word"), counted on the comment-stripped source
    but not inside tabular or verbatim content; semicolons, counted on the
    prose so math is excluded;
  - lexicon hits: overused words and phrases, case-insensitive whole-word
    matches on the prose. --lexicon FILE replaces the built-in list: one
    phrase per line, "re:" marks a regular expression, "#" starts a comment.
Across files: n-grams of exactly --ngram words (lowercased, within
sentences) found in at least --min-files files, ignoring n-grams with math
(X), digits or at least 60% stopwords; top 30 by files, then count. The
location given per file is the line where the sentence holding the n-gram's
first occurrence starts.

Line numbers refer to the source file. Sentences, words and prose come from
texutil.to_prose(), so citations, references, labels and math are excluded.

Exit codes: 0 = ran (these are measurements, not pass/fail),
2 = usage or file error.
"""

import argparse
import json
import math
import os
import re
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import texutil  # noqa: E402

# Dashes are counted on the comment-stripped source (so captions and
# footnotes count) but not inside table cells or code, where "---" is an
# empty-cell marker or part of a command line.
_CELL_ENVS = ["tabular", "tabular*", "tabularx", "longtable", "verbatim",
              "verbatim*", "Verbatim", "lstlisting", "minted", "comment"]
_CELL_ENV_RE = re.compile(
    r"\\begin\s*\{(%s)\}.*?\\end\s*\{\1\}"
    % "|".join(re.escape(e) for e in _CELL_ENVS), re.S)
_EM_DASH_RE = re.compile("---|\u2014")
# An en-dash with space (or ~) on both sides, between two non-dash characters.
_SPACED_EN_DASH_RE = re.compile(
    "(?<=[^\\s~-])[\\s~]+(--|\u2013)(?=[\\s~]+[^\\s~-])")
_SEMICOLON_RE = re.compile(";")


# Overused words and phrases of machine-written prose, in --lexicon file
# format: one phrase per line, "re:" marks a regular expression.
DEFAULT_LEXICON = [
    "delve", "crucial", "pivotal", "notably", "furthermore", "moreover",
    "additionally", "comprehensive", "robust", "seamless", "seamlessly",
    "leverage", "leverages", "utilize", "utilizes", "showcase", "showcases",
    "underscore", "underscores", "intricate", "nuanced", "landscape", "realm",
    "tapestry", "paramount", "plays a crucial role", "it is worth noting",
    "in order to", "a wide range of", "shed light on", "paving the way",
    "in the realm of", r"re:not only\b.{1,80}?\bbut also",
]


def load_lexicon(path):
    """Entries of a lexicon file; blank lines and # comments are skipped."""
    with open(path, encoding="utf-8") as handle:
        lines = [line.strip() for line in handle]
    return [line for line in lines if line and not line.startswith("#")]


def compile_lexicon(entries):
    """[(term, regex)]: phrases match whole words, case-insensitively."""
    compiled = []
    for entry in entries:
        if entry.startswith("re:"):
            pattern = entry[3:]
        else:
            pattern = (r"(?<![\w-])"
                       + r"\s+".join(re.escape(w) for w in entry.split())
                       + r"(?![\w-])")
        compiled.append((entry, re.compile(pattern, re.IGNORECASE)))
    return compiled


def _lexicon_hits(prose, compiled):
    """Hits per term on the prose; a phrase may run over a line break."""
    flat = prose.replace("\n", " ")
    index = texutil.LineIndex(prose)
    found = []
    for order, (term, regex) in enumerate(compiled):
        lines = [index.line(m.start()) for m in regex.finditer(flat)]
        if lines:
            found.append((-len(lines), order, {
                "term": term, "count": len(lines),
                "lines": sorted(set(lines))}))
    return [hit for _, _, hit in sorted(found, key=lambda f: f[:2])]


def _dash_source(source):
    text = texutil.strip_comments(source)
    return _CELL_ENV_RE.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)


def _hits(regex, text):
    """Count and lines of regex matches (of group 1 when there is one)."""
    index = texutil.LineIndex(text)
    group = 1 if regex.groups else 0
    lines = [index.line(m.start(group)) for m in regex.finditer(text)]
    return {"count": len(lines), "lines": sorted(set(lines))}


def _percentile(values, fraction):
    """Nearest-rank percentile of a non-empty list."""
    ordered = sorted(values)
    rank = max(1, int(math.ceil(fraction * len(ordered))))
    return ordered[rank - 1]


def _openers(sents, minimum):
    """Two-word openers (lowercased) that start at least `minimum` sentences."""
    lines = {}
    for line, ws in sents:
        if len(ws) >= 2:
            lines.setdefault(" ".join(ws[:2]).lower(), []).append(line)
    found = [{"opener": opener, "count": len(ls), "lines": sorted(set(ls))}
             for opener, ls in lines.items() if len(ls) >= minimum]
    found.sort(key=lambda o: (-o["count"], o["opener"]))
    return found


def _chapter_openers(sents):
    lines = [line for line, ws in sents
             if [w.lower() for w in ws[:3]] == ["in", "this", "chapter"]
             or [w.lower() for w in ws[:2]] == ["this", "chapter"]]
    return {"count": len(lines), "lines": sorted(set(lines))}


def analyze_file(source, long_words=35, opener_min=3, lexicon=None):
    """Measurements for one LaTeX source; lexicon is from compile_lexicon()."""
    if lexicon is None:
        lexicon = compile_lexicon(DEFAULT_LEXICON)
    prose = texutil.to_prose(source)
    sents = [(line, texutil.words(text))
             for line, text in texutil.sentences(prose)]
    lengths = [len(ws) for _, ws in sents]
    report = {"sentences": len(sents), "words": sum(lengths),
              "mean": 0, "median": 0, "p90": 0}
    if lengths:
        report["mean"] = round(statistics.mean(lengths), 2)
        report["median"] = statistics.median(lengths)
        report["p90"] = _percentile(lengths, 0.9)
    report["long_sentences"] = [
        {"line": line, "words": len(ws), "start": " ".join(ws[:12])}
        for line, ws in sents if len(ws) > long_words]
    report["openers"] = _openers(sents, opener_min)
    report["chapter_openers"] = _chapter_openers(sents)
    dashes = _dash_source(source)
    report["banned"] = {"em_dash": _hits(_EM_DASH_RE, dashes),
                        "spaced_en_dash": _hits(_SPACED_EN_DASH_RE, dashes),
                        "semicolon": _hits(_SEMICOLON_RE, prose)}
    report["lexicon"] = _lexicon_hits(prose, lexicon)
    return report


# Common English function words; n-grams made mostly of them are ignored.
STOPWORDS = frozenset("""
a about above after again against all also am among an and any are as at be
because been before being below between both but by can could did do does
doing down during each either few for from further had has have having he her
here hers him his how however i if in into is it its itself just may me might
more most much must my no nor not now of off on once one only or other our
ours out over own same she should so some such than that the their theirs
them then there these they this those though through thus to too under until
up upon very via was we were what when where whether which while who whom
whose why will with within without would yet you your
""".split())


def _countable(gram):
    """False for n-grams with math (X), digits, or >= 60% stopwords."""
    for w in gram:
        if "X" in w.split("-") or any(ch.isdigit() for ch in w):
            return False
    stop = sum(1 for w in gram if w.lower() in STOPWORDS)
    return 5 * stop < 3 * len(gram)


def repeated_ngrams(docs, n=5, min_files=2, top=30):
    """N-grams of exactly n words found in at least min_files files.

    docs is a list of (name, source). Each location is name:line of the
    sentence where the n-gram first occurs in that file.
    """
    seen = {}       # ngram -> {name: [count, first line]}
    for name, source in docs:
        for line, text in texutil.sentences(texutil.to_prose(source)):
            ws = texutil.words(text)
            for i in range(len(ws) - n + 1):
                if not _countable(ws[i:i + n]):
                    continue
                gram = " ".join(ws[i:i + n]).lower()
                per_file = seen.setdefault(gram, {})
                per_file.setdefault(name, [0, line])[0] += 1
    found = [{"ngram": gram, "files": len(per_file),
              "count": sum(c for c, _ in per_file.values()),
              "locations": ["%s:%d" % (name, line)
                            for name, (_, line) in per_file.items()]}
             for gram, per_file in seen.items() if len(per_file) >= min_files]
    found.sort(key=lambda g: (-g["files"], -g["count"], g["ngram"]))
    return found[:top]


def _positive_int(text):
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return value


def _non_negative_int(text):
    value = int(text)
    if value < 0:
        raise argparse.ArgumentTypeError("must be zero or more")
    return value


def _lines(values):
    return ", ".join(str(v) for v in values)


def _lines_label(values):
    return ("line " if len(values) == 1 else "lines ") + _lines(values)


def _cell(text):
    return text.replace("|", "\\|")


def render_markdown(data):
    s = data["settings"]
    out = ["# Prose metrics", ""]
    for rep in data["files"]:
        out += ["## " + rep["file"], "",
                "- Sentences: %d; words: %d" % (rep["sentences"], rep["words"]),
                "- Sentence length (words): mean %s, median %s, "
                "90th percentile %s" % (rep["mean"], rep["median"], rep["p90"]),
                '- Sentences starting "In this chapter" / "This chapter": '
                "%d%s" % (rep["chapter_openers"]["count"],
                          " (%s)" % _lines_label(rep["chapter_openers"]["lines"])
                          if rep["chapter_openers"]["count"] else ""),
                ""]
        out += ["### Long sentences (more than %d words): %d"
                % (s["long"], len(rep["long_sentences"])), ""]
        if rep["long_sentences"]:
            out += ["| Line | Words | Starts with |", "|---|---|---|"]
            out += ["| %d | %d | %s%s |" % (x["line"], x["words"],
                                            _cell(x["start"]),
                                            " ..." if x["words"] > 12 else "")
                    for x in rep["long_sentences"]]
            out.append("")
        out += ["### Repeated openers (at least %d sentences)" % s["openers"],
                ""]
        if rep["openers"]:
            out += ["| Opener | Sentences | Lines |", "|---|---|---|"]
            out += ["| %s | %d | %s |" % (_cell(o["opener"]), o["count"],
                                          _lines(o["lines"]))
                    for o in rep["openers"]]
        else:
            out.append("none")
        out += ["", "### Banned patterns", "",
                "| Pattern | Count | Lines |", "|---|---|---|"]
        labels = [("em_dash", "em-dash (---)"),
                  ("spaced_en_dash", "spaced en-dash ( -- )"),
                  ("semicolon", "semicolon")]
        for key, label in labels:
            hit = rep["banned"][key]
            out.append("| %s | %d | %s |" % (label, hit["count"],
                                             _lines(hit["lines"])))
        out += ["", "### Lexicon hits", ""]
        if rep["lexicon"]:
            out += ["| Term | Count | Lines |", "|---|---|---|"]
            out += ["| %s | %d | %s |" % (_cell(h["term"]), h["count"],
                                          _lines(h["lines"]))
                    for h in rep["lexicon"]]
        else:
            out.append("none")
        out.append("")
    out += ["## Repeated %d-grams across files (in at least %d files)"
            % (s["ngram"], s["min_files"]), ""]
    if data["ngrams"]:
        out += ["| N-gram | Files | Count | Locations |", "|---|---|---|---|"]
        out += ["| %s | %d | %d | %s |" % (_cell(g["ngram"]), g["files"],
                                           g["count"],
                                           ", ".join(g["locations"]))
                for g in data["ngrams"]]
    else:
        out.append("none")
    return "\n".join(out) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Measure sentence length, repeated openers, banned "
                    "patterns, overused words and wording repeated across "
                    "LaTeX files. Always exits 0 after a successful run.")
    parser.add_argument("files", nargs="+", metavar="FILE.tex",
                        help="LaTeX files to measure")
    parser.add_argument("--long", type=_non_negative_int, default=35,
                        help="report sentences longer than this many words "
                             "(default 35)")
    parser.add_argument("--openers", type=_positive_int, default=3,
                        help="report two-word openers that start at least "
                             "this many sentences (default 3)")
    parser.add_argument("--ngram", type=_positive_int, default=5,
                        help="n-gram length for the cross-file check "
                             "(default 5)")
    parser.add_argument("--min-files", type=_positive_int, default=2,
                        help="report n-grams found in at least this many "
                             "files (default 2)")
    parser.add_argument("--lexicon", metavar="FILE",
                        help="replace the built-in word list: one phrase "
                             "per line, 're:' for a regex, '#' for comments")
    parser.add_argument("--json", action="store_true",
                        help="print JSON instead of Markdown")
    args = parser.parse_args(argv)

    def fail(message):
        print("prose_metrics.py: " + message, file=sys.stderr)
        return 2

    entries = DEFAULT_LEXICON
    if args.lexicon:
        try:
            entries = load_lexicon(args.lexicon)
        except OSError as err:
            return fail("cannot read lexicon %s: %s"
                        % (args.lexicon, err.strerror))
    try:
        lexicon = compile_lexicon(entries)
    except re.error as err:
        return fail("bad regular expression in lexicon: %s" % err)

    docs, seen = [], set()
    for path in args.files:
        if os.path.realpath(path) in seen:
            continue
        seen.add(os.path.realpath(path))
        if os.path.isdir(path):
            return fail("%s is a directory; pass .tex files" % path)
        try:
            docs.append((path, texutil.read_tex(path)))
        except OSError as err:
            return fail("cannot read %s: %s" % (path, err.strerror))

    data = {
        "settings": {"long": args.long, "openers": args.openers,
                     "ngram": args.ngram, "min_files": args.min_files,
                     "lexicon": args.lexicon or "built-in"},
        "files": [],
        "ngrams": repeated_ngrams(docs, n=args.ngram,
                                  min_files=args.min_files),
    }
    for path, source in docs:
        report = {"file": path}
        report.update(analyze_file(source, long_words=args.long,
                                   opener_min=args.openers, lexicon=lexicon))
        data["files"].append(report)
    if args.json:
        print(json.dumps(data, indent=2))
    else:
        sys.stdout.write(render_markdown(data))
    return 0


if __name__ == "__main__":
    sys.exit(main())
