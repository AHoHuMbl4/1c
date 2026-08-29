#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""И0: генератор client-gold и сверка packet ↔ vitrine (без search_corpus).

Покрытие сущностей — information_schema.tables (catalog_*, accumulationregister_*, document*).
Формулировки — шаблоны классов × сущности + живые вопросы из ask_journal_text.
Эталон — двойной счёт: base_profile (пакетный след apply) vs SQL по витрине.
Расхождения — в отдельный лог, не молча.

Запуск:
  python3 work/gold/client_gold.py build --dsn "$SERENEDB_DSN" \\
      --slices work/gold/slices-okna-packet.json \\
      --out ubuntu/serenedb/client-gold-okna.tsv \\
      --discrepancy-log work/acceptance/runs/client-gold-discrepancies.tsv

Env: SERENEDB_DSN / ETALON_DSN, PGPASSWORD.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Optional

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_SERENEDB = os.path.join(_REPO, "ubuntu", "serenedb")
if _SERENEDB not in sys.path:
    sys.path.insert(0, _SERENEDB)

import etalon_1c as E  # noqa: E402

CLIENT_GOLD_HEADER = (
    "question",
    "etalon",
    "etalon_source",
    "freshness_lag_sec",
    "verify_status",
)

ETALON_SOURCE_PACKET = "packet"
ETALON_SOURCE_VITRINE = "vitrine"
ETALON_SOURCE_BOTH = "packet+vitrine"
ETALON_SOURCE_JOURNAL = E.ETALON_SOURCE_JOURNAL
ETALON_SOURCE_TEMPLATE = "template"

_TABLE_PREFIXES = ("catalog", "accumulationregister", "document")

# Шаблоны классов вопросов (универсальные, без привязки к базе).
_QUESTION_TEMPLATES: list[dict] = [
    {
        "kind": "catalog_leaf",
        "prefix": "catalog_",
        "template": "Сколько позиций в справочнике «{title}» (без групп)?",
    },
    {
        "kind": "document_count",
        "prefix": "document_",
        "template": "Сколько документов «{title}»?",
    },
    {
        "kind": "register_rows",
        "prefix": "accumulationregister_",
        "template": "Сколько движений в регистре «{title}»?",
    },
    {
        "kind": "register_period",
        "prefix": "accumulationregister_",
        "template": "Сколько движений в регистре «{title}» за последние 30 дней?",
    },
    {
        "kind": "table_rows",
        "prefix": "",
        "template": "Сколько записей в «{title}»?",
    },
]


def normalize_question(text: str) -> str:
    s = (text or "").strip().lower().replace("ё", "е")
    s = re.sub(r"\s+", " ", s)
    return s.strip(" «»\"'?.!,;:")


def table_to_entity_set(table_name: str) -> str:
    """catalog_aaa → Catalog_Aaa (префикс OData + хвост как в таблице)."""
    t = (table_name or "").strip()
    if "_" not in t:
        return t
    kind, rest = t.split("_", 1)
    mapping = {
        "catalog": "Catalog",
        "document": "Document",
        "accumulationregister": "AccumulationRegister",
        "informationregister": "InformationRegister",
    }
    prefix = mapping.get(kind.lower())
    if not prefix:
        return t
    return "%s_%s" % (prefix, rest)


def human_title(table_name: str) -> str:
    return E.humanize_entity_set(table_to_entity_set(table_name))


def _sql_escape(s: str) -> str:
    return (s or "").replace("'", "''")


def packet_count_sql(entity_set: str) -> str:
    return (
        "SELECT coalesce(max(rows), 0) FROM base_profile "
        "WHERE entity = '%s'"
    ) % _sql_escape(entity_set)


def vitrine_count_sql(table_name: str, *, leaf_only: bool = False) -> str:
    t = _sql_escape(table_name)
    if leaf_only:
        return (
            "SELECT count(*) FROM %s WHERE "
            "lower(cast(isfolder as varchar)) NOT IN ('true','t','1') AND "
            "lower(cast(deletionmark as varchar)) NOT IN ('true','t','1')"
        ) % t
    return "SELECT count(*) FROM %s" % t


def vitrine_tables_sql(prefixes: Iterable[str]) -> str:
    prefs = list(prefixes) or list(_TABLE_PREFIXES)
    likes = " OR ".join(
        "table_name LIKE '%s_%%'" % p.replace("'", "''") for p in prefs
    )
    return (
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public' AND (%s) ORDER BY table_name"
    ) % likes


@dataclass
class VerifySlice:
    id: str
    question: str
    period: str = "stable"
    packet_sql: str = ""
    vitrine_sql: str = ""
    declared: Any = None

    @classmethod
    def from_dict(cls, d: dict) -> "VerifySlice":
        packet = d.get("packet") or {}
        vitrine = d.get("vitrine") or d.get("fact") or {}
        return cls(
            id=str(d.get("id") or ""),
            question=d.get("question") or "",
            period=(d.get("period") or "stable").lower(),
            packet_sql=packet.get("sql") or d.get("packet_sql") or "",
            vitrine_sql=(
                vitrine.get("sql") or d.get("vitrine_sql")
                or d.get("fact_sql") or ""
            ),
            declared=d.get("declared") if "declared" in d else d.get("etalon"),
        )


@dataclass
class VerifyOutcome:
    slice_id: str
    question: str
    packet_value: Any = None
    vitrine_value: Any = None
    declared: Any = None
    status: str = E.STATUS_PENDING
    reason: str = ""
    error: str = ""

    def to_discrepancy_row(self) -> Optional[dict]:
        if self.status in (E.STATUS_MATCH, E.STATUS_PENDING, E.STATUS_ERROR):
            if self.status != E.STATUS_ERROR:
                return None
        if self.error:
            return {
                "id": self.slice_id,
                "question": self.question,
                "packet": self.packet_value,
                "vitrine": self.vitrine_value,
                "status": self.status,
                "reason": self.error,
            }
        if self.status in (
            E.STATUS_MISMATCH,
            E.STATUS_FRESHNESS_LAG,
            E.STATUS_DECLARED_WRONG,
            E.STATUS_NEEDS_READ,
        ):
            return {
                "id": self.slice_id,
                "question": self.question,
                "packet": self.packet_value,
                "vitrine": self.vitrine_value,
                "status": self.status,
                "reason": self.reason,
            }
        return None


def verify_slices(
    specs: list[VerifySlice],
    client: E.CorpusClient,
    *,
    just_after_tick: bool = False,
) -> list[VerifyOutcome]:
    outcomes: list[VerifyOutcome] = [
        VerifyOutcome(s.id, s.question, declared=s.declared) for s in specs
    ]
    indexed: list[tuple[int, str, str]] = []
    for i, spec in enumerate(specs):
        if spec.packet_sql:
            indexed.append((i, "packet", spec.packet_sql))
        if spec.vitrine_sql:
            indexed.append((i, "vitrine", spec.vitrine_sql))
    if not indexed:
        return outcomes
    try:
        values = client.scalars([sql for _, _, sql in indexed])
    except Exception as exc:  # noqa: BLE001
        err = "%s: %s" % (type(exc).__name__, exc)
        for i, _, _ in indexed:
            outcomes[i].error = err
            outcomes[i].status = E.STATUS_ERROR
        return outcomes

    for (i, side, _), val in zip(indexed, values):
        if side == "packet":
            outcomes[i].packet_value = val
        else:
            outcomes[i].vitrine_value = val

    for i, spec in enumerate(specs):
        o = outcomes[i]
        if o.error:
            continue
        cls = E.classify_discrepancy(
            o.packet_value,
            o.vitrine_value,
            o.declared,
            question=spec.question,
            period_hint=spec.period,
            just_after_tick=just_after_tick,
        )
        o.status = cls.status
        o.reason = cls.reason
        if cls.needs_independent_read and o.status == E.STATUS_MISMATCH:
            o.status = E.STATUS_NEEDS_READ
    return outcomes


def outcome_to_gold_row(
    outcome: VerifyOutcome,
    *,
    freshness_lag_sec: str = "",
) -> dict:
    packet, vitrine = outcome.packet_value, outcome.vitrine_value
    if packet is not None and vitrine is not None:
        if E.numbers_equal(packet, vitrine):
            etalon = E._jsonable(vitrine)
            source = ETALON_SOURCE_BOTH
        else:
            etalon = E._jsonable(vitrine)
            source = ETALON_SOURCE_VITRINE
    elif vitrine is not None:
        etalon = E._jsonable(vitrine)
        source = ETALON_SOURCE_VITRINE
    elif packet is not None:
        etalon = E._jsonable(packet)
        source = ETALON_SOURCE_PACKET
    elif outcome.declared is not None:
        etalon = E._jsonable(outcome.declared)
        source = E.ETALON_SOURCE_DECLARED
    else:
        etalon = ""
        source = E.ETALON_SOURCE_PENDING
    return {
        "question": outcome.question,
        "etalon": etalon,
        "etalon_source": source,
        "freshness_lag_sec": freshness_lag_sec,
        "verify_status": outcome.status,
    }


def format_client_gold_tsv(rows: Iterable[dict]) -> str:
    lines = ["\t".join(CLIENT_GOLD_HEADER)]
    for row in rows:
        cells = [
            str(row.get("question") or "").replace("\t", " ").replace("\n", " "),
            str(row.get("etalon") if row.get("etalon") is not None else ""),
            str(row.get("etalon_source") or E.ETALON_SOURCE_PENDING),
            str(row.get("freshness_lag_sec") or ""),
            str(row.get("verify_status") or E.STATUS_PENDING),
        ]
        lines.append("\t".join(cells))
    return "\n".join(lines) + "\n"


def parse_client_gold_tsv(text: str) -> list[dict]:
    rows = []
    for i, line in enumerate(text.splitlines()):
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if i == 0 and parts and parts[0] == "question":
            continue
        while len(parts) < 5:
            parts.append("")
        rows.append({
            "question": parts[0],
            "etalon": parts[1],
            "etalon_source": parts[2],
            "freshness_lag_sec": parts[3],
            "verify_status": parts[4],
        })
    return rows


def load_slices(path: str) -> list[VerifySlice]:
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    if isinstance(raw, dict) and "slices" in raw:
        raw = raw["slices"]
    if not isinstance(raw, list):
        raise ValueError('slices: список или {"slices": [...]}')
    return [VerifySlice.from_dict(x) for x in raw]


def fetch_vitrine_tables(client: E.CorpusClient, prefixes: Iterable[str]) -> list[str]:
    out = client._exec(vitrine_tables_sql(prefixes))
    return [ln.strip() for ln in out.splitlines() if ln.strip()]


def fetch_freshness_lag_sec(client: E.CorpusClient) -> Optional[int]:
    """Секунды с последнего такта (build_state.ts), не search_quality."""
    sql = (
        "SELECT extract(epoch from (now() - max(ts)))::bigint "
        "FROM build_state WHERE ts IS NOT NULL"
    )
    try:
        raw = client.scalar(sql)
        if raw is None or str(raw).strip() == "":
            return None
        return int(float(str(raw).strip()))
    except (ValueError, TypeError, RuntimeError):
        return None


def table_has_period_column(client: E.CorpusClient, table_name: str) -> bool:
    """Колонка Period есть в витрине (DESCRIBE, не information_schema.columns)."""
    t = _sql_escape(table_name)
    try:
        out = client._exec("DESCRIBE %s" % t)
    except RuntimeError:
        return False
    for line in out.splitlines():
        parts = [p.strip() for p in line.split("|")]
        if parts and parts[0].lower() == "period":
            return True
    return False


def vitrine_period_count_sql(table_name: str, *, days: int = 30) -> str:
    t = _sql_escape(table_name)
    return (
        "WITH today AS (SELECT current_date AS d) "
        "SELECT count(*) FROM %s, today "
        "WHERE CAST(Period AS TIMESTAMP) >= today.d - INTERVAL '%d day' "
        "AND CAST(Period AS TIMESTAMP) < today.d + INTERVAL 1 day"
    ) % (t, int(days))


def generate_template_questions(
    tables: Iterable[str],
    *,
    limit_per_kind: int = 0,
    period_check: Optional[Callable[[str], bool]] = None,
) -> list[dict]:
    rows: list[dict] = []
    has_period = period_check or (lambda _t: False)
    for table in sorted(set(tables)):
        low = table.lower()
        title = human_title(table)
        for tpl in _QUESTION_TEMPLATES:
            pref = tpl.get("prefix") or ""
            if pref and not low.startswith(pref):
                continue
            if tpl["kind"] == "table_rows" and pref:
                continue
            if tpl["kind"] != "table_rows" and not pref:
                continue
            if tpl["kind"] == "register_period" and not has_period(table):
                continue
            q = tpl["template"].format(title=title)
            row = {
                "question": q,
                "etalon": "",
                "etalon_source": ETALON_SOURCE_TEMPLATE,
                "freshness_lag_sec": "",
                "verify_status": E.STATUS_PENDING,
                "src_table": table,
                "template_kind": tpl["kind"],
            }
            entity = table_to_entity_set(table)
            if tpl["kind"] == "catalog_leaf":
                row["packet_sql"] = packet_count_sql(entity)
                row["vitrine_sql"] = vitrine_count_sql(table, leaf_only=True)
            elif tpl["kind"] == "register_period":
                sql = vitrine_period_count_sql(table)
                row["packet_sql"] = sql
                row["vitrine_sql"] = sql
                row["period"] = "relative"
            elif tpl["kind"] in ("document_count", "register_rows", "table_rows"):
                row["packet_sql"] = packet_count_sql(entity)
                row["vitrine_sql"] = vitrine_count_sql(table, leaf_only=False)
            rows.append(row)
            if limit_per_kind and sum(
                1 for r in rows if r.get("template_kind") == tpl["kind"]
            ) >= limit_per_kind:
                break
    return rows


def _journal_question_ok(text: str) -> bool:
    q = (text or "").strip()
    if q.startswith("User:"):
        q = q[5:].strip()
    if len(q) < 8:
        return False
    if q.startswith("[") or q.startswith("Assistant:"):
        return False
    if q.startswith("Уточните,") or q.startswith("Что могу подтвердить"):
        return False
    if "Chat messages since" in q or "Current message" in q:
        return False
    return True


def _normalize_journal_question(text: str) -> str:
    q = (text or "").strip()
    if q.startswith("User:"):
        q = q[5:].strip()
    return q


def generate_journal_rows(
    questions: Iterable[str],
    *,
    limit: int = 0,
) -> list[dict]:
    out = []
    seen = set()
    for q in questions:
        q = _normalize_journal_question(q)
        if not q or not _journal_question_ok(q):
            continue
        key = normalize_question(q)
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "question": q,
            "etalon": "",
            "etalon_source": ETALON_SOURCE_JOURNAL,
            "freshness_lag_sec": "",
            "verify_status": E.STATUS_PENDING,
        })
        if limit and len(out) >= limit:
            break
    return out


def merge_rows(*groups: list[dict]) -> list[dict]:
    out = []
    seen = set()
    for group in groups:
        for row in group:
            q = (row.get("question") or "").strip()
            if not q:
                continue
            key = normalize_question(q)
            if key in seen:
                continue
            seen.add(key)
            out.append(dict(row))
    return out


def load_ab_gold_questions(path: str) -> set[str]:
    qs = set()
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            qs.add(normalize_question(line.split("\t", 1)[0]))
    return qs


def load_working_gold_questions(repo_root: str) -> set[str]:
    """Все формулировки из рабочих наборов (GOLD_SETS §3 WORKING)."""
    working_files = (
        "ubuntu/serenedb/ab-gold-okna.tsv",
        "ubuntu/serenedb/ab-probe-okna.tsv",
        "ubuntu/serenedb/ab-gold.tsv",
        "ubuntu/serenedb/golden-questions.txt",
        "ubuntu/serenedb/ab-calendar-axis-okna.tsv",
    )
    qs: set[str] = set()
    for rel in working_files:
        path = os.path.join(repo_root, rel)
        if not os.path.isfile(path):
            continue
        if rel.endswith(".txt"):
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        qs.add(normalize_question(line))
        else:
            qs |= load_ab_gold_questions(path)
    return qs


def exclude_working_questions(rows: list[dict], working: set[str]) -> list[dict]:
    if not working:
        return rows
    out = []
    for row in rows:
        q = normalize_question(row.get("question") or "")
        if q and q in working:
            continue
        out.append(row)
    return out


def verify_template_rows(
    rows: list[dict],
    client: E.CorpusClient,
    *,
    freshness_lag_sec: str = "",
    just_after_tick: bool = False,
) -> tuple[list[dict], list[VerifyOutcome]]:
    specs = []
    idx_map = []
    for i, row in enumerate(rows):
        ps = row.get("packet_sql") or ""
        vs = row.get("vitrine_sql") or ""
        if not ps and not vs:
            continue
        specs.append(VerifySlice(
            id=row.get("src_table") or str(i),
            question=row["question"],
            packet_sql=ps,
            vitrine_sql=vs,
            period=(row.get("period") or "stable").lower(),
        ))
        idx_map.append(i)
    if not specs:
        return rows, []
    outcomes = verify_slices(specs, client, just_after_tick=just_after_tick)
    for pos, outcome in zip(idx_map, outcomes):
        gold = outcome_to_gold_row(outcome, freshness_lag_sec=freshness_lag_sec)
        rows[pos].update(gold)
    return rows, outcomes


def write_discrepancy_log(outcomes: list[VerifyOutcome], path: str) -> int:
    rows = []
    for o in outcomes:
        d = o.to_discrepancy_row()
        if d:
            rows.append(d)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("id\tquestion\tpacket\tvitrine\tstatus\treason\n")
        for r in rows:
            f.write(
                "\t".join(
                    str(r.get(k) or "").replace("\t", " ").replace("\n", " ")
                    for k in ("id", "question", "packet", "vitrine", "status", "reason")
                )
                + "\n"
            )
    return len(rows)


def load_working_gold_questions(repo_root: Optional[str] = None) -> set[str]:
    """Нормализованные вопросы рабочих наборов (GOLD_SETS §3 WORKING)."""
    root = repo_root or _REPO
    serenedb = os.path.join(root, "ubuntu", "serenedb")
    names = (
        "ab-gold-okna.tsv",
        "ab-probe-okna.tsv",
        "ab-gold.tsv",
        "golden-questions.txt",
        "ab-calendar-axis-okna.tsv",
    )
    out: set[str] = set()
    for name in names:
        path = os.path.join(serenedb, name)
        if not os.path.isfile(path):
            continue
        if name.endswith(".txt"):
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        out.add(normalize_question(line))
        else:
            out.update(load_ab_gold_questions(path))
    return out


def exclude_working_questions(rows: list[dict], working: set[str]) -> list[dict]:
    return [
        r for r in rows
        if normalize_question(r.get("question") or "") not in working
    ]


def cmd_build(args: argparse.Namespace) -> int:
    dsn = (args.dsn or "").strip()
    if not dsn:
        dsn = (
            os.environ.get("ETALON_DSN")
            or os.environ.get("SERENEDB_DSN")
            or ""
        ).strip()
    if not dsn:
        raise SystemExit("нужен --dsn или SERENEDB_DSN / ETALON_DSN")

    client = E.CorpusClient(dsn)
    lag = fetch_freshness_lag_sec(client)
    lag_s = str(lag) if lag is not None else ""

    prefixes = [
        p.strip() for p in (args.table_prefixes or "").split(",") if p.strip()
    ] or list(_TABLE_PREFIXES)

    tables = fetch_vitrine_tables(client, prefixes)
    sys.stderr.write(
        "vitrine tables: %d (%s)\n" % (len(tables), ",".join(prefixes))
    )

    journal_rows: list[dict] = []
    if args.journal_tsv:
        qs = []
        with open(args.journal_tsv, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    qs.append(line.split("\t", 1)[0].strip())
        journal_rows = generate_journal_rows(
            qs, limit=int(args.limit_journal or 0),
        )
    elif args.from_journal:
        qs = client.journal_questions(limit=int(args.limit_journal or 500) or 500)
        journal_rows = generate_journal_rows(
            qs, limit=int(args.limit_journal or 0),
        )

    period_cache: dict[str, bool] = {}

    def _has_period(table: str) -> bool:
        if table not in period_cache:
            period_cache[table] = table_has_period_column(client, table)
        return period_cache[table]

    template_rows = generate_template_questions(
        tables,
        limit_per_kind=int(args.limit_per_kind or 0),
        period_check=_has_period,
    )
    if args.limit_templates and int(args.limit_templates) > 0:
        template_rows = template_rows[: int(args.limit_templates)]

    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    working_qs = load_working_gold_questions(repo_root)
    journal_rows = exclude_working_questions(journal_rows, working_qs)
    template_rows = exclude_working_questions(template_rows, working_qs)

    merged = merge_rows(journal_rows, template_rows)
    merged = exclude_working_questions(merged, load_working_gold_questions())
    merged, template_outcomes = verify_template_rows(
        merged, client, freshness_lag_sec=lag_s,
        just_after_tick=bool(args.just_after_tick),
    )

    slice_outcomes: list[VerifyOutcome] = []
    if args.slices:
        specs = load_slices(args.slices)
        slice_outcomes = verify_slices(
            specs, client, just_after_tick=bool(args.just_after_tick),
        )
        slice_gold = [
            outcome_to_gold_row(o, freshness_lag_sec=lag_s)
            for o in slice_outcomes
        ]
        by_q = {normalize_question(r["question"]): r for r in merged}
        for g in slice_gold:
            by_q[normalize_question(g["question"])] = g
        merged = list(by_q.values())
        merged.sort(key=lambda r: normalize_question(r.get("question") or ""))

    out = args.out or "client-gold.tsv"
    with open(out, "w", encoding="utf-8") as f:
        f.write(format_client_gold_tsv(merged))

    all_outcomes = template_outcomes + slice_outcomes
    disc_n = 0
    if args.discrepancy_log and all_outcomes:
        disc_n = write_discrepancy_log(all_outcomes, args.discrepancy_log)

    counts: dict[str, int] = {}
    for r in merged:
        st = r.get("verify_status") or E.STATUS_PENDING
        counts[st] = counts.get(st, 0) + 1
    with_etalon = sum(1 for r in merged if str(r.get("etalon") or "").strip())

    sys.stderr.write(
        "client-gold: total=%d journal=%d template=%d with_etalon=%d "
        "freshness_lag_sec=%s counts=%s discrepancy_rows=%d → %s\n"
        % (
            len(merged),
            len(journal_rows),
            len(template_rows),
            with_etalon,
            lag_s or "?",
            counts,
            disc_n,
            out,
        )
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="И0: client-gold generator (packet↔vitrine)")
    p.add_argument("--dsn", default="", help="DSN SereneDB (витрина)")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="собрать client-gold.tsv")
    b.add_argument("--out", default="client-gold.tsv")
    b.add_argument(
        "--slices",
        default="",
        help="JSON срезов ACCEPTANCE (packet+vitrine)",
    )
    b.add_argument("--from-journal", action="store_true")
    b.add_argument("--journal-tsv", default="")
    b.add_argument("--limit-journal", type=int, default=40)
    b.add_argument(
        "--table-prefixes",
        default="catalog,accumulationregister,document",
    )
    b.add_argument("--limit-templates", type=int, default=0)
    b.add_argument("--limit-per-kind", type=int, default=0)
    b.add_argument("--discrepancy-log", default="")
    b.add_argument("--just-after-tick", action="store_true")
    b.set_defaults(func=cmd_build)
    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    sys.exit(main())
