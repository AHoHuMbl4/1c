#!/bin/bash
# ЗАВЕСТИ ТАКТ СВЕЖЕСТИ ДЛЯ БАЗЫ, У КОТОРОЙ ЕГО НЕТ.
#
# Повод `[замер 06.08]`: сторож бота прислал «свежесть:первая:1641мин». Он был прав, и это
# не потеря связи: у ПЕРВОЙ базы такта не было никогда. Экземпляр
# `1c-serene-pipeline@postgres` ни разу не запускался (журнал пуст), таймера для неё нет, а
# главное — нет побазового файла `/etc/1c-serene-pipeline-postgres.env`, без которого
# экземпляр не стартует вовсе: в юните он подключён БЕЗ знака «-», то есть обязателен.
# Последняя сборка корпуса первой базы — 05.08 04:38.
#
# 🔴 ЗАПУСКАЕТ ВЛАДЕЛЕЦ: файл ложится в `/etc`, сессии туда писать нельзя. Значения
# копируются НА СЕРВЕРЕ из уже существующего `/etc/1c-serene-sync.env` — ни один секрет не
# проходит через командную строку и не показывается в выводе.
#
# Использование:  sudo bash work/pipeline/install-base-tact.sh postgres
#                 sudo bash work/pipeline/install-base-tact.sh <база> [файл-образец]
set -eu

BASE="${1:?укажите имя базы движка, например: postgres}"
SRC="${2:-/etc/1c-serene-sync.env}"
DST="/etc/1c-serene-pipeline-${BASE}.env"

[ "$(id -u)" = 0 ] || { echo "нужны права root: файл ложится в /etc" >&2; exit 1; }
[ -r "$SRC" ] || { echo "нет образца $SRC — укажите его вторым доводом" >&2; exit 1; }

if [ -e "$DST" ]; then
  echo "$DST уже есть — не трогаю. Проверьте его и включите таймер вручную:"
  echo "  systemctl enable --now 1c-serene-pipeline@${BASE}.timer"
  exit 0
fi

# 🔴 ИМЯ БАЗЫ В DSN — ЯВНО. Без него libpq подставит базу по умолчанию, и такт вместе с
# деньгами эмбеддера уйдёт не туда, не дав ни одной ошибки (`MAP.md`, разбор про dbname).
umask 077
{
  grep -E '^(ETL_ODATA_BASE|ODG_GATEWAY_TOKEN|CSV_DIR|SERENE_SRC_DIR)=' "$SRC" || true
  dsn=$(grep -E '^SERENEDB_DSN=' "$SRC" | head -1 | cut -d= -f2-)
  case "$dsn" in
    *dbname=*) printf 'SERENEDB_DSN=%s\n' "$dsn" ;;
    *)         printf 'SERENEDB_DSN=%s dbname=%s\n' "$dsn" "$BASE" ;;
  esac
} > "$DST"

chown root:1c-secrets "$DST" 2>/dev/null || chown root:root "$DST"
chmod 640 "$DST"

echo "заведён $DST:"
sed -E 's/(ODG_GATEWAY_TOKEN|PGPASSWORD)=.*/\1=***/' "$DST" | sed 's/^/    /'

# Проверки ДО запуска: без них таймер включится, а такт будет падать молча.
gate=$(grep -E '^ETL_ODATA_BASE=' "$DST" | cut -d= -f2-)
if ! curl -s -o /dev/null -m 20 -w '' "$gate/\$metadata" 2>/dev/null; then
  echo "⚠ шлюз $gate не ответил — такт включаю, но проверьте его" >&2
fi

systemctl enable --now "1c-serene-pipeline@${BASE}.timer"
systemctl list-timers --all "1c-serene-pipeline@${BASE}.timer" --no-pager | head -3
echo
echo "ход первого такта:  journalctl -u 1c-serene-pipeline@${BASE}.service -f"
