# Design notes

## The problem

A PhD student has a folder of published papers and needs one thesis. Three things go
wrong when an agent does this naively (we watched each happen in baseline runs, see
`testing.md`):

1. It proposes a theme straight away, from one angle, without asking the student
   anything, and treats the papers in the folder as the whole thesis.
2. Its write and critique loop rewrites the student's published prose in its own style
   after the first critique, and each later round makes sentences longer and denser
   while the wording settles into the same shape.
3. It changes what the published papers say (equations, bolding, claim strength)
   without asking, and it piles chapter-specific notes into "global" rules.

## Decisions and the evidence behind them

| Decision | Why |
|---|---|
| Intake questions before any proposal; several framings from separate agents; a fit check against paper digests; iterate until the student approves | The theme is the student's. Separate agents per lens keep one framing from anchoring the rest. Graduate-school guidance for paper-based theses asks for an introduction that states the aims and how each paper serves them. |
| Fresh writer, critic and judge agents every round | Self-critique in the same context tends to keep the first answer or make it worse [2, 3, 4]; a judge that shares the writer's context scores its own output higher [5]. |
| Rotating critic lens (faithfulness, argument, readability) | One fixed lens produces the same comments round after round. |
| Critic must quote the passage and give a concrete fix; no generic advice; no extra hedges unless the evidence needs them | Specific feedback is what makes self-refinement work, and generic feedback lowers quality [1]. |
| Revise only flagged passages; revert collateral edits | Later revision rounds break text that was already right. |
| Blind judges in both presentation orders, a different model when possible; keep the old version unless the new one wins both | LLM judges have position and self-preference biases [5]. |
| Passages flagged twice or left unchanged get a cold rewrite from a content list, with three alternatives | Revision loops settle into near-repeats of earlier versions; temperature does not break them; rewriting from the source does. |
| Stop after three rounds, or earlier when nothing major is left | Gains concentrate in the first two or three rounds [1]. |
| Scripts every round: numbers against the paper, rule regex checks, prose metrics, LaTeX checks | LLM reviewers find a minority of known errors; deterministic checks do not drift. |
| Global rules are the only memory; local findings are a one-revision fix list | The student's choice. It also matches editorial style sheets (one running list of decisions for the whole book) and keeps the memory small. |
| Rules are added or retired one block at a time, with ids, a reason, a check and an origin; at most 40 active | Rewriting a memory file in one pass silently drops content ("context collapse" [6]); rule memories work best with small, explicit edit operations [6, 7]; instruction-following degrades as the number of instructions grows. |
| A local finding seen in a second chapter is promoted to global | Promotion on recurrence is how rule-learning systems avoid over-specific rules. |
| Changes to what the thesis claims go to `escalations.md` | Baseline runs "corrected" published equations and claims without asking. |
| The student's edits win and seed candidate rules | Learning from user edits is the most direct signal of their style [8]. |

## What goes where

See the table at the end of `skills/thesis-kit/references/formats.md`.

## Reused pieces

- Anthropic's `pdf` skill (optional) for table extraction and OCR; Poppler for text and
  page rendering; Claude Code's Read tool for viewing PDF pages and PNG crops.
- `check_numbers.py` generalizes a claim checker written for a thesis defence deck: every
  number must trace to its source.
- The faithfulness seed rules cover errors that are common when papers become chapters:
  a number quoted from a different row than the claim, a best-of-grid column treated as
  one configuration, and "improves" where the paper said "matches or exceeds".
- The humanizer skill (MIT) is used, when installed, as the readability round's checklist.
- From academic-pdf-translation (MIT): one independent review per pass with all fixes
  batched, and comparing source and output page images.
- From open-source thesis and writing skills: a central claim and a role for each paper
  (assembling-thesis-by-publication), a fresh reviewer every round (Research-Reviewer),
  fix the sentence, name the rule, then check the whole document (a dissertation
  checklist by JimmyRao).

## References

1. Madaan et al. Self-Refine: Iterative Refinement with Self-Feedback. NeurIPS 2023.
2. Huang et al. Large Language Models Cannot Self-Correct Reasoning Yet. ICLR 2024.
3. Kamoi et al. When Can LLMs Actually Correct Their Own Mistakes? A Critical Survey of
   Self-Correction of LLMs. TACL 2024.
4. Xu et al. Pride and Prejudice: LLM Amplifies Self-Bias in Self-Refinement. ACL 2024.
5. Panickssery et al. LLM Evaluators Recognize and Favor Their Own Generations.
   NeurIPS 2024.
6. Zhang et al. Agentic Context Engineering: Evolving Contexts for Self-Improving
   Language Models (ACE). 2025.
7. Zhao et al. ExpeL: LLM Agents Are Experiential Learners. AAAI 2024.
8. Gao et al. Aligning LLM Agents by Learning Latent Preference from User Edits
   (PRELUDE / CIPHER). NeurIPS 2024.
