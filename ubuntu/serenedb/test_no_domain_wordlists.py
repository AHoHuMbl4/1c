#!/usr/bin/env python3
"""K9-ф3: в ask/*.py нет предметных word-списков в маршрутизации.

Запуск: python3 ubuntu/serenedb/test_no_domain_wordlists.py
"""
from __future__ import annotations

import ast
import os
import re
import sys

ASK_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ask")

# K9-ф3: зоны balance/entity маршрутизации (не sales/rank — отдельные фазы).
K9_ROUTING_FILES = frozenset({
    "z02_intent.py",
    "z12_stock_balance.py",
    "z13_fork_outcomes.py",
    "z16_veto_pick_entity.py",
    "z20_ask_main_http.py",
})

# Структурные термины формы вопроса (не домен базы).
ALLOW = frozenset({
    "count", "sum", "list", "event", "object", "none", "data", "coverage",
    "period", "measure", "rank", "compare", "distinct", "complement",
})

# Имена констант-маркеров, которые запрещены в маршрутизации.
FORBIDDEN_CONST = re.compile(
    r"^_(STOCK|WAREHOUSE|AGGREGATE|PER_AXIS|RANK_NOT)_MARKERS?$", re.I)

# Подстроки в литералах — явный домен маршрутизации (не measure alias lookup).
DOMAIN_LITERAL = re.compile(
    r"(остат|склад|warehouse|позиц|номенклат|товар|product|goods|"
    r"всего|итого|вместе|together|contрагент|клиент|продаж|sale|revenue)",
    re.I)


def _tuple_strings(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        yield node.value
    elif isinstance(node, (ast.List, ast.Tuple)):
        for elt in node.elts:
            yield from _tuple_strings(elt)


def _is_routing_any_in_q(node):
    """any(w in q for w in (...)) — типичный word-router."""
    if not isinstance(node, ast.Call):
        return False
    if not (isinstance(node.func, ast.Name) and node.func.id == "any"):
        return False
    if len(node.args) != 1 or not isinstance(node.args[0], ast.GeneratorExp):
        return False
    gen = node.args[0]
    if len(gen.generators) != 1:
        return False
    comp = gen.generators[0]
    if not isinstance(comp.target, ast.Name):
        return False
    if not isinstance(comp.iter, (ast.List, ast.Tuple)):
        return False
    if not isinstance(gen.elt, ast.Compare):
        return False
    if len(gen.elt.ops) != 1 or not isinstance(gen.elt.ops[0], ast.In):
        return False
    if not (isinstance(gen.elt.left, ast.Name) and gen.elt.left.id == comp.target.id):
        return False
    if not (len(gen.elt.comparators) == 1 and isinstance(gen.elt.comparators[0], ast.Name)
            and gen.elt.comparators[0].id == "q"):
        return False
    return True


class Visitor(ast.NodeVisitor):
    def __init__(self, path):
        self.path = path
        self.hits = []

    def visit_Assign(self, node):
        for t in node.targets:
            if isinstance(t, ast.Name) and FORBIDDEN_CONST.search(t.id):
                self.hits.append((node.lineno, "const %s" % t.id))
        if isinstance(node.value, (ast.List, ast.Tuple)):
            for s in _tuple_strings(node.value):
                if DOMAIN_LITERAL.search(s) and s.lower() not in ALLOW:
                    self.hits.append((node.lineno, "literal %r" % s[:40]))
        self.generic_visit(node)

    def visit_Call(self, node):
        if _is_routing_any_in_q(node):
            for s in _tuple_strings(node.args[0].generators[0].iter):
                if DOMAIN_LITERAL.search(s) and s.lower() not in ALLOW:
                    self.hits.append((node.lineno, "any-in-q %r" % s[:40]))
        self.generic_visit(node)


def scan_file(path):
    try:
        tree = ast.parse(open(path, encoding="utf-8").read(), filename=path)
    except SyntaxError as e:
        return [(e.lineno or 0, "syntax: %s" % e)]
    v = Visitor(path)
    v.visit(tree)
    return v.hits


def main():
    bad = []
    for root, _dirs, files in os.walk(ASK_DIR):
        for fn in sorted(files):
            if not fn.endswith(".py"):
                continue
            if fn not in K9_ROUTING_FILES:
                continue
            path = os.path.join(root, fn)
            hits = scan_file(path)
            for ln, msg in hits:
                bad.append("%s:%d %s" % (os.path.relpath(path, os.path.dirname(ASK_DIR)), ln, msg))
    if bad:
        print("FAIL domain wordlists in routing:")
        for line in bad:
            print(" ", line)
        sys.exit(1)
    print("ok  - no domain wordlists in K9 routing (%d files)" % len(K9_ROUTING_FILES))


if __name__ == "__main__":
    main()
