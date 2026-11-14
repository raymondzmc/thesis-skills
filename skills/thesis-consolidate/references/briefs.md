# Briefs for thesis-consolidate agents

Each agent's prompt is the paragraph under "Every agent", then one section below, then
the paths: the files in FILES (from `latex_check.py --list-files`), `thesis-work/plan.md`,
`thesis-work/rules/global.md`, `thesis-work/papers/`, and the inventory file. Replace
`<kit>` with the absolute path of the thesis-kit skill.

## Every agent

You are reading a PhD thesis for consistency. Do not edit the thesis; write your report
to the path the coordinator gives. Report each problem
as one finding block in the format of `<kit>/references/formats.md` (lens `mechanics`,
`faithfulness` or `argument`), with an exact quote in Original, and validate your report
with `python3 <kit>/scripts/stagnation.py parse <report>`. Put the other quotes you rely
on (the chapter's line, the paper's line) in Reasoning, each with file:line, because the
format has no other fields. Number your findings from the number the coordinator gives
you (F101, F201 or F301) so reports can be merged. Major findings only; list anything
small under a final `## Minor` heading, one line each.

## Front and back matter against the chapters (start at F101)

Read the abstract, lay summary, preface, the Introduction's overview, and the
Conclusion's summary. For every statement about a chapter (a number, a venue, a method
name, a claim about what the chapter shows), find the chapter's own statement and the
paper's, and quote all three. Report a mismatch between any two. When no chapter states
the number, report that. If it is derived (a relative gain, a difference, an average),
recompute it from the chapter's numbers and show the arithmetic and the configuration. A
`check_numbers.py` match counts as support only when the matched line states the same
quantity. Also check the preface's publication list (venues, years, co-authors) against
the papers, and list any chapter contribution that the abstract or the conclusion leaves
out.

## Thesis-wide wording and notation (start at F201)

1. Research questions: every place an RQ is stated in full must match `plan.md`
   verbatim; a paraphrase in passing must not change its meaning.
2. Core terms: each term in `plan.md` is used with its defined meaning; list other names
   used for the same thing.
3. Notation: build a table symbol | meaning | chapter:line for every symbol defined in a
   chapter. Report a symbol used with two meanings, and a quantity written with two
   symbols.
4. Names: methods, models, datasets and metrics spelled and capitalized the same way
   everywhere ("F1" or "F-1", "TopK" or "Top-K"), including inside math.
5. For the inventory's variant groups and acronym list, say which form the thesis should
   use and why.

## Chapter seams and duplicated background (start at F301)

1. Each chapter's opening paragraph against `plan.md`: does it place the chapter in its
   part, name its RQ, link to the previous chapter, and state the publication note? Quote
   any piece that is missing or contradicts the plan.
2. Openers that repeat one another's sentence pattern (for example every chapter starting
   "In this chapter, we"): quote them and propose varied wording that keeps the content.
3. Each chapter's closing: does it say what the chapter contributes to its RQ, and does
   the next chapter pick up from there?
4. Duplicated background: for each overlap pair in the inventory, and any background a
   chapter re-explains that the Introduction already covers, propose which copy stays and
   the cross-reference that replaces the other. These are proposals for the student.
