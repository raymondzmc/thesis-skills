"""Tests for skills/thesis-kit/scripts/latex_check.py."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCRIPTS = os.path.join(ROOT, "skills", "thesis-kit", "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

import latex_check  # noqa: E402

SCRIPT = os.path.join(SCRIPTS, "latex_check.py")
FIXTURES = os.path.join(HERE, "fixtures", "latex_check")


class ProjectCase(unittest.TestCase):
    """Helpers to build a throwaway LaTeX project in a temp dir."""

    def project(self, files):
        root = tempfile.mkdtemp(prefix="latex_check_test_")
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        for rel, text in files.items():
            path = os.path.join(root, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
        return root

    def check(self, files, main="main.tex"):
        root = self.project(files)
        return latex_check.static_check(os.path.join(root, main))

    @staticmethod
    def of_type(result, kind):
        return [p for p in result["problems"] if p["type"] == kind]


class UndefinedRefTests(ProjectCase):
    def test_reports_ref_to_label_never_defined(self):
        result = self.check({
            "main.tex": "\\section{A}\\label{sec:a}\n"
                        "See \\ref{sec:a} and \\ref{sec:b}.\n",
        })
        found = [(p["key"], p["file"], p["line"])
                 for p in self.of_type(result, "undefined-ref")]
        self.assertEqual(found, [("sec:b", "main.tex", 2)])

    def test_every_ref_command_comma_list_and_star_is_checked(self):
        result = self.check({
            "main.tex": "\\label{a}\\refstepcounter{chapter}\n"
                        "\\autoref{b} \\cref{a, c} \\Cref{d}\n"
                        "\\eqref{e} \\pageref{f} \\nameref{g} \\cref*{h}\n",
        })
        found = sorted(p["key"] for p in self.of_type(result, "undefined-ref"))
        self.assertEqual(found, ["b", "c", "d", "e", "f", "g", "h"])

    def test_comments_are_ignored_but_escaped_percent_is_not_a_comment(self):
        result = self.check({
            "main.tex": "\\label{a}\n"
                        "% \\ref{gone}\n"
                        "50\\% of cases, see \\ref{kept}\n"
                        "line break\\\\% \\ref{gone2}\n",
        })
        found = [(p["key"], p["line"])
                 for p in self.of_type(result, "undefined-ref")]
        self.assertEqual(found, [("kept", 3)])


class InputTests(ProjectCase):
    def test_follows_input_and_include_recursively_relative_to_main_dir(self):
        result = self.check({
            "main.tex": "\\input{chapters/one.tex}\n\\include{chapters/two}\n",
            "chapters/one.tex": "\\label{sec:one}\n\\input{chapters/three}\n",
            "chapters/two.tex": "\\ref{sec:one} \\ref{sec:three}\n"
                                "\\ref{sec:none}\n",
            "chapters/three.tex": "\\label{sec:three}\n",
        })
        self.assertEqual(result["files"], [
            "main.tex", "chapters/one.tex", "chapters/three.tex",
            "chapters/two.tex"])
        found = [(p["key"], p["file"], p["line"])
                 for p in self.of_type(result, "undefined-ref")]
        self.assertEqual(found, [("sec:none", "chapters/two.tex", 2)])

    def test_reports_input_file_that_does_not_exist(self):
        result = self.check({"main.tex": "Text.\n\\include{chapters/missing}\n"})
        found = [(p["path"], p["file"], p["line"])
                 for p in self.of_type(result, "missing-input")]
        self.assertEqual(found, [("chapters/missing", "main.tex", 2)])

    @unittest.skipUnless(shutil.which("kpsewhich"), "kpsewhich not installed")
    def test_input_found_in_the_tex_distribution_is_not_missing(self):
        found = subprocess.run(["kpsewhich", "glyphtounicode.tex"],
                               capture_output=True, text=True).stdout.strip()
        if not found:
            self.skipTest("glyphtounicode.tex is not in this TeX distribution")
        result = self.check({"main.tex": "\\input{glyphtounicode}\n"})
        self.assertEqual(self.of_type(result, "missing-input"), [])


class LabelTests(ProjectCase):
    def test_reports_label_defined_more_than_once_with_all_locations(self):
        result = self.check({
            "main.tex": "\\label{sec:a}\n\\input{ch}\n\\label{sec:b}\n",
            "ch.tex": "Text\n\\label{sec:a}\n",
        })
        found = [(p["key"], p["locations"])
                 for p in self.of_type(result, "duplicate-label")]
        self.assertEqual(found, [("sec:a", [{"file": "main.tex", "line": 1},
                                            {"file": "ch.tex", "line": 2}])])

    def test_keys_built_from_macro_arguments_are_not_checked(self):
        result = self.check({
            "main.tex": "\\newcommand{\\fig}[1]{\\label{fig:#1}}\n"
                        "\\newcommand{\\tab}[1]{\\label{fig:#1}}\n"
                        "\\newcommand{\\figref}[1]{Figure~\\ref{#1}}\n"
                        "\\ref{\\mylabel}\n",
        })
        self.assertEqual(self.of_type(result, "duplicate-label"), [])
        self.assertEqual(self.of_type(result, "undefined-ref"), [])

    def test_label_with_cleveref_optional_argument_defines_the_key(self):
        result = self.check({
            "main.tex": "\\label[appsec]{sec:x}\nSee \\cref{sec:x}.\n"})
        self.assertEqual(self.of_type(result, "undefined-ref"), [])


class CitationTests(ProjectCase):
    BIB = "@article{known,\n  title = {A Title},\n  year = 2020,\n}\n"

    def test_reports_cite_key_missing_from_the_bibliography(self):
        result = self.check({
            "main.tex": "\\cite{known}\n\\cite{unknown}\n"
                        "\\bibliography{refs}\n",
            "refs.bib": self.BIB,
        })
        found = [(p["key"], p["file"], p["line"])
                 for p in self.of_type(result, "missing-citation")]
        self.assertEqual(found, [("unknown", "main.tex", 2)])

    def test_cite_family_with_optional_arguments_and_lists_is_checked(self):
        result = self.check({
            "main.tex": "\\citep[see][p.~3]{known, k1}\n"
                        "\\citet{k2} \\citealp*{k3} \\citeauthor{k4}\n"
                        "\\citeyear{k5} \\parencite[p.~2]{k6} \\textcite{k7}\n"
                        "\\citestyle{acl} \\nocite{*}\n"
                        "\\bibliography{refs}\n",
            "refs.bib": self.BIB,
        })
        found = sorted(p["key"]
                       for p in self.of_type(result, "missing-citation"))
        self.assertEqual(found, ["k1", "k2", "k3", "k4", "k5", "k6", "k7"])

    def test_addbibresource_files_are_searched(self):
        result = self.check({
            "main.tex": "\\addbibresource[location=local]{refs.bib}\n"
                        "\\parencite{known} \\parencite{other}\n",
            "refs.bib": self.BIB,
        })
        found = [p["key"] for p in self.of_type(result, "missing-citation")]
        self.assertEqual(found, ["other"])

    def test_bibitem_entries_satisfy_citations(self):
        result = self.check({
            "main.tex": "\\cite{a,b,c}\n\\begin{thebibliography}{9}\n"
                        "\\bibitem{a} A.\n\\bibitem[B(2020)]{b} B.\n"
                        "\\end{thebibliography}\n"})
        found = [p["key"] for p in self.of_type(result, "missing-citation")]
        self.assertEqual(found, ["c"])

    def test_reports_bibliography_file_that_does_not_exist(self):
        result = self.check({
            "main.tex": "\\cite{known}\n\\bibliography{refs,nothere}\n",
            "refs.bib": self.BIB,
        })
        found = [(p["path"], p["file"], p["line"])
                 for p in self.of_type(result, "missing-bib-file")]
        self.assertEqual(found, [("nothere.bib", "main.tex", 2)])
        self.assertEqual(self.of_type(result, "missing-citation"), [])

    @unittest.skipUnless(shutil.which("kpsewhich"), "kpsewhich not installed")
    def test_bibliography_file_from_the_tex_distribution_is_used(self):
        found = subprocess.run(["kpsewhich", "xampl.bib"],
                               capture_output=True, text=True).stdout.strip()
        if not found:
            self.skipTest("xampl.bib is not in this TeX distribution")
        result = self.check({
            "main.tex": "\\cite{article-full}\n\\bibliography{xampl}\n"})
        self.assertEqual(self.of_type(result, "missing-bib-file"), [])
        self.assertEqual(self.of_type(result, "missing-citation"), [])


class EncodingTests(ProjectCase):
    def test_latin1_source_and_bib_are_read_without_crashing(self):
        root = self.project({})
        with open(os.path.join(root, "main.tex"), "wb") as fh:
            fh.write(b"Caf\xe9 \\ref{x} \\cite{k}\n\\bibliography{refs}\n")
        with open(os.path.join(root, "refs.bib"), "wb") as fh:
            fh.write(b"@misc{k, title={Caf\xe9}}\n")
        result = latex_check.static_check(os.path.join(root, "main.tex"))
        self.assertEqual([p["key"] for p in self.of_type(result, "undefined-ref")],
                         ["x"])
        self.assertEqual(self.of_type(result, "missing-citation"), [])


class GraphicsTests(ProjectCase):
    def test_reports_missing_figure_and_accepts_known_extensions(self):
        result = self.check({
            "main.tex": "\\includegraphics[width=\\linewidth]{figures/plot}\n"
                        "\\includegraphics{figures/photo.jpg}\n"
                        "\\includegraphics*{figures/scan}\n"
                        "\\includegraphics{figures/missing}\n",
            "figures/plot.pdf": "",
            "figures/photo.jpg": "",
            "figures/scan.eps": "",
        })
        found = [(p["path"], p["file"], p["line"])
                 for p in self.of_type(result, "missing-graphic")]
        self.assertEqual(found, [("figures/missing", "main.tex", 4)])

    def test_graphicspath_directories_are_searched(self):
        result = self.check({
            "main.tex": "\\graphicspath{{figures/}{./img/}}\n"
                        "\\includegraphics{plot}\n"
                        "\\includegraphics{nothere}\n",
            "img/plot.png": "",
        })
        found = [p["path"] for p in self.of_type(result, "missing-graphic")]
        self.assertEqual(found, ["nothere"])

    def test_graphics_paths_built_from_macros_are_not_checked(self):
        result = self.check({
            "main.tex": "\\newcommand{\\fig}[1]{\\includegraphics{#1}}\n"
                        "\\includegraphics{\\figdir/plot}\n"})
        self.assertEqual(self.of_type(result, "missing-graphic"), [])


def run_cli(*args, **kwargs):
    return subprocess.run([sys.executable, SCRIPT] + list(args),
                          capture_output=True, text=True, **kwargs)


def summarize(problem):
    """One comparable tuple per problem, independent of output layout."""
    if problem["type"] in ("duplicate-label", "duplicate-bib-key"):
        return (problem["type"], problem["key"],
                tuple("%s:%d" % (l["file"], l["line"])
                      for l in problem["locations"]))
    if problem["type"] == "probable-duplicate-entry":
        return (problem["type"], tuple(problem["keys"]),
                tuple("%s:%d" % (l["file"], l["line"])
                      for l in problem["locations"]))
    return (problem["type"], problem.get("key", problem.get("path")),
            "%s:%d" % (problem["file"], problem["line"]))


class FixtureProjectCliTests(unittest.TestCase):
    MAIN = os.path.join(FIXTURES, "main.tex")

    def test_json_lists_exactly_the_planted_problems_and_exits_1(self):
        proc = run_cli(self.MAIN, "--json")
        self.assertEqual(proc.returncode, 1, proc.stderr)
        report = json.loads(proc.stdout)
        self.assertEqual(report["files"], ["main.tex", "ch1.tex", "ch2.tex"])
        self.assertEqual(report["bib_files"], ["refs.bib"])
        self.assertEqual(sorted(summarize(p) for p in report["problems"]), [
            ("duplicate-label", "sec:setup", ("ch1.tex:6", "ch2.tex:4")),
            ("missing-citation", "nosuchkey", "ch1.tex:7"),
            ("missing-graphic", "figures/missing-plot", "ch2.tex:7"),
            ("probable-duplicate-entry", ("doe2021", "doe2021copy"),
             ("refs.bib:1", "refs.bib:8")),
            ("undefined-ref", "sec:nowhere", "ch2.tex:5"),
        ])

    def test_default_markdown_report_names_each_problem_and_location(self):
        proc = run_cli(self.MAIN)
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertTrue(proc.stdout.startswith("# "), proc.stdout[:80])
        for needle in ("sec:nowhere", "ch2.tex:5", "nosuchkey", "ch1.tex:7",
                       "sec:setup", "ch1.tex:6", "ch2.tex:4",
                       "figures/missing-plot", "ch2.tex:7", "doe2021copy",
                       "refs.bib:1", "refs.bib:8"):
            self.assertIn(needle, proc.stdout)


class RenderMarkdownTests(unittest.TestCase):
    def test_build_problems_info_and_steps_are_rendered(self):
        result = {
            "main": "main.tex", "files": ["main.tex"], "bib_files": [],
            "bib_tool": None,
            "problems": [
                {"type": "latex-error", "message": "Undefined control sequence.",
                 "line": 3},
                {"type": "log-undefined-ref", "key": "sec:gone", "page": "2",
                 "input_line": 7},
                {"type": "log-undefined-citation", "key": "doe", "page": "3",
                 "input_line": None},
                {"type": "log-multiply-defined-label", "key": "dup"},
                {"type": "log-missing-file", "path": "fig.png"},
                {"type": "overfull-box", "box": "hbox", "size_pt": 12.3,
                 "lines": "10--12", "text": "Overfull \\hbox (12.3pt too wide)"},
                {"type": "build-error",
                 "message": "pdflatex timed out after 600 s"},
            ],
            "info": [
                {"type": "small-overfull-box", "box": "hbox", "size_pt": 0.5,
                 "lines": "30", "text": "Overfull \\hbox (0.5pt too wide)"},
                {"type": "rerun-needed",
                 "message": "Rerun to get cross-references right."},
                {"type": "unresolved-marks", "page": 4, "count": 2},
            ],
            "build": {"engine": "pdflatex", "stem": "main", "error": None,
                      "steps": [{"command": "pdflatex -interaction=nonstopmode"
                                            " main.tex",
                                 "returncode": 1, "timed_out": False}],
                      "log": "/x/main.log", "pdf": "/x/main.pdf"},
        }
        md = latex_check.render_markdown(result)
        for needle in ("Undefined control sequence.", "line 3", "sec:gone",
                       "page 2", "doe", "dup", "fig.png", "12.3pt", "10--12",
                       "timed out", "0.5pt", "Rerun to get", "page 4",
                       "pdflatex -interaction=nonstopmode main.tex",
                       "/x/main.pdf"):
            self.assertIn(needle, md)


class CliUsageTests(ProjectCase):
    def test_missing_main_file_is_a_usage_error(self):
        missing = os.path.join(self.project({}), "nothere.tex")
        proc = run_cli(missing)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("nothere.tex", proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)


CLEAN_DOC = ("\\documentclass{article}\n\\begin{document}\n"
             "\\section{One}\\label{sec:one}\nSee Section~\\ref{sec:one}.\n"
             "\\end{document}\n")


class BuildToolTests(ProjectCase):
    def test_missing_engine_is_an_environment_error_naming_the_tool(self):
        root = self.project({"main.tex": CLEAN_DOC})
        empty_path = self.project({})
        proc = run_cli(os.path.join(root, "main.tex"), "--build",
                       "--engine", "xelatex", env={"PATH": empty_path})
        self.assertEqual(proc.returncode, 2)
        self.assertIn("xelatex", proc.stderr)
        self.assertNotIn("usage:", proc.stderr)  # not an argparse rejection
        self.assertNotIn("Traceback", proc.stderr)

    def fake_tools(self, *names):
        """A PATH dir whose tools only record their argv and cwd, plus the
        file they record to."""
        bin_dir = self.project({})
        record = os.path.join(bin_dir, "calls.jsonl")
        for name in names:
            path = os.path.join(bin_dir, name)
            with open(path, "w") as fh:
                fh.write("#!%s\nimport json, os, sys\n"
                         "with open(%r, 'a') as fh:\n"
                         "    fh.write(json.dumps([os.path.basename(sys.argv[0]),"
                         " sys.argv[1:], os.getcwd()]) + '\\n')\n"
                         "open('main.log', 'w').write('Fake log.\\n')\n"
                         % (sys.executable, record))
            os.chmod(path, 0o755)
        return bin_dir, record

    def test_latexmk_is_used_when_available(self):
        root = self.project({"main.tex": CLEAN_DOC})
        bin_dir, record = self.fake_tools("latexmk", "xelatex")
        proc = run_cli(os.path.join(root, "main.tex"), "--build",
                       "--engine", "xelatex", env={"PATH": bin_dir})
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        with open(record) as fh:
            calls = [json.loads(line) for line in fh]
        self.assertEqual(
            [(tool, argv, os.path.realpath(cwd)) for tool, argv, cwd in calls],
            [("latexmk", ["-xelatex", "-interaction=nonstopmode", "main.tex"],
              os.path.realpath(root))])

    def test_a_step_that_times_out_stops_the_build_and_is_a_problem(self):
        root = self.project({"main.tex": CLEAN_DOC})
        bin_dir = self.project({})
        slow = os.path.join(bin_dir, "pdflatex")
        with open(slow, "w") as fh:
            fh.write("#!%s\nimport time\ntime.sleep(30)\n" % sys.executable)
        os.chmod(slow, 0o755)
        with mock.patch.dict(os.environ, {"PATH": bin_dir}):
            build = latex_check.run_build(os.path.join(root, "main.tex"),
                                          "pdflatex", None, timeout=1)
        self.assertEqual(len(build["steps"]), 1)
        self.assertTrue(build["steps"][0]["timed_out"])
        problems, _ = latex_check.build_findings(build)
        self.assertEqual([p["type"] for p in problems], ["build-error"])
        self.assertIn("timed out", problems[0]["message"])

    def test_a_build_that_leaves_no_log_is_a_problem(self):
        root = self.project({"main.tex": CLEAN_DOC})
        bin_dir = self.project({})
        broken = os.path.join(bin_dir, "pdflatex")
        with open(broken, "w") as fh:
            fh.write("#!%s\nimport sys\nsys.exit(1)\n" % sys.executable)
        os.chmod(broken, 0o755)
        with mock.patch.dict(os.environ, {"PATH": bin_dir}):
            build = latex_check.run_build(os.path.join(root, "main.tex"),
                                          "pdflatex", None)
        problems, _ = latex_check.build_findings(build)
        self.assertEqual([p["type"] for p in problems], ["build-error"])
        self.assertIn("main.log", problems[0]["message"])

    @unittest.skipIf(shutil.which("biber"), "biber is installed")
    def test_biblatex_document_needs_biber(self):
        root = self.project({"main.tex": (
            "\\documentclass{article}\n\\usepackage{biblatex}\n"
            "\\addbibresource{refs.bib}\n\\begin{document}\n\\end{document}\n"),
            "refs.bib": ""})
        proc = run_cli(os.path.join(root, "main.tex"), "--build")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("biber", proc.stderr)
        self.assertNotIn("usage:", proc.stderr)


@unittest.skipUnless(shutil.which("pdflatex"), "pdflatex not installed")
class BuildTests(ProjectCase):
    def build(self, files, *extra):
        root = self.project(files)
        proc = run_cli(os.path.join(root, "main.tex"), "--build", "--json",
                       *extra)
        self.assertNotIn("Traceback", proc.stderr)
        return proc, root

    def test_build_reports_latex_errors_from_the_log(self):
        proc, _ = self.build({"main.tex": (
            "\\documentclass{article}\n\\begin{document}\n"
            "Hello \\undefinedmacro.\n\\end{document}\n")})
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        report = json.loads(proc.stdout)
        errors = [p for p in report["problems"] if p["type"] == "latex-error"]
        self.assertEqual([(e["message"], e["line"]) for e in errors],
                         [("Undefined control sequence.", 3)])

    def test_clean_document_builds_with_no_problems_and_exits_0(self):
        # The \ref only resolves on a second engine pass.
        proc, root = self.build({"main.tex": CLEAN_DOC})
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        report = json.loads(proc.stdout)
        self.assertEqual(report["problems"], [])
        self.assertEqual(report["build"]["pdf"], os.path.join(root, "main.pdf"))
        self.assertTrue(os.path.isfile(report["build"]["pdf"]))

    @unittest.skipUnless(shutil.which("pdftotext"), "pdftotext not installed")
    def test_unresolved_references_are_counted_in_the_pdf(self):
        proc, _ = self.build({"main.tex": (
            "\\documentclass{article}\n\\begin{document}\n"
            "See Section~\\ref{sec:gone}.\n\\end{document}\n")})
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        report = json.loads(proc.stdout)
        self.assertIn(("log-undefined-ref", "sec:gone"),
                      [(p["type"], p.get("key")) for p in report["problems"]])
        marks = [i for i in report["info"] if i["type"] == "unresolved-marks"]
        self.assertEqual([(m["page"], m["count"]) for m in marks], [(1, 1)])

    @unittest.skipUnless(shutil.which("bibtex"), "bibtex not installed")
    def test_bibtex_runs_when_the_document_has_a_bibliography(self):
        proc, _ = self.build({
            "main.tex": "\\documentclass{article}\n\\begin{document}\n"
                        "As shown by \\cite{known}.\n"
                        "\\bibliographystyle{plain}\n\\bibliography{refs}\n"
                        "\\end{document}\n",
            "refs.bib": "@misc{known, author={Doe, Jane}, "
                        "title={A Synthetic Note}, year={2020}}\n",
        })
        self.assertEqual(proc.returncode, 0, proc.stdout)


class ParseLogTests(unittest.TestCase):
    def test_errors_are_lines_starting_with_bang_with_their_input_line(self):
        log = ("(./main.tex (./ch1.tex\n"
               "! Undefined control sequence.\n"
               "l.12 \\foo\n"
               "         bar\n"
               "! LaTeX Error: Something else.\n"
               "\n"
               "See the LaTeX manual or LaTeX Companion for explanation.\n"
               "!pdfTeX warning lookalike without a space\n")
        errors = latex_check.parse_log(log)["errors"]
        self.assertEqual([(e["message"], e["line"]) for e in errors], [
            ("Undefined control sequence.", 12),
            ("LaTeX Error: Something else.", None),
        ])

    def test_undefined_references_and_citations(self):
        log = ("LaTeX Warning: Reference `sec:nowhere' on page 3 undefined on "
               "input line 42.\n"
               "Package natbib Warning: Citation `nosuchkey' on page 4 "
               "undefined on input line 7.\n"
               "LaTeX Warning: Citation 'bibkey' on page iv undefined on input "
               "line 9.\n"
               "LaTeX Warning: There were undefined references.\n")
        parsed = latex_check.parse_log(log)
        self.assertEqual(parsed["undefined_refs"],
                         [{"key": "sec:nowhere", "page": "3", "input_line": 42}])
        self.assertEqual(parsed["undefined_citations"], [
            {"key": "nosuchkey", "page": "4", "input_line": 7},
            {"key": "bibkey", "page": "iv", "input_line": 9},
        ])

    def test_multiply_defined_labels(self):
        log = ("LaTeX Warning: Label `sec:setup' multiply defined.\n"
               "LaTeX Warning: There were multiply-defined labels.\n")
        self.assertEqual(latex_check.parse_log(log)["multiply_defined_labels"],
                         ["sec:setup"])

    def test_missing_files(self):
        log = ("! LaTeX Error: File `missing-chapter.tex' not found.\n"
               "LaTeX Warning: File `figures/plot.png' not found on input "
               "line 20.\n"
               "! Package pdftex.def Error: File `figures/plot.png' not found: "
               "using draft setting.\n"
               "No file main.bbl.\n")
        self.assertEqual(latex_check.parse_log(log)["missing_files"],
                         ["missing-chapter.tex", "figures/plot.png"])

    def test_overfull_boxes_with_size_and_lines(self):
        log = ("Overfull \\hbox (12.3pt too wide) in paragraph at lines 10--12\n"
               "[]\\OT1/cmr/m/n/10 Some text|\n"
               "Overfull \\hbox (0.5pt too wide) detected at line 30\n"
               "Underfull \\hbox (badness 10000) in paragraph at lines 5--6\n"
               "Overfull \\vbox (15.0pt too high) has occurred while \\output "
               "is active []\n")
        boxes = latex_check.parse_log(log)["overfull_boxes"]
        self.assertEqual([(b["box"], b["size_pt"], b["lines"]) for b in boxes], [
            ("hbox", 12.3, "10--12"),
            ("hbox", 0.5, "30"),
            ("vbox", 15.0, None),
        ])

    def test_leftover_rerun_message(self):
        log = ("LaTeX Warning: Label(s) may have changed. Rerun to get "
               "cross-references right.\n")
        self.assertEqual(latex_check.parse_log(log)["rerun"],
                         "LaTeX Warning: Label(s) may have changed. Rerun to "
                         "get cross-references right.")
        self.assertIsNone(latex_check.parse_log("All fine.\n")["rerun"])

    def test_lines_wrapped_at_79_characters_are_rejoined(self):
        key = "sec:" + "x" * 60
        message = ("LaTeX Warning: Reference `%s' on page 3 undefined on input "
                   "line 42." % key)
        wrapped = "\n".join(message[i:i + 79]
                            for i in range(0, len(message), 79))
        self.assertGreater(wrapped.count("\n"), 0)
        parsed = latex_check.parse_log(wrapped + "\n")
        self.assertEqual(parsed["undefined_refs"],
                         [{"key": key, "page": "3", "input_line": 42}])

    def test_wrap_detection_counts_utf8_bytes_like_pdftex(self):
        key = "sec:café-" + "x" * 50
        message = ("LaTeX Warning: Reference `%s' on page 3 undefined on input "
                   "line 42." % key).encode("utf-8")
        chunks = [message[i:i + 79] for i in range(0, len(message), 79)]
        wrapped = "\n".join(c.decode("utf-8") for c in chunks)
        self.assertEqual(len(wrapped.splitlines()[0]), 78)  # 79 bytes
        parsed = latex_check.parse_log(wrapped + "\n")
        self.assertEqual([r["key"] for r in parsed["undefined_refs"]], [key])

    def test_full_79_character_line_does_not_swallow_a_following_error(self):
        log = "(" + "a" * 78 + "\n! Undefined control sequence.\nl.5 \\foo\n"
        errors = latex_check.parse_log(log)["errors"]
        self.assertEqual([(e["message"], e["line"]) for e in errors],
                         [("Undefined control sequence.", 5)])


class LogFindingsTests(unittest.TestCase):
    def test_overfull_boxes_over_10pt_are_problems_smaller_ones_info(self):
        parsed = latex_check.parse_log(
            "Overfull \\hbox (12.3pt too wide) in paragraph at lines 10--12\n"
            "Overfull \\hbox (10.0pt too wide) in paragraph at lines 20--21\n"
            "Overfull \\hbox (0.5pt too wide) detected at line 30\n")
        problems, info = latex_check.log_findings(parsed)
        self.assertEqual([(p["type"], p["size_pt"]) for p in problems],
                         [("overfull-box", 12.3)])
        self.assertEqual([(i["type"], i["size_pt"]) for i in info],
                         [("small-overfull-box", 10.0),
                          ("small-overfull-box", 0.5)])

    def test_errors_undefined_and_missing_files_are_problems_rerun_is_info(self):
        parsed = latex_check.parse_log(
            "! Undefined control sequence.\nl.3 \\foo\n"
            "LaTeX Warning: Reference `r' on page 1 undefined on input line 4.\n"
            "LaTeX Warning: Citation `c' on page 1 undefined on input line 5.\n"
            "LaTeX Warning: Label `l' multiply defined.\n"
            "LaTeX Warning: File `f.png' not found on input line 6.\n"
            "LaTeX Warning: Label(s) may have changed. Rerun to get "
            "cross-references right.\n")
        problems, info = latex_check.log_findings(parsed)
        self.assertEqual(sorted((p["type"], p.get("key") or p.get("path")
                                 or p.get("message")) for p in problems), [
            ("latex-error", "Undefined control sequence."),
            ("log-missing-file", "f.png"),
            ("log-multiply-defined-label", "l"),
            ("log-undefined-citation", "c"),
            ("log-undefined-ref", "r"),
        ])
        self.assertEqual([i["type"] for i in info], ["rerun-needed"])


class UnresolvedMarksTests(unittest.TestCase):
    def test_counts_double_question_marks_per_page(self):
        text = "Intro\fSee Section ?? and Figure ??.\fNothing\fTable ??\f"
        self.assertEqual(latex_check.count_unresolved_marks(text),
                         [{"page": 2, "count": 2}, {"page": 4, "count": 1}])


class ParseBibTests(unittest.TestCase):
    def test_strings_concatenation_and_paren_delimited_entries(self):
        entries = latex_check.parse_bib(
            '@string{acl = "Proc. of ACL"}\n'
            '@inproceedings{a, title = {Mail x@y.org},\n'
            '  booktitle = acl # " 2020"}\n'
            '@comment{ignored}\n'
            '@book(b, title = "Paren {"}Entry")\n'
            '@misc{c, title = {After}}\n')
        self.assertEqual([(e["key"], e["type"], e["line"]) for e in entries],
                         [("a", "inproceedings", 2), ("b", "book", 5),
                          ("c", "misc", 6)])
        self.assertEqual(entries[0]["fields"]["title"], "Mail x@y.org")
        self.assertEqual(entries[0]["fields"]["booktitle"], "acl 2020")
        self.assertEqual(entries[1]["fields"]["title"], 'Paren {"}Entry')


class BibDuplicateTests(ProjectCase):
    def test_reports_bib_key_defined_twice_within_or_across_files(self):
        result = self.check({
            "main.tex": "\\bibliography{a,b}\n",
            "a.bib": "@article{x, title={One}}\n@book{x, title={Two}}\n"
                     "@misc{y, title={Three}}\n",
            "b.bib": "@misc{y, title={Four}}\n",
        })
        found = [(p["key"], p["locations"])
                 for p in self.of_type(result, "duplicate-bib-key")]
        self.assertEqual(found, [
            ("x", [{"file": "a.bib", "line": 1}, {"file": "a.bib", "line": 2}]),
            ("y", [{"file": "a.bib", "line": 3}, {"file": "b.bib", "line": 1}]),
        ])

    def test_bib_file_named_by_several_chapters_is_read_once(self):
        result = self.check({
            "main.tex": "\\include{ch1}\n\\include{ch2}\n",
            "ch1.tex": "\\cite{x}\n\\bibliography{refs}\n",
            "ch2.tex": "\\cite{x}\n\\bibliography{./refs}\n",
            "refs.bib": "@misc{x, title={One}}\n",
        })
        self.assertEqual(self.of_type(result, "duplicate-bib-key"), [])

    def test_reports_different_keys_with_the_same_normalized_title(self):
        result = self.check({
            "main.tex": "\\bibliography{refs}\n",
            "refs.bib": (
                "@article{smith2020,\n"
                "  title = {Topic Models for {L}ong Documents},\n"
                "  year = 2020,\n"
                "}\n"
                "@inproceedings{smith2020b,\n"
                "  booktitle = {Proceedings of Something},\n"
                "  Title = \"Topic models for long-documents.\",\n"
                "}\n"
                "@misc{other,\n"
                "  title = {Topic Models for Short Documents},\n"
                "  note = {Proceedings of Something},\n"
                "}\n"),
        })
        found = [(p["keys"], p["locations"])
                 for p in self.of_type(result, "probable-duplicate-entry")]
        self.assertEqual(found, [(["smith2020", "smith2020b"],
                                  [{"file": "refs.bib", "line": 1},
                                   {"file": "refs.bib", "line": 5}])])


if __name__ == "__main__":
    unittest.main()
