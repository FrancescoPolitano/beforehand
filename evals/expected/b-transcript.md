<!--
SYNTHETIC EXPECTED OUTPUT — NOT A RECORDED RUN.

What a passing case (b) transcript looks like, in the shape evals/cases/b/check.py parses.
The store side of the same run (the review report and the prediction snapshot) is in
evals/expected/b-store/, which the runner copies over the temp store before the checker
runs. Nothing here was produced by a model.
-->

beforehand · review · store <store>/golden

doctor first:

    golden: 3 personas, 1 wanted decision function with no persona, 1 pending snapshot
    (brief-q3, meeting 2099-01-15, not due), 0 open offers
    doctor: healthy

Roster: the whole valid panel — cfo-astrid (5), cto-jonas (4), coo-mira (3). Nobody
excluded. The unrepresented decision function is the gatekeeper: `## Wanted` declares a head
of procurement with no persona, and this draft carries a procurement calendar, so nothing
the panel says about shortlist or award dates is a prediction.

Linter gate, all three pass; coo-mira is thin (3 Facts, Red lines and Panel dynamics empty)
and that is carried into the report next to her objection.

Round 1 ran as three isolated `persona-reviewer` subagents, `enforced-tools`, two staged
files each. Each block reported exactly its two staged paths. Aggregated:

    panel --aggregate <round dir> --roster <store>/golden/INDEX.md
    control: no
    3 blocks, 5 objections, mean severity 4.4, 3 red-line violations, 0 shared anchors

What the panel objects to, in order of severity:

1. Commercial terms — a five-year term with no break clause, and a savings baseline
   deferred to after signature. cfo-astrid, Red lines and Judgment criteria.
2. Cutover and operations — a Friday production cutover, and a four-hour rollback against a
   thirty-minute window. cto-jonas, Red lines, twice.
3. Depot rollout — a third driver app with offline confirmation deferred to phase two.
   coo-mira, Recurring objections and Judgment criteria; thin persona.
4. The procurement calendar awards the contract on 5 October for a 1 September go-live.
   No persona's evidence reaches this, and the gatekeeper has no file — it is filed as an
   out-of-persona defect and repeated in the fix list so it is not lost.

Written:

    golden/reviews/2026-06-30-brief-q3-flawed.md
    golden/calibration/pending-brief-q3-flawed.md   (control: no, 5 round-1 rows, sha1 of
                                                     the document as reviewed)
    calibration/log.md   <- snapshot sha1 appended
    log review golden --doc brief-q3-flawed

The document itself is untouched: this was a plain review, so the objections are reported
and nothing was applied to `docs/brief-q3-flawed.md`.
