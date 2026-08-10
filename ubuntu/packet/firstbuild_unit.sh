#!/bin/sh
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

echo "== первая сборка слоя (1c-serene-pipeline@$DB)"
systemctl start "1c-serene-pipeline@$DB.service"

echo "== таймер свежести (1c-serene-pipeline@$DB.timer)"
systemctl enable --now "1c-serene-pipeline@$DB.timer"

# Глаз снят: отметка .first-data остаётся, без отключения path-юнит гонял бы
# сервис по кругу (замер 10.08).
systemctl disable --now "1c-serene-firstbuild@$BASE.path" 2>/dev/null || true
echo "firstbuild_unit: слой собран, таймер свежести включён — контур $BASE в бою"
