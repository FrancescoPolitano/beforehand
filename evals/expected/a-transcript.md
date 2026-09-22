<!--
SYNTHETIC EXPECTED OUTPUT — NOT A RECORDED RUN.

This file is what a passing case (a) transcript looks like, in the exact shape
evals/cases/a/check.py parses. It exists so that `evals/run.sh --checkers-only` exercises
every assertion without spending a session on the host CLI. The store side of the same
passing run is in evals/expected/a-store/, which the runner copies over the temp store
before the checker runs. Nothing here was produced by a model.
-->

beforehand · authoring · store <store>/golden

doctor first:

    golden: 3 personas, 1 wanted decision function with no persona, 1 pending snapshot
    (brief-q3, meeting 2099-01-15, not due), 0 open offers
    doctor: healthy

`## Wanted` in context.md lists a chief financial officer / economic buyer with no persona
file. Measuring the material first:

    coverage --sources <store>/golden/sources --people "Astrid Lindqvist"
    Astrid Lindqvist: 3 sources, ~2,100 chars spoken, 2026-05-06 … 2026-06-20

Three sources carry her, spanning 45 days, so this is a founded build rather than a
one-transcript sketch. Speaker attribution on the steering call is settled already (the
AUDIT line records `Guest 1 = the logistics director`), so her turns are the ones labelled
with her name.

Proposed persona file, every claim tagged and anchored — six core sections, 12 Facts,
nothing inferred beyond the decision weight, which carries its own Inference tag:

    slug: cfo-astrid · role: Chief Financial Officer · decision_function: economic buyer
    Mandate and incentives      2 Facts   (kickoff)
    Judgment criteria           2 Facts   (kickoff)
    Recurring objections        2 Facts   (steering)
    Red lines                   2 Facts   (steering)
    Language and dissent style  2 Facts   (June email)
    Panel dynamics              2 Facts   (June email)
    Watchlist                   1 entry   (single-source, not promoted)

You confirmed the write in advance, so it is saved.

    written: golden/personas/cfo-astrid.md
    lint --sources-root <store>/golden/sources --lint
      Summary: 12 Fact tag(s), 12 excerpt(s) | VERIFIED: 12 (100%) | MISPLACED: 0 (0%)
               | NOT FOUND: 0 (0%) | UNVERIFIABLE: 0 (0%) | UNPARSEABLE: 0 (0%)
      LINT PASS
    coverage golden/personas/cfo-astrid.md
      solid (3 sources, 45d, 6/6 sections)
    reindex --store <store>
      golden/INDEX.md written

Bookkeeping closed: the AUDIT lines for these three sources were already there (the sources
were ingested before this persona existed), and the flow is logged.

    log authoring golden --doc cfo-astrid.md

One thing the build did not do: the Watchlist entry on a phased rollout stays a Watchlist
entry. It is mentioned once, in passing, in one source; a second independent mention would
promote it into Judgment criteria, and inventing the promotion now is what the watchlist
exists to prevent.
