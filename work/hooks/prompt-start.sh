#!/usr/bin/env bash
# UserPromptSubmit: разовый вброс «С ЧЕГО НАЧАТЬ» в сессии Kimi.
#
# 🔴 ЗАЧЕМ НОВЫЙ ХУК, А НЕ session-start. У Kimi событие SessionStart — наблюдатель:
# его вывод в контекст НЕ попадает (живой замер 06.08: хук отработал, строка вброса легла
# в .claude/hooks.log, а модель вброшенного не видела и признала это). stdout в контекст
# движок добавляет у UserPromptSubmit — поэтому вброс для Kimi переехал сюда. В Claude
# Code ничего не меняется: там SessionStart вбрасывает, как и раньше.
#
# Событие срабатывает на КАЖДОЕ сообщение пользователя, поэтому вброс делается один раз
# на сессию — меткой с session_id в .claude/state. Повторный вброс того же раздела был
# бы шумом в контексте на каждый вопрос.
set -uo pipefail

INPUT=$(cat)
SID=$(printf '%s' "$INPUT" | python3 -c 'import json,sys
print(json.load(sys.stdin).get("session_id") or "")' 2>/dev/null)
[ -n "$SID" ] || exit 0

# Корень — от места самого хука: сессия может быть запущена не из каталога проекта.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." 2>/dev/null && pwd)"
[ -n "$ROOT" ] || exit 0
MARK="$ROOT/.claude/state/prompt-start-$SID"
[ -e "$MARK" ] && exit 0
mkdir -p "$ROOT/.claude/state" 2>/dev/null
touch "$MARK" 2>/dev/null || exit 0

"$ROOT/.claude/hooks/session-start.sh"
