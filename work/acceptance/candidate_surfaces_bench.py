#!/usr/bin/env python3
"""ПРИБОР: доносит ли ОТБОР верную сущность до кандидатов — по каждой поверхности врозь.

Зачем отдельный прибор. Главная открытая проблема — выбор сущности, и у неё две разные
половины: сущности вообще нет в кандидатах (recall) или она есть, но выбрали соседа
(precision). Приёмка через бота меряет их вместе, стоит денег и даёт разброс ±1 ответ из
восьми, поэтому по ней нельзя судить о правке ОТБОРА. Здесь меряется только отбор:
детерминированно, без модели ответов, без арбитра, без гейта.

Что делает:
  1. берёт пары «вопрос → эталонная сущность» ИЗ ПРИЁМОЧНОГО НАБОРА — разбор переиспользуется
     из `entity_choice_bench.pairs`, чтобы правила извлечения эталона жили в одном месте;
  2. зовёт НАСТОЯЩИЕ функции отбора из `serene_ask` (`probe`, `tables_of`, `alias_hits`,
     `near_tables`) — прибор не повторяет логику продукта, он её вызывает;
  3. печатает по каждой поверхности, донесла ли она верную сущность, и что даёт их сумма.

🔴 ЧЕСТНАЯ ГРАНИЦА ПРИБОРА. Понятия вопроса в бою формулирует модель (`parse_intent`):
она даёт варианты написания и словоформы. Здесь вместо неё берутся слова самого вопроса,
потому что вызов модели стоит денег, а прибор должен быть бесплатным и воспроизводимым.
Поэтому числа — НИЖНЯЯ ОЦЕНКА: в бою у каждой поверхности вход богаче. Приближение одно
и то же для ВСЕХ трёх поверхностей, поэтому сравнение между ними честное.

🔴 Табличная часть засчитывается за свой документ (`search_tables.parent`) — как и в
`entity_choice_bench`: выбрать шапку вместо строк или наоборот — не та ошибка, которую
меряет этот прибор.

Использование:
    SERENEDB_DSN_RO=… PGPASSWORD=… <переменные эмбеддера> \
        python3 work/acceptance/candidate_surfaces_bench.py [файл_набора]
"""
import importlib
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SET_FILE = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "docs/ACCEPTANCE_UT.md")

sys.path.insert(0, os.path.join(ROOT, "ubuntu/serenedb"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# `entity_choice_bench` читает набор из sys.argv[1] на импорте — задаём явно, чтобы он
# не разобрал наши собственные аргументы как чужие.
sys.argv = [sys.argv[0], SET_FILE]

A = importlib.import_module("serene_ask")
B = importlib.import_module("entity_choice_bench")

TOP = A.MEANING_TOP


def words(q):
    """Слова вопроса как отдельные понятия. Приближение к `parse_intent` — см. врезку."""
    return [w for w in re.split(r"[^0-9A-Za-zА-Яа-яЁё]+", q) if w]


def family(t, par):
    return par.get(t) or t


def surfaces(q):
    """Три поверхности отбора для одного вопроса. Считает база, как и в бою."""
    groups = [[w] for w in words(q)]
    try:
        exprs, _kinds = A.probe(groups)
    except RuntimeError:
        return None
    match, _k = A.match_expr(exprs, [])
    lit = list(A.tables_of(match, [])) if match else []
    return {"буквально": lit,
            "синонимы": A.alias_hits(exprs, TOP),
            "смысл": A.near_tables(q, TOP)}


def main():
    par = {}
    for r in A.psql("SELECT src_table, coalesce(nullif(parent,''), src_table) "
                    "FROM %s" % A.TABLES):
        if r and r[0]:
            par[r[0]] = r[1]
    pairs = B.pairs(SET_FILE)
    names = ["буквально", "синонимы", "смысл"]
    hit = {n: 0 for n in names}
    hit["сумма"] = 0
    only_new = []
    total = 0
    print("вопрос                                             буквально синонимы смысл")
    for q, want in pairs:
        s = surfaces(q)
        if s is None:
            continue
        total += 1
        wf = family(want, par)
        got = {}
        for n in names:
            got[n] = any(family(t, par) == wf for t in s[n])
            if got[n]:
                hit[n] += 1
        if any(got.values()):
            hit["сумма"] += 1
        if not got["буквально"] and (got["синонимы"] or got["смысл"]):
            only_new.append((q, want))
        print("%-50s %-9s %-8s %s"
              % (q[:50], "да" if got["буквально"] else "—",
                 "да" if got["синонимы"] else "—", "да" if got["смысл"] else "—"))
    print("\nвопросов с эталонной сущностью: %d" % total)
    for n in names + ["сумма"]:
        print("  %-10s верная сущность в кандидатах: %2d (%d%%)"
              % (n, hit[n], round(100.0 * hit[n] / total) if total else 0))
    print("\nПРИНЕСЕНЫ ТОЛЬКО НОВЫМИ ПОВЕРХНОСТЯМИ (буквальный отбор их терял): %d"
          % len(only_new))
    for q, want in only_new:
        print("  %s → %s" % (q[:60], want))
    return 0


if __name__ == "__main__":
    sys.exit(main())
