"""Guard: user-facing text and identifiers must come from `messages.py` / `constants.py`.

Fails when a module outside the allowed ones contains a prose-like string literal (a
string with a space, or an f-string with literal text containing a space). Docstrings are
ignored. If a literal genuinely belongs inline (e.g. an external tool's flag), mark the
line with `# literal-ok: <reason>`.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[2] / "src" / "teams_recorder"
ALLOWED_MODULES = {
    PACKAGE / "constants.py",
    PACKAGE / "messages.py",
    PACKAGE / "domain" / "status.py",  # meeting file names are the domain's state
}
MARKER = "# literal-ok"


def _docstring_ids(tree: ast.AST) -> set[int]:
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
                ids.add(id(body[0].value))
    return ids


def _is_prose(text: str) -> bool:
    return len(text.strip()) > 3 and " " in text.strip() and not text.lstrip().startswith("-")


def find_hardcoded(path: Path) -> list[tuple[int, str]]:
    source = path.read_text(encoding="utf-8")
    lines = source.splitlines()
    tree = ast.parse(source)
    docs = _docstring_ids(tree)
    fstring_parts: set[int] = set()
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            literal = "".join(v.value for v in node.values if isinstance(v, ast.Constant) and isinstance(v.value, str))
            fstring_parts.update(id(v) for v in node.values)
            if _is_prose(literal):
                hits.append((node.lineno, literal))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs and id(node) not in fstring_parts:
            if _is_prose(node.value):
                hits.append((node.lineno, node.value))
    return [(ln, text) for ln, text in sorted(hits) if MARKER not in lines[ln - 1]]


MODULES = sorted(p for p in PACKAGE.rglob("*.py") if p not in ALLOWED_MODULES)


@pytest.mark.parametrize("path", MODULES, ids=lambda p: str(p.relative_to(PACKAGE)))
def test_no_hardcoded_strings(path: Path) -> None:
    hits = find_hardcoded(path)
    assert not hits, (
        f"hardcoded text in {path.relative_to(PACKAGE)}; move it to messages.py (text) or constants.py "
        f"(identifiers), or mark the line with '{MARKER}: <reason>':\n" + "\n".join(f"  line {ln}: {text!r}" for ln, text in hits)
    )


def test_guard_detects_literals(tmp_path: Path) -> None:
    sample = tmp_path / "sample.py"
    sample.write_text('"""doc string is fine"""\nx = "plain text here"\ny = f"value {x} here"\nz = "ok"  \nw = "flag text"  # literal-ok: test\n')
    assert [ln for ln, _ in find_hardcoded(sample)] == [2, 3]
