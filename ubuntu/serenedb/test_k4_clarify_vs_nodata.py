#!/usr/bin/env python3
"""S1: K4 clarify vs nodata — veto helpers снесены; accounting slit жив."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("ASK_TOKEN", "test")
os.environ.setdefault("EMBED_BASE_URL", "-")
os.environ.setdefault("EMBED_MODEL", "-")

import serene_ask as A  # noqa: E402

PASS, FAIL = 0, []


def t(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, detail)


for name in ("src_supports_question", "pick_measure", "kind_has_corpus_support",
             "canon_claims_question"):
    t("S1 GONE: " + name, not hasattr(A, name))

t("question_expects_accounting_data slit",
  callable(A.question_expects_accounting_data))
t("off-topic creative → False",
  not A.question_expects_accounting_data({}, "напиши стих про окна"))
t("sum want → True",
  A.question_expects_accounting_data({"want": "sum"}, "сколько продали"))

print("PASS", PASS, "FAIL", len(FAIL))
sys.exit(1 if FAIL else 0)
