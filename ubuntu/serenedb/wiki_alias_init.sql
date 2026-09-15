\set ON_ERROR_STOP on
-- DDL словарей wiki_alias + память столкновений. Доки: Sql › CREATE TABLE; GRANT — штатный SQL.
-- probe result/gen_ver: добор колонок. Доки: Sql › Statements › ALTER TABLE › ADD COLUMN
-- (DEFAULT). IF NOT EXISTS в том разделе не назван; на сборке 26.07.3 форма
-- ADD COLUMN IF NOT EXISTS проверена (corpus_init). information_schema.columns на
-- части инстансов пуст (setup_ro_role) — чистый guard без IF NOT EXISTS ломал бы
-- повторный init (канон шага 1 для tables — information_schema.tables — для
-- columns здесь неприменим).
CREATE TABLE IF NOT EXISTS :alias_table (
  src_table VARCHAR, aliases VARCHAR, best_used_for VARCHAR, not_enough_for VARCHAR, seen_at TIMESTAMP);
CREATE TABLE IF NOT EXISTS :measure_table (
  src_table VARCHAR, measure VARCHAR, aliases VARCHAR, seen_at TIMESTAMP);
GRANT SELECT ON :measure_table TO serene_ro;
CREATE TABLE IF NOT EXISTS :probe_table (
  alias VARCHAR, entities_fp VARCHAR, asked_at TIMESTAMP,
  result VARCHAR DEFAULT '', gen_ver VARCHAR DEFAULT '');
-- Старые probe (3 колонки): CREATE IF NOT EXISTS схему не меняет.
ALTER TABLE :probe_table ADD COLUMN IF NOT EXISTS result VARCHAR DEFAULT '';
ALTER TABLE :probe_table ADD COLUMN IF NOT EXISTS gen_ver VARCHAR DEFAULT '';
