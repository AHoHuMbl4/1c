#!/usr/bin/env bash
# Идемпотентная настройка витрины SereneDB (Фаза 6 — деплой как код). Ноль ручных шагов:
#   • роли serene_ro (read-only) + serene_resolver (positive control над resolver_index) с ГЕНЕРИРУЕМЫМИ
#     паролями; гранты/ревок; secrets → env (не в git);
#   • затем загрузка витрины (serene_sync: выбранные сущности + пересборка резолвера).
# Параметризовано подключением — переносится на любую 1С-базу. Пароли рутуются при каждом прогоне →
# после setup перезапусти сервисы (reports-MCP), чтобы подхватили новый env.
#
# Запуск (под rw):  bash setup.sh [ENV_FILE] [--load]
#   ENV_FILE  — файл окружения reports (default /etc/1c-mcp-reports.env)
#   --load    — сразу прогнать serene_sync (загрузка + резолвер) после настройки ролей
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENVF="${1:-/etc/1c-mcp-reports.env}"
RW="${SETUP_RW_DSN:-host=127.0.0.1 port=7890 user=postgres}"
RES_DSN="${SETUP_RES_DSN:-host=127.0.0.1 port=7890 user=serene_resolver dbname=postgres}"
RO_DSN="${SETUP_RO_DSN:-host=127.0.0.1 port=7890 user=serene_ro dbname=postgres}"
RO_PW="$(openssl rand -hex 24)"; RES_PW="$(openssl rand -hex 24)"

echo "== роли (идемпотентно) =="
# ВАЖНО: в SereneDB CREATE ROLE существующей роли даёт WARNING + exit 0 (не ошибку), поэтому нельзя
# полагаться на 'CREATE || ALTER' — пароль не применился бы. Делаем CREATE (терпимо) ПОТОМ всегда ALTER
# PASSWORD (он реально меняет — проверено). Так пароль всегда синхронен с env, и для новой, и для старой роли.
role_pw() { psql "$RW" -c "CREATE ROLE $1 LOGIN PASSWORD '$2'" >/dev/null 2>&1 || true; psql "$RW" -c "ALTER ROLE $1 LOGIN PASSWORD '$2'" >/dev/null; }
role_pw serene_ro "$RO_PW"
role_pw serene_resolver "$RES_PW"
psql "$RW" -c "GRANT USAGE ON SCHEMA public TO serene_ro"
psql "$RW" -c "GRANT SELECT ON ALL TABLES IN SCHEMA public TO serene_ro"
psql "$RW" -c "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO serene_ro"
psql "$RW" -c "GRANT USAGE ON SCHEMA public TO serene_resolver"
# resolver_index может ещё не существовать (до первого build) — grant/revoke терпимо
psql "$RW" -c "GRANT SELECT ON resolver_index TO serene_resolver" 2>/dev/null || true
psql "$RW" -c "REVOKE SELECT ON resolver_index FROM serene_ro" 2>/dev/null || true

echo "== секреты -> $ENVF (600, не в git) =="
touch "$ENVF"; chmod 600 "$ENVF"
set_env() { sed -i "\|^$1=|d" "$ENVF"; printf '%s=%s\n' "$1" "$2" >> "$ENVF"; }
set_env PGPASSWORD "$RO_PW"           # reports ходят под serene_ro (PGPASSWORD)
set_env RESOLVER_PW "$RES_PW"
grep -q '^RESOLVER_DSN=' "$ENVF" || printf 'RESOLVER_DSN=%s\n' "$RES_DSN" >> "$ENVF"
grep -q '^SERENEDB_DSN=' "$ENVF"  || printf 'SERENEDB_DSN=%s\n' "$RO_DSN" >> "$ENVF"

echo "== контроль ролей =="
PGPASSWORD="$RO_PW"  psql "$RO_DSN"  -tAc "SELECT 'ro_select_ok', count(*)>=0 FROM duckdb_columns()" 2>&1 | head -1
PGPASSWORD="$RES_PW" psql "$RES_DSN" -tAc "SELECT 'resolver_role_ok', 1" 2>&1 | head -1

if [ "${2:-}" = "--load" ]; then
  echo "== загрузка витрины (serene_sync) =="
  # env грузим БЕЗ source (значения-DSN со пробелами ломают shell-source); DSN ставим явно (rw для загрузки)
  ( export $(grep -E '^(ALIBABA_|ETL_ODATA_BASE|CSV_DIR|EMBED_)' "$ENVF" | xargs -d '\n')
    export SERENEDB_DSN="$RW"; cd "$HERE" && python3 serene_sync.py ) || echo "serene_sync: см. вывод выше"
fi
echo "готово. Роли + секреты настроены. Перезапусти reports-MCP, чтобы подхватить env."
echo "Данные: python3 serene_select.py (дискавери) → отбери бизнес-сущности → serene_sync.py."
