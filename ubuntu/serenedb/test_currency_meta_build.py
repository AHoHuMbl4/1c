#!/usr/bin/env python3
"""Оффлайн-замок §1-quint: карта оси валют в corpus_build / corpus_init.

Без LLM и сети. Фикстуры tmp3_ent/tmp3_prop + строки витрины — моки.
Зеркало структурного отбора corpus_build.sql §1-quint (не второй загрузчик).
"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(ROOT, "corpus_build.sql")
INIT = os.path.join(ROOT, "corpus_init.sql")

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


def extract_currency_block(sql: str) -> str:
    start = sql.find("1-quint. ОСЬ ВАЛЮТ")
    if start < 0:
        return ""
    end = sql.find("SELECT 'currency_axis' AS step", start)
    if end < 0:
        end = len(sql)
    return sql[start:end]


def is_cur_cat(entity: str, props: list[tuple[str, str]]) -> bool:
    if not entity.startswith("catalog_"):
        return False
    if entity.endswith("_recordtype") or entity.endswith("_rowtype"):
        return False
    names = {p.lower() for p, _ in props}
    return {"ref_key", "code", "description"}.issubset(names)


def is_cur_rate_reg(entity: str, props: list[tuple[str, str]], has_cat: bool) -> bool:
    if not has_cat:
        return False
    if not entity.startswith("informationregister_"):
        return False
    if entity.endswith("_recordtype") or entity.endswith("_rowtype"):
        return False
    has_period = any(
        p.lower() == "period" and e in ("Edm.DateTime", "Edm.Date")
        for p, e in props
    )
    has_key = any(e == "Edm.Guid" and p.endswith("_Key") for p, e in props)
    has_num = any(e in NUM_EDM and p not in PLATFORM_SKIP for p, e in props)
    return has_period and has_key and has_num


def is_cur_fact(entity: str, props: list[tuple[str, str]], has_cat: bool) -> bool:
    if not has_cat:
        return False
    if entity.startswith("document_"):
        pass
    elif entity.startswith("accumulationregister_"):
        if entity.endswith("_recordtype") or entity.endswith("_rowtype"):
            return False
    else:
        return False
    has_key = any(e == "Edm.Guid" and p.endswith("_Key") for p, e in props)
    has_date = any(e in ("Edm.DateTime", "Edm.Date") for p, e in props)
    has_num = any(e in NUM_EDM and p not in PLATFORM_SKIP for p, e in props)
    return has_key and has_date and has_num


def pick_col(props, pred, key=lambda p: p):
    cands = sorted((p for p, e in props if pred(p, e)), key=key)
    return cands[0] if cands else None


def build_currency_meta(ents_props, vitrine, key_cols=None):
    """Зеркало §1-quint."""
    key_cols = key_cols or {}
    cats = sorted(e for e, props in ents_props.items() if is_cur_cat(e, props))
    has_cat = bool(cats)
    rate_regs = sorted(
        e for e, props in ents_props.items()
        if is_cur_rate_reg(e, props, has_cat)
    )
    facts = sorted(
        e for e, props in ents_props.items()
        if is_cur_fact(e, props, has_cat)
    )

    meta = {
        "currency_catalogs": ",".join(cats),
        "currency_rate_registers": ",".join(rate_regs),
        "accounting_currency_constant": "",
        "currency_working_keys": "",
    }
    amount_map = []
    rate_map = []
    if not has_cat:
        return meta, amount_map, rate_map

    cat = cats[0]
    cat_rows = vitrine.get(cat) or []
    cat_refs = {str(r.get("Ref_Key")) for r in cat_rows if r.get("Ref_Key")}

    for reg in rate_regs:
        props = ents_props[reg]
        period_col = pick_col(
            props, lambda p, e: p.lower() == "period" and e in ("Edm.DateTime", "Edm.Date")
        )
        key_cols_reg = [
            p for p, e in props if e == "Edm.Guid" and p.endswith("_Key")
        ]
        nums = [
            p for p, e in props if e in NUM_EDM and p not in PLATFORM_SKIP
        ]
        curr_col = None
        best_hits = -1
        rows = vitrine.get(reg) or []
        for kc in key_cols_reg:
            hits = sum(1 for r in rows if str(r.get(kc)) in cat_refs)
            if hits > best_hits or (hits == best_hits and (curr_col or "") > kc):
                best_hits = hits
                curr_col = kc
        rate_col = nums[0] if nums else None
        denom_col = nums[1] if len(nums) > 1 else ""
        if period_col and curr_col and rate_col:
            rate_map.append({
                "reg_table": reg,
                "period_col": period_col,
                "curr_col": curr_col,
                "rate_col": rate_col,
                "denom_col": denom_col or "",
            })

    workkeys = set()
    for src in facts:
        props = ents_props[src]
        key_cols_reg = [
            p for p, e in props if e == "Edm.Guid" and p.endswith("_Key")
        ]
        nums = [
            p for p, e in props if e in NUM_EDM and p not in PLATFORM_SKIP
        ]
        date_col = pick_col(
            props,
            lambda p, e: e in ("Edm.DateTime", "Edm.Date"),
            key=lambda p: (0 if p.lower() == "date" else 1, p),
        )
        curr_col = None
        best_hits = -1
        rows = vitrine.get(src) or []
        for kc in key_cols_reg:
            hits = sum(1 for r in rows if str(r.get(kc)) in cat_refs)
            if hits > best_hits or (hits == best_hits and (curr_col or "") > kc):
                best_hits = hits
                curr_col = kc
        amount_col = None
        best_amt = -1
        if curr_col:
            for nc in nums:
                hits = sum(
                    1 for r in rows
                    if r.get(curr_col) is not None and r.get(nc) is not None
                )
                if hits > best_amt or (hits == best_amt and (amount_col or "") > nc):
                    best_amt = hits
                    amount_col = nc
        rate_col = None
        for nc in nums:
            if nc != amount_col:
                rate_col = nc
                break
        grain = "header" if key_cols.get(src) == ["Ref_Key"] else "line"
        grain_col = (key_cols.get(src) or ["Ref_Key"])[0]
        posted = pick_col(props, lambda p, e: p.lower() == "posted")
        deleted = pick_col(props, lambda p, e: p.lower() == "deletionmark")
        if curr_col and amount_col and date_col:
            amount_map.append({
                "src_table": src,
                "curr_col": curr_col,
                "amount_col": amount_col,
                "date_col": date_col,
                "grain": grain,
                "grain_col": grain_col,
                "rate_col": rate_col or "",
                "posted_col": posted or "",
                "deleted_col": deleted or "",
            })
            for r in rows:
                k = r.get(curr_col)
                if k is not None:
                    workkeys.add(str(k))

    const_rows = []
    for ent, props in ents_props.items():
        if not ent.startswith("constant_"):
            continue
        guid_cols = [p for p, e in props if e == "Edm.Guid"]
        if not guid_cols:
            continue
        vc = guid_cols[0]
        for r in vitrine.get(ent) or []:
            val = r.get(vc)
            if val is not None:
                const_rows.append(str(val))
    acct = ""
    for v in const_rows:
        if v in cat_refs:
            acct = v
            break
    if not acct and const_rows:
        acct = const_rows[0]
    meta["accounting_currency_constant"] = acct
    meta["currency_working_keys"] = ",".join(sorted(workkeys))
    return meta, amount_map, rate_map


# --- фикстура: полная ось ---
MDL = "11111111-1111-1111-1111-111111111111"
EUR = "22222222-2222-2222-2222-222222222222"

FIXTURE_ON = {
    "catalog_currencies": [
        ("Ref_Key", "Edm.Guid"),
        ("Code", "Edm.String"),
        ("Description", "Edm.String"),
    ],
    "informationregister_rates": [
        ("Period", "Edm.DateTime"),
        ("Currency_Key", "Edm.Guid"),
        ("Rate", "Edm.Double"),
        ("Multiplier", "Edm.Int32"),
    ],
    "constant_accounting_currency": [
        ("Value", "Edm.Guid"),
    ],
    "document_sales": [
        ("Ref_Key", "Edm.Guid"),
        ("Date", "Edm.DateTime"),
        ("Currency_Key", "Edm.Guid"),
        ("Rate", "Edm.Double"),
        ("Amount", "Edm.Double"),
        ("Posted", "Edm.Boolean"),
        ("DeletionMark", "Edm.Boolean"),
    ],
    "informationregister_schedule_axis": [
        ("DateCol", "Edm.DateTime"),
        ("DayKind_Key", "Edm.Guid"),
        ("HoursNum", "Edm.Double"),
    ],
}

VITRINE_ON = {
    "catalog_currencies": [
        {"Ref_Key": MDL, "Code": "498", "Description": "National"},
        {"Ref_Key": EUR, "Code": "978", "Description": "Euro"},
    ],
    "informationregister_rates": [
        {"Period": "2026-08-01", "Currency_Key": EUR, "Rate": 19.5, "Multiplier": 1},
        {"Period": "2026-08-02", "Currency_Key": MDL, "Rate": 1.0, "Multiplier": 1},
    ],
    "constant_accounting_currency": [
        {"Value": MDL},
    ],
    "document_sales": [
        {"Ref_Key": "d1", "Date": "2026-08-05", "Currency_Key": MDL,
         "Rate": 1.0, "Amount": 100.0, "Posted": True, "DeletionMark": False},
        {"Ref_Key": "d2", "Date": "2026-08-06", "Currency_Key": EUR,
         "Rate": 19.5, "Amount": 10.0, "Posted": True, "DeletionMark": False},
    ],
}

meta_on, map_on, rate_on = build_currency_meta(
    FIXTURE_ON, VITRINE_ON, key_cols={"document_sales": ["Ref_Key"]})
t("with-cur: catalogs filled",
  meta_on["currency_catalogs"] == "catalog_currencies", meta_on)
t("with-cur: rate register filled",
  meta_on["currency_rate_registers"] == "informationregister_rates", meta_on)
t("with-cur: schedule register excluded",
  "informationregister_schedule_axis" not in meta_on["currency_rate_registers"],
  meta_on)
t("with-cur: accounting constant = catalog Ref",
  meta_on["accounting_currency_constant"] == MDL, meta_on)
t("with-cur: working keys from facts",
  set(meta_on["currency_working_keys"].split(",")) == {MDL, EUR}, meta_on)
t("with-cur: amount map row",
  len(map_on) == 1 and map_on[0]["src_table"] == "document_sales", map_on)
t("with-cur: curr_col from join",
  map_on and map_on[0]["curr_col"] == "Currency_Key", map_on)
t("with-cur: amount_col Amount",
  map_on and map_on[0]["amount_col"] == "Amount", map_on)
t("with-cur: grain header",
  map_on and map_on[0]["grain"] == "header", map_on)
t("with-cur: rate map cols",
  rate_on and rate_on[0]["period_col"] == "Period"
  and rate_on[0]["curr_col"] == "Currency_Key"
  and rate_on[0]["rate_col"] == "Rate", rate_on)

# --- фикстура: без оси ---
FIXTURE_OFF = {
    "catalog_goods": [
        ("Ref_Key", "Edm.Guid"),
        ("Description", "Edm.String"),
    ],
    "document_note": [
        ("Ref_Key", "Edm.Guid"),
        ("Date", "Edm.DateTime"),
        ("Note", "Edm.String"),
    ],
}
meta_off, map_off, rate_off = build_currency_meta(FIXTURE_OFF, {})
t("no-cur: catalogs empty", meta_off["currency_catalogs"] == "", meta_off)
t("no-cur: rate regs empty", meta_off["currency_rate_registers"] == "", meta_off)
t("no-cur: acct empty", meta_off["accounting_currency_constant"] == "", meta_off)
t("no-cur: working keys empty", meta_off["currency_working_keys"] == "", meta_off)
t("no-cur: amount map empty", map_off == [], map_off)
t("no-cur: rate map empty", rate_off == [], rate_off)
t("no-cur: no exception path", True)

# --- grep SQL блока ---
build_sql = open(BUILD, encoding="utf-8").read()
block = extract_currency_block(build_sql)
t("sql: block present", bool(block), "missing 1-quint")
for bad in ("EUR", "MDL", "Валюта", "Курс", "лей"):
    t(f"sql: no literal {bad!r}", bad not in block,
      f"found at {block.find(bad)}" if bad in block else "")

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

t("sql: writes currency_catalogs", "currency_catalogs" in block)
t("sql: writes currency_rate_registers", "currency_rate_registers" in block)
t("sql: writes accounting_currency_constant", "accounting_currency_constant" in block)
t("sql: writes currency_working_keys", "currency_working_keys" in block)
t("sql: search_currency_map", "DELETE FROM search_currency_map" in block)
t("sql: search_currency_rate_map", "DELETE FROM search_currency_rate_map" in block)
t("sql: structural catalog_", "catalog_%" in block or "catalog_" in block)
t("sql: uses query_table / format for vitrine join",
  "query_table" in block and "format(" in block)
t("sql: format template uses || (no implicit literal concat)",
  "|| 'FROM query_table" in block and "|| 'INNER JOIN query_table" in block)
t("sql: amthits src_real from tmp3_cur_live join",
  "tmp3_cur_live WHERE src_real IS NOT NULL" in block)
t("sql: platform Posted/DeletionMark",
  "posted" in code_only.lower() and "deletionmark" in code_only.lower())

init_sql = open(INIT, encoding="utf-8").read()
t("init: CREATE search_currency_map",
  "CREATE TABLE IF NOT EXISTS search_currency_map" in init_sql)
t("init: CREATE search_currency_rate_map",
  "CREATE TABLE IF NOT EXISTS search_currency_rate_map" in init_sql)
t("init: GRANT serene_ro currency_map",
  "GRANT SELECT ON search_currency_map TO serene_ro" in init_sql)
t("init: precheck currency_* quad",
  "currency_catalogs" in init_sql and "NOT IN (0, 4)" in init_sql)

# z04b читает те же ключи/таблицы
import serene_ask as _A  # noqa: E402

ask = _A.ask_source()
t("ask contract: currency_catalogs meta",
  "k = 'currency_catalogs'" in ask)
t("ask contract: search_currency_map table",
  "FROM search_currency_map" in ask)
t("ask contract: search_currency_rate_map table",
  "FROM search_currency_rate_map" in ask)

print("\n%d ok, %d fail" % (PASS, len(FAIL)))
if FAIL:
    print("failed:", ", ".join(FAIL))
    sys.exit(1)
sys.exit(0)
