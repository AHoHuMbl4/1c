#!/usr/bin/env python3
"""Офлайн-замок deploy-sql.sh: bash -n + --offline-dry (без SSH)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCRIPT = ROOT / "deploy-sql.sh"
COMMON = ROOT / "deploy-common.sh"
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
    t("script exists", SCRIPT.is_file())
    t("common exists", COMMON.is_file())
    r = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
    t("bash -n deploy-sql", r.returncode == 0, r.stderr)
    r2 = subprocess.run(["bash", "-n", str(COMMON)], capture_output=True, text=True)
    t("bash -n deploy-common", r2.returncode == 0, r2.stderr)
    r3 = subprocess.run(
        ["bash", str(SCRIPT), "--offline-dry"],
        capture_output=True, text=True, cwd=str(ROOT))
    t("offline-dry exit 0", r3.returncode == 0, r3.stderr[:200])
    out = r3.stdout
    for name in ("corpus_build.sql", "corpus_merge.sql", "corpus_precheck.sql",
                 "wiki_build.sql", "wiki_passport.sql", "resolver_build.sql"):
        t("offline lists %s" % name, name in out)
    t("offline says no SSH compare", "нет SSH" in out or "не сверяли" in out)

    body = SCRIPT.read_text(encoding="utf-8")
    t("sources deploy-common", "deploy-common.sh" in body)
    t("has --dry", "--dry" in body)
    t("atomic mv pattern", ".new" in body and "mv " in body)

    ask = ROOT / "deploy-ask.sh"
    if ask.is_file():
        ab = ask.read_text(encoding="utf-8")
        t("deploy-ask sources common", "deploy-common.sh" in ab)
        ra = subprocess.run(["bash", "-n", str(ask)], capture_output=True, text=True)
        t("bash -n deploy-ask", ra.returncode == 0, ra.stderr)

    total = PASS + len(FAIL)
    if FAIL:
        print("FAIL %d/%d" % (len(FAIL), total))
        return 1
    print("OK %d/%d" % (PASS, total))
    return 0


if __name__ == "__main__":
    sys.exit(main())
