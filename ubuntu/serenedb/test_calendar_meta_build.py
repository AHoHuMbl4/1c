#!/usr/bin/env python3
"""Оффлайн-замок §7bis шаг 1: карта оси дат графика в corpus_build / corpus_init.

Без LLM и сети. Фикстуры tmp3_ent/tmp3_prop + строки витрины — моки.
Зеркало структурного отбора corpus_build.sql §1-кватер (не второй загрузчик).
"""
from __future__ import annotations

import os
import re
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(ROOT, "corpus_build.sql")
INIT = os.path.join(ROOT, "corpus_init.sql")

PASS, FAIL = 0, []


def t(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + str(detail)[:240]) if detail else "")


def extract_calendar_block(sql: str) -> str:
    start = sql.find("1-кватер. ОСЬ ДАТ ГРАФИКА")
    if start < 0:
        return ""
    end = sql.find("SELECT 'метаданные' AS шаг", start)
    if end < 0:
        end = len(sql)
    return sql[start:end]


NUM_EDM = {
    "Edm.Double", "Edm.Decimal", "Edm.Int16", "Edm.Int32", "Edm.Int64", "Edm.Byte",
}


def is_cal_reg(entity: str, props: list[tuple[str, str]], has_chart: bool) -> bool:
    if not entity.startswith("informationregister_"):
        return False
    if entity.endswith("_recordtype") or entity.endswith("_rowtype"):
        return False
    if not has_chart:
        return False
    has_date = any(
        edm in ("Edm.DateTime", "Edm.Date") and prop.lower() != "period"
        for prop, edm in props
    )
    has_key = any(edm == "Edm.Guid" and prop.endswith("_Key") for prop, edm in props)
    has_num = any(edm in NUM_EDM for prop, edm in props)
    return has_date and has_key and has_num


def is_cal_chart(entity: str, props: list[tuple[str, str]], has_reg: bool) -> bool:
    if not entity.startswith("chartofcharacteristictypes_"):
        return False
    if entity.endswith("_recordtype") or entity.endswith("_rowtype"):
        return False
    if not has_reg:
        return False
    names = {p.lower() for p, _ in props}
    return "ref_key" in names and "description" in names


def pick_col(props, pred, key=lambda p: p):
    cands = sorted((p for p, e in props if pred(p, e)), key=key)
    return cands[0] if cands else None


def build_calendar_meta(ents_props, vitrine):
    """Зеркало §1-кватер: ents_props={entity: [(prop,edm)]}, vitrine={table: [rowdict]}."""
    charts_any = any(
        e.startswith("chartofcharacteristictypes_")
        and not e.endswith("_recordtype")
        and not e.endswith("_rowtype")
        for e in ents_props
    )
    regs = sorted(
        e for e, props in ents_props.items()
        if is_cal_reg(e, props, charts_any)
    )
    has_reg = bool(regs)
    charts = sorted(
        e for e, props in ents_props.items()
        if is_cal_chart(e, props, has_reg)
    )

    meta = {
        "calendar_registers": ",".join(regs),
        "calendar_day_kinds": "",
        "calendar_working_day_keys": "",
    }
    cmap = []
    if not regs:
        return meta, cmap

    # map from metadata
    maps = []
    for src in regs:
        props = ents_props[src]
        date_col = pick_col(
            props,
            lambda p, e: e in ("Edm.DateTime", "Edm.Date") and p.lower() != "period",
        )
        day_key = pick_col(
            props, lambda p, e: e == "Edm.Guid" and p.endswith("_Key"),
        )
        hours = pick_col(props, lambda p, e: e in NUM_EDM)
        maps.append({
            "src_table": src,
            "date_col": date_col,
            "day_key_col": day_key,
            "hours_col": hours,
        })

    # refine day_key / chart / hours from vitrine data
    workkeys = set()
    used_charts = set()
    for m in maps:
        src = m["src_table"]
        rows = vitrine.get(src) or []
        # key hits
        key_cols = [
            p for p, e in ents_props[src]
            if e == "Edm.Guid" and p.endswith("_Key")
        ]
        best = None  # (hits, chart, key_col)
        for chart in charts:
            kind_rows = vitrine.get(chart) or []
            kind_keys = {
                str(r.get("Ref_Key")) for r in kind_rows if r.get("Ref_Key") is not None
            }
            for kc in key_cols:
                hits = sum(1 for r in rows if str(r.get(kc)) in kind_keys)
                if hits > 0 and (best is None or hits > best[0]
                                 or (hits == best[0] and (chart, kc) < best[1:])):
                    best = (hits, chart, kc)
        if best:
            m["day_key_col"] = best[2]
            m["chart"] = best[1]
            used_charts.add(best[1])
        elif charts:
            m["chart"] = charts[0]
            used_charts.add(charts[0])

        # hours: prefer col with both pos and non-pos
        num_cols = [p for p, e in ents_props[src] if e in NUM_EDM]
        hour_best = None
        for hc in sorted(num_cols):
            pos = sum(1 for r in rows if _as_float(r.get(hc)) > 0)
            zero = sum(1 for r in rows if _as_float(r.get(hc)) <= 0)
            score = (pos > 0 and zero > 0, pos, hc)
            if pos > 0 and (hour_best is None or score > hour_best[0]):
                hour_best = (score, hc)
        if hour_best:
            m["hours_col"] = hour_best[1]

        chart = m.get("chart")
        kc = m.get("day_key_col")
        hc = m.get("hours_col")
        if chart and kc and hc:
            labels = {
                str(r.get("Ref_Key")): (r.get("Description") or "")
                for r in (vitrine.get(chart) or [])
            }
            for r in rows:
                if _as_float(r.get(hc)) > 0:
                    k = r.get(kc)
                    if k is not None and str(labels.get(str(k), "")) != "":
                        workkeys.add(str(k))

        if m.get("date_col") and m.get("day_key_col") and m.get("hours_col"):
            cmap.append({
                "src_table": m["src_table"],
                "date_col": m["date_col"],
                "day_key_col": m["day_key_col"],
                "hours_col": m["hours_col"],
            })

    day_kinds = sorted(used_charts) if used_charts else charts
    meta["calendar_day_kinds"] = ",".join(day_kinds)
    meta["calendar_working_day_keys"] = ",".join(sorted(workkeys))
    return meta, cmap


def _as_float(v):
    try:
        if v is None or v == "":
            return 0.0
        return float(v)
    except (TypeError, ValueError):
        return 0.0


# --- фикстура: есть регистр + план видов ---
# Подписи видов — из данных фикстуры (не литералы конфигурации в SQL).
WK = "aaaaaaaa-bbbb-cccc-dddd-000000000001"
OFF = "aaaaaaaa-bbbb-cccc-dddd-000000000002"
LABEL_ON = "OnShift"   # «рабочая» подпись фикстуры
LABEL_OFF = "OffShift"

FIXTURE_ON = {
    "informationregister_schedule_axis": [
        ("DateCol", "Edm.DateTime"),
        ("DayKind_Key", "Edm.Guid"),
        ("Schedule_Key", "Edm.Guid"),
        ("HoursNum", "Edm.Double"),
        ("OtherNum", "Edm.Double"),
    ],
    "chartofcharacteristictypes_daykinds": [
        ("Ref_Key", "Edm.Guid"),
        ("Description", "Edm.String"),
        ("Code", "Edm.String"),
    ],
    "informationregister_rates": [  # Period — не кандидат оси
        ("Period", "Edm.DateTime"),
        ("Currency_Key", "Edm.Guid"),
        ("Rate", "Edm.Double"),
    ],
}

VITRINE_ON = {
    "informationregister_schedule_axis": [
        {"DateCol": "2026-01-05", "DayKind_Key": WK, "Schedule_Key": "s1",
         "HoursNum": 8, "OtherNum": 1},
        {"DateCol": "2026-01-06", "DayKind_Key": OFF, "Schedule_Key": "s1",
         "HoursNum": 0, "OtherNum": 1},
        {"DateCol": "2026-01-07", "DayKind_Key": WK, "Schedule_Key": "s1",
         "HoursNum": 8, "OtherNum": 2},
    ],
    "chartofcharacteristictypes_daykinds": [
        {"Ref_Key": WK, "Description": LABEL_ON, "Code": "1"},
        {"Ref_Key": OFF, "Description": LABEL_OFF, "Code": "2"},
    ],
    "informationregister_rates": [
        {"Period": "2026-01-01", "Currency_Key": "c1", "Rate": 1.0},
    ],
}

meta_on, map_on = build_calendar_meta(FIXTURE_ON, VITRINE_ON)
t("with-cal: registers filled",
  meta_on["calendar_registers"] == "informationregister_schedule_axis",
  meta_on)
t("with-cal: rates excluded (Period-only)",
  "informationregister_rates" not in meta_on["calendar_registers"], meta_on)
t("with-cal: day_kinds filled",
  meta_on["calendar_day_kinds"] == "chartofcharacteristictypes_daykinds",
  meta_on)
t("with-cal: working_day_keys = Ref_Key with on-label from data",
  meta_on["calendar_working_day_keys"] == WK, meta_on)
t("with-cal: off key not in working",
  OFF not in meta_on["calendar_working_day_keys"].split(","), meta_on)
t("with-cal: map has hours HoursNum (pos+zero)",
  map_on and map_on[0]["hours_col"] == "HoursNum", map_on)
t("with-cal: map day_key DayKind_Key (joins chart)",
  map_on and map_on[0]["day_key_col"] == "DayKind_Key", map_on)

# --- фикстура: без оси ---
FIXTURE_OFF = {
    "informationregister_rates": [
        ("Period", "Edm.DateTime"),
        ("Currency_Key", "Edm.Guid"),
        ("Rate", "Edm.Double"),
    ],
    "catalog_goods": [
        ("Ref_Key", "Edm.Guid"),
        ("Description", "Edm.String"),
    ],
}
meta_off, map_off = build_calendar_meta(FIXTURE_OFF, {})
t("no-cal: registers empty", meta_off["calendar_registers"] == "", meta_off)
t("no-cal: day_kinds empty", meta_off["calendar_day_kinds"] == "", meta_off)
t("no-cal: working keys empty", meta_off["calendar_working_day_keys"] == "", meta_off)
t("no-cal: map empty", map_off == [], map_off)
t("no-cal: no exception path", True)  # дошли сюда

# --- grep SQL блока ---
build_sql = open(BUILD, encoding="utf-8").read()
block = extract_calendar_block(build_sql)
t("sql: block present", bool(block), "missing 1-кватер")
for bad in ("Календарь", "ДниНедели", "Рабочий"):
    t(f"sql: no literal {bad!r}", bad not in block,
      f"found at {block.find(bad)}" if bad in block else "")

t("sql: writes calendar_registers", "calendar_registers" in block)
t("sql: writes calendar_day_kinds", "calendar_day_kinds" in block)
t("sql: writes calendar_working_day_keys", "calendar_working_day_keys" in block)
t("sql: structural informationregister_",
  "informationregister_%" in block or "informationregister_" in block)
t("sql: structural chartofcharacteristictypes_",
  "chartofcharacteristictypes_%" in block or "chartofcharacteristictypes_" in block)
t("sql: uses query_table / format for vitrine join",
  "query_table" in block and "format(" in block)
t("sql: hours > 0 from data", "try_cast" in block and "> 0" in block)
t("sql: Description from data (platform field)",
  "'Description'" in block or "%I" in block)

init_sql = open(INIT, encoding="utf-8").read()
t("init: CREATE search_calendar_map",
  "CREATE TABLE IF NOT EXISTS search_calendar_map" in init_sql)
t("init: GRANT serene_ro",
  "GRANT SELECT ON search_calendar_map TO serene_ro" in init_sql)
t("init: GRANT serene_resolver",
  "GRANT SELECT ON search_calendar_map TO serene_resolver" in init_sql)
t("init: precheck calendar_* triad",
  "calendar_registers" in init_sql and "NOT IN (0, 3)" in init_sql)
t("init: search_meta GRANT unchanged",
  "GRANT SELECT ON search_meta TO serene_ro" in init_sql)

# ask читает search_meta тем же путём — ключи заведены под balance_registers-стиль
import serene_ask as _A  # noqa: E402

ask = _A.ask_source()
t("ask unchanged contract: balance_registers reads search_meta",
  "SELECT v FROM search_meta WHERE k = 'balance_registers'" in ask)

print("\n%d ok, %d fail" % (PASS, len(FAIL)))
if FAIL:
    print("failed:", ", ".join(FAIL))
    sys.exit(1)
sys.exit(0)
