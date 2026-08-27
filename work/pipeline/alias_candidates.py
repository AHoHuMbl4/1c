#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Прибор кандидатов алиасов (С5): журнал → термы → кандидаты → проверка на gold-подмножестве.

🔴 Не автопополнение словаря. Журнал — датчик; в ``search_entity_alias`` прибор
ничего не пишет (прецедент ``ask_choice_memory``).

Поток:
  1. Читает ``ask_journal`` + ``ask_journal_text`` (исходы clarify/no_data).
  2. Отбирает топ термов из текстов вопросов.
  3. Предлагает связи терм→сущность (журнал/atoms, существующий словарь, подпись
     в ``wiki_entity_facts``; при ``--apply`` — штатный infer как ``wiki_alias.sh``).
  4. Каждый кандидат проверяется на подмножестве рабочего gold (умолчание
     ``ab-probe-okna.tsv``, не полный ``ab-gold-okna.tsv``).
  5. Пишет ``candidates.tsv`` для ручной проверки.

База — только чтение через ``psql`` (как ``ask_journal_label.py`` / ``ab_scorer.py``).

Пример:
  python3 work/pipeline/alias_candidates.py --since '3 days' --top 5 --sample 7 \\
    --out /tmp/candidates.tsv
  python3 work/pipeline/alias_candidates.py --apply --since '7 days'  # + infer модели
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import subprocess
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[2]
SERENED = ROOT / "ubuntu" / "serenedb"
sys.path.insert(0, str(SERENED))

import ab_scorer as scorer  # noqa: E402
import wiki_alias_parse as wap  # noqa: E402

# Исходы журнала = kind ответа (serene_ask._ask_journal_write → outcome).
JOURNAL_OUTCOMES = ("clarify", "no_data")
TERM_RE = re.compile(r"[а-ёa-z]{4,}", re.I)
SRC_TABLE_RE = re.compile(r"src_table\s*=\s*'([^']+)'", re.I)
WRITE_SQL_RE = re.compile(
    r"\b(INSERT|UPDATE|DELETE|MERGE|DROP|CREATE\s+TABLE|VACUUM\s*\()\b", re.I
)

WIKI_PROMPT_HEAD = (
    "JSON only, no prose, no code fences. Below are record types of one database, "
    "shown together because they are CLOSE IN MEANING. For each, in the SAME language "
    "as its title: aliases — everyday words a person uses for this kind of record "
    "(including the title). Schema: "
    "{\"items\":[{\"entity\":\"...\",\"aliases\":[\"...\"]}]}. Input: "
)


@dataclass
class JournalRow:
    row_id: int
    ts: str
    outcome: str
    q_text: str
    atoms: list | dict | None = None
    clarify_options: list | None = None


@dataclass
class Candidate:
    term: str
    link: str
    source: str
    journal_freq: int = 0
    gold_sample_n: int = 0
    gold_pass: int = 0
    gold_fail: int = 0
    check_result: str = "skip"
    detail: str = ""


def load_env(path: str) -> None:
    if not os.path.isfile(path):
        return
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def default_dsn() -> str:
    load_env("/etc/1c-mcp-reports.env")
    load_env("/etc/1c-serene-ask-postgres.env")
    return os.environ.get(
        "SERENEDB_DSN",
        os.environ.get(
            "ALIAS_CANDIDATES_DSN",
            "host=127.0.0.1 port=7890 user=postgres dbname=okna",
        ),
    )


def psql_rows(dsn: str, sql: str, field_sep: str = "\x1f") -> list[list[str]]:
    """Read-only psql; падает на write-SQL (защита dry-run)."""
    if WRITE_SQL_RE.search(sql):
        raise RuntimeError("alias_candidates: mutating SQL not allowed")
    env = dict(os.environ)
    for k in ("PGUSER", "PGDATABASE", "PGPASSWORD"):
        env.pop(k, None)
    p = subprocess.run(
        ["psql", dsn, "-v", "ON_ERROR_STOP=1", "-tA", "-F", field_sep, "-c", sql],
        text=True,
        capture_output=True,
        env=env,
    )
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout or "psql error")[:400])
    rows = []
    for ln in p.stdout.splitlines():
        if not ln.strip():
            continue
        rows.append(ln.split(field_sep))
    return rows


def normalize_question(q: str) -> str:
    s = (q or "").lower().replace("ё", "е")
    s = re.sub(r"[^\w\s]", " ", s, flags=re.UNICODE)
    return re.sub(r"\s+", " ", s).strip()


def tokenize_terms(text: str) -> list[str]:
    return [m.group(0).casefold() for m in TERM_RE.finditer(text or "")]


def parse_json_field(raw: str | None):
    if not raw or raw in ("null", "NULL"):
        return None
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return None


def load_journal_file(path: str) -> list[JournalRow]:
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) < 4:
                continue
            rid, ts, outcome, q_text = parts[0], parts[1], parts[2], parts[3]
            atoms = parse_json_field(parts[4] if len(parts) > 4 else None)
            clarify = parse_json_field(parts[5] if len(parts) > 5 else None)
            rows.append(
                JournalRow(
                    int(rid),
                    ts,
                    outcome.strip(),
                    q_text,
                    atoms=atoms,
                    clarify_options=clarify if isinstance(clarify, list) else None,
                )
            )
    return rows


def load_journal_db(dsn: str, since: str) -> list[JournalRow]:
    since_sql = since.strip()
    if re.match(r"^\d+\s+(day|days|hour|hours|week|weeks)", since_sql, re.I):
        ts_filter = "j.ts >= now() - INTERVAL '%s'" % since_sql.replace("'", "''")
    else:
        ts_filter = "j.ts >= '%s'" % since_sql.replace("'", "''")
    sql = (
        "SELECT j.id, coalesce(j.ts::text, ''), j.outcome, t.q_text, "
        "coalesce(j.atoms::text, ''), coalesce(j.clarify_options::text, '') "
        "FROM ask_journal j "
        "JOIN ask_journal_text t ON t.id = j.id "
        "WHERE j.outcome IN ('clarify', 'no_data') AND %s "
        "ORDER BY j.ts DESC" % ts_filter
    )
    out = []
    for r in psql_rows(dsn, sql):
        if len(r) < 4:
            continue
        out.append(
            JournalRow(
                int(r[0]),
                r[1],
                r[2],
                r[3],
                atoms=parse_json_field(r[4] if len(r) > 4 else None),
                clarify_options=parse_json_field(r[5]) if len(r) > 5 else None,
            )
        )
    return out


def top_terms(rows: Iterable[JournalRow], top_n: int) -> list[tuple[str, int]]:
    ctr: Counter[str] = Counter()
    for row in rows:
        if row.outcome not in JOURNAL_OUTCOMES:
            continue
        for tok in tokenize_terms(row.q_text):
            ctr[tok] += 1
    return ctr.most_common(top_n)


def _dig_src(obj) -> str | None:
    if isinstance(obj, dict):
        for k in ("src", "src_table", "entity", "focus"):
            v = obj.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
        for v in obj.values():
            s = _dig_src(v)
            if s:
                return s
    elif isinstance(obj, list):
        for it in obj:
            s = _dig_src(it)
            if s:
                return s
    return None


def candidates_from_journal(
    rows: Iterable[JournalRow], terms: set[str]
) -> list[tuple[str, str, str]]:
    """term, src_table, source."""
    out: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str]] = set()
    term_set = {t.casefold() for t in terms}
    for row in rows:
        q_terms = set(tokenize_terms(row.q_text))
        hit = q_terms & term_set
        if not hit:
            continue
        for src in filter(None, [_dig_src(row.atoms), _dig_src(row.clarify_options)]):
            for t in hit:
                key = (t, src)
                if key not in seen:
                    seen.add(key)
                    out.append((t, src, "journal_atoms"))
        for opt in row.clarify_options or []:
            src = _dig_src(opt)
            if not src:
                continue
            for t in hit:
                key = (t, src)
                if key not in seen:
                    seen.add(key)
                    out.append((t, src, "journal_clarify"))
    return out


def candidates_from_alias_table(
    dsn: str, terms: set[str], alias_table: str = "search_entity_alias"
) -> list[tuple[str, str, str]]:
    if not terms:
        return []
    term_list = ", ".join("'%s'" % t.replace("'", "''") for t in sorted(terms))
    sql = (
        "SELECT src_table, trim(lower(x.a)) AS alias "
        "FROM %s, unnest(str_split(aliases, ',')) AS x(a) "
        "WHERE trim(x.a) <> '' AND trim(lower(x.a)) IN (%s)" % (alias_table, term_list)
    )
    out = []
    seen: set[tuple[str, str]] = set()
    for r in psql_rows(dsn, sql):
        if len(r) < 2:
            continue
        link, term = r[0], r[1]
        key = (term, link)
        if key not in seen:
            seen.add(key)
            out.append((term, link, "existing_alias"))
    return out


def candidates_from_labels(
    dsn: str, terms: set[str]
) -> list[tuple[str, str, str]]:
    out = []
    seen: set[tuple[str, str]] = set()
    for term in sorted(terms):
        esc = term.replace("'", "''")
        sql = (
            "SELECT src_table FROM wiki_entity_facts "
            "WHERE cls <> 'service' AND lower(label) LIKE '%%%s%%' "
            "ORDER BY src_table LIMIT 5" % esc
        )
        for r in psql_rows(dsn, sql):
            if not r or not r[0]:
                continue
            key = (term, r[0])
            if key not in seen:
                seen.add(key)
                out.append((term, r[0], "label_match"))
    return out


def candidates_from_model(
    dsn: str, term: str, alias_table: str, model: str, botuser: str
) -> list[tuple[str, str, str]]:
    """Один терм → пачка сущностей с тем же словом в словаре (как wiki_alias collisions)."""
    esc = term.replace("'", "''")
    sql = (
        "WITH al AS (SELECT src_table, trim(lower(x.a)) AS alias "
        "FROM %s, unnest(str_split(aliases, ',')) AS x(a) WHERE trim(x.a) <> ''), "
        "pick AS (SELECT src_table FROM al WHERE alias = '%s' "
        "UNION SELECT src_table FROM wiki_entity_facts f "
        "WHERE lower(f.label) LIKE '%%%s%%' AND f.cls <> 'service' LIMIT 8) "
        "SELECT to_json(list(struct_pack(entity := f.src_table, title := f.label, "
        "quantities := coalesce(f.measures,'')))) "
        "FROM wiki_entity_facts f WHERE f.src_table IN (SELECT src_table FROM pick) "
        "ORDER BY f.src_table LIMIT 8" % (alias_table, esc, esc)
    )
    rows = psql_rows(dsn, sql)
    if not rows or not rows[0] or not rows[0][0]:
        return []
    pay = rows[0][0]
    if pay in ("", "[]", "null"):
        return []

    tmp = tempfile.mkdtemp(prefix="alias-cand-")
    msg_path = os.path.join(tmp, "msg")
    ans_path = os.path.join(tmp, "ans")
    err_path = os.path.join(tmp, "err")
    pay_path = os.path.join(tmp, "pay.json")
    rows_path = os.path.join(tmp, "rows.json")
    meas_path = os.path.join(tmp, "meas.json")
    with open(pay_path, "w", encoding="utf-8") as fh:
        fh.write(pay)
    with open(msg_path, "w", encoding="utf-8") as fh:
        fh.write(WIKI_PROMPT_HEAD)
        fh.write(pay)

    gateway = SERENED / "alias_infer_gateway.py"
    runas = os.environ.get("OPENCLAW_RUNAS", "").strip()
    if runas:
        cmd_prefix = runas.split()
    elif os.environ.get("USER") == botuser:
        cmd_prefix = []
    else:
        cmd_prefix = ["runuser", "-u", botuser, "--"] if os.geteuid() == 0 else []

    infer = cmd_prefix + [
        sys.executable,
        str(gateway),
        "--message-file",
        msg_path,
        "--model",
        model,
        "--thinking",
        "off",
        "--ans",
        ans_path,
        "--err",
        err_path,
    ]
    p = subprocess.run(infer, capture_output=True, text=True, timeout=600)
    if p.returncode != 0 or not os.path.isfile(ans_path):
        return []

    wap.main([ "wiki_alias_parse.py", ans_path, pay_path, rows_path, meas_path])
    try:
        parsed = json.loads(open(rows_path, encoding="utf-8").read())
    except (OSError, ValueError):
        return []
    out = []
    term_cf = term.casefold()
    for row in parsed:
        src = (row.get("src_table") or "").strip()
        if not src:
            continue
        aliases = wap._alias_tokens(row.get("aliases"))
        if any(term_cf in a.casefold() or a.casefold() in term_cf for a in aliases):
            out.append((term, src, "model"))
    return out


def expected_entity(sql: str | None) -> str:
    if not sql:
        return ""
    m = SRC_TABLE_RE.search(sql)
    return m.group(1) if m else ""


def gold_questions_for_term(
    gold_rows: list[dict], term: str, sample: int, rng: random.Random
) -> list[dict]:
    term_cf = term.casefold()
    matched = [
        r
        for r in gold_rows
        if term_cf in normalize_question(r.get("q") or "")
        or any(term_cf in t for t in tokenize_terms(r.get("q") or ""))
    ]
    if len(matched) <= sample:
        return matched
    idx = list(range(len(matched)))
    rng.shuffle(idx)
    pick = sorted(idx[:sample])
    return [matched[i] for i in pick]


def alias_rank(
    dsn: str, question: str, entity: str, alias_table: str, index: str
) -> int:
    esc_q = question.replace("'", "''")
    sql = (
        "SELECT src_table FROM %s WHERE aliases @@ '%s' "
        "ORDER BY tfidf(%s.tableoid) DESC, src_table LIMIT 8"
        % (index, esc_q, index)
    )
    try:
        rows = psql_rows(dsn, sql)
    except RuntimeError:
        return 0
    for i, r in enumerate(rows, 1):
        if r and r[0] == entity:
            return i
    return 0


def validate_candidate(
    cand: Candidate,
    gold_rows: list[dict],
    sample: int,
    dsn: str | None,
    alias_table: str,
    alias_index: str,
    dry_run: bool,
    rng: random.Random,
) -> None:
    subset = gold_questions_for_term(gold_rows, cand.term, sample, rng)
    cand.gold_sample_n = len(subset)
    if not subset:
        cand.check_result = "skip"
        cand.detail = "нет gold-вопросов с термом"
        return
    if dry_run and not dsn:
        cand.check_result = "dry_run"
        cand.detail = "без psql — проверка отложена"
        return

    passes = fails = 0
    details = []
    for row in subset:
        exp = expected_entity(row.get("sql"))
        if not exp:
            continue
        if cand.link != exp:
            fails += 1
            details.append("mismatch:%s" % row.get("q", "")[:40])
            continue
        rank = alias_rank(dsn or "", row.get("q") or "", cand.link, alias_table, alias_index)
        if rank == 1:
            passes += 1
            details.append("rank1")
        elif rank == 0:
            fails += 1
            details.append("not_in_top8")
        else:
            passes += 1
            details.append("rank%d" % rank)
    cand.gold_pass = passes
    cand.gold_fail = fails
    if fails and passes:
        cand.check_result = "partial"
    elif fails:
        cand.check_result = "fail"
    elif passes:
        cand.check_result = "pass"
    else:
        cand.check_result = "skip"
        cand.detail = "нет src_table в эталонах подмножества"
        return
    cand.detail = ";".join(details[:5])


def write_tsv(path: str, rows: list[Candidate]) -> None:
    header = (
        "term\tcandidate_link\tsource\tjournal_freq\tgold_sample_n\t"
        "gold_pass\tgold_fail\tcheck_result\tdetail\n"
    )
    lines = [header]
    for c in rows:
        lines.append(
            "\t".join(
                [
                    c.term,
                    c.link,
                    c.source,
                    str(c.journal_freq),
                    str(c.gold_sample_n),
                    str(c.gold_pass),
                    str(c.gold_fail),
                    c.check_result,
                    c.detail.replace("\t", " ").replace("\n", " ")[:200],
                ]
            )
            + "\n"
        )
    with open(path, "w", encoding="utf-8") as fh:
        fh.writelines(lines)


def merge_candidates(raw: list[tuple[str, str, str]], freq: dict[str, int]) -> list[Candidate]:
    seen: set[tuple[str, str]] = set()
    out: list[Candidate] = []
    for term, link, source in raw:
        key = (term.casefold(), link)
        if key in seen:
            continue
        seen.add(key)
        out.append(
            Candidate(
                term=term,
                link=link,
                source=source,
                journal_freq=freq.get(term.casefold(), freq.get(term, 0)),
            )
        )
    return out


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Прибор кандидатов алиасов (С5, read-only словарь)")
    p.add_argument("--since", default="7 days", help="окно журнала (interval или timestamp)")
    p.add_argument("--top", type=int, default=10, help="сколько термов из журнала")
    p.add_argument("--sample", type=int, default=7, help="макс. gold-вопросов на кандидата")
    p.add_argument("--out", default="candidates.tsv", help="выходной TSV")
    p.add_argument(
        "--gold-file",
        default=str(SERENED / "ab-probe-okna.tsv"),
        help="рабочий gold-подмножество (не ab-gold-okna)",
    )
    p.add_argument("--journal-file", help="офлайн TSV вместо psql (id ts outcome q_text …)")
    p.add_argument("--dsn", default="", help="DSN postgres для чтения")
    p.add_argument("--alias-table", default="search_entity_alias")
    p.add_argument("--alias-index", default="alias_idx")
    p.add_argument(
        "--apply",
        action="store_true",
        help="не dry-run: разрешить infer модели (в словарь всё равно не пишет)",
    )
    p.add_argument("--seed", type=int, default=0, help="seed выборки gold-подмножества")
    p.add_argument("--tick", type=int, default=0, help="метка такта (только в stderr)")
    p.add_argument(
        "--model",
        default=os.environ.get("WIKI_ALIAS_MODEL", "vllm/Qwen3.8-27B"),
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    dry_run = not args.apply
    dsn = args.dsn or default_dsn()
    rng = random.Random(args.seed or None)

    if args.tick:
        sys.stderr.write("alias_candidates: tick=%d dry_run=%s\n" % (args.tick, dry_run))

    if args.journal_file:
        journal = load_journal_file(args.journal_file)
    else:
        journal = load_journal_db(dsn, args.since)

    freq_list = top_terms(journal, args.top)
    if not freq_list:
        sys.stderr.write("alias_candidates: журнал пуст или нет термов\n")
        write_tsv(args.out, [])
        return 0

    freq = {t.casefold(): n for t, n in freq_list}
    terms = set(freq.keys())

    raw: list[tuple[str, str, str]] = []
    raw.extend(candidates_from_journal(journal, terms))
    if dsn and not args.journal_file:
        raw.extend(candidates_from_alias_table(dsn, terms, args.alias_table))
        raw.extend(candidates_from_labels(dsn, terms))
        if args.apply:
            botuser = os.environ.get("OPENCLAW_USER", "undebot")
            for term, _ in freq_list:
                raw.extend(
                    candidates_from_model(dsn, term, args.alias_table, args.model, botuser)
                )

    candidates = merge_candidates(raw, freq)
    gold_rows = scorer.load_gold(args.gold_file)

    for cand in candidates:
        validate_candidate(
            cand,
            gold_rows,
            args.sample,
            dsn if not args.journal_file else None,
            args.alias_table,
            args.alias_index,
            dry_run,
            rng,
        )

    write_tsv(args.out, candidates)
    sys.stderr.write(
        "alias_candidates: journal=%d terms=%d candidates=%d dry_run=%s → %s\n"
        % (len(journal), len(freq_list), len(candidates), dry_run, args.out)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
