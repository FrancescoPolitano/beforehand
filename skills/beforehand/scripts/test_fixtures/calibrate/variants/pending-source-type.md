# Prediction snapshot — brief-q4

document: docs/brief-q4.md
sha1: ba9bf2b4ea81ee2f80cb41fd775d9df44045fd68
schema: 0.2
frozen: 2026-09-01 09:00
review date: 2026-09-01
meeting: 2026-09-10
events:
- steering | trial | 2026-09-10
- board | approvals | 2026-09-24
document version: 2
apply mode: yes
control: yes
personas: budget-lin (trial, updated 2026-08-20), data-rey (trial, updated 2026-08-20), platform-noor (trial, updated 2026-08-20), ops-sam (trial, updated 2026-08-20), legal-toft (trial, updated 2026-08-20)

## Round-1 objections
| Persona | Context | Isolation | Anchor in the document | Objection | Severity | Round tag | Event | Role-generic | Doc changed |
|---|---|---|---|---|---|---|---|---|---|
| budget-lin | trial | enforced-tools | "unit cost baseline" | The brief names no baseline to hold the unit cost flat against | 4 | r1 | steering | no | no |
| budget-lin | trial | enforced-tools | "Payment terms stay at sixty days" | Sixty-day terms move the working-capital risk onto us | 3 | r1 | steering | yes | no |
| platform-noor | trial | staged | "Single sign-on lands in a later phase" | Single sign-on deferred to a later phase again | 4 | r1 | steering | no | no |
| platform-noor | trial | staged | "The rollback window is two hours" | A two-hour rollback window is too short for a regional cutover | 3 | r1 | steering | no | yes (window extended to six hours) |
| ops-sam | trial | inline | "The driver handset app ships with the pilot" | A third handset app will be ignored on the floor | 3 | r1 | steering | no | no |
| ops-sam | trial | inline | "a weekend cutover" | A weekend cutover needs paid overtime cover | 2 | r1 | steering | no | yes (the weekend cutover clause was removed) |
| budget-lin | trial | enforced-tools | "Renewal uplift is set annually" | The annual renewal uplift carries no cap | 3 | r1 | steering | no | no |
| legal-toft | trial | emulated | "indemnity cap" | The indemnity cap sits below our own exposure | 4 | r1 | steering | no | no |
| platform-noor | trial | staged | "a later phase" | The later phase has no scope statement | 2 | r2 | steering | no | no |
| ops-sam | trial | inline | "A pilot runs in the first quarter" | The pilot names no cutover owner | 2 | r1 | board | no | no |

## Green lights
| Persona | GREENLIGHT | Sign-off criterion (observable event, written now) | Blockers if NO |
|---|---|---|---|
| budget-lin | YES | signs the order form at the steering session | — |
| platform-noor | YES | confirms the identity plan in writing within a week | — |
| ops-sam | YES | names a cutover owner in the minutes | — |
| legal-toft | NO | — | the indemnity cap is raised |
| data-rey | INSUFFICIENT_BASIS | — | the document says nothing about retention |

## Applied before sending
| Persona | Objection | Fate: applied-then-removed | deferred | carried | Round |
|---|---|---|---|---|---|
| platform-noor | A two-hour rollback window is too short | applied-then-removed | 1 |

## Predictions to verify
- P1 | platform-noor | will ask who staffs the integration after the first year | Recurring objections | source flow: consult | specificity: high | role-generic: no | source type: private-communication
- P2 | budget-lin | will raise the renewal uplift before signing | Judgment criteria | source flow: consult | specificity: low | role-generic: yes | source type: public-statement
- P3 | ops-sam | will ask for a named cutover owner | Recurring objections | source flow: rehearsal | specificity: high | role-generic: no
