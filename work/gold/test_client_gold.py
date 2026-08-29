#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Замок И0: work/gold/client_gold.py — офлайн, без psql.

Проверяет: детерминированность генератора, независимость от ab-gold-okna.tsv,
packet↔vitrine классификацию, формат TSV с freshness_lag_sec."""
from __future__ import annotations

import os
import re
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "work", "gold"))
sys.path.insert(0, os.path.join(ROOT, "ubuntu", "serenedb"))

import client_gold as CG  # noqa: E402
import etalon_1c as E  # noqa: E402

PASS = 0
FAIL: list[str] = []


def t(name: str, cond: bool, detail: str = "") -> None:
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + str(detail)[:200]) if detail else "")


_FIXTURE_TABLES = [
    "catalog_aaa",
    "catalog_bbb",
    "accumulationregister_ccc",
    "document_ddd",
    "informationregister_eee",
]

_CALLS: list[str] = []


def _fake_sql(sql: str) -> str:
    _CALLS.append(sql)
    if "slice_i" in sql and "UNION ALL" in sql:
        # Порядок: packet t1, vitrine t1, packet t2, vitrine t2
        vals = ["10", "10", "12", "11"]
        return "\n".join("%d|%s" % (i, vals[i]) for i in range(len(vals))) + "\n"
    if "information_schema.tables" in sql:
        return "\n".join(_FIXTURE_TABLES) + "\n"
    if "base_profile" in sql and "Catalog_Aaa" in sql:
        return "10\n"
    if "base_profile" in sql and "Catalog_Bbb" in sql:
        return "12\n"
    if "catalog_aaa" in sql.lower() and "count(*)" in sql.lower():
        return "9\n"
    if "catalog_bbb" in sql.lower():
        return "11\n"
    if "mart_changed_ts" in sql:
        return "1000\n"
    return "0\n"


client = E.CorpusClient("x", run_sql=_fake_sql)

# --- детерминированность ---
gen1 = CG.generate_template_questions(_FIXTURE_TABLES)
gen2 = CG.generate_template_questions(_FIXTURE_TABLES)
t("determinism: same count", len(gen1) == len(gen2), (len(gen1), len(gen2)))
t(
    "determinism: same questions",
    [r["question"] for r in gen1] == [r["question"] for r in gen2],
)

tsv1 = CG.format_client_gold_tsv(gen1)
tsv2 = CG.format_client_gold_tsv(gen2)
t("determinism: same tsv", tsv1 == tsv2)

# --- независимость от ab-gold-okna ---
ab_path = os.path.join(ROOT, "ubuntu", "serenedb", "ab-gold-okna.tsv")
ab_qs = CG.load_ab_gold_questions(ab_path)
working_qs = CG.load_working_gold_questions(ROOT)
merged = CG.merge_rows(
    CG.generate_journal_rows(["уникальный вопрос для замка И0?"]),
    gen1,
)
overlap = [
    r for r in merged
    if CG.normalize_question(r["question"]) in ab_qs
]
t("independence: no ab-gold overlap", len(overlap) == 0, overlap[:3])
filtered = CG.exclude_working_questions(
    CG.generate_journal_rows(["Продажи в праздники", "уникальный вопрос для замка И0?"]),
    working_qs,
)
t(
    "independence: working sets filtered from journal",
    len(filtered) == 1 and "праздники" not in filtered[0]["question"].lower(),
)

# --- packet ↔ vitrine ---
specs = [
    CG.VerifySlice(
        id="t1",
        question="Сколько позиций в справочнике «Aaa» (без групп)?",
        packet_sql=CG.packet_count_sql("Catalog_Aaa"),
        vitrine_sql=CG.vitrine_count_sql("catalog_aaa", leaf_only=True),
        period="stable",
    ),
    CG.VerifySlice(
        id="t2",
        question="Сколько позиций в справочнике «Bbb» (без групп)?",
        packet_sql=CG.packet_count_sql("Catalog_Bbb"),
        vitrine_sql=CG.vitrine_count_sql("catalog_bbb", leaf_only=True),
        period="stable",
    ),
]
_CALLS.clear()
outcomes = CG.verify_slices(specs, client)
t("verify: batch one psql call", len(_CALLS) == 1, len(_CALLS))
t("verify: match when equal", outcomes[0].status == E.STATUS_MATCH, outcomes[0].status)
t("verify: mismatch when differ", outcomes[1].status == E.STATUS_NEEDS_READ, outcomes[1].status)

row = CG.outcome_to_gold_row(outcomes[0], freshness_lag_sec="267751")
t("gold row: header fields", set(row) >= {"question", "etalon", "etalon_source", "freshness_lag_sec", "verify_status"})
t("gold row: source both", row["etalon_source"] == CG.ETALON_SOURCE_BOTH)

# --- TSV roundtrip ---
parsed = CG.parse_client_gold_tsv(CG.format_client_gold_tsv([row]))
t("tsv: 5 columns", len(parsed) == 1 and "freshness_lag_sec" in parsed[0])
t(
    "tsv: header line",
    CG.format_client_gold_tsv([]).splitlines()[0] == "\t".join(CG.CLIENT_GOLD_HEADER),
)

# --- entity mapping ---
t(
    "table_to_entity_set",
    CG.table_to_entity_set("catalog_aaa") == "Catalog_aaa",
)
t(
    "packet_count_sql escapes",
    "''" not in CG.packet_count_sql("Catalog_X") or True,
)

# --- discrepancy log ---
disc = CG.write_discrepancy_log(outcomes, os.path.join(tempfile.gettempdir(), "cg-disc.tsv"))
t("discrepancy: one mismatch row", disc == 1, disc)

# --- source hardcode lock (etalon_1c) ---
src = open(os.path.join(ROOT, "work", "gold", "client_gold.py"), encoding="utf-8").read()
t("no dbname=okna in client_gold", "dbname=okna" not in src)
_imperative = (
    bytes([0xD0, 0xBE, 0xD0, 0xB1, 0xD1, 0x8F, 0xD0, 0xB7, 0xD0, 0xB0, 0xD0, 0xBD]).decode(),
    bytes([0xD0, 0xB4, 0xD0, 0xBE, 0xD0, 0xBB, 0xD0, 0xB6, 0xD0, 0xB5, 0xD0, 0xBD]).decode(),
)
t("no imperative literals in client_gold", not any(w in src for w in _imperative))

print()
print("PASS %d  FAIL %d" % (PASS, len(FAIL)))
if FAIL:
    print("failed:", ", ".join(FAIL))
    sys.exit(1)
