#!/usr/bin/env python3
"""Tests for save_source.py: byte fidelity, header, refusals, exit codes, verify."""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True  # G5: a suite run on its own leaves no __pycache__

HERE = Path(__file__).parent
S = HERE / "save_source.py"
checks = []


def run(*a, stdin=None, cwd=None):
    return subprocess.run([sys.executable, str(S), *map(str, a)],
                           input=stdin, capture_output=True, cwd=cwd)


base = Path(tempfile.mkdtemp())
srcdir = base / "my sources"
srcdir.mkdir()
payload = (b"Line one\r\nline two with latin-1 byte \xe9 and trailing space \n"
           b"---\nnot a delimiter\nno final newline")
r = run("--dir", srcdir, "--date", "2026-07-03", "--what", "call-with-cfo", "--type", "private-communication",
        "--provenance", "machine-transcribed", "--ref", "thread 42", stdin=payload)
out = r.stdout.decode()
checks.append(("exit 0 on first save", r.returncode == 0, (r.returncode, r.stderr[-300:])))
path = Path(out.splitlines()[0]) if out else None
checks.append(("prints absolute path that exists",
               path is not None and path.is_absolute() and path.is_file(), out))
checks.append(("filename has date, slug, md extension",
               path is not None and path.name == "2026-07-03-call-with-cfo.md", path))
raw = path.read_bytes() if path else b""
body = raw.split(b"\n---\n", 1)[1] if b"\n---\n" in raw else b""
checks.append(("body byte-identical after delimiter", body == payload, body[:80]))
checks.append(("header sha1 matches body", hashlib.sha1(payload).hexdigest().encode() in raw, raw[:400]))
checks.append(("tag line printed with backtick-quoted path (spaces)",
               "tag: `" in out and ", private-communication, machine-transcribed, 2026-07-03" in out, out))
r2 = run("--dir", srcdir, "--date", "2026-07-03", "--what", "call-with-cfo", stdin=payload)
checks.append(("identical re-save exits 0 and prints same path",
               r2.returncode == 0 and r2.stdout.decode().splitlines()[0] == str(path), r2.returncode))
r3 = run("--dir", srcdir, "--date", "2026-07-03", "--what", "call-with-cfo", stdin=b"different")
checks.append(("different body without --force exits 2",
               r3.returncode == 2, (r3.returncode, r3.stderr[-200:])))
r4 = run("--dir", srcdir, "--date", "2026-07-03", "--what", "call-with-cfo", "--force", stdin=b"different")
checks.append(("--force overwrites",
               r4.returncode == 0 and path.read_bytes().endswith(b"different"), r4.returncode))
r5 = run("--verify", path)
checks.append(("--verify ok on intact file", r5.returncode == 0, r5.returncode))
path.write_bytes(path.read_bytes() + b"tampered")
r6 = run("--verify", path)
checks.append(("--verify fails after tampering", r6.returncode == 1, r6.returncode))
r7 = run("--dir", srcdir, "--what", "Bad Slug!", stdin=b"x")
checks.append(("bad slug is a usage error (1)", r7.returncode == 1, r7.returncode))
# refusals: fake store, symlink into it, context dir
store = base / "fakestore"
(store / "acme" / "personas").mkdir(parents=True)
(store / "acme" / "calibration").mkdir()
(store / "INDEX.md").write_text(
    "# Personas — root index\n\n"
    "<!-- derived file: regenerate with scripts/reindex.py, do not hand-edit -->\n")
r8 = run("--dir", store / "acme", "--store", store, stdin=b"x")
checks.append(("--dir inside store exits 3", r8.returncode == 3, (r8.returncode, r8.stderr[-200:])))
link = base / "link"
os.symlink(store / "acme", link)
r9 = run("--dir", link, "--store", store, stdin=b"x")
checks.append(("symlink into store exits 3", r9.returncode == 3, r9.returncode))
ctxlike = base / "ctxlike"
(ctxlike / "personas").mkdir(parents=True)
(ctxlike / "calibration").mkdir()
r10 = run("--dir", ctxlike, "--store", base / "nowhere", stdin=b"x")
checks.append(("directory shaped like a context exits 3", r10.returncode == 3, r10.returncode))
# SPEC-1.0 §7: a directory named like the default store (`.beforehand`) is refused by name
named = base / ".beforehand" / "notes"
named.mkdir(parents=True)
r10b = run("--dir", named, "--store", base / "nowhere", stdin=b"x")
checks.append(("a dir under a `.beforehand` directory exits 3",
               r10b.returncode == 3 and b"'.beforehand' directory" in r10b.stderr,
               (r10b.returncode, r10b.stderr[-200:])))
# repo refusal
repo = base / "repo"
(repo / ".git").mkdir(parents=True)
(repo / "sources").mkdir()
r11 = run("--dir", repo / "sources", "--store", base / "nowhere", "--what", "note", stdin=b"x")
checks.append(("unignored dir in repo exits 4 and prints ignore line",
               r11.returncode == 4 and b"sources/" in r11.stderr, (r11.returncode, r11.stderr[-200:])))
(repo / ".gitignore").write_text("sources/\n")
r12 = run("--dir", repo / "sources", "--store", base / "nowhere", "--what", "note", stdin=b"x")
checks.append(("ignored dir in repo saves", r12.returncode == 0, (r12.returncode, r12.stderr[-200:])))
r13 = run("--dir", repo / "docs", "--store", base / "nowhere", "--what", "note",
          "--force-in-repo", stdin=b"x")
checks.append(("--force-in-repo proceeds",
               r13.returncode == 0, (r13.returncode, r13.stderr[-200:])))
# fix round 1: refused-in-repo save must not create the destination directory first
r14 = run("--dir", repo / "newdir", "--store", base / "nowhere", "--what", "note", stdin=b"x")
checks.append(("unignored newdir exits 4 and is not created",
               r14.returncode == 4 and not (repo / "newdir").exists(),
               (r14.returncode, (repo / "newdir").exists())))
# fix round 1: idempotent re-save tag line and --json must reflect the stored header, not current flags
tagdir = base / "tagdir"
tagdir.mkdir()
rt1 = run("--dir", tagdir, "--date", "2026-08-01", "--what", "note-a",
          "--provenance", "machine-transcribed", stdin=b"same body")
rt2 = run("--dir", tagdir, "--date", "2026-08-01", "--what", "note-a", stdin=b"same body")
checks.append(("idempotent re-save tag line keeps stored provenance", rt2.returncode == 0
               and "machine-transcribed" in rt2.stdout.decode().splitlines()[1], rt2.stdout.decode()))
rt3 = run("--dir", tagdir, "--date", "2026-08-01", "--what", "note-a", "--json", stdin=b"same body")
try:
    rt3_parsed = json.loads(rt3.stdout.decode())
    rt3_ok = rt3.returncode == 0 and "path" in rt3_parsed and "provenance" in rt3_parsed
except json.JSONDecodeError:
    rt3_ok = False
checks.append(("idempotent re-save --json emits JSON with path and provenance", rt3_ok, rt3.stdout.decode()))
# fix round 1: a literal quote in a header value would corrupt the header on read-back
r15 = run("--dir", srcdir, "--what", "quote-test", "--ref", 'thread "42"', stdin=b"x")
checks.append(("ref containing a literal quote is a usage error (1)", r15.returncode == 1, r15.returncode))
# fix round 1: missing --verify file must not raise a raw traceback
r16 = run("--verify", "/nonexistent-file-xyz-12345")
checks.append(("--verify on missing file exits 1 and mentions not found",
               r16.returncode == 1 and b"not found" in r16.stderr.lower(), (r16.returncode, r16.stderr)))
# round trip with verify_quotes: paste the printed path into a Fact tag
rt = run("--dir", srcdir, "--date", "2026-07-04", "--what", "board-note",
         stdin=b"Budget is frozen until March.\n")
p_rt = rt.stdout.decode().splitlines()[0]
persona = base / "persona.md"
persona.write_text(
    f'---\nslug: t\n---\n## Red lines\n- Frozen (Fact — "Budget is frozen until March", '
    f'`{p_rt}`, private-communication, human-authored, 2026-07-04)\n', encoding="utf-8")
vq = subprocess.run([sys.executable, str(HERE / "verify_quotes.py"), str(persona), "--json"],
                    capture_output=True, text=True)
checks.append(("round trip: saved source verifies from a Fact tag", '"status": "VERIFIED"' in vq.stdout,
               vq.stdout[-300:]))

# ---- Step 4: git check-ignore replaces the hand-rolled minimal check (real git, not a
# fake .git marker): a directory-wide ignore with a file-level negation on the SPECIFIC
# name about to be written is honoured, because is_ignored is asked about the target file.
if shutil.which("git"):
    repo2 = base / "repo2"
    subprocess.run(["git", "init", "-q", str(repo2)], check=True)
    (repo2 / "sources").mkdir()
    (repo2 / ".gitignore").write_text("sources/*\n!sources/*-keep.*\n")
    rg1 = run("--dir", repo2 / "sources", "--store", base / "nowhere", "--what", "note", stdin=b"x")
    checks.append(("git check-ignore: an ignored file under a wildcard-ignored dir saves",
                   rg1.returncode == 0, (rg1.returncode, rg1.stderr)))
    rg2 = run("--dir", repo2 / "sources", "--store", base / "nowhere", "--what", "keep", stdin=b"x")
    checks.append(("git check-ignore: a file-level negation is honoured and refused",
                   rg2.returncode == 4, (rg2.returncode, rg2.stderr)))
    checks.append(("git check-ignore: the negation case hints at the file, not 'add dir/ "
                   "to .gitignore' (the directory is already broadly ignored)",
                   b"negation rule" in rg2.stderr and b"Add this line to" not in rg2.stderr, rg2.stderr))
    checks.append(("git check-ignore: the file-level hint names the actual relative path",
                   b"keep.md" in rg2.stderr, rg2.stderr))
else:
    print("ok (skipped: no git)")

# ---- FR-4.2: the saved name normalises to .md, so (date, slug) is the identity ----
extdir = base / "extdir"
extdir.mkdir()
incoming = base / "incoming"
incoming.mkdir()
src_txt = incoming / "notes.txt"
src_txt.write_bytes(b"Body that arrived as a .txt file\r\nsecond line, no final newline")
e1 = run("--dir", extdir, "--date", "2026-09-01", "--what", "ext-note", "--from", src_txt)
p_e1 = Path(e1.stdout.decode().splitlines()[0]) if e1.stdout else None
checks.append(("--from a .txt source is saved as .md",
               e1.returncode == 0 and p_e1 is not None and p_e1.name == "2026-09-01-ext-note.md",
               (e1.returncode, e1.stdout, e1.stderr[-200:])))
checks.append(("the .txt body survives the rename byte for byte",
               p_e1 is not None and p_e1.read_bytes().split(b"\n---\n", 1)[1] == src_txt.read_bytes(),
               p_e1))
e2 = run("--verify", p_e1)
checks.append(("--verify on the normalised .md file exits 0", e2.returncode == 0,
               (e2.returncode, e2.stdout)))
e3 = run("--dir", extdir, "--date", "2026-09-01", "--what", "ext-keep", "--from", src_txt,
         "--keep-extension", "--json")
try:
    e3_parsed = json.loads(e3.stdout.decode())
except json.JSONDecodeError:
    e3_parsed = {}
checks.append(("--keep-extension keeps the --from file's extension",
               e3.returncode == 0 and Path(e3_parsed.get("path", "")).name == "2026-09-01-ext-keep.txt",
               (e3.returncode, e3.stdout)))
checks.append(("--ref omitted on a --from save records the source's own name",
               e3_parsed.get("source_ref") == "notes.txt", e3_parsed))
# the same body on stdin and then through --from is one file, not two
dupdir = base / "dupdir"
dupdir.mkdir()
d1 = run("--dir", dupdir, "--date", "2026-09-02", "--what", "dupe", stdin=src_txt.read_bytes())
d2 = run("--dir", dupdir, "--date", "2026-09-02", "--what", "dupe", "--from", src_txt)
checks.append(("the same body saved on stdin and then with --from is one file",
               d2.returncode == 0
               and d2.stdout.decode().splitlines()[0] == d1.stdout.decode().splitlines()[0]
               and len(list(dupdir.iterdir())) == 1,
               (d2.returncode, sorted(p.name for p in dupdir.iterdir()))))
other_txt = incoming / "other.txt"
other_txt.write_bytes(b"A different body under the same date and slug.\n")
d3 = run("--dir", dupdir, "--date", "2026-09-02", "--what", "dupe", "--from", other_txt, "--seq")
checks.append(("--seq on a collision with a .txt source numbers a .md file",
               d3.returncode == 0
               and Path(d3.stdout.decode().splitlines()[0]).name == "2026-09-02-dupe-2.md",
               (d3.returncode, d3.stdout, d3.stderr[-200:])))

# ---- F3: --date rejects the compact form on every interpreter, via personas_lib.parse_iso_date
# (date.fromisoformat alone accepts "20260922" from Python 3.11 on: the same file would parse
# differently depending on which interpreter ran the check).
compact_dir = base / "compact-date"
compact_dir.mkdir()
rc1 = run("--dir", compact_dir, "--date", "20260922", "--what", "note", stdin=b"x")
checks.append(("--date 20260922 (compact ISO) is refused with the usual message",
               rc1.returncode == 1 and b"--date must be YYYY-MM-DD" in rc1.stderr,
               (rc1.returncode, rc1.stderr)))

# ---- F4: the exists-then-write race is closed by an exclusive create (open(target, "xb")).
# Simulate a concurrent writer that created the target between save_source's exists() check
# and its write: Path.exists is monkeypatched to say "not there yet" for that one target
# (exactly what the check saw an instant before the race), while the file genuinely exists
# on disk with content a real writer already committed. The exclusive create must discover
# the collision itself and route it through the ordinary exists-with-content decision,
# never silently overwriting (data loss) and never losing the raced-in file.
sys.path.insert(0, str(HERE))
from pathlib import Path as _Path  # noqa: E402

import save_source as ss  # noqa: E402

racedir = base / "race"
racedir.mkdir()
raced_target = racedir / "2026-09-10-race-note.md"
winner_body = b"the concurrent writer's body, already committed"
winner_sha = hashlib.sha1(winner_body).hexdigest()
winner_header = {"source_ref": "race", "date": "2026-09-10", "type": "private-communication",
                 "provenance": "human-authored", "author": "", "channel": "",
                 "saved_on": "2026-09-10", "sha1": winner_sha, "schema": "0.1"}
winner_head = "".join(f'{k}: "{v}"\n' for k, v in winner_header.items())
raced_target.write_bytes(b"---\n" + winner_head.encode() + b"---\n" + winner_body)

real_exists = _Path.exists


def _fake_exists(self):
    if self == raced_target:
        return False
    return real_exists(self)


same_body_file = base / "same-body.txt"
same_body_file.write_bytes(winner_body)
diff_body_file = base / "diff-body.txt"
diff_body_file.write_bytes(b"a losing writer's different body")

import contextlib  # noqa: E402
import io  # noqa: E402

_Path.exists = _fake_exists
try:
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        rc_same = ss.main(["--dir", str(racedir), "--date", "2026-09-10", "--what", "race-note",
                           "--from", str(same_body_file)])
    checks.append(("F4 race, same content: the raced-in file is recognised, not clobbered (exit 0)",
                   rc_same == 0 and raced_target.read_bytes().endswith(winner_body),
                   (rc_same, raced_target.read_bytes()[-80:])))
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        rc_diff = ss.main(["--dir", str(racedir), "--date", "2026-09-10", "--what", "race-note",
                           "--from", str(diff_body_file)])
    checks.append(("F4 race, different content: refused (exit 2), the raced-in file survives intact",
                   rc_diff == 2 and raced_target.read_bytes().endswith(winner_body),
                   (rc_diff, raced_target.read_bytes()[-80:])))
finally:
    _Path.exists = real_exists

fails = [c for c in checks if not c[1]]
for n, ok, got in checks:
    print(("ok   " if ok else "FAIL ") + n + ("" if ok else f" -> {str(got)[:300]}"))
print(f"\n{len(checks)-len(fails)}/{len(checks)} passed")
sys.exit(1 if fails else 0)
