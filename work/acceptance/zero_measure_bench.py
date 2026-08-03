#!/usr/bin/env python3
"""ПРИБОР: тождественно нулевая величина — «незаполненное поле» против «ответа ноль».

Зачем. `[замер 03.08]` На вопросе «Сколько НДС в наших продажах?» система выбрала регистр
выручки и величину `НДСРегл`, сложила её по 3 878 строкам и ответила **0 ₽** при эталоне
3 125 757,80. Величина у сущности есть и заполнена во всех строках — но нулём. Ноль
неотличим от посчитанного ответа, поэтому это худший исход (п. 21).

Что меряет прибор — три вещи, все детерминированные и бесплатные:

  1. **Масштаб явления по базе:** сколько пар «сущность-величина» тождественно нулевые
     (`sum = max = min = 0`). Признак — тождество, а не порог: константы, подобранной под
     нашу базу, здесь нет.
  2. **Есть ли чем заменить:** у скольких сущностей при нулевой величине остаются живые —
     то есть правило может предложить выбор, а не просто отказать. Где живых нет, правило
     НЕ срабатывает и поведение остаётся прежним; это тоже число, а не предположение.
  3. **Разбор известных случаев:** срабатывает ли признак там, где ошиблись (вопрос 4), и
     МОЛЧИТ ли там, где ответ был верным (вопросы 1, 3, 9). Второе важнее первого:
     правило, гасящее верные ответы, хуже отсутствующего.

🔴 ЧЕСТНЫЕ ГРАНИЦЫ. Прибор меряет ПРИЗНАК, а не продукт целиком: какую величину назовёт
модель на живом вопросе, здесь не проверяется — это стоит денег и меряется приёмкой.
Проверяется ровно то, что новое правило считает своим: тождественный ноль и наличие замены.

🔴 ИМЁН КОНКРЕТНОЙ БАЗЫ В ЭТОМ ФАЙЛЕ НЕТ. Разбираемые случаи лежат отдельным файлом данных
(`zero_measure_cases.tsv`, путь переопределяется `ZERO_MEASURE_CASES`) — на другой базе
подставляется другой файл, а прибор остаётся тем же. Пункты 1 и 2 имён не требуют вовсе:
они считаются по всей базе, какой бы она ни была.

Использование:
    SERENEDB_DSN_RO=… python3 work/acceptance/zero_measure_bench.py [файл_случаев]
"""
import importlib
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "ubuntu/serenedb"))
A = importlib.import_module("serene_ask")

CASES_FILE = (sys.argv[1] if len(sys.argv) > 1
              else os.environ.get("ZERO_MEASURE_CASES")
              or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "zero_measure_cases.tsv"))


def load_cases(path):
    """Случаи из файла данных: сущность, величина, ждём(1/0), пояснение."""
    out = []
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            p = line.split("\t")
            if len(p) < 3:
                continue
            out.append((p[3] if len(p) > 3 else "", p[0].strip(), p[1].strip(),
                        p[2].strip() == "1"))
    return out


def dead(src, measure):
    """Тождественный ноль по ВСЕЙ сущности: `sum = max = min = 0` при непустом счёте."""
    t = A.totals_of(src, "", [], [measure])
    if not t:
        return None                     # величины нет или значений нет вовсе — другой класс
    _m, s, mx, mn = t[0]
    return s == 0 and mx == 0 and mn == 0


def main():
    print("=" * 78)
    print("1. МАСШТАБ ПО БАЗЕ")
    r = A.psql(
        # 🔴 `map_entries` — ШТАТНЫЙ способ разложить карту, а не два `unnest` подряд.
        # Параллельные `unnest(map_keys(...))` и `unnest(map_values(...))` держатся на
        # негласном допущении, что оба списка идут в одном порядке; `map_entries` отдаёт
        # struct(key, value), где пара связана по построению. Проверено в доках SereneDB
        # (Sql › Functions › Map) и на нашей сборке 26.07.3; числа прибора не изменились —
        # 1928 / 454 / 539 обоими способами `[замер 03.08]`.
        "WITH m AS (SELECT src_table, unnest(map_entries(nums)) e"
        "           FROM search_corpus WHERE nums IS NOT NULL),"
        "     u AS (SELECT src_table, struct_extract(e, 'key') k,"
        "                  struct_extract(e, 'value') v FROM m),"
        "     g AS (SELECT src_table, k, min(v) mn, max(v) mx FROM u GROUP BY 1,2)"
        " SELECT count(*), count(*) FILTER (WHERE mn=0 AND mx=0),"
        "        count(DISTINCT src_table),"
        "        count(DISTINCT src_table) FILTER (WHERE mn=0 AND mx=0) FROM g")
    pairs, zero_pairs, ents, ents_zero = (int(x) for x in r[0][:4])
    print("   пар «сущность-величина»            %6d" % pairs)
    print("   из них тождественно нулевых        %6d  (%.1f %%)"
          % (zero_pairs, 100.0 * zero_pairs / max(pairs, 1)))
    print("   сущностей с величинами             %6d" % ents)
    print("   из них хотя бы с одной нулевой     %6d  (%.1f %%)"
          % (ents_zero, 100.0 * ents_zero / max(ents, 1)))

    print("\n2. ЕСТЬ ЛИ ЧЕМ ЗАМЕНИТЬ (правило молчит, если живых величин не осталось)")
    r2 = A.psql(
        # 🔴 `map_entries` — ШТАТНЫЙ способ разложить карту, а не два `unnest` подряд.
        # Параллельные `unnest(map_keys(...))` и `unnest(map_values(...))` держатся на
        # негласном допущении, что оба списка идут в одном порядке; `map_entries` отдаёт
        # struct(key, value), где пара связана по построению. Проверено в доках SereneDB
        # (Sql › Functions › Map) и на нашей сборке 26.07.3; числа прибора не изменились —
        # 1928 / 454 / 539 обоими способами `[замер 03.08]`.
        "WITH m AS (SELECT src_table, unnest(map_entries(nums)) e"
        "           FROM search_corpus WHERE nums IS NOT NULL),"
        "     u AS (SELECT src_table, struct_extract(e, 'key') k,"
        "                  struct_extract(e, 'value') v FROM m),"
        "     g AS (SELECT src_table, k, min(v) mn, max(v) mx FROM u GROUP BY 1,2),"
        "     ent AS (SELECT src_table, count(*) FILTER (WHERE mn=0 AND mx=0) z,"
        "                  count(*) FILTER (WHERE NOT (mn=0 AND mx=0)) a"
        "           FROM g GROUP BY 1)"
        " SELECT count(*) FILTER (WHERE z>0 AND a>0), count(*) FILTER (WHERE z>0 AND a=0) FROM ent")
    with_alt, no_alt = (int(x) for x in r2[0][:2])
    print("   сущностей, где правило предложит выбор   %6d" % with_alt)
    print("   сущностей, где предложить нечего         %6d  (поведение прежнее)" % no_alt)

    cases = load_cases(CASES_FILE)
    print("\n3. ИЗВЕСТНЫЕ СЛУЧАИ (%s, случаев %d)"
          % (os.path.basename(CASES_FILE), len(cases)))
    if not cases:
        print("   файла случаев нет — пункты 1 и 2 всё равно посчитаны")
        return 0
    bad = 0
    for title, src, measure, want in cases:
        got = dead(src, measure)
        ok = (got is want)
        if not ok:
            bad += 1
        print("   %-5s %-62s признак=%s ждали=%s"
              % ("OK" if ok else "🔴", title, got, want))
    print("\n%s" % ("ИТОГ: все случаи как ожидалось" if not bad
                    else "🔴 ИТОГ: расхождений %d" % bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
