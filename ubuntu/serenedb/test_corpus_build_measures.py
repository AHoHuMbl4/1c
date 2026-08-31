#!/usr/bin/env python3
"""Оффлайн-замок: классификация мер и corpus_cell_num в corpus_build.sql.

Без LLM, сети и живой базы. Зеркало:
  - MACRO corpus_cell_num (locale-число → DOUBLE);
  - приоритет числового Edm при конфликте обёртка/recordtype;
  - is_measure (ключи, LineNumber/SurrogateKey);
  - numhint text→num при num_ratio ≥ 0.8.

Запуск: python3 ubuntu/serenedb/test_corpus_build_measures.py
"""
from __future__ import annotations

import os

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


def corpus_cell_num(val: str):
    """Зеркало corpus_build.sql: corpus_cell_num(val)."""
    if val is None:
        return None
    s = str(val).strip().replace("\u00a0", "").replace(" ", "").replace(",", ".")
    if s == "":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def pick_edm(candidates: list[tuple[str, str, bool]]) -> tuple[str, str] | None:
    """Зеркало QUALIFY tmp3_cls0: numeric Edm beats String, then own entity."""
    if not candidates:
        return None

    def rank(item: tuple[str, str, bool]) -> tuple:
        _entity, edm, own = item
        if edm in NUM_EDM:
            edm_rank = 0
        elif edm == "Edm.String":
            edm_rank = 1
        else:
            edm_rank = 2
        return (edm_rank, 0 if own else 1, _entity)

    best = min(candidates, key=rank)
    return best[0], best[1]


def kind_from_edm(edm: str | None, data_type: str = "VARCHAR") -> str:
    if edm == "Edm.Guid":
        return "ref"
    if edm == "Edm.String":
        return "text"
    if edm == "Edm.Boolean":
        return "flag"
    if edm == "Edm.DateTime":
        return "date"
    if edm in NUM_EDM:
        return "num"
    if edm is not None:
        return "skip"
    if data_type == "VARCHAR":
        return "text"
    if data_type in ("BIGINT", "INTEGER", "DOUBLE", "DECIMAL", "SMALLINT", "TINYINT"):
        return "num"
    return "skip"


def is_measure(kind: str, col: str, key_cols: list[str]) -> bool:
    return (
        kind == "num"
        and col not in key_cols
        and col not in PLATFORM_SKIP
    )


def numhint_ratio(values: list[str]) -> float:
    """Зеркало p_cls_numhint: до 200 непустых значений, доля corpus_cell_num."""
    nonempty = [v for v in values if str(v).strip() != ""][:200]
    if not nonempty:
        return 0.0
    ok = sum(1 for v in nonempty if corpus_cell_num(v) is not None)
    return ok / len(nonempty)


def nums_from_row(cols: dict[str, str], *, kind_map: dict[str, str], key_cols: list[str]):
    out = {}
    for col, val in sorted(cols.items()):
        if val == "":
            continue
        k = kind_map.get(col, "skip")
        if not is_measure(k, col, key_cols):
            continue
        n = corpus_cell_num(val)
        if n is not None:
            out[col] = n
    return out


def read_build() -> str:
    with open(BUILD, encoding="utf-8") as f:
        return f.read()


sql = read_build()
t("corpus_build.sql exists", os.path.isfile(BUILD))
t("macro corpus_cell_num declared", "CREATE OR REPLACE MACRO corpus_cell_num(val)" in sql)
t("p_doc uses corpus_cell_num in nums",
  "FILTER (is_measure AND corpus_cell_num(val) IS NOT NULL)) AS nums" in sql)
t("no bare try_cast(val AS DOUBLE) in p_doc nums",
  "try_cast(val AS DOUBLE)" not in sql.split("PREPARE p_doc AS")[1].split("PREPARE p_doc_plain")[0])

# --- corpus_cell_num values ---
t("dot decimal", corpus_cell_num("480104.42") == 480104.42)
t("comma decimal", corpus_cell_num("480104,42") == 480104.42)
t("spaced comma decimal", corpus_cell_num("171 018,11") == 171018.11)
t("empty → None", corpus_cell_num("") is None)
t("zero", corpus_cell_num("0") == 0.0)
t("zero comma", corpus_cell_num("0,00") == 0.0)
t("non-numeric → None", corpus_cell_num("abc") is None)

# --- nums map keys (generic names, not domain) ---
kind_map = {
    "AmtTotal": "num",
    "Qty": "num",
    "DeadSum": "num",
    "Note": "text",
    "LineNumber": "num",
    "Recorder": "ref",
}
key_cols = ["Recorder", "Recorder_Type", "LineNumber"]
row = {
    "AmtTotal": "480104,42",
    "Qty": "3",
    "DeadSum": "0",
    "Note": "memo",
    "LineNumber": "7",
}
nums = nums_from_row(row, kind_map=kind_map, key_cols=key_cols)
t("comma amount in nums", nums.get("AmtTotal") == 480104.42, nums)
t("qty in nums", nums.get("Qty") == 3.0, nums)
t("dead zero sum in nums", nums.get("DeadSum") == 0.0, nums)
t("text not in nums", "Note" not in nums, nums)
t("LineNumber excluded from nums", "LineNumber" not in nums, nums)
t("key col excluded from nums", "Recorder" not in nums, nums)

# --- edm conflict: wrapper String vs recordtype Decimal ---
tbl = "accumulationregister_demo"
wrap = (tbl, "Edm.String", True)
rec = (tbl + "_recordtype", "Edm.Decimal", False)
picked = pick_edm([wrap, rec])
t("wrapper String vs recordtype Decimal → Decimal",
  picked == (tbl + "_recordtype", "Edm.Decimal"), picked)
kind = kind_from_edm(picked[1])
t("picked kind is num", kind == "num", kind)
nums2 = nums_from_row(
    {"ResourceA": "171018,11"},
    kind_map={"ResourceA": kind},
    key_cols=["Recorder", "LineNumber"],
)
t("resource after edm fix in nums", nums2.get("ResourceA") == 171018.11, nums2)

# --- wrapper String only: numhint поднимает text→num ---
kind_only_wrap = kind_from_edm("Edm.String")
ratio_wrap = numhint_ratio(["171018,11", "480104,42", "0", "3,5"])
kind_after_hint = "num" if kind_only_wrap == "text" and ratio_wrap >= 0.8 else kind_only_wrap
nums_wrap = nums_from_row(
    {"ResourceB": "171018,11"},
    kind_map={"ResourceB": kind_after_hint},
    key_cols=["Recorder", "LineNumber"],
)
t("wrapper-only String + numhint → nums", nums_wrap.get("ResourceB") == 171018.11, nums_wrap)

# --- numhint: text column with numeric sample (200 непустых, не первые 200 строк) ---
samples = ["480104,42", "0", "171018,11", "3,5"]
ratio = numhint_ratio(samples)
kind_hint = "num" if ratio >= 0.8 else "text"
t("numhint ratio", ratio == 1.0, ratio)
t("numhint upgrades text→num", kind_hint == "num", kind_hint)
mixed = ["480104,42", "memo", "171018,11", "note"]
ratio_m = numhint_ratio(mixed)
t("mixed sample stays text", (ratio_m >= 0.8) is False, ratio_m)
sparse_head = [""] * 300 + ["171018,11", "480104,42"]
ratio_sparse = numhint_ratio(sparse_head)
t("sparse head: sample skips empties", ratio_sparse == 1.0, ratio_sparse)
t("SQL numhint LIMIT after nonempty filter",
  "coalesce(val, '') <> ''\n  LIMIT 200" in sql)

# --- SurrogateKey regression ---
nums3 = nums_from_row(
    {"SurrogateKey": "12345", "Qty": "2"},
    kind_map={"SurrogateKey": "num", "Qty": "num"},
    key_cols=[],
)
t("SurrogateKey out of nums", "SurrogateKey" not in nums3, nums3)
t("Qty still in nums", nums3.get("Qty") == 2.0, nums3)

# --- SQL structural: numhint block ---
t("tmp3_cls_numhint table", "CREATE OR REPLACE TABLE tmp3_cls_numhint" in sql)
t("p_cls_numhint prepare", "PREPARE p_cls_numhint AS" in sql)
t("cls final merges hint", "coalesce(h.num_ratio, 0) >= 0.8 THEN 'num'" in sql)

print("\n---", PASS, "ok,", len(FAIL), "fail ---")
if FAIL:
    print("failed:", ", ".join(FAIL))
    raise SystemExit(1)
