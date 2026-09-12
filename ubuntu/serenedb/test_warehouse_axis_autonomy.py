#!/usr/bin/env python3
"""S1+S3: warehouse_clarify / warehouse_axis_values снесены; readings_menu жив."""
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


t("S1: warehouse_clarify GONE", not hasattr(A, "warehouse_clarify"))
t("S3: warehouse_axis_values GONE", not hasattr(A, "warehouse_axis_values"))
t("readings_menu жив", callable(getattr(A, "readings_menu", None)))
z20 = (ROOT / "ask" / "z20_ask_main_http.py").read_text(encoding="utf-8")
t("z20 без warehouse_clarify call", "warehouse_clarify(" not in z20)

print("PASS", PASS, "FAIL", len(FAIL))
sys.exit(1 if FAIL else 0)
