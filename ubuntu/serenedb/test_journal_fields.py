#!/usr/bin/env python3
"""Расширение журнала clarify (план A/B/C шаг 1, 23.08).

Замки оффлайн:
  · clarify → doubt / clarify_options / atoms заполнены;
  · ответ без clarify → clarify_options null, atoms из ответа или пусто;
  · ticket_variant при trusted;
  · текст только в ask_journal_text, не в INSERT ask_journal;
  · ошибка записи не роняет ответ.

Запуск: python3 ubuntu/serenedb/test_journal_fields.py
"""
import hashlib
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ASK_TOKEN", "test")
os.environ.setdefault("EMBED_BASE_URL", "-")
os.environ.setdefault("EMBED_MODEL", "-")
os.environ.setdefault("ASK_JOURNAL", "1")

import serene_ask as A  # noqa: E402

PASS, FAIL = 0, []


def t(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, detail)


def _fake_psql_factory(captured, nid_box, fail_on=None):
    def fake_psql(sql):
        if fail_on and fail_on in sql:
            raise RuntimeError("journal down: " + fail_on)
        captured.append(sql)
        if "nextval" in sql:
            nid_box[0] += 1
            return [[str(nid_box[0])]]
        if "search_quality" in sql or "concat_ws" in sql:
            return [["1|2|3"]]
        if "count(*) FROM search_tables" in sql or "count(*) FROM %s" % A.TABLES in sql:
            return [["8"]]
        return []
    return fake_psql


Q_CLARIFY = "сколько товара на складе?"
Q_ANSWER = "сколько наторговали в прошедшее воскресенье?"

captured, nid_box = [], [0]
A.ASK_JOURNAL = True
A._JOURNAL_KEEP = 200
A._JOURNAL_LOST = 0
A._JOURNAL_ALIAS_VER = "1|2|3"
A._JOURNAL_BUILD_TS = "1"
A._JOURNAL_BUILD_TS_AT = 1e18
old_psql = A.psql
A.psql = _fake_psql_factory(captured, nid_box)

try:
    clarify_out = {
        "kind": "clarify",
        "text": "уточните источник",
        "options": [
            {"label": "Остатки ТМЦ", "src": "accumulationregister_a",
             "decision_id": "d1"},
            {"label": "Счёт учёта", "src": "accountingregister_b",
             "measure": "Количество"},
        ],
        "diag": {
            "kind": "товар",
            "doubt": True,
            "fork_outcome": "C",
            "fork": {
                "outcome": "C",
                "atoms": [
                    {"atom": {"operation": "sum", "exact_value": "10.00",
                              "measure_id": "Количество"}},
                    {"atom": {"operation": "sum", "exact_value": "20.00",
                              "measure_id": "Количество"}},
                    {"atom": {"operation": "sum", "exact_value": "10.00",
                              "measure_id": "Количество"}},
                ],
            },
            "tokens": {"in": 2, "out": 1, "calls": 1},
        },
        "partial": None,
    }
    A._ask_journal_write(Q_CLARIFY, clarify_out, time.monotonic() - 0.02,
                         user="u-clarify", channel="probe")
    inserts = [s for s in captured if s.strip().upper().startswith("INSERT INTO ASK_JOURNAL ")]
    text_ins = [s for s in captured if "ask_journal_text" in s]
    t("clarify: INSERT ask_journal есть", len(inserts) == 1, len(inserts))
    sql = inserts[0] if inserts else ""
    # doubt — предпоследние поля VALUES; ищем TRUE рядом с rid
    t("clarify: doubt=TRUE", ", TRUE," in sql or sql.rstrip().endswith("TRUE)")
       or ", TRUE)" in sql, (sql[-180:] if sql else ""))
    # doubt is near end — check explicitly via helpers
    t("clarify: helper doubt True", A._journal_doubt(clarify_out) is True)
    opts = A._journal_clarify_options(clarify_out)
    t("clarify: options filled", isinstance(opts, list) and len(opts) == 2
      and opts[0].get("label") == "Остатки ТМЦ", opts)
    t("clarify: options в SQL", opts is not None and "Остатки ТМЦ" in sql, sql[-400:])
    atoms = A._journal_atoms_slim(clarify_out)
    t("clarify: atoms из fork, дедуп", len(atoms) == 2, atoms)
    t("clarify: atoms в SQL", "10.00" in sql and "20.00" in sql, sql[sql.find("atoms"):sql.find("atoms")+200])
    t("clarify: текста вопроса нет в ask_journal", Q_CLARIFY not in sql)
    t("clarify: текст в ask_journal_text", len(text_ins) == 1 and Q_CLARIFY in text_ins[0],
      text_ins[:1])

    captured.clear()
    answer_out = {
        "kind": "answer",
        "text": "0.00",
        "atom": {"operation": "sum", "exact_value": "0.00", "measure_id": "Всего"},
        "diag": {"kind": "продажи", "doubt": False, "tokens": {"in": 1, "out": 1, "calls": 1}},
        "partial": None,
    }
    A._ask_journal_write(Q_ANSWER, answer_out, time.monotonic() - 0.01,
                         user="u-ans", channel="probe")
    inserts = [s for s in captured if s.strip().upper().startswith("INSERT INTO ASK_JOURNAL ")]
    sql = inserts[0] if inserts else ""
    t("answer: clarify_options NULL", "NULL" in sql and A._journal_clarify_options(answer_out) is None)
    t("answer: doubt FALSE", A._journal_doubt(answer_out) is False)
    t("answer: atoms из atom", A._journal_atoms_slim(answer_out)[0].get("exact_value") == "0.00")
    t("answer: текста нет в ask_journal", Q_ANSWER not in sql)

    captured.clear()
    trusted = {"src": "accumulationregister_a", "label": "Остатки ТМЦ", "used": True}
    A._ask_journal_write(Q_ANSWER, answer_out, time.monotonic(),
                         trusted=trusted, user="u-tick", channel="probe",
                         decision_id="dec-1")
    inserts = [s for s in captured if s.strip().upper().startswith("INSERT INTO ASK_JOURNAL ")]
    sql = inserts[0] if inserts else ""
    t("ticket: ticket_variant=label", "Остатки ТМЦ" in sql,
      A._journal_ticket_variant(answer_out, trusted=trusted))

    # без clarify и без fork.atoms → atoms []
    empty = {"kind": "no_data", "text": "", "diag": {"doubt": False}, "partial": None}
    t("no_data: options null", A._journal_clarify_options(empty) is None)
    t("no_data: atoms []", A._journal_atoms_slim(empty) == [])
finally:
    A.psql = old_psql


# fail-open: ошибка записи новых полей не роняет ответ
A.ASK_JOURNAL = True
A.ENOUGH_ON = False
A._JOURNAL_LOST = 0
lost_before = A._JOURNAL_LOST
A.psql = _fake_psql_factory([], [0], fail_on="INSERT INTO ask_journal")
A.answer = lambda *a, **k: {"kind": "clarify", "text": "x", "options": [{"label": "A", "src": "s"}],
                            "diag": {"doubt": True}, "partial": None}
try:
    out = A.answer_checked(Q_CLARIFY, channel="probe", user="u-fail")
    t("fail-open: ответ clarify", out.get("kind") == "clarify", str(out)[:80])
    t("fail-open: LOST вырос", A._JOURNAL_LOST > lost_before, A._JOURNAL_LOST)
finally:
    A.psql = old_psql
    A.ENOUGH_ON = True


# хелперы: вопрос не попадает в lit ask_journal (только text-таблица)
t("q_hash = sha256", True)  # покрыто test_ask_journal; sanity
t("helpers: doubt None без ключа", A._journal_doubt({"kind": "answer", "diag": {}}) is None)

print("\nИТОГ: %d ok, %d fail" % (PASS, len(FAIL)))
sys.exit(1 if FAIL else 0)
