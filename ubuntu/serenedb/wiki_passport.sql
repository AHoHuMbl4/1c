\set ON_ERROR_STOP on
-- Б3-у: расширенный паспорт кандидата для контекстной верификации (PLAN_WIKI_CHOICE).
-- Доки: wiki_pages VIEW — wiki_build.sql; оси search_refcols; меры search_measure_alias.
-- Параметры: src_list (IN-список литералов), body_max (лимит wiki body).
-- Вызывается из ask/z21_wiki_choice.py после гибрид-пула; ≤5 src_table за вызов.

SELECT c.src_table,
       c.name,
       substr(coalesce(nullif(w.body, ''), c.description, ''), 1, :body_max) AS wiki_body,
       c.axes,
       c.measures,
       coalesce(t.parent, '') AS parent,
       split_part(c.src_table, '_', 1) AS platform_prefix
  FROM search_wiki_entity_card c
  LEFT JOIN wiki_pages w ON w.page_id = c.src_table
  LEFT JOIN search_tables t ON t.src_table = c.src_table
 WHERE c.src_table IN (:src_list);
