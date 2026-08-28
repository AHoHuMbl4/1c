#!/usr/bin/env python3
"""Оффлайн-замок Ф6.4: native freshness /health за ASK_HEALTH_NATIVE_FRESHNESS."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ASK_TOKEN", "test")
os.environ.setdefault("EMBED_BASE_URL", "-")
os.environ.setdefault("EMBED_MODEL", "-")

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


def with_env(**kw):
    saved = {}
    for k, v in kw.items():
        saved[k] = os.environ.get(k)
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    A.ASK_HEALTH_NATIVE_FRESHNESS = (
        os.environ.get("ASK_HEALTH_NATIVE_FRESHNESS", "0") == "1")
    A.ASK_HEALTH_SEARCH_IDX = os.environ.get(
        "ASK_HEALTH_SEARCH_IDX", "search_idx")
    return saved


def restore_env(saved):
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    A.ASK_HEALTH_NATIVE_FRESHNESS = (
        os.environ.get("ASK_HEALTH_NATIVE_FRESHNESS", "0") == "1")
    A.ASK_HEALTH_SEARCH_IDX = os.environ.get(
        "ASK_HEALTH_SEARCH_IDX", "search_idx")


class Cap:
    def __init__(self, rows_by_predicate):
        self.sql = []
        self.rows_by_predicate = rows_by_predicate

    def __call__(self, sql):
        self.sql.append(sql)
        for pred, rows in self.rows_by_predicate:
            if pred(sql):
                return rows
        return []


class FakeHandler(A.Handler):
    def __init__(self):
        self.path = "/health"
        self._code = None
        self._body = None

    def _send(self, code, obj):
        self._code = code
        self._body = obj


def stub_psql_corpus():
    return Cap([(lambda s: "count(*)" in s.lower(), [[100]])])


REAL = {
    "psql": A.psql,
    "measure": A._measure_native_index_freshness,
    "hg": A._health_gap,
    "cls": A._classify_health_gap,
}


def reset_reals():
    A.psql = REAL["psql"]
    A._measure_native_index_freshness = REAL["measure"]
    A._health_gap = REAL["hg"]
    A._classify_health_gap = REAL["cls"]


# --- умолчание ---
t("default ASK_HEALTH_NATIVE_FRESHNESS off",
  A.ASK_HEALTH_NATIVE_FRESHNESS is False)
t("default ASK_HEALTH_SEARCH_IDX",
  A.ASK_HEALTH_SEARCH_IDX == "search_idx")

# --- флаг off: без freshness / без native ---
saved = with_env(ASK_HEALTH_NATIVE_FRESHNESS="0")
native_calls = []
A.psql = stub_psql_corpus()
A._health_gap = lambda: None
A._classify_health_gap = lambda g: None
A._measure_native_index_freshness = lambda: native_calls.append(1) or {}
h = FakeHandler()
h.do_GET()
t("off: HTTP 200", h._code == 200, h._code)
t("off: no freshness key", "freshness" not in (h._body or {}), h._body)
t("off: no native measure call", native_calls == [], native_calls)
reset_reals()
restore_env(saved)

# --- freshness_lag + флаг off: только merge_pending_sec ---
saved = with_env(ASK_HEALTH_NATIVE_FRESHNESS="0")
native_calls = []
A.psql = stub_psql_corpus()
A._health_gap = lambda: {"entities": 1, "rows_missing": 5}
A._classify_health_gap = lambda g: {
    "entities": 1, "rows_missing": 5, "kind": "freshness_lag",
    "merge_pending_sec": 42}
A._measure_native_index_freshness = lambda: native_calls.append(1) or {}
h = FakeHandler()
h.do_GET()
t("off lag: freshness only merge",
  (h._body or {}).get("freshness") == {"merge_pending_sec": 42}, h._body)
t("off lag: no index_buffered",
  "index_buffered_docs" not in ((h._body or {}).get("freshness") or {}),
  h._body)
t("off lag: no native call", native_calls == [], native_calls)
reset_reals()
restore_env(saved)

# --- флаг on + мок метрик рядом с merge ---
saved = with_env(ASK_HEALTH_NATIVE_FRESHNESS="1",
                 ASK_HEALTH_SEARCH_IDX="search_idx")
mock_native = {
    "index_buffered_docs": 7,
    "index_failed_commits": 0,
    "refresh_pending": 1,
    "refresh_active": 0,
}
A.psql = stub_psql_corpus()
A._health_gap = lambda: {"entities": 1, "rows_missing": 5}
A._classify_health_gap = lambda g: {
    "entities": 1, "rows_missing": 5, "kind": "freshness_lag",
    "merge_pending_sec": 137}
A._measure_native_index_freshness = lambda: dict(mock_native)
h = FakeHandler()
h.do_GET()
fr = (h._body or {}).get("freshness") or {}
t("on: HTTP 200", h._code == 200, h._code)
t("on: keeps merge_pending_sec", fr.get("merge_pending_sec") == 137, fr)
t("on: index_buffered_docs from mock", fr.get("index_buffered_docs") == 7, fr)
t("on: index_failed_commits", fr.get("index_failed_commits") == 0, fr)
t("on: refresh_pending", fr.get("refresh_pending") == 1, fr)
t("on: refresh_active", fr.get("refresh_active") == 0, fr)
reset_reals()
restore_env(saved)

# --- measure SQL: sdb_metrics, имя из env, без VACUUM ---
saved = with_env(ASK_HEALTH_NATIVE_FRESHNESS="1",
                 ASK_HEALTH_SEARCH_IDX="my_search_idx")
cap = Cap([
    (lambda s: "sdb_metrics" in s, [
        ["index", 3, 0, None, None],
        ["process", None, None, 2, 1],
    ]),
])
A.psql = cap
out = A._measure_native_index_freshness()
sql = "\n".join(cap.sql)
t("measure: returns buffered", out.get("index_buffered_docs") == 3, out)
t("measure: returns failed", out.get("index_failed_commits") == 0, out)
t("measure: refresh_pending", out.get("refresh_pending") == 2, out)
t("measure: refresh_active", out.get("refresh_active") == 1, out)
t("measure: SQL has sdb_metrics", "sdb_metrics" in sql, sql)
t("measure: SQL has pg_class", "pg_class" in sql, sql)
t("measure: SQL uses env idx name", "my_search_idx" in sql, sql)
t("measure: SQL has no VACUUM", "VACUUM" not in sql.upper(), sql)
t("measure: SQL has no REFRESH_INDEX", "REFRESH_INDEX" not in sql.upper(), sql)
reset_reals()
restore_env(saved)

# --- ошибка чтения: явный degraded, merge не подменяется ---
saved = with_env(ASK_HEALTH_NATIVE_FRESHNESS="1")
A.psql = stub_psql_corpus()
A._health_gap = lambda: {"entities": 1, "rows_missing": 5}
A._classify_health_gap = lambda g: {
    "entities": 1, "rows_missing": 5, "kind": "freshness_lag",
    "merge_pending_sec": 50}


def boom():
    raise RuntimeError("sdb_metrics unavailable")


A._measure_native_index_freshness = boom
h = FakeHandler()
h.do_GET()
fr = (h._body or {}).get("freshness") or {}
t("err: still 200 with lag", h._code == 200, h._code)
t("err: keeps merge_pending_sec", fr.get("merge_pending_sec") == 50, fr)
t("err: index_metrics unknown", fr.get("index_metrics") == "unknown", fr)
t("err: has error text", "unavailable" in (fr.get("error") or ""), fr)
t("err: no fake buffered", "index_buffered_docs" not in fr, fr)
reset_reals()
restore_env(saved)

# --- attach: не подменяет merge buffered-ом ---
fr = A._attach_native_freshness(
    {"merge_pending_sec": 10},
    {"index_buffered_docs": 99, "index_failed_commits": 0,
     "refresh_pending": 0, "refresh_active": 0})
t("attach: merge stays", fr.get("merge_pending_sec") == 10, fr)
t("attach: buffered separate", fr.get("index_buffered_docs") == 99, fr)

# --- исходник: /health не вызывает VACUUM (комментарий «не зовём» — ок) ---
src = A.ask_source()
health_idx = src.find('if self.path.rstrip("/") == "/health"')
health_end = src.find("def do_POST", health_idx)
health_src = src[health_idx:health_end]
t("source health: no VACUUM call",
  "VACUUM (" not in health_src.upper()
  and 'psql("VACUUM' not in health_src
  and "psql('VACUUM" not in health_src)
t("source: has ASK_HEALTH_NATIVE_FRESHNESS",
  "ASK_HEALTH_NATIVE_FRESHNESS" in src)

print("PASS %d FAIL %d" % (PASS, len(FAIL)))
sys.exit(1 if FAIL else 0)
