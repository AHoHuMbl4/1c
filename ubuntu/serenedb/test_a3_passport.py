#!/usr/bin/env python3
"""A3 на БОЕВОЙ форме `figures`: счёт + даты + паспорт from/to/label/measure.

Аудит `docs/AUDIT_ABC_MODEL_2026-08-15.md` §5.2: на проде `figures` ответа — это
`compose_slot_values()` ПЛЮС паспорт набора (`from`/`to`/`label`/`measure`), а прежний
`_slot_fp` приводил каждый не-date ключ к числу и на строковом `label`/`measure`
возвращал `None` → `answers_diverge` считало это расхождением → `answers_src_conflict`
на боевой форме был недостижим (`passport_A3=False`). Существующие пробы
(`test_step4_guards.py`) используют голый `{"count": 19}` и боевую форму не
воспроизводили.

Здесь `figures` собирается ТЕМИ ЖЕ функциями и в том же виде, что в `answer()`:
числа — `compose_slot_values`, паспорт — `build_answer_passport`, слияние — `update`.

Запуск:  python3 ubuntu/serenedb/test_a3_passport.py
Без базы, сети и вызовов модели.
"""
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


def battle_figures(src_label, measure, count=19,
                   dmin="2025-07-01", dmax="2025-07-31",
                   pf="2025-07-01", pt="2025-07-31"):
    """Боевая форма figures: числа compose + паспорт, как в answer() (две ветки)."""
    agg = {"count": count, "date_min": dmin, "date_max": dmax}
    figs = A.compose_slot_values(agg, measure=measure, money=False, slot_mode="count")
    _frag, fields = A.build_answer_passport(
        period={"from": pf, "to": pt}, origin="",
        src_label=src_label, src_kind="документ",
        measure=measure or "", text="")
    figs.update(fields or {})
    return figs


# ── Это действительно боевая форма: паспорт присутствует ────────────────────────────
_doc = battle_figures("Реализация ТМЦ", "Сумма")
_book = battle_figures("Книга продаж", "Сумма")
t("боевая форма: есть count, date_min/date_max и паспорт from/to/label/measure",
  all(k in _doc for k in ("count", "date_min", "date_max",
                          "from", "to", "label", "measure")))
t("отпечаток боевой формы не None (паспорт больше не ломает типизацию)",
  A._slot_fp(_doc) is not None and A._slot_fp(_book) is not None)

# ── A3 достижим: два разных src, одинаковые числа и квалификаторы ───────────────────
t("A3 боевой формы: одинаковые числа и квалификаторы, разные src — не расхождение",
  A.answers_diverge([_doc, _book]) is False)
t("A3 боевой формы: два src с совпавшим атомом — answers_src_conflict=True",
  A.answers_src_conflict([
      {"src": "document_sale", "kind": "answer", "figures": _doc},
      {"src": "register_book", "kind": "answer", "figures": _book}]) is True)

# ── Разные квалификаторы — это разные ответы (ветка diverge, не A3) ──────────────────
_doc_qty = battle_figures("Реализация ТМЦ", "Количество")
t("разное measure — расхождение (не согласие)",
  A.answers_diverge([_doc, _doc_qty]) is True)
t("разное measure — не ветка A3",
  A.answers_src_conflict([
      {"src": "document_sale", "kind": "answer", "figures": _doc},
      {"src": "register_book", "kind": "answer", "figures": _doc_qty}]) is False)
_doc_june = battle_figures("Реализация ТМЦ", "Сумма", pf="2025-06-01", pt="2025-06-30")
t("разный период паспорта — расхождение",
  A.answers_diverge([_doc, _doc_june]) is True)
t("разный период паспорта — не ветка A3",
  A.answers_src_conflict([
      {"src": "document_sale", "kind": "answer", "figures": _doc},
      {"src": "register_book", "kind": "answer", "figures": _doc_june}]) is False)
_doc_dates = battle_figures("Реализация ТМЦ", "Сумма",
                            dmin="2025-07-02", dmax="2025-07-30")
t("разные служебные даты набора — расхождение",
  A.answers_diverge([_doc, _doc_dates]) is True)

# ── label — производная src и в сравнение не входит ──────────────────────────────────
_same_other_label = battle_figures("Совсем другая метка", "Сумма")
t("метка источника различна — атом всё равно один (label исключён)",
  A.answers_diverge([_doc, _same_other_label]) is False)

# ── Голые {"count": 19} — прежнее поведение сохранено ───────────────────────────────
t("голый счёт: 19=19 не расхождение",
  A.answers_diverge([{"count": 19}, {"count": 19}]) is False)
t("голый счёт: 19=19 при разных src — A3, как прежде",
  A.answers_src_conflict([
      {"src": "a", "kind": "answer", "figures": {"count": 19}},
      {"src": "b", "kind": "answer", "figures": {"count": 19}}]) is True)
t("голый счёт: 19 против 20 — расхождение",
  A.answers_diverge([{"count": 19}, {"count": 20}]) is True)
t("сравнивать нечем (пустой figures) — расхождение, как прежде",
  A.answers_diverge([{"count": 19}, {}]) is True)

print()
if FAIL:
    print("ПРОВАЛЕНО:", len(FAIL), "из", PASS + len(FAIL))
    sys.exit(1)
print("все", PASS, "проверок зелёные")
