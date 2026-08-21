#!/usr/bin/env python3
"""Замок: embed_secrets_base_url_check ловит рассинхрон TEMPORARY SECRET vs EMBED_HOST.

Корень klient-1 (21.08): curl на gpu-erw → 200; ai_embed → 404 HTML (minInterval),
потому что duckdb_secrets().base_url остался на *.thundercompute.net после смены env.

Оффлайн: разбор case-веток через bash -c с подменой psql.
Запуск: python3 test_embed_secret_url_check.py
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BOX = ROOT / "box_tune.sh"
_fail = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global _fail
    if not cond:
        _fail += 1
    print(f"  {'PASS' if cond else 'FAIL ✗'}  {name}   {detail}")


def run_check(secret_rows: str, embed_host: str) -> tuple[int, str]:
    """secret_rows: TSV name\\tsecret_string lines."""
    with tempfile.TemporaryDirectory() as td:
        fake_psql = Path(td) / "psql"
        out = Path(td) / "rows.tsv"
        out.write_text(secret_rows, encoding="utf-8")
        fake_psql.write_text(
            "#!/bin/bash\n"
            f"cat '{out}'\n",
            encoding="utf-8",
        )
        fake_psql.chmod(0o755)
        env = os.environ.copy()
        env["PATH"] = f"{td}:{env.get('PATH', '')}"
        env["SERENEDB_DSN"] = "host=127.0.0.1 port=7890 user=postgres dbname=postgres"
        env["EMBED_HOST"] = embed_host
        env.pop("EMBED_HOSTS", None)
        script = f"set -euo pipefail; . '{BOX}'; embed_secrets_base_url_check"
        r = subprocess.run(
            ["bash", "-c", script],
            text=True,
            capture_output=True,
            env=env,
        )
        return r.returncode, (r.stderr or "") + (r.stdout or "")


def main() -> int:
    print("== embed_secrets_base_url_check ==")
    host = "http://embed.example:8000"
    ok_row = (
        "emb_postgres_0\t"
        f"name=emb_postgres_0;type=openai;base_url={host};"
        "embeddings_path=/v1/embeddings\n"
    )
    bad_row = (
        "emb_postgres_0\t"
        "name=emb_postgres_0;type=openai;base_url=https://old-embed.example;"
        "embeddings_path=/v1/embeddings\n"
    )
    path_row = (
        "emb_postgres_0\t"
        "name=emb_postgres_0;type=openai;"
        f"base_url={host}/v1/embeddings;embeddings_path=/v1/embeddings\n"
    )

    rc, err = run_check(ok_row, host)
    check("совпадение base_url → 0", rc == 0, err[:120])

    rc, err = run_check(bad_row, host)
    check("чужой host ≠ EMBED_HOST → fail", rc != 0, err[:200])
    check("сообщает рассинхрон", "не из EMBED_HOST" in err or "TEMPORARY SECRET" in err)

    rc, err = run_check(path_row, host)
    check("путь в base_url → fail", rc != 0, err[:200])
    check("называет double-path", "double-path" in err or "содержит путь" in err)

    print(f"\nитог: {'OK' if _fail == 0 else f'{_fail} FAIL'}")
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(main())
