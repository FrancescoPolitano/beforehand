#!/usr/bin/env python3
"""Verify that Fact excerpts in a persona file exist in their referenced sources.

Deterministic, stdlib-only, no network. By default this is a report, not a gate:
exit code 0, the caller reads the statuses and acts on them. With --lint it becomes a
gate: exit 1 when any Fact is NOT FOUND or UNPARSEABLE.

Modes:
  verify_quotes.py <persona.md> [--sources-root DIR] [--lint] [--json]
      Audit every Fact tag in a persona file.
  verify_quotes.py --excerpts <excerpts.json> --source <file>
      Ingestion mode: check a JSON array of proposed excerpt strings against one
      source, BEFORE the user confirms the persona. Fabrication is caught at the
      moment it is introduced, when the source is by definition readable.

Tag grammar accepted (the canonical form is the first one; the others are tolerated
because they appear in real stores, and a linter that silently skips them lets a
persona full of unverifiable Facts pass as clean):
  (Fact — "excerpt", <source ref>, <type>, <provenance>, <date>)
  (Fact — "excerpt one" and "excerpt two", <source ref>, ...)      several excerpts
  (Fact — lead-in words: "excerpt", <source ref>, ...)              lead-in ignored
  "excerpt" (Fact — <source ref>, ...)                              quote abutting the tag
  "excerpt" (Fact, <source ref>, ...)                               comma form
  (Fact <- Inference <date> via <source> — "excerpt", <source ref>, ...)  promotion
  (... "same source" / "ibid" / a locale's own phrasing ...)        inherits the previous ref

Statuses (per excerpt):
  VERIFIED      excerpt found in the source (normalized, filler tokens ignored)
  NOT FOUND     source is readable but the excerpt is not in it -> likely fabricated
  UNVERIFIABLE  source missing, remote, not plain text, or not a path -> cannot check.
                Split into `by-construction` (a remote system or a binary: it will never be
                checkable, and it is old debt) and `fixable` (a path written badly or a file
                not yet saved locally: it is a new mistake, and it can be repaired). A single
                counter that never goes down is a counter people stop reading.
  MISPLACED     excerpt is in the same item but outside the tag, and it does check out
                against the source -> tidy it, but it is NOT an unevidenced claim
  APPROXIMATE   excerpt matches the source only approximately (a substituted word) -> warn;
                quote the source verbatim. MISPLACED takes precedence when both apply
  UNPARSEABLE   a Fact tag with no excerpt anywhere -> cannot ever be checked; rewrite it

MISPLACED exists because the two situations used to be reported identically. Writing prose,
the quote lands in the sentence where the reader needs it and the tag closes the bullet;
that is a formatting slip. A tag with no excerpt anywhere is the gravest violation the model
defines. Seeing the same error message for both teaches you to stop reading it.

Matching an excerpt against its source (`match_excerpt`, SPEC-0.3.1 FR-1.1): one path for
every source length. Exact when, after normalisation, the excerpt is a run of the source's
words (filler tokens such as "um" ignored on both sides). Otherwise the excerpt's rarest
words anchor candidate positions, and at each the excerpt is compared word by word with as
many source words: it matches approximately only if at most one word in eight differs, no
differing word is a prefix/suffix of its counterpart, a number or shorter than 4
characters, and the characters still agree (MATCH_THRESHOLD). No word can be inserted or
dropped. A short [bracket] in the excerpt is the author's placeholder for 0-3 source words:
standing for none keeps a match exact, standing for some makes it approximate (the reason
names them), and it may never stand for a word shorter than 4 characters or a number. An
approximate match is APPROXIMATE, a warning: the excerpt is repaired to the source's words.
"""
import argparse
import functools
import itertools
import json
import re
import sys
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

sys.dont_write_bytecode = True  # G5: set before any sibling import

sys.path.insert(0, str(Path(__file__).resolve().parent))
# The tag grammar, the section finder and the file readers live in the library: this module
# owns what to do with a Fact tag, not how to find one (SPEC-0.2 FR-2.1).
from personas_lib import (  # noqa: E402
    LocaleError,
    atomic_write,
    decode_lenient,
    item_end,
    item_start,
    locale_regexes,
    parse_tags,
    persona_sources_root,
    persona_store,
    read_text_lenient,
    resolve_source,
    sections,
    strip_frontmatter,
)

# The tag grammar's locale-aware bits (same-source shorthand, excerpt joiners) live in
# personas_lib.parse_tags itself, resolved lazily there. main() below calls
# locale_regexes() once, right after parse_args(), purely so an unknown BEFOREHAND_LOCALE is
# reported here too, at the moment this command actually runs — never at this module's own
# import, and never before argparse, which would make `--help` unreadable under a locale
# typo.

MATCH_THRESHOLD = 0.85
# Unverifiable for good (a remote system, a binary) vs unverifiable for now (a bad path, a
# source not yet saved). Only the second kind is anyone's fault, and only it can go down.
BY_CONSTRUCTION = ("remote URL", "not plain text")


# --------------------------------------------------------------------------- text utils
# soft hyphen, zero-width space/non-joiner/joiner, word joiner, BOM: invisible, never a word break
_INVISIBLE_RE = re.compile("[\u00ad\u200b-\u200d\u2060\ufeff]")
# a bracket of at most this many words is an editorial insertion ("[the client]", a
# timestamp); a longer one is words the author wants read as quoted, so it must match (A13)
EDITORIAL_MAX_WORDS = 4
# in an excerpt, an editorial bracket stands for 0..PLACEHOLDER_SPAN source words at its
# position ("we told [the client]" for "we told them"); its own words are never evidence
PLACEHOLDER_SPAN = 3
WILD = "\x00"
# an apostrophe or hyphen between two word characters glues its parts: "can't" is "can" +
# "t" glued, so a match may not start or end inside it -- "we can" is not a run of "we
# can't sign", "binding agreement" is not a run of "non-binding agreement" -- while
# "three year term" still matches "three-year term" (typography, not words). Elsewhere (a
# trailing "e'" typed for "è") it is punctuation and goes
GLUE = "\x01"
_JOINER_RE = re.compile(r"(?<=\w)['\u2018\u2019\u02bc`\-\u2010\u2011](?=\w)")
# a + or - directly before a digit is a sign ("-5" is not "5"); every other non-word
# character is a separator
_PUNCT_RE = re.compile(r"(?<![\w+-])([+-])(?=\d)|[^\w\s" + WILD + GLUE + "]")


def _normalize(text: str, placeholders: bool, glue: bool = False) -> str:
    text = _INVISIBLE_RE.sub("", text)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace(WILD, " ").replace(GLUE, " ")

    def bracket(m):
        inner = m.group(1)
        if len(inner.split()) > EDITORIAL_MAX_WORDS:
            return " " + inner + " "
        return " " + WILD + " " if placeholders else " "

    text = re.sub(r"\[([^\]]*)\]", bracket, text)
    text = _JOINER_RE.sub(GLUE if glue else " ", text.casefold())
    text = _PUNCT_RE.sub(lambda m: m.group(1) or " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize(text: str) -> str:
    """Case, punctuation and accent insensitive. Accents are folded on purpose: a
    transcript saved in ASCII and an excerpt typed with accents describe the same words.
    A short editorial bracket ("[the client]", a timestamp) is dropped."""
    return _normalize(text, False)


@functools.lru_cache(maxsize=256)
def _normalized(text: str) -> str:
    return normalize(text)


def _fillers():
    return locale_regexes()["filler_tokens"]


def _glued_tokens(text: str, placeholders: bool):
    """-> [(token, glued_left, glued_right)] without filler tokens: a token glued to its
    neighbour by an in-word apostrophe or hyphen says so, so a match cannot start or end
    inside a compound."""
    fillers = _fillers()
    out = []
    for word in _normalize(text, placeholders, glue=True).split():
        parts = [x for x in word.split(GLUE) if x]
        for i, part in enumerate(parts):
            if part not in fillers:
                out.append((part, i > 0, i < len(parts) - 1))
    return out


@functools.lru_cache(maxsize=256)
def _source_core(source_text: str):
    """-> (tokens, positions, padded, glued, absorb): the normalised source's tokens with
    filler tokens removed, each token's indices in that list, the list joined and
    space-padded for whole-token lookups, (glued_left, glued_right) per token, and the set of
    indices of tokens a bracket may stand for (`_absorbable`). Cached per raw source
    text, so a persona with dozens of Facts against one long transcript tokenises it once,
    not once per Fact."""
    triples = _glued_tokens(source_text, False)
    tokens = tuple(t for t, _, _ in triples)
    glued = tuple((a, b) for _, a, b in triples)
    positions = {}
    for i, t in enumerate(tokens):
        positions.setdefault(t, []).append(i)
    absorb = frozenset(i for i, t in enumerate(tokens) if _absorbable(t))
    return tokens, positions, " " + " ".join(tokens) + " ", glued, absorb


SHORT_TOKEN = 4


def _refused_pair(a: str, b: str) -> bool:
    """A substitution that can flip meaning, refused (rule 3): one side a proper prefix or
    suffix of the other (possible/impossible, can/cannot, approve/approved, 3/30); either
    side containing a digit (2025/2026); or either side shorter than 4 characters
    (not/now, no/a, is/as, won/will) -- short words carry negation and grammar, not the
    transcription drift an approximate match exists for."""
    return (a.startswith(b) or b.startswith(a) or a.endswith(b) or b.endswith(a)
            or any(ch.isdigit() for ch in a + b)
            or len(a) < SHORT_TOKEN or len(b) < SHORT_TOKEN)


def match_excerpt(excerpt: str, source_text: str):
    """-> (kind, detail): kind "exact", "approximate" or None (SPEC-0.3.1 FR-1.1).

    Both sides are normalised and their filler tokens (the locale's `filler_tokens`)
    dropped, so an "um" said or omitted never matters. exact: the excerpt's tokens are a run
    of the source's tokens; detail is [].

    approximate: one path for every source length. The excerpt's rarest tokens (as many as
    the substitutions it may carry, plus one, so at least one is unchanged) anchor candidate
    positions; at each, the excerpt is compared with the same number of source tokens,
    position by position. No word can be inserted or deleted by construction; the position
    is accepted with at most max(1, n // 8) substituted words, none of them a prefix/suffix
    of its counterpart, a number or shorter than 4 characters (either side), and a
    character ratio >= MATCH_THRESHOLD. The first accepted position in source order wins;
    detail is its substituted (excerpt, source) spans. The verdict depends only on the
    excerpt and the source text at that position, never on what else the source holds.

    A bracket of at most EDITORIAL_MAX_WORDS words in the excerpt ("[the client]") is a
    placeholder for 0..PLACEHOLDER_SPAN source words at its position; its content is the
    author's, never evidence. Absorbing none keeps the match exact; absorbing some caps it at
    approximate, with a (bracket, absorbed words, "placeholder") entry in detail; an absorbed
    word shorter than 4 characters or holding a digit is refused. A longer bracket is quoted
    text and must match (A13).
    """
    core = [t for t, _, _ in _glued_tokens(excerpt, True)]
    if not [t for t in core if t != WILD]:
        return None, []
    src, positions, padded, glued, absorb = _source_core(source_text)
    if WILD not in core:
        maybe_exact = (" " + " ".join(core) + " ") in padded
        return _match_at_anchors(core, src, positions, glued, maybe_exact)
    slots = [i for i, t in enumerate(core) if t == WILD]
    if len(slots) > 3:     # bound the expansions (4^3); a fourth bracket matches nothing
        slots, core = slots[:3], [t for i, t in enumerate(core) if t != WILD or i in slots[:3]]
    labels = _bracket_labels(excerpt, len(slots))
    shifted = {}      # offset -> the absorbable indices shifted by it, shared by expansions
    # absorbing nothing: the excerpt without its brackets, which alone can be exact
    words = [t for t in core if t != WILD]
    found = _match_at_anchors(words, src, positions, glued,
                              (" " + " ".join(words) + " ") in padded, with_start=True)
    if found[0] == "exact":
        return "exact", []
    best = found if found[0] else None
    # absorbing words: approximate at best, so the earliest accepted position in the source
    # wins, then the fewest substitutions (maybe_exact=False: each scan stops at its first)
    for counts in itertools.product(range(PLACEHOLDER_SPAN + 1), repeat=len(slots)):
        if not any(counts):
            continue
        expanded, owner, k = [], [], 0
        for t in core:
            if t == WILD:
                expanded.extend([WILD] * counts[k])
                owner.extend([k] * counts[k])
                k += 1
            else:
                expanded.append(t)
                owner.append(None)
        found = _match_at_anchors(expanded, src, positions, glued, False, with_start=True,
                                  owner=owner, labels=labels, absorb=absorb, shifted=shifted)
        if found[0] and (best is None or _rank(found) < _rank(best)):
            best = found
    return (best[0], best[1]) if best else (None, [])


def _rank(found):
    """Earliest in the source first; at one position, the expansion with fewer substituted
    words (a bracket standing for "them" beats one standing for "that" plus a substitution)."""
    return found[2], sum(len(d[0].split()) for d in found[1] if len(d) == 2)


def _bracket_labels(excerpt: str, n: int):
    """The excerpt's first n placeholder brackets as the author wrote them ("[the client]"),
    for the reason; "[...]" if the raw text and the normalised one disagree on the count."""
    raw = [m.group(0) for m in re.finditer(r"\[([^\]]*)\]", _INVISIBLE_RE.sub("", excerpt))
           if len(m.group(1).split()) <= EDITORIAL_MAX_WORDS]
    return raw[:n] if len(raw) >= n else ["[...]"] * n


def _absorbable(token: str) -> bool:
    """A source word a bracket may stand for: not a short word (negation and grammar live
    there: "not", "no") and not a number ("30") -- else a bracket hides the claim."""
    return len(token) >= SHORT_TOKEN and not any(ch.isdigit() for ch in token)


def _match_at_anchors(core, src, positions, glued, maybe_exact, with_start=False,
                      owner=None, labels=None, absorb=None, shifted=None):
    """The position-by-position comparison of `match_excerpt`. A WILD token (a placeholder
    word) matches any `_absorbable` source token and is neither a substitution nor part of
    the ratio; `owner[i]` names its bracket, and a position where a bracket absorbed words
    is approximate, naming them. A position whose first or last source token is glued
    outward (inside "non-binding", "can't") is refused. With `maybe_exact`, an exact
    position anywhere beats the first approximate one; without, the first accepted position
    wins."""
    first = None
    n = len(core)
    words = [t for t in core if t != WILD]
    max_sub = max(1, len(words) // 8)
    present = sorted((t for t in set(words) if t in positions), key=lambda t: (len(positions[t]), t))
    starts = set()
    for tok in present[:max_sub + 1]:
        offsets = [i for i, t in enumerate(core) if t == tok]
        for p in positions[tok]:
            starts.update(p - o for o in offsets)
    ex_text = " ".join(words)
    wild = [i for i in range(n) if core[i] == WILD]
    for i in wild:      # prune: a start is viable only where every placeholder word is absorbable
        if i not in shifted:
            shifted[i] = {q - i for q in absorb}
        starts &= shifted[i]
    for start in sorted(x for x in starts if 0 <= x <= len(src) - n):
        if glued[start][0] or glued[start + n - 1][1]:
            continue                    # the match would start or end inside a compound
        diff = []
        for i in range(n):
            if core[i] != WILD and core[i] != src[start + i]:
                diff.append(i)
                if len(diff) > max_sub:
                    break
        if len(diff) > max_sub:
            continue
        if any(_refused_pair(core[i], src[start + i]) for i in diff):
            continue
        window = src[start:start + n]
        seen = " ".join(w for w, t in zip(window, core) if t != WILD)
        if SequenceMatcher(None, ex_text, seen, autojunk=False).ratio() < MATCH_THRESHOLD:
            continue
        subs, run = [], []
        for i in diff + [None]:
            if run and (i is None or i != run[-1] + 1):
                subs.append((" ".join(core[j] for j in run), " ".join(window[j] for j in run)))
                run = []
            if i is not None:
                run.append(i)
        for k in sorted(set(owner[i] for i in wild)):
            subs.append((labels[k], " ".join(window[i] for i in wild if owner[i] == k),
                         "placeholder"))
        found = ("approximate" if subs else "exact", subs, start)
        if not subs or not maybe_exact:
            return found if with_start else found[:2]
        if first is None:
            first = found
    if first is not None:
        return first if with_start else first[:2]
    return (None, [], None) if with_start else (None, [])


def excerpt_in_source(excerpt: str, source_text: str) -> bool:
    """True if the excerpt is in the source, exactly or approximately (panel uses this)."""
    return match_excerpt(excerpt, source_text)[0] is not None


@functools.lru_cache(maxsize=256)
def _read_resolved(path_str: str):
    path = Path(path_str)
    try:
        raw = path.read_bytes()
    except OSError as e:
        return None, f"unreadable ({e.__class__.__name__})"
    if b"\x00" in raw[:1024]:
        return None, "not plain text (binary/PDF)"
    return strip_frontmatter(decode_lenient(raw)), ""


def read_source(ref: str, sources_root: Path, store=None):
    """Return (text, reason). text=None when unverifiable, with the reason why. Resolution is
    personas_lib.resolve_source's: a relative ref resolves under sources_root only, never
    the working directory (A3); `store`, when known, makes the reason's root store-relative."""
    path, reason = resolve_source(ref, sources_root, store)
    if path is None:
        return None, reason
    return _read_resolved(str(path.resolve()))


def approximate_reason(detail) -> str:
    """The pinned APPROXIMATE reason: the substituted spans, excerpt side vs source side, then
    what each bracket stood for, joined with " / "."""
    return "excerpt differs from the source: %s — quote the source verbatim" % _difference(detail)


def _difference(detail):
    subs = [d for d in detail if len(d) == 2]
    parts = []
    if subs:
        parts.append('"%s" vs "%s"' % (" / ".join(a for a, _ in subs), " / ".join(b for _, b in subs)))
    parts += ['"%s" stands for "%s"' % (d[0], d[1]) for d in detail if len(d) == 3]
    return " / ".join(parts)


def unverifiable_kind(reason: str) -> str:
    return "by-construction" if any(k in reason for k in BY_CONSTRUCTION) else "fixable"


def check(excerpt: str, ref, sources_root: Path, placement: str = "in-tag", store=None):
    if not ref:
        return "UNVERIFIABLE", "no source reference in the tag"
    text, reason = read_source(ref, sources_root, store)
    if text is None:
        return "UNVERIFIABLE", reason
    kind, detail = match_excerpt(excerpt, text)
    if kind is None:
        return "NOT FOUND", "excerpt not present in a readable source"
    if placement == "misplaced":       # MISPLACED keeps precedence over APPROXIMATE
        reason = ("excerpt is in the item but outside the tag: move it inside "
                  "the parentheses, right after Fact —")
        if kind == "approximate":      # ... without hiding the substitution
            reason += " (and it differs from the source: %s)" % _difference(detail)
        return "MISPLACED", reason
    if kind == "approximate":
        return "APPROXIMATE", approximate_reason(detail)
    return "VERIFIED", ""


def lint_persona(persona_path, sources_root, store=None):
    """Pure function behind the CLI: reindex.py imports this. Status rule (SPEC-0.1 FR-1.2):
    fail = any NOT FOUND or UNPARSEABLE; warn = any structural unverifiable (no ref, not a path,
    inherited), any MISPLACED or APPROXIMATE, or 100% environmental unverifiable; pass
    otherwise. Counts always printed so the
    threshold is auditable. `store`, when the caller knows it, only shortens the root named in
    a not-found reason (store-relative)."""
    persona_path, sources_root = Path(persona_path), Path(sources_root)
    body = read_text_lenient(persona_path)
    tags = parse_tags(body, sources_root)
    results = []
    for t in tags:
        if not t["excerpts"]:
            results.append({"tag": t["n"], "excerpt": "", "ref": t["ref"], "status": "UNPARSEABLE",
                            "reason": "Fact tag without any quoted excerpt: " + t["raw"][:80]})
            continue
        for ex in t["excerpts"]:
            status, reason = check(ex, t["ref"], sources_root, t.get("placement", "in-tag"), store)
            row = {"tag": t["n"], "excerpt": ex, "ref": t["ref"], "status": status, "reason": reason}
            if status == "UNVERIFIABLE":
                row["kind"] = unverifiable_kind(reason)
            results.append(row)
    summary = summarize(results, tags)
    structural = summary["non_path_refs"] + summary["missing_refs"] + summary["inherited_refs"]
    unresolved = sum(1 for r in results
                     if r["status"] == "UNVERIFIABLE" and r["reason"].startswith("source file not found"))
    n = summary["excerpts"]
    if summary["NOT FOUND"] or summary["UNPARSEABLE"]:
        status = "fail"
    elif structural or summary["MISPLACED"] or summary["APPROXIMATE"] or (n and unresolved == n):
        status = "warn"
    else:
        status = "pass"
    parts = []
    if summary["NOT FOUND"]:
        parts.append(f"{summary['NOT FOUND']} not found")
    if summary["UNPARSEABLE"]:
        parts.append(f"{summary['UNPARSEABLE']} unparseable")
    if summary["MISPLACED"]:
        parts.append(f"{summary['MISPLACED']} misplaced excerpts")
    if summary["APPROXIMATE"]:
        parts.append(f"{summary['APPROXIMATE']} approximate excerpts")
    if summary["non_path_refs"] + summary["missing_refs"]:
        parts.append(f"{summary['non_path_refs'] + summary['missing_refs']} refs not a path")
    if summary["inherited_refs"]:
        parts.append(f"{summary['inherited_refs']} inherited refs")
    if unresolved:
        parts.append(f"{unresolved}/{n} unresolved")
    label = status + (" (" + ", ".join(parts) + ")" if parts else " (0 issues)")
    return {"results": results, "summary": summary, "status": status,
            "counts": {"not_a_path": summary["non_path_refs"] + summary["missing_refs"],
                       "unresolved": unresolved, "inherited": summary["inherited_refs"],
                       "excerpts": n}, "label": label, "tags": tags}


# --------------------------------------------------------------------------- reporting
STATUSES = ("VERIFIED", "MISPLACED", "NOT FOUND", "UNVERIFIABLE", "UNPARSEABLE")
# APPROXIMATE is counted like the others but printed on its own line only when K > 0, the
# `joined tags: K` convention: the summary line every existing reader parses is unchanged.
ALL_STATUSES = STATUSES + ("APPROXIMATE",)


def summarize(results, tags):
    counts = {s: sum(1 for r in results if r["status"] == s) for s in ALL_STATUSES}
    return {"tags": len(tags), "excerpts": len(results), **counts,
            "unverifiable_by_construction": sum(1 for r in results if r.get("kind") == "by-construction"),
            "unverifiable_fixable": sum(1 for r in results if r.get("kind") == "fixable"),
            "inherited_refs": sum(1 for t in tags if t["ref_kind"] == "inherited"),
            "non_path_refs": sum(1 for t in tags if t["ref_kind"] == "not-a-path"),
            "missing_refs": sum(1 for t in tags if t["ref_kind"] == "missing"),
            # count groups, not segments: two segments sharing one set of parentheses are one
            # joined tag (FR-2.2), not two
            "joined_tags": len({(t["start"], t["end"]) for t in tags if t.get("joined")})}


def print_report(results, summary, lint: bool):
    for r in results:
        note = f"  [{r['reason']}]" if r["reason"] else ""
        print(f"{r['status']:12s} #{r['tag']:<4s}\"{r['excerpt'][:60]}\" <- {r['ref'] or '-'}{note}")
    if not results:
        print("No Fact tags found.")
        return
    n = summary["excerpts"]
    print(f"\nSummary: {summary['tags']} Fact tag(s), {n} excerpt(s) | "
          + " | ".join(f"{s}: {summary[s]} ({100 * summary[s] // n}%)" for s in STATUSES))
    if summary["joined_tags"]:
        print(f"joined tags: {summary['joined_tags']}")
    if summary.get("APPROXIMATE"):
        print(f"approximate: {summary['APPROXIMATE']}")
    if summary["inherited_refs"] or summary["non_path_refs"] or summary["missing_refs"]:
        print(f"Refs: inherited from 'same source': {summary['inherited_refs']} | "
              f"not a path: {summary['non_path_refs']} | missing: {summary['missing_refs']}"
              "  -> rewrite these as resolvable paths; shorthand survives one edit, not a re-audit")
    if summary["UNVERIFIABLE"]:
        print(f"Unverifiable: {summary['unverifiable_by_construction']} by construction "
              "(a remote system or a binary: it will never be checkable, this is old debt)"
              f" | {summary['unverifiable_fixable']} fixable (a bad path, or a source not yet\n"
              "saved locally: --migrate-ref rewrites a reference once the file exists).")
    if summary["MISPLACED"]:
        print(f"Misplaced: {summary['MISPLACED']} excerpt(s) sit in the item but outside their tag. "
              "They check out\nagainst the source, so this is tidying, not a fabrication: "
              "--fix-tags prints the rewrite.")
    if lint:
        verdict = "FAIL" if (summary["NOT FOUND"] or summary["UNPARSEABLE"]) else "PASS"
        fail_note = (" -> the persona does not enter a panel until every Fact has an excerpt "
                     "that exists in its source")
        print(f"LINT {verdict}: NOT FOUND: {summary['NOT FOUND']}, UNPARSEABLE: {summary['UNPARSEABLE']}"
              + ("" if verdict == "PASS" else fail_note))


# --------------------------------------------------------------------------- content loss
def shape(text):
    """What a persona is made of, in countable terms. Used to spot an edit that lost content."""
    per_section = {}
    for s in sections(text):
        per_section[s.title] = len(re.findall(r"^[ \t]*[-*]\s+", s.body(text), re.M))
    return {"facts": len(re.findall(r"\(Fact\b", text, re.I)), "sections": per_section,
            "bytes": len(text.encode("utf-8"))}


def content_loss(old_text, new_text):
    """-> list of losses. Empty means nothing disappeared.

    The excerpt checker reads one file in isolation: it can tell that what is written is
    true, never that what was written yesterday is still there. A promotion, a rewrite, any
    automated edit can take a section header with it and leave a file that lints perfectly.
    """
    a, b = shape(old_text), shape(new_text)
    out = []
    if b["facts"] < a["facts"]:
        out.append(f"Fact tags {a['facts']} -> {b['facts']}")
    for title, n in a["sections"].items():
        if title not in b["sections"]:
            out.append(f"section lost: {title!r}")
        elif b["sections"][title] < n:
            out.append(f"section {title!r}: {n} -> {b['sections'][title]} entries")
    if b["bytes"] < a["bytes"] * 0.9:
        out.append(f"file shrank by {100 - 100 * b['bytes'] // a['bytes']}%")
    return out


def _ref_fields(body, start, end):
    """-> [(lo, hi, masked, quoted)] for each top-level comma field of the group
    body[start:end], in body offsets. `masked` is the field with double-quoted text blanked
    to NUL; `quoted` says the field holds an excerpt (it is the excerpt field, whose lead-in
    such as `per call.txt:` is prose, not a ref)."""
    out, lo, in_q, in_bt, quoted = [], start + 1, False, False, False
    masked = []
    for i in range(start + 1, end - 1):
        ch = body[i]
        if ch in "\"“”" and not in_bt:
            in_q = not in_q
            quoted = True
            masked.append("\0")
            continue
        if ch == "`" and not in_q:
            in_bt = not in_bt
        if ch == "," and not in_q and not in_bt:
            out.append((lo, i, "".join(masked), quoted))
            lo, masked, quoted = i + 1, [], False
            continue
        masked.append("\0" if in_q else ch)
    out.append((lo, end - 1, "".join(masked), quoted))
    return out


def migrate_ref(path, old_ref, new_ref, apply_it):
    """Rewrite one source reference across a persona, once the source exists locally.

    The way out of the unverifiable debt: an old dossier cites mail identifiers and CRM
    records, and when that thread is finally saved as a file there was no way to point the
    tags at it short of editing by hand. Only a Fact tag's ref fields are touched, and only
    where OLD is the whole field or whole path components of it (A10): `call.txt` never
    rewrites `2026-08-01-call.txt`, an excerpt, or prose.
    """
    import difflib
    if not path.is_file():
        print(f"persona not found: {path}", file=sys.stderr)
        return 1
    body = read_text_lenient(path)
    pat = re.compile(r"(?<![^\s/\\`'\"<>(])" + re.escape(old_ref)
                     + r"(?=$|[\s/\\`'\"<>,;:)]|\.(?:\s|$))")
    hits = []
    for start, end in sorted({(t["start"], t["end"]) for t in parse_tags(body, path.parent)}):
        for lo, _hi, masked, quoted in _ref_fields(body, start, end):
            if quoted:
                continue
            hits.extend(lo + m.start() for m in pat.finditer(masked))
    n = len(hits)
    if not n:
        print(f"{old_ref!r} does not appear as a Fact tag reference in {path.name}", file=sys.stderr)
        return 1
    new_body = body
    for pos in sorted(hits, reverse=True):
        new_body = new_body[:pos] + new_ref + new_body[pos + len(old_ref):]
    if apply_it:
        atomic_write(path, new_body)
        print(f"{n} reference(s) rewritten in {path}")
    else:
        sys.stdout.writelines(difflib.unified_diff(
            body.splitlines(keepends=True), new_body.splitlines(keepends=True),
            fromfile=str(path), tofile=str(path) + " (proposed)"))
        print(f"\n{n} reference(s) would be rewritten. Nothing written: re-run with --apply.\n"
              "Then re-run the checker: a reference that now resolves turns UNVERIFIABLE into\n"
              "VERIFIED or into NOT FOUND, and NOT FOUND is the answer that matters.")
    return 0


def _misplaced_fix(raw, excerpts):
    """-> the tag's inner text with `excerpts` moved into it. The comma form (Fact, path, ...)
    already carries its separator: consume it too, otherwise the rewrite proposes a double
    comma."""
    quoted = '" and "'.join(excerpts)
    return re.sub(r'^\s*Fact\s*(?:[—–-]|,)?\s*', f'Fact — "{quoted}", ', raw)


def propose_fixes(body, tags, results):
    """Print the rewrite for every MISPLACED tag, and for every joined tag (FR-2.2) a rewrite
    that splits its shared parentheses into one pair per Fact. A joined group is handled once,
    as a single proposal: a segment inside it that is also MISPLACED gets its excerpt moved
    into that segment before the group is split, so one group never prints two proposals that
    would conflict if applied together. Never writes: moving a quote, or splitting a group, is
    the moment one is most tempted to make evidence fit, so a human reads the diff."""
    bad = {r["tag"] for r in results if r["status"] == "MISPLACED"}
    shown = 0
    any_split = False
    seen_groups = set()
    for t in tags:
        if t.get("joined"):
            group_key = (t["start"], t["end"])
            if group_key in seen_groups:
                continue          # this group's one proposal already covers every segment
            seen_groups.add(group_key)
            group_tags = [g for g in tags if (g["start"], g["end"]) == group_key]
            lo, hi = item_start(body, t["start"]), item_end(body, t["end"])
            item = body[lo:hi].strip()
            new_item = item
            new_segments = []
            for g in group_tags:
                if g["n"] in bad and g["excerpts"]:
                    new_segments.append(_misplaced_fix(g["raw"], g["excerpts"]))
                    # drop the quote from the prose, put it in its own segment
                    for ex in g["excerpts"]:
                        new_item = re.sub(r'[\s:,]*["“]' + re.escape(ex) + r'["”]',
                                          "", new_item, count=1)
                else:
                    new_segments.append(g["raw"])
            inner = body[t["start"] + 1: t["end"] - 1]
            split_inner = ") (".join(new_segments)
            new_item = new_item.replace("(" + inner + ")", "(" + split_inner + ")")
            print(f"\n--- tag #{t['n'].split('.')[0]} as written\n{item}\n+++ proposed\n{new_item.strip()}")
            shown += 1
            any_split = True
            continue
        if t["n"] not in bad or not t["excerpts"]:
            continue
        lo, hi = item_start(body, t["start"]), item_end(body, t["end"])
        item = body[lo:hi].strip()
        new_inner = _misplaced_fix(t["raw"], t["excerpts"])
        # drop the quote from the prose, put it in the tag
        new_item = item
        for ex in t["excerpts"]:
            new_item = re.sub(r'[\s:,]*["\u201c]' + re.escape(ex) + r'["\u201d]', "", new_item, count=1)
        new_item = re.sub(r"\(" + re.escape(t["raw"]) + r"\)", "(" + new_inner + ")", new_item)
        print(f"\n--- tag #{t['n']} as written\n{item}\n+++ proposed\n{new_item.strip()}")
        shown += 1
    if not shown:
        print("Nothing to fix: no misplaced excerpts.")
    else:
        print(f"\n{shown} rewrite(s) proposed, nothing written. Re-read the source before moving a\n"
              "quote: an excerpt shifted to the nearest claim is a fabrication with a passing test.")
        if any_split:
            print("A split changes no excerpt; check that each segment kept its own source.")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("persona", nargs="?", help="persona markdown file to audit")
    ap.add_argument("--sources-root", default=None,
                    help="base dir for relative source refs (default: the persona's context "
                         "sources_root, or the persona's own folder)")
    ap.add_argument("--excerpts", help="ingestion mode: JSON array of excerpt strings")
    ap.add_argument("--source", help="ingestion mode: the source file being ingested")
    ap.add_argument("--lint", action="store_true", help="gate mode: exit 1 on NOT FOUND or UNPARSEABLE")
    ap.add_argument("--fix-tags", action="store_true",
                    help="print the rewrite for misplaced excerpts (never writes the file)")
    ap.add_argument("--migrate-ref", nargs=2, metavar=("OLD", "NEW"),
                    help="rewrite a source reference across the persona (prints a diff; --apply writes)")
    ap.add_argument("--apply", action="store_true", help="with --migrate-ref: write the file")
    ap.add_argument("--against", metavar="OLD",
                    help="previous version of the persona: report content that disappeared")
    ap.add_argument("--allow-shrink", action="store_true",
                    help="with --against and --lint: accept a declared loss instead of failing")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args(argv)
    try:
        locale_regexes()  # validates BEFOREHAND_LOCALE lazily and AFTER parse_args, so --help
        # and an argparse usage error still work under an unknown locale
    except LocaleError as e:
        print(str(e), file=sys.stderr)
        return 1
    if args.sources_root is not None:
        root = Path(args.sources_root)
    elif args.persona:
        root = persona_sources_root(args.persona)
    else:
        root = None    # ingestion mode: --source is a command-line path, resolved below

    if args.migrate_ref:
        if not args.persona:
            ap.error("--migrate-ref needs a persona file")
        return migrate_ref(Path(args.persona), args.migrate_ref[0], args.migrate_ref[1], args.apply)

    results, tags, summary = [], [], None
    if args.excerpts and args.source:
        for i, ex in enumerate(json.loads(Path(args.excerpts).read_text(encoding="utf-8")), 1):
            # a file named on the command line is the user's path as typed, not a tag ref
            status, reason = check(ex, str(Path(args.source).expanduser().resolve()), root)
            results.append({"tag": str(i), "excerpt": ex, "ref": args.source,
                            "status": status, "reason": reason})
        tags = [{"ref_kind": "path"} for _ in results]
        summary = summarize(results, tags)
    elif args.persona:
        lp = lint_persona(args.persona, root, persona_store(args.persona))
        results, tags, summary = lp["results"], lp["tags"], lp["summary"]
        if args.fix_tags:
            # the same decode the tag offsets came from (A11)
            body = read_text_lenient(args.persona)
            propose_fixes(body, tags, results)
            return 0
    else:
        ap.error("provide a persona file, or --excerpts with --source")

    if args.json:
        print(json.dumps({"results": results, "summary": summary}, ensure_ascii=False, indent=1))
    else:
        print_report(results, summary, args.lint)
    losses = []
    if args.against and args.persona:
        old = read_text_lenient(args.against)
        new = read_text_lenient(args.persona)
        losses = content_loss(old, new)
        if losses and not args.json:
            print("\nCONTENT LOST since " + args.against + ":\n  " + "\n  ".join(losses))
            print("A persona that loses half its objections lints exactly like an intact one.\n"
                  "Declare the loss with --allow-shrink if it is intended.")
        elif not args.json:
            print(f"\nNo content lost since {args.against}.")

    if args.lint and (summary["NOT FOUND"] or summary["UNPARSEABLE"]):
        return 1
    if args.lint and losses and not args.allow_shrink:
        return 1
    return 0


if __name__ == "__main__":
    print("deprecated: use beforehand.py lint", file=sys.stderr)
    sys.exit(main())
