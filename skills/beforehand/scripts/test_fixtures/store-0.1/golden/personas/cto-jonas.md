---
slug: cto-jonas
aliases: [Jonas, Jonas Berg, the CTO]
role: Chief Technology Officer
organization: Halden Logistics (synthetic)
context: golden
decision_function: technical evaluator
decision_weight: 4 # (Inference — owns architecture sign-off, not budget)
cares_about: [system uptime during migration, integration effort over license cost, rollback safety]
created: 2026-05-06
updated: 2026-06-20
---

## Mandate and incentives <!-- last evidence: 2026-05-06 | decays fast -->
- Judged on dispatch-system uptime above all else (Fact — "my mandate is uptime on the dispatch system, full stop", 2026-05-06-kickoff.txt, private-communication, machine-transcribed, 2026-05-06)
- A failed migration is a personal career risk, more than a slow one (Fact — "a failed migration is the one thing that gets me fired, not a slow rollout", 2026-05-06-kickoff.txt, private-communication, machine-transcribed, 2026-05-06)

## Judgment criteria <!-- last evidence: 2026-05-06 | decays slowly -->
- Wants the rollback plan before the feature list (Fact — "show me the rollback plan before the feature list", 2026-05-06-kickoff.txt, private-communication, machine-transcribed, 2026-05-06)
- Weighs integration effort over license cost (Fact — "I weigh integration effort heavier than the license cost", 2026-05-06-kickoff.txt, private-communication, machine-transcribed, 2026-05-06)

## Recurring objections <!-- last evidence: 2026-06-11 | decays slowly -->
- SSO keeps being deferred to phase two (Fact — "every proposal so far treats single sign-on as a phase-two item", 2026-06-11-steering.txt, private-communication, machine-transcribed, 2026-06-11)
- Promised dedicated support turns into a ticket queue (Fact — "support keeps promising a dedicated engineer and we get a ticket queue instead", 2026-06-11-steering.txt, private-communication, machine-transcribed, 2026-06-11)

## Red lines <!-- last evidence: 2026-06-11 | decays slowly -->
- No production cutover on a Friday (Fact — "no production cutover on a Friday", 2026-06-11-steering.txt, private-communication, machine-transcribed, 2026-06-11)
- Rollback window under thirty minutes, non-negotiable (Fact — "I will not run this without a rollback window under thirty minutes", 2026-06-11-steering.txt, private-communication, machine-transcribed, 2026-06-11)

## Language and dissent style <!-- last evidence: 2026-06-20 | does not decay -->
- Goes quiet in the room and sends the real objection afterwards (Fact — "when I disagree I go quiet in the meeting and send the real objection by email afterwards", 2026-06-20-email.txt, private-communication, human-authored, 2026-06-20)
- His silence is not agreement (Fact — "don't read silence from me as a yes", 2026-06-20-email.txt, private-communication, human-authored, 2026-06-20)

## Panel dynamics <!-- last evidence: 2026-06-20 | decays fast -->
- Defers to the CFO on contract terms (Fact — "on contract terms I defer to Astrid, that's her call to make", 2026-06-20-email.txt, private-communication, human-authored, 2026-06-20)
- Sides with the depots over finance when scope is disputed (Fact — "when the depots and finance disagree on scope, I side with whoever protects uptime", 2026-06-20-email.txt, private-communication, human-authored, 2026-06-20)

## Watchlist
- **Possible interest in a phased cutover.** In the steering call he floated running the new dispatch module in parallel for two weeks before full cutover; mentioned once, would need a second occurrence to move into Judgment criteria (single source, 2026-06-11).

## Reliability
- 1 cycle: 1/1 — n too small to interpret
