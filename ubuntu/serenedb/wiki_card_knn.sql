\set ON_ERROR_STOP on
-- Б2: kNN по паспорт-карточкам. Доки: Vector Search › k-nearest-neighbor (kNN).
-- Параметры psql: question, embed_model, embed_secret, embed_dim, embed_maxlen.
-- Пример: psql … -v question='…' -v embed_model=… -v embed_secret=… \
--         -v embed_dim=1024 -v embed_maxlen=20000 -f wiki_card_knn.sql

SELECT c.src_table,
       c.name,
       substr(c.description, 1, 120) AS description_head,
       c.axes,
       c.measures,
       c.covered,
       c.emb <=> ai_embed(substr(:'question', 1, :embed_maxlen),
                          :'embed_model', :'embed_secret')::FLOAT[:embed_dim] AS distance
  FROM search_wiki_entity_card c
 WHERE c.emb IS NOT NULL
 ORDER BY distance
 LIMIT 5;
