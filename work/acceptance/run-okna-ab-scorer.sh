#!/bin/bash
set -euo pipefail
KEY=~/.ssh/id_ed25519_deploy
HOST=root@167.233.249.110
ssh -o BatchMode=yes -o IdentitiesOnly=yes -i "$KEY" "$HOST" bash -s <<'REMOTE'
set -e
cd /opt/1c-mcp-reports
export ASK_URL=http://127.0.0.1:8091/ask
export AB_BASE=postgres
export AB_SCORERS=bm25
export PROBE_RECORD=/tmp/ab-probe-records.tsv
: > "$PROBE_RECORD"
/opt/openclaw-mcp/venv/bin/python3 /srv/1c/ubuntu/serenedb/ab_scorer.py 2>/dev/null || \
/opt/openclaw-mcp/venv/bin/python3 ab_scorer.py
echo "=== PROBE records (tail) ==="
tail -3 "$PROBE_RECORD" 2>/dev/null || true
REMOTE
