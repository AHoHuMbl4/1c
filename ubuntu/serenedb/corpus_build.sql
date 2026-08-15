\timing on
\set ON_ERROR_STOP on

-- СБОРКА ПОИСКОВОГО КОРПУСА ШТАТНЫМИ СРЕДСТВАМИ SereneDB.
--
-- Это исполнение пункта 20 TARGET.md: данные лежат в SereneDB — работа с ними делается
-- внутри SereneDB. Питон здесь не участвует ни в одной строке: движок сам ходит по HTTP
-- в шлюз 1С за `$metadata`, сам разбирает XML регулярными выражениями, сам классифицирует
-- колонки, сам считает статистики, сам собирает текст и отпечаток.
--
-- Понятия «деньги» в сборке НЕТ: строка несёт все свои числовые величины картой
-- «имя → значение», а какую из них считать, решается по вопросу в момент ответа.
-- Своего кода в сборке корпуса не осталось вовсе.
--
-- ЗАПУСК: секрет с токеном шлюза подаётся ОТДЕЛЬНЫМ файлом с правами 600 и удаляется
-- в конце. «Временный» секрет SereneDB переживает сессию и виден любой другой —
-- `DROP SECRET` обязателен, сам он не исчезнет.
--
-- СОСТОЯНИЕ: файл боевой. Он собирает во временные таблицы `tmp3_*`, а перенос в корпус
-- делает `corpus_merge.sql` — разделение намеренное: сборка может упасть, не тронув
-- боевые объекты. Порядок вызова задаёт `build.sh`.
--
-- [замер 27.07] Один запуск процесса `psql`, 1 мин 58 с, ноль строк наружу.
-- Против прежней питоновской фазы: 258 с и около 1 190 запусков процесса.
--
-- ТАКТ — НЕ НОЧНОЙ. Решение владельца 28.07: понятие «ночная сборка» упразднено, цикл
-- обновления идёт не реже чем раз в 20 минут (п. 17 TARGET.md — реакция на новые данные).
-- Отсюда требования, которых у ночного прогона не было: замок от наложения тактов,
-- докатка прерванного и цена такта, не зависящая от размера базы, а только от изменений.

-- ============ 1. $metadata: движок сам ходит в 1С и сам разбирает XML ============
CREATE OR REPLACE TABLE tmp3_ent AS
SELECT lower(regexp_extract(b,'Name="([^"]+)"',1)) AS entity, b AS body
FROM (SELECT unnest(regexp_extract_all(content,'(?s)<EntityType\s.*?</EntityType>')) AS b
      FROM read_text(:'gate' || '/$metadata'));

CREATE OR REPLACE TABLE tmp3_prop AS
SELECT entity, x.prop, x.edm FROM (
  SELECT entity, regexp_extract(s,'<Property\s+Name="([^"]+)"\s+Type="([^"]+)"',['prop','edm']) AS x
  FROM (SELECT entity, unnest(regexp_extract_all(body,'<Property\s+Name="([^"]+)"\s+Type="([^"]+)"')) AS s
        FROM tmp3_ent));

CREATE OR REPLACE TABLE tmp3_key AS
SELECT entity, regexp_extract_all(regexp_extract(body,'(?s)<Key>(.*?)</Key>',1),
                                  '<PropertyRef\s+Name="([^"]+)"',1) AS key_cols
FROM tmp3_ent;

-- 🔴 Ответ 200 с НЕ ТЕМ телом (страница ошибки IIS, обрезанный XML, смена формата) даёт
-- пустые таблицы без единой ошибки. Дальше: ключей нет -> `keypos` пуст у всех колонок
-- -> ключом каждой строки становится отпечаток текста -> `MERGE` считает ВЕСЬ корпус
-- новым, `DELETE` сносит старый, эмбеддер получает 98 тысяч вызовов. Проверяем ДО того,
-- как что-либо посчитано: сравнение не с числом из головы, а с прошлым тактом.
SELECT CASE WHEN (SELECT count(*) FROM tmp3_ent) = 0
             OR (SELECT count(*) FROM tmp3_key WHERE len(key_cols) > 0) = 0
       THEN error('$metadata пусты или неполны: сущностей '
                  || (SELECT count(*) FROM tmp3_ent) || ', с ключом '
                  || (SELECT count(*) FROM tmp3_key WHERE len(key_cols) > 0)
                  || ' — сборка остановлена до изменения данных') END;

SELECT CASE WHEN prev > 0 AND (SELECT count(*) FROM tmp3_ent) * 2 < prev
       THEN error('$metadata усохли вдвое против прошлого такта: было '
                  || prev || ', стало ' || (SELECT count(*) FROM tmp3_ent)) END
FROM (SELECT coalesce(max(v), 0) AS prev FROM search_quality WHERE k = 'meta_entities');

DELETE FROM search_quality WHERE k = 'meta_entities';
INSERT INTO search_quality SELECT 'meta_entities', count(*), 'сущностей в $metadata' FROM tmp3_ent;

SELECT 'метаданные' AS шаг, (SELECT count(*) FROM tmp3_ent) AS сущностей,
       (SELECT count(*) FROM tmp3_prop) AS свойств,
       (SELECT count(*) FROM tmp3_key WHERE len(key_cols) > 0) AS с_ключом;

-- ============ 2. КЛАССИФИКАЦИЯ КОЛОНОК ============
-- ТАБЛИЦА, а не VIEW: коррелированный подзапрос к представлению с оконной функцией
-- роняет планировщик (LogicalProjection::GetExpression - table index mismatch).
CREATE OR REPLACE TABLE tmp3_cls AS
SELECT c.table_name AS tbl, c.column_index AS ord, c.column_name AS col, c.data_type, p.edm,
       CASE WHEN p.edm='Edm.Guid' THEN 'ref' WHEN p.edm='Edm.String' THEN 'text'
            WHEN p.edm='Edm.Boolean' THEN 'flag' WHEN p.edm='Edm.DateTime' THEN 'date'
            WHEN p.edm IN ('Edm.Double','Edm.Decimal','Edm.Int16','Edm.Int32','Edm.Int64','Edm.Byte') THEN 'num'
            WHEN p.edm IS NOT NULL THEN 'skip'
            WHEN EXISTS (SELECT 1 FROM tmp3_prop pe WHERE pe.entity=lower(c.table_name)) THEN 'skip'
            WHEN c.data_type='VARCHAR' THEN 'text' WHEN c.data_type='BOOLEAN' THEN 'flag'
            WHEN c.data_type LIKE 'TIMESTAMP%' OR c.data_type='DATE' THEN 'date'
            WHEN c.data_type IN ('BIGINT','INTEGER','DOUBLE','DECIMAL','SMALLINT','TINYINT') THEN 'num'
            ELSE 'skip' END AS kind,
       (c.column_name LIKE '%\_Type' AND EXISTS (SELECT 1 FROM tmp3_prop p2
            WHERE p2.entity=lower(c.table_name) AND p2.prop=regexp_replace(c.column_name,'_Type$',''))) AS is_companion,
       coalesce((SELECT k.key_cols=['Ref_Key'] FROM tmp3_key k WHERE k.entity=lower(c.table_name)),false) AS own_ref,
       -- 🔴 ПРИЗНАК «ОБЪЯВЛЕНИЕ СОБСТВЕННОЕ». Колонка объявлена самой сущностью, а не только
       -- её вложенным типом. Нужен, чтобы у ссылочного объекта в текст не попадали поля
       -- табличной части: они уже есть у своей сущности отдельным источником.
       -- Считается ЗДЕСЬ и один раз — соединение с объявлениями уже есть, новой работы нет.
       -- [замер 30.07] подзапрос на каждую сущность стоил бы 68 с в пересчёте на 1 502
       -- сущности против 98 мс одним разом; рост квадратичен по размеру базы.
       (p.entity = lower(c.table_name)) AS own_prop,
       -- 🔴 КТО ИМЕННО ОБЪЯВИЛ КОЛОНКУ. Нужно, чтобы условие «есть где взять» проверяло
       -- ТУ САМУЮ вложенную сущность, а не любую подходящую по шаблону имени. [замер 30.07]
       -- у документа с двумя табличными частями достаточно, чтобы одна не загрузилась
       -- (отказ 1С, права, пустая), и колонки ЭТОЙ части выбросились бы, потому что
       -- загрузилась соседняя. Шаблон имени к тому же не экранировал подчёркивания и
       -- ломался на именах объектов с `_`.
       p.entity AS decl_entity
FROM duckdb_columns() c
-- 🔴 ОБЪЯВЛЕНИЕ ИЩЕТСЯ И ВО ВЛОЖЕННОМ ТИПЕ. Регистры 1С отдают данные обёрткой, а поля
-- самих движений объявлены ОТДЕЛЬНОЙ сущностью, имя которой начинается с имени регистра
-- (`…_recordtype`). Загрузчик такие наборы разворачивает, и в витрине появляются колонки,
-- которых у обёртки нет. Классификатор их не находил и ставил `skip` — то есть
-- выбрасывал из текста: [замер 28.07] `Period`, `LineNumber`, `Active` и суммы проводок
-- не попадали в корпус вовсе, тексты 85 движений выходили ОДИНАКОВЫМИ, и слияние
-- останавливалось на дублях ключа. Данные при этом лежали в витрине целыми.
-- Правило структурное: имя вложенного типа начинается с имени сущности. Ни суффикса,
-- ни списка имён в коде нет — используется само соглашение платформы о вложенности.
LEFT JOIN tmp3_prop p ON p.prop = c.column_name
     AND (p.entity = lower(c.table_name)
          OR p.entity LIKE lower(c.table_name) || '\_%' ESCAPE '\')
-- 🔴 ИМЯ БАЗЫ НЕ ЗАШИТО. Прежде здесь стояло `database_name = 'postgres'` — имя нашей
-- базы на ЭТОМ стенде. На установке, где база SereneDB названа иначе, отбор давал бы
-- НОЛЬ источников, и корпус собрался бы пустым молча. [замер 28.07] найдено при
-- подготовке теста на второй базе: `current_database()` в `ut_test` вернул `ut_test`.
WHERE c.database_name=current_database()
-- Колонка бывает объявлена И у обёртки, И у вложенного типа — тогда соединение даёт ДВЕ
-- строки на одну колонку, и `map_from_entries` падает с «Map keys must be unique».
-- Оставляем одно объявление, приоритет — собственному: вложенный тип уточняет, а не
-- переопределяет.
QUALIFY row_number() OVER (PARTITION BY c.table_name, c.column_name
                           ORDER BY (p.entity = lower(c.table_name)) DESC NULLS LAST) = 1;

-- 🔴 ИСТОЧНИКИ БЕРУТСЯ ИЗ ОТДЕЛЬНОЙ ТАБЛИЦЫ, А НЕ ИЗ КОРПУСА.
-- Прежде здесь стояло `SELECT DISTINCT src_table FROM search_corpus`, и это была петля:
-- сущность, один раз собравшаяся пустой, вычищалась из корпуса и **выпадала из списка
-- навсегда**, а пустой корпус давал ноль источников — то есть после аварии сборка
-- не подняла бы ничего и отчиталась «0 строк» с кодом успеха. Найдено тремя
-- независимыми проверками и подтверждено замером на копии.
-- Перечень пополняется тем, что реально есть в витрине, и НИКОГДА не сужается молча:
-- пропавшая таблица остаётся в списке и попадает в отчёт, а не исчезает из мира.
-- Источник — это таблица, ОБЪЯВЛЕННАЯ СУЩНОСТЬЮ В `$metadata`, а не «всё, что не похоже
-- на служебное». Первая версия отбирала по шаблонам имён (`NOT LIKE 'tmp3_%'` и прочие),
-- и это был хардкод под нашу машину: [замер 28.07] в источники уехали `tmp_prod_corpus`,
-- `tmp_refmap`, `tbl_chunk` — корпус собрался на 235 532 строки вместо 97 965 и дал
-- 4 551 дубль ключа. Перечень имён нельзя ни угадать заранее, ни повторить у клиента.
-- Контракт платформы это решает сам: [замер] отбор по `$metadata` даёт ровно 226.
-- 🔴 ПЛОСКИЕ ТЕНИ РЕГИСТРОВ ИСКЛЮЧАЮТСЯ. Регистр 1С OData отдаёт ДВАЖДЫ: обёрткой
-- `<Регистр>` (одна запись на регистратор, движения внутри — их разворачивает загрузчик)
-- и плоской сущностью `<Регистр>_RecordType` с теми же движениями напрямую. [замер 28.07]
-- у `AccountingRegister_Хозрасчетный` обе дали по 280 строк — данные задвоены, а `_RecordType`
-- ещё и лез в кандидаты отдельной сущностью и путал выбор. Суффиксы `_RecordType`/`_RowType`
-- — технические имена платформы (одинаковы при любом языке конфигурации, это контракт
-- OData, а не бизнес-имя), поэтому отсев по ним не хардкод. Держим обёртку — у неё
-- человеческое имя; тень выбрасываем.
INSERT INTO search_sources
SELECT t.table_name, now() FROM duckdb_tables() t
WHERE t.database_name = current_database()
  AND EXISTS (SELECT 1 FROM tmp3_ent e WHERE e.entity = lower(t.table_name))
  AND t.table_name NOT ILIKE '%\_recordtype' ESCAPE '\'
  AND t.table_name NOT ILIKE '%\_rowtype'    ESCAPE '\'
  AND NOT EXISTS (SELECT 1 FROM search_sources s WHERE s.src_table = t.table_name);

-- Тень, попавшая в источники прежним прогоном, уходит из перечня.
DELETE FROM search_sources
WHERE src_table ILIKE '%\_recordtype' ESCAPE '\' OR src_table ILIKE '%\_rowtype' ESCAPE '\';

-- То, что источником быть перестало (или никогда им не было), из перечня уходит: иначе
-- ошибка одного прогона осталась бы в списке навсегда.
DELETE FROM search_sources s
WHERE NOT EXISTS (SELECT 1 FROM tmp3_ent e WHERE e.entity = lower(s.src_table));

-- В сборку идут только те источники, чьи таблицы существуют СЕЙЧАС. Пропавшие не
-- удаляются из перечня — они попадут в отчёт как «источник исчез».
CREATE OR REPLACE TABLE tmp3_src AS
SELECT s.src_table AS tbl FROM search_sources s
-- 🔴 ФИЛЬТР ПО БАЗЕ ОБЯЗАТЕЛЕН: `duckdb_tables()` видит ВСЕ присоединённые базы.
-- [замер 28.07] из `ut_test` он показал 1 605 своих таблиц И 302 чужих. Без фильтра
-- источник считался существующим, потому что есть в ДРУГОЙ базе, и `query_table()`
-- падал: «Table catalog_внешниекомпоненты does not exist». Найдено на второй базе.
WHERE EXISTS (SELECT 1 FROM duckdb_tables() t WHERE t.table_name = s.src_table
              AND t.database_name = current_database());

SELECT CASE WHEN count(*) > 0
       THEN error('источники исчезли из витрины (идёт синк?): ' || string_agg(src_table, ', ')) END
FROM search_sources s
WHERE NOT EXISTS (SELECT 1 FROM duckdb_tables() t WHERE t.table_name = s.src_table
                  AND t.database_name = current_database());

SELECT 'классификация' AS шаг, (SELECT count(*) FROM tmp3_src) AS сущностей_корпуса,
       (SELECT count(*) FROM tmp3_cls WHERE tbl IN (SELECT tbl FROM tmp3_src)) AS колонок;

-- ============ 2-quater. ЧТО ПЕРЕЧИТЫВАТЬ: ТОЛЬКО ИЗМЕНИВШЕЕСЯ ============
-- 🔴 Требование владельца 06.08: «обязательно не делать проходы по данным, которые не
-- изменялись». Здесь оно и решается. [замер 06.08] стоило измениться одной строке — и
-- сборка перечитывала ВСЕ 554 источника ДВАЖДЫ: один проход строит карту ссылок, другой
-- собирает текст. 2258 операторов, 806 с, из них 724 с — именно эти два прохода; самый
-- тяжёлый одиночный запрос всего 8,8 с, то есть дело не в тяжёлом запросе, а в том, что
-- проходов столько же, сколько источников.
--
-- 🔴 ИДТИ ПО-ИЗМЕНИВШЕМУСЯ МОЖНО ТОЛЬКО ПРИ ТРЁХ УСЛОВИЯХ СРАЗУ, иначе полный проход:
--   * синк сказал, какие таблицы изменились, И признал список полным
--     (`changed_sources_ok = 1`: при ошибке загрузки хоть одной сущности список неполон);
--   * боевой корпус не пуст — иначе собирать нечего и не с чем сравнивать;
--   * карта ссылок сохранена с прошлого раза — иначе имена брать неоткуда.
-- Ошибка при любом сомнении идёт в сторону лишней работы, а не потери данных.
CREATE TABLE IF NOT EXISTS search_changed_sources (src_table VARCHAR);
CREATE TABLE IF NOT EXISTS search_refmap (guid VARCHAR, name VARCHAR, owner VARCHAR);
-- Права выдаются при создании: пересозданная таблица их теряет, и читатель молча получает
-- пустоту — та же грабля, что разобрана в шапке `corpus_init.sql`.
GRANT SELECT ON search_refmap TO serene_ro;
GRANT SELECT ON search_changed_sources TO serene_ro;

CREATE OR REPLACE TABLE tmp3_inc AS
SELECT (coalesce((SELECT v FROM search_quality WHERE k = 'changed_sources_ok'), 0) = 1
        AND (SELECT count(*) FROM search_corpus) > 0
        AND (SELECT count(*) FROM search_refmap) > 0) AS on_;

-- Изменившиеся источники — те, что назвал синк, и только из числа собираемых.
CREATE OR REPLACE TABLE tmp3_changed AS
SELECT s.tbl FROM tmp3_src s
WHERE (SELECT on_ FROM tmp3_inc)
  AND EXISTS (SELECT 1 FROM search_changed_sources c WHERE c.src_table = s.tbl);

SELECT 'по-изменившемуся' AS шаг,
       (SELECT on_ FROM tmp3_inc) AS можно,
       (SELECT count(*) FROM tmp3_changed) AS изменилось_источников,
       (SELECT count(*) FROM tmp3_src) AS всего_источников;

-- ============ 2-бис. КАРТА СУЩНОСТЕЙ: метка и связь шапка↔часть ============
-- 🔴 `search_tables` (имя сущности для выбора моделью + связь `parent`) ПЕРЕСОБИРАЕТСЯ
-- ЗДЕСЬ. Прежде её наполнял только питоновский сборщик, а штатный такт не трогал — и она
-- устаревала: [замер 28.07] 8 новых сущностей (включая регистр бухучёта) не имели метки,
-- и модель их не выбирала — «обороты по счёту» уходили не в тот источник. Метка — из
-- `$metadata` (контракт), а не из старой памяти.
CREATE OR REPLACE TABLE tmp3_names AS
SELECT lower(regexp_extract(body,'Name="([^"]+)"',1)) AS ent,
       regexp_extract(body,'Name="([^"]+)"',1) AS orig
FROM tmp3_ent;

-- Метка = человекочитаемое имя: убрать тип-префикс (`Catalog_`/`Document_`/…), разбить
-- CamelCase пробелом. Подчёркивание табличной части сохраняется, как в прежнем формате.
-- parent = имя без последнего сегмента, если такой источник существует (табличная часть).
-- `emb = NULL` у изменившихся — вектор метки досчитает `embed_missing` штатным шагом.
MERGE INTO search_tables t
USING (
  SELECT s.tbl AS src_table,
         regexp_replace(regexp_replace(n.orig, '^[^_]+_', ''),
                        '([\p{Ll}0-9])([\p{Lu}])', '\1 \2', 'g') AS label,
         CASE WHEN len(str_split(s.tbl, '_')) >= 3
                   AND regexp_replace(s.tbl, '_[^_]+$', '')
                       IN (SELECT tbl FROM tmp3_src)
              THEN regexp_replace(s.tbl, '_[^_]+$', '') END AS parent
  FROM tmp3_src s JOIN tmp3_names n ON n.ent = lower(s.tbl)
) x ON t.src_table = x.src_table
WHEN MATCHED AND (t.label IS DISTINCT FROM x.label OR t.parent IS DISTINCT FROM x.parent)
     THEN UPDATE SET label = x.label, parent = x.parent, emb = NULL
WHEN NOT MATCHED THEN
     INSERT (src_table, label, parent, emb) VALUES (x.src_table, x.label, x.parent, NULL);

DELETE FROM search_tables WHERE src_table NOT IN (SELECT tbl FROM tmp3_src);

SELECT 'карта сущностей' AS шаг, count(*) AS всего,
       count(*) FILTER (WHERE label IS NULL OR label = '') AS без_метки,
       count(*) FILTER (WHERE parent IS NOT NULL) AS табличных_частей
FROM search_tables;

-- ============ 2-тер. КТО ПИШЕТ ЭТОТ ИСТОЧНИК: связь «регистр ← регистратор» ============
-- 🔴 ЗАЧЕМ. Выбор сущности брал регистр накопления вместо документа, который этот регистр
-- пишет: «Сколько штук мы закупили?» уходило в `accumulationregister_закупки` вместо
-- `document_приобретениетоваровуслуг`. Дело не в счёте: все сигналы выбора — метка, её
-- вектор, карточка, реранкер, синонимы — про НАЗВАНИЕ, а в 1С регистр назван деловым
-- языком («Закупки»), документ — канцелярским («Приобретение Товаров Услуг»). Человек
-- спрашивает деловым, и все именные сигналы дружно подтверждают регистр. Добавление
-- четвёртого именного не помогает: [замер 04.08] показ модели вида записи
-- (`Document`/`AccumulationRegister`) дал 3 ошибки → 6. Нужен сигнал, который не имя.
--
-- Он лежит в наших данных и до сих пор терялся на сборке. У движений регистра есть
-- регистратор (`Recorder` + спутник `Recorder_Type`); спутники `%_Type` помечаются
-- `is_companion` (:86) и в текст корпуса не идут — для поиска словами это верно, тип
-- ссылки не текст вопроса. Но связь не переносилась НИКУДА: `search_tables` знала только
-- `label` и `parent`. [замер 05.08, ut_test] в `accumulationregister_закупки` 1 443
-- движения из 1 901 написаны `Document_ПриобретениеТоваровУслуг` — ровно та пара, на
-- которой выбор спотыкался, и она лежала в витрине готовой.
--
-- 🔴 ЧТО ЗДЕСЬ НЕ ХАРДКОД. Имён нашей базы нет ни одного: перечень регистров не
-- перечисляется, а спрашивается — колонка ищется в каталоге движка (`duckdb_columns()`)
-- И обязана быть объявлена КЛЮЧОМ в `$metadata` (`tmp3_key`), то есть платформа сама
-- назвала её тождеством записи. `Recorder` — имя САМОЙ ПЛАТФОРМЫ 1С, одинаковое на любой
-- конфигурации и языке; тот же класс факта, что `Ref_Key`, `DataVersion`, `LineNumber`
-- (:415) и суффикс `_RecordType` (:146), и ровно так же оно проверяется по каталогу, а
-- не предполагается. Значение приезжает как `StandardODATA.Document_X` — пространство
-- имён OData; имя источника получается отбрасыванием этого префикса, как выше строится
-- `label` (:205), и обязано найтись СРЕДИ ИСТОЧНИКОВ: выдуманных связей не заводим,
-- ненайденное считается числом ниже, а не пропадает молча (п. 13).
--
-- 🔴 ПОРОГА ЗДЕСЬ НЕТ, И ЭТО НАМЕРЕННО. «Преобладающий регистратор» — `count(*)` по
-- данным, а не правило из головы. Рядом со связью кладутся её доля и полный расклад,
-- поэтому «схлопывать пару или спрашивать человека» решает тот, кто отвечает на вопрос,
-- по числам — а не сборка, назначившая порог за него. [замер 05.08, ut_test] 81 источник
-- с регистратором, у всех 81 регистратор нашёлся среди источников; доля преобладающего
-- больше половины у 47, медиана 0,56, единственный регистратор у 11 — то есть «регистр
-- агрегирует разные документы» это не редкость, а обычный случай, и объявлять такую
-- связь однозначной было бы неправдой.
CREATE OR REPLACE TABLE tmp3_regsrc AS
SELECT s.tbl FROM tmp3_src s
-- Фильтр по текущей базе обязателен: `duckdb_columns()` отдаёт колонки ВСЕХ
-- присоединённых баз (`techContext` ловушка 25).
WHERE EXISTS (SELECT 1 FROM duckdb_columns() c
              WHERE c.database_name = current_database()
                AND c.table_name = s.tbl AND c.column_name = 'Recorder_Type')
  AND EXISTS (SELECT 1 FROM tmp3_key k
              WHERE k.entity = lower(s.tbl) AND list_contains(k.key_cols, 'Recorder_Type'));

CREATE OR REPLACE TABLE tmp3_writer (src_table VARCHAR, writer_raw VARCHAR, n BIGINT);

PREPARE p_writer AS
INSERT INTO tmp3_writer
SELECT $1::VARCHAR, "Recorder_Type", count(*)
FROM query_table($1)
WHERE "Recorder_Type" IS NOT NULL AND "Recorder_Type" <> ''
GROUP BY 2;

-- Одна сущность не должна ронять такт — как и в сборке текста (:595). Не посчитавшееся
-- не исчезает: оно попадает в число `writer_failed` ниже.
\set ON_ERROR_STOP off
SELECT 'EXECUTE p_writer(' || quote_literal(tbl) || ');' FROM tmp3_regsrc
\gexec
\set ON_ERROR_STOP on

CREATE OR REPLACE TABLE tmp3_link AS
WITH w AS (
  -- `StandardODATA.Document_X` -> `document_x`: отбрасывается пространство имён OData.
  SELECT src_table, lower(regexp_replace(writer_raw, '^.*\.', '')) AS writer, sum(n) AS n
  FROM tmp3_writer GROUP BY 1, 2),
agg AS (
  SELECT src_table, sum(n) AS total,
         -- 🔴 ПОРЯДОК КЛЮЧЕЙ КАРТЫ ЗАДАЁТСЯ ЯВНО — как у `nums` (:529): сравнение `MAP`
         -- в движке зависит от порядка, и без `ORDER BY` связь «менялась» бы каждый такт
         -- у всех регистров, а число изменений перестало бы что-либо значить.
         map_from_entries(list({'key': writer, 'value': n} ORDER BY writer)) AS all_writers,
         -- Порядок ПОЛНЫЙ: по числу движений, при равенстве — по имени. Иначе выбор
         -- преобладающего зависел бы от порядка чтения (`techContext` ловушки 29, 30).
         (list(writer ORDER BY n DESC, writer))[1] AS top_writer,
         (list(n      ORDER BY n DESC, writer))[1] AS top_n
  FROM w GROUP BY src_table)
SELECT src_table, all_writers, total, top_writer,
       -- Связь заводится, только если регистратор ЕСТЬ среди источников. Доля идёт с ней
       -- в паре: доля без связи — число, к которому нечего отнести.
       CASE WHEN EXISTS (SELECT 1 FROM tmp3_src s WHERE s.tbl = top_writer)
            THEN top_writer END AS written_by,
       CASE WHEN EXISTS (SELECT 1 FROM tmp3_src s WHERE s.tbl = top_writer)
            THEN top_n::DOUBLE / total END AS share
FROM agg;

-- Связь обновляется ОТДЕЛЬНЫМ `MERGE`, а не вместе с меткой, по одной причине: у метки
-- изменение сбрасывает `emb` (:214), потому что меняется сам текст под вектором. Здесь
-- текст не меняется — вектор метки обязан уцелеть, иначе каждая правка связи стоила бы
-- пересчёта 1 502 векторов и денег эмбеддера.
MERGE INTO search_tables t
USING (SELECT src_table, written_by, share, all_writers FROM tmp3_link) x
   ON t.src_table = x.src_table
WHEN MATCHED AND (t.written_by       IS DISTINCT FROM x.written_by
               OR t.written_by_share IS DISTINCT FROM x.share
               OR t.written_by_all   IS DISTINCT FROM x.all_writers)
     THEN UPDATE SET written_by = x.written_by, written_by_share = x.share,
                     written_by_all = x.all_writers;

-- Источник перестал быть регистром (или его движения исчезли) — связь уходит. Иначе
-- ошибка одного прогона осталась бы в карте навсегда, как это уже было с источниками (:162).
UPDATE search_tables SET written_by = NULL, written_by_share = NULL, written_by_all = NULL
WHERE (written_by IS NOT NULL OR written_by_share IS NOT NULL OR written_by_all IS NOT NULL)
  AND NOT EXISTS (SELECT 1 FROM tmp3_link l WHERE l.src_table = search_tables.src_table);

DELETE FROM search_quality WHERE k LIKE 'writer_%';
INSERT INTO search_quality
SELECT 'writer_sources', count(*), 'источников с регистратором (`Recorder_Type` в объявленном ключе)'
FROM tmp3_regsrc
UNION ALL
SELECT 'writer_linked', count(*), 'источников получили связь «кто пишет»'
FROM tmp3_link WHERE written_by IS NOT NULL
UNION ALL
SELECT 'writer_multi', count(*), 'из них пишутся более чем одним источником — связь не однозначна'
FROM tmp3_link WHERE written_by IS NOT NULL AND len(map_keys(all_writers)) > 1
UNION ALL
-- 🔴 Регистратор есть в данных, а источника с таким именем нет: документ не загружен,
-- закрыт правами или отсеян. Связь не заводится, но молчать об этом нельзя (п. 13).
SELECT 'writer_unresolved', count(*), 'преобладающий регистратор не найден среди источников'
FROM tmp3_link WHERE written_by IS NULL
UNION ALL
SELECT 'writer_failed', count(*), 'источников с регистратором без единой связи: нет движений или шаг не прошёл'
FROM tmp3_regsrc r WHERE NOT EXISTS (SELECT 1 FROM tmp3_writer w WHERE w.src_table = r.tbl);

SELECT 'связь «кто пишет»' AS шаг,
       (SELECT count(*) FROM tmp3_regsrc) AS с_регистратором,
       (SELECT count(*) FROM tmp3_link WHERE written_by IS NOT NULL) AS связей,
       (SELECT count(*) FROM tmp3_link WHERE written_by IS NOT NULL
                                         AND len(map_keys(all_writers)) > 1) AS пишут_несколько,
       (SELECT round(median(share), 2) FROM tmp3_link WHERE written_by IS NOT NULL) AS медиана_доли;

-- ============ 3. КОЛОНКА-НАИМЕНОВАНИЕ и КАРТА ССЫЛОК ============
CREATE OR REPLACE TABLE tmp3_namecol (tbl VARCHAR, col VARCHAR, ord INT, score DOUBLE, std INT);
PREPARE p_stats AS
INSERT INTO tmp3_namecol
WITH n AS (SELECT count(*)::DOUBLE AS rows FROM query_table($1)),
     cells AS (SELECT * FROM (SELECT COLUMNS(*)::VARCHAR FROM query_table($1)) s
                    UNPIVOT (val FOR col IN (COLUMNS(*)))),
     agg AS (SELECT u.col,
                    avg(len(str_split(u.val,' '))) AS words,
                    avg(length(regexp_replace(u.val,'[^\p{L}]','','g'))::DOUBLE
                        / greatest(length(u.val),1)) AS alpha,
                    count(DISTINCT u.val)::DOUBLE/(SELECT rows FROM n) AS uniq,
                    bool_or(regexp_matches(u.val,'^(https?://|/)')) AS machine
             FROM cells u WHERE u.val<>'' GROUP BY u.col)
SELECT $1::VARCHAR, c.col, c.ord, a.words*a.alpha*a.uniq,
       CASE c.col WHEN 'Description' THEN 0 WHEN 'Code' THEN 1 ELSE 2 END
FROM agg a JOIN tmp3_cls c ON c.tbl=$1 AND c.col=a.col
WHERE c.kind='text' AND NOT c.is_companion AND c.col<>'DataVersion' AND NOT a.machine
QUALIFY c.col IN ('Description','Code')
     OR (a.words*a.alpha*a.uniq > 0
         AND a.words*a.alpha*a.uniq >= max(a.words*a.alpha*a.uniq) OVER () / 2);

SELECT 'EXECUTE p_stats(' || quote_literal(s.tbl) || ');'
FROM tmp3_src s JOIN tmp3_key k ON k.entity=lower(s.tbl)
WHERE k.key_cols=['Ref_Key']
\gexec

-- Сырая карта: по строке на каждое вхождение идентификатора. Однозначной она станет
-- ниже; здесь намеренно собирается ВСЁ, чтобы было из чего выбирать.
CREATE OR REPLACE TABLE tmp3_refmap_raw (guid VARCHAR, name VARCHAR, owner VARCHAR);
PREPARE p_ref AS
INSERT INTO tmp3_refmap_raw
WITH src AS (SELECT row_number() OVER () AS rid, COLUMNS(*)::VARCHAR FROM query_table($1)),
     cells AS (SELECT * FROM src UNPIVOT (val FOR col IN (COLUMNS(* EXCLUDE (rid))))),
     rows AS (SELECT u.rid,
                     max(u.val) FILTER (WHERE u.col='Ref_Key') AS guid,
                     -- 🔴 `nc.col` В КОНЦЕ СОРТИРОВКИ ОБЯЗАТЕЛЕН. Без него у колонок с
                     -- РАВНЫМИ (std, score) порядок произволен, склеенное имя выходит
                     -- разным от сборки к сборке — а вместе с ним и `row_key` строк
                     -- регистров (`sha1(doc)`). [замер 29.07] равных групп 30, имён из
                     -- нескольких колонок 27 177 из 42 107; после починки карты
                     -- расхождение ключей упало с 64 107 до 1 299, и остаток был именно
                     -- здесь. Имя колонки устойчиво, поэтому порядок становится одним и
                     -- тем же при любом порядке чтения.
                     list(u.val ORDER BY nc.std, nc.score DESC, nc.col)
                       FILTER (WHERE nc.col IS NOT NULL AND u.val<>'') AS names
              FROM cells u LEFT JOIN tmp3_namecol nc ON nc.tbl=$1 AND nc.col=u.col
              GROUP BY u.rid)
SELECT guid,
       list_aggregate(list_reduce(names, (acc,x) -> CASE WHEN len(list_filter(acc, y -> contains(y,x)))>0
                                                          THEN acc ELSE list_append(acc,x) END, []::VARCHAR[]),
                      'string_agg', ' / ') AS name,
       $1::VARCHAR AS owner
FROM rows
WHERE guid IS NOT NULL AND guid <> '00000000-0000-0000-0000-000000000000'
  AND names IS NOT NULL AND len(names) > 0;

-- 🔴 КАРТА ССЫЛОК ЖИВЁТ МЕЖДУ ТАКТАМИ, А НЕ СТРОИТСЯ ЗАНОВО. Прежде `p_ref` шёл по каждому
-- источнику-объекту КАЖДЫЙ раз — это половина тех 724 с, что уходили на проходы по
-- неизменившимся данным. Теперь постоянная `search_refmap` хранит карту, а перечитываются
-- только изменившиеся владельцы; остальные записи остаются как были.
--
-- Имена «до» снимаются ДО обновления: по ним ниже находится, у кого имя поменялось, —
-- иначе в тексте документа осталось бы старое название контрагента, и это была бы тихая
-- порча (п. 13), а не экономия.
CREATE OR REPLACE TABLE tmp3_names_before AS
SELECT guid, name FROM (
  SELECT guid, name, owner, count(*) OVER (PARTITION BY owner, guid) AS вх
  FROM search_refmap)
QUALIFY row_number() OVER (PARTITION BY guid ORDER BY вх, owner, name) = 1;

SELECT 'EXECUTE p_ref(' || quote_literal(s.tbl) || ');'
FROM tmp3_src s JOIN tmp3_key k ON k.entity=lower(s.tbl)
WHERE k.key_cols=['Ref_Key']
  AND (NOT (SELECT on_ FROM tmp3_inc)
       OR EXISTS (SELECT 1 FROM tmp3_changed c WHERE c.tbl = s.tbl))
\gexec

-- Перечитанные владельцы заменяются целиком, прочие остаются. При полном проходе
-- заменяется вся карта — условие ниже покрывает оба случая одним выражением.
DELETE FROM search_refmap
WHERE NOT (SELECT on_ FROM tmp3_inc)
   OR owner IN (SELECT DISTINCT owner FROM tmp3_refmap_raw);
INSERT INTO search_refmap SELECT guid, name, owner FROM tmp3_refmap_raw;

-- 🔴 КАРТА ССЫЛОК ОБЯЗАНА БЫТЬ ОДНОЗНАЧНОЙ, ИНАЧЕ КОРПУС НЕ ВОСПРОИЗВОДИМ.
-- [замер 29.07, УТ] пересборка тех же данных дала 632 683 строки — ровно столько же, —
-- но у **64 107** из них изменился `row_key`, и слияние остановилось защитой «удаление
-- снесло бы 10% корпуса». Все пострадавшие — РЕГИСТРЫ, то есть сущности без объявленного
-- ключа, где `row_key = sha1(doc)`. Значит менялся сам текст.
--
-- Причина: `p_ref` собирает карту по КАЖДОЙ таблице, а у табличных частей документа
-- `Ref_Key` — это ключ РОДИТЕЛЯ. Поэтому на один идентификатор попадало несколько строк
-- с разными именами: [замер] 50 535 строк на 42 107 различных идентификаторов, из них
-- **223 идентификатора с несколькими именами**. Соединение брало произвольное — и текст
-- строки, а с ним и ключ, менялись от сборки к сборке.
--
-- Чем это грозило, если бы защита не сработала: каждая пересборка выглядит как «десятая
-- часть данных изменилась», такие строки теряют вектор и считаются заново — за деньги,
-- каждый раз. Та же семья дефектов, что `techContext` ловушка 22.
--
-- Выбор ДЕТЕРМИНИРОВАННЫЙ и осмысленный:
--   1. сначала владелец, у которого этот идентификатор встречается ОДИН раз — это
--      настоящий объект, а не строка табличной части;
--   2. при равенстве — по имени таблицы, затем по самому имени. Оба поля устойчивы,
--      поэтому результат один и тот же при любом порядке чтения.
CREATE OR REPLACE TABLE tmp3_refmap AS
SELECT guid, name, owner FROM (
  SELECT guid, name, owner,
         count(*) OVER (PARTITION BY owner, guid) AS вхождений_у_владельца
  FROM search_refmap)
QUALIFY row_number() OVER (PARTITION BY guid
        ORDER BY вхождений_у_владельца, owner, name) = 1;

SELECT 'карта ссылок' AS шаг, count(*) AS записей FROM tmp3_refmap;

-- ============ 3-бис. У КОГО ПОМЕНЯЛОСЬ ИМЯ ============
-- 🔴 ЗДЕСЬ ЕДИНСТВЕННОЕ МЕСТО, ГДЕ ЭКОНОМИЯ МОГЛА БЫ ИСПОРТИТЬ ДАННЫЕ. Имя ссылки попадает
-- В ТЕКСТ строки («Контрагент: Ромашка»), поэтому переименование записи меняет текст у
-- всех, кто на неё ссылается, — а их собственные таблицы при этом не менялись. Пропусти
-- мы их, в корпусе осталось бы старое название при живом ключе: молчаливое расхождение
-- текста и данных.
--
-- Ищем по СТАРОМУ имени в `refs` — там лежат ровно пары «реквизит: имя», по которым текст
-- и собран. Это ОДИН проход по корпусу, а не проход по каждому источнику: разница между
-- «прочитать одну таблицу» и «прочитать пятьсот».
CREATE OR REPLACE TABLE tmp3_renamed AS
SELECT b.guid, b.name AS old_name
FROM tmp3_names_before b JOIN tmp3_refmap n USING (guid)
WHERE (SELECT on_ FROM tmp3_inc) AND n.name IS DISTINCT FROM b.name;

-- 🔴 ПРЕДЕЛ ОБЯЗАТЕЛЕН, И ОН ЖЕ ЗАЩИТА. Поиск по многим именам сразу стоит дороже полной
-- пересборки, а массовое переименование — это и есть случай, когда собрать заново честнее.
-- Порог не про правильность: при его превышении делается БОЛЬШЕ работы, а не меньше.
CREATE OR REPLACE TABLE tmp3_build AS
SELECT tbl FROM tmp3_src
WHERE NOT (SELECT on_ FROM tmp3_inc)
   OR (SELECT count(*) FROM tmp3_renamed) > 200
   OR tbl IN (SELECT tbl FROM tmp3_changed)
   OR tbl IN (SELECT DISTINCT c.src_table FROM search_corpus c
                WHERE EXISTS (SELECT 1 FROM tmp3_renamed r
                              WHERE r.old_name <> '' AND contains(c.refs, r.old_name)));

SELECT 'к пересборке' AS шаг,
       (SELECT count(*) FROM tmp3_renamed) AS переименовано,
       (SELECT count(*) FROM tmp3_build) AS источников,
       (SELECT count(*) FROM tmp3_src) AS всего;

-- ============ 4. ДАТА ЗАПИСИ ============
CREATE OR REPLACE TABLE tmp3_datecol AS
SELECT tbl, col FROM (
  SELECT tbl, col, ord, CASE col WHEN 'Date' THEN 0 WHEN 'Period' THEN 1 ELSE 2 END AS pr,
         count(*) OVER (PARTITION BY tbl) AS ndates,
         min(CASE col WHEN 'Date' THEN 0 WHEN 'Period' THEN 1 ELSE 2 END) OVER (PARTITION BY tbl) AS best
  FROM tmp3_cls WHERE kind='date')
WHERE (best < 2 AND pr = best) OR (best = 2 AND ndates = 1)
QUALIFY row_number() OVER (PARTITION BY tbl ORDER BY pr, ord) = 1;

-- ============ 5. ВЕЛИЧИНЫ СТРОКИ ============
-- 🔴 Здесь БОЛЬШЕ НЕ ВЫБИРАЕТСЯ «денежная колонка». Строка несёт ВСЕ свои числовые
-- величины разом, картой «имя величины → значение».
--
-- Почему прежний путь был неверен (замечание владельца 28.07): «pick_money_col — про
-- деньги, а мы говорили, что это не универсально. Базы разные бывают». Выбор одной
-- колонки из многих означал, что на вопрос «сколько ШТУК продано» отвечать нечем:
-- количества в корпусе не было вовсе — отсюда работа 3 в PRODUCTION_PLAN и ответ
-- «числом документов вместо количества».
--
-- Понятия «деньги» в коде теперь нет. Какую величину считать — решается ПО ВОПРОСУ, в
-- момент ответа: имена величин сущности достаются из самих данных (`map_keys`), а слово
-- человека сопоставляет с ними модель. Это её работа по п. 19 и короткий список — не
-- схема базы, а величины одной сущности.


-- ============ 6. СБОРКА ТЕКСТА ============
CREATE OR REPLACE TABLE tmp3_corpus
  (src_table VARCHAR, row_key VARCHAR, doc VARCHAR, refs VARCHAR, doc_hash VARCHAR,
   nums MAP(VARCHAR, DOUBLE), flags MAP(VARCHAR, BOOLEAN), doc_date TIMESTAMP,
   refs_map MAP(VARCHAR, VARCHAR), refs_own MAP(VARCHAR, VARCHAR));

PREPARE p_doc AS
INSERT INTO tmp3_corpus
WITH kc AS (SELECT key_cols FROM tmp3_key WHERE entity = lower($1)),
 -- 🔴 ОДНО ВЫРАЖЕНИЕ НА ДВА МЕСТА. Прежде условие «есть где взять» стояло только у
 -- отбрасывания колонок, а свёртка строк была безусловной: там, где условие защитило
 -- колонки, строки всё равно схлопывались до одной — и данные табличной части исчезали.
 -- Защита стояла на входе, а потеря происходила на выходе. Теперь оба места смотрят
 -- в одно выражение, и разойтись не могут по построению.
 --
 -- Подчёркивания В САМОМ имени экранируются: имя объекта 1С законно бывает с
 -- подчёркиванием (отраслевые префиксы), и без экранирования `Catalog_Мои_Товары`
 -- считался бы дочерним для `Catalog_Мои`.
 fold AS (SELECT (SELECT key_cols FROM kc) = ['Ref_Key'] AS on_),
 -- coalesce ДО unpivot: иначе пустые ячейки исчезают вовсе (UNPIVOT роняет NULL), и
 -- составной ключ схлопывается. Боевой ключ выглядит как «160.1|||ЛЕПРО|___|ЗП80РК» —
 -- пустые сегменты значимы, они держат позицию. Без них разные строки дают ОДИН ключ,
 -- то есть строка теряется молча (п. 13). Замерено: 789 строк из 97 965.
 -- ОБРЕЗКА ЗНАЧЕНИЯ. Хранилища и вложения приезжают в витрину как текст, и без обрезки
 -- строка корпуса вырастает до сотен тысяч символов. [замер 27.07] без неё самый длинный
 -- текст стал 560 400 символов против 15 724 у боевого кода, и две такие строки не могут
 -- получить вектор вовсе: у эмбеддера предел длины входа 33 000. Режем ЗНАЧЕНИЕ, а не
 -- строку целиком — так теряется хвост вложения, а не реквизиты (боевой аналог — clip()).
 src AS (SELECT row_number() OVER () AS rid, substr(coalesce(COLUMNS(*)::VARCHAR, ''), 1, 20000) FROM query_table($1)),
 cells AS (SELECT * FROM src UNPIVOT (val FOR col IN (COLUMNS(* EXCLUDE (rid))))),
 -- Ключ собирается ОТДЕЛЬНО и до отбрасывания пустых: он про тождество строки,
 -- а не про текст. Порядок сегментов — объявленный порядок ключа из $metadata.
 keyed AS (
   SELECT u.rid, string_agg(u.val, '|' ORDER BY list_position((SELECT key_cols FROM kc), u.col)) AS row_key
   FROM cells u
   WHERE list_position((SELECT key_cols FROM kc), u.col) IS NOT NULL
   GROUP BY u.rid),
 j AS (
   SELECT u.rid, u.col, u.val, c.ord, c.kind, c.own_ref,
          list_position((SELECT key_cols FROM kc), u.col) AS keypos,
          r.name AS refname, r.owner AS refowner,
          (c.kind='ref' OR regexp_full_match(u.val,'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}')) AS is_guid,
          (c.kind IN ('text','flag') AND NOT c.is_companion AND c.col <> 'DataVersion'
           AND NOT regexp_matches(u.val,'^(https?://|/)')) AS in_text,
          (c.kind = 'num') AS is_num,
          -- Булев реквизит — ОТДЕЛЬНАЯ карта, как и величины, и по той же причине:
          -- обращаться к реквизиту по имени, а не искать подстроку в тексте документа.
          -- [ревизия 30.07] `contains(doc, 'IsFolder: true')` — подстрочный поиск: литерал
          -- может встретиться в комментарии или наименовании, и запись молча выпадет из
          -- счёта. Сегодня совпадений нет (375 = 375 по граничному regexp), но булевых
          -- реквизитов в корпусе 830 имён у 376 301 строки — на следующем совпадёт.
          -- Агент `serenedb-native` проверил на живом движке: штатного способа достать
          -- именованный реквизит из УЖЕ СОБРАННОГО текста у движка нет, `ts_phrase` даёт
          -- ровно те же ложные срабатывания. Значит карта строится при сборке.
          (c.kind = 'flag') AS is_flag,
          -- 🔴 ВЕЛИЧИНА И ЧИСЛО В ТЕКСТЕ — РАЗНЫЕ ВЕЩИ, И ЭТО ОПЛАЧЕНО ОШИБКОЙ.
          -- [замер 30.07] `SurrogateKey` попал в карту величин у 656 сущностей,
          -- `LineNumber` — у 359, и на вопрос «сколько штук закупили» система отвечала
          -- «считано по величине SurrogateKey». Складывать ключ бессмысленно: это
          -- тождество строки, а не измерение.
          --
          -- Первая моя попытка исключила их из `is_num` — то есть СРАЗУ и из величин, и из
          -- ТЕКСТА строки. Слияние отказало: «дублей ключа 1368». У обёрток регистров ключ
          -- объявлен как `{Recorder, Recorder_Type}` и строки НЕ различает — их различал
          -- именно номер строки в тексте. Без него тексты совпали, отпечатки совпали.
          -- Защита сработала и перенос остановила, корпус остался цел.
          --
          -- Поэтому признаки разведены: в тексте число остаётся (оно про тождество
          -- строки), в карту величин не идёт (там только то, что можно складывать).
          -- Отличаем двумя правилами и БЕЗ списка слов о конкретной базе:
          --   1) колонка входит в объявленный ключ (`$metadata` → `kc`) — тот же источник,
          --      что `Ref_Key`; снимает `SurrogateKey` целиком (656 → 0);
          --   2) `LineNumber`/`SurrogateKey` — имена САМОЙ ПЛАТФОРМЫ 1С, одинаковые на
          --      любой конфигурации и языке. Нужны потому, что у обёрток регистров первое
          --      правило их не ловит: [замер] уцелели 95 сущностей из 359. Тот же класс
          --      факта, что `Ref_Key` и `DataVersion`.
          (c.kind = 'num'
           AND list_position((SELECT key_cols FROM kc), u.col) IS NULL
           AND u.col NOT IN ('LineNumber', 'SurrogateKey')) AS is_measure,
          -- ВСЕ даты строки, а не только выбранная. Прежде дата, не ставшая `doc_date`,
          -- не попадала НИКУДА: ни в текст, ни в величины. [замер 28.07] так пропадали
          -- 83 колонки и 30 909 значений, а у 24 сущностей не оставалось ни одной даты
          -- вовсе — «когда открыт счёт», «до какого числа действует договор», «дата
          -- регистрации контрагента» отвечать было нечем. `doc_date` по-прежнему одна:
          -- она про фильтр по периоду, а текст — про то, что человек может спросить.
          (c.kind = 'date') AS is_date,
          (SELECT 1 FROM tmp3_datecol   d WHERE d.tbl=$1 AND d.col=u.col) AS is_dt
   FROM cells u JOIN tmp3_cls c ON c.tbl=$1 AND c.col=u.col
   -- 🔴 СОЕДИНЯЕМСЯ ТОЛЬКО С GUID-ОБРАЗНЫМИ ЗНАЧЕНИЯМИ. Прежде ключом соединения было
   -- ЛЮБОЕ значение ячейки. Два следствия, оба плохие:
   --   1) движок хеширует все ячейки подряд (миллионы) против 39 тыс. записей карты —
   --      лишняя работа на каждой сущности;
   --   2) 🔴 значение с БИТОЙ КОДИРОВКОЙ роняет соединение целиком:
   --      `Invalid unicode (byte sequence mismatch) detected in value construction`.
   --      [замер 28.07, вторая база] на `catalog_правилаинтеграциис1сдокументооборотом`
   --      это убивало сборку ВСЕЙ сущности, а с `ON_ERROR_STOP on` — и весь такт.
   --      Проверено: исходное значение соединяется, а после нашей же обрезки
   --      `substr(…,1,20000)` — падает. То есть дефект наш, а не данных: на первой базе
   --      он просто не стрелял, потому что там не было таких значений.
   -- GUID по определению ASCII, поэтому битые байты до хеша не доходят вовсе.
   -- Ссылкой может быть ТОЛЬКО GUID — значит сужение не теряет ни одной связи.
   LEFT JOIN tmp3_refmap r
          ON r.guid = CASE WHEN regexp_full_match(u.val,
               '[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}')
             THEN u.val END
   -- 🔴 У ССЫЛОЧНОГО ОБЪЕКТА ПОЛЯ ВЛОЖЕННОГО ТИПА В ТЕКСТ НЕ ИДУТ.
   -- Вложенная табличная часть разворачивается загрузчиком в ту же таблицу, и её колонки
   -- (`LineNumber`, номенклатура, количество…) попадали в текст объекта, размножая строки:
   -- [замер 29.07] партнёров 216 строк на 164 объекта, раздуто 85 сущностей / 9 155 строк.
   -- Бот отвечал «216 партнёров» вместо 164, и гейт это пропускал: 216 действительно
   -- посчитано базой — посчитано не то.
   -- Эти колонки НЕ теряются: табличная часть — отдельная сущность 1С, она загружена и в
   -- корпусе есть у всех затронутых родителей (проверено).
   -- Признак `own_prop` считается один раз в `tmp3_cls`; ключевые колонки не отбрасываются
   -- никогда — иначе рассыпется тождество строки.
   -- У обёрток наборов записей (регистры, ключ ≠ `['Ref_Key']`) поведение прежнее: там
   -- вложенные строки и есть данные, [замер] сворачивание занизило бы число проводок вдвое.
   -- 🔴 ВЫБРАСЫВАЕМ ТОЛЬКО ТО, ЧТО ЕСТЬ ГДЕ ВЗЯТЬ. Колонки вложенного типа убираются из
   -- текста объекта лишь при условии, что сама вложенная сущность ЗАГРУЖЕНА и есть в
   -- источниках. Иначе это не перенос, а потеря.
   -- [замер 30.07] на второй базе дочерняя есть у всех затронутых — и я этого условия не
   -- увидел. На ПЕРВОЙ базе из 41 затронутой сущности у **25 дочерней нет вовсе**: без
   -- условия их колонки исчезли бы из текста, а взять их было бы негде.
   -- Одна база снова умолчала о случае, которого в ней нет.
   -- `coalesce(own_prop, true)` — БЕЗОПАСНОЕ НАПРАВЛЕНИЕ. `own_prop` считается через
   -- LEFT JOIN, и у колонки, которую не объявлял НИКТО, он NULL. Без `coalesce` всё
   -- выражение давало NULL, и `WHERE` выбрасывал ячейку — то есть терялось ровно то, про
   -- что неизвестно, где его взять. Считаем такую колонку своей: лишний текст дешевле
   -- потери.
   WHERE u.val <> ''
     AND NOT (coalesce(c.own_ref, false) AND NOT coalesce(c.own_prop, true)
              AND list_position((SELECT key_cols FROM kc), u.col) IS NULL
              AND (SELECT on_ FROM fold)
              -- Проверяем ИМЕННО ту сущность, что объявила колонку.
              AND EXISTS (SELECT 1 FROM tmp3_src s2 WHERE lower(s2.tbl) = c.decl_entity))),
 pieces AS (
   SELECT rid, ord, keypos, val, is_guid, refname, refowner, own_ref, col, is_num, is_measure, is_flag, is_dt, is_date,
     CASE WHEN is_guid AND col='Ref_Key' AND own_ref THEN NULL
          WHEN is_guid AND refname IS NOT NULL THEN replace(col,'_Key','') || ': ' || refname
          WHEN is_guid THEN NULL
          WHEN is_num AND try_cast(val AS DOUBLE) IS NOT NULL THEN col || ': ' ||
               CASE WHEN try_cast(val AS DOUBLE) = floor(try_cast(val AS DOUBLE))
                    THEN printf('%d', try_cast(val AS BIGINT))
                    ELSE printf('%.2f', try_cast(val AS DOUBLE)) END
          -- Незаполненная дата приезжает из 1С как `0001-01-01` — это НЕ дата, а пустое
          -- место, и в тексте ему делать нечего.
          WHEN is_date THEN nullif(col || ': ' || substr(val,1,10), col || ': 0001-01-01')
          WHEN in_text THEN col || ': ' || val
          ELSE NULL END AS piece,
     CASE WHEN is_guid THEN 0 WHEN is_num THEN 2 WHEN is_date THEN 3 ELSE 1 END AS prio
   FROM j)
-- 🔴 ДВА УРОВНЯ, А НЕ ОДИН. `QUALIFY` не может ссылаться на ключ, который сам считается
-- оконной функцией: движок отвечает `window function calls cannot be nested`. Ключ
-- строится на внутреннем уровне, выбор одной строки на объект — на внешнем.
-- 🔴 ДАЖЕ С ОТПЕЧАТКОМ ТЕКСТА КЛЮЧ МОЖЕТ ПОВТОРИТЬСЯ: у развёрнутых строк одного
-- регистратора текст бывает одинаков целиком (две одинаковые строки табличной части —
-- в 1С их различает LineNumber, а у текста различия нет). [замер 15.08, okna-1] после
-- починки дедупа приёмника (строки табчастей доезжают все) слияние остановила защита:
-- 17 269 дублей ключа в tmp3_corpus. Схлопывать такие строки нельзя (п. 13): это
-- разные движения, и в суммах нужны обе. Ключ дополняется порядковым номером по
-- полному детерминированному порядку — набор ключей стабилен между тактами, пока
-- стабильны данные, и обе строки остаются в корпусе.
SELECT src_table,
       CASE WHEN count(*) OVER (PARTITION BY src_table, row_key) > 1
            THEN row_key || '#' || row_number() OVER (PARTITION BY src_table, row_key
                                                      ORDER BY doc, refs, refs_map::VARCHAR,
                                                               nums::VARCHAR, flags::VARCHAR, dt)
            ELSE row_key END AS row_key,
       doc, refs, doc_hash, nums, flags, dt, refs_map, refs_own
FROM (
SELECT src_table, row_key, doc, refs, doc_hash, nums, flags, dt, refs_map, refs_own FROM (
SELECT src_table,
       -- 🔴 ОБЪЯВЛЕННЫЙ КЛЮЧ НЕ ВСЕГДА РАЗЛИЧАЕТ СТРОКИ. У регистров 1С отдаёт данные
       -- обёрткой (одна запись на регистратор, движения внутри списком), и объявленный
       -- ключ принадлежит ОБЁРТКЕ: [замер 28.07] `AccountingRegister_Хозрасчетный` —
       -- 280 движений схлопывались в 104 ключа, 66 ключей повторялись. Слияние в корпус
       -- на этом останавливалось, и правильно: дубль ключа в корпусе — двойной счёт в
       -- любой сумме, и уйти оттуда он уже не может.
       -- Ключ дополняется отпечатком строки ТОЛЬКО там, где он повторяется: где ключ
       -- различает — он остаётся прежним, и отпечатки строк не меняются впустую.
       -- 🔴 У ССЫЛОЧНОГО ОБЪЕКТА ОТПЕЧАТОК К КЛЮЧУ НЕ ДОПИСЫВАЕТСЯ: строка корпуса
       -- обязана быть ОДНА на объект. После отбрасывания колонок вложенного типа строки
       -- одного объекта дают одинаковый текст, и `QUALIFY` ниже оставляет одну.
       CASE WHEN NOT (SELECT on_ FROM fold)
             AND count(*) OVER (PARTITION BY src_table, rk) > 1
            THEN rk || '#' || sha1(doc) ELSE rk END AS row_key,
       doc, refs, sha1(doc || chr(0) || refs) AS doc_hash, nums, flags, dt, refs_map, refs_own
FROM (
SELECT src_table,
       -- Без объявленного ключа и без Ref_Key ключом становится отпечаток текста —
       -- как в боевом коде, иначе строки с пустым ключом затирают друг друга.
       coalesce(row_key, sha1(doc)) AS rk,
       doc, refs, nums, flags, dt, refs_map, refs_own
FROM (
  SELECT $1::VARCHAR AS src_table,
         coalesce(any_value(k.row_key),
                  max(val) FILTER (is_guid AND col='Ref_Key' AND own_ref)) AS row_key,
         regexp_replace($1,'^[^_]*_','') || coalesce(' | ' || string_agg(piece,' | ' ORDER BY prio, ord)
                                                     FILTER (piece IS NOT NULL), '') AS doc,
         coalesce(string_agg(piece,' | ' ORDER BY ord) FILTER (is_guid AND refname IS NOT NULL), '') AS refs,
         -- ВСЕ величины строки, а не одна выбранная. Имя величины — имя колонки из
         -- базы, а не наше слово: на другой конфигурации и языке это работает так же.
         -- ПОРЯДОК КЛЮЧЕЙ ЗАДАЁТСЯ ЯВНО. Сравнение `MAP` в движке зависит от порядка:
         -- [замер] `MAP{'a':1,'b':2} IS DISTINCT FROM MAP{'b':2,'a':1}` -> true. Без
         -- `ORDER BY` порядок определяется ходом агрегации и при параллельном исполнении
         -- не гарантирован — тогда `nums` переписывались бы каждый такт у всех строк,
         -- а число «сколько изменилось» переставало бы что-либо значить.
         map_from_entries(list({'key': col, 'value': try_cast(val AS DOUBLE)} ORDER BY col)
                          FILTER (is_measure AND try_cast(val AS DOUBLE) IS NOT NULL)) AS nums,
         -- Карта булевых реквизитов. `try_cast(... AS BOOLEAN)` — штатное приведение,
         -- круг замкнут на всех формах, которые отдаёт OData: 'true'/'True'/'1'/'t' -> t,
         -- мусор и пустая строка -> NULL, то есть в карту не попадают.
         -- `coalesce` до пустой карты обязателен: пустая агрегация даёт NULL, а не пустой
         -- MAP, и тогда сущности без единого булева реквизита отличались бы от прочих.
         -- Семантика отбора трёхзначная и это важно: «реквизита нет» = «не папка».
         coalesce(map_from_entries(list({'key': col, 'value': try_cast(val AS BOOLEAN)} ORDER BY col)
                          FILTER (is_flag AND try_cast(val AS BOOLEAN) IS NOT NULL)),
                  MAP{}::MAP(VARCHAR, BOOLEAN)) AS flags,
         -- Карта ссылок — как nums: колонка → имя (GUID, если имени нет). Ref_Key
         -- табличной части — это parent-зерно, в ось группы не входит. ORDER BY col —
         -- иначе MAP «меняется» каждый такт (как у nums).
         coalesce(map_from_entries(list({'key': replace(col,'_Key',''),
                                         'value': coalesce(refname, val)} ORDER BY col)
                          FILTER (is_guid AND col <> 'Ref_Key'
                                  AND coalesce(val,'') <> ''
                                  AND val <> '00000000-0000-0000-0000-000000000000')),
                  MAP{}::MAP(VARCHAR, VARCHAR)) AS refs_map,
         -- Чей GUID: для search_refcols.target_src. В боевой корпус не уходит.
         coalesce(map_from_entries(list({'key': replace(col,'_Key',''),
                                         'value': refowner} ORDER BY col)
                          FILTER (is_guid AND col <> 'Ref_Key'
                                  AND refowner IS NOT NULL AND refowner <> '')),
                  MAP{}::MAP(VARCHAR, VARCHAR)) AS refs_own,
         -- [замер 28.07] 312 строк корпуса имели `doc_date = 0001-01-01`: незаполненная
         -- дата 1С — валидный TIMESTAMP, и `try_cast` её принимал. «Самый ранний
         -- документ» отвечал первым годом нашей эры, а «даты нет» было неотличимо от
         -- даты. Отсутствие обязано выглядеть как отсутствие.
         max(nullif(try_cast(val AS TIMESTAMP), TIMESTAMP '0001-01-01 00:00:00'))
             FILTER (is_dt IS NOT NULL) AS dt
  FROM pieces LEFT JOIN keyed k USING (rid) GROUP BY rid) g) h) q
-- 🔴 ОДНА СТРОКА НА ОБЪЕКТ — только для ссылочных объектов. Порядок ПОЛНЫЙ: если два
-- представителя различаются, выбор обязан быть один и тот же при любом порядке чтения
-- (`techContext` ловушки 29, 30). Расхождение текстов внутри объекта после починки
-- загрузчика означать нечего не должно — это проверяется отдельным числом в отчёте.
QUALIFY NOT (SELECT on_ FROM fold)
     OR row_number() OVER (PARTITION BY src_table, row_key
          ORDER BY doc, refs, doc_hash) = 1) qq;

-- ============ 6-бис. УПРОЩЁННЫЙ ВАРИАНТ СБОРКИ (запасной) ============
-- 🔴 ОДНА СУЩНОСТЬ НЕ ДОЛЖНА УБИВАТЬ ВЕСЬ ТАКТ. Полная сборка делает много тонкого:
-- разрешает ссылки по карте, собирает карту величин, выбирает дату. Любой из этих шагов
-- может споткнуться о данные, которых мы не предвидели — [замер 28.07, вторая база]
-- значение с битой кодировкой роняло соединение с картой ссылок, а с `ON_ERROR_STOP on`
-- вместе с ним падал ВЕСЬ такт: 1 500 здоровых сущностей не доезжали из-за одной.
--
-- Решение (указание владельца 28.07): не падать, а пробовать ДРУГОЙ подготовленный
-- вариант. Этот — намеренно простой: текст из пар «колонка: значение», ключ из
-- объявленного ключа или отпечатка. Ни ссылок, ни величин, ни дат — только то, без чего
-- строка вообще не найдётся. Качество ниже, но сущность остаётся в поиске.
--
-- 🔴 Деградация НЕ МОЛЧАЛИВАЯ (п. 13): ниже считается, сколько сущностей собрано
-- упрощённо и сколько не собралось вовсе, и оба числа уходят в отчёт.
PREPARE p_doc_plain AS
INSERT INTO tmp3_corpus
WITH kc AS (SELECT key_cols FROM tmp3_key WHERE entity = lower($1)),
 src AS (SELECT row_number() OVER () AS rid,
                substr(coalesce(COLUMNS(*)::VARCHAR, ''), 1, 20000) FROM query_table($1)),
 cells AS (SELECT * FROM src UNPIVOT (val FOR col IN (COLUMNS(* EXCLUDE (rid))))),
 keyed AS (SELECT u.rid, string_agg(u.val, '|' ORDER BY list_position((SELECT key_cols FROM kc), u.col)) AS rk
           FROM cells u WHERE list_position((SELECT key_cols FROM kc), u.col) IS NOT NULL
           GROUP BY u.rid),
 g AS (SELECT c.rid,
              regexp_replace($1,'^[^_]*_','') || coalesce(' | ' || string_agg(c.col || ': ' || c.val, ' | '), '') AS doc
       FROM cells c WHERE c.val <> '' GROUP BY c.rid)
-- Порядок колонок позиционный: src_table, row_key, doc, refs, doc_hash, nums, flags,
-- doc_date, refs_map, refs_own. У упрощённого пути ни величин, ни булевых реквизитов, ни дат,
-- ни карты ссылок нет — и это честный NULL «не разбирали», а не пустая карта.
SELECT $1::VARCHAR, coalesce(k.rk, sha1(g.doc)), g.doc, '', sha1(g.doc),
       NULL, NULL, NULL, NULL, NULL
FROM g LEFT JOIN keyed k USING (rid);

-- Первый заход: полная сборка. Ошибка ОДНОЙ сущности здесь не останавливает файл —
-- останов включён обратно сразу после цикла, чтобы настоящие сбои (метаданные, права)
-- по-прежнему роняли такт.
\set ON_ERROR_STOP off
-- 🔴 ИДЁМ ПО `tmp3_build`, А НЕ ПО `tmp3_src`: перечитывается только изменившееся и то,
-- у чего поменялось имя ссылки. Слияние к частичному набору готово по построению — оно
-- удаляет строки только у сущностей, которые в этот раз собрались (`corpus_merge.sql`).
SELECT 'EXECUTE p_doc(' || quote_literal(tbl) || ');' FROM tmp3_build
\gexec
\set ON_ERROR_STOP on

-- Второй заход: то, что не собралось, — упрощённым вариантом.
\set ON_ERROR_STOP off
SELECT 'EXECUTE p_doc_plain(' || quote_literal(tbl) || ');'
FROM tmp3_build s
WHERE NOT EXISTS (SELECT 1 FROM tmp3_corpus t WHERE t.src_table = s.tbl)
\gexec
\set ON_ERROR_STOP on

-- Чем кончился перебор — ЧИСЛАМИ В БАЗУ, а не в поток. Считается по тому, что СОБИРАЛИ:
-- иначе при частичной сборке все непересобиравшиеся сущности выглядели бы упавшими.
DELETE FROM search_quality WHERE k IN ('build_degraded', 'build_failed');
INSERT INTO search_quality
SELECT 'build_failed', count(*), 'сущностей не собралось ни одним вариантом'
FROM tmp3_build s WHERE NOT EXISTS (SELECT 1 FROM tmp3_corpus t WHERE t.src_table = s.tbl);

SELECT 'сборка сущностей' AS шаг,
       (SELECT count(*) FROM tmp3_build) AS пересобирали,
       (SELECT count(*) FROM tmp3_src) AS всего_источников,
       (SELECT count(DISTINCT src_table) FROM tmp3_corpus) AS собрано,
       (SELECT v FROM search_quality WHERE k = 'build_failed') AS не_собралось;

-- ============ 6-тер. СПРАВОЧНИК ОСЕЙ ГРУППЫ ============
-- src_table, col, target_src. Цель — owner GUID из search_refmap. Пустая или
-- неоднозначная цель в таблицу не кладётся (п. 13 — счётчиком).
CREATE TABLE IF NOT EXISTS search_refcols (
  src_table VARCHAR, col VARCHAR, target_src VARCHAR);
GRANT SELECT ON search_refcols TO serene_ro;

DELETE FROM search_refcols
WHERE src_table IN (SELECT DISTINCT src_table FROM tmp3_corpus);

CREATE OR REPLACE TABLE tmp3_refcol_hits AS
SELECT src_table,
       unnest(map_keys(refs_own)) AS col,
       unnest(map_values(refs_own)) AS target_src
FROM tmp3_corpus
WHERE refs_own IS NOT NULL AND len(map_keys(refs_own)) > 0;

INSERT INTO search_refcols
SELECT src_table, col, min(target_src)
FROM tmp3_refcol_hits
WHERE target_src IS NOT NULL AND target_src <> ''
  AND EXISTS (SELECT 1 FROM search_tables s WHERE s.src_table = tmp3_refcol_hits.target_src)
GROUP BY src_table, col
HAVING count(DISTINCT target_src) = 1;

DELETE FROM search_quality WHERE k = 'refcols_empty_target';
INSERT INTO search_quality
SELECT 'refcols_empty_target', count(*),
       'осей ссылок без однозначной цели — в search_refcols не кладём'
FROM (
  SELECT DISTINCT src_table, unnest(map_keys(refs_map)) AS col
  FROM tmp3_corpus
  WHERE refs_map IS NOT NULL AND len(map_keys(refs_map)) > 0
  EXCEPT
  SELECT src_table, col FROM search_refcols
) z;

SELECT 'оси группы' AS шаг,
       (SELECT count(*) FROM search_refcols) AS осей,
       (SELECT coalesce(v,0) FROM search_quality WHERE k = 'refcols_empty_target') AS без_цели;

-- ============ 7. СВЕРКА С БОЕВЫМ КОРПУСОМ ============
SELECT 'строк: новая формула' AS что, count(*) AS сколько FROM tmp3_corpus
UNION ALL SELECT 'строк: боевой корпус', count(*) FROM search_corpus;

-- Сверка с боевым: отпечаток и дата сравниваются напрямую, величины — по существу.
-- Прежняя колонка `amount` несла ОДНУ величину, выбранную моделью; теперь строка несёт
-- их все, поэтому сравнивается не «равен ли amount», а «есть ли прежняя величина среди
-- нынешних»: сужение считалось бы потерей, а расширение — нет.
SELECT count(*) AS сошлось_ключами,
       count(*) FILTER (WHERE c.doc_hash = t.doc_hash) AS отпечаток_совпал,
       count(*) FILTER (WHERE c.doc_hash <> t.doc_hash) AS отпечаток_разошёлся,
       count(*) FILTER (WHERE c.doc_date IS DISTINCT FROM t.doc_date) AS doc_date_разошёлся,
       count(*) FILTER (WHERE c.nums IS NOT NULL AND len(map_keys(c.nums)) > 0
                          AND NOT (t.nums IS NOT NULL AND len(map_keys(t.nums)) > 0)) AS величины_пропали
FROM search_corpus c JOIN tmp3_corpus t USING (src_table, row_key);

-- 🔴 `coalesce` здесь не украшение. [замер] `map_from_entries` над списком, из которого
-- фильтр выбросил всё, даёт NULL, а не пустую карту; `len(map_keys(NULL))` — тоже NULL,
-- и условие `= 0` не срабатывает НИКОГДА. Отчёт печатал «строк без величин: 0», когда их
-- было 66 746 из 97 965, а среднее считалось по трети строк и было завышено втрое.
-- Число, которое структурно не может показать потерю, хуже отсутствующего.
SELECT 'величин в строке' AS что,
       round(avg(coalesce(len(map_keys(nums)), 0)), 1) AS в_среднем,
       max(coalesce(len(map_keys(nums)), 0)) AS максимум,
       count(*) FILTER (WHERE nums IS NULL OR len(map_keys(nums)) = 0) AS строк_без_величин
FROM tmp3_corpus;

-- 🔴 СРАВНИВАЕМ ТОЛЬКО ТО, ЧТО ПЕРЕСОБИРАЛИ. При частичной сборке `tmp3_corpus` содержит
-- лишь изменившиеся сущности, и без этого условия «нет в новой» показывало бы весь
-- остальной корпус как пропавший — число, которое пугает и ничего не значит.
SELECT 'нет в новой' AS сторона, count(*) FROM search_corpus c
  WHERE c.src_table IN (SELECT tbl FROM tmp3_build)
    AND NOT EXISTS (SELECT 1 FROM tmp3_corpus t WHERE t.src_table=c.src_table AND t.row_key=c.row_key)
UNION ALL
SELECT 'нет в боевой', count(*) FROM tmp3_corpus t
  WHERE NOT EXISTS (SELECT 1 FROM search_corpus c WHERE c.src_table=t.src_table AND c.row_key=t.row_key);

-- ============ 8. ОТЧЁТ О КАЧЕСТВЕ КАРТЫ ИМЁН ============
-- П. 13 TARGET.md: то, что данные где-то потеряли качество, обязано быть ВИДНО, а не
-- зависеть от того, догадался ли человек посмотреть. Три числа считаются на любой базе
-- без единой настройки и без просмотра глазами (проверка «посмотреть выборку» не
-- универсальна: её нельзя ни повторить у клиента, ни выразить замером).
CREATE TABLE IF NOT EXISTS search_quality (k VARCHAR, v BIGINT, note VARCHAR);
DELETE FROM search_quality WHERE k LIKE 'refmap_%';
INSERT INTO search_quality
SELECT 'refmap_resolved', count(*), 'ссылок получили человеческое имя' FROM tmp3_refmap
UNION ALL
-- 🔴 Сколько идентификаторов пришли с НЕСКОЛЬКИМИ именами. Пока это число не равно нулю,
-- имя выбирается правилом, а не данными, — и человек должен об этом знать. Именно эта
-- неоднозначность [замер 29.07] делала корпус невоспроизводимым: 64 107 строк меняли
-- ключ при пересборке тех же данных.
SELECT 'refmap_ambiguous_guid', count(*), 'идентификаторов с несколькими именами — имя выбрано правилом'
FROM (SELECT guid FROM tmp3_refmap_raw GROUP BY guid HAVING count(DISTINCT name) > 1)
UNION ALL
-- 🔴 СКОЛЬКО КОЛОНОК ОСТАВЛЕНО, ПОТОМУ ЧТО ОБЪЯВИВШЕЙ ИХ ВЛОЖЕННОЙ СУЩНОСТИ НЕТ В
-- ИСТОЧНИКАХ. Колонка вложенного типа выбрасывается из текста объекта только тогда, когда
-- то же самое есть где взять — у самой вложенной сущности. Если она не загрузилась (отказ
-- 1С, `Edm.Stream`, права), колонки ОСТАЮТСЯ: иначе это прямая потеря.
-- Число ненулевое означает: у стольких колонок текст объекта несёт значения строк, и
-- ответ на вопрос «сколько всего» по ним может быть завышен. Молчать об этом нельзя (п. 13).
SELECT 'fold_kept_no_child', count(*),
       'колонок вложенного типа оставлено в тексте: объявившая их сущность не загрузилась'
FROM tmp3_cls c
WHERE coalesce(c.own_ref, false) AND NOT coalesce(c.own_prop, true)
  AND EXISTS (SELECT 1 FROM tmp3_key k
              WHERE k.entity = lower(c.tbl) AND k.key_cols = ['Ref_Key'])
  AND NOT EXISTS (SELECT 1 FROM tmp3_src s WHERE lower(s.tbl) = c.decl_entity)
UNION ALL
-- Считается по СОБРАННОМУ, а не по боевому корпусу. Прежде это число бралось из
-- `search_corpus`, то есть из корпуса ПРЕДЫДУЩЕГО такта (файл выполняется до слияния):
-- рядом стояли два числа из разных эпох и выглядели как одно измерение.
SELECT 'refmap_unresolved', count(*), 'GUID в тексте без имени в карте'
FROM (SELECT DISTINCT val FROM (
        SELECT unnest(regexp_extract_all(doc,'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}')) val
        FROM tmp3_corpus)
      WHERE val NOT IN (SELECT guid FROM tmp3_refmap))
UNION ALL
SELECT 'refmap_ambiguous', count(*), 'имён, которые делят между собой разные объекты'
FROM (SELECT name FROM tmp3_refmap GROUP BY name HAVING count(*) > 1)
UNION ALL
-- Обрезка длинного значения (20 000 символов) была решением в комментарии и нигде не
-- считалась. П. 13: обрезал — покажи это числом, а не строкой в исходнике.
SELECT 'clipped_docs', count(*), 'строк, где значение обрезано по длине'
FROM tmp3_corpus WHERE length(doc) >= 20000;

SELECT k, v, note FROM search_quality WHERE k LIKE 'refmap_%' OR k = 'clipped_docs' ORDER BY k;

-- ============ 9. ОТМЕТКА ПРОГОНА ============
-- Ставится САМОЙ ПОСЛЕДНЕЙ командой: её наличие доказывает, что сборка дошла до конца,
-- а не оборвалась на середине. `corpus_merge.sql` откажется переносить данные, если
-- отметки нет или она старая — иначе он молча перенесёт вчерашние временные таблицы
-- (они обычные, а не временные, и переживают сессию и рестарт движка).
CREATE OR REPLACE TABLE tmp3_run AS SELECT now() AS ts, count(*) AS собрано FROM tmp3_corpus;
SELECT 'сборка завершена' AS шаг, собрано, ts FROM tmp3_run;
