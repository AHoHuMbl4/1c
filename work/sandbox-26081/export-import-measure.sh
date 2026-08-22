#!/usr/bin/env bash
# EXPORT → export-test2; IMPORT DATABASE + ручная сверка одной таблицы через COPY.
# Доки: sql/statements/export_and_import_database
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
DSN="${SERENEDB_DSN:-host=127.0.0.1 port=7895 user=postgres dbname=postgres}"
OUT="$ROOT/results/export-import.tsv"
EXP="$ROOT/results/export-test2"
PSQL=(psql "$DSN" -v ON_ERROR_STOP=1)
PROBE="search_entity_alias"
probe_count=$("${PSQL[@]}" -At -c "SELECT count(*) FROM ${PROBE};")

for t in f1_okna f1_cancel500k; do
  "${PSQL[@]}" -q -c "DROP TABLE IF EXISTS ${t};" 2>/dev/null || true
done

if [[ -d "$ROOT/results/export-test" ]]; then
  rm -rf "$ROOT/results/export-test"
fi
if [[ ! -f "$EXP/schema.sql" ]]; then
  rm -rf "$EXP"
  mkdir -p "$EXP"
  err=$("${PSQL[@]}" -q -c "EXPORT DATABASE '${EXP}' (FORMAT csv);" 2>&1) || true
fi

{
  echo "step|result|detail"
  if [[ -f "$EXP/schema.sql" && -f "$EXP/load.sql" ]]; then
    nfiles=$(find "$EXP" -type f | wc -l)
    echo "export|OK|dir=${EXP} nfiles=${nfiles} schema.sql=yes load.sql=yes"
  else
    echo "export|FAIL|${err:-missing files}"
  fi

  imp_err=""
  if [[ -f "$EXP/schema.sql" ]]; then
    "${PSQL[@]}" -q -c "DROP DATABASE IF EXISTS f1_scratch;" 2>/dev/null || true
    if "${PSQL[@]}" -q -c "CREATE DATABASE f1_scratch;" 2>/dev/null; then
      imp_dsn="host=127.0.0.1 port=7895 user=postgres dbname=f1_scratch"
      imp_err=$(psql "$imp_dsn" -v ON_ERROR_STOP=1 -q -c "IMPORT DATABASE '${EXP}';" 2>&1) || true
      if [[ -z "$imp_err" ]]; then
        imp_count=$(psql "$imp_dsn" -At -c "SELECT count(*) FROM ${PROBE};" 2>/dev/null || echo ERR)
        echo "import_full|OK|${PROBE}=${imp_count} expected=${probe_count}"
      else
        echo "import_full|FAIL|$(printf '%s' "$imp_err" | head -1 | tr '|' '/')"
        # ручной путь: одна таблица из load.sql
        csv="$EXP/public_search_entity_alias.csv"
        if [[ -n "$csv" ]]; then
          psql "$imp_dsn" -q -c "DROP TABLE IF EXISTS ${PROBE};" 2>/dev/null || true
          psql "$imp_dsn" -q -c "
            CREATE TABLE public.${PROBE}(
              src_table VARCHAR, aliases VARCHAR, best_used_for VARCHAR,
              not_enough_for VARCHAR, seen_at TIMESTAMP);" 2>/dev/null || true
          copy_err=$(psql "$imp_dsn" -v ON_ERROR_STOP=1 -q -c \
            "COPY public.${PROBE} FROM '${csv}' (FORMAT csv, DELIMITER ',', HEADER true, QUOTE '\"');" 2>&1) || true
          if [[ -z "$copy_err" ]]; then
            imp_count=$(psql "$imp_dsn" -At -c "SELECT count(*) FROM ${PROBE};" 2>/dev/null || echo ERR)
            match=$([[ "$imp_count" == "$probe_count" ]] && echo yes || echo NO)
            echo "import_copy_one|OK|${PROBE}=${imp_count} expected=${probe_count} match=${match} csv=$(basename "$csv")"
          else
            echo "import_copy_one|FAIL|$(printf '%s' "$copy_err" | head -1 | tr '|' '/')"
          fi
        fi
      fi
    else
      echo "import_full|FAIL|CREATE DATABASE f1_scratch failed"
    fi
  fi
} | tee "$OUT"
