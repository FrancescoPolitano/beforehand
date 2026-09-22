#!/usr/bin/env python3
"""Case (g) — FR-3.6 on/off, rubric-graded.

Case (b)'s prompt run twice: once with `assets/reviewer-examples.md` as it ships, once with
its three example blocks removed. The second transcript is `<workdir>/transcript-off.md`.

This checker does the arithmetic and stops there. It asserts only that both runs are usable
— both transcripts present, each with reviewer blocks that parse and carry the fields the
rubric is read against — and then prints four measured numbers per run and the rubric. The
verdict is the maintainer's: whether the examples change the *content* of the objections is
not a thing a grep can decide, and a checker that pretended otherwise would be the "output
non-empty" assertion in disguise.
"""
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "lib"))
import evalcheck as E  # noqa: E402

store, transcript_path, workdir = E.args(sys.argv, "g")
c = E.Checks("g")
doc_path = os.path.join(store, "golden", "docs", "brief-q3-flawed.md")
document = E.read_text(doc_path) if os.path.exists(doc_path) else ""
doc_flat = " ".join(document.split()).lower()

runs = [("examples on", transcript_path),
        ("examples off", os.path.join(workdir, "transcript-off.md"))]

measured = []
for label, path in runs:
    exists = os.path.exists(path)
    c.ok("transcript present for the '%s' run" % label, exists, path)
    if not exists:
        continue
    tr = E.read_transcript(path)
    blocks = E.review_blocks(tr)
    c.ok("'%s' run returned at least one reviewer block" % label, len(blocks) >= 1, len(blocks))
    c.ok("every reviewer block of the '%s' run parses as JSON" % label,
         blocks and all(b is not None for b, _ in blocks), [raw[:80] for b, raw in blocks if b is None])
    parsed = [b for b, _ in blocks if b is not None]
    if not parsed:
        continue

    objs = []
    for b in parsed:
        objs.extend(b.get("objections") or [])
    c.ok("'%s' run: every objection carries quote, grounds and severity" % label,
         objs and all({"quote", "grounds", "severity"} <= set(o) for o in objs),
         [o for o in objs if not {"quote", "grounds", "severity"} <= set(o)][:1])

    anchored = sum(1 for o in objs
                   if " ".join(str(o.get("quote", "")).split()).lower() in doc_flat
                   and str(o.get("quote", "")).strip())
    sevs = [o.get("severity") for o in objs if isinstance(o.get("severity"), int)]
    measured.append({
        "run": label,
        "personas": len(parsed),
        "objections": len(objs),
        "anchor rate": "%d/%d" % (anchored, len(objs)) if objs else "0/0",
        "mean severity": round(sum(sevs) / float(len(sevs)), 2) if sevs else None,
        "grounds sections": len(set(str(o.get("grounds", "")) for o in objs)),
        "no_basis items": sum(len(b.get("no_basis") or []) for b in parsed),
    })

print("")
print("case g — measured, for the rubric below (nothing here is a pass or a fail)")
print("| Run | Personas | Objections | Verbatim anchors | Mean severity | Distinct grounds | no_basis |")
print("|---|---|---|---|---|---|---|")
for m in measured:
    print("| %s | %d | %d | %s | %s | %d | %d |" % (
        m["run"], m["personas"], m["objections"], m["anchor rate"],
        m["mean severity"], m["grounds sections"], m["no_basis items"]))
print("")
print(E.read_text(os.path.join(os.path.dirname(os.path.abspath(__file__)), "rubric.md")))

c.finish()
