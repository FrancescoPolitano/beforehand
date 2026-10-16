# dev/

Internal to this repository: the release gates and dev-only tooling below. Nothing here
ships with the skill. Planning notes, review logs, issue write-ups and per-task
verification records are the maintainer's own working material, not part of the public
repository, and live outside it — the maintainer's planning history, kept outside
the repository — so this folder holds only what a user or a contributor needs. The generality
rule (SPEC-0.2 §0) still applies: no personal data, no real organisations, no maintainer
identity beyond the exact public strings in `public-identity.txt`, no `/Users/…` or `/home/…`
paths, anywhere in the repository, including this folder.

How to work on the tree — the gate as a sequence of commands, the rules that gate every
change, and the pull-request checklist — is [`../CONTRIBUTING.md`](../CONTRIBUTING.md). This
file is the reference for the tooling that checklist calls.

## Environment variables

- `BEFOREHAND_DEV_TERMS` — path to a file with one forbidden term per line (names, real
  organisations, anything that would deanonymise the maintainer or a real client), fed
  to `check_generality.sh` as a fixed-string, case-insensitive term list. Not part of
  the repository; kept outside it (e.g. `~/.beforehand-dev/generality-terms.txt`).
- `BEFOREHAND_DEV_LOG` — destination path for `log_usage.py`'s JSONL usage log (the script
  itself lives at `~/.beforehand-dev/dev-records/log_usage.py`, see
  [below](#plugin-layout-the-skill-build-and-the-opt-in-usage-hook)). Required; the script
  writes nothing if it is unset, and refuses (exit 3) if the resolved path falls inside a
  git work tree, so usage data can never land back in the repository.
- `BEFOREHAND_LOCALE` / `BEFOREHAND_LOCALE_DIR` — see [Locales](#locales) below.

## The check scripts, in one line each

- `check_all.sh` — the gate: runs everything below plus the test suite, the golden-store and
  determinism checks, the 3.9 syntax floor, ruff and the eval checkers. See [`check_all`](#check_all).
- `check_all_versions.sh` — `check_all.sh` once per Python interpreter this machine has.
- `check_generality.sh` — the publication gate: no personal data, no real organisations, no
  absolute machine paths, no working material under the tree. `public-identity.txt` lists the
  exact strings it exempts; `pre-commit` runs it as a git hook.
- `check_router.sh` — SKILL.md's budget (lines, estimated tokens, description length), the one
  invocation form, and the domain-vocabulary count over SKILL.md and the references. The
  description is read through `personas_lib`'s frontmatter reader (a folded `description: >`
  block is joined first, as the host reads it), and a missing or empty one fails
  (`description: missing or empty FAIL`).
- `check_floor.py` — the 3.9 syntax floor as an AST check, called by `check_all.sh`. See
  [`check_all`](#check_all).
- `check_norms.sh` — one norm, one file: every anchor in `norm-anchors.txt` matches exactly one
  file, and that file is `references/evidence-model.md`. Its companion, the anchor-target step
  inside `check_all.sh`, proves the pointers *to* that file resolve to real headings.
- `build_skill.sh` — the `.skill` bundle. See [Plugin layout](#plugin-layout-the-skill-build-and-the-opt-in-usage-hook).

## `check_generality.sh`

`dev/check_generality.sh [--patterns-only]` greps the repository tree (excluding
`.git/` and `dist/`) for two built-in pattern sets and, unless `--patterns-only`, for every term in
`$BEFOREHAND_DEV_TERMS` (this grep excludes nothing but `.git/` and `dist/`). The two built-in sets:

- **Anecdote/name patterns** (the handful of phrasal tells that mark real-case
  anecdotes in skill prose, plus the maintainer's first name and surname — see `anecdote_pat` in
  the script for the exact list): excludes only `check_generality.sh` itself. Historical
  planning documents and review logs used to need an exclusion here; they now live outside
  the repository (the maintainer's planning history, kept outside the repository), so
  nothing under the repository root is exempt any more.
- **Path patterns** (`/Users/[a-z]`, `/home/[a-z]`): excludes nothing but `.git/` and
  `dist/`. A leaked absolute path is a leak everywhere, including inside a compiled
  `.pyc` (which embeds the absolute source path of the machine that built it) — exactly
  the leak this gate exists to catch, so binary matches are kept, not excluded. `dist/`
  holds only `build_skill.sh`'s output, a deflated zip of `skills/` whose bytes are
  already scanned here in their source form and which a line-based grep can report only
  as an unreadable binary match either way.

**The public identity.** 1.0 publishes the maintainer's identity on purpose, in a few places
(`LICENSE`, the manifests' author and owner, the repository URLs). `dev/public-identity.txt`
lists those exact strings, one per line (`#` lines and blank lines ignored; letters, digits,
space and `/ . _ -` only, or the script refuses the file): the author's name, the repository
slug and the owner handle. The name-pattern scan and the term-list scan run on a stripped view
of the tree — a temporary copy of every file with each listed string removed, exact and
case-sensitive, longest first — and report a hit with the real file's path, line number and
unstripped line. So the listed strings pass and anything else still fails: the first name or
the surname on its own, a different case, or a longer word that starts with a listed string
(what remains of it is still scanned against the term list). The path scan and the junk scan
run on the tree itself and ignore the file. A file the view cannot copy (unreadable) makes both
scans incomplete, which fails, like a grep exit of 2 or more.

It also fails if `__pycache__`, `.backup-*`, `skill-workspace` or `.superpowers` are
present anywhere under the tree (`dist/` excepted). It prints each hit as `file:line: match` and exits 0 on
zero hits, 1 otherwise. A scan grep cannot complete (grep exit 2 or more, an unreadable file for
instance) is a failure too, printed as `generality: the <label> scan could not complete (grep
exit N)`: a scan that did not run is not a clean scan. When a `.git/` directory exists it additionally reports, without
failing, whether `git log -p --all` contains term-list hits — informational for the 1.0
adoption, not a gate.

**Run it before sharing, zipping or backing up this folder.** It is also the pre-commit hook:
`ln -s ../../dev/pre-commit .git/hooks/pre-commit` from the repository root installs
`dev/pre-commit` (POSIX sh), which runs `sh dev/check_generality.sh` from the root — with your
`BEFOREHAND_DEV_TERMS` term list when it is set — and exits with its code.

## `check_norms`

One norm, one file (SPEC-0.2 §0, FR-3.2): a rule the model follows is stated **once**, in
`skills/beforehand/references/evidence-model.md`; every other file that needs it cites
`references/evidence-model.md#<anchor>` instead of restating it. A rule restated in three
places is three rules on the day one of them is edited, and the model then follows whichever
copy it happened to load.

`dev/norm-anchors.txt` is the anchors file: one distinctive literal phrase per norm, one per
line, `#` and blank lines ignored. `dev/check_norms.sh` greps each phrase (`grep -rlF`, so
punctuation and case are literal) across `skills/beforehand/` and requires **exactly one
matching file, and that file to be `evidence-model.md`**. Two or more files means the norm has
been duplicated; zero, or one file that is not `evidence-model.md`, means the anchor is stale
and the list needs updating with the text. It prints one line per offending anchor and ends on
`norms: N anchors, one file each` or `norms: M of N anchors not stated exactly once`; exit 0 or
1. `skills/beforehand/assets/reviewer-examples.md` is excluded: it is a prompt fragment pasted
verbatim into the reviewer's context, not a place where a norm is stated (FR-3.6).

**To add a norm**: write it in `evidence-model.md` under its own heading, then add to
`norm-anchors.txt` one phrase from that sentence which (a) is distinctive enough not to match
anything else in the tree, and (b) sits on a **single line in every file where it appears** —
`grep` is line-based, so a phrase that wraps in a duplicate reports one file and hides the
duplicate. Several of the existing anchors are therefore fragments cut to what fits one line on
both sides. Then run `sh dev/check_norms.sh`: it must report one file. If a phrase is
unanchorable because a script also parses it as a literal string (the canonical empty-section
form `no evidence as of <date>` is in `coverage.py`, so its file count can never be 1), anchor
the norm on its rationale clause instead, and say so in a comment in the anchors file.

Norms that belong to a **flow** rather than to the evidence model (the two-file isolation rule
in `review.md`, the lint gate's two legal exits in `authoring.md`, the calibration accounting)
are not anchored here — an anchor phrase that is not in `evidence-model.md` cannot be checked
against "stated once, in that file". They are tracked in `docs/ARCHITECTURE.md`'s rule table.

## `check_all`

`dev/check_all.sh` is the gate (SPEC-0.2 FR-7.2). There is no hosted CI (decided for 1.0:
none for now): this script is what a CI workflow would call in one line, and it is run
by hand — before a commit, a pull request, a release, or calling a task done.

It runs, in order: `check_generality.sh --patterns-only` -> `check_router.sh` ->
`check_norms.sh` -> the anchor-target check (on every line carrying
`references/evidence-model.md#` under `skills/beforehand/`, `docs/`, `README.md` and
`CONTRIBUTING.md`, every anchor — the first and each follow-on `` `#<X>` `` — names a `## <X>`
heading in that file, compared with `-` normalised to a space; placeholders `#<…>` are
skipped; it prints the offending `file:line` and the anchor it could not resolve) -> the test
suite (`beforehand.py test`; a suite that crashes, prints `0/0` or no summary line is
`<suite>: no checks ran` and fails, and a failing suite prints its `FAIL ` lines and the last
20 lines of its stderr) -> golden-store expectations (`reindex --dry-run` on the golden
context reports `golden/INDEX.md` unchanged; `doctor` prints the pinned `doctor: healthy (3 of 3
personas checked)` line) -> a deterministic-index check (FR-4.7: real `reindex` writes on temporary copies of
the golden store with `reindex._today` mocked to 2027-01-10 and 2027-01-11, days on which every
golden persona is stale; copy A is written on the first day, copy B on the first day and
then again on the second, and every INDEX.md of A and B must be byte-identical — comparing
two copies each written once on a different day would differ by the `last regenerated` stamp
by design; the step fails if no staleness suffix is present, which would make the
comparison vacuous) -> the 3.9 syntax floor (`dev/check_floor.py`: every
`skills/beforehand/scripts/*.py`, `dev/*.py` and `evals/**/*.py` file parses with
`ast.parse(..., feature_version=(3, 9))`, with no PEP 604 union in an annotation outside a file
with `from __future__ import annotations`, no subscripted builtin at runtime, no parenthesised
context manager and no `zip(strict=)`; walrus and `removeprefix` are legal on 3.9 and are not
flagged; this guards the floor on a machine with no 3.9 interpreter of its own) -> `ruff
check` (over `skills/`, `dev/`, `evals/` and `beforehand_cli/`) -> `evals/run.sh --checkers-only`
(a fixture whose checker exits non-zero with no `FAIL `
line is reported as a crash, for must-fail and must-pass fixtures alike; nothing is written
outside a temporary directory unless `EVALS_OUT` is set) -> `cli` (`beforehand_cli/test_cli.py`,
runnable alone as `python3 -B beforehand_cli/test_cli.py`: install into a temporary HOME, every
refusal, `--update`, uninstall, the bundle against `build_skill.sh`'s file list, the passthrough
exit code and `--version`; nothing is written into the repository, and
`beforehand_cli/__pycache__` is removed after the step). The syntax floor also scans
`beforehand_cli/*.py`.

Each step prints its own diagnostic output (most of the called scripts already end in
their own pinned status line) followed by one `<step>: ok` / `<step>: FAIL` summary line.
Exit is 1 if any step fails. `__pycache__` under `skills/` and `evals/`, and `.ruff_cache`
at the repository root, are removed at the end unconditionally — both embed this machine's
absolute paths, which `check_generality.sh` would otherwise flag on the next run.
Every script and test module under `scripts/` sets `sys.dont_write_bytecode` before any
sibling import, so a real run, including a module or a suite run directly through a
symlinked skill directory, leaves no `__pycache__`; a static check in `test_entrypoint.py`
walks every `scripts/*.py` and fails on a module that sets the flag late or not at all. The
cleanup here covers ad-hoc imports.

**Environment.** `PYTHON` — interpreter used for the test suite and the store checks
(default `python3`). `RUFF` — the `ruff` binary; when unset and `ruff` is not on PATH, the
ruff step prints `ruff: skipped (RUFF unset and ruff not on PATH)` rather than failing
(ruff is not a repository dependency). `REQUIRE_RUFF=1` turns that skip into a failure —
`ruff: required but not found` — which is how a release (or a CI, if one is ever added) runs
it, so a green `check_all` can never mean a step vanished. Ruff is always invoked with `--no-cache` for the
same reason `.ruff_cache` is cleaned up above; its configuration is `pyproject.toml`
(`[tool.ruff.lint] select`).

`dev/check_all_versions.sh` runs `check_all.sh` once per Python interpreter this machine
actually has among `python3.9` .. `python3.14` on PATH and every
`~/.pyenv/versions/*/bin/python3` in that same range (deduplicated by resolved version;
an interpreter outside 3.9-3.14, and a PATH name that does not actually run, are both
skipped rather than counted). It prints one summary line per version and exits 1 if any
of them failed. Where this machine has no 3.9 interpreter at all, `check_all.sh`'s own
syntax-floor step (`dev/check_floor.py`) is what still guards that floor.

## Plugin layout, the `.skill` build and the opt-in usage hook

The repository is a Claude Code plugin (SPEC-0.2 FR-7.5): `.claude-plugin/plugin.json`
declares `skills/` (the skill lives at `skills/beforehand/`), `agents/`, the version, the
author, the homepage and the repository, and nothing else; `.claude-plugin/marketplace.json`
makes the repository a single-plugin marketplace (`claude plugin marketplace add
FrancescoPolitano/beforehand`, then `claude plugin install beforehand@beforehand`). Validate
with `claude plugin validate .` (the marketplace manifest) and
`claude plugin validate .claude-plugin/plugin.json`: both pass with no warnings, `--strict`
included.

`agents/persona-reviewer.md` exists twice by design: the plugin root copy is what Claude
Code loads as a subagent, and `skills/beforehand/agents/persona-reviewer.md` is the copy
the single-skill bundle carries for hosts that install a skill rather than a plugin. They
are one prompt: `test_panel.py` asserts they are byte-identical, and `build_skill.sh`
refuses to build on a drift.

`build_skill.sh` also refuses to build when `skills/<name>/assets/reviewer-examples.md` and
`agents/persona-reviewer.md` hold different examples: the asset is the fragment the review
flow pastes inline under "Three examples", the agent file is the prompt it is pasted into, and
the comparison is on the example blocks themselves (the four-space-indented lines). Same rule
again for `docs/assets/beforehand-loop.svg` and its in-bundle copy. The three checks are one
loop over the three pairs, each with its own refusal message.

`sh dev/build_skill.sh` writes `dist/<name>-<version>.skill` (`dist/beforehand-1.0.1.skill`) — a zip of `skills/<name>/`
rooted at `<name>/`, with `__pycache__` and `.DS_Store` stripped — taking both the name
and the version from `.claude-plugin/plugin.json` so the bundle cannot claim a version the
manifest does not. `dist/` is gitignored and excluded from the generality scan; the
bundle is a build artefact, rebuilt on demand and attached to the GitHub Release.
`beforehand bundle` (the `uvx` command line) writes the same archive, entry for entry.

**The usage hook is opt-in and is not shipped.** The manifest declares no hooks and the
repository contains none: a plugin that logged the maintainer's own usage on every install
would be logging its users. The logger script itself, `log_usage.py`, is not part of this
repository either: it is development and local material, kept at
`~/.beforehand-dev/dev-records/log_usage.py`. To enable it for yourself, set
`BEFOREHAND_DEV_LOG` (see above) and register that script as a `PostToolUse` hook on the
`Skill` tool in your own `~/.claude/settings.json` — never in this repository. The script
logs both the `beforehand` and the legacy `personas` skill names.

## Locales

A handful of regexes that used to have one language baked into them — a generic-speaker
label, a declared-empty-section phrase, a snapshot's field names, a Watchlist entry's
"if it repeats" clause, the same-source shorthand, the word joining two excerpts in one
Fact tag — are locale data instead (SPEC-0.2 FR-4.4): a JSON file per locale under
`skills/beforehand/scripts/locales/`, loaded by `personas_lib.get_locale()` /
`personas_lib.locale_regexes()`.

**Only `en` ships** (`skills/beforehand/scripts/locales/en.json`). English is always loaded
first; a non-English locale's file is merged ON TOP of it — it only has to state what it
*adds*, never repeat the English list, so a reviewer can see at a glance what a locale
changes and a locale file stays small.

**Format.** A locale file is one JSON object with these keys (every key is a list of
strings, except `snapshot_fields`, which is an object of lists):

- `same_source` — regex ALTERNATIVES (not escaped: each item is joined into one pattern
  as-is, so an item may itself contain groups, e.g. `"same (source|email|...)"`). Matches
  "same source" shorthand in a Fact tag, which inherits the previous tag's reference.
- `excerpt_joiners` — literal words (escaped) that join two excerpts inside one Fact tag
  (`"a" and "b"`).
- `generic_speaker` — literal words (escaped) for a speaker label the source platform
  assigned because it had no name for that participant (`Guest`, `Speaker 2`); the full
  list is the `generic_speaker` key; `en` includes `user` and `anonymous`, so a chat export
  whose real participant is labelled `User:` needs `--map`.
- `header_labels` — literal words (escaped) that look like a plain speaker marker but are
  a mail header or an editorial label (`Subject:`, `From:`, ...), so they are never
  mistaken for a participant.
- `empty_section` — literal phrases (escaped) that declare a template section empty on
  purpose (`no evidence as of YYYY-MM-DD`).
- `watchlist_repeat_clause` — literal phrases (escaped) that mark a Watchlist entry's note
  about what would change if it repeats, so it can be flagged for rewriting at promotion
  time.
- `snapshot_fields` — an object with three keys, `meeting`, `review_date`, `document`,
  each a list of field names `pending.py` looks for in a calibration snapshot (first match
  wins).

**Search path.** `scripts/locales/` (shipped) first, then `$BEFOREHAND_LOCALE_DIR` (not
part of the repository) — this is how a locale that is not shipped (a work-in-progress
translation, or a test fixture) is reached without adding it to the skill.
`$BEFOREHAND_LOCALE` selects which one to load; unset means `en`.

**Testing a new locale**, without adding it to `scripts/locales/`:

```
BEFOREHAND_LOCALE=xx BEFOREHAND_LOCALE_DIR=/path/to/your/locales beforehand.py <command> ...
```

`skills/beforehand/scripts/test_fixtures/locales/xx.json` is exactly this: a locale that
only ever existed to prove the mechanism in `test_locale.py`, reached the same way,
never shipped. Its sample fixture text (the words it recognises that English does not)
lives in `skills/beforehand/scripts/test_fixtures/locale-samples/`, not in any `.py` file —
the FR-4.4 acceptance check is a grep over `scripts/*.py` for exactly those words, and a
test proving a locale is recognised must not itself be a hit.

**Resolution is lazy**, not baked in at import: `get_locale()`/`locale_regexes()` read
`BEFOREHAND_LOCALE` at call time and cache per resolved code (not per call), because
`personas_lib` is typically imported once, early — often before a `--locale` flag on the
same command line has been applied to the environment — and a value resolved that early
would never see a locale requested later in the same process.

## 1.0 checklist

The state of the 1.0 launch, recorded here so that the decisions live in the repository rather
than in the maintainer's head. Each line is a decision already taken; none of them is an open
question.

Done:

- **Author.** `Francesco Politano` is the author in `.claude-plugin/plugin.json`, the owner in
  `marketplace.json`, the author in `pyproject.toml`, and the copyright holder in `LICENSE`;
  the repository is `https://github.com/FrancescoPolitano/beforehand`. These strings are the
  ones `public-identity.txt` exempts. `claude plugin validate` passes with no warnings.
- **`CHANGELOG.md`.** Emptied at the launch: it holds the `1.0.0` entry and records releases
  only.
- **Version control.** The history lives in git; contributions come as pull requests against
  `main`, and `dev/pre-commit` runs `check_generality.sh` on every commit.

Still outstanding:

- **Run the live eval pass.** `sh evals/run.sh --live` against a real host, and re-record
  every case; six of the seven cases have only ever been exercised by their checkers, and one
  recorded transcript predates the current reviewer prompt.
- **Verify the Cowork and Desktop installs.** Neither host was reachable from the build
  machine, so the README calls Cowork "expected to work, not yet verified end to end".
  Verifying means: the `.skill` bundle installs from its archive-root convention (one
  top-level directory named after the skill) and the plugin's `"skills": "./skills/"`
  discovery finds `skills/beforehand/` on the plugin side.
- **Decide the SKILL.md token cap.** The router sits at 1489 of 1500 estimated tokens and
  100 of 120 lines: the next sentence added to it fails `check_router.sh`. Either raise the
  cap with a stated reason or accept that the router is closed to additions.
- **CI.** Decided: none for now. `dev/check_all.sh` is what a CI job would run, with
  `REQUIRE_RUFF=1` so the ruff step can never silently skip; until then it is run by hand, and
  the pre-commit hook covers the generality gate.
