#!/usr/bin/env python3
"""Оффлайн-замки К8 compound-ask: таблица атомов, сборка без пересчёта."""
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
import table as T  # noqa: E402

PASS, FAIL = 0, []


def t(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, detail)


# --- parse_split_plan ---------------------------------------------------------

t("simple: composite false", T.parse_split_plan({"composite": False}).composite is False)

plan_cmp = T.parse_split_plan(
    {
        "composite": True,
        "synthesis": "compare",
        "atoms": [
            {"id": "a", "question": "сколько в этом месяце?", "label": "МТД"},
            {"id": "b", "question": "сколько в прошлом месяце?", "label": "пред."},
        ],
        "compare": {"left_id": "a", "right_id": "b", "relation": "more_than"},
    }
)
t("composite: два атома", len(plan_cmp.atoms) == 2)
t("composite: synthesis compare", plan_cmp.synthesis == "compare")

plan_top = T.parse_split_plan(
    {
        "composite": True,
        "synthesis": "top_n",
        "atoms": [
            {"id": "t1", "question": "сколько у позиции 1?", "label": "поз.1"},
            {"id": "t2", "question": "сколько у позиции 2?", "label": "поз.2"},
            {"id": "t3", "question": "сколько у позиции 3?", "label": "поз.3"},
        ],
    }
)
t("top_n: три атома", len(plan_top.atoms) == 3)

t(
    "пустые atoms → simple",
    T.parse_split_plan({"composite": True, "atoms": []}).composite is False,
)

# --- simple passthrough -------------------------------------------------------

calls = []


def ask_rec(q):
    calls.append(q)
    return {"kind": "answer", "text": "ответ: " + q, "atom": {"exact_value": 100}}


def split_simple(_q):
    return {"composite": False}


calls.clear()
r = T.handle("сколько вчера?", split_simple, ask_rec)
t("simple: один ask", len(calls) == 1)
t("simple: decomposed false", r.decomposed is False)

# --- compare: вердикт без разности --------------------------------------------

def split_compare(_q):
    return {
        "composite": True,
        "synthesis": "compare",
        "atoms": [
            {"id": "mtd", "question": "сколько в этом месяце?", "label": "этот месяц"},
            {"id": "prev", "question": "сколько в прошлом?", "label": "прошлый месяц"},
        ],
        "compare": {"left_id": "mtd", "right_id": "prev", "relation": "more_than"},
    }


def ask_compare(q):
    if "этом" in q or "текущ" in q:
        return {
            "kind": "figures",
            "text": "3817442.31",
            "atom": {"exact_value": 3817442.31},
        }
    return {
        "kind": "figures",
        "text": "2767450.98",
        "atom": {"exact_value": 2767450.98},
    }


r2 = T.handle("в этом месяце больше?", split_compare, ask_compare)
t("compare: decomposed", r2.decomposed is True)
t("compare: два атома", len(r2.rows) == 2)
t("compare: оба числа в тексте", "3817442.31" in r2.text and "2767450.98" in r2.text)
t("compare: вердикт больше", "да, больше" in r2.text)
t("compare: нет разности", not T.contains_derived_arithmetic(r2.text))
t("compare: нет diff-числа", "1049991" not in r2.text.replace(" ", ""))

# --- relation_phrase ----------------------------------------------------------

t("relation: больше", T.relation_phrase(10, 5, "more_than") == "да, больше")
t("relation: не больше", T.relation_phrase(3, 7, "more_than") == "нет, не больше")
t("relation: равно", T.relation_phrase(5, 5, "more_than") == "равно")
t("relation: меньше", T.relation_phrase(3, 7, "less_than") == "да, меньше")

# --- top-N --------------------------------------------------------------------

def split_top(_q):
    return plan_top


def ask_top_by_index(q):
    mapping = [
        ("позиции 1", 100),
        ("позиции 2", 80),
        ("позиции 3", 50),
    ]
    for needle, val in mapping:
        if needle in q:
            return {"kind": "figures", "atom": {"exact_value": val}}
    return {"kind": "no_data"}


r3 = T.handle("топ-3 и сколько", split_top, ask_top_by_index)
t("top_n: таблица", "| 1 |" in r3.text and "| 3 |" in r3.text)
t("top_n: числа из атомов", "100" in r3.text and "80" in r3.text and "50" in r3.text)
t("top_n: без пересчёта", not T.contains_derived_arithmetic(r3.text))

# --- no_data / clarify --------------------------------------------------------

def ask_no_data(_q):
    return {"kind": "no_data", "text": "нет таких данных"}


r4 = T.handle("сравни", split_compare, ask_no_data)
t("no_data: нет ложного вердикта", "да, больше" not in r4.text)
t("no_data: неполное сравнение", "неполн" in r4.text.lower())


def ask_partial(q):
    if "этом" in q:
        return {"kind": "figures", "atom": {"exact_value": 100}}
    return {"kind": "no_data", "text": "пусто"}


r5 = T.handle("сравни", split_compare, ask_partial)
t("partial: неполное", "неполн" in r5.text.lower())
t("partial: первое число видно", "100" in r5.text)


def ask_clarify(_q):
    return {"kind": "clarify", "text": "Что посчитать?", "options": []}


r6 = T.handle("сравни", split_compare, ask_clarify)
t("clarify: без вердикта", "да, больше" not in r6.text)
t("clarify: пометка", "уточнение" in r6.text)

# --- extract / body -----------------------------------------------------------

t(
    "extract: exact_value",
    T.extract_primary_value({"kind": "figures", "atom": {"exact_value": 42.5}}) == 42.5,
)
t("extract: no_data → None", T.extract_primary_value({"kind": "no_data"}) is None)
t(
    "body: figures text",
    "3817442.31" in T.body_from_payload({"kind": "figures", "text": "3817442.31"}),
)

# --- compare-набор Q1–Q8 (формулировки + планы из fixtures) -------------------

fixture_path = os.path.join(ROOT, "fixtures", "compare_plans.json")
with open(fixture_path, encoding="utf-8") as fh:
    compare_cases = json.load(fh)

t("fixtures: 8 вопросов compare", len(compare_cases) == 8)

MOCK_CUR = 3817442.31
MOCK_PREV = 2767450.98


def ask_pair(q):
    ql = q.lower()
    prior = ("прошл", "год назад", "июле", "за июль", "на прошлой")
    if any(m in ql for m in prior):
        return {
            "kind": "figures",
            "atom": {"exact_value": MOCK_PREV},
            "text": str(MOCK_PREV),
        }
    return {
        "kind": "figures",
        "atom": {"exact_value": MOCK_CUR},
        "text": str(MOCK_CUR),
    }


for case in compare_cases:
    cid = case["id"]
    question = case["question"]
    plan_data = case["plan"]

    def split_fixture(_q, p=plan_data):
        return p

    res = T.handle(question, split_fixture, ask_pair)
    t("%s: decomposed" % cid, res.decomposed is True)
    t("%s: два атома" % cid, len(res.rows) == 2)
    t("%s: числа в итоге" % cid, str(MOCK_CUR) in res.text and str(MOCK_PREV) in res.text)
    t("%s: вердикт" % cid, "да, больше" in res.text)
    t("%s: без разности" % cid, not T.contains_derived_arithmetic(res.text))

# --- parallel run_atoms -------------------------------------------------------

order = []


def ask_slow(q):
    order.append(q)
    return {"kind": "answer", "atom": {"exact_value": len(order)}}


atoms = [T.AtomSpec("x", "q1", "1"), T.AtomSpec("y", "q2", "2")]
res_par = T.run_atoms(atoms, ask_slow, parallel=True)
t("parallel: два результата", len(res_par) == 2)

print("\n%d passed, %d failed" % (PASS, len(FAIL)))
if FAIL:
    print("failed:", ", ".join(FAIL))
    sys.exit(1)
