#!/usr/bin/env python3
"""calibrate: grade the panel's predictions against what the meeting said (SPEC-0.2 FR-5.4).

The v0.1 accounting was arithmetic a model did by hand on markdown tables, and a measurement
instrument that is re-derived every time is not an instrument. This command does the counting;
the matching itself stays a judgment the user confirms, in the pairing file, before it runs.

Usage:
  beforehand.py calibrate --context CTX --doc NAME [--store PATH]
                        [--annotation FILE] [--pairing FILE] [--ledger [FILE]]
                        [--apply] [--json]

Three inputs, all on disk before this runs:

  1. the snapshot `<ctx>/calibration/pending-<doc>.md`, frozen at review time: the header
     (`document`, `sha1`, `frozen`, `meeting`, `events:`, `control: yes | no`, `personas`),
     `## Round-1 objections`, `## Green lights`, `## Criteria` (optional; pasted from
     `panel --aggregate`), `## Applied before sending`, `## Predictions to verify`.

     A snapshot frozen before that shape existed (prose, no `schema:`, no sections) cannot be
     read this way and is graded through `--ledger [FILE]`, default
     `<ctx>/calibration/ledger-<doc>.md`: a 0.2-shaped file the model writes from the prose
     and the user confirms line by line (references/calibrate.md). With `--ledger`, every
     header field, every section and the `events:` block are read from the ledger, while the
     pending file stays the frozen record — it must still exist, it is what `snapshot_sha1`
     hashes, and it is what `--apply` renames. The ledger must carry `reconstructed:
     YYYY-MM-DD`, `snapshot sha1:` matching that file, and `frozen:` (without it the
     pre-registration gate could not run at all); each missing one is exit 2. Meeting-date
     precedence: the snapshot's `meeting:` if it parses, else the ledger's, so a date moved
     with `pending --set-meeting` on the file of record always wins. `frozen:` follows the
     same precedence for the same reason: the snapshot's own date if it parses, else the
     ledger's, so a transcribed date may fill in a prose one that does not parse but never
     softens the pre-registration gate. Every such run prints
     the reconstruction warning, notes it in the log entry and says so in its limits: a
     ledger written after the meeting is transcription, not pre-registration, and nothing
     here can tell one written to fit the outcome from one written honestly;
  2. the annotation, `<ctx>/calibration/annotation-<doc>.md` unless `--annotation` says
     otherwise: the two-minute template of calibrate.md, saved as a source. Machine-read
     lines, in English whatever the conversation language:

       Meeting held: yes | postponed | replaced by email
       Attendees: <who was in the room>
       Personas rostered but absent: <slugs>      <- out of this cycle's denominators
       Grading cut-off: YYYY-MM-DD                <- later arrivals are noted, not graded
       - R<j> | <who> | <objection> | <part of the document> | channel: … | actual severity: N
       - R<j> | … | actual severity: N | date: YYYY-MM-DD      <- optional, for the cut-off
       - greenlight: <slug> | observed <yes | no | not observed | not applicable>

  3. the pairing `<ctx>/calibration/pairing-<doc>.md` unless `--pairing` says otherwise,
     written by the flow as a proposal and confirmed by the user line by line:

       <key> | R<j> | exact | substantive | loose | related | <note>
       unmatched real: R<j>, R<j> (blind spot), R<j> (known), R<j> (new)
       overruled: <key> | YYYY-MM-DD
       criterion: R<j> | <slug>#c<n>      <- the meeting raised that judgment criterion
       criterion: R<j> | absent           <- it raised one no persona row carries

     The `unmatched real:` tag set is closed — `blind spot | known | new`, untagged meaning
     `new` — because an unknown tag used to read as a plain miss without saying so.

     Two key forms, because the two ledgers are numbered differently: `<slug>#<n>` addresses
     the n-th `## Round-1 objections` row of that persona, counting from 1 (the same key
     `panel` uses for its role-generic overrides), and `P<k>` addresses a
     `## Predictions to verify` item, and `<n>` counts round-1 rows only, exactly as `panel`
     numbers them. A third key form belongs to `criterion:` lines alone: `<slug>#c<n>`
     addresses the n-th `## Criteria` row of that persona, in its own series, so
     `<slug>#c1` and `<slug>#1` have nothing to do with each other.
     `related` is the strength of a claim the user does not want counted as a
     match: it records the resemblance, and it is what a second claim on a real objection
     already taken **inside the same ledger** has to be marked. One-to-one holds per ledger,
     not across the two: a real objection may satisfy one round-1 row and one `P<k>` at once.
     Any other line, an unknown strength or an `overruled:` date that is not `YYYY-MM-DD`
     stops the run rather than being skipped.

Accounting rules — each closes a way for a miss to become something else:

  - One-to-one, inside each ledger. A real objection satisfies at most one round-1 row and at
    most one `P<k>`, and each key matches at most one real objection; a second claim in the
    same ledger marked `related` reads `related, not matched`, and an unmarked one stops the
    run, because a silent double count inflates both rates at once.
  - Match strength. `exact` (same substance, same anchor), `substantive` (same substance,
    the anchor moved and the note says why), `loose` (thematic only). The headline rate uses
    exact and substantive; the loose-inclusive rate is printed beside it as an upper bound.
  - Gradeable rows. Round-1 rows of the version that was actually sent, on an event the
    persona's context attended. Later rounds and anything under `## Applied before sending`
    are reported as `panel-driven edits: K` and never enter a rate: a prediction the panel
    already watched the document react to is no longer blind. A row whose `Event` belongs to
    another context is listed apart, ungraded — that audience has not met the document yet.
  - Absent personas. Every row and every green light of a persona named under
    `Personas rostered but absent:` leaves the denominators: they were never in the room.
    Each entry may carry a trailing `(note)` and may be a name (`Toft`) rather than the slug;
    it is resolved against the snapshot's roster, and an entry that resolves to no roster
    persona stops the run, because an ignored one leaves that persona in every denominator.
    A `- greenlight:` line naming no roster slug stops the run for the same reason.
  - Ids are unique. A duplicate `R<j>` in the annotation or `P<k>` in the snapshot stops
    the run: the pairing addresses them by id, and a doubled id is counted twice.
  - Mitigation split (FR-2.4). An unmatched row is `not-raised (mitigated)` when its
    `Doc changed` cell reads yes or partially, else `not-raised (unmitigated)`. Only the
    unmitigated cell speaks to predictive accuracy; the mitigated cell is value delivered.
  - Overruled (FR-2.4). A tag on a row, not a column. It leaves the denominator only when it
    was decided before the meeting **and** the anchor text was removed (`Doc changed: yes`);
    an overruled row whose text stayed is still gradeable, because the meeting could still
    raise it. A date on or after the meeting is a retroactive note and moves nothing.
  - Misses, by class. A graded real objection no line matched is a miss, attributed to the
    persona whose ground it was — the slug whose parts contain the annotation's `<who>`, else
    `unattributed`. The `unmatched real:` tag says which kind it is, and the three kinds
    indict different things:
      `new` (the default) — nothing in the persona anticipates it: a miss of the persona,
        and it points at a thin section;
      `known` — the persona already carries it (a Recurring objection, a Red line) and the
        panel did not list it for this document: a miss of the panel's reading of this
        document, not of the evidence. Reported as `miss (known, in the persona)`, counted
        in `misses_known`, never in `misses`;
      `blind spot` — declared before the meeting: `miss (declared blind spot)`, pointing at
        `## Wanted` in context.md, not at a thin section.
    A `criterion:` line refines the outcome further: `miss (criterion present, accepted by
    declaration: <key>)` when the snapshot's own `## Criteria` row read `met`, and
    `miss (criterion absent from the persona)` when the pairing says `absent`. The class
    tally is the pairing's tag set, so those two still count under the tag they carry.
  - Criteria ledger (FR-2.4). The snapshot's `## Criteria` rows are graded apart from both
    other ledgers, counts only and never a rate: a row the meeting raised reads `flagged,
    raised` unless the snapshot accepted it (`met`), which reads `miss (criterion present,
    accepted by declaration)`; a row the meeting never raised reads `accepted, not raised`
    or `flagged, not raised`. A `#c<n>` the snapshot cannot resolve to exactly one row —
    unknown, or named twice by the pasted table — stops the run rather than grading the wrong
    row. A `criterion:` line on a real objection that arrived after `Grading cut-off:` is
    ignored with a warning, like every other claim on a late arrival. Rows belonging to a
    persona under `Personas rostered but absent:` stay in this ledger, unlike the round-1 and
    prediction ledgers: the count is the pasted table's own row count, it is never a rate, and
    someone else in the room can raise an absent persona's criterion.
  - Grading cut-off. A real objection dated after `Grading cut-off:` is listed as noted, not
    graded, and sits in no denominator.
  - Green lights (FR-2.3). Their own 2x2, predicted YES/NO against observed yes/no, counts
    only, never pooled with objections: an objection predicts an event, a green light
    predicts a state, and the two have different base rates. `not observed` and
    `not applicable` are excluded from the table and counted beside it.
  - Predictions ledger (FR-2.5). `## Predictions to verify` items are graded in their own
    block with their own rate, split by `source flow`, because they carry no anchor quote
    and match more loosely. Like the round-1 rate, a hit is exact or substantive, and the
    loose-inclusive figure is printed beside the rate and beside every split as the upper
    bound. Items marked `role-generic: yes` are reported as base-rate items
    on a line of their own. The same rate is split twice more (FR-1.4): by the optional
    `source type: private-communication | public-statement | second-hand | mixed` trailing
    field of the P-row — absent reads `unknown`, and `unknown n/n` is always printed so a
    legacy ledger says so — and by the grounding section the row names. Unknown trailing
    fields on a P-row are ignored, in both directions.
  - Two rates, always together. Precision is hits over gradeable rows; coverage is the real
    objections a round-1 row matched at exact or substantive over every real objection
    graded, with the loose-inclusive count beside it (per persona: that persona's own graded
    real objections a round-1 row of any persona matched at exact or substantive, over all
    of that persona's own graded real objections — a hit on another persona's objection
    counts for the predicting row's precision and the raiser's coverage) — the predictions
    ledger keeps its own rate and never enters this one, because a `P<k>` carries no anchor
    quote and matches more loosely. Neither rate is printed alone.
  - Role-generic (FR-5.3). The rate restricted to `role-generic: no` rows is the only number
    that speaks to the differentiating claim. The column holds `yes | no | estimated`; a
    legacy `yes (proposed)` cell is read stripped, with a warning. It is labelled `(control)`
    only when the snapshot header says `control: yes`, `(estimated)` otherwise.
  - Never grade after the fact. A snapshot whose `frozen:` is on or after the meeting date is
    not gradeable at all, and a snapshot without a meeting date cannot be graded yet. A
    `sha1` that no longer matches the document is a warning, not a refusal: grading proceeds
    tagged `document changed after review`, since the predictions were about the earlier text.
  - No mid-review split. A persona file changed mid-loop restarts its reviewer; the clean
    final pass alone produces the snapshot, so there is nothing to split at calibration time.
  - Minimum n. Percentages appear only from 5 cycles on for that persona (a cycle is one
    `## ` entry naming the slug in `calibration/log.md`, this one included); below that,
    counts and `n too small to interpret`. A pooled rate under that floor would read as more
    certain than the sample supports.

Writes, only with `--apply`: the rename of `pending-<doc>.md` to `done-<today>-<doc>.md`
(or the first free `done-<today>-<doc>-<n>.md`, n >= 2: a frozen record is never
overwritten), then the `calibration/log.md` entry. If the entry cannot be appended the
rename is undone and the run exits 1 with the reason. The per-persona Reliability one-liner is
printed as a unified diff and never written — persona files change only through the
confirmed path (references/evidence-model.md#Writes and confirmations).

Exit codes: 0 ok · 1 usage, or an --apply that could not append the log entry (undone) ·
2 not gradeable (the reason is printed).
"""
import argparse
import datetime as dt
import difflib
import hashlib
import json
import re
import sys

sys.dont_write_bytecode = True   # before any sibling import (G5): a run leaves no __pycache__
from pathlib import Path  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pending import (  # noqa: E402
    document_state,
    field,
    parse_date,
    parse_events,
    snapshot_format,
)
from personas_lib import (  # noqa: E402
    LocaleError,
    Store,
    append_line,
    locale_regexes,
    read_text_lenient,
    resolve_store,
    section_body,
    sections,
)

# A hook, not a bare call: tests pin the date instead of asserting on the real calendar.
_today = dt.date.today

MIN_CYCLES = 5          # below this, counts only (SPEC-0.1 §3, Minimum n)
SHA_PREFIX = 12         # how much of a sha1 the pinned log heading carries
STRENGTHS = ("exact", "substantive", "loose")
STRENGTH_TOKENS = STRENGTHS + ("related",)
HEADLINE = ("exact", "substantive")

LIMITS = ("small n, single observer, assisted matching — a longitudinal case study, "
          "not a controlled study.")


class ArgParser(argparse.ArgumentParser):
    """argparse leaves with 2 on a bad invocation, and 2 is pinned here to `not gradeable`
    (Global Constraints). A malformed command line is usage, so it leaves with 1."""

    def error(self, message):
        self.print_usage(sys.stderr)
        print("%s: error: %s" % (self.prog, message), file=sys.stderr)
        raise SystemExit(1)


class NotGradeable(Exception):
    """Validation failed: the cycle cannot be graded at all (exit 2)."""


class Usage(Exception):
    """Something the caller must fix before the accounting can run (exit 1)."""


# ------------------------------------------------------------------ markdown table reading
# `panel.cell()` writes a literal pipe inside a cell as `\|`. Splitting on raw pipes would
# shift every column to the right of it — silently, including the row key — so the split is
# on unescaped pipes only and each cell is unescaped afterwards.
CELL_SPLIT_RE = re.compile(r"(?<!\\)\|")
CLOSING_PIPE_RE = re.compile(r"(?<!\\)\|$")


def table(body):
    """-> (header cells lowercased, [row cells]) of the first pipe table in `body`."""
    rows = [ln.strip() for ln in (body or "").splitlines() if ln.strip().startswith("|")]
    rows = [r for r in rows if not re.fullmatch(r"\|[\s:|-]*\|", r)]
    if not rows:
        return [], []
    def cells(line):
        # Drop the delimiters, not the content: the opening pipe cannot be escaped, and the
        # closing one goes only when it is not itself the `\|` ending the last cell.
        inner = CLOSING_PIPE_RE.sub("", line.strip()[1:])
        return [c.strip().replace("\\|", "|") for c in CELL_SPLIT_RE.split(inner)]
    head = [c.lower() for c in cells(rows[0])]
    return head, [cells(r) for r in rows[1:]]


# Column aliases: the 0.1 snapshot shape has fewer columns and names two of them differently
# (SPEC-0.2 §8), so every column is found by name and the missing ones fall back.
ALIASES = {
    "persona": ("persona",),
    "context": ("context",),
    "isolation": ("isolation",),
    "anchor": ("anchor in the document", "anchor"),
    "objection": ("objection",),
    "severity": ("severity",),
    "round": ("round tag", "round"),
    "event": ("event",),
    "role_generic": ("role-generic", "role generic"),
    "doc_changed": ("doc changed", "document changed"),
}


def column_index(head, aliases=None):
    """-> {key: column index} for every alias found in `head` (first alias wins)."""
    idx = {}
    for key, names in (ALIASES if aliases is None else aliases).items():
        for n in names:
            if n in head:
                idx[key] = head.index(n)
                break
    return idx


def row_getter(cells, idx):
    """-> cell(key, default=""): the one way a table row is read, so a short row reads as
    its defaults instead of raising or shifting."""
    def cell(key, default=""):
        i = idx.get(key)
        return cells[i] if i is not None and i < len(cells) else default
    return cell


PROPOSED_RE = re.compile(r"\s*\((?:proposed)\)\s*$", re.I)
ROUND1_RE = re.compile(r"r?(?:ound\s*)?1")


def parse_round1(text, ctx_name, warnings):
    """-> [row dict] for `## Round-1 objections`, keyed `<slug>#<n>` per persona."""
    head, raw = table(section_body(text, "Round-1 objections"))
    idx = column_index(head)
    if "persona" not in idx:
        return []
    out, seen = [], {}
    for cells in raw:
        cell = row_getter(cells, idx)
        slug = cell("persona")
        if not slug:
            continue
        round_tag = (cell("round") or "r1").strip().lower()
        first_round = bool(ROUND1_RE.fullmatch(round_tag))
        if first_round:
            seen[slug] = seen.get(slug, 0) + 1
            key = "%s#%d" % (slug, seen[slug])
        else:
            # `panel` numbers round-1 objections and nothing else, and the pairing key has to
            # be the same key; a later-round row therefore gets a label, not a number.
            key = "%s#- (%s, not round 1)" % (slug, round_tag)
        rg_raw = cell("role_generic", "estimated") or "estimated"
        rg = PROPOSED_RE.sub("", rg_raw).strip().lower()
        if rg != rg_raw.strip().lower():
            warnings.append("legacy role-generic cell `%s` read as `%s` (%s)"
                            % (rg_raw.strip(), rg, key))
        if rg not in ("yes", "no"):
            rg = "estimated"
        out.append({
            "key": key,
            "persona": slug,
            "context": cell("context") or ctx_name,
            "isolation": cell("isolation") or "unknown",
            "anchor": cell("anchor"),
            "objection": cell("objection"),
            "severity": cell("severity"),
            "round": round_tag,
            "event": cell("event"),
            "role_generic": rg,
            "doc_changed": (cell("doc_changed") or "no").lower(),
        })
    return out


GREEN_VALUES = ("yes", "no", "insufficient_basis")


def parse_green_lights(text):
    """-> {slug: predicted YES | NO | INSUFFICIENT_BASIS} from `## Green lights`.

    Table form (review.md Step 4) and the one-line-per-persona form are both accepted: the
    section is written by hand often enough that refusing one shape would cost a cycle.
    """
    body = section_body(text, "Green lights")
    if body is None:
        return {}
    out = {}
    head, raw = table(body)
    idx = column_index(head)
    if "persona" in idx:
        idx.update(column_index(head, {"greenlight": ("greenlight",)}))
        for cells in raw:
            cell = row_getter(cells, idx)
            slug, value = cell("persona"), cell("greenlight")
            if slug:
                out[slug] = value.strip().upper() or "DESCRIPTIVE ONLY"
        return out
    for ln in body.splitlines():
        m = re.match(r"^\s*[-*]\s+([A-Za-z0-9][\w.-]*)\s*[|:]\s*(.*)$", ln)
        if not m:
            continue
        rest = m.group(2)
        mv = re.match(r"\s*(YES|NO|INSUFFICIENT_BASIS)\b", rest, re.I)
        out[m.group(1)] = mv.group(1).upper() if mv else "DESCRIPTIVE ONLY"
    return out


PRED_RE = re.compile(r"^\s*[-*]\s+(P\d+)\s*\|\s*(.*)$")


PRED_FIELDS = {"source flow": "source_flow", "specificity": "specificity",
               "role-generic": "role_generic", "source type": "source_type"}


def parse_predictions(text):
    """-> [{id, persona, prediction, grounding, source_flow, specificity, role_generic,
    source_type}]. Raises NotGradeable on a duplicate `P<k>` (FR-3.4): the pairing addresses
    a prediction by its id, so two rows under one id would grade one of them at random.

    `source type` (FR-1.4) is the channel the evidence behind the prediction came from. It is
    optional and defaults to `unknown`: every snapshot frozen before the field existed reads
    that way, and saying so is the point — an unknown channel is not a private one. Trailing
    fields this parser does not know stay ignored, so a newer snapshot still grades here.
    """
    out = prediction_rows(text)
    seen = set()
    for rec in out:
        if rec["id"] in seen:
            raise NotGradeable("duplicate prediction id %s in the snapshot" % rec["id"])
        seen.add(rec["id"])
    return out


def prediction_rows(text):
    """parse_predictions without the duplicate check: `pending` counts rows, it never grades."""
    body = section_body(text, "Predictions to verify")
    out = []
    for ln in (body or "").splitlines():
        m = PRED_RE.match(ln)
        if not m:
            continue
        parts = [p.strip() for p in m.group(2).split("|")]
        rec = {"id": m.group(1), "persona": parts[0] if parts else "",
               "prediction": parts[1] if len(parts) > 1 else "",
               "grounding": parts[2] if len(parts) > 2 else "",
               "source_flow": "review", "specificity": "", "role_generic": "no",
               "source_type": "unknown"}
        for p in parts[3:]:
            mk = re.match(r"(source flow|specificity|role-generic|source type)\s*:\s*(.+)$",
                          p, re.I)
            if mk:
                rec[PRED_FIELDS[mk.group(1).lower()]] = mk.group(2).strip().lower()
        out.append(rec)
    return out


CRITERIA_COLUMNS = {"persona": ("persona",), "context": ("context",),
                    "criterion": ("criterion",), "verdict": ("verdict",),
                    "evidence": ("evidence",), "check": ("evidence check", "check")}


def parse_criteria(text, ctx_name):
    """-> [row dict] for `## Criteria`, keyed `<slug>#c<n>`; None when the section is absent.

    The section is pasted from `panel --aggregate` unedited, and `panel` numbers a persona's
    criteria rows inside that persona's own round-1 block. A persona that returned two blocks
    therefore numbers two different rows alike, and the pasted table alone cannot say where
    the second block starts: it carries no marker for it.

    What this function can observe is narrower, and the refusal says only that: a persona
    whose criteria rows do not carry distinct criterion texts is marked ambiguous, and a
    `criterion:` line naming one of its keys is refused rather than graded against a guess.
    Two round-1 blocks are the usual cause, because both answer the same `## Judgment
    criteria`; a reviewer that returned two rows for one item inside a single block trips the
    same check, which is right — that key names two rows either way, and `panel`'s
    `criteria: <slug> returned N rows for M items` line is where that case is diagnosed.

    The residual it cannot see: if a second block *paraphrases* the criterion instead of
    repeating it, the texts differ, this check passes, and `#c<n>` resolves silently to the
    wrong row. Nothing in a pasted table can close that; paste the section unedited and read
    `panel`'s row-count line before freezing the snapshot.

    Rows of a persona named under `Personas rostered but absent:` are kept and counted like
    any other: the count is the pasted table's own row count, and someone else in the room
    can raise an absent persona's criterion. Only the round-1 and prediction ledgers drop an
    absent persona's rows, because only those carry a rate.
    """
    body = section_body(text, "Criteria")
    if body is None:
        return None
    head, raw = table(body)
    idx = column_index(head, CRITERIA_COLUMNS)
    if "persona" not in idx:
        return []
    out, seen = [], {}
    for cells in raw:
        cell = row_getter(cells, idx)
        slug = cell("persona")
        if not slug:
            continue
        seen[slug] = seen.get(slug, 0) + 1
        out.append({
            "key": "%s#c%d" % (slug, seen[slug]),
            "persona": slug,
            "context": cell("context") or ctx_name,
            "criterion": cell("criterion"),
            "verdict": (cell("verdict") or "").strip().lower(),
            "evidence": cell("evidence"),
            "check": (cell("check") or "unchecked").strip().lower(),
        })
    texts = {}
    for row in out:
        texts.setdefault(row["persona"], []).append(re.sub(r"\s+", " ", row["criterion"]).strip().lower())
    twice = set(slug for slug, t in texts.items() if len(set(t)) != len(t))
    for row in out:
        row["ambiguous"] = row["persona"] in twice
    return out


# ------------------------------------------------------------------------------ annotation
REAL_RE = re.compile(r"^\s*[-*]\s+(R\d+)\s*\|\s*(.*)$")
GREEN_OBS_RE = re.compile(r"^\s*[-*]\s+greenlight\s*:\s*([\w.-]+)\s*\|\s*observed\s+(.+?)\s*$", re.I)
# A greenlight line the shape above does not match used to be skipped in silence, and the
# slug then defaulted to `not observed` — an observation the user wrote down, gone without a
# word. The pairing file refuses an unreadable line for the same reason; here the run still
# grades, so the line is reported instead.
GREEN_ANY_RE = re.compile(r"^\s*[-*]\s+greenlight\s*:", re.I)


def split_list(value):
    if not value:
        return []
    v = value.strip()
    if v.lower() in ("none", "-", "(none)", "n/a"):
        return []
    return [p.strip() for p in re.split(r"[,;]", v) if p.strip()]


def parse_annotation(text, warnings=None):
    ann = {
        "meeting_held": field(text, "Meeting held") or "",
        "attendees": field(text, "Attendees") or "",
        # parentheticals go before the split, so a note with a comma stays one entry
        "absent": split_list(PAREN_RE.sub("", field(text, "Personas rostered but absent")
                                          or "")),
        "cutoff": parse_date(field(text, "Grading cut-off")),
        "reals": [],
        "green_observed": {},
    }
    for ln in text.splitlines():
        mg = GREEN_OBS_RE.match(ln)
        if mg:
            ann["green_observed"][mg.group(1)] = mg.group(2).strip().lower()
            continue
        if GREEN_ANY_RE.match(ln):
            if warnings is not None:
                warnings.append("greenlight line not read, so that slug counts as `not "
                                "observed`: %s — the shape is `- greenlight: <slug> | "
                                "observed <yes | no | not observed | not applicable>`"
                                % ln.strip())
            continue
        m = REAL_RE.match(ln)
        if not m:
            continue
        parts = [p.strip() for p in m.group(2).split("|")]
        rec = {"id": m.group(1), "who": parts[0] if parts else "",
               "objection": parts[1] if len(parts) > 1 else "",
               "part": parts[2] if len(parts) > 2 else "",
               "channel": "", "severity": "", "date": None}
        for p in parts[3:]:
            mk = re.match(r"(channel|actual severity|date)\s*:\s*(.+)$", p, re.I)
            if not mk:
                continue
            k, v = mk.group(1).lower(), mk.group(2).strip()
            if k == "channel":
                rec["channel"] = v
            elif k == "date":
                d = parse_date(v)
                rec["date"] = d.isoformat() if d else None
            else:
                rec["severity"] = v
        if any(r["id"] == rec["id"] for r in ann["reals"]):
            # Counted twice, one objection inflated both coverage terms (C4).
            raise NotGradeable("duplicate real objection id %s in the annotation" % rec["id"])
        ann["reals"].append(rec)
    return ann


PAREN_TAIL_RE = re.compile(r"\s*\([^()]*\)\s*$")
PAREN_RE = re.compile(r"\([^()]*\)")


def roster_slugs(text, rows, preds, greens, crit_rows):
    """Every persona the snapshot names: its `personas:` header and every section's slugs."""
    header = PAREN_RE.sub("", field(text, "personas") or "")
    slugs = set(split_list(header))
    slugs |= set(r["persona"] for r in rows) | set(p["persona"] for p in preds)
    slugs |= set(greens) | set(c["persona"] for c in (crit_rows or []))
    return sorted(s for s in slugs if s)


def resolve_absent(entries, roster, warnings):
    """FR-3.3: each `Personas rostered but absent:` entry, its trailing parenthetical
    stripped, resolved to a roster slug (exact, then persona_for). An entry that resolves to
    nothing is refused: ignored, it left the absent persona's rows in every denominator as
    unmitigated not-raised rows, and nothing said so."""
    out = set()
    for entry in entries:
        name = PAREN_TAIL_RE.sub("", entry).strip()
        if name in roster:
            out.add(name)
            continue
        slug, cands = persona_for(name, roster)
        if slug is None:
            raise NotGradeable("annotation names an absent persona not in the roster: %s"
                               % entry)
        if len(cands) > 1:
            warnings.append("absent `%s` could be any of %s; read as %s"
                            % (entry, ", ".join(cands), slug))
        out.add(slug)
    return out


# --------------------------------------------------------------------------------- pairing
KEY_RE = r"(P\d+|[A-Za-z0-9][\w.-]*#\d+)"
PAIR_RE = re.compile(r"^\s*" + KEY_RE + r"\s*\|\s*(R\d+)\s*\|\s*([\w, ]+?)\s*(?:\|\s*(.*))?$")
OVERRULED_RE = re.compile(r"^\s*overruled\s*:\s*" + KEY_RE + r"\s*\|\s*(.+?)\s*$", re.I)
UNMATCHED_RE = re.compile(r"^\s*unmatched real\s*:\s*(.*)$", re.I)
CRITERION_RE = re.compile(r"^\s*criterion\s*:\s*(.*)$", re.I)
CRITERION_LINE_RE = re.compile(
    r"^\s*criterion\s*:\s*(R\d+)\s*\|\s*(absent|[A-Za-z0-9][\w.-]*#c\d+)\s*$", re.I)
ISO_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}$")

# Closed set (FR-1.3): an untagged unmatched real is `new`, and anything else stops the run.
# Before this, an unknown tag read as a plain miss without saying so, which put an objection
# the persona already carried in the one column that is meant to indict the persona.
UNMATCHED_TAGS = ("blind spot", "known", "new")


def parse_pairing(text):
    """-> (pairs, {key: decided-on date}, {real id: class}, [{real, target}]).

    Every non-empty, non-comment line has to be one of the four forms. A line that is not
    understood stops the run instead of being skipped: a pair the script silently dropped
    would read downstream as a prediction nobody matched, which is a miss that never happened.
    """
    pairs, overruled, unmatched, criteria = [], {}, {}, []
    for ln in text.splitlines():
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        mo = OVERRULED_RE.match(s)
        if mo:
            # The FR-2.4 date gate decides whether the row leaves the denominator, so a date
            # the gate cannot read must never fall through to the branch that removes it.
            if not ISO_DATE_RE.match(mo.group(2).strip()):
                raise NotGradeable("overruled date must be YYYY-MM-DD: %s" % s)
            overruled[mo.group(1)] = mo.group(2).strip()
            continue
        mu = UNMATCHED_RE.match(s)
        if mu:
            for item in split_list(mu.group(1)):
                mi = re.match(r"^(R\d+)\s*(?:\((.+)\))?$", item.strip())
                if not mi:
                    raise NotGradeable("pairing line not understood: %s" % s)
                tag = (mi.group(2) or "new").strip().lower()
                if tag not in UNMATCHED_TAGS:
                    raise NotGradeable("pairing line not understood: %s (an unmatched tag "
                                       "must be %s)" % (s, " | ".join(UNMATCHED_TAGS)))
                unmatched[mi.group(1)] = tag
            continue
        if CRITERION_RE.match(s):
            mc = CRITERION_LINE_RE.match(s)
            if not mc:
                raise NotGradeable("pairing line not understood: %s (a criterion line is "
                                   "`criterion: R<j> | <slug>#c<n>` or "
                                   "`criterion: R<j> | absent`)" % s)
            criteria.append({"real": mc.group(1), "target": mc.group(2).lower()})
            continue
        mp = PAIR_RE.match(s)
        if not mp:
            raise NotGradeable("pairing line not understood: %s" % s)
        strength = mp.group(3).strip().lower().replace(", not matched", "")
        if strength not in STRENGTH_TOKENS:
            raise NotGradeable("pairing line not understood: %s (strength must be one of %s)"
                               % (s, " | ".join(STRENGTH_TOKENS)))
        pairs.append({"key": mp.group(1), "real": mp.group(2), "strength": strength,
                      "note": (mp.group(4) or "").strip()})
    return pairs, overruled, unmatched, criteria


# ----------------------------------------------------------------------------- the grading
def persona_for(who, slugs):
    """Attribute a real objection to the persona whose ground it was.

    -> (slug or None, [every slug that could have taken it]). The match is on the slug's own
    dash-separated parts, so `Lin` finds `budget-lin`; when two slugs could take it the first
    one sorted wins and the caller says so out loud, because a miss filed against the wrong
    persona is the one error this accounting cannot see afterwards.
    """
    w = (who or "").strip().lower()
    if not w:
        return None, []
    cands = [s for s in slugs if w == s.lower() or w in s.lower().split("-")]
    return (cands[0] if cands else None), cands


def count_cycles(log_text, slug):
    """Prior cycles for a slug: `## ` entries of calibration/log.md with a scoring row of its
    own. Counted on the table, never on the prose: the Notes line names absent personas and
    excluded rows, and a name in a sentence is not a cycle that persona was graded on."""
    if not log_text:
        return 0
    blocks = re.split(r"^##\s+", log_text, flags=re.M)[1:]
    pat = re.compile(r"^\|\s*%s\s*\|" % re.escape(slug), re.M)
    return sum(1 for b in blocks if pat.search(b))


def overrule_status(date_str, meeting, doc_changed):
    """FR-2.4's date gate. -> 'removed' | 'retroactive' | 'still gradeable'.

    `removed` (out of the denominator) needs both halves: decided before the meeting **and**
    the anchor text gone. The date is validated when the pairing is read, so an unreadable one
    can never arrive here and fall through to `removed`.
    """
    d = parse_date(date_str)
    if d is None:
        return "still gradeable"
    if d >= meeting:
        return "retroactive"
    return "removed" if (doc_changed or "").strip().lower().startswith("yes") else "still gradeable"


def mitigation_split(doc_changed):
    """FR-2.4's covariate. -> the outcome of an unmatched gradeable row."""
    if (doc_changed or "").strip().lower().startswith(("yes", "partial")):
        return "not-raised (mitigated)"
    return "not-raised (unmitigated)"


def tally(rows, key, default="unknown", strengths=HEADLINE):
    """-> {value: [hits, n]} over `rows`, in first-appearance order (FR-1.4).

    One helper for every split of the predictions ledger — source flow, source type,
    grounding section — because three loops that count the same thing drift apart, and the
    grounding split is the 0.2 deferred item this closes. A hit is headline strength unless
    `strengths` says otherwise (FR-3.5): the loose-inclusive figure is the upper bound,
    printed beside the headline one and never instead of it.
    """
    out = {}
    for row in rows:
        pair = out.setdefault((row.get(key) or "").strip() or default, [0, 0])
        pair[1] += 1
        if row["strength"] in strengths:
            pair[0] += 1
    return out


def criterion_outcome(verdict, raised):
    """FR-2.4's 2x2: the snapshot's own verdict against what the meeting raised."""
    accepted = (verdict or "").strip().lower() == "met"
    if raised:
        return "miss (criterion present, accepted by declaration)" if accepted \
            else "flagged, raised"
    return "accepted, not raised" if accepted else "flagged, not raised"


def gradeable_reason(row, absent, ev_context):
    """Why this round-1 row is not gradeable, or None. The overruled gate is not here: it
    needs the meeting date and runs after this one (see overrule_status)."""
    if row["persona"] in absent:
        return "excluded: rostered but absent"
    if not ROUND1_RE.fullmatch(row["round"].strip()):
        return "context: round after the first"
    ev = (row["event"] or "").strip().lower()
    if ev and ev in ev_context and ev_context[ev] != row["context"]:
        return "context: event %s belongs to %s, not %s" % (row["event"], ev_context[ev],
                                                            row["context"])
    return None


def greenlight_cell(predicted, observed):
    """FR-2.3's 2x2. -> the cell this green light lands in.

    `not observed` / `not applicable` sit outside the table by construction; a prediction that
    is neither YES nor NO (`INSUFFICIENT_BASIS`, `descriptive only`) is `not gradeable` and is
    counted there rather than dropped, so the four observations always add up to the roster.
    """
    obs = (observed or "not observed").strip().lower()
    if obs in ("not observed", "not applicable"):
        return obs
    pred = (predicted or "").strip().upper()
    if pred not in ("YES", "NO") or obs not in ("yes", "no"):
        return "not gradeable"
    return "%s/%s" % (pred, obs)


def cycles_word(n):
    return "%d cycle%s" % (n, "" if n == 1 else "s")


def running_line(cycles, hits, gradeable, covered, own_reals):
    """The `running: cycles / counts` cell, and the body of the Reliability one-liner.

    Precision is the persona's own rows (`hits` over `gradeable`); coverage is the persona's
    own real objections (`covered` over `own_reals`, FR-3.2) — two populations, never mixed."""
    if cycles >= MIN_CYCLES:
        prec = "n/a" if not gradeable else "%d%%" % round(100.0 * hits / gradeable)
        cov = "n/a" if not own_reals else "%d%%" % round(100.0 * covered / own_reals)
        return "%s: precision %s, coverage %s" % (cycles_word(cycles), prec, cov)
    return "%s: %d/%d" % (cycles_word(cycles), hits, gradeable)


def read_ledger(ledger_text, snap_path, snap_text, warnings):
    """Validate a reconstructed ledger against the snapshot it stands for (FR-1.1).

    -> the `reconstructed:` date. Raises NotGradeable on every way the pairing of the two
    files can be wrong, because the ledger is written after the meeting: the only things
    holding it to the frozen record are the date it says it was written on and the sha1 of
    the file it was read from, and a ledger that states neither is an assertion, not evidence.
    """
    reconstructed = parse_date(field(ledger_text, "reconstructed"))
    if reconstructed is None:
        raise NotGradeable("ledger has no reconstructed: date (YYYY-MM-DD) — a ledger written "
                           "after the meeting must say when")
    declared = (field(ledger_text, "snapshot sha1") or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{40}", declared):
        raise NotGradeable("ledger has no snapshot sha1:")
    actual = hashlib.sha1(snap_path.read_bytes()).hexdigest()
    if declared != actual:
        raise NotGradeable("ledger snapshot sha1 %s does not match calibration/%s (%s): the "
                           "frozen text changed after the ledger was written"
                           % (declared[:SHA_PREFIX], snap_path.name, actual[:SHA_PREFIX]))
    if parse_date(field(ledger_text, "frozen")) is None:
        raise NotGradeable("ledger has no frozen: date — transcribe it from the snapshot, the "
                           "pre-registration gate cannot run without it")
    # `--ledger` works on any snapshot, not only a pre-0.2 one, so the warning states the
    # format it actually found instead of asserting the usual case.
    warnings.append("ledger reconstructed on %s from a %s snapshot — the rows were "
                    "transcribed after the meeting; the frozen text is calibration/%s "
                    "(sha1 %s)" % (reconstructed.isoformat(), snapshot_format(snap_text),
                                   snap_path.name, actual[:SHA_PREFIX]))
    return reconstructed


def grade(ctx_dir, ctx_name, doc, snap_path, ann_text, pair_text, store_root,
          ledger_path=None):
    """Validate, then count. Raises NotGradeable (exit 2). -> a result dict."""
    warnings = []
    snap_text = read_text_lenient(snap_path)
    text = snap_text
    reconstructed = None
    if ledger_path is not None:
        ledger_text = read_text_lenient(ledger_path)
        reconstructed = read_ledger(ledger_text, snap_path, snap_text, warnings)
        text = ledger_text          # header fields, sections and events all come from it now
    elif field(snap_text, "reconstructed"):
        # A ledger copied over the snapshot would otherwise grade as an ordinary cycle: no
        # sha1 pin to the text it was transcribed from, and no reconstruction note anywhere
        # in the log. The `reconstructed:` line is what a ledger always carries, so it is
        # also what refuses it here.
        raise NotGradeable("%s carries a reconstructed: line — that is a ledger, not a frozen "
                           "snapshot: keep the snapshot it was transcribed from and grade it "
                           "with --ledger" % snap_path.name)
    # Snapshot field names are locale data (FR-4.4), fetched here and never at import time.
    snap_fields = locale_regexes()["snapshot_fields"]

    # Precedence: the snapshot's own meeting date if it parses, else the ledger's. The
    # snapshot is the file of record and the one `pending --set-meeting` writes, so a date
    # moved there must not be shadowed by a date transcribed into the ledger earlier.
    meeting = parse_date(field(snap_text, *snap_fields["meeting"]))
    if meeting is None:
        meeting = parse_date(field(text, *snap_fields["meeting"]))
    if meeting is None:
        raise NotGradeable("no meeting date in %s — record it: beforehand.py pending "
                           "--context %s --set-meeting %s YYYY-MM-DD"
                           % (snap_path.name, ctx_name, doc))
    # Same precedence as `meeting:` above, and for the same reason: the pre-registration gate
    # is about the frozen record, so a date transcribed into the ledger may fill a prose date
    # in that does not parse but may never soften the snapshot's own.
    frozen = parse_date(field(snap_text, "frozen")) or parse_date(field(text, "frozen"))
    if frozen is not None and frozen >= meeting:
        raise NotGradeable("snapshot frozen on or after the meeting (frozen %s, meeting %s): "
                           "the predictions are not pre-registered"
                           % (frozen.isoformat(), meeting.isoformat()))

    control = (field(text, "control") or "no").strip().lower()
    control = "yes" if control.startswith("yes") else "no"

    # sha1: a warning, never a refusal — the predictions were about the earlier text.
    doc_path_raw = field(text, *snap_fields["document"]) or doc
    sha_declared = (field(text, "sha1") or "").strip()
    changed, found = document_state(doc_path_raw, sha_declared, ctx_dir)
    if found is None:
        warnings.append("document not found: cannot verify sha1 (%s) — grading proceeds, but "
                        "nothing here proves these predictions were about the text that was "
                        "sent" % doc_path_raw)
    elif changed is None:
        warnings.append("no usable sha1 in the snapshot: cannot verify the document")
    if changed:
        warnings.append("document changed after review — the predictions were about the "
                        "version that carried sha1 %s" % sha_declared[:SHA_PREFIX])

    ann = parse_annotation(ann_text, warnings)
    held = (ann["meeting_held"] or "").strip().lower()
    if held and not held.startswith("yes"):
        warnings.append("the annotation says the meeting was `%s`: whatever is graded below "
                        "did not come from the event the snapshot pre-registered" % held)
    rows = parse_round1(text, ctx_name, warnings)
    preds = parse_predictions(text)
    greens = parse_green_lights(text)
    events = parse_events(text)
    crit_rows = parse_criteria(text, ctx_name)
    pairs, overruled, unmatched, crit_pairs = parse_pairing(pair_text)
    roster = roster_slugs(text, rows, preds, greens, crit_rows)
    absent = resolve_absent(ann["absent"], roster, warnings)
    for slug in ann["green_observed"]:
        if slug not in roster:
            raise NotGradeable("greenlight names a persona not in the roster: %s" % slug)
    # The same `criterion:` line written twice is one judgment, not two. `absent from the
    # persona` is a count of criteria the meeting raised that no persona row carries, and a
    # line repeated by hand would raise it without anything having been raised twice.
    seen_crit, unique_crit = set(), []
    for cp in crit_pairs:
        if (cp["real"], cp["target"]) in seen_crit:
            continue
        seen_crit.add((cp["real"], cp["target"]))
        unique_crit.append(cp)
    crit_pairs = unique_crit

    row_by_key = dict((r["key"], r) for r in rows)
    pred_by_id = dict((p["id"], p) for p in preds)
    real_by_id = dict((r["id"], r) for r in ann["reals"])
    crit_by_key = dict((c["key"], c) for c in (crit_rows or []))

    # --- validation: every key and every real id must exist, and the map is one-to-one.
    for key in [p["key"] for p in pairs] + list(overruled):
        if key not in row_by_key and key not in pred_by_id:
            raise NotGradeable("pairing references unknown key %s: it names no "
                               "## Round-1 objections row and no ## Predictions to verify item"
                               % key)
    for cp in crit_pairs:
        if cp["target"] == "absent":
            continue
        crow = crit_by_key.get(cp["target"])
        if crow is None:
            raise NotGradeable("pairing references unknown key %s: it names no ## Criteria "
                               "row in the snapshot" % cp["target"])
        if crow["ambiguous"]:
            raise NotGradeable("pairing references ambiguous key %s: the pasted table names "
                               "this key twice (a persona that returned two round-1 blocks "
                               "restarts the numbering)" % cp["target"])
    for rid in ([p["real"] for p in pairs] + list(unmatched)
                + [c["real"] for c in crit_pairs]):
        if rid not in real_by_id:
            raise NotGradeable("pairing references unknown key %s: the annotation lists no "
                               "such real objection" % rid)
    # One-to-one holds inside each ledger, not across them: the round-1 table and the
    # predictions ledger are graded apart (SPEC-0.1 FR-2.5) and coverage counts only the
    # round-1 matches, so one real objection may satisfy one row and one `P<k>` at once.
    claimed_real = {"rows": {}, "preds": {}}
    claimed_key = {}
    strength_by_key = {}      # key -> the strength of its one counted match (S8: built once)
    for pr in pairs:
        if pr["strength"] not in STRENGTHS:
            continue
        block = "rows" if pr["key"] in row_by_key else "preds"
        held = claimed_real[block]
        if pr["real"] in held:
            raise NotGradeable("pairing not one-to-one: %s is matched twice inside the same "
                               "ledger, by %s and by %s — mark the second `related` or drop it"
                               % (pr["real"], held[pr["real"]], pr["key"]))
        if pr["key"] in claimed_key:
            raise NotGradeable("pairing not one-to-one: %s matches both %s and %s"
                               % (pr["key"], claimed_key[pr["key"]], pr["real"]))
        held[pr["real"]] = pr["key"]
        claimed_key[pr["key"]] = pr["real"]
        strength_by_key[pr["key"]] = pr["strength"]

    # --- which real objections are graded at all
    cutoff = ann["cutoff"]
    late = []
    for r in ann["reals"]:
        d = parse_date(r["date"]) if r["date"] else None
        r["late"] = bool(cutoff and d and d > cutoff)
        if r["late"]:
            late.append(r["id"])
    graded_reals = [r for r in ann["reals"] if not r["late"]]
    # The cut-off is one rule, applied once: a real objection that arrived after it is noted
    # and sits in no denominator — the criteria ledger included. Dropping the line here is
    # what keeps that true at every place it is consumed (the raised keys, the `absent`
    # count, the real's own outcome), rather than repeating the test at each of them.
    late_ids = set(late)
    dropped_crit = sorted(set(c["real"] for c in crit_pairs if c["real"] in late_ids))
    if dropped_crit:
        warnings.append("criterion: line on %s ignored: that real objection arrived after the "
                        "grading cut-off %s and is noted, not graded"
                        % (", ".join(dropped_crit), cutoff.isoformat() if cutoff else "?"))
    crit_pairs = [c for c in crit_pairs if c["real"] not in late_ids]

    ev_context = dict((lbl.lower(), cx) for lbl, cx, _d in events)

    # --- row by row
    edits = 0
    other_context, effective_overrules, retroactive = [], [], []
    still_gradeable_overrules = []
    for r in rows:
        key = r["key"]
        r["match"] = claimed_key.get(key)
        r["strength"] = strength_by_key.get(key)
        why = gradeable_reason(r, absent, ev_context)
        if why == "context: round after the first":
            edits += 1
        elif why and why.startswith("context: event"):
            other_context.append((key, r["event"], ev_context[r["event"].strip().lower()]))
        elif why is None and key in overruled:
            status = overrule_status(overruled[key], meeting, r["doc_changed"])
            if status == "retroactive":
                retroactive.append((key, overruled[key]))
            elif status == "removed":
                why = "overruled before the meeting, anchor text removed"
                effective_overrules.append((key, overruled[key]))
            else:
                r["overruled_still_gradeable"] = overruled[key]
                still_gradeable_overrules.append((key, overruled[key]))
        r["gradeable"] = why is None
        r["why_not"] = why
        if not r["gradeable"]:
            r["outcome"] = why
        elif r["match"]:
            r["outcome"] = "hit (%s)" % r["strength"]
        else:
            r["outcome"] = mitigation_split(r["doc_changed"])
    edits += len(table(section_body(text, "Applied before sending"))[1])

    # --- the predictions ledger, graded apart
    for pd in preds:
        pd["absent"] = pd["persona"] in absent
        pd["match"] = claimed_key.get(pd["id"])
        pd["strength"] = strength_by_key.get(pd["id"])
        related = [p for p in pairs if p["key"] == pd["id"] and p["strength"] == "related"]
        if pd["absent"]:
            pd["outcome"] = "excluded: rostered but absent"
        elif pd["match"]:
            pd["outcome"] = "hit (%s)" % pd["strength"]
        elif related:
            pd["outcome"] = "related, not matched (%s)" % related[0]["real"]
        else:
            pd["outcome"] = "not-raised"

    # --- misses: a graded real neither ledger matched
    slugs = [r["persona"] for r in rows] + [p["persona"] for p in preds]
    slugs = sorted(set(s for s in slugs if s))
    ambiguous = set()

    def attribute(who):
        slug, cands = persona_for(who, slugs)
        if len(cands) > 1 and who not in ambiguous:
            ambiguous.add(who)
            warnings.append("`%s` could be any of %s; attributed to %s — say who it was in "
                            "the annotation if that is wrong"
                            % (who, ", ".join(cands), slug))
        return slug

    strength_of = strength_by_key.__getitem__

    # A real objection may carry `criterion:` lines as well as a match; they refine the
    # outcome of a miss and never overwrite a match, because a criterion the panel flagged is
    # not an alternative account of an objection a round-1 row did predict.
    crit_absent_for = {}
    crit_accepted_for = {}
    for cp in crit_pairs:
        if cp["target"] == "absent":
            crit_absent_for.setdefault(cp["real"], True)
        elif crit_by_key[cp["target"]]["verdict"] == "met":
            crit_accepted_for.setdefault(cp["real"], cp["target"])

    for r in ann["reals"]:
        r["attributed"] = attribute(r["who"])
        r["miss_class"] = None
        r["blind_spot"] = unmatched.get(r["id"], "") == "blind spot" and not r["late"]
        r["matched_by_row"] = None if r["late"] else claimed_real["rows"].get(r["id"])
        r["matched_by_pred"] = None if r["late"] else claimed_real["preds"].get(r["id"])
        r["matched_by"] = r["matched_by_row"] or r["matched_by_pred"]
        if r["late"]:
            r["outcome"] = "noted, not graded: after the grading cut-off %s" % (
                cutoff.isoformat() if cutoff else "?")
            continue
        if r["matched_by_row"]:
            r["outcome"] = "matched %s by %s (round 1)" % (strength_of(r["matched_by_row"]),
                                                           r["matched_by_row"])
            if r["matched_by_pred"]:
                r["outcome"] += "; also %s by %s (ledger)" % (
                    strength_of(r["matched_by_pred"]), r["matched_by_pred"])
            continue
        if r["matched_by_pred"]:
            r["outcome"] = "matched %s by %s (ledger)" % (strength_of(r["matched_by_pred"]),
                                                          r["matched_by_pred"])
            continue
        r["miss_class"] = unmatched.get(r["id"], "new")
        if r["blind_spot"]:
            r["outcome"] = "miss (declared blind spot)"
        elif r["id"] in crit_absent_for:
            r["outcome"] = "miss (criterion absent from the persona)"
        elif r["id"] in crit_accepted_for:
            r["outcome"] = ("miss (criterion present, accepted by declaration: %s)"
                            % crit_accepted_for[r["id"]])
        elif r["miss_class"] == "known":
            r["outcome"] = "miss (known, in the persona)"
        else:
            r["outcome"] = "miss"

    # --- per persona
    log_path = ctx_dir / "calibration/log.md"
    log_text = read_text_lenient(log_path) if log_path.is_file() else ""
    people = sorted(set(r["persona"] for r in rows if r["persona"] not in absent))
    for r in graded_reals:
        if r["attributed"] and r["attributed"] not in absent and r["attributed"] not in people:
            people.append(r["attributed"])
    people = sorted(set(people))

    per = []
    for slug in people:
        mine = [r for r in rows if r["persona"] == slug and r["gradeable"]]
        hits_headline = sum(1 for r in mine if r["strength"] in HEADLINE)
        hits_loose = sum(1 for r in mine if r["strength"] == "loose")
        mine_reals = [r for r in graded_reals
                      if r["attributed"] == slug and not r["matched_by"]]
        misses = [r for r in mine_reals if r["miss_class"] == "new"]
        known = [r for r in mine_reals if r["miss_class"] == "known"]
        blinds = [r for r in mine_reals if r["miss_class"] == "blind spot"]
        # FR-3.2: coverage is about the persona's own objections, numerator and denominator
        # alike: every graded real attributed to the persona is in the denominator, and it
        # is covered when a round-1 row of ANY persona matched it at headline strength (a hit
        # on another persona's objection counts for the predicting row's precision and for
        # the raiser's coverage). A loose or ledger-only match covers nothing.
        own_reals = [r for r in graded_reals if r["attributed"] == slug]
        own_covered = sum(1 for r in own_reals if r["matched_by_row"]
                          and strength_by_key[r["matched_by_row"]] in HEADLINE)
        cycles = count_cycles(log_text, slug) + 1
        gl = greens.get(slug, "—")
        obs = ann["green_observed"].get(slug, "not observed")
        per.append({
            "persona": slug,
            "context": next((r["context"] for r in rows if r["persona"] == slug), ctx_name),
            "gradeable": len(mine),
            "hits_headline": hits_headline,
            "hits_loose": hits_loose,
            "misses": len(misses),
            "misses_known": len(known),
            "blind_spots": len(blinds),
            "not_raised_mitigated": sum(1 for r in mine if r["outcome"] == "not-raised (mitigated)"),
            "not_raised_unmitigated": sum(1 for r in mine
                                          if r["outcome"] == "not-raised (unmitigated)"),
            "overruled": sum(1 for k, _d in effective_overrules if k.startswith(slug + "#")),
            "greenlight": "%s/%s" % (gl, obs),
            "cycles": cycles,
            "running": running_line(cycles, hits_headline, len(mine), own_covered,
                                    len(own_reals)),
        })

    # --- panel rates
    gradeable_rows = [r for r in rows if r["gradeable"]]
    hits_h = sum(1 for r in gradeable_rows if r["strength"] in HEADLINE)
    hits_l = sum(1 for r in gradeable_rows if r["strength"] == "loose")
    # One definition of "covered" across the report: a headline round-1 match, with the
    # loose-inclusive count beside it as the upper bound, exactly as for precision.
    covered_l = [r for r in graded_reals if r["matched_by_row"]]
    covered = sum(1 for r in covered_l if strength_by_key[r["matched_by_row"]] in HEADLINE)
    rg_rows = [r for r in gradeable_rows if r["role_generic"] == "no"]
    rg_hits = sum(1 for r in rg_rows if r["strength"] in HEADLINE)
    rg_loose = sum(1 for r in rg_rows if r["strength"] == "loose")

    ledger_rows = [p for p in preds if not p["absent"]]
    ledger = {"hits": sum(1 for p in ledger_rows if p["strength"] in HEADLINE),
              "hits_loose_inclusive": sum(1 for p in ledger_rows if p["strength"] in STRENGTHS),
              "gradeable": len(ledger_rows)}
    for name, key, default in (("by_source_flow", "source_flow", "review"),
                               ("by_source_type", "source_type", "unknown"),
                               ("by_grounding", "grounding", "unknown")):
        ledger[name] = tally(ledger_rows, key, default)
        ledger[name + "_loose_inclusive"] = tally(ledger_rows, key, default, STRENGTHS)
    ledger["base_rate_items"] = sum(1 for p in ledger_rows if p["role_generic"] == "yes")

    # --- the criteria ledger, graded apart again: counts only, never a rate
    raised_keys = set(c["target"] for c in crit_pairs if c["target"] != "absent")
    crit_out = []
    for c in (crit_rows or []):
        row = dict(c)
        row["raised"] = c["key"] in raised_keys
        row["outcome"] = criterion_outcome(c["verdict"], row["raised"])
        crit_out.append(row)
    crit_counts = {
        "in_snapshot": crit_rows is not None,
        "rows": len(crit_out),
        "flagged_raised": sum(1 for c in crit_out if c["outcome"] == "flagged, raised"),
        "accepted_raised": sum(1 for c in crit_out if c["outcome"].startswith("miss (")),
        "flagged_not_raised": sum(1 for c in crit_out
                                  if c["outcome"] == "flagged, not raised"),
        "accepted_not_raised": sum(1 for c in crit_out
                                   if c["outcome"] == "accepted, not raised"),
        "absent": sum(1 for c in crit_pairs if c["target"] == "absent"),
    }

    gl_cells = {"YES/yes": 0, "YES/no": 0, "NO/yes": 0, "NO/no": 0,
                "not observed": 0, "not applicable": 0, "not gradeable": 0}
    for slug, predicted in sorted(greens.items()):
        cell = greenlight_cell(predicted, ann["green_observed"].get(slug))
        if slug in absent and cell not in ("not observed", "not applicable"):
            cell = "not gradeable"   # absent: never in the 2x2, but never dropped either
        gl_cells[cell] += 1

    min_cycles = min([p["cycles"] for p in per] or [0])
    return {
        "context": ctx_name, "document": doc, "store": str(store_root),
        "snapshot": snap_path.name,
        "snapshot_sha1": hashlib.sha1(snap_path.read_bytes()).hexdigest(),
        "meeting": meeting.isoformat(), "meeting_held": ann["meeting_held"],
        "attendees": ann["attendees"], "control": control,
        "document_changed": changed, "warnings": warnings,
        "absent": sorted(absent), "cutoff": cutoff.isoformat() if cutoff else None,
        "late": late, "panel_driven_edits": edits, "other_context_rows": other_context,
        "effective_overrules": effective_overrules, "retroactive_overrules": retroactive,
        "still_gradeable_overrules": still_gradeable_overrules,
        "rows": rows, "reals": ann["reals"], "predictions": preds, "personas": per,
        "green_lights": gl_cells,
        "criteria": crit_out, "criteria_counts": crit_counts,
        "misses_by_class": dict(
            (cls, sum(1 for r in graded_reals if r["miss_class"] == cls))
            for cls in UNMATCHED_TAGS),
        "rates": {
            "precision": [hits_h, len(gradeable_rows)],
            "loose_inclusive": [hits_h + hits_l, len(gradeable_rows)],
            "coverage": [covered, len(graded_reals)],
            "coverage_loose_inclusive": [len(covered_l), len(graded_reals)],
            "role_generic_restricted": [rg_hits, len(rg_rows)],
            "role_generic_loose_inclusive": [rg_hits + rg_loose, len(rg_rows)],
            "role_generic_source": "control" if control == "yes" else "estimated",
            "below_minimum_n": min_cycles < MIN_CYCLES,
            "minimum_n": MIN_CYCLES,
        },
        "ledger": ledger,
        "limits": (LIMITS.rstrip(".") + "; this cycle's ledger was reconstructed after the "
                   "meeting." if reconstructed else LIMITS),
        "ledger_reconstructed": reconstructed.isoformat() if reconstructed else None,
        "ledger_file": ledger_path.name if ledger_path is not None else None,
        "applied": False,
    }


# ---------------------------------------------------------------------------------- output
def criteria_line(counts):
    """FR-2.4's one line, printed under the criteria ledger and appended to the log Notes."""
    return ("criteria: %d rows · flagged and raised %d · accepted and raised %d (present, by "
            "declaration) · absent from the persona %d"
            % (counts["rows"], counts["flagged_raised"], counts["accepted_raised"],
               counts["absent"]))


def split_items(counts, loose, sep, always=None):
    """`<value> h/n (loose-inclusive l/n)` per value, in first-appearance order (FR-3.5).
    `always` is a value shown even when no row carries it, so `unknown 0/0` says out loud
    that nothing was recorded."""
    items = list(counts.items())
    if always is not None and always not in counts:
        items.append((always, [0, 0]))
    return sep.join("%s %d/%d (loose-inclusive %d/%d)"
                    % (k, v[0], v[1], loose.get(k, [0, 0])[0], v[1]) for k, v in items)


def tally_line(label, counts, loose, always=None):
    """`<label>: <split items>`, or `<label>: none`."""
    body = split_items(counts, loose, " · ", always)
    return "%s: %s" % (label, body or "none")


LOG_HEADER = ("| Persona | context | hits (exact+substantive / loose) | misses attributable | "
              "miss (blind spot) | not-raised (mitigated / unmitigated) | overruled | "
              "greenlight predicted/observed | control | running: cycles / counts |")


def persona_row(p, control):
    """One per-persona table row: the log entry and the screen print the same line (S8)."""
    return "| %s | %s | %d/%d | %d | %d | %d/%d | %d | %s | %s | %s |" % (
        p["persona"], p["context"], p["hits_headline"], p["hits_loose"], p["misses"],
        p["blind_spots"], p["not_raised_mitigated"], p["not_raised_unmitigated"],
        p["overruled"], p["greenlight"], control, p["running"])


def log_entry(res, today):
    """The pinned `calibration/log.md` block, as `--apply` appends it."""
    out = ["## %s — %s (snapshot %s)" % (today.isoformat(), res["document"],
                                         res["snapshot_sha1"][:SHA_PREFIX]),
           LOG_HEADER, "|" + "---|" * 10]
    out += [persona_row(p, res["control"]) for p in res["personas"]]
    r = res["rates"]
    notes = ["%d gradeable rows" % r["precision"][1],
             "%d distinct real objections graded%s" % (
                 r["coverage"][1],
                 ", %d noted after the grading cut-off" % len(res["late"]) if res["late"] else ""),
             "precision %d/%d exact+substantive, %d/%d loose-inclusive" % (
                 r["precision"][0], r["precision"][1],
                 r["loose_inclusive"][0], r["loose_inclusive"][1]),
             "coverage %d/%d exact+substantive, %d/%d loose-inclusive" % (
                 r["coverage"][0], r["coverage"][1],
                 r["coverage_loose_inclusive"][0], r["coverage_loose_inclusive"][1]),
             "role-generic: no restricted %d/%d (control: %s)" % (
                 r["role_generic_restricted"][0], r["role_generic_restricted"][1], res["control"]),
             "panel-driven edits: %d" % res["panel_driven_edits"]]
    # Every fragment below is conditional, so a cycle that uses none of the 0.3 accounting
    # writes the entry 0.2 pinned, byte for byte.
    if res["misses_by_class"]["known"]:
        notes.append("misses in the persona but not listed: %d"
                     % res["misses_by_class"]["known"])
    if any(k != "unknown" for k in res["ledger"]["by_source_type"]):
        notes.append("ledger by source type: "
                     + split_items(res["ledger"]["by_source_type"],
                                   res["ledger"]["by_source_type_loose_inclusive"], ", "))
    if res["criteria_counts"]["in_snapshot"]:
        notes.append(criteria_line(res["criteria_counts"]))
    for label, items in (("overruled out of the denominator", res["effective_overrules"]),
                         ("retroactive overrules, they moved nothing",
                          res["retroactive_overrules"]),
                         ("overruled but still gradeable, the anchor text stayed",
                          res["still_gradeable_overrules"])):
        if items:
            notes.append("%s: %s" % (label, ", ".join("%s (%s)" % (k, d) for k, d in items)))
    if res["absent"]:
        notes.append("excluded from the denominators: %s"
                     % ", ".join("%s (rostered but absent)" % s for s in res["absent"]))
    if res["document_changed"]:
        notes.append("document changed after review")
    if res.get("ledger_reconstructed"):
        notes.append("ledger reconstructed on %s" % res["ledger_reconstructed"])
    tail = (" Below the %d-cycle floor: counts only, no rate." % MIN_CYCLES
            if r["below_minimum_n"] else "")
    out.append("")
    out.append("Notes: " + "; ".join(notes) + "." + tail)
    return "\n".join(out) + "\n"


def reliability_diff(ctx_dir, slug, running, cycles):
    """A unified diff of the persona's Reliability one-liner. Printed, never written."""
    path = ctx_dir / "personas" / (slug + ".md")
    if not path.is_file():
        return None
    old = read_text_lenient(path)
    line = "- " + running + ("" if cycles >= MIN_CYCLES else " — n too small to interpret")
    sec = next((s for s in sections(old) if s.title.lower() == "reliability"), None)
    if sec is None:
        new = old.rstrip("\n") + "\n\n## Reliability\n" + line + "\n"
    else:
        new = old[:sec.body_start] + line + "\n" + old[sec.end:]
    if new == old:
        return None
    rel = "personas/%s.md" % slug
    return "\n".join(difflib.unified_diff(old.splitlines(), new.splitlines(),
                                          "a/" + rel, "b/" + rel, lineterm="", n=1))


def fraction(pair):
    return "%d/%d" % (pair[0], pair[1])


def render(res, applied_lines):
    r = res["rates"]
    L = ["beforehand · calibrate · store %s · context %s · %s"
         % (res["store"], res["context"], res["document"])]
    for w in res["warnings"]:
        L.append("warning: " + w)
    L.append("meeting %s (held: %s) · attendees: %s"
             % (res["meeting"], res["meeting_held"] or "?", res["attendees"] or "?"))

    L += ["", "## Per-persona accounting", LOG_HEADER, "|" + "---|" * 10]
    L += [persona_row(p, res["control"]) for p in res["personas"]]
    if res["absent"]:
        L.append("excluded from the denominators: "
                 + ", ".join("%s (rostered but absent)" % s for s in res["absent"]))
    L.append("not graded, context never a rate — panel-driven edits: %d"
             % res["panel_driven_edits"])
    for key, label, cx in res["other_context_rows"]:
        L.append("not graded: %s sits on event %s, which %s attended and this context did not"
                 % (key, label, cx))
    for key, d in res["effective_overrules"]:
        L.append("overruled out of the denominator: %s (decided %s, before the meeting, and the "
                 "anchor text was removed)" % (key, d))
    for key, d in res["retroactive_overrules"]:
        L.append("retroactive overrule, it moves nothing: %s (decided %s, on or after the "
                 "meeting)" % (key, d))
    for key, d in res["still_gradeable_overrules"]:
        L.append("overruled but still gradeable: %s (decided %s, the anchor text stayed)"
                 % (key, d))

    L += ["", "## Rates",
          "precision: %s (hits over gradeable rows, exact+substantive) · loose-inclusive: %s "
          "(upper bound)" % (fraction(r["precision"]), fraction(r["loose_inclusive"])),
          "coverage: %s (real objections a round-1 row matched over every real objection "
          "graded, exact+substantive) · loose-inclusive: %s (upper bound)"
          % (fraction(r["coverage"]), fraction(r["coverage_loose_inclusive"])),
          "role-generic: no restricted: %s (%s) · loose-inclusive %s"
          % (fraction(r["role_generic_restricted"]), r["role_generic_source"],
             fraction(r["role_generic_loose_inclusive"]))]
    if r["below_minimum_n"]:
        L.append("n too small to interpret: under %d cycles for a persona, counts only, never a "
                 "percentage" % MIN_CYCLES)

    g = res["green_lights"]
    L += ["", "## Green lights (their own 2x2, counts only, never pooled with objections)",
          "predicted YES / observed yes: %d" % g["YES/yes"],
          "predicted YES / observed no: %d" % g["YES/no"],
          "predicted NO / observed yes: %d" % g["NO/yes"],
          "predicted NO / observed no: %d" % g["NO/no"],
          "outside the table — not observed: %d · not applicable: %d · not gradeable: %d "
          "(no YES/NO predicted, or the persona was absent)"
          % (g["not observed"], g["not applicable"], g["not gradeable"])]

    L += ["", "## Predictions ledger (graded apart: no anchor quote, looser match)",
          "| Prediction | Persona | Source flow | Specificity | Outcome |", "|" + "---|" * 5]
    for p in res["predictions"]:
        L.append("| %s | %s | %s | %s | %s |" % (p["id"], p["persona"], p["source_flow"],
                                                 p["specificity"] or "?", p["outcome"]))
    lg = res["ledger"]
    L.append("ledger rate: %d/%d (exact+substantive) · loose-inclusive: %d/%d (upper bound)"
             % (lg["hits"], lg["gradeable"], lg["hits_loose_inclusive"], lg["gradeable"]))
    for label, name, always in (("by source flow", "by_source_flow", None),
                                ("by source type", "by_source_type", "unknown"),
                                ("by grounding section", "by_grounding", None)):
        L.append(tally_line(label, lg[name], lg[name + "_loose_inclusive"], always))
    L.append("base-rate items (role-generic: yes): %d" % lg["base_rate_items"])

    cc = res["criteria_counts"]
    if cc["in_snapshot"] or cc["absent"]:
        L += ["", "## Criteria ledger (graded apart: verdict against what the meeting "
              "raised, counts only)",
              "| Key | Persona | Verdict | Evidence check | Outcome |", "|" + "---|" * 5]
        for c in res["criteria"]:
            L.append("| %s | %s | %s | %s | %s |" % (c["key"], c["persona"],
                                                     c["verdict"] or "?", c["check"],
                                                     c["outcome"]))
        L.append(criteria_line(cc))

    L += ["", "## Real objections", "| Real | Who | Attributed | Outcome |", "|" + "---|" * 4]
    for rr in res["reals"]:
        L.append("| %s | %s | %s | %s |" % (rr["id"], rr["who"],
                                            rr.get("attributed") or "unattributed",
                                            rr.get("outcome", "")))
    mc = res["misses_by_class"]
    L.append("misses by class: new %d · known (in the persona, not listed) %d · declared "
             "blind spot %d" % (mc["new"], mc["known"], mc["blind spot"]))
    if any(rr.get("blind_spot") and not rr.get("matched_by") for rr in res["reals"]):
        L.append("a declared blind spot points at ## Wanted in context.md, not at a thin "
                 "section: the next authoring pass closes it")
    if any("miss (criterion" in (rr.get("outcome") or "") for rr in res["reals"]):
        L.append("where a criteria miss points: present and accepted by declaration -> the "
                 "review process, not the persona; absent from the persona -> its "
                 "## Judgment criteria")

    L += ["", "## Limits", res["limits"]]
    L += [""] + applied_lines
    return "\n".join(L)


# ----------------------------------------------------------------------------------- apply
class ApplyFailed(Exception):
    """--apply could not complete; the store is as it was before the run (exit 1)."""


def free_done_path(snap, doc, today):
    """-> the first `done-<today>-<doc>.md`, then `-2`, `-3`, … that does not exist (FR-3.1).
    A rename onto an existing name replaces it on POSIX, and that name is a frozen record."""
    base = "done-%s-%s" % (today.isoformat(), doc)
    cand, n = snap.with_name(base + ".md"), 2
    while cand.exists():
        cand, n = snap.with_name("%s-%d.md" % (base, n)), n + 1
    return cand


def apply_cycle(ctx_dir, snap, doc, ctx_name, entry, today):
    """Rename the snapshot to a free done- name, then append the log entry. -> the done path.

    That order, because the rename is the step that can be undone: if the append fails the
    snapshot goes back to `pending-` and nothing counts as graded; a log entry written first
    would have counted a cycle whose record never reached the file it names."""
    done = free_done_path(snap, doc, today)
    snap.rename(done)
    log_path = ctx_dir / "calibration/log.md"
    try:
        prev = read_text_lenient(log_path) if log_path.is_file() else None
        if prev is None or not prev:
            head = "# Calibration log — %s\n\n" % ctx_name if prev is None else ""
            append_line(log_path, head + entry.rstrip("\n"))
        else:
            # one blank line between entries, whatever the file ended with
            append_line(log_path, ("" if prev.endswith("\n\n") else "\n") + entry.rstrip("\n"))
    except Exception as e:                      # noqa: BLE001 — every failure is undone
        try:
            done.rename(snap)
            undone = "calibration/%s renamed back to %s" % (done.name, snap.name)
        except OSError as e2:
            undone = ("and the rename could not be undone (%s): calibration/%s holds the "
                      "snapshot" % (e2, done.name))
        raise ApplyFailed("log entry not appended to calibration/log.md (%s); %s"
                          % (e, undone))
    return done


# ------------------------------------------------------------------------------------ main
def main(argv=None):
    ap = ArgParser(prog="beforehand.py calibrate", description=__doc__,
                   formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--store", default=None)
    ap.add_argument("--context", required=True)
    ap.add_argument("--doc", required=True, help="document name, as in pending-<doc>.md")
    ap.add_argument("--annotation", default=None)
    ap.add_argument("--pairing", default=None)
    ap.add_argument("--ledger", nargs="?", const="", default=None, metavar="FILE",
                    help="grade a pre-0.2 prose snapshot through a reconstructed ledger "
                         "(default: <ctx>/calibration/ledger-<doc>.md); the snapshot stays "
                         "the frozen record and is hashed and renamed as usual")
    ap.add_argument("--apply", action="store_true",
                    help="append the log entry and rename the snapshot; without it, nothing "
                         "is written")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    try:
        locale_regexes()  # validates BEFOREHAND_LOCALE lazily and AFTER parse_args, so --help
        # and an argparse usage error still work under an unknown locale
    except LocaleError as e:
        print(str(e), file=sys.stderr)
        return 1

    store_root = resolve_store(args.store)
    ctx_dir = Store(store_root).context(args.context)
    try:
        if not ctx_dir.is_dir():
            raise Usage("context not found: %s" % args.context)
        snap = ctx_dir / "calibration" / ("pending-%s.md" % args.doc)
        if not snap.is_file():
            raise Usage("no pending snapshot for %s: expected calibration/%s"
                        % (args.doc, snap.name))
        ann_p = Path(args.annotation).expanduser() if args.annotation else (
            ctx_dir / "calibration" / ("annotation-%s.md" % args.doc))
        if not ann_p.is_file():
            raise Usage("annotation not found: %s (save the meeting notes first, then pass "
                        "--annotation)" % ann_p.name)
        pair_p = Path(args.pairing).expanduser() if args.pairing else (
            ctx_dir / "calibration" / ("pairing-%s.md" % args.doc))
        if not pair_p.is_file():
            raise Usage("pairing not found: %s (propose the pairs, have the user confirm them, "
                        "then pass --pairing)" % pair_p.name)
        ledger_p = None
        if args.ledger is not None:
            ledger_p = (Path(args.ledger).expanduser() if args.ledger
                        else ctx_dir / "calibration" / ("ledger-%s.md" % args.doc))
            if not ledger_p.is_file():
                raise Usage("ledger not found: %s (write it from the prose snapshot, have the "
                            "user confirm it line by line, then pass --ledger)" % ledger_p.name)
        res = grade(ctx_dir, args.context, args.doc, snap,
                    read_text_lenient(ann_p), read_text_lenient(pair_p), store_root,
                    ledger_path=ledger_p)
    except Usage as e:
        print("usage: %s" % e, file=sys.stderr)
        return 1
    except NotGradeable as e:
        print("not gradeable: %s" % e, file=sys.stderr)
        return 2

    today = _today()
    tail = []
    if args.apply:
        entry = log_entry(res, today)
        try:
            done = apply_cycle(ctx_dir, snap, args.doc, res["context"], entry, today)
        except ApplyFailed as e:
            print("error: %s" % e, file=sys.stderr)
            return 1
        res["applied"] = True
        res["done"] = done.name
        res["log_entry"] = entry
        tail = ["## Proposed Reliability updates (printed only — this script never writes a "
                "persona; see references/evidence-model.md#Writes and confirmations)"]
        for p in res["personas"]:
            d = reliability_diff(ctx_dir, p["persona"], p["running"], p["cycles"])
            if d:
                tail += [d, ""]
        tail.append("written: calibration/log.md (entry appended) · %s -> %s"
                    % (snap.name, done.name))
    else:
        tail = ["nothing written (add --apply to append the log entry, propose the Reliability "
                "one-liners and rename the snapshot)"]

    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=1, default=str))
    else:
        print(render(res, tail))
    return 0


if __name__ == "__main__":
    print("deprecated: use beforehand.py calibrate", file=sys.stderr)
    sys.exit(main())
