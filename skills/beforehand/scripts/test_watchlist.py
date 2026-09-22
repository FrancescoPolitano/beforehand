#!/usr/bin/env python3
"""Tests for watchlist.py and for the content-loss guard of verify_quotes.py.

The case that matters: promoting an entry by hand means cutting prose bullets of variable
length, and a cut that overshoots swallows the next section header. Nothing downstream
notices, because the excerpts still present all resolve.
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True  # G5: a suite run on its own leaves no __pycache__

HERE = Path(__file__).parent
FIX = HERE / "test_fixtures/watchlist/persona.md"
checks = []


def run(script, *a):
    return subprocess.run([sys.executable, str(HERE / script), *[str(x) for x in a]],
                          capture_output=True, text=True, cwd=HERE)


def fresh():
    d = Path(tempfile.mkdtemp())
    shutil.copy(FIX, d / "persona.md")
    return d / "persona.md"


# ---- list
r = run("watchlist.py", FIX, "--list", "--json")
rows = json.loads(r.stdout)
checks.append(("both entries parsed", len(rows) == 2, rows))
checks.append(("an entry citing two distinct sources is visible as such",
               len(rows[0]["sources"]) == 2, rows[0]))
checks.append(("a single-source entry is not", len(rows[1]["sources"]) == 1, rows[1]))
r = run("watchlist.py", FIX, "--list")
checks.append(("READY is offered as a hint, not a verdict", "not a verdict" in r.stdout, r.stdout))

# ---- ids
p = fresh()
r = run("watchlist.py", p, "--assign-ids")
checks.append(("--assign-ids without --apply writes nothing",
               p.read_text() == FIX.read_text() and "nothing written" in r.stdout, r.stdout))
r = run("watchlist.py", p, "--assign-ids", "--apply")
body = p.read_text()
checks.append(("ids are inserted",
               "- [wl-01] **Won't sign" in body and "- [wl-02] **Prefers" in body, body[:200]))
r2 = run("watchlist.py", p, "--assign-ids", "--apply")
checks.append(("--assign-ids is idempotent", "nothing to change" in r2.stdout, r2.stdout))

# ---- promotion
before = p.read_text()
r = run("watchlist.py", p, "--promote", "wl-01", "--section", "Red lines")
checks.append(("--promote without --apply writes nothing", p.read_text() == before, None))
checks.append(("it prints a diff", "+++ " in r.stdout and "@@" in r.stdout, r.stdout[:300]))
checks.append(("it warns that the 'if it repeats' clause must be rewritten",
               "belonged to the anteroom" in r.stderr, r.stderr))

r = run("watchlist.py", p, "--promote", "wl-01", "--section", "Red lines", "--apply")
after = p.read_text()
red = after.split("## Red lines")[1].split("## ")[0]
checks.append(("the entry landed in the target section",
               "Won't sign without a rollback rehearsal" in red, red))
checks.append(("a promotion record stays in the Watchlist",
               "[wl-01] PROMOTED" in after.split("## Watchlist")[1], after.split("## Watchlist")[1][:300]))
checks.append(("the record names the target section", "-> Red lines" in after, after))
checks.append(("no Fact tag was lost",
               after.count("(Fact") == before.count("(Fact"), (before.count("(Fact"), after.count("(Fact"))))
checks.append(("every heading survived",
               all(h in after for h in ("## Mandate and incentives", "## Judgment criteria",
                                        "## Red lines", "## Watchlist", "## Reliability")), None))
r = run("watchlist.py", p, "--promote", "wl-01", "--section", "Red lines")
checks.append(("a promoted entry cannot be promoted twice",
               r.returncode == 1 and "already a promotion record" in r.stderr, r.stderr))
checks.append(("wl-01's clause sits between two Fact tags and is still carried into the body",
               "If it repeats: becomes a red line" in red, red))

# ---- FR-4.1: the anteroom clause after the last Fact tag is dropped from the promoted
# line and kept in the promotion record, unless it holds a quoted excerpt
p3 = fresh()
run("watchlist.py", p3, "--assign-ids", "--apply")
before3 = p3.read_text()
r = run("watchlist.py", p3, "--promote", "wl-02", "--section", "Judgment criteria")
checks.append(("it announces the dropped tail on stdout",
               "dropped from the promoted line (kept in the promotion record): "
               "If it repeats: goes into Language and dissent style" in r.stdout, r.stdout))
moved_lines = [ln for ln in r.stdout.splitlines()
               if ln.startswith("+- **Prefers short meetings")]
checks.append(("the promoted line in the diff no longer carries the clause",
               len(moved_lines) == 1 and "If it repeats" not in moved_lines[0], moved_lines))
checks.append(("no NOTE fires once the clause has been dropped, not merely carried",
               "belonged to the anteroom" not in r.stderr, r.stderr))

r = run("watchlist.py", p3, "--promote", "wl-02", "--section", "Judgment criteria", "--apply")
after3 = p3.read_text()
checks.append(("the promotion record keeps the dropped tail",
               "— dropped: If it repeats: goes into Language and dissent style" in after3, after3))
checks.append(("no Fact tag was lost when the tail was dropped",
               after3.count("(Fact") == before3.count("(Fact"),
               (before3.count("(Fact"), after3.count("(Fact"))))

p4 = fresh()
run("watchlist.py", p4, "--assign-ids", "--apply")
r = run("watchlist.py", p4, "--promote", "wl-02", "--section", "Judgment criteria",
        "--note", "Confirmed again in the October review.", "--apply")
after4 = p4.read_text()
jc = after4.split("## Judgment criteria")[1].split("## ")[0]
checks.append(("--note is appended after the dropped clause, ending the promoted line",
               jc.rstrip().endswith("Confirmed again in the October review.")
               and "If it repeats" not in jc, jc))

# ---- the section title is the name, not the whole heading line
p2 = fresh()
run("watchlist.py", p2, "--assign-ids", "--apply")
t = p2.read_text().replace("## Red lines", "## Red lines <!-- last evidence: 2026-08-01 -->")
p2.write_text(t)
r = run("watchlist.py", p2, "--promote", "wl-01", "--section", "Red lines", "--apply")
checks.append(("a heading with a trailing HTML comment still resolves",
               r.returncode == 0 and "-> Red lines." in p2.read_text(), r.stdout + r.stderr))

# ---- a bad --section or --promote is refused, and says what is available
r = run("watchlist.py", FIX, "--promote", "wl-99", "--section", "Red lines")
checks.append(("an unknown id is refused", r.returncode == 1 and "matched 0 entries" in r.stderr, r.stderr))
r = run("watchlist.py", FIX, "--promote", "rollback", "--section", "No Such Section")
checks.append(("an unknown section is refused and the real ones are listed",
               r.returncode == 1 and "Judgment criteria" in r.stderr, r.stderr))

# ---- the content-loss guard: yesterday's failure, reproduced
old = fresh()
new = old.parent / "after.md"
body = old.read_text()
cut = body.index("## Reliability")
new.write_text(body[:cut - 300] + body[cut + len("## Reliability"):])   # the overshooting cut
r = run("verify_quotes.py", new, "--sources-root", HERE, "--against", old, "--lint")
checks.append(("the excerpt linter alone still passes the mangled file",
               "LINT PASS" in r.stdout, r.stdout))
checks.append(("--against reports the lost section", "section lost: 'Reliability'" in r.stdout, r.stdout))
checks.append(("--against reports the lost Fact tag", "Fact tags" in r.stdout, r.stdout))
checks.append(("--lint with --against fails on undeclared loss", r.returncode == 1, r.returncode))
r = run("verify_quotes.py", new, "--sources-root", HERE, "--against", old, "--lint", "--allow-shrink")
checks.append(("--allow-shrink lets a declared loss through", r.returncode == 0, r.returncode))
r = run("verify_quotes.py", old, "--sources-root", HERE, "--against", old, "--lint")
checks.append(("an unchanged file reports no loss", "No content lost" in r.stdout, r.stdout))

# ---- 0.3.1 E9: a persona that is not UTF-8 is read leniently, never a traceback
lat = fresh()
lat.write_bytes(lat.read_text(encoding="utf-8").replace("Prefers short meetings.",
                                                        "Prefers short réunions.")
                .encode("latin-1", errors="replace"))
r = run("watchlist.py", lat, "--list", "--json")
checks.append(("E9: a latin-1 persona lists without a traceback",
               r.returncode == 0 and "Traceback" not in r.stderr, (r.returncode, r.stderr[-300:])))

# ---- 0.3.1 S14: watchlist has a `_today` hook like the other modules
import contextlib  # noqa: E402
import datetime as _dt  # noqa: E402
import io  # noqa: E402

sys.path.insert(0, str(HERE))
import watchlist as _wl  # noqa: E402

checks.append(("S14: watchlist exposes a _today hook", callable(getattr(_wl, "_today", None)),
               dir(_wl)[:0]))
hp = fresh()
with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
    _wl.main([str(hp), "--assign-ids", "--apply"])
saved_today = getattr(_wl, "_today", None)
_wl._today = lambda: _dt.date(2030, 1, 2)
try:
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        rc = _wl.main([str(hp), "--promote", "wl-01", "--section", "Red lines", "--apply"])
    age = _wl.days_since("2030-01-01")
finally:
    if saved_today is None:
        del _wl._today
    else:
        _wl._today = saved_today
checks.append(("S14: the promotion record is dated by _today",
               rc == 0 and "PROMOTED 2030-01-02" in hp.read_text(encoding="utf-8"),
               hp.read_text(encoding="utf-8")[-500:]))
checks.append(("S14: entry ages are measured against _today", age == 1, age))
checks.append(("F3: days_since refuses a compact date on every interpreter",
               _wl.days_since("20260101") is None, _wl.days_since("20260101")))

# ---- 0.3.1 S6: the integrity check is migrate's content_loss plus the section-grew check
old = FIX.read_text(encoding="utf-8")
new = old.replace("- Owns delivery risk (Inference — from budget decisions in the call)\n", "")
new = new.replace("## Red lines\n", "## Red lines\n- a promoted line\n")
probs = _wl.integrity(old, new, "Red lines")
checks.append(("S6: integrity reports a section that lost a bullet (content_loss's rule)",
               any("Mandate and incentives" in p and "entries" in p for p in probs), probs))
checks.append(("S6: integrity still requires the target section to grow",
               any("did not grow" in p for p in _wl.integrity(old, old, "Red lines")),
               _wl.integrity(old, old, "Red lines")))

# ---- 0.3.1 S3: --apply writes through atomic_write
writes = []
saved_aw = getattr(_wl, "atomic_write", None)
_wl.atomic_write = lambda path, text: writes.append(str(path))
try:
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        _wl.main([str(fresh()), "--assign-ids", "--apply"])
finally:
    if saved_aw is None:
        del _wl.atomic_write
    else:
        _wl.atomic_write = saved_aw
checks.append(("S3: watchlist --apply writes through atomic_write", len(writes) == 1, writes))

fails = [c for c in checks if not c[1]]
for n, ok, got in checks:
    print(("ok   " if ok else "FAIL ") + n + ("" if ok else f" -> {str(got)[:300]}"))
print(f"\n{len(checks)-len(fails)}/{len(checks)} passed")
sys.exit(1 if fails else 0)
