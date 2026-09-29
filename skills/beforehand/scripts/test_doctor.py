#!/usr/bin/env python3
"""Tests for doctor.py (FR-4.2) and for the offer ledger read mode of log_flow.py (FR-5.5).

Every doctor run passes `--today 2026-09-17` so that staleness never depends on the day the
suite happens to run, and every store a test mutates is a temporary copy: doctor is read-only
and the fixtures are shared with the other suites.
"""
import hashlib
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
DOCTOR = HERE / "doctor.py"
LOG = HERE / "log_flow.py"
ENTRY = HERE / "beforehand.py"
FIXTURE = HERE / "test_fixtures/store"
TODAY = "2026-09-17"
checks = []
TMP = Path(tempfile.mkdtemp())


def run(*a, **kw):
    cwd = kw.pop("cwd", None)
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.update(kw.pop("env_extra", None) or {})
    return subprocess.run([sys.executable, *map(str, a)], capture_output=True, text=True,
                          cwd=(str(cwd) if cwd else None), env=env)


def doctor(*a, **kw):
    return run(DOCTOR, "--today", TODAY, *a, **kw)


def last_line(out):
    lines = [ln for ln in out.strip().splitlines() if ln.strip()]
    return lines[-1] if lines else ""


def loads(out):
    try:
        return json.loads(out)
    except ValueError:
        return None


def state(root):
    """Digest of every file under root: proof that a command wrote nothing."""
    return {str(p.relative_to(root)): hashlib.sha1(p.read_bytes()).hexdigest()
            for p in sorted(Path(root).rglob("*")) if p.is_file()}


def copy_store(name, contexts):
    """A temp store with one copy of the golden context per requested name."""
    store = TMP / name
    store.mkdir(parents=True)
    for ctx in contexts:
        shutil.copytree(FIXTURE / "golden", store / ctx)
    return store


# ------------------------------------------------------------------ the golden store
r = doctor("--store", FIXTURE, "--context", "golden")
checks.append(("doctor on the golden context exits 0", r.returncode == 0, (r.returncode, r.stderr)))
checks.append(("golden store is healthy",
               last_line(r.stdout) == "doctor: healthy (3 of 3 personas checked)", r.stdout))
for token in ("context: golden", "personas", "snapshots", "gaps", "offers",
              "cfo-astrid", "coo-mira", "cto-jonas", "docs/brief-q3.md"):
    checks.append((f"human output carries {token!r}", token in r.stdout, r.stdout))

r = doctor("--store", FIXTURE, "--context", "golden", "--json")
data = loads(r.stdout) or {}
checks.append(("doctor --json exits 0 and parses", r.returncode == 0 and isinstance(data, dict),
               (r.returncode, r.stdout[:200], r.stderr)))
personas = data.get("personas", [])
checks.append(("json lists the three golden personas", len(personas) == 3, personas))
checks.append(("every persona row carries a coverage verdict",
               bool(personas) and all(p.get("coverage") for p in personas),
               [p.get("coverage") for p in personas]))
checks.append(("every persona row carries a lint label",
               bool(personas) and all(p.get("lint_status") == "pass" for p in personas),
               [p.get("lint") for p in personas]))
checks.append(("every golden persona declares the current schema",
               bool(personas) and all(p.get("schema") == "0.2" for p in personas),
               [p.get("schema") for p in personas]))
checks.append(("no golden persona has a stale or undated section",
               bool(personas) and all(p.get("stale_sections") == [] for p in personas),
               [p.get("stale_sections") for p in personas]))
snaps = data.get("snapshots", [])
checks.append(("json lists the golden snapshot as upcoming",
               len(snaps) == 1 and snaps[0].get("status") == "upcoming", snaps))
checks.append(("golden snapshot records the user decisions",
               bool(snaps) and snaps[0].get("decisions_recorded") is True, snaps))
checks.append(("golden has no gaps", data.get("gaps") == [], data.get("gaps")))
checks.append(("golden has no offers pending", data.get("offers") == [], data.get("offers")))
checks.append(("golden has no items", data.get("items") == [], data.get("items")))
checks.append(("json mirrors the pinned summary line",
               data.get("summary") == "doctor: healthy (3 of 3 personas checked)", data.get("summary")))
checks.append(("json echoes the --today used for staleness", data.get("today") == TODAY,
               data.get("today")))

# the whole fixture store (three contexts) is a report too, never an error
r = doctor("--store", FIXTURE)
checks.append(("doctor over every context exits 0", r.returncode == 0, (r.returncode, r.stderr)))
summary = last_line(r.stdout)
checks.append(("summary line has the pinned shape",
               summary.endswith(" personas checked)") and
               (summary.startswith("doctor: healthy (") or
                re.match(r"doctor: \d+ items need attention \(", summary) is not None),
               summary))

# ------------------------------------------------------------------ staleness is dated
# Same store, a later --today: the fast-decay sections cross 180 days and become items.
r = doctor("--store", FIXTURE, "--context", "golden", "--today", "2027-06-01", "--json")
data = loads(r.stdout) or {}
stale_items = [i for i in data.get("items", []) if i["kind"] == "staleness"]
checks.append(("a later --today makes the fast-decay sections stale",
               r.returncode == 0 and len(stale_items) > 0 and
               all(i["kind"] == "staleness" for i in data.get("items", [])),
               data.get("items")))
checks.append(("stale item names the section and the age",
               any("Mandate and incentives" in i["message"] and "391" in i["message"]
                   for i in stale_items), [i["message"] for i in stale_items]))
checks.append(("a section that never decays is never stale",
               not any("Language and dissent style" in i["message"] for i in stale_items),
               [i["message"] for i in stale_items]))

# ------------------------------------------------------------------ doctor never writes
ro = copy_store("readonly", ["golden"])
before = state(ro)
doctor("--store", ro)
doctor("--store", ro, "--json")
checks.append(("doctor writes nothing", state(ro) == before, "store changed"))

# ------------------------------------------------------------------ five items, five findings
store5 = copy_store("store5", ["golden", "second"])

p = store5 / "golden/personas/cfo-astrid.md"
p.write_text("\n".join(ln for ln in p.read_text(encoding="utf-8").splitlines()
                       if not ln.startswith("cares_about:")) + "\n", encoding="utf-8")
(store5 / "second/context.md").unlink()
s = store5 / "golden/calibration/pending-brief-q3.md"
s.write_text(s.read_text(encoding="utf-8").replace("meeting: 2099-01-15", "meeting: unknown"),
             encoding="utf-8")
m = store5 / "golden/personas/coo-mira.md"
m.write_text(m.read_text(encoding="utf-8").replace(
    "## Panel dynamics <!-- last evidence: 2026-06-20 | decays fast -->", "## Panel dynamics"),
    encoding="utf-8")
(store5 / "usage.jsonl").write_text("".join(json.dumps(row) + "\n" for row in [
    {"ts": "2026-09-10T09:00:00", "flow": "offer", "context": "golden",
     "doc": "docs/brief-q3.md", "note": "offered"},
    {"ts": "2026-09-11T09:00:00", "flow": "offer", "context": "golden",
     "doc": "sources/2026-06-11-steering.txt", "note": "offered"},
    {"ts": "2026-09-11T10:00:00", "flow": "offer", "context": "golden",
     "doc": "sources/2026-06-11-steering.txt", "note": "declined"},
    {"ts": "2026-09-12T09:00:00", "flow": "review", "context": "golden",
     "doc": "docs/brief-q3.md"},
]), encoding="utf-8")

r = doctor("--store", store5)
checks.append(("the modified store exits 0 like any report", r.returncode == 0,
               (r.returncode, r.stderr)))
checks.append(("five items need attention",
               last_line(r.stdout) == "doctor: 5 items need attention (6 of 6 personas checked)",
               r.stdout))

r = doctor("--store", store5, "--json")
data = loads(r.stdout) or {}
items = data.get("items", [])
checks.append(("json reports the same five items", len(items) == 5, items))
checks.append(("one item per finding, with the pinned kinds",
               sorted(i["kind"] for i in items) ==
               ["gap", "gap", "offer", "snapshot", "staleness"],
               sorted(i.get("kind") for i in items)))


def item(kind, needle):
    return next((i for i in items if i["kind"] == kind and needle in i["message"]), None)


it = item("gap", "cares_about")
checks.append(("the persona without cares_about is a gap",
               it is not None and it["file"].endswith("cfo-astrid.md")
               and it["context"] == "golden", it))
it = item("gap", "context.md")
checks.append(("the context without context.md is a gap",
               it is not None and it["context"] == "second", it))
it = item("snapshot", "meeting")
checks.append(("the snapshot without a meeting date is a snapshot item",
               it is not None and it["context"] == "golden", it))
checks.append(("and that item now names the command that records the date (FR-1.2)",
               it is not None
               and it["message"].endswith("— record it: beforehand.py pending --context golden "
                                          "--set-meeting brief-q3 YYYY-MM-DD"), it))
it = item("staleness", "Panel dynamics")
checks.append(("the heading without a last evidence note is unknown staleness",
               it is not None and "unknown" in it["message"]
               and it["file"].endswith("coo-mira.md"), it))
it = item("offer", "docs/brief-q3.md")
checks.append(("the offer with no follow-up is an offer item", it is not None, it))
checks.append(("an offer answered by a later declined is not listed",
               not any("steering" in i["message"] for i in items),
               [i["message"] for i in items]))
checks.append(("item files are store-relative, never absolute",
               all(not i["file"].startswith("/") for i in items), [i["file"] for i in items]))
checks.append(("the json gaps list mirrors the structural findings",
               len(data.get("gaps", [])) == 2, data.get("gaps")))
checks.append(("the json offers list carries the open offer",
               len(data.get("offers", [])) == 1
               and data["offers"][0].get("doc") == "docs/brief-q3.md", data.get("offers")))
checks.append(("--context narrows the report to one context",
               (loads(doctor("--store", store5, "--context", "second", "--json").stdout) or {})
               .get("items", []) and
               all(i["context"] == "second" for i in
                   (loads(doctor("--store", store5, "--context", "second", "--json").stdout)
                    or {}).get("items", [])), "context filter"))

# ------------------------------------------------------------------ a failing linter
# A persona whose excerpt is not in the source it cites is what the panel gate refuses:
# doctor may never call that store healthy, so it is a gap like any other structural fault.
store_lint = copy_store("store_lint", ["golden"])
p = store_lint / "golden/personas/cfo-astrid.md"
p.write_text(p.read_text(encoding="utf-8").replace(
    "the board holds me to gross margin per lane, not revenue growth",
    "the board holds me to a number nobody ever said out loud", 1), encoding="utf-8")
r = doctor("--store", store_lint, "--json")
data = loads(r.stdout) or {}
items = data.get("items", [])
row = next((x for x in data.get("personas", []) if x["slug"] == "cfo-astrid"), {})
checks.append(("a failing lint is one more item on an otherwise healthy store",
               r.returncode == 0 and len(items) == 1 and items[0]["kind"] == "gap"
               and "lint fail" in items[0]["message"]
               and items[0]["file"].endswith("cfo-astrid.md"), items))
checks.append(("the failing persona still carries its lint label in the table",
               row.get("lint_status") == "fail" and row.get("lint", "").startswith("fail"),
               row.get("lint")))
checks.append(("a store with a failing persona is never healthy",
               last_line(doctor("--store", store_lint).stdout)
               == "doctor: 1 items need attention (3 of 3 personas checked)",
               doctor("--store", store_lint).stdout))
checks.append(("lint warn and thin coverage stay informational",
               all("lint warn" not in i["message"] for i in
                   (loads(doctor("--store", store5, "--json").stdout) or {}).get("items", [])),
               "warn counted"))

# ------------------------------------------------------------------ nothing is counted unseen
# An item can name a context that has no directory: an offer logged against a context that
# was never created still has to be printed, or the count has no lines behind it.
store_ghost = TMP / "store_ghost"
store_ghost.mkdir()
(store_ghost / "usage.jsonl").write_text(json.dumps(
    {"ts": "2026-09-10T09:00:00", "flow": "offer", "context": "ghost", "doc": "brief.md",
     "note": "offered"}) + "\n", encoding="utf-8")
r = doctor("--store", store_ghost)
checks.append(("an offer for a context with no directory is counted",
               last_line(r.stdout) == "doctor: 1 items need attention (0 of 0 personas checked)",
               r.stdout))
checks.append(("and it is printed, not only counted",
               "ghost" in r.stdout and "brief.md" in r.stdout, r.stdout))
r5 = doctor("--store", store5)
checks.append(("the roll-up prints one line per item, count included",
               "items needing attention (5)" in r5.stdout and
               len([ln for ln in r5.stdout.splitlines()
                    if ln.startswith("    - ") and " | " in ln]) >= 5, r5.stdout))

# ------------------------------------------------------------------ a store or context that is not there
r = doctor("--store", TMP / "no-such-store-at-all")
checks.append(("a store that does not exist is never healthy",
               r.returncode == 0
               and last_line(r.stdout) == "doctor: 1 items need attention (0 of 0 personas checked)",
               (r.returncode, r.stdout)))
data = loads(doctor("--store", TMP / "no-such-store-at-all", "--json").stdout) or {}
checks.append(("the missing store is one gap item",
               len(data.get("items", [])) == 1 and data["items"][0]["kind"] == "gap"
               and data["items"][0]["message"].startswith("store not found:"),
               data.get("items")))
r = doctor("--store", FIXTURE, "--context", "no-such-context")
checks.append(("a context that does not exist is never healthy",
               r.returncode == 0
               and last_line(r.stdout) == "doctor: 1 items need attention (0 of 0 personas checked)",
               (r.returncode, r.stdout)))
data = loads(doctor("--store", FIXTURE, "--context", "no-such-context", "--json").stdout) or {}
checks.append(("the missing context is one gap item naming it",
               len(data.get("items", [])) == 1 and data["items"][0]["kind"] == "gap"
               and data["items"][0]["message"] == "context not found: no-such-context",
               data.get("items")))

# ------------------------------------------------------------------ schema behind current
store_s = copy_store("store_schema", ["golden"])
p = store_s / "golden/personas/cto-jonas.md"
p.write_text(p.read_text(encoding="utf-8").replace("schema: 0.2", "schema: 0.1"), encoding="utf-8")
c = store_s / "golden/context.md"
c.write_text("\n".join(ln for ln in c.read_text(encoding="utf-8").splitlines()
                       if ln.strip() != "schema: 0.2") + "\n", encoding="utf-8")
r = doctor("--store", store_s, "--json")
data = loads(r.stdout) or {}
items = data.get("items", [])
checks.append(("a schema behind current and a missing schema are two schema items",
               len(items) == 2 and all(i["kind"] == "schema" for i in items), items))
checks.append(("the schema item names the version and the remedy",
               any("schema 0.1" in i["message"] and "run migrate" in i["message"] for i in items)
               and any("schema none" in i["message"] for i in items),
               [i.get("message") for i in items]))
checks.append(("the schema store reports two items",
               last_line(doctor("--store", store_s).stdout)
               == "doctor: 2 items need attention (3 of 3 personas checked)",
               doctor("--store", store_s).stdout))

# ------------------------------------------------------------------ frontmatter outside the subset
store_f = copy_store("store_fm", ["golden"])
p = store_f / "golden/personas/coo-mira.md"
p.write_text(p.read_text(encoding="utf-8").replace(
    "schema: 0.2\n---", "schema: 0.2\nextra:\n  - a\n---", 1), encoding="utf-8")
r = doctor("--store", store_f, "--json")
data = loads(r.stdout) or {}
items = data.get("items", [])
checks.append(("frontmatter outside the FR-4.8 subset is one gap, not a crash",
               r.returncode == 0 and len(items) == 1 and items[0]["kind"] == "gap"
               and "frontmatter outside the subset at line" in items[0]["message"], items))
# the block list item sits two lines below `schema:` (line 12 of coo-mira.md), i.e. line 14
checks.append(("the frontmatter gap names the offending line number",
               bool(items) and "line 14" in items[0]["message"], items))

# ------------------------------------------------------------------ the document changed
store_d = copy_store("store_doc", ["golden"])
doc = store_d / "golden/docs/brief-q3.md"
doc.write_text(doc.read_text(encoding="utf-8") + "\nA paragraph added after the snapshot.\n",
               encoding="utf-8")
r = doctor("--store", store_d, "--json", cwd=store_d / "golden")
data = loads(r.stdout) or {}
items = data.get("items", [])
checks.append(("a document changed since its snapshot is a snapshot item",
               r.returncode == 0 and len(items) == 1 and items[0]["kind"] == "snapshot"
               and "changed" in items[0]["message"], items))

# ------------------------------------------------------------------ registration in beforehand.py
r = run(ENTRY, "--store", FIXTURE, "doctor", "--context", "golden", "--today", TODAY)
checks.append(("beforehand.py doctor exits 0", r.returncode == 0, (r.returncode, r.stderr)))
checks.append(("beforehand.py doctor prints the pinned summary",
               last_line(r.stdout) == "doctor: healthy (3 of 3 personas checked)", r.stdout))
r = run(ENTRY, "--help")
checks.append(("--help no longer defers doctor to a later task",
               "doctor" in r.stdout and "doctor" not in
               "".join(ln for ln in r.stdout.splitlines() if "not available" in ln), r.stdout))

# ------------------------------------------------------------------ log: the offer ledger
store_l = TMP / "store_log"
store_l.mkdir()
rows = [
    {"ts": "2026-09-01T09:00:00", "flow": "review", "context": "golden", "doc": "a.md"},
    {"ts": "2026-09-02T09:00:00", "flow": "offer", "context": "golden", "doc": "b.md",
     "note": "offered"},
    {"ts": "2026-09-03T09:00:00", "flow": "offer", "context": "other", "doc": "c.md",
     "note": "declined"},
    {"ts": "2026-09-04T09:00:00", "flow": "consult", "context": "golden", "doc": "d.md"},
    {"ts": "2026-09-05T09:00:00", "flow": "offer", "context": "golden", "doc": "e.md",
     "note": "accepted"},
]
(store_l / "usage.jsonl").write_text("".join(json.dumps(x) + "\n" for x in rows), encoding="utf-8")
before = state(store_l)

r = run(LOG, "--last", "5", "--flow", "offer", "--json", "--store", store_l)
out = loads(r.stdout)
checks.append(("log --last --flow offer --json exits 0 and parses",
               r.returncode == 0 and isinstance(out, list), (r.returncode, r.stdout, r.stderr)))
checks.append(("log --last --flow offer returns only offer rows",
               out is not None and len(out) == 3 and all(x["flow"] == "offer" for x in out), out))
checks.append(("log --last reads, it never writes", state(store_l) == before, "log wrote"))

r = run(LOG, "--last", "2", "--json", "--store", store_l)
out = loads(r.stdout)
checks.append(("log --last N returns the tail, newest last",
               out is not None and len(out) == 2 and out[-1]["doc"] == "e.md", out))

r = run(LOG, "--last", "10", "--flow", "offer", "--context", "other", "--json", "--store", store_l)
out = loads(r.stdout)
checks.append(("log --last --context filters by context",
               out is not None and len(out) == 1 and out[0]["doc"] == "c.md", out))

r = run(LOG, "--last", "10", "--flow", "offer", "--store", store_l)
checks.append(("log --last without --json prints one line per row",
               r.returncode == 0 and len([ln for ln in r.stdout.splitlines() if ln.strip()]) == 3
               and "offered" in r.stdout, r.stdout))

r = run(LOG, "--last", "5", "--json", "--store", TMP / "no-such-store")
out = loads(r.stdout)
checks.append(("log --last on a store with no usage log is an empty report",
               r.returncode == 0 and out == [], (r.returncode, r.stdout)))

r = run(LOG, "offer", "golden", "--doc", "b.md", "--note", "sometimes", "--store", store_l)
checks.append(("an unknown note on the offer flow is a usage error (exit 1)",
               r.returncode == 1, (r.returncode, r.stderr)))
checks.append(("the usage error names the three pinned notes",
               all(w in r.stderr for w in ("offered", "accepted", "declined")), r.stderr))
checks.append(("the refused offer wrote nothing", state(store_l) == before, "log wrote"))

r = run(LOG, "offer", "golden", "--doc", "b.md", "--note", "accepted", "--store", store_l)
checks.append(("a pinned note on the offer flow is logged", r.returncode == 0,
               (r.returncode, r.stderr)))
tail = json.loads((store_l / "usage.jsonl").read_text(encoding="utf-8").strip().splitlines()[-1])
checks.append(("the logged offer row carries flow, doc and note",
               tail["flow"] == "offer" and tail["doc"] == "b.md" and tail["note"] == "accepted",
               tail))

undocumented_before = state(store_l)
r = run(LOG, "offer", "golden", "--note", "offered", "--store", store_l)
checks.append(("an offer with no --doc is a usage error (exit 1)", r.returncode == 1,
               (r.returncode, r.stderr)))
checks.append(("the offer with no --doc wrote nothing",
               state(store_l) == undocumented_before, "log wrote"))
checks.append(("the usage error names --doc", "--doc" in r.stderr, r.stderr))

r = run(LOG, "review", "golden", "--doc", "a.md", "--store", store_l)
checks.append(("an ordinary flow still logs without a note", r.returncode == 0,
               (r.returncode, r.stderr)))
r = run(LOG, "--store", store_l)
checks.append(("log with neither --last nor a flow is a usage error (exit 1)",
               r.returncode == 1, (r.returncode, r.stderr)))

r = run(ENTRY, "--store", store_l, "log", "--last", "3", "--flow", "offer", "--json")
out = loads(r.stdout)
checks.append(("beforehand.py log --last reads the store's ledger",
               r.returncode == 0 and isinstance(out, list) and all(x["flow"] == "offer" for x in out),
               (r.returncode, r.stdout, r.stderr)))

# ---- a lint that could not run at all is an item with its reason, not silence. In process
# and monkeypatched: the only way to make the linter crash on a well-formed store is to make
# it raise, and the point of the check is that `doctor: healthy` can no longer be printed
# over a check that never produced an answer.
sys.path.insert(0, str(HERE))
import datetime as dt  # noqa: E402

import doctor as doc  # noqa: E402

store_err = copy_store("lint-error", ["golden"])
saved_lint = doc._vq.lint_persona


def _boom(*_a, **_kw):
    raise RuntimeError("boom")


try:
    doc._vq.lint_persona = _boom
    rep_err = doc.scan(store_err, today=dt.date(2026, 9, 17))
finally:
    doc._vq.lint_persona = saved_lint
err_msgs = [i["message"] for i in rep_err["items"]]
checks.append(("a lint that crashed is reported as an item carrying the exception text",
               any("lint error (RuntimeError: boom)" in m for m in err_msgs), err_msgs))
checks.append(("a store whose lint crashed is not healthy",
               not rep_err["summary"].startswith("doctor: healthy"), rep_err["summary"]))
checks.append(("the persona row records lint_status 'error'",
               bool(rep_err["personas"])
               and all(p.get("lint_status") == "error" for p in rep_err["personas"]),
               [p.get("lint_status") for p in rep_err["personas"]]))
checks.append(("the golden store still reads healthy once the linter is restored",
               doc.scan(FIXTURE, only_context="golden",
                        today=dt.date(2026, 9, 17))["summary"] == "doctor: healthy (3 of 3 personas checked)",
               doc.scan(FIXTURE, only_context="golden", today=dt.date(2026, 9, 17))["summary"]))

# ---- and the same for coverage: it set the column to `error` but appended no item, so
# `doctor: healthy` printed over a crashed check — the first command every flow runs.
store_cov = copy_store("coverage-error", ["golden"])
saved_cov = doc._cov.assess
try:
    doc._cov.assess = _boom
    rep_cov = doc.scan(store_cov, today=dt.date(2026, 9, 17))
finally:
    doc._cov.assess = saved_cov
cov_msgs = [i["message"] for i in rep_cov["items"]]
checks.append(("a coverage check that crashed is reported as an item carrying the exception "
               "text", any("coverage error (RuntimeError: boom)" in m for m in cov_msgs),
               cov_msgs))
checks.append(("a store whose coverage check crashed is not healthy",
               not rep_cov["summary"].startswith("doctor: healthy"), rep_cov["summary"]))
checks.append(("the persona row records coverage 'error'",
               bool(rep_cov["personas"])
               and all(p.get("coverage_level") == "error" for p in rep_cov["personas"]),
               [p.get("coverage_level") for p in rep_cov["personas"]]))

# ---- the linter is checked before it is trusted: a canary with one quote its source holds
# and one it does not goes through the same call as every persona, before any of them. Five
# profiles once read "all good" for two weeks because the parser skipped a tag form it did
# not know and "found nothing to check" became "found nothing wrong". A parser fix proves
# the formats someone thought of; a quote known to be wrong proves the checker still looks.
rep_ok = doc.scan(FIXTURE, only_context="golden", today=dt.date(2026, 9, 17))
sc = rep_ok.get("lint_selfcheck") or {}
checks.append(("self-check: on a working linter the canary comes back VERIFIED, NOT FOUND",
               sc.get("ok") is True and sc.get("got") == ["VERIFIED", "NOT FOUND"], sc))
checks.append(("self-check: the json carries the count behind the summary",
               rep_ok.get("personas_total") == 3 and rep_ok.get("personas_checked") == 3,
               (rep_ok.get("personas_total"), rep_ok.get("personas_checked"))))
checks.append(("self-check: the golden summary states 3 of 3",
               rep_ok["summary"] == "doctor: healthy (3 of 3 personas checked)", rep_ok["summary"]))

SELFCHECK_PINNED = ("lint self-check: expected VERIFIED, NOT FOUND, got VERIFIED, VERIFIED — the "
                    "linter is broken, so no lint verdict in this report can be trusted")


def _passes_everything(*_a, **_kw):
    """A linter that never refuses a quote: the failure the canary exists for."""
    return {"results": [{"status": "VERIFIED"}, {"status": "VERIFIED"}], "status": "pass",
            "label": "pass (0 issues)"}


def _refuses_everything(*_a, **_kw):
    """A linter that reads every source as empty: `fail` on the canary is not enough."""
    return {"results": [{"status": "NOT FOUND"}, {"status": "NOT FOUND"}], "status": "fail",
            "label": "fail (2 not found)"}


store_pass = copy_store("lint-passes-everything", ["golden"])
try:
    doc._vq.lint_persona = _passes_everything
    rep_pass = doc.scan(store_pass, today=dt.date(2026, 9, 17))
finally:
    doc._vq.lint_persona = saved_lint
pass_items = [i for i in rep_pass["items"] if i["message"].startswith("lint self-check")]
checks.append(("self-check: a linter that passes the wrong quote is one gap item, pinned text",
               len(pass_items) == 1 and pass_items[0]["kind"] == "gap"
               and pass_items[0]["message"] == SELFCHECK_PINNED, rep_pass["items"]))
checks.append(("self-check: a store whose linter passes everything is never healthy",
               not rep_pass["summary"].startswith("doctor: healthy"), rep_pass["summary"]))
checks.append(("self-check: every persona still shows the (worthless) verdict in its row",
               all(p["lint_status"] == "pass" for p in rep_pass["personas"]),
               [p["lint_status"] for p in rep_pass["personas"]]))
checks.append(("self-check: but the count says 0 of 3 were checked",
               rep_pass["personas_checked"] == 0 and rep_pass["personas_total"] == 3
               and rep_pass["summary"].endswith("(0 of 3 personas checked)"), rep_pass["summary"]))
checks.append(("self-check: it is a gap, no new kind was invented for it",
               all(i["kind"] in doc.KINDS for i in rep_pass["items"]),
               [i["kind"] for i in rep_pass["items"]]))

try:
    doc._vq.lint_persona = _refuses_everything
    rep_refuse = doc.scan(store_pass, today=dt.date(2026, 9, 17))
finally:
    doc._vq.lint_persona = saved_lint
checks.append(("self-check: a linter that refuses the true quote too is broken as well",
               any("got NOT FOUND, NOT FOUND" in i["message"] for i in rep_refuse["items"])
               and rep_refuse["personas_checked"] == 0, rep_refuse["items"]))

# the canary and the personas share one call: a fake put on `lint_one` reaches both
saved_one = doc.lint_one
try:
    doc.lint_one = _passes_everything
    rep_one = doc.scan(store_pass, today=dt.date(2026, 9, 17))
finally:
    doc.lint_one = saved_one
checks.append(("self-check: the canary goes through lint_one, the same call as the personas",
               any(i["message"] == SELFCHECK_PINNED for i in rep_one["items"])
               and all(p["lint"] == "pass (0 issues)" for p in rep_one["personas"]),
               (rep_one["items"], [p["lint"] for p in rep_one["personas"]])))

# a linter that crashed on the canary is reported as such, on top of the per-persona items
checks.append(("self-check: a linter that raises fails the self-check with the exception text",
               any(m.startswith("lint self-check: expected VERIFIED, NOT FOUND, got error "
                                "(RuntimeError: boom)") for m in err_msgs), err_msgs))
checks.append(("self-check: and the count under a crashed linter is 0 of 3",
               rep_err["personas_checked"] == 0 and rep_err["summary"].endswith(
                   "(0 of 3 personas checked)"), rep_err["summary"]))
checks.append(("self-check: the linter restored, the golden context is 3 of 3 again",
               doc.scan(FIXTURE, only_context="golden", today=dt.date(2026, 9, 17))["summary"]
               == "doctor: healthy (3 of 3 personas checked)", None))
checks.append(("self-check: doctor still writes nothing into the store",
               state(store_pass) == state(copy_store("lint-untouched", ["golden"])),
               "store changed"))

# ------------------------------------------------------- FR-1.1: a pre-0.2 snapshot is named
# A snapshot frozen before the 0.2 shape existed used to be reported only through its
# consequences (no meeting date, dangling P<k>); it is now one item with one remedy, and the
# item goes away once the ledger that brings it back into the log is there.
pre = copy_store("pre02", ["golden"])
snap02 = pre / "golden/calibration/pending-brief-q3.md"
snap02.write_text("# Prediction snapshot - brief-q3\n\n"
                  "Document reviewed: docs/brief-q3.md\n"
                  "Frozen on: the twenty-fifth of June\n"
                  "Meeting expected: the fifteenth of January\n\n"
                  "### P1 - a named reconciliation baseline\n"
                  "cfo-astrid will ask for one before the next round.\n",
                  encoding="utf-8")
r = doctor("--store", pre, "--json")
data = loads(r.stdout) or {}
snap_items = [i for i in data.get("items", []) if i["kind"] == "snapshot"]
checks.append(("a pre-0.2 snapshot is reported as such, with the command that fixes it",
               any("pre-0.2 format, not gradeable" in i["message"]
                   and "calibrate --ledger" in i["message"] for i in snap_items), snap_items))
checks.append(("it is a snapshot item: no new kind was invented for it",
               all(i["kind"] in doc.KINDS for i in data.get("items", [])),
               [i["kind"] for i in data.get("items", [])]))
checks.append(("the date remedy still fires on top: two findings, two remedies",
               any("--set-meeting" in i["message"] for i in snap_items), snap_items))
checks.append(("the snapshot row carries the format",
               [s.get("format") for s in data.get("snapshots", [])] == ["pre-0.2"],
               data.get("snapshots")))

(pre / "golden/calibration/ledger-brief-q3.md").write_text(
    "reconstructed: 2026-09-21\nsnapshot sha1: " + "0" * 40 + "\n"
    "frozen: 2026-06-25\nmeeting: 2099-01-15\n"
    "\n## Predictions to verify\n- P1 | cfo-astrid | will ask for a baseline | Recurring "
    "objections |\n", encoding="utf-8")
r = doctor("--store", pre, "--json")
data = loads(r.stdout) or {}
checks.append(("once a ledger exists, the format item is gone",
               not any("pre-0.2 format, not gradeable" in i["message"]
                       for i in data.get("items", [])), data.get("items")))
checks.append(("and the ledger's date is what the snapshot row reports",
               [s.get("meeting") for s in data.get("snapshots", [])] == ["2099-01-15"],
               data.get("snapshots")))
checks.append(("doctor still writes nothing while reading a ledger",
               doctor("--store", pre).returncode == 0, "doctor failed"))

checks.append(("the golden fixture itself is 0.2-shaped, so none of this touches it",
               doc.scan(FIXTURE, only_context="golden",
                        today=dt.date(2026, 9, 17))["summary"] == "doctor: healthy (3 of 3 personas checked)",
               doc.scan(FIXTURE, only_context="golden",
                        today=dt.date(2026, 9, 17))["summary"]))

# ---- 0.3.1 E4: a snapshot scan that crashes is an item carrying its reason, never silence.
# One unreadable snapshot used to turn "2 items need attention" into "doctor: healthy".
store_snap = copy_store("snap-error", ["golden"])
saved_scan = doc._pending.scan


def _snap_boom(*_a, **_kw):
    raise OSError("pending-zz.md: permission denied")


try:
    doc._pending.scan = _snap_boom
    rep = doc.scan(store_snap, only_context="golden", today=dt.date(2026, 9, 17))
finally:
    doc._pending.scan = saved_scan
snap_items = [i for i in rep["items"] if "snapshot" in i["message"] and "OSError" in i["message"]]
checks.append(("E4: a crashed snapshot scan is an item, not a stderr warning",
               len(snap_items) == 1 and "permission denied" in snap_items[0]["message"],
               rep["items"]))
checks.append(("E4: doctor is not healthy over a crashed snapshot scan",
               not rep["summary"].startswith("doctor: healthy"), rep["summary"]))

# ---- 0.3.1 E4 (with FR-3.7): pending.scan skips an unreadable snapshot with a per-file
# stderr warning instead of raising, and reports it through its `unreadable` list; doctor
# turns each entry into an item, so the skip can
# never read as a clean snapshot column.
def _snap_warn(*_a, **kw):
    print("warning: golden/calibration/pending-zz.md: unreadable (PermissionError)",
          file=sys.stderr)
    kw["unreadable"].append({"file": "golden/calibration/pending-zz.md",
                             "error": "PermissionError"})
    return []


import contextlib  # noqa: E402
import io  # noqa: E402

try:
    doc._pending.scan = _snap_warn
    with contextlib.redirect_stderr(io.StringIO()):
        rep = doc.scan(store_snap, only_context="golden", today=dt.date(2026, 9, 17))
finally:
    doc._pending.scan = saved_scan
warn_items = [i for i in rep["items"] if "pending-zz.md" in i["message"]]
checks.append(("E4: a snapshot pending.scan skipped as unreadable is an item",
               len(warn_items) == 1 and warn_items[0]["kind"] == "snapshot"
               and "unreadable (PermissionError)" in warn_items[0]["message"], rep["items"]))

# ---- 0.3.1 E9 (locale): an unknown BEFOREHAND_LOCALE is ONE item, checked up front; the
# locale-dependent checks are skipped instead of each failing once per persona. Exit 0 kept.
r = run(DOCTOR, "--today", TODAY, "--store", FIXTURE, "--json",
        env_extra={"BEFOREHAND_LOCALE": "zz"})
rep = loads(r.stdout) or {}
loc = [i for i in rep.get("items", []) if i["message"].startswith("locale: ")]
checks.append(("locale: doctor still exits 0 under an unknown locale", r.returncode == 0,
               (r.returncode, r.stderr[-300:])))
checks.append(("locale: exactly one `locale: <message>` item",
               len(loc) == 1 and "zz" in loc[0]["message"], rep.get("items")))
checks.append(("locale: no per-persona LocaleError items",
               not [i for i in rep.get("items", []) if "LocaleError" in i["message"]],
               [i["message"] for i in rep.get("items", []) if "LocaleError" in i["message"]]))
r = run(DOCTOR, "--today", TODAY, "--store", FIXTURE, env_extra={"BEFOREHAND_LOCALE": "zz"})
checks.append(("locale: the human report ends on the pinned line and shows the item",
               last_line(r.stdout).startswith("doctor: ") and "locale: " in r.stdout,
               r.stdout[-400:]))
checks.append(("locale: with lint skipped, the count says 0 of 5 personas checked",
               last_line(r.stdout).endswith("(0 of 5 personas checked)"), last_line(r.stdout)))

shutil.rmtree(TMP, ignore_errors=True)

fails = [c for c in checks if not c[1]]
for name, ok, got in checks:
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  -> got {got!r}"))
print(f"\n{len(checks) - len(fails)}/{len(checks)} passed")
sys.exit(1 if fails else 0)
