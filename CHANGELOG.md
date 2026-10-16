# Changelog

From 1.0 the history of this project lives in git; this file records releases only.

## 1.0.1 — 2026-10-16
- Review: the control reviewer can answer. The instruction that it judges from the role
  alone moved from the stub, where the reviewer quoted it as an anomaly and abstained, into
  the prompt; the pinned stub sentence now describes the file (#1).
- `panel --aggregate --controls`: a control with no objections and `INSUFFICIENT_BASIS` is
  reported `control degenerate: <slug>`, its persona's rows stay `estimated` instead of
  being proposed `no`, and an override on them is refused (#1).
- Review: the round-1 prompt says `fixed`, `still_open`, `new` and `keep` stay empty in
  round 1, the rule the validator already applied (#2).
- `doctor` lints a canary persona before trusting the linter, and its last line carries
  the count: `doctor: healthy (N of M personas checked)`.

## 1.0.0 — 2026-09-22
First public release.
