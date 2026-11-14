"""Tests for skills/thesis-kit/scripts/rules_lint.py."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCRIPTS = os.path.join(ROOT, "skills", "thesis-kit", "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

import rules_lint  # noqa: E402

SCRIPT = os.path.join(SCRIPTS, "rules_lint.py")
FIXTURES = os.path.join(HERE, "fixtures", "rules_lint")
RULES = os.path.join(FIXTURES, "rules.md")
CHAPTER = os.path.join(FIXTURES, "chapter.tex")


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


class ParseTests(unittest.TestCase):
    def test_valid_file_parses_into_rules_without_errors(self):
        report = rules_lint.lint(read(RULES))
        self.assertEqual(report["errors"], [])
        self.assertEqual(
            [(r["id"], r["category"], r["status"], r["line"])
             for r in report["rules"]],
            [("G7", "notation", "active", 8),
             ("G8", "terminology", "active", 16),
             ("G9", "style", "retired", 22)])
        self.assertEqual(report["rules"][0]["fields"]["Check"],
                         "regex:`topic distribution \\$\\\\alpha\\$`")


DEFAULT_FIELDS = (("Rule", "Use the active voice in method sections."),
                  ("Why", "Readers follow who did what."),
                  ("Check", "read"),
                  ("Origin", "paper1 r1 F1"))


def block(header, drop=(), **fields):
    """A rule block (header, fields, blank line); DEFAULT_FIELDS fill in the
    fields not given, and DROP removes some."""
    values = dict(DEFAULT_FIELDS)
    values.update(fields)
    lines = [header] + ["- %s: %s" % (name, value)
                        for name, value in values.items() if name not in drop]
    return "\n".join(lines) + "\n\n"


def errors_of(text, **kwargs):
    return [(e["line"], e["rule"], e["kind"])
            for e in rules_lint.lint(text, **kwargs)["errors"]]


class FieldTests(unittest.TestCase):
    def test_missing_or_empty_required_fields_are_errors(self):
        report = rules_lint.lint("## G1 | style\n"
                                 "- Rule: Use the active voice.\n"
                                 "- Why:\n"
                                 "- Check: read\n")
        self.assertEqual(
            [(e["line"], e["rule"], e["kind"], e["field"])
             for e in report["errors"]],
            [(1, "G1", "missing-field", "Origin"),
             (3, "G1", "empty-field", "Why")])


class FieldNameTests(unittest.TestCase):
    def test_unknown_and_repeated_fields_are_errors(self):
        report = rules_lint.lint("## G1 | style\n"
                                 "- Rule: Use the active voice.\n"
                                 "- Why: Readers follow it.\n"
                                 "- Check: read\n"
                                 "- Origin: paper1 r1 F1\n"
                                 "- Stauts: retired\n"
                                 "- Rule: Say it twice.\n")
        self.assertEqual([(e["line"], e["rule"], e["kind"])
                          for e in report["errors"]],
                         [(6, "G1", "unknown-field"),
                          (7, "G1", "duplicate-field")])
        self.assertEqual(report["rules"][0]["fields"]["Rule"],
                         "Use the active voice.")
        self.assertEqual(report["rules"][0]["status"], "active")

    def test_indented_lines_continue_the_previous_field(self):
        report = rules_lint.lint("## G1 | style\n"
                                 "- Rule: Use the active voice\n"
                                 "  in method sections.\n"
                                 "- Why: Readers follow it.\n"
                                 "- Check: read\n"
                                 "- Origin: paper1 r1 F1\n")
        self.assertEqual(report["errors"], [])
        self.assertEqual(report["rules"][0]["fields"]["Rule"],
                         "Use the active voice in method sections.")

    def test_unindented_text_inside_a_block_is_an_error(self):
        text = ("Intro text before any rule is fine.\n"
                "## G1 | style\n"
                "- Rule: Use the active voice.\n"
                "A stray sentence.\n"
                "- Why: Readers follow it.\n"
                "- Check: read\n"
                "- Origin: paper1 r1 F1\n"
                "\n"
                "## Notes\n"
                "Text under another heading is fine.\n")
        self.assertEqual(errors_of(text), [(4, "G1", "unexpected-text")])


class CheckFieldTests(unittest.TestCase):
    def test_check_must_be_backticked_regex_script_or_read(self):
        text = (block("## G1 | style", Check="regex:`\\bvery\\b`")
                + block("## G2 | style", Check="script:latex_check")
                + block("## G3 | style", Check="regex:very")
                + block("## G4 | style", Check="grep:very")
                + block("## G5 | style", Check="script:"))
        self.assertEqual(errors_of(text), [(16, "G3", "check"),
                                           (22, "G4", "check"),
                                           (28, "G5", "check")])

    def test_regex_that_does_not_compile_is_an_error(self):
        report = rules_lint.lint(block("## G1 | style",
                                       Check="regex:`topic (distribution`"))
        self.assertEqual([(e["line"], e["rule"], e["kind"])
                          for e in report["errors"]], [(4, "G1", "regex")])
        self.assertIn("missing )", report["errors"][0]["message"])


class BudgetTests(unittest.TestCase):
    TEXT = (block("## G1 | style", Rule="Spell out numbers below ten.")
            + block("## G2 | notation", Rule="Bold lowercase for vectors.")
            + block("## G3 | other", Rule="Retired rules do not count.",
                    Status="retired"))

    def test_active_rules_within_the_budget_are_fine(self):
        self.assertEqual(errors_of(self.TEXT, max_active=2), [])

    def test_more_active_rules_than_the_budget_is_an_error(self):
        report = rules_lint.lint(self.TEXT, max_active=1)
        self.assertEqual([(e["rule"], e["kind"]) for e in report["errors"]],
                         [(None, "budget")])
        self.assertIn("over budget: merge or retire rules",
                      report["errors"][0]["message"])


class NearDuplicateTests(unittest.TestCase):
    def test_similar_active_rules_are_reported_as_pairs(self):
        text = (block("## G1 | notation", Rule="Write the topic distribution "
                      "as $\\theta$ in every chapter.")
                + block("## G2 | notation", Rule="Write the topic "
                        "distribution as $\\theta$ in each chapter.")
                + block("## G3 | style", Rule="Spell out numbers below ten.")
                + block("## G4 | notation", Rule="Write the topic "
                        "distribution as $\\theta$ in all chapters.",
                        Status="retired"))
        pairs = rules_lint.lint(text)["near_duplicates"]
        self.assertEqual([(p["a"], p["b"]) for p in pairs], [("G1", "G2")])
        self.assertAlmostEqual(pairs[0]["similarity"], 0.8)  # 8 of 10 words

    def test_similarity_of_exactly_the_threshold_counts(self):
        text = (block("## G1 | style", Rule="Alpha beta gamma delta.")
                + block("## G2 | style", Rule="Alpha beta gamma epsilon.")
                + block("## G3 | style", Rule="Alpha beta zeta eta."))
        pairs = rules_lint.lint(text)["near_duplicates"]
        self.assertEqual([(p["a"], p["b"], p["similarity"]) for p in pairs],
                         [("G1", "G2", 0.6)])  # 3 shared of 5 words


class ApplyTests(unittest.TestCase):
    def test_active_regex_rules_hit_comment_stripped_chapter_text(self):
        rules = rules_lint.lint(read(RULES))["rules"]
        hits = rules_lint.apply_rules(rules, [(CHAPTER, read(CHAPTER))])
        # G9 (retired) would match line 2 and line 3 is a comment.
        self.assertEqual(
            [(h["file"], h["line"], h["rule"], h["match"]) for h in hits],
            [(CHAPTER, 2, "G7", "topic distribution $\\alpha$")])

    def test_escaped_percent_does_not_hide_text_from_the_checks(self):
        rules = rules_lint.lint(read(RULES))["rules"]
        hits = rules_lint.apply_rules(rules, [(
            "ch.tex", "In 50\\% of cases the topic distribution $\\alpha$ "
                      "varies.\n")])
        self.assertEqual([(h["line"], h["rule"]) for h in hits], [(1, "G7")])

    def test_empty_matches_are_not_hits(self):
        rules = rules_lint.lint(block("## G1 | style",
                                      Check="regex:`(very)?`"))["rules"]
        hits = rules_lint.apply_rules(rules, [("a.tex", "a very long day\n")])
        self.assertEqual([(h["line"], h["match"]) for h in hits], [(1, "very")])

    def test_hits_are_listed_in_line_order_within_each_file(self):
        rules = rules_lint.lint(
            block("## G1 | style", Check="regex:`\\bthird\\b`")
            + block("## G2 | style", Check="regex:`\\bfirst\\b`"))["rules"]
        hits = rules_lint.apply_rules(rules, [
            ("b.tex", "first\nsecond\nthird\n"), ("a.tex", "third\n")])
        self.assertEqual([(h["file"], h["line"], h["rule"]) for h in hits],
                         [("b.tex", 1, "G2"), ("b.tex", 3, "G1"),
                          ("a.tex", 1, "G1")])


class NextIdTests(unittest.TestCase):
    def test_next_id_follows_the_highest_number_including_retired(self):
        # The fixture uses G7..G9 (G9 retired); G1..G6 are never reused.
        self.assertEqual(rules_lint.next_id(rules_lint.parse_rules(read(RULES))),
                         "G10")

    def test_next_id_without_rules_is_g1(self):
        self.assertEqual(rules_lint.next_id(rules_lint.parse_rules("# Rules\n")),
                         "G1")


def run_cli(*args):
    return subprocess.run([sys.executable, SCRIPT] + list(args),
                          capture_output=True, text=True)


class CliTests(unittest.TestCase):
    def test_valid_rules_file_exits_0_with_a_markdown_report(self):
        proc = run_cli(RULES)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertTrue(proc.stdout.startswith("# "), proc.stdout[:80])

    def write(self, text):
        fd, path = tempfile.mkstemp(suffix=".md")
        self.addCleanup(os.remove, path)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        return path

    def test_lint_error_exits_1_and_is_listed_with_its_line(self):
        path = self.write(block("## G1 | style", drop=("Why",)))
        proc = run_cli(path)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("line 1 | G1 |", proc.stdout)
        self.assertIn("Why", proc.stdout)

    def test_near_duplicate_pair_exits_1(self):
        path = self.write(block("## G1 | style", Rule="Alpha beta gamma.")
                          + block("## G2 | style", Rule="Alpha beta gamma."))
        proc = run_cli(path)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("G1 ~ G2", proc.stdout)

    def test_apply_lists_hits_as_file_line_rule_match_and_exits_1(self):
        proc = run_cli(RULES, "--apply", CHAPTER)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("%s:2 | G7 | topic distribution $\\alpha$" % CHAPTER,
                      proc.stdout)

    def test_next_id_prints_the_id_and_exits_0_despite_lint_errors(self):
        path = self.write(block("## G3 | style", drop=("Why",)))
        proc = run_cli(path, "--next-id")
        self.assertEqual((proc.returncode, proc.stdout), (0, "G4\n"))

    def test_json_report_holds_errors_pairs_and_hits(self):
        proc = run_cli(RULES, "--apply", CHAPTER, "--json")
        self.assertEqual(proc.returncode, 1)
        report = json.loads(proc.stdout)
        self.assertEqual((report["errors"], report["near_duplicates"]), ([], []))
        self.assertEqual(report["hits"], [{
            "file": CHAPTER, "line": 2, "rule": "G7",
            "match": "topic distribution $\\alpha$"}])
        self.assertEqual([r["id"] for r in report["rules"]], ["G7", "G8", "G9"])

    def test_next_id_as_json(self):
        proc = run_cli(RULES, "--next-id", "--json")
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(json.loads(proc.stdout), {"next_id": "G10"})

    def test_max_sets_the_active_rule_budget(self):
        self.assertEqual(run_cli(RULES, "--max", "2").returncode, 0)
        proc = run_cli(RULES, "--max", "1")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("over budget: merge or retire rules", proc.stdout)

    def test_rules_file_that_is_not_utf8_is_read_without_crashing(self):
        path = self.write("")
        with open(path, "wb") as fh:
            fh.write(block("## G1 | style", Origin="caf\xe9 r1 F1")
                     .encode("latin-1"))
        proc = run_cli(path)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_missing_rules_or_chapter_file_is_a_usage_error(self):
        missing = os.path.join(FIXTURES, "no-such-file.tex")
        for args in ((missing,), (RULES, "--apply", CHAPTER, missing)):
            proc = run_cli(*args)
            self.assertEqual(proc.returncode, 2, args)
            self.assertIn("no-such-file.tex", proc.stderr)
            self.assertNotIn("Traceback", proc.stderr)


class HeaderTests(unittest.TestCase):
    def test_malformed_headers_are_errors(self):
        text = (block("## G2 style") + block("### G3 | style")
                + block("## G4 | style | extra") + block("## G5 | style"))
        self.assertEqual(errors_of(text), [(1, "G2", "header"),
                                           (7, "G3", "header"),
                                           (13, "G4", "header")])

    def test_unknown_category_and_status_are_errors(self):
        text = (block("## G1 | Notation") + block("## G2 | wording")
                + block("## G3 | other", Status="retired")
                + block("## G4 | citation", Status="paused"))
        self.assertEqual(errors_of(text), [(1, "G1", "category"),
                                           (7, "G2", "category"),
                                           (25, "G4", "status")])

    def test_reused_id_is_an_error_at_the_later_block(self):
        text = (block("## G1 | style") + block("## G2 | style")
                + block("## G01 | other"))
        self.assertEqual(errors_of(text), [(13, "G1", "duplicate-id")])


if __name__ == "__main__":
    unittest.main()
