#!/usr/bin/env python3
"""Append one line to the local usage log of the personas store, or read its tail back.

Local file, no network: `~/.beforehand/usage.jsonl`. It exists so that the skill's own
use can be audited later (which flows run, how often, on which contexts): a hook on the
skill-invocation tool misses the flows started from an already-loaded reference, which
in practice is most reviews and consults.

The `offer` flow makes the log a small ledger (SPEC-0.2 FR-5.5). "Offer once per source, a
decline holds for the session" has no state of its own, so after a compaction the model
cannot know whether it already offered. Writing `offered | accepted | declined` against a
document reference gives that rule a memory, and reading it back before offering is what the
read mode below is for; `doctor` lists the offers that were never answered. The three notes
are pinned: any other note on the `offer` flow is a usage error, because a ledger nobody can
query is a log again.

Usage:
  log_flow.py <flow> <context> [--doc NAME] [--note TEXT] [--store ~/.beforehand]
  log_flow.py offer <context> --doc NAME --note offered|accepted|declined
  log_flow.py --last N [--flow F] [--context C] [--json] [--store ~/.beforehand]
  flow: authoring | update | review | regression | calibration | consult | rehearse | import | offer
"""
import sys

sys.dont_write_bytecode = True  # before any sibling import (G5)

import argparse  # noqa: E402
import datetime as dt  # noqa: E402
import json  # noqa: E402
from pathlib import Path  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from personas_lib import append_line, read_text_lenient, resolve_store  # noqa: E402

OFFER_NOTES = ("offered", "accepted", "declined")


def read_rows(store):
    """-> the usage log as a list of dicts, oldest first; [] when there is none.

    A line that is not JSON is skipped rather than fatal: the file is append-only and
    hand-editable, and one bad line must not hide the rest of the ledger.
    """
    path = Path(store) / "usage.jsonl"
    if not path.is_file():
        return []
    rows = []
    for line in read_text_lenient(path).splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def select(rows, last, flow=None, context=None):
    """The tail of the log after filtering: the last `last` rows that match."""
    out = [r for r in rows
           if (flow is None or r.get("flow") == flow)
           and (context is None or r.get("context") == context)]
    return out[-last:] if last > 0 else []


def format_row(row):
    return " | ".join([row.get("ts") or "-", row.get("flow") or "-", row.get("context") or "-",
                       row.get("doc") or "-", row.get("note") or "-"])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("flow", nargs="?")
    ap.add_argument("context", nargs="?")
    ap.add_argument("--doc", default=None)
    ap.add_argument("--note", default=None)
    ap.add_argument("--store", default=None)
    ap.add_argument("--last", type=int, default=None, metavar="N",
                    help="print the last N matching rows instead of writing one")
    ap.add_argument("--flow", dest="flow_filter", default=None,
                    help="with --last: only rows of this flow")
    ap.add_argument("--context", dest="context_filter", default=None,
                    help="with --last: only rows of this context")
    ap.add_argument("--json", action="store_true", help="with --last: print the rows as JSON")
    a = ap.parse_args(argv)
    store = resolve_store(a.store)

    if a.last is not None:
        rows = select(read_rows(store), a.last, a.flow_filter, a.context_filter)
        if a.json:
            print(json.dumps(rows, ensure_ascii=False))
        else:
            for row in rows:
                print(format_row(row))
        return 0                                  # reading writes nothing, not even the file

    if not a.flow or not a.context:
        print("usage: log_flow.py <flow> <context> [--doc NAME] [--note TEXT]\n"
              "       log_flow.py --last N [--flow F] [--context C] [--json]", file=sys.stderr)
        return 1
    if a.flow == "offer" and a.note not in OFFER_NOTES:
        print("usage: the offer flow takes --note %s (got %s); doctor reads those three to "
              "tell an open offer from an answered one" % (" | ".join(OFFER_NOTES),
                                                           repr(a.note) if a.note else "none"),
              file=sys.stderr)
        return 1
    if a.flow == "offer" and not a.doc:
        # The ledger is keyed by (context, document): an offer with no --doc can never be
        # answered by a later accepted/declined, so it would stay open for ever.
        print("usage: the offer flow takes --doc <source or document reference>: the ledger "
              "matches an answer to an offer by that reference", file=sys.stderr)
        return 1

    store.mkdir(parents=True, exist_ok=True)
    row = {"ts": dt.datetime.now().isoformat(timespec="seconds"), "flow": a.flow, "context": a.context}
    if a.doc:
        row["doc"] = a.doc
    if a.note:
        row["note"] = a.note
    # append_line (E5): the file is hand-editable, and a last line saved without its newline
    # used to swallow this row — `{…offered}{…declined}` parses as neither, and the offer
    # ledger lost both the offer and its answer without a word.
    append_line(store / "usage.jsonl", json.dumps(row, ensure_ascii=False))
    print(f"logged {a.flow} on {a.context}")
    return 0


if __name__ == "__main__":
    print("deprecated: use beforehand.py log", file=sys.stderr)
    sys.exit(main())
