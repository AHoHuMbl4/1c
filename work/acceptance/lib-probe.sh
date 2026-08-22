#!/usr/bin/env bash
# Общая обёртка протокола замера проб. source из приборов work/acceptance/*.sh
set -euo pipefail

PROBE_LIB_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROBE_PY="$PROBE_LIB_ROOT/probe_protocol.py"

probe_rid() {
  echo "probe-$(date -u +%Y%m%dT%H%M%SZ)-$$"
}

# Читает строку ask_journal на удалённом хосте (psql). rid — норма как в сервисе;
# если по rid пусто — fallback по q_hash вопроса.
# Печатает: q_len|q_hash|outcome|rid|code_md5
probe_ssh_journal_row() {
  local key="$1" host="$2" rid="$3" question="$4"
  local norm qhash
  norm="$(python3 "$PROBE_PY" rid-norm "$rid")"
  qhash="$(python3 -c 'import hashlib,sys; print(hashlib.sha256(sys.argv[1].encode("utf-8")).hexdigest())' "$question")"
  ssh -o BatchMode=yes -o IdentitiesOnly=yes -i "$key" "$host" "bash -s" <<REMOTE
set -euo pipefail
load_env() {
  for p in /etc/1c-mcp-reports.env /etc/1c-serene-ask-postgres.env; do
    [ -r "\$p" ] || continue
    while IFS= read -r line || [ -n "\$line" ]; do
      line="\${line%%#*}"; [[ "\$line" != *=* ]] && continue
      export "\${line%%=*}=\${line#*=}"
    done < "\$p"
  done
}
load_env
unset PGUSER PGDATABASE
DSN="\${ASK_JOURNAL_RW_DSN:-host=127.0.0.1 port=7890 user=postgres dbname=postgres}"
sleep 1.5
ROW=\$(psql "\$DSN" -tA -c "SELECT q_len, q_hash, outcome, rid, coalesce(code_md5, '') FROM ask_journal WHERE rid = '${norm}' ORDER BY id DESC LIMIT 1")
if [ -z "\$ROW" ]; then
  ROW=\$(psql "\$DSN" -tA -c "SELECT q_len, q_hash, outcome, rid, coalesce(code_md5, '') FROM ask_journal WHERE q_hash = '${qhash}' ORDER BY id DESC LIMIT 1")
fi
if [ -z "\$ROW" ]; then
  echo "journal not found rid_norm=${norm}" >&2
  exit 1
fi
echo "\$ROW"
REMOTE
}

# Сверка + PROBE-строка локально; code_md5 только из journal_row. exit 1 при провале.
probe_finish() {
  local question="$1" rid="$2" port="$3" outcome="$4" journal_row="$5" record="${6:-}"
  python3 "$PROBE_PY" finish \
    --rid "$rid" --port "$port" --outcome "$outcome" \
    --journal-row "$journal_row" \
    ${record:+--record "$record"} \
    "$question"
}

probe_fail() {
  echo "🔴 PROBE INVALID: $*" >&2
  exit 1
}
