"""The `beforehand` command (SPEC-1.0 §2). Python 3.9 stdlib only.

  beforehand install [--update] [--skills-dir DIR] [--agents-dir DIR]
  beforehand uninstall [--skills-dir DIR] [--agents-dir DIR]
  beforehand bundle [--out DIR]
  beforehand --version
  beforehand <command> [args...]      passed to the skill's scripts/beforehand.py

Defaults: skills dir ~/.claude/skills, agents dir ~/.claude/agents. The skill is copied (never
symlinked) to <skills dir>/beforehand with a marker file `.installed-by-beforehand` holding the
version; the agent prompt to <agents dir>/persona-reviewer.md.

Refusals (exit 1, nothing written): the skill destination is a symlink (a developer checkout
is never written through); it exists without the marker; it exists with the marker and
--update was not given; the agent file exists, differs from ours, and --update was not given.
Every copy is made in a temporary directory beside its target and then renamed into place, so
an interrupted run never leaves half an install.

Exit codes: 0 ok · 1 refused, or usage · otherwise beforehand.py's own exit code (passthrough).
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

sys.dont_write_bytecode = True

from beforehand_cli import __version__  # noqa: E402

NAME = "beforehand"
AGENT = "persona-reviewer.md"
MARKER = ".installed-by-beforehand"
# Never shipped, installed or bundled: __pycache__ and .pyc embed the absolute path of the
# machine that compiled them; .DS_Store is Finder noise.
JUNK_DIRS = ("__pycache__",)
JUNK_FILES = (".DS_Store",)
JUNK_SUFFIXES = (".pyc",)

USAGE = """usage: beforehand install [--update] [--skills-dir DIR] [--agents-dir DIR]
       beforehand uninstall [--skills-dir DIR] [--agents-dir DIR]
       beforehand bundle [--out DIR]
       beforehand --version
       beforehand <command> [args...]

  install     copy the skill to ~/.claude/skills/beforehand and the reviewer agent to
              ~/.claude/agents/persona-reviewer.md (--update replaces a previous install)
  uninstall   remove what install wrote, and nothing else
  bundle      write beforehand-%s.skill (a skill archive for hosts that install one)
  --version   print the version
  <command>   any other command runs the skill's scripts/beforehand.py, e.g.
              `beforehand doctor`, `beforehand test` (`beforehand help` lists them)""" % __version__


class CliError(Exception):
    """A refusal or usage error: printed as is, exit 1."""


def locate(package_dir=None):
    """(skill dir, agent file) this run ships.

    Installed from a wheel: the package data under <package>/_data/. From a source checkout:
    the repository's skills/beforehand/ and agents/persona-reviewer.md, beside the package."""
    pkg = Path(package_dir) if package_dir is not None else Path(__file__).resolve().parent
    candidates = [
        (pkg / "_data" / "skills" / NAME, pkg / "_data" / "agents" / AGENT),
        (pkg.parent / "skills" / NAME, pkg.parent / "agents" / AGENT),
    ]
    for skill, agent in candidates:
        if (skill / "SKILL.md").is_file() and agent.is_file():
            return skill, agent
    raise CliError("beforehand: cannot find the skill (looked in %s and %s)"
                   % (candidates[0][0], candidates[1][0]))


def show(path):
    """A path for printing: $HOME shown as ~."""
    p = str(path)
    home = str(Path.home())
    if home and home != "/" and (p == home or p.startswith(home + os.sep)):
        return "~" + p[len(home):]
    return p


def _junk(name, is_dir):
    if is_dir:
        return name in JUNK_DIRS
    return name in JUNK_FILES or name.endswith(JUNK_SUFFIXES)


def _ignore(directory, names):
    return {n for n in names if _junk(n, os.path.isdir(os.path.join(directory, n)))}


def _skill_files(skill):
    """(relative dir paths, relative file paths) of the skill, junk excluded, sorted."""
    dirs, files = [], []
    for dirpath, dirnames, filenames in os.walk(str(skill)):
        dirnames[:] = sorted(d for d in dirnames if not _junk(d, True))
        rel = os.path.relpath(dirpath, str(skill))
        if rel != ".":
            dirs.append(rel.replace(os.sep, "/"))
        for f in sorted(filenames):
            if not _junk(f, False):
                files.append((f if rel == "." else os.path.join(rel, f)).replace(os.sep, "/"))
    return dirs, files


def _read_marker(skill_dst):
    try:
        return (skill_dst / MARKER).read_text(encoding="utf-8").strip()
    except OSError:
        return None


def _targets(args):
    home = Path.home()
    skills_dir = Path(args.skills_dir).expanduser() if args.skills_dir else home / ".claude" / "skills"
    agents_dir = Path(args.agents_dir).expanduser() if args.agents_dir else home / ".claude" / "agents"
    return skills_dir / NAME, agents_dir / AGENT


def cmd_install(args):
    src_skill, src_agent = locate()
    skill_dst, agent_dst = _targets(args)
    ours = src_agent.read_bytes()

    # every refusal is decided before anything is written
    if skill_dst.is_symlink():
        raise CliError("install: refused: %s is a symlink (a developer checkout is never written "
                       "through); remove the link to install a copy" % show(skill_dst))
    if skill_dst.exists():
        if not skill_dst.is_dir() or not (skill_dst / MARKER).is_file():
            raise CliError("install: refused: %s exists and was not installed by beforehand (no %s marker)"
                           % (show(skill_dst), MARKER))
        if not args.update:
            raise CliError("install: refused: %s is already installed (version %s); rerun with --update "
                           "to replace it" % (show(skill_dst), _read_marker(skill_dst) or "unknown"))
    if agent_dst.is_symlink():
        raise CliError("install: refused: %s is a symlink; remove the link to install a copy"
                       % show(agent_dst))
    if agent_dst.exists():
        if not agent_dst.is_file():
            raise CliError("install: refused: %s exists and is not a file" % show(agent_dst))
        if agent_dst.read_bytes() != ours and not args.update:
            raise CliError("install: refused: %s exists and differs from the one beforehand %s ships; "
                           "rerun with --update to replace it" % (show(agent_dst), __version__))

    # skill: copy into a temp dir beside the target, then rename into place
    skill_dst.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".%s-install-" % NAME, dir=str(skill_dst.parent)))
    try:
        new = stage / NAME
        shutil.copytree(str(src_skill), str(new), ignore=_ignore)
        (new / MARKER).write_text(__version__ + "\n", encoding="utf-8")
        count = sum(1 for p in new.rglob("*") if p.is_file())
        if skill_dst.exists():
            os.rename(str(skill_dst), str(stage / "previous"))
        os.rename(str(new), str(skill_dst))
    finally:
        shutil.rmtree(str(stage), ignore_errors=True)
    print("wrote %s/ (%d files)" % (show(skill_dst), count))
    print("wrote %s" % show(skill_dst / MARKER))

    # agent: temp file beside the target, then replace
    agent_dst.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".%s-install-" % AGENT, dir=str(agent_dst.parent))
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(ours)
        os.chmod(tmp_name, 0o644)  # mkstemp defaults to 0600; match the skill files' 0644
        os.replace(tmp_name, str(agent_dst))
    except BaseException:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
        raise
    print("wrote %s" % show(agent_dst))
    print("installed beforehand %s" % __version__)
    return 0


def cmd_uninstall(args):
    _, src_agent = locate()
    skill_dst, agent_dst = _targets(args)
    ours = src_agent.read_bytes()

    if skill_dst.is_symlink():
        raise CliError("uninstall: refused: %s is a symlink (a developer checkout is never removed)"
                       % show(skill_dst))
    if skill_dst.exists() and (not skill_dst.is_dir() or not (skill_dst / MARKER).is_file()):
        raise CliError("uninstall: refused: %s was not installed by beforehand (no %s marker)"
                       % (show(skill_dst), MARKER))
    if agent_dst.is_symlink() or (agent_dst.exists() and
                                  (not agent_dst.is_file() or agent_dst.read_bytes() != ours)):
        raise CliError("uninstall: refused: %s differs from the one beforehand %s ships; remove it by "
                       "hand if it is yours to remove" % (show(agent_dst), __version__))

    removed = 0
    if skill_dst.exists():
        shutil.rmtree(str(skill_dst))
        print("removed %s/" % show(skill_dst))
        removed += 1
    if agent_dst.exists():
        agent_dst.unlink()
        print("removed %s" % show(agent_dst))
        removed += 1
    if not removed:
        print("uninstall: nothing to remove (no %s, no %s)" % (show(skill_dst), show(agent_dst)))
    return 0


def cmd_bundle(args):
    """beforehand-<version>.skill: the layout of dev/build_skill.sh — a zip of the skill rooted
    at beforehand/, directory entries included, __pycache__/.pyc/.DS_Store excluded."""
    src_skill, _ = locate()
    out_dir = Path(args.out).expanduser() if args.out else Path.cwd()
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / ("%s-%s.skill" % (NAME, __version__))
    dirs, files = _skill_files(src_skill)
    fd, tmp_name = tempfile.mkstemp(prefix=".%s-bundle-" % NAME, dir=str(out_dir))
    os.close(fd)
    try:
        with zipfile.ZipFile(tmp_name, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(str(src_skill), NAME + "/")
            for d in dirs:
                zf.write(str(src_skill / d), "%s/%s/" % (NAME, d))
            for f in files:
                zf.write(str(src_skill / f), "%s/%s" % (NAME, f))
        os.replace(tmp_name, str(out))
    except BaseException:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
        raise
    print("wrote %s (%d files)" % (show(out), len(files)))
    return 0


def passthrough(argv):
    src_skill, _ = locate()
    entry = src_skill / "scripts" / "beforehand.py"
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    return subprocess.call([sys.executable, str(entry)] + list(argv), env=env)


def _parser(prog, with_update=False, dirs=True, out=False):
    p = argparse.ArgumentParser(prog=prog)
    if with_update:
        p.add_argument("--update", action="store_true", help="replace a previous install")
    if dirs:
        p.add_argument("--skills-dir", metavar="DIR", help="default: ~/.claude/skills")
        p.add_argument("--agents-dir", metavar="DIR", help="default: ~/.claude/agents")
    if out:
        p.add_argument("--out", metavar="DIR", help="default: the current directory")
    return p


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    if not argv:
        print(USAGE)
        return 1
    head, rest = argv[0], argv[1:]
    try:
        if head in ("-h", "--help"):
            print(USAGE)
            return 0
        if head in ("-V", "--version"):
            print("beforehand %s" % __version__)
            return 0
        if head == "install":
            return cmd_install(_parser("beforehand install", with_update=True).parse_args(rest))
        if head == "uninstall":
            return cmd_uninstall(_parser("beforehand uninstall").parse_args(rest))
        if head == "bundle":
            return cmd_bundle(_parser("beforehand bundle", dirs=False, out=True).parse_args(rest))
        if head == "help":
            return passthrough(["--help"])
        return passthrough(argv)
    except CliError as e:
        print(str(e), file=sys.stderr)
        return 1
    except SystemExit as e:  # argparse usage errors: exit 1, as every refusal
        code = e.code if isinstance(e.code, int) else 1
        return 0 if code == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
