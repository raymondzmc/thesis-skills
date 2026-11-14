---
name: thesis-consolidate
description: Use when separately written thesis chapters need to read as one document, when terminology, notation, spelling, acronyms, citation commands or research-question wording differ between chapters, when numbers, venues or method names in the abstract, introduction, preface or conclusion may disagree with the chapters, when background is duplicated across chapters, when cross-references or the build are broken, or before the thesis goes to a supervisor or committee.
---

# Thesis consolidate

## Overview

One pass over the whole thesis that makes the chapters consistent with each other, with
the front and back matter, and with the papers. Scripts go first because they catch what
readers miss (spelling and hyphenation variants, repeated acronym definitions, citation
commands). Fresh agents then read for what needs judgment. Fixes follow, then a build
and a look at the pages.

Core principle: copying errors and mechanical variants are fixed directly. Anything that
changes what the thesis claims waits for the student.

**REQUIRED SUB-SKILL:** load `thesis-kit` first (`<kit>` = its base directory). Write
`<kit>` out as an absolute path in every command and every agent prompt.

If the thesis was not built with `thesis-theme` and `thesis-write` (no `thesis-work/`),
run `paper_text.py papers thesis-work/papers` first, ask the student for the research
questions and core terms and write them to `thesis-work/plan.md` together with the
chapter-to-paper table, and skip `rules_lint.py` until a rules file exists.

## Process

1. **Inventory.** From the thesis root, save every output below to
   `thesis-work/consolidate/<YYYY-MM-DD>/inventory.md`.
   - Files: `python3 <kit>/scripts/latex_check.py main.tex --list-files` lists main.tex
     and every file it `\input`s or `\include`s. The other scanners do not follow
     `\input`, so always pass them that list. Below, FILES stands for
     `$(python3 <kit>/scripts/latex_check.py main.tex --list-files)` written inline in
     the command; do not store the list in a shell variable (zsh would pass it as one
     argument).
   - `python3 <kit>/scripts/latex_check.py main.tex --build` (add `--engine xelatex` or
     `--engine lualatex` when the thesis loads fontspec).
   - `python3 <kit>/scripts/consistency_scan.py FILES`
   - `python3 <kit>/scripts/rules_lint.py thesis-work/rules/global.md --apply FILES`
   - `python3 <kit>/scripts/prose_metrics.py FILES` (wording repeated across chapters,
     repeated openers)
   - Numbers in the front and back matter: for each file F that holds the abstract,
     preface, introduction or conclusion, run
     `python3 <kit>/scripts/check_numbers.py F --all --source chapters/<a>.tex --source chapters/<b>.tex ...`
     with one `--source` per paper chapter, never F itself or a folder that contains it. A match only
     means the number appears in some chapter; the front-matter agent checks that it is
     the same quantity.
   - Numbers in each chapter:
     `python3 <kit>/scripts/check_numbers.py chapters/<ch>.tex --source thesis-work/papers/<paper id>/`
     with one `--source` for each paper in the chapter's "source paper(s)" column of
     `plan.md` (paper ids are the folder names in `thesis-work/papers/`).
   - The scan does not see names inside math (`$F_1$`). Grep each metric, model and
     method name from `plan.md` across FILES.
2. **Reading passes.** Start three fresh agents in one message. Each prompt is the
   paragraph under "Every agent" in `references/briefs.md`, then one of its sections
   (front and back matter, wording and notation, seams), then the paths and the report
   path (`thesis-work/consolidate/<date>/agent-<1|2|3>.md`).
3. **Decide each finding** (you, the coordinator), in one table.
   - **Apply directly:** mechanical variants (use the form a global rule fixes, else the
     form most chapters use), citation commands, broken references and labels, duplicate
     bib entries, and copying errors: a number, name or venue the thesis states
     differently from the paper, where the paper states it for the same configuration.
     Quote the paper's line in the report.
   - **Decisions for the student:** everything else that changes a claim. That includes
     a number no chapter or paper states (a relative gain, an average), a claim's
     strength, a contribution added to or removed from the abstract or conclusion, a
     renamed method, and cutting or moving duplicated background. Do not apply these.
     Record each one in the report and in `thesis-work/escalations.md`.
   - A fix inside a passage listed in any `thesis-work/rounds/*/<ch>/student-edits.md` is a
     decision for the student: they wrote it.
   - Keep acronym definitions in the abstract and at the first use in each chapter, even
     when the scan lists them as repeated: those are read on their own.
   - A new thesis-wide convention: add it to `rules/global.md` as one block.
4. **Apply** the direct fixes in small edits. Run step 1 again and build. Look at every
   page with a problem: `render_pages.py main.pdf --find "<phrase from the source line>"`
   gives the PDF page (page numbers in the LaTeX log are printed labels, not PDF pages),
   then `render_pages.py main.pdf --pages <n>` and open the PNG.
5. **Report** to `thesis-work/consolidate/<date>/report.md` with the layout below. Then go
   through the decisions with the student. Apply only what they approve, run step 1 and
   the build again, and mark each decision approved, declined or changed in the report
   and in `escalations.md`. Then copy each edited chapter to its latest
   `thesis-work/rounds/r<N>/<ch>/end.tex`, so a later `thesis-write` round does not take
   these edits for the student's.

When `thesis-work/config.md` says `Commits: allowed`, commit each category of applied
fixes as its own commit (that answer is the student's request), staging only the files
you edited (never `.aux`, `.log` or the PDF). Otherwise leave the changes uncommitted.

## Report layout

```
# Consolidation report (<date>)
Scope, files, and the state of the checks before and after.

## Applied
| # | Location (before this pass) | Original | Fix | Reasoning (with the paper or rule) |

## Decisions for the student
| # | Location | Original | Proposed fix | Reasoning and evidence |

## Left as is
| # | Location | What the scan or an agent flagged | Why it stays |
```

## Red flags

| Thought | Do this instead |
|---|---|
| "This number looks wrong, I'll change it to match the table." | Check the paper first. The chapter's table may be the wrong one. |
| "The chapter overclaims, I'll soften it." | That changes the claim. List it under decisions for the student, with the evidence. |
| "A rule says so, so I'll restructure every chapter." | Rules fix wording and conventions. Moving sections or cutting text is a decision for the student. |
| "Spelling variants are trivial, skip the scan." | Readers miss them and examiners notice them. Run the scan on FILES. |
| "I'll make the openers match." | Make them consistent in content (role, RQ, publication note) and varied in wording. |
| "The build passed, so references are fine." | Also read the undefined-reference list and the pages showing `??`. |
