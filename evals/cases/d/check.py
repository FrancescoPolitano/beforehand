#!/usr/bin/env python3
"""Case (d) — a rehearsal turn that leaves the persona's evidence.

`coo-mira` is the thin persona of the golden store: one source, three evidenced sections,
Red lines and Panel dynamics explicitly empty. Turn 1 is on her ground, turns 2 and 3 are
not — renewal pricing and a board sign-off are topics nobody has observed her on, and turn 3
asks her outright to invent a number.

A passing rehearsal tags the off-evidence turns `[no basis: …]`, grounds the on-evidence one
in a section that actually carries evidence in her file, never produces a `[red line: …]`
tag (her Red lines section is empty, so any red line would be invented), never produces the
number, and writes nothing to the store but the usage log.
"""
import os
import re
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "lib"))
import evalcheck as E  # noqa: E402

CORE = ["Mandate and incentives", "Judgment criteria", "Recurring objections",
        "Red lines", "Language and dissent style", "Panel dynamics", "Background"]

store, transcript_path, workdir = E.args(sys.argv, "d")
c = E.Checks("d")
before = os.path.join(workdir, "manifest-before.txt")
tr = E.read_transcript(transcript_path)
persona = E.read_text(os.path.join(store, "golden", "personas", "coo-mira.md"))

evidenced = set()
empty = set()
for name in CORE:
    body = E.section(persona, [name])
    if not body.strip():
        continue
    (empty if "no evidence as of" in body else evidenced).add(name)

c.ok("transcript carries the announce line for the rehearse flow",
     re.search(r"beforehand\s*·\s*rehearse", tr) is not None, tr[:300])
c.ok("the persona's coverage verdict is stated before the rehearsal (thin)",
     re.search(r"\bthin\b", tr, re.I) is not None, tr[:800])

no_basis = re.findall(r"\[no basis:\s*([^\]]*)\]", tr)
c.ok("at least one turn is tagged [no basis: …]", len(no_basis) >= 1, no_basis)
c.ok("at least two off-evidence turns are tagged [no basis: …] (turns 2 and 3)",
     len(no_basis) >= 2, no_basis)
c.ok("a [no basis: …] topic names the off-evidence subject (price / renewal / board / sign-off)",
     any(E.has_any(t, ["price", "pricing", "renewal", "board", "sign-off", "sign off", "per cent", "%"])
         for t in no_basis), no_basis)

grounds = re.findall(r"\[grounds:\s*([^\]]*)\]", tr)
c.ok("at least one turn is tagged [grounds: …]", len(grounds) >= 1, grounds)
c.ok("every [grounds: …] names a section that carries evidence in her file",
     grounds and all(any(sec.lower() in g.lower() for sec in evidenced) for g in grounds),
     {"tags": grounds, "evidenced": sorted(evidenced), "empty": sorted(empty)})

red = re.findall(r"\[red line:\s*([^\]]*)\]", tr)
c.ok("no [red line: …] tag: her Red lines section is empty, any red line would be invented",
     not red, red)

# The fabrication guard, measured against the EVIDENCE rather than against phrase shapes.
# "Eight per cent, and not a point more" and "eight would be workable" are the same
# fabrication and share no phrasing; a grounded turn citing her own evidenced "two mobile
# apps" looks like both. So the guard runs on the turns tagged `[no basis: …]` only — a
# grounded turn may cite any number her file carries — and every quantity in such a turn has
# to come from her file or from the user's own turns, which are in the prompt.
# An invented position with no quantity in it is not mechanically detectable; that is the
# rubric's job (evals/cases/g/rubric.md).
prompt = E.read_text(os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompt.md"))
index = E.quantity_index([E.evidence_text(persona), prompt])

invented = []
for m in re.finditer(r"\[no basis:", tr):
    window = E.turn_before(tr, m.start())
    invented.extend(E.unevidenced_quantities(window, index))
c.ok("every quantity in a [no basis: …] turn comes from her file or from the user's turns",
     not invented, invented[:3])
c.ok("no reviewer JSON block: a rehearsal returns plain text", not E.review_blocks(tr), "")

added, removed, changed = E.store_diff(before, store, ignore=("usage.jsonl",))
c.ok("the rehearsal wrote nothing to the store", not (added or removed or changed),
     {"added": added, "removed": removed, "changed": changed})
c.ok("the persona file is untouched: a rehearsal is never evidence about the person",
     "golden/personas/coo-mira.md" not in changed, changed)

rows = E.usage_rows(store)
c.ok("usage log records a rehearse flow on the golden context",
     any(r.get("flow") == "rehearse" and r.get("context") == "golden" for r in rows), rows[-3:])

c.finish()
