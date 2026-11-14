# Judge brief

Paste this brief into each judge agent's prompt, followed by the passages. Use a
different model from the writer when you can (for example `model: "sonnet"` when the
writer runs on Opus): models favour text written by themselves. Start the two judges of a
chapter in one message; the second gets every pair in the swapped order.

---

You compare versions of passages from a PhD thesis chapter. You are not told which
version is newer or why it changed, and you should not guess.

For each item you get: the paragraph before and after the passage (context), the
versions, and the facts the passage must convey (from the source paper).

Prefer the version a thesis examiner would rather read:

1. It states the facts correctly and completely, with nothing missing and nothing added.
2. It is easier to follow: the point comes first, each sentence carries one claim, terms
   are defined before use.
3. It fits its context: it connects to the sentences before and after it.

Do not prefer a version because it is longer, more hedged or more formal.

**Pairs.** Answer one line per pair: `<pair id>: 1 | 2 | tie - <one sentence why>`.

**Rankings** (several versions of one passage). Answer one line per passage:
`<passage id>: <best> > <next> > ... - <one sentence why the best wins>`.
