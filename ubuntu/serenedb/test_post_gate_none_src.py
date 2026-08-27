#!/usr/bin/env python3
"""Патч 1: post-gate при src=None не даёт TypeError (`x in None`).

Оффлайн. Источник: docs/I2_ACCEPTANCE_OKNA_2026-08-27.md (broken ×2).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ASK_TOKEN", "test")
os.environ.setdefault("EMBED_BASE_URL", "-")
os.environ.setdefault("EMBED_MODEL", "-")

import serene_ask as A  # noqa: E402

PASS, FAIL = 0, []


def t(name, cond, detail=None):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, detail if detail is not None else "")


t("_src_tag(None) пусто", A._src_tag(None) == "")
t("_src_tag('') пусто", A._src_tag("") == "")
t("_src_tag catalog ok", A._src_tag("catalog_контрагенты") == "контрагенты")
t("_src_tag без _", A._src_tag("x") == "x")

# Симуляция post-gate: гейт прошёл, src=None — раньше `"_" in src` → TypeError.
_src = None
try:
    tag = A._src_tag(_src)
    sources = [tag] if tag else []
    ok = True
except TypeError as e:
    ok = False
    err = str(e)
else:
    err = ""
t("post-gate src=None: нет TypeError", ok, err)
t("post-gate src=None: sources пуст", sources == [])

print("----")
print("%d ok, %d FAIL" % (PASS, len(FAIL)))
if FAIL:
    print("failed:", ", ".join(FAIL))
sys.exit(1 if FAIL else 0)
