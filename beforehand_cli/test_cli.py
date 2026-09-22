#!/usr/bin/env python3
"""Tests for the `beforehand` CLI (SPEC-1.0 §2, §3). Stdlib only, print-ok/FAIL style.

Run from anywhere: python3 beforehand_cli/test_cli.py
Every install/uninstall runs against a temporary HOME; nothing is written under the real
home directory or inside the repository (the bundle comparison builds both archives in a
temporary directory, from a copy of the files dev/build_skill.sh reads).
"""
import contextlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO))
from beforehand_cli import __version__, cli  # noqa: E402

RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append(bool(cond))
    if cond:
        print("ok   %s" % name)
    else:
        print("FAIL %s%s" % (name, (" — " + detail) if detail else ""))


def run(argv, home):
    """cli.main(argv) with HOME=home; returns (rc, stdout+stderr)."""
    saved = os.environ.get("HOME")
    os.environ["HOME"] = str(home)
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            rc = cli.main(argv)
    finally:
        if saved is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = saved
    return rc, buf.getvalue()


def files_in(d):
    return sorted(p.relative_to(d).as_posix() for p in d.rglob("*") if p.is_file())


def test_locate(tmp):
    skill, agent = cli.locate(HERE)
    check("locate: source checkout -> repository skills/beforehand",
          skill == REPO / "skills" / "beforehand" and agent == REPO / "agents" / "persona-reviewer.md",
          "%s %s" % (skill, agent))
    pkg = tmp / "site" / "beforehand_cli"
    (pkg / "_data" / "skills" / "beforehand").mkdir(parents=True)
    (pkg / "_data" / "skills" / "beforehand" / "SKILL.md").write_text("x\n", encoding="utf-8")
    (pkg / "_data" / "agents").mkdir(parents=True)
    (pkg / "_data" / "agents" / "persona-reviewer.md").write_text("a\n", encoding="utf-8")
    skill, agent = cli.locate(pkg)
    check("locate: installed layout -> package data",
          skill == pkg / "_data" / "skills" / "beforehand"
          and agent == pkg / "_data" / "agents" / "persona-reviewer.md", "%s %s" % (skill, agent))
    empty = tmp / "nowhere" / "beforehand_cli"
    empty.mkdir(parents=True)
    try:
        cli.locate(empty)
        check("locate: neither layout -> error", False, "no exception")
    except cli.CliError as e:
        check("locate: neither layout -> error", "cannot find the skill" in str(e), str(e))


def test_install_cycle(tmp):
    home = tmp / "home1"
    home.mkdir()
    skill_dst = home / ".claude" / "skills" / "beforehand"
    agent_dst = home / ".claude" / "agents" / "persona-reviewer.md"
    src_skill, src_agent = cli.locate(HERE)

    rc, out = run(["install"], home)
    check("install: exit 0 into a fresh HOME", rc == 0, out)
    check("install: skill copied", (skill_dst / "SKILL.md").is_file()
          and (skill_dst / "scripts" / "beforehand.py").is_file(), out)
    marker = skill_dst / ".installed-by-beforehand"
    check("install: marker holds the version",
          marker.is_file() and marker.read_text(encoding="utf-8").strip() == __version__)
    check("install: agent copied byte for byte",
          agent_dst.is_file() and agent_dst.read_bytes() == src_agent.read_bytes())
    check("install: agent file is 0644, like the skill files (not mkstemp's default 0600)",
          (agent_dst.stat().st_mode & 0o777) == 0o644, oct(agent_dst.stat().st_mode & 0o777))
    shipped = [f for f in files_in(src_skill) if "__pycache__" not in f and not f.endswith(".pyc")
               and not f.endswith(".DS_Store")]
    got = [f for f in files_in(skill_dst) if f != ".installed-by-beforehand"]
    check("install: the copy equals the skill (no __pycache__, .pyc, .DS_Store)", got == shipped,
          "%d vs %d files" % (len(got), len(shipped)))
    check("install: prints paths with $HOME as ~",
          "wrote ~/.claude/skills/beforehand/" in out
          and "wrote ~/.claude/agents/persona-reviewer.md" in out
          and "wrote ~/.claude/skills/beforehand/.installed-by-beforehand" in out
          and str(home) not in out, out)
    leftovers = [p.name for p in skill_dst.parent.iterdir() if p.name != "beforehand"]
    leftovers += [p.name for p in agent_dst.parent.iterdir() if p.name != "persona-reviewer.md"]
    check("install: no temp dir or file left beside the targets", leftovers == [], str(leftovers))

    # The installed copy has no `.claude-plugin/plugin.json` two levels above it (only a
    # checkout or a plugin install has that); its own test suite must still pass end to end.
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    proc = subprocess.run(
        [sys.executable, "-B", str(skill_dst / "scripts" / "beforehand.py"), "test"],
        cwd=str(skill_dst), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        universal_newlines=True)
    check("install: the installed copy's own `beforehand.py test` exits 0",
          proc.returncode == 0, proc.stdout[-4000:])

    rc, out = run(["install"], home)
    check("install again without --update: refused, exit 1",
          rc == 1 and ("install: refused: ~/.claude/skills/beforehand is already installed "
                       "(version %s); rerun with --update to replace it" % __version__) in out, out)

    (skill_dst / "stale-file.txt").write_text("old\n", encoding="utf-8")
    agent_dst.write_text("an older prompt\n", encoding="utf-8")
    rc, out = run(["install", "--update"], home)
    check("install --update: exit 0, replaces the skill wholesale and the agent",
          rc == 0 and not (skill_dst / "stale-file.txt").exists()
          and agent_dst.read_bytes() == src_agent.read_bytes() and marker.is_file(), out)

    agent_dst.write_text("someone else's reviewer\n", encoding="utf-8")
    rc, out = run(["uninstall"], home)
    check("uninstall: a differing agent file is refused, nothing removed",
          rc == 1 and ("uninstall: refused: ~/.claude/agents/persona-reviewer.md differs from the one "
                       "beforehand %s ships; remove it by hand if it is yours to remove" % __version__) in out
          and skill_dst.is_dir() and agent_dst.is_file(), out)
    agent_dst.write_bytes(src_agent.read_bytes())

    rc, out = run(["uninstall"], home)
    check("uninstall: removes what it installed",
          rc == 0 and not skill_dst.exists() and not agent_dst.exists()
          and "removed ~/.claude/skills/beforehand/" in out
          and "removed ~/.claude/agents/persona-reviewer.md" in out, out)
    check("uninstall: leaves the parent dirs", skill_dst.parent.is_dir() and agent_dst.parent.is_dir())
    rc, out = run(["uninstall"], home)
    check("uninstall with nothing installed: exit 0, says so",
          rc == 0 and "nothing to remove" in out, out)


def test_refusals(tmp):
    home = tmp / "home2"
    skills = home / ".claude" / "skills"
    agents = home / ".claude" / "agents"
    skills.mkdir(parents=True)
    agents.mkdir(parents=True)
    checkout = tmp / "checkout" / "beforehand"
    checkout.mkdir(parents=True)
    (checkout / "SKILL.md").write_text("dev copy\n", encoding="utf-8")
    os.symlink(str(checkout), str(skills / "beforehand"))

    rc, out = run(["install"], home)
    check("install: symlinked destination refused, exit 1",
          rc == 1 and ("install: refused: ~/.claude/skills/beforehand is a symlink (a developer "
                       "checkout is never written through); remove the link to install a copy") in out, out)
    rc, out = run(["install", "--update"], home)
    check("install --update: symlinked destination still refused",
          rc == 1 and "is a symlink" in out, out)
    check("install: the symlink target is untouched",
          (checkout / "SKILL.md").read_text(encoding="utf-8") == "dev copy\n"
          and sorted(p.name for p in checkout.iterdir()) == ["SKILL.md"])
    check("install: refused before writing the agent", not (agents / "persona-reviewer.md").exists())
    rc, out = run(["uninstall"], home)
    check("uninstall: symlinked destination refused",
          rc == 1 and ("uninstall: refused: ~/.claude/skills/beforehand is a symlink (a developer "
                       "checkout is never removed)") in out and (skills / "beforehand").is_symlink(), out)
    os.unlink(str(skills / "beforehand"))

    (skills / "beforehand").mkdir()
    (skills / "beforehand" / "SKILL.md").write_text("hand-made\n", encoding="utf-8")
    for argv in (["install"], ["install", "--update"]):
        rc, out = run(argv, home)
        check("%s: unmarked destination refused" % " ".join(argv),
              rc == 1 and ("install: refused: ~/.claude/skills/beforehand exists and was not installed "
                           "by beforehand (no .installed-by-beforehand marker)") in out, out)
    rc, out = run(["uninstall"], home)
    check("uninstall: unmarked destination refused, left in place",
          rc == 1 and ("uninstall: refused: ~/.claude/skills/beforehand was not installed by "
                       "beforehand (no .installed-by-beforehand marker)") in out
          and (skills / "beforehand" / "SKILL.md").is_file(), out)
    shutil.rmtree(str(skills / "beforehand"))

    (agents / "persona-reviewer.md").write_text("another plugin's reviewer\n", encoding="utf-8")
    rc, out = run(["install"], home)
    check("install: a differing agent file refused, exit 1, nothing written",
          rc == 1 and ("install: refused: ~/.claude/agents/persona-reviewer.md exists and differs from "
                       "the one beforehand %s ships; rerun with --update to replace it" % __version__) in out
          and not (skills / "beforehand").exists(), out)
    rc, out = run(["install", "--update"], home)
    check("install --update: replaces a differing agent file", rc == 0, out)

    home3 = tmp / "home3"
    home3.mkdir()
    sk, ag = tmp / "alt" / "sk", tmp / "alt" / "ag"
    rc, out = run(["install", "--skills-dir", str(sk), "--agents-dir", str(ag)], home3)
    check("install --skills-dir/--agents-dir: writes there, not under HOME",
          rc == 0 and (sk / "beforehand" / ".installed-by-beforehand").is_file()
          and (ag / "persona-reviewer.md").is_file() and not (home3 / ".claude").exists(), out)
    rc, out = run(["uninstall", "--skills-dir", str(sk), "--agents-dir", str(ag)], home3)
    check("uninstall --skills-dir/--agents-dir", rc == 0 and not (sk / "beforehand").exists(), out)


def zip_names(path):
    with zipfile.ZipFile(str(path)) as zf:
        return sorted(zf.namelist())


def test_bundle(tmp):
    out_dir = tmp / "bundle-out"
    rc, out = run(["bundle", "--out", str(out_dir)], tmp)
    archive = out_dir / ("beforehand-%s.skill" % __version__)
    check("bundle: exit 0, writes beforehand-<version>.skill", rc == 0 and archive.is_file(), out)
    if not archive.is_file():
        return
    names = zip_names(archive)
    check("bundle: rooted at beforehand/, no __pycache__/.pyc/.DS_Store",
          all(n.startswith("beforehand/") for n in names)
          and not any("__pycache__" in n or n.endswith(".pyc") or n.endswith(".DS_Store") for n in names))
    if shutil.which("zip") is None:
        print("skip bundle equals build_skill.sh (zip not on PATH)")
        return
    # build_skill.sh writes into <root>/dist: run it on a copy of what it reads.
    fake = tmp / "fake-root"
    for rel in (".claude-plugin", "skills/beforehand", "agents", "docs/assets", "dev/build_skill.sh"):
        src, dst = REPO / rel, fake / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(str(src), str(dst), ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        else:
            shutil.copy2(str(src), str(dst))
    proc = subprocess.run(["sh", str(fake / "dev" / "build_skill.sh")], stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, universal_newlines=True)
    built = sorted((fake / "dist").glob("*.skill")) if (fake / "dist").is_dir() else []
    check("bundle: build_skill.sh ran on the copy", proc.returncode == 0 and len(built) == 1, proc.stdout)
    if built:
        theirs = zip_names(built[0])
        check("bundle: entry list equals build_skill.sh's (%d entries)" % len(names), names == theirs,
              "only ours: %s; only theirs: %s" % (sorted(set(names) - set(theirs))[:5],
                                                 sorted(set(theirs) - set(names))[:5]))


def test_passthrough_and_version(tmp):
    rc, out = run(["--version"], tmp)
    check("--version: prints `beforehand <version>`, exit 0",
          rc == 0 and out.strip() == "beforehand %s" % __version__, out)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", HOME=str(tmp))
    proc = subprocess.run([sys.executable, "-B", "-m", "beforehand_cli", "--version"], cwd=str(REPO), env=env,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
    check("python3 -m beforehand_cli --version", proc.returncode == 0
          and proc.stdout.strip() == "beforehand %s" % __version__, proc.stdout)
    proc = subprocess.run([sys.executable, "-B", "-m", "beforehand_cli", "no-such-command"], cwd=str(REPO),
                          env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
    check("passthrough: beforehand.py's exit code kept (unknown command -> 1)",
          proc.returncode == 1 and "unknown command: no-such-command" in proc.stdout, proc.stdout)
    store = tmp / "empty-store"
    store.mkdir()
    proc = subprocess.run([sys.executable, "-B", "-m", "beforehand_cli", "doctor", "--store", str(store)],
                          cwd=str(REPO), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          universal_newlines=True)
    check("passthrough: `beforehand doctor --store X` runs beforehand.py doctor (exit 0)",
          proc.returncode == 0 and "doctor" in proc.stdout, proc.stdout)
    # The documented way to run from a checkout, `python3 -B -m beforehand_cli`, leaves no
    # __pycache__ (PYTHONDONTWRITEBYTECODE unset, so -B alone must do it). Run on a temp copy,
    # so a failure never dirties the repository.
    bare = tmp / "checkout-copy"
    shutil.copytree(str(HERE), str(bare / "beforehand_cli"),
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    bare_env = dict(os.environ, HOME=str(tmp))
    bare_env.pop("PYTHONDONTWRITEBYTECODE", None)
    proc = subprocess.run([sys.executable, "-B", "-m", "beforehand_cli", "--version"], cwd=str(bare),
                          env=bare_env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          universal_newlines=True)
    left = sorted(str(p.relative_to(bare)) for p in bare.rglob("*")
                  if p.name == "__pycache__" or p.suffix == ".pyc")
    check("`python3 -B -m beforehand_cli --version` from a checkout copy leaves no __pycache__",
          proc.returncode == 0 and not left, "%s %s" % (proc.stdout.strip(), left))
    rc, out = run([], tmp)
    check("no arguments: usage, exit 1", rc == 1 and "usage: beforehand" in out, out)
    rc, out = run(["--help"], tmp)
    check("--help: usage, exit 0", rc == 0 and "beforehand install" in out and "bundle" in out, out)


def main():
    tmp = Path(tempfile.mkdtemp(prefix="beforehand-cli-test-"))
    try:
        for t in (test_locate, test_install_cycle, test_refusals, test_bundle, test_passthrough_and_version):
            try:
                t(tmp)
            except Exception as e:  # a crash in one group is a FAIL, not a stopped suite
                check("%s did not crash" % t.__name__, False, "%s: %s" % (type(e).__name__, e))
    finally:
        shutil.rmtree(str(tmp), ignore_errors=True)
    passed = sum(RESULTS)
    print("%d/%d passed" % (passed, len(RESULTS)))
    return 0 if RESULTS and passed == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
