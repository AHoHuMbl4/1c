#!/usr/bin/env python3
"""Оффлайн-замки К8 ask-decomposer: моки модели и /ask, без сети."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import decomposer as D  # noqa: E402

PASS, FAIL = 0, []


def t(name, cond):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name)


# --- parse_split_plan: простой / составной ------------------------------------

t("simple: composite false → не декомпозируем",
  D.parse_split_plan({"composite": False}).composite is False)

plan_cmp = D.parse_split_plan({
    "composite": True,
    "synthesis": "compare",
    "atoms": [
        {"id": "a", "question": "сколько в этом месяце?", "label": "МТД"},
        {"id": "b", "question": "сколько в прошлом месяце?", "label": "пред."},
    ],
    "compare": {"left_id": "a", "right_id": "b", "relation": "more_than"},
})
t("composite: два атома", len(plan_cmp.atoms) == 2)
t("composite: synthesis compare", plan_cmp.synthesis == "compare")
t("composite: compare spec", plan_cmp.compare.left_id == "a")

plan_top = D.parse_split_plan({
    "composite": True,
    "synthesis": "top_n",
    "atoms": [
        {"id": "t1", "question": "сколько у товара А?", "label": "А"},
        {"id": "t2", "question": "сколько у товара Б?", "label": "Б"},
        {"id": "t3", "question": "сколько у товара В?", "label": "В"},
    ],
})
t("top_n: три атома", len(plan_top.atoms) == 3 and plan_top.synthesis == "top_n")

t("пустые atoms → simple",
  D.parse_split_plan({"composite": True, "atoms": []}).composite is False)

# --- classify mock: handle passthrough ----------------------------------------

calls = []

def ask_rec(q):
    calls.append(q)
    return {"kind": "answer", "text": "ответ на: " + q, "atom": {"exact_value": 100}}

def split_simple(_q):
    return {"composite": False}

calls.clear()
r = D.handle("сколько продали вчера?", split_simple, ask_rec)
t("simple: один ask", len(calls) == 1)
t("simple: decomposed false", r.decomposed is False)
t("simple: текст проброшен", "ответ на:" in r.text)

# --- составной: раскладка атомов (мок модели) ---------------------------------

def split_compare(_q):
    return {
        "composite": True,
        "synthesis": "compare",
        "atoms": [
            {"id": "mtd", "question": "сколько в этом месяце?", "label": "МТД"},
            {"id": "prev", "question": "сколько в прошлом?", "label": "пред."},
        ],
        "compare": {"left_id": "mtd", "right_id": "prev", "relation": "more_than"},
    }

calls_cmp = []

def ask_compare(q):
    calls_cmp.append(q)
    if "этом" in q:
        return {"kind": "figures", "text": "x",
                "atom": {"exact_value": 3817442.31, "measure_label": "сумма"}}
    return {"kind": "figures", "text": "x",
            "atom": {"exact_value": 2767450.98, "measure_label": "сумма"}}

calls_cmp.clear()
r2 = D.handle("в этом месяце больше?", split_compare, ask_compare)
t("compare: decomposed", r2.decomposed is True)
t("compare: два атома", len(r2.atoms) == 2)
t("compare: два вызова ask", len(calls_cmp) == 2)
t("compare: вердикт больше", "да, больше" in r2.text)
t("compare: разница в тексте", "1049991" in r2.text.replace(" ", "").replace(",", ""))

# --- compare_values: больше / меньше / равно ----------------------------------

v_gt, p_gt = D.compare_values(10, 5, "more_than")
t("arith: больше", v_gt is True and "да, больше" in p_gt)
v_lt, p_lt = D.compare_values(3, 7, "more_than")
t("arith: не больше", v_lt is False and "не больше" in p_lt)
v_eq, p_eq = D.compare_values(5, 5, "more_than")
t("arith: равно", v_eq is None and "равно" in p_eq)
_, p_less = D.compare_values(3, 7, "less_than")
t("arith: меньше", "да, меньше" in p_less)

# --- top-N сводка -------------------------------------------------------------

def split_top(_q):
    return plan_top

def ask_top(q):
    vals = {"А": 100, "Б": 80, "В": 50}
    for k, v in vals.items():
        if k in q:
            return {"kind": "figures", "atom": {"exact_value": v}}
    return {"kind": "no_data"}

r3 = D.handle("топ-3 и сколько", split_top, ask_top)
t("top_n: таблица", "| 1 |" in r3.text and "| 3 |" in r3.text)
t("top_n: значения", "100" in r3.text and "80" in r3.text)

# --- no_data атома — честно, без угадывания ---------------------------------

def ask_one_no_data(q):
    return {"kind": "no_data", "text": "нет таких данных"}

r4 = D.handle("сравни", split_compare, ask_one_no_data)
t("no_data: не выдумываем вердикт", "да, больше" not in r4.text)
t("no_data: честная пометка", "нет данных" in r4.text or "невозможно" in r4.text)

def ask_partial_no_data(q):
    if "этом" in q:
        return {"kind": "figures", "atom": {"exact_value": 100}}
    return {"kind": "no_data", "text": "пусто"}

r5 = D.handle("сравни", split_compare, ask_partial_no_data)
t("no_data partial: сравнение невозможно", "невозможно" in r5.text.lower())
t("no_data partial: есть число первого", "100" in r5.text)

# --- clarify атома ------------------------------------------------------------

def ask_clarify(q):
    return {"kind": "clarify", "text": "Что посчитать?", "options": []}

r6 = D.handle("сравни", split_compare, ask_clarify)
t("clarify: не сравниваем", "да, больше" not in r6.text)
t("clarify: пометка", "уточнение" in r6.text)

# --- extract_primary_value ----------------------------------------------------

t("extract: atom exact_value",
  D.extract_primary_value({"kind": "figures", "atom": {"exact_value": 42.5}}) == 42.5)
t("extract: no_data → None",
  D.extract_primary_value({"kind": "no_data"}) is None)

# --- parallel run_atoms -------------------------------------------------------

order = []

def ask_slow(q):
    order.append(q)
    return {"kind": "answer", "atom": {"exact_value": len(order)}}

atoms = [
    D.AtomSpec("x", "q1", "1"),
    D.AtomSpec("y", "q2", "2"),
]
res_par = D.run_atoms(atoms, ask_slow, parallel=True)
t("parallel: два результата", len(res_par) == 2)

print("\n%d passed, %d failed" % (PASS, len(FAIL)))
if FAIL:
    print("failed:", ", ".join(FAIL))
    sys.exit(1)
