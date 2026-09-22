#!/usr/bin/env python3
"""Tests for personas_lib.py — the one parser every script reads files with.

Five copies of "find the sections of a persona" drifted apart before this module existed
(two of five stripped the `<!-- ... -->` heading note, three did not). These tests pin the
behaviour the copies have to share, and the frontmatter subset of FR-4.8: what the parser
does not accept it must report, with the line, instead of dropping it silently.
"""
import os
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True  # G5: a suite run on its own leaves no __pycache__

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import personas_lib as lib  # noqa: E402

FIXSTORE = HERE / "test_fixtures/store"
checks = []


def check(name, ok, got=None):
    checks.append((name, bool(ok), got))


def raises(fn):
    """-> (exception or None). Only FrontmatterError is caught: anything else is a failure."""
    try:
        fn()
    except lib.FrontmatterError as e:
        return e
    return None


# --------------------------------------------------------------------- frontmatter
FM = """---
slug: cto-mara
role: Chief Technology Officer
decision_weight: 4 # (Inference — signs off architecture, not budget)
aliases: [Mara, "Lind, M.", the CTO]
organization: "Northwind Logistics"
empty:
---

## Mandate and incentives
- body
"""
fm = lib.read_frontmatter(FM)
check("scalar parsed", fm.get("slug") == "cto-mara", fm)
check("trailing # comment stripped from a scalar", fm.get("decision_weight") == "4", fm)
check("surrounding quotes stripped", fm.get("organization") == "Northwind Logistics", fm)
check("inline list parsed, quoted comma kept whole",
      fm.get("aliases") == ["Mara", "Lind, M.", "the CTO"], fm)
check("a key with no value is the empty string", fm.get("empty") == "", fm)
check("no frontmatter -> empty dict", lib.read_frontmatter("# title\n- x\n") == {},
      lib.read_frontmatter("# title\n- x\n"))

span = lib.frontmatter_span(FM)
check("frontmatter_span starts at 0", span is not None and span[0] == 0, span)
check("frontmatter_span ends after the closing delimiter line",
      span is not None and FM[span[0]:span[1]].endswith("---\n")
      and FM[span[1]:].startswith("\n## Mandate"), span)
check("frontmatter_span is None without a block", lib.frontmatter_span("# title\n") is None,
      lib.frontmatter_span("# title\n"))
# strip_frontmatter is the SOURCE reader (FR-1.3): it strips only the header `save` writes,
# never a persona's frontmatter or a `---` rule that happens to open a source.
check("strip_frontmatter leaves a persona's frontmatter alone (it is not a save header)",
      lib.strip_frontmatter(FM) == FM, lib.strip_frontmatter(FM)[:20])
check("strip_frontmatter leaves a body without one alone",
      lib.strip_frontmatter("## x\n") == "## x\n")

# B1: a file that is ONLY frontmatter keeps its fields. A minimal context.md
# (`schema` + `sources_root`, no body) used to read as {} because of a "never strip a source to
# nothing" guard that belonged to sources, not to frontmatter; sources now have their own
# recogniser (source_header_span), so the guard is gone.
NO_TRAILING_NL = "---\nslug: a\n---"
check("B1: frontmatter_span covers a block with no trailing newline and no body",
      lib.frontmatter_span(NO_TRAILING_NL) == (0, len(NO_TRAILING_NL)),
      lib.frontmatter_span(NO_TRAILING_NL))
check("strip_frontmatter leaves a non-save block whole",
      lib.strip_frontmatter(NO_TRAILING_NL) == NO_TRAILING_NL, lib.strip_frontmatter(NO_TRAILING_NL))
HEADER_ONLY = "---\nslug: a\n---\n"
check("B1: frontmatter_span covers a header-only file that ends in a newline",
      lib.frontmatter_span(HEADER_ONLY) == (0, len(HEADER_ONLY)), lib.frontmatter_span(HEADER_ONLY))
MIN_CTX = "---\nschema: 0.2\nsources_root: ~/src\n---\n"
check("B1: a frontmatter-only context.md keeps its fields",
      lib.read_frontmatter(MIN_CTX) == {"schema": "0.2", "sources_root": "~/src"},
      lib.read_frontmatter(MIN_CTX))
check("B1: ... also without the final newline",
      lib.read_frontmatter(MIN_CTX.rstrip("\n")) == {"schema": "0.2", "sources_root": "~/src"},
      lib.read_frontmatter(MIN_CTX.rstrip("\n")))

# The guard on the opening delimiter is wider than "starts with ---", and each branch of it
# decides whether a real body gets read as metadata (or a horizontal rule as a header), so
# each branch is pinned here rather than trusted.
check("a four-dash first line is not a frontmatter delimiter",
      lib.frontmatter_span("----\nslug: a\n---\nbody\n") is None,
      lib.frontmatter_span("----\nslug: a\n---\nbody\n"))
check("a first line with text after the delimiter is not frontmatter either",
      lib.frontmatter_span("--- title\nslug: a\n---\nbody\n") is None,
      lib.frontmatter_span("--- title\nslug: a\n---\nbody\n"))
check("a block that is never closed is not frontmatter",
      lib.frontmatter_span("---\nslug: a\nno close\n") is None,
      lib.frontmatter_span("---\nslug: a\nno close\n"))
check("a file that is only the opening delimiter has no span",
      lib.frontmatter_span("---") is None and lib.frontmatter_span("---\n") is None,
      (lib.frontmatter_span("---"), lib.frontmatter_span("---\n")))
check("trailing spaces on the closing delimiter still close the block",
      lib.frontmatter_span("---\nslug: a\n--- \nbody\n") is not None,
      lib.frontmatter_span("---\nslug: a\n--- \nbody\n"))

# CRLF: a source saved on another platform must not have its header read as body (every
# excerpt in it would then be looked for in text that includes the provenance lines).
CRLF = "---\r\nslug: a\r\n---\r\nbody\r\n"
check("a CRLF block ends exactly where the body begins",
      lib.frontmatter_span(CRLF) == (0, len(CRLF) - len("body\r\n")), lib.frontmatter_span(CRLF))
check("a CRLF block's keys parse", lib.read_frontmatter(CRLF) == {"slug": "a"},
      lib.read_frontmatter(CRLF))
CRLF_SAVE = "---\r\nsource_ref: \"a\"\r\nsha1: \"0\"\r\n---\r\nbody\r\n"
check("strip_frontmatter on a CRLF save header leaves the body alone",
      lib.strip_frontmatter(CRLF_SAVE) == "body\r\n", lib.strip_frontmatter(CRLF_SAVE))

BLOCK_LIST = "---\nslug: a\naliases:\n- Mara\n- M. Lind\n---\n\nbody\n"
e = raises(lambda: lib.read_frontmatter(BLOCK_LIST))
check("a block list is out of the subset and raises", e is not None, e)
check("the block list error carries the line number of the first '- ' line",
      e is not None and e.line_no == 4, e and (e.line_no, e.reason))
check("the block list error says what it refused",
      e is not None and "block list" in str(e).lower(), str(e))

NESTED = "---\nslug: a\nowner:\n  name: Mara\n---\n\nbody\n"
e2 = raises(lambda: lib.read_frontmatter(NESTED))
check("a nested map is out of the subset and raises", e2 is not None, e2)
check("the nested map error carries the line number of the indented line",
      e2 is not None and e2.line_no == 4, e2 and (e2.line_no, e2.reason))
check("the nested map error says what it refused",
      e2 is not None and "nested" in str(e2).lower(), str(e2))

e3 = raises(lambda: lib.read_frontmatter("---\nslug: a\n  continued\nrole: x\n---\n\nbody\n"))
check("an indented continuation line raises too, with its line number",
      e3 is not None and e3.line_no == 3, e3 and (e3.line_no, e3.reason))
check("FrontmatterError is a ValueError", issubclass(lib.FrontmatterError, ValueError))

# the fixtures and the shipped template must stay inside the subset
ok_fixtures, bad_fixtures = True, []
for p in sorted(FIXSTORE.rglob("*.md")) + sorted((HERE / "test_fixtures").glob("*.md")):
    try:
        lib.read_frontmatter(lib.read_text_lenient(p))
    except lib.FrontmatterError as exc:
        ok_fixtures = False
        bad_fixtures.append(f"{p.name}:{exc.line_no} {exc.reason}")
check("every shipped fixture parses inside the subset", ok_fixtures, bad_fixtures)

TEMPLATE = HERE.parent / "assets/persona-template.md"
tmpl_bad = []
if TEMPLATE.is_file():
    body = lib.read_text_lenient(TEMPLATE)
    for block in body.split("```markdown")[1:]:
        try:
            lib.read_frontmatter(block.lstrip("\n"))
        except lib.FrontmatterError as exc:
            tmpl_bad.append(f"{exc.line_no}: {exc.reason}")
check("the template's example frontmatter parses inside the subset", not tmpl_bad, tmpl_bad)

# --------------------------------------------------------------------- sections
PERSONA = """---
slug: s
---

# Persona — S

## Mandate and incentives <!-- last evidence: 2026-06-01 | decays fast -->
- owns uptime

### Internal tensions
- a sub-point

## Red lines <!-- decays slowly -->
- no rollback, no signature
"""
secs = lib.sections(PERSONA)
titles = [s.title for s in secs]
check("every heading is returned, in order",
      titles == ["Persona — S", "Mandate and incentives", "Internal tensions", "Red lines"], titles)
check("levels are the number of '#'", [s.level for s in secs] == [1, 2, 3, 2],
      [s.level for s in secs])
check("the heading note is stripped from the title", secs[1].title == "Mandate and incentives",
      secs[1].title)
check("the heading note is kept in .note",
      secs[1].note == "<!-- last evidence: 2026-06-01 | decays fast -->", secs[1].note)
check("a heading without a note has an empty note", secs[0].note == "", secs[0].note)
check("header_start points at the heading",
      PERSONA[secs[1].header_start:].startswith("## Mandate"), PERSONA[secs[1].header_start:][:20])
check("body_start/end delimit the body",
      PERSONA[secs[1].body_start:secs[1].end].strip() == "- owns uptime",
      PERSONA[secs[1].body_start:secs[1].end])
check("a subsection ends where the next same-level heading starts",
      PERSONA[secs[2].body_start:secs[2].end].strip() == "- a sub-point",
      PERSONA[secs[2].body_start:secs[2].end])
check("the last section runs to the end of the file",
      secs[-1].end == len(PERSONA), (secs[-1].end, len(PERSONA)))
check("no headings -> no sections", lib.sections("plain text\n") == [], lib.sections("plain text\n"))

# --------------------------------------------------------------------- section_body
DOC = """## Predictions to verify
- P1 something

### Detail
- still inside Predictions

## Notes
Body of notes.

```
## Fenced heading
not a section
```

## User decisions
- decided
"""
b = lib.section_body(DOC, "Predictions to verify")
check("section_body returns the body of a '##' section", b is not None and "- P1 something" in b, b)
check("a deeper heading does not end the section", b is not None and "still inside Predictions" in b, b)
check("the section ends at the next same-level heading", b is not None and "Body of notes" not in b, b)
check("section_body is case-insensitive",
      lib.section_body(DOC, "predictions TO verify") == b, lib.section_body(DOC, "predictions TO verify"))
check("an absent section is None", lib.section_body(DOC, "Red lines") is None,
      lib.section_body(DOC, "Red lines"))
notes = lib.section_body(DOC, "Notes")
check("a heading inside a fenced block is not a section boundary",
      notes is not None and "## Fenced heading" in notes and "- decided" not in notes, notes)
check("a heading inside a fenced block is not findable as a section",
      lib.section_body(DOC, "Fenced heading") is None, lib.section_body(DOC, "Fenced heading"))
check("level narrows which heading opens the section",
      lib.section_body(DOC, "Detail", level=3) is not None
      and lib.section_body(DOC, "Detail", level=2) is None,
      (lib.section_body(DOC, "Detail", level=3), lib.section_body(DOC, "Detail", level=2)))

# --------------------------------------------------------------------- read_text_lenient
tmpdir = Path(tempfile.mkdtemp())
latin = tmpdir / "latin.txt"
latin.write_bytes(b"caf\xe9 wants a rollback\n")
check("a non-utf-8 file is read through the latin-1 fallback",
      lib.read_text_lenient(latin) == "café wants a rollback\n", lib.read_text_lenient(latin))
utf8 = tmpdir / "utf8.txt"
utf8.write_text("caffè corretto\n", encoding="utf-8")
check("a utf-8 file is read as utf-8", lib.read_text_lenient(utf8) == "caffè corretto\n",
      lib.read_text_lenient(utf8))

# --------------------------------------------------------------------- parse_tags
tags = lib.parse_tags(lib.read_text_lenient(FIXSTORE / "northwind/personas/cto-mara.md"),
                      FIXSTORE / "northwind")
check("parse_tags lives in the library and finds the fixture's Fact tags", len(tags) >= 1, len(tags))
check("a parsed tag carries its excerpt and its ref",
      bool(tags) and tags[0]["excerpts"] == ["my bonus is the uptime number"]
      and tags[0]["ref"] == "source.txt", tags[:1])

# A joined tag shares one set of parentheses across two Fact claims. It does NOT share the
# one excerpt written in the prose around it: both segments used to run the same look-back
# and both came back holding the same quote, so the second claim read as sourced by evidence
# that belongs to the first. Only the first excerpt-less segment takes the prose; the second
# keeps none and is reported by the linter as a Fact tag without a quoted excerpt.
JOINED_BACK = ('- claim "only quote" (Fact — a.md, private-communication, human-authored, '
               '2026-01-01; Fact — b.md, private-communication, human-authored, 2026-02-02)\n')
jt = lib.parse_tags(JOINED_BACK, Path("."))
check("a joined group with one prose excerpt yields two segments", len(jt) == 2,
      [(t["n"], t["excerpts"]) for t in jt])
check("the first excerpt-less segment takes the prose excerpt",
      len(jt) == 2 and jt[0]["n"] == "1.1" and jt[0]["excerpts"] == ["only quote"], jt[:1])
check("the second segment keeps no excerpt instead of claiming the same one",
      len(jt) == 2 and jt[1]["n"] == "1.2" and jt[1]["excerpts"] == [], jt[1:])

# the same rule on the forward shape: the group closes the sentence and the quote follows it
JOINED_FWD = ('- claim (Fact — a.md, private-communication, human-authored, 2026-01-01; '
              'Fact — b.md, private-communication, human-authored, 2026-02-02) "after"\n')
jf = lib.parse_tags(JOINED_FWD, Path("."))
check("a quote after the group is claimed by the first segment only",
      len(jf) == 2 and jf[0]["excerpts"] == ["after"] and jf[1]["excerpts"] == [],
      [(t["n"], t["excerpts"]) for t in jf])
check("the segment that took the trailing quote records it as misplaced",
      len(jf) == 2 and jf[0]["placement"] == "misplaced", [t["placement"] for t in jf])

# --------------------------------------------------------------------- Store
store = lib.Store(FIXSTORE)
check("Store keeps its root", store.root == FIXSTORE, store.root)
check("contexts are the non-hidden directories, sorted",
      [c.name for c in store.contexts()] == ["golden", "ironbridge", "northwind"],  # golden added by Task 6
      [c.name for c in store.contexts()])
check("context(name) is the directory", store.context("northwind") == FIXSTORE / "northwind",
      store.context("northwind"))
check("personas(ctx) lists personas/*.md",
      [p.name for p in store.personas("northwind")] == ["cto-mara.md"],
      [p.name for p in store.personas("northwind")])
check("personas(ctx) accepts a path as well as a name",
      store.personas(FIXSTORE / "northwind") == store.personas("northwind"))
check("a context without a personas/ dir lists nothing",
      store.personas("nonexistent") == [], store.personas("nonexistent"))
snaps = [s.name for s in store.snapshots("northwind")]
check("snapshots(ctx) lists calibration/pending-*.md, sorted",
      snaps == sorted(snaps) and "pending-proposal-v2.md" in snaps and len(snaps) == 4, snaps)
check("the snapshot prefix is a parameter",
      store.snapshots("northwind", prefix="pending-memo") == [
          FIXSTORE / "northwind/calibration/pending-memo-nodate.md"],
      store.snapshots("northwind", prefix="pending-memo"))
check("audit(ctx) is the AUDIT.md path whether or not it exists",
      store.audit("northwind") == FIXSTORE / "northwind/AUDIT.md", store.audit("northwind"))
check("sources_root defaults to the context directory",
      store.sources_root("northwind") == FIXSTORE / "northwind", store.sources_root("northwind"))
check("sources_root honours context.md and resolves it against the context",
      store.sources_root("ironbridge") == (FIXSTORE / "ironbridge").resolve(),
      store.sources_root("ironbridge"))

# --------------------------------------------------------------------- resolve_store
saved = os.environ.get("BEFOREHAND_STORE")
try:
    os.environ["BEFOREHAND_STORE"] = str(tmpdir)
    check("--store wins over the environment",
          lib.resolve_store(str(FIXSTORE)) == FIXSTORE.resolve(), lib.resolve_store(str(FIXSTORE)))
    check("BEFOREHAND_STORE is used when no --store is given",
          lib.resolve_store(None) == tmpdir.resolve(), lib.resolve_store(None))
    check("an empty --store falls back to the environment",
          lib.resolve_store("") == tmpdir.resolve(), lib.resolve_store(""))
    os.environ["BEFOREHAND_STORE"] = "~"
    check("a tilde in the environment is expanded",
          lib.resolve_store(None) == Path.home().resolve(), lib.resolve_store(None).name)
    del os.environ["BEFOREHAND_STORE"]
    default = lib.resolve_store(None)
    check("without --store and without the environment the default is ~/.beforehand",
          default == (Path.home() / ".beforehand").resolve() and default.is_absolute(), default.name)
    check("resolve_store returns a Path", isinstance(default, Path), type(default).__name__)
finally:
    if saved is None:
        os.environ.pop("BEFOREHAND_STORE", None)
    else:
        os.environ["BEFOREHAND_STORE"] = saved

check("the schema version is exported", lib.SCHEMA_VERSION == "0.2", lib.SCHEMA_VERSION)
# rel() is what doctor, forget and migrate report paths with: an absolute path names this
# machine. It was a public helper that `from personas_lib import *` did not hand over.
check("rel is exported in __all__", "rel" in lib.__all__, lib.__all__)
check("every name in __all__ exists on the module",
      [n for n in lib.__all__ if not hasattr(lib, n)] == [],
      [n for n in lib.__all__ if not hasattr(lib, n)])

# ===================================================================== 0.3.1 (SPEC-0.3.1)
def safe(fn):
    """-> fn() or the exception it raised: a missing helper must FAIL a check, not crash."""
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001
        return exc


# --------------------------------------------------------------------- B2 BOM
BOM = "﻿---\nschema: 0.2\n---\nbody\n"
check("B2: decode_lenient drops a UTF-8 BOM",
      lib.decode_lenient(BOM.encode("utf-8")) == BOM[1:], repr(lib.decode_lenient(BOM.encode("utf-8"))[:5]))
bom_file = tmpdir / "bom.md"
bom_file.write_bytes(BOM.encode("utf-8"))
check("B2: a BOM does not hide the frontmatter",
      lib.read_frontmatter(lib.read_text_lenient(bom_file)) == {"schema": "0.2"},
      safe(lambda: lib.read_frontmatter(lib.read_text_lenient(bom_file))))
check("B2: latin-1 fallback still works after the utf-8-sig attempt",
      lib.decode_lenient(b"caf\xe9") == "café", lib.decode_lenient(b"caf\xe9"))

# --------------------------------------------------------------------- B3 '#' inside quotes
B3 = ('---\ntitle: "Q3 #1 plan"\nnote: \'a #b\' # trailing\nplain: x # comment\n'
      'lst: [a, "b #c"] # c\n---\nbody\n')
b3 = lib.read_frontmatter(B3)
check("B3: a '#' inside a double-quoted scalar is part of the value", b3.get("title") == "Q3 #1 plan", b3)
check("B3: a '#' inside a single-quoted scalar is kept, the comment after it stripped",
      b3.get("note") == "a #b", b3)
check("B3: a trailing comment outside quotes is still stripped", b3.get("plain") == "x", b3)
check("B3: an inline list keeps a quoted '#', drops the trailing comment",
      b3.get("lst") == ["a", "b #c"], b3)
check("B3: an apostrophe inside an unquoted value does not hide the comment",
      lib.read_frontmatter("---\nrole: CTO's deputy # note\n---\nx\n").get("role") == "CTO's deputy",
      lib.read_frontmatter("---\nrole: CTO's deputy # note\n---\nx\n"))

# --------------------------------------------------------------------- B4 one section reader
FENCED = "## A\ntext\n```\n## not a heading\n```\n~~~\n## nor this\n```\n~~~\n## B\nb body\n"
fsecs = [s.title for s in lib.sections(FENCED)]
check("B4: sections() skips headings inside ``` and ~~~ fences (toggled separately)",
      fsecs == ["A", "B"], fsecs)
a_sec = lib.sections(FENCED)[0] if lib.sections(FENCED) else None
check("B4: the fenced block belongs to the enclosing section's body",
      a_sec is not None and "## nor this" in a_sec.body(FENCED), a_sec)
NOTE_DOC = "## Style <!-- last evidence: 2026-01-01 | decays fast -->\n- terse\n\n## Next\n- x\n"
check("B4: section_body finds a heading carrying a <!-- --> note by its name",
      lib.section_body(NOTE_DOC, "Style") == "- terse\n", lib.section_body(NOTE_DOC, "Style"))
TILDE = "## N\n~~~\n## Inside\n~~~\nafter\n## M\n"
check("B4: section_body treats ~~~ as a fence too",
      lib.section_body(TILDE, "N") == "~~~\n## Inside\n~~~\nafter"
      and lib.section_body(TILDE, "Inside") is None,
      (lib.section_body(TILDE, "N"), lib.section_body(TILDE, "Inside")))
check("section_body keeps its boundary semantics: exact old output on DOC",
      lib.section_body(DOC, "Predictions to verify")
      == "- P1 something\n\n### Detail\n- still inside Predictions\n",
      lib.section_body(DOC, "Predictions to verify"))
check("section_body: a '#' level-1 heading is not a boundary (only ##/### count, as before)",
      lib.section_body("## A\nx\n# T\ny\n## B\n", "A") == "x\n# T\ny",
      lib.section_body("## A\nx\n# T\ny\n## B\n", "A"))

# --------------------------------------------------------------------- B6 deep copy
loc = lib.get_locale("en")
loc["same_source"].append("POISON")
loc["snapshot_fields"]["meeting"].append("POISON")
check("B6: mutating get_locale()'s result does not poison the next caller",
      "POISON" not in lib.get_locale("en")["same_source"]
      and "POISON" not in lib.get_locale("en")["snapshot_fields"]["meeting"],
      lib.get_locale("en")["same_source"])
check("B6: ... nor the regex bundle's snapshot fields",
      "POISON" not in lib.locale_regexes("en")["snapshot_fields"]["meeting"],
      lib.locale_regexes("en")["snapshot_fields"])
check("filler_tokens ships in en.json",
      lib.get_locale("en").get("filler_tokens") == ["um", "uh", "erm", "er", "hmm", "ah", "eh"],
      lib.get_locale("en").get("filler_tokens"))
check("locale_regexes exposes filler_tokens as a frozenset",
      lib.locale_regexes("en").get("filler_tokens")
      == frozenset(["um", "uh", "erm", "er", "hmm", "ah", "eh"]),
      lib.locale_regexes("en").get("filler_tokens"))

# --------------------------------------------------------------------- A5 keyword whole-field
src5 = tmpdir / "a5"
(src5 / "type-a").mkdir(parents=True)
for name in ("fact-sheet.txt", "post-review-call.txt", "type-a/notes.md"):
    (src5 / name).write_text("the budget is approved\n", encoding="utf-8")
for name in ("fact-sheet.txt", "post-review-call.txt", "type-a/notes.md"):
    t5 = lib.parse_tags('- x (Fact — "the vendor must go", %s, private-communication, '
                        'human-authored, 2026-01-01)\n' % name, src5)
    check("A5: a ref starting with a label keyword stays a ref: " + name,
          len(t5) == 1 and t5[0]["ref"] == name and t5[0]["ref_kind"] == "path",
          [(t["ref"], t["ref_kind"]) for t in t5])
t5b = lib.parse_tags('- x (Fact — "q", Fact, private-communication, type: x, human-authored, '
                     '2026-01-01)\n', src5)
check("A5: bare keywords and `type: x` are still dropped",
      len(t5b) == 1 and t5b[0]["ref_kind"] == "missing", [(t["ref"], t["ref_kind"]) for t in t5b])
check("A5: KEYWORD_RE matches only a whole keyword field",
      not lib.KEYWORD_RE.match("fact-sheet.txt") and lib.KEYWORD_RE.match("private-communication")
      and lib.KEYWORD_RE.match("Fact"), lib.KEYWORD_RE.pattern)

# --------------------------------------------------------------------- A6 paren_groups quotes
A6 = ('- a (Fact — "we did it :)", a.txt, private-communication, human-authored, 2026-01-01)\n'
      '- b (Fact — "made up", same source, private-communication, human-authored, 2026-01-02)\n')
g6 = [inner for _, _, inner in lib.paren_groups(A6)]
check("A6: a ')' inside a quoted excerpt does not close the group",
      len(g6) == 2 and g6[0].endswith("2026-01-01") and '"we did it :)"' in g6[0], g6)
t6 = lib.parse_tags(A6, src5)
check("A6: the smiley tag parses with its real ref, which the next tag inherits",
      len(t6) == 2 and t6[0]["excerpts"] == ["we did it :)"] and t6[0]["ref"] == "a.txt"
      and t6[1]["ref"] == "a.txt" and t6[1]["ref_kind"] == "inherited",
      [(t["excerpts"], t["ref"], t["ref_kind"]) for t in t6])
STRAY = ('A 12" pipe, said nobody.\n\n'
         '- c (Fact — "real words", a.txt, private-communication, human-authored, 2026-01-03)\n')
g6b = [inner for _, _, inner in lib.paren_groups(STRAY)]
check("A6: a stray '\"' in one paragraph does not hide the next paragraph's tag",
      len(g6b) == 1 and g6b[0].startswith("Fact"), g6b)

# --------------------------------------------------------------------- A7 source headers
RULE = "---\nMara: we ship in march, no slip.\n---\nJon: ok.\n"
check("A7: a source opening with a `---` rule has no save header",
      safe(lambda: lib.source_header_span(RULE)) is None, safe(lambda: lib.source_header_span(RULE)))
check("A7: strip_frontmatter keeps a `---` rule source whole",
      lib.strip_frontmatter(RULE) == RULE, lib.strip_frontmatter(RULE))
SAVE = ('---\nsource_ref: "call.txt"\ndate: "2026-01-01"\ntype: "call"\n'
        'sha1: "0123"\nschema: "0.1"\n---\nMara: hello.\n')
check("A7: a real save header is recognised",
      safe(lambda: lib.source_header_span(SAVE)) == (0, SAVE.index("Mara")),
      safe(lambda: lib.source_header_span(SAVE)))
check("A7: strip_frontmatter strips a real save header",
      lib.strip_frontmatter(SAVE) == "Mara: hello.\n", lib.strip_frontmatter(SAVE))
NO_SHA = '---\nsource_ref: "call.txt"\n---\nbody\n'
check("A7: a block without sha1 is not a save header",
      safe(lambda: lib.source_header_span(NO_SHA)) is None, safe(lambda: lib.source_header_span(NO_SHA)))
MIXED = '---\nsource_ref: "x"\nsha1: "0"\nsome prose line\n---\nbody\n'
check("A7: a block with a non `key: value` line is not a save header",
      safe(lambda: lib.source_header_span(MIXED)) is None, safe(lambda: lib.source_header_span(MIXED)))
check("A7: frontmatter_span still reads a persona block (it is not the source reader)",
      lib.frontmatter_span(FM) is not None and lib.read_frontmatter(FM).get("slug") == "cto-mara")

# --------------------------------------------------------------------- A12 path first
t12 = lib.parse_tags(
    '- a (Fact — "one", a.txt, private-communication, human-authored, 2026-01-01)\n'
    '- b (Fact — "two", same source, fact-sheet.txt, private-communication, human-authored, '
    '2026-01-02)\n', src5)
check("A12: an explicit path beats the same-source shorthand in the same tag",
      len(t12) == 2 and t12[1]["ref"] == "fact-sheet.txt" and t12[1]["ref_kind"] == "path",
      [(t["ref"], t["ref_kind"]) for t in t12])

# --------------------------------------------------------------------- A3 resolve_source
root3 = tmpdir / "root3"
root3.mkdir()
(root3 / "inroot.txt").write_text("root copy\n", encoding="utf-8")
cwd3 = tmpdir / "cwd3"
cwd3.mkdir()
(cwd3 / "notes.txt").write_text("cwd copy\n", encoding="utf-8")
(cwd3 / "inroot.txt").write_text("cwd copy\n", encoding="utf-8")
saved_cwd = os.getcwd()
try:
    os.chdir(str(cwd3))
    r_missing = safe(lambda: lib.resolve_source("notes.txt", root3))
    r_found = safe(lambda: lib.resolve_source("inroot.txt", root3))
    c_missing = safe(lambda: lib.resolve_candidate("notes.txt", root3))
finally:
    os.chdir(saved_cwd)
check("A3: a relative ref is never resolved against the working directory",
      r_missing == (None, "source file not found under sources_root (%s) — set sources_root: in "
                          "context.md or use an absolute path" % root3), r_missing)
check("A3: a relative ref resolves under sources_root, not to the CWD's same-named file",
      isinstance(r_found, tuple) and r_found[1] == "" and r_found[0] == root3 / "inroot.txt",
      r_found)
check("A3: resolve_candidate goes through resolve_source (CWD ignored)", c_missing is None, c_missing)
r_store = safe(lambda: lib.resolve_source("notes.txt", root3, tmpdir))
check("not-found reason: the root is store-relative when the caller passes the store",
      r_store == (None, "source file not found under sources_root (root3) — set sources_root: in "
                        "context.md or use an absolute path"), r_store)
r_out = safe(lambda: lib.resolve_source("notes.txt", root3, cwd3))
check("not-found reason: a root outside the store passed is named as given",
      isinstance(r_out, tuple) and ("(%s)" % root3) in r_out[1], r_out)
check("resolve_source: a URL is never fetched",
      safe(lambda: lib.resolve_source("https://example.com/a.txt", root3))
      == (None, "remote URL (never fetched)"), safe(lambda: lib.resolve_source("https://x", root3)))
check("resolve_source: a ref that is not path-like keeps the pinned reason",
      safe(lambda: lib.resolve_source("the call", root3))
      == (None, "source reference is not a path ('the call'); use a resolvable path"),
      safe(lambda: lib.resolve_source("the call", root3)))
check("resolve_source: an absolute path is used as given",
      safe(lambda: lib.resolve_source(str(cwd3 / "notes.txt"), root3)) == (cwd3 / "notes.txt", ""),
      safe(lambda: lib.resolve_source(str(cwd3 / "notes.txt"), root3)))
check("resolve_source: a missing absolute path is 'source file not found'",
      safe(lambda: lib.resolve_source(str(cwd3 / "nope.txt"), root3)) == (None, "source file not found"),
      safe(lambda: lib.resolve_source(str(cwd3 / "nope.txt"), root3)))
check("resolve_source: a '~' path is expanded, not joined to sources_root",
      safe(lambda: lib.resolve_source("~/definitely-not-here-0.3.1.txt", root3))
      == (None, "source file not found"),
      safe(lambda: lib.resolve_source("~/definitely-not-here-0.3.1.txt", root3)))

# --------------------------------------------------------------------- A3c no root at all: not even
# the CWD is consulted (a caller that forgot sources_root must never pick up a same-named file
# sitting in the directory the command happened to run from)
cwd_src = tmpdir / "cwd-src"
cwd_src.mkdir()
(cwd_src / "source.txt").write_text("would-be picked up from the CWD\n", encoding="utf-8")
cwd_bare = tmpdir / "cwd-bare"   # baseline: same shape, but no source.txt sitting in it
cwd_bare.mkdir()
BODY_NO_ROOT = ('- a (Fact — "one", source.txt, private-communication, human-authored, '
                '2026-01-01)\n')


def probe_no_root(cwd):
    """-> (resolve_source("source.txt", None), the same call on parse_tags' own parsed ref),
    both made while `cwd` is still the process CWD. Made INSIDE the chdir, not after restoring
    it: a resolve_source call made after the CWD is put back would stay blind to a regression
    that starts consulting the CWD, because by then the CWD no longer holds source.txt either
    way — the mutation and the correct behaviour would look identical from there."""
    saved = os.getcwd()
    try:
        os.chdir(str(cwd))
        r = safe(lambda: lib.resolve_source("source.txt", None))
        tags = safe(lambda: lib.parse_tags(BODY_NO_ROOT))
        tag_r = (safe(lambda: lib.resolve_source(tags[0]["ref"], None))
                 if isinstance(tags, list) and len(tags) == 1 else tags)
        return r, tag_r
    finally:
        os.chdir(saved)


r_in_src, tagr_in_src = probe_no_root(cwd_src)     # CWD holds a same-named source.txt
r_in_bare, tagr_in_bare = probe_no_root(cwd_bare)  # CWD does not — the baseline
check("resolve_source: sources_root=None never resolves a relative ref against the CWD",
      r_in_src == (None, "source file not found") and r_in_src == r_in_bare,
      (r_in_src, r_in_bare))
check("parse_tags: sources_root defaulting to None never resolves its ref against the CWD either",
      tagr_in_src == (None, "source file not found") and tagr_in_src == tagr_in_bare,
      (tagr_in_src, tagr_in_bare))

# --------------------------------------------------------------------- F2 phone-shaped numbers
unident = lib.locale_regexes("en")["inline_unident_re"]
check("F2: a thousands-grouped amount before a colon is not a marker",
      unident.search("the total is 1.200.000: approved") is None
      and unident.search("1.200.000: approved") is None
      and unident.search("1,200,000: approved") is None,
      [m.group(1) for m in unident.finditer("1.200.000: approved")])
check("F2: a short number before a colon is not a marker",
      unident.search("item 12345: done") is None and unident.search("12345: done") is None,
      [m.group(1) for m in unident.finditer("12345: done")])
check("F2: a phone number at line start is still a marker",
      [m.group(1).strip() for m in unident.finditer("x\n+44 7700 900123: hello")] == ["+44 7700 900123"],
      [m.group(1) for m in unident.finditer("x\n+44 7700 900123: hello")])
check("F2: a bracketed phone number is still a marker",
      unident.search("x\n(0044 20 7946 0000): hi") is not None
      and unident.search("then Marco (+44 7700 900123): hi") is not None,
      [m.group(1) for m in unident.finditer("x\n(0044 20 7946 0000): hi")])
check("F2: a masked phone number is still a marker",
      unident.search("\n+44 7700 *** **31: hi") is not None, unident.pattern[:80])
check("F2: a generic label mid-line is still a marker",
      unident.search("sorry, Speaker 2: can you repeat") is not None, unident.pattern[:80])

# --------------------------------------------------------------------- FR-2.5 helpers
check("parse_iso_date parses YYYY-MM-DD",
      safe(lambda: lib.parse_iso_date("2026-09-22")) == __import__("datetime").date(2026, 9, 22),
      safe(lambda: lib.parse_iso_date("2026-09-22")))
for bad in ("20260922", "2026-9-22", "2026-02-30", " 2026-09-22", "2026-09-22\n", "2026-09-22T00:00",
            "２０２６-09-22", ""):
    check("parse_iso_date refuses %r with ValueError" % bad,
          isinstance(safe(lambda: lib.parse_iso_date(bad)), ValueError),
          safe(lambda: lib.parse_iso_date(bad)))

aw = tmpdir / "aw" / "file.md"
aw.parent.mkdir()
safe(lambda: lib.atomic_write(aw, "caffè\nline two\n"))
check("atomic_write writes utf-8 with the newlines as given",
      aw.is_file() and aw.read_bytes() == "caffè\nline two\n".encode("utf-8"),
      aw.read_bytes() if aw.is_file() else None)
safe(lambda: lib.atomic_write(aw, "replaced\r\n"))
check("atomic_write replaces an existing file, CRLF kept as given",
      aw.is_file() and aw.read_bytes() == b"replaced\r\n", aw.read_bytes() if aw.is_file() else None)
check("atomic_write leaves no temp file behind",
      sorted(p.name for p in aw.parent.iterdir()) == ["file.md"], sorted(p.name for p in aw.parent.iterdir()))
if aw.is_file():
    os.chmod(str(aw), 0o640)
    safe(lambda: lib.atomic_write(aw, "again\n"))
check("atomic_write keeps the existing file's permissions",
      aw.is_file() and (os.stat(str(aw)).st_mode & 0o777) == 0o640,
      aw.is_file() and oct(os.stat(str(aw)).st_mode & 0o777))
check("atomic_write into a missing directory raises (the library never creates the store)",
      isinstance(safe(lambda: lib.atomic_write(tmpdir / "nodir" / "x.md", "x")), OSError),
      safe(lambda: lib.atomic_write(tmpdir / "nodir" / "x.md", "x")))

al = tmpdir / "log.jsonl"
safe(lambda: lib.append_line(al, "one"))
check("append_line creates the file with line + newline",
      al.is_file() and al.read_text(encoding="utf-8") == "one\n", al.read_text() if al.is_file() else None)
al.write_text("one\ntwo", encoding="utf-8")      # hand-edited: no final newline (E5)
safe(lambda: lib.append_line(al, "three"))
check("append_line adds the missing final newline before appending",
      al.read_text(encoding="utf-8") == "one\ntwo\nthree\n", al.read_text())
empty = tmpdir / "empty.log"
empty.write_text("", encoding="utf-8")
safe(lambda: lib.append_line(empty, "first"))
check("append_line on an empty file writes no leading newline",
      empty.read_text(encoding="utf-8") == "first\n", empty.read_text())

saved_loc = os.environ.get("BEFOREHAND_LOCALE")
try:
    os.environ["BEFOREHAND_LOCALE"] = "zz-nonexistent"
    cl_bad = safe(lambda: lib.check_locale())
    os.environ["BEFOREHAND_LOCALE"] = "en"
    cl_ok = safe(lambda: lib.check_locale())
finally:
    if saved_loc is None:
        os.environ.pop("BEFOREHAND_LOCALE", None)
    else:
        os.environ["BEFOREHAND_LOCALE"] = saved_loc
check("check_locale -> the LocaleError message for an unknown BEFOREHAND_LOCALE",
      isinstance(cl_bad, str) and cl_bad.startswith("unknown locale 'zz-nonexistent' (available: "),
      cl_bad)
check("check_locale -> None for a valid locale", cl_ok is None, cl_ok)

td = lib.parse_tags('- x (Fact — "q", a.txt, private-communication, human-authored, 2026-01-01, '
                    '2026-02-03)\n- y "p" (Fact — a.txt, 2026-03-04; Fact — "r", a.txt)\n', src5)
check("parse_tags: tag dicts carry their own date fields, in order",
      [t.get("dates") for t in td] == [["2026-01-01", "2026-02-03"], ["2026-03-04"], []],
      [t.get("dates") for t in td])

check("new names are exported",
      all(n in lib.__all__ for n in ("resolve_source", "source_header_span", "parse_iso_date",
                                     "atomic_write", "append_line", "check_locale")), lib.__all__)

# --------------------------------------------------------------------- G5
import shutil  # noqa: E402
import subprocess  # noqa: E402

g5_env = dict(os.environ)
g5_env.pop("PYTHONDONTWRITEBYTECODE", None)   # the runner exports it; the check must not lean on it
# The import below compiles personas_lib.py before executing it, so the .pyc for the module
# itself would land next to the source no matter what the module later sets. Run it against a
# temp copy, not HERE, so a direct `python3 test_lib.py` leaves no __pycache__ beside the
# real scripts.
with tempfile.TemporaryDirectory() as g5_tmp:
    shutil.copy2(HERE / "personas_lib.py", Path(g5_tmp) / "personas_lib.py")
    g5 = subprocess.run([sys.executable, "-c",
                         "import sys; sys.path.insert(0, sys.argv[1]); import personas_lib; "
                         "print(sys.dont_write_bytecode)", g5_tmp],
                        capture_output=True, text=True, env=g5_env)
check("G5: importing personas_lib turns bytecode writing off",
      g5.stdout.strip() == "True", (g5.stdout, g5.stderr[-200:]))

fails = [c for c in checks if not c[1]]
for n, ok, got in checks:
    print(("ok   " if ok else "FAIL ") + n + ("" if ok else f" -> {str(got)[:300]}"))
print(f"\n{len(checks)-len(fails)}/{len(checks)} passed")
sys.exit(1 if fails else 0)
