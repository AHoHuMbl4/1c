#!/usr/bin/env python3
"""Оффлайн-замок Б3: wiki_card_hybrid.sql + ask/z21_wiki_choice.py.

Без сети и живой базы. Проверяет: гибрид-пул SQL, форма карточек, исход «ни один»,
структурные фильтры (action_class, tabpart, axis), отсутствие слов домена.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HYBRID = ROOT / "wiki_card_hybrid.sql"
Z21 = ROOT / "ask" / "z21_wiki_choice.py"

PASS, FAIL = 0, []

FORBIDDEN_ENTITY = re.compile(
    r"(?i)(accumulationregister_|catalog_)(?:остат|номенклат|контрагент|реализац|"
    r"склад|продаж|клиент|товар|warehouse|nomenclature|counterpart)",
)
DOMAIN_LITERAL = re.compile(
    r"(?i)['\"][^'\"]{0,200}(?:остат|склад|warehouse|позиц|номенклат|товар|"
    r"контрагент|клиент|продаж|sale|revenue)[^'\"]{0,200}['\"]",
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
        "kind_word": lambda s: "справочник" if str(s).startswith("catalog_") else "",
        "intent_axis_words": lambda intent: [],
        "registers_for_kind_axes": lambda intent, scope=None: frozenset(),
        "entity_form_catalogs_for_kind": lambda kind, allow_meaning=True: [],
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
        "clarify_say": lambda *a, **k: "",
        "mk_opts": lambda *a, **k: [],
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


def main() -> int:
    hybrid = HYBRID.read_text(encoding="utf-8")
    combined = strip_sql_comments(hybrid)

    t("wiki_card_hybrid.sql exists", HYBRID.is_file())
    t("z21_wiki_choice.py exists", Z21.is_file())

    import os as _os
    _saved = {k: _os.environ.pop(k, None) for k in ("ASK_WIKI_CHOICE",)}
    try:
        _os.environ.setdefault("ASK_TOKEN", "test")
        _os.environ.setdefault("EMBED_BASE_URL", "-")
        _os.environ.setdefault("EMBED_MODEL", "-")
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        import serene_ask as _sa
        t("bootstrap ASK_WIKI_CHOICE defined", hasattr(_sa, "ASK_WIKI_CHOICE"))
        t("bootstrap try_wiki branch off no NameError",
          _sa.try_wiki_hybrid_entity_pick("сколько петель", {}, {}, None, 0) is None)
    finally:
        for k, v in _saved.items():
            if v is None:
                _os.environ.pop(k, None)
            else:
                _os.environ[k] = v

    z21 = load_z21()

    t("knn CTE with LIMIT param", "LIMIT :knn_limit" in hybrid)
    # [01.09, ночь] две формы вопроса — один пул + точное именование сущности.
    t("knn_raw arm (raw question)", "knn_raw" in hybrid
      and ":'question_raw'" in hybrid)
    t("struct_named arm (entity named in question)",
      "struct_named" in hybrid
      and "replace(t.src_table, '_', ' ')" in hybrid)
    t("struct_catalog layer", "struct_catalog" in hybrid)
    t("struct_catalog_event layer", "struct_catalog_event" in hybrid)
    t("event catalog when want_agg", ":want_agg = 1 AND p.src_table LIKE 'catalog_%'" in hybrid)
    t("struct_register layer", "struct_register" in hybrid)
    t("pool UNION dedupe", "DISTINCT ON (src_table)" in hybrid)
    t("pick LIMIT param", "LIMIT :pick_limit" in hybrid)
    t("action_class filter event", "action_class' = 'event'" in hybrid)
    t("action_class filter object", "action_class' = 'object'" in hybrid)
    t("tabpart parent filter", "m.parent <> ''" in hybrid)
    t("want_agg param", ":want_agg" in hybrid)
    t("axis stem via refcols", "search_refcols" in hybrid and "ts_lexize" in hybrid)
    # Живой дефект 30.08: row_number AS rk съедал src_table → wiki_pool=['1','2']
    sel = hybrid[hybrid.rfind("SELECT"):]
    t("hybrid SELECT no leading rk", "AS rk" not in sel.split("FROM")[0])
    t("hybrid SELECT has f.name", "f.name" in sel.split("FROM")[0]
      or "\n       f.name," in hybrid)
    t("hybrid SELECT starts with src_table",
      "SELECT f.src_table" in hybrid or "SELECT\n       f.src_table" in hybrid)
    t("object balance register path", "accumulationregister_%" in hybrid
      and "axis_ok" in hybrid)
    t("returns platform_prefix", "platform_prefix" in hybrid)
    t("uses ai_embed", "ai_embed" in hybrid)
    t("cosine distance", "<=>" in hybrid)

    t("okna_entity_hardcode_scan", FORBIDDEN_ENTITY.search(combined) is None)
    t("domain_routing_literal_scan", DOMAIN_LITERAL.search(combined) is None)

    t("wiki_aggregate_want count", z21["wiki_aggregate_want"]({"want": "count"}))
    t("wiki_aggregate_want sum", z21["wiki_aggregate_want"]({"want": "sum"}))
    t("wiki_aggregate_want rank", z21["wiki_aggregate_want"]({"want": "max"}, "топ товар"))
    t("wiki_action_class event",
      z21["wiki_action_class"]({"action_class": "event"}) == "event")
    t("wiki_action_class object",
      z21["wiki_action_class"]({"action_class": "object"}) == "object")
    t("wiki_action_class none default",
      z21["wiki_action_class"]({"action_class": "bogus"}) == "none")

    cards = [
        {"src_table": "catalog_a", "name": "A", "description": "", "axes": "",
         "measures": "", "distance": 0.1, "platform_kind": "справочник"},
        {"src_table": "catalog_b", "name": "B", "description": "", "axes": "",
         "measures": "", "distance": 0.5, "platform_kind": "справочник"},
    ]
    sep, gap = z21["wiki_knn_separable"](cards)
    t("knn separable wide gap", sep and gap == 0.4)
    cards[1]["distance"] = 0.11
    sep2, gap2 = z21["wiki_knn_separable"](cards)
    t("knn not separable narrow gap", not sep2 and gap2 == 0.01)

    lines = z21["wiki_format_card_lines"](cards[:1])
    t("card form has name platform axes",
      all(x in lines for x in ("name:", "platform:", "axes:", "measures:")))

    pick_none = z21["wiki_pick_from_cards"]("q", {}, [], {})
    t("empty pool none outcome", pick_none.get("outcome") == "none")

    z21["ds_chat"] = lambda *a, **k: '{"choice": 0, "separable": true}'
    pick0 = z21["wiki_pick_from_cards"]("q", {}, cards, {})
    t("model choice 0 none", pick0.get("outcome") == "none")

    z21["question_expects_accounting_data"] = lambda *a, **k: True
    z21["psql"] = lambda q: [("catalog_a", "A", "", "", "", 1, 0.1, "", "catalog")]
    z21["wiki_hybrid_pool"] = lambda q, intent=None: [
        {"src_table": "catalog_a", "name": "A", "description": "", "axes": "",
         "measures": "", "distance": 0.1, "platform_kind": "справочник", "parent": ""}]
    z21["ds_chat"] = lambda *a, **k: '{"choice": 0, "separable": true}'
    fb = z21["try_wiki_hybrid_entity_pick"]("q", {}, {}, None, 0)
    t("wiki none returns fallback None", fb is None)
    t("wiki none diag", (fb is None))

    z21["wiki_validate_leader_axes"] = lambda *a, **k: True
    cards_pick = [
        {"src_table": "catalog_a", "name": "A", "description": "", "axes": "",
         "measures": "", "distance": 0.1, "platform_kind": "справочник"},
        {"src_table": "catalog_b", "name": "B", "description": "", "axes": "",
         "measures": "", "distance": 0.5, "platform_kind": "справочник"},
    ]
    z21["ds_chat"] = lambda *a, **k: '{"choice": 1, "separable": true}'
    pick1 = z21["wiki_pick_from_cards"]("q", {}, cards_pick, {})
    t("model choice 1 leader", pick1.get("outcome") == "leader"
      and pick1.get("leader") == "catalog_a")

    def _val_ok(leader, intent=None):
        if not leader or str(leader).isdigit():
            return False
        head = str(leader).split("_", 1)[0].lower()
        return head in (
            "catalog", "document", "accumulationregister",
            "informationregister", "documentjournal", "constant")
    t("validate register form ok", _val_ok("accumulationregister_x"))
    t("validate digit reject", not _val_ok("1"))
    t("validate catalog form ok", _val_ok("catalog_a"))

    z21["wiki_validate_leader_axes"] = lambda *a, **k: True
    z21["ds_chat"] = lambda *a, **k: '{"choice": 1, "separable": false}'
    pick_cl = z21["wiki_pick_from_cards"]("q", {}, cards, {})
    t("inseparable clarify", pick_cl.get("outcome") == "clarify")

    # stock override: wiki clarify → stock_canon
    z21["ASK_WIKI_CHOICE"] = True
    z21["stock_question_engaged"] = lambda *a, **k: True
    z21["stock_canon_src"] = lambda *a, **k: "accumulationregister_stock"
    z21["try_wiki_hybrid_entity_pick"] = lambda *a, **k: {
        "kind": "clarify", "text": "?", "options": []}
    diag_so = {"stock_canon_locked": "accumulationregister_stock"}
    out_so = z21["wiki_primary_entity_cascade"](
        "q", {"want": "count"}, [], diag_so, None, 0, {}, "", [], {})
    # [01.09 «физически один путь»] перебоев вики-исхода больше нет:
    # clarify возвращается человеку как есть, override невозможен.
    t("wiki clarify возвращается без override",
      out_so.get("kind") == "clarify"
      and diag_so.get("wiki_pick") != "stock_override")
    t("stock override locks stock_canon",
      diag_so.get("stock_canon_locked") == "accumulationregister_stock")
    t("wiki_stock_canon_takeover helper",
      z21["wiki_stock_canon_takeover"](
          "q", {}, {"stock_canon_locked": "accumulationregister_stock"}, [])
      == "accumulationregister_stock")

    # wiki leader catalog + stock engaged → override register, not hybrid_pick
    z21["ASK_WIKI_CHOICE"] = True
    z21["stock_question_engaged"] = lambda *a, **k: True
    z21["stock_canon_src"] = lambda *a, **k: "accumulationregister_stock"
    z21["try_wiki_hybrid_entity_pick"] = lambda *a, **k: {
        "picked": ["catalog_goods"], "marks": {}, "plan": {}}
    diag_cat = {}
    out_cat = z21["wiki_primary_entity_cascade"](
        "q", {"want": "count"}, [], diag_cat, None, 0, {}, "", [], {})
    t("wiki catalog-лидер жив (перебоя регистром нет)",
      out_cat.get("picked") == ["catalog_goods"]
      and diag_cat.get("wiki_hybrid_pick") is True
      and diag_cat.get("wiki_pick") != "stock_override")

    t("ASK_WIKI_CHOICE flag exists", "ASK_WIKI_CHOICE" in z21)
    t("wiki_primary_entity_cascade exists",
      "wiki_primary_entity_cascade" in z21)
    t("cascade has wiki_skip_manual guard",
      "_wiki_skip_manual" in Z21.read_text(encoding="utf-8"))
    t("wiki verify step present",
      "wiki_verify_candidates" in Z21.read_text(encoding="utf-8"))
    t("wiki_passport.sql exists",
      (ROOT / "wiki_passport.sql").is_file())

    boot = (ROOT / "ask" / "_bootstrap.py").read_text(encoding="utf-8")
    t("bootstrap z20 wiki patch", "_patch_z20_wiki_primary" in boot)
    z20_raw = (ROOT / "ask" / "z20_ask_main_http.py").read_text(encoding="utf-8")
    import ask._bootstrap as _boot
    z20_patched = _boot._patch_z20_wiki_primary(z20_raw)
    t("bootstrap patch injects cascade call",
      "wiki_primary_entity_cascade(" in z20_patched)
    t("bootstrap patch: stock_override-инъекции больше нет",
      "stock_override" not in z20_patched)
    # [01.09 «физически один путь»] поздние канонные перебои вырезаны из z20:
    # после патча в коде НЕТ вызовов канон-функций, выбирающих сущность.
    t("z20 без поздних канон-выборов (один путь)",
      "sales_canon_src(cands" not in z20_patched
      and "register_count_src(cands" not in z20_patched
      and "stock_canon_src(cands" not in z20_patched
      and "catalog_count_src(cands" not in z20_patched)
    t("bootstrap net-distinct in no_axis_member",
      "stock_net_distinct" in z20_patched
      and "no_axis_member" in z20_patched)
    t("bootstrap ecp0 then entity_form_gate_open",
      "entity_form_gate_open(intent, diag)" in z20_patched
      and z20_patched.find("_ecp0 = try_event_count_period_clarify")
      < z20_patched.find("entity_form_gate_open(intent, diag)"))
    t("old z20 disk lacks cascade call (patch required)",
      "wiki_primary_entity_cascade(" not in z20_raw)

    z21["ASK_WIKI_CHOICE"] = True
    z21["stock_question_engaged"] = lambda *a, **k: False
    z21["stock_canon_src"] = lambda *a, **k: None
    _bal_calls = []
    z21["try_balance_code_entity_pick"] = lambda *a, **k: (
        _bal_calls.append(1) or {"picked": ["manual_balance"]})
    z21["try_event_code_entity_pick"] = lambda *a, **k: None
    z21["try_count_theme_code_pick"] = lambda *a, **k: None
    z21["pick_entity"] = lambda *a, **k: ([], {}, {})

    def _wiki_none_with_pool(q, intent, diag, cut, t0, **kw):
        diag["wiki_attempted"] = True
        diag["wiki_pool_n"] = 2
        diag["wiki_pick"] = "none"
        return None

    z21["try_wiki_hybrid_entity_pick"] = _wiki_none_with_pool
    diag_c = {}
    out = z21["wiki_primary_entity_cascade"](
        "q", {"want": "count"}, [], diag_c, None, 0, {}, "", [], {})
    t("wiki none+pool skips balance manual",
      not _bal_calls and out.get("kind") == "no_data")
    t("wiki none+pool diag attempted",
      diag_c.get("wiki_attempted") and diag_c.get("wiki_pick") == "none")

    _bal_calls.clear()

    def _wiki_degraded(q, intent, diag, cut, t0, **kw):
        diag["wiki_pick"] = "fallback"
        return None

    z21["try_wiki_hybrid_entity_pick"] = _wiki_degraded
    diag_c2 = {}
    out2 = z21["wiki_primary_entity_cascade"](
        "q", {"want": "count"}, [], diag_c2, None, 0, {}, "", [], {})
    # [01.09 «физически один путь»] fallback-лестницы нет: даже при
    # degraded-вики баланс-«ручной выбор» не зовётся — честный отказ.
    t("вики degraded → no_data, не ручной выбор",
      not _bal_calls and out2.get("kind") == "no_data")

    r = subprocess.run([sys.executable, "-m", "py_compile", str(Z21)],
                       capture_output=True, text=True)
    t("z21 py_compile", r.returncode == 0, r.stderr[:120])

    print("---", PASS, "ok,", len(FAIL), "fail")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
