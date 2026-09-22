#!/usr/bin/env python3
"""One parser for every script in this skill: files, frontmatter, sections, Fact tags, store.

Why this module exists. "Find the sections of a persona file" was written five times
(`verify_quotes.shape`, `reindex.section`, `pending.section`, `coverage.sections`,
`watchlist.section_spans`) and the copies had already drifted: two of them stripped the
per-section `<!-- ... -->` note from the heading, three kept it, so the same persona had
two different section names depending on which script read it. Frontmatter was parsed once
and re-regexed elsewhere. A template change — a new heading, a new frontmatter key — has to
be a one-place change, or the scripts keep disagreeing about what a persona is.

Nothing here prints or exits: the CLIs own the output and the exit codes, this owns the
reading. It also offers explicit write primitives (`atomic_write`, `append_line`) that callers
invoke; it never decides to write a store file on its own. The one side effect of importing
it: bytecode writing is turned off for everything imported after it (G5).

Frontmatter subset (SPEC-0.2 FR-4.8). Accepted: `key: value` scalars, inline lists
`[a, b, "c, d"]`, a trailing `# comment` on a scalar. Refused, with the line number:
block lists (`- item`), nested maps (any indented line), and anything that is not a
`key: value` pair. A hand-rolled YAML parser is acceptable only if what it does not parse
is reported rather than silently dropped — that report is `FrontmatterError`.
"""
import sys

# First, before any other import (G5, FR-2.6): __pycache__ in the skill folder embeds this
# machine's absolute path. Every script module under scripts/ also sets this itself right
# after `import sys`, before importing this one, so no module's cache file (this one's
# included) is ever written; this line covers anything imported through the library alone.
sys.dont_write_bytecode = True

import copy  # noqa: E402
import datetime  # noqa: E402
import functools  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402
import stat  # noqa: E402
import tempfile  # noqa: E402
from pathlib import Path  # noqa: E402

SCHEMA_VERSION = "0.2"

__all__ = [
    "SCHEMA_VERSION", "FrontmatterError", "decode_lenient", "read_text_lenient",
    "frontmatter_span", "read_frontmatter", "strip_frontmatter", "schema_of", "Section", "sections",
    "section_body", "parse_tags", "paren_groups", "split_top_level", "item_start",
    "item_end", "resolve_reference", "ref_candidates", "resolve_candidate", "unquote_ref",
    "resolve_sources_root", "resolve_store", "rel", "Store",
    "QUOTE_RE", "DATE_RE", "KEYWORD_RE", "PATHLIKE_RE", "TEXT_EXT",
    "REF_QUOTES", "ONLY_GLUE_RE", "FACT_LABEL_RE", "HEADING_RE", "HEADING_NOTE_RE",
    "DEFAULT_STORE", "STORE_ENV",
    "LocaleError", "load_locale", "get_locale", "locale_regexes", "LOCALE_ENV",
    "LOCALE_DIR_ENV",
    # 0.3.1 (SPEC-0.3.1 FR-1.2, FR-1.3, FR-2.5)
    "resolve_source", "source_header_span", "parse_iso_date", "atomic_write", "append_line",
    "check_locale", "SOURCE_NOT_UNDER_ROOT", "persona_store", "persona_sources_root",
]


# --------------------------------------------------------------------------- locale
class LocaleError(ValueError):
    """`load_locale` was asked for a code nothing ships (FR-4.4). Carries what IS available
    so a typo (or a locale never packaged) is reported instead of silently running in
    English or crashing with a bare traceback."""

    def __init__(self, code, available):
        super().__init__("unknown locale %r (available: %s)" % (code, ", ".join(available)))
        self.code = code
        self.available = available


LOCALE_ENV = "BEFOREHAND_LOCALE"
LOCALE_DIR_ENV = "BEFOREHAND_LOCALE_DIR"
_LOCALES_DIR = Path(__file__).resolve().parent / "locales"


def _locale_env_dir():
    """$BEFOREHAND_LOCALE_DIR as it is right now, "" when unset. Read at call time and carried
    into every locale cache key: the same code resolves to different data when the search
    path changes, so a cache keyed on the code alone would keep serving the first directory
    the process happened to see."""
    return os.environ.get(LOCALE_DIR_ENV) or ""


def _locale_search_dirs(extra_dir=""):
    """scripts/locales/ (shipped), then `extra_dir` — the $BEFOREHAND_LOCALE_DIR of the call,
    where a test or a deployment keeps locales that are not shipped (this is how the `xx`
    test locale is reached). Passed in rather than read here so the callers that are cached
    have the directory in their key."""
    dirs = [_LOCALES_DIR]
    if extra_dir:
        dirs.append(Path(extra_dir).expanduser())
    return dirs


def _available_locales(extra_dir=""):
    codes = {"en"}
    for d in _locale_search_dirs(extra_dir):
        if d.is_dir():
            codes.update(p.stem for p in d.glob("*.json"))
    return sorted(codes)


def _read_locale(code, extra_dir=""):
    for d in _locale_search_dirs(extra_dir):
        p = d / (code + ".json")
        if p.is_file():
            return json.loads(p.read_text(encoding="utf-8"))
    return None


@functools.lru_cache(maxsize=None)
def _locale_dict_cached(code, extra_dir):
    """The real load+merge, cached per (resolved code, locale directory) pair: a cache miss
    reads the two JSON files at most once per pair, ever, for the life of the process. The
    directory belongs in the key because it is what the code is resolved against — cached on
    the code alone, a process that pointed BEFOREHAND_LOCALE_DIR somewhere else after the first
    call kept the old file's word lists."""
    base = _read_locale("en", extra_dir) or {}
    if code == "en":
        return base
    extra = _read_locale(code, extra_dir)
    if extra is None:
        raise LocaleError(code, _available_locales(extra_dir))
    merged = {}
    for key, val in base.items():
        merged[key] = dict(val) if isinstance(val, dict) else list(val)
    for key, val in extra.items():
        if isinstance(val, dict):
            dest = merged.setdefault(key, {})
            for sub, items in val.items():
                dest[sub] = dest.get(sub, []) + list(items)
        else:
            merged[key] = merged.get(key, []) + list(val)
    return merged


def _locale_dict(code):
    """Thin wrapper: reads BEFOREHAND_LOCALE_DIR at call time and hands it to the cache."""
    return _locale_dict_cached(code, _locale_env_dir())


def get_locale(code=None):
    """-> dict of locale-driven word lists (FR-4.4): `same_source`, `empty_section`,
    `generic_speaker`, `header_labels`, `snapshot_fields`, `watchlist_repeat_clause`,
    `excerpt_joiners`, `filler_tokens`. The result is the caller's own copy: mutate it freely.

    English is always loaded first. `code` (or BEFOREHAND_LOCALE when `code` is None, or
    "en" when neither is set) selects what is merged on top: a non-English locale file
    only has to state what it ADDS to English, never repeat it, so it stays small and a
    reviewer can see at a glance what a locale changes. An unknown code raises
    LocaleError naming what is available, rather than running in English with no signal
    that the requested locale never loaded.

    Resolved LAZILY: BEFOREHAND_LOCALE is read HERE, at call time, never once at this
    module's own import — personas_lib is typically imported once, early, by whatever
    first needed `resolve_store` (e.g. beforehand.py's own top-of-file import, which runs
    before its `main()` parses --locale and exports BEFOREHAND_LOCALE for the command it is
    about to dispatch), so anything resolved only at that first import would never see a
    locale requested later on the same command line. Every call after the first, for a
    given resolved code and locale directory, is a cache lookup (functools.lru_cache on
    `(code, $BEFOREHAND_LOCALE_DIR)`), not a re-read of the locale files."""
    code = code or os.environ.get(LOCALE_ENV) or "en"
    # A deep copy (B6): the cached dict is shared by every caller in the process, and one
    # caller appending to a list would silently change what every later caller reads.
    return copy.deepcopy(_locale_dict(code))


load_locale = get_locale  # kept as an alias: pre-existing call sites are unaffected


@functools.lru_cache(maxsize=None)
def _locale_regex_bundle_cached(code, extra_dir):
    L = _locale_dict_cached(code, extra_dir)
    join_alt = "|".join(re.escape(w) for w in L["excerpt_joiners"])
    generic_alt = "|".join(re.escape(w) for w in L["generic_speaker"])
    empty_alt = "|".join(re.escape(p) for p in L["empty_section"])
    repeat_alt = "|".join(re.escape(w) for w in L["watchlist_repeat_clause"])
    return {
        # `same_source` is a list of regex alternatives (locale data), not literal words:
        # joined as-is, unescaped.
        "same_source_re": re.compile(r"^(" + "|".join(L["same_source"]) + r")$", re.I),
        "leading_join_re": (re.compile(r'^""\s*(?:' + join_alt + r')?\s*') if join_alt
                            else re.compile(r'^""\s*')),
        "generic_re": re.compile(r"^(" + generic_alt + r")\b[\s._#-]*\d*$", re.I),
        # An unidentified-participant marker inside a turn: a generic label, or a
        # phone-shaped number (F2, FR-2.7) — at least 7 digits (a masked `*` counts as a
        # digit), not grouped as thousands (`1.200.000:` is an amount), and only at the start
        # of a line or right after a bracket, where a dial-in label sits.
        "inline_unident_re": re.compile(
            r"(?m)((?:^[ \t]*|(?<=[(\[]))[+(]?"
            r"(?!\d{1,3}(?:[.,]\d{3})+[)\]]?[ \t]*:)"
            r"(?=(?:[ \t().+-]*[\d*]){7})"
            r"[\d*](?:[\d* \t().+-]*[\d*])?[)\]]?"
            r"|(?:^|(?<=[\s(\[*]))(?:" + generic_alt + r")[\s._#-]*\d*)\s*:", re.I),
        "header_labels": frozenset(L["header_labels"]),
        "empty_decl_re": re.compile(r"(" + empty_alt + r")\s*\d{4}-\d{2}-\d{2}", re.I),
        "repeat_clause_re": re.compile(r"(" + repeat_alt + r")", re.I),
        # its own copy: never the object the dictionary cache (and get_locale) is built from
        "snapshot_fields": copy.deepcopy(L["snapshot_fields"]),
        "filler_tokens": frozenset(w.lower() for w in L.get("filler_tokens", [])),
    }


def _locale_regex_bundle(code):
    """Thin wrapper: same (code, BEFOREHAND_LOCALE_DIR) key as the dictionary cache."""
    return _locale_regex_bundle_cached(code, _locale_env_dir())


def check_locale():
    # type: () -> Optional[str]
    """-> the error message for an unknown BEFOREHAND_LOCALE (the LocaleError text), or None.

    One copy of what reindex, migrate, watchlist and doctor each did by hand: validate the
    locale once, after argparse (so `--help` still works under a typo), and let the CLI
    decide how to report it. Never prints, never exits."""
    try:
        locale_regexes()
    except LocaleError as e:
        return str(e)
    return None


def locale_regexes(code=None):
    """-> dict of every locale-derived regex (or word-set) a module needs — same-source
    shorthand, excerpt joiners, generic-speaker labels, header labels, the declared-empty
    phrase, the Watchlist "if it repeats" clause, and the snapshot field names — built and
    cached lazily per resolved code, exactly like get_locale() (see its docstring for why
    lazy) — the cache key is (resolved code, $BEFOREHAND_LOCALE_DIR), so pointing the
    environment at another locale directory mid-process is honoured instead of silently
    reusing the first one. One place builds every pattern that used to be hardcoded per
    language and duplicated per module; a caller only needs the key it wants."""
    code = code or os.environ.get(LOCALE_ENV) or "en"
    return _locale_regex_bundle(code)


# --------------------------------------------------------------------------- files
def decode_lenient(raw):
    """Bytes -> str, utf-8 (a leading BOM dropped) with a latin-1 fallback.

    A source saved by another tool is not always utf-8, and refusing to read it would mean
    reporting every excerpt in it as unverifiable — a decoding detail reported as a
    fabrication risk.
    """
    try:
        # utf-8-sig (B2): a BOM would otherwise sit in front of `---` and hide the
        # frontmatter; for text without a BOM it is plain utf-8.
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


def read_text_lenient(path):
    """-> str. utf-8, latin-1 fallback."""
    return decode_lenient(Path(path).read_bytes())


def atomic_write(path, text):
    """Replace `path` with `text` (UTF-8, newlines exactly as given) or leave it untouched.

    Written to a temp file in the same directory, fsync'd, then `os.replace`d over the target
    (S3): a crash or a full disk mid-write can no longer leave a store file half-written. The
    existing file's permission bits are kept; a new file gets the umask default. A symlinked
    target is written through (the link stays a link). The directory must exist: the library
    never creates store layout."""
    target = Path(path)
    if target.is_symlink():
        target = target.resolve()
    mode = None
    try:
        mode = stat.S_IMODE(os.stat(str(target)).st_mode)
    except OSError:
        umask = os.umask(0)
        os.umask(umask)
        mode = 0o666 & ~umask
    fd, tmp = tempfile.mkstemp(dir=str(target.parent), prefix="." + target.name + ".",
                               suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, str(target))
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def append_line(path, line):
    """Append `line + "\n"` to `path` (created if missing), UTF-8.

    If the file is non-empty and does not end in a newline (a hand-edited ledger), a `"\n"`
    is written first, so the new row can never be glued onto the last one (S3, E5)."""
    p = Path(path)
    lead = ""
    try:
        with open(str(p), "rb") as f:
            f.seek(0, os.SEEK_END)
            if f.tell() > 0:
                f.seek(-1, os.SEEK_END)
                if f.read(1) != b"\n":
                    lead = "\n"
    except FileNotFoundError:
        pass
    with open(str(p), "a", encoding="utf-8", newline="") as f:
        f.write(lead + line + "\n")


_ISO_DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


def parse_iso_date(s):
    """`YYYY-MM-DD` -> datetime.date; ValueError for anything else (S4, F3).

    `date.fromisoformat` alone accepts `20260922` from 3.11 on and refuses it on 3.9/3.10,
    so the same file read differently per interpreter; the shape is checked first."""
    if not isinstance(s, str) or not _ISO_DATE_RE.fullmatch(s):
        raise ValueError("not a YYYY-MM-DD date: %r" % (s,))
    return datetime.date.fromisoformat(s)


# --------------------------------------------------------------------------- frontmatter
class FrontmatterError(ValueError):
    """Frontmatter outside the FR-4.8 subset, with the line it happened on.

    Carries `line_no` (1-based, counted in the whole file) and `reason` so a caller can say
    where to look instead of dropping the key.
    """

    def __init__(self, line_no, reason):
        super().__init__("line %d: %s" % (line_no, reason))
        self.line_no = line_no
        self.reason = reason


def frontmatter_span(text):
    """-> (start, end) of the leading `---` block, delimiters included, or None.

    Line-based rather than one regex: the three regexes this replaces disagreed about
    carriage returns and about a block with no keys in it.

    This is the persona / context.md reader. A file that is ONLY a block (a minimal
    context.md) is a block (B1): its fields are real. Sources are not read through this —
    `source_header_span` recognises the header `save` writes and nothing else.
    """
    if not text.startswith("---"):
        return None
    lines = text.split("\n")
    if lines[0].rstrip() != "---":
        return None
    pos = len(lines[0]) + 1
    for line in lines[1:]:
        end = pos + len(line) + 1
        if line.rstrip() == "---":
            return 0, min(end, len(text))
        pos = end
    return None


_HEADER_LINE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*[ \t]*:")


def source_header_span(text):
    """-> (start, end) of the provenance header `save` writes, or None (A7, FR-1.3).

    That header is a leading `---` block whose every non-blank line is `key: value` and which
    carries both `sha1` and `source_ref`. Anything else — a source whose first line is a
    `---` rule, a pasted YAML-ish block — is source text, and stripping it would hide the
    very words an excerpt is checked against."""
    span = frontmatter_span(text)
    if not span:
        return None
    keys = set()
    for line in text[span[0]:span[1]].split("\n")[1:]:
        line = line.rstrip("\r")
        if line.rstrip() == "---":
            break
        if not line.strip():
            continue
        m = _HEADER_LINE_RE.match(line)
        if not m:
            return None
        keys.add(line.split(":", 1)[0].strip())
    return span if {"sha1", "source_ref"} <= keys else None


def strip_frontmatter(text):
    """Source text without its `save` header (and only that: see source_header_span)."""
    span = source_header_span(text)
    return text[span[1]:] if span else text


def _split_inline_list(s):
    """Split on commas that are not inside quotes, so `[a, "b, c"]` stays two items."""
    parts, buf, q = [], [], None
    for ch in s:
        if q:
            if ch == q:
                q = None
            buf.append(ch)
        elif ch in "\"'":
            q = ch
            buf.append(ch)
        elif ch == ",":
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    parts.append("".join(buf))
    return parts


def _strip_comment(val):
    """Drop a trailing `# comment` from a frontmatter value, never a `#` inside quotes (B3).

    A quote opens only where a scalar or a list item can start (after `:`/start, `[` or `,`,
    spaces allowed), so an apostrophe inside a plain word (`CTO's`) is not a quote."""
    q = None
    prev = ""        # last non-space character seen outside quotes
    for i, ch in enumerate(val):
        if q:
            if ch == q:
                q = None
                prev = ch
            continue
        if ch in "\"'" and prev in ("", "[", ","):
            q = ch
            continue
        if ch == "#" and i > 0 and val[i - 1] in " \t":
            return val[:i].rstrip()
        if not ch.isspace():
            prev = ch
    return val


def read_frontmatter(text):
    """-> dict of the leading `---` block; {} when there is none.

    Values are strings, or a list of strings for an inline list. Raises FrontmatterError
    (with the line number) on anything outside the subset documented at the top of this
    module.
    """
    span = frontmatter_span(text)
    if not span:
        return {}
    lines = text[span[0]:span[1]].split("\n")
    if lines[-1] == "":
        lines.pop()                 # the span ends just after the closing delimiter's newline
    fm = {}
    # line numbers are counted in the whole file, and a frontmatter block starts at line 1
    for line_no, raw in enumerate(lines[1:-1], start=2):
        line = raw.rstrip("\r")
        if not line.strip():
            continue
        if line[0] in " \t":
            raise FrontmatterError(
                line_no, "indented line: nested maps and multi-line values are outside the "
                         "frontmatter subset (FR-4.8)")
        stripped = line.strip()
        if re.match(r"-(\s|$)", stripped):
            raise FrontmatterError(
                line_no, "block list item: write it as an inline list `key: [a, b]` "
                         "(FR-4.8 accepts no block lists)")
        if stripped.startswith("#"):
            continue
        if ":" not in line:
            raise FrontmatterError(line_no, "not a `key: value` line: %r" % stripped[:60])
        key, _, val = line.partition(":")
        val = _strip_comment(val).strip()   # strip a trailing "# (comment)" outside quotes
        if val.startswith("[") and val.endswith("]"):
            items = [v.strip().strip("\"'") for v in _split_inline_list(val[1:-1])]
            fm[key.strip()] = [v for v in items if v]
        else:
            fm[key.strip()] = val.strip("\"'")
    return fm


_SCHEMA_LINE_RE = re.compile(r"(?m)^schema:[ \t]*(\S+)[ \t]*$")


def schema_of(text):
    """-> the declared schema version of a store file, or None (FR-7.3).

    Reads `schema:` wherever that file keeps it: the `---` frontmatter of a persona or a
    `context.md`, or the plain `key: value` header of a prediction snapshot, which has no
    frontmatter block at all. One reader for both shapes, because `doctor` reports and
    `migrate` rewrites the same field in files that never agreed on where to put it.

    Never raises: frontmatter outside the FR-4.8 subset (a `schema:` next to a block list)
    still answers here, through the line-level fallback, because a file that cannot be fully
    parsed is exactly the file whose version a caller most needs to know.
    """
    span = frontmatter_span(text)
    if span:
        try:
            value = read_frontmatter(text).get("schema")
        except FrontmatterError:
            value = None
        if value:
            return str(value)
        head = text[span[0]:span[1]]
    else:
        head = text
    m = _SCHEMA_LINE_RE.search(head)
    return m.group(1).strip("\"'") if m else None


# --------------------------------------------------------------------------- sections
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.M)
# personas carry a per-section HTML comment (last evidence, decay): it is not part of the name
HEADING_NOTE_RE = re.compile(r"\s*<!--.*?-->\s*$", re.S)


class Section(object):
    """One heading and the body under it.

    level        number of '#'
    title        heading text with the `<!-- ... -->` note removed
    note         that note, or "" — it is metadata about the section, not its name
    header_start offset of the '#'
    body_start   offset of the first character after the heading line
    end          offset where the next heading starts (or the end of the text)
    """

    __slots__ = ("level", "title", "note", "header_start", "body_start", "end")

    def __init__(self, level, title, note, header_start, body_start, end):
        self.level = level
        self.title = title
        self.note = note
        self.header_start = header_start
        self.body_start = body_start
        self.end = end

    def body(self, text):
        return text[self.body_start:self.end]

    def __repr__(self):
        return "Section(level=%d, title=%r, note=%r, header_start=%d, body_start=%d, end=%d)" % (
            self.level, self.title, self.note, self.header_start, self.body_start, self.end)


def _fenced_offsets(text):
    """-> set of line-start offsets that sit inside (or open/close) a code fence.
    ``` and ~~~ toggle separately: a ~~~ inside a ``` block is text, and vice versa."""
    fenced, fence, pos = set(), None, 0
    for line in text.split("\n"):
        s = line.lstrip()
        marker = "```" if s.startswith("```") else "~~~" if s.startswith("~~~") else None
        if marker and (fence is None or fence == marker):
            fenced.add(pos)
            fence = None if fence else marker
        elif fence:
            fenced.add(pos)
        pos += len(line) + 1
    return fenced


def sections(text):
    """-> [Section] for every heading outside a code fence, in order of appearance (B4)."""
    fenced = _fenced_offsets(text)
    ms = [m for m in HEADING_RE.finditer(text) if m.start() not in fenced]
    out = []
    for i, m in enumerate(ms):
        end = ms[i + 1].start() if i + 1 < len(ms) else len(text)
        raw_title = m.group(2)
        note_m = HEADING_NOTE_RE.search(raw_title)
        out.append(Section(len(m.group(1)),
                           HEADING_NOTE_RE.sub("", raw_title).strip(),
                           note_m.group(0).strip() if note_m else "",
                           m.start(), min(m.end() + 1, end), end))
    return out


def section_body(text, title, level=None):
    """Body of a `##`/`###` section, by title, case-insensitively. None when absent.

    Built on `sections()` (B4), so a heading inside a ``` or ~~~ fence is text, and the
    title is compared without its `<!-- ... -->` note. Ends at the next `##`/`###` heading of
    the same or a higher level; `level` (2 or 3) narrows which heading may open it. The body
    is the lines after the heading line, joined with "\n" (no trailing newline).
    """
    heads = [s for s in sections(text) if s.level in (2, 3)]
    want = title.strip().lower()
    for i, s in enumerate(heads):
        if s.title.lower() != want or (level is not None and s.level != level):
            continue
        nl = text.find("\n", s.header_start)
        start = len(text) if nl < 0 else nl + 1
        end = len(text)
        for nxt in heads[i + 1:]:
            if nxt.level <= s.level:
                end = nxt.header_start
                break
        return "\n".join(text[start:end].splitlines())
    return None


# --------------------------------------------------------------------------- Fact tags
QUOTE_RE = re.compile(r"[\"“”]([^\"“”]+)[\"“”]")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$|^\d{1,2}/\d{1,2}(/\d{2,4})?$|^\d{4}(-\d{2})?$")
# A label keyword only as the whole field, or followed by `:`/whitespace (A5): `fact-sheet.txt`
# and `type-a/notes.md` are refs, not labels. parse_tags also never drops a PATHLIKE field.
KEYWORD_RE = re.compile(
    r"^(fact|inference|assumption|private-communication|public-statement|second-hand|"
    r"human-authored|machine-transcribed|post-review|type|provenance)(?=\s*$|[\s:])", re.I)
# `same_source` (SAME_SOURCE_RE) and the excerpt-joiner regex used below are locale data
# (FR-4.4) and are built lazily, per call, by `locale_regexes()` (see the locale section
# above) — never as module-level constants, so a locale requested after this module was
# first imported is still honoured.
TEXT_EXT = r"(md|markdown|txt|text|json|csv|html?|eml|msg|mbox|rtf|vtt|srt|log)"
PATHLIKE_RE = re.compile(r"(^https?://|/|\\|^~|^\.\.?[/\\]|^[A-Za-z]:[\\/]|\." + TEXT_EXT + r"$)", re.I)
REF_QUOTES = "`'<>"
# What may sit between a quote and the tag that follows it for the pair to read as one unit.
ONLY_GLUE_RE = re.compile(r"[\s—–-]*")
FACT_LABEL_RE = re.compile(r"(^\s*Fact\b)|([\"”]\s*[—–-]\s*Fact\b)", re.S)


def unquote_ref(s):
    s = s.strip()
    while len(s) >= 2 and s[0] in REF_QUOTES and s[-1] in "`'>":
        s = s[1:-1].strip()
    return s


def ref_candidates(field):
    """Candidates in order: as written, unquoted, without trailing punctuation, then each with
    the first word(s) dropped (lead-ins such as 'as quoted in'). Deterministic, no regex on
    whitespace: spaces inside a path are part of it."""
    base = []
    for c in (field.strip(), unquote_ref(field), unquote_ref(field).rstrip(".,;:)")):
        if c and c not in base:
            base.append(c)
    out = list(base)
    for c in base:
        words = c.split()
        for k in range(1, len(words)):
            cand = " ".join(words[k:])
            if cand not in out:
                out.append(cand)
    return out


SOURCE_NOT_UNDER_ROOT = ("source file not found under sources_root (%s) — set sources_root: "
                         "in context.md or use an absolute path")


def _is_file(p):
    try:
        return p.is_file()
    except OSError:
        return False


def resolve_source(ref, sources_root, store=None):
    """-> (Path or None, reason); reason is "" when found (FR-1.2, A3, S1).

    The one source resolver. A relative ref resolves against `sources_root` ONLY: the working
    directory is never consulted, so a verdict cannot depend on the folder a command ran
    from. An absolute or `~` path is used as given. The reasons are pinned strings; the
    sources_root in the not-found reason is relative to `store` when the caller knows the
    store and the root is under it (`rel`), else as given: a reason names no machine path it
    does not have to."""
    ref = ref.strip()
    if re.match(r"^https?://", ref):
        return None, "remote URL (never fetched)"
    if not PATHLIKE_RE.search(ref):
        return None, "source reference is not a path (%r); use a resolvable path" % ref
    p = Path(ref).expanduser()
    if ref.startswith("~") or p.is_absolute():
        return (p, "") if _is_file(p) else (None, "source file not found")
    if sources_root is None:     # no root given: a relative ref resolves to nothing
        return None, "source file not found"
    cand = Path(sources_root) / ref
    if _is_file(cand):
        return cand, ""
    shown = rel(sources_root, store) if store is not None else sources_root
    return None, SOURCE_NOT_UNDER_ROOT % (shown,)


def resolve_candidate(cand, sources_root):
    """-> cand when it names a URL or a file `resolve_source` finds, else None."""
    if re.match(r"^https?://", cand):
        return cand
    return cand if resolve_source(cand, sources_root)[0] is not None else None


def resolve_reference(fields, sources_root, prev_ref):
    """Return (ref, kind). kind: inherited | path | not-a-path | missing. If nothing resolves,
    the reported ref is the WHOLE path-like field, never a substring the author did not write.
    """
    # path-like fields first (A12): an explicit path in the tag is never overridden by a
    # "same source" shorthand written next to it
    pathlike = [i for i, f in enumerate(fields) if PATHLIKE_RE.search(unquote_ref(f))]
    for i in pathlike:
        for cand in ref_candidates(fields[i]):
            hit = resolve_candidate(cand, sources_root)
            if hit:
                return hit, "path"
        # recovery for an unquoted comma inside the path: rejoin with the next field(s)
        for extra in (1, 2):
            if i + extra < len(fields):
                joined = ", ".join(fields[i:i + extra + 1])
                for cand in ref_candidates(joined):
                    hit = resolve_candidate(cand, sources_root)
                    if hit:
                        return hit, "path"
    if pathlike:
        return unquote_ref(fields[pathlike[0]]).rstrip(".,;:)"), "path"
    same_source_re = locale_regexes()["same_source_re"]
    for f in fields:
        if same_source_re.match(f):
            return prev_ref, "inherited"
    if fields:
        return fields[-1], "not-a-path"
    return None, "missing"


def paren_groups(text):
    """Yield (start, end, inner) for every top-level parenthesized group, tolerating one
    level of nesting inside excerpts.

    Quote-aware like `split_top_level` (A6): a `(` or `)` between double quotes (`"`, `“`,
    `”`) is excerpt text — `"we did it :)"` does not close the tag. The quote state resets
    at a blank line, so one stray `"` in prose cannot swallow the rest of the file."""
    depth, start, in_q = 0, None, False
    n = len(text)
    for i, ch in enumerate(text):
        if ch == "\n":
            j = i + 1
            while j < n and text[j] in " \t\r":
                j += 1
            if j < n and text[j] == "\n":
                in_q = False
            continue
        if ch in "\"“”":
            in_q = not in_q
            continue
        if in_q:
            continue
        if ch == "(":
            if depth == 0:
                start = i
            depth += 1
        elif ch == ")" and depth:
            depth -= 1
            if depth == 0 and start is not None:
                yield start, i + 1, text[start + 1: i]
                start = None


def split_top_level(s):
    """Split on commas that are not inside double quotes or backticks."""
    parts, buf, in_q, in_bt = [], [], False, False
    for ch in s:
        if ch in "\"“”" and not in_bt:
            in_q = not in_q
        elif ch == "`" and not in_q:
            in_bt = not in_bt
        if ch == "," and not in_q and not in_bt:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    parts.append("".join(buf))
    return [p.strip() for p in parts if p.strip()]


def item_start(text, pos):
    """Start of the list item / paragraph that contains pos."""
    starts = [m.end() for m in re.finditer(r"(^|\n)\s*(?:[-*]|\d+[.)])\s+|\n\s*\n", text[:pos])]
    return starts[-1] if starts else 0


def item_end(text, pos):
    """End of the list item / paragraph that contains pos."""
    m = re.search(r"\n[ \t]*(?:[-*]|\d+[.)])\s+|\n[ \t]*\n|\n#{1,6}\s", text[pos:])
    return pos + m.start() if m else len(text)


def _strip_parens(text):
    """Blank out parenthesized groups so a neighbouring tag's excerpt is not stolen."""
    out = list(text)
    for a, b, _ in paren_groups(text):
        for i in range(a, b):
            out[i] = " "
    return "".join(out)


def parse_tags(body, sources_root=None):
    """Return a list of tag dicts: {n, start, end, excerpts, ref, ref_kind, placement, raw, joined,
    dates} — `dates` is the tag's own date fields as written, in order (D2).

    `sources_root` is where relative refs resolve (`resolve_source`). None (the default) means
    no filesystem resolution: a relative ref resolves to nothing, exactly as a missing file
    does, so a caller that forgot the root never picks up files from the working directory.

    A joined tag (FR-2.2) shares one set of parentheses across several Fact claims —
    `(Fact — "a", ref-a, ...; Fact — "b", ref-b, ...)` — so one bullet can carry two
    independent, independently-verifiable excerpts instead of forcing an author to either
    merge unrelated evidence into one tag or split one claim across two bullets. Each half
    is parsed exactly like a standalone tag (its own excerpts, its own ref) and numbered
    `<n>.<i>`; an un-joined tag keeps the plain `<n>` it always had. The prose excerpt
    around the group is claimed by the first excerpt-less segment only: shared parentheses
    are not shared evidence.
    """
    tags, prev_ref, prev_end = [], None, 0
    group_n = 0
    for start, end, inner in paren_groups(body):
        if not FACT_LABEL_RE.search(inner):
            continue
        group_n += 1
        segments = re.split(r";\s*(?=Fact\b)", inner)
        joined = len(segments) > 1
        # The prose around the group is evidence for ONE claim. A joined tag shares its
        # parentheses, not its evidence: if two excerpt-less segments both ran the look-back
        # they would both claim the same neighbouring quote, and the second would read as
        # sourced when nothing in the bullet backs it. Only the first excerpt-less segment
        # takes the prose; a later one keeps no excerpt and is reported as a Fact tag
        # without one.
        lookback_taken = False
        for i, seg in enumerate(segments, start=1):
            excerpts = QUOTE_RE.findall(seg)
            placement = "in-tag"
            if not excerpts and not lookback_taken:
                # look back in the same item, after the previous tag
                lo = max(item_start(body, start), prev_end)
                before = body[lo:start]
                found = list(QUOTE_RE.finditer(before))
                excerpts = [m.group(1) for m in found]
                if found:
                    lookback_taken = True
                    # abutting the tag ("excerpt" (Fact — ...)) is a documented form; anywhere
                    # else in the item is a slip worth naming, not an unevidenced claim
                    gap = before[found[-1].end():]
                    placement = "adjacent" if ONLY_GLUE_RE.fullmatch(gap) else "misplaced"
            if not excerpts and not lookback_taken:
                # look forward in the same item: the tag closes the sentence and the quote
                # follows it. Parenthesized groups are blanked so no neighbour is robbed.
                ahead = _strip_parens(body[end:item_end(body, end)])
                excerpts = QUOTE_RE.findall(ahead)
                if excerpts:
                    lookback_taken = True
                    placement = "misplaced"
            # fields: strip quotes and the label, split on top-level commas
            stripped = QUOTE_RE.sub('""', seg)
            stripped = re.sub(r"^\s*Fact\s*(<-[^—–-]*)?[—–-]?\s*", "", stripped, flags=re.S)
            stripped = re.sub(r'^""\s*[—–-]\s*Fact\s*[—–,-]?\s*', "", stripped, flags=re.S)
            all_fields = split_top_level(stripped)
            dates = [f for f in all_fields if DATE_RE.match(f)]
            fields = [f for f in all_fields if f and f != '""' and not DATE_RE.match(f)
                      and (PATHLIKE_RE.search(unquote_ref(f))
                           or not (KEYWORD_RE.match(f)
                                   or re.match(r"^(type|provenance)\s*:", f, re.I)))]
            leading_join_re = locale_regexes()["leading_join_re"]
            fields = [re.sub(r'\s*:?\s*""\s*$', "", leading_join_re.sub("", f)).strip()
                      for f in fields]
            fields = [f for f in fields if f and f != '""']
            ref, kind = resolve_reference(fields, sources_root, prev_ref)
            if ref:
                prev_ref = ref
            tags.append({"n": ("%d.%d" % (group_n, i)) if joined else str(group_n),
                         "start": start, "end": end, "excerpts": excerpts,
                         "ref": ref, "ref_kind": kind, "placement": placement,
                         "raw": seg.strip()[:160], "joined": joined, "dates": dates})
        prev_end = end
    return tags


# --------------------------------------------------------------------------- the store
STORE_ENV = "BEFOREHAND_STORE"
DEFAULT_STORE = "~/.beforehand"


def resolve_store(cli_value=None):
    """One precedence for every command (FR-4.3): --store > BEFOREHAND_STORE > ~/.beforehand.

    Rationale: three scripts resolved it three ways, so the same session could read one
    store and write another.
    """
    value = cli_value or os.environ.get(STORE_ENV) or DEFAULT_STORE
    return Path(value).expanduser().resolve()


def rel(path, root):
    """Paths are reported relative to the store: an absolute path names this machine, and a
    report is meant to be pasted into a note or a verification file. Falls back to the path
    as given when it is not actually under root (e.g. a source referenced by an absolute
    path outside the store)."""
    try:
        return str(Path(path).resolve().relative_to(Path(root).resolve()))
    except ValueError:
        return str(path)


def resolve_sources_root(ctx, ctx_fm):
    """`sources_root:` in context.md frontmatter, resolved relative to ctx; default ctx itself."""
    value = ctx_fm.get("sources_root")
    if not value:
        return ctx
    p = Path(value).expanduser()
    return p if p.is_absolute() else (Path(ctx) / value).resolve()


def persona_store(persona_path):
    """-> the store a persona sits in (`<store>/<ctx>/personas/<slug>.md`), or None when the
    file is outside a store layout."""
    p = Path(persona_path).expanduser().resolve()
    return p.parent.parent.parent if p.parent.name == "personas" else None


def persona_sources_root(persona_path):
    """The sources_root a persona's refs resolve against, derived from where it sits (A4).

    `<ctx>/personas/<slug>.md` -> that context's `sources_root:` (default the context
    folder; the context folder too when context.md cannot be parsed). A persona outside a
    store layout resolves against its own folder. Never the working directory: the same
    file must read the same from wherever the command runs."""
    p = Path(persona_path).expanduser().resolve()
    if p.parent.name == "personas":
        ctx = p.parent.parent
        try:
            return Store(ctx.parent).sources_root(ctx)
        except FrontmatterError:
            return ctx
    return p.parent


class Store(object):
    """The layout of a personas store, in one place.

    <store>/<context>/personas/*.md, context.md, AUDIT.md, calibration/pending-*.md.
    Every method takes a context name or a context path; nothing here creates or writes.
    """

    def __init__(self, path):
        self.root = Path(path).expanduser()

    def __repr__(self):
        return "Store(%r)" % str(self.root)

    def context(self, name):
        """-> the context directory (it may not exist)."""
        p = Path(name)
        return p if p.is_absolute() else self.root / p

    def contexts(self):
        """-> sorted context directories (hidden ones are not contexts)."""
        if not self.root.is_dir():
            return []
        return sorted(p for p in self.root.iterdir() if p.is_dir() and not p.name.startswith("."))

    def personas(self, ctx):
        d = self.context(ctx) / "personas"
        return sorted(d.glob("*.md")) if d.is_dir() else []

    def snapshots(self, ctx, prefix="pending-"):
        d = self.context(ctx) / "calibration"
        return sorted(d.glob(prefix + "*.md")) if d.is_dir() else []

    def audit(self, ctx):
        return self.context(ctx) / "AUDIT.md"

    def context_frontmatter(self, ctx):
        cm = self.context(ctx) / "context.md"
        return read_frontmatter(read_text_lenient(cm)) if cm.is_file() else {}

    def sources_root(self, ctx):
        c = self.context(ctx)
        return resolve_sources_root(c, self.context_frontmatter(c))
