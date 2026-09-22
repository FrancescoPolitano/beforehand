#!/bin/sh
# Router budget and vocabulary gate (SPEC-0.2 FR-3.3, FR-3.4, FR-2.5).
#
# SKILL.md is loaded on every trigger, so its size is a running cost: the gate holds it to
# 120 lines and 1,500 estimated tokens (words x 1.35), keeps the frontmatter description
# under the 400 characters the host truncates at, and proves that the one invocation form
# (`python3 $SKILL/scripts/beforehand.py <command>`) has no bare `python3 scripts/` left.
#
# Vocabulary: the router must read the same for a board memo as for a purchase, so the
# sales-specific words are counted outside fenced blocks, inline backtick spans and
# double-quoted strings — examples live inside those and are meant to name roles.
# Scope: FR-2.5's acceptance is `grep -rn 'python3 scripts/' skills/beforehand` -> 0 and
# FR-3.4's is 0 vocabulary hits over SKILL.md *and* the references, so both of those checks
# fail on a reference offence by default. --report-references downgrades the two
# reference-scoped counts to a printed number for local iteration on SKILL.md alone; it
# never relaxes anything measured on SKILL.md itself.
set -u

root=$(cd "$(dirname "$0")/.." && pwd)
skill="$root/skills/beforehand"
router="$skill/SKILL.md"

max_lines=120
max_tokens=1500
max_desc=400
vocab_pat='\b(deal|client|vendor|CFO|CTO)\b'

strict_refs=1
case "${1:-}" in
  --report-references) strict_refs=0 ;;
  '') ;;
  *) echo "usage: check_router.sh [--report-references]"; exit 1 ;;
esac

[ -f "$router" ] || { echo "check_router: missing $router"; exit 1; }

status=0
fail() { status=1; }

# Prose only: drop fenced code blocks, then inline `code` spans, then "quoted examples".
prose() {
  awk 'BEGIN{f=0} /^[ \t]*```/{f=!f; next} f==0{print}' "$1" \
    | sed -e 's/`[^`]*`//g' -e 's/"[^"]*"//g'
}

# An odd number of fence toggles means the file ends inside a fence, and prose() would then
# silently drop everything after the opener — a vocabulary count of 0 on a file nobody read.
# True (exit 0) when the fence is left open.
fence_unclosed() {
  awk '/^[ \t]*```/{n++} END{exit (n % 2) ? 0 : 1}' "$1"
}

# --- 1. Lines -----------------------------------------------------------------
lines=$(wc -l < "$router" | tr -d ' ')
if [ "$lines" -gt "$max_lines" ]; then
  echo "lines: $lines (max $max_lines) FAIL"
  fail
else
  echo "lines: $lines (max $max_lines) ok"
fi

# --- 2. Estimated tokens ------------------------------------------------------
words=$(wc -w < "$router" | tr -d ' ')
tokens=$((words * 135 / 100))
if [ "$tokens" -gt "$max_tokens" ]; then
  echo "tokens: $tokens (max $max_tokens; $words words x 1.35) FAIL"
  fail
else
  echo "tokens: $tokens (max $max_tokens; $words words x 1.35) ok"
fi

# --- 3. Frontmatter description ----------------------------------------------
# Read through personas_lib (S13, G3), in one $PYTHON call, so the router is parsed by the
# same frontmatter reader as every store file instead of an awk that understood one shape
# only (a one-line quoted description used to read as 0 chars and pass). SKILL.md's
# `description: >` is a folded block scalar, which the FR-4.8 subset refuses, so a pre-pass
# folds any `key: >` / `key: |` block into its text (indented lines joined with one space,
# indentation stripped — what the host actually reads) and hands every other line to
# read_frontmatter. A missing or empty description fails: 0 chars is a zero read, not a pass.
PYTHON="${PYTHON:-python3}"
desc_out=$("$PYTHON" - "$skill/scripts" "$router" "$max_desc" <<'PYEOF' 2>&1
import re
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, sys.argv[1])
import personas_lib as lib  # noqa: E402

text = lib.read_text_lenient(sys.argv[2])
max_desc = int(sys.argv[3])
span = lib.frontmatter_span(text)
if not span:
    print("description: no frontmatter block in SKILL.md FAIL")
    sys.exit(1)
lines = text[span[0]:span[1]].rstrip("\n").split("\n")
kept, folded, i = [lines[0]], {}, 1
while i < len(lines) - 1:
    m = re.match(r"^([A-Za-z_][\w-]*):[ \t]*[>|][+-]?[ \t]*$", lines[i].rstrip("\r"))
    if not m:
        kept.append(lines[i])
        i += 1
        continue
    i += 1
    body = []
    while i < len(lines) - 1 and (not lines[i].strip() or lines[i][0] in " \t"):
        body.append(lines[i].strip())
        i += 1
    folded[m.group(1)] = re.sub(r"\s+", " ", " ".join(b for b in body if b)).strip()
kept.append(lines[-1])
try:
    fm = lib.read_frontmatter("\n".join(kept) + "\n")
except lib.FrontmatterError as e:
    print("description: SKILL.md frontmatter unreadable: %s FAIL" % (e,))
    sys.exit(1)
fm.update(folded)
desc = fm.get("description")
if not isinstance(desc, str) or not desc.strip():
    print("description: missing or empty FAIL")
    sys.exit(1)
n = len(desc)
if n > max_desc:
    print("description: %d chars (max %d) FAIL" % (n, max_desc))
    sys.exit(1)
print("description: %d chars (max %d) ok" % (n, max_desc))
PYEOF
)
desc_rc=$?
printf '%s\n' "$desc_out"
[ $desc_rc -eq 0 ] || fail

# --- 4. One invocation form (FR-2.5) -----------------------------------------
bare_all=$(grep -rn 'python3 scripts/' "$skill" | wc -l | tr -d ' ')
bare_sk=$(grep -cn 'python3 scripts/' "$router" || true)
bare_sk=${bare_sk:-0}
bare_refs=$((bare_all - bare_sk))
if [ "$bare_sk" -gt 0 ]; then
  echo "bare invocations SKILL.md: $bare_sk (max 0) FAIL"
  grep -n 'python3 scripts/' "$router" | sed 's/^/  /'
  fail
else
  echo "bare invocations SKILL.md: 0 (max 0) ok"
fi
if [ "$strict_refs" -eq 1 ]; then
  if [ "$bare_refs" -gt 0 ]; then
    echo "bare invocations elsewhere: $bare_refs (max 0) FAIL"
    grep -rn 'python3 scripts/' "$skill" | grep -v '/SKILL.md:' | sed "s|^$root/|  |"
    fail
  else
    echo "bare invocations elsewhere: 0 (max 0) ok"
  fi
else
  echo "bare invocations elsewhere: $bare_refs (reported only, --report-references)"
fi

# --- 5. Vocabulary, SKILL.md (fails) -----------------------------------------
if fence_unclosed "$router"; then
  echo "FAIL: unclosed fence in ${router#"$root"/}"
  fail
fi
sk_vocab=$(prose "$router" | grep -ciE "$vocab_pat" || true)
sk_vocab=${sk_vocab:-0}
if [ "$sk_vocab" -gt 0 ]; then
  echo "vocabulary SKILL.md: $sk_vocab lines (max 0) FAIL"
  prose "$router" | grep -niE "$vocab_pat" | sed 's/^/  /'
  fail
else
  echo "vocabulary SKILL.md: 0 lines (max 0) ok"
fi

# --- 6. Vocabulary, references (fails unless --report-references) -------------
ref_total=0
ref_detail=""
for f in "$skill"/references/*.md; do
  [ -f "$f" ] || continue
  if fence_unclosed "$f"; then
    echo "FAIL: unclosed fence in ${f#"$root"/}"
    fail
  fi
  n=$(prose "$f" | grep -ciE "$vocab_pat" || true)
  n=${n:-0}
  ref_total=$((ref_total + n))
  [ "$n" -gt 0 ] && ref_detail="$ref_detail $(basename "$f"):$n"
done
if [ "$strict_refs" -eq 1 ]; then
  if [ "$ref_total" -gt 0 ]; then
    echo "vocabulary references: $ref_total lines (max 0)$ref_detail FAIL"
    fail
  else
    echo "vocabulary references: 0 lines (max 0) ok"
  fi
else
  echo "vocabulary references: $ref_total lines (reported only, --report-references)$ref_detail"
fi

if [ $status -eq 0 ]; then
  echo "router: within budget"
else
  echo "router: over budget"
fi
exit $status
