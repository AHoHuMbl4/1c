#!/bin/bash
# Сохранить ответ /ask в runs/. PROBE/code_md5 — только из ask_journal.
set -euo pipefail
. "$(dirname "$0")/lib-probe.sh"

KEY=~/.ssh/id_ed25519_deploy
HOST=root@167.233.249.110
PORT="${OKNA_ASK_PORT:-8091}"
Q="${1:?question}"
F="${2:?output filename under runs/}"
RID="$(probe_rid)"
RUNS=/srv/1c/work/acceptance/runs
RECORD="$RUNS/${F%.json}.probe.tsv"
mkdir -p "$RUNS"

ssh -o BatchMode=yes -o IdentitiesOnly=yes -i "$KEY" "$HOST" "bash -s" <<REMOTE
set -euo pipefail
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

JROW=""
if ! JROW="$(probe_ssh_journal_row "$KEY" "$HOST" "$RID" "$Q")"; then
  probe_fail "journal fetch failed (ssh/psql)"
fi
if [[ -z "$JROW" ]]; then
  probe_fail "journal row empty for rid=$RID"
fi

if ! probe_finish "$Q" "$RID" "$PORT" "$KIND" "$JROW" "$RECORD"; then
  probe_fail "journal verify failed rid=$RID"
fi

echo "saved $RUNS/$F probe=$RECORD rid=$RID" >&2
