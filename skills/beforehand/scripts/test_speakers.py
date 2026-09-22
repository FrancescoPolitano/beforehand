#!/usr/bin/env python3
"""Tests for speakers.py on synthetic multi-voice fixtures.

The case that matters is the first one: a participant the platform could not identify,
whose turn sits between two turns of a named speaker. Splitting by known names glues that
text onto the named speaker and nothing downstream can notice.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True  # G5: a suite run on its own leaves no __pycache__

HERE = Path(__file__).parent
SRC = HERE / "test_fixtures/multivoice/2026-09-02-steering-call.txt"
checks = []


def run(*a):
    return subprocess.run([sys.executable, str(HERE / "speakers.py"), *[str(x) for x in a]],
                          capture_output=True, text=True)


def write(name, body):
    p = Path(tempfile.mkdtemp()) / name
    p.write_text(body, encoding="utf-8")
    return p


# ---- the regression: the masked-phone participant is a speaker, not part of a named turn
r = run(SRC, "--json")
d = json.loads(r.stdout)
labels = {s["label"]: s for s in d["speakers"]}
checks.append(("masked phone label is its own speaker", "+44 7700 *** **31" in labels, list(labels)))
checks.append(("it is classified unidentified",
               labels.get("+44 7700 *** **31", {}).get("kind") == "unidentified",
               labels.get("+44 7700 *** **31")))
checks.append(("named speakers are classified named",
               all(labels[n]["kind"] == "named" for n in ("Dana Whitfield", "Marco Ferri", "Ines Okafor")),
               {n: labels[n]["kind"] for n in labels}))
checks.append(("unidentified speaker makes the run fail", r.returncode == 2, r.returncode))

r = run(SRC, "--speaker", "Dana Whitfield")
checks.append(("the phone participant's words are NOT in the named speaker's turns",
               "replication lag" not in r.stdout and "staging cluster" not in r.stdout, r.stdout))
checks.append(("the named speaker's own words are there",
               "procurement closes" in r.stdout and "confirm on the eighteenth" in r.stdout, r.stdout))

# ---- the second case: a marker that is mid-line, so the split cannot cut on it
checks.append(("mid-line marker makes the carrying turn dubious",
               any(t["label"] == "Marco Ferri" for t in d["dubious_turns"]), d["dubious_turns"]))
r = run(SRC, "--speaker", "Marco Ferri")
checks.append(("dubious turns are excluded from extraction by default",
               "repeat the lag figure" not in r.stdout, r.stdout))
checks.append(("excluding them is reported, not silent", "dubious paternity excluded" in r.stdout, r.stdout))
checks.append(("and it is a non-zero exit", r.returncode == 3, r.returncode))
r = run(SRC, "--speaker", "Marco Ferri", "--include-ambiguous")
checks.append(("--include-ambiguous brings them back",
               "repeat the lag figure" in r.stdout and r.returncode == 0, r.stdout))

# ---- declaring who the unidentified speaker is
r = run(SRC, "--map", "+44 7700 *** **31=cto-someone")
checks.append(("a declared label no longer fails the run", r.returncode == 3, r.returncode))
checks.append(("the declaration is echoed for the AUDIT line",
               "+44 7700 *** **31 = cto-someone" in r.stdout, r.stdout))
r = run(SRC, "--allow-unidentified", "--include-ambiguous")
checks.append(("both overrides together exit clean", r.returncode == 0, r.returncode))

# ---- the script never guesses an identity
checks.append(("no speaker is silently renamed",
               all(s["declared_as"] is None for s in d["speakers"]), d["speakers"]))

# ---- plain-text markers, the other common transcript shape
plain = write("plain.txt", (
    "Ada Lovelace: the budget is the constraint, not the schedule.\n"
    "Speaker 2: I disagree, we have three weeks of slack.\n"
    "Ada Lovelace: three weeks that procurement already spent.\n"
    "Speaker 2: fair.\n"))
r = run(plain, "--json")
d2 = json.loads(r.stdout)
checks.append(("plain markers are parsed", d2["marker_style"] == "plain", d2["marker_style"]))
checks.append(("a generic label counts as unidentified",
               "Speaker 2" in d2["unidentified_undeclared"], d2["unidentified_undeclared"]))

# ---- prose with colons is not a transcript
prose = write("prose.md", (
    "# Note\n\nNota: the vendor replied yesterday.\n\n"
    "The point is this: we cannot commit before the audit.\n"))
r = run(prose)
checks.append(("prose with colons is refused, not invented into speakers",
               r.returncode == 1 and "no speaker markers" in r.stderr, (r.returncode, r.stderr)))

# ---- a save_source.py provenance header is not read as speech
withhdr = write("hdr.txt", (
    '---\nsource_ref: "call of 2 September"\ndate: "2026-09-02"\ntype: "private-communication"\n'
    'provenance: "machine-transcribed"\nauthor: ""\nchannel: ""\nsaved_on: "2026-09-02"\n'
    'sha1: "59ae07087884e8edcaede9b180f3a9c82c2df4b6"\nschema: "0.1"\n---\n'
    "**Ada Lovelace:** the budget is the constraint.\n"
    "**Grace Hopper:** then we move the date.\n"))
r = run(withhdr, "--json")
d3 = json.loads(r.stdout)
checks.append(("provenance header is skipped",
               {s["label"] for s in d3["speakers"]} == {"Ada Lovelace", "Grace Hopper"},
               [s["label"] for s in d3["speakers"]]))
checks.append(("line numbers still point at the real line",
               d3["speakers"][0]["first_line"] >= 11, d3["speakers"][0]["first_line"]))

# ---- A7: a source whose first line is a `---` rule, and carries a second `---` rule
# further down (an ordinary markdown divider in the transcript, not a save header), must
# not be mistaken for a frontmatter block: it has neither `sha1` nor `source_ref`, so
# nothing is stripped and every turn survives, including the one sandwiched between the
# two rules.
rule_first = write("rule-first.txt", (
    "---\n"
    "**Mara Toft:** we ship in March, that part is not moving.\n"
    "\n"
    "---\n"
    "\n"
    "**Jon Park:** ok, I will tell procurement.\n"
    "**Mara Toft:** good, thanks for confirming.\n"
    "**Jon Park:** will do.\n"))
r = run(rule_first, "--json")
d3b = json.loads(r.stdout)
checks.append(("a source with two `---` rules keeps both speakers",
               {s["label"] for s in d3b["speakers"]} == {"Mara Toft", "Jon Park"},
               [s["label"] for s in d3b["speakers"]]))
r = run(rule_first, "--speaker", "Mara Toft")
checks.append(("the turn sandwiched between the two rules is not swallowed as frontmatter",
               "we ship in March" in r.stdout, r.stdout))

# ---- F1: a one-off "Label:" line in plain style is prose with a colon, not a new speaker.
# "Bottom line" is seen once and its words are not all capitalised (fold it into the turn
# it interrupts); "Jon Park" is also seen once but IS a capitalised name (it stays a
# speaker) — both labels recur enough elsewhere that plain style is still picked.
fold_src = write("fold.txt", (
    "Mara Toft: the vendor deal needs to close this month, procurement is already asking.\n"
    "Priti Nair: agreed, but only if legal signs off first.\n"
    "Mara Toft: we already briefed legal twice.\n"
    "Bottom line: we cut the vendor if legal stalls again.\n"
    "Priti Nair: understood, I will chase legal today.\n"
    "Jon Park: he confirmed the budget line this morning.\n"
    "Mara Toft: good, then we hold the date.\n"))
r = run(fold_src, "--json")
d6 = json.loads(r.stdout)
fold_labels = {s["label"] for s in d6["speakers"]}
checks.append(("the one-off lower-case-worded label is not a speaker",
               "Bottom line" not in fold_labels, fold_labels))
checks.append(("a single-turn but capitalised name stays a speaker",
               "Jon Park" in fold_labels, fold_labels))
checks.append(("folded_labels names it and its line, pinned key",
               d6["folded_labels"] == [{"label": "Bottom line", "line": 4}], d6["folded_labels"]))
checks.append(("exit codes are unchanged by folding (clean roster, no dubious/unidentified)",
               r.returncode == 0, r.returncode))
r = run(fold_src, "--speaker", "Mara Toft")
checks.append(("the folded text lands inside the turn it interrupted, not lost",
               "we already briefed legal twice" in r.stdout
               and "we cut the vendor if legal stalls again" in r.stdout, r.stdout))
r = run(fold_src)
checks.append(("the fold is reported on stderr with the pinned prefix",
               "folded labels: Bottom line (line 4)" in r.stderr, r.stderr))

# ---- resolution of --speaker
r = run(SRC, "--speaker", "dana")
checks.append(("--speaker resolves a unique case-insensitive fragment", r.returncode == 0, r.stderr))
r = run(SRC, "--speaker", "Nobody Here")
checks.append(("an unknown speaker is a usage error listing who is present",
               r.returncode == 1 and "Dana Whitfield" in r.stderr, (r.returncode, r.stderr)))

# ---- `user` and `anonymous` are on the shipped generic-speaker list: a chat or webinar
# export labels its real participants that way, so the label names a seat, not a person, and
# stays unidentified until --map says who sat in it.
sys.path.insert(0, str(HERE))
import speakers as sp  # noqa: E402

checks.append(("a chat export's `User` label is unidentified",
               sp.kind_of("User") == "unidentified", sp.kind_of("User")))
checks.append(("a numbered `Anonymous 3` label is unidentified too",
               sp.kind_of("Anonymous 3") == "unidentified", sp.kind_of("Anonymous 3")))

# ---- the third case: a named label that is a whole room. `named` never meant `one voice`,
# and nothing structural betrays a shared microphone: the script prints clues, the user
# declares the room, and the declaration — not the label — is what attributes the turns.
ROOM = HERE / "test_fixtures/multivoice/2026-09-09-room-call.txt"
ROOM_MAP = "Priya Raman=room: Priya and two engineers, 3 present"

r = run(ROOM)
checks.append(("a room behind a named label is not a failure state", r.returncode == 0, r.returncode))
checks.append(("it is printed as a question for the user, with the command to answer it",
               "POSSIBLE SHARED MICROPHONE." in r.stdout
               and '--map "Priya Raman=room: <who speaks>, <N> present"' in r.stdout, r.stdout))
checks.append(("and the block says a clean run proves nothing",
               "not evidence of a single voice" in r.stdout, r.stdout))

r = run(ROOM, "--json")
d4 = json.loads(r.stdout)
why_by_line = dict((h["line"], h["why"][0]) for h in d4["room_hints"])
reasons = list(why_by_line.values())
checks.append(("three turns carry a clue, all under the room label",
               len(d4["room_hints"]) == 3
               and all(h["label"] == "Priya Raman" for h in d4["room_hints"]), d4["room_hints"]))
checks.append(("one clue of each kind, each with its pinned wording",
               sum(1 for w in reasons if w == "names 'Priya' in its own turn") == 1
               and sum(1 for w in reasons if w == "answers its own question") == 1
               and sum(1 for w in reasons if w.startswith("a short turn (")
                       and w.endswith("c) between two long ones under the same label")) == 1,
               reasons))
room_row = [s for s in d4["speakers"] if s["label"] == "Priya Raman"][0]
checks.append(("the label's own first turn is never a clue: that one is a self-introduction",
               room_row["first_line"] not in why_by_line, (room_row["first_line"], sorted(why_by_line))))
checks.append(("the suspect label is named for the caller",
               d4["shared_mic_suspects"] == ["Priya Raman"], d4["shared_mic_suspects"]))

# ---- the false-positive guard: a presenter holding the floor is not a room
presenter = write("presenter.txt", (
    "**Ada Lovelace:** " + "the budget is the constraint and the schedule follows it. " * 6 + "\n"
    "**Grace Hopper:** agreed on the budget, and the schedule can take it.\n"
    "**Alan Turing:** the rehearsal is the part I would protect.\n"
    "**Ada Lovelace:** " + "then we hold the date and tell procurement tomorrow morning. " * 6 + "\n"
    "**Grace Hopper:** fine by me, I will send the note.\n"
    "**Ada Lovelace:** " + "the last point is the rehearsal, which nobody has booked yet. " * 6 + "\n"))
r = run(presenter)
checks.append(("a dominant single speaker with no clue prints no block and does not fail",
               "POSSIBLE SHARED MICROPHONE" not in r.stdout and r.returncode == 0,
               (r.returncode, r.stdout)))
r = run(SRC)
checks.append(("neither does the existing multi-voice fixture",
               "POSSIBLE SHARED MICROPHONE" not in r.stdout, r.stdout))

# ---- declaring the room: the user's words, echoed where the AUDIT line will copy them
r = run(ROOM, "--map", ROOM_MAP)
checks.append(("a declared room is echoed in the roster",
               "-> shared microphone: Priya and two engineers, 3 present" in r.stdout, r.stdout))
checks.append(("the AUDIT fragment records the declaration, who attributed it, and how many "
               "turns were questioned",
               "speaker attribution: 3 labels, 0 unidentified, 1 shared microphone (Priya "
               "Raman = room: Priya and two engineers, 3 present; attribution by the user; "
               "3 turns flagged), 0 turns of dubious paternity excluded" in r.stdout, r.stdout))
checks.append(("once declared, the clue block gives way to the declaration",
               "POSSIBLE SHARED MICROPHONE" not in r.stdout, r.stdout))
r = run(SRC, "--map", "+44 7700 *** **31=cto-someone")
checks.append(("a source with no room keeps the fragment it always had, byte for byte",
               "speaker attribution: 4 labels, 0 unidentified (+44 7700 *** **31 = cto-someone)"
               ", 1 turns of dubious paternity excluded" in r.stdout
               and "shared microphone" not in r.stdout, r.stdout))

# ---- extraction under a room label: every turn, the flagged ones marked for the user
r = run(ROOM, "--speaker", "Priya Raman", "--map", ROOM_MAP)
turn_lines = [ln for ln in r.stdout.splitlines() if ln.startswith("[L")]
checks.append(("the header says the turns are attributed by the user, not by the label",
               "# shared microphone: Priya and two engineers, 3 present" in r.stdout
               and "3 turns marked [room?] need the user to place them" in r.stdout, r.stdout))
checks.append(("the flagged turns are marked and kept, and the exit code does not move",
               len([ln for ln in turn_lines if "[room?] " in ln]) == 3
               and len(turn_lines) == 8 and r.returncode == 0, (r.returncode, turn_lines)))
r = run(ROOM, "--speaker", "Priya Raman", "--map", ROOM_MAP, "--json")
d5 = json.loads(r.stdout)
checks.append(("--json carries the declaration and the per-turn reasons",
               d5["shared_mic"] is True and len(d5["turns"]) == 8
               and sum(1 for t in d5["turns"] if t["room_hint"]) == 3
               and all(isinstance(t["room_hint"], list) for t in d5["turns"]), d5))
r = run(ROOM, "--speaker", "Priya Raman")
checks.append(("undeclared, no turn is marked: the marker follows the user's word",
               "[room?]" not in r.stdout and "# shared microphone" not in r.stdout, r.stdout))

# ---- the grammar of the declaration
r = run(ROOM, "--map", "Priya Raman=ROOM:   Priya and two engineers, 3 present")
checks.append(("the room keyword is case- and space-insensitive",
               "-> shared microphone: Priya and two engineers, 3 present" in r.stdout, r.stdout))
r = run(ROOM, "--map", "Priya Raman=room:")
checks.append(("an empty declaration is a usage error, never an empty attribution",
               r.returncode == 1
               and "--map room: wants who speaks after the colon" in r.stderr,
               (r.returncode, r.stderr)))
r = run(ROOM, "--map", "Nobody Here=room: someone else, 2 present")
checks.append(("a --map on a label absent from the source is noted, not silently dropped",
               "note: --map label not in this source: 'Nobody Here'" in r.stderr
               and r.returncode == 0, (r.returncode, r.stderr)))

# ---- `room:` is syntax this script defines, not a word it has to recognise in the user's
# language: it parses identically under a locale that knows nothing about it.
xx_env = dict(os.environ, BEFOREHAND_LOCALE="xx",
              BEFOREHAND_LOCALE_DIR=str(HERE / "test_fixtures/locales"))
r = subprocess.run([sys.executable, str(HERE / "speakers.py"), str(ROOM), "--map", ROOM_MAP],
                   capture_output=True, text=True, env=xx_env)
checks.append(("the room declaration parses under another locale",
               r.returncode == 0
               and "-> shared microphone: Priya and two engineers, 3 present" in r.stdout,
               (r.returncode, r.stdout, r.stderr)))

fails = [c for c in checks if not c[1]]
for n, ok, got in checks:
    print(("ok   " if ok else "FAIL ") + n + ("" if ok else f" -> {str(got)[:300]}"))
print(f"\n{len(checks)-len(fails)}/{len(checks)} passed")
sys.exit(1 if fails else 0)
