#!/usr/bin/env python3
"""Tests for coverage.py, and for the unverifiable split and --migrate-ref of verify_quotes.py.

The case that matters: two personas that both pass the excerpt linter, one built on several
independent sources with every judgment section populated, one on a single thin source with
sections left blank. They must not look the same.
"""
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True  # G5: a suite run on its own leaves no __pycache__

HERE = Path(__file__).parent
checks = []


def run(script, *a, cwd=None):
    return subprocess.run([sys.executable, str(HERE / script), *[str(x) for x in a]],
                          capture_output=True, text=True, cwd=str(cwd or HERE))


d = Path(tempfile.mkdtemp())
src = d / "sources"
src.mkdir()
(src / "2026-06-02-kickoff.txt").write_text(
    "**Dana Whitfield:** " + "the rollback rehearsal is the whole question. " * 120 + "\n"
    "**Marco Ferri:** " + "I can move the window if procurement agrees. " * 120 + "\n"
    "**Ines Okafor:** ok.\n", encoding="utf-8")
(src / "2026-07-14-steering.txt").write_text(
    "**Dana Whitfield:** " + "we are not signing without a rehearsal. " * 120 + "\n"
    "**Marco Ferri:** " + "the number does not change, the shape does. " * 80 + "\n"
    "**Ines Okafor:** agreed.\n", encoding="utf-8")
(src / "2026-08-30-review.txt").write_text(
    "**Dana Whitfield:** " + "procurement closes on the twentieth. " * 120 + "\n"
    "**Ines Okafor:** fine.\n", encoding="utf-8")
(src / "2026-08-30-thread.md").write_text(
    "Subject: budget\nFrom: someone\nTo: someone else\n\nThe point is this: Ines Okafor has not replied.\n",
    encoding="utf-8")

# ---- BEFORE: measuring the sources
r = run("coverage.py", "--sources", src, "--people", "Ines Okafor", "--json")
data = json.loads(r.stdout)
by = {p["label"]: p for p in data["people"]}
checks.append(("only the requested person is reported", list(by) == ["Ines Okafor"], list(by)))
checks.append(("a person who is present but barely speaks is not 'solid'",
               by["Ines Okafor"]["verdict"] in ("thin", "absent"), by["Ines Okafor"]))
r = run("coverage.py", "--sources", src, "--json")
allp = {p["label"]: p for p in json.loads(r.stdout)["people"]}
checks.append(("the person who speaks most ranks first",
               max(allp.values(), key=lambda p: p["spoken"])["label"] == "Dana Whitfield", list(allp)))
checks.append(("volume is counted across sources",
               allp["Dana Whitfield"]["spoken"] > 10000, allp["Dana Whitfield"]))
checks.append(("independent sources are counted",
               len(allp["Dana Whitfield"]["sources"]) == 3, allp["Dana Whitfield"]))
checks.append(("the time span is reported", allp["Dana Whitfield"]["span_days"] > 80, allp["Dana Whitfield"]))
non_transcripts = json.loads(r.stdout)["non_transcripts"]
checks.append(("a mail thread is not read as a transcript",
               "2026-08-30-thread.md" in non_transcripts, non_transcripts))
checks.append(("mail headers never become speakers",
               not any(lb.lower() in ("subject", "from", "to") for lb in allp), list(allp)))
r = run("coverage.py", "--sources", src)
checks.append(("being on the invitation is not speaking, and it is said",
               "not speaking" in r.stdout, r.stdout))

# ---- AFTER: the persona's own coverage
strong = d / "strong.md"
strong.write_text("""---
slug: dana
role: COO
cares_about: rollback rehearsals
---

## Mandate and incentives
- a (Fact — "the rollback rehearsal is the whole question", \
sources/2026-06-02-kickoff.txt, private-communication, machine-transcribed, 2026-06-02)

## Judgment criteria
- b (Fact — "we are not signing without a rehearsal", \
sources/2026-07-14-steering.txt, private-communication, machine-transcribed, 2026-07-14)

## Recurring objections
- c (Fact — "procurement closes on the twentieth", \
sources/2026-08-30-review.txt, private-communication, machine-transcribed, 2026-08-30)

## Red lines
- d (Fact — "we are not signing without a rehearsal", \
sources/2026-07-14-steering.txt, private-communication, machine-transcribed, 2026-07-14)

## Language and dissent style
- e (Fact — "the rollback rehearsal is the whole question", \
sources/2026-06-02-kickoff.txt, private-communication, machine-transcribed, 2026-06-02)

## Panel dynamics
- f (Fact — "procurement closes on the twentieth", \
sources/2026-08-30-review.txt, private-communication, machine-transcribed, 2026-08-30)
""", encoding="utf-8")

thin = d / "thin.md"
thin.write_text("""---
slug: ines
role: Head of Risk
---

## Mandate and incentives
- a (Fact — "the rollback rehearsal is the whole question", \
sources/2026-06-02-kickoff.txt, private-communication, machine-transcribed, 2026-06-02)

## Judgment criteria
- b (Fact — "the rollback rehearsal is the whole question", \
sources/2026-06-02-kickoff.txt, private-communication, machine-transcribed, 2026-06-02)

## Recurring objections

## Red lines
- no evidence as of 2026-09-17

## Language and dissent style

## Panel dynamics
""", encoding="utf-8")

a = json.loads(run("coverage.py", strong, "--json", cwd=d).stdout)
b = json.loads(run("coverage.py", thin, "--json", cwd=d).stdout)
checks.append(("a well-founded persona reads solid", a["level"] == "solid", a["level"]))
checks.append(("a thin one reads thin", b["level"] == "thin", b["level"]))
checks.append(("they do not produce the same index line",
               a["summary"] != b["summary"], (a["summary"], b["summary"])))
checks.append(("populated judgment sections are counted",
               len(a["populated_sections"]) == 6, a["populated_sections"]))
checks.append(("a declared empty section is counted as declared",
               b["empty_declared"] == ["Red lines"], b["empty_declared"]))
checks.append(("a silently blank section is named",
               set(b["empty_silent"]) == {"Recurring objections", "Language and dissent style",
                                          "Panel dynamics"},
               b["empty_silent"]))
checks.append(("a missing cares_about is a failed check",
               any(c["check"].startswith("cares_about") and not c["ok"] for c in b["checks"]),
               b["checks"]))
checks.append(("one source carrying everything is a failed check",
               any(c["check"].startswith("no single source") and not c["ok"] for c in b["checks"]),
               b["checks"]))
r = run("coverage.py", thin, cwd=d)
checks.append(("coverage never blocks, and says so",
               "never blocks" in r.stdout and r.returncode == 0, r.stdout))
checks.append(("it warns against filling empty sections by deduction",
               "roleplay this skill forbids" in r.stdout, r.stdout))

# ---- unverifiable debt: old and unfixable vs new and fixable
deb = d / "debt.md"
deb.write_text("""---
slug: x
role: y
---
## Red lines
- a (Fact — "whatever", https://crm.example/record/9, private-communication, human-authored, 2026-01-02)
- b (Fact — "whatever", sources/never-saved.txt, private-communication, human-authored, 2026-01-02)
""", encoding="utf-8")
out = run("verify_quotes.py", deb, "--sources-root", d, "--json", cwd=d).stdout
res = json.loads(out)
kinds = sorted(r.get("kind") for r in res["results"])
checks.append(("a remote reference is unverifiable by construction", "by-construction" in kinds, kinds))
checks.append(("a path that does not resolve is fixable", "fixable" in kinds, kinds))
checks.append(("the two are counted separately",
               res["summary"]["unverifiable_by_construction"] == 1
               and res["summary"]["unverifiable_fixable"] == 1, res["summary"]))

# ---- migrate-ref: the way back out of the debt
(d / "sources/2026-01-02-saved.txt").write_text("someone: whatever was said here.\n", encoding="utf-8")
before = deb.read_text()
r = run("verify_quotes.py", deb, "--migrate-ref", "sources/never-saved.txt",
        "sources/2026-01-02-saved.txt", cwd=d)
checks.append(("--migrate-ref proposes without writing",
               deb.read_text() == before and "@@" in r.stdout, r.stdout[:200]))
r = run("verify_quotes.py", deb, "--migrate-ref", "sources/never-saved.txt",
        "sources/2026-01-02-saved.txt", "--apply", cwd=d)
checks.append(("--apply rewrites the reference",
               "sources/2026-01-02-saved.txt" in deb.read_text(), deb.read_text()))
res2 = json.loads(run("verify_quotes.py", deb, "--sources-root", d, "--json", cwd=d).stdout)
checks.append(("the migrated reference now resolves and is judged",
               any(r["status"] in ("VERIFIED", "NOT FOUND") for r in res2["results"]), res2["results"]))
r = run("verify_quotes.py", deb, "--migrate-ref", "not/there.txt", "x.txt", cwd=d)
checks.append(("migrating a reference that is not there is refused", r.returncode == 1, r.returncode))

# ---- Step 6 / FR-4.8: frontmatter outside the accepted subset is a failed check here,
# not just a warning on stderr (that is reindex.py's job) — a persona whose header the
# tools cannot fully read should not read as founded on the strength of everything else.
bad_fm = d / "bad-frontmatter.md"
bad_fm.write_text("""---
slug: y
aliases:
- one
- two
---
## Red lines
- no evidence as of 2026-01-01
""", encoding="utf-8")
res_bad = json.loads(run("coverage.py", bad_fm, "--json", cwd=d).stdout)
fm_check = next((c for c in res_bad["checks"] if c["check"] == "frontmatter within subset"), None)
checks.append(("a block-list frontmatter fails the 'frontmatter within subset' check",
               fm_check is not None and fm_check["ok"] is False, fm_check))
checks.append(("the failure names the line and the reason as 'frontmatter: <line>: <reason>'",
               fm_check is not None and re.match(r"^frontmatter: \d+: \S", fm_check["evidence"]) is not None,
               fm_check))
res_ok = json.loads(run("coverage.py", strong, "--json", cwd=d).stdout)
fm_check_ok = next((c for c in res_ok["checks"] if c["check"] == "frontmatter within subset"), None)
checks.append(("a well-formed frontmatter passes the same check",
               fm_check_ok is not None and fm_check_ok["ok"] is True, fm_check_ok))

# ---- the header is read once, through read_frontmatter, so a quoted scalar and an inline
# list are the values the rest of the toolchain sees. Re-regexing the block here made
# `slug: "quoted"` the slug `"quoted"` — quotes included — which matched no AUDIT row, and
# an inline-list cares_about counted as present only by accident of the regex.
TAG = ('(Fact — "the rollback rehearsal is the whole question", '
       'sources/2026-06-02-kickoff.txt, private-communication, machine-transcribed, 2026-06-02)')
quoted = d / "quoted.md"
quoted.write_text('---\nslug: "quoted"\nrole: COO\n'
                  'cares_about: [rollback rehearsals, procurement]\n---\n\n'
                  '## Mandate and incentives\n- a ' + TAG + '\n', encoding="utf-8")
audit_q = d / "AUDIT-quoted.md"
audit_q.write_text("2026-06-02 | quoted | speaker attribution checked against the roster\n",
                   encoding="utf-8")
res_q = json.loads(run("coverage.py", quoted, "--audit", audit_q, "--json", cwd=d).stdout)
by_check = {c["check"]: c for c in res_q["checks"]}
attribution = by_check.get("attribution recorded in AUDIT for multi-voice sources")
checks.append(("a quoted slug still finds its AUDIT row",
               attribution is not None and attribution["evidence"] == "recorded", attribution))
cares_check = by_check.get("cares_about populated")
checks.append(("an inline-list cares_about counts as populated",
               cares_check is not None and cares_check["ok"] is True
               and cares_check["evidence"] == "present", cares_check))

# ---- 0.3.1 ---------------------------------------------------------------------------
import os  # noqa: E402

sys.path.insert(0, str(HERE))
import coverage as cov_mod  # noqa: E402

# A4: the sources_root is the persona's context's, never the working directory
store = d / "store31"
ctx = store / "ops"
(ctx / "material").mkdir(parents=True)
(ctx / "personas").mkdir()
(ctx / "context.md").write_text("---\nsources_root: material\n---\n", encoding="utf-8")
(ctx / "material" / "a.txt").write_text("alpha beta\n", encoding="utf-8")
pp = ctx / "personas" / "yara.md"
pp.write_text("---\nslug: yara\n---\n## Mandate and incentives\n"
              '- a (Fact — "alpha", a.txt, private-communication, human-authored, 2026-01-01)\n'
              '- b (Fact — "beta", as quoted in a.txt, private-communication, human-authored, '
              "2026-01-02)\n", encoding="utf-8")
other = d / "elsewhere"
(other / "material").mkdir(parents=True)
(other / "a.txt").write_text("alpha beta\n", encoding="utf-8")
seen = []
here = os.getcwd()
for cwd in (ctx, other, ctx / "material"):
    os.chdir(str(cwd))
    try:
        res = cov_mod.assess(pp)
        seen.append((res["sources"], res["summary"]))
    finally:
        os.chdir(here)
checks.append(("A4: assess(persona) gives the same result from three working directories",
               len(set(repr(s) for s in seen)) == 1, seen))
checks.append(("A4: 'as quoted in a.txt' and 'a.txt' are one source under the context's "
               "sources_root", seen and seen[0][0] == ["a.txt"], seen))
cli = [json.loads(run("coverage.py", pp, "--json", cwd=c).stdout)["sources"]
       for c in (ctx, other)]
checks.append(("A4: the CLI gives the same sources from two working directories",
               cli[0] == cli[1] == ["a.txt"], cli))
explicit = cov_mod.assess(pp, None, ctx / "material")
checks.append(("A4: an explicit sources_root is used as given",
               explicit["sources"] == ["a.txt"], explicit["sources"]))

# D2: the time span comes from the Fact tags' dates only
one = d / "one-date.md"
one.write_text("---\nslug: x\nupdated: 2026-09-20\n---\n"
               "## Mandate and incentives <!-- last evidence: 2026-01-01 | decays fast -->\n"
               '- a (Fact — "hello", src.txt, private-communication, human-authored, 2026-01-01)\n'
               "- no evidence as of 2026-06-30\n", encoding="utf-8")
res = cov_mod.assess(one)
span = next(c for c in res["checks"] if c["check"] == "time span covered")
checks.append(("D2: frontmatter, heading-note and prose dates do not enter the span",
               res["span_days"] == 0 and span["ok"] is False
               and span["evidence"].startswith("0 days"), (res["span_days"], span)))
two = d / "two-dates.md"
two.write_text("---\nslug: x\n---\n## Mandate and incentives\n"
               '- a (Fact — "hello", src.txt, private-communication, human-authored, 2026-01-01)\n'
               '- b (Fact — "world", src.txt, private-communication, human-authored, 2026-03-02)\n'
               '- c (Fact — "again", src.txt, private-communication, human-authored, 2026-13-45)\n',
               encoding="utf-8")
res = cov_mod.assess(two)
checks.append(("D2: two Fact dates give their span; an unparseable date is ignored",
               res["span_days"] == 60, res["span_days"]))

# D3: an AUDIT row is the persona's only when the slug stands alone
audit = d / "AUDIT-d3.md"
audit.write_text("- 2026-01-01 cto-dana: call.txt, speaker attribution confirmed\n"
                 "- 2026-01-02 dana-lee: call.txt, speaker attribution confirmed\n",
                 encoding="utf-8")
dana = d / "dana.md"
dana.write_text("---\nslug: dana\n---\n", encoding="utf-8")
att = next(c for c in cov_mod.assess(dana, audit)["checks"] if "attribution" in c["check"])
checks.append(("D3: a `cto-dana` or `dana-lee` row is not dana's",
               att["evidence"] == "no AUDIT row names dana", att))
audit.write_text("- 2026-01-03 dana: call.txt, speaker attribution confirmed\n",
                 encoding="utf-8")
att = next(c for c in cov_mod.assess(dana, audit)["checks"] if "attribution" in c["check"])
checks.append(("D3: dana's own row still counts", att["evidence"] == "recorded", att))

# S11: no files under --sources is exit 1 with the message, no Refused scaffolding
empty = d / "empty-sources"
empty.mkdir()
r = run("coverage.py", "--sources", empty)
checks.append(("S11: --sources on a folder with no matching files exits 1 and says why",
               r.returncode == 1 and "no sources with extension" in r.stderr,
               (r.returncode, r.stderr)))
checks.append(("S11: the Refused/die scaffolding is gone",
               not hasattr(cov_mod, "Refused") and not hasattr(cov_mod, "die"), None))
checks.append(("S11: scan_sources returns None when there are no files",
               cov_mod.scan_sources(empty, [], (".txt",)) is None, None))

fails = [c for c in checks if not c[1]]
for n, ok, got in checks:
    print(("ok   " if ok else "FAIL ") + n + ("" if ok else f" -> {str(got)[:300]}"))
print(f"\n{len(checks)-len(fails)}/{len(checks)} passed")
sys.exit(1 if fails else 0)
