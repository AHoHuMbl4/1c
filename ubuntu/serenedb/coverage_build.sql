\timing on
\set ON_ERROR_STOP on

-- ПЕРЕПИСЬ ПОЛНОТЫ: сколько данных 1С дошло до поиска и где потерялось.
--
-- Это исполнение пункта 13 TARGET.md. Требование не «не терять» — терять иногда
-- приходится, — а «потеря обязана быть ВИДНА». Молчаливая потеря приравнена контрактом
-- к неверному ответу.
--
-- [замер 28.07, до этой работы] в 1С объявлено 103 958 строк по 235 сущностям, до
-- корпуса дошло 97 965 по 226. Потеряно 5 993 строки и девять сущностей, и у всех
-- девяти поле `problem` было ПУСТО. Среди потерянных — `AccountingRegister_Хозрасчетный`,
-- главная книга: на вопрос про обороты по счёту отвечать нечем, и клиенту не сказано.
--
-- Считается ЦЕЛИКОМ ВНУТРИ ДВИЖКА (п. 20): ни одна строка не покидает базу.

-- ============ 1. СКОЛЬКО СТРОК В ВИТРИНЕ ============
-- Тем же приёмом, что `res_seen` в resolver_build.sql: `query_table($1)` берёт имя
-- литералом, поэтому список таблиц обходится генерацией команд, а не циклом в питоне.
-- [замер] 226 таблиц — меньше секунды.
CREATE OR REPLACE TABLE cov_mart (tbl VARCHAR, n_rows BIGINT);
PREPARE p_cov AS INSERT INTO cov_mart SELECT $1::VARCHAR, count(*) FROM query_table($1);
SELECT 'EXECUTE p_cov(' || quote_literal(table_name) || ');'
FROM duckdb_tables()
-- 🔴 ИМЯ БАЗЫ НЕ ЗАШИТО. Прежде здесь стояло `database_name = 'postgres'` — имя нашей
-- базы на ЭТОМ стенде. На установке, где база SereneDB названа иначе, отбор давал бы
-- НОЛЬ источников, и корпус собрался бы пустым молча. [замер 28.07] найдено при
-- подготовке теста на второй базе: `current_database()` в `ut_test` вернул `ut_test`.
WHERE database_name = current_database()
  AND EXISTS (SELECT 1 FROM tmp3_ent e WHERE e.entity = lower(table_name))
\gexec

-- ============ 2. ЦЕПОЧКА ПО КАЖДОЙ СУЩНОСТИ ============
-- 🔴 lower() ОБЯЗАТЕЛЕН. `base_profile.entity` записан в исходном регистре
-- (`Catalog_ПоляФормСтатистики`), а имена таблиц витрины и `search_sources` — в нижнем.
-- Соединение без `lower()` не сходится НИ ОДНОЙ строкой и выглядит как тотальная потеря:
-- я на этом споткнулся сегодня и чуть не записал 235 сущностей в пропавшие.
CREATE OR REPLACE TABLE search_coverage AS
WITH ent AS (
  -- Слева — то, что ОБЪЯВЛЕНО платформой, а не то, что мы сумели прочитать. Иначе
  -- перепись считала бы полноту по себе самой и всегда показывала бы «всё на месте».
  -- 🔴 ТЕНИ РЕГИСТРОВ (`_RecordType`/`_RowType`) ИСКЛЮЧАЮТСЯ. Плоская тень `<Регистр>_
  -- RecordType` объявлена в `$metadata` и несёт те же движения, что обёртка, но в корпус
  -- идёт ОБЁРТКА (`corpus_build.sql` тени отсекает). Без этого исключения перепись
  -- считала тень отдельной сущностью и кричала «280 строк не собралось», хотя данные
  -- целы в обёртке — [замер 28.07] так `cov_rows_lost` показывал 326 при реальной
  -- потере 2. Ложная тревога прячет настоящую: считаем по тем же сущностям, что и корпус.
  SELECT e.entity AS ent, b.rows AS in_1c, b.problem
  FROM tmp3_ent e
  LEFT JOIN base_profile b ON lower(b.entity) = e.entity
  WHERE e.entity NOT LIKE '%\_recordtype' ESCAPE '\'
    AND e.entity NOT LIKE '%\_rowtype'    ESCAPE '\'),
 mart AS (SELECT lower(tbl) AS ent, n_rows FROM cov_mart),
 corp AS (SELECT src_table AS ent, count(*) AS n,
                 count(*) FILTER (WHERE emb IS NOT NULL) AS n_emb
          FROM search_corpus GROUP BY 1),
 idx  AS (SELECT src_table AS ent, count(*) AS n FROM search_idx GROUP BY 1)
SELECT ent AS entity,
       coalesce(e.in_1c, 0)      AS в_1С,
       coalesce(m.n_rows, 0)     AS в_витрине,
       coalesce(c.n, 0)          AS в_корпусе,
       coalesce(i.n, 0)          AS в_индексе,
       coalesce(c.n_emb, 0)      AS с_вектором,
       -- ============ 3. ПРИЧИНА — СТРУКТУРНО, А НЕ СПИСКОМ ИМЁН ============
       -- Порядок ветвей значим: он идёт по течению данных, поэтому называется ПЕРВОЕ
       -- место, где данные встали, а не последнее, где их нет.
       CASE
         WHEN e.in_1c = -1                       THEN 'закрыто правами в 1С'
         WHEN coalesce(e.in_1c, 0) = 0           THEN 'в 1С нет строк'
         WHEN m.n_rows IS NULL                   THEN 'не загрузилось из 1С'
         WHEN m.n_rows = 0                       THEN 'выгрузка пуста'
         WHEN coalesce(c.n, 0) = 0               THEN 'не собралось в корпус'
         -- 🔴 КОРПУС МЕНЬШЕ ВИТРИНЫ БЫВАЕТ ЗАКОННО. У ссылочного объекта (ключ
         -- `['Ref_Key']`) вложенная табличная часть развёрнута в витрине в несколько
         -- строк, а в корпусе объект — ОДНА строка. Сравнивать надо с числом ОБЪЕКТОВ,
         -- иначе [замер 30.07] 85 сущностей второй базы навсегда получат ложную пометку
         -- «собралось не полностью»: партнёров в витрине 216, в корпусе 164, и это верно.
         WHEN c.n < m.n_rows AND NOT coalesce(
                (SELECT k.key_cols = ['Ref_Key'] FROM tmp3_key k WHERE k.entity = e.ent),
                false)                           THEN 'собралось не полностью'
         -- 🔴 РАЗДУТИЕ НАЗЫВАЕТСЯ, А НЕ УМАЛЧИВАЕТСЯ. Прежде ветки «в витрине больше, чем
         -- в 1С» не было вовсе: владелец видел `cov_rows_1c` 507 500 против
         -- `cov_rows_search` 632 720 и никакого объяснения. По п. 13 это молчаливое
         -- ИСКАЖЕНИЕ, а не потеря, и потому опаснее: недостачу видно, а раздутый счётчик
         -- выглядит как нормальный ответ.
         -- Два случая различаются: у регистров `$count` считает регистраторы, а не
         -- движения — сравнению не подлежит; у ссылочного объекта лишние строки витрины
         -- это развёрнутая табличная часть.
         WHEN m.n_rows > e.in_1c AND coalesce(
                (SELECT k.key_cols = ['Ref_Key'] FROM tmp3_key k WHERE k.entity = e.ent),
                false)                           THEN 'витрина развёрнута по табличной части'
         WHEN m.n_rows > e.in_1c                  THEN 'регистр: $count считает регистраторы'
         WHEN coalesce(i.n, 0) < c.n             THEN 'не опубликовано в индекс'
         WHEN c.n_emb < c.n                      THEN 'нет вектора'
         ELSE NULL
       END AS причина
FROM ent e
LEFT JOIN mart m USING (ent)
LEFT JOIN corp c ON c.ent = e.ent
LEFT JOIN idx  i ON i.ent = e.ent;

-- 🔴 ПРАВА ВЫДАЮТСЯ ЗДЕСЬ ЖЕ. `CREATE OR REPLACE TABLE` снимает `GRANT`, и читающая
-- роль сервиса молча получает «нет доступа», неотличимое от «данных нет». Наступил на это
-- сегодня третий раз: перепись считалась верно, а бот на вопрос «что не загрузилось»
-- отвечал отказом (`HOW_NOT_TO §2.9`, `techContext` ловушка про GRANT).
GRANT SELECT ON search_coverage TO serene_ro;

-- 🔴 В `base_profile` причина НЕ ПИШЕТСЯ, хотя соблазн есть: поле `problem` там пусто у
-- всех девяти потерянных, и именно поэтому потеря выглядела как «так и задумано».
-- Но `serene_sync.py:109` делает `DROP TABLE base_profile` при каждом прогоне и пишет
-- её заново. Наша запись прожила бы до ближайшего синка и всё это время выглядела бы
-- постоянной — то есть мы завели бы ещё один документ, который уверенно врёт.
-- Хозяин `base_profile` — синк; перепись живёт в своей таблице и пересчитывается сама.

-- ============ 4. ИТОГ — ЧИСЛАМИ В БАЗУ ============
DELETE FROM search_quality WHERE k LIKE 'cov_%';
INSERT INTO search_quality
            SELECT 'cov_rows_1c',    sum(в_1С) FILTER (WHERE в_1С > 0),    'строк объявлено в 1С'
            FROM search_coverage
UNION ALL   SELECT 'cov_rows_search', sum(в_корпусе),                      'строк дошло до поиска'
            FROM search_coverage
UNION ALL   SELECT 'cov_rows_lost',  sum(в_1С - в_корпусе) FILTER (WHERE в_1С > в_корпусе),
                   'строк не дошло' FROM search_coverage
UNION ALL   SELECT 'cov_ent_lost',   count(*) FILTER (WHERE в_1С > 0 AND в_корпусе = 0),
                   'сущностей не дошло совсем' FROM search_coverage
UNION ALL   SELECT 'cov_ent_denied', count(*) FILTER (WHERE в_1С = -1),
                   'сущностей закрыто правами' FROM search_coverage
-- 🔴 БЕЗ ВЕКТОРА — С ПРИЧИНОЙ, А НЕ ПРОСТО ЧИСЛОМ. Решение владельца 29.07: служебным
-- сущностям вектор не нужен вовсе («да, не нужны они в векторе»). Это осознанное решение,
-- а не недоделка, и разница обязана быть видна: строка без вектора ПО РЕШЕНИЮ и строка
-- без вектора ПОТОМУ ЧТО НЕ УСПЕЛИ — разные вещи (п. 13).
--
-- Что при этом НЕ теряется: служебные сущности целиком в корпусе и в текстовом индексе,
-- то есть находятся по словам. Не находятся только «по смыслу» — а по смыслу замеры
-- времени и объекты «Удалить…» никто и не ищет.
UNION ALL   SELECT 'cov_noemb_service',
                   (SELECT count(*) FROM search_corpus c
                     WHERE c.emb IS NULL AND EXISTS (SELECT 1 FROM search_entity_class e
                           WHERE e.src_table = c.src_table AND e.cls = 'service')),
                   'строк без вектора ПО РЕШЕНИЮ: служебные, ищутся словами через индекс'
UNION ALL   SELECT 'cov_noemb_pending',
                   (SELECT count(*) FROM search_corpus c
                     WHERE c.emb IS NULL AND NOT EXISTS (SELECT 1 FROM search_entity_class e
                           WHERE e.src_table = c.src_table AND e.cls = 'service')),
                   'строк без вектора В ОЧЕРЕДИ: не служебные, вектор ещё считается';

SELECT k, v, note FROM search_quality WHERE k LIKE 'cov_%' ORDER BY k;

-- Поимённо — то, что не дошло. Без этого списка число «5 993» ничего не говорит о том,
-- на какие вопросы система теперь не ответит.
SELECT entity AS сущность, в_1С, в_витрине, в_корпусе, причина
FROM search_coverage
WHERE причина IS NOT NULL AND причина <> 'закрыто правами в 1С' AND в_1С > 0
ORDER BY в_1С - в_корпусе DESC
LIMIT 20;
