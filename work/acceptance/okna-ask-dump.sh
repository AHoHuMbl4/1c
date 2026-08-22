#!/bin/bash
# Дамп ответа /ask на okna. Вопрос — heredoc (многословный цел), не аргумент ssh.
# После замера: самопроверка q_len/q_hash в ask_journal (postgres DSN).
set -euo pipefail
. "$(dirname "$0")/lib-probe.sh"

KEY=~/.ssh/id_ed25519_deploy
HOST=root@167.233.249.110
PORT="${OKNA_ASK_PORT:-8091}"
Q="${*:-на какую сумму мы продали}"
RID="$(probe_rid)"
CMD5="$(probe_code_md5 /srv/1c/ubuntu/serenedb/serene_ask.py)"
RUNS="${PROBE_RUNS:-/srv/1c/work/acceptance/runs}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RECORD="$RUNS/probe-${STAMP}-$$.tsv"
mkdir -p "$RUNS"

OUT_LOCAL="$RUNS/dump-${STAMP}-$$.json"
trap 'rm -f "$OUT_LOCAL"' EXIT

echo "=== ask dump port=$PORT rid=$RID q_len=${#Q} ===" >&2

ssh -o BatchMode=yes -o IdentitiesOnly=yes -i "$KEY" "$HOST" "bash -s" <<REMOTE | tee "$OUT_LOCAL" | python3 -m json.tool | head -120
load_env() {
  for p in /etc/1c-serene-ask.env /etc/1c-mcp-reports.env /etc/1c-serene-ask-postgres.env; do
    [ -r "\$p" ] || continue
    while IFS= read -r line || [ -n "\$line" ]; do
      line="\${line%%#*}"; [[ "\$line" != *=* ]] && continue
      export "\${line%%=*}=\${line#*=}"
    done < "\$p"
  done
}
load_env
PAYLOAD=\$(python3 -c 'import json,sys; print(json.dumps({"question": sys.argv[1], "rid": sys.argv[2]}))' "$Q" "$RID")
curl -sS -m 180 -X POST "http://127.0.0.1:${PORT}/ask" \\
  -H "Content-Type: application/json" -H "Authorization: Bearer \$ASK_TOKEN" \\
  -d "\$PAYLOAD"
REMOTE

KIND="$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(d.get("kind") or "—")' "$OUT_LOCAL" 2>/dev/null || echo parse_fail)"
probe_emit "$RID" "$PORT" "$CMD5" "$KIND" "$Q" "$RECORD"

# journal: postgres может читать q_hash/q_len (serene_ro — нет)
VERIFY_OUT="$(ssh -o BatchMode=yes -o IdentitiesOnly=yes -i "$KEY" "$HOST" "bash -s" <<REMOTE
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
export PROBE_JOURNAL_DSN="\${ASK_JOURNAL_RW_DSN:-host=127.0.0.1 port=7890 user=postgres dbname=postgres}"
python3 - <<'PY'
import os, sys
sys.path.insert(0, "/srv/1c/work/acceptance")
import probe_protocol as P
q = sys.argv[1]
rid = sys.argv[2]
ok, msg, meta = P.verify_journal(q, rid=rid, wait_sec=1.5)
print(msg)
if not ok:
    sys.exit(1)
PY
"$Q" "$RID"
REMOTE
)" || probe_fail_journal "$VERIFY_OUT"

echo "$VERIFY_OUT" >&2
echo "=== journal ok rid=$RID record=$RECORD ===" >&2
