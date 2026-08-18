-- Журнал «вопрос → кандидаты → ответ → действие» (план §8 шаг 5, аудит §14.5).
-- Отдельный файл: схему чужих таблиц corpus_init.sql не трогаем.
--
-- Доки SereneDB (сборка 26.07.3 проверяется живьём в ask_journal_apply.sh):
--   Sql › Statements › CREATE TABLE
--   Sql › Statements › CREATE SEQUENCE  (DEFAULT nextval — PK)
--   Sql › Statements › GRANT / REVOKE
--   Sql › Statements › INSERT
--   Security › Privileges  (INSERT без SELECT; DELETE — только ротация)
--   Data import and export › Json › JSON Type
--   Sql › Functions › Text Functions › sha256  (хеш считается в сервисе, SQL текст не видит)
--
-- Роль сервиса (serene_ro, тот же DSN, что у ответов): только INSERT и DELETE.
-- DELETE — ротация «последние N», N выводится из count(search_tables)*6*2
-- (виды исхода × вопрос+клик), не подбирается. SELECT/UPDATE отозваны:
-- сервис не читает журнал и не правит строки. Разметка — пишущей ролью, как
-- selftest_check (прямой SQL).
--
-- Приватность: колонки вопроса нет. q_hash = sha256(вопрос) снаружи, q_len = длина.

CREATE SEQUENCE IF NOT EXISTS ask_journal_id_seq START 1;

CREATE TABLE IF NOT EXISTS ask_journal (
  id BIGINT PRIMARY KEY DEFAULT nextval('ask_journal_id_seq'),
  ts TIMESTAMP DEFAULT now(),
  db_name VARCHAR,
  channel VARCHAR,
  user_hash VARCHAR,
  q_hash VARCHAR,
  q_len INTEGER,
  intent_json VARCHAR,
  outcome VARCHAR,
  fork_outcome VARCHAR,
  atoms JSON,
  fork_keys VARCHAR,
  ticket_used BOOLEAN,
  ticket_error VARCHAR,
  code_md5 VARCHAR,
  build_ts VARCHAR,
  alias_ver VARCHAR,
  tokens_in INTEGER,
  tokens_out INTEGER,
  tokens_calls INTEGER,
  latency_ms INTEGER,
  partial_flag BOOLEAN,
  freshness_age_sec INTEGER,
  uncounted INTEGER,
  truncated INTEGER,
  discarded_before INTEGER,
  rid VARCHAR
);

-- DEFAULT PRIVILEGES в нашей сборке на новые таблицы не накладываются
-- (Security › Privileges › Notes: «not yet applied»); REVOKE — на случай
-- GRANT SELECT ON ALL TABLES из setup.sh, повторённого после создания.
REVOKE ALL ON ask_journal FROM PUBLIC;
REVOKE SELECT, UPDATE, TRUNCATE, REFERENCES, TRIGGER ON ask_journal FROM serene_ro;
GRANT INSERT, DELETE ON ask_journal TO serene_ro;
-- Ротация «держим последние N»: DELETE WHERE id <= k. Без SELECT на id
-- SereneDB отвергает WHERE (живое: permission denied при DELETE=true).
-- Колоночный SELECT (id) не даёт читать q_hash/intent/atoms
-- (Security › Privileges › Column privileges).
GRANT SELECT (id) ON ask_journal TO serene_ro;
-- nextval для id требует UPDATE на последовательности
-- (GRANT › Privileges by object type: SEQUENCE = USAGE, SELECT, UPDATE).
GRANT USAGE, SELECT, UPDATE ON SEQUENCE ask_journal_id_seq TO serene_ro;

-- Обновление существующих баз (идempotent).
ALTER TABLE ask_journal ADD COLUMN IF NOT EXISTS rid VARCHAR;
