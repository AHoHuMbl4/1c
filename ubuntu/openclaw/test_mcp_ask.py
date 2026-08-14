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

print("\n%d проверок пройдено" % PASS)
if FAIL:
    print("ПРОВАЛЕНО %d: %s" % (len(FAIL), "; ".join(FAIL)))
    raise SystemExit(1)
