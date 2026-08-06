#!/usr/bin/env bash
# Проверка после правки: велосипед поверх штатного механизма, подгонка под нашу базу,
# рост величины без границы.
#
# Почему скриптом, а не промтом: промт-проверка на файлах, которые её не касаются
# (доки, конфиги), отвечала пояснением вместо «OK», а любой ответ кроме «OK» механизм
# считает находкой и обрывает работу. Отбор файлов обязан быть детерминированным.
set -uo pipefail

# Поле пути у Claude — `file_path`, у Kimi — `path` (замер 06.08): принимаем оба.
# 🔴 Эта строка однажды уже была потеряна: проба PostToolUse правила файл, а возврат
# пробы через `git checkout --` затёр и исправление (06.08). Пробу откатывать точечно.
FILE=$(python3 -c 'import json,sys; d=json.load(sys.stdin); ti=d.get("tool_input") or {}; print(ti.get("file_path") or ti.get("path") or "")' 2>/dev/null)
case "$FILE" in
  *.py|*.js|*.mjs) ;;
  *) echo '{}'; exit 0 ;;               # не код — молча пропускаем
esac
[ -f "$FILE" ] || { echo '{}'; exit 0; }

FOUND=""

# Своё поверх штатного: имена механизмов SereneDB, которые мы уже находили в аудите.
# Ищем в ДОБАВЛЕННОМ коде признаки ручной реализации того, что движок умеет сам.
if grep -qE "for .* in range\(.*\).*:\s*$" "$FILE" 2>/dev/null && \
   grep -qE "count\(\*\).*UNION ALL|UNION ALL.*count\(\*\)" "$FILE" 2>/dev/null; then
  FOUND="${FOUND}Похоже на счётчики циклом вместо словаря термов (ts_dict_agg/_count/_score).
"
fi

# Числовые отсечки в пути правильности. Бюджеты (размер пачки, параллельность,
# LIMIT показа) сюда не попадают — они читаются из окружения.
CONST=$(grep -nE "^[A-Z_]+ *= *[0-9]+" "$FILE" 2>/dev/null \
        | grep -vE "os\.environ|getenv|PORT|TIMEOUT|BATCH|PARALLEL|INS|PAGE|DIM" \
        | head -4)
[ -n "$CONST" ] && FOUND="${FOUND}Константы вне окружения (проверь, бюджет это или порог правильности):
$(printf '%s' "$CONST" | sed 's/^/  /')
"

# Величина, уходящая в модель или в память, без верхней границы.
if grep -qE "\.join\(.*for .* in (cands|names|rows|tables|srcs)\b" "$FILE" 2>/dev/null && \
   ! grep -qE "BUDGET|LIMIT|\[:.*\]" "$FILE" 2>/dev/null; then
  FOUND="${FOUND}Перечисление без видимой верхней границы — проверь, не растёт ли с размером базы.
"
fi

if [ -z "$FOUND" ]; then
  echo '{}'
else
  python3 - "$FILE" "$FOUND" <<'PY'
import json, sys
print(json.dumps({"systemMessage": "%s: %s" % (sys.argv[1].split("/")[-1], sys.argv[2].strip())},
                 ensure_ascii=False))
PY
fi
