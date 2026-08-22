#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Единый протокол замера проб: rid, code_md5, port, q_len, outcome, question.

Строка для отчётов (TSV, одна строка на замер):
  PROBE\\trid=...\\tport=...\\tcode_md5=...\\tq_len=...\\toutcome=...\\tquestion=...

Самопроверка (код verify_journal): q_hash = sha256(raw question); сверка q_len
с колонкой ask_journal после /ask. Несовпадение → exit 1, замер недействителен.

CLI:
  format   — напечатать строку PROBE
  verify   — сверить ask_journal (нужен DSN с SELECT на ask_journal)
  scan-sh  — найти в каталоге ssh bash -s "$..." (баг обрезки вопроса)
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any

PREFIX = "PROBE"
FIELDS = ("rid", "port", "code_md5", "q_len", "outcome", "question")


def q_hash(question: str) -> str:
    return hashlib.sha256((question or "").encode("utf-8")).hexdigest()


def q_len(question: str) -> int:
    return len(question or "")


def new_rid(prefix: str = "probe") -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return "%s-%s-%d" % (prefix, ts, os.getpid())


def code_md5(path: str | None = None, short: bool = False) -> str:
    p = path or os.environ.get(
        "PROBE_CODE_PATH", "/srv/1c/ubuntu/serenedb/serene_ask.py")
    try:
        with open(p, "rb") as fh:
            digest = hashlib.md5(fh.read()).hexdigest()
    except OSError:
        return "?"
    return digest if not short else digest[:8]


def _clean_question(question: str) -> str:
    return (question or "").replace("\t", " ").replace("\n", " ").strip()


def format_line(
    *,
    rid: str,
    port: int | str,
    code_md5_val: str,
    q_len_val: int,
    outcome: str,
    question: str,
) -> str:
    parts = [
        PREFIX,
        "rid=%s" % rid,
        "port=%s" % port,
        "code_md5=%s" % code_md5_val,
        "q_len=%s" % int(q_len_val),
        "outcome=%s" % (outcome or "—"),
        "question=%s" % _clean_question(question),
    ]
    return "\t".join(parts)


def parse_line(line: str) -> dict[str, str]:
    line = (line or "").strip()
    if not line.startswith(PREFIX):
        raise ValueError("not a PROBE line: %r" % (line[:80],))
    out: dict[str, str] = {}
    for chunk in line.split("\t")[1:]:
        if "=" not in chunk:
            continue
        k, v = chunk.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def write_record(path: str, line: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(line.rstrip("\n") + "\n")


def emit(
    *,
    rid: str,
    port: int | str,
    code_md5_val: str,
    question: str,
    outcome: str,
    record_path: str | None = None,
    stream=None,
) -> str:
    line = format_line(
        rid=rid,
        port=port,
        code_md5_val=code_md5_val,
        q_len_val=q_len(question),
        outcome=outcome,
        question=question,
    )
    stream = stream or sys.stderr
    print(line, file=stream)
    if record_path:
        write_record(record_path, line)
    return line


def journal_dsn(explicit: str | None = None) -> str:
    if explicit:
        return explicit
    for key in ("PROBE_JOURNAL_DSN", "ASK_JOURNAL_RW_DSN", "SERENEDB_DSN"):
        val = os.environ.get(key, "").strip()
        if val:
            return val
    port = os.environ.get("PGPORT", "7890")
    db = os.environ.get("PGDATABASE", "postgres")
    return "host=127.0.0.1 port=%s user=postgres dbname=%s" % (port, db)


def _psql_row(dsn: str, sql: str) -> tuple[int, str]:
    env = os.environ.copy()
    env.pop("PGUSER", None)
    env.pop("PGDATABASE", None)
    p = subprocess.run(
        ["psql", dsn, "-tA", "-c", sql],
        capture_output=True,
        text=True,
        env=env,
    )
    out = (p.stdout or "").strip()
    err = (p.stderr or "").strip()
    if p.returncode != 0:
        return p.returncode, err or out or "psql failed"
    return 0, out


def verify_journal(
    question: str,
    *,
    rid: str | None = None,
    dsn: str | None = None,
    wait_sec: float = 0.0,
) -> tuple[bool, str, dict[str, Any]]:
    """Сверка q_len/q_hash в ask_journal. True = замер действителен."""
    expected_len = q_len(question)
    expected_hash = q_hash(question)
    dsn = journal_dsn(dsn)
    if wait_sec > 0:
        import time

        time.sleep(wait_sec)

    esc_hash = expected_hash.replace("'", "''")
    if rid:
        esc_rid = rid.replace("'", "''")
        sql = (
            "SELECT q_len, q_hash, outcome, rid FROM ask_journal "
            "WHERE rid = '%s' ORDER BY id DESC LIMIT 1" % esc_rid
        )
    else:
        sql = (
            "SELECT q_len, q_hash, outcome, rid FROM ask_journal "
            "WHERE q_hash = '%s' ORDER BY id DESC LIMIT 1" % esc_hash
        )

    rc, raw = _psql_row(dsn, sql)
    if rc != 0:
        return False, "journal read failed: %s" % raw[:200], {}

    if not raw:
        return False, "journal row not found (q_hash=%s… rid=%s)" % (
            expected_hash[:12], rid or "—"), {}

    parts = raw.split("|")
    if len(parts) < 4:
        return False, "unexpected journal row: %r" % raw[:120], {}

    got_len_s, got_hash, got_outcome, got_rid = parts[0], parts[1], parts[2], parts[3]
    try:
        got_len = int(got_len_s)
    except ValueError:
        return False, "journal q_len not int: %r" % got_len_s, {}

    meta = {
        "expected_len": expected_len,
        "got_len": got_len,
        "expected_hash": expected_hash,
        "got_hash": got_hash,
        "outcome": got_outcome,
        "rid": got_rid,
    }

    if got_hash != expected_hash:
        return False, "q_hash mismatch (sent %d chars, journal hash other)" % expected_len, meta
    if got_len != expected_len:
        return False, (
            "q_len mismatch: sent=%d journal=%d — probe truncated or wrong question"
            % (expected_len, got_len)
        ), meta
    return True, "journal ok q_len=%d rid=%s outcome=%s" % (
        got_len, got_rid, got_outcome), meta


def scan_shell_bug(root: str) -> list[tuple[str, int, str]]:
    """ssh … bash -s "$VAR" — обрезает многословный вопрос до первого слова."""
    bad: list[tuple[str, int, str]] = []
    pat = re.compile(r"""bash\s+-s\s+["']?\$[A-Za-z_][A-Za-z0-9_]*""")
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in sorted(filenames):
            if not name.endswith(".sh"):
                continue
            path = os.path.join(dirpath, name)
            try:
                lines = open(path, encoding="utf-8").read().splitlines()
            except OSError:
                continue
            for i, line in enumerate(lines, 1):
                if pat.search(line):
                    bad.append((path, i, line.strip()))
    return bad


def _cli_format(argv: list[str]) -> int:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--rid", default=new_rid())
    ap.add_argument("--port", default=os.environ.get("OKNA_ASK_PORT", "8091"))
    ap.add_argument("--code-md5", default=code_md5(short=True))
    ap.add_argument("--outcome", default="—")
    ap.add_argument("--record", default="")
    ap.add_argument("question", nargs="?", default="")
    args = ap.parse_args(argv)
    emit(
        rid=args.rid,
        port=args.port,
        code_md5_val=args.code_md5,
        question=args.question,
        outcome=args.outcome,
        record_path=args.record or None,
    )
    return 0


def _cli_verify(argv: list[str]) -> int:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--rid", default="")
    ap.add_argument("--dsn", default="")
    ap.add_argument("--wait", type=float, default=1.0)
    ap.add_argument("question")
    args = ap.parse_args(argv)
    ok, msg, meta = verify_journal(
        args.question,
        rid=args.rid or None,
        dsn=args.dsn or None,
        wait_sec=args.wait,
    )
    print(msg)
    if meta:
        print(json.dumps(meta, ensure_ascii=False))
    return 0 if ok else 1


def _cli_scan_sh(argv: list[str]) -> int:
    root = argv[0] if argv else os.path.dirname(os.path.abspath(__file__))
    hits = scan_shell_bug(root)
    for path, line_no, text in hits:
        print("%s:%d:%s" % (path, line_no, text))
    return 1 if hits else 0


def main(argv: list[str] | None = None) -> int:
    argv = list(argv or sys.argv[1:])
    if not argv:
        print(__doc__ or "")
        return 2
    cmd, rest = argv[0], argv[1:]
    if cmd == "format":
        return _cli_format(rest)
    if cmd == "verify":
        return _cli_verify(rest)
    if cmd == "scan-sh":
        return _cli_scan_sh(rest)
    print("unknown command: %s" % cmd, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
