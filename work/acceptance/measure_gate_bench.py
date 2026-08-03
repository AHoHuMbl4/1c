#!/usr/bin/env python3
"""ПРИБОР: как часто срабатывает ГЕЙТ ВЕЛИЧИНЫ (задача 16, право на ответ «б»).

Правило: если слову вопроса отвечают несколько величин сущности И их итоги разные —
величина не выбирается молча, система спрашивает. Здесь меряется цена правила: на скольких
вопросах набора оно сработало бы и на скольких промолчало.

Считает база, прибор бесплатный и детерминированный: ни модели ответов, ни эмбеддера.
Зовутся настоящие функции продукта (`measure_choice`, `measure_ambiguous`, `totals_of`).

🔴 ЧЕСТНЫЕ ГРАНИЦЫ.
1. В бою слово величины называет `parse_intent` (модель) — ОДНО слово. Здесь перебираются
   ВСЕ слова вопроса, поэтому число срабатываний — ВЕРХНЯЯ оценка: в бою гейт сработает не
   чаще. Печатается и слово, на котором сработало, — видно, могла ли модель его назвать.
2. Сущность берётся ЭТАЛОННАЯ (из набора), а не выбранная моделью: цена правила меряется
   там, где сущность верна, иначе к цене примешивается чужая ошибка.
3. Итоги считаются без условий вопроса (период, контрагент): условия сужают строки, но не
   меняют того, РАЗНЫЕ ли величины между собой.

Использование:
    SERENEDB_DSN_RO=… PGPASSWORD=… python3 work/acceptance/measure_gate_bench.py [набор]
"""
import importlib
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SET_FILE = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "docs/ACCEPTANCE_UT.md")

sys.path.insert(0, os.path.join(ROOT, "ubuntu/serenedb"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.argv = [sys.argv[0], SET_FILE]

A = importlib.import_module("serene_ask")
B = importlib.import_module("entity_choice_bench")


def main():
    pairs = B.pairs(SET_FILE)
    fired, silent, rows = 0, 0, []
    for q, want in pairs:
        names = A.measures_of(want)
        if not names:
            silent += 1
            continue
        hit = None
        for w in re.split(r"[^0-9A-Za-zА-Яа-яЁё]+", q):
            if not w:
                continue
            _got, alts, how = A.measure_choice(names, w)
            if how != 'ask':
                continue
            tot = {m: v for m, v, _mx, _mn in A.totals_of(want, "", [], alts)}
            if A.measure_ambiguous(alts, tot):
                hit = (w, alts, tot)
                break
        if hit:
            fired += 1
            rows.append((q, want, hit))
        else:
            silent += 1
    for q, want, (w, alts, tot) in rows:
        print("СРАБОТАЛ  %-44s слово «%s» → %d величин" % (q[:44], w, len(alts)))
        for m in alts:
            print("            %-34s %s" % (m, tot.get(m)))
    # РАЗБИВКА ПО СЛОВУ — она и есть ответ на «верхняя оценка чего именно». Служебное слово
    # («и», «в», «за») оказывается подстрокой многих имён, но величиной его не назовёт ни
    # `parse_intent`, ни человек: в бою на таком слове гейт не сработает. Разделение делает
    # не порог по длине, а сам перечень: он показан целиком, и читать его должен человек.
    by_word = {}
    for _q, _w, (w, _a, _t) in rows:
        by_word[w] = by_word.get(w, 0) + 1
    print("\nсработал на словах: " + ", ".join(
        "«%s» %d" % (w, n) for w, n in sorted(by_word.items(), key=lambda kv: -kv[1])))
    print("вопросов с эталонной сущностью: %d" % (fired + silent))
    print("гейт величины сработал бы (верхняя оценка): %d" % fired)
    print("гейт промолчал бы:                          %d" % silent)
    return 0


if __name__ == "__main__":
    sys.exit(main())
