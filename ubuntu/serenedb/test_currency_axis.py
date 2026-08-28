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
cls_eq = A.fork_classes_windowed(
    rows_eq, pby_eq, "продали", want="sum", rel_by_src={"x": ["Всего"]})
out_eq, _ = A.resolve_fork_outcome(
    cls_eq, {"x": row(10, Всего=100.0)}, measure_ctx="продали",
    want="sum", rel_by_src={"x": ["Всего"]})
t("курс=1 / равные → A/unique", out_eq in ("A", "unique"), out_eq)

# ── разные + подписи → B ─────────────────────────────────────────────────────
rows_diff = {
    ("x", wfp_d): row(10, Всего=78758010.0),
    ("x", wfp_a): row(10, Всего=79133447.03),
}
pby_diff = {("x", wfp_d): p_doc, ("x", wfp_a): p_acct}
cls_diff = A.fork_classes_windowed(
    rows_diff, pby_diff, "продали", want="sum", rel_by_src={"x": ["Всего"]})
t("разные: 2 класса", len(cls_diff) == 2, len(cls_diff))


def _labs_amt(fk, srcs):
    out = {}
    for s in srcs or []:
        if s == "doc_amount":
            out[s] = "in-doc-currency"
        elif s == "accounting_amount":
            out[s] = "in-acct-currency"
    return out


_real_labs = A.fork_labels_of
A.fork_labels_of = _labs_amt
_real_cov = A.fork_labels_covering


def _cov_amt(srcs):
    m = _labs_amt("", srcs)
    return m, "fk-amt" if m else None


A.fork_labels_covering = _cov_amt
out_b, pay_b = A.resolve_fork_outcome(
    cls_diff, {"x": row(10, Всего=78758010.0)}, measure_ctx="продали",
    want="sum", rel_by_src={"x": ["Всего"]})
t("разные+подписи → B", out_b == "B", out_b)
bres = A.fork_outcome_b("q", pay_b, {}, picked_src="x")
t("B: лидер doc_amount",
  bres and A._class_amount_basis(
      {"period": (bres["atoms"][0].get("period") or {}),
       "atom": bres["atoms"][0]}) in ("", "doc_amount"),
  bres)
t("B: atoms[0] label in-doc-currency",
  bres and bres["atoms"][0].get("measure_label") == "in-doc-currency")

# ── разные без подписей → C ──────────────────────────────────────────────────
A.fork_labels_of = lambda fk, srcs: {}
A.fork_labels_covering = lambda srcs: ({}, None)
out_c, pay_c = A.resolve_fork_outcome(
    cls_diff, {"x": row(10, Всего=78758010.0)}, measure_ctx="продали",
    want="sum", rel_by_src={"x": ["Всего"]})
t("разные без подписей → C", out_c == "C" and pay_c.get("reason") == "unsigned_class",
  out_c)
cres = A.fork_outcome_c(
    "q", pay_c, cls_diff, {"x": row(10, Всего=78758010.0)}, {},
    picked_src="x")
t("C: options пуст", cres and cres.get("options") == [])

# ── EUR mismatch не отдаёт MDL молча ─────────────────────────────────────────
A.fork_labels_of = _real_labs
A.fork_labels_covering = _real_cov
_real_cref = A.currency_ref_requested
_real_cunit = A.currency_unit_for_ref
A.currency_ref_requested = lambda intent, question, trusted=None: "eur-ref"
A.currency_unit_for_ref = lambda ref: {"eur-ref": "EUR", "mdl-ref": "MDL"}.get(ref, "")
A.accounting_currency_key = lambda: "mdl-ref"
blk = A.currency_mismatch_blocks_answer({}, "сколько продали в евро", "document_x")
A.currency_ref_requested = _real_cref
A.currency_unit_for_ref = _real_cunit
t("EUR question + MDL facts → clarify", blk and blk.get("kind") == "clarify", blk)
t("clarify не figures с MDL-суммой",
  blk and "EUR" in (blk.get("text") or ""))

restore_meta(_real_meta)
A.fork_labels_of = _real_labs
A.fork_labels_covering = _real_cov
restore_flag(saved)

# ── grep: нет ISO/валютных литералов ─────────────────────────────────────────
TRIG = re.compile(r"\bMDL\b|\bEUR\b|лей|евро", re.I)
funcs = [
    A.currency_axis_readings, A.currency_axis_open, A.expand_readings_currency_axis,
    A.currency_amount_basis_prefer, A.currency_fx_probe, A.currency_sum_for_basis,
    A.currency_patch_fork_scan, A.currency_unit_for_reading,
    A.currency_ref_requested, A.currency_mismatch_blocks_answer,
    A._class_amount_basis,
]
bad = []
for fn in funcs:
    try:
        src = inspect.getsource(fn)
    except OSError:
        continue
    if TRIG.search(src):
        bad.append(fn.__name__)
t("нет ISO/валютных литералов в currency-хелперах", not bad, bad)

t("machine ids doc_amount/accounting_amount",
  A._AMOUNT_BASIS_DOC == "doc_amount"
  and A._AMOUNT_BASIS_ACCOUNTING == "accounting_amount")

print()
if FAIL:
    print("ПРОВАЛЕНО:", len(FAIL), "из", PASS + len(FAIL), FAIL)
    sys.exit(1)
print("все", PASS, "проверок зелёные")
