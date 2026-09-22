# Persona template

Copy the contents of the fenced block below — the template only, not the synthetic
example further down — into `~/.beforehand/<context>/personas/<slug>.md` and fill it in.
Every claim in the body carries an inline evidence tag: `(Fact — "excerpt", <path>, <type>,
<provenance>, <date>)`, `(Inference — from <observation>)`, or `(Assumption)`.

**Evidence rules — read them there, not here.** What the three labels mean and what each one
must carry: `references/evidence-model.md#Labels`. The canonical tag forms, their fields and
what the linter does with a tag that breaks them: `references/evidence-model.md#Tag contract`.
How a claim promoted from an Inference is recorded:
`references/evidence-model.md#Promotions`. The two axes a source is described on, and which
sections it may speak to: `references/evidence-model.md#Source type`,
`references/evidence-model.md#Provenance`, `references/evidence-model.md#Admissibility`.
They are stated once so that a change to the evidence model does not have to be made twice.

---

```markdown
---
slug: <kebab-case-id>
aliases: [<names and appellations this person appears under in sources>]
role: <title>
organization: <org name>            # optional — omit it when the person is not placed in one
context: <the audience this persona belongs to — an account, a committee, an investor group>
decision_function: <open field; the examples below are not a closed list>
# buying committee: economic buyer, technical evaluator, gatekeeper
# people decisions: manager, hiring panel member, promotion committee
# capital: investor, board member
# negotiation: counterpart lead, counterpart's approver
# review bodies: editor, committee chair
decision_weight: <1-5> # tag it like any claim — attributed weight is usually an Inference
cares_about: [<2-3 hot themes, one line each — drives roster selection and the INDEX line>]
created: <YYYY-MM-DD>
updated: <YYYY-MM-DD>
schema: 0.2 # schema of this file; beforehand.py migrate upgrades it
---
<!-- Frontmatter subset (FR-4.8): only `key: value` scalars, inline lists `[a, b]`, and a
     trailing `# comment` are accepted; a block list (`- item`) or a nested map raises an
     error naming the line instead of being silently dropped. -->

## Mandate and incentives <!-- last evidence: YYYY-MM-DD | decays fast -->
<!-- What they are measured on, budget/risk they own, what this proposal's success or failure
     means for them personally. The strongest objection predictor.
     Optional: an evidenced "Internal tensions" note — real stakeholders are contradictory,
     and tensions predict swing objections. Observed only, never invented. -->

## Judgment criteria <!-- last evidence: YYYY-MM-DD | decays slowly -->
<!-- What they look at first, what convinces them, what disqualifies a proposal. -->

## Recurring objections <!-- last evidence: YYYY-MM-DD | decays slowly -->
<!-- The observed repertoire, each with the evidence that supports it. -->

## Red lines <!-- last evidence: YYYY-MM-DD | decays slowly -->
<!-- Non-negotiables. Distinct from objections: an objection gets negotiated, a red line
     ends the decision against the document. -->

## Language and dissent style <!-- last evidence: YYYY-MM-DD | does not decay -->
<!-- How disagreement shows up: head-on, silence, via a delegate, an innocent-sounding question.
     Prefer verbatim signature phrases quoted from sources (as Fact) over trait adjectives —
     the fingerprint is how calibration recognizes an objection that arrives obliquely. -->

## Panel dynamics <!-- last evidence: YYYY-MM-DD | decays fast -->
<!-- Deference and conflict with other stakeholders: "follows the budget owner on price",
     "rivalry with the committee chair". Fuel for conflict detection during aggregation. -->

## Background and track record (optional)
<!-- Education, career path, formative experiences — admissible under the same evidence rules.
     Its role is explanatory context for judgment criteria; inferences drawn from it enter as
     Inference at most, never as Fact. No invented backstory, no demographic stereotyping. -->

## Watchlist
<!-- The anteroom. Entry form and ids, what counts as an independent second occurrence, and
     how a promotion is made: references/evidence-model.md#Watchlist
     (`beforehand.py watchlist <persona> --assign-ids` numbers entries written before the id
     rule). -->

<!-- EMPTY SECTIONS. The canonical form of a section with no evidence, and why one is never
     filled by deduction: references/evidence-model.md#Empty sections -->

## Reliability
<!-- One line, maintained by the calibrate flow via proposal: "N cycles: X% of objections
     predicted". Full history lives in calibration/log.md. Calibration is offered when the
     `meeting:` date of a pending snapshot passes (`beforehand.py doctor` reports it). -->

## Evidence freshness
<!-- Maintained by authoring. Sections age at very different speeds and one `updated:` date
     on the file hides that:
     - decays fast (mandate and incentives, panel dynamics): a reorg rewrites both overnight.
       The review flow warns when either is older than 6 months.
     - decays slowly (judgment criteria, recurring objections, red lines): warn past 12 months.
     - does not decay (language and dissent style): people argue the same way for decades. -->
```

---

# Synthetic example — do not copy real people into skill materials

*Everything below is invented for illustration. Borealis Freight and its people do not
exist — and this example is deliberately NOT the persona you are building: extract from
the user's sources, never from this file.*

```markdown
---
slug: cfo-ingrid
aliases: [Ingrid, I. Halvorsen, the CFO]
role: Chief Financial Officer
organization: Borealis Freight
context: borealis
decision_function: economic buyer
decision_weight: 5 # (Inference — her sign-off closed every commercial thread in the sources)
cares_about: [cost per shipment, downside quantified first, pilot before any spend above 100k]
created: 2026-05-11
updated: 2026-08-27
schema: 0.2
---

## Mandate and incentives
- Owns fleet-cost reduction for 2026; board reviews her quarterly on cost per shipment
  (Fact — "the board reads one number from me: cost per shipment", ~/work/borealis/sources/2026-05-10-kickoff-notes.txt,
  private-communication, human-authored, 2026-05-10)
- Internal tension: champions the digitalization budget she is also expected to cut
  (Inference — from the same meeting covering both mandates)

## Judgment criteria
- Wants the downside quantified before hearing the upside (Fact — "start with what happens
  if this fails", ~/work/borealis/sources/2026-05-10-kickoff-notes.txt, private-communication,
  human-authored, 2026-05-10)
- Distrusts savings projections without a named baseline (Inference — rejected the previous
  vendor's ROI slide for lacking one)

## Recurring objections
- Implementation effort her own team must absorb (Fact — "your effort estimate never
  includes my people's hours", ~/work/borealis/sources/2026-06-02-email.txt, private-communication,
  human-authored, 2026-06-02)

## Red lines
- No spend above 100k without a pilot phase (Fact — "above one hundred thousand, we pilot
  first, always", ~/work/borealis/sources/2026-05-10-kickoff-notes.txt, private-communication,
  human-authored, 2026-05-10)

## Language and dissent style
- Signature phrase precedes her rejections (Fact — "walk me through the assumption behind that",
  ~/work/borealis/sources/2026-05-10-kickoff-notes.txt, private-communication, human-authored, 2026-05-10)
- Objects in the meeting, directly; a follow-up email from her means agreement, not attack
  (Inference — opposite pattern to most stakeholders; two observed cycles)

## Panel dynamics
- Openly clashes with coo-lars on automation pace; expects proposals to pick a side
  (Inference — from their exchange in the kickoff)

## Background and track record
- Started as a warehouse operations manager before finance (Fact — "started as a warehouse
  operations manager", https://example.invalid/borealis/leadership, public-statement,
  human-authored, 2026-05-01). Explains why implementation effort is her ground
  (Inference).

## Reliability
- 0 cycles: no calibration data yet.
```
