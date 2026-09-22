#!/usr/bin/env python3
"""Shared helpers for the behavioural-eval checkers (SPEC-0.2 FR-7.1).

Python 3.9+, stdlib only, no network. Two jobs:

  1. `--manifest <store>` prints one `<sha1>  <relative path>` line per file in a store,
     sorted. The runner takes this before the host CLI runs; a checker compares it with
     the state afterwards, which is how "this flow wrote nothing" becomes an assertion
     instead of an impression.
  2. The `Checks` class gives every checker the same output shape as the script test
     suites: one `ok`/`FAIL` line per assertion, a count, exit 0 or 1.

A checker asserts named things — a file exists, a lint gate passes, a count falls in a
range, a phrase is present or absent, a digest is unchanged. "Output is non-empty" is not
an assertion: it passes on a transcript that did the wrong thing.
"""
import hashlib
import json
import os
import re
import sys

sys.dont_write_bytecode = True  # no __pycache__ under the repository root (generality gate)


# ---------------------------------------------------------------- store manifest

def manifest(store):
    """Return a list of "<sha1>  <relpath>" lines for every file under `store`."""
    lines = []
    for dirpath, dirnames, filenames in os.walk(store):
        dirnames[:] = sorted(d for d in dirnames if d != "__pycache__")
        for name in sorted(filenames):
            if name == ".DS_Store":
                continue
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, store)
            with open(full, "rb") as fh:
                digest = hashlib.sha1(fh.read()).hexdigest()
            lines.append("%s  %s" % (digest, rel))
    return sorted(lines, key=lambda row: row.split("  ", 1)[1])


def read_manifest(path):
    """Read a manifest file into a dict {relpath: sha1}."""
    out = {}
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line:
                continue
            digest, rel = line.split("  ", 1)
            out[rel] = digest
    return out


def manifest_map(store):
    """Manifest of the live store as a dict {relpath: sha1}."""
    out = {}
    for line in manifest(store):
        digest, rel = line.split("  ", 1)
        out[rel] = digest
    return out


def store_diff(before_path, store, ignore=()):
    """Paths added, removed or changed between a recorded manifest and the store now.

    `ignore` is a tuple of relative paths (or path prefixes ending in "/") excluded from
    the comparison — the usage log, typically, which every flow is supposed to append to.
    Returns (added, removed, changed), each a sorted list of relative paths.
    """
    before = read_manifest(before_path)
    after = manifest_map(store)

    def skipped(rel):
        for pat in ignore:
            if rel == pat or (pat.endswith("/") and rel.startswith(pat)):
                return True
        return False

    b = set(k for k in before if not skipped(k))
    a = set(k for k in after if not skipped(k))
    added = sorted(a - b)
    removed = sorted(b - a)
    changed = sorted(k for k in (a & b) if before[k] != after[k])
    return added, removed, changed


def sha1_of(path):
    with open(path, "rb") as fh:
        return hashlib.sha1(fh.read()).hexdigest()


# ---------------------------------------------------------------- transcript helpers

def read_text(path):
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)


def read_transcript(path):
    """A transcript with HTML comments removed.

    The synthetic fixtures under `evals/expected/` and `evals/cases/*/mutations/` carry a
    header saying what they are, and that header names the very tags and phrases the
    checkers look for. Stripping comments makes the header inert, so a fixture fails on what
    it does wrong and never on what it says about itself.
    """
    return HTML_COMMENT.sub("", read_text(path))


REVIEW_BLOCK = re.compile(r"```json personas-review\s*\n(.*?)\n```", re.S)


def review_blocks(transcript):
    """Every ```json personas-review``` block in a transcript, parsed.

    Returns a list of (dict, raw_text). A block that does not parse comes back as
    (None, raw_text), so a checker can fail on it by name rather than crash.
    """
    out = []
    for m in REVIEW_BLOCK.finditer(transcript):
        raw = m.group(1)
        try:
            out.append((json.loads(raw), raw))
        except ValueError:
            out.append((None, raw))
    return out


def usage_rows(store):
    """Every row of the store's usage.jsonl, parsed; [] when the log does not exist."""
    path = os.path.join(store, "usage.jsonl")
    if not os.path.exists(path):
        return []
    rows = []
    for line in read_text(path).splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except ValueError:
            rows.append({"_unparseable": line})
    return rows


def has_any(text, terms):
    """True when any term appears in text, case-insensitively."""
    low = text.lower()
    return any(t.lower() in low for t in terms)


# ---------------------------------------------------------------- fabrication guards
#
# The failure these catch is a persona inventing a position on a topic its file does not
# reach — a number it was never observed giving. Phrase shapes cannot catch it: "I would
# need an annual exit at month twelve" and "three years with a break clause each year would
# be acceptable" are the same fabrication, and the second has no first-person marker at all.
# Worse, a phrase guard punishes the correct answer too, because a persona citing its own
# evidenced red line ("a rollback window under thirty minutes") uses exactly the same shape.
#
# So the guard compares against the EVIDENCE, not against the shape. Every quantity in the
# persona's own file(s) and in the user's own turns is legitimate; a quantity that appears in
# neither was invented, whatever sentence carries it.
#
# What this does NOT catch, and cannot: an invented position with no quantity in it ("I would
# sign that"). That belongs to the rubric — see evals/README.md and evals/cases/g/rubric.md.

NUM_WORDS = ["one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
             "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen",
             "eighteen", "nineteen", "twenty", "thirty", "forty", "fifty", "sixty",
             "seventy", "eighty", "ninety", "hundred", "thousand", "half", "quarter"]

# "one", "half" and "quarter" are ordinary English words ("a question like this one", "half
# of what you asked"), so they count as a quantity only when a unit follows them. Every other
# number word counts on its own.
BARE_EXCLUDED = {"one", "half", "quarter"}

_UNIT = (r"per\s+cent|percent|years?|yrs?|months?|weeks?|days?|hours?|hrs?|minutes?|mins?|"
         r"seconds?|secs?|points?|pts?")
_NUM = r"\d+(?:[.,]\d+)?|" + "|".join(NUM_WORDS)
# A digit directly preceded by `#`, `[`, `-` or `wl-` is an identifier, not a quantity; the
# lookbehind keeps those out even when the id survived the pass above.
QUANTITY_RE = re.compile(
    r"(?<![\w.#\[-])(" + _NUM + r")(?![\w])(?:\s*(%)|[\s\-]+(" + _UNIT + r")\b)?", re.I)

# Bookkeeping is not a position. Dates, clock times, schema versions, prediction and row ids
# (`P1`, `R2`), watchlist and issue ids (`[wl-01]`, `#3`) and hyphenated ids appear in every
# transcript the skill produces and no persona ever invented one, so they are removed before
# tokenising rather than argued about afterwards.
_DATEISH = re.compile(r"\d{4}-\d{2}-\d{2}|\b\d{1,2}:\d{2}(?::\d{2})?\b|"
                      r"\bschema:\s*\d+\.\d+|\b(?:19|20)\d{2}\b|"
                      r"\[[^\]\n]*\d[^\]\n]*\]|"           # [wl-01], [P3], any bracketed id
                      r"\b[A-Za-z]{1,3}-?\d+\b|"              # P1, R2, wl-01, v2
                      r"#\s*\d+(?:\.\d+)*")                  # #3, #n.1


def _fold(s):
    """Lowercase, collapse whitespace, drop punctuation — the comparison form."""
    return re.sub(r"[^a-z0-9. ]+", "", " ".join(str(s).split()).lower()).strip()


def _unit_norm(unit):
    if unit is None:
        return None
    if "%" in unit:
        return "percent"
    u = _fold(unit).rstrip(".")
    if u in ("per cent", "percent"):
        return "percent"
    u = re.sub(r"s$", "", u)
    return {"yr": "year", "hr": "hour", "min": "minute", "sec": "second", "pt": "point"}.get(u, u)


def quantities(text):
    """Every quantity occurrence in `text`, as (number, unit-or-None, sentence)."""
    clean = _DATEISH.sub(" ", text)
    out = []
    for m in QUANTITY_RE.finditer(clean):
        num = _fold(m.group(1))
        unit = _unit_norm(m.group(2) or m.group(3))
        out.append((num, unit, " ".join(clean[max(0, m.start() - 90):m.end() + 90].split())))
    return out


# The sections of a persona file that ARE evidence about the person. Everything else in the
# file is bookkeeping about the file — the frontmatter (`decision_weight: 3`, aliases like
# "Guest 1"), `## Reliability` ("0 cycles"), `## Watchlist` (candidate material, by definition
# not yet evidence) and `## Evidence freshness`. Indexing those would licence a persona to
# fabricate "a number around 3" because 3 is its own decision weight, which is exactly the
# horoscope this guard exists to stop.
EVIDENCE_SECTIONS = ("mandate and incentives", "judgment criteria", "recurring objections",
                     "red lines", "language and dissent style", "panel dynamics",
                     "background and track record", "background")


def evidence_text(persona_text):
    """The bodies of a persona file's judgment sections, concatenated.

    Uses `personas_lib.sections` so the heading parsing is the skill's own — including the
    `<!-- last evidence: … -->` note being metadata about a section rather than part of its
    name.
    """
    lib = _personas_lib()
    out = []
    for sec in lib.sections(persona_text):
        if sec.level != 2:
            continue
        if sec.title.strip().lower() in EVIDENCE_SECTIONS:
            out.append(persona_text[sec.body_start:sec.end])
    return "\n".join(out)


_LIB = []


def _personas_lib():
    if not _LIB:
        here = os.path.dirname(os.path.abspath(__file__))
        scripts = os.path.join(here, "..", "..", "skills", "beforehand", "scripts")
        sys.path.insert(0, os.path.abspath(scripts))
        import personas_lib  # noqa: E402
        _LIB.append(personas_lib)
    return _LIB[0]


def quantity_index(texts):
    """The set of quantities that the evidence makes legitimate.

    `texts` are already-narrowed evidence — persona section bodies via `evidence_text()`, and
    the user's own prompt or turns. Returns (numbers, pairs): bare numbers, and
    (number, unit) pairs.
    """
    numbers = set()
    pairs = set()
    for text in texts:
        for num, unit, _ in quantities(text):
            numbers.add(num)
            if unit:
                pairs.add((num, unit))
    return numbers, pairs


def unevidenced_quantities(text, index):
    """Quantities in `text` that the evidence does not carry.

    A quantity with a unit has to match the same number *and* unit — "thirty minutes" in the
    persona's red line does not licence "thirty per cent" in its answer. A bare number only
    has to match a number the evidence carries.
    """
    numbers, pairs = index
    bad = []
    for num, unit, context in quantities(text):
        if unit is None:
            if num in BARE_EXCLUDED or num in numbers:
                continue
            bad.append(("%s" % num, context))
        else:
            if (num, unit) in pairs:
                continue
            bad.append(("%s %s" % (num, unit), context))
    return bad


SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n{2,}")


def sentences(text):
    """Split text into sentences, keeping it dumb and predictable."""
    return [s.strip() for s in SENTENCE_SPLIT.split(text) if s.strip()]


TURN_BOUNDARY = re.compile(
    r"(?m)^\s*\*\*[^*\n]{1,60}:\*\*|^\s*---+\s*$|"
    r"\[(?:grounds|no basis|red line):[^\]\n]*\]")


def turn_before(text, pos, cap=900):
    """The persona text that leads up to a tag at `pos`.

    Bounded by the previous turn marker, separator or *complete* tag, and capped, so a
    tag's own turn is what gets inspected rather than the whole conversation. The boundary
    swallows the whole of a preceding tag, brackets included: a tag's topic legitimately
    carries a number ("renewal pricing for year four") and is not a position the persona
    took.
    """
    start = 0
    for m in TURN_BOUNDARY.finditer(text, 0, pos):
        start = m.end()
    return text[max(start, pos - cap):pos]


def section(text, heading_terms, stop_prefix="## "):
    """The body of the first markdown section whose heading contains one of the terms.

    Returns "" when no heading matches. Used to assert that a theme is in the *fix list*
    rather than merely somewhere in a long report.
    """
    lines = text.splitlines()
    start = None
    level = 0
    for i, line in enumerate(lines):
        if line.startswith("#"):
            hashes = len(line) - len(line.lstrip("#"))
            title = line.lstrip("#").strip().lower()
            if start is None:
                if any(t.lower() in title for t in heading_terms):
                    start = i + 1
                    level = hashes
            elif hashes <= level:
                return "\n".join(lines[start:i])
    if start is None:
        return ""
    return "\n".join(lines[start:])


# ---------------------------------------------------------------- assertion runner

class Checks(object):
    """One `ok`/`FAIL` line per assertion, a count, exit 0 or 1."""

    def __init__(self, case):
        self.case = case
        self.items = []

    def ok(self, name, condition, detail=""):
        self.items.append((name, bool(condition), detail))
        return bool(condition)

    def finish(self):
        fails = [i for i in self.items if not i[1]]
        for name, good, detail in self.items:
            line = ("ok   " if good else "FAIL ") + name
            if not good and detail:
                line += " -> " + str(detail).replace("\n", " ")[:300]
            print(line)
        print("\ncase %s: %d/%d passed" % (self.case, len(self.items) - len(fails), len(self.items)))
        sys.exit(1 if fails else 0)


def args(argv, case):
    """Parse the pinned checker argv: <store> <transcript> [workdir]."""
    if len(argv) < 3:
        sys.stderr.write("usage: check.py <store> <transcript> [workdir]   (case %s)\n" % case)
        sys.exit(1)
    store, transcript = argv[1], argv[2]
    workdir = argv[3] if len(argv) > 3 else os.path.dirname(os.path.abspath(transcript))
    return store, transcript, workdir


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--manifest":
        for line in manifest(sys.argv[2]):
            print(line)
        sys.exit(0)
    sys.stderr.write("usage: evalcheck.py --manifest <store>\n")
    sys.exit(1)
