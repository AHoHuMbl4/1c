#!/usr/bin/env bash
# Перед выкатом: живая проба okna (AB_PROBE) + дерево исходников = HEAD по md5.
# ut_test smoke больше не блокер выката (HOW_NOT_TO §3.90, решение владельца 21.08).
# Отметку ставит AB_PROBE=okna → .claude/.probe-okna-last-run (okna probe … 0err/N).
# touch этого файла гейт не предлагает.
# Вторичный люк: эмбеддер мёртв + в HEAD строка «Золотой: невозможен» — когда пробу
# снять нельзя; основной путь — probe+HEAD.
set -uo pipefail

. "$(dirname "${BASH_SOURCE[0]}")/lib-hooks.sh"
CMD=$(hook_command)
is_deploy "$CMD" || { echo '{}'; exit 0; }

cd_repo || { hook_ask "Хук $(basename "$0") не определил каталог репозитория и ничего не проверил. Подтвердите шаг вручную."; exit 0; }

MARK=".claude/.probe-okna-last-run"
SRC_DIRS="ubuntu/serenedb ubuntu/openclaw ubuntu/1c-gateway ubuntu/1c-etl ubuntu/1c-config-ui"

probe_mark_ok() {
  [ -f "$MARK" ] || return 1
  IFS= read -r line < "$MARK" 2>/dev/null || return 1
  [[ "$line" == okna\ probe\ * ]] && [[ "$line" == *0err/* ]]
}

# 0 = чисто; 1 = грязно. Список расхождений — на stdout (до 5 строк).
tree_matches_head() {
  local f disk head bad="" n=0
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    if [ ! -f "$f" ]; then
      n=$((n + 1)); [ "$n" -le 5 ] && bad="${bad}
  $f (нет в дереве)"
      continue
    fi
    disk=$(md5sum -- "$f" | awk '{print $1}')
    if ! git cat-file -e "HEAD:$f" 2>/dev/null; then
      n=$((n + 1)); [ "$n" -le 5 ] && bad="${bad}
  $f (нет в HEAD)"
      continue
    fi
    head=$(git show "HEAD:$f" | md5sum | awk '{print $1}')
    if [ "$disk" != "$head" ]; then
      n=$((n + 1)); [ "$n" -le 5 ] && bad="${bad}
  $f"
    fi
  done < <(git ls-files -- $SRC_DIRS 2>/dev/null | grep -E '\.(py|js|mjs)$' || true)

  while IFS= read -r f; do
    [ -n "$f" ] || continue
    n=$((n + 1)); [ "$n" -le 5 ] && bad="${bad}
  $f (не в git)"
  done < <(git ls-files --others --exclude-standard -- $SRC_DIRS 2>/dev/null \
            | grep -E '\.(py|js|mjs)$' || true)

  if [ "$n" -gt 0 ]; then
    printf '%s\n' "${bad#"${bad%%[![:space:]]*}"}"
    return 1
  fi
  return 0
}

WHY=""
if ! probe_mark_ok; then
  if [ ! -f "$MARK" ]; then
    WHY="Живая проба okna (.probe-okna-last-run) ни разу не ставилась после появления этой проверки.
Выкат без AB_PROBE=okna — это то самое «сначала на боевой, потом посмотрим».
Smoke ut_test больше не открывает выкат (HOW_NOT_TO §3.90)."
  else
    WHY="Отметка .probe-okna-last-run есть, но это не успешная проба okna
(нужен префикс «okna probe …» и суффикс 0err/N).
Отметку ставит только AB_PROBE=okna при 0 сбоев, не touch."
  fi
elif ! DIRTY=$(tree_matches_head); then
  WHY="Исходники в SRC_DIRS отличаются от HEAD (md5) или есть неотслеживаемые *.py|js|mjs:
$DIRTY
Выкат только из закоммиченного дерева, совпадающего с рабочей копией."
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

RUN_HELP="Живая проба ДО выката (кандидат okna, см. REGRESSION_BASE1 §живая проба):
  AB_PROBE=okna ASK_URL=http://127.0.0.1:8092/ask python3 ubuntu/serenedb/ab_scorer.py
Отметку .claude/.probe-okna-last-run ставит только прогон с 0 сбоев (okna probe … 0err/N).
Дерево *.py|js|mjs в SRC_DIRS должно совпадать с HEAD по md5 (без неотслеживаемых).
Приёмка ПОСЛЕ выката на okna (числа + kind):
  AB_CONTOUR=okna python3 ubuntu/serenedb/ab_scorer.py
Smoke ut_test выкат не открывает."

emb=0
golden_embedder_status || emb=$?

if [ "$emb" = 1 ]; then
  NOTE="$(git log -1 --format=%B 2>/dev/null | grep -im1 -E '^[[:space:]]*золотой[[:space:]]*:[[:space:]]*невозможен')"
  if [ -n "$NOTE" ]; then
    hook_log "check-golden" "пропуск: эмбеддер не отвечает, в HEAD есть пометка"
    echo '{}'; exit 0
  fi
  WHY="Живая проба невозможна: эмбеддер не отвечает.
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
