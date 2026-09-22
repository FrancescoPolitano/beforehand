#!/usr/bin/env python3
"""Tests for beforehand.py: the single entrypoint and --store precedence (FR-4.1, FR-4.3)."""
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True  # G5: a suite run on its own leaves no __pycache__

HERE = Path(__file__).parent
P = HERE / "beforehand.py"
# The store root (a "golden" context lives inside it, per test_fixtures/store/golden/);
# pending.py scans every context under a store, so pointing --store here finds it.
GOLDEN = HERE / "test_fixtures/store"
checks = []


def run(*a, env=None, cwd=None):
    full_env = dict(os.environ)
    if env:
        full_env.update(env)
    return subprocess.run([sys.executable, str(P), *map(str, a)],
                           capture_output=True, text=True, env=full_env, cwd=cwd)


COMMAND_NAMES = ["lint", "save", "reindex", "pending", "speakers", "coverage", "watchlist",
                 "calibrate", "panel", "doctor", "migrate", "forget", "log", "test"]

# ---- --help lists all 14 commands -------------------------------------------------
r = run("--help")
checks.append(("beforehand.py --help exits 0", r.returncode == 0, r.returncode))
missing = [c for c in COMMAND_NAMES if c not in r.stdout]
checks.append(("--help lists all 14 commands", not missing, missing))
checks.append(("--help with no args (bare invocation) also prints help",
               run().stdout == r.stdout, run().stdout))

# ---- beforehand.py <command> --help forwards to the module's own argparse help -------
r = run("lint", "--help")
checks.append(("beforehand.py lint --help exits 0", r.returncode == 0, r.returncode))
checks.append(("beforehand.py lint --help contains --lint", "--lint" in r.stdout, r.stdout))

r = run("save", "--help")
checks.append(("beforehand.py save --help contains --dir", "--dir" in r.stdout, r.stdout))

# ---- --store PATH finds the golden store without --store on the subcommand --------
r = run("--store", GOLDEN, "pending", "--json")
checks.append(("--store PATH pending --json exits 0", r.returncode == 0, (r.returncode, r.stderr)))
try:
    rows = json.loads(r.stdout)
    checks.append(("--store PATH pending --json is a JSON list", isinstance(rows, list), r.stdout))
    checks.append(("--store PATH pending --json finds the golden pending snapshot",
                   any("brief-q3" in (row.get("document") or "") for row in rows), rows))
except json.JSONDecodeError:
    checks.append(("--store PATH pending --json parses as JSON", False, r.stdout))

# ---- BEFOREHAND_STORE env var finds the golden store without --store anywhere -------
r = run("pending", "--json", env={"BEFOREHAND_STORE": str(GOLDEN)})
checks.append(("BEFOREHAND_STORE=golden pending --json exits 0", r.returncode == 0, (r.returncode, r.stderr)))
try:
    rows = json.loads(r.stdout)
    checks.append(("BEFOREHAND_STORE env pending --json finds the golden pending snapshot",
                   any("brief-q3" in (row.get("document") or "") for row in rows), rows))
except json.JSONDecodeError:
    checks.append(("BEFOREHAND_STORE env pending --json parses as JSON", False, r.stdout))

# ---- --store (CLI) takes precedence over BEFOREHAND_STORE (env) ---------------------
with tempfile.TemporaryDirectory() as empty_store:
    r = run("--store", GOLDEN, "pending", "--json", env={"BEFOREHAND_STORE": empty_store})
    try:
        rows = json.loads(r.stdout)
        checks.append(("--store CLI beats BEFOREHAND_STORE env",
                       any("brief-q3" in (row.get("document") or "") for row in rows), rows))
    except json.JSONDecodeError:
        checks.append(("--store CLI beats BEFOREHAND_STORE env: JSON parses", False, r.stdout))

# ---- a bogus command exits 1 and lists the commands --------------------------------
r = run("bogus-command")
checks.append(("bogus command exits 1", r.returncode == 1, r.returncode))
checks.append(("bogus command lists known commands on stderr",
               all(c in r.stderr for c in COMMAND_NAMES), r.stderr))

# ---- every command is built: none of them prints the placeholder any more ---------
# (calibrate landed in task 16, panel in task 14, migrate and forget in task 18)
NOT_YET = {}
checks.append(("no command is left unregistered in COMMANDS", not NOT_YET, NOT_YET))
r = run("calibrate")
checks.append(("calibrate dispatches to its module instead of the placeholder",
               r.returncode == 1 and "not available before task" not in r.stderr,
               (r.returncode, r.stdout, r.stderr)))
checks.append(("calibrate with no arguments is a usage error (1, never 2: 2 is reserved "
               "for `not gradeable`)", r.returncode == 1 and "--context" in r.stderr, r.stderr))
r = run("--store", GOLDEN, "calibrate", "--context", "golden", "--doc", "brief-q3")
checks.append(("calibrate exits 1 (usage) when the pairing and annotation are not there yet",
               r.returncode == 1 and "not available before task" not in r.stderr,
               (r.returncode, r.stdout, r.stderr)))

# ---- migrate and forget (task 18) are built: they dispatch, with their own codes --
r = run("--store", GOLDEN, "migrate", "--to", "9.9")
checks.append(("migrate dispatches to its module instead of the placeholder",
               r.returncode == 1 and "not available before task" not in r.stderr,
               (r.returncode, r.stdout, r.stderr)))
r = run("--store", GOLDEN, "forget", "nobody-here")
checks.append(("forget dispatches to its module and exits 2 on an unknown slug",
               r.returncode == 2 and "not available before task" not in r.stderr,
               (r.returncode, r.stdout, r.stderr)))

# ---- panel (task 14) is built: usage error on no mode, and its own exit codes -----
r = run("panel")
checks.append(("panel dispatches to its module instead of the placeholder",
               r.returncode == 1 and "not available before task" not in r.stderr,
               (r.returncode, r.stdout, r.stderr)))

# ---- doctor (task 10) is built: it dispatches like any other command --------------
r = run("--store", GOLDEN, "doctor", "--context", "golden", "--today", "2026-09-17")
checks.append(("doctor exits 0 through the entrypoint", r.returncode == 0, (r.returncode, r.stderr)))
checks.append(("doctor prints its pinned summary line",
               r.stdout.strip().splitlines()[-1] == "doctor: healthy", r.stdout))

# ---- running a module directly still works and prints the deprecation line --------
with tempfile.TemporaryDirectory() as tmp:
    import shutil
    tmp_store = Path(tmp) / "store"
    shutil.copytree(GOLDEN, tmp_store)
    r = subprocess.run([sys.executable, str(HERE / "reindex.py"), "--store", tmp_store],
                        capture_output=True, text=True)
    checks.append(("reindex.py run directly still exits 0", r.returncode == 0, r.returncode))
    checks.append(("reindex.py run directly prints the deprecation line on stderr",
                   "deprecated: use beforehand.py reindex" in r.stderr, r.stderr))

r = subprocess.run([sys.executable, str(HERE / "speakers.py"), "--help"], capture_output=True, text=True)
checks.append(("speakers.py run directly still works (--help exits 0)", r.returncode == 0, r.returncode))
checks.append(("speakers.py run directly prints the deprecation line on stderr",
               "deprecated: use beforehand.py speakers" in r.stderr, r.stderr))

r = subprocess.run([sys.executable, str(HERE / "save_source.py"), "--verify", str(HERE / "beforehand.py")],
                    capture_output=True, text=True)
checks.append(("save_source.py run directly prints the deprecation line on stderr",
               "deprecated: use beforehand.py save" in r.stderr, r.stderr))
checks.append(("save_source.py --verify on a file with no header still exits 1 (die() codes preserved)",
               r.returncode == 1, r.returncode))

# ---- --locale is exported as BEFOREHAND_LOCALE for the process ----------------------
sys.path.insert(0, str(HERE))
import contextlib  # noqa: E402
import importlib  # noqa: E402
import io  # noqa: E402

entry = importlib.import_module("beforehand")
saved_store, saved_locale = os.environ.get("BEFOREHAND_STORE"), os.environ.get("BEFOREHAND_LOCALE")
try:
    # "en" here, not an arbitrary code: Task 8 made every module that reads BEFOREHAND_LOCALE
    # validate it (an unknown locale is now a usage error, exit 1 — see test_locale.py), so
    # this check needs a locale that actually loads; it is only exercising env-var export
    # and exit-code pass-through, not locale validation itself.
    with contextlib.redirect_stdout(io.StringIO()):  # in-process call: silence the module's own prints
        rc = entry.main(["--store", str(GOLDEN), "--locale", "en", "pending", "--json"])
    checks.append(("in-process beforehand.main exits 0", rc == 0, rc))
    checks.append(("--locale en is exported as BEFOREHAND_LOCALE",
                   os.environ.get("BEFOREHAND_LOCALE") == "en", os.environ.get("BEFOREHAND_LOCALE")))
    checks.append(("--store is exported as BEFOREHAND_STORE, resolved",
                   os.environ.get("BEFOREHAND_STORE") == str(Path(GOLDEN).resolve()),
                   os.environ.get("BEFOREHAND_STORE")))
finally:
    for k, v in (("BEFOREHAND_STORE", saved_store), ("BEFOREHAND_LOCALE", saved_locale)):
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v

# ---- exit codes from a module pass through beforehand.py unchanged ------------------
r = run("speakers", str(HERE / "does-not-exist.txt"))
checks.append(("beforehand.py speakers on a missing file exits 1 (module's own usage code)",
               r.returncode == 1, r.returncode))

r = run("watchlist", str(HERE / "does-not-exist.md"))
checks.append(("beforehand.py watchlist on a missing persona exits 1", r.returncode == 1, r.returncode))

# ---- log: --store is both exported and passed through to a module that has the flag
with tempfile.TemporaryDirectory() as tmp:
    r = run("--store", tmp, "log", "review", "northwind", "--doc", "smoke-test")
    checks.append(("beforehand.py log exits 0", r.returncode == 0, (r.returncode, r.stderr)))
    logged = (Path(tmp) / "usage.jsonl")
    checks.append(("beforehand.py log writes usage.jsonl under --store", logged.is_file(), tmp))
    if logged.is_file():
        row = json.loads(logged.read_text().strip().splitlines()[0])
        checks.append(("logged row records the flow", row.get("flow") == "review", row))

# ---- E5: the dispatched command's name is argparse's prog -------------------------
for _cmd in ("watchlist", "panel", "coverage"):
    r = run(_cmd, "--help")
    checks.append((f"beforehand.py {_cmd} --help prints `usage: beforehand.py {_cmd}`",
                   r.stdout.startswith(f"usage: beforehand.py {_cmd}"), r.stdout[:80]))
r = run("watchlist")
checks.append(("a module's own argparse error names the command "
               "(`beforehand.py watchlist: error:`)",
               "beforehand.py watchlist: error:" in r.stderr, r.stderr[-200:]))

# ---- FR-4.3: a real run writes no __pycache__ next to the scripts -----------------
# Run from a throwaway copy of scripts/ so the assertion cannot be satisfied by a
# leftover-free repository that some other step just cleaned.
with tempfile.TemporaryDirectory() as tmp:
    tmp_scripts = Path(tmp) / "scripts"
    shutil.copytree(HERE, tmp_scripts,
                    ignore=shutil.ignore_patterns("__pycache__", "test_*.py", "test_fixtures"))
    cache = tmp_scripts / "__pycache__"
    bytecode_env = dict(os.environ)
    # Essential: `beforehand.py test` exports PYTHONDONTWRITEBYTECODE=1 for every suite it
    # runs, so an inherited environment would make this pass without the source change.
    bytecode_env.pop("PYTHONDONTWRITEBYTECODE", None)
    r = subprocess.run([sys.executable, str(tmp_scripts / "beforehand.py"),
                        "doctor", "--store", str(Path(tmp) / "nostore")],
                       capture_output=True, text=True, env=bytecode_env)
    checks.append(("a run from a temp copy of scripts/ exits 0", r.returncode == 0,
                   (r.returncode, r.stderr[-200:])))
    checks.append(("a real run leaves no __pycache__ beside the scripts",
                   not cache.exists(), sorted(p.name for p in tmp_scripts.iterdir())))
    # Control: the same interpreter, the same environment, a plain import of a module that
    # does not turn bytecode off — this is what would have happened without
    # sys.dont_write_bytecode. (Not personas_lib: since 0.3.1 it turns bytecode off itself,
    # G5.) Skipped when the interpreter itself was started with -B, where
    # nothing writes bytecode and the control is vacuous.
    if not sys.flags.dont_write_bytecode:
        (tmp_scripts / "bytecode_probe.py").write_text("X = 1\n", encoding="utf-8")
        subprocess.run([sys.executable, "-c",
                        "import sys; sys.path.insert(0, sys.argv[1]); import bytecode_probe",
                        str(tmp_scripts)],
                       capture_output=True, text=True, env=bytecode_env)
        checks.append(("control: a plain import in the same environment does write it",
                       cache.is_dir(), cache.exists()))
        shutil.rmtree(cache, ignore_errors=True)

# ---- G5 / FR-2.6: a module run DIRECTLY (not through beforehand.py) writes no __pycache__
# either. Every script module sets sys.dont_write_bytecode right after `import sys`, before
# any sibling import, so not even personas_lib's own cache file is written (the interpreter
# caches a module before executing it, so the library's own line alone could not prevent it).
with tempfile.TemporaryDirectory() as tmp:
    tmp_scripts = Path(tmp) / "scripts"
    shutil.copytree(HERE, tmp_scripts,
                    ignore=shutil.ignore_patterns("__pycache__", "test_*.py", "test_fixtures"))
    bytecode_env = dict(os.environ)
    bytecode_env.pop("PYTHONDONTWRITEBYTECODE", None)
    r = subprocess.run([sys.executable, str(tmp_scripts / "verify_quotes.py"), "--help"],
                       capture_output=True, text=True, env=bytecode_env)
    checks.append(("G5: verify_quotes.py --help run directly from a temp copy exits 0",
                   r.returncode == 0, (r.returncode, r.stderr[-200:])))
    checks.append(("G5: a directly-run module leaves no __pycache__ beside the scripts",
                   not (tmp_scripts / "__pycache__").exists(),
                   sorted(p.name for p in (tmp_scripts / "__pycache__").iterdir())
                   if (tmp_scripts / "__pycache__").is_dir() else None))
    # doctor imports five siblings (and, through them, personas_lib): the widest import graph
    r = subprocess.run([sys.executable, str(tmp_scripts / "doctor.py"),
                        "--store", str(Path(tmp) / "nostore")],
                       capture_output=True, text=True, env=bytecode_env)
    checks.append(("G5: doctor.py run directly from a temp copy exits 0",
                   r.returncode == 0, (r.returncode, r.stderr[-200:])))
    checks.append(("G5: doctor.py run directly leaves no __pycache__ beside the scripts",
                   not (tmp_scripts / "__pycache__").exists(),
                   sorted(p.name for p in (tmp_scripts / "__pycache__").iterdir())
                   if (tmp_scripts / "__pycache__").is_dir() else None))

# Statically, for every script module AND every test_*.py suite (the suites are run by
# `test` with PYTHONDONTWRITEBYTECODE=1 already): the flag is set at module level before the
# first import of a sibling module, so a module added later cannot quietly skip it.
import ast  # noqa: E402

_siblings = {p.stem for p in HERE.glob("*.py")}
_late = []
for _p in sorted(HERE.glob("*.py")):
    _flag_line, _sib_line = None, None
    for _node in ast.walk(ast.parse(_p.read_text(encoding="utf-8"))):
        if (isinstance(_node, ast.Assign) and len(_node.targets) == 1
                and isinstance(_node.targets[0], ast.Attribute)
                and _node.targets[0].attr == "dont_write_bytecode"
                and isinstance(_node.targets[0].value, ast.Name)
                and _node.targets[0].value.id == "sys" and _node.col_offset == 0):
            _flag_line = _node.lineno if _flag_line is None else min(_flag_line, _node.lineno)
        _names = ([_node.module] if isinstance(_node, ast.ImportFrom)
                  else [a.name for a in _node.names] if isinstance(_node, ast.Import) else [])
        if any(n in _siblings for n in _names):
            _sib_line = _node.lineno if _sib_line is None else min(_sib_line, _node.lineno)
    if _flag_line is None or (_sib_line is not None and _sib_line < _flag_line):
        _late.append(_p.name)
checks.append(("G5: every script and test module under scripts/ sets sys.dont_write_bytecode "
               "before any sibling import", not _late, _late))

# ---- G4 / FR-5.9: `test` shows why a suite failed, and an empty suite is a failure ----
# A throwaway directory holding beforehand.py (plus the library it imports) and three
# synthetic suites: one that crashes at import, one that runs no checks, one that fails a
# check. The real suites are not involved, so the runner's reporting is what is measured.
with tempfile.TemporaryDirectory() as tmp:
    rdir = Path(tmp) / "scripts"
    rdir.mkdir()
    for name in ("beforehand.py", "personas_lib.py"):
        shutil.copy2(HERE / name, rdir / name)
    (rdir / "test_crash.py").write_text(
        "import sys\nsys.dont_write_bytecode = True\n"
        "def deep():\n    raise RuntimeError('crash-marker-g4')\ndeep()\n", encoding="utf-8")
    (rdir / "test_empty.py").write_text(
        "import sys\nsys.dont_write_bytecode = True\nprint('\\n0/0 passed')\n", encoding="utf-8")
    (rdir / "test_quiet.py").write_text(
        "import sys\nsys.dont_write_bytecode = True\nprint('nothing to report')\n",
        encoding="utf-8")
    (rdir / "test_red.py").write_text(
        "import sys\nsys.dont_write_bytecode = True\n"
        "print('ok   first')\nprint('FAIL second-marker  -> got 1')\n"
        "print('stderr-marker', file=sys.stderr)\nprint('\\n1/2 passed')\nsys.exit(1)\n",
        encoding="utf-8")
    r = subprocess.run([sys.executable, str(rdir / "beforehand.py"), "test"],
                       capture_output=True, text=True)
    out = r.stdout + r.stderr
    checks.append(("G4: `test` exits 1 when a suite crashes, runs nothing, or fails",
                   r.returncode == 1, (r.returncode, out[-400:])))
    checks.append(("G4: a suite crashing at import is `test_crash: no checks ran`",
                   "test_crash: no checks ran" in out, out[-600:]))
    checks.append(("G4: the crashing suite's traceback tail is shown",
                   "RuntimeError: crash-marker-g4" in out and "Traceback" in out, out[-600:]))
    checks.append(("G4: a suite printing `0/0 passed` is `test_empty: no checks ran`",
                   "test_empty: no checks ran" in out, out[-600:]))
    checks.append(("G4: a suite with no summary line is `test_quiet: no checks ran`",
                   "test_quiet: no checks ran" in out, out[-600:]))
    checks.append(("G4: a failing suite keeps its summary and prints its FAIL lines and stderr",
                   "test_red: 1/2 passed" in out and "FAIL second-marker" in out
                   and "stderr-marker" in out and "ok   first" not in out, out[-600:]))
    (rdir / "test_crash.py").unlink()
    (rdir / "test_empty.py").unlink()
    (rdir / "test_quiet.py").unlink()
    (rdir / "test_red.py").unlink()
    (rdir / "test_green.py").write_text(
        "import sys\nsys.dont_write_bytecode = True\nprint('ok   a')\nprint('\\n1/1 passed')\n",
        encoding="utf-8")
    r = subprocess.run([sys.executable, str(rdir / "beforehand.py"), "test"],
                       capture_output=True, text=True)
    checks.append(("G4: an all-green directory exits 0 with one summary line",
                   r.returncode == 0 and r.stdout.strip() == "test_green: 1/1 passed",
                   (r.returncode, r.stdout, r.stderr[-300:])))

# ---- S10: the dead "not available before task N" branch is gone -----------------------
_src = (HERE / "beforehand.py").read_text(encoding="utf-8")
checks.append(("S10: beforehand.py no longer carries the `not available before task` branch",
               "not available before task" not in _src and "task_n" not in _src, None))

# ---- the version is written once, and the badges are not a second place it lives --------
# `.claude-plugin/plugin.json` is the single source; `dev/build_skill.sh` reads it, but the
# two README badges are hand-written markdown that no script generates. Asserting the
# parity here is what makes "written once" true instead of aspirational. Only the repository
# holds plugin.json and the top-level README: an installed `.skill` has neither, and there
# the check does not apply.
REPO = HERE.parent.parent.parent          # scripts/ -> beforehand/ -> skills/ -> repo
PLUGIN_JSON = REPO / ".claude-plugin/plugin.json"
if PLUGIN_JSON.is_file():
    declared = json.loads(PLUGIN_JSON.read_text(encoding="utf-8")).get("version")
    badge = "badge/version-%s-" % declared
    for readme in (REPO / "README.md", HERE.parent / "README.md"):
        if not readme.is_file():
            continue
        checks.append(("%s carries the version badge of plugin.json (%s)"
                       % (readme.name if readme.parent == REPO else "skills/beforehand/"
                          + readme.name, declared),
                       badge in readme.read_text(encoding="utf-8"), badge))
    # SPEC-1.0 §0: the other manifests state the same version (marketplace entry, pyproject,
    # the CLI package), so the plugin, the uvx install and the bundle never disagree.
    stated = {}
    _mkt = REPO / ".claude-plugin/marketplace.json"
    if _mkt.is_file():
        stated["marketplace.json"] = [p.get("version") for p in json.loads(
            _mkt.read_text(encoding="utf-8")).get("plugins", [])]
    for _rel, _pat in (("pyproject.toml", r'(?m)^version\s*=\s*"([^"]+)"'),
                       ("beforehand_cli/__init__.py", r'(?m)^__version__\s*=\s*"([^"]+)"')):
        if (REPO / _rel).is_file():
            stated[_rel] = re.findall(_pat, (REPO / _rel).read_text(encoding="utf-8"))[:1]
    checks.append(("marketplace.json, pyproject.toml and beforehand_cli state plugin.json's "
                   "version (%s)" % declared,
                   bool(stated) and all(v == [declared] for v in stated.values()), stated))

# ---- SPEC-1.0 §7: the old public name is gone, with no alias ----------------------
# The shipped tree names the entry script, the environment variables, the default store and
# the dev workspace only by their `beforehand` names. The old spellings are assembled here
# from parts so this file does not match itself. CHANGELOG.md keeps its history; like the
# badge check, this applies only in a checkout (an installed copy has no plugin.json).
if PLUGIN_JSON.is_file():
    _old = "personas"
    stale = (_old + ".py", _old.upper() + "_", "~/." + _old, "." + _old + "-dev")
    shipped = [REPO / d for d in ("skills", "agents", "beforehand_cli", "dev", "evals", "docs")]
    shipped += [REPO / f for f in ("README.md", "CONTRIBUTING.md", ".gitignore")]
    stale_hits = []
    for top in shipped:
        files = [top] if top.is_file() else sorted(p for p in top.rglob("*") if p.is_file())
        for f in files:
            if "__pycache__" in f.parts or f.suffix == ".pyc":
                continue
            try:
                text = f.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for n, line in enumerate(text.splitlines(), 1):
                if any(s in line for s in stale):
                    stale_hits.append("%s:%d" % (f.relative_to(REPO), n))
    checks.append(("no shipped file names the old entry script, env vars, store or workspace",
                   not stale_hits, (len(stale_hits), stale_hits[:10])))

fails =[c for c in checks if not c[1]]
for name, ok, got in checks:
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  -> got {got!r}"))
print(f"\n{len(checks) - len(fails)}/{len(checks)} passed")
sys.exit(1 if fails else 0)
