-- Бэкап и догон регистра РеализацияТМЦ (+ документ и табчасти).
-- Мутация корпуса — штатный такт (corpus_build + merge) после этой переотметки.
-- Доки: sql/statements/insert, sql/statements/delete, sql/statements/merge_into.
--
-- Запуск (таймер пайплайна остановлен; DSN rw):
--   psql "$SERENEDB_DSN" -v ON_ERROR_STOP=1 -f work/packet/repair-corpus-period-lag.sql

\set ON_ERROR_STOP on

CREATE TABLE IF NOT EXISTS bak_corpus_реализациятмц_20260818 AS
SELECT * FROM search_corpus
 WHERE src_table = 'accumulationregister_реализациятмц';

CREATE TABLE IF NOT EXISTS bak_corpus_doc_реализациятмц_20260818 AS
SELECT * FROM search_corpus
 WHERE src_table = 'document_реализациятмц'
    OR src_table IN (SELECT src_table FROM search_tables
                     WHERE parent = 'document_реализациятмц');

SELECT 'backup_reg' AS k, count(*) FROM bak_corpus_реализациятмц_20260818
UNION ALL
SELECT 'backup_doc', count(*) FROM bak_corpus_doc_реализациятмц_20260818;

-- Сверка витрина = сестра RecordType (истина 1С / агента).
SELECT 'wrapper' AS src, count(*) AS n FROM query_table('accumulationregister_реализациятмц')
UNION ALL
SELECT 'recordtype', count(*) FROM query_table('accumulationregister_реализациятмц_recordtype')
UNION ALL
SELECT 'corpus', count(*) FROM search_corpus
 WHERE src_table = 'accumulationregister_реализациятмц';

CREATE TABLE IF NOT EXISTS search_changed_sources (src_table VARCHAR);

-- Переотметка: то, что перепись уже назвала задержанным.
INSERT INTO search_changed_sources
SELECT lower(entity) FROM search_coverage
 WHERE причина IN ('собралось не полностью', 'не собралось в корпус',
                   'в корпусе больше витрины')
   AND lower(entity) NOT IN (SELECT src_table FROM search_changed_sources);

-- Табличные части владельцев, уже попавших в список.
INSERT INTO search_changed_sources
SELECT t.src_table FROM search_tables t
 WHERE t.parent IN (SELECT src_table FROM search_changed_sources)
   AND t.src_table NOT IN (SELECT src_table FROM search_changed_sources);

-- Инцидент okna 18.08: регистр + документ реализации и его части.
INSERT INTO search_changed_sources
SELECT x FROM (
  SELECT 'accumulationregister_реализациятмц' AS x
  UNION ALL SELECT 'document_реализациятмц'
  UNION ALL SELECT src_table FROM search_tables
   WHERE parent IN ('document_реализациятмц', 'accumulationregister_реализациятмц')
      OR src_table IN ('document_реализациятмц', 'accumulationregister_реализациятмц')
) u
 WHERE x NOT IN (SELECT src_table FROM search_changed_sources);

DELETE FROM search_quality WHERE k = 'changed_sources_ok';
INSERT INTO search_quality VALUES (
  'changed_sources_ok', 1,
  'список полон: догон repair-corpus-period-lag');

SELECT 'marked' AS k, count(*) FROM search_changed_sources;
SELECT src_table FROM search_changed_sources
 WHERE src_table LIKE '%реализациятмц%'
 ORDER BY 1;

-- Дни, где корпус и витрина расходятся. После merge такта здесь 0 строк.
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
