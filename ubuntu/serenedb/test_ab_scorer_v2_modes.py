#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Оффлайн-замки для ubuntu/serenedb/ab_scorer.py (v2: digits/kind/clarify/name).

Цель: проверить разбор TSV и чистые функции вердиктов без вызовов /ask и psql.
"""

import os
import sys


PASS, FAIL = 0, []


def t(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + str(detail)[:160]) if detail else "")


ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import ab_scorer as S  # noqa: E402


def mk_out(kind, text="", diag=None, figures=None, totals=None, options=None):
    return {
        "kind": kind,
        "text": text,
        "diag": diag or {},
        "figures": figures or {},
        "totals": totals or {},
        "options": options or [],
    }


def test_load_gold():
    path = os.path.join(ROOT, "ab-gold-okna.tsv")
    rows = S.load_gold(path)
    t("tsv v2: 25 строк", len(rows) == 25, len(rows))
    modes = {r.get("mode") for r in rows}
    t("tsv v2: есть digits/kind/clarify/name", {"digits", "kind", "clarify", "name"} <= modes, modes)


def test_digits():
    ok, defect, fact = S.score_digits("123.45", mk_out("answer", text="Итого 123.45"))
    t("digits: совпадение в text", ok, (defect, fact))

    ok, defect, fact = S.score_digits("123.45", mk_out("figures", text="", figures={"sum": 123.45}))
    t("digits: совпадение в figures", ok, (defect, fact))

    ok, defect, _fact = S.score_digits("123.45", mk_out("answer", text="Итого 999"))
    t("digits: несовпадение => FAIL", not ok and defect == "число не сошлось", (defect,))


def test_kind():
    sql_period = "FROM accumulationregister_реализациятмц doc_date"
    ok, defect, fact = S.score_kind(sql_period, "0", mk_out("figures", text=""))
    t("kind: период+0 => figures", ok, (defect, fact))

    ok, defect, _fact = S.score_kind(sql_period, "0", mk_out("no_data", text=""))
    t("kind: wrong d.kind => FAIL", (not ok and defect == "kind не тот"), defect)

    sql_stock = "SELECT 0"
    ok, defect, _fact = S.score_kind(sql_stock, "0", mk_out("no_data", text="нет данных"))
    t("kind: stock+0 => no_data", ok, (defect, _fact))

    q_diag = "почему в воскресенье продаж ноль, это сбой?"
    ok, defect, _fact = S.score_kind(
        sql_period, "0", mk_out("answer", text="продаж не было"), question=q_diag)
    t("kind: диагностика нуля => answer OK", ok, (defect, _fact))
    ok, defect, _fact = S.score_kind(
        sql_period, "0", mk_out("no_data", text="нет данных"), question=q_diag)
    t("kind: диагностика нуля => no_data OK", ok, (defect, _fact))
    ok, defect, _fact = S.score_kind(
        sql_period, "0", mk_out("figures", text="0"), question=q_diag)
    t("kind: диагностика нуля => figures FAIL", not ok, (defect, _fact))


def test_truth_empty_as_zero():
    # без psql: проверяем только ветку empty_as_zero на пустом результате через mock нельзя
    # здесь — контракт score_digits("0", ...) и gold coalesce в TSV
    ok, defect, fact = S.score_digits("0", mk_out("answer", text="Итого 0"))
    t("digits: эталон 0 (воскресенье без продаж) считается", ok, (defect, fact))
    rows = S.load_gold(os.path.join(ROOT, "ab-gold-okna.tsv"))
    sun = [r for r in rows if "воскресенье" in r["q"] and r["mode"] == "digits"]
    t("gold #16: coalesce в SQL воскресенья",
      bool(sun) and "coalesce(" in (sun[0].get("sql") or "").lower(),
      sun[0].get("sql")[:80] if sun else "missing")


def test_clarify():
    out = mk_out(
        "clarify",
        text="уточнение",
        options=[
            {"label": "вариант 0", "decision_id": "d1"},
            {"label": "вариант 1", "decision_id": "d2"},
        ],
    )
    ok, defect, _fact = S.score_clarify("0", out)
    t("clarify: kind=clarify и needle найден в options", ok, defect)

    ok, defect, _fact = S.score_clarify("0", mk_out("answer", text="итог"))
    t("clarify: wrong kind => FAIL", (not ok and defect == "kind не тот"), defect)


def test_name():
    ok, defect, _fact = S.score_name("Alice|123.45", mk_out("answer", text="Лидер Alice, сумма 123.45"))
    t("name: top-1 name+number", ok, defect)

    want = "Ivan = 10 | Petr = 20"
    out = mk_out("answer", text="Топ: Ivan = 10 | Petr = 20")
    ok, defect, _fact = S.score_name(want, out)
    t("name: top-3: несколько пар", ok, defect)

    out = mk_out("answer", text="Топ: Ivan = 10")
    ok, defect, _fact = S.score_name(want, out)
    t("name: missing name/number => FAIL", (not ok and defect in ("имя не найдено", "число не сошлось")), defect)


def test_choose_clarify_option():
    opts = [
        {"label": "Алиса 1", "decision_id": "d1"},
        {"label": "Боб 2", "decision_id": "d2"},
    ]
    chosen = S.choose_clarify_option(opts, "Алиса")
    t("choose_clarify_option: находит по подстроке", chosen and chosen.get("decision_id") == "d1", chosen)


def _clients_menu():
    """Живой кейс слепоты токен-матча: «клиентов» → «Клиент Банк»."""
    return [
        {
            "label": "Правила Обмена Клиент Банк",
            "hint": "записей: 10",
            "decision_id": "d_bank",
        },
        {
            "label": "Контрагенты",
            "hint": "Контроль сроков оплаты | НДС контрагента",
            "decision_id": "d_contr",
        },
        {
            "label": "Физические Лица",
            "hint": "сотрудники",
            "decision_id": "d_fl",
        },
    ]


def test_click_llm_modes():
    q = "сколько у нас всего клиентов сейчас"
    opts = _clients_menu()
    tokens_pick = S.choose_click_option(opts, q)
    t("tokens baseline: клиенты → Клиент Банк (слепота)",
      tokens_pick and tokens_pick.get("decision_id") == "d_bank",
      tokens_pick)

    # (а) LLM вернула валидный индекс → выбран он
    seen = {"n": 0, "prompt": "", "etalon_in_prompt": False}

    def transport_ok(prompt):
        seen["n"] += 1
        seen["prompt"] = prompt
        # эталон не должен попасть в промт
        if "ЭТАЛОН_СЕКРЕТ_999" in prompt or "999001" in prompt:
            seen["etalon_in_prompt"] = True
        return "1"

    chosen, src = S.choose_click_option_llm(
        opts, q, transport=transport_ok,
        etalon="ЭТАЛОН_СЕКРЕТ_999=999001",
        environ={"AB_CLICK_LLM": "1"})
    t("llm (а): валидный индекс → Контрагенты",
      chosen and chosen.get("decision_id") == "d_contr" and src == "llm",
      (chosen, src))
    t("llm (а): transport вызван", seen["n"] == 1, seen["n"])
    fact = S.format_click_fact_label(chosen, src)
    t("llm (а): fact с пометкой llm",
      fact.startswith("Контрагенты") and "(llm)" in fact, fact)

    # (б) LLM таймаут/мусор → fallback токен-матч
    def transport_junk(_prompt):
        return "не знаю, может контрагенты?"

    chosen_b, src_b = S.choose_click_option_llm(
        opts, q, transport=transport_junk, environ={"AB_CLICK_LLM": "1"})
    t("llm (б): мусор → tokens + Клиент Банк",
      src_b == "tokens" and chosen_b and chosen_b.get("decision_id") == "d_bank",
      (chosen_b, src_b))

    def transport_timeout(_prompt):
        raise TimeoutError("simulated")

    chosen_t, src_t = S.choose_click_option_llm(
        opts, q, transport=transport_timeout, environ={"AB_CLICK_LLM": "1"})
    t("llm (б): таймаут → tokens",
      src_t == "tokens" and chosen_t and chosen_t.get("decision_id") == "d_bank",
      (chosen_t, src_t))

    # (в) AB_CLICK_LLM=0 → токен-матч, transport не зовётся
    seen_off = {"n": 0}

    def transport_must_not(_prompt):
        seen_off["n"] += 1
        return "1"

    chosen_off, src_off = S.choose_click_option_llm(
        opts, q, transport=transport_must_not,
        environ={"AB_CLICK_LLM": "0"})
    t("llm (в): AB_CLICK_LLM=0 → tokens",
      src_off == "tokens" and chosen_off
      and chosen_off.get("decision_id") == "d_bank",
      (chosen_off, src_off))
    t("llm (в): transport не вызван", seen_off["n"] == 0, seen_off["n"])

    # (г) LLM-путь не трогает эталон (промт без эталона; параметр ignored)
    t("llm (г): эталон не в промте",
      not seen["etalon_in_prompt"]
      and "ЭТАЛОН_СЕКРЕТ_999" not in seen["prompt"]
      and "999001" not in seen["prompt"],
      seen["prompt"][:120])
    # промт несёт вопрос и подписи, не эталон
    t("llm (г): промт содержит вопрос и опции",
      "клиентов" in seen["prompt"]
      and "Контрагенты" in seen["prompt"]
      and "0. Правила Обмена Клиент Банк" in seen["prompt"],
      seen["prompt"][:200])


def main():
    test_load_gold()
    test_digits()
    test_kind()
    test_truth_empty_as_zero()
    test_clarify()
    test_name()
    test_choose_clarify_option()
    test_click_llm_modes()
    print("\nИТОГ:", "ok — все %d проверок прошли" % PASS if not FAIL
          else "FAIL — %d из %d: %s" % (len(FAIL), PASS + len(FAIL), ", ".join(FAIL)))
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()

