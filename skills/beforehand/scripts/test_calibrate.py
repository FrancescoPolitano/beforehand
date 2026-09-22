#!/usr/bin/env python3
"""Tests for calibrate.py: the calibration accounting as a script (SPEC-0.2 FR-5.4).

The fixture under test_fixtures/calibrate/ is one cycle built to exercise every cell of the
accounting at once: hit exact, hit substantive, hit loose, related-not-matched, miss, miss
(declared blind spot), not-raised (mitigated), not-raised (unmitigated), overruled before the
meeting with the anchor removed, overruled retroactively, green lights YES/yes, YES/no and
`not observed`, a consult prediction, a rehearsal prediction, a role-generic row, and a
`control: yes` header. Variants under variants/ carry the refusals and the compatibility cases.

Today's date is injected through `calibrate._today` everywhere it matters: no test here may
depend on the real calendar (Global Constraints).
"""
import contextlib
import datetime as dt
import hashlib
import inspect
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True  # G5: a suite run on its own leaves no __pycache__

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import calibrate  # noqa: E402

FIX = HERE / "test_fixtures/calibrate"
STORE = FIX / "store"
VAR = FIX / "variants"
EXPECTED_ENTRY = (FIX / "expected/log-entry.md").read_text(encoding="utf-8")
FAKE_TODAY = dt.date(2026, 9, 21)

checks = []


def check(name, ok, got=None):
    checks.append((name, bool(ok), got))


def fresh_store():
    """A writable copy of the fixture store; the caller owns the temp directory."""
    tmp = Path(tempfile.mkdtemp()) / "store"
    shutil.copytree(STORE, tmp)
    return tmp


def call(*args, today=FAKE_TODAY):
    """calibrate.main in-process, with the date hook pinned. -> (rc, stdout, stderr)"""
    out, err = io.StringIO(), io.StringIO()
    saved = calibrate._today
    calibrate._today = lambda: today
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = calibrate.main([str(a) for a in args])
    finally:
        calibrate._today = saved
    return rc, out.getvalue(), err.getvalue()


def base_args(store, doc="brief-q4"):
    return ["--store", store, "--context", "trial", "--doc", doc]


# --------------------------------------------------------------- 1. dry run writes nothing
tmp = fresh_store()
before = sorted(p.name for p in (tmp / "trial/calibration").iterdir())
rc, out, err = call(*base_args(tmp))
check("dry run exits 0", rc == 0, (rc, err))
check("dry run writes nothing: no log.md, snapshot still pending",
      sorted(p.name for p in (tmp / "trial/calibration").iterdir()) == before, before)
check("dry run leaves the personas alone",
      "0 cycles: no calibration data yet." in (tmp / "trial/personas/budget-lin.md").read_text(),
      (tmp / "trial/personas/budget-lin.md").read_text()[-200:])
check("dry run says nothing was written", "nothing written" in out, out[-400:])

# --------------------------------------------------------------- 2. the human report
check("report names the flow and the store", out.splitlines()[0].startswith("beforehand · calibrate ·"),
      out.splitlines()[:1])
for frag in ["## Per-persona accounting", "## Rates", "## Green lights", "## Predictions ledger",
             "## Real objections", "## Limits"]:
    check("report has section %s" % frag, frag in out, out[:200])
check("report carries the per-persona row for budget-lin",
      "| budget-lin | trial | 2/0 | 1 | 0 | 0/1 | 0 | YES/yes |" in out, out)
check("report carries the per-persona row for platform-noor",
      "| platform-noor | trial | 0/1 | 0 | 0 | 1/0 | 0 | YES/no |" in out, out)
check("report carries the per-persona row for ops-sam",
      "| ops-sam | trial | 0/0 | 0 | 1 | 0/1 | 1 | YES/not observed |" in out, out)
check("precision reported as counts with the headline strength",
      "precision: 2/6" in out and "loose-inclusive: 3/6" in out, out)
check("coverage reported next to it, never alone, headline with loose-inclusive alongside",
      "coverage: 2/6 (real objections a round-1 row matched over every real objection graded, "
      "exact+substantive) · loose-inclusive: 3/6 (upper bound)" in out, out)
check("role-generic-restricted rate reported from a control snapshot, not estimated",
      "role-generic: no restricted: 1/5" in out and "estimated" not in out, out)
check("below the floor: counts and the interpretation warning, never a percentage",
      "n too small to interpret" in out and "%" not in out, out)
check("green-light 2x2 counted, not pooled",
      "predicted YES / observed yes: 1" in out and "predicted YES / observed no: 1" in out, out)
check("green lights not observed / not applicable counted apart from the 2x2",
      "not observed: 1" in out and "not applicable: 1" in out, out)
check("an INSUFFICIENT_BASIS green light is counted, not dropped",
      "not gradeable: 1" in out, out)
check("consult and rehearsal predictions graded in their own block with their own rate",
      "by source flow: consult 1/2" in out and "· rehearsal 0/1" in out, out)
check("the role-generic ledger item is reported as a base-rate line",
      "base-rate items (role-generic: yes): 1" in out, out)
check("the second claim on an already-matched real objection reads related, not matched",
      "related, not matched" in out, out)
check("the declared blind spot is tagged and points at ## Wanted",
      "miss (declared blind spot)" in out and "## Wanted" in out, out)
check("the late arrival is noted, not graded",
      "R7" in out and "after the grading cut-off" in out, out)
check("the absent persona is excluded from the denominators by name",
      "legal-toft" in out and "rostered but absent" in out, out)
check("retroactive overrule moves nothing and says so",
      "retroactive" in out and "budget-lin#3" in out, out)
check("rounds after the first are reported as panel-driven edits, never pooled",
      "panel-driven edits: 2" in out, out)
check("the limits paragraph is printed on every run",
      "longitudinal case study" in out and "not a controlled study" in out, out)

# --------------------------------------------------------------- 3. --json mirrors the tables
rc, out_j, err = call(*base_args(tmp), "--json")
check("--json exits 0", rc == 0, (rc, err))
try:
    data = json.loads(out_j)
except json.JSONDecodeError:
    data = None
    check("--json parses", False, out_j[:300])
if data:
    check("--json parses", True)
    per = {p["persona"]: p for p in data["personas"]}
    check("--json per-persona hits mirror the table",
          per["budget-lin"]["hits_headline"] == 2 and per["budget-lin"]["hits_loose"] == 0,
          per.get("budget-lin"))
    check("--json carries gradeable, misses, blind spots",
          per["ops-sam"]["gradeable"] == 1 and per["ops-sam"]["blind_spots"] == 1
          and per["budget-lin"]["misses"] == 1, per)
    check("--json carries the two rates as counts, not strings",
          data["rates"]["precision"] == [2, 6] and data["rates"]["coverage"] == [2, 6]
          and data["rates"]["coverage_loose_inclusive"] == [3, 6], data.get("rates"))
    check("--json carries the role-generic-restricted rate and its control provenance",
          data["rates"]["role_generic_restricted"] == [1, 5]
          and data["rates"]["role_generic_source"] == "control", data.get("rates"))
    check("--json carries the green-light 2x2",
          data["green_lights"]["YES/yes"] == 1 and data["green_lights"]["YES/no"] == 1
          and data["green_lights"]["not observed"] == 1, data.get("green_lights"))
    check("--json carries the ledger block", data["ledger"]["hits"] == 1
          and data["ledger"]["gradeable"] == 3, data.get("ledger"))
    check("--json says nothing was applied", data["applied"] is False, data.get("applied"))

# --------------------------------------------------------------- 4. --apply
tmp2 = fresh_store()
rc, out_a, err = call(*base_args(tmp2), "--apply")
check("--apply exits 0", rc == 0, (rc, err))
log = tmp2 / "trial/calibration/log.md"
check("--apply created the calibration log", log.is_file(), log)
if log.is_file():
    text = log.read_text(encoding="utf-8")
    check("--apply appended the pinned log entry byte-for-byte",
          text.endswith(EXPECTED_ENTRY), repr(text[-len(EXPECTED_ENTRY) - 40:]))
check("--apply renamed the snapshot to done-<today>-<doc>.md",
      (tmp2 / "trial/calibration/done-2026-09-21-brief-q4.md").is_file()
      and not (tmp2 / "trial/calibration/pending-brief-q4.md").exists(),
      sorted(p.name for p in (tmp2 / "trial/calibration").iterdir()))
check("--apply never writes a persona file",
      "0 cycles: no calibration data yet." in (tmp2 / "trial/personas/budget-lin.md").read_text(),
      (tmp2 / "trial/personas/budget-lin.md").read_text()[-200:])
check("--apply prints the Reliability update as a unified diff, proposed only",
      "--- a/personas/budget-lin.md" in out_a and "+++ b/personas/budget-lin.md" in out_a, out_a)
check("the proposed Reliability line for budget-lin is counts, below the floor",
      "+- 1 cycle: 2/3 — n too small to interpret" in out_a, out_a)
check("the proposed Reliability line removes the old one-liner",
      "-- 0 cycles: no calibration data yet." in out_a, out_a)
check("a diff is proposed for every graded persona, and for no other",
      out_a.count("--- a/personas/") == 3 and "legal-toft" not in out_a.split("## Reliability")[-1],
      out_a)
# a second --apply is refused: the snapshot is gone, there is nothing pending to grade
rc, _, err2 = call(*base_args(tmp2), "--apply")
check("re-applying an already graded snapshot exits 1 (usage), not 0", rc == 1, (rc, err2))

# --------------------------------------------------------------- 5. refusals (exit 2)
tmp3 = fresh_store()
shutil.copy(VAR / "pending-frozen-after.md", tmp3 / "trial/calibration/pending-brief-q4.md")
rc, out_f, err = call(*base_args(tmp3))
check("a snapshot frozen on the meeting day is not gradeable: exit 2", rc == 2, (rc, out_f, err))
check("and the reason names the rule",
      "frozen on or after the meeting" in (out_f + err), (out_f, err))

tmp4 = fresh_store()
shutil.copy(VAR / "pending-no-meeting.md", tmp4 / "trial/calibration/pending-brief-q4.md")
rc, out_n, err = call(*base_args(tmp4))
check("no meeting date: exit 2 with the reason",
      rc == 2 and "no meeting date" in (out_n + err), (rc, out_n, err))

tmp5 = fresh_store()
shutil.copy(VAR / "pairing-two-matches.md", tmp5 / "trial/calibration/pairing-brief-q4.md")
rc, out_p, err = call(*base_args(tmp5))
check("one real objection claimed twice in the round-1 ledger: exit 2 pairing not one-to-one",
      rc == 2 and "pairing not one-to-one" in (out_p + err), (rc, out_p, err))
check("and the refusal names the real objection claimed twice", "R1" in (out_p + err), (out_p, err))

# one-to-one is per ledger (SPEC-0.1 FR-2.5): the two blocks are graded apart
tmp5b = fresh_store()
shutil.copy(VAR / "pairing-cross-block.md", tmp5b / "trial/calibration/pairing-brief-q4.md")
rc, out_x, err = call(*base_args(tmp5b))
check("a real objection may satisfy one round-1 row and one P<k> at once: exit 0",
      rc == 0, (rc, out_x[-400:], err))
check("the cross-ledger match is reported on both sides, not silently merged",
      "matched exact by budget-lin#1 (round 1); also loose by P3 (ledger)" in out_x, out_x)
check("coverage still counts round-1 matches only, so the cross match does not inflate it",
      "coverage: 2/6" in out_x and "loose-inclusive: 3/6 (upper bound)" in out_x, out_x)
# 0.3.1 (C8): P3's match is loose, so it is an upper-bound hit, shown beside the headline rate
check("but the ledger's own rate does pick it up, as a loose-inclusive hit",
      "ledger rate: 1/3 (exact+substantive) · loose-inclusive: 2/3 (upper bound)" in out_x,
      out_x)

tmp5c = fresh_store()
shutil.copy(VAR / "pairing-two-preds.md", tmp5c / "trial/calibration/pairing-brief-q4.md")
rc, out_pp, err = call(*base_args(tmp5c))
check("two ledger items claiming one real objection: exit 2, same rule inside that ledger",
      rc == 2 and "pairing not one-to-one" in (out_pp + err) and "R5" in (out_pp + err),
      (rc, out_pp, err))

# the FR-2.4 date gate must never fail open
tmp5d = fresh_store()
shutil.copy(VAR / "pairing-bad-overruled-date.md", tmp5d / "trial/calibration/pairing-brief-q4.md")
rc, out_d, err = call(*base_args(tmp5d))
check("an overruled date that is not YYYY-MM-DD stops the run instead of dropping the row",
      rc == 2 and "overruled date must be YYYY-MM-DD" in (out_d + err), (rc, out_d, err))
check("and the refusal quotes the line it could not read", "05/09/2026" in (out_d + err), err)

for variant, why in [("pairing-malformed.md", "an unknown strength"),
                     ("pairing-missing-field.md", "a line missing a field")]:
    tmpm = fresh_store()
    shutil.copy(VAR / variant, tmpm / "trial/calibration/pairing-brief-q4.md")
    rc, out_m, err = call(*base_args(tmpm))
    check("%s is refused, never silently skipped" % why,
          rc == 2 and "pairing line not understood" in (out_m + err), (rc, out_m, err))

tmp6 = fresh_store()
shutil.copy(VAR / "pairing-unknown-key.md", tmp6 / "trial/calibration/pairing-brief-q4.md")
rc, out_u, err = call(*base_args(tmp6))
check("a pairing key naming no row: exit 2 with the key",
      rc == 2 and "unknown key" in (out_u + err) and "platform-noor#9" in (out_u + err),
      (rc, out_u, err))

# a refusal writes nothing, even with --apply
rc, _, _ = call(*base_args(tmp5), "--apply")
check("a refused run writes nothing even with --apply",
      rc == 2 and not (tmp5 / "trial/calibration/log.md").exists()
      and (tmp5 / "trial/calibration/pending-brief-q4.md").is_file(), rc)

# --------------------------------------------------------------- 6. the document changed
tmp7 = fresh_store()
shutil.copy(VAR / "brief-q4-changed.md", tmp7 / "trial/docs/brief-q4.md")
rc, out_c, err = call(*base_args(tmp7))
check("a document changed after the review still grades: exit 0", rc == 0, (rc, err))
check("and the run is tagged with the warning",
      "document changed after review" in out_c, out_c[:600])
check("the grades themselves are unchanged by the warning",
      "| budget-lin | trial | 2/0 | 1 | 0 | 0/1 | 0 | YES/yes |" in out_c, out_c)
rc, out_cj, _ = call(*base_args(tmp7), "--json")
check("--json carries the document-changed tag",
      json.loads(out_cj)["document_changed"] is True, out_cj[:300])

# --------------------------------------------------------------- 7. control: no -> estimated
tmp8 = fresh_store()
shutil.copy(VAR / "pending-control-no.md", tmp8 / "trial/calibration/pending-brief-q4.md")
rc, out_e, err = call(*base_args(tmp8))
check("control: no exits 0", rc == 0, (rc, err))
check("without a control round the restricted rate is labelled estimated",
      "role-generic: no restricted: 1/5 (estimated)" in out_e, out_e)
rc, out_ej, _ = call(*base_args(tmp8), "--json")
check("--json labels the restricted rate estimated too",
      json.loads(out_ej)["rates"]["role_generic_source"] == "estimated", out_ej[:400])

# --------------------------------------------------------------- 8. a 0.1-shaped snapshot
tmp9 = fresh_store()
shutil.copy(VAR / "pending-0.1.md", tmp9 / "trial/calibration/pending-brief-q4.md")
rc, out_o, err = call(*base_args(tmp9))
check("a 0.1-shaped snapshot still grades: exit 0", rc == 0, (rc, err))
rc, out_oj, _ = call(*base_args(tmp9), "--json")
data_o = json.loads(out_oj)
check("a snapshot without a control: header reads control no",
      data_o["control"] == "no" and data_o["rates"]["role_generic_source"] == "estimated",
      data_o.get("control"))
check("a snapshot without an Isolation column reads isolation unknown",
      all(r["isolation"] == "unknown" for r in data_o["rows"]),
      [r["isolation"] for r in data_o["rows"]][:3])
check("a snapshot without a Context column falls back to the context it lives in",
      all(r["context"] == "trial" for r in data_o["rows"]), [r["context"] for r in data_o["rows"]][:3])

# --------------------------------------------------------------- 9. legacy (proposed) marker
tmp10 = fresh_store()
snap = tmp10 / "trial/calibration/pending-brief-q4.md"
snap.write_text(snap.read_text(encoding="utf-8")
                .replace("| 4 | r1 | steering | no | no |", "| 4 | r1 | steering | no (proposed) | no |", 1),
                encoding="utf-8")
rc, out_pr, err = call(*base_args(tmp10))
check("a legacy `no (proposed)` cell is tolerated, not refused", rc == 0, (rc, err))
check("and the tolerated marker is warned about, once",
      "(proposed)" in out_pr and "warning" in out_pr.lower(), out_pr[:800])
check("the stripped value still counts as role-generic: no",
      "role-generic: no restricted: 1/5" in out_pr, out_pr)

# --------------------------------------------------------------- 10. usage errors (exit 1)
rc, _, err = call("--store", tmp, "--context", "trial", "--doc", "no-such-doc")
check("an unknown document exits 1 (usage), not 2", rc == 1, (rc, err))
rc, _, err = call("--store", tmp, "--context", "no-such-context", "--doc", "brief-q4")
check("an unknown context exits 1", rc == 1, (rc, err))
tmp11 = fresh_store()
(tmp11 / "trial/calibration/pairing-brief-q4.md").unlink()
rc, _, err = call(*base_args(tmp11))
check("a missing pairing file exits 1 and says where it was looked for",
      rc == 1 and "pairing-brief-q4.md" in err, (rc, err))
tmp12 = fresh_store()
(tmp12 / "trial/calibration/annotation-brief-q4.md").unlink()
rc, _, err = call(*base_args(tmp12))
check("a missing annotation file exits 1 and says where it was looked for",
      rc == 1 and "annotation-brief-q4.md" in err, (rc, err))

# --------------------------------------------------------------- 11. --help documents both keys
r = subprocess.run([sys.executable, str(HERE / "beforehand.py"), "calibrate", "--help"],
                   capture_output=True, text=True, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
check("beforehand.py calibrate --help exits 0", r.returncode == 0, (r.returncode, r.stderr))
check("--help carries the accounting rules (they live in the docstring, not in calibrate.md)",
      "One-to-one" in r.stdout and "Minimum n" in r.stdout, r.stdout[:400])
check("--help documents both pairing key forms",
      "<slug>#<n>" in r.stdout and "P<k>" in r.stdout, r.stdout[:400])
check("--help documents the annotation fields it reads",
      "Meeting held:" in r.stdout and "Personas rostered but absent:" in r.stdout
      and "Grading cut-off:" in r.stdout and "greenlight:" in r.stdout, r.stdout[:400])

# --------------------------------------------------------------- 12. cycles come from rows
# The Notes line names absent personas and excluded keys; a slug mentioned in prose must not
# collect a cycle it was never graded on.
check("count_cycles counts a persona with a scoring row of its own",
      calibrate.count_cycles(EXPECTED_ENTRY, "budget-lin") == 1,
      calibrate.count_cycles(EXPECTED_ENTRY, "budget-lin"))
check("count_cycles ignores a slug that only appears in the Notes prose",
      calibrate.count_cycles(EXPECTED_ENTRY, "legal-toft") == 0
      and "legal-toft" in EXPECTED_ENTRY,
      calibrate.count_cycles(EXPECTED_ENTRY, "legal-toft"))
check("count_cycles ignores a slug that only appears as an excluded key in the Notes",
      calibrate.count_cycles(EXPECTED_ENTRY, "ops-sam") == 1
      and "ops-sam#2" in EXPECTED_ENTRY, calibrate.count_cycles(EXPECTED_ENTRY, "ops-sam"))

tmp13 = fresh_store()
(tmp13 / "trial/calibration/log.md").write_text("# Calibration log — trial\n\n" + EXPECTED_ENTRY,
                                                encoding="utf-8")
rc, out_c2, err = call(*base_args(tmp13))
check("a second cycle on the same persona counts up from the log", rc == 0, (rc, err))
check("budget-lin reads 2 cycles after one logged entry", "| 2 cycles: 2/3 |" in out_c2, out_c2)

# --------------------------------------------------------------- 13. the extracted rules
MEETING = dt.date(2026, 9, 10)
check("overrule_status: decided before the meeting with the anchor gone -> out of the denominator",
      calibrate.overrule_status("2026-09-05", MEETING, "yes (clause removed)") == "removed")
check("overrule_status: decided before the meeting but the text stayed -> still gradeable",
      calibrate.overrule_status("2026-09-05", MEETING, "no") == "still gradeable")
check("overrule_status: `partially` is not `removed` — the anchor is still there",
      calibrate.overrule_status("2026-09-05", MEETING, "partially") == "still gradeable")
check("overrule_status: decided on the meeting day is retroactive, not before it",
      calibrate.overrule_status("2026-09-10", MEETING, "yes") == "retroactive")
check("overrule_status: a date it cannot read never reaches `removed`",
      calibrate.overrule_status("nonsense", MEETING, "yes") == "still gradeable")
check("mitigation_split: yes and partially are both mitigated",
      calibrate.mitigation_split("yes (window extended)") == "not-raised (mitigated)"
      and calibrate.mitigation_split("partially") == "not-raised (mitigated)")
check("mitigation_split: no is unmitigated — the only cell that speaks to accuracy",
      calibrate.mitigation_split("no") == "not-raised (unmitigated)"
      and calibrate.mitigation_split("") == "not-raised (unmitigated)")
GR = {"persona": "a", "context": "trial", "round": "r1", "event": "steering"}
check("gradeable_reason: a round-1 row on its own context's event is gradeable",
      calibrate.gradeable_reason(GR, set(), {"steering": "trial"}) is None)
check("gradeable_reason: an absent persona leaves the denominator",
      calibrate.gradeable_reason(GR, {"a"}, {}) == "excluded: rostered but absent")
check("gradeable_reason: round 2 is context, never a rate",
      calibrate.gradeable_reason(dict(GR, round="r2"), set(), {})
      == "context: round after the first")
check("gradeable_reason: an event another context attended is not this persona's",
      (calibrate.gradeable_reason(GR, set(), {"steering": "approvals"}) or "")
      .startswith("context: event steering belongs to approvals"))
check("greenlight_cell: the four 2x2 cells",
      [calibrate.greenlight_cell(p, o) for p, o in
       [("YES", "yes"), ("YES", "no"), ("NO", "yes"), ("NO", "no")]]
      == ["YES/yes", "YES/no", "NO/yes", "NO/no"])
check("greenlight_cell: not observed / not applicable sit outside the table",
      calibrate.greenlight_cell("YES", "not observed") == "not observed"
      and calibrate.greenlight_cell("NO", "not applicable") == "not applicable")
check("greenlight_cell: INSUFFICIENT_BASIS and `descriptive only` are counted, not dropped",
      calibrate.greenlight_cell("INSUFFICIENT_BASIS", "yes") == "not gradeable"
      and calibrate.greenlight_cell("DESCRIPTIVE ONLY", "no") == "not gradeable")
check("persona_for: an unambiguous who resolves, and reports one candidate",
      calibrate.persona_for("Lin", ["budget-lin", "ops-sam"]) == ("budget-lin", ["budget-lin"]))
check("persona_for: an ambiguous who reports every candidate, first sorted chosen",
      calibrate.persona_for("lin", ["budget-lin", "planning-lin"])
      == ("budget-lin", ["budget-lin", "planning-lin"]))

# --------------------------------------------------------------- 14. keys are panel's keys
rc, out_k, _ = call(*base_args(tmp), "--json")
rows_k = json.loads(out_k)["rows"]
check("<slug>#<n> numbers round-1 rows only, exactly as `panel` numbers them",
      [r["key"] for r in rows_k if r["persona"] == "platform-noor"]
      == ["platform-noor#1", "platform-noor#2", "platform-noor#- (r2, not round 1)"],
      [r["key"] for r in rows_k if r["persona"] == "platform-noor"])
check("a later-round row keeps a label, so a pairing naming it is refused as an unknown key",
      all("#-" in r["key"] or re.fullmatch(r"[\w-]+#\d+", r["key"]) for r in rows_k),
      [r["key"] for r in rows_k])

# --------------------------------------------------------------- 15. an unresolvable document
tmp14 = fresh_store()
shutil.copy(VAR / "pending-no-document.md", tmp14 / "trial/calibration/pending-brief-q4.md")
rc, out_nd, err = call(*base_args(tmp14))
check("a document that does not resolve still grades: exit 0", rc == 0, (rc, err))
check("but the report says the sha1 could not be verified",
      "document not found: cannot verify sha1" in out_nd, out_nd[:700])

# --------------------------------------------------------------- 16. the reconstructed ledger
# FR-1.1: a snapshot frozen in prose before the 0.2 shape existed is graded through a ledger
# the model transcribes and the user confirms. The prose file stays the frozen record: it is
# what is hashed into the log heading and what `--apply` renames.
PROSE = VAR / "pending-prose.md"
LEDGER = (VAR / "ledger-brief-q4.md").read_text(encoding="utf-8")
PROSE_SHA1 = hashlib.sha1(PROSE.read_bytes()).hexdigest()
check("the ledger fixture pins the sha1 of the prose fixture beside it "
      "(regenerate it if that file ever changes)",
      "snapshot sha1: %s" % PROSE_SHA1 in LEDGER,
      [ln for ln in LEDGER.splitlines() if ln.startswith("snapshot sha1:")])


def prose_store(ledger_text=LEDGER, ledger_name="ledger-brief-q4.md"):
    """A store whose pending snapshot is the prose one, with a ledger beside it."""
    st = fresh_store()
    shutil.copy(PROSE, st / "trial/calibration/pending-brief-q4.md")
    if ledger_text is not None:
        (st / "trial/calibration" / ledger_name).write_text(ledger_text, encoding="utf-8")
    return st


tmp15 = prose_store()
rc, out_pr, err = call(*base_args(tmp15))
check("without --ledger a prose snapshot is refused, and the reason is the missing date",
      rc == 2 and "no meeting date" in (out_pr + err), (rc, out_pr, err))

rc, out_lg, err = call(*base_args(tmp15), "--ledger")
check("--ledger with no argument finds calibration/ledger-<doc>.md and grades it",
      rc == 0, (rc, out_lg[-400:], err))
check("every ledger run says the rows were transcribed after the meeting",
      "warning: ledger reconstructed on 2026-09-21 from a pre-0.2 snapshot" in out_lg,
      out_lg[:400])
check("and names the file that is still the frozen record, with its sha1",
      "the frozen text is calibration/pending-brief-q4.md (sha1 %s)" % PROSE_SHA1[:12]
      in out_lg, out_lg[:400])
check("the limits say this cycle's ledger came after the meeting",
      "; this cycle's ledger was reconstructed after the meeting." in out_lg,
      out_lg[-600:])
check("the accounting itself is the ordinary one: same rates as the 0.2 snapshot",
      "coverage: 2/6" in out_lg and "precision: 2/6" in out_lg, out_lg)

rc, out_lj, err = call(*base_args(tmp15), "--ledger", "--json")
dj = json.loads(out_lj)
check("--json carries the reconstruction date and the ledger file",
      dj["ledger_reconstructed"] == "2026-09-21"
      and dj["ledger_file"] == "ledger-brief-q4.md", (dj.get("ledger_reconstructed"),
                                                      dj.get("ledger_file")))
check("--json hashes the prose snapshot, not the ledger",
      dj["snapshot_sha1"] == PROSE_SHA1, dj.get("snapshot_sha1"))
check("a run without --ledger carries both keys as null, never missing",
      json.loads(call(*base_args(fresh_store()), "--json")[1])["ledger_reconstructed"] is None,
      "key missing")

# an explicit path, anywhere
tmp16 = prose_store(ledger_name="elsewhere.md")
rc, out_x, err = call(*base_args(tmp16), "--ledger",
                      tmp16 / "trial/calibration/elsewhere.md")
check("--ledger FILE takes a path like --annotation and --pairing does", rc == 0,
      (rc, err))
rc, _, err = call(*base_args(tmp16), "--ledger")
check("and a missing default ledger is usage, not a grading verdict",
      rc == 1 and "ledger not found: ledger-brief-q4.md" in err, (rc, err))

# the four refusals, each one line of the ledger away
for name, bad, needle in [
        ("no reconstructed: date",
         LEDGER.replace("reconstructed: 2026-09-21\n", ""),
         "ledger has no reconstructed: date (YYYY-MM-DD) — a ledger written after the "
         "meeting must say when"),
        ("no snapshot sha1:",
         LEDGER.replace("snapshot sha1: %s\n" % PROSE_SHA1, ""),
         "ledger has no snapshot sha1:"),
        ("no frozen: date",
         LEDGER.replace("frozen: 2026-09-01 09:00\n", ""),
         "ledger has no frozen: date — transcribe it from the snapshot, the "
         "pre-registration gate cannot run without it"),
]:
    tmpb = prose_store(bad)
    rc, out_b, err_b = call(*base_args(tmpb), "--ledger")
    check("a ledger with %s is not gradeable: exit 2" % name, rc == 2, (rc, out_b, err_b))
    check("and the refusal says exactly what is missing (%s)" % name,
          needle in (out_b + err_b), (out_b, err_b))

# the sha1 pin is what stops a ledger from outliving the text it was read from
tmpb = prose_store(LEDGER.replace(PROSE_SHA1, "a" * 40))
rc, out_b, err_b = call(*base_args(tmpb), "--ledger")
check("a ledger whose snapshot sha1 does not match is not gradeable: exit 2", rc == 2,
      (rc, out_b, err_b))
check("and the refusal names both 12-character prefixes and what it means",
      ("ledger snapshot sha1 %s does not match calibration/pending-brief-q4.md (%s): the "
       "frozen text changed after the ledger was written" % ("a" * 12, PROSE_SHA1[:12]))
      in (out_b + err_b), (out_b, err_b))

# --apply: the cycle enters the log, and says how it got there
tmp17 = prose_store()
rc, out_ap, err = call(*base_args(tmp17), "--ledger", "--apply")
check("--ledger --apply exits 0", rc == 0, (rc, err))
entry = (tmp17 / "trial/calibration/log.md").read_text(encoding="utf-8")
check("the log heading carries the prose snapshot's sha1, not the ledger's",
      "## 2026-09-21 — brief-q4 (snapshot %s)" % PROSE_SHA1[:12] in entry, entry[:200])
check("the Notes close on the reconstruction, so the log shows how the cycle got in",
      "; ledger reconstructed on 2026-09-21." in entry, entry[-300:])
check("the log entry is otherwise the ordinary one",
      entry.count("| budget-lin | trial | 2/0 | 1 | 0 | 0/1 | 0 | YES/yes | yes | "
                  "1 cycle: 2/3 |") == 1, entry)
check("the prose snapshot is renamed like any other, and the ledger stays",
      (tmp17 / "trial/calibration/done-2026-09-21-brief-q4.md").is_file()
      and (tmp17 / "trial/calibration/ledger-brief-q4.md").is_file()
      and not (tmp17 / "trial/calibration/pending-brief-q4.md").exists(),
      sorted(p.name for p in (tmp17 / "trial/calibration").iterdir()))
check("the cycle counts: count_cycles sees the appended row",
      calibrate.count_cycles(entry, "budget-lin") == 1,
      calibrate.count_cycles(entry, "budget-lin"))

# Every fragment this release adds to Notes is conditional, so an ordinary cycle's entry is
# byte-identical to the one pinned before it (Cross-item notes, "Shared mechanisms").
tmp18 = fresh_store()
call(*base_args(tmp18), "--apply")
plain = (tmp18 / "trial/calibration/log.md").read_text(encoding="utf-8")
check("an ordinary cycle's log entry is unchanged, byte for byte",
      plain.endswith(EXPECTED_ENTRY), repr(plain[-len(EXPECTED_ENTRY) - 40:]))
check("and the reconstruction note is the only difference the ledger makes to the Notes",
      entry.split("Notes: ")[1].replace("; ledger reconstructed on 2026-09-21.", ".")
      == plain.split("Notes: ")[1],
      (entry.split("Notes: ")[1][-220:], plain.split("Notes: ")[1][-220:]))

# the snapshot's own meeting date wins over the ledger's (A2 meets A1)
tmp19 = prose_store()
import pending as _pending  # noqa: E402

snap19 = tmp19 / "trial/calibration/pending-brief-q4.md"
moved, _old = _pending.set_meeting(snap19.read_text(encoding="utf-8"), "2026-09-12",
                                   FAKE_TODAY)
snap19.write_text(moved, encoding="utf-8")
rc, out_m, err = call(*base_args(tmp19), "--ledger")
check("a date moved on the snapshot shadows the ledger's, and the sha1 pin catches the edit",
      rc == 2 and "does not match" in (out_m + err), (rc, out_m, err))
led19 = tmp19 / "trial/calibration/ledger-brief-q4.md"
led19.write_text(LEDGER.replace(PROSE_SHA1,
                                hashlib.sha1(snap19.read_bytes()).hexdigest()),
                 encoding="utf-8")
rc, out_m, err = call(*base_args(tmp19), "--ledger")
check("with the ledger re-pinned, the snapshot's date is the one graded",
      rc == 0 and "meeting 2026-09-12 (held: yes)" in out_m, (rc, out_m[:300], err))

# ----------------------------------------------- 17. what the ledger may and may not soften
# A ledger is transcription: it may fill in a date the prose never stated in a parseable
# shape, and it may never move a date the frozen snapshot does state.


def pinned_store(snap_text):
    """A store whose pending snapshot is `snap_text`, with the ledger re-pinned to it."""
    st = fresh_store()
    snp = st / "trial/calibration/pending-brief-q4.md"
    snp.write_text(snap_text, encoding="utf-8")
    (st / "trial/calibration/ledger-brief-q4.md").write_text(
        LEDGER.replace(PROSE_SHA1, hashlib.sha1(snp.read_bytes()).hexdigest()),
        encoding="utf-8")
    return st


SNAP_02 = (STORE / "trial/calibration/pending-brief-q4.md").read_text(encoding="utf-8")
LATE_FROZEN = SNAP_02.replace("frozen: 2026-09-01 09:00", "frozen: 2026-09-20")
GATE = ("snapshot frozen on or after the meeting (frozen 2026-09-20, meeting 2026-09-10): "
        "the predictions are not pre-registered")

tmp20 = pinned_store(LATE_FROZEN)
rc, out_20, err_20 = call(*base_args(tmp20))
check("a snapshot frozen after the meeting is not gradeable: exit 2", rc == 2,
      (rc, out_20, err_20))
check("and the refusal is the pinned pre-registration one", GATE in (out_20 + err_20), err_20)
rc, out_21, err_21 = call(*base_args(tmp20), "--ledger")
check("a ledger stating an earlier frozen: date does not reopen that gate: still exit 2",
      rc == 2, (rc, out_21, err_21))
check("and the message is the same one, from the snapshot's own dates",
      GATE in (out_21 + err_21), err_21)

# the other direction: a prose date that does not parse is what the ledger is for
UNPARSEABLE = PROSE.read_text(encoding="utf-8").replace(
    "Frozen on: the first of September, in the morning",
    "frozen: the first of September, in the morning")
rc, out_22, err_22 = call(*base_args(pinned_store(UNPARSEABLE)), "--ledger")
check("a snapshot whose own frozen: date does not parse still grades on the ledger's",
      rc == 0, (rc, out_22[-300:], err_22))

# the warning says which format it found, because --ledger works on any snapshot
rc, out_23, err_23 = call(*base_args(pinned_store(SNAP_02)), "--ledger")
check("a 0.2 snapshot graded through a ledger grades: exit 0", rc == 0, (rc, err_23))
check("and the warning says so instead of asserting a pre-0.2 snapshot",
      "warning: ledger reconstructed on 2026-09-21 from a 0.2 snapshot" in out_23,
      out_23[:400])

# ----------------------------------------------- 18. a ledger may not be graded as a snapshot
# Copying the ledger over pending-<doc>.md would launder it: no sha1 pin to the text it was
# transcribed from, and no reconstruction note in the log.
tmp24 = fresh_store()
(tmp24 / "trial/calibration/pending-brief-q4.md").write_text(LEDGER, encoding="utf-8")
rc, out_24, err_24 = call(*base_args(tmp24), "--apply")
check("a ledger copied over the snapshot is not gradeable: exit 2", rc == 2,
      (rc, out_24, err_24))
check("and the refusal names the flag that grades it honestly",
      ("pending-brief-q4.md carries a reconstructed: line — that is a ledger, not a frozen "
       "snapshot: keep the snapshot it was transcribed from and grade it with --ledger")
      in (out_24 + err_24), err_24)
check("so nothing reached the log", not (tmp24 / "trial/calibration/log.md").exists(),
      sorted(p.name for p in (tmp24 / "trial/calibration").iterdir()))
check("while an ordinary snapshot, which carries no reconstructed: line, is untouched",
      call(*base_args(fresh_store()))[0] == 0)
check("and the same ledger passed as a ledger still grades",
      call(*base_args(prose_store()), "--ledger")[0] == 0)

# ------------------------------------- 19. the ledger template is the shape grade() reads
# Derived from the code, never from a copy of the list: with --ledger every header field and
# every section comes from the ledger, so a field the reference leaves out is silently zero.
LEDGER_READERS = (calibrate.grade, calibrate.parse_round1, calibrate.parse_green_lights,
                  calibrate.parse_predictions, calibrate.parse_events,
                  calibrate.parse_criteria)
LEDGER_SRC = "".join(inspect.getsource(f) for f in LEDGER_READERS)
ledger_fields = set(re.findall(r'field\(text,\s*"([^"]+)"\)', LEDGER_SRC))
ledger_fields |= set(re.findall(r'snap_fields\["([^"]+)"\]', LEDGER_SRC))
ledger_fields |= set(re.findall(r'r"\^(\w+):', LEDGER_SRC))     # the `events:` block
ledger_sections = set(re.findall(r'section_body\(text,\s*"([^"]+)"\)', LEDGER_SRC))
check("the derivation found the fields and sections it is meant to check (a rename here "
      "must not quietly empty this test)",
      len(ledger_fields) >= 5 and len(ledger_sections) >= 4,
      (sorted(ledger_fields), sorted(ledger_sections)))

REF = (HERE.parent / "references/calibrate.md").read_text(encoding="utf-8")
TEMPLATE = [b for b in re.findall(r"^```.*?\n(.*?)^```", REF, re.S | re.M)
            if "reconstructed:" in b]
check("references/calibrate.md carries exactly one ledger template block",
      len(TEMPLATE) == 1, len(TEMPLATE))
tmpl = TEMPLATE[0] if TEMPLATE else ""
absent_from_template = [f for f in sorted(ledger_fields)
                        if not re.search(r"(?mi)^%s\s*:" % re.escape(f), tmpl)]
absent_from_template += ["## %s" % s for s in sorted(ledger_sections)
                         if "## %s" % s not in tmpl]
check("and it names every header field and every section grade() reads from the ledger",
      not absent_from_template, absent_from_template)

# --------------------------------------------------------------- 20. misses by class (FR-1.3)
# "Real reactions not predicted" used to mix three things; only one of them indicts the
# persona, and an unknown tag used to become that one silently.


def with_pairing(name):
    st = fresh_store()
    shutil.copy(VAR / name, st / "trial/calibration/pairing-brief-q4.md")
    return st


def with_snapshot(name, pairing=None):
    st = fresh_store()
    shutil.copy(VAR / name, st / "trial/calibration/pending-brief-q4.md")
    if pairing:
        shutil.copy(VAR / pairing, st / "trial/calibration/pairing-brief-q4.md")
    return st


check("the fixed misses-by-class line is printed on an ordinary cycle too",
      "misses by class: new 1 · known (in the persona, not listed) 0 · declared blind spot 1"
      in out, out)

tmp25 = with_pairing("pairing-known.md")
rc, out_kn, err = call(*base_args(tmp25))
check("a known objection the panel did not list still grades: exit 0", rc == 0, (rc, err))
check("it leaves the attributable-miss column, which is the one that indicts the persona",
      "| budget-lin | trial | 2/0 | 0 | 0 | 0/1 | 0 | YES/yes |" in out_kn, out_kn)
check("its outcome says which kind of miss it is",
      "| R6 | Lin | budget-lin | miss (known, in the persona) |" in out_kn, out_kn)
check("the class tally names all three kinds",
      "misses by class: new 0 · known (in the persona, not listed) 1 · declared blind spot 1"
      in out_kn, out_kn)
check("a known miss stays in the running line's denominator: the ground was still the persona's",
      "1 cycle: 2/3" in out_kn, out_kn)
check("and coverage is untouched, because every graded real is still in it",
      "coverage: 2/6" in out_kn, out_kn)
rc, out_knj, _ = call(*base_args(tmp25), "--json")
data_kn = json.loads(out_knj)
check("--json carries misses_known beside misses",
      {p["persona"]: (p["misses"], p["misses_known"]) for p in data_kn["personas"]}["budget-lin"]
      == (0, 1), [(p["persona"], p["misses"], p["misses_known"]) for p in data_kn["personas"]])
check("--json carries the class on the real objection itself",
      {r["id"]: r["miss_class"] for r in data_kn["reals"]}
      == {"R1": None, "R2": None, "R3": None, "R4": "blind spot", "R5": None, "R6": "known",
          "R7": None},
      {r["id"]: r["miss_class"] for r in data_kn["reals"]})

tmp26 = with_pairing("pairing-known.md")
call(*base_args(tmp26), "--apply")
check("--apply names the count in the Notes, so the log carries what the table cannot",
      "misses in the persona but not listed: 1"
      in (tmp26 / "trial/calibration/log.md").read_text(encoding="utf-8"),
      (tmp26 / "trial/calibration/log.md").read_text(encoding="utf-8")[-400:])

rc, out_bt, err_bt = call(*base_args(with_pairing("pairing-bad-tag.md")))
check("an unmatched tag outside the closed set stops the run instead of reading as a miss",
      rc == 2 and "pairing line not understood" in (out_bt + err_bt), (rc, out_bt, err_bt))
check("and the refusal names the set",
      "(an unmatched tag must be blind spot | known | new)" in (out_bt + err_bt), err_bt)

rc, out_nt, err = call(*base_args(with_pairing("pairing-new-tag.md")))
check("an explicit (new) tag grades exactly as an untagged one", rc == 0, (rc, err))
check("and reads as the plain miss it has always read as",
      "| R6 | Lin | budget-lin | miss |" in out_nt
      and "misses by class: new 1 · known (in the persona, not listed) 0 · declared blind "
          "spot 1" in out_nt, out_nt)

# --------------------------------------------------------- 21. source type / grounding (FR-1.4)
check("the default fixture reports the source-type split with unknown spelled out",
      "by source type: unknown 1/3 (loose-inclusive 1/3)" in out, out)
check("and the grounding-section split, the 0.2 deferred item",
      "by grounding section: Recurring objections 1/2 (loose-inclusive 1/2) · Judgment "
      "criteria 0/1 (loose-inclusive 0/1)" in out, out)
if data:
    check("--json carries both splits as counts",
          data["ledger"]["by_source_type"] == {"unknown": [1, 3]}
          and data["ledger"]["by_grounding"] == {"Recurring objections": [1, 2],
                                                 "Judgment criteria": [0, 1]},
          (data["ledger"].get("by_source_type"), data["ledger"].get("by_grounding")))

tmp27 = with_snapshot("pending-source-type.md")
rc, out_st, err = call(*base_args(tmp27))
check("a snapshot carrying source type: on its P-rows grades: exit 0", rc == 0, (rc, err))
check("the split names every channel present, and unknown for the row that carries none",
      "by source type: private-communication 1/1 (loose-inclusive 1/1) · public-statement 0/1 "
      "(loose-inclusive 0/1) · unknown 0/1 (loose-inclusive 0/1)" in out_st, out_st)
check("the source flow split is unchanged by the new column",
      "ledger rate: 1/3 (exact+substantive) · loose-inclusive: 1/3 (upper bound)" in out_st
      and "by source flow: consult 1/2 (loose-inclusive 1/2) · rehearsal 0/1 "
          "(loose-inclusive 0/1)" in out_st, out_st)
tmp28 = with_snapshot("pending-source-type.md")
call(*base_args(tmp28), "--apply")
check("--apply carries the split into the log only when some row has a known channel",
      "ledger by source type: private-communication 1/1 (loose-inclusive 1/1), "
      "public-statement 0/1 (loose-inclusive 0/1), unknown 0/1 (loose-inclusive 0/1)"
      in (tmp28 / "trial/calibration/log.md").read_text(encoding="utf-8"),
      (tmp28 / "trial/calibration/log.md").read_text(encoding="utf-8")[-400:])
check("a ledger where every row is unknown adds no such fragment",
      "ledger by source type" not in EXPECTED_ENTRY, EXPECTED_ENTRY[-200:])

PRED_ROW = "## Predictions to verify\n- P9 | a | will ask | Red lines | %s\n"
check("parse_predictions defaults an absent source type to unknown, never to private",
      calibrate.parse_predictions(PRED_ROW % "source flow: review")[0]["source_type"]
      == "unknown")
check("it reads the field when present, case-insensitively",
      calibrate.parse_predictions(PRED_ROW % "Source Type: Public-Statement")[0]["source_type"]
      == "public-statement")
check("an unknown trailing field is still ignored, in both directions",
      calibrate.parse_predictions(PRED_ROW % "confidence: high | source type: mixed")[0]
      ["source_type"] == "mixed")
TALLY_ROWS = [{"k": "a", "strength": "exact"}, {"k": "a", "strength": None},
              {"k": "", "strength": "loose"}]
check("tally groups by any key and counts headline hits over rows (C8)",
      calibrate.tally(TALLY_ROWS, "k") == {"a": [1, 2], "unknown": [0, 1]},
      calibrate.tally(TALLY_ROWS, "k"))
check("and counts loose too when asked for the loose-inclusive figure",
      calibrate.tally(TALLY_ROWS, "k", strengths=calibrate.STRENGTHS)
      == {"a": [1, 2], "unknown": [1, 1]},
      calibrate.tally(TALLY_ROWS, "k", strengths=calibrate.STRENGTHS))

# ------------------------------------------------- 22. the criteria ledger (FR-2.4)
tmp29 = with_snapshot("pending-criteria.md", "pairing-criteria.md")
rc, out_cr, err = call(*base_args(tmp29))
check("a snapshot carrying ## Criteria and a pairing carrying criterion: lines grades: exit 0",
      rc == 0, (rc, err))
check("the criteria ledger is a section of its own, counts only, never a rate",
      "## Criteria ledger (graded apart: verdict against what the meeting raised, counts only)"
      in out_cr and "| Key | Persona | Verdict | Evidence check | Outcome |" in out_cr, out_cr)
for needle in ["| budget-lin#c1 | budget-lin | met | body | miss (criterion present, accepted "
               "by declaration) |",
               "| budget-lin#c2 | budget-lin | declared | structural | flagged, raised |",
               "| ops-sam#c1 | ops-sam | not-addressed | unchecked | flagged, not raised |"]:
    check("the criteria ledger row %s" % needle.split("|")[1].strip(), needle in out_cr, out_cr)
check("a criterion no persona row carries is the real objection's own outcome",
      "| R4 | Sam | ops-sam | miss (criterion absent from the persona) |" in out_cr, out_cr)
check("a criterion the snapshot accepted by declaration names the row it was accepted on",
      "| R6 | Lin | budget-lin | miss (criterion present, accepted by declaration: "
      "budget-lin#c1) |" in out_cr, out_cr)
check("a criterion line never overwrites a match: R2 stays matched by its round-1 row",
      "| R2 | Lin | budget-lin | matched substantive by budget-lin#2 (round 1) |" in out_cr,
      out_cr)
check("the counts line is the pinned one",
      "criteria: 3 rows · flagged and raised 1 · accepted and raised 1 (present, by "
      "declaration) · absent from the persona 1" in out_cr, out_cr)
check("and one line says where each criteria miss points",
      "where a criteria miss points: present and accepted by declaration -> the review "
      "process, not the persona; absent from the persona -> its ## Judgment criteria"
      in out_cr, out_cr)
rc, out_crj, _ = call(*base_args(tmp29), "--json")
data_cr = json.loads(out_crj)
check("--json mirrors the criteria rows with their keys and outcomes",
      [(c["key"], c["verdict"], c["check"], c["raised"]) for c in data_cr["criteria"]]
      == [("budget-lin#c1", "met", "body", True),
          ("budget-lin#c2", "declared", "structural", True),
          ("ops-sam#c1", "not-addressed", "unchecked", False)],
      data_cr.get("criteria"))
check("--json carries the counts the line is built from",
      data_cr["criteria_counts"]["rows"] == 3
      and data_cr["criteria_counts"]["flagged_raised"] == 1
      and data_cr["criteria_counts"]["accepted_raised"] == 1
      and data_cr["criteria_counts"]["absent"] == 1
      and data_cr["criteria_counts"]["in_snapshot"] is True, data_cr.get("criteria_counts"))
tmp30 = with_snapshot("pending-criteria.md", "pairing-criteria.md")
call(*base_args(tmp30), "--apply")
check("--apply appends the criteria clause to the Notes",
      "criteria: 3 rows · flagged and raised 1 · accepted and raised 1 (present, by "
      "declaration) · absent from the persona 1"
      in (tmp30 / "trial/calibration/log.md").read_text(encoding="utf-8"),
      (tmp30 / "trial/calibration/log.md").read_text(encoding="utf-8")[-400:])

check("a snapshot without ## Criteria prints no criteria ledger and no clause",
      "## Criteria ledger" not in out and "criteria:" not in EXPECTED_ENTRY, EXPECTED_ENTRY)
rc, out_cn, err = call(*base_args(with_snapshot("pending-criteria-none.md")))
check("a ## Criteria section with no rows is a ledger of zero rows, not a missing section",
      rc == 0 and "## Criteria ledger" in out_cn
      and "criteria: 0 rows · flagged and raised 0 · accepted and raised 0 (present, by "
          "declaration) · absent from the persona 0" in out_cn, (rc, out_cn, err))

tmp32 = with_pairing("pairing-criterion-absent-only.md")
rc, out_ao, err = call(*base_args(tmp32))
check("an `absent` criterion on a snapshot with no ## Criteria still counts: exit 0",
      rc == 0 and "criteria: 0 rows · flagged and raised 0 · accepted and raised 0 (present, "
      "by declaration) · absent from the persona 1" in out_ao, (rc, out_ao, err))
check("a declared blind spot outranks it: the gap was pre-registered, and that outcome is "
      "the one 0.2 pinned",
      "| R4 | Sam | ops-sam | miss (declared blind spot) |" in out_ao, out_ao)
call(*base_args(tmp32), "--apply")
check("and with no ## Criteria in the snapshot the clause stays out of the log",
      "criteria: 0 rows"
      not in (tmp32 / "trial/calibration/log.md").read_text(encoding="utf-8"),
      (tmp32 / "trial/calibration/log.md").read_text(encoding="utf-8")[-400:])

# The grading cut-off is one rule and the criteria ledger obeys it like every other claim on
# a real objection: R7 arrived after it, so nothing it names may reach a count.
tmp33 = with_snapshot("pending-criteria.md", "pairing-criterion-late.md")
rc, out_lt, err = call(*base_args(tmp33))
check("a criterion line on a real that arrived after the cut-off grades: exit 0", rc == 0,
      (rc, err))
check("and it enters no count, neither as raised nor as absent",
      "criteria: 3 rows · flagged and raised 0 · accepted and raised 0 (present, by "
      "declaration) · absent from the persona 0" in out_lt, out_lt)
check("the row it named is still reported as never raised, not as accepted by declaration",
      "| budget-lin#c1 | budget-lin | met | body | accepted, not raised |" in out_lt, out_lt)
check("the late real keeps its own outcome, and nothing calls it a miss",
      "| R7 | Sam | ops-sam | noted, not graded: after the grading cut-off 2026-09-15 |"
      in out_lt and "miss (criterion" not in out_lt, out_lt)
check("and the dropped line is warned about, never dropped in silence",
      "warning: criterion: line on R7 ignored: that real objection arrived after the grading "
      "cut-off 2026-09-15 and is noted, not graded" in out_lt, out_lt[:600])
call(*base_args(tmp33), "--apply")
check("the log Notes carry the same zeroes, so the cycle cannot read as raised later",
      "criteria: 3 rows · flagged and raised 0 · accepted and raised 0 (present, by "
      "declaration) · absent from the persona 0"
      in (tmp33 / "trial/calibration/log.md").read_text(encoding="utf-8"),
      (tmp33 / "trial/calibration/log.md").read_text(encoding="utf-8")[-400:])

rc, out_dup, err = call(*base_args(with_pairing("pairing-criterion-absent-twice.md")))
check("the same criterion line written twice is one judgment, not two",
      rc == 0 and "absent from the persona 1" in out_dup, (rc, out_dup, err))

rc, out_ap2, err = call(*base_args(with_snapshot("pending-criteria-absent-persona.md")))
check("a criteria row of a rostered-but-absent persona is counted: the table's rows are the "
      "count, and someone else in the room can raise her criterion",
      rc == 0 and "| legal-toft#c1 | legal-toft | unmet | body | flagged, not raised |"
      in out_ap2 and "criteria: 4 rows" in out_ap2, (rc, out_ap2, err))

rc, out_uk, err_uk = call(*base_args(
    with_snapshot("pending-criteria.md", "pairing-criteria-unknown-key.md")))
check("a criterion line naming no ## Criteria row: exit 2 with the key",
      rc == 2 and "pairing references unknown key budget-lin#c9" in (out_uk + err_uk),
      (rc, out_uk, err_uk))
rc, out_am, err_am = call(*base_args(
    with_snapshot("pending-criteria-ambiguous.md", "pairing-criteria-ambiguous.md")))
check("a #c<n> the pasted table carries twice is refused, never graded against a guess",
      rc == 2 and "pairing references ambiguous key budget-lin#c1" in (out_am + err_am),
      (rc, out_am, err_am))
check("and the refusal says what it observed, not a cause it never saw",
      "the pasted table names this key twice (a persona that returned two round-1 blocks "
      "restarts the numbering)" in (out_am + err_am), err_am)
rc, out_cm, err_cm = call(*base_args(
    with_snapshot("pending-criteria.md", "pairing-criterion-malformed.md")))
check("a criterion line in another shape stops the run instead of being skipped",
      rc == 2 and "pairing line not understood" in (out_cm + err_cm)
      and "criterion: R<j> | <slug>#c<n>" in (out_cm + err_cm), (rc, out_cm, err_cm))

check("criterion_outcome: the snapshot accepted it and the meeting raised it anyway",
      calibrate.criterion_outcome("met", True)
      == "miss (criterion present, accepted by declaration)")
check("criterion_outcome: the other three verdicts raised are the panel flagging it first",
      [calibrate.criterion_outcome(v, True) for v in ("declared", "unmet", "not-addressed")]
      == ["flagged, raised"] * 3)
check("criterion_outcome: not raised at all is counted, never dropped",
      calibrate.criterion_outcome("met", False) == "accepted, not raised"
      and calibrate.criterion_outcome("unmet", False) == "flagged, not raised")
check("parse_criteria: no section is None, an empty one is [] — the two are not the same",
      calibrate.parse_criteria("# s\n\n## Green lights\n", "trial") is None
      and calibrate.parse_criteria("## Criteria\nnone.\n", "trial") == [])

# The section is pasted out of `panel --aggregate` unedited, so the keys this file derives
# from the pasted table have to be the keys `panel` itself assigned. Read from the aggregate's
# real output rather than from a copy of it, because a copy is what drifts.
PANEL_ROUND = HERE / "test_fixtures/panel/criteria-round"
PANEL_DOC = HERE / "test_fixtures/panel/criteria-doc.md"
GOLDEN_INDEX = HERE / "test_fixtures/store/golden/INDEX.md"
# The guard below decides whether the cross-module check runs at all, so a renamed or deleted
# fixture would take the check with it in silence. It is asserted first.
check("the fixtures the cross-module criteria check needs are all present",
      PANEL_ROUND.is_dir() and PANEL_DOC.is_file() and GOLDEN_INDEX.is_file(),
      [str(p) for p in (PANEL_ROUND, PANEL_DOC, GOLDEN_INDEX) if not p.exists()])
if PANEL_ROUND.is_dir() and PANEL_DOC.is_file() and GOLDEN_INDEX.is_file():
    agg = [sys.executable, str(HERE / "beforehand.py"), "panel", "--aggregate",
           str(PANEL_ROUND), "--roster", str(GOLDEN_INDEX), "--document", str(PANEL_DOC)]
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    printed = subprocess.run(agg, capture_output=True, text=True, env=env).stdout
    from_json = json.loads(subprocess.run(agg + ["--json"], capture_output=True, text=True,
                                          env=env).stdout)["criteria"]
    parsed = calibrate.parse_criteria(printed, "golden") or []
    check("the keys read back from a pasted ## Criteria section are the keys panel assigned",
          [c["key"] for c in parsed] == [c["key"] for c in from_json],
          ([c["key"] for c in parsed], [c["key"] for c in from_json]))
    check("and so are the verdicts and the evidence checks the ledger grades on",
          [(c["verdict"], c["check"]) for c in parsed]
          == [(c["verdict"], c["check"]) for c in from_json],
          [(c["verdict"], c["check"]) for c in parsed])
    check("no persona of a one-block round is marked ambiguous",
          not any(c["ambiguous"] for c in parsed), parsed)

# The regression guard of this release: every fragment above is conditional, so the cycle the
# 0.2 fixture describes writes the entry 0.2 pinned, byte for byte.
tmp31 = fresh_store()
call(*base_args(tmp31), "--apply")
check("after all of the above, an ordinary cycle's log entry is still byte-identical",
      (tmp31 / "trial/calibration/log.md").read_text(encoding="utf-8").endswith(EXPECTED_ENTRY),
      repr((tmp31 / "trial/calibration/log.md").read_text(encoding="utf-8")[-200:]))

# The pairing grammar in the reference is a template a user copies, so every line of it has
# to survive the parser with its placeholders filled in. `|` is this grammar's field
# separator, so writing alternatives on one line the way a fence usually does produces a line
# that is refused when it is written to.
GRAMMAR = [b for b in re.findall(r"^```.*?\n(.*?)^```", REF, re.S | re.M)
           if "unmatched real:" in b]
check("references/calibrate.md carries exactly one pairing grammar block", len(GRAMMAR) == 1,
      len(GRAMMAR))
crit_templates = [ln for ln in (GRAMMAR[0] if GRAMMAR else "").splitlines()
                  if ln.strip().lower().startswith("criterion:")]
check("the block shows both criterion shapes, one line each", len(crit_templates) == 2,
      crit_templates)
for template in crit_templates:
    filled = template.replace("R<j>", "R1").replace("<slug>#c<n>", "budget-lin#c1")
    try:
        parsed_crit = calibrate.parse_pairing(filled)[3]
    except calibrate.NotGradeable as exc:
        parsed_crit, filled = [], "%s -> %s" % (filled, exc)
    check("a criterion template line copied literally parses: %s" % template.strip(),
          len(parsed_crit) == 1, filled)

# ------------------------------------------- 23. a literal pipe inside a cell (`\|`)
# `panel.cell()` writes a pipe inside a cell as `\|` and `review.md` says never to edit the
# pasted table, so the snapshot this file reads can carry one. Splitting on raw pipes shifted
# every column to its right — silently, including the row key, which dropped the row out of
# the gradeable set and blamed the pairing for it.
check("table(): an escaped pipe is content, not a separator",
      calibrate.table('| a \\| b | c |\n') == (["a | b", "c"], []),
      calibrate.table('| a \\| b | c |\n'))
check("table(): a cell ending in an escaped pipe keeps it — the closing delimiter is the "
      "unescaped one",
      calibrate.table('| a | b \\||\n') == (["a", "b |"], []),
      calibrate.table('| a | b \\||\n'))
check("table(): a row without escapes reads exactly as it did before",
      calibrate.table("| A | B |\n|---|---|\n| one | two |\n")
      == (["a", "b"], [["one", "two"]]),
      calibrate.table("| A | B |\n|---|---|\n| one | two |\n"))

tmp29b = with_snapshot("pending-escaped-pipes.md", "pairing-criteria.md")
rc, out_ep, err = call(*base_args(tmp29b))
check("a snapshot with `\\|` in an Anchor cell and in a Criterion cell still grades: exit 0",
      rc == 0, (rc, err))
check("and the whole accounting is the one the unescaped snapshot produces — the escape "
      "moves no column",
      out_ep.split("\n", 1)[1] == out_cr.split("\n", 1)[1],
      out_ep.split("\n", 1)[1][:600])
check("no escape leaks into what is printed back",
      "\\|" not in out_ep, out_ep[:400])


# ------------------------------- 23b. a greenlight line the parser cannot read is reported
# The annotation template used to show `observed yes | no | not observed | not applicable`,
# a menu; only the first alternative parses, and the other three were skipped in silence —
# the slug then defaulted to `not observed`, so an observation the user wrote down vanished.
tmp29c = fresh_store()
shutil.copy(VAR / "annotation-greenlight-menu.md",
            tmp29c / "trial/calibration/annotation-brief-q4.md")
rc, out_gw, err = call(*base_args(tmp29c))
check("an unreadable greenlight line does not stop the cycle: exit 0", rc == 0, (rc, err))
check("it is reported as a warning, with the line and the shape that parses",
      "warning: greenlight line not read" in out_gw
      and "- greenlight: platform-noor | not observed" in out_gw
      and "observed <yes | no | not observed | not applicable>" in out_gw, out_gw[:900])
check("the slug it names is still counted as not observed, as it always was",
      "predicted YES / observed no: 0" in out_gw, out_gw)
check("--help shows the greenlight shape the parser actually reads",
      "- greenlight: <slug> | observed <yes | no | not observed | not applicable>" in r.stdout,
      r.stdout[:400])


# --------------------------------------------------------------- 24. --help documents them all
check("--help documents the closed unmatched tag set",
      "blind spot | known | new" in r.stdout, r.stdout[:400])
check("--help documents the fourth pairing line shape",
      "criterion: R<j> | <slug>#c<n>" in r.stdout and "criterion: R<j> | absent" in r.stdout,
      r.stdout[:400])
check("--help documents the third key form and says it is its own series",
      "<slug>#c<n>" in r.stdout, r.stdout[:400])
check("--help names the source type field and its values",
      "source type: private-communication | public-statement | second-hand | mixed"
      in r.stdout, r.stdout[:400])
check("--help names the three pinned miss outcomes",
      "miss (known, in the persona)" in r.stdout
      and "miss (declared blind spot)" in r.stdout
      and "miss (criterion absent from the persona)" in r.stdout, r.stdout[:400])

# ---- an unknown locale is a usage error here too (FR-4.4, same as every other module)
r = subprocess.run([sys.executable, str(HERE / "beforehand.py"), "calibrate",
                    "--context", "trial", "--doc", "brief-q4"],
                   capture_output=True, text=True,
                   env=dict(os.environ, BEFOREHAND_LOCALE="zz", PYTHONDONTWRITEBYTECODE="1"))
check("an unknown locale exits 1 and names what is available",
      r.returncode == 1 and "unknown locale 'zz'" in r.stderr, (r.returncode, r.stderr))

# =================================================================================== 0.3.1
def safe(fn, *a, **kw):
    """A missing helper or a raising one fails its check instead of crashing the suite."""
    try:
        return fn(*a, **kw)
    except Exception as e:                      # noqa: BLE001 — reported as the check's value
        return "%s: %s" % (e.__class__.__name__, e)


CAL_DIR = "trial/calibration"
ANN_NAME = "annotation-brief-q4.md"
FIXTURE_ANN = (STORE / CAL_DIR / ANN_NAME).read_text(encoding="utf-8")
FIXTURE_SNAP = (STORE / CAL_DIR / "pending-brief-q4.md").read_text(encoding="utf-8")


def with_annotation(text):
    st = fresh_store()
    (st / CAL_DIR / ANN_NAME).write_text(text, encoding="utf-8")
    return st


# ------------------------------------------------ 25. --apply never overwrites (C1, FR-3.1)
# Re-grading the same document on the same day used to rename the second pending file over
# the first frozen record (POSIX rename replaces), after the log entry had been written.
t25 = fresh_store()
cal25 = t25 / CAL_DIR
rc1, _, _ = call(*base_args(t25), "--apply")
first = cal25 / "done-2026-09-21-brief-q4.md"
first_bytes = first.read_bytes() if first.is_file() else b""
second_snap = FIXTURE_SNAP + "\n<!-- MARK-SECOND-RECORD -->\n"
(cal25 / "pending-brief-q4.md").write_text(second_snap, encoding="utf-8")
rc2, out25, err25 = call(*base_args(t25), "--apply")
second = cal25 / "done-2026-09-21-brief-q4-2.md"
check("C1: a second --apply the same day exits 0", rc1 == 0 and rc2 == 0, (rc1, rc2, err25))
check("C1: the first frozen record is byte-intact",
      first_bytes == (STORE / CAL_DIR / "pending-brief-q4.md").read_bytes(),
      sorted(p.name for p in cal25.iterdir()))
check("C1: the second record goes to the first free done-<date>-<doc>-<n>.md (n >= 2)",
      second.is_file() and "MARK-SECOND-RECORD" in second.read_text(encoding="utf-8"),
      sorted(p.name for p in cal25.iterdir()))
check("C1: stdout names the path actually written",
      "pending-brief-q4.md -> done-2026-09-21-brief-q4-2.md" in out25, out25[-300:])
log25 = (cal25 / "log.md").read_text(encoding="utf-8") if (cal25 / "log.md").is_file() else ""
check("C1: the log carries one entry per apply, no more",
      log25.count("## 2026-09-21 — brief-q4 (snapshot ") == 2, log25[-600:])
(cal25 / "pending-brief-q4.md").write_text(FIXTURE_SNAP + "\n<!-- third -->\n", encoding="utf-8")
call(*base_args(t25), "--apply")
check("C1: a third apply the same day takes -3",
      (cal25 / "done-2026-09-21-brief-q4-3.md").is_file() and second.is_file() and first.is_file(),
      sorted(p.name for p in cal25.iterdir()))

# the append fails: the rename is undone and the command says why
t25b = fresh_store()
cal25b = t25b / CAL_DIR
saved_append = getattr(calibrate, "append_line", None)


def _boom(path, line):
    raise OSError("no space left on device (simulated)")


calibrate.append_line = _boom
try:
    rc, out25b, err25b = call(*base_args(t25b), "--apply")
finally:
    if saved_append is None:
        del calibrate.append_line
    else:
        calibrate.append_line = saved_append
check("C1: an append failure exits 1", rc == 1, (rc, out25b, err25b))
check("C1: and the pending file is back in place, no done- file left behind",
      (cal25b / "pending-brief-q4.md").is_file()
      and not list(cal25b.glob("done-*.md")),
      sorted(p.name for p in cal25b.iterdir()))
check("C1: and the reason is printed", "simulated" in err25b, err25b)

# ------------------------------------------------ 26. per-persona coverage (C2, FR-3.2)
# Sam's row predicts R1, which Lin raised; Sam's own R4 is missed. Sam's coverage used to read
# 100% (a hit on anyone's objection over Sam's own reals) and Lin's R1 vanished from every
# denominator. Four prior cycles in the log put both over the floor, so percentages print.
LOG_PRIOR = "# Calibration log — trial\n\n" + "".join(
    "## 2026-0%d-01 — prior-%d (snapshot 000000000000)\n%s\n|---|---|\n"
    "| budget-lin | trial |\n| ops-sam | trial |\n| platform-noor | trial |\n\n"
    % (i, i, calibrate.LOG_HEADER) for i in range(1, 5))
t26 = fresh_store()
(t26 / CAL_DIR / "pairing-brief-q4.md").write_text(
    "ops-sam#1 | R1 | exact | Sam's row predicts the objection Lin raised\n"
    "unmatched real: R2, R3, R4, R5, R6\n", encoding="utf-8")
(t26 / CAL_DIR / "log.md").write_text(LOG_PRIOR, encoding="utf-8")
rc, out26, err26 = call(*base_args(t26), "--json")
per26 = {}
if rc == 0:
    per26 = dict((p["persona"], p["running"]) for p in json.loads(out26)["personas"])
check("C2: the Sam/Lin cycle grades", rc == 0, (rc, err26))
check("C2: Sam's hit on Lin's objection counts for Sam's precision, not Sam's coverage",
      per26.get("ops-sam") == "5 cycles: precision 50%, coverage 0%", per26)
check("C2: and for Lin's coverage — R1 is Lin's, and it was covered",
      per26.get("budget-lin") == "5 cycles: precision 0%, coverage 33%", per26)

# Fix round 1: a persona's own real objection that only a P<k> matched (here loose) stays in
# that persona's coverage denominator — it is theirs, and no round-1 row covered it.
t26b = fresh_store()
(t26b / CAL_DIR / "pairing-brief-q4.md").write_text(
    "platform-noor#1 | R3 | exact | same substance\n"
    "P1 | R5 | loose | thematic only\n"
    "unmatched real: R1, R2, R4, R6\n", encoding="utf-8")
(t26b / CAL_DIR / "log.md").write_text(LOG_PRIOR, encoding="utf-8")
rc, out26b, err26b = call(*base_args(t26b), "--json")
per26b = dict((p["persona"], p["running"]) for p in json.loads(out26b)["personas"]) \
    if rc == 0 else {}
check("C2: a real only the predictions ledger matched stays in its persona's denominator",
      per26b.get("platform-noor") == "5 cycles: precision 50%, coverage 50%", (per26b, err26b))

# ------------------------------------------------ 27. absent personas and green lights (C3)
for entry, why in (("legal-toft (on leave)", "a trailing parenthetical"),
                   ("Toft", "a name persona_for resolves"),
                   ("Toft (on leave, back in May)", "a comma inside its parenthetical")):
    rc, out27, err27 = call(*base_args(with_annotation(FIXTURE_ANN.replace(
        "Personas rostered but absent: legal-toft",
        "Personas rostered but absent: %s" % entry))), "--json")
    rates27 = json.loads(out27)["rates"] if rc == 0 else {}
    check("C3: an absent entry with %s still leaves the denominators" % why,
          rc == 0 and rates27.get("precision") == [2, 6], (rc, rates27.get("precision"), err27))
rc, out27, err27 = call(*base_args(with_annotation(FIXTURE_ANN.replace(
    "Personas rostered but absent: legal-toft", "Personas rostered but absent: legal-tofu"))))
check("C3: an absent entry that resolves to no roster persona is not gradeable (exit 2)",
      rc == 2 and "not gradeable: annotation names an absent persona not in the roster: "
      "legal-tofu" in err27, (rc, err27))
rc, out27, err27 = call(*base_args(with_annotation(FIXTURE_ANN.replace(
    "- greenlight: data-rey | observed yes", "- greenlight: data-ray | observed yes"))))
check("C3: a greenlight line naming no roster slug is not gradeable (exit 2)",
      rc == 2 and "not gradeable: greenlight names a persona not in the roster: data-ray"
      in err27, (rc, err27))

# ------------------------------------------------ 28. duplicate ids (C4, FR-3.4)
dup_ann = FIXTURE_ANN.replace("- R4 |", "- R3 | Noor | said identity again | the identity "
                              "section | channel: in-meeting | actual severity: 4\n- R4 |")
rc, out28, err28 = call(*base_args(with_annotation(dup_ann)))
check("C4: a duplicate R<j> in the annotation is not gradeable (exit 2)",
      rc == 2 and "not gradeable: duplicate real objection id R3 in the annotation" in err28,
      (rc, err28))
t28 = fresh_store()
(t28 / CAL_DIR / "pending-brief-q4.md").write_text(FIXTURE_SNAP.replace(
    "- P3 | ops-sam", "- P2 | ops-sam"), encoding="utf-8")
rc, out28, err28 = call(*base_args(t28))
check("C4: a duplicate P<k> in the snapshot is not gradeable (exit 2)",
      rc == 2 and "not gradeable: duplicate prediction id P2 in the snapshot" in err28,
      (rc, err28))
check("C4: parse_predictions itself raises NotGradeable on a duplicate id (forget relies on it)",
      "NotGradeable: duplicate prediction id P9 in the snapshot" == safe(
          calibrate.parse_predictions,
          "## Predictions to verify\n- P9 | a | x | Red lines\n- P9 | b | y | Red lines\n"),
      safe(calibrate.parse_predictions, "## Predictions to verify\n- P9 | a\n- P9 | b\n"))
check("C4: parse_predictions keeps its one-argument signature",
      list(inspect.signature(calibrate.parse_predictions).parameters) == ["text"],
      str(inspect.signature(calibrate.parse_predictions)))

# ------------------------------------------------ 29. the ledger rate counts headline (C8)
rc, out29, err29 = call(*base_args(with_pairing("pairing-cross-block.md")), "--json")
lg29 = json.loads(out29)["ledger"] if rc == 0 else {}
check("C8: the ledger rate counts exact+substantive as hits, loose shown alongside",
      lg29.get("hits") == 1 and lg29.get("hits_loose_inclusive") == 2, lg29)
check("C8: every split counts headline too, with its own loose-inclusive figure",
      lg29.get("by_source_flow") == {"consult": [1, 2], "rehearsal": [0, 1]}
      and lg29.get("by_source_flow_loose_inclusive") == {"consult": [1, 2], "rehearsal": [1, 1]}
      and lg29.get("by_grounding_loose_inclusive") == {"Recurring objections": [2, 2],
                                                       "Judgment criteria": [0, 1]},
      lg29)

fails = [c for c in checks if not c[1]]
for name, ok, got in checks:
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else "  -> got %s" % (str(got)[:400],)))
print("\n%d/%d passed" % (len(checks) - len(fails), len(checks)))
sys.exit(1 if fails else 0)
