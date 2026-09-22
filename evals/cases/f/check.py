#!/usr/bin/env python3
"""Case (f) — the negative trigger.

A request to summarise a quarter's figures names no stakeholder, no document going to a
decision, and no person the store knows. The skill must not fire: rule 2 of the interaction
model is that a flow runs on a request or an accepted offer, never because it looks useful.
A persona store sitting in `BEFOREHAND_STORE`, with the skill installed, is exactly the
condition under which a skill that over-triggers does so.

The assertion is the announce line: every flow opens with `beforehand · <flow> · store …`, so
its absence is the machine-checkable form of "the skill did not run". Two guards keep this
from passing on a transcript that failed for another reason: the store must be byte-for-byte
what it was (an over-trigger that ran doctor and logged an offer would show up there), and
the answer must actually summarise the figures it was given.
"""
import os
import re
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "lib"))
import evalcheck as E  # noqa: E402

store, transcript_path, workdir = E.args(sys.argv, "f")
c = E.Checks("f")
before = os.path.join(workdir, "manifest-before.txt")
tr = E.read_transcript(transcript_path)

# The skill's name changed to `beforehand` in v0.2; the pre-rename prefix is still matched,
# so a stale install announcing the old name is caught as the over-trigger it is.
ANNOUNCE = r"(?:beforehand|personas)\s*[·•]"

c.ok("no `beforehand ·` announce line in the transcript",
     re.search(ANNOUNCE, tr) is None,
     (re.search(r".{0,60}" + ANNOUNCE + r".{0,60}", tr) or [""])[0])
c.ok("no flow name announced either",
     re.search(ANNOUNCE + r"\s*(authoring|review|regression|calibration|consult|rehearse|import)",
               tr, re.I) is None, "")
c.ok("no reviewer JSON block was produced", not E.review_blocks(tr), "")
c.ok("no persona slug from the store is named",
     not E.has_any(tr, ["cfo-astrid", "cto-jonas", "coo-mira"]),
     [s for s in ("cfo-astrid", "cto-jonas", "coo-mira") if s in tr])

added, removed, changed = E.store_diff(before, store)
c.ok("the store is untouched, usage log included", not (added or removed or changed),
     {"added": added, "removed": removed, "changed": changed})
c.ok("no usage row was appended (no flow, no offer)", not E.usage_rows(store),
     E.usage_rows(store)[-2:])

# Guard: the run must have answered the question, or "no announce line" would pass on a
# transcript in which nothing happened at all.
figures = ["4.12", "31", "2.4", "148"]
present = [f for f in figures if f in tr]
c.ok("the answer summarises the figures it was given (at least three of four)",
     len(present) >= 3, present)

c.finish()
