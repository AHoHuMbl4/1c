#!/usr/bin/env python3
"""Оффлайн-замок Б3-у: контекстная верификация кандидатов (wiki_passport + z21).

Без сети и живой базы. Мок ds_chat. Проверяет: паспорт (wiki/оси/меры/отличия),
исходы verify (один yes → leader; два+ yes/unsure → clarify; ноль yes → none),
лимит ≤8 паспортов, отсутствие слов домена.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PASSPORT = ROOT / "wiki_passport.sql"
Z21 = ROOT / "ask" / "z21_wiki_choice.py"

PASS, FAIL = 0, []

FORBIDDEN_ENTITY = re.compile(
    r"(?i)(accumulationregister_|catalog_)(?:остат|номенклат|контрагент|реализац|"
    r"склад|продаж|клиент|товар|warehouse|nomenclature|counterpart)",
)
# Границы [a-z0-9_]: слово домена внутри snake_case-идентификатора (ссылка на
# общий резолвер оси) — не доменный литерал; ловим термины-тексты, не имена.
DOMAIN_LITERAL = re.compile(
    r"(?i)['\"][^'\"]{0,200}(?<![a-zа-яё0-9_])(?:остат|склад|warehouse|позиц|"
    r"номенклат|товар|контрагент|клиент|продаж|sale|revenue)(?![a-zа-яё0-9_])"
    r"[^'\"]{0,200}['\"]",
)


def t(name: str, cond: bool, detail: str = "") -> None:
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + str(detail)[:240]) if detail else "")


def strip_sql_comments(text: str) -> str:
    return re.sub(r"--[^\n]*", "", text)


def load_z21():
    import types

    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    import ask._imports as real_imp

    fake = types.ModuleType("ask._wire")
    fake.register_zone = lambda *a, **k: None
    fake.apply_bindings = lambda g: None
    sys.modules["ask._wire"] = fake
    sys.modules["ask._imports"] = real_imp
    src = Z21.read_text(encoding="utf-8")
    ns = {
        "__name__": "z21_wiki_choice",
        "__file__": str(Z21),
        "rank_intent_from": lambda *a, **k: False,
        "_intent_text": lambda x: (x[0] if isinstance(x, (list, tuple)) and x else x or "") or "",
        "kind_word": lambda s: "справочник" if str(s).startswith("catalog_") else "регистр",
        "intent_axis_words": lambda intent: [],
        "ds_chat": lambda *a, **k: "{}",
        "lit": lambda s: "'%s'" % str(s).replace("'", "''"),
        "psql": lambda q: [],
        "_ensure_embed_secret": lambda: None,
        "EMBED_MODEL": "m",
        "EMBED_SECRET_NAME": "sec",
        "EMBED_DIM": 1024,
        "STEM_DICT": "russian",
        "TABLES": "search_tables",
        "NO_DATA_TEXT": "",
        "refuse_text": lambda q: "refuse",
        "question_expects_accounting_data": lambda intent, q, diag=None: True,
        "clarify_say": lambda *a, **k: "clarify?",
        "mk_opts": lambda srcs, lab_by, *a, **k: [
            {"label": lab_by.get(s, s), "src": s} for s in srcs],
        "_diag_pack": lambda d, **k: d,
        "register_zone": lambda *a, **k: None,
        "apply_bindings": lambda g: None,
    }
    for k, v in vars(real_imp).items():
        if k.startswith("_") and k not in ("__builtins__",):
            continue
        ns.setdefault(k, v)
    exec(compile(src, str(Z21), "exec"), ns)
    return ns


def _cards(n=3):
    return [
        {"src_table": "catalog_a", "name": "Alpha", "description": "d1",
         "axes": "col1 -> catalog_x, col2 -> catalog_y",
         "measures": "m1: alias1; m2: alias2",
         "distance": 0.1, "platform_kind": "справочник", "parent": ""},
        {"src_table": "catalog_b", "name": "Beta", "description": "d2",
         "axes": "col1 -> catalog_x, col3 -> catalog_z",
         "measures": "m1: alias1; m3: alias3",
         "distance": 0.2, "platform_kind": "справочник", "parent": ""},
        {"src_table": "document_c", "name": "Gamma", "description": "d3",
         "axes": "col4 -> catalog_q",
         "measures": "m4: alias4",
         "distance": 0.3, "platform_kind": "документ", "parent": ""},
    ][:n]


def main() -> int:
    passport = PASSPORT.read_text(encoding="utf-8")
    z21_src = Z21.read_text(encoding="utf-8")
    # Новый код верификации (без легаси-docstring stock_canon ниже по файлу).
    vmark = "WIKI_VERIFY_SYS"
    vend = "def wiki_knn_separable"
    i0 = z21_src.find(vmark)
    i1 = z21_src.find(vend, i0 if i0 >= 0 else 0)
    verify_slice = z21_src[i0:i1] if i0 >= 0 and i1 > i0 else ""
    combined = strip_sql_comments(passport) + strip_sql_comments(verify_slice)

    t("wiki_passport.sql exists", PASSPORT.is_file())
    t("uses wiki_pages", "wiki_pages" in passport)
    t("uses search_wiki_entity_card", "search_wiki_entity_card" in passport)
    t("body_max param", ":body_max" in passport)
    t("src_list param", ":src_list" in passport)
    t("join search_tables parent", "search_tables" in passport)

    t("okna_entity_hardcode_scan", FORBIDDEN_ENTITY.search(combined) is None)
    t("domain_routing_literal_scan", DOMAIN_LITERAL.search(combined) is None)

    z21 = load_z21()
    t("WIKI_VERIFY_SYS exists", "WIKI_VERIFY_SYS" in z21)
    t("wiki_verify_candidates exists", callable(z21.get("wiki_verify_candidates")))
    t("wiki_passport_enrich exists", callable(z21.get("wiki_passport_enrich")))
    t("wiki_outcome_from_verify exists", callable(z21.get("wiki_outcome_from_verify")))
    # [01.09, ночь] 8 = WIKI_PICK_N: каждая карточка выбора верифицируема
    # (при 5 верная карточка №6 пула уходила в no_data при живом эталоне).
    t("WIKI_PASSPORT_N default 8 == WIKI_PICK_N",
      z21["WIKI_PASSPORT_N"] == 8 and z21["WIKI_PASSPORT_N"] == z21["WIKI_PICK_N"])

    cards = _cards(2)
    d0 = z21["wiki_passport_distinct"](cards[0], cards)
    t("distinct has col2 not in beta", "col2" in d0 or "axes:" in d0, d0)
    t("distinct has m2", "m2" in d0 or "measures:" in d0, d0)

    z21["psql"] = lambda q: [
        ("catalog_a", "Alpha", "wiki body alpha long text", cards[0]["axes"],
         cards[0]["measures"], "", "catalog"),
    ]
    enriched = z21["wiki_passport_enrich"](cards)
    t("enrich wiki_body from sql", "wiki body" in (enriched[0].get("wiki_body") or ""))
    t("enrich distinct field", enriched[0].get("distinct"))

    lines = z21["wiki_format_passport_lines"](enriched[:1])
    t("passport form has wiki distinct",
      all(x in lines for x in ("wiki:", "distinct:", "platform:", "measures:")))

    many = _cards(3) + [
        {"src_table": "catalog_d", "name": "Delta", "description": "",
         "axes": "", "measures": "", "distance": 0.4, "platform_kind": "справочник"},
        {"src_table": "catalog_e", "name": "Epsilon", "description": "",
         "axes": "", "measures": "", "distance": 0.5, "platform_kind": "справочник"},
        {"src_table": "catalog_f", "name": "Zeta", "description": "",
         "axes": "", "measures": "", "distance": 0.6, "platform_kind": "справочник"},
    ] + [
        {"src_table": "catalog_%d" % i, "name": "N%d" % i, "description": "",
         "axes": "", "measures": "", "distance": 0.7, "platform_kind": "справочник"}
        for i in range(7, 11)
    ]
    fmt9 = z21["wiki_format_passport_lines"](many[:9], short_tail=many[9:])
    t("passport cap 8 full + tail names", fmt9.count("passport\n") == 8)
    t("short tail names only", "Other pool names only:" in fmt9)

    v_one, m_one = z21["wiki_parse_verify_response"](
        json.dumps({"verdicts": [
            {"index": 1, "fit": "yes", "why": "matches axis"},
            {"index": 2, "fit": "no", "why": "wrong kind"},
        ]}), 2)
    t("parse two verdicts", len(v_one) == 2 and v_one[0]["fit"] == "yes")
    t("parse full mode", m_one == "full")

    out_one = z21["wiki_outcome_from_verify"](v_one, _cards(2), {}, {})
    t("one yes → leader", out_one.get("outcome") == "leader"
      and out_one.get("leader") == "catalog_a")

    v_two, m_two = z21["wiki_parse_verify_response"](
        json.dumps({"verdicts": [
            {"index": 1, "fit": "yes", "why": "a"},
            {"index": 2, "fit": "yes", "why": "b"},
        ]}), 2)
    out_two = z21["wiki_outcome_from_verify"](v_two, _cards(2), {}, {})
    t("two yes → clarify", out_two.get("outcome") == "clarify"
      and len(out_two.get("candidates") or []) == 2)

    v_zero, m_zero = z21["wiki_parse_verify_response"](
        json.dumps({"verdicts": [
            {"index": 1, "fit": "no", "why": "nope"},
            {"index": 2, "fit": "no", "why": "nope2"},
        ]}), 2)
    out_zero = z21["wiki_outcome_from_verify"](v_zero, _cards(2), {}, {})
    t("zero yes → none", out_zero.get("outcome") == "none")

    v_unsure, m_unsure = z21["wiki_parse_verify_response"](
        json.dumps({"verdicts": [
            {"index": 1, "fit": "yes", "why": "maybe a"},
            {"index": 2, "fit": "unsure", "why": "unclear"},
        ]}), 2)
    out_unsure = z21["wiki_outcome_from_verify"](v_unsure, _cards(2), {}, {})
    t("yes+unsure → clarify", out_unsure.get("outcome") == "clarify")

    v_ru, m_ru = z21["wiki_parse_verify_response"](
        json.dumps({"verdicts": [{"index": 1, "fit": "подходит", "why": "x"}]}), 1)
    t("parse russian fit подходит", v_ru and v_ru[0]["fit"] == "yes")

    # [02.09, решение владельца] одиночная карточка — тот же путь verify, без struct_single
    single = _cards(1)
    z21["psql"] = lambda q: [
        ("catalog_a", "Alpha", "wiki body", single[0]["axes"],
         single[0]["measures"], "", "catalog"),
    ]
    z21["ds_chat"] = lambda *a, **k: json.dumps({"verdicts": [
        {"index": 1, "fit": "yes", "why": "ok"},
    ]})
    z21["wiki_validate_leader_axes"] = lambda *a, **k: True
    out_single_yes = z21["wiki_verify_candidates"]("q", {}, single, {})
    t("single pool verify yes → leader",
      out_single_yes.get("outcome") == "leader"
      and out_single_yes.get("leader") == "catalog_a"
      and not out_single_yes.get("diag", {}).get("wiki_verify_skipped"))
    z21["ds_chat"] = lambda *a, **k: json.dumps({"verdicts": [
        {"index": 1, "fit": "no", "why": "nope"},
    ]})
    out_single_no = z21["wiki_verify_candidates"]("q", {}, single, {})
    t("single pool verify no → none", out_single_no.get("outcome") == "none")

    z21["psql"] = lambda q: []
    z21["ds_chat"] = lambda *a, **k: json.dumps({"verdicts": [
        {"index": 1, "fit": "yes", "why": "ok"},
        {"index": 2, "fit": "no", "why": "no"},
    ]})
    z21["wiki_validate_leader_axes"] = lambda *a, **k: True
    vfy = z21["wiki_verify_candidates"]("q", {}, _cards(2), {})
    t("mock one yes picked", vfy.get("outcome") == "leader"
      and vfy.get("leader") == "catalog_a")

    z21["ds_chat"] = lambda *a, **k: json.dumps({"verdicts": [
        {"index": 1, "fit": "no", "why": "n"},
        {"index": 2, "fit": "no", "why": "n"},
    ]})
    vfy0 = z21["wiki_verify_candidates"]("q", {}, _cards(2), {})
    t("mock zero yes none", vfy0.get("outcome") == "none")

    z21["ds_chat"] = lambda *a, **k: json.dumps({"verdicts": [
        {"index": 1, "fit": "yes", "why": "a"},
        {"index": 2, "fit": "yes", "why": "b"},
    ]})
    vfy2 = z21["wiki_verify_candidates"]("q", {}, _cards(2), {})
    t("mock two yes clarify", vfy2.get("outcome") == "clarify")

    # интеграция try_wiki: verify перекрывает pick-none
    z21["wiki_hybrid_pool"] = lambda q, intent=None: _cards(2)
    pick_calls = []
    verify_payload = []

    def _pick(q, intent, cards, diag=None):
        pick_calls.append(1)
        return {"outcome": "none", "reason": "model_none", "diag": diag or {}}

    def _ds_verify(*a, **k):
        verify_payload.append(a)
        return json.dumps({"verdicts": [{"index": 1, "fit": "yes", "why": "v"}]})

    z21["wiki_pick_from_cards"] = _pick
    z21["ds_chat"] = _ds_verify
    z21["psql"] = lambda q: (
        [("catalog_a", "Alpha", "wiki", "", "", "", "catalog")]
        if "wiki_passport" in str(q) or "wiki_pages" in str(q)
        else [("x",)])
    diag_i = {}
    res = z21["try_wiki_hybrid_entity_pick"]("q", {}, diag_i, None, 0, by={})
    t("try_wiki verify overrides pick none",
      res and res.get("picked") == ["catalog_a"] and pick_calls)
    t("try_wiki diag wiki_verify", diag_i.get("wiki_verify_yes") == 1)

    # clarify с options ≥2
    z21["ds_chat"] = lambda *a, **k: json.dumps({"verdicts": [
        {"index": 1, "fit": "yes", "why": "a"},
        {"index": 2, "fit": "unsure", "why": "b"},
    ]})
    z21["psql"] = lambda q: (
        [("catalog_a", "Alpha", "w", "", "", "", "catalog"),
         ("catalog_b", "Beta", "w", "", "", "", "catalog")]
        if "wiki_pages" in str(q)
        else [("catalog_a", "Alpha"), ("catalog_b", "Beta")]
        if "search_tables" in str(q)
        else [("x",)])
    diag_cl = {}
    res_cl = z21["try_wiki_hybrid_entity_pick"](
        "q", {}, diag_cl, None, 0, by={}, match="", preds=[])
    t("try_wiki clarify options",
      res_cl and res_cl.get("kind") == "clarify"
      and len(res_cl.get("options") or []) >= 2)


    # [02.09] обрезанный JSON: salvage завершённых verdicts
    trunc_raw = (
        '{"verdicts": ['
        '{"index": 1, "fit": "yes", "why": "ok"}, '
        '{"index": 2, "fit": "no", "why": "long text cut mid'
    )
    v_trunc, m_trunc = z21["wiki_parse_verify_response"](trunc_raw, 3)
    t("truncated json salvage one verdict",
      len(v_trunc) == 1 and v_trunc[0]["index"] == 1 and v_trunc[0]["fit"] == "yes")
    t("truncated json salvage mode", m_trunc == "salvage")

    v_garbage, m_garbage = z21["wiki_parse_verify_response"]("not json at all", 2)
    t("garbage parse empty", v_garbage == [] and m_garbage == "failed")

    v_bracket, m_bracket = z21["wiki_parse_verify_response"]("[", 2)
    t("lone bracket parse empty", v_bracket == [] and m_bracket == "failed")

    v_empty, m_empty = z21["wiki_parse_verify_response"]("", 2)
    t("empty raw parse empty", v_empty == [] and m_empty == "failed")

    z21["psql"] = lambda q: []
    z21["wiki_validate_leader_axes"] = lambda *a, **k: True
    z21["ds_chat"] = lambda *a, **k: "not json at all"
    vfy_garbage = z21["wiki_verify_candidates"]("q", {}, _cards(2), {})
    t("garbage verify → degraded not none",
      vfy_garbage.get("outcome") == "degraded")

    z21["ds_chat"] = lambda *a, **k: json.dumps({"verdicts": []})
    vfy_empty_ok = z21["wiki_verify_candidates"]("q", {}, _cards(2), {})
    t("valid empty verdicts → none not degraded",
      vfy_empty_ok.get("outcome") == "none")

    t("WIKI_VERIFY_MAX_TOKENS default 2048",
      z21.get("WIKI_VERIFY_MAX_TOKENS") == 2048)

    t("try_wiki integrates verify step",
      "wiki_verify_candidates" in Z21.read_text(encoding="utf-8"))

    # [02.09] post-verify: меры (все alts) + квалификатор action_axis
    t("post-verify helpers exist",
      all(callable(z21.get(n)) for n in (
          "wiki_intent_named_measures", "wiki_leader_post_verify",
          "wiki_axis_is_question_subject", "wiki_leader_carries_axis")))
    t("intent measures list collects alts",
      z21["wiki_intent_named_measures"](
          {"measure": ["alpha", "beta"]}) == ["alpha", "beta"])
    t("axis subject when kind equals axis",
      z21["wiki_axis_is_question_subject"](
          {"kind": "axis_k", "action_axis": "axis_k"}, "axis_k"))
    t("axis qualifier when kind differs",
      not z21["wiki_axis_is_question_subject"](
          {"kind": "entity_k", "action_axis": "axis_k"}, "axis_k"))

    _axis_cats = {"axis_k": ["catalog_axis"]}
    z21["entity_form_catalogs_for_kind"] = (
        lambda word, allow_meaning=True: _axis_cats.get(word) or [])
    z21["_wiki_axis_has_carriers"] = lambda phrase, intent, question="": (
        phrase == "axis_k")
    z21["wiki_measure_carried"] = lambda src, m: (
        m != "beta" or src == "catalog_carrier")

    def _psql_measures(q):
        qs = str(q)
        if "search_measure_alias" in qs:
            if "beta" in qs:
                return [(2, 0 if "catalog_nom" in qs else 1)]
            return [(0, 0)]
        if "search_refcols" in qs:
            if "catalog_nom" in qs:
                return []
            if "catalog_carrier" in qs:
                return [(1,)]
            return []
        if "search_wiki_entity_card" in qs:
            return [("x",)]
        return [("x",)]

    _real_wmc = z21["wiki_measure_carried"]
    z21["psql"] = _psql_measures
    z21["wiki_hybrid_pool"] = lambda q, intent=None: _cards(1)
    z21["wiki_validate_leader_axes"] = lambda *a, **k: True
    z21["ds_chat"] = lambda *a, **k: json.dumps({"verdicts": [
        {"index": 1, "fit": "yes", "why": "ok"},
    ]})

    diag_axis = {}
    res_axis = z21["try_wiki_hybrid_entity_pick"](
        "q", {"kind": "entity_k", "action_axis": "axis_k",
              "want": "count"}, diag_axis, None, 0)
    t("leader without qualifier axis → none",
      res_axis is None and diag_axis.get("wiki_none") == "axis_not_carried")

    diag_subj = {}
    res_subj = z21["try_wiki_hybrid_entity_pick"](
        "q", {"kind": "axis_k", "action_axis": "axis_k",
              "want": "count"}, diag_subj, None, 0)
    t("leader axis-catalog when axis is subject → leader",
      res_subj and res_subj.get("picked") == ["catalog_a"])

    z21["wiki_hybrid_pool"] = lambda q, intent=None: [
        {"src_table": "catalog_nom", "name": "N", "description": "",
         "axes": "", "measures": "", "distance": 0.1,
         "platform_kind": "справочник", "parent": ""}]
    diag_meas = {}
    res_meas = z21["try_wiki_hybrid_entity_pick"](
        "q", {"measure": ["alpha", "beta"], "want": "count"},
        diag_meas, None, 0)
    t("second known measure not carried → none",
      res_meas is None and diag_meas.get("wiki_none") == "measure_not_carried")

    z21["wiki_measure_carried"] = _real_wmc
    z21["psql"] = lambda q: (_ for _ in ()).throw(RuntimeError("db"))
    t("measure metadata error does not drop leader",
      z21["wiki_leader_post_verify"]("catalog_a", {"measure": "alpha"}, "q", {}))

    # [02.09] post-verify: ось из resolved_warehouse_axis_word при пустом action_axis
    z21["wiki_measure_carried"] = lambda src, m: True
    z21["_wiki_axis_has_carriers"] = lambda phrase, intent, question="": True
    z21["wiki_leader_carries_axis"] = (
        lambda leader, axis_word, intent=None, question="": leader != "catalog_nom")
    z21["resolved_warehouse_axis_word"] = (
        lambda question, intent=None: "axis_place")

    diag_rw = {}
    ok_rw = z21["wiki_leader_post_verify"](
        "catalog_nom",
        {"kind": "entity_k", "action_axis": ""},
        "q with place axis",
        diag_rw)
    t("empty action_axis + place resolver → none when leader lacks axis",
      (not ok_rw) and diag_rw.get("wiki_none") == "axis_not_carried"
      and diag_rw.get("wiki_axis_not_carried") == "catalog_nom")

    diag_rw_subj = {}
    ok_rw_subj = z21["wiki_leader_post_verify"](
        "catalog_nom",
        {"kind": "axis_place", "action_axis": ""},
        "q with place axis",
        diag_rw_subj)
    t("empty action_axis + place resolver as subject → keep leader",
      ok_rw_subj and not diag_rw_subj.get("wiki_none"))

    z21["resolved_warehouse_axis_word"] = lambda question, intent=None: ""
    diag_rw_empty = {}
    ok_rw_empty = z21["wiki_leader_post_verify"](
        "catalog_nom",
        {"kind": "entity_k", "action_axis": ""},
        "q no place",
        diag_rw_empty)
    t("empty action_axis + empty resolver → keep leader (unchanged)",
      ok_rw_empty and not diag_rw_empty.get("wiki_none"))

    # [02.09] collapse: пустая мера + sales-вид → money-канон, не count
    _sales_q = "позавчера сколько было продаж"
    _sales_intent = {"kind": "продажи", "measure": "", "want": "count"}
    z21["sales_sum_intent"] = lambda intent, question="": True
    z21["sales_rank_engaged"] = lambda *a, **k: False
    z21["sales_force_money_measure"] = lambda intent, question="": True
    z21["sales_money_measure"] = lambda names, alias_by=None: "Всего"
    z21["measures_of"] = lambda src: ["Всего", "Количество"]
    z21["measure_aliases_of"] = lambda src: {}
    z21["pick_measure"] = lambda src, question, word: (None, [], "none")
    z21["unresolved_quantity"] = lambda m, alts, want, compute, names, totals=None: (m, list(alts or []))

    def _agg_sales(src, match, preds, measure):
        if measure:
            return {"sum": 0.0, "count": 9, "form": "money", "grain": "row"}
        return {"sum": None, "count": 9, "form": "number", "grain": "row"}

    z21["aggregate"] = _agg_sales
    z21["answer_slot_mode"] = lambda want, compute: "count"
    z21["atom_operation"] = lambda *a, **k: "sum"
    z21["measure_label_of"] = lambda src, m: m or "count"
    z21["atom_from_agg"] = lambda agg, **k: {
        "exact_value": agg.get("sum") if k.get("money") else agg.get("count"),
        "operation": k.get("operation"), "measure_id": k.get("measure_id")}
    z21["_passport_origin"] = lambda intent, diag: None
    z21["split_ident"] = lambda s: s
    z21["render_atom_pair"] = lambda atom: str(atom.get("exact_value"))
    z21["_fmt"] = lambda v: str(v)
    z21["_fork_figures_of"] = lambda atom: [atom.get("exact_value")]

    diag_collapse = {}
    tied_sales = ["accumulationregister_a", "accumulationregister_b"]
    collapsed = z21["_wiki_clarify_collapse_answer"](
        _sales_q, _sales_intent, tied_sales, "", [], diag_collapse, None, 0, {})
    t("collapse sales empty measure uses money canon not count",
      collapsed and collapsed.get("kind") == "answer"
      and collapsed.get("text") == "0.0"
      and diag_collapse.get("wiki_clarify_collapsed") == "equal"
      and diag_collapse.get("wiki_clarify_collapsed_measure") == "Всего")

    # count-only: без sales-канона свёртка считает записи
    z21["sales_sum_intent"] = lambda intent, question="": False
    diag_count = {}
    collapsed_count = z21["_wiki_clarify_collapse_answer"](
        "сколько записей", {"want": "count"}, tied_sales, "", [], diag_count, None, 0, {})
    t("collapse non-sales count intent stays count",
      collapsed_count and collapsed_count.get("text") == "9"
      and diag_count.get("wiki_clarify_collapsed_measure") == "count")

    r = subprocess.run([sys.executable, "-m", "py_compile", str(Z21)],
                       capture_output=True, text=True)
    t("z21 py_compile", r.returncode == 0, r.stderr[:120])

    print("---", PASS, "ok,", len(FAIL), "fail")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
