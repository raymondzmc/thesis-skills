# Seed rules

`rules/global.md` starts from these blocks. The faithfulness rules apply to every thesis.
The structure and style rules are defaults: show them to the student during intake, keep
the ones they want, and add their own house rules in the same format. Renumber from G1 in
the order you keep them.

## Always keep

```
## G1 | faithfulness
- Rule: Every number in a chapter matches the source paper's number for the same configuration (table row, setting, dataset).
- Why: numbers copied from the wrong row or retyped by hand are the most common error examiners catch.
- Check: script:check_numbers
- Origin: seed
- Status: active

## G2 | faithfulness
- Rule: State each result at the strength the paper claims it; when the paper says "matches or exceeds", the chapter says the same.
- Why: a chapter that upgrades "comparable" to "improves" overclaims the published work.
- Check: read
- Origin: seed
- Status: active

## G3 | faithfulness
- Rule: When a table column or summary mixes configurations (best of a grid, different backbones), name the configuration next to each number quoted in the text.
- Why: a best-of-grid number quoted next to one configuration's claim misattributes the result.
- Check: read
- Origin: seed
- Status: active

## G4 | terminology
- Rule: Copy each research question verbatim from thesis-work/plan.md wherever it is stated in full.
- Why: paraphrased RQs drift in meaning between chapters.
- Check: read
- Origin: seed
- Status: active
```

## Defaults to confirm with the student

```
## G5 | citation
- Rule: Use \citep for parenthetical citations and \citet when the authors are part of the sentence.
- Why: one citation style across chapters; a bare \cite renders differently.
- Check: regex:`\\cite\{`
- Origin: seed
- Status: active

## G6 | structure
- Rule: Open each paper-based chapter with one paragraph that places it in the thesis (part, theme, previous chapter), names the RQ it addresses, and states where the paper was published and how the chapter differs from the published version.
- Why: manuscript-based theses are judged on how well the chapters connect.
- Check: read
- Origin: seed
- Status: active

## G7 | structure
- Rule: Give each paper-based chapter a Limitations section, placed the same way in every chapter.
- Why: examiners look for the limits of each contribution in one place.
- Check: read
- Origin: seed
- Status: active

## G8 | style
- Rule: Open each paragraph with its main point, and give each sentence one main claim.
- Why: dense sentences that carry several claims are what makes revised text hard to read.
- Check: read
- Origin: seed
- Status: active

## G9 | style
- Rule: Add a hedge or caveat only when the paper's evidence requires it.
- Why: critique rounds tend to add hedges until the text reads as defensive and heavy.
- Check: read
- Origin: seed
- Status: active
```

Common house rules students ask for (offer them, don't impose them): no em-dashes;
no semicolons; "we" or "I" throughout; US or UK spelling; a fixed spelling for
recurring compounds such as "pre-trained" or "fine-tuning".
