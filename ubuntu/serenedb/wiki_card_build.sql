\set ON_ERROR_STOP on
-- Б1: паспорт-карточки сущностей для векторного отбора (PLAN_WIKI_CHOICE §2).
-- Доки: ai_embed — Sql › Functions › AI Functions;
--       vector ivf kNN — Sql › Indexes › Inverted › Vector Search.
--
-- Сборка ВНУТРИ движка (п. 20): имя + wiki_pages → card_text (стабильный текст под
-- вектор); оси search_refcols + меры search_measure_alias — отдельные колонки, в
-- хэш вектора не входят. MERGE идемпотентен: повторный прогон не сбрасывает emb.
-- Не в такте: отдельный прогон; досчёт emb — embed_missing.sh после этого файла.

CREATE TABLE IF NOT EXISTS search_wiki_entity_card (
  src_table VARCHAR PRIMARY KEY,
  name VARCHAR,
  description VARCHAR,
  axes VARCHAR,
  measures VARCHAR,
  card_text VARCHAR,
  covered INTEGER,
  emb FLOAT[1024]);

-- Оси-ссылки сущности (исходящие ref-колонки → цель).
CREATE OR REPLACE TABLE tmp_wiki_card_axes AS
SELECT r.src_table,
       string_agg(r.col || ' -> ' || r.target_src, ', ' ORDER BY r.col) AS axes
  FROM search_refcols r
 GROUP BY r.src_table;

-- Человеческие имена величин сущности.
CREATE OR REPLACE TABLE tmp_wiki_card_measures AS
SELECT m.src_table,
       string_agg(m.measure || ': ' || coalesce(m.aliases, ''), '; ' ORDER BY m.measure) AS measures
  FROM search_measure_alias m
 WHERE coalesce(m.aliases, '') <> ''
 GROUP BY m.src_table;

-- card_text под вектор = стабильная часть (name | description). axes/measures —
-- агрегаты (refcols + measure_alias): пересборка словаря/осей каждый такт не должна
-- жечь emb. Колонки живут отдельно, в индекс IVF входят через INCLUDE / лексику.
CREATE OR REPLACE TABLE tmp_wiki_card AS
SELECT t.src_table,
       t.label AS name,
       coalesce(w.body, '') AS description,
       coalesce(ax.axes, '') AS axes,
       coalesce(ms.measures, '') AS measures,
       concat_ws(' | ', t.label, nullif(w.body, '')) AS card_text,
       CASE WHEN w.page_id IS NOT NULL THEN 1 ELSE 0 END AS covered,
       NULL::FLOAT[1024] AS emb
  FROM search_tables t
  LEFT JOIN wiki_pages w ON w.page_id = t.src_table
  LEFT JOIN tmp_wiki_card_axes ax ON ax.src_table = t.src_table
  LEFT JOIN tmp_wiki_card_measures ms ON ms.src_table = t.src_table;

-- Карта переноса при смене формы: старый card_text держал axes|measures.
CREATE OR REPLACE TABLE tmp_wiki_card_emb_xfer AS
SELECT s.src_table, t.emb
FROM tmp_wiki_card s
JOIN search_wiki_entity_card t ON t.src_table = s.src_table
WHERE t.emb IS NOT NULL
  AND t.card_text IS DISTINCT FROM s.card_text
  AND (
    t.card_text = concat_ws(' | ', s.card_text, nullif(t.axes, ''), nullif(t.measures, ''))
    OR t.card_text = concat_ws(' | ', s.card_text, nullif(s.axes, ''), nullif(s.measures, ''))
    OR s.card_text = concat_ws(' | ', t.name, nullif(t.description, ''))
  );

-- Сброс emb только при изменении текста под вектор (CASE над FLOAT[1024] нельзя).
UPDATE search_wiki_entity_card AS t SET emb = NULL
  FROM tmp_wiki_card AS s
 WHERE t.src_table = s.src_table AND t.card_text IS DISTINCT FROM s.card_text
   AND NOT EXISTS (
     SELECT 1 FROM tmp_wiki_card_emb_xfer x WHERE x.src_table = t.src_table
   );

MERGE INTO search_wiki_entity_card AS t
USING tmp_wiki_card AS s
ON t.src_table = s.src_table
WHEN MATCHED AND (t.card_text IS DISTINCT FROM s.card_text
               OR t.name IS DISTINCT FROM s.name
               OR t.description IS DISTINCT FROM s.description
               OR t.axes IS DISTINCT FROM s.axes
               OR t.measures IS DISTINCT FROM s.measures
               OR t.covered IS DISTINCT FROM s.covered) THEN
     UPDATE SET name = s.name, description = s.description, axes = s.axes,
                measures = s.measures, card_text = s.card_text, covered = s.covered
WHEN NOT MATCHED THEN
     INSERT (src_table, name, description, axes, measures, card_text, covered, emb)
     VALUES (s.src_table, s.name, s.description, s.axes, s.measures,
             s.card_text, s.covered, NULL);

CREATE OR REPLACE TABLE tmp_wiki_card_emb_xfer_n AS
SELECT row_number() OVER (ORDER BY src_table) AS n, *
FROM tmp_wiki_card_emb_xfer;

SELECT 'UPDATE search_wiki_entity_card SET emb = x.emb FROM tmp_wiki_card_emb_xfer_n x '
       || 'WHERE search_wiki_entity_card.src_table = x.src_table '
       || 'AND search_wiki_entity_card.emb IS NULL AND x.n >= ' || (b * 1000)
       || ' AND x.n < ' || ((b + 1) * 1000) || ';'
FROM (SELECT i AS b FROM range(0, (SELECT ceil(count(*) / 1000.0)::BIGINT
                                   FROM tmp_wiki_card_emb_xfer_n)) t(i)) z
\gexec

DELETE FROM search_wiki_entity_card
 WHERE src_table NOT IN (SELECT src_table FROM tmp_wiki_card);

DROP TABLE IF EXISTS tmp_wiki_card_axes;
DROP TABLE IF EXISTS tmp_wiki_card_measures;
DROP TABLE IF EXISTS tmp_wiki_card;
DROP TABLE IF EXISTS tmp_wiki_card_emb_xfer;
DROP TABLE IF EXISTS tmp_wiki_card_emb_xfer_n;

SELECT 'wiki_card' AS шаг,
       count(*) AS карточек,
       sum(covered) AS с_wiki,
       count(*) - sum(covered) AS без_wiki,
       count(*) FILTER (WHERE emb IS NOT NULL) AS с_вектором,
       count(*) FILTER (WHERE emb IS NULL) AS без_вектора
  FROM search_wiki_entity_card;

-- IVF-индекс для kNN (cosine — штатный для text-embedding на сборке 26.07.3).
DROP INDEX IF EXISTS wiki_entity_card_emb_idx;
CREATE INDEX wiki_entity_card_emb_idx ON search_wiki_entity_card
  USING inverted (src_table, emb ivf (metric = 'cosine'))
  INCLUDE (name, description, axes, measures, covered);

VACUUM (REFRESH_TABLE) search_wiki_entity_card;
-- После embed_missing: VACUUM (REFRESH_INDEX) wiki_entity_card_emb_idx;

GRANT SELECT ON search_wiki_entity_card TO serene_ro;
