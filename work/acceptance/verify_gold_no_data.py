#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка эталонов no_data в ab-gold-okna.tsv / ab-probe-okna.tsv по данным базы.

Для каждой строки с ожиданием no_data (режим kind, не период продаж):
  · SQL-доказательство: balance_registers / search_balance_map / строки корпуса
  · если данные есть — дефект эталона (консервация), gold не правится молча

Запуск:
  python3 work/acceptance/verify_gold_no_data.py --offline
  python3 work/acceptance/verify_gold_no_data.py --dsn 'host=… port=7890 …'
  python3 work/acceptance/verify_gold_no_data.py --host okna   # через ssh оркестратора

Выход: markdown-таблица на stdout; код 1 если есть дефекты эталона без разбора.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SERENEDB = os.path.join(ROOT, "ubuntu", "serenedb")
if SERENEDB not in sys.path:
    sys.path.insert(0, SERENEDB)

import ab_scorer as AB  # noqa: E402


def load_rows(path: str) -> list[dict]:
    rows = []
    for row in AB.load_gold(path):
        want = ""
        if row.get("sql"):
            want = AB.truth(row["sql"], empty_as_zero=(row["mode"] in ("digits", "kind")))
        rows.append({**row, "want": want})
    return rows


def no_data_candidates(rows: list[dict]) -> list[dict]:
    out = []
    for row in rows:
        if row.get("mode") != "kind":
            continue
        expected = AB.kind_expected_for_kind_mode(
            row.get("sql") or "", row.get("want"), question=row.get("q") or "")
        if expected != "no_data":
            continue
        out.append({**row, "expected_kind": expected})
    return out


def psql_ta(dsn: str, sql: str) -> str:
    p = subprocess.run(
        ["psql", dsn, "-tA", "-c", sql],
        capture_output=True,
        text=True,
        env={k: v for k, v in os.environ.items() if k != "PGUSER"},
    )
    if p.returncode:
        raise RuntimeError((p.stderr or p.stdout or "psql error")[:300])
    return (p.stdout or "").strip()


def stock_proof(dsn: str) -> dict:
    """Доказательства наличия складского контура в базе."""
    proof: dict = {"balance_registers": "", "balance_map_rows": None, "register_counts": {}}
    try:
        proof["balance_registers"] = psql_ta(
            dsn,
            "SELECT coalesce(v,'') FROM search_meta WHERE k='balance_registers' LIMIT 1",
        )
    except Exception as e:  # noqa: BLE001
        proof["balance_registers_error"] = str(e)[:120]

    try:
        proof["balance_map_rows"] = int(psql_ta(
            dsn, "SELECT count(*) FROM search_balance_map"))
    except Exception:
        proof["balance_map_rows"] = None

    regs: list[str] = []
    raw = proof.get("balance_registers") or ""
    if raw.startswith("["):
        try:
            regs = json.loads(raw)
        except json.JSONDecodeError:
            regs = re.findall(r"accumulationregister_[a-z0-9_]+", raw.lower())
    else:
        regs = re.findall(r"accumulationregister_[a-z0-9_]+", raw.lower())

    for reg in regs[:12]:
        try:
            n = int(psql_ta(
                dsn,
                "SELECT count(*) FROM search_corpus WHERE src_table='%s'" % reg.replace("'", "''")))
        except Exception as e:  # noqa: BLE001
            n = -1
            proof.setdefault("errors", {})[reg] = str(e)[:80]
        proof["register_counts"][reg] = n

    proof["has_stock_data"] = bool(
        (proof.get("balance_map_rows") or 0) > 0
        or any(v > 0 for v in proof.get("register_counts", {}).values())
        or (raw and raw not in ("", "[]", "null"))
    )
    return proof


def classify_row(row: dict, proof: dict | None) -> tuple[str, str]:
    q = (row.get("q") or "").lower()
    is_stock = any(w in q for w in ("склад", "остат", "петел", "товар на"))
    if proof is None:
        return "offline", "ожидается no_data; live SQL не запускался"
    if not is_stock:
        return "unchecked", "не складской no_data — проверка balance_registers не применима"
    if proof.get("has_stock_data"):
        return "gold_defect", (
            "данные склада есть: balance_map=%s registers=%s"
            % (proof.get("balance_map_rows"), proof.get("register_counts"))
        )
    return "ok", "balance_registers/search_balance_map пусты — no_data обоснован"


def remote_dsn(host: str) -> str:
    key = os.path.expanduser("~/.ssh/id_ed25519_deploy")
    ssh_base = ["ssh", "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes", "-i", key]
    if host == "okna":
        target = "root@167.233.249.110"
    elif host == "klient-1":
        target = "root@89.23.101.22"
        inner = (
            "ssh -o StrictHostKeyChecking=no root@10.1.1.7 "
            "'source /etc/1c-mcp-reports.env 2>/dev/null; "
            "echo host=127.0.0.1 port=7890 user=postgres dbname=postgres'"
        )
        p = subprocess.run(ssh_base + [target, inner], capture_output=True, text=True)
        if p.returncode:
            raise RuntimeError(p.stderr or p.stdout)
        return p.stdout.strip()
    elif host == "dev":
        return os.environ.get(
            "PROBE_JOURNAL_DSN",
            "host=127.0.0.1 port=7890 user=postgres dbname=postgres",
        )
    else:
        raise ValueError("unknown host: %s" % host)

    cmd = (
        "bash -lc 'set -a; [ -r /etc/1c-mcp-reports.env ] && . /etc/1c-mcp-reports.env; "
        "set +a; echo host=127.0.0.1 port=7890 user=postgres dbname=postgres'"
    )
    p = subprocess.run(ssh_base + [target, cmd], capture_output=True, text=True)
    if p.returncode:
        raise RuntimeError(p.stderr or p.stdout)
    return p.stdout.strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", action="append", default=[], help="tsv path (repeatable)")
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--dsn", default="")
    ap.add_argument("--host", default="", choices=["", "okna", "klient-1", "dev"])
    args = ap.parse_args()

    gold_paths = args.gold or [
        os.path.join(SERENEDB, "ab-gold-okna.tsv"),
        os.path.join(SERENEDB, "ab-probe-okna.tsv"),
    ]

    all_rows: list[tuple[str, dict]] = []
    for gp in gold_paths:
        if not os.path.isfile(gp):
            sys.stderr.write("skip missing gold: %s\n" % gp)
            continue
        for row in no_data_candidates(load_rows(gp)):
            all_rows.append((gp, row))

    dsn = args.dsn.strip()
    if not args.offline and not dsn and args.host:
        dsn = remote_dsn(args.host)
    proof = None if args.offline or not dsn else stock_proof(dsn)

    defects = 0
    print("| gold | question | verdict | detail |")
    print("|---|---|---|---|")
    for gp, row in all_rows:
        verdict, detail = classify_row(row, proof)
        if verdict == "gold_defect":
            defects += 1
        q = (row.get("q") or "").replace("|", "\\|")[:80]
        base = os.path.basename(gp)
        print("| %s | %s | %s | %s |" % (base, q, verdict, detail.replace("|", "\\|")[:200]))

    if args.offline:
        print("\n(offline: live SQL не запускался; для доказательства — --host okna|klient-1|dev)")
    elif proof:
        print("\n```json")
        print(json.dumps(proof, ensure_ascii=False, indent=2))
        print("```")

    if defects:
        sys.stderr.write(
            "\n🔴 %d строк no_data — дефект эталона (данные есть). "
            "Менять gold только с разбором каждой строки.\n" % defects
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
