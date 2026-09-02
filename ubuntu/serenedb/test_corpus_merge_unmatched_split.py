#!/usr/bin/env python3
"""Замок M1: резка unmatched по сущностям + порядок edited_delta (план v4 §3).

Фикстура и сверки — внутри движка (serened shell / ATTACH :memory:).
Python только поднимает SQL и читает маркеры PASS/FAIL из stdout.
Строки корпуса наружу не выгружаются.

Запуск: python3 test_corpus_merge_unmatched_split.py
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MERGE = ROOT / "corpus_merge.sql"
PASS, FAIL = 0, []


def t(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + str(detail))[:240] if detail else "")


def extract_prepare_body() -> str:
    text = MERGE.read_text(encoding="utf-8")
    start = text.index("PREPARE p_merge_unmatched AS")
    end = text.index("\\gexec", start)
    # тело PREPARE до диспетчера (строка SELECT DISTINCT 'EXECUTE…)
    block = text[start:end]
    # отрезать диспетчер SELECT
    cut = block.rfind("SELECT DISTINCT 'EXECUTE p_merge_unmatched(")
    if cut < 0:
        raise RuntimeError("dispatcher SELECT not found after PREPARE")
    return block[:cut].rstrip() + "\n"


def extract_ref_select() -> str:
    """Эталонная формула монолитного unmatched (старый SELECT :162-199)."""
    return """
CREATE OR REPLACE TABLE tmp3_merge_unmatched_ref AS
SELECT c.src_table, c.row_key
FROM search_corpus c
WHERE c.src_table IN (SELECT DISTINCT src_table FROM tmp3_corpus)
  AND c.src_table NOT IN (SELECT src_table FROM tmp3_merge_rewrite_wave)
  AND NOT EXISTS (SELECT 1 FROM tmp3_corpus t
                  WHERE t.src_table = c.src_table AND t.row_key = c.row_key)
  AND NOT EXISTS (SELECT 1 FROM tmp3_corpus t
                  WHERE t.src_table = c.src_table
                    AND t.row_key = regexp_replace(c.row_key, '#[0-9a-f]{40}$', ''))
  AND NOT EXISTS (SELECT 1 FROM tmp3_corpus t
                  WHERE t.src_table = c.src_table
                    AND t.row_key = split_part(c.row_key, '#', 1)
                    AND position('#' in c.row_key) > 0)
  AND NOT EXISTS (SELECT 1 FROM tmp3_corpus t
                  WHERE t.src_table = c.src_table
                    AND split_part(t.row_key, '|', 1) = split_part(c.row_key, '|', 1)
                    AND split_part(c.row_key, '|', 1) <> '')
  AND NOT EXISTS (SELECT 1 FROM tmp3_corpus t
                  WHERE t.src_table = c.src_table
                    AND split_part(t.row_key, '|', 1) = split_part(c.row_key, '#', 1)
                    AND position('#' in c.row_key) > 0
                    AND split_part(c.row_key, '#', 1) <> '')
  AND NOT EXISTS (SELECT 1 FROM tmp3_corpus t
                  WHERE t.src_table = c.src_table
                    AND substr(t.row_key, length(split_part(t.row_key, '|', 1)) + 2)
                      = substr(c.row_key, length(split_part(c.row_key, '|', 1)) + 2)
                    AND split_part(t.row_key, '|', 1) <> split_part(c.row_key, '|', 1)
                    AND split_part(c.row_key, '|', 1) <> ''
                    AND EXISTS (SELECT 1 FROM tmp3_key k
                                WHERE k.entity = lower(c.src_table)
                                  AND list_contains(k.key_cols, 'Period')));
"""


def extract_edited_delta() -> str:
    text = MERGE.read_text(encoding="utf-8")
    start = text.index("CREATE OR REPLACE TABLE tmp3_merge_edited_delta AS")
    end = text.index("CREATE OR REPLACE TABLE tmp3_merge_ent_guard AS", start)
    return text[start:end].rstrip() + "\n"


def extract_memory_limit_paren(s_literal: str | None = None) -> str:
    """Выражение ( WITH ml AS … ) из corpus_merge.sql; опционально подставить литерал s."""
    text = MERGE.read_text(encoding="utf-8")
    anchor = "WITH ml AS (SELECT current_setting('memory_limit') AS s)"
    i = text.find(anchor)
    if i < 0:
        raise RuntimeError("формула memory_limit не найдена в corpus_merge.sql")
    sel = text.rfind("SELECT (", 0, i)
    if sel < 0:
        raise RuntimeError("SELECT ( перед формулой memory_limit не найден")
    end = text.find(") AS ml", i)
    if end < 0:
        raise RuntimeError(") AS ml после формулы memory_limit не найден")
    paren = text[sel + len("SELECT ") : end + 1]  # "( WITH … )"
    if s_literal is not None:
        old = "WITH ml AS (SELECT current_setting('memory_limit') AS s)"
        new = f"WITH ml AS (SELECT {s_literal} AS s)"
        if old not in paren:
            raise RuntimeError("не удалось подставить литерал в формулу memory_limit")
        paren = paren.replace(old, new, 1)
    return paren


def serened_sql(sql: str) -> str:
    """Один сеанс serened shell; маркеры M1:… читает тест."""
    r = subprocess.run(
        ["serened", "shell", "--csv"],
        input=sql,
        text=True,
        capture_output=True,
        env=os.environ.copy(),
        timeout=120,
    )
    out = (r.stdout or "") + ("\n" + r.stderr if r.stderr else "")
    if r.returncode != 0 and "Error" in out:
        # отдельные SELECT после ошибки могут шуметь — отдаём stdout для разбора
        pass
    return out


def serened_sql_rc(sql: str) -> tuple[int, str]:
    """Как serened_sql, но возвращает (returncode, out) — для живого негатива."""
    r = subprocess.run(
        ["serened", "shell", "--csv"],
        input=sql,
        text=True,
        capture_output=True,
        env=os.environ.copy(),
        timeout=120,
    )
    out = (r.stdout or "") + ("\n" + r.stderr if r.stderr else "")
    return r.returncode, out


def markers(out: str) -> dict[str, str]:
    found = {}
    for line in out.splitlines():
        line = line.strip().strip('"')
        if line.startswith("M1:"):
            _, key, *rest = line.split(":", 2)
            found[key] = rest[0] if rest else ""
    return found


# --- структурные проверки файла (как key_form) ---
txt = MERGE.read_text(encoding="utf-8")
t("SQL: empty unmatched CTAS",
  "CREATE OR REPLACE TABLE tmp3_merge_unmatched AS\n"
  "SELECT c.src_table, c.row_key FROM search_corpus c WHERE false;" in txt)
t("SQL: PREPARE p_merge_unmatched", "PREPARE p_merge_unmatched AS" in txt)
t("SQL: src_table = $1", "c.src_table = $1" in txt)
t("SQL: fail-safe NOT IN rewrite_wave в теле",
  "NOT IN (SELECT src_table FROM tmp3_merge_rewrite_wave)" in txt)
t("SQL: диспетчер \\gexec",
  "EXECUTE p_merge_unmatched(" in txt and "\\gexec" in txt)
t("SQL: 6 анти-джойнов Period/tmp3_key",
  "list_contains(k.key_cols, 'Period')" in txt
  and txt.count("AND NOT EXISTS (SELECT 1 FROM tmp3_corpus t") >= 6)
t("SQL: memory_limit \\gset",
  "current_setting('memory_limit')" in txt
  and "\\gset" in txt
  and "SET memory_limit = :'ml';" in txt)
t("SQL: memory_limit без литерала GiB/GB в SET",
  not re.search(r"SET memory_limit\s*=\s*'[0-9.]+\s*(GiB|GB|MiB|MB)'", txt))
t("SQL: memory_limit fail-closed на неизвестной единице",
  "corpus_merge: неизвестная единица memory_limit" in txt
  and "NOT IN ('', 'b', 'kb', 'mb', 'gb', 'kib', 'mib', 'gib')" in txt)
t("SQL: threads не трогаем", "SET threads" not in txt)
i_un = txt.index("PREPARE p_merge_unmatched AS")
i_ed = txt.index("CREATE OR REPLACE TABLE tmp3_merge_edited_delta AS")
i_guard = txt.index("CREATE OR REPLACE TABLE tmp3_merge_ent_guard AS")
t("SQL: порядок prepare < edited_delta < ent_guard", i_un < i_ed < i_guard)

prepare = extract_prepare_body()
edited = extract_edited_delta()
ref_sel = extract_ref_select()

# вырезание формулы memory_limit (якорь) — fail, если дрейф
try:
    _ml_paren = extract_memory_limit_paren()
    _ml_extract_ok = "неизвестная единица memory_limit" in _ml_paren
    _ml_extract_detail = f"{len(_ml_paren)}B"
except RuntimeError as e:
    _ml_paren = ""
    _ml_extract_ok = False
    _ml_extract_detail = str(e)
t("SQL: формула memory_limit вырезается из файла", _ml_extract_ok, _ml_extract_detail)

# --- живая фикстура в serened shell ---
fixture_sql = f"""
ATTACH ':memory:' AS mem;
USE mem;

CREATE TABLE search_corpus (
  src_table VARCHAR, row_key VARCHAR, refs VARCHAR, doc VARCHAR);
INSERT INTO search_corpus VALUES
  -- ent_a: orphan k1; matched k2; edited-pair (старый sha, тот же refs)
  ('ent_a', 'k1', 'refs-a-1', 'old'),
  ('ent_a', 'k2', 'refs-a-2', 'keep'),
  ('ent_a', 'oldsha#dead', 'refs-a-edit', 'was'),
  -- ent_b: orphan plain
  ('ent_b', 'orphan-b', 'refs-b', 'x'),
  -- ent_wave: в стейдже и в wave — unmatched не строится
  ('ent_wave', 'wave-old-1', 'rw', 'w'),
  ('ent_wave', 'wave-old-2', 'rw', 'w'),
  -- вне стейджа: не попадает в unmatched ни по монолиту, ни по резке
  ('ent_other', 'solo', 'r', 'y');

CREATE TABLE tmp3_corpus (
  src_table VARCHAR, row_key VARCHAR, refs VARCHAR, doc VARCHAR);
INSERT INTO tmp3_corpus VALUES
  ('ent_a', 'k2', 'refs-a-2', 'keep'),
  ('ent_a', 'newsha', 'refs-a-edit', 'now'),
  ('ent_b', 'new-b', 'refs-b2', 'z'),
  ('ent_wave', 'wave-new', 'rw', 'w');

CREATE TABLE tmp3_merge_rewrite_wave (
  src_table VARCHAR, было BIGINT, стало BIGINT);
INSERT INTO tmp3_merge_rewrite_wave VALUES ('ent_wave', 100, 102);

CREATE TABLE tmp3_key (entity VARCHAR, key_cols VARCHAR[]);
INSERT INTO tmp3_key VALUES
  ('ent_a', ['Ref_Key']),
  ('ent_b', ['Ref_Key']),
  ('ent_wave', ['Period']);

-- диспетчерский список (как в corpus_merge.sql)
CREATE OR REPLACE TABLE tmp3_merge_dispatch AS
SELECT DISTINCT src_table FROM tmp3_corpus
WHERE src_table NOT IN (SELECT src_table FROM tmp3_merge_rewrite_wave);

SELECT 'M1:dispatch|' || string_agg(src_table, ',' ORDER BY src_table)
FROM tmp3_merge_dispatch;

-- резка: каркас + PREPARE + EXECUTE по списку диспетчера
CREATE OR REPLACE TABLE tmp3_merge_unmatched AS
SELECT c.src_table, c.row_key FROM search_corpus c WHERE false;

{prepare}

SELECT 'EXECUTE p_merge_unmatched(' || quote_literal(src_table) || ');'
FROM tmp3_merge_dispatch;
-- serened shell без \\gexec — зовём EXECUTE сами:
EXECUTE p_merge_unmatched('ent_a');
EXECUTE p_merge_unmatched('ent_b');

{ref_sel}

SELECT 'M1:eq_ref|' || (
  (SELECT count(*) FROM tmp3_merge_unmatched)
    = (SELECT count(*) FROM tmp3_merge_unmatched_ref)
  AND NOT EXISTS (
    SELECT 1 FROM tmp3_merge_unmatched s
    FULL OUTER JOIN tmp3_merge_unmatched_ref r USING (src_table, row_key)
    WHERE s.row_key IS NULL OR r.row_key IS NULL)
)::VARCHAR;

SELECT 'M1:wave0|' || (
  SELECT count(*) FROM tmp3_merge_unmatched WHERE src_table = 'ent_wave'
)::VARCHAR;

SELECT 'M1:uniq|' || (
  SELECT count(*) = count(DISTINCT src_table || chr(1) || row_key)
  FROM tmp3_merge_unmatched
)::VARCHAR;

SELECT 'M1:no_other|' || (
  SELECT count(*) FROM tmp3_merge_unmatched WHERE src_table = 'ent_other'
)::VARCHAR;

{edited}

SELECT 'M1:ed1|' || coalesce((SELECT sum(правок)::VARCHAR FROM tmp3_merge_edited_delta), '0');

-- свежесть: меняем unmatched → edited_delta меняется
DELETE FROM tmp3_merge_unmatched WHERE row_key = 'oldsha#dead';
{edited}
SELECT 'M1:ed2|' || coalesce((SELECT sum(правок)::VARCHAR FROM tmp3_merge_edited_delta), '0');

-- memory_limit формула (как в шапке merge): та же единица, 0.55
CREATE OR REPLACE TABLE tmp3_ml_probe AS
SELECT (
  WITH ml AS (SELECT current_setting('memory_limit') AS s),
  parsed AS (
    SELECT s,
           lower(trim(regexp_replace(s, '^[0-9.]+\\s*', ''))) AS unit_l,
           try_cast(regexp_extract(s, '^([0-9.]+)', 1) AS DOUBLE) AS n
    FROM ml
  ),
  bytes AS (
    SELECT s, unit_l, n,
           CASE
             WHEN unit_l NOT IN ('', 'b', 'kb', 'mb', 'gb', 'kib', 'mib', 'gib')
               THEN error('corpus_merge: неизвестная единица memory_limit: ' || s)
             WHEN unit_l IN ('gib') THEN n * power(1024::BIGINT, 3)
             WHEN unit_l IN ('mib') THEN n * power(1024::BIGINT, 2)
             WHEN unit_l IN ('kib') THEN n * 1024
             WHEN unit_l IN ('gb')  THEN n * power(1000::BIGINT, 3)
             WHEN unit_l IN ('mb')  THEN n * power(1000::BIGINT, 2)
             WHEN unit_l IN ('kb')  THEN n * 1000
             ELSE n
           END AS mem_bytes,
           CASE
             WHEN unit_l IN ('gib') THEN power(1024::BIGINT, 3)
             WHEN unit_l IN ('mib') THEN power(1024::BIGINT, 2)
             WHEN unit_l IN ('kib') THEN 1024
             WHEN unit_l IN ('gb')  THEN power(1000::BIGINT, 3)
             WHEN unit_l IN ('mb')  THEN power(1000::BIGINT, 2)
             WHEN unit_l IN ('kb')  THEN 1000
             ELSE 1
           END AS div,
           CASE
             WHEN unit_l IN ('gib') THEN 'GiB'
             WHEN unit_l IN ('mib') THEN 'MiB'
             WHEN unit_l IN ('kib') THEN 'KiB'
             WHEN unit_l IN ('gb')  THEN 'GB'
             WHEN unit_l IN ('mb')  THEN 'MB'
             WHEN unit_l IN ('kb')  THEN 'KB'
             ELSE 'B'
           END AS unit
    FROM parsed
  )
  SELECT (floor(mem_bytes * 0.55 / div))::BIGINT::VARCHAR
         || CASE WHEN position(' ' in s) > 0 THEN ' ' ELSE '' END
         || unit
  FROM bytes
) AS ml;
SELECT 'M1:ml|' || ml FROM tmp3_ml_probe;
"""

out = serened_sql(fixture_sql)
m = markers(out)

# markers lines look like M1:eq_ref|true — our parser splits on first two colons
# Fix: we used M1:key|value with one colon after M1
def mget(key):
    # markers() splits M1:key|val → key, rest='|val' if we used split(..., 2) wrong
    # re-parse
    for line in out.splitlines():
        line = line.strip().strip('"')
        if line.startswith("M1:" + key + "|"):
            return line.split("|", 1)[1]
        # csv may wrap
        if ("M1:" + key + "|") in line:
            return line.split(key + "|", 1)[1].strip().strip('"')
    return m.get(key, "")


t("engine: dispatch == ent_a,ent_b",
  mget("dispatch") == "ent_a,ent_b", mget("dispatch") or out[-400:])
t("engine: unmatched == эталонный SELECT",
  mget("eq_ref") == "true", mget("eq_ref") or out[-500:])
t("engine: wave → 0 строк unmatched",
  mget("wave0") == "0", mget("wave0"))
t("engine: уникальность (src_table,row_key)",
  mget("uniq") == "true", mget("uniq"))
t("engine: вне стейджа не в unmatched",
  mget("no_other") == "0", mget("no_other"))

ed1, ed2 = mget("ed1"), mget("ed2")
t("engine: edited_delta от свежего unmatched (до>0)",
  ed1.isdigit() and int(ed1) > 0, f"ed1={ed1}")
t("engine: edited_delta меняется после правки unmatched",
  ed1 != ed2 and ed2.isdigit(), f"ed1={ed1} ed2={ed2}")

ml = mget("ml")
t("engine: memory_limit формула вернула единицу GiB/GB/…",
  bool(re.search(r"[0-9]+\s*(GiB|MiB|KiB|GB|MB|KB|B)$", ml or "")), ml)

# --- пустая база: только нужные таблицы, без прочих tmp3_merge_* ---
empty_sql = f"""
ATTACH ':memory:' AS mem;
USE mem;
CREATE TABLE search_corpus (src_table VARCHAR, row_key VARCHAR, refs VARCHAR);
CREATE TABLE tmp3_corpus (src_table VARCHAR, row_key VARCHAR, refs VARCHAR);
CREATE TABLE tmp3_merge_rewrite_wave (src_table VARCHAR, было BIGINT, стало BIGINT);
CREATE TABLE tmp3_key (entity VARCHAR, key_cols VARCHAR[]);
CREATE OR REPLACE TABLE tmp3_merge_unmatched AS
SELECT c.src_table, c.row_key FROM search_corpus c WHERE false;
{prepare}
{edited}
SELECT 'M1:empty_ok|' || (SELECT count(*) FROM tmp3_merge_unmatched)::VARCHAR
  || '/' || (SELECT count(*) FROM tmp3_merge_edited_delta)::VARCHAR;
"""
out2 = serened_sql(empty_sql)
ok_empty = "M1:empty_ok|0/0" in out2 and "does not exist" not in out2.lower()
t("engine: пустая база без лишних tmp3_* не падает",
  ok_empty, out2[-400:] if not ok_empty else "")

# --- живой негатив unknown-unit + позитив GiB (формула ВЫРЕЗАНА из файла) ---
if _ml_extract_ok:
    try:
        ml_neg = extract_memory_limit_paren("'80%'")
        ml_pos = extract_memory_limit_paren("'50.0 GiB'")
    except RuntimeError as e:
        ml_neg = ml_pos = ""
        t("engine: подстановка s в формулу memory_limit", False, str(e))
        ml_neg = None
    if ml_neg is not None:
        rc_neg, out_neg = serened_sql_rc(
            f"ATTACH ':memory:' AS mem;\nUSE mem;\nSELECT {ml_neg} AS ml;\n"
        )
        t(
            "engine: unknown-unit s='80%' → error",
            rc_neg != 0 and "неизвестная единица" in out_neg,
            f"rc={rc_neg} {out_neg[-300:]}",
        )
        rc_pos, out_pos = serened_sql_rc(
            "ATTACH ':memory:' AS mem;\nUSE mem;\n"
            f"SELECT 'M1:ml_pos|' || ({ml_pos}) AS m;\n"
        )
        pos_val = ""
        for line in out_pos.splitlines():
            line = line.strip().strip('"')
            if "M1:ml_pos|" in line:
                pos_val = line.split("M1:ml_pos|", 1)[1].strip().strip('"')
                break
        t(
            "engine: s='50.0 GiB' → '27 GiB'",
            rc_pos == 0 and pos_val == "27 GiB",
            f"rc={rc_pos} got={pos_val!r} out={out_pos[-200:]}",
        )
else:
    t("engine: unknown-unit s='80%' → error", False, "формула не вырезана")
    t("engine: s='50.0 GiB' → '27 GiB'", False, "формула не вырезана")

print("PASS %d FAIL %d" % (PASS, len(FAIL)))
sys.exit(1 if FAIL else 0)
