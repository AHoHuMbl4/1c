#!/usr/bin/env bash
# «БОТ ЖИВ» — сторож всего пути ответа. Алерт владельцу в Telegram при падении.
#
# Алерт шлётся НАПРЯМУЮ через bot-токен (минуя OpenClaw) — работает, даже если бот лежит.
# Алертим только на СМЕНУ состояния (ok<->down), без спама. Запуск: systemd-таймер (root).
#
# 🔴 ЗАЧЕМ ПЕРЕПИСАН 02.08. Прежний сторож трое суток не замечал, что бот отдаёт 503 на
# каждый вопрос, а конвейер свежести стоит с 29.07. Причин было пять
# (`F112`, `F014`, `F247`, вопрос `№7`):
#   * он сторожил ВЫВЕДЕННЫЙ контур — в списке стояли `1c-mcp-braine` и `api` (слой braine,
#     снят 26.07), то есть тревожился бы на намеренно погашенное;
#   * и НЕ сторожил путь ответа: ни моста `1c-mcp-ask`, ни отвечающих сервисов, ни шлюзов
#     OData, ни тактов свежести;
#   * `/health` бота не проверялся НИ РАЗУ: адрес лежал в `/etc/1c-bot-monitor.env`, а юнит
#     этот файл не подключал — переменная всегда была пуста, проверка молча пропускалась;
#   * токен уходил в КОМАНДНУЮ СТРОКУ `curl` (виден любому `ps`) — прямое нарушение
#     инварианта проекта «секреты никогда в командной строке»;
#   * состояние записывалось независимо от того, доставлен ли алерт: не ушло сообщение —
#     сторож всё равно считал владельца предупреждённым и больше не повторял.
#
# 🔴 СПИСОК СЕРВИСОВ НЕ ПИШЕТСЯ РУКАМИ. Он выводится из системы: проверяются все НАШИ
# юниты, которые `enabled`, то есть сами объявлены «должны работать всегда». Это снимает
# два дефекта разом: погашенное (`disabled`) не попадает в список ПО ПОСТРОЕНИЮ, а новое
# (ещё один шлюз, ещё одна база) попадает без правки сторожа.
set -u

STATE="${STATE:-/var/lib/1c-bot-monitor/state}"
BOT_USER="${BOT_USER:-undebot}"
TOKEN_FILE="${TOKEN_FILE:-/home/undebot/.openclaw/telegram-token}"
# Кому слать. Умолчания НЕТ намеренно: идентификатор конкретного человека — настройка, а
# не свойство кода. Не задан — сторож говорит об этом в журнал, а не молчит.
OWNER_ID="${OWNER_ID:-}"
# Маска наших юнитов: всё, что ей соответствует и `enabled`, обязано быть `active`.
UNIT_GLOB="${UNIT_GLOB:-1c-*.service}"
# Юниты сверх маски (движок называется иначе).
EXTRA_UNITS="${EXTRA_UNITS:-serenedb.service}"
# Двери, которые обязаны отвечать: процесс бывает жив, а дверь молчит. Формат «имя=URL»
# через пробел. Пусто — проверка пропускается.
HEALTH_URLS="${HEALTH_URLS:-}"
# Свежесть данных (п. 17): предельный возраст последнего такта в минутах, 0 — не следить.
# 🔴 Формат `FRESH_DSNS`: «имя=строка подключения», записи через ТОЧКУ С ЗАПЯТОЙ, а не
# через пробел: в строке подключения libpq пробелы есть всегда (`host=… port=… user=…`),
# и разбор по пробелу разваливает её на куски. [замер 02.08] сторож на этом сразу и
# споткнулся — отчитался «свежесть:port:не-прочитана».
FRESH_MAX_MIN="${FRESH_MAX_MIN:-0}"
FRESH_DSNS="${FRESH_DSNS:-}"
# Такт (firstbuild/pipeline) в failed дольше N минут → токен в алерт.
# 0 — не следить. Умолчание 15: firstbuild на klient-1 простоял 3 дня молча.
TACT_FAIL_MAX_MIN="${TACT_FAIL_MAX_MIN:-15}"
TACT_WATCH="${TACT_WATCH:-/opt/1c-bot-monitor/tact_watch.sh}"
if [ ! -f "$TACT_WATCH" ]; then
  _here="$(cd "$(dirname "$0")" && pwd)"
  [ -f "$_here/tact_watch.sh" ] && TACT_WATCH="$_here/tact_watch.sh"
fi

mkdir -p "$(dirname "$STATE")"
fails=""

# --- 1. бот: user-юнит под своим пользователем --------------------------------
U=$(id -u "$BOT_USER" 2>/dev/null || echo "")
if [ -n "$U" ]; then
  sudo -u "$BOT_USER" XDG_RUNTIME_DIR="/run/user/$U" \
    systemctl --user is-active openclaw-gateway.service >/dev/null 2>&1 \
    || fails="$fails бот-gateway"
else
  fails="$fails нет-пользователя-бота"
fi

# --- 2. наши юниты: `enabled` обязан быть `active` ----------------------------
# 🔴 Источник списка — СИМВОЛЬНЫЕ ССЫЛКИ в `*.target.wants`, а не `list-unit-files`.
# [замер 02.08] `list-unit-files '1c-*.service'` НЕ показывает экземпляры шаблонов —
# то есть пропускает ровно то, чем стали сервисы ответов и шлюзы вторых баз
# (`1c-serene-ask@ut_test`, `1c-odata-gateway@ut`). Сторож, построенный на нём, не
# заметил бы падения именно боевого пути. Ссылка в `wants` — это и есть «объявлено
# запускать при старте», и она есть у экземпляров тоже.
for link in /etc/systemd/system/*.target.wants/*; do
  [ -e "$link" ] || continue
  unit="${link##*/}"
  case "$unit" in *.service) ;; *) continue;; esac        # таймеры проверяются отдельно
  case "$unit" in $UNIT_GLOB) ;; *)
      # не под маской — берём, только если названо явно в EXTRA_UNITS
      case " $EXTRA_UNITS " in *" $unit "*) ;; *) continue;; esac ;;
  esac
  systemctl is-active "$unit" >/dev/null 2>&1 || fails="$fails ${unit%.service}"
done

# Таймеры — отдельно: остановившийся таймер не роняет сервис, но останавливает работу.
# Ровно так 29.07 встал конвейер свежести, и это никто не заметил четверо суток.
for link in /etc/systemd/system/*.target.wants/*.timer; do
  [ -e "$link" ] || continue
  unit="${link##*/}"
  case "$unit" in 1c-*) ;; *) continue;; esac
  systemctl is-active "$unit" >/dev/null 2>&1 || fails="$fails таймер:${unit%.timer}"
done

# --- 3. двери: процесс жив, а отвечает ли ------------------------------------
if [ -n "$HEALTH_URLS" ]; then
  for pair in $HEALTH_URLS; do
    name="${pair%%=*}"; url="${pair#*=}"
    { [ -z "$url" ] || [ "$name" = "$url" ]; } && continue
    curl -fsS -m 8 "$url" >/dev/null 2>&1 || fails="$fails дверь:$name"
  done
fi

# --- 4. свежесть данных (п. 17) ----------------------------------------------
# 🔴 Ровно этого не хватало 29.07: конвейер встал, данные старели четвёртые сутки, и
# увидеть это можно было только заглянув в базу руками.
if [ "${FRESH_MAX_MIN:-0}" -gt 0 ] 2>/dev/null && [ -n "$FRESH_DSNS" ]; then
  while IFS= read -r d; do
    [ -z "$d" ] && continue
    name="${d%%=*}"; dsn="${d#*=}"
    age=$(psql "$dsn" -tAc \
      "SELECT CAST((epoch(now()) - max(v)) / 60 AS BIGINT) FROM search_quality WHERE k = 'build_ts'" \
      2>/dev/null | tr -cd '0-9-')
    if [ -z "$age" ]; then
      fails="$fails свежесть:$name:не-прочитана"
    elif [ "$age" -gt "$FRESH_MAX_MIN" ]; then
      fails="$fails свежесть:$name:${age}мин"
    fi
  done <<< "$(printf '%s' "$FRESH_DSNS" | tr ';' '\n')"
fi

# --- 5. красный такт (firstbuild/pipeline failed дольше N минут) --------------
# oneshot после успеха inactive — это норма; смотрим только failed. Path-юнит
# больше не крутит сервис по кругу (disable сразу + Restart= с пределом).
if [ "${TACT_FAIL_MAX_MIN:-0}" -gt 0 ] 2>/dev/null && [ -f "${TACT_WATCH:-}" ]; then
  # shellcheck disable=SC1090
  . "$TACT_WATCH"
  _tact="$(tact_watch_tokens)"
  [ -n "$_tact" ] && fails="$fails $_tact"
fi

now=$([ -z "$fails" ] && echo "ok" || echo "down:$fails")
prev=$(cat "$STATE" 2>/dev/null || echo "")

# 🔴 ТОКЕН НЕ УХОДИТ В КОМАНДНУЮ СТРОКУ. Прежде он стоял прямо в URL, и его видел любой
# `ps`. `curl --config -` читает и адрес, и данные из stdin — в argv не остаётся ничего.
# Код возврата настоящий: он решает, записывать ли состояние.
alert() {
  local token; token=$(cat "$TOKEN_FILE" 2>/dev/null)
  [ -n "$token" ] || { echo "сторож: нет токена в $TOKEN_FILE" >&2; return 1; }
  [ -n "$OWNER_ID" ] || { echo "сторож: не задан OWNER_ID, слать некому" >&2; return 1; }
  printf 'url = "https://api.telegram.org/bot%s/sendMessage"\ndata-urlencode = "chat_id=%s"\ndata-urlencode = "text=%s"\nsilent\nshow-error\nmax-time = 15\noutput = "/dev/null"\n' \
    "$token" "$OWNER_ID" "$1" | curl --config -
}

if [ "$now" != "$prev" ]; then
  if [ -z "$fails" ]; then
    if [ -n "$prev" ]; then
      # 🔴 Состояние пишется ТОЛЬКО после доставки. Иначе не ушедший алерт означал бы, что
      # сторож считает владельца предупреждённым, и повтора не будет никогда (`F247`).
      alert "✅ Бот 1С снова в строю." && echo "$now" > "$STATE"
    else
      echo "$now" > "$STATE"        # первый запуск: про «ok» не спамим
    fi
  else
    alert "⚠️ Бот 1С: не в порядке —$fails. Проверьте сервер." && echo "$now" > "$STATE"
  fi
fi

# Итог в журнал всегда: по нему видно, что сторож работал, даже когда всё хорошо.
echo "сторож: $now"
