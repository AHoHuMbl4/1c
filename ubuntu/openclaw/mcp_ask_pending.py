"""Непогашенный clarify в мосте: текстовый выбор без decision_id.

Живая петля OWUI 21.08: модель зовёт ask_1c текстом опции, билет не доезжает,
serene_ask каждый раз печатает новый clarify. Состояние здесь — код моста
(HOW_NOT_TO §1.51), семантику билетов serene_ask не ослабляет.
"""
from __future__ import annotations

import os
import re
import threading
import time

PENDING_CLARIFY_TTL = float(os.environ.get("MCP_PENDING_CLARIFY_TTL", "900"))
PENDING_CLARIFY_LOOP_N = int(os.environ.get("MCP_PENDING_CLARIFY_LOOP_N", "5"))
# Текст в теле clarify (язык клиента). Не инструкция модели.
CLARIFY_LOOP_TEXT = os.environ.get(
    "MCP_CLARIFY_LOOP_TEXT",
    "Выбор не распознан, вот варианты ещё раз.")
# Маркер исхода для модели — без долженствований (п. 21 / HOW_NOT_TO §1.51).
CLARIFY_LOOP_REFUSE = os.environ.get(
    "MCP_CLARIFY_LOOP_REFUSE",
    "[NO DATA] Clarification choice unresolved after repeated attempts.")

_PENDING_LOCK = threading.Lock()
_PENDING_CLARIFY = {}  # key -> {at, question, options, data, fp, streak, escalated}
_CHIP_PREFIX_MIN = 3


def reset_pending_clarify_for_tests():
    with _PENDING_LOCK:
        _PENDING_CLARIFY.clear()


def pending_key(user, channel):
    u = (user or "").strip()
    c = (channel or "").strip()
    return "%s\0%s" % (c or "-", u or "_anon")


def norm_clarify_key(s):
    return re.sub(r"\s+", "", str(s or "").lower())


def strip_choice_num(s):
    return re.sub(r"^\d+[.)]\s+", "", str(s or "")).strip()


def options_fingerprint(opts):
    parts = []
    for o in opts or []:
        if not isinstance(o, dict):
            continue
        parts.append("%s|%s|%s|%s" % (
            norm_clarify_key(o.get("label")),
            norm_clarify_key(o.get("measure")),
            norm_clarify_key(o.get("entity_label")),
            (o.get("decision_id") or "").strip()))
    return "\n".join(parts)


def _option_fields(opt):
    return [opt.get("label"), opt.get("focus"), opt.get("measure"),
            opt.get("entity_label"), opt.get("hint")]


def _unique_opts(arr):
    seen, out = set(), []
    for o in arr:
        k = "%s|%s|%s" % (
            (o.get("decision_id") or "").strip(),
            norm_clarify_key(o.get("label")),
            norm_clarify_key(o.get("measure")))
        if k in seen:
            continue
        seen.add(k)
        out.append(o)
    return out


def match_pending_option(prompt, options):
    """Сопоставить текст выбора с опцией (как verify-plugin matchClarifyOption)."""
    raw = str(prompt or "").strip()
    if raw.startswith("ask1c:"):
        raw = raw[len("ask1c:"):].strip()
    key = norm_clarify_key(raw) or norm_clarify_key(strip_choice_num(raw))
    if not key:
        return None
    opts = [o for o in (options or []) if isinstance(o, dict)]

    for opt in opts:
        did = (opt.get("decision_id") or "").strip()
        if did and (raw == did or norm_clarify_key(did) == key):
            return opt

    exact = []
    for opt in opts:
        lab = opt.get("label")
        if (norm_clarify_key(lab) == key
                or norm_clarify_key(strip_choice_num(lab or "")) == key):
            exact.append(opt)
        elif opt.get("focus") and norm_clarify_key(opt.get("focus")) == key:
            exact.append(opt)
        elif opt.get("measure") and norm_clarify_key(opt.get("measure")) == key:
            exact.append(opt)
        elif (opt.get("entity_label")
              and norm_clarify_key(opt.get("entity_label")) == key):
            exact.append(opt)
    exact_u = _unique_opts(exact)
    if len(exact_u) == 1:
        return exact_u[0]
    if len(exact_u) > 1:
        return None

    num = re.match(r"^\s*#?\s*(\d+)\s*[.)]?\s*$", raw)
    if num:
        i = int(num.group(1))
        if 1 <= i <= len(opts):
            return opts[i - 1]
        return None

    if len(key) >= _CHIP_PREFIX_MIN:
        pref = []
        for opt in opts:
            for f in _option_fields(opt):
                nk = norm_clarify_key(f)
                if not nk:
                    continue
                if nk.startswith(key) or (key.startswith(nk)
                                          and len(nk) >= _CHIP_PREFIX_MIN):
                    pref.append(opt)
                    break
        pref_u = _unique_opts(pref)
        if len(pref_u) == 1:
            return pref_u[0]
        if len(pref_u) > 1:
            return None

    contain = []
    for opt in opts:
        for f in _option_fields(opt):
            nk = norm_clarify_key(strip_choice_num(str(f or "")))
            if len(nk) >= 8 and nk in key:
                contain.append(opt)
                break
    contain_u = _unique_opts(contain)
    if len(contain_u) == 1:
        return contain_u[0]
    return None


def looks_like_choice_attempt(prompt, options):
    raw = str(prompt or "").strip()
    if raw.startswith("ask1c:"):
        raw = raw[len("ask1c:"):].strip()
    if not raw:
        return False
    if re.match(r"^\s*#?\s*\d+\s*[.)]?\s*$", raw):
        return True
    key = norm_clarify_key(raw)
    if len(key) < 2:
        return False
    for opt in options or []:
        if not isinstance(opt, dict):
            continue
        for f in _option_fields(opt):
            nk = norm_clarify_key(f)
            if not nk:
                continue
            if nk.startswith(key) or key.startswith(nk) or key in nk or nk in key:
                return True
    return False


def get_pending(user, channel):
    key = pending_key(user, channel)
    now = time.time()
    with _PENDING_LOCK:
        row = _PENDING_CLARIFY.get(key)
        if not row:
            return None
        if float(row.get("at") or 0) + PENDING_CLARIFY_TTL <= now:
            _PENDING_CLARIFY.pop(key, None)
            return None
        return dict(row)


def clear_pending(user, channel):
    key = pending_key(user, channel)
    with _PENDING_LOCK:
        _PENDING_CLARIFY.pop(key, None)


def store_pending(user, channel, question, data, *, bump_streak=True):
    opts = [dict(o) for o in (data.get("options") or []) if isinstance(o, dict)]
    if not opts or not any((o.get("decision_id") or "").strip() for o in opts):
        return None
    key = pending_key(user, channel)
    fp = options_fingerprint(opts)
    now = time.time()
    with _PENDING_LOCK:
        prev = _PENDING_CLARIFY.get(key)
        streak = 1
        escalated = False
        if prev and prev.get("fp") == fp:
            streak = int(prev.get("streak") or 0) + (1 if bump_streak else 0)
            if streak < 1:
                streak = 1
            escalated = bool(prev.get("escalated"))
        snap = {
            "at": now,
            "question": question,
            "options": opts,
            "data": {
                "kind": data.get("kind") or "clarify",
                "text": data.get("text") or "",
                "options": opts,
                "atoms": data.get("atoms"),
                "atom": data.get("atom"),
                "partial": data.get("partial"),
                "diag": data.get("diag"),
            },
            "fp": fp,
            "streak": streak,
            "escalated": escalated,
        }
        _PENDING_CLARIFY[key] = snap
        return dict(snap)


def mark_pending_escalated(user, channel):
    key = pending_key(user, channel)
    with _PENDING_LOCK:
        row = _PENDING_CLARIFY.get(key)
        if row:
            row["escalated"] = True
            row["at"] = time.time()


def apply_pending_before_ask(question, focus, measure, decision_id, user, channel):
    """До /ask: подставить билет / те же опции / стоп петли.

    Возврат: question, focus, measure, decision_id, short_circuit, refuse.
    """
    q = question or ""
    foc = focus or ""
    meas = measure or ""
    did = (decision_id or "").strip()
    pending = get_pending(user, channel)
    if not pending:
        return {"question": q, "focus": foc, "measure": meas,
                "decision_id": did, "short_circuit": None, "refuse": False}

    opts = pending.get("options") or []
    locked_q = pending.get("question") or q

    if did:
        return {"question": q, "focus": foc, "measure": meas,
                "decision_id": did, "short_circuit": None, "refuse": False}

    matched = (match_pending_option(q, opts)
               or match_pending_option(foc, opts)
               or match_pending_option(meas, opts))
    if matched and (matched.get("decision_id") or "").strip():
        return {
            "question": locked_q,
            "focus": "",
            "measure": "",
            "decision_id": (matched.get("decision_id") or "").strip(),
            "short_circuit": None,
            "refuse": False,
        }

    same_q = norm_clarify_key(q) == norm_clarify_key(locked_q)
    choice_ish = (looks_like_choice_attempt(q, opts)
                  or looks_like_choice_attempt(foc, opts))

    if same_q or choice_ish:
        streak = int(pending.get("streak") or 1)
        if pending.get("escalated") and streak >= PENDING_CLARIFY_LOOP_N:
            clear_pending(user, channel)
            return {"question": q, "focus": foc, "measure": meas,
                    "decision_id": "", "short_circuit": None, "refuse": True}
        if streak >= PENDING_CLARIFY_LOOP_N and not pending.get("escalated"):
            data = dict(pending.get("data") or {})
            data["kind"] = "clarify"
            data["options"] = [dict(o) for o in opts]
            data["text"] = CLARIFY_LOOP_TEXT
            mark_pending_escalated(user, channel)
            snap = store_pending(user, channel, locked_q, data, bump_streak=True)
            return {"question": locked_q, "focus": "", "measure": "",
                    "decision_id": "",
                    "short_circuit": snap["data"] if snap else data,
                    "refuse": False}
        data = dict(pending.get("data") or {})
        data["options"] = [dict(o) for o in opts]
        store_pending(user, channel, locked_q, data, bump_streak=True)
        return {"question": locked_q, "focus": "", "measure": "",
                "decision_id": "", "short_circuit": data, "refuse": False}

    clear_pending(user, channel)
    return {"question": q, "focus": foc, "measure": meas,
            "decision_id": "", "short_circuit": None, "refuse": False}
