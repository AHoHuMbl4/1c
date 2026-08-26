#!/usr/bin/env python3
"""Офлайн-замок п. 13: признак потери → пометка клиенту (Э4).

Инвариант: has_loss_signal(out) ⇒ client_mark_present(out).
Падает, когда потеря есть, а в ответе нет ни LOSS-ключей в partial
(мост PARTIAL), ни цифры/ноты потери в text.

Без сети и базы. serene_ask.py не правится — только читается через импорт.
См. docs/COMPLETENESS_P13.md §8–§10.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ASK_TOKEN", "test")
os.environ.setdefault("EMBED_BASE_URL", "-")
os.environ.setdefault("EMBED_MODEL", "-")

import serene_ask as A  # noqa: E402

PASS, FAIL = 0, []

LOSS_PARTIAL_KEYS = frozenset({
    "coverage_missing", "undated_excluded", "intent_lost",
})
BUDGET_KEYS = (
    ("entities_shown", "entities_total"),
    ("partial_shown", "partial_total"),
    ("reranked", "reranked_of"),
)
UNCOUNTED_NOTE = "часть прочтений не удалось посчитать"


def t(name, cond, detail=None):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, detail if detail is not None else "")


def _atoms_of(out):
    atoms = []
    if isinstance(out.get("atom"), dict):
        atoms.append(out["atom"])
    for a in (out.get("atoms") or []):
        if isinstance(a, dict) and "atom" in a and isinstance(a["atom"], dict):
            atoms.append(a["atom"])
        elif isinstance(a, dict):
            atoms.append(a)
    return atoms


def _norm_nums(text):
    return A._norm_numbers(text or "")


def loss_values(out):
    """Числа потери — те, что видны клиенту цифрой или PARTIAL-ключом."""
    vals = []
    partial = out.get("partial") if isinstance(out.get("partial"), dict) else {}
    for k in LOSS_PARTIAL_KEYS:
        v = partial.get(k)
        if v is None:
            continue
        try:
            vals.append(float(v))
        except (TypeError, ValueError):
            pass
    for atom in _atoms_of(out):
        excl = atom.get("excluded") if isinstance(atom.get("excluded"), dict) else {}
        for k in ("folders", "undated", "outside_period"):
            if excl.get(k) is not None:
                try:
                    vals.append(float(excl[k]))
                except (TypeError, ValueError):
                    pass
        comp = atom.get("completeness") if isinstance(atom.get("completeness"), dict) else {}
        if comp.get("missing") is not None:
            try:
                vals.append(float(comp["missing"]))
            except (TypeError, ValueError):
                pass
    sb = ((out.get("diag") or {}).get("selection_budget")
          if isinstance(out.get("diag"), dict) else None) or {}
    if isinstance(sb, dict):
        for shown_k, total_k in BUDGET_KEYS:
            shown, total = sb.get(shown_k), sb.get(total_k)
            if shown is None or total is None:
                continue
            try:
                if int(total) > int(shown):
                    vals.append(float(total))
                    vals.append(float(shown))
            except (TypeError, ValueError):
                pass
    # budget keys already mirrored into partial (после будущей починки)
    if isinstance(partial, dict):
        for shown_k, total_k in BUDGET_KEYS:
            shown, total = partial.get(shown_k), partial.get(total_k)
            if shown is None or total is None:
                continue
            try:
                if int(total) > int(shown):
                    vals.append(float(total))
                    vals.append(float(shown))
            except (TypeError, ValueError):
                pass
    return vals


def has_loss_signal(out):
    """Признак потери счёта/отбора (не C5 atoms_truncated, не _JOURNAL_LOST)."""
    if not isinstance(out, dict):
        return False
    partial = out.get("partial") if isinstance(out.get("partial"), dict) else {}
    for k in LOSS_PARTIAL_KEYS:
        if partial.get(k) not in (None, "", 0, "0"):
            return True
    lim = partial.get("fork_limitation") if isinstance(partial, dict) else None
    if isinstance(lim, dict) and int(lim.get("uncounted_classes") or 0) > 0:
        return True
    for atom in _atoms_of(out):
        excl = atom.get("excluded") if isinstance(atom.get("excluded"), dict) else {}
        if any(excl.get(k) for k in ("folders", "undated", "outside_period")):
            return True
        comp = atom.get("completeness") if isinstance(atom.get("completeness"), dict) else {}
        if comp.get("missing"):
            return True
    diag = out.get("diag") if isinstance(out.get("diag"), dict) else {}
    sb = diag.get("selection_budget") if isinstance(diag.get("selection_budget"), dict) else {}
    for shown_k, total_k in BUDGET_KEYS:
        shown, total = sb.get(shown_k), sb.get(total_k)
        if shown is None or total is None:
            continue
        try:
            if int(total) > int(shown):
                return True
        except (TypeError, ValueError):
            pass
    # budget already in partial
    for shown_k, total_k in BUDGET_KEYS:
        shown, total = partial.get(shown_k), partial.get(total_k)
        if shown is None or total is None:
            continue
        try:
            if int(total) > int(shown):
                return True
        except (TypeError, ValueError):
            pass
    fork = diag.get("fork") if isinstance(diag.get("fork"), dict) else {}
    if fork.get("uncounted"):
        return True
    inc = diag.get("incomplete") if isinstance(diag.get("incomplete"), dict) else {}
    if inc.get("missing"):
        return True
    return False


def client_mark_present(out):
    """Пометка видна клиенту: LOSS в partial и/или цифра/нота в text."""
    if not isinstance(out, dict):
        return False
    partial = out.get("partial") if isinstance(out.get("partial"), dict) else {}
    for k in LOSS_PARTIAL_KEYS:
        if partial.get(k) not in (None, "", 0, "0"):
            return True  # мост mcp_ask._with_partial допишет PARTIAL
    # budget в partial + цифра в тексте (мост budget не показывает)
    text = out.get("text") or ""
    have = _norm_nums(text)
    for v in loss_values(out):
        if v in have or round(v, 2) in have:
            return True
    low = text.lower()
    if UNCOUNTED_NOTE in low:
        return True
    if "undated=" in low or "missing=" in low or "folders=" in low:
        return True
    if "всего позиций:" in low or "всего записей:" in low:
        return True
    lim = partial.get("fork_limitation") if isinstance(partial, dict) else None
    if isinstance(lim, dict) and int(lim.get("uncounted_classes") or 0) > 0:
        if UNCOUNTED_NOTE in low:
            return True
        # fork_limitation в partial → partial_flag журнала, но мост не показывает;
        # без ноты в text считаем непомеченным для клиента
        return False
    # budget только в partial без цифр в text — для клиента молчание (S8)
    return False


def invariant_holds(out):
    if not has_loss_signal(out):
        return True
    return client_mark_present(out)


# ── хелперы, которые уже держат пометку ──────────────────────────────────────

_atom_miss = {
    "operation": "sum",
    "exact_value": 100,
    "display_value": "100",
    "measure_label": "Сумма",
    "unit_or_currency": "RUB",
    "proof_status": A.PROOF_COMPUTED,
    "completeness": {"missing": 104, "in_1c": 200, "in_search": 96},
    "excluded": {"undated": 12, "folders": 3},
}
_rendered = A.render_atom_pair(_atom_miss)
t("render_atom_pair: missing в тексте",
  _rendered is not None and "missing=" in (_rendered or "") and "104" in (_rendered or ""),
  _rendered)
t("render_atom_pair: undated/folders в тексте",
  _rendered is not None and "undated=" in (_rendered or "") and "folders=" in (_rendered or ""),
  _rendered)

_agg_g = {"grain": "group", "n_groups": 40, "groups": [{"k": "a", "sum": 1}] * 5,
          "count": 5, "sum": 5.0}
_txt_g = A.ensure_n_groups_named("лидер: a", _agg_g)
t("ensure_n_groups_named дописывает n_groups",
  "40" in _txt_g and "всего позиций" in _txt_g, _txt_g)

_miss_f = A.asked_figure_missing("итого 100", {"count": 10, "sum": 100.0},
                                 "sum", True, folders=7)
t("asked_figure_missing требует folders",
  _miss_f is not None and "7" in str(_miss_f), _miss_f)

# ── фикстуры: инвариант обязан держаться ─────────────────────────────────────

_ok_loss_partial = {
    "kind": "answer",
    "text": "итого 500",
    "partial": {"coverage_missing": 104},
    "diag": {},
}
t("invariant: LOSS в partial → ok (мост PARTIAL)",
  invariant_holds(_ok_loss_partial))

_ok_digit = {
    "kind": "answer",
    "text": "итого 500; не дошло 104 строки",
    "partial": None,
    "atom": {"exact_value": 500, "proof_status": A.PROOF_COMPUTED,
             "completeness": {"missing": 104}},
    "diag": {},
}
t("invariant: missing в атоме + цифра в text → ok",
  invariant_holds(_ok_digit))

_ok_uncounted = {
    "kind": "clarify",
    "text": "уточните источник\n" + UNCOUNTED_NOTE,
    "partial": {"fork_limitation": {"reason": "uncounted_cell", "uncounted_classes": 2}},
    "diag": {},
}
t("invariant: uncounted + нота в text → ok",
  invariant_holds(_ok_uncounted))

_ok_budget_text = {
    "kind": "clarify",
    "text": "рассмотрено 12 видов из 226",
    "partial": None,
    "diag": {"selection_budget": {"entities_shown": 12, "entities_total": 226}},
}
t("invariant: budget в diag + цифры в text → ok",
  invariant_holds(_ok_budget_text))

t("invariant: нет потери → ok",
  invariant_holds({"kind": "answer", "text": "42", "partial": None, "diag": {}}))

# ── фикстуры молчания: инвариант ОБЯЗАН падать (класс дефекта до починки) ────
# После ensure_partial_visible эти кейсы должны стать ok.

_silent_budget = {
    "kind": "answer",
    "text": "итого 1 000 000",
    "partial": None,
    "diag": {"selection_budget": {
        "entities_shown": 12, "entities_total": 226,
        "reranked": 60, "reranked_of": 1502,
        "partial_shown": 40, "partial_total": 200,
    }},
}
t("invariant: selection_budget только в diag → пометка клиенту",
  invariant_holds(_silent_budget),
  "S1–S3: budget в diag, partial=None, text без цифр отбора")

_silent_atom = {
    "kind": "answer",
    "text": "итого 500",
    "partial": None,
    "atom": {
        "exact_value": 500,
        "display_value": "500",
        "proof_status": A.PROOF_COMPUTED,
        "completeness": {"missing": 104},
        "excluded": {"undated": 54},
    },
    "diag": {},
}
t("invariant: missing/undated в атоме без text/partial → пометка",
  invariant_holds(_silent_atom),
  "S5–S7: атом знает потерю, проза молчит")

_silent_unc_diag = {
    "kind": "clarify",
    "text": "уточните вариант",
    "partial": None,
    "diag": {"fork": {"uncounted": [["a"], ["b"]], "atoms_truncated": 3}},
}
t("invariant: uncounted только в diag.fork → пометка",
  invariant_holds(_silent_unc_diag),
  "uncounted в diag без fork_outcome_c-ноты")

_silent_incomplete = {
    "kind": "answer",
    "text": "сумма 10",
    "partial": None,
    "diag": {"incomplete": {"missing": 881, "in_1c": 1000, "in_search": 119}},
}
t("invariant: diag.incomplete.missing без partial/text → пометка",
  invariant_holds(_silent_incomplete))

# ── журнал: C5 truncated ≠ клиентская потеря; partial_flag ↔ bool(partial) ───

_c5 = {"partial": None, "diag": {"fork": {"atoms_truncated": 7}}}
_unc, _trn = A._journal_uncounted_truncated(_c5)
t("journal: atoms_truncated → truncated", _trn == 7, (_unc, _trn))
t("C5: atoms_truncated alone — не has_loss_signal",
  not has_loss_signal(_c5))

_j_unc = {
    "partial": {"fork_limitation": {"uncounted_classes": 2}},
    "diag": {"fork": {}},
}
_u2, _t2 = A._journal_uncounted_truncated(_j_unc)
t("journal: uncounted_classes из partial", _u2 == 2, (_u2, _t2))

# partial_flag журнала = bool(partial); без ensure бюджет не поднимает флаг
t("journal-shaped: silent budget → partial_flag был бы false",
  not bool(_silent_budget.get("partial")))

# ── гейт не требует undated/missing (дыра S5/S6) — замок фиксирует ───────────

_no_undated_gate = A.asked_figure_missing(
    "итого 100",
    {"count": 10, "sum": 100.0, "undated": 54, "grain": "row"},
    "sum", True, folders=0)
t("asked_figure_missing не ловит undated — открытая дыра S6",
  _no_undated_gate is not None,
  _no_undated_gate)

# ── итог ─────────────────────────────────────────────────────────────────────

print()
print("passed:", PASS, "failed:", len(FAIL))
if FAIL:
    print("FAILED:", ", ".join(FAIL))
    sys.exit(1)
sys.exit(0)
