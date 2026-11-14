import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "skills", "thesis-kit", "scripts")
sys.path.insert(0, SCRIPTS)
sys.path.insert(0, HERE)

import paper_text  # noqa: E402
from handmade_pdf import SAMPLE_LINE, write_pdf  # noqa: E402

HAVE_POPPLER = bool(shutil.which("pdftotext") and shutil.which("pdfinfo"))
SCRIPT = os.path.join(SCRIPTS, "paper_text.py")

FIXTURE_PAPERS = os.path.join(HERE, "fixtures", "paper_text", "papers")


def run_main(*args):
    stdout, stderr = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = paper_text.main(list(args))
    except SystemExit as exc:
        code = exc.code
    return code, stdout.getvalue(), stderr.getvalue()


def table_rows(markdown):
    """Cells of each data row of the Markdown table."""
    rows = []
    for row in markdown.splitlines():
        if row.startswith("|") and not set(row) <= set("|-: "):
            cells = [cell.strip() for cell in row.strip("|").split(" | ")]
            if cells[0] != "id":
                rows.append(tuple(cells))
    return rows


def read_json(path):
    with open(path) as handle:
        return json.load(handle)


def read_text(path):
    with open(path) as handle:
        return handle.read()


def write_tree(root, files):
    """Create files under root from {relative path: text}."""
    for relative, text in files.items():
        path = os.path.join(root, relative)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as handle:
            handle.write(text)
    return root


class TempDirTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)


class SlugifyTest(unittest.TestCase):
    def test_lowercases_and_joins_words_with_single_dashes(self):
        cases = {
            "Smith et al. 2021 (NeurIPS)": "smith-et-al-2021-neurips",
            "__Widget_Study__": "widget-study",
            "Über Netze": "uber-netze",
            "???": "paper",
        }
        for name, want in cases.items():
            with self.subTest(name=name):
                self.assertEqual(paper_text.slugify(name), want)


class AssignIdsTest(unittest.TestCase):
    def test_collisions_get_numbered_suffixes_that_no_other_paper_owns(self):
        names = ["A.pdf", "a-2.pdf", "a.tex", "a_2.tex", "b.v2"]
        self.assertEqual(
            paper_text.assign_ids(names),
            {
                "A.pdf": "a",
                "a-2.pdf": "a-2",
                "a.tex": "a-3",  # a-2 is the slug of a-2.pdf
                "a_2.tex": "a-2-2",
                "b.v2": "b-v2",  # a directory keeps its dotted name
            },
        )


DOC = "\\documentclass{article}\n\\begin{document}\nText.\n\\end{document}\n"
BIG = DOC + "Filler text. " * 50
STANDALONE = "\\documentclass{standalone}\n\\begin{document}\nx\n\\end{document}\n" + "% " * 200


class FindMainTexTest(TempDirTest):
    def test_picks_the_document_preferring_main_then_paper_then_largest(self):
        cases = {
            "only one document": ({"intro.tex": "Intro.", "article.tex": DOC}, "article.tex"),
            "main.tex wins": ({"paper.tex": DOC, "big.tex": BIG, "main.tex": DOC}, "main.tex"),
            "paper.tex next": ({"paper.tex": DOC, "big.tex": BIG}, "paper.tex"),
            "then the largest": ({"a.tex": DOC, "b.tex": BIG}, "b.tex"),
            # a main file that \input's its sections is small on its own
            "largest after inlining inputs": (
                {"wrapper.tex": "\\documentclass{article}\n\\input{body}\n",
                 "body.tex": "Section text. " * 100, "rebuttal.tex": BIG},
                "wrapper.tex",
            ),
            "standalone figures are not papers": (
                {"short.tex": DOC, os.path.join("figs", "arch.tex"): STANDALONE},
                "short.tex",
            ),
            "commented-out documentclass": (
                {"old.tex": "% \\documentclass{article}\n" + "x " * 300, "x.tex": DOC},
                "x.tex",
            ),
            "no documentclass anywhere": ({"a.tex": "Short.", "b.tex": "Longer text."}, "b.tex"),
        }
        for name, (files, want) in cases.items():
            with self.subTest(name):
                root = write_tree(os.path.join(self.tmp, name.replace(" ", "_")), files)
                self.assertEqual(
                    paper_text.find_main_tex(root), os.path.join(root, want)
                )


class FlattenLatexTest(TempDirTest):
    def test_inlines_inputs_recursively_without_comments_or_cycles(self):
        write_tree(self.tmp, {
            "main.tex": (
                "\\documentclass{article}\n"
                "\\begin{document}\n"
                "% \\input{old}\n"
                "\\input{sections/intro}\n"
                "\\include{sections/results}\n"
                "\\input sections/appendix\n"
                "\\input{missing-file}\n"
                "\\end{document}\n"
            ),
            # paths are relative to the main file, even in nested files
            "sections/intro.tex": "Intro text 12.5\\% here. % remark\n\\input{sections/loop}\n",
            "sections/loop.tex": "Loop text.\n\\input{sections/intro}\n",
            "sections/results.tex": "Results 0.727.\n\\input{tables/main.tex}\n",
            "tables/main.tex": "Ours & 0.727 \\\\\n",
            "sections/appendix.tex": "Appendix text.\n",
            "old.tex": "OLD CONTENT\n",
        })
        flat = paper_text.flatten_latex(os.path.join(self.tmp, "main.tex"))
        self.assertEqual(
            flat,
            "\\documentclass{article}\n"
            "\\begin{document}\n"
            "Intro text 12.5\\% here.\n"
            "Loop text.\n"
            "\\input{sections/intro}\n"  # the cycle is left as written
            "Results 0.727.\n"
            "Ours & 0.727 \\\\\n"
            "Appendix text.\n"
            "\\input{missing-file}\n"
            "\\end{document}\n",
        )


class LatexTitleTest(unittest.TestCase):
    def test_reads_the_title_argument_as_plain_text(self):
        cases = {
            "\\title{A Synthetic Study of Widgets\\thanks{Supported by the Fund.}}":
                "A Synthetic Study of Widgets",
            "\\title[Short]{Learning {GPU} Kernels:\\\\ \\textit{Fast} and~Exact}":
                "Learning GPU Kernels: Fast and Exact",
            "\\twocolumn[\\icmltitle{Widgets \\& Gadgets}]": "Widgets & Gadgets",
            "\\titlerunning{Not this one}": None,
            "No title here.": None,
        }
        for text, want in cases.items():
            with self.subTest(text=text):
                self.assertEqual(paper_text.latex_title(text), want)


class LatexFiguresTest(TempDirTest):
    def test_lists_included_images_that_exist_relative_to_the_papers_dir(self):
        papers = os.path.join(self.tmp, "papers")
        write_tree(papers, {
            "widget/figs/plot.png": "image",
            "widget/figs/arch.pdf": "image",
            "widget/images/photo.jpg": "image",
            "widget/diagram.v2.pdf": "image",
        })
        text = (
            "\\graphicspath{{figs/}{images/}}\n"
            "\\includegraphics[width=0.5\\linewidth]{plot}\n"
            "\\includegraphics{figs/arch.pdf}\n"
            "\\includegraphics*[scale=0.3]{photo}\n"
            "\\includegraphics{diagram.v2}\n"
            "\\includegraphics{missing}\n"
            "\\includegraphics{figs/arch}\n"
        )
        figures = paper_text.latex_figures(text, os.path.join(papers, "widget"), papers)
        self.assertEqual(
            figures,
            ["widget/figs/plot.png", "widget/figs/arch.pdf",
             "widget/images/photo.jpg", "widget/diagram.v2.pdf"],
        )


class LatexPapersTest(TempDirTest):
    def test_flattens_latex_papers_and_writes_meta(self):
        out = os.path.join(self.tmp, "text")
        code, stdout, _ = run_main(FIXTURE_PAPERS, out)
        self.assertEqual(code, 0)
        self.assertEqual(sorted(os.listdir(out)), ["short-note", "widget-study"])

        self.assertEqual(read_json(os.path.join(out, "short-note", "meta.json")), {
            "id": "short-note",
            "kind": "latex",
            "source_path": "short-note.tex",
            "pages": None,
            "title": "Short Note",
            "words": 10,
            "extractor": "latex-flatten",
            "figures": [],
        })
        meta = read_json(os.path.join(out, "widget-study", "meta.json"))
        self.assertEqual(
            (meta["kind"], meta["source_path"], meta["title"], meta["figures"]),
            ("latex", "widget-study/main.tex", "A Synthetic Study of Widgets",
             ["widget-study/figs/plot.png"]),
        )
        tex = read_text(os.path.join(out, "widget-study", "source.tex"))
        self.assertEqual(read_text(os.path.join(out, "widget-study", "source.txt")), tex)
        self.assertIn("Accuracy improves from 0.671 to 0.727 on 1,000 documents.", tex)
        self.assertIn("Widgets matter in 12.5\\% of cases.", tex)
        for gone in ("Draft note", "private remark", "\\input", "\\include{"):
            self.assertNotIn(gone, tex)

        self.assertEqual(table_rows(stdout), [
            ("short-note", "latex", "-", "10", "Short Note", "processed"),
            ("widget-study", "latex", "-", str(meta["words"]),
             "A Synthetic Study of Widgets", "processed"),
        ])
        self.assertIn("README.md", stdout.split("|")[-1])  # listed as skipped

    def test_json_reports_each_paper_with_its_status_and_the_skipped_entries(self):
        out = os.path.join(self.tmp, "text")
        code, stdout, _ = run_main(FIXTURE_PAPERS, out, "--json")
        self.assertEqual(code, 0)
        report = json.loads(stdout)
        self.assertEqual(report["skipped"], ["README.md"])
        self.assertEqual(
            [(p["id"], p["status"]) for p in report["papers"]],
            [("short-note", "processed"), ("widget-study", "processed")],
        )
        note = read_json(os.path.join(out, "short-note", "meta.json"))
        self.assertEqual(report["papers"][0], dict(note, status="processed"))

    def test_kept_paper_without_meta_is_reported_from_its_text(self):
        out = os.path.join(self.tmp, "text")
        run_main(FIXTURE_PAPERS, out)
        folder = os.path.join(out, "short-note")
        os.remove(os.path.join(folder, "meta.json"))
        with open(os.path.join(folder, "source.txt"), "w") as handle:
            handle.write("three words here")
        code, stdout, _ = run_main(FIXTURE_PAPERS, out)
        self.assertEqual(code, 0)
        self.assertIn(("short-note", "latex", "-", "3", "-", "kept"), table_rows(stdout))

    def test_rerun_keeps_existing_text_and_notes_unless_forced(self):
        out = os.path.join(self.tmp, "text")
        run_main(FIXTURE_PAPERS, out)
        folder = os.path.join(out, "short-note")
        for name, text in (("source.txt", "EDITED"), ("source.tex", "EDITED TEX"),
                           ("notes.md", "my notes")):
            with open(os.path.join(folder, name), "w") as handle:
                handle.write(text)

        code, stdout, _ = run_main(FIXTURE_PAPERS, out)
        self.assertEqual(code, 0)
        self.assertIn(("short-note", "latex", "-", "10", "Short Note", "kept"), table_rows(stdout))
        self.assertEqual(read_text(os.path.join(folder, "source.txt")), "EDITED")
        self.assertEqual(read_text(os.path.join(folder, "source.tex")), "EDITED TEX")

        code, stdout, _ = run_main(FIXTURE_PAPERS, out, "--force")
        self.assertEqual(code, 0)
        self.assertIn(("short-note", "latex", "-", "10", "Short Note", "processed"),
                      table_rows(stdout))
        self.assertIn("A note with 42 widgets.", read_text(os.path.join(folder, "source.txt")))
        self.assertEqual(read_text(os.path.join(folder, "notes.md")), "my notes")


def tex_paper(title):
    return "\\documentclass{article}\n\\title{%s}\n\\begin{document}\nBody.\n\\end{document}\n" % title


class StableIdsTest(TempDirTest):
    def statuses(self, stdout):
        return {row[0]: (row[4], row[5]) for row in table_rows(stdout)}

    def test_ids_from_earlier_runs_stick_to_their_papers(self):
        papers = os.path.join(self.tmp, "papers")
        out = os.path.join(self.tmp, "text")
        write_tree(papers, {"paper.tex": tex_paper("Original")})
        run_main(papers, out)

        # "Paper/" sorts before "paper.tex" and has the same slug
        write_tree(papers, {"Paper/main.tex": tex_paper("Newcomer")})
        code, stdout, _ = run_main(papers, out)
        self.assertEqual(code, 0)
        self.assertEqual(self.statuses(stdout), {
            "paper": ("Original", "kept"),
            "paper-2": ("Newcomer", "processed"),
        })

        # a folder left by a removed paper is not handed to a new one
        os.remove(os.path.join(papers, "paper.tex"))
        write_tree(papers, {"PAPER.tex": tex_paper("Third")})
        code, stdout, _ = run_main(papers, out)
        self.assertEqual(self.statuses(stdout), {
            "paper-2": ("Newcomer", "kept"),
            "paper-3": ("Third", "processed"),
        })
        self.assertEqual(read_json(os.path.join(out, "paper", "meta.json"))["title"], "Original")


@unittest.skipUnless(HAVE_POPPLER, "pdftotext/pdfinfo (Poppler) not installed")
class HandmadePdfTest(TempDirTest):
    def test_pdftotext_extracts_the_hand_made_pdf(self):
        pdf = write_pdf(os.path.join(self.tmp, "sample.pdf"), [[SAMPLE_LINE]])
        text = subprocess.run(
            ["pdftotext", "-layout", pdf, "-"], capture_output=True, text=True, check=True
        ).stdout
        self.assertEqual(text.strip(), SAMPLE_LINE)


@unittest.skipUnless(HAVE_POPPLER, "pdftotext/pdfinfo (Poppler) not installed")
class PdfPapersTest(TempDirTest):
    def setUp(self):
        super().setUp()
        self.papers = os.path.join(self.tmp, "papers")
        self.out = os.path.join(self.tmp, "text")
        os.makedirs(self.papers)

    def test_extracts_text_with_page_breaks_page_count_and_metadata_title(self):
        write_pdf(os.path.join(self.papers, "Widget Paper.pdf"),
                  [["A Synthetic Study of Widgets"], [SAMPLE_LINE]],
                  title="Widget Metadata Title")
        code, stdout, _ = run_main(self.papers, self.out)
        self.assertEqual(code, 0)
        folder = os.path.join(self.out, "widget-paper")
        self.assertEqual(read_json(os.path.join(folder, "meta.json")), {
            "id": "widget-paper",
            "kind": "pdf",
            "source_path": "Widget Paper.pdf",
            "pages": 2,
            "title": "Widget Metadata Title",
            "words": 15,
            "extractor": "pdftotext -layout",
            "figures": [],
        })
        pages = read_text(os.path.join(folder, "source.txt")).split("\f")
        self.assertIn(SAMPLE_LINE, pages[1])  # page 2, after the form feed
        self.assertEqual(sorted(os.listdir(folder)), ["meta.json", "source.txt"])
        self.assertEqual(table_rows(stdout), [
            ("widget-paper", "pdf", "2", "15", "Widget Metadata Title", "processed")])

    def test_pdf_without_a_text_layer_gets_a_warning(self):
        write_pdf(os.path.join(self.papers, "scanned.pdf"), [[]])
        code, stdout, _ = run_main(self.papers, self.out)
        self.assertEqual(code, 0)
        self.assertEqual(table_rows(stdout), [("scanned", "pdf", "1", "0", "-", "processed")])
        warnings = [l for l in stdout.splitlines() if l.lower().startswith("warning")]
        self.assertEqual(len(warnings), 1)
        self.assertIn("scanned", warnings[0])
        report = json.loads(run_main(self.papers, self.out, "--json")[1])
        self.assertEqual(len(report["warnings"]), 1)

    def test_title_falls_back_to_the_first_line_of_page_one(self):
        write_pdf(os.path.join(self.papers, "untitled.pdf"),
                  [["", "  A Synthetic   Study of Widgets  "], [SAMPLE_LINE]])
        run_main(self.papers, self.out)
        meta = read_json(os.path.join(self.out, "untitled", "meta.json"))
        self.assertEqual(meta["title"], "A Synthetic Study of Widgets")


class DiscoverTest(TempDirTest):
    def test_out_dir_inside_papers_dir_and_hidden_entries_are_not_papers(self):
        papers = write_tree(os.path.join(self.tmp, "papers"), {
            "note.tex": tex_paper("Note"), ".DS_Store": "junk"})
        out = os.path.join(papers, "text")
        run_main(papers, out)  # writes papers/text/note/source.tex
        code, stdout, _ = run_main(papers, out)
        self.assertEqual(code, 0)
        self.assertEqual([row[0] for row in table_rows(stdout)], ["note"])
        self.assertNotIn(".DS_Store", stdout)

    def test_out_dir_equal_to_papers_dir_exits_2(self):
        papers = write_tree(os.path.join(self.tmp, "papers"), {"note.tex": tex_paper("Note")})
        code, _, stderr = run_main(papers, papers)
        self.assertEqual(code, 2)
        self.assertTrue(stderr.strip())
        self.assertEqual(os.listdir(papers), ["note.tex"])


class ExitCodesTest(TempDirTest):
    def test_missing_papers_dir_exits_2(self):
        code, stdout, stderr = run_main(os.path.join(self.tmp, "nope"), os.path.join(self.tmp, "out"))
        self.assertEqual(code, 2)
        self.assertIn("nope", stderr)

    def test_no_papers_exits_1(self):
        for files in ({}, {"README.md": "not a paper"}):
            with self.subTest(files=files):
                papers = write_tree(tempfile.mkdtemp(dir=self.tmp), files)
                code, stdout, _ = run_main(papers, os.path.join(self.tmp, "out"))
                self.assertEqual(code, 1)

    def run_without_poppler(self, papers, out):
        empty_bin = os.path.join(self.tmp, "bin")
        os.makedirs(empty_bin, exist_ok=True)
        return subprocess.run(
            [sys.executable, SCRIPT, papers, out],
            capture_output=True, text=True, env=dict(os.environ, PATH=empty_bin),
        )

    def test_pdf_to_extract_without_poppler_exits_2_before_writing(self):
        papers = write_tree(os.path.join(self.tmp, "papers"), {"note.tex": tex_paper("Note")})
        write_pdf(os.path.join(papers, "paper.pdf"), [[SAMPLE_LINE]])
        out = os.path.join(self.tmp, "out")
        result = self.run_without_poppler(papers, out)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("pdftotext", result.stderr)
        self.assertIn("brew install poppler", result.stderr)
        self.assertIn("apt install poppler-utils", result.stderr)
        self.assertFalse(os.path.exists(out))

    def test_kept_pdfs_do_not_need_poppler(self):
        papers = os.path.join(self.tmp, "papers")
        os.makedirs(papers)
        write_pdf(os.path.join(papers, "paper.pdf"), [[SAMPLE_LINE]])
        folder = write_tree(os.path.join(self.tmp, "out", "paper"), {
            "source.txt": SAMPLE_LINE,
            "meta.json": json.dumps({"id": "paper", "kind": "pdf", "source_path": "paper.pdf",
                                     "pages": 1, "title": "T", "words": 10,
                                     "extractor": "pdftotext -layout", "figures": []}),
        })
        result = self.run_without_poppler(papers, os.path.dirname(folder))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(("paper", "pdf", "1", "10", "T", "kept"), table_rows(result.stdout))

    @unittest.skipUnless(HAVE_POPPLER, "pdftotext/pdfinfo (Poppler) not installed")
    def test_unreadable_pdf_is_an_error_but_other_papers_are_processed(self):
        papers = write_tree(os.path.join(self.tmp, "papers"), {
            "broken.pdf": "not really a PDF", "note.tex": tex_paper("Note")})
        out = os.path.join(self.tmp, "out")
        code, stdout, _ = run_main(papers, out)
        self.assertEqual(code, 1)
        statuses = {row[0]: row[5] for row in table_rows(stdout)}
        self.assertEqual(statuses["note"], "processed")
        self.assertTrue(statuses["broken"].startswith("error"), statuses["broken"])
        leftovers = [name for _, _, files in os.walk(out) for name in files
                     if name.endswith(".partial")]
        self.assertEqual(leftovers, [])
        self.assertFalse(os.path.exists(os.path.join(out, "broken", "source.txt")))


if __name__ == "__main__":
    unittest.main()
