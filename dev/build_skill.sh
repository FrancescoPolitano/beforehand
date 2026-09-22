#!/bin/sh
# build_skill.sh — build the distributable `.skill` bundle (SPEC-0.2 FR-7.5).
#
# The repository is a Claude Code plugin (.claude-plugin/plugin.json + skills/ + agents/);
# Claude Cowork and Claude Desktop install a single skill instead, as a zip whose
# one top-level directory is the skill. This produces that zip:
#
#   dist/<name>-<version>.skill     zip of skills/<name>/, rooted at <name>/
#
# `<name>` is the plugin manifest's name, `<version>` its version, so the bundle can never
# claim a version the manifest does not: one file states it.
#
# Excluded from the zip: __pycache__ (it embeds the absolute source path of the machine that
# built it) and .DS_Store. Nothing else — the test suites and their fixtures ship, because
# `beforehand.py test` is how an installed copy proves itself on the host's interpreter.
#
# The plugin-level agents/persona-reviewer.md and the in-skill copy must be byte-identical:
# the zip carries only the in-skill copy, and a drift between the two would ship a reviewer
# prompt that no longer matches the one Claude Code loads. The build refuses on a drift.
# The hero diagram is duplicated for the same reason — docs/assets/beforehand-loop.svg for the
# root README, skills/<name>/assets/beforehand-loop.svg for the one inside the zip — and is
# checked the same way.
#
# Usage: sh dev/build_skill.sh
# Exit 0 on a built bundle, 1 on any refusal.
set -u

root=$(cd "$(dirname "$0")/.." && pwd)
manifest="$root/.claude-plugin/plugin.json"

[ -f "$manifest" ] || { echo "build_skill: missing .claude-plugin/plugin.json"; exit 1; }
command -v zip >/dev/null 2>&1 || { echo "build_skill: zip is not on PATH"; exit 1; }

PYTHON="${PYTHON:-python3}"
read_field() {
  "$PYTHON" - "$manifest" "$1" <<'PYEOF'
import json
import sys
with open(sys.argv[1], encoding="utf-8") as fh:
    print(json.load(fh)[sys.argv[2]])
PYEOF
}

name=$(read_field name) || { echo "build_skill: cannot read name from the manifest"; exit 1; }
version=$(read_field version) || { echo "build_skill: cannot read version from the manifest"; exit 1; }
skill="$root/skills/$name"

[ -d "$skill" ] || { echo "build_skill: the manifest names '$name' but skills/$name does not exist"; exit 1; }

# Identical copies (S13): one text shipped in two places, and a drift between the two would
# ship something that no longer matches its twin. The build refuses on a drift. One record per
# pair: first|second|mode|message when a copy is missing|message on a drift|hint.
#   - agents/persona-reviewer.md (what Claude Code loads) and the in-skill copy (the only one
#     the zip carries): mode `file`, byte for byte.
#   - assets/reviewer-examples.md, the fragment the flow pastes inline under "Three examples",
#     and the in-skill reviewer prompt it is pasted into: mode `examples` — the example blocks
#     (the lines indented by four spaces, which is what an example is in both files) must match
#     byte for byte, and the fragment must hold at least one. A third copy of an example that
#     drifts teaches the reviewer a different rule than the one the prompt carries.
#   - docs/assets/beforehand-loop.svg (the root README's hero diagram) and the in-skill copy the
#     bundle carries so the skill README renders it for a host that installs the zip: `file`.
# Only the second file of the examples pair is checked for presence there: the prompt it is
# compared with was checked by the first record.
in_skill="$skill/agents/persona-reviewer.md"
while IFS='|' read -r first second mode missing_msg drift_msg hint; do
  [ -n "$first" ] || continue
  if [ "$mode" = examples ]; then
    present=0
    [ -f "$first" ] && present=1
  else
    present=0
    [ -f "$first" ] && [ -f "$second" ] && present=1
  fi
  if [ "$present" -ne 1 ]; then
    echo "build_skill: $missing_msg"
    exit 1
  fi
  if [ "$mode" = examples ]; then
    first_blocks=$(awk '/^    [^ ]/' "$first")
    second_blocks=$(awk '/^    [^ ]/' "$second")
    same=0
    [ -n "$first_blocks" ] && [ "$first_blocks" = "$second_blocks" ] && same=1
  else
    same=0
    cmp -s "$first" "$second" && same=1
  fi
  if [ "$same" -ne 1 ]; then
    echo "build_skill: $drift_msg"
    echo "  $hint"
    exit 1
  fi
done <<PAIRS
$root/agents/persona-reviewer.md|$in_skill|file|one of the two persona-reviewer.md copies is missing|agents/persona-reviewer.md and skills/$name/agents/persona-reviewer.md differ|the two copies are one prompt; reconcile them before building
$skill/assets/reviewer-examples.md|$in_skill|examples|skills/$name/assets/reviewer-examples.md is missing|assets/reviewer-examples.md and agents/persona-reviewer.md hold different examples|the two example blocks are one text; reconcile them before building
$root/docs/assets/beforehand-loop.svg|$skill/assets/beforehand-loop.svg|file|one of the two beforehand-loop.svg copies is missing|docs/assets/beforehand-loop.svg and skills/$name/assets/beforehand-loop.svg differ|the two copies are one diagram; reconcile them before building
PAIRS

dist="$root/dist"
out="$dist/$name-$version.skill"
mkdir -p "$dist"
rm -f "$out"

# Built from a staging copy so the zip's paths are `<name>/...` with no repository prefix and
# no machine path anywhere in the archive.
stage=$(mktemp -d "${TMPDIR:-/tmp}/$name-build.XXXXXX")
cleanup() { rm -rf "$stage"; }
trap cleanup EXIT INT TERM

cp -R "$skill" "$stage/$name"
find "$stage/$name" -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null
find "$stage/$name" -name '.DS_Store' -delete 2>/dev/null

(cd "$stage" && zip -q -r -X "$out" "$name") || { echo "build_skill: zip failed"; exit 1; }

echo "built dist/$name-$version.skill"
# The listing is a report, not a build step: without unzip the bundle is still built, and
# saying so beats printing empty lines under a heading.
if command -v unzip >/dev/null 2>&1; then
  echo "archive root: $(unzip -Z1 "$out" | sed 's|/.*||' | sort -u | tr '\n' ' ')"
  echo "top-level entries:"
  unzip -Z1 "$out" | sed "s|^$name/||" | awk -F/ 'NF>0 && $1!="" {print ($0 ~ /\// ? $1 "/" : $1)}' \
    | sort -u | sed 's/^/  /'
  echo "files: $(unzip -Z1 "$out" | grep -cv '/$')"
else
  echo "report: unzip not found, the archive listing is skipped"
fi
exit 0
