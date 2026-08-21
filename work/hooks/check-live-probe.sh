#!/usr/bin/env bash
# Перед коммитом serene_ask.py: живая проба okna (AB_PROBE=okna) свежее файла, 0 сбоев.
# Оффлайн-замки мокают кандидатов; бой даёт другой набор — три возврата подряд (9/10/11).
# Отметку ставит только состоявшийся прогон, не touch. Процедура — REGRESSION_BASE1 §0.
set -uo pipefail

. "$(dirname "${BASH_SOURCE[0]}")/lib-hooks.sh"
CMD=$(hook_command)
is_git_commit "$CMD" || { echo '{}'; exit 0; }

cd_repo || { hook_ask "Хук $(basename "$0") не определил каталог репозитория и ничего не проверил. Подтвердите шаг вручную."; exit 0; }

mapfile -t PS < <(hook_commit_pathspec "$CMD")
STAGED=$(git diff --cached --name-only -- "${PS[@]}" 2>/dev/null)
printf '%s\n' "$STAGED" | grep -qx 'ubuntu/serenedb/serene_ask.py' \
  || { echo '{}'; exit 0; }

MARK=".claude/.probe-okna-last-run"
ASK="ubuntu/serenedb/serene_ask.py"

probe_mark_ok() {
  [ -f "$MARK" ] || return 1
  IFS= read -r line < "$MARK" 2>/dev/null || return 1
  [[ "$line" == okna\ probe\ * ]] && [[ "$line" == *0err/* ]]
}

if [ ! -f "$MARK" ]; then
  WHY="Живая проба okna ни разу не прогонялась после появления этой проверки.
Коммит serene_ask.py без живого замера — то самое «замки зелёные, живьём красное»."
elif ! probe_mark_ok; then
  WHY="Отметка .probe-okna-last-run есть, но это не успешная проба (нужен префикс
okna probe … и суффикс 0err/N). Отметку ставит только AB_PROBE=okna при 0 сбоев."
elif [ "$ASK" -nt "$MARK" ]; then
  WHY="serene_ask.py правили ПОСЛЕ последней живой пробы okna.
Последняя проба: $(date -r "$MARK" '+%Y-%m-%d %H:%M' 2>/dev/null)
Сначала прогон (см. REGRESSION_BASE1 §0), потом коммит."
else
  echo '{}'; exit 0
fi

RUN_HELP="Живая проба ДО коммита serene_ask.py (кандидат на okna :8092, эталоны SQL):
  # на okna: scp кандидата в /tmp, инстанс :8092 (env построчно, НЕ source), затем:
  AB_PROBE=okna ASK_URL=http://127.0.0.1:8092/ask python3 ubuntu/serenedb/ab_scorer.py
  # отметку .claude/.probe-okna-last-run ставит только прогон с 0 сбоев, не touch.
Подробности — docs/REGRESSION_BASE1.md §0."

python3 - "$WHY

$RUN_HELP" <<'PY' | hook_gate_json check-live-probe
import json, sys
print(json.dumps({"hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": sys.argv[1]}},
    ensure_ascii=False))
PY
