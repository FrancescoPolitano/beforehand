#!/usr/bin/env python3
"""Tests for reindex.py and pending.py on the synthetic fixture store."""
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
tmp = Path(tempfile.mkdtemp()) / "store"
shutil.copytree(HERE / "test_fixtures/store", tmp)
checks = []
def run(*a):
    return subprocess.run([sys.executable, *a], capture_output=True, text=True)

r = run(HERE / "reindex.py", "--store", tmp, "--dry-run")
checks.append(("dry-run writes nothing",
               not (tmp / "INDEX.md").exists() and "would write" in r.stdout, r.stdout))
r = run(HERE / "reindex.py", "--store", tmp)
idx = (tmp / "northwind/INDEX.md").read_text()
root = (tmp / "INDEX.md").read_text()
checks.append(("context index has persona line",
               "- cto-mara | Chief Technology Officer | technical evaluator | weight 4 |" in idx, idx))
checks.append(("weight comment stripped", "# (Inference" not in idx, idx))
checks.append(("cares_about rendered",
               "cares about: vendor lock-in, on-call load for her team, migration downtime" in idx, idx))
checks.append(("wanted section carried from context.md", "- CFO | economic buyer" in idx, idx))
checks.append(("root index has description and count",
               "- northwind — the Northwind account" in root and "[1 persona]" in root, root))
r2 = run(HERE / "reindex.py", "--store", tmp)
checks.append(("idempotent", "unchanged" in r2.stdout and "written" not in r2.stdout, r2.stdout))
ptr = tmp / "pointer.md"
run(HERE / "reindex.py", "--store", tmp, "--context", "northwind", "--pointer", ptr)
checks.append(("pointer written", ptr.exists() and "cto-mara" in ptr.read_text(), ptr.exists()))

# ---- FR-1.2 lint column
bad = tmp / "ironbridge/personas/broken-bytes.md"
bad.write_bytes(
    b"---\nslug: broken\nrole: x\n---\n## Red lines\n- bad byte \xff here "
    b"(Fact \xe2\x80\x94 \"x\", sources/none.txt, private-communication, human-authored, 2026-08-01)\n")
r = run(HERE / "reindex.py", "--store", tmp)
iron = (tmp / "ironbridge/INDEX.md").read_text(encoding="utf-8", errors="replace")
root = (tmp / "INDEX.md").read_text()
checks.append(("reindex exits 0 with failing personas", r.returncode == 0, r.returncode))
checks.append(("failing persona shows lint: fail with counts",
               "- coo-dana |" in iron and "| lint: fail (1 not found)" in iron, iron))
checks.append(("lint then coverage, before the stale suffix",
               re.search(r"\| lint: [^|\n]+\| coverage: [^|\n]+(\| stale since [0-9-]+)?\n", iron)
               is not None, iron))
broken_line = next((ln for ln in iron.splitlines() if ln.startswith("- broken |")), "")
checks.append(("broken bytes persona indexed with a status, run not aborted",
               re.match(r"^- broken \|.*\| lint: \S", broken_line) is not None, iron))
checks.append(("root index counts failing lint",
               re.search(r"- ironbridge — .*\[\d+ personas, \d+ failing lint\]", root) is not None, root))
checks.append(("northwind root line has no failing clause",
               re.search(r"- northwind — .*\[1 persona\]", root) is not None, root))
checks.append(("lint root stamped in context header", "<!-- lint root:" in iron, iron))
# FR-7.3: the index declares the schema of the store it describes, in both index shapes.
checks.append(("schema comment stamped in context header", "<!-- schema: 0.2 -->" in iron, iron))
checks.append(("schema comment stamped in root header", "<!-- schema: 0.2 -->" in root, root))
r = run(HERE / "reindex.py", "--store", tmp, "--no-lint")
iron2 = (tmp / "ironbridge/INDEX.md").read_text(encoding="utf-8", errors="replace")
checks.append(("--no-lint writes lint: -", "| lint: -" in iron2, iron2))
checks.append(("--no-lint still stamps last-regenerated (the stamp tracks persona lines, "
               "not whether lint ran)", "<!-- last regenerated:" in iron2, iron2))
r = run(HERE / "reindex.py", "--store", tmp, "--fail-on-lint")
checks.append(("--fail-on-lint exits 3", r.returncode == 3, r.returncode))

cwd_a, cwd_b = tempfile.mkdtemp(), tempfile.mkdtemp()
subprocess.run([sys.executable, str(HERE / "reindex.py"), "--store", str(tmp)],
               cwd=cwd_a, capture_output=True)
idx_a = (tmp / "ironbridge/INDEX.md").read_bytes()
subprocess.run([sys.executable, str(HERE / "reindex.py"), "--store", str(tmp)],
               cwd=cwd_b, capture_output=True)
idx_b = (tmp / "ironbridge/INDEX.md").read_bytes()
checks.append(("cwd-independent index when sources_root declared", idx_a == idx_b, (cwd_a, cwd_b)))
cwd_c, cwd_d = tempfile.mkdtemp(), tempfile.mkdtemp()
rel_c, rel_d = os.path.relpath(tmp, cwd_c), os.path.relpath(tmp, cwd_d)
subprocess.run([sys.executable, str(HERE / "reindex.py"), "--store", rel_c], cwd=cwd_c, capture_output=True)
idx_c = (tmp / "ironbridge/INDEX.md").read_bytes()
subprocess.run([sys.executable, str(HERE / "reindex.py"), "--store", rel_d], cwd=cwd_d, capture_output=True)
idx_d = (tmp / "ironbridge/INDEX.md").read_bytes()
checks.append(("cwd-independent index with relative --store", idx_c == idx_d, (cwd_c, cwd_d, rel_c, rel_d)))

r = run(HERE / "pending.py", "--store", tmp, "--json")
rows = json.loads(r.stdout)
by = {x["document"]: x for x in rows}
# +1: golden/calibration/pending-brief-q3.md (Task 6)
checks.append(("pending snapshots found", len(rows) == 5, rows))
checks.append(("past meeting is overdue", by["~/work/northwind/proposal-v2.md"]["overdue"] is True, by))
checks.append(("unknown meeting flagged",
               by["memo"]["meeting"] is None and "no meeting date" in by["memo"]["status"], by["memo"]))
r = run(HERE / "pending.py", "--store", tmp)
checks.append(("human output mentions overdue and missing date",
               "OVERDUE" in r.stdout and "without a meeting date" in r.stdout, r.stdout))

# ---- FR-2.5 predictions, events, decisions
r = run(HERE / "pending.py", "--store", tmp, "--json")
rows = json.loads(r.stdout)
by = {x["document"]: x for x in rows}
bp = by["~/work/northwind/brief.md"]
zp = by["~/work/northwind/zero.md"]
checks.append(("predictions counted as top-level items, (none) excluded", bp["predictions"] == 2, bp))
checks.append(("pre-0.1 snapshot has null predictions", by["memo"]["predictions"] is None, by["memo"]))
checks.append(("schema-0.1 snapshot without a predictions section counts zero", zp["predictions"] == 0, zp))
checks.append(("events parsed with per-event overdue",
               len(bp["events"]) == 3 and bp["events"][0]["overdue"] is False
               and bp["events"][1]["overdue"] is True, bp["events"]))
checks.append(("unknown-date event parses to null date, not overdue",
               bp["events"][2]["date"] is None and bp["events"][2]["overdue"] is False, bp["events"][2]))
checks.append(("dangling P4 flagged", "P4" in json.dumps(bp.get("warnings", [])), bp))
checks.append(("document missing -> changed unknown", bp["document_changed"] is None, bp))
checks.append(("decisions recorded via matching review report", bp["decisions_recorded"] is True, bp))
checks.append(("decisions not recorded: own section is (none) and no matching report",
               zp["decisions_recorded"] is False, zp))
h = run(HERE / "pending.py", "--store", tmp)
checks.append(("human output shows pred N for a schema-0.1 row with predictions",
               "pred 2" in h.stdout, h.stdout))
checks.append(("human output shows pred - for a pre-0.1 row (no predictions section, no schema)",
               "pred -" in h.stdout, h.stdout))
checks.append(("human output shows pred 0 for a schema-0.1 row with no predictions section",
               "pred 0" in h.stdout, h.stdout))

# ---- coverage column, and gaps that used to be silent placeholders
iron3 = (tmp / "ironbridge/INDEX.md").read_text(encoding="utf-8", errors="replace")
persona_lines = [ln for ln in iron3.split("## Wanted")[0].splitlines() if ln.startswith("- ")]
checks.append(("every persona line carries a coverage verdict",
               persona_lines and all("| coverage: " in ln for ln in persona_lines), persona_lines))
checks.append(("coverage says solid/adequate/thin, not a bare number",
               re.search(r"\| coverage: (solid|adequate|thin|-|error)", iron3) is not None, iron3))

nomd = tmp / "nocontext"
(nomd / "personas").mkdir(parents=True)
(nomd / "personas/ghost.md").write_text(
    "---\nslug: ghost\nrole: CFO\n---\n## Red lines\n- none\n", encoding="utf-8")
r = run(HERE / "reindex.py", "--store", tmp)
checks.append(("a context without context.md is named out loud",
               "no context.md" in r.stderr, r.stderr))
checks.append(("a persona without cares_about is named out loud",
               "no `cares_about`" in r.stderr and "ghost.md" in r.stderr, r.stderr))
checks.append(("warnings alone do not change the exit code", r.returncode == 0, r.returncode))

# ---- Step 6 / FR-4.8: a block-list frontmatter is a warning here (not a failure) — the
# rest of the store's bookkeeping still runs.
(nomd / "personas/badfm.md").write_text(
    "---\nslug: badfm\nrole: y\naliases:\n- one\n- two\n---\n## Red lines\n- no evidence as of 2026-01-01\n",
    encoding="utf-8")
r_fm = run(HERE / "reindex.py", "--store", tmp)
checks.append(("reindex warns on a block-list frontmatter (FR-4.8), run not aborted",
               "badfm.md" in r_fm.stderr and "frontmatter outside the subset at line" in r_fm.stderr,
               r_fm.stderr))
checks.append(("reindex frontmatter warning does not change the exit code",
               r_fm.returncode == 0, r_fm.returncode))

r = run(HERE / "reindex.py", "--store", tmp, "--fail-on-gaps")
checks.append(("--fail-on-gaps exits 4", r.returncode == 4, r.returncode))

r = run(HERE / "log_flow.py", "review", "northwind", "--doc", "proposal-v2", "--store", tmp)
log = (tmp / "usage.jsonl").read_text().strip().splitlines()
checks.append(("usage log appended", len(log) == 1 and json.loads(log[0])["flow"] == "review", log))

# ---- Task 6: golden store (FR-2.4) — a complete, small store other tests/docs can point to
r = run(HERE / "reindex.py", "--store", tmp, "--context", "golden")
checks.append(("golden reindex: no warnings on stderr (beyond the direct-run deprecation line)",
               r.stderr == "deprecated: use beforehand.py reindex\n", r.stderr))
gidx = (tmp / "golden/INDEX.md").read_text()
checks.append(("golden index: astrid lints pass with 0 issues",
               re.search(r"^- cfo-astrid \|.*\| lint: pass \(0 issues\) \|", gidx, re.M) is not None, gidx))
checks.append(("golden index: jonas lints pass with 0 issues",
               re.search(r"^- cto-jonas \|.*\| lint: pass \(0 issues\) \|", gidx, re.M) is not None, gidx))
checks.append(("golden index: astrid and jonas coverage solid",
               len(re.findall(r"- (?:cfo-astrid|cto-jonas) \|.*\| coverage: solid \(", gidx)) == 2, gidx))
checks.append(("golden index: mira coverage thin, red lines and panel dynamics empty",
               re.search(r"- coo-mira \|.*\| coverage: thin \([^\n]*Red lines, Panel dynamics empty\)",
                         gidx) is not None, gidx))
r2 = run(HERE / "reindex.py", "--store", tmp, "--context", "golden")
checks.append(("golden reindex idempotent: second run only unchanged",
               "unchanged" in r2.stdout and "written" not in r2.stdout, r2.stdout))
checks.append(("golden index: no date embedded in the lint-root line itself",
               re.search(r"<!-- lint root: [^\n]*\d{4}-\d{2}-\d{2}", gidx) is None, gidx))
checks.append(("golden index: lint root is store-relative, no absolute machine path",
               "<!-- lint root: golden/sources -->" in gidx, gidx))
checks.append(("golden index: schema comment sits above the lint root line (FR-7.3)",
               re.search(r"<!-- schema: 0\.2 -->\n<!-- lint root: golden/sources -->", gidx)
               is not None, gidx[:400]))
checks.append(("golden index: the committed fixture already carries the schema comment",
               "<!-- schema: 0.2 -->" in (HERE / "test_fixtures/store/golden/INDEX.md")
               .read_text(encoding="utf-8"), "fixture index not regenerated"))

# ---- Step 5 (FR-4.7): deterministic index — re-running on an unchanged store must not
# touch the file just because the calendar date moved on. In-process, with reindex's own
# `_today` hook monkeypatched (never assert on the real today): two runs on two different
# mocked dates, nothing about the personas themselves changing, must be byte-identical.
sys.path.insert(0, str(HERE))
import datetime as _dt  # noqa: E402

import reindex as _rx  # noqa: E402

tmp2 = Path(tempfile.mkdtemp()) / "store"
shutil.copytree(HERE / "test_fixtures/store", tmp2)
(tmp2 / "golden/INDEX.md").unlink(missing_ok=True)  # start from no index at all
saved_today = _rx._today
try:
    # Both mocked dates are earlier than every golden persona's `updated:` field, so the
    # (also date-dependent) "stale since" suffix stays off in both runs — isolating the
    # thing this test is actually about (the regenerated-date stamp) from an unrelated,
    # correctly date-sensitive column.
    _rx._today = lambda: _dt.date(2020, 1, 1)
    rc1 = _rx.main(["--store", str(tmp2), "--context", "golden"])
    first = (tmp2 / "golden/INDEX.md").read_bytes()
    _rx._today = lambda: _dt.date(2021, 6, 15)
    rc2 = _rx.main(["--store", str(tmp2), "--context", "golden"])
    second = (tmp2 / "golden/INDEX.md").read_bytes()
finally:
    _rx._today = saved_today
checks.append(("deterministic index: both runs exit 0", rc1 == 0 and rc2 == 0, (rc1, rc2)))
checks.append(("deterministic index: last-regenerated stamped on first build",
               b"<!-- last regenerated: 2020-01-01 -->" in first, first[:400]))
checks.append(("deterministic index: unchanged personas -> byte-identical across two mocked todays",
               first == second, (len(first), len(second))))

r = run(HERE / "pending.py", "--store", tmp, "--context", "golden", "--json")
grows = json.loads(r.stdout)
checks.append(("golden pending: exactly one row", len(grows) == 1, grows))
g = grows[0] if grows else {}
checks.append(("golden pending: not overdue (meeting far in the future)", g.get("overdue") is False, g))
checks.append(("golden pending: two predictions to verify", g.get("predictions") == 2, g))
checks.append(("golden pending: decisions recorded via matching review report",
               g.get("decisions_recorded") is True, g))
checks.append(("golden pending: the document is found and unchanged (sha1 matches)",
               g.get("document_changed") is False, g))

# A relative `document:` is resolved against the snapshot's own context directory, not the
# process working directory: run from anywhere else, the same store must give the same
# verdict. Before this, `pending` reported None (document not found) from every cwd but the
# one the document happened to be relative to, and that flag feeds the calibration record.
elsewhere = tempfile.mkdtemp()
r = subprocess.run([sys.executable, str(HERE / "pending.py"), "--store", str(tmp),
                    "--context", "golden", "--json"],
                   capture_output=True, text=True, cwd=elsewhere)
g_elsewhere = (json.loads(r.stdout) or [{}])[0] if r.stdout.strip() else {}
checks.append(("golden pending: document_changed is False from an unrelated cwd too",
               g_elsewhere.get("document_changed") is False, (r.returncode, r.stdout, r.stderr)))

r = run(HERE / "coverage.py", str(tmp / "golden/personas/coo-mira.md"),
        "--audit", str(tmp / "golden/AUDIT.md"))
checks.append(("golden coverage: mira's empty sections are declared, not silent",
               "empty sections are declared, not silent" in r.stdout, r.stdout))

# ---- Task 17 / FR-6.3: a snapshot of a document extracted from a non-text file carries
# `original:` next to `document:`. Built in its own temp store, on a copy of the golden
# snapshot's header shape, so the committed fixture stays untouched.
tmp3 = Path(tempfile.mkdtemp()) / "store"
(tmp3 / "extracted/calibration").mkdir(parents=True)
golden_snap = (HERE / "test_fixtures/store/golden/calibration/pending-brief-q3.md").read_text(
    encoding="utf-8")
# Checked before the rewrite below: if the fixture's document line ever changes, this prints a
# named failure instead of a KeyError three checks later, on rows that were never rewritten.
checks.append(("fixture snapshot still carries the document: line these checks rewrite",
               "document: docs/brief-q3.md" in golden_snap, golden_snap[:120]))
(tmp3 / "extracted/calibration/pending-pitch.md").write_text(
    golden_snap.replace("document: docs/brief-q3.md",
                        "document: docs/pitch-extracted.md\noriginal: docs/pitch.odp"),
    encoding="utf-8")
(tmp3 / "extracted/calibration/pending-plain.md").write_text(golden_snap, encoding="utf-8")
r = run(HERE / "pending.py", "--store", tmp3, "--json")
erows = {x["document"]: x for x in json.loads(r.stdout)}
extracted, plain = erows.get("docs/pitch-extracted.md", {}), erows.get("docs/brief-q3.md", {})
checks.append(("original read from the snapshot into the row",
               extracted.get("original") == "docs/pitch.odp", erows))
checks.append(("document: still names the extracted text that was reviewed",
               extracted.get("document") == "docs/pitch-extracted.md", erows))
checks.append(("a snapshot without original: gets the key as null, not a missing key",
               "original" in plain and plain["original"] is None, plain))
h3 = run(HERE / "pending.py", "--store", tmp3)
checks.append(("human output names the original file when present",
               "original pitch.odp" in h3.stdout, h3.stdout))
checks.append(("human output says nothing about an original when absent",
               h3.stdout.count("original ") == 1, h3.stdout))

# ---- Task 17 / FR-6.1: the rehearse flow logs like any other flow, and its --doc is optional
# (a rehearsal may run with no agenda at all).
r = run(HERE / "log_flow.py", "rehearse", "northwind", "--store", tmp)
rows_log = [json.loads(ln) for ln in (tmp / "usage.jsonl").read_text().strip().splitlines()]
checks.append(("log rehearse without --doc exits 0", r.returncode == 0, (r.returncode, r.stderr)))
checks.append(("rehearse row appended with no doc key",
               rows_log[-1]["flow"] == "rehearse" and "doc" not in rows_log[-1], rows_log[-1]))

# ---- Task T2 / FR-1.1: the snapshot format, and the ledger that stands beside a pre-0.2 one
r = run(HERE / "pending.py", "--store", tmp, "--json")
by = {x["document"]: x for x in json.loads(r.stdout)}
checks.append(("a 0.2-shaped snapshot declares format 0.2",
               by["~/work/northwind/brief.md"]["format"] == "0.2", by["~/work/northwind/brief.md"]))
checks.append(("a header-only snapshot with no schema and no sections is pre-0.2",
               by["memo"]["format"] == "pre-0.2"
               and by["~/work/northwind/proposal-v2.md"]["format"] == "pre-0.2",
               [by["memo"]["format"], by["~/work/northwind/proposal-v2.md"]["format"]]))
checks.append(("a pre-0.2 row says so once, instead of listing symptoms",
               by["memo"]["warnings"] == ["pre-0.2 format, not gradeable"], by["memo"]))
checks.append(("no ledger next to it yet", by["memo"]["ledger"] is None, by["memo"]))
h = run(HERE / "pending.py", "--store", tmp)
checks.append(("the human line carries the format",
               any(ln.strip().endswith("pre-0.2") for ln in h.stdout.splitlines()), h.stdout))

# A reconstructed ledger next to it: the snapshot stays the record, the ledger supplies what
# the snapshot cannot state in a readable shape (FR-1.1).
led = tmp / "northwind/calibration/ledger-memo-nodate.md"
led.write_text("reconstructed: 2026-09-21\n"
               "snapshot sha1: " + "0" * 40 + "\n"
               "document: docs/memo.md\n"
               "frozen: 2026-06-01\n"
               "meeting: 2026-06-10\n"
               "\n## Predictions to verify\n"
               "- P1 | cto-mara | will ask who runs this | Recurring objections |\n",
               encoding="utf-8")
r = run(HERE / "pending.py", "--store", tmp, "--json")
by = {x["document"]: x for x in json.loads(r.stdout)}
memo_row = by.get("memo", {})
checks.append(("the ledger is named on the row", memo_row.get("ledger") == "ledger-memo-nodate.md",
               memo_row))
checks.append(("the snapshot still wins wherever it does say something: document stays its own",
               memo_row.get("document") == "memo", memo_row))
checks.append(("what the snapshot cannot say, the ledger says: meeting and predictions",
               memo_row.get("meeting") == "2026-06-10" and memo_row.get("predictions") == 1,
               memo_row))
checks.append(("the warning now says the ledger exists and when it was written",
               memo_row.get("warnings") == ["pre-0.2 format, ledger reconstructed 2026-09-21"],
               memo_row))
h = run(HERE / "pending.py", "--store", tmp)
checks.append(("the human line says the ledger is there",
               "pre-0.2 (ledger)" in h.stdout, h.stdout))
led.unlink()

# ---- 0.3.1 E5: `log` never glues a row onto a hand-edited last line without a newline
import contextlib  # noqa: E402
import io  # noqa: E402

import log_flow as _lf  # noqa: E402

e5 = Path(tempfile.mkdtemp()) / "store"
e5.mkdir(parents=True)
(e5 / "usage.jsonl").write_text('{"ts": "2026-09-01T10:00:00", "flow": "offer", "context": "c", '
                                '"doc": "d.md", "note": "offered"}', encoding="utf-8")
with contextlib.redirect_stdout(io.StringIO()):
    rc = _lf.main(["offer", "c", "--doc", "d.md", "--note", "declined", "--store", str(e5)])
rows = _lf.read_rows(e5)
checks.append(("E5: log after a line with no final newline keeps both rows",
               rc == 0 and [r.get("note") for r in rows] == ["offered", "declined"], rows))

# ---- 0.3.1 E7 (+S9): a one-context reindex never zeroes (or re-lints) the other contexts
e7 = Path(tempfile.mkdtemp()) / "store"
shutil.copytree(HERE / "test_fixtures/store", e7)
with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
    _rx.main(["--store", str(e7)])
root_full = (e7 / "INDEX.md").read_text(encoding="utf-8")
with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
    _rx.main(["--store", str(e7), "--context", "golden", "--no-lint"])
root_nolint = (e7 / "INDEX.md").read_text(encoding="utf-8")
checks.append(("E7: the full run counts ironbridge's failing persona",
               "[1 persona, 1 failing lint]" in root_full, root_full))
checks.append(("E7: `--no-lint --context golden` keeps ironbridge's failing count",
               "[1 persona, 1 failing lint]" in root_nolint, root_nolint))
# the counts come from the other context's INDEX.md, not from a re-lint of its personas
iron_idx = e7 / "ironbridge/INDEX.md"
iron_idx.write_text(iron_idx.read_text(encoding="utf-8").replace(
    "## Personas (1)", "## Personas (2)").rstrip("\n")
    + "\n", encoding="utf-8")
it = iron_idx.read_text(encoding="utf-8")
fail_line = next(ln for ln in it.splitlines() if "lint: fail" in ln)
iron_idx.write_text(it.replace(fail_line, fail_line + "\n" + fail_line.replace("coo-dana", "coo-dup")),
                    encoding="utf-8")
saved_lint_label = _rx.lint_label
linted = []


def _spy(path, *a, **kw):
    linted.append(Path(path).parent.parent.name)
    return saved_lint_label(path, *a, **kw)


_rx.lint_label = _spy
try:
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        _rx.main(["--store", str(e7), "--context", "golden"])
finally:
    _rx.lint_label = saved_lint_label
root_one = (e7 / "INDEX.md").read_text(encoding="utf-8")
checks.append(("E7: other contexts' counts are read from their INDEX.md (persona and lint: fail)",
               "- ironbridge — " in root_one and "[2 personas, 2 failing lint]" in root_one,
               root_one))
checks.append(("E7: a one-context reindex lints only that context",
               set(linted) == {"golden"}, sorted(set(linted))))

# ---- 0.3.1 E8: the staleness suffix is a date, so a stale store reindexes byte-identically
e8 = Path(tempfile.mkdtemp()) / "store"
shutil.copytree(HERE / "test_fixtures/store", e8)
outs = []
saved_today = _rx._today
try:
    for day in (_dt.date(2027, 3, 1), _dt.date(2027, 3, 2)):
        _rx._today = lambda day=day: day
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            _rx.main(["--store", str(e8), "--context", "golden"])
        outs.append((e8 / "golden/INDEX.md").read_bytes())
finally:
    _rx._today = saved_today
gtxt = outs[0].decode("utf-8")
checks.append(("E8: a stale persona carries `stale since YYYY-MM-DD` (first day past 180)",
               "| coo-mira |" not in gtxt and "- coo-mira |" in gtxt
               and "| stale since 2026-12-09" in gtxt and "| stale since 2026-12-18" in gtxt, gtxt))
checks.append(("E8: no day count in the suffix", "days since last update" not in gtxt, gtxt))
checks.append(("E8: two mocked stale days -> byte-identical INDEX", outs[0] == outs[1],
               (len(outs[0]), len(outs[1]))))

# ---- 0.3.1 E9: list-valued `updated:` is an item, `--pointer` without --context is usage
e9 = Path(tempfile.mkdtemp()) / "store"
shutil.copytree(HERE / "test_fixtures/store", e9)
mp = e9 / "northwind/personas/cto-mara.md"
mt = mp.read_text(encoding="utf-8")
mp.write_text(re.sub(r"(?m)^updated:.*$", "updated: [2026-01-01]", mt), encoding="utf-8")
r = run(HERE / "reindex.py", "--store", e9, "--context", "northwind")
checks.append(("E9: a list-valued updated: is no traceback", r.returncode == 0
               and "Traceback" not in r.stderr, (r.returncode, r.stderr[-300:])))
checks.append(("E9: ... it is reported as an incomplete input naming the file",
               "cto-mara.md" in r.stderr and "updated" in r.stderr, r.stderr[-300:]))
e9b = Path(tempfile.mkdtemp()) / "store"
shutil.copytree(HERE / "test_fixtures/store", e9b)
before_e9 = sorted(str(p.relative_to(e9b)) for p in e9b.rglob("*"))
r = run(HERE / "reindex.py", "--store", e9b, "--pointer", e9b.parent / "ptr.md")
checks.append(("E9: --pointer without --context exits 1 (usage)", r.returncode == 1,
               (r.returncode, r.stderr[-200:])))
checks.append(("E9: ... before anything is written",
               sorted(str(p.relative_to(e9b)) for p in e9b.rglob("*")) == before_e9
               and not (e9b.parent / "ptr.md").exists(), r.stdout[-300:]))

fails = [c for c in checks if not c[1]]
for n, ok, got in checks:
    print(("ok   " if ok else "FAIL ") + n + ("" if ok else f" -> {str(got)[:300]}"))
print(f"\n{len(checks)-len(fails)}/{len(checks)} passed")
sys.exit(1 if fails else 0)
