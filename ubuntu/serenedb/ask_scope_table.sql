-- Таблица ask_scope: хранит спецификацию счёта (scope) посчитанного ответа
-- для кнопки «добавить в дашборд».
-- Создаётся от имени postgres (у serene_resolver нет прав CREATE TABLE в public).
-- Вызов: psql -f ask_scope_table.sql
CREATE TABLE IF NOT EXISTS ask_scope (
    answer_sha256 VARCHAR PRIMARY KEY,
    spec VARCHAR NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT now()
);
GRANT SELECT ON ask_scope TO serene_ro;
GRANT INSERT, UPDATE, SELECT ON ask_scope TO serene_resolver;
