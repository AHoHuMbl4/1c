#!/usr/bin/env bash
# Перехват перед коммитом: новые/удалённые компоненты не должны проходить мимо графа.
#
# Зачем: прямое направление (вброс зависимостей при правке) держит check-deps.sh, а
# обратное — «создал компонент → внеси в граф» — держалось текстом CLAUDE.md и в первый
# же день не сработало: сессия 02.08 создала три файла, не вызвав MCP memory ни разу.
# Не блокирует, а выносит владельцу, как остальные снайперы.
set -uo pipefail

. "$(dirname "${BASH_SOURCE[0]}")/lib-hooks.sh"
CMD=$(hook_command)
# Опознаватель общий на все хуки (`lib-hooks.sh`): подстрока «git commit» пропускала
# равнозначные формы вроде `git -C /srv/1c commit` (`F248`). Этот хук в находке назван не
# был — его завели позже, и он унаследовал тот же дефект: ещё один довод держать
# опознаватель в одном месте, а не копией в каждом файле.
is_git_commit "$CMD" || { echo '{}'; exit 0; }

# Корень репозитория — от движка или от места самого хука, НЕ от текущего каталога:
# прежняя форма при запуске из чужого каталога молча пропускала коммит (fail-open).
cd_repo || { hook_ask "Хук $(basename "$0") не смог определить каталог репозитория и ничего не проверил. Пропускать проверку молча нельзя — подтвердите шаг вручную."; exit 0; }
GRAPH="memory_bank/mcp-memory.json"
[ -f "$GRAPH" ] || { echo '{}'; exit 0; }

# A<TAB>path / D<TAB>path; для теста подменяется через STAGED_OVERRIDE
STAGED="${STAGED_OVERRIDE:-$(git diff --cached --name-status 2>/dev/null)}"
[ -z "$STAGED" ] && { echo '{}'; exit 0; }

STAGED="$STAGED" python3 - "$GRAPH" <<'PY'
import json, os, sys, time

def log(msg):
    try:
        with open(".claude/hooks.log", "a", encoding="utf-8") as f:
            f.write(time.strftime("%d.%m %H:%M:%S") + " graph-fresh " + msg + "\n")
    except Exception:
        pass

hay = open(sys.argv[1], encoding="utf-8").read()
graph_staged, added, deleted = False, [], []
CODE_EXT = (".py", ".sh", ".sql", ".js", ".mjs", ".service", ".timer", ".ts")

for row in os.environ["STAGED"].splitlines():
    parts = row.split("\t")
    if len(parts) < 2:
        continue
    st, path = parts[0][:1], parts[-1]
    if path == "memory_bank/mcp-memory.json":
        graph_staged = True
        continue
    if path.startswith((".claude/", "work/", "docs/", "memory_bank/")):
        continue
    if not path.endswith(CODE_EXT):
        continue
    base = os.path.basename(path)
    stem = base.split("@")[0].rsplit(".", 1)[0]
    known = base in hay or (len(stem) >= 7 and stem in hay)
    if st == "A" and not known:
        added.append(path)
    elif st == "D" and known:
        deleted.append(path)

if graph_staged or (not added and not deleted):
    log("тихо (граф в коммите или компоненты известны)")
    print("{}"); sys.exit(0)

msg = []
if added:
    msg.append("Новые компоненты, которых НЕТ в графе зависимостей:\n  " + "\n  ".join(added[:8]))
if deleted:
    msg.append("Удалённые файлы, которые в графе ЕСТЬ (связи осиротеют):\n  " + "\n  ".join(deleted[:8]))
log("ASK: " + ", ".join(added[:3] + deleted[:3]))
print(json.dumps({"hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "ask",
    "permissionDecisionReason":
        "\n\n".join(msg)
        + "\n\nПравило CLAUDE.md: создал или удалил компонент — обнови граф тем же заходом\n"
          "(mcp__memory__create_entities / create_relations / delete_relations, с источником\n"
          "файл:строка) и закоммить memory_bank/mcp-memory.json вместе с правкой.\n"
          "Если файл — не компонент (разовый вспомогательный), подтвердите коммит."}},
    ensure_ascii=False))
PY
