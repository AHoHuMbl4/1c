#!/bin/bash
# Open WebUI + Caddy на openclaw-okna (2.28.49.158 / 10.3.0.2).
# Домен: baulogistic.timpul.pro → этот хост. Бэкенд OpenClaw web — 10.3.0.4:18801.
#
# Запуск ОТ ROOT на фронте:
#   GATEWAY_TOKEN=<из бэкенда> bash /opt/1c-open-webui/setup-okna-front.sh
set -euo pipefail

DOMAIN="${DOMAIN:-baulogistic.timpul.pro}"
BACKEND_IP="${BACKEND_IP:-10.3.0.4}"
GATEWAY_PORT="${GATEWAY_PORT:-18801}"
WEBUSER="${WEBUI_USER:-webui}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="/home/$WEBUSER/open-webui-venv"
DATA="/home/$WEBUSER/open-webui-data"
ENV_FILE="/home/$WEBUSER/.open-webui.env"
OWUI_VER="${OPEN_WEBUI_VERSION:-0.11.0}"

die() { echo "setup-okna-front: $*" >&2; exit 1; }
[ -n "${GATEWAY_TOKEN:-}" ] || die "задайте GATEWAY_TOKEN (вывод setup-okna-backend-web.sh на бэкенде)"

if ! id "$WEBUSER" >/dev/null 2>&1; then
  useradd -m -s /bin/bash "$WEBUSER"
fi
loginctl enable-linger "$WEBUSER" >/dev/null 2>&1 || true

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip curl ca-certificates \
  debian-keyring debian-archive-keyring apt-transport-https gnupg

if ! command -v caddy >/dev/null 2>&1; then
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
    | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
    | tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null
  apt-get update -qq
  apt-get install -y -qq caddy
fi

if [ ! -x "$VENV/bin/open-webui" ]; then
  PY=""
  for c in python3.12 python3; do
    if command -v "$c" >/dev/null 2>&1; then
      ver=$("$c" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
      case "$ver" in 3.11|3.12) PY=$c; break ;; esac
    fi
  done
  if [ -n "$PY" ]; then
    # Ubuntu 24.04: системный 3.12 — обычный venv
    runuser -u "$WEBUSER" -- "$PY" -m venv "$VENV"
    runuser -u "$WEBUSER" -- "$VENV/bin/pip" install -U pip wheel
    runuser -u "$WEBUSER" -- "$VENV/bin/pip" install torch --index-url https://download.pytorch.org/whl/cpu
    runuser -u "$WEBUSER" -- "$VENV/bin/pip" install "open-webui==${OWUI_VER}"
  else
    # Ubuntu 26.04 = 3.14; open-webui требует <3.13 — 3.12 через uv
    runuser -u "$WEBUSER" -- bash -lc "
      set -euo pipefail
      export HOME=/home/$WEBUSER
      export PATH=\$HOME/.local/bin:\$PATH
      export UV_CACHE_DIR=\$HOME/.cache/uv
      unset UV_CONFIG_FILE
      mkdir -p \$HOME/.cache/uv
      command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
      export PATH=\$HOME/.local/bin:\$PATH
      uv python install 3.12
      uv venv \"$VENV\" --python 3.12
      uv pip install --python \"$VENV/bin/python\" torch --index-url https://download.pytorch.org/whl/cpu
      uv pip install --python \"$VENV/bin/python\" \"open-webui==${OWUI_VER}\"
    "
  fi
fi

install -d -m 700 -o "$WEBUSER" -g "$WEBUSER" "$DATA"
cat >"$ENV_FILE" <<EOF
OPENAI_API_KEY=${GATEWAY_TOKEN}
OPENAI_API_BASE_URL=http://${BACKEND_IP}:${GATEWAY_PORT}/v1
ENABLE_OLLAMA_API=false
DATA_DIR=${DATA}
WEBUI_NAME="Ассистент 1С"
ENABLE_VERSION_UPDATE_CHECK=false
EOF
chown "$WEBUSER:$WEBUSER" "$ENV_FILE"
chmod 600 "$ENV_FILE"

# Опционально: STT Whisper (ключ владельца). Файл /etc/1c-open-webui-stt.env:
#   AUDIO_STT_ENGINE=openai
#   AUDIO_STT_MODEL=whisper-large-v3
#   AUDIO_STT_OPENAI_API_BASE_URL=.../v1
#   AUDIO_STT_OPENAI_API_KEY=...
#   AUDIO_STT_OPENAI_API_REQUEST_FORMAT=multipart
#   # WHISPER_LANGUAGE не задавать — иначе язык прибит и UI не выбирает
STT_ENV="${STT_ENV_FILE:-/etc/1c-open-webui-stt.env}"
if [ -f "$STT_ENV" ]; then
  while IFS= read -r line; do
    case "$line" in
      ''|\#*) continue ;;
      AUDIO_STT_*=*|WHISPER_LANGUAGE=*)
        printf '%s\n' "$line" >>"$ENV_FILE"
        ;;
    esac
  done <"$STT_ENV"
  chown "$WEBUSER:$WEBUSER" "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  echo "STT: подмешан из $STT_ENV"
fi

# Скрыть Workspace и селектор моделей в UI (замер 13.08)
if [ -f "$SCRIPT_DIR/static/brand-ui.css" ]; then
  runuser -u "$WEBUSER" -- "$VENV/bin/python" - "$SCRIPT_DIR/static/brand-ui.css" <<'PY'
import open_webui, pathlib, shutil, sys
src = pathlib.Path(sys.argv[1])
dst = pathlib.Path(open_webui.__file__).resolve().parent / "static" / ("custom" + ".css")
shutil.copyfile(src, dst)
print(dst)
PY
fi

install -d -m 755 -o "$WEBUSER" -g "$WEBUSER" "/home/$WEBUSER/.config/systemd/user"
install -m 644 -o "$WEBUSER" -g "$WEBUSER" \
  "$SCRIPT_DIR/systemd/open-webui.service" \
  "/home/$WEBUSER/.config/systemd/user/open-webui.service"

install -m 644 "$SCRIPT_DIR/Caddyfile.okna" /etc/caddy/Caddyfile
sed -i "s|__DOMAIN__|${DOMAIN}|g" /etc/caddy/Caddyfile

UID_WEB=$(id -u "$WEBUSER")
# runtime dir появляется после linger + первого входа в user session
if [ ! -d "/run/user/$UID_WEB" ]; then
  loginctl enable-linger "$WEBUSER"
  # форсируем user manager
  systemctl start "user@$UID_WEB.service" || true
  sleep 2
fi
runuser -u "$WEBUSER" -- env XDG_RUNTIME_DIR="/run/user/$UID_WEB" systemctl --user daemon-reload
runuser -u "$WEBUSER" -- env XDG_RUNTIME_DIR="/run/user/$UID_WEB" systemctl --user enable --now open-webui.service
systemctl enable --now caddy
# Caddy стартует до WebUI — после подъёма :8080 нужен reload, иначе LE не стартует (замер 13.08)
for i in 1 2 3 4 5 6 7 8 9 10; do
  curl -sf -o /dev/null http://127.0.0.1:8080/ && break
  sleep 3
done
systemctl reload caddy || true

sleep 5

if curl -sf -H "Authorization: Bearer ${GATEWAY_TOKEN}" \
    "http://${BACKEND_IP}:${GATEWAY_PORT}/v1/models" | grep -q openclaw; then
  echo "✅ бэкенд /v1/models доступен с фронта"
else
  echo "⚠ бэкенд /v1/models не ответил — ufw на 10.3.0.4 и bind=lan web-гейтвея"
fi

if [ -f "$SCRIPT_DIR/configure-branding.py" ]; then
  sleep 10
  ADMIN_PASS="${ADMIN_PASS:-$(openssl rand -base64 18)}"
  OWUI_URL=http://127.0.0.1:8080 \
    ADMIN_EMAIL="${ADMIN_EMAIL:-admin@okna.local}" \
    ADMIN_PASS="$ADMIN_PASS" \
    OPENAI_API_KEY="$GATEWAY_TOKEN" \
    OPENAI_API_BASE_URL="http://${BACKEND_IP}:${GATEWAY_PORT}/v1" \
    "$VENV/bin/python" "$SCRIPT_DIR/configure-branding.py" || \
    echo "⚠ configure-branding — донастроить вручную (см. OPENCLAW_BOT.md «Брендинг»)"
  echo "Админ: ${ADMIN_EMAIL:-admin@okna.local} пароль: $ADMIN_PASS"
fi

if command -v ufw >/dev/null 2>&1; then
  # 🔴 СНАЧАЛА 22 — иначе enable отрежет SSH (живой случай 13.08 на openclaw-okna)
  ufw allow 22/tcp comment "ssh" >/dev/null 2>&1 || true
  ufw allow 80/tcp comment "okna web http" >/dev/null 2>&1 || true
  ufw allow 443/tcp comment "okna web https" >/dev/null 2>&1 || true
  ufw --force enable >/dev/null 2>&1 || true
fi

if curl -sfI "https://${DOMAIN}/" | head -1 | grep -qE '200|302|307'; then
  echo "✅ https://${DOMAIN}/ отвечает"
else
  echo "⚠ https://${DOMAIN}/ — проверить DNS, caddy: journalctl -u caddy -n 40"
fi

echo "Готово: https://${DOMAIN}/"
