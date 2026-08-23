#!/bin/bash
# Ф4: перевести /etc/1c-embed.env dev на канон 4B (23.08). Хосты — ВНЕШНИЕ IP (dev не видит vSwitch 10.3.1.x — владелец, 23.08).
# Root-only. Секреты (KEY/TOKEN/PASS) не меняет. Юниты НЕ перезапускает.
set -euo pipefail

ENV_FILE=/etc/1c-embed.env
TS=$(date +%Y%m%d-%H%M%S)
BAK="${ENV_FILE}.bak-${TS}"

# dev до GPU ходит только по ВНЕШНИМ адресам (vSwitch 10.3.1.x с dev недоступен — владелец, 23.08).
# Порты те же, что в каноне: embed 8000/8002, health 8001, rerank 8005.
H11=178.63.211.188
H12=49.13.97.101

die() { echo "ERROR: $*" >&2; exit 1; }

[[ $(id -u) -eq 0 ]] || die "запускать от root"
[[ -r "$ENV_FILE" && -w "$ENV_FILE" ]] || die "${ENV_FILE} недоступен для записи"

mask_pipe_val() {
  local v="$1"
  if [[ "$v" == *"|"* ]]; then
    local k="${v##*|}"
    printf '%s|***%s' "${v%%|*}" "${k: -4}"
  else
    printf '%s' "$v"
  fi
}

get_val() {
  grep -E "^${1}=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"' || true
}

set_kv() {
  local key="$1" val="$2"
  if grep -qE "^${key}=" "$ENV_FILE"; then
    sed -i "s#^${key}=.*#${key}=${val}#" "$ENV_FILE"
  else
    echo "${key}=${val}" >> "$ENV_FILE"
  fi
}

# --- бэкап ---
cp -a "$ENV_FILE" "$BAK"
echo "Бэкап: ${BAK}"

# --- ключ из существующего EMBED_HOSTS (не печатать) ---
EMBED_KEY=$(get_val EMBED_HOSTS | sed 's/.*|//; s/,.*//')
if [[ -z "$EMBED_KEY" ]]; then
  EMBED_KEY=$(get_val EMBED_API_KEY)
fi
[[ -n "$EMBED_KEY" ]] || die "не найден ключ в EMBED_HOSTS / EMBED_API_KEY — правка вручную"

NEW_HOSTS="http://${H11}:8000|${EMBED_KEY},http://${H12}:8002|${EMBED_KEY}"

# --- канон (docs/NETWORK.md §2.1, CHANGELOG 23.08) ---
declare -A WANT=(
  [EMBED_MODEL]=Qwen3-Embedding-4B
  [EMBED_DIM]=1024
  [EMBED_HOSTS]="${NEW_HOSTS}"
  [EMBED_BASE_URL]="http://${H11}:8000"
  [EMBED_HOST]="http://${H11}:8000"
  [EMBED_HEALTH_URL]="http://${H11}:8001/health"
  [RERANK_URL]="http://${H11}:8005/rerank"
  [EMBED_BATCH_CHARS]=60000
)

echo "=== замены (секреты маскированы) ==="
for key in "${!WANT[@]}"; do
  old=$(get_val "$key")
  new="${WANT[$key]}"
  if [[ "$old" == "$new" ]]; then
    echo "${key}: без изменений"
  else
    echo "${key}:"
    echo "  было: $(mask_pipe_val "$old")"
    echo "  стало: $(mask_pipe_val "$new")"
    set_kv "$key" "$new"
  fi
done

# --- верификация: все ключи на месте, секреты не тронуты ---
echo ""
echo "=== верификация ключей ==="
for key in EMBED_MODEL EMBED_DIM EMBED_HOSTS EMBED_BASE_URL EMBED_HOST \
           EMBED_HEALTH_URL RERANK_URL EMBED_BATCH_CHARS \
           EMBED_API_KEY EMBED_API_KEYS RERANK_API_KEY; do
  if grep -qE "^${key}=" "$ENV_FILE"; then
    echo "  OK  ${key}"
  else
    echo "  --  ${key} (нет в файле)"
  fi
done

model=$(get_val EMBED_MODEL)
dim=$(get_val EMBED_DIM)
[[ "$model" == "Qwen3-Embedding-4B" ]] || die "EMBED_MODEL != 4B после правки"
[[ "$dim" == "1024" ]] || die "EMBED_DIM != 1024 после правки"

echo ""
echo "Готово. Юниты НЕ перезапущены — см. 00-README.md §1 (список systemctl restart)."
