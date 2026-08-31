#!/usr/bin/env python3
"""Оффлайн-замок: resolver MERGE сохраняет emb (не REPLACE).

Семантика resolver_build.sql:
  ключ = (tbl, col, clip≤20000); MATCHED не трогает emb;
  смена формы full→clip — карта xfer; повторный прогон — no-op.

Порог 20000 — тот же, что в resolver_build.sql (длина ключа), не отсечка
правильности. Запуск: python3 test_resolver_merge_emb.py
"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
SQL = os.path.join(ROOT, "resolver_build.sql")
PASS, FAIL = 0, []

_sql_txt = open(SQL, encoding="utf-8").read()
_m = re.search(r"substr\(val,\s*1,\s*(\d+)\)", _sql_txt)
CLIP_N = int(_m.group(1)) if _m else 0


def t(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + detail)[:200] if detail else "")


t("SQL declares clip length", CLIP_N > 0, str(CLIP_N))


def clip(v):
    return v[:CLIP_N]


def build_xfer(stored, src_keys):
    """stored: (tbl,col,value)->emb; src_keys: set of clip-keys from incoming."""
    xfer = {}
    for (tbl, col, val), emb in stored.items():
        if emb is None or val == clip(val):
            continue
        key = (tbl, col, clip(val))
        if key not in src_keys:
            continue
        olds = [
            1
            for (t2, c2, v2), e2 in stored.items()
            if t2 == tbl and c2 == col and clip(v2) == key[2] and e2 is not None
        ]
        if len(olds) == 1:
            xfer[key] = emb
    return xfer


def merge_pass(stored, incoming_raw, seen_ok):
    """Один такт. incoming_raw values — сырые; ключ = clip.
    Возвращает (store, n_null, n_xfer)."""
    src = {(tbl, col, clip(val)) for (tbl, col, val) in incoming_raw}
    xfer = build_xfer(stored, src)

    out = {}
    for key in src:
        if key in stored:
            out[key] = stored[key]
        elif key in xfer:
            out[key] = xfer[key]
        else:
            out[key] = None

    for key, emb in stored.items():
        ck = (key[0], key[1], clip(key[2]))
        if ck in src:
            continue
        if key[0] not in seen_ok:
            out[key] = emb
    return out, sum(1 for e in out.values() if e is None), len(xfer)


# --- (а) неизменный источник ---
v = "город А"
st = {("t", "c", v): [0.1]}
out, nnull, nx = merge_pass(st, [("t", "c", v)], {"t"})
t("a: unchanged keeps emb", out.get(("t", "c", v)) == [0.1])
t("a: zero null", nnull == 0)
t("a: xfer empty", nx == 0)

# --- (б) одно значение изменилось ---
st = {("t", "c", "А"): [0.1], ("t", "c", "Б"): [0.2]}
out, nnull, _ = merge_pass(st, [("t", "c", "А"), ("t", "c", "Б-new")], {"t"})
t("b: unchanged keeps emb", out.get(("t", "c", "А")) == [0.1])
t("b: new value null emb", out.get(("t", "c", "Б-new")) is None)
t("b: old value removed", ("t", "c", "Б") not in out)
t("b: exactly one null", nnull == 1)

# --- (в) повторный прогон ---
out2, nnull2, nx2 = merge_pass(out, [("t", "c", "А"), ("t", "c", "Б-new")], {"t"})
t("c: rerun same map", out2 == out)
t("c: rerun xfer 0", nx2 == 0)

# --- (г) форма full→clip ---
long = "X" * (CLIP_N + 5000)
st = {("t", "c", long): [0.9]}
out, nnull, nx = merge_pass(st, [("t", "c", long)], {"t"})
ck = ("t", "c", clip(long))
t("d: clip key present", ck in out)
t("d: emb transferred", out.get(ck) == [0.9])
t("d: xfer 1", nx == 1)
t("d: zero null after xfer", nnull == 0)

# --- (д) повтор после clip ---
out2, _, nx2 = merge_pass(out, [("t", "c", long)], {"t"})
t("e: rerun keeps emb", out2.get(ck) == [0.9])
t("e: rerun xfer 0", nx2 == 0)

# --- grep SQL ---
txt = _sql_txt
t("SQL: res_clip", "CREATE OR REPLACE TABLE res_clip AS" in txt)
t("SQL: USING res_clip", "USING res_clip s" in txt)
t("SQL: INSERT s.val", "VALUES (s.tbl, s.col, s.val, NULL)" in txt)
t("SQL: no INSERT substr(s.val)", "substr(s.val, 1, 20000), NULL)" not in txt)
t("SQL: res_emb_xfer", "CREATE OR REPLACE TABLE res_emb_xfer AS" in txt)
t("SQL: form candidates",
  "value IS DISTINCT FROM substr(value, 1, 20000)" in txt)
t("SQL: batch UPDATE 1000",
  "res_emb_xfer_n" in txt and "x.n >= ' || (b * 1000)" in txt)
t("SQL: IF NOT EXISTS only",
  "CREATE TABLE IF NOT EXISTS resolver_index" in txt
  and "CREATE OR REPLACE TABLE resolver_index" not in txt)
t("SQL: resolver_emb_xfer quality", "'resolver_emb_xfer'" in txt)

print("PASS %d FAIL %d" % (PASS, len(FAIL)))
sys.exit(1 if FAIL else 0)
