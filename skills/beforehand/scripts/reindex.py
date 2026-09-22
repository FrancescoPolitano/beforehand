#!/usr/bin/env python3
"""Regenerate the derived index files of a personas store from the persona files.

INDEX files are derived data: hand-editing them is how a store drifts (two formats,
counts that no longer match, a persona missing from the roster). This script rebuilds
them deterministically from the frontmatter of `personas/*.md` and, optionally, from
`context.md` in each context directory.

Usage:
  reindex.py [--store ~/.beforehand] [--context NAME] [--dry-run] [--pointer PATH]
             [--no-lint] [--fail-on-lint] [--fail-on-gaps]

  --context NAME   rebuild one context (default: all contexts + the root index)
  --dry-run        print what would change, write nothing
  --pointer PATH   also write a pointer file (for a working directory outside the store)
                   listing the personas of --context; requires --context
  --no-lint        skip the verify_quotes linter; lint column is written as '-'
  --fail-on-lint   exit 3 if any rebuilt persona fails lint
  --fail-on-gaps   exit 4 if a context has no context.md or a persona has no cares_about

Exit codes: 0 ok · 1 usage (--pointer without --context, unknown locale; nothing is
written) · 2 store/context not found · 3 --fail-on-lint and a persona fails · 4
--fail-on-gaps and gaps found. Exits 3 and 4 come after every file has been written.

Inputs read per context:
  personas/<slug>.md frontmatter: slug, role, organization, decision_function,
      decision_weight (a trailing "# (...)" comment is stripped), aliases [..],
      cares_about (string or [..]), created, updated
  context.md (optional):
      ---
      description: <one line: who this audience is>
      sources_root: <path, relative to this context dir or absolute; default: this dir>
      ---
      ## Wanted
      - <role or name> | <decision function it would cover> | <why it matters>
      (stakeholders you know exist but have no evidence for yet; they are the panel's
       declared blind spots, so they are listed in the index, never invented as personas)

Lint column: each persona line is linted with verify_quotes.lint_persona (Fact excerpts
checked against sources_root) unless --no-lint. A linter that fails to import, or raises
on one file, never aborts the run: the column falls back to '-' or 'error (...)'.

Staleness: a persona whose `updated:` is more than 180 days old ends its line with
`| stale since YYYY-MM-DD`, the first day it was past that budget. A date, not a day count,
so an unchanged store reindexes byte-identically on any later day (FR-4.7). An `updated:`
that is not a YYYY-MM-DD date is reported as an incomplete input, never a traceback.

--context NAME rebuilds that context's INDEX.md and the root line of every context; the
other contexts' persona and failing counts are read from their own INDEX.md (the
`## Personas (N)` heading and the `lint: fail` lines), never re-linted and never zeroed —
with or without --no-lint. A context that has no INDEX.md yet is counted from its persona
files, with no failing clause, until its own reindex runs.

Outputs:
  <context>/INDEX.md and <store>/INDEX.md, canonical format below. Everything else in the
  store is left untouched.
"""
import sys

sys.dont_write_bytecode = True  # before any sibling import (G5)

import argparse  # noqa: E402
import datetime as dt  # noqa: E402
import re  # noqa: E402
from pathlib import Path  # noqa: E402

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
from personas_lib import (  # noqa: E402
    SCHEMA_VERSION,
    FrontmatterError,
    Store,
    atomic_write,
    check_locale,
    parse_iso_date,
    read_frontmatter,
    read_text_lenient,
    resolve_sources_root,
    resolve_store,
    section_body,
)

# The index says which schema the store it describes is written in (FR-7.3), so `doctor` and
# `migrate` can tell a 0.1 store from a 0.2 one without opening every persona. It is a
# constant line, not a stamp: it changes only when SCHEMA_VERSION does, so it never makes an
# otherwise unchanged index look changed (FR-4.7) and it is deliberately ignored by the
# comparison that decides whether `last regenerated` moves — that comparison reads the
# persona block alone.
SCHEMA_COMMENT = "<!-- schema: %s -->" % SCHEMA_VERSION

# A hook, not a bare `dt.date.today()` call: a test sets `reindex._today = lambda: dt.date(...)`
# to get a deterministic "today" without ever asserting on the real one (SPEC-0.2 global
# constraint). Every place in this module that needs today's date calls `_today()`.
_today = dt.date.today
try:
    import verify_quotes as _vq
except Exception as e:  # a broken linter must never block bookkeeping
    _vq = None
    print(f"warning: linter unavailable ({e.__class__.__name__}); lint column written as '-'",
          file=sys.stderr)
try:
    import coverage as _cov
except Exception:  # same rule: bookkeeping does not depend on it
    _cov = None


def frontmatter(path: Path, text=None) -> dict:
    """Frontmatter of one file, never fatal. A file whose frontmatter is outside the FR-4.8
    subset is named on stderr and its fields are dropped: bookkeeping runs on the rest of the
    store, the same rule the linter and the coverage column already follow here."""
    try:
        return read_frontmatter(read_text_lenient(path) if text is None else text)
    except FrontmatterError as e:
        print(f"warning: {path}: frontmatter outside the subset at line {e.line_no} "
              f"({e.reason}); its fields are ignored", file=sys.stderr)
        return {}


def lint_label(path: Path, sources_root: Path, enabled: bool, store=None) -> str:
    if not enabled or _vq is None:
        return "-"
    try:
        return _vq.lint_persona(path, sources_root, store)["label"]
    except Exception as e:  # one bad file must not abort the index
        return f"error ({e.__class__.__name__})"


def coverage_label(path: Path, audit: Path, enabled: bool) -> str:
    """How founded the persona is, next to whether its quotes resolve. Two different questions:
    the linter says the excerpts exist, this says there is enough of them, spread widely
    enough, to be worth convening. It never blocks — it travels with the persona."""
    if not enabled or _cov is None:
        return "-"
    try:
        return _cov.coverage_line(path, audit if audit.is_file() else None)
    except Exception as e:
        return f"error ({e.__class__.__name__})"


STALE_DAYS = 180


def stale_since(upd):
    """-> the first day `updated` was more than STALE_DAYS old, or None when `upd` is not a
    YYYY-MM-DD string (`parse_iso_date` raises ValueError for anything else, a list included)."""
    try:
        return parse_iso_date(upd) + dt.timedelta(days=STALE_DAYS + 1)
    except ValueError:
        return None


def persona_line(fm: dict, path: Path, lint: str, coverage: str = "-") -> str:
    cares = fm.get("cares_about", "")
    if isinstance(cares, list):
        cares = ", ".join(cares)
    aliases = fm.get("aliases", [])
    if isinstance(aliases, str):
        aliases = [aliases]
    slug = fm.get("slug") or path.stem
    weight = fm.get("decision_weight", "?")
    stale = ""
    upd = fm.get("updated")
    since = stale_since(upd) if upd else None
    if since is not None and _today() >= since:
        stale = f" | stale since {since.isoformat()}"
    if upd and not isinstance(upd, str):
        upd = None                               # reported by build_context_index
    return (f"- {slug} | {fm.get('role', '?')} | {fm.get('decision_function', '?')} | weight {weight} | "
            f"aliases: {', '.join(aliases) if aliases else '-'} | cares about: {cares or '-'}"
            f" | updated {upd or '?'} | lint: {lint} | coverage: {coverage}{stale}")


def _lint_root_display(sources_root: Path, store: Path) -> str:
    """The lint-root path as shown in the index: relative to the STORE root, not to the
    process's cwd or to the machine. Cwd-relative would break the cwd-independence this
    module already guarantees (the same store, addressed via a different relative --store
    from a different working directory, must produce byte-identical output); an absolute
    path would put this machine's directory layout into a file the repository commits
    (SPEC-0.2 publishable-at-every-moment). Store-relative is the only rendering that is
    both cwd-independent and free of any machine-specific prefix. Falls back to the
    absolute path only when sources_root sits outside the store entirely (allowed by
    context.md's `sources_root:`), where no relative form exists."""
    try:
        return sources_root.resolve().relative_to(store.resolve()).as_posix()
    except ValueError:
        return str(sources_root)


_REGEN_RE = re.compile(r"^<!-- last regenerated: .*? -->$", re.M)


def _persona_block(content):
    """The '## Personas (N)' section body, or None. Used to decide whether 'last
    regenerated' should move: that stamp tracks the persona listing itself, not bookkeeping
    prose (a context's description, its `## Wanted` list) that can change independently."""
    m = re.search(r"^## Personas[^\n]*\n\n(.*?)\n\n## ", content, re.S | re.M)
    return m.group(1) if m else None


def build_context_index(ctx: Path, lint_enabled: bool) -> tuple:
    personas = Store(ctx.parent).personas(ctx)
    ctx_md = ctx / "context.md"
    description, wanted, ctx_fm = "", "", {}
    # Gaps that used to be filled with a silent placeholder in the index, where nobody ever
    # read them. A missing input is said out loud, once, where the command is run.
    warnings = []
    if not ctx_md.is_file():
        warnings.append(f"{ctx.name}: no context.md, so no description and no `## Wanted` "
                        "section. The index shows a placeholder; the blind spots of this "
                        "context are recorded nowhere.")
    if ctx_md.is_file():
        text = read_text_lenient(ctx_md)
        ctx_fm = frontmatter(ctx_md, text)
        description = ctx_fm.get("description", "")
        wanted = (section_body(text, "Wanted", level=2) or "").strip()
    sources_root = resolve_sources_root(ctx, ctx_fm)
    lines = [f"# {ctx.name} — personas index", "",
             "<!-- derived file: regenerate with scripts/reindex.py, do not hand-edit -->",
             SCHEMA_COMMENT]
    # Where the regenerated-date stamp is anchored: right after the lint-root line when
    # lint ran, otherwise right after the "derived file" comment — the stamp tracks the
    # persona listing, not whether lint happened to run this time (a --no-lint rebuild must
    # not silently drop it).
    regen_anchor_idx = len(lines) - 1
    if lint_enabled:
        lines.append(f"<!-- lint root: {_lint_root_display(sources_root, ctx.parent)} -->")
        regen_anchor_idx = len(lines) - 1
    lines.append("")
    if description:
        lines += [description, ""]
    lines.append(f"## Personas ({len(personas)})")
    lines.append("")
    labels = []
    for p in personas:
        fm = frontmatter(p)
        lint = lint_label(p, sources_root, lint_enabled, ctx.parent)
        labels.append(lint)
        lines.append(persona_line(fm, p, lint, coverage_label(p, ctx / "AUDIT.md", lint_enabled)))
        upd = fm.get("updated")
        if upd and stale_since(upd) is None:
            warnings.append(f"{p.name}: `updated: {upd}` is not a YYYY-MM-DD date, so "
                            "staleness is not computed for this persona.")
        if not str(fm.get("cares_about", "")).strip():
            warnings.append(f"{p.name}: no `cares_about` in the frontmatter. It is the field "
                            "roster selection reads, so this persona will be picked badly and "
                            "nothing else will say so.")
    if not personas:
        lines.append("- (none yet)")
    lines += ["", "## Wanted — no evidence yet, declared blind spots", ""]
    lines.append(wanted if wanted else "- (none declared; add them in context.md under `## Wanted`)")
    lines.append("")
    n_fail = sum(1 for label in labels if label.startswith("fail"))

    # Deterministic index (FR-4.7): re-running reindex on an unchanged store must produce a
    # byte-identical file even when the calendar date has moved on. "last regenerated" is
    # compared and rewritten separately from everything else: if the persona listing itself
    # is unchanged, the old stamp (whatever date it carries) is kept verbatim; only a real
    # change to the personas gets a fresh one. This runs regardless of `lint_enabled`: the
    # stamp tracks the persona listing, not the lint column, so a `--no-lint` rebuild must
    # not rewrite the index with the stamp silently dropped.
    old_path = ctx / "INDEX.md"
    old_text = read_text_lenient(old_path) if old_path.is_file() else None
    core = "\n".join(lines)
    changed = old_text is None or _persona_block(core) != _persona_block(old_text)
    if changed:
        regen_line = f"<!-- last regenerated: {_today().isoformat()} -->"
    else:
        m = _REGEN_RE.search(old_text)
        regen_line = m.group(0) if m else None
    if regen_line:
        lines.insert(regen_anchor_idx + 1, regen_line)
    return "\n".join(lines), description, n_fail, warnings


_COUNT_RE = re.compile(r"^## Personas \((\d+)\)", re.M)
_FAIL_LINE_RE = re.compile(r"^- .*\| lint: fail\b", re.M)


def indexed_counts(ctx: Path) -> tuple:
    """-> (persona count, failing count) of a context that is NOT rebuilt this run, read from
    its own INDEX.md (FR-5.5): re-linting it would do its work behind its back, and `--no-lint`
    used to zero its failing count in the root index. No INDEX.md yet: the persona files are
    counted and the failing count is unknown (0) until that context's own reindex runs."""
    idx = ctx / "INDEX.md"
    text = read_text_lenient(idx) if idx.is_file() else ""
    m = _COUNT_RE.search(text)
    if not m:
        return len(Store(ctx.parent).personas(ctx)), 0
    return int(m.group(1)), len(_FAIL_LINE_RE.findall(text))


def build_root_index(store: Path, descriptions: dict, failing: dict, counts=None) -> str:
    lines = ["# Personas — root index", "",
             "<!-- derived file: regenerate with scripts/reindex.py, do not hand-edit -->",
             SCHEMA_COMMENT, ""]
    counts = counts or {}
    for name in sorted(descriptions):
        n = counts[name] if name in counts else len(Store(store).personas(name))
        desc = descriptions[name] or "(no description: add `description:` to context.md)"
        m = failing.get(name, 0)
        plural = "s" if n != 1 else ""
        fail_clause = f", {m} failing lint" if m else ""
        lines.append(f"- {name} — {desc} [{n} persona{plural}{fail_clause}]")
    lines.append("")
    return "\n".join(lines)


def build_pointer(ctx: Path) -> str:
    personas = Store(ctx.parent).personas(ctx)
    lines = ["# Personas of this work — pointer", "",
             f"The stakeholder dossiers live in the personas store, not here: `{ctx}`.",
             "Nothing is duplicated in the working directory; ask the `beforehand` skill for a review,",
             "a consult or an update.", ""]
    for p in personas:
        fm = frontmatter(p)
        lines.append(f"- {fm.get('slug', p.stem)} — {fm.get('role', '?')}, "
                     f"{fm.get('decision_function', '?')}, "
                     f"weight {fm.get('decision_weight', '?')}: `{p}`")
    lines.append("")
    return "\n".join(lines)


def write(path: Path, content: str, dry: bool) -> bool:
    old = read_text_lenient(path) if path.is_file() else None
    if old == content:
        print(f"unchanged  {path}")
        return False
    print(f"{'would write' if dry else 'written   '} {path}")
    if not dry:
        atomic_write(path, content)
    return True


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--store", default=None)
    ap.add_argument("--context")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--pointer")
    ap.add_argument("--no-lint", action="store_true",
                     help="skip the verify_quotes linter; lint column is written as '-'")
    ap.add_argument("--fail-on-lint", action="store_true",
                     help="exit 3 if any rebuilt persona fails lint")
    ap.add_argument("--fail-on-gaps", action="store_true",
                     help="exit 4 if a context has no context.md or a persona has no cares_about")
    args = ap.parse_args(argv)
    # validated AFTER parse_args, so --help and an argparse usage error still work under an
    # unknown locale
    locale_err = check_locale()
    if locale_err:
        print(locale_err, file=sys.stderr)
        return 1
    if args.pointer and not args.context:
        # A usage error, and before anything is written (E9): it used to surface only after
        # every INDEX.md had been rewritten, with exit 2 — the code for "store not found".
        print("usage: --pointer requires --context (the pointer lists one context's personas)",
              file=sys.stderr)
        return 1
    store = resolve_store(args.store)
    if not store.is_dir():
        print(f"store not found: {store}", file=sys.stderr)
        return 2
    st = Store(store)
    lint_enabled = not args.no_lint
    contexts = [st.context(args.context)] if args.context else st.contexts()
    descriptions, failing = {}, {}
    total_fail = 0
    all_warnings = []
    for ctx in contexts:
        if not ctx.is_dir():
            print(f"context not found: {ctx}", file=sys.stderr)
            return 2
        content, desc, n_fail, warns = build_context_index(ctx, lint_enabled)
        write(ctx / "INDEX.md", content, args.dry_run)
        descriptions[ctx.name] = desc
        failing[ctx.name] = n_fail
        total_fail += n_fail
        all_warnings += warns
    if not args.context:
        write(store / "INDEX.md", build_root_index(store, descriptions, failing), args.dry_run)
    else:
        # root index: this context's line from the rebuild, every other line from that
        # context's own INDEX.md (never re-linted, never zeroed — FR-5.5)
        all_desc, all_fail, all_count = {}, {}, {}
        for c in st.contexts():
            cm = c / "context.md"
            cm_fm = frontmatter(cm) if cm.is_file() else {}
            all_desc[c.name] = cm_fm.get("description", "")
            if c.name in failing:
                all_fail[c.name] = failing[c.name]
            else:
                all_count[c.name], all_fail[c.name] = indexed_counts(c)
        write(store / "INDEX.md", build_root_index(store, all_desc, all_fail, all_count),
              args.dry_run)
    if args.pointer:
        write(Path(args.pointer).expanduser(), build_pointer(st.context(args.context)),
              args.dry_run)
    if all_warnings:
        print("\nIncomplete inputs (bookkeeping still ran):", file=sys.stderr)
        for w in all_warnings:
            print("  - " + w, file=sys.stderr)
    if args.fail_on_lint and total_fail:
        return 3
    return 4 if all_warnings and args.fail_on_gaps else 0


if __name__ == "__main__":
    print("deprecated: use beforehand.py reindex", file=sys.stderr)
    sys.exit(main())
