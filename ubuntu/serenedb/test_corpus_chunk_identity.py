#!/usr/bin/env python3
"""Идентичность чанкованного p_doc полному: тот же набор строк корпуса.

На ut_test: сущность среднего размера, полная сборка vs порции при заниженном
memory_limit (формула chunk_rows из corpus_build.sql). Сравнение — множества
(doc_hash, doc, refs, nums::VARCHAR, flags::VARCHAR, doc_date, refs_map::VARCHAR)
без учёта порядка; row_key может отличаться порядком #N только если doc совпадает.

Запуск: python3 test_corpus_chunk_identity.py
"""
import hashlib
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENTITY = "document_установкаценноменклатуры_товары"
MEM_LIMIT = "1GB"  # chunk_rows≈6250; полный p_doc ~0.5GiB на 12k строк
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


def _fingerprint_rows(raw):
    rows = []
    for line in raw.splitlines():
        if not line or line.startswith("FINGER|"):
            continue
        rows.append(line)
    return frozenset(rows)


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

    sql_path = ROOT / ".test_corpus_chunk_identity_run.sql"
    sql_path.write_text(
        f"""\\set ON_ERROR_STOP on
SET memory_limit = '{MEM_LIMIT}';
SET threads = 2;
SET preserve_insertion_order = false;

CREATE OR REPLACE TABLE tmp3_build AS SELECT '{ENTITY}'::VARCHAR AS tbl;
CREATE OR REPLACE TABLE tmp3_pdoc_cfg AS
WITH ml AS (SELECT current_setting('memory_limit') AS s),
     mem AS (
       SELECT CASE WHEN s LIKE '%GiB' THEN try_cast(regexp_extract(s, '^([0-9.]+)', 1) AS DOUBLE) * power(1024::BIGINT, 3)
                   WHEN upper(s) LIKE '%MIB' OR upper(s) LIKE '%MB'
                        THEN try_cast(regexp_extract(s, '^([0-9.]+)', 1) AS DOUBLE) * power(1024::BIGINT, 2)
                   ELSE try_cast(regexp_extract(s, '^([0-9.]+)', 1) AS DOUBLE) END AS mem_bytes
       FROM ml)
SELECT 2147483648.0 / 50000.0 AS ws_bytes_per_row, 0.25 AS mem_fraction,
       greatest(1000::BIGINT, floor((SELECT mem_bytes FROM mem) * 0.25 / (2147483648.0 / 50000.0))::BIGINT) AS chunk_rows
FROM mem;
CREATE OR REPLACE TABLE tmp3_entity_rows (tbl VARCHAR, nrows BIGINT);
DELETE FROM tmp3_entity_rows;
SELECT 'INSERT INTO tmp3_entity_rows SELECT '
       || quote_literal(b.tbl) || ', count(*)::BIGINT FROM query_table('
       || quote_literal(b.tbl) || ');'
FROM tmp3_build b
\\gexec
CREATE OR REPLACE TABLE tmp3_pdoc_chunks AS
SELECT e.tbl, gs AS lo, least(gs + cfg.chunk_rows - 1, e.nrows) AS hi, e.nrows
FROM tmp3_entity_rows e CROSS JOIN tmp3_pdoc_cfg cfg
CROSS JOIN LATERAL (SELECT unnest(generate_series(1::BIGINT, e.nrows, cfg.chunk_rows)) AS gs) g
WHERE e.nrows > cfg.chunk_rows;

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

-- full path (deallocate/recreate from corpus_build.sql tail not needed — use live prepares)
DELETE FROM tmp3_corpus;
\\set ON_ERROR_STOP off
EXECUTE p_doc('{ENTITY}');
\\set ON_ERROR_STOP on
CREATE OR REPLACE TABLE measure_full AS
SELECT doc_hash, doc, refs, nums::VARCHAR AS nums, flags::VARCHAR AS flags,
       doc_date, refs_map::VARCHAR AS refs_map, doc_hash AS fp
FROM tmp3_corpus WHERE src_table = '{ENTITY}';
SELECT 'FULL|' || count(*)::VARCHAR || '|' || (SELECT chunk_rows FROM tmp3_pdoc_cfg)::VARCHAR
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
    chunk_rows = chunks = 0
    hash_f = hash_c = ""
    for line in raw.splitlines():
        if line.startswith("FULL|"):
            parts = line.split("|")
            full_n, chunk_rows = int(parts[1]), int(parts[2])
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
    check("порог ниже размера сущности (идёт чанкование)", chunk_rows < n, f"chunk_rows={chunk_rows}")
    check("несколько порций", chunks >= 2, f"chunks={chunks}")
    check("полная сборка: строк", full_n == n, f"{full_n} vs {n}")
    check("чанкованная: строк", chunk_n == n, f"{chunk_n} vs {n}")
    check("только в полной: 0", only_full == 0, str(only_full))
    check("только в чанковой: 0", only_chunk == 0, str(only_chunk))
    check("doc_hash набор совпал", hash_f == hash_c and hash_f, f"{hash_f} vs {hash_c}")

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
