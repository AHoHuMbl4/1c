\set ON_ERROR_STOP on

-- РАЗВЁРТЫВАНИЕ ОБЪЕКТОВ ПОИСКА С НУЛЯ. Идемпотентно: можно звать перед каждым тактом.
--
-- Зачем отдельный файл. Прежняя цепочка умела только ПОДДЕРЖИВАТЬ то, что уже есть:
-- `corpus_build.sql` брал список сущностей из существующего корпуса, `corpus_merge.sql`
-- начинался с `ALTER TABLE search_corpus`. На чистой машине клиента ни то, ни другое не
-- стартует, а после аварии 28.07 (корпус снесён) сборка не подняла бы ничего и
-- рапортовала бы «0 строк» с кодом успеха.
--
-- 🔴 Права выдаются ЗДЕСЬ ЖЕ. Пересозданная таблица теряет `GRANT`, и читающая роль
-- сервиса молча получает пустоту — бот отвечает «нет данных» при живом корпусе. Это
-- уже случилось (`HOW_NOT_TO §2.9`), и по журналу выглядело как отсутствие данных.

CREATE TABLE IF NOT EXISTS search_corpus (
  src_table VARCHAR, row_key VARCHAR, doc VARCHAR, refs VARCHAR, doc_hash VARCHAR,
  nums MAP(VARCHAR, DOUBLE), doc_date TIMESTAMP, emb FLOAT[1024]);

CREATE TABLE IF NOT EXISTS resolver_index (
  table_name VARCHAR, column_name VARCHAR, value VARCHAR, emb FLOAT[1024]);

CREATE TABLE IF NOT EXISTS search_tables (
  src_table VARCHAR, label VARCHAR, parent VARCHAR, emb FLOAT[1024]);

-- ПЕРЕЧЕНЬ ИСТОЧНИКОВ — отдельная таблица, а НЕ производная от корпуса.
-- Это главная структурная починка: раньше `tmp3_src` строился как
-- `SELECT DISTINCT src_table FROM search_corpus`, поэтому сущность, один раз собравшаяся
-- пустой, вычищалась из корпуса и **выпадала из списка навсегда**, а пустой корпус давал
-- ноль источников. Найдено тремя независимыми проверками, подтверждено замером на копии.
CREATE TABLE IF NOT EXISTS search_sources (src_table VARCHAR, seen_at TIMESTAMP);

CREATE TABLE IF NOT EXISTS search_meta (k VARCHAR, v VARCHAR);
CREATE TABLE IF NOT EXISTS search_quality (k VARCHAR, v BIGINT, note VARCHAR);
CREATE TABLE IF NOT EXISTS build_state (ts TIMESTAMP, k VARCHAR, v BIGINT);
-- Разметка «о таком спрашивают / это служебное». Заводится ЗДЕСЬ, а не только в
-- `classify_entities.py`: сборка ссылается на неё при выборе очерёдности векторизации, и
-- на первом такте, когда разметчик ещё не отработал (или модель недоступна), таблица
-- обязана существовать пустой — тогда весь корпус считается одним проходом, как раньше.
CREATE TABLE IF NOT EXISTS search_entity_class (src_table VARCHAR, cls VARCHAR, seen_at TIMESTAMP);

-- 🔴 ЧЕЛОВЕЧЕСКИЕ СЛОВА К СУЩНОСТИ — ОСНОВА ДЛЯ ВЫБОРА, А НЕ ДОГАДКА. Замысел владельца
-- 30.07: «нельзя надеяться на ллм, у него мало контекста чтобы правильно сделать; Wiki тут
-- поможет». [замер 30.07] из 11 провалов приёмки 8-10 — выбрана не та сущность, и переход на
-- модель посильнее этого НЕ починил (плохих исходов 11 против 11): из названия «Отчёт о
-- розничных продажах» против «Реализация Товаров Услуг» неоткуда узнать, какое отвечает на
-- «на какую сумму мы продали». Знание кладётся сюда один раз при установке и переиспользуется,
-- как разметка деловых/служебных (`search_entity_class`).
CREATE TABLE IF NOT EXISTS search_entity_alias (
  src_table VARCHAR, aliases VARCHAR, best_used_for VARCHAR, not_enough_for VARCHAR,
  seen_at TIMESTAMP);

-- Словарь и индекс. Поля индексируются по отдельности в ОДНОМ индексе — штатный шаблон
-- движка: `doc` для широкого запроса, `refs` для адресности и веса, `src_table` без
-- словаря (keyword) для фильтра уровня индекса.
CREATE TEXT SEARCH DICTIONARY IF NOT EXISTS search_dict (
  template = 'text', locale = :'dict_locale', case = 'lower',
  stemming = false, accent = false, frequency = true, position = true, norm = true);

-- 🔴 ВТОРОЙ СЛОВАРЬ — ТОЛЬКО ДЛЯ СОПОСТАВЛЕНИЯ СЛОВА ЧЕЛОВЕКА С НАЗВАНИЕМ. Со стеммингом.
-- Указание владельца 30.07: «разве это не должно было решиться через средства serene? там
-- ведь инструмент, чтобы „спб" был Санкт-Петербург». Инструмент есть, и он у нас был
-- описан (`docs/SERENE_CAPS_3.md §2.4`), а я вместо него написал `contains()` по подстроке.
--
-- Зачем отдельный словарь, а не `stemming = true` в основном. `stemming = false` в
-- `search_dict` — осознанное решение ради языконезависимости ПОИСКА (`SERENEDB.md`): на
-- кодах и артикулах стемминг режет точность. Но сопоставление «слово вопроса ↔ название
-- сущности» — другая задача, и там словоформы обязаны сходиться:
-- [замер 30.07] `складов` / `Склады` без стемминга дают `{складов}` / `{склады}` — НЕ
-- сходятся, и мой отсев выбросил `catalog_склады`, то есть сам ответ. Со стеммингом оба
-- дают `{склад}`. Та же пара, что роняла ответ монеткой: `закупки` / `закупка` -> `{закупк}`;
-- `приобретений` / `Приобретение` -> `{приобретен}`.
--
-- `copy_from` берёт ВСЕ настройки основного словаря, включая ЛОКАЛЬ: своего значения я не
-- задаю, оно приходит из настройки базы. Индекс этот словарь не трогает — он не участвует
-- ни в одном `CREATE INDEX`, поэтому пересборка индекса не нужна.
-- Словари живут В СВОЕЙ БАЗЕ (проверено: из `postgres` словарь `ut_test` не виден), то есть
-- столкновения между базами тут нет, в отличие от секретов (`techContext` ловушка 26).
CREATE TEXT SEARCH DICTIONARY IF NOT EXISTS search_dict_stem (
  template = 'copy_from', from = 'search_dict', stemming = true);

CREATE INDEX IF NOT EXISTS search_idx ON search_corpus
  USING inverted(doc search_dict, refs search_dict, src_table)
  INCLUDE (src_table, row_key, doc_date);

-- Права. Идемпотентно, поэтому повторный вызов безвреден.
-- `serene_resolver` — отдельная роль под резолвер (positive control): SQL, который пишет
-- модель, не должен дотягиваться до служебных эмбеддингов даже в обход валидатора.
GRANT SELECT ON search_corpus  TO serene_ro;
GRANT SELECT ON search_tables  TO serene_ro;
-- Свежесть данных (`build_ts`) и полнота (`cov_*`) — сервис ответов читает их, чтобы
-- показать возраст данных и старение (п. 18), поэтому право нужно читающей роли.
GRANT SELECT ON search_quality TO serene_ro;
GRANT SELECT ON search_entity_class TO serene_ro;
GRANT SELECT ON resolver_index TO serene_resolver;
REVOKE SELECT ON resolver_index FROM serene_ro;

SELECT 'объекты поиска на месте' AS шаг,
       (SELECT count(*) FROM duckdb_tables()
        WHERE database_name = current_database()
          AND table_name IN ('search_corpus','resolver_index','search_tables',
                             'search_sources','search_meta','build_state')) AS таблиц,
       (SELECT count(*) FROM duckdb_indexes() WHERE index_name = 'search_idx') AS индексов;
