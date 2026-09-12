\set ON_ERROR_STOP on
-- Добор величин: сущность описана, поля — нет. Доки: struct_pack; vector <=>; LIMIT / OFFSET.
-- force=1 — песочница/перегенерация живых (P7 §5.5): NOT EXISTS не отсекает непустые aliases мер.
-- Паттерн иной, чем entity (два NOT EXISTS: «уже заполнено» + «пустой + свежий skip»),
-- но force-семантика та же: при :force=1 оба отсева выключены.
-- OFFSET CASE WHEN :force=1 THEN :skip_rows ELSE 0: курсор только при force
-- (пул=весь корпус); при force=0 пул сжимается сам — OFFSET сдвинул бы mark_skip.
WITH seed AS (
  SELECT f.src_table, t.emb FROM wiki_entity_facts f
  JOIN search_tables t ON t.src_table = f.src_table
  WHERE f.cls <> 'service'
    AND coalesce(f.measures,'') <> ''
    AND EXISTS (SELECT 1 FROM :alias_table a
                WHERE a.src_table = f.src_table AND coalesce(a.aliases,'') <> '')
    AND NOT EXISTS (SELECT 1 FROM :measure_table m
                    WHERE m.src_table = f.src_table
                      AND ( :force = 0 AND coalesce(m.aliases,'') <> '' ))
    AND NOT EXISTS (SELECT 1 FROM :measure_table m
                    WHERE m.src_table = f.src_table
                      AND ( :force = 0 AND coalesce(m.aliases,'') = ''
                        AND m.seen_at > now() - INTERVAL :retry_h HOUR ))
  ORDER BY f.src_table LIMIT 1)
SELECT to_json(list(struct_pack(entity := src_table, title := label,
                                quantities := coalesce(measures,''))))
FROM (SELECT f.*, t.emb <=> (SELECT emb FROM seed) AS d
        FROM wiki_entity_facts f
        JOIN search_tables t ON t.src_table = f.src_table
       WHERE f.cls <> 'service'
         AND coalesce(f.measures,'') <> ''
         AND EXISTS (SELECT 1 FROM :alias_table a
                     WHERE a.src_table = f.src_table AND coalesce(a.aliases,'') <> '')
         AND NOT EXISTS (SELECT 1 FROM :measure_table m
                         WHERE m.src_table = f.src_table
                           AND ( :force = 0 AND coalesce(m.aliases,'') <> '' ))
         AND NOT EXISTS (SELECT 1 FROM :measure_table m
                         WHERE m.src_table = f.src_table
                           AND ( :force = 0 AND coalesce(m.aliases,'') = ''
                             AND m.seen_at > now() - INTERVAL :retry_h HOUR ))
       ORDER BY d, f.src_table
       LIMIT :batch
       OFFSET CASE WHEN :force = 1 THEN :skip_rows ELSE 0 END);
