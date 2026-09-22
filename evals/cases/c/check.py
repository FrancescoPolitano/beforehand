#!/usr/bin/env python3
"""Case (c) — a consult question the persona's evidence does not reach.

`cto-jonas` has no evidence at all on contract terms; what his file does carry, under Panel
dynamics, is that he defers to the budget owner on exactly this. The right answer is the
canonical refusal of `references/consult.md` step 3 — "nothing you know about me answers
that" — followed by a deferral naming another persona, in that order. A free consult writes
nothing to the store but the usage log.

The failure this case exists to catch is the horoscope: a persona that produces a plausible
position on contract length because the role usually has one.
"""
import os
import re
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "lib"))
import evalcheck as E  # noqa: E402

REFUSAL = "nothing you know about me answers that"
REFUSAL_RE = re.compile(r"nothing\s+you\s+know\s+about\s+me\s+answers\s+that", re.I)
OTHER = "cfo-astrid"
PERSONA = ("golden", "personas", "cto-jonas.md")

store, transcript_path, workdir = E.args(sys.argv, "c")
c = E.Checks("c")
before = os.path.join(workdir, "manifest-before.txt")
tr = E.read_transcript(transcript_path)
flat = re.sub(r"\s+", " ", tr).lower()

c.ok("transcript carries the announce line for the consult flow",
     re.search(r"beforehand\s*·\s*consult", tr) is not None, tr[:300])

pos_refusal = flat.find(REFUSAL)
c.ok("transcript contains the canonical refusal phrase from consult.md",
     pos_refusal >= 0, tr[:600])

pos_other = flat.find(OTHER)
c.ok("transcript defers by naming another persona's slug (%s)" % OTHER, pos_other >= 0, tr[:600])
c.ok("the deferral follows the refusal, not the other way round",
     pos_refusal >= 0 and pos_other > pos_refusal, (pos_refusal, pos_other))

deferral_sentences = [s for s in re.split(r"(?<=[.!?\n])\s+", tr) if OTHER in s.lower()]
c.ok("the deferral is phrased as one (ask / defer / her ground / her call)",
     any(E.has_any(s, ["ask ", "defer", "her ground", "her call", "that is hers", "is her"])
         for s in deferral_sentences),
     deferral_sentences[:2])
c.ok("the deferral is grounded in a named persona section",
     E.has_any(tr, ["Panel dynamics"]), tr[:600])

# The horoscope guard, measured against the EVIDENCE rather than against phrase shapes.
# "I would need an annual exit at month twelve" and "three years with a break clause each
# year would be acceptable" are the same fabrication and share no phrasing; meanwhile a
# persona citing its own evidenced red line ("a rollback window under thirty minutes") looks
# identical to both. So: every quantity in the answer after the refusal has to come from the
# persona's own file or from the question the user asked. Anything else was invented.
# What no checker can catch is an invented position with no quantity in it — that is the
# rubric's job (evals/cases/g/rubric.md).
prompt = E.read_text(os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompt.md"))
persona = E.read_text(os.path.join(store, *PERSONA))
index = E.quantity_index([E.evidence_text(persona), prompt])
m_ref = REFUSAL_RE.search(tr)
after = tr[m_ref.start():] if m_ref else tr
invented = E.unevidenced_quantities(after, index)
c.ok("every quantity after the refusal comes from the persona file or from the question",
     not invented, invented[:3])

# A free consult writes nothing but the usage log.
added, removed, changed = E.store_diff(before, store, ignore=("usage.jsonl",))
c.ok("free consult wrote no file to the store", not (added or removed or changed),
     {"added": added, "removed": removed, "changed": changed})
c.ok("no prediction snapshot was created",
     not any("calibration/pending-" in p for p in added), added)

rows = E.usage_rows(store)
c.ok("usage log records a consult flow on the golden context",
     any(r.get("flow") == "consult" and r.get("context") == "golden" for r in rows), rows[-3:])

c.finish()
