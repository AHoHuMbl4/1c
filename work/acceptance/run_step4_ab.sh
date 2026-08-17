#!/bin/bash
# Usage: run_step4_ab.sh <8099|8098> <out.tsv>
set -euo pipefail
PORT="$1"
OUT="$2"
set -a
. /etc/1c-serene-ask.env
. /etc/1c-serene-ask-ut_test.env
. /etc/1c-mcp-reports.env
. /etc/1c-embed.env
set +a
export SERENEDB_DSN_RO='host=127.0.0.1 port=7890 user=serene_ro dbname=ut_test'
export ASK_URL="http://127.0.0.1:${PORT}"
export DUMP="$OUT"
exec python3 /srv/1c/work/acceptance/step4_bench.py
