#!/usr/bin/env python3
"""В4 замок: построитель подписей wiki_menu_captions (K4 §2.1).

  · N options in → N out, порядок сохранён
  · при наличии паспорта в options есть его текст
  · без паспорта — человеческий label как есть
  · без фильтрации / слияния / сортировки / выбора
"""
from __future__ import annotations

import sys
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
        "_intent_text": lambda x: "",
        "ds_chat": lambda *a, **k: "{}",
        "lit": lambda s: "'%s'" % s,
        "psql": lambda q: [],
        "register_zone": lambda *a, **k: None,
        "apply_bindings": lambda g: None,
        "WIKI_PASSPORT_N": 8,
        "WIKI_PASSPORT_BODY_MAX": 400,
    }
    for k, v in vars(real_imp).items():
        if k.startswith("_") and k not in ("__builtins__",):
            continue
        ns.setdefault(k, v)
    exec(compile(src, str(Z21), "exec"), ns)
    return ns


z21 = load_z21()
fn = z21["wiki_menu_captions"]
t("wiki_menu_captions exists", callable(fn))

opts = [
    {"src": "catalog_a", "label": "AlphaLabel", "hint": "", "found": 1},
    {"src": "catalog_b", "label": "BetaLabel", "hint": "", "found": 2},
    {"src": "document_c", "label": "GammaLabel", "hint": "", "found": 3},
]
passports = {
    "catalog_a": {
        "name": "Справочник Альфа",
        "wiki_body": "карточки контрагентов и реквизиты",
        "src_table": "catalog_a",
    },
}
out = fn(opts, passports_by_src=passports)
t("N→N", len(out) == len(opts), (len(out), len(opts)))
t("порядок сохранён",
  [o["src"] for o in out] == [o["src"] for o in opts])
t("паспортный текст в options",
  "карточки контрагентов" in (out[0].get("label") or "")
  or "карточки контрагентов" in (out[0].get("wiki_caption") or ""),
  out[0])
t("без паспорта — label как есть",
  out[1].get("label") == "BetaLabel" and out[2].get("label") == "GammaLabel")
t("не фильтрует", len(out) == 3)
t("не сортирует по found",
  [o["found"] for o in out] == [1, 2, 3])

# card fallback
out2 = fn(
    [{"src": "x", "label": "X"}],
    cards_by_src={"x": {"name": "CardName", "description": "card desc text"}},
)
t("card description в label",
  "card desc text" in (out2[0].get("label") or ""), out2[0])

# example menu line for report
EXAMPLE = out[0].get("label") or ""
t("пример меню непуст", bool(EXAMPLE.strip()))
print("EXAMPLE_MENU:", EXAMPLE)

print("PASS", PASS, "FAIL", len(FAIL))
if FAIL:
    sys.exit(1)
sys.exit(0)
