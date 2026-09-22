#!/usr/bin/env python3
"""List who speaks in a multi-voice source, and extract one speaker's turns safely.

Why this exists. Transcripts open a turn with a marker at the start of a line
(`**Jane Doe:**`, `Jane Doe:`, `[00:12] Jane Doe:`). A participant the platform could not
identify is labelled with whatever it has instead of a name: a masked phone number,
`Guest`, `Speaker 2`. Splitting turns by *a list of known names* silently glues that
person's words onto the previous named speaker's turn, and the excerpts stay verifiable in
the source file, so `verify_quotes.py --lint` passes on a persona that quotes someone
else. Two personas are corrupted at once and nothing reports it.

So this script splits on the *form* of the marker, never on a list of names: every marker
opens a turn, whoever it belongs to. Unidentified speakers become speakers in their own
right, are counted, and by default they make the run fail. It never guesses who they are —
that is the user's judgment, declared with `--map`, and it belongs in the AUDIT line.

A third case is neither named nor unidentified: a *shared microphone*, one platform label
over everyone in a room. The script cannot know that a name covers three people, so the
user declares it — `--map "LABEL=room: <who speaks, in their words>, N present"`, where
`room:` is a fixed English keyword (syntax this script defines, like `=`) and the text
after it is the user's — and the declaration is echoed in the roster, in the AUDIT fragment
and at the head of `--speaker` output, where the turns the clues flagged are marked
`[room?]` for the user to place or drop. Undeclared, the roster prints a
`POSSIBLE SHARED MICROPHONE.` block: those are clues, not findings, and absence of clues is
not evidence of a single voice.

Usage:
  speakers.py SOURCE [--min-chars N] [--json]
  speakers.py SOURCE --speaker LABEL [--include-ambiguous] [--json]
  speakers.py SOURCE --map "LABEL=who they are" [--map ...] [--allow-unidentified]
  speakers.py SOURCE --map "LABEL=room: who speaks, N present" [--map ...]

--json: the roster gains `room_hints` (one entry per flagged turn: label, line, why),
`shared_mic_suspects` (the labels whose clues trip the block), and `folded_labels` (a
plain-style one-off label folded into the turn it interrupted instead of becoming a speaker
of its own, F1: label, line); `--speaker` gains `shared_mic` (was this label declared a
room) and per-turn `room_hint` (its reasons, an empty list when none). Outside `--json`,
each folded label prints as its own `folded labels: <label> (line N)` line on stderr.

Exit codes: 0 clean · 1 usage or unparseable · 2 unidentified speakers not resolved
            3 turns of dubious paternity present and not requested
Unchanged by any of the above: a shared microphone is not resolvable by the script, so it
is a question printed for the user, never a failure state.
"""
import argparse
import json
import re
import sys

sys.dont_write_bytecode = True  # G5, FR-2.6: run directly, this must land before any sibling import

from pathlib import Path  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from personas_lib import LocaleError, locale_regexes, read_text_lenient, source_header_span  # noqa: E402

# --- marker styles, tried in order of how unambiguous they are -----------------------
# Each regex matches at the start of a line and captures the speaker label in group
# "label". An optional timestamp prefix is allowed and discarded.
TS = r"(?:[\[(<]?\s*\d{1,2}:\d{2}(?::\d{2})?(?:\s*[AaPp]\.?[Mm]\.?)?\s*[\])>]?\s*)?"
STYLES = [
    ("bold", re.compile(rf"^[ \t]*{TS}\*\*(?P<label>[^\n]{{1,60}}?)\s*:\s*\*\*[ \t]*", re.M)),
    ("plain", re.compile(
        rf"^[ \t]*{TS}(?P<label>[^\n:]{{1,60}}?)\s*(?:\(\s*\d{{1,2}}:\d{{2}}(?::\d{{2}})?\s*\))?\s*:[ \t]+",
        re.M)),
]

# A label the platform assigned because it had no name for that participant.
PHONE = re.compile(r"^[+(]?[\d][\d\s()*.+-]{4,}$")

# The generic-speaker words, mail-header labels, and the "inside a turn body" marker are
# locale data (FR-4.4: "generic_speaker", "header_labels") — built lazily by
# personas_lib.locale_regexes(), called where each is actually used, never at import time
# (BEFOREHAND_LOCALE may not be set yet when this module is first imported).

# A marker found *inside* a turn body: either bold (a marker that was not at line start)
# or a label that is itself unidentified. Plain prose colons are not flagged.
INLINE_BOLD = re.compile(r"\*\*[^\n]{1,60}?\s*:\s*\*\*")

# The shared-microphone keyword. It is a constant and not locale data because every locale
# key is a recogniser of human-authored text the script has to *read* in the user's language
# (generic labels, mail headers); `room:` is syntax this script defines and the caller types
# on a command line, like `=`, and the AUDIT fragment it lands in is hard-coded English too.
# What follows the keyword is free text in the user's language, exactly like the WHO today.
ROOM_KEY = "room:"

# Thresholds of the shared-microphone clues (room_hints): S1 dominance, S4 sandwich, and the
# floor under which a label has too few turns for any of this to mean anything.
DOMINANT_SHARE = 0.5
SHORT_TURN = 60
LONG_TURN = 200
MIN_ROOM_TURNS = 3

# The tokens of a label that a turn under that same label could name in the third person.
LABEL_TOKEN = re.compile(r"[A-Za-zÀ-ÿ]{3,}")


class Refused(Exception):
    """Raised by die() instead of exiting the process; main() converts it to a return code.

    die() is called from nested helpers (resolve_speaker), not only from main() itself, so
    a bare return-code convention would not unwind the call stack; an exception does. This
    also means an in-process caller of main() (a test, or another module) gets an ordinary
    return code back instead of the whole interpreter exiting under it.
    """
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def die(code, msg):
    print(msg, file=sys.stderr)
    raise Refused(code)


def kind_of(label):
    """named | unidentified — what the platform knew about this participant."""
    s = label.strip().strip("*_ \t")
    if not s or not re.search(r"[A-Za-zÀ-ÿ]", s):
        return "unidentified"
    if PHONE.match(s) or locale_regexes()["generic_re"].match(s):
        return "unidentified"
    return "named"


def strip_header(text):
    """Skip a leading `---` provenance header (save_source.py) without losing line numbers.

    Returns (offset_in_chars, lines_consumed). The header's `key: value` lines would
    otherwise be read as plain-style speaker markers.

    Uses `source_header_span`, not the generic frontmatter block: a source whose first line
    is itself a `---` rule (a transcript export, a markdown divider) is not a save header
    just because it starts with `---` — only the header `save_source.py` actually writes
    (both `sha1` and `source_ref` keys) is recognised and stripped (A7).
    """
    span = source_header_span(text)
    if not span:
        return 0, 0
    return span[1], text[:span[1]].count("\n")


def pick_style(text):
    """The dominant marker style: the one that yields the most turns over >= 2 labels.

    Mixing styles is what produces phantom speakers, so one style wins the whole file.
    """
    header_labels = locale_regexes()["header_labels"]
    best = None
    for name, rx in STYLES:
        hits = list(rx.finditer(text))
        labels = {h.group("label").strip() for h in hits}
        # A plain-style match needs at least two distinct recurring labels to be a
        # transcript rather than prose with colons.
        recurring = {lb for lb in labels
                     if sum(1 for h in hits if h.group("label").strip() == lb) >= 2}
        # Mail headers recur like speakers do, and a mail thread is full of prose lines that
        # end in a colon. A plain-style file is a transcript only when at least two labels
        # that are neither header labels nor prose recur AND they carry most of the turns.
        real = {lb for lb in recurring
                if lb.strip().lower().rstrip(":") not in header_labels and len(lb.split()) <= 5}
        held = sum(1 for h in hits if h.group("label").strip() in real)
        ok = name == "bold" or (len(real) >= 2 and held >= 0.6 * len(hits))
        score = len(hits) if ok else 0
        if score and (best is None or score > best[0]):
            best = (score, name, rx, hits)
    return best


def _all_capitalised(label):
    """True when every word of `label` starts with an uppercase letter: the shape of a name
    ("Jon Park"), not of a sentence ("Bottom line")."""
    words = [w for w in label.split() if w]
    return bool(words) and all(w[0].isupper() for w in words)


def parse(text):
    """-> (style, [turn, ...]). A turn: label, kind, body, line, dubious, why."""
    return _parse(text)[:2]


def _parse(text):
    """-> (style, turns, folded). A turn: label, kind, body, line, dubious, why. `folded`:
    the plain-style one-off labels folded into the turn they interrupted (F1), each
    {"label", "line"}, in source order."""
    off, hdr_lines = strip_header(text)
    body_text = text[off:]
    best = pick_style(body_text)
    if not best:
        return None, [], []
    _, style, _, hits = best
    inline_unident_re = locale_regexes()["inline_unident_re"]

    # F1: in plain style, a label seen exactly once whose words are not all capitalised
    # reads as an ordinary sentence with a colon ("Bottom line: we cut the vendor."), not a
    # transcript marker — folding it into the turn it interrupts keeps that speaker's words
    # in their own turn instead of manufacturing a one-turn speaker that silently steals
    # them. A label seen more than once, or a single-turn capitalised name ("Jon Park:"),
    # is unaffected. The very first marker in the file is never folded: there is no turn yet
    # to fold it into, so it stands as a turn of its own.
    fold = set()
    if style == "plain":
        counts = {}
        for h in hits:
            lb = h.group("label").strip()
            counts[lb] = counts.get(lb, 0) + 1
        have_real = False
        for i, h in enumerate(hits):
            lb = h.group("label").strip()
            if have_real and counts[lb] == 1 and not _all_capitalised(lb):
                fold.add(i)
            else:
                have_real = True

    real = [i for i in range(len(hits)) if i not in fold]
    turns = []
    for pos, i in enumerate(real):
        h = hits[i]
        start = h.end()
        end = hits[real[pos + 1]].start() if pos + 1 < len(real) else len(body_text)
        chunk = body_text[start:end]
        label = h.group("label").strip()
        line = hdr_lines + body_text[: h.start()].count("\n") + 1
        why = []
        if INLINE_BOLD.search(chunk):
            why.append("a bold speaker marker survives inside the turn")
        for m in inline_unident_re.finditer(chunk):
            why.append(f"an unidentified-participant marker inside the turn: {m.group(1).strip()!r}")
            break
        turns.append({
            "label": label,
            "kind": kind_of(label),
            "line": line,
            "text": chunk.strip(),
            "chars": len(chunk.strip()),
            "dubious": bool(why),
            "why": why,
        })
    folded = [{"label": hits[i].group("label").strip(),
              "line": hdr_lines + body_text[: hits[i].start()].count("\n") + 1}
             for i in sorted(fold)]
    return style, turns, folded


def roster(turns, mapping):
    """-> [row, ...] sorted by volume. `mapping` maps a label to what --map declared about
    it: {"who", "shared", "raw"}. `declared_as` stays the raw string the user typed, so a
    reader of the JSON sees the declaration as given; `shared_mic` is the room flag."""
    out = {}
    for t in turns:
        m = mapping.get(t["label"])
        r = out.setdefault(t["label"], {
            "label": t["label"], "kind": t["kind"], "turns": 0, "chars": 0,
            "dubious_turns": 0, "first_line": t["line"],
            "declared_as": m["raw"] if m else None,
            "shared_mic": bool(m and m["shared"]),
        })
        r["turns"] += 1
        r["chars"] += t["chars"]
        r["dubious_turns"] += 1 if t["dubious"] else 0
    return sorted(out.values(), key=lambda r: -r["chars"])


def _names_itself(text, token):
    """True when `token` appears mid-sentence inside a turn of its own label.

    Not at the start of the turn and not right after a full stop: "Priya Raman here" is how
    a person opens, "…and Priya wants the number by Friday" is how a room talks about the
    person whose name is on the microphone.
    """
    for m in re.finditer(r"\b" + re.escape(token) + r"\b", text):
        before = text[: m.start()].rstrip()
        if not before or before[-1] in ".!?":
            continue
        return True
    return False


def _room_signals(turns, rows):
    """-> (hints, counts, suspects). One pass for the three per-turn clues, their per-label
    tallies (S1 dominance included, which is a label-level weight and never a clue line of
    its own) and the labels whose tally trips the printed block."""
    by_label = {}
    for t in turns:
        by_label.setdefault(t["label"], []).append(t)
    total = sum(r["chars"] for r in rows) or 1
    considered = [r for r in rows if r["kind"] == "named"
                  and len(by_label.get(r["label"], [])) >= MIN_ROOM_TURNS]
    named = set(r["label"] for r in considered)
    hints = {}
    counts = dict((lb, {"S1": 0, "S2": 0, "S3": 0, "S4": 0}) for lb in named)

    def add(turn, reason, signal):
        hints.setdefault(turn["line"], []).append(reason)
        counts[turn["label"]][signal] += 1

    for r in considered:
        # S1, dominance: it describes every interview and every pitch, so it only raises the
        # weight of the others, never fires alone.
        if len(rows) >= 3 and r["chars"] >= DOMINANT_SHARE * total:
            counts[r["label"]]["S1"] = 1
        tokens = LABEL_TOKEN.findall(r["label"])
        for t in by_label[r["label"]][1:]:  # never the first turn: that is a self-introduction
            for tok in tokens:
                if _names_itself(t["text"], tok):
                    add(t, "names %r in its own turn" % tok, "S2")
                    break

    for i in range(len(turns) - 1):
        t, nxt = turns[i], turns[i + 1]
        # S3: a handover that nobody took up ("Tom, do you want to add?" — then the same
        # label again). Rhetorical questions are the false positive, hence contributing.
        if t["label"] in named and nxt["label"] == t["label"] \
                and t["text"].rstrip().endswith(("?", "？")):
            add(nxt, "answers its own question", "S3")

    for i in range(1, len(turns) - 1):
        a, b, c = turns[i - 1], turns[i], turns[i + 1]
        # S4: a platform that cuts on pauses produces this inside a monologue too.
        if b["label"] in named and a["label"] == b["label"] and c["label"] == b["label"] \
                and b["chars"] <= SHORT_TURN and a["chars"] >= LONG_TURN and c["chars"] >= LONG_TURN:
            add(b, "a short turn (%dc) between two long ones under the same label" % b["chars"], "S4")

    suspects = [r["label"] for r in considered
                if counts[r["label"]]["S2"] >= 1
                or (counts[r["label"]]["S1"]
                    and counts[r["label"]]["S3"] + counts[r["label"]]["S4"] >= 2)]
    return hints, counts, suspects


def room_hints(turns, rows):
    """-> {line: [reason, ...]} for the turns that read like a shared microphone.

    Computed over named labels with at least MIN_ROOM_TURNS turns, from the text alone:
    S2 a turn naming one of its own label's tokens, S3 a turn answering the question the
    same label just asked, S4 a short turn between two long ones under the same label.
    These are clues, not findings — absence of clues is not evidence of a single voice —
    so nothing here touches an exit code: who spoke into one microphone is the user's word
    (`--map "<label>=room: …"`), never an inference from content.

    Separate from parse() on purpose: the turn list and the `dubious` flag are shared with
    coverage.py and keep their shape and their meaning.
    """
    return _room_signals(turns, rows)[0]


def room_suspects(turns, rows):
    """-> [label, ...] whose clues are worth printing: one self-naming turn, or dominance
    together with two or more of the weaker clues."""
    return _room_signals(turns, rows)[2]


def flagged_by_label(turns, hints):
    """-> {label: K} how many turns of each label the clues flagged."""
    out = {}
    for t in turns:
        if hints.get(t["line"]):
            out[t["label"]] = out.get(t["label"], 0) + 1
    return out


def resolve_speaker(rows, wanted):
    exact = [r for r in rows if r["label"] == wanted]
    if exact:
        return exact[0]
    low = wanted.lower()
    part = [r for r in rows if low in r["label"].lower()]
    if len(part) == 1:
        return part[0]
    if len(part) > 1:
        die(1, "ambiguous --speaker %r, it matches: %s" % (wanted, ", ".join(r["label"] for r in part)))
    die(1, "no speaker %r in this source. Present: %s" % (wanted, ", ".join(r["label"] for r in rows)))


def _run(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source")
    ap.add_argument("--speaker", help="extract only this speaker's turns")
    ap.add_argument("--min-chars", type=int, default=0,
                    help="hide speakers below this volume from the roster")
    ap.add_argument("--map", action="append", default=[], metavar="LABEL=WHO",
                    help="declare who an unidentified label is; repeatable. Your judgment, "
                         "recorded, not the script's guess. LABEL=room: <who speaks>, <N> "
                         "present declares a shared microphone on any label, named or not")
    ap.add_argument("--allow-unidentified", action="store_true",
                    help="proceed with unidentified speakers left undeclared")
    ap.add_argument("--include-ambiguous", action="store_true",
                    help="keep turns of dubious paternity instead of excluding them")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        locale_regexes()  # validates BEFOREHAND_LOCALE lazily and AFTER parse_args, so --help
        # and an argparse usage error still work under an unknown locale
    except LocaleError as e:
        die(1, str(e))

    p = Path(a.source).expanduser()
    if not p.is_file():
        die(1, f"source not found: {p}")
    text = read_text_lenient(p)

    mapping = {}
    for item in a.map:
        if "=" not in item:
            die(1, f"--map wants LABEL=WHO, got: {item!r}")
        k, v = item.split("=", 1)
        v = v.strip()
        shared = v.lower().startswith(ROOM_KEY)
        who = v[len(ROOM_KEY):].strip() if shared else v
        if shared and not who:
            die(1, f"--map room: wants who speaks after the colon, got: {item!r}")
        mapping[k.strip()] = {"who": who, "shared": shared, "raw": v}

    style, turns, folded = _parse(text)
    if not turns:
        die(1, f"no speaker markers found in {p.name}. Supported: '**Name:**', 'Name:', "
               "'[00:12] Name:' at the start of a line. If this is not a multi-voice "
               "source, it does not need this script.")

    rows = roster(turns, mapping)
    present = set(r["label"] for r in rows)
    for k in mapping:
        if k not in present:
            print(f"note: --map label not in this source: {k!r}", file=sys.stderr)
    for f in folded:
        print(f"folded labels: {f['label']} (line {f['line']})", file=sys.stderr)
    unidentified = [r for r in rows if r["kind"] == "unidentified" and not r["declared_as"]]
    dubious = [t for t in turns if t["dubious"]]
    spoken = sum(r["chars"] for r in rows) or 1
    hints = room_hints(turns, rows)
    suspects = room_suspects(turns, rows)
    flagged = flagged_by_label(turns, hints)

    if a.speaker:
        row = resolve_speaker(rows, a.speaker)
        picked = [t for t in turns if t["label"] == row["label"]
                  and (a.include_ambiguous or not t["dubious"])]
        dropped = row["turns"] - len(picked)
        marked = [t for t in picked if hints.get(t["line"])]
        if a.json:
            out_turns = [dict(t, room_hint=hints.get(t["line"], [])) for t in picked]
            print(json.dumps({"source": str(p), "speaker": row["label"], "kind": row["kind"],
                              "declared_as": row["declared_as"], "shared_mic": row["shared_mic"],
                              "turns": out_turns, "excluded_dubious": dropped},
                             ensure_ascii=False, indent=1))
        else:
            print(f"# turns of {row['label']} in {p.name}")
            dubious_note = (f" · {dropped} of dubious paternity excluded "
                            "(--include-ambiguous keeps them)" if dropped else "")
            print(f"# {len(picked)} turns, {sum(t['chars'] for t in picked)} chars" + dubious_note)
            # The marker is printed only once the user has declared the room: before that it
            # would sit on legitimate single-speaker turns all over the file.
            if row["shared_mic"]:
                print(f"# shared microphone: {mapping[row['label']]['who']} — every turn below "
                      "is attributed by the user's word, not by the label; "
                      f"{len(marked)} turns marked [room?] need the user to place them "
                      "before promotion")
            print()
            for t in picked:
                mark = "[room?] " if row["shared_mic"] and hints.get(t["line"]) else ""
                print(f"[L{t['line']}] {mark}{t['text']}\n")
        if dropped and not a.include_ambiguous:
            return 3
        return 0

    if a.json:
        dubious_turns = [{"label": t["label"], "line": t["line"], "why": t["why"]} for t in dubious]
        room = [{"label": t["label"], "line": t["line"], "why": hints[t["line"]]}
                for t in turns if hints.get(t["line"])]
        print(json.dumps({"source": str(p), "marker_style": style, "speakers": rows,
                          "dubious_turns": dubious_turns,
                          "room_hints": room, "shared_mic_suspects": suspects,
                          "unidentified_undeclared": [r["label"] for r in unidentified],
                          "folded_labels": folded},
                         ensure_ascii=False, indent=1))
    else:
        print(f"\nSpeakers in {p.name} ({style} markers, {len(turns)} turns)\n")
        print(f"{'volume':>9}  {'turns':>5}  kind          speaker")
        for r in rows:
            if r["chars"] < a.min_chars:
                continue
            if r["shared_mic"]:
                who = r["label"] + f"  -> shared microphone: {mapping[r['label']]['who']}"
            elif r["declared_as"]:
                who = r["label"] + f"  -> declared: {r['declared_as']}"
            else:
                who = r["label"]
            flags = f"   [{r['dubious_turns']} dubious]" if r["dubious_turns"] else ""
            k = flagged.get(r["label"], 0)
            if k and (r["shared_mic"] or r["label"] in suspects):
                flags += f"   [{k} room?]"
            print(f"{r['chars']:>8,}c  {r['turns']:>5}  {r['kind']:<12}  {who}" + flags)
        print(f"\n{len(rows)} speakers, {spoken:,} characters of speech.")

        if dubious:
            print(f"\n{len(dubious)} turns of DUBIOUS PATERNITY. The label says one person, the body\n"
                  "carries a second speaker marker: the words inside are probably not theirs.\n"
                  "They are excluded from --speaker unless you pass --include-ambiguous.")
            for t in dubious[:5]:
                print(f"  L{t['line']} labelled {t['label']!r}: {t['why'][0]}")
            if len(dubious) > 5:
                print(f"  ... and {len(dubious) - 5} more")

        undeclared_suspects = [lb for lb in suspects if not mapping.get(lb, {}).get("shared")]
        if undeclared_suspects:
            print("\nPOSSIBLE SHARED MICROPHONE. The platform labels a microphone, not a voice: "
                  "one named\nlabel can cover everyone in a room. These are clues, not findings — "
                  "absence of clues is\nnot evidence of a single voice, and nothing here fails. "
                  "If the user knows the room was\nshared, declare it in their words and it goes "
                  "into the AUDIT line:")
            for lb in undeclared_suspects:
                clues = [(t["line"], hints[t["line"]][0])
                         for t in turns if t["label"] == lb and hints.get(t["line"])]
                print(f"  --map \"{lb}=room: <who speaks>, <N> present\"    ({len(clues)} clues)")
                for line, why in clues[:5]:
                    print(f"    L{line}: {why}")
                if len(clues) > 5:
                    print(f"    ... and {len(clues) - 5} more")

        if unidentified:
            print("\nUNIDENTIFIED SPEAKERS. The platform had no name for these participants,\n"
                  "so their words belong to nobody until you say who they are. Do not guess\n"
                  "from the surrounding text: decide from something outside this file (a mail\n"
                  "signature, the invite, the user's own memory) and declare it:")
            for r in unidentified:
                print(f"  --map \"{r['label']}=<who>\"    "
                      f"({r['turns']} turns, {r['chars']:,}c, first at L{r['first_line']})")
            print("  ...or --allow-unidentified to go on with them unattributed.")

        declared = "; ".join(f"{r['label']} = {r['declared_as']}"
                             for r in rows if r["declared_as"] and not r["shared_mic"])
        shared_rows = [r for r in rows if r["shared_mic"]]
        # A room is its own clause: it says nothing about how many labels the platform could
        # not name, and it records who attributed the turns and how many were questioned.
        shared_seg = ""
        if shared_rows:
            parts = "; ".join(
                f"{r['label']} = {ROOM_KEY} {mapping[r['label']]['who']}; attribution by the user"
                f"; {flagged.get(r['label'], 0)} turns flagged" for r in shared_rows)
            shared_seg = f", {len(shared_rows)} shared microphone ({parts})"
        note = (f"speaker attribution: {len(rows)} labels, {len(unidentified)} unidentified"
                + (f" ({declared})" if declared else "")
                + shared_seg
                + f", {len(dubious)} turns of dubious paternity excluded")
        print(f"\nAUDIT note fragment:\n  {note}")

    if unidentified and not a.allow_unidentified:
        return 2
    if dubious and not a.include_ambiguous:
        return 3
    return 0


def main(argv=None):
    try:
        return _run(argv)
    except Refused as e:
        return e.code


if __name__ == "__main__":
    print("deprecated: use beforehand.py speakers", file=sys.stderr)
    sys.exit(main())
