#!/usr/bin/env python3
"""Доказуемый выбор: decision_id + сырой focus не гасит защиты (план §6, аудит §10).

Замки:
  · таблица истинности: сырой focus НЕ отключает stop2 / _checked-путь / enough;
  · валидный билет снимает одну неоднозначность (trusted);
  · used / expired / unknown / mismatch — видимая ошибка;
  · рестарт хранилища (= reset) → старый билет unknown.

Запуск: python3 ubuntu/serenedb/test_decision_id.py
Без базы, сети и модели.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ASK_TOKEN", "test")
os.environ.setdefault("EMBED_BASE_URL", "-")
os.environ.setdefault("EMBED_MODEL", "-")

import serene_ask as A  # noqa: E402

PASS, FAIL = 0, []


def t(name, cond):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name)


A.reset_decisions_for_tests()
A.RAW_FOCUS_TRUST = False

# ── таблица истинности: сырой focus не гасит три защиты ──────────────────────
t("сырой focus: guards_skip=False",
  A.guards_skip_for_choice("catalog_x", None, None) is False)
t("сырой focus: stop2_active=True",
  A.stop2_active("catalog_x", None, False, None) is True)
t("сырой measure: stop2_active=True",
  A.stop2_active(None, "Сумма", False, None) is True)
t("без выбора: stop2_active=True",
  A.stop2_active(None, None, False, None) is True)
t("no_arbiter: stop2_active=False",
  A.stop2_active(None, None, True, None) is False)

trusted_ent = {"ambiguity": "entity", "src": "catalog_x"}
trusted_meas = {"ambiguity": "measure", "src": "catalog_x", "measure": "Сумма"}
t("билет entity: guards_skip=True",
  A.guards_skip_for_choice("catalog_x", None, trusted_ent) is True)
t("билет entity: stop2_active=False",
  A.stop2_active("catalog_x", None, False, trusted_ent) is False)
t("билет measure: stop2_active=False",
  A.stop2_active(None, "Сумма", False, trusted_meas) is False)

old = A.RAW_FOCUS_TRUST
A.RAW_FOCUS_TRUST = True
t("ASK_RAW_FOCUS_TRUST=1: сырой focus гасит (эвакуация)",
  A.guards_skip_for_choice("catalog_x", None, None) is True
  and A.stop2_active("catalog_x", None, False, None) is False)
A.RAW_FOCUS_TRUST = old

# ── билеты ───────────────────────────────────────────────────────────────────
A.reset_decisions_for_tests()
opts = [
    {"src": "document_a", "label": "А", "distinct_by": "продажа", "found": 10},
    {"src": "document_b", "label": "Б", "distinct_by": "оплата", "found": 5},
]
sealed = A.seal_clarify({"kind": "clarify", "text": "что?", "options": opts},
                        "На какую сумму продали?")
ids = [o["decision_id"] for o in sealed["options"]]
t("seal: decision_id у каждого варианта",
  len(ids) == 2 and all(ids) and ids[0] != ids[1])
t("seal: id короткий для Telegram (≤64 байт)",
  all(len(i.encode("utf-8")) <= 64 for i in ids))
t("seal: ambiguity=entity",
  sealed["diag"].get("ambiguity") == "entity")

ticket, err = A.consume_decision(ids[0], "На какую сумму продали?")
t("валидный билет: ok, src из записи",
  err is None and ticket["src"] == "document_a"
  and ticket["ambiguity"] == "entity" and ticket["used"] is True)
t("валидный билет снимает одну неоднозначность (entity)",
  A.choice_proven(ticket, "entity") and not A.choice_proven(ticket, "measure"))

_, err_used = A.consume_decision(ids[0], "На какую сумму продали?")
t("повторный билет → used", err_used == "used")
t("чужой id → unknown", A.consume_decision("no-such", "На какую сумму продали?")[1] == "unknown")
t("чужой вопрос → mismatch",
  A.consume_decision(ids[1], "Другой вопрос")[1] == "mismatch")

# expired
A._DECISIONS[ids[1]]["expires_at"] = time.time() - 1
t("просроченный → expired",
  A.consume_decision(ids[1], "На какую сумму продали?")[1] == "expired")

# user mismatch
A.reset_decisions_for_tests()
sealed_u = A.seal_clarify(
    {"kind": "clarify", "options": [
        {"src": "a", "label": "A", "distinct_by": "x", "found": 1}]},
    "q", user="u1")
tid_u = sealed_u["options"][0]["decision_id"]
t("чужой user → user_mismatch",
  A.consume_decision(tid_u, "q", user="u2")[1] == "user_mismatch")
t("свой user → ok",
  A.consume_decision(tid_u, "q", user="u1")[1] is None)

# restart = empty store
A.reset_decisions_for_tests()
t("рестарт хранилища → старый билет unknown",
  A.consume_decision(ids[0], "На какую сумму продали?")[1] == "unknown")

# choice_error_response — внутренний снимок; клиенту answer_checked его не отдаёт
err_out = A.choice_error_response("used", "x")
t("снимок ошибки билета собирается (kind=choice_error)",
  err_out["kind"] == "choice_error" and err_out["error"] == "used"
  and err_out["text"] and "sources" in err_out)

A.reset_decisions_for_tests()
opts_r = [
    {"src": "document_a", "label": "Реализация (документ)", "distinct_by": "продажа", "found": 10},
    {"src": "register_a", "label": "Продажи (регистр)", "distinct_by": "итоги", "found": 5},
]
q_r = "На какую сумму продали?"
sealed_r = A.seal_clarify({"kind": "clarify", "text": "что посчитать?", "options": opts_r}, q_r)
tid_r = sealed_r["options"][0]["decision_id"]
A.consume_decision(tid_r, q_r)
out_used = A.answer_checked(q_r, decision_id=tid_r)
t("used → свежий clarify, не choice_error",
  out_used.get("kind") == "clarify" and len(out_used.get("options") or []) == 2)
txt_u = (out_used.get("text") or "") + str(out_used.get("diag") and "")
t("used → в text нет тикет/decision_id",
  "тикет" not in (out_used.get("text") or "").lower()
  and "decision_id" not in (out_used.get("text") or "").lower())
t("used → ticket_reissued=used",
  (out_used.get("diag") or {}).get("ticket_reissued") == "used")
labs = {o.get("label") for o in out_used["options"]}
t("used → те же подписи",
  "Реализация (документ)" in labs and "Продажи (регистр)" in labs)

core_calls = []
def _core_stub(*a, **k):
    core_calls.append(1)
    return {"kind": "no_data", "text": "общий путь", "options": [], "diag": {}, "partial": None}
old_core = A._answer_checked_core
A._answer_checked_core = _core_stub
out_unk = A.answer_checked("вопрос", decision_id="нет-такого-билета")
t("unknown → общий путь, не choice_error",
  out_unk.get("kind") != "choice_error" and out_unk.get("kind") == "no_data")
t("unknown → без слов про билеты",
  "тикет" not in (out_unk.get("text") or "").lower())
t("unknown → core звался", len(core_calls) == 1)
A._answer_checked_core = old_core

# measure options
A.reset_decisions_for_tests()
sealed_m = A.seal_clarify(
    {"kind": "clarify", "options": [
        {"src": "d", "measure": "Сумма", "label": "Сумма", "entity_label": "Док"},
        {"src": "d", "measure": "СуммаНДС", "label": "НДС", "entity_label": "Док"},
    ]}, "q")
t("measure clarify: ambiguity=measure",
  sealed_m["diag"]["ambiguity"] == "measure")
tm, em = A.consume_decision(sealed_m["options"][0]["decision_id"], "q")
t("measure билет несёт measure",
  em is None and tm["measure"] == "Сумма" and tm["ambiguity"] == "measure")

print("\n%d проверок пройдено" % PASS)
if FAIL:
    print("ПРОВАЛЕНО %d: %s" % (len(FAIL), "; ".join(FAIL)))
    raise SystemExit(1)
