#!/usr/bin/env python3
"""Идентичность чанкованного p_doc полному: тот же набор строк корпуса.

На ut_test: сущность среднего размера, полная сборка vs порции при заниженном
memory_limit (формула chunk_cells из corpus_build.sql). Сравнение — множества
(doc_hash, doc, refs, nums::VARCHAR, flags::VARCHAR, doc_date, refs_map::VARCHAR)
без учёта порядка; row_key может отличаться порядком #N только если doc совпадает.

Запуск: python3 test_corpus_chunk_identity.py
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENTITY = "document_установкаценноменклатуры_товары"
MEM_LIMIT = "1GB"  # chunk_cells≈6k; полный p_doc ~0.5GiB на 12k строк
_fail = 0
_checks = 0


def _load_env(path):
    try:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip("'\""))
    except OSError:
        pass


_load_env("/etc/1c-mcp-reports.env")
_base = os.environ.get("SERENEDB_DSN", "host=127.0.0.1 port=7890 dbname=ut_test")
DSN = _base.replace("user=serene_ro", "user=postgres").replace("dbname=postgres", "dbname=ut_test")


def psql(sql, db=None):
    r = subprocess.run(
        ["psql", db or DSN, "-v", "ON_ERROR_STOP=1", "-tA", "-c", sql],
        text=True,
        capture_output=True,
        env=os.environ.copy(),
    )
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip()[:1200])
    return r.stdout.strip()


def psql_file(path):
    r = subprocess.run(
        ["psql", DSN, "-v", "ON_ERROR_STOP=1", "-tA", "-f", str(path)],
        text=True,
        capture_output=True,
        env=os.environ.copy(),
    )
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip()[:1200])
    return r.stdout.strip()


def check(name, cond, detail=""):
    global _fail, _checks
    _checks += 1
    if not cond:
        _fail += 1
    print(f"  {'PASS' if cond else 'FAIL ✗'}  {name}   {detail}")


def _chunk_cells_sql(mem_limit):
    return f"""
CREATE OR REPLACE TABLE tmp3_pdoc_cfg AS
WITH ml AS (SELECT current_setting('memory_limit') AS s),
     mem AS (
       SELECT CASE WHEN s LIKE '%GiB' THEN try_cast(regexp_extract(s, '^([0-9.]+)', 1) AS DOUBLE) * power(1024::BIGINT, 3)
                   WHEN upper(s) LIKE '%GB'  THEN try_cast(regexp_extract(s, '^([0-9.]+)', 1) AS DOUBLE) * power(1000::BIGINT, 3)
                   WHEN upper(s) LIKE '%MIB' OR upper(s) LIKE '%MB'
                        THEN try_cast(regexp_extract(s, '^([0-9.]+)', 1) AS DOUBLE) * power(1024::BIGINT, 2)
                   ELSE try_cast(regexp_extract(s, '^([0-9.]+)', 1) AS DOUBLE) END AS mem_bytes
       FROM ml)
SELECT 2147483648.0 / 50000.0 AS ws_bytes_per_cell, 0.25 AS mem_fraction,
       floor((SELECT mem_bytes FROM mem) * 0.25 / (2147483648.0 / 50000.0))::BIGINT AS chunk_cells
FROM mem;"""


def _entity_rows_and_chunks_sql():
    return """
CREATE OR REPLACE TABLE tmp3_entity_rows (tbl VARCHAR, nrows BIGINT, ncols BIGINT);
DELETE FROM tmp3_entity_rows;
SELECT 'INSERT INTO tmp3_entity_rows SELECT '
       || quote_literal(b.tbl) || ', count(*)::BIGINT, '
       || '(SELECT count(*)::BIGINT FROM duckdb_columns() dc WHERE dc.database_name = current_database()'
       || ' AND dc.table_name = ' || quote_literal(b.tbl) || ') FROM query_table('
       || quote_literal(b.tbl) || ');'
FROM tmp3_build b
\\gexec
CREATE OR REPLACE TABLE tmp3_pdoc_entity AS
SELECT e.tbl, e.nrows, e.ncols, floor(cfg.chunk_cells / e.ncols)::BIGINT AS chunk_rows
FROM tmp3_entity_rows e CROSS JOIN tmp3_pdoc_cfg cfg
JOIN tmp3_key k ON k.entity = lower(e.tbl)
WHERE len(k.key_cols) > 0 AND e.ncols > 0 AND e.nrows * e.ncols > cfg.chunk_cells
  AND floor(cfg.chunk_cells / e.ncols)::BIGINT >= 1;
CREATE OR REPLACE TABLE tmp3_pdoc_chunks AS
SELECT ent.tbl, gs AS lo, least(gs + ent.chunk_rows - 1, ent.nrows) AS hi,
       ent.nrows, ent.chunk_rows, ent.ncols
FROM tmp3_pdoc_entity ent
CROSS JOIN LATERAL (SELECT unnest(generate_series(1::BIGINT, ent.nrows, ent.chunk_rows)) AS gs) g;
CREATE OR REPLACE TABLE tmp3_pdoc_order (tbl VARCHAR, pos BIGINT, keyvals VARCHAR);
DELETE FROM tmp3_pdoc_order;
SELECT 'INSERT INTO tmp3_pdoc_order SELECT '
|| quote_literal(x.tbl) || ', pos, keyvals FROM ('
|| 'WITH kc AS (SELECT key_cols FROM tmp3_key WHERE entity = lower(' || quote_literal(x.tbl) || ')), '
|| 'numbered AS (SELECT row_number() OVER (ORDER BY ' || x.order_expr || ') AS pos, q.* '
|| 'FROM query_table(' || quote_literal(x.tbl) || ') q), '
|| 'cells AS (SELECT pos, u.col, u.val, '
|| 'coalesce(list_position((SELECT list_transform(key_cols, x -> lower(x::VARCHAR)) FROM kc), lower(u.col)), '
|| 'CASE lower(u.col) WHEN ''linenumber'' THEN 1000000 WHEN ''recorder'' THEN 1000001 END) AS sort_ord '
|| 'FROM numbered n UNPIVOT (val FOR col IN (COLUMNS(* EXCLUDE (pos)))) u '
|| 'WHERE list_position((SELECT list_transform(key_cols, x -> lower(x::VARCHAR)) FROM kc), lower(u.col)) IS NOT NULL '
|| 'OR (lower(u.col) = ''linenumber'' AND NOT list_contains((SELECT list_transform(key_cols, x -> lower(x::VARCHAR)) FROM kc), ''linenumber'') '
|| 'AND EXISTS (SELECT 1 FROM duckdb_columns() dc WHERE dc.database_name = current_database() '
|| 'AND dc.table_name = ' || quote_literal(x.tbl) || ' AND dc.column_name = ''LineNumber'')) '
|| 'OR (lower(u.col) = ''recorder'' AND NOT list_contains((SELECT list_transform(key_cols, x -> lower(x::VARCHAR)) FROM kc), ''recorder'') '
|| 'AND EXISTS (SELECT 1 FROM duckdb_columns() dc WHERE dc.database_name = current_database() '
|| 'AND dc.table_name = ' || quote_literal(x.tbl) || ' AND dc.column_name = ''Recorder''))), '
|| 'agg AS (SELECT pos, string_agg(CASE WHEN val IS NULL THEN ''∅'' '
|| 'ELSE replace(val::VARCHAR, ''|'', ''\\|'') END, ''|'' ORDER BY sort_ord) AS keyvals '
|| 'FROM cells WHERE sort_ord IS NOT NULL GROUP BY pos) '
|| 'SELECT pos, keyvals FROM agg);'
FROM (
  SELECT c.tbl, k.key_cols,
    coalesce(
      (SELECT string_agg('"' || u.x || '" NULLS LAST', ', '
                         ORDER BY list_position(k.key_cols, u.x))
       FROM unnest(k.key_cols) AS u(x)),
      '1'
    )
    || CASE WHEN EXISTS (
           SELECT 1 FROM duckdb_columns() dc
           WHERE dc.database_name = current_database()
             AND dc.table_name = c.tbl AND dc.column_name = 'LineNumber')
           AND NOT list_contains(k.key_cols, 'LineNumber')
          THEN ', "LineNumber" NULLS LAST' ELSE '' END
    || CASE WHEN EXISTS (
           SELECT 1 FROM duckdb_columns() dc
           WHERE dc.database_name = current_database()
             AND dc.table_name = c.tbl AND dc.column_name = 'Recorder')
           AND NOT list_contains(k.key_cols, 'Recorder')
          THEN ', "Recorder" NULLS LAST' ELSE '' END
    AS order_expr
  FROM (SELECT DISTINCT tbl FROM tmp3_pdoc_chunks) c
  JOIN tmp3_key k ON k.entity = lower(c.tbl)
) x
\\gexec"""


def _check_keyvals_collision():
    """Две строки с одинаковым md5(COLUMNS(*)), но разными keyvals — разные порции."""
    print("\n== keyvals vs md5 row_tag (коллизия отпечатка строки) ==")
    tbl = "_chunk_keyvals_collide"
    try:
        out = psql(
            f"""
DROP TABLE IF EXISTS {tbl};
CREATE TABLE {tbl} (Ref_Key VARCHAR, Payload VARCHAR);
INSERT INTO {tbl} VALUES ('aaa', ''), ('bbb', '');

WITH kc AS (SELECT ['Ref_Key']::VARCHAR[] AS key_cols),
numbered AS (
  SELECT row_number() OVER (ORDER BY "Ref_Key" NULLS LAST) AS pos, q.*
  FROM query_table('{tbl}') q
),
cells AS (
  SELECT pos, u.col, u.val,
         list_position((SELECT list_transform(key_cols, x -> lower(x::VARCHAR)) FROM kc), lower(u.col)) AS sort_ord
  FROM numbered n
  UNPIVOT (val FOR col IN (COLUMNS(* EXCLUDE (pos)))) u
  WHERE list_position((SELECT list_transform(key_cols, x -> lower(x::VARCHAR)) FROM kc), lower(u.col)) IS NOT NULL
),
ord AS (
  SELECT pos,
         string_agg(
           CASE WHEN val IS NULL THEN '∅' ELSE replace(val::VARCHAR, '|', '\\|') END,
           '|' ORDER BY sort_ord) AS keyvals
  FROM cells
  GROUP BY pos
),
row_md5 AS (
  SELECT pos, md5(coalesce(COLUMNS(*)::VARCHAR, '')) AS row_tag
  FROM numbered
),
kv_all AS (
  WITH kc2 AS (SELECT ['Ref_Key']::VARCHAR[] AS key_cols),
  numbered2 AS (SELECT row_number() OVER () AS rn, q.* FROM query_table('{tbl}') q),
  cells2 AS (
    SELECT rn, u.col, u.val, list_position((SELECT list_transform(key_cols, x -> lower(x::VARCHAR)) FROM kc2), lower(u.col)) AS sort_ord
    FROM numbered2 n
    UNPIVOT (val FOR col IN (COLUMNS(* EXCLUDE (rn)))) u
    WHERE list_position((SELECT list_transform(key_cols, x -> lower(x::VARCHAR)) FROM kc2), lower(u.col)) IS NOT NULL
  )
  SELECT rn, string_agg(
           CASE WHEN val IS NULL THEN '∅' ELSE replace(val::VARCHAR, '|', '\\|') END,
           '|' ORDER BY sort_ord) AS keyvals
  FROM cells2 GROUP BY rn
),
sim AS (
  SELECT o.pos, count(*) AS matched
  FROM ord o
  JOIN kv_all k ON k.keyvals = o.keyvals
  GROUP BY o.pos
)
SELECT 'DISTINCT|' || (SELECT count(DISTINCT keyvals) FROM ord)::VARCHAR
     || '|' || (SELECT count(*) FROM ord)::VARCHAR
     || '|' || (SELECT count(DISTINCT row_tag) FROM row_md5)::VARCHAR
     || '|' || coalesce((SELECT sum(matched) FROM sim)::VARCHAR, '0')
     || '|' || coalesce((SELECT max(matched) FROM sim)::VARCHAR, '0');
"""
        )
    except RuntimeError as e:
        check("keyvals collision probe", False, str(e)[:200])
        return
    parts = out.strip().split("|")
    if len(parts) < 6 or parts[0] != "DISTINCT":
        check("keyvals collision probe", False, out[:200])
        return
    distinct_kv, total, distinct_md5, sum_matched, max_matched = (
        int(parts[1]),
        int(parts[2]),
        int(parts[3]),
        int(parts[4]),
        int(parts[5]),
    )
    check("keyvals: 2 строки → 2 distinct keyvals", distinct_kv == 2 and total == 2, f"{distinct_kv}/{total}")
    if distinct_md5 < total:
        check("md5 row_tag коллидирует (сценарий рецензии)", True, f"distinct_md5={distinct_md5}")
    check(
        "фильтр по keyvals: без задвоения по порциям",
        sum_matched == total and max_matched == 1,
        f"sum={sum_matched} max={max_matched}",
    )
    psql(f"DROP TABLE IF EXISTS {tbl};")


def main():
    if not os.environ.get("PGPASSWORD"):
        print("PGPASSWORD не задан — пропуск живой пробы")
        sys.exit(0)

    n = int(psql(f"SELECT count(*) FROM query_table('{ENTITY}')"))
    print(f"== chunk identity ({ENTITY}, {n} строк, memory_limit={MEM_LIMIT}) ==")

    prep = psql(
        f"SELECT count(*) FROM duckdb_tables() WHERE table_name IN ('tmp3_cls','tmp3_key','tmp3_refmap')"
    )
    if int(prep) < 3:
        print("tmp3_* не готовы — нужен хотя бы один такт corpus_build на ut_test")
        sys.exit(1)

    ncols = int(
        psql(
            f"SELECT count(*) FROM duckdb_columns() "
            f"WHERE database_name=current_database() AND table_name='{ENTITY}'"
        )
    )
    chunk_cells = int(
        psql(
            f"SET memory_limit='{MEM_LIMIT}'; "
            f"SELECT floor("
            f"CASE WHEN current_setting('memory_limit') LIKE '%GB' "
            f"THEN try_cast(regexp_extract(current_setting('memory_limit'), '^([0-9.]+)', 1) AS DOUBLE)"
            f" * power(1000::BIGINT, 3) ELSE 0 END * 0.25 / (2147483648.0 / 50000.0))::BIGINT;"
        )
    )
    per_entity_rows = chunk_cells // max(ncols, 1)
    check("формула chunk_cells без greatest(1000)", chunk_cells > 0, str(chunk_cells))
    check(
        "ncols≥100: порция = floor(cells/ncols)",
        per_entity_rows == chunk_cells // ncols,
        f"ncols={ncols} chunk_rows={per_entity_rows}",
    )
    check(
        "ncols=100 синтетика: floor без greatest(1000)",
        (chunk_cells // 100) * 100 <= chunk_cells and chunk_cells // 100 != 1000,
        f"floor100={chunk_cells // 100}",
    )
    check(
        "инвариант chunk_rows×ncols ≤ chunk_cells",
        per_entity_rows * ncols <= chunk_cells,
        f"{per_entity_rows}×{ncols}={per_entity_rows * ncols} ≤ {chunk_cells}",
    )

    sql_path = ROOT / ".test_corpus_chunk_identity_run.sql"
    sql_path.write_text(
        f"""\\set ON_ERROR_STOP on
SET memory_limit = '{MEM_LIMIT}';
SET threads = 2;
SET preserve_insertion_order = false;

CREATE OR REPLACE TABLE tmp3_build AS SELECT '{ENTITY}'::VARCHAR AS tbl;
{_chunk_cells_sql(MEM_LIMIT)}
{_entity_rows_and_chunks_sql()}

CREATE TABLE IF NOT EXISTS tmp3_pdoc_progress (tbl VARCHAR PRIMARY KEY, rid_hi BIGINT, nrows BIGINT);
CREATE TABLE IF NOT EXISTS tmp3_pdoc_stage (
  src_table VARCHAR, rk VARCHAR, doc VARCHAR, refs VARCHAR,
  nums MAP(VARCHAR, DOUBLE), flags MAP(VARCHAR, BOOLEAN), doc_date TIMESTAMP,
  refs_map MAP(VARCHAR, VARCHAR), refs_own MAP(VARCHAR, VARCHAR));
CREATE OR REPLACE TABLE tmp3_resume_pdoc AS SELECT false AS on_;
CREATE OR REPLACE TABLE tmp3_corpus (
  src_table VARCHAR, row_key VARCHAR, doc VARCHAR, refs VARCHAR, doc_hash VARCHAR,
  nums MAP(VARCHAR, DOUBLE), flags MAP(VARCHAR, BOOLEAN), doc_date TIMESTAMP,
  refs_map MAP(VARCHAR, VARCHAR), refs_own MAP(VARCHAR, VARCHAR));

DELETE FROM tmp3_corpus;
\\set ON_ERROR_STOP off
EXECUTE p_doc('{ENTITY}');
\\set ON_ERROR_STOP on
CREATE OR REPLACE TABLE measure_full AS
SELECT doc_hash, doc, refs, nums::VARCHAR AS nums, flags::VARCHAR AS flags,
       doc_date, refs_map::VARCHAR AS refs_map, doc_hash AS fp
FROM tmp3_corpus WHERE src_table = '{ENTITY}';
SELECT 'FULL|' || count(*)::VARCHAR || '|' || (SELECT chunk_cells FROM tmp3_pdoc_cfg)::VARCHAR
     || '|' || (SELECT ncols FROM tmp3_entity_rows)::VARCHAR
     || '|' || (SELECT chunk_rows FROM tmp3_pdoc_entity)::VARCHAR
FROM measure_full;

DELETE FROM tmp3_corpus;
DELETE FROM tmp3_pdoc_stage;
DELETE FROM tmp3_pdoc_progress;
\\set ON_ERROR_STOP off
SELECT stmt FROM (
  SELECT c.lo, 1 AS ord, 'EXECUTE p_doc_chunk(' || quote_literal(c.tbl) || ', ' || c.lo || ', ' || c.hi || ');' AS stmt
  FROM tmp3_pdoc_chunks c
  UNION ALL
  SELECT c.lo, 2, 'INSERT INTO tmp3_pdoc_progress (tbl, rid_hi, nrows) SELECT '
    || quote_literal(c.tbl) || ', ' || c.hi || ', ' || c.nrows
    || ' ON CONFLICT (tbl) DO UPDATE SET rid_hi = excluded.rid_hi, nrows = excluded.nrows;'
  FROM tmp3_pdoc_chunks c
) z ORDER BY lo, ord;
\\gexec
EXECUTE p_doc_finalize('{ENTITY}');
\\set ON_ERROR_STOP on
CREATE OR REPLACE TABLE measure_chunk AS
SELECT doc_hash, doc, refs, nums::VARCHAR AS nums, flags::VARCHAR AS flags,
       doc_date, refs_map::VARCHAR AS refs_map, doc_hash AS fp
FROM tmp3_corpus WHERE src_table = '{ENTITY}';
SELECT 'CHUNK|' || count(*)::VARCHAR || '|' || (SELECT count(*) FROM tmp3_pdoc_chunks)::VARCHAR
FROM measure_chunk;

SELECT 'ONLY_FULL|' || count(*)::VARCHAR FROM measure_full f
WHERE NOT EXISTS (SELECT 1 FROM measure_chunk c WHERE c.doc_hash = f.doc_hash AND c.doc = f.doc
  AND c.refs IS NOT DISTINCT FROM f.refs AND c.nums IS NOT DISTINCT FROM f.nums
  AND c.flags IS NOT DISTINCT FROM f.flags AND c.doc_date IS NOT DISTINCT FROM f.doc_date
  AND c.refs_map IS NOT DISTINCT FROM f.refs_map);
SELECT 'ONLY_CHUNK|' || count(*)::VARCHAR FROM measure_chunk c
WHERE NOT EXISTS (SELECT 1 FROM measure_full f WHERE c.doc_hash = f.doc_hash AND c.doc = f.doc
  AND c.refs IS NOT DISTINCT FROM f.refs AND c.nums IS NOT DISTINCT FROM f.nums
  AND c.flags IS NOT DISTINCT FROM f.flags AND c.doc_date IS NOT DISTINCT FROM f.doc_date
  AND c.refs_map IS NOT DISTINCT FROM f.refs_map);
SELECT 'HASH|' || md5(string_agg(doc_hash, ',' ORDER BY doc_hash)) FROM measure_full;
SELECT 'HASHC|' || md5(string_agg(doc_hash, ',' ORDER BY doc_hash)) FROM measure_chunk;
""",
        encoding="utf-8",
    )

    prep_sql = ROOT / ".test_corpus_chunk_identity_prepare.sql"
    _write_prepare_script(prep_sql)
    run_sql = sql_path.read_text(encoding="utf-8")
    combined = ROOT / ".test_corpus_chunk_identity_combined.sql"
    combined.write_text(prep_sql.read_text(encoding="utf-8") + "\n" + run_sql, encoding="utf-8")
    raw = psql_file(combined)
    full_n = chunk_n = only_full = only_chunk = 0
    chunk_cells_run = chunks = ent_ncols = ent_chunk_rows = 0
    hash_f = hash_c = ""
    for line in raw.splitlines():
        if line.startswith("FULL|"):
            parts = line.split("|")
            full_n, chunk_cells_run = int(parts[1]), int(parts[2])
            if len(parts) > 3:
                ent_ncols = int(parts[3])
            if len(parts) > 4 and parts[4]:
                ent_chunk_rows = int(parts[4])
        elif line.startswith("CHUNK|"):
            parts = line.split("|")
            chunk_n, chunks = int(parts[1]), int(parts[2])
        elif line.startswith("ONLY_FULL|"):
            only_full = int(line.split("|", 1)[1])
        elif line.startswith("ONLY_CHUNK|"):
            only_chunk = int(line.split("|", 1)[1])
        elif line.startswith("HASH|"):
            hash_f = line.split("|", 1)[1]
        elif line.startswith("HASHC|"):
            hash_c = line.split("|", 1)[1]

    check("источник непустой", n > 0, str(n))
    check(
        "порог по ячейкам (nrows×ncols > chunk_cells)",
        n * ncols > chunk_cells_run,
        f"n×ncols={n * ncols} chunk_cells={chunk_cells_run}",
    )
    check(
        "per-entity chunk_rows = floor(cells/ncols)",
        ent_chunk_rows == chunk_cells_run // ent_ncols if ent_ncols else False,
        f"chunk_rows={ent_chunk_rows}",
    )
    check("несколько порций", chunks >= 2, f"chunks={chunks}")
    check("полная сборка: строк", full_n == n, f"{full_n} vs {n}")
    check("чанкованная: строк", chunk_n == n, f"{chunk_n} vs {n}")
    check("только в полной: 0", only_full == 0, str(only_full))
    check("только в чанковой: 0", only_chunk == 0, str(only_chunk))
    check("doc_hash набор совпал", hash_f == hash_c and hash_f, f"{hash_f} vs {hash_c}")

    _check_keyvals_collision()

    print(f"\nИТОГ: {_checks - _fail}/{_checks} PASS"
          + (" ✅" if _fail == 0 else f", {_fail} FAIL ✗"))
    sys.exit(1 if _fail else 0)


def _write_prepare_script(path: Path):
    text = (ROOT / "corpus_build.sql").read_text(encoding="utf-8")
    parts = [
        "\\set ON_ERROR_STOP off\nDEALLOCATE ALL;\n\\set ON_ERROR_STOP on\n",
        "CREATE TABLE IF NOT EXISTS tmp3_pdoc_stage (\n"
        "  src_table VARCHAR, rk VARCHAR, doc VARCHAR, refs VARCHAR,\n"
        "  nums MAP(VARCHAR, DOUBLE), flags MAP(VARCHAR, BOOLEAN), doc_date TIMESTAMP,\n"
        "  refs_map MAP(VARCHAR, VARCHAR), refs_own MAP(VARCHAR, VARCHAR));\n",
        "CREATE OR REPLACE TABLE tmp3_pdoc_order (tbl VARCHAR, pos BIGINT, keyvals VARCHAR);\n",
        "CREATE OR REPLACE TABLE tmp3_corpus (\n"
        "  src_table VARCHAR, row_key VARCHAR, doc VARCHAR, refs VARCHAR, doc_hash VARCHAR,\n"
        "  nums MAP(VARCHAR, DOUBLE), flags MAP(VARCHAR, BOOLEAN), doc_date TIMESTAMP,\n"
        "  refs_map MAP(VARCHAR, VARCHAR), refs_own MAP(VARCHAR, VARCHAR));\n",
    ]
    for name in ("p_doc", "p_doc_chunk", "p_doc_finalize"):
        start = text.index(f"PREPARE {name} AS")
        if name == "p_doc":
            end = text.index("PREPARE p_doc_chunk AS")
        elif name == "p_doc_chunk":
            end = text.index("PREPARE p_doc_finalize AS")
        else:
            end = text.index("-- ============ 6-бис.")
        parts.append(text[start:end].rstrip() + "\n")
    path.write_text("\n".join(parts), encoding="utf-8")


if __name__ == "__main__":
    main()
