#!/usr/bin/env python3
"""Case (a) — authoring a Wanted stakeholder from the context's own sources.

What a passing run must have produced: exactly one new persona file in `golden/personas/`,
built only from the sources already in the store; it passes the excerpt linter as a gate;
it rests on between 8 and 14 Facts (fewer means one thin source was used and the other two
ignored, more means the tags were padded or split); and every core section of the template
is either evidenced or explicitly declared empty. The sources themselves are unchanged —
authoring reads them, it never edits them.
"""
import os
import re
import subprocess
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "lib"))
import evalcheck as E  # noqa: E402

CORE = ["Mandate and incentives", "Judgment criteria", "Recurring objections",
        "Red lines", "Language and dissent style", "Panel dynamics"]
FACT_TAG = re.compile(r"\(Fact\b")

store, transcript_path, workdir = E.args(sys.argv, "a")
c = E.Checks("a")
ctx = os.path.join(store, "golden")
before = os.path.join(workdir, "manifest-before.txt")
added, removed, changed = E.store_diff(before, store, ignore=("usage.jsonl",))

new_personas = [p for p in added if p.startswith("golden/personas/") and p.endswith(".md")]
c.ok("exactly one new persona file under golden/personas/", len(new_personas) == 1,
     new_personas or added)
if len(new_personas) != 1:
    c.finish()

persona_rel = new_personas[0]
persona_path = os.path.join(store, persona_rel)
text = E.read_text(persona_path)
slug_m = re.search(r"^slug:\s*(\S+)\s*$", text, re.M)

c.ok("persona frontmatter declares a slug", slug_m is not None, text[:200])
c.ok("persona frontmatter declares context: golden",
     re.search(r"^context:\s*golden\s*$", text, re.M) is not None, text[:400])
c.ok("persona frontmatter declares schema: 0.2",
     re.search(r"^schema:\s*0\.2\s*$", text, re.M) is not None, text[:400])
c.ok("persona frontmatter declares decision_function: economic buyer",
     re.search(r"^decision_function:\s*economic buyer\s*$", text, re.M) is not None, text[:400])

lint = subprocess.run(
    [sys.executable,
     os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..",
                  "skills", "beforehand", "scripts", "beforehand.py"),
     "lint", persona_path, "--sources-root", os.path.join(ctx, "sources"), "--lint"],
    capture_output=True, text=True, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
c.ok("lint --lint gate exits 0 (no NOT FOUND, no UNPARSEABLE)",
     lint.returncode == 0, (lint.returncode, lint.stdout[-400:] + lint.stderr[-200:]))
summary = re.search(r"^Summary:.*$", lint.stdout, re.M)
summary = summary.group(0) if summary else ""
# A --lint exit of 0 is not enough on its own: 100% UNVERIFIABLE also exits 0. The excerpts
# have to have been found in the sources that are sitting right there in the store.
c.ok("every excerpt VERIFIED against a source in the store (0 UNVERIFIABLE)",
     "UNVERIFIABLE: 0 (0%)" in summary and "VERIFIED: 0 (0%)" not in summary, summary)
c.ok("no MISPLACED excerpt (each quote is in the section it is cited for)",
     "MISPLACED: 0 (0%)" in summary, summary)

facts = len(FACT_TAG.findall(text))
c.ok("Fact count within [8, 14] (got %d)" % facts, 8 <= facts <= 14, facts)

for name in CORE:
    body = E.section(text, [name])
    evidenced = bool(FACT_TAG.search(body)) or "(Inference" in body or "(Assumption" in body
    declared = "no evidence as of" in body
    c.ok("section %r is evidenced or declares 'no evidence as of'" % name,
         bool(body.strip()) and (evidenced or declared), body[:200])

c.ok("no core section was left with an empty body",
     all(E.section(text, [n]).strip() for n in CORE), [n for n in CORE if not E.section(text, [n]).strip()])

# The persona must cite more than the one source named in the prompt: the flow was told the
# other sources exist, and a persona built on one transcript is the thin one this case is
# designed to catch.
cited = set(re.findall(r"(2026-\d\d-\d\d-[a-z]+\.txt)", text))
c.ok("at least two distinct sources cited", len(cited) >= 2, sorted(cited))
c.ok("every cited source exists in the context",
     all(os.path.exists(os.path.join(ctx, "sources", s)) for s in cited), sorted(cited))

src_touched = [p for p in (changed + removed) if p.startswith("golden/sources/")]
c.ok("sources unchanged by the authoring flow", not src_touched, src_touched)

index = E.read_text(os.path.join(ctx, "INDEX.md")) if os.path.exists(os.path.join(ctx, "INDEX.md")) else ""
slug = slug_m.group(1) if slug_m else "?"
c.ok("context INDEX.md regenerated with the new persona line",
     re.search(r"^- %s \|" % re.escape(slug), index, re.M) is not None, index[:600])

flows = [r.get("flow") for r in E.usage_rows(store)]
c.ok("usage log records an authoring flow", "authoring" in flows, flows[-5:])

tr = E.read_transcript(transcript_path)
c.ok("transcript carries the announce line for the authoring flow",
     re.search(r"beforehand\s*·\s*authoring", tr) is not None, tr[:300])

c.finish()
