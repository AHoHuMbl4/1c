#!/usr/bin/env python3
"""Тест детектора подмены метрики (serene_report.measure_caveat) — чистая функция, без БД/LLM.
Ловит числовую свёртку/приведение ТЕКСТОВОГО реквизита (номер счёта→«оборот»), но НЕ трогает
легит-агрегаты (LENGTH/COUNT/ORDER BY/GROUP BY). Схемо-типовой сигнал, без карты бизнес-терминов.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import serene_report as R  # noqa: E402

TC = {"номерсчета", "corr_account", "description", "city", "code", "inn", "swift"}
CASES = [
    ("AVG(CAST(bs.НомерСчета AS HUGEINT)) как оборот", "SELECT AVG(CAST(bs.НомерСчета AS HUGEINT)) FROM t bs", True),
    ("SUM(НомерСчета) как деньги на счетах", "SELECT SUM(НомерСчета) AS сумма FROM t", True),
    ("corr_account::bigint суммой", "SELECT sum(corr_account::bigint) FROM banks", True),
    ("AVG(LENGTH(description)) — легит длина", "SELECT AVG(LENGTH(description)) FROM banks", False),
    ("COUNT(*) — легит", "SELECT COUNT(*) FROM banks WHERE city='x'", False),
    ("ORDER BY code — легит сортировка", "SELECT description FROM banks ORDER BY code LIMIT 5", False),
    ("GROUP BY city count — легит", "SELECT city, count(*) FROM banks GROUP BY city", False),
    ("количество по классификатору (COUNT) — не ловим (нужен критик)", "SELECT count(*) FROM t WHERE vid='НалогНаПрибыль'", False),
]


def main():
    fails = 0
    for name, sql, expect in CASES:
        got = bool(R.measure_caveat(sql, TC))
        if got != expect:
            fails += 1
        print(f"  {'OK  ' if got == expect else 'FAIL ✗'}  [{'caveat' if got else 'чисто '}]  {name}")
    print(f"\nИТОГ: {'ВСЁ PASS ✅' if fails == 0 else str(fails) + ' FAIL ✗'}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
