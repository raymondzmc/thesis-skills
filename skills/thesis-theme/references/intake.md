# Intake

Ask these one at a time, in this order, and skip any the student has already answered.
Each answer goes into `thesis-work/config.md` in their own words, except the answer to
question 3: save the student's framing and its source as `thesis-work/intake/framing.md`,
together with anything they share (a proposal, slides, supervisor feedback). Only the
student-lens framing agent reads `thesis-work/intake/`.

If the student declines questions, explain in one sentence why three are needed, then ask
questions 1, 3 and 4 together in one numbered message. Ingestion may start once question
1 is answered, since it proposes nothing. Mark the other fields of `config.md` as
`not asked`; ask question 2 before the plan is saved, question 5 before the rules are
seeded, and questions 6 to 8 at hand-off.
For question 2, read the answers from the guidelines they send when they send them.

1. Where are your papers, and which of them go into the thesis?
2. What format does your university require? Ask for the template or class file and the
   graduate school's thesis guidelines. Things to find out: whether a manuscript-based
   (paper-based) thesis is allowed; required front matter (abstract, lay summary,
   preface or statement of co-author contributions, GenAI statement); one bibliography
   or one per chapter; page or word limits. Ask about the university's policy on
   generative AI, so the thesis discloses this tool's use the way the policy requires.
3. Do you have a framing already, even a rough one, from a proposal, a talk, or how your
   supervisor describes your work? Please share the proposal if there is one.
4. Should each paper become one chapter, or should some be merged, split or left out?
   Is there unpublished work to include?
5. Voice and spelling: "we" or "I"; US, UK or Canadian spelling; any house rules (for
   example no em-dashes, no semicolons). Show the defaults in
   `<kit>/references/seed-rules.md` and ask which to keep. Ask them to point to two or
   three paragraphs in their papers that sound most like them; writers use these as the
   voice reference for new text.
6. What would make you wince if this got it wrong?
7. Who else reads the drafts, and how do they give feedback (Overleaf comments, a
   commented PDF, Word)? Is there a deadline?
8. May I commit to git after each step, or will you commit yourself? (If the project is
   not a git repository, offer to run `git init`.)

`config.md` layout:

```
# Thesis config
- Papers: papers/ (list the files that go in)
- Chapters: one per paper | <papers merged, split or left out>; unpublished work: none | <what>
- Template: <class file or Overleaf template>, main file: main.tex
- Thesis type: manuscript-based | integrated | mixed
- Required front matter: ...
- Bibliography: single | per chapter
- Limits: none | <pages or words>
- Voice: we | I; spelling: US | UK | Canadian
- Voice samples: <paper id, page, first words of each paragraph>
- House rules: ...
- GenAI policy: <what the university requires, and where the statement goes>
- Avoid: <what would make them wince>
- Readers and feedback: ...
- Deadline: ...
- Commits: allowed | the student commits
```
