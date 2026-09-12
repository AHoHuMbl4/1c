#!/usr/bin/env python3
"""Оффлайн-замок amount-basis (work/currency-axis-design.md §5.1/§7).

Запуск: python3 ubuntu/serenedb/test_currency_axis.py
"""
import inspect
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ASK_TOKEN", "test")
os.environ.setdefault("EMBED_BASE_URL", "-")
os.environ.setdefault("EMBED_MODEL", "-")
os.environ.pop("ASK_CURRENCY_AXIS", None)

import serene_ask as A  # noqa: E402

PASS, FAIL = 0, []


def t(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + str(detail)[:200]) if detail else "")


def with_flag(on):
    saved = os.environ.get("ASK_CURRENCY_AXIS")
    if on:
        os.environ["ASK_CURRENCY_AXIS"] = "1"
    else:
        os.environ.pop("ASK_CURRENCY_AXIS", None)
    A.ASK_CURRENCY_AXIS = os.environ.get("ASK_CURRENCY_AXIS", "0") == "1"
    return saved


def restore_flag(saved):
    if saved is None:
        os.environ.pop("ASK_CURRENCY_AXIS", None)
    else:
        os.environ["ASK_CURRENCY_AXIS"] = saved
    A.ASK_CURRENCY_AXIS = os.environ.get("ASK_CURRENCY_AXIS", "0") == "1"


def clear_cur_cache():
    A._CURRENCY_REGS.update({"at": 0.0, "set": None})
    A._CURRENCY_ACCT.update({"at": 0.0, "val": None})
    A._CURRENCY_MAP.update({"at": 0.0, "rows": None})
    A._CURRENCY_RATE_MAP.update({"at": 0.0, "rows": None})
    A._CURRENCY_CATALOGS.update({"at": 0.0, "set": None})


def mock_meta(acct="acct-mdl", maps=None, rate_maps=None, catalogs="catalog_val"):
    clear_cur_cache()
    if maps is None:
        maps = [{
            "src": "document_x",
            "curr_col": "Curr_Key",
            "amount_col": "Amount",
            "date_col": "DocDate",
            "grain": "header",
            "grain_col": "Ref_Key",
            "rate_col": "",
            "posted_col": "",
            "deleted_col": "",
        }]
    if rate_maps is None:
        rate_maps = [{
            "reg": "informationregister_rates",
            "period_col": "Period",
            "curr_col": "Curr_Key",
            "rate_col": "Rate",
            "denom_col": "",
        }]
    A.accounting_currency_key = lambda: acct
    A.currency_map_rows = lambda: list(maps or [])
    A.currency_rate_map_rows = lambda: list(rate_maps or [])
    A.currency_rate_registers = lambda: frozenset(
        [r["reg"] for r in (rate_maps or []) if r.get("reg")])
    A.currency_catalogs = lambda: frozenset(
        x.strip() for x in str(catalogs or "").split(",") if x.strip())


def restore_meta(real):
    (A.accounting_currency_key, A.currency_map_rows, A.currency_rate_map_rows,
     A.currency_rate_registers, A.currency_catalogs) = real
    clear_cur_cache()


_real_meta = (A.accounting_currency_key, A.currency_map_rows,
              A.currency_rate_map_rows, A.currency_rate_registers,
              A.currency_catalogs)


def row(n, folders=0, **sums):
    return {"count": n, "folders": folders, "sums": sums}


base = A._window_reading(
    {"from": "2026-08-01", "to": "2026-08-31"}, "explicit", "explicit")

# ── умолчание флага ──────────────────────────────────────────────────────────
t("ASK_CURRENCY_AXIS default off", A.ASK_CURRENCY_AXIS is False)

saved = with_flag(False)
mock_meta()
t("off: currency_axis_readings пуст", A.currency_axis_readings(base) == [])
t("off: expand no-op", len(A.expand_readings_currency_axis([base])) == 1)
restore_flag(saved)
restore_meta(_real_meta)

# ── on + пустая карта ────────────────────────────────────────────────────────
saved = with_flag(True)
mock_meta(maps=[], rate_maps=[])
t("on+empty map: axis closed", A.currency_axis_open() is False)
restore_flag(saved)
restore_meta(_real_meta)

# ── FX probe mock → 2 readings ───────────────────────────────────────────────
saved = with_flag(True)
mock_meta()
A.currency_fx_probe = lambda src, preds: {
    "doc_amount": 100.0, "accounting_amount": 110.0, "n_fx": 1, "has_fx": True}
A.currency_axis_applies = lambda *a, **k: True
cals = A.currency_axis_readings(base)
t("on+fx: ровно 2 reading", len(cals) == 2, len(cals))
bases = {r.get("amount_basis") for r in cals}
t("on+fx: doc_amount + accounting_amount",
  bases == {"doc_amount", "accounting_amount"}, bases)
t("on+fx: лидер doc_amount first",
  cals[0].get("amount_basis") == "doc_amount")
restore_flag(saved)
restore_meta(_real_meta)

# ── равные ветки → A ─────────────────────────────────────────────────────────
saved = with_flag(True)
mock_meta()
p_doc = {"from": "2026-08-01", "to": "2026-08-31", "origin": "explicit",
         "interpretation_id": "explicit", "amount_basis": "doc_amount"}
p_acct = dict(p_doc, amount_basis="accounting_amount")
wfp_d = A.window_fp_of(p_doc, "explicit")
wfp_a = A.window_fp_of(p_acct, "explicit")
rows_eq = {
    ("x", wfp_d): row(10, Всего=100.0),
    ("x", wfp_a): row(10, Всего=100.0),
}
pby_eq = {("x", wfp_d): p_doc, ("x", wfp_a): p_acct}

# ── S1: fork_classes_windowed / outcomes снесены ──────────────────────────────
t("S1: fork_classes_windowed GONE", not hasattr(A, "fork_classes_windowed"))
t("S1: resolve_fork_outcome GONE", not hasattr(A, "resolve_fork_outcome"))
t("S1 slit: fork_labels_of", callable(A.fork_labels_of))
t("S1 slit: fork_labels_covering", callable(A.fork_labels_covering))

print("PASS %d FAIL %d" % (PASS, len(FAIL)))
sys.exit(1 if FAIL else 0)
