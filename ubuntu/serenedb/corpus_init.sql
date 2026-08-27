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
  refs_map MAP(VARCHAR, VARCHAR), emb FLOAT[1024]);

-- 🔴 ДОБОР КОЛОНКИ ДЛЯ БАЗ, СОБРАННЫХ ПРЕЖНИМ КОДОМ. `CREATE TABLE IF NOT EXISTS` у
-- существующей таблицы не делает НИЧЕГО — новая колонка из объявления выше в такую базу
-- не попадёт. [замер 30.07] первая база (`dbname=postgres`, 103 808 строк) осталась без
-- `flags`, и запрос сервиса падал: `Referenced column "flags" not found in FROM clause`.
-- Отказ при наличии данных — дефект (п. 21), поэтому добор стоит ЗДЕСЬ, в создании схемы,
-- которое идёт первым шагом каждого такта, а не только в слиянии.
-- Пока база не пересобрана, карта пуста, `coalesce(..., false)` читает это как «не папка»,
-- и поведение совпадает с прежним — деградация плавная, а не отказ.
ALTER TABLE search_corpus ADD COLUMN IF NOT EXISTS flags MAP(VARCHAR, BOOLEAN);
-- Карта ссылок строки — как `nums`: колонка → имя (или GUID, если имени нет).
-- GROUP BY оси, не разбор текста `refs`. Вектор не задет: колонка не входит в doc_hash.
ALTER TABLE search_corpus ADD COLUMN IF NOT EXISTS refs_map MAP(VARCHAR, VARCHAR);

-- Справочник осей группы: какая колонка refs_map на какой каталог ссылается.
-- Берётся из kind='ref' и search_refmap.owner. Пустая цель в таблицу не кладётся.
CREATE TABLE IF NOT EXISTS search_refcols (
  src_table VARCHAR, col VARCHAR, target_src VARCHAR);
GRANT SELECT ON search_refcols TO serene_ro;

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
GRANT SELECT ON search_meta TO serene_ro;
GRANT SELECT ON search_meta TO serene_resolver;

-- Карта баланс-источников: структура из $metadata (форма, Period, Дт/Кт или RecordType).
-- Наполняется `corpus_build.sql`; ответ читает через `balance_map_rows` в `serene_ask.py`.
-- Пустая на первом такте — норма; выкат `corpus_init` на развёрнутые базы — отдельный шаг.
CREATE TABLE IF NOT EXISTS search_balance_map (
  src_table VARCHAR,
  form VARCHAR,
  has_record_type BOOLEAN,
  has_debit_credit BOOLEAN,
  has_period BOOLEAN,
  has_ext_dimension BOOLEAN,
  seen_at TIMESTAMP);
GRANT SELECT ON search_balance_map TO serene_ro;
GRANT SELECT ON search_balance_map TO serene_resolver;

-- Карта оси дат графика: prop-имена из $metadata (дата / ключ вида / часы).
-- Наполняется corpus_build.sql §1-кватер; пустая — норма (оси в базе нет).
CREATE TABLE IF NOT EXISTS search_calendar_map (
  src_table VARCHAR,
  date_col VARCHAR,
  day_key_col VARCHAR,
  hours_col VARCHAR,
  seen_at TIMESTAMP);
GRANT SELECT ON search_calendar_map TO serene_ro;
GRANT SELECT ON search_calendar_map TO serene_resolver;

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

-- КЛАССЫ РАЗВИЛОК И ЧЕЛОВЕЧЕСКИЕ ПОДПИСИ ИХ ВЕТОК (план `PLAN_ANSWER_CONTRACT.md` §7,
-- аудит §12: ручная разметка отвергнута, подписи пишет штатный агент OpenClaw).
-- Проблема: подпись «Реализация ТМЦ (документ)» не говорит человеку «это отгрузки,
-- а не оплаты». Класс развилки — множество источников, по которым один и тот же
-- вопрос даёт РАЗНЫЕ числа (документ ↔ его регистр, одноимённые источники); классов
-- мало, и они не растут с языком.
--
-- `search_fork_class` ПИШЕТ детектор (шаг 4): fork_key = sha1(src_set¦measure_ctx),
-- где src_set — ОДИН класс эквивалентности атомов (src с одинаковым типизированным
-- атомом), не все конкурирующие ветки разом. Исход B группирует по атому; подписи в
-- `search_fork_label` — (fork_key, src) внутри класса. Волна-1 писала sha1 всех src
-- сразу — рассинхрон с исходами шага 4 ([замер 17.08 okna]).
-- 🔴 Колонка называется `measure_ctx`, а не `measure`: именно её пишет детектор
-- (`serene_ask.py`, `_fork_log`), иначе его INSERT падает и класс теряется МОЛЧА.
-- 🔴 `UNIQUE` на fork_key обязателен: детектор пишет `INSERT … ON CONFLICT (fork_key)
-- DO UPDATE`, а цель конфликта требует уникального ограничения или индекса (доки
-- SereneDB: Sql › Statements › INSERT › Defining a Conflict Target). [замер 16.08]
-- на ut_test без UNIQUE вставка отвергается: «conflict target are not referenced by
-- a UNIQUE/PRIMARY KEY CONSTRAINT or INDEX» — и shadow-заметка терялась бы молча.
CREATE TABLE IF NOT EXISTS search_fork_class (
  fork_key VARCHAR UNIQUE, src_set VARCHAR, measure_ctx VARCHAR,
  seen_at TIMESTAMP, seen_count INTEGER);

-- `search_fork_label` ПИШЕТ `branch_alias.sh` штатным агентом OpenClaw, читает рендер
-- веток. Подпись — СМЫСЛ ветки бизнес-языком, а не пересказ имени таблицы. Пустая
-- запись — попытка, не ответ (тот же смысл, что у `search_entity_alias`): переспрос
-- не чаще RETRY_H держит сам скрипт. Ключ пары — (fork_key, src), запись через MERGE.
CREATE TABLE IF NOT EXISTS search_fork_label (
  fork_key VARCHAR, src VARCHAR, label VARCHAR, seen_at TIMESTAMP);

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

-- ── Словарь индекса алиасов СО стеммингом + frequency (С3/С5) ─────────────────
-- Доки: Cookbook › Stemming and Stopwords; CREATE TEXT SEARCH DICTIONARY › text.
-- search_dict_stem (copy_from) для ts_lexize годится, но на inverted давал
-- tfidf=0 без явного frequency=true ([замер C3 27.08]). Индекс корпуса
-- (search_idx) остаётся на search_dict без стемма — коды/артикулы.
CREATE TEXT SEARCH DICTIONARY IF NOT EXISTS search_dict_alias_stem (
  template = 'text', locale = :'dict_locale', case = 'lower',
  stemming = true, accent = false,
  frequency = true, position = true, norm = true);

-- ── Ф6.3 словарь синонимов (query-side: pipeline text→solr_synonyms) ──────────
-- Доки: Cookbook › Synonyms; CREATE TEXT SEARCH DICTIONARY › pipeline /
-- solr_synonyms / stem. Имя — параметр :"solr_syn_dict" (build.sh /
-- ASK_SOLR_SYNONYMS_DICT → умолч. search_dict_syn), не имя базы клиента.
-- Заготовка: IF NOT EXISTS карту не обновляет (ловушка §5.2 фактуры).
-- Наполнение — DROP+CREATE файлом после wiki_alias (`solr_synonyms_build.py`:
-- стем-ключи через ts_lexize(search_dict_stem), step1 stemming=true).
-- Индекс корпуса не трогаем — только ts_lexize. Orphan-слот кэша моста снят
-- (С3, docs/SYNONYM_BRIDGE_DECISION.md).
--
-- 🔴 УМОЛЧАНИЕ ИМЕНИ (Д4 / 27.08). Без `-v solr_syn_dict=…` psql оставляет
-- литерал `:"solr_syn_dict"` → syntax error → такт «развёртывание объектов»
-- падает на каждом выстреле. На okna так стояло с 24.08 19:36 (3083 падения):
-- выкатили corpus_init с параметром, а build.sh без `-v`. Умолчание здесь
-- fail-open к тому же имени, что build.sh (`search_dict_syn`); вызывающий
-- по-прежнему обязан передавать `-v` (замок test_psql_init_vars.py).

\if :{?solr_syn_dict}
\else
\set solr_syn_dict search_dict_syn
\endif

CREATE TEXT SEARCH DICTIONARY IF NOT EXISTS :"solr_syn_dict" (
  template = 'pipeline',
  step1_template = 'text',
  step1_locale = :'dict_locale',
  step1_case = 'lower',
  step1_stemming = true,
  step2_template = 'solr_synonyms',
  step2_synonyms = '');
-- Отдельного GRANT USAGE ON TEXT SEARCH DICTIONARY в SereneDB нет
-- (доки GRANT › Privileges by object type: TABLE/SEQUENCE/FUNCTION/…; словаря
-- нет). Как у search_dict_stem: создатель — postgres, ts_lexize под serene_ro
-- отвечает без отдельного права. Держим право на таблицу-источник + precheck.

CREATE INDEX IF NOT EXISTS search_idx ON search_corpus
  USING inverted(doc search_dict, refs search_dict, src_table)
  INCLUDE (src_table, row_key, doc_date);

-- Права. Идемпотентно, поэтому повторный вызов безвреден.
-- `serene_resolver` — отдельная роль под резолвер (positive control): SQL, который пишет
-- модель, не должен дотягиваться до служебных эмбеддингов даже в обход валидатора.
GRANT SELECT ON search_corpus  TO serene_ro;
GRANT SELECT ON search_refcols TO serene_ro;
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
-- Развилки и их подписи: рендер читает обе (класс — чтобы назвать развилку,
-- подписи — чтобы показать ветки человеческими словами). Без GRANT та же молчаливая
-- пустота, что у алиасов выше, — рендер считал бы «развилок нет» при живом журнале.
-- 🔴 INSERT/UPDATE на `search_fork_class` — осознанное ЕДИНСТВЕННОЕ исключение из
-- read-only: журнал пишет детектор ответного сервиса, а у сервиса один DSN (ro-роль).
-- Без права его вставка падает, RuntimeError ловится и класс теряется молча — контур
-- словаря развилок мёртв при живом детекторе. `test_ro_role.py` исключает эту таблицу
-- из пробы записи нарочно; остальная витрина по-прежнему физически read-only.
GRANT SELECT, INSERT, UPDATE ON search_fork_class TO serene_ro;
GRANT SELECT ON search_fork_label TO serene_ro;

-- Индекс по алиасам: когда выбор сущности не подтверждён, соперников по вопросу ранжирует
-- ДВИЖОК штатной `tfidf`, а не наш счёт общих слов. Разница принципиальная: [замер 30.07]
-- счёт совпадений считает ВСЕ общие слова, поэтому «сколько записей в справочнике»
-- совпадало с любым вопросом такого вида, и верный ответ про номенклатуру превращался в
-- уточнение с вариантами «Денежные Средства В Кассах ККМ». У словаря включена частота
-- (`frequency = true`), и редкое слово весит больше частого — это делает движок.
CREATE INDEX IF NOT EXISTS alias_idx ON search_entity_alias
  USING inverted(aliases search_dict_alias_stem, src_table) INCLUDE (src_table);
GRANT SELECT ON alias_idx TO serene_ro;
GRANT SELECT ON resolver_index TO serene_resolver;
REVOKE SELECT ON resolver_index FROM serene_ro;


-- Precheck оси дат графика: ключи calendar_* либо все три (после build), либо
-- ни одного (до первого такта). Частичный набор — дефект сборки. Пустой v —
-- оси в этой базе нет, не ошибка. GRANT на карту обязателен.
SELECT CASE
  WHEN (SELECT count(*) FROM information_schema.role_table_grants
        WHERE privilege_type = 'SELECT' AND grantee = 'serene_ro'
          AND table_name = 'search_calendar_map') = 0
       THEN error('serene_ro без SELECT на search_calendar_map')
  WHEN (SELECT count(*) FROM search_meta
        WHERE k IN ('calendar_registers', 'calendar_day_kinds',
                    'calendar_working_day_keys'))
       NOT IN (0, 3)
       THEN error('search_meta calendar_*: частичный набор (нужно 0 или 3 ключа)')
  WHEN EXISTS (
         SELECT 1 FROM search_meta
         WHERE k IN ('calendar_registers', 'calendar_day_kinds',
                     'calendar_working_day_keys') AND v IS NULL)
       THEN error('search_meta calendar_*: v IS NULL (ожидается VARCHAR, пусто при отсутствии)')
END;

SELECT 'объекты поиска на месте' AS шаг,
       (SELECT count(*) FROM duckdb_tables()
        WHERE database_name = current_database()
          AND table_name IN ('search_corpus','resolver_index','search_tables',
                             'search_sources','search_meta','search_balance_map','search_calendar_map',
                             'build_state','search_refcols','search_fork_class',
                             'search_fork_label')) AS таблиц,
       (SELECT count(*) FROM duckdb_indexes() WHERE index_name = 'search_idx') AS индексов,
       (SELECT CASE WHEN ts_lexize(:'solr_syn_dict', 'x') IS NOT NULL
               THEN 1 ELSE 0 END) AS solr_syn_dict_ok;
