---
name: thesis-write
description: Use when drafting or revising thesis chapters from a student's papers once a thesis plan exists, when chapter revisions keep reusing the same wording without getting better, or when a chapter needs critique and revision rounds or a supervisor's comments worked in.
---

# Thesis write

## Overview

Drafts every chapter, then runs critique and revision rounds across all chapters. Each
round uses new agents (writer, critic, judge), so no agent anchors on its own earlier
drafts. Between rounds only the chapter files and `thesis-work/rules/global.md` carry
over as memory. A chapter's local findings become a fix list for one revision and are
then dropped.

Core principle: a change is kept only when it fixes a quoted problem and passes its
check (a script for conventions and numbers, a blind judge for prose). A problem that
comes back is rewritten from the source, not reworded again.

**REQUIRED SUB-SKILL:** load `thesis-kit` first. `<kit>` below is its base directory;
replace every `<kit>` with that absolute path, in commands and in every brief you paste
into an agent's prompt. This skill needs `thesis-work/plan.md`; if it is missing, run
`thesis-theme` first. `R` below is `thesis-work/rounds/r<N>/<ch>/`.

## Before the first round, ask the student

- Which chapters to write now. Paper chapters come first; the Introduction and
  Conclusion come after the paper chapters have had one round (see below).
- How many rounds (default 3, one per lens) and whether to pause after the first draft.
- Whether a supervisor's comments will come in, and in what form.

## Round 0: draft

One writer agent per chapter, all in one message, with `references/writer-brief.md` in
draft mode, each writing its notes to `thesis-work/rounds/r0/<ch>/notes.md`. Then you
(not the writers) add each chapter and its appendix file to `main.tex` in plan order, the
way the template includes chapters (`\include{chapters/<ch>}` or `\input{...}`), with a
`\part{...}` line where `plan.md` starts a part.
Move each "For the student" item from the writers' notes to
`thesis-work/escalations.md`. Copy each chapter to `thesis-work/rounds/r0/<ch>/end.tex`,
and commit when `config.md` says `Commits: allowed`.

## Rounds 1 to 3

Lenses rotate: 1 faithfulness, 2 argument, 3 readability. Steps 1 to 3 run for all
chapters in parallel; step 4 starts once every critique is in, and step 5 waits until
every chapter is sorted.

1. **Start.** Compare each chapter with `thesis-work/rounds/r<N-1>/<ch>/end.tex`. Passages
   the student changed are theirs: write them to `R/student-edits.md` together with the
   passages listed in earlier rounds' `student-edits.md` for this chapter. Copy the
   chapter to `R/start.tex`.
2. **Check.** Write to `R/checks.md` the output of
   `check_numbers.py chapters/<ch>.tex --source thesis-work/papers/<id>/`,
   `rules_lint.py thesis-work/rules/global.md --apply chapters/<ch>.tex`,
   `latex_check.py main.tex`, and `prose_metrics.py` on all chapter files (its
   cross-chapter section shows wording that repeats).
3. **Critique.** A new critic agent per chapter with `references/critic-brief.md`, this
   round's lens and the paths. It writes `R/critique.md`; check it with
   `stagnation.py parse`.
4. **Sort the findings** (you, the coordinator), once every critique is in, together with
   any supervisor comments saved in `thesis-work/feedback/` since the last round. See
   `<kit>/references/formats.md`.
   - Drop a finding whose Original is not in the chapter (the critic misquoted). Check
     each faithfulness finding against the paper before keeping it.
   - Drop a finding on an item the student already decided in `escalations.md`.
   - To `thesis-work/escalations.md`, not to a writer: a finding on a passage in
     `R/student-edits.md`; a finding that would change what the thesis claims; a finding
     that cuts or moves a section or background.
   - Scope `global` or Rule `new`: add one block to `rules/global.md` with Edit (id from
     `rules_lint.py thesis-work/rules/global.md --next-id`). If a similar rule exists,
     sharpen it instead. At most 40 active rules. Also copy the finding into `R/fixlist.md`
     so this chapter's passage gets fixed.
   - Scope `local`: copy the block into `R/fixlist.md`.
   - Read all chapters' fix lists side by side, with earlier rounds' fix lists in
     `rounds/` (only you read these). A kind of finding that appears in two or more
     chapters becomes one global rule; the findings stay in their fix lists.
   - Plan changes: for a chapter listed under a `Revised` line of `plan.md` that is newer
     than the last round, add a finding on its opening paragraph and closing link to
     `R/fixlist.md`, saying what they must now say.
   - Stuck passages (from round 2 on): run
     `stagnation.py recurring --prev thesis-work/rounds/r<N-1>/<ch>/fixlist.md --curr R/critique.md`,
     and again with `--prev thesis-work/rounds/r<N-1>/<ch>/coldlist.md` when that file
     exists. A recurring finding, and every entry of last round's `unchanged.md`, moves to
     `R/coldlist-todo.md` as a content list (what the passage must say, with numbers and
     their sources), the reason earlier versions failed, and the paragraphs before and
     after it. A passage already in an earlier `coldlist.md` goes to `escalations.md`.
   - Minor findings: list them in `R/summary.md` for the student; writers act on them
     only if the student asks.
5. **Revise.** A new writer per chapter in revise mode with `R/fixlist.md` and
   `R/student-edits.md`, writing its notes to `R/notes.md`. For a chapter with a
   `coldlist-todo.md`, a separate writer in cold-rewrite mode gets that file, `config.md`,
   `plan.md` and `rules/global.md` (never the chapter or the old finding blocks, which
   quote the old wording) and writes three versions per passage to `R/cold.md`.
6. **Guard the revision.**
   - Scope: compare the chapter with `R/start.tex`. Revert any changed passage that no
     finding or `regex:` rule asked for, and any change to a passage in
     `R/student-edits.md`.
   - Conventions and mechanics (changes made for a `regex:` rule, broken references,
     citation commands): rerun `rules_lint.py thesis-work/rules/global.md --apply chapters/<ch>.tex`
     and `latex_check.py main.tex`. Keep the change when the check passes. No judge.
   - Faithfulness fixes and supervisor comments: check faithfulness fixes against the
     paper and rerun `check_numbers.py`. No judge.
   - Prose changes (everything else): run
     `stagnation.py unchanged --critique R/fixlist.md --before R/start.tex --after chapters/<ch>.tex --json`.
     `applied` and `rewritten` results give the pairs (old passage, new passage). Save
     the `unchanged` results that `R/notes.md` did not decline to `R/unchanged.md`. Start
     two judge agents per chapter in one message, each with `references/judge-brief.md`,
     every pair with the paragraph around it, and the facts the passage must convey (from
     the paper's `digest.md` and the finding's Reasoning). The second judge gets each pair
     in the swapped order. Keep a new passage only if it wins with both judges; otherwise
     restore the old one, including when the judges split by position. Save both verdicts
     in `R/judge.md`. The judges use the same rubric in every round, whatever the lens.
   - Cold rewrites: give two judges the old passage and the three versions, in two
     different orders, to rank. Insert the version with the best total rank yourself. If
     the old passage ranks best, keep it and put the passage in `escalations.md`. Record
     each inserted passage in `R/coldlist.md` as a finding block whose Original is the
     new text.
   - Copy the chapter to `R/end.tex`. When `config.md` says `Commits: allowed`, commit it
     as `round <N>: <ch>` (that answer is the student's request to commit).
7. **Tell the student** in a few lines per chapter: fixed, declined, rejected by the
   judges (with finding ids), stuck, escalated, rules added, and the change in long
   sentences and repeated cross-chapter wording. Save the same lines to
   `thesis-work/rounds/r<N>/summary.md`. Then go through the open items in
   `escalations.md`, one per message. Apply what the student approves yourself, check it
   with the scripts, copy each changed chapter to `R/end.tex` again (commit when allowed),
   and mark each item approved, declined or changed.

**Stop** after round 3, or earlier when a critique has no major findings and the checks
are clean, or when the judges reject almost all of a round's prose changes. More rounds
only if the student asks; restart the lens rotation then.

**After the last round,** run the checks once more. Give any remaining faithfulness or
mechanics problem to a new writer in revise mode as its fix list, check it with the
scripts, copy each chapter to `R/end.tex` again, and commit when allowed. Then hand over
to `thesis-consolidate`.

## Introduction and Conclusion

Draft them after the paper chapters have had round 1: one writer each in synthesis mode
(`references/writer-brief.md`), with the chapter files and `plan.md`'s "Introduction
must" or "Conclusion must" as sources, and no paper, each writing its notes to
`thesis-work/rounds/r1/<ch>/notes.md`. Add them to `main.tex` yourself, and save each
draft as `thesis-work/rounds/r1/<ch>/end.tex`; from then on they go through the remaining rounds
like any chapter, except that in steps 2 and 3 their sources are the paper chapters:
`check_numbers.py chapters/<intro>.tex --source chapters/<a>.tex --source chapters/<b>.tex ...`.

## Supervisor comments

Read Word comments with the `docx` skill and PDF comments with the `pdf` skill. Save each
comment as a finding block numbered from F901, quoting the chapter's LaTeX at the
comment's anchor, in `thesis-work/feedback/<YYYY-MM-DD>-<ch>.md`. The next step 4 sorts
them like the critic's findings; in step 6 they skip the judge.

## Red flags

| Thought | Do this instead |
|---|---|
| "It was flagged again, but a small rewording will do it." | Rewording is how it got stuck. Cold rewrite from the content list. |
| "While the writer is in there, it can polish the rest." | Only flagged passages and rule violations change. Collateral edits break text that was right. |
| "A style rule applies everywhere, so the writer can apply it to the paper's sentences." | Only `regex:` rules apply everywhere. Style rules reach a paper sentence through a finding and the judges. |
| "The new version is obviously better, skip the judge." | Judge prose changes in both orders. Models prefer their own text. |
| "The judge tied on the hyphenation fix, so revert it." | Conventions and mechanics are checked by the scripts, not judged. |
| "The judges split by position; I'll pick the better one myself." | A split is not a win. Keep the old passage. |
| "Keep the local findings for next round, just in case." | They are dropped. If it matters beyond this chapter, make it a global rule. |
| "Add a hedge so the critic is satisfied." | Only when the paper's evidence requires it (the seed rule on hedges). |
| "Regenerate global.md cleanly with all the rules." | Edit one block at a time. Regenerating a memory file drops rules. |
| "The student's edit reads worse; the writer can fix it." | The student's text is authoritative. Raise it with them. |
| "One more round will fix it." | After three rounds gains are small and text starts to degrade. Escalate instead. |
