#!/usr/bin/env python3
"""п.0 TARGET: в ask/*.py нет ПРЕДМЕТНЫХ word-списков — все зоны, трещотка.

30.08 (решение владельца «да»): замок расширен с 5 файлов K9-роутинга на ВСЕ
зоны пакета. Легаси-слова (K7-эпоха: z11 прайс/номенклатура-лексика) не
вычищены одним коммитом — выжженная земля сломала бы каноны продаж. Поэтому
трещотка: базлайн test_no_domain_baseline.json фиксирует существующее;
замок сравнивает текущие вхождения с базлайном и выходит ненулевым кодом
при превышении счётчика или новом сообщении; уменьшение проходит свободно
(перегенерация базлайна — флагом --update-baseline, отдельным коммитом).

Запуск: python3 ubuntu/serenedb/test_no_domain_wordlists.py
"""
from __future__ import annotations

import ast
import json
import os
import re
import sys

ASK_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ask")
BASELINE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "test_no_domain_baseline.json")

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
                self.hits.append("const %s" % t.id)
        if isinstance(node.value, (ast.List, ast.Tuple)):
            for s in _tuple_strings(node.value):
                if DOMAIN_LITERAL.search(s) and s.lower() not in ALLOW:
                    self.hits.append("literal %r" % s[:40])
        self.generic_visit(node)

    def visit_Call(self, node):
        if _is_routing_any_in_q(node):
            for s in _tuple_strings(node.args[0].generators[0].iter):
                if DOMAIN_LITERAL.search(s) and s.lower() not in ALLOW:
                    self.hits.append("any-in-q %r" % s[:40])
        self.generic_visit(node)


def scan_dir():
    """relpath → {сообщение: счётчик} — строки НЕ в ключе (чувствительны к
    правкам выше по файлу), вхождение идентифицируется файлом и текстом."""
    out = {}
    for root, _dirs, files in os.walk(ASK_DIR):
        for fn in sorted(files):
            if not fn.endswith(".py"):
                continue
            path = os.path.join(root, fn)
            try:
                tree = ast.parse(open(path, encoding="utf-8").read(),
                                 filename=path)
            except SyntaxError as e:
                out[os.path.relpath(path, ASK_DIR)] = {
                    "syntax: %s" % e: 1}
                continue
            v = Visitor(path)
            v.visit(tree)
            if v.hits:
                m = {}
                for h in v.hits:
                    m[h] = m.get(h, 0) + 1
                out[os.path.relpath(path, ASK_DIR)] = m
    return out


def main():
    update = "--update-baseline" in sys.argv
    current = scan_dir()
    if update:
        json.dump(current, open(BASELINE, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1, sort_keys=True)
        print("baseline обновлён: %d файлов с вхождениями" % len(current))
        return 0
    base = {}
    if os.path.exists(BASELINE):
        try:
            base = json.load(open(BASELINE, encoding="utf-8"))
        except (ValueError, OSError):
            base = {}
    bad = []
    for f, msgs in sorted(current.items()):
        for msg, n in sorted(msgs.items()):
            bn = (base.get(f) or {}).get(msg, 0)
            if n > bn:
                bad.append("ask/%s: %s ×%d (базлайн %d)" % (f, msg, n, bn))
    if bad:
        print("FAIL — новые предметные слова в зонах ask (п.0 TARGET):")
        for line in bad:
            print(" ", line)
        print("Выжечь легаси — правь код и --update-baseline отдельным коммитом.")
        sys.exit(1)
    n_files = len(current)
    n_legacy = sum(sum(m.values()) for m in current.values())
    print("ok  - no domain wordlists: все зоны ask, легаси-вхождений в базлайне %d "
          "(файлов %d), новых 0" % (n_legacy, n_files))
    return 0


if __name__ == "__main__":
    sys.exit(main())
