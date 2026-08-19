#!/usr/bin/env python3
"""Замки: единицы измерения — из данных, не из слов.

Пять замков:
1. Единица из данных: money=True → env, money=False → пусто
2. Без данных — без единицы: пустой MONEY_UNIT → пустая единица
3. «unknown» не уходит в текст: render_atom_pair не печатает (unknown)
4. rank fallback = compose по единице: rank_leader_answer_text принимает unit
5. env перекрывает: ASK_MONEY_UNIT заполнен → появляется в ответе
"""
import sys, os, re
sys.path.insert(0, os.path.dirname(__file__))
import serene_ask as A

ok_n = fail_n = 0
fails = []

def t(name, cond, detail=""):
    global ok_n, fail_n
    if cond:
        ok_n += 1
        print("ok  -", name)
    else:
        fail_n += 1
        fails.append(name)
        print("FAIL-", name, "|", detail)


# ═══ 1. Единица из данных (money flag, не словарь) ═══════════════════════════

t("unit_data: money=True → env (MONEY_UNIT)",
  A._unit_for_measure("Сумма", money=True) == A.MONEY_UNIT, "")
t("unit_data: money=False → пусто",
  A._unit_for_measure("Количество", money=False) == "", "")
t("unit_data: нерусская мера money=True → env",
  A._unit_for_measure("Cantitate", money=True) == A.MONEY_UNIT, "")
t("unit_data: нерусская мера money=False → пусто",
  A._unit_for_measure("Miktar", money=False) == "", "")
t("unit_data: None measure money=False → пусто",
  A._unit_for_measure(None, money=False) == "", "")

# ═══ 2. Без данных — без единицы ═════════════════════════════════════════════

saved = A.MONEY_UNIT
A.MONEY_UNIT = ""
t("no_data: MONEY_UNIT пуст, money=True → пустая единица",
  A._unit_for_measure("Сумма", money=True) == "", "")
t("no_data: MONEY_UNIT пуст, money=False → пусто",
  A._unit_for_measure("Количество", money=False) == "", "")
A.MONEY_UNIT = saved

# ═══ 3. «unknown» не уходит в текст ══════════════════════════════════════════

atom_unk = A.build_answer_atom(
    exact_value=99.0, measure_label="Сумма",
    unit_or_currency=A.UNIT_UNKNOWN)
pair_unk = A.render_atom_pair(atom_unk)
t("no_unknown: render с UNIT_UNKNOWN не содержит «unknown»",
  pair_unk is not None and "unknown" not in pair_unk, pair_unk)

atom_empty = A.build_answer_atom(
    exact_value=99.0, measure_label="Сумма",
    unit_or_currency="")
pair_empty = A.render_atom_pair(atom_empty)
t("no_unknown: render с пустой единицей — нет «unknown»",
  pair_empty is not None and "unknown" not in pair_empty, pair_empty)

atom_none = A.build_answer_atom(
    exact_value=99.0, measure_label="Сумма",
    unit_or_currency=None)
pair_none = A.render_atom_pair(atom_none)
t("no_unknown: render с None — нет «unknown»",
  pair_none is not None and "unknown" not in pair_none, pair_none)

# ═══ 4. rank fallback = compose по единице ════════════════════════════════════

agg_rank = {
    "count": 100, "sum": 500000.0, "grain": "group",
    "groups": [{"name": "Товар А", "value": 96620.0}],
    "n_groups": 5,
}

txt_no_unit = A.rank_leader_answer_text(agg_rank, measure_label="Сумма", unit="")
t("rank_unit: без единицы — число без суффикса",
  txt_no_unit is not None and "Товар А" in txt_no_unit
  and not txt_no_unit.rstrip().endswith(" "), txt_no_unit)

txt_with_unit = A.rank_leader_answer_text(agg_rank, measure_label="Сумма", unit="лей")
t("rank_unit: unit=лей — лей в тексте",
  txt_with_unit is not None and "лей" in txt_with_unit, txt_with_unit)

txt_unk_unit = A.rank_leader_answer_text(agg_rank, measure_label="Сумма", unit=A.UNIT_UNKNOWN)
t("rank_unit: UNIT_UNKNOWN — нет в тексте",
  txt_unk_unit is not None and "unknown" not in txt_unk_unit, txt_unk_unit)

# ═══ 5. env перекрывает ══════════════════════════════════════════════════════

saved2 = A.MONEY_UNIT
A.MONEY_UNIT = "₺"
t("env_override: MONEY_UNIT=₺ → _unit_for_measure отдаёт ₺",
  A._unit_for_measure("СуммаДокумента", money=True) == "₺", "")

atom_env = A.build_answer_atom(
    exact_value=77.0, measure_label="Итого",
    unit_or_currency=A._unit_for_measure("СуммаДокумента", money=True))
pair_env = A.render_atom_pair(atom_env)
t("env_override: ₺ в render_atom_pair",
  pair_env is not None and "₺" in pair_env, pair_env)
A.MONEY_UNIT = saved2

# ═══ 6. atom_from_agg использует _unit_for_measure ═══════════════════════════

saved3 = A.MONEY_UNIT
A.MONEY_UNIT = "€"
agg_simple = {"count": 10, "sum": 50000.0, "grain": "row"}
atom_agg = A.atom_from_agg(agg_simple, operation="sum",
                            measure_id="Сумма", money=True)
t("atom_agg: money=True → unit = MONEY_UNIT",
  atom_agg.get("unit_or_currency") == "€", atom_agg.get("unit_or_currency"))

atom_agg_qty = A.atom_from_agg(agg_simple, operation="count",
                                measure_id="Количество", money=False)
t("atom_agg: money=False → unit пусто",
  atom_agg_qty.get("unit_or_currency") == "", atom_agg_qty.get("unit_or_currency"))
A.MONEY_UNIT = saved3

# ═══ 7. postprocess_money_answer_text = identity ═════════════════════════════

sample = "Товар X: 96 620 шт. Общее количество по перечисленным: 100 шт."
t("postprocess: identity — текст не меняется",
  A.postprocess_money_answer_text(sample, unit="лей") == sample, "")
t("postprocess: пустой текст — identity",
  A.postprocess_money_answer_text("") == "", "")

# ═══ grep-замок: «шт» / «руб» / RU-слов для единицы в _unit_for_measure нет ═

import inspect
_src_lines = inspect.getsource(A._unit_for_measure).splitlines()
_body_lines = [l for l in _src_lines if not l.lstrip().startswith(('"""', '#'))]
_body = "\n".join(_body_lines)
t("grep: нет хардкода «шт» в теле _unit_for_measure",
  "\u0448\u0442" not in _body, "")
t("grep: нет хардкода «руб» в теле _unit_for_measure",
  "\u0440\u0443\u0431" not in _body, "")
t("grep: нет хардкода «количество» в теле _unit_for_measure",
  "\u043a\u043e\u043b\u0438\u0447\u0435\u0441\u0442\u0432\u043e" not in _body.lower(), "")

# ═══════════════════════════════════════════════════════════════════════════════

print("\n%d ok, %d fail" % (ok_n, fail_n))
if fails:
    print("failed:", ", ".join(fails))
sys.exit(1 if fail_n else 0)
