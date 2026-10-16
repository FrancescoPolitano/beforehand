#!/usr/bin/env python3
"""panel: validate one reviewer's output, and aggregate a round of them (SPEC-0.2 FR-5.2).

Why this module exists. A panel round produces one answer per persona, and everything the
report and the snapshot need from those answers is counting: which objections were raised,
which of them violate a red line, which two personas anchored on the same sentence, what
each persona could not judge, how many objections each returned and at what mean severity.
Done by hand that is transcription work, and transcription is where a measurement instrument
quietly loses rows. The weighted synthesis, the conflict adjudication and the dynamics round
stay with the model: those are judgments. This command does the arithmetic under them.

The reviewer answers with one fenced block, info string pinned as ```json personas-review```,
so the block can be found in a file that also carries prose. Prose is ignored, with one
exception: exactly one line `isolation: enforced-tools | staged | inline | emulated` **above**
the block is the flow's own annotation of how that reviewer was boxed (FR-5.1). It sits
outside the block on purpose — the reviewer does not know which shape the host allowed, and
reviewer output is never edited after the fact. `--aggregate` refuses a round in which any
output lacks it: the column is pinned to those four values, and a guessed fifth one would
travel into the snapshot, which calibration stratifies on.

Two modes:

  --validate FILE [--document DOC]
      Check one output against the schema. Exit 0, or 1 printing one
      `schema error at <json.path>: <reason>` line per problem, so the flow can hand the
      message straight back to the reviewer in the one re-request it is allowed.

  --aggregate DIR --roster INDEX.md [--document DOC] [--json]
      Read every reviewer output in DIR (`.md`, `.json`, `.txt`, any case), refuse the lot
      if any one of them is malformed, unannotated, names a persona the roster does not
      list — a silently dropped persona biases the panel — or is a second round-1 block for
      a persona (`two round-1 outputs for <slug>: <file-a>, <file-b>`), and print, under the `control:` header
      line, six sections: the Round-1 objections table in snapshot format, Red-line
      violations, Shared anchors, Blind spots, Criteria, Method counts. One roster means one
      context: a review that spans contexts runs this command once per context, each with its own
      index and its own directory, and the tables are concatenated, so every row keeps the
      context its persona was convened from. `?` marks a cell only the model can fill (the
      event, whether the document changed). Outputs from later rounds are reported but never
      enter the round-1 table: round 1 on a given document version is the measurement.

  --aggregate … --controls DIR [--overrides FILE]
      DIR holds the control round (FR-5.3): one output per rostered persona, same prompt,
      same isolation shape, same schema, from a stub carrying the role and the decision
      function and no evidence — so whatever it objects, the job title alone produced. Each
      block names `control-<slug>` of a rostered persona and answers round 1; anything else
      is refused, because a control counted against the wrong persona is worse than none.
      A round-1 row then reads `yes` in the Role-generic column when *its own* persona's
      control shares the anchor (the 60% rule below) and `no` otherwise; one control
      objection proposes `yes` for every row of its persona whose anchor it shares, since
      the match is asked per row and a control objection is not consumed by the first row it
      matches. Without `--controls` the column reads `estimated`: no control ran, the value
      is the model's own proxy and calibration labels it so.

      A control with no objections and `greenlight: INSUFFICIENT_BASIS` abstained, and an
      abstention measures nothing: proposing `no` from it would make the column look
      measured when it is not. Its persona's rows stay `estimated`, Method counts prints
      `control degenerate: <slug> (0 objections, INSUFFICIENT_BASIS): its rows stay
      estimated`, and an override naming one of those rows is refused (exit 1), because
      there is no proposal for it to confirm. A control with no objections and a `YES` or
      `NO` answered: the role alone produced nothing, and its persona's rows read `no`.

      The column carries those three values and nothing else, because the table is pasted
      into the snapshot unedited. The proposal is not the verdict — the anchor is shared,
      the substance may not be — so Method counts lists every row still only proposed,
      `role-generic proposed, unconfirmed: <slug>#<n>, …` (`none` when there are none), and
      the model confirms them, recording any changed verdict in `--overrides FILE`, one per
      line:

          <slug>#<n>=yes|no: <reason>

      `<n>` is the position of the objection inside that persona's own block, counting from
      1, which is the only row identity that exists before the snapshot is written (`P<k>`
      is numbered later, in the snapshot). An overridden row leaves that list and its
      proposal, confirmed value and reason are printed side by side in Method. The overrides
      file lives *beside* the controls directory, never inside it: everything in that
      directory is read as a control block.

      Control objections are never gradeable rows: they appear in Method counts and nowhere
      else — not in the Round-1 table, not in Red-line violations even when the control
      raised one, not in Shared anchors or Blind spots — and the control's own greenlight is
      dropped.

  --validate|--aggregate … --document DOC
      The computable half of the criteria rule (FR-2.3). Every `criteria[].evidence` is
      looked up in DOC, split once into *structural* lines — a leading frontmatter block,
      `#` headings outside fences (``` and ~~~ fences each close only on their own
      marker), a table header row (a `|` line whose next line is the rule row), a
      `key: value` metadata line under 80 characters in the preamble before the first `##`
      (a document with no `##` has no preamble), and the label span of a line-leading
      `**Label:**` or `**Label**:` (a bold sentence without the colon is body) — and
      everything else, which is the body. Evidence counts as structural only when it sits
      inside a structural line; a short heading never "finds" a longer quote that holds its
      words. A `met` whose evidence is found only among the structural
      lines is recorded `declared` with check `structural` and printed
      `criteria[i]: declared — evidence sits only in a heading or metadata line: "<line>"`;
      evidence found nowhere is `schema error at criteria[i].evidence: not found in <DOC>`
      and exits 1. Without `--document` every check reads `unchecked` and nothing is forced.

      The check only ever demotes. It never promotes a verdict and never says that a body
      quote demonstrates the criterion — that judgment is the reviewer's and calibration's.
      Its limits, stated rather than papered over: a one-word evidence string that also
      occurs somewhere in the prose passes as body; a body sentence that names the criterion
      without meeting it passes; HTML headings are not recognised, because a reviewer reads
      the rendered text and parsing HTML here would trade a plain rule for a fragile one.

Shared anchors: two objections from *different* personas whose `quote` fields, normalised
the way the lint gate normalises excerpts, share a substring covering at least 60% of the
shorter one. That is a candidate conflict or a candidate agreement — which one it is, is
the model's call. The same 60% rule matches a control objection to the persona objection it
may have produced, and there the two sides are the same person by construction.

Usage:
  panel.py --validate FILE [--document DOC]
  panel.py --aggregate DIR --roster INDEX.md [--controls DIR] [--overrides FILE]
           [--document DOC] [--json]
"""
import argparse
import difflib
import json
import re
import sys

sys.dont_write_bytecode = True
from pathlib import Path  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from personas_lib import frontmatter_span, locale_regexes, read_text_lenient, sections  # noqa: E402
from verify_quotes import excerpt_in_source, normalize  # noqa: E402

SCHEMA = "0.2"
BLOCK_INFO = "json personas-review"
# Fenced block, info string pinned: this is how the block is found in a file of prose.
BLOCK_RE = re.compile(r"^[ \t]*```[ \t]*" + re.escape(BLOCK_INFO) + r"[ \t]*$(.*?)^[ \t]*```[ \t]*$",
                      re.M | re.S)
ISOLATION_RE = re.compile(r"^[ \t]*isolation:[ \t]*([A-Za-z-]+)[ \t]*$", re.M)
ISOLATION_SHAPES = ("enforced-tools", "staged", "inline", "emulated")
SHAPES_LIST = " | ".join(ISOLATION_SHAPES)
GREENLIGHTS = ("YES", "NO", "INSUFFICIENT_BASIS")
# `grounds` names the section of the persona file that carries the objection: the six
# judgment sections of the template, or Background.
GROUNDS = ("Mandate and incentives", "Judgment criteria", "Recurring objections", "Red lines",
           "Language and dissent style", "Panel dynamics", "Background")
GROUNDS_BY_LOWER = {g.lower(): g for g in GROUNDS}
# The template's heading is `Background and track record`; a reviewer citing the heading it
# actually read is right, so the full title is an alias of the canonical short name.
GROUNDS_BY_LOWER["background and track record"] = "Background"
OVERLAP_THRESHOLD = 0.60
# One row per item of the persona's `## Judgment criteria` (FR-2.2). `declared` is the
# verdict the aggregate can force and the reviewer rarely returns: the criterion is named by
# the document and demonstrated nowhere in its body.
CRITERIA_VERDICTS = ("met", "declared", "unmet", "not-addressed")
VERDICTS_LIST = " | ".join(CRITERIA_VERDICTS)
# Where the aggregate found that row's evidence in the document (FR-2.3). `unchecked` is
# both "no --document was given" and "the row quotes nothing to look for".
CRITERIA_CHECKS = ("body", "structural", "not-found", "unchecked")
CRITERIA_SECTION = "Judgment criteria"
ROSTER_LINE_RE = re.compile(r"^-\s+([a-z0-9][a-z0-9-]*)\s*\|")
FILL_IN = "?"          # a cell the model fills: event, doc changed
CONTROL_PREFIX = "control-"   # a control block names control-<slug> of a rostered persona
ESTIMATED = "estimated"       # the Role-generic value when no control round ran (FR-5.3)
OVERRIDE_FORM = "<slug>#<n>=yes|no: <reason>"
OVERRIDE_RE = re.compile(r"^([a-z0-9][a-z0-9-]*)#([0-9]+)[ \t]*=[ \t]*(yes|no)[ \t]*:[ \t]*(\S.*)$")


# --------------------------------------------------------------------------- the block
def extract_block(text):
    """(json_text, isolation or None, error). The block is located by its info string;
    everything else in the file is prose, except the flow's own `isolation:` annotation,
    which is read from the prose *above* the block — a header, so that a line appearing in
    quoted material after the answer cannot silently retag the round."""
    blocks = BLOCK_RE.findall(text)
    if not blocks:
        return None, None, ("$", "no fenced ```%s block in the file" % BLOCK_INFO)
    if len(blocks) > 1:
        return None, None, ("$", "%d fenced ```%s blocks, expected 1" % (len(blocks), BLOCK_INFO))
    header = text[:BLOCK_RE.search(text).start()]
    found = ISOLATION_RE.findall(header)
    if len(found) > 1:
        return None, None, ("isolation", "%d isolation lines above the block, expected 1"
                            % len(found))
    isolation = found[0] if found else None
    if isolation is not None and isolation not in ISOLATION_SHAPES:
        return None, None, ("isolation", "%r is not one of %s" % (isolation, SHAPES_LIST))
    return blocks[0], isolation, None


def parse_block(text):
    """(obj, error). Only a JSON object is a reviewer output."""
    block, isolation, err = extract_block(text)
    if err is not None:
        return None, None, err
    try:
        obj = json.loads(block)
    except ValueError as exc:
        return None, None, ("$", "the block is not valid JSON (%s)" % exc)
    if not isinstance(obj, dict):
        return None, None, ("$", "the block is a %s, expected a JSON object"
                            % type(obj).__name__)
    return obj, isolation, None


# --------------------------------------------------------------------------- the schema
def _is_str(v):
    return isinstance(v, str)


def _is_int(v):
    # bool is an int in Python and `"severity": true` must not pass as severity 1.
    return isinstance(v, int) and not isinstance(v, bool)


def _list(errors, value, path, what="a list"):
    """True when `value` is a list; otherwise one `expected <what>, got <type>` error."""
    if isinstance(value, list):
        return True
    errors.append((path, "expected %s, got %s" % (what, type(value).__name__)))
    return False


def _str_list(errors, value, path):
    if not _list(errors, value, path, "a list of strings"):
        return False
    for i, item in enumerate(value):
        if not _is_str(item):
            errors.append(("%s[%d]" % (path, i),
                           "expected a string, got %s" % type(item).__name__))
    return True


def _objection(errors, item, path):
    if not isinstance(item, dict):
        errors.append((path, "expected an object, got %s" % type(item).__name__))
        return
    for key in ("quote", "objection", "grounds"):
        if key not in item:
            errors.append(("%s.%s" % (path, key), "missing"))
        elif not _is_str(item[key]) or not item[key].strip():
            errors.append(("%s.%s" % (path, key), "expected a non-empty string"))
    if _is_str(item.get("grounds")) and item["grounds"].strip():
        if item["grounds"].strip().lower() not in GROUNDS_BY_LOWER:
            errors.append(("%s.grounds" % path,
                           "%r is not a persona section; expected one of: %s"
                           % (item["grounds"], ", ".join(GROUNDS))))
    if "severity" not in item:
        errors.append(("%s.severity" % path, "missing"))
    elif not _is_int(item["severity"]):
        errors.append(("%s.severity" % path,
                       "expected an integer 1-5, got %s" % type(item["severity"]).__name__))
    elif not 1 <= item["severity"] <= 5:
        errors.append(("%s.severity" % path,
                       "expected an integer 1-5, got %s" % item["severity"]))
    if "red_line" not in item:
        errors.append(("%s.red_line" % path, "missing"))
    elif not isinstance(item["red_line"], bool):
        errors.append(("%s.red_line" % path,
                       "expected true or false, got %s" % type(item["red_line"]).__name__))


def _criterion(errors, item, path):
    """One row of `criteria`: the criterion as the persona file writes it, a verdict, and
    the passage the verdict rests on. `met` is the only verdict that demands a passage and
    `not-addressed` the only one that forbids one — a `met` with nothing quoted is the
    failure this array exists to make visible."""
    if not isinstance(item, dict):
        errors.append((path, "expected an object, got %s" % type(item).__name__))
        return
    if "criterion" not in item:
        errors.append(("%s.criterion" % path, "missing"))
    elif not _is_str(item["criterion"]) or not item["criterion"].strip():
        errors.append(("%s.criterion" % path,
                       "expected a non-empty string: one item of your %s, as written there"
                       % CRITERIA_SECTION))
    if "verdict" not in item:
        errors.append(("%s.verdict" % path, "missing"))
    elif item["verdict"] not in CRITERIA_VERDICTS:
        errors.append(("%s.verdict" % path, "expected one of %s, got %r"
                       % (VERDICTS_LIST, item["verdict"])))
    if "evidence" not in item:
        errors.append(("%s.evidence" % path, "missing"))
    elif not _is_str(item["evidence"]):
        errors.append(("%s.evidence" % path,
                       "expected a string, got %s" % type(item["evidence"]).__name__))
    elif item.get("verdict") == "met" and not item["evidence"].strip():
        errors.append(("%s.evidence" % path, "met requires the body passage it rests on"))
    elif item.get("verdict") == "not-addressed" and item["evidence"].strip():
        errors.append(("%s.evidence" % path,
                       "not-addressed quotes nothing; use unmet or declared for a passage "
                       "that fails it"))


def _loose_items(errors, value, path):
    """`fixed`, `still_open` and `keep` carry either a sentence or an object with the quote
    and the section: the round-N prompt asks for a quote, not for a fixed record shape."""
    if not _list(errors, value, path):
        return
    for i, item in enumerate(value):
        if not (_is_str(item) or isinstance(item, dict)):
            errors.append(("%s[%d]" % (path, i),
                           "expected a string or an object, got %s" % type(item).__name__))


ROUND_N_KEYS = ("fixed", "still_open", "new", "keep")


def validate(obj):
    """Every schema problem, as (json path, reason) pairs, in reading order."""
    errors = []
    for key in ("schema", "persona", "read", "no_basis", "greenlight", "greenlight_changes",
                "signoff_criterion", "overall", "round"):
        if key not in obj:
            errors.append((key, "missing"))

    if "schema" in obj and obj["schema"] != SCHEMA:
        errors.append(("schema", "expected %r, got %r" % (SCHEMA, obj["schema"])))
    if "persona" in obj and (not _is_str(obj["persona"]) or not obj["persona"].strip()):
        errors.append(("persona", "expected a non-empty slug string"))
    if "read" in obj:
        _str_list(errors, obj["read"], "read")
    if "no_basis" in obj:
        _str_list(errors, obj["no_basis"], "no_basis")
    if "greenlight_changes" in obj:
        _str_list(errors, obj["greenlight_changes"], "greenlight_changes")
    if "greenlight" in obj and obj["greenlight"] not in GREENLIGHTS:
        errors.append(("greenlight", "expected one of %s, got %r"
                       % (" | ".join(GREENLIGHTS), obj["greenlight"])))
    if obj.get("greenlight") == "NO" and isinstance(obj.get("greenlight_changes"), list) \
            and not obj["greenlight_changes"]:
        errors.append(("greenlight_changes",
                       "greenlight NO requires the one or two changes that would make it YES"))
    for key in ("signoff_criterion", "overall"):
        if key in obj and (not _is_str(obj[key]) or not obj[key].strip()):
            errors.append((key, "expected a non-empty string"))

    # `criteria` is required in every round, round 1 and round N alike: a criterion the
    # document declared in round 1 and demonstrates in round 3 is what a fix looks like,
    # and `fixed[]` is objection-shaped, so it cannot carry that.
    if "criteria" not in obj:
        errors.append(("criteria", "missing: every round answers the persona's %s; [] when "
                                   "that section is declared empty" % CRITERIA_SECTION))
    elif _list(errors, obj["criteria"], "criteria"):
        for i, item in enumerate(obj["criteria"]):
            _criterion(errors, item, "criteria[%d]" % i)

    rnd = obj.get("round")
    if "round" in obj:
        if not _is_int(rnd):
            errors.append(("round", "expected an integer >= 1, got %s" % type(rnd).__name__))
            rnd = None
        elif rnd < 1:
            errors.append(("round", "expected an integer >= 1, got %s" % rnd))
            rnd = None

    if rnd is not None and rnd >= 2:
        if "objections" in obj:
            errors.append(("objections",
                           "a round-%d answer carries fixed/still_open/new/keep, never "
                           "objections: only round 1 is the measurement" % rnd))
        for key in ROUND_N_KEYS:
            if key not in obj:
                errors.append((key, "missing: round %d requires %s"
                               % (rnd, "/".join(ROUND_N_KEYS))))
        for key in ("fixed", "still_open", "keep"):
            if key in obj:
                _loose_items(errors, obj[key], key)
        if "new" in obj and _list(errors, obj["new"], "new"):
            for i, item in enumerate(obj["new"]):
                _objection(errors, item, "new[%d]" % i)
    else:
        if "objections" not in obj:
            errors.append(("objections", "missing: round 1 requires the objections list"))
        elif _list(errors, obj["objections"], "objections"):
            for i, item in enumerate(obj["objections"]):
                _objection(errors, item, "objections[%d]" % i)
        for key in ROUND_N_KEYS:
            if key in obj and _list(errors, obj[key], key):
                if obj[key]:
                    errors.append((key, "round 1 carries no %s: it is the first reading of "
                                        "this version" % key))
    return errors


def canonical_grounds(value):
    return GROUNDS_BY_LOWER.get(str(value).strip().lower(), str(value).strip())


# --------------------------------------------------------------------------- overlap
def anchor_overlap(a, b):
    """Share of the shorter normalised quote covered by the longest common substring.

    Normalisation is the lint gate's (`verify_quotes.normalize`): case, punctuation and
    accents folded, so two reviewers quoting the same sentence with different typography
    still land on the same anchor."""
    na, nb = normalize(a or ""), normalize(b or "")
    if not na or not nb:
        return 0.0
    best = difflib.SequenceMatcher(None, na, nb, autojunk=False).find_longest_match(
        0, len(na), 0, len(nb))
    return best.size / float(min(len(na), len(nb)))


# ------------------------------------------------------------------ the document check
FENCE_RE = re.compile(r"^[ \t]*(```|~~~)")
HEADING_LINE_RE = re.compile(r"^#{1,6}\s")
SUBHEADING_LINE_RE = re.compile(r"^#{2,6}\s")
TABLE_RULE_RE = re.compile(r"^\|[\s:|-]*\|$")
# A `key: value` line, short, and only in the preamble: `Note: the price includes VAT`
# deeper in the body is a sentence, not a field title, and misreading it as one would let
# the check demote a criterion the body does meet.
META_LINE_RE = re.compile(r"^[A-Za-z][\w /-]{0,40}:\s*\S")
META_LINE_MAX = 80
# The colon is what makes a bold span a label (A9): `**Label:**` or `**Label**:`. A bold
# sentence without one is emphasis on something the document says, which is body.
BOLD_LABEL_RE = re.compile(r"^(?:[-*]\s+)?\*\*([^*]{1,60})(?::\*\*|\*\*:)")
COMMENT_LINE_RE = re.compile(r"^[ \t]*<!--")


def split_document(text):
    """(body text, [structural lines]) — the one classifier both modes share (FR-2.3).

    A structural line names something; a body line says it. The five structural kinds are
    pinned in the module docstring and nowhere else: a leading frontmatter block, a heading
    outside fences, a table header row, a short `key: value` line in the preamble, and the
    label span of a line-leading `**Label:**` (the rest of that line is body). Blank lines,
    table rule rows, HTML comments and fence markers are neither. Fenced content, table data
    rows and list items are body — which is where a document that delivers says so.
    """
    lines = text.splitlines()
    structural, body = [], []
    start = 0
    span = frontmatter_span(text)
    if span is not None:
        start = len(text[span[0]:span[1]].splitlines())
        structural.extend(lines[:start])
    # One pass classifies fences (a fence closes only on its own marker, so a ``` inside
    # ~~~ is content and vice versa — D4), and says whether the document has a `##` at all:
    # the preamble is what sits above the first `##`, so without one there is none.
    fenced, fence = [], None
    for i in range(start, len(lines)):
        m = FENCE_RE.match(lines[i])
        if m is not None and (fence is None or m.group(1) == fence):
            fenced.append("marker")
            fence = m.group(1) if fence is None else None
        else:
            fenced.append("in" if fence is not None else "out")
    preamble = any(kind == "out" and SUBHEADING_LINE_RE.match(lines[start + j])
                   for j, kind in enumerate(fenced))
    for i in range(start, len(lines)):
        line = lines[i].rstrip()
        stripped = line.strip()
        kind = fenced[i - start]
        if kind == "marker":
            continue
        if kind == "in":
            body.append(line)
            continue
        if not stripped or COMMENT_LINE_RE.match(line):
            continue
        if HEADING_LINE_RE.match(line):
            structural.append(line)
            if SUBHEADING_LINE_RE.match(line):
                preamble = False
            continue
        if TABLE_RULE_RE.match(stripped):
            continue
        following = lines[i + 1].strip() if i + 1 < len(lines) else ""
        if stripped.startswith("|") and TABLE_RULE_RE.match(following):
            structural.append(line)
            continue
        if preamble and len(stripped) < META_LINE_MAX and META_LINE_RE.match(stripped):
            structural.append(line)
            continue
        label = BOLD_LABEL_RE.match(stripped)
        if label is not None:
            structural.append(label.group(0))
            rest = stripped[label.end():].strip()
            if rest:
                body.append(rest)
            continue
        body.append(line)
    return "\n".join(body), structural


def classify_criterion(item, doc):
    """(verdict, check, the structural line it matched) for one `criteria` row.

    `doc` is `split_document(...)` or None. One-directional by construction: the only
    verdict this can change is a `met` whose evidence lives in a structural line and nowhere
    in the body, and it changes it to `declared`. Nothing here ever promotes a verdict, and
    finding the evidence in the body says only that the quote is body text — whether it
    demonstrates the criterion is the reviewer's judgment and calibration's to grade.
    """
    returned = item.get("verdict")
    evidence = item.get("evidence") or ""
    if doc is None or not evidence.strip():
        return returned, "unchecked", ""
    body_text, structural = doc
    if excerpt_in_source(evidence, body_text):
        return returned, "body", ""
    # One direction only (A8): the evidence must sit inside a structural line. The reverse
    # let a short heading "find" any invented sentence that happened to contain its word.
    ev = normalize(evidence)
    for line in structural:
        normalized = normalize(line)
        if not normalized or not ev:
            continue
        if ev in normalized:
            return ("declared" if returned == "met" else returned), "structural", line
    return returned, "not-found", ""


def criteria_summary(verdicts):
    """The `ok:` line's pinned suffix: every verdict counted, in the pinned order, including
    the zeros — a count that disappears when it is 0 is a count nobody can read."""
    counted = dict((v, 0) for v in CRITERIA_VERDICTS)
    for verdict in verdicts:
        if verdict in counted:
            counted[verdict] += 1
    return "criteria " + " / ".join("%d %s" % (counted[v], v) for v in CRITERIA_VERDICTS)


def criteria_item_count(roster_path, slug):
    """Top-level `- ` bullets under the persona's `## Judgment criteria`, or None when the
    file is not there. The one place the aggregate reads past the blocks: a persona with
    four criteria whose reviewer answered two is a silently short answer, and the count line
    is the only thing that would say so."""
    path = Path(roster_path).resolve().parent / "personas" / ("%s.md" % slug)
    if not path.is_file():
        return None
    # `sections()`, not `section_body()`: a persona heading carries its own
    # `<!-- last evidence: … -->` note, which is metadata about the section and not part of
    # its name, and only `sections()` strips it before the title is compared.
    text = read_text_lenient(path)
    body = None
    for item in sections(text):
        if item.level == 2 and item.title.lower() == CRITERIA_SECTION.lower():
            body = item.body(text)
            break
    if body is None:
        return None
    empty_decl_re = locale_regexes()["empty_decl_re"]
    items = 0
    for line in body.splitlines():
        if not re.match(r"^-\s+\S", line):
            continue
        if empty_decl_re.search(line):
            continue
        items += 1
    return items


# --------------------------------------------------------------------------- roster
def read_roster(path):
    """(slugs in index order, context name). The context is the directory the index sits in:
    an index is always written into its own context (FR-4.7)."""
    text = read_text_lenient(path)
    slugs = []
    for line in text.splitlines():
        m = ROSTER_LINE_RE.match(line.strip())
        if m and m.group(1) not in slugs:
            slugs.append(m.group(1))
    return slugs, Path(path).resolve().parent.name


# --------------------------------------------------------------------------- overrides
def read_overrides(path):
    """({row key: (yes|no, reason)}, [message]). One confirmation per line,
    `<slug>#<n>=yes|no: <reason>`; `#` at the start of a line is a comment and blank lines
    are skipped. A malformed line, a reason-less verdict or a row confirmed twice is a
    message, never a silent drop: an override the aggregate ignored would leave the model
    believing it recorded a confirmation that never reached the table."""
    overrides, errors = {}, []
    for lineno, raw in enumerate(read_text_lenient(path).splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = OVERRIDE_RE.match(line)
        if m is None:
            errors.append("line %d: %r is not `%s`" % (lineno, line, OVERRIDE_FORM))
            continue
        index = int(m.group(2))
        if index < 1:
            errors.append("line %d: objection numbering starts at 1" % lineno)
            continue
        key = "%s#%d" % (m.group(1), index)
        if key in overrides:
            errors.append("line %d: %s is confirmed twice; one row carries one verdict"
                          % (lineno, key))
            continue
        overrides[key] = (m.group(3), m.group(4).strip())
    return overrides, errors


# --------------------------------------------------------------------------- rendering
def cell(value):
    """One markdown table cell: pipes escaped, newlines flattened."""
    return re.sub(r"\s+", " ", str(value)).replace("|", "\\|").strip()


def flat(value):
    """One line of prose outside a table: newlines flattened, pipes left alone — a table
    header row quoted back to the reader is unreadable with its pipes escaped."""
    return re.sub(r"\s+", " ", str(value)).strip()


def table(header, body_rows):
    out = ["| " + " | ".join(header) + " |",
           "|" + "|".join(["---"] * len(header)) + "|"]
    out.extend("| " + " | ".join(r) + " |" for r in body_rows)
    return out


# --------------------------------------------------------------------------- aggregate
def load_outputs(directory, skip=(), doc=None, doc_name=None):
    """([(path, obj, isolation)], [(path, message)]). A message is printed as it stands: the
    schema ones are the line the reviewer gets back, the isolation one is for the flow.
    `skip` holds resolved paths that are not reviewer output — the overrides file when it was
    saved inside the controls directory, which would otherwise be read as a malformed block.

    `doc`/`doc_name` (the round's document, when `--document` was given) turn a criterion
    quote found nowhere in it into a schema error like any other, so the round is refused and
    re-requested once rather than aggregated around a quotation nobody can locate. Controls
    are loaded without a document: their criteria are ignored, so nothing checks them."""
    skip = {Path(p).resolve() for p in skip}
    files = sorted(p for p in Path(directory).iterdir()
                   if p.is_file() and p.suffix.lower() in (".md", ".json", ".txt")
                   and not p.name.startswith(".") and p.resolve() not in skip)
    loaded, errors = [], []
    for path in files:
        obj, isolation, err = parse_block(read_text_lenient(path))
        if err is not None:
            errors.append((path, "schema error at %s: %s" % err))
            continue
        problems = validate(obj)
        if problems:
            errors.extend((path, "schema error at %s: %s" % (jp, reason))
                          for jp, reason in problems)
            continue
        if doc is not None:
            not_found = []
            for i, item in enumerate(obj["criteria"]):
                if classify_criterion(item, doc)[1] == "not-found":
                    not_found.append((path, "schema error at criteria[%d].evidence: "
                                            "not found in %s" % (i, doc_name)))
            if not_found:
                errors.extend(not_found)
                continue
        if isolation is None:
            errors.append((path, "isolation missing for %s: annotate the file with one of %s"
                           % (obj["persona"], SHAPES_LIST)))
            continue
        loaded.append((path, obj, isolation))
    return loaded, errors


def duplicate_round1(loaded):
    """[(path, message)] for every round-1 block whose persona already answered round 1 (D1).

    Two round-1 answers from one persona are two measurements where the panel has room for
    one: aggregated, the persona is counted twice in every table and its `<slug>#<n>` keys
    name two rows each. Which one stands is the flow's call, so the round is refused. The
    message names both files, the shape the control round's duplicate check uses."""
    first, errors = {}, []
    for path, obj, _isolation in loaded:
        if obj["round"] >= 2:
            continue
        persona = obj["persona"]
        if persona in first:
            errors.append((path, "two round-1 outputs for %s: %s, %s"
                           % (persona, first[persona], path.name)))
        else:
            first[persona] = path.name
    return errors


def control_errors(controls, slugs):
    """[(path, message)] for the control round: a duplicate control, a block that is not a
    control of this roster, a control that answered a later round. Collected here and
    printed once by the caller (S12)."""
    errors, seen = [], {}
    for path, obj, _isolation in controls:
        slug = control_slug(obj["persona"])
        if slug is not None and slug in seen:
            errors.append((path, "two control outputs for %s (%s and %s): one control per "
                                 "persona, or its objections are counted twice"
                           % (slug, seen[slug], path.name)))
            continue
        if slug is not None:
            seen[slug] = path.name
        if slug is None or slug not in slugs:
            errors.append((path, "%s is not a control of this roster: a control block names "
                                 "control-<slug> of a rostered persona" % obj["persona"]))
        elif obj["round"] >= 2:
            errors.append((path, "%s answered round %d: the round-N loop never runs controls"
                           % (obj["persona"], obj["round"])))
    return errors


def control_slug(persona):
    """The rostered persona a control block belongs to, or None."""
    if not persona.startswith(CONTROL_PREFIX):
        return None
    return persona[len(CONTROL_PREFIX):] or None


def aggregate(loaded, slugs, context, controls=None, overrides=None, doc=None,
              doc_name=None, roster_path=None):
    """The six sections, as data, under the `control:` header. Ordering follows the roster:
    a report reads in the same order as the index it was convened from.

    `controls` is the loaded control round (None when none ran) and `overrides` the model's
    confirmations, keyed `<slug>#<n>`. Control objections propose the Role-generic value of
    the rows of their own persona and enter no other section; a control's own `criteria`
    array is ignored the same way its greenlight is.

    `doc` is `split_document(...)` of the reviewed document, or None. Criteria rows are
    numbered `<slug>#c<n>` within that persona's own round-1 block, counting from 1 — the
    `<slug>#<n>` rule, in its own series, because an objection row and a criterion row of
    the same persona are two different things to point at."""
    order = {slug: i for i, slug in enumerate(slugs)}
    loaded = sorted(loaded, key=lambda t: (order.get(t[1]["persona"], len(order)), t[0].name))
    overrides = dict(overrides or {})

    # the control objections of each persona, whatever file they arrived in, and the
    # controls that abstained (no objection, INSUFFICIENT_BASIS): those measured nothing
    control_quotes = {}
    degenerate = set()
    if controls is not None:
        for _path, obj, _isolation in controls:
            slug = control_slug(obj["persona"])
            control_quotes.setdefault(slug, []).extend(obj["objections"])
            if not obj["objections"] and obj["greenlight"] == "INSUFFICIENT_BASIS":
                degenerate.add(slug)

    round1 = []
    blind = []
    counts = []
    later = []
    criteria = []
    declared_by_label = []
    for path, obj, isolation in loaded:
        persona = obj["persona"]
        if obj["round"] >= 2:
            later.append({"persona": persona, "round": obj["round"], "file": path.name})
            continue
        for n, item in enumerate(obj["criteria"], 1):
            verdict, check, line = classify_criterion(item, doc)
            row = {"persona": persona, "context": context, "key": "%s#c%d" % (persona, n),
                   "criterion": item["criterion"], "verdict": verdict,
                   "verdict_returned": item["verdict"], "evidence": item["evidence"],
                   "check": check}
            criteria.append(row)
            if verdict != item["verdict"]:
                declared_by_label.append({"key": row["key"], "line": line})
        for n, item in enumerate(obj["objections"], 1):
            round1.append({"persona": persona, "context": context, "isolation": isolation,
                           "key": "%s#%d" % (persona, n),
                           "quote": item["quote"], "objection": item["objection"],
                           "grounds": canonical_grounds(item["grounds"]),
                           "severity": item["severity"], "red_line": bool(item["red_line"]),
                           "round_tag": "r1", "file": path.name})
        if obj["no_basis"]:
            blind.append({"persona": persona, "items": list(obj["no_basis"])})
        sev = [i["severity"] for i in obj["objections"]]
        counts.append({"persona": persona, "context": context,
                       "objections": len(obj["objections"]),
                       "mean_severity": round(sum(sev) / float(len(sev)), 1) if sev else 0.0,
                       "greenlight": obj["greenlight"], "isolation": isolation})

    # Role-generic (FR-5.3): proposed from the persona's own control, confirmed by the model.
    applied = []
    degenerate_overrides = []
    for row in round1:
        if controls is None or row["persona"] in degenerate:
            row["role_generic"] = ESTIMATED
            row["role_generic_status"] = ESTIMATED
            if row["key"] in overrides:
                degenerate_overrides.append(row["key"])
                continue
        else:
            best, best_quote = 0.0, None
            for item in control_quotes.get(row["persona"], []):
                overlap = anchor_overlap(row["quote"], item["quote"])
                if overlap > best:
                    best, best_quote = overlap, item["quote"]
            row["role_generic"] = "yes" if best >= OVERLAP_THRESHOLD else "no"
            row["role_generic_status"] = "proposed"
            row["control_overlap"] = round(best, 2)
            if best >= OVERLAP_THRESHOLD:
                row["control_quote"] = best_quote
        verdict = overrides.get(row["key"])
        if verdict is not None:
            applied.append({"key": row["key"], "persona": row["persona"],
                            "proposed": row["role_generic"], "confirmed": verdict[0],
                            "reason": verdict[1]})
            row["role_generic"] = verdict[0]
            row["role_generic_status"] = "confirmed"

    red_lines = [o for o in round1 if o["red_line"]]

    shared = []
    for i in range(len(round1)):
        for j in range(i + 1, len(round1)):
            a, b = round1[i], round1[j]
            if a["persona"] == b["persona"]:
                continue
            ov = anchor_overlap(a["quote"], b["quote"])
            if ov >= OVERLAP_THRESHOLD:
                shared.append({"persona_a": a["persona"], "persona_b": b["persona"],
                               "overlap": round(ov, 2), "quote_a": a["quote"],
                               "quote_b": b["quote"]})
    shared.sort(key=lambda s: (-s["overlap"], s["persona_a"], s["persona_b"]))

    answered = {c["persona"] for c in counts}
    notes = []
    missing = [s for s in slugs if s not in answered]
    if missing:
        notes.append("no round-1 output: " + ", ".join(missing))
    for item in later:
        notes.append("later rounds: %s round %d" % (item["persona"], item["round"]))

    control_counts = []
    if controls is not None:
        control_counts = [{"persona": slug, "objections": len(control_quotes[slug])}
                          for slug in slugs if slug in control_quotes]
        uncontrolled = [s for s in slugs if s in answered and s not in control_quotes]
        if uncontrolled:
            notes.append("no control output: " + ", ".join(uncontrolled))
        for slug in slugs:
            if slug in degenerate:
                notes.append("control degenerate: %s (0 objections, INSUFFICIENT_BASIS): its "
                             "rows stay %s" % (slug, ESTIMATED))

    # Row keys are unique: `main` refuses a round with two round-1 blocks for one persona
    # (`duplicate_round1`) before it gets here.
    keys = {row["key"] for row in round1}
    unknown_overrides = sorted(k for k in overrides if k not in keys)

    # The cross-check the aggregate reads past the blocks for: how many items that persona's
    # `## Judgment criteria` holds, against how many rows its reviewer returned.
    item_counts = []
    if roster_path is not None:
        for row in counts:
            items = criteria_item_count(roster_path, row["persona"])
            if items is None:
                continue
            item_counts.append({"persona": row["persona"], "items": items,
                                "rows": len([c for c in criteria
                                             if c["persona"] == row["persona"]])})
    return {"control": "yes" if controls is not None else "no",
            "context": context, "round1": round1, "red_lines": red_lines,
            "shared_anchors": shared,
            "blind_spots": {b["persona"]: b["items"] for b in blind},
            "blind_spot_order": [b["persona"] for b in blind],
            "criteria": criteria, "criteria_declared_by_label": declared_by_label,
            "criteria_item_counts": item_counts,
            "document": doc_name,
            "method_counts": counts, "control_counts": control_counts,
            "unconfirmed": [row["key"] for row in round1
                            if row["role_generic_status"] == "proposed"],
            "overrides": applied, "unknown_overrides": unknown_overrides,
            "degenerate_controls": [s for s in slugs if s in degenerate],
            "degenerate_overrides": sorted(degenerate_overrides), "notes": notes}


def role_generic_cell(row):
    """`estimated` with no control round, the bare verdict with one. The column is pinned to
    those three values and the table is pasted into the snapshot unedited, so which rows are
    still only proposed is said in Method counts, never inside a cell."""
    if row["role_generic_status"] == ESTIMATED:
        return ESTIMATED
    return row["role_generic"]


def render(result):
    out = ["control: %s" % result["control"], "", "## Round-1 objections"]
    out.extend(table(["Persona", "Context", "Isolation", "Anchor in the document", "Objection",
                      "Severity", "Round tag", "Event", "Role-generic", "Doc changed"],
                     [[cell(o["persona"]), cell(o["context"]), cell(o["isolation"]),
                       '"%s"' % cell(o["quote"]), cell(o["objection"]), str(o["severity"]),
                       o["round_tag"], FILL_IN, role_generic_cell(o), FILL_IN]
                      for o in result["round1"]]))
    out.append("(Event and Doc changed are marked `%s`: the aggregator cannot fill them.)"
               % FILL_IN)
    if result["control"] == "yes":
        out.append("(Role-generic carries the control round's verdict: the rows it only "
                   "proposed, and that no override has confirmed, are listed in Method counts "
                   "— confirm those, do not edit the table.)")
    else:
        out.append("(Role-generic reads `%s`: no control round ran, so the value is your own "
                   "proxy and calibration reports it under that label.)" % ESTIMATED)

    out.append("")
    out.append("## Red-line violations")
    if result["red_lines"]:
        out.extend(table(["Persona", "Context", "Anchor in the document", "Objection",
                          "Severity", "Grounds"],
                         [[cell(o["persona"]), cell(o["context"]), '"%s"' % cell(o["quote"]),
                           cell(o["objection"]), str(o["severity"]), cell(o["grounds"])]
                          for o in result["red_lines"]]))
    else:
        out.append("none.")

    out.append("")
    out.append("## Shared anchors")
    if result["shared_anchors"]:
        out.extend(table(["Persona A", "Persona B", "Overlap", "Anchor A", "Anchor B"],
                         [[cell(s["persona_a"]), cell(s["persona_b"]),
                           "%d%%" % round(s["overlap"] * 100),
                           '"%s"' % cell(s["quote_a"]), '"%s"' % cell(s["quote_b"])]
                          for s in result["shared_anchors"]]))
        out.append("(A shared anchor is a candidate conflict or a candidate agreement; which "
                   "one it is, is yours to adjudicate.)")
    else:
        out.append("none.")

    out.append("")
    out.append("## Blind spots")
    if result["blind_spot_order"]:
        for persona in result["blind_spot_order"]:
            out.append("- %s" % persona)
            for item in result["blind_spots"][persona]:
                out.append("  - %s" % re.sub(r"\s+", " ", item).strip())
    else:
        out.append("none.")

    out.append("")
    out.append("## Criteria")
    if result["criteria"]:
        out.extend(table(["Persona", "Context", "Criterion", "Verdict", "Evidence",
                          "Evidence check"],
                         [[cell(c["persona"]), cell(c["context"]), cell(c["criterion"]),
                           cell(c["verdict"]),
                           ('"%s"' % cell(c["evidence"])) if c["evidence"].strip() else "",
                           cell(c["check"])] for c in result["criteria"]]))
        if result["document"]:
            out.append("(Verdict is the aggregate's: a met whose evidence sat only in a "
                       "heading, a table header, a field title or a metadata line reads "
                       "`declared` here and `met` in the block — the block is never edited.)")
        else:
            out.append("(Evidence check reads `unchecked` throughout: no `--document` was "
                       "given, so no quote was looked up and no verdict was forced.)")
    else:
        out.append("none.")

    out.append("")
    out.append("## Method counts")
    out.extend(table(["Persona", "Context", "Objections", "Mean severity", "Greenlight",
                      "Isolation"],
                     [[cell(c["persona"]), cell(c["context"]), str(c["objections"]),
                       "%.1f" % c["mean_severity"], cell(c["greenlight"]),
                       cell(c["isolation"])] for c in result["method_counts"]]))
    if result["control"] == "yes":
        breakdown = ", ".join("%s %d" % (c["persona"], c["objections"])
                              for c in result["control_counts"])
        out.append("control objections: %d%s"
                   % (sum(c["objections"] for c in result["control_counts"]),
                      " (%s)" % breakdown if breakdown else ""))
        out.append("role-generic proposed, unconfirmed: %s"
                   % (", ".join(result["unconfirmed"]) if result["unconfirmed"] else "none"))
        for item in result["overrides"]:
            out.append("override %s: %s (proposed) -> %s — %s"
                       % (item["key"], item["proposed"], item["confirmed"],
                          cell(item["reason"])))
    if result["criteria_declared_by_label"]:
        out.append("criteria declared by label: "
                   + ", ".join('%s ("%s")' % (d["key"], flat(d["line"]))
                               for d in result["criteria_declared_by_label"]))
    for item in result["criteria_item_counts"]:
        out.append("criteria: %s returned %d rows for %d items under ## %s"
                   % (item["persona"], item["rows"], item["items"], CRITERIA_SECTION))
    for note in result["notes"]:
        out.append(note)
    return "\n".join(out)


# --------------------------------------------------------------------------- CLI
def build_parser():
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--validate", metavar="FILE",
                   help="check one reviewer output against the schema")
    p.add_argument("--aggregate", metavar="DIR",
                   help="aggregate every reviewer output in DIR")
    p.add_argument("--roster", metavar="INDEX.md",
                   help="the context index the panel was convened from (with --aggregate)")
    p.add_argument("--controls", metavar="DIR",
                   help="the control round: one control-<slug> output per rostered persona")
    p.add_argument("--overrides", metavar="FILE",
                   help="role-generic confirmations, one per line: " + OVERRIDE_FORM)
    p.add_argument("--document", metavar="DOC",
                   help="the document under review: check every criterion's evidence "
                        "against its body and its structural lines")
    p.add_argument("--json", action="store_true", dest="as_json",
                   help="the same aggregate as one JSON object")
    return p


def usage(message):
    print("usage: %s" % message, file=sys.stderr)
    return 1


def main(argv=None):
    args = build_parser().parse_args(argv)

    if args.validate and args.aggregate:
        return usage("--validate and --aggregate are separate modes")
    if not args.validate and not args.aggregate:
        return usage("panel.py --validate FILE | --aggregate DIR --roster INDEX.md")
    if args.validate and (args.controls or args.overrides):
        return usage("--controls and --overrides belong to --aggregate: one file is "
                     "validated on its own schema, control round or not")
    if args.overrides and not args.controls:
        return usage("--overrides needs --controls: a role-generic verdict confirms a "
                     "control round's proposal, and without one the column is `%s`"
                     % ESTIMATED)

    doc, doc_name = None, None
    if args.document:
        document_path = Path(args.document)
        if not document_path.is_file():
            return usage("no such document: %s" % args.document)
        doc = split_document(read_text_lenient(document_path))
        doc_name = document_path.name

    if args.validate:
        path = Path(args.validate)
        if not path.is_file():
            return usage("no such file: %s" % args.validate)
        obj, _isolation, err = parse_block(read_text_lenient(path))
        errors = [err] if err is not None else validate(obj)
        if errors:
            for json_path, reason in errors:
                print("schema error at %s: %s" % (json_path, reason))
            return 1

        # The document check runs only once the shape is sound: a quote cannot be looked up
        # in a block whose `criteria` array is not yet an array of the right rows.
        verdicts, forced, not_found = [], [], []
        for i, item in enumerate(obj["criteria"]):
            verdict, check, line = classify_criterion(item, doc)
            verdicts.append(verdict)
            if check == "not-found":
                not_found.append("schema error at criteria[%d].evidence: not found in %s"
                                 % (i, doc_name))
            elif verdict != item["verdict"]:
                forced.append('criteria[%d]: %s — evidence sits only in a heading or '
                              'metadata line: "%s"' % (i, verdict, line))
        if not_found:
            for message in not_found:
                print(message)
            return 1
        for message in forced:
            print(message)

        summary = criteria_summary(verdicts)
        if obj["round"] >= 2:
            print("ok: %s round %d — %d fixed, %d still open, %d new, %d keep, %s"
                  % (obj["persona"], obj["round"], len(obj["fixed"]), len(obj["still_open"]),
                     len(obj["new"]), len(obj["keep"]), summary))
        else:
            print("ok: %s round 1 — %d objections, %d no-basis items, greenlight %s, %s"
                  % (obj["persona"], len(obj["objections"]), len(obj["no_basis"]),
                     obj["greenlight"], summary))
        return 0

    # --aggregate
    if not args.roster:
        return usage("--aggregate requires --roster INDEX.md")
    directory = Path(args.aggregate)
    if not directory.is_dir():
        return usage("no such directory: %s" % args.aggregate)
    roster_path = Path(args.roster)
    if not roster_path.is_file():
        return usage("no such roster index: %s" % args.roster)

    slugs, context = read_roster(roster_path)
    if not slugs:
        return usage("no persona lines in the roster index: %s" % args.roster)

    loaded, errors = load_outputs(directory, doc=doc, doc_name=doc_name)
    for path, message in errors:
        print("%s: %s" % (path.name, message))
    if errors:
        print("aggregate refused: %d unusable output(s); re-request a malformed block once, "
              "then process that persona yourself with isolation: emulated and write its block "
              "into this directory" % len({p for p, _ in errors}))
        return 1
    if not loaded:
        return usage("no reviewer outputs in %s" % args.aggregate)

    unknown = sorted({obj["persona"] for _p, obj, _i in loaded} - set(slugs))
    if unknown:
        for slug in unknown:
            print("%s is not in this roster: aggregate its context separately" % slug)
        print("aggregate refused: one roster is one context, and every row carries the context "
              "its persona was convened from")
        return 1

    duplicates = duplicate_round1(loaded)
    if duplicates:
        for path, message in duplicates:
            print("%s: %s" % (path.name, message))
        print("aggregate refused: one persona, one round-1 measurement; keep the block that "
              "stands and move the other out of this directory")
        return 1

    controls = None
    if args.controls:
        controls_dir = Path(args.controls)
        if not controls_dir.is_dir():
            return usage("no such controls directory: %s" % args.controls)
        controls, cerrors = load_outputs(controls_dir,
                                         skip=[args.overrides] if args.overrides else [])
        cerrors.extend(control_errors(controls, slugs))
        for path, message in cerrors:
            print("%s: %s" % (path.name, message))
        if cerrors:
            print("control round refused: %d unusable output(s); the role-generic column is "
                  "left `%s` rather than proposed from a control that is not the persona's"
                  % (len({p for p, _ in cerrors}), ESTIMATED))
            return 1
        if not controls:
            return usage("no control outputs in %s" % args.controls)

    overrides = {}
    if args.overrides:
        overrides_path = Path(args.overrides)
        if not overrides_path.is_file():
            return usage("no such overrides file: %s" % args.overrides)
        overrides, oerrors = read_overrides(overrides_path)
        for message in oerrors:
            print("overrides: %s" % message)
        if oerrors:
            print("aggregate refused: an override is a recorded confirmation, so a line the "
                  "aggregate cannot read is never skipped")
            return 1

    result = aggregate(loaded, slugs, context, controls, overrides, doc=doc,
                       doc_name=doc_name, roster_path=roster_path)
    if result["unknown_overrides"]:
        for key in result["unknown_overrides"]:
            print("overrides: no round-1 row %s in this round" % key)
        print("aggregate refused: an override names the row it confirms as `%s`"
              % OVERRIDE_FORM)
        return 1
    if result["degenerate_overrides"]:
        for key in result["degenerate_overrides"]:
            print("overrides: %s has no proposal to confirm: its control abstained "
                  "(0 objections, INSUFFICIENT_BASIS)" % key)
        print("aggregate refused: a row whose control abstained stays `%s`; re-run that "
              "control instead" % ESTIMATED)
        return 1
    if args.as_json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(render(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
