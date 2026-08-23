#!/usr/bin/env python3
"""Оффлайн-замок Ф6.1: SQL-RRF за ASK_SQL_RRF, fallback на python-RRF."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ASK_TOKEN", "test")
import serene_ask as A
PASS, FAIL = 0, []

def t(name, cond, detail=""):
    global PASS
    if cond: PASS += 1; print("ok  -", name)
    else: FAIL.append(name); print("FAIL-", name, ("| "+str(detail)[:160]) if detail else "")

class Base:
    def __init__(self, rule): self.rule, self.sql = rule, []
    def __call__(self, sql): self.sql.append(sql); return self.rule(sql)

def with_env(**kw):
    saved = {}
    for k, v in kw.items():
        saved[k] = os.environ.get(k)
        if v is None: os.environ.pop(k, None)
        else: os.environ[k] = v
    A.ASK_SQL_RRF = os.environ.get("ASK_SQL_RRF", "0") == "1"
    return saved

def restore_env(saved):
    for k, v in saved.items():
        if v is None: os.environ.pop(k, None)
        else: os.environ[k] = v
    A.ASK_SQL_RRF = os.environ.get("ASK_SQL_RRF", "0") == "1"

def with_base(rule, fn):
    base, real = Base(rule), A.psql
    A.psql = base
    try: return fn(), base.sql
    finally: A.psql = real

EXPR = "ts_phrase('пробный')"
FUSED_HEAD = "WITH fused AS ("

def branch_rule(sql):
    if FUSED_HEAD in sql:
        if "corpus_ivf_idx" in sql:
            return [["register_пробный_a"], ["catalog_пробный_b"]]
        return [["register_пробный_a"], ["catalog_пробный_b"], ["document_пробный_c"]]
    if "FROM search_entity_card" in sql or "FROM search_tables" in sql:
        if "emb <=>" in sql and "RANK()" in sql:
            return [["register_пробный_a"]]
    if "duckdb_indexes" in sql: return [["1"]]
    if "search_quality" in sql: return [["Qwen3-Embedding-4B"]]
    return []

def _emb_mocks():
    A._EMB_OK_CACHE.clear(); A._CORPUS_IVF_CACHE.clear()
    A._EMB_LIVE_CACHE[0] = True; A._EMB_LIVE_CACHE[1] = 0
    real_emb, real_ivf, real_vec = A.emb_ready, A._corpus_ivf_ready, A._vec
    A.emb_ready = lambda table: table in (A.CORPUS, A.CARD, A.TABLES)
    A._vec = lambda text: "[0.1,0.2]::FLOAT[2]"
    return real_emb, real_ivf, real_vec

saved = with_env(ASK_SQL_RRF="0")
real_emb, real_ivf, real_vec = _emb_mocks()
out, sqls = with_base(branch_rule, lambda: A._fused_candidates([EXPR], "продажи пробные", "сколько пробных продаж", 3))
t("флаг off без corpus", not any("corpus_ivf" in q for q in sqls), sqls)
t("флаг off порядок", out == ["register_пробный_a", "catalog_пробный_b", "document_пробный_c"], out)
A.emb_ready, A._vec = real_emb, real_vec; restore_env(saved)

saved = with_env(ASK_SQL_RRF="1")
real_emb, real_ivf, real_vec = _emb_mocks(); A._corpus_ivf_ready = lambda: False
out, sqls = with_base(branch_rule, lambda: A._fused_candidates([EXPR], "продажи пробные", "сколько пробных продаж", 3))
t("флаг on без IVF = off", not any("corpus_ivf" in q for q in sqls), sqls)
A.emb_ready, A._corpus_ivf_ready, A._vec = real_emb, real_ivf, real_vec; restore_env(saved)

saved = with_env(ASK_SQL_RRF="1")
real_emb, real_ivf, real_vec = _emb_mocks(); A._corpus_ivf_ready = lambda: True
diag = {}
out, sqls = with_base(branch_rule, lambda: A._fused_candidates([EXPR], "продажи пробные", "сколько пробных продаж", 3, diag=diag))
t("флаг on + IVF", any("corpus_ivf_idx" in q for q in sqls), sqls)
t("diag sql_rrf", diag.get("sql_rrf") is True, diag)
A.emb_ready, A._corpus_ivf_ready, A._vec = real_emb, real_ivf, real_vec; restore_env(saved)

def fail_fused(sql):
    if FUSED_HEAD in sql and "corpus_ivf" in sql: raise RuntimeError("mock fail")
    return branch_rule(sql)
saved = with_env(ASK_SQL_RRF="1")
real_emb, real_ivf, real_vec = _emb_mocks(); A._corpus_ivf_ready = lambda: True
diag = {}
out, _ = with_base(fail_fused, lambda: A._fused_candidates([EXPR], "продажи пробные", "сколько", 3, diag=diag))
t("fallback marked", diag.get("sql_rrf_fallback") is True, diag)
t("fallback non-empty", bool(out), out)
A.emb_ready, A._corpus_ivf_ready, A._vec = real_emb, real_ivf, real_vec; restore_env(saved)

print("\nИтог:", PASS, "ok,", len(FAIL), "fail")
sys.exit(1 if FAIL else 0)
