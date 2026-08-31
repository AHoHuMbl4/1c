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

-- 🔴 ПУБЛИКУЕТСЯ `MERGE`-ем, А НЕ ПЕРЕСОЗДАНИЕМ. Пересоздание обнуляло бы `emb` у ВСЕХ
-- 1 502 карточек каждый такт — это 45 с и деньги эмбеддера на пустом месте, при том что
-- меняются единицы. Приём тот же, что у корпуса (`corpus_merge.sql:100`): вектор
-- сбрасывается только там, где изменился сам текст карточки.
CREATE TABLE IF NOT EXISTS search_entity_card (
  src_table VARCHAR, label VARCHAR, parent VARCHAR, aliases VARCHAR,
  about VARCHAR, quantities VARCHAR, attrs VARCHAR, card VARCHAR, emb FLOAT[1024]);
-- Карточка могла быть собрана прежней сборкой, без имён реквизитов. Поле добавляется
-- отдельно: `CREATE TABLE IF NOT EXISTS` существующую таблицу не трогает. Для
-- инвертированного индекса это безопасно — «ADD COLUMN … index-neutral»
-- (доки SereneDB, «Schema changes on an indexed table»).
ALTER TABLE search_entity_card ADD COLUMN IF NOT EXISTS attrs VARCHAR;

CREATE OR REPLACE TABLE tmp_entity_card AS
WITH q AS (
  -- Какие величины у сущности вообще есть. Факт из данных, а не список в коде.
  SELECT src_table, string_agg(DISTINCT k, ', ' ORDER BY k) AS quantities
  FROM (SELECT src_table, unnest(map_keys(nums)) AS k
        FROM search_corpus WHERE nums IS NOT NULL) x
  GROUP BY src_table
), r AS (
  -- 🔴 ИМЕНА РЕКВИЗИТОВ — ЧЕТВЁРТОЕ ПОЛЕ КАРТОЧКИ (04.08). Спрашиваются у КАТАЛОГА
  -- ДВИЖКА, а не разбором текста строки: `duckdb_columns()` знает настоящие имена
  -- колонок витрины, и на любой базе и любом языке конфигурации они свои. Ни списка
  -- слов, ни шаблона имени здесь нет — п. 9 и девиз «спроси того, кто знает».
  --
  -- Зачем. `[замер 04.08]` вопрос «Кто нам поставляет товар?» не доносила ни одна
  -- поверхность: у справочника партнёров в синонимах слова «поставщик» нет, а по смыслу
  -- он на 338-м месте — верх занят служебными «Использовать Соглашения СПоставщиками».
  -- При этом признак «Поставщик» у него ЕСТЬ и стоит отдельным реквизитом: сущность
  -- знает о себе то, чего не знает ни её название, ни описание от агента.
  --
  -- 🔴 Ограничение по текущей базе обязательно: `duckdb_columns()` отдаёт колонки ВСЕХ
  -- присоединённых баз (ловушка 25 `techContext`), а одноимённых таблиц в них
  -- `[замер 04.08]` **91**. Без этого условия в карточку попали бы реквизиты чужой базы.
  SELECT t.src_table,
         string_agg(DISTINCT c.column_name, ', ' ORDER BY c.column_name) AS attrs
  FROM search_tables t
  JOIN duckdb_columns() c ON c.table_name = t.src_table
                         AND c.database_name = current_database()
  GROUP BY t.src_table
)
SELECT t.src_table,
       t.label,
       coalesce(t.parent, '')                       AS parent,
       coalesce(a.aliases, '')                      AS aliases,
       coalesce(a.best_used_for, '')                AS about,
       coalesce(q.quantities, '')                   AS quantities,
       coalesce(r.attrs, '')                        AS attrs,
       -- Текст под вектор: ТОЛЬКО стабильная часть (label | aliases | about).
       -- `quantities` — агрегат по корпусу: набор ключей nums растёт с данными каждый
       -- такт → прежний card с quantities сбрасывал emb у «неизменившихся» сущностей.
       -- `attrs` — каталог колонок; тоже вне вектора (лексический индекс). Обоснование
       -- то же, что у attrs 04.08: смысл карточки — имя и описание, не инвентарь полей.
       concat_ws(' | ', t.label, coalesce(a.aliases, ''),
                 coalesce(a.best_used_for, '')) AS card,
       NULL::FLOAT[1024]                            AS emb
FROM search_tables t
LEFT JOIN search_entity_alias a ON a.src_table = t.src_table
LEFT JOIN q                     ON q.src_table = t.src_table
LEFT JOIN r                     ON r.src_table = t.src_table
WHERE NOT EXISTS (
  SELECT 1 FROM search_entity_class e
  WHERE e.src_table = t.src_table AND e.cls = 'service'
);

-- Карта переноса при смене формы card (старый card = stable | quantities → новый stable).
-- Без неё однократная смена формы обнулила бы emb у всех. Доки: MERGE INTO;
-- sql/statements/update#update-from-other-table.
CREATE OR REPLACE TABLE tmp_entity_card_emb_xfer AS
SELECT s.src_table, t.emb
FROM tmp_entity_card s
JOIN search_entity_card t ON t.src_table = s.src_table
WHERE t.emb IS NOT NULL
  AND t.card IS DISTINCT FROM s.card
  AND (
    t.card = concat_ws(' | ', s.card, coalesce(t.quantities, ''))
    OR t.card = concat_ws(' | ', s.card, coalesce(s.quantities, ''))
    OR s.card = concat_ws(' | ', t.label, coalesce(t.aliases, ''), coalesce(t.about, ''))
  );

-- Изменившимся карточкам вектор сбрасывается, неизменившиеся его сохраняют.
-- Форма-only (в карте xfer) emb не трогает — перенос ниже.
-- 🔴 СБРОС — ОТДЕЛЬНЫМ UPDATE ДО MERGE: `CASE` над FLOAT[1024] движок не вычисляет
-- («Unimplemented type for case expression: FLOAT[1024]» — okna 16.08).
UPDATE search_entity_card AS t SET emb = NULL
FROM tmp_entity_card AS s
WHERE t.src_table = s.src_table AND t.card IS DISTINCT FROM s.card
  AND NOT EXISTS (
    SELECT 1 FROM tmp_entity_card_emb_xfer x WHERE x.src_table = t.src_table
  );

MERGE INTO search_entity_card AS t
USING tmp_entity_card AS s
ON t.src_table = s.src_table
WHEN MATCHED AND (t.card IS DISTINCT FROM s.card
               OR t.attrs IS DISTINCT FROM s.attrs
               OR t.quantities IS DISTINCT FROM s.quantities
               OR t.label IS DISTINCT FROM s.label
               OR t.parent IS DISTINCT FROM s.parent
               OR t.aliases IS DISTINCT FROM s.aliases
               OR t.about IS DISTINCT FROM s.about) THEN
     UPDATE SET label = s.label, parent = s.parent, aliases = s.aliases,
                about = s.about, quantities = s.quantities, attrs = s.attrs,
                card = s.card
WHEN NOT MATCHED THEN
     INSERT (src_table, label, parent, aliases, about, quantities, attrs, card, emb)
     VALUES (s.src_table, s.label, s.parent, s.aliases, s.about, s.quantities,
             s.attrs, s.card, NULL);

-- Перенос emb при смене формы card (≤1000; таблица ~1.5k — один пакет обычно).
CREATE OR REPLACE TABLE tmp_entity_card_emb_xfer_n AS
SELECT row_number() OVER (ORDER BY src_table) AS n, *
FROM tmp_entity_card_emb_xfer;

SELECT 'UPDATE search_entity_card SET emb = x.emb FROM tmp_entity_card_emb_xfer_n x '
       || 'WHERE search_entity_card.src_table = x.src_table '
       || 'AND search_entity_card.emb IS NULL AND x.n >= ' || (b * 1000)
       || ' AND x.n < ' || ((b + 1) * 1000) || ';'
FROM (SELECT i AS b FROM range(0, (SELECT ceil(count(*) / 1000.0)::BIGINT
                                   FROM tmp_entity_card_emb_xfer_n)) t(i)) z
\gexec

-- Сущность исчезла из витрины — её карточка не должна оставаться в отборе кандидатов.
DELETE FROM search_entity_card
WHERE src_table NOT IN (SELECT src_table FROM tmp_entity_card);

DROP TABLE IF EXISTS tmp_entity_card;
DROP TABLE IF EXISTS tmp_entity_card_emb_xfer;
DROP TABLE IF EXISTS tmp_entity_card_emb_xfer_n;

-- Индекс по карточке. Словарь — общий `search_dict` (`stemming = false`), тот же, что у
-- корпуса и алиасов: словарь со стеммингом отклонён и по п. 9, и замером (см. шапку).
-- `src_table` без словаря (keyword) — фильтр уровня индекса, как в `search_idx`.
--
-- 🔴 ПЕРЕСОЗДАЁТСЯ, А НЕ ДОПОЛНЯЕТСЯ. Добавить поле в существующий инвертированный
-- индекс движок не даёт: «To pick up … rebuild it with DROP INDEX followed by CREATE
-- INDEX» (доки SereneDB, «Maintenance & Introspection»). Здесь это дёшево — таблица
-- 1 502 строки, `[замер 04.08]` пересоздание 0,1 с, — и делается в такте, между
-- запросами сервиса: пока индекса нет, поверхность карточки честно отдаёт пусто
-- (`card_hits` ловит `RuntimeError`), а не роняет ответ.
DROP INDEX IF EXISTS entity_card_idx;
CREATE INDEX IF NOT EXISTS entity_card_idx ON search_entity_card
  USING inverted(label search_dict, aliases search_dict, about search_dict,
                 quantities search_dict, attrs search_dict, src_table)
  INCLUDE (src_table, label, parent);
-- Записи становятся видимы индексу только после публикации; фоновая — раз в секунду,
-- явная — здесь, чтобы следующий же вопрос искал по свежей карточке
-- (доки SereneDB, «Visibility and the refresh model»).
VACUUM (REFRESH_TABLE) search_entity_card;

GRANT SELECT ON search_entity_card TO serene_ro;
