-- ПРОВЕРКА СВЯЗИ «КТО ПИШЕТ ЭТОТ ИСТОЧНИК» — бесплатно, детерминированно, без модели.
--
-- Связь заводит подготовка базы (`corpus_build.sql`, раздел 2-тер): у движений регистра
-- есть регистратор, и это единственный сигнал выбора сущности, который не является
-- названием. Здесь она проверяется двумя вопросами: сколько источников связь получили и
-- совпадает ли она с эталонными парами приёмки.
--
-- Запуск:
--   psql 'host=127.0.0.1 port=7890 user=postgres dbname=<база>' -f work/entity-choice/writer_link_check.sql
--
-- 🔴 Один прогон здесь ЗНАЧИТ ровно то, что показывает: связь — свойство данных, а не
-- ответа модели, поэтому разброса у неё нет. Разброс есть у поведения (`step4_bench.py`),
-- и там одного прогона мало (`HOW_NOT_TO §1.34`).

\pset border 2

-- 1. Числа подготовки: они же уходят в `search_quality` каждый такт.
SELECT k, v, note FROM search_quality WHERE k LIKE 'writer_%' ORDER BY k;

-- 2. Доля источников с регистратором, у которых связь нашлась. `writer_unresolved` — это
-- регистратор, которого нет среди источников: документ не загружен или закрыт правами.
SELECT count(*) FILTER (WHERE written_by IS NOT NULL)                       AS со_связью,
       count(*) FILTER (WHERE written_by IS NULL AND written_by_all IS NOT NULL) AS без_связи,
       round(median(written_by_share), 2)                                   AS медиана_доли,
       count(*) FILTER (WHERE written_by_share > 0.5)                       AS доля_больше_половины,
       count(*) FILTER (WHERE len(map_keys(written_by_all)) = 1)            AS пишет_один
FROM search_tables WHERE written_by_all IS NOT NULL;

-- 3. Расклад по доле преобладающего регистратора: видно, где связь однозначна, а где
-- регистр агрегирует разные документы и однозначного ответа нет по существу.
SELECT round(written_by_share, 1) AS доля_преобладающего, count(*) AS источников
FROM search_tables WHERE written_by IS NOT NULL GROUP BY 1 ORDER BY 1 DESC;

-- 4. Двадцать самых уверенных связей — глазами.
SELECT src_table, written_by, round(written_by_share, 3) AS доля,
       len(map_keys(written_by_all)) AS регистраторов
FROM search_tables WHERE written_by IS NOT NULL
ORDER BY written_by_share DESC, src_table LIMIT 20;

-- 5. ЭТАЛОННЫЕ ПАРЫ ПРИЁМКИ ЭТОЙ БАЗЫ (`work/entity-choice/SPEC_REGISTRAR_LINK.md` §1).
-- Это данные приёмки, а не код продукта: имена сущностей здесь так же законны, как в
-- `docs/ACCEPTANCE_UT.md`. На другой базе раздел просто вернёт ноль строк.
-- Ожидается: у регистра, который выбирался вместо документа, `written_by` = этот документ
-- (для табличной части эталона — её `parent`).
WITH эталон(регистр, документ) AS (
  VALUES ('accumulationregister_закупки',        'document_приобретениетоваровуслуг'),
         ('accumulationregister_заказыклиентов', 'document_заказклиента')
)
SELECT э.регистр, э.документ AS эталонный_документ, t.written_by AS связь,
       round(t.written_by_share, 3) AS доля,
       (t.written_by = э.документ) AS сошлось
FROM эталон э LEFT JOIN search_tables t ON t.src_table = э.регистр;
