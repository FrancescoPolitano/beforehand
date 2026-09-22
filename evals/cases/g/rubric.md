# Case (g) rubric — do the reviewer examples change the objections? (FR-3.6)

Case (b)'s prompt is run twice against the same flawed document and the same panel: once
with `assets/reviewer-examples.md` as it ships, once with its three example blocks removed.
The examples are pasted inline into the round-1 reviewer prompt, so removing them is the
only difference between the two runs.

This case is **graded by a person**, not by a checker. `check.py` verifies that both
transcripts exist and are structurally usable, prints four measured numbers per run, and
then prints this rubric. Nothing here is an automatic pass or fail: the question is whether
the examples earn their place in the prompt, and that is a judgment about the content of the
objections.

## What the checker measures for you

| Measure | Why it is in the table |
|---|---|
| objections per persona | the examples do not ask for more objections; a large jump either way is worth reading |
| verbatim anchor rate | share of `quote` values that appear word for word in the document — the grounded example is built around an anchor, so this is where its effect should show |
| mean severity | the generic example carries severity 3; a run that collapses onto 3 has copied the example rather than learned from it |
| distinct `grounds` sections | an objection set that names one section for everything is not reading the persona file |

## Grade each run on these five, side by side

1. **Anchoring.** Does each objection quote a sentence that is actually in the document, or
   does it paraphrase the document's gist? Count the paraphrases in each run.
2. **Role-generic content.** How many objections would any person holding that job title
   have written — no persona evidence behind them ("the price is high and should come
   down")? Count them in each run. This is the measure the examples exist for.
3. **Grounding.** Is each objection's `grounds` section one that actually carries the
   evidence the objection rests on? Open the persona file and check three of them per run.
4. **Blind spots.** Does `no_basis` name the parts of the document the persona's file really
   cannot reach, or is it empty in one run and honest in the other?
5. **Invented positions with no number in them.** "I would sign that", "we could live with
   the phase-two scope" — a plausible sentence about something the persona file does not
   reach. The deterministic guard in cases (c) and (d) catches an invented *quantity* and
   nothing else, by construction (`evals/README.md`, "The fabrication guard"), so this is the
   one failure mode that has no checker anywhere in the suite. Read for it here, in both
   runs, against the persona files.

## The verdict to record

Write one of these into `${EVALS_OUT:-~/.beforehand-dev/evals}/<date>/g.md`, with two sentences of reason:

- **examples earn their place** — the examples-off run is measurably more role-generic or
  less anchored, and the difference is visible in the objections themselves, not only in the
  counts. FR-3.6 stands as it is.
- **no measurable difference** — the two runs are equivalent on all five points. Record it;
  the examples are then costing prompt budget for nothing, and that is a finding for the
  next release, not a defect to fix in this one.
- **examples hurt** — the examples-on run copies the example objections, or reuses their
  wording, or anchors on sentences that resemble the examples rather than the document. This
  one is a defect: file it in the maintainer's issue tracker before release.

Run this case on the release candidate, once per release. It costs four reviewer runs.
