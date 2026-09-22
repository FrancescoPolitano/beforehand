# Contributing to beforehand

Thank you for wanting to work on this. The skill makes one promise — every trait in a profile
traceable to something a real person actually said, nothing entering a profile unlabeled, and
the repository publishable at every moment — and every rule below exists so that promise
survives more than one person editing the tree. Where a rule can be checked by a script, the
script is named next to it; where it cannot, that is said plainly instead.

## Before you start

Python 3.9 or newer, standard library only. There is nothing to install: no `requirements.txt`,
no virtualenv. [`pyproject.toml`](pyproject.toml) packages the `beforehand` command line for
`uvx` (hatchling, at build time only — never a runtime dependency) and configures ruff
(`line-length = 110`, `target-version = "py39"`, `select = ["E", "F", "I"]`); ruff is optional
locally — the gate skips it with a notice when it is absent.

Fork `FrancescoPolitano/beforehand` on GitHub, clone your fork, and work on a branch:

```bash
git clone https://github.com/<you>/beforehand && cd beforehand
git checkout -b <your-branch>
ln -s ../../dev/pre-commit .git/hooks/pre-commit              # the generality gate on every commit
ln -s "$PWD/skills/beforehand" ~/.claude/skills/beforehand   # install from your clone
export BEFOREHAND_STORE="<a throwaway folder outside any repository>"
sh dev/check_all.sh                                          # see green before you change anything
```

**The pre-commit hook.** `dev/pre-commit` runs `sh dev/check_generality.sh` from the repository
root and exits with its code, so a commit that would put a forbidden name, a machine path or
working material into the tree is refused. When `BEFOREHAND_DEV_TERMS` is set in your
environment it names your own term list (kept outside the repository) and the hook checks it
too. The symlink keeps the hook current as `dev/pre-commit` changes.

**The command line from a checkout.** `beforehand_cli/` is the `beforehand` command that `uvx`
installs (`install`, `uninstall`, `bundle`, `--version`, and every skill command passed
through). Run it from a checkout without installing anything as
`python3 -B -m beforehand_cli <command>`; the `-B` keeps `__pycache__` out of the tree
(check_generality refuses it). Point `install` at a throwaway place
(`--skills-dir DIR --agents-dir DIR`) rather than your own `~/.claude`, where the symlink
above is refused anyway. `claude plugin validate .` checks the plugin and the marketplace
manifests and passes with no warnings.

Set `BEFOREHAND_STORE` before you run anything, so nothing you do while developing lands in a
store you care about. Store resolution is `--store` > `BEFOREHAND_STORE` > `~/.beforehand`,
everywhere, with no exceptions. Three more variables exist for development only, all documented
in [`dev/README.md`](dev/README.md#environment-variables): `BEFOREHAND_DEV_TERMS` (a term list for
the generality gate, kept outside the repository), `BEFOREHAND_DEV_LOG` (the usage log
destination; unset means nothing is written), and `BEFOREHAND_LOCALE` / `BEFOREHAND_LOCALE_DIR`.

## Where things live

| Area | Path | What it is |
|---|---|---|
| The skill (ships) | [`skills/beforehand/`](skills/beforehand/) | `SKILL.md` (the router), `references/*.md` (six flows plus the evidence model), `assets/`, `agents/`, `scripts/` |
| Scripts | `skills/beforehand/scripts/` | `beforehand.py` (the entry point), `personas_lib.py` (frontmatter, sections, locales), one module per command, `test_*.py` beside them, `test_fixtures/` |
| Plugin manifest | [`.claude-plugin/plugin.json`](.claude-plugin/plugin.json) | name, version, author, `"skills": "./skills/"`, `"agents": ["./agents/persona-reviewer.md"]`; `marketplace.json` beside it makes the repository a single-plugin marketplace |
| Command line | [`beforehand_cli/`](beforehand_cli/) | the `uvx` front end (`cli.py`) and its tests (`test_cli.py`); `pyproject.toml` packages it with the skill and the agent as package data |
| Plugin-level agent | [`agents/persona-reviewer.md`](agents/persona-reviewer.md) | byte-identical to `skills/beforehand/agents/persona-reviewer.md` |
| Release gates (do not ship) | [`dev/`](dev/README.md) | `check_all.sh`, `check_generality.sh`, `public-identity.txt`, `pre-commit`, `check_router.sh`, `check_norms.sh`, `check_floor.py`, `norm-anchors.txt`, `build_skill.sh`, `check_all_versions.sh` |
| Behavioural evals | [`evals/`](evals/README.md) | `run.sh`, `cases/a`..`cases/g`, `expected/`, `lib/evalcheck.py` |
| Docs | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md), [`CHANGELOG.md`](CHANGELOG.md), [`LICENSE`](LICENSE) | the three layers and the rule table; the releases; MIT |
| Build output | `dist/` | gitignored; `dev/build_skill.sh` rebuilds it on demand |

Read [`skills/beforehand/README.md`](skills/beforehand/README.md) before changing anything in
the skill: it is the shortest accurate description of what the skill promises, and
[`README.md`](README.md) is its shorter counterpart for the repository.

## Ways to contribute

- **A script fix or a new check** in `skills/beforehand/scripts/`, with its case in the
  neighbouring `test_<module>.py`.
- **A test** for behaviour that is correct but unguarded — especially a refusing path (its exit
  code and its message) that no test pins today.
- **A fixture** under `scripts/test_fixtures/`: a lint edge case, a multi-voice transcript, an
  awkward path.
- **A reference**: a rule, its rationale in one clause, and where it is enforced.
- **A locale** under `scripts/locales/` (see [Locales](#locales)), or **an eval case** under
  `evals/cases/` with the mutation fixtures that prove its checker can fail.
- **Documentation**: the two READMEs, `docs/ARCHITECTURE.md`, this file.

Opening an issue first is welcome and never required. A short issue saying what you hit and what
you expected is more useful than a long one.

## The gate: `sh dev/check_all.sh`

One command runs everything. It exits 1 if any step fails, and ends on `check_all: ok` or
`check_all: FAIL`. There is no hosted CI, so nothing runs it for you: you run it by hand and say
so in the pull request. A red gate never ships — if a step fails for a reason you
believe is not yours, name the step and paste its output rather than working around it.

| # | Step | What it proves |
|---|---|---|
| 1 | `check_generality.sh --patterns-only` | no anecdote phrasing or maintainer name outside the exact public strings in `dev/public-identity.txt`, no `/Users/` or `/home/` path anywhere (binary files included), and no `__pycache__`, `.backup-*`, `skill-workspace` or `.superpowers` under the tree |
| 2 | `check_router.sh` | `SKILL.md` within its budget, one invocation form, no domain vocabulary in the router or the references |
| 3 | `check_norms.sh` | every phrase in `dev/norm-anchors.txt` matches exactly one file, and that file is `references/evidence-model.md` |
| 4 | anchor targets | every anchor on a line carrying `references/evidence-model.md#` — the first and each follow-on `` `#<X>` `` — under `skills/beforehand/`, `docs/`, `README.md` and `CONTRIBUTING.md` names a real `## <X>` heading |
| 5 | `beforehand.py test` | every suite, one `name: N/M passed` line each, run with `PYTHONDONTWRITEBYTECODE=1`; a suite that crashes, prints `0/0` or no summary line is `<suite>: no checks ran` and fails; a failing suite prints its `FAIL ` lines and the last 20 lines of its stderr |
| 6 | golden store | `reindex --dry-run` on the `golden` context reports `golden/INDEX.md` unchanged, and `doctor` ends on the pinned `doctor: healthy` |
| 7 | index determinism | real `reindex` writes on temporary copies of the golden store, with `reindex._today` mocked to 2027-01-10 and 2027-01-11 (days on which every golden persona is stale): copy A written on the first day and copy B written on the first day and again on the second are byte-identical, and the step fails if no staleness suffix is present |
| 8 | 3.9 syntax floor | `dev/check_floor.py`: every script, dev and evals module parses with `feature_version=(3, 9)`, with no PEP 604 union in an annotation (outside a file with `from __future__ import annotations`), no subscripted builtin at runtime, no parenthesised context manager, no `zip(strict=)`; walrus and `removeprefix` are legal |
| 9 | `ruff check --no-cache skills dev evals beforehand_cli` | style and imports; skipped with a notice when ruff is absent |
| 10 | `evals/run.sh --checkers-only` | the eval checkers, and the mutation and positive fixtures behind them; a fixture whose checker exits non-zero with no `FAIL ` line is reported as a crash (`the checker crashed`), never counted as a must-fail pass; nothing is written outside a temporary directory unless `EVALS_OUT` is set |
| 11 | `cli` | `beforehand_cli/test_cli.py` (runnable alone as `python3 -B beforehand_cli/test_cli.py`): install into a temporary HOME, every refusal, `--update`, uninstall of only what was installed, the bundle equal to `build_skill.sh`'s file list, the passthrough exit code, `--version`; nothing is written into the repository |

It then removes `__pycache__` under `skills/`, `evals/` and `beforehand_cli/`, and `.ruff_cache` at the root,
whether or not the run passed: both embed this machine's absolute paths, which step 1 would flag
on the next run.

**Environment.** `PYTHON` selects the interpreter for the suite and the store checks (default
`python3`). `RUFF` names the ruff binary. `REQUIRE_RUFF=1` turns the ruff skip into a failure
— use it if you have ruff, so a green run cannot mean a step quietly vanished. `sh dev/check_all_versions.sh` repeats the whole gate once per
Python 3.9 through 3.14 found on the machine.

## The rules that gate every change

Eight rules, each with the thing that enforces it.

**1. Publishable at every moment.** No real person, real organisation, maintainer identity, or
`/Users/…` / `/home/…` path anywhere in the tree — fixtures, comments, test data, eval
transcripts, binary files included. *Why:* a folder that is only privately clean is one `zip`
away from not being. *Enforced by:* `dev/check_generality.sh`, ending on `generality: clean`, run by the pre-commit
hook on every commit; the maintainer additionally runs it with a term list kept outside the
repository. The one exception is the project's own public identity — the author's name, the
repository slug and the owner handle, as the exact strings listed in `dev/public-identity.txt`;
any other spelling still fails. Everything
shipped lives in one synthetic universe: contexts `golden`, `northwind`, `ironbridge`; personas
`cfo-astrid`, `coo-mira`, `cto-jonas`, `cto-mara`, `coo-dana`.

**2. One norm, one file.** A rule the model follows is stated once, in
[`references/evidence-model.md`](skills/beforehand/references/evidence-model.md), and cited
everywhere else as `references/evidence-model.md#<Heading>`. *Why:* a rule restated in three
places is three rules on the day one of them is edited, and the model then follows whichever
copy it happened to load. *Enforced by:* `dev/check_norms.sh` (22 anchors today, one file each)
plus the anchor-target step of the gate. To add a norm: write it under its own heading in
`evidence-model.md`, add one distinctive single-line phrase to
[`dev/norm-anchors.txt`](dev/norm-anchors.txt), run `sh dev/check_norms.sh`. A norm belonging to
a flow rather than to the evidence model is tracked in `docs/ARCHITECTURE.md`'s rule table.

**3. The router is on a budget.** `SKILL.md`: at most 120 lines, 1,500 estimated tokens, a
400-character frontmatter description, one invocation form, no domain vocabulary. *Why:* the
router is loaded on every invocation, so everything in it is paid for whether or not it is used.
*Enforced by:* `dev/check_router.sh`, ending on `router: within budget`. It sits at 100 lines
and 1,489 tokens today, so new behaviour goes into a reference and the router gains at most a
pointer.

**4. Stdlib only, Python 3.9 floor, deterministic and offline.** No third-party import in
`scripts/`, no 3.10+ syntax, no network call, and no output that depends on the wall clock
unless the module exposes a `_today` hook the tests can mock. *Why:* the skill runs wherever the
host runs it with nothing installed, and an index that changes because a day passed is an index
nobody can diff. *Enforced by:* `dev/check_floor.py`, the determinism step, ruff's `py39`
target.

**5. Scripts propose, users confirm.** A command that changes a persona prints a diff and
writes only with `--apply` (`watchlist`, `migrate`, `forget`); `lint` blocks and never edits;
`doctor` always exits 0. *Why:* a profile is a judgment about a real person, and nothing edits
one on the user's behalf. *Enforced by:* the per-command contract in
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) Layer 2, and the module tests. A new command
follows the same contract and documents its exit codes in its `--help`.

**6. The store is never a repository.** `save` refuses a destination inside a store (exit 3) or
an unignored path in a git work tree (exit 4); tests and evals run only on throwaway copies of
`test_fixtures/store`; nothing here reads or writes `~/.beforehand`. *Why:* judgments about real
people must not be one commit away from a shared remote. *Enforced by:* `save_source.py`'s
refusals and the per-case temp store in `evals/run.sh`.

**7. Two copies, one text.** Three pairs stay byte-identical: `agents/persona-reviewer.md` and
`skills/beforehand/agents/persona-reviewer.md`; the four-space-indented example blocks in
`skills/beforehand/assets/reviewer-examples.md` and those in the agent prompt;
`docs/assets/beforehand-loop.svg` and `skills/beforehand/assets/beforehand-loop.svg`. *Why:* the
plugin loads one copy and the single-skill bundle carries the other, so a drift means two
different reviewers. *Enforced by:* `test_panel.py`, and `dev/build_skill.sh`, which refuses to
build on a drift.

**8. Every commit says what changed and why.** The history lives in git: a commit message states
what changed *and why it was worth changing*, and a pull request says the same for the whole
branch. `CHANGELOG.md` records releases only, and the maintainer writes its entry at release
time. *Why:* a diff shows what changed; only the message can say why. *Enforced by:* review —
this one has no script, which is why it is on the checklist.

## Working on the skill prose

The prose is `SKILL.md`, the seven files under `references/`, `assets/persona-template.md`,
`assets/reviewer-examples.md`, and `agents/persona-reviewer.md`.

- **Every command is written as `python3 $SKILL/scripts/beforehand.py <command>`.** Never
  `python3 scripts/<module>.py`. `check_router.sh` counts bare invocations anywhere under
  `skills/beforehand/` and allows zero.
- **The evidence model owns the norms.** Its headings today are Labels, Tag contract,
  Promotions, Source type, Provenance, Admissibility, Empty sections, Declared and demonstrated,
  Post-review, Watchlist, Writes and confirmations, Glossary. Cite one of those anchors rather
  than restating what is under it; the gate fails on an anchor with no matching `## ` heading.
- **Domain vocabulary stays out of prose.** The words deal, client, vendor, CFO and CTO are
  counted by `check_router.sh` over `SKILL.md` and `references/*.md`, and allowed only inside
  backticks, quotes and fences, where they are examples of a role rather than our own language.
  `sh dev/check_router.sh --report-references` downgrades the reference-scoped counts to a
  report while you iterate on the router alone.
- **Test prose by using it.** Symlink-install the skill, point `BEFOREHAND_STORE` at a copy of the
  golden fixture store, run the flow, and read the transcript. Prose that reads well and routes
  badly is the failure mode here.

## Working on the scripts

- **`beforehand.py` is the entry point.** Fourteen commands: `lint`, `save`, `reindex`, `pending`,
  `speakers`, `coverage`, `watchlist`, `calibrate`, `panel`, `doctor`, `migrate`, `forget`,
  `log`, `test`. `beforehand.py --help` prints one line per command with its exit codes;
  `beforehand.py <command> --help` prints that module's own argparse help, whose usage line reads
  `beforehand.py <command>`.
- **Exit codes are a contract** and pass through the entry point unchanged. The conventions in
  use: 0 ok; 1 usage, or a blocking violation for `lint`; 2 "not gradeable", "would lose
  content", or unresolved speakers; 3 a dubious turn in `speakers`, or a destination inside a
  store for `save`; 4 a git work tree for `save`. Assert them exactly in tests, and never assert
  on today's date or on an absolute path.
- **Shared parsing goes through `personas_lib.py`** — frontmatter, the section splitter,
  `get_locale()` and `locale_regexes()`, the one source resolver `resolve_source` (a relative
  ref resolves under `sources_root` only, never the working directory) and `parse_iso_date`.
  Store writes go through `atomic_write`, appends through `append_line`, reads through
  `read_text_lenient`. Do not add a second frontmatter parser, resolver or date parser.
- **A new module ships with `test_<module>.py` beside it.** `beforehand.py test` discovers
  `test_*.py` by glob and prints one `name: N/M passed` line per suite. `test_bench.py` keeps a
  full lint of the golden store under five seconds.
- **Every script and test module sets `sys.dont_write_bytecode` before any sibling import,**
  so a real run leaves no `__pycache__`, even through a symlinked skill directory or a module
  or suite run directly; `test_entrypoint.py` checks the order statically over every
  `scripts/*.py`, so a new module must do the same. Ad-hoc imports from your own
  shell still can, so run those with `PYTHONDONTWRITEBYTECODE=1`.
- **Naming is part of the contract.** `save` writes `<date>-<slug>.md`, normalising the extension
  so the same text saved on stdin and from a file is one record and not two; `--keep-extension`
  opts out and keeps the source file's extension.

## Fixtures and the golden store

Everything under `skills/beforehand/scripts/test_fixtures/` is synthetic, English, and says so.
The golden store is `test_fixtures/store/golden/` — `context.md`, `INDEX.md`, `AUDIT.md`,
`personas/{cfo-astrid,coo-mira,cto-jonas}.md`, `sources/`, `docs/`, `reviews/`, `calibration/` —
with `northwind/` and `ironbridge/` beside it. Feature fixtures sit alongside: `store-0.1/` and
`store-0.1-lossy/` for migration, then `joined/`, `watchlist/`, `multivoice/`, `panel/`,
`calibrate/`, `placement/`, `inherited/`, `variants/`, `locale-samples/`, `locales/xx.json`, and
`paths/`, which holds a directory with a comma in its name and one with spaces, on purpose.

**The committed fixture store is never written to**: a test or an eval that needs to write
copies it to a temp directory first. **After editing anything under `store/golden/`**, run what
step 6 of the gate runs and commit the regenerated `INDEX.md`, so "unchanged" stays true:

```bash
S=skills/beforehand/scripts
python3 $S/beforehand.py reindex --store $S/test_fixtures/store --context golden --dry-run
python3 $S/beforehand.py doctor  --store $S/test_fixtures/store --context golden --today 2026-09-17
```

## Evals

The script suites test the scripts. The [evals](evals/README.md) test the *skill*: whether the
model, running the real references against a real store, does what the spec says.

```bash
sh evals/run.sh                     # free and deterministic; this is what the gate runs (the default)
sh evals/run.sh --live              # the live pass: one host session per case, two for `g`
```

A live pass costs a session per case, so the default, checkers-only, is the day-to-day command: it replays
the synthetic transcripts and store overlays under `evals/expected/` through the same checkers.
Those files are synthetic expected outputs, not recorded runs, and each says so in its first
lines. `EVALS_CLI` names the host CLI (default `claude`); results land under
`${EVALS_OUT:-~/.beforehand-dev/evals}/<date>/` for a live run, never inside the repository and
with home paths scrubbed; a `--checkers-only` replay writes only into its temporary work
directory unless `EVALS_OUT` is set. Each case gets a throwaway copy of the fixture store; no
case touches `~/.beforehand`. Live case `g` is refused while `~/.claude/skills/beforehand`
exists, since a user-level skill would load in both arms of its comparison
(`EVALS_ALLOW_USER_SKILL=1` overrides).

A case is `evals/cases/<x>/prompt.md` and `check.py`, optionally `setup.sh` and `rubric.md`,
plus `mutations/*.md` (transcripts that must **fail** the checker) and `positives/*.md`
(transcripts that must **pass** it). Assertions print named `ok` / `FAIL` lines; "the output is
not empty" is never an assertion, because it passes on a run that did the wrong thing. Write the
checker, then try to make it pass on a transcript that did the wrong thing — a checker that has
never failed has not been tested.

## Locales

Only `en` ships, at `skills/beforehand/scripts/locales/en.json`. Its keys are `same_source`,
`excerpt_joiners`, `generic_speaker`, `header_labels`, `empty_section`,
`watchlist_repeat_clause`, `snapshot_fields` (itself an object with `meeting`, `review_date`,
`document`) and `filler_tokens` (the words lint ignores when it compares an excerpt with its
source). English is always loaded first and a second locale is merged on top of it, so a
locale file states only what it *adds*. Try one before proposing it, without adding it to the
shipped directory:

```bash
BEFOREHAND_LOCALE=xx BEFOREHAND_LOCALE_DIR=<your locales folder> \
    python3 skills/beforehand/scripts/beforehand.py <command> ...
```

The words a locale recognises belong in `scripts/test_fixtures/locale-samples/`, never inside a
`.py` file: the acceptance check for that rule is a grep over `scripts/*.py` for exactly those
words, and a test proving a locale works must not itself be a hit. `test_fixtures/locales/xx.json`
is a locale that exists only to prove the mechanism in `test_locale.py`, and is never shipped.

## Before you open a pull request

- [ ] `sh dev/check_all.sh` ends on `check_all: ok` — paste that last line in the pull request;
      there is no CI to do it for you
- [ ] `REQUIRE_RUFF=1 sh dev/check_all.sh` if you have ruff, so the ruff step actually ran
- [ ] `sh dev/check_generality.sh` still prints `generality: clean` (the pre-commit hook runs it
      on every commit; the maintainer reruns it with the term list)
- [ ] new script behaviour has a case in `test_<module>.py`, including the refusing path — its
      exit code and its message
- [ ] a rule you added or moved is stated once, in `references/evidence-model.md`, and
      `sh dev/check_norms.sh` reports `one file each`
- [ ] `SKILL.md` untouched, or `sh dev/check_router.sh` ends on `router: within budget`
- [ ] fixtures you added are synthetic and say so: no real name, organisation or path
- [ ] a pull request against `main`, from a branch of your fork, whose commits say what changed
      and why it was worth changing
- [ ] `sh dev/build_skill.sh` still builds, so the byte-identical pairs are intact
- [ ] no `__pycache__`, `*.pyc`, `.ruff_cache`, `.DS_Store` or `dist/` in the diff

## What we will not merge

1. A real person, a real organisation, or the maintainer's identity anywhere in the tree,
   including fixtures, eval transcripts and comments.
2. An absolute machine path (`/Users/…`, `/home/…`) anywhere, including inside a `.pyc` or an
   eval result. Write `$SKILL`, `~`, or `<store>`.
3. `__pycache__/`, `*.pyc`, `.ruff_cache/`, `.DS_Store`, `dist/`, `.backup-*`,
   `skill-workspace/`, `.superpowers/` or `.claude/settings.local.json` in the diff.
4. A `SKILL.md` over budget. Add to a reference, and at most a pointer line to the router.
5. A norm of the evidence model restated outside `references/evidence-model.md`, or an anchor
   cited that has no `## ` heading there.
6. `python3 scripts/<module>.py` in a shipped file, or the words deal, client, vendor, CFO or
   CTO in router or reference prose outside backticks, quotes and fences.
7. Anything that reads or writes `~/.beforehand`, or a test, eval or example pointed at it.
8. A test or eval that writes into the committed `test_fixtures/store`, or anything that writes
   results back into the repository.
9. A third-party dependency, a `requirements.txt`, a network call, or 3.10+ syntax under
   `skills/beforehand/scripts/`.
10. One half of a byte-identical pair, edited alone.
11. A script that edits a persona without `--apply`, a linter that rewrites what it checks, a
    `doctor` that exits non-zero, or a hook in `.claude-plugin/plugin.json` — the usage logger
    is opt-in, lives outside this repository, and is registered in the contributor's own
    settings, never here.
12. A version bump, a tag, a `CHANGELOG.md` entry, a change to the manifests' author or to
    `LICENSE`, a new string in `dev/public-identity.txt`, a hand-edited `INDEX.md` (derived —
    `reindex` regenerates it) or a derived `AUDIT.md` (hand-appended only).

## Sized first contributions

**Small.** Add a sample word for an existing `en.json` key under
`scripts/test_fixtures/locale-samples/`, with the matching line in `test_locale.py`. Or add a
`mutations/` fixture to an eval case that has none, and confirm the case fails when that
mutation passes.

**Medium.** Add a `test_fixtures/` scenario for a `lint` edge case — `MISPLACED`,
`UNVERIFIABLE`, a joined tag — with its case in `test_verify_quotes.py`, including the exit code
the case must produce.

**Large.** Add a second shipped locale under `scripts/locales/`, exercised through
`BEFOREHAND_LOCALE_DIR` first and with its samples under `locale-samples/`. Or verify the Claude
Cowork install end to end — the `.skill` bundle from its archive root, and the plugin's
`"skills": "./skills/"` discovery — and write the result into the host tables in the two READMEs,
which say "not yet verified" precisely because nobody has.

## Releases and versioning

Releases are maintainer-driven, and contributors never do any part of them.

- The version is stated in `.claude-plugin/plugin.json`, and `dev/build_skill.sh` reads it
  from there. The marketplace entry, `pyproject.toml`, `beforehand_cli/__init__.py` and the two
  README badges state it again, and `test_entrypoint.py` fails if any of them drifts from
  plugin.json. Do not bump it in a pull request.
- `sh dev/build_skill.sh` writes `dist/beforehand-<version>.skill`, a zip of
  `skills/beforehand/` rooted at `beforehand/`, with `__pycache__` and `.DS_Store` stripped.
  `dist/` is gitignored and rebuilt on demand.
- A release is a tag `v<version>` on `main` and a GitHub Release carrying
  `beforehand-<version>.skill`; `CHANGELOG.md` gets one entry per release.
- What is deliberately outstanding, and already decided, is listed in
  [`dev/README.md`](dev/README.md#10-checklist): the live eval pass, the Cowork and Desktop
  verification, the `SKILL.md` token cap, and CI (none for now).

## Questions, capacity, license

Open an issue. A question about why a rule exists is a good issue: if the answer is not already
next to the rule, that is a documentation bug. This project is maintained in spare time, so a
reply and a review land when they can rather than when you would like them to — which is also
why the gate is one command: the more of it you have already run, the less of it is in the way.

By contributing you agree that your contribution is licensed under the MIT license, the same as
the rest of the project — see [`LICENSE`](LICENSE).

All examples and fixtures here are synthetic. Halden Logistics does not exist.
