#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Оффлайн-замок: шаблоны systemd не зовут несуществующие и выведенные скрипты.

Э5: мёртвый шаблон в ubuntu/serenedb/systemd/ удалён. Канон —
ubuntu/systemd/1c-serene-index.service → build.sh; замок падает, если
ExecStart живого юнита перестал ссылаться на build.sh.
"""
from __future__ import annotations

import glob
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

# Префиксы раскладки deploy.sh / install — путь юнита → путь в дереве.
DEPLOY_PREFIXES: tuple[tuple[str, str], ...] = (
    ("/opt/1c-mcp-reports/", "ubuntu/serenedb/"),
    ("/opt/openclaw-mcp/", "ubuntu/openclaw/"),
    ("/opt/1c-packet/", "ubuntu/packet/"),
    ("/opt/1c-odata-gateway/", "ubuntu/1c-gateway/"),
    ("/opt/1c-gateway/", "ubuntu/1c-gateway/"),
    ("/opt/1c-etl/", "ubuntu/1c-etl/"),
    ("/opt/1c-config-ui/", "ubuntu/1c-config-ui/"),
)

# Файлы в дереве есть, но ExecStart на них запрещён (выведены из контура).
WITHDRAWN_BASENAMES: frozenset[str] = frozenset({"serene_search_build.py"})

# Интерпретаторы и системные бинарники — не проверяем как цель.
INTERPRETER_SUFFIXES = ("/python", "/python3", "/bash", "/sh", "/openclaw")

EXEC_KEYS = ("ExecStart=", "ExecStartPre=", "ExecStartPost=")

# Канон раскатки index: одна копия, только ubuntu/systemd/.
LIVE_INDEX_UNIT = os.path.join(ROOT, "ubuntu", "systemd", "1c-serene-index.service")
# Мёртвый двойник удалён (Э5) — путь не должен снова появиться в дереве.
DEAD_INDEX_UNIT = os.path.join(
    ROOT, "ubuntu", "serenedb", "systemd", "1c-serene-index.service"
)

FAILS: list[str] = []
CHECKS = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global CHECKS
    CHECKS += 1
    if cond:
        print("ok  -", name)
    else:
        FAILS.append(name)
        print("FAIL-", name, ("| " + detail[:200]) if detail else "")


def repo_rel(abs_path: str) -> str | None:
    if abs_path.startswith("/srv/1c/"):
        return abs_path[len("/srv/1c/"):]
    for deploy, rel in DEPLOY_PREFIXES:
        if abs_path.startswith(deploy):
            return rel + abs_path[len(deploy):]
    return None


def is_interpreter(path: str) -> bool:
    if "/venv/bin/" in path:
        return True
    return any(path.endswith(suf) for suf in INTERPRETER_SUFFIXES)


def script_paths_from_exec(line: str) -> list[str]:
    val = line.split("=", 1)[1].strip()
    tokens = val.split()
    paths = [t for t in tokens if t.startswith("/")]
    if not paths:
        return []
    # runuser … -- /bin/bash /srv/1c/… — берём последний исполняемый скрипт.
    for p in reversed(paths):
        if is_interpreter(p):
            continue
        if p.endswith((".py", ".sh")) or "/work/" in p or p.startswith("/srv/1c/"):
            return [p]
    # одиночный скрипт без интерпретора (build.sh, pipeline.sh)
    for p in reversed(paths):
        if not is_interpreter(p):
            return [p]
    return []


def iter_unit_templates() -> list[str]:
    patterns = [
        os.path.join(ROOT, "ubuntu", "**", "systemd", "*.service"),
        os.path.join(ROOT, "ubuntu", "**", "systemd", "*.timer"),
    ]
    out: list[str] = []
    for pat in patterns:
        out.extend(glob.glob(pat, recursive=True))
    return sorted(set(out))


def live_index_execstart_ok() -> tuple[bool, str]:
    if not os.path.isfile(LIVE_INDEX_UNIT):
        return False, "missing ubuntu/systemd/1c-serene-index.service"
    text = open(LIVE_INDEX_UNIT, encoding="utf-8").read()
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("ExecStart="):
            continue
        if "build.sh" in stripped:
            return True, stripped
        return False, stripped
    return False, "no ExecStart="


def main() -> int:
    templates = iter_unit_templates()
    check("templates found", len(templates) >= 18, "count=%d" % len(templates))

    check(
        "dead serenedb index unit absent",
        not os.path.exists(DEAD_INDEX_UNIT),
        DEAD_INDEX_UNIT,
    )

    ok, detail = live_index_execstart_ok()
    check(
        "live ubuntu/systemd/1c-serene-index.service ExecStart → build.sh",
        ok,
        detail,
    )

    for unit_path in templates:
        rel_unit = os.path.relpath(unit_path, ROOT)
        text = open(unit_path, encoding="utf-8").read()
        for line in text.splitlines():
            stripped = line.strip()
            if not any(stripped.startswith(k) for k in EXEC_KEYS):
                continue
            for abs_script in script_paths_from_exec(stripped):
                rel = repo_rel(abs_script)
                tag = "%s → %s" % (rel_unit, abs_script)
                if rel is None:
                    # Вне дерева и вне /opt|/srv — внешняя установка (open-webui и т.п.).
                    continue
                full = os.path.join(ROOT, rel)
                check("%s exists" % tag, os.path.isfile(full), rel)
                base = os.path.basename(abs_script)
                check(
                    "%s not withdrawn" % tag,
                    base not in WITHDRAWN_BASENAMES,
                    "withdrawn from contour",
                )

    if FAILS:
        print("FAIL %d/%d" % (len(FAILS), CHECKS))
        return 1
    print("OK %d/%d" % (CHECKS, CHECKS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
