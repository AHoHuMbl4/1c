#!/usr/bin/env python3
"""S1+S3: stock-фильтры не в маршруте выбора сущности; orphans z12 снесены.

Щель stock_balance_is_sales_noise — в answer-atoms.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
Z20 = ROOT / "ask" / "z20_ask_main_http.py"

PASS, FAIL = 0, []

FORBIDDEN = (
    "filter_stock_balance_sales_noise",
    "filter_stock_goods_registers",
    "prefer_entity_for_stock",
)


def t(name: str, cond: bool, detail: str = "") -> None:
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + str(detail)[:240]) if detail else "")


def main() -> int:
    text = Z20.read_text(encoding="utf-8")
    t("z20 readable", Z20.is_file() and len(text) > 1000)
    t("no stock_bypass_empty_by in z20", "stock_bypass_empty_by" not in text)
    for name in FORBIDDEN:
        hits = [i + 1 for i, line in enumerate(text.splitlines()) if name in line]
        t("z20: no %s" % name, not hits, "lines≈%s" % hits)

    z12 = (ROOT / "ask" / "z12_stock_balance.py").read_text(encoding="utf-8")
    t("S3: filter_stock_goods_registers GONE from z12",
      "def filter_stock_goods_registers" not in z12)
    t("S3: prefer_entity_for_stock GONE from z12",
      "def prefer_entity_for_stock" not in z12)
    import os
    os.environ.setdefault("ASK_TOKEN", "test")
    os.environ.setdefault("EMBED_BASE_URL", "-")
    os.environ.setdefault("EMBED_MODEL", "-")
    sys.path.insert(0, str(ROOT))
    import serene_ask as A  # noqa: E402
    t("S1 slit: stock_balance_is_sales_noise жив",
      callable(getattr(A, "stock_balance_is_sales_noise", None)))
    t("S1: filter_stock_balance_sales_noise снесён",
      not hasattr(A, "filter_stock_balance_sales_noise"))
    t("S3: filter_stock_goods_registers снесён",
      not hasattr(A, "filter_stock_goods_registers"))
    t("S3: prefer_entity_for_stock снесён",
      not hasattr(A, "prefer_entity_for_stock"))

    print("PASS %d FAIL %d" % (PASS, len(FAIL)))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
