#!/usr/bin/env python3
"""ПРИБОР: «одна семья — одно прочтение» — посылка выбора сущности, проверяемая числом.

Зачем. В выборе сущности стояло допущение: шапка документа и его табличные части — одно и
то же прочтение вопроса, поэтому сосед по семье не считается соперником и **не поднимает
сомнения**. Из этого следовало, что арбитр-детектор на таком расхождении не запускается
вовсе и ответ уходит человеку молча.

`[замер 03.08]` Вопрос 6 приёмки «Сколько штук мы закупили?»: система ответила **327** по
табличной части «Виды Запасов» при эталоне **92 683** по «Товарам» — это ДВЕ ТАБЛИЧНЫЕ
ЧАСТИ ОДНОГО документа, то есть одна семья. Допущение стоило неверного ответа.

Что меряет прибор:

  1. **Расходятся ли члены одной семьи** по одноимённой величине — сплошным перебором по
     всей базе, с разделением на «шапка ↔ строки» и «строки ↔ строки». Это и есть проверка
     посылки: если расхождений мало, соседей правильно было исключать.
  2. **Сколько вопросов приёмки задеты**: у скольких эталонных сущностей есть сосед по
     семье, расходящийся числом хотя бы по одной общей величине. Пока такой сосед есть,
     ответ по нему неотличим от верного — ни для гейта, ни для человека.

🔴 ЧЕСТНАЯ ГРАНИЦА. Прибор меряет ПОСЫЛКУ, а не поведение продукта: попадёт ли сосед в круг
арбитра на живом вопросе, зависит от выбора модели, а он стоит денег. Здесь показано лишь
то, что классу ошибок есть где возникать, и насколько он част.

Имён конкретной базы в приборе нет: семьи он берёт из `search_tables.parent`, эталоны — из
приёмочного набора (путь аргументом).

Использование:
    SERENEDB_DSN_RO=… python3 work/acceptance/kin_rival_bench.py [файл_набора]
"""
import importlib
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SET_FILE = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "docs/ACCEPTANCE_UT.md")

sys.path.insert(0, os.path.join(ROOT, "ubuntu/serenedb"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
A = importlib.import_module("serene_ask")
B = importlib.import_module("entity_choice_bench")

# Итоги по каждой паре «сущность + величина», сведённые в семьи по `search_tables.parent`.
# Считает база одним запросом: наружу не вычитывается ничего, кроме готовых чисел (п. 20).
FAMILY_SQL = """
WITH m AS (SELECT src_table, unnest(map_keys(nums)) k, unnest(map_values(nums)) v
           FROM search_corpus WHERE nums IS NOT NULL),
s AS (SELECT src_table, k, round(sum(v), 2) tot FROM m GROUP BY 1, 2),
f AS (SELECT coalesce(t.parent, t.src_table) fam, t.parent IS NULL AS head,
             s.src_table, s.k, s.tot
      FROM s JOIN search_tables t ON t.src_table = s.src_table)
SELECT a.fam, a.src_table, b.src_table, a.k, a.tot, b.tot, a.head, b.head
FROM f a JOIN f b ON a.fam = b.fam AND a.k = b.k AND a.src_table < b.src_table
"""


def main():
    rows = A.psql(FAMILY_SQL)
    tot_hc = dif_hc = tot_cc = dif_cc = 0
    disagree = {}                      # сущность → соседи, расходящиеся числом
    for r in rows:
        fam, ta, tb, k, va, vb, ha, hb = r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7]
        head_a, head_b = str(ha).lower() in ("true", "t", "1"), str(hb).lower() in ("true", "t", "1")
        differ = str(va) != str(vb)
        if head_a != head_b:
            tot_hc += 1
            dif_hc += 1 if differ else 0
        elif not head_a and not head_b:
            tot_cc += 1
            dif_cc += 1 if differ else 0
        if differ:
            disagree.setdefault(ta, set()).add(tb)
            disagree.setdefault(tb, set()).add(ta)

    print("=" * 78)
    print("1. РАСХОДЯТСЯ ЛИ ЧЛЕНЫ ОДНОЙ СЕМЬИ ПО ОДНОИМЁННОЙ ВЕЛИЧИНЕ")
    def line(name, dif, tot):
        print("   %-26s %4d из %4d  (%s)"
              % (name, dif, tot, ("%.0f %%" % (100.0 * dif / tot)) if tot else "нет пар"))
    line("шапка ↔ табличная часть", dif_hc, tot_hc)
    line("табличная ↔ табличная", dif_cc, tot_cc)
    line("всего", dif_hc + dif_cc, tot_hc + tot_cc)
    print("   Посылка «одна семья — одно прочтение» верна ровно настолько, насколько эти")
    print("   доли МАЛЫ. Чем они больше, тем чаще молчаливый выбор внутри семьи — догадка.")

    print("\n2. СКОЛЬКО ВОПРОСОВ ПРИЁМКИ ЗАДЕТО")
    ps = B.pairs(SET_FILE)
    hit = [(q, e) for q, e in ps if disagree.get(e)]
    print("   вопросов с эталонной сущностью: %d" % len(ps))
    print("   у эталона есть расходящийся сосед по семье: %d (%.0f %%)"
          % (len(hit), 100.0 * len(hit) / max(len(ps), 1)))
    for q, e in hit[:12]:
        kin = sorted(disagree[e])
        print("      %-48s соседей %d" % (q[:48], len(kin)))
    if len(hit) > 12:
        print("      … и ещё %d" % (len(hit) - 12))
    return 0


if __name__ == "__main__":
    sys.exit(main())
