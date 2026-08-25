#!/usr/bin/env python3
"""Оффлайн-замок защиты такта: большой остаток → bulk; малый проходит; обход работает.

Без сети и живой базы: подмена psql, зов embed_tick_guard_check.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
GUARD = ROOT / "embed_tick_guard.sh"
MISSING = ROOT / "embed_missing.sh"
PASS, FAIL = 0, []


def t(name: str, cond: bool, detail: str = "") -> None:
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + detail[:240]) if detail else "")


def run_guard(psql_reply_logic: str, env_extra: dict | None = None) -> tuple[int, str]:
    """psql_reply_logic — тело функции, видит $ARGS со всеми аргументами."""
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        fake_psql = td_path / "psql"
        fake_psql.write_text(
            "#!/bin/bash\nARGS=\"$*\"\n" + psql_reply_logic + "\n",
            encoding="utf-8",
        )
        fake_psql.chmod(0o755)
        env = os.environ.copy()
        env["PATH"] = f"{td}:{env.get('PATH', '')}"
        env["SERENEDB_DSN"] = "host=127.0.0.1 port=7890 user=postgres dbname=postgres"
        env.pop("EMBED_ALLOW_LARGE_TICK", None)
        if env_extra:
            env.update(env_extra)
        else:
            env["EMBED_TICK_MAX_REMAINING"] = "100000"
        env.setdefault("EMBED_TICK_MAX_REMAINING", "100000")
        script = (
            f"set -uo pipefail; . '{GUARD}'; "
            f"embed_tick_guard_check search_corpus emb_testdb_search_corpus; "
            f"rc=$?; echo GUARD_RC=$rc; exit $rc"
        )
        r = subprocess.run(
            ["bash", "-c", script],
            text=True,
            capture_output=True,
            env=env,
        )
        return r.returncode, (r.stderr or "") + (r.stdout or "")


def main() -> int:
    t("guard +x", bool(GUARD.stat().st_mode & 0o111))
    r = subprocess.run(["bash", "-n", str(GUARD)], capture_output=True, text=True)
    t("guard bash -n", r.returncode == 0, r.stderr[:120])

    large_todo = """
if echo "$ARGS" | grep -q reltuples; then echo 7858166; exit 0; fi
echo 0
"""
    rc, out = run_guard(large_todo)
    t("большой остаток → rc 2", rc == 2, f"rc={rc} {out[:200]}")
    t("большой остаток → называет embed_bulk",
      "embed_bulk" in out, out[:300])
    t("большой остаток → порог в сообщении",
      "100000" in out or "порог" in out, out[:300])

    small_todo = """
if echo "$ARGS" | grep -q reltuples; then echo 1200; exit 0; fi
echo 0
"""
    rc, out = run_guard(small_todo)
    t("малый остаток → rc 0", rc == 0, f"rc={rc} {out[:200]}")
    t("малый остаток → слово такт", "такт" in out, out[:200])

    rc, out = run_guard(large_todo, {"EMBED_ALLOW_LARGE_TICK": "1"})
    t("обход EMBED_ALLOW_LARGE_TICK → rc 0", rc == 0, f"rc={rc} {out[:200]}")
    t("обход → сообщение об обходе", "обход" in out or "ALLOW_LARGE" in out, out[:200])

    no_todo_large = """
if echo "$ARGS" | grep -q reltuples; then echo NULL; exit 0; fi
if echo "$ARGS" | grep -q count; then echo 500001; exit 0; fi
echo 0
"""
    rc, out = run_guard(no_todo_large, {"EMBED_TICK_MAX_REMAINING": "100000"})
    t("без todo, probe > порога → rc 2", rc == 2, f"rc={rc} {out[:200]}")

    no_todo_small = """
if echo "$ARGS" | grep -q reltuples; then echo NULL; exit 0; fi
if echo "$ARGS" | grep -q count; then echo 50; exit 0; fi
echo 0
"""
    rc, out = run_guard(no_todo_small)
    t("без todo, probe мал → rc 0", rc == 0, f"rc={rc} {out[:200]}")

    miss = MISSING.read_text(encoding="utf-8")
    all_sh = (ROOT / "embed_all.sh").read_text(encoding="utf-8")
    t("embed_missing зовёт guard",
      "embed_tick_guard" in miss and "embed_tick_guard_check" in miss)
    t("embed_missing guard до left()/счёта",
      miss.find("embed_tick_guard_check") < miss.find("n=$(left)"))
    t("embed_all зовёт guard на corpus",
      "embed_tick_guard_check" in all_sh)
    t("embed_all exit 2 на большом остатке",
      "exit 2" in all_sh)

    print("\nитог: %d ok, %d fail" % (PASS, len(FAIL)))
    if FAIL:
        print("FAIL:", ", ".join(FAIL))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
