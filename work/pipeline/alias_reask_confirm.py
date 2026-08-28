#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Сверка reask → основной словарь: только подтверждённые связи.

Подтверждение: confirm_count >= min_confirm ИЛИ gold check_result == pass.
Неподтверждённые — только journal_path (прецедент ask_choice_memory).
"""
from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PIPE = ROOT / "work" / "pipeline"
SERENED = ROOT / "ubuntu" / "serenedb"
sys.path.insert(0, str(PIPE))
sys.path.insert(0, str(SERENED))

import alias_candidates as AC  # noqa: E402
import wiki_alias_parse as wap  # noqa: E402


def psql_rows(dsn: str, sql: str) -> list[list[str]]:
    if AC.WRITE_SQL_RE.search(sql):
        raise RuntimeError("alias_reask_confirm: mutating SQL in read path")
    env = dict(os.environ)
    for k in ("PGUSER", "PGDATABASE", "PGPASSWORD"):
        env.pop(k, None)
    p = subprocess.run(
        ["psql", dsn, "-v", "ON_ERROR_STOP=1", "-tA", "-F", "\x1f", "-c", sql],
        text=True,
        capture_output=True,
        env=env,
    )
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout or "psql error")[:400])
    rows = []
    for ln in p.stdout.splitlines():
        if ln.strip():
            rows.append(ln.split("\x1f"))
    return rows


def load_main_aliases(
    dsn: str, alias_table: str, srcs: set[str] | None = None
) -> dict[str, set[str]]:
    """Токены основного словаря ТОЛЬКО по сущностям reask-пула (снайпер 28.08:
    вся таблица наружу росла бы с базой; сверка нужна лишь по пулу)."""
    if srcs:
        in_list = ", ".join("'%s'" % s.replace("'", "''") for s in sorted(srcs))
        where = " AND src_table IN (%s)" % in_list
    else:
        where = ""
    sql = (
        "SELECT src_table, aliases FROM %s WHERE coalesce(aliases,'') <> ''%s"
        % (alias_table, where)
    )
    out: dict[str, set[str]] = {}
    for r in psql_rows(dsn, sql):
        if len(r) < 2:
            continue
        tokens = {t.casefold() for t in wap._alias_tokens(r[1])}
        out[r[0]] = tokens
    return out


def load_confirm_counts(
    dsn: str, confirm_table: str, srcs: set[str] | None = None
) -> dict[tuple[str, str], dict]:
    if srcs:
        in_list = ", ".join("'%s'" % s.replace("'", "''") for s in sorted(srcs))
        where = " WHERE src_table IN (%s)" % in_list
    else:
        where = ""
    sql = (
        "SELECT src_table, alias_token, confirm_count, gold_ok "
        "FROM %s%s" % (confirm_table, where)
    )
    out: dict[tuple[str, str], dict] = {}
    for r in psql_rows(dsn, sql):
        if len(r) < 4:
            continue
        key = (r[0], r[1].casefold())
        out[key] = {
            "count": int(r[2] or 0),
            "gold_ok": str(r[3]).lower() in ("1", "t", "true"),
        }
    return out


def parse_reask_rows(rows_path: str) -> list[dict]:
    try:
        data = json.loads(open(rows_path, encoding="utf-8").read())
    except (OSError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    return [r for r in data if isinstance(r, dict)]


def new_tokens_for_row(
    row: dict, main: dict[str, set[str]]
) -> list[tuple[str, str]]:
    src = (row.get("src_table") or "").strip()
    if not src:
        return []
    existing = main.get(src, set())
    found = []
    for tok in wap._alias_tokens(row.get("aliases")):
        cf = tok.casefold()
        if cf and cf not in existing:
            found.append((src, tok))
    return found


def gold_passes(
    term: str,
    link: str,
    gold_file: str,
    dsn: str,
    alias_table: str,
    alias_index: str,
    sample: int,
    seed: int,
) -> bool:
    if not gold_file:
        return False  # gold не задан — путь только через min-confirm
    gold_rows = AC.scorer.load_gold(gold_file)
    cand = AC.Candidate(term, link, "reask", journal_freq=0)
    AC.validate_candidate(
        cand,
        gold_rows,
        sample,
        dsn,
        alias_table,
        alias_index,
        False,
        random.Random(seed),
    )
    return cand.check_result == "pass"


def bump_confirm_sql(
    confirm_table: str, src: str, token: str, gold_ok: bool
) -> str:
    esc_s = src.replace("'", "''")
    esc_t = token.replace("'", "''")
    g = "true" if gold_ok else "false"
    return (
        "MERGE INTO %s t USING (SELECT '%s' AS src_table, '%s' AS alias_token) n "
        "ON t.src_table = n.src_table AND t.alias_token = n.alias_token "
        "WHEN MATCHED THEN UPDATE SET confirm_count = t.confirm_count + 1, "
        "gold_ok = t.gold_ok OR %s, last_seen = now() "
        "WHEN NOT MATCHED THEN INSERT (src_table, alias_token, confirm_count, "
        "gold_ok, first_seen, last_seen) "
        "VALUES (n.src_table, n.alias_token, 1, %s, now(), now());"
        % (confirm_table, esc_s, esc_t, g, g)
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Сверка reask (С5-пайплайн)")
    p.add_argument("--rows-path", required=True, help="rows.json от wiki_alias_parse")
    p.add_argument("--confirmed-out", required=True, help="JSON для merge_confirmed")
    p.add_argument("--journal-out", required=True, help="JSON для reask_journal")
    p.add_argument("--dsn", default="")
    p.add_argument("--alias-table", default="search_entity_alias")
    p.add_argument("--confirm-table", required=True)
    p.add_argument("--min-confirm", type=int, default=2)
    p.add_argument(
        "--gold-file", default=os.environ.get("WIKI_ALIAS_GOLD_FILE", ""),
        help="TSV подмножества gold для проверки кандидата; пусто — только "
             "подтверждения моделью (снайпер 28.08: дефолт с именем базы "
             "был хардкодом okna)",
    )
    p.add_argument("--gold-sample", type=int, default=7)
    p.add_argument("--alias-index", default="alias_idx")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--apply", action="store_true", help="писать confirm_table в БД")
    p.add_argument("--dry-run", action="store_true", help="не трогать confirm_table")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    dsn = args.dsn or AC.default_dsn()
    rows = parse_reask_rows(args.rows_path)
    pool_srcs = {(r.get("src_table") or "").strip() for r in rows}
    pool_srcs.discard("")
    main_aliases = load_main_aliases(dsn, args.alias_table, pool_srcs)
    prior = (
        load_confirm_counts(dsn, args.confirm_table, pool_srcs)
        if not args.dry_run else {}
    )

    confirmed_rows: list[dict] = []
    journal_rows: list[dict] = []
    merge_sql: list[str] = []

    for row in rows:
        for src, token in new_tokens_for_row(row, main_aliases):
            key = (src, token.casefold())
            gold_ok = gold_passes(
                token,
                src,
                args.gold_file,
                dsn,
                args.alias_table,
                args.alias_index,
                args.gold_sample,
                args.seed,
            )
            prev = prior.get(key, {"count": 0, "gold_ok": False})
            new_count = prev["count"] + 1
            merged_gold = prev["gold_ok"] or gold_ok

            if args.apply and not args.dry_run:
                merge_sql.append(
                    bump_confirm_sql(args.confirm_table, src, token, gold_ok)
                )

            if merged_gold or new_count >= args.min_confirm:
                confirmed_rows.append({"src_table": src, "aliases": token})
            else:
                journal_rows.append(
                    {
                        "src_table": src,
                        "alias_token": token,
                        "reason": "unconfirmed",
                        "detail": "count=%d need=%d gold=%s"
                        % (new_count, args.min_confirm, gold_ok),
                    }
                )

    with open(args.confirmed_out, "w", encoding="utf-8") as fh:
        json.dump(confirmed_rows, fh, ensure_ascii=False)
    with open(args.journal_out, "w", encoding="utf-8") as fh:
        json.dump(journal_rows, fh, ensure_ascii=False)

    if merge_sql and args.apply and not args.dry_run:
        env = dict(os.environ)
        for k in ("PGUSER", "PGDATABASE", "PGPASSWORD"):
            env.pop(k, None)
        # один процесс psql на весь пакет (снайпер 28.08: цикл процессов —
        # п. 20), стейтменты пачкой через stdin
        subprocess.run(
            ["psql", dsn, "-v", "ON_ERROR_STOP=1"],
            input="\n".join(merge_sql),
            text=True,
            check=True,
            env=env,
        )

    sys.stderr.write(
        "alias_reask_confirm: confirmed=%d journal=%d dry=%s\n"
        % (len(confirmed_rows), len(journal_rows), args.dry_run)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
