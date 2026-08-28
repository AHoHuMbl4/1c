-- Э1б / Ф6.3: компиляция Solr-карты из search_entity_alias → pipeline text→solr_synonyms.
-- Без Python-посредника: split/escape/dedupe/string_agg в SQL, один psql.
-- Доки: solr_synonyms — CREATE TEXT SEARCH DICTIONARY › solr_synonyms;
--       pipeline — CREATE TEXT SEARCH DICTIONARY › pipeline;
--       ts_lexize — Sql › Functions › Search › Full-Text Search;
--       string_split_regex — Sql › Functions › Text Functions;
--       list_string_agg — Sql › Functions › List Functions.
-- Параметры psql (-v): solr_syn_dict, dict_locale, alias_table (умолч. search_entity_alias),
--   stem_dict (умолч. search_dict_stem), max_rules (20000), max_bytes (400000).
\set ON_ERROR_STOP on

\if :{?solr_syn_dict}
\else
\set solr_syn_dict search_dict_syn
\endif
\if :{?dict_locale}
\else
\set dict_locale ru_RU.UTF-8
\endif
\if :{?alias_table}
\else
\set alias_table search_entity_alias
\endif
\if :{?stem_dict}
\else
\set stem_dict search_dict_stem
\endif
\if :{?max_rules}
\else
\set max_rules 20000
\endif
\if :{?max_bytes}
\else
\set max_bytes 400000
\endif

-- Нормализация locale (.utf8 → .UTF-8) как в solr_synonyms_build.py
CREATE OR REPLACE TEMP TABLE _solr_locale AS
  SELECT CASE
           WHEN lower(:'dict_locale') LIKE '%.utf8'
                AND lower(:'dict_locale') NOT LIKE '%.utf-8'
             THEN substr(:'dict_locale', 1, length(:'dict_locale') - 5) || 'UTF-8'
           ELSE :'dict_locale'
         END AS loc;

-- Карта правил: одиночные слова → стем-ключи → bi-классы Solr
CREATE OR REPLACE TEMP TABLE _solr_map AS
WITH raw AS (
       SELECT aliases
         FROM :"alias_table"
        WHERE coalesce(trim(aliases), '') <> ''
     ),
     split AS (
       SELECT r.aliases,
              trim(t.term) AS term
         FROM raw r,
              unnest(regexp_split_to_array(r.aliases, '(?<!\\),')) AS t(term)
        WHERE trim(t.term) <> ''
     ),
     unesc AS (
       SELECT aliases,
              trim(replace(replace(term, '\\,', ','), '\\\\', '\\')) AS term
         FROM split
        WHERE trim(replace(replace(term, '\\,', ','), '\\\\', '\\')) <> ''
     ),
     single AS (
       SELECT aliases, term
         FROM unesc
        WHERE NOT regexp_matches(term, '\s')
     ),
     stems AS (
       SELECT s.aliases,
              s.term,
              coalesce((ts_lexize(:'stem_dict', s.term))[1], s.term) AS stem
         FROM single s
     ),
     esc AS (
       SELECT aliases,
              replace(replace(stem, '\', '\\'), ',', '\,') AS esc_stem,
              lower(stem) AS stem_key
         FROM stems
     ),
     row_dedup AS (
       SELECT aliases, esc_stem, stem_key,
              row_number() OVER (PARTITION BY aliases, stem_key ORDER BY esc_stem) AS rn
         FROM esc
     ),
     row_rules AS (
       SELECT string_agg(esc_stem, ', ' ORDER BY stem_key) AS rule
         FROM row_dedup
        WHERE rn = 1
        GROUP BY aliases
       HAVING count(DISTINCT stem_key) >= 2
     ),
     uniq AS (
       SELECT rule,
              lower(rule) AS rule_key,
              row_number() OVER (PARTITION BY lower(rule) ORDER BY rule) AS rn
         FROM row_rules
        WHERE rule IS NOT NULL AND trim(rule) <> ''
     )
SELECT string_agg(rule, chr(10) ORDER BY rule_key) AS solr_map,
       count(*)::bigint AS n_rules,
       coalesce(length(string_agg(rule, chr(10) ORDER BY rule_key)), 0)::bigint AS n_bytes
  FROM uniq
 WHERE rn = 1;

SELECT n_rules, n_bytes, coalesce(solr_map, '') AS solr_map
  FROM _solr_map;
\gset map_

\if :map_n_rules
\else
\set map_n_rules 0
\endif
\if :map_n_bytes
\else
\set map_n_bytes 0
\endif

\if :map_n_rules
-- лимиты (п. 13: ошибка, не обрезка)
SELECT CASE
         WHEN :map_n_rules > :max_rules THEN
           error('solr synonyms: ' || :map_n_rules || ' правил > лимита '
                 || :max_rules || ' (F6_SYNONYMS_FACTS §3.2) — карта не обрезается')
         WHEN :map_n_bytes > :max_bytes THEN
           error('solr synonyms: ' || :map_n_bytes || ' байт > лимита '
                 || :max_bytes || ' (F6_SYNONYMS_FACTS §3.2) — карта не обрезается')
         ELSE 1
       END;

-- alias_idx на search_dict_alias_stem (С5)
CREATE TEXT SEARCH DICTIONARY IF NOT EXISTS search_dict_alias_stem (
  template = 'text', locale = (SELECT loc FROM _solr_locale), case = 'lower',
  stemming = true, accent = false,
  frequency = true, position = true, norm = true);
DROP INDEX IF EXISTS alias_idx;
CREATE INDEX alias_idx ON :"alias_table"
  USING inverted(aliases search_dict_alias_stem, src_table) INCLUDE (src_table);
GRANT SELECT ON alias_idx TO serene_ro;

DROP TEXT SEARCH DICTIONARY IF EXISTS :"solr_syn_dict";
SELECT 'CREATE TEXT SEARCH DICTIONARY ' || quote_ident(:'solr_syn_dict') || ' ('
       || ' template = ''pipeline'','
       || ' step1_template = ''text'','
       || ' step1_locale = ' || quote_literal((SELECT loc FROM _solr_locale)) || ','
       || ' step1_case = ''lower'','
       || ' step1_stemming = true,'
       || ' step2_template = ''solr_synonyms'','
       || ' step2_synonyms = ' || quote_literal((SELECT solr_map FROM _solr_map))
       || ');'
  FROM _solr_map
 WHERE coalesce(solr_map, '') <> '';
\gexec

VACUUM (REFRESH_TABLE) :"alias_table";

\echo solr synonyms: правил :map_n_rules, байт :map_n_bytes → pipeline stem
\else
\echo solr synonyms: пустые источники — словарь не пересоздаётся
\endif
