#!/usr/bin/env python3
"""Оффлайн-замок G7c: deploy_wiki_alias.sh — выкат генератора без живого scp.

Проверяет: bash -n; FILES ⊇ вызовам wiki_alias.sh (-f $HERE/… и python3 ./…);
md5-сверка; бэкап перед заменой; нет systemctl/restart; ключ из env, не дефолт argv.
Запуск: python3 ubuntu/serenedb/test_wiki_alias_deploy.py
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCRIPT = ROOT / "deploy_wiki_alias.sh"
WIKI = ROOT / "wiki_alias.sh"
PASS, FAIL = 0, []


def t(name: str, cond: bool, detail: str = "") -> None:
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + detail[:240]) if detail else "")


def extract_files_array(body: str) -> set[str]:
    m = re.search(r"^FILES=\(\s*(.*?)^\s*\)", body, re.M | re.S)
    if not m:
        return set()
    return set(re.findall(r"([A-Za-z0-9_./-]+\.(?:sh|py|sql))", m.group(1)))


def required_from_wiki(wiki_body: str) -> set[str]:
    need: set[str] = {"wiki_alias.sh"}
    need.update(re.findall(r'-f\s+"\$HERE/([^"]+)"', wiki_body))
    need.update(re.findall(r'python3\s+\./([A-Za-z0-9_.-]+\.py)', wiki_body))
    return need


def main() -> int:
    t("deploy script exists", SCRIPT.is_file())
    t("wiki_alias.sh exists", WIKI.is_file())
    body = SCRIPT.read_text(encoding="utf-8") if SCRIPT.is_file() else ""
    wiki = WIKI.read_text(encoding="utf-8") if WIKI.is_file() else ""

    r = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
    t("bash -n", r.returncode == 0, (r.stderr or r.stdout)[:200])

    files = extract_files_array(body)
    need = required_from_wiki(wiki)
    missing = sorted(need - files)
    t(
        "FILES ⊇ wiki_alias calls ($HERE -f + python3 ./)",
        not missing,
        f"missing={missing}; files={len(files)} need={len(need)}",
    )
    for f in sorted(need):
        t(f"covers {f}", f in files)

    # Night hot-set (G7-checklist §1): wiki_alias* core + gateway + usage_log
    night_core = {
        "wiki_alias.sh",
        "wiki_alias_parse.py",
        "alias_infer_gateway.py",
        "alias_usage_log.py",
        "wiki_alias_init.sql",
        "wiki_alias_select_entity_batch.sql",
        "wiki_alias_select_measure_batch.sql",
        "wiki_alias_merge_entity.sql",
        "wiki_alias_merge_measures.sql",
        "wiki_alias_collision_left.sql",
        "wiki_alias_collision_round.sql",
    }
    night_miss = sorted(night_core - files)
    t("covers G7 night scp core", not night_miss, f"missing={night_miss}")

    reask = {
        "wiki_alias_reask_init.sql",
        "wiki_alias_reask_select_entity_batch.sql",
        "wiki_alias_reask_merge_confirmed.sql",
        "wiki_alias_reask_journal.sql",
    }
    t("covers reask SQL", reask <= files, f"missing={sorted(reask - files)}")
    t(
        "covers branch_alias.sh (optional fork contour)",
        "branch_alias.sh" in files,
    )

    code = re.sub(r"[ \t]*#.*", "", body)

    t("md5sum present", "md5sum" in code)
    t("md5 mismatch exits non-zero", "MISMATCH" in code and "exit 1" in code)
    t("backup .bak-deploy-", ".bak-deploy-" in code)
    bak_pos = code.find("bak-deploy-")
    scp_pos = code.find("\nscp ")
    if scp_pos < 0:
        scp_pos = code.find("scp ")
    t("backup before scp", bak_pos >= 0 and scp_pos >= 0 and bak_pos < scp_pos)
    t("chmod 755 wiki_alias.sh", "chmod 755" in code and "wiki_alias.sh" in code)

    t("no systemctl", "systemctl" not in code)
    t("no restart marker", not re.search(r"\brestart\b", code, re.I))
    # Не запускает генерацию: нет прямого exec/bash wiki_alias.sh
    t(
        "does not run wiki_alias.sh",
        not re.search(r"(?:bash|exec)\s+[^\n]*wiki_alias\.sh\b", code),
    )

    t("WIKI_DEPLOY_TARGET env", "WIKI_DEPLOY_TARGET" in body)
    t("WIKI_DEPLOY_SSH_KEY env", "WIKI_DEPLOY_SSH_KEY" in body)
    t("WIKI_DEPLOY_DIR default /opt", "WIKI_DEPLOY_DIR" in body and "/opt/1c-mcp-reports" in body)
    # Ключ не зашит дефолтом во 2-й аргумент: пустой fallback из env
    t(
        "SSH key default empty (from env)",
        re.search(
            r'SSH_KEY="\$\{2:- \$\{WIKI_DEPLOY_SSH_KEY:-\}\}"'.replace(" ", ""),
            body.replace(" ", ""),
        )
        is not None
        or 'SSH_KEY="${2:-${WIKI_DEPLOY_SSH_KEY:-}}"' in body,
    )
    t("no hardcoded IdentityFile path", not re.search(r"/home/\S+\.ssh/|/root/\.ssh/", code))
    t("set -euo pipefail / bash strict", "set -euo pipefail" in body)

    print(f"\n{PASS} ok, {len(FAIL)} fail")
    if FAIL:
        print("FAILED:", ", ".join(FAIL))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
