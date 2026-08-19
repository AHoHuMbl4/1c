#!/usr/bin/env bash
# Перед выкатом: smoke-прогон золотого набора ut_test (0 сбоев обращения).
# После выката на okna: приёмка AB_CONTOUR=okna (числа + kind) — см. REGRESSION_BASE1 §0.
# Отметку smoke ставит AB_GOLD_MODE=smoke → .claude/.golden-last-run (префикс smoke).
# touch этого файла гейт не предлагает.
set -uo pipefail

. "$(dirname "${BASH_SOURCE[0]}")/lib-hooks.sh"
CMD=$(hook_command)
is_deploy "$CMD" || { echo '{}'; exit 0; }

cd_repo || { hook_ask "Хук $(basename "$0") не определил каталог репозитория и ничего не проверил. Подтвердите шаг вручную."; exit 0; }

MARK=".claude/.golden-last-run"
SRC_DIRS="ubuntu/serenedb ubuntu/openclaw ubuntu/1c-gateway ubuntu/1c-etl ubuntu/1c-config-ui"

NEWEST=$(find $SRC_DIRS -type f \( -name '*.py' -o -name '*.js' -o -name '*.mjs' \) \
         -newer "$MARK" 2>/dev/null | head -5)

golden_smoke_mark_ok() {
  [ -f "$MARK" ] || return 1
  read -r line _ < "$MARK" 2>/dev/null || return 1
  [[ "$line" == smoke\ * ]] && [[ "$line" == *0err/* ]]
}

if [ ! -f "$MARK" ]; then
  WHY="Золотой smoke ut_test ни разу не прогонялся после появления этой проверки.
Выкат без замера — это то самое «сначала на боевой, потом посмотрим»."
elif ! golden_smoke_mark_ok; then
  WHY="Отметка .golden-last-run есть, но это не smoke-прогон ut_test (нужен префикс smoke … 0err/N).
ДО выката — только smoke: 0 сбоев обращения, порог верных не ставится.
После выката на okna — приёмка AB_CONTOUR=okna (числа), см. REGRESSION_BASE1 §0."
elif [ -n "$NEWEST" ]; then
  WHY="Исходники правились ПОСЛЕ последнего smoke-прогона:
$(printf '%s\n' "$NEWEST" | sed 's/^/  /')
Последний smoke: $(date -r "$MARK" '+%Y-%m-%d %H:%M' 2>/dev/null)"
else
  echo '{}'; exit 0
fi

# 0 жив, 1 нет, 2 неизвестно (нет URL — строка коммита этот случай не закрывает).
golden_embedder_status() {
  local url="" body
  if [ -n "${GOLDEN_EMBED_HEALTH:-}" ]; then
    url="$GOLDEN_EMBED_HEALTH"
  elif [ -r /etc/1c-embed.env ]; then
    url="$(awk -F= '/^EMBED_HEALTH_URL=/{
      v=$0; sub(/^[^=]+=/, "", v)
      gsub(/^["\047]|["\047]$/, "", v)
      print v; exit
    }' /etc/1c-embed.env)"
  fi
  [ -n "$url" ] || return 2
  body="$(curl -sS -m 5 -- "$url" 2>/dev/null)" || return 1
  printf '%s' "$body" | python3 -c '
import json, sys
raw = sys.stdin.read()
if "Nothing running here" in raw:
    raise SystemExit(1)
try:
    d = json.loads(raw)
except Exception:
    raise SystemExit(1)
if d.get("model"):
    raise SystemExit(0)
w = d.get("workers")
if isinstance(w, list) and w:
    raise SystemExit(0)
raise SystemExit(1)
'
}

RUN_HELP="Smoke ДО выката (0 сбоев, порог верных не нужен):
  AB_GOLD_MODE=smoke AB_BASE=ut_test ASK_URL=http://127.0.0.1:8099/ask python3 ubuntu/serenedb/ab_scorer.py
Приёмка ПОСЛЕ выката на okna (числа + kind склад):
  AB_CONTOUR=okna python3 ubuntu/serenedb/ab_scorer.py
Отметку ставит только состоявшийся прогон, не touch."

emb=0
golden_embedder_status || emb=$?

if [ "$emb" = 1 ]; then
  NOTE="$(git log -1 --format=%B 2>/dev/null | grep -im1 -E '^[[:space:]]*золотой[[:space:]]*:[[:space:]]*невозможен')"
  if [ -n "$NOTE" ]; then
    hook_log "check-golden" "пропуск: эмбеддер не отвечает, в HEAD есть пометка"
    echo '{}'; exit 0
  fi
  WHY="Золотой набор невозможен: эмбеддер не отвечает.
Прогон сейчас гейт не закроет. В коммите (HEAD) нужна строка:
  Золотой: невозможен — эмбеддер недоступен
После этого повтори выкат. Люк не нужен.

$WHY

$RUN_HELP"
elif [ "$emb" = 2 ]; then
  WHY="$WHY

$RUN_HELP
Эмбеддер не проверен (нет EMBED_HEALTH_URL) — строка в коммите этот случай не закрывает."
else
  WHY="$WHY

$RUN_HELP"
fi

python3 - "$WHY" <<'PY' | hook_gate_json check-golden
import json, sys
print(json.dumps({"hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": sys.argv[1]}},
    ensure_ascii=False))
PY
