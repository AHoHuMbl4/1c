#!/bin/bash
set -euo pipefail
set -a
. /etc/1c-embed.env
set +a
export DEEPSEEK_BASE="${DEEPSEEK_BASE:-https://a1f19thc-8000.thundercompute.net}"
export DEEPSEEK_API_KEY="${DEEPSEEK_API_KEY:-$EMBED_API_KEY}"
export DEEPSEEK_MODEL="${DEEPSEEK_MODEL:-Qwen3.8-27B}"
export DEEPSEEK_THINKING=disabled
export ASK_THINKING_OFF_BODY=1
export BENCH_OUT=/srv/1c/work/acceptance/runs/qwen-gates-20260817.json
exec python3 /srv/1c/work/acceptance/qwen_llm_gates.py
