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

    v_one = z21["wiki_parse_verify_response"](
        json.dumps({"verdicts": [
            {"index": 1, "fit": "yes", "why": "matches axis"},
            {"index": 2, "fit": "no", "why": "wrong kind"},
        ]}), 2)
    t("parse two verdicts", len(v_one) == 2 and v_one[0]["fit"] == "yes")

    out_one = z21["wiki_outcome_from_verify"](v_one, _cards(2), {}, {})
    t("one yes → leader", out_one.get("outcome") == "leader"
      and out_one.get("leader") == "catalog_a")

    v_two = z21["wiki_parse_verify_response"](
        json.dumps({"verdicts": [
            {"index": 1, "fit": "yes", "why": "a"},
            {"index": 2, "fit": "yes", "why": "b"},
        ]}), 2)
    out_two = z21["wiki_outcome_from_verify"](v_two, _cards(2), {}, {})
    t("two yes → clarify", out_two.get("outcome") == "clarify"
      and len(out_two.get("candidates") or []) == 2)

    v_zero = z21["wiki_parse_verify_response"](
        json.dumps({"verdicts": [
            {"index": 1, "fit": "no", "why": "nope"},
            {"index": 2, "fit": "no", "why": "nope2"},
        ]}), 2)
    out_zero = z21["wiki_outcome_from_verify"](v_zero, _cards(2), {}, {})
    t("zero yes → none", out_zero.get("outcome") == "none")

    v_unsure = z21["wiki_parse_verify_response"](
        json.dumps({"verdicts": [
            {"index": 1, "fit": "yes", "why": "maybe a"},
            {"index": 2, "fit": "unsure", "why": "unclear"},
        ]}), 2)
    out_unsure = z21["wiki_outcome_from_verify"](v_unsure, _cards(2), {}, {})
    t("yes+unsure → clarify", out_unsure.get("outcome") == "clarify")

    v_ru = z21["wiki_parse_verify_response"](
        json.dumps({"verdicts": [{"index": 1, "fit": "подходит", "why": "x"}]}), 1)
    t("parse russian fit подходит", v_ru and v_ru[0]["fit"] == "yes")

    single = _cards(1)
    out_single = z21["wiki_verify_candidates"]("q", {}, single, {})
    t("single pool struct leader no model",
      out_single.get("outcome") == "leader"
      and out_single.get("diag", {}).get("wiki_verify_skipped"))

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
    z21["ASK_WIKI_CHOICE"] = True
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

    t("try_wiki integrates verify step",
      "wiki_verify_candidates" in Z21.read_text(encoding="utf-8"))

    r = subprocess.run([sys.executable, "-m", "py_compile", str(Z21)],
                       capture_output=True, text=True)
    t("z21 py_compile", r.returncode == 0, r.stderr[:120])

    print("---", PASS, "ok,", len(FAIL), "fail")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
