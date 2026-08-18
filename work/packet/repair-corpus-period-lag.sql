-- Бэкап и сверка регистра РеализацияТМЦ. Мутацию корпуса НЕ делать, пока
-- держится flock 1c-serene-build-postgres.lock (эмбеддер пишет search_corpus).
-- Догон 18.08/19.08 — следующий такт после flock: таблица уже в
-- search_changed_sources. Доки: sql/statements/merge_into, query_table.
--
-- Запуск (flock свободен; DSN rw):
--   psql "$SERENEDB_DSN" -v ON_ERROR_STOP=1 -f work/packet/repair-corpus-period-lag.sql

\set ON_ERROR_STOP on

CREATE TABLE IF NOT EXISTS bak_corpus_реализациятмц_20260818 AS
SELECT * FROM search_corpus
 WHERE src_table = 'accumulationregister_реализациятмц';

SELECT 'backup_rows' AS k, count(*) FROM bak_corpus_реализациятмц_20260818;

-- Сверка витрина = сестра RecordType (истина 1С / агента).
SELECT 'wrapper' AS src, count(*) AS n FROM query_table('accumulationregister_реализациятмц')
UNION ALL
SELECT 'recordtype', count(*) FROM query_table('accumulationregister_реализациятмц_recordtype')
UNION ALL
SELECT 'corpus', count(*) FROM search_corpus
 WHERE src_table = 'accumulationregister_реализациятмц';

-- Дни, где корпус и витрина расходятся. После следующего merge здесь 0 строк.
WITH w AS (
  SELECT try_cast("Period" AS TIMESTAMP)::date AS d, count(*) AS n,
         round(sum(try_cast("Всего" AS DOUBLE))::numeric, 2) AS s
  FROM query_table('accumulationregister_реализациятмц') GROUP BY 1
), c AS (
  SELECT doc_date::date AS d, count(*) AS n,
         round(sum(coalesce(map_extract_value(nums,'Всего'),0))::numeric, 2) AS s
  FROM search_corpus WHERE src_table='accumulationregister_реализациятмц' GROUP BY 1
)
SELECT coalesce(w.d, c.d) AS d,
       coalesce(w.n,0) AS w_n, coalesce(c.n,0) AS c_n,
       coalesce(w.s,0) AS w_sum, coalesce(c.s,0) AS c_sum
FROM w FULL OUTER JOIN c USING (d)
WHERE coalesce(w.n,0) IS DISTINCT FROM coalesce(c.n,0)
ORDER BY 1;
