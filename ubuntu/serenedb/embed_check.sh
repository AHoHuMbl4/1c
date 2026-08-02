#!/bin/bash
# ПРОВЕРКА, ЧТО ЭМБЕДДЕР ОТДАЁТ ИМЕННО ТУ МОДЕЛЬ, КОТОРУЮ МЫ ПРОСИМ.
#
# 🔴 ЗАЧЕМ. [замер 02.08] наш эндпоинт при неизвестном имени модели молча подставляет
# свою: запрос с `model=Qwen3-Embedding-4B-Q8_0` и даже с выдуманным именем возвращает
# HTTP 200 и вектор, посчитанный `Qwen3-Embedding-4B-Q6_K`. Ошибки нет ни одной.
# Для нас это худший из возможных отказов: векторы разных моделей несравнимы, а таблица
# получила бы отметку о модели, которой её на самом деле не считали, — то есть система
# считала бы смысловой путь исправным и тихо выбирала не то (п. 10, п. 12 TARGET.md).
#
# Проверка стоит один запрос и снимает ровно этот класс ошибок: сверяется имя модели В
# ОТВЕТЕ, а не то, что мы попросили. Ключ идёт файлом, а не аргументом: в командной
# строке его видно любому `ps`.
#
# Использование: embed_check.sh   (0 — модель та, 1 — не та или сервис не отвечает)
# Окружение:     EMBED_BASE_URL, EMBED_API_KEY|EMBED_API_KEYS, EMBED_MODEL
set -u

BASE="${EMBED_BASE_URL:-}"
KEY="${EMBED_API_KEY:-}"
[ -n "$KEY" ] || KEY="$(printf '%s' "${EMBED_API_KEYS:-}" | cut -d, -f1 | tr -d ' ')"
MODEL="${EMBED_MODEL:-}"

# Адрес для нашего кода собирается из тех же двух переменных, что и секрет движка, если
# EMBED_BASE_URL не задан отдельно, — чтобы проверялся ТОТ ЖЕ эндпоинт, куда пойдёт ai_embed.
[ -n "$BASE" ] || BASE="${EMBED_HOST:-}${EMBED_PATH%/embeddings}"

if [ -z "$BASE" ] || [ -z "$KEY" ] || [ -z "$MODEL" ]; then
  echo "проверка эмбеддера: не заданы адрес, ключ или модель" >&2
  exit 1
fi

OUT=$(printf 'url = "%s/embeddings"\nheader = "Authorization: Bearer %s"\nheader = "Content-Type: application/json"\ndata = "{\\"model\\":\\"%s\\",\\"dimensions\\":%s,\\"input\\":[\\"ping\\"]}"\nsilent\nshow-error\nmax-time = 60\n' \
        "${BASE%/}" "$KEY" "$MODEL" "${EMBED_DIM:-1024}" | curl --config - 2>/dev/null)

GOT=$(printf '%s' "$OUT" | python3 -c 'import json,sys
try:
    d = json.load(sys.stdin)
except Exception:
    print(""); raise SystemExit
print(d.get("model") or "")' 2>/dev/null)

if [ -z "$GOT" ]; then
  echo "проверка эмбеддера: сервис не ответил или ответ не разобран" >&2
  exit 1
fi
if [ "$GOT" != "$MODEL" ]; then
  echo "🔴 ЭМБЕДДЕР ОТДАЁТ ДРУГУЮ МОДЕЛЬ: просим «$MODEL», получаем «$GOT»." >&2
  echo "   Векторы этих моделей несравнимы. Либо поправьте EMBED_MODEL, либо верните модель на сервере." >&2
  exit 1
fi
echo "проверка эмбеддера: модель совпала ($GOT)"
