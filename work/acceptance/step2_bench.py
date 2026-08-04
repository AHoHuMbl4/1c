#!/usr/bin/env python3
"""ПРИБОР ШАГА 2 «отбор буквально»: считает ОШИБКИ шага, а не удачи.

Мерило дня — число ошибок, цель ноль (`activeContext`, 03.08). Для шага 2 оно переводится
в проверяемое: возвращены ровно те сущности, у которых слова вопроса действительно стоят
в записях, число верное, и от прогона к прогону ничего не пляшет. Ошибка шага — не «эталон
не дошёл» (слова человека может не быть в данных вовсе; это задача шага 3), а расхождение
шага с самой базой.

Четыре класса ошибок, каждый сверяется НЕЗАВИСИМЫМ пересчётом по индексу:

  E1 ПОТЕРЯ    — у сущности есть строка под условием вопроса, а шаг её не вернул.
                 Это молчаливая потеря данных (п. 13): дальше по цепочке её не найдёт никто.
  E2 ЛИШНЕЕ    — шаг вернул сущность, у которой под её же условием нет ни строки.
                 Такой кандидат посчитается нулём и уведёт ответ.
  E3 СЧЁТ      — число совпадений расходится с пересчётом. Это число уходит дальше как
                 признак, по которому кандидатов различают, — враньё в нём хуже пропуска.
  E4 РАЗБРОС   — два прогона на неизменных данных дали разное. Воспроизводимость проверяется
                 повтором, а не рассуждением (`techContext` ловушка 30).

🔴 ЧЕСТНАЯ ГРАНИЦА. Понятия вопроса в бою даёт шаг 1 (`parse_intent`, модель). Здесь вместо
него берутся слова самого вопроса — прибор остаётся бесплатным и воспроизводимым. Для
ошибок шага 2 это ничего не искажает: сверяется СОГЛАСИЕ шага с базой на том входе, который
ему дали, каким бы вход ни был. Числа полноты («дошёл ли эталон») печатаются справочно и
мерилом шага 2 не являются.

Ни одного вызова модели ответов. Считает и сверяет база.

Использование:
    SERENEDB_DSN_RO=… PGPASSWORD=… python3 work/acceptance/step2_bench.py [файл_набора]
"""
import importlib
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SET_FILE = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "docs/ACCEPTANCE_UT.md")

sys.path.insert(0, os.path.join(ROOT, "ubuntu/serenedb"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.argv = [sys.argv[0], SET_FILE]

A = importlib.import_module("serene_ask")
B = importlib.import_module("entity_choice_bench")
S = importlib.import_module("candidate_surfaces_bench")


def parents():
    par = {}
    for r in A.psql("SELECT src_table, coalesce(nullif(parent,''), src_table) "
                    "FROM %s" % A.TABLES):
        if r and r[0]:
            par[r[0]] = r[1]
    return par


def step2(question):
    """Шаг 2 целиком, настоящими функциями продукта."""
    exprs, _kinds = A.probe([[w] for w in S.words(question)])
    if not exprs:
        return None
    match, k = A.match_expr(exprs, [])
    by = A.tables_of(match, []) if match else {}
    lvl, pred = A.partial_tables(exprs, [], k)
    return {"exprs": exprs, "match": match, "k": k, "by": by, "lvl": lvl, "pred": pred}


def recount(where_by_entity):
    """Независимый пересчёт: {сущность: условие} -> {сущность: строк}. Один запрос."""
    if not where_by_entity:
        return {}
    parts = ["SELECT %s AS t, count(*) AS n FROM %s WHERE src_table = %s AND %s"
             % (A.lit(t), A.INDEX, A.lit(t), w) for t, w in where_by_entity.items()]
    out = {}
    for r in A.psql(" UNION ALL ".join(parts)):
        if r and r[0]:
            try:
                out[r[0]] = int(r[1])
            except (ValueError, IndexError):
                pass
    return out


def loose_expr(exprs):
    """«Хотя бы одно понятие вопроса» — верхняя граница того, что шаг мог найти."""
    if len(exprs) == 1:
        return A.with_refs(exprs[0])
    return A.with_refs("ts_compound(NULL, NULL, [%s], 1)" % ", ".join(exprs))


def main():
    par = parents()
    # 🔴 ВСЕ вопросы набора, а не только те, у кого есть эталонная сущность. Ошибка шага 2 —
    # это расхождение шага с базой, и для неё эталон не нужен вовсе. Прежняя выборка
    # (44 пары из `entity_choice_bench`) оставляла без проверки четырнадцать вопросов, среди
    # них как раз те, где верной сущности нет по замыслу — то есть самые неудобные.
    import re as _re
    _text = open(SET_FILE, encoding="utf-8").read()
    all_q = [m.group(1).strip() for m in
             _re.finditer(r"\*\*\d+\.\s*«(.+?)»", _text, _re.S)]
    want_of = dict(B.pairs(SET_FILE))
    err = {"E1": [], "E2": [], "E3": [], "E4": []}
    fp = {}
    fp_path = os.environ.get("ASK_STEP2_FP")
    prev = {}
    if fp_path and os.path.exists(fp_path):
        for line in open(fp_path, encoding="utf-8"):
            if "\t" in line:
                a, b = line.rstrip("\n").split("\t", 1)
                prev[a] = b
    n = reached = with_ref = 0
    sizes = []

    for q in all_q:
        want = want_of.get(q)
        st = step2(q)
        if st is None:
            continue
        n += 1
        by, lvl, pred = st["by"], st["lvl"], st["pred"]
        returned = set(by) | set(lvl)
        sizes.append(len(returned))

        # E1: всё, что вообще можно было найти словами вопроса.
        could = {r[0] for r in A.psql(
            "SELECT src_table FROM %s WHERE %s GROUP BY 1"
            % (A.INDEX, loose_expr(st["exprs"]))) if r and r[0]}
        lost = could - returned
        if lost:
            err["E1"].append((q, sorted(lost)[:5], len(lost)))

        # E2 и E3: сверка КАЖДОЙ возвращённой сущности её собственным условием.
        where = {t: st["match"] for t in by}
        where.update({t: pred[t] for t in lvl})
        got = recount(where)
        for t in sorted(returned):
            real = got.get(t, 0)
            if real <= 0:
                err["E2"].append((q, t))
            elif t in by and by[t] != real:
                err["E3"].append((q, t, by[t], real))

        if want:
            with_ref += 1
            wf = par.get(want, want)
            if any(par.get(t, t) == wf for t in returned):
                reached += 1

        # E4: повтор на тех же данных. Двумя заходами, и оба нужны.
        #  * в этом же процессе — ловит разброс порядка исполнения в самой базе;
        #  * между процессами (отпечаток в файл `ASK_STEP2_FP`) — ловит то, чего первый
        #    заход увидеть не может: `probe` при ненайденном понятии зовёт резолвер, а тот
        #    ходит к эмбеддеру и реранкеру, то есть наружу. [замер 04.08] три прогона подряд
        #    дали 33/32/33 дошедших эталона при нуле ошибок по внутрипроцессной проверке —
        #    значит отбор между прогонами всё-таки менялся, и увидеть это можно только так.
        again = step2(q)
        if (again is None or again["by"] != by or again["lvl"] != lvl
                or again["match"] != st["match"]):
            err["E4"].append(q + "  (в одном прогоне)")
        fp[q] = "%s|%s" % (
            ";".join("%s=%d" % (t, by[t]) for t in sorted(by)),
            ";".join("%s=%d" % (t, lvl[t]) for t in sorted(lvl)))

    # Сверка с прошлым прогоном и запись отпечатка для следующего.
    for q, v in fp.items():
        if q in prev and prev[q] != v:
            err["E4"].append(q + "  (между прогонами)")
    if fp_path:
        with open(fp_path, "w", encoding="utf-8") as fh:
            for q in sorted(fp):
                fh.write("%s\t%s\n" % (q, fp[q]))

    med = sorted(sizes)[len(sizes) // 2] if sizes else 0
    print("=" * 78)
    print("ШАГ 2 «ОТБОР БУКВАЛЬНО» — ОШИБКИ ШАГА (вопросов: %d)" % n)
    print("=" * 78)
    names = {"E1": "ПОТЕРЯ  (нашлось в базе, шаг не вернул)",
             "E2": "ЛИШНЕЕ  (вернул, а строк под своим условием нет)",
             "E3": "СЧЁТ    (число совпадений расходится с пересчётом)",
             "E4": "РАЗБРОС (повтор дал другое)"}
    total = 0
    for code in ("E1", "E2", "E3", "E4"):
        cnt = len(err[code])
        total += cnt
        print("  %s %-50s %s" % ("🔴" if cnt else "  ", names[code],
                                 "%d" % cnt if cnt else "0"))
        for item in err[code][:5]:
            print("        %s" % (item,))
    print("\nИТОГО ОШИБОК ШАГА 2: %d  —  %s"
          % (total, "ЧИСТО" if total == 0 else "ЕСТЬ ЧТО ЧИНИТЬ"))
    print("\nсправочно (мерилом шага 2 не является):")
    print("  эталонная сущность среди возвращённых: %d из %d (%d%%)"
          % (reached, with_ref, round(100.0 * reached / with_ref) if with_ref else 0))
    print("  кандидатов от шага: медиана %d" % med)
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
