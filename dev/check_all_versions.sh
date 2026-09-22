#!/bin/sh
# check_all_versions.sh — runs check_all.sh once per Python interpreter this machine has,
# among python3.9 .. python3.14 on PATH and every ~/.pyenv/versions/*/bin/python3 in that
# same range (SPEC-0.2 FR-7.2, §10). There is no hosted CI (a maintainer decision, not a
# stopgap before 1.0): this is the per-interpreter matrix, run by hand.
#
# Where this machine has no 3.9 interpreter at all, check_all.sh's own syntax-floor step
# (dev/check_floor.py) is what still guards the 3.9 floor (see its header). This script only
# exercises whatever interpreters actually exist here; it never fails because 3.9 itself is
# missing.
#
# Usage: dev/check_all_versions.sh
# Honours RUFF (passed through to every check_all.sh run); PYTHON is set per interpreter
# and any inherited value is overridden.
#
# Prints one summary line per interpreter version (never an absolute path — this file's
# output is meant to be pasted into a note or a verification record) and exits 1 if any of
# them failed.
set -u

root=$(cd "$(dirname "$0")/.." && pwd)

# ---- 1. find candidate interpreters --------------------------------------------------
candidates=""
for v in 3.9 3.10 3.11 3.12 3.13 3.14; do
    p=$(command -v "python$v" 2>/dev/null) || continue
    candidates="$candidates $p"
done
for p in "$HOME"/.pyenv/versions/*/bin/python3; do
    [ -x "$p" ] || continue
    candidates="$candidates $p"
done

# ---- 2. probe each candidate, keep the first working binary per distinct version ------
# (a pyenv shim and a pyenv versions/*/bin/python3 for the same version both show up above;
# a shim also fails outright when that version isn't the active one — command -v finding
# it on PATH does not mean it runs). Restricted to 3.9-3.14: an older interpreter this
# machine happens to have (e.g. a leftover 3.6) is not a supported floor and is not this
# script's job to exercise.
seen_versions=""
run_list=""
for p in $candidates; do
    ver=$("$p" -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])' 2>/dev/null) || continue
    major=$(echo "$ver" | cut -d. -f1)
    minor=$(echo "$ver" | cut -d. -f2)
    [ "$major" = 3 ] || continue
    case "$minor" in
        9|10|11|12|13|14) ;;
        *) continue ;;
    esac
    case " $seen_versions " in
        *" $ver "*) continue ;;
    esac
    seen_versions="$seen_versions $ver"
    run_list="$run_list $ver=$p"
done

if [ -z "$run_list" ]; then
    echo "check_all_versions: no usable python3.9-3.14 interpreter found on this machine"
    echo "(check_all.sh's syntax-floor step still guards the 3.9 floor on whichever"
    echo " interpreter runs it)"
    exit 1
fi

# ---- 3. run check_all.sh once per version --------------------------------------------
status=0
for entry in $run_list; do
    ver=${entry%%=*}
    bin=${entry#*=}
    echo ""
    echo "==== python $ver ===="
    PYTHON="$bin" sh "$root/dev/check_all.sh"
    rc=$?
    if [ $rc -eq 0 ]; then
        echo "$ver: ok"
    else
        echo "$ver: FAIL"
        status=1
    fi
done

echo ""
if [ $status -eq 0 ]; then
    echo "check_all_versions: ok ($(echo "$seen_versions" | wc -w | tr -d ' ') interpreter(s))"
else
    echo "check_all_versions: FAIL"
fi
exit $status
