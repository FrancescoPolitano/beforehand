# beforehand

[![version 1.0.1](https://img.shields.io/badge/version-1.0.1-0969da)](CHANGELOG.md)
![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-3776ab)
![stdlib only](https://img.shields.io/badge/dependencies-stdlib%20only-2da44e)
![local-first, no telemetry](https://img.shields.io/badge/data-local--first%20%C2%B7%20no%20telemetry-8250df)
![hosts: Code yes, Cowork unverified, Desktop consult-only](https://img.shields.io/badge/hosts-Code%20%E2%9C%93%20%C2%B7%20Cowork%20%28unverified%29%20%C2%B7%20Desktop%20consult--only-57606a)
![tests: 17 suites](https://img.shields.io/badge/tests-17%20suites-2da44e)
[![license MIT](https://img.shields.io/badge/license-MIT-656d76)](LICENSE)

*evidence-based stakeholder panels*

A Claude skill that rehearses how specific, known people will react to a document before they
see it. From sources you own — transcripts, emails, notes — it builds a profile where every
trait is labeled Fact, Inference or Assumption, every Fact carries the excerpt and the file it
came from, and a deterministic linter checks that the excerpt is really there. That profile
then stress-tests a draft, rehearses a conversation, or answers a question as that person
would, and its predictions are graded afterwards against what the person actually did.

Local-first: the store lives outside any repository, nothing leaves the machine, and nothing
enters a profile unlabeled.

A profile holds how someone judges and decides — mandate, judgment criteria, recurring
objections, red lines, dissent style, panel dynamics — and not their tastes, personality or
private life. The skill README spells out
[what is tracked and what deliberately is not](skills/beforehand/README.md#what-we-track-about-a-person--and-what-we-dont).

![The beforehand loop: sources feed a persona of labeled, lint-gated claims; the persona is convened in a panel of isolated reviewers alongside a control reviewer; the panel freezes a snapshot of its predictions before the meeting; afterwards, calibrate grades them into precision and coverage and feeds the result back into the persona.](docs/assets/beforehand-loop.svg)

## Install

**Claude Code, as a plugin** — the repository is its own single-plugin marketplace:

```bash
claude plugin marketplace add FrancescoPolitano/beforehand
claude plugin install beforehand@beforehand
```

**Claude Code, without the plugin system** — the `beforehand` command line, run with
[uv](https://docs.astral.sh/uv/)'s `uvx` (nothing to install first):

```bash
uvx --from git+https://github.com/FrancescoPolitano/beforehand beforehand install
```

It copies the skill to `~/.claude/skills/beforehand` and the reviewer agent to
`~/.claude/agents/persona-reviewer.md`, and prints what it wrote:

```
wrote ~/.claude/skills/beforehand/ (181 files)
wrote ~/.claude/skills/beforehand/.installed-by-beforehand
wrote ~/.claude/agents/persona-reviewer.md
installed beforehand 1.0.1
```

It copies, never symlinks, and it refuses (exit 1, with the reason) rather than overwrite
something it did not put there: a destination that is a symlink is never written through, a
skill directory without its `.installed-by-beforehand` marker is left alone, and an existing
install or a different agent file is replaced only with `--update`. The copy is staged beside
the target and swapped in, so an install is never half done. The same command upgrades and
removes:

```bash
uvx --from git+https://github.com/FrancescoPolitano/beforehand beforehand install --update
uvx --from git+https://github.com/FrancescoPolitano/beforehand beforehand uninstall
```

`uninstall` removes only a skill directory carrying the marker and an agent file identical
to the one this version ships. Both commands take `--skills-dir DIR --agents-dir DIR` for
other locations. `beforehand --version` prints `beforehand 1.0.1`; any other command is the
skill's own (`beforehand doctor`, `beforehand test`, `beforehand help` for the list).

**Claude Cowork, or any host that installs a skill archive** — expected to work, not yet
verified end to end. Download `beforehand-1.0.1.skill` from the
[Releases page](https://github.com/FrancescoPolitano/beforehand/releases), or build it with
`uvx --from git+https://github.com/FrancescoPolitano/beforehand beforehand bundle`
(it writes `beforehand-1.0.1.skill` into the current folder, or into `--out DIR`), install it the way the
host installs a skill, and choose where the store lives:

```bash
export BEFOREHAND_STORE="<a folder you choose, outside any repository>"
```

**Claude Desktop** — consult only. The filesystem is ephemeral, so there is no store to keep;
you can ask about a document with a profile supplied in the conversation, and nothing persists.

**Development** — a symlink from a clone, so your edits are live (the installer refuses to
write through this link, by design):

```bash
git clone https://github.com/FrancescoPolitano/beforehand
cd beforehand
ln -s "$PWD/skills/beforehand" ~/.claude/skills/beforehand
```

[`CONTRIBUTING.md`](CONTRIBUTING.md) takes it from there.

## Quickstart

```bash
# put a source on disk, intact, with its provenance header
python3 $SKILL/scripts/beforehand.py save --dir ./sources --date 2026-07-03 --what call-of-3-july \
  --ref "call of 3 July" --type private-communication --provenance machine-transcribed < transcript.txt

# settle who actually speaks in it before extracting anything
python3 $SKILL/scripts/beforehand.py speakers ./sources/2026-07-03-call-of-3-july.md

# read-only diagnosis of the context you are about to work in
python3 $SKILL/scripts/beforehand.py doctor --context halden
```

If you have the `beforehand` command from `uvx` (see Install above), it is a shorter form of
the same calls — `beforehand save …`, `beforehand speakers …`, `beforehand doctor …` — since
anything past its own commands (`install`, `uninstall`, `bundle`, `help`) passes straight
through to its bundled `scripts/beforehand.py`, byte-identical to the one under `$SKILL`.

Then, in the session: *"build a persona for halden from ./sources/2026-07-03-call-of-3-july.md"*,
accept the proposed file, and *"stress-test ./proposal.md for halden"*. `$SKILL` is the skill
directory; the store defaults to `~/.beforehand`. Where the skill directory is depends on how you installed:
`~/.claude/skills/beforehand` after `uvx … beforehand install`, or
`~/.claude/plugins/cache/beforehand/beforehand/1.0.1/skills/beforehand` after the plugin-marketplace
route (the cache path is versioned, so it moves on upgrade).

A named label is not the same thing as one voice: a conference room arrives as one name, so
`speakers` prints a `POSSIBLE SHARED MICROPHONE.` block whenever the text carries clues of
one. That block is common rather than rare — a legitimate call where someone names their own
label or answers their own question trips it — and it is warn-only: no exit code changes, and
a clean run is not evidence of a single voice. When you have confirmed the room, record it in
your own words with `--map "<label>=room: <who speaks>, <N> present"`.

## Proactive offers (optional)

`beforehand` does not watch what you do: it runs when you ask it to. Its offer rules —
proposing an update when new material about someone you already track enters the session,
flagging a prediction snapshot that has come due — apply only once the skill is loaded, and the
skill loads when your request matches what it is for.

To make those rules fire while you work, add this line to your agent's context file
(`CLAUDE.md` for Claude Code, `AGENTS.md` for agents that follow that convention), in the
directory where you keep meeting material:

> When a transcript, an email or call notes naming someone already in the `beforehand` store
> enter the session, invoke the skill and let it decide whether to offer an update. An offer
> executes nothing: you accept it.

For an overdue snapshot the sturdier route is not an instruction but a session-start hook that
runs `doctor`: it is deterministic and has no false positives.

**Other agents.** The scripts are plain Python 3.9 stdlib behind one command line, so they run
under any agent or none. The references are markdown and travel as text. What does not travel
is the isolation: a panel is worth what its separation is worth, and `enforced-tools`
isolation — where the host, not the prompt, holds a reviewer to its two files — is Claude
Code's. Elsewhere the review flow degrades to `staged`, `inline` or `emulated`, which it names
and requires you to disclose per persona.

## Repository

| Path | What is in it |
|---|---|
| [`skills/beforehand/README.md`](skills/beforehand/README.md) | the skill: flows, evidence model, all 14 commands, what a review looks like, host support, responsible use, limits |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | three layers — what the scripts guarantee, what they explicitly do not, and which rules rest on the prompt alone |
| [`CHANGELOG.md`](CHANGELOG.md) | the releases; from 1.0 the history is in git |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | how to work on this: the gate, the eight rules that gate every change, the pull-request checklist |
| `dev/` | the gate scripts (`check_all.sh` and the checks it calls), the `pre-commit` hook, `build_skill.sh`, `norm-anchors.txt` and `public-identity.txt`. Not part of the skill |
| `beforehand_cli/` | the `beforehand` command line behind `uvx` (install, uninstall, bundle) and its tests. Not part of the skill |
| [`evals/`](evals/README.md) | the behavioural evals: seven cases, their checkers and their synthetic transcripts. Not part of the skill |

The whole repository is also a Claude Code plugin: `.claude-plugin/plugin.json` declares
`skills/` and `agents/`. No hooks ship: the development usage logger is opt-in and lives
outside this repository (see `dev/README.md`).

## Status

**1.0.1** — a fix release after the first public one (1.0.0); usable and used daily. The history lives in git from
1.0 on. `sh dev/check_all.sh` is the gate: 17 test suites, the router budget, the norm
anchors, the generality scan, the golden-store and determinism checks, the 3.9 syntax floor,
ruff, the eval checkers and the command-line tests. [`CONTRIBUTING.md`](CONTRIBUTING.md) is
how to run all of it.

## Honest limits

Calibration here is a longitudinal case study, not a controlled experiment: small n, a single
observer, assisted matching. Nothing here claims accuracy. It claims that every trait is
traceable to something a real person actually said, and that you will know how often the panel
was right.

All examples and fixtures are synthetic. Halden Logistics does not exist.

## License

MIT — see [`LICENSE`](LICENSE).
