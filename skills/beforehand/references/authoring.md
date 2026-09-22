# Authoring flow — build, update and import personas from evidence

Personas are extracted, not invented. The paths below are ordered by evidence strength;
always take the strongest path the available material allows. Announce first:
`beforehand · authoring (create | update | import) · store ~/.beforehand/<context>`, then run
`python3 $SKILL/scripts/beforehand.py doctor --context <ctx>` and act on what it lists: an
overdue snapshot is offered for calibration first, and an open offer is not re-offered.

## Step 0 — The source must be an intact local file

Before extracting anything, make sure every source you will cite exists as a file its tag
can reach (`references/evidence-model.md#Tag contract`) — never inside the store. When the
sources live outside the context folder, set `sources_root:` in the context's `context.md`
to the folder they are saved in:

- **Pasted in chat** (a transcript, a mail, a message) or fetched from a remote system: save
  it first with `python3 $SKILL/scripts/beforehand.py save --dir <project>/sources/ --ref "<original locator>"`
  (body on stdin or `--from FILE`). Pass `--date <the date of the source>` rather than letting
  it use today, and `--what <slug>` when the content opens with a generic heading: meeting
  platforms give every transcript the same title, so ten sources saved in one sitting derive
  the same file name. The script never overwrites, it refuses; `--seq` numbers the collisions
  instead, so a batch does not turn into ten manual renames.
  It writes `YYYY-MM-DD-<slug>.md` (or the source's extension with `--keep-extension`) with a provenance header,
  keeps the body byte for byte, refuses to write inside a personas store, and refuses an
  unignored directory inside a git work tree (it prints the `.gitignore` line to add). It prints
  the path and a ready-to-paste tag fragment. Do not strip accents, tidy filler or summarise by
  hand: a copy that differs from the original makes every later re-audit fail or lie. The first
  time a project needs `sources/`, propose the `.gitignore` entry.
- **Remote** (cloud document, mail thread, CRM note, web page): fetch it if a tool allows,
  save the text locally, cite the local path *and* keep the remote reference in the AUDIT
  line. If it cannot be fetched, cite the URL or identifier and accept `UNVERIFIABLE` — but
  say so in the proposal, and prefer downgrading to Inference over promoting a Fact nobody
  will ever be able to re-check.
- **The user's own words** (see Path B, user reports): save them to a dated notes file in
  the working directory before citing them.

Cite paths that resolve (absolute or `~`-anchored). A bare filename or a shorthand like
"same source" makes the tag unparseable or unverifiable at the next audit.

## Path A — Create from sources (primary)

Input: one or more written sources — private communications (call transcripts, emails,
meeting notes) or public material (news, podcast transcripts, published interviews,
social posts).

### Before step 1, on a multi-voice source: establish who speaks

The rule this implements — establish who speaks before extracting, never infer an identity
from the content — is in `references/evidence-model.md#Provenance`. The procedure:

Run `python3 $SKILL/scripts/beforehand.py speakers <source>`. It prints every speaker with the
volume they spoke, and it fails while anything is unresolved. Two things it protects you
from, neither of which the linter can catch afterwards:

- **A participant the platform could not identify.** Transcripts open a turn with a
  marker at the start of a line. Someone joining by phone, or a guest, gets whatever
  label the platform has — a masked number, `Guest`, `Speaker 2`, including `User`/`Anonymous` — and a reader (or a
  throwaway script) splitting turns *by the names they know* does not see that marker,
  so those words are silently appended to the previous named speaker's turn:

  ```
  **Named Person:** ...their words...
  **+44 7700 *** **31:** ...the phone participant's words, absorbed above...
  ```

  The excerpts remain findable in the file, so the persona lints green while quoting
  someone else. Settle the label from outside the file (a mail signature, the invitation,
  the user's own memory), ask the user to confirm, then record it with
  `--map "<label>=<who>"`.
- **A marker sitting mid-line**, which no split can cut on. Those turns are reported as
  *dubious paternity* and excluded from `--speaker` output unless you ask for them.
- **A named label that can be a whole room** (`references/evidence-model.md#Provenance`):
  `named` only means the platform had a name for that microphone. The script prints
  `POSSIBLE SHARED MICROPHONE` with the clues it found, and they are clues — a run without
  any is not evidence of a single voice — so on any call where one label is the only one on
  a side the user attended, **ask the user whether that microphone was shared**. That
  question, not the heuristic, is what catches a room. Record their answer with
  `--map "<label>=room: <who speaks>, <N> present"`; then put the turns `--speaker` marks
  `[room?]` in the proposal as they are, and let the user place or drop each one.

Use the volume column before deciding whom to build: being on the invitation is not
speaking, and a person with a few hundred characters across a long call does not have a
persona in that source. If the attribution cannot be settled, exclude the turns, or the
whole source, and say so in the proposal and in AUDIT.

Across a whole folder of sources the same question is one command:
`python3 $SKILL/scripts/beforehand.py coverage --sources <dir> [--people "A, B"]`. It ranks
everyone by how much they actually spoke, over how many independent sources and what time
span, and marks who is too thin to carry a persona. **Run it before building several
personas at once.** Full-text search over a document system returns the meetings where a
name is on the invitation; a person can appear in eight of them and say a few hundred
characters in total. Measuring first is the difference between building three founded
personas and building three founded ones plus two empty ones that look exactly the same.

1. **Read each source once and extract**, per template section (`assets/persona-template.md`):
   - *Mandate and incentives*: what they say they are measured on, budget/risk ownership,
     personal stakes; evidenced internal tensions.
   - *Judgment criteria*: what they ask about first, what convinced or disqualified past
     proposals.
   - *Recurring objections*: objections actually raised, verbatim where possible.
   - *Red lines*: absolute statements ("below that, I do not sign").
   - *Language and dissent style*: signature phrases quoted verbatim — how they open an
     attack, how dissent surfaces (email later? via a delegate?). Prefer quotes over
     adjectives: the fingerprint is what lets calibration recognize oblique objections.
   - *Panel dynamics*: who they defer to, who they clash with.
   - *Background* (optional): only evidence-backed items that explain judgment criteria.
   - Frontmatter `cares_about`: the 2-3 hot themes, one line — it drives roster selection.
   - Decision weight: propose 1–5 with its own label — attributed weight is usually an
     Inference, and it should look like one.
2. **Label every claim as it is born.** The three labels, the five-field Fact tag and its
   promotion marker, the two axes, the admissibility table and the limits provenance puts
   on top of it are stated once, in `references/evidence-model.md`:

   | What you need at this step | Where it is stated |
   |---|---|
   | What Fact, Inference and Assumption mean | `references/evidence-model.md#Labels` |
   | The canonical tag forms and their fields | `references/evidence-model.md#Tag contract` |
   | Recording a claim promoted from Inference | `references/evidence-model.md#Promotions` |
   | `private-communication` / `public-statement` / `second-hand` | `references/evidence-model.md#Source type` |
   | `human-authored` / `machine-transcribed` / `post-review` | `references/evidence-model.md#Provenance` |
   | Which label a section will carry from that source | `references/evidence-model.md#Admissibility` |
   | What a `post-review` source may and may not do | `references/evidence-model.md#Post-review` |

   Read them before the first tag, and settle both axes of a source before labelling
   anything out of it: labelling is the one step of this flow no script can repair
   afterwards, and the axes decide what the whole source may promote. Decision weight is
   a claim like any other and carries its own label. On a multi-voice source, the
   attribution settled in the subsection above holds for every excerpt you promote here.

3. **Lint before proposing (gate).** First check the proposed Fact excerpts against the
   source: write them to a JSON array and run
   ```
   python3 $SKILL/scripts/beforehand.py lint --excerpts <excerpts.json> --source <source-file>
   ```
   Then write the proposed persona file to a scratch path and run
   `python3 $SKILL/scripts/beforehand.py lint <file> --sources-root <the context's sources_root> --lint`.
   See `references/evidence-model.md#Tag contract` for what each verdict means. Procedure
   here: a file the gate fails is not shown to the user, and there are two legal exits from
   that failure — repair the tag so that it resolves and the excerpt is in the source, or
   downgrade the claim to Inference keeping the unresolvable locator in the text, saying so
   in the proposal. Fabricating a path is the failure this gate exists to prevent.
   A MISPLACED rewrite from `--fix-tags` is applied by hand after re-reading the source:
   moving a quote is exactly the moment one is tempted to let it support the nearest claim
   instead of the one it actually supported.
   Anti-gaming rule: a NOT FOUND or an APPROXIMATE is fixed by re-reading the source and
   replacing the excerpt with text that is actually there, or by downgrading. Never by trimming
   or rewording the excerpt until the lint stops reporting it: an excerpt edited to fit is a
   fabrication with a passing test.
   After two repair attempts, stop and show the user the failing tags and the source.
4. **Definition of done of the flow, before proposing anything.** The linter answers "does
   every quote exist". It cannot answer "is this persona founded", and the two are not the
   same question: a file built on one thin source passes it exactly like one built on five
   independent ones. Run
   `python3 $SKILL/scripts/beforehand.py coverage <the proposed file> --audit <ctx>/AUDIT.md`,
   which checks nine things computable from the file and the AUDIT — independent sources,
   time span, volume, how many judgment sections carry evidence, whether one source carries
   most of it, whether empty sections are declared, `cares_about`, the attribution note
   on multi-voice sources, and whether the frontmatter stays inside the accepted subset
   (FR-4.8) — and returns solid / adequate / thin with the reason.
   **It never blocks.** A thin persona is usable; one that is thin without saying so is not.
   The verdict goes in the proposal, in the index, and next to the name in every panel report.

   Sections the sources do not evidence are declared, never filled: the canonical form and
   the reason are in `references/evidence-model.md#Empty sections`. Each one is also a
   declared blind spot the panel will report, so write it before proposing, not after.

5. **Propose the compiled persona** to the user: the filled template plus the verification
   summary, the lint line and the coverage verdict. Apply only on confirmation.
6. **Bookkeeping after confirmation**: write `personas/<slug>.md`; create or update
   `context.md` (description, and `## Wanted` for stakeholders who appeared in the sources
   or were named but have no first-hand evidence — role, the decision function they would
   cover, why they matter); run `python3 $SKILL/scripts/beforehand.py reindex --context <ctx>`
   (add `--pointer <working-dir>/personas.md` if the user keeps a pointer there); append to
   `AUDIT.md`:
   `<date> | <source path or ref> | <approx volume> | type: <source type> | provenance: <provenance> | personas: <slugs> | <notes>`
   — **one physical line, however long**: `forget` removes an AUDIT record by deleting the
   line that names the slug, so a record wrapped over two lines leaves the second half
   behind as an orphan. On a multi-voice source the notes are **mandatory** and say
   how attribution was settled: paste the AUDIT fragment `beforehand.py speakers` prints (speaker count,
   unidentified labels and what each was declared to be, any shared microphone with the words the
   user declared it in and how many turns it flagged, turns excluded as dubious), plus any
   turns or whole sources you dropped and why — on a shared microphone, which of the `[room?]`
   turns were left out of promotion — plus the sections this source may not promote.
   "Attribution checked" without saying what was checked is not a record. The line takes an
   optional trailing field after `personas:` — `| led by: <label>, had read the review: yes | no`
   — required for a transcript dated after a review of the same document
   (`references/evidence-model.md#Post-review`);
   `python3 $SKILL/scripts/beforehand.py log authoring <ctx>`.

## Path B — Update from new sources (the living dossier)

Input: a new communication, or the user's account of something a stakeholder did or said,
plus existing persona(s). **This path is offered, not only requested** (SKILL.md,
interaction model rule 3): a source that names an indexed person, or a remark from the
user about one, triggers a one-line offer. A persona that is not updated after every
contact decays into a portrait of who the person was on the day of the first transcript.

**User reports are a source.** "She was cold on the timeline", "he decided alone in the
end", "turns out price was never the issue" — the user witnessed behavior the store does
not have. Handle it as evidence, with its true labels:
- save the user's words to a dated notes file in the working directory first (Step 0);
- type `private-communication` when the user witnessed it, `second-hand` when the user is
  relaying what someone else reported; provenance `human-authored`, or `post-review` if the
  report follows a panel review of the same document
  (`references/evidence-model.md#Post-review`);
- the excerpt is the user's sentence, quoted; the claim about the stakeholder is usually
  an Inference from it ("did not raise price in the closing meeting → price sensitivity
  lower than assumed"), a Fact only where the user quotes the person.

1. Extract as in Path A, then **diff against the existing persona** and present four lists:
   - **Confirmed**: existing Inference now directly evidenced → propose promotion to Fact,
     written with the promotion marker (`references/evidence-model.md#Promotions`). Before
     proposing any promotion out of this source read
     `references/evidence-model.md#Post-review`: it decides what a note written after the
     review, and a transcript led by someone who had read it, may promote — for the second,
     ask who led the conversation and record the answer in the AUDIT line.
   - **Contradicted**: new evidence clashes with an existing claim → flag the conflict and
     let the user decide (keep, replace, or hold both with dates — people change).
   - **New**: claims not yet in the persona, labeled and verified as in Path A steps 2–3.
   - **Watchlist**: a claim resting on one occurrence goes to `## Watchlist`, not into the
     body. The entry form, the id rule, what counts as a second occurrence and what the
     promotion script refuses are in `references/evidence-model.md#Watchlist`.
     Run `python3 $SKILL/scripts/beforehand.py watchlist <persona> --list` to see what is
     waiting and which entries already cite two distinct sources, then
     `--promote <id> --section "<section>"` — it prints the diff and writes only with
     `--apply`, so the user confirms the independence judgment the script can only flag.
2. Propose the resulting edit as one diff, then lint as in Path A step 3 and recompute
   coverage as in Path A step 4; the same two exits
   and the same anti-gaming rule apply. Also run `beforehand.py lint` with
   `--against <the file before the edit>`: it reports Fact tags, sections and entries that
   disappeared. A persona that quietly lost half its objections lints exactly like an intact
   one, so a shrink is either explained to the user or it is a bug. Apply on confirmation; bookkeeping as in A6
   (`updated:` bumped, `last evidence:` bumped only on the sections the diff touched,
   `cares_about` revisited, AUDIT appended, `beforehand.py reindex`, `beforehand.py log update <ctx>`).

## Multi-persona routing (A and B)

A source touching several stakeholders is processed **once**:
1. Cluster the extracted evidence by person (speaker attribution in transcripts, named
   mentions elsewhere).
2. Match each person against the context `INDEX.md` aliases.
3. Present ALL resulting per-persona diffs as a single batch for one confirmation.
4. Unmatched people who spoke first-hand: if they are listed under `## Wanted` in
   `context.md`, offer a new persona; otherwise report that they spoke and have no persona
   and let the user decide. Never create silently.

## Path C — Interview (fallback, no written sources)

Ask the user the template sections one at a time, label answers honestly (mostly
Inference and Assumption — say so in the proposed file), and state plainly that this
persona is weaker than an extracted one. Nudge: "when you have a transcript or email from
this person, bring it here — Path B upgrades the persona."

## Path D — Import from existing stakeholder notes

Input: a stakeholder file written in another format (an older template, another tool's
export, free-form notes with labels such as *Fact / Estimate / Hypothesis*).

1. Map labels honestly, never upward: a claim with a verbatim quote **and** a source that
   still exists as a local file → propose `Fact` after the script verifies it; a quote whose
   source is gone or was never a file → `Inference` with the note "quoted in imported
   notes, source not re-checkable"; an estimate or hypothesis → `Inference` or `Assumption`
   per its original meaning; anything unlabeled → `Assumption`.
2. Fill the template sections; what the old format does not distinguish (red lines vs
   objections, dynamics vs background) stays where the evidence puts it, thin sections
   declared thin.
3. Propose the persona with the mapping table (old label → new label, counts) and the lint
   line; apply on confirmation. AUDIT line: `type` and `provenance` of the *original*
   sources where known, plus `imported from <path>`. Then
   `python3 $SKILL/scripts/beforehand.py reindex --context <ctx>` and
   `python3 $SKILL/scripts/beforehand.py log import <ctx>`.
4. Tell the user what the import cannot give: an imported persona enters panels as `warn`
   until at least one source is re-verified or a new one is ingested.

## Privacy notes that shape this flow

- Only the minimal excerpt enters the persona; whoever needs full context returns to the
  original source. A reference that later dangles (source deleted) is acceptable.
- Record source references as `references/evidence-model.md#Tag contract` says; a ref that
  only resolves from the working directory reads UNVERIFIABLE at every later re-audit.
- Never paste large source passages into the persona or the audit trail.
- Raw source copies live in the user's working directory by the user's rules; what may and
  may not be written into the store is in `references/evidence-model.md#Writes and confirmations`.
