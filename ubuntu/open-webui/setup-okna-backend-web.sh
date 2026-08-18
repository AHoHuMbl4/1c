#!/bin/bash
# Web-профиль OpenClaw + ask/mcp на бэкенде okna (167.233.249.110 / 10.3.0.4).
# На прод-юните dbname всегда postgres (слот okna-1 → одна СУБД).
# Слушает :18801 для фронта 10.3.0.2. Telegram-профиль undebot не трогаем.
#
# Запуск ОТ ROOT на okna-бэкенде:
#   bash /opt/1c-open-webui/setup-okna-backend-web.sh
#   (или из /srv/1c после rsync)
set -euo pipefail

DBNAME="${DBNAME:-postgres}"
FRONTEND_IP="${FRONTEND_IP:-10.3.0.2}"
GATEWAY_PORT="${GATEWAY_PORT:-18801}"
ASK_PORT="${ASK_PORT:-8091}"
MCP_PORT="${MCP_PORT:-6016}"
BOTUSER="${OPENCLAW_USER:-undebot}"
STATE="/home/$BOTUSER/.openclaw-web"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO="${REPO_ROOT:-$SCRIPT_DIR/../..}"
# если скрипт лежит в /opt/1c-open-webui — репо-файлы рядом
if [ ! -d "$REPO/ubuntu/openclaw" ] && [ -d "$SCRIPT_DIR/../openclaw" ]; then
  REPO="$(cd "$SCRIPT_DIR/.." && pwd)/.."
fi
if [ ! -d "$REPO/ubuntu/openclaw" ]; then
  REPO="$SCRIPT_DIR"
fi

die() { echo "setup-okna-backend-web: $*" >&2; exit 1; }

id "$BOTUSER" >/dev/null 2>&1 || die "юзер $BOTUSER не найден"
[ -f /etc/1c-serene-ask.env ] || die "нет /etc/1c-serene-ask.env"
[ -f /etc/1c-mcp-reports.env ] || die "нет /etc/1c-mcp-reports.env"
[ -x /opt/openclaw-mcp/venv/bin/python ] || die "нет /opt/openclaw-mcp"
[ -f /usr/lib/node_modules/openclaw/dist/index.js ] || die "нет openclaw npm"

# --- symlink openclaw CLI (на эталоне v2 бинаря не было) ---
if [ ! -e /usr/bin/openclaw ]; then
  ln -sf /usr/lib/node_modules/openclaw/openclaw.mjs /usr/bin/openclaw
  chmod +x /usr/lib/node_modules/openclaw/openclaw.mjs
  echo "создан /usr/bin/openclaw"
fi

# --- токены ask/mcp: из профиля undebot, иначе сгенерировать ---
ASK_TOKEN=$(grep -E '^ASK_TOKEN=' /etc/1c-serene-ask.env | cut -d= -f2- | tr -d '\r')
[ -n "$ASK_TOKEN" ] || die "ASK_TOKEN пуст"

MCP_TOKEN=""
if [ -f "/home/$BOTUSER/.openclaw/openclaw.json" ]; then
  MCP_TOKEN=$(python3 - <<PY
import json
c=json.load(open("/home/$BOTUSER/.openclaw/openclaw.json"))
servers=((c.get("mcp") or {}).get("servers") or {})
for s in servers.values():
    h=(s.get("headers") or {}).get("Authorization","")
    if h.startswith("Bearer "):
        print(h.split(" ",1)[1]); break
PY
)
fi
[ -n "$MCP_TOKEN" ] || MCP_TOKEN=$(openssl rand -hex 16)

# --- /etc/1c-serene-ask-postgres.env ---
ASK_ENV="/etc/1c-serene-ask-${DBNAME}.env"
if [ ! -f "$ASK_ENV" ]; then
  cat >"$ASK_ENV" <<EOF
SERENEDB_DSN_RO=host=127.0.0.1 port=7890 user=serene_ro dbname=${DBNAME}
RESOLVER_DSN=host=127.0.0.1 port=7890 user=serene_resolver dbname=${DBNAME}
ASK_LISTEN_PORT=${ASK_PORT}
ASK_SCORER=lm_dirichlet
EOF
  chmod 600 "$ASK_ENV"
  echo "создан $ASK_ENV"
fi

# --- /etc/1c-mcp-ask-postgres.env ---
MCP_ENV="/etc/1c-mcp-ask-${DBNAME}.env"
cat >"$MCP_ENV" <<EOF
ASK_URL=http://127.0.0.1:${ASK_PORT}
ASK_TOKEN=${ASK_TOKEN}
MCP_PORT=${MCP_PORT}
MCP_TOKEN=${MCP_TOKEN}
EOF
chmod 600 "$MCP_ENV"
echo "записан $MCP_ENV"

# --- поднять ask + mcp ---
systemctl enable --now "1c-serene-ask@${DBNAME}.service"
systemctl enable --now "1c-mcp-ask@${DBNAME}.service"
sleep 2
curl -sf -o /dev/null -w "ask_health=%{http_code}\n" "http://127.0.0.1:${ASK_PORT}/health" \
  -H "Authorization: Bearer ${ASK_TOKEN}" || echo "⚠ ask ещё не готов (сборка слоя?)"
curl -sf -o /dev/null -w "mcp_probe=%{http_code}\n" "http://127.0.0.1:${MCP_PORT}/mcp" || true

# --- web-профиль ---
TOKEN_FILE="$STATE/.gateway-token"
install -d -m 700 -o "$BOTUSER" -g "$BOTUSER" "$STATE"/{workspace,logs,agents/main/agent}

if [ -f "$TOKEN_FILE" ]; then
  GW_TOKEN=$(cat "$TOKEN_FILE")
else
  GW_TOKEN=$(openssl rand -hex 32)
  printf '%s' "$GW_TOKEN" >"$TOKEN_FILE"
  chown "$BOTUSER:$BOTUSER" "$TOKEN_FILE"
  chmod 600 "$TOKEN_FILE"
fi

# deepseek: из gateway.systemd.env основного профиля
DEEPSEEK_LINE=""
if [ -f "/home/$BOTUSER/.openclaw/gateway.systemd.env" ]; then
  DEEPSEEK_LINE=$(grep -E '^DEEPSEEK_API_KEY=' "/home/$BOTUSER/.openclaw/gateway.systemd.env" || true)
fi
if [ -n "$DEEPSEEK_LINE" ]; then
  printf '%s\n' "$DEEPSEEK_LINE" >"$STATE/gateway.systemd.env"
  chown "$BOTUSER:$BOTUSER" "$STATE/gateway.systemd.env"
  chmod 600 "$STATE/gateway.systemd.env"
fi
# EMBED_API_KEY — для memory-core (openai-compatible эмбеддер юнита)
EMBED_BASE_URL="${EMBED_BASE_URL:-http://gpu-erw.timpul.pro:8000/v1}"
EMBED_MODEL="${EMBED_MODEL:-Qwen3-Embedding-8B}"
if [ -f /etc/1c-embed.env ]; then
  # shellcheck disable=SC1091
  source /etc/1c-embed.env
  if [ -n "${EMBED_API_KEY:-}" ]; then
    grep -v '^EMBED_API_KEY=' "$STATE/gateway.systemd.env" 2>/dev/null >"$STATE/gateway.systemd.env.tmp" || true
    printf 'EMBED_API_KEY=%s\n' "$EMBED_API_KEY" >>"$STATE/gateway.systemd.env.tmp"
    mv "$STATE/gateway.systemd.env.tmp" "$STATE/gateway.systemd.env"
    chown "$BOTUSER:$BOTUSER" "$STATE/gateway.systemd.env"
    chmod 600 "$STATE/gateway.systemd.env"
  fi
fi

python3 - "$STATE/openclaw.json" "$GATEWAY_PORT" "$GW_TOKEN" "$MCP_PORT" "$MCP_TOKEN" "$STATE" "${EMBED_BASE_URL:-http://gpu-erw.timpul.pro:8000/v1}" "${EMBED_MODEL:-Qwen3-Embedding-8B}" <<'PY'
import json, sys
path, port, token, mcp_port, mcp_token, state, embed_base, embed_model = sys.argv[1:9]
embed_base = embed_base.rstrip("/")
if not embed_base.endswith("/v1"):
  embed_base = embed_base + "/v1"
cfg = {
  "gateway": {
    "port": int(port),
    "bind": "lan",
    "mode": "local",
    "auth": {"mode": "token", "token": token},
    "http": {"endpoints": {"chatCompletions": {"enabled": True}}},
  },
  "session": {"dmScope": "per-channel-peer"},
  "agents": {
    "defaults": {
      "workspace": f"{state}/workspace",
      "model": {"primary": "deepseek/deepseek-v4-flash"},
      "models": {"deepseek/deepseek-v4-flash": {}},
      "thinkingDefault": "off",
      "heartbeat": {"every": "0m"},
      # Смысловой поиск вики (как main-профиль 02.08): без memorySearch
      # провайдер по умолчанию openai без ключа → Memory index failed каждые ~2 мин.
      "memorySearch": {
          "enabled": True,
          "provider": "openai-compatible",
          "model": embed_model,
          "remote": {
              "baseUrl": embed_base,
              "apiKey": "${EMBED_API_KEY}",
              "nonBatchConcurrency": 2,
          },
          "extraPaths": [f"{state}/wiki/main/entities"],
          "fallback": "none",
      },
    }
  },
  "models": {
    "mode": "merge",
    "providers": {
      "deepseek": {
        "baseUrl": "https://api.deepseek.com",
        "api": "openai-completions",
        "models": [{
          "id": "deepseek-v4-flash",
          "name": "DeepSeek V4 Flash",
          "input": ["text"],
          "cost": {"input": 0.14, "output": 0.28, "cacheRead": 0.028, "cacheWrite": 0},
          "contextWindow": 1000000,
          "maxTokens": 8192,
          "api": "openai-completions",
        }],
      }
    },
  },
  "auth": {"profiles": {"deepseek:default": {"provider": "deepseek", "mode": "api_key"}}},
  "commands": {"native": False},
  "plugins": {
    "entries": {
      "deepseek": {"enabled": True},
      "memory-core": {"config": {}},
      # hooks.allowConversationAccess — без него движок БЛОКИРУЕТ типизированные хуки
      # плагина («blocked because non-bundled plugins must set …allowConversationAccess»),
      # то есть гейт числится включённым, а ходы не проверяет. В main-профиле поле
      # стояло, сюда не было перенесено (журнал web-шлюза okna, 13.08).
      "braine-verify": {"enabled": True, "config": {"debug": True, "minDigitsWithRef": 1},
                        "hooks": {"allowConversationAccess": True}},
      # 🔴 ВИКИ НУЖНА ТОМУ ПРОФИЛЮ, КОТОРЫЙ ОТВЕЧАЕТ. Персона идёт сперва в вики —
      # перефразировать вопрос словами базы — и лишь потом зовёт данные. Живой чат
      # клиента 13.08: у web-профиля вики не было вовсе, бот ответил «без вики я не
      # могу определить нужный вид записей» и инструмент данных НЕ ПОЗВАЛ.
      # Хранилище своё, в каталоге этого профиля: такт публикует сюда, получив
      # OPENCLAW_PROFILE_ID=web (см. ниже про env такта).
      "memory-wiki": {
          "enabled": True,
          "config": {
              "vaultMode": "isolated",
              "vault": {"path": f"{state}/wiki/main", "renderMode": "native"},
              "search": {"backend": "shared", "corpus": "all"},
              "context": {"includeCompiledDigestPrompt": False},
              "render": {"preserveHumanBlocks": True, "createBacklinks": True,
                         "createDashboards": True},
              "ingest": {"autoCompile": True, "allowUrlIngest": False},
          },
      },
    },
    "allow": ["deepseek", "braine-verify", "memory-wiki", "memory-core"],
  },
  "logging": {"level": "info", "file": f"{state}/logs/gateway.log"},
  "mcp": {
    "servers": {
      "serene-ask": {
        "url": f"http://127.0.0.1:{mcp_port}/mcp",
        "transport": "streamable-http",
        "toolFilter": {"include": ["ask_1c"]},
        "connectionTimeoutMs": 15000,
        "requestTimeoutMs": 300000,
        "headers": {"Authorization": f"Bearer {mcp_token}"},
      }
    }
  },
  "tools": {"allow": ["message", "bundle-mcp"], "elevated": {"enabled": False}},
}
with open(path, "w", encoding="utf-8") as f:
  json.dump(cfg, f, indent=2, ensure_ascii=False)
  f.write("\n")
PY
chown "$BOTUSER:$BOTUSER" "$STATE/openclaw.json"
chmod 600 "$STATE/openclaw.json"

# персона
if [ -f "$SCRIPT_DIR/AGENTS.md" ]; then
  PERSONA_SRC="$SCRIPT_DIR/AGENTS.md"
elif [ -f "$SCRIPT_DIR/../openclaw/instance/AGENTS.md" ]; then
  PERSONA_SRC="$SCRIPT_DIR/../openclaw/instance/AGENTS.md"
elif [ -f "/home/$BOTUSER/.openclaw/workspace/AGENTS.md" ]; then
  PERSONA_SRC="/home/$BOTUSER/.openclaw/workspace/AGENTS.md"
else
  PERSONA_SRC=""
fi
if [ -n "$PERSONA_SRC" ]; then
  install -m 644 -o "$BOTUSER" -g "$BOTUSER" "$PERSONA_SRC" "$STATE/workspace/AGENTS.md"
  for f in BOOTSTRAP.md SOUL.md IDENTITY.md TOOLS.md USER.md; do
    printf '%s\n' "(не используется — см. AGENTS.md)" >"$STATE/workspace/$f"
    chown "$BOTUSER:$BOTUSER" "$STATE/workspace/$f"
  done
  python3 - "$STATE/workspace/openclaw-workspace-state.json" <<'PY'
import json, sys, datetime
p = sys.argv[1]
d = {"setupCompletedAt": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z")}
json.dump(d, open(p, "w"))
PY
  chown "$BOTUSER:$BOTUSER" "$STATE/workspace/openclaw-workspace-state.json"
fi

# verify-plugin из основного профиля.
# 🔴 КОПИРУЕТСЯ ВЕСЬ NPM-ПРОЕКТ, А НЕ КАТАЛОГ С КОДОМ. Движок держит плагин как проект
# (`npm/projects/<имя>__…/` c `package.json` и `package-lock.json`), и признаёт его
# установленным по проекту, а не по файлам внутри `node_modules`. Прежняя копия брала
# каталог с `verify-core.js`, то есть без `package.json`, — и движок отвечал
# «plugin not found: braine-verify», хотя файлы лежали на месте. Замер okna 13.08:
# у web-профиля гейт ответов числился в настройках и НЕ РАБОТАЛ, то есть числа уходили
# клиенту без проверки опоры.
if ! find "$STATE/npm/projects" -maxdepth 3 -name package.json -path '*braine-verify*' \
     2>/dev/null | grep -q .; then
  SRCMOD=$(find "/home/$BOTUSER/.openclaw" -name verify-core.js -printf '%h\n' 2>/dev/null | head -1)
  # от каталога модуля вверх до корня проекта: <проект>/node_modules/<модуль>
  SRC=$(cd "$SRCMOD/../.." 2>/dev/null && pwd)
  if [ -n "${SRC:-}" ] && [ -f "$SRC/package.json" ]; then
    REL=${SRC#/home/$BOTUSER/.openclaw/}
    DST="$STATE/$REL"
    install -d -m 755 -o "$BOTUSER" -g "$BOTUSER" "$(dirname "$DST")"
    cp -a "$SRC/." "$DST/"
    chown -R "$BOTUSER:$BOTUSER" "$(dirname "$DST")"
    echo "verify-plugin (проект целиком) → $DST"
  else
    echo "⚠ verify-plugin не найден в основном профиле как npm-проект"
  fi
fi

# user-юнит web-гейтвея (как основной: node dist/index.js + profile)
UNIT_DIR="/home/$BOTUSER/.config/systemd/user"
install -d -m 755 -o "$BOTUSER" -g "$BOTUSER" "$UNIT_DIR"
cat >"$UNIT_DIR/openclaw-gateway-web.service" <<EOF
[Unit]
Description=OpenClaw Gateway web-профиль (фронт okna)
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=/usr/bin/node /usr/lib/node_modules/openclaw/dist/index.js --profile web gateway --port ${GATEWAY_PORT}
Restart=always
RestartSec=5
TimeoutStopSec=30
TimeoutStartSec=30
EnvironmentFile=-${STATE}/gateway.systemd.env
Environment=OPENCLAW_SERVICE_MANAGED_ENV_KEYS=DEEPSEEK_API_KEY,EMBED_API_KEY
Environment=HOME=/home/${BOTUSER}
Environment=OPENCLAW_STATE_DIR=${STATE}

[Install]
WantedBy=default.target
EOF
chown "$BOTUSER:$BOTUSER" "$UNIT_DIR/openclaw-gateway-web.service"

loginctl enable-linger "$BOTUSER" >/dev/null 2>&1 || true

if command -v ufw >/dev/null 2>&1; then
  ufw allow from "$FRONTEND_IP" to any port "$GATEWAY_PORT" proto tcp comment "openclaw-web front" >/dev/null 2>&1 || true
fi

UID_BOT=$(id -u "$BOTUSER")
# user bus для undebot
export XDG_RUNTIME_DIR="/run/user/$UID_BOT"
# если runtime ещё нет — создать через loginctl
if [ ! -d "$XDG_RUNTIME_DIR" ]; then
  loginctl enable-linger "$BOTUSER"
  sleep 1
fi
runuser -u "$BOTUSER" -- env XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" systemctl --user daemon-reload
runuser -u "$BOTUSER" -- env XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" systemctl --user enable --now openclaw-gateway-web.service

sleep 3
if curl -sf "http://127.0.0.1:${GATEWAY_PORT}/health" >/dev/null; then
  echo "✅ web-гейтвей :${GATEWAY_PORT} health OK"
else
  echo "⚠ health — journalctl --user -M ${BOTUSER}@ -u openclaw-gateway-web -n 40"
fi

# проверка с ожидаемого bind
ss -tlnp | grep ":${GATEWAY_PORT}" || true

echo ""
echo "=== для фронта (10.3.0.2) ==="
echo "BACKEND_IP=10.3.0.4"
echo "GATEWAY_PORT=${GATEWAY_PORT}"
echo "GATEWAY_TOKEN=${GW_TOKEN}"
