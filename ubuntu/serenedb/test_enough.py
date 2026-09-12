#!/usr/bin/env python3
"""В1 негатив: enough-слой снесён из _answer_checked_core.

ENOUGH_ON / serene_enough / question_facts / _need_clarify не читаются в ядре
ответа. Модуль serene_enough.py может жить файлом — вне тракта answer_checked.
Запуск: python3 ubuntu/serenedb/test_enough.py
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
Z20 = ROOT / "ask" / "z20_ask_main_http_legacy.py"

PASS, FAIL = 0, []


def t(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + str(detail)[:240]) if detail else "")


def _func_src(text: str, name: str) -> str:
    """Тело top-level def name(...) до следующего def на том же уровне."""
    m = re.search(r"^def %s\(" % re.escape(name), text, re.M)
    if not m:
        return ""
    start = m.start()
    m2 = re.search(r"^def \w+\(", text[m.end():], re.M)
    end = m.end() + m2.start() if m2 else len(text)
    return text[start:end]


def main() -> int:
    text = Z20.read_text(encoding="utf-8")
    core = _func_src(text, "_answer_checked_core")
    t("_answer_checked_core найден", bool(core))
    t("ENOUGH_ON не читается в _answer_checked_core", "ENOUGH_ON" not in core)
    t("serene_enough не читается в _answer_checked_core", "serene_enough" not in core)
    t("question_facts не в _answer_checked_core", "question_facts" not in core)
    t("_need_clarify не в _answer_checked_core", "_need_clarify" not in core)
    t("ENOUGH_ON нет в z20", "ENOUGH_ON" not in text)
    t("def question_facts снесён", "def question_facts" not in text)
    t("def _need_clarify снесён", "def _need_clarify" not in text)
    # прямой вызов answer (как бывшая else-ветка)
    t("_answer_checked_core зовёт answer напрямую",
      bool(re.search(r"return answer\(", core)))

    # синтаксис зоны
    try:
        ast.parse(text)
        t("z20 парсится (ast)", True)
    except SyntaxError as e:
        t("z20 парсится (ast)", False, str(e))

    print("\n%d проверок пройдено" % PASS)
    if FAIL:
        print("ПРОВАЛЕНО %d: %s" % (len(FAIL), "; ".join(FAIL)))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
