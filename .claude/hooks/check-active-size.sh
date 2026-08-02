#!/usr/bin/env bash
# Перехват перед коммитом: activeContext.md не должен разрастаться.
#
# Зачем: файл дорос до ~900 строк, и при большом контексте модель скользит по нему
# глазами — правила и состояние игнорируются. Автоматически ПЕРЕНОСИТЬ текст скриптом
# нельзя: что ещё живо, а что уже история — решение семантическое, тупой перенос даст
# молчаливую потерю. Поэтому порог держит код, а перенос делает модель осмысленно.
#
# Куда переносить: историю по дням — в memory_bank/progress.md; раздел «С ЧЕГО НАЧАТЬ»
# остаётся коротким, новое сверху.
set -uo pipefail

. "$(dirname "${BASH_SOURCE[0]}")/lib-hooks.sh"
CMD=$(hook_command)
# Опознаватель общий на все хуки (`lib-hooks.sh`): подстрока «git commit» пропускала
# равнозначные формы вроде `git -C /srv/1c commit` (`F248`).
is_git_commit "$CMD" || { echo '{}'; exit 0; }

# Корень репозитория — от движка или от места самого хука, НЕ от текущего каталога:
# прежняя форма при запуске из чужого каталога молча пропускала коммит (fail-open).
cd_repo || { hook_ask "Хук $(basename "$0") не смог определить каталог репозитория и ничего не проверил. Пропускать проверку молча нельзя — подтвердите шаг вручную."; exit 0; }

F="memory_bank/activeContext.md"
LIMIT=300
[ -f "$F" ] || { echo '{}'; exit 0; }

LINES=$(wc -l < "$F")
[ "$LINES" -le "$LIMIT" ] && { echo '{}'; exit 0; }
echo "$(date '+%d.%m %H:%M:%S') active-size ASK: activeContext.md $LINES строк (порог $LIMIT)" >> .claude/hooks.log 2>/dev/null || true

python3 - "$LINES" "$LIMIT" <<'PY'
import json, sys
lines, limit = sys.argv[1], sys.argv[2]
print(json.dumps({"hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "ask",
    "permissionDecisionReason":
        f"memory_bank/activeContext.md разросся до {lines} строк (порог {limit}).\n\n"
        "Разросшийся файл при большом контексте игнорируется — правила перестают "
        "действовать. Перенеси историю в memory_bank/progress.md (по дням, осмысленно, "
        "ничего не теряя — молчаливая потеря = дефект), оставь здесь только живое "
        "состояние и «С ЧЕГО НАЧАТЬ». Потом повтори коммит.\n"
        "Если прямо сейчас переносить нельзя — подтвердите коммит, но перенос остаётся "
        "долгом ближайшего шага."}},
    ensure_ascii=False))
PY
