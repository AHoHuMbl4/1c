#!/usr/bin/env bash
# Read-only прогон И0 на prod okna. Не рестартует сервисы.
set -euo pipefail
KEY="${KEY:-$HOME/.ssh/id_ed25519_deploy}"
HOST="${HOST:-root@gpu-erw.timpul.pro}"
PORT="${PORT:-2202}"
REPO="${REPO:-/srv/1c}"
REMOTE_REPO="${REMOTE_REPO:-/opt/1c-mcp-reports}"

ssh -i "$KEY" -p "$PORT" -o BatchMode=yes -o StrictHostKeyChecking=no "$HOST" \
  "REPO='$REMOTE_REPO'" bash -s <<'EOF'
set -euo pipefail
set -a
. /etc/1c-mcp-reports.env
set +a
DSN="${SERENEDB_DSN:-host=127.0.0.1 port=7890 user=postgres dbname=postgres}"
cd "$REPO"
PY="$REPO/work/gold/client_gold.py"
test -f "$PY" || { echo "client_gold.py not found in $REPO"; exit 1; }
python3 "$PY" --dsn "$DSN" build \
  --slices work/gold/slices-okna-packet.json \
  --from-journal --limit-journal 40 \
  --limit-templates 30 \
  --out /tmp/client-gold-okna-live.tsv \
  --discrepancy-log /tmp/client-gold-discrepancies.tsv
wc -l /tmp/client-gold-okna-live.tsv
echo "--- discrepancies (head) ---"
head -20 /tmp/client-gold-discrepancies.tsv 2>/dev/null || true
EOF
