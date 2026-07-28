\timing on
\set ON_ERROR_STOP on

-- СБОРКА СЕМАНТИЧЕСКОГО РЕЗОЛВЕРА ШТАТНЫМИ СРЕДСТВАМИ SereneDB.
--
-- Резолвер сопоставляет слово человека со значением в базе («питер» → «Г. САНКТ-
-- ПЕТЕРБУРГ»). Хранит различные значения колонок-измерений и их векторы.
--
-- Чем отличается от прежней питоновской сборки (`build_resolver_index.py`), и почему
-- это и есть работа по п. 17 (свежесть):
--   * прежняя делала `DELETE FROM resolver_index` и считала ВСЕ векторы заново каждый
--     синк. [замер 27.07] это 7 часов 34 минуты при 10 минутах процессорного времени —
--     всё остальное ожидание облачного эмбеддера;
--   * здесь значения добавляются `MERGE`-ом, а вектор считается ТОЛЬКО у новых
--     (`emb IS NULL`). Повторный запуск на неизменных данных не тратит ни одного вызова;
--   * прежняя тянула в облако мусор: [замер] 43 680 значений из 12 колонок
--     `*_Base64Data` — двоичные вложения, закодированные текстом. Здесь отбор идёт по
--     тем же правилам, что у корпуса: объявленный тип `Edm.String`, без служебных
--     свойств протокола, без машинных значений, без вложений;
--   * прежняя плодила дубли: [замер] 34 230 из 119 271. Ключ `(таблица, колонка,
--     значение)` здесь соблюдается `MERGE`-ом.
--
-- Требует таблиц классификации из `corpus_build.sql` (`tmp3_cls`, `tmp3_src`) — они
-- строятся из `$metadata` самой базы, а не из кода.

-- ============ 1. КОЛОНКИ СО ЗНАЧЕНИЯМИ ============
-- 🔴 ЗДЕСЬ НЕТ ЧИСЛОВЫХ ОТСЕЧЕК, и это принципиально. В первой версии я перенёс из
-- питона предел «не больше 1500 различных значений» и добавил свой «значение короче
-- 200 символов». Обе — отсечки в пути ПРАВИЛЬНОСТИ: колонка с 1501 значением молча
-- становится неразрешимой, а одно длинное значение выбрасывает из резолвера все
-- остальные значения своей колонки. [замер 28.07] на нашей базе самое крупное
-- измерение — 1 470 значений, то есть предел не резал ничего СЕГОДНЯ и сработал бы
-- молча на базе побольше. Это ловушка, а не бюджет.
-- Отбор идёт только СТРУКТУРНЫЙ, по контракту платформы:
--   * объявленный тип — строка (`Edm.String`), а не число и не дата;
--   * не спутник протокола и не версия записи;
--   * не вложение (`*_Base64Data`) — это двоичные данные, а не значение;
--   * не GUID — ссылку разрешает карта корпуса, а не резолвер;
--   * не машинный токен (адрес).
-- Цена честного набора платится ОДИН раз: вектор считается только новым значениям.
CREATE OR REPLACE TABLE res_dim (tbl VARCHAR, col VARCHAR, n_distinct BIGINT);

PREPARE p_dim AS
INSERT INTO res_dim
WITH cells AS (SELECT * FROM (SELECT COLUMNS(*)::VARCHAR FROM query_table($1)) s
                    UNPIVOT (val FOR col IN (COLUMNS(*))))
SELECT $1::VARCHAR, u.col, count(DISTINCT u.val)
FROM cells u
JOIN tmp3_cls c ON c.tbl = $1 AND c.col = u.col
WHERE u.val <> ''
  AND c.kind = 'text'                      -- объявленный тип, а не тип витрины
  AND NOT c.is_companion                   -- спутники протокола (`X_Type`) не данные
  AND c.col <> 'DataVersion'               -- версия записи объявлена платформой
  AND c.col NOT LIKE '%\_Base64Data'       -- вложение, а не значение измерения
  AND NOT regexp_matches(u.val, '^(https?://|/)')
  -- GUID измерением не бывает: он и есть ссылка, её разрешает карта корпуса
  AND NOT regexp_full_match(u.val,
        '[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}')
GROUP BY u.col
HAVING count(DISTINCT u.val) > 0;

SELECT 'EXECUTE p_dim(' || quote_literal(tbl) || ');' FROM tmp3_src
\gexec

SELECT 'колонок-измерений' AS шаг, count(*) AS колонок, sum(n_distinct) AS значений FROM res_dim;

-- ============ 2. ЗНАЧЕНИЯ ============
CREATE OR REPLACE TABLE res_val (tbl VARCHAR, col VARCHAR, val VARCHAR);

PREPARE p_val AS
INSERT INTO res_val
WITH cells AS (SELECT * FROM (SELECT COLUMNS(*)::VARCHAR FROM query_table($1)) s
                    UNPIVOT (val FOR col IN (COLUMNS(*))))
SELECT DISTINCT $1::VARCHAR, u.col, u.val
FROM cells u JOIN res_dim d ON d.tbl = $1 AND d.col = u.col
WHERE u.val <> '';

SELECT 'EXECUTE p_val(' || quote_literal(tbl) || ');' FROM (SELECT DISTINCT tbl FROM res_dim)
\gexec

SELECT 'значений к разрешению' AS шаг, count(*) AS всего,
       count(DISTINCT (tbl, col, val)) AS уникальных FROM res_val;

-- ============ 3. ИНКРЕМЕНТ: значения обновляются, векторы считаются только новым ============
-- Размерность задаёт модель (`ai_embed` отдаёт 1024) — колонка объявляется под неё.
-- Смена размерности делается один раз: `ALTER COLUMN TYPE` движок не даёт,
-- `DROP COLUMN` + `ADD COLUMN` работает и индексы таблицы переживает.
CREATE TABLE IF NOT EXISTS resolver_index
  (table_name VARCHAR, column_name VARCHAR, value VARCHAR, emb FLOAT[1024]);

-- Убираем ушедшее ТОЧЕЧНО — только по тем таблицам, которые мы в этот раз осмотрели
-- (`tmp3_src`). Удалять всё, чего нет в текущей выгрузке, нельзя: выгрузка из 1С бывает
-- неполной, и это стёрло бы живые данные (HOW_NOT_TO §4.2).
-- Две ветки, и обе нужны:
--   1. колонка перестала быть измерением (или ею и не была — так уходит мусор прежней
--      сборки: [замер] 43 680 значений из колонок `*_Base64Data`);
--   2. само значение исчезло из данных.
-- Служебные таблицы — не бизнес-данные. [замер] прежняя сборка индексировала
-- `base_profile`, `search_tables`, `search_corpus_bak` и даже сам `search_idx`,
-- то есть отправляла в облако нашу собственную служебную перепись.
DELETE FROM resolver_index r
WHERE NOT EXISTS (SELECT 1 FROM tmp3_src s WHERE s.tbl = r.table_name);

DELETE FROM resolver_index r
WHERE r.table_name IN (SELECT tbl FROM tmp3_src)
  AND (NOT EXISTS (SELECT 1 FROM res_dim d
                   WHERE d.tbl = r.table_name AND d.col = r.column_name)
       OR NOT EXISTS (SELECT 1 FROM res_val v
                      WHERE v.tbl = r.table_name AND v.col = r.column_name AND v.val = r.value));

-- Новые значения. Вектор НЕ считается здесь: он считается отдельным шагом только тем,
-- у кого его нет. Так повторный запуск на неизменных данных не стоит ни одного вызова
-- к облаку — это и есть исполнение п. 17.
INSERT INTO resolver_index (table_name, column_name, value, emb)
SELECT v.tbl, v.col, v.val, NULL
FROM res_val v
WHERE NOT EXISTS (SELECT 1 FROM resolver_index r
                  WHERE r.table_name = v.tbl AND r.column_name = v.col AND r.value = v.val);

SELECT 'резолвер' AS шаг, count(*) AS значений,
       count(*) FILTER (WHERE emb IS NULL) AS ждут_вектора,
       array_length(any_value(emb) FILTER (WHERE emb IS NOT NULL)) AS размерность
FROM resolver_index;
