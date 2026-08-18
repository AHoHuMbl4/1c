#!/usr/bin/env python3
"""Оффлайн-проба моста: БЕЗ сервиса ответов, БЕЗ сети, БЕЗ модели.

Мост — часть шага 7: это последняя точка, где внутреннее становится клиентским. Своей
пробы у него не было, а живой прогон 04.08 показал, зачем она нужна: боту уходили
внутренние счётчики под своими именами (`reranked_of=1502`), и человек услышал «всего в
базе 1 502 документа» — числа законные, сказанное про них ложное.

Запуск тем же питоном, которым мост исполняется (в системном `mcp` нет):
    /opt/openclaw-mcp/venv/bin/python ubuntu/openclaw/test_mcp_ask.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ASK_URL", "http://127.0.0.1:1/ask")
os.environ.setdefault("ASK_TOKEN", "test")

import mcp_ask as M  # noqa: E402

PASS, FAIL = 0, []


def t(name, cond):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name)


# ---------------------------------------------- F251: бюджет ≠ потеря счёта
budget_only = {"reranked_of": 1502, "reranked": 60,
               "intent_assumed": "period.from=2026-08-12"}
out_budget = M._with_partial("ответ", {"partial": budget_only})
t("PARTIAL: бюджет и assumed-only — без HINT и без блока",
  out_budget == "ответ")
t("PARTIAL: бюджет-only — нет «Not everything was taken into account»",
  "Not everything was taken into account" not in out_budget
  and "учли не всё" not in out_budget.lower())

loss = {"coverage_missing": 104, "undated_excluded": 3}
named = M._named_partial(loss)
t("PARTIAL: потеря счёта — произносимые имена",
  named == {"rows_missing_from_search": 104,
            "records_without_date_excluded": 3})
t("PARTIAL: числа потери не меняются — гейт сверяет их с ответом инструмента",
  set(named.values()) == {104, 3})

unknown = M._named_partial({"coverage_missing": 7, "нечто_новое": 42})
t("PARTIAL: неизвестный ключ числом наружу не идёт",
  42 not in unknown.values() and "нечто_новое" not in unknown)
t("PARTIAL: но и не пропадает молча — сказано, что отсечка была (п. 13)",
  unknown.get("other_limits_applied") == 1)

t("PARTIAL: пустая пометка не рождает блок",
  M._named_partial({}) == {} and M._named_partial(None) == {})
t("PARTIAL: значения None отбрасываются (их нечего говорить)",
  M._named_partial({"coverage_missing": None}) == {})

block = M._kv_block("PARTIAL", M._named_partial(loss))
t("PARTIAL: блок машинный, без прозы, с обоими числами",
  block.startswith("PARTIAL:") and "rows_missing_from_search=104" in block
  and "records_without_date_excluded=3" in block)
t("PARTIAL: целое печатается без хвоста .0 — иначе гейт сверяет «3.0» с «3»",
  "=3\n" in block + "\n")

out_loss = M._with_partial("ответ", {"partial": loss})
t("PARTIAL: потеря счёта — HINT и блок приписываются к ответу",
  out_loss.startswith("ответ")
  and "Not everything was taken into account" in out_loss
  and "PARTIAL:" in out_loss)
t("PARTIAL: без пометки ответ не трогается",
  M._with_partial("ответ", {"partial": None}) == "ответ")

# kind=no_data: маркер — префикс к text сервиса, как у verify-plugin, не замена
saved_ask = M._ask
M._ask = lambda *a, **k: {"kind": "no_data",
                          "text": "проверенный ответ дать невозможно"}
out_nd = M.ask_1c("q")
t("no_data + непустой text: маркер как префикс",
  out_nd.startswith("[NO DATA]") and "проверенный ответ дать невозможно" in out_nd)
t("no_data + непустой text: не голая формула there is no such data",
  "there is no such data" not in out_nd.lower())
M._ask = lambda *a, **k: {"kind": "no_data", "text": ""}
out_empty = M.ask_1c("q")
t("no_data + пустой text: формула на месте",
  "there is no such data" in out_empty.lower())
M._ask = saved_ask


# ---------------------------------------------- атом / figures (план §5)
atom = {
    "operation": "sum",
    "exact_value": 1310413.93,
    "display_value": "1310413.93",
    "measure_label": "Реализация ТМЦ",
    "unit_or_currency": "unknown",
    "period": {"from": "2025-07-01", "to": "2025-07-31", "origin": "prior"},
    "proof_status": "computed",
    "src": "document_реализациятмц",  # внутреннее — проверка: в текст бота не попадает
}
roles = M._atom_roles_block(atom)
t("figures: роли — operation/value/measure_label, не плоский sum=",
  "operation=sum" in roles and "value=1310413.93" in roles
  and "measure_label=Реализация ТМЦ" in roles
  and "sum=" not in roles)
t("figures: src атома в ролях нет",
  "document_реализациятмц" not in roles and "src=" not in roles)

saved_ask = M._ask
M._ask = lambda *a, **k: {
    "kind": "figures", "text": "refuse",
    "figures": {"sum": 1310413.93, "count": 19, "label": "X"},
    "atom": atom, "atoms": [atom],
}
out_fig = M.ask_1c("q")
t("figures: маркер FIGURES на месте (протокол цел)",
  "[FIGURES]" in out_fig)
t("figures: семантические роли, не key=value из figures",
  "measure_label=Реализация ТМЦ" in out_fig
  and "value=1310413.93" in out_fig
  and "sum=1310413.93" not in out_fig
  and "count=19" not in out_fig)
t("figures: ATOM_JSON есть, внутреннего src нет",
  "ATOM_JSON:" in out_fig and "document_реализациятмц" not in out_fig)
t("figures: плоский figures без атома не разворачивается в KV",
  True)  # ветка ниже
M._ask = lambda *a, **k: {"kind": "figures", "text": "refuse",
                          "figures": {"sum": 99, "count": 1}}
out_legacy = M.ask_1c("q")
t("figures без атома: нет плоского sum=/count= (аудит §8)",
  "sum=99" not in out_legacy and "count=1" not in out_legacy
  and "[FIGURES]" in out_legacy)
M._ask = saved_ask


# ---------------------------------------------- decision_id / presentation (план §6)
opts_d = [
    {"src": "document_a", "label": "Реализация", "distinct_by": "продажа", "found": 3,
     "decision_id": "abc123XYZ"},
    {"src": "document_b", "label": "Оплата", "distinct_by": "оплата", "found": 2,
     "decision_id": "def456UVW"},
]
saved_ask = M._ask
M._ask = lambda *a, **k: {"kind": "clarify", "text": "Что посчитать?", "options": opts_d}
out_c = M.ask_1c("q")
t("clarify: decision_id в OPTIONS и ATOM_JSON",
  "decision_id=abc123XYZ" in out_c and "ATOM_JSON:" in out_c)
t("clarify: PRESENTATION_JSON с callback=decision_id",
  "PRESENTATION_JSON:" in out_c and "abc123XYZ" in out_c)
pres = M._clarify_presentation(opts_d)
t("presentation: кнопки label+callback, ≤64 байт",
  pres is not None
  and pres["blocks"][0]["buttons"][0]["label"] == "Реализация"
  and pres["blocks"][0]["buttons"][0]["action"]["value"] == "ask1c:abc123XYZ")
calls_ce = []
def _ce_then_clarify(q, focus=None, measure=None, context=None, prior=None,
                     decision_id=None, user=None, memory=None, channel=None, rid=None):
    calls_ce.append(decision_id)
    if decision_id:
        return {"kind": "choice_error", "text": "Срок выбора истёк. тикет.",
                "error": "expired"}
    return {"kind": "clarify", "text": "Что посчитать?", "options": opts_d}
M._ask = _ce_then_clarify
out_ce = M.ask_1c("q", decision_id="expired-tid")
t("choice_error: повтор без билета → обычное уточнение",
  "[CLARIFICATION NEEDED]" in out_ce and "Что посчитать?" in out_ce
  and "[CHOICE ERROR]" not in out_ce
  and "тикет" not in out_ce.lower()
  and calls_ce[0] == "expired-tid" and calls_ce[1] is None)
M._ask = lambda *a, **k: {"kind": "choice_error", "text": "Срок выбора истёк. тикет.",
                          "error": "expired"}
out_ce2 = M.ask_1c("q", decision_id="x")
t("choice_error повтор не помог → без кухни протокола",
  "[CHOICE ERROR]" not in out_ce2 and "тикет" not in out_ce2.lower()
  and "[CLARIFICATION NEEDED]" in out_ce2)
# _ask пробрасывает decision_id
seen = {}
def capture(q, focus=None, measure=None, context=None, prior=None,
            decision_id=None, user=None, memory=None, channel=None, rid=None):
    seen.update(decision_id=decision_id, user=user, q=q, memory=memory,
                channel=channel)
    return {"kind": "answer", "text": "ok", "sources": []}
M._ask = capture
M.ask_1c("вопрос", decision_id="tid1", user="u9")
t("_ask пробрасывает decision_id и user",
  seen.get("decision_id") == "tid1" and seen.get("user") == "u9")
M.ask_1c("запомни так", decision_id="tid1", user="u9")
t("фраза без поля memory не ставит remember",
  seen.get("memory") is None and seen.get("q") == "запомни так")
M.ask_1c("сколько продали, запомни так", user="u9")
t("хвост без поля не снимается",
  seen.get("memory") is None and seen.get("q") == "сколько продали, запомни так")
M.ask_1c("вопрос", memory="forget", user="u9")
t("поле memory пробрасывается", seen.get("memory") == "forget")
M.ask_1c("вопрос", user="telegram:111", channel="telegram")
t("channel пробрасывается",
  seen.get("channel") == "telegram" and seen.get("user") == "telegram:111")
seen_rid = {}
def cap_rid(*a, rid=None, **k):
    seen_rid["rid"] = rid
    return {"kind": "answer", "text": "ok", "sources": []}
M._ask = cap_rid
M.ask_1c("q", rid="rid1deadbeef")
t("rid пробрасывается в _ask", seen_rid.get("rid") == "rid1deadbeef")
M._ask = saved_ask

t("_choice_prompt: вопрос и подпись одной строкой",
  M._choice_prompt("сколько продали вчера всего", "Реализация ТМЦ (документ)")
  == "сколько продали вчера всего: Реализация ТМЦ (документ)?")
opts_chip = [
    {"src": "document_a", "label": "Реализация ТМЦ (документ)", "hint": "отгрузки",
     "distinct_by": "", "found": 3, "decision_id": "abc123XYZ"},
    {"src": "document_b", "label": "Реализация ТМЦ (регистр)", "hint": "итоги",
     "distinct_by": "", "found": 2, "decision_id": "def456UVW"},
]
_saved_chip = M._ask
M._ask = lambda *a, **k: {"kind": "clarify", "text":
    "1. сколько продали вчера всего: Реализация ТМЦ (документ)? — отгрузки\n"
    "2. сколько продали вчера всего: Реализация ТМЦ (регистр)? — итоги",
    "options": opts_chip}
out_chip = M.ask_1c("сколько продали вчера всего")
t("clarify OPTIONS: строка-вопрос чипа, focus=подпись, hint рядом",
  "сколько продали вчера всего: Реализация ТМЦ (документ)?" in out_chip
  and "focus=Реализация ТМЦ (документ)" in out_chip
  and " — отгрузки" in out_chip
  and "focus=Реализация ТМЦ (регистр)" in out_chip)
M._ask = _saved_chip

print("\n%d проверок пройдено" % PASS)
if FAIL:
    print("ПРОВАЛЕНО %d: %s" % (len(FAIL), "; ".join(FAIL)))
    raise SystemExit(1)
