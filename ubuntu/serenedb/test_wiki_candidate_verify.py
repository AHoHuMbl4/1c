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
        "wiki_menu_captions": lambda opts, **k: opts,
        "wiki_captions_map_from_cards": lambda cards: {},
        "human_table_label": lambda src, label=None: (
            (label or "").strip() or (
                str(src).split("_", 1)[1] if "_" in str(src) else str(src))),
        "readings_menu": lambda question, kind, items, diag, cut, t0, *, reason="": (
            {"kind": "clarify", "options": list(items or []), "text": reason or "?",
             "diag": dict(diag or {}), "partial": cut}
            if len(list(items or [])) >= 2 else None),
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
    t("mock one yes confirm agree",
      (vfy.get("diag") or {}).get("wiki_verify_confirm") == "agree")

    # I0-П2b: согласие sole-yes (второй вызов)
    _calls = []

    def _ds_seq(*a, **k):
        _calls.append(1)
        seq = getattr(_ds_seq, "seq")
        i = min(len(_calls) - 1, len(seq) - 1)
        item = seq[i]
        if isinstance(item, Exception):
            raise item
        return item

    z21["psql"] = lambda q: []
    z21["wiki_validate_leader_axes"] = lambda *a, **k: True

    _calls.clear()
    _ds_seq.seq = [
        json.dumps({"verdicts": [
            {"index": 1, "fit": "yes", "why": "a"},
            {"index": 2, "fit": "no", "why": "n"},
        ]}),
        json.dumps({"verdicts": [
            {"index": 1, "fit": "yes", "why": "a2"},
            {"index": 2, "fit": "no", "why": "n2"},
        ]}),
    ]
    z21["ds_chat"] = _ds_seq
    v_agree = z21["wiki_verify_candidates"]("q", {}, _cards(2), {})
    t("P2b agree: second sole-yes → leader",
      v_agree.get("outcome") == "leader"
      and v_agree.get("leader") == "catalog_a"
      and (v_agree.get("diag") or {}).get("wiki_verify_confirm") == "agree"
      and len(_calls) == 2
      and (v_agree.get("diag") or {}).get("wiki_verify_yes") == 1
      and (v_agree.get("diag") or {}).get("wiki_verify2_yes") == 1)

    # I0-П2b-фикс: salvage второго ответа (обрезан после лидера) ≠ agree
    _calls.clear()
    trunc2 = (
        '{"verdicts": ['
        '{"index": 1, "fit": "yes", "why": "ok"}, '
        '{"index": 2, "fit": "no", "why": "cut mid'
    )
    _ds_seq.seq = [
        json.dumps({"verdicts": [
            {"index": 1, "fit": "yes", "why": "a"},
            {"index": 2, "fit": "no", "why": "n"},
        ]}),
        trunc2,
    ]
    z21["ds_chat"] = _ds_seq
    v_trunc2 = z21["wiki_verify_candidates"]("q", {}, _cards(2), {})
    d_trunc2 = v_trunc2.get("diag") or {}
    t("P2b fix salvage2 after leader ≠ agree",
      v_trunc2.get("outcome") != "leader"
      and d_trunc2.get("wiki_verify_confirm") == "disagree-trunc"
      and d_trunc2.get("wiki_verify2_truncated") == 1
      and len(_calls) == 2,
      (v_trunc2.get("outcome"), d_trunc2.get("wiki_verify_confirm")))

    # I0-П2b-фикс: полный JSON только с объектом лидера (n=3) → disagree-partial
    _calls.clear()
    _ds_seq.seq = [
        json.dumps({"verdicts": [
            {"index": 1, "fit": "yes", "why": "a"},
            {"index": 2, "fit": "no", "why": "n"},
            {"index": 3, "fit": "no", "why": "n"},
        ]}),
        json.dumps({"verdicts": [
            {"index": 1, "fit": "yes", "why": "only leader"},
        ]}),
    ]
    z21["ds_chat"] = _ds_seq
    v_partial = z21["wiki_verify_candidates"]("q", {}, _cards(3), {})
    d_partial = v_partial.get("diag") or {}
    t("P2b fix partial JSON only leader ≠ agree",
      v_partial.get("outcome") != "leader"
      and d_partial.get("wiki_verify_confirm") == "disagree-partial"
      and len(_calls) == 2,
      (v_partial.get("outcome"), d_partial.get("wiki_verify_confirm")))

    # I0-П2b-фикс: лидер yes + чужой yes → disagree (other_yes)
    _calls.clear()
    _ds_seq.seq = [
        json.dumps({"verdicts": [
            {"index": 1, "fit": "yes", "why": "a"},
            {"index": 2, "fit": "no", "why": "n"},
        ]}),
        json.dumps({"verdicts": [
            {"index": 1, "fit": "yes", "why": "a2"},
            {"index": 2, "fit": "yes", "why": "other"},
        ]}),
    ]
    z21["ds_chat"] = _ds_seq
    v_dual = z21["wiki_verify_candidates"]("q", {}, _cards(2), {})
    d_dual = v_dual.get("diag") or {}
    srcs_dual = [c.get("src_table") for c in (v_dual.get("candidates") or [])]
    t("P2b fix leader+other yes → disagree",
      v_dual.get("outcome") == "clarify"
      and v_dual.get("leader") is None
      and set(srcs_dual) == {"catalog_a", "catalog_b"}
      and d_dual.get("wiki_verify_confirm") == "disagree"
      and len(_calls) == 2,
      (v_dual.get("outcome"), d_dual.get("wiki_verify_confirm"), srcs_dual))

    _calls.clear()
    _ds_seq.seq = [
        json.dumps({"verdicts": [
            {"index": 1, "fit": "yes", "why": "a"},
            {"index": 2, "fit": "no", "why": "n"},
        ]}),
        json.dumps({"verdicts": [
            {"index": 1, "fit": "no", "why": "flip"},
            {"index": 2, "fit": "yes", "why": "other"},
        ]}),
    ]
    z21["ds_chat"] = _ds_seq
    v_other = z21["wiki_verify_candidates"]("q", {}, _cards(2), {})
    srcs_other = [c.get("src_table") for c in (v_other.get("candidates") or [])]
    t("P2b disagree-other: clarify both, not leader",
      v_other.get("outcome") == "clarify"
      and v_other.get("leader") is None
      and set(srcs_other) == {"catalog_a", "catalog_b"}
      and (v_other.get("diag") or {}).get("wiki_verify_confirm") == "disagree"
      and len(_calls) == 2)

    _calls.clear()
    _ds_seq.seq = [
        json.dumps({"verdicts": [
            {"index": 1, "fit": "yes", "why": "a"},
            {"index": 2, "fit": "no", "why": "n"},
        ]}),
        json.dumps({"verdicts": [
            {"index": 1, "fit": "no", "why": "n"},
            {"index": 2, "fit": "no", "why": "n"},
        ]}),
    ]
    z21["ds_chat"] = _ds_seq
    v_allno = z21["wiki_verify_candidates"]("q", {}, _cards(2), {})
    t("P2b disagree-all-no → none",
      v_allno.get("outcome") == "none"
      and (v_allno.get("diag") or {}).get("wiki_verify_confirm") == "disagree"
      and len(_calls) == 2)

    _calls.clear()
    _ds_seq.seq = [
        json.dumps({"verdicts": [
            {"index": 1, "fit": "yes", "why": "a"},
            {"index": 2, "fit": "no", "why": "n"},
        ]}),
        RuntimeError("confirm down"),
    ]
    z21["ds_chat"] = _ds_seq
    v_err = z21["wiki_verify_candidates"]("q", {}, _cards(2), {})
    srcs_err = [c.get("src_table") for c in (v_err.get("candidates") or [])]
    t("P2b disagree-error → clarify first yes, not leader",
      v_err.get("outcome") == "clarify"
      and v_err.get("leader") is None
      and srcs_err == ["catalog_a"]
      and (v_err.get("diag") or {}).get("wiki_verify_confirm") == "disagree"
      and (v_err.get("diag") or {}).get("wiki_verify2_error") == 1
      and len(_calls) == 2)

    _calls.clear()
    _ds_seq.seq = [
        json.dumps({"verdicts": [
            {"index": 1, "fit": "yes", "why": "ok"},
        ]}),
        json.dumps({"verdicts": [
            {"index": 1, "fit": "no", "why": "should not run"},
        ]}),
    ]
    z21["ds_chat"] = _ds_seq
    z21["psql"] = lambda q: [
        ("catalog_a", "Alpha", "wiki body", "", "", "", "catalog"),
    ]
    v_single = z21["wiki_verify_candidates"]("q", {}, _cards(1), {})
    t("P2b single pool: no confirm call",
      v_single.get("outcome") == "leader"
      and len(_calls) == 1
      and "wiki_verify_confirm" not in (v_single.get("diag") or {}))

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
    t("mock two yes no confirm",
      "wiki_verify_confirm" not in (vfy2.get("diag") or {}))

    # интеграция try_wiki: verify перекрывает pick-none
    z21["wiki_hybrid_pool"] = lambda q, intent=None: _cards(2)
    pick_calls = []
    verify_payload = []

    def _pick(q, intent, cards, diag=None):
        pick_calls.append(1)
        return {"outcome": "none", "reason": "model_none", "diag": diag or {}}

    def _ds_verify(*a, **k):
        verify_payload.append(a)
        # В4/4-А: лидер только при остальных no — мок обязан отвергнуть №2.
        return json.dumps({"verdicts": [
            {"index": 1, "fit": "yes", "why": "v"},
            {"index": 2, "fit": "no", "why": "n"},
        ]})

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

    # I0-П2-фикс: исключение ds_chat → wiki_verdicts=[] + wiki_verify_error=1
    def _boom(*a, **k):
        raise RuntimeError("model down")

    z21["ds_chat"] = _boom
    vfy_exc = z21["wiki_verify_candidates"]("q", {}, _cards(2), {})
    d_exc = vfy_exc.get("diag") or {}
    t("exception degraded → wiki_verdicts []",
      vfy_exc.get("outcome") == "degraded" and d_exc.get("wiki_verdicts") == [])
    t("exception degraded → wiki_verify_error 1",
      d_exc.get("wiki_verify_error") == 1)
    t("exception degraded → TRACE condition",
      ("wiki_verdicts" in d_exc or d_exc.get("wiki_verify_error")))

    # I0-П2: diag несёт wiki_verdicts (наблюдаемость, без смены выбора)
    z21["psql"] = lambda q: []
    z21["wiki_validate_leader_axes"] = lambda *a, **k: True
    z21["ds_chat"] = lambda *a, **k: json.dumps({"verdicts": [
        {"index": 1, "fit": "yes", "why": "ok line"},
        {"index": 2, "fit": "no", "why": "reject"},
    ]})
    vfy_diag = z21["wiki_verify_candidates"]("q", {}, _cards(2), {})
    wv = (vfy_diag.get("diag") or {}).get("wiki_verdicts")
    t("diag wiki_verdicts keys i/fit/why",
      isinstance(wv, list) and len(wv) == 2
      and all(set(x) == {"i", "fit", "why"} for x in wv)
      and wv[0]["i"] == 1 and wv[0]["fit"] == "yes"
      and wv[1]["i"] == 2 and wv[1]["fit"] == "no",
      wv)
    z21["ds_chat"] = lambda *a, **k: json.dumps({"verdicts": [
        {"index": 1, "fit": "yes",
         "why": "line1\nline2  with   spaces\r\nand CR"},
        {"index": 2, "fit": "no", "why": "n"},
    ]})
    vfy_nl = z21["wiki_verify_candidates"]("q", {}, _cards(2), {})
    why_nl = ((vfy_nl.get("diag") or {}).get("wiki_verdicts") or [{}])[0].get("why", "")
    t("diag why one line no newlines",
      "\n" not in why_nl and "\r" not in why_nl
      and "  " not in why_nl
      and why_nl.startswith("line1 line2"),
      repr(why_nl))
    z21["ds_chat"] = lambda *a, **k: json.dumps({"verdicts": []})
    vfy_empty_diag = z21["wiki_verify_candidates"]("q", {}, _cards(2), {})
    t("empty verdicts → wiki_verdicts []",
      (vfy_empty_diag.get("diag") or {}).get("wiki_verdicts") == [])

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

    # [02.09] class 9 снят из post-verify: warehouse-резолвер больше не зовётся
    z21["wiki_measure_carried"] = lambda src, m: True
    z21["_wiki_axis_has_carriers"] = lambda phrase, intent, question="": True
    _rw_calls = []

    def _rw_track(question, intent=None):
        _rw_calls.append(question)
        return "axis_place"

    z21["resolved_warehouse_axis_word"] = _rw_track
    z21["resolved_unaccounted_slice_axis_word"] = (
        lambda question, intent=None: "")

    def _carries_real(leader, axis_word, intent=None, question="",
                      *, require_axis_cats=False):
        leader = (leader or "").strip()
        axis_word = (axis_word or "").strip()
        if not leader or not axis_word:
            return True
        _efc = z21.get("entity_form_catalogs_for_kind")
        if not callable(_efc):
            return True
        period = (intent or {}).get("period") or {}
        has_period = bool(period.get("from") or period.get("to"))
        axis_cats = [c for c in (_efc(axis_word, allow_meaning=has_period) or []) if c]
        if not axis_cats:
            return not require_axis_cats
        if leader in axis_cats:
            return True
        return leader != "catalog_nom"

    z21["wiki_leader_carries_axis"] = _carries_real

    diag_rw = {}
    ok_rw = z21["wiki_leader_post_verify"](
        "catalog_nom",
        {"kind": "entity_k", "action_axis": ""},
        "q with place axis",
        diag_rw)
    t("class9 removed: warehouse resolver not called from post-verify",
      ok_rw and not _rw_calls and not diag_rw.get("wiki_none"))

    # [02.09] post-verify: ось из resolved_unaccounted_slice_axis_word
    z21["resolved_warehouse_axis_word"] = lambda question, intent=None: ""
    z21["_wiki_axis_has_carriers"] = lambda phrase, intent, question="": False
    z21["wiki_leader_carries_axis"] = _carries_real
    z21["entity_form_catalogs_for_kind"] = (
        lambda word, allow_meaning=True: (
            ["catalog_места"] if str(word).startswith("склад")
            or word == "axis_slice" else []))
    z21["resolved_unaccounted_slice_axis_word"] = (
        lambda question, intent=None: "axis_slice")

    diag_ua = {}
    ok_ua = z21["wiki_leader_post_verify"](
        "catalog_nom",
        {"kind": "entity_k", "action_axis": ""},
        "q with unaccounted slice",
        diag_ua)
    t("empty action_axis + unaccounted resolver → none when leader lacks axis",
      (not ok_ua) and diag_ua.get("wiki_none") == "axis_not_carried"
      and diag_ua.get("wiki_axis_not_carried") == "catalog_nom")

    diag_ua_ok = {}
    ok_ua_ok = z21["wiki_leader_post_verify"](
        "catalog_места",
        {"kind": "entity_k", "action_axis": ""},
        "q with unaccounted slice",
        diag_ua_ok)
    t("unaccounted resolver + leader carries axis → keep leader",
      ok_ua_ok and not diag_ua_ok.get("wiki_none"))

    diag_ua_subj = {}
    ok_ua_subj = z21["wiki_leader_post_verify"](
        "catalog_nom",
        {"kind": "axis_slice", "action_axis": ""},
        "q with unaccounted slice",
        diag_ua_subj)
    t("unaccounted resolver as subject → keep leader",
      ok_ua_subj and not diag_ua_subj.get("wiki_none"))

    # vacuum carry: unaccounted + пустой axis_cats → False (не True)
    z21["entity_form_catalogs_for_kind"] = (
        lambda word, allow_meaning=True: [])
    z21["resolved_unaccounted_slice_axis_word"] = (
        lambda question, intent=None: "складах")
    diag_vac = {}
    ok_vac = z21["wiki_leader_post_verify"](
        "catalog_номенклатура",
        {"kind": "номенклатура", "action_axis": ""},
        "сколько номенклатуры числится на складах",
        diag_vac)
    t("2402-style: unaccounted + empty axis_cats → axis_not_carried",
      (not ok_vac) and diag_vac.get("wiki_none") == "axis_not_carried"
      and diag_vac.get("wiki_axis_not_carried") == "catalog_номенклатура")

    # негатив: «в компании» — warehouse не в post-verify; unaccounted пуст → keep
    z21["resolved_unaccounted_slice_axis_word"] = (
        lambda question, intent=None: "")
    z21["resolved_warehouse_axis_word"] = (
        lambda question, intent=None: "компании")
    diag_co = {}
    ok_co = z21["wiki_leader_post_verify"](
        "catalog_номенклатура",
        {"kind": "номенклатура", "action_axis": ""},
        "сколько номенклатуры в компании",
        diag_co)
    t("в компании: warehouse not in post-verify → keep leader",
      ok_co and not diag_co.get("wiki_none"))

    z21["resolved_unaccounted_slice_axis_word"] = (
        lambda question, intent=None: "")
    diag_ua_empty = {}
    ok_ua_empty = z21["wiki_leader_post_verify"](
        "catalog_nom",
        {"kind": "entity_k", "action_axis": ""},
        "q no slice",
        diag_ua_empty)
    t("all axis resolvers empty → keep leader (unchanged)",
      ok_ua_empty and not diag_ua_empty.get("wiki_none"))

    # LLM action_axis + пустой efc: прежний vacuum True (require_axis_cats=False)
    z21["_wiki_axis_has_carriers"] = lambda phrase, intent, question="": True
    z21["entity_form_catalogs_for_kind"] = (
        lambda word, allow_meaning=True: [])
    diag_llm = {}
    ok_llm = z21["wiki_leader_post_verify"](
        "catalog_nom",
        {"kind": "entity_k", "action_axis": "axis_k"},
        "q",
        diag_llm)
    t("LLM action_axis + empty axis_cats → keep (vacuum fail-open)",
      ok_llm and not diag_llm.get("wiki_none"))

    # [В4] collapse-equal снесён: равные числа при >1 → меню (1-Б).
    t("В4: collapse helper отсутствует",
      "_wiki_clarify_collapse_answer" not in z21)
    z21_src = Z21.read_text(encoding="utf-8")
    t("В4: collapse equal → clarify (нет silent helper в z21)",
      "_wiki_clarify_collapse" not in z21_src
      and "wiki_clarify_collapsed" not in z21_src)
    t("В4: wiki_menu_captions есть", callable(z21.get("wiki_menu_captions")))

    # I0-П5: degraded verify — непроверенный пик не уходит в ответ
    def _psql_p5(q):
        qs = str(q)
        if "search_wiki_entity_card" in qs and "LIMIT 1" in qs:
            return [("x",)]
        if "search_tables" in qs:
            return [("catalog_a", "Alpha"), ("catalog_b", "Beta")]
        if "wiki_pages" in qs or "wiki_passport" in qs:
            return [("catalog_a", "Alpha", "w", "", "", "", "catalog"),
                    ("catalog_b", "Beta", "w", "", "", "", "catalog")]
        return [("x",)]

    z21["psql"] = _psql_p5
    z21["wiki_validate_leader_axes"] = lambda *a, **k: True
    z21["wiki_leader_post_verify"] = lambda *a, **k: True
    z21["filter_pool_by_named_type"] = lambda q, cards, diag=None: cards

    # (а) пул≥2: pick=leader, verify=degraded → clarify, не picked
    z21["wiki_hybrid_pool"] = lambda q, intent=None: _cards(2)

    def _pick_leader(q, intent, cards, diag=None):
        d = diag if diag is not None else {}
        d["wiki_pick"] = "catalog_a"
        return {"outcome": "leader", "leader": "catalog_a", "diag": d}

    z21["wiki_pick_from_cards"] = _pick_leader
    z21["wiki_verify_candidates"] = lambda q, intent, cards, diag=None: {
        "outcome": "degraded", "diag": dict(diag or {})}
    diag_a = {}
    res_a = z21["try_wiki_hybrid_entity_pick"](
        "q", {}, diag_a, None, 0, by={}, match="", preds=[])
    t("P5a pool≥2 verify-degraded → clarify",
      res_a and res_a.get("kind") == "clarify"
      and len(res_a.get("options") or []) >= 2
      and not res_a.get("picked"),
      res_a)
    t("P5a diag wiki_degraded=1", diag_a.get("wiki_degraded") == 1)
    t("P5a peak not asserted as wiki_pick leader",
      diag_a.get("wiki_pick") == "clarify")
    t("P5a wiki_pick_hint preserves peak",
      diag_a.get("wiki_pick_hint") == "catalog_a", diag_a)

    # (а′) пул≥2: сам pick degraded → тоже меню по пулу
    z21["wiki_pick_from_cards"] = lambda q, intent, cards, diag=None: {
        "outcome": "degraded", "diag": diag or {}}
    _verify_calls = []

    def _verify_must_not(*a, **k):
        _verify_calls.append(1)
        return {"outcome": "leader", "leader": "catalog_a", "diag": {}}

    z21["wiki_verify_candidates"] = _verify_must_not
    diag_a2 = {}
    res_a2 = z21["try_wiki_hybrid_entity_pick"](
        "q", {}, diag_a2, None, 0, by={}, match="", preds=[])
    t("P5a pick-degraded pool≥2 → clarify without verify",
      res_a2 and res_a2.get("kind") == "clarify"
      and not res_a2.get("picked")
      and not _verify_calls
      and diag_a2.get("wiki_degraded") == 1)

    # (б) пул=1 + degraded → None
    z21["wiki_hybrid_pool"] = lambda q, intent=None: _cards(1)
    z21["wiki_verify_candidates"] = lambda q, intent, cards, diag=None: {
        "outcome": "degraded", "diag": dict(diag or {})}
    diag_b = {}
    res_b = z21["try_wiki_hybrid_entity_pick"](
        "q", {}, diag_b, None, 0, by={})
    t("P5b pool=1 degraded → None",
      res_b is None and diag_b.get("wiki_degraded") == 1
      and diag_b.get("wiki_pick") == "fallback")


    # (г) tie+degraded: пул 8, pick=clarify(cands=2) → меню из 2, не 8
    def _cards8(n=8):
        base = _cards(3)
        out = list(base)
        for i in range(3, n):
            out.append({
                "src_table": "catalog_x%d" % i, "name": "X%d" % i,
                "description": "d", "axes": "a", "measures": "m",
                "distance": 0.1 + i * 0.01, "platform_kind": "справочник",
                "parent": ""})
        return out

    pool8 = _cards8(8)
    z21["wiki_hybrid_pool"] = lambda q, intent=None: list(pool8)

    def _pick_tie(q, intent, cards, diag=None):
        d = diag if diag is not None else {}
        d["wiki_pick"] = "clarify"
        return {"outcome": "clarify", "candidates": list(cards)[:2], "diag": d}

    z21["wiki_pick_from_cards"] = _pick_tie
    z21["wiki_verify_candidates"] = lambda q, intent, cards, diag=None: {
        "outcome": "degraded", "diag": dict(diag or {})}
    # labels for any src in pool
    def _psql_p5_tie(q):
        qs = str(q)
        if "search_wiki_entity_card" in qs and "LIMIT 1" in qs:
            return [("x",)]
        if "search_tables" in qs:
            return [(c["src_table"], c["name"]) for c in pool8]
        return [("x",)]
    z21["psql"] = _psql_p5_tie
    diag_tie = {}
    res_tie = z21["try_wiki_hybrid_entity_pick"](
        "q", {}, diag_tie, None, 0, by={}, match="", preds=[])
    n_opts = len(res_tie.get("options") or []) if res_tie else -1
    t("P5g tie+degraded menu size=2 not 8",
      res_tie and res_tie.get("kind") == "clarify" and n_opts == 2,
      {"n": n_opts, "res": res_tie, "deg": diag_tie.get("wiki_degraded")})

    # (д) degraded-меню → no_data при <2 opts: reason=wiki_degraded
    z21["wiki_hybrid_pool"] = lambda q, intent=None: _cards(2)
    z21["wiki_pick_from_cards"] = _pick_leader
    z21["wiki_verify_candidates"] = lambda q, intent, cards, diag=None: {
        "outcome": "degraded", "diag": dict(diag or {})}
    z21["mk_opts"] = lambda srcs, lab_by, *a, **k: (
        [{"label": lab_by.get(srcs[0], srcs[0]), "src": srcs[0]}]
        if srcs else [])
    z21["psql"] = _psql_p5
    diag_e = {}
    res_e = z21["try_wiki_hybrid_entity_pick"](
        "q", {}, diag_e, None, 0, by={}, match="", preds=["doc_date >= 'x'"])
    t("P5e empty-window degraded → None wiki_pick=wiki_degraded",
      res_e is None and diag_e.get("wiki_degraded") == 1
      and diag_e.get("wiki_pick") == "wiki_degraded"
      and diag_e.get("wiki_pick_hint") == "catalog_a",
      diag_e)

    # (в) щель «pass» закрыта: verify-degraded после pick-leader
    # не оставляет leader в pick (мутация pass → краснеет)
    try_src = z21_src
    i_try = try_src.find("def try_wiki_hybrid_entity_pick")
    i_next = try_src.find("\ndef wiki_intent_named_measures", i_try)
    try_body = try_src[i_try:i_next if i_next > 0 else None]
    t("P5v no bare pass on verify degraded",
      "if verify.get(\"outcome\") == \"degraded\":\n            pass"
      not in try_body
      and "wiki_degraded" in try_body)

    r = subprocess.run([sys.executable, "-m", "py_compile", str(Z21)],
                       capture_output=True, text=True)
    t("z21 py_compile", r.returncode == 0, r.stderr[:120])

    print("---", PASS, "ok,", len(FAIL), "fail")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
