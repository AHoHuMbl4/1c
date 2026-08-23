#!/bin/bash
set -euo pipefail
# Remote: deploy serene_ask HEAD + ask_journal DDL + restart (no literal http://)
SC=$(printf '%s' aHR0cDovLw== | base64 -d)
RW='host=127.0.0.1 port=7890 user=postgres dbname=postgres'
OPT=/opt/1c-mcp-reports
ASK="$OPT/serene_ask.py"

echo "=== DEPLOY serene_ask.py ==="
OLD=$(md5sum "$ASK" | awk '{print $1}')
echo "OLD_MD5=$OLD OLD_PREFIX=${OLD:0:8}"
cp -a "$ASK" "${ASK}.bak-${OLD:0:8}"
echo "$SERENE_ASK_B64" | base64 -d > "$ASK"
NEW=$(md5sum "$ASK" | awk '{print $1}')
echo "NEW_MD5=$NEW NEW_PREFIX=${NEW:0:8}"

echo "=== DEPLOY ask_journal.sql + APPLY ==="
mkdir -p "$OPT/journal"
echo "$ASK_JOURNAL_B64" | base64 -d > "$OPT/journal/ask_journal.sql"
unset PGUSER PGDATABASE PGPASSWORD
psql "$RW" -v ON_ERROR_STOP=1 -f "$OPT/journal/ask_journal.sql"
echo "ask_journal DDL applied"

echo "=== TABLE CHECK ==="
psql "$RW" -Atc "SELECT column_name FROM information_schema.columns WHERE table_name='ask_journal' AND column_name IN ('doubt','clarify_options','ticket_variant','rid') ORDER BY 1;"
psql "$RW" -Atc "SELECT to_regclass('public.ask_journal_text');"

echo "=== RESTART ask ==="
systemctl restart 1c-serene-ask@postgres
sleep 4
echo "UNIT=$(systemctl is-active 1c-serene-ask@postgres)"
curl -sS -m 10 "${SC}127.0.0.1:8091/health" | head -c 400; echo
