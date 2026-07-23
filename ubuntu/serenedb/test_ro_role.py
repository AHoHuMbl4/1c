#!/usr/bin/env python3
"""Защита в глубину: роль serene_ro должна ФИЗИЧЕСКИ отвергать любую запись (даже если валидатор
обойдён). Требует PGPASSWORD (serene_ro) в env. По эффекту read-only — все попытки записи падают.
Запуск в окружении reports (PGPASSWORD из /etc/1c-mcp-reports.env)."""
import subprocess
import sys

DSN = "host=127.0.0.1 port=7890 user=serene_ro dbname=postgres"
WRITES = [
    ("INSERT", "INSERT INTO banks(ref_key) VALUES ('ro_probe')"),
    ("UPDATE", "UPDATE banks SET city = 'RO_PROBE'"),
    ("DELETE", "DELETE FROM banks WHERE ref_key = 'ro_probe'"),
    ("DROP", "DROP TABLE banks"),
    ("CREATE", "CREATE TABLE t_ro_probe(x int)"),
    ("TRUNCATE", "TRUNCATE banks"),
]
_fail = 0


def run(sql):
    return subprocess.run(["psql", DSN, "-tAc", sql], text=True, capture_output=True)


def check(name, cond, detail=""):
    global _fail
    if not cond:
        _fail += 1
    print(f"  {'PASS' if cond else 'FAIL ✗'}  {name}   {detail}")


def main():
    print("== запись под serene_ro должна ОТВЕРГАТЬСЯ ==")
    for name, sql in WRITES:
        r = run(sql)
        rejected = r.returncode != 0
        check(f"{name} отвергнут", rejected, (r.stderr or r.stdout).strip().splitlines()[-1][:80] if (r.stderr or r.stdout).strip() else "(выполнилось!)")
    print("== эскалация привилегий не проходит ==")
    # не-владелец не может выдать привилегию: БД делает no-op (WARNING «no privileges were granted»)
    # или ошибку — в любом случае это НЕ эскалация. Главное доказательство — запись после GRANT всё равно падает.
    rg = run("GRANT INSERT ON banks TO serene_ro")
    grant_noop = rg.returncode != 0 or "no privileges were granted" in (rg.stderr + rg.stdout).lower()
    check("GRANT INSERT — no-op/отклонён", grant_noop, (rg.stderr or rg.stdout).strip().splitlines()[-1][:70])
    ri = run("INSERT INTO banks(ref_key) VALUES ('ro_probe2')")
    check("после GRANT запись всё равно отвергнута", ri.returncode != 0,
          (ri.stderr or ri.stdout).strip().splitlines()[-1][:70] if (ri.stderr or ri.stdout).strip() else "(выполнилось!)")

    print("== чтение под serene_ro должно РАБОТАТЬ ==")
    r = run("SELECT count(*) FROM banks")
    check("SELECT работает", r.returncode == 0 and r.stdout.strip().isdigit(), f"got={r.stdout.strip()[:30]}")
    print(f"\nИТОГ: {'ВСЁ PASS ✅' if _fail == 0 else str(_fail) + ' FAIL ✗'}")
    sys.exit(1 if _fail else 0)


if __name__ == "__main__":
    main()
