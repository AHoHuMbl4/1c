#!/usr/bin/env python3
"""Оффлайн-замок Ф6.2: resolve_values через ASK_RESOLVER_IVF / resolver_ivf_idx."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ASK_TOKEN", "test")
# Реранкер не зовём: пустой ключ → порядок кандидатов как пришёл из SQL.
os.environ.pop("RERANK_KEY", None)
os.environ.pop("DASHSCOPE_API_KEY", None)
import serene_ask as A
PASS, FAIL = 0, []

def t(name, cond, detail=""):
    global PASS
    if cond: PASS += 1; print("ok  -", name)
    else: FAIL.append(name); print("FAIL-", name, ("| "+str(detail)[:160]) if detail else "")

def with_env(**kw):
    saved = {}
    for k, v in kw.items():
        saved[k] = os.environ.get(k)
        if v is None: os.environ.pop(k, None)
        else: os.environ[k] = v
    A.ASK_RESOLVER_IVF = os.environ.get("ASK_RESOLVER_IVF", "0") == "1"
    A.RESOLVER_IVF_IDX = os.environ.get("ASK_RESOLVER_IVF_IDX", "resolver_ivf_idx")
    return saved

def restore_env(saved):
    for k, v in saved.items():
        if v is None: os.environ.pop(k, None)
        else: os.environ[k] = v
    A.ASK_RESOLVER_IVF = os.environ.get("ASK_RESOLVER_IVF", "0") == "1"
    A.RESOLVER_IVF_IDX = os.environ.get("ASK_RESOLVER_IVF_IDX", "resolver_ivf_idx")

class Cap:
    def __init__(self, rows):
        self.sql, self.rows = [], rows
    def __call__(self, sql):
        self.sql.append(sql)
        return self.rows

# Значение делит триграмм с «питер» («тер») — проходит _shares_chars без сети.
HIT = [["Санкт-Петербург"]]

def _mocks(ivf_ready):
    A._EMB_OK_CACHE.clear()
    A._RESOLVER_IVF_CACHE.clear()
    real = (A.emb_ready, A._vec, A._resolver_psql, A._resolver_ivf_ready, A.rerank)
    A.emb_ready = lambda table: table == "resolver_index"
    A._vec = lambda text: "[0.1,0.2]::FLOAT[2]"
    A._resolver_ivf_ready = lambda: ivf_ready
    A.rerank = lambda q, docs: []
    return real

def _restore(real):
    A.emb_ready, A._vec, A._resolver_psql, A._resolver_ivf_ready, A.rerank = real

# --- умолчание: флаг выключен ---
t("default ASK_RESOLVER_IVF off", A.ASK_RESOLVER_IVF is False)
t("default idx name", A.RESOLVER_IVF_IDX == "resolver_ivf_idx")

# --- флаг off → exact по resolver_index, <=> , не IVF ---
saved = with_env(ASK_RESOLVER_IVF="0")
real = _mocks(True)
cap = Cap(HIT)
A._resolver_psql = cap
out = A.resolve_values("питер")
sql = cap.sql[-1] if cap.sql else ""
t("off: hits resolver_index", "resolver_index" in sql, sql)
t("off: uses <=>", "<=>" in sql, sql)
t("off: no IVF idx name", "resolver_ivf_idx" not in sql, sql)
t("off: has WHERE emb", "WHERE emb IS NOT NULL" in sql, sql)
t("off: no <#>", "<#>" not in sql, sql)
t("off: returns hit", bool(out), out)
_restore(real); restore_env(saved)

# --- флаг on + индекс «есть» → IVF, <#> , без WHERE emb ---
saved = with_env(ASK_RESOLVER_IVF="1", ASK_RESOLVER_IVF_IDX="resolver_ivf_idx")
real = _mocks(True)
cap = Cap(HIT)
A._resolver_psql = cap
out = A.resolve_values("питер")
sql = cap.sql[-1] if cap.sql else ""
t("on+ready: IVF idx in FROM", "FROM resolver_ivf_idx" in sql, sql)
t("on+ready: uses <#>", "<#>" in sql, sql)
t("on+ready: no WHERE emb", "WHERE emb IS NOT NULL" not in sql, sql)
t("on+ready: no exact table", "resolver_index" not in sql, sql)
t("on+ready: no <=>", "<=>" not in sql, sql)
t("on+ready: returns hit", bool(out), out)
_restore(real); restore_env(saved)

# --- флаг on, индекса нет → тихий fallback на exact ---
saved = with_env(ASK_RESOLVER_IVF="1")
real = _mocks(False)
cap = Cap(HIT)
A._resolver_psql = cap
out = A.resolve_values("питер")
sql = cap.sql[-1] if cap.sql else ""
t("on+noidx: fallback resolver_index", "resolver_index" in sql, sql)
t("on+noidx: fallback <=>", "<=>" in sql, sql)
t("on+noidx: no IVF in SQL", "resolver_ivf_idx" not in sql, sql)
_restore(real); restore_env(saved)

# --- кастомное имя индекса из env ---
saved = with_env(ASK_RESOLVER_IVF="1", ASK_RESOLVER_IVF_IDX="custom_res_ivf")
real = _mocks(True)
cap = Cap(HIT)
A._resolver_psql = cap
A.resolve_values("питер")
sql = cap.sql[-1] if cap.sql else ""
t("custom idx name", "FROM custom_res_ivf" in sql, sql)
_restore(real); restore_env(saved)

print("\nИтог:", PASS, "ok,", len(FAIL), "fail")
sys.exit(1 if FAIL else 0)
