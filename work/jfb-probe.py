#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Живая проба B: parse_intent ×2 + wiki_leader_post_verify на OKNA.

Кейс: spaced «реализации ТМЦ» vs склейка «реализациятмц» на лидере
accumulationregister_реализациятмц. Код не меняет — только замер.

Запуск на окне (после scp в /tmp и env полигона :8092):
  python3 /tmp/jfb-probe.py
"""
from __future__ import annotations

import datetime
import json
import os
import sys
import traceback

PROBE_ROOT = os.environ.get("PROBE_ROOT", "/tmp/probe_root")
LEADER = "accumulationregister_реализациятмц"
Q_SP = "Сколько движений в регистре реализации ТМЦ?"
Q_GL = "Сколько движений в регистре «реализациятмц»?"
TODAY = os.environ.get("PROBE_TODAY") or datetime.date.today().isoformat()


def _j(obj):
    return json.dumps(obj, ensure_ascii=False, default=str, indent=2)


def _load_ask():
    if PROBE_ROOT not in sys.path:
        sys.path.insert(0, PROBE_ROOT)
    os.chdir(PROBE_ROOT)
    import serene_ask as A  # noqa: WPS433
    return A


def _intent_slice(intent):
    """Поля, которые читает wiki_leader_post_verify (+ соседние для трассы)."""
    intent = intent or {}
    keys = (
        "want", "kind", "measure", "action_axis", "action_class", "search_form",
        "about", "terms", "period", "period2", "amount", "parse",
    )
    out = {k: intent.get(k) for k in keys}
    return out


def _named_measures(A, intent):
    fn = getattr(A, "wiki_intent_named_measures", None)
    if callable(fn):
        return list(fn(intent) or [])
    raw = intent.get("measure")
    if isinstance(raw, (list, tuple)):
        return [str(x).strip() for x in raw if str(x).strip()]
    if raw is not None and str(raw).strip():
        return [str(raw).strip()]
    return []


def _unaccounted(A, question, intent):
    fn = getattr(A, "resolved_unaccounted_slice_axis_word", None)
    if not callable(fn):
        return None, "resolved_unaccounted_slice_axis_word missing"
    try:
        return (fn(question, intent) or ""), None
    except Exception as e:  # noqa: BLE001 — замер: полный след
        return None, "%s: %s" % (type(e).__name__, e)


def _axis_word_path(A, intent, question):
    """Как wiki_leader_post_verify выбирает axis_word."""
    axis_word = ""
    src = "empty"
    try:
        axis_word = (A._intent_text(intent.get("action_axis")) or "").strip()
    except Exception:
        axis_word = (str(intent.get("action_axis") or "")).strip()
    if axis_word:
        src = "action_axis"
        return axis_word, src, False
    ua, err = _unaccounted(A, question, intent)
    if err:
        return "", "unaccounted_error", False
    if ua:
        return ua, "resolved_unaccounted_slice_axis_word", True
    return "", "empty", False


def _refcols_for_cats(A, leader, axis_cats):
    """Что видит wiki_leader_carries_axis: search_refcols лидера → axis_cats."""
    cats = [c for c in (axis_cats or []) if c]
    if not cats:
        return {"skipped": "no axis_cats", "rows": []}
    cats_sql = ", ".join(A.lit(c) for c in sorted(set(cats)))
    sql = (
        "SELECT col, target_src FROM search_refcols "
        "WHERE src_table = %s AND target_src IN (%s) "
        "  AND col IS NOT NULL AND trim(col) <> '' "
        "ORDER BY 1, 2"
        % (A.lit(leader), cats_sql)
    )
    try:
        rows = A.psql(sql) or []
        return {
            "sql_ok": True,
            "rows": [{"col": r[0], "target_src": r[1]} for r in rows if r],
        }
    except Exception as e:  # noqa: BLE001
        return {"sql_ok": False, "error": "%s: %s" % (type(e).__name__, e), "rows": []}


def _all_leader_refcols(A, leader):
    try:
        rows = A.psql(
            "SELECT col, target_src FROM search_refcols "
            "WHERE src_table = %s AND col IS NOT NULL AND trim(col) <> '' "
            "ORDER BY 1, 2" % A.lit(leader)
        ) or []
        return [{"col": r[0], "target_src": r[1]} for r in rows if r]
    except Exception as e:  # noqa: BLE001
        return {"error": "%s: %s" % (type(e).__name__, e)}


def _trace_one(A, label, question):
    print("=" * 72)
    print("CASE", label)
    print("Q:", question)
    print("today:", TODAY)
    print("-" * 72)

    t0 = __import__("time").time()
    try:
        intent = A.parse_intent(question, TODAY)
    except Exception:
        print("parse_intent FAILED:")
        traceback.print_exc()
        return
    print("parse_intent_sec:", round(__import__("time").time() - t0, 2))
    print("INTENT_FULL:")
    print(_j(_intent_slice(intent)))
    named = _named_measures(A, intent)
    print("named_measures:", _j(named))
    ua, ua_err = _unaccounted(A, question, intent)
    print("resolved_unaccounted_slice_axis_word:", _j(ua), "err=", ua_err)

    axis_word, axis_src, from_ua = _axis_word_path(A, intent, question)
    print("axis_word:", repr(axis_word), "source:", axis_src, "from_unaccounted:", from_ua)

    is_subj = None
    try:
        is_subj = A.wiki_axis_is_question_subject(intent, axis_word) if axis_word else False
    except Exception as e:  # noqa: BLE001
        is_subj = "ERR %s: %s" % (type(e).__name__, e)
    print("wiki_axis_is_question_subject:", is_subj)

    has_carriers = None
    try:
        if axis_word:
            has_carriers = A._wiki_axis_has_carriers(axis_word, intent, question)
        else:
            has_carriers = False
    except Exception as e:  # noqa: BLE001
        has_carriers = "ERR %s: %s" % (type(e).__name__, e)
    print("_wiki_axis_has_carriers:", has_carriers)

    efc_cats = None
    efc_err = None
    try:
        period = intent.get("period") or {}
        has_period = bool(period.get("from") or period.get("to"))
        efc = getattr(A, "entity_form_catalogs_for_kind", None)
        if axis_word and callable(efc):
            efc_cats = list(efc(axis_word, allow_meaning=has_period) or [])
        else:
            efc_cats = []
    except Exception as e:  # noqa: BLE001
        efc_err = "%s: %s" % (type(e).__name__, e)
        efc_cats = None
    print("entity_form_catalogs_for_kind(%r):" % axis_word, _j(efc_cats), "err=", efc_err)

    carries = None
    try:
        if axis_word:
            carries = A.wiki_leader_carries_axis(
                LEADER, axis_word, intent, question,
                require_axis_cats=from_ua)
        else:
            carries = True  # как в коде: пустая ось → True (не режет)
    except Exception as e:  # noqa: BLE001
        carries = "ERR %s: %s" % (type(e).__name__, e)
    print("wiki_leader_carries_axis:", carries, "require_axis_cats=", from_ua)

    if axis_word:
        print("refcols_matching_efc:", _j(_refcols_for_cats(A, LEADER, efc_cats or [])))
    print("leader_all_refcols:", _j(_all_leader_refcols(A, LEADER)))

    diag = {}
    try:
        ok = A.wiki_leader_post_verify(LEADER, intent, question, diag)
    except Exception:
        print("wiki_leader_post_verify FAILED:")
        traceback.print_exc()
        ok = None
    print("post_verify_ok:", ok)
    print("post_verify_diag:", _j(diag))
    print()


def main():
    print("PROBE_ROOT=", PROBE_ROOT)
    print("LEADER=", LEADER)
    print("cwd→", PROBE_ROOT)
    print("env_keys_present:", {
        "SERENEDB_DSN_RO": bool(os.environ.get("SERENEDB_DSN_RO")),
        "PGPASSWORD": bool(os.environ.get("PGPASSWORD")),
        "DEEPSEEK_API_KEY": bool(os.environ.get("DEEPSEEK_API_KEY")),
        "DEEPSEEK_BASE": os.environ.get("DEEPSEEK_BASE", ""),
        "DEEPSEEK_MODEL": os.environ.get("DEEPSEEK_MODEL", ""),
        "OPENCLAW_HOME": os.environ.get("OPENCLAW_HOME", ""),
        "ASK_INTENT_SAMPLES": os.environ.get("ASK_INTENT_SAMPLES", ""),
        "ASK_INTENT_MEMO": os.environ.get("ASK_INTENT_MEMO", ""),
    })
    A = _load_ask()
    print("loaded serene_ask; parse_intent=", callable(getattr(A, "parse_intent", None)))
    print("wiki_leader_post_verify=", callable(getattr(A, "wiki_leader_post_verify", None)))
    # Без памяти между двумя формулировками — иначе второй вопрос не зовёт LLM,
    # а нам нужен независимый intent каждой формы.
    try:
        A.INTENT_MEMO = 0
        if hasattr(A, "_INTENT_MEMO"):
            A._INTENT_MEMO.clear()
        print("INTENT_MEMO forced 0 for independent parses")
    except Exception as e:  # noqa: BLE001
        print("INTENT_MEMO tweak skipped:", e)

    _trace_one(A, "Q_SP spaced", Q_SP)
    _trace_one(A, "Q_GL glued", Q_GL)
    print("DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
