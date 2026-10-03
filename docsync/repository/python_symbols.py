from __future__ import annotations

import ast
from dataclasses import dataclass


@dataclass(frozen=True)
class Symbol:
    code_id: str
    path: str
    name: str
    kind: str
    source: str


def extract_symbols(path: str, source: str) -> dict[str, Symbol]:
    """Extract stable qualified Python symbols; this performs no impact inference."""
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as exc:
        raise ValueError(f"Cannot parse {path}: {exc}") from exc
    lines = source.splitlines(keepends=True)
    found: dict[str, Symbol] = {}

    def text_for(node: ast.AST) -> str:
        start = getattr(node, "lineno", 1)
        end = getattr(node, "end_lineno", start)
        return "".join(lines[start - 1 : end]).rstrip("\n")

    def add(name: str, kind: str, node: ast.AST) -> None:
        code_id = f"{path}::{name}"
        found[code_id] = Symbol(code_id, path, name, kind, text_for(node))

    def visit_body(body: list[ast.stmt], prefix: str = "") -> None:
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = f"{prefix}.{node.name}" if prefix else node.name
                kind = "class" if isinstance(node, ast.ClassDef) else "function"
                add(name, kind, node)
                if isinstance(node, ast.ClassDef):
                    visit_body(node.body, name)
            elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                names: list[str] = []
                for target in targets:
                    if isinstance(target, ast.Name):
                        names.append(target.id)
                for item in names:
                    name = f"{prefix}.{item}" if prefix else item
                    add(name, "assignment", node)

    visit_body(tree.body)
    return found

