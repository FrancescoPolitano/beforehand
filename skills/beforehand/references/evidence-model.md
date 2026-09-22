# Evidence model — the rules every claim in a persona obeys

One norm, one file. Every rule below is stated here and nowhere else in this package:
`SKILL.md`, the flow references and `assets/persona-template.md` cite it by anchor as
`references/evidence-model.md#<heading>`. The flow references carry the steps; this file
carries the rules, so a rule is read once and changed in one place.

## Labels

Every claim in a persona carries exactly one label, inline, in the item that makes the
claim. A claim you cannot tag is a claim you should not write — that is what separates a
persona from an invented profile.

| Label | Meaning | Carries |
|-------|---------|---------|
| **Fact** | Directly observed or quoted | verbatim excerpt in double quotes + resolvable source ref + source type + provenance + date |
| **Inference** | Deduced from observed behavior | the observation it rests on |
| **Assumption** | User's untested belief | nothing — its visibility IS the point |

- **Fact** — directly observed or quoted. It carries the minimal excerpt that supports the
  claim, the source reference (path or URL), the source type, the provenance and a date;
  all five, so that the claim can be re-checked by someone who was not in the room.
- **Inference** — deduced from observed behavior ("asked for the annex twice →
  contract-detail oriented"). It names the observation it rests on, so a reader can
  disagree with the deduction instead of with the person.
- **Assumption** — the user's untested belief, visible for what it is. Assumptions are
  legal and useful; unlabeled assumptions dressed as facts are not.

Attributed decision weight is a claim like any other: it is usually an Inference, and it
should look like one.

## Tag contract

Canonical forms, inline in the item:

```
(Fact — "excerpt", <path>, <type>, <provenance>, <date>)
(Inference — from <observation>)
(Assumption)
```

A Fact tag has five fields. The excerpt is mandatory and sits inside the tag in double
quotes, and the source is a path that is absolute, `~`-anchored, or relative to the
context's `sources_root:` (default: the context folder) — never to the working directory,
so every later audit finds the same file from any shell.

- A Fact without an excerpt is **UNPARSEABLE**: `beforehand.py lint` blocks the persona from
  any panel, because a Fact without a checkable excerpt is indistinguishable from an
  invention the day after.
- An excerpt cited in the item but sitting outside the tag — the quote lands in the
  sentence where the reader needs it and the tag closes the item — is **MISPLACED**: it is
  checked against the source like any other, it warns and never blocks, and `--fix-tags`
  prints the rewrite without applying it. The two cases carry different weight and must
  not share an error message: a warning that fires for a formatting slip is a warning
  nobody reads when it matters.
- An excerpt that matches its source only approximately — a word substituted, never a word
  added or dropped — is **APPROXIMATE**: it warns and never blocks, and the excerpt is
  repaired to the source's words, never accepted as close enough, because a near-quote that
  passes once reads as verbatim at every later audit. MISPLACED is reported first when both
  apply.
- Text in square brackets inside an excerpt is the author's, never evidence: a bracket of
  up to four words (`[the client]`) stands for up to three of the source's words and is
  shown as the author's insertion — exact when it stands for none, APPROXIMATE naming the
  words when it stands for some, and never a match when one of them is shorter than four
  letters or a number, because a bracket that hid "not" or "30" would pass an edited claim
  as the person's words; a longer bracket is read as quoted text and must match.
- An excerpt whose source cannot be opened from here is **UNVERIFIABLE**: it never blocks,
  and every one of them is listed in the proposal with its reason, because a store that
  deliberately keeps no copy of the sources will always produce some.
- A shorthand like "same source" is parsed and discouraged: it survives one edit, not a
  re-audit.
- **One Fact per parenthesis**; a `;` joining two Facts is parsed but reported as
  `joined tags`, with the segments numbered `#n.1`, `#n.2` so the author can find them.
  Joined tags verify correctly and are untidy, never a failure.
- A source must exist as an intact local file before it is extracted from, and the tag
  cites that file: no accent stripping, no clean-up, no summarising on the way in, because
  a normalised copy makes every later re-audit lie. How to save one: `authoring.md`, Step 0.

## Promotions

A Fact born a Fact and a Fact promoted from an Inference must not look identical: the
promotion is recorded inline as

```
(Fact <- Inference <date> via <promoting source> — <source>, <type>, <provenance>, <date>)
```

Ten extra characters, and the day a source turns out to be bad, everything it promoted can
be found by grep.

A promotion is a persona change: proposed, applied on confirmation (#Writes and
confirmations). A `post-review` source promotes nothing (#Post-review), and a second
occurrence from the Watchlist promotes through the script, not by hand (#Watchlist).

## Source type

What channel is it? `private-communication`, `public-statement`, `second-hand`.

- A public statement proves what the person *professes*, not how they judge — a published
  post is posture, a private message is behavior. Flag a persona built predominantly on
  public material: calibration will reveal what it is actually worth.
- A statement about a third person carried inside a source ("A says B will ask about exit
  costs") is `second-hand` for the person they describe, whatever the carrying source's
  type — the author witnessed the telling, not the behavior.

## Provenance

Who actually produced this text, and what had they already read? `human-authored` (a
person wrote it: a message, a chat, notes taken in the room, the user's own account),
`machine-transcribed` (a system produced it: speech recognition, auto-summary),
`post-review` (written after reading a panel review of the same document).

**Determine provenance before labelling anything.** If you cannot tell, ask the user — one
question, and it decides what the whole source may promote. Anything the user calls a call
*transcript* is `machine-transcribed` by default. Two products are worth telling apart,
both machine-transcribed: a **meeting-platform transcript** is near-verbatim (filler
surviving in the text is the tell, and it is the stronger source); **automated meeting
notes** are a rewrite — usable for mandate, criteria and objections, the weakest source
there is for signature phrasing. A file named "minutes" is neither by default — ask. A
transcript recorded after a review of the same document gets one more question — who led
it, and had they read the review (#Post-review).

`machine-transcribed` promotes to Fact like any other source, but such a Fact is never
reproduced as a direct quotation attributed to the person outside the store: inside the
persona it is evidence, in a report or a message it would be putting words in a real
person's mouth.

On a source with three or more voices, establish who speaks **before extracting
anything**, with `beforehand.py speakers` (the procedure is in `authoring.md`): a
misattributed line corrupts two personas at once, one gaining an objection that is not
theirs and the other losing it, while the excerpt is still in the file and the lint gate
passes on both. **Never infer an identity from the content** — that is the invented
attribution this whole model exists to prevent: settle it from outside the file (a
signature, the invitation, the user's own memory), have the user confirm it, declare it
with `--map "<label>=<who>"`, and record in the `AUDIT.md` line what was declared and what
was excluded. If the attribution cannot be settled, drop the turns, or the whole source.

A named label can be a shared microphone — several people in one room behind one name;
the label then attributes nothing by itself: the user's word does, declared with
`--map "<label>=room: <who>, N present"` and recorded in `AUDIT.md`, and a turn under that
label the user cannot place is left out of promotion.

The two axes are orthogonal, and conflating them is the mistake this model exists to
prevent. An auto-transcribed call and the same call written up by hand are both
`private-communication`, and they are not worth the same. Meeting notes, and meeting notes
written by someone who had read that morning the objections the panel predicted, are also
both `private-communication`, and they are not worth the same either.

## Admissibility

A source is not trustworthy in the abstract, only for particular sections. This is the
ceiling, not a floor: nothing here forces a Fact.

| Section | private-communication | public-statement | second-hand |
|---|---|---|---|
| Mandate and incentives | Fact | Inference | Inference |
| Judgment criteria | Fact | Fact | Inference |
| Recurring objections | Fact | Inference | Inference |
| Red lines | Fact | Inference | Inference |
| Language and dissent style | Fact | Inference | not admissible |
| Panel dynamics | Fact | not admissible | Inference |

Provenance applies on top of the table, never against it: `machine-transcribed` promotes
like any other source under the quotation limit of #Provenance, and `post-review` promotes
nothing (#Post-review). The table is about which section a channel may speak to; the
labels remain the author's judgment.

## Empty sections

A section with no evidence is written exactly `- no evidence as of YYYY-MM-DD` and left at
that: the derived index and the coverage check count that form, and a section left blank
is indistinguishable from a section someone forgot.

Never fill one by deducing what the person would probably think — that is the roleplay
this skill exists to prevent, and it is most tempting exactly where evidence is missing. A
persona with no documented red lines is not a person without red lines, it is a person
whose red lines nobody has observed. "No basis to judge" is a valid, reportable answer —
and each one is a declared blind spot: a declared empty section is information, the blind
spot the panel reports and the next authoring pass closes.

## Declared and demonstrated

A judgment criterion is met by what the document's body says, never by what a label says
about it: a heading, a field title, a table header, a metadata line or a bold label that
names the criterion is `declared`, not demonstrated.
A field named like the criterion is not the criterion.
The reviewer answers every criterion with a verdict — `met`, `declared`, `unmet` or
`not-addressed` — and, for `met`, the body passage it rests on, quoted verbatim; a verdict
whose only support sits in such a line is recorded as `declared` by the aggregate, whatever
the reviewer returned.

Rationale: a document names what it intends and demonstrates what it delivers, and the two
diverge exactly where a criterion is expensive to satisfy.

## Post-review

A `post-review` source cannot promote a claim that was already present in the persona
before that review. It can contradict anything and add what is genuinely new.

The writer of those notes had read what the panel predicted: the prediction told them what
to listen for, so they heard it, wrote it down more precisely than the rest, and often in
the panel's own words. A review that can confirm itself measures nothing — the meeting is
trusted to falsify the persona, not to confirm it. The same reasoning removes the
`post-review` note from the Watchlist count (#Watchlist).

The channel is the reader, not the recording. A transcript stays `machine-transcribed`, and
when the person who led the conversation had read the review, the stakeholder's turns that
answer that person's questions on a point the panel raised
confirm at most as a reinforced Inference and promote nothing — a solicited confirmation is
the prediction hearing itself. The same turns contradict with full standing, and whatever the
stakeholder raises unprompted keeps full standing. Whether the lead had read the review is the
user's word, asked once before labelling (#Provenance) and recorded in the `AUDIT.md` line.

## Watchlist

The anteroom of a persona: a claim resting on one occurrence goes to `## Watchlist`, not
into the body. Written into the body it starts driving the panel on a single data point;
left out entirely it evaporates, and the second occurrence weeks later lands on nobody's
memory.

- One entry per line, opened by a stable id:
  `- [wl-NN] **Title.** observation, single source, and what would change if it repeats`.
  The id is what makes the entry addressable: without it a promotion has to find the entry
  by its own text and cut to the next one, and a cut that overshoots takes the following
  heading with it.
- A second occurrence from an independent source promotes the entry into the relevant
  section, through `beforehand.py watchlist <persona> --promote <id> --section <section>`: it prints
  the diff, writes only with `--apply`, and refuses an edit that would drop a Fact tag or a
  heading. Never move an entry by editing the text by hand. The text after the entry's last
  Fact tag — the *what would change* clause — is dropped from the promoted line and kept in
  the promotion record; `--note` is where body wording for the promoted line goes.
- **Independence is a judgment, not a count.** One source is one occurrence, however many
  times the person repeats the claim inside it: someone who returns to a point three times
  in one meeting has said it once, in one room, on one day. A `post-review` note repeating
  what the panel said is not an occurrence at all. The script flags candidates; the user
  confirms.
- Repetition inside a single source is recorded in the entry as intensity, not as a second
  occurrence: three returns to the same point in one meeting signal something a single
  mention does not.
- Entries that never repeat are not deleted on a schedule — they are the record of what was
  watched and did not hold.

## Writes and confirmations

| What is written | Rule | Why |
|---|---|---|
| Persona files (creation, update, label promotion, import, Reliability line) | proposed, then applied only after the user confirms | the personas are the source of truth on judgment, and silent drift there poisons everything downstream — including when calibration makes the correction look obvious |
| Flow deliverables: review report, prediction snapshot, calibration log append, usage-log line | written as part of the flow the user asked for, with no further confirmation | confirmation protects personas, not every file |
| Structured-consult outputs (scores, elicitation gaps, assessments) | written to the user's working directory on request, never in the store, and only if the user asks | they are working material, not evidence: a consult never feeds a persona file |
| `AUDIT.md` | hand-appended, never derived: one line per source ingestion, with the attribution note on a multi-voice source | it is the record of what was ingested and on whose word, which no script can reconstruct afterwards |
| `INDEX.md`, root and per context | derived, never hand-edited: regenerate with `beforehand.py reindex` after every confirmed mutation | the roster must not be able to drift from the files; `context.md` is the only hand-written index input |
| Sources | never stored raw in the store; the persona holds only the minimal excerpt plus its reference | the store is distilled judgment with provenance, not an archive of communications |
| The document under review | read where it is, never copied into the store; changed only in apply mode, on request, with every incorporation logged per objection | the skill reports objections, it does not ghostwrite |

## Glossary

- **Context** — one audience, one folder under the store: the group of people a document
  must convince. Decision weights are relative to one decision and are not comparable
  across contexts.
- **Persona** — one file per person, built to `assets/persona-template.md`, holding labeled
  claims and nothing else.
- **Source** — a written artefact evidence is extracted from, held intact outside the
  store, carrying a source type and a provenance.
- **Excerpt** — the minimal verbatim span of a source that supports one claim, quoted
  inside the tag and checkable against the file.
- **Snapshot** — the prediction record written at review time to `calibration/`, frozen
  before the meeting; `pending-` means awaiting a meeting, `done-` means graded.
- **Event** — one occasion at which the document met its audience: a meeting, a written
  reply, a decision communicated. A snapshot may carry one event per context convened.
- **Cycle** — one snapshot graded against one event; per-persona rates are counted in
  cycles, and below five cycles counts are reported instead of percentages (rules in
  `beforehand.py calibrate --help`).
- **Gradeable row** — a round-1 prediction row of the version actually sent, on an event
  the persona's context attended; later rounds, dynamics endorsements and protected
  passages are context, never counted (rules in `beforehand.py calibrate --help`).
- **Occurrence** — one source carrying one claim; the unit the Watchlist counts
  (#Watchlist).
- **Coverage verdict** — `solid`, `adequate` or `thin`: how much independent material, over
  what span, the persona rests on. It never blocks, and it travels with the persona into
  the index and every report.
- **Lint gate** — the check that every Fact tag parses and every excerpt exists in the
  source it cites. It can only block a persona out of a panel; it never edits one.
- **Offer** — a one-line proposal to run a flow, recorded in the local usage log; an offer
  executes nothing until the user accepts it.
