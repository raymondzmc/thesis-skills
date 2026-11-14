import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "skills", "thesis-kit", "scripts")
sys.path.insert(0, SCRIPTS)
sys.path.insert(0, HERE)

import check_numbers  # noqa: E402
from handmade_pdf import SAMPLE_LINE, write_pdf  # noqa: E402

HAVE_PDFTOTEXT = bool(shutil.which("pdftotext"))

SCRIPT = os.path.join(SCRIPTS, "check_numbers.py")
FIXTURES = os.path.join(HERE, "fixtures", "check_numbers")
CHAPTER = os.path.join(FIXTURES, "chapter.tex")
PAPER = os.path.join(FIXTURES, "paper.txt")


def run_main(*args):
    stdout, stderr = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = check_numbers.main(list(args))
    except SystemExit as exc:
        code = exc.code
    return code, stdout.getvalue(), stderr.getvalue()


def table_rows(markdown):
    """(line, token, status) for each data row of the Markdown table."""
    rows = []
    for row in markdown.splitlines():
        if not row.startswith("|") or set(row) <= set("|-: "):
            continue
        cells = [cell.strip() for cell in re.split(r"(?<!\\)\|", row)[1:-1]]
        if cells[0] == "line":
            continue
        rows.append((int(cells[0]), cells[1], cells[3]))
    return rows


def token_texts(text):
    return [token.text for token in check_numbers.find_tokens(text)]


def chapter_tokens(latex):
    """(line, token) pairs left after masking, checking that masking keeps
    every character position (so line numbers and contexts stay right)."""
    masked = check_numbers.mask_latex(latex)
    assert len(masked) == len(latex), "masking changed the text length"
    assert [i for i, c in enumerate(masked) if c == "\n"] == [
        i for i, c in enumerate(latex) if c == "\n"
    ], "masking moved line breaks"
    return [(t.line, t.text) for t in check_numbers.find_tokens(masked)]


class MaskCommentsTest(unittest.TestCase):
    def test_comments_are_masked_but_escaped_percent_is_kept(self):
        latex = (
            "Acc 0.727 % was 0.71\n"
            "next 12.5\\% here % 0.99\n"
            "line break \\\\% 0.55 is a comment after \\\\\n"
            "\\begin{comment}\n0.42 old\n\\end{comment}\n"
            "kept 0.81\n"
        )
        self.assertEqual(
            chapter_tokens(latex), [(1, "0.727"), (2, "12.5\\%"), (7, "0.81")]
        )


class MaskReferencesTest(unittest.TestCase):
    def test_labels_refs_and_citations_are_masked(self):
        latex = (
            "See Table~\\ref{tab:results2021} and Eq.~\\eqref{eq:12}, \\autoref{fig:10},\n"
            "\\cref{sec:42}, \\Cref{app:77} on p.~\\pageref{p:99}.\\label{sec:2020}\n"
            "As shown by \\citet{smith2021} and \\citep[p.~45][]{lee2019,\n"
            "  kim2018}, \\citealp{a10}, \\citeauthor{b11} (\\citeyear{c12}) reach 0.93.\n"
            "\\parencite[see][12]{x2020}, \\nameref{sec:55}, \\crefrange{a:10}{a:12}.\n"
            "Not a ref: \\refstepcounter 2.5 or \\labelfont 3.5.\n"
        )
        self.assertEqual(chapter_tokens(latex), [(4, "0.93"), (6, "2.5"), (6, "3.5")])

    def test_urls_graphics_and_inputs_are_masked(self):
        latex = (
            "Code at \\url{https://example.org/v2/data%2020/x} with 0.88 recall.\n"
            "See \\href{https://doi.org/10.1145/12345}{our 2021 report}"
            " and \\nolinkurl{ftp://host/77}.\n"
            "\\includegraphics[width=0.48\\linewidth,trim=10 20 30 40]{figs/plot_2019.pdf}\n"
            "\\input{sections/part12}\\include{chapters/ch03} done\n"
        )
        # the % inside the URL does not start a comment that would hide 0.88
        self.assertEqual(chapter_tokens(latex), [(1, "0.88"), (2, "2021")])


class MaskLayoutTest(unittest.TestCase):
    def test_lengths_and_dimension_settings_are_masked(self):
        latex = (
            "\\vspace{-12pt}\\hspace*{1.5em}\\setlength{\\tabcolsep}{10pt}"
            "\\setlength\\arrayrulewidth{0.8pt}\\vspace{2\\baselineskip}\n"
            "\\renewcommand{\\arraystretch}{1.25}\\def\\arraystretch{1.35}"
            "\\renewcommand\\baselinestretch{1.15}\n"
            "\\begin{minipage}{0.45\\textwidth} a gap of 0.31 \\end{minipage}\n"
            "\\\\[-2mm] \\\\[3pt] \\kern 12bp \\rule{25cm}{.5ex}\n"
            "We trained 12 models in 36 hours on 224 px crops of 50 cm rods.\n"
        )
        self.assertEqual(
            chapter_tokens(latex),
            [(3, "0.31"), (5, "12"), (5, "36"), (5, "224"), (5, "50")],
        )

    def test_scale_spacing_font_and_counter_settings_are_masked(self):
        latex = (
            "\\scalebox{0.85}{0.91} \\linespread{1.3}\\setstretch{1.5}"
            " {\\fontsize{10}{12}\\selectfont 0.62}\n"
            "\\setcounter{secnumdepth}{12}\\addtocounter{table}{10}"
            " \\resizebox{0.9\\linewidth}{!}{0.74}\n"
        )
        self.assertEqual(chapter_tokens(latex), [(1, "0.91"), (1, "0.62"), (2, "0.74")])

    def test_unit_lengths_in_prose_are_still_checked(self):
        latex = (
            "A gain of 3pt; reads of 150bp, 10pc and (5mm) rods, 12in wide.\n"
            "\\addlinespace[2pt] \\specialrule{1pt}{2pt}{2pt} \\hskip 13pt"
            " \\geometry{margin=1in}\n"
        )
        self.assertEqual(
            chapter_tokens(latex),
            [(1, "3"), (1, "150"), (1, "10"), (1, "5"), (1, "12")],
        )

    def test_table_structure_is_masked_but_cells_are_kept(self):
        latex = (
            "\\begin{tabular}{p{2.5cm}*{3}{c}S[table-format=2.3]}\n"
            "\\begin{tabularx}{\\linewidth}{l*{12}{X}}\n"
            "\\multicolumn{12}{c|}{Mean 0.95} & \\multirow{15}{*}{0.88}"
            " & \\multirow[t]{16}{*}{0.77} \\\\\n"
            "\\cline{2-13} \\cmidrule(lr){10-12} \\cmidrule[0.5pt](l{2pt}){14-15}\n"
        )
        self.assertEqual(chapter_tokens(latex), [(3, "0.95"), (3, "0.88"), (3, "0.77")])

    def test_color_specs_are_masked_but_colored_values_are_kept(self):
        latex = (
            "\\rowcolor[gray]{0.95} 0.61 & \\cellcolor{blue!15}0.72"
            " & \\cellcolor[HTML]{E0E0E0} 0.83 \\\\\n"
            "\\definecolor{best}{RGB}{12,34,56}\\textcolor{red!60}{0.94}"
            " \\color{gray!50} \\columncolor{green!20}\n"
            "\\rowcolors{2}{gray!10}{white} \\colorbox{yellow!30}{0.45}\n"
        )
        self.assertEqual(
            chapter_tokens(latex),
            [(1, "0.61"), (1, "0.72"), (1, "0.83"), (2, "0.94"), (3, "0.45")],
        )


class FindTokensTest(unittest.TestCase):
    def test_finds_decimals_thousands_and_percentages_with_line_numbers(self):
        text = (
            "Accuracy improves from 0.671 to 0.727 on 1,000 documents (12.5\\%).\n"
            "We used 3 seeds and 2,048 samples.\n"
        )
        found = [(t.line, t.text) for t in check_numbers.find_tokens(text)]
        self.assertEqual(
            found,
            [(1, "0.671"), (1, "0.727"), (1, "1,000"), (1, "12.5\\%"),
             (2, "3"), (2, "2,048")],
        )

    def test_signs_leading_dots_versions_and_latex_separators(self):
        cases = {
            # a dash between numbers is a range, not a minus sign
            "from 2019--2021 and 2019-2021": ["2019", "2021", "2019", "2021"],
            # unary minus (ASCII or U+2212) is kept; subtraction x-12 is not
            "$-0.12$ and (−0.5) and x-12 and k=-10": ["-0.12", "−0.5", "12", "-10"],
            "+2.3 points; 0.5.": ["+2.3", "0.5"],
            # leading-dot decimal, but not the number after an abbreviation
            "an F1 of .727 (Fig.12)": ["1", ".727"],
            "PyTorch 1.13.1 on 2021.05.12": ["1.13.1", "2021.05.12"],
            "1{,}000 and 1\\,000 rows": ["1{,}000", "1\\,000"],
            "12,5 vs 12,345.6": ["12", "5", "12,345.6"],
        }
        for text, want in cases.items():
            with self.subTest(text=text):
                self.assertEqual(token_texts(text), want)


class CanonicalTest(unittest.TestCase):
    def test_normalizes_spelling_differences_of_the_same_number(self):
        cases = {
            "0.727": "0.727",
            ".727": "0.727",
            "90.50": "90.5",
            "2.0": "2",
            "2.00": "2",
            "100": "100",
            "1,000": "1000",
            "1{,}000": "1000",
            "1\\,000": "1000",
            "12.5\\%": "12.5",
            "12.5%": "12.5",
            "+2.3": "2.3",
            "−0.5": "-0.5",
            "–0.5": "-0.5",
            "-.5": "-0.5",
            "1.10.0": "1.10.0",
        }
        for token, want in cases.items():
            with self.subTest(token=token):
                self.assertEqual(check_numbers.canonical(token), want)


def match_line(token, source_text):
    index = check_numbers.build_index([("paper.txt", source_text)])
    match = check_numbers.lookup(index, token)
    return None if match is None else (match.source, match.line)


class LookupTest(unittest.TestCase):
    def test_matches_normalized_variants(self):
        cases = [
            (".727", "acc 0.727"),
            ("0.727", "acc .727"),
            ("90.50", "score 90.5"),
            ("2.0", "a 2x speedup"),
            ("1000", "1,000 docs"),
            ("1,000", "1000 docs"),
            ("12.5\\%", "a 12.5% gain"),
            ("12.5\\%", "a 12.5 gain"),
            ("-0.5", "delta −0.5"),
            ("-0.5", "f(x) = x−0.5"),
            ("0.5", "delta −0.5"),
            ("2021", "from 2019-2021"),
            ("1.13.1", "torch 1.13.1"),
        ]
        for token, source in cases:
            with self.subTest(token=token, source=source):
                self.assertEqual(match_line(token, source), ("paper.txt", 1))

    def test_respects_numeric_boundaries_and_signs(self):
        cases = [
            ("727", "acc 0.727"),  # fractional part of another number
            ("0.72", "acc 0.727"),
            ("12", "123 items"),
            ("12", "12.5 items"),
            ("12", "12,000 items"),
            ("-0.5", "delta 0.5"),  # a sign flip is a different number
            ("-12", "pages 10-12"),  # a range dash is not a minus
            ("1.13", "torch 1.13.1"),
        ]
        for token, source in cases:
            with self.subTest(token=token, source=source):
                self.assertIsNone(match_line(token, source))

    def test_reports_the_first_matching_line(self):
        self.assertEqual(match_line("0.727", "a\n0.727\nb 0.727"), ("paper.txt", 2))

    def test_counts_pages_from_form_feeds(self):
        text = "page one 0.5\fpage two 0.727\n\fthird 12.5\n"
        index = check_numbers.build_index([("paper.pdf", text)])
        self.assertEqual(check_numbers.lookup(index, "0.727"), ("paper.pdf", 1, 2))
        self.assertEqual(check_numbers.lookup(index, "12.5"), ("paper.pdf", 2, 3))
        plain = check_numbers.build_index([("notes.md", "no pages 0.727")])
        self.assertIsNone(check_numbers.lookup(plain, "0.727").page)


class ContextTest(unittest.TestCase):
    def contexts(self, latex):
        results, _ = check_numbers.check(latex, {})
        return [result["context"] for result in results]

    def test_context_is_one_line_without_comments(self):
        latex = "First line ends\n% hidden 0.99\nvalue 0.732 | next\n"
        self.assertEqual(self.contexts(latex), ["First line ends value 0.732 | next"])

    def test_context_keeps_about_40_characters_each_side(self):
        latex = "a" * 50 + " 0.732 " + "b" * 50
        self.assertEqual(self.contexts(latex), ["a" * 39 + " 0.732 " + "b" * 39])


class ReportTest(unittest.TestCase):
    def test_lists_only_unsupported_numbers_and_exits_1(self):
        code, out, _ = run_main(CHAPTER, "--source", PAPER)
        self.assertEqual(code, 1)
        # 0.056 is derived (0.727 - 0.671); 0.732 is a typo for 0.723
        self.assertEqual(
            table_rows(out), [(4, "0.056", "UNSUPPORTED"), (9, "0.732", "UNSUPPORTED")]
        )
        self.assertIn("7 tokens checked, 2 unsupported", out)

    def test_all_lists_every_checked_token_with_its_source_line(self):
        code, out, _ = run_main(CHAPTER, "--source", PAPER, "--all")
        self.assertEqual(code, 1)
        self.assertEqual(
            table_rows(out),
            [
                (2, "0.671", PAPER + ":2"),
                (2, "0.727", PAPER + ":2"),
                (2, "1,000", PAPER + ":2"),
                (2, "12.5\\%", PAPER + ":2"),
                (4, "0.056", "UNSUPPORTED"),
                (9, "0.732", "UNSUPPORTED"),
                (9, "90.50", PAPER + ":3"),
            ],
        )

    def test_ignore_skips_listed_numbers_in_any_spelling(self):
        for args in (["--ignore", "0.0560,.732"], ["--ignore", "0.056", "--ignore", "0.732"]):
            with self.subTest(args=args):
                code, out, _ = run_main(CHAPTER, "--source", PAPER, *args)
                self.assertEqual(code, 0)
                self.assertEqual(table_rows(out), [])
                self.assertIn("5 tokens checked, 0 unsupported (4 skipped", out)

    def test_min_digits_sets_the_shortest_number_checked(self):
        code, out, _ = run_main(CHAPTER, "--source", PAPER, "--min-digits", "4", "--all")
        self.assertEqual(code, 1)
        self.assertNotIn("12.5\\%", [token for _, token, _ in table_rows(out)])
        self.assertIn("6 tokens checked, 2 unsupported (3 skipped", out)
        code, out, _ = run_main(CHAPTER, "--source", PAPER, "--min-digits", "1", "--all")
        self.assertIn((5, "3", "UNSUPPORTED"), table_rows(out))

    def test_directory_source_reads_tex_and_txt_recursively(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "src")
            os.makedirs(os.path.join(src, "sub"))
            files = {
                "main.tex": "\\documentclass{article}\nWe obtain 0.732 here. % old value 0.056\n",
                os.path.join("sub", "extra.txt"): "Recall 77.7\n",
                os.path.join("sub", "table.csv"): "88.8\n",
            }
            for name, text in files.items():
                with open(os.path.join(src, name), "w") as handle:
                    handle.write(text)
            chapter = os.path.join(tmp, "chapter.tex")
            with open(chapter, "w") as handle:
                handle.write("Values 0.732, 0.056, 77.7 and 88.8.\n")
            code, out, _ = run_main(chapter, "--source", src, "--all")
        self.assertEqual(code, 1)
        self.assertEqual(
            table_rows(out),
            [
                (1, "0.732", os.path.join(src, "main.tex") + ":2"),
                (1, "0.056", "UNSUPPORTED"),  # only in a comment of the source
                (1, "77.7", os.path.join(src, "sub", "extra.txt") + ":1"),
                (1, "88.8", "UNSUPPORTED"),  # .csv files are not read
            ],
        )

    def test_directory_skips_a_txt_copy_of_a_tex_file(self):
        # paper_text.py writes the same flattened LaTeX to source.tex and
        # source.txt; only the masked .tex copy may count as support
        with tempfile.TemporaryDirectory() as tmp:
            folder = os.path.join(tmp, "smith2021")
            os.makedirs(folder)
            for name in ("source.tex", "source.txt"):
                with open(os.path.join(folder, name), "w") as handle:
                    handle.write("As in \\cite{smith2021}, accuracy is 0.732.\n")
            chapter = os.path.join(tmp, "chapter.tex")
            with open(chapter, "w") as handle:
                handle.write("In 2021 the accuracy was 0.732.\n")
            code, out, _ = run_main(chapter, "--source", folder, "--all")
        self.assertEqual(table_rows(out), [
            (1, "2021", "UNSUPPORTED"),
            (1, "0.732", os.path.join(folder, "source.tex") + ":1"),
        ])

    @unittest.skipUnless(HAVE_PDFTOTEXT, "pdftotext (Poppler) not installed")
    def test_pdf_source_is_converted_and_matches_name_the_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf = write_pdf(
                os.path.join(tmp, "paper.pdf"), [["A Synthetic Study"], [SAMPLE_LINE]]
            )
            chapter = os.path.join(tmp, "chapter.tex")
            with open(chapter, "w") as handle:
                handle.write("From 0.671 to 0.727 on 1,000 documents (12.5\\%); 0.732 is new.\n")
            code, out, _ = run_main(chapter, "--source", pdf, "--all")
        self.assertEqual(code, 1)
        found = pdf + ":2 (page 2)"
        self.assertEqual(
            table_rows(out),
            [(1, "0.671", found), (1, "0.727", found), (1, "1,000", found),
             (1, "12.5\\%", found), (1, "0.732", "UNSUPPORTED")],
        )

    def test_json_reports_counts_and_tokens(self):
        code, out, _ = run_main(CHAPTER, "--source", PAPER, "--json")
        self.assertEqual(code, 1)
        report = json.loads(out)
        self.assertEqual(
            (report["checked"], report["unsupported"], report["skipped"]), (7, 2, 2)
        )
        self.assertEqual(
            [(t["line"], t["token"], t["supported"]) for t in report["tokens"]],
            [(4, "0.056", False), (9, "0.732", False)],
        )
        code, out, _ = run_main(CHAPTER, "--source", PAPER, "--json", "--all")
        entry = [t for t in json.loads(out)["tokens"] if t["token"] == "90.50"][0]
        self.assertEqual(
            (entry["supported"], entry["value"], entry["source"], entry["source_line"],
             entry["source_page"]),
            (True, "90.5", PAPER, 3, None),
        )

    def test_exits_0_when_every_number_is_in_the_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            chapter = os.path.join(tmp, "chapter.tex")
            with open(chapter, "w") as handle:
                handle.write("From 0.671 to 0.727 on 1,000 documents (12.5\\%).\n")
            code, out, _ = run_main(chapter, "--source", PAPER)
        self.assertEqual(code, 0)
        self.assertEqual(table_rows(out), [])
        self.assertIn("4 tokens checked, 0 unsupported", out)

    def test_pipes_in_the_context_do_not_break_the_table(self):
        with tempfile.TemporaryDirectory() as tmp:
            chapter = os.path.join(tmp, "chapter.tex")
            with open(chapter, "w") as handle:
                handle.write("\\begin{tabular}{l|c}\nOurs | 0.732 | 0.723\n")
            code, out, _ = run_main(chapter, "--source", PAPER)
        self.assertEqual(code, 1)
        self.assertEqual(table_rows(out), [(2, "0.732", "UNSUPPORTED")])


class ErrorsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)

    def test_missing_or_unsupported_inputs_exit_2_with_a_message(self):
        docx = os.path.join(self.tmp, "notes.docx")
        with open(docx, "w") as handle:
            handle.write("0.732\n")
        cases = {
            "missing chapter": [os.path.join(self.tmp, "nope.tex"), "--source", PAPER],
            "missing source": [CHAPTER, "--source", os.path.join(self.tmp, "nope.txt")],
            "unsupported source type": [CHAPTER, "--source", docx],
        }
        for name, args in cases.items():
            with self.subTest(name):
                code, out, err = run_main(*args)
                self.assertEqual(code, 2)
                self.assertEqual(out, "")
                self.assertTrue(err.strip())

    @unittest.skipUnless(HAVE_PDFTOTEXT, "pdftotext (Poppler) not installed")
    def test_unreadable_pdf_source_exits_2(self):
        fake = os.path.join(self.tmp, "fake.pdf")
        with open(fake, "w") as handle:
            handle.write("not a PDF 0.732\n")
        code, out, err = run_main(CHAPTER, "--source", fake)
        self.assertEqual(code, 2)
        self.assertIn("pdftotext failed", err)

    def test_pdf_source_without_pdftotext_exits_2_with_install_hint(self):
        pdf = write_pdf(os.path.join(self.tmp, "paper.pdf"), [[SAMPLE_LINE]])
        empty_bin = os.path.join(self.tmp, "bin")
        os.mkdir(empty_bin)
        result = subprocess.run(
            [sys.executable, SCRIPT, CHAPTER, "--source", pdf],
            capture_output=True, text=True, env=dict(os.environ, PATH=empty_bin),
        )
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("pdftotext", result.stderr)
        self.assertIn("brew install poppler", result.stderr)
        self.assertIn("apt install poppler-utils", result.stderr)


if __name__ == "__main__":
    unittest.main()
