#!/usr/bin/env python3
"""ПРИБОР ШАГА 5 («СЧЁТ»): считает ли база то множество, которое ей дали, и всё ли оно.

Шаг 5 пайплайна — единственное место, где появляются числа ответа: `count/sum/min/max/avg`
по ВСЕМУ подходящему множеству, без `LIMIT`. Всё остальное их только переносит: модель
ставит место (`{total}`), а код подставляет посчитанное. Значит ошибка шага 5 —
это неверное число в ответе, и оно неотличимо от верного ни для человека, ни для гейта:
гейт сверяет ответ С ТЕМ ЖЕ agg, то есть своё же неверное число подтвердит.

Отсюда устройство прибора: он проверяет шаг 5 НЕ ИМ САМИМ, а независимым пересчётом другой
формулой, и проверяет инварианты, верные на любой базе.

Что меряется (каждое — числом, без модели и без денег):

  1. **Пересчёт независимой формулой.** `aggregate()` берёт величину через
     `map_extract(nums, 'имя')[1]`; прибор пересчитывает те же строки через развёртку карты
     (`unnest(map_entries(nums))`) — другой путь исполнения, другая ветка движка. Числа
     сходятся до последнего знака; расхождение — находка.
  2. **Инварианты арифметики.** `count >= count_amount`, `min <= max`, среднее посчитано по
     строкам СО ЗНАЧЕНИЕМ (`avg = sum / count_amount`), а не по всем.
  3. **«Нечего считать» против «посчитано и вышло ноль».** Множество, в котором величины
     нет ни у одной строки, даёт ОТСУТСТВИЕ числа, а не 0. Ноль неотличим от
     ответа (п. 21: неверный ответ хуже отказа), и страж тождественного нуля этот случай
     не видит — он смотрит на `totals_of`, а тот при нуле строк со значением молчит.
  4. **Паритет множеств: посчитано = показано.** Строки, которые уходят модели
     (`rows_of`), и строки, по которым посчитан итог (`aggregate`), — ОДНО И ТО ЖЕ
     множество. Разошлись — модель видит записи, которых нет в счёте, и цитирует из них
     число, которое гейт пропустит: оно ведь честно лежит в показанной строке.
  5. **Детерминированность.** Один и тот же вопрос к неизменным данным даёт один
     и тот же ответ (п. 3 контракта). Проверяется повтором.
  6. **Цена отказа от `LIMIT`.** Прибор считает, насколько итог по ВСЕМУ множеству
     отличается от итога по показанным строкам. Это не проверка, а замер: он показывает,
     что было бы, считай мы по выборке, как чанковый RAG.

🔴 ИМЁН КОНКРЕТНОЙ БАЗЫ ЗДЕСЬ НЕТ. Пары «сущность — величина» берутся ИЗ ДАННЫХ (самые
крупные по числу строк), поэтому на чужой базе прибор меряет её же, без правки.

Использование:
    SERENEDB_DSN_RO='host=… dbname=…' python3 work/acceptance/step5_bench.py [сколько_пар]

Код возврата: 0 — все проверки прошли, 1 — есть провалы.
"""
import importlib
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "ubuntu/serenedb"))
A = importlib.import_module("serene_ask")

PAIRS = int(sys.argv[1]) if len(sys.argv) > 1 else 20


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def pairs_from_data(n):
    """Пары «сущность — величина» ИЗ ДАННЫХ: самые крупные по числу строк.

    Крупные берутся не ради красоты: накопленная ошибка сложения и расхождение выборки с
    целым видны тем лучше, чем больше слагаемых.
    """
    rs = A.psql(
        "SELECT c.src_table, u.k, count(*) "
        "FROM %s c, unnest(map_keys(c.nums)) AS u(k) "
        "WHERE c.nums IS NOT NULL "
        "GROUP BY 1, 2 ORDER BY 3 DESC, 1, 2 LIMIT %d" % (A.CORPUS, n))
    return [(r[0], r[1], int(r[2])) for r in rs if r and r[0]]


def independent(pairs):
    """Пересчёт ДРУГОЙ формулой — одним запросом на все пары, а не запросом на пару.

    `aggregate()` достаёт величину точечно (`map_extract`), здесь карта РАЗВОРАЧИВАЕТСЯ и
    величина отбирается по имени ключа. Путь исполнения другой, результат — тот же.
    Папки исключаются тем же признаком платформы, что и в счёте, — иначе сравнивались бы
    разные множества и расхождение означало бы только это.
    """
    if not pairs:
        return {}
    nf = "NOT coalesce(map_extract_value(flags, 'IsFolder'), false)"
    # Сложение — в той же точной арифметике, что и в шаге 5 (`DECIMAL`): иначе прибор
    # ловил бы не ошибку счёта, а невоспроизводимость DOUBLE, ради устранения которой шаг 5
    # на DECIMAL и переведён. Независимость прибора — в СПОСОБЕ ДОБЫЧИ величины (развёртка
    # карты против точечного `map_extract`), а не в типе накопления.
    q = " UNION ALL ".join(
        "SELECT %s AS t, %s AS m, count(*) AS n, "
        "       sum(e.value), min(e.value), max(e.value), count(e.value) "
        "FROM %s c LEFT JOIN (SELECT 1) ON TRUE, "
        "     LATERAL (SELECT TRY_CAST(max(x.value) AS DECIMAL(38,10)) AS value "
        "              FROM unnest(map_entries(c.nums)) AS u(x) WHERE x.key = %s) e "
        "WHERE c.src_table = %s AND %s"
        % (A.lit(t), A.lit(m), A.CORPUS, A.lit(m), A.lit(t), nf)
        for t, m, _n in pairs)
    out = {}
    for r in A.psql(q):
        out[(r[0], r[1])] = {"count": int(r[2]), "sum": _f(r[3]), "min": _f(r[4]),
                             "max": _f(r[5]), "count_amount": int(r[6])}
    return out


def main():
    print("ПРИБОР ШАГА 5 — счёт по всему множеству")
    print("база: %s" % A.DSN)
    pairs = pairs_from_data(PAIRS)
    print("пар «сущность — величина» из данных: %d\n" % len(pairs))
    if not pairs:
        print("данных нет — мерить нечего")
        return 1

    ind = independent(pairs)
    bad = {k: [] for k in ("пересчёт", "инварианты", "нечего считать",
                           "паритет множеств", "детерминированность")}
    limit_gap = []

    for t, m, n in pairs:
        agg = A.aggregate(t, "", [], m)
        if not agg:
            bad["пересчёт"].append("%s.%s: aggregate вернул пусто" % (t, m))
            continue
        # 1. пересчёт независимой формулой
        e = ind.get((t, m))
        if not e:
            bad["пересчёт"].append("%s.%s: независимый пересчёт не дал строки" % (t, m))
        else:
            for k in ("count", "sum", "min", "max", "count_amount"):
                if _f(agg.get(k)) != _f(e.get(k)):
                    bad["пересчёт"].append("%s.%s: %s — шаг 5 даёт %r, пересчёт %r"
                                           % (t, m, k, agg.get(k), e.get(k)))
        # 2. инварианты арифметики
        ca, c = agg["count_amount"], agg["count"]
        if ca > c:
            bad["инварианты"].append("%s.%s: со значением %d > строк %d" % (t, m, ca, c))
        if agg["min"] > agg["max"]:
            bad["инварианты"].append("%s.%s: min %r > max %r" % (t, m, agg["min"], agg["max"]))
        if ca:
            want = round(agg["sum"] / ca, 2)
            if abs(want - agg["avg"]) > 0.01:
                bad["инварианты"].append(
                    "%s.%s: среднее %r, а sum/со значением = %r (считано не по тем строкам)"
                    % (t, m, agg["avg"], want))
        # 3. «нечего считать» против нуля: множество без этой величины
        empty = A.aggregate(t, "", ["(nums IS NULL OR NOT map_contains(nums, %s))" % A.lit(m)], m)
        if empty and empty.get("count_amount") == 0:
            named = [k for k in ("sum", "min", "max", "avg") if empty.get(k) is not None]
            if named:
                bad["нечего считать"].append(
                    "%s.%s: строк со значением 0, а числа названы: %s"
                    % (t, m, ", ".join("%s=%r" % (k, empty[k]) for k in named)))
        # 4. паритет: показано модели против посчитано
        shown = A.rows_of(t, "", [], A.TOPK, m)
        seen = A.psql("SELECT count(*) FROM %s WHERE src_table = %s" % (A.CORPUS, A.lit(t)))
        total_rows = int(seen[0][0]) if seen and seen[0] else 0
        if total_rows <= A.TOPK and len(shown) != c:
            bad["паритет множеств"].append(
                "%s.%s: показано строк %d, посчитано %d (разные множества)"
                % (t, m, len(shown), c))
        # 5. детерминированность
        again = [A.aggregate(t, "", [], m) for _ in range(2)]
        for a2 in again:
            if a2 != agg:
                bad["детерминированность"].append("%s.%s: повтор дал другое" % (t, m))
                break
        # 6. замер: итог по всему множеству против итога по показанным строкам
        part = sum(_f(r[2]) or 0 for r in shown)
        if agg["sum"]:
            limit_gap.append(abs(agg["sum"] - part) / abs(agg["sum"]) * 100)

    print("=" * 72)
    fails = 0
    for k, v in bad.items():
        mark = "OK  " if not v else "ПРОВАЛ"
        print("%-6s %-22s %s" % (mark, k, ("" if not v else "%d случаев" % len(v))))
        for line in v[:5]:
            print("        · %s" % line)
        if len(v) > 5:
            print("        · … ещё %d" % (len(v) - 5))
        fails += len(v)
    if limit_gap:
        print("\nЗАМЕР: итог по всему множеству против итога по %d показанным строкам —"
              % A.TOPK)
        print("       расходится в среднем на %.1f %%, наибольшее %.1f %% (пар: %d)"
              % (sum(limit_gap) / len(limit_gap), max(limit_gap), len(limit_gap)))
        print("       Это цена отказа от LIMIT: столько соврал бы ответ, считай мы по выборке.")
    print("=" * 72)
    print("ИТОГ: %s" % ("все проверки прошли" if not fails else "провалов %d" % fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
