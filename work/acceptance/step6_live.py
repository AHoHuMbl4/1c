#!/usr/bin/env python3
"""Живой замер ШАГА 6 «формулировка»: что модель на самом деле присылает и что из этого
доходит до человека.

Оффлайн-проба (`ubuntu/serenedb/test_compose.py`) отвечает на вопрос «верно ли код
обрабатывает ответ модели». На вопрос «а что модель присылает на самом деле» она ответить
не может по устройству: там модель подменена. Этот прибор зовёт НАСТОЯЩУЮ модель
настоящим промтом `ANSWER_SYS` на настоящих числах — и считает ровно то, ради чего шаг 6
существует:

  • сколько ответов пришло в разбираемой обёртке (а не прозой и не обрубком);
  • сколько раз модель оставила МЕСТО под число вместо того, чтобы набрать число самой
    (это и есть работающий калькулятор: число ставит код);
  • сколько раз она всё-таки набрала посчитанное число цифрами — и справляется ли с этим
    вторая попытка;
  • сколько мест осталось незаполненными, то есть заготовка поехала бы человеку.

Цитата из строки (номер документа, дата, имя) рукописью НЕ считается: промт её прямо
разрешает, а `min`/`max` по построению совпадают со значением какой-то строки.

Базы не трогает: числа заданы, к движку прибор не ходит. Цена — 8 вызовов модели за
прогон плюс по одному на каждую вторую попытку.

Запуск (ключ модели лежит в env сервиса отчётов):
  set -a; . /etc/1c-serene-ask-ut_test.env; . /etc/1c-embed.env; . /etc/1c-mcp-reports.env; set +a
  python3 work/acceptance/step6_live.py
"""
import io
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "ubuntu", "serenedb"))
os.environ.setdefault("ASK_TOKEN", "test")

import serene_ask as A  # noqa: E402

# 🔴 ИМЁН КОНКРЕТНОЙ БАЗЫ В КОДЕ НЕТ. Сущность, величины, стороны и сами вопросы живут в
# `step6-cases.json` рядом — по той же причине, по какой вопросы `golden.sh` живут в файле:
# они привязаны к конкретной базе, а продукт обязан работать на любой (п. 9 TARGET.md).
# Путь перекрывается через STEP6_CASES; целевое состояние (п. 15) — набор строится из
# самой базы клиента при установке.
CASES_FILE = os.environ.get(
    "STEP6_CASES", os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "step6-cases.json"))
with io.open(CASES_FILE, encoding="utf-8") as fh:
    _CFG = json.load(fh)

AGG = _CFG["agg"]
TOTALS = [tuple(t) for t in _CFG["totals"]]
COV = _CFG["coverage"]
# Строка корпуса в том виде, в каком её отдаёт psql: код читает r[2] (величина),
# r[3] (дата) и r[5] (текст строки).
ROWS = [["", "", a, d, "", txt] for a, d, txt in _CFG["rows"]]
CASES = [(q, dict(opts)) for q, opts in _CFG["cases"]]

NUM = re.compile(r"\d[\d  .,]*\d|\d")


def classify(text, agg, rows):
    """Числа, набранные моделью, по классам: посчитанное от руки / цитата / выдумка.

    Разбор нужен, чтобы замер не врал в обе стороны. Номер документа и дата ИЗ СТРОКИ —
    цитата, промт её разрешает, и считать её нарушением значит объявить дефектом верное
    поведение. Посчитанное число, набранное цифрами, — то самое, ради чего заведён
    калькулятор. Выдумка — работа гейта, здесь она только называется.
    """
    computed = {round(float(agg[k]), 2) for k in ("sum", "min", "max", "avg")
                if agg.get(k) is not None} | {float(agg["count"])}
    in_rows = set()
    for r in rows:
        in_rows |= A._norm_numbers(r[5]) | A._norm_numbers(r[3])
        try:
            in_rows.add(round(float(r[2]), 2))
        except (TypeError, ValueError):
            pass
    by_hand, quoted, invented = [], [], []
    for tok in NUM.findall(text):
        readings = A._readings(tok)
        if not readings:
            continue
        if readings & in_rows:
            quoted.append(tok)          # цитата сильнее: max равен значению строки
        elif readings & computed:
            by_hand.append(tok)
        else:
            invented.append(tok)
    return by_hand, quoted, invented


def defects(q, extra, text, ask, agg, cov_slots):
    """ВЕСЬ договор шага 6 по одному вопросу — списком изъянов, а не одним признаком.

    Мерило владельца 04.08: «0 ошибок стабильно в 100 % вопросов». Значит считать надо не
    «сколько раз сработал признак», а «сколько вопросов прошли БЕЗ ЕДИНОГО изъяна».
    Проверяется тем же кодом, что стоит на боевом пути, — иначе замер мерил бы не то, что
    работает.
    """
    out = []
    if not (text or "").strip() and not (ask or "").strip():
        out.append("обёртка не разобрана")
    by_hand, _, invented = classify(text, agg, ROWS)
    if by_hand:
        out.append("посчитанное набрано цифрами: %s" % ", ".join(by_hand))
    filled, bad = A._fill_figures(text, agg, TOTALS, True, cov_slots)
    out += A.formulation_flaws(filled, bad)
    miss = A.asked_figure_missing(filled, agg, extra.get("want"), True,
                                  extra.get("folders", 0))
    if miss:
        out.append(miss)
    leak = A.prompt_leak(filled, A.OUR_PROMPTS)
    if leak:
        out.append("утечка инструкции: %s" % leak)
    # Белый список — тот же, что в `answer()`: итоги по именам, числа переписи и число
    # отброшенных групп. Расходись он с боевым, прибор мерил бы не боевой путь.
    extra_vals = [x for t in TOTALS for x in t[1:]]
    if cov_slots:
        extra_vals += [cov_slots["in_1c"], cov_slots["in_search"], cov_slots["missing"]]
    if agg.get("folders"):
        extra_vals.append(agg["folders"])
    ok_nums, bad_nums = A.gate(filled, ROWS, agg, extra_vals)
    if not ok_nums:
        out.append("гейт: числа вне данных %s" % bad_nums[:3])
    if invented:
        out.append("выдуманные числа: %s" % ", ".join(invented))
    return out, filled, by_hand


def main():
    total = len(CASES)
    parsed = placeheld = wrote_own = left_over = empty = 0
    retry_ok = retry_failed = 0
    clean = 0
    for q, extra in CASES:
        folders = extra.get("folders", 0)
        agg = dict(AGG, folders=folders) if folders else dict(AGG)
        cov = COV if extra.get("cov") else None
        cov_slots = ({"in_1c": cov["in_1c"], "in_search": cov["in_search"],
                      "missing": cov["missing"]} if cov else None)
        try:
            raw = A.compose(q, ROWS, agg, totals=TOTALS, coverage=cov,
                            measure_used=agg.get("measure"), folders=folders)
        except Exception as e:                      # noqa: BLE001
            print("── %s\n   СБОЙ вызова модели: %s: %s" % (q, type(e).__name__, e))
            continue
        text, _ = A._split_answer(raw)
        ask = A._ask_back(raw)
        if text.strip() or ask.strip():
            parsed += 1
        slots = A.SLOT.findall(text)
        if slots:
            placeheld += 1
        flaws, filled, by_hand = defects(q, extra, text, ask, agg, cov_slots)
        _, quoted, invented = classify(text, agg, ROWS)
        if by_hand:
            wrote_own += 1
        if any("незаполненное" in f or "нераспознанное" in f for f in flaws):
            left_over += 1
        if any("пустая" in f for f in flaws):
            empty += 1
        if not flaws:
            clean += 1

        print("── %s" % q)
        print("   мест: %-2d от руки: %-2d цитат: %-2d выдумано: %-2d изъянов: %s"
              % (len(slots), len(by_hand), len(quoted), len(invented),
                 "; ".join(str(f) for f in flaws) or "нет"))
        print("   → %s" % " ".join(filled.split())[:300])
        if ask:
            print("   ? %s" % " ".join(ask.split())[:200])
        if by_hand:
            # 🔴 МЕРЯЕТСЯ И ВТОРАЯ ПОПЫТКА, а не только факт находки. Отказ безопасен, но
            # задача проекта — отдать ответ (п. 21): если вторая попытка с названной
            # причиной ставит место, механизм чинит; если нет — числа уходят структурой,
            # и это тоже надо знать числом, а не предполагать.
            reasons = A.copied_figures(text, agg, ROWS)
            raw2 = A.compose(q, ROWS, agg, corrections=reasons[:3], totals=TOTALS,
                             coverage=cov, measure_used=agg.get("measure"),
                             folders=folders)
            text2, _ = A._split_answer(raw2)
            again = A.copied_figures(text2, agg, ROWS)
            filled2, bad2 = A._fill_figures(text2, agg, TOTALS, True, cov_slots)
            if again or A.formulation_flaws(filled2, bad2):
                retry_failed += 1
                print("   вторая попытка НЕ справилась: %s"
                      % ("; ".join(again) or "изъян формулировки"))
            else:
                retry_ok += 1
                print("   вторая попытка справилась → %s"
                      % " ".join(filled2.split())[:200])

    print("\nПО ШАГУ 6 (из %d вопросов):" % total)
    print("  🔴 БЕЗ ЕДИНОГО ИЗЪЯНА .................. %d из %d" % (clean, total))
    print("  обёртка разобрана ...................... %d" % parsed)
    print("  оставила МЕСТО под число ............... %d" % placeheld)
    print("  🔴 посчитанное число набрано цифрами .... %d" % wrote_own)
    print("  🔴 заготовка поехала бы человеку ........ %d" % left_over)
    print("  🔴 пустая формулировка .................. %d" % empty)
    if wrote_own:
        print("  из них вторая попытка справилась ....... %d, не справилась ... %d"
              % (retry_ok, retry_failed))


if __name__ == "__main__":
    main()
