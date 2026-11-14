#!/usr/bin/env python3
"""Detect a stuck revision loop: findings that recur, or fixes that did not take.

Usage:
    python3 stagnation.py parse CRITIQUE.md [--json]
    python3 stagnation.py recurring --prev PREV.md --curr CURR.md [--threshold 0.5] [--json]
    python3 stagnation.py unchanged --critique PREV.md --before BEFORE.tex --after AFTER.tex [--threshold 0.85] [--json]

A critique is Markdown with one block per finding:

    ### F3 | readability | major | local
    - Location: chapters/ch4.tex:57
    - Original: "exact quote from the chapter"
    - Fix: "replacement text" (or a concrete instruction)
    - Reasoning: why, citing the paper page/table or a rule ID
    - Rule: G7

lens: faithfulness, argument, readability or mechanics; severity: major or
minor; scope: global or local; Rule: a rule ID (G7), new, or -.  All five
fields are required.  A field runs until the next "- Field:" line, so the
Original may span several lines (a quoted one may even span blank lines); it
may be wrapped in double quotes or backticks.  A block ends at the next
heading or at text that follows a blank line, so headings, a summary or notes
may sit between blocks.

parse      validate a critique and list its findings; exit 1 if any block is
           malformed (each error names its line).
recurring  pair findings of the current round with findings of the previous
           round whose Original overlaps (word Jaccard on lowercase
           alphanumeric words >= --threshold, or one quote's words inside the
           other's), whatever the lens; exit 1 if any pair.
unchanged  for each previous finding whose Fix is not "keep": locate the
           Original in BEFORE (exact after whitespace normalization, else the
           most similar run of words, which must reach a ratio of 0.7), find
           the most similar run of words of similar length in AFTER, and
           compare the two with difflib's SequenceMatcher ratio:
             unchanged  ratio >= --threshold (the fix did not take, or was
                        cosmetic)
             applied    ratio >= --threshold, but the quoted Fix text (two
                        words or more) is now in AFTER and was not in
                        BEFORE: a small fix made exactly as asked
             rewritten  below the threshold
             removed    no run of AFTER reaches 0.3
             not-found  the Original is not in BEFORE
           % comments are ignored in BEFORE and AFTER.  Exit 1 if any
           finding is unchanged.

Malformed blocks are still compared by recurring and unchanged when their
Original was read; the report notes how many format errors each file has.

Exit codes: 0 = nothing found, 1 = see each command, 2 = usage error (e.g. a
file that does not exist).
"""
import argparse
import json
import os
import re
import sys
from collections import Counter
from difflib import SequenceMatcher

FINDING_HEADING_RE = re.compile(r"^#+\s*F(\d+)\b")
# Headers the parser cannot read as blocks: indented, bold instead of ###, or
# any other line that announces a major finding without "### F<n> |" (a list
# item, a numbered line, "### **F1** |", "### Finding F1 |", a bare "F1 |").
UNREADABLE_HEADER_RE = re.compile(
    r"^(?:\s+#+|\s*\*\*)\s*F\d+\s*\|"
    r"|^(?!#+\s*F\d+\b)(?!\s*\|)[\W\d]*?(?:Finding\s+)?F\d+\W*\|[^|\n]*\|\W*major\b")
HEADER_RE = re.compile(
    r"^###\s+F(\d+)\s*\|\s*(\S+)\s*\|\s*(\S+)\s*\|\s*(\S+)\s*$")
FIELD_RE = re.compile(r"^- ([A-Za-z]+):[ \t]*(.*)$")
FIELDS = ("Location", "Original", "Fix", "Reasoning", "Rule")
LENSES = ("faithfulness", "argument", "readability", "mechanics")
SEVERITIES = ("major", "minor")
SCOPES = ("global", "local")
RULE_VALUE_RE = re.compile(r"^(?:G\d+|new|-)$")
QUOTES = {'"': '"', "\u201c": "\u201d"}  # opening -> closing; backticks too
# A % starts a LaTeX comment unless escaped; an even run of backslashes
# before it (as in the line break \\%) does not escape it.
COMMENT_RE = re.compile(r"(?<!\\)((?:\\\\)*)%.*$", re.MULTILINE)
LOCATE_AT_LEAST = 0.7  # a fuzzy match of the Original in BEFORE must reach this
REMOVED_BELOW = 0.3  # no window of AFTER reaches this ratio: passage removed
CANDIDATES = 5  # regions refined with difflib after the word-overlap pass


def _quote_is_open(value):
    """True while a value that starts with a quote has not been closed."""
    v = value.strip()
    if not v:
        return False
    if v[0] == "`":
        ticks = len(v) - len(v.lstrip("`"))
        return not (len(v) > ticks and v.endswith("`" * ticks))
    if v[0] in QUOTES:
        return not (len(v) >= 2 and v.endswith(QUOTES[v[0]]))
    return False


def unquote(value):
    """Drop one pair of surrounding double quotes, curly quotes or backticks."""
    v = value.strip()
    if len(v) >= 2 and v[0] in QUOTES and v[-1] == QUOTES[v[0]]:
        return v[1:-1].strip()
    if v.startswith("`"):
        ticks = len(v) - len(v.lstrip("`"))
        if len(v) > 2 * ticks and v.endswith("`" * ticks):
            return v[ticks:-ticks].strip()
    return v


def parse_critique(text):
    """Find the finding blocks of a critique.  A block starts at a heading
    that begins with F<number> and ends at the next heading, or at text that
    follows a blank line (a summary or note between blocks).  A field runs
    until the next '- Field:' line; a quoted Original may span blank lines."""
    blocks = []
    unreadable = []
    current = field = None
    blank = False
    for number, line in enumerate(text.splitlines(), start=1):
        if UNREADABLE_HEADER_RE.match(line):
            unreadable.append(number)
            current = field = None
            continue
        if line.startswith("#"):
            current = field = None
            m = FINDING_HEADING_RE.match(line)
            if m:
                header = HEADER_RE.match(line)
                current = {"id": "F%d" % int(m.group(1)), "line": number,
                           "header": header.groups()[1:] if header else None,
                           "fields": {}, "field_lines": {}, "problems": []}
                blocks.append(current)
                blank = False
            continue
        if current is None:
            continue
        m = FIELD_RE.match(line)
        if m:
            name = m.group(1)
            if blank and (name not in FIELDS or name in current["fields"]):
                current = field = None  # a list in the text after the block
                continue
            blank = False
            if name not in FIELDS:
                current["problems"].append(
                    (number, "unknown-field", "unknown field '%s' (fields: %s)"
                     % (name, ", ".join(FIELDS))))
            elif name in current["fields"]:
                current["problems"].append(
                    (number, "duplicate-field", "field %s appears twice"
                     % name))
                name = "\0" + name  # keep its continuation lines out of the way
            current["fields"][name] = m.group(2)
            current["field_lines"][name] = number
            field = name
            continue
        if not line.strip():
            if field == "Original" and _quote_is_open(current["fields"][field]):
                current["fields"][field] += "\n"
            else:
                blank = True
            continue
        if field and not blank:
            current["fields"][field] += "\n" + line.strip()
            continue
        current = field = None  # text after a blank line ends the block

    findings, errors = [], []
    first_line = {}
    for block in blocks:
        errors.extend(_block_errors(block))
        if block["id"] in first_line:
            errors.append(_error(block, block["line"], "duplicate-id",
                                 "%s is already used at line %d"
                                 % (block["id"], first_line[block["id"]])))
        else:
            first_line[block["id"]] = block["line"]
        lens, severity, scope = block["header"] or (None, None, None)
        fields = block["fields"]
        findings.append({
            "id": block["id"], "line": block["line"], "lens": lens,
            "severity": severity, "scope": scope,
            "location": fields.get("Location", "").strip(),
            "original": unquote(fields.get("Original", "")),
            "fix": unquote(fields.get("Fix", "")),
            "reasoning": fields.get("Reasoning", "").strip(),
            "rule": fields.get("Rule", "").strip(),
        })
    for number in unreadable:
        errors.append({"line": number, "finding": None, "kind": "unreadable-header",
                       "message": "a finding header must start the line with "
                                  "'### F<n> | ...' (no indent, no bold)"})
    errors.sort(key=lambda e: e["line"])
    return {"findings": findings, "errors": errors}


def _error(block, line, kind, message):
    return {"line": line, "finding": block["id"], "kind": kind,
            "message": message}


def _block_errors(block):
    errors = [_error(block, line, kind, message)
              for line, kind, message in block["problems"]]
    if block["header"] is None:
        errors.append(_error(block, block["line"], "header",
                             "header must look like '### F<n> | <lens> | "
                             "<severity> | <scope>'"))
    else:
        for kind, value, allowed in zip(("lens", "severity", "scope"),
                                        block["header"],
                                        (LENSES, SEVERITIES, SCOPES)):
            if value not in allowed:
                errors.append(_error(block, block["line"], kind,
                                     "%s must be one of %s, not '%s'"
                                     % (kind, ", ".join(allowed), value)))
    fields, lines = block["fields"], block["field_lines"]
    for name in FIELDS:
        if name not in fields:
            errors.append(_error(block, block["line"], "missing-field",
                                 "missing field %s" % name))
        elif not unquote(fields[name]):
            errors.append(_error(block, lines[name], "empty-field",
                                 "field %s is empty" % name))
    rule = fields.get("Rule", "").strip()
    if rule and not RULE_VALUE_RE.match(rule):
        errors.append(_error(block, lines["Rule"], "rule",
                             "Rule must be a rule ID such as G7, new or -, "
                             "not '%s'" % rule))
    return errors


def tokens(text):
    """Lowercase alphanumeric words, in order."""
    return re.findall(r"[a-z0-9]+", text.lower())


def _contains(outer, inner):
    """True if the word sequence INNER occurs contiguously in OUTER."""
    return (" %s " % " ".join(inner)) in (" %s " % " ".join(outer))


def recurring(prev, curr, threshold=0.5):
    """Pairs (current finding, previous finding) whose Original quotes overlap:
    word Jaccard >= THRESHOLD, or one quote's words lie inside the other's.
    The lens is ignored: re-flagging a passage under another lens counts."""
    pairs = []
    for new in curr:
        new_words = tokens(new["original"])
        if not new_words:
            continue
        for old in prev:
            old_words = tokens(old["original"])
            if not old_words:
                continue
            a, b = set(new_words), set(old_words)
            similarity = len(a & b) / len(a | b)
            contained = (_contains(old_words, new_words)
                         or _contains(new_words, old_words))
            if similarity >= threshold or contained:
                pairs.append({"curr": new["id"], "prev": old["id"],
                              "similarity": round(similarity, 3),
                              "contained": contained,
                              "prev_lens": old["lens"],
                              "curr_lens": new["lens"]})
    return pairs


def strip_comments(text):
    """Remove % comments but keep every newline, so line numbers still match."""
    return COMMENT_RE.sub(r"\1", text)


def normalize(text):
    """Collapse every run of whitespace to one space."""
    return " ".join(text.split())


def _window_lengths(n, available):
    """Window sizes (in words) "of similar length" to an N-word passage."""
    low = max(1, int(n * 0.75))
    high = max(low, -(-n * 5 // 4))  # ceil(1.25 n)
    return [size for size in range(low, high + 1) if size <= available] or [
        available]


def _key(word):
    return re.sub(r"[^a-z0-9]", "", word.lower())


def _overlap_starts(passage_words, words, size, count):
    """Starts of the COUNT windows of SIZE words that share the most words
    with the passage, at least half a window apart (one cheap pass)."""
    want = Counter(k for k in map(_key, passage_words) if k)
    keys = [_key(word) for word in words]
    have = Counter()
    overlap = 0
    scored = []
    for i, key in enumerate(keys):
        if key and have[key] < want[key]:
            overlap += 1
        have[key] += 1
        if i >= size:
            old = keys[i - size]
            have[old] -= 1
            if old and have[old] < want[old]:
                overlap -= 1
        if i >= size - 1:
            scored.append((-overlap, i - size + 1))
    scored.sort()
    starts, gap = [], max(1, size // 2)
    for _, begin in scored:
        if all(abs(begin - other) >= gap for other in starts):
            starts.append(begin)
            if len(starts) == count:
                break
    return starts


def best_window(passage, words):
    """(ratio, start, end): the run words[start:end], of similar length to
    PASSAGE, whose difflib ratio with PASSAGE is highest.  A cheap word-overlap
    pass picks a few regions; difflib then refines start and end in each."""
    if not words or not passage:
        return (0.0, 0, 0)
    passage_words = passage.split()
    sizes = _window_lengths(len(passage_words), len(words))
    low, high = sizes[0], sizes[-1]
    size = min(len(passage_words), len(words))
    total = len(words)
    matcher = SequenceMatcher(None, autojunk=False)
    matcher.set_seq2(passage)
    cache = {}

    def score(begin, end):
        if (begin, end) not in cache:
            matcher.set_seq1(" ".join(words[begin:end]))
            cache[(begin, end)] = matcher.ratio()
        return cache[(begin, end)]

    best = (0.0, 0, 0)
    reach = max(1, len(passage_words) // 2)
    for seed in _overlap_starts(passage_words, words, size, CANDIDATES):
        begin = seed
        for other in range(max(0, seed - reach),
                           min(total - size, seed + reach) + 1):
            if score(other, other + size) > score(begin, begin + size):
                begin = other
        end = begin + size
        for other in range(begin + low, min(total, begin + high) + 1):
            if score(begin, other) > score(begin, end):
                end = other
        for other in range(max(0, end - high), end - low + 1):
            if score(other, end) > score(begin, end):
                begin = other
        if score(begin, end) > best[0]:
            best = (score(begin, end), begin, end)
    return best


def unchanged(findings, before, after, threshold=0.85):
    """For each finding whose Fix is not 'keep', find its Original in BEFORE
    and the most similar passage in AFTER; a ratio of THRESHOLD or more means
    the revision left the flagged wording essentially as it was."""
    before_text = normalize(strip_comments(before))
    before_words = before_text.split()
    after_text = normalize(strip_comments(after))
    after_words = after_text.split()
    results, skipped = [], []
    for item in findings:
        if item["fix"].strip() == "keep":
            skipped.append(item["id"])
            continue
        quote = normalize(item["original"])
        passage, located, locate_ratio = None, None, None
        if quote and quote in before_text:
            passage, located, locate_ratio = quote, "exact", 1.0
        elif quote:
            ratio, start, end = best_window(quote, before_words)
            if ratio >= LOCATE_AT_LEAST:
                passage = " ".join(before_words[start:end])
                located, locate_ratio = "fuzzy", round(ratio, 3)
        if passage is None:
            results.append({"finding": item["id"], "lens": item["lens"],
                            "status": "not-found", "ratio": None,
                            "located": None, "locate_ratio": None,
                            "before": None, "after": None})
            continue
        ratio, start, end = best_window(passage, after_words)
        if ratio < REMOVED_BELOW:
            status = "removed"
        elif ratio >= threshold:
            # A small fix applied exactly as asked (64.3 -> 63.4) also leaves
            # the passage similar; that is "applied", not stuck.
            fix = normalize(unquote(item["fix"]))
            applied = (len(fix.split()) >= 2 and fix in after_text
                       and fix not in before_text)
            status = "applied" if applied else "unchanged"
        else:
            status = "rewritten"
        results.append({"finding": item["id"], "lens": item["lens"],
                        "status": status, "ratio": round(ratio, 3),
                        "located": located, "locate_ratio": locate_ratio,
                        "before": passage,
                        "after": " ".join(after_words[start:end])})
    return {"results": results, "skipped": skipped}


def _read(path):
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def render_parse(path, parsed):
    findings, errors = parsed["findings"], parsed["errors"]
    out = ["# Critique findings: %s" % path, "",
           "%d finding(s), %d format error(s)." % (len(findings), len(errors)),
           "", "## Findings (%d)" % len(findings), ""]
    for item in findings:
        out.append("- %s | %s | %s | %s | %s | Rule %s" % (
            item["id"], item["lens"], item["severity"], item["scope"],
            item["location"] or "-", item["rule"] or "-"))
        out.append("  Original: \"%s\"" % normalize(item["original"]))
    if not findings:
        out.append("None.")
    out.append("")
    if errors:
        out.append("## Format errors (%d)" % len(errors))
        out.append("")
        out.extend("- line %d | %s | %s" % (e["line"], e["finding"],
                                            e["message"]) for e in errors)
        out.append("")
    return "\n".join(out)


def _format_notes(named):
    """Lines warning about critiques whose blocks are malformed."""
    return ["Note: %s has %d format error(s); run 'stagnation.py parse' on "
            "it. Findings are still compared where their Original was read."
            % (path, len(parsed["errors"]))
            for path, parsed in named if parsed["errors"]]


def render_recurring(prev_path, curr_path, prev, curr, pairs, threshold):
    out = ["# Recurring findings", "",
           "Previous: %s (%d findings). Current: %s (%d findings). Word "
           "Jaccard threshold %s." % (prev_path, len(prev["findings"]),
                                       curr_path, len(curr["findings"]),
                                       threshold), ""]
    out.extend(_format_notes([(prev_path, prev), (curr_path, curr)]))
    out.append("## Pairs (%d)" % len(pairs))
    out.append("")
    for pair in pairs:
        out.append("- %s (%s) re-flags previous %s (%s): word Jaccard %s%s"
                   % (pair["curr"], pair["curr_lens"], pair["prev"],
                      pair["prev_lens"], pair["similarity"],
                      ", one quote contains the other" if pair["contained"]
                      else ""))
    if not pairs:
        out.append("None.")
    out.append("")
    return "\n".join(out)


def render_unchanged(paths, parsed, out_data, threshold):
    critique, before, after = paths
    results = out_data["results"]
    out = ["# Unchanged after revision", "",
           "Critique: %s. Before: %s. After: %s. A ratio of %s or more counts "
           "as unchanged." % (critique, before, after, threshold), ""]
    out.extend(_format_notes([(critique, parsed)]))
    out.append("## Findings checked (%d)" % len(results))
    out.append("")
    for result in results:
        if result["status"] == "not-found":
            out.append("- %s (%s) | not-found: the Original is not in %s"
                       % (result["finding"], result["lens"], before))
            continue
        out.append("- %s (%s) | %s | ratio %s (Original located %s)"
                   % (result["finding"], result["lens"], result["status"],
                      result["ratio"], result["located"]))
        out.append("  before: \"%s\"" % result["before"])
        out.append("  after:  \"%s\"" % result["after"])
    if not results:
        out.append("None.")
    out.append("")
    if out_data["skipped"]:
        out.append("Skipped (Fix is keep): %s" % ", ".join(out_data["skipped"]))
        out.append("")
    return "\n".join(out)


def _cmd_parse(args):
    parsed = parse_critique(_read(args.critique))
    if args.json:
        print(json.dumps(dict(parsed, critique=args.critique), indent=2))
    else:
        print(render_parse(args.critique, parsed))
    return 1 if parsed["errors"] else 0


def _cmd_recurring(args):
    prev = parse_critique(_read(args.prev))
    curr = parse_critique(_read(args.curr))
    pairs = recurring(prev["findings"], curr["findings"], args.threshold)
    if args.json:
        print(json.dumps({"prev": args.prev, "curr": args.curr,
                          "threshold": args.threshold, "pairs": pairs,
                          "format_errors": {"prev": len(prev["errors"]),
                                            "curr": len(curr["errors"])}},
                         indent=2))
    else:
        print(render_recurring(args.prev, args.curr, prev, curr, pairs,
                               args.threshold))
    return 1 if pairs else 0


def _cmd_unchanged(args):
    parsed = parse_critique(_read(args.critique))
    out_data = unchanged(parsed["findings"], _read(args.before),
                         _read(args.after), args.threshold)
    if args.json:
        print(json.dumps(dict(out_data, critique=args.critique,
                              before=args.before, after=args.after,
                              threshold=args.threshold,
                              format_errors=len(parsed["errors"])),
                         indent=2))
    else:
        print(render_unchanged((args.critique, args.before, args.after),
                               parsed, out_data, args.threshold))
    return 1 if any(r["status"] == "unchanged"
                    for r in out_data["results"]) else 0


COMMANDS = {"parse": (_cmd_parse, ["critique"]),
            "recurring": (_cmd_recurring, ["prev", "curr"]),
            "unchanged": (_cmd_unchanged, ["critique", "before", "after"])}


def main(argv=None):
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true",
                        help="print machine-readable JSON instead of Markdown")
    parser = argparse.ArgumentParser(
        description="Detect a stuck revision loop: findings that the critic "
                    "raises again, and fixes that left the flagged wording "
                    "essentially unchanged.",
        epilog="Run '%(prog)s COMMAND --help' for each command. Exit codes: "
               "0 = nothing found, 1 = malformed blocks (parse), recurring "
               "pairs (recurring) or unchanged findings (unchanged), "
               "2 = usage error.")
    commands = parser.add_subparsers(dest="command", metavar="COMMAND")
    commands.required = True
    parse_cmd = commands.add_parser(
        "parse", parents=[common],
        help="validate a critique and list its findings (exit 1 on "
             "malformed blocks)")
    parse_cmd.add_argument("critique", metavar="CRITIQUE.md",
                           help="the critique to check")
    recurring_cmd = commands.add_parser(
        "recurring", parents=[common],
        help="findings of this round whose Original overlaps a finding of "
             "the previous round (exit 1 if any)")
    recurring_cmd.add_argument("--prev", required=True, metavar="PREV.md",
                               help="critique of the previous round")
    recurring_cmd.add_argument("--curr", required=True, metavar="CURR.md",
                               help="critique of this round")
    recurring_cmd.add_argument("--threshold", type=float, default=0.5,
                               help="word Jaccard from which two quotes "
                                    "overlap (default 0.5)")
    unchanged_cmd = commands.add_parser(
        "unchanged", parents=[common],
        help="findings whose flagged wording survived the revision (exit 1 "
             "if any)")
    unchanged_cmd.add_argument("--critique", required=True, metavar="PREV.md",
                               help="critique the revision answered")
    unchanged_cmd.add_argument("--before", required=True, metavar="BEFORE.tex",
                               help="chapter as the critic read it")
    unchanged_cmd.add_argument("--after", required=True, metavar="AFTER.tex",
                               help="chapter after the revision")
    unchanged_cmd.add_argument("--threshold", type=float, default=0.85,
                               help="difflib ratio from which a passage "
                                    "counts as unchanged (default 0.85)")
    args = parser.parse_args(argv)

    command, paths = COMMANDS[args.command]
    for name in paths:
        if not os.path.isfile(getattr(args, name)):
            print("stagnation: no such file: %s" % getattr(args, name),
                  file=sys.stderr)
            return 2
    return command(args)


if __name__ == "__main__":
    sys.exit(main())
