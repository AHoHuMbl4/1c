#!/usr/bin/env python3
"""Оффлайн: перепись полноты считает объекты только при физической колонке ключа."""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

FAILS = []


def check(name, cond, detail=""):
    print(("ok  " if cond else "FAIL") + "  " + name + (("  " + str(detail)[:200]) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


cov = open(os.path.join(ROOT, "coverage_build.sql"), encoding="utf-8").read()

check("obj insert uses duckdb_columns", "duckdb_columns()" in cov)
check("obj filter case-insensitive ref_key",
      "lower(dc.column_name) = 'ref_key'" in cov)
check("no hardcoded p_cov_obj Ref_Key",
      "PREPARE p_cov_obj AS INSERT INTO cov_mart_obj" not in cov
      and 'count(DISTINCT "Ref_Key")' not in cov)
check("dynamic column name in obj insert",
      "count(DISTINCT \"" in cov and "dc.column_name" in cov)
check("structural reason missing key col",
      "перепись объектов: нет колонки ключа" in cov)
check("obj_recount_ok gate", "obj_recount_ok" in cov)

check("selection requires physical ref_key",
      "lower(dc.column_name) = 'ref_key'" in cov
      and cov.count("lower(dc.column_name) = 'ref_key'") >= 2)

# Мок: ключ есть физически — INSERT генерируется с именем из каталога.
check("insert reads column_name from catalog",
      "SELECT dc.column_name FROM duckdb_columns()" in cov)

if FAILS:
    print("FAIL %d/%d" % (len(FAILS), 8))
    sys.exit(1)
print("OK %d/%d" % (8 - len(FAILS), 8))
