#!/usr/bin/env python3
"""Remove one person from a store — the dossier and every row that still names them.

Why this exists (FR-7.4). The store holds judgments about identifiable people, so "delete
what you hold about me" is a request the skill has to be able to honour exactly, not
approximately. Deleting the persona file by hand is the approximate version: the slug stays
in the index, in the AUDIT rows of the sources it was built from, in the objection rows of
every prediction snapshot, in the calibration log and in the usage log. What is left is worse
than either keeping or deleting — an unreadable half-record of someone who asked to be
removed.

What is removed, per file:
  `personas/<slug>.md`     the dossier itself.
  `AUDIT.md`               every ingestion row that names the slug. A row naming several
                           personas goes with it: the row is one statement about one
                           ingestion, and rewriting it would leave a record of who was
                           extracted from that source that no longer matches the store.
                           An earlier `<date> | forget <slug> | …` line is kept.
  snapshots                objection rows whose `Persona` cell is the slug, `P<k>` prediction
                           lines naming it, bullets addressed to it, and its entry in the
                           `personas:` header (the whole header line when it is the only
                           entry: a header naming nobody else is a row about this person).
  pairing / annotation     (`calibration/pairing-*.md`, `annotation-*.md`) the lines keyed by
                           the slug — `<slug>#<n> | R<j> | …`, `overruled: <slug>#<n>`,
                           `- greenlight: <slug> | …`, `criterion: R<j> | <slug>#c<n>` — and
                           the `P<k> | …` / `overruled: P<k>` lines of the prediction ids the
                           slug owned in the ONE snapshot that pairing grades — pending-<doc>,
                           else the newest done-*-<doc> (a `-<n>` suffix is a second grading
                           only when done-<same date>-<doc>.md exists), replaced by
                           ledger-<doc> when that snapshot is prose or pinned by it — read
                           with `calibrate.parse_predictions` before any P-row is removed.
                           Ids are never pooled across cycles: a new cycle renumbers from P1.
                           Left behind, any of these lines names a key that no longer exists
                           and calibrate refuses the whole cycle, so forgetting one person
                           would stop the others being graded. A snapshot whose ids cannot
                           be read is reported, and its P<k> lines are left: ownership is
                           never guessed.
  pinned snapshots         pending-<doc> when a ledger-<doc> carries `snapshot sha1:`, and any
                           pending or done file whose sha1 a ledger pins, is never edited (the
                           ledger would stop grading); every line naming the slug is reported
                           LEFT with `pinned by ledger-<doc>.md (snapshot sha1)`.
  `reviews/`               `- <date> | <slug> | …` decision bullets addressed to the slug.
  `calibration/log.md`     scoring rows whose `Persona` cell is the slug.
  `usage.jsonl`            rows whose `doc` names the slug.
  anything else in the     the slug is dropped from the enumeration it appears in (a review
  context                  report's "personas a, b, c"), keeping the sentence and the other
                           names. A mention that is not a list entry, or that sits inside a
                           quoted span ("…"), is NEVER rewritten: it is reported, with its file
                           and line, for a human to handle. A slug glued to another word
                           (`devops-sam` when forgetting `ops-sam`) is another slug: it is
                           left alone and not reported. The dry run prints every entry
                           edit as `old -> new`; a line that keeps a mention of the slug after
                           its entry was dropped is also reported LEFT.

Other persona files are not touched either, for the same reason: a line in someone else's
dossier is their evidence, and editing it silently would be a second, unrequested change to
a second person's record.

Write order: the keyed pairing/annotation files first, then every other file of the
context, then the calibration files that hold P-rows (pending, done, ledger), then the
store's usage.jsonl (after the P-row files; it holds no keys, so its place does not affect
crash safety), then the AUDIT, and the persona file last. Each write replaces its file
whole (`atomic_write`). A run that stops after any write therefore leaves the dossier on
disk and every P-row still attributable, and running the command again finishes the
removal. The AUDIT line of that re-run counts only what the re-run itself removed: the
interrupted run wrote no AUDIT line, so its share is not counted anywhere (the rows are
gone either way; the count is not cumulative). The AUDIT write drops its rows naming the
slug and appends one line (the file is created with migrate's 0.2 header when the context
has none); then the index is regenerated. The line:
`<date> | forget <slug> | <N> rows removed`, with `, <M> entries edited` after it when a
line kept its sentence and lost one name. The store must not be able to answer "was
anything ever removed here?" with silence, so the removal itself is recorded — the slug in
that line is the only trace the command leaves on purpose.

Nothing is written without `--apply`.

Usage:
  forget.py SLUG [--store ~/.beforehand] [--context NAME] [--apply]

Exit codes: 0 ok · 1 usage (including a --context that is not a directory) · 2 slug not found
"""
import sys

sys.dont_write_bytecode = True  # before any sibling import (G5)

import argparse  # noqa: E402
import datetime as dt  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import re  # noqa: E402
from pathlib import Path  # noqa: E402

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import calibrate  # noqa: E402
import migrate  # noqa: E402
import reindex  # noqa: E402
from personas_lib import (  # noqa: E402
    Store,
    atomic_write,
    read_text_lenient,
    rel,
    resolve_store,
)

# A hook, not a bare call: tests pin the date without asserting on today.
_today = dt.date.today

SKIP_DIRS = ("sources", "personas")
SKIP_NAMES = ("INDEX.md",)


def entries_clause(n_entries):
    """The `, <M> entries edited` half of the audit line, written only when there is one.

    The pinned form `<date> | forget <slug> | <N> rows removed` stays the head of the line
    and N stays a count of rows; a line that lost one name out of an enumeration was edited,
    not removed, and folding the two together would make the audit overstate the cut.
    """
    return ", %d entries edited" % n_entries if n_entries else ""


def slug_re(slug):
    """The slug as a whole word: `coo-mira` must not match `coo-mirabel`."""
    return re.compile(r"(?<![\w-])" + re.escape(slug) + r"(?![\w-])")


def first_cell(line):
    """The first cell of a markdown table row, or None."""
    if not line.lstrip().startswith("|"):
        return None
    return line.strip().strip("|").split("|")[0].strip()


# What a list of slugs looks like on either side of the one being removed. A comma is not
# enough to make a list: `(P1 for coo-mira, P2 for cto-jonas)` is a sentence, and cutting
# `coo-mira, ` out of it leaves `(P1 for P2 for cto-jonas)` — a corrupted record, which is
# the one outcome this command must never produce. So the neighbour the comma is shared with
# has to be an entry too: a slug-shaped token, optionally with the `(updated <date>)` the
# snapshot header writes, and nothing else before the next delimiter.
_TAIL = r"(?:\s*\([^)]*\))?"
_SLUG_SHAPE = r"[a-z0-9]+(?:-[a-z0-9]+)+"
_NEXT_ENTRY_RE = re.compile(r"^\s*" + _SLUG_SHAPE + _TAIL + r"\s*(?:$|[,.;:)|])")
_PREV_ENTRY_RE = re.compile(r"(?:^|[\s|:(])" + _SLUG_SHAPE + _TAIL + r"\s*$")


def drop_from_enumeration(line, slug):
    """-> the line without the slug's entry in a comma-separated list, or None if the slug is
    not written as a list entry there.

    `personas: a (updated X), b (updated Y), coo-mira (updated Z)` and
    `..., personas a, b, coo-mira.` both lose one entry and keep their punctuation; a
    sentence that uses the slug as a word does not match, and is reported instead.
    """
    s = re.escape(slug)
    m = re.search(r",\s*" + s + _TAIL + r"(?=\s*(?:$|[,.;:)|]))", line)
    if m and _PREV_ENTRY_RE.search(line[:m.start()]):
        return line[:m.start()] + line[m.end():]
    m = re.search(r"(?<![\w-])" + s + _TAIL + r"\s*,\s*", line)
    if m and _NEXT_ENTRY_RE.match(line[m.end():]):
        return line[:m.start()] + line[m.end():]
    return None


# A header whose only entry is the slug: removing the entry leaves a line about nobody, so
# the line is the row (FR-5.1). Only the two headers the store writes this way qualify —
# `personas:` of a snapshot and the annotation's absent list — never an arbitrary `Label:`.
_SOLE_ENTRY_LABELS = r"(?:personas|personas rostered but absent)"


def keyed_row_re(slug):
    """The pairing/annotation lines keyed by the slug: `<slug>#<n> | …`, `overruled:
    <slug>#<n>`, `- greenlight: <slug> | …`, `criterion: R<j> | <slug>#c<n>`."""
    s = re.escape(slug)
    return re.compile(r"^\s*(?:[-*]\s*)?(?:(?:overruled:\s*)?" + s + r"#c?\d+\s*(?:\||$)"
                      r"|greenlight:\s*" + s + r"\s*(?:\||$)"
                      r"|criterion:\s*R\d+\s*\|\s*" + s + r"#c\d+\b)", re.I)


_P_KEY_RE = re.compile(r"^\s*(?:[-*]\s*)?(?:overruled:\s*)?(P\d+)\s*(?:\||$)")


_QUOTED_RE = re.compile(r'"[^"\n]*"|\u201c[^\u201d\n]*\u201d')


def in_quotes(line, slug):
    """True when an occurrence of the slug sits inside a quoted span: a quote is evidence,
    someone's words, and is never edited (it is reported instead)."""
    spans = [m.span() for m in _QUOTED_RE.finditer(line)]
    return any(a <= m.start() < b for m in slug_re(slug).finditer(line) for a, b in spans)


def clean_text(text, slug, rows, owned=None, ambiguous=None, keyed=False):
    """-> new text. Removes the rows a snapshot, a log or a report keeps about the slug, and
    appends one (kind, line[, new line]) per removal to `rows`.

    keyed: the file is a pairing or an annotation, whose lines are keyed rather than named
    (see the module docstring). owned / ambiguous: the P<k> ids the slug owned in the
    snapshot this file grades, and the ids whose owner cannot be told (left, reported)."""
    pat = slug_re(slug)
    keyed_re = keyed_row_re(slug) if keyed else None
    sole_re = re.compile(r"^\s*" + _SOLE_ENTRY_LABELS + r"\s*:\s*" + re.escape(slug) + _TAIL
                         + r"\s*$", re.I)
    out = []
    for line in text.split("\n"):
        if keyed:
            if keyed_re.match(line):
                rows.append(("row", line))
                continue
            mp = _P_KEY_RE.match(line)
            if mp and mp.group(1) in (ambiguous or ()):
                rows.append(("mention", line))
                out.append(line)
                continue
            if mp and mp.group(1) in (owned or ()):
                rows.append(("row", line))
                continue
        if not pat.search(line):
            out.append(line)
            continue
        cell = first_cell(line)
        stripped = line.strip()
        if cell is not None and pat.fullmatch(cell or ""):
            rows.append(("row", line))
            continue
        if re.match(r"^-\s*((?:P\d+|\d{4}-\d{2}-\d{2})\s*\|\s*)?" + re.escape(slug)
                    + r"\s*(\||:)", stripped):
            rows.append(("row", line))
            continue
        if sole_re.match(line):
            rows.append(("row", line))
            continue
        replaced = None if in_quotes(line, slug) else drop_from_enumeration(line, slug)
        if replaced is not None:
            rows.append(("entry", line, replaced))
            if pat.search(replaced):
                # the entry went, a plain mention of the slug stays: say so (R2.5)
                rows.append(("mention", replaced, "the slug still appears after the entry "
                                                  "was dropped"))
            out.append(replaced)
            continue
        rows.append(("mention", line))          # left as written, reported to the user
        out.append(line)
    return "\n".join(out)


def clean_audit(text, slug, rows):
    """AUDIT rows are dropped whole (see the module docstring). An earlier
    `<date> | forget <slug> | …` line is kept: it is the one trace left on purpose."""
    pat = slug_re(slug)
    forget_line = re.compile(r"^\d{4}-\d{2}-\d{2} \| forget " + re.escape(slug) + r" \|")
    out = []
    for line in text.split("\n"):
        if line.strip() and pat.search(line) and not forget_line.match(line.strip()):
            rows.append(("row", line))
            continue
        out.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out))


def clean_usage(text, slug, rows):
    """usage.jsonl: rows whose `doc` names the slug. A line that is not JSON is kept: the log
    is append-only and hand-editable, and one bad line is not a reason to drop it."""
    pat = slug_re(slug)
    out = []
    for line in text.splitlines():
        if line.strip():
            try:
                row = json.loads(line)
            except ValueError:
                row = None
            if isinstance(row, dict) and pat.search(str(row.get("doc") or "")):
                rows.append(("row", line))
                continue
        out.append(line)
    return "\n".join(out) + ("\n" if out and out[-1].strip() else "")


def contexts_with(store, slug):
    """Every context whose roster holds the slug: its persona file, or its INDEX line."""
    st = Store(store)
    found = []
    for ctx in st.contexts():
        if (ctx / "personas" / (slug + ".md")).is_file():
            found.append(ctx)
            continue
        idx = ctx / "INDEX.md"
        if idx.is_file() and re.search(r"(?m)^- " + re.escape(slug) + r"\s*\|",
                                       read_text_lenient(idx)):
            found.append(ctx)
    return found


_CAL_DOC_RE = re.compile(r"^(?:pending|ledger|pairing|annotation)-(.+)\.md$")
_DONE_RE = re.compile(r"^done-\d{4}-\d{2}-\d{2}-(.+)\.md$")


def known_docs(cal):
    """The document keys a calibration directory names: pending-, ledger-, pairing- and
    annotation- files. A done file is matched against these, never parsed on its own."""
    return {m.group(1) for m in (_CAL_DOC_RE.match(p.name) for p in cal.glob("*.md")) if m}


def doc_key(name, known, present=()):
    """-> the document key a calibration file belongs to, or None. A done file
    `done-<date>-<rest>.md` belongs to <rest> when <rest> is a document the directory names;
    otherwise `<doc>-<n>` is read as a second grading of <doc> (FR-3.1) ONLY when
    `done-<same date>-<doc>.md` is in `present` (the directory's file names). Anything else
    is part of the document name: `done-<date>-plan-2026.md` is never filed under `plan`."""
    m = _CAL_DOC_RE.match(name)
    if m:
        return m.group(1)
    m = _DONE_RE.match(name)
    if not m:
        return None
    rest = m.group(1)
    if rest in known:
        return rest
    base = re.match(r"^(.+)-\d+$", rest)
    date = name[len("done-"):len("done-") + 10]
    if base and "done-%s-%s.md" % (date, base.group(1)) in present:
        return base.group(1)
    return rest


def _done_order(path, doc):
    """Newest first: the date in the name, then the second-grading suffix — the part left
    after the resolved <doc> key, never a number read off the name alone."""
    date = path.name[len("done-"):len("done-") + 10]
    rest = path.name[len("done-") + 11:-len(".md")]
    tail = rest[len(doc):] if rest.startswith(doc) else ""
    m = re.fullmatch(r"-(\d+)", tail)
    return (date, int(m.group(1)) if m else 1)


def ledger_pins(cal):
    """-> {snapshot file name: ledger file name}. A ledger-<doc> carrying `snapshot sha1:`
    pins pending-<doc>.md, and any pending or done file whose sha1 is that value (a cycle
    already graded and renamed). Editing a pinned file would make the ledger refuse to
    grade, so forget treats it as read-only and takes ownership from the ledger."""
    pins = {}
    snaps = sorted(list(cal.glob("pending-*.md")) + list(cal.glob("done-*.md")))
    digests = {}
    for led in sorted(cal.glob("ledger-*.md")):
        m = re.search(r"(?m)^snapshot sha1:\s*([0-9a-f]{40})", read_text_lenient(led))
        if not m:
            continue
        pins["pending-%s.md" % led.name[len("ledger-"):-len(".md")]] = led.name
        for snap in snaps:
            if snap not in digests:
                digests[snap] = hashlib.sha1(snap.read_bytes()).hexdigest()
            if digests[snap] == m.group(1):
                pins[snap.name] = led.name
    return pins


def grading_snapshot(cal, doc, known, present=(), pins=None):
    """-> the file whose P<k> ids a pairing-<doc> / annotation-<doc> refers to: pending-<doc>,
    else the newest done-*-<doc>; replaced by ledger-<doc> when that snapshot is pre-0.2
    prose or pinned by the ledger's sha1. One file, one cycle: a new cycle renumbers from
    P1, so ids are never pooled across files."""
    pending = cal / ("pending-%s.md" % doc)
    ledger = cal / ("ledger-%s.md" % doc)
    if pending.is_file():
        snap = pending
    else:
        done = [p for p in cal.glob("done-*.md") if doc_key(p.name, known, present) == doc]
        snap = max(done, key=lambda p: _done_order(p, doc)) if done else None
    if snap is None:
        return None
    if ledger.is_file() and ((pins or {}).get(snap.name) == ledger.name or
                             calibrate.snapshot_format(read_text_lenient(snap)) == "pre-0.2"):
        return ledger
    return snap


def prediction_owners(cal, doc, known, slug, mentions, present=(), pins=None):
    """-> (owned, ambiguous) P<k> ids of the snapshot that pairing-<doc> grades. Read BEFORE
    any P-row is removed. A snapshot whose ids cannot be parsed (calibrate refuses it, e.g. a
    duplicate id) is reported LEFT and every id becomes ambiguous: cutting a pairing line on
    a guess would corrupt the record of another person."""
    snap = grading_snapshot(cal, doc, known, present, pins)
    if snap is None:
        return set(), set()
    text = read_text_lenient(snap)
    try:
        preds = calibrate.parse_predictions(text)
    except calibrate.NotGradeable as e:
        mentions.append((snap, "", "prediction ids not readable (%s): its P<k> lines in "
                                   "the pairing are left" % e))
        return set(), set(re.findall(r"(?m)^\s*[-*]\s+(P\d+)\s*\|", text))
    return {r["id"] for r in preds if r["persona"] == slug}, set()


def write_rank(path, ctx):
    """Write order (FR-5.1, crash-safe): keyed pairing/annotation files first, every other
    file next, the calibration files that hold P-rows (pending, done, ledger) last. A run
    that stops after any write leaves those P-rows in place, so a re-run still reads who
    owned which P<k>; the AUDIT line and the persona file follow them."""
    if path.parent == ctx / "calibration":
        if path.name.startswith(("pairing-", "annotation-")):
            return 0
        if path.name.startswith(("pending-", "done-", "ledger-")):
            return 2
    return 1


def scan(ctx, store, slug):
    """-> (edits, removals, mentions).

    edits: [(path, old, new)] text files to rewrite, in write order (the AUDIT last);
    removals: [(path, kind, line, new line or None)] for the report; mentions:
    [(path, line, reason or None)] the command refuses to rewrite, or a slug that survives.
    """
    edits, removals, mentions = [], [], []
    persona = ctx / "personas" / (slug + ".md")
    cal = ctx / "calibration"
    known = known_docs(cal) if cal.is_dir() else set()
    present = {p.name for p in cal.glob("*.md")} if cal.is_dir() else set()
    pins = ledger_pins(cal) if cal.is_dir() else {}
    owners = {}

    def record(path, old, new, rows):
        for row in rows:
            kind, line = row[0], row[1]
            if kind == "mention":
                mentions.append((path, line, row[2] if len(row) > 2 else None))
            else:
                removals.append((path, kind, line, row[2] if len(row) > 2 else None))
        if new != old:
            edits.append((path, old, new))

    for path in sorted(ctx.rglob("*"), key=lambda p: (write_rank(p, ctx), str(p))):
        if not path.is_file() or path.name == "AUDIT.md" and path.parent == ctx \
                or path == persona:
            continue
        if path.name in SKIP_NAMES or path.relative_to(ctx).parts[0] in SKIP_DIRS:
            continue
        if path.suffix.lower() not in (".md", ".txt", ".jsonl"):
            continue
        rows = []
        old = read_text_lenient(path)
        if path.parent == cal and path.name in pins:
            # pinned by a ledger's `snapshot sha1:` (ruling R1.4): read-only, every line that
            # names the slug is reported with the pin as its reason
            reason = "pinned by %s (snapshot sha1)" % pins[path.name]
            for line in old.split("\n"):
                if slug_re(slug).search(line):
                    mentions.append((path, line, reason))
            continue
        if path.suffix == ".jsonl":
            new = clean_usage(old, slug, rows)
        else:
            keyed = path.parent == cal and path.name.startswith(("pairing-", "annotation-"))
            mine, amb = set(), set()
            if keyed:
                doc = doc_key(path.name, known, present)
                if doc not in owners:
                    owners[doc] = prediction_owners(cal, doc, known, slug, mentions,
                                                    present, pins)
                mine, amb = owners[doc]
            new = clean_text(old, slug, rows, owned=mine, ambiguous=amb, keyed=keyed)
        record(path, old, new, rows)

    usage = Path(store) / "usage.jsonl"
    if usage.is_file():
        rows = []
        old = read_text_lenient(usage)
        record(usage, old, clean_usage(old, slug, rows), rows)

    audit = ctx / "AUDIT.md"
    if audit.is_file():
        rows = []
        old = read_text_lenient(audit)
        record(audit, old, clean_audit(old, slug, rows), rows)
    return edits, removals, mentions


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("slug", help="the persona slug to remove, e.g. coo-mira")
    ap.add_argument("--store", default=None)
    ap.add_argument("--context", help="the context to remove it from (default: the only one "
                                      "that holds it)")
    ap.add_argument("--apply", action="store_true",
                    help="write the removals (default: print what they would be)")
    args = ap.parse_args(argv)

    store = resolve_store(args.store)
    if not store.is_dir():
        print("usage: store not found: %s" % store, file=sys.stderr)
        return 1
    st = Store(store)
    holders = contexts_with(store, args.slug)
    if args.context:
        ctx = st.context(args.context)
        if not ctx.is_dir():
            # A typo in --context is not "the slug is not in the roster": the roster it names
            # does not exist. Reported as usage, so exit 2 keeps meaning the one thing it
            # documents — a slug this store never held.
            print("usage: context not found: %s" % rel(ctx, store), file=sys.stderr)
            return 1
        if ctx not in holders:
            print("%s is not in the roster of %s. Nothing was removed: `doctor` or the "
                  "context INDEX lists the slugs this store holds."
                  % (args.slug, rel(ctx, store)), file=sys.stderr)
            return 2
    elif not holders:
        print("%s is in no context of %s. Nothing was removed: a slug this store never held "
              "cannot be forgotten, and a typo must not read as success."
              % (args.slug, store), file=sys.stderr)
        return 2
    elif len(holders) > 1:
        print("usage: %s is in %d contexts (%s). Name one with --context: forgetting someone "
              "in one audience is not forgetting them in another, and this command will not "
              "choose for you."
              % (args.slug, len(holders), ", ".join(c.name for c in holders)), file=sys.stderr)
        return 1
    else:
        ctx = holders[0]

    persona = ctx / "personas" / (args.slug + ".md")
    edits, removals, mentions = scan(ctx, store, args.slug)
    # Two different things happen to two different shapes, so they are counted separately:
    # a row is deleted whole, an entry is one name dropped from a line that stays. `N rows
    # removed` has to mean rows, or the number in the audit line overstates what was cut.
    n_rows = sum(1 for _p, kind, _l, _n in removals if kind == "row")
    n_entries = len(removals) - n_rows

    if not persona.is_file():
        print("no persona file at %s (the slug is in the roster, not on disk)"
              % rel(persona, store))
    elif not args.apply:
        print("would remove  %s" % rel(persona, store))
    for path, kind, line, new_line in removals:
        if kind == "row":
            print("  row   %s: %s" % (rel(path, store), line.strip()[:110]))
        else:
            # the whole edit, old -> new: a mangled rewrite must be visible before --apply
            print("  entry %s: %s -> %s" % (rel(path, store), line.strip(), new_line.strip()))
    for path, line, reason in mentions:
        # the quoted line is cut to fit, the reason never is
        print("  LEFT  %s: %s%s" % (rel(path, store), line.strip()[:110],
                                    ("  [%s]" % reason if line.strip() else reason)
                                    if reason else ""))
    if mentions:
        print("\n%d mention(s) above are prose, not rows: they are left exactly as written.\n"
              "Read them and decide — a sentence is not a record this command can cut safely."
              % len(mentions))

    if not args.apply:
        print("\n%d row(s) would be removed%s, across %d file(s); then the index would be "
              "regenerated (reindex) and the removal recorded in AUDIT.md."
              % (n_rows, entries_clause(n_entries), len(edits)))
        print("nothing written. Re-run with --apply after the user confirms.")
        return 0

    # Write order (see write_rank and the module docstring): keyed pairing/annotation files,
    # every other file, the P-row sources, then the AUDIT (its cut rows and the forget line
    # in one write), the persona file last. A run that stops after any write leaves the
    # dossier on disk and the P-rows readable, so re-running forget finishes the job.
    audit = st.audit(ctx)
    audit_new = None
    for path, _old, new in edits:
        if path == audit:
            audit_new = new
            continue
        atomic_write(path, new)
    line = "%s | forget %s | %d rows removed%s" % (_today().isoformat(), args.slug, n_rows,
                                                   entries_clause(n_entries))
    if audit.is_file():
        base = audit_new if audit_new is not None else read_text_lenient(audit)
        atomic_write(audit, base.rstrip("\n") + "\n\n" + line + "\n")
    else:
        # migrate's 0.2 header, from its one constant: a bare `# AUDIT` made the next
        # `migrate` show a diff on an otherwise-0.2 store (E3).
        atomic_write(audit, migrate.AUDIT_TEMPLATE + "\n" + line + "\n")
    print("\nappended   %s: %s" % (rel(audit, store), line))
    if persona.is_file():
        persona.unlink()
        print("removed       %s" % rel(persona, store))
    rc = reindex.main(["--store", str(store), "--context", ctx.name])
    if rc:
        print("reindex exited %d after the removal: the rows are gone, the index was not "
              "fully rebuilt." % rc, file=sys.stderr)
    return 0


if __name__ == "__main__":
    print("deprecated: use beforehand.py forget", file=sys.stderr)
    sys.exit(main())
