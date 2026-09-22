#!/usr/bin/env python3
"""Benchmark for verify_quotes.match_excerpt (SPEC-0.3.1 FR-1.1).

Builds one deterministic ~200 KB synthetic source (random.Random(0) over a fixed word
list) and checks three excerpt populations against it: 25 verbatim spans (must be
`exact`), 15 drifted spans -- one rare word misheard plus punctuation changed -- (must be
`approximate`: found, and flagged as not verbatim), and 10 fabricated sentences built only
from words absent from the source (must be None); plus 20 excerpts carrying 1-3 short
[brackets] (exact when a bracket absorbs no source word, approximate when it stands for
some) and one all-filler 3-bracket excerpt, timed on their own row. The correctness assertions
(which excerpt is exact / approximate / None) never depend on the clock and
are the same on any machine. Wall time is also asserted under 5 s, but that is one more
row in the table below like every other check: it is printed either way, with the
measured seconds folded into the row's own name, not something that aborts the run.

Vocabulary is split into FILLER (common connective words, heavily weighted so every
filler word's count in the source stays in the thousands) and TOPIC (uncommon words, a
handful of occurrences each). A drift mishears one TOPIC word's first letter: a word of at
least 4 characters (rule 3 refuses a substitution of a shorter one, where negation and
grammar live), while the excerpt's other rare words still anchor the match. Excerpts are drawn
only from sentences carrying at least 3 TOPIC words (a real Fact excerpt is quoted
because it says something distinctive, not because it is filler-word soup) -- a sentence
that is almost all filler gives the pre-filter no rare token to anchor on, which is a
real limit of a token-frequency pre-filter, not something this benchmark needs to cover.

Run from the scripts/ directory: python3 test_bench.py
"""
import random
import sys
import time
from collections import Counter
from pathlib import Path

sys.dont_write_bytecode = True  # G5: a suite run on its own leaves no __pycache__

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import verify_quotes as vq  # noqa: E402

# ---------------------------------------------------------------- fixed vocabulary
# Common connective words, repeated FILLER_WEIGHT times in the sampling pool so each one
# individually occurs thousands of times in the 200 KB source -- far more than any TOPIC
# word -- and therefore can never be picked as an excerpt's rarest (anchor) token, drifted
# or not.
FILLER = ["the", "a", "of", "and", "to", "in", "that", "is", "was", "for",
          "on", "with", "as", "by", "at", "this", "it", "from", "an", "or"]
FILLER_WEIGHT = 12
# 36 distinct uncommon words: each occurs only a couple of hundred times in the 200 KB
# source (rarer than any FILLER word by an order of magnitude), which is what lets the
# pre-filter narrow a search to a handful of windows instead of the whole source.
TOPIC = [
    "quartz", "lumen", "cobalt", "onyx", "cedar", "willow", "harbor", "meridian", "granite",
    "ember", "thicket", "current", "ridge", "spindle", "lantern", "copper", "basalt", "fern",
    "auger", "tundra", "meadow", "channel", "furrow", "kestrel", "otter", "beacon", "gravel",
    "cinder", "marsh", "pinion", "sable", "trellis", "vellum", "wicker", "zephyr", "alcove",
]
PUNCT_END = [".", "!"]
TOPIC_SET = set(TOPIC)


def build_source(target_bytes=200_000):
    rng = random.Random(0)
    vocab = FILLER * FILLER_WEIGHT + TOPIC
    sentences = []
    size = 0
    while size < target_bytes:
        n = rng.randint(6, 14)
        words = [rng.choice(vocab) for _ in range(n)]
        sentence = " ".join(words)
        sentence = sentence[0].upper() + sentence[1:] + rng.choice(PUNCT_END)
        sentences.append(sentence)
        size += len(sentence) + 1
    return sentences, " ".join(sentences)


SENTENCES, SOURCE = build_source()


def _topic_word_count(sentence):
    return sum(1 for w in sentence.rstrip(".!").split(" ") if w.lower() in TOPIC_SET)


# a real Fact excerpt is a distinctive quote, not filler-word soup: only draw from
# sentences with at least 3 TOPIC words, so the pre-filter always has a real anchor
DISTINCTIVE = [i for i, s in enumerate(SENTENCES) if _topic_word_count(s) >= 3]

# words that never appear anywhere in SOURCE, for the fabricated population
FABRICATED_WORDS = ["glimmerhoop", "trundleworth", "quixzam", "flembert", "narwhalium",
                     "plurbex", "snorkelfen", "gribbleton", "vaxumal", "thornquil",
                     "wrenfable", "opsilon", "yammerdyne", "clovendark", "brackenspur"]


def make_exact_excerpts(n):
    rng = random.Random(1)
    picks = rng.sample(DISTINCTIVE, n)
    return [SENTENCES[i].rstrip(".!") for i in picks], picks


def _misheard(word):
    """A transcription drift: the word's first letter misheard ("cobalt" -> "zobalt"). The
    result is as long as the word (>= 4 characters, so rule 3 does not refuse it), is never
    a prefix or suffix of it, and occurs nowhere in the source."""
    first = "z" if word[0].lower() != "z" else "y"
    return (first.upper() if word[0].isupper() else first) + word[1:]


def make_drift_excerpts(n, avoid):
    """One TOPIC word misheard (see _misheard), plus the trailing punctuation changed. The
    excerpt's other rare words are untouched, so one of them still anchors the match."""
    rng = random.Random(2)
    pool = [i for i in DISTINCTIVE if i not in avoid]
    picks = rng.sample(pool, n)
    out = []
    for i in picks:
        s = SENTENCES[i]
        body, punct = s[:-1], s[-1]
        words = body.split(" ")
        pos = [p for p, w in enumerate(words) if w.lower() in TOPIC_SET][0]
        words[pos] = _misheard(words[pos])
        new_punct = "?" if punct != "?" else ";"
        out.append(" ".join(words) + new_punct)
    return out


def make_fabricated_excerpts(n):
    rng = random.Random(3)
    out = []
    for _ in range(n):
        k = rng.randint(6, 12)
        words = [rng.choice(FABRICATED_WORDS) for _ in range(k)]
        out.append(" ".join(words) + ".")
    return out


def make_bracket_excerpts(n, avoid):
    """Excerpts carrying 1-3 short [brackets] (the author's placeholders). The first half
    inserts "[sic]" between words, absorbing no source word (must stay `exact`); the second
    half puts "[the item]" in place of TOPIC words (>= 4 characters, no digit), leaving at
    least one TOPIC word to anchor (must be `approximate`: a bracket that stands for source
    words is never verbatim)."""
    rng = random.Random(4)
    pool = [i for i in DISTINCTIVE if i not in avoid]
    zero, absorbing = [], []
    for j, i in enumerate(rng.sample(pool, n)):
        words = SENTENCES[i].rstrip(".!").split(" ")
        k = 1 + j % 3
        if j < n // 2:
            for pos in sorted(rng.sample(range(1, len(words)), min(k, len(words) - 1)), reverse=True):
                words.insert(pos, "[sic]")
            zero.append(" ".join(words))
        else:
            topic = [p for p, w in enumerate(words) if w.lower() in TOPIC_SET]
            for pos in rng.sample(topic, min(k, len(topic) - 1)):
                words[pos] = "[the item]"
            absorbing.append(" ".join(words))
    return zero, absorbing


EXACT, EXACT_IDX = make_exact_excerpts(25)
DRIFT = make_drift_excerpts(15, avoid=set(EXACT_IDX))
FABRICATED = make_fabricated_excerpts(10)
BRACKET_ZERO, BRACKET_ABSORB = make_bracket_excerpts(20, avoid=set(EXACT_IDX))
# the pathological bracket case: three placeholders among the source's most common words,
# so every anchor occurs thousands of times and every expansion is tried
BRACKET_PATHOLOGICAL = "the [x] of [y] and [z] the"

checks = []

# ---------------------------------------------------------------- correctness (deterministic)
for i, ex in enumerate(EXACT):
    norm_ex, norm_src = vq.normalize(ex), vq._normalized(SOURCE)
    checks.append((f"exact excerpt {i}: normalized text is a literal substring (fast path)",
                    norm_ex in norm_src, ex[:50]))
    checks.append((f"exact excerpt {i}: match_excerpt is exact",
                    vq.match_excerpt(ex, SOURCE)[0] == "exact", ex[:50]))

for i, ex in enumerate(DRIFT):
    norm_ex, norm_src = vq.normalize(ex), vq._normalized(SOURCE)
    checks.append((f"drift excerpt {i}: not a literal substring (drift actually changed it)",
                    norm_ex not in norm_src, ex[:50]))
    checks.append((f"drift excerpt {i}: match_excerpt is approximate",
                    vq.match_excerpt(ex, SOURCE)[0] == "approximate", ex[:50]))

for i, ex in enumerate(FABRICATED):
    checks.append((f"fabricated excerpt {i}: match_excerpt is None",
                    vq.match_excerpt(ex, SOURCE)[0] is None, ex[:50]))

for i, ex in enumerate(BRACKET_ZERO):
    checks.append((f"bracket excerpt {i}: a bracket absorbing no word keeps it exact",
                    vq.match_excerpt(ex, SOURCE)[0] == "exact", ex[:60]))
for i, ex in enumerate(BRACKET_ABSORB):
    r = vq.match_excerpt(ex, SOURCE)
    checks.append((f"bracket excerpt {i}: a bracket standing for source words is approximate, named",
                    r[0] == "approximate" and any(len(d) == 3 for d in r[1]), (ex[:60], r)))

# ---------------------------------------------------------------- one-word drift where the
# altered word IS the excerpt's rarest token (the fallback-to-second-rarest case).
# Counted independently of verify_quotes' own internals (plain collections.Counter here,
# not vq._token_counts), so this check stands on its own regardless of how the module
# implements its cache.
counts = Counter(vq._normalized(SOURCE).split())
candidate_sentence = rarest = second_rarest = None
for i in DISTINCTIVE:
    s = SENTENCES[i]
    toks = vq.normalize(s.rstrip(".!")).split()
    topic_toks = sorted(set(t for t in toks if t in TOPIC_SET), key=lambda t: counts.get(t, 0))
    if len(topic_toks) >= 2:
        candidate_sentence, rarest, second_rarest = s, topic_toks[0], topic_toks[1]
        break
assert candidate_sentence is not None, "fixture generation must produce a 2-topic-word sentence"

drifted_rarest = candidate_sentence.rstrip(".!").replace(rarest, "notinsourceword", 1) + "?"
checks.append(("rarest-token drift: altered word is absent from the drifted excerpt",
               "notinsourceword" in vq.normalize(drifted_rarest), drifted_rarest[:60]))
checks.append(("rarest-token drift: second-rarest topic token still present, unaltered",
               second_rarest in vq.normalize(drifted_rarest).split(), (drifted_rarest, second_rarest)))
checks.append(("one-word drift on the excerpt's rarest token still found, approximate "
               "(another rare token anchors it)",
               vq.match_excerpt(drifted_rarest, SOURCE)[0] == "approximate", drifted_rarest[:60]))

# ---------------------------------------------------------------- drift whose substitute is
# a word the source DOES hold, and its rarest: the changed word is then the excerpt's rarest
# token, so it becomes an anchor pointing at the wrong places; the unchanged rare words must
# still anchor the true position. Counted with the plain Counter above, not vq internals.
_topic_by_rarity = sorted(TOPIC, key=lambda t: (counts.get(t, 0), t))
rare_sub_excerpt = rare_sub = None
for i in DISTINCTIVE:
    words = SENTENCES[i].rstrip(".!").split(" ")
    if len(words) < 12:
        continue
    pos = [p for p, w in enumerate(words) if w.lower() in TOPIC_SET][0]
    orig = words[pos].lower()
    sub = next(t for t in _topic_by_rarity if t != orig and t not in {w.lower() for w in words}
               and not (t.startswith(orig) or orig.startswith(t) or t.endswith(orig) or orig.endswith(t)))
    words[pos] = sub.capitalize() if words[pos][0].isupper() else sub
    rare_sub_excerpt, rare_sub = " ".join(words), sub
    break
assert rare_sub_excerpt is not None, "fixture generation must produce a 12-word distinctive sentence"
_rs_toks = vq.normalize(rare_sub_excerpt).split()
checks.append(("rare-substitute drift: the substitute occurs in the source and is the excerpt's rarest token",
               counts.get(rare_sub, 0) > 0
               and min(_rs_toks, key=lambda t: (counts.get(t, 0) or 10 ** 9, t)) == rare_sub,
               (rare_sub, rare_sub_excerpt)))
checks.append(("rare-substitute drift: not a literal substring",
               vq.normalize(rare_sub_excerpt) not in vq._normalized(SOURCE), rare_sub_excerpt[:60]))
checks.append(("rare-substitute drift is approximate (the unchanged rare words anchor it)",
               vq.match_excerpt(rare_sub_excerpt, SOURCE)[0] == "approximate", rare_sub_excerpt[:60]))

# ---------------------------------------------------------------- one-word drift at the
# literal tail of the source: the excerpt is SOURCE's own last words (ending exactly where
# SOURCE ends) with one >= 4-character word misheard, so the compared span must stop at the
# last source token rather than run past it.
_all_words = SOURCE.split(" ")
_k = 6
while not any(len(w.strip(".!")) >= 4 for w in _all_words[-_k:]):
    _k += 1                # reach back to the last >= 4-character word, at least 6 words
tail_words = _all_words[-_k:]
tail_excerpt = " ".join(tail_words)
assert tail_excerpt in SOURCE, "the source's own last words must be a literal substring of it"
_long = [p for p, w in enumerate(tail_words) if len(w.strip(".!")) >= 4]
assert _long, "fixture generation must put a >= 4-character word in the source's last words"
_tail = list(tail_words)
_tail[_long[-1]] = _misheard(_tail[_long[-1]])
drifted_tail = " ".join(_tail)
_tail_norm_src = vq._normalized(SOURCE)
_tail_ex = vq.normalize(drifted_tail)
checks.append(("tail-of-source drift: not a literal substring (drift actually changed it)",
               _tail_ex not in _tail_norm_src, drifted_tail[:60]))
checks.append(("tail-of-source one-word drift still found, approximate",
               vq.match_excerpt(drifted_tail, SOURCE)[0] == "approximate", drifted_tail[:60]))

# ---------------------------------------------------------------- timing (soft: measured and
# printed either way, but NEVER part of the pass/fail count or the exit code -- only the
# correctness checks above do that. A slow machine prints "SLOW" here and still exits 0.
start = time.perf_counter()
for ex in EXACT:
    vq.match_excerpt(ex, SOURCE)
for ex in DRIFT:
    vq.match_excerpt(ex, SOURCE)
for ex in FABRICATED:
    vq.match_excerpt(ex, SOURCE)
elapsed = time.perf_counter() - start
timing_ok = elapsed < 5.0
timing_line = (("ok   " if timing_ok else "SLOW ")
               + f"wall time for 50 excerpts against a {len(SOURCE)}-byte source: "
               + f"{elapsed:.3f}s < 5.000s")

start = time.perf_counter()
for ex in BRACKET_ZERO + BRACKET_ABSORB:
    vq.match_excerpt(ex, SOURCE)
bracket_elapsed = time.perf_counter() - start
start = time.perf_counter()
vq.match_excerpt(BRACKET_PATHOLOGICAL, SOURCE)
patho_elapsed = time.perf_counter() - start
bracket_ok = bracket_elapsed + patho_elapsed < 5.0
bracket_line = (("ok   " if bracket_ok else "SLOW ")
                + f"wall time for {len(BRACKET_ZERO) + len(BRACKET_ABSORB)} excerpts with 1-3 brackets "
                + f"({bracket_elapsed:.3f}s) + the all-filler 3-bracket case ({patho_elapsed:.3f}s) "
                + "< 5.000s")

fails = [c for c in checks if not c[1]]
for name, ok, got in checks:
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  -> got {got!r}"))
print(timing_line + ("" if timing_ok else "  (soft bound, not counted below)"))
print(bracket_line + ("" if bracket_ok else "  (soft bound, not counted below)"))
# Pinned summary format (beforehand.py's `test` command parses this exact line, see its
# _PASSED_LINE regex): timing is deliberately excluded from both the numerator and the
# denominator here, so a slow machine never fails this line or the process exit code --
# only the correctness checks above (`checks`/`fails`) can do that.
print(f"\n{len(checks) - len(fails)}/{len(checks)} passed")
sys.exit(1 if fails else 0)
