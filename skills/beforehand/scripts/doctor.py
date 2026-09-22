#!/usr/bin/env python3
"""doctor: one read-only diagnosis of a personas store (SPEC-0.2 FR-4.2, FR-5.5).

Why this module exists. Opening a flow used to mean four commands and a mnemonic: `pending`
for the snapshots, the warnings `reindex` prints on the side, the lint and coverage columns
of the index, and the per-section staleness rule spelled out in `review.md`. Steps that can
be skipped are skipped, and the ones skipped first are the ones that report bad news. This
command answers the only question a flow actually asks at its start — *is anything in this
store not fit to be used right now* — in one table per context and one pinned last line.

What it looks at, and what each finding is called (the kinds are pinned, so a caller can
branch on them instead of on prose):

  gap        no `context.md` in a context; a persona with no `cares_about` (the field roster
             selection reads); frontmatter outside the FR-4.8 subset, with the line number —
             `reindex` prints that one as a passing warning on stderr, where it is lost; a
             persona whose lint status is `fail`, because an excerpt that is not in the
             source it cites is what the panel gate refuses outright, or whose lint could
             not run at all (the exception text is the item's reason: a check that crashed
             is not a check that passed).
  schema     a persona or a `context.md` whose `schema:` is missing or behind SCHEMA_VERSION.
  staleness  a judgment section whose `last evidence:` note is older than its decay budget
             (fast-decay `Mandate and incentives` and `Panel dynamics` at 180 days, slow-decay
             `Judgment criteria`, `Recurring objections` and `Red lines` at 365; `Language and
             dissent style` does not decay), or a judgment heading carrying no note at all.
  snapshot   a pending snapshot with no meeting date, one whose meeting has passed, or one
             whose document changed since it was frozen.
  offer      an offer logged as `offered` in `usage.jsonl` that no later row answered with
             `accepted` or `declined` (FR-5.5) — the state the "offer once" rule needs and
             that a compacted session cannot remember.

Everything else on the table is information, not a finding: `lint: warn` and a thin coverage
say how founded a persona is, not whether it may be used, and are reported in full by their
own commands; Watchlist entries that already cite two sources are listed as `READY` because
promotion is the user's judgment, never the script's.

A check that could not run is an item with its reason, never a silence: a crashed lint,
coverage or snapshot scan, and a snapshot the scan skipped as unreadable. An unknown
`BEFOREHAND_LOCALE` is checked once, up front, and reported as ONE item (`locale: <message>`);
the checks that read the locale (lint, coverage, snapshots) are then skipped instead of each
failing once per persona.

Staleness is measured against `--today` (default: the real date) so that a suite can pin a
date instead of depending on the day it runs. Exit is 0 whatever the store contains: this is
a report. It reads store files only — never `SKILL.md` or anything outside the store — and it
never writes, not even an index.

Usage:
  doctor.py [--store PATH] [--context CTX] [--today YYYY-MM-DD] [--json]
"""
import sys

sys.dont_write_bytecode = True  # before any sibling import (G5)

import argparse  # noqa: E402
import datetime as dt  # noqa: E402
import json  # noqa: E402
import re  # noqa: E402
from pathlib import Path  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import coverage as _cov  # noqa: E402
import log_flow as _log  # noqa: E402
import pending as _pending  # noqa: E402
import verify_quotes as _vq  # noqa: E402
import watchlist as _wl  # noqa: E402
from personas_lib import (  # noqa: E402
    SCHEMA_VERSION,
    FrontmatterError,
    Store,
    check_locale,
    parse_iso_date,
    read_frontmatter,
    read_text_lenient,
    rel,
    resolve_store,
    sections,
)

FAST_DAYS = 180
SLOW_DAYS = 365
# section title (lowercased) -> (decay class, budget in days or None)
DECAY = {
    "mandate and incentives": ("fast", FAST_DAYS),
    "panel dynamics": ("fast", FAST_DAYS),
    "judgment criteria": ("slow", SLOW_DAYS),
    "recurring objections": ("slow", SLOW_DAYS),
    "red lines": ("slow", SLOW_DAYS),
    "language and dissent style": ("never", None),
}
LAST_EVIDENCE_RE = re.compile(r"last evidence:\s*(\d{4}-\d{2}-\d{2})", re.I)
KINDS = ("gap", "snapshot", "staleness", "offer", "schema")


# --------------------------------------------------------------------------- helpers
def parse_today(value):
    """`--today` as a date. YYYY-MM-DD only (`parse_iso_date`: the same answer on every
    interpreter, where `date.fromisoformat` alone accepts `20260922` from 3.11 on)."""
    try:
        return parse_iso_date(value)
    except ValueError:
        raise argparse.ArgumentTypeError("expected a date as YYYY-MM-DD, got %r" % value)


def clip(text, n):
    text = text or "-"
    return text if len(text) <= n else text[:n - 3] + "..."


def table(headers, rows, indent="  "):
    """Columns as wide as their widest cell: a dashboard is read, not parsed."""
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))
    out = [indent + "  ".join(h.ljust(w) for h, w in zip(headers, widths)).rstrip()]
    for row in rows:
        out.append(indent + "  ".join(c.ljust(w) for c, w in zip(row, widths)).rstrip())
    return out


def section_states(text, today):
    """-> [{section, decay, last_evidence, age_days, state}] for the judgment sections present.

    state: fresh | stale | unknown. `unknown` is a heading with no (or an unreadable) `last
    evidence:` note — the template's own dating is missing, so nothing can say whether the
    section still holds.
    """
    out = []
    for sec in sections(text):
        entry = DECAY.get(sec.title.lower())
        if entry is None:
            continue
        decay, budget = entry
        m = LAST_EVIDENCE_RE.search(sec.note or "")
        if not m:
            out.append({"section": sec.title, "decay": decay, "last_evidence": None,
                        "age_days": None, "state": "unknown"})
            continue
        try:
            seen = parse_iso_date(m.group(1))
        except ValueError:                      # a note that is not a date reads as no note
            out.append({"section": sec.title, "decay": decay, "last_evidence": m.group(1),
                        "age_days": None, "state": "unknown"})
            continue
        age = (today - seen).days
        state = "stale" if budget is not None and age > budget else "fresh"
        out.append({"section": sec.title, "decay": decay, "last_evidence": seen.isoformat(),
                    "age_days": age, "state": state})
    return out


def stale_phrase(s):
    if s["state"] == "unknown":
        return "%s (unknown)" % s["section"]
    return "%s (%dd)" % (s["section"], s["age_days"])


def snapshot_doc_key(relp):
    """`--doc` / `--set-meeting` name of a snapshot path: its stem without the `pending-`."""
    stem = Path(relp).stem
    return stem[len("pending-"):] if stem.startswith("pending-") else stem


def snapshot_status(meeting, today):
    """pending.scan dates its own status against the real day; doctor dates everything against
    --today, so the status is recomputed here from the meeting date it parsed."""
    if not meeting:
        return "no meeting date"
    try:
        day = parse_iso_date(meeting)
    except ValueError:
        return "no meeting date"
    if day < today:
        return "overdue"
    if day == today:
        return "meeting today"
    return "upcoming"


def pending_offers(store, only_context=None):
    """Offers still open: the last row in the ledger for a (context, document) pair says
    `offered`. The ledger is append-only, so file order is chronological order."""
    latest = {}
    for row in _log.read_rows(store):
        if row.get("flow") != "offer":
            continue
        doc = row.get("doc")
        if not doc:                              # an offer with no document cannot be tracked
            continue
        ctx = row.get("context") or ""
        if only_context and ctx != only_context:
            continue
        latest[(ctx, doc)] = row
    out = []
    for (ctx, doc), row in sorted(latest.items()):
        if row.get("note") == "offered":
            out.append({"context": ctx, "doc": doc, "ts": row.get("ts"), "note": "offered"})
    return out


# --------------------------------------------------------------------------- the scan
def scan_persona(store, ctx, path, sources_root, today, items, locale_ok=True):
    """One persona row, plus whatever it contributes to `items`. Never raises: a store with
    one unreadable file still gets a diagnosis of the rest. With `locale_ok` False the
    locale-dependent checks (lint, coverage) are skipped: the one `locale:` item says why."""
    ctx_name = ctx.name
    relp = rel(path, store)
    try:
        text = read_text_lenient(path)
    except OSError as e:                         # unreadable file: report it, diagnose the rest
        items.append({"kind": "gap", "context": ctx_name, "file": relp,
                      "message": "%s: cannot be read (%s)" % (path.name, e.__class__.__name__)})
        return {"context": ctx_name, "slug": path.stem, "file": relp, "lint": "-",
                "lint_status": "-", "coverage": "-", "coverage_level": "-", "sections": [],
                "stale_sections": [], "watchlist_ready": [], "schema": None}
    fm = None
    try:
        fm = read_frontmatter(text)
    except FrontmatterError as e:
        # The fields cannot be trusted, so cares_about and schema are not judged on top of it:
        # one finding, the one that has to be fixed first.
        items.append({"kind": "gap", "context": ctx_name, "file": relp,
                      "message": "%s: frontmatter outside the subset at line %d (%s)"
                                 % (path.name, e.line_no, e.reason)})
    schema = None
    if fm is not None:
        cares = fm.get("cares_about", "")
        if isinstance(cares, list):
            cares = ", ".join(cares)
        if not str(cares).strip():
            items.append({"kind": "gap", "context": ctx_name, "file": relp,
                          "message": "%s: no cares_about in the frontmatter (roster selection "
                                     "reads that field)" % path.name})
        schema = fm.get("schema") or None
        if schema != SCHEMA_VERSION:
            items.append({"kind": "schema", "context": ctx_name, "file": relp,
                          "message": "%s: schema %s, run migrate" % (path.name, schema or "none")})

    try:
        if not locale_ok:
            lint = {"label": "-", "status": "-"}
        else:
            lint = _vq.lint_persona(path, sources_root, store)
        lint_label, lint_status = lint["label"], lint["status"]
    except Exception as e:                       # one bad file must not abort the diagnosis
        # The exception text, not just its class: "error (RuntimeError)" in a column tells
        # the reader nothing they can act on.
        lint_label = "error (%s: %s)" % (e.__class__.__name__, str(e)[:80])
        lint_status = "error"
    if lint_status in ("fail", "error"):
        # A failing linter means an excerpt is not in the source it cites, which is the one
        # thing the panel gate refuses outright: `healthy` may never be printed over it.
        # A linter that could not run at all is not a linter that passed, so it is the same
        # item with its reason attached — otherwise a crash on one persona was reported as a
        # healthy store. `warn` and a thin coverage stay in the table only — they are
        # judgments about how founded a persona is, not about whether it may be used at all.
        items.append({"kind": "gap", "context": ctx_name, "file": relp,
                      "message": "%s: lint %s" % (path.name, lint_label)})
    try:
        if not locale_ok:
            cov = {"summary": "-", "level": "-"}
        else:
            cov = _cov.assess(path, ctx / "AUDIT.md" if (ctx / "AUDIT.md").is_file() else None)
        cov_summary, cov_level = cov["summary"], cov["level"]
    except Exception as e:
        # Same rule as the linter above: a check that could not run is not a check that
        # passed. Without an item, `doctor: healthy` printed over a crashed coverage run —
        # and the exception class alone told the reader nothing they could act on.
        cov_summary = "error (%s: %s)" % (e.__class__.__name__, str(e)[:80])
        cov_level = "error"
        items.append({"kind": "gap", "context": ctx_name, "file": relp,
                      "message": "%s: coverage %s" % (path.name, cov_summary)})

    states = section_states(text, today)
    stale = [s for s in states if s["state"] in ("stale", "unknown")]
    for s in stale:
        if s["state"] == "unknown":
            msg = ("%s: %s has no last evidence note (%s-decay), staleness unknown"
                   % (path.name, s["section"], s["decay"]))
        else:
            msg = ("%s: %s last evidence %s, %d days (%s-decay limit %d)"
                   % (path.name, s["section"], s["last_evidence"], s["age_days"], s["decay"],
                      DECAY[s["section"].lower()][1]))
        items.append({"kind": "staleness", "context": ctx_name, "file": relp, "message": msg})

    try:
        ready = [{"id": e["id"], "title": e["title"]} for e in _wl.parse_entries(text)
                 if not e["promoted"] and len(e["sources"]) >= 2]
    except Exception:
        ready = []

    return {"context": ctx_name, "slug": (fm or {}).get("slug") or path.stem, "file": relp,
            "lint": lint_label, "lint_status": lint_status,
            "coverage": cov_summary, "coverage_level": cov_level,
            "sections": states, "stale_sections": stale,
            "watchlist_ready": ready, "schema": schema}


def store_sources_root(store, ctx):
    """Where this context's excerpts live (`sources_root:` in context.md, else the context)."""
    try:
        return Store(store).sources_root(ctx)
    except Exception:                            # unreadable or unparseable context.md
        return ctx


def scan_snapshots(store, only_context, items):
    """-> pending.scan's rows. A crash of the scan is an item carrying the exception text
    (E4), like the lint and coverage branches; a snapshot the scan skipped as unreadable
    (reported back through its `unreadable` list) is an item too, so a skip can never read
    as a clean snapshot column."""
    if not Path(store).is_dir():
        return []
    unreadable = []
    try:
        rows = _pending.scan(Path(store), only_context, unreadable=unreadable)
    except Exception as e:
        items.append({"kind": "snapshot", "context": only_context or "", "file": "",
                      "message": "snapshots not scanned: error (%s: %s)"
                                 % (e.__class__.__name__, str(e)[:80])})
        rows = []
    for u in unreadable:
        f = str(u.get("file") or "")
        parts = Path(f).parts
        items.append({"kind": "snapshot", "context": parts[0] if len(parts) > 1 else "",
                      "file": f, "message": "%s: unreadable (%s), not scanned"
                                            % (Path(f).name, u.get("error") or "error")})
    return rows


def scan(store, only_context=None, today=None):
    """-> the whole report as a dict. Reads store files only; writes nothing."""
    today = today or dt.date.today()
    st = Store(store)
    report = {"today": today.isoformat(), "contexts": [], "personas": [], "snapshots": [],
              "gaps": [], "offers": [], "items": [], "summary": ""}
    items = report["items"]

    if not Path(store).is_dir():
        items.append({"kind": "gap", "context": "", "file": "",
                      "message": "store not found: %s" % store})
    elif only_context and not (Path(store) / only_context).is_dir():
        items.append({"kind": "gap", "context": only_context, "file": only_context,
                      "message": "context not found: %s" % only_context})

    contexts = [c for c in st.contexts() if not only_context or c.name == only_context]
    # The locale once, up front (FR-5.2): under a typo every locale-reading check would fail
    # on its own, once per persona, and the snapshots would vanish — one cause reported as
    # a dozen symptoms. One item, and the checks that need the locale are skipped.
    locale_err = check_locale()
    if locale_err:
        items.append({"kind": "gap", "context": "", "file": "",
                      "message": "locale: %s" % locale_err})
        snap_rows = []
    else:
        snap_rows = scan_snapshots(store, only_context, items)

    for ctx in contexts:
        report["contexts"].append(ctx.name)
        cm = ctx / "context.md"
        if not cm.is_file():
            items.append({"kind": "gap", "context": ctx.name, "file": rel(cm, store),
                          "message": "context.md: missing (the context declares no description, "
                                     "no sources_root and no schema)"})
        else:
            try:
                cfm = read_frontmatter(read_text_lenient(cm))
                schema = cfm.get("schema") or None
                if schema != SCHEMA_VERSION:
                    items.append({"kind": "schema", "context": ctx.name, "file": rel(cm, store),
                                  "message": "context.md: schema %s, run migrate"
                                             % (schema or "none")})
            except FrontmatterError as e:
                items.append({"kind": "gap", "context": ctx.name, "file": rel(cm, store),
                              "message": "context.md: frontmatter outside the subset at line %d "
                                         "(%s)" % (e.line_no, e.reason)})
        sources_root = store_sources_root(store, ctx)
        for p in st.personas(ctx):
            report["personas"].append(
                scan_persona(store, ctx, p, sources_root, today, items,
                             locale_ok=locale_err is None))

        for row in [r for r in snap_rows if r["context"] == ctx.name]:
            status = snapshot_status(row.get("meeting"), today)
            relp = rel(row["snapshot"], store)
            fmt, ledger = row.get("format"), row.get("ledger")
            # The table says `pre-0.2 (ledger)` only where the date-derived status has nothing
            # to say and the ledger has taken over the reading; the items below are still
            # decided by `status`, so a file with no date anywhere keeps its own remedy.
            shown = ("pre-0.2 (ledger)" if fmt == "pre-0.2" and ledger
                     and status == "no meeting date" else status)
            out = {"context": ctx.name, "file": relp, "document": row.get("document"),
                   "meeting": row.get("meeting"), "status": shown,
                   "format": fmt, "ledger": ledger,
                   "document_changed": row.get("document_changed"),
                   "decisions_recorded": row.get("decisions_recorded"),
                   "predictions": row.get("predictions")}
            report["snapshots"].append(out)
            doc_key = snapshot_doc_key(relp)
            if status == "no meeting date":
                # The remedy, not just the diagnosis (FR-1.2): this item used to repeat daily
                # with no command behind it, and the date was then recorded by hand or not at all.
                items.append({"kind": "snapshot", "context": ctx.name, "file": relp,
                              "message": "%s: no meeting date, so calibration can never come "
                                         "due — record it: beforehand.py pending --context %s "
                                         "--set-meeting %s YYYY-MM-DD"
                                         % (Path(relp).name, ctx.name, doc_key)})
            elif status == "overdue":
                items.append({"kind": "snapshot", "context": ctx.name, "file": relp,
                              "message": "%s: meeting %s has passed, offer calibration"
                                         % (Path(relp).name, row.get("meeting"))})
            if fmt == "pre-0.2" and not ledger:
                # FR-1.1: a snapshot frozen before the 0.2 shape existed is a record, not an
                # instrument. Naming the format (and the one command that brings it back into
                # the log) beats reporting the symptoms it causes downstream.
                items.append({"kind": "snapshot", "context": ctx.name, "file": relp,
                              "message": "%s: pre-0.2 format, not gradeable — reconstruct its "
                                         "ledger (calibrate --ledger)" % Path(relp).name})
            if row.get("document_changed") is True:
                items.append({"kind": "snapshot", "context": ctx.name, "file": relp,
                              "message": "%s: %s changed since the snapshot was frozen"
                                         % (Path(relp).name, row.get("document"))})

    for offer in pending_offers(Path(store), only_context):
        report["offers"].append(offer)
        items.append({"kind": "offer", "context": offer["context"], "file": "usage.jsonl",
                      "message": "offer on %s is still open (offered %s, never accepted or "
                                 "declined)" % (offer["doc"], offer["ts"] or "?")})

    report["gaps"] = [i for i in items if i["kind"] in ("gap", "schema")]
    n = len(items)
    report["summary"] = "doctor: healthy" if n == 0 else "doctor: %d items need attention" % n
    return report


# --------------------------------------------------------------------------- reporting
def render(report):
    """The human report: one block per context, then the pinned last line."""
    out = []
    for ctx in report["contexts"]:
        personas = [p for p in report["personas"] if p["context"] == ctx]
        snaps = [s for s in report["snapshots"] if s["context"] == ctx]
        gaps = [g for g in report["gaps"] if g["context"] == ctx]
        offers = [o for o in report["offers"] if o["context"] == ctx]
        out.append("context: %s" % ctx)
        out.append("")
        out.append("  personas")
        rows = [[p["slug"], clip(p["lint"], 34), p["coverage_level"],
                 clip("; ".join(stale_phrase(s) for s in p["stale_sections"]), 44),
                 str(len(p["watchlist_ready"])), p["schema"] or "-"] for p in personas]
        out += (table(["slug", "lint", "coverage", "stale sections", "READY", "schema"], rows)
                if rows else ["    (no personas)"])
        out.append("")
        out.append("  snapshots")
        rows = [[clip(s["document"], 48), s["meeting"] or "unknown", s["status"],
                 {True: "yes", False: "no"}.get(s["document_changed"], "-"),
                 "recorded" if s["decisions_recorded"] else "missing"] for s in snaps]
        out += (table(["doc", "meeting", "status", "doc changed", "decisions"], rows)
                if rows else ["    (no pending snapshots)"])
        ready = [(p["slug"], e) for p in personas for e in p["watchlist_ready"]]
        if ready:
            out.append("")
            out.append("  watchlist READY (two or more sources; promotion is your call)")
            for slug, e in ready:
                out.append("    - %s | %s | %s" % (slug, e["id"] or "(no id)", clip(e["title"], 60)))
        out.append("")
        out.append("  gaps")
        out += ["    - " + g["message"] for g in gaps] or ["    (none)"]
        out.append("")
        out.append("  offers pending")
        out += ["    - %s (offered %s)" % (o["doc"], o["ts"] or "?") for o in offers] or \
               ["    (none)"]
        out.append("")
    # Every item, not only the ones the per-context blocks above happen to cover: an item can
    # name a context that has no directory (an offer logged against a context never created,
    # a --context that does not exist), and a count with no visible line behind it is worse
    # than a repeated line.
    items = report["items"]
    if items:
        width = max(len(i["kind"]) for i in items)
        out.append("items needing attention (%d)" % len(items))
        for i in items:
            out.append("    - %s | %s | %s"
                       % (i["kind"].ljust(width), i["context"] or "-", i["message"]))
        out.append("")
    out.append(report["summary"])
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--store", default=None)
    ap.add_argument("--context", help="diagnose one context instead of every context")
    ap.add_argument("--today", type=parse_today, default=None,
                    help="the date staleness is measured against (default: today)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    store = resolve_store(a.store)
    report = scan(store, a.context, a.today or dt.date.today())
    if a.json:
        print(json.dumps(report, ensure_ascii=False, indent=1))
    else:
        print(render(report))
    return 0                                     # a report, whatever it found


if __name__ == "__main__":
    sys.exit(main())
