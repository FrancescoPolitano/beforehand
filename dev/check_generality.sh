#!/bin/sh
# Generality gate: the repository is publishable at every moment (SPEC-0.2 §0, FR-1.2).
set -u
root=$(cd "$(dirname "$0")/.." && pwd)
status=0
# Anecdote/name patterns: historical planning docs (SPEC*/PLAN*/HARNESS-SURVEY) and review
# logs used to legitimately quote past field work and were excluded here by basename; as of
# Task 23 they live outside the repository (~/.beforehand-dev/), so the only exclusion left is
# this script itself. The term-list grep below still excludes nothing.
# grep exits 0 on a hit, 1 on none, and >= 2 when it could not read something (an unreadable
# file, a bad pattern file): that last case is a failure, never a clean pass (G8).
scan() {
  label=$1
  shift
  hits=$(grep "$@")
  rc=$?
  if [ $rc -eq 0 ]; then
    echo "$hits"
    status=1
  elif [ $rc -ge 2 ]; then
    [ -n "$hits" ] && echo "$hits"
    echo "generality: the $label scan could not complete (grep exit $rc)"
    status=1
  fi
}
# The public identity (SPEC-1.0 §1): dev/public-identity.txt lists the few exact strings the
# project publishes on purpose (the author's name, the repository slug, the owner handle). The
# name-pattern and term-list scans run on a stripped view of the tree — a temporary copy of
# every file with each of those strings removed (exact, case-sensitive) — so an allowed string
# never matches, while any other occurrence of a forbidden name or term still does, including
# what remains of a longer word that starts with an allowed string. The path scan and the junk
# scan run on the tree itself and ignore the file.
identity="$root/dev/public-identity.txt"
view=$(mktemp -d "${TMPDIR:-/tmp}/generality-view.XXXXXX") || { echo "generality: cannot create a temporary view"; exit 1; }
work=$(mktemp -d "${TMPDIR:-/tmp}/generality-work.XXXXXX") || { rm -rf "$view"; echo "generality: cannot create a temporary directory"; exit 1; }
trap 'rm -rf "$view" "$work"' EXIT
: > "$work/strip.sed"
if [ -f "$identity" ]; then
  bad=$(grep -nvE '^(#.*|[[:space:]]*|[A-Za-z0-9 /._-]+)$' "$identity")
  if [ -n "$bad" ]; then
    printf '%s\n' "$bad" | sed 's/^/dev\/public-identity.txt:/'
    echo "generality: dev/public-identity.txt may hold only letters, digits, space and / . _ -"
    exit 1
  fi
  # Longest first, so a string that contains another is removed whole.
  grep -vE '^(#|[[:space:]]*$)' "$identity" | awk '{ print length($0) "\t" $0 }' | sort -rn |
    cut -f2- | sed -e 's/\./\\./g' -e 's/.*/s#&##g/' > "$work/strip.sed"
fi
find "$root" \( -name .git -o -path "$root/dist" \) -prune -o -type f -print |
  while IFS= read -r f; do
    rel=${f#"$root"/}
    mkdir -p "$view/$(dirname "$rel")" &&
      LC_ALL=C sed -f "$work/strip.sed" "$f" > "$view/$rel" 2>/dev/null ||
      printf '%s\n' "$rel" >> "$work/unread"
  done
# scan_view LABEL GREP-ARGS... PATTERN: like scan, on the stripped view; hits are reported with
# the file's real path. A file the view could not copy makes the scan incomplete (G8).
scan_view() {
  label=$1
  shift
  if [ -s "$work/unread" ]; then
    sed 's/^/could not read: /' "$work/unread"
    echo "generality: the $label scan could not complete (unreadable file)"
    status=1
    return
  fi
  hits=$(cd "$view" && grep "$@" .)
  rc=$?
  if [ $rc -eq 0 ]; then
    # Each hit is reported as the real file's path, line number and unstripped line.
    printf '%s\n' "$hits" | while IFS= read -r hit; do
      # `./<file>:<n>:<line>`, where <file> may itself contain a colon: the file part is the
      # shortest prefix that names a real file and is followed by a line number.
      rel="" tail=${hit#./} shown=""
      case $hit in ./*) ;; *) tail="" ;; esac
      while [ -z "$shown" ] && case $tail in *:*) true ;; *) false ;; esac; do
        rel=$rel${tail%%:*}
        tail=${tail#*:}
        n=${tail%%:*}
        case $n in
          ''|*[!0-9]*) ;;
          *) if [ -f "$root/$rel" ] && [ "$tail" != "$n" ]; then
               shown=$(printf '%s:%s:' "$root/$rel" "$n"; sed -n "${n}p" "$root/$rel")
             fi ;;
        esac
        rel=$rel:
      done
      if [ -n "$shown" ]; then printf '%s\n' "$shown"; else printf '%s\n' "$hit"; fi
    done
    status=1
  elif [ $rc -ge 2 ]; then
    [ -n "$hits" ] && echo "$hits"
    echo "generality: the $label scan could not complete (grep exit $rc)"
    status=1
  fi
}
anecdote_pat='from the field|\bwe saw\b|the case offers|used to report|\bF[r]ancesco\b|\bP[o]litano\b'
scan_view anecdote -rniE --exclude-dir=.git --exclude-dir=dist --exclude=check_generality.sh "$anecdote_pat"
# Path patterns: no exclusions beyond .git and dist — a leaked /Users or /home path is a leak
# everywhere, including inside a compiled .pyc, which embeds the absolute source path of the
# machine that built it; that is exactly the leak this gate exists to catch, so binary matches
# are kept. dist/ is excluded because it holds only the build output of dev/build_skill.sh: a
# deflated zip of skills/, whose bytes are already scanned here in their source form and which
# a line-based grep can only report as an unreadable binary match either way.
path_pat='/Users/[a-z]|/home/[a-z]'
scan path -rniE --exclude-dir=.git --exclude-dir=dist "$path_pat" "$root"
if [ "${1:-}" != "--patterns-only" ] && [ -n "${BEFOREHAND_DEV_TERMS:-}" ] && [ -f "$BEFOREHAND_DEV_TERMS" ]; then
  scan_view term-list -rniF --exclude-dir=.git --exclude-dir=dist -f "$BEFOREHAND_DEV_TERMS"
fi
for junk in __pycache__ '.backup-*' skill-workspace .superpowers; do
  found=$(find "$root" -name "$junk" -not -path '*/.git/*' -not -path "$root/dist/*" | head -1)
  [ -n "$found" ] && { echo "$found: working material inside the repository"; status=1; }
done
if [ -d "$root/.git" ] && command -v git >/dev/null 2>&1 && [ -n "${BEFOREHAND_DEV_TERMS:-}" ] && [ -f "$BEFOREHAND_DEV_TERMS" ]; then
  history_hits=$(git -C "$root" log -p --all 2>/dev/null | grep -niF -f "$BEFOREHAND_DEV_TERMS")
  if [ -n "$history_hits" ]; then
    count=$(printf '%s\n' "$history_hits" | wc -l | tr -d ' ')
    echo "history: git log -p --all contains $count term-list hit(s) — informational for the 1.0 adoption, not a gate"
  fi
fi
[ $status -eq 0 ] && echo "generality: clean"
exit $status
