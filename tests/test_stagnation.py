"""Tests for skills/thesis-kit/scripts/stagnation.py."""
import json
import os
import random
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCRIPTS = os.path.join(ROOT, "skills", "thesis-kit", "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

import stagnation  # noqa: E402

SCRIPT = os.path.join(SCRIPTS, "stagnation.py")
FIXTURES = os.path.join(HERE, "fixtures", "stagnation")
R1 = os.path.join(FIXTURES, "critique_r1.md")


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def squash(text):
    return " ".join(text.split())


class ParseTests(unittest.TestCase):
    def test_parses_each_finding_block_and_its_fields(self):
        parsed = stagnation.parse_critique(read(R1))
        self.assertEqual(parsed["errors"], [])
        findings = parsed["findings"]
        self.assertEqual(
            [(f["id"], f["lens"], f["severity"], f["scope"], f["line"])
             for f in findings],
            [("F1", "readability", "major", "local", 5),
             ("F2", "faithfulness", "major", "local", 13),
             ("F3", "mechanics", "minor", "local", 22),
             ("F4", "argument", "minor", "global", 31)])
        self.assertEqual(squash(findings[0]["original"]),
                         "The proposed sampler is considerably faster than the "
                         "baseline because it avoids recomputing the full "
                         "likelihood after every update of the widget counts.")
        self.assertEqual(findings[1]["original"],
                         "We evaluate on four synthetic corpora drawn from the "
                         "widget simulator.")
        self.assertEqual(findings[0]["location"], "chapters/ch3.tex:12")
        self.assertEqual([f["fix"] for f in findings][2:],
                         ["keep", "Qualify the claim to the settings that were "
                                  "tested."])
        self.assertEqual([f["rule"] for f in findings], ["new", "-", "G7", "G12"])


FINDING_DEFAULTS = (("Location", "ch.tex:1"),
                    ("Original", '"A quoted sentence from the chapter."'),
                    ("Fix", '"A better sentence."'),
                    ("Reasoning", "Because the paper says so."),
                    ("Rule", "-"))


def finding(header, drop=(), **fields):
    """A finding block (header, fields, blank line) with default fields."""
    values = dict(FINDING_DEFAULTS)
    values.update(fields)
    lines = [header] + ["- %s: %s" % (name, value)
                        for name, value in values.items() if name not in drop]
    return "\n".join(lines) + "\n\n"


def errors_of(text):
    return [(e["line"], e["finding"], e["kind"])
            for e in stagnation.parse_critique(text)["errors"]]


class QuoteTests(unittest.TestCase):
    def test_original_in_curly_quotes_is_unquoted(self):
        parsed = stagnation.parse_critique(finding(
            "### F1 | argument | minor | local",
            Original="“A curly quote.”"))
        self.assertEqual(parsed["findings"][0]["original"], "A curly quote.")

    def test_quoted_keep_counts_as_keep(self):
        parsed = stagnation.parse_critique(finding(
            "### F1 | argument | minor | local", Fix='"keep"'))
        out = stagnation.unchanged(parsed["findings"], "Some text.", "")
        self.assertEqual(out["skipped"], ["F1"])


class BlockBoundaryTests(unittest.TestCase):
    def test_quoted_original_may_span_a_blank_line(self):
        text = ("### F1 | readability | minor | local\n"
                "- Location: ch.tex:3\n"
                "- Original: \"The first paragraph ends here.\n"
                "\n"
                "The second paragraph starts here.\"\n"
                "- Fix: \"Join them.\"\n"
                "- Reasoning: One idea.\n"
                "- Rule: -\n")
        parsed = stagnation.parse_critique(text)
        self.assertEqual(parsed["errors"], [])
        self.assertEqual(squash(parsed["findings"][0]["original"]),
                         "The first paragraph ends here. The second paragraph "
                         "starts here.")

    def test_a_blank_line_between_fields_keeps_the_block_open(self):
        text = ("### F1 | readability | minor | local\n"
                "- Location: ch.tex:3\n"
                "- Original: \"One sentence.\"\n"
                "\n"
                "- Fix: \"Another sentence.\"\n"
                "- Reasoning: Clearer.\n"
                "- Rule: -\n")
        self.assertEqual(errors_of(text), [])

    def test_a_list_after_the_block_is_not_part_of_it(self):
        text = (finding("### F1 | readability | minor | local", Rule="G7")
                + "Summary of this round:\n- Rule: G7 was applied once.\n")
        text2 = (finding("### F1 | readability | minor | local", Rule="G7")
                 + "- Rule: G7 was applied once.\n")
        self.assertEqual(errors_of(text), [])
        self.assertEqual(errors_of(text2), [])


R2 = os.path.join(FIXTURES, "critique_r2.md")


def findings_of(path):
    return stagnation.parse_critique(read(path))["findings"]


class RecurringTests(unittest.TestCase):
    def test_overlapping_originals_are_paired_regardless_of_lens(self):
        pairs = stagnation.recurring(findings_of(R1), findings_of(R2))
        self.assertEqual(
            [(p["curr"], p["prev"], p["similarity"], p["contained"],
              p["prev_lens"], p["curr_lens"]) for p in pairs],
            # r2 F1 lies inside r1 F1 (5 of 20 words); r2 F3 shares 9 of
            # 11 words with r1 F4; r2 F2 repeats "the" so is not inside r1 F1.
            [("F1", "F1", 0.25, True, "readability", "argument"),
             ("F3", "F4", 0.818, False, "argument", "argument")])

    def test_threshold_limits_jaccard_pairs_but_not_containment(self):
        pairs = stagnation.recurring(findings_of(R1), findings_of(R2),
                                     threshold=0.9)
        self.assertEqual([(p["curr"], p["prev"]) for p in pairs], [("F1", "F1")])

    def test_quote_without_words_matches_nothing(self):
        prev = [{"id": "F1", "lens": "mechanics", "original": "$$"}]
        curr = [{"id": "F1", "lens": "mechanics", "original": "--"},
                {"id": "F2", "lens": "mechanics", "original": "Some words."}]
        self.assertEqual(stagnation.recurring(prev, curr), [])


BEFORE = ("\\section{Method}\n"
          "We describe the sampler used throughout this chapter.\n"
          "The proposed sampler is considerably faster than the baseline "
          "because it\n"
          "avoids recomputing the full likelihood after every update of the "
          "widget counts.\n"
          "We evaluate on four synthetic corpora drawn from the widget "
          "simulator.\n"
          "Gadgets are therefore always preferable to widgets in every "
          "setting.\n")
SPEED = ("The proposed sampler is considerably faster than the baseline "
         "because it avoids recomputing the full likelihood after every "
         "update of the widget counts.")
CORPORA = "We evaluate on four synthetic corpora drawn from the widget simulator."


def flagged(id_, original, fix='"A better sentence."', lens="readability"):
    return {"id": id_, "lens": lens, "original": original, "fix": fix}


class UnchangedTests(unittest.TestCase):
    def check(self, original, after, before=BEFORE, **kwargs):
        out = stagnation.unchanged([flagged("F1", original)], before, after,
                                   **kwargs)
        self.assertEqual(len(out["results"]), 1)
        return out["results"][0]

    def test_two_swapped_synonyms_count_as_unchanged(self):
        after = BEFORE.replace("considerably faster", "substantially quicker")
        result = self.check(SPEED, after)
        self.assertEqual((result["finding"], result["status"],
                          result["located"]), ("F1", "unchanged", "exact"))
        self.assertGreaterEqual(result["ratio"], 0.85)
        self.assertEqual(result["after"], squash(SPEED).replace(
            "considerably faster", "substantially quicker"))

    def test_genuine_rewrite_counts_as_rewritten(self):
        after = BEFORE.replace(SPEED.split(" because")[0] + " because it\n"
                               "avoids recomputing the full likelihood after "
                               "every update of the widget counts.",
                               "Skipping the full likelihood after each count "
                               "update is what lets the new sampler finish in "
                               "a third of the baseline's time.")
        self.assertNotIn("considerably", after)
        result = self.check(SPEED, after)
        self.assertEqual(result["status"], "rewritten")
        self.assertLess(result["ratio"], 0.85)

    def test_passage_with_no_similar_window_left_counts_as_removed(self):
        for after in ("\\section{Method}\n", ""):
            result = self.check(SPEED, after)
            self.assertEqual(result["status"], "removed", after)
            self.assertLess(result["ratio"], 0.3)

    def test_passage_moved_elsewhere_is_still_found(self):
        lines = BEFORE.splitlines(True)
        after = "".join(lines[:2] + lines[4:] + lines[2:4])  # to the end
        result = self.check(SPEED, after)
        self.assertEqual((result["status"], result["ratio"]), ("unchanged", 1.0))

    def test_original_absent_from_before_is_not_found(self):
        result = self.check("Nothing like this sentence was ever in the "
                            "chapter, not even close.", BEFORE)
        self.assertEqual((result["status"], result["located"]),
                         ("not-found", None))

    def test_quote_that_dropped_markup_is_located_fuzzily(self):
        before = BEFORE.replace("considerably", "\\emph{considerably}")
        result = self.check(SPEED, before, before=before)
        self.assertEqual((result["status"], result["located"], result["ratio"]),
                         ("unchanged", "fuzzy", 1.0))
        self.assertEqual(result["before"], squash(SPEED).replace(
            "considerably", "\\emph{considerably}"))
        self.assertTrue(0.7 <= result["locate_ratio"] < 1.0)


def pseudo_chapter(seed, words):
    """Deterministic gibberish: WORDS pseudo-words, ten to a sentence."""
    rng = random.Random(seed)
    syllables = ["ka", "lo", "mi", "ter", "san", "vu", "pel", "dor", "fi",
                 "gan", "ru", "bes", "tal", "no", "qui", "zen"]
    out = []
    for i in range(words):
        word = "".join(rng.choice(syllables)
                       for _ in range(rng.choice((2, 3))))
        out.append(word + ("." if i % 10 == 9 else ""))
    return out


class UnchangedScaleTests(unittest.TestCase):
    def test_long_chapter_with_twenty_findings_is_checked_quickly(self):
        words = pseudo_chapter(7, 10000)
        after = list(words)
        findings, expected = [], {}
        for k in range(20):
            start = 400 + k * 480
            findings.append(flagged("F%d" % (k + 1),
                                    " ".join(words[start:start + 25])))
            if k % 2 == 0:  # cosmetic: two words swapped for others
                after[start + 5] = "zenzen"
                after[start + 17] = "kaka"
                expected["F%d" % (k + 1)] = "unchanged"
            else:  # genuine rewrite of the whole passage
                after[start:start + 25] = pseudo_chapter(100 + k, 25)
        began = time.time()
        out = stagnation.unchanged(findings, " ".join(words), " ".join(after))
        elapsed = time.time() - began
        statuses = {r["finding"]: r["status"] for r in out["results"]}
        for fid, status in statuses.items():
            if fid in expected:
                self.assertEqual(status, "unchanged", fid)
            else:
                self.assertNotEqual(status, "unchanged", fid)
        self.assertLess(elapsed, 15.0)


class UnchangedSelectionTests(unittest.TestCase):
    def test_findings_whose_fix_is_keep_are_skipped(self):
        out = stagnation.unchanged(
            [flagged("F1", SPEED, fix="keep"), flagged("F2", CORPORA),
             flagged("F3", SPEED, fix="keep the claim but cite Table 2")],
            BEFORE, BEFORE)
        self.assertEqual(out["skipped"], ["F1"])
        self.assertEqual([(r["finding"], r["status"]) for r in out["results"]],
                         [("F2", "unchanged"), ("F3", "unchanged")])

    def test_old_wording_kept_in_a_comment_does_not_count(self):
        old_lines = ("The proposed sampler is considerably faster than the "
                     "baseline because it\navoids recomputing the full "
                     "likelihood after every update of the widget counts.\n")
        self.assertIn(old_lines, BEFORE)
        after = BEFORE.replace(old_lines, "% " + old_lines.replace(
            "\n", "\n% ", 1) + "Skipping the full likelihood after each "
            "count update is what lets the new sampler finish in a third of "
            "the baseline's time.\n")
        result = stagnation.unchanged([flagged("F1", SPEED)], BEFORE,
                                      after)["results"][0]
        self.assertEqual(result["status"], "rewritten")

    def test_original_found_only_in_a_comment_of_before_is_not_found(self):
        before = BEFORE + "% An old remark about the gadget simulator.\n"
        result = stagnation.unchanged(
            [flagged("F1", "An old remark about the gadget simulator.")],
            before, before)["results"][0]
        self.assertEqual(result["status"], "not-found")


BEFORE_TEX = os.path.join(FIXTURES, "before.tex")
AFTER_TEX = os.path.join(FIXTURES, "after.tex")


def run_cli(*args):
    return subprocess.run([sys.executable, SCRIPT] + list(args),
                          capture_output=True, text=True)


class CliCase(unittest.TestCase):
    def write(self, text, suffix=".md"):
        fd, path = tempfile.mkstemp(suffix=suffix)
        self.addCleanup(os.remove, path)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        return path


class ParseCliTests(CliCase):
    def test_valid_critique_exits_0_with_a_markdown_list(self):
        proc = run_cli("parse", R1)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertTrue(proc.stdout.startswith("# "), proc.stdout[:80])
        for needle in ("F1", "F4", "chapters/ch3.tex:12", "readability"):
            self.assertIn(needle, proc.stdout)

    def test_malformed_blocks_exit_1_with_their_line_numbers(self):
        path = self.write(finding("### F1 | clarity | major | local")
                          + finding("### F2 | argument | minor | local",
                                    drop=("Fix",)))
        proc = run_cli("parse", path)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("line 1 | F1 |", proc.stdout)
        self.assertIn("line 8 | F2 |", proc.stdout)

    def test_json_lists_findings_and_errors(self):
        proc = run_cli("parse", R1, "--json")
        self.assertEqual(proc.returncode, 0)
        data = json.loads(proc.stdout)
        self.assertEqual([f["id"] for f in data["findings"]],
                         ["F1", "F2", "F3", "F4"])
        self.assertEqual(data["errors"], [])


class RecurringCliTests(CliCase):
    def test_overlapping_findings_exit_1_and_are_listed_as_pairs(self):
        proc = run_cli("recurring", "--prev", R1, "--curr", R2, "--json")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        data = json.loads(proc.stdout)
        self.assertEqual([(p["curr"], p["prev"]) for p in data["pairs"]],
                         [("F1", "F1"), ("F3", "F4")])

    def test_threshold_option_is_used(self):
        proc = run_cli("recurring", "--prev", R1, "--curr", R2,
                       "--threshold", "0.9", "--json")
        self.assertEqual([(p["curr"], p["prev"])
                          for p in json.loads(proc.stdout)["pairs"]],
                         [("F1", "F1")])

    def test_no_overlap_exits_0(self):
        curr = self.write(finding("### F1 | mechanics | minor | local",
                                  Original='"An unrelated sentence entirely."'))
        proc = run_cli("recurring", "--prev", R1, "--curr", curr)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_malformed_blocks_are_still_compared_and_noted(self):
        curr = self.write(finding(
            "### F1 | clarity | minor | global",  # unknown lens
            Original='"Gadgets are therefore always preferable to widgets in '
                     'every setting."'))
        proc = run_cli("recurring", "--prev", R1, "--curr", curr)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("previous F4", proc.stdout)
        self.assertIn("1 format error", proc.stdout)

    def test_markdown_names_both_findings_their_lenses_and_similarity(self):
        proc = run_cli("recurring", "--prev", R1, "--curr", R2)
        self.assertEqual(proc.returncode, 1)
        for needle in ("F3", "F4", "0.818", "argument", "readability"):
            self.assertIn(needle, proc.stdout)


class UnchangedCliTests(CliCase):
    ARGS = ("unchanged", "--critique", R1, "--before", BEFORE_TEX,
            "--after", AFTER_TEX)

    def test_a_fix_that_did_not_take_exits_1(self):
        proc = run_cli(*self.ARGS + ("--json",))
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        data = json.loads(proc.stdout)
        self.assertEqual([(r["finding"], r["status"]) for r in data["results"]],
                         [("F1", "unchanged"), ("F2", "rewritten"),
                          ("F4", "rewritten")])
        self.assertEqual(data["skipped"], ["F3"])

    def test_threshold_option_is_used(self):
        # F1 scores about 0.91 after its two synonym swaps.
        proc = run_cli(*self.ARGS + ("--threshold", "0.95", "--json"))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["results"][0]["status"],
                         "rewritten")

    def test_markdown_shows_each_status_with_both_passages(self):
        proc = run_cli(*self.ARGS)
        self.assertEqual(proc.returncode, 1)
        for needle in ("F1", "unchanged", "F2", "rewritten", "F3", "keep",
                       "substantially quicker", "considerably faster"):
            self.assertIn(needle, proc.stdout)


class UsageCliTests(CliCase):
    def test_missing_files_are_usage_errors(self):
        missing = os.path.join(FIXTURES, "no-such-file.md")
        for args in (("parse", missing),
                     ("recurring", "--prev", R1, "--curr", missing),
                     ("unchanged", "--critique", R1, "--before", missing,
                      "--after", AFTER_TEX)):
            proc = run_cli(*args)
            self.assertEqual(proc.returncode, 2, args)
            self.assertIn("no-such-file.md", proc.stderr)
            self.assertNotIn("Traceback", proc.stderr)

    def test_missing_subcommand_is_a_usage_error(self):
        proc = run_cli()
        self.assertEqual(proc.returncode, 2)
        self.assertNotIn("Traceback", proc.stderr)


class MalformedTests(unittest.TestCase):
    def test_malformed_headers_are_errors_with_line_numbers(self):
        text = (finding("### F1 | readability | major")
                + finding("## F2 | readability | major | local")
                + finding("### F3 | clarity | major | local")
                + finding("### F4 | mechanics | blocker | local")
                + finding("### F5 | mechanics | minor | everywhere")
                + finding("### F6 | mechanics | minor | local"))
        self.assertEqual(errors_of(text), [(1, "F1", "header"),
                                           (8, "F2", "header"),
                                           (15, "F3", "lens"),
                                           (22, "F4", "severity"),
                                           (29, "F5", "scope")])

    def test_missing_or_empty_fields_are_errors(self):
        text = (finding("### F1 | argument | minor | local", drop=("Fix",))
                + finding("### F2 | argument | minor | local", Reasoning=""))
        self.assertEqual(errors_of(text), [(1, "F1", "missing-field"),
                                           (11, "F2", "empty-field")])

    def test_rule_must_be_a_rule_id_new_or_dash(self):
        text = (finding("### F1 | argument | minor | local", Rule="G7")
                + finding("### F2 | argument | minor | local", Rule="new")
                + finding("### F3 | argument | minor | local", Rule="G7, G8")
                + finding("### F4 | argument | minor | local", Rule="none"))
        self.assertEqual(errors_of(text), [(20, "F3", "rule"),
                                           (27, "F4", "rule")])

    def test_repeated_finding_id_is_an_error_at_the_later_block(self):
        text = (finding("### F1 | argument | minor | local")
                + finding("### F1 | mechanics | minor | local"))
        self.assertEqual(errors_of(text), [(8, "F1", "duplicate-id")])

    def test_unknown_and_repeated_fields_are_errors(self):
        text = ("### F1 | argument | minor | local\n"
                "- Location: ch.tex:1\n"
                "- Original: \"A quoted sentence.\"\n"
                "- Severity: major\n"
                "- Fix: \"Better.\"\n"
                "- Reasoning: Because.\n"
                "- Rule: -\n"
                "- Fix: \"Second fix.\"\n")
        self.assertEqual(errors_of(text), [(4, "F1", "unknown-field"),
                                           (8, "F1", "duplicate-field")])
        self.assertEqual(stagnation.parse_critique(text)["findings"][0]["fix"],
                         "Better.")

    def test_errors_are_listed_in_line_order(self):
        text = finding("### F1 | clarity | minor | local", Note="extra")
        self.assertEqual(errors_of(text), [(1, "F1", "lens"),
                                           (7, "F1", "unknown-field")])


if __name__ == "__main__":
    unittest.main()
