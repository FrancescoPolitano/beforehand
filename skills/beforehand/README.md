# beforehand

![version 1.0.1](https://img.shields.io/badge/version-1.0.1-0969da)
![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-3776ab)
![stdlib only](https://img.shields.io/badge/dependencies-stdlib%20only-2da44e)
![local-first, no telemetry](https://img.shields.io/badge/data-local--first%20%C2%B7%20no%20telemetry-8250df)
![hosts: Code yes, Cowork unverified, Desktop consult-only](https://img.shields.io/badge/hosts-Code%20%E2%9C%93%20%C2%B7%20Cowork%20%28unverified%29%20%C2%B7%20Desktop%20consult--only-57606a)
![tests: 17 suites](https://img.shields.io/badge/tests-17%20suites-2da44e)
![license MIT](https://img.shields.io/badge/license-MIT-656d76)

*evidence-based stakeholder panels*

*Rehearses how specific, known people will react to a document before they see it, from
evidence-labeled profiles built out of the user's own sources. Use it when you hear yourself
saying "build a persona from this transcript", "stress-test this proposal", "how would she
react", "rehearse the call", or "calibrate".*

Get rejected while you can still do something about it. `beforehand` builds a profile of the
specific people who will decide on your document, out of transcripts, emails and notes you
already own, then puts them in a room with the draft before the real room gets it.

The profile is not invented. Every trait carries a label — **Fact**, **Inference**,
**Assumption** — and every Fact carries the verbatim excerpt it came from, the file it came
from, and a date. A deterministic linter opens that file and checks the excerpt is really in
it. A trait that cannot be checked does not get to speak. Where a profile has no evidence on
a question, it says so instead of guessing, and that blind spot is reported as one.

Then it keeps score: every review freezes its predictions before the meeting, and after the
meeting you grade them against what the person actually did.

Everything runs on your machine, on files you control. No backend, no account, no telemetry.

![The beforehand loop: sources feed a persona of labeled, lint-gated claims; the persona is convened in a panel of isolated reviewers alongside a control reviewer; the panel freezes a snapshot of its predictions before the meeting; afterwards, calibrate grades them into precision and coverage and feeds the result back into the persona.](assets/beforehand-loop.svg)

---

## What you get

| Flow | You say | What comes back |
|---|---|---|
| **Authoring** | "build a persona from this transcript" | labeled traits with excerpts, every quote machine-verified, proposed as a diff you accept or reject — never written silently |
| **Review** | "stress-test this proposal before the panel" | one isolated reviewer per person, a dynamics round, weighted synthesis, conflicts, a prioritized fix list, declared blind spots, and the decision functions nobody on the roster represents |
| **Iterative + apply** | "iterate with her until she passes it", "apply the objections" | a stateful reviewer that loops with you; apply mode is off until you name it, keeps an `r0` copy, and logs every edit against the objection that caused it |
| **Regression** | "did v2 answer the timeline objection?" | objections diffed across versions: resolved / persisting / newly introduced |
| **Calibration** | "here's what they actually said", "calibrate" | your predictions graded against reality, one pair at a time, with hit and coverage counts per person |
| **Consult** | "how would she react to a shorter timeline?", "score these answers as he would", "read my self-assessment as my manager will" | evidence-bounded answers, scoring, elicitation, and the assessment block for performance and periodic reviews |
| **Rehearse** | "rehearse the call", "play the budget owner while I present" | a turn-based simulation that cites the section behind every reply, flags a red line the moment you touch it, and answers `[no basis]` rather than improvise a position |

Consults and rehearsals never feed back into a profile. Only sources do, and only with your yes.

---

## Three rules that are never optional

1. **Every claim carries a label and a resolvable source.** A claim you cannot tag has no
   business being in the file.
2. **The lint gate blocks and never edits.** A profile with a fabricated or unparseable Fact
   is kept out of every panel; nothing rewrites it for you.
3. **Profiles change only on your confirmation.** Creation, update, promotion, import: all
   proposals until you say yes.

Everything else is progressive. These three are not.

---

## How it works

### The evidence model

Every claim in a profile carries exactly one label, inline, in the item that makes it.

| Label | Means | Carries |
|---|---|---|
| `Fact` | observed or quoted | the excerpt, a resolvable path, source type, provenance, date |
| `Inference` | deduced from observed behavior | the observation it rests on |
| `Assumption` | your untested belief | nothing — its visibility is the point |

A line from a real profile looks like this:

```
## Judgment criteria
- Reads risk before numbers. (Fact — "send me the risks first, I'll read the rest after",
  ./sources/2026-07-03-call.md, private-communication, machine-transcribed, 2026-07-03)
```

`lint` opens that path and looks for that span. No excerpt is `UNPARSEABLE`; an excerpt that
is not in the file is `NOT FOUND`; both block. An excerpt with a word substituted is
`APPROXIMATE` and warns, naming the words that differ, until it is repaired to the source's
own; a word added or dropped, a changed number, a flipped prefix (`can`/`cannot`) or a swapped
short word (`not`/`now`) is `NOT FOUND`, so an elided quote is written as two excerpts
(`"we ship" and "in March"`). A relative path resolves against the context's `sources_root:`
in `context.md`, never against the folder you happen to run lint from; until that is set, a
relative ref that is not under the context folder reads `UNVERIFIABLE`. Two more axes decide what a source is even
allowed to support: **type** (private communication, public statement, second-hand — a public
post proves what someone professes, not how they judge) and **provenance** (human-authored,
machine-transcribed, post-review). A source written after reading a panel report promotes
nothing: a review that can confirm itself measures nothing.

A section with no evidence reads `- no evidence as of 2026-07-03` and stays that way. Someone
whose red lines nobody has written down is not thereby someone without red lines.

### What we track about a person — and what we don't

We track how a person judges and decides. Not who they are, and not what they like.

| Section | The question it answers | What it tells the panel |
|---|---|---|
| **Mandate and incentives** | What are they measured on? What budget or what risk do they own? What does it cost them personally if this document passes, or fails? | What drives them — the strongest single predictor of an objection. It holds the tensions too: *pushes for innovation, is measured on cost* is one person, and both halves are observed. |
| **Judgment criteria** | What do they look at first? What convinces them, and what disqualifies on sight? | The filter they read your document through. |
| **Recurring objections** | What have they objected to before, and in whose words? | The repertoire. Someone who objected to a thing once tends to object to it again. |
| **Red lines** | What have they declared non-negotiable? | An objection can be negotiated. A red line ends the conversation, which is why it outranks the weighted synthesis. |
| **Language and dissent style** | How does disagreement actually surface — head-on, as silence, through a delegate, as an innocent question? Which phrases are theirs? | How to recognise an objection that arrives sideways: in the room, or two days later by email. |
| **Panel dynamics** | Whom do they defer to? Whom do they clash with? | How they move in a room, which is not how they read alone. |

Four more sections sit around those six. **Background and track record** is optional and earns
its place only by explaining a criterion. **Watchlist** is the anteroom: something seen once,
not yet a trait, promoted into the body when it repeats. **Reliability** is how this profile's
own predictions have scored so far — a short record `calibrate` maintains, not an
evidence-tagged claim like the rest. **Evidence freshness** is the note that records how
fast each of the six ages. The frontmatter adds `decision_function`, `decision_weight`
and `cares_about` — the fields that decide who gets convened for a given document. Every claim in
the six sections above, and in Background and Watchlist, carries its label: a Fact with a verifiable excerpt and the source
it came from, an Inference with the observation under it, an Assumption declared as an
Assumption. And each section ages at its own speed, which the template marks: mandate and panel
dynamics are rewritten by a reorganisation; a dissent style can go twenty years without moving.

**What we deliberately do not track.** Tastes. Personality. Big-Five-style traits.
Demographics. Private life. "What they like", in general. Admission is a double filter: a trait
has to be labelable against evidence *and* useful for predicting an objection or weighing a
verdict. Something with no source gets in only as an Assumption, visible as one; something
perfectly documented that predicts nothing does not get in at all. That selectivity is the
difference between this and role prompting — and it is what lets "nothing I know about this
person answers that" be an honest answer when a document touches ground nobody has observed.

### The panel

Each person is reviewed by their own reviewer, and the isolation is staged, not promised: the
profile (with its reliability history stripped) and the document are copied into an empty
directory and those are the only paths the reviewer gets. Reading anything else means leaving
the directory. Where the host supports it, the reviewer also runs with file-reading tools only.
Every report and every snapshot row records which shape was used —
`enforced-tools | staged | inline | emulated` — so a weak run is visible rather than averaged in.

Reviewers return a fenced JSON block. `panel --validate` checks its schema; `panel --aggregate`
builds six sections: the objections table, the red-line violations, the conflict candidates
(two objections anchored to overlapping quotes), the blind-spot list, the criteria table and
the method counts. The narrative synthesis stays the model's work; the arithmetic does not.

The reviewer answers every judgment criterion of its persona with a verdict and, for a
criterion it calls met, the passage of the document body it rests on; `panel --document`
rewrites to `declared` any met whose only support is a heading, a table header, a field title
or a metadata line. That is the difference between a document that says "Risks" and one that
states the risk, and it is the reviewer's block that is left alone: the rewrite happens in the
aggregate only. The iterative loop stops on `greenlight: YES` only when no criterion of that
persona still reads `declared`.

Alongside each reviewer runs a **control reviewer**: same document, same isolation, but its
profile is a stub with a role, a decision function and one sentence — *you have no other
information about this person*. An objection the control also raises is marked
`role-generic: yes`. That is the honest part of the measurement: it separates what the evidence
bought you from what any competent reader would have said anyway. On by default for rosters of
five or fewer.

One more gate: a person convened from a context that is not the document's audience — whoever
approves the document on your side — forms an **Approver gate** ahead of the synthesis, and
that section blocks regardless of weight.

### What a review looks like

`panel --aggregate` on the shipped golden fixtures, trimmed. Three people, one draft; the
prose around it is the model's, the counting is not:

```
control: yes

## Round-1 objections
| Persona | Context | Isolation | Anchor in the document | Objection | Severity | Round tag | Event | Role-generic | Doc changed |
|---|---|---|---|---|---|---|---|---|---|
| cfo-astrid | golden | enforced-tools | "Three-year term with an annual break clause" | A three-year term is exactly the length I do not sign without the break clause written into the contract, not into a brief. | 5 | r1 | ? | yes | ? |
| cfo-astrid | golden | enforced-tools | "Phased rollout starting with one depot" | One depot first means the savings case rests on a sample of one. Name the baseline the phase is measured against. | 3 | r1 | ? | no | ? |
| coo-mira | golden | inline | "Dispatch confirmations for depot drivers" | Confirmations that need a signal at the depot gate will not be used on the floor. That is the part the drivers abandon first. | 3 | r1 | ? | no | ? |
| cto-jonas | golden | staged | "Single sign-on for all users at go-live" | At go-live means the identity work sits on the critical path with no rollback story. […] | 4 | r1 | ? | no | ? |
(Event and Doc changed are marked `?`: the aggregator cannot fill them.)
(Role-generic carries the control round's verdict: the rows it only proposed, and that no override has confirmed, are listed in Method counts — confirm those, do not edit the table.)

## Red-line violations
| Persona | Context | Anchor in the document | Objection | Severity | Grounds |
|---|---|---|---|---|---|
| cfo-astrid | golden | "Three-year term with an annual break clause" | A three-year term is exactly the length I do not sign without the break clause written into the contract, not into a brief. | 5 | Red lines |

## Shared anchors
| Persona A | Persona B | Overlap | Anchor A | Anchor B |
|---|---|---|---|---|
| cfo-astrid | cto-jonas | 100% | "Three-year term with an annual break clause" | "term with an annual break clause" |
(A shared anchor is a candidate conflict or a candidate agreement; which one it is, is yours to adjudicate.)

## Blind spots
- cfo-astrid
  - Offline fallback behaviour during an outage
- coo-mira
  - Three-year term with an annual break clause
- cto-jonas
  - Reporting rollup for depot supervisors

## Criteria
| Persona | Context | Criterion | Verdict | Evidence | Evidence check |
|---|---|---|---|---|---|
| cfo-astrid | golden | Wants the downside before the upside | unmet | "Phased rollout starting with one depot" | unchecked |
| cfo-astrid | golden | Refuses savings claims without a named baseline | not-addressed |  | unchecked |
| coo-mira | golden | Checks offline capability for a shift before anything else | unmet | "Dispatch confirmations for depot drivers" | unchecked |
| cto-jonas | golden | Wants the rollback plan before the feature list | not-addressed |  | unchecked |
| cto-jonas | golden | Weighs integration effort over license cost | met | "Single sign-on for all users at go-live" | unchecked |
(Evidence check reads `unchecked` throughout: no `--document` was given, so no quote was looked up and no verdict was forced.)

## Method counts
| Persona | Context | Objections | Mean severity | Greenlight | Isolation |
|---|---|---|---|---|---|
| cfo-astrid | golden | 3 | 4.0 | NO | enforced-tools |
| coo-mira | golden | 1 | 3.0 | INSUFFICIENT_BASIS | inline |
| cto-jonas | golden | 2 | 3.0 | NO | staged |
control objections: 4 (cfo-astrid 2, coo-mira 0, cto-jonas 2)
role-generic proposed, unconfirmed: cfo-astrid#1, cfo-astrid#2, cfo-astrid#3, coo-mira#1, cto-jonas#1, cto-jonas#2
criteria: cfo-astrid returned 2 rows for 2 items under ## Judgment criteria
criteria: coo-mira returned 1 rows for 1 items under ## Judgment criteria
criteria: cto-jonas returned 2 rows for 2 items under ## Judgment criteria
```

`[…]` marks a sentence cut for length; rows were dropped, no cell was edited.

The severity-5 row is a red line, so it blocks whatever the weighted synthesis says. The
100%-overlap pair is handed back as a candidate conflict, not resolved for you. And the
`role-generic: yes` row is the one any careful reader would have raised without knowing this
person at all — which is exactly the row the evidence does not get credit for, once you confirm
the verdict: every role-generic call the control proposes is listed as unconfirmed until you
say so.

The Criteria table is the same review read the other way round — one row per judgment
criterion the profile carries, so a criterion nobody addressed shows up as `not-addressed`
instead of as silence — and the `criteria:` lines under Method counts state, per person, how
many rows came back against how many criteria the file holds, because a reviewer that answered
four of six criteria has told you nothing about the other two.

### The calibration loop

```
review  →  snapshot frozen (predictions + document hash, before the meeting)
              ↓
          the meeting happens
              ↓
doctor  →  "1 snapshot overdue"        you paste what was actually said
              ↓
          pairing proposed, you confirm every single pair
              ↓
calibrate  →  hits (exact / substantive / loose), misses by class, objections not
              raised (mitigated or not), overruled ones, the green-light table, the
              predictions ledger, the criteria ledger, precision and coverage, and the
              rate restricted to objections the control reviewer did *not* raise
```

Under five graded cycles per person it prints counts and `n too small to interpret`, never a
percentage. Every rate counts exact and substantive matches as hits and prints the
loose-inclusive figure beside it as the upper bound, and a person's coverage is measured on
the objections that person actually raised: a row that catches a colleague's objection earns
precision for its own persona and coverage for the colleague.

A miss is not one thing, so the report splits it three ways on `misses by class:`. `new` is
the default and the only one that indicts the profile: nothing in it anticipated the
objection, and it points at a thin section. `known` is an objection the profile already
carried and the panel did not list for this document — a miss of the panel's reading, never
counted in the attributable column. `blind spot` was declared before the meeting and points
at `## Wanted` in `context.md`. The tag set is closed: an unrecognised tag stops the run
rather than reading as a plain miss.

The predictions ledger is split three ways too — by `source flow`, by the optional
`source type:` a prediction row states, and by the grounding section it names — so it is
visible whether the predictions that land come from red lines, judgment criteria or stated
priorities. A row that states no source type reads `unknown`, and `unknown n/n` is always
printed: a snapshot frozen before the field existed says so instead of being guessed at. And
the review's judgment criteria are graded apart, counts only and never a rate: a criterion the
snapshot accepted by declaration that the meeting then raised anyway reads
`miss (criterion present, accepted by declaration)` and points at the review process, while
one no profile row carries points at its `## Judgment criteria`.

The meeting date has one writer: `beforehand.py pending --context <ctx> --set-meeting <doc>
YYYY-MM-DD`. A date that moves keeps the date it replaced on a `meeting moved:` line under it,
one per move, never deleted.

A snapshot frozen before the 0.2 shape existed is not migrated: it is graded through a
reconstructed ledger written beside it (`calibrate --ledger`), and every such cycle says so —
in a warning, in the log entry and in the limits paragraph. A ledger written after the
meeting is transcription, not pre-registration, and nothing in the accounting can tell one
written to fit the outcome from one written honestly.

---

## Install

The full instructions, with what each route prints and refuses, are in the repository README
(`https://github.com/FrancescoPolitano/beforehand`). In short:

**Claude Code** — as a plugin, or with the `beforehand` command line (it copies the skill to
`~/.claude/skills/beforehand` and the reviewer agent to `~/.claude/agents/`, never symlinks,
and refuses to write through a symlink; `--update` upgrades, `uninstall` removes only what it
wrote):

```bash
claude plugin marketplace add FrancescoPolitano/beforehand
claude plugin install beforehand@beforehand
# or
uvx --from git+https://github.com/FrancescoPolitano/beforehand beforehand install
```

**Claude Cowork** — expected to work, not yet verified end to end. Install
`beforehand-1.0.1.skill` from the repository's Releases page (or build it with
`uvx --from git+https://github.com/FrancescoPolitano/beforehand beforehand bundle`) the way the
host installs a skill, then point the store at a folder you keep:

```bash
export BEFOREHAND_STORE="<a folder you choose, outside any repository>"
```

**Claude Desktop** — consult only. The filesystem is ephemeral, so there is no store to keep;
you can hand it a profile in the conversation and ask questions about a document, and nothing
persists between sessions.

**Development** — symlink the skill from a clone: `ln -s "$PWD/skills/beforehand"
~/.claude/skills/beforehand`.

## Quickstart

```bash
# 1. put the source on disk, intact, with its provenance header
python3 $SKILL/scripts/beforehand.py save --dir ./sources --date 2026-07-03 --what call-of-3-july \
  --ref "call of 3 July" --type private-communication --provenance machine-transcribed < transcript.txt

# 2. settle who actually speaks in it, and how much, before extracting anything
python3 $SKILL/scripts/beforehand.py speakers ./sources/2026-07-03-call-of-3-july.md

# 3. one read-only diagnosis of the context you are about to work in
python3 $SKILL/scripts/beforehand.py doctor --context halden
```

Then, in the session:

> build a persona for halden from ./sources/2026-07-03-call-of-3-july.md

You get a proposed file, every Fact tagged and lint-checked, and a `solid / adequate / thin`
verdict on what it rests on. Accept it, then:

> stress-test ./proposal.md for halden

The panel convenes, the report lands in the store, and a snapshot is frozen with the document's
hash and the date of the meeting you are heading into. `$SKILL` is the skill directory; the
store is `~/.beforehand` unless `--store` or `BEFOREHAND_STORE` says otherwise, and it is never
inside a repository.

---

## Commands

Everything runs as `python3 $SKILL/scripts/beforehand.py <command>`. Stdlib only, offline,
deterministic. `--help` on any command lists its flags and exit codes.

| Command | What it does |
|---|---|
| `lint` | check every Fact excerpt against the source it cites; the panel gate |
| `save` | copy a source to disk byte-for-byte with a provenance header and a hash; `--keep-extension` keeps the source's own extension |
| `reindex` | rebuild the derived index files from the profiles themselves |
| `pending` | prediction snapshots awaiting a meeting, and the overdue ones; `--set-meeting` is the one writer of the meeting date |
| `speakers` | who speaks in a multi-voice source, how much, and whose turns are unsafe; `--map` declares who a label is, including a whole room |
| `coverage` | how much independent material a profile rests on: solid, adequate, thin |
| `watchlist` | list single-occurrence entries; promote one into the body, with a diff |
| `calibrate` | grade a frozen snapshot against what actually happened; `--ledger` grades one frozen before the 0.2 shape existed |
| `panel` | validate a reviewer's JSON block; aggregate a round; `--document` checks each criterion's evidence against the document |
| `doctor` | one read-only health check of a context; run it at the start of every flow |
| `migrate` | move a store or a profile to a newer schema, diff first |
| `forget` | remove one person from the store, everywhere, audited |
| `log` | append one line per flow and per offer to the local usage log |
| `test` | run every test suite and the benchmark |

A few of those deserve a sentence more than a table cell.

**`speakers` and the shared microphone.** A named label is not the same thing as one voice: a
conference room arrives as one name. `speakers` prints a `POSSIBLE SHARED MICROPHONE.` block
when the text carries clues of it (a turn that names its own label, a turn that answers the
label's own question, a short turn between two long ones), and those are clues only — nothing
there changes an exit code and a clean run is not evidence of a single voice. Expect the block
often rather than rarely: a legitimate call where a presenter self-answers across split turns
trips it, which is the price of a check that cannot be wrong in the other direction. When you
have confirmed the room, record it in your words with
`--map "<label>=room: <who speaks>, <N> present"`: the roster, the AUDIT fragment and the head
of `--speaker` output all carry the declaration, and the turns you still have to place are
marked `[room?]`.

**`save` and the name it writes.** `save` writes `<date>-<slug>.md`: the saved copy is a
markdown-framed record whose body is byte-faithful, so `(date, slug)` is the identity the
no-overwrite check and the `--seq` dedupe see — the same text saved on stdin and again with
`--from notes.txt` is one file, not two. `--keep-extension` keeps the `--from` file's extension
instead. With `--from FILE` and no `--ref`, the header's `source_ref` defaults to the source
file's own name.

**`watchlist --promote` and the anteroom clause.** Promoting an entry drops the anteroom's
"what would change if it repeats" clause from the promoted line and keeps it in the
Watchlist's own promotion record instead; use `--note` for wording that belongs in the body.

**`forget` and its exit codes.** A mistyped `--context` is answered as a usage error
(`usage: context not found: <ctx>`), never as "that slug is not here": the only exit code that
means the store never held the person is 2. A snapshot that a reconstructed ledger pins by
`snapshot sha1:` is never edited — its lines naming the person are reported `LEFT` for you to
handle — because an edit would stop that cycle grading.

**`doctor` and its last line.** `doctor: healthy` is never printed over a check that could not
run: a lint or a coverage check that raised is listed as a gap with the exception text, the
same as a lint that failed, and a snapshot scan that crashed or skipped an unreadable file is
an item too. The line carries its denominator — `doctor: healthy (12 of 14 personas checked)`
— so a green light cannot stand in for a check that never ran. And before any persona is
linted, the linter is run on a canary that holds one quote its source contains and one it
does not, through the same call the real personas take: if it does not answer `VERIFIED`
then `NOT FOUND`, the linter itself is reported broken and the count reads 0 of N.

## Host support

| Host | Support |
|---|---|
| Claude Code | full — enforced isolation via `agents/`, local store |
| Claude Cowork | expected to work, not yet verified end to end (no install was reachable from the build machine); isolation staged or inline; set `BEFOREHAND_STORE` to a folder you choose |
| Claude Desktop | not supported for the store (ephemeral filesystem); consult only on files provided in the conversation |

Where the store path is not writable, the skill says which host limitation applies and
stops; it never pretends the store persisted.

---

## Responsible use

A persona file is a judgment about a real, identifiable person, written from material about
them and kept on your machine. That makes you its controller, and these five rules part of
using the skill at all.

- **Hold only material you are entitled to hold.** Your own correspondence and meeting
  notes, recordings the participants know about, things the person published. Not material
  obtained without authorisation, and not a copy of someone else's private archive.
- **Keep the public and the private apart.** The evidence model already separates a public
  statement from a private communication, and a Fact from an Inference. Those labels travel
  with every line: they are what lets a reader see, later, on what footing a claim was made.
- **Update and delete on request.** If the person asks what you hold, the dossier is a
  readable file you can show them; if they ask you to correct it, correct it; if they ask you
  to remove it, `beforehand.py forget <slug>` removes the dossier and every structured row that
  names them — audit, snapshots, pairings, calibration log, usage log — reports any prose
  mention it will not rewrite, and any line in a ledger-pinned snapshot it will not edit, so
  you can edit that sentence yourself, and never touches the raw material you saved in your
  own folders. It records that the removal happened.
- **Store it where the machine protects it.** An encrypted volume where your platform offers
  one, and a path outside any repository or shared folder. The store is plain text by design,
  so its confidentiality is the filesystem's, not the format's.
- **Simulate the person, never speak for them.** A persona is an instrument for anticipating
  an audience's objections, not a mouth: nothing it produces is a quotation of what the
  person said, and nothing it predicts is evidence of what they will do.

## Honest limits

Calibration here is a longitudinal case study, not a controlled experiment: small n, a single
observer, assisted matching. Every calibration output says so, and below five cycles it refuses
to print a percentage at all. The skill makes no accuracy claim. What it offers is narrower and
checkable: every trait traceable to something a real person actually said, and a record of how
often the panel was right, which an invented profile can never produce.

---

**Where the name comes from.** The only rejection you can still act on is the one that happens
beforehand.

In the repository this skill is built from: `CHANGELOG.md` lists the releases (the history
is in git), `docs/ARCHITECTURE.md` has the three layers — what the scripts guarantee, what
they explicitly do not, and which rules rest on the prompt alone — `CONTRIBUTING.md` has the
gate and the rules that gate every change, and `LICENSE` is MIT. They are not part of this
bundle, which carries only the skill.

All examples and fixtures here are synthetic. Halden Logistics does not exist.
