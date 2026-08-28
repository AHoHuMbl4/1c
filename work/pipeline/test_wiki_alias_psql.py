#!/usr/bin/env python3
"""Оффлайн-замок Э1а: wiki_alias — оркестрация psql в .sql, не веер -c.

Запуск: python3 work/pipeline/test_wiki_alias_psql.py
"""
from __future__ import annotations

import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SER = os.path.join(ROOT, "ubuntu", "serenedb")

PASS = 0
FAIL: list[str] = []

SQL_FILES = [
    "wiki_alias_init.sql",
    "wiki_alias_select_entity_batch.sql",
    "wiki_alias_select_measure_batch.sql",
    "wiki_alias_mark_skip.sql",
    "wiki_alias_mark_measure_skip.sql",
    "wiki_alias_merge_entity.sql",
    "wiki_alias_merge_measures.sql",
    "wiki_alias_collision_round.sql",
    "wiki_alias_collision_merge.sql",
    "wiki_alias_collision_left.sql",
    "wiki_alias_publish.sql",
    "wiki_alias_fork_init.sql",
    "wiki_alias_dayfork_batch.sql",
    "wiki_alias_dayfork_mark.sql",
    "wiki_alias_dayfork_merge.sql",
]


def t(name: str, cond: bool, detail: str = "") -> None:
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + detail[:200]) if detail else "")


wa = open(os.path.join(SER, "wiki_alias.sh"), encoding="utf-8").read()

for fn in SQL_FILES:
    path = os.path.join(SER, fn)
    t("sql file exists: " + fn, os.path.isfile(path), path)
    if os.path.isfile(path):
        body = open(path, encoding="utf-8").read()
        t(fn + " ON_ERROR_STOP", "\\set ON_ERROR_STOP on" in body, fn)

t("wiki_alias uses psql_wa helper", "psql_wa()" in wa)
t("init via -f wiki_alias_init.sql", "wiki_alias_init.sql" in wa)
t("publish via -f wiki_alias_publish.sql", "wiki_alias_publish.sql" in wa)
t("entity batch via -f", "wiki_alias_select_entity_batch.sql" in wa)
t("merge entity via MERGE sql", "wiki_alias_merge_entity.sql" in wa)
t("collision round combined", "wiki_alias_collision_round.sql" in wa)
t("dayfork batch combined", "wiki_alias_dayfork_batch.sql" in wa)

# Статика: меньше прямых psql -c/-tAc с SQL-текстом (остаются count и solr python).
inline_psql = len(re.findall(r'psql\s+"?\$DSN"?\s+-[tq]', wa))
t("inline psql calls <= 3", inline_psql <= 3, "count=%d" % inline_psql)

# D3 / day-basis якоря для соседних замков (test_inverted_index_guard, test_fork_label_daybasis).
t("VACUUM REFRESH anchor in sh",
  "VACUUM (REFRESH_TABLE) $ALIAS_TABLE" in wa)
# Снайпер 28.08: перенос `\` с висячим комментарием ломал bash-синтаксис,
# а текстовый якорь выше оставался зелёным — держим bash -n как замок.
import subprocess  # noqa: E402
_bashn = subprocess.run(["bash", "-n", os.path.join(SER, "wiki_alias.sh")],
                        capture_output=True, text=True)
t("bash -n wiki_alias.sh (синтаксис переноса)", _bashn.returncode == 0,
  _bashn.stderr.strip()[:200])
t("stats anchor in sh", "алиасов в базе" in wa)
start = wa.find("# ── §7 / §7bis: подписи веток развилок")
end = wa.find("# ── Ф6.3: Solr-словарь", start)
block = wa[start:end] if start >= 0 and end > start else ""
t("day-basis block preserved", start >= 0 and "wiki_alias_dayfork_batch.sql" in block)

# MERGE в sql, не UPDATE для collision
cm = open(os.path.join(SER, "wiki_alias_collision_merge.sql"), encoding="utf-8").read()
t("collision merge uses MERGE", "MERGE INTO" in cm and "UPDATE" not in cm.split("MERGE")[0])

me = open(os.path.join(SER, "wiki_alias_merge_entity.sql"), encoding="utf-8").read()
t("entity merge uses MERGE x2", me.count("MERGE INTO") >= 2)

pub = open(os.path.join(SER, "wiki_alias_publish.sql"), encoding="utf-8").read()
t("publish has stats + VACUUM", "алиасов в базе" in pub and "VACUUM (REFRESH_TABLE)" in pub)

print("\nИТОГ: %d/%d" % (PASS, PASS + len(FAIL)))
if FAIL:
    print("FAIL:", ", ".join(FAIL))
    raise SystemExit(1)
