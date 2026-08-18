#!/bin/bash
# Первая сборка поискового слоя на юните — по отметке .first-data от apply
# (path-юнит 1c-serene-firstbuild@<base>.path). До первых данных такт пайплайна
# обрывается штатным сторожем «после такта корпус ПУСТ» — поэтому слой собирается
# по сигналу «данные применены», а не по снимку $metadata (порядок 10.08).
#
#   firstbuild_unit.sh <base_id> [pipeline_db=postgres]
set -eu

BASE="${1:-}"
DB="${2:-postgres}"
case "$BASE" in
  ""|*[!a-z0-9_-]*) echo "firstbuild_unit: недопустимый base_id «$BASE»" >&2; exit 2 ;;
esac
case "$DB" in
  ""|*[!a-z0-9_-]*) echo "firstbuild_unit: недопустимый db «$DB»" >&2; exit 2 ;;
esac

BASE_DIR="/var/lib/serenedb/packet-meta/$BASE"
[ -f "$BASE_DIR/.first-data" ] || { echo "firstbuild_unit: нет отметки .first-data — рано" >&2; exit 1; }

ENV_FILE="/etc/1c-serene-pipeline-$DB.env"
[ -f "$ENV_FILE" ] || { echo "firstbuild_unit: нет $ENV_FILE — привязка копии не сделана" >&2; exit 1; }

REPORTS="${SERENE_REPORTS:-/opt/1c-mcp-reports}"
TUNE="${BOX_TUNE_SH:-$REPORTS/box_tune.sh}"

# Глаз снять СРАЗУ: иначе при падении path снова стартует сервис за секунды
# («Start request repeated too quickly», firstbuild 14–17.08). Повтор — Restart=
# юнита (5 раз / час), не path.
systemctl disable --now "1c-serene-firstbuild@$BASE.path" 2>/dev/null || true

if [ -f "$TUNE" ]; then
  # shellcheck disable=SC1090
  . "$TUNE"
  embed_hosts_form_check || { echo "firstbuild_unit: EMBED_HOST без схемы+порта — стоп до такта" >&2; exit 1; }
  BOX_TUNE_PIPELINE_ENV="$ENV_FILE"
  BOX_TUNE_DSN="${BOX_TUNE_DSN:-$(sed -n 's/^SERENEDB_DSN=//p' "$ENV_FILE" | head -1)}"
  export BOX_TUNE_PIPELINE_ENV BOX_TUNE_DSN
  box_tune_apply_first_build
  box_tune_disk_preflight || { echo "firstbuild_unit: диск не держит первую сборку/слияние — стоп (E4b)" >&2; exit 1; }
fi

if [ -x "$REPORTS/embed_check.sh" ]; then
  "$REPORTS/embed_check.sh" || { echo "firstbuild_unit: эмбеддер не жив — стоп до такта" >&2; exit 1; }
fi

echo "== первая сборка слоя (1c-serene-pipeline@$DB)"
systemctl start "1c-serene-pipeline@$DB.service"

if [ -f "$TUNE" ]; then
  # shellcheck disable=SC1090
  . "$TUNE"
  box_tune_restore || echo "firstbuild_unit: возврат memory_limit/swap не удался — ручки первой сборки остаются (PLAN_KEY_DEDUP_RECOVERY §0)" >&2
fi

echo "== таймер свежести (1c-serene-pipeline@$DB.timer)"
systemctl enable --now "1c-serene-pipeline@$DB.timer"

echo "firstbuild_unit: слой собран, таймер свежести включён — контур $BASE в бою"
