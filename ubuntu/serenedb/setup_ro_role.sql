-- Read-only роль SereneDB для бот-отчётов (защита в глубину: запись физически запрещена БД,
-- сверх валидатора «только SELECT» в serene_report). Бот ходит под serene_ro; загрузчик витрины
-- (poc_load_entity / штатный ETL) — под rw (postgres). Разделение как ai_reader vs app_rw в 1С.
--
-- Запуск под rw:  PGPASSWORD='' psql "host=127.0.0.1 port=7890 user=postgres" -f setup_ro_role.sql
-- (пароль serene_ro подставить свой — в /etc/1c-mcp-reports.env как PGPASSWORD, НЕ в git).

CREATE ROLE serene_ro LOGIN PASSWORD 'CHANGE_ME_RANDOM';
GRANT USAGE ON SCHEMA public TO serene_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO serene_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO serene_ro;

-- Проверено (2026-07-23): под serene_ro SELECT работает; CREATE/INSERT/UPDATE/DROP -> permission denied.
-- ⚠ Схему бот интроспектирует через duckdb_columns() (schema_name='public'), т.к. под ro
--   information_schema.columns пуста (квирк SereneDB/DuckDB). PRAGMA table_info / SELECT * LIMIT 0 тоже ок.
-- Подключение бота: host=127.0.0.1 port=7890 user=serene_ro dbname=postgres (+ PGPASSWORD из env).
