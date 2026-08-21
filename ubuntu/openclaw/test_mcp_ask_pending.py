#!/usr/bin/env python3
"""Замки текстового выбора в мосте (петля OWUI 21.08). Без сети и модели.

Запуск:
    /opt/openclaw-mcp/venv/bin/python ubuntu/openclaw/test_mcp_ask_pending.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("MCP_PENDING_CLARIFY_LOOP_N", "5")

import mcp_ask_pending as P  # noqa: E402

PASS, FAIL = 0, []


def t(name, cond):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name)


P.reset_pending_clarify_for_tests()

OPTS = [
    {"src": "a", "label": "Номенклатура перемещения ТМЦ", "found": 3,
     "decision_id": "tidAAA111"},
    {"src": "b", "label": "Остатки на складах", "found": 2,
     "decision_id": "tidBBB222"},
]
Q = "список остатков на складе по названию sku. топ 10"
USER, CH = "web:u1", "webchat"

data0 = {"kind": "clarify", "text": "Что показать?", "options": OPTS}
snap = P.store_pending(USER, CH, Q, data0, bump_streak=True)
t("store: pending появился", snap is not None and snap["streak"] == 1)
t("store: fingerprint стабилен", bool(snap and snap.get("fp")))

# ── текстовый выбор без билета → резолв ──────────────────────────────────────
r = P.apply_pending_before_ask(
    "Номенклатура перемещения ТМЦ", "", "", "", USER, CH)
t("текст-выбор без билета → decision_id подставлен",
  r["decision_id"] == "tidAAA111" and r["short_circuit"] is None
  and not r["refuse"])
t("текст-выбор → исходный question восстановлен",
  r["question"] == Q)

r_foc = P.apply_pending_before_ask(
    "что-то ещё", "Номенклатура перемещения ТМЦ", "", "", USER, CH)
t("focus=подпись → тот же резолв",
  r_foc["decision_id"] == "tidAAA111" and r_foc["question"] == Q)

# ── повтор вопроса → те же опции и билеты ────────────────────────────────────
P.reset_pending_clarify_for_tests()
P.store_pending(USER, CH, Q, data0, bump_streak=True)
r2 = P.apply_pending_before_ask(Q, "", "", "", USER, CH)
t("повтор вопроса → short_circuit, не новый круг",
  r2["short_circuit"] is not None and r2["decision_id"] == "")
ids2 = [(o.get("decision_id") or "") for o in (r2["short_circuit"] or {}).get("options") or []]
t("повтор вопроса → те же билеты",
  ids2 == ["tidAAA111", "tidBBB222"])

# ── петля из 5 одинаковых → эскалация, затем отказ ───────────────────────────
P.reset_pending_clarify_for_tests()
P.store_pending(USER, CH, Q, data0, bump_streak=True)  # streak=1
escalated = False
refused = False
last_text = ""
for i in range(8):
    r = P.apply_pending_before_ask(Q, "", "", "", USER, CH)
    if r.get("refuse"):
        refused = True
        break
    sc = r.get("short_circuit") or {}
    last_text = sc.get("text") or ""
    if last_text == P.CLARIFY_LOOP_TEXT:
        escalated = True
t("петля: эскалация текстом «выбор не распознан…»",
  escalated and "не распознан" in P.CLARIFY_LOOP_TEXT)
t("петля из одинаковых вызовов → не бесконечность (refuse)",
  refused)
t("после refuse pending снят",
  P.get_pending(USER, CH) is None)

# ── чужой/новый вопрос снимает замок, билет не подставляет ───────────────────
P.reset_pending_clarify_for_tests()
P.store_pending(USER, CH, Q, data0, bump_streak=True)
r_new = P.apply_pending_before_ask("сколько продали вчера", "", "", "", USER, CH)
t("новый вопрос → pending снят, без decision_id",
  r_new["decision_id"] == "" and r_new["short_circuit"] is None
  and P.get_pending(USER, CH) is None)

# ── явный decision_id не переписывается ──────────────────────────────────────
P.reset_pending_clarify_for_tests()
P.store_pending(USER, CH, Q, data0, bump_streak=True)
r_did = P.apply_pending_before_ask(Q, "", "", "explicitTID", USER, CH)
t("явный decision_id не переписывается мостом",
  r_did["decision_id"] == "explicitTID" and r_did["short_circuit"] is None)

# ── match: нормализация пробелов / номер ─────────────────────────────────────
t("match: нормализация пробелов",
  P.match_pending_option("Номенклатура  перемещения ТМЦ", OPTS)["decision_id"]
  == "tidAAA111")
t("match: номер 2",
  P.match_pending_option("2", OPTS)["decision_id"] == "tidBBB222")
t("match: чужая строка → None",
  P.match_pending_option("совсем другое", OPTS) is None)

# ── TTL ──────────────────────────────────────────────────────────────────────
P.reset_pending_clarify_for_tests()
P.store_pending(USER, CH, Q, data0, bump_streak=True)
with P._PENDING_LOCK:
    key = P.pending_key(USER, CH)
    P._PENDING_CLARIFY[key]["at"] = 0  # протух
t("TTL истёк → pending нет", P.get_pending(USER, CH) is None)

print("\n%d проверок пройдено" % PASS)
if FAIL:
    print("ПРОВАЛЕНО %d: %s" % (len(FAIL), "; ".join(FAIL)))
    raise SystemExit(1)
