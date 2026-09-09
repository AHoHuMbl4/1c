\timing on
\set ON_ERROR_STOP on

-- 🔴 partial_rebuild=0 — константа пакета B0 (=1 только с row-level p_doc, отдельный пакет).
-- Merge работает прежним режимом; search_changed_rows копится, удаления по списку — будущая B.
\set partial_rebuild 0

-- Session memory_limit: 0.55 от current_setting (cookbook/performance/oom, 50-60%).
-- 🔴 В SereneDB у memory_limit ТОЛЬКО GLOBAL scope («option cannot be set
-- locally», доки Sql › Statements › SET/RESET › Scopes): этот SET ужимает
-- память ВСЕГО движка, а не одной сессии. Поэтому build.sh (cleanup, trap на
-- любой исход) восстанавливает исходное значение ПОСЛЕ такта; без этого
-- каждый следующий такт считал 0.55 от уже ужатого — каскад 94.9→…→2 GiB
-- ронял merge на OOM (замер okna 08.09, такт №10).
-- Единица строки — та же, что вернул current_setting; без литералов и без ОС.
SELECT (
  WITH ml AS (SELECT current_setting('memory_limit') AS s),
  parsed AS (
    SELECT s,
           lower(trim(regexp_replace(s, '^[0-9.]+\s*', ''))) AS unit_l,
           try_cast(regexp_extract(s, '^([0-9.]+)', 1) AS DOUBLE) AS n
    FROM ml
  ),
  bytes AS (
    SELECT s, unit_l, n,
           CASE
             WHEN unit_l NOT IN ('', 'b', 'kb', 'mb', 'gb', 'kib', 'mib', 'gib')
               THEN error('corpus_merge: неизвестная единица memory_limit: ' || s)
             WHEN unit_l IN ('gib') THEN n * power(1024::BIGINT, 3)
             WHEN unit_l IN ('mib') THEN n * power(1024::BIGINT, 2)
             WHEN unit_l IN ('kib') THEN n * 1024
             WHEN unit_l IN ('gb')  THEN n * power(1000::BIGINT, 3)
             WHEN unit_l IN ('mb')  THEN n * power(1000::BIGINT, 2)
             WHEN unit_l IN ('kb')  THEN n * 1000
             ELSE n  -- '' / 'b' = байты
           END AS mem_bytes,
           CASE
             WHEN unit_l IN ('gib') THEN power(1024::BIGINT, 3)
             WHEN unit_l IN ('mib') THEN power(1024::BIGINT, 2)
             WHEN unit_l IN ('kib') THEN 1024
             WHEN unit_l IN ('gb')  THEN power(1000::BIGINT, 3)
             WHEN unit_l IN ('mb')  THEN power(1000::BIGINT, 2)
             WHEN unit_l IN ('kb')  THEN 1000
             ELSE 1  -- '' / 'b'
           END AS div,
           CASE
             WHEN unit_l IN ('gib') THEN 'GiB'
             WHEN unit_l IN ('mib') THEN 'MiB'
             WHEN unit_l IN ('kib') THEN 'KiB'
             WHEN unit_l IN ('gb')  THEN 'GB'
             WHEN unit_l IN ('mb')  THEN 'MB'
             WHEN unit_l IN ('kb')  THEN 'KB'
             ELSE 'B'  -- '' / 'b'
           END AS unit
    FROM parsed
  )
  SELECT (floor(mem_bytes * 0.55 / div))::BIGINT::VARCHAR
         || CASE WHEN position(' ' in s) > 0 THEN ' ' ELSE '' END
         || unit
  FROM bytes
) AS ml
\gset
SET memory_limit = :'ml';

-- ПЕРЕНОС СОБРАННОГО КОРПУСА В БОЕВОЙ И ПУБЛИКАЦИЯ ПОИСКУ.
-- Запускается после `corpus_build.sql` — он строит `tmp3_corpus` и ставит отметку `tmp3_run`.
--
-- 🔴 Это САМЫЙ ОПАСНЫЙ файл проекта: он пишет в боевой корпус и удаляет из него. Поэтому
-- всё, что может испортить данные, закрыто ПРОВЕРКОЙ ДО ЗАПИСИ, а сама запись идёт одной
-- транзакцией. Проверки написаны через `error()` — штатную функцию движка: она даёт
-- настоящую ошибку и ненулевой код возврата, который видит вызывающий. Печатать
-- предупреждение и продолжать нельзя — так данные уже терялись молча.

-- ============ 0. ПРОВЕРКИ ДО ЗАПИСИ ============

-- Свежесть временных таблиц. Они ОБЫЧНЫЕ, а не временные: переживают сессию и рестарт
-- движка. Без проверки запуск в одиночку перенёс бы вчерашнюю сборку и снёс всё, чего
-- в ней нет. Отметка ставится последней командой сборки — значит она же доказывает,
-- что сборка дошла до конца, а не оборвалась.
--
-- Первая сборка / merge-only: корпус пуст ИЛИ перенос оборвался на пачках
-- (`search_corpus` < `tmp3_corpus`), стейдж совпал со штампом, штамп моложе 48 ч —
-- слияние после падения (диск ENOSPC, checkpoint) можно догнать без пересборки.
-- [замер 18.08 klient-1] после 8/17 пачек `search_corpus`=8M — прежнее «только
-- при count=0» блокировало догон через 6 ч. Инкремент с полным корпусом — 6 часов:
-- иначе вчерашний tmp3 затёр бы бой.
SELECT CASE WHEN coalesce((SELECT max(ts) FROM tmp3_run), TIMESTAMP '1970-01-01')
                 < now() - INTERVAL '6 hours'
            AND NOT (
                 (
                     (SELECT count(*) FROM search_corpus) = 0
                  OR (SELECT count(*) FROM search_corpus)
                       < (SELECT count(*) FROM tmp3_corpus)
                 )
             AND (SELECT собрано FROM tmp3_run) = (SELECT count(*) FROM tmp3_corpus)
             AND (SELECT собрано FROM tmp3_run) > 0
             AND coalesce((SELECT max(ts) FROM tmp3_run), TIMESTAMP '1970-01-01')
                 >= now() - INTERVAL '48 hours'
            )
       THEN error('corpus_merge: tmp3_* не от этого прогона — сначала corpus_build.sql') END;

-- Сущность собралась ПУСТОЙ — главный сценарий тихой потери: витрина не долилась, шлюз
-- отдал урезанные метаданные, сборка сущности упала. Её живые строки ушли бы в `DELETE`
-- без единого слова. Лучше отказаться от переноса целиком.
--
-- 🔴 СПРАШИВАЕМ С ТЕХ, КОГО СОБИРАЛИ (`tmp3_build`), А НЕ СО ВСЕХ ИСТОЧНИКОВ. С 06.08
-- сборка идёт по изменившемуся, и `tmp3_corpus` законно содержит только их. Пока условие
-- смотрело в `tmp3_src`, каждая НЕ пересобиравшаяся сущность выглядела «собравшейся
-- пустой», и защита останавливала такт — [замер 06.08] так и вышло на первом же прогоне
-- по-изменившемуся: перенос отменён, перечислены сотни сущностей. Данные при этом целы —
-- защита сработала верно, неверен был её вопрос.
--
-- `tmp3_build` создаёт сама сборка. Если его нет — значит слияние зовут от сборки старее
-- этой правки, и запрос упадёт с «нет такой таблицы». Это правильный исход: молча слить
-- частичный набор по правилам, которых та сборка не знала, было бы хуже. Отдельную защиту
-- от такого запуска держит проверка свежести `tmp3_run` выше.
SELECT CASE WHEN count(*) > 0
       THEN error('corpus_merge: сущности собрались пустыми, перенос отменён: '
                  || string_agg(tbl, ', ')) END
FROM (SELECT s.tbl FROM tmp3_build s
      WHERE NOT EXISTS (SELECT 1 FROM tmp3_corpus t WHERE t.src_table = s.tbl));

-- Дубли ключа в источнике. [замер] движок на дубль в `MERGE` не ругается: одно совпадение
-- берёт, второе игнорирует, а несовпавшие дубли вставляет оба. Ограничения уникальности
-- на корпусе нет, и попавший дубль оттуда уже не уйдёт.
SELECT CASE WHEN count(*) > 0
       THEN error('corpus_merge: в tmp3_corpus дублей ключа: ' || count(*)) END
FROM (SELECT src_table, row_key FROM tmp3_corpus GROUP BY 1, 2 HAVING count(*) > 1);

-- Масштаб удаления. Если перенос снёс бы больше десятой части корпуса — это не
-- обновление, а авария на стороне источника. Доля, а не число: она не зависит от базы.
--
-- 🔴 СЧИТАЕМ ПОТЕРЮ ОБЪЕКТОВ, А НЕ ИСЧЕЗНОВЕНИЕ КЛЮЧЕЙ. Строка может уйти под старым
-- ключом и остаться в корпусе под новым — тогда данные целы, а защита видела бы аварию.
-- Такое бывает не только при правке кода: пока объект развёрнут по строкам, ключ несёт
-- отпечаток текста (`<объект>#<sha1 текста>`), и правка одной строки табличной части
-- меняет ключ, не меняя объекта. [замер 30.07] после починки «строка ≠ объект» по этой
-- причине сменилось 64 107 ключей — защита остановила бы законный перенос, и корпус
-- замер бы навсегда, а такт падал бы бесконечно.
--
-- Отпечаток отсекается по СВОЕМУ ЖЕ формату. Два вида суффикса после `#`:
--   1) `sha1` — ровно 40 шестнадцатеричных знаков (ключ регистра без LineNumber);
--   2) порядковый номер (`row_number`) — цифры: когда fold ещё не схлопывал
--      разворот шапки, `QUALIFY` дописывал `#1`, `#2`… к одному Ref_Key.
-- [замер 21.08 okna] `document_установкаценноменклатуры`: корпус 321 757 ключей
-- `guid#N`, стейдж 439 plain GUID; сторож видел «удаление 322 119 / 1 550 088»
-- (20 %) и крутил такт в fail-loop с 20:01 20.08. `split_part(...,'#',1)` —
-- тот же объект; DELETE ниже по exact key всё равно снимет лишние `#N`.
-- Составной ключ склеен через `|`, и в данных 1С `#` встречается — поэтому
-- режем только ХВОСТ после последнего осмысленного совпадения со стейджем,
-- а не «всё до первого `#`» вслепую.
--
-- [замер 29.08 okna] после нового $metadata форма row_key сменилась целиком
-- (guid → 40-hex хеш; регистр: guid|StandardODATA → Period|измерения) — анти-
-- соединения ниже ключи не сопоставляют. У сущности уходит 100 % её старых ключей,
-- новая сборка непуста и не меньше — пересбор, не потеря. Частичный уход (<100 %)
-- при росте сборки и живых Recorder в витрине — схлопывание гранулярности ключа
-- (два движения с одним составом измерений → один объект), не потеря. Мёртвый
-- Recorder и документ-регистратор удалён из 1С — легитимная дельта (п. 17),
-- `entity_deleted_delta`. Мёртвый Recorder, документ жив — дефект транспорта,
-- STOP. Перепроведение под другим Recorder при том же Period|оси — анти-соединение
-- ниже (только если Period в объявленном ключе). Иначе STOP.
--
-- [замер 31.08 okna] full_entity переapply 19 пакетов переписал витрину целиком:
-- row_key = sha1(doc||refs), текст строки сменился → sha другой → у ~400 тыс.
-- живых строк все 6 анти-соединений не матчят (split_part от целого sha = весь
-- sha). Построение tmp3_merge_unmatched = перебор 1,43 млн × 400 тыс. → OOM.
-- Класс «rewrite wave»: per-table, без списков — ≥90 % живых без exact-match,
-- объём стейджа ≈ живому (|Δ|/live ≤ 5 %), сборка не меньше. Для них unmatched
-- построчно не считается (уйдёт := было); MERGE+DELETE ниже заменяют таблицу.
-- Вектор принадлежит бизнес-контенту, не row_key (О4): стыковка переноса —
-- по уникальному content_hash (канон колонок doc без платформенного шума).
-- Смена формы при тех же значениях → тот же content_hash → либо MERGE не
-- трогает emb (тот же row_key), либо карта xfer возвращает emb после волны.
-- Реальное изменение значений → другой content_hash → emb=NULL, bulk досчитает.
-- Гейт вектор-бюджета (1-тер) стопит ДО записи, если потеря вне карты > доли
-- MERGE_VECTOR_LOSS_TOLERANCE (умолчание 0.5%). Доки: MERGE INTO;
-- sql/functions/map; sql/functions/text#string_split; sql/functions/utility#error;
-- sql/statements/create_macro; cookbook/sql_features/query_and_query_table_functions.
CREATE OR REPLACE TABLE tmp3_merge_ent_counts AS
SELECT e.src_table,
       coalesce(o.было, 0::BIGINT) AS было,
       e.стало,
       coalesce(m.matched_exact, 0::BIGINT) AS matched_exact
FROM (SELECT src_table, count(*)::BIGINT AS стало FROM tmp3_corpus GROUP BY 1) e
LEFT JOIN (
  SELECT src_table, count(*)::BIGINT AS было
  FROM search_corpus
  WHERE src_table IN (SELECT DISTINCT src_table FROM tmp3_corpus)
  GROUP BY 1
) o USING (src_table)
LEFT JOIN (
  SELECT c.src_table, count(*)::BIGINT AS matched_exact
  FROM search_corpus c
  INNER JOIN tmp3_corpus t
          ON t.src_table = c.src_table AND t.row_key = c.row_key
  GROUP BY 1
) m USING (src_table);

CREATE OR REPLACE TABLE tmp3_merge_rewrite_wave AS
SELECT src_table, было, стало
FROM tmp3_merge_ent_counts
WHERE было > 0 AND стало > 0 AND стало >= было
  AND (было - matched_exact)::DOUBLE / было >= 0.9
  AND abs(стало - было)::DOUBLE / было <= 0.05;

-- Правка строки при перепроведении: тот же refs (та же строка данных), новый
-- контент → новый sha-ключ. Это изменение из 1С, а не потеря: пара по refs
-- доказывает, что строка жива в новой сборке. Такие строки уходят из
-- «уйдёт» частичной потери. edited_delta считается ПОСЛЕ unmatched (ниже).

-- unmatched режется по сущностям: пустой каркас + PREPARE/EXECUTE на каждую
-- таблицу стейджа вне rewrite_wave (fail-safe NOT IN wave и в теле).
CREATE OR REPLACE TABLE tmp3_merge_unmatched AS
SELECT c.src_table, c.row_key FROM search_corpus c WHERE false;

PREPARE p_merge_unmatched AS
INSERT INTO tmp3_merge_unmatched
SELECT c.src_table, c.row_key
FROM search_corpus c
WHERE c.src_table = $1
  AND c.src_table NOT IN (SELECT src_table FROM tmp3_merge_rewrite_wave)
  -- РАЗДЕЛЬНЫЕ анти-соединения, а не одно `IN (ключ, обрезанный ключ)`:
  -- список внутри `IN` лишает движок равенства, и он уходит в перебор. [замер 30.07]
  -- одним `IN` запрос не уложился в две минуты на 623 565 строках; двумя — 0,2 с.
  AND NOT EXISTS (SELECT 1 FROM tmp3_corpus t
                  WHERE t.src_table = c.src_table AND t.row_key = c.row_key)
  AND NOT EXISTS (SELECT 1 FROM tmp3_corpus t
                  WHERE t.src_table = c.src_table
                    AND t.row_key = regexp_replace(c.row_key, '#[0-9a-f]{40}$', ''))
  AND NOT EXISTS (SELECT 1 FROM tmp3_corpus t
                  WHERE t.src_table = c.src_table
                    AND t.row_key = split_part(c.row_key, '#', 1)
                    AND position('#' in c.row_key) > 0)
  AND NOT EXISTS (SELECT 1 FROM tmp3_corpus t
                  WHERE t.src_table = c.src_table
                    AND split_part(t.row_key, '|', 1) = split_part(c.row_key, '|', 1)
                    AND split_part(c.row_key, '|', 1) <> '')
  AND NOT EXISTS (SELECT 1 FROM tmp3_corpus t
                  WHERE t.src_table = c.src_table
                    AND split_part(t.row_key, '|', 1) = split_part(c.row_key, '#', 1)
                    AND position('#' in c.row_key) > 0
                    AND split_part(c.row_key, '#', 1) <> '');

-- Перепроведение: тот же хвост ключа после Recorder (Period|измерения), другой
-- Recorder уже в tmp3 — не orphan. Только если Period в объявленном ключе:
-- для {Recorder,Recorder_Type,LineNumber} хвост = LineNumber, совпадение ложное.
--
-- 🔴 ЭТО СОЕДИНЕНИЕ ЖИВЁТ ОТДЕЛЬНЫМ PREPARE И ЗОВЁТСЯ ТОЛЬКО ДЛЯ СУЩНОСТЕЙ
-- С Period В КЛЮЧЕ. «Только если Period» прежде стоял коррелированным EXISTS
-- по tmp3_key ВНУТРИ подзапроса — и на сущностях БЕЗ Period (319 из 351) движок
-- всё равно ВЫЧИСЛЯЛ соединение: у односегментного ключа (без '|') хвост за
-- концом строки = '', равенство ''='' матчит ЛЮБУЮ пару строк той же сущности,
-- и соединение вырождалось в декартово. [замер 08.09 okna] на
-- document_установкаценноменклатуры (321 793 × 323 292, ключ {Ref_Key,LineNumber}):
-- 2-3 мин активного CPU и 241.8 GiB спилла, statement не завершался — merge
-- падал на этом месте четыре такта подряд. Вынос Period-константы из коррелята
-- НЕ лечит (AND в движке не ленив: проба с выносом — 3:27 и то же переполнение).
-- Те же пять анти-соединений без шестого: 0.4 с, unmatched 22 109 — побитово
-- тот же результат (у сущности без Period шестое условие по смыслу всегда
-- пропускало строки: NOT EXISTS с заведомо ложным EXISTS = true). Для 32
-- сущностей с Period поведение не меняется вовсе — см. p_merge_unmatched_period.
-- 🔴 p_merge_unmatched / p_merge_unmatched_period — ЗЕРКАЛА: пять общих
-- анти-соединений обязаны совпадать побуквенно (прецедент p_doc / p_doc_chunk);
-- правка одного — синхронная правка второго в том же заходе. Замок
-- test_corpus_merge_unmatched_split.py гоняет оба тела на одной фикстуре
-- и сверяет результат с эталонным монолитным SELECT.
PREPARE p_merge_unmatched_period AS
INSERT INTO tmp3_merge_unmatched
SELECT c.src_table, c.row_key
FROM search_corpus c
WHERE c.src_table = $1
  AND c.src_table NOT IN (SELECT src_table FROM tmp3_merge_rewrite_wave)
  AND NOT EXISTS (SELECT 1 FROM tmp3_corpus t
                  WHERE t.src_table = c.src_table AND t.row_key = c.row_key)
  AND NOT EXISTS (SELECT 1 FROM tmp3_corpus t
                  WHERE t.src_table = c.src_table
                    AND t.row_key = regexp_replace(c.row_key, '#[0-9a-f]{40}$', ''))
  AND NOT EXISTS (SELECT 1 FROM tmp3_corpus t
                  WHERE t.src_table = c.src_table
                    AND t.row_key = split_part(c.row_key, '#', 1)
                    AND position('#' in c.row_key) > 0)
  AND NOT EXISTS (SELECT 1 FROM tmp3_corpus t
                  WHERE t.src_table = c.src_table
                    AND split_part(t.row_key, '|', 1) = split_part(c.row_key, '|', 1)
                    AND split_part(c.row_key, '|', 1) <> '')
  AND NOT EXISTS (SELECT 1 FROM tmp3_corpus t
                  WHERE t.src_table = c.src_table
                    AND split_part(t.row_key, '|', 1) = split_part(c.row_key, '#', 1)
                    AND position('#' in c.row_key) > 0
                    AND split_part(c.row_key, '#', 1) <> '')
  AND NOT EXISTS (SELECT 1 FROM tmp3_corpus t
                  WHERE t.src_table = c.src_table
                    -- ГЕЙТ РАЗМЕРНОСТИ КЛЮЧА — ПЕРВЫМ, до дорогого равенства хвостов:
                    -- AND в движке не ленив, гейт после substr не отсекает декартово.
                    -- «Хвост после Recorder» существует только при Recorder-префиксе,
                    -- то есть при '|' в ключе ОБЕИХ сторон. Без гейта у односегментного
                    -- ключа хвост за концом строки = '' и равенство ''='' матчит ЛЮБУЮ
                    -- пару строк с разными первыми сегментами — декартово соединение и
                    -- ЛОЖНОЕ «перепроведение» (orphan зря спасается). [замер 08.09
                    -- okna] 219 994/219 994 строк Period-сущностей с '|', гейт ничего
                    -- не меняет; на базе с ключом из одного Period он обязателен.
                    AND position('|' in c.row_key) > 0
                    AND position('|' in t.row_key) > 0
                    AND substr(t.row_key, length(split_part(t.row_key, '|', 1)) + 2)
                      = substr(c.row_key, length(split_part(c.row_key, '|', 1)) + 2)
                    AND split_part(t.row_key, '|', 1) <> split_part(c.row_key, '|', 1)
                    AND split_part(c.row_key, '|', 1) <> ''
                    AND EXISTS (SELECT 1 FROM tmp3_key k
                                WHERE k.entity = lower(c.src_table)
                                  AND list_contains(k.key_cols, 'Period')));

-- Диспетчер: Period в объявленном ключе сущности (свойство СУЩНОСТИ из
-- $metadata-ключа, а не строки) выбирает полный вариант; прочие — базовый.
-- COALESCE: сущности без записи в tmp3_key — базовый (прежде внутренний EXISTS
-- был ложен, шестое условие пропускало строки — та же семантика).
SELECT DISTINCT 'EXECUTE ' ||
       CASE WHEN coalesce((SELECT list_contains(k.key_cols, 'Period')
                           FROM tmp3_key k WHERE k.entity = lower(t.src_table)), false)
            THEN 'p_merge_unmatched_period(' ELSE 'p_merge_unmatched(' END
       || quote_literal(src_table) || ');'
FROM (SELECT DISTINCT src_table FROM tmp3_corpus
      WHERE src_table NOT IN (SELECT src_table FROM tmp3_merge_rewrite_wave)) t
\gexec

CREATE OR REPLACE TABLE tmp3_merge_edited_delta AS
SELECT u.src_table, count(*)::BIGINT AS правок
FROM tmp3_merge_unmatched u
JOIN search_corpus c ON c.src_table = u.src_table AND c.row_key = u.row_key
WHERE EXISTS (SELECT 1 FROM tmp3_corpus t
              WHERE t.src_table = u.src_table AND t.refs = c.refs)
GROUP BY 1;

CREATE OR REPLACE TABLE tmp3_merge_ent_guard AS
SELECT e.src_table,
       coalesce(o.было, 0::BIGINT) AS было,
       CASE WHEN w.src_table IS NOT NULL THEN w.было
            ELSE greatest(coalesce(u.уйдёт, 0::BIGINT) - coalesce(ed.правок, 0::BIGINT), 0::BIGINT)
       END AS уйдёт,
       e.стало
FROM (SELECT src_table, count(*)::BIGINT AS стало FROM tmp3_corpus GROUP BY 1) e
LEFT JOIN (
  SELECT src_table, count(*)::BIGINT AS было
  FROM search_corpus
  WHERE src_table IN (SELECT DISTINCT src_table FROM tmp3_corpus)
  GROUP BY 1
) o USING (src_table)
LEFT JOIN (
  SELECT src_table, count(*)::BIGINT AS уйдёт FROM tmp3_merge_unmatched GROUP BY 1
) u USING (src_table)
LEFT JOIN tmp3_merge_edited_delta ed USING (src_table)
LEFT JOIN tmp3_merge_rewrite_wave w USING (src_table);

-- Усыхание сборки разбирается ниже (tmp3_merge_shrink): свидетель — витрина;
-- безусловный STOP «стало<было» заменён на «стало<витрины» (живой стоп 09.09).
-- Усыхание сборки: свидетель — витрина (живой стоп 09.09). 🔴 БЕЗ промежуточной
-- DML-таблицы: движок repeatable read — SELECT той же psql-сессии НЕ ВИДИТ INSERT,
-- сделанный \gexec-командой (замер 09.09: гейт видел mart пустой, после сессии
-- строка на месте; DDL-заполненные таблицы видны). Проверка — ПРЯМЫЕ \gexec-
-- команды per-entity: снапшот не мешает (витрина в сессии не менялась, «стало/
-- было» — литералы из видимой DDL-таблицы shrink). Расхождение → STOP.
CREATE OR REPLACE TABLE tmp3_merge_shrink AS
SELECT g.src_table, g.было, g.стало
FROM tmp3_merge_ent_guard g
WHERE g.было > 0 AND g.стало < g.было;

-- 🔴 ГОД ПОД ON_ERROR_STOP on (контрольная sc5a/b/c): команды несут error() —
-- при off расхождение печатается, но psql ПРОДОЛЖАЕТ и гейт молчит. Паттерн
-- p_rec_dead не годится: там INSERT без вердикта, здесь — STOP-проверка.
-- Имя сущности в тексте ошибки — через quote_literal (экранирование кавычек).
-- 🔴 СЧЁТ ВИТРИНЫ — ПО DECLARED-КЛЮЧУ, не по строкам (живой стоп 21:02:
-- контрагенты fold — витрина 373 РАЗВЁРНУТЫХ строк = 362 объектов, сборка 362;
-- count(*) ронял гейт ложно). count(DISTINCT (ключ-колонки)) — объекты для
-- fold, строки для построчных: та же форма, что корпусный row_key без суффиксов.
SELECT 'SELECT CASE WHEN (SELECT count(DISTINCT (' || kexpr || ')) FROM query_table('
       || quote_literal(src_table) || ')) <> ' || стало
       || ' THEN error(''corpus_merge: новая сборка меньше старой И разошлась с витриной: '''
       || ' || ' || quote_literal(src_table)
       || ' || '' (стало ' || стало || ' ключей витрины '' || '
       || '(SELECT count(DISTINCT (' || kexpr || ')) FROM query_table('
       || quote_literal(src_table) || '))'
       || ' || '' было ' || было || ')'') END;'
FROM (SELECT s.*, array_to_string(
                 list_transform(k.key_cols, c -> '"' || c || '"'), ',') AS kexpr
      FROM tmp3_merge_shrink s
      JOIN tmp3_key k ON lower(k.entity) = s.src_table) q
\gexec

DELETE FROM search_quality WHERE k LIKE 'entity_source_shrink:%';
INSERT INTO search_quality
SELECT 'entity_source_shrink:' || src_table, было - стало,
       'сущность усохла в 1С (витрина подтверждена \gexec-проверкой выше): '
         || src_table || ' было=' || было || ' стало=витрине=' || стало
FROM tmp3_merge_shrink;
-- Расхождение остановило бы исполнение error() в \gexec выше; ниже (частичная
-- потеря, die_unexplained) сущность исключается membership'ом в shrink.
-- «Обрезанный синк» (витрина сама порезана == сборке): внутри такта не отличим
-- без второго свидетеля; видимость — coverage-постчек следующего такта (в_1С
-- против в_витрины, п.13); усиление постчека — отдельный пункт, без чисел-из-головы.

-- Частичный уход при росте сборки: проверяем, жив ли split_part(row_key,'|',1)
-- в колонке Recorder витрины (имя платформы 1С, не домен). Все живы — коллапс
-- ключа, запись в search_quality; мёртвый Recorder или нет колонки — STOP ниже.
-- «стало >= было» (08.09): при РАВНОМ объёме классификация тоже нужна —
-- [замер 08.09, такт №22] одна строка каталога заменена (стало==было==368):
-- строгий «стало > было» оставлял замену неклассифицированной, и гвард
-- «частичная потеря» честно, но зря останавливал такт. Равенство — тот же
-- класс «замена при сохранении объёма», что и рост.
CREATE OR REPLACE TABLE tmp3_merge_collapse_cand AS
SELECT src_table, было, стало, уйдёт
FROM tmp3_merge_ent_guard
WHERE уйдёт > 0 AND уйдёт < было AND стало >= было;

CREATE OR REPLACE TABLE tmp3_merge_collapse_rec AS
SELECT u.src_table, u.row_key, split_part(u.row_key, '|', 1) AS rec
FROM tmp3_merge_unmatched u
WHERE u.src_table IN (SELECT src_table FROM tmp3_merge_collapse_cand)
  AND split_part(u.row_key, '|', 1) <> '';

CREATE OR REPLACE TABLE tmp3_merge_collapse_regs AS
SELECT DISTINCT c.src_table
FROM tmp3_merge_collapse_cand c
WHERE EXISTS (SELECT 1 FROM duckdb_columns() dc
              WHERE dc.database_name = current_database()
                AND dc.table_name = c.src_table
                AND dc.column_name = 'Recorder');

CREATE OR REPLACE TABLE tmp3_merge_collapse_dead (src_table VARCHAR, dead BIGINT);

PREPARE p_collapse_dead AS
INSERT INTO tmp3_merge_collapse_dead
SELECT $1::VARCHAR, count(*)
FROM (SELECT DISTINCT rec FROM tmp3_merge_collapse_rec WHERE src_table = $1) r
WHERE NOT EXISTS (SELECT 1 FROM query_table($1) q WHERE q."Recorder" = r.rec);

\set ON_ERROR_STOP off
SELECT 'EXECUTE p_collapse_dead(' || quote_literal(src_table) || ');'
FROM tmp3_merge_collapse_regs
\gexec
\set ON_ERROR_STOP on

CREATE OR REPLACE TABLE tmp3_merge_key_collapse AS
SELECT c.src_table, c.было, c.стало, c.уйдёт
FROM tmp3_merge_collapse_cand c
INNER JOIN tmp3_merge_collapse_regs r USING (src_table)
INNER JOIN tmp3_merge_collapse_dead d ON d.src_table = c.src_table AND d.dead = 0
WHERE (SELECT count(DISTINCT rec) FROM tmp3_merge_collapse_rec WHERE src_table = c.src_table) > 0;

DELETE FROM search_quality WHERE k LIKE 'entity_key_collapse:%';
INSERT INTO search_quality
SELECT 'entity_key_collapse:' || src_table, уйдёт,
       'было ' || было || ' → стало ' || стало
FROM tmp3_merge_key_collapse;

-- Частичный уход, мёртвый Recorder в регистре: документ-регистратор удалён из 1С —
-- дельта, строки уходят из корпуса. Документ жив в витрине — дефект транспорта.
-- 🔴 ДОКУМЕНТНАЯ СУЩНОСТЬ — САМА СЕБЕ РЕГИСТРАТОР: у неё нет Recorder и written_by
-- (это связь «кто пишет регистр»), и прежний doc_tbl для неё был пуст — классификатор
-- удалений её не покрывал, и легитимная убыль живой базы (okna 02.09+: 637 GUID
-- документов, отсутствующих в витрине) стопилась гвардом «частичная потеря» как
-- необъяснённая. Теперь: сегмент ключа — платформенный тип ('StandardODATA.…',
-- как в 1С OData) → регистратор из него; иначе written_by; иначе при колонке
-- ref_key в витрине (платформенное поле документов) doc_tbl = сама сущность,
-- и её строки классифицируются тем же p_doc_alive (жив/помечен/удалён).
-- Гейт 'StandardODATA.%' заодно убирает мусорные doc_tbl ('1'-'5' — LineNumber
-- табличной части, попадавший в EXECUTE и ронявший «Table with name 1»).
CREATE OR REPLACE TABLE tmp3_merge_delta_rec AS
SELECT u.src_table, u.row_key, split_part(u.row_key, '|', 1) AS rec,
       CASE WHEN split_part(u.row_key, '|', 2) LIKE 'StandardODATA.%'
            THEN lower(regexp_replace(split_part(u.row_key, '|', 2), '^.*\.', ''))
            ELSE coalesce((SELECT st.written_by FROM search_tables st
                           WHERE st.src_table = u.src_table),
                          CASE WHEN EXISTS (SELECT 1 FROM duckdb_columns() dc
                                             WHERE dc.database_name = current_database()
                                               AND dc.table_name = u.src_table
                                               AND lower(dc.column_name) = 'ref_key')
                               THEN u.src_table END)
       END AS doc_tbl
FROM tmp3_merge_unmatched u
WHERE u.src_table IN (SELECT src_table FROM tmp3_merge_collapse_cand)
  AND split_part(u.row_key, '|', 1) <> '';

CREATE OR REPLACE TABLE tmp3_merge_rec_dead (src_table VARCHAR, rec VARCHAR);

PREPARE p_rec_dead AS
INSERT INTO tmp3_merge_rec_dead
SELECT $1::VARCHAR, r.rec
FROM (SELECT DISTINCT rec FROM tmp3_merge_collapse_rec WHERE src_table = $1) r
WHERE NOT EXISTS (SELECT 1 FROM query_table($1) q WHERE q."Recorder" = r.rec);

\set ON_ERROR_STOP off
SELECT 'EXECUTE p_rec_dead(' || quote_literal(src_table) || ');'
FROM tmp3_merge_collapse_regs
\gexec
\set ON_ERROR_STOP on

-- Документные сущности cand (колонка ref_key есть, Recorder нет): их «регистратор»
-- — они сами. Мёртвый ref_key (строки нет в витрине — deletionmark уже недоступен)
-- означает «документ удалён из 1С» — та же семантика, что у мёртвого Recorder
-- регистра: легитимная дельта, а не потеря.
-- 🔴 ОГРАНИЧЕНИЕ ЭТОГО СВИДЕТЕЛЯ (армия 08.09): регистровая ветка смотрит ДВЕ
-- таблицы (Recorder в регистре + документ в своей витрине), документная — ОДНУ,
-- поэтому «строка исчезла при живом документе» здесь не отличима от удаления
-- и уходит в deleted вместе с ним; транспорт-дефект для документного пути
-- недостижим (мёртв/жив взаимоисключены одной таблицей), а ветка для документов
-- меняет поведение с fail-closed (STOP «частичная потеря») на fail-open
-- (deleted = легитимно). Регистровая ветка ложный deleted даёт при неполной
-- витрине ДОКУМЕНТА (p_doc_alive) — с 31.08; здесь дыра та же по сути.
-- Реальные страховки: вектор-бюджет (MERGE_VECTOR_LOSS_TOLERANCE, доля от базы)
-- и «стало < было»; гварды ent_guard-порог и «удаление снесло бы» key_deleted
-- исключают и НЕ защищают. Полный второй свидетель — search_changed_rows
-- op='deleted_gone', пакет «полная B» (шапка этого файла; docs/audit/
-- FULLB_PLAN_2026-09-03.md).
CREATE OR REPLACE TABLE tmp3_merge_docs AS
SELECT DISTINCT c.src_table
FROM tmp3_merge_collapse_cand c
WHERE EXISTS (SELECT 1 FROM duckdb_columns() dc
              WHERE dc.database_name = current_database()
                AND dc.table_name = c.src_table
                AND lower(dc.column_name) = 'ref_key')
  AND NOT EXISTS (SELECT 1 FROM duckdb_columns() dc
                  WHERE dc.database_name = current_database()
                    AND dc.table_name = c.src_table
                    AND lower(dc.column_name) = 'recorder');

PREPARE p_doc_dead AS
INSERT INTO tmp3_merge_rec_dead
SELECT $1::VARCHAR, r.rec
FROM (SELECT DISTINCT rec FROM tmp3_merge_collapse_rec WHERE src_table = $1) r
WHERE NOT EXISTS (SELECT 1 FROM query_table($1) q WHERE q."Ref_Key" = r.rec);

\set ON_ERROR_STOP off
SELECT 'EXECUTE p_doc_dead(' || quote_literal(src_table) || ');'
FROM tmp3_merge_docs
\gexec
\set ON_ERROR_STOP on

CREATE OR REPLACE TABLE tmp3_merge_doc_alive (doc_tbl VARCHAR, rec VARCHAR, alive BIGINT);

PREPARE p_doc_alive AS
INSERT INTO tmp3_merge_doc_alive
SELECT $1::VARCHAR, d."Ref_Key", count(*)
FROM query_table($1) d
WHERE d."Ref_Key" IN (SELECT r.rec FROM tmp3_merge_delta_rec r WHERE r.doc_tbl = $1)
  -- «Жив» = присутствует и НЕ помечен на удаление: annulled/deleted документы
  -- движений в регистрах не пишут, их отсутствие — не дефект транспорта.
  -- deletionmark — платформенное поле, есть у всех документных таблиц витрины.
  AND lower(try_cast(d."DeletionMark" AS VARCHAR)) IS DISTINCT FROM 'true'
GROUP BY d."Ref_Key";

\set ON_ERROR_STOP off
SELECT 'EXECUTE p_doc_alive(' || quote_literal(doc_tbl) || ');'
FROM (SELECT DISTINCT doc_tbl FROM tmp3_merge_delta_rec
      WHERE doc_tbl IS NOT NULL AND doc_tbl <> '') x
\gexec
\set ON_ERROR_STOP on

CREATE OR REPLACE TABLE tmp3_merge_orphan_rec AS
SELECT d.src_table, d.row_key, d.rec, d.doc_tbl
FROM tmp3_merge_delta_rec d
INNER JOIN tmp3_merge_rec_dead x USING (src_table, rec);

CREATE OR REPLACE TABLE tmp3_merge_deleted_delta_rows AS
SELECT o.src_table, o.row_key
FROM tmp3_merge_orphan_rec o
WHERE o.doc_tbl IS NOT NULL AND o.doc_tbl <> ''
  AND NOT EXISTS (SELECT 1 FROM tmp3_merge_doc_alive a
                  WHERE a.doc_tbl = o.doc_tbl AND a.rec = o.rec AND a.alive > 0);

CREATE OR REPLACE TABLE tmp3_merge_transport_defect AS
SELECT o.src_table, o.rec, o.doc_tbl, count(*)::BIGINT AS n
FROM tmp3_merge_orphan_rec o
INNER JOIN tmp3_merge_doc_alive a ON a.doc_tbl = o.doc_tbl AND a.rec = o.rec AND a.alive > 0
GROUP BY 1, 2, 3;

-- 🔴 REPOST_DELTA (живой стоп 09.09 19:34, 6 движений/2 документа): документ ЖИВ,
-- движений в регистре нет, НО сам документ ИЗМЕНЯЛСЯ в этом окне — есть delta-маркер
-- search_changed_rows (витринный ключ: равно rec — fold/HTTP, или хвост «|N» —
-- построчный). Перепроведение сняло движения при живом документе — легитимная
-- убыль 1С, классифицируем и пишем в quality; БЕЗ маркера — прежний STOP
-- «дефект транспорта» (документ не трогали, а движения исчезли = потеря).
-- Свидетель — данные (маркеры B0), не порог.
CREATE OR REPLACE TABLE tmp3_merge_repost_delta AS
SELECT t.src_table, t.rec, t.n
FROM tmp3_merge_transport_defect t
WHERE EXISTS (
  SELECT 1 FROM search_changed_rows k
  WHERE k.op = 'delta'
    AND k.src_table = t.doc_tbl
    AND (k.key_text = t.rec OR starts_with(k.key_text, t.rec || '|')));

DELETE FROM search_quality WHERE k LIKE 'entity_repost_delta:%';
INSERT INTO search_quality
SELECT 'entity_repost_delta:' || src_table, n,
       'движения сняты перепроведением живого документа (delta-маркер): recorder=' || rec
FROM tmp3_merge_repost_delta;

SELECT CASE WHEN count(*) > 0
       THEN error('corpus_merge: документ жив, движений в регистре нет (дефект транспорта): '
                  || string_agg(src_table || ' recorder=' || rec || ' (' || n || ')',
                                ', ' ORDER BY src_table, rec)) END
FROM tmp3_merge_transport_defect t
WHERE NOT EXISTS (SELECT 1 FROM tmp3_merge_repost_delta r
                  WHERE r.src_table = t.src_table AND r.rec = t.rec);

CREATE OR REPLACE TABLE tmp3_merge_key_deleted_delta AS
SELECT c.src_table, c.было, c.стало, count(d.row_key)::BIGINT AS уйдёт
FROM tmp3_merge_collapse_cand c
INNER JOIN tmp3_merge_deleted_delta_rows d ON d.src_table = c.src_table
WHERE NOT EXISTS (SELECT 1 FROM tmp3_merge_transport_defect t WHERE t.src_table = c.src_table)
GROUP BY 1, 2, 3;

DELETE FROM search_quality WHERE k LIKE 'entity_deleted_delta:%';
INSERT INTO search_quality
SELECT 'entity_deleted_delta:' || src_table, уйдёт,
       'было ' || было || ' → стало ' || стало
FROM tmp3_merge_key_deleted_delta;

-- Допуск на легитимные удаления 1С при перепроведении (без пары по refs:
-- строка и в витрине исчезла). Порог — доля от «было», не абсолютное число:
-- защита от потери стелажа остаётся (массовая пропажа > 0.1% — STOP),
-- единичные удаления строк (замер 31.08: 10 из 76 214 = 0.013%) — дельта.
SELECT CASE WHEN count(*) > 0
       THEN error('corpus_merge: частичная потеря объектов у сущностей: '
                  || string_agg(src_table || ' (' || уйдёт || ' из ' || было || ')',
                                ', ')) END
FROM tmp3_merge_ent_guard g
WHERE g.уйдёт > 0 AND g.уйдёт < g.было
  AND g.уйдёт::DOUBLE > g.было * 0.001
  AND NOT EXISTS (SELECT 1 FROM tmp3_merge_key_collapse k WHERE k.src_table = g.src_table)
  AND NOT EXISTS (SELECT 1 FROM tmp3_merge_key_deleted_delta k WHERE k.src_table = g.src_table)
  -- (09.09) SHRINK: убыль объяснена усохшим источником (сборка==витрина —
  -- \gexec-проверка выше остановила бы расхождение) — та же легитимная убыль.
  AND NOT EXISTS (SELECT 1 FROM tmp3_merge_shrink s
                  WHERE s.src_table = g.src_table)
  -- (09.09) REPOST_DELTA: движения сняты перепроведением живых документов
  -- (delta-маркер) — массовое закрытие периода не должно стопить конвейер.
  AND NOT EXISTS (SELECT 1 FROM tmp3_merge_repost_delta r
                  WHERE r.src_table = g.src_table);

DELETE FROM search_quality WHERE k LIKE 'entity_source_delta:%' OR k LIKE 'entity_edited_delta:%';
INSERT INTO search_quality
SELECT 'entity_edited_delta:' || src_table, правок,
       'строк правлено при перепроведении (пара по refs, контент изменён)'
FROM tmp3_merge_edited_delta;

INSERT INTO search_quality
SELECT 'entity_source_delta:' || g.src_table, g.уйдёт,
       'легитимные удаления 1С (нет пары по refs; доля ' ||
       round(g.уйдёт::DOUBLE / greatest(g.было,1) * 100, 3) || '% <= 0.1%)'
FROM tmp3_merge_ent_guard g
WHERE g.уйдёт > 0 AND g.уйдёт < g.было
  AND g.уйдёт::DOUBLE <= g.было * 0.001;

CREATE OR REPLACE TABLE tmp3_merge_key_form AS
SELECT src_table, было, стало, уйдёт
FROM tmp3_merge_ent_guard
WHERE было > 0 AND уйдёт = было AND стало > 0 AND стало >= было;

DELETE FROM search_quality WHERE k LIKE 'entity_key_form_changed:%';
INSERT INTO search_quality
SELECT 'entity_key_form_changed:' || src_table, стало,
       'было ' || было || ' → стало ' || стало
FROM tmp3_merge_key_form;

DELETE FROM search_quality WHERE k LIKE 'entity_rewrite_wave:%';
INSERT INTO search_quality
SELECT 'entity_rewrite_wave:' || src_table, стало,
       'было ' || было || ' → стало ' || стало || ' (exact-match '
       || (SELECT matched_exact FROM tmp3_merge_ent_counts c WHERE c.src_table = w.src_table)
       || '/' || w.было || ')'
FROM tmp3_merge_rewrite_wave w;

SELECT CASE WHEN (SELECT count(*) FROM search_corpus) > 0
             AND уйдёт::DOUBLE / (SELECT count(*) FROM search_corpus) > 0.1
       THEN error('corpus_merge: удаление снесло бы ' || уйдёт || ' объектов из '
                  || (SELECT count(*) FROM search_corpus) || ' — остановлено') END
FROM (SELECT count(*) AS уйдёт FROM tmp3_merge_unmatched u
      WHERE NOT EXISTS (SELECT 1 FROM tmp3_merge_key_form k
                        WHERE k.src_table = u.src_table)
        AND NOT EXISTS (SELECT 1 FROM tmp3_merge_rewrite_wave k
                        WHERE k.src_table = u.src_table)
        AND NOT EXISTS (SELECT 1 FROM tmp3_merge_key_collapse k
                        WHERE k.src_table = u.src_table)
        AND NOT EXISTS (SELECT 1 FROM tmp3_merge_key_deleted_delta k
                        WHERE k.src_table = u.src_table));

-- Сужение величин — не ошибка, но и не пустяк: строка теряет числа, оставаясь на месте,
-- и по журналу это неотличимо от «их там и не было». Считаем ДО записи, пока прежнее
-- состояние ещё видно, и кладём числом в базу (п. 13).
DELETE FROM search_quality WHERE k = 'nums_lost';
INSERT INTO search_quality
SELECT 'nums_lost', count(*), 'строк, у которых величины были, а в новой сборке их нет'
FROM search_corpus c JOIN tmp3_corpus t USING (src_table, row_key)
WHERE c.nums IS NOT NULL AND len(map_keys(c.nums)) > 0
  AND (t.nums IS NULL OR len(map_keys(t.nums)) = 0);

-- ============ 1. СХЕМА ============
-- DDL остаётся ВНЕ транзакции: движок коммитит его сразу и сам об этом предупреждает
-- («DDL is not transactional»), а при `sdb_strict_ddl = on` он внутри транзакции упал бы.
ALTER TABLE search_corpus ADD COLUMN IF NOT EXISTS nums MAP(VARCHAR, DOUBLE);
-- Булевы реквизиты — своей типизированной картой, как и величины. Обращение к
-- реквизиту по имени вместо подстрочного поиска в тексте (`corpus_build.sql`, is_flag).
-- [проверено] `ADD COLUMN` при живом инвертированном индексе индекс не роняет.
ALTER TABLE search_corpus ADD COLUMN IF NOT EXISTS flags MAP(VARCHAR, BOOLEAN);
-- Карта ссылок строки. Вектор не сбрасывается: колонка не входит в doc_hash.
ALTER TABLE search_corpus ADD COLUMN IF NOT EXISTS refs_map MAP(VARCHAR, VARCHAR);
-- Стабильный бизнес-хэш рядом с doc_hash (row_key не трогаем).
ALTER TABLE search_corpus ADD COLUMN IF NOT EXISTS content_hash VARCHAR;

-- Время последнего переноса сущности в поисковый слой. Пишется ниже по фактически
-- перенесённым (`tmp3_build`); такт-пропуск колонку не трогает.
ALTER TABLE search_tables ADD COLUMN IF NOT EXISTS last_built_at TIMESTAMP;

-- ============ 1-бис. ПЕРЕНОС ВЕКТОРОВ ПРИ REWRITE-ВОЛНЕ (О4) + content_hash ============
-- Текст doc = «сущность | колонка: значение | …» (строит corpus_build). Карта
-- бизнес-полей — пары с «: »; префикс без двоеточия отбрасывается. content_hash —
-- sha1 канона (сортированные пары без платформенного шума и пустых). Стыковка
-- пар переноса — по уникальному content_hash в пределах сущности (миграция
-- вектор-нейтральна: форма сменилась → doc_hash другой, content_hash тот же →
-- emb переезжает). Дубли content_hash с обеих сторон → пара не ищется.
-- Доки: sql/functions/map#map_from_entries; list_intersect; map_extract_value;
-- sql/functions/text#string_split; sql/functions/list#array_to_string; list_sort;
-- sql/functions/utility#sha1; sql/statements/create_macro.
-- [замер 01.09 okna] дубли ключей («Map keys must be unique» на map_from_entries)
-- схлопываются map_concat'ом: последний выигрывает; на чистых строках результат
-- идентичен старой формуле. Доки: sql/functions/map#map_concat.
CREATE OR REPLACE MACRO corpus_doc_bmap(doc) AS (
  CASE WHEN len(list_filter(string_split(coalesce(doc, ''), ' | '),
                            p -> position(': ' IN p) > 0)) = 0
       THEN MAP{}::MAP(VARCHAR, VARCHAR)
       ELSE list_reduce(
              list_transform(
                list_filter(string_split(doc, ' | '),
                            p -> position(': ' IN p) > 0),
                p -> MAP {split_part(p, ': ', 1):
                          substr(p, length(split_part(p, ': ', 1)) + 3)}
              ),
              (acc, m) -> map_concat(acc, m)
            )
  END
);

-- content_hash: карта один раз (map_entries) — как в corpus_init.sql (корень
-- «деградации» 03-04.09: 2N+1 пересборок corpus_doc_bmap на строку; фикс
-- разработчиков SereneDB 08.09, 7 мин против 5+ ч). Обе копии макроса обязаны
-- совпадать побайтно. Доки: sql/functions/map#map_entries.
CREATE OR REPLACE MACRO corpus_content_hash(doc) AS (
  sha1(coalesce(
    array_to_string(
      list_sort(
        list_transform(
          list_filter(
            map_entries(corpus_doc_bmap(doc)),
            e -> e.key <> 'DataVersion'
                 AND e.key <> '__metadata'
                 AND position('navigationLinkUrl' IN e.key) = 0
                 AND coalesce(e.value, '') <> ''
          ),
          e -> e.key || chr(1) || e.value
        )
      ),
      chr(0)
    ),
    ''
  ))
);

CREATE OR REPLACE MACRO corpus_bmap_common_eq(a, b) AS (
  len(list_intersect(map_keys(a), map_keys(b))) > 0
  AND len(list_filter(
        list_intersect(map_keys(a), map_keys(b)),
        k -> map_extract_value(a, k) IS DISTINCT FROM map_extract_value(b, k)
      )) = 0
);

-- Стыковка переноса: (A) уникальный content_hash — миграция и тождество
-- канона; (B) уникальные refs + corpus_bmap_common_eq — волна при смене формы
-- с новыми заполненными колонками (хэш другой, пересечение значений то же).
-- content_hash на лету, если колонка ещё NULL. UPDATE search_corpus — только
-- ПОСЛЕ гейта (ниже), иначе стоп оставил бы следы записи.
CREATE OR REPLACE TABLE tmp3_merge_emb_old AS
SELECT src_table, ch AS content_hash, any_value(emb) AS emb
FROM (
  SELECT src_table, emb,
         coalesce(nullif(content_hash, ''), corpus_content_hash(doc)) AS ch
  FROM search_corpus
  WHERE src_table IN (SELECT src_table FROM tmp3_merge_rewrite_wave)
    AND emb IS NOT NULL
) _
WHERE ch IS NOT NULL AND ch <> ''
GROUP BY src_table, ch
HAVING count(*) = 1;

CREATE OR REPLACE TABLE tmp3_merge_emb_new AS
SELECT src_table, row_key, ch AS content_hash
FROM (
  SELECT src_table, row_key,
         coalesce(nullif(content_hash, ''), corpus_content_hash(doc)) AS ch
  FROM tmp3_corpus
  WHERE src_table IN (SELECT src_table FROM tmp3_merge_rewrite_wave)
) _
WHERE ch IS NOT NULL AND ch <> ''
QUALIFY count(*) OVER (PARTITION BY src_table, ch) = 1;

CREATE OR REPLACE TABLE tmp3_merge_emb_old_refs AS
SELECT src_table, refs, any_value(emb) AS emb, any_value(corpus_doc_bmap(doc)) AS bmap
FROM search_corpus
WHERE src_table IN (SELECT src_table FROM tmp3_merge_rewrite_wave)
  AND emb IS NOT NULL AND refs IS NOT NULL AND refs <> ''
GROUP BY src_table, refs
HAVING count(*) = 1;

CREATE OR REPLACE TABLE tmp3_merge_emb_new_refs AS
SELECT src_table, row_key, refs, corpus_doc_bmap(doc) AS bmap
FROM tmp3_corpus
WHERE src_table IN (SELECT src_table FROM tmp3_merge_rewrite_wave)
  AND refs IS NOT NULL AND refs <> ''
QUALIFY count(*) OVER (PARTITION BY src_table, refs) = 1;

CREATE OR REPLACE TABLE tmp3_merge_emb_xfer AS
SELECT src_table, row_key, emb FROM (
  SELECT n.src_table, n.row_key, o.emb, 1 AS prio
  FROM tmp3_merge_emb_new n
  INNER JOIN tmp3_merge_emb_old o USING (src_table, content_hash)
  UNION ALL
  SELECT n.src_table, n.row_key, o.emb, 2 AS prio
  FROM tmp3_merge_emb_new_refs n
  INNER JOIN tmp3_merge_emb_old_refs o USING (src_table, refs)
  WHERE corpus_bmap_common_eq(n.bmap, o.bmap)
) _
QUALIFY row_number() OVER (PARTITION BY src_table, row_key ORDER BY prio) = 1;

DELETE FROM search_quality WHERE k LIKE 'entity_emb_xfer:%';
INSERT INTO search_quality
SELECT 'entity_emb_xfer:' || src_table, count(*)::BIGINT,
       'векторов перенесено без пересчёта (content_hash или refs+common_eq)'
FROM tmp3_merge_emb_xfer
GROUP BY 1;

-- ============ 1-тер. ГЕЙТ ВЕКТОР-БЮДЖЕТА — СТОП ДО ЗАПИСИ В search_corpus ============
-- Считаем, сколько векторов эта транзакция оставит без emb (DELETE исчезнувших ключей
-- + MATCHED со сменой content_hash), минус спасённые картой tmp3_merge_emb_xfer.
-- Порог — ДОЛЯ от векторов всей базы (MERGE_VECTOR_LOSS_TOLERANCE, умолчание 0.5%).
-- Явный обход — только MERGE_VECTOR_LOSS_BYPASS=1 с записью в search_quality.
-- Доки: sql/functions/utility#error; sql/statements/insert.
CREATE TABLE IF NOT EXISTS tmp3_merge_cfg (
  chunk_rows BIGINT,
  vector_loss_tol DOUBLE,
  vector_loss_bypass BOOLEAN
);
ALTER TABLE tmp3_merge_cfg ADD COLUMN IF NOT EXISTS vector_loss_tol DOUBLE;
ALTER TABLE tmp3_merge_cfg ADD COLUMN IF NOT EXISTS vector_loss_bypass BOOLEAN;
INSERT INTO tmp3_merge_cfg (chunk_rows, vector_loss_tol, vector_loss_bypass)
SELECT 1000000, 0.005, false
WHERE (SELECT count(*) FROM tmp3_merge_cfg) = 0;
UPDATE tmp3_merge_cfg SET vector_loss_tol = coalesce(vector_loss_tol, 0.005),
                     vector_loss_bypass = coalesce(vector_loss_bypass, false);

CREATE OR REPLACE TABLE tmp3_merge_vec_budget AS
WITH rebuilt AS (
  SELECT DISTINCT src_table FROM tmp3_corpus
),
old_full AS (
  SELECT src_table, row_key, emb, doc,
         coalesce(nullif(content_hash, ''), corpus_content_hash(doc)) AS ch,
         corpus_doc_bmap(doc) AS bmap
  FROM search_corpus
  WHERE src_table IN (SELECT src_table FROM rebuilt)
),
new_full AS (
  SELECT src_table, row_key, doc,
         coalesce(nullif(content_hash, ''), corpus_content_hash(doc)) AS ch,
         corpus_doc_bmap(doc) AS bmap
  FROM tmp3_corpus
),
was AS (
  SELECT src_table, count(*) FILTER (WHERE emb IS NOT NULL)::BIGINT AS векторов_было
  FROM old_full
  GROUP BY 1
),
surviving AS (
  -- content_hash равен ИЛИ форма расширилась при тех же общих значениях
  SELECT o.src_table, count(*)::BIGINT AS векторов_живёт
  FROM old_full o
  INNER JOIN new_full n
          ON n.src_table = o.src_table AND n.row_key = o.row_key
         AND (n.ch IS NOT DISTINCT FROM o.ch
              OR corpus_bmap_common_eq(o.bmap, n.bmap))
  WHERE o.emb IS NOT NULL
  GROUP BY 1
),
xfer AS (
  SELECT src_table, count(*)::BIGINT AS векторов_спасено_картой
  FROM tmp3_merge_emb_xfer
  GROUP BY 1
),
die_hash AS (
  SELECT o.src_table, count(*)::BIGINT AS hash_kill
  FROM old_full o
  INNER JOIN new_full n
          ON n.src_table = o.src_table AND n.row_key = o.row_key
         AND n.ch IS DISTINCT FROM o.ch
         AND NOT corpus_bmap_common_eq(o.bmap, n.bmap)
  WHERE o.emb IS NOT NULL
  GROUP BY 1
),
die_unmatched AS (
  SELECT o.src_table, count(*)::BIGINT AS unmatched_kill
  FROM old_full o
  WHERE o.emb IS NOT NULL
    AND NOT EXISTS (SELECT 1 FROM new_full n
                    WHERE n.src_table = o.src_table AND n.row_key = o.row_key)
  GROUP BY 1
),
-- НЕОБЪЯСНЁННЫЙ unmatched — единственный класс «окончательной потери».
-- Объяснения из данных (правка 08.09; прежде гейт суммировал и пересчёт, и
-- волны — первый такт нового канона чанкования проводили разовым
-- MERGE_VECTOR_LOSS_BYPASS руками, что запрещено п.0):
--   (а) ЗАМЕНА КЛЮЧА: контент строки (content_hash) жив в новой сборке той
--       же сущности — строка переехала на новый ключ; вектор вернёт
--       xfer-карта или досчитает шаг 5 (замер 08.09: установкацен 22 109,
--       счёт-волны);
--   (б) ЛЕГИТМНАЯ УБЫЛЬ 1С: сущность в key_deleted_delta (документы удалены
--       — свидетель витрина) или key_collapse (перепроведение).
-- Прочее (контент исчез без объяснения) — потеря, гейт STOPит (класс 31.08).
-- hash_kill отдельно НЕ вычитается и в «умрёт» не входит: строка жива,
-- шаг 5 пересчитает emb на месте.
die_unexplained AS (
  -- ch-приход объясняет строку только при СЧЁТНОМ балансе группы ch: новых
  -- строк с этим ch пришло не меньше, чем было старых (частный случай — пара
  -- 1:1, как в xfer-карте). Без баланса 1000 старых дублей одного ch при
  -- одном новом «объяснялись» бы все — массовая потеря маскировалась (армия
  -- 08.09). Дисбаланс → не объяснены → ловятся гейтом; плановая смена канона
  -- чанкования с дисбалансом — операция обслуживания: первый такт после неё
  -- идёт с MERGE_VECTOR_LOSS_BYPASS=1 по RUNBOOK (разовый обход, не код).
  SELECT o.src_table, count(*)::BIGINT AS n
  FROM old_full o
  WHERE o.emb IS NOT NULL
    AND NOT EXISTS (SELECT 1 FROM new_full n
                    WHERE n.src_table = o.src_table AND n.row_key = o.row_key)
    AND NOT EXISTS (SELECT 1 FROM new_full n2
                    WHERE n2.src_table = o.src_table
                      AND n2.ch IS NOT DISTINCT FROM o.ch
                      AND ((SELECT count(*) FROM new_full n3
                            WHERE n3.src_table = o.src_table
                              AND n3.ch IS NOT DISTINCT FROM o.ch)
                           >= (SELECT count(*) FROM old_full o2
                               WHERE o2.src_table = o.src_table
                                 AND o2.ch IS NOT DISTINCT FROM o.ch)))
    AND NOT EXISTS (SELECT 1 FROM tmp3_merge_key_deleted_delta d
                    WHERE d.src_table = o.src_table)
    AND NOT EXISTS (SELECT 1 FROM tmp3_merge_key_collapse c
                    WHERE c.src_table = o.src_table)
    AND NOT EXISTS (SELECT 1 FROM tmp3_merge_rewrite_wave rw
                    WHERE rw.src_table = o.src_table)
    -- (09.09) SHRINK: вектор исчезающей строки объяснён усохшим источником
    -- (сборка==витрина, \gexec-проверка выше) — легитимная убыль, не катастрофа.
    AND NOT EXISTS (SELECT 1 FROM tmp3_merge_shrink s
                    WHERE s.src_table = o.src_table)
    -- (09.09) REPOST_DELTA: движения сняты перепроведением живого документа
    -- (delta-маркер) — легитимная убыль движений, не потеря транспорта.
    AND NOT EXISTS (SELECT 1 FROM tmp3_merge_repost_delta r
                    WHERE r.src_table = o.src_table)
  GROUP BY 1
)
-- 🔴 «УМРЁТ» = ОКОНЧАТЕЛЬНАЯ ПОТЕРЯ, А НЕ ПЕРЕСЧЁТ (правка 08.09 по указанию
-- владельца «ручное — в пайплайн»; прежде гейт суммировал всё подряд и первый
-- такт нового канона чанкования приходилось проводить разовым
-- MERGE_VECTOR_LOSS_BYPASS — ручной шаг, запрещённый п.0). Классы:
--   * hash_kill — строка ЖИВА (row_key на месте), контент изменился: MERGE
--     обновит, emb=NULL, шаг 5 (embed_bulk) посчитает заново — НЕ потеря;
--   * unmatched при ЗАМЕНЕ КЛЮЧА (контент жив в новой сборке) или
--     ЛЕГИТМНОЙ УБЫЛИ (key_deleted_delta/key_collapse) — НЕ потеря;
--   * прочий unmatched — контент исчез без объяснения: потеря, гейт STOPит
--     (как при катастрофе 31.08).
SELECT coalesce(w.src_table, s.src_table, x.src_table, h.src_table, u.src_table, du.src_table) AS src_table,
       coalesce(w.векторов_было, 0::BIGINT) AS векторов_было,
       coalesce(x.векторов_спасено_картой, 0::BIGINT) AS векторов_спасено_картой,
       coalesce(s.векторов_живёт, 0::BIGINT) AS векторов_живёт,
       coalesce(h.hash_kill, 0::BIGINT) AS hash_kill,
       coalesce(u.unmatched_kill, 0::BIGINT) AS unmatched_kill,
       coalesce(du.n, 0::BIGINT) AS векторов_умрёт,
       CASE
         WHEN coalesce(u.unmatched_kill, 0) > 0
              AND EXISTS (SELECT 1 FROM tmp3_merge_rewrite_wave rw
                          WHERE rw.src_table = coalesce(w.src_table, u.src_table))
              AND coalesce(x.векторов_спасено_картой, 0) = 0
           THEN 'rewrite_wave без карты'
         WHEN coalesce(u.unmatched_kill, 0) > 0
              AND EXISTS (SELECT 1 FROM tmp3_merge_rewrite_wave rw
                          WHERE rw.src_table = coalesce(w.src_table, u.src_table))
           THEN 'rewrite_wave: unmatched минус карта'
         WHEN coalesce(u.unmatched_kill, 0) > 0 AND coalesce(du.n, 0) = 0
           THEN 'unmatched объяснён (замена ключа/легитимная убыль)'
         WHEN coalesce(u.unmatched_kill, 0) > 0
           THEN 'unmatched'
         WHEN coalesce(h.hash_kill, 0) > 0
           THEN 'content_hash/значение-изменение вне карты'
         ELSE 'ok'
       END AS причина
FROM was w
FULL OUTER JOIN surviving s USING (src_table)
FULL OUTER JOIN xfer x USING (src_table)
FULL OUTER JOIN die_hash h USING (src_table)
FULL OUTER JOIN die_unmatched u USING (src_table)
FULL OUTER JOIN die_unexplained du USING (src_table);

DELETE FROM search_quality WHERE k IN ('vector_loss_gate', 'vector_loss_bypass');
INSERT INTO search_quality
SELECT 'vector_loss_gate',
       (SELECT coalesce(sum(векторов_умрёт), 0) FROM tmp3_merge_vec_budget)::DOUBLE,
       'потеря векторов вне карты / всего='
         || (SELECT count(*) FILTER (WHERE emb IS NOT NULL) FROM search_corpus)
         || ' tol='
         || (SELECT vector_loss_tol FROM tmp3_merge_cfg LIMIT 1);

SELECT CASE
  WHEN (SELECT vector_loss_bypass FROM tmp3_merge_cfg LIMIT 1)
  THEN NULL
  WHEN (SELECT count(*) FILTER (WHERE emb IS NOT NULL) FROM search_corpus) = 0
  THEN NULL
  WHEN (SELECT coalesce(sum(векторов_умрёт), 0) FROM tmp3_merge_vec_budget)::DOUBLE
         / (SELECT count(*) FILTER (WHERE emb IS NOT NULL) FROM search_corpus)
       > (SELECT vector_loss_tol FROM tmp3_merge_cfg LIMIT 1)
  THEN error(
    'corpus_merge: вектор-бюджет — потеря '
    || (SELECT coalesce(sum(векторов_умрёт), 0) FROM tmp3_merge_vec_budget)
    || ' из '
    || (SELECT count(*) FILTER (WHERE emb IS NOT NULL) FROM search_corpus)
    || ' (>'
    || round(100.0 * (SELECT vector_loss_tol FROM tmp3_merge_cfg LIMIT 1), 3)
    || '%): '
    || (SELECT string_agg(
                  src_table || ' умерёт=' || векторов_умрёт
                    || ' было=' || векторов_было
                    || ' карта=' || векторов_спасено_картой
                    || ' [' || причина || ']',
                  '; '
                )
        FROM tmp3_merge_vec_budget
        WHERE векторов_умрёт > 0)
  )
END;

INSERT INTO search_quality
SELECT 'vector_loss_bypass', 1,
       'обход гейта вектор-бюджета (MERGE_VECTOR_LOSS_BYPASS), потеря='
         || (SELECT coalesce(sum(векторов_умрёт), 0) FROM tmp3_merge_vec_budget)
WHERE (SELECT vector_loss_bypass FROM tmp3_merge_cfg LIMIT 1);

-- Гейт пройден (или пустой корпус) — теперь можно писать. Миграция content_hash:
-- заполняем NULL без сброса emb, иначе MERGE увидит NULL≠hash и убьёт векторы.
-- [замер 01.09 okna] один UPDATE на весь корпус (1,66 млн строк) ЧАС висел без
-- CPU и записи (WAL не рос с 288 МБ, потоки движка спали) — транзакция такого
-- размера на 26.07.3 не доходит до фазы записи. Тот же приём, что пачки MERGE
-- ниже (E4b): порции по src_table (литералы IN), большие сущности режем
-- hash(row_key)%n_parts, checkpoint после каждой пачки. На повторных тактах
-- NULL уже нет и все пачки пустые — миграция мгновенная.
ALTER TABLE tmp3_corpus ADD COLUMN IF NOT EXISTS content_hash VARCHAR;
UPDATE tmp3_corpus SET content_hash = corpus_content_hash(doc)
WHERE content_hash IS NULL AND doc IS NOT NULL;

CREATE OR REPLACE TABLE tmp3_ch_ents AS
SELECT src_table, count(*)::BIGINT AS n FROM search_corpus
WHERE content_hash IS NULL AND doc IS NOT NULL
GROUP BY 1;

CREATE OR REPLACE TABLE tmp3_ch_jobs AS
WITH cfg AS (SELECT chunk_rows FROM tmp3_merge_cfg LIMIT 1),
small_ents AS (
  SELECT e.src_table, e.n FROM tmp3_ch_ents e, cfg
  WHERE e.n <= cfg.chunk_rows
),
large_ents AS (
  SELECT e.src_table, e.n,
         GREATEST(1, (e.n + cfg.chunk_rows - 1) // cfg.chunk_rows) AS n_parts
  FROM tmp3_ch_ents e, cfg
  WHERE e.n > cfg.chunk_rows
),
small_jobs AS (
  SELECT s.src_table, s.n, 1::BIGINT AS n_parts, 0::BIGINT AS part,
         ((sum(s.n) OVER (ORDER BY s.n DESC, s.src_table) - s.n)
           // (SELECT chunk_rows FROM cfg)) AS job_id
  FROM small_ents s
),
large_jobs AS (
  SELECT l.src_table, l.n, l.n_parts, i.part,
         1000000000 + row_number() OVER (ORDER BY l.src_table, i.part) AS job_id
  FROM large_ents l
  JOIN (SELECT unnest(range(64)) AS part) i ON i.part < l.n_parts
)
SELECT job_id, src_table, n, n_parts, part FROM small_jobs
UNION ALL
SELECT job_id, src_table, n, n_parts, part FROM large_jobs;

SELECT 'миграция content_hash пачками' AS шаг, count(DISTINCT job_id) AS пачек,
       sum(n) AS строк_к_миграции
FROM tmp3_ch_jobs;

SELECT stmt FROM (
  SELECT job_id, 1 AS ord,
         'UPDATE search_corpus SET content_hash = corpus_content_hash(doc) WHERE content_hash IS NULL AND doc IS NOT NULL AND src_table IN ('
         || ins || ')'
         || CASE WHEN n_parts = 1 THEN ''
            ELSE ' AND (hash(row_key) % ' || n_parts || ') = ' || part END
         || ';' AS stmt
  FROM (
    SELECT job_id,
           string_agg(quote_literal(src_table), ', ') AS ins,
           max(n_parts) AS n_parts,
           min(part) AS part
    FROM tmp3_ch_jobs GROUP BY job_id
  ) g
  UNION ALL
  SELECT job_id, 2, 'SELECT checkpoint();'
  FROM (SELECT DISTINCT job_id FROM tmp3_ch_jobs) x
) z ORDER BY job_id, ord
\gexec

DROP TABLE IF EXISTS tmp3_ch_jobs;
DROP TABLE IF EXISTS tmp3_ch_ents;

-- ============ 2. ЗАПИСЬ — ПАЧКАМИ, КАЖДАЯ СО СВОИМ COMMIT ============
-- [замер 18.08 klient-1] одна транзакция MERGE+UPDATE+DELETE на 15 148 327 строк
-- писала WAL 1 ч 08 мин и умерла на COMMIT: store.db.wal — No space left on device.
-- Откат вернул диск; стейдж цел. Пачка ≤ tmp3_merge_cfg.chunk_rows (префлайт E4b,
-- умолчание 1 000 000 ≈ 4 ГиБ WAL). CHECKPOINT после пачки сбрасывает WAL в store.db
-- (доки: sql/functions/utility#checkpointdatabase, Configuration › Pragmas ›
-- Checkpointing, sql/statements/transactions). DELETE исчезнувших — ПОСЛЕ всех
-- пачек: иначе недовставленная сущность выглядела бы «пропавшей».
--
-- [замер 18.08 klient-1] EXISTS по tmp3_merge_jobs в USING сканировал все 15,1 млн
-- и за 3 мин налил /var/lib/serenedb/.tmp на 21 ГиБ (90 % диска). Фильтр —
-- src_table IN (литералы пачки): движок отсекает до скана. Доки: MERGE INTO;
-- sql/functions/utility#hash; Configuration › Pragmas › Temp Directory.
-- Гейт вектор-бюджета выше обязан стоять ДО первого MERGE/DELETE в search_corpus.
SELECT CASE WHEN (SELECT min(chunk_rows) FROM tmp3_merge_cfg) < 10000
       THEN error('corpus_merge: chunk_rows < 10000') END;

CREATE OR REPLACE TABLE tmp3_merge_ents AS
SELECT src_table, count(*)::BIGINT AS n FROM tmp3_corpus GROUP BY 1;

CREATE OR REPLACE TABLE tmp3_merge_jobs AS
WITH cfg AS (SELECT chunk_rows FROM tmp3_merge_cfg LIMIT 1),
small_ents AS (
  SELECT e.src_table, e.n FROM tmp3_merge_ents e, cfg
  WHERE e.n <= cfg.chunk_rows
),
large_ents AS (
  SELECT e.src_table, e.n,
         GREATEST(1, (e.n + cfg.chunk_rows - 1) // cfg.chunk_rows) AS n_parts
  FROM tmp3_merge_ents e, cfg
  WHERE e.n > cfg.chunk_rows
),
small_jobs AS (
  SELECT s.src_table, s.n, 1::BIGINT AS n_parts, 0::BIGINT AS part,
         ((sum(s.n) OVER (ORDER BY s.n DESC, s.src_table) - s.n)
           // (SELECT chunk_rows FROM cfg)) AS job_id
  FROM small_ents s
),
large_jobs AS (
  SELECT l.src_table, l.n, l.n_parts, i.part,
         1000000000 + row_number() OVER (ORDER BY l.src_table, i.part) AS job_id
  FROM large_ents l
  JOIN (SELECT unnest(range(64)) AS part) i ON i.part < l.n_parts
)
SELECT job_id, src_table, n, n_parts, part FROM small_jobs
UNION ALL
SELECT job_id, src_table, n, n_parts, part FROM large_jobs;

SELECT 'слияние пачками' AS шаг, count(DISTINCT job_id) AS пачек,
       count(*) AS назначений,
       (SELECT chunk_rows FROM tmp3_merge_cfg LIMIT 1) AS порция,
       max(n) AS макс_сущность
FROM tmp3_merge_jobs;

SELECT stmt FROM (
  -- 🔴 ПАЧКА В ТРАНЗАКЦИИ: BEGIN первым statement-ом каждой пачки, COMMIT (ord=90)
  -- после maps-UPDATE. При ошибке любого statement-а пачки ON_ERROR_STOP рвёт
  -- сессию — незакрытая транзакция откатывается движком целиком, смешанного
  -- состояния «emb обнулён, контент старый» не остаётся.
  SELECT job_id, 0 AS ord, 'BEGIN;' AS stmt
  FROM (SELECT DISTINCT job_id FROM tmp3_merge_jobs) x
  UNION ALL
  -- 🔴 emb В MERGE-UPDATE НЕ ТРОГАЕМ: `emb = CASE … THEN t.emb ELSE NULL END`
  -- над FLOAT[1024] движком не реализован («Unimplemented type for case
  -- expression: FLOAT[1024]», живой стоп okna 08.09 — код впервые дошёл до
  -- исполнения). Тот же обход, что в restore-drill 06.09: вместо CASE/COALESCE
  -- над массивом — ДВА UPDATE. Обнуление — отдельной волной ord=1 выше (в
  -- транзакции пачки):
  -- контент изменился И общая часть карты различна → emb = NULL (шаг 5
  -- досчитает); иначе emb строки-цели сохраняется MERGE-ом нетронутым.
  -- 🔴 ВОЛНА ord=1 — ОБНУЛЕНИЕ emb ДО MERGE, а не после: прежний CASE сравнивал
  -- СТАРЫЙ doc строки корпуса с новым (bmap_common_eq(t.doc, s.doc) в MERGE
  -- вычисляется до UPDATE). После MERGE c.doc уже новый (= s.doc) и сравнение
  -- всегда true — emb не обнулялся бы никогда. До MERGE c.doc/c.content_hash
  -- ещё старые — семантика CASE воспроизведена точно.
  SELECT job_id, 1 AS ord,
         'UPDATE search_corpus c SET emb = NULL FROM tmp3_corpus t WHERE t.src_table = c.src_table AND t.row_key = c.row_key AND t.content_hash IS DISTINCT FROM c.content_hash AND NOT corpus_bmap_common_eq(corpus_doc_bmap(c.doc), corpus_doc_bmap(t.doc)) AND t.src_table IN ('
         || ins
         || ')'
         || CASE WHEN n_parts = 1 THEN ''
            ELSE ' AND (hash(t.row_key) % ' || n_parts || ') = ' || part END
         || ';' AS stmt
  FROM (
    SELECT job_id,
           string_agg(quote_literal(src_table), ', ') AS ins,
           max(n_parts) AS n_parts,
           min(part) AS part
    FROM tmp3_merge_jobs GROUP BY job_id
  ) g
  UNION ALL
  SELECT job_id, 2,
         'MERGE INTO search_corpus AS t USING (SELECT s.* FROM tmp3_corpus s WHERE s.src_table IN ('
         || ins
         || ')'
         || CASE WHEN n_parts = 1 THEN ''
            ELSE ' AND (hash(s.row_key) % ' || n_parts || ') = ' || part END
         || ') AS s ON t.src_table = s.src_table AND t.row_key = s.row_key WHEN MATCHED AND t.content_hash IS DISTINCT FROM s.content_hash THEN UPDATE SET doc = s.doc, refs = s.refs, doc_hash = s.doc_hash, content_hash = s.content_hash, nums = s.nums, flags = s.flags, doc_date = s.doc_date, refs_map = s.refs_map WHEN NOT MATCHED THEN INSERT (src_table, row_key, doc, refs, doc_hash, content_hash, nums, flags, doc_date, refs_map, emb) VALUES (s.src_table, s.row_key, s.doc, s.refs, s.doc_hash, s.content_hash, s.nums, s.flags, s.doc_date, s.refs_map, NULL);' AS stmt
  FROM (
    SELECT job_id,
           string_agg(quote_literal(src_table), ', ') AS ins,
           max(n_parts) AS n_parts,
           min(part) AS part
    FROM tmp3_merge_jobs GROUP BY job_id
  ) g
  UNION ALL
  SELECT job_id, 3,
         'UPDATE search_corpus c SET nums = t.nums, flags = t.flags, doc_date = t.doc_date, refs_map = t.refs_map FROM tmp3_corpus t WHERE t.src_table = c.src_table AND t.row_key = c.row_key AND (c.nums IS DISTINCT FROM t.nums OR c.flags IS DISTINCT FROM t.flags OR c.doc_date IS DISTINCT FROM t.doc_date OR c.refs_map IS DISTINCT FROM t.refs_map) AND t.src_table IN ('
         || ins
         || ')'
         || CASE WHEN n_parts = 1 THEN ''
            ELSE ' AND (hash(t.row_key) % ' || n_parts || ') = ' || part END
         || ';'
  FROM (
    SELECT job_id,
           string_agg(quote_literal(src_table), ', ') AS ins,
           max(n_parts) AS n_parts,
           min(part) AS part
    FROM tmp3_merge_jobs GROUP BY job_id
  ) g
  UNION ALL
  -- 🔴 ПАЧКА В ТРАНЗАКЦИИ (армия 08.09): обнуление emb и MERGE — отдельные
  -- statement-ы; без BEGIN/COMMIT ошибка MERGE ПОСЛЕ успешного обнуления
  -- оставляла бы emb=NULL при ещё старом контенте (дырка до перезапуска).
  -- Multi-statement transactions — штатно (sql/statements/transactions).
  SELECT job_id, 90, 'COMMIT;' AS stmt
  FROM (SELECT DISTINCT job_id FROM tmp3_merge_jobs) x
  UNION ALL
  SELECT job_id, 95, 'SELECT checkpoint();' AS stmt
  FROM (SELECT DISTINCT job_id FROM tmp3_merge_jobs) x
) z ORDER BY job_id, ord
\gexec

-- Исчезнувшие строки удаляет БАЗА одним запросом — и только по сущностям, которые в этот
-- раз ДЕЙСТВИТЕЛЬНО собрались. Прежний фильтр по `tmp3_src` был тавтологией: `tmp3_src`
-- сам строится из корпуса, поэтому «защита» покрывала весь корпус целиком.
DELETE FROM search_corpus c
WHERE c.src_table IN (SELECT DISTINCT src_table FROM tmp3_corpus)
  AND NOT EXISTS (SELECT 1 FROM tmp3_corpus t
                  WHERE t.src_table = c.src_table AND t.row_key = c.row_key);

-- Сущность, ВЫБЫВШАЯ ИЗ ИСТОЧНИКОВ целиком (переименована, признана тенью регистра и
-- исключена), оставляет свои строки сиротами: `DELETE` выше их не трогает — их нет в
-- новом наборе, а `IN (… tmp3_corpus)` их и не покрывает. [замер 28.07] так после отсева
-- теней `_recordtype` в корпусе осталось 324 лишних строки, и финальная сверка упала.
-- Убираем по контракту: строка, чьего источника больше нет в перечне, в корпусе не нужна.
DELETE FROM search_corpus c
WHERE NOT EXISTS (SELECT 1 FROM search_sources s WHERE s.src_table = c.src_table);

-- ============ 1-гис. ПЕРЕНОС ВЕКТОРОВ ПО КАРТЕ (О4) ============
-- Новые строки вошли с emb=NULL (массив FLOAT[1024] пачкой через MERGE-INSERT
-- роняет сборку 26.07.3 — Vector::SetSize; живой стоп 31.08). Перенос —
-- отдельными UPDATE-пакетами: массивы пакетом 1000 строк движок несёт
-- (замер: UPDATE 200 строк с emb — ок). Пакеты нумеруем один раз.
CREATE OR REPLACE TABLE tmp3_merge_emb_xfer_n AS
SELECT row_number() OVER (ORDER BY src_table, row_key) AS n, *
FROM tmp3_merge_emb_xfer;

SELECT 'UPDATE search_corpus SET emb = x.emb FROM tmp3_merge_emb_xfer_n x '
       || 'WHERE search_corpus.src_table = x.src_table AND search_corpus.row_key = x.row_key '
       || 'AND search_corpus.emb IS NULL AND x.n >= ' || (b * 1000)
       || ' AND x.n < ' || ((b + 1) * 1000) || ';'
FROM (SELECT i AS b FROM range(0, (SELECT ceil(count(*) / 1000.0)::BIGINT
                                   FROM tmp3_merge_emb_xfer_n)) t(i)) z
\gexec

SELECT checkpoint();

-- ============ 2-бис. ДАТА СОБЫТИЯ У ТАБЛИЧНОЙ ЧАСТИ ============
-- `doc_date` — когда случился факт. Date/Period платформы стоит на шапке; у строк
-- табличной части колонки нет, и `doc_date` оставался NULL. Фильтр ответа сравнивает
-- именно его — при 100 % пустых дат `rows` пуст и `kind=no_data` срабатывал ДО счёта
-- `undated`. Видимость потери ≠ тождество события (п. 13).
--
-- Своя дата на строке не затирается (`ch.doc_date IS NULL`). Родитель — из
-- `search_tables.parent`. Контракт ключа тот же, что `children_by_parent` в
-- `serene_ask.py`: `split_part(child.row_key,'|',1) = parent.row_key`.
-- Штатно: UPDATE FROM other table (доки sql/statements/update#update-from-other-table).
-- Цель и источник — одна таблица: на 26.07.3 `UPDATE ch FROM search_corpus par`
-- на 441k строках рвёт соединение за 2 с (замер 14.08 okna). Доки «Same Table»
-- дают correlated subquery; живой путь — материализовать источник в ДРУГУЮ
-- таблицу, затем UPDATE FROM неё. `-c` несколько команд DDL не видит;
-- `psql -f` в одном файле — видит. Вектор не сбрасывается.
--
-- Инкремент: дети родителей, у которых в этом такте сменилась дата шапки
-- (родитель в `tmp3_build`), и у которых своей колонки Date/Period нет
-- (нет строки в `tmp3_datecol`). Иначе правка Date документа не доедет до строк.
-- Доки: sql/statements/update#update-from-other-table
CREATE OR REPLACE TABLE tmp3_child_date AS
SELECT ch.src_table, ch.row_key, par.doc_date
  FROM search_corpus AS ch, search_tables AS m, search_corpus AS par
 WHERE m.src_table = ch.src_table
   AND m.parent IS NOT NULL
   AND par.src_table = m.parent
   AND par.row_key = split_part(ch.row_key, '|', 1)
   AND par.doc_date IS NOT NULL
   AND (
        ch.doc_date IS NULL
     OR (
          NOT EXISTS (SELECT 1 FROM tmp3_datecol d WHERE d.tbl = ch.src_table)
          AND EXISTS (SELECT 1 FROM tmp3_build b WHERE b.tbl = par.src_table)
          AND ch.doc_date IS DISTINCT FROM par.doc_date
        )
   );
UPDATE search_corpus AS ch
   SET doc_date = t.doc_date
  FROM tmp3_child_date AS t
 WHERE ch.src_table = t.src_table
   AND ch.row_key = t.row_key;
DROP TABLE tmp3_child_date;

-- ============ 3. ПУБЛИКАЦИЯ ПОИСКУ ============
-- Именно REFRESH_INDEX (один индекс), а НЕ REFRESH_TABLE: последний на таблице с вектором
-- дал 34 ГБ и смерть движка (замер 27.07).
--
-- 🔴 ЭТУ КОМАНДУ НЕЛЬЗЯ ЗАВОДИТЬ ВНУТРЬ ТРАНЗАКЦИИ, И ВЕСЬ ФАЙЛ НЕЛЬЗЯ ОБОРАЧИВАТЬ В
-- ОДИН `BEGIN … COMMIT`. [замер 28.07] обновление индекса в той же транзакции, что и
-- запись, — ТИХИЙ no-op: ошибки нет, а строка поиску не видна.
--   `INSERT` + `REFRESH_INDEX` одной транзакцией → найдено 0
--   те же команды разными вызовами            → найдено 1
-- Именно поэтому запись выше закрыта своим `COMMIT`, а публикация идёт отдельно.
-- Без публикации индекс какое-то время отдаёт УДАЛЁННЫЕ строки и старый текст, а
-- `count(*)` и показ расходятся: строка считается, но не показывается.
VACUUM (REFRESH_INDEX) search_idx;

-- ============ 4. ПРОВЕРЯЕМЫЙ ИТОГ ============
-- Не «напечатали числа», а «сверили и упали, если не сошлось»: после переноса множество
-- строк корпуса обязано совпасть с собранным.
--
-- 🔴 СВЕРЯЕМ ПО ПЕРЕСОБРАННЫМ СУЩНОСТЯМ, А НЕ ПО ВСЕМУ КОРПУСУ. С 06.08 сборка идёт по
-- изменившемуся, и `tmp3_corpus` законно содержит только их: сравнение «весь корпус против
-- собранного» тогда сравнивает 623 565 с нулём и валит такт на ровном месте — [замер
-- 06.08] так и произошло. Смысл проверки при этом сохраняется полностью: у КАЖДОЙ
-- пересобранной сущности число строк в корпусе обязано совпасть с собранным, а
-- непересобранные к этому переносу отношения не имеют.
SELECT CASE WHEN count(*) > 0
       THEN error('corpus_merge: после переноса разошлось число строк у сущностей: '
                  || string_agg(src_table || ' (' || в_корпусе || ' против ' || собрано || ')',
                                ', ')) END
FROM (SELECT t.src_table,
             (SELECT count(*) FROM search_corpus c WHERE c.src_table = t.src_table) AS в_корпусе,
             count(*) AS собрано
      FROM tmp3_corpus t GROUP BY t.src_table)
WHERE в_корпусе <> собрано;

-- ============ 5. ОТМЕТКИ ИЗМЕНЁННОГО ПОТРЕБЛЯЮТСЯ — И ТОЛЬКО ПЕРЕСОБРАННЫЕ ============
-- На пакетном контуре отметки пишет apply (дописывая), а съедает их сборка — ровно те,
-- что вошли в этот проход (`tmp3_build` зафиксирован в начале `corpus_build`). Отметка,
-- поставленная apply ВО ВРЕМЯ сборки по уже пройденному источнику, здесь не удаляется:
-- её данные этот проход не читал, и пересоберёт следующий такт. Прежде отметки не
-- потреблял никто (синку это не нужно — он переписывает список целиком каждый прогон),
-- и на юните они копились без дела при мёртвом инкременте (замер okna 14.08).
DELETE FROM search_changed_sources
WHERE src_table IN (SELECT tbl FROM tmp3_build);

-- Фактически перенесённые в этом проходе. Такт-пропуск сюда не доходит.
UPDATE search_tables SET last_built_at = now()
WHERE src_table IN (SELECT tbl FROM tmp3_build);

SELECT 'корпус' AS шаг, count(*) AS строк, count(DISTINCT src_table) AS сущностей,
       count(*) FILTER (WHERE emb IS NULL) AS ждут_вектора,
       count(*) FILTER (WHERE nums IS NOT NULL AND len(map_keys(nums)) > 0) AS строк_с_величинами
FROM search_corpus;
