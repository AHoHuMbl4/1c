#!/bin/bash
# Сохранить ответ /ask в runs/. Вопрос heredoc-safe; строка PROBE + journal verify.
set -euo pipefail
. "$(dirname "$0")/lib-probe.sh"

KEY=~/.ssh/id_ed25519_deploy
HOST=root@167.233.249.110
PORT="${OKNA_ASK_PORT:-8091}"
Q="${1:?question}"
F="${2:?output filename under runs/}"
RID="$(probe_rid)"
CMD5="$(probe_code_md5 /srv/1c/ubuntu/serenedb/serene_ask.py)"
RUNS=/srv/1c/work/acceptance/runs
RECORD="$RUNS/${F%.json}.probe.tsv"
mkdir -p "$RUNS"

ssh -o BatchMode=yes -o IdentitiesOnly=yes -i "$KEY" "$HOST" "bash -s" <<REMOTE
load_env() {
  for p in /etc/1c-serene-ask.env; do [ -r "\$p" ] || continue
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
  -d "\$PAYLOAD" > /tmp/$F
echo WROTE /tmp/$F \$(wc -c < /tmp/$F)
REMOTE

scp -o BatchMode=yes -o IdentitiesOnly=yes -i "$KEY" "$HOST:/tmp/$F" "$RUNS/$F"

KIND="$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(d.get("kind") or "—")' "$RUNS/$F" 2>/dev/null || echo parse_fail)"
probe_emit "$RID" "$PORT" "$CMD5" "$KIND" "$Q" "$RECORD"

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
import sys
sys.path.insert(0, "/srv/1c/work/acceptance")
import probe_protocol as P
q, rid = sys.argv[1], sys.argv[2]
ok, msg, _ = P.verify_journal(q, rid=rid, wait_sec=1.5)
print(msg)
sys.exit(0 if ok else 1)
PY
"$Q" "$RID"
REMOTE
)" || probe_fail_journal "$VERIFY_OUT"

echo "$VERIFY_OUT" >&2
echo "saved $RUNS/$F probe=$RECORD rid=$RID" >&2
