#!/usr/bin/env python3
"""Save a source (mail body, transcript, note) as an intact local file with a provenance header.

Why this exists: the authoring rule says every source must be a local file before anything is
extracted from it, byte for byte. Doing that by hand is friction, and friction produced Fact
tags that cited identifiers instead of paths. This script makes the rule the easy path.

Usage:
  save_source.py --dir DIR [--from FILE] [--date YYYY-MM-DD] [--what slug] [--ref TEXT]
                 [--type T] [--provenance P] [--author A] [--channel C] [--store PATH]
                 [--seq] [--keep-extension] [--force] [--force-in-repo] [--json]
  save_source.py --verify FILE

Writes DIR/YYYY-MM-DD-<slug>.md as:   ---\\n<header>\\n---\\n<body bytes unchanged>
The extension normalises to .md — the saved copy is a markdown-framed record whose body is
byte-faithful, so (date, slug) is the identity the no-overwrite and --seq checks see, and
the same text saved on stdin and again with --from x.txt is one file, not two.
--keep-extension keeps the --from file's extension instead.
Prints the absolute path, then a ready-to-paste tag fragment.
Exit codes: 0 ok · 1 usage · 2 exists with different content · 3 inside a personas store
            4 inside a git work tree and not ignored (use --force-in-repo)
"""
import argparse
import datetime as dt
import hashlib
import json
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True  # G5, FR-2.6: run directly, this must land before any sibling import

from pathlib import Path  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from personas_lib import parse_iso_date, read_text_lenient, resolve_store  # noqa: E402

SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
TYPES = ("private-communication", "public-statement", "second-hand")
PROVS = ("human-authored", "machine-transcribed", "post-review")
DERIVED_MARK = "derived file: regenerate with scripts/reindex.py"


class Refused(Exception):
    """Raised by die() instead of exiting the process; main() converts it to a return code.

    die() is called from nested helpers (refuse_if_store), not only from main() itself, so
    a bare return-code convention would not unwind the call stack; an exception does.
    """
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def die(code, msg):
    print(msg, file=sys.stderr)
    raise Refused(code)


def slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:60].rstrip("-") or "source"


def looks_like_store_or_context(p: Path) -> bool:
    idx = p / "INDEX.md"
    if idx.is_file():
        try:
            if DERIVED_MARK in read_text_lenient(idx):
                return True
        except OSError:
            pass
    return (p / "personas").is_dir() and (p / "calibration").is_dir()


def refuse_if_store(dest: Path, store: Path):
    dest_r, store_r = dest.resolve(), store.expanduser().resolve()
    if dest_r == store_r or store_r in dest_r.parents:
        die(3, f"refused: {dest} is inside the personas store {store_r}; sources never live in the store")
    for anc in (dest_r, *dest_r.parents):
        if anc.name == ".beforehand":
            die(3, f"refused: {dest} is under a '.beforehand' directory; sources never live in the store")
        if looks_like_store_or_context(anc):
            die(3, f"refused: {anc} looks like a personas store or context; "
                   "save sources in your project instead")


def git_root(p: Path):
    # p may not exist yet (checked before mkdir): walk from the nearest existing ancestor.
    start = p if p.exists() else next(a for a in p.parents if a.exists())
    for anc in (start, *start.parents):
        if (anc / ".git").exists():
            return anc
    return None


def _is_ignored_minimal(root: Path, target: Path) -> bool:
    """Fallback .gitignore check, used only when git itself is unavailable: a rule equal to
    the relative dir (with or without trailing /), or a leading path component of it, or the
    file's relative path. Approximate on purpose — it does not know about negation
    (`!pattern`) or globs; `git check-ignore` (is_ignored, above) is exact and is always
    preferred. Good enough to protect the common case; --force-in-repo exists for the rest."""
    gi = root / ".gitignore"
    if not gi.is_file():
        return False
    rel = target.resolve().relative_to(root.resolve()).as_posix()
    rules = [ln.strip().strip("/") for ln in read_text_lenient(gi).splitlines()
             if ln.strip() and not ln.startswith("#")]
    parts = rel.split("/")
    for r in rules:
        if r == rel or any("/".join(parts[:i]) == r for i in range(1, len(parts) + 1)):
            return True
    return False


def is_ignored(root, target):
    """Whether `target` (the file about to be written) is ignored by git in `root`'s work
    tree. `git check-ignore` is the real thing: it understands negation (`!pattern`) and
    globs the way git itself does, which a hand-rolled check cannot. It is asked about the
    target FILE, not the destination directory, so a directory-wide ignore rule with a
    file-level negation on the specific file being written is honoured correctly. Falls back
    to the minimal check when git is not on PATH, or when `check-ignore` could not answer at
    all (its exit codes are only 0/1 for an answer; anything else — e.g. 128, not a git work
    tree — means the question was not actually answered, not that the file is not ignored)."""
    if shutil.which("git"):
        r = subprocess.run(["git", "-C", str(root), "check-ignore", "-q", str(target)], capture_output=True)
        if r.returncode in (0, 1):
            return r.returncode == 0
        print("warning: approximate .gitignore check (git check-ignore unavailable)", file=sys.stderr)
    else:
        print("warning: approximate .gitignore check (git not found)", file=sys.stderr)
    return _is_ignored_minimal(root, target)


def _dir_broadly_ignored(root, dest_dir):
    """Best-effort: is this directory's contents ignored in general — as opposed to this
    one file happening to be exempted by a `!pattern` negation elsewhere in .gitignore?
    Used only to choose which refusal hint to print (never for the accept/refuse decision
    itself, which always checks the actual target file). `git check-ignore` treats an
    explicit trailing slash as "this directory": under a `dir/*`-style pattern that itself
    does not match the bare directory path, appending `/` still reports it as ignored,
    which is the answer this question actually wants. Conservatively False without git."""
    if not shutil.which("git"):
        return False
    r = subprocess.run(["git", "-C", str(root), "check-ignore", "-q", str(dest_dir.resolve()) + "/"],
                       capture_output=True)
    return r.returncode == 0


def parse_saved(raw: bytes):
    if not raw.startswith(b"---\n"):
        return None, None
    i = raw.find(b"\n---\n", 4)
    if i < 0:
        return None, None
    header, body = raw[4:i].decode("utf-8", "replace"), raw[i + 5:]
    fields = {}
    for line in header.splitlines():
        k, _, v = line.partition(":")
        fields[k.strip()] = v.strip().strip('"')
    return fields, body


def _report_existing(target: Path, sha: str, a, date: str) -> bool:
    """`target` already exists: same content is idempotent success (prints the existing
    file's own header and returns True); different content is refused (2, via die -> raises
    Refused). Shared by the up-front exists() check and the FileExistsError race
    `open(target, "xb")` catches (F4), so both paths make exactly the same decision."""
    old_fields, old_body = parse_saved(target.read_bytes())
    if old_fields is not None and hashlib.sha1(old_body).hexdigest() == sha:
        if a.json:
            print(json.dumps({"path": str(target), **old_fields}, ensure_ascii=False))
        else:
            print(target)
            print(tag_line(target, old_fields.get("type", a.type),
                            old_fields.get("provenance", a.provenance), old_fields.get("date", date)))
        return True
    old_sha8 = (old_fields or {}).get("sha1", "?")[:8]
    die(2, f"refused: {target} exists with different content (existing sha1 {old_sha8}, "
           f"new {sha[:8]}); use a distinct --what, or --seq to number it, or --force to replace it")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir")
    ap.add_argument("--from", dest="from_file")
    ap.add_argument("--date")
    ap.add_argument("--what")
    ap.add_argument("--ref", default="")
    ap.add_argument("--type", default="private-communication", choices=TYPES)
    ap.add_argument("--provenance", default="human-authored", choices=PROVS)
    ap.add_argument("--author", default="")
    ap.add_argument("--channel", default="")
    ap.add_argument("--store", default=None)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--force-in-repo", action="store_true")
    ap.add_argument("--seq", action="store_true",
                    help="on a name collision with different content, append -2, -3 ... instead of refusing")
    ap.add_argument("--keep-extension", action="store_true",
                    help="keep the --from file's extension instead of .md")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--verify")
    a = ap.parse_args(argv)
    try:
        return _run(a)
    except Refused as e:
        return e.code


def _run(a):
    if a.verify:
        verify_path = Path(a.verify)
        if not verify_path.is_file():
            die(1, f"--verify: file not found: {a.verify}")
        raw = verify_path.read_bytes()
        fields, body = parse_saved(raw)
        if fields is None:
            die(1, "not a save_source file (no header)")
        ok = fields.get("sha1") == hashlib.sha1(body).hexdigest()
        print("sha1 ok" if ok else "sha1 MISMATCH: body was modified after saving")
        return 0 if ok else 1

    if not a.dir:
        die(1, "usage: --dir DIR is required (or --verify FILE)")
    # A --from save with no --ref still has one provenance hint worth keeping: the name the
    # source arrived under. Validated below with the other header values.
    ref = a.ref or (Path(a.from_file).name if a.from_file else "")
    for v in (ref, a.author, a.channel):
        if "\n" in v or "\r" in v:
            die(1, "header values must be single-line")
        if '"' in v:
            die(1, 'header values must not contain a literal " character')
    if a.from_file:
        from_path = Path(a.from_file)
        if not from_path.is_file():
            die(1, f"--from: file not found: {a.from_file}")
        body = from_path.read_bytes()
    else:
        body = sys.stdin.buffer.read()
    if not body:
        die(1, "empty body: pass text on stdin or --from FILE")
    date = a.date or dt.date.today().isoformat()
    try:
        parse_iso_date(date)
    except ValueError:
        die(1, "--date must be YYYY-MM-DD")
    if a.what:
        if not SLUG_RE.match(a.what) or len(a.what) > 60:
            die(1, "--what must match ^[a-z0-9]+(-[a-z0-9]+)*$ (max 60 chars)")
        slug = a.what
    else:
        first = next((ln for ln in body.decode("utf-8", "replace").splitlines() if ln.strip()), "source")
        slug = slugify(first)
    # The name normalises to .md so that (date, slug) — not (date, slug, ext) — is the
    # identity the no-overwrite check and --seq dedupe see: the same body saved on stdin
    # and again with --from x.txt is one file. The body is untouched either way.
    ext = (Path(a.from_file).suffix.lstrip(".") or "md") if (a.from_file and a.keep_extension) else "md"
    dest_dir = Path(a.dir).expanduser()
    refuse_if_store(dest_dir, resolve_store(a.store))
    target = (dest_dir / f"{date}-{slug}.{ext}").resolve()
    if dest_dir.resolve() not in target.parents:
        die(1, "target escapes --dir")
    root = git_root(dest_dir.resolve())
    if root and not a.force_in_repo and not is_ignored(root, target):
        # Checked against the actual FILE about to be written, not the directory: a
        # directory-wide ignore rule with a file-level negation (`!pattern`) on this
        # specific name is honoured correctly, where a directory-only check could not see it.
        # The hint below picks accordingly: telling the user to ignore the whole directory
        # is wrong advice when the directory is already broadly ignored and it is THIS file,
        # specifically, that a negation rule re-includes.
        rel_dir = dest_dir.resolve().relative_to(root.resolve()).as_posix()
        if _dir_broadly_ignored(root, dest_dir):
            rel_file = target.relative_to(root.resolve()).as_posix()
            die(4, f"refused: {target} is inside the git work tree {root} and not ignored, "
                   f"although {rel_dir}/ is otherwise ignored: a negation rule (`!pattern`) "
                   f"in {root / '.gitignore'} re-includes this specific file.\n"
                   f"Adjust the rule covering {rel_file}, move the file elsewhere, or pass "
                   f"--force-in-repo.")
        die(4, f"refused: {dest_dir} is inside the git work tree {root} and not ignored.\n"
               f"Add this line to {root / '.gitignore'}:\n{rel_dir}/\nor pass --force-in-repo.")
    dest_dir.mkdir(parents=True, exist_ok=True)
    sha = hashlib.sha1(body).hexdigest()
    if a.seq and target.exists() and not a.force:
        # Meeting platforms open every transcript with the same generic heading, so ten
        # sources saved in one sitting derive the same slug. Refusing is safe but it means
        # inventing a --what ten times; --seq numbers them instead. It still never
        # overwrites: an identical body short-circuits below, a different one gets a new name.
        same = None
        for cand in [target] + sorted(dest_dir.glob(f"{date}-{slug}-*.{ext}")):
            fields, old_body = parse_saved(cand.read_bytes())
            if fields is not None and hashlib.sha1(old_body).hexdigest() == sha:
                same = cand
                break
        if same is not None:
            target = same.resolve()          # already saved: hand back the file, do not clone it
        else:
            n = 2
            while (dest_dir / f"{date}-{slug}-{n}.{ext}").exists():
                n += 1
            target = (dest_dir / f"{date}-{slug}-{n}.{ext}").resolve()
    if target.exists() and not a.force:
        if _report_existing(target, sha, a, date):
            return 0
    try:
        body.decode("utf-8")
    except UnicodeDecodeError:
        print("warning: body is not valid UTF-8; saved unchanged, the verifier will decode it as latin-1",
              file=sys.stderr)
    header = {"source_ref": ref, "date": date, "type": a.type, "provenance": a.provenance,
              "author": a.author, "channel": a.channel, "saved_on": dt.date.today().isoformat(),
              "sha1": sha, "schema": "0.1"}
    head = "".join(f'{k}: "{v}"\n' for k, v in header.items())
    payload = b"---\n" + head.encode("utf-8") + b"---\n" + body
    if a.force:
        # --force means "replace whatever is there", so the file may legitimately already
        # exist; the exclusive-create race guard below does not apply here on purpose.
        target.write_bytes(payload)
    else:
        try:
            # F4: exclusive create closes the exists-then-write race. Between the exists()
            # check above and this line, nothing else can have created `target` without
            # this raising FileExistsError instead of the write silently clobbering it.
            with open(target, "xb") as f:
                f.write(payload)
        except FileExistsError:
            # Someone else saved the same source concurrently: replay the exact
            # exists-with-content decision instead of losing that write. _report_existing
            # either returns True (idempotent, handled below) or raises Refused(2).
            if _report_existing(target, sha, a, date):
                return 0
    if a.json:
        print(json.dumps({"path": str(target), **header}, ensure_ascii=False))
    else:
        print(target)
        print(tag_line(target, a.type, a.provenance, date))
    return 0


def tag_line(target: Path, type_: str, provenance: str, date: str) -> str:
    p = str(target)
    if "," in p or " " in p:
        p = f"`{p}`"
    return f"tag: {p}, {type_}, {provenance}, {date}"


if __name__ == "__main__":
    print("deprecated: use beforehand.py save", file=sys.stderr)
    sys.exit(main())
