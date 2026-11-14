# Briefs for thesis-theme agents

Paste the matching section into each agent's prompt, followed by its paths.

## Digest (one agent per paper)

Read one paper in full: `thesis-work/papers/<id>/source.tex` or `source.txt`, and the PDF
pages for tables and figures (Read tool with `pages`). Write
`thesis-work/papers/<id>/digest.md`, under 600 words:

- Citation: title, authors, venue, year, as printed in the paper.
- Problem: two or three sentences, in the paper's words where possible.
- Contributions: as the paper lists them.
- Method: three to five sentences, then the key terms and notation (symbol: meaning).
- Results: each headline result with its number, dataset, configuration and location
  (for example "Table 2, p. 5"), and the claim strength as written ("outperforms",
  "matches or exceeds", "comparable").
- Limitations: those the paper states; then any you see, marked "(digest)".
- Links: which other papers in the folder it cites, extends or shares data with.
- Thesis-level questions it speaks to: one or two, phrased neutrally.

Report facts only. Do not judge the paper's quality.

## Framing (one agent per lens)

You propose one framing of the thesis from the paper digests, through one lens. Other
agents work through other lenses at the same time, so make yours the strongest version of
your lens instead of a compromise.

Lenses (the coordinator gives you one, or a structure the student chose):

- **problem**: what problem do the papers attack together?
- **method**: what kind of technique or approach connects them?
- **object**: what do they study: a model component, a property, a phenomenon?
- **student**: build on the student's own framing from `thesis-work/intake/`.

Inputs: every `digest.md` and `thesis-work/config.md`. Only the student lens also reads
`thesis-work/intake/`; with any other lens, do not open that folder. Write
`thesis-work/framings/<lens>.md` (the coordinator may give a versioned name):

- Working title.
- Guiding question: one question of at most 25 words.
- Two to four research questions, each one question of at most 25 words; where possible
  each one is answered by two or more papers. Put qualifications in the prose around
  them, not inside the questions.
- Central claim: the one sentence the whole thesis argues.
- Parts and chapter order, ordered by the argument rather than by publication date: each
  paper with its chapter, part, RQ, and one sentence on how it answers that RQ, citing
  the digest's result.
- What the Introduction and the Conclusion must synthesize.
- Weakest fit: the paper that fits least, and what the thesis would have to say to hold
  it in.
- Claims beyond the papers: every sentence of the framing that the papers do not
  directly support. Keep the list short.

## Fit check (one agent for all framings)

Test each framing file the coordinator lists against the digests. For each framing:

- Each paper: does its stated role match what its digest says the paper shows? Rate the
  fit strong, adequate or stretched, and quote the evidence.
- Each RQ: which papers answer it. Flag RQs that only one paper answers and RQs that no
  paper fully answers.
- Overclaims: sentences that need evidence the papers do not contain.
- Orphans: papers that answer no RQ.
- A verdict in one paragraph.

Write the fit check to the path the coordinator gives (for example
`thesis-work/framings/fit-check.md`, or `fit-check-v2.md` for a revision) with one section
per framing and a final table: framing | strong | adequate | stretched | orphans |
overclaims.
