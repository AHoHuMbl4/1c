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
    t("struct_catalog layer", "struct_catalog" in hybrid)
    t("struct_register layer", "struct_register" in hybrid)
    t("pool UNION dedupe", "DISTINCT ON (src_table)" in hybrid)
    t("pick LIMIT param", "LIMIT :pick_limit" in hybrid)
    t("action_class filter event", "action_class' = 'event'" in hybrid)
    t("action_class filter object", "action_class' = 'object'" in hybrid)
    t("tabpart parent filter", "m.parent <> ''" in hybrid)
    t("want_agg param", ":want_agg" in hybrid)
    t("axis stem via refcols", "search_refcols" in hybrid and "ts_lexize" in hybrid)
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

    z21["ds_chat"] = lambda *a, **k: '{"choice": 1, "separable": false}'
    pick_cl = z21["wiki_pick_from_cards"]("q", {}, cards, {})
    t("inseparable clarify", pick_cl.get("outcome") == "clarify")

    t("ASK_WIKI_CHOICE flag exists", "ASK_WIKI_CHOICE" in z21)

    r = subprocess.run([sys.executable, "-m", "py_compile", str(Z21)],
                       capture_output=True, text=True)
    t("z21 py_compile", r.returncode == 0, r.stderr[:120])

    print("---", PASS, "ok,", len(FAIL), "fail")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
