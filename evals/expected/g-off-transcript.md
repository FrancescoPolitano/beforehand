<!--
SYNTHETIC EXPECTED OUTPUT — NOT A RECORDED RUN.

Case (g), run 2 of 2: the same prompt with `assets/reviewer-examples.md` blanked, so the
round-1 reviewer prompt carries no examples. Written to show what the measured table looks
like when the two runs differ — paraphrased anchors instead of verbatim ones, severities
collapsing toward the middle, criteria answered from the document's gist rather than from a
passage, objections any holder of the job title could have written.
This is an illustration of the shape, not a claim about what the skill actually does: the
real comparison is made live, by the maintainer, against evals/cases/g/rubric.md. Nothing
here was produced by a model.
-->

beforehand · review · store <store>/golden

```json personas-review
{"schema": "0.2", "persona": "cfo-astrid",
 "read": ["/tmp/personas-stage-a2/persona.md", "/tmp/personas-stage-a2/document.md"],
 "objections": [{"quote": "Five-year term, no break clause, priced flat for the whole period",
                 "objection": "The term is too long and the lack of an exit is a risk. This should be shortened.",
                 "grounds": "Judgment criteria", "severity": 3, "red_line": false},
                {"quote": "the commercial terms section",
                 "objection": "The pricing is not justified and the savings are not quantified. Finance will want more detail before approving.",
                 "grounds": "Judgment criteria", "severity": 3, "red_line": false}],
 "no_basis": [],
 "criteria": [{"criterion": "Wants the downside before the upside", "verdict": "unmet", "evidence": "the commercial terms section"},
              {"criterion": "Refuses savings claims without a named baseline", "verdict": "unmet", "evidence": "the savings are not quantified"}],
 "greenlight": "NO", "greenlight_changes": ["shorten the term", "quantify the savings"],
 "signoff_criterion": "descriptive only",
 "overall": "The commercial section needs work before this is approvable.",
 "round": 1, "fixed": [], "still_open": [], "new": [], "keep": []}
```

```json personas-review
{"schema": "0.2", "persona": "cto-jonas",
 "read": ["/tmp/personas-stage-j2/persona.md", "/tmp/personas-stage-j2/document.md"],
 "objections": [{"quote": "Production cutover on Friday 25 September, out of hours",
                 "objection": "Friday cutovers are risky and the rollback approach is weak. I would want a stronger plan here.",
                 "grounds": "Red lines", "severity": 4, "red_line": true},
                {"quote": "the cutover and operations section",
                 "objection": "Support through a standard ticket queue is not sufficient for a migration of this size.",
                 "grounds": "Recurring objections", "severity": 3, "red_line": false}],
 "no_basis": [],
 "criteria": [{"criterion": "Wants the rollback plan before the feature list", "verdict": "unmet", "evidence": "the rollback approach is weak"},
              {"criterion": "Weighs integration effort over license cost", "verdict": "not-addressed", "evidence": ""}],
 "greenlight": "NO", "greenlight_changes": ["a better cutover plan"],
 "signoff_criterion": "descriptive only",
 "overall": "The technical plan is not detailed enough to approve.",
 "round": 1, "fixed": [], "still_open": [], "new": [], "keep": []}
```

```json personas-review
{"schema": "0.2", "persona": "coo-mira",
 "read": ["/tmp/personas-stage-m2/persona.md", "/tmp/personas-stage-m2/document.md"],
 "objections": [{"quote": "the depot rollout section",
                 "objection": "Driver adoption is a risk and the timeline looks tight for operations.",
                 "grounds": "Recurring objections", "severity": 3, "red_line": false}],
 "no_basis": [],
 "criteria": [{"criterion": "Checks offline capability for a shift before anything else", "verdict": "not-addressed", "evidence": ""}],
 "greenlight": "NO", "greenlight_changes": ["more detail on the depot rollout"],
 "signoff_criterion": "descriptive only",
 "overall": "Operations needs more detail before this can go ahead.",
 "round": 1, "fixed": [], "still_open": [], "new": [], "keep": []}
```

    panel --aggregate <round dir> --roster <store>/golden/INDEX.md
    control: no — 3 blocks, 5 objections, mean severity 3.2
