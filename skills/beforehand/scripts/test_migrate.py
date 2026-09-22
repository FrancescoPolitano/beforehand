#!/usr/bin/env python3
"""Tests for migrate.py (FR-7.3): schema versions and the 0.1 -> 0.2 migration.

Every run works on a temporary copy of a fixture store, and the 0.1 fixtures live OUTSIDE
`test_fixtures/store/` on purpose: a fourth context inside the fixture store would be picked
up by every other suite's `reindex`/`doctor` run and would break their "healthy" and
idempotency assertions.

The alias-form empty section in the 0.1 fixture is Italian, which only the synthetic `xx`
test locale recognises (FR-4.4): the migration is run with BEFOREHAND_LOCALE=xx and
BEFOREHAND_LOCALE_DIR pointing at `test_fixtures/locales`, and one check proves that the same
run in English leaves that line alone instead of guessing.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True  # G5: a suite run on its own leaves no __pycache__

HERE = Path(__file__).parent
MIGRATE = HERE / "migrate.py"
ENTRY = HERE / "beforehand.py"
GOLDEN = HERE / "test_fixtures/store/golden"
FIX_01 = HERE / "test_fixtures/store-0.1"
FIX_LOSSY = HERE / "test_fixtures/store-0.1-lossy"
LOCALE_DIR = HERE / "test_fixtures/locales"
TMP = Path(tempfile.mkdtemp())
checks = []

sys.path.insert(0, str(HERE))
from personas_lib import schema_of  # noqa: E402

# The alias form the 0.1 fixture is written in, read from the test locale rather than spelled
# here: FR-4.4's acceptance grep (test_locale.py) requires that no scripts/*.py carries a
# hardcoded non-English token, tests included.
ALIAS = json.loads((LOCALE_DIR / "xx.json").read_text(encoding="utf-8"))["empty_section"][0]


def run(*a, **kw):
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.update(kw.pop("env", None) or {})
    return subprocess.run([sys.executable, *map(str, a)], capture_output=True, text=True, env=env)


def xx(*a, **kw):
    """migrate.py with the synthetic test locale loaded."""
    env = {"BEFOREHAND_LOCALE": "xx", "BEFOREHAND_LOCALE_DIR": str(LOCALE_DIR)}
    env.update(kw.pop("env", None) or {})
    return run(MIGRATE, *a, env=env, **kw)


def copy(src, name):
    dst = TMP / name
    shutil.copytree(src, dst)
    return dst


def state(root):
    """Digest of every file under root: proof that a dry run wrote nothing."""
    return {str(p.relative_to(root)): hashlib.sha1(p.read_bytes()).hexdigest()
            for p in sorted(Path(root).rglob("*")) if p.is_file()}


def read(p):
    return Path(p).read_text(encoding="utf-8")


# ------------------------------------------------------------------ schema_of, both shapes
# The reader `doctor` and `migrate` share (FR-7.3): frontmatter, a snapshot's bare header, a
# frontmatter outside the FR-4.8 subset, and a file that declares nothing.
checks.append(("schema_of reads the frontmatter of a persona",
               schema_of("---\nslug: x\nschema: 0.2\n---\n\n## Red lines\n") == "0.2",
               schema_of("---\nslug: x\nschema: 0.2\n---\n")))
checks.append(("schema_of reads a snapshot header, which has no frontmatter block",
               schema_of("# snapshot\n\ndocument: d.md\nschema: 0.1\n") == "0.1",
               schema_of("# snapshot\n\ndocument: d.md\nschema: 0.1\n")))
checks.append(("schema_of answers through a frontmatter outside the FR-4.8 subset",
               schema_of("---\nslug: x\nschema: 0.1\nextra:\n  - a\n---\n") == "0.1",
               schema_of("---\nslug: x\nschema: 0.1\nextra:\n  - a\n---\n")))
checks.append(("schema_of returns None when nothing declares a version",
               schema_of("---\nslug: x\n---\n\n## Red lines\n") is None,
               schema_of("---\nslug: x\n---\n")))
checks.append(("a `schema:` in the body is not mistaken for the file's version",
               schema_of("---\nslug: x\n---\n\nthe line `schema: 0.1` in prose\n") is None,
               schema_of("---\nslug: x\n---\n\nthe line `schema: 0.1` in prose\n")))

# ------------------------------------------------- split_joined_tags: the negative branches
# The split is unambiguous only when every segment carries exactly one path-like field. The
# two shapes that break that rule are left exactly as written, and `lint` keeps reporting the
# group as joined — a script must not guess which source belongs to which claim.
from migrate import split_joined_tags  # noqa: E402

SAME_SOURCE = ('- Claim (Fact — "one", 2026-06-11-steering.txt, private-communication, '
               'machine-transcribed, 2026-06-11; Fact — "two", same source, '
               'private-communication, machine-transcribed, 2026-06-11)')
TWO_PATHS = ('- Claim (Fact — "one", 2026-06-11-steering.txt, private-communication, '
             'machine-transcribed, 2026-06-11; Fact — "two", 2026-05-06-kickoff.txt, '
             'notes/appendix.md, private-communication, machine-transcribed, 2026-05-06)')
SPLITTABLE = ('- Claim (Fact — "one", 2026-06-11-steering.txt, private-communication, '
              'machine-transcribed, 2026-06-11; Fact — "two", 2026-05-06-kickoff.txt, '
              'private-communication, machine-transcribed, 2026-05-06)')
checks.append(("a segment with no path-like field (same source) is left joined",
               split_joined_tags(SAME_SOURCE) == SAME_SOURCE, split_joined_tags(SAME_SOURCE)))
checks.append(("a segment with two path-like fields is left joined",
               split_joined_tags(TWO_PATHS) == TWO_PATHS, split_joined_tags(TWO_PATHS)))
checks.append(("the control case, one path-like field per segment, does split",
               split_joined_tags(SPLITTABLE).count("(Fact") == 2
               and "; Fact —" not in split_joined_tags(SPLITTABLE),
               split_joined_tags(SPLITTABLE)))

# ------------------------------------------------------------------ dry run writes nothing
store = copy(FIX_01, "dry")
before = state(store)
r = xx("--store", store, "--context", "golden")
checks.append(("dry run exits 0", r.returncode == 0, (r.returncode, r.stderr)))
checks.append(("dry run writes nothing", state(store) == before, r.stdout[:400]))
checks.append(("dry run says nothing was written",
               "nothing written" in r.stdout and "--apply" in r.stdout, r.stdout[-400:]))
for expected in ("golden/context.md", "golden/AUDIT.md", "golden/personas/cfo-astrid.md",
                 "golden/personas/coo-mira.md", "golden/personas/cto-jonas.md",
                 "golden/calibration/pending-brief-q3.md",
                 "golden/calibration/done-2026-07-02-brief-q2.md"):
    checks.append((f"dry run diffs {expected}", expected in r.stdout, r.stdout[:200]))
checks.append(("diff paths are store-relative, not absolute machine paths",
               str(store) not in r.stdout, r.stdout[:200]))
checks.append(("dry run prints a unified diff, not a summary",
               "--- golden/personas/cfo-astrid.md" in r.stdout and "+schema: 0.2" in r.stdout,
               r.stdout[:600]))

# ------------------------------------------------------------------ English leaves the alias
r_en = run(MIGRATE, "--store", store, "--context", "golden")
mira_hunk = [b for b in r_en.stdout.split("--- ") if b.startswith("golden/personas/coo-mira.md")]
checks.append(("without the locale, the alias empty-section line is not rewritten",
               all("no evidence as of" not in h for h in mira_hunk), mira_hunk[:1]))
checks.append(("without the locale, coo-mira is still migrated for its schema line",
               bool(mira_hunk) and "+schema: 0.2" in mira_hunk[0], mira_hunk[:1]))

# ------------------------------------------------------------------ --apply
store = copy(FIX_01, "apply")
r = xx("--store", store, "--context", "golden", "--apply")
checks.append(("--apply exits 0", r.returncode == 0, (r.returncode, r.stderr[-400:])))
checks.append(("--apply reports what it wrote", "written" in r.stdout, r.stdout[-400:]))

personas = sorted((store / "golden/personas").glob("*.md"))
checks.append(("every migrated persona declares schema 0.2",
               len(personas) == 3 and all(schema_of(read(p)) == "0.2" for p in personas),
               [(p.name, schema_of(read(p))) for p in personas]))
checks.append(("context.md declares schema 0.2",
               schema_of(read(store / "golden/context.md")) == "0.2",
               read(store / "golden/context.md")[:200]))

for name in ("cto-jonas.md", "coo-mira.md"):
    checks.append((f"migrated {name} is byte-identical to the golden 0.2 file",
                   read(store / "golden/personas" / name) == read(GOLDEN / "personas" / name),
                   name))

astrid = read(store / "golden/personas/cfo-astrid.md")
checks.append(("watchlist ids assigned", "- [wl-01] **Possible openness" in astrid, astrid[-600:]))
checks.append(("the joined tag is split into one parenthesis per Fact",
               'machine-transcribed, 2026-06-11) (Fact — "Vague percentages' in astrid,
               [ln for ln in astrid.splitlines() if "Vague percentages" in ln]))
checks.append(("no joined tag survives the migration", "; Fact —" not in astrid, astrid[:0]))
checks.append(("cfo-astrid is otherwise the golden file (only the joined bullet differs)",
               [ln for ln in astrid.splitlines() if "Vague percentages" not in ln]
               == read(GOLDEN / "personas/cfo-astrid.md").splitlines(),
               astrid[:200]))

mira = read(store / "golden/personas/coo-mira.md")
checks.append(("the alias empty-section form is rewritten to the canonical English one",
               ALIAS not in mira and mira.count("- no evidence as of 2026-06-20") == 2,
               [ln for ln in mira.splitlines() if "no evidence" in ln]))

audit = read(store / "golden/AUDIT.md")
checks.append(("the AUDIT derived-file header is rewritten to the hand-appended wording",
               "Do not hand-edit" not in audit
               and "<!-- one line per source ingestion; hand-appended -->" in audit, audit[:300]))
checks.append(("AUDIT carries the schema comment", "<!-- schema: 0.2 -->" in audit, audit[:300]))
checks.append(("AUDIT gains the pinned migration line",
               re.search(r"^\d{4}-\d{2}-\d{2} \| migrate 0\.1 -> 0\.2 \| \d+ files changed$",
                         audit, re.M) is not None, audit[-200:]))
checks.append(("the AUDIT ingestion rows are untouched",
               audit.count("| type: private-communication |") == 3, audit))
checks.append(("AUDIT above the migration line is the golden AUDIT",
               [ln for ln in audit.splitlines() if "migrate 0.1" not in ln and ln.strip()]
               == [ln for ln in read(GOLDEN / "AUDIT.md").splitlines() if ln.strip()],
               audit[-300:]))

snap = read(store / "golden/calibration/pending-brief-q3.md")
checks.append(("snapshot schema bumped to 0.2",
               "schema: 0.2" in snap and "schema: 0.1" not in snap, snap[:200]))
checks.append(("snapshot is otherwise the golden snapshot",
               snap == read(GOLDEN / "calibration/pending-brief-q3.md"), snap[:200]))

idx = read(store / "golden/INDEX.md")
checks.append(("the index was regenerated with the schema header line",
               "<!-- schema: 0.2 -->" in idx, idx[:300]))
checks.append(("the regenerated index equals the golden index",
               [ln for ln in idx.splitlines() if not ln.startswith("<!-- last regenerated:")]
               == [ln for ln in read(GOLDEN / "INDEX.md").splitlines()
                   if not ln.startswith("<!-- last regenerated:")], idx[:600]))

# ------------------------------------------------------------------ idempotent
r2 = xx("--store", store, "--context", "golden")
checks.append(("a second migrate finds nothing to change",
               r2.returncode == 0 and "nothing to migrate" in r2.stdout, (r2.returncode, r2.stdout)))
gold = copy(HERE / "test_fixtures/store", "golden-store")
r3 = xx("--store", gold, "--context", "golden")
checks.append(("migrate on the 0.2 golden store finds nothing to change",
               r3.returncode == 0 and "nothing to migrate" in r3.stdout, (r3.returncode, r3.stdout)))

# ------------------------------------------------------------------ usage errors
r = xx("--store", store, "--to", "0.3")
checks.append(("--to a version this release cannot produce is a usage error (exit 1)",
               r.returncode == 1 and "0.2" in r.stderr, (r.returncode, r.stderr)))
r = xx("--store", store, "--context", "nope")
checks.append(("an unknown context is a usage error (exit 1)",
               r.returncode == 1, (r.returncode, r.stderr)))
r = xx("--store", TMP / "no-such-store")
checks.append(("a missing store is a usage error (exit 1)", r.returncode == 1, (r.returncode, r.stderr)))

# ------------------------------------------------------------------ content loss refused
# 0.3.1 (E6): the lossy fixture's declared-empty bullet that also carries a Fact tag is no
# longer rewritten (whole-bullet rule), so it no longer trips the guard: it is left as prose
# (checked below). The guard itself is exercised in process further down, with a rule that
# drops a Fact tag — it must still refuse the whole run and write nothing.
lossy = copy(FIX_LOSSY, "lossy")
r = xx("--store", lossy, "--context", "tangle", "--apply")
ada = read(lossy / "tangle/personas/ops-ada.md")
checks.append(("the mixed declared-empty bullet keeps its Fact tag after --apply",
               r.returncode == 0 and '(Fact — "no production cutover on a Friday"' in ada,
               (r.returncode, r.stderr[-300:])))

# ------------------------------------------------------------------ through the entrypoint
store = copy(FIX_01, "entry")
r = run(ENTRY, "--store", store, "--locale", "xx", "migrate", "--context", "golden",
        env={"BEFOREHAND_LOCALE_DIR": str(LOCALE_DIR)})
checks.append(("beforehand.py migrate dispatches to the module",
               r.returncode == 0 and "not available before task" not in r.stderr,
               (r.returncode, r.stderr[:200])))

# ---------------------------------------------- FR-1.1: a pre-0.2 prose snapshot is left alone
# `migrate` could recover a prose prediction's id and title and nothing else — not the slug,
# the grounding section, the specificity or an ISO date. It therefore rewrites nothing here
# and says so in its docstring; the way back into the log is `calibrate --ledger`.
prose_store = copy(FIX_01, "prose")
prose = prose_store / "golden/calibration/pending-prose.md"
prose.write_text("# Prediction snapshot - brief\n\n"
                 "Document reviewed: docs/brief.md\n"
                 "Frozen on: the first of June\n"
                 "Meeting expected: the tenth of June\n\n"
                 "### P1 - the reconciliation baseline\n"
                 "She will ask for one before signing.\n", encoding="utf-8")
before_prose = state(prose_store)
r = xx("--store", prose_store)
checks.append(("a prose snapshot is not in the diff of a 0.1 -> 0.2 migration",
               r.returncode == 0 and "pending-prose.md" not in r.stdout,
               (r.returncode, r.stdout[:400])))
checks.append(("and a dry run over it writes nothing", state(prose_store) == before_prose,
               "store changed"))
r = xx("--store", prose_store, "--apply")
checks.append(("--apply leaves the prose snapshot byte-identical",
               r.returncode == 0
               and state(prose_store)["golden/calibration/pending-prose.md"]
               == before_prose["golden/calibration/pending-prose.md"],
               (r.returncode, r.stdout[:300])))
checks.append(("the docstring points at the command that can grade it",
               "calibrate --ledger" in read(MIGRATE), "no pointer in the docstring"))

# ---------------------------------------------- 0.3.1 E6: a bullet is rewritten only whole
# `canonical_empty_sections` used `search`: a sentence that merely CONTAINED the phrase and a
# date became the bare canonical bullet, and the content guard (Fact tags, headings, 10%
# shrink) did not see the loss. Now only a bullet that IS the phrase plus a date is rewritten;
# any other bullet carrying the phrase is left and listed on a `left as prose:` line.
e6 = copy(GOLDEN, "e6-src")
e6_store = TMP / "e6"
e6_store.mkdir()
shutil.move(str(e6), str(e6_store / "golden"))
PROSE = ("- Budget above 2M needs the board; no evidence as of 2026-01-01 on capex, but she "
         "asked twice for a TCO sheet.")
pp = e6_store / "golden/personas/cfo-astrid.md"
pt = read(pp)
pt = re.sub(r"(?m)^schema: 0\.2$", "schema: 0.1", pt, count=1)
pt = pt.rstrip("\n") + "\n\n## Notes\n" + PROSE + "\n- no evidence as of 2026-01-01\n"
pp.write_text(pt, encoding="utf-8")
r = run(MIGRATE, "--store", e6_store, "--context", "golden", "--apply")
after = read(pp)
checks.append(("E6: migrate exits 0 on a prose bullet carrying the phrase",
               r.returncode == 0, (r.returncode, r.stderr[-300:])))
checks.append(("E6: the prose bullet is left exactly as written", PROSE in after, after[-400:]))
checks.append(("E6: ... and listed on a `left as prose:` line naming the file",
               any(ln.startswith("left as prose: ") and "golden/personas/cfo-astrid.md" in ln
                   and "TCO sheet" in ln for ln in r.stdout.splitlines()), r.stdout[-500:]))
checks.append(("E6: a bullet that IS the phrase plus a date stays canonical",
               "\n- no evidence as of 2026-01-01\n" in after, after[-200:]))

# the 0.1 lossy fixture: a declared-empty bullet that also carries a Fact tag is no longer
# rewritten at all (so there is nothing for the guard to refuse): it is left as prose.
lossy2 = copy(FIX_LOSSY, "lossy-e6")
r = xx("--store", lossy2, "--context", "tangle")
checks.append(("E6: the declared-empty bullet with a Fact tag is left as prose, not refused",
               r.returncode == 0 and "left as prose: tangle/personas/ops-ada.md" in r.stdout,
               (r.returncode, r.stdout[-400:], r.stderr[-300:])))

# ---------------------------------------------- 0.3.1 E9: `schema:0.1` without a space
e9 = copy(FIX_01, "e9")
mp = e9 / "golden/personas/coo-mira.md"
mt = read(mp)
mt = re.sub(r"(?m)^slug:", "schema:0.1\nslug:", mt, count=1)
mp.write_text(mt, encoding="utf-8")
r = xx("--store", e9, "--context", "golden", "--apply")
fm_block = read(mp).split("---")[1]
checks.append(("E9: `schema:0.1` is recognised: one schema key, bumped to 0.2",
               r.returncode == 0 and re.findall(r"(?m)^schema:.*$", fm_block) == ["schema: 0.2"],
               (r.returncode, re.findall(r"(?m)^schema:.*$", fm_block))))
sys.path.insert(0, str(HERE))
import migrate as _mg  # noqa: E402

checks.append(("E9: a snapshot's `schema:0.1` is bumped too",
               _mg.migrate_snapshot("# s\n\nschema:0.1\nfrozen: x\n") == "# s\n\nschema: 0.2\nfrozen: x\n",
               _mg.migrate_snapshot("# s\n\nschema:0.1\nfrozen: x\n")))

# ---------------------------------------------- the content guard still refuses, in process
# The one rule that used to trip the guard no longer rewrites a mixed bullet, so the refusal
# is exercised directly: a rule that drops a Fact tag must still stop the whole run.
import contextlib  # noqa: E402
import io  # noqa: E402

guard = copy(FIX_01, "guard")
before_guard = state(guard)
saved_rule = _mg.migrate_persona
_mg.migrate_persona = lambda text: re.sub(r"\(Fact\b[^)]*\)", "", text)
try:
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()) as err:
        rc = _mg.main(["--store", str(guard), "--context", "golden", "--apply"])
finally:
    _mg.migrate_persona = saved_rule
checks.append(("a rule that would drop a Fact tag is still refused (exit 2), nothing written",
               rc == 2 and state(guard) == before_guard and "Fact tags" in err.getvalue(),
               (rc, err.getvalue()[-300:])))

fails = [c for c in checks if not c[1]]
for n, ok, got in checks:
    print(("ok   " if ok else "FAIL ") + n + ("" if ok else f" -> {str(got)[:400]}"))
print(f"\n{len(checks)-len(fails)}/{len(checks)} passed")
sys.exit(1 if fails else 0)
