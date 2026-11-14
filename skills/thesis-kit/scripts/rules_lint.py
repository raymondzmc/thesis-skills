#!/usr/bin/env python3
r"""Lint the thesis's global rules file and apply its regex checks to chapters.

Usage:
    python3 rules_lint.py RULES.md [--max 40] [--apply CHAPTER.tex ...] [--next-id] [--json]

The rules file is Markdown.  A rule block starts at a heading that begins with
G<number> and runs to the next heading:

    ## G7 | notation
    - Rule: Write the document-topic distribution as $\theta$ in every chapter.
    - Why: $\alpha$ is the Dirichlet prior, so reusing it for topics confuses readers.
    - Check: regex:`topic distribution \$\\alpha\$`
    - Example: `topic distribution $\alpha$` -> `topic distribution $\theta$`
    - Origin: ch4 r1 F2
    - Status: active

Inside a block, lines are fields ("- Name: value"), indented continuations of
the previous field, or blank.  Text outside blocks (a title, an intro, other
headings such as "## Notes") is ignored.

Lint checks: the header is "## G<number> | <category>" with category one of
notation, terminology, faithfulness, structure, style, citation, formatting,
other; IDs are unique; Rule, Why, Check and Origin are present and non-empty;
no unknown or repeated fields; Status, when given, is active or retired
(default active); Check is regex:`<python regex>` (it must compile),
script:<name> or read; at most --max active rules ("over budget: merge or
retire rules"); and no two active rules whose Rule texts have a word Jaccard
similarity of 0.6 or more (reported as pairs).

--apply searches each chapter, with % comments stripped, using every active
rule whose Check is a regex (compiled with re.MULTILINE; empty matches are
ignored) and reports hits as "file:line | rule id | matched text".

--next-id prints one past the highest G number in use (retired rules
included; numbers are never reused) and exits 0.

Exit codes: 0 = clean, 1 = lint errors, near-duplicate pairs or --apply hits,
2 = usage error (e.g. a file that does not exist).
"""
import argparse
import json
import os
import re
import sys

RULE_HEADING_RE = re.compile(r"^#+\s*G(\d+)\b")
HEADER_RE = re.compile(r"^##\s+G(\d+)\s*\|\s*(\S+)\s*$")
FIELD_RE = re.compile(r"^- ([A-Za-z]+):[ \t]*(.*)$")
REQUIRED_FIELDS = ("Rule", "Why", "Check", "Origin")
FIELDS = REQUIRED_FIELDS + ("Example", "Status")
CATEGORIES = ("notation", "terminology", "faithfulness", "structure", "style",
              "citation", "formatting", "other")
STATUSES = ("active", "retired")
CHECK_REGEX_RE = re.compile(r"^regex:\s*`(.+)`$")
CHECK_SCRIPT_RE = re.compile(r"^script:\s*(\S+)$")


def parse_check(value):
    """('regex', pattern), ('script', name) or ('read', None); None when VALUE
    is none of regex:`...`, script:<name> or read."""
    m = CHECK_REGEX_RE.match(value)
    if m:
        return ("regex", m.group(1))
    m = CHECK_SCRIPT_RE.match(value)
    if m:
        return ("script", m.group(1))
    if value == "read":
        return ("read", None)
    return None


def parse_rules(text):
    """Split TEXT into rule blocks: a heading starting with G<number> up to the
    next heading.  Inside a block, '- Name: value' lines are fields and
    indented lines continue the previous field.  Text outside blocks is
    ignored."""
    rules = []
    current = None
    last_field = None
    for number, line in enumerate(text.splitlines(), start=1):
        if line.startswith("#"):
            current = None
            m = RULE_HEADING_RE.match(line)
            if m:
                header = HEADER_RE.match(line)
                current = {"id": "G%d" % int(m.group(1)),
                           "category": header.group(2) if header else None,
                           "header_ok": bool(header), "line": number,
                           "fields": {}, "field_lines": {}, "problems": []}
                rules.append(current)
            continue
        if current is None:
            continue
        if line[:1] in (" ", "\t") and line.strip() and last_field:
            current["fields"][last_field] = (
                current["fields"][last_field] + " " + line.strip()).strip()
            continue
        last_field = None
        field = FIELD_RE.match(line)
        if field:
            name = field.group(1)
            if name not in FIELDS:
                current["problems"].append(
                    (number, "unknown-field", "unknown field '%s' (fields: %s)"
                     % (name, ", ".join(FIELDS))))
            elif name in current["fields"]:
                current["problems"].append(
                    (number, "duplicate-field", "field %s appears twice" % name))
            else:
                current["fields"][name] = field.group(2).strip()
                current["field_lines"][name] = number
                last_field = name
        elif line.strip():
            current["problems"].append(
                (number, "unexpected-text", "unexpected text in a rule block "
                 "(fields look like '- Name: value'; put notes under another "
                 "heading)"))
    for rule in rules:
        rule["status"] = rule["fields"].get("Status", "active")
    return rules


NEAR_DUPLICATE = 0.6  # word Jaccard of two Rule texts


def words(text):
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def jaccard(a, b):
    a, b = words(a), words(b)
    return len(a & b) / len(a | b) if a | b else 0.0


def near_duplicates(rules):
    """Pairs of active rules whose Rule texts share most of their words."""
    active = [r for r in rules if r["status"] == "active"]
    pairs = []
    for i, first in enumerate(active):
        for second in active[i + 1:]:
            if first["category"] != second["category"]:
                continue  # a notation rule and a terminology rule may share wording
            similarity = jaccard(first["fields"].get("Rule", ""),
                                 second["fields"].get("Rule", ""))
            if similarity >= NEAR_DUPLICATE:
                pairs.append({"a": first["id"], "b": second["id"],
                              "similarity": round(similarity, 3)})
    return pairs


def _error(rule, line, kind, message, **extra):
    return dict({"line": line, "rule": rule["id"] if rule else None,
                 "kind": kind, "message": message}, **extra)


def _rule_errors(rule):
    errors = [_error(rule, line, kind, message)
              for line, kind, message in rule["problems"]]
    if not rule["header_ok"]:
        errors.append(_error(rule, rule["line"], "header",
                             "header must look like '## G<number> | "
                             "<category>'"))
    elif rule["category"] not in CATEGORIES:
        errors.append(_error(rule, rule["line"], "category",
                             "unknown category '%s' (use one of: %s)"
                             % (rule["category"], ", ".join(CATEGORIES))))
    check = rule["fields"].get("Check")
    parsed = parse_check(check) if check else None
    if check and parsed is None:
        errors.append(_error(rule, rule["field_lines"]["Check"], "check",
                             "Check must be regex:`<python regex>`, "
                             "script:<name> or read, not '%s'" % check))
    elif parsed and parsed[0] == "regex":
        try:
            re.compile(parsed[1], re.MULTILINE)
        except re.error as exc:
            errors.append(_error(rule, rule["field_lines"]["Check"], "regex",
                                 "regex does not compile: %s" % exc))
    if rule["status"] not in STATUSES:
        errors.append(_error(rule, rule["field_lines"]["Status"], "status",
                             "Status must be active or retired, not '%s'"
                             % rule["status"]))
    for name in REQUIRED_FIELDS:
        if name not in rule["fields"]:
            errors.append(_error(rule, rule["line"], "missing-field",
                                 "missing required field %s" % name,
                                 field=name))
        elif not rule["fields"][name]:
            errors.append(_error(rule, rule["field_lines"][name],
                                 "empty-field",
                                 "required field %s is empty" % name,
                                 field=name))
    return errors


# A % starts a LaTeX comment unless escaped; an even run of backslashes
# before it (as in the line break \\%) does not escape it.
COMMENT_RE = re.compile(r"(?<!\\)((?:\\\\)*)%.*$", re.MULTILINE)


def strip_comments(text):
    """Remove % comments but keep every newline, so line numbers still match."""
    return COMMENT_RE.sub(r"\1", text)


def apply_rules(rules, chapters):
    """Search each (path, text) chapter, comments stripped, with every active
    rule whose Check is a regex (compiled with re.MULTILINE).  Empty matches
    are not hits.  Rules whose regex does not compile are skipped (lint
    reports them)."""
    checks = []
    for rule in rules:
        parsed = parse_check(rule["fields"].get("Check", ""))
        if rule["status"] != "active" or not parsed or parsed[0] != "regex":
            continue
        try:
            checks.append((rule["id"], re.compile(parsed[1], re.MULTILINE)))
        except re.error:
            continue
    hits = []
    for path, text in chapters:
        text = strip_comments(text)
        found = []
        for rule_id, pattern in checks:
            for m in pattern.finditer(text):
                if m.end() == m.start():  # e.g. `x*` matches everywhere
                    continue
                found.append((m.start(), {
                    "file": path, "line": text.count("\n", 0, m.start()) + 1,
                    "rule": rule_id, "match": " ".join(m.group(0).split())}))
        found.sort(key=lambda item: item[0])
        hits.extend(hit for _, hit in found)
    return hits


def next_id(rules):
    """One past the highest G number in use (retired rules included), so an
    ID cited by an old critique is never given to a different rule."""
    return "G%d" % (max([int(rule["id"][1:]) for rule in rules] or [0]) + 1)


def lint(text, max_active=40):
    rules = parse_rules(text)
    errors = []
    first_line = {}
    for rule in rules:
        errors.extend(_rule_errors(rule))
        if rule["id"] in first_line:
            errors.append(_error(rule, rule["line"], "duplicate-id",
                                 "%s is already used at line %d"
                                 % (rule["id"], first_line[rule["id"]])))
        else:
            first_line[rule["id"]] = rule["line"]
    active = [rule for rule in rules if rule["status"] == "active"]
    if len(active) > max_active:
        errors.append(_error(None, None, "budget",
                             "%d active rules, budget %d: over budget: merge "
                             "or retire rules" % (len(active), max_active)))
    errors.sort(key=lambda e: e["line"] or 0)
    return {"rules": rules, "errors": errors,
            "near_duplicates": near_duplicates(rules),
            "active": len(active), "max_active": max_active}


def render_markdown(path, report, hits=None):
    rules = report["rules"]
    out = ["# Rules lint: %s" % path, ""]
    out.append("%d rule(s): %d active, %d retired; budget %d active."
               % (len(rules), report["active"], len(rules) - report["active"],
                  report["max_active"]))
    out.append("")
    errors = report["errors"]
    out.append("## Errors (%d)" % len(errors))
    out.append("")
    for error in errors:
        where = "line %d" % error["line"] if error["line"] else "file"
        out.append("- %s | %s | %s" % (where, error["rule"] or "-",
                                       error["message"]))
    if not errors:
        out.append("None.")
    out.append("")
    pairs = report["near_duplicates"]
    out.append("## Near-duplicate active rules (%d)" % len(pairs))
    out.append("")
    for pair in pairs:
        out.append("- %s ~ %s (word Jaccard %.2f): merge them or retire one"
                   % (pair["a"], pair["b"], pair["similarity"]))
    if not pairs:
        out.append("None.")
    out.append("")
    if hits is not None:
        out.append("## Hits (%d)" % len(hits))
        out.append("")
        for hit in hits:
            out.append("- %s:%d | %s | %s" % (hit["file"], hit["line"],
                                              hit["rule"], hit["match"]))
        if not hits:
            out.append("None.")
        out.append("")
    return "\n".join(out)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Lint the thesis's global rules file (rule block format, "
                    "unique IDs, required fields, categories, Status, Check "
                    "regexes, the active-rule budget, near-duplicate rules) "
                    "and optionally apply its regex checks to chapters.",
        epilog="Exit codes: 0 = clean, 1 = lint errors, near-duplicate pairs "
               "or --apply hits, 2 = usage error.")
    parser.add_argument("rules", metavar="RULES.md", help="the rules file")
    parser.add_argument("--max", type=int, default=40, dest="max_active",
                        metavar="N",
                        help="most active rules allowed (default 40)")
    parser.add_argument("--apply", nargs="+", metavar="CHAPTER.tex",
                        help="search these chapters with the active regex "
                             "checks")
    parser.add_argument("--next-id", action="store_true",
                        help="print the next free rule ID (e.g. G8) and exit 0")
    parser.add_argument("--json", action="store_true",
                        help="print machine-readable JSON instead of Markdown")
    args = parser.parse_args(argv)
    for path in [args.rules] + (args.apply or []):
        if not os.path.isfile(path):
            print("rules_lint: no such file: %s" % path, file=sys.stderr)
            return 2
    with open(args.rules, encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    if args.next_id:
        new_id = next_id(parse_rules(text))
        print(json.dumps({"next_id": new_id}) if args.json else new_id)
        return 0
    report = lint(text, args.max_active)
    hits = None
    if args.apply:
        chapters = []
        for path in args.apply:
            with open(path, encoding="utf-8", errors="replace") as fh:
                chapters.append((path, fh.read()))
        hits = apply_rules(report["rules"], chapters)
    if args.json:
        print(json.dumps({
            "file": args.rules,
            "rules": [{key: rule[key] for key in
                       ("id", "category", "status", "line", "fields")}
                      for rule in report["rules"]],
            "active": report["active"], "max_active": report["max_active"],
            "errors": report["errors"],
            "near_duplicates": report["near_duplicates"],
            "hits": hits}, indent=2))
    else:
        print(render_markdown(args.rules, report, hits))
    return 1 if report["errors"] or report["near_duplicates"] or hits else 0


if __name__ == "__main__":
    sys.exit(main())
