#!/usr/bin/env python3
"""ПРИБОР: может ли верная сущность вообще СТАТЬ соперником арбитра (шаг 4).

Зачем отдельный прибор. Кандидатов на шаге 4 приносят три поверхности, и с 03.08 они
складываются: буквальная (`by` — инвертированный индекс), синонимы (`alias_hits`) и
смысл (`near_tables`). Но дальше по коду сущность, пришедшая НЕ буквально, поражена в
правах — три места требуют `in by`:

  * `serene_ask.py:3183`  признак расхождения сигналов: `top_by_question in by`;
  * `serene_ask.py:3236`  подбор соперника арбитру: `c not in by → continue`;
  * `serene_ask.py:3249`  второй заход, соседи по семье: то же условие.

Следствие: если верная сущность дошла до перечня только смыслом или синонимом, а модель
выбрала чужую, то сомнение не поднимается, арбитр не собирает по ней ответ, числа не
сравниваются — и система отвечает неверно УВЕРЕННО. Это ровно наблюдавшееся
`сомнение=False` при трёх ошибках прогона 03.08.

Прибор считает, как часто это возможно: доля вопросов приёмки, где эталонная сущность
буквальным отбором НЕ находится.

🔴 ЧЕСТНЫЕ ГРАНИЦЫ.
1. Понятия вопроса в бою формулирует модель (`parse_intent`); здесь вместо неё берутся
   слова самого вопроса — то же приближение, что в `candidate_surfaces_bench`, и по той
   же причине: этот прибор бесплатен и воспроизводим. Слов больше, чем понятий
   от модели, поэтому буквальный отбор здесь ШИРЕ боевого, и число «не нашлось буквально»
   — НИЖНЯЯ оценка беды.
2. Смысловая поверхность (`near_tables`) требует эмбеддинга вопроса, то есть ключа
   эмбеддера. Без него столбец «смысл» не считается и печатается как «?» — прибор об
   этом говорит вслух, а не подставляет ноль.
3. Табличная часть засчитывается за свой документ (`search_tables.parent`) — как и в
   соседних приборах.

Использование:
    SERENEDB_DSN='host=… dbname=ut_test' python3 work/acceptance/rival_reach_bench.py [набор]
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
# `entity_choice_bench` требует переменные эмбеддера уже на импорте, а нам от него нужен
# только разбор набора. Подставляем заглушки — вектор здесь не считается ни разу.
os.environ.setdefault("EMBED_BASE_URL", "-")
os.environ.setdefault("EMBED_MODEL", "-")

A = importlib.import_module("serene_ask")
B = importlib.import_module("entity_choice_bench")

TOP = A.MEANING_TOP


def words(q):
    return [w for w in re.split(r"[^0-9A-Za-zА-Яа-яЁё]+", q) if w]


def main():
    par = {}
    for r in A.psql("SELECT src_table, coalesce(nullif(parent,''), src_table) "
                    "FROM %s" % A.TABLES):
        if r and r[0]:
            par[r[0]] = r[1]

    def fam(t):
        return par.get(t) or t

    pairs = B.pairs(SET_FILE)
    n = lit_hit = alias_hit = only_alias = neither = 0
    barred = []
    print("%-46s %-10s %s" % ("вопрос", "буквально", "синонимы"))
    for q, want in pairs:
        groups = [[w] for w in words(q)]
        try:
            exprs, _k = A.probe(groups)
        except RuntimeError:
            continue
        match, _kk = A.match_expr(exprs, [])
        by = list(A.tables_of(match, [])) if match else []
        # Табличные части найденных шапок попадают в `by` тем же способом, что в бою.
        try:
            kids, _kp = A.children_by_parent({t: 1 for t in by}, match, [])
            by = by + [t for t in kids if t not in by]
        except (RuntimeError, TypeError):
            pass
        al = A.alias_hits(exprs, TOP) if exprs else []
        w = fam(want)
        in_lit = any(fam(t) == w for t in by)
        in_al = any(fam(t) == w for t in al)
        n += 1
        lit_hit += in_lit
        alias_hit += in_al
        if not in_lit and in_al:
            only_alias += 1
            barred.append((q, want))
        if not in_lit and not in_al:
            neither += 1
        print("%-46s %-10s %s" % (q[:46], "да" if in_lit else "—", "да" if in_al else "—"))

    print("\nвопросов с эталонной сущностью: %d" % n)
    if not n:
        return 1
    print("  эталон найден БУКВАЛЬНО (`in by`)      : %2d (%d%%)"
          % (lit_hit, round(100.0 * lit_hit / n)))
    print("  эталон найден СИНОНИМОМ                : %2d (%d%%)"
          % (alias_hit, round(100.0 * alias_hit / n)))
    print("  🔴 НЕ буквально — значит не может быть ни соперником арбитра,")
    print("     ни источником сомнения (serene_ask.py:3183/3236/3249): %2d (%d%%)"
          % (n - lit_hit, round(100.0 * (n - lit_hit) / n)))
    print("       из них синоним его всё-таки принёс в перечень: %d" % only_alias)
    print("       смысловая поверхность здесь не считалась (нужен эмбеддер): ?")
    print("       не принесла ни одна из двух измеренных: %d" % neither)
    if barred:
        print("\nЭталон в перечне ЕСТЬ, но в круг арбитра попасть не может:")
        for q, want in barred:
            print("  %s → %s" % (q[:58], want))
    return 0


if __name__ == "__main__":
    sys.exit(main())
