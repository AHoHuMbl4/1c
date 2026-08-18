#!/bin/bash
# Онбординг слота на юните компании: КОНТУР агента по снимку $metadata.
# Зовётся path-юнитом 1c-serene-onboard@<base>.path, когда приёмник положил
# первый снимок $metadata в packet-meta/<base>/ (приём пакетов сам делается
# apply-таймером, он уже автоматический).
#
# Порядок 10.08 (вариант А): контур ПЕРВЫМ — на чистом юните перепись пуста,
# и packet_config строит бутстреп-контур из снимка $metadata. Сборка слоя сюда
# НЕ входит: до данных сторож «пустой корпус» пайплайна обрывает такт — первую
# сборку и таймер свежести включает 1c-serene-firstbuild@<base> по отметке
# .first-data от apply. Дальше без человека: агент забирает контур своим
# тактом → полная выгрузка демоном → данные → первый билд слоя.
#
# Идемпотентно: метка .onboard-done не даёт перезаписать контур при повторном
# снимке (resync пришлёт meta ещё раз — контур к тому моменту уже с данными).
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

# DSN — из env-файла этой базы движка (его кладёт привязка копии,
# PLAN_PROD_LXC §8.1); ничего о конкретной базе здесь не зашито.
# 🔴 Файл рассчитан на systemd EnvironmentFile, где значение — вся строка после
# «=». Источить его оболочкой (. file) нельзя: DSN содержит пробелы, и шелл
# обрежет значение до первого слова (замер 10.08: psql ушёл на 5432 вместо 7890).
ENV_FILE="/etc/1c-serene-pipeline-$DB.env"
[ -f "$ENV_FILE" ] || { echo "onboard_unit: нет $ENV_FILE — привязка копии не сделана" >&2; exit 1; }
DSN=$(sed -n 's/^SERENEDB_DSN=//p' "$ENV_FILE" | head -1)
[ -n "$DSN" ] || { echo "onboard_unit: в $ENV_FILE нет SERENEDB_DSN" >&2; exit 1; }

REPORTS="${SERENE_REPORTS:-/opt/1c-mcp-reports}"
TUNE="${BOX_TUNE_SH:-$REPORTS/box_tune.sh}"

# Глаз снять сразу — иначе path крутит сервис при падении на EMBED_HOST (17.08).
systemctl disable --now "1c-serene-onboard@$BASE.path" 2>/dev/null || true

if [ -f "$TUNE" ]; then
  # shellcheck disable=SC1090
  . "$TUNE"
  embed_hosts_form_check || { echo "onboard_unit: EMBED_HOST без схемы+порта — стоп" >&2; exit 1; }
  BOX_TUNE_PIPELINE_ENV="$ENV_FILE"
  BOX_TUNE_DSN="${BOX_TUNE_DSN:-$DSN}"
  export BOX_TUNE_PIPELINE_ENV BOX_TUNE_DSN
  box_tune_apply_first_build
fi

if [ -x "$REPORTS/embed_check.sh" ]; then
  "$REPORTS/embed_check.sh" || { echo "onboard_unit: эмбеддер не жив — стоп до контура" >&2; exit 1; }
fi

echo "== контур агента (packet_config $BASE → /etc/1c-packet-bases.json)"
SERENEDB_DSN="$DSN" PACKET_BASES="${PACKET_BASES:-/etc/1c-packet-bases.json}" \
  python3 /opt/1c-packet/packet_config.py "$BASE"

touch "$STAMP"
echo "onboard_unit: контур $BASE записан — агент заберёт его своим тактом;"
echo "  сборку слоя по первым данным включит 1c-serene-firstbuild@$BASE"
