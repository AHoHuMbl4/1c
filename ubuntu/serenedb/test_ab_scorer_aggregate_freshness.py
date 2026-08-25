#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Оффлайн-замок: aggregate_totals_in_text не путает минуты свежести с итогом."""

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

STALE = (
    "\n\n⚠ Данные могли устареть: последнее обновление из 1С было 1439 мин назад."
)
NO_DATA = "Таких данных нет."


def main():
    text_fresh = NO_DATA + STALE
    t("свежесть 1439 мин — не итог",
      not S.aggregate_totals_in_text(text_fresh), text_fresh[-60:])
    t("kind_row_ok: no_data + свежесть",
      S.kind_row_ok({"kind": "no_data", "text": text_fresh}))

    text_total = NO_DATA + " Итого 1 500."
    t("группированный итог — брак",
      S.aggregate_totals_in_text(text_total), text_total)
    t("дробный итог — брак",
      S.aggregate_totals_in_text(NO_DATA + " сумма 1500.00"), "1500.00")
    t("kind_row_ok: no_data + итог",
      not S.kind_row_ok({"kind": "no_data", "text": text_total}))

    text_both = NO_DATA + " Итого 1 236 800." + STALE
    t("свежесть + итог одновременно — брак",
      S.aggregate_totals_in_text(text_both), text_both[-80:])
    t("kind_row_ok: оба сразу",
      not S.kind_row_ok({"kind": "no_data", "text": text_both}))

    t("голое 1439 без единицы времени — не ловим размером",
      not S.aggregate_totals_in_text(NO_DATA + " код 1439."), "порог n≥1000 снят")
    t("год 2024 в тексте — не итог",
      not S.aggregate_totals_in_text(NO_DATA + " за 2024 год."))

    print("\nИТОГ:", "ok — все %d проверок прошли" % PASS if not FAIL
          else "FAIL — %d из %d: %s" % (len(FAIL), PASS + len(FAIL), ", ".join(FAIL)))
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
