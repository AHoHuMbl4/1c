#!/usr/bin/env python3
"""Замок чистки webchat-конверта в мосту ask_1c (план web1 v2).

Оффлайн: без сети и без сервиса ответов. Стиль — как test_mcp_ask.py.
Запуск:
    /opt/openclaw-mcp/venv/bin/python ubuntu/openclaw/test_mcp_ask_envelope.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ASK_URL", "http://127.0.0.1:1/ask")
os.environ.setdefault("ASK_TOKEN", "test")

import mcp_ask as M  # noqa: E402
import mcp_ask_pending as P  # noqa: E402

P.reset_pending_clarify_for_tests()

PASS, FAIL = 0, []


def t(name, cond):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name)


def _env(tail, history_body="User: раньше\n\nAssistant: ок 🙂\n"):
    """Канон конверта движка: HISTORY-строка, история, CURRENT-строка, хвост."""
    return (
        "[Chat messages since your last reply - for context]\n"
        + history_body
        + "[Current message - respond to this]\n"
        + tail
    )


strip = M.strip_webchat_question_envelope

# ---------------------------------------------- C: unit strip
canon = _env("User: за вчера. общая")
t("C-а канон → хвост без User:",
  strip(canon) == "за вчера. общая")

multi = _env("User: строка1\nстрока2")
t("C-б многострочный хвост сохраняет \\n",
  strip(multi) == "строка1\nстрока2")

no_user = _env("просто хвост")
t("C-в хвост без User: как есть",
  strip(no_user) == "просто хвост")

plain = "  вопрос с пробелами\n\nи пустыми  "
plain_out = strip(plain)
t("C-г без маркеров == исходнику", plain_out == plain)
t("C-г без маркеров is исходник", plain_out is plain)

quoted = "человек написал [Current message - respond to this] внутри"
t("C-д цитата CURRENT внутри строки → нетронут",
  strip(quoted) is quoted)

cur_only = (
    "какой-то текст\n"
    "[Current message - respond to this]\n"
    "User: q"
)
t("C-д2 CURRENT без HISTORY → нетронут",
  strip(cur_only) is cur_only)

mid_hist = (
    "кто-то сказал [Chat messages since your last reply - for context] в чате\n"
    "[Current message - respond to this]\n"
    "User: q"
)
t("C-д3 HISTORY substring mid-line → нетронут",
  strip(mid_hist) is mid_hist)

empty_tail = (
    "[Chat messages since your last reply - for context]\n"
    "User: old\n"
    "[Current message - respond to this]\n"
)
t("C-е пустой хвост → исходник",
  strip(empty_tail) is empty_tail)

user_only = _env("User:")
t("C-е2 хвост User: → исходник",
  strip(user_only) is user_only)

same_line = (
    "[Chat messages since your last reply - for context]\n"
    "[Current message - respond to this] User: q"
)
t("C-f same-line CURRENT → нетронут",
  strip(same_line) is same_line)

crlf = (
    "[Chat messages since your last reply - for context]\r\n"
    "User: hist\r\n"
    "[Current message - respond to this]\r\n"
    "User: чистый\r\n"
)
t("C-g CRLF + HISTORY префикс → хвост",
  strip(crlf) == "чистый")

t("C-h User:\\t и USER:",
  strip(_env("User:\t q")) == "q"
  and strip(_env("USER: q")) == "q")

# ---------------------------------------------- P: pending + ask_1c
# label короткий: len(norm) < 8 → contain по грязному конверту не срабатывает
LABEL_SHORT = "Альфа"  # norm len 5
assert len(P.norm_clarify_key(LABEL_SHORT)) < 8
TID_P1 = "tidEnvP1"
Q_P1 = "сколько всего по альфе"
opts_p1 = [
    {"src": "a", "label": LABEL_SHORT, "found": 2, "decision_id": TID_P1},
    {"src": "b", "label": "Бета-длинная", "found": 1, "decision_id": "tidEnvP1b"},
]
env_p1 = _env("User: " + LABEL_SHORT)
t("P-1' strip(env)==label", strip(env_p1) == LABEL_SHORT)

P.reset_pending_clarify_for_tests()
calls = []


def _ask_rec(q, focus=None, measure=None, context=None, prior=None,
             decision_id=None, user=None, memory=None, channel=None, rid=None):
    calls.append({"q": q, "decision_id": decision_id, "user": user,
                  "focus": focus, "measure": measure})
    if decision_id == TID_P1:
        return {"kind": "answer", "text": "ответ альфа", "sources": []}
    return {"kind": "clarify", "text": "Что?", "options": opts_p1}


saved = M._ask
M._ask = _ask_rec
M.ask_1c(Q_P1, user="u-p1", channel="webchat")
calls.clear()
out_p1 = M.ask_1c(env_p1, user="u-p1", channel="webchat")
t("P-1' конверт+label → question=Q locked + decision_id",
  "ответ альфа" in out_p1
  and any(c.get("q") == Q_P1 and c.get("decision_id") == TID_P1 for c in calls))

# P-2 первый конверт → clarify, pending.question == чистый хвост
P.reset_pending_clarify_for_tests()
calls.clear()
TAIL_P2 = "за вчера. общая"
opts_p2 = [
    {"src": "a", "label": "ВариантА", "found": 3, "decision_id": "tidP2a"},
    {"src": "b", "label": "ВариантБ", "found": 2, "decision_id": "tidP2b"},
]


def _ask_p2(q, focus=None, measure=None, context=None, prior=None,
            decision_id=None, user=None, memory=None, channel=None, rid=None):
    calls.append({"q": q, "decision_id": decision_id})
    return {"kind": "clarify", "text": "Что показать?", "options": opts_p2}


M._ask = _ask_p2
env_p2 = _env("User: " + TAIL_P2)
out_p2 = M.ask_1c(env_p2, user="u-p2", channel="webchat")
pend = P.get_pending("u-p2", "webchat") if hasattr(P, "get_pending") else None
# get_pending может отсутствовать — читаем через внутреннее хранилище
if pend is None:
    key = P.pending_key("u-p2", "webchat")
    with P._PENDING_LOCK:
        pend = P._PENDING_CLARIFY.get(key)
t("P-2 clarify + pending.question == чистый хвост",
  "[CLARIFICATION NEEDED]" in out_p2
  and pend is not None
  and pend.get("question") == TAIL_P2
  and calls and calls[0]["q"] == TAIL_P2)

# P-3 повтор конверта с тем же хвостом → short_circuit, один _ask
calls.clear()
out_p3 = M.ask_1c(env_p2, user="u-p2", channel="webchat")
t("P-3 повтор конверта → short_circuit, один _ask",
  "tidP2a" in out_p3 and len(calls) == 0)

# P-4 петля 5 конвертов → эскалация + refuse
P.reset_pending_clarify_for_tests()
calls.clear()
M._ask = _ask_p2
M.ask_1c(env_p2, user="u-p4", channel="webchat")
esc_hit = refuse_hit = False
for _ in range(8):
    o = M.ask_1c(env_p2, user="u-p4", channel="webchat")
    if "не распознан" in o:
        esc_hit = True
    if "unresolved after repeated" in o or ("[NO DATA]" in o and "Clarification" in o):
        refuse_hit = True
        break
t("P-4 петля 5 конвертов → эскалация+refuse",
  esc_hit and refuse_hit and len(calls) == 1)

# P-5 конверт с новым вопросом → pending снят
P.reset_pending_clarify_for_tests()
calls.clear()
M._ask = _ask_p2
M.ask_1c(env_p2, user="u-p5", channel="webchat")
env_new = _env("User: совсем другой вопрос")
calls.clear()
M.ask_1c(env_new, user="u-p5", channel="webchat")
key5 = P.pending_key("u-p5", "webchat")
with P._PENDING_LOCK:
    pend5 = P._PENDING_CLARIFY.get(key5)
t("P-5 новый вопрос в конверте → pending на новый хвост",
  pend5 is not None and pend5.get("question") == "совсем другой вопрос"
  and calls and calls[0]["q"] == "совсем другой вопрос")

# P-6 конверт + явный decision_id → чистый question + тот же tid
P.reset_pending_clarify_for_tests()
calls.clear()
TID_P6 = "tidP6x"
opts_p6 = [
    {"src": "a", "label": "Гаmma", "found": 1, "decision_id": TID_P6},
]


def _ask_p6(q, focus=None, measure=None, context=None, prior=None,
            decision_id=None, user=None, memory=None, channel=None, rid=None):
    calls.append({"q": q, "decision_id": decision_id})
    if decision_id == TID_P6:
        return {"kind": "answer", "text": "по билету", "sources": []}
    return {"kind": "clarify", "text": "?", "options": opts_p6}


M._ask = _ask_p6
TAIL_P6 = "вопрос с билетом"
env_p6 = _env("User: " + TAIL_P6)
out_p6 = M.ask_1c(env_p6, decision_id=TID_P6, user="u-p6", channel="webchat")
t("P-6 конверт+decision_id → чистый q + tid",
  "по билету" in out_p6
  and any(c.get("q") == TAIL_P6 and c.get("decision_id") == TID_P6 for c in calls))

# ---------------------------------------------- T: telegram / no-op
P.reset_pending_clarify_for_tests()
calls.clear()
tg_q = "сколько продали вчера"


def _ask_tg(q, focus=None, measure=None, context=None, prior=None,
            decision_id=None, user=None, memory=None, channel=None, rid=None):
    calls.append({"q": q, "focus": focus, "measure": measure})
    return {"kind": "answer", "text": "42", "sources": []}


M._ask = _ask_tg
M.ask_1c(tg_q, user="u-tg", channel="telegram")
t("T-1 telegram == тот же текст",
  calls and calls[0]["q"] == tg_q)
t("T-1 telegram is тот же объект",
  calls and calls[0]["q"] is tg_q)

# T-2 no-op через apply_pending_before_ask без pending
P.reset_pending_clarify_for_tests()
calls.clear()
plain_t2 = "обычный вопрос без конверта"
M.ask_1c(plain_t2, user="u-t2", channel="webchat")
t("T-2 no-op без pending → q как есть",
  calls and calls[0]["q"] is plain_t2)

# ---------------------------------------------- F: focus
P.reset_pending_clarify_for_tests()
calls.clear()
focus_env = _env("User: фокус-сущность")
M.ask_1c("q", focus=focus_env, user="u-f1", channel="webchat")
t("F-1 focus с конвертом → чистка",
  calls and calls[0].get("focus") == "фокус-сущность")

P.reset_pending_clarify_for_tests()
calls.clear()
focus_plain = "просто фокус"
M.ask_1c("q", focus=focus_plain, user="u-f2", channel="webchat")
t("F-2 focus без маркера is",
  calls and calls[0].get("focus") is focus_plain)

M._ask = saved
P.reset_pending_clarify_for_tests()

print("\n%d проверок пройдено" % PASS)
if FAIL:
    print("ПРОВАЛЕНО %d: %s" % (len(FAIL), "; ".join(FAIL)))
    raise SystemExit(1)
