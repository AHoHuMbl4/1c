#!/usr/bin/env bash
# Перехват перед коммитом: код без документов не коммитится молча.
#
# Зачем: главное правило проекта — «работа не закончена, пока не обновлены документы»,
# и коммит обязан включать и код, и документы (CLAUDE.md). До этого хука правило
# держалось текстом; дважды документ, отставший от кода, приводил к реальным поломкам
# (HOW_NOT_TO §3.1). Теперь проверяет код.
#
# Не блокирует, а выносит решение владельцу — как и остальные снайперы.
set -uo pipefail

. "$(dirname "${BASH_SOURCE[0]}")/lib-hooks.sh"
CMD=$(hook_command)
# Опознаватель общий на все хуки (`lib-hooks.sh`): подстрока «git commit» пропускала
# равнозначные формы вроде `git -C /srv/1c commit` (`F248`).
is_git_commit "$CMD" || { echo '{}'; exit 0; }

# Корень репозитория — от движка или от места самого хука, НЕ от текущего каталога:
# прежняя форма при запуске из чужого каталога молча пропускала коммит (fail-open).
cd_repo || { hook_ask "Хук $(basename "$0") не смог определить каталог репозитория и ничего не проверил. Пропускать проверку молча нельзя — подтвердите шаг вручную."; exit 0; }

STAGED=$(git diff --cached --name-only 2>/dev/null)
[ -z "$STAGED" ] && { echo '{}'; exit 0; }

# Код и состояние: исходники, скрипты, конфиги, юниты. memory_bank/ — данные, не код.
CODE=$(printf '%s\n' "$STAGED" | grep -v '^memory_bank/' \
  | grep -E '\.(py|sh|cs|js|mjs|ts|sql|ps1|psm1|bat|cmd|ini|toml|yml|yaml|json|conf|cfg|service|timer)$' || true)
DOCS=$(printf '%s\n' "$STAGED" | grep -E '\.md$' || true)

LOG=".claude/hooks.log"

# 🔴 ОБРАТНАЯ ПРОВЕРКА (`№13`, `F122`): документы, уехавшие ВПЕРЁД кода. Прежде хук ловил
# только «код без документов», а зеркальный случай проходил молча — именно так 30.07
# `CHANGELOG` и `progress` описали код, которого в git не было. Ищем в добавленных строках
# упоминания файлов репозитория и проверяем, что они существуют хоть где-то: в рабочем
# дереве, в индексе или в HEAD. Документ вправе говорить и о прошлом — поэтому спрашиваем,
# а не запрещаем.
if [ -z "$CODE" ] && [ -n "$DOCS" ]; then
  GHOSTS=$(git diff --cached -U0 -- '*.md' 2>/dev/null \
    | grep '^+' | grep -v '^+++' \
    | grep -oE '(ubuntu|work|windows|docs|memory_bank|\.claude)/[A-Za-z0-9_@./-]+\.(py|sh|sql|js|mjs|ts|service|timer|tsv|ps1|cs|json)' \
    | sort -u \
    | while read -r p; do
        [ -e "$p" ] && continue
        git cat-file -e ":$p" 2>/dev/null && continue
        git cat-file -e "HEAD:$p" 2>/dev/null && continue
        echo "$p"
      done)
  if [ -n "$GHOSTS" ]; then
    echo "$(date '+%d.%m %H:%M:%S') check-docs  ASK: документы про несуществующий код" >> "$LOG" 2>/dev/null || true
    python3 - "$(printf '%s\n' "$GHOSTS" | head -10)" <<'PY' | hook_gate_json check-docs
import json, sys
print(json.dumps({"hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason":
        "В коммите одни документы, и они называют файлы, которых нет ни в рабочем "
        "дереве, ни в индексе, ни в HEAD:\n\n"
        + sys.argv[1]
        + "\n\nЛибо код забыли добавить в коммит (`git add`), либо документ описывает "
          "то, чего ещё нет, — и тогда он врёт с первой минуты. Устаревший документ "
          "хуже отсутствующего: отсутствующий заставляет посмотреть в код, а "
          "устаревший уверенно врёт (CLAUDE.md).\n"
          "Если документ намеренно говорит о прошлом (разбор «было ошибочно», история "
          "в progress.md) — подтвердите."}},
    ensure_ascii=False))
PY
    exit 0
  fi
fi

if [ -z "$CODE" ] || [ -n "$DOCS" ]; then
  echo "$(date '+%d.%m %H:%M:%S') check-docs  тихо (коммит в порядке)" >> "$LOG" 2>/dev/null || true
  echo '{}'; exit 0
fi
echo "$(date '+%d.%m %H:%M:%S') check-docs  ASK: код без документов" >> "$LOG" 2>/dev/null || true

python3 - "$(printf '%s\n' "$CODE" | head -10)" <<'PY' | hook_gate_json check-docs
import json, sys
print(json.dumps({"hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason":
        "В коммите есть код, но нет ни одного документа:\n\n"
        + sys.argv[1]
        + "\n\nПравило CLAUDE.md: коммит включает и код, и документы — как минимум "
          "запись в CHANGELOG.md (что изменилось и чем доказано), плюс документы по "
          "типу изменения из таблицы «Куда что писать».\n"
          "Если это правка, которой документы правда не нужны, — подтвердите; "
          "иначе — сначала документы, потом коммит."}},
    ensure_ascii=False))
PY
