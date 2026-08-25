#!/usr/bin/env python3
"""Оффлайн-замок: вопрос-эмбеддинг через ai_embed за ASK_EMBED_NATIVE."""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ASK_TOKEN", "test")
os.environ.setdefault("SERENEDB_DSN_RO", "host=127.0.0.1 port=7890 user=serene_ro dbname=postgres")
os.environ.setdefault("EMBED_BASE_URL", "http://127.0.0.1:9")
os.environ.setdefault("EMBED_HOST", "http://127.0.0.1:9")
os.environ.setdefault("EMBED_MODEL", "Qwen3-Embedding-4B")
os.environ.setdefault("EMBED_DIM", "1024")
os.environ.setdefault("EMBED_SECRET", "ask_embed_test")
# Умолч. EMBED_API в serene_ask — openai; мок ниже — формат texts (как okna).
os.environ.setdefault("EMBED_API", "texts")

import serene_ask as A  # noqa: E402
A.EMBED_API = os.environ.get("EMBED_API", "openai")

PASS, FAIL = 0, []


def t(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + str(detail)[:200]) if detail else "")


def with_env(**kw):
    saved = {}
    for k, v in kw.items():
        saved[k] = os.environ.get(k)
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    A._reload_embed_native_env()
    return saved


def restore_env(saved):
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    A._reload_embed_native_env()
    A.EMBED_API = os.environ.get("EMBED_API", "openai")


class CapPsql:
    def __init__(self, handler):
        self.handler = handler
        self.calls = []

    def __call__(self, sql):
        self.calls.append(sql)
        return self.handler(sql)


REAL = {"psql": A.psql, "urlopen": None}


def reset_reals():
    A.psql = REAL["psql"]


# --- умолчание ---
t("ASK_EMBED_NATIVE exists", hasattr(A, "ASK_EMBED_NATIVE"))
t("default ASK_EMBED_NATIVE off", A.ASK_EMBED_NATIVE is False)

# --- флаг 0: HTTP-путь ---
saved = with_env(ASK_EMBED_NATIVE="0", EMBED_API="texts")
A.EMBED_API = "texts"
http_hits = []


class FakeResp:
    def read(self):
        return json.dumps({"embeddings": [[0.1, 0.2]]}).encode()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def fake_urlopen(req, timeout=60):
    http_hits.append(req.full_url)
    return FakeResp()


import urllib.request  # noqa: E402

REAL["urlopen"] = urllib.request.urlopen
urllib.request.urlopen = fake_urlopen
A._EMB_ONE_CACHE.clear()
try:
    vec = A.embed_one("тестовый вопрос")
finally:
    urllib.request.urlopen = REAL["urlopen"]
reset_reals()
restore_env(saved)
t("flag 0: HTTP вызов", len(http_hits) == 1, http_hits)
t("flag 0: вектор из HTTP", vec == [0.1, 0.2], vec)

# --- флаг 1: один SQL ai_embed ---
saved = with_env(ASK_EMBED_NATIVE="1", EMBED_DIM="3")
native_sql = []


def native_ok(sql):
    native_sql.append(sql)
    if "CREATE OR REPLACE TEMPORARY SECRET" in sql:
        return []
    if "duckdb_secrets()" in sql:
        return []
    if "to_json(ai_embed" in sql:
        return [[json.dumps([0.5, -0.25, 0.125])]]
    return []


cap = CapPsql(native_ok)
A.psql = cap
A._EMBED_SECRET_READY = False
A._EMB_ONE_CACHE.clear()
try:
    vec = A.embed_one("один вопрос")
finally:
    reset_reals()
    A._EMBED_SECRET_READY = False
restore_env(saved)
embed_calls = [s for s in cap.calls if "to_json(ai_embed" in s]
t("flag 1: ai_embed SQL", len(embed_calls) == 1, embed_calls)
t("flag 1: secret constant in SQL", "ask_embed_test" in (embed_calls[0] if embed_calls else ""))
t("flag 1: размерность 3", len(vec) == 3 and vec[0] == 0.5, vec)
before = len(embed_calls)
A.embed_one("один вопрос")
t("flag 1: кэш без второго ai_embed SQL", len(embed_calls) == before, len(embed_calls))
A._EMB_ONE_CACHE.clear()

# --- нет секрета → явная ошибка ---
saved = with_env(ASK_EMBED_NATIVE="1")


def secret_missing(sql):
    if "CREATE OR REPLACE TEMPORARY SECRET" in sql:
        raise RuntimeError("permission denied for CREATE SECRET")
    if "duckdb_secrets()" in sql:
        return []
    raise RuntimeError("ai_embed: secret 'ask_embed_test' not found")


A.psql = CapPsql(secret_missing)
A._EMBED_SECRET_READY = False
A._EMB_ONE_CACHE.clear()
err = None
try:
    A.embed_one("вопрос")
except RuntimeError as e:
    err = str(e)
finally:
    reset_reals()
    A._EMBED_SECRET_READY = False
restore_env(saved)
t("нет секрета → RuntimeError", err is not None, err)
t("нет секрета → текст про секрет", err and ("секрет" in err.lower() or "secret" in err.lower()), err)

# --- размерность ≠ EMBED_DIM → явная ошибка ---
saved = with_env(ASK_EMBED_NATIVE="1", EMBED_DIM="1024")


def bad_dim(sql):
    if "CREATE OR REPLACE TEMPORARY SECRET" in sql or "duckdb_secrets()" in sql:
        return []
    return [[json.dumps([0.0] * 512)]]


A.psql = CapPsql(bad_dim)
A._EMBED_SECRET_READY = False
A._EMB_ONE_CACHE.clear()
err = None
try:
    A.embed_one("размерность")
except RuntimeError as e:
    err = str(e)
finally:
    reset_reals()
    A._EMBED_SECRET_READY = False
restore_env(saved)
t("bad dim → RuntimeError", err is not None, err)
t("bad dim → текст про размерность", err and "1024" in err, err)

# --- _vec использует embed_one ---
saved = with_env(ASK_EMBED_NATIVE="0", EMBED_API="texts")
A.EMBED_API = "texts"
A.psql = CapPsql(lambda s: [])
urllib.request.urlopen = fake_urlopen
http_hits.clear()
A._EMB_ONE_CACHE.clear()
try:
    frag = A._vec("вектор")
finally:
    urllib.request.urlopen = REAL["urlopen"]
    reset_reals()
restore_env(saved)
t("_vec: FLOAT[1024] в SQL", "FLOAT[1024]" in frag, frag)
t("_vec: HTTP при флаге 0", len(http_hits) >= 1)

print("PASS %d FAIL %d" % (PASS, len(FAIL)))
sys.exit(1 if FAIL else 0)
