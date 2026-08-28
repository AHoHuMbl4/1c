#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Пул сущностей для reask: журнал (alias_candidates) + устаревшие из основного словаря.

Только чтение базы через psql; в основной словарь не пишет.
Выход: JSON-массив строк src_table для wiki_alias_reask_select_entity_batch.sql.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PIPE = ROOT / "work" / "pipeline"
sys.path.insert(0, str(PIPE))

import alias_candidates as AC  # noqa: E402


def psql_scalar(dsn: str, sql: str) -> str:
    env = dict(os.environ)
    for k in ("PGUSER", "PGDATABASE", "PGPASSWORD"):
        env.pop(k, None)
    p = subprocess.run(
        ["psql", dsn, "-v", "ON_ERROR_STOP=1", "-tA", "-c", sql],
        text=True,
        capture_output=True,
        env=env,
    )
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout or "psql error")[:400])
    return (p.stdout or "").strip()


def stale_entities(dsn: str, alias_table: str, stale_days: int) -> list[str]:
    sql = (
        "SELECT f.src_table FROM wiki_entity_facts f "
        "JOIN %s a ON a.src_table = f.src_table "
        "WHERE f.cls <> 'service' AND coalesce(a.aliases,'') <> '' "
        "AND a.seen_at < now() - INTERVAL '%d days' "
        "ORDER BY a.seen_at, f.src_table" % (alias_table, stale_days)
    )
    if AC.WRITE_SQL_RE.search(sql):
        raise RuntimeError("alias_reask_pool: mutating SQL blocked")
    env = dict(os.environ)
    for k in ("PGUSER", "PGDATABASE", "PGPASSWORD"):
        env.pop(k, None)
    p = subprocess.run(
        ["psql", dsn, "-v", "ON_ERROR_STOP=1", "-tA", "-c", sql],
        text=True,
        capture_output=True,
        env=env,
    )
    if p.returncode != 0:
        return []
    return [ln.strip() for ln in p.stdout.splitlines() if ln.strip()]


def journal_entities(dsn: str, since: str, top: int) -> list[str]:
    journal = AC.load_journal_db(dsn, since)
    freq = AC.top_terms(journal, top)
    terms = {t.casefold() for t, _ in freq}
    raw = AC.candidates_from_journal(journal, terms)
    out: list[str] = []
    seen: set[str] = set()
    for _term, link, _src in raw:
        if link and link not in seen:
            seen.add(link)
            out.append(link)
    return out


def build_pool(
    dsn: str,
    alias_table: str,
    stale_days: int,
    since: str,
    top: int,
    journal_file: str | None,
) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    if journal_file:
        journal = AC.load_journal_file(journal_file)
        freq = AC.top_terms(journal, top)
        terms = {t.casefold() for t, _ in freq}
        for _t, link, _s in AC.candidates_from_journal(journal, terms):
            if link and link not in seen:
                seen.add(link)
                ordered.append(link)
    else:
        for link in journal_entities(dsn, since, top):
            if link not in seen:
                seen.add(link)
                ordered.append(link)
    for link in stale_entities(dsn, alias_table, stale_days):
        if link not in seen:
            seen.add(link)
            ordered.append(link)
    return ordered


def write_pool(path: str, entities: list[str]) -> None:
    rows = [{"t": e} for e in entities]
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(rows, fh, ensure_ascii=False)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Пул сущностей reask (С5-пайплайн)")
    p.add_argument("--out", required=True, help="JSON для read_json pool_path")
    p.add_argument("--dsn", default="", help="DSN postgres")
    p.add_argument("--alias-table", default="search_entity_alias")
    p.add_argument("--stale-days", type=int, default=30)
    p.add_argument("--since", default="7 days")
    p.add_argument("--top", type=int, default=10)
    p.add_argument("--journal-file", help="офлайн журнал вместо psql")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    dsn = args.dsn or AC.default_dsn()
    pool = build_pool(
        dsn,
        args.alias_table,
        args.stale_days,
        args.since,
        args.top,
        args.journal_file,
    )
    write_pool(args.out, pool)
    sys.stderr.write(
        "alias_reask_pool: entities=%d → %s\n" % (len(pool), args.out)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
