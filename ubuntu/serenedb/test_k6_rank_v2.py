#!/usr/bin/env python3
"""K6 v2: замок lead≥12/23 и 0 регрессов v1-top3 через product entity_rank_v2.

Оффлайн: импорт и reorder на фикстурах.
Живой (SERENEDB_DSN): subprocess work/k6-rank-v2/bench.py — тот же код продукта.

Запуск: python3 ubuntu/serenedb/test_k6_rank_v2.py
"""
from __future__ import annotations

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SERENEDB = os.path.join(ROOT, "ubuntu/serenedb")
sys.path.insert(0, SERENEDB)

import entity_rank_v2 as K6  # noqa: E402

PASS, FAIL = 0, []


def t(name, cond, detail=None):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, detail if detail is not None else "")


# оффлайн: rank_key порядок live register выше catalog на sum
_feat_reg = {"prefix": "accumulationregister", "cls": "business",
             "n_dated": 100, "n_with_nums": 50, "n_cards": 0, "axis_fit": 0}
_feat_cat = {"prefix": "catalog", "cls": "business",
             "n_dated": 0, "n_with_nums": 0, "n_cards": 353, "axis_fit": 0,
             "is_kind_catalog": True}
_k_reg = K6.rank_key_v2("accumulationregister_x", _feat_reg,
                        {"want": "sum"}, "sum", 1)
_k_cat = K6.rank_key_v2("catalog_y", _feat_cat, {"want": "sum"}, "sum", 0)
t("offline: sum live register < catalog key", _k_reg < _k_cat, (_k_reg, _k_cat))

_cands = ["catalog_a", "accumulationregister_b"]
_feats = {
    "catalog_a": {"is_kind_catalog": True, "n_cards": 10, "axis_fit": 0,
                  "holds_kind_axis": False, "prefix": "catalog", "cls": ""},
    "accumulationregister_b": {"is_kind_catalog": False, "n_cards": 0,
                             "axis_fit": 2, "holds_kind_axis": True,
                             "prefix": "accumulationregister", "cls": ""},
}
cat, holder = K6.dual_atom_pair(_cands, _feats, {"want": "count", "kind": "клиенты"})
t("dual_atom: cat+holder", cat == "catalog_a" and holder == "accumulationregister_b")

# K6a offline: q_meta info register above accounting giant without q_meta
_feat_info = {"prefix": "informationregister", "cls": "business",
              "n_rows": 17, "n_dated": 17, "n_cards": 17,
              "q_meta_overlap": 1, "q_row_ratio": 800, "axis_fit": 0}
_feat_acct = {"prefix": "accountingregister", "cls": "business",
              "n_rows": 189043, "n_dated": 189043, "n_cards": 189043,
              "q_meta_overlap": 0, "q_row_ratio": 50, "axis_fit": 0}
_k_info = K6.rank_key_v2("informationregister_x", _feat_info,
                         {"want": "count"}, "count", 5)
_k_acct = K6.rank_key_v2("accountingregister_y", _feat_acct,
                         {"want": "count"}, "count", 0)
t("offline: q_meta info < acct giant", _k_info < _k_acct, (_k_info, _k_acct))

dsn = os.environ.get("SERENEDB_DSN_RO") or os.environ.get("SERENEDB_DSN")
if dsn:
    bench = os.path.join(ROOT, "work/k6-rank-v2/bench.py")
    env = os.environ.copy()
    env.setdefault("SERENEDB_DSN", dsn)
    env.setdefault("SERENEDB_DSN_RO", dsn)
    r = subprocess.run([sys.executable, bench], capture_output=True, text=True, env=env,
                       cwd=ROOT, timeout=180)
    tail = (r.stdout or "") + (r.stderr or "")
    gate_pass = "GATE: v2_lead=" in tail and "PASS" in tail.split("GATE:")[-1]
    t("bench GATE PASS (live)", r.returncode == 0 and gate_pass,
      tail[-400:] if not gate_pass else None)
else:
    print("skip- bench (no SERENEDB_DSN)")

print("----")
print("%d ok, %d FAIL" % (PASS, len(FAIL)))
if FAIL:
    print("failed:", ", ".join(FAIL))
sys.exit(1 if FAIL else 0)
