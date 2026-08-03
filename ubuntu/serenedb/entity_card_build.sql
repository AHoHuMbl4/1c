-- Карточка сущности: ОДНА строка на сущность — поверхность для отбора кандидатов.
--
-- Зачем. Сегодня кандидаты собираются из корпуса ЗАПИСЕЙ (623 565 строк) через
-- `GROUP BY src_table`. На такой поверхности признак «сколько совпадений» пропорционален
-- РАЗМЕРУ сущности, а не относимости: [замер 03.08] 7 307 совпадений у себестоимости
-- против 272 у верного документа реализации. Здесь размер исчезает по построению.
-- Замысел и порядок проверки — `work/entity-choice/PLAN_ENTITY_SURFACE.md`.
--
-- Всё считается ВНУТРИ движка одним запросом: наружу не уходит ни строки (п. 20).
--
-- 🔴 ЧЕГО ЗДЕСЬ НЕТ И ПОЧЕМУ:
--
-- * `sig_terms` (отличительные термы). Их предлагали все внешние мнения, но собрать их
--   на все сущности одним запросом движок НЕ ДАЁТ: [замер 03.08]
--   «ts_dict_* aggregates cannot be combined with GROUP BY», подсказка — считать
--   отдельным подзапросом. Отдельным подзапросом НА СУЩНОСТЬ — это 1 502 запроса за
--   сборку, то есть ровно «один запрос на таблицу», запрещённый п. 20. Поэтому в v1 их
--   нет. Для подсказки МОДЕЛИ они по-прежнему считаются на лету, по одному вопросу
--   (`serene_ask.signal_terms`) — там это один запрос, а не полторы тысячи.
--
-- * `not_enough_for` — вторая половина описания от установочного агента. В карточку не
--   берётся намеренно: она называет ЧУЖИЕ сущности («приобретение у поставщика —
--   Приобретение Товаров Услуг»), и как поисковая поверхность давала бы переток —
--   вопрос про приобретение находил бы реализацию. Ровно та ошибка, от которой карточка
--   и должна избавить.
--
-- * Стемминга нет. Индекс поверх этой таблицы строится на общем `search_dict`
--   (`stemming = false`): словарь со стеммингом отклонён и по п. 9
--   (`CHECKLIST_SEARCH_FIX §5-бис` — стеммер углубляет допущение о языке), и замером
--   («индекс алиасов на словаре со стеммингом — ранжирование вырождается в нули»).
--   Мост через словоформы дают `ts_ngram` и вектор карточки.
--
-- 🔴 Порядок в `string_agg` задан ЯВНО. Без `ORDER BY` склейка при равных даёт разный
-- текст от сборки к сборке, а значит другой вектор и лишний пересчёт за деньги — это
-- ловушка 30 `techContext`, уже кусавшая сборку корпуса и (03.08, `F243`) выбор сущности.

CREATE OR REPLACE TABLE search_entity_card AS
WITH q AS (
  -- Какие величины у сущности вообще есть. Факт из данных, а не список в коде.
  SELECT src_table, string_agg(DISTINCT k, ', ' ORDER BY k) AS quantities
  FROM (SELECT src_table, unnest(map_keys(nums)) AS k
        FROM search_corpus WHERE nums IS NOT NULL) x
  GROUP BY src_table
)
SELECT t.src_table,
       t.label,
       coalesce(t.parent, '')                       AS parent,
       coalesce(a.aliases, '')                      AS aliases,
       coalesce(a.best_used_for, '')                AS about,
       coalesce(q.quantities, '')                   AS quantities,
       -- Текст под вектор: то же, что индексируется, одной строкой.
       concat_ws(' | ', t.label, coalesce(a.aliases, ''),
                 coalesce(a.best_used_for, ''), coalesce(q.quantities, '')) AS card,
       NULL::FLOAT[1024]                            AS emb
FROM search_tables t
LEFT JOIN search_entity_alias a ON a.src_table = t.src_table
LEFT JOIN q                     ON q.src_table = t.src_table;

-- Индекс по карточке. Словарь — общий `search_dict` (`stemming = false`), тот же, что у
-- корпуса и алиасов: словарь со стеммингом отклонён и по п. 9, и замером (см. шапку).
-- `src_table` без словаря (keyword) — фильтр уровня индекса, как в `search_idx`.
CREATE INDEX IF NOT EXISTS entity_card_idx ON search_entity_card
  USING inverted(label search_dict, aliases search_dict, about search_dict,
                 quantities search_dict, src_table)
  INCLUDE (src_table, label, parent);

GRANT SELECT ON search_entity_card TO serene_ro;
