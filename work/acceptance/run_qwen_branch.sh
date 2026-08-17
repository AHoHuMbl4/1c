#!/bin/bash
set -euo pipefail
set -a
. /etc/1c-embed.env
. /etc/1c-mcp-reports.env
. /etc/1c-serene-ask-ut_test.env
set +a
export DEEPSEEK_BASE=https://a1f19thc-8000.thundercompute.net
export DEEPSEEK_API_KEY="$EMBED_API_KEY"
export DEEPSEEK_MODEL=Qwen3.8-27B
export ASK_THINKING_OFF_BODY=1
export SERENEDB_DSN="host=127.0.0.1 port=7890 user=serene_ro dbname=ut_test"
export BENCH_OUT=/srv/1c/work/acceptance/runs/qwen-branch-chunks-20260817.json
exec python3 /srv/1c/work/acceptance/qwen_branch_chunks.py
