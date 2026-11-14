"""Tests for behaviours added after the first review round.

- latex_check --list-files: the files a thesis really contains (\\input and
  \\include followed), so the other scanners can be given the full list.
- render_pages --find: the physical PDF pages that contain a phrase (log page
  numbers are printed labels, not PDF pages).
- consistency_scan: letter-digit names written two ways (F1 / F-1).
- consistency_scan: a line with several bare \\cite commands is listed once.
"""
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

import consistency_scan  # noqa: E402
from handmade_pdf import write_pdf  # noqa: E402


def run(script, *args, cwd=None):
    return subprocess.run([sys.executable, os.path.join(SCRIPTS, script)] + list(args),
                          capture_output=True, text=True, cwd=cwd)


def project(test, files):
    root = tempfile.mkdtemp(prefix="review_fixes_")
    test.addCleanup(shutil.rmtree, root, ignore_errors=True)
    for rel, text in files.items():
        path = os.path.join(root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
    return root


class ListFiles(unittest.TestCase):
    def test_lists_main_and_every_input_and_include_relative_to_cwd(self):
        root = project(self, {
            "main.tex": "\\documentclass{book}\\begin{document}\n\\input{front/intro}\n"
                        "\\include{chapters/ch1}\n\\end{document}\n",
            "front/intro.tex": "Intro text.\n",
            "chapters/ch1.tex": "\\input{chapters/table1}\nChapter text.\n",
            "chapters/table1.tex": "\\begin{tabular}{l}x\\end{tabular}\n",
        })
        r = run("latex_check.py", "main.tex", "--list-files", cwd=root)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.split(), ["main.tex", "front/intro.tex",
                                            "chapters/ch1.tex", "chapters/table1.tex"])


class FindPhrase(unittest.TestCase):
    def setUp(self):
        if not shutil.which("pdftotext"):
            self.skipTest("pdftotext not installed")
        self.dir = tempfile.mkdtemp(prefix="find_phrase_")
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.pdf = os.path.join(self.dir, "doc.pdf")
        write_pdf(self.pdf, [["Front matter page"], ["Results are in Table 2"],
                             ["Nothing here"], ["See Table   2 again"]])

    def test_prints_physical_pages_containing_the_phrase(self):
        r = run("render_pages.py", self.pdf, "--find", "table 2")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.split(), ["2", "4"])

    def test_exits_1_when_the_phrase_is_nowhere(self):
        r = run("render_pages.py", self.pdf, "--find", "Table 9")
        self.assertEqual(r.returncode, 1)
        self.assertEqual(r.stdout.strip(), "")


class LetterDigitVariants(unittest.TestCase):
    def test_reports_f1_written_with_and_without_hyphen(self):
        docs = [("a.tex", "We report F1 on both sets.\n"),
                ("b.tex", "The F-1 score improves.\n")]
        groups = consistency_scan.check_hyphenation(docs)
        flat = json.dumps(groups)
        self.assertIn("F-1", flat)
        self.assertIn("F1", flat)

    def test_ignores_a_digit_name_written_one_way(self):
        docs = [("a.tex", "We use GPT-2 here.\n"), ("b.tex", "GPT-2 again.\n")]
        groups = consistency_scan.check_hyphenation(docs)
        self.assertNotIn("GPT-2", json.dumps(groups))


class BareCiteOncePerLine(unittest.TestCase):
    def test_line_with_three_bare_cites_is_listed_once(self):
        docs = [("a.tex", "Metrics \\cite{x} and \\cite{y} and \\cite{z}.\nWe follow \\citep{w}.\n")]
        result = consistency_scan.check_citations(docs)
        bare = result["bare_cite"]
        self.assertEqual(len(bare), 1, bare)



class UnchangedRecognisesAppliedFixes(unittest.TestCase):
    """A fix applied exactly as asked leaves the passage very similar
    (64.3 -> 63.4), which must not be reported as a stuck passage."""

    CRITIQUE = """### F1 | faithfulness | major | local
- Location: chapters/a.tex:1
- Original: "an accuracy of 64.3 on the dev set"
- Fix: "an accuracy of 63.4 on the dev set"
- Reasoning: Table 2 says 63.4.
- Rule: -

### F2 | readability | major | local
- Location: chapters/a.tex:2
- Original: "The model, which we train with the loss that we propose, which is cheap, is fast."
- Fix: Split this sentence in two and lead with the speed result.
- Reasoning: three clauses before the point.
- Rule: -
"""

    def statuses(self, after):
        d = tempfile.mkdtemp(prefix="unchanged_applied_")
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        before = ("We reach an accuracy of 64.3 on the dev set with the base model.\n"
                  "The model, which we train with the loss that we propose, which is cheap, is fast.\n")
        for name, text in (("c.md", self.CRITIQUE), ("b.tex", before), ("a.tex", after)):
            with open(os.path.join(d, name), "w", encoding="utf-8") as fh:
                fh.write(text)
        r = run("stagnation.py", "unchanged", "--critique", os.path.join(d, "c.md"),
                "--before", os.path.join(d, "b.tex"), "--after", os.path.join(d, "a.tex"), "--json")
        return r.returncode, {x["finding"]: x["status"] for x in json.loads(r.stdout)["results"]}

    def test_fix_text_present_in_the_new_version_is_applied(self):
        rc, st = self.statuses("We reach an accuracy of 63.4 on the dev set with the base model.\n"
                               "The model is fast. We train it with our cheap loss.\n")
        self.assertEqual(st["F1"], "applied")
        self.assertEqual(rc, 0)

    def test_instruction_fix_with_wording_left_alone_is_still_unchanged(self):
        rc, st = self.statuses("We reach an accuracy of 63.4 on the dev set with the base model.\n"
                               "The model, which we train with the loss we propose, which is cheap, is fast.\n")
        self.assertEqual(st["F2"], "unchanged")
        self.assertEqual(rc, 1)


class NumbersNeverSupportedBySelf(unittest.TestCase):
    def test_a_file_listed_as_its_own_source_is_skipped(self):
        root = project(self, {
            "conclusion.tex": "The pattern model reaches 0.81 F1.\n",
            "ch2.tex": "Our model reaches 0.72 F1 on WikiSection.\n",
        })
        r = run("check_numbers.py", "conclusion.tex", "--source", "ch2.tex",
                "--source", "conclusion.tex", cwd=root)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("0.81", r.stdout)


class ParseRejectsHeadersItCannotRead(unittest.TestCase):
    BODY = ("- Location: a.tex:1\n- Original: \"x y z\"\n- Fix: \"y z\"\n"
            "- Reasoning: r\n- Rule: -\n")

    def parse(self, text):
        root = project(self, {"c.md": text})
        return run("stagnation.py", "parse", os.path.join(root, "c.md"))

    def test_indented_finding_header_is_an_error(self):
        r = self.parse("  ### F1 | readability | major | local\n" + self.BODY)
        self.assertEqual(r.returncode, 1, r.stdout)

    def test_bold_finding_header_is_an_error(self):
        r = self.parse("**F1 | readability | major | local**\n" + self.BODY)
        self.assertEqual(r.returncode, 1, r.stdout)


class NearDuplicatesOnlyWithinCategory(unittest.TestCase):
    def test_similar_rules_in_different_categories_are_not_paired(self):
        rules = ("## G1 | terminology\n"
                 "- Rule: Use the core terms exactly as defined in thesis-work/plan.md in every chapter.\n"
                 "- Why: w\n- Check: read\n- Origin: seed\n\n"
                 "## G2 | notation\n"
                 "- Rule: Use the notation exactly as defined in thesis-work/plan.md in every chapter.\n"
                 "- Why: w\n- Check: read\n- Origin: seed\n")
        root = project(self, {"global.md": rules})
        r = run("rules_lint.py", "global.md", cwd=root)
        self.assertEqual(r.returncode, 0, r.stdout)


class RenderDefaultsIntoThesisWork(unittest.TestCase):
    def test_default_output_folder_is_thesis_work_pages(self):
        if not (shutil.which("pdftoppm") and shutil.which("pdfinfo")):
            self.skipTest("poppler not installed")
        root = tempfile.mkdtemp(prefix="render_default_")
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        write_pdf(os.path.join(root, "doc.pdf"), [["Page one"]])
        r = run("render_pages.py", "doc.pdf", "--pages", "1", "--dpi", "40", cwd=root)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), os.path.join("thesis-work", "pages", "doc-p1.png"))


class ParseRejectsOtherHeaderStyles(unittest.TestCase):
    BODY = ParseRejectsHeadersItCannotRead.BODY

    def parse(self, text):
        root = project(self, {"c.md": text})
        return run("stagnation.py", "parse", os.path.join(root, "c.md"))

    def test_bold_id_inside_a_heading_is_an_error(self):
        self.assertEqual(self.parse("### **F1** | readability | major | local\n" + self.BODY).returncode, 1)

    def test_list_item_or_numbered_header_is_an_error(self):
        self.assertEqual(self.parse("- **F1 | readability | major | local**\n" + self.BODY).returncode, 1)
        self.assertEqual(self.parse("1. **F1 | readability | major | local**\n" + self.BODY).returncode, 1)

    def test_bare_or_worded_header_is_an_error(self):
        self.assertEqual(self.parse("F1 | readability | major | local\n" + self.BODY).returncode, 1)
        self.assertEqual(self.parse("### Finding F1 | readability | major | local\n" + self.BODY).returncode, 1)

    def test_valid_block_minor_list_and_table_rows_still_pass(self):
        text = ("### F1 | readability | major | local\n" + self.BODY +
                "\n## Minor\n\n- F2 | typo in line 3\n\n| F3 | readability | major | x |\n")
        self.assertEqual(self.parse(text).returncode, 0)


if __name__ == "__main__":
    unittest.main()
