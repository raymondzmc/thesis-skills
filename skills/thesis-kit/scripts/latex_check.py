#!/usr/bin/env python3
r"""Check a LaTeX thesis for broken references, citations, figures and builds.

Usage:
    python3 latex_check.py MAIN.tex [--build] [--engine pdflatex|xelatex|lualatex] [--json]

Static checks (always run, no TeX needed) cover MAIN.tex and every file it
\input's or \include's, recursively, with % comments stripped:
  * \ref, \autoref, \cref, \Cref, \eqref, \pageref, \nameref to labels
    that are never defined, and labels defined more than once;
  * citation keys (natbib and biblatex commands) missing from the .bib files
    named by \bibliography{a,b} or \addbibresource{x.bib} (\bibitem keys count);
  * duplicate .bib keys, and probable duplicate entries (different keys,
    same title once lowercased with braces, punctuation and spaces removed);
  * \includegraphics files that do not exist (also tried with .pdf .png .jpg
    .jpeg .eps, and under \graphicspath directories);
  * \input/\include and .bib files that do not exist (files that kpsewhich
    finds in the TeX distribution are fine).

--build compiles MAIN in its own directory (latexmk when installed, otherwise
engine, bibtex or biber, engine, engine; 600 s per step) and reads MAIN.log
for errors, undefined references and citations, multiply-defined labels,
missing files, overfull boxes and a leftover "Rerun to get" message.  With
pdftotext installed, the PDF is searched for "??" per page.

Problems: everything above except overfull boxes of 10pt or less, the rerun
message and the "??" counts, which are reported as info.

Exit codes: 0 = no problems, 1 = problems found, 2 = usage error or a build
tool is missing.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys

# A % starts a comment unless escaped; an even run of backslashes before it
# (as in the line break \\%) does not escape it.
COMMENT_RE = re.compile(r"(?<!\\)((?:\\\\)*)%.*$", re.MULTILINE)
LABEL_RE = re.compile(r"\\label\s*(?:\[[^\]]*\]\s*)?\{([^}]*)\}")
REF_RE = re.compile(
    r"\\(ref|autoref|cref|Cref|eqref|pageref|nameref)\*?\s*\{([^}]*)\}")
INPUT_RE = re.compile(r"\\(input|include)\s*\{([^}]*)\}")
# natbib and biblatex citation commands whose (last) braced argument is a key
# list.  \citestyle and friends take no keys and are deliberately absent.
CITE_COMMANDS = (
    "cite", "citep", "citet", "citealp", "citealt", "citeauthor", "citeyear",
    "citeyearpar", "citenum", "parencite", "textcite", "autocite", "footcite",
    "smartcite", "supercite", "fullcite", "nocite",
    "Cite", "Citep", "Citet", "Citealp", "Citealt", "Citeauthor",
    "Parencite", "Textcite", "Autocite", "Footcite", "Smartcite",
)
CITE_RE = re.compile(
    r"\\(" + "|".join(sorted(CITE_COMMANDS, key=len, reverse=True)) + r")"
    r"\*?(?:\s*\[[^\]]*\]){0,2}\s*\{([^}]*)\}")
BIBITEM_RE = re.compile(r"\\bibitem\s*(?:\[[^\]]*\]\s*)?\{([^}]*)\}")
BIBLIOGRAPHY_RE = re.compile(r"\\bibliography\s*\{([^}]*)\}")
ADDBIBRESOURCE_RE = re.compile(
    r"\\addbibresource\s*(?:\[[^\]]*\]\s*)?\{([^}]*)\}")
GRAPHICS_RE = re.compile(
    r"\\includegraphics\*?\s*(?:\[[^\]]*\]\s*){0,2}\{([^}]*)\}")
GRAPHICS_EXTENSIONS = (".pdf", ".png", ".jpg", ".jpeg", ".eps")
GRAPHICSPATH_RE = re.compile(r"\\graphicspath\s*\{((?:\s*\{[^}]*\})*)\s*\}")
BIB_AT_RE = re.compile(r"@\s*([A-Za-z]+)\s*([{(])")
BIB_FIELD_RE = re.compile(r"\s*([A-Za-z][\w\-:.+/]*)\s*=\s*")
BIB_BARE_RE = re.compile(r"[^\s,#}]+")


def strip_comments(text):
    """Remove % comments but keep every newline, so line numbers still match."""
    return COMMENT_RE.sub(r"\1", text)


def _read(path):
    """Read a text file; bytes that are not UTF-8 (e.g. latin-1) are replaced."""
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def _literal(key):
    """Keys holding a macro parameter (#1) or a macro (\\x) are only known
    after expansion, e.g. inside \\newcommand bodies; they are not checked."""
    return bool(key) and "#" not in key and "\\" not in key


def _split_keys(arg):
    return [k.strip() for k in arg.split(",") if _literal(k.strip())]


def _line_of(text, pos):
    return text.count("\n", 0, pos) + 1


def _display_path(path, root):
    """PATH relative to the project root, or absolute when it lies outside."""
    rel = os.path.relpath(os.path.abspath(path), root)
    return os.path.abspath(path) if rel.startswith("..") else rel


def _input_candidates(name):
    return [name] if name.endswith(".tex") else [name + ".tex", name]


def _kpsewhich(name, cwd):
    """Path of NAME as found by kpsewhich (when installed), e.g. a file shipped
    with the TeX distribution such as glyphtounicode.tex or IEEEabrv.bib."""
    exe = shutil.which("kpsewhich")
    if not exe:
        return None
    try:
        out = subprocess.run([exe, name], cwd=cwd, capture_output=True,
                             text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    found = out.stdout.strip()
    return os.path.join(cwd, found) if found else None


def collect_sources(main_path):
    """Read MAIN and every file it \\input's or \\include's, depth-first.

    Paths are resolved relative to MAIN's directory, as LaTeX does.  Returns
    (sources, missing): sources is [(relative path, comment-stripped text)]
    and missing lists the input commands whose file does not exist."""
    root = os.path.dirname(os.path.abspath(main_path))
    sources = []
    missing = []
    seen = set()

    def visit(path):
        rel = os.path.relpath(path, root)
        if rel in seen:
            return
        seen.add(rel)
        text = strip_comments(_read(path))
        sources.append((rel, text))
        for m in INPUT_RE.finditer(text):
            name = m.group(2).strip()
            for cand in _input_candidates(name):
                cand_path = os.path.join(root, cand)
                if os.path.isfile(cand_path):
                    visit(cand_path)
                    break
            else:
                if not any(_kpsewhich(c, root)
                           for c in _input_candidates(name)):
                    missing.append({"path": name, "file": rel,
                                    "line": _line_of(text, m.start())})

    visit(os.path.abspath(main_path))
    return sources, missing


def _brace_end(text, start):
    """Index of the } closing a group whose body starts at START."""
    depth = 1
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return i
    return len(text)


def _paren_end(text, start):
    """Index of the ) closing an @entry( ... ) whose body starts at START."""
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
        elif text[i] == ")" and depth <= 0:
            return i
    return len(text)


def _quote_end(text, start):
    """Index of the " closing a quoted value (quotes inside braces are text)."""
    depth = 0
    for i in range(start, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        elif ch == '"' and depth <= 0:
            return i
    return len(text)


def _parse_fields(body):
    """Parse 'name = value, ...' where a value is {...}, "..." or a bare word,
    possibly joined with #.  Field names are lowercased; macros stay unexpanded."""
    fields = {}
    i, n = 0, len(body)
    while i < n:
        m = BIB_FIELD_RE.match(body, i)
        if not m:
            comma = body.find(",", i)
            if comma < 0:
                break
            i = comma + 1
            continue
        name, i = m.group(1).lower(), m.end()
        parts = []
        while i < n:
            if body[i] == "{":
                end = _brace_end(body, i + 1)
                parts.append(body[i + 1:end])
                i = end + 1
            elif body[i] == '"':
                end = _quote_end(body, i + 1)
                parts.append(body[i + 1:end])
                i = end + 1
            else:
                bare = BIB_BARE_RE.match(body, i)
                if not bare:
                    break
                parts.append(bare.group(0))
                i = bare.end()
            while i < n and body[i].isspace():
                i += 1
            if i < n and body[i] == "#":
                i += 1
                while i < n and body[i].isspace():
                    i += 1
                continue
            break
        fields[name] = "".join(parts)
        while i < n and body[i] != ",":
            i += 1
        i += 1
    return fields


def parse_bib(text):
    """Return the entries of a .bib file as [{"key", "type", "line", "fields"}].
    @string, @preamble and @comment blocks are skipped."""
    entries = []
    pos = 0
    while True:
        m = BIB_AT_RE.search(text, pos)
        if not m:
            break
        start = m.end()
        if m.group(2) == "{":
            end = _brace_end(text, start)
        else:
            end = _paren_end(text, start)
        pos = end + 1
        kind = m.group(1).lower()
        if kind in ("string", "preamble", "comment"):
            continue
        key, _, rest = text[start:end].partition(",")
        if not key.strip():
            continue
        entries.append({"key": key.strip(), "type": kind,
                        "line": _line_of(text, m.start()),
                        "fields": _parse_fields(rest)})
    return entries


def normalize_title(title):
    """Lowercase and drop braces, punctuation and whitespace."""
    return re.sub(r"[\W_]+", "", title.lower())


def _check_labels_and_refs(sources):
    labels = {}
    for rel, text in sources:
        for m in LABEL_RE.finditer(text):
            key = m.group(1).strip()
            if _literal(key):
                labels.setdefault(key, []).append(
                    {"file": rel, "line": _line_of(text, m.start())})
    problems = []
    for rel, text in sources:
        for m in REF_RE.finditer(text):
            for key in _split_keys(m.group(2)):
                if key not in labels:
                    problems.append({"type": "undefined-ref", "key": key,
                                     "command": "\\" + m.group(1),
                                     "file": rel,
                                     "line": _line_of(text, m.start())})
    for key, locations in labels.items():
        if len(locations) > 1:
            problems.append({"type": "duplicate-label", "key": key,
                             "locations": locations})
    return problems


def _load_bibliography(sources, root):
    """Read every .bib file named by \\bibliography or \\addbibresource.
    Returns (entries, display paths of the files read, problems)."""
    named = []  # (bib file name, file naming it, line)
    for rel, text in sources:
        for m in BIBLIOGRAPHY_RE.finditer(text):
            line = _line_of(text, m.start())
            for name in _split_keys(m.group(1)):
                named.append((name if name.endswith(".bib") else name + ".bib",
                              rel, line))
        for m in ADDBIBRESOURCE_RE.finditer(text):
            named.append((m.group(1).strip(), rel, _line_of(text, m.start())))
    entries, files, problems, seen = [], [], [], set()
    for name, rel, line in named:
        path = os.path.join(root, name)
        if not os.path.isfile(path):
            path = _kpsewhich(name, root)
        if not path:
            problems.append({"type": "missing-bib-file", "path": name,
                             "file": rel, "line": line})
            continue
        if os.path.realpath(path) in seen:  # e.g. one refs.bib per chapter
            continue
        seen.add(os.path.realpath(path))
        files.append(_display_path(path, root))
        for entry in parse_bib(_read(path)):
            entry["file"] = files[-1]
            entries.append(entry)
    return entries, files, problems


def _check_bib_duplicates(entries):
    problems = []
    by_key = {}
    for entry in entries:
        by_key.setdefault(entry["key"], []).append(
            {"file": entry["file"], "line": entry["line"]})
    for key, locations in by_key.items():
        if len(locations) > 1:
            problems.append({"type": "duplicate-bib-key", "key": key,
                             "locations": locations})
    by_title = {}
    for entry in entries:
        norm = normalize_title(entry["fields"].get("title", ""))
        if norm:
            by_title.setdefault(norm, []).append(entry)
    for group in by_title.values():
        keys = _unique(entry["key"] for entry in group)
        if len(keys) > 1:
            problems.append({
                "type": "probable-duplicate-entry",
                "keys": keys,
                "title": group[0]["fields"]["title"],
                "locations": [{"file": e["file"], "line": e["line"]}
                              for e in group],
            })
    return problems


def _check_citations(sources, entries):
    known = set(entry["key"] for entry in entries)
    for _, text in sources:
        known.update(m.group(1).strip() for m in BIBITEM_RE.finditer(text))
    problems = []
    for rel, text in sources:
        for m in CITE_RE.finditer(text):
            for key in _split_keys(m.group(2)):
                if key != "*" and key not in known:
                    problems.append({"type": "missing-citation", "key": key,
                                     "command": "\\" + m.group(1),
                                     "file": rel,
                                     "line": _line_of(text, m.start())})
    return problems


def _check_graphics(sources, root):
    dirs = [""]
    for _, text in sources:
        for m in GRAPHICSPATH_RE.finditer(text):
            dirs.extend(re.findall(r"\{([^}]*)\}", m.group(1)))
    problems = []
    for rel, text in sources:
        for m in GRAPHICS_RE.finditer(text):
            name = m.group(1).strip()
            if not _literal(name):
                continue
            names = [name] + [name + ext for ext in GRAPHICS_EXTENSIONS]
            if not any(os.path.isfile(os.path.join(root, d, cand))
                       for d in dirs for cand in names):
                problems.append({"type": "missing-graphic", "path": name,
                                 "file": rel,
                                 "line": _line_of(text, m.start())})
    return problems


def _bib_tool(sources):
    """biber for biblatex (\\addbibresource), bibtex for \\bibliography."""
    if any(ADDBIBRESOURCE_RE.search(text) for _, text in sources):
        return "biber"
    if any(BIBLIOGRAPHY_RE.search(text) for _, text in sources):
        return "bibtex"
    return None


def static_check(main_path):
    """Run every check that needs no TeX installation."""
    root = os.path.dirname(os.path.abspath(main_path))
    sources, missing_inputs = collect_sources(main_path)
    entries, bib_files, bib_problems = _load_bibliography(sources, root)
    problems = (_check_labels_and_refs(sources)
                + _check_citations(sources, entries)
                + _check_bib_duplicates(entries)
                + _check_graphics(sources, root)
                + [dict(item, type="missing-input") for item in missing_inputs]
                + bib_problems)
    return {"main": main_path, "files": [rel for rel, _ in sources],
            "bib_files": bib_files, "bib_tool": _bib_tool(sources),
            "problems": problems, "info": [], "build": None}


def _unique(items):
    out = []
    for item in items:
        if item not in out:
            out.append(item)
    return out


LOG_INPUT_LINE_RE = re.compile(r"^l\.(\d+)")
LOG_MULTIPLY_RE = re.compile(r"Label [`']([^']*)' multiply defined")
LOG_MISSING_FILE_RE = re.compile(r"File [`']([^']*)' not found")
LOG_OVERFULL_RE = re.compile(
    r"^Overfull \\([hv]box) \((\d+(?:\.\d+)?)pt too (?:wide|high)\)(.*)$",
    re.MULTILINE)
LOG_BOX_LINES_RE = re.compile(r"\blines? (\d+(?:--\d+)?)")
LOG_UNDEFINED_RE = re.compile(
    r"(Reference|Citation) [`']([^']*)' on page (\S+) undefined"
    r"(?: on input line (\d+))?")


LOG_WRAP = 79  # TeX's default max_print_line
# Lines that start a new message are never the continuation of a wrapped line,
# even when the line before them happens to be exactly LOG_WRAP long.
LOG_NEW_MESSAGE_RE = re.compile(
    r"^(?:! |LaTeX |Package |Class |Overfull \\|Underfull \\|l\.\d+ )")


def unwrap_log(text):
    """Rejoin log lines that TeX broke at max_print_line characters."""
    out = []
    joining = False
    for line in text.splitlines():
        if joining and not LOG_NEW_MESSAGE_RE.match(line):
            out[-1] += line
        else:
            out.append(line)
        # pdfTeX counts bytes, XeTeX counts characters.
        joining = LOG_WRAP in (len(line),
                               len(line.encode("utf-8", "replace")))
    return "\n".join(out)


def parse_log(text):
    """Parse a LaTeX .log into errors, warnings and box reports."""
    text = unwrap_log(text)
    lines = text.splitlines()
    errors = []
    for i, line in enumerate(lines):
        if not line.startswith("! "):
            continue
        input_line = None
        for follow in lines[i + 1:i + 15]:
            if follow.startswith("! "):
                break
            m = LOG_INPUT_LINE_RE.match(follow)
            if m:
                input_line = int(m.group(1))
                break
        errors.append({"message": line[2:].strip(), "line": input_line})
    undefined = {"Reference": [], "Citation": []}
    for m in LOG_UNDEFINED_RE.finditer(text):
        undefined[m.group(1)].append({
            "key": m.group(2), "page": m.group(3),
            "input_line": int(m.group(4)) if m.group(4) else None})
    return {"errors": errors, "undefined_refs": undefined["Reference"],
            "undefined_citations": undefined["Citation"],
            "multiply_defined_labels": _unique(
                m.group(1) for m in LOG_MULTIPLY_RE.finditer(text)),
            "missing_files": _unique(
                m.group(1) for m in LOG_MISSING_FILE_RE.finditer(text)),
            "overfull_boxes": [_overfull(m)
                               for m in LOG_OVERFULL_RE.finditer(text)],
            "rerun": next((l.strip() for l in lines if "Rerun to get" in l),
                          None)}


def _overfull(m):
    lines = LOG_BOX_LINES_RE.search(m.group(3))
    return {"box": m.group(1), "size_pt": float(m.group(2)),
            "lines": lines.group(1) if lines else None,
            "text": m.group(0).strip()}


OVERFULL_LIMIT_PT = 10.0


def log_findings(parsed):
    """Split parse_log() output into (problems, info) items."""
    problems, info = [], []
    for error in parsed["errors"]:
        problems.append(dict(error, type="latex-error"))
    for ref in parsed["undefined_refs"]:
        problems.append(dict(ref, type="log-undefined-ref"))
    for cite in parsed["undefined_citations"]:
        problems.append(dict(cite, type="log-undefined-citation"))
    for key in parsed["multiply_defined_labels"]:
        problems.append({"type": "log-multiply-defined-label", "key": key})
    for name in parsed["missing_files"]:
        problems.append({"type": "log-missing-file", "path": name})
    for box in parsed["overfull_boxes"]:
        if box["size_pt"] > OVERFULL_LIMIT_PT:
            problems.append(dict(box, type="overfull-box"))
        else:
            info.append(dict(box, type="small-overfull-box"))
    if parsed["rerun"]:
        info.append({"type": "rerun-needed", "message": parsed["rerun"]})
    return problems, info


def count_unresolved_marks(pdf_text):
    """Count "??" (how LaTeX prints unresolved references) on each page of
    pdftotext output, where pages are separated by form feeds."""
    counts = []
    for number, page in enumerate(pdf_text.split("\f"), start=1):
        if page.count("??"):
            counts.append({"page": number, "count": page.count("??")})
    return counts


ENGINES = ("pdflatex", "xelatex", "lualatex")
LATEXMK_FLAGS = {"pdflatex": "-pdf", "xelatex": "-xelatex",
                 "lualatex": "-lualatex"}


def build_tools(engine, bib_tool):
    """The external programs a build with ENGINE will run."""
    return [engine] + ([bib_tool] if bib_tool else [])


STEP_TIMEOUT = 600  # seconds per build step


def build_commands(engine, main_name, bib_tool):
    """latexmk when available; otherwise engine, bibtex/biber, engine twice."""
    if shutil.which("latexmk"):
        return [["latexmk", LATEXMK_FLAGS[engine], "-interaction=nonstopmode",
                 main_name]]
    tex = [engine, "-interaction=nonstopmode", main_name]
    commands = [tex]
    if bib_tool:
        commands.append([bib_tool, os.path.splitext(main_name)[0]])
    return commands + [tex, tex]


def run_build(main_path, engine, bib_tool, timeout=STEP_TIMEOUT):
    """Compile MAIN in its own directory; return the steps run, the paths of
    the log and PDF (None when not produced) and an error for a step that
    timed out (the remaining steps are then skipped)."""
    root = os.path.dirname(os.path.abspath(main_path))
    name = os.path.basename(main_path)
    stem = os.path.splitext(name)[0]
    steps = []
    error = None
    for cmd in build_commands(engine, name, bib_tool):
        try:
            proc = subprocess.run(cmd, cwd=root, stdin=subprocess.DEVNULL,
                                  stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT, timeout=timeout)
        except subprocess.TimeoutExpired:
            steps.append({"command": " ".join(cmd), "returncode": None,
                          "timed_out": True})
            error = "%s timed out after %d s" % (cmd[0], timeout)
            break
        steps.append({"command": " ".join(cmd), "returncode": proc.returncode,
                      "timed_out": False})
    log = os.path.join(root, stem + ".log")
    pdf = os.path.join(root, stem + ".pdf")
    return {"engine": engine, "stem": stem, "steps": steps, "error": error,
            "log": log if os.path.isfile(log) else None,
            "pdf": pdf if os.path.isfile(pdf) else None}


def build_findings(build):
    """(problems, info) from a run_build() result and the log it left."""
    problems, info = [], []
    if build["error"]:
        problems.append({"type": "build-error", "message": build["error"]})
    if build["log"]:
        problems_log, info_log = log_findings(parse_log(_read(build["log"])))
        problems.extend(problems_log)
        info.extend(info_log)
    elif not build["error"]:
        problems.append({"type": "build-error", "message":
                         "the build produced no %s.log (see the steps' exit "
                         "codes)" % build["stem"]})
    if build["pdf"]:
        for page in pdf_unresolved_marks(build["pdf"]):
            info.append(dict(page, type="unresolved-marks"))
    return problems, info


def pdf_unresolved_marks(pdf_path):
    """count_unresolved_marks() on the PDF's text; [] without pdftotext."""
    exe = shutil.which("pdftotext")
    if not exe:
        return []
    try:
        proc = subprocess.run([exe, "-enc", "UTF-8", pdf_path, "-"],
                              stdin=subprocess.DEVNULL, capture_output=True,
                              timeout=STEP_TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return []
    return count_unresolved_marks(proc.stdout.decode("utf-8", "replace"))


SECTION_TITLES = (
    ("undefined-ref", "Undefined references"),
    ("duplicate-label", "Labels defined more than once"),
    ("missing-citation", "Citation keys not found in any .bib file"),
    ("duplicate-bib-key", "Duplicate .bib keys"),
    ("probable-duplicate-entry", "Probable duplicate .bib entries (same title)"),
    ("missing-graphic", "Missing figure files"),
    ("missing-input", "Missing \\input/\\include files"),
    ("missing-bib-file", "Missing .bib files"),
    ("build-error", "Build errors"),
    ("latex-error", "LaTeX errors (log)"),
    ("log-undefined-ref", "Undefined references (log)"),
    ("log-undefined-citation", "Undefined citations (log)"),
    ("log-multiply-defined-label", "Multiply-defined labels (log)"),
    ("log-missing-file", "Files not found (log)"),
    ("overfull-box", "Overfull boxes over 10pt (log)"),
)
INFO_TITLES = (
    ("small-overfull-box", "Overfull boxes of 10pt or less (log)"),
    ("rerun-needed", "Rerun needed (log)"),
    ("unresolved-marks", "Pages showing ?? in the PDF"),
)


def _locations(item):
    return ", ".join("%s:%d" % (l["file"], l["line"]) for l in item["locations"])


def describe(item):
    """One Markdown list line for a problem or info item."""
    kind = item["type"]
    if kind == "duplicate-label":
        return "%s defined %d times: %s" % (
            item["key"], len(item["locations"]), _locations(item))
    if kind == "duplicate-bib-key":
        return "%s appears %d times: %s" % (
            item["key"], len(item["locations"]), _locations(item))
    if kind == "probable-duplicate-entry":
        return "%s share the title \"%s\": %s" % (
            ", ".join(item["keys"]), item["title"], _locations(item))
    if kind in ("build-error", "rerun-needed"):
        return item["message"]
    if kind == "latex-error":
        if item["line"] is None:
            return item["message"]
        return "input line %d | %s" % (item["line"], item["message"])
    if kind in ("log-undefined-ref", "log-undefined-citation"):
        where = "page %s" % item["page"]
        if item["input_line"] is not None:
            where += ", input line %d" % item["input_line"]
        return "%s (%s)" % (item["key"], where)
    if kind == "log-multiply-defined-label":
        return item["key"]
    if kind == "log-missing-file":
        return item["path"]
    if kind in ("overfull-box", "small-overfull-box"):
        where = ("at line(s) %s" % item["lines"] if item["lines"]
                 else "(no line number)")
        return "%spt overfull \\%s %s" % (item["size_pt"], item["box"], where)
    if kind == "unresolved-marks":
        return "page %d: ?? appears %d time(s)" % (item["page"], item["count"])
    where = "%s:%d" % (item["file"], item["line"])
    if kind == "undefined-ref":
        return "%s | %s{%s}: label never defined" % (
            where, item["command"], item["key"])
    if kind == "missing-citation":
        return "%s | %s{%s}: key not in the bibliography" % (
            where, item["command"], item["key"])
    if kind == "missing-graphic":
        return "%s | \\includegraphics{%s}: no such file (also tried %s)" % (
            where, item["path"], " ".join(GRAPHICS_EXTENSIONS))
    return "%s | %s: file not found" % (where, item["path"])


def render_markdown(result):
    problems = result["problems"]
    out = ["# LaTeX check: %s" % result["main"], ""]
    out.append("Scanned %d file(s): %s" % (len(result["files"]),
                                           ", ".join(result["files"])))
    out.append("Bibliography: %s" % (", ".join(result["bib_files"]) or "none"))
    out.append("")
    out.append("## Problems (%d)" % len(problems))
    out.append("")
    if not problems:
        out.append("None.")
        out.append("")
    out.extend(_sections(problems, SECTION_TITLES))
    if result["info"]:
        out.append("## Info (%d)" % len(result["info"]))
        out.append("")
        out.extend(_sections(result["info"], INFO_TITLES))
    build = result.get("build")
    if build:
        out.append("## Build (%s)" % build["engine"])
        out.append("")
        for step in build["steps"]:
            status = ("timed out" if step["timed_out"]
                      else "exited %d" % step["returncode"])
            out.append("- `%s` %s" % (step["command"], status))
        out.append("- Log: %s" % (build["log"] or "none"))
        out.append("- PDF: %s" % (build["pdf"] or "none"))
        out.append("")
    out.append("Result: %s." % ("%d problem(s)" % len(problems)
                                if problems else "no problems"))
    return "\n".join(out)


def _sections(items, titles):
    out = []
    for kind, title in titles:
        group = [item for item in items if item["type"] == kind]
        if group:
            out.append("### %s (%d)" % (title, len(group)))
            out.extend("- " + describe(item) for item in group)
            out.append("")
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Check a LaTeX thesis for undefined references, duplicate "
                    "labels, missing citations, duplicate .bib entries and "
                    "missing figures; with --build, also compile it and check "
                    "the log for errors, undefined references and overfull "
                    "boxes.",
        epilog="Exit codes: 0 = no problems, 1 = problems found, 2 = usage "
               "error or a needed tool (engine, bibtex, biber) is missing.")
    parser.add_argument("main", metavar="MAIN.tex", help="the root .tex file")
    parser.add_argument("--build", action="store_true",
                        help="also compile the document and check the log")
    parser.add_argument("--engine", choices=ENGINES, default="pdflatex",
                        help="TeX engine for --build (default: pdflatex)")
    parser.add_argument("--json", action="store_true",
                        help="print machine-readable JSON instead of Markdown")
    parser.add_argument("--list-files", action="store_true",
                        help="print MAIN and every file it \\input's or "
                             "\\include's, relative to the current directory, "
                             "one per line, and exit (pass this list to the "
                             "other scanners, which do not follow \\input)")
    args = parser.parse_args(argv)

    if not os.path.isfile(args.main):
        print("latex_check: no such file: %s" % args.main, file=sys.stderr)
        return 2
    if args.list_files:
        root = os.path.dirname(os.path.abspath(args.main))
        sources, _missing = collect_sources(args.main)
        for rel, _text in sources:
            print(os.path.relpath(os.path.join(root, rel)))
        return 0
    result = static_check(args.main)
    if args.build:
        for tool in build_tools(args.engine, result["bib_tool"]):
            if not shutil.which(tool):
                print("latex_check: --build needs %s, which is not installed "
                      "or not on PATH" % tool, file=sys.stderr)
                return 2
        build = run_build(args.main, args.engine, result["bib_tool"])
        result["build"] = build
        problems, info = build_findings(build)
        result["problems"].extend(problems)
        result["info"].extend(info)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(render_markdown(result))
    return 1 if result["problems"] else 0


if __name__ == "__main__":
    sys.exit(main())
