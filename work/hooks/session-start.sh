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
echo "$(date '+%d.%m %H:%M:%S') session-start вброс «С ЧЕГО НАЧАТЬ» ($TOTAL строк в разделе)" >> .claude/hooks.log 2>/dev/null || true
echo "=== Автовброс из $F (SessionStart-хук) ==="
printf '%s\n' "$SECTION" | head -n "$MAX_LINES"
if [ "$TOTAL" -gt "$MAX_LINES" ]; then
  echo ""
  echo "…показаны первые $MAX_LINES строк из $TOTAL (свежее — сверху). Полный раздел и история — в $F."
fi

# Свежесть вброшенного: сессии забывают обновлять activeContext (владелец, 03.08), и
# тогда вброс выше уверенно врёт. Считаем рабочие коммиты с последней правки файла —
# и говорим об отставании прямо, с числом, а не молчим.
LAST_AC=$(git log -1 --format=%H -- "$F" 2>/dev/null)
if [ -n "$LAST_AC" ]; then
  BEHIND=$(git rev-list --count "$LAST_AC..HEAD" -- ubuntu/ work/ windows/ docs/ 2>/dev/null || echo 0)
  if [ "${BEHIND:-0}" -gt 10 ]; then
    echo ""
    echo "🔴 ВБРОШЕННОЕ ВЫШЕ ОТСТАЁТ: с последней правки $F прошло $BEHIND рабочих коммитов."
    echo "Раздел «С ЧЕГО НАЧАТЬ» может врать. Сверься с CHANGELOG.md за сегодня и, если"
    echo "состояние сдвинулось, обнови $F ПЕРВЫМ действием — иначе следующая сессия"
    echo "получит этот же устаревший вброс."
    echo "$(date '+%d.%m %H:%M:%S') session-start ⚠️ activeContext отстаёт на $BEHIND коммитов" >> .claude/hooks.log 2>/dev/null || true
  fi
fi
