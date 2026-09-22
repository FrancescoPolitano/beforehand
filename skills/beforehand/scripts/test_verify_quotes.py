#!/usr/bin/env python3
"""Regression test for verify_quotes.py — run from the scripts/ directory: python3 test_verify_quotes.py"""
import json
import pathlib
import subprocess
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True  # G5: a suite run on its own leaves no __pycache__

HERE = Path(__file__).parent
out = subprocess.run(
    [sys.executable, HERE / "verify_quotes.py", HERE / "test_fixtures/variants/persona.md",
     "--sources-root", str(HERE), "--json"],
    capture_output=True, text=True)
try:
    data = json.loads(out.stdout)
except json.JSONDecodeError:
    print("FAIL: --json output not parseable\n", out.stdout[-800:], out.stderr[-800:])
    sys.exit(1)

expected_tags = 11
statuses = {}
for r in data["results"]:
    statuses.setdefault(r["tag"], []).append(r["status"])

checks = [
    ("tag count", data["summary"]["tags"] == expected_tags, data["summary"]["tags"]),
    ("canonical VERIFIED", statuses.get('1') == ["VERIFIED"], statuses.get('1')),
    ("same-source inherits ref", statuses.get('2') == ["VERIFIED"], statuses.get('2')),
    ("quote before tag", statuses.get('3') == ["VERIFIED"], statuses.get('3')),
    ("quote before comma-form tag", statuses.get('4') == ["VERIFIED"], statuses.get('4')),
    ("accent folding", statuses.get('5') == ["VERIFIED"], statuses.get('5')),
    ("two excerpts both checked", statuses.get('6') == ["VERIFIED", "VERIFIED"], statuses.get('6')),
    ("lead-in text ignored", statuses.get('7') == ["VERIFIED"], statuses.get('7')),
    ("fabrication NOT FOUND", statuses.get('8') == ["NOT FOUND"], statuses.get('8')),
    ("no excerpt UNPARSEABLE", statuses.get('9') == ["UNPARSEABLE"], statuses.get('9')),
    ("missing file UNVERIFIABLE", statuses.get('10') == ["UNVERIFIABLE"], statuses.get('10')),
    ("promotion marker parsed", statuses.get('11') == ["VERIFIED"], statuses.get('11')),
    # default mode exits 0
    ("lint exit code 1 on NOT FOUND/UNPARSEABLE", out.returncode == 0, out.returncode),
]
lint = subprocess.run([sys.executable, HERE / "verify_quotes.py", HERE / "test_fixtures/variants/persona.md",
                       "--sources-root", str(HERE), "--lint"], capture_output=True, text=True)
checks.append(("--lint exits 1 when the store has NOT FOUND or UNPARSEABLE",
               lint.returncode == 1, lint.returncode))
checks.append(("--lint reports unparseable count", "UNPARSEABLE: 1" in lint.stdout, lint.stdout[-300:]))

# ---- FR-1.1: paths with spaces, commas, Windows form, frontmatter sources
out2 = subprocess.run([sys.executable, HERE / "verify_quotes.py", HERE / "test_fixtures/paths/persona.md",
                       "--sources-root", str(HERE), "--json"], capture_output=True, text=True)
d2 = json.loads(out2.stdout)
st2, ref2 = {}, {}
for r in d2["results"]:
    st2.setdefault(r["tag"], []).append(r["status"])
    ref2[r["tag"]] = r["ref"]
tag6_reason = d2["results"][[r["tag"] for r in d2["results"]].index("6")]["reason"]
checks += [
    ("spaces: plain path VERIFIED", st2.get('1') == ["VERIFIED"], (st2.get('1'), ref2.get('1'))),
    ("spaces: lead-in before path VERIFIED", st2.get('2') == ["VERIFIED"], (st2.get('2'), ref2.get('2'))),
    ("spaces: trailing period stripped", st2.get('3') == ["VERIFIED"], (st2.get('3'), ref2.get('3'))),
    ("comma: backtick-quoted path VERIFIED, one excerpt", st2.get('4') == ["VERIFIED"], st2.get('4')),
    ("unresolvable: whole field reported",
     ref2.get('5') == "test_fixtures/paths/no such dir/missing file.txt", ref2.get('5')),
    ("windows: recognised as path (UNVERIFIABLE, not 'not a path')",
     st2.get('6') == ["UNVERIFIABLE"] and "not a path" not in tag6_reason, d2["results"]),
    ("url unchanged", st2.get('7') == ["UNVERIFIABLE"], st2.get('7')),
    ("frontmatter never satisfies an excerpt", st2.get('8') == ["NOT FOUND"], st2.get('8')),
]

# ---- lint_persona API used by reindex.py
sys.path.insert(0, str(HERE))
import verify_quotes as vq  # noqa: E402

lp = vq.lint_persona(HERE / "test_fixtures/variants/persona.md", HERE)
checks += [
    ("lint_persona status fail on fixture with NOT FOUND", lp["status"] == "fail", lp["status"]),
    ("lint_persona label pinned format", lp["label"].startswith("fail ("), lp["label"]),
]
lp2 = vq.lint_persona(HERE / "test_fixtures/paths/persona.md", HERE)
checks += [("lint_persona counts unresolved", lp2["counts"]["unresolved"] >= 2, lp2["counts"])]

lp3 = vq.lint_persona(HERE / "test_fixtures/inherited/persona.md", HERE)
checks += [
    ("lint_persona label reports inherited refs", "inherited refs" in lp3["label"], lp3["label"]),
    ("lint_persona counts inherited", lp3["counts"]["inherited"] >= 1, lp3["counts"]),
    ("lint_persona never labels a real issue as 0 issues", lp3["label"] != "warn (0 issues)", lp3["label"]),
]

# ---- FR: excerpt placement (MISPLACED vs UNPARSEABLE)
# The two used to be reported identically, so a formatting slip and the gravest violation
# the model defines produced the same error message.
FIX = HERE / "test_fixtures/placement/persona.md"
lp4 = vq.lint_persona(FIX, HERE)
st4 = {r["tag"]: r["status"] for r in lp4["results"]}
checks += [
    ("excerpt inside the tag is VERIFIED", st4['1'] == "VERIFIED", st4),
    ("excerpt abutting the tag stays VERIFIED (documented form)", st4['2'] == "VERIFIED", st4),
    ("excerpt after the tag is found, not UNPARSEABLE", st4['3'] == "MISPLACED", st4),
    ("excerpt far away in the same item is MISPLACED", st4['4'] == "MISPLACED", st4),
    ("a tag with no excerpt anywhere stays UNPARSEABLE", st4['5'] == "UNPARSEABLE", st4),
    ("a misplaced excerpt absent from the source is still NOT FOUND", st4['6'] == "NOT FOUND", st4),
    ("misplaced excerpts are counted in the label", "misplaced excerpts" in lp4["label"], lp4["label"]),
]

# MISPLACED alone warns, never blocks: the evidence is there, only the formatting is off.
only_mis = pathlib.Path(tempfile.mkdtemp()) / "p.md"
body = FIX.read_text(encoding="utf-8")
only_mis.write_text(body.split("## Red lines")[0], encoding="utf-8")
lp5 = vq.lint_persona(only_mis, HERE)
checks += [
    ("misplaced only -> warn, not fail", lp5["status"] == "warn", lp5["status"]),
    ("misplaced only -> lint exits 0",
     subprocess.run([sys.executable, str(HERE / "verify_quotes.py"), str(only_mis),
                     "--sources-root", str(HERE), "--lint"], capture_output=True).returncode == 0, None),
]

# --fix-tags proposes, never writes
before = FIX.read_bytes()
r = subprocess.run([sys.executable, str(HERE / "verify_quotes.py"), str(FIX),
                    "--sources-root", str(HERE), "--fix-tags"], capture_output=True, text=True)
checks += [
    ("--fix-tags proposes a rewrite for each misplaced tag", r.stdout.count("+++ proposed") == 2, r.stdout),
    ("the rewrite puts the excerpt inside the tag",
     '(Fact — "the estimate doesn\'t hold - e troppo ottimista", test_fixtures/placement/source.txt'
     in r.stdout, r.stdout),
    ("the comma form does not produce a double comma", ", ," not in r.stdout, r.stdout),
    ("--fix-tags writes nothing", FIX.read_bytes() == before, None),
    ("--fix-tags says a human must re-read the source", "Re-read the source" in r.stdout, r.stdout),
]

# ---- FR-2.2: joined Fact tags (several Facts sharing one set of parentheses)
JOINED = HERE / "test_fixtures/joined/persona.md"
outj = subprocess.run([sys.executable, HERE / "verify_quotes.py", str(JOINED),
                       "--sources-root", str(HERE), "--json"], capture_output=True, text=True)
try:
    dj = json.loads(outj.stdout)
except json.JSONDecodeError:
    print("FAIL: joined --json output not parseable\n", outj.stdout[-800:], outj.stderr[-800:])
    sys.exit(1)
stj = {}
for r in dj["results"]:
    stj.setdefault(r["tag"], []).append(r["status"])
checks += [
    ("joined: first item splits into #1.1 and #1.2",
     set(stj) >= {"1.1", "1.2", "2.1", "2.2", "3"}, sorted(stj)),
    ("joined: #1.1 VERIFIED (ref a)", stj.get("1.1") == ["VERIFIED"], stj.get("1.1")),
    ("joined: #1.2 VERIFIED (ref b)", stj.get("1.2") == ["VERIFIED"], stj.get("1.2")),
    ("joined: fabricated second half is NOT FOUND on #2.2 only", stj.get("2.1") == ["VERIFIED"]
     and stj.get("2.2") == ["NOT FOUND"], (stj.get("2.1"), stj.get("2.2"))),
    ("joined: semicolon inside one excerpt stays a single un-joined tag #3",
     stj.get("3") == ["VERIFIED"], stj.get("3")),
    ("joined: a joined group can carry a MISPLACED segment, #4.1 MISPLACED",
     stj.get("4.1") == ["MISPLACED"], stj.get("4.1")),
    ("joined: the other segment of that group is independently VERIFIED, #4.2",
     stj.get("4.2") == ["VERIFIED"], stj.get("4.2")),
    ("joined: summary counts 3 joined tags (groups, not segments)",
     dj["summary"]["joined_tags"] == 3, dj["summary"]["joined_tags"]),
]
outj_text = subprocess.run([sys.executable, HERE / "verify_quotes.py", str(JOINED),
                            "--sources-root", str(HERE)], capture_output=True, text=True)
checks.append(("joined: text report prints 'joined tags: 3'",
               "joined tags: 3" in outj_text.stdout, outj_text.stdout))

rj = subprocess.run([sys.executable, str(HERE / "verify_quotes.py"), str(JOINED),
                     "--sources-root", str(HERE), "--fix-tags"], capture_output=True, text=True)
checks += [
    ("joined: --fix-tags proposes a split for the joined group in item 1",
     rj.stdout.count("--- tag #1 as written") == 1, rj.stdout),
    ("joined: --fix-tags emits two separate parentheses for item 1",
     ') (Fact — "delta epsilon zeta"' in rj.stdout, rj.stdout),
    ("joined: --fix-tags does not split the un-joined semicolon-inside tag",
     "--- tag #3 as written" not in rj.stdout, rj.stdout),
    # a joined group with a MISPLACED segment must print exactly one proposal for that
    # group (the split, carrying the moved excerpt), never a second, conflicting one
    ("joined+MISPLACED: exactly one proposal is printed for group #4",
     rj.stdout.count("--- tag #4 as written") == 1, rj.stdout),
    ("joined+MISPLACED: the proposed text carries both excerpts, each inside its own tag",
     '(Fact — "alpha beta gamma", test_fixtures/joined/source-a.txt' in rj.stdout
     and '(Fact — "delta epsilon zeta", test_fixtures/joined/source-b.txt' in rj.stdout, rj.stdout),
    ("joined+MISPLACED: the moved excerpt is not also left dangling in the prose",
     'group: "alpha beta gamma" and more words here (Fact —'
     not in rj.stdout.split("--- tag #4 as written")[1].split("+++ proposed")[1], rj.stdout),
    ("a split explains that no excerpt changes, once",
     rj.stdout.count("A split changes no excerpt") == 1, rj.stdout),
]

# ---- joined is never, by itself, a failure: --lint exits 0 on an all-VERIFIED joined persona
ONLY_VERIFIED = pathlib.Path(tempfile.mkdtemp()) / "p.md"
joined_body = JOINED.read_text(encoding="utf-8")
kept = "\n".join(ln for ln in joined_body.splitlines()
                 if not ln.startswith("- Fabricated second")
                 and not ln.startswith("- Misplaced in a joined group"))
ONLY_VERIFIED.write_text(kept + "\n", encoding="utf-8")
lint_ok = subprocess.run([sys.executable, str(HERE / "verify_quotes.py"), str(ONLY_VERIFIED),
                          "--sources-root", str(HERE), "--lint"], capture_output=True, text=True)
checks += [
    ("joined, all VERIFIED: --lint exits 0", lint_ok.returncode == 0, lint_ok.returncode),
]

# ================================================================ 0.3.1
import os  # noqa: E402


def safe(fn, *a, **kw):
    """A missing helper fails a check instead of crashing the suite."""
    try:
        return fn(*a, **kw)
    except Exception as e:  # noqa: BLE001
        return "error: %s: %s" % (e.__class__.__name__, e)


def match(ex, src):
    return vq.match_excerpt(ex, src)


def kind_of(ex, src):
    r = safe(match, ex, src)
    return r[0] if isinstance(r, tuple) else r


PAD = ("Jon: the weather was fine and we talked about lunch for a while. "
       "Ada: the train was late again this morning, as usual. "
       "Jon: someone should water the plants in the lobby.")

# ---- A1: a negation is never "close enough", in either direction, short or long source
A1_PAIRS = [
    ("we will approve the budget this quarter", "we will not approve the budget this quarter"),
    ("it is impossible to deliver in q3", "it is possible to deliver in q3"),
    ("we can't sign the contract", "we can sign the contract"),
    ("illegal is fine", "legal is fine"),
]
for said, quoted in A1_PAIRS:
    for a, b in ((said, quoted), (quoted, said)):
        for src in ("Mara: " + a + ".", "Mara: " + a + ". " + PAD):
            checks.append(("A1: %r against %r (%d chars) is None" % (b, a, len(src)),
                           kind_of(b, src) is None, safe(match, b, src)))

# ---- A2: the verdict does not depend on how much unrelated text the source holds
A2_SRC = "Mara: we are gonna approve the budget in the third quarter."
A2_EX = "we are going to approve the budget in the third quarter"
checks.append(("A2: same kind for a source and the same source + 3 unrelated sentences",
               kind_of(A2_EX, A2_SRC) == kind_of(A2_EX, A2_SRC + " " + PAD),
               (kind_of(A2_EX, A2_SRC), kind_of(A2_EX, A2_SRC + " " + PAD))))
A2_SUB_SRC = "Mara: we are going to approve the budget in the third quarter."
A2_SUB_EX = "we are going to approve the budget in the fourth quarter"
checks.append(("A2: a one-word substitution is approximate, short source",
               kind_of(A2_SUB_EX, A2_SUB_SRC) == "approximate", safe(match, A2_SUB_EX, A2_SUB_SRC)))
checks.append(("A2: a one-word substitution is approximate, same source + 3 unrelated sentences",
               kind_of(A2_SUB_EX, A2_SUB_SRC + " " + PAD) == "approximate",
               safe(match, A2_SUB_EX, A2_SUB_SRC + " " + PAD)))
checks.append(("approximate detail names the substituted span",
               safe(match, A2_SUB_EX, A2_SUB_SRC) == ("approximate", [("fourth", "third")]),
               safe(match, A2_SUB_EX, A2_SUB_SRC)))
checks.append(("verbatim excerpt is exact", kind_of("approve the budget", A2_SUB_SRC) == "exact",
               kind_of("approve the budget", A2_SUB_SRC)))
checks.append(("a partial word is not an exact match (token boundaries)",
               kind_of("pprove the budget", A2_SUB_SRC) != "exact", kind_of("pprove the budget", A2_SUB_SRC)))
checks.append(("excerpt_in_source is match_excerpt(...)[0] is not None",
               safe(vq.excerpt_in_source, A2_SUB_EX, A2_SUB_SRC) is True
               and safe(vq.excerpt_in_source, "we will not approve the budget this quarter",
                        "Mara: we will approve the budget this quarter.") is False, None))
checks.append(("_full_scan is gone (one matcher, S2)", not hasattr(vq, "_full_scan"), None))

# ---- filler-only differences are quoting, not paraphrase: exact
for ex, src in (("we are um going to approve the budget", A2_SUB_SRC),
                ("we are going to approve the budget", "Mara: we are, uh, going to erm approve the budget."),
                ("so um we ship in march", "Mara: so we ship, hmm, in march.")):
    checks.append(("filler-only difference is exact: %r" % ex, kind_of(ex, src) == "exact",
                   safe(match, ex, src)))

# ---- APPROXIMATE lint status: warns, pinned reason, summary line, --json rows
T = Path(tempfile.mkdtemp())
(T / "src").mkdir()
(T / "src/call.txt").write_text("Mara: we are going to approve the budget in the third quarter.\n"
                                 "Jon: the pilot starts with two teams.\n", encoding="utf-8")
APX = T / "approx.md"
APX.write_text(
    "---\nslug: x\n---\n## Positions\n"
    "- Budget (Fact — \"we are going to approve the budget in the fourth quarter\", src/call.txt, "
    "private-communication, human-authored, 2026-01-01)\n"
    "- Pilot (Fact — \"the pilot starts with two teams\", src/call.txt, "
    "private-communication, human-authored, 2026-01-01)\n", encoding="utf-8")
PINNED = ('excerpt differs from the source: "fourth" vs "third" — quote the source verbatim')
lpa = safe(vq.lint_persona, APX, T)
rows = lpa["results"] if isinstance(lpa, dict) else []
checks += [
    ("APPROXIMATE: one-word substitution row status",
     [r["status"] for r in rows] == ["APPROXIMATE", "VERIFIED"], [r["status"] for r in rows]),
    ("APPROXIMATE: pinned reason", rows and rows[0]["reason"] == PINNED, rows and rows[0]["reason"]),
    ("APPROXIMATE: persona status warn", isinstance(lpa, dict) and lpa["status"] == "warn",
     isinstance(lpa, dict) and lpa["label"]),
    ("APPROXIMATE: summary counts it", isinstance(lpa, dict) and lpa["summary"].get("APPROXIMATE") == 1,
     isinstance(lpa, dict) and lpa["summary"]),
]
ra = subprocess.run([sys.executable, str(HERE / "verify_quotes.py"), str(APX), "--sources-root", str(T),
                     "--lint"], capture_output=True, text=True)
checks += [
    ("APPROXIMATE: --lint exits 0", ra.returncode == 0, ra.returncode),
    ("APPROXIMATE: text report prints 'approximate: 1'", "\napproximate: 1\n" in ra.stdout, ra.stdout),
    ("APPROXIMATE: text report prints the pinned reason", PINNED in ra.stdout, ra.stdout),
]
rj2 = subprocess.run([sys.executable, str(HERE / "verify_quotes.py"), str(APX), "--sources-root", str(T),
                      "--json"], capture_output=True, text=True)
try:
    dj2 = json.loads(rj2.stdout)
except json.JSONDecodeError:
    dj2 = {"results": []}
checks.append(("APPROXIMATE: --json rows carry status and reason",
               any(r["status"] == "APPROXIMATE" and r["reason"] == PINNED for r in dj2["results"]),
               dj2["results"]))
checks.append(("no 'approximate:' line when K = 0",
               "approximate:" not in outj_text.stdout, outj_text.stdout))
# MISPLACED keeps precedence when both apply
MIS = T / "mis.md"
MIS.write_text(
    "## Positions\n- Budget: \"we are going to approve the budget in the fourth quarter\", said twice "
    "(Fact — src/call.txt, private-communication, human-authored, 2026-01-01)\n", encoding="utf-8")
lpm = safe(vq.lint_persona, MIS, T)
checks.append(("MISPLACED keeps precedence over APPROXIMATE",
               isinstance(lpm, dict) and [r["status"] for r in lpm["results"]] == ["MISPLACED"],
               isinstance(lpm, dict) and lpm["results"]))

# ---- A3: lint_persona gives identical rows from two different working directories
A3 = Path(tempfile.mkdtemp())
(A3 / "root").mkdir()
(A3 / "cwd1").mkdir()
(A3 / "cwd2").mkdir()
(A3 / "cwd2/notes.txt").write_text("Mara: we will cut the price by half.\n", encoding="utf-8")
(A3 / "root/other.txt").write_text("Mara: the pilot starts in may.\n", encoding="utf-8")
A3P = A3 / "p.md"
A3P.write_text("## Positions\n"
               "- (Fact — \"we will cut the price by half\", notes.txt, private-communication, "
               "human-authored, 2026-01-01)\n"
               "- (Fact — \"the pilot starts in may\", other.txt, private-communication, "
               "human-authored, 2026-01-01)\n", encoding="utf-8")
rows_by_cwd = []
old_cwd = os.getcwd()
for c in ("cwd1", "cwd2"):
    os.chdir(str(A3 / c))
    try:
        res = safe(vq.lint_persona, A3P, A3 / "root")
        rows_by_cwd.append(res["results"] if isinstance(res, dict) else res)
    finally:
        os.chdir(old_cwd)
checks.append(("A3: lint_persona rows identical from two working directories",
               rows_by_cwd[0] == rows_by_cwd[1], rows_by_cwd))
checks.append(("A3: a relative ref found only in the CWD is UNVERIFIABLE with the sources_root reason",
               isinstance(rows_by_cwd[1], list) and rows_by_cwd[1][0]["status"] == "UNVERIFIABLE"
               and rows_by_cwd[1][0]["reason"].startswith("source file not found under sources_root ("),
               rows_by_cwd[1]))
checks.append(("A3: the unresolved count includes the sources_root reason",
               safe(lambda: vq.lint_persona(A3P, A3 / "root")["counts"]["unresolved"]) == 1,
               safe(lambda: vq.lint_persona(A3P, A3 / "root")["counts"])))

# ---- A10: --migrate-ref rewrites only whole ref fields / path components inside Fact tags
MR = Path(tempfile.mkdtemp())
MRP = MR / "p.md"
MR_BODY = ("## Positions\n"
           "- Ships (Fact — \"see call.txt for it\", call.txt, private-communication, human-authored, "
           "2026-01-01)\n"
           "- Other (Fact — \"y\", 2026-08-01-call.txt, private-communication, human-authored, 2026-01-01)\n"
           "- Nested (Fact — \"z\", `notes/call.txt`, private-communication, human-authored, 2026-01-01)\n"
           "- Prose mentions call.txt but has no tag.\n")
MRP.write_text(MR_BODY, encoding="utf-8")
rm = subprocess.run([sys.executable, str(HERE / "verify_quotes.py"), str(MRP), "--migrate-ref", "call.txt",
                     "sources/call.txt", "--apply"], capture_output=True, text=True)
after = MRP.read_text(encoding="utf-8")
checks += [
    ("A10: --migrate-ref exits 0", rm.returncode == 0, (rm.returncode, rm.stderr)),
    ("A10: the whole ref field is rewritten",
     '"see call.txt for it", sources/call.txt, private' in after, after),
    ("A10: a whole path component is rewritten", "`notes/sources/call.txt`" in after, after),
    ("A10: a ref that only contains the text is untouched", "2026-08-01-call.txt," in after, after),
    ("A10: excerpt text is untouched", '"see call.txt for it"' in after, after),
    ("A10: prose is untouched", "- Prose mentions call.txt but" in after, after),
    ("A10: reports 2 references", "2 reference(s)" in rm.stdout, rm.stdout),
]
rmiss = subprocess.run([sys.executable, str(HERE / "verify_quotes.py"), str(MR / "nope.md"), "--migrate-ref",
                        "a.txt", "b.txt"], capture_output=True, text=True)
checks.append(("A10: a missing persona is exit 1, not a traceback",
               rmiss.returncode == 1 and "Traceback" not in rmiss.stderr, (rmiss.returncode, rmiss.stderr)))
MRL = MR / "latin.md"
MRL.write_bytes("## Positions\n- Café (Fact — \"y\", call.txt, private-communication, human-authored, "
                "2026-01-01)\n".replace("—", "-").encode("latin-1"))
rml = subprocess.run([sys.executable, str(HERE / "verify_quotes.py"), str(MRL), "--migrate-ref", "call.txt",
                      "s/call.txt"], capture_output=True, text=True)
checks.append(("A10: a latin-1 persona is read leniently",
               rml.returncode == 0 and "Traceback" not in rml.stderr, (rml.returncode, rml.stderr[-300:])))

# ---- A11: --fix-tags on a latin-1 persona proposes the rewrite at the right offsets
FT = Path(tempfile.mkdtemp())
(FT / "s.txt").write_text("Mara: the caf\u00e9 estimate does not hold at all.\n", encoding="utf-8")
FTP = FT / "p.md"
FTP.write_bytes(("## Positions\n"
                 "- Café© résumé note é©é© here.\n"
                 "- Estimate: \"the caf\u00e9 estimate does not hold\", he said "
                 "(Fact - s.txt, private-communication, human-authored, 2026-01-01)\n").encode("latin-1"))
rf = subprocess.run([sys.executable, str(HERE / "verify_quotes.py"), str(FTP), "--sources-root", str(FT),
                     "--fix-tags"], capture_output=True, text=True)
checks += [
    ("A11: --fix-tags on latin-1 proposes one rewrite", rf.stdout.count("+++ proposed") == 1, rf.stdout),
    ("A11: the proposal is the right item, decoded as the offsets were",
     "--- tag #1 as written\nEstimate: \"the caf\u00e9 estimate does not hold\", he said (Fact - s.txt"
     in rf.stdout,
     rf.stdout),
    ("A11: the excerpt moves inside the tag",
     "Estimate, he said (Fact — \"the caf\u00e9 estimate does not hold\", s.txt" in rf.stdout, rf.stdout),
]

# ================================================================ 0.3.1 fix round 1
# 1. A2: a copy of the substituted word in neighbouring text cannot steal the alignment
for pad in (" The fourth floor is closed.", " Fourth.",
            " The fourth floor is closed. Parking in the fourth lot."):
    checks.append(("A2 r1: pad containing the substituted word keeps approximate: %r" % pad,
                   kind_of(A2_SUB_EX, A2_SUB_SRC + pad) == "approximate",
                   safe(match, A2_SUB_EX, A2_SUB_SRC + pad)))
    checks.append(("A2 r1: same pad before the passage keeps approximate: %r" % pad,
                   kind_of(A2_SUB_EX, pad + " " + A2_SUB_SRC) == "approximate",
                   safe(match, A2_SUB_EX, pad + " " + A2_SUB_SRC)))
for k in range(0, 7):
    src = "we " + "um " * k + "will surely approve the whole budget for this year"
    checks.append(("A2 r1: %d fillers before the anchor keep approximate" % k,
                   kind_of("we will surely approve the whole budget for this quarter", src) == "approximate",
                   safe(match, "we will surely approve the whole budget for this quarter", src)))

# 3. rule 3: prefix or suffix either way, and any digit, refuse the substitution
R3 = [("we cannot sign the contract with them", "we can sign the contract with them"),
      ("we can sign the contract with them", "we cannot sign the contract with them"),
      ("the vendor is ready for the migration next week",
       "the vendor isnt ready for the migration next week"),
      ("the deal is worth 30 million euros over the next three years for us",
       "the deal is worth 3 million euros over the next three years for us"),
      ("the deal is worth 3 million euros over the next three years for us",
       "the deal is worth 30 million euros over the next three years for us"),
      ("the board approved the vendor proposal at the next meeting in march",
       "the board approve the vendor proposal at the next meeting in march"),
      ("we will migrate the whole platform to the cloud by the end of 2026",
       "we will migrate the whole platform to the cloud by the end of 2025"),
      ("we expect the cost to rise by 15 percent next year in the region",
       "we expect the cost to rise by 10 percent next year in the region")]
for ex, src in R3:
    checks.append(("rule 3 r1: %r vs %r is None" % (ex[:40], src[:40]), kind_of(ex, src) is None,
                   safe(match, ex, src)))

# 4. A13: a bracket of more than 4 words is not editorial
checks.append(("A13: a 5-word bracket stays in the excerpt and must match",
               kind_of("[the board will reject the vendor] this quarter",
                       "we will approve the budget this quarter") is None,
               safe(match, "[the board will reject the vendor] this quarter",
                    "we will approve the budget this quarter")))
checks.append(("A13: a short editorial bracket is still dropped",
               kind_of("[the client] will approve the budget",
                       "we will approve the budget this quarter") == "exact",
               safe(match, "[the client] will approve the budget",
                    "we will approve the budget this quarter")))
checks.append(("A13: bracketed timestamp in the source is still dropped",
               kind_of("we will approve the budget", "we will approve [00:12:03] the budget") == "exact",
               None))

# 5. "mm" is a unit, not a filler
checks.append(("mm is not a filler: '5 mm' is not an exact match for '5 cm'",
               kind_of("the bolt is 5 mm", "the bolt is 5 cm long") != "exact",
               safe(match, "the bolt is 5 mm", "the bolt is 5 cm long")))

# 9. invisible characters and casefold
for ex, src in (("important decision", "impor\u00adtant decision"),
                ("important decision", "impor\u200btant decision"),
                ("important decision", "impor\u2060tant decision"),
                ("important decision", "\ufeffimportant decision"),
                ("the strasse is closed", "the Stra\u00dfe is closed")):
    checks.append(("normalize r1: %r verifies exactly" % src, kind_of(ex, src) == "exact",
                   safe(match, ex, src)))

# 8. MISPLACED + approximate keeps the substitution visible
lpm2 = safe(vq.lint_persona, MIS, T)
checks.append(("MISPLACED+approximate: reason appends the difference",
               isinstance(lpm2, dict) and lpm2["results"][0]["reason"].endswith(
                   ' (and it differs from the source: "fourth" vs "third")'),
               isinstance(lpm2, dict) and lpm2["results"][0]["reason"]))

# 6. migrate_ref: the excerpt field's lead-in is not a ref field
MR2 = Path(tempfile.mkdtemp()) / "p.md"
MR2.write_text("## Positions\n- A (Fact — per call.txt: \"x\", call.txt, private-communication, "
               "human-authored, 2026-01-01)\n", encoding="utf-8")
subprocess.run([sys.executable, str(HERE / "verify_quotes.py"), str(MR2), "--migrate-ref", "call.txt",
                "s/call.txt", "--apply"], capture_output=True, text=True)
a2 = MR2.read_text(encoding="utf-8")
checks.append(("A10 r1: the excerpt field's lead-in is untouched, the ref field is rewritten",
               'per call.txt: "x", s/call.txt,' in a2, a2))

# 2. CLI without --sources-root derives the root from the persona's context, never "."
CL = Path(tempfile.mkdtemp())
(CL / "store/ctx/personas").mkdir(parents=True)
(CL / "store/ctx/src").mkdir()
(CL / "store/ctx/context.md").write_text("---\nschema: 0.2\nsources_root: src\n---\n", encoding="utf-8")
(CL / "store/ctx/src/a.txt").write_text("Mara: the pilot starts in may.\n", encoding="utf-8")
(CL / "cwd").mkdir()
(CL / "cwd/b.txt").write_text("Mara: we will cut the price by half.\n", encoding="utf-8")
CLP = CL / "store/ctx/personas/p.md"
CLP.write_text("## Positions\n- (Fact — \"the pilot starts in may\", a.txt, private-communication, "
               "human-authored, 2026-01-01)\n- (Fact — \"we will cut the price by half\", b.txt, "
               "private-communication, human-authored, 2026-01-01)\n", encoding="utf-8")
LOOSE = CL / "loose"
LOOSE.mkdir()
(LOOSE / "c.txt").write_text("Mara: we meet on friday.\n", encoding="utf-8")
(LOOSE / "p.md").write_text("## Positions\n- (Fact — \"we meet on friday\", c.txt, private-communication, "
                            "human-authored, 2026-01-01)\n", encoding="utf-8")
import contextlib  # noqa: E402
import io  # noqa: E402


def main_rows(persona, cwd):
    old = os.getcwd()
    os.chdir(str(cwd))
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            rc = vq.main([str(persona), "--json"])
    finally:
        os.chdir(old)
    return rc, [(r["status"], r["reason"]) for r in json.loads(buf.getvalue())["results"]]


cli1 = safe(main_rows, CLP, CL)
cli2 = safe(main_rows, CLP, CL / "cwd")
checks += [
    ("CLI r1: rows identical from two working directories", cli1 == cli2, (cli1, cli2)),
    ("CLI r1: the context's sources_root is used when --sources-root is omitted",
     isinstance(cli1, tuple) and cli1[1][0][0] == "VERIFIED", cli1),
    ("CLI r1: a file only in the CWD does not verify",
     isinstance(cli2, tuple) and cli2[1][1][0] == "UNVERIFIABLE", cli2),
    ("CLI r1: a persona outside a context resolves against its own folder",
     safe(main_rows, LOOSE / "p.md", CL / "cwd") == (0, [("VERIFIED", "")]),
     safe(main_rows, LOOSE / "p.md", CL / "cwd")),
    ("CLI: a persona in a store names its sources_root relative to the store",
     isinstance(cli2, tuple) and cli2[1][1][1] == "source file not found under sources_root ("
     + str(Path("ctx") / "src") + ") — set sources_root: in context.md or use an absolute path", cli2),
]

# ================================================================ 0.3.1 fix round 2
# a substitution where either token is shorter than 4 characters is refused
for ex, src in (("we will not approve the budget this quarter",
                 "we will now approve the budget this quarter"),
                ("there is no risk in the migration plan for the team",
                 "there is a risk in the migration plan for the team"),
                ("the plan is good for the whole team this year",
                 "the plan as good for the whole team this year"),
                ("we won approve the budget", "we will approve the budget")):
    checks.append(("rule 3 r2: short-token substitution %r vs %r is None" % (ex[:30], src[:30]),
                   kind_of(ex, src) is None, safe(match, ex, src)))
checks.append(("rule 3 r2: a >= 4-char drift (fourth/third) is still approximate",
               kind_of(A2_SUB_EX, A2_SUB_SRC) == "approximate", safe(match, A2_SUB_EX, A2_SUB_SRC)))

# ================================================================ 0.3.1 fix round 3
# 1 + 2. token boundaries: an apostrophe or hyphen inside a word joins it
for ex, src, want in (
        ("the legal team told me we can", "Mara: the legal team told me we can't sign it.", None),
        ("binding agreement with the vendor for three years",
         "Mara: this is a non-binding agreement with the vendor for three years.", None),
        ("cloud this year", "Mara: the team is anti-cloud this year.", None),
        ("we can't sign it", "Mara: we can\u2019t sign it.", "exact"),
        ("a non-binding agreement", "Mara: a non-binding agreement.", "exact"),
        ("perche' e' vero", "Mara: perch\u00e9 \u00e8 vero.", "exact"),
        ("revenue growth was -5 percent in the northern region",
         "Mara: revenue growth was 5 percent in the northern region.", None),
        ("margin moved +3 points in the quarter", "Mara: margin moved -3 points in the quarter.", None),
        ("revenue growth was -5 percent", "Mara: revenue growth was -5 percent.", "exact")):
    checks.append(("normalize r3: %r against %r is %s" % (ex, src[:40], want), kind_of(ex, src) == want,
                   safe(match, ex, src)))
checks.append(("normalize r3: a compound still matches its spaced spelling (three-year / three year)",
               kind_of("a three year term", "Mara: a three-year term.") == "exact"
               and kind_of("a three-year term", "Mara: a three year term.") == "exact", None))
checks.append(("normalize r3: a match may not end inside a compound",
               kind_of("a three", "Mara: a three-year term.") is None,
               safe(match, "a three", "Mara: a three-year term.")))
checks.append(("normalize r3: a sign before a digit is kept", safe(vq.normalize, "was -5, +3 or 5") ==
               "was -5 +3 or 5", safe(vq.normalize, "was -5, +3 or 5")))

# 3. a short bracket is a placeholder for 0-3 source tokens at its position
for ex, src, want in (
        ("we told [the client] the price is final", "Mara: we told them the price is final.", "approximate"),
        ("we told [the client] the price is final",
         "Mara: we told the whole board the price is final.", None),
        ("we told [the client] the price is final",
         "Mara: we told the board and the team the price is final.", None),
        ("she said [the vendor] will ship", "Mara: they will ship.", None),
        ("[the client] will approve the budget", "we will approve the budget this quarter", "exact"),
        ("the board will [not] approve the vendor budget this quarter",
         "Mara: the board will approve the vendor budget this quarter.", "exact"),
        ("we told [the client] the price is final on the invoice for june",
         "Mara: we told them the price is fixed on the invoice for june.", "approximate"),
        ("[the board will reject the vendor] this quarter", "we will approve the budget this quarter", None)):
    checks.append(("bracket r3: %r against %r is %s" % (ex, src[:45], want), kind_of(ex, src) == want,
                   safe(match, ex, src)))

# ================================================================ 0.3.1 fix round 4
# a bracket that absorbs no source word keeps the match exact; one that absorbs words caps
# it at approximate and the reason names them; an absorbed word shorter than 4 characters
# or holding a digit is refused (no match at that expansion)
for ex, src in (("we will [somehow] approve the budget this quarter",
                 "Mara: we will not approve the budget this quarter."),
                ("revenue grew [a lot] percent this year", "Mara: revenue grew 30 percent this year."),
                ("we are [maybe] to approve this", "Mara: we are definitely not going to approve this."),
                ("we told [the client] the price is final",
                 "Mara: we told the whole board the price is final.")):
    checks.append(("bracket r4: %r against %r is None" % (ex, src[:45]), kind_of(ex, src) is None,
                   safe(match, ex, src)))
R4_THEM = safe(match, "we told [the client] the price is final", "Mara: we told them the price is final.")
checks.append(("bracket r4: a bracket absorbing 'them' is approximate, detail names it",
               R4_THEM == ("approximate", [("[the client]", "them", "placeholder")]), R4_THEM))
checks.append(("bracket r4: the reason names what the bracket stood for",
               isinstance(R4_THEM, tuple) and safe(vq.approximate_reason, R4_THEM[1]) ==
               'excerpt differs from the source: "[the client]" stands for "them"'
               ' — quote the source verbatim',
               isinstance(R4_THEM, tuple) and safe(vq.approximate_reason, R4_THEM[1])))
R4_MIX = safe(match, "we told [the client] the price is final on the invoice for june",
              "Mara: we told them the price is fixed on the invoice for june.")
checks.append(("bracket r4: substitution spans and the bracket are joined with ' / '",
               isinstance(R4_MIX, tuple) and safe(vq.approximate_reason, R4_MIX[1]) ==
               'excerpt differs from the source: "final" vs "fixed" / "[the client]" stands for "them"'
               ' — quote the source verbatim',
               isinstance(R4_MIX, tuple) and safe(vq.approximate_reason, R4_MIX[1])))
R4_TWO = safe(match, "we told [the client] that [the price] stays final",
              "Mara: we told them that pricing stays final.")
checks.append(("bracket r4: two absorbing brackets are both named",
               isinstance(R4_TWO, tuple) and R4_TWO[0] == "approximate"
               and safe(vq.approximate_reason, R4_TWO[1])
               == 'excerpt differs from the source: "[the client]" stands for "them" / "[the price]"'
               ' stands for "pricing" — quote the source verbatim', R4_TWO))
for ex, src in (("[the client] will approve the budget", "we will approve the budget this quarter"),
                ("the board will [not] approve the vendor budget this quarter",
                 "Mara: the board will approve the vendor budget this quarter."),
                ("we told [the client] the price is final", "Mara: we told the price is final.")):
    checks.append(("bracket r4: a bracket absorbing nothing stays exact: %r" % ex,
                   safe(match, ex, src) == ("exact", []), safe(match, ex, src)))
# lint row: APPROXIMATE with the bracket reason; MISPLACED appends the same difference
(T / "src/told.txt").write_text("Mara: we told them the price is final.\n", encoding="utf-8")
BRP = T / "bracket.md"
BRP.write_text("## Positions\n- Price (Fact — \"we told [the client] the price is final\", src/told.txt, "
               "private-communication, human-authored, 2026-01-01)\n", encoding="utf-8")
lpb = safe(vq.lint_persona, BRP, T)
checks.append(("bracket r4: lint row is APPROXIMATE with the bracket reason",
               isinstance(lpb, dict) and [(r["status"], r["reason"]) for r in lpb["results"]] ==
               [("APPROXIMATE", 'excerpt differs from the source: "[the client]" stands for "them"'
                 ' — quote the source verbatim')], isinstance(lpb, dict) and lpb["results"]))
BRM = T / "bracket-mis.md"
BRM.write_text("## Positions\n- Price: \"we told [the client] the price is final\", twice "
               "(Fact — src/told.txt, private-communication, human-authored, 2026-01-01)\n", encoding="utf-8")
lpbm = safe(vq.lint_persona, BRM, T)
checks.append(("bracket r4: MISPLACED appends what the bracket stood for",
               isinstance(lpbm, dict) and lpbm["results"][0]["status"] == "MISPLACED"
               and lpbm["results"][0]["reason"].endswith(
                   ' (and it differs from the source: "[the client]" stands for "them")'),
               isinstance(lpbm, dict) and lpbm["results"]))

# 5. line length
checks.append(("verify_quotes.py lines 52 and 171 fit 100 chars",
               all(len(ln) <= 100 for ln in (HERE / "verify_quotes.py").read_text(encoding="utf-8")
                   .splitlines()[:200]), None))

fails = [c for c in checks if not c[1]]
for name, ok, got in checks:
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  -> got {got!r}"))
print(f"\n{len(checks) - len(fails)}/{len(checks)} passed")
sys.exit(1 if fails else 0)
