\timing on
\set ON_ERROR_STOP on

-- ПЕРЕНОС СОБРАННОГО КОРПУСА В БОЕВОЙ И ПУБЛИКАЦИЯ ПОИСКУ.
-- Запускается после `corpus_build.sql` (он строит `tmp3_corpus`) и `pick_money_col.py`.

-- Условие `t.doc_hash <> s.doc_hash` обязано остаться: без него молча переписываются и
-- пересчитываются все строки, а не изменившиеся (п. 13).
-- `emb = NULL` у изменившихся — не потеря, а честная отметка «вектор ещё не посчитан»:
-- она видна запросом `count(*) FILTER (WHERE emb IS NULL)`, тогда как оставленный старый
-- вектор при новом тексте был бы тихим расхождением смысла и текста.
MERGE INTO search_corpus AS t
USING tmp3_corpus AS s
ON t.src_table = s.src_table AND t.row_key = s.row_key
WHEN MATCHED AND t.doc_hash <> s.doc_hash THEN
     UPDATE SET doc = s.doc, refs = s.refs, doc_hash = s.doc_hash,
                amount = s.amount, doc_date = s.doc_date, emb = NULL
WHEN NOT MATCHED THEN
     INSERT (src_table, row_key, doc, refs, doc_hash, amount, doc_date, emb)
     VALUES (s.src_table, s.row_key, s.doc, s.refs, s.doc_hash, s.amount, s.doc_date, NULL);

-- Исчезнувшие строки удаляет БАЗА одним запросом — и только по тем сущностям, которые
-- в этот раз собирались. Иначе неполная выгрузка из 1С вычистила бы живые данные.
DELETE FROM search_corpus c
WHERE c.src_table IN (SELECT tbl FROM tmp3_src)
  AND NOT EXISTS (SELECT 1 FROM tmp3_corpus t
                  WHERE t.src_table = c.src_table AND t.row_key = c.row_key);

-- Публикация свежих записей поиску — штатной командой движка. Именно REFRESH_INDEX
-- (один индекс), а НЕ REFRESH_TABLE: последний на таблице с вектором дал 34 ГБ и смерть
-- движка (замер 27.07).
VACUUM (REFRESH_INDEX) search_idx;

SELECT 'корпус' AS шаг, count(*) AS строк, count(DISTINCT src_table) AS сущностей,
       count(*) FILTER (WHERE emb IS NULL) AS ждут_вектора FROM search_corpus;
