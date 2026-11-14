#!/usr/bin/env python3
r"""Extract the text of the student's papers once, into stable text files.

Later agents read OUT_DIR/<id>/source.txt instead of re-extracting PDFs.

Usage:
    python3 paper_text.py PAPERS_DIR OUT_DIR [--force] [--json]

Each entry directly inside PAPERS_DIR is one paper:
  - a .pdf file: `pdftotext -layout` writes source.txt, keeping the form
    feed that separates pages; the page count comes from pdfinfo; the
    title is the PDF's Title metadata, else the first line of page 1.
  - a .tex file, or a directory holding .tex files: the main file (the one
    with \documentclass; main.tex, then paper.tex, then the largest once
    its inputs are counted) is flattened, with \input and \include inlined
    recursively and comments removed, into source.tex and source.txt (the
    same text). The title comes from \title{...}; meta.json lists the
    \includegraphics files that exist.
  Anything else is listed as skipped; hidden entries are ignored.

The id is a slug of the file or directory name (Smith et al. 2021.pdf ->
smith-et-al-2021); clashes get -2, -3. An id recorded in OUT_DIR by an
earlier run stays with its paper, and the folder of a removed paper is
never given to another one.

OUT_DIR/<id>/meta.json holds id, kind ("pdf" or "latex"), source_path and
figures (relative to PAPERS_DIR), pages (null for LaTeX), title, words
(whitespace-separated tokens of source.txt, LaTeX markup included) and
extractor ("pdftotext -layout" or "latex-flatten").

Re-runs are cheap: a paper whose source.txt exists is reported as "kept"
and its folder is not touched, so notes stored there are safe. --force
extracts again, replacing only source.txt, source.tex and meta.json.

Prints a Markdown table (id | kind | pages | words | title | status) and a
warning for any paper with no extractable text, such as a scanned PDF.

Exit codes: 0 papers processed or kept, none failed; 1 no papers found, or
an extraction failed; 2 PAPERS_DIR missing, OUT_DIR equal to PAPERS_DIR,
or a PDF to extract while pdftotext or pdfinfo (Poppler) is missing.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata

# % preceded by an even number of backslashes starts a comment (\\% is a
# line break followed by one, \% is a literal percent sign)
COMMENT_RE = re.compile(r"(?<!\\)((?:\\\\)*)%.*")
DOCUMENTCLASS_RE = re.compile(r"\\documentclass\s*(?:\[[^\]]*\])?\s*\{([^}]*)\}")
TITLE_RE = re.compile(r"\\(?:title|icmltitle)(?![A-Za-z])\s*(?:\[[^\]]*\])?\s*\{")
NOTE_RE = re.compile(r"\\(?:thanks|footnote)\s*\{")
GRAPHICS_RE = re.compile(r"\\includegraphics\*?\s*(?:\[[^\]]*\]\s*)*\{([^{}]+)\}")
GRAPHICSPATH_RE = re.compile(r"\\graphicspath\s*\{((?:\s*\{[^{}]*\})+)\s*\}")
# the extensions graphicx tries, in order, when \includegraphics has none
GRAPHICS_EXTENSIONS = (".pdf", ".png", ".jpg", ".jpeg", ".eps", ".ps",
                       ".PDF", ".PNG", ".JPG", ".JPEG", ".EPS")
# \input{x}, \include{x} and the plain TeX form \input x
INPUT_RE = re.compile(r"\\(?:input|include)\s*\{([^{}]*)\}|\\input\s+([^\s{}\\%]+)")


def slugify(name):
    """Lowercase ASCII id: runs of other characters become one dash."""
    ascii_name = (
        unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    )
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")
    return slug or "paper"


def _stem(name):
    """A paper's name without its .pdf or .tex extension (a directory keeps
    its whole name, dots included)."""
    if name.lower().endswith((".pdf", ".tex")):
        return name[:-4]
    return name


def assign_ids(names, owners=None):
    """Map each entry name to a unique id, processing names in sorted order.

    owners maps ids already in OUT_DIR to the entry that made them (from
    their meta.json). A paper keeps the id it had; ids owned by papers that
    are gone are never reused, so their folders and notes stay theirs. Any
    other name whose slug is taken gets the first free "-2", "-3", ...
    suffix that is not itself the slug of another entry.
    """
    names = sorted(names)
    owners = owners or {}
    ids = {}
    present = set(names)
    for paper_id in sorted(owners):
        if owners[paper_id] in present and owners[paper_id] not in ids:
            ids[owners[paper_id]] = paper_id
    bases = {name: slugify(_stem(name)) for name in names}
    all_bases = set(bases.values())
    used = set(owners)
    for name in names:
        if name in ids:
            continue
        candidate = bases[name]
        if candidate in used:
            number = 2
            while ("%s-%d" % (bases[name], number) in used
                   or "%s-%d" % (bases[name], number) in all_bases):
                number += 1
            candidate = "%s-%d" % (bases[name], number)
        used.add(candidate)
        ids[name] = candidate
    return ids


def _read(path):
    with open(path, encoding="utf-8", errors="replace") as handle:
        return handle.read()


def strip_comments(text):
    """Remove LaTeX comments. Lines that held only a comment are dropped,
    so they do not turn into paragraph breaks."""
    lines = []
    for line in text.split("\n"):
        stripped = COMMENT_RE.sub(lambda m: m.group(1), line)
        if stripped == line:
            lines.append(line)
        elif stripped.strip():
            lines.append(stripped.rstrip())
    return "\n".join(lines)


def _tex_files(directory):
    found = []
    for root, dirs, files in os.walk(directory):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        for name in sorted(files):
            if name.lower().endswith(".tex") and not name.startswith("."):
                found.append(os.path.join(root, name))
    return found


def find_main_tex(directory):
    """Return the main .tex file of a LaTeX source directory, or None.

    The main file has an (uncommented) \\documentclass; standalone figure
    documents count only if nothing else does, and without any
    \\documentclass every .tex file is a candidate. Among candidates,
    main.tex wins, then paper.tex, then the largest document counting the
    files it inputs (a main file that only inputs its sections is small).
    """
    tex_files = _tex_files(directory)
    documents, standalone = [], []
    for path in tex_files:
        match = DOCUMENTCLASS_RE.search(strip_comments(_read(path)))
        if match:
            if match.group(1).strip() == "standalone":
                standalone.append(path)
            else:
                documents.append(path)
    candidates = documents or standalone or tex_files
    if not candidates:
        return None

    def rank(path):
        preference = {"main.tex": 0, "paper.tex": 1}.get(os.path.basename(path).lower(), 2)
        depth = os.path.relpath(path, directory).count(os.sep)
        return (preference, -len(flatten_latex(path)), depth, path)

    return min(candidates, key=rank)


def _resolve_input(base_dir, name):
    """The file \\input{name} reads: name.tex first (unless name already
    ends in .tex), then name itself; None if neither exists."""
    path = os.path.join(base_dir, name)
    candidates = [path] if name.endswith(".tex") else [path + ".tex", path]
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    return None


def flatten_latex(main_path):
    """Return the main file's text with comments removed and every
    \\input/\\include inlined recursively. Paths are relative to the main
    file's directory, as LaTeX resolves them; a missing file, or one that
    would include itself again, is left as the command."""
    base_dir = os.path.dirname(os.path.abspath(main_path))

    def inline(path, active):
        text = strip_comments(_read(path))

        def replace(match):
            target = _resolve_input(base_dir, (match.group(1) or match.group(2)).strip())
            if target is None or os.path.realpath(target) in active:
                return match.group(0)
            content = inline(target, active | {os.path.realpath(target)})
            # TeX turns the end of an input file into a space, not a new
            # paragraph, so drop one trailing line break
            return content[:-1] if content.endswith("\n") else content

        return INPUT_RE.sub(replace, text)

    return inline(main_path, {os.path.realpath(main_path)})


def _brace_end(text, i):
    """text[i] is "{"; return the index of its matching "}", or None."""
    depth = 0
    j = i
    while j < len(text):
        char = text[j]
        if char == "\\":
            j += 2
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return j
        j += 1
    return None


def _plain_title(raw):
    """Turn the LaTeX of a title into plain text."""
    while True:  # drop \thanks{...} and \footnote{...}
        match = NOTE_RE.search(raw)
        end = _brace_end(raw, match.end() - 1) if match else None
        if end is None:
            break
        raw = raw[:match.start()] + raw[end + 1:]
    text = re.sub(r"\\\\(?:\[[^\]]*\])?", " ", raw)  # \\ line breaks
    text = re.sub(r"\\([&%$#_])", r"\1", text)
    text = re.sub(r"\\-", "", text)
    text = re.sub(r"\\[A-Za-z]+\*?", " ", text)  # command names; keep arguments
    text = text.replace("~", " ").replace("{", "").replace("}", "")
    return " ".join(text.split())


def latex_title(text):
    """The plain-text \\title{...} (or \\icmltitle{...}) of a paper, or None."""
    match = TITLE_RE.search(text)
    if not match:
        return None
    end = _brace_end(text, match.end() - 1)
    if end is None:
        return None
    return _plain_title(text[match.end():end]) or None


def latex_figures(text, main_dir, papers_dir):
    """Paths, relative to papers_dir, of the \\includegraphics files that
    exist. Like graphicx, each name is looked up in the main file's
    directory and then in the \\graphicspath directories, adding the usual
    extensions when the file as named does not exist."""
    search = [main_dir]
    for match in GRAPHICSPATH_RE.finditer(text):
        search += [os.path.join(main_dir, d) for d in re.findall(r"\{([^{}]*)\}", match.group(1))]
    figures = []
    for match in GRAPHICS_RE.finditer(text):
        name = match.group(1).strip()
        found = None
        for directory in search:
            for candidate in [name] + [name + ext for ext in GRAPHICS_EXTENSIONS]:
                path = os.path.join(directory, candidate)
                if os.path.isfile(path):
                    found = path
                    break
            if found:
                break
        if found:
            relative = os.path.relpath(found, papers_dir).replace(os.sep, "/")
            if relative not in figures:
                figures.append(relative)
    return figures


def previous_owners(out_dir):
    """{id: entry name} for the folders of OUT_DIR made by earlier runs."""
    owners = {}
    if not os.path.isdir(out_dir):
        return owners
    for paper_id in sorted(os.listdir(out_dir)):
        try:
            with open(os.path.join(out_dir, paper_id, "meta.json"), encoding="utf-8") as handle:
                source = json.load(handle).get("source_path")
        except (OSError, ValueError, AttributeError):
            continue
        if isinstance(source, str) and source:
            owners[paper_id] = source.split("/")[0]
    return owners


def discover(papers_dir, out_dir):
    """Classify the entries directly inside papers_dir.

    Returns (papers, skipped): papers is [(name, kind)] with kind "pdf" or
    "latex"; skipped lists the other entries. Hidden entries and OUT_DIR
    itself (if it is inside papers_dir) are ignored.
    """
    out_real = os.path.realpath(out_dir)
    papers, skipped = [], []
    for name in sorted(os.listdir(papers_dir)):
        path = os.path.join(papers_dir, name)
        if name.startswith(".") or os.path.realpath(path) == out_real:
            continue
        if os.path.isfile(path) and name.lower().endswith(".pdf"):
            papers.append((name, "pdf"))
        elif os.path.isfile(path) and name.lower().endswith(".tex"):
            papers.append((name, "latex"))
        elif os.path.isdir(path) and _tex_files(path):
            papers.append((name, "latex"))
        else:
            skipped.append(name)
    return papers, skipped


def _write(path, text):
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def _relative(path, papers_dir):
    return os.path.relpath(path, papers_dir).replace(os.sep, "/")


def extract_latex(papers_dir, name, folder, paper_id):
    """Flatten a LaTeX paper into folder/source.tex and source.txt."""
    path = os.path.join(papers_dir, name)
    main_file = path if os.path.isfile(path) else find_main_tex(path)
    text = flatten_latex(main_file)
    _write(os.path.join(folder, "source.tex"), text)
    _write(os.path.join(folder, "source.txt"), text)
    return {
        "id": paper_id,
        "kind": "latex",
        "source_path": _relative(main_file, papers_dir),
        "pages": None,
        "title": latex_title(text),
        "words": len(text.split()),
        "extractor": "latex-flatten",
        "figures": latex_figures(text, os.path.dirname(main_file), papers_dir),
    }


def _kept_meta(folder, paper_id, kind):
    """The meta.json of an already extracted paper, without re-reading the
    paper itself; rebuilt from source.txt if meta.json is unreadable."""
    try:
        with open(os.path.join(folder, "meta.json"), encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        words = len(_read(os.path.join(folder, "source.txt")).split())
        return {"id": paper_id, "kind": kind, "source_path": None, "pages": None,
                "title": None, "words": words, "extractor": None, "figures": []}


def _run(command):
    return subprocess.run(command, capture_output=True, check=True,
                          encoding="utf-8", errors="replace").stdout


def extract_pdf(papers_dir, name, folder, paper_id):
    """Write folder/source.txt with pdftotext -layout, keeping the form
    feeds it puts between pages, and return the paper's meta."""
    path = os.path.join(papers_dir, name)
    target = os.path.join(folder, "source.txt")
    partial = target + ".partial"
    info = _run(["pdfinfo", "-enc", "UTF-8", path])
    # write beside the target and rename, so a failed run never leaves a
    # truncated source.txt that a later run would keep
    _run(["pdftotext", "-layout", "-enc", "UTF-8", path, partial])
    os.replace(partial, target)
    pages = re.search(r"^Pages:\s+(\d+)", info, re.MULTILINE)
    title = re.search(r"^Title:[ \t]*(.*)$", info, re.MULTILINE)
    title = " ".join(title.group(1).split()) if title else ""
    text = _read(target)
    if not title:
        first_page = text.split("\f")[0]
        title = next((" ".join(l.split()) for l in first_page.splitlines() if l.strip()), "")
    return {
        "id": paper_id,
        "kind": "pdf",
        "source_path": _relative(path, papers_dir),
        "pages": int(pages.group(1)) if pages else None,
        "title": title or None,
        "words": len(text.split()),
        "extractor": "pdftotext -layout",
        "figures": [],
    }


def _cell(value):
    if value is None:
        return "-"
    return str(value).replace("|", "\\|")


def no_text_warnings(papers):
    return [
        "Warning: no text extracted from %s (%s); a scanned PDF needs OCR first."
        % (paper["id"], paper.get("source_path"))
        for paper in papers
        if paper.get("words") == 0 and not paper["status"].startswith("error")
    ]


def format_markdown(papers, skipped, out_dir):
    if not papers:
        lines = ["No papers found (looked for .pdf files, .tex files and "
                 "directories of .tex files)."]
        if skipped:
            lines.append("Skipped: " + ", ".join(skipped))
        return "\n".join(lines)
    lines = [
        "| id | kind | pages | words | title | status |",
        "|---|---|---:|---:|---|---|",
    ]
    for paper in papers:
        lines.append("| %s |" % " | ".join(_cell(paper.get(key)) for key in (
            "id", "kind", "pages", "words", "title", "status")))
    processed = sum(1 for p in papers if p["status"] == "processed")
    kept = sum(1 for p in papers if p["status"] == "kept")
    failed = sum(1 for p in papers if p["status"].startswith("error"))
    lines.append("")
    lines.append("%d processed, %d kept, %d failed. Text is in %s."
                 % (processed, kept, failed, out_dir))
    lines += no_text_warnings(papers)
    if skipped:
        lines.append("Skipped (not a .pdf, a .tex file or a directory of .tex files): "
                     + ", ".join(skipped))
    return "\n".join(lines)


INSTALL_HINT = (
    "Install Poppler: `brew install poppler` on macOS, "
    "`apt install poppler-utils` on Debian/Ubuntu."
)


def _error(message):
    print("paper_text: " + message, file=sys.stderr)


def _failure(exc):
    """One line saying why an extraction failed."""
    if isinstance(exc, subprocess.CalledProcessError):
        lines = [l for l in (exc.stderr or "").splitlines() if l.strip()]
        return "%s failed%s" % (exc.cmd[0], ": " + lines[-1].strip() if lines else "")
    return str(exc)


def _clean_failed(folder, created):
    """Remove what a failed extraction left behind (never other files)."""
    partial = os.path.join(folder, "source.txt.partial")
    if os.path.exists(partial):
        os.remove(partial)
    if created and not os.listdir(folder):
        os.rmdir(folder)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("papers_dir", metavar="PAPERS_DIR",
                        help="folder holding one PDF, .tex file or LaTeX folder per paper")
    parser.add_argument("out_dir", metavar="OUT_DIR",
                        help="where to write OUT_DIR/<id>/source.txt and meta.json")
    parser.add_argument("--force", action="store_true",
                        help="extract again even if OUT_DIR/<id>/source.txt exists")
    parser.add_argument("--json", action="store_true",
                        help="print a JSON report instead of a Markdown table")
    args = parser.parse_args(argv)

    def report(papers, skipped):
        if args.json:
            print(json.dumps({"out_dir": args.out_dir, "papers": papers,
                              "skipped": skipped, "warnings": no_text_warnings(papers)},
                             indent=2))
        else:
            print(format_markdown(papers, skipped, args.out_dir))

    if not os.path.isdir(args.papers_dir):
        _error("no such directory: %s" % args.papers_dir)
        return 2
    if os.path.realpath(args.out_dir) == os.path.realpath(args.papers_dir):
        _error("OUT_DIR must be a different folder from PAPERS_DIR")
        return 2
    entries, skipped = discover(args.papers_dir, args.out_dir)
    if not entries:
        report([], skipped)
        return 1
    ids = assign_ids([name for name, _ in entries], previous_owners(args.out_dir))

    def is_kept(name):
        exists = os.path.exists(os.path.join(args.out_dir, ids[name], "source.txt"))
        return exists and not args.force

    to_extract = [kind for name, kind in entries if not is_kept(name)]
    missing = [tool for tool in ("pdftotext", "pdfinfo") if not shutil.which(tool)]
    if "pdf" in to_extract and missing:
        _error("%s needed to read PDFs but not found on PATH. %s"
               % (" and ".join(missing), INSTALL_HINT))
        return 2

    papers = []
    for name, kind in entries:
        folder = os.path.join(args.out_dir, ids[name])
        if is_kept(name):
            papers.append(dict(_kept_meta(folder, ids[name], kind), status="kept"))
            continue
        created = not os.path.isdir(folder)
        os.makedirs(folder, exist_ok=True)
        extract = extract_pdf if kind == "pdf" else extract_latex
        try:
            meta = extract(args.papers_dir, name, folder, ids[name])
        except (subprocess.CalledProcessError, OSError) as exc:
            _clean_failed(folder, created)
            papers.append({"id": ids[name], "kind": kind, "source_path": name,
                           "pages": None, "title": None, "words": None,
                           "extractor": None, "figures": [],
                           "status": "error: %s" % _failure(exc)})
            continue
        _write(os.path.join(folder, "meta.json"), json.dumps(meta, indent=2) + "\n")
        papers.append(dict(meta, status="processed"))
    report(papers, skipped)
    failed = any(paper["status"].startswith("error") for paper in papers)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
