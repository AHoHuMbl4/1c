#!/bin/bash
set -euo pipefail
echo "=== SCORER GOLD CHECK ==="
cd /opt/1c-mcp-reports
ls -la ab-gold*.tsv ab-probe*.tsv 2>/dev/null || true
if ls ab-gold-klient*.tsv 2>/dev/null; then
  echo "GOLD_EXISTS running scorer..."
  AB_CONTOUR=klient1 AB_BASE=postgres ASK_URL=127.0.0.1:8091 python3 ab_scorer.py 2>&1 | tail -30
else
  echo "GOLD_KLIENT1_ABSENT skip scorer"
  head -20 ab_scorer.py
fi
