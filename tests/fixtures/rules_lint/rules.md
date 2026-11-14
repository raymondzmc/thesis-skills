# Global rules

These rules carry decisions from one revision round to the next. Each block
lists these fields:
- Rule: what to do
- Why: the reason

## G7 | notation
- Rule: Write the document-topic distribution as $\theta$ in every chapter.
- Why: $\alpha$ is the Dirichlet prior, so reusing it for topics confuses readers.
- Check: regex:`topic distribution \$\\alpha\$`
- Example: `topic distribution $\alpha$` -> `topic distribution $\theta$`
- Origin: ch4 r1 F2
- Status: active

## G8 | terminology
- Rule: Call the evaluation corpus the benchmark after its first mention.
- Why: Mixing names suggests two different datasets.
- Check: read
- Origin: ch2 r2 F5

## G9 | style
- Rule: Avoid the phrase per document in captions.
- Why: An earlier convention, kept here for history.
- Check: regex:`per document`
- Origin: ch4 r1 F7
- Status: retired

## Notes
Free text under another heading is not part of any rule.
