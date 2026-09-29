# beforehand — architecture

The skill is three layers, and the distinction between them is the whole design: the
**data** layer is what is on disk and in which shape; the **tools** layer is what a
deterministic script can guarantee about that data; the **behaviour** layer is every rule
the model must follow, each with the mechanism that actually enforces it. A rule whose
only mechanism is the prompt is not weaker by accident — it is a rule no script can check,
and saying so is the point of the third table.

This page is written from the rules as they stand today, and everything it describes is
built and green in this tree. The last column of the behaviour table is where each rule
lives, and `dev/check_norms.sh` proves that it lives there exactly once.

---

## Layer 1 — Data

Everything the skill owns lives in a store outside any repository (default `~/.beforehand/`,
resolved as `--store` > `BEFOREHAND_STORE` > the default). Judgments about real people must
not be one `git commit` away from a shared remote, so the placement is structural rather
than advisory.

```
<store>/
├── INDEX.md                    DERIVED   one line per context
├── usage.jsonl                 APPEND    flows run, offers made; never leaves the machine
└── <context>/                  one audience
    ├── context.md              SOURCE    description, sources_root, ## Wanted
    ├── INDEX.md                DERIVED   one line per persona, with lint and coverage
    ├── AUDIT.md                APPEND    one hand-written line per source ingestion
    ├── personas/<slug>.md      SOURCE    labeled claims, one file per person
    ├── reviews/                OUTPUT    panel reports
    └── calibration/            OUTPUT    pending-*.md / done-*.md snapshots, log.md,
                                          annotation-*.md, pairing-*.md, ledger-*.md
```

Two kinds of file that are *not* in the store: the **sources** (transcripts, messages,
notes) stay intact in the user's working directory, because the store keeps distilled
judgment with provenance and not an archive of communications; and the **document under
review**, which is read where it is.

| Artefact | Schema marker | Written by | Kind |
|---|---|---|---|
| Persona file | `schema: 0.2` in frontmatter | model, on confirmation | source |
| `context.md` | `schema: 0.2` | model, on confirmation | source |
| `INDEX.md` | `<!-- schema: 0.2 -->`, `<!-- lint root: <path> -->`, `<!-- last regenerated: YYYY-MM-DD -->` only when a persona line changed | `reindex` | derived |
| `AUDIT.md` | `<!-- schema: 0.2 -->` header; the derived-file marker never appears here | model, hand-appended | append-only record |
| Prediction snapshot | `schema: 0.2`, header `control: yes \| no`, per-row `Isolation`, `## Criteria` section, optional per-P-row `source type:` field | review flow | output |
| Saved source | provenance header with sha1 | `save` | input, outside the store |
| `calibration/log.md` | one section per graded cycle | `calibrate` | append-only record |
| `calibration/ledger-<doc>.md` | `reconstructed: YYYY-MM-DD` and `snapshot sha1: <40 hex>`, pinning it to the prose snapshot it was transcribed from | model, on confirmation line by line; read by `calibrate --ledger`, never rewritten by a script | source |
| `meeting moved:` line in a snapshot | `meeting moved: <old \| unknown \| none> -> <new> on <date>`, one line per move, directly under `meeting:` | `pending --set-meeting`; read back as `meeting_history`, never deleted | append-only record |
| `usage.jsonl` | one JSON object per line | `log` | append-only record |

Schema changes are a migration, never an edit in place: `migrate` prints a diff and
refuses any change that would reduce Fact tags or headings.

---

## Layer 2 — Tools

Every command is deterministic, stdlib-only and offline. The second and third columns are
the contract: a guarantee is something the user may rely on without reading the file, and
the "does not" column exists because every one of those absences has, at some point, been
mistaken for a guarantee.

All commands are subcommands of `beforehand.py`; the modules named below stay runnable on
their own for one release.

| Command | Guarantees | Explicitly does **not** guarantee |
|---|---|---|
| `lint` (`verify_quotes.py`) | every Fact tag parses into its five fields; every excerpt is looked up by one matcher whose verdict does not depend on the source's length: exact is a whole-token run of the source, filler words ignored; `APPROXIMATE` is one or more words substituted and none added or dropped, never a negating or other prefix change, a changed number or sign, a swap of a word shorter than four letters, or a cut inside a hyphenated or apostrophised word, and the reason names the substituted words; a short `[bracket]` stands for at most three source words and is named when it stands for any, a longer one must match; a relative source ref resolves against the context's `sources_root:` only (the context folder when unset), never the working directory, and `lint <file>` without `--sources-root` derives that root from the persona's context; `NOT FOUND` and `UNPARSEABLE` block (exit 1), `APPROXIMATE`, `MISPLACED` and `UNVERIFIABLE` warn; joined tags are reported; `--against` reports content that disappeared since a previous version; `--migrate-ref` rewrites only a Fact tag's ref field | not that the persona is founded (`coverage`), not that the excerpt was said by the person it is attributed to (`speakers`), not that the label is the right one, not that the source is admissible for that section, not that the speaker was right; not that an `APPROXIMATE` substitution keeps the meaning — an antonym of four letters or more (`approve`/`reject`) is a substitution like any other, which is why it warns and is repaired to the source's words; and not that bracketed text is evidence: a bracket that stands for nothing (`[not]`) verifies, because brackets are the author's words, visible as such |
| `save` | a copy of the source written as `<date>-<slug>.md` (`--keep-extension` for the source's own extension) with a provenance header and sha1, the body byte-for-byte; no overwrite ever, including between two concurrent runs (the final write is an exclusive create); `--date` accepts `YYYY-MM-DD` only, on every Python version; refuses to write inside a store or into an unignored path in a version-controlled tree | not that the content is what the user says it is, not that the locator is correct, not that anything was fetched; byte fidelity is a statement about the body, never about the name |
| `reindex` | the derived index rebuilt from persona frontmatter and `context.md`, with lint status per persona; a persona past its 180-day budget ends `\| stale since YYYY-MM-DD`, a date and not a day count, so an unchanged store reindexes byte-identically on any later day; `--context X` reads the other contexts' persona and failing counts from their own INDEX.md, never re-linting or zeroing them; a non-date `updated:` is a reported input gap, not a traceback; `--pointer` without `--context` is a usage error (exit 1) before anything is written; every write replaces its file atomically | not that the personas are correct; it never edits a persona, never touches `AUDIT.md`, never decides a roster; not that another context's counts are current — a one-context run trusts that context's last INDEX.md |
| `pending` | every snapshot awaiting a meeting, flagged overdue, missing a meeting date, or with a document changed since the review; reports a snapshot in the pre-0.2 prose shape as such; with `--set-meeting`, the meeting date written once, in the shape the accounting reads, and every earlier date kept on a `meeting moved:` line (exit 0 ok · 1 usage, `--set-meeting` only) | not that the meeting happened; it grades nothing |
| `speakers` | turns split on the *form* of the speaker marker, not on a list of names; unidentified participants reported (exit 2) — a phone-shaped number (seven digits or more, at line start or after a bracket) counts as a marker, an amount like `1.200.000:` does not; a one-off label whose words are not all capitalised is folded into the turn it interrupts and reported on `folded labels:` (and `folded_labels` in `--json`), never counted as a speaker; only the header `save` writes is stripped, so a source opening with a `---` rule keeps its turns; turns carrying a second marker reported and excluded (exit 3); volume per speaker; a shared microphone declared by the user with `--map "<label>=room: …"` is echoed in the roster, in the AUDIT fragment and at the head of `--speaker` output, where the turns the clues flagged are marked `[room?]`; room clues are printed, never exit-bearing | not who an unidentified speaker is — that is declared from outside the file with `--map`, never inferred from what is being said; not that a folded label was not a real one-turn speaker — it is reported so you can map it; and not whether a named label is one voice or a whole room — the clues it prints (`POSSIBLE SHARED MICROPHONE.`) are questions for the user, they fire on legitimate calls often rather than rarely, and absence of clues is not evidence of a single voice |
| `coverage` | before building, who speaks across a folder of sources and how much; after building, the nine definition-of-done checks and a `solid / adequate / thin` verdict with its reason; refs resolved against the persona's context `sources_root:`, never the working directory; the time span counted from Fact-tag dates only; AUDIT rows matched on the slug as a whole word | it never blocks; not that the evidence is representative, not that the persona predicts anything, not that the quotes exist (`lint`) |
| `watchlist` | entries with stable ids, their sources and age; promotion into a section with a dated record; a printed diff, writes only with `--apply`; refuses an edit that would drop a Fact tag or a heading; `--promote` strips everything after the entry's last Fact tag (unless it is a quoted excerpt) from the promoted line, appending it to the promotion record as `— dropped: <tail>` and announcing it on stdout before the diff | not that two occurrences are independent (a judgment the user confirms), not that the entry deserves promotion |
| `log` | one appended line per flow, and per offer (`offered / accepted / declined`), read back with `--last` | it is not evidence and never enters a persona; it never leaves the machine |
| `doctor` | one read-only diagnosis per context: lint, coverage, per-section staleness, watchlist entries `READY`, snapshots with status, structural gaps, schema behind current, offers without a follow-up; last line `doctor: healthy (N of M personas checked)` or `doctor: K items need attention (N of M personas checked)`, where N is how many personas the linter returned a verdict for and M how many the store holds; exit 0 always; before any persona is linted, a canary persona in a temporary directory (one quote its source holds, one it does not) goes through the same lint call and must come back exactly `VERIFIED`, `NOT FOUND` — any other answer is a `gap` item and N is reported as 0, because a linter that passes a quote it should refuse has checked nothing; a check that could not run is an item carrying its reason, not a silent pass — a lint or coverage check that raised, a snapshot scan that crashed, a snapshot the scan skipped as unreadable; an unknown `BEFOREHAND_LOCALE` is one item (`locale: <message>`) and the checks that read the locale are skipped under it | it fixes nothing, reindexes nothing, blocks nothing; "healthy" means the bookkeeping is in order, not that a persona is right |
| `panel` | `--validate FILE [--document DOC]`: the reviewer's JSON block matches the schema and value ranges, `criteria` array included (exit 1 with the field path); `--aggregate DIR --roster INDEX.md [--controls DIR] [--overrides FILE] [--document DOC] [--json]`: six sections — the round-1 table in snapshot format, red-line violations, shared-anchor conflict candidates, the blind-spot list, the criteria table fifth, then per-persona counts and mean severity; a round with two round-1 blocks for one persona is refused (`two round-1 outputs for <slug>: …`, exit 1); with `--document`, a `met` whose evidence sits only in a structural line (a heading, a table header, a metadata line, a `**Label:**` span) is printed `declared` in the aggregate, never in the reviewer's block, and evidence found nowhere in the document is a schema error | not the weighted synthesis and not the dynamics round (the model's work); it does not adjudicate a conflict and cannot verify that isolation held; and the document check does not tell you that a body quote demonstrates the criterion — it can only demote a `met` whose evidence sits in a structural line, never promote anything and never certify that body text satisfies a criterion |
| `calibrate` | the accounting on snapshot + annotation + pairing: gradeable rows only, one-to-one matching, match strength, mitigation split, overruled with its date gate, misses by class (`new` \| `known, in the persona` \| `declared blind spot`, on a closed `unmatched real:` tag set), green-light table, precision and coverage, the predictions ledger split by source flow, by source type and by grounding section, the criteria ledger graded apart against what the meeting raised, the role-generic-restricted rate, the limits paragraph; every rate counts exact and substantive as hits and prints the loose-inclusive figure beside it as the upper bound; per-persona coverage is the persona's own real objections a round-1 row matched over the persona's own graded real objections; a repeated `R<j>` or `P<k>`, or an absent entry or `- greenlight:` slug outside the snapshot's roster, is not gradeable; `--apply` never overwrites a frozen record (`done-<date>-<doc>-<n>.md` on a second grading the same day), renames before appending and undoes the rename (exit 1) if the append fails; with `--ledger`, grades a reconstructed ledger only against an unchanged snapshot (pinned by `snapshot sha1:`), keeps the snapshot as the frozen record, and marks the cycle reconstructed in the log entry and in the limits; exit 2 with the reason when the cycle is not gradeable | it does not match predictions to reality — the user confirms every pair; it does not prove a persona is accurate; below five cycles it reports counts and never a percentage; it does not infer a prediction's source type from the persona — the P-row states it, and an absent field reads `unknown`, never private; it does not turn the criteria ledger into a rate; it does not rewrite earlier log entries, so a rate read across the 0.3.1 upgrade mixes the old loose-as-hit coverage with the new one |
| `migrate` | the unified diff of every file it would change; writes only with `--apply`; refuses (exit 2) any change that would reduce Fact tags or headings | it does not improve content, does not re-verify excerpts, and never runs unreviewed |
| `forget` | the persona file and every row naming the slug removed across `AUDIT.md`, snapshots, pairing and annotation files (the person's keyed lines and the `P<k>` lines of the predictions they owned in the snapshot that pairing grades), the calibration log and the usage log, so a cycle that was gradeable stays gradeable; a name inside an enumeration is dropped and the sentence kept, shown as `old -> new`; leaving one `forget` line in `AUDIT.md` (created with the 0.2 header when missing); writes only with `--apply`, each write atomic and ordered so a re-run after an interruption finishes the removal; a `--context` that is not a directory is a usage error (`usage: context not found: <ctx>`, exit 1), so exit 2 keeps meaning "this store never held that slug" | it never edits a snapshot a ledger pins by `snapshot sha1:` — those lines are reported `LEFT`, as are a mention in prose or inside a quoted span, and the `P<k>` lines of a snapshot whose ids cannot be read: each is for a human to handle; a name glued to another word (`devops-sam` when forgetting `ops-sam`) is another slug and is left alone, unreported; it cannot reach copies outside the store — saved sources in the working directory, exported reports, backups — and it is not reversible |
| `test` | every `test_*.py` suite and the matching benchmark, one `name: N/M passed` line each and one exit code; a suite that crashes, prints `0/0` or no summary line is `<suite>: no checks ran` and fails the run; a failing suite prints its `FAIL` lines and the tail of its stderr | it tests the scripts, not the model's behaviour; that is what the evals measure |

---

## Layer 3 — Behaviour

Mechanisms, in decreasing order of strength:

- **script gate** — a script exits non-zero, or refuses to write, and the flow stops.
- **host tool restriction** — the host is asked to withhold the capability (a reviewer
  subagent restricted to reading files).
- **staging** — the environment is arranged so the rule is the only available path (the
  two files copied into an empty directory, so reading anything else means leaving it).
- **prompt only** — the rule holds because the model follows it. Everything here is a
  candidate for a stronger mechanism, and the honest reason it has none is usually that
  the check would need judgment.

| # | Rule | Layer | Mechanism | Where it is stated |
|---|---|---|---|---|
| N1 | Every claim in a persona carries a label and a resolvable source | data | script gate (`lint`) | `evidence-model.md#Labels`, `#Tag contract` |
| N2 | The lint gate blocks and never edits | tools | script gate (`lint`, exit 1) | `evidence-model.md#Glossary` (lint gate); the two legal exits stay in `authoring.md` |
| N3 | Personas change only on the user's confirmation | behaviour | prompt only | `evidence-model.md#Writes and confirmations` |
| S1 | Everything lives in the store, outside repositories | data | script gate (`save` refuses a store or an unignored versioned path) | SKILL.md, Storage |
| S2 | A source must exist as an intact local file before it is extracted from | data | prompt only (`save` provides the mechanism, nothing forces its use) | `evidence-model.md#Tag contract`; how-to stays in `authoring.md` |
| S3 | Sources are never stored raw in the store; only the minimal excerpt is | data | script gate (`save` refuses to write inside a store) | `evidence-model.md#Writes and confirmations` |
| S4 | INDEX files are derived and never hand-edited; `AUDIT.md` is hand-appended and never derived | data | script gate (`reindex` regenerates; the derived marker is absent from AUDIT) | `evidence-model.md#Writes and confirmations` |
| I1 | Every flow announces itself in one line | behaviour | prompt only | SKILL.md, interaction model |
| I2 | Explicit invocation executes; never run a flow because it seems useful | behaviour | prompt only | SKILL.md, interaction model |
| I3 | Proactive offers execute nothing and are mandatory on four triggers, once per source per session | behaviour | prompt only, with the offer ledger as state (`log offer`) | SKILL.md, interaction model |
| I4 | Any write to a persona is proposed, then applied only after the user confirms | behaviour | prompt only | `evidence-model.md#Writes and confirmations` |
| I5 | Flow deliverables need no extra confirmation | behaviour | prompt only | `evidence-model.md#Writes and confirmations` |
| I6 | Bookkeeping closes every flow: reindex, one AUDIT line per source, one log line | behaviour | prompt only | SKILL.md, interaction model |
| H1 | Never roleplay traits with no evidence; a section with no evidence is declared, never filled | behaviour | prompt only (the canonical form is counted by `reindex` and `coverage`, which report but never block) | `evidence-model.md#Empty sections` |
| H2 | Objections are reported, never incorporated into the document, except in apply mode where every incorporation is logged per objection | behaviour | prompt only | `evidence-model.md#Writes and confirmations`; the apply-mode log stays in `review.md` |
| H3 | Persona changes are proposed, never applied silently | behaviour | prompt only | merged into I4 |
| H4 | A simulated persona sees only its persona file and the document | behaviour | host tool restriction + staging; `READ:` self-report as secondary signal | `review.md` step 2 (+ `agents/persona-reviewer.md`) |
| H5 | A passing linter is not a founded persona | tools | script gate (`coverage`, reporting, never blocking) | SKILL.md one line + `evidence-model.md#Glossary` (coverage verdict) |
| H6 | State the limits in every calibration output | behaviour | script-printed (`calibrate` prints the limits paragraph itself) | `calibrate.md` / the `calibrate` module |
| H7 | Shipped examples are synthetic; real personas never enter skill materials | data | script gate (`dev/check_generality.sh`, repository side) | SKILL.md one line |
| H8 | Never let the panel's own output return as evidence | behaviour | prompt only | `evidence-model.md#Post-review` |
| H9 | No sycophancy: objections derive from mandate, incentives and evidence | behaviour | prompt only (repeated in the reviewer prompt) | SKILL.md one line; the reviewer prompt keeps its own line |
| P1 | `machine-transcribed` promotes like any other source, but such a Fact is never quoted as the person's words outside the store | behaviour | prompt only | `evidence-model.md#Provenance` |
| P2 | On a source with three or more voices, establish who speaks before extracting; never infer an identity from the content | behaviour | script gate (`speakers`, exit 2 and 3) for the detection; prompt only for the declaration, including a shared microphone | `evidence-model.md#Provenance` (the rule) + `authoring.md` (the procedure) |
| P3 | A `post-review` source, or a transcript led by a reader of the review, cannot promote a claim already present | behaviour | prompt only | `evidence-model.md#Post-review` |
| R1 | A judgment criterion is met by quoted body content, never by a label that names it | behaviour | script-forced (`panel --document` rewrites a label-only met to declared in the aggregate output, never in the reviewer's block); prompt for the judgment | `evidence-model.md#Declared and demonstrated`; the reviewer prompt keeps its own line |

Three observations this table is meant to make visible:

1. The strongest mechanisms cluster in the data layer. Everything about *what is on disk*
   can be checked; almost everything about *what the model says* cannot.
2. Four rules used to be stated in three places each (N3/I4/H3, H1, P1, P3). The
   one-norm-one-file rule removed that duplication: each now lives at a single anchor, and
   `dev/check_norms.sh` fails the build if a second file restates it.
3. Two rules have gained a genuinely stronger mechanism since the prompt-only start: H4,
   which moved to staging plus host tool restriction in 0.2, and R1, which is script-forced
   in 0.3 — not because a script can judge a criterion, but because *where the evidence
   sits* in a document is a structural question and not a judgment at all. The rest stay
   prompt-level on purpose: a script that decided whether an objection was "grounded in the
   evidence" would be the same guess the skill refuses to make.
