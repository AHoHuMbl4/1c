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
  nums MAP(VARCHAR, DOUBLE), flags MAP(VARCHAR, BOOLEAN), doc_date TIMESTAMP,
  emb FLOAT[1024]);

-- 🔴 ДОБОР КОЛОНКИ ДЛЯ БАЗ, СОБРАННЫХ ПРЕЖНИМ КОДОМ. `CREATE TABLE IF NOT EXISTS` у
-- существующей таблицы не делает НИЧЕГО — новая колонка из объявления выше в такую базу
-- не попадёт. [замер 30.07] первая база (`dbname=postgres`, 103 808 строк) осталась без
-- `flags`, и запрос сервиса падал: `Referenced column "flags" not found in FROM clause`.
-- Отказ при наличии данных — дефект (п. 21), поэтому добор стоит ЗДЕСЬ, в создании схемы,
-- которое идёт первым шагом каждого такта, а не только в слиянии.
-- Пока база не пересобрана, карта пуста, `coalesce(..., false)` читает это как «не папка»,
-- и поведение совпадает с прежним — деградация плавная, а не отказ.
ALTER TABLE search_corpus ADD COLUMN IF NOT EXISTS flags MAP(VARCHAR, BOOLEAN);

CREATE TABLE IF NOT EXISTS resolver_index (
  table_name VARCHAR, column_name VARCHAR, value VARCHAR, emb FLOAT[1024]);

-- `written_by*` — связь «кто пишет этот источник»: у движений регистра есть регистратор,
-- и это ЕДИНСТВЕННЫЙ сигнал выбора сущности, который не является названием (разбор —
-- `corpus_build.sql`, раздел 2-тер). Хранится тройкой, а не одним именем: связь
-- (`written_by`), её доля в движениях (`written_by_share`) и полный расклад
-- (`written_by_all`) — чтобы порог «преобладает ли регистратор» назначал тот, кто
-- принимает решение, а не сборка.
CREATE TABLE IF NOT EXISTS search_tables (
  src_table VARCHAR, label VARCHAR, parent VARCHAR, emb FLOAT[1024],
  written_by VARCHAR, written_by_share DOUBLE, written_by_all MAP(VARCHAR, BIGINT));

-- Добор колонок для баз, собранных прежним кодом, — по той же причине, что у `flags`
-- выше: `CREATE TABLE IF NOT EXISTS` существующую таблицу не трогает. Пока база не
-- пересобрана, связь пуста, и всё, что её читает, обязано читать пустоту как «связи нет».
ALTER TABLE search_tables ADD COLUMN IF NOT EXISTS written_by VARCHAR;
ALTER TABLE search_tables ADD COLUMN IF NOT EXISTS written_by_share DOUBLE;
ALTER TABLE search_tables ADD COLUMN IF NOT EXISTS written_by_all MAP(VARCHAR, BIGINT);

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

-- Словарь величин: человеческие имена к полю сущности. Связь поле → слова, а не
-- мешок слов в алиасах сущности: иначе «сумма продаж» не отличить от «оплаты картой»,
-- когда оба лежат одной строкой. Пустая запись — попытка, не ответ (тот же смысл,
-- что у `search_entity_alias`): переспрос держит `wiki_alias.sh`.
CREATE TABLE IF NOT EXISTS search_measure_alias (
  src_table VARCHAR, measure VARCHAR, aliases VARCHAR, seen_at TIMESTAMP);

-- Время последнего переноса сущности в поисковый слой. Пишет `corpus_merge` по
-- фактически перенесённым (`tmp3_build`); такт-пропуск колонку не трогает.
-- MERGE метки в `corpus_build` её не сбрасывает — там UPDATE только label/parent/emb.
ALTER TABLE search_tables ADD COLUMN IF NOT EXISTS last_built_at TIMESTAMP;

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
-- 🔴 ПРАВО НА АЛИАСЫ. Без него правило подтверждения выбора НЕ РАБОТАЕТ ВОВСЕ, и это не
-- заметно: `psql` отдаёт `permission denied`, сервис ловит RuntimeError и трактует его как
-- «знания нет — требовать подтверждения нечем», то есть пропускает ответ БЕЗ проверки.
-- [замер 30.07] защита, построенная против уверенного неверного ответа, вырождалась ровно
-- в него: «сколько НДС заплатили поставщикам» отвечалось регистром вместо уточнения, хотя
-- в алиасах верной сущности лежит дословно эта фраза.
GRANT SELECT ON search_entity_alias TO serene_ro;
-- Без права сервис ловит RuntimeError и считает «словаря величин нет» — выбор
-- величины тогда молча идёт по подстроке имени колонки. Та же ловушка, что у
-- алиасов сущности выше.
GRANT SELECT ON search_measure_alias TO serene_ro;

-- Индекс по алиасам: когда выбор сущности не подтверждён, соперников по вопросу ранжирует
-- ДВИЖОК штатной `tfidf`, а не наш счёт общих слов. Разница принципиальная: [замер 30.07]
-- счёт совпадений считает ВСЕ общие слова, поэтому «сколько записей в справочнике»
-- совпадало с любым вопросом такого вида, и верный ответ про номенклатуру превращался в
-- уточнение с вариантами «Денежные Средства В Кассах ККМ». У словаря включена частота
-- (`frequency = true`), и редкое слово весит больше частого — это делает движок.
CREATE INDEX IF NOT EXISTS alias_idx ON search_entity_alias
  USING inverted(aliases search_dict, src_table) INCLUDE (src_table);
GRANT SELECT ON alias_idx TO serene_ro;
GRANT SELECT ON resolver_index TO serene_resolver;
REVOKE SELECT ON resolver_index FROM serene_ro;

SELECT 'объекты поиска на месте' AS шаг,
       (SELECT count(*) FROM duckdb_tables()
        WHERE database_name = current_database()
          AND table_name IN ('search_corpus','resolver_index','search_tables',
                             'search_sources','search_meta','build_state')) AS таблиц,
       (SELECT count(*) FROM duckdb_indexes() WHERE index_name = 'search_idx') AS индексов;
