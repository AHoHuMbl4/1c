#!/usr/bin/env python3
"""ПРИБОР СЛОВАРЯ СИНОНИМОВ: на каком месте эталонная сущность — БЕЗ модели и без денег.

Зачем. Словарь синонимов (`search_entity_alias`) участвует в выборе сущности дважды: приводит
кандидатов и ПОДТВЕРЖДАЕТ выбор («лидер словаря по вопросу»). `[замер 05.08]` подтверждение
держит 17 ответов из 44, и решает его один-единственный лидер — значит качество словаря видно
по одному числу: **на каком месте в его ранжировании стоит эталонная сущность вопроса**.

Прогон приёмки через модель стоит денег и 40 минут; этот прибор считает то же качество за
секунды, потому что ранжирует ДВИЖОК по индексу, а модель не зовётся вовсе. Поэтому им можно
сравнивать варианты словаря сколько угодно раз, а платный прогон снимать один — в конце.

Что печатает: место эталона (1 = лидер), сколько эталонов в лидерах, сколько в тройке, сколько
не найдено вовсе, и — построчно — кто оказался лидером вместо эталона.

Варианты сравниваются через окружение, сам словарь прибор НЕ меняет:
    ALIAS_TABLE=<таблица>   какой словарь спрашивать (умолчание search_entity_alias)
    ALIAS_INDEX=<индекс>    каким индексом (умолчание alias_idx)
    SCORERS=tfidf,bm25      какие линейки сравнить

Использование:
    ASK_ENV_FILES=… python3 work/entity-choice/alias_rank_bench.py [от] [до]
"""
import importlib
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "ubuntu/serenedb"))
sys.path.insert(0, os.path.join(ROOT, "work/acceptance"))
os.environ.setdefault("EMBED_BASE_URL", "-")
os.environ.setdefault("EMBED_MODEL", "-")
os.environ.setdefault("ASK_TOKEN", "bench")
SET_FILE = os.environ.get("SET_FILE", os.path.join(ROOT, "docs/ACCEPTANCE_UT.md"))
sys.argv = [sys.argv[0], SET_FILE]

A = importlib.import_module("serene_ask")
B = importlib.import_module("entity_choice_bench")

TABLE = os.environ.get("ALIAS_TABLE", "search_entity_alias")
INDEX = os.environ.get("ALIAS_INDEX", "alias_idx")
SCORERS = [s.strip() for s in os.environ.get("SCORERS", "tfidf").split(",") if s.strip()]
DEPTH = int(os.environ.get("DEPTH", "8"))


def место(вопрос, семья, fam, scorer):
    """Место семьи эталона в ранжировании словаря по вопросу. 0 — не нашлась вовсе."""
    try:
        rs = A.psql("SELECT src_table, %s(%s.tableoid) AS s FROM %s WHERE aliases @@ %s "
                    "ORDER BY s DESC, src_table LIMIT %d"
                    % (scorer, INDEX, INDEX, A.lit(вопрос), DEPTH))
    except RuntimeError as e:
        print("   запрос не прошёл:", str(e)[:160])
        return 0, ""
    top = [r[0] for r in rs if r and r[0]]
    for i, t in enumerate(top, 1):
        if fam.get(t, t) == семья:
            return i, top[0]
    return 0, (top[0] if top else "")


def main():
    pairs = B.pairs(SET_FILE)
    args = [a for a in sys.argv[2:] if a.isdigit()]
    lo = int(args[0]) if args else 1
    hi = int(args[1]) if len(args) > 1 else len(pairs)
    pairs = pairs[lo - 1:hi]
    fam = {r[0]: r[1] for r in A.psql(
        "SELECT src_table, coalesce(nullif(parent,''), src_table) FROM %s" % A.TABLES)
        if r and r[0]}
    print("словарь: %s, индекс: %s, вопросов: %d\n" % (TABLE, INDEX, len(pairs)))
    итог = {}
    for scorer in SCORERS:
        лидер = тройка = нет = 0
        подмены = []
        for i, (q, want) in enumerate(pairs, lo):
            семья = fam.get(want, want)
            n, вместо = место(q, семья, fam, scorer)
            if n == 1:
                лидер += 1
            elif n and n <= 3:
                тройка += 1
            elif not n:
                нет += 1
                подмены.append((i, q, вместо))
        итог[scorer] = (лидер, тройка, нет)
        print("%-6s эталон лидер: %2d | в тройке: %2d | не найден вовсе: %2d  (из %d)"
              % (scorer, лидер, тройка, нет, len(pairs)))
        if os.environ.get("SHOW_MISS") == "1":
            for i, q, вместо in подмены[:20]:
                print("      %2d. %-44s лидер: %s" % (i, q[:44], (вместо or "—")[:44]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
