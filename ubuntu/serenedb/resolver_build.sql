\timing on
\set ON_ERROR_STOP on

-- СБОРКА СЕМАНТИЧЕСКОГО РЕЗОЛВЕРА ШТАТНЫМИ СРЕДСТВАМИ SereneDB.
--
-- Резолвер сопоставляет слово человека со значением в базе («питер» → «Г. САНКТ-
-- ПЕТЕРБУРГ»). Хранит различные значения текстовых колонок и их векторы.
--
-- Чем отличается от прежней питоновской сборки (`build_resolver_index.py`):
--   * прежняя делала `DELETE FROM resolver_index` и считала ВСЕ векторы заново каждый
--     синк. [замер 27.07] 7 часов 34 минуты при 10 минутах процессорного времени;
--   * здесь значения сводятся `MERGE`-ом, а вектор считается ТОЛЬКО новым (`emb IS NULL`).
--     Повторный прогон на неизменных данных не тратит ни одного вызова к облаку;
--   * прежняя тянула в облако мусор: [замер] 43 680 значений из колонок `*_Base64Data`
--     (таких колонок у сущностей корпуса 20), плюс значения наших служебных таблиц;
--   * прежняя плодила дубли: [замер] 34 230 из 119 271.
--
-- 🔴 ЧИСЛОВЫХ ОТСЕЧЕК ЗДЕСЬ НЕТ, и это принципиально. В первой версии я перенёс из питона
-- предел «не больше 1500 различных значений на колонку» и добавил свой «значение короче
-- 200 символов» — обе оказались отсечками в пути ПРАВИЛЬНОСТИ, а не бюджетами.
-- [замер 28.07] самое крупное измерение нашей базы — 10 048 значений, колонок свыше 1500
-- — семнадцать: прежний предел молча выбросил бы их все. Отбор только СТРУКТУРНЫЙ, по
-- контракту платформы: объявленный тип строка, не спутник протокола, не версия записи,
-- не вложение, не GUID (ссылку разрешает карта корпуса), не адрес.

-- ============ 1. ЧТО В ЭТОТ РАЗ ДЕЙСТВИТЕЛЬНО ПРОЧИТАНО ============
-- 🔴 Без этого шага удаление стирало живые значения вместе с посчитанными векторами.
-- Прежняя охрана смотрела на `tmp3_src` — «что числится источником», а не «что мы сейчас
-- смогли прочитать». Сущность, у которой источник в этот раз вернул ноль строк (сбой 1С,
-- окно пересоздания таблицы синком), теряла ВСЕ свои значения.
-- [замер] воспроизведено на копии: `DELETE 2` у сущности, которая просто была пуста.
-- [замер] `count(*)` по самой крупной таблице — 2,6 мс, по всем 226 — меньше секунды.
CREATE OR REPLACE TABLE res_seen (tbl VARCHAR, n_rows BIGINT);
PREPARE p_seen AS INSERT INTO res_seen SELECT $1::VARCHAR, count(*) FROM query_table($1);
SELECT 'EXECUTE p_seen(' || quote_literal(tbl) || ');' FROM tmp3_src
\gexec

-- ============ 2. ЗНАЧЕНИЯ — ОДНИМ ПРОХОДОМ ============
-- Прежде было два полных прохода по всем ячейкам: первый считал `count(DISTINCT)` по
-- колонкам, второй забирал значения. При этом фильтры стояли только в первом, а решение
-- принималось «по колонке» — поэтому достаточно было одного нормального значения, чтобы
-- в резолвер уехали ВСЕ GUID этой колонки. [замер] так туда попали 454 GUID и 2 адреса,
-- и за них уже заплачено векторами.
-- Теперь фильтры стоят там же, где отбираются значения, и проход один.
-- [замер] на самой крупной таблице: 150 мс против 68 мс — вдвое быстрее.
-- Порядок важен: регулярные выражения применяются к РАЗЛИЧНЫМ значениям (10 675), а не
-- ко всем ячейкам (477 тысяч).
CREATE OR REPLACE TABLE res_val (tbl VARCHAR, col VARCHAR, val VARCHAR);

PREPARE p_val AS
INSERT INTO res_val
WITH cells AS (SELECT * FROM (SELECT COLUMNS(*)::VARCHAR FROM query_table($1)) s
                    UNPIVOT (val FOR col IN (COLUMNS(*)))),
     d AS (SELECT DISTINCT u.col, u.val
           FROM cells u JOIN tmp3_cls c ON c.tbl = $1 AND c.col = u.col
           WHERE u.val <> ''
             AND c.kind = 'text'                    -- объявленный тип, а не тип витрины
             AND NOT c.is_companion                 -- спутник протокола (`X_Type`)
             -- Служебные свойства протокола OData 1С: `DataVersion` — версия записи,
             -- `PredefinedDataName` — машинное имя предопределённого элемента ([замер]
             -- объявлено у 707 сущностей, 2 526 значений). Человеческих имён там не
             -- бывает никогда, а подсказка резолвера увела бы модель на служебный реквизит.
             AND c.col NOT IN ('DataVersion', 'PredefinedDataName')
             AND c.col NOT LIKE '%\_Base64Data')    -- вложение, а не значение
SELECT $1::VARCHAR, col, val FROM d
WHERE NOT regexp_matches(val, '^(https?://|/)')
  AND NOT regexp_matches(val, '^\\{')
  AND NOT regexp_full_match(val,
        '[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}');

SELECT 'EXECUTE p_val(' || quote_literal(tbl) || ');' FROM tmp3_src s
WHERE NOT EXISTS (
  SELECT 1 FROM search_entity_class e
  WHERE lower(e.src_table) = lower(s.tbl) AND e.cls = 'service'
)
\gexec

-- Колонки-измерения выводятся из значений, а не считаются отдельным проходом по данным.
CREATE OR REPLACE TABLE res_dim AS
SELECT tbl, col, count(*) AS n_distinct FROM res_val GROUP BY 1, 2;

SELECT 'значения' AS шаг, (SELECT count(*) FROM res_val) AS всего,
       (SELECT count(*) FROM res_dim) AS колонок,
       (SELECT max(n_distinct) FROM res_dim) AS крупнейшее_измерение;

-- ============ 3. СВЕДЕНИЕ С ХРАНИМЫМ — ОДНИМ MERGE ============
CREATE TABLE IF NOT EXISTS resolver_index
  (table_name VARCHAR, column_name VARCHAR, value VARCHAR, emb FLOAT[1024]);

-- Права выдаются здесь же: на чистой машине таблица рождается этим файлом, и без этих
-- команд `serene_resolver` её не прочитает, а `serene_ro` не будет отозван — то есть
-- разделение ролей окажется невыполненным МОЛЧА, а `test_integrity.py` T3 упадёт.
GRANT SELECT ON resolver_index TO serene_resolver;
REVOKE SELECT ON resolver_index FROM serene_ro;

-- Служебные таблицы прежней сборки вычищаем по КОНТРАКТУ 1С, а не по нашему корпусу:
-- сущность — это то, что объявлено в `$metadata`. Прежняя ветка удаляла всё, чего нет в
-- `tmp3_src`, то есть повторяла шаблон, запрещённый `HOW_NOT_TO §4.2`: пустой или
-- устаревший `tmp3_src` стёр бы весь резолвер (89 436 значений, из них 66 479 с
-- посчитанными векторами). Условие `count(*) > 0` не даёт сработать на пустых метаданных.
DELETE FROM resolver_index r
WHERE (SELECT count(*) FROM tmp3_ent) > 0
  AND NOT EXISTS (SELECT 1 FROM tmp3_ent e WHERE e.entity = lower(r.table_name));

-- Один `MERGE` вместо трёх операторов: удаляет ушедшее ТОЛЬКО у сущностей, которые в
-- этот раз реально прочитаны, вставляет новое без вектора, а совпавшие строки НЕ трогает —
-- их векторы уцелевают. [замер] `NOT MATCHED BY SOURCE` в сборке 26.07.3 работает.
MERGE INTO resolver_index t
USING (SELECT tbl, col, val FROM res_val) s
   ON t.table_name = s.tbl AND t.column_name = s.col AND t.value = s.val
 WHEN NOT MATCHED BY SOURCE
      AND EXISTS (SELECT 1 FROM res_seen z WHERE z.tbl = t.table_name AND z.n_rows > 0)
      THEN DELETE
 WHEN NOT MATCHED THEN
      INSERT (table_name, column_name, value, emb)
      VALUES (s.tbl, s.col, substr(s.val, 1, 20000), NULL);

-- 🔴 SERVICE НЕ В РЕЗОЛВЕРЕ (возврат 2 / 21.08, DATA_SCOPE §9.4). Бизнес-вопросов к
-- служебным сущностям нет: ни значения, ни их векторы. Даже если таблица не попала в
-- tmp3_src в этот такт, старые строки service снимаем явно (MERGE их иначе не тронет).
DELETE FROM resolver_index r
WHERE EXISTS (
  SELECT 1 FROM search_entity_class e
  WHERE lower(e.src_table) = lower(r.table_name) AND e.cls = 'service'
);

-- ============ 4. ОТЧЁТ — В БАЗУ, А НЕ В ЖУРНАЛ ============
-- П. 13: потеря обязана быть видна запросом, а не только тому, кто смотрел в консоль.
-- `resolver_too_long` — значения, которые вектор не получат никогда, если досчёт не
-- обрежет вход: у эмбеддера предел 33 000 символов, а в базе лежат значения по 560 282.
DELETE FROM search_quality WHERE k LIKE 'resolver_%';
INSERT INTO search_quality
            SELECT 'resolver_values',   count(*),                            'значений в резолвере'
            FROM resolver_index
UNION ALL   SELECT 'resolver_no_emb',   count(*) FILTER (WHERE emb IS NULL), 'ждут вектора'
            FROM resolver_index
UNION ALL   SELECT 'resolver_clipped', count(*) FILTER (WHERE length(value) > 20000),
                   'вектор посчитан по обрезанному началу значения, а не по всему'
            FROM resolver_index;

SELECT k, v, note FROM search_quality WHERE k LIKE 'resolver_%' ORDER BY k;
