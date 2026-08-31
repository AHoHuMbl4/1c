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
-- Вектор принадлежит бизнес-контенту, не row_key (О4): перед вставкой новые
-- строки стыкуются со старыми по refs; emb переносится, если общие колонки
-- doc-текста совпали (новые колонки формы игнорируются). Иначе emb=NULL —
-- очередь bulk (EMBED_BULK §5/§9) досчитает только реально изменившиеся.
-- Доки: MERGE INTO; sql/functions/map; sql/functions/text#string_split;
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
-- «уйдёт» частичной потери.
CREATE OR REPLACE TABLE tmp3_merge_edited_delta AS
SELECT u.src_table, count(*)::BIGINT AS правок
FROM tmp3_merge_unmatched u
JOIN search_corpus c ON c.src_table = u.src_table AND c.row_key = u.row_key
WHERE EXISTS (SELECT 1 FROM tmp3_corpus t
              WHERE t.src_table = u.src_table AND t.refs = c.refs)
GROUP BY 1;

CREATE OR REPLACE TABLE tmp3_merge_unmatched AS
SELECT c.src_table, c.row_key
FROM search_corpus c
WHERE c.src_table IN (SELECT DISTINCT src_table FROM tmp3_corpus)
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
                    AND split_part(c.row_key, '#', 1) <> '')
  -- Перепроведение: тот же хвост ключа после Recorder (Period|измерения), другой
  -- Recorder уже в tmp3 — не orphan. Только если Period в объявленном ключе:
  -- для {Recorder,Recorder_Type,LineNumber} хвост = LineNumber, совпадение ложное.
  AND NOT EXISTS (SELECT 1 FROM tmp3_corpus t
                  WHERE t.src_table = c.src_table
                    AND substr(t.row_key, length(split_part(t.row_key, '|', 1)) + 2)
                      = substr(c.row_key, length(split_part(c.row_key, '|', 1)) + 2)
                    AND split_part(t.row_key, '|', 1) <> split_part(c.row_key, '|', 1)
                    AND split_part(c.row_key, '|', 1) <> ''
                    AND EXISTS (SELECT 1 FROM tmp3_key k
                                WHERE k.entity = lower(c.src_table)
                                  AND list_contains(k.key_cols, 'Period')));

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

SELECT CASE WHEN count(*) > 0
       THEN error('corpus_merge: новая сборка меньше старой у сущностей: '
                  || string_agg(src_table || ' (' || стало || ' против ' || было || ')',
                                ', ')) END
FROM tmp3_merge_ent_guard
WHERE было > 0 AND стало < было;

-- Частичный уход при росте сборки: проверяем, жив ли split_part(row_key,'|',1)
-- в колонке Recorder витрины (имя платформы 1С, не домен). Все живы — коллапс
-- ключа, запись в search_quality; мёртвый Recorder или нет колонки — STOP ниже.
CREATE OR REPLACE TABLE tmp3_merge_collapse_cand AS
SELECT src_table, было, стало, уйдёт
FROM tmp3_merge_ent_guard
WHERE уйдёт > 0 AND уйдёт < было AND стало > было;

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
CREATE OR REPLACE TABLE tmp3_merge_delta_rec AS
SELECT u.src_table, u.row_key, split_part(u.row_key, '|', 1) AS rec,
       CASE WHEN split_part(u.row_key, '|', 2) <> ''
            THEN lower(regexp_replace(split_part(u.row_key, '|', 2), '^.*\.', ''))
            ELSE (SELECT st.written_by FROM search_tables st
                  WHERE st.src_table = u.src_table) END AS doc_tbl
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

CREATE OR REPLACE TABLE tmp3_merge_doc_alive (doc_tbl VARCHAR, rec VARCHAR, alive BIGINT);

PREPARE p_doc_alive AS
INSERT INTO tmp3_merge_doc_alive
SELECT $1::VARCHAR, d."ref_key", count(*)
FROM query_table($1) d
WHERE d."ref_key" IN (SELECT r.rec FROM tmp3_merge_delta_rec r WHERE r.doc_tbl = $1)
  -- «Жив» = присутствует и НЕ помечен на удаление: annulled/deleted документы
  -- движений в регистрах не пишут, их отсутствие — не дефект транспорта.
  -- deletionmark — платформенное поле, есть у всех документных таблиц витрины.
  AND lower(try_cast(d."deletionmark" AS VARCHAR)) IS DISTINCT FROM 'true'
GROUP BY d."ref_key";

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

SELECT CASE WHEN count(*) > 0
       THEN error('corpus_merge: документ жив, движений в регистре нет (дефект транспорта): '
                  || string_agg(src_table || ' recorder=' || rec || ' (' || n || ')',
                                ', ' ORDER BY src_table, rec)) END
FROM tmp3_merge_transport_defect;

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
  AND NOT EXISTS (SELECT 1 FROM tmp3_merge_key_deleted_delta k WHERE k.src_table = g.src_table);

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

-- Время последнего переноса сущности в поисковый слой. Пишется ниже по фактически
-- перенесённым (`tmp3_build`); такт-пропуск колонку не трогает.
ALTER TABLE search_tables ADD COLUMN IF NOT EXISTS last_built_at TIMESTAMP;

-- ============ 1-бис. ПЕРЕНОС ВЕКТОРОВ ПРИ REWRITE-ВОЛНЕ (О4) ============
-- Текст doc = «сущность | колонка: значение | …» (строит corpus_build). Карта
-- бизнес-полей — пары с «: »; префикс без двоеточия отбрасывается. Стыковка
-- пар — по refs (стабильна при смене формы, ломается при смене значений ссылок).
-- Дубли refs с обеих сторон → пара не ищется (безопаснее, чем чужой emb).
-- Доки: sql/functions/map#map_from_entries; list_intersect; map_extract_value;
-- sql/functions/text#string_split; sql/statements/create_macro.
CREATE OR REPLACE MACRO corpus_doc_bmap(doc) AS (
  CASE WHEN len(list_filter(string_split(coalesce(doc, ''), ' | '),
                            p -> position(': ' IN p) > 0)) = 0
       THEN MAP{}::MAP(VARCHAR, VARCHAR)
       ELSE map_from_entries(
              list_transform(
                list_filter(string_split(doc, ' | '),
                            p -> position(': ' IN p) > 0),
                p -> {'key': split_part(p, ': ', 1),
                      'value': substr(p, length(split_part(p, ': ', 1)) + 3)}
              )
            )
  END
);

CREATE OR REPLACE MACRO corpus_bmap_common_eq(a, b) AS (
  len(list_intersect(map_keys(a), map_keys(b))) > 0
  AND len(list_filter(
        list_intersect(map_keys(a), map_keys(b)),
        k -> map_extract_value(a, k) IS DISTINCT FROM map_extract_value(b, k)
      )) = 0
);

CREATE OR REPLACE TABLE tmp3_merge_emb_old AS
SELECT src_table, refs, any_value(emb) AS emb, any_value(corpus_doc_bmap(doc)) AS bmap
FROM search_corpus
WHERE src_table IN (SELECT src_table FROM tmp3_merge_rewrite_wave)
  AND refs IS NOT NULL AND refs <> ''
  AND emb IS NOT NULL
GROUP BY src_table, refs
HAVING count(*) = 1;

CREATE OR REPLACE TABLE tmp3_merge_emb_new AS
SELECT src_table, row_key, refs, corpus_doc_bmap(doc) AS bmap
FROM tmp3_corpus
WHERE src_table IN (SELECT src_table FROM tmp3_merge_rewrite_wave)
  AND refs IS NOT NULL AND refs <> ''
QUALIFY count(*) OVER (PARTITION BY src_table, refs) = 1;

CREATE OR REPLACE TABLE tmp3_merge_emb_xfer AS
SELECT n.src_table, n.row_key, o.emb
FROM tmp3_merge_emb_new n
INNER JOIN tmp3_merge_emb_old o USING (src_table, refs)
WHERE corpus_bmap_common_eq(n.bmap, o.bmap);

DELETE FROM search_quality WHERE k LIKE 'entity_emb_xfer:%';
INSERT INTO search_quality
SELECT 'entity_emb_xfer:' || src_table, count(*)::BIGINT,
       'векторов перенесено без пересчёта (общие колонки doc совпали)'
FROM tmp3_merge_emb_xfer
GROUP BY 1;

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
CREATE TABLE IF NOT EXISTS tmp3_merge_cfg (chunk_rows BIGINT);
INSERT INTO tmp3_merge_cfg (chunk_rows)
SELECT 1000000 WHERE (SELECT count(*) FROM tmp3_merge_cfg) = 0;
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
  SELECT job_id, 1 AS ord,
         'MERGE INTO search_corpus AS t USING (SELECT s.* FROM tmp3_corpus s WHERE s.src_table IN ('
         || ins
         || ')'
         || CASE WHEN n_parts = 1 THEN ''
            ELSE ' AND (hash(s.row_key) % ' || n_parts || ') = ' || part END
         || ') AS s ON t.src_table = s.src_table AND t.row_key = s.row_key WHEN MATCHED AND t.doc_hash IS DISTINCT FROM s.doc_hash THEN UPDATE SET doc = s.doc, refs = s.refs, doc_hash = s.doc_hash, nums = s.nums, flags = s.flags, doc_date = s.doc_date, refs_map = s.refs_map, emb = NULL WHEN NOT MATCHED THEN INSERT (src_table, row_key, doc, refs, doc_hash, nums, flags, doc_date, refs_map, emb) VALUES (s.src_table, s.row_key, s.doc, s.refs, s.doc_hash, s.nums, s.flags, s.doc_date, s.refs_map, NULL);' AS stmt
  FROM (
    SELECT job_id,
           string_agg(quote_literal(src_table), ', ') AS ins,
           max(n_parts) AS n_parts,
           min(part) AS part
    FROM tmp3_merge_jobs GROUP BY job_id
  ) g
  UNION ALL
  SELECT job_id, 2,
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
  SELECT job_id, 3, 'SELECT checkpoint();'
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
