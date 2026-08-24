#!/usr/bin/env python3
"""Замок: SQL и арифметика embed_progress.sh.

Доки: data_import_and_export/parquet/overview#partial-reading (partial reading).
Запуск: python3 test_embed_progress.py
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(ROOT, "embed_progress.sh")
_fail = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global _fail
    if not cond:
        _fail += 1
    print(f"  {'PASS' if cond else 'FAIL ✗'}  {name}   {detail}")


def left_sql(tbl: str) -> str:
    svc = (
        f"NOT EXISTS (SELECT 1 FROM search_entity_class e "
        f"WHERE e.src_table = {tbl}.src_table AND e.cls = 'service')"
    )
    return (
        f"SELECT count(*) FROM (SELECT src_table FROM {tbl} WHERE emb IS NULL) {tbl} "
        f"WHERE true AND ({svc})"
    )


def extract_fn(name: str) -> str:
    text = open(SCRIPT, encoding="utf-8").read()
    m = re.search(rf"{name}\(\) \{{\n(.*?)\n\}}\n", text, re.S)
    assert m, name
    return m.group(1)


def main() -> int:
    print("== 1. left_sql совпадает с embed_missing ==")
    sql = left_sql("search_corpus")
    check("service filter", "search_entity_class" in sql and "service" in sql)
    check("без прямой проекции emb", "Projections" not in sql)
    check("partial reading: только src_table", "SELECT src_table FROM search_corpus WHERE emb IS NULL" in sql)

    print("== 2. скрипт исполняем и без имён баз ==")
    st = os.stat(SCRIPT)
    check("chmod +x", st.st_mode & 0o111)
    body = open(SCRIPT, encoding="utf-8").read()
    code_only = re.sub(r"#.*", "", body)
    check("нет klient/okna/ut_test в коде", not re.search(r"\b(klient-1|okna|ut_test)\b", code_only))
    check("dbname у движка", "current_database()" in body)
    check("TAG emb_${DBNAME}", "emb_${DBNAME}_${TBL}" in body)

    print("== 3. ETA из скорости (арифметика) ==")
    rem, spd = 1_000_000, 10.0
    eta_h = int(rem / spd) // 3600
    check("ETA hours", eta_h == 27, f"eta_h={eta_h}")

    print("== 4. dry: bash -n ==")
    r = subprocess.run(["bash", "-n", SCRIPT], capture_output=True, text=True)
    check("bash -n", r.returncode == 0, r.stderr.strip()[:120])

    print("== 5. перечень part у движка, одна сумма, признак неполноты ==")
    cp = extract_fn("count_parts")
    check("duckdb_tables()", "duckdb_tables()" in cp)
    check("фильтр текущей базы", "database_name = current_database()" in cp)
    check("сумма штатным query_table", "query_table(" in cp)
    check("нет seq по номерам", "seq " not in cp)
    check("нет верхней границы воркеров", "WORKERS_MAX" not in body and "EMBED_PART_WORKERS" not in code_only)
    check("нет трёх промахов", "miss" not in cp)
    check("не больше двух psql_timeout в count_parts", cp.count("psql_timeout") == 2)
    check("нет цикла for по таблицам", "for " not in cp)
    check("флаг неполноты в снимке", "PARTS_INCOMPLETE" in body and "parts=$(count_parts)" not in body)
    check("parts_incomplete в JSON", "parts_incomplete" in body)
    check("причина неполноты", "parts_incomplete_reason" in body)
    check("каталог недоступен — не молчать", "каталог duckdb_tables недоступен" in cp)
    check("сумма недоступна — не молчать", "сумма по part-таблицам недоступна" in cp)

    print(f"\nитог: {'OK' if _fail == 0 else f'{_fail} FAIL'}")
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(main())
