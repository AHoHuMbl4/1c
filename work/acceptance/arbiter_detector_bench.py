#!/usr/bin/env python3
"""ПРИБОР: как часто АРБИТР-ДЕТЕКТОР сказал бы «спрашиваем» (задача 17).

Правило: арбитр больше не выбирает между посчитанными ответами кандидатов — если их числа
разошлись, это доказанная неоднозначность, и выбор делает человек. Здесь меряется, насколько
часто числа кандидатов вообще расходятся, то есть цена правила.

Пара кандидатов берётся детерминированно и без модели: эталонная сущность набора и её
сильнейший соперник — первая сущность смысловой поверхности (`near_tables`), не входящая в
семью эталона. Числа — `count(*)` каждого, считает база.

🔴 ЧЕСТНЫЕ ГРАНИЦЫ.
1. В бою арбитр запускается ТОЛЬКО при найденном сомнении (модель назвала несколько
   сущностей либо вершина по вектору вопроса разошлась с выбором модели). Прибор этого не
   знает — он меряет не «как часто спросим», а «как часто числа расходятся, КОГДА кандидатов
   двое». Частота самого сомнения меряется только приёмкой, то есть за деньги.
2. В бою сравниваются итоги по выбранной величине, если она названа; здесь — число записей.
   Это НИЖНЯЯ оценка расхождения: итоги разных сущностей совпадают ещё реже, чем счётчики.
3. Соперник берётся по смысловой поверхности, потому что она приносит эталон чаще прочих
   (66 % против 43 % и 11 %, `candidate_surfaces_bench`).

Использование:
    SERENEDB_DSN_RO=… PGPASSWORD=… <переменные эмбеддера> \
        python3 work/acceptance/arbiter_detector_bench.py [набор]
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


def rows_count(src):
    try:
        r = A.psql("SELECT count(*) FROM %s WHERE src_table = %s" % (A.CORPUS, A.lit(src)))
        return int(r[0][0]) if r and r[0] else 0
    except (RuntimeError, ValueError, IndexError):
        return 0


def main():
    par = {}
    for r in A.psql("SELECT src_table, coalesce(nullif(parent,''), src_table) FROM %s"
                    % A.TABLES):
        if r and r[0]:
            par[r[0]] = r[1]
    fired, same, alone = 0, 0, 0
    coincided = []
    for q, want in B.pairs(SET_FILE):
        wf = S.family(want, par)
        rival = next((t for t in A.near_tables(q, A.MEANING_TOP)
                      if S.family(t, par) != wf), None)
        if not rival:
            alone += 1
            continue
        a, b = rows_count(want), rows_count(rival)
        # То же правило, что в продукте: сравниваются сами числа, порога нет.
        if A.answers_diverge([{"count": a}, {"count": b}]):
            fired += 1
        else:
            same += 1
            coincided.append((q, want, rival, a))
    print("вопросов с эталонной сущностью и соперником: %d" % (fired + same))
    print("  числа кандидатов РАЗОШЛИСЬ — детектор спросил бы: %d" % fired)
    print("  числа совпали — детектор молчит, отвечаем:        %d" % same)
    print("  соперника вне семьи не нашлось:                   %d" % alone)
    for q, want, rival, n in coincided:
        print("    совпало %d: %s | %s ↔ %s" % (n, q[:40], want, rival))
    return 0


if __name__ == "__main__":
    sys.exit(main())
