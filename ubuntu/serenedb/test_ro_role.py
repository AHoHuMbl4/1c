#!/usr/bin/env python3
"""Защита в глубину: роль serene_ro должна ФИЗИЧЕСКИ отвергать любую запись (даже если валидатор обойдён).
Требует PGPASSWORD (serene_ro) в env. Таблица берётся ДИНАМИЧЕСКИ из схемы — без вшитого имени."""
import subprocess
import sys

DSN = "host=127.0.0.1 port=7890 user=serene_ro dbname=postgres"
_fail = 0


def run(sql):
    return subprocess.run(["psql", DSN, "-tAc", sql], text=True, capture_output=True)


def check(name, cond, detail=""):
    global _fail
    if not cond:
        _fail += 1
    print(f"  {'PASS' if cond else 'FAIL ✗'}  {name}   {detail}")


def _pick():
    """Реальная таблица витрины + её колонка — динамически (без вшитого имени)."""
    t = run("SELECT table_name FROM duckdb_columns() WHERE schema_name='public' "
            "AND table_name <> 'resolver_index' LIMIT 1").stdout.strip()
    c = run(f"SELECT column_name FROM duckdb_columns() WHERE schema_name='public' "
            f"AND table_name='{t}' LIMIT 1").stdout.strip() if t else ""
    return t, c


def main():
    t, c = _pick()
    if not t:
        sys.exit("нет таблиц в витрине")
    writes = [
        ("INSERT", f'INSERT INTO "{t}" SELECT * FROM "{t}" LIMIT 0'),
        ("UPDATE", f'UPDATE "{t}" SET "{c}" = "{c}"'),
        ("DELETE", f'DELETE FROM "{t}" WHERE false'),
        ("DROP", f'DROP TABLE "{t}"'),
        ("CREATE", "CREATE TABLE t_ro_probe(x int)"),
        ("TRUNCATE", f'TRUNCATE "{t}"'),
    ]
    print(f"== запись под serene_ro должна ОТВЕРГАТЬСЯ (таблица {t}) ==")
    for name, sql in writes:
        r = run(sql)
        rejected = r.returncode != 0
        tail = (r.stderr or r.stdout).strip().splitlines()[-1][:80] if (r.stderr or r.stdout).strip() else "(выполнилось!)"
        check(f"{name} отвергнут", rejected, tail)

    print("== эскалация привилегий не проходит ==")
    rg = run(f'GRANT INSERT ON "{t}" TO serene_ro')
    grant_noop = rg.returncode != 0 or "no privileges were granted" in (rg.stderr + rg.stdout).lower()
    check("GRANT INSERT — no-op/отклонён", grant_noop, (rg.stderr or rg.stdout).strip().splitlines()[-1][:70])
    ri = run(f'INSERT INTO "{t}" SELECT * FROM "{t}" LIMIT 0')
    check("после GRANT запись всё равно отвергнута", ri.returncode != 0,
          (ri.stderr or ri.stdout).strip().splitlines()[-1][:70] if (ri.stderr or ri.stdout).strip() else "(выполнилось!)")

    print("== чтение под serene_ro должно РАБОТАТЬ ==")
    r = run(f'SELECT count(*) FROM "{t}"')
    check("SELECT работает", r.returncode == 0 and r.stdout.strip().isdigit(), f"got={r.stdout.strip()[:30]}")
    print(f"\nИТОГ: {'ВСЁ PASS ✅' if _fail == 0 else str(_fail) + ' FAIL ✗'}")
    sys.exit(1 if _fail else 0)


if __name__ == "__main__":
    main()
