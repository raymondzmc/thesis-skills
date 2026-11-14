---
name: thesis-theme
description: Use when a PhD student wants to turn a folder of their published papers into a thesis and the overall theme, research questions, parts or chapter plan are not settled yet, or when they want to revisit, test or change an existing thesis framing or plan.
---

# Thesis theme

## Overview

Finds, together with the student, the thread that turns separate papers into one thesis.
The theme is theirs to choose. This skill collects what they already think, proposes
framings from several angles, tests each one against what the papers actually show, and
iterates with them until they approve a plan.

Output: `thesis-work/config.md`, `thesis-work/plan.md`, and the first global rules in
`thesis-work/rules/global.md`. If `plan.md` already exists, go to "Changing an approved
plan" below instead.

**REQUIRED SUB-SKILL:** load `thesis-kit` first. It defines the state folder, the rule
format and the scripts. Below, `<kit>` is the thesis-kit base directory (write it out as an
absolute path in commands and agent prompts) and `references/` is this skill's folder.

## Process

1. **Intake before anything else.** Ask the questions in `references/intake.md`, one per
   message, and record the answers as it says. Do not propose a theme, research questions
   or a chapter list during intake, however obvious the papers make it look.
2. **Ingest the papers.** Run `python3 <kit>/scripts/paper_text.py papers thesis-work/papers`
   (see `<kit>/references/reading-papers.md`). If it warns that a paper has no text, or a
   PDF gives fewer than about 100 words per page, it is scanned: OCR it (the `pdf` skill or
   `ocrmypdf`), replace the file in `papers/` under the same name, and rerun with
   `--force`. When every paper has text, start one digest agent per paper, all in one
   message, each with `references/briefs.md` § Digest. Read the digests, not the papers.
3. **Three or four framings, in parallel.** One framing agent per lens (problem, method,
   object), each with § Framing. When intake produced a framing (from the student, their
   supervisor or a proposal), add a fourth agent with the student lens. Only that agent
   reads `thesis-work/intake/`; the others must not see the student's framing, or all of
   them drift toward it.
4. **Fit check.** One new agent tests all framings against the digests (§ Fit check).
5. **Show the student.** One message: a table (framing | guiding question | fit counts |
   weakest paper), your recommendation and why, the paths of the framing files, and one
   question.
   - If every framing leaves the same papers as orphans, say plainly that they are
     separate lines of work, and recommend one way to handle them: leave them out if the
     guidelines allow, two parts with their own RQs joined in the Introduction only by
     links the digests show, or a structure the student suggests. Give the chosen
     structure to one framing agent as its lens and fit-check that file. Record the
     decision in `thesis-work/escalations.md`.
6. **Iterate.** Revise the chosen framing with their feedback (save it as a new version,
   such as `framings/student-v2.md`), fit-check only the new version, and show the result
   the same way: what changed, the fit table, one question. Several rounds are normal.
   Keep the guiding question and each RQ to one question of at most 25 words. Put
   qualifications in the plan's prose, not in the question.
7. **Ask for approval of the plan text.** Settle the notation first: wherever papers use
   different symbols or names for the same thing, choose one with the student. Then paste
   the plan itself (title, central claim, guiding question, RQs, core terms, notation,
   chapter table) and ask whether to save it as approved. A yes to a framing, or "go with
   your recommendation", is not approval of the plan text.
8. **Save the plan and seed the rules**, after that yes. Write `plan.md` in the format
   below. Seed `rules/global.md`: copy the blocks from `<kit>/references/seed-rules.md`
   that the student kept, add one terminology rule and one notation rule that point to the
   Core terms and Notation lines of `plan.md` (Check: read), and a regex rule for each
   banned variant (for example "pretrained" when the plan says "pre-trained"). Check it
   with `python3 <kit>/scripts/rules_lint.py thesis-work/rules/global.md`, then commit
   when `config.md` says `Commits: allowed`.
9. **Hand off.** Ask any intake questions still marked `not asked`. Tell the student that
   `thesis-write` drafts the chapters from this plan.

## plan.md

```
# Thesis plan (approved YYYY-MM-DD)
- Title:
- Central claim: <one sentence the whole thesis argues>
- Guiding question:
- RQ1: <exact wording; chapters copy it verbatim>
- RQ2: ...
- Core terms: <term>: <definition used thesis-wide>
- Notation: <quantity>: <symbol> (replaces <other symbol> in <paper ids>)

## Chapters
| # | id | source paper(s) | part | RQ | role in the thesis (one sentence) | link from the previous chapter |

## Introduction must
## Conclusion must
## Front matter (from config.md)
## Open questions
```

## Changing an approved plan

When `plan.md` exists, read it, `config.md` and the latest `thesis-work/rounds/` first.
Do not repeat intake, digests or framings, and never re-seed `rules/global.md`: it holds
rules learned while writing. Write the changed plan to `framings/plan-r<N>.md`,
fit-check only that file, and show the student the rows that change (the moved chapter,
and the chapters next to its old and new positions). After an explicit yes, edit those
rows in `plan.md` (keep the chapter ids), add `Revised YYYY-MM-DD: <change>` under the
heading, and under that line list the drafted chapters whose opening paragraph or closing
link must change and what each must now say; `thesis-write` reads that list. Move the
chapter's `\include` and `\part` lines in `main.tex` to match, and commit when allowed.

## How to talk with the student

- One question per message. Their own words go into `config.md` and `thesis-work/intake/`.
- Mark your guesses as guesses.
- Recommend one option and say why; do not just list options.
- Give paths to the framing files instead of pasting them; paste the plan text itself
  only for approval.

## Red flags

| Thought | Do this instead |
|---|---|
| "The papers make the theme obvious, I'll propose it now." | Finish intake. The student may have a framing, a supervisor's framing, or papers you have not seen. |
| "One strong framing is enough." | Three lenses, then the fit check. A single framing anchors the student as much as it anchors you. |
| "All the framing agents should know what the supervisor thinks." | Only the student-lens agent reads it. The others must stay independent. |
| "These papers are the whole thesis." | Ask which papers go in and whether unpublished work is included. |
| "A cross-cutting RQ will make it cohesive." | Every RQ needs papers that answer it. List unsupported claims as claims beyond the papers. |
| "They liked the framing, I'll write plan.md." | Paste the plan text and get a yes to that text. |
| "The student wants to move a chapter, I'll rerun the skill." | Follow "Changing an approved plan". Never re-seed the rules. |
