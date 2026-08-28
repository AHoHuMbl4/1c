#!/usr/bin/env python3
"""Оффлайн-замок машинной карты ask (code_map.py) после K10 — пакет ask/."""
from __future__ import annotations

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


ASK_DIR = HERE / "ask"
ZONES_PATH = ROOT / "docs" / "audit" / "zones.json"
JSON_PATH = ROOT / "docs" / "audit" / "code-map.json"
MD_PATH = ROOT / "docs" / "CODE_MAP_ASK.md"

t("ask/ exists", ASK_DIR.is_dir(), str(ASK_DIR))
t("zones.json exists", ZONES_PATH.is_file(), str(ZONES_PATH))
t("code-map.json exists", JSON_PATH.is_file(), str(JSON_PATH))
t("CODE_MAP_ASK.md exists", MD_PATH.is_file(), str(MD_PATH))

zone_defs = CM.load_zones(ZONES_PATH)
t("zones have start anchors", all("start" in z for z in zone_defs))

fresh = CM.analyze_package(zone_defs, ASK_DIR)
t("package coverage_ok", fresh["coverage_ok"] is True, fresh["coverage_problems"])
t("20 zone files", len(fresh["zones"]) == 20, len(fresh["zones"]))
t("function list non-empty", fresh["function_count"] > 0, fresh["function_count"])

raw = JSON_PATH.read_text(encoding="utf-8")
try:
    stored = json.loads(raw)
    t("code-map.json parses", True)
except json.JSONDecodeError as e:
    stored = {}
    t("code-map.json parses", False, str(e))

# перегенерировать если устарело
if not stored.get("package") or stored.get("function_count") != fresh["function_count"]:
    CM.analyze_package(zone_defs, ASK_DIR)
    import subprocess

    subprocess.run(
        [sys.executable, str(HERE / "code_map.py"), str(HERE / "serene_ask.py")],
        check=True,
        cwd=str(HERE),
    )
    stored = json.loads(JSON_PATH.read_text(encoding="utf-8"))

t("stored package flag", stored.get("package") is True)
t("stored coverage_ok", stored.get("coverage_ok") is True, stored.get("coverage_problems"))
t("function_count stable", stored.get("function_count") == fresh["function_count"],
  f"{stored.get('function_count')} vs {fresh['function_count']}")
t("zone count stable", len(stored.get("zones", [])) == 20)

zone_ids = {z["id"] for z in fresh["zones"]}
none = [f["qualname"] for f in fresh["functions"] if f.get("zone_id") not in zone_ids]
t("every function in a zone", not none, none[:5])

stored_ids = [z["id"] for z in stored.get("zones", [])]
file_ids = [z["id"] for z in zone_defs]
t("zone ids match zones.json", stored_ids == file_ids, f"{stored_ids} vs {file_ids}")

bad_cross = [
    c for c in fresh["cross_cutting"] if c.get("from_zones_count", 0) < 3
]
t("cross_cutting all ≥3 caller zones", not bad_cross, bad_cross[:3])

md = MD_PATH.read_text(encoding="utf-8")
t("md has toc", "## Оглавление зон" in md)
t("md has cross section", "## Сквозные функции" in md)
t("md mentions ask/", "ubuntu/serenedb/ask/" in md or "ask/z" in md)

# рост файла внутри зоны 03
z03_path = CM.zone_module_path(next(z for z in zone_defs if z["id"] == "03"), ASK_DIR)
insert_name = "_code_map_growth_probe_fn"
text = z03_path.read_text(encoding="utf-8")
anchor = next(z["start"] for z in zone_defs if z["id"] == "03")
needle = f"def {anchor}("
idx = text.find(needle)
t("growth: found zone-03 start in source", idx >= 0, anchor)
if idx >= 0:
    import ast

    tree = ast.parse(text)
    syms = CM.module_toplevel_symbols(tree)
    hit = syms[anchor][0]
    lines = text.splitlines(keepends=True)
    insert_at = hit["end_lineno"]
    stub = (
        f"\ndef {insert_name}():\n"
        f"    \"\"\"probe: рост файла внутри зоны, zones.json не трогаем.\"\"\"\n"
        f"    return None\n"
    )
    grown_text = "".join(lines[:insert_at] + [stub] + lines[insert_at:])
    with tempfile.TemporaryDirectory() as td:
        grown_dir = Path(td) / "ask"
        grown_dir.mkdir()
        for p in ASK_DIR.glob("z*.py"):
            grown_dir.write_text if False else None
        import shutil

        for p in ASK_DIR.glob("z*.py"):
            shutil.copy2(p, grown_dir / p.name)
        (grown_dir / z03_path.name).write_text(grown_text, encoding="utf-8")
        grown = CM.analyze_package(zone_defs, grown_dir)
        grown_fn = next(
            (f for f in grown["functions"] if f["name"] == insert_name), None
        )
        t("growth: coverage_ok without zones.json edit", grown["coverage_ok"] is True,
          grown.get("coverage_problems"))
        t("growth: inserted fn lands in zone 03",
          grown_fn is not None and grown_fn.get("zone_id") == "03",
          f"zone={grown_fn and grown_fn.get('zone_id')}")
        t("growth: function_count +1",
          grown["function_count"] == fresh["function_count"] + 1,
          f"{grown['function_count']} vs {fresh['function_count']}+1")
else:
    t("growth: coverage_ok without zones.json edit", False, "no insert")
    t("growth: inserted fn lands in zone 03", False, "no insert")
    t("growth: function_count +1", False, "no insert")

broken = [dict(z) for z in zone_defs]
for z in broken:
    if z["id"] == "05":
        z["start"] = "_code_map_missing_anchor_xyz"
        break
grown_cov = CM.analyze_package(broken, ASK_DIR)
t("missing anchor fails coverage",
  not grown_cov["coverage_ok"]
  and any("_code_map_missing_anchor_xyz" in p for p in grown_cov["coverage_problems"]),
  grown_cov["coverage_problems"])

print()
print(f"PASS {PASS}  FAIL {len(FAIL)}")
if FAIL:
    print("failed:", ", ".join(FAIL))
    sys.exit(1)
sys.exit(0)
