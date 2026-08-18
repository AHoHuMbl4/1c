#!/usr/bin/env python3
"""Величина-пустышка и «позавчера»: опции без всюду-0, пивот, compose без {count}.

Числа в замках — снимок корпуса okna 18.08 (корпус сам под следствием в другом треде).
Запуск: python3 ubuntu/serenedb/test_measure_empty.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ASK_TOKEN", "test")
os.environ.setdefault("EMBED_BASE_URL", "-")
os.environ.setdefault("EMBED_MODEL", "-")

import serene_ask as A  # noqa: E402

PASS, FAIL = 0, []

# Снимок корпуса okna 18.08, accumulationregister_реализациятмц, день 17.08.
CORPUS_VSEGO = 766578.68
CORPUS_COUNT = 331


def t(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + str(detail)[:200]) if detail else "")


# --- (а) всюду-0 не в опциях ---
totals = [
    ("Сумма", 0.0, 0.0, 0.0),
    ("Всего", CORPUS_VSEGO, 12000.0, 10.0),
    ("СуммаБезНДС", 638815.56, 10000.0, 8.0),
    ("Количество", 40.0, 4.0, 1.0),
]
t("row all-zero: Сумма", A.measure_row_all_zero(totals[0]))
t("row alive: Всего", not A.measure_row_all_zero(totals[1]))
t("alive names без Сумма",
  A.alive_measure_names(totals) == ["Всего", "СуммаБезНДС", "Количество"])
alts = ["Сумма", "Всего", "СуммаБезНДС", "Количество", "Себестоимость"]
kept = A.filter_dead_measure_alts(alts, totals)
t("опции: Сумма вычеркнута", "Сумма" not in kept, kept)
t("опции: Всего на месте", "Всего" in kept, kept)
t("пустотелый totals не режет опции",
  A.filter_dead_measure_alts(alts, []) == alts)

# --- явный vs молчаливый ---
t("билет → явно",
  A.measure_asked_explicitly("", "Сумма", "rerank", measure_pick="сумма"))
t("слово exact → явно",
  A.measure_asked_explicitly("сумма", "Сумма", "exact"))
t("rerank без слова → не явно",
  not A.measure_asked_explicitly("", "Сумма", "rerank"))
t("rerank со словом → не явно (how)",
  not A.measure_asked_explicitly("сумма", "Сумма", "rerank"))

# --- пивот ---
txt = A.format_measure_empty_pivot(
    "Сумма", "Сумма",
    [("Всего", CORPUS_VSEGO, 12000.0, 10.0)],
    {"Сумма": "Сумма", "Всего": "Всего"},
    "сколько продали вчера всего?")
t("пивот: нет значений по Сумма", "Сумма" in txt and "нет значений" in txt, txt)
t("пивот: Всего и число по корпусу",
  "Всего" in txt and "766" in txt.replace("\u00a0", "").replace(" ", ""), txt)
t("пивот: не refuse", "проверенную информацию" not in txt.lower(), txt)

A.measure_aliases_of = lambda src: {}
A._table_label = lambda src: "Движения реализации с себестоимостью"
A.kind_word = lambda src: "регистр накопления"
out = A.build_measure_empty_pivot(
    "сколько продали вчера всего?", "Сумма",
    "accumulationregister_реализациятмц",
    [("Всего", CORPUS_VSEGO, 12000.0, 10.0)],
    None, {}, 0.0,
    {"want": "sum", "period": {"from": "2026-08-17", "to": "2026-08-17"}},
    how="exact", measure_pick="сумма")
t("пивот kind=answer", out.get("kind") == "answer", out.get("kind"))
t("пивот figures.sum по корпусу",
  out.get("figures", {}).get("sum") == CORPUS_VSEGO, out.get("figures"))
t("пивот gate_ok", (out.get("diag") or {}).get("gate_ok") is True)
t("пивот diag.measure_empty_pivot",
  (out.get("diag") or {}).get("measure_empty_pivot") == "Сумма")
t("пивот без {count}", "{count}" not in (out.get("text") or ""), out.get("text"))

# --- compose: sum=0.0 не выпускает {count} (дыра 5ca1b66) ---
SENT = {}


def _fake_chat(messages, temperature=0, max_tokens=900):
    SENT["sys"] = messages[0]["content"]
    SENT["body"] = messages[1]["content"]
    return '{"text": "ок", "ask": null, "claims": {}}'


_real_chat = A.ds_chat
A.ds_chat = _fake_chat
rows = [["", "", "0.00", "2026-08-17", "", "строка"]]
agg0 = {
    "count": CORPUS_COUNT, "count_amount": CORPUS_COUNT,
    "sum": 0.0, "min": 0.0, "max": 0.0, "avg": 0.0,
    "date_min": "2026-08-17", "date_max": "2026-08-17",
    "src": "accumulationregister_реализациятмц",
    "measure": "Сумма", "folders": 0, "grain": "row", "form": "number",
}
A.compose("сколько продали вчера всего?", rows, agg0, money=True, slot_mode="sum")
t("compose sum=0: {count} нет в COMPUTED",
  "-> {count}" not in SENT.get("body", "")
  and "number of records is {count}" not in SENT.get("body", ""),
  SENT.get("body", "")[-400:])
t("compose sum=0: {count} нет в sys",
  "{count}" not in SENT.get("sys", ""))
A.ds_chat = _real_chat

# --- дефект 2: date-only и пустая вилка ---
by = {
    "informationregister_курсывалют": 2,
    "accumulationregister_реализациятмц": 0,
}
kind_ok = ["accumulationregister_реализациятмц", "document_реализациятмц"]
kept, dropped = A.date_only_kind_filter(by, "", kind_ok)
t("date-only: курсы выпали",
  "informationregister_курсывалют" in dropped
  and "informationregister_курсывалют" not in kept, (kept, dropped))
t("date-only: продажи в kept",
  "accumulationregister_реализациятмц" in kept)
kept2, dropped2 = A.date_only_kind_filter(by, "ts_phrase('x')", kind_ok)
t("date-only: непустой match не режет",
  kept2 == by and dropped2 == [])

srcs = ["accumulationregister_реализациятмц", "document_реализациятмц"]
preds = ["doc_date >= '2026-08-16'",
         "doc_date < ('2026-08-16'::date + INTERVAL 1 day)"]
t("пустой период: вилка не режется",
  A.keep_empty_period_opts(srcs, {s: 0 for s in srcs}, preds) == srcs)
t("кто-то жив: только живые",
  A.keep_empty_period_opts(
      srcs + ["informationregister_курсывалют"],
      {"accumulationregister_реализациятмц": 331,
       "document_реализациятмц": 0,
       "informationregister_курсывалют": 2},
      preds) == ["accumulationregister_реализациятмц",
                 "informationregister_курсывалют"])
t("counted is None: не режем",
  A.keep_empty_period_opts(srcs, None, preds) == srcs)

print("\nИТОГ:", "ok — все %d проверок прошли" % PASS if not FAIL
      else "FAIL — %d из %d: %s" % (len(FAIL), PASS + len(FAIL), ", ".join(FAIL)))
sys.exit(1 if FAIL else 0)
