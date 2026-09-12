#!/usr/bin/env python3
"""aggregate_live_column жив; S3: aggregate_live_header/row_count снесены.

[замер okna 30.08] count контрагентов 365 → folders в scope после фильтра.
Мок патчит psql в globals самой функции (serene_ask после wire_all).
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ASK_TOKEN", "test")
os.environ.setdefault("EMBED_BASE_URL", "-")
os.environ.setdefault("EMBED_MODEL", "-")

import serene_ask as A  # noqa: E402

PASS, FAIL = 0, []

def t(name, cond, detail=None):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, detail if detail is not None else "")


t("S3: aggregate_live_header_count GONE", not hasattr(A, "aggregate_live_header_count"))
t("S3: aggregate_live_row_count GONE", not hasattr(A, "aggregate_live_row_count"))
t("aggregate_live_column жив", callable(getattr(A, "aggregate_live_column", None)))

_old_psql = A.psql
AGG_SQL = []
_CAT_COLS = frozenset({"всего", "isfolder", "deletionmark", "ref_key"})
_REG_COLS = frozenset({"всего"})


def _col_from_duckdb_sql(ql):
    m = re.search(r"(?:lower\(column_name\)|column_name)\s*=\s*'([^']+)'", ql)
    return (m.group(1) if m else "").lower()


def _psql(q):
    ql = q.lower()
    if "duckdb_columns" in ql:
        if "lower(column_name) = 'ref_key'" in ql:
            return [("ref_key",)]
        col = _col_from_duckdb_sql(ql)
        return [(1,)] if col in _CAT_COLS else []
    if "query_table" in ql:
        AGG_SQL.append(q)
        return [(365, 10, 1, 2, None, 10)]
    return []


A.psql = _psql
try:
    r = A.aggregate_live_column("catalog_x", [], "Всего")
    t("живой итог вернулся", isinstance(r, dict) and r.get("count") == 365, r)
    sql = (AGG_SQL[-1] if AGG_SQL else "").lower()
    t("isfolder исключён", "isfolder" in sql and "not in" in sql, sql[:160])
    t("deletionmark исключён", "deletionmark" in sql, sql[:160])
    t("folders=2 в итоге", (r or {}).get("folders") == 2, (r or {}).get("folders"))
    t("folder_pred в scope", bool(((r or {}).get("scope") or {}).get("folder_pred")),
       (r or {}).get("scope"))

    AGG_SQL.clear()

    def _psql_noflags(q):
        ql = q.lower()
        if "duckdb_columns" in ql:
            if "lower(column_name) = 'ref_key'" in ql:
                return []
            col = _col_from_duckdb_sql(ql)
            return [(1,)] if col in _REG_COLS else []
        if "query_table" in ql:
            AGG_SQL.append(q)
            return [(100, 10, 1, 2, None, 10)]
        return []

    A.psql = _psql_noflags
    r2 = A.aggregate_live_column("accumulationregister_x", [], "Всего")
    sql2 = (AGG_SQL[-1] if AGG_SQL else "").lower()
    t("регистр без флагов работает", isinstance(r2, dict) and r2.get("count") == 100, r2)
    t("регистр флагов не получил", "isfolder" not in sql2 and "deletionmark" not in sql2,
       sql2[:160])
    t("folders=0 у регистра", (r2 or {}).get("folders") == 0, (r2 or {}).get("folders"))
finally:
    A.psql = _old_psql

print("ИТОГ: ok %d, FAIL %d" % (PASS, len(FAIL)))
sys.exit(1 if FAIL else 0)
