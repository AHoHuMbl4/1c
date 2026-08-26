#!/usr/bin/env python3
"""Оффлайн-замок машинной карты serene_ask (code_map.py).

Проверяет: зоны покрывают файл без дыр и нахлёстов; каждая функция ровно
в одной зоне; JSON перечитывается и согласован с повторным разбором;
рост файла внутри зоны не требует правки zones.json; исчезнувший якорь
даёт понятную ошибку. Без сети, БД и сервисов. serene_ask.py не импортируется.
"""
from __future__ import annotations

import ast
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

import code_map as CM  # noqa: E402

PASS, FAIL = 0, []


def t(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, detail)


SOURCE = HERE / "serene_ask.py"
ZONES_PATH = ROOT / "docs" / "audit" / "zones.json"
JSON_PATH = ROOT / "docs" / "audit" / "code-map.json"
MD_PATH = ROOT / "docs" / "CODE_MAP_ASK.md"

t("source exists", SOURCE.is_file(), str(SOURCE))
t("zones.json exists", ZONES_PATH.is_file(), str(ZONES_PATH))
t("code-map.json exists", JSON_PATH.is_file(), str(JSON_PATH))
t("CODE_MAP_ASK.md exists", MD_PATH.is_file(), str(MD_PATH))

zone_defs = CM.load_zones(ZONES_PATH)
t("zones have start anchors", all("start" in z for z in zone_defs),
  [z.get("id") for z in zone_defs if "start" not in z])

src_text = SOURCE.read_text(encoding="utf-8")
n_lines = len(src_text.splitlines())
tree = ast.parse(src_text, filename=str(SOURCE))
try:
    zones = CM.resolve_zones(zone_defs, tree, n_lines)
    resolve_err = None
except CM.AnchorError as e:
    zones = []
    resolve_err = str(e)

t("anchors resolve", resolve_err is None, resolve_err)
problems = CM.check_zone_coverage(zones, n_lines) if zones else [resolve_err or "no zones"]
t("zones cover file 1..N", problems == [], problems)
t("no overlap / no gaps", problems == [], problems)

# JSON перечитывается
raw = JSON_PATH.read_text(encoding="utf-8")
try:
    stored = json.loads(raw)
    t("code-map.json parses", True)
except json.JSONDecodeError as e:
    stored = {}
    t("code-map.json parses", False, str(e))

t("stored coverage_ok", stored.get("coverage_ok") is True, stored.get("coverage_problems"))
t("stored source_lines == file", stored.get("source_lines") == n_lines,
  f"{stored.get('source_lines')} vs {n_lines}")

# повторный разбор
fresh = CM.analyze(SOURCE, zone_defs)
t("fresh coverage_ok", fresh["coverage_ok"] is True, fresh["coverage_problems"])
t("function_count stable", fresh["function_count"] == stored.get("function_count"),
  f"{fresh['function_count']} vs {stored.get('function_count')}")
t("zone count stable", len(fresh["zones"]) == len(stored.get("zones", [])),
  f"{len(fresh['zones'])} vs {len(stored.get('zones', []))}")

# каждая функция ровно в одной зоне
zone_ids = {z["id"] for z in zones}
seen = []
multi = []
none = []
for f in fresh["functions"]:
    zid = f["zone_id"]
    if zid is None:
        none.append(f["qualname"])
    elif zid not in zone_ids:
        none.append(f"{f['qualname']}→{zid}")
    else:
        hits = [z["id"] for z in zones if z["from"] <= f["lineno"] <= z["to"]]
        if len(hits) != 1:
            multi.append((f["qualname"], hits))
        seen.append(f["qualname"])

t("every function in exactly one zone", not none and not multi,
  f"none={none[:5]} multi={multi[:5]}")
t("function list non-empty", len(seen) > 0, len(seen))

# зоны в JSON = zones.json
stored_ids = [z["id"] for z in stored.get("zones", [])]
file_ids = [z["id"] for z in zone_defs]
t("zone ids match zones.json", stored_ids == file_ids, f"{stored_ids} vs {file_ids}")

# сквозные — из ≥3 зон
bad_cross = [
    c for c in fresh["cross_cutting"] if c.get("from_zones_count", 0) < 3
]
t("cross_cutting all ≥3 caller zones", not bad_cross, bad_cross[:3])

# MD не пустой и содержит якоря
md = MD_PATH.read_text(encoding="utf-8")
t("md has toc", "## Оглавление зон" in md)
t("md has cross section", "## Сквозные функции" in md)
t("md has internal section", "## Внутренние функции зоны" in md)
t("md mentions anchors", "якорям" in md or "якорь" in md)

# --- рост файла: вставка функции внутрь зоны без правки zones.json ---
anchor_start = next(z["start"] for z in zone_defs if z["id"] == "03")
insert_name = "_code_map_growth_probe_fn"
needle = f"def {anchor_start}("
idx = src_text.find(needle)
t("growth: found zone-03 start in source", idx >= 0, anchor_start)
grown_ok = False
grown_zone = None
grown_coverage = False
if idx >= 0:
    # вставить сразу ПЕРЕД якорем зоны 03 → попадает в зону 02 (между якорями)
    # и отдельно: внутрь зоны 03 — после первой строки def якоря + pass-заглушка
    # Требование: вставка ВНУТРЬ зоны. Ставим после конца функции-якоря.
    tree2 = ast.parse(src_text)
    syms = CM.module_toplevel_symbols(tree2)
    hit = syms[anchor_start][0]
    # end_lineno — последняя строка тела якоря; вставляем после неё
    lines = src_text.splitlines(keepends=True)
    insert_at = hit["end_lineno"]  # 1-based; после этой строки
    stub = (
        f"\ndef {insert_name}():\n"
        f"    \"\"\"probe: рост файла внутри зоны, zones.json не трогаем.\"\"\"\n"
        f"    return None\n"
    )
    new_lines = lines[:insert_at] + [stub] + lines[insert_at:]
    grown_text = "".join(new_lines)
    with tempfile.TemporaryDirectory() as td:
        grown_path = Path(td) / "serene_ask_grown.py"
        grown_path.write_text(grown_text, encoding="utf-8")
        # тот же zones.json — без правок
        grown = CM.analyze(grown_path, zone_defs)
        grown_coverage = grown["coverage_ok"] is True
        grown_fn = next(
            (f for f in grown["functions"] if f["name"] == insert_name), None
        )
        grown_zone = grown_fn["zone_id"] if grown_fn else None
        grown_ok = grown_fn is not None and grown_zone == "03"
        t("growth: coverage_ok without zones.json edit", grown_coverage,
          grown.get("coverage_problems"))
        t("growth: inserted fn lands in zone 03", grown_ok,
          f"zone={grown_zone} fn={grown_fn}")
        t("growth: function_count +1",
          grown["function_count"] == fresh["function_count"] + 1,
          f"{grown['function_count']} vs {fresh['function_count']}+1")
else:
    t("growth: coverage_ok without zones.json edit", False, "no insert")
    t("growth: inserted fn lands in zone 03", False, "no insert")
    t("growth: function_count +1", False, "no insert")

# --- исчезнувший якорь: понятная ошибка ---
broken = [dict(z) for z in zone_defs]
for z in broken:
    if z["id"] == "05":
        z["start"] = "_code_map_missing_anchor_xyz"
        break
try:
    CM.resolve_zones(broken, tree, n_lines)
    missing_msg = ""
    missing_raised = False
except CM.AnchorError as e:
    missing_raised = True
    missing_msg = str(e)
t("missing anchor raises AnchorError", missing_raised, missing_msg)
t("missing anchor names the anchor",
  missing_raised and "_code_map_missing_anchor_xyz" in missing_msg
  and "05" in missing_msg,
  missing_msg)

print()
print(f"PASS {PASS}  FAIL {len(FAIL)}")
if FAIL:
    print("failed:", ", ".join(FAIL))
    sys.exit(1)
sys.exit(0)
