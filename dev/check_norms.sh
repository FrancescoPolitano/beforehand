#!/bin/sh
# One norm, one file (SPEC-0.2 §0, FR-3.2): every phrase in dev/norm-anchors.txt must match
# exactly one file under skills/beforehand/, and that file must be references/evidence-model.md.
# Two or more means the rule is restated somewhere instead of cited as
# references/evidence-model.md#<anchor>; zero, or one file that is not evidence-model.md,
# means the anchor no longer sits where the norm belongs and the list is stale.
set -u
root=$(cd "$(dirname "$0")/.." && pwd)
anchors="$root/dev/norm-anchors.txt"
tree="$root/skills/beforehand"
home="$root/skills/beforehand/references/evidence-model.md"
status=0
total=0
bad=0

[ -f "$anchors" ] || { echo "check_norms: missing $anchors"; exit 1; }
[ -d "$tree" ] || { echo "check_norms: missing $tree"; exit 1; }

while IFS= read -r phrase || [ -n "$phrase" ]; do
  case "$phrase" in
    ''|'#'*) continue ;;
  esac
  total=$((total + 1))
  # reviewer-examples.md is a prompt fragment pasted verbatim into the reviewer's context,
  # not a place where a norm is stated; it is excluded (FR-3.6).
  files=$(grep -rlF --exclude=reviewer-examples.md -- "$phrase" "$tree")
  if [ -z "$files" ]; then
    n=0
    list=""
  else
    n=$(printf '%s\n' "$files" | wc -l | tr -d ' ')
    list=$(printf '%s\n' "$files" | sed "s|^$root/||" | tr '\n' ' ' | sed 's/ $//')
  fi
  if [ "$n" -ne 1 ]; then
    echo "anchor \"$phrase\": $n files ($list)"
    bad=$((bad + 1))
    status=1
  elif [ "$files" != "$home" ]; then
    # exactly one file, but not the one allowed to state the norm
    echo "anchor \"$phrase\": 1 file, not evidence-model.md ($list)"
    bad=$((bad + 1))
    status=1
  fi
done < "$anchors"

if [ $status -eq 0 ]; then
  echo "norms: $total anchors, one file each"
else
  echo "norms: $bad of $total anchors not stated exactly once"
fi
exit $status
