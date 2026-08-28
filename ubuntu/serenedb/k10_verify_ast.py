#!/usr/bin/env python3
"""K10: сравнение ast.dump тел функций до/после нарезки."""
from __future__ import annotations

import ast
import inspect
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


class FuncCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.stack: list[str] = []
        self.funcs: dict[str, str] = {}

    def _fn(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        if len(self.stack) > 1:  # не вложенные функции внутри функций
            self.generic_visit(node)
            return
        q = ".".join(self.stack + [node.name]) if self.stack else node.name
        self.funcs[q] = ast.dump(node, include_attributes=False)
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._fn(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._fn(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()


def _monolith_baseline() -> str:
    """Текст монолита до нарезки — из git-истории, не из дерева.

    [снайпер 28.08] копия .bak в дереве — устаревающий дубль: с первой же
    правкой зоны она начнёт врать и может уехать выкатом. Резерв монолита —
    история git; база верификатора — последний коммит, где serene_ask.py
    ещё был монолитом (≥ 10 000 строк).
    """
    import subprocess
    repo = str(HERE.parents[1])
    rel = "ubuntu/serenedb/serene_ask.py"
    hashes = subprocess.run(
        ["git", "-C", repo, "log", "--format=%H", "--", rel],
        capture_output=True, text=True, check=True).stdout.split()
    for h in hashes:
        text = subprocess.run(
            ["git", "-C", repo, "show", f"{h}:{rel}"],
            capture_output=True, text=True, check=True).stdout
        if len(text.splitlines()) >= 10_000:
            return text
    raise SystemExit("монолит не найден в истории (нет версии ≥ 10 000 строк)")


def main() -> int:
    bak_path = HERE / "serene_ask.py.bak-k10"
    bak_text = (bak_path.read_text(encoding="utf-8")
                if bak_path.is_file() else _monolith_baseline())
    bak_tree = ast.parse(bak_text)
    before = FuncCollector()
    before.visit(bak_tree)

    import serene_ask as A  # noqa: E402

    after: dict[str, str] = {}
    missing = []
    skipped = 0
    for q in before.funcs:
        obj: object = A
        for part in q.split("."):
            if not hasattr(obj, part):
                missing.append(q)
                break
            obj = getattr(obj, part)
        else:
            if not callable(obj) or isinstance(obj, type):
                continue
            try:
                src = inspect.getsource(obj)
                node = ast.parse(src).body[0]
            except (OSError, SyntaxError, IndentationError):
                skipped += 1
                continue
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            after[q] = ast.dump(node, include_attributes=False)

    mismatch = [q for q in before.funcs if q in after and before.funcs[q] != after[q]]
    print(f"backup функций: {len(before.funcs)}")
    print(f"сверено после: {len(after)}")
    print(f"missing: {len(missing)}")
    print(f"skipped (nested/uninspectable): {skipped}")
    print(f"mismatch: {len(mismatch)}")
    if missing:
        print("missing sample:", missing[:10])
    if mismatch:
        print("mismatch sample:", mismatch[:5])
    return 1 if missing or mismatch else 0


if __name__ == "__main__":
    raise SystemExit(main())
