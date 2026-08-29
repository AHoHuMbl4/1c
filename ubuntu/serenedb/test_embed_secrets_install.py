#!/usr/bin/env python3
"""Оффлайн-замок embed_secrets_install: идемпотентные персистентные секреты (О5).

Проверяет: SQL без TEMPORARY, psql -v (не -c с ключом), динамическое число хостов,
qwen = первый хост, имена emb_<база>_N от current_database().
Запуск: python3 ubuntu/serenedb/test_embed_secrets_install.py
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCRIPT = ROOT / "embed_secrets_install.sh"
SQL = ROOT / "embed_secrets_install.sql"
UNIT = ROOT.parent / "systemd" / "1c-serene-embed-secrets.service"
DROPIN = ROOT.parent / "systemd" / "serenedb.service.d" / "embed-secrets.conf"
PASS, FAIL = 0, []


def t(name: str, cond: bool, detail: str = "") -> None:
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + detail[:200]) if detail else "")


def main() -> int:
    body = SCRIPT.read_text(encoding="utf-8")
    sql = SQL.read_text(encoding="utf-8")
    unit = UNIT.read_text(encoding="utf-8")
    dropin = DROPIN.read_text(encoding="utf-8")
    code = re.sub(r"#.*", "", body)

    t("script exists", SCRIPT.is_file())
    t("sql exists", SQL.is_file())
    t("unit exists", UNIT.is_file())
    t("serenedb drop-in exists", DROPIN.is_file())

    r = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
    t("bash -n", r.returncode == 0, r.stderr[:120])

    t("CREATE OR REPLACE SECRET in sql", "CREATE OR REPLACE SECRET" in sql)
    t("no TEMPORARY in sql", "TEMPORARY" not in sql)
    t("psql vars sec_name api_key", ':"sec_name"' in sql and ":'api_key'" in sql)
    t("shell uses psql -v", re.search(r"-v\s+[\"']?sec_name=", body) is not None and "-f" in body)
    t("no inline CREATE in shell -c", "psql" not in code or "-c \"CREATE" not in body)
    t("qwen secret", 'apply_secret "qwen"' in body)
    t("emb from current_database", "current_database()" in body)
    t("dynamic pairs loop", "for i in \"${!PAIRS[@]}\"" in body)
    t("no hardcoded host count", "EMBED_HOSTS" in body and "PAIRS[@]" in body)
    t("count check duckdb_secrets", "duckdb_secrets()" in body)

    t("unit After serenedb", "After=" in unit and "serenedb.service" in unit)
    t("unit EnvironmentFile embed", "EnvironmentFile=/etc/1c-embed.env" in unit)
    t("unit oneshot", "Type=oneshot" in unit)
    t("unit ExecStart script", "embed_secrets_install.sh" in unit)

    t("drop-in ExecStartPost", "ExecStartPost=" in dropin)
    t("drop-in starts embed unit", "1c-serene-embed-secrets.service" in dropin)

    t("regress: not TEMPORARY in shell secrets", "TEMPORARY SECRET" not in body)

    total = PASS + len(FAIL)
    if FAIL:
        print("FAIL %d/%d" % (len(FAIL), total))
        return 1
    print("OK %d/%d" % (PASS, total))
    return 0


if __name__ == "__main__":
    sys.exit(main())
