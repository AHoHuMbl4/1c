\timing on
\set ON_ERROR_STOP on

-- СБОРКА ПОИСКОВОГО КОРПУСА ШТАТНЫМИ СРЕДСТВАМИ SereneDB.
--
-- Это исполнение пункта 20 TARGET.md: данные лежат в SereneDB — работа с ними делается
-- внутри SereneDB. Питон здесь не участвует ни в одной строке: движок сам ходит по HTTP
-- в шлюз 1С за `$metadata`, сам разбирает XML регулярными выражениями, сам классифицирует
-- колонки, сам считает статистики, сам собирает текст и отпечаток.
--
-- Единственное, чего у движка нет и что остаётся снаружи, — решение «какая из числовых
-- колонок содержит деньги». Это языковая задача, и пункт 20 разрешает её явно. Здесь
-- таблица `tmp3_amountcol` заполняется восстановлением прошлого выбора модели из боевого
-- корпуса — это нужно ДЛЯ СВЕРКИ; в бою её заполняет ответ модели.
--
-- ЗАПУСК: секрет с токеном шлюза подаётся ОТДЕЛЬНЫМ файлом с правами 600 и удаляется
-- в конце. «Временный» секрет SereneDB переживает сессию и виден любой другой —
-- `DROP SECRET` обязателен, сам он не исчезнет.
--
-- СОСТОЯНИЕ: Шаг 3 плана CHECK2_INCR_SUMMARY_V2 пройден — сборка идёт во ВРЕМЕННЫЕ
-- таблицы `tmp3_*` и сверяется с боевым корпусом построчно. Боевые объекты
-- (`search_corpus`, `search_idx`) не трогаются ни одной командой этого файла.
-- Шаг 4 (переключение сборщика и MERGE в боевой корпус) — не сделан.
--
-- [замер 27.07] Один запуск процесса `psql`, 1 мин 58 с, ноль строк наружу.
-- Против сегодняшней питоновской фазы: 258 с и около 1 190 запусков процесса.
-- Сверка с боевым корпусом: 97 965 строк сошлись по ключу, из них отпечаток совпал
-- у 62 756, разошёлся у 35 209, `amount` совпал у ВСЕХ, `doc_date` разошёлся у 90.
-- Каждое расхождение разобрано — см. docs/CHECK2_INCR_SUMMARY_V2.md и CHANGELOG.

-- ============ 1. $metadata: движок сам ходит в 1С и сам разбирает XML ============
CREATE OR REPLACE TABLE tmp3_ent AS
SELECT lower(regexp_extract(b,'Name="([^"]+)"',1)) AS entity, b AS body
FROM (SELECT unnest(regexp_extract_all(content,'(?s)<EntityType\s.*?</EntityType>')) AS b
      FROM read_text('http://127.0.0.1:6011/$metadata'));

CREATE OR REPLACE TABLE tmp3_prop AS
SELECT entity, x.prop, x.edm FROM (
  SELECT entity, regexp_extract(s,'<Property\s+Name="([^"]+)"\s+Type="([^"]+)"',['prop','edm']) AS x
  FROM (SELECT entity, unnest(regexp_extract_all(body,'<Property\s+Name="([^"]+)"\s+Type="([^"]+)"')) AS s
        FROM tmp3_ent));

CREATE OR REPLACE TABLE tmp3_key AS
SELECT entity, regexp_extract_all(regexp_extract(body,'(?s)<Key>(.*?)</Key>',1),
                                  '<PropertyRef\s+Name="([^"]+)"',1) AS key_cols
FROM tmp3_ent;

SELECT 'метаданные' AS шаг, (SELECT count(*) FROM tmp3_ent) AS сущностей,
       (SELECT count(*) FROM tmp3_prop) AS свойств,
       (SELECT count(*) FROM tmp3_key WHERE len(key_cols) > 0) AS с_ключом;

-- ============ 2. КЛАССИФИКАЦИЯ КОЛОНОК ============
-- ТАБЛИЦА, а не VIEW: коррелированный подзапрос к представлению с оконной функцией
-- роняет планировщик (LogicalProjection::GetExpression - table index mismatch).
CREATE OR REPLACE TABLE tmp3_cls AS
SELECT c.table_name AS tbl, c.column_index AS ord, c.column_name AS col, c.data_type, p.edm,
       CASE WHEN p.edm='Edm.Guid' THEN 'ref' WHEN p.edm='Edm.String' THEN 'text'
            WHEN p.edm='Edm.Boolean' THEN 'flag' WHEN p.edm='Edm.DateTime' THEN 'date'
            WHEN p.edm IN ('Edm.Double','Edm.Decimal','Edm.Int16','Edm.Int32','Edm.Int64','Edm.Byte') THEN 'num'
            WHEN p.edm IS NOT NULL THEN 'skip'
            WHEN EXISTS (SELECT 1 FROM tmp3_prop pe WHERE pe.entity=lower(c.table_name)) THEN 'skip'
            WHEN c.data_type='VARCHAR' THEN 'text' WHEN c.data_type='BOOLEAN' THEN 'flag'
            WHEN c.data_type LIKE 'TIMESTAMP%' OR c.data_type='DATE' THEN 'date'
            WHEN c.data_type IN ('BIGINT','INTEGER','DOUBLE','DECIMAL','SMALLINT','TINYINT') THEN 'num'
            ELSE 'skip' END AS kind,
       (c.column_name LIKE '%\_Type' AND EXISTS (SELECT 1 FROM tmp3_prop p2
            WHERE p2.entity=lower(c.table_name) AND p2.prop=regexp_replace(c.column_name,'_Type$',''))) AS is_companion,
       coalesce((SELECT k.key_cols=['Ref_Key'] FROM tmp3_key k WHERE k.entity=lower(c.table_name)),false) AS own_ref
FROM duckdb_columns() c
LEFT JOIN tmp3_prop p ON p.entity=lower(c.table_name) AND p.prop=c.column_name
WHERE c.database_name='postgres';

-- Источники корпуса: ровно те, что уже есть в боевом корпусе. Так сверка идёт по
-- одному и тому же множеству сущностей, а не по «похожему».
CREATE OR REPLACE TABLE tmp3_src AS
SELECT DISTINCT src_table AS tbl FROM search_corpus;

SELECT 'классификация' AS шаг, (SELECT count(*) FROM tmp3_src) AS сущностей_корпуса,
       (SELECT count(*) FROM tmp3_cls WHERE tbl IN (SELECT tbl FROM tmp3_src)) AS колонок;

-- ============ 3. КОЛОНКА-НАИМЕНОВАНИЕ и КАРТА ССЫЛОК ============
CREATE OR REPLACE TABLE tmp3_namecol (tbl VARCHAR, col VARCHAR, ord INT, score DOUBLE, std INT);
PREPARE p_stats AS
INSERT INTO tmp3_namecol
WITH n AS (SELECT count(*)::DOUBLE AS rows FROM query_table($1)),
     cells AS (SELECT * FROM (SELECT COLUMNS(*)::VARCHAR FROM query_table($1)) s
                    UNPIVOT (val FOR col IN (COLUMNS(*)))),
     agg AS (SELECT u.col,
                    avg(len(str_split(u.val,' '))) AS words,
                    avg(length(regexp_replace(u.val,'[^\p{L}]','','g'))::DOUBLE
                        / greatest(length(u.val),1)) AS alpha,
                    count(DISTINCT u.val)::DOUBLE/(SELECT rows FROM n) AS uniq,
                    bool_or(regexp_matches(u.val,'^(https?://|/)')) AS machine
             FROM cells u WHERE u.val<>'' GROUP BY u.col)
SELECT $1::VARCHAR, c.col, c.ord, a.words*a.alpha*a.uniq,
       CASE c.col WHEN 'Description' THEN 0 WHEN 'Code' THEN 1 ELSE 2 END
FROM agg a JOIN tmp3_cls c ON c.tbl=$1 AND c.col=a.col
WHERE c.kind='text' AND NOT c.is_companion AND c.col<>'DataVersion' AND NOT a.machine
QUALIFY c.col IN ('Description','Code')
     OR (a.words*a.alpha*a.uniq > 0
         AND a.words*a.alpha*a.uniq >= max(a.words*a.alpha*a.uniq) OVER () / 2);

SELECT 'EXECUTE p_stats(' || quote_literal(s.tbl) || ');'
FROM tmp3_src s JOIN tmp3_key k ON k.entity=lower(s.tbl)
WHERE k.key_cols=['Ref_Key']
\gexec

CREATE OR REPLACE TABLE tmp3_refmap (guid VARCHAR, name VARCHAR, owner VARCHAR);
PREPARE p_ref AS
INSERT INTO tmp3_refmap
WITH src AS (SELECT row_number() OVER () AS rid, COLUMNS(*)::VARCHAR FROM query_table($1)),
     cells AS (SELECT * FROM src UNPIVOT (val FOR col IN (COLUMNS(* EXCLUDE (rid))))),
     rows AS (SELECT u.rid,
                     max(u.val) FILTER (WHERE u.col='Ref_Key') AS guid,
                     list(u.val ORDER BY nc.std, nc.score DESC)
                       FILTER (WHERE nc.col IS NOT NULL AND u.val<>'') AS names
              FROM cells u LEFT JOIN tmp3_namecol nc ON nc.tbl=$1 AND nc.col=u.col
              GROUP BY u.rid)
SELECT guid,
       list_aggregate(list_reduce(names, (acc,x) -> CASE WHEN len(list_filter(acc, y -> contains(y,x)))>0
                                                          THEN acc ELSE list_append(acc,x) END, []::VARCHAR[]),
                      'string_agg', ' / ') AS name,
       $1::VARCHAR AS owner
FROM rows
WHERE guid IS NOT NULL AND guid <> '00000000-0000-0000-0000-000000000000'
  AND names IS NOT NULL AND len(names) > 0;

SELECT 'EXECUTE p_ref(' || quote_literal(s.tbl) || ');'
FROM tmp3_src s JOIN tmp3_key k ON k.entity=lower(s.tbl)
WHERE k.key_cols=['Ref_Key']
\gexec

SELECT 'карта ссылок' AS шаг, count(*) AS записей FROM tmp3_refmap;

-- ============ 4. ДАТА ЗАПИСИ ============
CREATE OR REPLACE TABLE tmp3_datecol AS
SELECT tbl, col FROM (
  SELECT tbl, col, ord, CASE col WHEN 'Date' THEN 0 WHEN 'Period' THEN 1 ELSE 2 END AS pr,
         count(*) OVER (PARTITION BY tbl) AS ndates,
         min(CASE col WHEN 'Date' THEN 0 WHEN 'Period' THEN 1 ELSE 2 END) OVER (PARTITION BY tbl) AS best
  FROM tmp3_cls WHERE kind='date')
WHERE (best < 2 AND pr = best) OR (best = 2 AND ndates = 1)
QUALIFY row_number() OVER (PARTITION BY tbl ORDER BY pr, ord) = 1;

-- ============ 5. КОЛОНКА ДЕНЕГ ============
-- Единственное решение, которого у движка нет: какое из чисел — деньги. Его принимает
-- языковая модель (п. 20 TARGET.md разрешает явно). Для СВЕРКИ мы не спрашиваем модель
-- заново, а восстанавливаем ЕЁ ЖЕ прошлый выбор из боевого корпуса: колонка денег та,
-- чьё имя стоит в тексте строки рядом со значением, равным полю amount. Это сверка,
-- а не работа продукта: в бою таблица заполняется ответом модели.
CREATE OR REPLACE TABLE tmp3_amountcol AS
SELECT DISTINCT c.tbl, c.col
FROM tmp3_cls c
JOIN search_corpus sc ON sc.src_table = c.tbl AND sc.amount IS NOT NULL
WHERE c.kind = 'num'
  AND contains(sc.doc, c.col || ': ' ||
        CASE WHEN sc.amount = floor(sc.amount) THEN printf('%d', sc.amount::BIGINT)
             ELSE printf('%.2f', sc.amount) END);

SELECT 'колонка денег' AS шаг, count(*) AS сущностей FROM tmp3_amountcol;

-- ============ 6. СБОРКА ТЕКСТА ============
CREATE OR REPLACE TABLE tmp3_corpus
  (src_table VARCHAR, row_key VARCHAR, doc VARCHAR, refs VARCHAR, doc_hash VARCHAR,
   amount DOUBLE, doc_date TIMESTAMP);

PREPARE p_doc AS
INSERT INTO tmp3_corpus
WITH kc AS (SELECT key_cols FROM tmp3_key WHERE entity = lower($1)),
 -- coalesce ДО unpivot: иначе пустые ячейки исчезают вовсе (UNPIVOT роняет NULL), и
 -- составной ключ схлопывается. Боевой ключ выглядит как «160.1|||ЛЕПРО|___|ЗП80РК» —
 -- пустые сегменты значимы, они держат позицию. Без них разные строки дают ОДИН ключ,
 -- то есть строка теряется молча (п. 13). Замерено: 789 строк из 97 965.
 -- ОБРЕЗКА ЗНАЧЕНИЯ. Хранилища и вложения приезжают в витрину как текст, и без обрезки
 -- строка корпуса вырастает до сотен тысяч символов. [замер 27.07] без неё самый длинный
 -- текст стал 560 400 символов против 15 724 у боевого кода, и две такие строки не могут
 -- получить вектор вовсе: у эмбеддера предел длины входа 33 000. Режем ЗНАЧЕНИЕ, а не
 -- строку целиком — так теряется хвост вложения, а не реквизиты (боевой аналог — clip()).
 src AS (SELECT row_number() OVER () AS rid, substr(coalesce(COLUMNS(*)::VARCHAR, ''), 1, 20000) FROM query_table($1)),
 cells AS (SELECT * FROM src UNPIVOT (val FOR col IN (COLUMNS(* EXCLUDE (rid))))),
 -- Ключ собирается ОТДЕЛЬНО и до отбрасывания пустых: он про тождество строки,
 -- а не про текст. Порядок сегментов — объявленный порядок ключа из $metadata.
 keyed AS (
   SELECT u.rid, string_agg(u.val, '|' ORDER BY list_position((SELECT key_cols FROM kc), u.col)) AS row_key
   FROM cells u
   WHERE list_position((SELECT key_cols FROM kc), u.col) IS NOT NULL
   GROUP BY u.rid),
 j AS (
   SELECT u.rid, u.col, u.val, c.ord, c.kind, c.own_ref,
          list_position((SELECT key_cols FROM kc), u.col) AS keypos,
          r.name AS refname,
          (c.kind='ref' OR regexp_full_match(u.val,'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}')) AS is_guid,
          (c.kind IN ('text','flag') AND NOT c.is_companion AND c.col <> 'DataVersion'
           AND NOT regexp_matches(u.val,'^(https?://|/)')) AS in_text,
          (SELECT 1 FROM tmp3_amountcol a WHERE a.tbl=$1 AND a.col=u.col) AS is_amt,
          (SELECT 1 FROM tmp3_datecol   d WHERE d.tbl=$1 AND d.col=u.col) AS is_dt
   FROM cells u JOIN tmp3_cls c ON c.tbl=$1 AND c.col=u.col
   LEFT JOIN tmp3_refmap r ON r.guid = u.val
   WHERE u.val <> ''),
 pieces AS (
   SELECT rid, ord, keypos, val, is_guid, refname, own_ref, col, is_amt, is_dt,
     CASE WHEN is_guid AND col='Ref_Key' AND own_ref THEN NULL
          WHEN is_guid AND refname IS NOT NULL THEN replace(col,'_Key','') || ': ' || refname
          WHEN is_guid THEN NULL
          WHEN is_amt IS NOT NULL THEN col || ': ' ||
               CASE WHEN try_cast(val AS DOUBLE) = floor(try_cast(val AS DOUBLE))
                    THEN printf('%d', try_cast(val AS BIGINT))
                    ELSE printf('%.2f', try_cast(val AS DOUBLE)) END
          WHEN is_dt IS NOT NULL THEN col || ': ' || substr(val,1,10)
          WHEN in_text THEN col || ': ' || val
          ELSE NULL END AS piece,
     CASE WHEN is_guid THEN 0 WHEN is_amt IS NOT NULL THEN 2 WHEN is_dt IS NOT NULL THEN 3 ELSE 1 END AS prio
   FROM j)
SELECT src_table,
       -- Без объявленного ключа и без Ref_Key ключом становится отпечаток текста —
       -- как в боевом коде, иначе строки с пустым ключом затирают друг друга.
       coalesce(row_key, sha1(doc)) AS row_key,
       doc, refs, sha1(doc || chr(0) || refs) AS doc_hash, amt, dt
FROM (
  SELECT $1::VARCHAR AS src_table,
         coalesce(any_value(k.row_key),
                  max(val) FILTER (is_guid AND col='Ref_Key' AND own_ref)) AS row_key,
         regexp_replace($1,'^[^_]*_','') || coalesce(' | ' || string_agg(piece,' | ' ORDER BY prio, ord)
                                                     FILTER (piece IS NOT NULL), '') AS doc,
         coalesce(string_agg(piece,' | ' ORDER BY ord) FILTER (is_guid AND refname IS NOT NULL), '') AS refs,
         max(try_cast(val AS DOUBLE))    FILTER (is_amt IS NOT NULL) AS amt,
         max(try_cast(val AS TIMESTAMP)) FILTER (is_dt  IS NOT NULL) AS dt
  FROM pieces LEFT JOIN keyed k USING (rid) GROUP BY rid) g;

SELECT 'EXECUTE p_doc(' || quote_literal(tbl) || ');' FROM tmp3_src
\gexec

-- ============ 7. СВЕРКА С БОЕВЫМ КОРПУСОМ ============
SELECT 'строк: новая формула' AS что, count(*) AS сколько FROM tmp3_corpus
UNION ALL SELECT 'строк: боевой корпус', count(*) FROM search_corpus;

SELECT count(*) AS сошлось_ключами,
       count(*) FILTER (WHERE c.doc_hash = t.doc_hash) AS отпечаток_совпал,
       count(*) FILTER (WHERE c.doc_hash <> t.doc_hash) AS отпечаток_разошёлся,
       count(*) FILTER (WHERE c.amount IS DISTINCT FROM t.amount) AS amount_разошёлся,
       count(*) FILTER (WHERE c.doc_date IS DISTINCT FROM t.doc_date) AS doc_date_разошёлся
FROM search_corpus c JOIN tmp3_corpus t USING (src_table, row_key);

SELECT 'нет в новой' AS сторона, count(*) FROM search_corpus c
  WHERE NOT EXISTS (SELECT 1 FROM tmp3_corpus t WHERE t.src_table=c.src_table AND t.row_key=c.row_key)
UNION ALL
SELECT 'нет в боевой', count(*) FROM tmp3_corpus t
  WHERE NOT EXISTS (SELECT 1 FROM search_corpus c WHERE c.src_table=t.src_table AND c.row_key=t.row_key);

-- ============ 8. ОТЧЁТ О КАЧЕСТВЕ КАРТЫ ИМЁН ============
-- П. 13 TARGET.md: то, что данные где-то потеряли качество, обязано быть ВИДНО, а не
-- зависеть от того, догадался ли человек посмотреть. Три числа считаются на любой базе
-- без единой настройки и без просмотра глазами (проверка «посмотреть выборку» не
-- универсальна: её нельзя ни повторить у клиента, ни выразить замером).
CREATE TABLE IF NOT EXISTS search_quality (k VARCHAR, v BIGINT, note VARCHAR);
DELETE FROM search_quality WHERE k LIKE 'refmap_%';
INSERT INTO search_quality
SELECT 'refmap_resolved', count(*), 'ссылок получили человеческое имя' FROM tmp3_refmap
UNION ALL
SELECT 'refmap_unresolved', count(*), 'GUID в корпусе без имени в карте'
FROM (SELECT DISTINCT val FROM (
        SELECT unnest(regexp_extract_all(doc,'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}')) val
        FROM search_corpus)
      WHERE val NOT IN (SELECT guid FROM tmp3_refmap))
UNION ALL
SELECT 'refmap_ambiguous', count(*), 'имён, которые делят между собой разные объекты'
FROM (SELECT name FROM tmp3_refmap GROUP BY name HAVING count(*) > 1);

SELECT k, v, note FROM search_quality WHERE k LIKE 'refmap_%' ORDER BY k;
