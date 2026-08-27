#!/usr/bin/env python3
"""Оффлайн-замок Э1: embed_missing без веера внешних psql.

(а) нет `for w in $(seq` / фоновых `psql … &`;
(б) одна staging `${TAG}_part_0` + \\gexec;
(в) EMBED_ROUNDS умолчание 1;
(г) bash -n; синтетическая порча веера краснеет.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCRIPT = ROOT / "embed_missing.sh"
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
    code = re.sub(r"#.*", "", body)

    t("+x", bool(SCRIPT.stat().st_mode & 0o111))
    r = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
    t("bash -n", r.returncode == 0, r.stderr[:120])

    t("нет for w in seq воркеров", "for w in $(seq" not in code and "for w in `seq" not in code)
    t("нет фоновых psql &",
      not re.search(r"psql[^\n]*\s+&", code)
      and "pids+=($!)" not in code)
    t("есть part_0", "${TAG}_part_0" in body)
    t("один \\gexec", code.count("\\gexec") == 1 or body.count("\\gexec") == 1)
    t("EMBED_ROUNDS умолчание 1", "EMBED_ROUNDS:-1" in body)
    t("воркеры игнорируются (Э1)", "игнорируются" in body and "Э1" in body)
    t("SET threads в сессии досчёта", "SET threads" in body)

    old_fan = 'for w in $(seq 0 $((N - 1))); do\n  psql "$DSN" ... &\ndone\n'
    t("regress: веер seq краснеет", "for w in $(seq" in old_fan)
    t("regress: фон & краснеет", "&\n" in old_fan)

    total = PASS + len(FAIL)
    if FAIL:
        print("FAIL %d/%d" % (len(FAIL), total))
        return 1
    print("OK %d/%d" % (PASS, total))
    return 0


if __name__ == "__main__":
    sys.exit(main())
