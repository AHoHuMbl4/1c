#!/usr/bin/env bash
# Перехват перед выкатом на сервер: требует, чтобы золотой набор был прогнан ПОСЛЕ
# последней правки исходников.
#
# Зачем: сложился порядок «выкатил — потом померил», из-за которого на боевой стенд
# уезжали правки, ломавшие ответы, и обнаруживалось это уже там. Порядок должен быть
# обратным.
#
# Отметку ставит прогон золотого набора: ubuntu/serenedb/ab_scorer.py или ручной прогон,
# который трогает файл .claude/.golden-last-run.
set -uo pipefail

. "$(dirname "${BASH_SOURCE[0]}")/lib-hooks.sh"
CMD=$(hook_command)
# 🔴 Было `scp`/`rsync` — то есть выкат на ДРУГУЮ машину (`F133`, `№14`). Наш выкат
# местный: `deploy.sh` в `/opt/1c-mcp-reports`, `deploy_instance.sh` в рабочую папку бота,
# плюс правки прямо в `/opt`. Правило «замер до выката» не срабатывало ни разу на том
# способе, которым мы выкатываем на самом деле.
is_deploy "$CMD" || { echo '{}'; exit 0; }

# Корень репозитория — от движка или от места самого хука, НЕ от текущего каталога:
# прежняя форма при запуске из чужого каталога молча пропускала коммит (fail-open).
cd_repo || { hook_ask "Хук $(basename "$0") не смог определить каталог репозитория и ничего не проверил. Пропускать проверку молча нельзя — подтвердите шаг вручную."; exit 0; }

MARK=".claude/.golden-last-run"
SRC_DIRS="ubuntu/serenedb ubuntu/openclaw ubuntu/1c-gateway ubuntu/1c-etl ubuntu/1c-config-ui"

NEWEST=$(find $SRC_DIRS -type f \( -name '*.py' -o -name '*.js' -o -name '*.mjs' \) \
         -newer "$MARK" 2>/dev/null | head -5)

if [ ! -f "$MARK" ]; then
  REASON="Золотой набор ни разу не прогонялся после появления этой проверки.
Выкат без замера — это то самое «сначала на боевой, потом посмотрим»."
elif [ -n "$NEWEST" ]; then
  REASON="Исходники правились ПОСЛЕ последнего прогона золотого набора:
$(printf '%s\n' "$NEWEST" | sed 's/^/  /')
Последний прогон: $(date -r "$MARK" '+%Y-%m-%d %H:%M' 2>/dev/null)"
else
  echo '{}'; exit 0
fi

python3 - "$REASON" <<'PY'
import json, sys
print(json.dumps({"hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "ask",
    "permissionDecisionReason": sys.argv[1]
        + "\n\nПрогнать: python3 ubuntu/serenedb/ab_scorer.py (или отметить "
          "touch .claude/.golden-last-run, если замер сделан иначе)."}},
    ensure_ascii=False))
PY
