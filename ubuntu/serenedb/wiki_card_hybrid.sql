\set ON_ERROR_STOP on
-- Б3: гибридный пул — kNN top-N ∪ структурные носители оси, затем сужение.
-- Доки: Vector Search › k-nearest-neighbor (kNN); ai_embed — Sql › Functions › AI Functions.
-- Параметры: question, embed_model, embed_secret, embed_dim, embed_maxlen,
--   knn_limit, action_class, action_axis, want_agg, stem_dict, pick_limit.

WITH q AS (
  SELECT ai_embed(substr(:'question', 1, :embed_maxlen),
                  :'embed_model', :'embed_secret')::FLOAT[:embed_dim] AS qv
),
knn AS (
  SELECT c.src_table,
         c.name,
         c.description,
         c.axes,
         c.measures,
         c.covered,
         c.emb <=> (SELECT qv FROM q) AS distance,
         1 AS src_layer
    FROM search_wiki_entity_card c
   WHERE c.emb IS NOT NULL
   ORDER BY distance
   LIMIT :knn_limit
),
axis_words AS (
  SELECT list_filter(ts_lexize(:'stem_dict', :'action_axis'), x -> length(x) >= 3) AS stems
  WHERE :'action_axis' <> ''
),
struct_catalog AS (
  SELECT c.src_table, c.name, c.description, c.axes, c.measures, c.covered,
         c.emb <=> (SELECT qv FROM q) AS distance,
         2 AS src_layer
    FROM search_wiki_entity_card c
    JOIN search_tables t ON t.src_table = c.src_table
    LEFT JOIN search_entity_alias a ON a.src_table = c.src_table
   WHERE :'action_class' = 'object'
     AND c.src_table LIKE 'catalog_%'
     AND :'action_axis' <> ''
     AND list_has_any(
           (SELECT stems FROM axis_words),
           list_filter(ts_lexize(:'stem_dict',
                     concat_ws(' ', t.label, a.aliases, a.best_used_for)),
                     x -> length(x) >= 3))
),
struct_register AS (
  SELECT c.src_table, c.name, c.description, c.axes, c.measures, c.covered,
         c.emb <=> (SELECT qv FROM q) AS distance,
         2 AS src_layer
    FROM search_wiki_entity_card c
   WHERE c.src_table LIKE 'accumulationregister_%'
     AND :'action_axis' <> ''
     AND EXISTS (
           SELECT 1 FROM search_refcols r
            WHERE r.src_table = c.src_table
              AND list_has_any(
                    (SELECT stems FROM axis_words),
                    list_filter(ts_lexize(:'stem_dict',
                                concat_ws(' ', r.col, r.target_src)),
                                x -> length(x) >= 3))
     )
),
struct_move AS (
  SELECT c.src_table, c.name, c.description, c.axes, c.measures, c.covered,
         c.emb <=> (SELECT qv FROM q) AS distance,
         2 AS src_layer
    FROM search_wiki_entity_card c
    JOIN search_tables t ON t.src_table = c.src_table
    LEFT JOIN search_entity_alias a ON a.src_table = c.src_table
   WHERE :'action_class' = 'event'
     AND (c.src_table LIKE 'document_%'
          OR c.src_table LIKE 'accumulationregister_%')
     AND :'action_axis' <> ''
     AND list_has_any(
           (SELECT stems FROM axis_words),
           list_filter(ts_lexize(:'stem_dict',
                     concat_ws(' ', t.label, a.aliases, a.best_used_for)),
                     x -> length(x) >= 3))
),
struct_catalog_event AS (
  SELECT c.src_table, c.name, c.description, c.axes, c.measures, c.covered,
         c.emb <=> (SELECT qv FROM q) AS distance,
         2 AS src_layer
    FROM search_wiki_entity_card c
    JOIN search_tables t ON t.src_table = c.src_table
    LEFT JOIN search_entity_alias a ON a.src_table = c.src_table
   WHERE :'action_class' = 'event'
     AND :want_agg = 1
     AND c.src_table LIKE 'catalog_%'
     AND :'action_axis' <> ''
     AND list_has_any(
           (SELECT stems FROM axis_words),
           list_filter(ts_lexize(:'stem_dict',
                     concat_ws(' ', t.label, a.aliases, a.best_used_for)),
                     x -> length(x) >= 3))
),
pool AS (
  SELECT DISTINCT ON (src_table) src_table, name, description, axes, measures,
         covered, distance, src_layer
    FROM (
      SELECT * FROM knn
      UNION ALL SELECT * FROM struct_catalog
      UNION ALL SELECT * FROM struct_register
      UNION ALL SELECT * FROM struct_move
      UNION ALL SELECT * FROM struct_catalog_event
    ) u
   ORDER BY src_table, src_layer DESC, distance
),
meta AS (
  SELECT t.src_table, coalesce(t.parent, '') AS parent
    FROM search_tables t
   WHERE t.src_table IN (SELECT src_table FROM pool)
),
axis_ok AS (
  SELECT p.src_table
    FROM pool p
   WHERE :'action_axis' = ''
      -- [01.09 okna] class=none — вопрос без объектно/событийной семантики
      -- («записей в регистре X» — прямой выбор по имени): осевые фильтры не
      -- применимы, kNN-топ проходит как есть. Замер: «книгапродаж» давал
      -- ПУСТОЙ пул — kind уезжал в action_axis, стемов kind в refcols
      -- регистров нет, axis_ok выкашивал все kNN-карточки (29 вопросов
      -- «движений в регистре X» уходили в no_data при живых эталонах).
      -- Доки: Sql › Functions › Vector Functions › kNN.
      OR :'action_class' = 'none'
      OR p.src_layer = 2
      OR EXISTS (
           SELECT 1 FROM search_refcols r
            WHERE r.src_table = p.src_table
              AND list_has_any(
                    (SELECT stems FROM axis_words),
                    list_filter(ts_lexize(:'stem_dict',
                                concat_ws(' ', r.col, r.target_src)),
                                x -> length(x) >= 3))
         )
),
filtered AS (
  SELECT p.*
    FROM pool p
    JOIN meta m ON m.src_table = p.src_table
   WHERE p.src_table IN (SELECT src_table FROM axis_ok)
     AND NOT (:want_agg = 1 AND :'action_class' <> 'none' AND m.parent <> '')
     AND (
           :'action_class' NOT IN ('event', 'object')
        OR (:'action_class' = 'event'
            AND (p.src_table LIKE 'accumulationregister_%'
                 OR p.src_table LIKE 'document_%'
                 OR (:want_agg = 1 AND p.src_table LIKE 'catalog_%')))
        OR (:'action_class' = 'object'
            AND (p.src_table LIKE 'catalog_%'
                 OR p.src_table LIKE 'accumulationregister_%'))
         )
)
-- Колонки = wiki_hybrid_pool: src_table, name, description, axes, measures,
-- covered, distance, parent, platform_prefix. rk в SELECT ломал src_table→«1».
-- Доки: Sql › Functions › Vector Functions › knn; AI Functions › ai_embed.
SELECT f.src_table,
       f.name,
       substr(f.description, 1, 120) AS description_head,
       f.axes,
       f.measures,
       f.covered,
       round(f.distance::numeric, 4) AS distance,
       coalesce(m.parent, '') AS parent,
       split_part(f.src_table, '_', 1) AS platform_prefix
  FROM filtered f
  LEFT JOIN meta m ON m.src_table = f.src_table
 ORDER BY f.src_layer DESC, f.distance, f.src_table
 LIMIT :pick_limit;
