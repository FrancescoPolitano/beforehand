#!/bin/sh
# check_all.sh — the gate (SPEC-0.2 FR-7.2). There is no hosted CI (a maintainer decision,
# not a stopgap before 1.0): this script is the gate, run by hand before a share, a backup,
# or calling a task done, and by the pre-commit-minded contributor before a commit or a pull
# request. check_all_versions.sh runs it once per supported interpreter.
#
# Order: generality (patterns only) -> router budget -> one norm, one file -> anchor targets
# resolve (every anchor on the line) -> the test suite -> golden-store expectations
# (idempotent reindex, doctor: healthy) -> deterministic index (real writes on copies of the
# golden store, on two days when its personas are stale: byte-identical) -> the 3.9 syntax
# floor (dev/check_floor.py, an AST check, since this machine may have no 3.9 interpreter of
# its own — see check_all_versions.sh) -> ruff -> evals (checkers-only, no host CLI, nothing
# written outside a temporary directory) -> cli (beforehand_cli/test_cli.py: install, refusals,
# uninstall and bundle against a temporary HOME; nothing written into the repository).
#
# Environment:
#   PYTHON   interpreter to run the suite and the store checks with. Default: python3.
#   RUFF     ruff binary. Default: `ruff` on PATH if present; the step is skipped with a
#            notice, not a failure, when neither is set.
#   REQUIRE_RUFF  set to 1 (CI) to turn that skip into a failure: `ruff: required but not
#            found`. A green run must not mean a step vanished.
#
# Exit 1 if any step fails. One line per step (`ok` / `FAIL` / `skipped`), preceded by
# whatever that step's own tool prints (most already end in their own pinned status line).
set -u

root=$(cd "$(dirname "$0")/.." && pwd)
scripts="$root/skills/beforehand/scripts"
entry="$scripts/beforehand.py"
PYTHON="${PYTHON:-python3}"

PYTHONDONTWRITEBYTECODE=1
export PYTHONDONTWRITEBYTECODE

status=0

section() {
    echo ""
    echo "-- $1 --"
}

# --------------------------------------------------------------------- 1. generality
section "generality"
out=$(sh "$root/dev/check_generality.sh" --patterns-only 2>&1)
rc=$?
printf '%s\n' "$out"
if [ $rc -eq 0 ]; then echo "generality: ok"; else echo "generality: FAIL"; status=1; fi

# --------------------------------------------------------------------- 2. router budget
section "router"
out=$(sh "$root/dev/check_router.sh" 2>&1)
rc=$?
printf '%s\n' "$out"
if [ $rc -eq 0 ]; then echo "router: ok"; else echo "router: FAIL"; status=1; fi

# --------------------------------------------------------------------- 3. one norm, one file
section "norms"
out=$(sh "$root/dev/check_norms.sh" 2>&1)
rc=$?
printf '%s\n' "$out"
if [ $rc -eq 0 ]; then echo "norms: ok"; else echo "norms: FAIL"; status=1; fi

# --------------------------------------------------------------------- 4. anchor targets
# One norm, one file says where a rule is stated; this says the pointers to it resolve.
# Scanned: skills/beforehand/, docs/, README.md and CONTRIBUTING.md. On every line that carries
# `evidence-model.md#`, EVERY anchor is checked (G2): the one right after
# `evidence-model.md#` and each follow-on written as `` `#<X>` `` on the same line, so in
# ``evidence-model.md#Labels`, `#Tag contract`` both must name a `## <X>` heading in that
# file. Anchors are compared with `-` normalised to a space, so `#Post-review` and
# `#Writes and confirmations` are both legal spellings of their heading and a mis-spelled one
# (`#Writes-and-confirmations` when the heading has spaces) still matches. A placeholder
# (`#<heading>`, `#<X>`) is skipped.
# (Run into a temp file rather than inside $(...): the program holds unbalanced backticks and
# parentheses, which /bin/sh on some hosts mis-parses in a here-document inside a command
# substitution.)
section "anchors"
anchor_tmp=$(mktemp "${TMPDIR:-/tmp}/personas-anchors.XXXXXX")
"$PYTHON" - "$root" >"$anchor_tmp" 2>&1 <<'PYEOF'
import os
import re
import sys

root = sys.argv[1]
em = os.path.join(root, "skills", "beforehand", "references", "evidence-model.md")
with open(em, encoding="utf-8") as fh:
    heads = {ln[3:].rstrip("\n").replace("-", " ").strip() for ln in fh if ln.startswith("## ")}
STOP = "`)\",;"
FIRST = re.compile(r"evidence-model\.md#([^%s]*)" % re.escape(STOP))
FOLLOW = re.compile(r"`#([^#\s`][^%s]*)" % re.escape(STOP))

targets = []
for top in ("skills/beforehand", "docs"):
    for dirpath, dirnames, filenames in os.walk(os.path.join(root, top)):
        dirnames[:] = sorted(d for d in dirnames if d != "__pycache__")
        targets += [os.path.join(dirpath, f) for f in sorted(filenames)]
targets += [os.path.join(root, f) for f in ("README.md", "CONTRIBUTING.md")]
for path in targets:
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().split("\n")
    except (OSError, UnicodeDecodeError):
        continue
    rel = os.path.relpath(path, root)
    for n, line in enumerate(lines, 1):
        if "evidence-model.md#" not in line:
            continue
        for a in FIRST.findall(line) + FOLLOW.findall(line):
            a = re.sub(r"-->$", "", a)
            a = re.sub(r"[ .:]+$", "", a)
            if not a or a.startswith("<"):
                continue
            if a.replace("-", " ").strip() not in heads:
                print("%s:%d: no `## %s` heading in evidence-model.md" % (rel, n, a.replace("-", " ")))
PYEOF
anchor_bad=$(cat "$anchor_tmp")
rm -f "$anchor_tmp"
if [ -z "$anchor_bad" ]; then
    echo "anchors: ok (every evidence-model.md#<X> resolves to a heading)"
else
    printf '%s\n' "$anchor_bad"
    echo "anchors: FAIL"
    status=1
fi

# --------------------------------------------------------------------- 5. the test suite
section "tests (PYTHON=$PYTHON)"
out=$("$PYTHON" "$entry" test 2>&1)
rc=$?
printf '%s\n' "$out"
if [ $rc -eq 0 ]; then echo "tests: ok"; else echo "tests: FAIL"; status=1; fi

# --------------------------------------------------------------------- 6. golden-store expectations
# reindex --dry-run on the golden context must report golden/INDEX.md unchanged (the
# committed fixture is already up to date), and doctor must call it healthy.
section "golden"
golden_store="$scripts/test_fixtures/store"
reindex_out=$("$PYTHON" "$entry" reindex --store "$golden_store" --context golden --dry-run 2>&1)
reindex_rc=$?
reindex_ok=0
if [ $reindex_rc -eq 0 ] && printf '%s\n' "$reindex_out" | grep -Eq '^unchanged[[:space:]]+.*golden/INDEX\.md$'; then
    reindex_ok=1
fi
doctor_out=$("$PYTHON" "$entry" doctor --store "$golden_store" --context golden --today 2026-09-17 2>&1)
doctor_rc=$?
doctor_last=$(printf '%s\n' "$doctor_out" | tail -1)
doctor_ok=0
[ $doctor_rc -eq 0 ] && [ "$doctor_last" = "doctor: healthy" ] && doctor_ok=1
printf '%s\n' "$reindex_out"
printf '%s\n' "$doctor_out"
if [ "$reindex_ok" -eq 1 ] && [ "$doctor_ok" -eq 1 ]; then
    echo "golden: ok"
else
    echo "golden: FAIL"
    [ "$reindex_ok" -eq 1 ] || echo "  reindex --dry-run did not report golden/INDEX.md unchanged"
    [ "$doctor_ok" -eq 1 ] || echo "  doctor did not print the pinned 'doctor: healthy' line"
    status=1
fi

# --------------------------------------------------------------------- 7. deterministic index
# FR-4.7, FR-5.6 (E8): an unchanged store must reindex byte-identically on any later day. A
# dry-run cannot show this — it prints `would write` / `unchanged`, never the content — so this
# step makes REAL writes, on temporary copies of the golden store, with reindex._today (the
# hook the module defines for this) mocked to 2027-01-10 and 2027-01-11: two days on which every
# golden persona IS stale, so the staleness suffix is present on both and a suffix that varied
# by day (a day count instead of `stale since YYYY-MM-DD`) would show. Copy A is reindexed on the
# first day; copy B on the first day and then again on the second, as an unchanged store is on
# any later day. Every INDEX.md in A and B must then be byte-identical — including the
# `last regenerated` stamp, which only moves when a persona line changes (comparing two copies
# each written on a different day would differ by that stamp by design, so the second day's
# write goes onto a store the first day has already brought current). The step also fails if
# the suffix is absent, which would make the comparison vacuous.
section "index-determinism"
det_out=$("$PYTHON" - "$scripts" "$golden_store" <<'PYEOF' 2>&1
import contextlib
import datetime as dt
import io
import shutil
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True
scripts_dir, store = Path(sys.argv[1]), Path(sys.argv[2])
sys.path.insert(0, str(scripts_dir))
import reindex as rx  # noqa: E402

DAY1, DAY2 = dt.date(2027, 1, 10), dt.date(2027, 1, 11)


def write(copy, day):
    rx._today = lambda: day
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return rx.main(["--store", str(copy), "--context", "golden"])


def indexes(copy):
    return {p.relative_to(copy).as_posix(): p.read_bytes() for p in sorted(copy.rglob("INDEX.md"))}


saved_today = rx._today
tmp = Path(tempfile.mkdtemp(prefix="personas-det-"))
try:
    a, b = tmp / "a", tmp / "b"
    shutil.copytree(store, a)
    shutil.copytree(store, b)
    rcs = [write(a, DAY1), write(b, DAY1), write(b, DAY2)]
    ia, ib = indexes(a), indexes(b)
finally:
    rx._today = saved_today
    shutil.rmtree(tmp, ignore_errors=True)

if rcs != [0, 0, 0]:
    print("reindex exited non-zero: %s" % rcs)
    sys.exit(1)
golden = ia.get("golden/INDEX.md", b"").decode("utf-8", "replace")
if "| stale" not in golden:
    print("golden/INDEX.md written on %s carries no staleness suffix: the dates no longer "
          "exercise staleness, pick days on which a golden persona is stale" % DAY1)
    sys.exit(1)
if ia != ib:
    for name in sorted(set(ia) | set(ib)):
        if ia.get(name) != ib.get(name):
            print("%s differs between a write on %s and a rewrite on %s:" % (name, DAY1, DAY2))
            la = ia.get(name, b"").decode("utf-8", "replace").splitlines()
            lb = ib.get(name, b"").decode("utf-8", "replace").splitlines()
            for x, y in zip(la, lb):
                if x != y:
                    print("  - " + x)
                    print("  + " + y)
            if len(la) != len(lb):
                print("  (line counts differ: %d vs %d)" % (len(la), len(lb)))
    sys.exit(1)
print("ok: %d INDEX.md file(s) byte-identical across real writes on %s and %s (stale suffix "
      "present)" % (len(ia), DAY1, DAY2))
PYEOF
)
det_rc=$?
printf '%s\n' "$det_out"
if [ $det_rc -eq 0 ]; then echo "index-determinism: ok"; else echo "index-determinism: FAIL"; status=1; fi

# --------------------------------------------------------------------- 8. the 3.9 syntax floor
# dev/check_floor.py (FR-7.1, G1): every script, dev and evals module parsed with
# `ast.parse(..., feature_version=(3, 9))`, then walked for what that parse still lets through
# (PEP 604 unions in annotations, subscripted builtins, parenthesised context managers,
# zip(strict=)). Static, so it guards the floor where this machine has no 3.9 interpreter of
# its own to run the suite on (see check_all_versions.sh). Walrus and removeprefix are legal.
section "syntax-floor"
scan_out=$("$PYTHON" "$root/dev/check_floor.py" "$root" 2>&1)
scan_rc=$?
printf '%s\n' "$scan_out"
if [ $scan_rc -eq 0 ]; then
    echo "syntax-floor: ok (no 3.10+ constructs found by dev/check_floor.py)"
else
    echo "syntax-floor: FAIL"
    status=1
fi

# --------------------------------------------------------------------- 9. ruff
section "ruff"
ruff_bin="${RUFF:-}"
if [ -z "$ruff_bin" ] && command -v ruff >/dev/null 2>&1; then
    ruff_bin=ruff
fi
if [ -z "$ruff_bin" ]; then
    # Skipped by default (ruff is not a repository dependency); a green run that silently
    # dropped a step is exactly what REQUIRE_RUFF=1 exists to prevent in CI.
    if [ "${REQUIRE_RUFF:-}" = "1" ]; then
        echo "ruff: required but not found"
        echo "ruff: FAIL"
        status=1
    else
        echo "ruff: skipped (RUFF unset and ruff not on PATH)"
    fi
else
    # --no-cache: a .ruff_cache directory embeds this machine's absolute paths, which
    # check_generality.sh would then flag; cleanup below also removes it belt-and-suspenders.
    ruff_out=$("$ruff_bin" check --no-cache "$root/skills" "$root/dev" "$root/evals" "$root/beforehand_cli" 2>&1)
    ruff_rc=$?
    printf '%s\n' "$ruff_out"
    if [ $ruff_rc -eq 0 ]; then echo "ruff: ok"; else echo "ruff: FAIL"; status=1; fi
fi

# --------------------------------------------------------------------- 10. evals
section "evals"
evals_sh="$root/evals/run.sh"
if [ -f "$evals_sh" ]; then
    evals_out=$(sh "$evals_sh" --checkers-only 2>&1)
    evals_rc=$?
    printf '%s\n' "$evals_out"
    if [ $evals_rc -eq 0 ]; then echo "evals: ok"; else echo "evals: FAIL"; status=1; fi
else
    echo "evals: skipped (evals/run.sh not found)"
fi

# --------------------------------------------------------------------- 11. cli
# beforehand_cli/test_cli.py (SPEC-1.0 §3): the `beforehand` command installs into a temporary
# HOME, refuses what it must (re-install, symlink, unmarked destination, differing agent),
# uninstalls only what it wrote, bundles the same entry list as dev/build_skill.sh (built on a
# copy, so dist/ is untouched), passes other commands to beforehand.py with its exit code.
section "cli"
cli_test="$root/beforehand_cli/test_cli.py"
if [ -f "$cli_test" ]; then
    cli_out=$("$PYTHON" -B "$cli_test" 2>&1)
    cli_rc=$?
    printf '%s\n' "$cli_out"
    if [ $cli_rc -eq 0 ]; then echo "cli: ok"; else echo "cli: FAIL"; status=1; fi
else
    echo "cli: FAIL (beforehand_cli/test_cli.py not found)"
    status=1
fi
find "$root/beforehand_cli" -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null

# --------------------------------------------------------------------- cleanup
# __pycache__ embeds this machine's absolute source path, which check_generality.sh flags;
# .ruff_cache does the same. Removed always, whether or not the run above passed.
find "$root/skills" "$root/evals" -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null
rm -rf "$root/.ruff_cache"

echo ""
if [ $status -eq 0 ]; then
    echo "check_all: ok"
else
    echo "check_all: FAIL"
fi
exit $status
