#!/usr/bin/env python3
"""Оффлайн-замки K5 / ASK_ATOM_TERMINAL (work/silent-refusal-fix-design.md §5–§6).

Контракт: computed-атом терминален; флаг 0 = прежнее поведение.
Компенсации: ≥2 классов ≠ unique; гейт прозы цел; compare ≠ rank + sum-путь.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ASK_TOKEN", "test")
os.environ.setdefault("EMBED_BASE_URL", "-")
os.environ.setdefault("EMBED_MODEL", "-")
os.environ.pop("ASK_ATOM_TERMINAL", None)

import serene_ask as A  # noqa: E402

PASS, FAIL = 0, []


def t(name, cond, detail=None):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, detail if detail is not None else "")


def _flag(on):
    saved = os.environ.get("ASK_ATOM_TERMINAL")
    if on:
        os.environ["ASK_ATOM_TERMINAL"] = "1"
    else:
        os.environ.pop("ASK_ATOM_TERMINAL", None)
    A.ASK_ATOM_TERMINAL = os.environ.get("ASK_ATOM_TERMINAL", "0") == "1"
    return saved


def _restore(saved):
    if saved is None:
        os.environ.pop("ASK_ATOM_TERMINAL", None)
    else:
        os.environ["ASK_ATOM_TERMINAL"] = saved
    A.ASK_ATOM_TERMINAL = os.environ.get("ASK_ATOM_TERMINAL", "0") == "1"


t("ASK_ATOM_TERMINAL default off", A.ASK_ATOM_TERMINAL is False)


def row(n, folders=0, **sums):
    return {"count": n, "folders": folders, "sums": sums}


# ── K5a: unique + computed → early answer ─────────────────────────────────────
_s = _flag(1)
cls_u = A.fork_classes({"doc": row(307)}, "count", want="count",
                       rel_by_src={"doc": []})
out_u, pay_u = A.resolve_fork_outcome(
    cls_u, {"doc": row(307)}, "count", want="count")
t("K5a resolve → unique", out_u == "unique")
_atom_u = ((pay_u.get("class") or {}).get("atom") or {})
t("K5a unique atom computed",
  _atom_u.get("proof_status") == A.PROOF_COMPUTED
  and _atom_u.get("exact_value") == 307,
  _atom_u)
_ans_u = A.fork_outcome_unique(
    "сколько документов реализации за декабрь 2025?",
    pay_u.get("class"), {"focus": "doc"})
t("K5a unique→answer kind",
  _ans_u and _ans_u.get("kind") in ("answer", "figures"),
  (_ans_u or {}).get("kind"))
t("K5a unique→answer несёт 307",
  _ans_u and "307" in str((_ans_u or {}).get("text") or ""),
  (_ans_u or {}).get("text"))
t("K5a unique diag fork_outcome",
  ((_ans_u or {}).get("diag") or {}).get("fork_outcome") == "unique")
_restore(_s)

_s = _flag(0)
t("flag0: fork_outcome_unique всё равно строит пару (строитель чистый)",
  A.fork_outcome_unique("q", pay_u.get("class"), {}) is not None)
# ранний выход в answer() завязан на флаг — проверяем гейт флага отдельно
t("flag0: ASK_ATOM_TERMINAL is False", A.ASK_ATOM_TERMINAL is False)
_restore(_s)


# ── компенсация: ≥2 live classes → B/C, не unique ─────────────────────────────
A.fork_labels_of = lambda fk, srcs: {"a": "Отгрузки", "b": "Оплаты"}
cls2 = A.fork_classes(
    {"a": row(10, Сумма=100.0), "b": row(10, Сумма=200.0)},
    "сумма", want="sum",
    rel_by_src={"a": ["Сумма"], "b": ["Сумма"]})
out2, pay2 = A.resolve_fork_outcome(
    cls2,
    {"a": row(10, Сумма=100.0), "b": row(10, Сумма=200.0)},
    "сумма", want="sum",
    rel_by_src={"a": ["Сумма"], "b": ["Сумма"]})
t("компенсация: 2 класса → не unique", out2 in ("B", "C"), out2)
t("компенсация: 2 класса с подписями → B", out2 == "B", out2)

A.fork_labels_of = lambda fk, srcs: {}
out2c, _ = A.resolve_fork_outcome(
    cls2,
    {"a": row(10, Сумма=100.0), "b": row(10, Сумма=200.0)},
    "сумма", want="sum",
    rel_by_src={"a": ["Сумма"], "b": ["Сумма"]})
t("компенсация: 2 класса без подписей → C", out2c == "C", out2c)


# ── mute + пустые rivals → не entity-clarify без лидера ───────────────────────
_s = _flag(1)
_mute = {
    "document_реализациятмц": {
        "kind": "clarify",
        "text": "",
        "atom": {
            "operation": "count",
            "exact_value": 307,
            "display_value": "307",
            "measure_label": "Реализация ТМЦ",
            "proof_status": A.PROOF_COMPUTED,
            "unit_or_currency": A.UNIT_UNKNOWN,
        },
        "figures": {"count": 307},
    }
}
_figs_zero = [{"count": 0}, {"count": 0}]
_prom = A.prefer_mute_computed_over_clarify(
    _mute, "document_реализациятмц", _figs_zero, question="сколько документов?")
t("mute+computed: prefer лидера, не clarify",
  _prom is not None
  and _prom.get("kind") in ("answer", "figures")
  and "307" in str(_prom.get("text") or ""),
  _prom)
_restore(_s)

_s = _flag(0)
t("flag0: prefer_mute → None",
  A.prefer_mute_computed_over_clarify(
      _mute, "document_реализациятмц", _figs_zero, question="q") is None)
_restore(_s)


# ── K5b: form=compare → slot_mode не rank; figures с sum ──────────────────────
_s = _flag(1)
_sm_cmp = A.answer_slot_mode("sum", "sum", form="compare", grain="row")
t("K5b flag1: compare → slot_mode ≠ rank", _sm_cmp != "rank", _sm_cmp)
t("K5b flag1: compare → slot_mode compare|sum",
  _sm_cmp in ("compare", "sum"), _sm_cmp)
_agg_cmp = {
    "count": 50, "sum": 1755883.45, "form": "compare", "grain": "row",
    "max": 100.0, "min": 1.0, "avg": 10.0,
}
_slots = A.compose_slot_values(
    _agg_cmp, measure="Всего", money=True, slot_mode=_sm_cmp)
t("K5b figures содержат sum/diff",
  _slots.get("sum") == 1755883.45, _slots)
_op = A.atom_operation("sum", "sum", form="compare", grain="row",
                       slot_mode=_sm_cmp)
t("K5b atom_operation остаётся compare", _op == "compare", _op)
_restore(_s)

_s = _flag(0)
t("flag0: compare → slot_mode rank (прежнее)",
  A.answer_slot_mode("sum", "sum", form="compare", grain="row") == "rank")
_restore(_s)


# ── K5b: gate-fail + computed → render_atom_pair, не refuse ───────────────────
_atom_cmp = A.build_answer_atom(
    operation="compare", exact_value=1755883.45,
    measure_label="Реализация ТМЦ", form="compare",
    proof_status=A.PROOF_COMPUTED, unit_or_currency="лей")
_s = _flag(1)
_txt = A.atom_terminal_gate_text(
    _atom_cmp, "в этом месяце продали больше, чем в прошлом?",
    agg=_agg_cmp)
_pair = A.render_atom_pair(_atom_cmp)
t("K5b gate-fail text = render_atom_pair",
  _txt == _pair and _txt and "1755883" in _txt.replace(" ", "").replace("\xa0", ""),
  (_txt, _pair))
t("K5b gate-fail не refuse_text",
  _txt and "невозможно" not in (_txt or "").lower())
_restore(_s)

_s = _flag(0)
# без TOTAL_TEXT и с флагом 0 — путь к refuse (модель); мокаем
_old_refuse = A.refuse_text
A.refuse_text = lambda q: "REFUSE_STUB"
_txt0 = A.atom_terminal_gate_text(
    _atom_cmp, "в этом месяце продали больше, чем в прошлом?",
    agg=_agg_cmp)
t("flag0: gate-fail → refuse/TOTAL (не пара атома)",
  _txt0 == "REFUSE_STUB" or (_txt0 != _pair),
  _txt0)
A.refuse_text = _old_refuse
_restore(_s)


# ── компенсация: гейт прозы всё ещё ловит рукопись на пути ok ─────────────────
_hand = A.copied_figures(
    "Итого продали 1755883.45 лей за месяц",
    _agg_cmp, rows=[])
t("гейт прозы: рукопись ловится",
  bool(_hand) and any("цифрами" in str(x) for x in _hand),
  _hand)


# ── компенсация: sum-путь «сколько продали вчера» без смены kind ─────────────
_s = _flag(1)
_sm_sum = A.answer_slot_mode("sum", "sum", form="number", grain="row")
t("sum-путь: form=number → sum", _sm_sum == "sum", _sm_sum)
_slots_sum = A.compose_slot_values(
    {"count": 19, "sum": 112325.97, "grain": "row"},
    measure="Всего", money=True, slot_mode=_sm_sum)
t("sum-путь: figures.sum на месте",
  _slots_sum.get("sum") == 112325.97, _slots_sum)
_sm_rank = A.answer_slot_mode("list", "sum", form="rank", grain="group")
t("rank-путь: form=rank остаётся rank", _sm_rank == "rank", _sm_rank)
_restore(_s)

_s = _flag(0)
t("flag0: number→sum как раньше",
  A.answer_slot_mode("sum", "sum", form="number", grain="row") == "sum")
t("flag0: rank→rank как раньше",
  A.answer_slot_mode("list", "sum", form="rank", grain="group") == "rank")
_restore(_s)


print()
if FAIL:
    print("ПРОВАЛЕНО:", len(FAIL), "из", PASS + len(FAIL), FAIL)
    sys.exit(1)
print("все", PASS, "проверок зелёные")
