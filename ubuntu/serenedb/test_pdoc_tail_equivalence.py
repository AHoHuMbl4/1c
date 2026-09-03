#!/usr/bin/env python3
"""Замок M2: V5-хвост коллизий ≡ монолитный p_doc (план TAKT_SPEED §2.5 / §4).

Фикстуры в движке; сверки — запросами (строки корпуса наружу не выгружаются).
Запуск: python3 ubuntu/serenedb/test_pdoc_tail_equivalence.py

DSN: SERENEDB_DSN / PGPASSWORD, иначе эфемерный serened на свободном порту
(боевой :7890 может быть занят тактом — это не дефект замка).
"""
from __future__ import annotations

import atexit
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BUILD = ROOT / "corpus_build.sql"
INIT = ROOT / "corpus_init.sql"

_fail = 0
_checks = 0
_ephem = None  # (proc, datadir, port)


def _load_env(path: str) -> None:
    try:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip("'\""))
    except OSError:
        pass


for _p in ("/etc/1c-serene-pipeline-ut_test.env", "/etc/1c-mcp-reports.env"):
    _load_env(_p)


def check(name: str, cond: bool, detail: str = "") -> None:
    global _fail, _checks
    _checks += 1
    if not cond:
        _fail += 1
    print(f"  {'PASS' if cond else 'FAIL ✗'}  {name}   {detail}")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _cleanup_ephem() -> None:
    global _ephem
    if not _ephem:
        return
    proc, datadir, _port = _ephem
    try:
        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=5)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
    shutil.rmtree(datadir, ignore_errors=True)
    _ephem = None


def _try_dsn(dsn: str, timeout_sec: float = 3.0) -> bool:
    try:
        r = subprocess.run(
            ["psql", dsn, "-v", "ON_ERROR_STOP=1", "-tA", "-c", "SELECT 1"],
            text=True,
            capture_output=True,
            env=os.environ.copy(),
            timeout=timeout_sec,
        )
        return r.returncode == 0 and r.stdout.strip() == "1"
    except (subprocess.TimeoutExpired, OSError):
        return False


def _start_ephemeral() -> str:
    """Поднять эфемерный serened на свободном порту (не трогает боевой :7890)."""
    global _ephem
    port = _free_port()
    datadir = tempfile.mkdtemp(prefix="pdoc-tail-m2-")
    log = open(Path(datadir) / "serened.log", "w", encoding="utf-8")
    proc = subprocess.Popen(
        ["serened", datadir, f"--listen=postgres://127.0.0.1:{port}", "--log_storage=stdout"],
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    _ephem = (proc, datadir, port)
    atexit.register(_cleanup_ephem)
    dsn = f"host=127.0.0.1 port={port} user=postgres dbname=postgres connect_timeout=5"
    for _ in range(40):
        if proc.poll() is not None:
            raise RuntimeError(f"serened умер при старте: {(Path(datadir) / 'serened.log').read_text()[-800:]}")
        if _try_dsn(dsn, timeout_sec=1.5):
            print(f"== DSN (эфемерный serened): port={port} dir={datadir}")
            return dsn
        time.sleep(0.25)
    raise RuntimeError("эфемерный serened не ответил")


def resolve_dsn() -> str:
    """Живой DSN: env (если отвечает) иначе эфемерный serened.

    PDOC_TAIL_FORCE_EPHEMERAL=1 — только эфемерный (замок не трогает боевой :7890).
    """
    if os.environ.get("PDOC_TAIL_FORCE_EPHEMERAL", "").strip().lower() in ("1", "true", "yes"):
        return _start_ephemeral()
    base = os.environ.get("SERENEDB_DSN", "").strip()
    candidates = []
    if base and "port=" in base:
        d = base.replace("user=serene_ro", "user=postgres")
        if "dbname=" not in d:
            d += " dbname=postgres"
        candidates.append(d)
    candidates.append("host=127.0.0.1 port=7890 user=postgres dbname=ut_test connect_timeout=2")
    candidates.append("host=127.0.0.1 port=7890 user=postgres dbname=postgres connect_timeout=2")
    for dsn in candidates:
        if _try_dsn(dsn):
            print(f"== DSN (живой): {re.sub(r'password=\\S+', 'password=***', dsn, flags=re.I)}")
            return dsn
    return _start_ephemeral()


DSN = ""


def psql(sql: str) -> str:
    r = subprocess.run(
        ["psql", DSN, "-v", "ON_ERROR_STOP=1", "-tA", "-c", sql],
        text=True,
        capture_output=True,
        env=os.environ.copy(),
        timeout=120,
    )
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip()[:2000])
    return r.stdout.strip()


def psql_file(path: Path) -> str:
    r = subprocess.run(
        ["psql", DSN, "-v", "ON_ERROR_STOP=1", "-tA", "-f", str(path)],
        text=True,
        capture_output=True,
        env=os.environ.copy(),
        timeout=300,
    )
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip()[:2500])
    return r.stdout.strip()




def write_run_sql(path: Path, body: str) -> None:
    """Только PREPARE + тело — одна сессия; key/cls/фикстуры не трогаем."""
    path.write_text(_bootstrap_prepare_only() + "\n" + body, encoding="utf-8")

def _extract_macros() -> str:
    """corpus_content_hash зависит от corpus_doc_bmap — оба из corpus_init.sql."""
    text = INIT.read_text(encoding="utf-8")
    start = text.index("CREATE OR REPLACE MACRO corpus_doc_bmap")
    end = text.index("CREATE OR REPLACE MACRO corpus_content_hash")
    m_hash = re.search(
        r"CREATE OR REPLACE MACRO corpus_content_hash\(doc\) AS \([\s\S]*?\n\);",
        text[end : end + 2500],
    )
    if not m_hash:
        raise RuntimeError("corpus_content_hash не найден в corpus_init.sql")
    m_bmap = re.search(
        r"CREATE OR REPLACE MACRO corpus_doc_bmap\(doc\) AS \([\s\S]*?\n\);",
        text[start : end + 50],
    )
    if not m_bmap:
        raise RuntimeError("corpus_doc_bmap не найден в corpus_init.sql")
    return m_bmap.group(0) + "\n\n" + m_hash.group(0)


def _extract_prepare(name: str) -> str:
    text = BUILD.read_text(encoding="utf-8")
    start = text.index(f"PREPARE {name} AS")
    if name == "p_doc":
        end = text.index("PREPARE p_doc_chunk AS")
    elif name == "p_doc_chunk":
        end = text.index("PREPARE p_doc_tail AS")
    elif name == "p_doc_tail":
        end = text.index("PREPARE p_doc_finalize AS")
    elif name == "p_doc_finalize":
        end = text.index("-- ============ 6-бис.")
    else:
        raise ValueError(name)
    return text[start:end].rstrip() + "\n"


def _extract_fresh_wipe_from_file() -> str:
    """Свежий-wipe из corpus_build.sql: от «-- Хвост — артефакт плана» до конца DELETE _done.

    Если перед комментарием в том же разделе есть DELETE stage/progress — захватываем
    и их (полный wipe из файла). Якорь не найден → RuntimeError (FAIL).
    """
    text = BUILD.read_text(encoding="utf-8")
    marker = "-- Хвост — артефакт плана"
    mi = text.find(marker)
    if mi < 0:
        raise RuntimeError("якорь «-- Хвост — артефакт плана» не найден в corpus_build.sql")
    stage = text.rfind("DELETE FROM tmp3_pdoc_stage s", 0, mi)
    # stage/progress того же раздела — не дальше ~400 символов до комментария
    start = stage if (stage >= 0 and mi - stage < 500) else mi
    d = text.find("DELETE FROM tmp3_pdoc_tail_done", mi)
    if d < 0:
        raise RuntimeError("DELETE tmp3_pdoc_tail_done после «артефакт плана» не найден")
    semi = text.find(";", d)
    if semi < 0:
        raise RuntimeError("конец DELETE tmp3_pdoc_tail_done не найден")
    block = text[start : semi + 1]
    if marker not in block or "DELETE FROM tmp3_pdoc_tail_done" not in block:
        raise RuntimeError("вырезанный fresh-wipe не содержит обязательных якорей")
    return block


def _extract_fresh_wipe_section_for_grep() -> str:
    """Блок fresh-wipe для оффлайн-негатива: от «артефакт плана» до следующего раздела."""
    text = BUILD.read_text(encoding="utf-8")
    marker = "-- Хвост — артефакт плана"
    mi = text.find(marker)
    if mi < 0:
        raise RuntimeError("якорь «-- Хвост — артефакт плана» не найден в corpus_build.sql")
    end = None
    for nxt in ("SELECT 'pdoc лимиты'", "PREPARE p_doc AS"):
        k = text.find(nxt, mi + len(marker))
        if k >= 0:
            end = k if end is None else min(end, k)
    if end is None:
        raise RuntimeError("следующий раздел после fresh-wipe не найден")
    return text[mi:end]


def _extract_battle_tail_dispatch_from_file() -> str:
    """SELECT-диспетчер хвоста из corpus_build.sql (от «Хвост+маркер» / SELECT до \\gexec)."""
    text = BUILD.read_text(encoding="utf-8")
    comment = "-- Хвост+маркер"
    sel = "SELECT 'EXECUTE p_doc_tail("
    ci = text.find(comment)
    if ci >= 0:
        si = text.find(sel, ci)
        start = ci if si >= 0 else -1
    else:
        si = text.find(sel)
        start = si
    if start < 0 or si < 0:
        raise RuntimeError(
            "якорь диспетчера хвоста («Хвост+маркер» / SELECT 'EXECUTE p_doc_tail() не найден"
        )
    ge = text.find("\\gexec", si)
    if ge < 0:
        raise RuntimeError("\\gexec после диспетчера хвоста не найден")
    return text[start : ge + len("\\gexec")]


def _offline_structure() -> None:
    print("\n== оффлайн: структура corpus_build.sql ==")
    text = BUILD.read_text(encoding="utf-8")
    check("есть PREPARE p_doc_tail", "PREPARE p_doc_tail AS" in text)
    check("есть tmp3_pdoc_tail", "CREATE TABLE IF NOT EXISTS tmp3_pdoc_tail" in text)
    check("есть tmp3_pdoc_tail_done", "CREATE TABLE IF NOT EXISTS tmp3_pdoc_tail_done" in text)
    check(
        "атомарный хвост+маркер (multi-statement без BEGIN)",
        "'EXECUTE p_doc_tail(' || quote_literal(t.tbl)" in text
        and "INSERT INTO tmp3_pdoc_tail_done VALUES (" in text
        and "BEGIN TRANSACTION; EXECUTE p_doc_tail(" not in text,
    )
    check("гейт покрытия collision_rows", "count(order)+collision_rows" in text.replace(" ", ""))
    check(
        "гейт без формы count(DISTINCT tail)",
        "count(order)+count(DISTINCT" not in text.replace(" ", "")
        and "count(*)+count(DISTINCT" not in text.replace(" ", ""),
    )
    # stage_gate: нет исключения fold
    sg = text[text.index("stage_gate AS") : text.index("tail_gate AS")]
    check("stage_gate без NOT fold", "NOT (SELECT on_ FROM fold)" not in sg)
    check(
        "нет QUALIFY fold-подзапроса (X6)",
        "QUALIFY NOT (SELECT on_ FROM fold)" not in text,
    )
    check(
        "fin2/rn rewrite финализатора (X6)",
        "f.on_ AS fold_on FROM mid CROSS JOIN fold f)" in text
        and "WHERE NOT rn.fold_on OR rn.rn = 1" in text,
    )
    check("tail_gate перед finalize", "хвост коллизий не собран" in text)
    check("зеркало-комментарий", "p_doc / p_doc_chunk / p_doc_tail" in text)
    # жизненный цикл: formula / fresh (_done) / post-finalize; план хвоста на fresh не стирается
    check("lifecycle wipe formula", "смена formula" in text or "Жизненный цикл хвоста" in text)
    check(
        "lifecycle fresh: _done стирается, tail-план нет",
        "DELETE FROM tmp3_pdoc_tail_done d\nWHERE EXISTS (SELECT 1 FROM tmp3_pdoc_chunks c WHERE c.tbl = d.tbl)\n  AND NOT (SELECT on_ FROM tmp3_resume_pdoc);"
        in text
        and "артефакт плана" in text,
    )
    # оффлайн-негатив BUG-1: в блоке fresh-wipe нет DELETE хвоста (кроме _done)
    try:
        wipe_sec = _extract_fresh_wipe_section_for_grep()
        wipe_ok = True
        wipe_detail = ""
    except RuntimeError as e:
        wipe_sec = ""
        wipe_ok = False
        wipe_detail = str(e)
    check("якорь fresh-wipe для оффлайн-негатива", wipe_ok, wipe_detail)
    if wipe_ok:
        # запрещены DELETE FROM tmp3_pdoc_tail t / WHERE / без суффикса _done
        bad_tail = re.search(
            r"DELETE\s+FROM\s+tmp3_pdoc_tail(?:\s+(?:t|WHERE)\b|(?:\s*;))",
            wipe_sec,
            re.IGNORECASE,
        )
        bad_any = re.search(
            r"DELETE\s+FROM\s+tmp3_pdoc_tail\b(?!\s*_done)",
            wipe_sec,
            re.IGNORECASE,
        )
        check(
            "offline BUG-1: fresh-wipe без DELETE tmp3_pdoc_tail",
            not bad_tail and not bad_any,
            (bad_any or bad_tail).group(0) if (bad_any or bad_tail) else "",
        )
    check(
        "lifecycle wipe after finalize",
        "DELETE FROM tmp3_pdoc_tail t\nWHERE EXISTS (SELECT 1 FROM tmp3_corpus" in text,
    )
    n_tail_done_del = text.count("DELETE FROM tmp3_pdoc_tail_done")
    check("tail_done стирается ≥3 раз", n_tail_done_del >= 3, str(n_tail_done_del))
    # фильтр tail
    tail = _extract_prepare("p_doc_tail")
    check(
        "p_doc_tail фильтр из tmp3_pdoc_tail",
        "FROM tmp3_pdoc_tail" in tail and "pos BETWEEN" not in tail,
    )
    chunk = _extract_prepare("p_doc_chunk")
    check("p_doc_chunk сохранил pos BETWEEN", "pos BETWEEN" in chunk)



def _bootstrap_prepare_only() -> str:
    """Только DEALLOCATE + PREPARE — не трогает tmp3_key/cls/фикстуры."""
    return "\n".join(
        [
            "\\set ON_ERROR_STOP on",
            "DEALLOCATE ALL;",
            _extract_prepare("p_doc"),
            _extract_prepare("p_doc_chunk"),
            _extract_prepare("p_doc_tail"),
            _extract_prepare("p_doc_finalize"),
        ]
    )


def _bootstrap_sql() -> str:
    cell_num = """
CREATE OR REPLACE MACRO corpus_cell_num(val) AS
  try_cast(replace(replace(replace(trim(CAST(val AS VARCHAR)), chr(160), ''), ' ', ''), ',', '.')
           AS DOUBLE);
"""
    return "\n".join(
        [
            "\\set ON_ERROR_STOP on",
            "DEALLOCATE ALL;",
            cell_num,
            _extract_macros() + ";",
            """
CREATE TABLE IF NOT EXISTS search_quality (k VARCHAR, v BIGINT, note VARCHAR);
CREATE TABLE IF NOT EXISTS tmp3_pdoc_progress (tbl VARCHAR PRIMARY KEY, rid_hi BIGINT, nrows BIGINT);
CREATE TABLE IF NOT EXISTS tmp3_pdoc_stage (
  src_table VARCHAR, rk VARCHAR, doc VARCHAR, refs VARCHAR,
  nums MAP(VARCHAR, DOUBLE), flags MAP(VARCHAR, BOOLEAN), doc_date TIMESTAMP,
  refs_map MAP(VARCHAR, VARCHAR), refs_own MAP(VARCHAR, VARCHAR));
CREATE TABLE IF NOT EXISTS tmp3_pdoc_tail (tbl VARCHAR, keyvals VARCHAR);
CREATE TABLE IF NOT EXISTS tmp3_pdoc_tail_done (tbl VARCHAR);
CREATE OR REPLACE TABLE tmp3_pdoc_order (tbl VARCHAR, pos BIGINT, keyvals VARCHAR);
CREATE OR REPLACE TABLE tmp3_refmap AS
  SELECT ''::VARCHAR AS guid, ''::VARCHAR AS name, ''::VARCHAR AS owner WHERE false;
CREATE OR REPLACE TABLE tmp3_datecol AS
  SELECT ''::VARCHAR AS tbl, ''::VARCHAR AS col WHERE false;
CREATE OR REPLACE TABLE tmp3_src AS
  SELECT ''::VARCHAR AS tbl WHERE false;
CREATE OR REPLACE TABLE tmp3_run AS
  SELECT TIMESTAMP '1970-01-01' AS ts WHERE false;
CREATE OR REPLACE TABLE search_pdoc_formula AS
  SELECT ''::VARCHAR AS tbl, ''::VARCHAR AS formula WHERE false;
CREATE OR REPLACE TABLE tmp3_key AS
  SELECT ''::VARCHAR AS entity, []::VARCHAR[] AS key_cols WHERE false;
CREATE OR REPLACE TABLE tmp3_cls AS
  SELECT ''::VARCHAR AS tbl, 0::BIGINT AS ord, ''::VARCHAR AS col, ''::VARCHAR AS data_type,
         NULL::VARCHAR AS edm, ''::VARCHAR AS kind, false AS is_companion, false AS own_ref,
         true AS own_prop, ''::VARCHAR AS decl_entity WHERE false;
CREATE OR REPLACE TABLE tmp3_pdoc_chunks AS
  SELECT ''::VARCHAR AS tbl, 0::BIGINT AS lo, 0::BIGINT AS hi,
         0::BIGINT AS nrows, 0::BIGINT AS chunk_rows, 0::BIGINT AS ncols WHERE false;
CREATE OR REPLACE TABLE search_refcols AS
  SELECT ''::VARCHAR AS src_table, ''::VARCHAR AS col, ''::VARCHAR AS target_src WHERE false;
CREATE OR REPLACE TABLE tmp3_corpus (
  src_table VARCHAR, row_key VARCHAR, doc VARCHAR, refs VARCHAR, doc_hash VARCHAR,
  nums MAP(VARCHAR, DOUBLE), flags MAP(VARCHAR, BOOLEAN), doc_date TIMESTAMP,
  refs_map MAP(VARCHAR, VARCHAR), refs_own MAP(VARCHAR, VARCHAR), content_hash VARCHAR);
""",
            _extract_prepare("p_doc"),
            _extract_prepare("p_doc_chunk"),
            _extract_prepare("p_doc_tail"),
            _extract_prepare("p_doc_finalize"),
        ]
    )


def _install_entity(tbl: str, key_cols: list[str], cols_kinds: dict[str, str]) -> str:
    """SQL: tmp3_key + tmp3_cls + tmp3_src для синтетической витрины."""
    keys = "[" + ", ".join(f"'{c}'" for c in key_cols) + "]::VARCHAR[]"
    cls_rows = []
    for i, (col, kind) in enumerate(cols_kinds.items(), start=1):
        own_ref = "true" if key_cols == ['Ref_Key'] else "false"
        cls_rows.append(
            f"SELECT '{tbl}', {i}, '{col}', 'VARCHAR', NULL::VARCHAR, '{kind}', "
            f"false, {own_ref}, true, lower('{tbl}')"
        )
    cls_union = "\nUNION ALL\n".join(cls_rows)
    return f"""
DELETE FROM tmp3_src;
INSERT INTO tmp3_src SELECT '{tbl}';
CREATE OR REPLACE TABLE tmp3_key AS
SELECT lower('{tbl}') AS entity, {keys} AS key_cols;
CREATE OR REPLACE TABLE tmp3_cls AS
SELECT * FROM (
  {cls_union}
) x(tbl, ord, col, data_type, edm, kind, is_companion, own_ref, own_prop, decl_entity);
"""


def _keyvals_expr_sql(tbl: str, key_cols: list[str]) -> str:
    """То же выражение keyvals, что order/chunk (NULL→∅)."""
    kc = "[" + ", ".join(f"'{c}'" for c in key_cols) + "]::VARCHAR[]"
    return f"""
WITH kc AS (SELECT {kc} AS key_cols),
numbered AS (
  SELECT row_number() OVER (ORDER BY {", ".join(f'"{c}" NULLS LAST' for c in key_cols)}) AS pos, q.*
  FROM query_table('{tbl}') q
),
cells AS (
  SELECT pos, u.col, u.val,
         list_position((SELECT list_transform(key_cols, x -> lower(x::VARCHAR)) FROM kc), lower(u.col)) AS sort_ord
  FROM numbered n
  UNPIVOT INCLUDE NULLS (val FOR col IN (COLUMNS(* EXCLUDE (pos)))) u
  WHERE list_position((SELECT list_transform(key_cols, x -> lower(x::VARCHAR)) FROM kc), lower(u.col)) IS NOT NULL
),
agg AS (
  SELECT pos, string_agg(
           CASE WHEN val IS NULL THEN '∅' ELSE replace(val::VARCHAR, '|', '\\|') END,
           '|' ORDER BY sort_ord) AS keyvals
  FROM cells WHERE sort_ord IS NOT NULL GROUP BY pos
)
SELECT pos, keyvals FROM agg
"""


def _build_order_and_decide(tbl: str, chunk_cells: int, key_cols: list[str]) -> str:
    """Материализует order + V5/mono решение (зеркало блока из corpus_build)."""
    return f"""
CREATE OR REPLACE TABLE tmp3_pdoc_cfg AS
SELECT 1.0 AS ws_bytes_per_cell, 0.25 AS mem_fraction, {chunk_cells}::BIGINT AS chunk_cells;

CREATE OR REPLACE TABLE tmp3_entity_rows AS
SELECT '{tbl}'::VARCHAR AS tbl,
       (SELECT count(*)::BIGINT FROM query_table('{tbl}')) AS nrows,
       (SELECT count(*)::BIGINT FROM duckdb_columns()
         WHERE database_name=current_database() AND table_name='{tbl}') AS ncols;

CREATE OR REPLACE TABLE tmp3_pdoc_formula AS
SELECT e.tbl, md5('v8c' || 'key_order' || cfg.chunk_cells::VARCHAR || '|' || e.ncols::VARCHAR) AS formula
FROM tmp3_entity_rows e CROSS JOIN tmp3_pdoc_cfg cfg
WHERE e.nrows * e.ncols > cfg.chunk_cells
  AND cfg.chunk_cells >= e.ncols;  -- ≡ floor(cells/ncols)≥1 (без floor: баг движка на AND с nrows*ncols);

CREATE OR REPLACE TABLE tmp3_pdoc_entity AS
SELECT e.tbl, e.nrows, e.ncols, floor(cfg.chunk_cells / e.ncols)::BIGINT AS chunk_rows
FROM tmp3_entity_rows e CROSS JOIN tmp3_pdoc_cfg cfg
WHERE e.nrows * e.ncols > cfg.chunk_cells
  AND cfg.chunk_cells >= e.ncols;  -- ≡ floor(cells/ncols)≥1 (без floor: баг движка на AND с nrows*ncols);

CREATE OR REPLACE TABLE tmp3_pdoc_chunks AS
SELECT ent.tbl, gs AS lo, least(gs + ent.chunk_rows - 1, ent.nrows) AS hi,
       ent.nrows, ent.chunk_rows, ent.ncols
FROM tmp3_pdoc_entity ent
CROSS JOIN LATERAL (SELECT unnest(generate_series(1::BIGINT, ent.nrows, ent.chunk_rows)) AS gs) g;

DELETE FROM tmp3_pdoc_order;
INSERT INTO tmp3_pdoc_order
SELECT '{tbl}', pos, keyvals FROM ({_keyvals_expr_sql(tbl, key_cols)});

-- --- решение V5 / mono (как в corpus_build) ---
DELETE FROM tmp3_pdoc_tail WHERE tbl = '{tbl}';

CREATE OR REPLACE TABLE tmp3_pdoc_mono AS
SELECT e.tbl FROM tmp3_entity_rows e
WHERE EXISTS (SELECT 1 FROM tmp3_pdoc_entity pe WHERE pe.tbl = e.tbl)
  AND (SELECT count(*) FROM tmp3_pdoc_order o WHERE o.tbl = e.tbl) <> e.nrows;

CREATE OR REPLACE TABLE tmp3_pdoc_collision AS
WITH coll_keys AS (
  SELECT o.tbl, o.keyvals FROM tmp3_pdoc_order o
  WHERE EXISTS (SELECT 1 FROM tmp3_pdoc_entity pe WHERE pe.tbl = o.tbl)
    AND o.tbl NOT IN (SELECT m.tbl FROM tmp3_pdoc_mono m)
  GROUP BY o.tbl, o.keyvals HAVING count(*) > 1
),
coll_rows AS (
  SELECT o.tbl, count(*)::BIGINT AS collision_rows
  FROM tmp3_pdoc_order o
  JOIN coll_keys ck ON ck.tbl = o.tbl AND ck.keyvals IS NOT DISTINCT FROM o.keyvals
  GROUP BY o.tbl
)
SELECT cr.tbl, cr.collision_rows, e.nrows, e.ncols, cfg.chunk_cells,
       (cr.collision_rows * e.ncols > cfg.chunk_cells) AS oversize
FROM coll_rows cr
JOIN tmp3_entity_rows e ON e.tbl = cr.tbl
CROSS JOIN tmp3_pdoc_cfg cfg;

INSERT INTO tmp3_pdoc_mono
SELECT c.tbl FROM tmp3_pdoc_collision c WHERE c.oversize
  AND c.tbl NOT IN (SELECT m.tbl FROM tmp3_pdoc_mono m);

DELETE FROM tmp3_pdoc_tail WHERE tbl IN (SELECT tbl FROM tmp3_pdoc_mono);
DELETE FROM tmp3_pdoc_tail_done WHERE tbl IN (SELECT tbl FROM tmp3_pdoc_mono);
DELETE FROM tmp3_pdoc_order WHERE tbl IN (SELECT tbl FROM tmp3_pdoc_mono);
DELETE FROM tmp3_pdoc_chunks WHERE tbl IN (SELECT tbl FROM tmp3_pdoc_mono);
DELETE FROM tmp3_pdoc_formula WHERE tbl IN (SELECT tbl FROM tmp3_pdoc_mono);
DELETE FROM tmp3_pdoc_entity WHERE tbl IN (SELECT tbl FROM tmp3_pdoc_mono);

INSERT INTO tmp3_pdoc_tail
SELECT ck.tbl, ck.keyvals FROM (
  SELECT o.tbl, o.keyvals FROM tmp3_pdoc_order o
  JOIN tmp3_pdoc_collision c ON c.tbl = o.tbl AND NOT c.oversize
  GROUP BY o.tbl, o.keyvals HAVING count(*) > 1
) ck;

-- collision_rows до DELETE уже в tmp3_pdoc_collision
CREATE OR REPLACE TABLE tmp3_pdoc_collision_saved AS SELECT * FROM tmp3_pdoc_collision;

DELETE FROM tmp3_pdoc_order o
WHERE EXISTS (
  SELECT 1 FROM tmp3_pdoc_tail t
  WHERE t.tbl = o.tbl AND t.keyvals IS NOT DISTINCT FROM o.keyvals
);

SELECT CASE
  WHEN EXISTS (
    SELECT 1 FROM tmp3_pdoc_collision c
    WHERE NOT c.oversize
      AND c.tbl NOT IN (SELECT m.tbl FROM tmp3_pdoc_mono m)
      AND (SELECT count(*) FROM tmp3_pdoc_order o WHERE o.tbl = c.tbl) + c.collision_rows <> c.nrows
  ) THEN error('pdoc_tail: count(order)+collision_rows <> nrows')
END;

DELETE FROM search_quality WHERE k = 'pdoc_tail_oversize' OR k LIKE 'pdoc_tail:%';
INSERT INTO search_quality
SELECT 'pdoc_tail_oversize', count(*)::BIGINT, 'сущностей с хвостом > chunk_cells'
FROM tmp3_pdoc_collision WHERE oversize;
INSERT INTO search_quality
SELECT 'pdoc_tail:' || x.tbl, x.tail_rows,
       'nrows=' || x.nrows::VARCHAR || ' ncols=' || x.ncols::VARCHAR || ' path=' || x.path
FROM (
  SELECT m.tbl, 0::BIGINT AS tail_rows, e.nrows, e.ncols, 'mono_incomplete'::VARCHAR AS path
  FROM tmp3_pdoc_mono m JOIN tmp3_entity_rows e ON e.tbl = m.tbl
  WHERE m.tbl NOT IN (SELECT c.tbl FROM tmp3_pdoc_collision c)
  UNION ALL
  SELECT c.tbl, c.collision_rows, c.nrows, c.ncols,
         CASE WHEN c.oversize THEN 'mono_oversize' ELSE 'v5' END
  FROM tmp3_pdoc_collision c
) x;
"""


def _run_chunk_tail_finalize(tbl: str) -> str:
    return f"""
DELETE FROM tmp3_corpus WHERE src_table = '{tbl}';
DELETE FROM tmp3_pdoc_stage WHERE src_table = '{tbl}';
DELETE FROM tmp3_pdoc_progress WHERE tbl = '{tbl}';
-- маркеры хвоста для этой сущности сбрасываем только если нет resume-сценария снаружи
SELECT stmt FROM (
  SELECT c.lo, 1 AS ord,
         'EXECUTE p_doc_chunk(' || quote_literal(c.tbl) || ', ' || c.lo || ', ' || c.hi || ');' AS stmt
  FROM tmp3_pdoc_chunks c WHERE c.tbl = '{tbl}'
  UNION ALL
  SELECT c.lo, 2,
         'INSERT INTO tmp3_pdoc_progress (tbl, rid_hi, nrows) SELECT '
           || quote_literal(c.tbl) || ', ' || c.hi || '::BIGINT, ' || c.nrows
           || '::BIGINT ON CONFLICT (tbl) DO UPDATE SET rid_hi = excluded.rid_hi, nrows = excluded.nrows;'
  FROM tmp3_pdoc_chunks c WHERE c.tbl = '{tbl}'
) z ORDER BY lo, ord;
\\gexec

SELECT 'STAGE_BEFORE_TAIL|' || count(*)::VARCHAR FROM tmp3_pdoc_stage WHERE src_table = '{tbl}';

SELECT stmt FROM (
  SELECT 1 AS ord, 'EXECUTE p_doc_tail(' || quote_literal(t.tbl) || ');' AS stmt
  FROM (SELECT DISTINCT tbl FROM tmp3_pdoc_tail WHERE tbl = '{tbl}') t
  WHERE NOT EXISTS (SELECT 1 FROM tmp3_pdoc_tail_done d WHERE d.tbl = t.tbl)
  UNION ALL
  SELECT 2, 'INSERT INTO tmp3_pdoc_tail_done VALUES (' || quote_literal(t.tbl) || ');'
  FROM (SELECT DISTINCT tbl FROM tmp3_pdoc_tail WHERE tbl = '{tbl}') t
  WHERE NOT EXISTS (SELECT 1 FROM tmp3_pdoc_tail_done d WHERE d.tbl = t.tbl)
) z ORDER BY ord;
\\gexec

SELECT 'STAGE_AFTER_TAIL|' || count(*)::VARCHAR
     || '|NROWS|' || (SELECT nrows::VARCHAR FROM tmp3_entity_rows WHERE tbl='{tbl}')
FROM tmp3_pdoc_stage WHERE src_table = '{tbl}';

EXECUTE p_doc_finalize('{tbl}');

SELECT 'MULTI|' || md5(string_agg(content_hash || chr(1) || row_key, chr(2) ORDER BY content_hash, row_key))
     || '|N|' || count(*)::VARCHAR
FROM tmp3_corpus WHERE src_table = '{tbl}';
"""


def _run_mono(tbl: str) -> str:
    return f"""
DELETE FROM tmp3_corpus WHERE src_table = '{tbl}';
EXECUTE p_doc('{tbl}');
SELECT 'MULTI|' || md5(string_agg(content_hash || chr(1) || row_key, chr(2) ORDER BY content_hash, row_key))
     || '|N|' || count(*)::VARCHAR
FROM tmp3_corpus WHERE src_table = '{tbl}';
"""


def _parse_multi(out: str) -> tuple[str, int]:
    for line in out.splitlines():
        if line.startswith("MULTI|"):
            parts = line.split("|")
            return parts[1], int(parts[3])
    raise RuntimeError(f"нет MULTI в выводе: {out[-400:]}")


def _setup_empty_cls() -> None:
    """Очистка стейджа между кейсами. Без CREATE OR REPLACE corpus — иначе гонка с прошлым INSERT."""
    for stmt in (
        "DELETE FROM tmp3_corpus;",
        "DELETE FROM tmp3_pdoc_stage;",
        "DELETE FROM tmp3_pdoc_progress;",
        "DELETE FROM tmp3_pdoc_tail;",
        "DELETE FROM tmp3_pdoc_tail_done;",
        "DELETE FROM search_quality;",
    ):
        try:
            psql(stmt)
        except RuntimeError:
            pass
    time.sleep(0.15)


def test_v5_equivalence_and_coverage() -> None:
    print("\n== V5: коллизии + пустой ключ (∅) → multiset == mono ==")
    tbl = "_m2_v5_collide"
    psql(f"DROP TABLE IF EXISTS {tbl};")
    # Id — ключ; Payload различает контент. Три строки с Id='dup', две с NULL Id (∅), одна уникальная.
    psql(
        f"""
CREATE TABLE {tbl} (id VARCHAR, payload VARCHAR, qty VARCHAR);
INSERT INTO {tbl} VALUES
  ('dup', 'a', '1'), ('dup', 'b', '2'), ('dup', 'c', '3'),
  (NULL, 'n1', '10'), (NULL, 'n2', '20'),
  ('uniq', 'u', '99');
"""
    )
    _setup_empty_cls()
    psql(_install_entity(tbl, ['id'], {"id": "text", "payload": "text", "qty": "text"}))

    # chunk_cells достаточно большой для V5, но порог чанкования пройден
    nrows = int(psql(f"SELECT count(*) FROM {tbl}"))
    ncols = 3
    # V5: nrows*ncols > chunk_cells (чанкование) И collision_rows*ncols <= chunk_cells
    # при collision_rows=5 → 15 <= cells < 18
    chunk_cells = 15
    assert nrows * ncols > chunk_cells

    boot = Path(tempfile.mkdtemp(prefix="m2-sql-")) / "boot.sql"
    # bootstrap already applied once; just decision+run
    decide = ROOT / ".test_pdoc_tail_decide_v5.sql"
    decide.write_text(
        "\\set ON_ERROR_STOP on\n"
        + _build_order_and_decide(tbl, chunk_cells, ['id'])
        + f"""
SELECT 'PATH|' || coalesce((SELECT note FROM search_quality WHERE k='pdoc_tail:{tbl}'), 'none');
SELECT 'COLL_ROWS|' || coalesce((SELECT collision_rows::VARCHAR FROM tmp3_pdoc_collision_saved WHERE tbl='{tbl}'),'0');
SELECT 'ORDER_AFTER|' || (SELECT count(*)::VARCHAR FROM tmp3_pdoc_order WHERE tbl='{tbl}');
SELECT 'TAIL_DIST|' || (SELECT count(DISTINCT keyvals)::VARCHAR FROM tmp3_pdoc_tail WHERE tbl='{tbl}');
SELECT 'COVER_OK|' || CASE
  WHEN (SELECT count(*) FROM tmp3_pdoc_order WHERE tbl='{tbl}')
     + coalesce((SELECT collision_rows FROM tmp3_pdoc_collision_saved WHERE tbl='{tbl}'),0)
     = (SELECT nrows FROM tmp3_entity_rows WHERE tbl='{tbl}')
  THEN '1' ELSE '0' END;
SELECT 'IN_CHUNKS|' || CASE WHEN EXISTS (SELECT 1 FROM tmp3_pdoc_chunks WHERE tbl='{tbl}') THEN '1' ELSE '0' END;
"""
    )
    out = psql_file(decide)
    path_note = next((l.split("|", 1)[1] for l in out.splitlines() if l.startswith("PATH|")), "")
    coll_rows = int(next(l.split("|", 1)[1] for l in out.splitlines() if l.startswith("COLL_ROWS|")))
    order_after = int(next(l.split("|", 1)[1] for l in out.splitlines() if l.startswith("ORDER_AFTER|")))
    tail_dist = int(next(l.split("|", 1)[1] for l in out.splitlines() if l.startswith("TAIL_DIST|")))
    cover = next(l.split("|", 1)[1] for l in out.splitlines() if l.startswith("COVER_OK|"))
    in_chunks = next(l.split("|", 1)[1] for l in out.splitlines() if l.startswith("IN_CHUNKS|"))

    check("путь v5", "path=v5" in path_note, path_note)
    check("collision_rows = 3+2 (dup+NULL)", coll_rows == 5, str(coll_rows))
    check("покрытие order+collision_rows", cover == "1", f"order={order_after} coll={coll_rows}")
    check("сверка НЕ через count(tail)", order_after + coll_rows == nrows and tail_dist == 2, f"tail_dist={tail_dist}")
    check("сущность осталась в chunks", in_chunks == "1")

    # mono эталон
    mono_sql = ROOT / ".test_pdoc_tail_mono_v5.sql"
    write_run_sql(mono_sql, "\\set ON_ERROR_STOP on\n" + _run_mono(tbl))
    mono_out = psql_file(mono_sql)
    mono_h, mono_n = _parse_multi(mono_out)

    # V5 путь
    # пересобрать order/chunks после mono прогона
    psql_file(decide)
    v5_sql = ROOT / ".test_pdoc_tail_v5_run.sql"
    write_run_sql(v5_sql, "\\set ON_ERROR_STOP on\n" + _run_chunk_tail_finalize(tbl))
    v5_out = psql_file(v5_sql)
    stage_line = next(l for l in v5_out.splitlines() if l.startswith("STAGE_AFTER_TAIL|"))
    # STAGE_AFTER_TAIL|N|NROWS|NROWS
    parts = stage_line.split("|")
    stage_n, nrows_s = int(parts[1]), int(parts[3])
    check("stage_rows == nrows (non-fold)", stage_n == nrows_s == nrows, stage_line)
    v5_h, v5_n = _parse_multi(v5_out)
    check("multiset content_hash,row_key == mono", v5_h == mono_h and v5_n == mono_n, f"{v5_n} vs {mono_n}")


def _finalize_select_sql(tbl: str) -> str:
    """Финальный SELECT финализатора (WITH…SELECT) с $1 → литерал — для EXPLAIN."""
    body = _extract_prepare("p_doc_finalize")
    wi = body.index("WITH ")
    sql = body[wi:].rstrip().rstrip(";")
    return sql.replace("$1", f"'{tbl}'")


def _explain_finalize_plan(tbl: str) -> str:
    """EXPLAIN финального SELECT финализатора на живом движке фикстуры."""
    path = ROOT / f".test_pdoc_tail_explain_{tbl}.sql"
    path.write_text(
        "\\set ON_ERROR_STOP on\nEXPLAIN\n" + _finalize_select_sql(tbl) + ";\n",
        encoding="utf-8",
    )
    return psql_file(path)


def test_fold_finalize_plan_and_semantics() -> None:
    """X6: fold-TRUE multiset ≡ mono; EXPLAIN финализатора без BLOCKWISE_NL_JOIN (и fold-FALSE)."""
    print("\n== fold X6: multiset ≡ mono + EXPLAIN без BLOCKWISE_NL_JOIN ==")
    tbl = "_m2_fold_x6"
    psql(f"DROP TABLE IF EXISTS {tbl};")
    psql(
        f"""
CREATE TABLE {tbl} ("Ref_Key" VARCHAR, name VARCHAR, n VARCHAR);
INSERT INTO {tbl} VALUES
  ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa1', 'x', '1'),
  ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa1', 'y', '2'),
  ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa2', 'z', '3'),
  ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa3', 'w', '4'),
  ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa3', 'w2', '5'),
  ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa4', 'q', '6');
"""
    )
    _setup_empty_cls()
    psql(_install_entity(tbl, ['Ref_Key'], {"Ref_Key": "ref", "name": "text", "n": "text"}))
    nrows = 6
    chunk_cells = 12  # 6*3=18 > 12; collision~4*3=12 ≤ 12 → V5
    decide = ROOT / ".test_pdoc_tail_fold_x6_decide.sql"
    decide.write_text(
        "\\set ON_ERROR_STOP on\n" + _build_order_and_decide(tbl, chunk_cells, ['Ref_Key'])
    )
    psql_file(decide)
    in_chunks = int(psql(f"SELECT count(*) FROM tmp3_pdoc_chunks WHERE tbl='{tbl}'"))
    if in_chunks == 0:
        check("fold-x6 ушёл в mono (сверка V5 недоступна)", False, "oversize/mono")
        return

    mono_sql = ROOT / ".test_pdoc_tail_fold_x6_mono.sql"
    write_run_sql(mono_sql, "\\set ON_ERROR_STOP on\n" + _run_mono(tbl))
    mono_h, mono_n = _parse_multi(psql_file(mono_sql))

    psql_file(decide)
    v5_sql = ROOT / ".test_pdoc_tail_fold_x6_run.sql"
    write_run_sql(v5_sql, "\\set ON_ERROR_STOP on\n" + _run_chunk_tail_finalize(tbl))
    v5_out = psql_file(v5_sql)
    v5_h, v5_n = _parse_multi(v5_out)
    check(
        "fold-TRUE multiset == mono",
        v5_h == mono_h and v5_n == mono_n,
        f"v5={v5_n}/{v5_h[:8]} mono={mono_n}/{mono_h[:8]}",
    )
    check("fold-TRUE сверка схлопнула объекты", v5_n == 4 and nrows == 6, f"n={v5_n}")

    plan_fold = _explain_finalize_plan(tbl)
    check(
        "fold-TRUE EXPLAIN без BLOCKWISE_NL_JOIN",
        "BLOCKWISE_NL_JOIN" not in plan_fold,
        plan_fold[:300].replace("\n", " | "),
    )

    # fold-FALSE санити: тот же финальный SELECT, ключ ≠ ['Ref_Key']
    tbl2 = "_m2_nofold_x6"
    psql(f"DROP TABLE IF EXISTS {tbl2};")
    psql(
        f"""
CREATE TABLE {tbl2} (id VARCHAR, payload VARCHAR);
INSERT INTO {tbl2} VALUES ('a','1'),('b','2'),('c','3');
"""
    )
    _setup_empty_cls()
    psql(_install_entity(tbl2, ['id'], {"id": "text", "payload": "text"}))
    # минимальный stage + progress, чтобы план читал base (гейты не error)
    psql(
        f"""
DELETE FROM tmp3_pdoc_stage WHERE src_table='{tbl2}';
INSERT INTO tmp3_pdoc_stage
SELECT '{tbl2}', id, 'doc-'||id, '', MAP{{}}::MAP(VARCHAR,DOUBLE),
       MAP{{}}::MAP(VARCHAR,BOOLEAN), NULL::TIMESTAMP,
       MAP{{}}::MAP(VARCHAR,VARCHAR), MAP{{}}::MAP(VARCHAR,VARCHAR)
FROM {tbl2};
DELETE FROM tmp3_pdoc_progress WHERE tbl='{tbl2}';
INSERT INTO tmp3_pdoc_progress VALUES ('{tbl2}', 3, 3);
DELETE FROM tmp3_pdoc_chunks WHERE tbl='{tbl2}';
INSERT INTO tmp3_pdoc_chunks VALUES ('{tbl2}', 1, 3, 3, 3, 2);
DELETE FROM tmp3_pdoc_tail WHERE tbl='{tbl2}';
DELETE FROM tmp3_pdoc_tail_done WHERE tbl='{tbl2}';
"""
    )
    plan_nf = _explain_finalize_plan(tbl2)
    check(
        "fold-FALSE EXPLAIN без BLOCKWISE_NL_JOIN",
        "BLOCKWISE_NL_JOIN" not in plan_nf,
        plan_nf[:300].replace("\n", " | "),
    )


def test_fold_stage_rows() -> None:
    print("\n== fold: stage_rows == nrows до finalize ==")
    tbl = "_m2_fold"
    psql(f"DROP TABLE IF EXISTS {tbl};")
    psql(
        f"""
CREATE TABLE {tbl} ("Ref_Key" VARCHAR, name VARCHAR, n VARCHAR);
INSERT INTO {tbl} VALUES
  ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa1', 'x', '1'),
  ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa1', 'y', '2'),
  ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa2', 'z', '3'),
  ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa3', 'w', '4'),
  ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa3', 'w2', '5'),
  ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa4', 'q', '6');
"""
    )
    _setup_empty_cls()
    psql(_install_entity(tbl, ['Ref_Key'], {"Ref_Key": "ref", "name": "text", "n": "text"}))
    nrows = 6
    chunk_cells = 12  # 6*3=18 > 12; collision~4*3=12 ≤ 12 → V5
    decide = ROOT / ".test_pdoc_tail_fold_decide.sql"
    decide.write_text(
        "\\set ON_ERROR_STOP on\n" + _build_order_and_decide(tbl, chunk_cells, ['Ref_Key'])
    )
    psql_file(decide)
    in_chunks = psql(f"SELECT count(*) FROM tmp3_pdoc_chunks WHERE tbl='{tbl}'")
    if int(in_chunks) == 0:
        check("fold-кейс ушёл в mono (допустимо при oversize)", True, "mono")
        return
    for _stmt in (
        f"DELETE FROM tmp3_corpus WHERE src_table='{tbl}';",
        f"DELETE FROM tmp3_pdoc_stage WHERE src_table='{tbl}';",
        f"DELETE FROM tmp3_pdoc_progress WHERE tbl='{tbl}';",
        f"DELETE FROM tmp3_pdoc_tail_done WHERE tbl='{tbl}';",
    ):
        psql(_stmt)
    run = ROOT / ".test_pdoc_tail_fold_run.sql"
    write_run_sql(run,
        "\\set ON_ERROR_STOP on\n"
        + f"""
SELECT stmt FROM (
  SELECT c.lo, 1 AS ord, 'EXECUTE p_doc_chunk(' || quote_literal(c.tbl) || ', ' || c.lo || ', ' || c.hi || ');' AS stmt
  FROM tmp3_pdoc_chunks c WHERE c.tbl='{tbl}'
  UNION ALL
  SELECT c.lo, 2, 'INSERT INTO tmp3_pdoc_progress (tbl, rid_hi, nrows) SELECT '
    || quote_literal(c.tbl) || ', ' || c.hi || '::BIGINT, ' || c.nrows
    || '::BIGINT ON CONFLICT (tbl) DO UPDATE SET rid_hi = excluded.rid_hi, nrows = excluded.nrows;'
  FROM tmp3_pdoc_chunks c WHERE c.tbl='{tbl}'
) z ORDER BY lo, ord;
\\gexec
SELECT stmt FROM (
  SELECT 1 AS ord, 'EXECUTE p_doc_tail(' || quote_literal(t.tbl) || ');' AS stmt
  FROM (SELECT DISTINCT tbl FROM tmp3_pdoc_tail WHERE tbl = '{tbl}') t
  WHERE NOT EXISTS (SELECT 1 FROM tmp3_pdoc_tail_done d WHERE d.tbl = t.tbl)
  UNION ALL
  SELECT 2, 'INSERT INTO tmp3_pdoc_tail_done VALUES (' || quote_literal(t.tbl) || ');'
  FROM (SELECT DISTINCT tbl FROM tmp3_pdoc_tail WHERE tbl = '{tbl}') t
  WHERE NOT EXISTS (SELECT 1 FROM tmp3_pdoc_tail_done d WHERE d.tbl = t.tbl)
) z ORDER BY ord;
\\gexec
SELECT 'STAGE_FOLD|' || count(*)::VARCHAR FROM tmp3_pdoc_stage WHERE src_table='{tbl}';
EXECUTE p_doc_finalize('{tbl}');
SELECT 'FIN_N|' || count(*)::VARCHAR FROM tmp3_corpus WHERE src_table='{tbl}';
""",
    )
    out = psql_file(run)
    stage_n = int(next(l.split("|", 1)[1] for l in out.splitlines() if l.startswith("STAGE_FOLD|")))
    check("fold: stage_rows == nrows", stage_n == nrows, str(stage_n))


def test_incomplete_order_mono() -> None:
    print("\n== неполный order → mono ==")
    tbl = "_m2_incomplete"
    psql(f"DROP TABLE IF EXISTS {tbl};")
    psql(
        f"""
CREATE TABLE {tbl} (id VARCHAR, payload VARCHAR);
INSERT INTO {tbl} VALUES ('a','1'),('b','2'),('c','3'),('d','4'),('e','5'),('f','6');
"""
    )
    _setup_empty_cls()
    psql(_install_entity(tbl, ['id'], {"id": "text", "payload": "text"}))
    chunk_cells = 4  # 6*2=12 > 4
    sql = ROOT / ".test_pdoc_tail_incomplete.sql"
    sql.write_text(
        "\\set ON_ERROR_STOP on\n"
        + _build_order_and_decide(tbl, chunk_cells, ['id'])
        + f"""
-- имитация неполного order: удаляем одну строку до решения — переиграем вручную
DELETE FROM tmp3_pdoc_order;
INSERT INTO tmp3_pdoc_order SELECT '{tbl}', pos, keyvals FROM ({_keyvals_expr_sql(tbl, ['id'])});
DELETE FROM tmp3_pdoc_order WHERE pos = 1;
-- повтор гейта (в)
CREATE OR REPLACE TABLE tmp3_pdoc_mono AS
SELECT e.tbl FROM tmp3_entity_rows e
WHERE EXISTS (SELECT 1 FROM tmp3_pdoc_entity pe WHERE pe.tbl = e.tbl)
  AND (SELECT count(*) FROM tmp3_pdoc_order o WHERE o.tbl = e.tbl) <> e.nrows;
SELECT 'MONO|' || count(*)::VARCHAR FROM tmp3_pdoc_mono WHERE tbl='{tbl}';
SELECT 'V5TAIL|' || count(*)::VARCHAR FROM tmp3_pdoc_tail WHERE tbl='{tbl}';
"""
    )
    out = psql_file(sql)
    mono = int(next(l.split("|", 1)[1] for l in out.splitlines() if l.startswith("MONO|")))
    check("неполный order → mono", mono == 1, str(mono))


def test_oversize_mono() -> None:
    print("\n== oversize-хвост → mono + pdoc_tail_oversize ==")
    tbl = "_m2_oversize"
    psql(f"DROP TABLE IF EXISTS {tbl};")
    # много коллизий при tiny chunk_cells
    vals = ", ".join(f"('k', 'p{i}', '{i}')" for i in range(12))
    vals += ", ('u','alone', '100')"
    psql(
        f"""
CREATE TABLE {tbl} (id VARCHAR, payload VARCHAR, n VARCHAR);
INSERT INTO {tbl} VALUES {vals};
"""
    )
    _setup_empty_cls()
    psql(_install_entity(tbl, ['id'], {"id": "text", "payload": "text", "n": "text"}))
    # chunk_cells мал: collision_rows(12)*ncols(3)=36 > chunk_cells, но nrows*ncols > chunk_cells
    chunk_cells = 20
    sql = ROOT / ".test_pdoc_tail_oversize.sql"
    sql.write_text(
        "\\set ON_ERROR_STOP on\n"
        + _build_order_and_decide(tbl, chunk_cells, ['id'])
        + f"""
SELECT 'PATH|' || coalesce((SELECT note FROM search_quality WHERE k='pdoc_tail:{tbl}'),'none');
SELECT 'OVER|' || coalesce((SELECT v::VARCHAR FROM search_quality WHERE k='pdoc_tail_oversize'),'0');
SELECT 'CHUNKS|' || (SELECT count(*)::VARCHAR FROM tmp3_pdoc_chunks WHERE tbl='{tbl}');
"""
    )
    out = psql_file(sql)
    path = next(l.split("|", 1)[1] for l in out.splitlines() if l.startswith("PATH|"))
    over = int(next(l.split("|", 1)[1] for l in out.splitlines() if l.startswith("OVER|")))
    chunks = int(next(l.split("|", 1)[1] for l in out.splitlines() if l.startswith("CHUNKS|")))
    check("path=mono_oversize", "mono_oversize" in path, path)
    check("запись pdoc_tail_oversize ≥1", over >= 1, str(over))
    check("chunks сняты (mono)", chunks == 0, str(chunks))


def test_resume_and_fresh() -> None:
    print("\n== resume: маркер не раздувает stage; fresh сбрасывает ==")
    tbl = "_m2_resume"
    psql(f"DROP TABLE IF EXISTS {tbl};")
    psql(
        f"""
CREATE TABLE {tbl} (id VARCHAR, payload VARCHAR, n VARCHAR);
INSERT INTO {tbl} VALUES
  ('dup','a','1'),('dup','b','2'),('dup','c','3'),
  ('x','1','4'),('y','2','5'),('z','3','6'),('w','4','7'),('v','5','8');
"""
    )
    _setup_empty_cls()
    psql(_install_entity(tbl, ['id'], {"id": "text", "payload": "text", "n": "text"}))
    chunk_cells = 12  # 8*3=24 > 12; collision 3*3=9 ≤ 12 → V5
    decide = ROOT / ".test_pdoc_tail_resume_decide.sql"
    decide.write_text(
        "\\set ON_ERROR_STOP on\n" + _build_order_and_decide(tbl, chunk_cells, ['id'])
    )
    psql_file(decide)
    if int(psql(f"SELECT count(*) FROM tmp3_pdoc_chunks WHERE tbl='{tbl}'")) == 0:
        check("resume: ожидался V5, получили mono — chunk_cells", False, "skip")
        return

    run1 = ROOT / ".test_pdoc_tail_resume_run1.sql"
    write_run_sql(run1, "\\set ON_ERROR_STOP on\n" + _run_chunk_tail_finalize(tbl))
    out1 = psql_file(run1)
    stage1 = int(next(l for l in out1.splitlines() if l.startswith("STAGE_AFTER_TAIL|")).split("|")[1])

    # повтор диспетчера хвоста при наличии маркера (stage уже полный; corpus после finalize очистил progress —
    # имитируем mid-resume: восстановим stage+marker без повторного INSERT хвоста)
    # Пересоберём decide, заполним stage один раз, поставим маркер, вызовем tail-список дважды.
    psql_file(decide)
    psql(
        f"""
DELETE FROM tmp3_corpus WHERE src_table='{tbl}';
DELETE FROM tmp3_pdoc_stage WHERE src_table='{tbl}';
DELETE FROM tmp3_pdoc_progress WHERE tbl='{tbl}';
DELETE FROM tmp3_pdoc_tail_done WHERE tbl='{tbl}';
"""
    )
    mid = ROOT / ".test_pdoc_tail_resume_mid.sql"
    write_run_sql(mid,
        "\\set ON_ERROR_STOP on\n"
        + f"""
SELECT stmt FROM (
  SELECT c.lo, 1 AS ord, 'EXECUTE p_doc_chunk(' || quote_literal(c.tbl) || ', ' || c.lo || ', ' || c.hi || ');' AS stmt
  FROM tmp3_pdoc_chunks c WHERE c.tbl='{tbl}'
  UNION ALL
  SELECT c.lo, 2, 'INSERT INTO tmp3_pdoc_progress (tbl, rid_hi, nrows) SELECT '
    || quote_literal(c.tbl) || ', ' || c.hi || '::BIGINT, ' || c.nrows
    || '::BIGINT ON CONFLICT (tbl) DO UPDATE SET rid_hi = excluded.rid_hi, nrows = excluded.nrows;'
  FROM tmp3_pdoc_chunks c WHERE c.tbl='{tbl}'
) z ORDER BY lo, ord;
\\gexec
SELECT stmt FROM (
  SELECT 1 AS ord, 'EXECUTE p_doc_tail(' || quote_literal(t.tbl) || ');' AS stmt
  FROM (SELECT DISTINCT tbl FROM tmp3_pdoc_tail WHERE tbl = '{tbl}') t
  WHERE NOT EXISTS (SELECT 1 FROM tmp3_pdoc_tail_done d WHERE d.tbl = t.tbl)
  UNION ALL
  SELECT 2, 'INSERT INTO tmp3_pdoc_tail_done VALUES (' || quote_literal(t.tbl) || ');'
  FROM (SELECT DISTINCT tbl FROM tmp3_pdoc_tail WHERE tbl = '{tbl}') t
  WHERE NOT EXISTS (SELECT 1 FROM tmp3_pdoc_tail_done d WHERE d.tbl = t.tbl)
) z ORDER BY ord;
\\gexec
SELECT 'S1|' || count(*)::VARCHAR FROM tmp3_pdoc_stage WHERE src_table='{tbl}';
-- повтор (маркер есть → 0 строк \\gexec)
SELECT stmt FROM (
  SELECT 1 AS ord, 'EXECUTE p_doc_tail(' || quote_literal(t.tbl) || ');' AS stmt
  FROM (SELECT DISTINCT tbl FROM tmp3_pdoc_tail WHERE tbl = '{tbl}') t
  WHERE NOT EXISTS (SELECT 1 FROM tmp3_pdoc_tail_done d WHERE d.tbl = t.tbl)
  UNION ALL
  SELECT 2, 'INSERT INTO tmp3_pdoc_tail_done VALUES (' || quote_literal(t.tbl) || ');'
  FROM (SELECT DISTINCT tbl FROM tmp3_pdoc_tail WHERE tbl = '{tbl}') t
  WHERE NOT EXISTS (SELECT 1 FROM tmp3_pdoc_tail_done d WHERE d.tbl = t.tbl)
) z ORDER BY ord;
\\gexec
SELECT 'S2|' || count(*)::VARCHAR FROM tmp3_pdoc_stage WHERE src_table='{tbl}';
SELECT 'DONE|' || count(*)::VARCHAR FROM tmp3_pdoc_tail_done WHERE tbl='{tbl}';
"""
    )
    out = psql_file(mid)
    s1 = int(next(l.split("|", 1)[1] for l in out.splitlines() if l.startswith("S1|")))
    s2 = int(next(l.split("|", 1)[1] for l in out.splitlines() if l.startswith("S2|")))
    done = int(next(l.split("|", 1)[1] for l in out.splitlines() if l.startswith("DONE|")))
    check("resume: stage не раздулся", s1 == s2 and s1 > 0, f"s1={s1} s2={s2}")
    check("маркер стоит", done == 1, str(done))

    # сброс на fresh (NOT on_) — только _done (+ stage/progress в бою); план хвоста не стираем
    psql("CREATE OR REPLACE TABLE tmp3_resume_pdoc AS SELECT false AS on_;")
    psql(
        f"""
DELETE FROM tmp3_pdoc_tail_done d
WHERE EXISTS (SELECT 1 FROM tmp3_pdoc_chunks c WHERE c.tbl = d.tbl)
  AND NOT (SELECT on_ FROM tmp3_resume_pdoc);
"""
    )
    aft_done = int(psql(f"SELECT count(*) FROM tmp3_pdoc_tail_done WHERE tbl='{tbl}'"))
    aft_tail = int(psql(f"SELECT count(*) FROM tmp3_pdoc_tail WHERE tbl='{tbl}'"))
    check(
        "fresh сбросил маркеры _done, tail-план жив",
        aft_done == 0 and aft_tail > 0,
        f"done={aft_done} tail={aft_tail}",
    )

    # сброс на смене formula
    psql_file(decide)  # восстановить tail
    psql(f"INSERT INTO tmp3_pdoc_tail_done VALUES ('{tbl}');")
    psql(f"CREATE OR REPLACE TABLE search_pdoc_formula AS SELECT '{tbl}'::VARCHAR AS tbl, 'old'::VARCHAR AS formula;")
    psql(
        f"""
DELETE FROM tmp3_pdoc_tail t
WHERE EXISTS (SELECT 1 FROM tmp3_pdoc_formula f WHERE f.tbl = t.tbl)
  AND coalesce((SELECT f0.formula FROM search_pdoc_formula f0 WHERE f0.tbl = t.tbl), '')
      IS DISTINCT FROM (SELECT f2.formula FROM tmp3_pdoc_formula f2 WHERE f2.tbl = t.tbl);
DELETE FROM tmp3_pdoc_tail_done d
WHERE EXISTS (SELECT 1 FROM tmp3_pdoc_formula f WHERE f.tbl = d.tbl)
  AND coalesce((SELECT f0.formula FROM search_pdoc_formula f0 WHERE f0.tbl = d.tbl), '')
      IS DISTINCT FROM (SELECT f2.formula FROM tmp3_pdoc_formula f2 WHERE f2.tbl = d.tbl);
"""
    )
    check(
        "formula-смена сбросила маркеры",
        int(psql(f"SELECT count(*) FROM tmp3_pdoc_tail_done WHERE tbl='{tbl}'")) == 0,
    )


def test_no_collision_byte_identity() -> None:
    print("\n== без коллизий: байт-в-байт как mono (чанковый путь) ==")
    tbl = "_m2_unique"
    psql(f"DROP TABLE IF EXISTS {tbl};")
    psql(
        f"""
CREATE TABLE {tbl} (id VARCHAR, payload VARCHAR, n VARCHAR);
INSERT INTO {tbl} VALUES
  ('a','1','1'),('b','2','2'),('c','3','3'),('d','4','4'),('e','5','5'),('f','6','6');
"""
    )
    _setup_empty_cls()
    psql(_install_entity(tbl, ['id'], {"id": "text", "payload": "text", "n": "text"}))
    chunk_cells = 12  # 6*3=18 > 12; collision~4*3=12 ≤ 12 → V5
    decide = ROOT / ".test_pdoc_tail_unique_decide.sql"
    decide.write_text(
        "\\set ON_ERROR_STOP on\n"
        + _build_order_and_decide(tbl, chunk_cells, ['id'])
        + f"""
SELECT 'TAIL|' || (SELECT count(*)::VARCHAR FROM tmp3_pdoc_tail WHERE tbl='{tbl}');
SELECT 'CHUNKS|' || (SELECT count(*)::VARCHAR FROM tmp3_pdoc_chunks WHERE tbl='{tbl}');
"""
    )
    out = psql_file(decide)
    tail_n = int(next(l.split("|", 1)[1] for l in out.splitlines() if l.startswith("TAIL|")))
    chunks = int(next(l.split("|", 1)[1] for l in out.splitlines() if l.startswith("CHUNKS|")))
    check("без коллизий: tail пуст", tail_n == 0, str(tail_n))
    check("без коллизий: чанкуется", chunks >= 1, str(chunks))

    mono_sql = ROOT / ".test_pdoc_tail_unique_mono.sql"
    write_run_sql(mono_sql, "\\set ON_ERROR_STOP on\n" + _run_mono(tbl))
    mh, mn = _parse_multi(psql_file(mono_sql))

    psql_file(decide)
    # chunk+finalize без хвоста
    run = ROOT / ".test_pdoc_tail_unique_run.sql"
    write_run_sql(run,
        "\\set ON_ERROR_STOP on\n"
        + f"""
DELETE FROM tmp3_corpus WHERE src_table='{tbl}';
DELETE FROM tmp3_pdoc_stage WHERE src_table='{tbl}';
DELETE FROM tmp3_pdoc_progress WHERE tbl='{tbl}';
SELECT stmt FROM (
  SELECT c.lo, 1 AS ord, 'EXECUTE p_doc_chunk(' || quote_literal(c.tbl) || ', ' || c.lo || ', ' || c.hi || ');' AS stmt
  FROM tmp3_pdoc_chunks c WHERE c.tbl='{tbl}'
  UNION ALL
  SELECT c.lo, 2, 'INSERT INTO tmp3_pdoc_progress (tbl, rid_hi, nrows) SELECT '
    || quote_literal(c.tbl) || ', ' || c.hi || '::BIGINT, ' || c.nrows
    || '::BIGINT ON CONFLICT (tbl) DO UPDATE SET rid_hi = excluded.rid_hi, nrows = excluded.nrows;'
  FROM tmp3_pdoc_chunks c WHERE c.tbl='{tbl}'
) z ORDER BY lo, ord;
\\gexec
SELECT 'STAGE|' || count(*)::VARCHAR FROM tmp3_pdoc_stage WHERE src_table='{tbl}';
EXECUTE p_doc_finalize('{tbl}');
SELECT 'MULTI|' || md5(string_agg(content_hash || chr(1) || row_key, chr(2) ORDER BY content_hash, row_key))
     || '|N|' || count(*)::VARCHAR
FROM tmp3_corpus WHERE src_table='{tbl}';
"""
    )
    out = psql_file(run)
    stage = int(next(l.split("|", 1)[1] for l in out.splitlines() if l.startswith("STAGE|")))
    ch, cn = _parse_multi(out)
    check("без коллизий: stage_rows == nrows", stage == 6, str(stage))
    check("без коллизий: multiset == mono", ch == mh and cn == mn, f"{cn} vs {mn}")


def _battle_tail_dispatch_stmt(tbl: str) -> str:
    """Проверка формы: боевая строка ≡ вырезанному SELECT (без BEGIN/COMMIT)."""
    block = _extract_battle_tail_dispatch_from_file()
    needle = "'EXECUTE p_doc_tail(' || quote_literal(t.tbl)"
    if needle not in block:
        raise RuntimeError("боевая строка диспетчера хвоста не найдена в вырезанном блоке")
    return (
        f"EXECUTE p_doc_tail({repr(tbl)}); "
        f"INSERT INTO tmp3_pdoc_tail_done VALUES ({repr(tbl)});"
    )


def _run_file_wipe_on_false() -> None:
    """Выполнить fresh-wipe, вырезанный из corpus_build.sql, при on_=false."""
    wipe = _extract_fresh_wipe_from_file()
    path = ROOT / ".test_pdoc_tail_file_wipe.sql"
    path.write_text(
        "\\set ON_ERROR_STOP on\n"
        "CREATE OR REPLACE TABLE tmp3_resume_pdoc AS SELECT false AS on_;\n"
        + wipe
        + "\n",
        encoding="utf-8",
    )
    psql_file(path)


def _run_chunks_then_file_tail_finalize(tbl: str) -> str:
    """Порции (зеркало) + хвост SELECT\\gexec из файла + finalize; вернуть stdout."""
    tail_disp = _extract_battle_tail_dispatch_from_file()
    run = ROOT / f".test_pdoc_tail_file_tail_{tbl}.sql"
    write_run_sql(
        run,
        "\\set ON_ERROR_STOP on\n"
        + f"""
DELETE FROM tmp3_corpus WHERE src_table = '{tbl}';
DELETE FROM tmp3_pdoc_stage WHERE src_table = '{tbl}';
DELETE FROM tmp3_pdoc_progress WHERE tbl = '{tbl}';
SELECT stmt FROM (
  SELECT c.lo, 1 AS ord,
         'EXECUTE p_doc_chunk(' || quote_literal(c.tbl) || ', ' || c.lo || ', ' || c.hi || ');' AS stmt
  FROM tmp3_pdoc_chunks c WHERE c.tbl = '{tbl}'
  UNION ALL
  SELECT c.lo, 2,
         'INSERT INTO tmp3_pdoc_progress (tbl, rid_hi, nrows) SELECT '
           || quote_literal(c.tbl) || ', ' || c.hi || '::BIGINT, ' || c.nrows
           || '::BIGINT ON CONFLICT (tbl) DO UPDATE SET rid_hi = excluded.rid_hi, nrows = excluded.nrows;'
  FROM tmp3_pdoc_chunks c WHERE c.tbl = '{tbl}'
) z ORDER BY lo, ord;
\\gexec

SELECT 'STAGE_BEFORE_TAIL|' || count(*)::VARCHAR FROM tmp3_pdoc_stage WHERE src_table = '{tbl}';

{tail_disp}

SELECT 'STAGE_AFTER_TAIL|' || count(*)::VARCHAR
     || '|NROWS|' || (SELECT nrows::VARCHAR FROM tmp3_entity_rows WHERE tbl='{tbl}')
FROM tmp3_pdoc_stage WHERE src_table = '{tbl}';

EXECUTE p_doc_finalize('{tbl}');

SELECT 'MULTI|' || md5(string_agg(content_hash || chr(1) || row_key, chr(2) ORDER BY content_hash, row_key))
     || '|N|' || count(*)::VARCHAR
FROM tmp3_corpus WHERE src_table = '{tbl}';
""",
    )
    return psql_file(run)


def test_fresh_battle_order_bug1() -> None:
    print("\n== боевой порядок на fresh (регрессия BUG-1, wipe+хвост из файла) ==")
    try:
        wipe_block = _extract_fresh_wipe_from_file()
        tail_block = _extract_battle_tail_dispatch_from_file()
        anchors_ok = True
        anchors_detail = f"wipe={len(wipe_block)}B tail={len(tail_block)}B"
    except RuntimeError as e:
        anchors_ok = False
        anchors_detail = str(e)
    check("якоря fresh-wipe и диспетчера хвоста в файле", anchors_ok, anchors_detail)
    if not anchors_ok:
        return

    tbl = "_m2_fresh_battle"
    psql(f"DROP TABLE IF EXISTS {tbl};")
    psql(
        f"""
CREATE TABLE {tbl} (id VARCHAR, payload VARCHAR, n VARCHAR);
INSERT INTO {tbl} VALUES
  ('dup','a','1'),('dup','b','2'),('dup','c','3'),
  (NULL,'n1','10'),(NULL,'n2','20'),
  ('uniq','u','99'),('x','1','4'),('y','2','5');
"""
    )
    _setup_empty_cls()
    psql(_install_entity(tbl, ['id'], {"id": "text", "payload": "text", "n": "text"}))
    nrows = int(psql(f"SELECT count(*) FROM {tbl}"))
    chunk_cells = 15  # 8*3=24 > 15; collision 5*3=15 ≤ 15 → V5
    decide = ROOT / ".test_pdoc_tail_fresh_battle_decide.sql"
    decide.write_text(
        "\\set ON_ERROR_STOP on\n" + _build_order_and_decide(tbl, chunk_cells, ['id'])
    )
    psql_file(decide)
    if int(psql(f"SELECT count(*) FROM tmp3_pdoc_chunks WHERE tbl='{tbl}'")) == 0:
        check("fresh-battle: ожидался V5", False, "mono")
        return
    tail_before = int(psql(f"SELECT count(*) FROM tmp3_pdoc_tail WHERE tbl='{tbl}'"))
    check("fresh-battle: хвост после decide >0", tail_before > 0, str(tail_before))

    # эталон mono
    mono_sql = ROOT / ".test_pdoc_tail_fresh_battle_mono.sql"
    write_run_sql(mono_sql, "\\set ON_ERROR_STOP on\n" + _run_mono(tbl))
    mh, mn = _parse_multi(psql_file(mono_sql))

    # снова decide, wipe ИЗ ФАЙЛА (on_=false), затем порции + хвост ИЗ ФАЙЛА
    psql_file(decide)
    _run_file_wipe_on_false()
    tail_after_wipe = int(psql(f"SELECT count(*) FROM tmp3_pdoc_tail WHERE tbl='{tbl}'"))
    check("fresh-wipe (из файла) не снёс план хвоста", tail_after_wipe == tail_before, f"{tail_after_wipe} vs {tail_before}")

    out = _run_chunks_then_file_tail_finalize(tbl)
    stage_line = next(l for l in out.splitlines() if l.startswith("STAGE_AFTER_TAIL|"))
    parts = stage_line.split("|")
    stage_n = int(parts[1])
    before_tail = int(next(l.split("|", 1)[1] for l in out.splitlines() if l.startswith("STAGE_BEFORE_TAIL|")))
    check("stage содержит порции и хвост", stage_n == nrows and before_tail < stage_n, stage_line)
    vh, vn = _parse_multi(out)
    check("fresh-battle multiset == mono", vh == mh and vn == mn, f"{vn} vs {mn}")


def test_combined_file_pipeline() -> None:
    print("\n== combined: decide→wipe(file)→chunks→хвост(file)→finalize ==")
    try:
        _extract_fresh_wipe_from_file()
        _extract_battle_tail_dispatch_from_file()
        ok = True
        detail = ""
    except RuntimeError as e:
        ok = False
        detail = str(e)
    check("combined: якоря wipe/хвоста", ok, detail)
    if not ok:
        return

    tbl = "_m2_combined"
    psql(f"DROP TABLE IF EXISTS {tbl};")
    psql(
        f"""
CREATE TABLE {tbl} (id VARCHAR, payload VARCHAR, n VARCHAR);
INSERT INTO {tbl} VALUES
  ('dup','a','1'),('dup','b','2'),('dup','c','3'),
  (NULL,'n1','10'),(NULL,'n2','20'),
  ('uniq','u','99'),('x','1','4'),('y','2','5');
"""
    )
    _setup_empty_cls()
    psql(_install_entity(tbl, ['id'], {"id": "text", "payload": "text", "n": "text"}))
    nrows = int(psql(f"SELECT count(*) FROM {tbl}"))
    chunk_cells = 15
    decide = ROOT / ".test_pdoc_tail_combined_decide.sql"
    decide.write_text(
        "\\set ON_ERROR_STOP on\n" + _build_order_and_decide(tbl, chunk_cells, ['id']),
        encoding="utf-8",
    )
    psql_file(decide)
    if int(psql(f"SELECT count(*) FROM tmp3_pdoc_chunks WHERE tbl='{tbl}'")) == 0:
        check("combined: ожидался V5", False, "mono")
        return

    mono_sql = ROOT / ".test_pdoc_tail_combined_mono.sql"
    write_run_sql(mono_sql, "\\set ON_ERROR_STOP on\n" + _run_mono(tbl))
    mh, mn = _parse_multi(psql_file(mono_sql))

    # один прогон: decide → wipe(file) → chunks → tail(file) → finalize
    psql_file(decide)
    _run_file_wipe_on_false()
    out = _run_chunks_then_file_tail_finalize(tbl)
    stage_line = next(l for l in out.splitlines() if l.startswith("STAGE_AFTER_TAIL|"))
    stage_n = int(stage_line.split("|")[1])
    check("combined: stage == nrows", stage_n == nrows, stage_line)
    vh, vn = _parse_multi(out)
    check("combined: multiset == mono", vh == mh and vn == mn, f"{vn} vs {mn}")


def test_battle_tail_multistmt() -> None:
    print("\n== боевая multi-statement строка диспетчера хвоста ==")
    tbl = "_m2_battle_stmt"
    psql(f"DROP TABLE IF EXISTS {tbl};")
    psql(
        f"""
CREATE TABLE {tbl} (id VARCHAR, payload VARCHAR, n VARCHAR);
INSERT INTO {tbl} VALUES
  ('dup','a','1'),('dup','b','2'),('dup','c','3'),
  ('x','1','4'),('y','2','5'),('z','3','6'),('w','4','7'),('v','5','8');
"""
    )
    _setup_empty_cls()
    psql(_install_entity(tbl, ['id'], {"id": "text", "payload": "text", "n": "text"}))
    chunk_cells = 12
    decide = ROOT / ".test_pdoc_tail_battle_stmt_decide.sql"
    decide.write_text(
        "\\set ON_ERROR_STOP on\n" + _build_order_and_decide(tbl, chunk_cells, ['id'])
    )
    psql_file(decide)
    if int(psql(f"SELECT count(*) FROM tmp3_pdoc_chunks WHERE tbl='{tbl}'")) == 0:
        check("battle-stmt: ожидался V5", False, "mono")
        return

    # порции без хвоста
    chunks_only = ROOT / ".test_pdoc_tail_battle_stmt_chunks.sql"
    write_run_sql(
        chunks_only,
        "\\set ON_ERROR_STOP on\n"
        + f"""
DELETE FROM tmp3_corpus WHERE src_table='{tbl}';
DELETE FROM tmp3_pdoc_stage WHERE src_table='{tbl}';
DELETE FROM tmp3_pdoc_progress WHERE tbl='{tbl}';
DELETE FROM tmp3_pdoc_tail_done WHERE tbl='{tbl}';
SELECT stmt FROM (
  SELECT c.lo, 1 AS ord, 'EXECUTE p_doc_chunk(' || quote_literal(c.tbl) || ', ' || c.lo || ', ' || c.hi || ');' AS stmt
  FROM tmp3_pdoc_chunks c WHERE c.tbl='{tbl}'
  UNION ALL
  SELECT c.lo, 2, 'INSERT INTO tmp3_pdoc_progress (tbl, rid_hi, nrows) SELECT '
    || quote_literal(c.tbl) || ', ' || c.hi || '::BIGINT, ' || c.nrows
    || '::BIGINT ON CONFLICT (tbl) DO UPDATE SET rid_hi = excluded.rid_hi, nrows = excluded.nrows;'
  FROM tmp3_pdoc_chunks c WHERE c.tbl='{tbl}'
) z ORDER BY lo, ord;
\\gexec
SELECT 'BEFORE|' || count(*)::VARCHAR FROM tmp3_pdoc_stage WHERE src_table='{tbl}';
""",
    )
    before = int(next(l.split("|", 1)[1] for l in psql_file(chunks_only).splitlines() if l.startswith("BEFORE|")))

    # боевая строка: SELECT\\gexec ВЫРЕЗАН из corpus_build.sql
    try:
        file_disp = _extract_battle_tail_dispatch_from_file()
        sample = _battle_tail_dispatch_stmt(tbl)
        form_ok = True
        form_detail = sample
    except RuntimeError as e:
        file_disp = ""
        sample = ""
        form_ok = False
        form_detail = str(e)
    check(
        "форма боевой строки ≡ файлу (вырезание)",
        form_ok
        and sample.startswith("EXECUTE p_doc_tail(")
        and "; INSERT INTO tmp3_pdoc_tail_done VALUES (" in sample
        and "BEGIN" not in sample
        and "COMMIT" not in sample
        and "\\gexec" in file_disp
        and "SELECT 'EXECUTE p_doc_tail(" in file_disp,
        form_detail,
    )
    if not form_ok:
        return
    battle_sql = ROOT / ".test_pdoc_tail_battle_stmt_exec.sql"
    write_run_sql(
        battle_sql,
        "\\set ON_ERROR_STOP on\n"
        + f"""
{file_disp}
SELECT 'AFTER|' || count(*)::VARCHAR FROM tmp3_pdoc_stage WHERE src_table='{tbl}';
SELECT 'DONE|' || count(*)::VARCHAR FROM tmp3_pdoc_tail_done WHERE tbl='{tbl}';
""",
    )
    bout = psql_file(battle_sql)
    after = int(next(l.split("|", 1)[1] for l in bout.splitlines() if l.startswith("AFTER|")))
    done = int(next(l.split("|", 1)[1] for l in bout.splitlines() if l.startswith("DONE|")))
    check("после боевой строки: stage вырос (хвост)", after > before, f"before={before} after={after}")
    check("после боевой строки: маркер стоит", done == 1, str(done))

    # повтор той же строки из файла: guard маркера
    again = ROOT / ".test_pdoc_tail_battle_stmt_again.sql"
    again.write_text(
        "\\set ON_ERROR_STOP on\n"
        + f"""
{file_disp}
SELECT 'AFTER2|' || count(*)::VARCHAR FROM tmp3_pdoc_stage WHERE src_table='{tbl}';
SELECT 'GEXEC|' || count(*)::VARCHAR FROM (
  SELECT 1
  FROM (SELECT DISTINCT tbl FROM tmp3_pdoc_tail) t
  WHERE NOT EXISTS (SELECT 1 FROM tmp3_pdoc_tail_done d WHERE d.tbl = t.tbl)
    AND NOT EXISTS (SELECT 1 FROM tmp3_corpus c WHERE c.src_table = t.tbl)
    AND EXISTS (SELECT 1 FROM tmp3_pdoc_chunks c WHERE c.tbl = t.tbl)
    AND t.tbl = '{tbl}'
) g;
""",
        encoding="utf-8",
    )
    out2 = psql_file(again)
    after2 = int(next(l.split("|", 1)[1] for l in out2.splitlines() if l.startswith("AFTER2|")))
    gexec_n = int(next(l.split("|", 1)[1] for l in out2.splitlines() if l.startswith("GEXEC|")))
    check("повтор по guard маркера не выполняется", gexec_n == 0 and after2 == after, f"g={gexec_n} s={after2}")


def test_pipe_keyvals_empty_strings() -> None:
    print("\n== keyvals класса «|»: пустые строки в ключах ==")
    tbl = "_m2_pipe_empty"
    psql(f"DROP TABLE IF EXISTS {tbl};")
    # два ключевых столбца с '' → keyvals='|' (не NULL)
    psql(
        f"""
CREATE TABLE {tbl} (a VARCHAR, b VARCHAR, payload VARCHAR);
INSERT INTO {tbl} VALUES
  ('','','p1'),('','','p2'),('','','p3'),
  ('x','y','u1'),('x','z','u2'),('p','q','u3'),('r','s','u4');
"""
    )
    _setup_empty_cls()
    psql(_install_entity(tbl, ['a', 'b'], {"a": "text", "b": "text", "payload": "text"}))
    nrows = 7
    chunk_cells = 12  # 7*3=21 > 12; collision 3*3=9 ≤ 12 → V5
    decide = ROOT / ".test_pdoc_tail_pipe_decide.sql"
    decide.write_text(
        "\\set ON_ERROR_STOP on\n"
        + _build_order_and_decide(tbl, chunk_cells, ['a', 'b'])
        + f"""
SELECT 'TAIL_KV|' || coalesce((SELECT keyvals FROM tmp3_pdoc_tail WHERE tbl='{tbl}' LIMIT 1), 'none');
SELECT 'TAIL_N|' || (SELECT count(*)::VARCHAR FROM tmp3_pdoc_tail WHERE tbl='{tbl}');
SELECT 'PATH|' || coalesce((SELECT note FROM search_quality WHERE k='pdoc_tail:{tbl}'),'none');
SELECT 'COLL|' || coalesce((SELECT collision_rows::VARCHAR FROM tmp3_pdoc_collision_saved WHERE tbl='{tbl}'),'0');
"""
    )
    out = psql_file(decide)
    tail_kv = next(l.split("|", 1)[1] for l in out.splitlines() if l.startswith("TAIL_KV|"))
    coll = int(next(l.split("|", 1)[1] for l in out.splitlines() if l.startswith("COLL|")))
    path = next(l.split("|", 1)[1] for l in out.splitlines() if l.startswith("PATH|"))
    check("хвост содержит keyvals «|»", tail_kv == "|", repr(tail_kv))
    check("collision_rows = 3 (пустые ключи)", coll == 3, str(coll))
    check("путь v5 для «|»", "path=v5" in path, path)

    mono_sql = ROOT / ".test_pdoc_tail_pipe_mono.sql"
    write_run_sql(mono_sql, "\\set ON_ERROR_STOP on\n" + _run_mono(tbl))
    mh, mn = _parse_multi(psql_file(mono_sql))
    psql_file(decide)
    run = ROOT / ".test_pdoc_tail_pipe_run.sql"
    write_run_sql(run, "\\set ON_ERROR_STOP on\n" + _run_chunk_tail_finalize(tbl))
    vh, vn = _parse_multi(psql_file(run))
    check("«|»-хвост: stage/multiset == mono", vh == mh and vn == mn == nrows, f"{vn} vs {mn}")


def test_identical_tail_duplicates() -> None:
    """Идентичные по контенту дубли через хвост: finalize не схлопывает (≡ монолит)."""
    print("\n== идентичные дубли через хвост: multiset == mono, nrows без схлопа ==")
    tbl = "_m2_ident_dup"
    psql(f"DROP TABLE IF EXISTS {tbl};")
    # ≥2 строки с одинаковым keyvals И полностью одинаковым контентом — обе уходят в хвост
    psql(
        f"""
CREATE TABLE {tbl} (id VARCHAR, payload VARCHAR, n VARCHAR);
INSERT INTO {tbl} VALUES
  ('same', 'x', '1'), ('same', 'x', '1'),
  ('a', 'p', '2'), ('b', 'q', '3'), ('c', 'r', '4'), ('d', 's', '5');
"""
    )
    _setup_empty_cls()
    psql(_install_entity(tbl, ['id'], {"id": "text", "payload": "text", "n": "text"}))
    nrows = 6
    chunk_cells = 12  # 6*3=18 > 12; collision 2*3=6 ≤ 12 → V5
    decide = ROOT / ".test_pdoc_tail_ident_decide.sql"
    decide.write_text(
        "\\set ON_ERROR_STOP on\n"
        + _build_order_and_decide(tbl, chunk_cells, ['id'])
        + f"""
SELECT 'PATH|' || coalesce((SELECT note FROM search_quality WHERE k='pdoc_tail:{tbl}'), 'none');
SELECT 'COLL|' || coalesce((SELECT collision_rows::VARCHAR FROM tmp3_pdoc_collision_saved WHERE tbl='{tbl}'),'0');
SELECT 'TAIL_N|' || (SELECT count(*)::VARCHAR FROM tmp3_pdoc_tail WHERE tbl='{tbl}');
SELECT 'IN_CHUNKS|' || CASE WHEN EXISTS (SELECT 1 FROM tmp3_pdoc_chunks WHERE tbl='{tbl}') THEN '1' ELSE '0' END;
"""
    )
    out = psql_file(decide)
    path = next(l.split("|", 1)[1] for l in out.splitlines() if l.startswith("PATH|"))
    coll = int(next(l.split("|", 1)[1] for l in out.splitlines() if l.startswith("COLL|")))
    tail_n = int(next(l.split("|", 1)[1] for l in out.splitlines() if l.startswith("TAIL_N|")))
    in_chunks = next(l.split("|", 1)[1] for l in out.splitlines() if l.startswith("IN_CHUNKS|"))
    check("идент-дубли: путь v5", "path=v5" in path, path)
    check("идент-дубли: collision_rows = 2", coll == 2, str(coll))
    check("идент-дубли: хвост непуст (обе через хвост)", tail_n >= 1, str(tail_n))
    check("идент-дубли: сущность в chunks", in_chunks == "1")

    mono_sql = ROOT / ".test_pdoc_tail_ident_mono.sql"
    write_run_sql(mono_sql, "\\set ON_ERROR_STOP on\n" + _run_mono(tbl))
    mono_out = psql_file(mono_sql)
    mono_h, mono_n = _parse_multi(mono_out)

    psql_file(decide)
    v5_sql = ROOT / ".test_pdoc_tail_ident_run.sql"
    write_run_sql(v5_sql, "\\set ON_ERROR_STOP on\n" + _run_chunk_tail_finalize(tbl))
    v5_out = psql_file(v5_sql)
    stage_line = next(l for l in v5_out.splitlines() if l.startswith("STAGE_AFTER_TAIL|"))
    parts = stage_line.split("|")
    stage_n, nrows_s = int(parts[1]), int(parts[3])
    v5_h, v5_n = _parse_multi(v5_out)

    check("идент-дубли: stage_rows == nrows", stage_n == nrows_s == nrows, stage_line)
    check(
        "идент-дубли: multiset content_hash,row_key == mono",
        v5_h == mono_h and v5_n == mono_n,
        f"{v5_n} vs {mono_n}",
    )
    check(
        "идент-дубли: corpus N == mono N == nrows (никто не схлопнут)",
        v5_n == mono_n == nrows,
        f"v5={v5_n} mono={mono_n} nrows={nrows}",
    )
    # fin-суффикс #N разводит одинаковый mid-ключ; одинаково у обоих путей
    hash_cnt = int(
        psql(
            f"""
SELECT count(*) FROM tmp3_corpus
WHERE src_table = '{tbl}' AND position('#' IN row_key) > 0
"""
        )
    )
    check(
        "идент-дубли: есть row_key с '#'-суффиксом fin",
        hash_cnt >= 2,
        str(hash_cnt),
    )


def test_coverage_gate_negative() -> None:
    print("\n== негатив coverage-гейта: испорченный DELETE order ==")
    tbl = "_m2_cover_neg"
    psql(f"DROP TABLE IF EXISTS {tbl};")
    psql(
        f"""
CREATE TABLE {tbl} (id VARCHAR, payload VARCHAR, n VARCHAR);
INSERT INTO {tbl} VALUES
  ('dup','a','1'),('dup','b','2'),('dup','c','3'),
  ('x','1','4'),('y','2','5'),('z','3','6');
"""
    )
    _setup_empty_cls()
    psql(_install_entity(tbl, ['id'], {"id": "text", "payload": "text", "n": "text"}))
    chunk_cells = 12  # 6*3=18 > 12; collision 3*3=9 ≤ 12
    # decide без DELETE order (испорченный): хвост заполнен, order цел → cover ломается
    broken = ROOT / ".test_pdoc_tail_cover_neg.sql"
    body = _build_order_and_decide(tbl, chunk_cells, ['id'])
    # вырезаем DELETE order по tail — имитация сломанного DELETE
    bad = body.replace(
        """DELETE FROM tmp3_pdoc_order o
WHERE EXISTS (
  SELECT 1 FROM tmp3_pdoc_tail t
  WHERE t.tbl = o.tbl AND t.keyvals IS NOT DISTINCT FROM o.keyvals
);""",
        "-- ИСПОРЧЕНО: DELETE order по tail пропущен (негатив coverage-гейта)\n",
    )
    if bad == body:
        check("негатив: шаблон DELETE найден", False, "replace miss")
        return
    # гейт в _build_order_and_decide уже есть; при сломанном DELETE он падает с error
    broken.write_text("\\set ON_ERROR_STOP on\n" + bad, encoding="utf-8")
    raised = False
    err = ""
    try:
        psql_file(broken)
    except RuntimeError as e:
        raised = True
        err = str(e)
    check(
        "coverage-гейт даёт error при count≠nrows",
        raised and "count(order)+collision_rows" in err,
        err[:200],
    )


def main() -> int:
    global DSN
    _offline_structure()
    try:
        DSN = resolve_dsn()
    except Exception as e:
        print(f"\nЖивой движок недоступен: {e}")
        print(f"\nИТОГ (только оффлайн): {_checks - _fail}/{_checks} PASS"
              + (" ✅" if _fail == 0 else f", {_fail} FAIL ✗"))
        return 1 if _fail else 2

    boot = ROOT / ".test_pdoc_tail_boot.sql"
    boot.write_text(_bootstrap_sql(), encoding="utf-8")
    print("\n== bootstrap PREPARE ==")
    try:
        psql_file(boot)
        check("bootstrap PREPARE", True)
    except Exception as e:
        check("bootstrap PREPARE", False, str(e)[:300])
        print(f"\nИТОГ: {_checks - _fail}/{_checks} PASS, {_fail} FAIL ✗")
        return 1

    for fn in (
        test_fold_stage_rows,
        test_fold_finalize_plan_and_semantics,
        test_v5_equivalence_and_coverage,
        test_incomplete_order_mono,
        test_oversize_mono,
        test_resume_and_fresh,
        test_no_collision_byte_identity,
        test_fresh_battle_order_bug1,
        test_combined_file_pipeline,
        test_battle_tail_multistmt,
        test_pipe_keyvals_empty_strings,
        test_identical_tail_duplicates,
        test_coverage_gate_negative,
    ):
        try:
            time.sleep(0.2)
            fn()
        except Exception as e:
            check(fn.__name__ + " exception", False, str(e)[:400])

    print(
        f"\nИТОГ: {_checks - _fail}/{_checks} PASS"
        + (" ✅" if _fail == 0 else f", {_fail} FAIL ✗")
    )
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(main())
