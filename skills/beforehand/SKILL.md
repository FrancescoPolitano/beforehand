---
name: beforehand
description: >
  Rehearses how specific, known people will react to a document before they see it, from
  evidence-labeled profiles built out of the user's own sources. Use it when you hear yourself
  saying "build a persona from this transcript", "stress-test this proposal", "how would she
  react", "rehearse the call", or "calibrate".
---

# beforehand — evidence-based stakeholder panels

Get a document rejected by the people who decide on it *before* they read it. A persona here
is not invented: it is built from labeled evidence in the user's own sources, and its
predictions are calibrated against what the meeting said.

## Three rules that are never optional

- Every claim in a persona carries a label and a resolvable source — `references/evidence-model.md#Labels`, `#Tag contract`.
- The lint gate blocks a persona out of a panel and never edits one — `#Glossary`.
- Personas change only on the user's confirmation — `#Writes and confirmations`.

## Storage

```
<store>/: INDEX.md, usage.jsonl, <ctx>/{context.md, INDEX.md, AUDIT.md, personas/<slug>.md, reviews/, calibration/}
```

- `$SKILL` is the directory containing this SKILL.md; resolve it from the path you loaded this file from.
- Store path: `--store` > `BEFOREHAND_STORE` > `~/.beforehand`, never inside a repository. Infer the context from the request against the root `INDEX.md`, ask when ambiguous; on a new one create the tree and run `reindex`.
- Documents under review are read where they are, sources stay intact local files outside the store — `#Tag contract`, `#Writes and confirmations`.
- If the store path is not writable, say which host limitation applies and stop; never pretend the store persisted.

| Host | Support |
|---|---|
| Claude Code | full — enforced isolation via `agents/`, local store |
| Claude Cowork | unverified; isolation staged or inline; set `BEFOREHAND_STORE` to a folder you choose |
| Claude Desktop | not supported for the store (ephemeral filesystem); consult only on files provided in the conversation |

## Interaction model

1. **Announce in one line before acting**: `beforehand · <flow> · store <store>/<ctx>` — two stakeholder systems can coexist on one machine.
2. **Explicit invocation executes.** A flow runs on a user request or an accepted offer, never because it looks useful.
3. **Offers execute nothing.** Offer in one line, at most once per source or event per session, on four triggers: a source naming an indexed person enters the session, the user reports feedback or an exception about a person, a snapshot is overdue, the user says they rejected or ignored something the panel asked for. Record every offer and its outcome with `python3 $SKILL/scripts/beforehand.py log offer <ctx> --doc <ref> --note offered|accepted|declined` and read the last offers before offering again.
4. **Confirmed mutation.** Every write to a persona (creation, update, promotion, import) is a proposal until the user says yes — `references/evidence-model.md#Writes and confirmations`.
5. **Flow deliverables are written without a further ask** — same anchor.
6. **Bookkeeping closes every flow**: `reindex` after a mutation, one hand-written `AUDIT.md` line per source, one `log` line.

## Hygiene

1. Never roleplay a trait the persona file does not evidence; declare an empty section instead of filling it — `references/evidence-model.md#Empty sections`.
2. Objections are reported, never written into the document under review, except in apply mode where each incorporation is logged — `#Writes and confirmations`, steps in `references/review.md`.
3. A simulated persona sees only its persona file and the document — the isolation rules are in `references/review.md` Step 2.
4. A passing lint is not a founded persona: `coverage` reports `solid` / `adequate` / `thin` and never blocks, so a reader knows what an objection rests on — `#Glossary`.
5. Every calibration output ends with its limits — stated in `references/calibrate.md`.
6. Shipped examples and fixtures are synthetic: material about real people never enters skill files.
7. The panel's own output never returns as evidence: notes written after a review carry `post-review` provenance — `#Post-review`.
8. No sycophancy: objections follow from mandate, incentives and evidence; a persona with no real objection says so.
9. With three or more voices in a source, settle who speaks with `speakers` before extracting: the lint gate cannot see a misattributed turn — `#Provenance`.

## Start every flow with doctor

Run `python3 $SKILL/scripts/beforehand.py doctor --context <ctx>` first and act on what it lists (overdue snapshots are offered for calibration before anything else; an open offer is not re-offered).
It reads only, fixes nothing and always exits 0.

## Flows

| User intent sounds like | Flow | Read |
|---|---|---|
| "build a persona from this transcript", "add what she said yesterday", "import my old stakeholder notes" | Authoring (create / update / import) | `references/authoring.md` |
| "stress-test this proposal before the buying committee", "review this board memo", "apply the objections" | Review | `references/review.md` |
| "re-review the v2", "did the changes answer the timeline objection?" | Regression | `references/regression.md` |
| "here's what they actually said in the meeting", "calibrate", `doctor` reports an overdue snapshot | Calibration | `references/calibrate.md` |
| "how would the CFO read this negotiation agenda?", "score this grant submission as the editor would" | Consult | `references/consult.md` |
| "let me practise the meeting", "rehearse my self-assessment before the performance review" | Rehearse | `references/rehearse.md` |

- **Approver gate**: a persona from a non-primary context blocks regardless of weight; convene one whenever the document goes out in the user's name (`references/review.md`).
- Routing starts from the index files: load a full persona file only for the people convened; `assets/persona-template.md` is the schema.

## Commands

Run every command as `python3 $SKILL/scripts/beforehand.py <command>`; `--help` lists options and exit codes.

| Command | What it does |
|---|---|
| `lint` | check each Fact excerpt against its source; panel gate |
| `save` | save a source intact, with a provenance header |
| `reindex` | rebuild the derived `INDEX.md` files |
| `pending` | prediction snapshots due or overdue |
| `speakers` | who speaks in a multi-voice source; extract one's turns |
| `coverage` | how much material a persona rests on |
| `watchlist` | list Watchlist entries; promote one |
| `calibrate` | grade predictions against the meeting |
| `panel` | validate a reviewer's JSON block; aggregate a round |
| `doctor` | read-only health check of a context |
| `migrate` | move a store or persona to a newer schema |
| `forget` | remove one person's rows, audited |
| `log` | append one line per flow and per offer |
| `test` | run every test suite |

Evidence rules live in `references/evidence-model.md`; read only the reference of the flow you are running.
