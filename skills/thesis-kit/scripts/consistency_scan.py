"""Mechanical cross-chapter consistency inventory for the consolidation step.

Usage:
    python3 consistency_scan.py PATH [PATH ...] [--json]

PATH is a .tex file or a directory (searched recursively for *.tex). Every
finding carries file:line. Prose checks run on texutil.to_prose() output
(so comments, math, labels and citations are excluded); the citation check
runs on the comment-stripped source.

Checks
  1. Hyphenation and spacing variants: built-in compounds (pre-trained /
     pretrained / pre trained, data set / dataset, top-k / topk / top k ...)
     and any a-b whose closed form ab also occurs; per-form counts and the
     first location of each form. Open forms count only for the built-in
     compounds.
  2. US/UK spelling: built-in pairs with inflections (modeling/modelling,
     optimize/optimise ...); pairs used both ways, with the locations of the
     minority variant, and the overall US vs UK count per file.
  3. Acronym definitions such as "neural topic model (NTM)": acronyms
     defined more than once in a file, and acronyms whose expansions
     (lowercased, hyphens as spaces, singular) differ between files.
  4. Citation commands: per-file counts of \\cite, \\citep, \\citet,
     \\citealp, \\parencite, \\textcite; every bare \\cite{ when the files also
     use \\citep or \\citet.
  5. Verbatim overlap: paragraphs of 30+ words in different files sharing
     at least half of the smaller paragraph's word 6-grams.

Output: Markdown, one section per check ("none" when empty); --json gives a
dict keyed by check (hyphenation, spelling, acronyms, citations, overlap).
Exit codes: 0 = nothing found, 1 = something found, 2 = usage or file error.
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import texutil  # noqa: E402


class _Doc(object):
    """A source file with its prose view and line lookups."""

    def __init__(self, name, source):
        self.name = name
        self.source = source.replace("\r\n", "\n").replace("\r", "\n")
        self.prose = texutil.to_prose(self.source)
        self.flat = self.prose.replace("\n", " ")
        self.lines = texutil.LineIndex(self.prose)
        self.stripped = texutil.strip_comments(self.source)
        self.stripped_lines = texutil.LineIndex(self.stripped)

    def where(self, offset):
        return "%s:%d" % (self.name, self.lines.line(offset))


def _prepare(docs):
    return [d if isinstance(d, _Doc) else _Doc(*d) for d in docs]


# 1. Compounds written closed, hyphenated or open (open forms only here).
COMPOUNDS = [
    ["pre-trained", "pretrained", "pre trained"],
    ["fine-tuning", "finetuning", "fine tuning"],
    ["fine-tune", "finetune"],
    ["fine-tuned", "finetuned"],
    ["multi-head", "multihead"],
    ["data set", "dataset"],
    ["state-of-the-art", "state of the art"],
    ["large-scale", "large scale"],
    ["real-world", "real world"],
    ["end-to-end", "end to end"],
    ["non-linear", "nonlinear"],
    ["co-occurrence", "cooccurrence"],
    ["sub-word", "subword"],
    ["zero-shot", "zero shot"],
    ["few-shot", "few shot"],
    ["in-context", "in context"],
    ["top-k", "topk", "top k"],
]


# Forms that also take an -s (plural nouns, third-person verbs).
_TAKES_S = frozenset(["fine-tune", "finetune", "data set", "dataset",
                      "co-occurrence", "cooccurrence", "sub-word", "subword"])


def _form_regex(form):
    body = r"\s+".join(re.escape(part) for part in form.split())
    if form in _TAKES_S:
        body += "s?"
    return re.compile(r"(?<![\w-])" + body + r"(?![\w-])", re.IGNORECASE)


def _count(regex, docs):
    """Total matches over docs and the location of the first one."""
    count, first = 0, None
    for doc in docs:
        for m in regex.finditer(doc.flat):
            count += 1
            if first is None:
                first = doc.where(m.start())
    return count, first


_TOKEN_RE = re.compile(r"[^\W_]+(?:-[^\W_]+)*")
_TWO_PART_RE = re.compile(r"([^\W\d_]{2,})-([^\W\d_]{2,})")


def _token_table(docs):
    """Lowercased hyphen-joined tokens -> [count, first location]."""
    table = {}
    for doc in docs:
        for m in _TOKEN_RE.finditer(doc.flat):
            entry = table.setdefault(m.group(0).lower(),
                                     [0, doc.where(m.start())])
            entry[0] += 1
    return table


def check_hyphenation(docs):
    """Compounds written in two or more ways (closed, hyphenated, open)."""
    docs = _prepare(docs)
    groups = []
    builtin = []
    for forms in COMPOUNDS:
        regexes = [_form_regex(form) for form in forms]
        builtin.extend(regexes)
        found = []
        for form, regex in zip(forms, regexes):
            count, first = _count(regex, docs)
            if count:
                found.append({"form": form, "count": count, "first": first})
        if len(found) >= 2:
            groups.append({"group": "/".join(forms), "forms": found})
    # Any other a-b whose closed form ab also occurs (open forms are
    # ordinary phrases too often to count here).
    table = _token_table(docs)
    general = []
    for token, (count, first) in table.items():
        m = _TWO_PART_RE.fullmatch(token)
        closed = m and table.get(m.group(1) + m.group(2))
        if not closed or any(rx.fullmatch(token) for rx in builtin):
            continue
        general.append({"group": "%s/%s" % (token, m.group(1) + m.group(2)),
                        "forms": [
                            {"form": token, "count": count, "first": first},
                            {"form": m.group(1) + m.group(2),
                             "count": closed[0], "first": closed[1]}]})
    return (groups + sorted(general, key=lambda g: g["group"])
            + _letter_digit_groups(docs))


# Names made of letters and a number, such as F1 / F-1 or ROUGE-1 / ROUGE1.
_LETTER_DIGIT_RE = re.compile(r"(?<![\w-])([A-Za-z]{1,12})(-?)(\d{1,4})(?![\w-]|\.\d)")


def _letter_digit_groups(docs):
    """Letter-digit names that occur both with and without the hyphen."""
    seen = {}
    for doc in docs:
        for m in _LETTER_DIGIT_RE.finditer(doc.flat):
            key = (m.group(1).lower(), m.group(3))
            kind = "hyphenated" if m.group(2) else "closed"
            entry = seen.setdefault(key, {}).setdefault(
                kind, {"form": m.group(0), "count": 0, "first": doc.where(m.start())})
            entry["count"] += 1
    groups = []
    for forms in seen.values():
        if len(forms) == 2:
            hyphenated, closed = forms["hyphenated"], forms["closed"]
            groups.append({"group": "%s/%s" % (hyphenated["form"], closed["form"]),
                           "forms": [hyphenated, closed]})
    return sorted(groups, key=lambda g: g["group"])


# 2. US/UK spelling pairs: (label, US forms, UK forms). Matches are
# case-insensitive whole words; any letters may precede a form, so
# "unlabelled" and "reorganize" count.
_IZE = ["e", "es", "ed", "ing", "er", "ers", "able"]
_ATION = ["ation", "ations"]


def _ize(label, us_stem, uk_stem, suffixes=None, drop=()):
    suffixes = suffixes or _IZE
    return (label, [us_stem + s for s in suffixes],
            [uk_stem + s for s in suffixes if uk_stem + s not in drop])


def _nouns(label, us, uk):
    return (label, [us, us + "s"], [uk, uk + "s"])


SPELLING_PAIRS = [
    ("modeling/modelling", ["modeling", "modeler", "modelers"],
     ["modelling", "modeller", "modellers"]),
    ("modeled/modelled", ["modeled"], ["modelled"]),
    ("labeled/labelled", ["labeled"], ["labelled"]),
    ("labeling/labelling", ["labeling", "labeler", "labelers"],
     ["labelling", "labeller", "labellers"]),
    ("behavior/behaviour",
     ["behavior", "behaviors", "behavioral", "behaviorally"],
     ["behaviour", "behaviours", "behavioural", "behaviourally"]),
    ("color/colour",
     ["color", "colors", "colored", "coloring", "colorful", "colorless"],
     ["colour", "colours", "coloured", "colouring", "colourful",
      "colourless"]),
    ("favor/favour",
     ["favor", "favors", "favored", "favoring", "favorable", "favorably",
      "favorite", "favorites"],
     ["favour", "favours", "favoured", "favouring", "favourable",
      "favourably", "favourite", "favourites"]),
    ("center/centre", ["center", "centers", "centered", "centering"],
     ["centre", "centres", "centred", "centring"]),
    # "analyses" is also the plural of "analysis", so it is not counted.
    _ize("analyze/analyse", "analyz", "analys", drop=("analyses",)),
    _ize("optimize/optimise", "optimiz", "optimis"),
    _nouns("optimization/optimisation", "optimization", "optimisation"),
    _nouns("generalization/generalisation", "generalization",
           "generalisation"),
    _ize("normalize/normalise", "normaliz", "normalis"),
    _nouns("normalization/normalisation", "normalization", "normalisation"),
    _nouns("regularization/regularisation", "regularization",
           "regularisation"),
    _ize("summarize/summarise", "summariz", "summaris"),
    _nouns("summarization/summarisation", "summarization", "summarisation"),
    # -ization nouns that have no pair of their own are folded in here.
    _ize("initialize/initialise", "initializ", "initialis", _IZE + _ATION),
    _ize("utilize/utilise", "utiliz", "utilis", _IZE + _ATION),
    _ize("organize/organise", "organiz", "organis", _IZE + _ATION),
    _ize("recognize/recognise", "recogniz", "recognis"),
    _ize("characterize/characterise", "characteriz", "characteris",
         _IZE + _ATION),
    _ize("emphasize/emphasise", "emphasiz", "emphasis"),
    _ize("minimize/minimise", "minimiz", "minimis", _IZE + _ATION),
    _ize("maximize/maximise", "maximiz", "maximis", _IZE + _ATION),
    _ize("tokenize/tokenise", "tokeniz", "tokenis"),
    _nouns("tokenization/tokenisation", "tokenization", "tokenisation"),
]


def _spelling_regex(forms):
    alternatives = "|".join(sorted((re.escape(f) for f in forms),
                                   key=len, reverse=True))
    return re.compile(r"(?<!\w)[^\W\d_]*(?:%s)(?!\w)" % alternatives,
                      re.IGNORECASE)


def _variant_hits(regex, docs):
    return [(doc.name, doc.where(m.start()), m.group(0))
            for doc in docs for m in regex.finditer(doc.flat)]


def check_spelling(docs):
    """US/UK pairs used both ways, and the overall US vs UK count."""
    docs = _prepare(docs)
    per_file = dict((d.name, {"us": 0, "uk": 0}) for d in docs)
    found = []
    all_hits = {"us": [], "uk": []}
    for label, us_forms, uk_forms in SPELLING_PAIRS:
        hits = {"us": _variant_hits(_spelling_regex(us_forms), docs),
                "uk": _variant_hits(_spelling_regex(uk_forms), docs)}
        for side in ("us", "uk"):
            all_hits[side].extend(hits[side])
            for name, _, _ in hits[side]:
                per_file[name][side] += 1
        found.append((label, hits))
    us, uk = len(all_hits["us"]), len(all_hits["uk"])
    overall_minority = None
    if us and uk:
        overall_minority = "us" if us < uk else "uk"
    pairs = []
    for label, hits in found:
        n_us, n_uk = len(hits["us"]), len(hits["uk"])
        if n_us and n_uk:
            if n_us != n_uk:
                minority = "us" if n_us < n_uk else "uk"
            else:
                minority = overall_minority or "uk"
            pairs.append({"pair": label, "us": n_us, "uk": n_uk,
                          "minority": minority,
                          "minority_locations": [
                              {"location": where, "word": word}
                              for _, where, word in hits[minority]]})
    overall = {"us": us, "uk": uk, "per_file": per_file,
               "minority": overall_minority,
               "minority_locations": [
                   {"location": where, "word": word}
                   for _, where, word in all_hits.get(overall_minority, [])]}
    return {"pairs": pairs, "overall": overall}


# 3. Acronym definitions: "neural topic model (NTM)".
# An expansion does not reach back past punctuation or a paragraph break.
_CLAUSE_END_RE = re.compile(r"[.!?;:()\[\]]|\n\n")
_EXPANSION_WORD_RE = re.compile(r"[^\W_]+(?:['’-][^\W_]+)*")


def _acronym_base(acronym):
    """The acronym without a plural s: SAEs -> SAE."""
    if acronym.endswith("s") and sum(c.isupper() for c in acronym[:-1]) >= 2:
        return acronym[:-1]
    return acronym


def _loose_match(letters, parts):
    """First letter starts the first part; the others follow in order."""
    text = " ".join(parts).lower()
    if not text.startswith(letters[0]):
        return False
    i = len(text) - 1
    for letter in reversed(letters[1:]):
        while i >= 1 and text[i] != letter:
            i -= 1
        if i < 1:
            return False
        i -= 1
    return True


def find_expansion(before, acronym):
    """Shortest run of up to 8 words at the end of `before` that matches
    the acronym's letters loosely (hyphenated parts count as words), or
    None. The run does not reach back past a sentence or clause end."""
    letters = [c.lower() for c in _acronym_base(acronym) if c.isalpha()]
    if len(letters) < 2:
        return None
    clause = _CLAUSE_END_RE.split(before)[-1]
    tokens = _EXPANSION_WORD_RE.findall(clause)[-8:]
    for k in range(1, len(tokens) + 1):
        run = tokens[-k:]
        parts = [p for token in run for p in token.split("-") if p]
        if _loose_match(letters, parts):
            return " ".join(run)
    return None


# "(NTM)", "(SAEs)", "(LoRA)": 2-10 characters with 2+ capitals, plural s.
_ACRONYM_RE = re.compile(r"\(([A-Za-z][A-Za-z0-9-]{1,10})\)")


def _singular(word):
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith(("sses", "xes", "ches", "shes")):
        return word[:-2]
    if word.endswith(("ss", "us", "is")):
        return word
    return word[:-1] if word.endswith("s") else word


def normalize_expansion(expansion):
    """Lowercase, hyphens to spaces, last word singular."""
    words = expansion.lower().replace("-", " ").split()
    if words:
        words[-1] = _singular(words[-1])
    return " ".join(words)


def _definitions(doc):
    """(acronym, line, normalized expansion) for each definition in doc."""
    found = []
    for m in _ACRONYM_RE.finditer(doc.prose):
        acronym = _acronym_base(m.group(1))
        if not (2 <= len(acronym) <= 10
                and sum(c.isupper() for c in acronym) >= 2):
            continue
        before = doc.prose[max(0, m.start() - 400):m.start()]
        expansion = find_expansion(before, m.group(1))
        if expansion:
            found.append((acronym, doc.lines.line(m.start()),
                          normalize_expansion(expansion)))
    return found


def check_acronyms(docs):
    """Acronyms defined twice in a file; expansions that differ by file."""
    docs = _prepare(docs)
    duplicates = []
    by_acronym = {}     # acronym -> {expansion: [locations]}, in order
    files_of = {}       # acronym -> set of files
    for doc in docs:
        lines_of = {}
        for acronym, line, expansion in _definitions(doc):
            lines_of.setdefault(acronym, []).append(line)
            by_acronym.setdefault(acronym, {}).setdefault(
                expansion, []).append("%s:%d" % (doc.name, line))
            files_of.setdefault(acronym, set()).add(doc.name)
        duplicates.extend({"acronym": acronym, "file": doc.name,
                           "lines": lines}
                          for acronym, lines in sorted(lines_of.items())
                          if len(lines) > 1)
    conflicts = [{"acronym": acronym, "expansions": [
                     {"expansion": e, "locations": locs}
                     for e, locs in expansions.items()]}
                 for acronym, expansions in sorted(by_acronym.items())
                 if len(expansions) > 1 and len(files_of[acronym]) > 1]
    return {"duplicates": duplicates, "conflicts": conflicts}


# 4. Citation commands, counted on the comment-stripped source.
CITE_COMMANDS = ["cite", "citep", "citet", "citealp", "parencite", "textcite"]
_CITE_RE = re.compile(r"\\(%s)(?![A-Za-z])" % "|".join(CITE_COMMANDS))
_BARE_CITE_RE = re.compile(r"\\cite(?![A-Za-z])\*?\s*(?:\[[^\]]*\]\s*){0,2}\{")


def check_citations(docs):
    """Per-file citation command counts; bare \\cite{ next to natbib."""
    docs = _prepare(docs)
    counts = {}
    for doc in docs:
        per_command = dict.fromkeys(CITE_COMMANDS, 0)
        for m in _CITE_RE.finditer(doc.stripped):
            per_command[m.group(1)] += 1
        counts[doc.name] = per_command
    bare = []
    if any(c["citep"] or c["citet"] for c in counts.values()):
        for doc in docs:
            for m in _BARE_CITE_RE.finditer(doc.stripped):
                location = "%s:%d" % (doc.name, doc.stripped_lines.line(m.start()))
                if location not in bare:
                    bare.append(location)
    return {"counts": counts, "bare_cite": bare}


# 5. Verbatim overlap between paragraphs of different files.
OVERLAP_MIN_WORDS = 30
OVERLAP_SHINGLE = 6


def _shingled_paragraphs(docs):
    paras = []
    for doc in docs:
        for line, text in texutil.paragraphs(doc.prose):
            ws = texutil.words(text)
            if len(ws) < OVERLAP_MIN_WORDS:
                continue
            low = [w.lower() for w in ws]
            shingles = set(tuple(low[i:i + OVERLAP_SHINGLE])
                           for i in range(len(low) - OVERLAP_SHINGLE + 1))
            paras.append(("%s:%d" % (doc.name, line), doc.name, shingles, ws))
    return paras


def check_overlap(docs):
    """Paragraph pairs (different files) sharing >= 50% of the smaller
    paragraph's word 6-grams."""
    docs = _prepare(docs)
    paras = _shingled_paragraphs(docs)
    postings = {}
    for pid, para in enumerate(paras):
        for shingle in para[2]:
            postings.setdefault(shingle, []).append(pid)
    shared = {}
    for pids in postings.values():
        for x, a in enumerate(pids):
            for b in pids[x + 1:]:
                if paras[a][1] != paras[b][1]:
                    shared[(a, b)] = shared.get((a, b), 0) + 1
    found = []
    for (a, b), count in shared.items():
        smaller = min(len(paras[a][2]), len(paras[b][2]))
        if 2 * count >= smaller:
            found.append((-count / smaller, a, b, {
                "a": paras[a][0], "b": paras[b][0],
                "overlap": round(count / smaller, 2), "shared": count,
                "words": " ".join(paras[a][3][:10])}))
    return [item for _, _, _, item in sorted(found, key=lambda f: f[:3])]


CHECKS = ["hyphenation", "spelling", "acronyms", "citations", "overlap"]


def scan(docs):
    """All five checks over docs, a list of (name, source)."""
    docs = _prepare(docs)
    return {"hyphenation": check_hyphenation(docs),
            "spelling": check_spelling(docs),
            "acronyms": check_acronyms(docs),
            "citations": check_citations(docs),
            "overlap": check_overlap(docs)}


def findings(result):
    """Names of the checks that found something."""
    spelling = result["spelling"]
    found = {
        "hyphenation": bool(result["hyphenation"]),
        "spelling": bool(spelling["pairs"]
                         or (spelling["overall"]["us"]
                             and spelling["overall"]["uk"])),
        "acronyms": bool(result["acronyms"]["duplicates"]
                         or result["acronyms"]["conflicts"]),
        "citations": bool(result["citations"]["bare_cite"]),
        "overlap": bool(result["overlap"]),
    }
    return [name for name in CHECKS if found[name]]


class UsageError(Exception):
    pass


def collect_files(paths):
    """.tex files named directly or found under directories, in order."""
    files, seen = [], set()
    for path in paths:
        if os.path.isdir(path):
            found = []
            for root, dirs, names in os.walk(path):
                dirs.sort()
                found.extend(os.path.join(root, n) for n in names
                             if n.endswith(".tex"))
            if not found:
                raise UsageError("no .tex files under %s" % path)
            candidates = sorted(found)
        elif os.path.isfile(path):
            candidates = [path]
        else:
            raise UsageError("no such file or directory: %s" % path)
        for name in candidates:
            if os.path.realpath(name) not in seen:
                seen.add(os.path.realpath(name))
                files.append(name)
    return files


def _md_hyphenation(groups):
    if not groups:
        return ["none"]
    return ["- **%s**: %s" % (g["group"], "; ".join(
        "%s %d (first %s)" % (f["form"], f["count"], f["first"])
        for f in g["forms"])) for g in groups]


def _md_spelling(spelling):
    overall = spelling["overall"]
    out = ["Overall: US %d, UK %d." % (overall["us"], overall["uk"]), "",
           "| File | US | UK |", "|---|---|---|"]
    out += ["| %s | %d | %d |" % (name, c["us"], c["uk"])
            for name, c in overall["per_file"].items()]
    out += ["", "Pairs used both ways:", ""]
    if spelling["pairs"]:
        out += ["- **%s**: US %d, UK %d; %s (minority): %s" % (
            p["pair"], p["us"], p["uk"], p["minority"].upper(),
            ", ".join("%s (%s)" % (x["location"], x["word"])
                      for x in p["minority_locations"]))
            for p in spelling["pairs"]]
    else:
        out.append("none")
    if overall["minority"]:
        out += ["", "All %s spellings (%s): %s" % (
            overall["minority"].upper(),
            "US and UK are tied" if overall["us"] == overall["uk"]
            else "the overall minority",
            ", ".join("%s (%s)" % (x["location"], x["word"])
                      for x in overall["minority_locations"]))]
    return out


def _md_acronyms(acronyms):
    out = ["Defined more than once in the same file:", ""]
    out += ["- %s in %s: lines %s" % (d["acronym"], d["file"],
                                      ", ".join(str(n) for n in d["lines"]))
            for d in acronyms["duplicates"]] or ["none"]
    out += ["", "Expansions that differ between files:", ""]
    out += ["- **%s**: %s" % (c["acronym"], "; ".join(
        '"%s" (%s)' % (e["expansion"], ", ".join(e["locations"]))
        for e in c["expansions"])) for c in acronyms["conflicts"]] or ["none"]
    return out


def _md_citations(citations):
    out = ["| File | %s |" % " | ".join("\\" + c for c in CITE_COMMANDS),
           "|---|%s" % ("---|" * len(CITE_COMMANDS))]
    out += ["| %s | %s |" % (name, " | ".join(str(counts[c])
                                              for c in CITE_COMMANDS))
            for name, counts in citations["counts"].items()]
    out += ["", "Bare \\cite{ while \\citep or \\citet are in use:", ""]
    out += ["- " + where for where in citations["bare_cite"]] or ["none"]
    return out


def _md_overlap(overlap):
    if not overlap:
        return ["none"]
    return ["- %s and %s: %d%% of 6-word shingles shared (%d): \"%s ...\"" % (
        o["a"], o["b"], round(100 * o["overlap"]), o["shared"], o["words"])
        for o in overlap]


def render_markdown(result, files):
    out = ["# Consistency scan", "", "Scanned %d file%s." % (
        len(files), "" if len(files) == 1 else "s"), ""]
    sections = [
        ("1. Hyphenation and spacing variants",
         _md_hyphenation(result["hyphenation"])),
        ("2. US/UK spelling", _md_spelling(result["spelling"])),
        ("3. Acronym definitions", _md_acronyms(result["acronyms"])),
        ("4. Citation commands", _md_citations(result["citations"])),
        ("5. Verbatim overlap (paragraphs of %d+ words)" % OVERLAP_MIN_WORDS,
         _md_overlap(result["overlap"])),
    ]
    for title, body in sections:
        out += ["## " + title, ""] + body + [""]
    return "\n".join(out)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Cross-chapter consistency inventory: hyphenation and "
                    "spacing variants, US/UK spelling, acronym definitions, "
                    "citation commands and verbatim overlap. Exits 1 when "
                    "anything is found, 0 when all checks are empty.")
    parser.add_argument("paths", nargs="+", metavar="PATH",
                        help=".tex files or directories (searched "
                             "recursively for *.tex)")
    parser.add_argument("--json", action="store_true",
                        help="print JSON (a dict keyed by check)")
    args = parser.parse_args(argv)
    try:
        files = collect_files(args.paths)
        docs = [(name, texutil.read_tex(name)) for name in files]
    except UsageError as err:
        print("consistency_scan.py: %s" % err, file=sys.stderr)
        return 2
    except OSError as err:
        print("consistency_scan.py: cannot read %s: %s"
              % (err.filename, err.strerror), file=sys.stderr)
        return 2
    result = scan(docs)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        sys.stdout.write(render_markdown(result, files))
    return 1 if findings(result) else 0


if __name__ == "__main__":
    sys.exit(main())
