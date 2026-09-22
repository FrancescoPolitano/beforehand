#!/usr/bin/env python3
"""Tests for panel.py (FR-5.2, FR-5.1) — the reviewer-output validator and the aggregator.

Every check runs the module as a subprocess and asserts the exit code exactly, because the
exit codes are the contract the flow branches on (`--validate` 0 ok / 1 schema error). The
roster is the golden fixture index, read but never written; the reviewer outputs live in
`test_fixtures/panel/` and are copied into a temporary directory whenever a check needs a
variant of one.
"""
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True  # G5: a suite run on its own leaves no __pycache__

HERE = Path(__file__).parent
PANEL = HERE / "panel.py"
ENTRY = HERE / "beforehand.py"
FIX = HERE / "test_fixtures/panel"
ROSTER = HERE / "test_fixtures/store/golden/INDEX.md"
SKILL = HERE.parent
AGENT = SKILL / "agents/persona-reviewer.md"
REVIEW = SKILL / "references/review.md"
checks = []
TMP = Path(tempfile.mkdtemp())


def run(*a):
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run([sys.executable, *map(str, a)], capture_output=True, text=True,
                          env=env)


def panel(*a):
    return run(PANEL, *a)


def rows(out, first_cell):
    """Data rows of a markdown table whose first column holds `first_cell`-like values."""
    return [ln for ln in out.splitlines()
            if ln.startswith("| ") and ln.split("|")[1].strip() == first_cell]


def section(out, heading):
    """The lines of one `## heading` section, heading excluded."""
    got, on = [], False
    for ln in out.splitlines():
        if ln.startswith("## "):
            on = ln.strip() == heading
            continue
        if on:
            got.append(ln)
    return "\n".join(got).strip()


def table_rows(out, heading):
    body = section(out, heading)
    return [ln for ln in body.splitlines()
            if ln.startswith("|") and set(ln.replace("|", "").strip()) != {"-"}
            and not ln.startswith("| Persona A |") and not ln.startswith("| Persona |")]


def first(lst):
    """The first row, or an empty string: a failing check must still print its evidence."""
    return lst[0] if lst else ""


def stage(name, sources):
    """A temp directory holding copies of the named fixture files."""
    d = TMP / name
    d.mkdir(parents=True, exist_ok=True)
    for src in sources:
        shutil.copy(str(FIX / src), str(d / Path(src).name))
    return d


# --------------------------------------------------------------- 1. --validate, valid
for fname in ("round1/cfo-astrid.md", "round1/cto-jonas.md", "round1/coo-mira.md",
              "round2/cfo-astrid-round2.md"):
    r = panel("--validate", FIX / fname)
    checks.append((f"--validate accepts {fname} (exit 0)", r.returncode == 0,
                   (r.returncode, r.stdout, r.stderr)))
    checks.append((f"--validate prints no schema error for {fname}",
                   "schema error" not in r.stdout + r.stderr, (r.stdout, r.stderr)))

# --------------------------------------------------------------- 2. --validate, malformed
MALFORMED = [
    ("malformed/bad-severity.md", "objections[0].severity"),
    ("malformed/missing-read.md", "read"),
    ("malformed/bad-grounds.md", "objections[0].grounds"),
    ("malformed/round2-with-objections.md", "objections"),
    ("malformed/criteria-missing.md", "criteria"),
    ("malformed/criteria-bad-verdict.md", "criteria[0].verdict"),
    ("malformed/criteria-met-no-evidence.md", "criteria[0].evidence"),
    ("malformed/criteria-not-addressed-with-evidence.md", "criteria[0].evidence"),
]
for fname, path in MALFORMED:
    r = panel("--validate", FIX / fname)
    checks.append((f"--validate rejects {fname} (exit 1)", r.returncode == 1,
                   (r.returncode, r.stdout, r.stderr)))
    checks.append((f"--validate names the json path {path} in stdout for {fname}",
                   r.stdout.startswith(f"schema error at {path}: "),
                   (r.stdout, r.stderr)))

r = panel("--validate", FIX / "no-block.md")
checks.append(("--validate rejects a file with no `json personas-review` block (exit 1)",
               r.returncode == 1, (r.returncode, r.stdout)))
checks.append(("the missing-block error is a schema error line",
               r.stdout.startswith("schema error at $: "), r.stdout))

r = panel("--validate", TMP / "does-not-exist.md")
checks.append(("--validate on a missing file exits 1", r.returncode == 1,
               (r.returncode, r.stdout, r.stderr)))

bad_json = TMP / "bad-json.md"
bad_json.parent.mkdir(parents=True, exist_ok=True)
bad_json.write_text("```json personas-review\n{\"schema\": \"0.2\",\n```\n", encoding="utf-8")
r = panel("--validate", bad_json)
checks.append(("--validate on unparseable JSON exits 1 with a schema error",
               r.returncode == 1 and r.stdout.startswith("schema error at $: "),
               (r.returncode, r.stdout)))

# --------------------------------------------------------------- 3. --aggregate
r = panel("--aggregate", FIX / "round1", "--roster", ROSTER)
agg = r.stdout
checks.append(("--aggregate on three valid outputs exits 0", r.returncode == 0,
               (r.returncode, r.stdout, r.stderr)))
checks.append(("the six pinned sections are printed, in order, with `## Criteria` fifth",
               [ln for ln in agg.splitlines() if ln.startswith("## ")] ==
               ["## Round-1 objections", "## Red-line violations", "## Shared anchors",
                "## Blind spots", "## Criteria", "## Method counts"],
               [ln for ln in agg.splitlines() if ln.startswith("## ")]))

r1_rows = table_rows(agg, "## Round-1 objections")
checks.append(("the Round-1 table has 3 + 2 + 1 rows", len(r1_rows) == 6, r1_rows))
checks.append(("3 of the Round-1 rows are cfo-astrid's",
               len([ln for ln in r1_rows if ln.split("|")[1].strip() == "cfo-astrid"]) == 3,
               r1_rows))
checks.append(("the Round-1 header carries Context and Isolation next to the snapshot columns",
               "| Persona | Context | Isolation | Anchor in the document | Objection | "
               "Severity | Round tag | Event | Role-generic | Doc changed |" in agg, agg[:800]))
checks.append(("the isolation shape of each output reaches its rows",
               all(f"| {shape} |" in "\n".join(r1_rows)
                   for shape in ("enforced-tools", "staged", "inline")), r1_rows))
checks.append(("the context comes from the roster's directory",
               all("| golden |" in ln for ln in r1_rows), r1_rows))
checks.append(("cells the model must fill are marked, and Role-generic without a control "
               "round reads `estimated`, never a guessed yes/no",
               all(ln.rstrip().endswith("| ? | estimated | ? |") for ln in r1_rows), r1_rows))
checks.append(("the aggregate opens with the snapshot's control header",
               agg.splitlines()[0] == "control: no" if agg else False,
               agg.splitlines()[:2]))

red = table_rows(agg, "## Red-line violations")
checks.append(("exactly one red-line row", len(red) == 1, red))
checks.append(("the red-line row is the contract-term objection",
               "cfo-astrid" in first(red) and "break clause" in first(red), red))

shared = table_rows(agg, "## Shared anchors")
checks.append(("exactly one shared-anchor pair", len(shared) == 1, shared))
checks.append(("the shared-anchor pair names both personas",
               "cfo-astrid" in first(shared) and "cto-jonas" in first(shared), shared))

blind = section(agg, "## Blind spots")
checks.append(("blind spots are grouped by persona",
               blind.count("- cfo-astrid") == 1 and blind.count("- cto-jonas") == 1
               and blind.count("- coo-mira") == 1, blind))
checks.append(("every no_basis item is listed",
               blind.count("  - ") == 2 + 1 + 2, blind))

method = table_rows(agg, "## Method counts")
checks.append(("one method-counts row per persona with an output", len(method) == 3, method))
checks.append(("mean severity is computed per persona",
               "| cfo-astrid | golden | 3 | 4.0 | NO | enforced-tools |" in agg
               and "| cto-jonas | golden | 2 | 3.0 | NO | staged |" in agg
               and "| coo-mira | golden | 1 | 3.0 | INSUFFICIENT_BASIS | inline |" in agg,
               method))

# --------------------------------------------------------------- 4. --json mirrors it
r = panel("--aggregate", FIX / "round1", "--roster", ROSTER, "--json")
checks.append(("--aggregate --json exits 0", r.returncode == 0, (r.returncode, r.stderr)))
try:
    data = json.loads(r.stdout)
except ValueError:
    data = None
checks.append(("--json is parseable and mirrors the six sections",
               isinstance(data, dict) and set(data) >= {"round1", "red_lines", "shared_anchors",
                                                        "blind_spots", "method_counts",
                                                        "criteria"},
               r.stdout[:400]))
if isinstance(data, dict):
    checks.append(("--json round1 has the six objections", len(data["round1"]) == 6,
                   len(data["round1"])))
    checks.append(("--json red_lines has one entry", len(data["red_lines"]) == 1,
                   data["red_lines"]))
    checks.append(("--json shared_anchors has one pair with its overlap",
                   len(data["shared_anchors"]) == 1
                   and data["shared_anchors"][0]["overlap"] >= 0.6, data["shared_anchors"]))
    checks.append(("--json blind_spots is grouped by persona",
                   sorted(data["blind_spots"]) == ["cfo-astrid", "coo-mira", "cto-jonas"],
                   data["blind_spots"]))
    checks.append(("--json method_counts carries counts, mean, greenlight and isolation",
                   {m["persona"]: (m["objections"], m["mean_severity"], m["greenlight"],
                                   m["isolation"]) for m in data["method_counts"]} ==
                   {"cfo-astrid": (3, 4.0, "NO", "enforced-tools"),
                    "cto-jonas": (2, 3.0, "NO", "staged"),
                    "coo-mira": (1, 3.0, "INSUFFICIENT_BASIS", "inline")},
                   data["method_counts"]))
    checks.append(("--json round1 rows carry the isolation shape",
                   {o["isolation"] for o in data["round1"]} ==
                   {"enforced-tools", "staged", "inline"},
                   [o["isolation"] for o in data["round1"]]))
    checks.append(("--json carries the control header as a field",
                   data.get("control") == "no", data.get("control")))
    checks.append(("--json round1 rows carry the row key and an estimated role-generic",
                   {o.get("role_generic") for o in data["round1"]} == {"estimated"}
                   and [o.get("key") for o in data["round1"]][:3] ==
                   ["cfo-astrid#1", "cfo-astrid#2", "cfo-astrid#3"],
                   [(o.get("key"), o.get("role_generic")) for o in data["round1"]]))

# --------------------------------------------------------------- 5. what the aggregate refuses
d = stage("with-malformed", ["round1/cfo-astrid.md", "malformed/bad-severity.md"])
r = panel("--aggregate", d, "--roster", ROSTER)
checks.append(("a malformed output in the directory stops the aggregate (exit 1)",
               r.returncode == 1, (r.returncode, r.stdout)))
checks.append(("the refusal names the file and the json path",
               "bad-severity.md" in r.stdout and "objections[0].severity" in r.stdout,
               r.stdout))

d = stage("unknown-slug", ["round1/cfo-astrid.md"])
txt = (d / "cfo-astrid.md").read_text(encoding="utf-8").replace('"persona": "cfo-astrid"',
                                                                '"persona": "cfo-nobody"')
(d / "cfo-astrid.md").write_text(txt, encoding="utf-8")
r = panel("--aggregate", d, "--roster", ROSTER)
checks.append(("an output whose persona is not in the roster stops the aggregate (exit 1)",
               r.returncode == 1 and "cfo-nobody" in r.stdout, (r.returncode, r.stdout)))
checks.append(("the refusal sends a foreign persona to its own context's aggregate",
               "cfo-nobody is not in this roster: aggregate its context separately" in r.stdout,
               r.stdout))

r = panel("--aggregate", TMP / "not-a-directory", "--roster", ROSTER)
checks.append(("--aggregate on a missing directory exits 1", r.returncode == 1,
               (r.returncode, r.stdout, r.stderr)))

d = stage("empty-dir", [])
r = panel("--aggregate", d, "--roster", ROSTER)
checks.append(("--aggregate on an empty directory exits 1", r.returncode == 1,
               (r.returncode, r.stdout, r.stderr)))

# --------------------------------------------------------------- 6. notes the flow needs
d = stage("one-persona", ["round1/cfo-astrid.md"])
r = panel("--aggregate", d, "--roster", ROSTER)
checks.append(("a roster persona with no output is named, not silently dropped",
               r.returncode == 0 and "no round-1 output: coo-mira, cto-jonas" in r.stdout,
               (r.returncode, r.stdout)))

d = stage("with-round2", ["round1/cfo-astrid.md", "round1/cto-jonas.md",
                          "round1/coo-mira.md", "round2/cfo-astrid-round2.md"])
r = panel("--aggregate", d, "--roster", ROSTER)
checks.append(("a round-2 output never enters the round-1 table",
               r.returncode == 0 and len(table_rows(r.stdout, "## Round-1 objections")) == 6,
               (r.returncode, table_rows(r.stdout, "## Round-1 objections"))))
checks.append(("the later round is reported in Method counts",
               "later rounds: cfo-astrid round 2" in r.stdout, r.stdout))

d = stage("no-isolation", ["round1/cfo-astrid.md"])
txt = (d / "cfo-astrid.md").read_text(encoding="utf-8").replace("isolation: enforced-tools\n", "")
(d / "cfo-astrid.md").write_text(txt, encoding="utf-8")
r = panel("--aggregate", d, "--roster", ROSTER)
checks.append(("an unannotated output stops the aggregate instead of getting a fifth value",
               r.returncode == 1 and "isolation missing for cfo-astrid" in r.stdout,
               (r.returncode, r.stdout)))
checks.append(("the isolation refusal names the four shapes",
               "enforced-tools | staged | inline | emulated" in r.stdout, r.stdout))
checks.append(("no guessed isolation value reaches the output",
               "unrecorded" not in r.stdout, r.stdout))

d = stage("late-isolation", ["round1/cfo-astrid.md"])
txt = (d / "cfo-astrid.md").read_text(encoding="utf-8")
txt = txt.replace("isolation: enforced-tools\n", "") + "\nisolation: emulated\n"
(d / "cfo-astrid.md").write_text(txt, encoding="utf-8")
r = panel("--aggregate", d, "--roster", ROSTER)
checks.append(("an isolation line below the block does not annotate the round",
               r.returncode == 1 and "isolation missing for cfo-astrid" in r.stdout,
               (r.returncode, r.stdout)))

d = stage("two-isolations", ["round1/cfo-astrid.md"])
txt = (d / "cfo-astrid.md").read_text(encoding="utf-8").replace(
    "isolation: enforced-tools\n", "isolation: enforced-tools\nisolation: emulated\n")
(d / "cfo-astrid.md").write_text(txt, encoding="utf-8")
r = panel("--aggregate", d, "--roster", ROSTER)
checks.append(("two isolation lines above one block are refused, never last-wins",
               r.returncode == 1 and "isolation" in r.stdout, (r.returncode, r.stdout)))

bad_shape = TMP / "bad-shape.md"
bad_shape.write_text((FIX / "round1/cfo-astrid.md").read_text(encoding="utf-8").replace(
    "isolation: enforced-tools", "isolation: sandboxed"), encoding="utf-8")
r = panel("--validate", bad_shape)
checks.append(("an isolation value outside the four shapes is a schema error at isolation",
               r.returncode == 1 and r.stdout.startswith("schema error at isolation: "),
               (r.returncode, r.stdout)))

# `greenlight: NO` with nothing in `greenlight_changes` is a semantic error, not a shape one:
# a refusal that names no change the document could make is not a reviewable verdict. The rule
# lives in panel.py alone, so an unasserted rule here is one refactor from silent loss.
no_changes = TMP / "greenlight-no-without-changes.md"
no_changes.write_text((FIX / "round1/cfo-astrid.md").read_text(encoding="utf-8").replace(
    ' "greenlight_changes": ["Put the break clause in the contract text", '
    '"Name the reconciliation baseline for the first phase"],',
    ' "greenlight_changes": [],'), encoding="utf-8")
r = panel("--validate", no_changes)
checks.append(("greenlight NO with an empty greenlight_changes is rejected (exit 1) at "
               "the greenlight_changes path",
               r.returncode == 1 and r.stdout.startswith("schema error at greenlight_changes: "),
               (r.returncode, r.stdout)))

# the full template heading is the same section as the canonical short name
bg = TMP / "background-heading.md"
bg.write_text((FIX / "round1/cfo-astrid.md").read_text(encoding="utf-8").replace(
    '"grounds": "Judgment criteria"', '"grounds": "Background and track record"'),
    encoding="utf-8")
r = panel("--validate", bg)
checks.append(("`Background and track record` is accepted as the Background section",
               r.returncode == 0, (r.returncode, r.stdout)))

# --------------------------------------------------------------- 7. control reviewers
CONTROLS = FIX / "controls"
OVERRIDES = FIX / "overrides.txt"


def row_for(out, key_persona, anchor):
    """The Round-1 row of `key_persona` whose anchor cell contains `anchor`."""
    return first([ln for ln in table_rows(out, "## Round-1 objections")
                  if ln.split("|")[1].strip() == key_persona and anchor in ln])


r = panel("--aggregate", FIX / "round1", "--roster", ROSTER, "--controls", CONTROLS)
ctl = r.stdout
checks.append(("--aggregate --controls exits 0", r.returncode == 0,
               (r.returncode, r.stdout, r.stderr)))
checks.append(("a control round sets the snapshot header to `control: yes`",
               ctl.splitlines()[0] == "control: yes" if ctl else False, ctl.splitlines()[:2]))

ctl_rows = table_rows(ctl, "## Round-1 objections")
checks.append(("control objections never enter the Round-1 table", len(ctl_rows) == 6, ctl_rows))
checks.append(("the row whose anchor a control shares reads role-generic yes",
               row_for(ctl, "cfo-astrid", "break clause").rstrip().endswith("| yes | ? |"),
               row_for(ctl, "cfo-astrid", "break clause")))
checks.append(("every other row reads role-generic no",
               len([ln for ln in ctl_rows if ln.rstrip().endswith("| no | ? |")]) == 5,
               ctl_rows))
checks.append(("the column carries the pinned values alone: no marker travels into the "
               "snapshot table",
               "(proposed)" not in section(ctl, "## Round-1 objections"),
               section(ctl, "## Round-1 objections")))
checks.append(("a control matches only its own persona: another persona's control sharing "
               "the anchor does not make the row role-generic",
               row_for(ctl, "cto-jonas", "break clause").rstrip().endswith("| no | ? |"),
               row_for(ctl, "cto-jonas", "break clause")))
checks.append(("Method counts prints the control objection count, per persona",
               "control objections: 4 (cfo-astrid 2, coo-mira 0, cto-jonas 2)" in ctl, ctl))
checks.append(("Method counts lists every row still only proposed, in row order",
               "role-generic proposed, unconfirmed: cfo-astrid#1, cfo-astrid#2, cfo-astrid#3, "
               "coo-mira#1, cto-jonas#1, cto-jonas#2" in ctl,
               section(ctl, "## Method counts")))
checks.append(("the control personas stay out of every gradeable section",
               "control-" not in section(ctl, "## Round-1 objections")
               and "control-" not in section(ctl, "## Red-line violations")
               and "control-" not in section(ctl, "## Shared anchors")
               and "control-" not in section(ctl, "## Blind spots"), ctl))
checks.append(("a control's red-line objection enters neither table: a control is never a "
               "gradeable row, red line or not",
               "no technical evaluator signs" not in ctl
               and len(table_rows(ctl, "## Red-line violations")) == 1
               and len(ctl_rows) == 6,
               (table_rows(ctl, "## Red-line violations"), len(ctl_rows))))
checks.append(("the control's own greenlight and no_basis are ignored",
               len(table_rows(ctl, "## Method counts")) == 3
               and section(ctl, "## Blind spots").count("  - ") == 5,
               (table_rows(ctl, "## Method counts"), section(ctl, "## Blind spots"))))
checks.append(("the red-line and shared-anchor sections are unchanged by the control round",
               len(table_rows(ctl, "## Red-line violations")) == 1
               and len(table_rows(ctl, "## Shared anchors")) == 1,
               (table_rows(ctl, "## Red-line violations"),
                table_rows(ctl, "## Shared anchors"))))

# --------------------------------------------------------------- 7b. overrides
r = panel("--aggregate", FIX / "round1", "--roster", ROSTER, "--controls", CONTROLS,
          "--overrides", OVERRIDES)
ovr = r.stdout
checks.append(("--overrides exits 0", r.returncode == 0, (r.returncode, r.stdout, r.stderr)))
checks.append(("an overridden row carries the confirmed value",
               row_for(ovr, "cto-jonas", "Single sign-on").rstrip().endswith("| yes | ? |"),
               row_for(ovr, "cto-jonas", "Single sign-on")))
checks.append(("a confirmed row leaves the unconfirmed list",
               "role-generic proposed, unconfirmed: cfo-astrid#1, cfo-astrid#2, cfo-astrid#3, "
               "coo-mira#1, cto-jonas#2" in ovr, section(ovr, "## Method counts")))
checks.append(("the proposal the override replaced is still recorded, with its reason",
               "override cto-jonas#1: no (proposed) -> yes" in ovr
               and "the anchor moved but the substance did not" in ovr,
               section(ovr, "## Method counts")))
checks.append(("a row nobody overrode keeps the proposed verdict",
               row_for(ovr, "coo-mira", "Dispatch").rstrip().endswith("| no | ? |"),
               row_for(ovr, "coo-mira", "Dispatch")))

flip = TMP / "flip-to-no.txt"
flip.write_text("cfo-astrid#2=no: the control quoted the same sentence for a different "
                "reason, and the substance is the persona's own red line\n", encoding="utf-8")
r = panel("--aggregate", FIX / "round1", "--roster", ROSTER, "--controls", CONTROLS,
          "--overrides", flip)
checks.append(("an override flips a proposed yes to a confirmed no",
               r.returncode == 0
               and row_for(r.stdout, "cfo-astrid", "break clause").rstrip().endswith("| no | ? |"),
               (r.returncode, row_for(r.stdout, "cfo-astrid", "break clause"))))
checks.append(("the yes -> no override is recorded too",
               "override cfo-astrid#2: yes (proposed) -> no" in r.stdout,
               section(r.stdout, "## Method counts")))

bad = TMP / "overrides-unknown-row.txt"
bad.write_text("cfo-astrid#9=yes: no such objection\n", encoding="utf-8")
r = panel("--aggregate", FIX / "round1", "--roster", ROSTER, "--controls", CONTROLS,
          "--overrides", bad)
checks.append(("an override naming a row that does not exist stops the aggregate (exit 1)",
               r.returncode == 1 and "cfo-astrid#9" in r.stdout, (r.returncode, r.stdout)))

bad = TMP / "overrides-malformed.txt"
bad.write_text("cfo-astrid#2 = maybe\n", encoding="utf-8")
r = panel("--aggregate", FIX / "round1", "--roster", ROSTER, "--controls", CONTROLS,
          "--overrides", bad)
checks.append(("a malformed override line stops the aggregate (exit 1)", r.returncode == 1,
               (r.returncode, r.stdout, r.stderr)))
checks.append(("the malformed-override message names the line and the form",
               "line 1" in r.stdout + r.stderr
               and "<slug>#<n>=yes|no: <reason>" in r.stdout + r.stderr, (r.stdout, r.stderr)))

bad = TMP / "overrides-no-reason.txt"
bad.write_text("cfo-astrid#2=yes:\n", encoding="utf-8")
r = panel("--aggregate", FIX / "round1", "--roster", ROSTER, "--controls", CONTROLS,
          "--overrides", bad)
checks.append(("an override without a reason is refused (exit 1)", r.returncode == 1,
               (r.returncode, r.stdout, r.stderr)))

bad = TMP / "overrides-twice.txt"
bad.write_text("cfo-astrid#2=yes: first reason\ncfo-astrid#2=no: second reason\n",
               encoding="utf-8")
r = panel("--aggregate", FIX / "round1", "--roster", ROSTER, "--controls", CONTROLS,
          "--overrides", bad)
checks.append(("the same row overridden twice is refused, never last-wins",
               r.returncode == 1 and "cfo-astrid#2" in r.stdout + r.stderr,
               (r.returncode, r.stdout, r.stderr)))

d = stage("two-blocks", ["round1/cfo-astrid.md"])
shutil.copy(str(FIX / "round1/cfo-astrid.md"), str(d / "cfo-astrid-second.md"))
r = panel("--aggregate", d, "--roster", ROSTER, "--controls", CONTROLS)
checks.append(("D1: a persona returning two valid round-1 blocks refuses the round (exit 1), "
               "naming both files",
               r.returncode == 1
               and "two round-1 outputs for cfo-astrid: cfo-astrid-second.md, cfo-astrid.md"
               in r.stdout and "## Round-1 objections" not in r.stdout,
               (r.returncode, r.stdout)))
r = panel("--aggregate", d, "--roster", ROSTER)
checks.append(("D1: the same refusal without a control round",
               r.returncode == 1
               and "two round-1 outputs for cfo-astrid: cfo-astrid-second.md, cfo-astrid.md"
               in r.stdout, (r.returncode, r.stdout)))
d = stage("round1-plus-round2", ["round1/cfo-astrid.md", "round2/cfo-astrid-round2.md"])
r = panel("--aggregate", d, "--roster", ROSTER)
checks.append(("D1: a round-1 block plus a later round of the same persona is not a duplicate",
               r.returncode == 0 and "two round-1 outputs" not in r.stdout,
               (r.returncode, r.stdout[-400:])))

r = panel("--aggregate", FIX / "round1", "--roster", ROSTER, "--overrides", OVERRIDES)
checks.append(("--overrides without --controls is a usage error: there is no proposal to "
               "confirm (exit 1)", r.returncode == 1, (r.returncode, r.stdout, r.stderr)))

r = panel("--validate", FIX / "round1/cfo-astrid.md", "--controls", CONTROLS)
checks.append(("--controls with --validate is a usage error, never silently ignored",
               r.returncode == 1, (r.returncode, r.stdout, r.stderr)))

# --------------------------------------------------------------- 7c. what the controls refuse
d = stage("controls-no-isolation", ["controls/control-cfo-astrid.md"])
txt = (d / "control-cfo-astrid.md").read_text(encoding="utf-8").replace(
    "isolation: enforced-tools\n", "")
(d / "control-cfo-astrid.md").write_text(txt, encoding="utf-8")
r = panel("--aggregate", FIX / "round1", "--roster", ROSTER, "--controls", d)
checks.append(("an unannotated control output stops the aggregate, like a persona's",
               r.returncode == 1 and "isolation missing for control-cfo-astrid" in r.stdout,
               (r.returncode, r.stdout)))

d = stage("controls-bare-slug", ["controls/control-cfo-astrid.md"])
txt = (d / "control-cfo-astrid.md").read_text(encoding="utf-8").replace(
    '"persona": "control-cfo-astrid"', '"persona": "cfo-astrid"')
(d / "control-cfo-astrid.md").write_text(txt, encoding="utf-8")
r = panel("--aggregate", FIX / "round1", "--roster", ROSTER, "--controls", d)
checks.append(("a control block that does not name control-<slug> is refused (exit 1)",
               r.returncode == 1 and "control-<slug>" in r.stdout, (r.returncode, r.stdout)))

d = stage("controls-foreign", ["controls/control-cfo-astrid.md"])
txt = (d / "control-cfo-astrid.md").read_text(encoding="utf-8").replace(
    '"persona": "control-cfo-astrid"', '"persona": "control-cfo-nobody"')
(d / "control-cfo-astrid.md").write_text(txt, encoding="utf-8")
r = panel("--aggregate", FIX / "round1", "--roster", ROSTER, "--controls", d)
checks.append(("a control of a persona outside the roster is refused (exit 1)",
               r.returncode == 1 and "control-cfo-nobody" in r.stdout, (r.returncode, r.stdout)))

d = stage("controls-round2", ["controls/control-cfo-astrid.md",
                              "round2/cfo-astrid-round2.md"])
txt = (d / "cfo-astrid-round2.md").read_text(encoding="utf-8").replace(
    '"persona": "cfo-astrid"', '"persona": "control-cfo-astrid"')
(d / "cfo-astrid-round2.md").write_text(txt, encoding="utf-8")
r = panel("--aggregate", FIX / "round1", "--roster", ROSTER, "--controls", d)
checks.append(("a control answering a later round is refused: the round-N loop never runs "
               "controls (exit 1)", r.returncode == 1 and "round 2" in r.stdout,
               (r.returncode, r.stdout)))

r = panel("--aggregate", FIX / "round1", "--roster", ROSTER, "--controls",
          TMP / "no-controls-here")
checks.append(("--controls on a missing directory exits 1", r.returncode == 1,
               (r.returncode, r.stdout, r.stderr)))

d = stage("controls-empty", [])
r = panel("--aggregate", FIX / "round1", "--roster", ROSTER, "--controls", d)
checks.append(("--controls on an empty directory exits 1", r.returncode == 1,
               (r.returncode, r.stdout, r.stderr)))

d = stage("controls-partial", ["controls/control-cfo-astrid.md"])
r = panel("--aggregate", FIX / "round1", "--roster", ROSTER, "--controls", d)
checks.append(("a persona whose control is missing is named, not silently counted as no",
               r.returncode == 0 and "no control output: coo-mira, cto-jonas" in r.stdout,
               (r.returncode, r.stdout)))

# --------------------------------------------------------------- 7d. --json with controls
r = panel("--aggregate", FIX / "round1", "--roster", ROSTER, "--controls", CONTROLS,
          "--overrides", OVERRIDES, "--json")
try:
    cdata = json.loads(r.stdout)
except ValueError:
    cdata = None
checks.append(("--json --controls is parseable and carries control: yes",
               isinstance(cdata, dict) and cdata.get("control") == "yes", r.stdout[:300]))
if isinstance(cdata, dict):
    checks.append(("--json carries the per-persona control counts",
                   [(c["persona"], c["objections"]) for c in cdata.get("control_counts", [])] ==
                   [("cfo-astrid", 2), ("coo-mira", 0), ("cto-jonas", 2)],
                   cdata.get("control_counts")))
    checks.append(("--json marks the proposed and the confirmed rows apart",
                   {o.get("key"): (o.get("role_generic"), o.get("role_generic_status"))
                    for o in cdata["round1"]}.get("cto-jonas#1") == ("yes", "confirmed")
                   and {o.get("key"): (o.get("role_generic"), o.get("role_generic_status"))
                        for o in cdata["round1"]}.get("cfo-astrid#2") == ("yes", "proposed"),
                   [(o.get("key"), o.get("role_generic"), o.get("role_generic_status"))
                    for o in cdata["round1"]]))
    checks.append(("--json records every override with its reason",
                   len(cdata.get("overrides", [])) == 1
                   and cdata.get("overrides", [{}])[0].get("key") == "cto-jonas#1"
                   and cdata.get("overrides", [{}])[0].get("proposed") == "no"
                   and cdata.get("overrides", [{}])[0].get("confirmed") == "yes"
                   and str(cdata.get("overrides", [{}])[0].get("reason")).startswith("the control raised"),
                   cdata.get("overrides")))

# an overrides file saved inside the controls directory is not a control block
d = stage("controls-with-overrides", ["controls/control-cfo-astrid.md",
                                      "controls/control-cto-jonas.md",
                                      "controls/control-coo-mira.md"])
inside = d / "overrides.txt"
inside.write_text("cfo-astrid#2=no: the anchor is shared, the substance is the red line\n",
                  encoding="utf-8")
r = panel("--aggregate", FIX / "round1", "--roster", ROSTER, "--controls", d,
          "--overrides", inside)
checks.append(("an overrides file inside the controls directory is skipped, not read as a "
               "malformed control", r.returncode == 0 and "schema error" not in r.stdout,
               (r.returncode, r.stdout[:400])))
checks.append(("that overrides file is still applied",
               "override cfo-astrid#2: yes (proposed) -> no" in r.stdout,
               section(r.stdout, "## Method counts")))

d = stage("controls-twice", ["controls/control-cfo-astrid.md"])
shutil.copy(str(FIX / "controls/control-cfo-astrid.md"), str(d / "control-cfo-astrid-2.md"))
r = panel("--aggregate", FIX / "round1", "--roster", ROSTER, "--controls", d)
checks.append(("two control outputs for one persona are refused, never merged and "
               "double-counted",
               r.returncode == 1 and "two control outputs for cfo-astrid" in r.stdout,
               (r.returncode, r.stdout)))

r = panel("--help")
checks.append(("--help says a control objection is not consumed by the first row it matches",
               "a control objection is not consumed by the first row it" in r.stdout, r.stdout[:200]))
checks.append(("--help says where the overrides file lives",
               "file lives *beside* the controls directory, never inside it" in r.stdout, r.stdout[:200]))
checks.append(("--help documents the override key form",
               "<slug>#<n>=yes|no: <reason>" in r.stdout, r.stdout[-800:]))

# --------------------------------------------------------------- 8. usage
r = panel()
checks.append(("panel with no mode is a usage error (exit 1)", r.returncode == 1,
               (r.returncode, r.stdout, r.stderr)))
r = panel("--aggregate", FIX / "round1")
checks.append(("--aggregate without --roster is a usage error (exit 1)", r.returncode == 1,
               (r.returncode, r.stdout, r.stderr)))

# --------------------------------------------------------------- 9. the overlap rule
sys.path.insert(0, str(HERE))
import panel as panel_mod  # noqa: E402

checks.append(("identical quotes overlap fully",
               panel_mod.anchor_overlap("Three-year term", "three year TERM") == 1.0,
               panel_mod.anchor_overlap("Three-year term", "three year TERM")))
checks.append(("the fixture pair is over the 0.60 threshold",
               panel_mod.anchor_overlap("Three-year term with an annual break clause",
                                        "term with an annual break clause") >= 0.60, None))
checks.append(("two unrelated anchors stay under the threshold",
               panel_mod.anchor_overlap("Dispatch confirmations for depot drivers",
                                        "Single sign-on for all users at go-live") < 0.60,
               panel_mod.anchor_overlap("Dispatch confirmations for depot drivers",
                                        "Single sign-on for all users at go-live")))
checks.append(("an empty anchor never pairs",
               panel_mod.anchor_overlap("", "term with an annual break clause") == 0.0, None))

# --------------------------------------------------------------- 9b. criteria (FR-2.2, FR-2.3)
DOC = FIX / "criteria-doc.md"
CRIT_ROUND = FIX / "criteria-round"

r = panel("--validate", CRIT_ROUND / "cfo-astrid.md")
checks.append(("a block carrying criteria validates without a document (exit 0)",
               r.returncode == 0, (r.returncode, r.stdout, r.stderr)))
checks.append(("without --document the ok: line reports the reviewer's own counts",
               "criteria 3 met / 0 declared / 0 unmet / 0 not-addressed" in r.stdout,
               r.stdout))
checks.append(("without --document nothing is forced", "declared —" not in r.stdout, r.stdout))

r = panel("--validate", CRIT_ROUND / "cfo-astrid.md", "--document", DOC)
checks.append(("--validate --document on a block whose every quote is found exits 0",
               r.returncode == 0, (r.returncode, r.stdout, r.stderr)))
checks.append(("a met whose evidence sits only in a table header is printed as declared, "
               "with the line it was found in",
               'criteria[0]: declared — evidence sits only in a heading or metadata line: '
               '"| Signal | Source | Lead time | Confidence |"' in r.stdout, r.stdout))
checks.append(("the ok: line counts the forced verdict, not the returned one",
               "criteria 2 met / 1 declared / 0 unmet / 0 not-addressed" in r.stdout,
               r.stdout))
checks.append(("a forced row is not an error: the exit code stays 0", r.returncode == 0,
               (r.returncode, r.stdout)))

r = panel("--validate", FIX / "malformed/criteria-missing.md")
checks.append(("the missing-criteria message says what the empty answer looks like",
               "schema error at criteria: missing: every round answers the persona's "
               "Judgment criteria; [] when that section is declared empty" in r.stdout,
               r.stdout))

r = panel("--validate", FIX / "malformed/criteria-not-found.md")
checks.append(("a quote found in no document passes the shape check on its own (exit 0)",
               r.returncode == 0, (r.returncode, r.stdout, r.stderr)))
r = panel("--validate", FIX / "malformed/criteria-not-found.md", "--document", DOC)
checks.append(("with --document a quote found nowhere is a schema error (exit 1)",
               r.returncode == 1, (r.returncode, r.stdout, r.stderr)))
checks.append(("the not-found error names the path and the document",
               r.stdout.strip() == "schema error at criteria[0].evidence: not found in "
                                   "criteria-doc.md", r.stdout))

r = panel("--validate", CRIT_ROUND / "cfo-astrid.md", "--document", TMP / "no-such-doc.md")
checks.append(("--document on a missing file is a usage error on stderr (exit 1)",
               r.returncode == 1 and r.stderr.startswith("usage:"),
               (r.returncode, r.stdout, r.stderr)))

# the round-N block answers criteria too: a criterion declared in r1 and met in r3 is what a
# fix looks like, and `fixed[]` cannot carry it
r = panel("--validate", FIX / "round2/cfo-astrid-round2.md")
checks.append(("a round-N block carries its own criteria and reports them on the ok: line",
               r.returncode == 0 and "criteria 1 met / 1 declared / 0 unmet / 0 not-addressed"
               in r.stdout, (r.returncode, r.stdout)))

r = panel("--aggregate", CRIT_ROUND, "--roster", ROSTER, "--document", DOC)
cri = r.stdout
checks.append(("--aggregate --document exits 0", r.returncode == 0,
               (r.returncode, r.stdout, r.stderr)))
checks.append(("the six sections are printed in order, `## Criteria` fifth",
               [ln for ln in cri.splitlines() if ln.startswith("## ")] ==
               ["## Round-1 objections", "## Red-line violations", "## Shared anchors",
                "## Blind spots", "## Criteria", "## Method counts"],
               [ln for ln in cri.splitlines() if ln.startswith("## ")]))
checks.append(("the Criteria table carries the pinned header row",
               "| Persona | Context | Criterion | Verdict | Evidence | Evidence check |" in cri,
               section(cri, "## Criteria")[:200]))
crit_rows = table_rows(cri, "## Criteria")
checks.append(("one Criteria row per criterion returned, in roster order", len(crit_rows) == 5,
               crit_rows))
checks.append(("the demoted row reads declared, with the check that demoted it",
               any("| cfo-astrid | golden |" in ln and "| declared |" in ln
                   and '| "Lead time" |' in ln and ln.rstrip().endswith("| structural |")
                   for ln in crit_rows), crit_rows))
checks.append(("a met whose quote is body text keeps its verdict",
               any("| met |" in ln and ln.rstrip().endswith("| body |") for ln in crit_rows),
               crit_rows))
checks.append(("a row quoting nothing is checked against nothing",
               any("| not-addressed |" in ln and ln.rstrip().endswith("| unchecked |")
                   for ln in crit_rows), crit_rows))
checks.append(("Method counts names every rewritten row and the line that rewrote it",
               'criteria declared by label: cfo-astrid#c1 ("| Signal | Source | Lead time | '
               'Confidence |")' in cri, section(cri, "## Method counts")))
checks.append(("Method counts cross-checks the rows returned against the persona file",
               "criteria: cfo-astrid returned 3 rows for 2 items under ## Judgment criteria"
               in cri, section(cri, "## Method counts")))
checks.append(("the aggregate says the verdict column is its own, not the block's",
               "reads `declared` here and `met` in the block — the block is never edited"
               in section(cri, "## Criteria"), section(cri, "## Criteria")))

r = panel("--aggregate", CRIT_ROUND, "--roster", ROSTER)
nodoc = r.stdout
checks.append(("without --document the aggregate still prints the section (exit 0)",
               r.returncode == 0 and "## Criteria" in nodoc, (r.returncode, nodoc[:200])))
checks.append(("without --document every check cell reads unchecked",
               all(ln.rstrip().endswith("| unchecked |")
                   for ln in table_rows(nodoc, "## Criteria")),
               table_rows(nodoc, "## Criteria")))
checks.append(("without --document no verdict is forced and nothing is listed as rewritten",
               "criteria declared by label:" not in nodoc
               and "| declared |" not in section(nodoc, "## Criteria"),
               section(nodoc, "## Criteria")))

d = stage("criteria-not-found-round", ["criteria-round/cfo-astrid.md",
                                       "malformed/criteria-not-found.md"])
r = panel("--aggregate", d, "--roster", ROSTER, "--document", DOC)
checks.append(("a criterion quote found nowhere refuses the round, like any schema error",
               r.returncode == 1 and "criteria[0].evidence: not found in criteria-doc.md"
               in r.stdout, (r.returncode, r.stdout)))

r = panel("--aggregate", CRIT_ROUND, "--roster", ROSTER, "--document", DOC, "--json")
try:
    jdata = json.loads(r.stdout)
except ValueError:
    jdata = None
checks.append(("--json mirrors the criteria rows with their keys and both verdicts",
               isinstance(jdata, dict)
               and [(c["key"], c["verdict"], c["verdict_returned"], c["check"])
                    for c in jdata.get("criteria", [])][:2] ==
               [("cfo-astrid#c1", "declared", "met", "structural"),
                ("cfo-astrid#c2", "met", "met", "body")],
               r.stdout[:600] if jdata is None else jdata.get("criteria")))
checks.append(("--json mirrors the rewritten rows",
               isinstance(jdata, dict)
               and [d["key"] for d in jdata.get("criteria_declared_by_label", [])] ==
               ["cfo-astrid#c1"],
               None if jdata is None else jdata.get("criteria_declared_by_label")))

# a control may answer criteria and the aggregate ignores them, exactly as it drops the
# control's own greenlight: a control block is never a gradeable row
d = stage("controls-with-criteria", ["controls/control-cfo-astrid.md"])
txt = (d / "control-cfo-astrid.md").read_text(encoding="utf-8").replace(
    ' "criteria": [],',
    ' "criteria": [{"criterion": "Wants the downside before the upside", "verdict": "met",'
    ' "evidence": "nothing in any document anywhere"}],')
(d / "control-cfo-astrid.md").write_text(txt, encoding="utf-8")
r = panel("--aggregate", CRIT_ROUND, "--roster", ROSTER, "--document", DOC, "--controls", d)
checks.append(("a control's criteria are accepted and never checked against the document",
               r.returncode == 0 and "not found in" not in r.stdout,
               (r.returncode, r.stdout[:400])))
checks.append(("a control's criteria enter no row of the Criteria table",
               len(table_rows(r.stdout, "## Criteria")) == 5
               and "control-" not in section(r.stdout, "## Criteria"),
               table_rows(r.stdout, "## Criteria")))

# the classifier itself: the golden round-1 anchors are list items, and a list item is body
quotes = []
for fname in ("round1/cfo-astrid.md", "round1/cto-jonas.md", "round1/coo-mira.md"):
    block = re.search(r"```json personas-review\n(.*?)\n```",
                      (FIX / fname).read_text(encoding="utf-8"), re.S).group(1)
    quotes.extend(o["quote"] for o in json.loads(block)["objections"])
synthetic = ("# Q3 platform brief\n\nCadence: quarterly\n\n## Scope\n"
             + "".join("- %s\n" % q for q in quotes))
parsed = panel_mod.split_document(synthetic)
checks.append(("the six golden round-1 anchors all classify as body, not as structure",
               len(quotes) == 6
               and all(panel_mod.classify_criterion({"verdict": "met", "evidence": q},
                                                    parsed)[1] == "body" for q in quotes),
               [(q, panel_mod.classify_criterion({"verdict": "met", "evidence": q},
                                                 parsed)[1]) for q in quotes]))
doc_parsed = panel_mod.split_document(DOC.read_text(encoding="utf-8"))
checks.append(("the frontmatter, the headings, the table header, the preamble metadata line "
               "and the bold label are all structural",
               all(any(want in line for line in doc_parsed[1])
                   for want in ("title: Weekly signal digest", "# Weekly signal digest",
                                "Cadence: weekly", "| Signal | Source |",
                                "**Lead time:**")), doc_parsed[1]))
checks.append(("a table data row and a list item are body, and the label's own line keeps "
               "its sentence in the body",
               "| Depot queue length | dispatch export | | high |" in doc_parsed[0]
               and "to be agreed with the desks" in doc_parsed[0]
               and "Who signs off the weekly issue" in doc_parsed[0], doc_parsed[0][:400]))
checks.append(("the check never promotes: a declared whose quote is body text stays declared",
               panel_mod.classify_criterion(
                   {"verdict": "declared",
                    "evidence": "The downside comes first here, before any saving is claimed"},
                   doc_parsed)[:2] == ("declared", "body"),
               panel_mod.classify_criterion(
                   {"verdict": "declared",
                    "evidence": "The downside comes first here, before any saving is claimed"},
                   doc_parsed)))

r = panel("--help")
checks.append(("--help documents what --document can and cannot say",
               "The check only ever demotes." in r.stdout
               and "HTML headings are not recognised" in r.stdout, r.stdout[-1200:]))

# --------------------------------------------------------------- 10. the entrypoint
r = run(ENTRY, "panel", "--validate", FIX / "round1/cfo-astrid.md")
checks.append(("beforehand.py panel --validate passes the module's exit code through",
               r.returncode == 0, (r.returncode, r.stdout, r.stderr)))
r = run(ENTRY, "panel", "--validate", FIX / "malformed/bad-severity.md")
checks.append(("beforehand.py panel --validate exits 1 on a schema error",
               r.returncode == 1 and "objections[0].severity" in r.stdout,
               (r.returncode, r.stdout, r.stderr)))
r = run(ENTRY, "--help")
checks.append(("the help line no longer says panel is unavailable",
               "not available before task 14" not in r.stdout, r.stdout))
checks.append(("the help line keeps the exit codes of panel",
               "0 ok · 1 schema error" in r.stdout, r.stdout))

# --------------------------------------------------------------- 11. one prompt, two files
agent_body = AGENT.read_text(encoding="utf-8").split("---\n", 2)[2].strip()
prompt_blocks = re.findall(r"^````\n(.*?)^````$", REVIEW.read_text(encoding="utf-8"),
                           re.M | re.S)
checks.append(("review.md carries the two four-backtick prompt blocks",
               len(prompt_blocks) == 2, len(prompt_blocks)))
checks.append(("the round-1 prompt in review.md is the body of agents/persona-reviewer.md, "
               "character for character (the agent file is the canonical one)",
               bool(prompt_blocks) and prompt_blocks[0].strip() == agent_body,
               "\n".join(difflib.unified_diff(
                   (prompt_blocks[0].strip() if prompt_blocks else "").splitlines(),
                   agent_body.splitlines(), "review.md", "persona-reviewer.md", lineterm=""))))

# Asserting that a prompt block exists is not asserting that the schema it hands the reviewer
# is the one this validator accepts: the round-N block shipped without `criteria` for a whole
# release because nothing ever ran it. Both blocks are extracted, their placeholders filled
# with the value each field's own rules name, and the result is fed to `--validate` — the
# reviewer's side of the contract, checked the way the reviewer meets it.
FILL_GROUNDS = "Judgment criteria"


def fill(value):
    """A prompt placeholder, resolved: a `a|b|c` menu collapses to its first alternative,
    an `<angle-bracket>` description stands as the non-empty string it stands in for."""
    if isinstance(value, dict):
        return dict((k, FILL_GROUNDS if k == "grounds" else fill(v)) for k, v in value.items())
    if isinstance(value, list):
        return [fill(v) for v in value]
    if isinstance(value, str):
        return value.split("|")[0].strip() or value
    return value


schema_blocks = [re.search(r"```json personas-review\n(.*?)\n```", b, re.S)
                 for b in prompt_blocks]
checks.append(("both prompt blocks in review.md carry a `json personas-review` schema block",
               len(schema_blocks) == 2 and all(schema_blocks), len(prompt_blocks)))
for n, m in enumerate(schema_blocks, start=1):
    label = "round-1" if n == 1 else "round-N"
    if not m:
        continue
    # `N` is the only placeholder outside a string: the round-N prompt writes the round number
    # as a letter, so it is filled before the block is parsed rather than after.
    raw = m.group(1).replace('"round": N', '"round": 2')
    try:
        filled = json.dumps(fill(json.loads(raw)), indent=1)
        err = ""
    except ValueError as exc:
        filled, err = "", str(exc)
    checks.append(("the %s schema block in review.md is parseable once its placeholders are "
                   "filled" % label, bool(filled), err or raw[:300]))
    if not filled:
        continue
    path = TMP / ("prompt-%s.md" % label)
    path.write_text("```json personas-review\n%s\n```\n" % filled, encoding="utf-8")
    r = panel("--validate", path)
    checks.append(("the %s prompt in review.md asks for a block panel --validate accepts"
                   % label, r.returncode == 0, (r.returncode, r.stdout, r.stderr)))
    checks.append(("the %s prompt asks the reviewer for `criteria` — panel requires it in "
                   "every round" % label, '"criteria"' in raw, raw[:400]))

# The plugin ships the same prompt twice: agents/persona-reviewer.md at the plugin root, which
# is what Claude Code loads as a subagent, and this in-skill copy, which is the one the `.skill`
# zip carries for the hosts that install a single skill (FR-7.5). AGENT above is the in-skill
# copy — the one that travels with these tests. The two must be byte-identical, or the two
# install routes would run different reviewers. Only the repository holds both: an installed
# `.skill` has no plugin root, and there the check does not apply.
REPO = SKILL.parent.parent
PLUGIN_AGENT = REPO / "agents/persona-reviewer.md"
if (REPO / "dev/build_skill.sh").exists():
    checks.append(("the plugin-level agents/persona-reviewer.md exists beside the skill",
                   PLUGIN_AGENT.is_file(), str(PLUGIN_AGENT.exists())))
    checks.append(("the plugin-level and in-skill persona-reviewer.md are byte-identical",
                   PLUGIN_AGENT.is_file() and PLUGIN_AGENT.read_bytes() == AGENT.read_bytes(),
                   "\n".join(difflib.unified_diff(
                       (PLUGIN_AGENT.read_text(encoding="utf-8") if PLUGIN_AGENT.is_file()
                        else "").splitlines(),
                       AGENT.read_text(encoding="utf-8").splitlines(),
                       "agents/persona-reviewer.md", "skills/<name>/agents/persona-reviewer.md",
                       lineterm=""))))
else:
    # Outside the repository, two levels up is whatever the host's skill directory sits in —
    # `~/.claude/agents/` for a bundle installed at `~/.claude/skills/<name>/`, which is a
    # legitimate place for the same reviewer subagent. Absence is fine there; a copy that
    # differs is not, for the same reason as above: one prompt, two files.
    checks.append(("standalone install: any persona-reviewer.md beside the skill directory "
                   "is byte-identical to the in-skill one",
                   (not PLUGIN_AGENT.is_file())
                   or PLUGIN_AGENT.read_bytes() == AGENT.read_bytes(),
                   "\n".join(difflib.unified_diff(
                       (PLUGIN_AGENT.read_text(encoding="utf-8") if PLUGIN_AGENT.is_file()
                        else "").splitlines(),
                       AGENT.read_text(encoding="utf-8").splitlines(),
                       "../../agents/persona-reviewer.md", "agents/persona-reviewer.md",
                       lineterm=""))))

# --------------------------------------------------------------- 12. review.md, controls
review = REVIEW.read_text(encoding="utf-8")
checks.append(("review.md carries the control stub's pinned sentence, verbatim",
               "You have no other information about this person. Judge the document from "
               "the role alone." in review, None))
checks.append(("review.md states when controls are on by default",
               "Control reviewers (default on with ≤ 5 personas; propose otherwise)"
               in review, None))
checks.append(("review.md gives the stub's slug form and its round rule",
               "slug: control-<slug>" in review and "round 1 only" in review, None))
checks.append(("review.md documents the override key form and the aggregate flag",
               "<slug>#<n>=yes|no: <reason>" in review and "--controls <controls dir>"
               in review, None))
checks.append(("review.md sends the model to the Method list, never to the table",
               "role-generic proposed, unconfirmed" in review
               and "never edit the table" in review, None))
checks.append(("review.md says the overrides file lives beside the controls directory",
               "beside the controls directory" in review, None))
checks.append(("the snapshot template header carries the control field",
               "control: yes | no" in review, None))
checks.append(("the announce line gains the control marker",
               "controls on" in review, None))

# --------------------------------------------------------------- 12b. the criteria prompt
EXAMPLES = SKILL / "assets/reviewer-examples.md"
examples = EXAMPLES.read_text(encoding="utf-8")
agent_text = AGENT.read_text(encoding="utf-8")
THIRD = """    criterion: needs to receive a signal before finding it alone
    verdict: declared
    evidence: "| Signal | Source | Lead time |"
"""
for name, text in (("agents/persona-reviewer.md", agent_text),
                   ("references/review.md", review),
                   ("assets/reviewer-examples.md", examples)):
    checks.append((f"{name} carries the third, declared example", THIRD in text,
                   text[-900:]))
    checks.append((f"{name} says three examples, not two", "Three examples." in text
                   or "three blocks below" in text, text[:400]))
    checks.append((f"{name} says the why: lines are reasoning, not fields",
                   "The `role-generic:` and `why:` lines in these examples are reasoning "
                   "shown to you, not" in text, text[-400:]))
for name, text in (("agents/persona-reviewer.md", agent_text),
                   ("references/review.md", review)):
    checks.append((f"{name} carries the criteria bullet and the criteria schema field",
                   "Answer every item of the persona's `## Judgment criteria`, one row each "
                   "in `criteria`." in text
                   and '"verdict": "met|declared|unmet|not-addressed"' in text, text[:200]))
    checks.append((f"{name} carries the criteria field rule", "`criteria[].verdict` is one "
                   "of `met`, `declared`, `unmet`, `not-addressed`" in text, text[-400:]))
    # the norm lives in evidence-model.md and is cited, never pasted: dev/check_norms.sh
    # greps the agent files, and the anchor phrase must keep matching exactly one file
    checks.append((f"{name} does not restate the norm's anchor phrase",
                   "A field named like the criterion is not the criterion" not in text,
                   name))

# the four-space example blocks are one text: this is the same comparison build_skill.sh makes
agent_blocks = [ln for ln in agent_text.splitlines() if re.match(r"^    [^ ]", ln)]
example_blocks = [ln for ln in examples.splitlines() if re.match(r"^    [^ ]", ln)]
checks.append(("assets/reviewer-examples.md and the agent prompt hold the same three example "
               "blocks, the declared one included",
               agent_blocks == example_blocks and agent_blocks.count("    verdict: declared") == 1,
               "\n".join(difflib.unified_diff(example_blocks, agent_blocks,
                                              "reviewer-examples.md", "persona-reviewer.md",
                                              lineterm=""))))

checks.append(("review.md runs --validate with the document, before the staging directory "
               "is deleted",
               "panel --validate <answer file> --document <staged document path>" in review
               and "before the staging directory is deleted" in review, None))
checks.append(("review.md says a label-only met is printed declared and never re-requested",
               "is printed as `declared` and is" in review
               and "not** re-requested" in review, None))
checks.append(("review.md cites the norm instead of restating it",
               "references/evidence-model.md#Declared and demonstrated" in review, None))
checks.append(("rule 14 also waits for the criteria",
               "and no criterion of theirs" in review and "reads `declared`**" in review, None))
checks.append(("rule 6 records the criteria verdicts per round",
               "the criteria\n   verdicts" in review, None))
checks.append(("Step 4 lists the sixth section and says where the count comes from",
               "`## Criteria` (one row per item" in review
               and "from the blocks, and from the persona files only to count criteria items"
               in review, None))
checks.append(("the snapshot template carries the pending --set-meeting comment",
               "meeting: YYYY-MM-DD | unknown   <- set or move it later with pending "
               "--set-meeting; never edit by hand once frozen" in review, None))
checks.append(("review.md says a pre-0.2 snapshot is graded through a reconstructed ledger, "
               "never migrated",
               "A snapshot frozen before this shape existed is not migrated and not edited"
               in review, None))

# --------------------------------------------------------------- 10. 0.3.1 document check
def one_criterion(name, criterion, doc_text, doc_file):
    """--validate one round-1 block carrying a single criterion against a synthetic doc."""
    doc_path = TMP / doc_file
    doc_path.write_text(doc_text, encoding="utf-8")
    block = {"schema": "0.2", "persona": "cfo-astrid", "read": [], "no_basis": [],
             "greenlight": "YES", "greenlight_changes": [], "signoff_criterion": "s",
             "overall": "o", "round": 1, "objections": [], "criteria": [criterion]}
    out = TMP / name
    out.write_text("isolation: staged\n```json personas-review\n%s\n```\n"
                   % json.dumps(block), encoding="utf-8")
    return panel("--validate", out, "--document", doc_path)


RISKS_DOC = "# Proposal\n\n## Risks\n\nWe list them later.\n"
r = one_criterion("a8-invented.md", {"criterion": "risk", "verdict": "unmet",
                                     "evidence": "we have fully insured all Risks with Lloyd's"},
                  RISKS_DOC, "a8-risks.md")
checks.append(("A8: invented evidence containing a heading word is not found (exit 1)",
               r.returncode == 1 and r.stdout.strip()
               == "schema error at criteria[0].evidence: not found in a8-risks.md",
               (r.returncode, r.stdout)))
r = one_criterion("a8-heading.md", {"criterion": "risk", "verdict": "met", "evidence": "Risks"},
                  RISKS_DOC, "a8-risks.md")
checks.append(("A8: evidence that sits inside a heading is still structural (met -> declared)",
               r.returncode == 0 and 'criteria[0]: declared' in r.stdout
               and '"## Risks"' in r.stdout, (r.returncode, r.stdout)))
DATA_DOC = ("# Proposal\n\n## Data\n\n**All customer data stays in the EU region.**\n\n"
            "More text.\n")
r = one_criterion("a8-body.md", {"criterion": "data residency", "verdict": "met",
                                 "evidence": "All customer data stays in the EU region"},
                  DATA_DOC, "a8-data.md")
checks.append(("A8/A9: a real body met is not demoted because its evidence holds a heading word",
               r.returncode == 0 and "declared" not in r.stdout.split("criteria ")[0]
               and "criteria 1 met / 0 declared" in r.stdout, (r.returncode, r.stdout)))

body, structural = panel_mod.split_document(
    "# Proposal\n\n## Hosting\n\n**All customer data stays in the EU region.**\n\n"
    "**Pricing:** fixed per seat.\n\n**Scope**: two desks.\n\n- **Owner:** the ops desk\n")
checks.append(("A9: a line-leading bold sentence without a colon is body",
               "**All customer data stays in the EU region.**" in body
               and not any("customer data" in s for s in structural), (body, structural)))
checks.append(("A9: `**Label:**` and `**Label**:` are still structural, their rest is body",
               "**Pricing:**" in structural and "**Scope**:" in structural
               and "**Owner:**" in " ".join(structural)
               and "fixed per seat." in body and "two desks." in body, (body, structural)))

body, structural = panel_mod.split_document(
    "# Memo\n\nNote: the price includes VAT\n\nThe rest of the memo.\n")
checks.append(("D4: a document with no `##` has no preamble, so `key: value` lines are body",
               "Note: the price includes VAT" in body and structural == ["# Memo"],
               (body, structural)))
body, structural = panel_mod.split_document(
    "# Doc\n\n## Setup\n\nText.\n\n## Example\n\nFirst: line\n")
checks.append(("D4: a `key: value` line after the first `##` is still body",
               "First: line" in body, (body, structural)))
body, structural = panel_mod.split_document(
    "# Doc\n\n## Real\n\n```\n~~~\n## inside the backtick fence\n```\n\n"
    "~~~\n```\n## inside the tilde fence\n~~~\n\n## After\n")
checks.append(("D4: ``` and ~~~ fences toggle separately",
               "## inside the backtick fence" in body and "## inside the tilde fence" in body
               and structural == ["# Doc", "## Real", "## After"], (body, structural)))

d = stage("upper-suffix", [])
shutil.copy(str(FIX / "round1/cfo-astrid.md"), str(d / "CFO-ASTRID.MD"))
r = panel("--aggregate", d, "--roster", ROSTER)
checks.append(("D4: an output named *.MD is read, not reported as missing",
               r.returncode == 0 and len(rows(r.stdout, "cfo-astrid")) > 0
               and not any(ln.startswith("no round-1 output:") and "cfo-astrid" in ln
                           for ln in r.stdout.splitlines()),
               (r.returncode, r.stdout[-400:])))

# S12: every control error is printed once, in one place
d = stage("controls-two-errors", ["controls/control-cfo-astrid.md",
                                  "controls/control-cto-jonas.md"])
shutil.copy(str(FIX / "controls/control-cfo-astrid.md"), str(d / "control-cfo-astrid-2.md"))
txt = (d / "control-cto-jonas.md").read_text(encoding="utf-8").replace(
    '"control-cto-jonas"', '"control-nobody"')
(d / "control-cto-jonas.md").write_text(txt, encoding="utf-8")
r = panel("--aggregate", FIX / "round1", "--roster", ROSTER, "--controls", d)
checks.append(("S12: each control error is printed exactly once, then the refusal",
               r.returncode == 1
               and r.stdout.count("two control outputs for cfo-astrid") == 1
               and r.stdout.count("control-nobody is not a control of this roster") == 1
               and r.stdout.count("control round refused: 2 unusable output(s)") == 1
               and r.stdout.strip().splitlines()[-1].startswith("control round refused"),
               (r.returncode, r.stdout)))

shutil.rmtree(TMP, ignore_errors=True)

fails =[c for c in checks if not c[1]]
for name, ok, got in checks:
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  -> got {got!r}"))
print(f"\n{len(checks) - len(fails)}/{len(checks)} passed")
sys.exit(1 if fails else 0)
