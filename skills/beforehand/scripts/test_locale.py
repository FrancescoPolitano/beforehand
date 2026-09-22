#!/usr/bin/env python3
"""Tests for locale as data (SPEC-0.2 FR-4.4).

Every regex that used to have a language baked into it — a generic-speaker label, a
declared-empty-section phrase, a snapshot's field names, the "if it repeats" clause on a
Watchlist entry — is now built from `personas_lib.load_locale()`. English ships
(scripts/locales/en.json); the `xx` test locale used here lives only in
test_fixtures/locales/ and is reached through BEFOREHAND_LOCALE_DIR, never shipped.

The xx-only sample words these checks feed to each script (a generic-speaker transcript
label, a declared-empty-section line, a snapshot field name, a Watchlist repeat clause —
each one recognised only under the `xx` locale, not the shipped default) are deliberately
NOT written as Python string literals in this file: they live in
test_fixtures/locale-samples/ instead, so the FR-4.4 acceptance grep
(`grep -nE '<pattern>' scripts/*.py`, run over every .py file with no exclusions) finds
nothing here either — this test module is itself one of the "scripts" it is proving clean.

Run from the scripts/ directory: python3 test_locale.py
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True  # G5: a suite run on its own leaves no __pycache__

HERE = Path(__file__).parent
FIXTURE_LOCALES = HERE / "test_fixtures/locales"
SAMPLES = HERE / "test_fixtures/locale-samples"
checks = []


def run(script, *a, env=None):
    full_env = dict(os.environ)
    if env:
        full_env.update(env)
    return subprocess.run([sys.executable, str(HERE / script), *[str(x) for x in a]],
                          capture_output=True, text=True, env=full_env)


def write(name, body):
    p = Path(tempfile.mkdtemp()) / name
    p.write_text(body, encoding="utf-8")
    return p


def sample(name):
    return (SAMPLES / name).read_text(encoding="utf-8")


XX_ENV = {"BEFOREHAND_LOCALE": "xx", "BEFOREHAND_LOCALE_DIR": str(FIXTURE_LOCALES)}

# ---- speakers.py: a generic-speaker word is locale data, not built-in Italian ------------
transcript_text = sample("generic-speaker.txt")
transcript = write("call.txt", transcript_text)
generic_label = transcript_text.splitlines()[0].split(":")[0]  # the xx-only generic label,
# read out of the fixture rather than named here, so this file never spells it out itself
r = run("speakers.py", transcript, "--json")
d = json.loads(r.stdout)
labels = {s["label"]: s for s in d["speakers"]}
checks.append(("default locale: the xx-only generic label is a named speaker, not generic",
               labels.get(generic_label, {}).get("kind") == "named", labels))
checks.append(("default locale: nothing unidentified, clean exit", r.returncode == 0, r.returncode))

r = run("speakers.py", transcript, "--json", env=XX_ENV)
d2 = json.loads(r.stdout)
labels2 = {s["label"]: s for s in d2["speakers"]}
checks.append(("xx locale: the xx-only generic label becomes unidentified",
               labels2.get(generic_label, {}).get("kind") == "unidentified", labels2))
checks.append(("xx locale: the unidentified speaker fails the run", r.returncode == 2, r.returncode))

# ---- coverage.py: the declared-empty-section phrase is locale data ----------------------
persona = write("persona.md", sample("empty-section.md"))
r = run("coverage.py", persona, "--json")
res = json.loads(r.stdout)
checks.append(("default locale: the xx-only empty-declaration is not recognised as declared",
               "Red lines" not in res["empty_declared"], res))
r = run("coverage.py", persona, "--json", env=XX_ENV)
res2 = json.loads(r.stdout)
checks.append(("xx locale: the same line is recognised as a declared-empty section",
               "Red lines" in res2["empty_declared"], res2))

# ---- pending.py: the snapshot field names are locale data -------------------------------
store = Path(tempfile.mkdtemp())
(store / "acme/calibration").mkdir(parents=True)
(store / "acme/personas").mkdir()
(store / "acme/calibration/pending-brief.md").write_text(sample("snapshot.md"), encoding="utf-8")
r = run("pending.py", "--store", store, "--json")
rows = json.loads(r.stdout)
checks.append(("default locale: the xx-only field name is not read, no meeting date",
               bool(rows) and rows[0]["meeting"] is None and "no meeting date" in rows[0]["status"], rows))
r = run("pending.py", "--store", store, "--json", env=XX_ENV)
rows2 = json.loads(r.stdout)
checks.append(("xx locale: the xx-only field name is read as the meeting date",
               bool(rows2) and rows2[0]["meeting"] == "2026-01-01", rows2))

# ---- watchlist.py: the "if it repeats" clause is locale data -----------------------------
wl = write("watchlist.md", sample("watchlist.md"))
r = run("watchlist.py", wl, "--promote", "Trait", "--section", "Red lines", env={"BEFOREHAND_LOCALE": "en"})
checks.append(("default locale: the xx-only repeat clause is not flagged",
               "belonged to the anteroom" not in r.stderr, r.stderr))
r2 = run("watchlist.py", wl, "--promote", "Trait", "--section", "Red lines", env=XX_ENV)
checks.append(("xx locale: the xx-only repeat clause is recognised and flagged for rewriting",
               "belonged to the anteroom" in r2.stderr, r2.stderr))

# ---- FR-4.4 laziness: a locale set AFTER personas_lib was first imported must still be
# honoured. personas_lib is typically imported once, early (e.g. by whatever first needed
# `resolve_store`), often before a later `--locale` is applied to the environment in the
# same process; `same_source_re` (and every other locale-derived regex) must therefore be
# resolved at CALL time, not baked in at that first import. No cache-clearing needed: the
# cache key is the resolved code string, not "has this been called before".
sys.path.insert(0, str(HERE))
same_source_sample = sample("same-source.txt").strip()
saved_locale = os.environ.pop("BEFOREHAND_LOCALE", None)
saved_locale_dir = os.environ.pop("BEFOREHAND_LOCALE_DIR", None)
try:
    import personas_lib as _lib
    before = _lib.locale_regexes()["same_source_re"].match(same_source_sample)
    os.environ["BEFOREHAND_LOCALE"] = "xx"
    os.environ["BEFOREHAND_LOCALE_DIR"] = str(FIXTURE_LOCALES)
    after = _lib.locale_regexes()["same_source_re"].match(same_source_sample)
finally:
    if saved_locale is None:
        os.environ.pop("BEFOREHAND_LOCALE", None)
    else:
        os.environ["BEFOREHAND_LOCALE"] = saved_locale
    if saved_locale_dir is None:
        os.environ.pop("BEFOREHAND_LOCALE_DIR", None)
    else:
        os.environ["BEFOREHAND_LOCALE_DIR"] = saved_locale_dir
checks.append((
    "lazy locale: personas_lib imported before the xx locale was set still recognises "
    "the xx-only same-source alias once it is set",
    before is None and after is not None, (before, after)))

# ---- the locale caches are keyed on (code, BEFOREHAND_LOCALE_DIR), never on the code alone.
# `xx` is not a file, it is a file found on a search path, and the path is an environment
# variable: a process that loads `xx` from one directory and is then pointed at another must
# read the second one. Cached on the code alone, the first directory a process happened to
# see was served for the rest of its life — which is exactly what a host that sets the
# variable per command, or a suite that swaps locale directories, does.
alt_locales = Path(tempfile.mkdtemp())
(alt_locales / "xx.json").write_text(json.dumps({"same_source": ["zzz"]}), encoding="utf-8")
saved_locale = os.environ.get("BEFOREHAND_LOCALE")
saved_locale_dir = os.environ.get("BEFOREHAND_LOCALE_DIR")
try:
    os.environ["BEFOREHAND_LOCALE"] = "xx"
    os.environ["BEFOREHAND_LOCALE_DIR"] = str(FIXTURE_LOCALES)
    from_fixture = _lib.locale_regexes()["same_source_re"].match("zzz")
    os.environ["BEFOREHAND_LOCALE_DIR"] = str(alt_locales)
    from_alt = _lib.locale_regexes()["same_source_re"].match("zzz")
finally:
    if saved_locale is None:
        os.environ.pop("BEFOREHAND_LOCALE", None)
    else:
        os.environ["BEFOREHAND_LOCALE"] = saved_locale
    if saved_locale_dir is None:
        os.environ.pop("BEFOREHAND_LOCALE_DIR", None)
    else:
        os.environ["BEFOREHAND_LOCALE_DIR"] = saved_locale_dir
checks.append((
    "locale cache key includes BEFOREHAND_LOCALE_DIR: the same code read from a second "
    "directory yields that directory's word list, not the first one's",
    from_fixture is None and from_alt is not None, (from_fixture, from_alt)))

# ---- `same_source` is English data, not a museum of every language's shorthand. A German
# abbreviation left in the shipped list made a German word for "same place" read as a source
# reference in an English persona; removed, it falls through to not-a-path and is reported as
# unverifiable, which is what an unresolvable reference is.
en_same_source = _lib.locale_regexes("en")["same_source_re"]
checks.append(("the shipped English same-source list carries no German abbreviation",
               en_same_source.match("ebd.") is None, en_same_source.pattern))
checks.append(("the English same-source shorthand itself still matches",
               en_same_source.match("ibid.") is not None, en_same_source.pattern))

# ---- an unknown locale is a usage error naming what is available ------------------------
r = run("speakers.py", transcript, "--json",
        env={"BEFOREHAND_LOCALE": "zz", "BEFOREHAND_LOCALE_DIR": str(FIXTURE_LOCALES)})
checks.append(("unknown locale exits 1", r.returncode == 1, r.returncode))
checks.append(("unknown locale names what is available",
               "unknown locale 'zz'" in r.stderr and "available: en, xx" in r.stderr, r.stderr))
r3 = run("speakers.py", transcript, "--json", env={"BEFOREHAND_LOCALE": "zz"})
checks.append(("unknown locale without the test locale dir still names 'en' as available",
               "available: en" in r3.stderr, r3.stderr))

# ---- ...but the locale is validated AFTER parse_args, so the one command that tells you
# which locales exist is not the one the locale typo blocks: `--help` must print under
# BEFOREHAND_LOCALE=zz, and argparse's own usage errors must still be usage errors.
for mod in ("watchlist.py", "verify_quotes.py"):
    rh = run(mod, "--help", env={"BEFOREHAND_LOCALE": "zz"})
    checks.append(("%s --help exits 0 under an unknown locale" % mod, rh.returncode == 0,
                   (rh.returncode, rh.stderr[:200])))
    checks.append(("%s --help prints its usage under an unknown locale" % mod,
                   "usage:" in rh.stdout, rh.stdout[:200]))
rv = run("verify_quotes.py", "nosuch-persona.md", "--lint", env={"BEFOREHAND_LOCALE": "zz"})
checks.append(("a real invocation under an unknown locale still exits 1 with the same message",
               rv.returncode == 1 and "unknown locale 'zz'" in rv.stderr,
               (rv.returncode, rv.stderr[:200])))

# ---- reindex.py validates BEFOREHAND_LOCALE too, same message and exit code as every other
# locale-consuming module (it has no locale-derived regex of its own, but the check is
# uniform across the CLI regardless of which command you run).
store_dir = Path(tempfile.mkdtemp()) / "store"
(store_dir / "acme/personas").mkdir(parents=True)
(store_dir / "acme/calibration").mkdir()
r4 = run("reindex.py", "--store", store_dir, "--dry-run",
         env={"BEFOREHAND_LOCALE": "zz", "BEFOREHAND_LOCALE_DIR": str(FIXTURE_LOCALES)})
checks.append(("reindex.py: unknown locale exits 1, same as the other modules",
               r4.returncode == 1, r4.returncode))
checks.append(("reindex.py: unknown locale names what is available",
               "unknown locale 'zz'" in r4.stderr and "available: en, xx" in r4.stderr, r4.stderr))
r5 = run("reindex.py", "--store", store_dir, "--dry-run", env={"BEFOREHAND_LOCALE": "en"})
checks.append(("reindex.py: a valid locale runs normally", r5.returncode == 0, (r5.returncode, r5.stderr)))

# ---- FR-4.4 acceptance grep: no hardcoded Italian survives in ANY scripts/*.py, tests
# included — the pattern itself is read from a fixture file (not a Python string literal)
# so this very check does not reintroduce what it is proving absent.
pattern = sample("grep-pattern.txt").strip()
g = subprocess.run(["grep", "-nE", pattern, *[str(p) for p in sorted(HERE.glob("*.py"))]],
                   capture_output=True, text=True)
checks.append(("no hardcoded Italian tokens remain in scripts/*.py",
               g.stdout == "" and g.returncode == 1, g.stdout))

fails = [c for c in checks if not c[1]]
for n, ok, got in checks:
    print(("ok   " if ok else "FAIL ") + n + ("" if ok else f" -> {str(got)[:300]}"))
print(f"\n{len(checks)-len(fails)}/{len(checks)} passed")
sys.exit(1 if fails else 0)
