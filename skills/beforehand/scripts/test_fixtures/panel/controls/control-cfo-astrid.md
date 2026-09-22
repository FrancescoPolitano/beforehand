# Control reviewer output — control-cfo-astrid, round 1

The stub this reviewer read carries the role and the decision function and nothing else:
no evidence, no history, no red lines. What it returns is what the job title alone produces.

isolation: enforced-tools

```json personas-review
{"schema": "0.2", "persona": "control-cfo-astrid",
 "read": ["/tmp/personas-stage-r1-control-a/persona.md", "/tmp/personas-stage-r1-control-a/document.md"],
 "objections": [
   {"quote": "Three-year term with an annual break clause",
    "objection": "A three-year commitment needs a documented way out, and the way out belongs in the contract rather than in a summary.",
    "grounds": "Judgment criteria", "severity": 4, "red_line": false},
   {"quote": "Reporting rollup for depot supervisors",
    "objection": "The rollup is described but never costed. Nothing here says who pays for the reporting work or when.",
    "grounds": "Mandate and incentives", "severity": 2, "red_line": false}],
 "no_basis": ["Dispatch confirmations for depot drivers"],
 "criteria": [],
 "greenlight": "NO",
 "greenlight_changes": ["Write the break clause into the contract text"],
 "signoff_criterion": "descriptive only",
 "overall": "Nothing here is priced against a baseline and the term is long. From the role alone I would not sign it as it stands.",
 "round": 1, "fixed": [], "still_open": [], "new": [], "keep": []}
```
