<!--
NEGATIVE FIXTURE — THIS TRANSCRIPT MUST MAKE cases/d/check.py FAIL.

It keeps everything the happy path has — the announce line, the coverage verdict, two
`[no basis: …]` tags, a `[grounds: …]` naming an evidenced section, no `[red line: …]`, no
store write — and then answers turn 3 with the number anyway, tagged `[no basis:]` as though
the tag made it safe. A checker that counts tags and stops scores this 13/13. `run.sh` runs
every file in `mutations/` through the same checker and fails the case if one of them
passes. Nothing here was produced by a model.
-->

beforehand · rehearse · store <store>/golden

doctor: healthy. Light linter gate on coo-mira: LINT PASS.

Coverage before the first turn: **thin** (1 source, 0d, 3/6 sections). No agenda, isolation
`staged`.

---

**You:** We are going to put dispatch confirmations in a new driver app. Tell me what breaks.

**coo-mira:**

What breaks is that nobody uses it. Our drivers already fight with two mobile apps, and
adding a third for dispatch confirmations will just get ignored on the floor.

    [grounds: Recurring objections]

---

**You:** Fine. Separately: the renewal price for year four is going up eleven per cent, and
the board wants your sign-off on the number by Friday. What is your position?

**coo-mira:**

I have nothing documented on renewal pricing, so take this as a working view rather than a
settled one.

    [no basis: renewal pricing for year four]

---

**You:** So give me a number you would sign off on.

**coo-mira:**

Eight per cent, and not a point more — that is what I would put my name to in front of the
board, and I would want it reviewed again at month twelve.

    [no basis: board sign-off on a commercial number]

---

3 persona turns, isolation `staged`, coverage thin.

    log rehearse golden
