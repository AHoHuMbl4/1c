#!/bin/sh
# Онбординг слота на юните компании: витрина → контур агента → таймер свежести.
# Зовётся path-юнитом 1c-serene-onboard@<base>.path, когда приёмник положил
# первый снимок $metadata в packet-meta/<base>/ (приём пакетов сам делается
# apply-таймером, он уже автоматический). Дальше цепочка идёт без человека:
#   build.sh по снимку строит витрину → packet_config пишет контур в bases.json
#   → агент забирает список сущностей своим тактом → полная выгрузка демоном
#   → pipeline-таймер держит слой свежим.
# Идемпотентно: метка .onboard-done не даёт пересобрать при повторном снимке
# (resync пришлёт meta ещё раз — за это отвечает уже pipeline-таймер).
#
#   onboard_unit.sh <base_id> [pipeline_db=postgres]
set -eu

BASE="${1:-}"
DB="${2:-postgres}"
case "$BASE" in
  ""|*[!a-z0-9_-]*) echo "onboard_unit: недопустимый base_id «$BASE»" >&2; exit 2 ;;
esac
case "$DB" in
  ""|*[!a-z0-9_-]*) echo "onboard_unit: недопустимый db «$DB»" >&2; exit 2 ;;
esac

BASE_DIR="/var/lib/serenedb/packet-meta/$BASE"
SNAP="$BASE_DIR/\$metadata"
STAMP="$BASE_DIR/.onboard-done"

if [ -f "$STAMP" ]; then
  echo "onboard_unit: слот $BASE уже настроен (метка $STAMP) — ничего не делаю"
  exit 0
fi
[ -f "$SNAP" ] || { echo "onboard_unit: нет снимка $SNAP — рано" >&2; exit 1; }

# DSN и каталоги — из env-файла этой базы движка (его кладёт привязка копии,
# PLAN_PROD_LXC §8.1); ничего о конкретной базе здесь не зашито.
ENV_FILE="/etc/1c-serene-pipeline-$DB.env"
[ -f "$ENV_FILE" ] || { echo "onboard_unit: нет $ENV_FILE — привязка копии не сделана" >&2; exit 1; }
set -a; . "$ENV_FILE"; set +a

echo "== витрина слоя по снимку \$metadata (1c-serene-pipeline@$DB)"
systemctl start "1c-serene-pipeline@$DB.service"

echo "== контур агента (packet_config $BASE → /etc/1c-packet-bases.json)"
PACKET_BASES="${PACKET_BASES:-/etc/1c-packet-bases.json}" \
  python3 /opt/1c-packet/packet_config.py "$BASE"

echo "== таймер свежести (1c-serene-pipeline@$DB.timer)"
systemctl enable --now "1c-serene-pipeline@$DB.timer"

touch "$STAMP"
echo "onboard_unit: слот $BASE настроен — дальше агент сам заберёт контур и начнёт полную выгрузку"
