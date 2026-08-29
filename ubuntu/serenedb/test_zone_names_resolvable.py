#!/usr/bin/env python3
"""Замок: имена в телах ask/z*.py резолвятся через ask/_imports (bootstrap namespace).

Запуск: python3 ubuntu/serenedb/test_zone_names_resolvable.py

Ловит класс дефектов NameError при load_all: модульные import выше тела зоны
не попадают в exec-namespace _bootstrap; все зависимости — только в _imports.
"""
from __future__ import annotations

import ast
import re
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ASK_DIR = ROOT / "ask"
sys.path.insert(0, str(ROOT))

from ask import _bootstrap as boot  # noqa: E402

PASS, FAIL = 0, []

_ALLOWED_HEADER_IMPORT = re.compile(
    r"^\s*(from __future__ import |from ask\._imports import |from ask\._wire import )"
)

_FORBIDDEN_HEADER_IMPORT = re.compile(
    r"^\s*(import |from (?!(ask\._imports|ask\._wire|__future__)))"
)


def t(name: str, cond: bool, detail: str = "") -> None:
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, detail)


def _imports_namespace() -> dict:
    import ask._imports as imp

    ns: dict = {"__builtins__": __builtins__}
    for k, v in vars(imp).items():
        if k.startswith("_") and k not in ("__builtins__",):
            continue
        ns[k] = v
    return ns


def _zone_body_slice(path: Path) -> tuple[list[ast.stmt], int, int]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(True)
    start = boot._body_start_line(lines)
    end = boot._body_end_line(lines)
    tree = ast.parse(text, filename=str(path))
    kept = [
        n
        for n in tree.body
        if getattr(n, "lineno", 0) >= start and getattr(n, "lineno", 0) <= end
    ]
    return kept, start, end


def _assign_targets(node: ast.AST) -> list[str]:
    out: list[str] = []
    if isinstance(node, ast.Name):
        out.append(node.id)
    elif isinstance(node, (ast.Tuple, ast.List)):
        for elt in node.elts:
            out.extend(_assign_targets(elt))
    return out


def _collect_defined_names(stmts: list[ast.stmt]) -> set[str]:
    defined: set[str] = set()
    for node in stmts:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defined.add(node.name)
        elif isinstance(node, ast.Assign):
            for tgt in node.targets:
                defined.update(_assign_targets(tgt))
        elif isinstance(node, ast.AnnAssign) and node.target is not None:
            defined.update(_assign_targets(node.target))
        elif isinstance(node, ast.For) and isinstance(node.target, ast.Name):
            defined.add(node.target.id)
    return defined


def _all_zone_defined_names(zone_files: list[Path]) -> set[str]:
    names: set[str] = set()
    for path in zone_files:
        stmts, _, _ = _zone_body_slice(path)
        names |= _collect_defined_names(stmts)
    return names


def _header_lines_before_body(path: Path) -> list[tuple[int, str]]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    start = boot._body_start_line(lines)
    out: list[tuple[int, str]] = []
    for i, ln in enumerate(lines[: start - 1], 1):
        s = ln.strip()
        if not s or s.startswith('"""') or s.startswith("'''") or s.startswith("#"):
            continue
        if _ALLOWED_HEADER_IMPORT.match(ln):
            continue
        if _FORBIDDEN_HEADER_IMPORT.match(ln):
            out.append((i, ln))
    return out


def _global_refs_unresolved(body: str, filename: str, avail: set[str]) -> list[str]:
    import symtable

    try:
        table = symtable.symtable(body, filename, "exec")
    except SyntaxError as exc:
        return [f"syntax:{exc}"]

    bad: set[str] = set()

    def refs_in(st: symtable.SymbolTable) -> None:
        for name in st.get_identifiers():
            sym = st.lookup(name)
            if sym.is_referenced() and sym.is_global() and name not in avail:
                if not sym.is_assigned():
                    bad.add(name)
        for child in st.get_children():
            refs_in(child)

    refs_in(table)
    return sorted(bad)


def _exec_zone_stmts(path: Path, stmts: list[ast.stmt], ns: dict) -> None:
    mod = ast.Module(body=list(stmts), type_ignores=[])
    ast.fix_missing_locations(mod)
    code = compile(mod, str(path), "exec")
    exec(code, ns)  # noqa: S102


def _collect_file_refs(stmts: list[ast.stmt]) -> list[int]:
    """Строки тел зон, где читают __file__ (exec-namespace = serene_ask, не зона)."""
    hits: list[int] = []

    class V(ast.NodeVisitor):
        def visit_Name(self, node: ast.Name) -> None:
            if node.id == "__file__" and isinstance(node.ctx, ast.Load):
                hits.append(node.lineno)
            self.generic_visit(node)

    for node in stmts:
        V().visit(node)
    return hits


def _self_check_file_ref_red_case() -> None:
    src = "p = Path(__file__).resolve()\n"
    tree = ast.parse(src)
    hits = _collect_file_refs(tree.body)
    t("self-check red: __file__ in zone body", bool(hits), repr(hits))


def _self_check_file_ref_green_case() -> None:
    src = "p = ASK_ROOT / 'wiki_card_hybrid.sql'\n"
    tree = ast.parse(src)
    hits = _collect_file_refs(tree.body)
    t("self-check green: ASK_ROOT path (no __file__)", not hits, repr(hits))


def _self_check_red_case() -> None:
    """Синтетический header с локальным import — красный кейс для детектора."""
    header = textwrap.dedent(
        """\
        from __future__ import annotations

        from pathlib import Path

        from ask._imports import *
        from ask._wire import register_zone, apply_bindings
        """
    )
    bad = [
        ln
        for ln in header.splitlines()
        if _FORBIDDEN_HEADER_IMPORT.match(ln)
    ]
    t("self-check red: header import detected", bool(bad), repr(bad))


def main() -> int:
    zone_files = boot.zone_paths()
    t("zone file count", len(zone_files) == len(boot._ZONE_FILES))

    zones_with_header_imports = 0
    for path in zone_files:
        bad_lines = _header_lines_before_body(path)
        if bad_lines:
            zones_with_header_imports += 1
        t(
            f"no header imports {path.name}",
            not bad_lines,
            "; ".join(f"L{n}:{ln.strip()}" for n, ln in bad_lines),
        )

    t("zones with own header imports (expect 0)", zones_with_header_imports == 0)

    import ask._imports as imp

    t(
        "ASK_ROOT/wiki_card_hybrid.sql exists",
        (imp.ASK_ROOT / "wiki_card_hybrid.sql").is_file(),
        str(imp.ASK_ROOT / "wiki_card_hybrid.sql"),
    )

    for path in zone_files:
        stmts, _, _ = _zone_body_slice(path)
        file_hits = _collect_file_refs(stmts)
        t(
            f"no __file__ in body {path.name}",
            not file_hits,
            ", ".join(f"L{n}" for n in file_hits),
        )

    imp_ns = _imports_namespace()
    zone_defined = _all_zone_defined_names(zone_files)
    avail = set(imp_ns) | set(dir(__builtins__)) | zone_defined | {"__file__", "__name__"}

    for path in zone_files:
        stmts, _, _ = _zone_body_slice(path)
        body = ast.unparse(ast.Module(body=stmts, type_ignores=[]))
        unresolved = _global_refs_unresolved(body, str(path), avail)
        t(
            f"global refs in {path.name}",
            not unresolved,
            ", ".join(unresolved),
        )

    ns = _imports_namespace()
    ns["__name__"] = "serene_ask"
    for path in zone_files:
        stmts, _, _ = _zone_body_slice(path)
        ns["__file__"] = str(path)
        try:
            _exec_zone_stmts(path, stmts, ns)
            t(f"exec body {path.name}", True)
        except NameError as exc:
            t(f"exec body {path.name}", False, str(exc))

    try:
        boot.load_all({})
        t("load_all completes", True)
    except NameError as exc:
        t("load_all completes", False, str(exc))

    _self_check_file_ref_red_case()
    _self_check_file_ref_green_case()
    _self_check_red_case()

    print(f"\n{PASS} passed, {len(FAIL)} failed")
    if FAIL:
        for name in FAIL:
            print("  -", name)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
