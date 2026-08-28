#!/usr/bin/env python3
"""Оффлайн-замок Э1а + С5-пайплайн: wiki_alias — оркестрация psql в .sql.

Запуск: python3 work/pipeline/test_wiki_alias_psql.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SER = os.path.join(ROOT, "ubuntu", "serenedb")
PIPE = os.path.join(ROOT, "work", "pipeline")

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
    "wiki_alias_reask_init.sql",
    "wiki_alias_reask_select_entity_batch.sql",
    "wiki_alias_reask_merge_confirmed.sql",
    "wiki_alias_reask_journal.sql",
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
bs = open(os.path.join(SER, "build.sh"), encoding="utf-8").read()
ent_sql = open(
    os.path.join(SER, "wiki_alias_select_entity_batch.sql"), encoding="utf-8"
).read()
reask_sql = open(
    os.path.join(SER, "wiki_alias_reask_select_entity_batch.sql"), encoding="utf-8"
).read()

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

# (а) cold start: непокрытые раньше покрытых
t(
    "cold start NOT EXISTS uncovered",
    "NOT EXISTS" in ent_sql and "coalesce(a.aliases,'') <> ''" in ent_sql,
)
not_exists_pos = ent_sql.find("NOT EXISTS")
order_pos = ent_sql.rfind("ORDER BY")
t(
    "cold start filter before ORDER BY",
    not_exists_pos >= 0 and order_pos > not_exists_pos,
    "not_exists=%d order=%d" % (not_exists_pos, order_pos),
)

# (б) reask: default off, включён → боковой пул
t("reask default EVERY=0", 'WIKI_ALIAS_REASK_EVERY:-0}' in wa or "REASK_EVERY:-0" in wa)
t("reask gated by tick mod", "WIKI_ALIAS_TICK % REASK_EVERY" in wa)
t("reask side table merge", "wiki_alias_reask_merge_confirmed.sql" in wa)
t("reask pool script", "alias_reask_pool.py" in wa)
t("reask confirm script", "alias_reask_confirm.py" in wa)
t("reask journal sql", "wiki_alias_reask_journal.sql" in wa)
t("reask pool pri=0 journal first", "0 AS pri FROM pool" in reask_sql)
t("build.sh wiki_alias_tick", "wiki_alias_tick" in bs)
t("build.sh exports WIKI_ALIAS_TICK", "export WIKI_ALIAS_TICK" in bs)

# Статика: прямых psql -q/-tA (Э1а helpers + reask-блок С5).
inline_psql = len(re.findall(r'psql\s+"?\$DSN"?\s+-[tq]', wa))
t("inline psql calls <= 8", inline_psql <= 8, "count=%d" % inline_psql)

t("VACUUM REFRESH anchor in sh", "VACUUM (REFRESH_TABLE) $ALIAS_TABLE" in wa)
_bashn_wa = subprocess.run(
    ["bash", "-n", os.path.join(SER, "wiki_alias.sh")], capture_output=True, text=True
)
t("bash -n wiki_alias.sh", _bashn_wa.returncode == 0, _bashn_wa.stderr.strip()[:200])
_bashn_bs = subprocess.run(
    ["bash", "-n", os.path.join(SER, "build.sh")], capture_output=True, text=True
)
t("bash -n build.sh", _bashn_bs.returncode == 0, _bashn_bs.stderr.strip()[:200])
t("stats anchor in sh", "алиасов в базе" in wa)
start = wa.find("# ── §7 / §7bis: подписи веток развилок")
end = wa.find("# ── Ф6.3: Solr-словарь", start)
block = wa[start:end] if start >= 0 and end > start else ""
t("day-basis block preserved", start >= 0 and "wiki_alias_dayfork_batch.sql" in block)

cm = open(os.path.join(SER, "wiki_alias_collision_merge.sql"), encoding="utf-8").read()
t("collision merge uses MERGE", "MERGE INTO" in cm and "UPDATE" not in cm.split("MERGE")[0])

me = open(os.path.join(SER, "wiki_alias_merge_entity.sql"), encoding="utf-8").read()
t("entity merge uses MERGE x2", me.count("MERGE INTO") >= 2)

rm = open(
    os.path.join(SER, "wiki_alias_reask_merge_confirmed.sql"), encoding="utf-8"
).read()
t("reask merge appends not replace", "|| ', ' ||" in rm)

pub = open(os.path.join(SER, "wiki_alias_publish.sql"), encoding="utf-8").read()
t("publish has stats + VACUUM", "алиасов в базе" in pub and "VACUUM (REFRESH_TABLE)" in pub)

# (в) запись в основную таблицу — только после подтверждения (моки)
sys.path.insert(0, PIPE)
spec = importlib.util.spec_from_file_location(
    "alias_reask_confirm", os.path.join(PIPE, "alias_reask_confirm.py")
)
arc = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(arc)

main_aliases = {"catalog_x": {"existing"}}
rows = [{"src_table": "catalog_x", "aliases": "existing, newtok"}]
new_links = []
for row in rows:
    new_links.extend(arc.new_tokens_for_row(row, main_aliases))
t("confirm finds new token only", new_links == [("catalog_x", "newtok")], new_links)

confirmed_path = os.path.join(tempfile.gettempdir(), "reask_conf_test.json")
journal_path = os.path.join(tempfile.gettempdir(), "reask_rej_test.json")

with patch.object(arc, "load_main_aliases", return_value=main_aliases):
    with patch.object(arc, "load_confirm_counts", return_value={}):
        with patch.object(arc, "gold_passes", return_value=False):
            with patch.object(arc, "parse_reask_rows", return_value=rows):
                rc = arc.main(
                    [
                        "--rows-path",
                        "/dev/null",
                        "--confirmed-out",
                        confirmed_path,
                        "--journal-out",
                        journal_path,
                        "--confirm-table",
                        "t_confirm",
                        "--dry-run",
                    ]
                )
t("confirm dry-run rc 0", rc == 0)
rej = json.loads(open(journal_path, encoding="utf-8").read())
conf = json.loads(open(confirmed_path, encoding="utf-8").read())
t("unconfirmed → journal not main", len(rej) == 1 and len(conf) == 0, (rej, conf))

with patch.object(arc, "load_main_aliases", return_value=main_aliases):
    with patch.object(arc, "load_confirm_counts", return_value={}):
        with patch.object(arc, "gold_passes", return_value=True):
            with patch.object(arc, "parse_reask_rows", return_value=rows):
                arc.main(
                    [
                        "--rows-path",
                        "/dev/null",
                        "--confirmed-out",
                        confirmed_path,
                        "--journal-out",
                        journal_path,
                        "--confirm-table",
                        "t_confirm",
                        "--dry-run",
                    ]
                )
conf2 = json.loads(open(confirmed_path, encoding="utf-8").read())
t("gold pass → confirmed out", len(conf2) == 1 and conf2[0]["aliases"] == "newtok")

# alias_reask_pool offline
spec2 = importlib.util.spec_from_file_location(
    "alias_reask_pool", os.path.join(PIPE, "alias_reask_pool.py")
)
arp = importlib.util.module_from_spec(spec2)
assert spec2.loader
spec2.loader.exec_module(arp)
sys.path.insert(0, PIPE)
import alias_candidates as AC  # noqa: E402

jfix = os.path.join(PIPE, "fixtures", "alias_candidates_journal.tsv")
pool_out = os.path.join(tempfile.gettempdir(), "reask_pool_test.json")
pool = arp.build_pool("fake", "search_entity_alias", 30, "7 days", 5, jfix)
t("reask pool from journal fixture", len(pool) >= 1, pool[:3])
arp.write_pool(pool_out, pool)
loaded = json.loads(open(pool_out, encoding="utf-8").read())
t("reask pool json shape", all("t" in x for x in loaded))

print("\nИТОГ: %d/%d" % (PASS, PASS + len(FAIL)))
if FAIL:
    print("FAIL:", ", ".join(FAIL))
    sys.exit(1)
