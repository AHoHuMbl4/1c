#!/usr/bin/env bash
# Ground-truth SELECT под serene_ro (READ-ONLY; запись роль физически отвергнет). Для сверки ответов
# зонда с фактами. Имя таблицы — из ВАШЕЙ витрины (список: sql.sh "SELECT table_name FROM duckdb_tables()").
# Использование:  sql.sh "SELECT count(DISTINCT ref_key) FROM <таблица_витрины> WHERE <колонка>='<значение>'"
set -euo pipefail
export $(grep -E '^PGPASSWORD=' /etc/1c-mcp-reports.env | xargs -d '\n')
exec psql 'host=127.0.0.1 port=7890 user=serene_ro dbname=postgres' -tA -c "$1"
