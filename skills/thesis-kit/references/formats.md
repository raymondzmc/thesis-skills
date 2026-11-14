# State folder and file formats

All three thesis skills share one state folder, `thesis-work/`, at the root of the
student's thesis project (next to `main.tex`). Copies of each chapter at the start and
end of every round live in it too, so every change can be compared without git. Commit
only when the student allows it in `config.md`.

```
thesis-work/
  config.md                 intake answers: template, rules, limits, voice (thesis-theme writes it)
  plan.md                   approved theme, RQs, parts, chapter map (thesis-theme writes it)
  intake/framing.md         the student's framing and anything they shared (student-lens agent only)
  papers/<id>/
    source.txt              extracted text (paper_text.py); never edited by hand
    source.tex              flattened LaTeX, when the paper came as LaTeX source
    meta.json               id, kind, pages, title, figures
    digest.md               what the paper claims, with page/table pointers (digest brief)
  rules/global.md           THE memory: thesis-wide rules, one block per rule
  framings/                 candidate framings and fit checks (thesis-theme)
  rounds/r<N>/<ch>/
    start.tex, end.tex      the chapter at the start and the end of the round
    student-edits.md        passages the student changed (accumulates across rounds)
    checks.md               script outputs for this round
    critique.md             critic findings for this round
    fixlist.md              local fix list for this round's revision (dropped after it)
    coldlist-todo.md        stuck passages with their content lists
    cold.md                 three versions per stuck passage (cold-rewrite writer)
    coldlist.md             passages inserted from a cold rewrite (new text as Original)
    notes.md                writer's change notes
    judge.md                blind verdicts from the two judges
    unchanged.md            fixes the writer did not make (next round's cold-rewrite input)
    summary.md              minor findings and what the student should know
  rounds/r<N>/summary.md    what happened this round, rules added, escalations
  escalations.md            items only the author can decide, marked approved, declined or changed
  feedback/<date>-<ch>.md   supervisor comments as finding blocks (F901 and up)
  consolidate/<date>/       consolidation inventory and report
  pages/                    PNGs rendered by render_pages.py
```

What carries between rounds as memory: the chapter files themselves and
`rules/global.md`. Nothing else is shown to the next round's agents, except that writers
are told which passages the student wrote (`student-edits.md`) so they leave them alone. `fixlist.md` and `critique.md` stay
on disk only so the coordinator can detect recurring problems.

## Global rule block (`rules/global.md`)

```
## G7 | notation
- Rule: Write the document-topic distribution as $\theta$ in every chapter.
- Why: $\alpha$ is the Dirichlet prior, so reusing it for topics confuses readers.
- Check: regex:`topic distribution \$\\alpha\$`
- Example: `topic distribution $\alpha$` -> `topic distribution $\theta$`
- Origin: ch4 r1 F2
- Status: active
```

- Header `## G<n> | <category>`. Categories: notation, terminology, faithfulness,
  structure, style, citation, formatting, other.
- Required: Rule, Why, Check, Origin. Optional: Example, Status (`active` or `retired`).
- Check is `regex:` plus a backtick-quoted Python regex (a hit is a violation),
  `script:<name>`, or `read` (an agent has to read for it).
- Write the Rule as the thing to do, concretely enough to check. Give the reason in Why.
- Add or retire one block at a time with Edit. Never regenerate the whole file:
  rewriting a memory file in one pass drops rules silently.
- Get the next id with `python3 <kit>/scripts/rules_lint.py thesis-work/rules/global.md --next-id`.
- Budget: at most 40 active rules. Over budget, merge rules that say the same thing or
  retire the least useful one before adding another.

## Finding block (`critique.md`)

```
### F3 | readability | major | local
- Location: chapters/ch4.tex:57
- Original: "exact quote from the chapter"
- Fix: "replacement text" (or a concrete instruction when new content is needed)
- Reasoning: why, citing the paper (page, table, equation) or a rule id
- Rule: G7
```

- Header `### F<n> | <lens> | <severity> | <scope>`.
  - lens: faithfulness, argument, readability, mechanics
  - severity: major (an examiner would object, or the reader is misled or loses the thread)
    or minor (everything else; minor findings go in a one-line-each appendix)
  - scope: `global` when the same problem could occur in any chapter (a convention,
    a recurring habit, a thesis-wide fact); `local` when it is about this chapter only
- Original is an exact quote, so scripts can find it again.
- Rule: the id of the global rule it violates, `new` when it should become one, or `-`.
- Check the format with `python3 <kit>/scripts/stagnation.py parse critique.md`.

## What goes where

| Finding | Goes to | Example |
|---|---|---|
| A convention every chapter must share | global rule | notation for a symbol, "pre-trained" not "pretrained", `\citep` for parenthetical citations, RQ wording copied verbatim |
| A faithfulness trap that can recur | global rule | "quote a number with the configuration of its table row", "say 'matches or exceeds' when the paper does not claim a strict gain" |
| A style habit the critic keeps seeing | global rule | "open a paragraph with its point", "do not start consecutive sentences with 'This'" |
| A fact about one paper | local fix list | "Table 3's headline is the lambda=0.5 row", "the encoder has 12 layers, not 10" |
| A passage that reads badly | local fix list | one bogged-down sentence, a buried result |
| A local finding seen in a second chapter | promote to global | the same wrong-row habit appears in two chapters |
| A judgment call about the thesis's claims | `escalations.md` | whether to call a result an improvement, whether to cut a section |
