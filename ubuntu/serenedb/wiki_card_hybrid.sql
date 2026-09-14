\set ON_ERROR_STOP on
-- Б3: гибридный пул — kNN top-N ∪ структурные носители оси, затем сужение.
-- Доки: Vector Search › k-nearest-neighbor (kNN); ai_embed — Sql › Functions › AI Functions.
-- Параметры: question, question_raw, embed_model, embed_secret, embed_dim,
--   embed_maxlen, knn_limit, action_class, action_axis, want_agg, stem_dict,
--   pick_limit.

WITH q AS (
  SELECT ai_embed(substr(:'question', 1, :embed_maxlen),
                  :'embed_model', :'embed_secret')::FLOAT[:embed_dim] AS qv
),
-- [01.09, ночь] ДВЕ ФОРМЫ — ОДИН ПУЛ. :question = поисковая форма разбора
-- (без периода/чисел; гасит утягивание kNN к карточкам периода), но на
-- склеенных именах регистров модель сворачивает вопрос в голый токен
-- («Сколько записей в «книгапродаж»?» → search_form «книгапродаж»), и kNN по
-- нему промахивается: замер L8, пул = года/праздники/нумераторы, верная
-- карточка accumulationregister_книгапродаж потеряна (регрессия 17→10 match
-- против L7). По сырому вопросу та же карточка — №2 (d=0.415): слова
-- «сколько записей в» — контекст, который помогает вектору. Поэтому обе
-- формы — входы пула (объединение, не замена); когда формы равны, ветвь
-- пуста (embed не зовётся: q2 без строк).
q2 AS (
  SELECT ai_embed(substr(:'question_raw', 1, :embed_maxlen),
                  :'embed_model', :'embed_secret')::FLOAT[:embed_dim] AS qv
   WHERE :'question_raw' <> :'question'
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
knn_raw AS (
  SELECT c.src_table,
         c.name,
         c.description,
         c.axes,
         c.measures,
         c.covered,
         c.emb <=> (SELECT qv FROM q2) AS distance,
         1 AS src_layer
    FROM search_wiki_entity_card c
   WHERE c.emb IS NOT NULL
     AND :'question_raw' <> :'question'
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
-- [01.09 «один судья»] СЛОВАРЬ СИНОНИМОВ — ВХОД ПУЛА, А НЕ СУДЬЯ ПОСЛЕ.
-- Раньше его лидер жил в отдельном вето (z20 _alias_verdict) и переигрывал
-- уже верифицированный выбор; на склеенных именах («книгапродаж») словарь
-- слеп и подставлял чужой топ по общим словам («строки 5-С») — верный ответ
-- превращался в уточнение (замер L6: 55 из 67 — отказы при живых эталонах).
-- Теперь словарь даёт КАНДИДАТОВ: топ-K по bm25 входит в пул наравне с kNN,
-- а судьёй остаётся одна паспортная верификация каскада. Источник — те же
-- данные (search_entity_alias), на любой базе; скорер и разделитель равных —
-- штатные предписания движка.
-- Доки: Sql › Indexes › Inverted › Ranking › Tie-breaking;
--       Sql › Functions › Search › Relevance Scoring › Scorer Functions.
struct_alias AS (
  SELECT c.src_table, c.name, c.description, c.axes, c.measures, c.covered,
         c.emb <=> (SELECT qv FROM q) AS distance,
         2 AS src_layer
    FROM (SELECT src_table
            FROM alias_idx
           WHERE aliases @@ :'question'
              OR (:'question_raw' <> :'question'
                  AND aliases @@ :'question_raw')
           ORDER BY bm25(alias_idx.tableoid) DESC, src_table
           LIMIT :alias_top) a
    JOIN search_wiki_entity_card c ON c.src_table = a.src_table
),
-- [01.09 «один судья»] СПРОШЕННАЯ ВЕЛИЧИНА — вход пула: сущности-носители меры
-- из вопроса (search_measure_alias, по стемам — те же данные, что выбор
-- величины). «Остатки по складу» находит не «места хранения» (у них нет
-- меры), а носителей меры — паспортная верификация решает дальше. На базе,
-- где такой меры нет вообще, слагаемое пусто и вопрос честно уходит в
-- no_data по итогам верификации (п. 13: данных по величине нет).
-- Доки: Sql › Functions › List Functions › list_has_any.
struct_measure AS (
  SELECT c.src_table, c.name, c.description, c.axes, c.measures, c.covered,
         c.emb <=> (SELECT qv FROM q) AS distance,
         2 AS src_layer
    FROM (SELECT src_table FROM search_measure_alias
           WHERE :'measure' <> ''
             AND list_has_any(
                   list_filter(ts_lexize(:'stem_dict', :'measure'),
                               x -> length(x) >= 3),
                   list_filter(ts_lexize(:'stem_dict',
                               concat_ws(' ', measure, aliases)),
                               x -> length(x) >= 3))
           GROUP BY src_table) m
    JOIN search_wiki_entity_card c ON c.src_table = m.src_table
),
-- [01.09, ночь] ВОПРОС НАЗЫВАЕТ СУЩНОСТЬ — её карточка гарантированно в пуле.
-- Стемы слов сырого вопроса против стемов слов системного имени и label
-- (те же данные базы, тот же ts_lexize-приём, что у struct_* выше). Закрывает
-- два измеренных промаха остальных входов: kNN по вопросу со склеенным именем
-- тонет в соседях по общим словам («движений в регистре книгапродаж» тянул
-- «движения денежных средств», верный регистр не входил в топ-8 — замер
-- L9-пробы), а словарь bm25 на склеенных именах слеп. Слагаемое только
-- ДОБАВЛЯЕТ кандидатов — судья по-прежнему одна паспортная верификация.
-- Доки: Sql › Functions › Search › Full-Text Search Functions › ts_lexize;
--       Sql › Functions › List Functions › list_has_any.
struct_named AS (
  SELECT c.src_table, c.name, c.description, c.axes, c.measures, c.covered,
         c.emb <=> (SELECT qv FROM q) AS distance,
         2 AS src_layer
    FROM search_wiki_entity_card c
    JOIN search_tables t ON t.src_table = c.src_table
   WHERE list_has_any(
           list_filter(ts_lexize(:'stem_dict', :'question_raw'),
                       x -> length(x) >= 4),
           list_filter(ts_lexize(:'stem_dict',
                     concat_ws(' ', replace(t.src_table, '_', ' '),
                               coalesce(t.label, ''))),
                       x -> length(x) >= 4))
),
pool AS (
  SELECT DISTINCT ON (src_table) src_table, name, description, axes, measures,
         covered, distance, src_layer
    FROM (
      SELECT * FROM knn
      UNION ALL SELECT * FROM knn_raw
      UNION ALL SELECT * FROM struct_named
      UNION ALL SELECT * FROM struct_catalog
      UNION ALL SELECT * FROM struct_register
      UNION ALL SELECT * FROM struct_move
      UNION ALL SELECT * FROM struct_catalog_event
      UNION ALL SELECT * FROM struct_alias
      UNION ALL SELECT * FROM struct_measure
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
