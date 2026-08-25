#!/usr/bin/env python3
"""Оффлайн-замок: measure_resolver не носит списков значений базы в коде.

Без LLM и сети. После аудита Ф6.6: термы только из argv.
"""
from __future__ import annotations

import ast
import os
import re
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "measure_resolver.py")

PASS, FAIL = 0, []


def t(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + str(detail)[:240]) if detail else "")


raw = open(SRC, encoding="utf-8").read()
tree = ast.parse(raw)

# Нет модуля TERMS = [ ... ] с литералами.
assign_terms = []
for node in ast.walk(tree):
    if isinstance(node, ast.Assign):
        for tgt in node.targets:
            if isinstance(tgt, ast.Name) and tgt.id == "TERMS":
                assign_terms.append(node)
t("нет присваивания TERMS", not assign_terms, assign_terms)

# Нет кириллических строковых литералов в исполняемом коде (докстринг/usage — ок).
cyr_lit = []
for node in ast.walk(tree):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        if re.search(r"[А-Яа-яЁё]", node.value):
            # usage/help на русском — в stderr-строках main, не список термов
            if "usage:" in node.value or "стенд:" in node.value:
                continue
            if node.value.strip().startswith("Стендовый") or "НЕ часть" in node.value:
                continue
            cyr_lit.append(node.value[:80])
t("нет кириллических литералов-термов", not cyr_lit, cyr_lit)

# main() требует argv; без аргументов — код 2.
import importlib.util
spec = importlib.util.spec_from_file_location("measure_resolver", SRC)
mod = importlib.util.module_from_spec(spec)
# Не исполняем top-level embed: подменим после load только если есть main.
# Файл при import зовёт только defs — embed только в main.
sys.modules["serene_report"] = type(sys)("serene_report")  # stub до exec
sys.modules["serene_report"].embed = lambda terms: []
sys.modules["serene_report"]._vec_literal = lambda v: "[]"
sys.modules["serene_report"].psql = lambda *a, **k: type("R", (), {"stdout": type("S", (), {"strip": lambda self: ""})()})()
spec.loader.exec_module(mod)
rc = mod.main([])
t("main([]) → 2", rc == 2, rc)

# С аргументами не падает на отсутствии TERMS.
calls = []
def fake_embed(terms):
    calls.append(list(terms))
    return [[0.0] * 2 for _ in terms]
sys.modules["serene_report"].embed = fake_embed
class _Out:
    def strip(self):
        return "x | 0.000"
class _R:
    stdout = _Out()
sys.modules["serene_report"].psql = lambda *a, **k: _R()
# перезагрузка не нужна — main уже на stub embed через R в замыкании модуля
mod.R.embed = fake_embed
mod.R.psql = lambda *a, **k: _R()
mod.R._vec_literal = lambda v: "[0,0]"
rc2 = mod.main(["alpha", "beta"])
t("main(terms) зовёт embed с argv", rc2 == 0 and calls == [["alpha", "beta"]], calls)

print("все", PASS, "проверок зелёные" if not FAIL else "с ошибками")
if FAIL:
    print("FAIL:", ", ".join(FAIL))
    sys.exit(1)
