#!/usr/bin/env python3
"""В4 замок: построитель подписей wiki_menu_captions (K4 §2.1).

  · N options in → N out, порядок сохранён
  · при наличии паспорта — человеческое name/H1 (U3: без YAML/prose body)
  · без паспорта — человеческий label как есть
  · без фильтрации / слияния / сортировки / выбора
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
Z21 = ROOT / "ask" / "z21_wiki_choice.py"

PASS, FAIL = 0, []

_KIND = frozenset({
    "document", "catalog", "documentjournal",
    "accumulationregister", "informationregister",
    "accountingregister", "calculationregister",
    "chartofaccounts", "businessprocess", "exchangeplan",
})


def t(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, detail)


def _looks_like_src_table(s):
    sl = (s or "").strip().lower()
    if "_" not in sl:
        return False
    return sl.split("_", 1)[0] in _KIND


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
        "looks_like_src_table": _looks_like_src_table,
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
# U3: для меню — name/H1; короткий prose body не дописывать
t("паспорт без YAML → name",
  out[0].get("label") == "Справочник Альфа",
  out[0])
t("без паспорта — label как есть",
  out[1].get("label") == "BetaLabel" and out[2].get("label") == "GammaLabel")
t("не фильтрует", len(out) == 3)
t("не сортирует по found",
  [o["found"] for o in out] == [1, 2, 3])

# U3 §4.1: passport YAML → label чист
PASSPORT_YAML = (
    "---\n"
    "pageType: entity\n"
    "entityType: AccumulationRegister\n"
    "id: entity.accumulationregister_реализациятмц\n"
    "canonicalId: accumulationregister_реализациятмц\n"
    "title: Реализация ТМЦ\n"
    "---\n"
    "\n"
    "# Реализация ТМЦ\n"
    "\n"
    "Record type in this 1C database. Platform entity set: "
    "`accumulationregister_реализациятмц`.\n"
)
out_yaml = fn(
    [{"src": "accumulationregister_реализациятмц", "label": "prev"}],
    passports_by_src={
        "accumulationregister_реализациятмц": {
            "name": "Реализация ТМЦ",
            "wiki_body": PASSPORT_YAML,
        },
    },
)
lab = out_yaml[0].get("label") or ""
cap = out_yaml[0].get("wiki_caption") or ""
blob = (lab + "\n" + cap).lower()
t("U3 YAML → label == name", lab == "Реализация ТМЦ", out_yaml[0])
t("U3 YAML → нет pageType", "pagetype" not in blob, blob[:80])
t("U3 YAML → нет entityType", "entitytype" not in blob)
t("U3 YAML → нет canonicalId", "canonicalid" not in blob)
t("U3 YAML → нет id: entity.", "id: entity." not in blob)
t("U3 YAML → нет забора ---", "---" not in (lab + cap))

# U3 §4.1: card.description = body (тот же запрет)
out_card_yaml = fn(
    [{"src": "x", "label": "X"}],
    cards_by_src={
        "x": {"name": "Реализация ТМЦ", "description": PASSPORT_YAML},
    },
)
clab = out_card_yaml[0].get("label") or ""
cblob = (clab + "\n" + (out_card_yaml[0].get("wiki_caption") or "")).lower()
t("U3 card YAML → label == name", clab == "Реализация ТМЦ", out_card_yaml[0])
t("U3 card YAML → без паспорта на экране",
  "pagetype" not in cblob and "---" not in clab, out_card_yaml[0])

# card без YAML → name (U3: prose body не в label)
out2 = fn(
    [{"src": "x", "label": "X"}],
    cards_by_src={"x": {"name": "CardName", "description": "card desc text"}},
)
t("card без YAML → name",
  out2[0].get("label") == "CardName", out2[0])

# U3 §4.1: em-dash в легитимной подписи
out_em = fn(
    [{"src": "a", "label": "old"}],
    passports_by_src={
        "a": {"name": "А — Б", "wiki_body": "обычный текст без забора"},
    },
)
t("U3 em-dash сохраняется",
  "—" in (out_em[0].get("label") or "") and out_em[0].get("label") == "А — Б",
  out_em[0])

# U3 §4.1: H1 после frontmatter
H1_BODY = (
    "---\n"
    "pageType: entity\n"
    "---\n"
    "\n"
    "# Склад товаров\n"
    "\n"
    "Record type in this 1C database. Platform entity set: "
    "`catalog_склады`.\n"
)
out_h1 = fn(
    [{"src": "catalog_склады", "label": "prev"}],
    passports_by_src={
        "catalog_склады": {"name": "", "wiki_body": H1_BODY},
    },
)
h1_lab = out_h1[0].get("label") or ""
t("U3 H1 после frontmatter", h1_lab == "Склад товаров", out_h1[0])
t("U3 H1 без backticks/src",
  "`" not in h1_lab and "catalog_" not in h1_lab.lower(), h1_lab)

# U3 §4.1: hint
import re as _re
out_hint_uuid = fn(
    [{"src": "a", "label": "A", "hint": "см. 550e8400-e29b-41d4-a716-446655440000 ещё"}],
    passports_by_src={"a": {"name": "A", "wiki_body": ""}},
)
hu = out_hint_uuid[0].get("hint") or ""
t("U3 hint UUID → пусто или без UUID",
  (not hu) or not _re.search(
      r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
      r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", hu),
  repr(hu))

out_hint_pt = fn(
    [{"src": "a", "label": "A", "hint": "pageType: entity"}],
    passports_by_src={"a": {"name": "A", "wiki_body": ""}},
)
t("U3 hint pageType → пусто",
  (out_hint_pt[0].get("hint") or "") == "", out_hint_pt[0])

_LEAK_MARKS = ("pagetype:", "entitytype:", "canonicalid:", "id: entity.", "---")


def _leaky(s):
    low = (s or "").lower()
    return any(m in low for m in _LEAK_MARKS)


# U4-красная, обход №1: паспорт в name — не в подпись
out_u4_name = fn(
    [{"src": "a", "label": "A"}],
    passports_by_src={"a": {"name": "---\npageType: entity\nid: x\n---",
                            "wiki_body": ""}},
)
lab_u4n = (out_u4_name[0].get("label") or "") + (out_u4_name[0].get("wiki_caption") or "")
t("U4: грязный name не утекает", not _leaky(lab_u4n), repr(lab_u4n))

# U4-красная, обход №2: пустые name/h1 + грязный prev — затёрт
out_u4_prev = fn(
    [{"src": "a", "label": "entityType: document xxx"}],
    passports_by_src={"a": {"name": "", "wiki_body": ""}},
)
lab_u4p = (out_u4_prev[0].get("label") or "") + (out_u4_prev[0].get("wiki_caption") or "")
t("U4: грязный prev затёрт", not _leaky(lab_u4p), repr(lab_u4p))

EXAMPLE = out[0].get("label") or ""
t("пример меню непуст", bool(EXAMPLE.strip()))
print("EXAMPLE_MENU:", EXAMPLE)

print("PASS", PASS, "FAIL", len(FAIL))
if FAIL:
    sys.exit(1)
sys.exit(0)
