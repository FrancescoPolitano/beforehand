# Reviewer output — malformed: no read field

isolation: staged

```json personas-review
{"schema": "0.2", "persona": "cto-jonas",
 "objections": [
   {"quote": "Single sign-on for all users at go-live",
    "objection": "The identity cutover has no rollback path.",
    "grounds": "Red lines", "severity": 4, "red_line": false}],
 "criteria": [], "no_basis": [], "greenlight": "NO", "greenlight_changes": ["State the rollback path"],
 "signoff_criterion": "descriptive only",
 "overall": "The cutover needs a way back.",
 "round": 1, "fixed": [], "still_open": [], "new": [], "keep": []}
```
