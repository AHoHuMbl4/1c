\set ON_ERROR_STOP on
-- DDL словарей wiki_alias + память столкновений. Доки: Sql › CREATE TABLE; GRANT — штатный SQL.
CREATE TABLE IF NOT EXISTS :alias_table (
  src_table VARCHAR, aliases VARCHAR, best_used_for VARCHAR, not_enough_for VARCHAR, seen_at TIMESTAMP);
CREATE TABLE IF NOT EXISTS :measure_table (
  src_table VARCHAR, measure VARCHAR, aliases VARCHAR, seen_at TIMESTAMP);
GRANT SELECT ON :measure_table TO serene_ro;
CREATE TABLE IF NOT EXISTS search_alias_probe (
  alias VARCHAR, entities_fp VARCHAR, asked_at TIMESTAMP);
