# Testing

The skills were tested the way a student would use them: fresh headless Claude Code
sessions (`claude -p`, Opus, no user-level plugins or hooks) working in a scratch copy of
a thesis project, first without the skills (baseline) and then with the plugin loaded
(`--plugin-dir`). Fixtures came from a real paper-based thesis in NLP: three published
papers (PDF) and three of the thesis chapters built from them. Fixtures are not part of
this repository.

## Scenarios

| Scenario | Workspace | Prompt |
|---|---|---|
| Theme | three paper PDFs | "I'm a PhD student and my published papers are in papers/. Help me turn them into a coherent PhD thesis: find the overall theme, the research questions, and a chapter plan." |
| Write | one short paper (11 pages) plus the thesis plan, config and seed rules | write the chapter with three critique rounds |
| Consolidate | three chapters plus a short introduction and conclusion, with 12 planted inconsistencies | "make the chapters consistent with each other and with the introduction and conclusion" |

The 12 planted inconsistencies are errors common in paper-based theses: a symbol used for
two quantities, a conclusion number that differs from the chapter table, a number
credited to the wrong configuration, an RQ paraphrased with a different meaning, a
spelling variant ("finetuning"), a UK spelling ("modelling"), a bare `\cite`, a
duplicate bibliography entry under a second key, a broken cross-reference, a paragraph
copied from another chapter, a wrong venue, and a method name that differs between the
overview and the chapter. Three small issues of the same kinds that the copies already contained (two spellings
of one compound, a bare `\cite`, an acronym defined three times) also count.

## Baseline results (no skills)

**Theme.** Answered in one turn without asking a single question, proposed one framing,
treated the three papers as the whole thesis, added a "cross-cutting" research question
no paper answers, and saved nothing.

**Write.** Three rounds, 13 minutes, USD 3.67.

| | round 1 | round 2 | round 3 |
|---|---|---|---|
| sentences kept from the paper | 62% | 8% | 8% |
| mean sentence length (words) | 23.5 | 25.4 | 26.3 |
| sentences over 35 words | 17 | 16 | 19 |
| semicolons | 5 | 17 | 19 |
| words | 2941 | 3023 | 3259 |

Round 2 rewrote 118 of 125 sentences; round 3 kept 92 of 119, and 13 of its 32 changed
sentences were near-copies of the old ones. It changed the paper's equations, table formatting
and claim strength without asking, and wrote 17 "global" rules after one chapter, many
specific to that chapter. For comparison, the student's own chapter keeps 46% of the
paper's sentences.

**Consolidate.** Found 9 of the 12 planted defects (every meaning-level one) but none of
the mechanical ones ("finetuning", "modelling", the bare `\cite`) and none of the three
pre-existing issues. It also changed two claims in the chapters without asking.

## With the skills, round 1

**Theme.** The skill triggered from the student's own words and asked all intake
questions one at a time before proposing anything. It digested the papers, built four
framings in parallel (problem, method, object, and the supervisor's framing), and
fit-checked them; the fit check caught the overclaims the baseline had made ("more
interpretable" for a paper that never measures interpretability, "efficiency" where the
paper only reports sparsity). It revised the chosen framing twice, rerunning the check
each time, raised a real conflict between the plan and the student's upcoming papers,
and wrote `plan.md` only after an explicit yes. The 24 seeded rules passed `rules_lint`.
Cost: USD 8.69 for the whole 11-turn session (the baseline's single answer: USD 0.72).

Problems found and fixed afterwards: the guiding question and RQs grew to 40+ words as
each fit check added a qualifier (now: one question, at most 25 words); every framing
agent could read the supervisor's framing (now only the student-lens agent reads it);
"go with your recommendation" counted as approval of a plan the student had not seen
(now the plan text is pasted for approval); a later change of plan would have re-run the
whole skill and re-seeded the rules (now a separate "changing an approved plan" path).

**Consolidate.** 15 of 15 (all 12 planted defects and the 3 pre-existing issues), against
9 of 15 without the skill. It also fixed real issues nobody planted (UK "behaviour" in
one chapter, "F-1" next to "F1", one symbol used for two quantities) and held back the
diversity overclaim as a decision for the student. USD 6.61, 10 minutes (baseline USD
1.59, 3.5 minutes).

Problems found and fixed afterwards: a seed rule worded "end each chapter with a
Limitations section" made it move sections in every chapter (rule reworded, and
restructuring is now a decision for the student); it did not commit, which conflicts with
Claude Code's own default of committing only when asked (the skills now snapshot chapters
and ask once about commits); build files were left in the project; the scanners did not
follow `\include` (now `latex_check.py --list-files` feeds them).

**Write.** Three rounds, 30 minutes, USD 10.54.

| | baseline, final | with skill, round 0 | round 1 | round 2 | round 3 |
|---|---|---|---|---|---|
| mean sentence length (words) | 26.3 | 17.1 | 17.2 | 17.1 | 17.2 |
| sentences over 35 words | 19 | 2 | 3 | 3 | 3 |
| semicolons | 19 | 0 | 0 | 0 | 0 |
| sentences changed by the revision | 118, then 32 | - | 14 | 4 | 18 |
| paper's 4-word phrases kept | 13% | 28% | 27% | 27% | 24% |
| numbers not found in the paper | 3 | | | | 1 (the venue year) |

The revisions stayed targeted and readability held. Content questions (a possible
equation error, a claim stronger than the evidence) were
logged in `escalations.md`, but the draft and round 1 had already changed some of them
in the chapter (see below). Three argument findings that would have changed the claim
about RQ2 were escalated without being applied. The judges kept 2 of 6 argument changes
and 10 of 13 readability changes; two stuck passages were cold-rewritten.

Problems found and fixed afterwards: the draft split and reworded the paper's own
sentences to satisfy the style rules (24-28% of the paper's phrasing kept, against 60%
in the student's own chapter), so style rules now apply only to new text and paper
sentences change only when a rule check or a critique flags them; the draft moved the
paper's appendices into the main text; it corrected the paper's equations and claims
itself instead of asking the student; when the two judges disagreed by position, the
coordinator picked one version instead of keeping the old one. Reviews of the skill text
also found that `stagnation.py unchanged` counted correctly applied small fixes as stuck
(it now reports them as `applied`), and that a judge tie undid convention fixes (those are
now checked by scripts, not judged).

## With the skills, round 2

After the fixes above, each scenario was run again in a fresh workspace.

**Theme**, this time with a student who says "just give me a thesis plan, I don't have
time for a lot of questions". The skill explained why it needed three answers and asked
them in one message. Only the student-lens framing mentions the supervisor's view; the
other three never do. Every research question is one question of 8 to 23 words (the
guiding question in the saved plan: 20). "Go with your recommendation" produced the full
plan text for approval, including a notation section that resolves four symbol clashes
between the papers, and `plan.md` was written only after "yes, save it as approved". It
asked the skipped voice and rules question before seeding 16 rules (lint clean, no
near-duplicates) and committed only after the student allowed it. USD 6.92 for the
session.

**Consolidate.** 15 of 15 again. No sections were moved. The report uses Original / Fix
/ Reasoning tables with locations from before the pass, a before-and-after table for
every check, and visual checks of three rendered pages; 16 changes to claims were left
for the student and logged in `escalations.md`. It still did not commit although
`config.md` allowed it, reasoning that the student had not asked in this request; the
skills now state that the intake answer is that request. USD 7.27, 23 minutes.

**Write.** Three rounds, 47 minutes, USD 10.23.

| | baseline, final | round-1 skill, final | round-2 skill, round 0 | round 1 | round 2 | round 3 | the student's own chapter |
|---|---|---|---|---|---|---|---|
| paper's 4-word phrases kept | 13% | 24% | 68% | 67% | 65% | 62% | 60% |
| mean sentence length (words) | 26.3 | 17.2 | 22.2 | 22.2 | 22.4 | 21.1 | 24.9 |
| sentences over 35 words | 19 | 3 | 16 | 16 | 17 | 12 | 22 |
| semicolons | 19 | 0 | 0 | 0 | 0 | 0 | 4 |
| sentences changed by the revision | 118, then 32 | 14, 4, 18 | - | 7 | 11 | 17 | - |

With style rules kept off the paper's own sentences, the draft keeps the student's
wording at the level of their own chapter, and the readability round still shortens the
long sentences that a critic flagged and the judges accepted. The appendix stayed in its
own file. One stuck passage was cold-rewritten and recorded so a later round can detect
it coming back; minor findings went to the student instead of to writers; 22 decisions
were left in `escalations.md`, the most important being that the test plan gives RQ2 no
chapter that answers it. Every number in the final chapter appears in the paper except
the venue year.
