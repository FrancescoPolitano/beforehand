#!/usr/bin/env python3
"""Unit checks for the eval library's quantity tokeniser and evidence index.

The checkers in `evals/cases/*/check.py` are only as good as this tokeniser: everything the
fabrication guard decides comes down to which strings it calls a quantity and where it looks
for the legitimate ones. Two classes of bug have already shipped here — bookkeeping counted
as a quantity (`P1`, `[wl-01]`, `#3`, a date), and persona metadata counted as evidence
(`decision_weight: 3`, `## Reliability`) — so both are pinned by name below.

Run by `evals/run.sh --checkers-only`; exits 0 or 1 and prints one `ok`/`FAIL` line per
assertion, like every other checker in the suite.
"""
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import evalcheck as E  # noqa: E402

c = E.Checks("lib")


def tokens(text):
    """The (number, unit) pairs the tokeniser finds, as comparable tuples."""
    return [(n, u) for n, u, _ in E.quantities(text)]


# ---------------------------------------------------------------- excluded: bookkeeping
for label, text in [
    ("an ISO date", "frozen 2026-06-30, reviewed 2026-07-02"),
    ("a clock time", "frozen: 2026-06-30 09:00 and again at 14:05:30"),
    ("a schema version", "schema: 0.2"),
    ("a bare year", "the 2026 steering round"),
    ("a prediction id", "P1 and P2 graded, R2 unmatched"),
    ("a watchlist id", "[wl-01] possible openness to a phased rollout"),
    ("a hash-prefixed key", "cfo-astrid#3 role-generic, item #3 and #n.1"),
    ("a bracketed row id", "rows [P3] and [R2] overruled"),
]:
    c.ok("excluded: %s" % label, tokens(text) == [], (text, tokens(text)))

# ---------------------------------------------------------------- included: real quantities
for label, text, want in [
    ("a spelled duration", "a rollback window under thirty minutes", [("thirty", "minute")]),
    ("a digit percentage", "drop the price by 12%", [("12", "percent")]),
    ("a spelled percentage", "twelve per cent off", [("twelve", "percent")]),
    ("a spelled year count", "three years with a break clause", [("three", "year")]),
    ("a digit with a plain noun", "2 apps on the handset", [("2", None)]),
    ("a decimal", "revenue of 4.12 against plan", [("4.12", None)]),
    ("a plural unit folded to singular", "eighteen months", [("eighteen", "month")]),
]:
    c.ok("included: %s" % label, tokens(text) == want, (text, tokens(text), want))

c.ok("`one`, `half` and `quarter` are not bare quantities (ordinary English words)",
     E.BARE_EXCLUDED == {"one", "half", "quarter"}, sorted(E.BARE_EXCLUDED))

idx = E.quantity_index(["a rollback window under thirty minutes"])
c.ok("a unit-bearing quantity must match number AND unit",
     [t for t, _ in E.unevidenced_quantities("thirty per cent off", idx)] == ["thirty percent"],
     E.unevidenced_quantities("thirty per cent off", idx))
c.ok("the same number with the same unit is licensed",
     E.unevidenced_quantities("under thirty minutes", idx) == [], "")
c.ok("`one` needs no licence, having none to need",
     E.unevidenced_quantities("a question like this one", idx) == [], "")

# ---------------------------------------------------------------- evidence scope
STORE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "..", "..", "skills", "beforehand", "scripts", "test_fixtures",
                     "store", "golden", "personas")
mira = E.read_text(os.path.join(STORE, "coo-mira.md"))
jonas = E.read_text(os.path.join(STORE, "cto-jonas.md"))

ev_mira = E.evidence_text(mira)
c.ok("evidence_text keeps the judgment sections",
     "drivers already fight with two mobile apps" in ev_mira, ev_mira[:200])
c.ok("evidence_text drops the frontmatter (decision_weight is bookkeeping, not evidence)",
     "decision_weight" not in ev_mira and "aliases" not in ev_mira, ev_mira[:200])
c.ok("evidence_text drops ## Reliability (a measurement of the file, not of the person)",
     "cycles" not in ev_mira and "cycle:" not in ev_mira, ev_mira[-200:])
c.ok("evidence_text drops ## Watchlist (candidate material is not yet evidence)",
     "wl-01" not in E.evidence_text(jonas), E.evidence_text(jonas)[-300:])

nums_mira, _ = E.quantity_index([ev_mira])
c.ok("a persona's own decision_weight is not a licensed quantity",
     "3" not in nums_mira, sorted(nums_mira))
nums_jonas, pairs_jonas = E.quantity_index([E.evidence_text(jonas)])
c.ok("the technical lead's decision_weight is not licensed either",
     "4" not in nums_jonas, sorted(nums_jonas))
c.ok("his evidenced red line IS licensed (thirty minutes)",
     ("thirty", "minute") in pairs_jonas, sorted(pairs_jonas))

c.finish()
