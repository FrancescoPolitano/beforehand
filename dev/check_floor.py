#!/usr/bin/env python3
"""check_floor.py — the Python 3.9 syntax floor, checked on any interpreter (FR-7.1, G1).

This machine may have no 3.9 interpreter to run the suite on (see check_all_versions.sh),
so the floor is checked statically instead, and on the parse tree rather than with a grep —
a grep missed `def f(x) -> Path | None:` and at the same time banned walrus and
`str.removeprefix`, which 3.9 has.

Scanned: skills/beforehand/scripts/*.py, dev/*.py, evals/**/*.py, beforehand_cli/*.py. Each file is
  1. parsed with `ast.parse(src, feature_version=(3, 9))` — `match`, `except*` and the other
     grammar the parser itself knows to be newer are refused here;
  2. walked for what that parse still accepts but a 3.9 interpreter would reject when it
     runs the line:
     - `X | Y` (a `BinOp(BitOr)`) inside an annotation — argument, return or `AnnAssign` —
       of a file without `from __future__ import annotations` (PEP 604 is 3.10);
     - a subscripted builtin (`list[...]`, `dict[...]`, `tuple[...]`, `set[...]`,
       `frozenset[...]`, `type[...]`), in an annotation or evaluated at runtime (the
       project's constraint: `typing` names or comments instead);
     - a parenthesised context manager, `with (a, b):` or `with (a as b):` (3.10 grammar the
       3.9 parser accepted only by accident);
     - `zip(..., strict=...)` (3.10).
Walrus (3.8) and `removeprefix`/`removesuffix` (3.9) are legal and not reported.

Usage: python3 dev/check_floor.py [ROOT]      ROOT defaults to the repository root
Prints one `<path>:<line>: <what>` per offence (paths relative to ROOT), then a status line.
Exit 0 clean, 1 any offence.
"""
import ast
import io
import sys
import tokenize
from pathlib import Path

sys.dont_write_bytecode = True

# builtin -> the typing name to use instead
BUILTINS_NOT_SUBSCRIPTABLE = {"list": "List", "dict": "Dict", "tuple": "Tuple", "set": "Set",
                              "frozenset": "FrozenSet", "type": "Type"}


def files_under(root):
    out = sorted((root / "skills" / "beforehand" / "scripts").glob("*.py"))
    out += sorted((root / "dev").glob("*.py"))
    out += sorted((root / "evals").rglob("*.py"))
    out += sorted((root / "beforehand_cli").glob("*.py"))
    return out


def has_future_annotations(tree):
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == "__future__":
            if any(a.name == "annotations" for a in node.names):
                return True
    return False


def annotations_of(tree):
    """Every annotation expression in the file: arguments, returns, AnnAssign targets."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            a = node.args
            args = list(a.posonlyargs) + list(a.args) + list(a.kwonlyargs)
            args += [x for x in (a.vararg, a.kwarg) if x is not None]
            for arg in args:
                if arg.annotation is not None:
                    yield arg.annotation
            if not isinstance(node, ast.Lambda) and node.returns is not None:
                yield node.returns
        elif isinstance(node, ast.AnnAssign):
            yield node.annotation


def pep604_in_annotations(tree):
    for ann in annotations_of(tree):
        for sub in ast.walk(ann):
            if isinstance(sub, ast.BinOp) and isinstance(sub.op, ast.BitOr):
                yield sub.lineno, "PEP 604 union `X | Y` in an annotation (3.10; use typing.Optional/Union)"


def subscripted_builtins(tree):
    for node in ast.walk(tree):
        if (isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Load)
                and isinstance(node.value, ast.Name)
                and node.value.id in BUILTINS_NOT_SUBSCRIPTABLE):
            yield node.lineno, ("subscripted builtin `%s[...]` (use typing.%s or a comment)"
                                % (node.value.id, BUILTINS_NOT_SUBSCRIPTABLE[node.value.id]))


def zip_strict(tree):
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "zip" and any(k.arg == "strict" for k in node.keywords)):
            yield node.lineno, "`zip(..., strict=...)` (3.10)"


def parenthesised_with(src):
    """`with (` whose matching `)` is followed by `:` and holds a top-level `,` or `as`.

    The parse tree cannot tell `with (a, b):` from `with a, b:`, so this reads tokens."""
    try:
        toks = [t for t in tokenize.generate_tokens(io.StringIO(src).readline)
                if t.type not in (tokenize.NL, tokenize.COMMENT, tokenize.NEWLINE,
                                  tokenize.INDENT, tokenize.DEDENT)]
    except (tokenize.TokenError, SyntaxError):
        return
    for i, tok in enumerate(toks):
        if tok.type != tokenize.NAME or tok.string != "with":
            continue
        if i + 1 >= len(toks) or toks[i + 1].string != "(":
            continue
        depth, j, multi = 0, i + 1, False
        while j < len(toks):
            s = toks[j].string
            if s in "([{" and toks[j].type == tokenize.OP:
                depth += 1
            elif s in ")]}" and toks[j].type == tokenize.OP:
                depth -= 1
                if depth == 0:
                    break
            elif depth == 1 and (s == "," or (s == "as" and toks[j].type == tokenize.NAME)):
                multi = True
            j += 1
        if multi and j + 1 < len(toks) and toks[j + 1].string == ":":
            yield tok.start[0], "parenthesised context manager `with (...):` (3.10)"


def check_file(path):
    src = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(src, filename=str(path), feature_version=(3, 9))
    except SyntaxError as e:
        return [(e.lineno or 0, "does not parse as Python 3.9: %s" % e.msg)]
    found = []
    if not has_future_annotations(tree):
        found += list(pep604_in_annotations(tree))
    found += list(subscripted_builtins(tree))
    found += list(zip_strict(tree))
    found += list(parenthesised_with(src))
    return sorted(set(found))


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    root = Path(argv[0]).resolve() if argv else Path(__file__).resolve().parent.parent
    files = files_under(root)
    bad = 0
    for path in files:
        for line, what in check_file(path):
            print("%s:%d: %s" % (path.relative_to(root).as_posix(), line, what))
            bad += 1
    if bad:
        print("syntax floor: %d offence(s) in %d file(s) scanned" % (bad, len(files)))
        return 1
    print("syntax floor: clean (%d files parsed as 3.9)" % len(files))
    return 0


if __name__ == "__main__":
    sys.exit(main())
