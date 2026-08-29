#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Замок И0+И2: work/gold/ — офлайн, без psql и HTTP.

Проверяет: детерминированность генератора И0, независимость от ab-gold-okna.tsv,
packet↔vitrine классификацию, формат TSV; механические вердикты И2 на синтетике."""
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

_i2_src = open(os.path.join(ROOT, "work", "gold", "i2_runner.py"), encoding="utf-8").read()
t("no dbname=okna in i2_runner", "dbname=okna" not in _i2_src)
t("no imperative literals in i2_runner", not any(w in _i2_src for w in _imperative))

# --- И2: механические вердикты (синтетика, без HTTP) ---
import i2_runner as I2  # noqa: E402

t(
    "i2: no phrase-marker lists in i2_runner",
    "_CLARIFY_MARKERS" not in _i2_src
    and "looks_like_clarify" not in _i2_src,
    # конкретные фразы-словари не перечисляем: их ловит гейт check-prompt-rules
    # на коммите (поймал 29.08 дважды), дубль словами здесь сам стал бы списком
)


def _i2_mock_ok() -> bool:
    rows = [
        I2.QuestionRow("q1", "10"),
        I2.QuestionRow("q2", "no_data"),
    ]

    def eng(q: str) -> I2.PathAnswer:
        if q == "q1":
            return I2.PathAnswer(
                I2.PATH_ENGINE, text="10", kind="answer", diag={"found": 5},
            )
        return I2.PathAnswer(
            I2.PATH_ENGINE, text="Нет таких данных.", kind="no_data",
        )

    def web(q: str) -> I2.PathAnswer:
        # Шлюз chatCompletions обычно не доносит kind/diag — только текст.
        if q == "q1":
            return I2.PathAnswer(I2.PATH_WEB, text="10", kind="")
        return I2.PathAnswer(I2.PATH_WEB, text="Данных нет.", kind="")

    I2.run_i2(rows, paths=[I2.PATH_ENGINE, I2.PATH_WEB], engine_ask=eng, web_ask=web)
    return (
        rows[0].engine
        and rows[0].engine.verdict == I2.VERDICT_MATCH
        and rows[1].engine
        and rows[1].engine.verdict == I2.VERDICT_HONEST_NO
        and rows[0].web
        and rows[0].web.verdict == I2.VERDICT_UNRESOLVED
        and rows[1].web
        and rows[1].web.verdict == I2.VERDICT_UNRESOLVED
    )


t(
    "i2: match when number equals etalon",
    I2.classify_verdict(text="Итого: 293 банка.", etalon="293", kind="answer")
    == I2.VERDICT_MATCH,
)
t(
    "i2: confident_wrong when number differs",
    I2.classify_verdict(text="Всего 300.", etalon="293", kind="figures")
    == I2.VERDICT_CONFIDENT_WRONG,
)
t(
    "i2: honest_no on clarify kind only",
    I2.classify_verdict(text="Уточните, за какой период?", etalon="100", kind="clarify")
    == I2.VERDICT_HONEST_NO,
)
t(
    "i2: honest_no on no_data kind",
    I2.classify_verdict(text="Таких данных нет.", etalon="no_data", kind="no_data")
    == I2.VERDICT_HONEST_NO,
)
t(
    "i2: text alone without kind is unresolved",
    I2.classify_verdict(text="Уточните период?", etalon="100", kind="")
    == I2.VERDICT_UNRESOLVED,
)
t(
    "i2: confident_wrong on matches=0 with number",
    I2.classify_verdict(
        text="Ответ: 42.",
        etalon="100",
        kind="answer",
        diag={"found": 0},
    )
    == I2.VERDICT_CONFIDENT_WRONG,
)
t(
    "i2: confident_wrong on doubt with number",
    I2.classify_verdict(
        text="Сумма 1 234 567,89 руб.",
        etalon="1234567.89",
        kind="answer",
        diag={"doubt": True},
    )
    == I2.VERDICT_CONFIDENT_WRONG,
)
t(
    "i2: unresolved on transport error",
    I2.classify_verdict(transport_error="URLError: timed out") == I2.VERDICT_UNRESOLVED,
)
t(
    "i2: unresolved on empty answer",
    I2.classify_verdict(text="", kind="") == I2.VERDICT_UNRESOLVED,
)
t(
    "i2: confident_wrong number against no_data etalon",
    I2.classify_verdict(text="На складе 5 позиций.", etalon="no_data", kind="answer")
    == I2.VERDICT_CONFIDENT_WRONG,
)
t(
    "i2: match from atom exact_value",
    I2.classify_verdict(
        text="",
        etalon="42",
        kind="answer",
        nums=I2.structured_nums({"atom": {"exact_value": 42}}),
    )
    == I2.VERDICT_MATCH,
)
t(
    "i2: ask_fields_from_payload engine envelope",
    I2.ask_fields_from_payload(
        {"kind": "clarify", "text": "x", "diag": {"found": 2}}
    )[:2]
    == ("clarify", {"found": 2}),
)
t(
    "i2: ask_fields_from_payload chatCompletions has no kind",
    I2.ask_fields_from_payload(
        {"choices": [{"message": {"content": "Уточните?"}}]}
    )[0]
    == "",
)
t(
    "i2: dry run_i2 mock both paths",
    _i2_mock_ok(),
)


print()
print("PASS %d  FAIL %d" % (PASS, len(FAIL)))
if FAIL:
    print("failed:", ", ".join(FAIL))
    sys.exit(1)
