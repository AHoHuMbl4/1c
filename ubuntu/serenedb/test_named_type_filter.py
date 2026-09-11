#!/usr/bin/env python3
"""Замок: тип-фильтр ступени 2 (дополнение к В4, решение владельца 11.09).

Названный в вопросе род метаданных 1С ($metadata) исключает из wiki-пула
карточки чужого platform_kind ДО verify. Без сети и живой базы.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent
Z21 = ROOT / "ask" / "z21_wiki_choice.py"

PASS, FAIL = 0, []


def t(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, detail)


def load_z21():
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
        "_intent_text": lambda x: (
            (x[0] if isinstance(x, (list, tuple)) and x else x or "") or ""),
        "ds_chat": lambda *a, **k: "{}",
        "lit": lambda s: "'%s'" % str(s).replace("'", "''"),
        "psql": lambda q: [],
        "_ensure_embed_secret": lambda: None,
        "kind_word": lambda s: "",
        "rank_intent_from": lambda *a, **k: False,
        "register_zone": lambda *a, **k: None,
        "apply_bindings": lambda g: None,
        "EMBED_MODEL": "m",
        "EMBED_SECRET_NAME": "sec",
        "EMBED_DIM": 1024,
        "STEM_DICT": "russian",
        "TABLES": "search_tables",
        "NO_DATA_TEXT": "",
        "refuse_text": lambda q: "refuse",
        "question_expects_accounting_data": lambda *a, **k: True,
        "clarify_say": lambda *a, **k: "clarify?",
        "mk_opts": lambda *a, **k: [],
        "_diag_pack": lambda d, **k: d,
    }
    for k, v in vars(real_imp).items():
        if k.startswith("_") and k not in ("__builtins__",):
            continue
        ns.setdefault(k, v)
    exec(compile(src, str(Z21), "exec"), ns)
    return ns


def _card(src, platform_kind=""):
    return {
        "src_table": src,
        "name": src.split("_", 1)[-1],
        "description": "",
        "axes": "",
        "measures": "",
        "distance": 0.1,
        "parent": "",
        "platform_kind": platform_kind or src.split("_", 1)[0],
    }


z21 = load_z21()
named = z21["named_platform_kinds"]
filt = z21["filter_pool_by_named_type"]

# (1) «в регистре» → только *register; пул мокается
pool_reg = [
    _card("accumulationregister_X", "регистр накопления"),
    _card("document_X", "документ"),
]
out1 = filt('Сколько движений в регистре «X»', pool_reg, diag={})
t("(1) регистр: остаётся только register",
  [c["src_table"] for c in out1] == ["accumulationregister_X"],
  out1)

# (2) тип не назван → пул без изменений
pool2 = list(pool_reg)
out2 = filt('Сколько записей в «X»', pool2, diag={})
t("(2) тип не назван: пул без изменений",
  [c["src_table"] for c in out2]
  == ["accumulationregister_X", "document_X"],
  out2)

# (3) «в справочнике» → catalog, document исчез
pool3 = [
    _card("catalog_X", "справочник"),
    _card("document_X", "документ"),
]
out3 = filt("Сколько банков в справочнике", pool3, diag={})
t("(3) справочник: остаётся catalog",
  [c["src_table"] for c in out3] == ["catalog_X"],
  out3)

# (4) «журнал документов» → documentjournal, не document
pool4 = [
    _card("documentjournal_X", "журнал документов"),
    _card("document_X", "документ"),
]
out4 = filt("Сколько строк в журнале документов", pool4, diag={})
t("(4) журнал документов → documentjournal, не document",
  [c["src_table"] for c in out4] == ["documentjournal_X"],
  out4)

# (5) «регистр накопления» ≠ «регистр сведений»
pool5 = [
    _card("accumulationregister_X", "регистр накопления"),
    _card("informationregister_X", "регистр сведений"),
]
out5 = filt("Сколько движений в регистре накопления «X»", pool5, diag={})
t("(5) регистр накопления не путается со сведений",
  [c["src_table"] for c in out5] == ["accumulationregister_X"],
  out5)
t("(5b) named_platform_kinds: только accumulation",
  named("в регистре накопления") == ["accumulationregister"],
  named("в регистре накопления"))

# (6) фильтр пуст → пул []
pool6 = [
    _card("document_X", "документ"),
    _card("catalog_X", "справочник"),
]
out6 = filt("Сколько движений в регистре «X»", pool6, diag={})
t("(6) несовместимый пул → []", out6 == [], out6)

# (7) diag: named_type / pool_before / pool_after
diag7 = {}
filt('Сколько движений в регистре «X»', pool_reg, diag=diag7)
t("(7) named_type заполнен",
  isinstance(diag7.get("named_type"), list) and len(diag7["named_type"]) == 4,
  diag7)
t("(7) pool_before / pool_after",
  diag7.get("pool_before") == 2 and diag7.get("pool_after") == 1,
  diag7)

# Проводка в каскаде: пул-функция мокается, фильтр до verify
captured = {}

def _mock_pool(q, intent=None):
    return list(pool_reg)

def _mock_verify(q, intent, cards, diag=None):
    captured["cards"] = list(cards or [])
    return {"outcome": "none", "reason": "test_stop", "diag": dict(diag or {})}

z21["wiki_hybrid_pool"] = _mock_pool
z21["wiki_verify_candidates"] = _mock_verify
z21["wiki_pick_from_cards"] = _mock_verify
z21["psql"] = lambda q: [(1,)] if "search_wiki_entity_card" in q else []
diag_w = {}
z21["try_wiki_hybrid_entity_pick"](
    'Сколько движений в регистре «X»', {}, diag_w, None, 0.0)
t("каскад: фильтр до verify (мок пула)",
  [c["src_table"] for c in captured.get("cards", [])]
  == ["accumulationregister_X"],
  captured.get("cards"))
t("каскад diag named_type/pool_*",
  diag_w.get("named_type") and diag_w.get("pool_before") == 2
  and diag_w.get("pool_after") == 1,
  {k: diag_w.get(k) for k in ("named_type", "pool_before", "pool_after")})

# Гарантия (а): без типа — named_type=[], пул не режется в каскаде
captured.clear()
diag_a = {}
z21["try_wiki_hybrid_entity_pick"](
    'Сколько записей в «X»', {}, diag_a, None, 0.0)
t("без типа: пул в verify полный",
  len(captured.get("cards") or []) == 2, captured.get("cards"))
t("без типа: named_type пуст",
  diag_a.get("named_type") == [], diag_a.get("named_type"))

# Формы слов: «в справочнике», «документа» не есть documentjournal
t("форма справочнике → catalog",
  named("в справочнике") == ["catalog"])
t("форма документа → document",
  named("в документа") == ["document"])
t("регистр без уточнения → 4 register",
  set(named("в регистре"))
  == {"accumulationregister", "informationregister",
      "calculationregister", "accountingregister"})

print("---", PASS, "ok,", len(FAIL), "fail")
sys.exit(1 if FAIL else 0)
