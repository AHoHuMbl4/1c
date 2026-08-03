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

STAGED="$STAGED" python3 - "$GRAPH" <<'PY' | hook_gate_json check-graph-fresh
import json, os, sys, time

def log(msg):
    try:
        with open(".claude/hooks.log", "a", encoding="utf-8") as f:
            f.write(time.strftime("%d.%m %H:%M:%S") + " graph-fresh " + msg + "\n")
    except Exception:
        pass

# 🔴 «Известен» = существует СУЩНОСТЬ с таким именем, а не подстрока где-то в файле.
# Первая версия искала имя по всему тексту графа и пропустила пять компонентов 03.08:
# их имена упоминались в наблюдениях ЧУЖИХ сущностей, своих сущностей не было.
# Упоминание — не учёт. И граф читаем из ИНДЕКСА, если он в коммите: «тронул файл
# графа» само по себе ничего не доказывает.
import subprocess

graph_staged = any(
    row.split("\t")[-1] == "memory_bank/mcp-memory.json"
    for row in os.environ["STAGED"].splitlines() if "\t" in row)
if graph_staged:
    try:
        graph_text = subprocess.run(
            ["git", "show", ":memory_bank/mcp-memory.json"],
            capture_output=True, text=True, check=True).stdout
    except Exception:
        graph_text = open(sys.argv[1], encoding="utf-8").read()
else:
    graph_text = open(sys.argv[1], encoding="utf-8").read()

entity_names = []
for line in graph_text.splitlines():
    line = line.strip()
    if not line:
        continue
    try:
        d = json.loads(line)
    except Exception:
        continue
    if d.get("type") == "entity":
        entity_names.append(d.get("name", ""))

def is_entity(base, stem):
    for n in entity_names:
        if n == base or n == stem:
            return True
        if len(base) >= 7 and (base in n or n in base):
            return True
        if len(stem) >= 7 and (stem in n or n in stem):
            return True
    return False

added, deleted, changed = [], [], []
CODE_EXT = (".py", ".sh", ".sql", ".js", ".mjs", ".service", ".timer", ".ts")

for row in os.environ["STAGED"].splitlines():
    parts = row.split("\t")
    if len(parts) < 2:
        continue
    st, path = parts[0][:1], parts[-1]
    if path == "memory_bank/mcp-memory.json":
        continue
    # 🔴 `work/` из пропуска УБРАН для случая правки (M). Приборы приёмки живут именно
    # там и в графе как сущности ЕСТЬ; пропуская их, гейт молчал бы ровно о том, что
    # правится чаще всего. Для новых файлов (A) пропуск сохранён: в `work/` заводится
    # много разового, и требовать сущность на каждый черновик — превратить гейт в шум.
    if path.startswith((".claude/", "docs/", "memory_bank/")):
        continue
    if st == "A" and path.startswith("work/"):
        continue
    if not path.endswith(CODE_EXT):
        continue
    base = os.path.basename(path)
    stem = base.split("@")[0].rsplit(".", 1)[0]
    known = is_entity(base, stem)
    if st == "A" and not known:
        added.append(path)
    elif st == "D" and known:
        deleted.append(path)
    # 🔴 ПРАВКА ИЗВЕСТНОГО КОМПОНЕНТА БЕЗ ГРАФА (заведено 03.08 по слову владельца
    # «чтобы это было не рекомендация, а неизбежное правило»).
    #
    # Прямое направление — вброс связей при правке — держал `check-deps.sh`, и держал
    # честно: `[замер 03.08]` за день **94 вброса**. Изменений в графе за тот же день —
    # **ноль**. Вброс СООБЩАЕТ, но ничего не требует, поэтому работа шла дальше. Все
    # правила, у которых была ОСТАНОВКА (`check-docs` 5 раз, `check-active-size` 7,
    # снайпер хардкода, проверка кода), исполнены в тот день без исключения.
    #
    # Отсюда правило: у вброса обязан быть момент, в котором работа не продолжается.
    # Момент — коммит: тронул файл, у которого в графе ЕСТЬ сущность, а сам граф в
    # коммит не входит — покажи, чем граф обновлён, либо подтверди, что зависимости
    # не менялись. Проверка механическая: имя сущности против имени файла, ровно та же,
    # что уже работает для A и D.
    elif st in ("M", "R", "C") and known and not graph_staged:
        changed.append(path)

if not added and not deleted and not changed:
    log("тихо (все компоненты коммита — сущности графа)")
    print("{}"); sys.exit(0)

msg = []
if added:
    msg.append("Новые компоненты, которых НЕТ в графе зависимостей:\n  " + "\n  ".join(added[:8]))
if deleted:
    msg.append("Удалённые файлы, которые в графе ЕСТЬ (связи осиротеют):\n  " + "\n  ".join(deleted[:8]))
if changed:
    msg.append("Правятся компоненты, которые ЕСТЬ в графе, а граф в коммит не входит:\n  "
               + "\n  ".join(changed[:8]))
log("ASK: " + ", ".join(added[:3] + deleted[:3] + changed[:3]))
tail = ("\n\nПравило CLAUDE.md: создал, удалил или изменил компонент — обнови граф тем же\n"
        "заходом (mcp__memory__create_entities / create_relations / delete_relations /\n"
        "add_observations, с источником файл:строка) и закоммить memory_bank/mcp-memory.json\n"
        "вместе с правкой.\n"
        "Дешёвый честный способ закрыть: одно наблюдение о том, ЧТО именно изменилось в\n"
        "поведении компонента — это и есть то, ради чего граф ведётся.\n"
        "Зависимости и поведение правда не менялись (опечатка, комментарий) — подтвердите коммит.")
print(json.dumps({"hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "\n\n".join(msg) + tail}},
    ensure_ascii=False))
PY
