-- Э1б: один psql на раунд досчёта векторов (todo + transfer + ai_embed + cleanup).
-- Доки: ai_embed — Sql › Functions › AI Functions;
--       SET threads — Cookbook › Performance › OOM;
--       UPDATE … FROM — Sql › UPDATE;
--       partial reading — Data import › Parquet › partial-reading.
-- Параметры psql (-v): tbl, src, tag, tag_old, tag_todo, tag_part0, kcols,
--   on_clause, ord, rows_per_batch, budget, maxlen, model, sec0, dim,
--   thr_sql (может быть «--»), rows_where (пусто или AND (...)), light_cols,
--   use_rows_filter (0|1).
\set ON_ERROR_STOP on

-- ── 1. Докатка staging → цель (текущая и прежняя метки) ─────────────────────
SELECT 'UPDATE ' || :'tbl' || ' t SET emb = p.emb FROM ' || table_name ||
       ' p WHERE ' || :'on_clause' || ' AND t.emb IS NULL;'
  FROM duckdb_tables()
 WHERE (table_name LIKE :'tag' || '\_part\_%' ESCAPE '\'
     OR table_name LIKE :'tag_old' || '\_part\_%' ESCAPE '\')
   AND database_name = current_database();
\gexec

-- ── 2. Остаток без вектора (лёгкая проекция при фильтре) ────────────────────
\if :use_rows_filter
SELECT count(*)::bigint AS n_left, (count(*) > 0) AS has_left
  FROM (SELECT :light_cols FROM :"tbl" WHERE emb IS NULL) :"tbl"
 WHERE true :rows_where;
\else
SELECT count(*)::bigint AS n_left, (count(*) > 0) AS has_left FROM :"tbl" WHERE emb IS NULL;
\endif
\gset left_

\if :{?left_n_left}
\else
\echo 'embed_missing.sql: не удалось прочитать остаток'
\quit 1
\endif

\if :left_has_left
\else
-- n=0: уборка и выход
SELECT 'DROP TABLE IF EXISTS ' || table_name || ';'
  FROM duckdb_tables()
 WHERE (table_name LIKE :'tag' || '\_part\_%' ESCAPE '\'
     OR table_name = :'tag' || '_todo'
     OR table_name LIKE :'tag_old' || '\_part\_%' ESCAPE '\'
     OR table_name = :'tag_old' || '_todo')
   AND database_name = current_database();
\gexec
SELECT json_object(
  'таблица', :'tbl',
  'было_без_вектора', 0,
  'осталось', 0,
  'вектор_невозможен', 0,
  'session_rows', 0)::text AS result;
\quit 0
\endif

-- ── 3. Уборка рабочих таблиц перед новым todo ───────────────────────────────
SELECT 'DROP TABLE IF EXISTS ' || table_name || ';'
  FROM duckdb_tables()
 WHERE (table_name LIKE :'tag' || '\_part\_%' ESCAPE '\'
     OR table_name = :'tag' || '_todo'
     OR table_name LIKE :'tag_old' || '\_part\_%' ESCAPE '\'
     OR table_name = :'tag_old' || '_todo')
   AND database_name = current_database();
\gexec

-- ── 4. План пачек ───────────────────────────────────────────────────────────
CREATE OR REPLACE TABLE :"tag_todo" AS
  WITH s AS (
         SELECT :kcols, :src AS txt
           FROM :"tbl"
          WHERE emb IS NULL :rows_where
       ),
       ok AS (
         SELECT * FROM s
          WHERE txt IS NOT NULL AND length(txt) BETWEEN 1 AND :maxlen
       ),
       w AS (
         SELECT *, row_number() OVER (ORDER BY :ord) - 1 AS rn,
                sum(length(txt)) OVER (ORDER BY :ord ROWS BETWEEN UNBOUNDED PRECEDING
                                                              AND 1 PRECEDING) AS cum
           FROM ok
       )
  SELECT * EXCLUDE (rn, cum),
         (rn / :rows_per_batch) + (coalesce(cum, 0) / :budget) AS chunk
    FROM w;

-- ── 5. Невозможные строки (длина / NULL / пусто) ────────────────────────────
\if :use_rows_filter
SELECT count(*)::bigint AS n_impossible
  FROM :"tbl"
 WHERE emb IS NULL :rows_where
   AND ((:src) IS NULL OR length(:src) = 0 OR length(:src) > :maxlen);
\else
SELECT count(*)::bigint AS n_impossible
  FROM :"tbl"
 WHERE emb IS NULL
   AND ((:src) IS NULL OR length(:src) = 0 OR length(:src) > :maxlen);
\endif
\gset imp_

-- ── 6. Одна сессия: МАССОВЫЙ ai_embed одним оператором на раунд (26.08.1) ──
-- [замер 29.08] дефект 26.07.3 (Vector::SetSize при >16–32 строк) на 26.08.1
-- не воспроизводится: 64/512 строк одним оператором живьём. Решение владельца:
-- только массовый нативный вызов; порция раунда = :chunks_round чанков.
\set ON_ERROR_STOP off
:thr_sql
CREATE OR REPLACE TABLE :"tag_part0" AS SELECT * FROM :"tag_todo" WHERE false;
ALTER TABLE :"tag_part0" DROP COLUMN txt;
ALTER TABLE :"tag_part0" DROP COLUMN chunk;
ALTER TABLE :"tag_part0" ADD COLUMN emb FLOAT[:dim];
INSERT INTO :"tag_part0"
SELECT * EXCLUDE (txt, chunk),
       ai_embed(txt, :'model', :'sec0')::FLOAT[:dim]
  FROM :"tag_todo"
 WHERE chunk <= :chunks_round;
\set ON_ERROR_STOP on

SELECT count(*)::bigint AS session_rows FROM :"tag_part0";
\gset sess_

-- ── 7. Transfer + финальный остаток + уборка ───────────────────────────────
SELECT 'UPDATE ' || :'tbl' || ' t SET emb = p.emb FROM ' || table_name ||
       ' p WHERE ' || :'on_clause' || ' AND t.emb IS NULL;'
  FROM duckdb_tables()
 WHERE (table_name LIKE :'tag' || '\_part\_%' ESCAPE '\'
     OR table_name LIKE :'tag_old' || '\_part\_%' ESCAPE '\')
   AND database_name = current_database();
\gexec

\if :use_rows_filter
SELECT count(*)::bigint AS n_after
  FROM (SELECT :light_cols FROM :"tbl" WHERE emb IS NULL) :"tbl"
 WHERE true :rows_where;
\else
SELECT count(*)::bigint AS n_after FROM :"tbl" WHERE emb IS NULL;
\endif
\gset after_

SELECT 'DROP TABLE IF EXISTS ' || table_name || ';'
  FROM duckdb_tables()
 WHERE (table_name LIKE :'tag' || '\_part\_%' ESCAPE '\'
     OR table_name = :'tag' || '_todo'
     OR table_name LIKE :'tag_old' || '\_part\_%' ESCAPE '\'
     OR table_name = :'tag_old' || '_todo')
   AND database_name = current_database();
\gexec

SELECT json_object(
  'таблица', :'tbl',
  'было_без_вектора', :left_n_left,
  'осталось', :after_n_after,
  'вектор_невозможен', coalesce(:imp_n_impossible, 0),
  'session_rows', coalesce(:sess_session_rows, 0))::text AS result;
