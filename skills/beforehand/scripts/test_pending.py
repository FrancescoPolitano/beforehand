#!/usr/bin/env python3
"""Tests for pending.py's own behaviour: the meeting-date writer (FR-1.2) and the pre-0.2
snapshot format (FR-1.1).

`pending` was a report and nothing else until 0.3; `--set-meeting` is the one thing here that
writes, so most of this file is about what it writes, what it refuses, and what it leaves
alone. Every run pins `pending._today` — no test may depend on the day the suite happens to
run (Global Constraints) — and every store a test mutates is a temporary copy.
"""
import contextlib
import datetime as dt
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True  # G5: a suite run on its own leaves no __pycache__

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import pending  # noqa: E402

FIXTURE = HERE / "test_fixtures/store"
CAL = HERE / "test_fixtures/calibrate"
ENTRY = HERE / "beforehand.py"
FAKE_TODAY = dt.date(2026, 9, 21)
checks = []


def check(name, ok, got=None):
    checks.append((name, bool(ok), got))


def fresh(src=FIXTURE):
    tmp = Path(tempfile.mkdtemp()) / "store"
    shutil.copytree(src, tmp)
    return tmp


def call(*args, **kw):
    """pending.main in-process with the date hook pinned. -> (rc, stdout, stderr)."""
    today = kw.pop("today", FAKE_TODAY)
    out, err = io.StringIO(), io.StringIO()
    saved = pending._today
    pending._today = lambda: today
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = pending.main([str(a) for a in args])
    finally:
        pending._today = saved
    return rc, out.getvalue(), err.getvalue()


def state(root):
    """Digest of every file under root: proof that a command wrote nothing."""
    return {str(p.relative_to(root)): hashlib.sha1(p.read_bytes()).hexdigest()
            for p in sorted(Path(root).rglob("*")) if p.is_file()}


# ----------------------------------------------------------- 1. a date that moves
tmp = fresh()
snap = tmp / "golden/calibration/pending-brief-q3.md"
before_text = snap.read_text(encoding="utf-8")
before_all = state(tmp)
rc, out, err = call("--store", tmp, "--context", "golden", "--set-meeting", "brief-q3",
                    "2026-09-21")
after_text = snap.read_text(encoding="utf-8")
check("--set-meeting exits 0", rc == 0, (rc, out, err))
check("stdout names the file and both dates",
      out.strip() == "written: calibration/pending-brief-q3.md meeting 2099-01-15 -> 2026-09-21",
      out)
check("the new date is written once, under the English key",
      after_text.count("meeting: 2026-09-21") == 1, after_text[:400])
check("the old date is not left anywhere as a field",
      "meeting: 2099-01-15" not in after_text, after_text[:400])
check("the move is recorded directly under the meeting line",
      "meeting: 2026-09-21\nmeeting moved: 2099-01-15 -> 2026-09-21 on 2026-09-21\n"
      in after_text, after_text[:400])
check("nothing else in the file changed",
      after_text.replace("meeting: 2026-09-21\n"
                         "meeting moved: 2099-01-15 -> 2026-09-21 on 2026-09-21\n",
                         "meeting: 2099-01-15\n") == before_text,
      after_text[:400])
check("no other file in the store was touched",
      {k: v for k, v in state(tmp).items()
       if k != "golden/calibration/pending-brief-q3.md"}
      == {k: v for k, v in before_all.items()
          if k != "golden/calibration/pending-brief-q3.md"}, "store changed")

# the same run again is a no-op, and says so
rc, out2, err2 = call("--store", tmp, "--context", "golden", "--set-meeting", "brief-q3",
                      "2026-09-21")
check("setting the date it already says exits 0", rc == 0, (rc, err2))
check("and says unchanged, naming the date",
      out2.strip() == "unchanged: calibration/pending-brief-q3.md already says meeting "
                      "2026-09-21", out2)
check("a no-op move writes nothing: no second history line",
      snap.read_text(encoding="utf-8") == after_text, snap.read_text(encoding="utf-8")[:400])

# a second, real move appends; nothing is ever deleted
rc, out3, _ = call("--store", tmp, "--context", "golden", "--set-meeting", "brief-q3",
                   "2026-10-05", today=dt.date(2026, 9, 25))
moved = [ln for ln in snap.read_text(encoding="utf-8").splitlines()
         if ln.startswith("meeting moved:")]
check("a second move keeps the first line and adds its own",
      moved == ["meeting moved: 2099-01-15 -> 2026-09-21 on 2026-09-21",
                "meeting moved: 2026-09-21 -> 2026-10-05 on 2026-09-25"], moved)
check("the second move names the date it replaced, not the original one",
      "meeting 2026-09-21 -> 2026-10-05" in out3, out3)

rc, out_j, _ = call("--store", tmp, "--context", "golden", "--json")
row = json.loads(out_j)[0]
check("--json exposes the whole history in file order",
      row["meeting_history"] == [{"from": "2099-01-15", "to": "2026-09-21",
                                  "on": "2026-09-21"},
                                 {"from": "2026-09-21", "to": "2026-10-05",
                                  "on": "2026-09-25"}], row.get("meeting_history"))
check("--json reports the date that is now in force", row["meeting"] == "2026-10-05", row)
rc, out_h, _ = call("--store", tmp, "--context", "golden")
check("the human line says where the date moved from",
      "moved from 2026-09-21" in out_h, out_h)

# ----------------------------------------------------------- 2. `meeting: unknown`
tmp2 = fresh()
rc, out, err = call("--store", tmp2, "--context", "northwind", "--set-meeting", "memo-nodate",
                    "2026-09-21")
memo = (tmp2 / "northwind/calibration/pending-memo-nodate.md").read_text(encoding="utf-8")
check("an unknown date is replaced like any other", rc == 0 and "meeting: 2026-09-21" in memo,
      (rc, memo))
check("and the history says it was unknown, not none",
      "meeting moved: unknown -> 2026-09-21 on 2026-09-21" in memo, memo)
check("stdout carries the same word", "meeting unknown -> 2026-09-21" in out, out)

# ----------------------------------------------------------- 3. a snapshot with no such field
tmp3 = Path(tempfile.mkdtemp()) / "store"
(tmp3 / "trial/calibration").mkdir(parents=True)
prose_src = (CAL / "variants/pending-prose.md").read_text(encoding="utf-8")
prose = tmp3 / "trial/calibration/pending-brief-q4.md"
prose.write_text(prose_src, encoding="utf-8")
rc, out, err = call("--store", tmp3, "--context", "trial", "--set-meeting", "brief-q4",
                    "2026-09-21")
lines = prose.read_text(encoding="utf-8").splitlines()
i = lines.index("meeting: 2026-09-21")
check("a file with no meeting field gets one", rc == 0 and i > 0, (rc, err, lines[:12]))
check("stdout says there was no date before, not that it was unknown",
      "meeting none -> 2026-09-21" in out, out)
check("the field lands in the head block, after the last header line",
      lines[i - 1].startswith("Mode:"), lines[max(0, i - 3):i + 2])
check("and before the first body heading",
      i < next(k for k, ln in enumerate(lines) if ln.startswith("### ")), (i, lines[:14]))
check("the history line follows it",
      lines[i + 1] == "meeting moved: none -> 2026-09-21 on 2026-09-21", lines[i:i + 3])
rc, out_j, _ = call("--store", tmp3, "--context", "trial", "--json")
row = json.loads(out_j)[0]
check("the date is readable afterwards, and the move is one entry",
      row["meeting"] == "2026-09-21" and len(row["meeting_history"]) == 1, row)

# a head block with no header line and no title at all: the field goes to the top
bare = tmp3 / "trial/calibration/pending-bare.md"
bare.write_text("## Round-1 objections\n| Persona |\n", encoding="utf-8")
rc, out, err = call("--store", tmp3, "--context", "trial", "--set-meeting", "bare",
                    "2026-09-21")
check("with no header line and no title, the field goes to the very top",
      rc == 0 and bare.read_text(encoding="utf-8").startswith(
          "meeting: 2026-09-21\nmeeting moved: none -> 2026-09-21 on 2026-09-21\n"
          "## Round-1 objections"), bare.read_text(encoding="utf-8"))

# frontmatter is not the documented snapshot shape, but it is tolerated rather than broken
fm = tmp3 / "trial/calibration/pending-fm.md"
fm.write_text("---\nslug: x\nmeeting: 2020-01-01\n---\n\nbody\n", encoding="utf-8")
rc, _, err = call("--store", tmp3, "--context", "trial", "--set-meeting", "fm", "2026-09-21")
check("a frontmatter block is edited in place, not duplicated below it",
      rc == 0 and fm.read_text(encoding="utf-8") ==
      "---\nslug: x\nmeeting: 2026-09-21\n"
      "meeting moved: 2020-01-01 -> 2026-09-21 on 2026-09-21\n---\n\nbody\n",
      fm.read_text(encoding="utf-8"))

fm2 = tmp3 / "trial/calibration/pending-fm2.md"
fm2.write_text("---\nslug: x\n---\n\nbody\n", encoding="utf-8")
call("--store", tmp3, "--context", "trial", "--set-meeting", "fm2", "2026-09-21")
check("a frontmatter block with no such field gets it before the closing delimiter",
      fm2.read_text(encoding="utf-8") ==
      "---\nslug: x\nmeeting: 2026-09-21\n"
      "meeting moved: none -> 2026-09-21 on 2026-09-21\n---\n\nbody\n",
      fm2.read_text(encoding="utf-8"))

# ----------------------------------------------------------- 4. usage errors write nothing
for name, args, needle in [
        ("a date that is not YYYY-MM-DD",
         ["--context", "golden", "--set-meeting", "brief-q3", "14 September"],
         "meeting date must be YYYY-MM-DD"),
        ("a date-shaped string that is not a date",
         ["--context", "golden", "--set-meeting", "brief-q3", "2026-13-40"],
         "meeting date must be YYYY-MM-DD"),
        ("no --context", ["--set-meeting", "brief-q3", "2026-09-21"],
         "--set-meeting needs --context"),
        ("a document with no pending snapshot",
         ["--context", "golden", "--set-meeting", "nothing-here", "2026-09-21"],
         "no pending snapshot for nothing-here: expected calibration/pending-nothing-here.md"),
]:
    tmp4 = fresh()
    before4 = state(tmp4)
    rc, out, err = call("--store", tmp4, *args)
    check("%s is a usage error (exit 1)" % name, rc == 1, (rc, out, err))
    check("%s is refused with the pinned reason on stderr" % name,
          err.startswith("usage: ") and needle in err, err)
    check("%s leaves the store untouched" % name, state(tmp4) == before4, "store changed")

# ----------------------------------------------------------- 5. warnings, never refusals
tmp5 = fresh(CAL / "store")
rc, out, err = call("--store", tmp5, "--context", "trial", "--set-meeting", "brief-q4",
                    "2026-09-01")
check("a date on or before frozen: is still written", rc == 0 and out.startswith("written: "),
      (rc, out, err))
check("but the warning names the gate that will refuse it",
      "warning: meeting 2026-09-01 is on or before frozen 2026-09-01" in err
      and "calibrate will refuse this snapshot" in err, err)
r = subprocess.run([sys.executable, str(HERE / "calibrate.py"), "--store", str(tmp5),
                    "--context", "trial", "--doc", "brief-q4"],
                   capture_output=True, text=True,
                   env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
check("and calibrate does refuse it, which is where that gate lives",
      r.returncode == 2 and "frozen on or after the meeting" in (r.stdout + r.stderr),
      (r.returncode, r.stderr))

tmp6 = fresh()
ev_before = (tmp6 / "northwind/calibration/pending-brief-preds.md").read_text(encoding="utf-8")
ev_block = ev_before.split("events:\n", 1)[1].split("personas:", 1)[0]
rc, out, err = call("--store", tmp6, "--context", "northwind", "--set-meeting", "brief-preds",
                    "2026-09-21")
ev_after = (tmp6 / "northwind/calibration/pending-brief-preds.md").read_text(encoding="utf-8")
check("an events: block gets a note, not a refusal",
      rc == 0 and "note: events: block left as written" in err, (rc, err))
check("and the block itself is byte-identical",
      ev_after.split("events:\n", 1)[1].split("personas:", 1)[0] == ev_block,
      ev_after.split("events:\n", 1)[1][:200])
check("the meeting field moved even so",
      "meeting: 2026-09-21" in ev_after and "meeting moved: 2099-01-01 -> 2026-09-21 on "
      "2026-09-21" in ev_after, ev_after[:300])

# ----------------------------------------------------------- 6. without the flag, a report
tmp7 = fresh()
before7 = state(tmp7)
call("--store", tmp7)
call("--store", tmp7, "--json")
call("--store", tmp7, "--overdue-only")
check("pending without --set-meeting still writes nothing", state(tmp7) == before7,
      "store changed")
rc, out, _ = call("--store", tmp7)
check("the summary line names the command that records a missing date",
      "without a meeting date (ask when the meeting is, then: beforehand.py pending --context "
      "<ctx> --set-meeting <doc> YYYY-MM-DD)" in out, out[-300:])

# ----------------------------------------------------------- 7. through the entrypoint
tmp8 = fresh()
r = subprocess.run([sys.executable, str(ENTRY), "pending", "--store", str(tmp8), "--context",
                    "golden", "--set-meeting", "brief-q3", "2026-09-21"],
                   capture_output=True, text=True,
                   env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
check("beforehand.py dispatches --set-meeting with the store flag",
      r.returncode == 0 and r.stdout.startswith("written: "), (r.returncode, r.stdout, r.stderr))
r = subprocess.run([sys.executable, str(ENTRY), "pending", "--store", str(tmp8), "--context",
                    "golden", "--set-meeting", "brief-q3", "nope"],
                   capture_output=True, text=True,
                   env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
check("and the usage exit code survives the dispatcher", r.returncode == 1, (r.returncode,))
r = subprocess.run([sys.executable, str(ENTRY), "--help"], capture_output=True, text=True,
                   env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
check("the entrypoint help states pending's new exit contract",
      "0 ok (a report) · 1 usage with --set-meeting" in r.stdout, r.stdout)

# ----------------------------------------------------------- 8. the pre-0.2 format (FR-1.1)
check("a prose snapshot with no schema: and no sections is pre-0.2",
      pending.snapshot_format(prose_src) == "pre-0.2", prose_src[:120])
check("a declared schema is enough to be read normally, whatever else is missing",
      pending.snapshot_format("document: x\nschema: 0.1\nmeeting: 2026-01-01\n") == "0.2")
check("so is a predictions section with no schema line",
      pending.snapshot_format("document: x\n\n## Predictions to verify\n- P1 | a | b |\n")
      == "0.2")
check("so is a round-1 section with no schema line",
      pending.snapshot_format("document: x\n\n## Round-1 objections\n| a |\n") == "0.2")

# =================================================================================== 0.3.1
def scan_at(store, today, context=None):
    """pending.scan with the date hook pinned. -> (rows, stderr)."""
    err = io.StringIO()
    saved = pending._today
    pending._today = lambda: today
    try:
        with contextlib.redirect_stderr(err):
            rows = pending.scan(Path(store), context)
    finally:
        pending._today = saved
    return rows, err.getvalue()


def one_snapshot(name, text, extra=None):
    """A store with one context `c` holding calibration/<name> (+ extra {relpath: text})."""
    root = Path(tempfile.mkdtemp()) / "store"
    (root / "c/calibration").mkdir(parents=True)
    (root / "c/calibration" / name).write_text(text, encoding="utf-8")
    for relpath, body in (extra or {}).items():
        (root / "c" / relpath).parent.mkdir(parents=True, exist_ok=True)
        (root / "c" / relpath).write_text(body, encoding="utf-8")
    return root


SNAP9 = ("# Prediction snapshot\n\ndocument: docs/d.md\nsha1: %s\nschema: 0.2\n"
         "frozen: 2026-09-01\nmeeting: 2026-09-10\n\n## Predictions to verify\n"
         "- P1 | a | will ask | Red lines | source flow: review\n"
         "- note: a plain bullet the reviewer left, not a prediction\n"
         % ("0" * 40))

# C5: scan dates its status through its own `_today` hook
rows9, _ = scan_at(one_snapshot("pending-d.md", SNAP9), dt.date(2026, 9, 5))
check("C5: scan uses the _today hook, not the real calendar",
      rows9 and rows9[0]["status"] == "upcoming in 5 days" and rows9[0]["overdue"] is False,
      rows9 and rows9[0]["status"])

# C9: `pred N` counts `- P<k> |` rows, as calibrate does
check("C9: pred counts parse_predictions rows, not every bullet",
      rows9 and rows9[0]["predictions"] == 1, rows9 and rows9[0]["predictions"])

# C6: the locale alias `doc:` names the document for the changed-check too
DOC_TEXT = "the document as reviewed\n"
snap_alias = SNAP9.replace("document: docs/d.md", "doc: docs/d.md").replace(
    "0" * 40, hashlib.sha1(DOC_TEXT.encode()).hexdigest())
root_alias = one_snapshot("pending-d.md", snap_alias, {"docs/d.md": DOC_TEXT + "edited\n"})
rows_alias, _ = scan_at(root_alias, FAKE_TODAY)
check("C6: a `doc:` snapshot whose document changed reads document_changed True",
      rows_alias and rows_alias[0]["document_changed"] is True,
      rows_alias and rows_alias[0]["document_changed"])
(root_alias / "c/docs/d.md").write_text(DOC_TEXT, encoding="utf-8")
rows_alias, _ = scan_at(root_alias, FAKE_TODAY)
check("C6: and False once it matches the sha1 again",
      rows_alias and rows_alias[0]["document_changed"] is False,
      rows_alias and rows_alias[0]["document_changed"])

# C7: the snapshot key is the stem minus the leading `pending-` only
PROSE = "# Notes for the q3 review\n\nMeeting on 14 September.\n"
root7 = one_snapshot("pending-q3-pending-review.md", PROSE,
                     {"calibration/ledger-q3-pending-review.md":
                      "reconstructed: 2026-09-20\nmeeting: 2026-09-14\n"})
rows7, _ = scan_at(root7, FAKE_TODAY)
check("C7: a doc name containing `pending-` keeps it (document falls back to the key)",
      rows7 and rows7[0]["document"] == "q3-pending-review", rows7 and rows7[0]["document"])
check("C7: and the ledger beside it is found under the same key",
      rows7 and rows7[0]["ledger"] == "ledger-q3-pending-review.md"
      and rows7[0]["meeting"] == "2026-09-14", rows7 and (rows7[0]["ledger"], rows7[0]["meeting"]))

# S8 / FR-5.2: an unreadable snapshot is skipped with a per-file warning, never a crash
root_bad = one_snapshot("pending-d.md", SNAP9)
(root_bad / "c/calibration/pending-zz.md").mkdir()     # globbed like a file, unreadable
try:
    rows_bad, err_bad = scan_at(root_bad, FAKE_TODAY)
except Exception as e:                                  # noqa: BLE001
    rows_bad, err_bad = None, "raised %s" % e.__class__.__name__
check("scan skips an unreadable snapshot instead of raising, and keeps the others",
      rows_bad is not None and [r["snapshot"].endswith("pending-d.md") for r in rows_bad] == [True],
      (rows_bad, err_bad))
check("and warns once for that file, naming the exception",
      "warning: c/calibration/pending-zz.md: unreadable (IsADirectoryError)" in err_bad, err_bad)

fails = [c for c in checks if not c[1]]
for name, ok, got in checks:
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else "  -> got %s" % (str(got)[:400],)))
print("\n%d/%d passed" % (len(checks) - len(fails), len(checks)))
sys.exit(1 if fails else 0)
