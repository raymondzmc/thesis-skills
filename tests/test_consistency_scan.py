import json
import os
import subprocess
import sys
import unittest

TESTS = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(TESTS), "skills", "thesis-kit", "scripts")
FIXTURES = os.path.join(TESTS, "fixtures", "consistency_scan")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

import consistency_scan as cs  # noqa: E402


VOCAB = ["word" + chr(97 + i // 26) + chr(97 + i % 26) for i in range(120)]


def para(words):
    return " ".join(words) + "."


class OverlapTest(unittest.TestCase):
    def test_overlapping_paragraphs_in_different_files(self):
        base = VOCAB[:40]
        docs = [
            ("a.tex", para(base)),
            ("b.tex", "\\section{Intro}\n" + para(base[:30] + VOCAB[40:50])),
            ("c.tex", para(base[:20] + VOCAB[50:70])),      # 15 of 35 shared
            ("d.tex", para(base[:20])),                      # under 30 words
        ]
        self.assertEqual(cs.check_overlap(docs), [
            {"a": "a.tex:1", "b": "b.tex:2", "overlap": 0.71, "shared": 25,
             "words": " ".join(base[:10])}])

    def test_paragraphs_in_the_same_file_are_not_compared(self):
        text = para(VOCAB[:40])
        self.assertEqual(cs.check_overlap([("a.tex", text + "\n\n" + text)]), [])

    def test_threshold_is_half_of_the_smaller_set(self):
        base = VOCAB[:40]                               # 35 shingles
        short = base[:32]                               # 27 shingles
        half = base[:19] + VOCAB[60:81]                 # 14 shared of 35
        docs = [("a.tex", para(base)), ("b.tex", para(short)),
                ("c.tex", para(half))]
        found = cs.check_overlap(docs)
        self.assertEqual([(f["a"], f["b"], f["shared"]) for f in found],
                         [("a.tex:1", "b.tex:1", 27),
                          ("b.tex:1", "c.tex:1", 14)])


class CitationTest(unittest.TestCase):
    def test_counts_and_bare_cites_when_natbib_is_used(self):
        docs = [("a.tex", "Shown \\citep{x} and \\citep[p.~3]{y}, \\citet{z} "
                          "says.\n% \\cite{commented}\nAlso \\citealp{w} and "
                          "\\citeauthor{v}."),
                ("b.tex", "Old style \\cite{k}.\nAgain \\cite[p.~2]{m} and "
                          "\\parencite{n} \\textcite{o}.")]
        self.assertEqual(cs.check_citations(docs), {
            "counts": {
                "a.tex": {"cite": 0, "citep": 2, "citet": 1, "citealp": 1,
                          "parencite": 0, "textcite": 0},
                "b.tex": {"cite": 2, "citep": 0, "citet": 0, "citealp": 0,
                          "parencite": 1, "textcite": 1}},
            "bare_cite": ["b.tex:1", "b.tex:2"]})

    def test_bare_cites_are_fine_without_citep_or_citet(self):
        result = cs.check_citations([("a.tex", "\\cite{a} and \\parencite{b}.")])
        self.assertEqual(result["bare_cite"], [])
        self.assertEqual(result["counts"]["a.tex"]["cite"], 1)


class AcronymTest(unittest.TestCase):
    def test_expansion_is_the_shortest_matching_run_of_preceding_words(self):
        cases = [
            ("we use a neural topic model", "NTM", "neural topic model"),
            ("with parameter-efficient fine-tuning", "PEFT",
             "parameter-efficient fine-tuning"),
            ("Recent Sparse Autoencoders", "SAEs", "Sparse Autoencoders"),
            ("a large language model", "LLM", "large language model"),
            ("Bidirectional Encoder Representations from Transformers",
             "BERT", "Bidirectional Encoder Representations from Transformers"),
            ("trained with Low-Rank Adaptation", "LoRA", "Low-Rank Adaptation"),
            ("We stop here. Neural topic model", "NTM", "Neural topic model"),
            ("Natural\n\ntopic model", "NTM", None),           # paragraph break
            ("Natural\n   \ntopic model", "NTM", "Natural topic model"),
            ("the results of the study", "NTM", None),
            ("alpha bravo charlie delta echo foxtrot golf hotel india",
             "ABCDEFGHI", None),
            ("alpha bravo charlie delta echo foxtrot golf hotel",
             "ABCDEFGH", "alpha bravo charlie delta echo foxtrot golf hotel"),
        ]
        for before, acronym, expected in cases:
            with self.subTest(acronym=acronym, before=before):
                self.assertEqual(cs.find_expansion(before, acronym), expected)

    def test_duplicates_in_a_file_and_differing_expansions_across_files(self):
        docs = [
            ("a.tex", "A neural topic model (NTM) is used.\n"
                      "We train Sparse Autoencoders (SAEs).\n"
                      "Again the neural topic model (NTM) here. See the "
                      "results (Table 3), (e.g.) and ($x$)."),
            ("b.tex", "Neural Topic Models (NTMs) are common.\n\n"
                      "Parameter-Efficient Fine-Tuning (PEFT) helps."),
            ("c.tex", "A noisy text miner (NTM) differs. Then\n\n"
                      "parameter efficient fine tuning (PEFT) agrees."),
        ]
        result = cs.check_acronyms(docs)
        self.assertEqual(result["duplicates"], [
            {"acronym": "NTM", "file": "a.tex", "lines": [1, 3]}])
        self.assertEqual(result["conflicts"], [
            {"acronym": "NTM", "expansions": [
                {"expansion": "neural topic model",
                 "locations": ["a.tex:1", "a.tex:3", "b.tex:1"]},
                {"expansion": "noisy text miner", "locations": ["c.tex:1"]}]}])

    def test_singular_forms_used_for_comparison(self):
        self.assertEqual(
            [cs.normalize_expansion(e) for e in [
                "Gaussian Processes", "Gaussian process", "Neural Topic Models",
                "ontologies", "analysis", "Parameter-Efficient Fine-Tuning"]],
            ["gaussian process", "gaussian process", "neural topic model",
             "ontology", "analysis", "parameter efficient fine tuning"])


class SpellingTest(unittest.TestCase):
    def test_pair_with_both_variants_lists_the_minority(self):
        docs = [("a.tex", "We model it. The modeling is hard.\nModeling helps."),
                ("b.tex", "Our modelling differs. % modelling\n\\label{modelling}")]
        result = cs.check_spelling(docs)
        self.assertEqual(result["pairs"], [
            {"pair": "modeling/modelling", "us": 2, "uk": 1, "minority": "uk",
             "minority_locations": [{"location": "b.tex:1",
                                     "word": "modelling"}]}])
        self.assertEqual((result["overall"]["us"], result["overall"]["uk"]),
                         (2, 1))
        self.assertEqual(result["overall"]["per_file"],
                         {"a.tex": {"us": 2, "uk": 0},
                          "b.tex": {"us": 0, "uk": 1}})

    def test_inflections_prefixes_and_ties(self):
        docs = [("a.tex", "Unlabeled data, optimizers and behavioral cues are "
                          "centered. Several analyses agree."),
                ("b.tex", "The unlabelled set; optimisers; behavioural shifts "
                          "are centred.\nWe analysed it.")]
        result = cs.check_spelling(docs)
        self.assertEqual(
            [(p["pair"], p["us"], p["uk"], p["minority"])
             for p in result["pairs"]],
            [("labeled/labelled", 1, 1, "us"),
             ("behavior/behaviour", 1, 1, "us"),
             ("center/centre", 1, 1, "us"),
             ("optimize/optimise", 1, 1, "us")])
        overall = result["overall"]
        self.assertEqual((overall["us"], overall["uk"], overall["minority"]),
                         (4, 5, "us"))
        self.assertEqual([x["word"] for x in overall["minority_locations"]],
                         ["Unlabeled", "behavioral", "centered", "optimizers"])

    def test_every_listed_pair_is_recognized(self):
        us = ("modeling modeled labeled labeling behavior color favor center "
              "analyze optimize optimization generalization normalize "
              "normalization regularization summarize summarization "
              "initialize utilize organize recognize characterize emphasize "
              "minimize maximize tokenize tokenization")
        uk = ("modelling modelled labelled labelling behaviour colour favour "
              "centre analyse optimise optimisation generalisation normalise "
              "normalisation regularisation summarise summarisation "
              "initialise utilise organise recognise characterise emphasise "
              "minimise maximise tokenise tokenisation")
        result = cs.check_spelling([("a.tex", us), ("b.tex", uk)])
        self.assertEqual(len(result["pairs"]), 27)
        self.assertTrue(all(p["us"] == 1 and p["uk"] == 1
                            for p in result["pairs"]))


THESIS = os.path.join(FIXTURES, "thesis")
CH1 = os.path.join(THESIS, "ch1.tex")
CH2 = os.path.join(THESIS, "parts", "ch2.tex")
CLEAN = os.path.join(FIXTURES, "clean")


def run_cli(*args):
    return subprocess.run(
        [sys.executable, os.path.join(SCRIPTS, "consistency_scan.py")]
        + list(args), capture_output=True, text=True)


class CliTest(unittest.TestCase):
    def test_json_is_keyed_by_check_and_findings_exit_1(self):
        result = run_cli(THESIS, "--json")
        self.assertEqual(result.returncode, 1, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(sorted(data), ["acronyms", "citations", "hyphenation",
                                        "overlap", "spelling"])
        self.assertEqual(sorted(data["citations"]["counts"]), [CH1, CH2])
        self.assertEqual(data["citations"]["bare_cite"], [CH2 + ":2"])
        self.assertEqual([g["group"] for g in data["hyphenation"]],
                         ["pre-trained/pretrained/pre trained"])
        self.assertEqual([p["pair"] for p in data["spelling"]["pairs"]],
                         ["modeling/modelling"])
        self.assertEqual([c["acronym"] for c in data["acronyms"]["conflicts"]],
                         ["NTM"])
        self.assertEqual([(o["a"], o["b"]) for o in data["overlap"]],
                         [(CH1 + ":5", CH2 + ":5")])

    def test_markdown_has_one_section_per_check(self):
        result = run_cli(CH1, CH2)
        self.assertEqual(result.returncode, 1, result.stderr)
        out = result.stdout
        for heading in ["## 1. Hyphenation and spacing variants",
                        "## 2. US/UK spelling", "## 3. Acronym definitions",
                        "## 4. Citation commands", "## 5. Verbatim overlap"]:
            self.assertIn(heading, out)
        self.assertIn(CH2 + ":2", out)
        self.assertIn("pretrained", out)
        self.assertIn("UK spellings (US and UK are tied): " + CH2 + ":3", out)

    def test_clean_files_exit_0_and_say_none(self):
        result = run_cli(CLEAN)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        sections = result.stdout.split("\n## ")[1:]
        self.assertEqual(len(sections), 5)
        for section in sections:
            self.assertIn("none", section)

    def test_usage_errors_exit_2(self):
        for args in [[os.path.join(FIXTURES, "missing.tex")],
                     [os.path.join(FIXTURES, "empty_dir")], []]:
            with self.subTest(args=args):
                result = run_cli(*args)
                self.assertEqual(result.returncode, 2)
                self.assertTrue(result.stderr.strip())

    def test_help(self):
        result = run_cli("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("--json", result.stdout)


class HyphenationTest(unittest.TestCase):
    def test_builtin_compound_in_several_forms(self):
        docs = [("a.tex", "We use a pre-trained model. The pretrained one is "
                          "big.\nPre-trained weights help. % pretrained\n"
                          "\\label{sec:pretrained} $pretrained$"),
                ("b.tex", "A pre\ntrained network. It is fine-tuned.")]
        self.assertEqual(cs.check_hyphenation(docs), [
            {"group": "pre-trained/pretrained/pre trained", "forms": [
                {"form": "pre-trained", "count": 2, "first": "a.tex:1"},
                {"form": "pretrained", "count": 1, "first": "a.tex:1"},
                {"form": "pre trained", "count": 1, "first": "b.tex:1"}]}])

    def test_plural_and_third_person_forms_count(self):
        docs = [("a.tex", "Two data sets and one Data set. It fine-tunes."),
                ("b.tex", "The datasets differ.\nIt finetunes co-occurrences "
                          "and cooccurrence.")]
        self.assertEqual(
            [(g["group"], [(f["form"], f["count"]) for f in g["forms"]])
             for g in cs.check_hyphenation(docs)],
            [("fine-tune/finetune", [("fine-tune", 1), ("finetune", 1)]),
             ("data set/dataset", [("data set", 2), ("dataset", 1)]),
             ("co-occurrence/cooccurrence",
              [("co-occurrence", 1), ("cooccurrence", 1)])])

    def test_any_hyphenated_word_whose_closed_form_also_occurs(self):
        docs = [("a.tex", "We apply re-ranking and Self-Attention. The x-axis, "
                          "co training and sub-words."),
                ("b.tex", "Then reranking helps; selfattention too.\nThe "
                          "xaxis, cotraining and subwords. Also pre-trained "
                          "and pretrained.")]
        self.assertEqual(cs.check_hyphenation(docs), [
            {"group": "pre-trained/pretrained/pre trained", "forms": [
                {"form": "pre-trained", "count": 1, "first": "b.tex:2"},
                {"form": "pretrained", "count": 1, "first": "b.tex:2"}]},
            {"group": "sub-word/subword", "forms": [
                {"form": "sub-word", "count": 1, "first": "a.tex:1"},
                {"form": "subword", "count": 1, "first": "b.tex:2"}]},
            {"group": "re-ranking/reranking", "forms": [
                {"form": "re-ranking", "count": 1, "first": "a.tex:1"},
                {"form": "reranking", "count": 1, "first": "b.tex:1"}]},
            {"group": "self-attention/selfattention", "forms": [
                {"form": "self-attention", "count": 1, "first": "a.tex:1"},
                {"form": "selfattention", "count": 1, "first": "b.tex:1"}]},
        ])


if __name__ == "__main__":
    unittest.main()
