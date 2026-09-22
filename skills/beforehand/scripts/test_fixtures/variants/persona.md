---
slug: test-variants
context: fixture
---

## Mandate and incentives
- Canonical tag (Fact — "my number this year is opex, not growth", test_fixtures/variants/source.txt, private-communication, human-authored, 2026-07-03)
- Same-source shorthand inherits the previous ref (Fact — "Year two is where these things bite", same source, 2026-07-03)
- Quote before the tag: "I refuse to fly for internal meetings" (Fact — test_fixtures/variants/source.txt, private-communication, 2026-07-03)
- Quote before a comma-form tag: says "start with what happens if this fails" (Fact, same source, 2026-07-03)
- Accents folded: (Fact — "cosi va bene, pero la perche non e brillante", test_fixtures/variants/source.txt, private-communication, machine-transcribed, 2026-07-03)
- Two excerpts in one tag (Fact — "we pilot first" and "Year two is where these things bite", test_fixtures/variants/source.txt, private-communication, 2026-07-03)
- Lead-in text before the quote (Fact — on the pilot rule: "above one hundred thousand, we pilot first", test_fixtures/variants/source.txt, private-communication, 2026-07-03)
- Fabricated (Fact — "we never pilot anything", test_fixtures/variants/source.txt, private-communication, 2026-07-03)
- No excerpt anywhere (Fact — test_fixtures/variants/source.txt, private-communication, 2026-07-03)
- Missing file (Fact — "opex, not growth", test_fixtures/variants/missing.txt, private-communication, 2026-07-03)
- Promoted fact keeps the marker (Fact <- Inference 2026-08-01 via later email — "opex, not growth", test_fixtures/variants/source.txt, private-communication, 2026-08-01)
- Not a Fact, must be ignored (Inference — from the same meeting) and (Assumption)
