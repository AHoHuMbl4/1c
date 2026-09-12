#!/usr/bin/env python3
"""Оффлайн-замок G2: разделитель ' | ', потолок 1600, двойные читатели.

Без базы и сети. Отдельный файл — не раздувать prompts_v2 (G1) и не смешивать
с семантикой meta/title; parse-замок остаётся на инвариантах разбора величин.
"""
from __future__ import annotations

import io
import os
import re
import sys
from contextlib import redirect_stderr
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import wiki_alias_parse as P  # noqa: E402
import entity_rank_v2 as ER  # noqa: E402

PASS, FAIL = 0, []


def t(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + str(detail)[:200]) if detail else "")


# ── _join: разделитель и потолок ─────────────────────────────────────────────
joined = P._join(["а", "б", "в"])
t("_join пишет ' | '", joined == "а | б | в", joined)
t("_join потолок по умолчанию 1600", P._JOIN_CAP == 1600 and P._join.__defaults__[0] == 1600)

# Длинный список: не режется раньше 1600 (элементы по 10 симв. + sep)
items = ["x" * 10 for _ in range(200)]  # 200*10 + 199*3 = 2597 > 1600
long = P._join(items)
t("_join длинный список режется на 1600, не раньше",
  len(long) == 1600 and " | " in long[:50],
  (len(long), long[:40]))
# При потолке 900 старый код обрезал бы раньше — убедимся, что 901-й символ достижим
mid = P._join(["y" * 50] * 20)  # 20*50 + 19*3 = 1057
t("_join >900 символов не режется раньше 1600",
  len(mid) == 1057, len(mid))

# ── валидатор '|': лог + результат ───────────────────────────────────────────
buf = io.StringIO()
with redirect_stderr(buf):
    scrubbed = P._join(["нормальный", "плохой|хвост", "|", "ещё"])
err = buf.getvalue()
t("pipe-валидатор: символ вырезан, элемент сохранён",
  scrubbed == "нормальный | плохойхвост | ещё", scrubbed)
t("pipe-валидатор: голый '|' отброшен",
  " |  | " not in scrubbed and scrubbed.count("|") == 2, scrubbed)
t("pipe-валидатор: лог в stderr",
  "pipe in element stripped" in err and "плохой|хвост" in err, err[:200])

# ── _alias_tokens: оба формата ───────────────────────────────────────────────
t("_alias_tokens: новый ' | '",
  P._alias_tokens("а | б | в") == ["а", "б", "в"])
t("_alias_tokens: старый ', '",
  P._alias_tokens("а, б, в") == ["а", "б", "в"])
t("_alias_tokens: BUF с запятой внутри + pipe",
  P._alias_tokens("взнос работодателя, НДФЛ | другая")
  == ["взнос работодателя, НДФЛ", "другая"])
t("_alias_tokens: список без изменений",
  P._alias_tokens(["а", "б"]) == ["а", "б"])
# дедуп в filter (не в tokens)
got_dedup = P.filter_entity_aliases("клиент | Клиент | товар")
t("_alias_tokens+filter: дедуп после разбора ' | '",
  got_dedup == ["клиент", "товар"], got_dedup)
got_old = P.filter_entity_aliases("клиент, Клиент, товар")
t("_alias_tokens+filter: дедуп после разбора ', '",
  got_old == ["клиент", "товар"], got_old)

# ── потребители: маркеры нового формата + фолбэк ─────────────────────────────
build = (HERE / "wiki_build.sql").read_text(encoding="utf-8")
t("wiki_build: str_split ' | '", "str_split(coalesce(a.aliases, ''), ' | ')" in build)
t("wiki_build: фолбэк ', ' (aliases)",
  "THEN str_split(a.aliases, ', ')" in build
  and "position(', ' IN coalesce(a.aliases, '')) > 0" in build)
# P4: best/nef без ', '-фолбэка — «взнос работодателя, НДФЛ» без ' | ' → 1 элемент
t("wiki_build: best/nef БЕЗ фолбэка ', '",
  "THEN str_split(a.best_used_for, ', ')" not in build
  and "THEN str_split(a.not_enough_for, ', ')" not in build
  and "str_split(coalesce(a.best_used_for, ''), ' | ')" in build
  and "str_split(coalesce(a.not_enough_for, ''), ' | ')" in build)

left = (HERE / "wiki_alias_collision_left.sql").read_text(encoding="utf-8")
t("collision_left: ' | ' + фолбэк ', '",
  "str_split(coalesce(aliases, ''), ' | ')" in left
  and "THEN str_split(aliases, ', ')" in left
  and "position(', ' IN coalesce(aliases, '')) > 0" in left)

round_sql = (HERE / "wiki_alias_collision_round.sql").read_text(encoding="utf-8")
t("collision_round: ' | ' + фолбэк ', '",
  "str_split(coalesce(aliases, ''), ' | ')" in round_sql
  and "THEN str_split(aliases, ', ')" in round_sql
  and "position(', ' IN coalesce(aliases, '')) > 0" in round_sql)

rank = (HERE / "entity_rank_v2.py").read_text(encoding="utf-8")
t("entity_rank_v2: split_part ' | ' + фолбэк",
  "split_part(coalesce(a.aliases, ''), ' | ', 1)" in rank
  and "split_part(a.aliases, ', ', 1)" in rank
  and "position(', ' IN coalesce(a.aliases, '')) > 0" in rank)

# ── entity_rank_v2._alias_parts: dual-разбор мер (G2c / R14) ─────────────────
t("_alias_parts: новый ' | '",
  ER._alias_parts("сумма | итог | всего") == ["сумма", "итог", "всего"])
t("_alias_parts: старый ', '",
  ER._alias_parts("сумма, итог, всего") == ["сумма", "итог", "всего"])
t("_alias_parts: BUF с запятой внутри + pipe",
  ER._alias_parts("взнос работодателя, НДФЛ | другая")
  == ["взнос работодателя, НДФЛ", "другая"])
t("_alias_parts: дедуп casefold",
  ER._alias_parts("Сумма | сумма | ИТОГ") == ["Сумма", "ИТОГ"])
t("_alias_parts: голая ',' (запас)",
  ER._alias_parts("а,б,в") == ["а", "б", "в"])

# ── z14_clarify_memory._alias_parts: dual (G2d) — живой импорт, без БД/env ───
from ask.z14_clarify_memory import _alias_parts as Z14_alias_parts  # noqa: E402
t("z14._alias_parts: новый ' | '",
  Z14_alias_parts("сумма | итог | всего") == ["сумма", "итог", "всего"])
t("z14._alias_parts: старый ', '",
  Z14_alias_parts("сумма, итог, всего") == ["сумма", "итог", "всего"])
t("z14._alias_parts: BUF с запятой внутри + pipe",
  Z14_alias_parts("взнос работодателя, НДФЛ | другая")
  == ["взнос работодателя, НДФЛ", "другая"])
t("z14._alias_parts: дедуп casefold",
  Z14_alias_parts("Сумма | сумма | ИТОГ") == ["Сумма", "ИТОГ"])
t("z14._alias_parts: голая ',' (запас)",
  Z14_alias_parts("а,б,в") == ["а", "б", "в"])
t("z14._alias_parts: список без изменений",
  Z14_alias_parts(["а", "б"]) == ["а", "б"])

reask = (HERE / "wiki_alias_reask_merge_confirmed.sql").read_text(encoding="utf-8")
t("reask append через ' | '",
  "t.aliases || ' | ' || n.aliases" in reask
  and "|| ', '" not in reask)

z02 = (HERE / "ask" / "z02_intent.py").read_text(encoding="utf-8")
t("z02_intent: re.split [,;|/] не трогали",
  're.split(r"[,;|/]"' in z02)

# ── миграционный SQL ─────────────────────────────────────────────────────────
mig = (HERE / "wiki_alias_migrate_sep.sql").read_text(encoding="utf-8")
t("migrate: snap CREATE TABLE … AS SELECT *",
  "CREATE TABLE :alias_snap AS SELECT * FROM :alias_table" in mig
  and "CREATE TABLE :measure_snap AS SELECT * FROM :measure_table" in mig)
t("migrate: replace с условием скобок",
  "replace(aliases, ', ', ' | ')" in mig
  and "regexp_matches(aliases, '\\([^)]*,[^)]*\\)')" in mig
  and "NOT regexp_matches" in mig)
t("migrate: контрольные SELECT по колонкам",
  "entity.aliases replaced" in mig
  and "entity.best_used_for replaced" in mig
  and "entity.not_enough_for replaced" in mig
  and "measure.aliases replaced" in mig
  and "untouched" in mig)
t("migrate: шапка — только по слову владельца",
  "ПО СЛОВУ ВЛАДЕЛЬЦА" in mig
  and "entity_card_build" in mig)

# ── G4: PROBE_TABLE (песочница не марает боевую память столкновений) ─────────
init = (HERE / "wiki_alias_init.sql").read_text(encoding="utf-8")
# DDL-строка probe — переменная, не литерал (CREATE … :probe_table)
ddl_probe = [ln for ln in init.splitlines() if "CREATE TABLE" in ln and "probe" in ln.lower()]
t("init: DDL probe через :probe_table, без литерала search_alias_probe",
  len(ddl_probe) == 1
  and ":probe_table" in ddl_probe[0]
  and "search_alias_probe" not in ddl_probe[0],
  ddl_probe)
t("init: литерал search_alias_probe отсутствует в файле",
  "search_alias_probe" not in init)

t("collision_round: :probe_table в NOT EXISTS и INSERT, литерала нет",
  "FROM :probe_table" in round_sql
  and "INSERT INTO :probe_table" in round_sql
  and "search_alias_probe" not in round_sql)
t("collision_left: :probe_table в NOT EXISTS, литерала нет",
  "FROM :probe_table" in left
  and "search_alias_probe" not in left)

sh = (HERE / "wiki_alias.sh").read_text(encoding="utf-8")
t("wiki_alias.sh: PROBE_TABLE дефолт search_alias_probe",
  'PROBE_TABLE="${PROBE_TABLE:-search_alias_probe}"' in sh)
t("wiki_alias.sh: -v probe_table в psql_wa и psql_wa_tA",
  sh.count('-v probe_table="$PROBE_TABLE"') >= 2)
# collision_left/round зовутся psql_wa_tA — переменная должна быть в обеих обёртках
t("wiki_alias.sh: collision_left через psql_wa_tA (probe_table доезжает)",
  'psql_wa_tA -f "$HERE/wiki_alias_collision_left.sql"' in sh)
# :probe_table только в SQL, которые зовутся через обёртки с -v probe_table
probe_sql_files = [
    HERE / "wiki_alias_init.sql",
    HERE / "wiki_alias_collision_round.sql",
    HERE / "wiki_alias_collision_left.sql",
]
other_sql = [p for p in HERE.glob("wiki_alias*.sql") if p not in probe_sql_files]
t(":probe_table только в init/round/left (остальные SQL без переменной)",
  all(":probe_table" not in p.read_text(encoding="utf-8") for p in other_sql),
  [p.name for p in other_sql if ":probe_table" in p.read_text(encoding="utf-8")])

print()
if FAIL:
    print("ИТОГ: FAIL — %d из %d: %s" % (len(FAIL), len(FAIL) + PASS, "; ".join(FAIL)))
    sys.exit(1)
print("ИТОГ: ok — все %d проверок прошли" % PASS)
