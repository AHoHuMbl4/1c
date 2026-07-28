#!/bin/bash
# Досчитать векторы тем строкам, у которых их нет — штатной функцией движка `ai_embed`.
#
# Почему это shell, а не SQL одним запросом: `ai_embed` САМ группирует строки в пачки, а
# провайдер принимает не больше 10 за раз и не длиннее 33 000 символов на вход
# ([замер 27.07]: пачка крупнее — `batch size is invalid`). Ручки размера пачки в
# настройках движка нет, поэтому режем сами — генерацией запросов средствами SQL.
# Данные при этом НЕ покидают движок: текст берётся и вектор кладётся внутри базы,
# наружу уходит только вызов модели, что п. 20 разрешает явно.
#
# Параллельность — потому что вызов сетевой и ждёт: [замер] 1 поток — 6,7 строк/с,
# 2 потока — 12,7, 12 потоков — около 30. Дальше упирается в провайдера.
#
# 🔴 КАЖДЫЙ ПОТОК ПИШЕТ В СВОЮ ТАБЛИЦУ, и только в конце результат переносится одним
# запросом. Это не стиль, а обход падения движка: [замер 28.07] четырнадцать
# параллельных `UPDATE ... FROM (SELECT ai_embed(...))` в ОДНУ таблицу уронили движок
# с `SIGSEGV` (systemd поднял через 3 с, данные уцелели, но досчёт встал молча).
# Запись у движка однопоточная; раздельные таблицы конфликта не создают.
#
# Использование: embed_missing.sh <таблица> <колонка-источник> [потоков]
set -u
TBL="$1"; SRC="$2"; N="${3:-8}"
DSN="${SERENEDB_DSN:-host=127.0.0.1 port=7890 user=postgres dbname=postgres}"
MODEL="${EMBED_MODEL:-text-embedding-v4}"
DIM="${EMBED_DIM:-1024}"
TAG="emb_$$"

left() { psql "$DSN" -tA -c "SELECT count(*) FROM $TBL WHERE emb IS NULL" 2>/dev/null; }

n=$(left)
[ -z "$n" ] && { echo "не удалось прочитать $TBL" >&2; exit 1; }
[ "$n" = "0" ] && { echo "{\"таблица\":\"$TBL\",\"было_без_вектора\":0,\"осталось\":0}"; exit 0; }

# Ключ строки — `rowid` движка: он уникален внутри одного прогона, а нам больше и не надо.
psql "$DSN" -q -c "CREATE OR REPLACE TABLE ${TAG}_todo AS
  SELECT rowid AS rid, $SRC AS txt,
         ((row_number() OVER (ORDER BY rowid)) - 1) / 10 AS chunk
  FROM $TBL WHERE emb IS NULL;" || exit 1

for w in $(seq 0 $((N - 1))); do
  psql "$DSN" -q -v ON_ERROR_STOP=0 <<SQL >/dev/null 2>&1 &
CREATE OR REPLACE TABLE ${TAG}_part_$w (rid BIGINT, emb FLOAT[$DIM]);
SELECT 'INSERT INTO ${TAG}_part_$w SELECT rid, ai_embed(txt, ''$MODEL'', ''qwen'')::FLOAT[$DIM]
        FROM ${TAG}_todo WHERE chunk = ' || chunk || ';'
FROM (SELECT DISTINCT chunk FROM ${TAG}_todo WHERE chunk % $N = $w ORDER BY 1)
\gexec
SQL
done
wait

# Перенос — одним запросом на поток, последовательно: писатель у движка один.
psql "$DSN" -tA -c "SELECT 'UPDATE $TBL t SET emb = p.emb FROM ' || table_name ||
       ' p WHERE t.rowid = p.rid AND t.emb IS NULL;'
     FROM duckdb_tables() WHERE table_name LIKE '${TAG}\_part\_%' ESCAPE '\'" \
  | psql "$DSN" -q >/dev/null 2>&1

after=$(left)
psql "$DSN" -tA -c "SELECT 'DROP TABLE IF EXISTS ' || table_name || ';' FROM duckdb_tables()
     WHERE table_name LIKE '${TAG}\_%' ESCAPE '\'" | psql "$DSN" -q >/dev/null 2>&1
echo "{\"таблица\":\"$TBL\",\"было_без_вектора\":$n,\"осталось\":${after:-?}}"
