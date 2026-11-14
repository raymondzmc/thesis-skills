# thesis-skills

Claude Code skills that help a PhD student turn their published papers into one
coherent LaTeX thesis. They are built for paper-based (manuscript-based) theses, where
most chapters come from a paper, and they also handle the parts no paper covers: the
theme, the introduction, the conclusion and the links between chapters.

| Skill | What it does |
|---|---|
| `thesis-theme` | Asks you about your thesis first, reads your papers, proposes framings from different angles, tests each one against what the papers show, and revises with you until you approve a plan. |
| `thesis-write` | Drafts each chapter from its paper, then runs up to three critique and revision rounds with fresh agents. |
| `thesis-consolidate` | Makes the chapters consistent with each other, with the front matter and with the papers. |
| `thesis-kit` | Shared formats and helper scripts the other three use. |

## How the writing loop avoids getting stuck

- Every round uses new agents: a writer, a critic and a judge. None of them sees earlier
  drafts or earlier critiques.
- The critic's focus rotates: faithfulness to the paper, then the argument, then
  readability. It must quote each problem and give a concrete fix.
- Findings that apply to every chapter (notation, terminology, citation style, recurring
  habits) become **global rules** in `thesis-work/rules/global.md`. That file is the only
  memory kept between rounds. Findings about one chapter go into a fix list for one
  revision and are then dropped.
- A passage flagged twice, or left unchanged by a revision, is rewritten from what it
  has to say (taken from the paper) without showing the writer the old wording.
- A prose revision is kept only if two blind judges prefer it, one for each
  presentation order, without knowing which version is new. Convention and number fixes
  are checked by scripts instead.
- Scripts check every round that the numbers still match the paper, and measure long
  sentences and wording repeated across chapters.

## Install

As a plugin, in Claude Code:

```
/plugin marketplace add raymondzmc/thesis-skills
/plugin install thesis-skills@thesis-skills
```

From a local clone, use the clone's path instead of `raymondzmc/thesis-skills`.

For a single session: `claude --plugin-dir /path/to/thesis-skills`.

Or copy the four folders in `skills/` into your thesis project's `.claude/skills/`. Keep
them together; the three workflow skills load `thesis-kit`.

Requirements: Claude Code, Python 3.9 or later, Poppler (`brew install poppler` or
`apt install poppler-utils`), and a TeX distribution. Optional: Anthropic's `pdf` and
`docx` skills, a humanizer skill for the readability round, and `academic-refchecker`
(Python 3.11 or later) for checking bibliography entries.

## Use

Start from your university's LaTeX template, with its main file named `main.tex` at the
project root. Put each paper in `papers/` as one PDF or as one folder of its LaTeX
source (for example an unzipped Overleaf download). The skills write chapters to
`chapters/` and add them to `main.tex`. Then, in Claude Code, from the project root:

1. "Help me turn my papers into a thesis." This runs `thesis-theme`.
2. "Write the chapters." This runs `thesis-write`.
3. "Consolidate the thesis." This runs `thesis-consolidate`.

Everything the skills keep is in `thesis-work/` (layout in
`skills/thesis-kit/references/formats.md`). Each round keeps start and end copies of
every chapter in `thesis-work/rounds/`, and the skills commit to git only if you allow
it when they ask.

## Academic integrity

You are the author of your thesis. These skills adapt your own published papers and
draft the text that connects them, and you review every change. Check your university's
policy on generative AI and disclose the use of these tools the way it requires; the
intake asks about it. Do not use them to present text as written without assistance.

## Testing

Script tests: `python3 -m unittest discover -s tests`. Scenario tests, with baseline
and with-skill results: `docs/testing.md`.

## Credits

Design ideas come from published work and open-source skills, summarized in
`docs/design.md`: incremental rule updates (ACE), insight extraction (ExpeL),
self-correction studies (Self-Refine and its critics), a fresh reviewer every round
(Research-Reviewer), fix, name the rule, then check everywhere (a dissertation checklist
by JimmyRao), a central claim and a role for each paper (assembling-thesis-by-publication),
one independent review per pass (academic-pdf-translation), and the humanizer skill's
checklist of AI-prose habits.

## License

MIT
