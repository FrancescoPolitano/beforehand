#!/usr/bin/env python3
"""Single entrypoint for the beforehand skill's scripts (FR-4.1, FR-4.3).

Usage:
  beforehand.py [--store PATH] [--locale CODE] <command> [args...]
  beforehand.py --help              one line per command
  beforehand.py <command> --help    that module's own argparse help

Global options precede the command; each module still takes its own arguments after it.
--store is resolved with the same precedence every module uses (--store > BEFOREHAND_STORE
env var > ~/.beforehand), then exported as BEFOREHAND_STORE for the whole process — so a
module without its own --store flag still sees it through the environment — and passed
as --store to the modules that declare that flag. --locale is exported as BEFOREHAND_LOCALE;
this entrypoint only carries it through, and each module reads it for itself.
"""
import importlib
import os
import re
import subprocess
import sys
from pathlib import Path

# a run through the dogfooding symlink must not leave __pycache__ in the tree
# (dev/check_generality.sh) — set before importing any sibling module
sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from personas_lib import resolve_store  # noqa: E402

# command name -> (module name, or None for `test`, which runs here; one-line role; exit codes)
COMMANDS = {
    "lint": ("verify_quotes",
             "Check Fact excerpts against their sources; --lint gates",
             "0 ok (report), or --migrate-ref applied · 1 --lint: NOT FOUND/UNPARSEABLE present or an "
             "undeclared --against shrink; or --migrate-ref found no match"),
    "save": ("save_source",
             "Save a source file intact, with a provenance header",
             "0 ok · 1 usage · 2 exists with different content · 3 inside a personas store · "
             "4 inside a git work tree and not ignored"),
    "reindex": ("reindex",
                "Rebuild INDEX.md files for a store or one context",
                "0 ok · 1 usage (--pointer without --context, unknown locale) · "
                "2 store/context not found · 3 --fail-on-lint and a persona fails · "
                "4 --fail-on-gaps and gaps found"),
    "pending": ("pending",
                "List calibration snapshots due or overdue for review",
                "0 ok (a report) · 1 usage with --set-meeting"),
    "speakers": ("speakers",
                 "List speakers in a transcript, or extract one speaker's turns",
                 "0 clean · 1 usage/unparseable · 2 unidentified speakers not resolved · "
                 "3 dubious turns present and not requested"),
    "coverage": ("coverage",
                 "Score how much source material supports a persona",
                 "0 ok · 1 usage"),
    "watchlist": ("watchlist",
                  "List and promote Watchlist entries",
                  "0 ok · 1 usage · 2 the edit would lose content (refused)"),
    "calibrate": ("calibrate",
                  "Grade predictions against what a meeting actually said",
                  "0 ok · 1 usage · 2 not gradeable (the reason is printed)"),
    "panel": ("panel",
              "Validate one reviewer output, or aggregate a panel round",
              "0 ok · 1 schema error with --validate, usage, or a malformed output "
              "with --aggregate"),
    "doctor": ("doctor",
               "Health-check a personas store: gaps, staleness, snapshots, open offers",
               "0 always (a report)"),
    "migrate": ("migrate",
                "Bring a store up to the current schema, diff first",
                "0 ok · 1 usage · 2 would lose content"),
    "forget": ("forget",
               "Remove one person from a store, audited",
               "0 ok · 1 usage · 2 slug not found"),
    "log": ("log_flow",
            "Append one line to the store's usage log",
            "0 ok"),
    "test": (None,
             "Run every test_*.py suite in this directory",
             "0 all suites passed · 1 any suite failed"),
}

# Command order fixed here (this is what --help prints, and what "unknown command" lists).
ORDER = ["lint", "save", "reindex", "pending", "speakers", "coverage", "watchlist",
         "calibrate", "panel", "doctor", "migrate", "forget", "log", "test"]

# Commands whose module accepts a --store flag: --store is both exported as BEFOREHAND_STORE
# and passed through explicitly to these.
HAS_STORE_FLAG = {"save", "reindex", "pending", "log", "doctor", "migrate", "forget",
                  "calibrate"}

_PASSED_LINE = re.compile(r"^(\d+)/(\d+) passed$")


def print_help():
    print(__doc__.strip())
    print()
    print("commands:")
    for name in ORDER:
        _, role, codes = COMMANDS[name]
        print(f"  {name:10s} {role}")
        print(f"             exit codes: {codes}")


STDERR_TAIL = 20


def run_test_command():
    """`test`: run every test_*.py next to this file, one line per suite (FR-5.9, G4).

    A suite passes only when it exits 0 AND its last `N/M passed` line has M > 0: a suite
    with no summary line (it crashed before printing one) or `0/0` is `<suite>: no checks
    ran`, a failure, so a green run cannot hide a suite that never executed. A failing suite
    shows why: its `FAIL ` lines, then the last lines of its stderr (a traceback's tail)."""
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    test_files = sorted(HERE.glob("test_*.py"))
    all_ok = True
    for tf in test_files:
        proc = subprocess.run([sys.executable, str(tf)], capture_output=True, text=True, env=env)
        summary = None
        for ln in reversed(proc.stdout.splitlines()):
            m = _PASSED_LINE.match(ln.strip())
            if m:
                summary = m
                break
        ran = summary is not None and int(summary.group(2)) > 0
        ok = proc.returncode == 0 and ran
        all_ok = all_ok and ok
        print(f"{tf.stem}: {summary.group(0) if ran else 'no checks ran'}")
        if ok:
            continue
        for ln in proc.stdout.splitlines():
            if ln.startswith("FAIL "):
                print("  " + ln)
        err = proc.stderr.rstrip("\n").splitlines()[-STDERR_TAIL:]
        if err:
            print(f"  -- stderr (last {len(err)} lines) --")
            for ln in err:
                print("  " + ln)
    return 0 if all_ok else 1


def _split_global_options(argv):
    """Global options precede the command: pull --store/--locale off the front, manually
    (argparse would need to know the subcommand's own flags to do this safely)."""
    store_cli = None
    locale_cli = None
    i = 0
    while i < len(argv):
        tok = argv[i]
        if tok == "--store":
            if i + 1 >= len(argv):
                print("usage: --store requires a PATH", file=sys.stderr)
                return None
            store_cli = argv[i + 1]
            i += 2
        elif tok.startswith("--store="):
            store_cli = tok.split("=", 1)[1]
            i += 1
        elif tok == "--locale":
            if i + 1 >= len(argv):
                print("usage: --locale requires a CODE", file=sys.stderr)
                return None
            locale_cli = argv[i + 1]
            i += 2
        elif tok.startswith("--locale="):
            locale_cli = tok.split("=", 1)[1]
            i += 1
        else:
            break
    return store_cli, locale_cli, argv[i:]


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)

    if not argv or argv[0] in ("--help", "-h"):
        print_help()
        return 0

    parsed = _split_global_options(argv)
    if parsed is None:
        return 1
    store_cli, locale_cli, rest = parsed

    if not rest:
        print_help()
        return 0
    if rest[0] in ("--help", "-h"):
        print_help()
        return 0

    command, cmd_args = rest[0], rest[1:]
    if command not in COMMANDS:
        print(f"unknown command: {command}", file=sys.stderr)
        print("commands: " + ", ".join(ORDER), file=sys.stderr)
        return 1

    store = resolve_store(store_cli)
    os.environ["BEFOREHAND_STORE"] = str(store)
    if locale_cli is not None:
        os.environ["BEFOREHAND_LOCALE"] = locale_cli

    if command == "test":
        return run_test_command()

    module_name = COMMANDS[command][0]
    module_args = list(cmd_args)
    if command in HAS_STORE_FLAG and not any(
            a == "--store" or a.startswith("--store=") for a in module_args):
        module_args = ["--store", str(store)] + module_args

    # argparse takes its prog from sys.argv[0]: without this, `beforehand.py watchlist --help`
    # would print `usage: beforehand.py …` and its errors `beforehand.py: error:`, neither of
    # which can be typed back. Set before the import, so a module that builds its parser at
    # import time sees it too.
    sys.argv[0] = "%s %s" % (Path(sys.argv[0]).name, command)
    module = importlib.import_module(module_name)
    return module.main(module_args)


if __name__ == "__main__":
    sys.exit(main())
