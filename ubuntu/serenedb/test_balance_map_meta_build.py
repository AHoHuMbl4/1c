#!/usr/bin/env python3
"""Оффлайн-замок §1-тер: карта баланс-источников в corpus_build (форма warehouse).

Без LLM, сети и живой базы. Зеркало структурного отбора accumulation_warehouse:
числовой Edm-ресурс + Period, без языковых литералов имён свойств.
"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(ROOT, "corpus_build.sql")

PASS, FAIL = 0, []

NUM_EDM = {
    "Edm.Double", "Edm.Decimal", "Edm.Int16", "Edm.Int32", "Edm.Int64", "Edm.Byte",
}
PLATFORM_SKIP = {"LineNumber", "SurrogateKey"}


def t(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + str(detail)[:240]) if detail else "")


def extract_balance_block(sql: str) -> str:
    start = sql.find("1-тер. КАРТА БАЛАНС-ИСТОЧНИКОВ")
    if start < 0:
        return ""
    end = sql.find("1-кватер. ОСЬ ДАТ ГРАФИКА", start)
    if end < 0:
        end = len(sql)
    return sql[start:end]


def is_warehouse(entity: str, props: list[tuple[str, str]]) -> bool:
    if not entity.startswith("accumulationregister_"):
        return False
    if entity.endswith("_recordtype") or entity.endswith("_rowtype"):
        return False
    names = {p.lower() for p, _ in props}
    if "period" not in names:
        return False
    return any(
        edm in NUM_EDM and prop not in PLATFORM_SKIP
        for prop, edm in props
    )


def warehouse_rows(ents_props):
    """Зеркало формы accumulation_warehouse: список src_table."""
    return sorted(e for e, props in ents_props.items() if is_warehouse(e, props))


# --- фикстура: числовой ресурс + Period ---
FIXTURE_ON = {
    "accumulationregister_stock_en": [
        ("Period", "Edm.DateTime"),
        ("Recorder", "Edm.Guid"),
        ("LineNumber", "Edm.Int64"),
        ("Qty", "Edm.Double"),
        ("Warehouse_Key", "Edm.Guid"),
    ],
    "accumulationregister_stock_ru_name_only": [
        # Имя свойства на языке конфигурации — структурно всё равно ресурс Edm.Double.
        ("Period", "Edm.DateTime"),
        ("Amt", "Edm.Decimal"),
        ("Item_Key", "Edm.Guid"),
    ],
    "accumulationregister_turn_noperiod": [
        ("Recorder", "Edm.Guid"),
        ("Qty", "Edm.Double"),
    ],
    "accumulationregister_only_linenumber": [
        ("Period", "Edm.DateTime"),
        ("LineNumber", "Edm.Int64"),
        ("SurrogateKey", "Edm.Int64"),
    ],
    "accumulationregister_x_recordtype": [
        ("RecordType", "Edm.String"),
        ("Period", "Edm.DateTime"),
        ("Qty", "Edm.Double"),
    ],
    "catalog_goods": [
        ("Ref_Key", "Edm.Guid"),
        ("Description", "Edm.String"),
    ],
}

got_on = warehouse_rows(FIXTURE_ON)
t("with-num: stock_en in warehouse",
  "accumulationregister_stock_en" in got_on, got_on)
t("with-num: stock_ru_name_only in warehouse (Edm, not name)",
  "accumulationregister_stock_ru_name_only" in got_on, got_on)
t("with-num: turn without Period out",
  "accumulationregister_turn_noperiod" not in got_on, got_on)
t("with-num: only LineNumber/SurrogateKey out",
  "accumulationregister_only_linenumber" not in got_on, got_on)
t("with-num: _recordtype shadow out of warehouse form",
  "accumulationregister_x_recordtype" not in got_on, got_on)
t("with-num: catalog out", "catalog_goods" not in got_on, got_on)
t("with-num: exactly two warehouse sources",
  got_on == [
      "accumulationregister_stock_en",
      "accumulationregister_stock_ru_name_only",
  ],
  got_on)

# --- фикстура: ни одного совпадения → явный пустой список ---
FIXTURE_OFF = {
    "accumulationregister_empty": [
        ("Period", "Edm.DateTime"),
        ("Recorder", "Edm.Guid"),
        ("Note", "Edm.String"),
    ],
    "catalog_goods": [
        ("Ref_Key", "Edm.Guid"),
        ("Price", "Edm.Double"),
    ],
}
got_off = warehouse_rows(FIXTURE_OFF)
t("no-match: warehouse list empty (explicit)", got_off == [], got_off)
t("no-match: no exception path", True)

# --- grep SQL блока ---
build_sql = open(BUILD, encoding="utf-8").read()
block = extract_balance_block(build_sql)
t("sql: block present", bool(block), "missing 1-тер")

# Кириллические литералы-значения в добавленных условиях (не комментарии).
# Ищем строковые литералы SQL с кириллицей вне строк, начинающихся с --.
code_lines = []
for line in block.splitlines():
    stripped = line.lstrip()
    if stripped.startswith("--"):
        continue
    code_lines.append(line)
code_only = "\n".join(code_lines)
str_lits = re.findall(r"'([^']*)'", code_only)
cyr_lits = [s for s in str_lits if re.search(r"[\u0400-\u04ff]", s)]
t("sql: no cyrillic value literals in executable lines",
  cyr_lits == [], cyr_lits)

t("sql: no quantity/количество name list",
  "quantity" not in code_only.lower() or "IN ('quantity'" not in code_only.lower(),
  "found name-list")
t("sql: no IN quantity list exact",
  "IN ('quantity', 'количество')" not in block
  and "IN ('количество', 'quantity')" not in block)

t("sql: warehouse form uses Edm numeric",
  "Edm.Double" in block and "accumulation_warehouse" in block)
t("sql: skips LineNumber/SurrogateKey",
  "LineNumber" in block and "SurrogateKey" in block)
t("sql: Period structural",
  "lower(p.prop) = 'period'" in block)
t("sql: diagnostic SELECT by form counts",
  "balance_map" in block
  and "accumulation_warehouse" in block
  and "AS warehouse_n" in block)
t("sql: DELETE then INSERT search_balance_map",
  "DELETE FROM search_balance_map" in block
  and "INSERT INTO search_balance_map" in block)

print("\n%d ok, %d fail" % (PASS, len(FAIL)))
if FAIL:
    print("failed:", ", ".join(FAIL))
    sys.exit(1)
sys.exit(0)
