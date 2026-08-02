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

# 🔴 ПРОВЕРЯЕТСЯ ТА ЖЕ ДВЕРЬ, В КОТОРУЮ ПОЙДЁТ ДВИЖОК — `EMBED_HOST` + `EMBED_PATH`,
# ровно то, что уходит в секрет `TYPE openai (base_url, embeddings_path)`. Проверять
# соседний адрес бессмысленно: [замер 02.08] у нового сервиса путь движка `/v1/embeddings`,
# а вопросы наш код шлёт в `/embed` — это РАЗНЫЕ двери одного сервиса, и совпадение
# моделей на одной ничего не говорит о другой.
URL="${EMBED_HOST:-}${EMBED_PATH:-}"
[ -n "$URL" ] || URL="${EMBED_BASE_URL:-}/embeddings"
KEY="${EMBED_API_KEY:-}"
[ -n "$KEY" ] || KEY="$(printf '%s' "${EMBED_API_KEYS:-}" | cut -d, -f1 | tr -d ' ')"
MODEL="${EMBED_MODEL:-}"

if [ -z "$URL" ] || [ -z "$MODEL" ]; then
  echo "проверка эмбеддера: не заданы адрес или модель" >&2
  exit 1
fi

# 🔴 ИМЯ МОДЕЛИ БЕРЁТСЯ ИЗ `/health`, А НЕ ИЗ ОТВЕТА НА ЗАПРОС.
# [замер 02.08] два сервиса подряд повели себя по-разному, и оба — молча:
#   * llama.cpp при незнакомом имени ПОДСТАВЛЯЛ своё (просим Q8_0 — считает Q6_K);
#   * нынешний сервис ЭХОМ возвращает то имя, которое попросили, — подтвердил даже
#     несуществующую «Qwen3-Embedding-4B-f16».
# То есть поле `model` в ответе не является свидетельством ни в ту, ни в другую сторону.
# `/health` называет модель, которая реально загружена, и открыт без ключа.
HEALTH_URL="${EMBED_HEALTH_URL:-}"
if [ -z "$HEALTH_URL" ] && [ -n "${EMBED_HOST:-}" ]; then HEALTH_URL="${EMBED_HOST%/}/health"; fi

GOT=""
if [ -n "$HEALTH_URL" ]; then
  GOT=$(printf 'url = "%s"\nuser-agent = "%s"\nsilent\nmax-time = 30\n' \
          "$HEALTH_URL" "${EMBED_UA:-curl/8.5.0}" | curl --config - 2>/dev/null \
        | python3 -c 'import json,sys
try: print(json.load(sys.stdin).get("model") or "")
except Exception: print("")' 2>/dev/null)
fi

# Запасной путь: сервис без `/health` — тогда сверяем по ответу, зная его слабость.
if [ -z "$GOT" ]; then
  GOT=$(printf 'url = "%s"\nheader = "Authorization: Bearer %s"\nheader = "Content-Type: application/json"\nuser-agent = "%s"\ndata = "{\\"model\\":\\"%s\\",\\"dimensions\\":%s,\\"input\\":[\\"ping\\"]}"\nsilent\nshow-error\nmax-time = 60\n' \
          "$URL" "$KEY" "${EMBED_UA:-curl/8.5.0}" "$MODEL" "${EMBED_DIM:-1024}" | curl --config - 2>/dev/null \
        | python3 -c 'import json,sys
try: print(json.load(sys.stdin).get("model") or "")
except Exception: print("")' 2>/dev/null)
fi

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
