#!/usr/bin/env python3
"""List and promote Watchlist entries without cutting the file by hand.

Why this exists. The Watchlist is the anteroom: an observation seen once waits there, and a
second independent occurrence promotes it into the body. That promotion is the most
consequential edit the model defines — it turns "observed once" into "stable trait about a
real person" — and it was the only one with no tool. Doing it by hand means finding the
entry's start and cutting to the next one; entries are prose bullets of variable length, so
a cut can overshoot into the next section and take content with it. The linter cannot see
that: it checks that the excerpts still present resolve, never that the ones from yesterday
are still there.

So: entries are addressed by a stable id, boundaries come from a list parser rather than a
string search, and the write is refused if the operation would lose content — the same
`content_loss` rule migrate uses (Fact tags, sections, their bullet counts, a >10% shrink),
plus a check of its own that the target section grew. The write replaces the file whole
(`atomic_write`); the persona is read leniently (utf-8, latin-1 fallback).

Usage:
  watchlist.py PERSONA --list [--json]
  watchlist.py PERSONA --assign-ids [--apply]
  watchlist.py PERSONA --promote ID --section "Recurring objections" [--note TEXT] [--apply]

Without --apply nothing is written: the proposed file is printed as a unified diff, because
a persona changes on the user's confirmation and never on a script's initiative.

The anteroom clause after an entry's last Fact tag is dropped from the promoted line and
kept in the promotion record instead (references/evidence-model.md#Watchlist); --note is
where body wording for the promoted line goes.

Exit codes: 0 ok · 1 usage · 2 the edit would lose content (refused)
"""
import sys

sys.dont_write_bytecode = True  # before any sibling import (G5)

import argparse  # noqa: E402
import datetime as dt  # noqa: E402
import difflib  # noqa: E402
import json  # noqa: E402
import re  # noqa: E402
from pathlib import Path  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from personas_lib import (  # noqa: E402
    FACT_LABEL_RE,
    QUOTE_RE,
    atomic_write,
    check_locale,
    locale_regexes,
    paren_groups,
    parse_iso_date,
    read_text_lenient,
    sections,
)
from verify_quotes import content_loss  # noqa: E402

# A hook, not a bare call (S14): tests pin the date without asserting on today, as in
# reindex, migrate, forget and pending.
_today = dt.date.today

# The "if it repeats" clause is locale data (FR-4.4: "watchlist_repeat_clause") — the words
# a note about a Watchlist entry's future promotion is written in, so it can be recognised
# and flagged for rewriting before a promotion, regardless of which language it was written
# in. Fetched lazily from personas_lib.locale_regexes() inside cmd_promote(), where it is
# used — never as a module-level constant (BEFOREHAND_LOCALE may not be set yet at import).

WATCHLIST_H = re.compile(r"^##\s+Watchlist\s*$", re.M | re.I)
ID_RE = re.compile(r"^-\s*\[(wl-\d+)\]\s*")
BOLD = re.compile(r"\*\*(.+?)\*\*", re.S)
DATE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
# a source reference inside a tag: enough to tell two independent sources apart
REF = re.compile(
    r"(?:^|[\s,(])((?:~|\.{0,2}/|[A-Za-z]:[\\/])[^\s,)]+|[^\s,()]+\.(?:md|txt|json|csv|html?|eml|vtt|srt))")
PROMOTED = re.compile(r"^-\s*\[(wl-\d+)\]\s*PROMOTED\b", re.I)


class Refused(Exception):
    """Raised by die() instead of exiting the process; main() converts it to a return code.

    die() is called from nested helpers (cmd_promote), not only from main() itself, so a
    bare return-code convention would not unwind the call stack; an exception does. This
    also means an in-process caller of main() (a test, or another module) gets an ordinary
    return code back instead of the whole interpreter exiting under it.
    """
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def die(code, msg):
    print(msg, file=sys.stderr)
    raise Refused(code)


def watchlist_span(text):
    m = WATCHLIST_H.search(text)
    if not m:
        return None
    for s in sections(text):
        if s.header_start == m.start():
            return s.body_start, s.end
    return None


def parse_entries(text):
    """Bullets of the Watchlist, with boundaries taken from the list structure.

    A bullet runs from a line starting with '- ' to the next such line, the next heading, or
    the end of the section. Nothing is located by searching for its text, which is how a cut
    ends up two lines past where it should.
    """
    span = watchlist_span(text)
    if not span:
        return []
    lo, hi = span
    body = text[lo:hi]
    starts = [m.start() for m in re.finditer(r"^-[ \t]+", body, re.M)]
    entries = []
    for i, st in enumerate(starts):
        en = starts[i + 1] if i + 1 < len(starts) else len(body)
        raw = body[st:en]
        stripped = raw.rstrip()
        eid = ID_RE.match(stripped)
        title_m = BOLD.search(stripped)
        dates = sorted(set(DATE.findall(stripped)))
        refs = sorted({r for r in REF.findall(stripped)})
        entries.append({
            "id": eid.group(1) if eid else None,
            "promoted": bool(PROMOTED.match(stripped)),
            "title": (title_m.group(1).strip() if title_m
                      else re.sub(r"\s+", " ", stripped[2:])[:70]),
            "dates": dates,
            "sources": refs,
            "abs_start": lo + st,
            "abs_end": lo + st + len(stripped),
            "text": stripped,
        })
    return entries


def days_since(ds):
    try:
        return (_today() - parse_iso_date(ds)).days
    except ValueError:
        return None


def integrity(old, new, target_title):
    """Refuse an edit that loses evidence. Checked on the operation, not on a snapshot.

    One content-loss rule for every automated edit (S6): `verify_quotes.content_loss`, the one
    migrate applies, plus the check only a promotion needs — its target section must grow."""
    problems = list(content_loss(old, new))
    for s in sections(new):
        if s.title.lower() == target_title.lower():
            before = next((o.end - o.body_start for o in sections(old)
                           if o.title.lower() == s.title.lower()), 0)
            if (s.end - s.body_start) <= before:
                problems.append(f"section {s.title!r} did not grow")
    return problems


def emit(path, old, new, apply_it, what):
    if old == new:
        print("nothing to change.")
        return 0
    if apply_it:
        atomic_write(path, new)
        print(f"{what}: written to {path}")
    else:
        sys.stdout.writelines(difflib.unified_diff(
            old.splitlines(keepends=True), new.splitlines(keepends=True),
            fromfile=str(path), tofile=str(path) + " (proposed)"))
        print(f"\n{what}: nothing written. Re-run with --apply after the user confirms.")
    return 0


def cmd_list(entries, as_json):
    if as_json:
        print(json.dumps([{k: v for k, v in e.items() if k != "text"} for e in entries],
                         ensure_ascii=False, indent=1))
        return 0
    if not entries:
        print("Watchlist is empty (or the persona has no ## Watchlist section).")
        return 0
    print(f"\n{len(entries)} Watchlist entries\n")
    for e in entries:
        age = days_since(e["dates"][-1]) if e["dates"] else None
        flag = ("PROMOTED" if e["promoted"]
                else "READY" if len(e["sources"]) >= 2 else "waiting")
        print(f"  {e['id'] or '(no id)':<8} {flag:<9} {len(e['sources'])} src"
              + (f", {age}d" if age is not None else "") + f"  {e['title'][:70]}")
    ready = [e for e in entries if not e["promoted"] and len(e["sources"]) >= 2]
    if ready:
        print(f"\n{len(ready)} entry(ies) already cite two or more distinct sources: READY is a\n"
              "hint, not a verdict. Independence is yours to judge — two excerpts from the same\n"
              "meeting, or a post-review note repeating what the panel said, are one occurrence.")
    if any(e["id"] is None for e in entries):
        print("\nSome entries have no id and cannot be addressed: run --assign-ids.")
    return 0


def assign_ids(text, entries=None):
    """-> (new_text, highest_id_number). Numbers every Watchlist bullet that has no `[wl-NN]`,
    continuing from the highest id already in the file. Pure: it writes nothing and prints
    nothing, so the 0.1 -> 0.2 migration (FR-7.3) can run the same numbering as this command
    instead of shelling out to it or copying the loop.
    """
    entries = parse_entries(text) if entries is None else entries
    new, shift = text, 0
    n = max([int(e["id"].split("-")[1]) for e in entries if e["id"]] or [0])
    for e in entries:
        if e["id"]:
            continue
        n += 1
        at = e["abs_start"] + shift
        m = re.match(r"^-[ \t]+", new[at:])
        ins = f"[wl-{n:02d}] "
        new = new[: at + m.end()] + ins + new[at + m.end():]
        shift += len(ins)
    return new, n


def cmd_assign(path, text, entries, apply_it):
    new, n = assign_ids(text, entries)
    return emit(path, text, new, apply_it, f"assign-ids ({n} entries numbered)")


def cmd_promote(path, text, entries, eid, section, note, apply_it):
    repeat_clause_re = locale_regexes()["repeat_clause_re"]
    if re.fullmatch(r"wl-\d+", eid, re.I):
        want = [e for e in entries if (e["id"] or "").lower() == eid.lower()]
    else:
        want = [e for e in entries if eid.lower() in e["title"].lower()]
    if len(want) != 1:
        die(1, f"--promote {eid!r} matched {len(want)} entries. Use the id from --list "
               f"(available: {', '.join(e['id'] or '(no id)' for e in entries)})")
    e = want[0]
    if e["promoted"]:
        die(1, f"{e['id']} is already a promotion record, not a live entry.")
    targets = [s for s in sections(text) if section.lower() in s.title.lower()
               and s.title.lower() != "watchlist"]
    if len(targets) != 1:
        die(1, f"--section {section!r} matched {len(targets)} sections: "
               + ", ".join(t.title for t in sections(text)))
    ttitle, tbody, tend = targets[0].title, targets[0].body_start, targets[0].end

    moved = re.sub(r"^-\s*(\[wl-\d+\]\s*)?", "- ", e["text"]).rstrip()
    # Everything after the entry's last Fact tag is anteroom bookkeeping (the "what would
    # change if it repeats" clause) and is dropped from the promoted line, kept in the
    # promotion record instead — unless it holds a quoted excerpt, which is evidence, not
    # bookkeeping (references/evidence-model.md#Watchlist).
    dropped = ""
    fact_groups = [g for g in paren_groups(moved) if FACT_LABEL_RE.search(g[2])]
    if fact_groups:
        last_end = fact_groups[-1][1]
        tail = moved[last_end:]
        if tail.strip() and not QUOTE_RE.search(tail):
            moved = moved[:last_end].rstrip()
            dropped = tail.strip(" .;—–-")
    if note:
        moved += f" {note.strip()}"
    today = _today().isoformat()
    record = (f"- [{e['id']}] PROMOTED {today} -> {ttitle}. {e['title']}"
              f" (sources: {', '.join(e['sources']) or 'see the promoted entry'})")
    if dropped:
        record += f" — dropped: {dropped}"

    # insert into the target section, at the end of its body
    insert_at = tend
    while insert_at > tbody and text[insert_at - 1] == "\n":
        insert_at -= 1
    new = text[:insert_at] + "\n" + moved + text[insert_at:]
    # replace the Watchlist entry with its promotion record (offsets after the insertion)
    shift = len(moved) + 1 if e["abs_start"] >= insert_at else 0
    a, b = e["abs_start"] + shift, e["abs_end"] + shift
    new = new[:a] + record + new[b:]

    if dropped:
        print(f"dropped from the promoted line (kept in the promotion record): {dropped}")
    if repeat_clause_re.search(moved):
        print("NOTE: the promoted line still carries its 'what would change if it repeats'\n"
              "clause, which belonged to the anteroom. Rewrite that sentence for the body\n"
              "before applying, and keep the tag untouched.\n", file=sys.stderr)
    problems = integrity(text, new, ttitle)
    if problems:
        print("REFUSED: this edit would lose content.\n  " + "\n  ".join(problems), file=sys.stderr)
        print("Nothing was written. This is the check that was missing when a hand-made cut\n"
              "swallowed a section header and only a malformed tag gave it away.", file=sys.stderr)
        return 2
    return emit(path, text, new, apply_it, f"promote {e['id']} -> {ttitle}")


def _run(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("persona")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--assign-ids", action="store_true")
    ap.add_argument("--promote", metavar="ID")
    ap.add_argument("--section", help="target section for --promote")
    ap.add_argument("--note", help="text appended to the promoted entry")
    ap.add_argument("--apply", action="store_true", help="write the file (default: print the diff)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    # validated AFTER parse_args, so --help and an argparse usage error still work under an
    # unknown locale
    locale_err = check_locale()
    if locale_err:
        die(1, locale_err)

    path = Path(a.persona).expanduser()
    if not path.is_file():
        die(1, f"persona not found: {path}")
    text = read_text_lenient(path)
    if watchlist_span(text) is None:
        die(1, f"{path.name} has no '## Watchlist' section.")
    entries = parse_entries(text)

    if a.promote:
        if not a.section:
            die(1, "--promote needs --section")
        return cmd_promote(path, text, entries, a.promote, a.section, a.note, a.apply)
    if a.assign_ids:
        return cmd_assign(path, text, entries, a.apply)
    return cmd_list(entries, a.json)


def main(argv=None):
    try:
        return _run(argv)
    except Refused as e:
        return e.code


if __name__ == "__main__":
    print("deprecated: use beforehand.py watchlist", file=sys.stderr)
    sys.exit(main())
