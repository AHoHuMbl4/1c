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
# 🔴 СВЕРКИ МОДЕЛИ МАЛО — НУЖЕН ЖИВОЙ ВЫЗОВ С КЛЮЧОМ (15.08). `/health` на этом сервисе
# открыт без авторизации, и проверка по одному `/health` вернула 0 при НЕВАЛИДНОМ ключе:
# ложный зелёный прибор, смысловой путь в бою был бы выключен молча. Поэтому после сверки
# модели делается минимальный ЖИВОЙ вызов на каждую дверь с её ключом, и код 0 отдаётся
# только за реальный вектор нужной размерности. 401/403 называются явно: «ключ не годится».
#
# Использование: embed_check.sh   (0 — модель та и оба ключа дают вектор нужной dim)
# Окружение:     EMBED_BASE_URL, EMBED_API_KEY|EMBED_API_KEYS, EMBED_MODEL
set -u

# 🔴 СНАЧАЛА ФОРМА АДРЕСА. [замер 17.08] EMBED_HOST=gpu-erw.timpul.pro без схемы
# давал curl код 000 на двери движка; embed_check это ловил, но уже внутри такта —
# firstbuild уходил в «repeated too quickly», и три дня никто не видел. Форма
# (схема+хост+порт) проверяется ДО curl, чтобы отказ был мгновенным и понятным.
_BOX_TUNE="$(cd "$(dirname "$0")" && pwd)/box_tune.sh"
if [ -f "$_BOX_TUNE" ]; then
  # shellcheck disable=SC1090
  . "$_BOX_TUNE"
  embed_hosts_form_check || exit 1
fi
if [ "${EMBED_CHECK_FORM_ONLY:-}" = 1 ]; then
  echo "проверка эмбеддера: форма EMBED_HOST верна"
  exit 0
fi

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

# 🔴 ЖИВОЙ ВЫЗОВ С КЛЮЧОМ — ПО ОДНОМУ НА ДВЕРЬ. `/health` ключа не спрашивает (живой
# случай 15.08: модель совпала, оба ключа — «Invalid API key»), поэтому пригодность
# ключа доказывается только вектором нужной размерности из ответа. Проверяются обе
# двери, потому что ключи у них разные: вопросы — `/embed` с `EMBED_API_KEY`
# (наш сервис ответов), документы — `/v1/embeddings` с `EMBED_API_KEYS` (движок,
# `ai_embed`). Тело запроса повторяет боевое (`_embed_request` в `serene_ask.py`).
live_door() {
  # $1 — адрес, $2 — ключ, $3 — тело JSON, $4 — имя двери для сообщения
  local out code body verdict
  out=$(printf 'url = "%s"\nheader = "Authorization: Bearer %s"\nheader = "Content-Type: application/json"\nuser-agent = "%s"\ndata = %s\nsilent\nshow-error\nmax-time = 60\nwrite-out = "\\n%%{http_code}"\n' \
          "$1" "$2" "${EMBED_UA:-curl/8.5.0}" "$3" | curl --config - 2>/dev/null)
  code=$(printf '%s' "$out" | tail -n1)
  body=$(printf '%s' "$out" | sed '$d')
  case "$code" in
    401|403)
      echo "🔴 КЛЮЧ НЕ ГОДИТСЯ ($4): сервис ответил $code. Обновите ключ в /etc/1c-embed.env." >&2
      return 1;;
    200) ;;
    *)
      echo "проверка эмбеддера: $4 ответила кодом «$code» — сервис нездоров или ответ не разобран" >&2
      return 1;;
  esac
  verdict=$(printf '%s' "$body" | python3 -c 'import json,sys
want = int(sys.argv[1])
try:
    d = json.load(sys.stdin)
    v = d["embeddings"][0] if "embeddings" in d else d["data"][0]["embedding"]
    print("ok" if len(v) == want else "dim:%d" % len(v))
except Exception:
    print("bad")' "${EMBED_DIM:-1024}" 2>/dev/null)
  case "$verdict" in
    ok) echo "проверка эмбеддера: $4 — живой вектор, dim ${EMBED_DIM:-1024}"; return 0;;
    dim:*)
      echo "🔴 $4: вектор ДРУГОЙ размерности ($verdict, ждём ${EMBED_DIM:-1024}) — пространство несравнимо." >&2
      return 1;;
    *)
      echo "проверка эмбеддера: $4 вернула 200 без вектора — ответ не разобран" >&2
      return 1;;
  esac
}

QURL="${EMBED_BASE_URL:-}${EMBED_QUERY_PATH:-/embed}"
if [ -z "${EMBED_BASE_URL:-}" ] || [ -z "${EMBED_API_KEY:-}" ]; then
  echo "проверка эмбеддера: не заданы EMBED_BASE_URL или EMBED_API_KEY (дверь вопроса)" >&2
  exit 1
fi
live_door "$QURL" "$EMBED_API_KEY" \
  '"{\"texts\":[\"ping\"],\"is_query\":true,\"dim\":'"${EMBED_DIM:-1024}"'}' \
  "дверь вопроса $QURL" || exit 1

if [ -z "$KEY" ]; then
  echo "проверка эмбеддера: не задан EMBED_API_KEYS (дверь движка)" >&2
  exit 1
fi
live_door "$URL" "$KEY" \
  '"{\"model\":\"'"$MODEL"'\",\"dimensions\":'"${EMBED_DIM:-1024}"',\"input\":[\"ping\"]}"' \
  "дверь движка $URL" || exit 1
