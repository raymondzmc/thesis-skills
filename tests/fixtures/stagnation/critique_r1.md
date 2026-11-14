# Critique: chapter 3, round 1

Summary: the method section overstates the speed-up and miscounts corpora.

### F1 | readability | major | local
- Location: chapters/ch3.tex:12
- Original: "The proposed sampler is considerably faster than the baseline because it
  avoids recomputing the full likelihood after every update of the widget counts."
- Fix: "State the speed-up with the measured factor."
- Reasoning: The claim needs the number from Table 2 of the paper.
- Rule: new

### F2 | faithfulness | major | local
- Location: chapters/ch3.tex:20
- Original: `We evaluate on four synthetic corpora drawn from the widget simulator.`
- Fix: "We evaluate on three synthetic corpora drawn from the widget simulator."
- Reasoning: The paper (p. 5, Table 1) lists three corpora, not four.
- Rule: -

Between findings, the critic may leave notes like this one.

### F3 | mechanics | minor | local
- Location: chapters/ch3.tex:31
- Original: "as shown in Section~\ref{sec:setup}"
- Fix: keep
- Reasoning: Checked: the reference resolves.
- Rule: G7

## Global findings

### F4 | argument | minor | global
- Location: chapters/ch3.tex
- Original: "Gadgets are therefore always preferable to widgets in every setting."
- Fix: Qualify the claim to the settings that were tested.
- Reasoning: Only two settings were compared.
- Rule: G12
