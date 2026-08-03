#!/usr/bin/env bash
# Счётчик повторных правок одного файла за сессию.
#
# Зачем: третья подряд правка одного и того же участка — почти всегда признак подбора, а
# не исправления. В этом проекте так и было: маршрутизация переписывалась шесть раз
# подряд, пока я смотрел на результат восьми вопросов. По каждой отдельной правке это
# незаметно, видно только по серии — поэтому считать должен механизм, а не память.
set -uo pipefail

STATE="${TMPDIR:-/tmp}/claude-edit-counts-${CLAUDE_SESSION_ID:-default}.txt"
FILE=$(python3 -c 'import json,sys; d=json.load(sys.stdin); print((d.get("tool_input") or {}).get("file_path") or "")' 2>/dev/null)
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
