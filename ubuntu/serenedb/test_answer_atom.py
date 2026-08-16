#!/usr/bin/env python3
"""Типизированный AnswerAtom + детерминированный renderer (план §5, аудит §17).

Замки:
  · build_answer_atom — одно место сборки;
  · render_atom_pair — пара целиком; непосчитанный → None;
  · fill_atom_pairs — только {pair:pN}; нет API смешать label↔value;
  · при нескольких парах compose не открывает одиночные числовые места;
  · перепутанные подписи фразу не собирают (по построению).

Запуск:  python3 ubuntu/serenedb/test_answer_atom.py
Без базы, сети и вызовов модели.
"""
import inspect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ASK_TOKEN", "test")
os.environ.setdefault("EMBED_BASE_URL", "-")
os.environ.setdefault("EMBED_MODEL", "-")

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


# ── строитель ──────────────────────────────────────────────────────────────────
a = A.build_answer_atom(
    operation="sum", exact_value=1310413.93,
    measure_id="Сумма", measure_label="Реализация ТМЦ",
    period={"from": "2025-07-01", "to": "2025-07-31", "origin": "prior"},
    proof_status=A.PROOF_COMPUTED)
t("атом: operation/exact/display/measure_label/unit",
  a["operation"] == "sum"
  and a["exact_value"] == 1310413.93
  and a["display_value"] == "1310413.93"
  and a["measure_label"] == "Реализация ТМЦ"
  and a["unit_or_currency"] == A.UNIT_UNKNOWN
  and a["period"]["origin"] == "prior"
  and a["proof_status"] == A.PROOF_COMPUTED)

t("единица пустая → явный unknown",
  A.build_answer_atom(exact_value=1, unit_or_currency="")["unit_or_currency"]
  == A.UNIT_UNKNOWN)

t("atom_from_agg: count без величины",
  A.atom_from_agg({"count": 19}, operation="count", money=False)["exact_value"] == 19)

t("atom_operation: count/sum/rank/compare",
  A.atom_operation(want="count", compute="count") == "count"
  and A.atom_operation(want="sum", compute="sum") == "sum"
  and A.atom_operation(form="rank", grain="group") == "rank"
  and A.atom_operation(form="compare", grain="group") == "compare")

# ── renderer ───────────────────────────────────────────────────────────────────
pair = A.render_atom_pair(a)
t("render_atom_pair: подпись + число + unknown одной строкой",
  pair is not None
  and "Реализация ТМЦ" in pair
  and "1310413.93" in pair
  and "unknown" in pair)

unc = A.build_answer_atom(operation="sum", exact_value=None,
                          measure_label="X", proof_status=A.PROOF_UNCOUNTED)
t("непосчитанный атом → пара не собирается",
  A.render_atom_pair(unc) is None)

# ── замок: перепутанные подписи не собираются ─────────────────────────────────
a1 = A.build_answer_atom(operation="sum", exact_value=100,
                         measure_label="Отгрузки", proof_status=A.PROOF_COMPUTED)
a2 = A.build_answer_atom(operation="sum", exact_value=200,
                         measure_label="Оплаты", proof_status=A.PROOF_COMPUTED)
p0 = A.render_atom_pair(a1)
p1 = A.render_atom_pair(a2)
t("две пары различны и несут свои подписи",
  p0 != p1 and "Отгрузки" in p0 and "100" in p0
  and "Оплаты" in p1 and "200" in p1)

# Публичного API «подпись + число» порознь нет — только целый атом.
sig = inspect.signature(A.render_atom_pair)
t("render_atom_pair принимает ровно атом (нет label=, value=)",
  list(sig.parameters) == ["atom"])
t("отдельного render_pair(label, value) в модуле нет",
  not hasattr(A, "render_pair"))

# fill_atom_pairs: {pair:p0} всегда даёт пару a1 целиком — нельзя подставить label a2.
filled, bad = A.fill_atom_pairs("A={pair:p0}; B={pair:p1}", [a1, a2])
t("fill: p0/p1 — целые пары своих атомов",
  not bad and filled == "A=%s; B=%s" % (p0, p1))

# Попытка «перепутать»: модель пишет только индексы; чужую подпись рядом с чужим
# числом поставить нечем. Даже если вручную склеить label a2 + value a1 —
# такого API у fill/render нет, а результат fill не содержит такой склейки.
swapped_wish = "Оплаты: 100"
t("перепутанная склейка отсутствует в результате fill_atom_pairs",
  swapped_wish not in filled
  and A.fill_atom_pairs("{pair:p0}", [a1, a2])[0] != swapped_wish)

# Неверный индекс — место не заполняется (отказ), а не тихая чужая пара.
miss, miss_bad = A.fill_atom_pairs("X={pair:p9}", [a1, a2])
t("несуществующий pair → отказ места",
  miss_bad and "{pair:p9}" in miss)

# ── compose: при >1 паре только {pair:pN} ───────────────────────────────────────
agg = {"count": 2, "sum": 300, "measure": "Сумма", "grain": "row"}
_bodies = []
_real_ds = A.ds_chat

def _capture_ds(messages, temperature=0, max_tokens=900):
    _bodies.append(messages[1]["content"])
    return "x"  # модель не нужна: смотрим задание

A.ds_chat = _capture_ds
try:
    A.compose("сколько?", [], agg, money=True, slot_mode="sum", atom_pairs=[a1, a2])
    body_multi = _bodies[-1]
    A.compose("сколько?", [], agg, money=True, slot_mode="sum", atom_pairs=[a1])
    body_one = _bodies[-1]
finally:
    A.ds_chat = _real_ds

t("несколько пар: в задании есть {pair:p0} и {pair:p1}",
  "{pair:p0}" in body_multi and "{pair:p1}" in body_multi)
t("несколько пар: одиночного {total}/{count}/{max} нет",
  "{total}" not in body_multi and "{count}" not in body_multi
  and "{max}" not in body_multi and "{min}" not in body_multi)

t("одна пара: одиночные слоты по-прежнему есть (аддитивно)",
  "{total}" in body_one or "{count}" in body_one)

t("pair_slots_only: >1 → True, 1 → False",
  A.pair_slots_only(2) is True and A.pair_slots_only(1) is False)

# ── whitelist ───────────────────────────────────────────────────────────────────
t("whitelist labels из атомов",
  A.atom_whitelist_labels([a1, a2]) == ["Отгрузки", "Оплаты"])
t("whitelist numbers из атомов",
  A.atom_whitelist_numbers([a1, a2]) == [100, 200])

print()
if FAIL:
    print("ПРОВАЛЕНО:", len(FAIL), "из", PASS + len(FAIL))
    for n in FAIL:
        print(" ", n)
    sys.exit(1)
print("все", PASS, "проверок зелёные")
