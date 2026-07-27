#!/bin/bash
# Приёмочный набор: гоняется после КАЖДОЙ правки поиска (docs/CHECKLIST_SEARCH_FIX.md §0).
# Печатает вид ответа, время и текст. Сравнивать с базовой линией из чек-листа.
#
# Вопросы В КОДЕ НЕ ЖИВУТ: они привязаны к конкретной базе, а продукт обязан работать на
# любой (п. 9 TARGET.md). Скрипт читает их из файла, путь — в GOLDEN_FILE.
# Целевое состояние (п. 15 TARGET.md): набор строится ИЗ САМОЙ базы клиента при
# установке, а не пишется руками. Пока файл заполняется вручную под конкретный стенд —
# это тестовые данные, а не часть продукта.
set -a; [ -f /etc/1c-serene-ask.env ] && . /etc/1c-serene-ask.env; set +a
URL=${ASK_URL:-http://127.0.0.1:8091/ask}
GOLDEN_FILE=${GOLDEN_FILE:-$(dirname "$0")/golden-questions.txt}
AUTH=(); [ -n "$ASK_TOKEN" ] && AUTH=(-H "Authorization: Bearer $ASK_TOKEN")

if [ ! -f "$GOLDEN_FILE" ]; then
  echo "нет файла вопросов: $GOLDEN_FILE" >&2
  echo "задайте GOLDEN_FILE или создайте файл: по одному вопросу в строке, # — комментарий" >&2
  exit 2
fi

ask() {
  local q="$1" body t0 t1 out
  body=$(python3 -c 'import json,sys; print(json.dumps({"question": sys.argv[1]}))' "$q")
  t0=$(date +%s%N)
  out=$(curl -s --max-time 120 -X POST "$URL" -H 'Content-Type: application/json' "${AUTH[@]}" -d "$body")
  t1=$(date +%s%N)
  printf '%-44s %5d мс  ' "${q:0:44}" $(( (t1-t0)/1000000 ))
  printf '%s\n' "$out" | python3 -c '
import json,sys
try:
    d = json.loads(sys.stdin.read())
except Exception:
    print("НЕ JSON"); raise SystemExit
kind = d.get("kind","?")
txt  = (d.get("text") or "").replace("\n"," ").strip()
if not txt:
    kind += "(ПУСТОЙ ОТВЕТ)"       # п.18 TARGET.md: молчать вместо отказа запрещено
print("%-22s %s" % (kind, txt[:150] if txt else ""))
'
}

n=0
while IFS= read -r q; do
  [ -z "$q" ] && continue
  case "$q" in \#*) continue;; esac
  ask "$q"; n=$(( n + 1 ))
done < "$GOLDEN_FILE"
echo "— вопросов: $n"
