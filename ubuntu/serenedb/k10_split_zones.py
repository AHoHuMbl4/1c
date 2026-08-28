#!/usr/bin/env python3
"""One-shot K10: split serene_ask.py into ask/z*.py by zones.json anchors.

Mechanical extraction — function bodies unchanged. Wiring via ask/_wire.py.
Run from ubuntu/serenedb: python3 k10_split_zones.py
"""
from __future__ import annotations

import ast
import json
import shutil
import textwrap
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ZONES_PATH = ROOT / "docs" / "audit" / "zones.json"
SOURCE = HERE / "serene_ask.py"
ASK_DIR = HERE / "ask"
BACKUP = HERE / "serene_ask.py.bak-k10"

IMPORT_END_MARKER = "import ask_choice_mem as ACM"
DOCSTRING_END = '"""'


def load_zone_defs() -> list[dict]:
    return json.loads(ZONES_PATH.read_text(encoding="utf-8"))


def resolve_zones(source: Path, zone_defs: list[dict]) -> list[dict]:
    import code_map as CM

    text = source.read_text(encoding="utf-8")
    n_lines = len(text.splitlines())
    tree = ast.parse(text, filename=str(source))
    return CM.resolve_zones(zone_defs, tree, n_lines)


def extract_import_block(lines: list[str]) -> list[str]:
    """Import block: stdlib + optional try/import for serene_enough, ACM, PV, axis, K6R."""
    start = next(i for i, ln in enumerate(lines) if ln.startswith("import contextvars"))
    end = next(i for i, ln in enumerate(lines) if ln.startswith("DSN = "))
    return lines[start:end]


def zone_module_name(z: dict) -> str:
    return f"z{z['id']}_{z['slug'].replace('-', '_')}"


def write_wire() -> None:
    (ASK_DIR / "_wire.py").write_text(
        textwrap.dedent(
            '''\
            """Cross-zone bindings — зоны не импортируют друг друга напрямую."""
            from __future__ import annotations

            _SKIP = frozenset({
                "__name__", "__doc__", "__package__", "__loader__",
                "__spec__", "__file__", "__cached__", "__annotations__",
            })
            _ZONES: list[tuple[str, dict]] = []


            def register_zone(module_name: str, namespace: dict) -> None:
                _ZONES.append((module_name, namespace))


            def apply_bindings(namespace: dict) -> None:
                """Inject symbols from already-loaded zones (module-level init in later zones)."""
                merged: dict = {}
                for _, g in _ZONES:
                    for k, v in g.items():
                        if k in _SKIP:
                            continue
                        merged[k] = v
                namespace.update(merged)


            def wire_all() -> dict:
                """Merge all zone namespaces; every zone sees the same symbols."""
                merged: dict = {}
                for _, g in _ZONES:
                    for k, v in g.items():
                        if k in _SKIP:
                            continue
                        merged[k] = v
                for _, g in _ZONES:
                    g.update(merged)
                return dict(merged)


            def merged_public() -> dict:
                return wire_all() if not _ZONES else {k: v for k, v in _ZONES[-1][1].items() if k not in _SKIP}
            '''
        ),
        encoding="utf-8",
    )


def write_imports(import_lines: list[str]) -> None:
    header = '"""Shared imports for ask zone modules."""\nfrom __future__ import annotations\n\n'
    (ASK_DIR / "_imports.py").write_text(header + "".join(import_lines), encoding="utf-8")


def write_bootstrap(zone_modules: list[str]) -> None:
    body = textwrap.dedent(
        '''\
        """Load zone modules in order and wire cross-zone names."""
        from __future__ import annotations

        import importlib

        _ZONE_MODULES = [
        '''
    )
    body += "".join(f"    {m!r},\n" for m in zone_modules)
    body += textwrap.dedent(
        '''\
        ]


        def unify_function_globals(canonical: dict) -> None:
            """All zone functions share serene_ask.__dict__ so tests can patch A.fn."""
            import types
            from ask._wire import _SKIP, _ZONES

            for _, g in _ZONES:
                for k, v in g.items():
                    if k not in _SKIP:
                        canonical.setdefault(k, v)
            for _, g in _ZONES:
                for v in g.values():
                    if isinstance(v, types.FunctionType):
                        v.__globals__.clear()
                        v.__globals__.update(canonical)


        def load_all() -> dict:
            from ask._wire import wire_all

            for name in _ZONE_MODULES:
                importlib.import_module(name)
            merged = wire_all()
            return merged
        '''
    )
    (ASK_DIR / "_bootstrap.py").write_text(body, encoding="utf-8")


def write_init() -> None:
    (ASK_DIR / "__init__.py").write_text(
        '"""ask package — zones of serene_ask."""\nfrom ask._bootstrap import load_all\n\n__all__ = ["load_all"]\n',
        encoding="utf-8",
    )


def write_entry(docstring: str) -> None:
    entry = (
        "#!/usr/bin/env python3\n"
        "# -*- coding: utf-8 -*-\n"
        + docstring.rstrip()
        + "\n"
        + textwrap.dedent(
            '''\
            from ask._bootstrap import load_all, unify_function_globals

            _ns = load_all()
            _g = globals()
            _g.update(_ns)
            unify_function_globals(_g)
            del _ns, load_all, unify_function_globals

            if __name__ == "__main__":
                import sys
                sys.exit(main() or 0)
            '''
        )
    )
    SOURCE.write_text(entry, encoding="utf-8")


def main() -> None:
    if not SOURCE.is_file():
        raise SystemExit(f"missing {SOURCE}")
    if BACKUP.is_file():
        print(f"backup exists: {BACKUP}")
        src_lines = BACKUP.read_text(encoding="utf-8").splitlines(keepends=True)
    else:
        shutil.copy2(SOURCE, BACKUP)
        print(f"backup -> {BACKUP}")
        src_lines = SOURCE.read_text(encoding="utf-8").splitlines(keepends=True)

    zone_defs = load_zone_defs()
    zones = resolve_zones(BACKUP if BACKUP.is_file() else SOURCE, zone_defs)

    doc_start = next(i for i, ln in enumerate(src_lines) if ln.startswith('"""'))
    doc_end = next(
        i for i, ln in enumerate(src_lines[doc_start + 1 :], doc_start + 1)
        if ln.strip() == '"""'
    )
    docstring = "".join(src_lines[doc_start : doc_end + 1])

    import_lines = extract_import_block(src_lines)

    if ASK_DIR.exists():
        shutil.rmtree(ASK_DIR)
    ASK_DIR.mkdir()

    write_wire()
    write_imports(import_lines)
    write_init()

    zone_modules: list[str] = []
    for z in zones:
        mod = zone_module_name(z)
        fq = f"ask.{mod}"
        zone_modules.append(fq)
        chunk = src_lines[z["from"] - 1 : z["to"]]
        if z["id"] == "01":
            dsn_idx = next(
                i for i, ln in enumerate(chunk) if ln.startswith("DSN = ")
            )
            chunk = chunk[dsn_idx:]

        header = f'"""Zone {z["id"]}: {z["title"]} ({z["slug"]})."""\n'
        header += "from __future__ import annotations\n\n"
        header += "from ask._imports import *\n"
        header += "from ask._wire import register_zone, apply_bindings\n\n"
        if z["id"] != "01":
            header += "apply_bindings(globals())\n\n"
        footer = f'\nregister_zone({fq!r}, globals())\n'

        path = ASK_DIR / f"{mod}.py"
        path.write_text(header + "".join(chunk) + footer, encoding="utf-8")
        n = len((header + "".join(chunk) + footer).splitlines())
        print(f"  {path.name}: {n} lines (source {z['from']}-{z['to']})")

    write_bootstrap(zone_modules)
    write_entry(docstring)
    print("done:", len(zone_modules), "zones")


if __name__ == "__main__":
    main()
