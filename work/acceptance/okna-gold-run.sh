#!/bin/bash
# Прогон ab-gold-okna на живом okna :8091 (AB_CONTOUR=okna).
set -euo pipefail
KEY=~/.ssh/id_ed25519_deploy
HOST=root@167.233.249.110
RUNS=/srv/1c/work/acceptance/runs
TAG=2026-08-19-okna-gold
mkdir -p "$RUNS"
OUT="$RUNS/${TAG}.txt"

echo "=== sync scorer + tsv ==="
scp -o BatchMode=yes -o IdentitiesOnly=yes -i "$KEY" \
  /srv/1c/ubuntu/serenedb/ab_scorer.py \
  /srv/1c/ubuntu/serenedb/ab-gold-okna.tsv \
  "$HOST:/tmp/"

echo "=== run AB_CONTOUR=okna on okna ==="
ssh -o BatchMode=yes -o IdentitiesOnly=yes -i "$KEY" "$HOST" \
  'cd /srv/1c 2>/dev/null || cd /opt/1c-mcp-reports; \
   ASK_MD5=$(md5sum /opt/1c-mcp-reports/serene_ask.py 2>/dev/null | cut -c1-32 || echo missing); \
   echo "serene_ask.py md5: $ASK_MD5"; \
   AB_CONTOUR=okna AB_MARK_DIR=/srv/1c python3 /tmp/ab_scorer.py' | tee "$OUT"

echo "=== saved $OUT ==="
