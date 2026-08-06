#!/usr/bin/env python3
"""Генератор комплекта базы пакетного транспорта (AGENT_TZ §2, контракт §3/§10).

На базу создаётся: identity age (private key), токен Bearer, начальный конфиг агента,
фрагмент файла баз приёмника и packet-setup.json для установщика Windows.

Секреты не попадают в git: весь вывод — в --out каталог (умолчание work/packet/kit/<base>,
в .gitignore). Раскладка по /etc — за владельцем (сессии туда не пишут).
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import packet_crypto as C  # noqa: E402

BASE_ID_RE = __import__("re").compile(r"[a-z0-9_-]+")


def fail(msg: str) -> "SystemExit":
    sys.stderr.write(f"packet_kit: {msg}\n")
    return SystemExit(2)


def entities_from_dsn(dsn: str) -> list[str]:
    """Список сущностей из переписи base_profile указанной базы (одним SELECT)."""
    sql = "SELECT entity FROM base_profile WHERE rows > 0 ORDER BY 1;"
    p = subprocess.run(
        ["psql", dsn, "--csv", "-tA", "-c", sql], capture_output=True, timeout=120
    )
    if p.returncode != 0:
        raise fail(f"psql: {p.stderr.decode('utf-8', 'replace').strip()}")
    return [ln.split(",")[0] for ln in p.stdout.decode().splitlines() if ln.strip()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("base_id")
    ap.add_argument("--out", default=None)
    ap.add_argument("--dsn", default=None, help="DSN базы для начального списка сущностей")
    ap.add_argument("--receiver-url", default="https://1c-gate.timpul.ru")
    args = ap.parse_args()

    if not BASE_ID_RE.fullmatch(args.base_id):
        raise fail(f"base_id не по форме [a-z0-9_-]+: {args.base_id!r}")

    out = args.out or os.path.join("work", "packet", "kit", args.base_id)
    os.makedirs(out, exist_ok=True)
    identity = os.path.join(out, "age.key")

    if os.path.exists(identity):
        pubkey = C.recipient_of(identity)  # комплект не затирается (контракт §3)
        print(f"identity уже есть — pubkey взят из неё: {pubkey}")
    else:
        pubkey = C.keygen(identity)
        print(f"identity создан: {identity} (600)")

    token = secrets.token_hex(32)

    entities: list[str] = []
    if args.dsn:
        entities = entities_from_dsn(args.dsn)
        print(f"сущностей из base_profile: {len(entities)}")

    config = {
        "config_version": 1,
        "entities": entities,
        "params": {"page_size": 10000, "tact_seconds": 1200, "chunk_mb": 32},
    }

    setup = {
        "base_id": args.base_id,
        "token": token,
        "recipient_pubkey": pubkey,
        "receiver_url": args.receiver_url,
    }
    with open(os.path.join(out, "packet-setup.json"), "w", encoding="utf-8") as f:
        json.dump(setup, f, ensure_ascii=False, indent=2)

    bases_entry = {args.base_id: {"token": token, "identity": identity, "config": config}}
    with open(os.path.join(out, "bases-entry.json"), "w", encoding="utf-8") as f:
        json.dump(bases_entry, f, ensure_ascii=False, indent=2)

    print(f"комплект: {out}/packet-setup.json (установщику), {out}/bases-entry.json (приёмнику)")
    print("раскладка /etc и перезапуск приёмника — за владельцем")
    return 0


if __name__ == "__main__":
    sys.exit(main())
