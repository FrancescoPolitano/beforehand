# Review report — brief-q3-flawed (2026-06-30)

<!--
SYNTHETIC EXPECTED OUTPUT — NOT A RECORDED RUN. This is the report a passing case (b) run
writes into the store, in the shape evals/cases/b/check.py parses. The runner copies it over
the temp store in --checkers-only mode. Nothing here was produced by a model.
-->

Panel run against `docs/brief-q3-flawed.md`, context golden.

## Roster and rationale

Convened: cfo-astrid (economic buyer, weight 5), cto-jonas (technical evaluator, weight 4),
coo-mira (user, weight 3) — the whole valid panel of the context. Nobody was excluded.

**Unrepresented decision functions.** `## Wanted` in context.md declares a head of
procurement, gatekeeper on the vendor shortlist, with no evidenced persona. This document
carries a procurement calendar, so the gatekeeper's function is the one with no voice in
this round: every statement below about shortlist and award dates is an out-of-persona
observation, not a prediction about how procurement will react.

## Linter scorecard

| Persona | Evidence per section | Mix | VERIFIED / UNVERIFIABLE | Lint | Coverage | Verdict |
|---|---|---|---|---|---|---|
| cfo-astrid | 2,2,2,2,2,2 | 12 Fact / 1 Inference / 0 Assumption | 12 / 0 | pass | solid | pass |
| cto-jonas | 2,2,2,2,2,2 | 12 Fact / 1 Inference / 0 Assumption | 12 / 0 | pass | solid | pass |
| coo-mira | 1,1,1,0,1,0 | 3 Fact / 1 Inference / 0 Assumption | 3 / 0 | pass | thin | warn |

coo-mira is thin: three evidenced sections, Red lines and Panel dynamics empty. Her
objection below is worth less than the other two, and that is why it says so here.

## Verdict synthesis

Weighted against the document as it stands: **no**. The two heaviest voices both hit a
documented red line on the first page they read, and neither red line is a matter of
negotiation in their own evidence.

## Stakeholder conflicts

None this round. The technical evaluator and the budget owner object to different sections
and neither's fix damages the other's.

## Red-line violations

- cfo-astrid — a five-year term with no break clause. Her file: "I will not sign anything
  with an annual contract over three years without a break clause" (Red lines). Blocking
  regardless of weight.
- cto-jonas — a production cutover on Friday 25 September. His file: "no production cutover
  on a Friday" (Red lines). Blocking regardless of weight.
- cto-jonas — a four-hour rollback. His file: "I will not run this without a rollback window
  under thirty minutes" (Red lines). Blocking regardless of weight.

## Prioritized fix list

1. **Commercial terms — the five-year term has no break clause.** cfo-astrid, Red lines,
   severity 5. The term exceeds three years and carries no break clause; this is a red line
   in her own words, not a preference. The savings baseline deferred to after signature
   compounds it: her Judgment criteria refuse savings claims without a named baseline.
2. **Cutover and operations — the Friday cutover and the four-hour rollback.** cto-jonas,
   Red lines, severity 5. Two red lines in one section: a production cutover on a Friday,
   and a rollback window an order of magnitude outside the thirty minutes he has said he
   will not run without.
3. **Depot rollout — a third driver app with offline confirmation deferred.** coo-mira,
   Recurring objections and Judgment criteria, severity 3. Her evidence says the drivers
   already fight with two apps and a third for dispatch confirmations will be ignored on the
   floor; offline capability for a shift is the first thing she checks in any proposal, and
   this draft defers it to phase two. Thin persona: one source behind both points.
4. **Procurement calendar — the contract is awarded after go-live.** No persona, severity 4.
   Shortlist closes 10 July, contract award 5 October, go-live 1 September: the dates cannot
   all hold. No rostered persona's evidence reaches this, and the gatekeeper who would own
   it has no persona file, so it is listed as a defect, not as a prediction.

None of the above rewrites the document; each names the problem and who it comes from.

## Blind spots

- cfo-astrid: the offline fallback behaviour, the training plan for dispatchers.
- cto-jonas: the savings baseline, the reporting rollup for depot supervisors.
- coo-mira: the commercial terms in full, the procurement calendar, the support model — her
  file carries no Red lines and no Panel dynamics evidence at all.

## Out-of-persona observations

- The procurement calendar is internally inconsistent (award 5 October, go-live 1 September).
- "Single sign-on for all users at go-live" in Scope and "offline confirmation deferred to
  phase two" in Depot rollout describe two different go-live scopes.

## Method

Rounds run: 1. Isolation: `enforced-tools` for all three personas (the host registers the
shipped `persona-reviewer` definition). No emulated persona, no malformed answer, no
re-request. `read` contamination events: none — each block reported exactly its two staged
paths. Control round: not run (`control: no`), so the Role-generic column reads `estimated`
in every row and nothing was measured. Dynamics round: skipped — coo-mira has no Panel
dynamics evidence, so the round would have run on two of three personas.

### Method counts

| Persona | Objections | Mean severity | Greenlight | Isolation | Control objections |
|---|---|---|---|---|---|
| cfo-astrid | 2 | 4.5 | NO | enforced-tools | - |
| cto-jonas | 2 | 4.5 | NO | enforced-tools | - |
| coo-mira | 1 | 3.0 | NO | enforced-tools | - |

## User decisions

(none yet — appended at calibration)
