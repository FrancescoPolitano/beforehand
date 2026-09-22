# Prediction snapshot — brief-q3-flawed

<!--
SYNTHETIC EXPECTED OUTPUT — NOT A RECORDED RUN. The snapshot a passing case (b) run writes,
in the shape evals/cases/b/check.py parses. Nothing here was produced by a model.
-->

document: docs/brief-q3-flawed.md
sha1: 02561a22f44178ddf8b962a792a25ca1b067ebee
schema: 0.2
frozen: 2026-06-30 11:20
review date: 2026-06-30
meeting: 2099-01-15
apply mode: no
control: no
personas: cfo-astrid (golden, updated 2026-06-20), cto-jonas (golden, updated 2026-06-20), coo-mira (golden, updated 2026-06-11)

## Round-1 objections
| Persona | Context | Isolation | Anchor in the document | Objection | Severity | Round tag | Event | Role-generic | Doc changed |
|---|---|---|---|---|---|---|---|---|---|
| cfo-astrid | golden | enforced-tools | "Five-year term, no break clause, priced flat for the whole period" | over three years with no break clause: she has said she will not sign it | 5 | r1 | steering committee | estimated | ? |
| cfo-astrid | golden | enforced-tools | "Savings baseline to be agreed with finance after signature" | a savings claim with no named baseline, agreed after the signature that depends on it | 4 | r1 | steering committee | estimated | ? |
| cto-jonas | golden | enforced-tools | "Production cutover on Friday 25 September, out of hours" | a Friday production cutover, after two outages from Friday cutovers | 5 | r1 | steering committee | estimated | ? |
| cto-jonas | golden | enforced-tools | "Rollback is a restore from the previous night's backup, about four hours end to end" | four hours against a rollback window he has said must stay under thirty minutes | 5 | r1 | steering committee | estimated | ? |
| coo-mira | golden | enforced-tools | "Depot drivers confirm each dispatch in a new third mobile app; offline confirmation is" | a third driver app, and the offline behaviour she checks first deferred to phase two | 3 | r1 | steering committee | estimated | ? |

## Green lights
| Persona | GREENLIGHT | Sign-off criterion (observable event, written now) | Blockers if NO |
|---|---|---|---|
| cfo-astrid | NO | a redraft naming the term at three years with a break clause, and the baseline agreed before signature | term, baseline |
| cto-jonas | NO | a cutover date that is not a Friday, and a rollback tested under thirty minutes | cutover day, rollback window |
| coo-mira | NO | offline confirmation in the go-live scope, on a surface the drivers already use | third app, offline deferral |

## Criteria
| Persona | Context | Criterion | Verdict | Evidence | Evidence check |
|---|---|---|---|---|---|
| cfo-astrid | golden | Wants the downside before the upside | unmet | "Five-year term, no break clause, priced flat for the whole period" | body |
| cfo-astrid | golden | Refuses savings claims without a named baseline | declared | "Savings baseline to be agreed with finance after signature" | body |
| cto-jonas | golden | Wants the rollback plan before the feature list | unmet | "Rollback is a restore from the previous night's backup, about four hours end to end" | body |
| cto-jonas | golden | Weighs integration effort over license cost | not-addressed |  | unchecked |
| coo-mira | golden | Checks offline capability for a shift before anything else | unmet | "offline confirmation is deferred to phase two" | body |

## Predictions to verify
- P1 | cfo-astrid | will refuse the five-year term outright and ask for a break clause before discussing price | Red lines | source flow: review | specificity: high | role-generic: no
- P2 | cfo-astrid | will ask for the savings baseline to be named before signature, not after | Judgment criteria | source flow: review | specificity: high | role-generic: no
- P3 | cto-jonas | will refuse the Friday cutover date and say so in the room | Red lines | source flow: review | specificity: high | role-generic: no
- P4 | cto-jonas | will ask for the rollback window in writing, under thirty minutes | Red lines | source flow: review | specificity: high | role-generic: no
- P5 | coo-mira | will raise the third-app problem from the depot side before anything commercial | Recurring objections | source flow: review | specificity: high | role-generic: no
