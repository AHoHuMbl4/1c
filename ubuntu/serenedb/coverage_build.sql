\timing on
\set ON_ERROR_STOP on

-- ПЕРЕПИСЬ ПОЛНОТЫ: сколько данных 1С дошло до поиска и где потерялось.
--
-- Это исполнение пункта 13 TARGET.md. Требование не «не терять» — терять иногда
-- приходится, — а «потеря обязана быть ВИДНА». Молчаливая потеря приравнена контрактом
-- к неверному ответу.
--
-- [замер 28.07, до этой работы] в 1С объявлено 103 958 строк по 235 сущностям, до
-- корпуса дошло 97 965 по 226. Потеряно 5 993 строки и девять сущностей, и у всех
-- девяти поле `problem` было ПУСТО. Среди потерянных — `AccountingRegister_Хозрасчетный`,
-- главная книга: на вопрос про обороты по счёту отвечать нечем, и клиенту не сказано.
--
-- Считается ЦЕЛИКОМ ВНУТРИ ДВИЖКА (п. 20): ни одна строка не покидает базу.

-- ============ 1. СКОЛЬКО СТРОК В ВИТРИНЕ ============
-- Тем же приёмом, что `res_seen` в resolver_build.sql: `query_table($1)` берёт имя
-- литералом, поэтому список таблиц обходится генерацией команд, а не циклом в питоне.
-- [замер] 226 таблиц — меньше секунды.
CREATE OR REPLACE TABLE cov_mart (tbl VARCHAR, n_rows BIGINT);
PREPARE p_cov AS INSERT INTO cov_mart SELECT $1::VARCHAR, count(*) FROM query_table($1);
SELECT 'EXECUTE p_cov(' || quote_literal(table_name) || ');'
FROM duckdb_tables()
WHERE database_name = 'postgres'
  AND EXISTS (SELECT 1 FROM tmp3_ent e WHERE e.entity = lower(table_name))
\gexec

-- ============ 2. ЦЕПОЧКА ПО КАЖДОЙ СУЩНОСТИ ============
-- 🔴 lower() ОБЯЗАТЕЛЕН. `base_profile.entity` записан в исходном регистре
-- (`Catalog_ПоляФормСтатистики`), а имена таблиц витрины и `search_sources` — в нижнем.
-- Соединение без `lower()` не сходится НИ ОДНОЙ строкой и выглядит как тотальная потеря:
-- я на этом споткнулся сегодня и чуть не записал 235 сущностей в пропавшие.
CREATE OR REPLACE TABLE search_coverage AS
WITH ent AS (
  -- Слева — то, что ОБЪЯВЛЕНО платформой, а не то, что мы сумели прочитать. Иначе
  -- перепись считала бы полноту по себе самой и всегда показывала бы «всё на месте».
  SELECT e.entity AS ent, b.rows AS in_1c, b.problem
  FROM tmp3_ent e
  LEFT JOIN base_profile b ON lower(b.entity) = e.entity),
 mart AS (SELECT lower(tbl) AS ent, n_rows FROM cov_mart),
 corp AS (SELECT src_table AS ent, count(*) AS n,
                 count(*) FILTER (WHERE emb IS NOT NULL) AS n_emb
          FROM search_corpus GROUP BY 1),
 idx  AS (SELECT src_table AS ent, count(*) AS n FROM search_idx GROUP BY 1)
SELECT ent AS entity,
       coalesce(e.in_1c, 0)      AS в_1С,
       coalesce(m.n_rows, 0)     AS в_витрине,
       coalesce(c.n, 0)          AS в_корпусе,
       coalesce(i.n, 0)          AS в_индексе,
       coalesce(c.n_emb, 0)      AS с_вектором,
       -- ============ 3. ПРИЧИНА — СТРУКТУРНО, А НЕ СПИСКОМ ИМЁН ============
       -- Порядок ветвей значим: он идёт по течению данных, поэтому называется ПЕРВОЕ
       -- место, где данные встали, а не последнее, где их нет.
       CASE
         WHEN e.in_1c = -1                       THEN 'закрыто правами в 1С'
         WHEN coalesce(e.in_1c, 0) = 0           THEN 'в 1С нет строк'
         WHEN m.n_rows IS NULL                   THEN 'не загрузилось из 1С'
         WHEN m.n_rows = 0                       THEN 'выгрузка пуста'
         WHEN coalesce(c.n, 0) = 0               THEN 'не собралось в корпус'
         WHEN c.n < m.n_rows                     THEN 'собралось не полностью'
         WHEN coalesce(i.n, 0) < c.n             THEN 'не опубликовано в индекс'
         WHEN c.n_emb < c.n                      THEN 'нет вектора'
         ELSE NULL
       END AS причина
FROM ent e
LEFT JOIN mart m USING (ent)
LEFT JOIN corp c ON c.ent = e.ent
LEFT JOIN idx  i ON i.ent = e.ent;

-- 🔴 В `base_profile` причина НЕ ПИШЕТСЯ, хотя соблазн есть: поле `problem` там пусто у
-- всех девяти потерянных, и именно поэтому потеря выглядела как «так и задумано».
-- Но `serene_sync.py:109` делает `DROP TABLE base_profile` при каждом прогоне и пишет
-- её заново. Наша запись прожила бы до ближайшего синка и всё это время выглядела бы
-- постоянной — то есть мы завели бы ещё один документ, который уверенно врёт.
-- Хозяин `base_profile` — синк; перепись живёт в своей таблице и пересчитывается сама.

-- ============ 4. ИТОГ — ЧИСЛАМИ В БАЗУ ============
DELETE FROM search_quality WHERE k LIKE 'cov_%';
INSERT INTO search_quality
            SELECT 'cov_rows_1c',    sum(в_1С) FILTER (WHERE в_1С > 0),    'строк объявлено в 1С'
            FROM search_coverage
UNION ALL   SELECT 'cov_rows_search', sum(в_корпусе),                      'строк дошло до поиска'
            FROM search_coverage
UNION ALL   SELECT 'cov_rows_lost',  sum(в_1С - в_корпусе) FILTER (WHERE в_1С > в_корпусе),
                   'строк не дошло' FROM search_coverage
UNION ALL   SELECT 'cov_ent_lost',   count(*) FILTER (WHERE в_1С > 0 AND в_корпусе = 0),
                   'сущностей не дошло совсем' FROM search_coverage
UNION ALL   SELECT 'cov_ent_denied', count(*) FILTER (WHERE в_1С = -1),
                   'сущностей закрыто правами' FROM search_coverage;

SELECT k, v, note FROM search_quality WHERE k LIKE 'cov_%' ORDER BY k;

-- Поимённо — то, что не дошло. Без этого списка число «5 993» ничего не говорит о том,
-- на какие вопросы система теперь не ответит.
SELECT entity AS сущность, в_1С, в_витрине, в_корпусе, причина
FROM search_coverage
WHERE причина IS NOT NULL AND причина <> 'закрыто правами в 1С' AND в_1С > 0
ORDER BY в_1С - в_корпусе DESC
LIMIT 20;
