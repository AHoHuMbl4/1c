-- Память явного выбора человека (план §8 шаг 6, аудит §13).
-- Отдельный файл: corpus_init.sql не трогаем.
--
-- Доки SereneDB (сборка 26.07.3 проверяется живьём в ask_choice_memory_apply.sh):
--   Sql › Statements › CREATE TABLE
--   Sql › Statements › CREATE SEQUENCE  (DEFAULT nextval — PK)
--   Sql › Constraints › Primary Key and Unique Constraint
--     UNIQUE (user_hash, db_name, class_key) — upsert «запомни» повторно
--   Sql › Statements › INSERT › DO UPDATE Clause (Upsert)
--     ON CONFLICT (user_hash, db_name, class_key) DO UPDATE
--   Sql › Statements › UPDATE
--   Sql › Statements › GRANT / REVOKE
--   Security › Privileges  (column privileges; INSERT/UPDATE/SELECT)
--   GRANT › Privileges by object type: SEQUENCE = USAGE, SELECT, UPDATE
--
-- Область: база (таблица живёт в своей БД) + пользователь (user_hash).
-- Глобального повышения личного выбора нет: чужой user_hash строку не читает
-- как свою. Коллизия (разные ветки у разных пользователей того же класса)
-- видна shadow-метрикой, в ответ не входит.
--
-- Роль сервиса (serene_ro, тот же DSN, что у ответов):
--   INSERT — «запомни»; UPDATE — «забудь» (active/cancelled);
--   SELECT — shadow-чтение своей строки и сводка коллизий класса.
-- В отличие от ask_journal, сервис память ЧИТАЕТ (shadow в diag).
-- DELETE/TRUNCATE отозваны: строк мало, ротации нет.
-- Текста вопроса нет.

CREATE SEQUENCE IF NOT EXISTS ask_choice_memory_id_seq START 1;

CREATE TABLE IF NOT EXISTS ask_choice_memory (
  id BIGINT PRIMARY KEY DEFAULT nextval('ask_choice_memory_id_seq'),
  ts TIMESTAMP DEFAULT now(),
  db_name VARCHAR,
  user_hash VARCHAR,
  class_key VARCHAR,
  readings_fp VARCHAR,
  measure_ctx VARCHAR,
  window_fp VARCHAR,
  chosen_src VARCHAR,
  chosen_measure VARCHAR,
  chosen_axis VARCHAR,
  chosen_label VARCHAR,
  entity_ver VARCHAR,
  ticket_id VARCHAR,
  active BOOLEAN DEFAULT TRUE,
  cancelled BOOLEAN DEFAULT FALSE,
  cancelled_at TIMESTAMP,
  UNIQUE (user_hash, db_name, class_key)
);

REVOKE ALL ON ask_choice_memory FROM PUBLIC;
REVOKE DELETE, TRUNCATE, REFERENCES, TRIGGER ON ask_choice_memory FROM serene_ro;
GRANT INSERT, SELECT, UPDATE ON ask_choice_memory TO serene_ro;
GRANT USAGE, SELECT, UPDATE ON SEQUENCE ask_choice_memory_id_seq TO serene_ro;
