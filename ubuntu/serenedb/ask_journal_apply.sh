#!/usr/bin/env bash
# Создаёт ask_journal в указанной базе и выдаёт узкий GRANT (INSERT+DELETE
# serene_ro, без SELECT). Пишущая роль — postgres, как у branch_alias.sh.
# Запуск: bash ubuntu/serenedb/ask_journal_apply.sh [dbname]
# DSN: SERENEDB_DSN (rw). dbname из аргумента перекрывает DSN.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
DB="${1:-${ASK_JOURNAL_DB:-}}"
# Пишущая роль. SERENEDB_DSN в reports-env — это serene_ro; им CREATE не сделать.
DSN="${ASK_JOURNAL_RW_DSN:-host=127.0.0.1 port=7890 user=postgres dbname=postgres}"
if [ -n "$DB" ]; then
  if [[ "$DSN" == *"dbname="* ]]; then
    DSN="$(printf '%s\n' "$DSN" | sed -E "s/dbname=[^ ]*/dbname=$DB/")"
  else
    DSN="$DSN dbname=$DB"
  fi
fi
# reports-env задаёт PGUSER=serene_ro и его PGPASSWORD — иначе CREATE SEQUENCE
# = permission denied for schema public (подключение оказывается ro-ролью).
unset PGUSER PGDATABASE PGPASSWORD
psql "$DSN" -v ON_ERROR_STOP=1 -f "$HERE/ask_journal.sql"
echo "ask_journal: применено ($DSN)"
