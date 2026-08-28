#!/usr/bin/env python3
"""Машинная карта большого Python-модуля (зоны + функции + вызовы).

Только стандартная библиотека. Не ходит в сеть, БД и сервисы.
Имя исходника — аргумент; умолчание — serene_ask.py рядом с этим файлом.

Зоны задаются якорями (имена модульных функций/классов), а не номерами
строк: границы вычисляются разбором AST при каждом прогоне.
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = Path(__file__).resolve().parent / "serene_ask.py"
DEFAULT_ZONES = ROOT / "docs" / "audit" / "zones.json"
DEFAULT_JSON_OUT = ROOT / "docs" / "audit" / "code-map.json"
DEFAULT_MD_OUT = ROOT / "docs" / "CODE_MAP_ASK.md"

EXTERNAL_KINDS = ("psql", "ds_chat", "embed_one", "rerank", "urlopen")


class AnchorError(Exception):
    """Якорь зоны не найден, неоднозначен или ломает порядок."""


def _literal_default(node: ast.AST | None) -> str | None:
    if node is None:
        return None
    try:
        val = ast.literal_eval(node)
    except Exception:
        return "<expr>"
    if val is None:
        return None
    if isinstance(val, str):
        return val
    return repr(val)


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _is_os_environ(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "environ"
        and isinstance(node.value, ast.Name)
        and node.value.id == "os"
    )


def _is_os_getenv(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "getenv"
        and isinstance(node.value, ast.Name)
        and node.value.id == "os"
    )


def _is_environ_get(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "get"
        and _is_os_environ(node.value)
    )


class _FuncCollector(ast.NodeVisitor):
    """Собирает все FunctionDef/AsyncFunctionDef с qualname и телом."""

    def __init__(self) -> None:
        self.stack: list[str] = []
        self.funcs: list[dict] = []

    def _visit_fn(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        qual = ".".join(self.stack + [node.name]) if self.stack else node.name
        end = getattr(node, "end_lineno", None) or node.lineno
        self.funcs.append(
            {
                "name": node.name,
                "qualname": qual,
                "lineno": node.lineno,
                "end_lineno": end,
                "length": end - node.lineno + 1,
                "node": node,
                "nested": bool(self.stack),
            }
        )
        self.stack.append(node.name)
        for child in node.body:
            self.visit(child)
        self.stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_fn(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_fn(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.stack.append(node.name)
        for child in node.body:
            self.visit(child)
        self.stack.pop()


def module_toplevel_symbols(tree: ast.AST) -> dict[str, list[dict]]:
    """Имена модульных FunctionDef/AsyncFunctionDef/ClassDef → список вхождений."""
    out: dict[str, list[dict]] = defaultdict(list)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            end = getattr(node, "end_lineno", None) or node.lineno
            kind = (
                "class"
                if isinstance(node, ast.ClassDef)
                else "async" if isinstance(node, ast.AsyncFunctionDef) else "function"
            )
            out[node.name].append(
                {
                    "name": node.name,
                    "lineno": node.lineno,
                    "end_lineno": end,
                    "kind": kind,
                }
            )
    return out


def resolve_anchor(
    name: str,
    symbols: dict[str, list[dict]],
    zone_id: str,
    role: str,
) -> dict:
    """Находит модульный символ по имени. Понятная ошибка, если якорь пропал."""
    hits = symbols.get(name) or []
    if not hits:
        raise AnchorError(
            f"якорь {role} зоны {zone_id}: {name!r} не найден в модуле "
            f"(переименовали или удалили?)"
        )
    if len(hits) > 1:
        locs = ", ".join(str(h["lineno"]) for h in hits)
        raise AnchorError(
            f"якорь {role} зоны {zone_id}: имя {name!r} неоднозначно "
            f"(строки {locs})"
        )
    return hits[0]


def load_zones(path: Path) -> list[dict]:
    """Читает зоны. Источник границ — якоря start[/end], не номера строк.

    Опциональные поля from/to (или from_ref/to_ref) — только справочные,
    в расчёт не входят.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise SystemExit(f"zones: ожидается JSON-массив, got {type(data).__name__}")
    zones = []
    for i, z in enumerate(data):
        for key in ("id", "slug", "start", "title"):
            if key not in z:
                raise SystemExit(f"zones[{i}]: нет поля {key!r}")
        item = {
            "id": str(z["id"]),
            "slug": str(z["slug"]),
            "start": str(z["start"]),
            "title": str(z["title"]),
        }
        if z.get("end"):
            item["end"] = str(z["end"])
        # справочные номера (не источник истины)
        for src_key, dst_key in (("from_ref", "from_ref"), ("to_ref", "to_ref"),
                                  ("from", "from_ref"), ("to", "to_ref")):
            if src_key in z and dst_key not in item:
                try:
                    item[dst_key] = int(z[src_key])
                except (TypeError, ValueError):
                    pass
        zones.append(item)
    return zones


def resolve_zones(zone_defs: list[dict], tree: ast.AST, n_lines: int) -> list[dict]:
    """Якоря → сомкнутые from/to на текущем файле.

    Зона i: от строки якоря start (первая — с 1) до строки перед start
    следующей зоны (последняя — до конца файла). Новая функция между
    якорями попадает в предыдущую зону по положению.
    """
    if not zone_defs:
        raise AnchorError(f"нет зон; файл {n_lines} строк")
    symbols = module_toplevel_symbols(tree)
    starts: list[dict] = []
    ends: list[dict | None] = []
    for z in zone_defs:
        starts.append(resolve_anchor(z["start"], symbols, z["id"], "start"))
        if z.get("end"):
            ends.append(resolve_anchor(z["end"], symbols, z["id"], "end"))
        else:
            ends.append(None)

    for i in range(len(starts) - 1):
        a, b = starts[i], starts[i + 1]
        if a["lineno"] >= b["lineno"]:
            raise AnchorError(
                f"якоря зон {zone_defs[i]['id']} и {zone_defs[i + 1]['id']}: "
                f"порядок нарушен: start {zone_defs[i]['start']!r}@{a['lineno']} "
                f"идёт не раньше start {zone_defs[i + 1]['start']!r}@{b['lineno']}"
            )

    resolved: list[dict] = []
    for i, z in enumerate(zone_defs):
        fr = 1 if i == 0 else starts[i]["lineno"]
        to = n_lines if i == len(zone_defs) - 1 else starts[i + 1]["lineno"] - 1
        if fr > to:
            raise AnchorError(
                f"зона {z['id']}: вычисленные границы from={fr} > to={to}"
            )
        end_hit = ends[i]
        if end_hit is not None and not (fr <= end_hit["lineno"] <= to):
            raise AnchorError(
                f"якорь end зоны {z['id']}: {z['end']!r}@{end_hit['lineno']} "
                f"вне границ зоны {fr}–{to}"
            )
        item = {
            "id": z["id"],
            "slug": z["slug"],
            "title": z["title"],
            "start": z["start"],
            "from": fr,
            "to": to,
        }
        if z.get("end"):
            item["end"] = z["end"]
        if "from_ref" in z:
            item["from_ref"] = z["from_ref"]
        if "to_ref" in z:
            item["to_ref"] = z["to_ref"]
        resolved.append(item)
    return resolved


def check_zone_coverage(zones: list[dict], n_lines: int) -> list[str]:
    """Возвращает список проблем покрытия (пусто = ок)."""
    problems: list[str] = []
    if not zones:
        return [f"нет зон; файл {n_lines} строк"]
    if zones[0]["from"] != 1:
        problems.append(f"первая зона начинается с {zones[0]['from']}, нужна 1")
    if zones[-1]["to"] != n_lines:
        problems.append(
            f"последняя зона кончается на {zones[-1]['to']}, нужен конец файла {n_lines}"
        )
    for z in zones:
        if z["from"] > z["to"]:
            problems.append(f"зона {z['id']}: from={z['from']} > to={z['to']}")
    for a, b in zip(zones, zones[1:]):
        if a["to"] >= b["from"]:
            problems.append(
                f"нахлёст {a['id']}({a['from']}-{a['to']}) и "
                f"{b['id']}({b['from']}-{b['to']})"
            )
        elif a["to"] + 1 != b["from"]:
            problems.append(
                f"дыра {a['to'] + 1}-{b['from'] - 1} между {a['id']} и {b['id']}"
            )
    return problems


def zone_of(lineno: int, zones: list[dict]) -> dict | None:
    for z in zones:
        if z["from"] <= lineno <= z["to"]:
            return z
    return None


DEFAULT_ASK_PACKAGE = Path(__file__).resolve().parent / "ask"


def zone_module_path(zone: dict, ask_dir: Path | None = None) -> Path:
    base = ask_dir or DEFAULT_ASK_PACKAGE
    slug = str(zone["slug"]).replace("-", "_")
    return base / f"z{zone['id']}_{slug}.py"


def analyze_package(zone_defs: list[dict], ask_dir: Path | None = None) -> dict:
    """Карта пакета ask/ после K10: одна зона = один файл."""
    base = ask_dir or DEFAULT_ASK_PACKAGE
    zone_reports: list[dict] = []
    functions_out: list[dict] = []
    calls: list[dict] = []
    external_calls: list[dict] = []
    env_reads: list[dict] = []
    coverage_problems: list[str] = []
    total_lines = 0
    module_names: set[str] = set()
    by_name: dict[str, list[dict]] = defaultdict(list)
    zone_by_id: dict[str, dict] = {}

    for zdef in zone_defs:
        path = zone_module_path(zdef, base)
        if not path.is_file():
            coverage_problems.append(f"нет файла зоны {zdef['id']}: {path}")
            continue
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        n_lines = len(lines)
        total_lines += n_lines
        try:
            rel = str(path.resolve().relative_to(ROOT))
        except ValueError:
            rel = str(path)
        try:
            tree = ast.parse(text, filename=str(path))
        except SyntaxError as e:
            coverage_problems.append(f"синтаксис {rel}: {e}")
            continue
        symbols = module_toplevel_symbols(tree)
        try:
            start_hit = resolve_anchor(zdef["start"], symbols, zdef["id"], "start")
            if zdef.get("end"):
                resolve_anchor(zdef["end"], symbols, zdef["id"], "end")
        except AnchorError as e:
            coverage_problems.append(str(e))
            continue
        fr, to = 1, n_lines
        z = {
            "id": zdef["id"],
            "slug": zdef["slug"],
            "title": zdef["title"],
            "start": zdef["start"],
            "from": fr,
            "to": to,
            "file": rel,
        }
        if zdef.get("end"):
            z["end"] = zdef["end"]
        zone_by_id[z["id"]] = z

        collector = _FuncCollector()
        collector.visit(tree)
        for f in collector.funcs:
            if not f["nested"]:
                module_names.add(f["name"])
            entry = dict(f)
            entry["zone_id"] = z["id"]
            entry["file"] = rel
            by_name[f["name"]].append(entry)

        for stmt in tree.body:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            # env at module level — reuse scan from analyze via inline
            for sub in ast.walk(stmt):
                if isinstance(sub, ast.Call):
                    if _is_environ_get(sub.func) or _is_os_getenv(sub.func):
                        if sub.args:
                            try:
                                key = ast.literal_eval(sub.args[0])
                            except Exception:
                                key = None
                            if isinstance(key, str):
                                default = _literal_default(
                                    sub.args[1] if len(sub.args) > 1 else None
                                )
                                env_reads.append(
                                    {
                                        "name": key,
                                        "lineno": sub.lineno,
                                        "default": default,
                                        "in_function": None,
                                        "file": rel,
                                    }
                                )

    # second pass: function bodies + calls
    for zdef in zone_defs:
        zid = zdef["id"]
        z = zone_by_id.get(zid)
        if not z:
            continue
        path = zone_module_path(zdef, base)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        collector = _FuncCollector()
        collector.visit(tree)
        for f in collector.funcs:
            functions_out.append(
                {
                    "name": f["name"],
                    "qualname": f["qualname"],
                    "lineno": f["lineno"],
                    "end_lineno": f["end_lineno"],
                    "length": f["length"],
                    "nested": f["nested"],
                    "zone_id": zid,
                    "file": z["file"],
                }
            )
            node = f["node"]
            for sub in ast.walk(node):
                if isinstance(sub, ast.Call):
                    cname = _call_name(sub.func)
                    if cname in EXTERNAL_KINDS:
                        external_calls.append(
                            {
                                "kind": cname,
                                "lineno": sub.lineno,
                                "in_function": f["qualname"],
                                "file": z["file"],
                            }
                        )
                    if cname and cname in module_names:
                        calls.append(
                            {
                                "caller": f["qualname"],
                                "caller_zone": zid,
                                "callee": cname,
                                "lineno": sub.lineno,
                                "file": z["file"],
                            }
                        )

    # zone reports (same shape as analyze)
    zone_funcs: dict[str, list[str]] = defaultdict(list)
    fn_zone: dict[str, str] = {}
    for f in functions_out:
        if not f["nested"]:
            zone_funcs[f["zone_id"]].append(f["qualname"])
            fn_zone[f["qualname"]] = f["zone_id"]

    outgoing: dict[str, set[str]] = defaultdict(set)
    incoming: dict[str, set[str]] = defaultdict(set)
    callers_zones: dict[str, set[str]] = defaultdict(set)
    called_from_outside: dict[str, set[str]] = defaultdict(set)
    seen_edge: set[tuple] = set()
    for c in calls:
        cz, tz = c["caller_zone"], None
        for f in functions_out:
            if f["qualname"] == c["callee"] or f["name"] == c["callee"]:
                tz = f["zone_id"]
                break
        if tz is None:
            continue
        if cz == tz:
            continue
        edge = (c["caller"], c["callee"], cz, tz)
        if edge in seen_edge:
            continue
        seen_edge.add(edge)
        outgoing[cz].add(tz)
        incoming[tz].add(cz)
        callers_zones[c["callee"]].add(cz)
        called_from_outside[tz].add(c["callee"])

    cross_cutting = sorted(
        [
            {
                "qualname": q,
                "name": q.split(".")[-1],
                "lineno": next(
                    (f["lineno"] for f in functions_out if f["qualname"] == q), None
                ),
                "zone_id": fn_zone.get(q),
                "from_zones": sorted(zs),
                "from_zones_count": len(zs),
            }
            for q, zs in callers_zones.items()
            if len(zs) >= 3
        ],
        key=lambda x: (-x["from_zones_count"], x["lineno"] or 0),
    )

    fully_internal_zones = []
    for zdef in zone_defs:
        zid = zdef["id"]
        z = zone_by_id.get(zid)
        if not z:
            continue
        funcs = zone_funcs[zid]
        ext_called = sorted(called_from_outside[zid])
        internal = sorted(set(funcs) - called_from_outside[zid])
        if funcs and not ext_called:
            fully_internal_zones.append(zid)
        zone_reports.append(
            {
                "id": zid,
                "slug": z["slug"],
                "title": z["title"],
                "start": z["start"],
                "from": z["from"],
                "to": z["to"],
                "lines": z["to"] - z["from"] + 1,
                "file": z["file"],
                "functions": funcs,
                "function_count": len(funcs),
                "incoming_zones": sorted(incoming[zid]),
                "outgoing_zones": sorted(outgoing[zid]),
                "incoming_count": len(incoming[zid]),
                "outgoing_count": len(outgoing[zid]),
                "internal_functions": internal,
                "internal_count": len(internal),
                "externally_called": ext_called,
                **({"end": z["end"]} if z.get("end") else {}),
            }
        )

    return {
        "source": "ubuntu/serenedb/ask/",
        "source_lines": total_lines,
        "package": True,
        "zones_file": str(DEFAULT_ZONES.relative_to(ROOT)),
        "coverage_ok": not coverage_problems,
        "coverage_problems": coverage_problems,
        "function_count": len(functions_out),
        "functions": functions_out,
        "calls": calls,
        "env_reads": env_reads,
        "external_calls": external_calls,
        "zones": zone_reports,
        "cross_cutting": cross_cutting,
        "fully_internal_zones": fully_internal_zones,
    }


def analyze(source: Path, zone_defs: list[dict]) -> dict:
    text = source.read_text(encoding="utf-8")
    lines = text.splitlines()
    n_lines = len(lines)
    tree = ast.parse(text, filename=str(source))

    try:
        zones = resolve_zones(zone_defs, tree, n_lines)
    except AnchorError as e:
        return {
            "source": str(source),
            "source_lines": n_lines,
            "zones_file": str(DEFAULT_ZONES.relative_to(ROOT)),
            "coverage_ok": False,
            "coverage_problems": [str(e)],
            "function_count": 0,
            "functions": [],
            "calls": [],
            "env_reads": [],
            "external_calls": [],
            "zones": [],
            "cross_cutting": [],
            "fully_internal_zones": [],
            "anchor_error": str(e),
        }

    coverage = check_zone_coverage(zones, n_lines)

    collector = _FuncCollector()
    collector.visit(tree)

    # индекс: короткое имя → список функций (для резолва вызовов)
    by_name: dict[str, list[dict]] = defaultdict(list)
    for f in collector.funcs:
        by_name[f["name"]].append(f)

    # модульные имена (не вложенные) — предпочтительный резолв
    module_names = {f["name"] for f in collector.funcs if not f["nested"]}

    functions_out: list[dict] = []
    for f in collector.funcs:
        z = zone_of(f["lineno"], zones)
        functions_out.append(
            {
                "name": f["name"],
                "qualname": f["qualname"],
                "lineno": f["lineno"],
                "end_lineno": f["end_lineno"],
                "length": f["length"],
                "nested": f["nested"],
                "zone_id": z["id"] if z else None,
            }
        )

    # вызовы внутри модуля + внешние + env
    calls: list[dict] = []
    external_calls: list[dict] = []
    env_reads: list[dict] = []

    def record_env(varname: str, lineno: int, default, in_fn: str | None) -> None:
        env_reads.append(
            {
                "name": varname,
                "lineno": lineno,
                "default": default,
                "in_function": in_fn,
            }
        )

    def scan_env_and_external(node: ast.AST, in_fn: str | None) -> None:
        for sub in ast.walk(node):
            if not isinstance(sub, ast.Call):
                continue
            # os.environ.get / os.getenv
            if _is_environ_get(sub.func) or _is_os_getenv(sub.func):
                if sub.args:
                    try:
                        key = ast.literal_eval(sub.args[0])
                    except Exception:
                        key = None
                    if isinstance(key, str):
                        default = _literal_default(sub.args[1] if len(sub.args) > 1 else None)
                        if default is None and sub.keywords:
                            for kw in sub.keywords:
                                if kw.arg in ("default", None):
                                    default = _literal_default(kw.value)
                                    break
                        record_env(key, sub.lineno, default, in_fn)
            # внешние вызовы по имени
            cname = _call_name(sub.func)
            if cname in EXTERNAL_KINDS:
                external_calls.append(
                    {
                        "kind": cname,
                        "lineno": sub.lineno,
                        "in_function": in_fn,
                    }
                )

    # модульный уровень (вне функций)
    for stmt in tree.body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        scan_env_and_external(stmt, None)

    # по каждой функции: вызовы имён модуля + env/external
    for f in collector.funcs:
        node = f["node"]
        scan_env_and_external(node, f["qualname"])
        for sub in ast.walk(node):
            if not isinstance(sub, ast.Call):
                continue
            if not isinstance(sub.func, ast.Name):
                continue
            callee = sub.func.id
            if callee not in by_name:
                continue
            # резолв: предпочитаем модульную функцию с этим именем
            targets = by_name[callee]
            if callee in module_names:
                targets = [t for t in targets if not t["nested"]] or targets
            for t in targets:
                if t["qualname"] == f["qualname"]:
                    continue
                calls.append(
                    {
                        "caller": f["qualname"],
                        "caller_lineno": f["lineno"],
                        "callee": t["qualname"],
                        "callee_name": t["name"],
                        "callee_lineno": t["lineno"],
                        "at": sub.lineno,
                    }
                )

    # привязка зоны к функции
    fn_zone: dict[str, str | None] = {
        f["qualname"]: f["zone_id"] for f in functions_out
    }

    # по зонам
    zone_funcs: dict[str, list[str]] = {z["id"]: [] for z in zones}
    for f in functions_out:
        if f["zone_id"] is not None:
            zone_funcs[f["zone_id"]].append(f["qualname"])

    # входящие/исходящие межзонные вызовы
    incoming: dict[str, set[str]] = {z["id"]: set() for z in zones}
    outgoing: dict[str, set[str]] = {z["id"]: set() for z in zones}
    # кто зовёт данную функцию из каких зон
    callers_zones: dict[str, set[str]] = defaultdict(set)
    called_from_outside: dict[str, set[str]] = {z["id"]: set() for z in zones}

    seen_edge: set[tuple] = set()
    for c in calls:
        cz = fn_zone.get(c["caller"])
        tz = fn_zone.get(c["callee"])
        if not cz or not tz:
            continue
        if cz == tz:
            continue
        edge = (c["caller"], c["callee"], cz, tz)
        if edge in seen_edge:
            continue
        seen_edge.add(edge)
        outgoing[cz].add(tz)
        incoming[tz].add(cz)
        callers_zones[c["callee"]].add(cz)
        called_from_outside[tz].add(c["callee"])

    # сквозные: зовут из ≥3 зон
    cross_cutting = sorted(
        [
            {
                "qualname": q,
                "name": q.split(".")[-1],
                "lineno": next(
                    (f["lineno"] for f in functions_out if f["qualname"] == q), None
                ),
                "zone_id": fn_zone.get(q),
                "from_zones": sorted(zs),
                "from_zones_count": len(zs),
            }
            for q, zs in callers_zones.items()
            if len(zs) >= 3
        ],
        key=lambda x: (-x["from_zones_count"], x["lineno"] or 0),
    )

    zone_reports = []
    fully_internal_zones = []
    for z in zones:
        zid = z["id"]
        funcs = zone_funcs[zid]
        internal = sorted(set(funcs) - called_from_outside[zid])
        ext_called = sorted(called_from_outside[zid])
        if funcs and not ext_called:
            fully_internal_zones.append(zid)
        report = {
            "id": zid,
            "slug": z["slug"],
            "title": z["title"],
            "start": z["start"],
            "from": z["from"],
            "to": z["to"],
            "lines": z["to"] - z["from"] + 1,
            "functions": funcs,
            "function_count": len(funcs),
            "incoming_zones": sorted(incoming[zid]),
            "outgoing_zones": sorted(outgoing[zid]),
            "incoming_count": len(incoming[zid]),
            "outgoing_count": len(outgoing[zid]),
            "internal_functions": internal,
            "internal_count": len(internal),
            "externally_called": ext_called,
        }
        if z.get("end"):
            report["end"] = z["end"]
        zone_reports.append(report)

    rel_source = str(source)
    try:
        rel_source = str(source.resolve().relative_to(ROOT))
    except ValueError:
        pass

    return {
        "source": rel_source,
        "source_lines": n_lines,
        "zones_file": str(DEFAULT_ZONES.relative_to(ROOT)),
        "coverage_ok": not coverage,
        "coverage_problems": coverage,
        "function_count": len(functions_out),
        "functions": functions_out,
        "calls": calls,
        "env_reads": env_reads,
        "external_calls": external_calls,
        "zones": zone_reports,
        "cross_cutting": cross_cutting,
        "fully_internal_zones": fully_internal_zones,
    }


def render_markdown(data: dict) -> str:
    src = data["source"]
    lines: list[str] = []
    lines.append(f"# Карта `{src}`")
    lines.append("")
    lines.append(
        f"Сгенерировано `ubuntu/serenedb/code_map.py`. "
        f"Строк файла: **{data['source_lines']}**. "
        f"Функций: **{data['function_count']}**. "
        f"Зон: **{len(data['zones'])}**. "
        f"Сквозных (≥3 зон-вызывающих): **{len(data['cross_cutting'])}**."
    )
    lines.append("")
    lines.append(
        "Границы зон — по якорям (`start`[/`end`] в `docs/audit/zones.json`), "
        "номера строк вычисляются при каждом прогоне."
    )
    lines.append("")
    if data["coverage_problems"]:
        lines.append("## Покрытие зон")
        lines.append("")
        for p in data["coverage_problems"]:
            lines.append(f"- {p}")
        lines.append("")

    lines.append("## Оглавление зон")
    lines.append("")
    for z in data["zones"]:
        end_s = f" … `{z['end']}`" if z.get("end") else ""
        loc = z.get("file") or src
        lines.append(
            f"- [{z['id']} {z['slug']}]({loc}:{z['from']}) — {z['title']} "
            f"(якорь `{z['start']}`{end_s}; `{z['from']}–{z['to']}`)"
        )
    lines.append("")

    lines.append("## Таблица зон")
    lines.append("")
    lines.append(
        "| id | slug | start | строк | функций | входящих зон | исходящих зон | внутренних |"
    )
    lines.append("|---|---|---|---:|---:|---:|---:|---:|")
    for z in data["zones"]:
        lines.append(
            f"| {z['id']} | {z['slug']} | `{z['start']}` | {z['lines']} | "
            f"{z['function_count']} | {z['incoming_count']} | "
            f"{z['outgoing_count']} | {z['internal_count']} |"
        )
    lines.append("")

    for z in data["zones"]:
        lines.append(f"## {z['id']}. {z['slug']} — {z['title']}")
        lines.append("")
        end_note = f", end `{z['end']}`" if z.get("end") else ""
        loc = z.get("file") or src
        lines.append(
            f"Якорь: `{z['start']}`{end_note}. "
            f"Участок: [`{loc}:{z['from']}`]({loc}:{z['from']})–`{z['to']}`."
        )
        lines.append("")
        lines.append(
            f"Функций: {z['function_count']}. "
            f"Входящие зоны: {', '.join(z['incoming_zones']) or '—'}. "
            f"Исходящие зоны: {', '.join(z['outgoing_zones']) or '—'}."
        )
        lines.append("")
        if z["functions"]:
            lines.append("Функции:")
            lines.append("")
            # коротко: имя @ строка
            fn_by_q = {f["qualname"]: f for f in data["functions"]}
            for q in z["functions"]:
                f = fn_by_q[q]
                mark = " (влож.)" if f["nested"] else ""
                lines.append(
                    f"- [`{f['qualname']}`]({src}:{f['lineno']}) "
                    f"`{f['lineno']}–{f['end_lineno']}` len={f['length']}{mark}"
                )
            lines.append("")
        if z["externally_called"]:
            lines.append(
                "Зовут снаружи зоны: "
                + ", ".join(f"`{n}`" for n in z["externally_called"])
            )
            lines.append("")

    lines.append("## Сквозные функции")
    lines.append("")
    lines.append("Функции, которые вызывают из трёх и более других зон.")
    lines.append("")
    if not data["cross_cutting"]:
        lines.append("Нет.")
    else:
        lines.append("| функция | зона | вызывающих зон | зоны |")
        lines.append("|---|---|---:|---|")
        for c in data["cross_cutting"]:
            lines.append(
                f"| [`{c['qualname']}`]({src}:{c['lineno']}) | {c['zone_id']} | "
                f"{c['from_zones_count']} | {', '.join(c['from_zones'])} |"
            )
    lines.append("")

    lines.append("## Внутренние функции зоны")
    lines.append("")
    lines.append(
        "Функции, которые никто снаружи своей зоны не вызывает "
        "(включая ни разу не вызванные из других зон)."
    )
    lines.append("")
    fully = set(data["fully_internal_zones"])
    for z in data["zones"]:
        tag = " — зона полностью внутренняя" if z["id"] in fully else ""
        lines.append(
            f"### {z['id']} {z['slug']} "
            f"({z['internal_count']}/{z['function_count']}){tag}"
        )
        lines.append("")
        if not z["internal_functions"]:
            lines.append("—")
        else:
            for q in z["internal_functions"]:
                lines.append(f"- `{q}`")
        lines.append("")

    lines.append("## Чтение окружения")
    lines.append("")
    lines.append(f"Всего: {len(data['env_reads'])}.")
    lines.append("")
    if data["env_reads"]:
        lines.append("| переменная | строка | умолчание | функция |")
        lines.append("|---|---:|---|---|")
        for e in data["env_reads"]:
            default = e["default"]
            if default is None:
                default_s = "—"
            else:
                default_s = json.dumps(default, ensure_ascii=False)
            fn = e["in_function"] or "(модуль)"
            lines.append(
                f"| `{e['name']}` | [{e['lineno']}]({src}:{e['lineno']}) | "
                f"{default_s} | `{fn}` |"
            )
        lines.append("")

    lines.append("## Обращения наружу")
    lines.append("")
    lines.append(
        "Вызовы `psql` / `ds_chat` / `embed_one` / `rerank` / `urlopen`."
    )
    lines.append("")
    by_kind: dict[str, list] = defaultdict(list)
    for e in data["external_calls"]:
        by_kind[e["kind"]].append(e)
    for kind in EXTERNAL_KINDS:
        items = by_kind.get(kind, [])
        lines.append(f"### {kind} ({len(items)})")
        lines.append("")
        if not items:
            lines.append("—")
        else:
            for e in items:
                fn = e["in_function"] or "(модуль)"
                lines.append(f"- [`{src}:{e['lineno']}`]({src}:{e['lineno']}) в `{fn}`")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Карта Python-модуля по зонам")
    p.add_argument(
        "source",
        nargs="?",
        default=str(DEFAULT_SOURCE),
        help="путь к .py (умолч. ubuntu/serenedb/serene_ask.py)",
    )
    p.add_argument(
        "--zones",
        default=str(DEFAULT_ZONES),
        help="JSON с зонами (якоря start/end)",
    )
    p.add_argument(
        "--json-out",
        default=str(DEFAULT_JSON_OUT),
        help="машинный выход",
    )
    p.add_argument(
        "--md-out",
        default=str(DEFAULT_MD_OUT),
        help="человеческий выход",
    )
    p.add_argument(
        "--check-only",
        action="store_true",
        help="только проверить покрытие зон, ничего не писать",
    )
    args = p.parse_args(argv)

    source = Path(args.source)
    zone_defs = load_zones(Path(args.zones))
    use_package = (
        DEFAULT_ASK_PACKAGE.is_dir()
        and (source.name == "serene_ask.py" or str(source).endswith("/ask"))
    )
    if use_package:
        data = analyze_package(zone_defs)
        problems = data["coverage_problems"]
        n_lines = data["source_lines"]
        if problems:
            print("Покрытие зон НЕ сходится:", file=sys.stderr)
            for pr in problems:
                print(f"  - {pr}", file=sys.stderr)
            if args.check_only:
                return 1
        else:
            print(
                f"Покрытие пакета ask/ ок: {len(data['zones'])} зон, "
                f"строк {n_lines}, без дыр"
            )
            if args.check_only:
                return 0
        if data.get("anchor_error"):
            print(f"Якорь зоны: {data['anchor_error']}", file=sys.stderr)
            return 1
        json_path = Path(args.json_out)
        md_path = Path(args.md_out)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        md_path.write_text(render_markdown(data), encoding="utf-8")
        print(f"JSON: {json_path}")
        print(f"MD:   {md_path}")
        print(
            f"функций={data['function_count']} сквозных={len(data['cross_cutting'])} "
            f"полностью внутренних зон={len(data['fully_internal_zones'])}"
        )
        return 1 if problems else 0

    if not source.is_file():
        print(f"нет файла: {source}", file=sys.stderr)
        return 2

    zone_defs = load_zones(Path(args.zones))
    text = source.read_text(encoding="utf-8")
    n_lines = len(text.splitlines())
    try:
        tree = ast.parse(text, filename=str(source))
        zones = resolve_zones(zone_defs, tree, n_lines)
    except AnchorError as e:
        print(f"Якорь зоны: {e}", file=sys.stderr)
        return 1
    except SyntaxError as e:
        print(f"синтаксис {source}: {e}", file=sys.stderr)
        return 2

    problems = check_zone_coverage(zones, n_lines)
    if problems:
        print("Покрытие зон НЕ сходится:", file=sys.stderr)
        for pr in problems:
            print(f"  - {pr}", file=sys.stderr)
        if args.check_only:
            return 1
    else:
        print(
            f"Покрытие зон ок: {len(zones)} зон, строк 1–{n_lines}, без дыр и нахлёстов"
        )
        if args.check_only:
            return 0

    data = analyze(source, zone_defs)
    if data.get("anchor_error"):
        print(f"Якорь зоны: {data['anchor_error']}", file=sys.stderr)
        return 1

    json_path = Path(args.json_out)
    md_path = Path(args.md_out)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)

    json_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(render_markdown(data), encoding="utf-8")
    print(f"JSON: {json_path}")
    print(f"MD:   {md_path}")
    print(
        f"функций={data['function_count']} сквозных={len(data['cross_cutting'])} "
        f"полностью внутренних зон={len(data['fully_internal_zones'])}"
    )
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
