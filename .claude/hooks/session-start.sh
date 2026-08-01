#!/usr/bin/env bash
# SessionStart: вбрасывает в контекст новой сессии раздел «С ЧЕГО НАЧАТЬ» из
# memory_bank/activeContext.md.
#
# Зачем: порядок чтения в CLAUDE.md держался текстом («прочитай activeContext.md»),
# а правило проекта — обязательное держится кодом. Теперь текущее состояние работ
# попадает в контекст независимо от того, дочитала ли модель инструкцию.
#
# Раздел большой (новое сверху, старое ниже), поэтому берётся шапка в MAX_LINES
# строк — с явной пометкой об обрезке (молчаливая потеря = дефект).
set -uo pipefail

cd "$(git rev-parse --show-toplevel 2>/dev/null || echo "${CLAUDE_PROJECT_DIR:-.}")" || exit 0

F="memory_bank/activeContext.md"
MAX_LINES=90

if [ ! -f "$F" ]; then
  echo "⚠️ SessionStart-хук: $F не найден. Состояние работ неизвестно — найди его прежде чем работать."
  exit 0
fi

SECTION=$(awk '/^# .*С ЧЕГО НАЧАТЬ/{on=1} on{print}' "$F")

if [ -z "$SECTION" ]; then
  echo "⚠️ SessionStart-хук: в $F нет раздела «С ЧЕГО НАЧАТЬ». Прочитай файл целиком — состояние работ обязано быть известно до первого действия."
  exit 0
fi

TOTAL=$(printf '%s\n' "$SECTION" | wc -l)
echo "=== Автовброс из $F (SessionStart-хук) ==="
printf '%s\n' "$SECTION" | head -n "$MAX_LINES"
if [ "$TOTAL" -gt "$MAX_LINES" ]; then
  echo ""
  echo "…показаны первые $MAX_LINES строк из $TOTAL (свежее — сверху). Полный раздел и история — в $F."
fi
