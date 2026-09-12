#!/usr/bin/env python3
"""S1 некролог: axis_focus_plan жил в legacy-тракте и снесён с ним (W2-A1 S1)."""
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


t("S1: axis_focus_plan GONE", not hasattr(A, "axis_focus_plan"))
t("readings_menu жив (onepath)", callable(getattr(A, "readings_menu", None)))
t("z20 без axis_focus_plan",
  "axis_focus_plan" not in (ROOT / "ask" / "z20_ask_main_http.py").read_text(encoding="utf-8"))

print("PASS", PASS, "FAIL", len(FAIL))
sys.exit(1 if FAIL else 0)
