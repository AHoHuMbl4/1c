#!/usr/bin/env python3
"""K4-3 / K5: служебные OData-имена на первом экране clarify.

Оффлайн. Замок проверяет, что text и options[].label/hint при kind=clarify
свободны от OData-префиксов (перечень META_PREFIXES ниже).
Источник: docs/K4_AXIS_AND_NAMES.md §6.1.

Запуск: python3 ubuntu/serenedb/test_k4_meta_names.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ASK_TOKEN", "test")
os.environ.setdefault("EMBED_BASE_URL", "-")
os.environ.setdefault("EMBED_MODEL", "-")

import serene_ask as A  # noqa: E402

PASS, FAIL = 0, []

META_PREFIXES = (
    "document_",
    "catalog_",
    "documentjournal_",
    "accumulationregister_",
    "informationregister_",
    "accountingregister_",
    "calculationregister_",
    "chartofaccounts_",
    "businessprocess_",
    "exchangeplan_",
)


def t(name, cond, detail=None):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, detail if detail is not None else "")


def screen_leaks(obj):
    """True, если на первом экране видны служебные имена."""
    parts = [str(obj.get("text") or "")]
    for o in obj.get("options") or []:
        if not isinstance(o, dict):
            continue
        parts.append(str(o.get("label") or ""))
        parts.append(str(o.get("hint") or ""))
    blob = "\n".join(parts).lower()
    for p in META_PREFIXES:
        if p in blob:
            return True, p
    for tok in blob.replace("\n", " ").split():
        if A.looks_like_src_table(tok.strip(".,;:?«»\"'()")):
            return True, tok
    return False, None


SRC = "accumulationregister_товарынаскладах"

# --- human_table_label / disambiguate ---
t("human: пустая метка → без префикса",
  not A.label_has_meta_src(A.human_table_label(SRC, "")))
t("human: метка=src → без префикса",
  not A.label_has_meta_src(A.human_table_label(SRC, SRC)))
t("human: живая метка сохраняется",
  A.human_table_label(SRC, "Товары на складах") == "Товары на складах")
t("human: (документ) у человеческой метки допустим",
  "документ" in A.label_with_kind("document_отгрузкапробная", "Отгрузка Пробная")
  and not A.label_has_meta_src(
      A.label_with_kind("document_отгрузкапробная", "Отгрузка Пробная")))

dis = A.disambiguate_labels([(SRC, "")], ambiguous=frozenset())
t("disambiguate: пустая метка без accumulationregister_",
  SRC in dis and not A.label_has_meta_src(dis[SRC]), dis)

dis2 = A.disambiguate_labels(
    [("accumulationregister_x", "X"), ("document_x", "X")],
    ambiguous=frozenset())
t("disambiguate: many → kind_word, без OData-префикса",
  all(not A.label_has_meta_src(v) for v in dis2.values())
  and any("регистр" in v or "документ" in v for v in dis2.values()), dis2)

# --- balance_bridge_clarify с пустым label ---
_real = A.psql


def _empty_label_psql(q):
    if "search_tables" in q or "FROM" in q.upper():
        return [(SRC, None)]
    return []


A.psql = _empty_label_psql
A._AMBIG_CACHE.clear()
A._AMBIG_CACHE["at"] = 0.0
A._AMBIG_CACHE["set"] = frozenset()
try:
    br = A.balance_bridge_clarify(
        "Сколько товара на складе?", {SRC}, {}, {}, time.time(), labels={})
    t("bridge: kind=clarify", br and br.get("kind") == "clarify", br)
    leak, why = screen_leaks(br or {})
    t("bridge: экран без OData-префиксов", not leak, (why, br))
    # src внутри dict — внутреннее, допустимо
    t("bridge: src внутри option остаётся",
      br and any(o.get("src") == SRC for o in (br.get("options") or [])), br)
finally:
    A.psql = _real

# --- mk_opts с lab_by={src: src} ---
A._AMBIG_CACHE.clear()
A._AMBIG_CACHE["at"] = 0.0
A._AMBIG_CACHE["set"] = frozenset()
A.psql = lambda q: []  # opts_hints / ambiguous пусты
try:
    opts = A.mk_opts([SRC], {SRC: SRC}, live={SRC: 1})
    leak, why = screen_leaks({"text": "", "options": opts})
    t("mk_opts: lab_by=src → экран без префикса", not leak, (why, opts))
finally:
    A.psql = _real

# --- format_clarify_options fail-closed ---
raw_opts = [{"src": SRC, "label": SRC, "hint": "see catalog_foo", "measure": ""}]
lines = A.format_clarify_options("сколько?", raw_opts)
blob = "\n".join(lines).lower()
t("format: сырой src в label заменён",
  "accumulationregister_" not in blob and "catalog_" not in blob, lines)

# --- регрессия: человеческая метка + вид ---
ok_lab = "Отгрузка Пробная (документ)"
t("регрессия: Отгрузка Пробная (документ) допустима",
  not A.label_has_meta_src(ok_lab))

print("----")
print("%d ok, %d FAIL" % (PASS, len(FAIL)))
if FAIL:
    print("failed:", ", ".join(FAIL))
sys.exit(1 if FAIL else 0)
