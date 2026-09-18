#!/usr/bin/env python3
"""Замок C5: R-A..R-K прохода «один путь» (design-c §5).

Оффлайн: моки psql ('t'/'f') и LLM. КОД продукта не правит — красный = находка
для оркестратора. Имена конкретной базы — ТОЛЬКО в фикстурах.
Запуск: python3 ubuntu/serenedb/test_onepath_rescue.py
"""
from __future__ import annotations

import inspect
import json
import os
import re
import sys
import time
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("ASK_TOKEN", "test")
os.environ.setdefault("EMBED_BASE_URL", "-")
os.environ.setdefault("EMBED_MODEL", "-")
os.environ.setdefault("ASK_ATOM_TERMINAL", "0")
os.environ.setdefault("ASK_JOURNAL", "0")

import serene_ask as A  # noqa: E402

PASS, FAIL = 0, []
SECTION = {"cur": "?"}


def t(name, cond, detail=None):
    global PASS
    tag = "%s/%s" % (SECTION["cur"], name)
    if cond:
        PASS += 1
        print("ok  -", tag)
    else:
        FAIL.append(tag)
        print("FAIL-", tag, detail if detail is not None else "")


# --- фикстуры (имена базы здесь, не в логике продукта) ---
Q1 = "а на прошлой неделе сколько наторговали"
Q5 = "Сколько движений в регистре реализации ТМЦ?"
Q6 = "сколько у нас вообще клиентов сейчас"
SRC_SALES = "accumulationregister_fixture_sales"
SRC_TMZ = "accumulationregister_реализациятмц"
SRC_CLIENTS = "catalog_контрагенты"
SRC_PEER = "document_реализациятмц"
SRC_OTHER = "catalog_fixture_other"
SRC_FAR = "catalog_fixture_beyond_top3"
LABEL_TMZ = "Реализация ТМЦ"
GLUE_Q5 = "реализациитмц"
TAIL_TMZ = "реализациятмц"


def _card(src, name="", layer=1, dist=0.1):
    return {
        "src_table": src,
        "name": name or src.split("_", 1)[-1],
        "description": "fixture",
        "axes": "",
        "measures": "",
        "covered": 1,
        "distance": dist,
        "parent": "",
        "platform_kind": src.split("_", 1)[0],
        "src_layer": layer,
    }


def _pool_n(n, leader=None):
    leader = leader or SRC_FAR
    out = [_card("catalog_noise_%02d" % i, "noise %d" % i, layer=1,
                 dist=0.5 + i * 0.01)
           for i in range(max(0, n - 1))]
    out.append(_card(leader, "leader far", layer=2, dist=0.05))
    return out


def _verdict(src, fit):
    return {"fit": fit, "index": 1, "src_table": src}


def _verdicts_map(pool, yes_src=None, unsure=(), missing=()):
    vb = {}
    for c in pool:
        s = c["src_table"]
        if s in missing:
            continue
        if yes_src and s == yes_src:
            vb[s] = _verdict(s, "yes")
        elif s in unsure:
            vb[s] = _verdict(s, "unsure")
        else:
            vb[s] = _verdict(s, "no")
    return vb


_REAL = {}


def _save(*names):
    for n in names:
        if n not in _REAL and hasattr(A, n):
            _REAL[n] = getattr(A, n)


def _restore():
    for k, v in list(_REAL.items()):
        setattr(A, k, v)
    if hasattr(A, "_III_SPAN_HIT_CACHE"):
        A._III_SPAN_HIT_CACHE.clear()


def _reset_session():
    if hasattr(A, "_DECISION_LOCK"):
        with A._DECISION_LOCK:
            getattr(A, "_DECISIONS", {}).clear()
            getattr(A, "_CLARIFY_BATCHES", {}).clear()
            getattr(A, "_RESOLVED_CHOICES", {}).clear()
    if hasattr(A, "_III_SPAN_HIT_CACHE"):
        A._III_SPAN_HIT_CACHE.clear()


def _dl_mock(a, b):
    """Локальный DL для мока psql (не код продукта)."""
    a, b = str(a), str(b)
    if a == b:
        return 0
    la, lb = len(a), len(b)
    prev = list(range(lb + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            ins, delete, sub = cur[j - 1] + 1, prev[j] + 1, prev[j - 1]
            if ca != cb:
                sub += 1
            best = min(ins, delete, sub)
            if i > 1 and j > 1 and a[i - 2] == cb and b[j - 2] == ca:
                best = min(best, prev[j - 2] + 1)
            cur.append(best)
        prev = cur
    return prev[lb]


def _psql_damerau(sql):
    """Мок штатного damerau: пороги — из продукта (_PROBE_NORM_DIST*), не хардкод."""
    if "unnest" not in sql.lower() or "damerau" not in sql.lower():
        return []
    arrs = re.findall(r"unnest\(\[([^\]]*)\]\)", sql, flags=re.I)
    if len(arrs) < 2:
        return []

    def _items(blob):
        return [x.strip(" '\"") for x in blob.split(",") if x.strip(" '\"")]

    gs, ts = _items(arrs[0]), _items(arrs[1])
    mdist = re.search(r"<=\s*(\d+)", sql)
    short_d = int(getattr(A, "_PROBE_NORM_DIST", 2))
    long_d = int(getattr(A, "_PROBE_NORM_DIST_LONG", 3))
    long_at = int(getattr(A, "_PROBE_NORM_LONG_AT", 16))
    fixed = int(mdist.group(1)) if mdist else short_d
    caseful = "CASE WHEN length" in sql or "case when length" in sql.lower()

    def _lim(g):
        if caseful:
            return long_d if len(g) >= long_at else short_d
        return fixed

    hits = []
    for g in gs:
        for tgt in ts:
            if len(g) < 8 or len(tgt) < 8:
                continue
            if _dl_mock(g, tgt) <= _lim(g):
                hits.append([g])
                break
    return hits


def _stamp_returns_ok(src_block, *, allow_menu=False, lookback_n=700):
    """Каждый return в блоке либо сам _c3_stamp_*, либо штамп в lookback.

    allow_menu: return _*_menu без штампа допустим (меню до SQL).
    """
    bad = []
    for m in re.finditer(r"(?m)^[ \t]*return\b", src_block):
        rpos = m.start()
        line = src_block[rpos:src_block.find("\n", rpos) + 1]
        lookback = src_block[max(0, rpos - lookback_n):rpos]
        if "_c3_stamp" in line or "_c3_stamp" in lookback:
            continue
        # point1: return _ep после `_ep = _c3_stamp_out(...)` (в т.ч. условно)
        if re.search(r"return\s+_ep\b", line) and "_ep = _c3_stamp_out" in src_block:
            continue
        if allow_menu and re.search(r"return\s+_\w*menu\b", line):
            continue
        bad.append(line.strip()[:60])
    return bad


def _install_deadline(hit=False):
    _save("deadline_hit", "_deadline_remaining_sec")
    A.deadline_hit = lambda rid=None: bool(hit)
    A._deadline_remaining_sec = lambda: 30.0


def _install_menu_passthrough():
    _save("finalize_clarify_menu", "mk_opts", "wiki_menu_captions",
          "wiki_captions_map_from_cards", "readings_menu", "psql",
          "wiki_leader_post_verify", "wiki_leader_db_homonym_gate",
          "wiki_homonym_kind_peers", "wiki_validate_leader_axes",
          "human_table_label", "label_with_kind")

    def _mk(srcs, lab_by, marks=None, by=None, match="", preds=None,
            live=None, skip_empty_filter=False):
        counted = live if live is not None else (by or {})
        srcs = list(srcs or [])
        if counted is not None and not skip_empty_filter:
            live_srcs = [s for s in srcs if counted.get(s, 0) > 0]
            if live_srcs:
                srcs = live_srcs
        return [{"src": s, "label": lab_by.get(s) or s, "hint": "",
                 "found": counted.get(s, 0)} for s in srcs]

    def _fin(question, kind, items, diag, cut, t0, *, why="", **kw):
        why = why or kw.get("reason") or ""
        items = list(items or [])
        if len(items) < 2:
            return None
        return {"kind": "clarify", "options": items, "text": why or "?",
                "diag": dict(diag or {}), "partial": cut, "why": why}

    A.mk_opts = _mk
    A.finalize_clarify_menu = (
        lambda question, kind, items, diag, cut, t0, **kw: _fin(
            question, kind, items, diag, cut, t0,
            why=kw.get("reason") or ""))
    A.wiki_menu_captions = lambda opts, **k: opts
    A.wiki_captions_map_from_cards = lambda cards: {
        c.get("src_table"): c for c in (cards or []) if c.get("src_table")}
    A.readings_menu = (
        lambda *a, **k: _fin(a[0], a[1], a[2], a[3], a[4], a[5],
                             why=k.get("reason", "")))
    A.wiki_leader_post_verify = lambda *a, **k: True
    A.wiki_leader_db_homonym_gate = lambda *a, **k: None
    A.wiki_homonym_kind_peers = lambda *a, **k: []
    A.wiki_validate_leader_axes = lambda *a, **k: True
    A.human_table_label = (
        lambda src, lab=None: (lab or str(src or "").split("_", 1)[-1]))
    A.label_with_kind = lambda src, lab: lab or src


def _install_psql_basic(tables=None, hybrid_rows=None):
    tables = dict(tables or {})
    hybrid_rows = list(hybrid_rows or [])
    calls = {"sqls": [], "n": 0}

    def fake(sql):
        calls["n"] += 1
        calls["sqls"].append(sql)
        qs = " ".join(str(sql).lower().split())
        if "damerau_levenshtein" in qs:
            return _psql_damerau(sql)
        if "select 1 from search_wiki_entity_card" in qs:
            return [(1,)]
        if "from search_tables" in qs and "label" in qs:
            out = []
            for src, lab in tables.items():
                if ("'%s'" % src) in sql or src in sql:
                    out.append([src, lab])
            if not out and "in (" in qs:
                for src, lab in tables.items():
                    out.append([src, lab])
            return out
        if hybrid_rows and (
                "src_table" in qs or "from pool" in qs
                or "from selected" in qs or "struct_norm" in qs
                or "ai_embed" in qs or "from knn" in qs):
            return hybrid_rows
        return []

    _save("psql")
    A.psql = fake
    return calls


def run_R_A():
    SECTION["cur"] = "R-A"
    _reset_session()
    _install_deadline(False)
    _install_menu_passthrough()

    rare = "наторговали"
    intent_a = {
        "measure": rare,
        "want": "sum",
        "terms": [[rare], ["прошлой"], ["неделе"]],
    }
    excl = A.conceptual_term_group_norms(
        intent_a["terms"], intent=intent_a, concepts=[], src=None, question=Q1)
    t("a-slot-and-terms-concept",
      A._homonym_norm(rare) in excl,
      "excl missing measure-slot word")
    kept = A.terms_for_probe(intent_a, diag={})
    kept_n = {A._term_group_norm(g) for g in kept}
    t("a-terms-for-probe-drops-slot",
      A._homonym_norm(rare) not in kept_n, "kept=%s" % kept)

    intent_b = {"want": "sum", "terms": [[rare], ["окно"]]}
    excl_b0 = A.conceptual_term_group_norms(
        intent_b["terms"], intent=intent_b, concepts=[], src=None)
    t("b-without-concepts-not-i",
      A._homonym_norm(rare) not in excl_b0)
    excl_b1 = A.conceptual_term_group_norms(
        intent_b["terms"], intent=intent_b, concepts=[rare], src=None)
    t("b-concepts-marks-terms-only",
      A._homonym_norm(rare) in excl_b1)

    excl_ex = A.conceptual_term_group_norms(
        [["valuexact"], ["other"]], intent={}, concepts=["valuexact"],
        exact_matched=["valuexact"])
    t("d-exact-matched-not-concept",
      A._homonym_norm("valuexact") not in excl_ex, "excl=%s" % excl_ex)

    _save("wiki_concepts_call", "wiki_rescue_full_pool_pass")
    concept_calls = {"n": 0}

    def _cc(q, cards, diag=None, **kw):
        concept_calls["n"] += 1
        return {"ok": True, "concepts": [rare], "fail": False, "verdict": None}

    A.wiki_concepts_call = _cc
    rescue_calls = {"n": 0}
    A.wiki_rescue_full_pool_pass = (
        lambda *a, **k: rescue_calls.__setitem__("n", rescue_calls["n"] + 1))
    # (в) живой лидер + unmatched-понятие: покрытие (i) слотом measure
    # (канон: continue при wiki_full ∧ ¬(ii)-only)
    diag2 = {"wiki_full_pool": True, "wiki_rescue_origin": "cascade"}
    intent_c = {"want": "sum", "measure": rare, "terms": [[rare], ["окно"]]}
    p2 = A._point2_unmatched_gate(
        Q1, intent_c, diag2, None, time.time(),
        src=SRC_SALES, probe_terms=[[rare], ["окно"]],
        kinds={1: "exact"},
        exact_matched=[A._homonym_norm("окно")])
    t("c-point2-continue-alive",
      isinstance(p2, dict) and p2.get("continue") is True,
      "got=%s branch=%s" % (p2, diag2.get("point2_branch")))
    t("c-point2-no-escalate-when-full",
      rescue_calls["n"] == 0, "n=%s" % rescue_calls["n"])

    _restore()
    _install_deadline(False)
    _install_menu_passthrough()
    pool = _pool_n(5, leader=SRC_FAR)
    _save("wiki_hybrid_pool", "wiki_batch_verify", "wiki_pool_resolver",
          "wiki_concepts_call", "deadline_hit")
    A.deadline_hit = lambda rid=None: False
    A.wiki_hybrid_pool = lambda *a, **k: list(pool)
    A.wiki_batch_verify = lambda q, intent, cards, diag=None: {
        "verdicts_by_src": _verdicts_map(cards, yes_src=SRC_FAR),
        "passports": cards, "incomplete": False, "diag": dict(diag or {})}
    A.wiki_pool_resolver = lambda q, cards, diag=None, concepts_only=False: {
        "ok": True, "verdict": "many", "concepts": [rare], "fail": False}
    diag = {}
    out = A.wiki_rescue_full_pool_pass(
        Q1, {"want": "sum", "terms": [[rare]]}, diag, None, time.time())
    t("cascade-death-rescue-runs",
      diag.get("wiki_full_pool") is True
      and diag.get("wiki_rescue_pool_n", 0) >= 1,
      "pool_n=%s" % diag.get("wiki_rescue_pool_n"))
    # sole-фикстура (ровно 1 yes = SRC_FAR): жёстко picked; no_data = красный
    t("cascade-death-sole-picked",
      isinstance(out, dict)
      and out.get("picked") == [SRC_FAR]
      and out.get("kind") != "no_data",
      "out=%s" % out)
    t("far-card-in-pool",
      SRC_FAR in (diag.get("wiki_rescue_pool") or []),
      "pool=%s" % diag.get("wiki_rescue_pool"))

    # all-no: полный пул → clarify с len(opts)==len(pool); no_data = красный
    diag_all = {}
    A.wiki_batch_verify = lambda q, intent, cards, diag=None: {
        "verdicts_by_src": _verdicts_map(cards),
        "passports": cards, "incomplete": False, "diag": dict(diag or {})}
    A.wiki_pool_resolver = lambda q, cards, diag=None, concepts_only=False: {
        "ok": True, "verdict": "many", "concepts": [rare], "fail": False}
    out_all = A.wiki_rescue_full_pool_pass(
        Q1, {"want": "sum", "terms": [[rare]]}, diag_all, None, time.time())
    opts_all = (
        out_all.get("options") or []) if isinstance(out_all, dict) else []
    t("cascade-death-all-no-clarify",
      isinstance(out_all, dict)
      and out_all.get("kind") == "clarify"
      and len(opts_all) == len(pool)
      and out_all.get("kind") != "no_data",
      "out=%s n_opts=%s pool=%s" % (
          out_all.get("kind") if isinstance(out_all, dict) else out_all,
          len(opts_all), len(pool)))

    _reset_session()
    opt = {"src": SRC_SALES, "label": "sales",
           "rescue_concepts": [rare], "rescue_concepts_pending": False}
    tid = A.issue_decision(Q1, opt, "entity", "v1", user="u-ra")
    ticket = A._DECISIONS.get(tid) or {}
    t("e-whitelist-rescue_concepts",
      "rescue_concepts" in ticket
      and ticket.get("rescue_concepts") == [rare],
      "ticket keys=%s" % list(ticket.keys()))
    A.accumulate_resolution(Q1, "u-ra", ticket)
    resolved = A.peek_resolved(Q1, "u-ra")
    t("e-accumulate-concepts",
      resolved.get("rescue_concepts") == [rare],
      "resolved=%s" % resolved)
    opt2 = {"src": SRC_SALES, "measure": "Сумма", "label": "sum"}
    tid2 = A.issue_decision(Q1, opt2, "measure", "v1", user="u-ra")
    A.accumulate_resolution(Q1, "u-ra", A._DECISIONS[tid2])
    resolved2 = A.peek_resolved(Q1, "u-ra")
    t("e-chain-concepts-survive-measure",
      resolved2.get("rescue_concepts") == [rare]
      and resolved2.get("src") == SRC_SALES,
      "resolved2=%s" % resolved2)
    kept_chain = A.terms_for_probe(
        {"terms": [[rare], ["value"]]},
        trusted=None, resolved=resolved2, diag={}, src=SRC_SALES, question=Q1)
    t("e-terms-ticket-resolved-exclude",
      A._homonym_norm(rare) not in {A._term_group_norm(g) for g in kept_chain},
      "kept=%s" % kept_chain)

    _save("wiki_pool_resolver")
    tries = {"n": 0}

    def _res_fail(q, cards, diag=None, concepts_only=False):
        tries["n"] += 1
        if tries["n"] == 1:
            return {"ok": False, "fail": True, "verdict": None, "concepts": []}
        return {"ok": True, "fail": False, "verdict": None, "concepts": [rare]}

    A.wiki_pool_resolver = _res_fail
    d_retry = {}
    r = A.wiki_concepts_call(Q1, [_card(SRC_SALES)], d_retry, retry=True)
    t("e-inline-retry-concepts",
      r.get("ok") and tries["n"] == 2 and d_retry.get("wiki_concepts_retry"),
      "tries=%s r=%s" % (tries["n"], r))

    tries["n"] = 0
    A.wiki_pool_resolver = lambda q, cards, diag=None, concepts_only=False: (
        tries.__setitem__("n", tries["n"] + 1) or {
            "ok": False, "fail": True, "verdict": None, "concepts": []})
    d_fail = {}
    r2 = A.wiki_concepts_call(Q1, [_card(SRC_SALES)], d_fail, retry=True)
    t("e-double-fail-unavailable",
      (not r2.get("ok")) and d_fail.get("wiki_concepts_unavailable")
      and tries["n"] == 2,
      "tries=%s" % tries["n"])

    _reset_session()
    opt_p = {"src": SRC_SALES, "label": "s", "rescue_concepts_pending": True}
    tid_p = A.issue_decision(Q1, opt_p, "entity", "v1", user="u-pend")
    A.accumulate_resolution(Q1, "u-pend", A._DECISIONS[tid_p])
    resolved_p = A.peek_resolved(Q1, "u-pend")
    t("e-pending-in-resolved",
      resolved_p.get("rescue_concepts_pending") is True)

    # продукт: issue → answer_checked(consume + pending-retry), не копия z20:5250+
    _reset_session()
    tid_ok = A.issue_decision(
        Q1, {"src": SRC_SALES, "label": "s", "rescue_concepts_pending": True},
        "entity", "v1", user="u-pend")
    _save("wiki_concepts_call", "_answer_checked_core")
    cc = {"n": 0}

    def _wc_ok(*a, **k):
        cc["n"] += 1
        return {"ok": True, "concepts": [rare], "fail": False}

    A.wiki_concepts_call = _wc_ok
    A._answer_checked_core = lambda *a, **k: {
        "kind": "answer", "text": "stub", "diag": {}, "atoms": [], "sources": []}
    A.answer_checked(Q1, decision_id=tid_ok, user="u-pend", channel="lock")
    resolved_ok = A.peek_resolved(Q1, "u-pend")
    n_first = cc["n"]
    A.answer_checked(Q1, user="u-pend", channel="lock")  # settled: без повторного concepts
    t("e-consume-retry-once",
      n_first == 1 and cc["n"] == 1
      and resolved_ok.get("rescue_concepts") == [rare]
      and resolved_ok.get("src") == SRC_SALES
      and not resolved_ok.get("rescue_concepts_pending"),
      "cc=%s n_first=%s resolved=%s" % (cc["n"], n_first, resolved_ok))

    _reset_session()
    tid_pf = A.issue_decision(
        Q1, {"src": SRC_SALES, "label": "s", "rescue_concepts_pending": True},
        "entity", "v1", user="u-pf")
    cc_f = {"n": 0}

    def _wc_fail(*a, **k):
        cc_f["n"] += 1
        return {"ok": False, "fail": True, "concepts": []}

    A.wiki_concepts_call = _wc_fail
    A._answer_checked_core = lambda *a, **k: {
        "kind": "answer", "text": "stub", "diag": {}, "atoms": [], "sources": []}
    A.answer_checked(Q1, decision_id=tid_pf, user="u-pf", channel="lock")
    resolved_pf = A.peek_resolved(Q1, "u-pf")
    n_fail = cc_f["n"]
    A.answer_checked(Q1, user="u-pf", channel="lock")
    t("e-retry-fail-empty-concepts-boundary",
      n_fail == 1 and cc_f["n"] == 1
      and resolved_pf.get("rescue_concepts") == []
      and resolved_pf.get("src") == SRC_SALES
      and not resolved_pf.get("rescue_concepts_pending"),
      "cc=%s resolved=%s" % (cc_f["n"], resolved_pf))
    _restore()


def run_R_B():
    SECTION["cur"] = "R-B"
    _reset_session()
    _install_deadline(False)
    _install_menu_passthrough()

    n = A.WIKI_PASSPORT_N + 4
    pool = _pool_n(n, leader=SRC_CLIENTS)
    enrich_slices = []
    _save("wiki_hybrid_pool", "wiki_passport_enrich_slice", "wiki_batch_verify",
          "wiki_pool_resolver", "ds_chat", "wiki_parse_verify_response",
          "deadline_hit")
    A.deadline_hit = lambda rid=None: False
    A.wiki_hybrid_pool = lambda *a, **k: list(pool)

    def _enrich(cards):
        enrich_slices.append(len(cards))
        return [dict(c, wiki_body="body-%s" % c.get("src_table")) for c in cards]

    A.wiki_passport_enrich_slice = _enrich
    A.ds_chat = lambda *a, **k: "1:yes"
    A.wiki_parse_verify_response = lambda raw, n_cards: (
        [{"index": i + 1, "fit": "no"} for i in range(n_cards)], "ok")
    batch = A.wiki_batch_verify(Q6, {"want": "count"}, pool, diag={})
    t("batch-enrich-beyond-first-8",
      len(enrich_slices) >= 2 and sum(enrich_slices) == len(pool),
      "slices=%s pool=%s" % (enrich_slices, len(pool)))
    vb_full = batch.get("verdicts_by_src") or {}
    pool_srcs = {c.get("src_table") for c in pool}
    t("batch-merge-full-list-keys",
      batch.get("incomplete") is False
      and set(vb_full) == pool_srcs
      and len(vb_full) == len(pool),
      "incomplete=%s vb=%s pool=%s" % (
          batch.get("incomplete"), set(vb_full), pool_srcs))

    # негатив: incomplete → outcome incomplete (дозапрос/меню по канону)
    enrich_slices.clear()
    A.deadline_hit = lambda rid=None: len(enrich_slices) >= 1
    batch_inc = A.wiki_batch_verify(Q6, {"want": "count"}, pool, diag={})
    oc_inc = A.wiki_outcome_from_full_verify(
        batch_inc.get("verdicts_by_src") or {}, pool, {"want": "count"}, {},
        ceiling_hit=False)
    t("batch-incomplete-triggers-menu-or-requery",
      batch_inc.get("incomplete") is True
      and oc_inc.get("outcome") == "incomplete"
      and len(batch_inc.get("verdicts_by_src") or {}) < len(pool),
      "inc=%s oc=%s vb=%s" % (
          batch_inc.get("incomplete"), oc_inc.get("outcome"),
          len(batch_inc.get("verdicts_by_src") or {})))
    A.deadline_hit = lambda rid=None: False

    vb = _verdicts_map(pool, yes_src=SRC_CLIENTS)
    oc = A.wiki_outcome_from_full_verify(
        vb, pool, {"want": "count"}, {}, ceiling_hit=False)
    t("sole-yes-full-complete",
      oc.get("outcome") == "leader" and oc.get("leader") == SRC_CLIENTS,
      "oc=%s" % oc)

    oc_c = A.wiki_outcome_from_full_verify(
        vb, pool, {"want": "count"}, {}, ceiling_hit=True)
    t("ceiling-blocks-sole",
      oc_c.get("outcome") != "leader", "oc=%s" % oc_c)

    _install_psql_basic()
    intent = {"want": "count", "terms": [["клиентов"], ["сейчас"]]}
    excl = A.conceptual_term_group_norms(
        intent["terms"], intent=intent, concepts=["клиентов"],
        src=SRC_CLIENTS, question=Q6)
    kept = A.terms_for_probe(
        intent, diag={"rescue_concepts": ["клиентов"]}, src=SRC_CLIENTS,
        question=Q6)
    t("after-sole-probe-survives-concept",
      A._homonym_norm("клиентов") in excl
      and A._homonym_norm("клиентов") not in {
          A._term_group_norm(g) for g in kept},
      "excl=%s kept=%s" % (excl, kept))

    pool2 = [_card(SRC_TMZ, LABEL_TMZ), _card(SRC_PEER, LABEL_TMZ),
             _card(SRC_OTHER, "other")]
    _save("wiki_homonym_kind_peers", "wiki_validate_leader_axes")
    A.wiki_validate_leader_axes = lambda *a, **k: True
    A.wiki_homonym_kind_peers = lambda cards, leader: [
        {"src_table": SRC_TMZ, "name": LABEL_TMZ},
        {"src_table": SRC_PEER, "name": LABEL_TMZ},
    ]
    vb2 = {SRC_TMZ: _verdict(SRC_TMZ, "yes"),
           SRC_PEER: _verdict(SRC_PEER, "no"),
           SRC_OTHER: _verdict(SRC_OTHER, "no")}
    oc_h = A.wiki_outcome_from_full_verify(vb2, pool2, {}, {})
    t("in-pool-tie-homonym-menu",
      oc_h.get("outcome") == "clarify" and oc_h.get("reason") == "homonym",
      "oc=%s" % oc_h)

    _restore()
    _install_deadline(False)
    _install_menu_passthrough()
    pool3 = [_card(SRC_CLIENTS, "clients"), _card(SRC_OTHER, "other")]
    _save("wiki_hybrid_pool", "wiki_batch_verify", "wiki_pool_resolver",
          "deadline_hit")
    A.deadline_hit = lambda rid=None: False
    A.wiki_hybrid_pool = lambda *a, **k: list(pool3)
    A.wiki_batch_verify = lambda q, intent, cards, diag=None: {
        "verdicts_by_src": _verdicts_map(cards, yes_src=SRC_CLIENTS),
        "passports": cards, "incomplete": False, "diag": {}}
    A.wiki_pool_resolver = lambda *a, **k: {
        "ok": True, "verdict": "one", "concepts": [], "fail": False}
    diag_nz = {"named_pool_zeroed": True}
    out_nz = A.wiki_rescue_full_pool_pass(
        Q6, {"want": "count"}, diag_nz, None, time.time())
    t("named-zeroed-not-silent-leader",
      not (isinstance(out_nz, dict) and out_nz.get("picked")),
      "out=%s" % out_nz)
    t("named-zeroed-menu-or-rd",
      isinstance(out_nz, dict)
      and out_nz.get("kind") in ("clarify", "no_data"),
      "kind=%s" % (out_nz.get("kind") if isinstance(out_nz, dict) else out_nz))

    pool4 = [_card("a_1", "A"), _card("a_2", "B"), _card("a_3", "C")]
    vb4 = {"a_1": _verdict("a_1", "yes"), "a_2": _verdict("a_2", "unsure"),
           "a_3": _verdict("a_3", "no")}
    oc4 = A.wiki_outcome_from_full_verify(vb4, pool4, {}, {})
    t("separability-tie-candidates",
      oc4.get("outcome") == "clarify"
      and oc4.get("reason") == "separability"
      and len(oc4.get("candidates") or []) == 2,
      "oc=%s" % oc4)
    _restore()


def run_R_C():
    SECTION["cur"] = "R-C"
    _reset_session()
    _install_psql_basic()

    groups = [["движений"], ["регистре"], ["реализации"], ["ТМЦ"]]
    spans = list(A._probe_iter_spans(groups, question=Q5))
    glues = [g for g, _n, _gis in spans]
    t("span-glue-q5-present",
      GLUE_Q5 in glues,
      "glues=%s" % glues[:12])
    t("span-min-len-8",
      all(len(g) >= 8 for g in glues),
      "short=%s" % [g for g in glues if len(g) < 8])

    # жёстко == 2 / == 3 (не «in (const, 2)» — тавтология при сдвиге const)
    t("norm-dist-short",
      A._probe_norm_dist("abcdefgh") == 2,
      "got=%s const=%s" % (
          A._probe_norm_dist("abcdefgh"), A._PROBE_NORM_DIST))
    t("norm-dist-long-ge16",
      A._probe_norm_dist("a" * 16) == 3,
      "got=%s const=%s" % (
          A._probe_norm_dist("a" * 16), A._PROBE_NORM_DIST_LONG))

    # --- синтетика у порога: DL==допуск → hit; DL==допуск+1 → miss ---
    def _synth_pair(length, want_dl):
        """Пара одинаковой длины с фактическим DL=want_dl (считаем, не угадываем)."""
        base = "a" * length
        for k in range(0, length + 1):
            other = ("z" * k) + ("a" * (length - k))
            if len(other) == length and _dl_mock(base, other) == want_dl:
                return base, other
        raise AssertionError(
            "no synth pair len=%s dl=%s" % (length, want_dl))

    short_d = int(getattr(A, "_PROBE_NORM_DIST", 2))
    long_d = int(getattr(A, "_PROBE_NORM_DIST_LONG", 3))
    long_at = int(getattr(A, "_PROBE_NORM_LONG_AT", 16))
    g_s, tgt_hit_s = _synth_pair(8, short_d)
    _, tgt_miss_s = _synth_pair(8, short_d + 1)
    t("synth-short-dl-at-threshold",
      _dl_mock(g_s, tgt_hit_s) == short_d
      and _dl_mock(g_s, tgt_miss_s) == short_d + 1
      and len(g_s) >= 8 and len(tgt_hit_s) >= 8,
      "hit_dl=%s miss_dl=%s short_d=%s" % (
          _dl_mock(g_s, tgt_hit_s), _dl_mock(g_s, tgt_miss_s), short_d))
    hits_s = A._probe_src_name_hit_glues(
        [g_s], src="catalog_%s" % tgt_hit_s, diag={})
    miss_s = A._probe_src_name_hit_glues(
        [g_s], src="catalog_%s" % tgt_miss_s, diag={})
    t("synth-short-hit-at-dist",
      g_s in hits_s, "hits=%s pair=%s/%s" % (hits_s, g_s, tgt_hit_s))
    t("synth-short-miss-at-dist-plus1",
      g_s not in miss_s, "miss=%s pair=%s/%s" % (miss_s, g_s, tgt_miss_s))

    g_l, tgt_hit_l = _synth_pair(long_at, long_d)
    _, tgt_miss_l = _synth_pair(long_at, long_d + 1)
    t("synth-long-dl-at-threshold",
      _dl_mock(g_l, tgt_hit_l) == long_d
      and _dl_mock(g_l, tgt_miss_l) == long_d + 1
      and len(g_l) >= long_at,
      "hit_dl=%s miss_dl=%s long_d=%s" % (
          _dl_mock(g_l, tgt_hit_l), _dl_mock(g_l, tgt_miss_l), long_d))
    hits_l = A._probe_src_name_hit_glues(
        [g_l], src="catalog_%s" % tgt_hit_l, diag={})
    miss_l = A._probe_src_name_hit_glues(
        [g_l], src="catalog_%s" % tgt_miss_l, diag={})
    t("synth-long-hit-at-dist",
      g_l in hits_l, "hits=%s pair=%s/%s" % (hits_l, g_l, tgt_hit_l))
    t("synth-long-miss-at-dist-plus1",
      g_l not in miss_l, "miss=%s pair=%s/%s" % (miss_l, g_l, tgt_miss_l))

    q_hole = "реализации XXX ТМЦ"
    groups_h = [["реализации"], ["ТМЦ"]]
    spans_h = list(A._probe_iter_spans(groups_h, question=q_hole))
    t("continuity-hole-breaks-span",
      not any(g == GLUE_Q5 or g == A._probe_norm("реализации ТМЦ")
              for g, _n, _gis in spans_h),
      "spans=%s" % spans_h)

    per = {
        0: (2, ["ts_levenshtein('реализации', 2)"], "fuzzy"),
    }
    span_hits = [(
        GLUE_Q5, 2, frozenset({0, 1}),
        ["ts_levenshtein('%s', 2)" % GLUE_Q5])]
    diag = {}
    A._probe_apply_span_supersede(per, 2, span_hits, diag)
    t("supersede-fuzzy-both-norm",
      0 in per and per[0][2] == "norm"
      and 1 in per and per[1][2] == "norm"
      and per[0][1] == per[1][1],
      "per=%s diag=%s" % (per, diag.get("_norm")))

    per_ex = {
        0: (0, ["ts_phrase('a')"], "exact"),
        1: (0, ["ts_phrase('b')"], "exact"),
    }
    diag_ex = {}
    A._probe_apply_span_supersede(
        per_ex, 2,
        [(GLUE_Q5, 2, frozenset({0, 1}), ["span_expr"])],
        diag_ex)
    t("supersede-exact-untouched",
      per_ex[0][2] == "exact" and per_ex[1][2] == "exact"
      and not diag_ex.get("_norm"),
      "per=%s" % per_ex)

    per_ok = {0: (0, ["e"], "exact"), 1: (0, ["e"], "exact")}
    trig = A._probe_span_trigger(
        per_ok, 2, [(GLUE_Q5, 2, frozenset({0, 1}), ["x"])])
    t("trigger-no-soft-no-unmatched", trig is False)
    # позитив: unmatched ∨ fuzzy → True
    per_un = {0: (0, ["e"], "exact")}  # gi=1 unmatched
    t("trigger-unmatched-fires",
      A._probe_span_trigger(
          per_un, 2, [(GLUE_Q5, 2, frozenset({0, 1}), ["x"])]) is True)
    per_fz = {0: (2, ["e"], "fuzzy"), 1: (2, ["e"], "fuzzy")}
    t("trigger-fuzzy-fires",
      A._probe_span_trigger(
          per_fz, 2, [(GLUE_Q5, 2, frozenset({0, 1}), ["x"])]) is True)

    hits = A._probe_src_name_hit_glues(
        [GLUE_Q5, "коротко"], src=SRC_TMZ, src_label=LABEL_TMZ, diag={})
    t("wiki-damerau-src-name-hit",
      GLUE_Q5 in hits,
      "hits=%s dl=%s" % (hits, _dl_mock(GLUE_Q5, TAIL_TMZ)))

    # --- (iii) жёстко: группа src-имени в excl ТОЛЬКО через DL-хит к хвосту ---
    SRC_NAME_GROUP = ["реализации", "ТМЦ"]
    SRC_NAME_NORM = A._term_group_norm(SRC_NAME_GROUP)  # primary → «реализации»
    terms = [["движений"], ["регистре"], SRC_NAME_GROUP]
    _install_psql_basic()
    if hasattr(A, "_III_SPAN_HIT_CACHE"):
        A._III_SPAN_HIT_CACHE.clear()
    card_tmz = _card(SRC_TMZ, LABEL_TMZ, layer=2)
    excl = A.conceptual_term_group_norms(
        terms, intent={"kind": "регистре", "want": "count"}, concepts=[],
        src=SRC_TMZ, question=Q5, card=card_tmz, src_layer=2)
    # (iii): норм-склейка реализациитмц И норма группы — в excl
    t("src-name-in-terms-exclude",
      GLUE_Q5 in excl and SRC_NAME_NORM in excl,
      "excl=%s (need glue=%s + group=%s via iii)" % (
          excl, GLUE_Q5, SRC_NAME_NORM))
    # платформенные — отдельным под-assert (не подменяют (iii))
    t("platform-words-in-excl",
      A._homonym_norm("движений") in excl
      and A._homonym_norm("регистре") in excl,
      "excl=%s" % excl)
    # негатив: нет DL-хита (чужой хвост / пустой iii) → группа НЕ исключена
    if hasattr(A, "_III_SPAN_HIT_CACHE"):
        A._III_SPAN_HIT_CACHE.clear()
    _save("_iii_span_hit_glues")
    A._iii_span_hit_glues = lambda *a, **k: (set(), {})
    excl_neg = A.conceptual_term_group_norms(
        terms, intent={"kind": "регистре", "want": "count"}, concepts=[],
        src=SRC_TMZ, question=Q5, card=card_tmz, src_layer=2)
    kept_neg = A.filter_terms_by_concepts(terms, excl_neg, diag={})[0]
    t("src-name-exclude-requires-iii-hit",
      GLUE_Q5 not in excl_neg and SRC_NAME_NORM not in excl_neg
      and any(A._term_group_norm(g) == SRC_NAME_NORM for g in kept_neg),
      "excl_neg=%s kept_neg=%s" % (excl_neg, kept_neg))
    _restore()
    _install_psql_basic()

    # q5 count: имя src ИСКЛЮЧЕНО из probe → счёт по всему src (без сужения)
    if hasattr(A, "_III_SPAN_HIT_CACHE"):
        A._III_SPAN_HIT_CACHE.clear()
    excl_q5 = A.conceptual_term_group_norms(
        terms, intent={"kind": "регистре", "want": "count"}, concepts=[],
        src=SRC_TMZ, question=Q5, card=card_tmz, src_layer=2)
    kept_q5 = A.filter_terms_by_concepts(terms, excl_q5, diag={})[0]
    t("q5-count-without-src-name-narrowing",
      SRC_NAME_NORM in excl_q5 and GLUE_Q5 in excl_q5
      and not any(A._term_group_norm(g) == SRC_NAME_NORM for g in kept_q5)
      and not any(
          A._homonym_norm(a) == SRC_NAME_NORM
          or A._homonym_norm(a) == A._homonym_norm("ТМЦ")
          for g in kept_q5
          for a in (g if isinstance(g, (list, tuple)) else [g])),
      "excl=%s kept=%s" % (excl_q5, kept_q5))
    # probe на раздельных группах: kind=src_name; мок count>0 на lit не-excluded
    terms_sep = [["движений"], ["регистре"], ["реализации"], ["ТМЦ"]]
    _save("psql")
    _psql_prev = A.psql

    def _psql_probe_q5(sql):
        qs = " ".join(str(sql).lower().split())
        if "damerau_levenshtein" in qs:
            return _psql_damerau(sql)
        if "union all" in qs and "count(*)" in qs:
            idxs = re.findall(r"select\s+(\d+)\s+i\b", sql, flags=re.I)
            return [[int(i), 3] for i in idxs]
        if callable(_psql_prev):
            return _psql_prev(sql)
        return []

    A.psql = _psql_probe_q5
    if hasattr(A, "_III_SPAN_HIT_CACHE"):
        A._III_SPAN_HIT_CACHE.clear()
    exprs_q5, kinds_q5 = A.probe(
        terms_sep, question=Q5, src=SRC_TMZ, src_label=LABEL_TMZ)
    A.psql = _psql_prev
    excl_gis = set(kinds_q5.get("probe_src_name_excluded") or [])
    t("q5-probe-src-name-kind",
      kinds_q5.get(2) == "src_name" and kinds_q5.get(3) == "src_name"
      and 2 in excl_gis and 3 in excl_gis,
      "kinds=%s" % {k: kinds_q5.get(k) for k in (2, 3, "probe_src_name_excluded")})
    blob_exprs = " ".join(str(e) for e in (exprs_q5 or [])).lower()
    # непустые exprs у не-excluded; пустой match по имени — только у excluded gis
    t("q5-probe-no-src-name-match-expr",
      bool(exprs_q5)
      and "реализац" not in blob_exprs and "тмц" not in blob_exprs
      and kinds_q5.get(2) == "src_name" and kinds_q5.get(3) == "src_name"
      and 2 in excl_gis and 3 in excl_gis,
      "exprs=%s kinds=%s excl=%s" % (
          exprs_q5,
          {k: kinds_q5.get(k) for k in (0, 1, 2, 3, "probe_src_name_excluded")},
          excl_gis))

    # wiki-ветка поведенческая: живой wiki_hybrid_pool(rescue) → diag pool
    _save("_ensure_embed_secret", "_wiki_hybrid_sql", "psql",
          "wiki_batch_verify", "wiki_pool_resolver", "deadline_hit")
    A.deadline_hit = lambda rid=None: False
    A._ensure_embed_secret = lambda: None
    A._wiki_hybrid_sql = lambda: (
        "SELECT src_table, name, description, axes, measures, covered, "
        "distance, parent, platform_prefix, src_layer FROM selected")
    hybrid_row = [
        SRC_TMZ, LABEL_TMZ, "fixture", "", "", 1, 0.05, "", "", 2]
    # hybrid-строка только при DL-хите склейки↔хвост (порог продукта)
    _damerau_fn = {"f": _psql_damerau}

    def _glue_hits_src_tail(question, src):
        glues = list(A._rescue_norm_glues(question) or [])
        pos = str(src).find("_")
        tail = (str(src)[pos + 1:] if pos >= 0 else str(src))
        tail = tail.replace(" ", "").lower()
        glues = [g for g in glues if len(g) >= 8]
        if not glues or len(tail) < 8:
            return False
        dist = int(getattr(A, "WIKI_NORM_DIST", 2))
        g_lit = ", ".join("'%s'" % str(g).replace("'", "''") for g in glues)
        sql = (
            "SELECT g.glue FROM unnest([%s]) AS g(glue), "
            "unnest(['%s']) AS t(tgt) WHERE length(g.glue) >= 8 "
            "AND damerau_levenshtein(g.glue, t.tgt) <= %d"
            % (g_lit, tail.replace("'", "''"), dist))
        return bool(_damerau_fn["f"](sql))

    def _psql_wiki(sql):
        qs = " ".join(str(sql).lower().split())
        if "damerau_levenshtein" in qs:
            return _damerau_fn["f"](sql)
        # rescue hybrid / selected / knn / struct_norm — только при DL-хите
        if ("from selected" in qs or "from pool" in qs or "from knn" in qs
                or "struct_norm" in qs or "ai_embed" in qs
                or "src_table" in qs):
            if _glue_hits_src_tail(Q5, SRC_TMZ):
                return [hybrid_row]
            return []
        return []

    A.psql = _psql_wiki
    A.wiki_batch_verify = lambda q, intent, cards, diag=None: {
        "verdicts_by_src": _verdicts_map(cards, yes_src=SRC_TMZ),
        "passports": cards, "incomplete": False, "diag": {}}
    A.wiki_pool_resolver = lambda *a, **k: {
        "ok": True, "verdict": "one", "concepts": [], "fail": False}
    diag_w = {}
    # не мокаем wiki_hybrid_pool — зовём продукт
    cards_w = A.wiki_hybrid_pool(
        Q5, {"want": "count"}, rescue_mode=True, diag=diag_w)
    t("wiki-hybrid-rescue-returns-src",
      any(c.get("src_table") == SRC_TMZ for c in (cards_w or []))
      and diag_w.get("rescue_no_axis_filter") is True,
      "cards=%s diag=%s" % (
          [c.get("src_table") for c in (cards_w or [])], diag_w))
    diag_pass = {}
    A.wiki_rescue_full_pool_pass(
        Q5, {"want": "count"}, diag_pass, None, time.time())
    t("wiki-rescue-pool-has-src-via-norm",
      SRC_TMZ in (diag_pass.get("wiki_rescue_pool") or [])
      and diag_pass.get("wiki_full_pool") is True,
      "pool=%s" % diag_pass.get("wiki_rescue_pool"))
    # негатив: без DL-хита hybrid пуст → src НЕ в wiki_rescue_pool
    _damerau_fn["f"] = lambda sql: []
    diag_miss = {}
    cards_miss = A.wiki_hybrid_pool(
        Q5, {"want": "count"}, rescue_mode=True, diag=diag_miss)
    diag_pass_miss = {}
    A.wiki_rescue_full_pool_pass(
        Q5, {"want": "count"}, diag_pass_miss, None, time.time())
    t("wiki-rescue-pool-empty-without-damerau-hit",
      not cards_miss
      and SRC_TMZ not in (diag_pass_miss.get("wiki_rescue_pool") or []),
      "cards=%s pool=%s" % (
          cards_miss, diag_pass_miss.get("wiki_rescue_pool")))
    _damerau_fn["f"] = _psql_damerau

    # --- негатив «похожий хвост другого src»: DL≤допуск у двух src → не sole ---
    short_d_peer = int(getattr(A, "_PROBE_NORM_DIST", 2))
    t("peer-tail-dl-within-dist",
      _dl_mock(GLUE_Q5, TAIL_TMZ) <= short_d_peer,
      "dl=%s dist=%s" % (_dl_mock(GLUE_Q5, TAIL_TMZ), short_d_peer))
    hits_tmz = A._probe_src_name_hit_glues(
        [GLUE_Q5], src=SRC_TMZ, src_label=LABEL_TMZ, diag={})
    hits_peer = A._probe_src_name_hit_glues(
        [GLUE_Q5], src=SRC_PEER, src_label=LABEL_TMZ, diag={})
    t("peer-tail-both-src-hit-glue",
      GLUE_Q5 in hits_tmz and GLUE_Q5 in hits_peer,
      "tmz=%s peer=%s" % (hits_tmz, hits_peer))
    _restore()
    _install_deadline(False)
    _install_menu_passthrough()
    _install_psql_basic()
    pool_peer = [_card(SRC_TMZ, LABEL_TMZ), _card(SRC_PEER, LABEL_TMZ),
                 _card(SRC_OTHER, "other")]
    _save("wiki_hybrid_pool", "wiki_batch_verify", "wiki_pool_resolver",
          "wiki_leader_post_verify", "wiki_homonym_kind_peers",
          "deadline_hit")
    A.deadline_hit = lambda rid=None: False
    A.wiki_hybrid_pool = lambda *a, **k: list(pool_peer)
    A.wiki_leader_post_verify = lambda *a, **k: True
    A.wiki_homonym_kind_peers = lambda *a, **k: []
    A.wiki_pool_resolver = lambda *a, **k: {
        "ok": True, "verdict": "many", "concepts": [], "fail": False}
    # батч без sole (все no) → clarify/меню, не silent picked
    A.wiki_batch_verify = lambda *a, **k: {
        "verdicts_by_src": _verdicts_map(pool_peer),
        "passports": pool_peer, "incomplete": False, "diag": {}}
    diag_peer = {}
    out_peer = A.wiki_rescue_full_pool_pass(
        Q5, {"want": "count"}, diag_peer, None, time.time())
    t("peer-tail-no-sole-not-silent-picked",
      isinstance(out_peer, dict)
      and not out_peer.get("picked")
      and out_peer.get("kind") == "clarify"
      and len(out_peer.get("options") or []) >= 2,
      "out=%s" % out_peer)
    # два yes на похожих хвостах — тоже не единственный лидер
    vb_two = {
        SRC_TMZ: _verdict(SRC_TMZ, "yes"),
        SRC_PEER: _verdict(SRC_PEER, "yes"),
        SRC_OTHER: _verdict(SRC_OTHER, "no"),
    }
    oc_two = A.wiki_outcome_from_full_verify(
        vb_two, pool_peer, {"want": "count"}, {}, ceiling_hit=False)
    t("peer-tail-two-yes-not-sole-leader",
      oc_two.get("outcome") != "leader"
      or oc_two.get("leader") not in (SRC_TMZ, SRC_PEER),
      "oc=%s" % oc_two)
    A.wiki_batch_verify = lambda *a, **k: {
        "verdicts_by_src": vb_two,
        "passports": pool_peer, "incomplete": False, "diag": {}}
    diag_two = {}
    out_two = A.wiki_rescue_full_pool_pass(
        Q5, {"want": "count"}, diag_two, None, time.time())
    t("peer-tail-two-yes-menu-not-picked",
      isinstance(out_two, dict)
      and not out_two.get("picked")
      and out_two.get("kind") in ("clarify", "no_data"),
      "out=%s" % out_two)

    short_spans = list(A._probe_iter_spans(
        [["ab"], ["cd"]], question="ab cd"))
    t("min-len-drops-short",
      short_spans == [] or all(len(g) >= 8 for g, *_ in short_spans),
      "spans=%s" % short_spans)
    _restore()


def run_R_D():
    SECTION["cur"] = "R-D"
    _reset_session()
    _install_deadline(False)
    _install_menu_passthrough()
    _save("wiki_hybrid_pool", "wiki_batch_verify", "wiki_pool_resolver",
          "wiki_leader_post_verify", "deadline_hit", "wiki_concepts_call",
          "wiki_homonym_kind_peers", "wiki_leader_db_homonym_gate")
    A.deadline_hit = lambda rid=None: False

    A.wiki_hybrid_pool = lambda *a, **k: []
    diag = {}
    out = A.wiki_rescue_full_pool_pass("q", {}, diag, None, time.time())
    t("empty-pool-returns-none",
      out is None and diag.get("wiki_full_pool") is True
      and diag.get("wiki_rescue_pool_n") == 0,
      "out=%s" % out)

    pool = [_card(SRC_OTHER, "o1"), _card(SRC_FAR, "o2")]
    A.wiki_hybrid_pool = lambda *a, **k: list(pool)
    A.wiki_batch_verify = lambda *a, **k: {
        "verdicts_by_src": _verdicts_map(pool),
        "passports": pool, "incomplete": False, "diag": {}}
    A.wiki_pool_resolver = lambda *a, **k: {
        "ok": True, "verdict": "none", "concepts": [], "fail": False}
    diag2 = {}
    out2 = A.wiki_rescue_full_pool_pass("q", {}, diag2, None, time.time())
    t("none-full-coverage-no_data",
      isinstance(out2, dict) and out2.get("kind") == "no_data",
      "out=%s" % out2)

    pool1 = [_card(SRC_OTHER, "only")]
    A.wiki_hybrid_pool = lambda *a, **k: list(pool1)
    A.wiki_batch_verify = lambda *a, **k: {
        "verdicts_by_src": {SRC_OTHER: _verdict(SRC_OTHER, "no")},
        "passports": pool1, "incomplete": False, "diag": {}}
    A.wiki_pool_resolver = lambda *a, **k: {
        "ok": True, "verdict": "many", "concepts": [], "fail": False}
    diag3 = {}
    out3 = A.wiki_rescue_full_pool_pass("q", {}, diag3, None, time.time())
    t("non-sole-pool1-no_data",
      isinstance(out3, dict) and out3.get("kind") == "no_data",
      "out=%s" % out3)

    A.wiki_hybrid_pool = lambda *a, **k: list(pool)
    A.wiki_batch_verify = lambda *a, **k: {
        "verdicts_by_src": _verdicts_map(pool, yes_src=SRC_FAR),
        "passports": pool, "incomplete": False, "diag": {}}
    A.wiki_pool_resolver = lambda *a, **k: {
        "ok": True, "verdict": "many", "concepts": [], "fail": False}
    A.wiki_leader_post_verify = lambda *a, **k: False
    A.wiki_homonym_kind_peers = lambda *a, **k: []
    diag4 = {}
    out4 = A.wiki_rescue_full_pool_pass("q", {}, diag4, None, time.time())
    t("post_verify-fail-no_data",
      isinstance(out4, dict) and out4.get("kind") == "no_data",
      "out=%s" % out4)

    A.wiki_concepts_call = lambda *a, **k: {
        "ok": True, "concepts": [], "fail": False}
    diag5 = {"wiki_full_pool": True}
    p2 = A._point2_unmatched_gate(
        "q", {"terms": [["чужоезначениеxyz"]]}, diag5, None, time.time(),
        src=SRC_SALES, probe_terms=[["чужоезначениеxyz"]], kinds={})
    t("nonconcept-unmatched-point2-nodata",
      p2 is None and diag5.get("point2_branch") == 1,
      "p2=%s branch=%s" % (p2, diag5.get("point2_branch")))

    A.wiki_leader_post_verify = lambda *a, **k: True
    A.wiki_leader_db_homonym_gate = lambda *a, **k: None
    tries = {"n": 0}

    def _res_fail(*a, **k):
        tries["n"] += 1
        return {"ok": False, "fail": True, "verdict": None, "concepts": []}

    A.wiki_pool_resolver = _res_fail
    A.wiki_hybrid_pool = lambda *a, **k: list(pool)
    A.wiki_batch_verify = lambda *a, **k: {
        "verdicts_by_src": _verdicts_map(pool, yes_src=SRC_FAR),
        "passports": pool, "incomplete": False, "diag": {}}
    intent_gap = {"terms": [["valuegapxyz"]], "want": "sum"}
    diag6 = {}
    out6 = A.wiki_rescue_full_pool_pass(
        "q", intent_gap, diag6, None, time.time())
    t("concepts-fail-remaining-nonconcept-demote",
      isinstance(out6, dict) and out6.get("kind") in ("clarify", "no_data"),
      "out=%s pending=%s" % (
          out6.get("kind") if isinstance(out6, dict) else out6,
          diag6.get("rescue_concepts_pending")))

    A.wiki_pool_resolver = lambda *a, **k: {
        "ok": True, "verdict": "many", "concepts": [], "fail": False}
    A.wiki_batch_verify = lambda *a, **k: {
        "verdicts_by_src": _verdicts_map(pool),
        "passports": pool, "incomplete": False, "diag": {}}
    diag7 = {}
    out7 = A.wiki_rescue_full_pool_pass("q", {}, diag7, None, time.time())
    t("many-on-none-is-menu",
      isinstance(out7, dict) and out7.get("kind") == "clarify",
      "out=%s" % out7)

    # sole-yes (полный batch, ¬ceiling) → гейт fail-soft/clarify → не silent picked
    pool_h = [_card(SRC_FAR, "far"), _card(SRC_OTHER, "other")]
    vb_h = _verdicts_map(pool_h, yes_src=SRC_FAR)
    oc_h = A.wiki_outcome_from_full_verify(
        vb_h, pool_h, {"want": "sum"}, {}, ceiling_hit=False)
    t("homonym-fail-sole-fixture",
      oc_h.get("outcome") == "leader" and oc_h.get("leader") == SRC_FAR,
      "oc=%s" % oc_h)
    A.wiki_hybrid_pool = lambda *a, **k: list(pool_h)
    A.wiki_batch_verify = lambda *a, **k: {
        "verdicts_by_src": vb_h,
        "passports": pool_h, "incomplete": False, "diag": {}}
    A.wiki_pool_resolver = lambda *a, **k: {
        "ok": True, "verdict": "many", "concepts": [], "fail": False}
    A.wiki_leader_post_verify = lambda *a, **k: True
    gate_calls = {"n": 0}

    def _gate_fail_soft(leader, question, intent, diag, cut, t0,
                        by=None, match="", preds=None, plan=None):
        """Сигнатура = wiki_leader_db_homonym_gate; fail-soft R6."""
        gate_calls["n"] += 1
        gate_calls["leader"] = leader
        return A.wiki_homonym_peer_fail_soft(question, diag, cut, t0)

    A.wiki_leader_db_homonym_gate = _gate_fail_soft
    diag_h = {}
    out_h = A.wiki_rescue_full_pool_pass(
        "q", {"want": "sum"}, diag_h, None, time.time())
    d_h = (out_h.get("diag") or {}) if isinstance(out_h, dict) else {}
    why_h = (out_h.get("why") if isinstance(out_h, dict) else None) or (
        d_h.get("reason") or "")
    is_fail = (
        isinstance(out_h, dict)
        and not out_h.get("picked")
        and not (out_h.get("atoms") or [])
        and out_h.get("kind") == "answer"
        and (d_h.get("wiki_homonym_peer_check") == "error"
             or d_h.get("wiki_pick") == "homonym_peer_fail"))
    is_menu = (
        isinstance(out_h, dict)
        and not out_h.get("picked")
        and out_h.get("kind") == "clarify"
        and (why_h == "wiki_homonym_db"
             or d_h.get("wiki_pick") == "clarify"
             or d_h.get("wiki_homonym_db_peers")))
    t("homonym-fail-after-sole-yes",
      gate_calls["n"] == 1
      and gate_calls.get("leader") == SRC_FAR
      and (is_fail or is_menu),
      "out=%s gate=%s diag=%s" % (out_h, gate_calls, d_h))
    _restore()


def run_R_E():
    SECTION["cur"] = "R-E"
    _reset_session()
    _install_deadline(False)
    _install_menu_passthrough()
    _save("try_wiki_hybrid_entity_pick", "wiki_rescue_full_pool_pass",
          "deadline_hit")
    A.deadline_hit = lambda rid=None: False
    calls = {"n": 0}

    def _resc(*a, **k):
        calls["n"] += 1
        return {"picked": [SRC_SALES], "marks": {}, "plan": {}}

    A.wiki_rescue_full_pool_pass = _resc
    A.try_wiki_hybrid_entity_pick = lambda *a, **k: {
        "picked": [SRC_SALES], "marks": {}, "plan": {}}
    diag = {}
    out = A.wiki_primary_entity_cascade(
        Q1, {}, [], diag, None, time.time(), {}, "", [], {})
    t("live-outcome-zero-point1",
      calls["n"] == 0 and out.get("picked") == [SRC_SALES],
      "n=%s out=%s" % (calls["n"], out))

    calls["n"] = 0
    A.try_wiki_hybrid_entity_pick = lambda *a, **k: {
        "kind": "no_data", "text": "refuse", "sources": [],
        "diag": {"reason": "wiki_none_empty"}}
    diag2 = {}
    out2 = A.wiki_primary_entity_cascade(
        "привет", {}, [], diag2, None, time.time(), {}, "", [], {})
    t("offtopic-zero-point1",
      calls["n"] == 0 and out2.get("kind") == "no_data",
      "n=%s" % calls["n"])

    calls["n"] = 0
    A.try_wiki_hybrid_entity_pick = lambda *a, **k: None
    diag3 = {}
    A.wiki_primary_entity_cascade(
        Q1, {}, [], diag3, None, time.time(), {}, "", [], {})
    t("cascade-death-one-point1",
      calls["n"] == 1, "n=%s" % calls["n"])
    _restore()


def run_R_F():
    SECTION["cur"] = "R-F"
    _reset_session()
    _save("_base_knows_kind_or_measure")
    A._base_knows_kind_or_measure = lambda w: False

    def _install_answer_shell():
        _save("deadline_hit", "period_readings",
              "expand_readings_calendar_axis", "expand_readings_currency_axis",
              "parse_intent", "sales_compare_intent", "wiki_primary_entity_cascade")
        A.deadline_hit = lambda rid=None: False
        A.period_readings = lambda *a, **k: []
        A.expand_readings_calendar_axis = lambda r, **k: r
        A.expand_readings_currency_axis = lambda r, **k: r
        A.sales_compare_intent = lambda *a, **k: False

    def _assert_stamp_payload(tag, out, *, checkpoint, outcome, want_uw=None,
                              want_utm=None):
        d = (out.get("diag") or {}) if isinstance(out, dict) else {}
        ji = A._journal_intent(out)
        ok = (
            d.get("checkpoint") == checkpoint
            and (d.get("outcome") == outcome or out.get("kind") == outcome)
            and "unknown_words" in d and "unknown_terms_unmatched" in d
            and ji.get("checkpoint") == checkpoint
            and "unknown_words" in ji and "unknown_terms_unmatched" in ji
            and ji.get("outcome") == outcome)
        if want_uw is not None:
            ok = ok and want_uw in (d.get("unknown_words") or [])
        if want_utm is not None:
            ok = ok and want_utm in (d.get("unknown_terms_unmatched") or [])
        t(tag, ok,
          "kind=%s cp=%s oc=%s uw=%s utm=%s ji=%s" % (
              out.get("kind") if isinstance(out, dict) else out,
              d.get("checkpoint"), d.get("outcome"),
              d.get("unknown_words"), d.get("unknown_terms_unmatched"), ji))

    # --- 1) point1 смерть каскада → clarify + штамп ---
    _install_answer_shell()
    A.parse_intent = lambda q, today: {
        "measure": "наторговали", "kind": "", "want": "sum",
        "terms": [["наторговали"]], "parse": {}, "period": None}
    A.wiki_primary_entity_cascade = lambda *a, **k: {
        "kind": "clarify",
        "options": [{"src": SRC_SALES, "label": "a"},
                    {"src": SRC_OTHER, "label": "b"}],
        "text": "уточните", "diag": {}, "partial": None}
    out_p1 = A.answer(Q1)
    _assert_stamp_payload(
        "point1-cascade-death-stamp", out_p1,
        checkpoint="point1", outcome="clarify", want_uw="наторговали")

    # --- 2) point2 ветка (1) no_data → штамп ---
    _restore()
    _reset_session()
    _save("_base_knows_kind_or_measure")
    A._base_knows_kind_or_measure = lambda w: False
    _install_answer_shell()
    _save("refcols_of", "count_defer_measure_clarify", "human_table_label",
          "terms_for_probe", "probe", "_point2_unmatched_gate",
          "_settle_measure", "_settle_axis")
    A.parse_intent = lambda q, today: {
        "measure": "", "kind": "", "want": "count",
        "terms": [["чужоеxyz"]], "parse": {}, "period": None}
    A.wiki_primary_entity_cascade = lambda *a, **k: {
        "picked": [SRC_SALES], "marks": {}, "plan": {}}
    A.refcols_of = lambda src: []
    A.count_defer_measure_clarify = lambda *a, **k: True
    A.human_table_label = lambda src, lab=None: src
    A.terms_for_probe = lambda intent, **k: list(intent.get("terms") or [])
    A.probe = lambda terms, **k: ([], {})  # unmatched
    A._point2_unmatched_gate = lambda *a, **k: None  # ветка (1)
    out_p2 = A.answer("сколько чужоеxyz")
    _assert_stamp_payload(
        "point2-branch1-nodata-stamp", out_p2,
        checkpoint="point2", outcome="no_data", want_utm="чужоеxyz")

    # --- 3) R-I деградация меню → clarify + штамп через point1 return ---
    _restore()
    _reset_session()
    _save("_base_knows_kind_or_measure")
    A._base_knows_kind_or_measure = lambda w: False
    _install_answer_shell()
    A.parse_intent = lambda q, today: {
        "measure": "наторговали", "kind": "", "want": "sum",
        "terms": [["наторговали"]], "parse": {}, "period": None}
    A.wiki_primary_entity_cascade = lambda *a, **k: {
        "kind": "clarify",
        "options": [{"src": SRC_OTHER, "label": "A"},
                    {"src": SRC_FAR, "label": "B"}],
        "text": "wiki_rescue",
        "diag": {"wiki_rescue_menu_degraded": True}}
    out_ri = A.answer(Q1)
    d_ri = out_ri.get("diag") or {}
    t("ri-degrade-menu-flag",
      d_ri.get("wiki_rescue_menu_degraded") is True)
    _assert_stamp_payload(
        "ri-degrade-stamp", out_ri,
        checkpoint="point1", outcome="clarify", want_uw="наторговали")

    # --- source-scan: каждый return точек 1/2 зовёт штамп ---
    ans_src = inspect.getsource(A.answer)
    i_p1 = ans_src.find("_ep = wiki_primary_entity_cascade")
    i_p1_end = ans_src.find("if about_coverage:", i_p1)
    block_p1 = ans_src[i_p1:i_p1_end] if i_p1 >= 0 and i_p1_end > i_p1 else ""
    bad_p1 = _stamp_returns_ok(block_p1, allow_menu=False)
    t("source-scan-point1-returns-stamp",
      bool(block_p1) and not bad_p1
      and "_c3_stamp_out" in block_p1 and "_c3_stamp_diag" in block_p1,
      "bad=%s" % bad_p1)

    i_p2 = ans_src.find("_p2 = _point2_unmatched_gate")
    i_p2_end = ans_src.find("match, _k = match_expr", i_p2)
    block_p2 = ans_src[i_p2:i_p2_end] if i_p2 >= 0 and i_p2_end > i_p2 else ""
    bad_p2 = _stamp_returns_ok(block_p2, allow_menu=True)
    t("source-scan-point2-returns-stamp",
      bool(block_p2) and not bad_p2
      and block_p2.count("_c3_stamp") >= 2,
      "bad=%s n_stamp=%s" % (bad_p2, block_p2.count("_c3_stamp")))

    # call-site scan: все _c3_stamp_* в answer на checkpoint point1/point2
    stamp_sites = list(re.finditer(r"_c3_stamp_(?:out|diag)\(", ans_src))
    t("source-scan-stamp-call-sites",
      len(stamp_sites) >= 4,
      "n=%s" % len(stamp_sites))

    # прямые юнит-проверки штамп-хелперов (корм)
    intent = {"measure": "наторговали", "kind": "",
              "terms": [["наторговали"]]}
    diag = {"rescue_concepts": ["наторговали"]}
    A._c3_stamp_diag(diag, intent, checkpoint="point1", outcome="clarify")
    t("stamp-unknown_words",
      "наторговали" in (diag.get("unknown_words") or []),
      "uw=%s" % diag.get("unknown_words"))
    t("stamp-checkpoint", diag.get("checkpoint") == "point1")
    t("stamp-outcome", diag.get("outcome") == "clarify")

    diag2 = {}
    A._c3_stamp_diag(
        diag2, {"terms": [["чужоеxyz"]]}, checkpoint="point2",
        outcome="no_data", probe_terms=[["чужоеxyz"]], kinds={})
    t("stamp-unknown_terms_unmatched",
      "чужоеxyz" in (diag2.get("unknown_terms_unmatched") or []),
      "utm=%s" % diag2.get("unknown_terms_unmatched"))

    src_ji = inspect.getsource(A._journal_intent)
    t("journal-intent-reads-both-keys",
      "unknown_words" in src_ji and "unknown_terms_unmatched" in src_ji)

    A._base_knows_kind_or_measure = lambda w: True
    d_empty = {}
    A._c3_stamp_diag(d_empty, intent, checkpoint="point1")
    t("offline-known-feed-empty",
      d_empty.get("unknown_words") == [],
      "uw=%s" % d_empty.get("unknown_words"))
    _restore()


def run_R_G():
    SECTION["cur"] = "R-G"
    _reset_session()
    _install_deadline(False)
    _install_menu_passthrough()

    src_iss = inspect.getsource(A.issue_decision)
    t("whitelist-rescue_concepts",
      "rescue_concepts" in src_iss
      and "rescue_concepts_pending" in src_iss)
    src_acc = inspect.getsource(A.accumulate_resolution)
    t("accumulate-both-keys",
      "rescue_concepts" in src_acc
      and "rescue_concepts_pending" in src_acc)

    # клик: issue → answer_checked(consume) на билете rescue-меню → 0 rescue
    _save("wiki_rescue_full_pool_pass", "_answer_checked_core", "deadline_hit")
    A.deadline_hit = lambda rid=None: False
    calls = {"n": 0}
    A.wiki_rescue_full_pool_pass = lambda *a, **k: (
        calls.__setitem__("n", calls["n"] + 1) or None)
    seen = {}

    def _core_click(q, focus=None, measure_pick=None, context="", prior=None,
                    trusted=None, resolved=None):
        seen["focus"] = focus
        seen["trusted"] = trusted
        seen["resolved"] = dict(resolved or {})
        seen["measure_pick"] = measure_pick
        pin = A.hold_settled_entity(
            focus, trusted, resolved, found_by=None,
            measure_pick=measure_pick)
        seen["pinned"] = pin
        return {"kind": "answer", "text": "stub", "diag": {},
                "atoms": [], "sources": []}

    A._answer_checked_core = _core_click
    tid_click = A.issue_decision(
        Q1, {"src": SRC_SALES, "label": "sales",
             "rescue_concepts": ["наторговали"]},
        "entity", "v1", user="u-click")
    A.answer_checked(Q1, decision_id=tid_click, user="u-click", channel="lock")
    resolved_click = A.peek_resolved(Q1, "u-click")
    t("click-path-zero-rescue-when-live",
      calls["n"] == 0
      and seen.get("pinned") == SRC_SALES
      and resolved_click.get("src") == SRC_SALES
      and (seen.get("trusted") or {}).get("src") == SRC_SALES,
      "n=%s pinned=%s resolved=%s" % (
          calls["n"], seen.get("pinned"), resolved_click))

    # D1: consume с мерой — число/люк, без повторного rescue
    _reset_session()
    calls["n"] = 0
    seen_m = {}

    def _core_meas(q, focus=None, measure_pick=None, context="", prior=None,
                   trusted=None, resolved=None):
        seen_m["focus"] = focus
        seen_m["measure_pick"] = measure_pick
        seen_m["resolved"] = dict(resolved or {})
        seen_m["trusted"] = trusted
        return {"kind": "answer", "text": "42", "diag": {},
                "atoms": [], "sources": []}

    A._answer_checked_core = _core_meas
    tid_m = A.issue_decision(
        Q1, {"src": SRC_SALES, "measure": "Сумма", "label": "sum",
             "rescue_concepts": ["наторговали"]},
        "measure", "v1", user="u-d1")
    out_m = A.answer_checked(Q1, decision_id=tid_m, user="u-d1", channel="lock")
    resolved_m = A.peek_resolved(Q1, "u-d1")
    t("d1-consume-measure-no-rescue",
      calls["n"] == 0
      and out_m.get("kind") == "answer"
      and seen_m.get("measure_pick") == "Сумма"
      and resolved_m.get("src") == SRC_SALES
      and resolved_m.get("measure") == "Сумма"
      and resolved_m.get("rescue_concepts") == ["наторговали"],
      "n=%s mp=%s resolved=%s" % (
          calls["n"], seen_m.get("measure_pick"), resolved_m))

    _restore()
    _install_deadline(False)
    _install_menu_passthrough()
    _save("wiki_hybrid_pool", "deadline_hit")
    A.deadline_hit = lambda rid=None: False
    hyb = {"n": 0}

    def _hyb(*a, **k):
        hyb["n"] += 1
        return [_card(SRC_OTHER), _card(SRC_FAR)]

    A.wiki_hybrid_pool = _hyb
    diag = {"wiki_full_pool": True}
    out = A.wiki_rescue_full_pool_pass(Q1, {}, diag, None, time.time())
    t("once-only-second-entry-noop",
      out is None and hyb["n"] == 0, "n=%s" % hyb["n"])

    menu = {"kind": "clarify", "options": [
        {"src": SRC_SALES, "label": "a",
         "measure_verdict": "alive",
         "answer_mode": "short_circuit",
         "digest_form": "sum"},
        {"src": SRC_OTHER, "label": "b",
         "measure_verdict": "alive",
         "answer_mode": "short_circuit",
         "digest_form": "sum"}]}
    stamped = A._stamp_rescue_concepts(menu, ["x"], pending=False)
    for o in stamped["options"]:
        t("entity-opt-no-measure-bypass-keys",
          "measure_verdict" not in o
          and "answer_mode" not in o
          and "digest_form" not in o,
          "opt=%s" % o)
    # реальная проводка: после issue_decision(entity) в билете нет bypass-ключей
    _reset_session()
    for o in stamped["options"]:
        tid = A.issue_decision(Q1, o, "entity", "v1", user="u-rg-bypass")
        ticket = A._DECISIONS.get(tid) or {}
        t("entity-opt-no-measure-bypass-keys",
          "measure_verdict" not in ticket
          and "answer_mode" not in ticket
          and "digest_form" not in ticket,
          "ticket keys=%s amb=%s" % (
              list(ticket.keys()), ticket.get("ambiguity")))

    pinned = A.hold_settled_entity(
        SRC_OTHER, trusted={"src": SRC_SALES},
        resolved={"src": SRC_SALES, "measure": "Сумма"},
        measure_pick="Сумма")
    t("hold_settled_entity",
      pinned == SRC_SALES, "pinned=%s" % pinned)
    _restore()


def run_R_H():
    SECTION["cur"] = "R-H"
    _reset_session()
    hybrid = (ROOT / "wiki_card_hybrid.sql").read_text(encoding="utf-8")
    t("sql-rescue-bypasses-axis-filter",
      ":rescue_mode = 1" in hybrid
      and "WHERE :rescue_mode = 1" in hybrid)
    t("sql-norm-damerau-on-tail",
      "damerau_levenshtein" in hybrid
      and "struct_norm" in hybrid
      and ("position('_' IN c.src_table)" in hybrid
           or "position('_' in c.src_table)" in hybrid.lower()))

    vars_ = A._wiki_hybrid_vars(
        "q long enough glue here", {}, rescue_mode=True)
    t("rescue-alias-and-top-plus1",
      vars_["rescue_mode"] == 1
      and vars_["alias_top"] == A.WIKI_RESCUE_ALIAS_N
      and vars_["pick_limit"] == A.WIKI_RESCUE_TOP + 1,
      "vars pick/alias/mode ok")
    t("norm-dist-default-2", vars_["norm_dist"] == 2)

    _install_deadline(False)
    _install_menu_passthrough()
    _save("wiki_hybrid_pool", "wiki_batch_verify", "wiki_pool_resolver",
          "deadline_hit", "psql", "_ensure_embed_secret")
    A.deadline_hit = lambda rid=None: False
    A._ensure_embed_secret = lambda: None
    top = A.WIKI_RESCUE_TOP
    rows = []
    for i in range(top + 1):
        src = "catalog_item_%02d" % i
        rows.append([src, "n%d" % i, "d", "", "", 1, 0.1, "", "", 1])
    calls = {"n": 0, "sqls": []}

    def fake_psql(sql):
        calls["n"] += 1
        calls["sqls"].append(sql)
        if "damerau" in sql.lower():
            return _psql_damerau(sql)
        return rows

    A.psql = fake_psql
    A._wiki_hybrid_sql = lambda: (
        "SELECT src_table, name, description, axes, measures, covered, "
        "distance, parent, platform_prefix, src_layer FROM selected")
    _save("_wiki_hybrid_sql")
    diag = {}
    A.wiki_hybrid_pool(
        "вопрос длинный для склейки нормы", {},
        rescue_mode=True, diag=diag)
    t("diag-rescue_no_axis_filter",
      diag.get("rescue_no_axis_filter") is True, "diag=%s" % diag)
    t("diag-numeric-limits",
      diag.get("wiki_rescue_alias_n") == A.WIKI_RESCUE_ALIAS_N
      and diag.get("wiki_rescue_top") == A.WIKI_RESCUE_TOP,
      "diag=%s" % diag)

    A.wiki_batch_verify = lambda *a, **k: {
        "verdicts_by_src": {}, "passports": [],
        "incomplete": True, "diag": {}}
    A.wiki_pool_resolver = lambda *a, **k: {
        "ok": True, "verdict": "none", "concepts": [], "fail": False}

    def _pool_trunc(*a, **k):
        diag_ref = a[3] if len(a) > 3 else k.get("diag")
        # wiki_rescue_full_pool_pass calls wiki_hybrid_pool(q, intent, rescue_mode=True, diag=diag)
        return [_card("catalog_item_%02d" % i) for i in range(top + 1)]

    A.wiki_hybrid_pool = lambda *a, **k: (
        [_card("catalog_item_%02d" % i) for i in range(top + 1)])
    diag_t = {}
    out_t = A.wiki_rescue_full_pool_pass(
        "q", {}, diag_t, None, time.time())
    t("truncate-final-ceiling",
      diag_t.get("wiki_rescue_truncated", 0) >= 1
      and diag_t.get("wiki_rescue_pre_count") == top + 1
      and diag_t.get("wiki_rescue_pool_n") == top,
      "diag trunc/pre/n")
    t("truncated-none-becomes-menu",
      isinstance(out_t, dict) and out_t.get("kind") == "clarify",
      "out=%s" % out_t)
    vb = _verdicts_map(
        [_card("catalog_item_%02d" % i) for i in range(top)],
        yes_src="catalog_item_00")
    oc = A.wiki_outcome_from_full_verify(
        vb, [_card("catalog_item_%02d" % i) for i in range(top)],
        {}, {}, ceiling_hit=True)
    t("truncated-sole-blocked",
      oc.get("outcome") != "leader", "oc=%s" % oc)
    _restore()


def run_R_I():
    SECTION["cur"] = "R-I"
    _reset_session()
    _install_menu_passthrough()
    _save("wiki_hybrid_pool", "wiki_batch_verify", "wiki_pool_resolver",
          "deadline_hit")
    pool = [_card(SRC_OTHER), _card(SRC_FAR), _card(SRC_SALES)]
    A.wiki_hybrid_pool = lambda *a, **k: list(pool)
    hits = {"n": 0}

    def _dh(rid=None):
        hits["n"] += 1
        return hits["n"] > 1

    A.deadline_hit = _dh
    diag = {}
    out = A.wiki_rescue_full_pool_pass("q", {}, diag, None, time.time())
    t("deadline-after-entry-menu",
      isinstance(out, dict) and out.get("kind") == "clarify"
      and len(out.get("options") or []) >= 2
      and diag.get("wiki_rescue_ri") == "deadline",
      "out=%s ri=%s" % (
          out.get("kind") if isinstance(out, dict) else out,
          diag.get("wiki_rescue_ri")))

    hits["n"] = 0
    A.wiki_hybrid_pool = lambda *a, **k: [_card(SRC_OTHER)]
    diag1 = {}
    out1 = A.wiki_rescue_full_pool_pass("q", {}, diag1, None, time.time())
    t("deadline-pool1-prev-or-rd",
      out1 is None
      or (isinstance(out1, dict) and out1.get("kind") == "no_data"),
      "out=%s" % out1)

    _restore()
    _install_deadline(False)
    _install_menu_passthrough()
    _save("wiki_entity_clarify_menu", "deadline_hit",
          "wiki_hybrid_pool", "wiki_batch_verify", "wiki_pool_resolver")
    A.deadline_hit = lambda rid=None: False
    A.wiki_hybrid_pool = lambda *a, **k: list(pool)
    A.wiki_batch_verify = lambda *a, **k: {
        "verdicts_by_src": _verdicts_map(pool),
        "passports": pool, "incomplete": False, "diag": {}}
    A.wiki_pool_resolver = lambda *a, **k: {
        "ok": True, "verdict": "many", "concepts": [], "fail": False}
    A.wiki_entity_clarify_menu = lambda *a, **k: None
    diag_m = {}
    out_m = A.wiki_rescue_full_pool_pass("q", {}, diag_m, None, time.time())
    t("menu-none-degrade-rebuild",
      isinstance(out_m, dict) and out_m.get("kind") == "clarify"
      and diag_m.get("wiki_rescue_menu_degraded") is True,
      "out=%s deg=%s" % (
          out_m.get("kind") if isinstance(out_m, dict) else out_m,
          diag_m.get("wiki_rescue_menu_degraded")))

    src = inspect.getsource(A.wiki_rescue_full_pool_pass)
    t("no-503-from-pass",
      "503" not in src and "AskDeadline" not in src)
    _restore()


def run_R_J():
    SECTION["cur"] = "R-J"
    _reset_session()
    import urllib.request as ur
    _save("deadline_hit", "_deadline_remaining_sec")
    A.deadline_hit = lambda rid=None: False
    A._deadline_remaining_sec = lambda: 5.0
    _save_urlopen = ur.urlopen

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps({
                "choices": [{"message": {"content":
                    json.dumps({"verdict": "one", "concepts": ["x"]})}}]
            }).encode()

    ur.urlopen = lambda *a, **k: _Resp()
    try:
        diag = {}
        cards = [_card(SRC_OTHER, "A"), _card(SRC_FAR, "B")]
        r = A.wiki_pool_resolver("q", cards, diag)
        blob = (json.dumps(r, ensure_ascii=False)
                + json.dumps(diag, ensure_ascii=False))
        t("resolver-no-star",
          "\u2605" not in blob and r.get("ok"), "r=%s" % r)
        t("resolver-no-leader-field",
          "leader" not in r and "picked" not in r)
        t("resolver-cards-untouched",
          cards[0]["src_table"] == SRC_OTHER)
    finally:
        ur.urlopen = _save_urlopen

    class _R2:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps({
                "choices": [{"message": {"content": "1"}}]}).encode()

    opts = [{"label": "один", "hint": "", "src": "a"},
            {"label": "два", "hint": "", "src": "b"}]
    ur.urlopen = lambda *a, **k: _R2()
    try:
        A.deadline_hit = lambda rid=None: False
        A._deadline_remaining_sec = lambda: 5.0
        diag_h = {}
        A.llm_option_highlight("q", opts, diag_h)
        stars = sum(1 for o in opts if "\u2605" in (o.get("hint") or ""))
        t("highlight-star-one", stars == 1, "opts=%s" % opts)
    finally:
        ur.urlopen = _save_urlopen
    _restore()


def run_R_K():
    SECTION["cur"] = "R-K"
    _reset_session()
    _install_deadline(False)
    _install_menu_passthrough()
    _install_psql_basic(tables={
        SRC_OTHER: "other", SRC_FAR: "far", SRC_SALES: "sales",
        "a_1": "A", "a_2": "B", "a_3": "C",
    })

    pool = [_card(SRC_OTHER, "other"), _card(SRC_FAR, "far"),
            _card(SRC_SALES, "sales")]
    # смесь: ≥2 found>0 + ≥1 found=0; wiki_rescue держит мёртвых в opts
    by = {SRC_OTHER: 4, SRC_FAR: 2, SRC_SALES: 0}
    diag = {"wiki_full_pool": True}
    menu = A.wiki_entity_clarify_menu(
        "q", pool, diag, None, time.time(),
        by=by, reason="wiki_rescue")
    t("wiki_rescue-opts-eq-pool",
      isinstance(menu, dict)
      and len(menu.get("options") or []) == len(pool)
      and {o.get("src") for o in (menu.get("options") or [])}
      == {c["src_table"] for c in pool},
      "opts=%s pool=%s" % (
          len((menu or {}).get("options") or []), len(pool)))

    tie = [_card("a_1", "A"), _card("a_2", "B")]
    full = tie + [_card("a_3", "C")]
    diag_s = {"wiki_full_pool": True}
    menu_s = A.wiki_entity_clarify_menu(
        "q", tie, diag_s, None, time.time(),
        by={s: 1 for s in ("a_1", "a_2", "a_3")},
        reason="wiki_separability")
    t("separability-opts-eq-tie-not-full",
      isinstance(menu_s, dict)
      and len(menu_s.get("options") or []) == len(tie)
      and len(menu_s.get("options") or []) < len(full),
      "opts=%s" % len((menu_s or {}).get("options") or []))

    _save("wiki_hybrid_pool", "wiki_batch_verify", "wiki_pool_resolver",
          "deadline_hit")
    A.deadline_hit = lambda rid=None: False
    A.wiki_hybrid_pool = lambda *a, **k: list(full)
    A.wiki_batch_verify = lambda *a, **k: {
        "verdicts_by_src": {
            "a_1": _verdict("a_1", "yes"),
            "a_2": _verdict("a_2", "unsure"),
            "a_3": _verdict("a_3", "no"),
        },
        "passports": full, "incomplete": False, "diag": {}}
    A.wiki_pool_resolver = lambda *a, **k: {
        "ok": True, "verdict": "many", "concepts": [], "fail": False}
    diag_p = {}
    out = A.wiki_rescue_full_pool_pass("q", {}, diag_p, None, time.time())
    if isinstance(out, dict) and out.get("kind") == "clarify":
        n_opts = len(out.get("options") or [])
        why = out.get("why") or (out.get("diag") or {}).get("reason") or ""
        t("pass-separability-tie-eq-2",
          n_opts == 2 and why == "wiki_separability",
          "n=%s why=%s" % (n_opts, why))
    else:
        t("pass-separability-tie-eq-2", False, "out=%s" % out)
    _restore()


def run_PERF_gate_context():
    """PERF6: гейт дедлайна в воркерах видит rid через copy_context.

    Без мока deadline_hit — реальный _rid_ctx / _REQ_T0. На коде без
    copy_context().run сценарий падает (воркер слеп к rid → ds_chat > 0).
    """
    SECTION["cur"] = "PERF"
    _reset_session()
    _restore()  # живой deadline_hit, не _install_deadline
    _save("wiki_passport_enrich_slice", "ds_chat", "WIKI_VERIFY_WORKERS",
          "wiki_format_passport_lines")
    A.WIKI_VERIFY_WORKERS = 4
    A.wiki_passport_enrich_slice = (
        lambda cards, cache=None, distinct_against=None, **kw: [
            dict(c) for c in (cards or [])])
    A.wiki_format_passport_lines = lambda cards: "P"

    calls = {"n": 0}

    def _ds(messages, max_tokens=0):
        calls["n"] += 1
        return '{"fit":"yes","why":"ok"}'

    A.ds_chat = _ds
    pool = [_card("catalog_gate_%02d" % i, "g%d" % i) for i in range(6)]

    rid = A._rid_enter()
    try:
        A._REQ_T0[rid] = time.monotonic() - float(A.ASK_DEADLINE_SEC) - 5.0
        t("gate-context-main-hit",
          A.deadline_hit() is True and A._rid_get() == rid,
          "rid=%s hit=%s" % (A._rid_get(), A.deadline_hit()))
        batch = A.wiki_batch_verify(
            "сколько клиентов", {"kind": "catalog", "want": "count"},
            pool, diag={})
        d = batch.get("diag") or {}
        t("gate-context-blind",
          calls["n"] == 0
          and batch.get("incomplete") is True
          and d.get("wiki_card_verify_deadline") is True
          and d.get("wiki_batch_verify_deadline") is True
          and int(d.get("wiki_batch_verify_n", -1)) == 0
          and len(batch.get("verdicts_by_src") or {}) == 0,
          "ds=%s inc=%s d=%s vb=%s" % (
              calls["n"], batch.get("incomplete"), {
                  k: d.get(k) for k in (
                      "wiki_card_verify_deadline",
                      "wiki_batch_verify_deadline",
                      "wiki_batch_verify_n")},
              len(batch.get("verdicts_by_src") or {})))
    finally:
        A._req_t0_clear(rid)
        try:
            A._rid_ctx.set("")
        except Exception:  # noqa: BLE001
            pass
    _restore()


def main():
    runners = [
        ("R-A", run_R_A),
        ("R-B", run_R_B),
        ("R-C", run_R_C),
        ("R-D", run_R_D),
        ("R-E", run_R_E),
        ("R-F", run_R_F),
        ("R-G", run_R_G),
        ("R-H", run_R_H),
        ("R-I", run_R_I),
        ("R-J", run_R_J),
        ("R-K", run_R_K),
        ("PERF", run_PERF_gate_context),
    ]
    per = {}
    for name, fn in runners:
        before_p, before_f = PASS, len(FAIL)
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            SECTION["cur"] = name
            t("EXCEPTION", False, "%s: %s" % (type(e).__name__, e))
        finally:
            _restore()
            _reset_session()
        ok_n = PASS - before_p
        fail_n = len(FAIL) - before_f
        per[name] = (ok_n, fail_n)

    print("---")
    for name, (ok_n, fail_n) in per.items():
        print("%s: %d ok / %d fail" % (name, ok_n, fail_n))
    print("TOTAL: %d ok / %d fail" % (PASS, len(FAIL)))
    if FAIL:
        print("FAILED:")
        for f in FAIL:
            print(" ", f)
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())
