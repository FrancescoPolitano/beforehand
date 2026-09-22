# Consult flow — ask a persona (or the panel) anything

Input: a question to one persona or the whole panel, with no document under review
("what will she expect from me next quarter?", "how would the budget owner react to a price
increase?"), or a **structured consult**: an artefact the persona is asked to work through
in its own judgment — a list of questions to score for relevance, a set of metrics to react
to, a plan to interrogate for missing requirements. Announce:
`beforehand · consult · store ~/.beforehand/<context>`.

1. **Resolve who is asked** via the context INDEX (aliases included). "The panel" means
   every valid persona; the linter gate applies in its light form — refuse to speak for a
   persona whose file fails `beforehand.py lint <file> --lint`, and say why.
2. **Answer strictly within the persona's evidence.** Cite which section grounds the
   answer ("her red line on multi-year commitments suggests..."). The persona's register
   (Language and dissent style) shapes the voice of the answer.
3. **When the evidence does not cover the question, say exactly that**: "nothing you know
   about me answers that." This is a feature — a persona that answers everything is a
   horoscope. Then, if another persona's file plausibly covers it (Panel dynamics or
   INDEX "cares about"), end with a deferral: "ask cfo-elena — price is her ground."
4. **Free consult is conversational.** No files are written in the store, no prediction
   snapshot is taken: calibration stays anchored to reviews, where predictions are tied to
   a specific document and a specific meeting.

## Structured consult

Same evidence rules, different shape of output.

- **Scoring** ("which of these 60 questions would he find relevant, which would bore
  him"): one row per item — score, the persona section that grounds it, or "no basis". An
  item with no basis gets no score, not a middling one; the count of unscored items is the
  first line of the result.
- **Elicitation interview** ("interview her persona for requirements we have not
  captured"): ask the persona the questions a discovery would ask; every answer cites its
  grounding section; every "nothing I know answers that" is recorded as an **elicitation
  gap** — the real value of the exercise is that list, which becomes the agenda for the
  real person.
- **Reaction to non-documents** (metrics, a plan, a decision): a verdict in the persona's
  voice with grounds, plus the parts it cannot judge.

Where a structured output may be written, and on whose say-so, is stated once in
`references/evidence-model.md#Writes and confirmations`. Whatever that section allows, a
structured consult never feeds the persona file and never creates a snapshot. If a separate
agent runs the persona, the two-file rule of `references/review.md` applies.

A structured consult about a document that has a pending snapshot may append its predictions
to that snapshot's `## Predictions to verify`, numbered from the next free `P<k>`:

```
- P<k> | <persona> | <prediction> | <grounding section> | source flow: consult | specificity: high | low | role-generic: yes | no | source type: private-communication | public-statement | second-hand | mixed
```

(`source type` is the channel the evidence behind the prediction came from: one value when
every Fact the prediction rests on carries it, `mixed` when they differ or the grounding is
Inference or Assumption only; leave the field out and it reads `unknown`. What a channel is
worth is `references/evidence-model.md#Source type`, and calibration is where it stops being
an opinion.) This is the only write a consult makes, and only to the snapshot. A free consult
still writes nothing.

## Structured consult → Assessment

The shape to use when the artefact is a periodic assessment — a self-assessment, a set of
metrics against prior objectives, a promotion case, a progress report — and the question is
how a specific known assessor will read it.

**Inputs.** The artefact itself; the objectives or criteria it is measured against (named in
the artefact, or by the user — when neither names them, ask once, because inventing the
criteria invents the result); and the assessing persona, resolved as in step 1. That persona
usually lives in an internal context, and the rest of the panel is not convened: an assessment
is read by the person who signs it, not by a room.

**Output, in this order.**

1. **What this persona cannot judge**, first and never last. Each part of the artefact the
   file gives no basis to read — an output nobody has observed this person react to, a
   criterion their file never mentions. Reading the list first is what stops the rest from
   being taken for a verdict on the whole artefact.
2. **Per criterion: the likely reading, and what grounds it.** One row per criterion: how this
   persona would read the artefact on it, in their register, with the body passage that
   grounds the reading, quoted (`references/evidence-model.md#Declared and demonstrated`), and
   with the section that carries it
   (Judgment criteria, Mandate and incentives, Recurring objections, Red lines). A criterion the
   evidence does not reach gets `no basis` and no reading — not a neutral one, for the reason
   given once in `references/evidence-model.md#Empty sections`.
3. **The questions this persona would ask.** The questions their documented criteria produce
   against this artefact, each grounded the same way. These are the ones worth having an answer
   for before the meeting, and every one of them is also an elicitation gap if it turns out
   nobody knows how the person would answer it.

**Use note.** This block simulates how a known assessor would read an artefact; it does not
assess the user, and nothing it prints is a rating, a score of a person, or a recommendation
about one. The persona of a colleague obeys every rule the evidence model states for any other
persona — no source, no trait, no inferred temperament — and a persona built out of one
performance conversation is thin evidence about a person, which the coverage verdict says out
loud. Where the assessment is the user's own, the persona speaks only for the assessor; the
user's work is the artefact, never the subject of the simulation.

Close with `python3 $SKILL/scripts/beforehand.py log consult <context> [--doc <artefact>]`.
