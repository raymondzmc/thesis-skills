import json
import os
import subprocess
import sys
import unittest

TESTS = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(TESTS), "skills", "thesis-kit", "scripts")
FIXTURES = os.path.join(TESTS, "fixtures", "prose_metrics")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

import prose_metrics  # noqa: E402


def sentence_of(n, word="word"):
    """A sentence of exactly n words, capitalized, ending with a period."""
    return " ".join(["Alpha"] + [word] * (n - 1)) + "."


ALPHA = os.path.join(FIXTURES, "ch_alpha.tex")
BETA = os.path.join(FIXTURES, "ch_beta.tex")


def run_cli(*args):
    return subprocess.run(
        [sys.executable, os.path.join(SCRIPTS, "prose_metrics.py")] + list(args),
        capture_output=True, text=True)


class CliTest(unittest.TestCase):
    def test_json_report(self):
        result = run_cli(ALPHA, BETA, "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        alpha, beta = data["files"]
        self.assertEqual((alpha["file"], beta["file"]), (ALPHA, BETA))
        self.assertEqual(alpha["sentences"], 5)
        self.assertEqual(alpha["openers"], [
            {"opener": "we propose", "count": 3, "lines": [2, 3]}])
        self.assertEqual(alpha["chapter_openers"], {"count": 1, "lines": [2]})
        self.assertEqual(beta["chapter_openers"], {"count": 1, "lines": [2]})
        self.assertEqual(alpha["banned"]["em_dash"], {"count": 1, "lines": [3]})
        self.assertEqual(alpha["banned"]["semicolon"], {"count": 1, "lines": [3]})
        self.assertEqual([h["term"] for h in alpha["lexicon"]], ["robust"])
        self.assertEqual([h["term"] for h in beta["lexicon"]],
                         ["it is worth noting"])
        self.assertEqual([(g["ngram"], g["files"]) for g in data["ngrams"]], [
            ("encoder learns coherent themes from", 2),
            ("sparse topic encoder learns coherent", 2),
            ("the sparse topic encoder learns", 2),
            ("topic encoder learns coherent themes", 2)])
        self.assertEqual(data["ngrams"][0]["locations"],
                         [ALPHA + ":4", BETA + ":2"])

    def test_options_reach_the_measurements(self):
        result = run_cli(ALPHA, BETA, "--json", "--long", "8", "--openers", "2",
                         "--ngram", "4", "--min-files", "1")
        data = json.loads(result.stdout)
        alpha = data["files"][0]
        self.assertEqual([s["line"] for s in alpha["long_sentences"]], [4])
        self.assertEqual(data["settings"], {
            "long": 8, "openers": 2, "ngram": 4, "min_files": 1,
            "lexicon": "built-in"})
        self.assertTrue(all(len(g["ngram"].split()) == 4
                            for g in data["ngrams"]))
        self.assertIn(1, [g["files"] for g in data["ngrams"]])

    def test_markdown_report(self):
        result = run_cli(ALPHA, BETA)
        self.assertEqual(result.returncode, 0, result.stderr)
        out = result.stdout
        self.assertIn("## " + ALPHA, out)
        self.assertIn("## " + BETA, out)
        self.assertIn("| we propose | 3 | 2, 3 |", out)
        self.assertIn("| em-dash (---) | 1 | 3 |", out)
        self.assertIn("| sparse topic encoder learns coherent | 2 | 2 |", out)
        self.assertIn('"This chapter": 1 (line 2)', out)

    def test_markdown_marks_only_truncated_sentence_starts(self):
        out = run_cli(ALPHA, BETA, "--long", "8").stdout
        self.assertIn("| 4 | 10 | The sparse topic encoder learns coherent "
                      "themes from noisy text |", out)
        self.assertIn("| 2 | 12 | The sparse topic encoder learns coherent "
                      "themes from short posts as well |", out)
        out = run_cli(ALPHA, "--long", "4").stdout
        self.assertIn("| 4 | 10 | The sparse topic encoder learns coherent "
                      "themes from noisy text |", out)

    def test_custom_lexicon_option(self):
        lexicon = os.path.join(FIXTURES, "custom_lexicon.txt")
        data = json.loads(run_cli(ALPHA, "--json", "--lexicon", lexicon).stdout)
        self.assertEqual(data["files"][0]["lexicon"], [])
        self.assertEqual(data["settings"]["lexicon"], lexicon)

    def test_usage_errors_exit_2(self):
        missing = os.path.join(FIXTURES, "missing.tex")
        for args in [[missing], [ALPHA, "--lexicon", missing],
                     [ALPHA, "--lexicon",
                      os.path.join(FIXTURES, "bad_regex_lexicon.txt")],
                     [ALPHA, "--ngram", "0"], [], [FIXTURES]]:
            with self.subTest(args=args):
                result = run_cli(*args)
                self.assertEqual(result.returncode, 2)
                self.assertTrue(result.stderr.strip())

    def test_help(self):
        result = run_cli("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("--min-files", result.stdout)


class BannedPatternsTest(unittest.TestCase):
    def test_em_dashes_in_source_outside_comments_and_table_cells(self):
        source = ("Models---like LDA---work.\n"
                  "Here \u2014 a typed one.\n"
                  "% a comment --- ignored\n"
                  "\\begin{tabular}{ll} a & --- \\\\ \\end{tabular}\n"
                  "\\caption{A caption---with a dash.}")
        report = prose_metrics.analyze_file(source)
        self.assertEqual(report["banned"]["em_dash"],
                         {"count": 4, "lines": [1, 2, 5]})

    def test_spaced_en_dashes_between_words(self):
        source = ("Topic models -- which are old -- still work.\n"
                  "Pages 1--5 and 1990--2000.\n"
                  "A~--~B and C – D.\n"
                  "An em --- dash is not one.\n"
                  "% a -- comment\n")
        report = prose_metrics.analyze_file(source)
        self.assertEqual(report["banned"]["spaced_en_dash"],
                         {"count": 4, "lines": [1, 3]})

    def test_semicolons_in_prose_only(self):
        source = ("One; two.\n$a; b$ and \\[x;y\\] here.\n% c; d\n"
                  "\\begin{align} a;b \\end{align}\nThree; four; five.")
        report = prose_metrics.analyze_file(source)
        self.assertEqual(report["banned"]["semicolon"],
                         {"count": 3, "lines": [1, 5]})


class LexiconTest(unittest.TestCase):
    def test_default_lexicon_whole_words_and_phrases(self):
        source = ("We delve into a Crucial, robust, crucial and comprehensive "
                  "landscape.\nIt is worth noting that, in order\n"
                  "to leverage it, we utilize X.\n"
                  "Robustness and crucially are fine. This not only helps "
                  "but also hurts.\n% moreover in a comment\n"
                  "\\label{sec:robust} $robust$")
        hits = prose_metrics.analyze_file(source)["lexicon"]
        self.assertEqual({h["term"]: (h["count"], h["lines"]) for h in hits}, {
            "delve": (1, [1]), "crucial": (2, [1]), "robust": (1, [1]),
            "comprehensive": (1, [1]), "landscape": (1, [1]),
            "it is worth noting": (1, [2]), "in order to": (1, [2]),
            "leverage": (1, [3]), "utilize": (1, [3]),
            r"re:not only\b.{1,80}?\bbut also": (1, [4])})
        self.assertEqual(hits[0]["term"], "crucial")

    def test_lexicon_file_replaces_the_default_list(self):
        entries = prose_metrics.load_lexicon(
            os.path.join(FIXTURES, "custom_lexicon.txt"))
        self.assertEqual(entries, ["hence", r"re:\bas such\b", "in a nutshell"])
        hits = prose_metrics.analyze_file(
            "Hence, as such, in a\nnutshell we delve.",
            lexicon=prose_metrics.compile_lexicon(entries))["lexicon"]
        self.assertEqual([(h["term"], h["count"]) for h in hits], [
            ("hence", 1), (r"re:\bas such\b", 1), ("in a nutshell", 1)])


class NgramTest(unittest.TestCase):
    def test_ngrams_shared_by_files_with_one_location_each(self):
        docs = [
            ("a.tex", "Our sparse topic encoder learns coherent themes fast."),
            ("b.tex", "Intro line.\nThe sparse topic encoder learns "
                      "coherent themes too."),
            ("c.tex", "Nothing in common appears in this file at all."),
        ]
        self.assertEqual(prose_metrics.repeated_ngrams(docs, n=5), [
            {"ngram": "sparse topic encoder learns coherent", "files": 2,
             "count": 2, "locations": ["a.tex:1", "b.tex:2"]},
            {"ngram": "topic encoder learns coherent themes", "files": 2,
             "count": 2, "locations": ["a.tex:1", "b.tex:2"]},
        ])


    def test_placeholder_digit_and_stopword_ngrams_are_ignored(self):
        text = ("Alpha $k$ beta gamma delta epsilon. "
                "Run 5 seeds over many trials. "
                "It is one of the best. "
                "Sparse coding finds stable latent features.")
        docs = [("a.tex", text), ("b.tex", text)]
        self.assertEqual(
            [g["ngram"] for g in prose_metrics.repeated_ngrams(docs, n=5)],
            ["coding finds stable latent features",
             "sparse coding finds stable latent"])

    def test_sorting_min_files_and_top(self):
        common = "Latent topics drift across noisy corpora."
        docs = [("a.tex", common + " Shared phrase grows longer here now."),
                ("b.tex", common + " Shared phrase grows longer here now.\n"
                          "Again shared phrase grows longer here."),
                ("c.tex", common)]
        grams = prose_metrics.repeated_ngrams(docs, n=5)
        self.assertEqual([(g["ngram"], g["files"], g["count"]) for g in grams], [
            ("latent topics drift across noisy", 3, 3),
            ("topics drift across noisy corpora", 3, 3),
            ("shared phrase grows longer here", 2, 3),
            ("phrase grows longer here now", 2, 2),
        ])
        self.assertEqual(grams[2]["locations"], ["a.tex:1", "b.tex:1"])
        self.assertEqual(len(prose_metrics.repeated_ngrams(docs, n=5, top=1)), 1)
        self.assertEqual(
            [g["files"] for g in prose_metrics.repeated_ngrams(
                docs, n=5, min_files=3)], [3, 3])


class SentenceStatsTest(unittest.TestCase):
    def test_counts_mean_median_and_90th_percentile(self):
        source = " ".join(sentence_of(n) for n in range(1, 11))
        report = prose_metrics.analyze_file(source)
        self.assertEqual(report["sentences"], 10)
        self.assertEqual(report["words"], 55)
        self.assertEqual(report["mean"], 5.5)
        self.assertEqual(report["median"], 5.5)
        self.assertEqual(report["p90"], 9)

    def test_long_sentences_report_line_length_and_first_twelve_words(self):
        numbered = " ".join(["Alpha"] + ["b%d" % i for i in range(2, 15)]) + "."
        source = "Short one here.\n%s\n%s %s" % (
            numbered, sentence_of(13), sentence_of(12))
        report = prose_metrics.analyze_file(source, long_words=12)
        self.assertEqual(report["long_sentences"], [
            {"line": 2, "words": 14,
             "start": "Alpha b2 b3 b4 b5 b6 b7 b8 b9 b10 b11 b12"},
            {"line": 3, "words": 13, "start": " ".join(["Alpha"] + ["word"] * 11)},
        ])

    def test_repeated_openers_and_chapter_openers(self):
        source = ("We propose a model. We propose a loss.\n"
                  "We propose a metric. We show results.\n"
                  "In this chapter, we study it. This chapter ends. "
                  "In this work, we go.\nThis chapter is short.")
        report = prose_metrics.analyze_file(source, opener_min=3)
        self.assertEqual(report["openers"], [
            {"opener": "we propose", "count": 3, "lines": [1, 2]}])
        self.assertEqual(report["chapter_openers"],
                         {"count": 3, "lines": [3, 4]})
        report = prose_metrics.analyze_file(source, opener_min=2)
        self.assertEqual([(o["opener"], o["count"]) for o in report["openers"]],
                         [("we propose", 3), ("in this", 2),
                          ("this chapter", 2)])

    def test_empty_file_has_zero_stats(self):
        report = prose_metrics.analyze_file("% only a comment\n")
        self.assertEqual((report["sentences"], report["words"], report["mean"],
                          report["median"], report["p90"]), (0, 0, 0, 0, 0))


if __name__ == "__main__":
    unittest.main()
