#!/bin/bash
# Дамп ответа /ask на okna. Вопрос — heredoc. PROBE/code_md5 — только из ask_journal.
set -euo pipefail
. "$(dirname "$0")/lib-probe.sh"

KEY=~/.ssh/id_ed25519_deploy
HOST=root@167.233.249.110
PORT="${OKNA_ASK_PORT:-8091}"
Q="${*:-на какую сумму мы продали}"
RID="$(probe_rid)"
RUNS="${PROBE_RUNS:-/srv/1c/work/acceptance/runs}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RECORD="$RUNS/probe-${STAMP}-$$.tsv"
mkdir -p "$RUNS"

OUT_LOCAL="$RUNS/dump-${STAMP}-$$.json"
trap 'rm -f "$OUT_LOCAL"' EXIT

echo "=== ask dump port=$PORT rid=$RID q_len=${#Q} ===" >&2

ssh -o BatchMode=yes -o IdentitiesOnly=yes -i "$KEY" "$HOST" "bash -s" <<REMOTE | tee "$OUT_LOCAL" | python3 -m json.tool | head -120
set -euo pipefail
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

JROW=""
if ! JROW="$(probe_ssh_journal_row "$KEY" "$HOST" "$RID")"; then
  probe_fail "journal fetch failed (ssh/psql)"
fi
if [[ -z "$JROW" ]]; then
  probe_fail "journal row empty for rid=$RID"
fi

if ! probe_finish "$Q" "$RID" "$PORT" "$KIND" "$JROW" "$RECORD"; then
  probe_fail "journal verify failed rid=$RID"
fi

echo "=== journal ok rid=$RID record=$RECORD ===" >&2
