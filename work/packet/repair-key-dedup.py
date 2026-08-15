#!/usr/bin/env python3
"""Пересбор таблиц витрины, обрезанных прежним дедупом по неразличающему ключу.

Работа идёт ВНУТРИ движка: наружу выходят только имена (список колонок из
каталога — путь, который рекомендуют сами доки: звёздочка с отрицанием и
query_table по значению колонки не поддерживаются). Строки не вычитываются и
не заливаются обратно — пересбор это один CREATE OR REPLACE ... AS SELECT.
Помощники берутся из packet_apply, чтобы не заводить второй способ ходить в базу.

Без --apply только показывает план.

Заводился 14.08 под последствия дефекта «объявленный ключ приняли за факт»
(`HOW_NOT_TO §3.73`): дедуп по ключу выбрасывал строки молча. Приёмник исправлен
(дедуп по полной строке), но уже загруженные таблицы этим не лечатся —
пересобираются отсюда. Лечится только то, у чего есть плоская сестра
`..._RecordType` с полными данными: у документов, планов счетов и справочников
её нет, там нужен повторный прочит из 1С (у агента нет ручки «перечитай»: он
молчит по сущности, пока версии в 1С совпадают с его `EntityIndex`, — прочит
запускается удалением индекса в рабочем каталоге агента на Windows).

Живой прогон okna 15.08: 14 таблиц, вернулось 590 955 строк
(`ЦеныНоменклатуры` 301 → 208 317, `РеализацияТМЦ` 8 295 → 77 179).
klient-1 15.08: 44 таблицы, вернулось 2 132 923 строки — каждая ровно в число,
которое прислал агент.

Запуск на юните (DSN передаётся строкой, а НЕ через `. /etc/1c-packet.env`:
там `SERENEDB_DSN=host=… port=… user=…` без кавычек, и bash разбирает это как
четыре отдельных присваивания — переменной достаётся один `host=127.0.0.1`,
psql идёт в 5432 и получает отказ; systemd тот же файл читает верно):

    SERENEDB_DSN='host=127.0.0.1 port=7890 user=postgres dbname=postgres' \\
        python3 repair-key-dedup.py <база> [--apply]
"""
import json
import glob
import os
import sys

sys.path.insert(0, "/opt/1c-packet")
from packet_apply import (safe_col, RO_ROLE, _psql, _psql_scalar,  # noqa: E402
                          _psql_col)

APPLY = "--apply" in sys.argv
BASE = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else "klient-1"

tables = set(_psql_col("SELECT table_name FROM duckdb_tables() "
                       "WHERE database_name = current_database()"))

# Что прислал агент — по манифестам всех пакетов базы.
sent: dict = {}
for p in sorted(glob.glob("/var/lib/1c-packet/inbox/%s/*/manifest.json" % BASE)):
    try:
        m = json.load(open(p, encoding="utf-8"))
    except (OSError, ValueError):
        continue
    pkg = os.path.basename(os.path.dirname(p))
    for e in m.get("entities") or []:
        if e.get("op") in ("full", "full_entity") and isinstance(e.get("rows"), int):
            sent[safe_col(e.get("name", "")).lower()] = (e["rows"], e.get("key") or [], pkg)

print("%-58s %10s %10s %12s" % ("таблица", "прислано", "легло", "потеряно"))
plan, unfixable = [], []
for t in sorted(sent):
    if t not in tables:
        continue
    rows_sent, _key, pkg = sent[t]
    got = int(_psql_scalar('SELECT count(*) FROM "%s"' % t))
    if got >= rows_sent:
        continue
    sib, lost = t + "_recordtype", rows_sent - got
    print("%-58s %10d %10d %8d (%4.1f%%)%s"
          % (t[:58], rows_sent, got, lost, 100.0 * lost / rows_sent,
             "" if sib in tables else "  ← сестры нет, порция " + pkg))
    (plan if sib in tables else unfixable).append((t, sib, rows_sent, got, pkg))

if not plan and not unfixable:
    print("\nпотерь нет — пересобирать нечего")
    sys.exit(0)

print("\n--- пересбор из сестёр _recordtype: %d таблиц" % len(plan))
for t, sib, rows_sent, got, _pkg in plan:
    cols_t = _psql_col("SELECT column_name FROM duckdb_columns() WHERE database_name "
                       "= current_database() AND table_name = '%s' ORDER BY column_index" % t)
    cols_s = set(_psql_col("SELECT column_name FROM duckdb_columns() WHERE database_name "
                           "= current_database() AND table_name = '%s'" % sib))
    missing = [c for c in cols_t if c not in cols_s]
    if missing:
        print("  ПРОПУСК %s: в сестре нет колонок %s" % (t, missing[:5]))
        continue
    n_sib = int(_psql_scalar('SELECT count(*) FROM "%s"' % sib))
    if n_sib < rows_sent:
        print("  ПРОПУСК %s: сестра сама неполна (%d из %d)" % (t, n_sib, rows_sent))
        continue
    if not APPLY:
        print("  ПЛАН %s ← %s (%d колонок, ожидается %d строк)"
              % (t, sib, len(cols_t), n_sib))
        continue
    sel = ", ".join('"%s"' % c for c in cols_t)
    _psql('CREATE OR REPLACE TABLE "%s" AS SELECT DISTINCT %s FROM "%s";\n'
          'GRANT SELECT ON "%s" TO %s;\n' % (t, sel, sib, t, RO_ROLE))
    now = int(_psql_scalar('SELECT count(*) FROM "%s"' % t))
    print("  %s: %d → %d строк (прислано %d) %s"
          % (t, got, now, rows_sent, "ok" if now >= rows_sent else "ВСЁ ЕЩЁ МЕНЬШЕ"))

if unfixable:
    # 🔴 «Сестры нет» НЕ значит «данные потеряны»: сущность приехала своей
    # порцией, и порция лежит на приёмнике целой. Восстановление — переприменить
    # её (пометить пакет verified, откатить last_applied_seq), как делали okna
    # 15.08. Прежний текст звал повторную выгрузку из 1С — и увёл на заход
    # на Windows, которого нет и не будет (docs/PLAN_KEY_DEDUP_RECOVERY.md).
    print("\n--- сестры нет: чинится ПЕРЕПРИМЕНЕНИЕМ порции, она цела на диске: %d"
          % len(unfixable))
    for t, _s, rows_sent, got, pkg in unfixable:
        print("  %s: %d из %d — порция %s" % (t, got, rows_sent, pkg))
    print("  как: пометить эти порции verified и откатить last_applied_seq до "
          "предыдущей — приёмник применит их по порядку заново")
if not APPLY:
    print("\nэто был план. с --apply — пересобрать")
