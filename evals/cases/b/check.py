#!/usr/bin/env python3
"""Case (b) — review of a document with three planted flaws, one per persona's ground.

`docs/brief-q3-flawed.md` plants, deliberately:
  1. a five-year term with no break clause and no named savings baseline — the budget
     owner's red line and judgment criterion;
  2. a Friday production cutover with a four-hour rollback — the technical lead's two red
     lines;
  3. a third driver app with offline confirmation deferred, sold on a procurement calendar
     that awards the contract after go-live — the thin persona's recurring objection, plus
     a date inconsistency that no persona's evidence covers.

A passing run names the first three themes in the prioritized fix list, names the fourth
somewhere in the report (fix list, out-of-persona observations or the unrepresented
decision function), leaves the document byte-identical, and writes a snapshot that carries
the `control:` header and round-1 rows only.
"""
import os
import re
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "lib"))
import evalcheck as E  # noqa: E402

DOC = "golden/docs/brief-q3-flawed.md"
ROSTER = {"cfo-astrid", "cto-jonas", "coo-mira"}

store, transcript_path, workdir = E.args(sys.argv, "b")
c = E.Checks("b")
ctx = os.path.join(store, "golden")
before = os.path.join(workdir, "manifest-before.txt")
added, removed, changed = E.store_diff(before, store, ignore=("usage.jsonl",))

# --- the document under review is never edited by a plain review
c.ok("document under review unchanged (sha1 identical)",
     DOC not in changed and DOC not in removed, (changed, removed))
doc_sha1 = E.sha1_of(os.path.join(store, DOC))
c.ok("document sha1 matches the one recorded before the run",
     E.read_manifest(before).get(DOC) == doc_sha1, doc_sha1)

# --- the review report
reports = [p for p in added
           if re.match(r"^golden/reviews/\d{4}-\d\d-\d\d-.*brief-q3-flawed.*\.md$", p)]
c.ok("a review report was written as reviews/YYYY-MM-DD-brief-q3-flawed.md",
     len(reports) == 1, reports or added)
report = E.read_text(os.path.join(store, reports[0])) if len(reports) == 1 else ""

fixes = E.section(report, ["fix list", "prioritized fix", "prioritised fix"])
c.ok("report has a prioritized fix list section", bool(fixes.strip()), report[:400])

THEMES = [
    ("multi-year term without a break clause",
     [["five-year", "5-year", "five year", "multi-year", "term"],
      ["break clause", "break-clause"]]),
    ("Friday cutover / rollback window",
     [["friday"], ["cutover", "rollback"]]),
    ("third driver app with offline confirmation deferred",
     [["third", "offline"], ["app", "offline"]]),
]
for name, groups in THEMES:
    c.ok("fix list names the theme: %s" % name,
         all(E.has_any(fixes, g) for g in groups), fixes[:400])

# The procurement flaw is the two dates that cannot both hold, not the word "procurement":
# either the report names both dates, or it says in so many words that the calendar
# contradicts itself, within reach of the word it is talking about.
both_dates = E.has_any(report, ["5 October"]) and E.has_any(report, ["1 September"])
near = False
for m in re.finditer(r"procurement", report, re.I):
    window = report[max(0, m.start() - 300):m.start() + 300]
    if re.search(r"inconsisten|contradict|cannot both|cannot all hold|impossible|after go-live",
                 window, re.I):
        near = True
        break
c.ok("report names the procurement-date flaw (both dates, or names the contradiction)",
     both_dates or near, {"both_dates": both_dates, "contradiction_near_procurement": near})
c.ok("report names the unrepresented decision function (gatekeeper / procurement)",
     E.has_any(report, ["gatekeeper", "head of procurement"]), report[:600])

# "Does not rewrite the document" is primarily the sha1 above; these two catch a report that
# left the file alone but handed over replacement prose instead, which hygiene rule 2 forbids
# just as much.
verbs = re.compile(r"(?mi)^\s*(?:[-*>]\s*|\d+\.\s*)?\**\s*"
                   r"(replace (?:it |this |the \w+ )?with|rewrite (?:it |this )?as|"
                   r"suggested wording|suggested text|new wording|proposed wording|"
                   r"revised wording|change (?:it |this )?to)\b")
c.ok("no replacement-wording instruction in the report",
     verbs.search(report) is None, (verbs.search(report) or [""])[0])

doc_lines = set(ln.strip() for ln in E.read_text(os.path.join(store, DOC)).splitlines()
                if len(ln.strip()) > 20)
long_quoting_fence = None
for m in re.finditer(r"```[^\n]*\n(.*?)```", report, re.S):
    body = [ln.strip() for ln in m.group(1).splitlines() if ln.strip()]
    if len(body) > 4 and sum(1 for ln in body if ln in doc_lines) >= 2:
        long_quoting_fence = m.group(1)[:200]
        break
c.ok("no fenced block long enough to be a rewritten passage of the document",
     long_quoting_fence is None, long_quoting_fence)

# --- the prediction snapshot
snaps = [p for p in added if p == "golden/calibration/pending-brief-q3-flawed.md"]
c.ok("prediction snapshot written to calibration/pending-brief-q3-flawed.md",
     len(snaps) == 1, [p for p in added if "calibration" in p])
snap = E.read_text(os.path.join(store, snaps[0])) if snaps else ""

c.ok("snapshot carries the pinned `control:` header with yes or no",
     re.search(r"^control:\s*(yes|no)\s*$", snap, re.M) is not None, snap[:600])
c.ok("snapshot declares schema: 0.2", re.search(r"^schema:\s*0\.2\s*$", snap, re.M) is not None, snap[:600])
c.ok("snapshot records the document sha1 as reviewed",
     re.search(r"^sha1:\s*%s\s*$" % doc_sha1, snap, re.M) is not None,
     re.search(r"^sha1:.*$", snap, re.M).group(0) if re.search(r"^sha1:.*$", snap, re.M) else snap[:200])
c.ok("snapshot names the document under review",
     re.search(r"^document:\s*.*brief-q3-flawed\.md\s*$", snap, re.M) is not None, snap[:300])

rows_body = E.section(snap, ["Round-1 objections"])
rows = [ln for ln in rows_body.splitlines()
        if ln.strip().startswith("|") and not re.match(r"^\s*\|[\s\-:|]+\|\s*$", ln)]
header = next((ln for ln in rows if re.search(r"\|\s*Persona\s*\|", ln, re.I)), "")
head_cells = [x.strip().lower() for x in header.strip().strip("|").split("|")]
data_rows = [ln for ln in rows if ln is not header]
c.ok("snapshot has a round-1 objections table with a Persona column", bool(header), rows[:2])
c.ok("snapshot round-1 table has at least three rows", len(data_rows) >= 3, len(data_rows))

tags = [[x.strip() for x in ln.strip().strip("|").split("|")] for ln in data_rows]
round_col = next((i for i, h in enumerate(head_cells) if "round" in h), None)
c.ok("the table declares a round-tag column", round_col is not None, head_cells)
c.ok("every objection row carries the round tag r1 in that column",
     round_col is not None and data_rows
     and all(len(cells) > round_col and cells[round_col].lower() in ("r1", "round 1", "1")
             for cells in tags),
     [cells[round_col] if round_col is not None and len(cells) > round_col else cells for cells in tags],)
c.ok("no round-2 or later rows leaked into the snapshot",
     not re.search(r"\|\s*r[2-9]\s*\|", rows_body, re.I), rows_body[:400])

persona_col = next((i for i, h in enumerate(head_cells) if "persona" in h), 0)
slugs = set(cells[persona_col] for cells in tags if len(cells) > persona_col)
c.ok("every row names a rostered persona", slugs and slugs <= ROSTER, sorted(slugs))
c.ok("all three rostered personas appear in the round-1 table", slugs == ROSTER, sorted(slugs))

c.ok("snapshot has no meeting in the past (it is still gradeable)",
     re.search(r"^meeting:\s*(2099-01-15|unknown)\s*$", snap, re.M) is not None, snap[:400])

flows = [r.get("flow") for r in E.usage_rows(store)]
c.ok("usage log records a review flow", "review" in flows, flows[-5:])

tr = E.read_transcript(transcript_path)
c.ok("transcript carries the announce line for the review flow",
     re.search(r"beforehand\s*·\s*review", tr) is not None, tr[:300])

c.finish()
