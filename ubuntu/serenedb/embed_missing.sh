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
# Использование: embed_missing.sh <таблица> <колонка-источник> [потоков]
set -u
TBL="$1"; SRC="$2"; N="${3:-8}"
DSN="${SERENEDB_DSN:-host=127.0.0.1 port=7890 user=postgres dbname=postgres}"
MODEL="${EMBED_MODEL:-text-embedding-v4}"
DIM="${EMBED_DIM:-1024}"

left() { psql "$DSN" -tA -c "SELECT count(*) FROM $TBL WHERE emb IS NULL" 2>/dev/null; }

n=$(left)
[ -z "$n" ] && { echo "не удалось прочитать $TBL" >&2; exit 1; }
[ "$n" = "0" ] && { echo "{\"таблица\":\"$TBL\",\"досчитано\":0,\"было_без_вектора\":0}"; exit 0; }

# Ключ строки — `rowid` движка: он уникален внутри одного прогона, а нам больше и не надо.
psql "$DSN" -q -c "CREATE OR REPLACE TABLE emb_todo_$$ AS
  SELECT rowid AS rid, $SRC AS txt,
         ((row_number() OVER (ORDER BY rowid)) - 1) / 10 AS chunk
  FROM $TBL WHERE emb IS NULL;" || exit 1

for w in $(seq 0 $((N - 1))); do
  psql "$DSN" -q -v ON_ERROR_STOP=0 <<SQL >/dev/null 2>&1 &
SELECT 'UPDATE $TBL t SET emb = s.e FROM (SELECT rid, ai_embed(txt, ''$MODEL'', ''qwen'')::FLOAT[$DIM] e
        FROM emb_todo_$$ WHERE chunk = ' || chunk || ') s WHERE t.rowid = s.rid;'
FROM (SELECT DISTINCT chunk FROM emb_todo_$$ WHERE chunk % $N = $w ORDER BY 1)
\gexec
SQL
done
wait

after=$(left)
psql "$DSN" -q -c "DROP TABLE IF EXISTS emb_todo_$$;"
echo "{\"таблица\":\"$TBL\",\"было_без_вектора\":$n,\"осталось\":$after}"
