#!/usr/bin/env bash
# Перехват перед коммитом: в коммит добавлен SQL — назови раздел доков SereneDB.
#
# 🔴 ЭТО ПОДГОТОВЛЕННАЯ ВЕРСИЯ. Записывать прямо в `.claude/hooks/` рубеж среды не даёт
# (точка входа хука). Установка владельцем:
#     install -m 755 work/hooks/check-sql-docs.sh .claude/hooks/check-sql-docs.sh
# и добавить `check-sql-docs` в перечень хуков в `.githooks/pre-commit`.
#
# ЗАЧЕМ. `CLAUDE.md` требует: прежде чем писать SQL, создавать индекс или утверждать
# «штатного средства нет» — спросить `serenedb-docs`. Правило жило только текстом и
# `[замер 03.08]` было нарушено за день ПОЛНОСТЬЮ: доки не спрашивались ни разу, при том
# что SQL писался в двух новых приборах. Ошибки не вышло, но в приборы уехала конструкция
# на непроверенном допущении (два параллельных `unnest` вместо штатного `map_entries`),
# и нашлась она только по вопросу владельца (`HOW_NOT_TO §1.50`).
#
# 🔴 ЧЕГО ЭТОТ ХУК НЕ ДЕЛАЕТ — и врать об этом нельзя. Он НЕ проверяет, что доки были
# открыты: обращение к MCP в дифф не попадает, проверить его нечем. Он делает другое и
# единственно возможное — создаёт МОМЕНТ, в котором работа не продолжается, пока раздел
# не назван. `[замер 03.08]` за день все хуки-остановки исполнены без исключения, а
# 94 вброса-напоминания не изменили поведения ни разу. Останавливать — единственная
# известная форма правила, которая работает.
#
# Что считается SQL — синтаксис языка, а не имена нашей базы: `SELECT … FROM`,
# `WITH … AS (`, `CREATE TABLE|VIEW|INDEX`, `INSERT INTO`, `MERGE INTO`, `UPDATE … SET`,
# `DELETE FROM`. Это универсально и к конкретной конфигурации не привязано.
set -uo pipefail

. "$(dirname "${BASH_SOURCE[0]}")/lib-hooks.sh"
CMD=$(hook_command)
is_git_commit "$CMD" || { echo '{}'; exit 0; }

cd_repo || { hook_ask "Хук $(basename "$0") не смог определить каталог репозитория и ничего не проверил. Пропускать проверку молча нельзя — подтвердите шаг вручную."; exit 0; }

# Для проб подменяется через DIFF_OVERRIDE. `-U0` — только сами добавленные строки.
DIFF="${DIFF_OVERRIDE:-$(git diff --cached -U0 2>/dev/null)}"
[ -z "$DIFF" ] && { echo '{}'; exit 0; }

DIFF="$DIFF" python3 <<'PY'
import json, os, re, sys, time

def log(msg):
    try:
        with open(".claude/hooks.log", "a", encoding="utf-8") as f:
            f.write(time.strftime("%d.%m %H:%M:%S") + " sql-docs    " + msg + "\n")
    except Exception:
        pass

CODE_EXT = (".py", ".sql", ".sh", ".js", ".mjs", ".ts")
# Документы показывают SQL примерами — там правило про доки бессмысленно.
SKIP_PREFIX = (".claude/", "docs/", "memory_bank/")

# Сильные признаки: не одиночное слово, а конструкция. Одиночный `select` встречается в
# прозе и в чужих языках, и на нём хук стал бы шумом.
MARKERS = [
    (r"\bSELECT\b[\s\S]{0,400}?\bFROM\b", "SELECT … FROM"),
    (r"\bWITH\b\s+\w+\s+\bAS\b\s*\(", "WITH … AS ("),
    (r"\bCREATE\b\s+(OR\s+REPLACE\s+)?(TABLE|VIEW|INDEX|MACRO)\b", "CREATE TABLE/VIEW/INDEX"),
    (r"\bINSERT\b\s+\bINTO\b", "INSERT INTO"),
    (r"\bMERGE\b\s+\bINTO\b", "MERGE INTO"),
    (r"\bUPDATE\b[\s\S]{0,200}?\bSET\b", "UPDATE … SET"),
    (r"\bDELETE\b\s+\bFROM\b", "DELETE FROM"),
]

cur = None
hits = {}          # файл -> набор признаков
for line in (os.environ.get("DIFF") or "").splitlines():
    if line.startswith("+++ b/"):
        cur = line[6:].strip()
        continue
    if not line.startswith("+") or line.startswith("+++"):
        continue
    if not cur or cur.startswith(SKIP_PREFIX) or not cur.endswith(CODE_EXT):
        continue
    body = line[1:]
    for rx, name in MARKERS:
        if re.search(rx, body, re.IGNORECASE):
            hits.setdefault(cur, set()).add(name)

if not hits:
    log("тихо (SQL в добавленных строках не найден)")
    print("{}"); sys.exit(0)

lines = []
for path in sorted(hits)[:6]:
    lines.append("  %s — %s" % (path, ", ".join(sorted(hits[path]))))

log("ASK: " + ", ".join(sorted(hits)[:3]))
reason = (
    "В коммит добавлен SQL:\n" + "\n".join(lines) +
    "\n\nПравило CLAUDE.md: прежде чем писать SQL, создавать индекс или утверждать\n"
    "«штатного средства нет» — спросить `serenedb-docs` (search_docs, затем прочитать\n"
    "раздел по url находки) и проверить найденное на живом инстансе: доки описывают\n"
    "текущую версию движка, у нас сборка 26.07.3.\n\n"
    "Назовите раздел доков, по которому проверено, что здесь используется штатное\n"
    "средство (или что штатного нет), — и подтвердите коммит.\n"
    "🔴 Проверить сам факт обращения к докам хук не может: вызова MCP в диффе нет.\n"
    "Он лишь не даёт проскочить момент. Ответ «не смотрел» — законный: тогда посмотрите\n"
    "сейчас, это один вызов.\n\n"
    "Повод, по которому правило заведено гейтом: [замер 03.08] за день доки не\n"
    "спрашивались ни разу, и в приборы уехал параллельный `unnest` вместо штатного\n"
    "`map_entries` (HOW_NOT_TO §1.50, techContext Возможность 40).")
print(json.dumps({"hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "ask",
    "permissionDecisionReason": reason}}, ensure_ascii=False))
PY
