#!/usr/bin/env python3
"""List prediction snapshots awaiting calibration, and flag the overdue ones.

A review writes `calibration/pending-<doc>.md` with a `meeting:` date. Once that date
has passed, the meeting happened and the predictions can be graded: that is the moment
the calibrate flow should be offered. Without this check, snapshots accumulate and the
calibration loop, the whole point of the skill, never closes.

Usage:
  pending.py [--store ~/.beforehand] [--context NAME] [--json] [--overdue-only]
  pending.py --context NAME --set-meeting DOC YYYY-MM-DD [--store ~/.beforehand]

Snapshot fields read (first match wins, case-insensitive, `key: value` on its own line):
  meeting: YYYY-MM-DD        date of the meeting the document is for; `unknown` allowed
  document: / doc: <path>    the text the panel actually read; its sha1 is the one hashed
  original: <path or name>   optional; the non-text file that text was extracted from (FR-6.3)
  data review: / review date: / date: YYYY-MM-DD

`--set-meeting` is the only thing here that writes, and it writes one field (FR-1.2). The
date the whole calibration loop hangs on had no writer: the flow said "record it", nothing
recorded it, and a date that slipped was overwritten with no trace of the date it replaced.
So this writes `meeting: <new>` (always under the English key, whatever locale alias the old
line used) and appends directly under it

  meeting moved: <old | unknown | none> -> <new> on <today>

one line per move, never deleted, ignored by every other reader and exposed as
`meeting_history` in `--json`. It is not the pre-registration gate: a new date on or before
`frozen:` is a warning here and a refusal in `calibrate`, which is where the gate belongs.

`pred N` counts the `- P<k> |` rows calibrate grades. A snapshot that cannot be read is
skipped with `warning: <ctx>/calibration/<file>: unreadable (<Exception>)` on stderr; the
other snapshots are still listed.

Exit codes: 0 ok (a report; with --set-meeting: written or unchanged) ·
1 usage (--set-meeting only).
"""
import argparse
import datetime as dt
import hashlib
import json
import re
import sys

sys.dont_write_bytecode = True   # before any sibling import (G5): a run leaves no __pycache__
from pathlib import Path  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from personas_lib import (  # noqa: E402
    LocaleError,
    Store,
    atomic_write,
    frontmatter_span,
    locale_regexes,
    parse_iso_date,
    read_text_lenient,
    resolve_store,
    section_body,
)

# The snapshot field names ("meeting", "review_date", "document") are locale data
# (FR-4.4: "snapshot_fields"), fetched lazily from personas_lib.locale_regexes() inside
# scan(), where they are used — never as a module-level constant (BEFOREHAND_LOCALE may not
# be set yet at import time).

# A hook, not a bare call: tests pin the date instead of asserting on the real calendar
# (the same pattern as calibrate._today and migrate._today).
_today = dt.date.today


def field(text: str, *keys):
    for k in keys:
        m = re.search(rf"^\s*(?:[-*]\s*)?\**{re.escape(k)}\**\s*:\s*(.+?)\s*$", text, re.I | re.M)
        if m:
            return m.group(1).strip().strip("`")
    return None


def parse_date(s):
    if not s:
        return None
    m = re.search(r"\d{4}-\d{2}-\d{2}", s)
    if not m:
        return None
    try:
        return parse_iso_date(m.group(0))
    except ValueError:
        return None


# ------------------------------------------------------------------ the meeting date (FR-1.2)
# `<old>` is written verbatim, so it may be prose ("14 September") as well as a date or
# `unknown`; the capture is non-greedy rather than one token so such a line still parses.
MOVED_RE = re.compile(r"^meeting moved:\s*(.+?)\s*->\s*(\d{4}-\d{2}-\d{2})"
                      r"\s+on\s+(\d{4}-\d{2}-\d{2})\s*$", re.M)
# A head-block line that declares a field: `document:`, `frozen:`, and prose keys such as
# `Agenda item:` too — the shape is what matters, not a known vocabulary, because the file
# a pre-0.2 snapshot writes its header in is the user's prose, not this script's.
HEADER_LINE_RE = re.compile(r"^[A-Za-z][\w -]*:\s")
BODY_HEADING_RE = re.compile(r"^#{2,}\s")


def meeting_history(text):
    """-> [{"from": ..., "to": ..., "on": ...}] for every `meeting moved:` line, in file order."""
    return [{"from": m.group(1), "to": m.group(2), "on": m.group(3)}
            for m in MOVED_RE.finditer(text)]


def _meeting_line(lines, keys):
    """Index of the line `field()` reads the meeting from, or None. Same order of precedence:
    the first alias that matches anywhere wins, then its first line."""
    for k in keys:
        pat = re.compile(rf"^\s*(?:[-*]\s*)?\**{re.escape(k)}\**\s*:\s*(.+?)\s*$", re.I)
        for i, ln in enumerate(lines):
            if pat.match(ln):
                return i
    return None


def _insert_at(lines, fm_span_lines):
    """Where a `meeting:` line goes in a file that has none. -> line index.

    Inside a leading frontmatter block when there is one (before its closing `---`);
    otherwise after the last `key: value` line of the head block — the lines before the first
    `##` heading — and never after an `events:` line, whose bullets belong to it. With no
    header line at all, after an H1 title and its blank line, else at the very top.
    """
    if fm_span_lines is not None:
        return fm_span_lines[1]                       # the closing `---` line index
    end = len(lines)
    for i, ln in enumerate(lines):
        if BODY_HEADING_RE.match(ln):
            end = i
            break
    last_field = None
    for i in range(end):
        ln = lines[i]
        if re.match(r"^events\s*:", ln, re.I):
            break
        if HEADER_LINE_RE.match(ln):
            last_field = i
    if last_field is not None:
        return last_field + 1
    if lines and lines[0].startswith("# "):
        return 2 if len(lines) > 1 and not lines[1].strip() else 1
    return 0


def _frontmatter_lines(text, lines):
    """The leading frontmatter block as (first, last) line indices, or None.

    `frontmatter_span` decides whether there is one (it is the single reader of that shape);
    the closing delimiter is then located by line, because the caller inserts by line.
    """
    if frontmatter_span(text) is None:
        return None
    for i in range(1, len(lines)):
        if lines[i].rstrip() == "---":
            return (0, i)
    return None


def set_meeting(text, new_date, today):
    """Write `meeting: <new_date>` and record the move. -> (new_text, old_value).

    `old_value` is the raw previous value (a date, `unknown`, or prose) or None when the
    file had no such field. When the file already says this date, the text comes back
    unchanged and nothing should be written: a no-op move is not history.
    """
    keys = locale_regexes()["snapshot_fields"]["meeting"]
    old = field(text, *keys)
    if old is not None:
        parsed = parse_date(old)
        if parsed is not None and parsed.isoformat() == new_date:
            return text, old
    trailing = "\n" if text.endswith("\n") else ""
    lines = text[:len(text) - len(trailing)].split("\n") if text else []
    moved = "meeting moved: %s -> %s on %s" % (old if old is not None else "none",
                                               new_date, today.isoformat())
    idx = _meeting_line(lines, keys)
    if idx is None:
        at = _insert_at(lines, _frontmatter_lines(text, lines))
        lines[at:at] = ["meeting: %s" % new_date, moved]
    else:
        lines[idx] = "meeting: %s" % new_date
        after = idx + 1
        while after < len(lines) and MOVED_RE.match(lines[after]):
            after += 1                                # earlier moves stay, in the order made
        lines[after:after] = [moved]
    return "\n".join(lines) + trailing, old


ITEM_RE = re.compile(r"^\s{0,3}(?:[-*]|\d+[.)])\s+(\S.*)$")


def snapshot_format(text: str) -> str:
    """-> "0.2" | "pre-0.2" (FR-1.1).

    `pre-0.2` is the shape snapshots were frozen in before the 0.2 template existed: no
    `schema:` line and neither of the two sections the accounting reads. Such a file is a
    record, not an instrument — `calibrate` cannot grade it, and saying so is this function's
    whole job. It is not a guess about age: a 0.1 snapshot declares `schema:` and is read
    normally.
    """
    if field(text, "schema"):
        return "0.2"
    if (section_body(text, "Round-1 objections") is not None
            or section_body(text, "Predictions to verify") is not None):
        return "0.2"
    return "pre-0.2"


def prediction_ids(body: str):
    return set(re.findall(r"\bP(\d+)\b", body or ""))


def parse_events(text):
    """-> [(label, context, date string)] from the snapshot's optional `events:` block.

    One reader for `pending` and `calibrate` (S8): two copies disagreed on how many fields an
    event line needs, so one command listed an event the other never saw."""
    m = re.search(r"^events:\s*\n((?:[ \t]*-[ \t].*\n?)+)", text, re.M)
    if not m:
        return []
    evs = []
    for ln in m.group(1).splitlines():
        parts = [p.strip() for p in ln.strip().lstrip("-").split("|")]
        if len(parts) >= 2:
            evs.append((parts[0], parts[1], parts[2] if len(parts) > 2 else ""))
    return evs


SHA1_RE = re.compile(r"[0-9a-f]{40}")


def document_state(doc, sha, ctx_dir=None):
    """-> (changed, found): changed is True/False when the document can be hashed against a
    usable sha1, None when it cannot; found is the file it resolved to, or None.

    The one document-changed helper (C6, S8): `pending` read only the literal key `document`
    while `calibrate` read the locale alias `doc` too, so the same edited document was
    "changed" in one and "unknown" in the other. Callers read the fields (see
    document_changed); this resolves and hashes. A relative path is tried against the
    snapshot's own context directory first and the working directory only as a fallback,
    so the verdict does not depend on the shell it was run from whenever the store holds it.
    """
    if not doc:
        return None, None
    p = Path(doc).expanduser()
    if p.is_absolute():
        candidates = [p]
    elif ctx_dir is not None:
        candidates = [Path(ctx_dir) / p, Path.cwd() / p]
    else:
        candidates = [Path.cwd() / p]
    for cand in candidates:
        if cand.is_file():
            if not SHA1_RE.fullmatch((sha or "").strip()):
                return None, cand
            return hashlib.sha1(cand.read_bytes()).hexdigest() != sha.strip(), cand
    return None, None


def document_changed(text, ctx_dir=None):
    """True/False when the document behind a snapshot can be hashed, None when it cannot.
    Reads `document:` under every locale alias, and `sha1:`."""
    doc = field(text, *locale_regexes()["snapshot_fields"]["document"])
    return document_state(doc, field(text, "sha1"), ctx_dir)[0]


def section_has_content(body):
    """True when a section body has at least one real item or non-blank line: a bare
    '(none)' (bulleted or not) or an empty/blank body does not count as recorded content."""
    if body is None:
        return False
    for ln in body.splitlines():
        m = ITEM_RE.match(ln)
        if m:
            if m.group(1).strip() != "(none)":
                return True
            continue
        s = ln.strip()
        if s and s != "(none)":
            return True
    return False


REPORT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-(.+)$")

def report_decisions_recorded(ctx: Path, snap: Path):
    """True when a review report under <ctx>/reviews/ matches this snapshot by filename
    (the report's name minus its leading date equals the snapshot's minus 'pending-') and
    that report's own '## User decisions' section has real content. The review report, not
    the prediction snapshot, is where user decisions actually get recorded (see calibrate.md);
    this lets decisions_recorded find them there too, not just in the snapshot itself."""
    reviews_dir = ctx / "reviews"
    if not reviews_dir.is_dir() or not snap.stem.startswith("pending-"):
        return False
    key = snap.stem[len("pending-"):]
    for rep in sorted(reviews_dir.glob("*.md")):
        m = REPORT_RE.match(rep.stem)
        if m and m.group(1) == key:
            rep_text = read_text_lenient(rep)
            if section_has_content(section_body(rep_text, "User decisions")):
                return True
    return False


def prediction_count(text):
    """-> the number of `- P<k> |` rows, the rows `calibrate` grades (C9): counting every
    bullet put a reviewer's stray note in `pred N`. A duplicate id is calibrate's refusal to
    make; here the rows are still counted, so the report stays a report."""
    import calibrate  # lazy: calibrate imports this module
    try:
        return len(calibrate.parse_predictions(text))
    except calibrate.NotGradeable:
        return len(calibrate.prediction_rows(text))


def scan(store, only_context=None, unreadable=None):
    """-> one row per `calibration/pending-*.md`. A snapshot that cannot be read is skipped
    with a `warning: <file>: unreadable (<Exception>)` line on stderr, and appended to
    `unreadable` as {"file", "error"} when a list is passed: one bad file used to raise out of
    the whole scan, and `doctor` then reported the store healthy (FR-5.2)."""
    today = _today()
    fields = locale_regexes()["snapshot_fields"]
    st = Store(store)
    rows = []
    for ctx in st.contexts():
        if only_context and ctx.name != only_context:
            continue
        for snap in st.snapshots(ctx):
            key = snap.stem[len("pending-"):]
            ledger_path = ctx / "calibration" / ("ledger-%s.md" % key)
            try:
                text = read_text_lenient(snap)
                ledger_text = read_text_lenient(ledger_path) if ledger_path.is_file() else None
            except (OSError, ValueError) as e:
                where = "%s/calibration/%s" % (ctx.name, snap.name)
                print("warning: %s: unreadable (%s)" % (where, e.__class__.__name__),
                      file=sys.stderr)
                if unreadable is not None:
                    unreadable.append({"file": where, "error": e.__class__.__name__})
                continue
            fmt = snapshot_format(text)
            # A pre-0.2 snapshot keeps being the frozen record; what it cannot state in a
            # shape this reads, the reconstructed ledger states beside it (FR-1.1). The
            # snapshot still wins wherever it does say something.
            fallback = ledger_text if (fmt == "pre-0.2" and ledger_text is not None) else ""
            meeting = parse_date(field(text, *fields["meeting"]))
            reviewed = parse_date(field(text, *fields["review_date"]))
            if fallback:
                # A date the snapshot states in prose (or as `unknown`) does not parse, which
                # is the whole reason the ledger exists; the snapshot still wins whenever its
                # own value is readable.
                meeting = meeting or parse_date(field(fallback, *fields["meeting"]))
                reviewed = reviewed or parse_date(field(fallback, *fields["review_date"]))
            doc = field(text, *fields["document"]) or field(fallback, *fields["document"]) or key
            # FR-6.3: a document extracted from slides or a word-processor file is reviewed and
            # hashed as its extracted text (`document:`); `original:` names the file it came
            # from, so the anchors stay traceable to what the user actually sends. Optional and
            # not locale data: it is a path, never a parsed value.
            original = field(text, "original")
            if meeting is None:
                status = "no meeting date"
            elif meeting < today:
                status = f"OVERDUE by {(today - meeting).days} days: offer calibration"
            elif meeting == today:
                status = "meeting today"
            else:
                status = f"upcoming in {(meeting - today).days} days"
            schema = field(text, "schema")
            own_preds = section_body(text, "Predictions to verify")
            preds_body = own_preds if own_preds is not None else (
                section_body(fallback, "Predictions to verify") if fallback else None)
            if preds_body is None:
                predictions = 0 if schema else None
            else:
                predictions = prediction_count("## Predictions to verify\n" + preds_body)
            pred_ids = prediction_ids(own_preds)
            text_wo_preds = text.replace(own_preds, "", 1) if own_preds is not None else text
            text_wo_preds = re.sub(r"^#{2,3}\s+Predictions to verify\s*$", "", text_wo_preds,
                                    flags=re.I | re.M)
            warnings = []
            if fmt == "pre-0.2":
                # A file with no ledger to resolve `P<k>` against has no dangling references,
                # only an unreadable shape: three "dangling reference P1" lines named a
                # symptom of the format and hid the format itself.
                rec = parse_date(field(ledger_text or "", "reconstructed"))
                if ledger_text is None:
                    warnings.append("pre-0.2 format, not gradeable")
                elif rec is None:
                    warnings.append("pre-0.2 format, ledger reconstructed (no date stated)")
                else:
                    warnings.append("pre-0.2 format, ledger reconstructed %s" % rec.isoformat())
            else:
                for k in sorted(set(re.findall(r"\bP(\d+)\b", text_wo_preds)) - pred_ids, key=int):
                    warnings.append(f"dangling reference P{k}")
            events = []
            for label, cx, raw in parse_events(text):
                d = parse_date(raw)
                events.append({"label": label, "context": cx,
                               "date": d.isoformat() if d else None,
                               "overdue": bool(d and d < today)})
            decisions_recorded = (section_has_content(section_body(text, "User decisions"))
                                   or report_decisions_recorded(ctx, snap))
            changed = document_changed(text, ctx)
            rows.append({"context": ctx.name, "snapshot": str(snap), "document": doc,
                         "original": original,
                         "review_date": reviewed.isoformat() if reviewed else None,
                         "meeting": meeting.isoformat() if meeting else None, "status": status,
                         "overdue": bool(meeting and meeting < today),
                         "predictions": predictions, "warnings": warnings, "events": events,
                         "format": fmt,
                         "ledger": ledger_path.name if ledger_text is not None else None,
                         "meeting_history": meeting_history(text),
                         "document_changed": changed, "decisions_recorded": decisions_recorded})
    return rows


def run_set_meeting(store, context, doc, new_date):
    """`--set-meeting`: the one write this module does. -> exit code (0 ok, 1 usage).

    Usage errors leave the store untouched; warnings never do. The pre-registration rule
    (frozen before the meeting) is `calibrate`'s to enforce, so a date that breaks it is
    written and flagged here, not refused: the snapshot has to be able to say what happened.
    """
    if not context:
        print("usage: --set-meeting needs --context", file=sys.stderr)
        return 1
    try:
        new_day = parse_iso_date(new_date)
    except ValueError:
        print("usage: meeting date must be YYYY-MM-DD, got %r" % (new_date,), file=sys.stderr)
        return 1
    snap = Path(store) / context / "calibration" / ("pending-%s.md" % doc)
    if not snap.is_file():
        print("usage: no pending snapshot for %s: expected calibration/%s" % (doc, snap.name),
              file=sys.stderr)
        return 1
    text = read_text_lenient(snap)
    new_text, old = set_meeting(text, new_date, _today())
    if new_text == text:
        print("unchanged: calibration/%s already says meeting %s" % (snap.name, new_date))
        return 0
    atomic_write(snap, new_text)
    print("written: calibration/%s meeting %s -> %s"
          % (snap.name, old if old is not None else "none", new_date))
    frozen = parse_date(field(new_text, "frozen"))
    if frozen is not None and new_day <= frozen:
        print("warning: meeting %s is on or before frozen %s: calibrate will refuse this "
              "snapshot (frozen on or after the meeting)" % (new_date, frozen.isoformat()),
              file=sys.stderr)
    if re.search(r"^events:\s*$", new_text, re.M):
        print("note: events: block left as written; move the event line by hand if it names "
              "the old date", file=sys.stderr)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--store", default=None)
    ap.add_argument("--context")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--overdue-only", action="store_true")
    ap.add_argument("--set-meeting", nargs=2, metavar=("DOC", "DATE"), default=None,
                    help="write the meeting date of calibration/pending-DOC.md and keep the "
                         "date it replaces on a `meeting moved:` line (needs --context)")
    args = ap.parse_args(argv)
    try:
        locale_regexes()  # validates BEFOREHAND_LOCALE lazily and AFTER parse_args, so --help
        # and an argparse usage error still work under an unknown locale
    except LocaleError as e:
        print(str(e), file=sys.stderr)
        return 1
    store = resolve_store(args.store)
    if args.set_meeting:
        return run_set_meeting(store, args.context, args.set_meeting[0], args.set_meeting[1])
    if not store.is_dir():
        print(f"store not found: {store}", file=sys.stderr)
        return 0
    rows = scan(store, args.context)
    if args.overdue_only:
        rows = [r for r in rows if r["overdue"] or r["meeting"] is None]
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=1))
        return 0
    if not rows:
        print("No pending snapshots." if not args.overdue_only else "Nothing overdue.")
        return 0
    show_pred_col = any(r.get("predictions") is not None for r in rows)
    for r in rows:
        line = (f"{r['context']:18s} {r['document'][:48]:48s} reviewed {r['review_date'] or '?'}  "
                f"meeting {r['meeting'] or 'unknown':10s}  {r['status']}")
        if show_pred_col:
            preds = r.get("predictions")
            line += f"  pred {preds}" if preds is not None else "  pred -"
        if r.get("original"):
            line += f"  original {Path(r['original']).name}"
        if r.get("document_changed") is True:
            line += "  doc changed!"
        if r.get("format") == "pre-0.2":
            line += "  pre-0.2 (ledger)" if r.get("ledger") else "  pre-0.2"
        hist = r.get("meeting_history") or []
        if hist:
            line += "  moved from %s" % hist[-1]["from"]
        print(line)
        for e in r.get("events", []):
            print(f"    event {e['label']} ({e['context']}) {e['date'] or 'unknown'} "
                  f"{'OVERDUE' if e['overdue'] else ''}")
    n_over = sum(1 for r in rows if r["overdue"])
    n_nodate = sum(1 for r in rows if r["meeting"] is None)
    print(f"\n{len(rows)} pending | {n_over} overdue | {n_nodate} without a meeting date"
          + (" (ask when the meeting is, then: beforehand.py pending --context <ctx> "
             "--set-meeting <doc> YYYY-MM-DD)" if n_nodate else ""))
    return 0


if __name__ == "__main__":
    print("deprecated: use beforehand.py pending", file=sys.stderr)
    sys.exit(main())
