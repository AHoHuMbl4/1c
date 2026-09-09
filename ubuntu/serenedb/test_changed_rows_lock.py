#!/usr/bin/env python3
"""Оффлайн: контур маркеров строк search_changed_rows (полная B, этап 0).

0c: DDL живёт в corpus_init.sql с UNIQUE (src_table, key_text, op); миграция для
баз, собранных до пакета, идемпотентна (оба statement-условия пусты при готовом
констрейнте). 0d: pipeline.sh возвращает строковый снимок после синка дописыванием
отсутствующих — симметрично sources. Каркас L0: константа partial_rebuild объявлена
в corpus_merge и равна 0 (ветвление merge — этап 1, сторож A — после 0f; полный L0
на движке-фикстуре вводит этап 1d).

Запуск: python3 test_changed_rows_lock.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
INIT = os.path.join(ROOT, "corpus_init.sql")
MERGE = os.path.join(ROOT, "corpus_merge.sql")
PIPE = os.path.join(ROOT, "pipeline.sh")
APPLY = os.path.join(ROOT, "..", "packet", "packet_apply.py")

PASS, FAIL = 0, []


def t(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + str(detail))[:200] if detail else "")


init = open(INIT, encoding="utf-8").read()
merge = open(MERGE, encoding="utf-8").read()
pipe = open(PIPE, encoding="utf-8").read()
apply_py = open(APPLY, encoding="utf-8").read()

# --- 0c: DDL в corpus_init (канон для новых баз) ---
t("init: DDL search_changed_rows",
  "CREATE TABLE IF NOT EXISTS search_changed_rows" in init)
t("init: UNIQUE тройки",
  "UNIQUE (src_table, key_text, op)" in init)
t("init: op/ts колонки",
  "op VARCHAR, ts TIMESTAMP DEFAULT now()" in init)

# --- 0c: миграция идемпотентна (для баз, собранных до пакета) ---
n_cond = init.count("WHERE NOT EXISTS (SELECT 1 FROM information_schema.table_constraints")
t("init: миграция за констрейнтом-условием (два statement)",
  n_cond >= 2, "found %d" % n_cond)
t("init: дедуп оставляет свежий ts (row_number ts DESC)",
  "ORDER BY ts DESC, rowid DESC" in init)
t("init: ADD CONSTRAINT UNIQUE",
  "ADD CONSTRAINT search_changed_rows_uniq" in init)

# --- 3d (синхронная часть 0c): писатели идемпотентны при UNIQUE ---
t("apply: delta upsert ON CONFLICT",
  "ON CONFLICT (src_table, key_text, op) DO UPDATE SET ts = EXCLUDED.ts" in apply_py)
t("apply: gone upsert ON CONFLICT",
  apply_py.count("DO UPDATE SET ts = EXCLUDED.ts") >= 2)
# SKIP-инвариант (план 0b/5b) читает max(ts) — повторная отметка ОБЯЗАНА освежать ts
t("apply: ensure-миграция свежего ts",
  "ORDER BY ts DESC, rowid DESC" in apply_py)

# --- 0d: снимок rows возвращается после синка ---
i_sync = pipe.find("serene_sync.py")
i_snap = pipe.find("tmp_changed_rows_keep AS SELECT")
i_restore = pipe.find("INSERT INTO search_changed_rows SELECT k.src_table")
i_drop = pipe.find("DROP TABLE tmp_changed_rows_keep")
t("pipeline: rows snapshot до sync",
  i_sync >= 0 and i_snap >= 0 and i_snap < i_sync)
t("pipeline: rows restore после sync",
  i_sync >= 0 and i_restore > i_sync)
t("pipeline: rows restore дописыванием отсутствующих",
  "WHERE NOT EXISTS (SELECT 1 FROM search_changed_rows r" in pipe)
t("pipeline: rows snapshot снимается (DROP)",
  i_drop > i_restore > 0)

# --- L0-каркас: рубильник пакета объявлен и мёртв (ветвление — этап 1) ---
t("merge: константа partial_rebuild=0",
  "\\set partial_rebuild 0" in merge)
t("merge: константа не читается до этапа 1 (проводки \\if нет)",
  "\\if :partial_rebuild" not in merge)

print("PASS %d FAIL %d" % (PASS, len(FAIL)))
sys.exit(1 if FAIL else 0)
