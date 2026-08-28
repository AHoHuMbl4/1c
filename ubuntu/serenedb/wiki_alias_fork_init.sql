\set ON_ERROR_STOP on
-- DDL развилок day-basis / branch (§7). Доки: CREATE TABLE; MERGE — штатный SQL.
CREATE TABLE IF NOT EXISTS :fork_class_table (
  fork_key VARCHAR UNIQUE, src_set VARCHAR, measure_ctx VARCHAR,
  seen_at TIMESTAMP, seen_count INTEGER);
CREATE TABLE IF NOT EXISTS :fork_label_table (
  fork_key VARCHAR, src VARCHAR, label VARCHAR, seen_at TIMESTAMP);
GRANT SELECT, INSERT, UPDATE ON :fork_class_table TO serene_ro;
GRANT SELECT ON :fork_label_table TO serene_ro;
