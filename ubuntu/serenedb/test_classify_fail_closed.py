#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Оффлайн-замки fail-closed разметки (возврат 2).

Симуляция: полный провал модели → код 2; потолок / частичный успех → 0.
Живой 401 на klient-1 не гоняем здесь — это код выхода classify_entities.
"""
from pathlib import Path
import re
import classify_entities as C

PASS = 0
FAIL = []


def t(name, ok):
    global PASS
    if ok:
        PASS += 1
        print("ok ", name)
    else:
        FAIL.append(name)
        print("FAIL", name)


t("401-sim: done=0 failed>0 → 2", C.classify_exit_code(0, 400, 400) == 2)
t("ceiling: done=400 left-work → 0", C.classify_exit_code(400, 0, 400) == 0)
t("partial: done>0 failed>0 → 0", C.classify_exit_code(390, 10, 400) == 0)
t("idle: attempted=0 → 0", C.classify_exit_code(0, 0, 0) == 0)

build = Path(__file__).with_name("build.sh").read_text()
t("build: soft-warn убран", "ВНИМАНИЕ: разметка не удалась" not in build)
t("build: fail-closed на classify",
  "без разметки векторы не считаем" in build
  and "python3 classify_entities.py" in build
  and "|| fail" in build)
t("build: ROWS_WHERE на метках service",
  "search_tables.src_table" in build and "e.cls = 'service'" in build)
t("build: ROWS_WHERE на resolver service",
  "resolver_index.table_name" in build)

resolver = Path(__file__).with_name("resolver_build.sql").read_text()
t("resolver: p_val без service",
  "search_entity_class" in resolver
  and "e.cls = 'service'" in resolver
  and "EXECUTE p_val" in resolver)
t("resolver: DELETE service из index",
  "DELETE FROM resolver_index" in resolver
  and "e.cls = 'service'" in resolver)

# Старый soft-path не должен вернуться одной строкой
soft = re.findall(r"classify_entities\.py.*\n.*ВНИМАНИЕ", build)
t("build: нет soft-path classify→ВНИМАНИЕ", not soft)

print("----")
print(f"{PASS} ok, {len(FAIL)} fail")
if FAIL:
    raise SystemExit(1)
