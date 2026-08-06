#!/usr/bin/env bash
# Счётчик повторных правок одного файла за сессию.
#
# Зачем: третья подряд правка одного и того же участка — почти всегда признак подбора, а
# не исправления. В этом проекте так и было: маршрутизация переписывалась шесть раз
# подряд, пока я смотрел на результат восьми вопросов. По каждой отдельной правке это
# незаметно, видно только по серии — поэтому считать должен механизм, а не память.
set -uo pipefail

# Событие читается один раз: и путь, и идентификатор сессии. У Kimi идентификатор сессии
# приходит в полезной нагрузке (session_id), у Claude — переменной CLAUDE_SESSION_ID; без
# него счётчик был бы общим на все сессии, и чужие правки накручивали бы чужой счёт.
# Поле пути у Kimi — `path`, у Claude — `file_path` (замер 06.08): принимаем оба.
INPUT=$(cat)
FILE=$(printf '%s' "$INPUT" | python3 -c 'import json,sys; d=json.load(sys.stdin); ti=d.get("tool_input") or {}; print(ti.get("file_path") or ti.get("path") or "")' 2>/dev/null)
SID=$(printf '%s' "$INPUT" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("session_id") or "")' 2>/dev/null)
STATE="${TMPDIR:-/tmp}/hook-edit-counts-${CLAUDE_SESSION_ID:-${SID:-default}}.txt"
[ -z "$FILE" ] && { echo '{}'; exit 0; }

case "$FILE" in
  *.py|*.js|*.mjs) ;;
  *) echo '{}'; exit 0 ;;
esac

touch "$STATE"
N=$(grep -c -F -x "$FILE" "$STATE" 2>/dev/null | head -1)
N=$(( ${N:-0} + 1 ))
printf '%s\n' "$FILE" >> "$STATE"

# Порог намеренно низкий и не подстраивается: он не влияет на правильность продукта,
# только на то, когда задать вопрос.
if [ "$N" -ge 3 ] && [ $(( N % 3 )) -eq 0 ]; then
  python3 - "$FILE" "$N" <<'PY'
import json, sys
print(json.dumps({"systemMessage":
    "%s правится %s-й раз за сессию. Если это подбор под замер, а не исправление "
    "найденной причины — остановись и опиши гипотезу до следующей правки." % (sys.argv[1], sys.argv[2])},
    ensure_ascii=False))
PY
else
  echo '{}'
fi
