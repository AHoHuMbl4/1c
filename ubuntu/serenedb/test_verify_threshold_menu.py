#!/usr/bin/env python3
"""В4 замок: порог wiki verify (решение владельца 4-А).

  · ровно один yes и остальные no → leader
  · yes + unsure → clarify (меню)
  · два yes → clarify (меню)
"""
from __future__ import annotations

import json
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
        "_intent_text": lambda x: (x[0] if isinstance(x, (list, tuple)) and x else x or "") or "",
        "ds_chat": lambda *a, **k: "{}",
        "lit": lambda s: "'%s'" % str(s).replace("'", "''"),
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
cards = [
    {"src_table": "catalog_a", "name": "Alpha"},
    {"src_table": "catalog_b", "name": "Beta"},
    {"src_table": "document_c", "name": "Gamma"},
]

v_leader = [
    {"index": 1, "fit": "yes", "why": "ok"},
    {"index": 2, "fit": "no", "why": "no"},
    {"index": 3, "fit": "no", "why": "no"},
]
out = z21["wiki_outcome_from_verify"](v_leader, cards, {}, {})
t("ровно один yes + остальные no → leader",
  out.get("outcome") == "leader" and out.get("leader") == "catalog_a",
  out)

v_yu = [
    {"index": 1, "fit": "yes", "why": "ok"},
    {"index": 2, "fit": "unsure", "why": "?"},
    {"index": 3, "fit": "no", "why": "no"},
]
out = z21["wiki_outcome_from_verify"](v_yu, cards, {}, {})
t("yes+unsure → clarify",
  out.get("outcome") == "clarify"
  and len(out.get("candidates") or []) == 2,
  out)

v_yy = [
    {"index": 1, "fit": "yes", "why": "a"},
    {"index": 2, "fit": "yes", "why": "b"},
    {"index": 3, "fit": "no", "why": "no"},
]
out = z21["wiki_outcome_from_verify"](v_yy, cards, {}, {})
t("два yes → clarify",
  out.get("outcome") == "clarify"
  and len(out.get("candidates") or []) == 2,
  out)

# missing verdict ≠ no → не молчаливый лидер
v_miss = [
    {"index": 1, "fit": "yes", "why": "ok"},
    # index 2 missing
    {"index": 3, "fit": "no", "why": "no"},
]
out = z21["wiki_outcome_from_verify"](v_miss, cards, {}, {})
t("один yes + пропуск вердикта → не leader",
  out.get("outcome") != "leader", out)

print("PASS", PASS, "FAIL", len(FAIL))
if FAIL:
    sys.exit(1)
sys.exit(0)
