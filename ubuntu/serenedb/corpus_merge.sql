\timing on
\set ON_ERROR_STOP on

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
SELECT CASE WHEN coalesce((SELECT max(ts) FROM tmp3_run), TIMESTAMP '1970-01-01')
                 < now() - INTERVAL '6 hours'
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
-- Отпечаток отсекается по СВОЕМУ ЖЕ формату (`sha1` — ровно 40 шестнадцатеричных знаков),
-- а не по первому `#`: составной ключ склеен через `|`, и в данных 1С `#` встречается.
SELECT CASE WHEN (SELECT count(*) FROM search_corpus) > 0
             AND уйдёт::DOUBLE / (SELECT count(*) FROM search_corpus) > 0.1
       THEN error('corpus_merge: удаление снесло бы ' || уйдёт || ' объектов из '
                  || (SELECT count(*) FROM search_corpus) || ' — остановлено') END
FROM (SELECT count(*) AS уйдёт FROM search_corpus c
      WHERE c.src_table IN (SELECT DISTINCT src_table FROM tmp3_corpus)
        -- Два РАЗДЕЛЬНЫХ анти-соединения, а не одно `IN (ключ, обрезанный ключ)`:
        -- список внутри `IN` лишает движок равенства, и он уходит в перебор. [замер 30.07]
        -- одним `IN` запрос не уложился в две минуты на 623 565 строках; двумя — 0,2 с.
        -- Второе проверяется только у тех строк, что не нашлись по своему ключу, поэтому
        -- регулярное выражение считается для единиц, а не для всего корпуса.
        AND NOT EXISTS (SELECT 1 FROM tmp3_corpus t
                        WHERE t.src_table = c.src_table AND t.row_key = c.row_key)
        AND NOT EXISTS (SELECT 1 FROM tmp3_corpus t
                        WHERE t.src_table = c.src_table
                          AND t.row_key = regexp_replace(c.row_key, '#[0-9a-f]{40}$', ''))
        -- Смена формы ключа (в ключ регистра дописали LineNumber) — не потеря
        -- объекта: GUID регистратора/ссылки — первый кусок ключа, склеенного `|`.
        AND NOT EXISTS (SELECT 1 FROM tmp3_corpus t
                        WHERE t.src_table = c.src_table
                          AND split_part(t.row_key, '|', 1) = split_part(c.row_key, '|', 1)
                          AND split_part(c.row_key, '|', 1) <> ''));

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

-- Время последнего переноса сущности в поисковый слой. Пишется ниже по фактически
-- перенесённым (`tmp3_build`); такт-пропуск колонку не трогает.
ALTER TABLE search_tables ADD COLUMN IF NOT EXISTS last_built_at TIMESTAMP;

-- ============ 2. ЗАПИСЬ — ОДНОЙ ТРАНЗАКЦИЕЙ ============
-- [замер] транзакции в этом движке работают: `BEGIN; MERGE; UPDATE; DELETE; ROLLBACK`
-- откатывает всё до строки. Без транзакции обрыв посередине оставлял корпус в состоянии,
-- которое ничем не помечено и которое следующий прогон НЕ чинит: отпечатки уже совпали,
-- а векторов нет.
BEGIN;

-- Условие по отпечатку обязано остаться: без него молча пересчитываются все строки.
-- `IS DISTINCT FROM`, а не `<>`: при `NULL` в отпечатке сравнение дало бы `NULL`, ветка
-- не сработала бы, и строка навсегда осталась бы со старым текстом при живом ключе.
-- `emb = NULL` у изменившихся — честная отметка «вектор не посчитан», видимая запросом;
-- оставленный старый вектор при новом тексте был бы тихим расхождением смысла и текста.
MERGE INTO search_corpus AS t
USING tmp3_corpus AS s
ON t.src_table = s.src_table AND t.row_key = s.row_key
WHEN MATCHED AND t.doc_hash IS DISTINCT FROM s.doc_hash THEN
     UPDATE SET doc = s.doc, refs = s.refs, doc_hash = s.doc_hash,
                nums = s.nums, flags = s.flags, doc_date = s.doc_date,
                refs_map = s.refs_map, emb = NULL
WHEN NOT MATCHED THEN
     INSERT (src_table, row_key, doc, refs, doc_hash, nums, flags, doc_date, refs_map, emb)
     VALUES (s.src_table, s.row_key, s.doc, s.refs, s.doc_hash, s.nums, s.flags, s.doc_date, s.refs_map, NULL);

-- Величины и дата не входят в отпечаток, поэтому строки с неизменившимся текстом `MERGE`
-- не трогает — а обновить их нужно. Вектор здесь не сбрасывается: текст тот же.
-- 🔴 `doc_date` здесь не случайно. В текст дата попадает без времени (`substr(val,1,10)`),
-- поэтому смена времени внутри суток отпечаток НЕ меняет: `MERGE` строку пропускает, и
-- без этой строки `doc_date` оставался бы старым навсегда. [замер] 446 строк корпуса
-- несут дату с ненулевым временем, то есть попадают в этот класс.
-- 🔴 `flags` ОБЯЗАНЫ БЫТЬ ЗДЕСЬ, а не только в `MERGE`. Булев реквизит в отпечаток не
-- входит (он часть текста, но карта строится отдельно), поэтому у строк с неизменившимся
-- текстом `MERGE` не срабатывает вовсе. При первом такте после `ADD COLUMN` отпечатки
-- совпадают У ВСЕГО корпуса — без этой строки карта осталась бы пустой навсегда, и
-- отбор «не папка» молча возвращал бы всё подряд.
UPDATE search_corpus c SET nums = t.nums, flags = t.flags, doc_date = t.doc_date,
                           refs_map = t.refs_map
FROM tmp3_corpus t
WHERE t.src_table = c.src_table AND t.row_key = c.row_key
  AND (c.nums IS DISTINCT FROM t.nums OR c.flags IS DISTINCT FROM t.flags
       OR c.doc_date IS DISTINCT FROM t.doc_date
       OR c.refs_map IS DISTINCT FROM t.refs_map);

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

COMMIT;

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
