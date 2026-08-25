#!/usr/bin/env python3
"""Оффлайн-замок замера коллизий памяти (PLAN_ANSWER_CONTRACT §8 шаг 6).

Проверяет ask_choice_memory_collisions_measure.sql и определение коллизии
в ask_choice_mem.py: поля class_key / chosen_* / active, без имён сущностей
конкретной базы. Без сети и без живой БД.

Запуск: python3 ubuntu/serenedb/test_memory_collisions_measure.py
"""
import ast
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SQL_PATH = os.path.join(HERE, "ask_choice_memory_collisions_measure.sql")
MEM_PATH = os.path.join(HERE, "ask_choice_mem.py")

PASS, FAIL = 0, []


def t(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + str(detail)[:200]) if detail else "")


sql = open(SQL_PATH, encoding="utf-8").read()
mem_src = open(MEM_PATH, encoding="utf-8").read()

# --- SQL разбирается как набор SELECT (без DDL/DML записи) ---
stripped = re.sub(r"--[^\n]*", "\n", sql)
stmts = [s.strip() for s in stripped.split(";") if s.strip()]
t("sql: есть запросы", len(stmts) >= 4, len(stmts))
t("sql: только SELECT/WITH",
  all(re.match(r"(?is)^(WITH|SELECT)\b", s) for s in stmts),
  stmts[:1])
t("sql: нет INSERT/UPDATE/DELETE",
  not re.search(r"(?i)\b(INSERT|UPDATE|DELETE|DROP|TRUNCATE)\b", stripped))

# --- коллизия выражена полями, не именами конфигурации ---
need = ("ask_choice_memory", "class_key", "chosen_src", "chosen_measure",
        "chosen_axis", "user_hash", "active", "cancelled", "n_branches")
for col in need:
    t("sql поле: " + col, col in sql)

t("sql: порог коллизии n_branches >= 2",
  "n_branches >= 2" in sql or "HAVING count(*) >= 2" in sql)
t("sql: распределение по n_branches",
  "n_branches, count(*) AS n_classes" in sql
  or "n_branches, count(*) as n_classes" in sql.lower())

# --- без привязки к конкретной базе (имена сущностей 1С / хосты) ---
banned = (
    "document_", "catalog_", "accumulationregister_", "informationregister_",
    "accountingregister_", "okna", "ut_test", "klient", "gpu-erw",
    "167.233", "7890", "8091", "8092",
)
low = sql.lower()
hit = [b for b in banned if b.lower() in low]
t("sql: нет имён сущностей/хостов базы", hit == [], hit)

# --- определение коллизии в коде: поля, не проза конфигурации ---
tree = ast.parse(mem_src)
fn = None
for node in tree.body:
    if isinstance(node, ast.FunctionDef) and node.name == "_memory_collisions":
        fn = node
        break
t("код: есть _memory_collisions", fn is not None)
fn_src = ast.get_source_segment(mem_src, fn) if fn else ""
t("код коллизии: GROUP BY chosen_src/measure/axis",
  "chosen_src" in fn_src and "chosen_measure" in fn_src
  and "chosen_axis" in fn_src and "GROUP BY" in fn_src)
t("код коллизии: порог len(branches) < 2",
  "len(branches) < 2" in fn_src)
t("код коллизии: n_branches в ответе",
  "n_branches" in fn_src)

ck = None
for node in tree.body:
    if isinstance(node, ast.FunctionDef) and node.name == "choice_class_key":
        ck = node
        break
ck_src = ast.get_source_segment(mem_src, ck) if ck else ""
t("класс: readings + measure + window",
  "measure_ctx" in ck_src and "window_fp" in ck_src)
t("класс: выбранный src в ключ не входит",
  "chosen" not in ck_src.lower())

# --- журнал: замер помечает «не посчитано» для apply (тело, не комментарии) ---
t("sql: journal контекст без выдуманного apply",
  "ask_journal" in stripped
  and "would_apply" not in stripped
  and "from_memory" not in stripped)

print()
if FAIL:
    print("FAIL %d; ok %d" % (len(FAIL), PASS))
    sys.exit(1)
print("OK %d/%d" % (PASS, PASS))
