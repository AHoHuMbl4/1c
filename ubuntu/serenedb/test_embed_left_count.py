#!/usr/bin/env python3
"""Замок: left()-count в embed_missing не проецирует FLOAT[1024] emb в CTE.

Корень fail-loop на klient-1 (21.08):
  SELECT count(*) FROM search_corpus WHERE emb IS NULL AND NOT EXISTS (...)
давал план `Projections: emb, src_table` и OOM на ~15 млн векторов.

Новая форма — подзапрос только с лёгкими колонками; emb остаётся Column Filter.
Доки: data_import_and_export/parquet/overview#partial-reading (читать лишь нужное).

Запуск: python3 test_embed_left_count.py
Требует живой SereneDB (postgres + ut_test).
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

_base = os.environ.get("SERENEDB_DSN", "host=127.0.0.1 port=7890 user=postgres dbname=postgres")
DSN_PG = _base.replace("user=serene_ro", "user=postgres")
if "dbname=" not in DSN_PG:
    DSN_PG += " dbname=postgres"
DSN_UT = DSN_PG.replace("dbname=postgres", "dbname=ut_test")

_fail = 0


def psql(dsn: str, sql: str, *, on_error_stop: bool = True) -> str:
    cmd = ["psql", dsn, "-tA"]
    if on_error_stop:
        cmd.extend(["-v", "ON_ERROR_STOP=1"])
    cmd.extend(["-c", sql])
    r = subprocess.run(cmd, text=True, capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[:400] or r.stdout.strip()[:400])
    return r.stdout.strip()


def check(name: str, cond: bool, detail: str = "") -> None:
    global _fail
    if not cond:
        _fail += 1
    print(f"  {'PASS' if cond else 'FAIL ✗'}  {name}   {detail}")


def new_sql(tbl: str, rows_where: str) -> str:
    """Та же форма, что left() в embed_missing.sh при непустом ROWS_WHERE."""
    return (
        f"SELECT count(*) FROM (SELECT src_table FROM {tbl} WHERE emb IS NULL) {tbl} "
        f"WHERE true {rows_where}"
    )


def old_sql(tbl: str, rows_where: str) -> str:
    return f"SELECT count(*) FROM {tbl} WHERE emb IS NULL {rows_where}"


def main() -> int:
    rw = (
        "AND (NOT EXISTS (SELECT 1 FROM search_entity_class e "
        "WHERE e.src_table = search_corpus.src_table AND e.cls = 'service'))"
    )

    print("== 1. план: новая форма не проецирует emb ==")
    for label, dsn in (("postgres", DSN_PG), ("ut_test", DSN_UT)):
        plan_new = psql(dsn, f"EXPLAIN {new_sql('search_corpus', rw)}")
        plan_old = psql(dsn, f"EXPLAIN {old_sql('search_corpus', rw)}")
        check(
            f"{label}: new без Projections: emb",
            "Projections: emb" not in plan_new,
            "new=" + ("ok" if "Projections: src_table" in plan_new else "no src_table proj"),
        )
        check(
            f"{label}: old с Projections: emb (регрессия формы)",
            "Projections: emb" in plan_old,
            "иначе замок не ловит корень",
        )
        check(
            f"{label}: new Column Filter emb IS NULL",
            "Column Filter: emb IS NULL" in plan_new,
        )

    print("== 2. синтетика FLOAT[1024] NULL: счёт new == old ==")
    # Без заполнения векторов: UPDATE FLOAT[1024] на деве сейчас упирается в
    # сломанный temp_directory движка (PrivateTmp). NULL-строк достаточно, чтобы
    # сравнить счёт и план.
    for stmt in (
        "DROP TABLE IF EXISTS left_oom_probe",
        "DROP TABLE IF EXISTS left_oom_class",
        "CREATE TABLE left_oom_probe (src_table VARCHAR, emb FLOAT[1024])",
        "INSERT INTO left_oom_probe SELECT ('t_' || (i % 50))::VARCHAR, NULL::FLOAT[1024] FROM range(0, 50000) t(i)",
        "CREATE TABLE left_oom_class AS SELECT ('t_' || i)::VARCHAR AS src_table, "
        "CASE WHEN i < 10 THEN 'service' ELSE 'business' END AS cls FROM range(0, 50) t(i)",
    ):
        psql(DSN_PG, stmt)
    rw_p = (
        "AND (NOT EXISTS (SELECT 1 FROM left_oom_class e "
        "WHERE e.src_table = left_oom_probe.src_table AND e.cls = 'service'))"
    )
    n_old = int(psql(DSN_PG, old_sql("left_oom_probe", rw_p)))
    n_new = int(psql(DSN_PG, new_sql("left_oom_probe", rw_p)))
    check("probe count new==old", n_old == n_new and n_new > 0, f"old={n_old} new={n_new}")
    plan_p_new = psql(DSN_PG, f"EXPLAIN {new_sql('left_oom_probe', rw_p)}")
    plan_p_old = psql(DSN_PG, f"EXPLAIN {old_sql('left_oom_probe', rw_p)}")
    check("probe new без emb", "Projections: emb" not in plan_p_new)
    check("probe old с emb", "Projections: emb" in plan_p_old)
    for stmt in (
        "DROP TABLE IF EXISTS left_oom_probe",
        "DROP TABLE IF EXISTS left_oom_class",
    ):
        try:
            psql(DSN_PG, stmt)
        except RuntimeError as e:
            print(f"  WARN cleanup: {e}")

    print("== 3. живой ut_test: count без OOM, время разумное ==")
    t0 = time.monotonic()
    n_ut = int(psql(DSN_UT, new_sql("search_corpus", rw)))
    dt = time.monotonic() - t0
    rows = int(psql(DSN_UT, "SELECT count(*) FROM search_corpus"))
    check(
        "ut_test left() завершился",
        True,
        f"n={n_ut} rows={rows} dt={dt:.2f}s",
    )
    check("ut_test left() < 60s", dt < 60.0, f"dt={dt:.2f}s")

    print("== 4. извлечённые колонки для resolver (table_name) ==")
    # Как в embed_missing.sh: grep $TBL.col из ROWS_WHERE
    import re

    tbl = "resolver_index"
    rows_where = (
        "AND (NOT EXISTS (SELECT 1 FROM search_entity_class e "
        "WHERE lower(e.src_table) = lower(resolver_index.table_name) AND e.cls = 'service'))"
    )
    cols = sorted(set(re.findall(rf"{tbl}\.([A-Za-z_][A-Za-z0-9_]*)", rows_where)))
    check("resolver light cols", cols == ["table_name"], f"cols={cols}")

    print(f"\nитог: { 'OK' if _fail == 0 else f'{_fail} FAIL' }")
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(main())
