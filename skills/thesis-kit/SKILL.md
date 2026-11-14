---
name: thesis-kit
description: Use when thesis-theme, thesis-write or thesis-consolidate says to load it, or when one of its scripts (paper text extraction, PDF page rendering, number checks against a paper, prose metrics, consistency scan, LaTeX checks, rule checks, stagnation checks) must run on a thesis.
---

# Thesis kit

Shared conventions and scripts for `thesis-theme`, `thesis-write` and
`thesis-consolidate`. This skill's base directory is `<kit>` in those skills.

- `references/formats.md`: the `thesis-work/` folder, the global rule block, the finding
  block, and what goes in global rules versus a chapter's fix list.
- `references/reading-papers.md`: getting LaTeX sources, reading PDFs, looking at page
  images, figures, bibliography.
- `references/seed-rules.md`: the rules every thesis starts with.

## Scripts

Python 3.9+, standard library only. Run them from the thesis root with
`python3 <kit>/scripts/<name>.py`; each has `--help` and `--json`. Exit 0 means nothing
found, 1 means problems found, 2 means a usage or environment error (a missing tool is
named in the message). Exceptions: `prose_metrics.py` never exits 1 (it measures);
`paper_text.py` exits 1 when no paper is found or an extraction fails; `render_pages.py`
exits 1 only when `--find` finds nothing.

| Script | Use it to |
|---|---|
| `paper_text.py PAPERS OUT` | extract each paper's text once into `thesis-work/papers/<id>/` |
| `render_pages.py PDF --pages 4 [--crop l,t,w,h]` | render a page or region to PNG (in `thesis-work/pages/`), then open it with Read; `--find PHRASE` gives the PDF page that holds a phrase |
| `check_numbers.py CHAPTER --source SRC` | list numbers in a chapter that do not appear in the paper |
| `prose_metrics.py FILES...` | sentence lengths, long sentences, repeated openers, banned patterns, stock phrases, wording repeated across chapters |
| `consistency_scan.py PATHS...` | spelling and hyphenation variants, acronym definitions, citation commands, paragraphs duplicated across chapters |
| `latex_check.py MAIN [--build] [--list-files]` | undefined references and citations, duplicate labels and bib entries, missing figures, build log problems; `--list-files` prints every file MAIN pulls in |
| `rules_lint.py RULES [--apply CHAPTERS] [--next-id]` | validate `rules/global.md`, find regex rule violations, get the next rule id |
| `stagnation.py parse/recurring/unchanged` | validate a critique, find findings that came back, find revisions that left the wording as it was |

Tools the scripts call when present: Poppler (`pdftotext`, `pdftoppm`, `pdfinfo`;
`brew install poppler` or `apt install poppler-utils`) and a TeX distribution
(`pdflatex`, `bibtex` or `biber`, `latexmk` if installed).

## Working rules for all three skills

- The main session coordinates; writing, critiquing, judging and digesting go to fresh
  agents with the briefs in each skill's `references/`. Start independent agents in one
  message so they run in parallel.
- Ask the student before anything that changes what the thesis claims. Record such items
  in `thesis-work/escalations.md`.
- The student's own edits win. Before each step, compare each chapter with the copy you
  saved at the end of the last step (`thesis-work/rounds/r<N>/<ch>/end.tex`, or
  `git diff` when the project is committed). If the student changed it, keep their
  version and treat their changes as evidence of their style.
- Save copies instead of relying on git: at the start and end of each round, copy each
  chapter to `thesis-work/rounds/r<N>/<ch>/start.tex` and `end.tex`.
- Commits: when `thesis-work/config.md` says `Commits: allowed`, that answer is the
  student's request to commit, so commit without asking again at the end of every round
  (round 0 and the final fixes included), every consolidation category, and every plan
  approval or plan change, staging only the files you edited (never `.aux`, `.log` or the PDF). When it
  says the student commits, or nothing, do not commit.
