#!/usr/bin/env python3
"""How much material there is for a person — before building, and after.

Two directions, because the same question has two moments.

BEFORE (`--sources DIR`): who actually speaks across a folder of sources, and how much.
Full-text search returns the meetings where a name is on the invitation, which is not the
same as having spoken: a person can appear in eight calls and say a few hundred characters
in total. Measuring first is the difference between building two founded personas and
building two founded ones plus two empty ones that look identical.

AFTER (`PERSONA.md`): the definition of done of the authoring flow. The excerpt linter
answers "does every quote exist"; it cannot answer "is this persona founded". A file built
on one thin source passes the linter exactly like one built on five independent ones, and
in the index they are the same line. This computes the second question and says it in three
levels with the reason attached.

Usage:
  coverage.py --sources DIR [--people "Name, Other Name"] [--ext .txt,.md] [--json]
  coverage.py PERSONA.md [--audit AUDIT.md] [--json]

Exit codes: 0 ok · 1 usage. Coverage NEVER blocks: a thin persona is usable as long as
everyone reading it knows it is thin. That is the whole point of measuring it.
"""
import argparse
import json
import re
import sys

sys.dont_write_bytecode = True
from pathlib import Path  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import speakers as sp  # noqa: E402
from personas_lib import (  # noqa: E402
    FrontmatterError,
    LocaleError,
    locale_regexes,
    parse_iso_date,
    parse_tags,
    persona_sources_root,
    read_frontmatter,
    read_text_lenient,
    sections,
)

DATE_IN_NAME = re.compile(r"(\d{4}-\d{2}-\d{2})")
DATE_ANY = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
# The template sections that carry judgment. Background and Watchlist are not evidence of
# how someone decides, so they do not count towards populated sections.
JUDGMENT_SECTIONS = ["Mandate and incentives", "Judgment criteria", "Recurring objections",
                     "Red lines", "Language and dissent style", "Panel dynamics"]
# The declared-empty phrase ("empty_decl_re", built from locale data "empty_section") is
# fetched lazily from personas_lib.locale_regexes() inside assess(), where it is used —
# never as a module-level constant (BEFOREHAND_LOCALE may not be set yet at import time).


def span_days(dates):
    """Days between the earliest and the latest parseable `YYYY-MM-DD` in `dates`; a string
    that is not a real date is ignored rather than zeroing the whole span."""
    ds = []
    for d in set(dates):
        try:
            ds.append(parse_iso_date(d))
        except ValueError:
            continue
    if len(ds) < 2:
        return 0
    return (max(ds) - min(ds)).days


# --------------------------------------------------------------------- BEFORE: the sources
def scan_sources(root, people, exts):
    """(rows, file count, non-transcript names), or None when no file matches `exts`."""
    files = sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in exts)
    if not files:
        return None
    agg, skipped = {}, []
    for f in files:
        text = read_text_lenient(f)
        date = (DATE_IN_NAME.search(f.name) or DATE_ANY.search(text[:4000]))
        date = date.group(1) if date else None
        _, turns = sp.parse(text)
        if turns:
            for t in turns:
                r = agg.setdefault(t["label"], {"label": t["label"], "kind": t["kind"], "spoken": 0,
                                                "turns": 0, "sources": set(), "dates": set(),
                                                "dubious": 0, "mentions": 0})
                r["spoken"] += t["chars"]
                r["turns"] += 1
                r["dubious"] += 1 if t["dubious"] else 0
                r["sources"].add(f.name)
                if date:
                    r["dates"].add(date)
        else:
            # not a transcript: a name appearing here is a mention, never speech
            skipped.append(f.name)
            for name in people:
                n = len(re.findall(re.escape(name), text, re.I))
                if n:
                    r = agg.setdefault(name, {"label": name, "kind": "named", "spoken": 0, "turns": 0,
                                              "sources": set(), "dates": set(), "dubious": 0, "mentions": 0})
                    r["mentions"] += n
                    r["sources"].add(f.name)
                    if date:
                        r["dates"].add(date)
    rows = []
    for r in agg.values():
        if people and not any(p.lower() in r["label"].lower() for p in people):
            continue
        rows.append({**r, "sources": sorted(r["sources"]), "dates": sorted(r["dates"]),
                     "span_days": span_days(r["dates"])})
    rows.sort(key=lambda r: -r["spoken"])
    return rows, len(files), skipped


def verdict_sources(r):
    if r["spoken"] >= 20000 and len(r["sources"]) >= 3:
        return "solid", "volume and several independent sources"
    if r["spoken"] >= 5000 and len(r["sources"]) >= 2:
        return "adequate", "enough to start, worth another source"
    if r["spoken"] > 0:
        return "thin", f"only {r['spoken']} characters spoken across {len(r['sources'])} source(s)"
    return "absent", "named but never speaks in these sources"


# --------------------------------------------------------------------- AFTER: the persona
def audit_facts(persona_path, sources_root=None):
    text = read_text_lenient(persona_path)
    root = sources_root if sources_root is not None else persona_sources_root(persona_path)
    tags = parse_tags(text, Path(root))
    return text, tags


def assess(persona_path, audit_path=None, sources_root=None):
    """The AFTER report for one persona. `sources_root=None` derives it from the persona's
    location (`persona_sources_root`); callers that already know it pass it."""
    text, tags = audit_facts(persona_path, sources_root)
    secs = {s.title: s.body(text) for s in sections(text)}
    # FR-4.8: frontmatter outside the accepted subset is a failed check here, not just a
    # warning on stderr (that is reindex.py's job) — a persona whose header the tools cannot
    # fully read should not read as founded on the strength of everything else. One parse
    # serves every header field this function needs: re-regexing the block meant a quoted
    # `slug: "dana"` was the slug `"dana"`, quotes included, only in this file.
    try:
        fm = read_frontmatter(text)
        fm_ok, fm_evidence = True, "within the accepted subset"
    except FrontmatterError as e:
        fm, fm_ok, fm_evidence = {}, False, f"frontmatter: {e.line_no}: {e.reason}"
    cares = fm.get("cares_about", "")
    cares_present = bool(cares if isinstance(cares, list) else str(cares).strip())
    empty_decl_re = locale_regexes()["empty_decl_re"]

    refs = [t["ref"] for t in tags if t["ref"]]
    distinct = sorted(set(refs))
    # Only the Fact tags' own dates (D2): frontmatter `updated:`, heading notes and "no
    # evidence as of" lines say when the file was touched, not what period the evidence spans.
    dates = [day for t in tags for day in t["dates"]]
    span = span_days(dates)
    per_ref = {r: refs.count(r) for r in distinct}
    top_share = (max(per_ref.values()) / len(refs)) if refs else 0

    # Four states, not two. A section can carry real content with no Fact tag in it —
    # inferences, panel dynamics deduced from behaviour — and calling that "empty" sends the
    # author to fill a section that is already written. Only a section with no content AND no
    # declaration is silent.
    populated, inference_only, empty_declared, empty_silent = [], [], [], []
    for name in JUDGMENT_SECTIONS:
        body = next((v for k, v in secs.items() if k.lower() == name.lower()), None)
        if body is None:
            empty_silent.append(name)
            continue
        has_content = bool(re.search(r"^[ \t]*[-*]\s+\S", re.sub(r"<!--.*?-->", "", body, flags=re.S), re.M))
        if re.search(r"\(Fact\b", body, re.I):
            populated.append(name)
        elif empty_decl_re.search(body):
            empty_declared.append(name)
        elif has_content:
            inference_only.append(name)
        else:
            empty_silent.append(name)

    audit_note, audit_none = None, "no AUDIT passed"
    if audit_path and Path(audit_path).is_file():
        atext = read_text_lenient(audit_path)
        slug = fm.get("slug")
        slug = slug if isinstance(slug, str) else ""
        # a whole slug, not a substring (D3): `dana` must not claim a `cto-dana` row
        slug_re = re.compile(r"(?<![\w-])" + re.escape(slug) + r"(?![\w-])") if slug else None
        rows = [ln for ln in atext.splitlines() if slug_re and slug_re.search(ln)]
        audit_note = any(re.search(r"speaker attribution", ln, re.I) for ln in rows) if rows else None
        if not rows:
            audit_none = "no AUDIT row names %s" % (slug or "this persona")

    checks = [
        ("independent sources >= 2", len(distinct) >= 2, f"{len(distinct)} distinct source refs"),
        ("time span covered", span >= 30, f"{span} days between first and last date"),
        ("evidence volume", len(tags) >= 10, f"{len(tags)} Fact tags, {len(refs)} with a source"),
        ("judgment sections with evidence",
         len(populated) >= 4, f"{len(populated)}/{len(JUDGMENT_SECTIONS)}: {', '.join(populated) or 'none'}"),
        ("no single source dominates",
         top_share <= 0.6, f"heaviest source carries {round(100 * top_share)}% of the Facts"),
        ("empty sections are declared, not silent",
         not empty_silent, ("declared: " + ", ".join(empty_declared) if empty_declared else "none empty")
         + (f" | no Fact but written: {', '.join(inference_only)}" if inference_only else "")
         + (f" | SILENT: {', '.join(empty_silent)}" if empty_silent else "")),
        ("cares_about populated", cares_present,
         "present" if cares_present else "missing: roster selection reads this field"),
        ("attribution recorded in AUDIT for multi-voice sources",
         audit_note is not False,
         audit_none if audit_note is None
         else ("recorded" if audit_note else "AUDIT rows carry no attribution note")),
        ("frontmatter within subset", fm_ok, fm_evidence),
    ]
    total = len(checks)
    passed = sum(1 for _, ok, _ in checks if ok)
    # A floor, not just a count: a persona whose judgment sections mostly rest on no quote
    # at all is not solid however many of the other checks pass. Two sections out of six
    # with nothing quoted is two dimensions on which a panel would be improvising.
    quoted_enough = len(populated) >= len(JUDGMENT_SECTIONS) - 1
    if passed >= total - 1 and quoted_enough:
        level, why = "solid", f"{passed}/{total} checks"
    elif passed >= total - 3:
        thin_note = (f", but only {len(populated)}/{len(JUDGMENT_SECTIONS)} "
                     "judgment sections carry a quote")
        level, why = ("adequate", f"{passed}/{total} checks" + ("" if quoted_enough else thin_note))
    else:
        level, why = "thin", f"{passed}/{total} checks"
    short = (f"{level} ({len(distinct)} sources, {span}d, "
             f"{len(populated)}/{len(JUDGMENT_SECTIONS)} sections"
             + (f", {len(inference_only)} without a Fact" if inference_only else "")
             + (f", {', '.join(empty_declared)} empty" if empty_declared else "") + ")")
    return {"persona": str(persona_path), "level": level, "why": why, "summary": short,
            "checks": [{"check": c, "ok": ok, "evidence": ev} for c, ok, ev in checks],
            "sources": distinct, "span_days": span, "facts": len(tags),
            "populated_sections": populated, "inference_only_sections": inference_only,
            "empty_declared": empty_declared, "empty_silent": empty_silent}


def coverage_line(persona_path, audit_path=None, sources_root=None):
    """One-line summary for reindex.py. Never raises: bookkeeping must not depend on it."""
    try:
        return assess(Path(persona_path), audit_path, sources_root)["summary"]
    except Exception:
        return "-"


def _run(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("persona", nargs="?")
    ap.add_argument("--sources", help="directory of sources to measure before building")
    ap.add_argument("--people", help="comma-separated names to look for in non-transcript sources")
    ap.add_argument("--ext", default=".txt,.md,.vtt,.srt")
    ap.add_argument("--audit", help="AUDIT.md of the context, for the attribution check")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        locale_regexes()  # validates BEFOREHAND_LOCALE lazily and AFTER parse_args, so --help
        # and an argparse usage error still work under an unknown locale
    except LocaleError as e:
        print(str(e), file=sys.stderr)
        return 1
    people = [p.strip() for p in (a.people or "").split(",") if p.strip()]

    if a.sources:
        root = Path(a.sources).expanduser()
        if not root.is_dir():
            print(f"not a directory: {root}", file=sys.stderr)
            return 1
        exts = tuple(e.strip().lower() for e in a.ext.split(","))
        scanned = scan_sources(root, people, exts)
        if scanned is None:
            print(f"no sources with extension {', '.join(exts)} under {root}", file=sys.stderr)
            return 1
        rows, n_files, skipped = scanned
        if a.json:
            print(json.dumps({"files": n_files, "non_transcripts": skipped,
                              "people": [{**r, "verdict": verdict_sources(r)[0]} for r in rows]},
                             ensure_ascii=False, indent=1))
            return 0
        print(f"\nCoverage across {n_files} source file(s) in {root}\n")
        print(f"{'spoken':>9} {'turns':>6} {'src':>4} {'span':>6}  verdict    who")
        verdicts = [verdict_sources(r) for r in rows]
        for r, (v, _why) in zip(rows, verdicts):
            extra = f"   [{r['mentions']} mentions, not speech]" if r["mentions"] and not r["spoken"] else ""
            print(f"{r['spoken']:>8,}c {r['turns']:>6} {len(r['sources']):>4} {r['span_days']:>5}d  "
                  f"{v:<10} {r['label']}{extra}")
        thin = [(r, why) for r, (v, why) in zip(rows, verdicts) if v in ("thin", "absent")]
        if thin:
            print("\nBeing on the invitation is not speaking. These have too little to carry a persona:")
            for r, why in thin:
                print(f"  {r['label']}: {why}")
        if skipped:
            print(f"\n{len(skipped)} file(s) had no speaker markers and were counted as mentions only: "
                  + ", ".join(skipped[:4]) + (" ..." if len(skipped) > 4 else ""))
        return 0

    if not a.persona:
        ap.error("give a persona file, or --sources DIR")
    p = Path(a.persona).expanduser()
    if not p.is_file():
        print(f"persona not found: {p}", file=sys.stderr)
        return 1
    res = assess(p, a.audit, persona_sources_root(p))
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=1))
        return 0
    print(f"\nCoverage — {p.name}: {res['level'].upper()} ({res['why']})\n")
    for c in res["checks"]:
        print(f"[{'  ok  ' if c['ok'] else ' thin ' }] {c['check']}: {c['evidence']}")
    print(f"\nIndex line: {res['summary']}")
    if res["inference_only_sections"]:
        print("\nSections written but carrying no Fact: " + ", ".join(res["inference_only_sections"]) +
              "\nThey are not empty. They rest on inference, which is a legitimate label — but a\n"
              "section a panel will lean on and that no quote supports is worth knowing about.")
    if res["empty_silent"]:
        print("\nSections with neither evidence nor a declaration: " + ", ".join(res["empty_silent"]) +
              "\nA section left blank and a section with nothing to say look the same. Write\n"
              "\"no evidence as of <date>\" in the empty ones — and do NOT fill them by deducing\n"
              "what the person would probably think: that is the roleplay this skill forbids.")
    print("\nCoverage never blocks. A thin persona is usable as long as whoever reads its\n"
          "objections knows how thin it is.")
    return 0


def main(argv=None):
    return _run(argv)


if __name__ == "__main__":
    print("deprecated: use beforehand.py coverage", file=sys.stderr)
    sys.exit(main())
