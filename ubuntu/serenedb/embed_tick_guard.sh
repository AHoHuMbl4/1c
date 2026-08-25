#!/bin/bash
# Защита тактового досчёта: на большом остатке останавливается и называет bulk.
#
# Оценка остатка — дёшево через pg_class.reltuples (как docs/EMBED_ETA_KLIENT1.md):
#   remaining ≈ todo.reltuples − Σ part.reltuples
# Когда todo ещё нет — capped probe (LIMIT порог+1) по лёгкой проекции, без полного left().
#
# Доки: compatibility/system-table-compatibility#system-tables (pg_class 🟢);
#       data_import_and_export/parquet/overview#partial-reading.
#
# Вызов: embed_tick_guard_check <таблица> <метка TAG без _todo/_part>
# Окружение:
#   SERENEDB_DSN
#   EMBED_TICK_MAX_REMAINING  — порог (умолч. 100000)
#   EMBED_ALLOW_LARGE_TICK=1  — явный обход (малая дельта такта / отладка)
# Код возврата: 0 — можно тактом; 2 — остаток велик, звать embed_bulk.sh

embed_tick_guard_check() {
  local tbl="$1" tag="$2"
  local dsn max rem todo_name like_pat sql out

  if [ "${EMBED_ALLOW_LARGE_TICK:-0}" = "1" ]; then
    echo "tick-guard: обход EMBED_ALLOW_LARGE_TICK=1" >&2
    return 0
  fi

  dsn="${SERENEDB_DSN:-host=127.0.0.1 port=7890 user=postgres dbname=postgres}"
  max="${EMBED_TICK_MAX_REMAINING:-100000}"
  todo_name="${tag}_todo"
  like_pat=$(printf '%s' "$tag" | sed 's/[_%]/\\&/g')
  like_pat="${like_pat}\\_part\\_%"

  # 1) Активный/прерванный раунд: todo − parts по reltuples (ETA).
  sql="SELECT CASE
         WHEN NOT EXISTS (
           SELECT 1 FROM pg_class c
           JOIN pg_namespace n ON n.oid = c.relnamespace
           WHERE n.nspname = 'public' AND c.relkind = 'r' AND c.relname = '${todo_name}'
         ) THEN NULL
         ELSE (
           SELECT c.reltuples::bigint FROM pg_class c
           JOIN pg_namespace n ON n.oid = c.relnamespace
           WHERE n.nspname = 'public' AND c.relname = '${todo_name}'
         ) - coalesce((
           SELECT sum(c.reltuples::bigint) FROM pg_class c
           JOIN pg_namespace n ON n.oid = c.relnamespace
           WHERE n.nspname = 'public' AND c.relkind = 'r'
             AND c.relname LIKE '${like_pat}' ESCAPE '\\' AND c.reltuples >= 0
         ), 0)
       END"
  out=$(psql "$dsn" -tAc "$sql" 2>/dev/null | tr -d '[:space:]')
  if [ -n "$out" ] && [ "$out" != "NULL" ]; then
    rem="$out"
  else
    # 2) Todo нет: capped probe — не больше max+1 строк, без полного скана очереди.
    sql="SELECT count(*) FROM (
           SELECT 1 FROM (SELECT 1 AS _ FROM ${tbl} WHERE emb IS NULL LIMIT $((max + 1))) s
         ) t"
    rem=$(psql "$dsn" -tAc "$sql" 2>/dev/null | tr -d '[:space:]')
    [ -n "$rem" ] || rem=""
  fi

  if [ -z "$rem" ]; then
    echo "tick-guard: оценку остатка снять не удалось — такт не начат" >&2
    return 1
  fi

  # Сравнение в awk: rem может быть больше 2^63-1 только теоретически; порог — целое.
  if awk -v r="$rem" -v m="$max" 'BEGIN { exit (r + 0 > m + 0) ? 0 : 1 }'; then
    echo "tick-guard: остаток ≈ ${rem} > порога ${max} — тактовый embed_missing/embed_all" >&2
    echo "tick-guard: для разовой сборки: ubuntu/serenedb/embed_bulk.sh (docs/EMBED_BULK_HOWTO.md §9)" >&2
    echo "tick-guard: обход порога: EMBED_ALLOW_LARGE_TICK=1" >&2
    return 2
  fi

  echo "tick-guard: остаток ≈ ${rem} ≤ порога ${max} — такт" >&2
  return 0
}
