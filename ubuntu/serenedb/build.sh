#!/bin/bash
# НОЧНАЯ СБОРКА: корпус, резолвер, индекс — штатными средствами SereneDB.
#
# Это то, что запускает таймер вместо `serene_search_build.py`.
#
# Порядок шагов значим:
#   1. секреты — движку нужен токен шлюза 1С (`$metadata` он читает сам) и ключ эмбеддера;
#   2. корпус собирается во временные таблицы и там же сверяется;
#   3. слияние в боевой корпус по отпечатку + публикация индекса;
#   4. векторы досчитываются только новым строкам;
#   5. резолвер — тем же способом: значения по ключу, векторы только новым;
#   6. секреты удаляются. 🔴 Это обязательный шаг: «временный» секрет SereneDB
#      переживает сессию и виден любой другой, сам он не исчезает.
#
# Своего кода в сборке НЕ ОСТАЛОСЬ вовсе: шаг выбора денежной колонки убран вместе с
# самим понятием «денежная колонка» — строка несёт все свои величины, а какую считать,
# решается по вопросу в момент ответа.
set -u
cd "$(dirname "$0")" || exit 1

DSN="${SERENEDB_DSN:-host=127.0.0.1 port=7890 user=postgres dbname=postgres}"
export SERENEDB_DSN="$DSN"
GATE="${ETL_ODATA_BASE:-http://127.0.0.1:6011}"
WORKERS="${BUILD_EMBED_WORKERS:-8}"
t0=$(date +%s)

# Секреты подаются ФАЙЛОМ с правами 600, а не аргументом командной строки: в командной
# строке они видны любому `ps`.
umask 077
SEC=$(mktemp); trap 'rm -f "$SEC"' EXIT
{
  printf "CREATE OR REPLACE TEMPORARY SECRET odg (TYPE http, EXTRA_HTTP_HEADERS MAP{'Authorization': 'Bearer %s'});\n" "${ODG_GATEWAY_TOKEN:-}"
  printf "CREATE OR REPLACE TEMPORARY SECRET qwen (TYPE openai, api_key '%s', base_url '%s', embeddings_path '%s');\n" \
         "${ALIBABA_API_KEY:-}" "${EMBED_HOST:-https://dashscope-intl.aliyuncs.com}" \
         "${EMBED_PATH:-/compatible-mode/v1/embeddings}"
} > "$SEC"
psql "$DSN" -q -f "$SEC" || { echo "секреты не созданы" >&2; exit 1; }
rm -f "$SEC"

fail() { echo "СБОРКА ПРЕРВАНА: $1" >&2; psql "$DSN" -q -c "DROP SECRET IF EXISTS odg; DROP SECRET IF EXISTS qwen;"; exit 1; }

echo "== 1. корпус: движок читает \$metadata из $GATE и собирает текст"
psql "$DSN" -q -f corpus_build.sql || fail "сборка корпуса"

echo "== 2. слияние в боевой корпус и публикация индекса"
psql "$DSN" -q -f corpus_merge.sql || fail "слияние корпуса"

echo "== 3. векторы новым строкам корпуса"
./embed_missing.sh search_corpus doc "$WORKERS" || echo "предупреждение: часть векторов не посчитана" >&2

echo "== 4. резолвер"
psql "$DSN" -q -f resolver_build.sql || fail "сборка резолвера"
./embed_missing.sh resolver_index value "$WORKERS" || echo "предупреждение: часть векторов резолвера не посчитана" >&2

echo "== 5. секреты убраны"
psql "$DSN" -q -c "DROP SECRET IF EXISTS odg; DROP SECRET IF EXISTS qwen;"

# Итог такта — числами, а не словами: по ним видно, выполняется ли п. 17.
psql "$DSN" -tA -F' | ' -c "
SELECT 'корпус: ' || count(*) || ' строк, без вектора ' || count(*) FILTER (WHERE emb IS NULL)
FROM search_corpus
UNION ALL SELECT 'резолвер: ' || count(*) || ' значений, без вектора ' || count(*) FILTER (WHERE emb IS NULL)
FROM resolver_index"
echo "== такт занял $(( $(date +%s) - t0 )) с"
