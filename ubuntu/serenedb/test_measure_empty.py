#!/usr/bin/env python3
"""S1-некролог: мерный пивот пустышки (legacy-механизм) снесён.

Новый тракт одного пути: пустое окно закрывается period_empty-ответом
(build_period_empty_answer), меры — _settle_measure/count_defer; всюду-0
гашение (measure_row_all_zero / alive_measure_names /
filter_dead_measure_alts) и пивоты (format/build_measure_empty_pivot,
measure_asked_explicitly) были только-legacy (W1-z16, SR1/SR2-red:
в новом тракте 0 вызовов). Замок сторожит отсутствие этих символов.
Запуск: python3 ubuntu/serenedb/test_measure_empty.py
"""
import sys

sys.path.insert(0, "/srv/1c/ubuntu/serenedb")

from ask import _bootstrap  # noqa: E402

ns = _bootstrap.load_all()

GONE = [
    "measure_row_all_zero",
    "alive_measure_names",
    "filter_dead_measure_alts",
    "measure_asked_explicitly",
    "format_measure_empty_pivot",
    "build_measure_empty_pivot",
]

PASS, FAIL = 0, []
for _name in GONE:
    if _name not in ns:
        PASS += 1
        print("ok  - снесено и не возвращается:", _name)
    else:
        FAIL.append(_name)
        print("FAIL- мерный пивот жив:", _name)

if "build_period_empty_answer" in ns:
    PASS += 1
    print("ok  - пустое окно закрыто period_empty-ответом")
else:
    FAIL.append("build_period_empty_answer")
    print("FAIL- period_empty-ответ отсутствует")

print("PASS", PASS, "FAIL", len(FAIL))
sys.exit(1 if FAIL else 0)
