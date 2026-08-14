#!/usr/bin/env python3
"""Оффлайн: паспорт набора решений (слой 1 видимости). Без базы, сети, модели.

Фикстуры без имён боевой базы. Мерило: окно/источник/величина/ось только из
переданных подписей; assumed/prior — маркеры; src_table в текст не утекает;
гейт пропускает ISO фильтра (F245).
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


# -------- нет period → нет окна
frag, fields = A.build_answer_passport(
    period={}, src_label="Alpha", src_kind="catalog", measure="Qty")
t("нет period: окна нет", "2026" not in frag and ".." not in frag)
t("нет period: источник и величина есть",
  "Alpha" in frag and "Qty" in frag and fields.get("label") == "Alpha"
  and fields.get("measure") == "Qty")
t("нет period: from/to в figures нет",
  "from" not in fields and "to" not in fields)

# -------- окно ISO + assumed
frag, fields = A.build_answer_passport(
    period={"from": "2026-08-07", "to": "2026-08-14"},
    origin="assumed",
    src_label="Alpha", src_kind="catalog", measure="Qty")
t("окно ISO + assumed",
  frag.startswith("2026-08-07..2026-08-14 assumed")
  and fields.get("from") == "2026-08-07" and fields.get("to") == "2026-08-14")
t("assumed — маркер, не проза",
  "assumed" in frag and "дат" not in frag.lower()
  and "предыдущ" not in frag.lower() and "недел" not in frag.lower())

# -------- prior
frag, _ = A.build_answer_passport(
    period={"from": "2026-08-12", "to": "2026-08-12"},
    origin="prior", src_label="Alpha", measure="Qty")
t("prior — маркер рядом с ISO",
  "2026-08-12..2026-08-12 prior" in frag)

# -------- period_dropped: снятый фильтр не как применённый
frag, fields = A.build_answer_passport(
    period={"from": "2026-01-01", "to": "2026-12-31"},
    period_dropped=True, origin="assumed",
    src_label="Alpha", measure="Qty")
t("period_dropped: окна нет",
  "2026-01-01" not in frag and "from" not in fields)
t("period_dropped: источник остаётся", "Alpha" in frag and "Qty" in frag)

# -------- grain=row → нет группировки
frag, _ = A.build_answer_passport(
    period={"from": "2026-08-07", "to": "2026-08-14"},
    src_label="Beta", src_kind="document", measure="Qty",
    grain="row", axis_label="Gamma", form="number")
t("grain=row: оси нет даже если передали label",
  "Gamma" not in frag)

# -------- grain=group + метка оси
frag, _ = A.build_answer_passport(
    period={"from": "2026-08-07", "to": "2026-08-14"},
    src_label="Beta", src_kind="document", measure="Qty",
    grain="group", axis_label="Gamma", form="rank")
t("grain=group: ось из метки", "Gamma" in frag and "rank" in frag)

# -------- grain=group без метки оси → не выдумывать
frag, _ = A.build_answer_passport(
    src_label="Beta", measure="Qty",
    grain="group", axis_label="", form="rank")
t("grain=group без метки оси: оси нет",
  "Gamma" not in frag and frag.count(" · ") <= 2)

# -------- внутренний src_table в текст не класть
frag, fields = A.build_answer_passport(
    src_label="", src_kind="catalog", measure="Qty")
t("пустая метка: src_table не подставляется",
  "catalog_alpha" not in frag and "document_beta" not in frag
  and fields.get("label") is None)

frag, _ = A.build_answer_passport(
    src_label="Alpha", src_kind="catalog", measure="Qty")
t("источник — label + kind_word, не src",
  "Alpha (catalog)" in frag and "catalog_alpha" not in frag)

# -------- дедуп ISO уже в тексте
frag, _ = A.build_answer_passport(
    period={"from": "2026-08-07", "to": "2026-08-14"},
    origin="assumed", src_label="Alpha", measure="Qty",
    text="Лидер 869 за 2026-08-07..2026-08-14")
t("ISO уже в тексте: окно не дублируется",
  "2026-08-07..2026-08-14 assumed" not in frag
  and "Alpha" in frag)

text = A.ensure_answer_passport("Лидер 869", frag)
t("ensure: дописывает · паспорт",
  text.startswith("Лидер 869") and "Alpha" in text)

text2 = A.ensure_answer_passport(text, frag)
t("ensure: повторно не дублирует", text2 == text)

# -------- F245: гейт пропускает ISO фильтра
_rows = [{"dummy": 1}]
# gate expects row tuples — use minimal via existing helper pattern from test_gate
def row(amount="869.00", when="2026-08-10", doc="x"):
    return (None, None, amount, when, None, doc)

ok, bad = A.gate(
    "Лидер 869 · 2026-08-07..2026-08-14 assumed · Alpha (catalog) · Qty",
    [row()],
    {"count": 1, "sum": 869.0, "grain": "row"},
    [],
    A._filter_dates({"period": {"from": "2026-08-07", "to": "2026-08-14"}}),
    money=True)
t("F245: ISO фильтра паспорта проходит гейт", ok and not bad)

ok2, _ = A.gate(
    "Лидер 869 · 2018-01-01..2018-01-02 · Alpha · Qty",
    [row()],
    {"count": 1, "sum": 869.0, "grain": "row"},
    [],
    A._filter_dates({"period": {"from": "2026-08-07", "to": "2026-08-14"}}),
    money=True)
t("F245: чужое окно не проходит", not ok2)

# -------- origin helpers
t("origin prior из diag",
  A._passport_origin({}, {"period_from_prior": True}) == "prior")
t("origin assumed из parse",
  A._passport_origin({"parse": {"assumed": ["period.from", "period.to"]}}, {})
  == "assumed")
t("origin пуст без prior/assumed",
  A._passport_origin({"parse": {"assumed": []}}, {}) == "")
t("prior сильнее assumed",
  A._passport_origin({"parse": {"assumed": ["period.from"]}},
                     {"period_from_prior": True}) == "prior")

# -------- form только rank/compare
frag, _ = A.build_answer_passport(
    src_label="Alpha", measure="Qty", form="number")
t("form=number не пишется", "number" not in frag)
frag, _ = A.build_answer_passport(
    src_label="Alpha", measure="Qty", form="compare")
t("form=compare — ASCII", frag.endswith("compare") or "compare" in frag)

print("\n%d проверок пройдено" % PASS)
if FAIL:
    print("ПРОВАЛЕНО %d: %s" % (len(FAIL), "; ".join(FAIL)))
    raise SystemExit(1)
