#!/usr/bin/env bash
# Общие опознаватели команд для хуков. Одно место на все хуки — по построению, а не
# договорённостью: разъехавшиеся копии одного правила и были дефектом `F248`.
#
# 🔴 ЗАЧЕМ. Все коммит-хуки начинали с `case "$CMD" in *"git commit"*)`, то есть искали
# ПОДСТРОКУ. Мимо неё проходит любая равнозначная форма той же команды:
#   git -C /srv/1c commit -m …        git --git-dir=… --work-tree=… commit …
#   git -c user.name=X commit …
# Запрет, который обходится сменой формы записи, запретом не является (`CLAUDE.md`:
# «запреты держатся кодом, а не промтом»). Опознаём git по команде и подкоманде, а не
# по буквам подряд.
#
# Ловить всё подряд тоже нельзя: хук спрашивает владельца, и ложное срабатывание — это
# отнятое внимание. Поэтому поиск не пересекает границу команды (`;`, `&&`, `||`, `|`),
# и `git log --grep commit` в неё не попадает.

# 🔴 КАТАЛОГ РЕПОЗИТОРИЯ БЕРЁТСЯ НЕ ИЗ CWD. Хуки начинались с
#   cd "$(git rev-parse --show-toplevel 2>/dev/null || echo .)" || exit 0
# и это fail-open: если движок запустил хук не из каталога проекта, `git rev-parse` не
# срабатывает, `git diff --cached` отдаёт пусто, хук печатает `{}` и коммит проходит
# БЕЗ ЕДИНОЙ ПРОВЕРКИ. Проверено 02.08 прямым вызовом из `/`: молчаливое `{}`.
# Порядок источников: переменная движка → корень по текущему каталогу → МЕСТО САМОГО ХУКА.
# Последняя ступень и закрывает fail-open: хук лежит в `<корень>/.claude/hooks/`, значит
# свой репозиторий он знает всегда, даже когда его запустили из `/`.
hook_repo_root() {
  local d="${CLAUDE_PROJECT_DIR:-}"
  if [ -n "$d" ] && [ -e "$d/.git" ]; then printf '%s' "$d"; return 0; fi
  d="$(git rev-parse --show-toplevel 2>/dev/null)"
  if [ -n "$d" ]; then printf '%s' "$d"; return 0; fi
  d="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." 2>/dev/null && pwd)"
  if [ -n "$d" ] && [ -e "$d/.git" ]; then printf '%s' "$d"; return 0; fi
  return 1
}

# Перейти в каталог репозитория. Не удалось — это не повод пропустить проверку.
cd_repo() {
  local r
  r="$(hook_repo_root)" || return 1
  [ -n "$r" ] || return 1
  cd "$r" || return 1
}

# Вынести решение владельцу (единственная форма ответа, которой хуки останавливают шаг).
hook_ask() {
  python3 - "$1" <<'PY'
import json, sys
print(json.dumps({"hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "ask",
    "permissionDecisionReason": sys.argv[1]}}, ensure_ascii=False))
PY
}

# Команда из полезной нагрузки хука (stdin — JSON события).
hook_command() {
  python3 -c 'import json,sys
d=json.load(sys.stdin)
print((d.get("tool_input") or {}).get("command") or "")' 2>/dev/null
}

# Это коммит?
is_git_commit() {
  # Между `git` и `commit` допускаются только ФЛАГИ, каждый — со своим значением
  # («-C /srv/1c», «-c user.name=X», «--git-dir=…»). Поэтому `git log --grep commit`
  # сюда не попадает: `log` флагом не является.
  printf '%s' "$1" \
    | grep -qE '(^|[;&|]|[[:space:]])git([[:space:]]+-{1,2}[^;&|[:space:]]+([[:space:]]+[^-;&|[:space:]][^;&|[:space:]]*)?)*[[:space:]]+commit([[:space:]]|$)'
}

# Это выкат, то есть попадание кода туда, откуда он ИСПОЛНЯЕТСЯ?
#
# 🔴 Прежде хук замера ловил только `scp` и `rsync` (`F133`, `№14`) — то есть выкат на
# ДРУГУЮ машину. Но наш выкат местный: `deploy.sh` кладёт в `/opt/1c-mcp-reports`,
# `deploy_instance.sh` — в рабочую папку бота, и правки случаются прямо в `/opt`.
# Правило «замер до выката» не срабатывало ни разу на том способе, которым мы выкатываем.
is_deploy() {
  printf '%s' "$1" | grep -qE '(^|[;&|]|[[:space:]])(scp|rsync)([[:space:]]|$)|deploy(_instance)?\.sh|(^|[;&|]|[[:space:]])(install|cp|mv|rsync)[[:space:]][^;&|]*[[:space:]]/(opt|etc)/|openclaw[[:space:]]+plugins[[:space:]]+(install|link)'
}
