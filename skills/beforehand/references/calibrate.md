# Calibration flow — measure the panel against the real meeting

This is the flow that separates this skill from role prompting: predictions were written
down before the meeting; now reality grades them. Announce:
`beforehand · calibration · store ~/.beforehand/<context>`.

The accounting itself is not in this file. It is a script, and the rules it applies are
stated once, in its own `--help`:
`python3 $SKILL/scripts/beforehand.py calibrate --help`. Read it before arguing with a number.

## When it starts

Two ways, and the second matters more than the first:
- the user brings the meeting notes ("here's what they actually said");
- `python3 $SKILL/scripts/beforehand.py doctor --context <ctx>` reports a snapshot whose
  `meeting:` date has passed. Every flow on a context runs `doctor` first and acts on what
  it lists: an overdue snapshot is offered for calibration before anything else — a review
  whose snapshot is never graded is a review that never learns — and an open offer is not
  re-offered. A snapshot with `meeting: unknown` gets one question: when is the meeting?
  Record the answer with
  `python3 $SKILL/scripts/beforehand.py pending --context <ctx> --set-meeting <doc> YYYY-MM-DD`
  rather than by editing the file: the command writes the field once, in the shape the
  accounting reads, and when a date slips it keeps the date it replaced on a `meeting moved:`
  line under it. A date that was overwritten by hand leaves no evidence that it moved, and a
  meeting that moved is exactly the thing a later reader needs to see.

Input: the user's notes on what actually happened, plus the pending snapshot in
`calibration/pending-<doc-name>.md` (ask which document if ambiguous; if no snapshot
exists, say so — there is nothing to calibrate).

## Step 1 — The 2-minute annotation

Offer this template if the user has not annotated yet (keep it this small — if annotating
costs more than two minutes, the loop dies and the whole calibration claim with it). The
`- R<j>` items, the `- greenlight:` items and four of the header lines — `Meeting held:`,
`Attendees:`, `Personas rostered but absent:` and `Grading cut-off:` — are what the script
reads; the rest is for the human reader. Those lines stay in English and in this shape
whatever language the conversation is in:

```
Meeting: <document>, <date>
Meeting held: yes | postponed | replaced by email
Attendees: <who was actually in the room>
Personas rostered but absent: <slugs, or none>
Total distinct objections or reactions raised: N
Grading cut-off: <date>
- R1 | <who> | <objection or reaction, roughly their words> | <on which part of the doc> | channel: <in-meeting | email after | via third party> | actual severity: 1-5
- R2 | ... | date: <date>          <- only when it arrived on its own day
- greenlight: <slug> | observed <yes | no | not observed | not applicable>
Not raised but expected: <anything you were braced for that never came>
Anything the panel asked for that you decided not to do: <list, or none>   <- becomes the report's "User decisions" section
```

Each `Personas rostered but absent:` entry may be a slug or a name, with or without a
trailing `(note)`; one that matches no persona of the snapshot stops the run with
`annotation names an absent persona not in the roster: <entry>`, because an ignored entry
leaves that persona's rows in every denominator. The same holds for a `- greenlight:` slug
(`greenlight names a persona not in the roster: <slug>`), for a repeated `R<j>`
(`duplicate real objection id R<j> in the annotation`, since it would be counted twice) and
for a repeated `P<k>` in the snapshot (`duplicate prediction id P<k> in the snapshot`, since
the pairing could not say which one it means).

Save it as a dated notes file in the working directory (authoring Step 0): it is a source,
and it will be cited. Ask the "anything you decided not to do" question once — without it
the accounting cannot tell a wrong prediction from an overruled one.

## Step 2 — Propose the pairing, wait for confirmation

Write `calibration/pairing-<doc-name>.md` as a **proposal**, show it in full, and change
nothing until the user has confirmed it line by line. **Matching is never automatic.** Use
each persona's *Language and dissent style* signature phrases to catch oblique arrivals: a
question about who else runs this at their volume may be the predicted cost objection
wearing its meeting clothes.

```
<key> | R<j> | exact | substantive | loose | related | <why the anchor moved, if substantive>
unmatched real: R<j>, R<j> (blind spot), R<j> (known), R<j> (new)
overruled: <key> | YYYY-MM-DD
criterion: R<j> | <slug>#c<n>
criterion: R<j> | absent
```

`<key>` is `<slug>#<n>` for the n-th `## Round-1 objections` row of that persona (counting
from 1, the same key `panel` takes for its overrides) and `P<k>` for a
`## Predictions to verify` item. The four strengths, `related`, the unmatched tags and the
date gate on `overruled:` are defined in `calibrate --help`.

**The unmatched tag says which kind of miss it is**, and the set is closed —
`blind spot | known | new`, with an untagged `R<j>` reading `new`. Ask the question out loud
for each one: is this something the persona already carries and the panel did not list for
this document (`known` — a miss of the panel's reading, never counted against the persona),
something declared before the meeting (`blind spot`, pointing at `## Wanted`), or something
nothing in the persona anticipated (`new`, pointing at a thin section)? Any other tag stops
the run: until 0.3 it was silently a plain miss, which put a known objection in the one
column meant to indict the persona.

**The `criterion:` line** is for a real objection that lands on a judgment criterion the
panel already held. `criterion: R<j> | <slug>#c<n>` names the n-th row of that persona in the
snapshot's `## Criteria` section — its own series, so `<slug>#c1` and `<slug>#1` are
unrelated — and `criterion: R<j> | absent` says no persona row carries it. It is graded apart
from the one-to-one matching, so the same `R<j>` may also match a round-1 row. When the
snapshot's verdict for that row was `met`, the real objection reads
`miss (criterion present, accepted by declaration: <key>)` and points at the review process,
not at the persona: the panel held the criterion and accepted the document's own claim to
meet it. `absent` reads `miss (criterion absent from the persona)` and points at that
persona's `## Judgment criteria`. A `#c<n>` the snapshot cannot resolve to exactly one row
stops the run, including the case where the pasted table carries the key twice.

The `criterion:` line refines the outcome; it does not set the class. A real objection whose
criterion the persona already held is still counted under whatever its `unmatched real:` tag
says, and an untagged one counts as `new` — that is, against the persona, in the attributable
column and in its running denominator. So when the criterion was present and the report says
the miss points at the review process, the same `R<j>` should usually also carry `(known)` on
the `unmatched real:` line: the persona did carry the ground. Ask the question, do not assume
it; the two lines answer different ones, and only the tag moves a count.

The four line shapes above are the whole grammar: `overruled:` takes the decision date as
`YYYY-MM-DD` and nothing else. Any other line, an unknown strength, an unknown unmatched tag,
or an `overruled:` date in another form stops the run instead of being skipped — a pairing
line the accounting cannot read would otherwise vanish silently, and a vanished overrule is a
miss that never happened.

Then run the accounting:

```
python3 $SKILL/scripts/beforehand.py calibrate --context <ctx> --doc <doc-name>
python3 $SKILL/scripts/beforehand.py calibrate --context <ctx> --doc <doc-name> --apply
```

Without `--apply` nothing is written: read the tables, fix the pairing if the user
disagrees, run it again. `--apply` appends the `calibration/log.md` entry, prints the
one-line Reliability update per persona as a diff, and renames the snapshot to
`done-<date>-<doc-name>.md` — `pending-` always means "awaiting a meeting", and the
calibrated snapshot stays on file as the study's raw record. A document graded twice on
one day gets `done-<date>-<doc-name>-2.md` (then `-3`, …) and the run prints the name it
used, because a rename over the first record would destroy it. The rename happens first and
the log entry second; if the entry cannot be appended the rename is undone and the command
exits 1 with the reason, so the log never counts a cycle whose record is not on file. Exit 2
means the cycle is not gradeable at all and prints why; do not work around it.

Then record the flow:
`python3 $SKILL/scripts/beforehand.py log calibration <ctx> --doc <doc-name>`.

Every rate counts exact and substantive matches as hits and prints the loose-inclusive
figure beside it as the upper bound, because a thematic match is weaker evidence than a
matched anchor and a single number would hide which kind it was. Coverage reads
`coverage: h/n (… exact+substantive) · loose-inclusive: l/n (upper bound)`; the predictions
ledger reads `ledger rate: h/n (exact+substantive) · loose-inclusive: l/n (upper bound)`, and
each of its splits (`by source flow`, `by source type`, `by grounding section`) reads
`<value> h/n (loose-inclusive l/n)`. Per persona, coverage is that persona's own graded real
objections a round-1 row of any persona matched at exact or substantive, over all of that
persona's own graded real objections, because precision belongs to the row that predicted
and coverage to the person who raised: a row that caught a colleague's objection earns
precision for its persona and coverage for the colleague.

The Reliability diff is a proposal like any other persona edit: show it, apply it only on
the user's confirmation (`references/evidence-model.md#Writes and confirmations`).

## A snapshot in the pre-0.2 prose shape

A snapshot frozen before the 0.2 template existed — prose header lines, no `schema:`, the
predictions as `### P<k> — <title>` blocks — cannot be graded: the accounting reads tables
and bullet rows, and there are none. `pending` and `doctor` report it as
`pre-0.2 format, not gradeable`. It is not migrated: from a prose block a script can recover
the id and the title and nothing else, and the slug, the grounding section, the specificity
and the ISO dates are judgment. Write them, do not guess them.

The way back into the log is a **reconstructed ledger**: a 0.2-shaped file beside the
snapshot, `calibration/ledger-<doc-name>.md`, that you propose in full and the user confirms
line by line, exactly like the pairing. The snapshot itself is never edited — it is the
frozen record, and the ledger is pinned to it by its sha1.

```
reconstructed: YYYY-MM-DD          the day this file was written (after the meeting)
snapshot sha1: <40 hex>            sha1 of calibration/pending-<doc-name>.md as you read it
document: <path>                   transcribed from the prose
sha1: <40 hex>                     the document's, if the prose states it
frozen: YYYY-MM-DD [HH:MM]         required: without it the pre-registration gate cannot run
review date: YYYY-MM-DD            the day the panel ran
meeting: YYYY-MM-DD
control: yes | no                  yes only if the panel ran as a control; it is what
                                   labels the role-generic rate `control` rather than
                                   `estimated`, so a missing line reads as `no`
events:                            optional, and only if the prose names them
- <label> | <ctx> | YYYY-MM-DD
personas: <slug> (<ctx>, updated YYYY-MM-DD), ...
## Round-1 objections
<the 0.2 table, as in references/review.md>
## Green lights
<the 0.2 table, as in references/review.md>
## Criteria
<the 0.2 table, as in references/review.md>   only if the prose carries per-criterion
                                              verdicts; a section left out is no criteria
                                              ledger at all. The heading carries nothing
                                              but the word: an annotation on the heading
                                              line makes the section unreadable
## Applied before sending
<the 0.2 table, as in references/review.md>
## Predictions to verify
- P<k> | <slug> | <prediction, one line> | <grounding section> | source flow: … | specificity: … | role-generic: … | source type: …
```

Transcribe the whole shape even where the prose is thin: with `--ledger` every header field
and every section is read from the ledger and never from the snapshot — `meeting:` and
`frozen:` excepted, where the snapshot's own date wins whenever it parses — so anything left
out counts as zero rather than as unknown (no green lights, no applied edits, `control: no`).

Keep the prose numbering (`P1`…`P12`). A block you cannot turn into a row is left out and
named in prose above the section, never invented. Then:

```
python3 $SKILL/scripts/beforehand.py calibrate --context <ctx> --doc <doc-name> --ledger
python3 $SKILL/scripts/beforehand.py calibrate --context <ctx> --doc <doc-name> --ledger --apply
```

Every such run prints `warning: ledger reconstructed on <date> from a <format> snapshot — the
rows were transcribed after the meeting; the frozen text is calibration/<file> (sha1 <sha1>)`
— `--ledger` is allowed on a 0.2 snapshot too, so the warning names the format it actually
found. The log entry ends with `ledger reconstructed on <date>`, and the limits gain
`; this cycle's ledger was reconstructed after the meeting`. That is the honest limit and it
is not a formality: rows written after the meeting can be written to fit it, and nothing in
the accounting can tell one that was from one that was not. Reconstruct a cycle to get it
into the register, never to improve what it says.

`calibrate` refuses a snapshot file that carries a `reconstructed:` line without `--ledger`,
so a ledger left in the snapshot's place cannot be graded as if it had been frozen before the
meeting. That guard reads one line: a ledger stripped of it grades as an ordinary cycle, and
no check inside the store can see the difference. The store is hand-editable by design — the
scripts make the honest record the easy one, they do not defend it against its own author.

## Step 3 — Persona update proposal

The meeting notes are a source, but **not a source like any other**: ingest them as
`post-review` provenance (`references/evidence-model.md#Post-review`) and run the authoring
**update path** (`references/authoring.md`, Path B) — confirmed / contradicted / new /
watchlist, verified, proposed as one diff. Misses are the most valuable input this skill
ever gets, but read the class before acting on one: a `new` miss usually means a section of
the persona is thin, and the update should say which, and which `## Wanted` stakeholder in
`context.md` would have caught it. A `known` miss and a
`miss (criterion present, accepted by declaration)` change no persona section at all — they
are the panel's reading of this document, and they belong in the review's Method notes.

## Every calibration output ends with its limits

State plainly: small n, single observer, assisted matching — a longitudinal case study,
not a controlled study. This honesty is not a disclaimer to mumble; it is the difference
between a measurement and a marketing claim, and it is part of what this skill is for.
