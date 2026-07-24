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

-- РАЗНОС РОЛЕЙ (positive control, 2026-07-24): служебный resolver_index читает ОТДЕЛЬНАЯ роль
-- serene_resolver, а НЕ serene_ro. Тогда LLM-SQL под serene_ro не дотянется к внутреннему индексу
-- (эмбеддинги) ДАЖЕ в обход валидатора — нет привилегии. Пароль сгенерировать (openssl rand -hex 24),
-- вписать в /etc/1c-mcp-reports.env: RESOLVER_PW=<pw> и
-- RESOLVER_DSN=host=127.0.0.1 port=7890 user=serene_resolver dbname=postgres  (НЕ в git).
CREATE ROLE serene_resolver LOGIN PASSWORD 'CHANGE_ME_RANDOM';
GRANT USAGE ON SCHEMA public TO serene_resolver;
GRANT SELECT ON resolver_index TO serene_resolver;   -- resolver_index создаёт build_resolver_index.py
REVOKE SELECT ON resolver_index FROM serene_ro;       -- ro теряет доступ к служебному индексу
-- Проверено (2026-07-24): под serene_ro SELECT FROM resolver_index -> permission denied; резолвер
-- (семантика «спб»->Г. САНКТ-ПЕТЕРБУРГ, n=172) работает через serene_resolver. build_resolver_index
-- идемпотентно повторяет GRANT serene_resolver + REVOKE serene_ro при каждой пересборке индекса.
--
-- ⚠ Движковый лимит доступа к ФС (allowed_directories/enable_external_access) для serene_ro на этой
--   сборке SereneDB НЕДОСТИЖИМ (enable_external_access — глобальный one-way латч, ломает загрузчик;
--   allowed_directories под ro = no-op, SET GLOBAL/ALTER ROLE не держат, флага конфига нет). Доступ к
--   файлам ограничивает ТОЛЬКО валидатор (FS_ACCESS денайлист). Вопрос фаундерам SereneDB — см. docs.
