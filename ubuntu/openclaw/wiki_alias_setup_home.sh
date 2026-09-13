#!/bin/bash
# Установка генераторного openclaw-HOME для wiki-alias (песочница / новая база).
#
# Usage:
#   WIKI_LLM_API_KEY=<ключ> \
#     wiki_alias_setup_home.sh <OPENCLAW_HOME> <base_url> <model_id> \
#       [agent_id=dict] [owner]
#
# Пример:
#   WIKI_LLM_API_KEY=<из /etc или песочницы> \
#     ./wiki_alias_setup_home.sh /home/undebot/.openclaw-sandbox \
#       https://openrouter.ai/api/v1 qwen/qwen3.8-27b dict undebot
#
# Скрипт НЕ запускает генерацию и НЕ трогает чужие HOME — только указанный
# OPENCLAW_HOME. Боевой ~/.openclaw не патчится (для боя — ensure_vllm_gateway.sh).
#
# ─── Ловушки ночи 12–13.09 (G7-checklist §2) ───
# 1. maxTokens 12288 на модели провайдера (models.providers.vllm.models[].maxTokens),
#    не только в agents.defaults.models[].params — иначе local/agent режет JSON.
# 2. enable_thinking:false через params.chat_template_kwargs — иначе Qwen жжёт
#    весь лимит на рассуждения; --thinking off на infer-local для не-Claude
#    нормализуется в undefined (G0).
# 3. OPENCLAW_HOME = домашний каталог, НЕ каталог .openclaw; путь только
#    абсолютный (/*). Подставить относительный или путь к state → OpenClaw
#    ищет ещё один вложенный .openclaw.
# 4. apiKey только из env WIKI_LLM_API_KEY — секреты не в argv (правило проекта).
# 5. Gateway в этом HOME нет — генератор идёт agent --local, шлюз не нужен.
# 6. [owner] — необязательный 5-й argv: после создания chown -R owner: HOME
#    (прогон под undebot). Без аргумента владельца не трогаем.
#
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
TEMPLATE="${HERE}/wiki-alias-home-template.json"

usage() {
  echo "Usage: WIKI_LLM_API_KEY=<key> $0 <OPENCLAW_HOME> <base_url> <model_id> [agent_id=dict] [owner]" >&2
  echo "  apiKey — только из env WIKI_LLM_API_KEY (не argv)." >&2
  echo "  OPENCLAW_HOME — абсолютный путь (/*); owner — необязательный chown после создания." >&2
  exit 2
}

[ "$#" -ge 3 ] && [ "$#" -le 5 ] || usage

OPENCLAW_HOME="$1"
BASE_URL="$2"
MODEL_ID="$3"
AGENT_ID="${4:-dict}"
OWNER="${5:-}"

# Маркер: apiKey НЕ из argv — только WIKI_LLM_API_KEY.
API_KEY="${WIKI_LLM_API_KEY:-}"
if [ -z "$API_KEY" ]; then
  echo "wiki_alias_setup_home: нет WIKI_LLM_API_KEY в окружении" >&2
  exit 1
fi

# Guard: только абсолютный OPENCLAW_HOME (ловушка двойного .openclaw).
case "$OPENCLAW_HOME" in
  /*) ;;
  *)
    echo "wiki_alias_setup_home: OPENCLAW_HOME должен быть абсолютным путём (/*), не '$OPENCLAW_HOME' — иначе двойной .openclaw" >&2
    exit 1
    ;;
esac

if [ ! -f "$TEMPLATE" ]; then
  echo "wiki_alias_setup_home: нет шаблона $TEMPLATE" >&2
  exit 1
fi

# OPENCLAW_HOME — дом. каталог; state = $OPENCLAW_HOME/.openclaw
STATE_DIR="${OPENCLAW_HOME}/.openclaw"
CFG="${STATE_DIR}/openclaw.json"
WS="${STATE_DIR}/workspace"

mkdir -p "$WS"
chmod 700 "$OPENCLAW_HOME"

if [ -f "$CFG" ]; then
  BAK="${CFG}.bak-$(date +%Y%m%d-%H%M%S)"
  cp -a "$CFG" "$BAK"
  echo "wiki_alias_setup_home: прежний конфиг → $BAK"
fi

# sed-подстановка плейсхолдеров шаблона (включая workspace из OPENCLAW_HOME).
# Разделитель sed — | ; значения URL/ключей могут содержать /.
TMP_CFG="$(mktemp)"
trap 'rm -f "$TMP_CFG"' EXIT

# Экранирование & \ и разделителя | для sed replacement.
_sed_esc() {
  printf '%s' "$1" | sed -e 's/[\\|&]/\\&/g'
}

sed \
  -e "s|@@WIKI_LLM_BASE_URL@@|$(_sed_esc "$BASE_URL")|g" \
  -e "s|@@WIKI_LLM_API_KEY@@|$(_sed_esc "$API_KEY")|g" \
  -e "s|@@WIKI_LLM_MODEL_ID@@|$(_sed_esc "$MODEL_ID")|g" \
  -e "s|@@WIKI_ALIAS_AGENT_ID@@|$(_sed_esc "$AGENT_ID")|g" \
  -e "s|@@OPENCLAW_WORKSPACE@@|$(_sed_esc "$WS")|g" \
  "$TEMPLATE" > "$TMP_CFG"

# Быстрая проверка: JSON валиден и плейсхолдеры не остались.
python3 -c '
import json, sys
p = sys.argv[1]
raw = open(p, encoding="utf-8").read()
if "@@" in raw:
    raise SystemExit("wiki_alias_setup_home: остались плейсхолдеры @@…@@")
json.load(open(p, encoding="utf-8"))
' "$TMP_CFG"

install -m 600 "$TMP_CFG" "$CFG"
chmod 600 "$CFG"
chmod 700 "$OPENCLAW_HOME"

# Маркер chown: только при 5-м аргументе [owner]; без него — не трогаем владельца.
if [ -n "$OWNER" ]; then
  chown -R "${OWNER}:" "$OPENCLAW_HOME"
  echo "wiki_alias_setup_home: owner → ${OWNER}:"
fi

echo "wiki_alias_setup_home: конфиг → $CFG"
echo "wiki_alias_setup_home: workspace → $WS"
echo "wiki_alias_setup_home: model=vllm/${MODEL_ID} agent=${AGENT_ID} maxTokens=12288 (провайдер+params)"
