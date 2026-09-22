# Reviewer examples — three calibration examples for the round-1 prompt (FR-3.6)

The flow pastes the three blocks below inline, under "Three examples", into the reviewer's
prompt. They are part of the prompt and never a third file: the reviewer reads exactly two
files. All three are synthetic and deliberately domain-neutral — replace nothing, add nothing.

**Grounded — this is what an objection is.**

    quote: "the rollout completes in the first quarter after signature"
    objection: The last two rollouts here slipped a quarter each, and this one adds a
      second site. Tie the date to the site count, not to the signature.
    grounds: Recurring objections
    severity: 4
    red_line: false
    role-generic: no — the budget owner's own history of slipped rollouts produced it.

**Generic — this is what does not count.**

    quote: "the price is high"
    objection: The price is high and should come down.
    grounds: Judgment criteria
    severity: 3
    red_line: false
    role-generic: yes — the job title alone writes this sentence: it cites nothing the
      persona file evidences, and any approver could have said it. Do not send it.

**Declared — this is what does not pass a criterion.**

    criterion: needs to receive a signal before finding it alone
    verdict: declared
    evidence: "| Signal | Source | Lead time |"
    why: the column is named after the criterion and every cell under it is empty; the
      sample entries report what was public the day before. Nothing in the body arrives
      early, so the label is all there is.

The `role-generic:` and `why:` lines in these examples are reasoning shown to you, not
fields you return.
