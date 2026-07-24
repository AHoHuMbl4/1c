#!/usr/bin/env bash
# Зонд аналитики под serene_ro (READ-ONLY ролью). Env берём из сервисного файла reports, КРОМЕ
# SERENEDB_DSN: значение со пробелами не переживает shell-source, поэтому ставим ro-DSN явно.
# Использование:  probe.sh "сколько банков в Казани"
set -euo pipefail
cd /opt/1c-mcp-reports
export $(grep -E '^(DEEPSEEK_API_KEY|DEEPSEEK_BASE|ALIBABA_API_KEY|ALIBABA_EMBED_URL|EMBED_MODEL|EMBED_DIM|PGPASSWORD|RESOLVER_PW)=' /etc/1c-mcp-reports.env | xargs -d '\n')
export SERENEDB_DSN='host=127.0.0.1 port=7890 user=serene_ro dbname=postgres'
export RESOLVER_DSN='host=127.0.0.1 port=7890 user=serene_resolver dbname=postgres'  # пробелы — ставим явно
exec /opt/openclaw-mcp/venv/bin/python probe.py "$1"
