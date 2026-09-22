#!/bin/sh
# Case (a) setup: make the budget owner a Wanted stakeholder with sources on file.
#
# The golden fixture already carries a persona for every speaker in its sources, so there
# is nothing left to author. This removes one persona from the TEMP COPY only, declares the
# same decision function under `## Wanted` in the temp `context.md`, and rebuilds the index
# so the store is internally consistent again. The committed fixture is never touched.
#
# $1 = temp store, $2 = repository root
set -eu
store=$1
root=$2
ctx="$store/golden"

rm -f "$ctx/personas/cfo-astrid.md"

cat >> "$ctx/context.md" <<'EOF'
- chief financial officer | economic buyer | speaks in the kickoff, the steering call and the June email
EOF

PYTHONDONTWRITEBYTECODE=1 python3 "$root/skills/beforehand/scripts/beforehand.py" \
    reindex --store "$store" >/dev/null
