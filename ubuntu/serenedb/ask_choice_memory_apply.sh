#!/usr/bin/env bash
# Создаёт ask_choice_memory в указанной базе и выдаёт гранты serene_ro
# (INSERT+SELECT+UPDATE; без DELETE). Пишущая роль — postgres, как у ask_journal.
# Запуск: bash ubuntu/serenedb/ask_choice_memory_apply.sh [dbname]
# DSN: ASK_JOURNAL_RW_DSN / SERENEDB_DSN (rw). dbname из аргумента перекрывает DSN.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
DB="${1:-${ASK_CHOICE_MEMORY_DB:-}}"
DSN="${ASK_JOURNAL_RW_DSN:-host=127.0.0.1 port=7890 user=postgres dbname=postgres}"
if [ -n "$DB" ]; then
  if [[ "$DSN" == *"dbname="* ]]; then
    DSN="$(printf '%s\n' "$DSN" | sed -E "s/dbname=[^ ]*/dbname=$DB/")"
  else
    DSN="$DSN dbname=$DB"
  fi
fi
unset PGUSER PGDATABASE PGPASSWORD
psql "$DSN" -v ON_ERROR_STOP=1 -f "$HERE/ask_choice_memory.sql"
echo "ask_choice_memory: применено ($DSN)"
