<!--
SYNTHETIC EXPECTED OUTPUT — NOT A RECORDED RUN.

Case (g), run 1 of 2: `assets/reviewer-examples.md` as it ships. The shape
evals/cases/g/check.py parses; the verdict is the maintainer's, against
evals/cases/g/rubric.md. Nothing here was produced by a model.
-->

beforehand · review · store <store>/golden

Three isolated reviewers, `enforced-tools`, two staged files each.

```json personas-review
{"schema": "0.2", "persona": "cfo-astrid",
 "read": ["/tmp/personas-stage-a1/persona.md", "/tmp/personas-stage-a1/document.md"],
 "objections": [{"quote": "Five-year term, no break clause, priced flat for the whole period",
                 "objection": "Five years with nothing to get out of is not a term I sign, and it is not a negotiating position: it is the line I gave you in the steering call. Bring it to three with a break clause or bring it to someone else.",
                 "grounds": "Red lines", "severity": 5, "red_line": true},
                {"quote": "Savings baseline to be agreed with finance after signature",
                 "objection": "You want the signature first and the baseline afterwards. I do not approve savings without a named baseline, and a baseline agreed after signature is one I have no leverage over.",
                 "grounds": "Judgment criteria", "severity": 4, "red_line": false}],
 "no_basis": ["the offline confirmation behaviour", "the training plan for dispatchers"],
 "criteria": [{"criterion": "Wants the downside before the upside", "verdict": "unmet", "evidence": "Five-year term, no break clause, priced flat for the whole period"},
              {"criterion": "Refuses savings claims without a named baseline", "verdict": "declared", "evidence": "Savings baseline to be agreed with finance after signature"}],
 "greenlight": "NO", "greenlight_changes": ["three-year term with an annual break clause", "the savings baseline named in the document"],
 "signoff_criterion": "a redraft I can take to the board with the term and the baseline both in it",
 "overall": "Two things on the first page I have already told you I will not sign. I am not going to spend the meeting on the rest of it.",
 "round": 1, "fixed": [], "still_open": [], "new": [], "keep": []}
```

```json personas-review
{"schema": "0.2", "persona": "cto-jonas",
 "read": ["/tmp/personas-stage-j1/persona.md", "/tmp/personas-stage-j1/document.md"],
 "objections": [{"quote": "Production cutover on Friday 25 September, out of hours",
                 "objection": "No production cutover on a Friday. We have had two outages from Friday cutovers and I am not approving a third, out of hours or not.",
                 "grounds": "Red lines", "severity": 5, "red_line": true},
                {"quote": "Rollback is a restore from the previous night's backup, about four hours end to end",
                 "objection": "Four hours is not a rollback, it is an outage with a plan attached. I will not run this without a window under thirty minutes, and a nightly restore also loses the day's dispatches.",
                 "grounds": "Red lines", "severity": 5, "red_line": true}],
 "no_basis": ["the savings baseline", "the reporting rollup for depot supervisors"],
 "criteria": [{"criterion": "Wants the rollback plan before the feature list", "verdict": "unmet", "evidence": "Rollback is a restore from the previous night's backup, about four hours end to end"},
              {"criterion": "Weighs integration effort over license cost", "verdict": "not-addressed", "evidence": ""}],
 "greenlight": "NO", "greenlight_changes": ["a cutover day that is not a Friday", "a tested rollback under thirty minutes"],
 "signoff_criterion": "a dry-run cutover on the first depot that rolls back inside thirty minutes",
 "overall": "The rollout shape is fine. The two things that would get me fired are both in one section of this document.",
 "round": 1, "fixed": [], "still_open": [], "new": [], "keep": []}
```

```json personas-review
{"schema": "0.2", "persona": "coo-mira",
 "read": ["/tmp/personas-stage-m1/persona.md", "/tmp/personas-stage-m1/document.md"],
 "objections": [{"quote": "Vendor shortlist closes 10 July, contract award 5 October, go-live 1 September",
                 "objection": "Whatever the commercial calendar is, it puts the award after the date the depots are told to be live. I cannot plan shift cover against that.",
                 "grounds": "Mandate and incentives", "severity": 3, "red_line": false}],
 "no_basis": ["the commercial terms", "the support model", "the reporting rollup"],
 "criteria": [{"criterion": "Checks offline capability for a shift before anything else", "verdict": "unmet", "evidence": "offline confirmation is deferred to phase two"}],
 "greenlight": "NO", "greenlight_changes": ["offline confirmation inside the go-live scope"],
 "signoff_criterion": "a depot shift run end to end with the network off",
 "overall": "A third app the drivers will ignore, and no offline story until phase two. The first thing I check in any proposal is whether it works offline for a shift, and this one says it does not yet.",
 "round": 1, "fixed": [], "still_open": [], "new": [], "keep": []}
```

    panel --aggregate <round dir> --roster <store>/golden/INDEX.md
    control: no — 3 blocks, 5 objections, mean severity 4.4
