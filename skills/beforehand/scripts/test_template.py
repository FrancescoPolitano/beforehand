#!/usr/bin/env python3
"""Regression test for the persona template's tag contract (SPEC-0.2 FR-2.3).

Extracts the synthetic example from assets/persona-template.md, writes it out as a
persona under a temp store (with the two source files it cites), and lints it exactly
as reindex.py would. The template is documentation a human copies — if its own worked
example does not obey the tag contract it teaches, nobody's persona will either.

Run from the scripts/ directory: python3 test_template.py
"""
import json
import os
import re
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True  # G5: a suite run on its own leaves no __pycache__

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import personas_lib as lib  # noqa: E402
import verify_quotes as vq  # noqa: E402

TEMPLATE = HERE.parent / "assets" / "persona-template.md"

template_text = TEMPLATE.read_text(encoding="utf-8")
marker = "# Synthetic example"
if marker not in template_text:
    print(f"FAIL: marker {marker!r} not found in {TEMPLATE}")
    sys.exit(1)
after_marker = template_text[template_text.index(marker):]
fence = re.search(r"```markdown\n(.*?)```", after_marker, re.S)
if not fence:
    print("FAIL: no fenced ```markdown block found after the synthetic-example marker")
    sys.exit(1)
example_body = fence.group(1)

old_home = os.environ.get("HOME")
try:
    with tempfile.TemporaryDirectory() as tmp_root_str:
        tmp_root = Path(tmp_root_str)
        persona_path = tmp_root / "persona.md"
        persona_path.write_text(example_body, encoding="utf-8")

        sources_dir = tmp_root / "work" / "borealis" / "sources"
        sources_dir.mkdir(parents=True)
        (sources_dir / "2026-05-10-kickoff-notes.txt").write_text(
            "Kickoff notes, 2026-05-10.\n\n"
            'The board reads one number from me: cost per shipment.\n'
            'Start with what happens if this fails.\n'
            'Above one hundred thousand, we pilot first, always.\n'
            'Walk me through the assumption behind that.\n',
            encoding="utf-8",
        )
        (sources_dir / "2026-06-02-email.txt").write_text(
            "Follow-up email, 2026-06-02.\n\n"
            "Your effort estimate never includes my people's hours.\n",
            encoding="utf-8",
        )

        os.environ["HOME"] = str(tmp_root)
        result = vq.lint_persona(persona_path, tmp_root)
        # The text lint_persona actually parsed, for re-slicing tags by offset below —
        # read back rather than reusing example_body so this matches byte-for-byte even
        # if decoding ever normalises anything.
        persona_text = lib.read_text_lenient(persona_path)
finally:
    if old_home is None:
        os.environ.pop("HOME", None)
    else:
        os.environ["HOME"] = old_home

checks = [
    ("status is pass or warn", result["status"] in ("pass", "warn"), result["status"]),
    ("counts.not_a_path == 0", result["counts"]["not_a_path"] == 0, result["counts"]),
    ("summary.UNPARSEABLE == 0", result["summary"]["UNPARSEABLE"] == 0, result["summary"]),
    ("summary.MISPLACED == 0", result["summary"]["MISPLACED"] == 0, result["summary"]),
]

tags = result["tags"]
checks.append(("at least one Fact tag was parsed", len(tags) > 0, len(tags)))
for t in tags:
    # t["raw"] is truncated to 160 chars by parse_tags; re-slice the tag's own inner text
    # from the full persona text via its offsets so a long tag isn't silently shortchanged.
    inner = persona_text[t["start"] + 1: t["end"] - 1].strip()
    fields = lib.split_top_level(inner)
    checks.append((
        f"tag {t['n']!r} has >= 5 top-level fields (excerpt+path+type+provenance+date)",
        len(fields) >= 5, (t["n"], fields),
    ))

https_tags = [t for t in tags if (t["ref"] or "").startswith("https://")]
checks.append(("exactly one tag references a https:// URL", len(https_tags) == 1,
               [t["ref"] for t in tags]))
if https_tags:
    https_ref = https_tags[0]["ref"]
    https_rows = [r for r in result["results"] if r["ref"] == https_ref]
    checks.append(("https:// tag row(s) are UNVERIFIABLE",
                   bool(https_rows) and all(r["status"] == "UNVERIFIABLE" for r in https_rows),
                   https_rows))
    checks.append(("https:// tag row(s) are kind == by-construction",
                   bool(https_rows) and all(r.get("kind") == "by-construction" for r in https_rows),
                   https_rows))

# E12: the plugin manifest and the router frontmatter are read at different moments (the
# plugin list, then the trigger) and must promise the same thing — the manifest line is
# SKILL.md's first sentence. Only a checkout (or a plugin install, which copies the whole
# repo) has `.claude-plugin/plugin.json` two levels above `skills/beforehand`; a copy made
# by `beforehand install`, a wheel's `_data/`, or an unpacked `.skill` archive does not, and
# there this check does not apply (test_entrypoint.py guards the same path the same way).
_manifest_path = HERE.parents[2] / ".claude-plugin" / "plugin.json"
if _manifest_path.is_file():
    _fm = re.search(r"\ndescription: >\n(.*?)\n---\n", (HERE.parent / "SKILL.md").read_text(encoding="utf-8"),
                    re.S)
    _fm_desc = " ".join(ln.strip() for ln in _fm.group(1).splitlines()) if _fm else ""
    _manifest = json.loads(_manifest_path.read_text(encoding="utf-8"))
    _sentence_m = re.match(r".+?\.(?=\s|$)", _fm_desc)
    _first_sentence = _sentence_m.group(0) if _sentence_m else ""
    checks.append(("plugin.json description equals SKILL.md's first sentence",
                   bool(_first_sentence) and _manifest.get("description") == _first_sentence,
                   (_manifest.get("description"), _first_sentence)))

fails = [c for c in checks if not c[1]]
for name, ok, got in checks:
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  -> got {got!r}"))
print(f"\n{len(checks) - len(fails)}/{len(checks)} passed")
sys.exit(1 if fails else 0)
