#!/usr/bin/env python3
"""Tests for forget.py (FR-7.4): removing one person from a store, audited.

The acceptance of FR-7.4 is a grep: after `forget <slug> --apply`, the only place the slug
still appears anywhere under the store is the one AUDIT line that records the removal. Every
test runs on a temporary copy of the golden fixture store.
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
FORGET = HERE / "forget.py"
LOG = HERE / "log_flow.py"
ENTRY = HERE / "beforehand.py"
FIXTURE = HERE / "test_fixtures/store"
GOLDEN = FIXTURE / "golden"
TMP = Path(tempfile.mkdtemp())
checks = []


def run(*a, **kw):
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.update(kw.pop("env", None) or {})
    return subprocess.run([sys.executable, *map(str, a)], capture_output=True, text=True, env=env)


def copy_store(name, contexts):
    """A temp store with one copy of the golden context per requested name."""
    store = TMP / name
    store.mkdir(parents=True)
    for ctx in contexts:
        shutil.copytree(GOLDEN, store / ctx)
    return store


def state(root):
    return {str(p.relative_to(root)): hashlib.sha1(p.read_bytes()).hexdigest()
            for p in sorted(Path(root).rglob("*")) if p.is_file()}


def grep(root, needle):
    """Every (relative path, line) under root containing needle."""
    out = []
    for p in sorted(Path(root).rglob("*")):
        if not p.is_file():
            continue
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            if needle in line:
                out.append((str(p.relative_to(root)), line))
    return out


def read(p):
    return Path(p).read_text(encoding="utf-8")


# ------------------------------------------------------------------ dry run writes nothing
store = copy_store("dry", ["golden"])
run(LOG, "review", "golden", "--doc", "docs/brief-q3.md", "--store", store)
run(LOG, "consult", "golden", "--doc", "personas/coo-mira.md", "--store", store)
before = state(store)
r = run(FORGET, "coo-mira", "--store", store)
checks.append(("dry run exits 0", r.returncode == 0, (r.returncode, r.stderr)))
checks.append(("dry run writes nothing", state(store) == before, r.stdout[:400]))
checks.append(("dry run says nothing was written",
               "nothing written" in r.stdout and "--apply" in r.stdout, r.stdout[-300:]))
for expected in ("golden/personas/coo-mira.md", "golden/AUDIT.md",
                 "golden/calibration/pending-brief-q3.md",
                 "golden/reviews/2026-06-25-brief-q3.md", "usage.jsonl"):
    checks.append((f"dry run lists {expected}", expected in r.stdout, r.stdout))
checks.append(("dry run announces the reindex that follows", "reindex" in r.stdout, r.stdout[-300:]))
checks.append(("dry run paths are store-relative", str(store) not in r.stdout, r.stdout[:200]))

# ------------------------------------------------------------------ --apply, the FR-7.4 grep
store = copy_store("apply", ["golden"])
run(LOG, "review", "golden", "--doc", "docs/brief-q3.md", "--store", store)
run(LOG, "consult", "golden", "--doc", "personas/coo-mira.md", "--store", store)
astrid_before = read(store / "golden/personas/cfo-astrid.md")
r = run(FORGET, "coo-mira", "--store", store, "--apply")
checks.append(("--apply exits 0", r.returncode == 0, (r.returncode, r.stderr[-400:])))

hits = grep(store, "coo-mira")
checks.append(("after forget, the slug survives only in the AUDIT line",
               len(hits) == 1 and hits[0][0] == "golden/AUDIT.md", hits))
checks.append(("that line is the pinned forget line",
               bool(hits) and re.match(r"^\d{4}-\d{2}-\d{2} \| forget coo-mira \| \d+ rows "
                                       r"removed(, \d+ entries edited)?$",
                                       hits[0][1]) is not None, hits[:1]))
checks.append(("the audit line counts rows and entries separately, not both as rows",
               # the AUDIT ingestion row, the snapshot objection row and the usage row are
               # rows; the two `personas: …` enumerations are entries, not removals.
               bool(hits) and "3 rows removed, 2 entries edited" in hits[0][1], hits[:1]))
checks.append(("the persona file is gone",
               not (store / "golden/personas/coo-mira.md").exists(), "still there"))
checks.append(("the other personas are untouched",
               read(store / "golden/personas/cfo-astrid.md") == astrid_before, "changed"))
checks.append(("the index was regenerated without the slug",
               "## Personas (2)" in read(store / "golden/INDEX.md"), read(store / "golden/INDEX.md")[:400]))

snap = read(store / "golden/calibration/pending-brief-q3.md")
checks.append(("the snapshot keeps the other personas in its header",
               "personas: cfo-astrid (updated 2026-06-20), cto-jonas (updated 2026-06-20)" in snap,
               [ln for ln in snap.splitlines() if ln.startswith("personas:")]))
checks.append(("the snapshot keeps the other objection rows",
               snap.count("| r1 | steering committee |") == 2, snap))
review = read(store / "golden/reviews/2026-06-25-brief-q3.md")
checks.append(("an enumeration elsewhere loses the name and keeps the sentence",
               "personas cfo-astrid, cto-jonas." in review,
               [ln for ln in review.splitlines() if "personas" in ln]))
rows = [json.loads(ln) for ln in read(store / "usage.jsonl").splitlines() if ln.strip()]
checks.append(("usage rows naming the slug in doc are gone, the others kept",
               len(rows) == 1 and rows[0]["doc"] == "docs/brief-q3.md", rows))
audit = read(store / "golden/AUDIT.md")
checks.append(("the ingestion row that named the slug is gone",
               audit.count("| type: private-communication |") == 2, audit))

# ---------------------------------------- the done snapshot, the calibration log, and prose
# `forget coo-mira` never reaches the calibration log (that cycle graded the other two), so
# the rows FR-7.4 names there are exercised on a slug that does appear in all of them.
store = copy_store("logs", ["golden"])
r = run(FORGET, "cfo-astrid", "--store", store, "--apply")
checks.append(("--apply on a graded persona exits 0", r.returncode == 0, (r.returncode, r.stderr[-300:])))
log = read(store / "golden/calibration/log.md")
checks.append(("the calibration log loses the scoring row whose Persona cell is the slug",
               "| cfo-astrid |" not in log and "| cto-jonas | golden |" in log, log))
done = read(store / "golden/calibration/done-2026-07-02-brief-q2.md")
checks.append(("a done snapshot loses its P<k> line and its header entry, keeping the others",
               "cfo-astrid" not in done and "- P2 | cto-jonas |" in done
               and "personas: cto-jonas (updated 2026-06-01)" in done, done))
checks.append(("a prose mention is left exactly as written, not cut out of its sentence",
               "(P1\nfor cfo-astrid, P2 for cto-jonas), 0 misses" in log,
               [ln for ln in log.splitlines() if "gradeable" in ln or "P2 for" in ln]))
checks.append(("the run reports the prose mention it refused to rewrite",
               "LEFT  golden/calibration/log.md" in r.stdout and "prose, not rows" in r.stdout,
               r.stdout[-600:]))

sys.path.insert(0, str(HERE))
from forget import drop_from_enumeration  # noqa: E402

for line, slug, want in [
        ("personas: a-one (updated 2026-01-01), b-two (updated 2026-01-02)", "a-one",
         "personas: b-two (updated 2026-01-02)"),
        ("Panel run, personas a-one, b-two, c-three.", "c-three",
         "Panel run, personas a-one, b-two."),
        ("- 2026-06-25 | a-one, b-two | accepted the term, on condition", "b-two",
         "- 2026-06-25 | a-one | accepted the term, on condition"),
        ("1 gradeable prediction each (P1 for a-one, P2 for b-two), 0 misses", "a-one", None),
        ("a-one wrote the memo and, separately, signed it", "a-one", None)]:
    checks.append((f"drop_from_enumeration({slug!r}) on {line[:36]!r}",
                   drop_from_enumeration(line, slug) == want, drop_from_enumeration(line, slug)))

# ------------------------------------------------------ a slug that is a prefix of another
# `slug_re` pins the whole-word rule; this proves it end to end, because the failure mode is
# silent: forgetting coo-mira must not touch coo-mirabel's dossier, her rows, or a line that
# names them both.
store = copy_store("prefix", ["golden"])
NEIGHBOUR = """---
slug: coo-mirabel
aliases: [Mirabel]
role: Head of Depot Operations
organization: Halden Logistics (synthetic)
context: golden
decision_function: user
decision_weight: 2 # (Inference — runs one depot, does not sign off on spend)
cares_about: [depot handover, shift rosters]
created: 2026-06-11
updated: 2026-06-11
schema: 0.2
---

## Mandate and incentives <!-- last evidence: 2026-06-11 | decays fast -->
- Answers for the handover between shifts (Inference — from how she framed the rota)
"""
(store / "golden/personas/coo-mirabel.md").write_text(NEIGHBOUR, encoding="utf-8")
both = store / "golden/reviews/2026-06-25-brief-q3.md"
both.write_text(read(both).rstrip("\n")
                + "\n\n- 2026-06-25 | coo-mira, coo-mirabel | both read the depot section\n",
                encoding="utf-8")
r = run(FORGET, "coo-mira", "--store", store, "--apply")
checks.append(("forget on a slug that prefixes another exits 0", r.returncode == 0,
               (r.returncode, r.stderr[-300:])))
checks.append(("the neighbour's dossier is untouched",
               read(store / "golden/personas/coo-mirabel.md") == NEIGHBOUR, "changed"))
checks.append(("a line naming both keeps the neighbour and loses only the slug",
               "- 2026-06-25 | coo-mirabel | both read the depot section" in read(both),
               [ln for ln in read(both).splitlines() if "depot section" in ln]))
checks.append(("the neighbour still appears in the regenerated index",
               "- coo-mirabel |" in read(store / "golden/INDEX.md"),
               read(store / "golden/INDEX.md")[:400]))
checks.append(("grep for the forgotten slug still returns only the audit line",
               [h[0] for h in grep(store, "coo-mira") if "coo-mirabel" not in h[1]]
               == ["golden/AUDIT.md"],
               [h for h in grep(store, "coo-mira") if "coo-mirabel" not in h[1]]))

# ------------------------------------------------------------------ exit codes
store2 = copy_store("codes", ["golden"])
r = run(FORGET, "nobody-here", "--store", store2)
checks.append(("an unknown slug exits 2", r.returncode == 2, (r.returncode, r.stderr)))
checks.append(("the unknown-slug message names the slug", "nobody-here" in r.stderr, r.stderr))
r = run(FORGET, "coo-mira", "--store", store2, "--context", "golden")
checks.append(("an explicit --context that holds the slug exits 0", r.returncode == 0, r.stderr))
# A --context that is not a directory and a --context that is a real context this slug was
# never in are two different mistakes: the first is a typo in the command (usage, 1), the
# second is the documented "slug not found" (2). Answered with the same code, a mistyped
# context read as proof that the person is not in the store.
r = run(FORGET, "coo-mira", "--store", store2, "--context", "no-such-context")
checks.append(("a --context that is not a directory is a usage error (exit 1)",
               r.returncode == 1, (r.returncode, r.stderr)))
checks.append(("the message says the context was not found and names it",
               "usage: context not found: no-such-context" in r.stderr, r.stderr))
(store2 / "empty-context/personas").mkdir(parents=True, exist_ok=True)
r = run(FORGET, "coo-mira", "--store", store2, "--context", "empty-context")
checks.append(("a slug absent from a context that does exist still exits 2",
               r.returncode == 2, (r.returncode, r.stderr)))

two = copy_store("two", ["alpha", "beta"])
r = run(FORGET, "coo-mira", "--store", two)
checks.append(("an ambiguous slug is a usage error (exit 1)", r.returncode == 1, (r.returncode, r.stderr)))
checks.append(("the ambiguity message names both contexts",
               "alpha" in r.stderr and "beta" in r.stderr, r.stderr))
r = run(FORGET, "coo-mira", "--store", two, "--context", "beta", "--apply")
checks.append(("--context disambiguates and exits 0", r.returncode == 0, (r.returncode, r.stderr)))
checks.append(("only the named context lost the persona",
               (two / "alpha/personas/coo-mira.md").exists()
               and not (two / "beta/personas/coo-mira.md").exists(), "wrong context touched"))


# ------------------------------------------------------------------ through the entrypoint
store3 = copy_store("entry", ["golden"])
r = run(ENTRY, "--store", store3, "forget", "coo-mira")
checks.append(("beforehand.py forget dispatches to the module",
               r.returncode == 0 and "not available before task" not in r.stderr,
               (r.returncode, r.stderr[:200])))

# ------------------------------------------------ 0.3.1 E1: a gradeable cycle stays gradeable
# The pairing and the annotation key their lines by `<slug>#<n>`, `P<k>`, `- greenlight:` and
# `criterion:`. Left behind, one of them names a key that no longer exists and calibrate
# refuses the whole cycle (exit 2) — forgetting one person broke the grading of the others.
CAL_FIX = HERE / "test_fixtures/calibrate/store"


def calibrate(store):
    return run(ENTRY, "calibrate", "--store", store, "--context", "trial", "--doc", "brief-q4")


cal = TMP / "cal-e1"
shutil.copytree(CAL_FIX, cal)
r = calibrate(cal)
checks.append(("E1: the calibrate fixture grades before forget (exit 0)",
               r.returncode == 0, (r.returncode, r.stdout[-300:])))
dry = run(FORGET, "ops-sam", "--store", cal)
checks.append(("E1: the dry run lists the pairing row owned through P3",
               "row   trial/calibration/pairing-brief-q4.md: P3 | R1" in dry.stdout, dry.stdout))
checks.append(("E1: the dry run lists the overruled line and the greenlight line as rows",
               "row   trial/calibration/pairing-brief-q4.md: overruled: ops-sam#2" in dry.stdout
               and "row   trial/calibration/annotation-brief-q4.md: - greenlight: ops-sam"
               in dry.stdout, dry.stdout))
checks.append(("E1: nothing in the calibration files is LEFT", "LEFT" not in dry.stdout,
               dry.stdout))
r = run(FORGET, "ops-sam", "--store", cal, "--apply")
checks.append(("E1: forget --apply on the calibrate fixture exits 0", r.returncode == 0,
               (r.returncode, r.stderr[-300:])))
r = calibrate(cal)
checks.append(("E1: the same cycle still grades after forget (exit 0)",
               r.returncode == 0, (r.returncode, r.stdout[-300:] + r.stderr[-300:])))
pairing = read(cal / "trial/calibration/pairing-brief-q4.md")
checks.append(("E1: the other personas' pairing lines are kept",
               "budget-lin#1 | R1 | exact" in pairing and "P1 | R5 | substantive" in pairing
               and "overruled: budget-lin#3 | 2026-09-12" in pairing, pairing))
checks.append(("E1: after forget, the slug survives only in the AUDIT line",
               [h[0] for h in grep(cal, "ops-sam")] == ["trial/AUDIT.md"], grep(cal, "ops-sam")))

# criterion lines keyed by the slug, and pairing rows owned by the slug's P<k>
cal = TMP / "cal-e1-criteria"
shutil.copytree(CAL_FIX, cal)
pp = cal / "trial/calibration/pairing-brief-q4.md"
pp.write_text(read(pp) + "criterion: R6 | ops-sam#c1\ncriterion: R6 | budget-lin#c1\n"
              "overruled: P3 | 2026-09-05\n", encoding="utf-8")
dry = run(FORGET, "ops-sam", "--store", cal)
checks.append(("E1: a criterion line keyed <slug>#c<n> is a row",
               "row   trial/calibration/pairing-brief-q4.md: criterion: R6 | ops-sam#c1"
               in dry.stdout and "criterion: R6 | budget-lin#c1" not in dry.stdout, dry.stdout))
checks.append(("E1: `overruled: P<k>` for a P<k> the slug owns is a row",
               "row   trial/calibration/pairing-brief-q4.md: overruled: P3 | 2026-09-05"
               in dry.stdout, dry.stdout))

# a snapshot whose P ids cannot be read (T5: calibrate.NotGradeable on a duplicate id): the
# ownership of its P<k> rows is unknown, so the file is reported LEFT, never guessed.
sys.path.insert(0, str(HERE))
import calibrate as _cal  # noqa: E402
import forget as _fg  # noqa: E402

cal = TMP / "cal-e1-dup"
shutil.copytree(CAL_FIX, cal)
saved = _cal.parse_predictions


def _raise(text):
    raise _cal.NotGradeable("duplicate prediction id P3 in the snapshot")


import contextlib  # noqa: E402
import io  # noqa: E402

_cal.parse_predictions = _raise
try:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
        rc = _fg.main(["ops-sam", "--store", str(cal)])
finally:
    _cal.parse_predictions = saved
out = buf.getvalue()
checks.append(("E1: an unreadable P-id set does not crash forget", rc == 0, (rc, out[-300:])))
checks.append(("E1: the snapshot whose P ids cannot be read is reported LEFT",
               "LEFT  trial/calibration/pending-brief-q4.md" in out
               and "duplicate prediction id P3" in out, out))
checks.append(("E1: without the P ids, the P3 pairing row is not cut on a guess",
               "row   trial/calibration/pairing-brief-q4.md: P3 | R1" not in out, out))

# ---------------------------------------------- 0.3.1 E2: single-entry headers, review rows
nw = TMP / "nw-e2"
shutil.copytree(FIXTURE, nw)
dry = run(FORGET, "cto-mara", "--store", nw)
checks.append(("E2: a single-entry `personas:` header is a row, not LEFT prose",
               "row   northwind/calibration/pending-zero-preds.md: personas: cto-mara" in dry.stdout
               and "LEFT" not in dry.stdout, dry.stdout))
checks.append(("E2: a `- <date> | <slug> | …` bullet under reviews/ is a row",
               "row   northwind/reviews/2026-08-20-brief-preds.md: - 2026-08-21 | cto-mara |"
               in dry.stdout, dry.stdout))
r = run(FORGET, "cto-mara", "--store", nw, "--apply")
checks.append(("E2: after forget, cto-mara survives only in the AUDIT line",
               r.returncode == 0 and [h[0] for h in grep(nw, "cto-mara")] == ["northwind/AUDIT.md"],
               (r.returncode, grep(nw, "cto-mara"))))

# ---------------------------------------------- 0.3.1 E3: a created AUDIT is a 0.2 AUDIT
# northwind has no AUDIT.md: forget creates it, and a migrate right after must find nothing.
import migrate as _mg  # noqa: E402

audit = read(nw / "northwind/AUDIT.md")
checks.append(("E3: a created AUDIT carries migrate's 0.2 header",
               audit.startswith(getattr(_mg, "AUDIT_TEMPLATE", "\0")) and _mg.AUDIT_HEADER in audit
               and _mg.SCHEMA_COMMENT in audit, audit))
checks.append(("E3: migrate has nothing to change in the created AUDIT",
               _mg.migrate_audit(audit) == audit, _mg.migrate_audit(audit)))

# ---------------------------------------------- 0.3.1 order: the persona file goes last
cal = TMP / "cal-order"
shutil.copytree(CAL_FIX, cal)
order = []
saved_write, saved_unlink = getattr(_fg, "atomic_write", None), Path.unlink


def _w(path, text):
    order.append(("write", Path(path).name))
    return saved_write(path, text) if saved_write else Path(path).write_text(text)


def _u(self, *a, **kw):
    order.append(("unlink", self.name))
    return saved_unlink(self, *a, **kw)


_fg.atomic_write, Path.unlink = _w, _u
try:
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        rc = _fg.main(["ops-sam", "--store", str(cal), "--apply"])
finally:
    _fg.atomic_write, Path.unlink = saved_write, saved_unlink
persona_at = [i for i, o in enumerate(order) if o == ("unlink", "ops-sam.md")]
checks.append(("forget writes every other file through atomic_write, the persona file last",
               rc == 0 and persona_at and any(o[0] == "write" for o in order)
               and all(i < persona_at[0] for i, o in enumerate(order)
                       if o[0] == "write" and o[1] != "INDEX.md"),
               order))

# ================================================================== 0.3.1 fix round 1
VAR = HERE / "test_fixtures/calibrate/variants"


def cal_copy(name):
    dst = TMP / name
    shutil.copytree(CAL_FIX, dst)
    return dst


def prose_copy(name):
    """The calibrate fixture graded through a ledger: a prose pending pinned by sha1."""
    dst = cal_copy(name)
    shutil.copy(VAR / "pending-prose.md", dst / "trial/calibration/pending-brief-q4.md")
    shutil.copy(VAR / "ledger-brief-q4.md", dst / "trial/calibration/ledger-brief-q4.md")
    return dst


def calibrate_ledger(store):
    return run(ENTRY, "calibrate", "--store", store, "--context", "trial", "--doc", "brief-q4",
               "--ledger")


# ---- R1.1: ownership comes from the snapshot the pairing grades, never pooled across cycles
two = cal_copy("fr1-two-cycles")
cald = two / "trial/calibration"
pend = read(cald / "pending-brief-q4.md")
done = (pend.replace("- P1 | platform-noor |", "- P1 | ops-sam |")
        .replace("- P2 | budget-lin |", "- P2 | platform-noor |")
        .replace("- P3 | ops-sam |", "- P3 | budget-lin |"))
(cald / "done-2026-06-01-brief-q4.md").write_text(done, encoding="utf-8")
r = calibrate(two)
checks.append(("R1.1: the two-cycle store grades before forget", r.returncode == 0,
               (r.returncode, r.stdout[-200:] + r.stderr[-200:])))
dry = run(FORGET, "ops-sam", "--store", two)
checks.append(("R1.1: platform-noor's P1 pairing line is neither cut nor LEFT",
               "P1 | R5" not in dry.stdout, dry.stdout))
checks.append(("R1.1: ops-sam's P3 pairing line (current cycle) is a row",
               "row   trial/calibration/pairing-brief-q4.md: P3 | R1" in dry.stdout, dry.stdout))
run(FORGET, "ops-sam", "--store", two, "--apply")
r = calibrate(two)
checks.append(("R1.1: the two-cycle store still grades after forget", r.returncode == 0,
               (r.returncode, r.stdout[-200:] + r.stderr[-200:])))

# ---- R1.4: a pending pinned by a ledger's `snapshot sha1:` is read-only
pin = prose_copy("fr1-pinned")
r = calibrate_ledger(pin)
checks.append(("R1.4: the ledger-graded prose cycle grades before forget", r.returncode == 0,
               (r.returncode, r.stdout[-200:] + r.stderr[-200:])))
pinned_before = (pin / "trial/calibration/pending-brief-q4.md").read_bytes()
r = run(FORGET, "ops-sam", "--store", pin, "--apply")
checks.append(("R1.4: the pinned pending is byte-unchanged",
               (pin / "trial/calibration/pending-brief-q4.md").read_bytes() == pinned_before,
               r.stdout[-400:]))
checks.append(("R1.4: its mentions are LEFT with the pin as the reason",
               "LEFT  trial/calibration/pending-brief-q4.md" in r.stdout
               and "pinned by ledger-brief-q4.md (snapshot sha1)" in r.stdout, r.stdout))
r = calibrate_ledger(pin)
checks.append(("R1.4: the ledger-graded cycle still grades after forget", r.returncode == 0,
               (r.returncode, r.stdout[-200:] + r.stderr[-200:])))

# ---- R1.2: a crash after any number of writes, then a re-run, leaves a gradeable cycle
count_store = prose_copy("fr1-count")
n_writes = []
saved_aw = _fg.atomic_write


def _count(path, text):
    n_writes.append(Path(path).name)
    return saved_aw(path, text)


_fg.atomic_write = _count
try:
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        _fg.main(["ops-sam", "--store", str(count_store), "--apply"])
finally:
    _fg.atomic_write = saved_aw
crash_bad = []
for n in range(len(n_writes) + 1):
    st_n = prose_copy("fr1-crash-%d" % n)
    done_n = [0]

    def _boom(path, text, done_n=done_n, n=n):
        if done_n[0] >= n:
            raise OSError("simulated crash")
        done_n[0] += 1
        return saved_aw(path, text)

    _fg.atomic_write = _boom
    try:
        with contextlib.redirect_stdout(io.StringIO()) as crash_out, \
                contextlib.redirect_stderr(io.StringIO()):
            try:
                _fg.main(["ops-sam", "--store", str(st_n), "--apply"])
            except OSError:
                pass
    finally:
        _fg.atomic_write = saved_aw
    if n < len(n_writes) and "removed       trial/personas/ops-sam.md" in crash_out.getvalue():
        crash_bad.append((n, "announced the persona removed before it happened"))
    run(FORGET, "ops-sam", "--store", st_n, "--apply")
    r = calibrate_ledger(st_n)
    if r.returncode != 0:
        crash_bad.append((n, r.stdout[-200:] + r.stderr[-200:]))
checks.append(("R1.2: crash after N writes (every N) + re-run -> still gradeable (%d writes)"
               % len(n_writes), len(n_writes) > 1 and not crash_bad, crash_bad))
checks.append(("R1.2: keyed pairing/annotation files are written first, P-row sources last",
               n_writes[:2] == sorted(n_writes[:2]) and set(n_writes[:2])
               == {"annotation-brief-q4.md", "pairing-brief-q4.md"}
               and n_writes.index("ledger-brief-q4.md") > max(
                   i for i, w in enumerate(n_writes) if w not in ("ledger-brief-q4.md", "AUDIT.md")),
               n_writes))
checks.append(("R1.6: the persona line says `removed` only after the file is gone",
               not [b for b in crash_bad if "announced" in str(b[1])], crash_bad))

# ---- R1.3: an enumeration edit never eats a longer slug's prefix
for line, slug in [("Reviewed by devops-sam, cto-jonas. Follow-up owner: ops-sam.", "ops-sam"),
                   ("Reviewed by cto-dana, cto-jonas.", "dana")]:
    got = _fg.drop_from_enumeration(line, slug)
    checks.append(("R1.3: drop_from_enumeration(%r) leaves %r alone" % (slug, line[:30]),
                   got is None, got))

# ---- R1.5: an earlier forget line in the AUDIT is the intended trace and is kept
rows5 = []
kept = _fg.clean_audit("# AUDIT\n\n2026-01-01 | forget ops-sam | 3 rows removed\n\n"
                       "2026-02-01 | sources/x.txt | personas: ops-sam\n", "ops-sam", rows5)
checks.append(("R1.5: clean_audit keeps an earlier `forget <slug>` line, drops the others",
               "2026-01-01 | forget ops-sam | 3 rows removed" in kept
               and "sources/x.txt" not in kept, kept))

# ---- R1.7: the dry run shows `old -> new` for an entry edit
store7 = copy_store("fr1-entries", ["golden"])
r = run(FORGET, "coo-mira", "--store", store7)
entry_lines = [ln for ln in r.stdout.splitlines() if ln.lstrip().startswith("entry")]
checks.append(("R1.7: every entry line in the dry run shows old -> new",
               entry_lines and all(" -> " in ln for ln in entry_lines)
               and any("personas cfo-astrid, cto-jonas." in ln.split(" -> ")[-1]
                       for ln in entry_lines), entry_lines))

# ---- R1.8: done-file names are matched against the documents actually present
checks.append(("R1.8: done-<date>-plan-2026.md belongs to plan-2026, not plan",
               hasattr(_fg, "doc_key")
               and _fg.doc_key("done-2026-07-02-plan-2026.md", {"plan-2026", "plan"}) == "plan-2026"
               and _fg.doc_key("done-2026-07-02-plan-2026.md", {"plan-2026"}) == "plan-2026",
               [_fg.doc_key("done-2026-07-02-plan-2026.md", k) for k in ({"plan-2026", "plan"},
                                                                          {"plan-2026"})]
               if hasattr(_fg, "doc_key") else "no doc_key"))
# Ruling R2.2: `-<n>` is a second grading only when done-<same date>-<doc>.md exists.
checks.append(("R1.8: a second grading done-<date>-<doc>-2.md belongs to <doc>",
               _fg.doc_key("done-2026-07-02-brief-2.md", {"brief"},
                           {"done-2026-07-02-brief.md", "done-2026-07-02-brief-2.md"})
               == "brief", "wrong key"))

# ---- R1.9: a quoted span in another persona's row is never edited
rows9 = []
line9 = '| cto-jonas | "ops-sam, cfo-astrid." said in the call |'
out9 = _fg.clean_text(line9, "ops-sam", rows9)
checks.append(("R1.9: a slug inside a quoted span is LEFT, the line unchanged",
               out9 == line9 and [k for k, *_ in rows9] == ["mention"], rows9))

# ================================================================== 0.3.1 fix round 2
# ---- R2.1/R2.2: no pending, a same-day second grading of a document named plan-2026
ords = cal_copy("fr2-order")
oc = ords / "trial/calibration"
base_pend = read(oc / "pending-brief-q4.md")
older = (base_pend.replace("- P1 | platform-noor |", "- P1 | ops-sam |")
         .replace("- P2 | budget-lin |", "- P2 | platform-noor |")
         .replace("- P3 | ops-sam |", "- P3 | budget-lin |"))
(oc / "done-2026-07-02-plan-2026.md").write_text(older, encoding="utf-8")
(oc / "done-2026-07-02-plan-2026-2.md").write_text(base_pend, encoding="utf-8")
(oc / "pending-brief-q4.md").unlink()
(oc / "pairing-brief-q4.md").rename(oc / "pairing-plan-2026.md")
(oc / "annotation-brief-q4.md").rename(oc / "annotation-plan-2026.md")
dry = run(FORGET, "ops-sam", "--store", ords)
checks.append(("R2.1: the newest grading (-2) owns the ids: platform-noor's P1 is kept",
               "P1 | R5" not in dry.stdout, dry.stdout[-900:]))
checks.append(("R2.1: ... and ops-sam's P3 (newest grading) is a row",
               "row   trial/calibration/pairing-plan-2026.md: P3 | R1" in dry.stdout,
               dry.stdout[-900:]))
names = {"done-2026-07-02-plan-2026.md", "pairing-plan.md"}
checks.append(("R2.2: with only `plan` known, done-<date>-plan-2026.md is plan-2026",
               _fg.doc_key("done-2026-07-02-plan-2026.md", {"plan"}, names) == "plan-2026",
               _fg.doc_key("done-2026-07-02-plan-2026.md", {"plan"}, names)))

# ---- R2.3: a ledger-graded prose cycle already renamed to done-<date>-<doc>.md
pdone = prose_copy("fr2-prose-done")
pc = pdone / "trial/calibration"
(pc / "pending-brief-q4.md").rename(pc / "done-2026-09-12-brief-q4.md")
done_before = (pc / "done-2026-09-12-brief-q4.md").read_bytes()
r = run(FORGET, "ops-sam", "--store", pdone, "--apply")
checks.append(("R2.3: a done snapshot pinned by the ledger's sha1 is byte-unchanged",
               (pc / "done-2026-09-12-brief-q4.md").read_bytes() == done_before, r.stdout[-500:]))
checks.append(("R2.3: ... its mentions are LEFT with the pin as the reason",
               "LEFT  trial/calibration/done-2026-09-12-brief-q4.md" in r.stdout
               and "pinned by ledger-brief-q4.md (snapshot sha1)" in r.stdout, r.stdout[-800:]))
checks.append(("R2.3: ... ownership came from the ledger: the P3 pairing line is gone",
               "P3 | R1" not in read(pc / "pairing-brief-q4.md"), read(pc / "pairing-brief-q4.md")))

# ---- R2.4: a long LEFT line keeps its whole reason
long_store = prose_copy("fr2-long")
lp = long_store / "trial/calibration/ledger-brief-q4.md"
pr = long_store / "trial/calibration/pending-brief-q4.md"
pr.write_text(read(pr) + "\nops-sam " + "x" * 200 + "\n", encoding="utf-8")
led = read(lp)
import hashlib as _hl  # noqa: E402

led = re.sub(r"(?m)^snapshot sha1: .*$", "snapshot sha1: " + _hl.sha1(pr.read_bytes()).hexdigest(), led)
lp.write_text(led, encoding="utf-8")
r = run(FORGET, "ops-sam", "--store", long_store)
long_left = [ln for ln in r.stdout.splitlines() if "LEFT" in ln and "xxxx" in ln]
checks.append(("R2.4: the quoted line is cut, never the reason",
               long_left and long_left[0].endswith("[pinned by ledger-brief-q4.md (snapshot sha1)]"),
               long_left))

# ---- R2.5: an entry edit that leaves a second mention of the slug is also reported LEFT
rows5 = []
line5 = "Panel run with personas ops-sam, cto-jonas; later ops-sam said the pilot slips."
out5 = _fg.clean_text(line5, "ops-sam", rows5)
checks.append(("R2.5: the entry is dropped and the surviving mention reported LEFT",
               [r_[0] for r_ in rows5] == ["entry", "mention"] and "ops-sam said" in out5,
               rows5))

fails = [c for c in checks if not c[1]]
for n, ok, got in checks:
    print(("ok   " if ok else "FAIL ") + n + ("" if ok else f" -> {str(got)[:400]}"))
print(f"\n{len(checks)-len(fails)}/{len(checks)} passed")
sys.exit(1 if fails else 0)
