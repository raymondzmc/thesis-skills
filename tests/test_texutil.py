import json
import os
import subprocess
import sys
import unittest

TESTS = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(TESTS), "skills", "thesis-kit", "scripts")
FIXTURE = os.path.join(TESTS, "fixtures", "texutil", "sample.tex")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

import texutil  # noqa: E402


def run_cli(*args):
    return subprocess.run(
        [sys.executable, os.path.join(SCRIPTS, "texutil.py")] + list(args),
        capture_output=True, text=True)


class CliTest(unittest.TestCase):
    def test_sentences_as_json(self):
        result = run_cli(FIXTURE, "--sentences", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {
            "file": FIXTURE,
            "sentences": [
                {"line": 2, "text": "We study topic models."},
                {"line": 2, "text": "They are useful where X is fixed."},
                {"line": 9, "text": "Second paragraph."}]})

    def test_default_output_numbers_the_prose_lines(self):
        result = run_cli(FIXTURE)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("   7 | where X is fixed.", result.stdout)
        self.assertNotIn("citep", result.stdout)

    def test_missing_file_is_a_usage_error(self):
        result = run_cli(os.path.join(TESTS, "fixtures", "texutil", "nope.tex"))
        self.assertEqual(result.returncode, 2)
        self.assertIn("nope.tex", result.stderr)

    def test_help_exits_cleanly(self):
        result = run_cli("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("--sentences", result.stdout)


class StripCommentsTest(unittest.TestCase):
    def test_removes_comment_to_end_of_line_and_keeps_newline(self):
        self.assertEqual(texutil.strip_comments("keep % drop this\nnext"),
                         "keep \nnext")

    def test_escaped_percent_is_not_a_comment(self):
        self.assertEqual(texutil.strip_comments(r"50\% of runs % note"),
                         "50\\% of runs ")

    def test_percent_after_double_backslash_is_a_comment(self):
        self.assertEqual(texutil.strip_comments("end\\\\% note\nx"),
                         "end\\\\\nx")


class SentencesTest(unittest.TestCase):
    def test_splits_at_terminators_and_reports_start_lines(self):
        prose = "First one here. Second one\nfollows! Third?\nFourth starts here."
        self.assertEqual(texutil.sentences(prose), [
            (1, "First one here."), (1, "Second one follows!"),
            (2, "Third?"), (3, "Fourth starts here.")])

    def test_what_may_follow_a_sentence_end(self):
        prose = ('We saw it. and then more. 2 cases remain. "Quoted" text. '
                 'He said "stop." Then (see it.) Next.')
        self.assertEqual([s for _, s in texutil.sentences(prose)], [
            "We saw it. and then more.", "2 cases remain.", '"Quoted" text.',
            'He said "stop."', "Then (see it.)", "Next."])

    def test_empty_lines_split_but_blanked_lines_do_not(self):
        prose = "No period here\n\nNew paragraph text\n   \ncontinues here."
        self.assertEqual(texutil.sentences(prose), [
            (1, "No period here"),
            (3, "New paragraph text continues here.")])
        src = ("We define\n\\begin{equation}\nx = 1\n\\end{equation}\n"
               "where it holds.\n% aside\n\nNext paragraph")
        self.assertEqual(texutil.sentences(texutil.to_prose(src)), [
            (1, "We define where it holds."), (8, "Next paragraph")])

    def test_items_split_and_the_marker_is_dropped(self):
        prose = "Three points:\n\\item first one\n\\item\n  second one."
        self.assertEqual(texutil.sentences(prose), [
            (1, "Three points:"), (2, "first one"), (4, "second one.")])

    def test_fragments_without_words_are_skipped(self):
        self.assertEqual(texutil.sentences("First.\n\n .\n\n\\item\nSecond."),
                         [(1, "First."), (6, "Second.")])

    def test_no_space_is_left_before_closing_punctuation(self):
        prose = texutil.to_prose(r"Topic models~\citep{a}. They work (see~\cite{b}) , too.")
        self.assertEqual([s for _, s in texutil.sentences(prose)],
                         ["Topic models.", "They work (see), too."])

    def test_no_split_after_abbreviations(self):
        for abbr in ["e.g.", "i.e.", "et al.", "cf.", "vs.", "Fig.", "Figs.",
                     "Eq.", "Eqs.", "Sec.", "Tab.", "No.", "approx.", "resp.",
                     "(e.g.", "E.g.",
                     # a few more of the same kind
                     "Secs.", "Nos.", "viz.", "Ch.", "Eqn.", "Refs."]:
            with self.subTest(abbr=abbr):
                self.assertEqual(
                    len(texutil.sentences("See %s Two here. Next." % abbr)), 2)

    def test_etc_before_an_uppercase_word_ends_the_sentence(self):
        self.assertEqual(
            [s for _, s in texutil.sentences("Topics, words, etc. The rest.")],
            ["Topics, words, etc.", "The rest."])

    def test_no_split_inside_decimals(self):
        self.assertEqual(
            [s for _, s in texutil.sentences("It got 0.727 here. 3.5 later.")],
            ["It got 0.727 here.", "3.5 later."])


class ParagraphsTest(unittest.TestCase):
    def test_paragraphs_are_normalized_with_their_start_lines(self):
        prose = ("\n  First paragraph\nspans lines.\n\n   \n\n"
                 "Second \\item one \\item two\n\n    \nThird.\n")
        self.assertEqual(texutil.paragraphs(prose), [
            (2, "First paragraph spans lines."), (7, "Second one two"),
            (10, "Third.")])
        self.assertEqual(texutil.paragraphs("Cited work , here ."),
                         [(1, "Cited work, here.")])


class WordsTest(unittest.TestCase):
    def test_hyphenated_words_and_apostrophes_stay_whole(self):
        self.assertEqual(
            texutil.words("The pre-trained model's state-of-the-art "
                          "'quoted' `word' don't."),
            ["The", "pre-trained", "model's", "state-of-the-art", "quoted",
             "word", "don't"])

    def test_numbers_with_separators_are_one_word_and_x_counts(self):
        self.assertEqual(
            texutil.words("Set X to 0.727 on 1,000 runs, e.g. twice."),
            ["Set", "X", "to", "0.727", "on", "1,000", "runs", "e.g", "twice"])

    def test_commands_and_dashes_are_not_words(self):
        self.assertEqual(
            texutil.words("\\item Schrödinger -- naïve --- pages 1--5"),
            ["Schrödinger", "naïve", "pages", "1", "5"])


def prose_lines(src):
    """to_prose output split into lines, whitespace-normalized per line."""
    return [" ".join(line.split()) for line in texutil.to_prose(src).split("\n")]


class ToProseTest(unittest.TestCase):
    def test_comments_are_blanked_and_line_count_is_kept(self):
        src = "First line. % a remark\n% whole line\nThird line."
        out = texutil.to_prose(src)
        self.assertEqual(out.count("\n"), 2)
        self.assertEqual(prose_lines(src), ["First line.", "", "Third line."])

    def test_inline_math_becomes_x(self):
        self.assertEqual(prose_lines(r"We set $k = 5$ and \(\alpha_i\) here."),
                         ["We set X and X here."])

    def test_display_math_is_blanked(self):
        src = "Before\n$$ a + b $$\nmiddle \\[ x \\] end\n\\[\n  a = b\n\\]\nafter"
        self.assertEqual(prose_lines(src),
                         ["Before", "", "middle end", "", "", "", "after"])

    def test_display_math_environments_are_blanked(self):
        for env in ["equation", "equation*", "align", "align*", "gather",
                    "gather*", "multline", "eqnarray", "displaymath",
                    # common relatives
                    "multline*", "eqnarray*", "flalign", "flalign*",
                    "alignat", "alignat*"]:
            with self.subTest(env=env):
                src = "A \\begin{%s} x &= 1 \\\\ y \\end{%s} B" % (env, env)
                self.assertEqual(prose_lines(src), ["A B"])
        src = ("We minimise\n\\begin{equation}\n  L = \\sum_i x_i\n"
               "\\end{equation}\nwhere it holds.")
        self.assertEqual(prose_lines(src),
                         ["We minimise", "", "", "", "where it holds."])

    def test_non_prose_environments_are_blanked(self):
        for env in ["table", "table*", "tabular", "tabularx", "figure",
                    "figure*", "algorithm", "algorithmic", "lstlisting",
                    "verbatim", "minted", "tikzpicture",
                    # common relatives
                    "tabular*", "longtable", "wrapfigure", "wraptable",
                    "subfigure", "subtable", "sidewaystable",
                    "sidewaysfigure", "algorithm*", "thebibliography"]:
            with self.subTest(env=env):
                src = "A \\begin{%s}[h] Cell $x$ & y \\end{%s} B" % (env, env)
                self.assertEqual(prose_lines(src), ["A B"])

    def test_nested_environments_are_blanked_as_one_block(self):
        src = ("A\n\\begin{figure}\n\\begin{tabular}{ll}\nCell & b\n"
               "\\end{tabular}\n\\caption{Caption text.}\n\\end{figure}\nB")
        self.assertEqual(prose_lines(src), ["A", "", "", "", "", "", "", "B"])

    def test_percent_inside_verbatim_does_not_start_a_comment(self):
        src = "Run \\begin{verbatim}50% done\\end{verbatim} now.\nNext."
        self.assertEqual(prose_lines(src), ["Run now.", "Next."])

    def test_citation_commands_are_removed_with_their_arguments(self):
        names = ["cite", "citep", "citet", "citealp", "citeauthor",
                 "citeyear", "parencite", "textcite",
                 # other natbib/biblatex variants go the same way
                 "citealt", "Citet", "autocite"]
        for name in names:
            with self.subTest(name=name):
                self.assertEqual(prose_lines("A \\%s{key1,key2} B" % name),
                                 ["A B"])
                self.assertEqual(
                    prose_lines("A \\%s[see][p. 3]{key} B" % name), ["A B"])
        self.assertEqual(
            prose_lines(r"Models \cite{blei} are popular \citep[p. 3]{a}."),
            ["Models are popular ."])

    def test_argument_after_a_comment_line_still_belongs_to_the_command(self):
        self.assertEqual(prose_lines("A \\cite\n% note\n{key} text."),
                         ["A", "", "text."])
        self.assertEqual(prose_lines("A \\cite\n\n{key} text."),
                         ["A", "", "key text."])

    def test_reference_and_layout_commands_are_removed(self):
        names = ["ref", "autoref", "cref", "Cref", "eqref", "pageref",
                 "label", "url", "input", "include", "vspace", "vspace*",
                 "hspace", "hspace*", "bibliography", "bibliographystyle",
                 "includegraphics", "nameref"]
        for name in names:
            with self.subTest(name=name):
                self.assertEqual(prose_lines("A \\%s{x:y} B" % name), ["A B"])
        self.assertEqual(
            prose_lines(r"A \includegraphics[width=0.5\textwidth]{f.pdf} B"),
            ["A B"])

    def test_url_with_percent_is_removed(self):
        self.assertEqual(prose_lines(r"See \url{http://x.org/a%20b} now."),
                         ["See now."])

    def test_href_keeps_only_its_text(self):
        self.assertEqual(
            prose_lines(r"See \href{http://x.org/%7Eme}{the site} now."),
            ["See the site now."])

    def test_headings_are_blanked(self):
        for name in ["part", "chapter", "section", "subsection",
                     "subsubsection", "paragraph"]:
            for star in ["", "*"]:
                with self.subTest(name=name + star):
                    src = "\\%s%s[Short]{Long $x$ title}\nText." % (name, star)
                    self.assertEqual(prose_lines(src), ["", "Text."])
        self.assertEqual(prose_lines(r"\paragraph{Results.} We find it."),
                         ["We find it."])

    def test_text_style_commands_keep_content_and_other_commands_drop(self):
        for name in ["textit", "textbf", "emph", "textsc", "texttt",
                     "underline", "textrm", "mbox"]:
            with self.subTest(name=name):
                self.assertEqual(prose_lines("A \\%s{two words} B" % name),
                                 ["A two words B"])
        self.assertEqual(prose_lines(r"\emph{see \textbf{$x$} here}"),
                         ["see X here"])
        self.assertEqual(prose_lines(r"\textbf{pre}trained"), ["pretrained"])
        self.assertEqual(prose_lines("\\centering\\noindent Some text.\\newline"),
                         ["Some text."])

    def test_ties_quotes_and_escaped_symbols(self):
        self.assertEqual(
            prose_lines(r"Fig.~3 shows ``good'' results: 50\% of A \& B."),
            ['Fig. 3 shows "good" results: 50% of A & B.'])

    def test_other_control_symbols(self):
        src = ("Line\\\\[2pt] next, hy\\-phen, Schr\\\"odinger, caf\\'{e}, "
               "5\\,GB, i.e.\\@ fine, a\\_b \\#1")
        self.assertEqual(prose_lines(src), [
            "Line next, hyphen, Schrodinger, cafe, 5 GB, i.e. fine, a_b #1"])
        self.assertEqual(prose_lines("a\\\nb"), ["a", "b"])

    def test_only_source_blank_lines_become_empty_lines(self):
        src = ("First part\n% a comment line\n\\label{x}\n\\begin{equation}\n"
               "a=b\n\\end{equation}\ncontinues.\n   \nNew paragraph.")
        out = texutil.to_prose(src).split("\n")
        self.assertEqual([line == "" for line in out],
                         [False] * 7 + [True, False])
        self.assertEqual(out[0], "First part")
        self.assertEqual(out[8], "New paragraph.")

    def test_crlf_line_endings_are_normalized(self):
        self.assertEqual(texutil.to_prose("One. % c\r\n\r\nTwo.\r\n"),
                         "One.    \n\nTwo.\n")

    def test_other_environments_keep_content_and_items_stay_marked(self):
        src = ("Intro:\n\\begin{enumerate}[label=(\\alph*)]\n"
               "\\item First point.\n\\item[Speed:] Second point.\n"
               "\\end{enumerate}\n\\begin{minipage}[t]{0.5\\textwidth}"
               "Boxed.\\end{minipage}\n\\begin{abstract}After.\\end{abstract}")
        self.assertEqual(prose_lines(src), [
            "Intro:", "", "\\item First point.", "\\item Second point.", "",
            "Boxed.", "After."])

    def test_math_never_crosses_a_paragraph_break(self):
        src = "Costs 5$ only.\n\nNext has $x$ math."
        self.assertEqual(prose_lines(src),
                         ["Costs 5 only.", "", "Next has X math."])

    def test_comment_line_inside_math_is_not_a_paragraph_break(self):
        src = "Let $a +\n% note\nb$ hold."
        self.assertEqual(prose_lines(src), ["Let X", "", "hold."])

    def test_preamble_and_text_after_end_document_are_blanked(self):
        src = ("\\documentclass{book}\n\\usepackage[utf8]{inputenc}\n"
               "\\title{My Thesis}\n\\begin{document}\nBody text.\n"
               "\\end{document}\nTrailing notes.")
        self.assertEqual(prose_lines(src),
                         ["", "", "", "", "Body text.", "", ""])

    def test_footnote_text_is_kept_apart_from_the_sentence(self):
        self.assertEqual(
            prose_lines(r"It is popular.\footnote{See the survey.} They work."),
            ["It is popular. See the survey. They work."])

    def test_color_and_todo_arguments_are_not_prose(self):
        self.assertEqual(
            prose_lines(r"A \textcolor{red}{warm} \color{blue}B\todo[inline]{fix} C"),
            ["A warm B C"])

    def test_inline_verb_is_blanked(self):
        self.assertEqual(prose_lines(r"Pass \verb|--lr 5%| and \verb*+$x+ on."),
                         ["Pass and on."])

    def test_iffalse_block_is_blanked(self):
        src = ("Kept.\n\\iffalse\nOld text \\ifx\\a\\b same\\fi inside.\n"
               "\\fi\nAlso kept. \\ifthenelse{\\boolean{x}}{Yes}{No} done.")
        self.assertEqual(prose_lines(src), ["Kept.", "", "", "",
                                            "Also kept. YesNo done."])

    def test_comment_environment_is_blanked(self):
        src = "Kept.\n\\begin{comment}\nOld $ text\n\\end{comment}\nAlso kept."
        self.assertEqual(prose_lines(src), ["Kept.", "", "", "", "Also kept."])

    def test_unknown_command_drops_an_adjacent_optional_argument(self):
        self.assertEqual(
            prose_lines(r"A\linebreak[3] B \caption[Short]{Long text} [1] C"),
            ["A B Long text [1] C"])

    def test_definitions_are_removed(self):
        src = ("\\newcommand{\\R}{\\mathbb{R}}\\renewcommand\\arraystretch{1.2}"
               "\\providecommand{\\ours}[1][x]{Ours #1}"
               "\\setlength{\\tabcolsep}{4pt}Text.")
        self.assertEqual(prose_lines(src), ["Text."])

    def test_commands_that_print_text(self):
        self.assertEqual(
            prose_lines(r"We use \LaTeX{} and so on\ldots{} The end\dots"),
            ["We use LaTeX and so on... The end..."])

    def test_math_environment_is_inline_math(self):
        self.assertEqual(prose_lines(r"Take \begin{math}k\end{math} topics."),
                         ["Take X topics."])

    def test_escaped_dollar_is_not_math(self):
        self.assertEqual(prose_lines(r"It costs \$5 and $x$ more."),
                         ["It costs $5 and X more."])


if __name__ == "__main__":
    unittest.main()
