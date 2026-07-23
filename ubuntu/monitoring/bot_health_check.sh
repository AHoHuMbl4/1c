#!/usr/bin/env bash
# «Бот жив» — проверка ключевых сервисов бота и алерт владельцу в Telegram при падении.
# Алерт шлётся НАПРЯМУЮ через bot-токен (минуя OpenClaw) — работает даже если gateway лежит.
# Алертим только на СМЕНУ состояния (ok<->down), без спама. Запуск: systemd-таймер (root).
set -u

OWNER_ID="${OWNER_ID:-5949699699}"                 # кому слать (Telegram id владельца)
TOKEN_FILE="${TOKEN_FILE:-/home/undebot/.openclaw/telegram-token}"
STATE="${STATE:-/var/lib/1c-bot-monitor/state}"
BOT_USER="${BOT_USER:-undebot}"
SYS_SERVICES="${SYS_SERVICES:-serenedb 1c-mcp-braine 1c-mcp-reports api}"  # системные сервисы

mkdir -p "$(dirname "$STATE")"
U=$(id -u "$BOT_USER" 2>/dev/null || echo "")

fails=""
# gateway — user-сервис под ботом
if [ -n "$U" ]; then
  sudo -u "$BOT_USER" XDG_RUNTIME_DIR="/run/user/$U" systemctl --user is-active openclaw-gateway.service >/dev/null 2>&1 \
    || fails="$fails gateway"
else
  fails="$fails no-bot-user"
fi
# системные сервисы, от которых зависит бот
for s in $SYS_SERVICES; do
  systemctl is-active "$s.service" >/dev/null 2>&1 || fails="$fails $s"
done

now=$([ -z "$fails" ] && echo "ok" || echo "down:$fails")
prev=$(cat "$STATE" 2>/dev/null || echo "")

alert() {
  local token; token=$(cat "$TOKEN_FILE" 2>/dev/null)
  [ -n "$token" ] && curl -s -o /dev/null --max-time 15 \
    "https://api.telegram.org/bot${token}/sendMessage" \
    --data-urlencode "chat_id=${OWNER_ID}" --data-urlencode "text=$1" || true
}

# Алерт только при смене состояния (первый запуск с пустым prev не спамит про «ok»)
if [ "$now" != "$prev" ]; then
  if [ -z "$fails" ]; then
    [ -n "$prev" ] && alert "✅ Бот 1С снова в строю."
  else
    alert "⚠️ Бот 1С: не работают сервисы —$fails. Проверьте сервер."
  fi
  echo "$now" > "$STATE"
fi
