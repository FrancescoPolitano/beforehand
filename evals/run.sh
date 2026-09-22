#!/bin/sh
# evals/run.sh — behavioural evals for the beforehand skill (SPEC-0.2 FR-7.1).
#
# Usage:
#   sh evals/run.sh [options] [case ...]        default: --checkers-only, cases a b c d e f g
#
# Options:
#   --checkers-only   do not call the host CLI; replay the synthetic expected transcripts
#                     and store overlays from evals/expected/ and run every checker against
#                     them. Deterministic, free, and what dev/check_all.sh runs. This is the
#                     default when no mode flag is given — a live run always needs --live
#                     stated explicitly.
#   --live            call the host CLI once per case. Costs a session per case. Never the
#                     default: it must be asked for by name.
#   --keep            keep the temporary stores and print where they are.
#   -h, --help        this text.
#
# Environment:
#   EVALS_CLI                 host CLI, default `claude`. It is called as
#                             `$EVALS_CLI -p "<prompt>" --allowedTools Read,Write,Bash
#                              --add-dir <tmp store>`, with BEFOREHAND_STORE pointing at a
#                             throwaway copy of the golden fixture store. It is never
#                             pointed at ~/.beforehand.
#   PYTHON                    interpreter for every internal invocation (the manifest tool,
#                             the checkers, the library unit check), default `python3`. The
#                             repository's per-version runner sets it, so the checkers are
#                             exercised on each supported interpreter, not only the default.
#   EVALS_OUT                 directory results are written under, one subfolder per date.
#                             Live default `$HOME/.beforehand-dev/evals`, outside the repository.
#                             With --checkers-only and EVALS_OUT unset, results go to the run's
#                             temporary work directory and vanish with it (unless --keep): a
#                             replay records nothing anywhere unless asked to.
#   EVALS_ALLOW_USER_SKILL=1  run live case (g) even while a user-level skill named beforehand
#                             exists under ~/.claude/skills/. Without it (g) is refused: that
#                             skill loads in both arms of the on/off comparison, so the
#                             "examples off" arm could still see the real examples.
# No eval ever modifies a shipped file. Case (g) needs the skill with one asset blanked, so
# it builds a throwaway PLUGIN COPY of skills/beforehand in the workdir, blanks the asset in the
# copy, and loads that copy with --plugin-dir. If the host CLI has no such flag, (g) is
# rubric-only: the runner says so and the maintainer records two runs deliberately.
#
# Each case gets its own copy of skills/beforehand/scripts/test_fixtures/store; the committed
# fixture is never written to. A live run writes its results to
# ${EVALS_OUT:-$HOME/.beforehand-dev/evals}/<date>/<case>.md — never inside the repository,
# scrubbed of any home-directory path. --checkers-only writes `<case>-checkers.md` (so a replay
# never overwrites the record of a real run) under $EVALS_OUT/<date>/ when EVALS_OUT is set, and
# into the temporary work directory otherwise. The `results:` header prints $HOME as `~`.
# Exit 1 if any deterministic checker fails, or if live case (g) is refused.

set -u

root=$(cd "$(dirname "$0")/.." && pwd)
evals="$root/evals"
fixture="$root/skills/beforehand/scripts/test_fixtures/store"
CLI=${EVALS_CLI:-claude}
PY=${PYTHON:-python3}
PYTHONDONTWRITEBYTECODE=1
export PYTHONDONTWRITEBYTECODE

mode=checkers
keep=no
cases=""
for arg do
  case "$arg" in
    --checkers-only) mode=checkers ;;
    --live)          mode=live ;;
    --keep)          keep=yes ;;
    -h|--help)       sed -n '2,/^[^#]/p' "$0" | sed -n '/^#/p' | sed 's/^# \{0,1\}//'
                     exit 0 ;;
    -*)              echo "run.sh: unknown option $arg" >&2; exit 1 ;;
    *)               cases="$cases $arg" ;;
  esac
done
[ -n "$cases" ] || cases="a b c d e f g"

scrub() {
  sed -e 's#/Users/[A-Za-z0-9._-]*#<home>#g' -e 's#/home/[A-Za-z0-9._-]*#<home>#g'
}

today=$(date +%Y-%m-%d)
tmpbase=${TMPDIR:-/tmp}
work=$(mktemp -d "${tmpbase%/}/personas-evals.XXXXXX")
cleanup() {
  [ "$keep" = yes ] || rm -rf "$work"
}
trap cleanup EXIT INT TERM
# G6: a checkers-only replay (what check_all runs) writes nothing outside its work directory
# unless EVALS_OUT asks it to; a live run keeps its record outside the repository.
if [ -n "${EVALS_OUT:-}" ]; then
  out="$EVALS_OUT/$today"
elif [ "$mode" = checkers ]; then
  out="$work/results"
else
  out="$HOME/.beforehand-dev/evals/$today"
fi
mkdir -p "$out"
# $HOME shown as `~`: this header is pasted into notes and verification records.
case "$out" in
  "$HOME"/*) out_shown="~/${out#"$HOME"/}" ;;
  *)         out_shown=$out ;;
esac
[ "$out" = "$work/results" ] && [ "$keep" != yes ] && out_shown="$out_shown (temporary; set EVALS_OUT to keep)"

status=0
ran=0
echo "beforehand evals — mode: $mode — results: $out_shown"
echo ""

# The library the checkers are built on, checked first: if the quantity tokeniser or the
# evidence index is wrong, every fabrication guard downstream is wrong in the same way.
if "$PY" "$evals/lib/test_evalcheck.py" >"$work/lib.out" 2>&1; then
  echo "lib: ok    ($(grep -c '^ok   ' "$work/lib.out") assertions)"
else
  echo "lib: FAIL"
  grep '^FAIL ' "$work/lib.out" | scrub | sed 's/^/     /'
  status=1
fi

for c in $cases; do
  cdir="$evals/cases/$c"
  if [ ! -d "$cdir" ]; then
    echo "$c: FAIL no such case directory"
    status=1
    continue
  fi
  w="$work/$c"
  mkdir -p "$w"
  store="$w/store"
  cp -R "$fixture" "$store"

  if [ -f "$cdir/setup.sh" ]; then
    if ! sh "$cdir/setup.sh" "$store" "$root" >"$w/setup.log" 2>&1; then
      echo "$c: FAIL setup.sh"
      scrub <"$w/setup.log"
      status=1
      continue
    fi
  fi

  "$PY" "$evals/lib/evalcheck.py" --manifest "$store" >"$w/manifest-before.txt"
  transcript="$w/transcript.md"

  if [ "$mode" = checkers ]; then
    exp="$evals/expected/$c-transcript.md"
    if [ ! -f "$exp" ]; then
      echo "$c: FAIL no expected transcript at evals/expected/$c-transcript.md"
      status=1
      continue
    fi
    cp "$exp" "$transcript"
    [ -f "$evals/expected/$c-off-transcript.md" ] && cp "$evals/expected/$c-off-transcript.md" "$w/transcript-off.md"
    [ -d "$evals/expected/$c-store" ] && cp -R "$evals/expected/$c-store/." "$store/"
  else
    if [ "$c" = g ]; then
      # G7: a user-level skill loads in BOTH arms of the on/off comparison, so the
      # examples-off arm would still see the real examples; refuse rather than grade that.
      user_skills=""
      for us in "$HOME/.claude/skills/beforehand"; do
        if [ -e "$us" ] || [ -L "$us" ]; then
          user_skills="$user_skills ~/${us#"$HOME"/}"
        fi
      done
      if [ -n "$user_skills" ] && [ "${EVALS_ALLOW_USER_SKILL:-}" != 1 ]; then
        for us in $user_skills; do
          echo "$c: REFUSED live — a user-level skill exists at $us: it would load in both arms"
        done
        echo "     of the examples on/off comparison. Move it aside for this run, or set"
        echo "     EVALS_ALLOW_USER_SKILL=1 to run (g) anyway."
        echo ""
        status=1
        continue
      fi
      if ! "$CLI" --help 2>/dev/null | grep -q -- '--plugin-dir'; then
        echo "$c: SKIPPED live — $CLI has no --plugin-dir, so the examples-off run cannot"
        echo "     load a copied skill. (g) is rubric-only on this host: run case (b)'s"
        echo "     prompt twice yourself, once against a skill copy whose"
        echo "     assets/reviewer-examples.md is blank, and record both transcripts."
        echo "     evals/README.md says how; the shipped file is never edited in place."
        echo ""
        continue
      fi
      # Two plugin copies of the skill, identical but for the one asset. Nothing under
      # skills/beforehand is written to: the copies live and die in the workdir.
      for variant in on off; do
        pdir="$w/plugin-$variant"
        mkdir -p "$pdir/.claude-plugin" "$pdir/skills"
        cp -R "$root/skills/beforehand" "$pdir/skills/beforehand"
        printf '{"name": "beforehand-eval-%s", "description": "eval copy of the beforehand skill"}\n' \
            "$variant" >"$pdir/.claude-plugin/plugin.json"
      done
      printf '# Reviewer examples — blanked for eval case (g), in a throwaway copy\n' \
          >"$w/plugin-off/skills/beforehand/assets/reviewer-examples.md"
      store_off="$w/store-off"
      cp -R "$fixture" "$store_off"
      BEFOREHAND_STORE="$store" "$CLI" -p "$(cat "$cdir/prompt.md")" \
          --allowedTools Read,Write,Bash --add-dir "$store" \
          --plugin-dir "$w/plugin-on" >"$transcript" 2>&1
      BEFOREHAND_STORE="$store_off" "$CLI" -p "$(cat "$cdir/prompt.md")" \
          --allowedTools Read,Write,Bash --add-dir "$store_off" \
          --plugin-dir "$w/plugin-off" >"$w/transcript-off.md" 2>&1
    else
      BEFOREHAND_STORE="$store" "$CLI" -p "$(cat "$cdir/prompt.md")" \
          --allowedTools Read,Write,Bash --add-dir "$store" >"$transcript" 2>&1
    fi
  fi

  if [ -f "$cdir/check.py" ]; then
    "$PY" "$cdir/check.py" "$store" "$transcript" "$w" >"$w/check.out" 2>&1
    rc=$?
  else
    echo "no check.py: rubric-graded case, read the transcript" >"$w/check.out"
    rc=0
  fi
  [ $rc -eq 0 ] || status=1
  ran=$((ran + 1))

  # Fixtures the checker is measured against, replayed on every run and costing nothing.
  #   mutations/  a transcript that does the wrong thing while keeping every surface signal
  #               the happy path has. Each MUST fail; one that passes means the checker has
  #               become a rubber stamp.
  #   positives/  a transcript that does the right thing in a way a careless guard would
  #               punish — a persona citing a number its own file evidences. Each MUST pass;
  #               one that fails means the checker is calling correct behaviour a defect.
  neg_total=0
  neg_ok=0
  pos_total=0
  pos_ok=0
  for kind in mutations positives; do
    [ -d "$cdir/$kind" ] || continue
    for fix in "$cdir/$kind"/*.md; do
      [ -f "$fix" ] || continue
      fname=$(basename "$fix" .md)
      fdir="$w/$kind-$fname"
      mkdir -p "$fdir"
      cp -R "$fixture" "$fdir/store"
      [ -f "$cdir/setup.sh" ] && sh "$cdir/setup.sh" "$fdir/store" "$root" >/dev/null 2>&1
      "$PY" "$evals/lib/evalcheck.py" --manifest "$fdir/store" >"$fdir/manifest-before.txt"
      [ -d "$evals/expected/$c-store" ] && cp -R "$evals/expected/$c-store/." "$fdir/store/"
      "$PY" "$cdir/check.py" "$fdir/store" "$fix" "$fdir" >"$fdir/check.out" 2>&1
      frc=$?
      if [ "$kind" = mutations ]; then
        neg_total=$((neg_total + 1))
        if [ $frc -eq 0 ]; then
          echo "$c: FAIL must-fail fixture $fname PASSED — the checker is a rubber stamp"
          status=1
        elif ! grep -q '^FAIL ' "$fdir/check.out"; then
          # G8: a non-zero exit with no named failure is a checker that crashed (a traceback),
          # not one that rejected the transcript; it proves nothing about the guard.
          echo "$c: FAIL must-fail fixture $fname exited $frc with no FAIL line — the checker crashed"
          tail -5 "$fdir/check.out" | scrub | sed 's/^/       /'
          status=1
        else
          neg_ok=$((neg_ok + 1))
        fi
      else
        pos_total=$((pos_total + 1))
        if [ $frc -eq 0 ]; then
          pos_ok=$((pos_ok + 1))
        elif ! grep -q '^FAIL ' "$fdir/check.out"; then
          # G8: a non-zero exit with no named failure is a checker that crashed (a traceback),
          # not one that rejected the transcript; it proves nothing about the guard.
          echo "$c: FAIL must-pass fixture $fname exited $frc with no FAIL line — the checker crashed"
          tail -5 "$fdir/check.out" | scrub | sed 's/^/       /'
          status=1
        else
          echo "$c: FAIL must-pass fixture $fname FAILED — the checker punishes correct behaviour"
          grep '^FAIL ' "$fdir/check.out" | scrub | sed 's/^/       /'
          status=1
        fi
      fi
    done
  done

  if [ "$mode" = checkers ]; then
    result="$out/$c-checkers.md"
  else
    result="$out/$c.md"
  fi

  {
    echo "# eval case $c — $today"
    echo ""
    echo "- mode: $mode"
    echo "- host CLI: $CLI"
    echo "- checker exit: $rc"
    [ -f "$cdir/rubric.md" ] && echo "- rubric-graded: read evals/cases/$c/rubric.md and record the verdict here"
    echo ""
    echo "## Prompt"
    echo ""
    echo '```'
    cat "$cdir/prompt.md"
    echo '```'
    echo ""
    echo "## Transcript (last 120 lines)"
    echo ""
    echo '```'
    tail -120 "$transcript"
    echo '```'
    if [ -f "$w/transcript-off.md" ]; then
      echo ""
      echo "## Transcript, examples off (last 120 lines)"
      echo ""
      echo '```'
      tail -120 "$w/transcript-off.md"
      echo '```'
    fi
    echo ""
    echo "## Checks"
    echo ""
    echo '```'
    cat "$w/check.out"
    echo '```'
    if [ "$neg_total" -gt 0 ] || [ "$pos_total" -gt 0 ]; then
      echo ""
      echo "## Fixtures the checker is measured against"
      echo ""
      echo "- must-fail: $neg_ok/$neg_total failed as required"
      echo "- must-pass: $pos_ok/$pos_total passed as required"
    fi
  } | scrub >"$result"

  if [ $rc -eq 0 ]; then
    neg_note=""
    [ "$neg_total" -gt 0 ] && neg_note=", $neg_ok/$neg_total must-fail"
    [ "$pos_total" -gt 0 ] && neg_note="$neg_note, $pos_ok/$pos_total must-pass"
    echo "$c: ok    ($(grep -c '^ok   ' "$w/check.out" 2>/dev/null || echo 0) assertions$neg_note)"
  else
    echo "$c: FAIL"
    grep '^FAIL ' "$w/check.out" | scrub | sed 's/^/     /'
  fi
done

echo ""
[ "$keep" = yes ] && echo "temporary stores kept in $work"
if [ $status -eq 0 ]; then
  echo "evals: $ran case(s) green"
else
  echo "evals: failures above"
fi
exit $status
