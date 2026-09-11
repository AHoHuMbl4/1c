#!/usr/bin/env python3
"""Замок FINAL: stock-фильтры изъяты из маршрутизации выбора сущности в z20.

Окно: от начала answer() до шага «кандидаты собраны».
В маршруте не используется filter_stock_*/prefer_entity_for_stock/stock_question_engaged
в сборке пула. Серый край stock_bypass_empty_by снесён (В1): пустой by → no_data.
После якоря prefer/filter в маршруте fork/arb тоже не используется; счётные
слои (stock_question_engaged после wiki/arb) — разрешены.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
Z20 = ROOT / "ask" / "z20_ask_main_http.py"

PASS, FAIL = 0, []

FORBIDDEN = (
    "filter_stock_balance_sales_noise",
    "filter_stock_goods_registers",
    "prefer_entity_for_stock",
    "stock_question_engaged",
)


def t(name: str, cond: bool, detail: str = "") -> None:
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + str(detail)[:240]) if detail else "")


def _answer_window(text: str) -> tuple[str, str, str]:
    m_ans = re.search(r"^def answer\(", text, re.M)
    if not m_ans:
        raise SystemExit("def answer not found in z20")
    start = m_ans.start()
    m_end = re.search(r'шаг\("кандидаты собраны"', text[start:])
    if not m_end:
        raise SystemExit("anchor кандидаты собраны not found after answer")
    end = start + m_end.end()
    pre = text[start:end]
    post = text[end:]
    return pre, post, text[start:]


def main() -> int:
    text = Z20.read_text(encoding="utf-8")
    pre, post, answer_body = _answer_window(text)

    t("z20 readable", Z20.is_file() and len(text) > 1000)
    t("answer window non-empty", len(pre) > 200, len(pre))

    # В1: серый bypass снесён — маркера нет нигде в z20
    t("no stock_bypass_empty_by in z20", "stock_bypass_empty_by" not in text)

    for name in FORBIDDEN:
        hits = [i + 1 for i, line in enumerate(pre.splitlines()) if name in line]
        t(
            "route window: no %s" % name,
            not hits,
            "lines_in_window≈%s" % hits,
        )

    # После «кандидаты собраны» prefer/filter не должны вернуться в маршрут
    # (fork/arb). Счётные stock_question_engaged — ок.
    for name in (
        "filter_stock_balance_sales_noise",
        "filter_stock_goods_registers",
        "prefer_entity_for_stock",
    ):
        hits = [i + 1 for i, line in enumerate(post.splitlines()) if name in line]
        t("post-cands route: no %s" % name, not hits, hits)

    # plan={} сохранён до K6 (early path / UnboundLocalError)
    plan_ok = bool(re.search(
        r"prefer_entity_for_catalog_count\(cands, intent, question\)\n"
        r"\s*plan = \{\}\n",
        pre,
    ))
    t("plan={} kept before K6", plan_ok)

    # Сироты в дереве живы (не выжигали z12/z13)
    z12 = (ROOT / "ask" / "z12_stock_balance.py").read_text(encoding="utf-8")
    z13 = (ROOT / "ask" / "z13_fork_outcomes.py").read_text(encoding="utf-8")
    t("orphan filter_stock_balance_sales_noise lives in tree",
      "def filter_stock_balance_sales_noise" in z13 or "filter_stock_balance_sales_noise" in z13)
    t("orphan filter_stock_goods_registers lives in tree",
      "def filter_stock_goods_registers" in z12)
    t("orphan prefer_entity_for_stock lives in tree",
      "def prefer_entity_for_stock" in z12)

    print("PASS %d FAIL %d" % (PASS, len(FAIL)))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
