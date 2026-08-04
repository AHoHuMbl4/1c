#!/usr/bin/env python3
"""Оффлайн-прогон ШАГА 2 «отбор буквально»: БЕЗ базы, БЕЗ сети, БЕЗ вызовов модели.

Шаг 2 — это `probe` (проверить слова вопроса), `match_expr` (собрать условие с
градиентом), `tables_of` (разложить совпадения по сущностям), `children_by_parent`
(табличные части найденных шапок) и `matched_group_count` (сколько понятий вопроса
нашлось — от него зависит отказ). Всё это собирает SQL и зовёт базу, поэтому проверялось
только на живом стенде: дорого, невоспроизводимо, а с 03.08 сессиям ещё и недоступно.

Здесь `psql` подменён: каждому запросу отвечает заготовленное число, а сам текст запроса
остаётся для проверки. Так видно и ЧТО шаг спросил у базы, и ЧТО он сделал с ответом —
то есть ровно те решения шага 2, которые не зависят от содержимого базы.

Чего этот прибор НЕ проверяет и проверить не может: полноту («доходит ли верная сущность
до кандидатов») и избирательность («сколько сущностей вернулось») — это свойства данных,
они снимаются на живой базе.

Запуск:  python3 ubuntu/serenedb/test_step2.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ASK_TOKEN", "test")

import serene_ask as A  # noqa: E402

PASS = 0
FAIL = []


def t(name, cond):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name)


class Base:
    """Подставная база: помнит запросы и отвечает по правилу.

    `rule(sql)` -> список строк, как их отдаёт `psql` (список списков строк).
    """

    def __init__(self, rule):
        self.rule, self.sql = rule, []

    def __call__(self, sql):
        self.sql.append(sql)
        return self.rule(sql)


def with_base(rule, fn):
    """Выполнить `fn()` с подменённым `psql`, вернуть (результат, журнал запросов)."""
    base, real = Base(rule), A.psql
    A.psql = base
    try:
        return fn(), base.sql
    finally:
        A.psql = real


def counts_for(hit):
    """Ответ на пачку `probe`: попадание получают варианты, чей номер назван в `hit`."""
    def rule(sql):
        if " UNION ALL " in sql or sql.startswith("SELECT 0 i"):
            out = []
            for part in sql.split(" UNION ALL "):
                i = int(part.split(" i,")[0].rsplit(" ", 1)[-1])
                out.append([str(i), "7" if i in hit else "0"])
            return out
        return []
    return rule


# ------------------------------------------------------- образец `ts_like`: знаки слова
# `%` и `_` в `ts_like` — подстановочные знаки (доки движка
# `sql/functions/search/full-text`, `cookbook/search/wildcard-search`: экранирование `\%`,
# `\_`). Слово приходит из вопроса человека, где эти знаки — обычные буквы.
t("образец: обычное слово обёрнуто с двух сторон",
  A._like_pattern("Контрагент") == "%контрагент%")
t("образец: «%» из вопроса экранирован, а не стал «что угодно»",
  A._like_pattern("наценка 10%") == "%наценка 10\\%%")
t("образец: «_» из вопроса экранирован, а не стал «любой знак»",
  A._like_pattern("A_12") == "%a\\_12%")
t("образец: обратная косая экранирует себя, а не добавленное нами",
  A._like_pattern("a\\b") == "%a\\\\b%")
t("образец: у пустого слова образца нет (иначе «любой терм»)",
  A._like_pattern("   ") is None and A._like_pattern("") is None)

# Тот же знак, но уже в собранном запросе: голый «%» без экранирования дал бы образец
# `%%%` — совпадение с КАЖДЫМ термом индекса, то есть отбор без отбора.
_, sql = with_base(counts_for(set()), lambda: A.probe([["%"]]))
t("запрос: «%» не превращается в образец «любой терм»",
  all("'%%%'" not in q for q in sql))

# ------------------------------------------------------- строгость: какой способ победил
GR = [["Ромашка"]]
# Номера вариантов в пачке: 0 exact, 1 fuzzy, 2 part (слово одно, `slop` не строится).
(out, _d), _ = with_base(counts_for({0, 1, 2}), lambda: A.probe(GR))
t("строгость: при совпадении всеми способами берётся точная фраза",
  out and out[0].startswith("ts_phrase("))
(out, _d), _ = with_base(counts_for({1, 2}), lambda: A.probe(GR))
t("строгость: без точного берётся опечаточный, а не подстрока",
  out and out[0].startswith("ts_levenshtein("))
(out, _d), _ = with_base(counts_for({2}), lambda: A.probe(GR))
t("строгость: подстрока — последнее средство",
  out and out[0].startswith("ts_like("))
(out, diag), _ = with_base(counts_for(set()), lambda: A.probe(GR))
t("нет совпадений — нет ни выражения, ни отметки",
  out == [] and A.matched_group_count(diag) == 0)

# ------------------------------------------------------- многословное имя: фраза с окном
_, sql = with_base(counts_for(set()), lambda: A.probe([["Общество Ромашка"]]))
joined = " ".join(sql)
t("многословное: строится фраза с окном по самой фразе, без константы",
  "ts_phrase('Общество', ARRAY[0,1], 'Ромашка')" in joined)
_, sql = with_base(counts_for(set()), lambda: A.probe([["а б в г"]]))
t("многословное: окно растёт с числом слов (4 слова -> 3)",
  "ARRAY[0,3]" in " ".join(sql))

# ------------------------------------------------------- расстояние опечатки от длины
_, sql = with_base(counts_for(set()), lambda: A.probe([["tax"]]))
t("опечатки: у короткого слова расстояние 0 (иначе совпадает полкорпуса)",
  "ts_levenshtein('tax', 0)" in " ".join(sql))
_, sql = with_base(counts_for(set()), lambda: A.probe([["контрагенты"]]))
t("опечатки: у длинного слова расстояние 2",
  "ts_levenshtein('контрагенты', 2)" in " ".join(sql))

# ------------------------------------------------------- цена шага: один запрос на всё
_, sql = with_base(counts_for(set()),
                   lambda: A.probe([["Ромашка", "ООО Ромашка"], ["декабрь"]]))
t("цена: все слова и все их написания проверяются ОДНИМ запросом",
  len(sql) == 1)

# ------------------------------------------------------- 🔴 резолвер: найденное — найдено
# Разрешённое резолвером понятие («Питер» -> «Санкт-Петербург») — это НАЙДЕННОЕ понятие:
# выражение поиска по нему возвращается и работает. Прежде отметка ему не ставилась, а
# вызывающий считает найденные понятия ровно по отметкам, — и вопрос из одного такого
# понятия получал отказ «значения из вопроса не найдены» ДО сборки запроса.
real_resolve = A.resolve_values
A.resolve_values = lambda term: ["Санкт-Петербург"] if "питер" in term.lower() else []
try:
    (out, diag), _ = with_base(counts_for(set()), lambda: A.probe([["Питер"]]))
    t("резолвер: выражение поиска по разрешённому значению построено",
      out == ["ts_phrase('Санкт-Петербург')"])
    t("резолвер: понятие считается НАЙДЕННЫМ (иначе отказ при живых данных)",
      A.matched_group_count(diag) == 1)
    t("резолвер: сами значения видны отдельно — они уходят в ответ (п. 13)",
      diag.get("_resolved") == {0: ["Санкт-Петербург"]})

    # Смесь: одно понятие нашлось буквально, второе — резолвером. Найдены оба, отказа нет.
    (out, diag), _ = with_base(counts_for({0}), lambda: A.probe([["Ромашка"], ["Питер"]]))
    t("резолвер: в смеси с буквальным найденными считаются оба понятия",
      A.matched_group_count(diag) == 2 and len(out) == 2)

    # Резолвер молчит — понятия в базе нет. Это честный отказ, и он остаётся.
    (out, diag), _ = with_base(counts_for(set()), lambda: A.probe([["SanDisk"]]))
    t("резолвер молчит — понятие не найдено, отказ сохраняется",
      out == [] and A.matched_group_count(diag) == 0)
finally:
    A.resolve_values = real_resolve

# ------------------------------------------------------- градиент: «не меньше k из N»
def grad(hits):
    """Ответ на пачку `match_expr`: k из `hits` имеют совпадения."""
    def rule(sql):
        out = []
        for part in sql.split(" UNION ALL "):
            k = int(part.split(" k,")[0].rsplit(" ", 1)[-1])
            out.append([str(k), "5" if k in hits else "0"])
        return out
    return rule


E3 = ["ts_phrase('а')", "ts_phrase('б')", "ts_phrase('в')"]
(m, k), sql = with_base(grad({3, 2, 1}), lambda: A.match_expr(E3, []))
t("градиент: берётся наибольшее k, при котором есть совпадения", k == len(E3))
(m, k), _ = with_base(grad({2, 1}), lambda: A.match_expr(E3, []))
t("градиент: все три не совпали — берём два из трёх", k == 2)
(m, k), _ = with_base(grad({1}), lambda: A.match_expr(E3, []))
t("градиент: осталось одно понятие из трёх", k == 1)
(m, k), _ = with_base(grad(set()), lambda: A.match_expr(E3, []))
t("градиент: не совпало ничего — k не опускается ниже 1", k == 1)
t("градиент: в условие уходит ts_compound с выбранным k",
  "ts_compound(NULL, NULL, [%s], 1)" % ", ".join(E3) in m)
(m, k), sql = with_base(grad({1}), lambda: A.match_expr(E3, []))
t("цена: весь градиент — один запрос, а не запрос на каждое k", len(sql) == 1)
(m, k), _ = with_base(grad({1}), lambda: A.match_expr(["ts_phrase('а')"], []))
t("одно понятие: к базе за градиентом не ходим вовсе",
  k == 1 and "ts_compound" not in m)
t("ссылкам вес: условие ищет и по строке, и по полю ссылок",
  "refs @@" in m and A.REFS_BOOST in m)
(m, k), sql = with_base(grad({2, 1}), lambda: A.match_expr(E3, ["doc_date >= '2019-01-01'"]))
t("градиент считается ВНУТРИ условий по дате, а не поверх них",
  "doc_date >= '2019-01-01'" in sql[0])

# ------------------------------------------------------- разложение по сущностям
def rows(rs):
    return lambda sql: rs


by, sql = with_base(rows([["catalog_контрагенты", "12"], ["document_продажа", "3"]]),
                    lambda: A.tables_of("doc @@ ts_phrase('х')", []))
t("разложение: сущность -> число совпадений",
  by == {"catalog_контрагенты": 12, "document_продажа": 3})
t("разложение: считает база группировкой, а не мы построчно",
  len(sql) == 1 and "GROUP BY" in sql[0])
t("разложение: со словами идём в индекс",
  sql[0].split(" FROM ")[1].startswith(A.INDEX))
by, sql = with_base(rows([["document_продажа", "6"]]),
                    lambda: A.tables_of("", ["doc_date >= '2019-12-01'"]))
t("разложение: без слов остаются условия и корпус",
  by == {"document_продажа": 6} and A.CORPUS in sql[0])
t("разложение: без слов и без условий берётся всё (WHERE TRUE)",
  "WHERE TRUE" in with_base(rows([]), lambda: A.tables_of("", []))[1][0])

# ------------------------------------------------------- табличные части найденных шапок
def kids_rule(sql):
    if sql.startswith("SELECT src_table, parent FROM"):
        return [["document_продажа_товары", "document_продажа"]]
    return [["document_продажа_товары", "76"]]


(kids, pred), sql = with_base(
    kids_rule, lambda: A.children_by_parent({"document_продажа": 6},
                                            "doc @@ ts_phrase('Ромашка')", []))
t("табличные части: строки найденной шапки попадают в кандидаты",
  kids == {"document_продажа_товары": 76})
t("табличные части: связь берётся структурно — по владельцу строки",
  "split_part(row_key, '|', 1)" in pred["document_продажа_товары"])
t("цена: один запрос на ВСЕ табличные части, а не по запросу на каждую", len(sql) == 2)
(kids, pred), sql = with_base(kids_rule,
                              lambda: A.children_by_parent({}, "doc @@ х", []))
t("табличные части: без найденных шапок к базе не ходим вовсе",
  kids == {} and sql == [])

print("\n%d ok, %d FAIL" % (PASS, len(FAIL)))
for f in FAIL:
    print("  FAIL:", f)
sys.exit(1 if FAIL else 0)
