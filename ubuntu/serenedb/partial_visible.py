#!/usr/bin/env python3
"""п. 13 TARGET: признак потери → пометка клиенту (Э4).

Единая пост-обработка ответа: если в атоме/`diag`/partial есть потеря счёта
или обрезка отбора, а клиенту это не видно — дописать в `partial` и/или в
`text` кодом (не промтом). Образец — `stale_note` в serene_ask.

Вызов (патч оркестратора в serene_ask): в `answer_checked` finally, до
`_ask_journal_write`, и идемпотентно в Handler. Этот файл serene_ask не
импортирует на чтении — только наоборот, чтобы замок и мост жили отдельно.
"""
from __future__ import annotations

import re

LOSS_PARTIAL_KEYS = frozenset({
    "coverage_missing", "undated_excluded", "intent_lost",
})
BUDGET_KEYS = (
    ("entities_shown", "entities_total"),
    ("partial_shown", "partial_total"),
    ("reranked", "reranked_of"),
)
UNCOUNTED_NOTE = "часть прочтений не удалось посчитать"


def _fmt(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "0"
    return "%d" % v if v == int(v) else "%.2f" % v


def _norm_numbers(text):
    """Цифры из текста (достаточно для хвоста ensure; полный токенайзер — в ask)."""
    out = set()
    for m in re.finditer(r"\d+(?:[.,]\d+)?", text or ""):
        s = m.group(0).replace(",", ".")
        try:
            out.add(float(s))
        except ValueError:
            pass
    return out


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


def _ensure_partial_dict(out):
    p = out.get("partial")
    if isinstance(p, dict):
        return p
    p = {}
    out["partial"] = p
    return p


def _num_in_text(have, v):
    try:
        nf = float(v)
    except (TypeError, ValueError):
        return True
    return nf in have or round(nf, 2) in have


def ensure_partial_visible(out):
    """Сделать потерю видимой клиенту: partial (LOSS/budget) + цифры/нота в text.

    Мутирует `out` на месте и возвращает его. Идемпотентна.
    C5 `atoms_truncated` и `_JOURNAL_LOST` не трогает — это не потеря счёта клиенту.
    """
    if not isinstance(out, dict):
        return out
    text = out.get("text") or ""
    have = _norm_numbers(text)
    low = text.lower()
    partial = _ensure_partial_dict(out)
    diag = out.get("diag") if isinstance(out.get("diag"), dict) else {}
    changed_text = False

    # ── атом: missing / undated / folders ───────────────────────────────────
    for atom in _atoms_of(out):
        excl = atom.get("excluded") if isinstance(atom.get("excluded"), dict) else {}
        comp = atom.get("completeness") if isinstance(atom.get("completeness"), dict) else {}
        miss = comp.get("missing")
        if miss not in (None, "", 0, "0"):
            if partial.get("coverage_missing") in (None, "", 0, "0"):
                partial["coverage_missing"] = miss
            if not _num_in_text(have, miss) and "missing=" not in low:
                text = (text.rstrip() + " · missing=%s" % _fmt(miss)).strip()
                have = _norm_numbers(text)
                low = text.lower()
                changed_text = True
        und = excl.get("undated")
        if und not in (None, "", 0, "0"):
            if partial.get("undated_excluded") in (None, "", 0, "0"):
                partial["undated_excluded"] = und
            if not _num_in_text(have, und) and "undated=" not in low:
                text = (text.rstrip() + " · undated=%s" % _fmt(und)).strip()
                have = _norm_numbers(text)
                low = text.lower()
                changed_text = True
        folders = excl.get("folders")
        if folders not in (None, "", 0, "0"):
            if not _num_in_text(have, folders) and "folders=" not in low:
                text = (text.rstrip() + " · folders=%s" % _fmt(folders)).strip()
                have = _norm_numbers(text)
                low = text.lower()
                changed_text = True
        outside = excl.get("outside_period")
        if outside not in (None, "", 0, "0"):
            if not _num_in_text(have, outside):
                text = (text.rstrip() + " · outside_period=%s" % _fmt(outside)).strip()
                have = _norm_numbers(text)
                low = text.lower()
                changed_text = True

    # ── diag.incomplete → coverage_missing ──────────────────────────────────
    inc = diag.get("incomplete") if isinstance(diag.get("incomplete"), dict) else {}
    miss_i = inc.get("missing")
    if miss_i not in (None, "", 0, "0"):
        if partial.get("coverage_missing") in (None, "", 0, "0"):
            partial["coverage_missing"] = miss_i
        if not _num_in_text(have, miss_i) and "missing=" not in low:
            text = (text.rstrip() + " · missing=%s" % _fmt(miss_i)).strip()
            have = _norm_numbers(text)
            low = text.lower()
            changed_text = True

    # ── diag.fork.uncounted → fork_limitation + нота ─────────────────────────
    fork = diag.get("fork") if isinstance(diag.get("fork"), dict) else {}
    unc = fork.get("uncounted")
    n_unc = 0
    if unc:
        if isinstance(unc, (list, tuple)):
            n_unc = len(unc)
        else:
            try:
                n_unc = int(unc)
            except (TypeError, ValueError):
                n_unc = 1
    lim = partial.get("fork_limitation")
    if isinstance(lim, dict):
        try:
            n_unc = max(n_unc, int(lim.get("uncounted_classes") or 0))
        except (TypeError, ValueError):
            pass
    if n_unc > 0:
        if not isinstance(lim, dict):
            lim = {}
            partial["fork_limitation"] = lim
        lim.setdefault("reason", "uncounted_cell")
        if int(lim.get("uncounted_classes") or 0) < n_unc:
            lim["uncounted_classes"] = n_unc
        if UNCOUNTED_NOTE not in low:
            text = (text + ("\n" if text else "") + UNCOUNTED_NOTE).strip()
            have = _norm_numbers(text)
            low = text.lower()
            changed_text = True

    # ── selection_budget (мост budget не показывает — цифры в text) ──────────
    sb = diag.get("selection_budget") if isinstance(diag.get("selection_budget"), dict) else {}
    budget_bits = []
    for shown_k, total_k in BUDGET_KEYS:
        shown, total = sb.get(shown_k), sb.get(total_k)
        if shown is None or total is None:
            # уже могли лежать в partial
            shown = partial.get(shown_k) if shown is None else shown
            total = partial.get(total_k) if total is None else total
        if shown is None or total is None:
            continue
        try:
            si, ti = int(shown), int(total)
        except (TypeError, ValueError):
            continue
        if ti <= si:
            continue
        partial.setdefault(shown_k, shown)
        partial.setdefault(total_k, total)
        if not _num_in_text(have, si) or not _num_in_text(have, ti):
            budget_bits.append("%s/%s" % (_fmt(si), _fmt(ti)))
    if budget_bits:
        # цифры в text обязательны: мост PARTIAL budget намеренно не показывает (S8)
        need = False
        for bit in budget_bits:
            a, _, b = bit.partition("/")
            if not _num_in_text(have, a) or not _num_in_text(have, b):
                need = True
                break
        if need:
            text = (text.rstrip() + " · рассмотрено " + "; ".join(budget_bits)).strip()
            changed_text = True

    if changed_text:
        out["text"] = text

    # пустой partial → None (как раньше: bool({}) == False для журнала)
    if not partial:
        out["partial"] = None
    else:
        out["partial"] = partial
    return out
