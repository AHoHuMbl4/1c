#!/usr/bin/env python3
"""Оффлайн-замок Э7: wiki dump без SELECT→Python→.md (б1).

Без сети и живой базы. Мок psql (образец test_embed_tick_guard / changed_sources).
(а) в wiki_publish.sh нет построчной сборки .md Python'ом / SELECT dump;
(б) wiki_build.sql держит VIEW wiki_pages (тела в движке);
(в) замок падает при возврате к прежней форме (синтетическая порча).
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PUBLISH = ROOT / "wiki_publish.sh"
BUILD_SQL = ROOT / "wiki_build.sql"
BUILD_SH = ROOT / "build.sh"

PASS, FAIL = 0, []


def t(name: str, cond: bool, detail: str = "") -> None:
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + str(detail)[:240]) if detail else "")


def main() -> int:
    pub = PUBLISH.read_text(encoding="utf-8")
    sql = BUILD_SQL.read_text(encoding="utf-8")
    build = BUILD_SH.read_text(encoding="utf-8")

    # --- (а) писатель: нет прежнего dump ---
    t("publish +x", bool(PUBLISH.stat().st_mode & 0o111))
    r = subprocess.run(["bash", "-n", str(PUBLISH)], capture_output=True, text=True)
    t("publish bash -n", r.returncode == 0, r.stderr[:120])

    t("no python3 heredoc dump", "python3" not in pub)
    t("no SELECT page_id body dump",
      "SELECT page_id, body FROM wiki_pages" not in pub)
    t("no RS/FS dump separators",
      "\\x1e" not in pub and "\\x1f" not in pub)
    t("no entities/*.md write",
      "page_id + '.md'" not in pub and 'page_id + ".md"' not in pub)
    t("no purge of stale .md",
      "удалено устаревших" not in pub and "os.remove" not in pub)
    t("no openclaw wiki compile in tact",
      "wiki compile" not in pub)
    t("calls wiki_build.sql", "wiki_build.sql" in pub)
    t("build.sh still calls wiki_publish",
      "./wiki_publish.sh" in build)

    # --- (б) SQL: штатно — VIEW в движке (не файловый I/O) ---
    t("CREATE VIEW wiki_pages",
      "CREATE OR REPLACE VIEW wiki_pages" in sql)
    t("view has page_id and body",
      re.search(r"\bpage_id\b", sql) is not None and
      re.search(r"\bbody\b", sql) is not None)
    # комментарий не врёт «файлов движок не умеет»
    t("comment not claims engine cannot write files",
      "файлов движок не умеет" not in sql)

    # --- мок psql: скрипт зовёт -f wiki_build.sql, не пишет .md ---
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        log = td_path / "psql.log"
        fake = td_path / "psql"
        fake.write_text(
            "#!/bin/bash\n"
            "echo \"$*\" >> '%s'\n"
            "if echo \"$*\" | grep -q current_database; then echo testdb; exit 0; fi\n"
            "if echo \"$*\" | grep -q 'wiki_build.sql'; then exit 0; fi\n"
            "exit 0\n" % log,
            encoding="utf-8",
        )
        fake.chmod(0o755)
        vault = td_path / "vault" / "entities"
        vault.mkdir(parents=True)
        (vault / "Old_Page.md").write_text("stale\n", encoding="utf-8")
        env = os.environ.copy()
        env["PATH"] = f"{td}:{env.get('PATH', '')}"
        env["SERENEDB_DSN"] = "host=127.0.0.1 port=9 user=postgres dbname=testdb"
        env["WIKI_VAULT"] = str(td_path / "vault")
        env["OPENCLAW_USER"] = "nobody"
        r2 = subprocess.run(
            ["bash", str(PUBLISH)],
            text=True, capture_output=True, env=env, cwd=str(ROOT),
        )
        out = (r2.stdout or "") + (r2.stderr or "")
        logged = log.read_text(encoding="utf-8") if log.exists() else ""
        t("mock psql: rc 0", r2.returncode == 0, out[:200])
        t("mock psql: ran wiki_build.sql",
          "wiki_build.sql" in logged, logged[:300])
        t("mock psql: no SELECT dump in args",
          "SELECT page_id" not in logged, logged[:300])
        t("mock: entities/*.md not rewritten",
          (vault / "Old_Page.md").read_text(encoding="utf-8") == "stale\n")
        t("mock: no new .md beside Old_Page",
          list(vault.glob("*.md")) == [vault / "Old_Page.md"])
        t("mock: message mentions Э7 or wiki_pages",
          "wiki_pages" in out or "Э7" in out, out[:200])

    # --- (в) возврат к прежней форме → проверки краснеют ---
    old_form = (
        'psql "$DSN" -tA -c "SELECT page_id, body FROM wiki_pages" > dump\n'
        "python3 - dump entities <<'PY'\n"
        "open(page_id + '.md', 'w').write(body)\n"
        "os.remove(stale)\n"
        "print('вики: записано страниц %d, удалено устаревших %d' % (0, 0))\n"
        "PY\n"
        "openclaw wiki compile\n"
    )
    t("regress: old form has python3", "python3" in old_form)
    t("regress: old form has SELECT dump",
      "SELECT page_id, body FROM wiki_pages" in old_form)
    # те же предикаты, что (а), на порче — обязаны быть False
    t("regress: python3 would fail lock",
      not ("python3" not in old_form))
    t("regress: SELECT dump would fail lock",
      not ("SELECT page_id, body FROM wiki_pages" not in old_form))
    t("regress: entities md write would fail lock",
      not ("page_id + '.md'" not in old_form))

    total = PASS + len(FAIL)
    if FAIL:
        print("FAIL %d/%d" % (len(FAIL), total))
        return 1
    print("OK %d/%d" % (PASS, total))
    return 0


if __name__ == "__main__":
    sys.exit(main())
