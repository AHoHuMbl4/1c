#!/usr/bin/env python3
"""Проба p_doc_plain: порядковый суффикс ключа при дублях (§3.77 / F2).

Сущность с ключом-обёрткой (много строк на один объявленный ключ) через plain-путь:
  • все строки в tmp3_corpus;
  • ключи (src_table, row_key) уникальны — сторож corpus_merge проходит;
  • повторный прогон по тем же данным → те же ключи (стабильность векторов).

Требует живой SereneDB (PGPASSWORD + DSN из /etc/1c-mcp-reports.env).
Запуск: python3 test_corpus_plain_key.py
"""
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SQL_FILE = ROOT / "corpus_build.sql"
ENTITY = "t_f2_plain_key_probe"
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
_base = os.environ.get("SERENEDB_DSN", "")
DSN = _base.replace("user=serene_ro", "user=postgres") if _base else ""


def psql_file(path):
    r = subprocess.run(
        ["psql", DSN, "-v", "ON_ERROR_STOP=1", "-tA", "-f", str(path)],
        text=True,
        capture_output=True,
        env=os.environ.copy(),
    )
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip()[:800])
    return r.stdout.strip()


def check(name, cond, detail=""):
    global _fail, _checks
    _checks += 1
    if not cond:
        _fail += 1
    print(f"  {'PASS' if cond else 'FAIL ✗'}  {name}   {detail}")


def _extract_prepare():
    text = SQL_FILE.read_text(encoding="utf-8")
    start = text.index("PREPARE p_doc_plain AS")
    end = text.index("FROM base;", start) + len("FROM base;")
    return text[start:end]


def _session_script(extra_after_first_run=""):
    prepare = _extract_prepare()
    return f"""\\set ON_ERROR_STOP on
DROP TABLE IF EXISTS {ENTITY};
CREATE TABLE {ENTITY} AS
SELECT * FROM (VALUES
 ('rec-A', '10', 'same'),
 ('rec-A', '10', 'same'),
 ('rec-A', '10', 'same'),
 ('rec-B', '20', 'other'),
 ('rec-C', '30', 'third')) AS t(recorder, amount, note);
CREATE OR REPLACE TABLE tmp3_key AS
SELECT '{ENTITY.lower()}' AS entity, ['recorder'] AS key_cols;
CREATE OR REPLACE TABLE tmp3_corpus (
  src_table VARCHAR, row_key VARCHAR, doc VARCHAR, refs VARCHAR, doc_hash VARCHAR,
  nums MAP(VARCHAR, DOUBLE), flags MAP(VARCHAR, BOOLEAN), doc_date TIMESTAMP,
  refs_map MAP(VARCHAR, VARCHAR), refs_own MAP(VARCHAR, VARCHAR));
DELETE FROM tmp3_corpus WHERE src_table = '{ENTITY}';
\set ON_ERROR_STOP off
DEALLOCATE p_doc_plain;
\set ON_ERROR_STOP on
{prepare}
EXECUTE p_doc_plain('{ENTITY}');
SELECT 'ROWS' || chr(124) || count(*)::VARCHAR FROM tmp3_corpus WHERE src_table = '{ENTITY}';
SELECT 'DUPS' || chr(124) || count(*)::VARCHAR FROM (
  SELECT src_table, row_key FROM tmp3_corpus WHERE src_table = '{ENTITY}'
  GROUP BY 1, 2 HAVING count(*) > 1) d;
SELECT 'KEY' || chr(124) || row_key FROM tmp3_corpus WHERE src_table = '{ENTITY}' ORDER BY row_key;
{extra_after_first_run}
"""  # noqa: W605


def _parse_out(raw):
    rows = dups = None
    keys = []
    for line in raw.splitlines():
        if line.startswith("ROWS|"):
            rows = int(line.split("|", 1)[1])
        elif line.startswith("DUPS|"):
            dups = int(line.split("|", 1)[1])
        elif line.startswith("KEY|"):
            keys.append(line.split("|", 1)[1])
    return rows, dups, keys


def main():
    if not os.environ.get("PGPASSWORD") or not DSN:
        print("PGPASSWORD/DSN не задан — пропуск живой пробы (нет SereneDB)")
        sys.exit(0)

    print(f"== p_doc_plain ключи ({ENTITY}) ==")
    script1 = ROOT / ".test_corpus_plain_key_run.sql"
    script1.write_text(
        _session_script(
            extra_after_first_run=f"""
DELETE FROM tmp3_corpus WHERE src_table = '{ENTITY}';
EXECUTE p_doc_plain('{ENTITY}');
SELECT 'KEY2' || chr(124) || row_key FROM tmp3_corpus WHERE src_table = '{ENTITY}' ORDER BY row_key;
DROP TABLE IF EXISTS {ENTITY};
"""
        ),
        encoding="utf-8",
    )
    raw = psql_file(script1)
    rows, dups, keys = _parse_out(raw)
    keys2 = [ln.split("|", 1)[1] for ln in raw.splitlines() if ln.startswith("KEY2|")]

    check("все строки источника в корпусе", rows == 5, f"rows={rows}")
    check("дублей ключа нет (сторож merge)", dups == 0, f"dups={dups}")
    check("уникальных ключей столько же, сколько строк", len(keys) == rows, f"keys={len(keys)}")

    suffixed = [k for k in keys if re.match(r"^rec-A#\d+$", k)]
    check("одинаковый ключ-обёртка получила #N", len(suffixed) == 3, f"{suffixed}")
    check("одиночный rec-B без суффикса", "rec-B" in keys)
    check("одиночный rec-C без суффикса", "rec-C" in keys)
    check("повторный прогон — те же ключи", keys == keys2, f"was={keys} now={keys2}")

    bad = [k for k in keys2 if re.search(r"#\d+#\d+$", k)]
    check("нет rk#N#M (двойной суффикс)", not bad, str(bad))

    print(f"\nИТОГ: {_checks - _fail}/{_checks} PASS"
          + (" ✅" if _fail == 0 else f", {_fail} FAIL ✗"))
    sys.exit(1 if _fail else 0)


if __name__ == "__main__":
    main()
