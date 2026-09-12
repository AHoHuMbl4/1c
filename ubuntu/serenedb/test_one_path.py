#!/usr/bin/env python3
"""Скелет замка «один путь» (O5 §2.6 фаза «скелет»; волна B3).

Читает НОВЫЙ z20_ask_main_http.py по пути (не load_all / не pytest).
Фаза скелета: (г) чёрный список выбирателей + hatch-имена; часть (а) — нет
bare return {kind:clarify} в answer мимо построителя.
Полный (а)(б)(в)(г) — волна B7.
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ASK = ROOT / "ask"
Z20_PATH = ASK / "z20_ask_main_http.py"

PASS, FAIL = 0, []


def t(name, cond, detail=None):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, detail if detail is not None else "")


ALLOWED_CLARIFY_BUILDERS = {
    "clarify_opts_response",
    "readings_menu",
}

FORBIDDEN_SELECTORS = {
    "try_entity_form_answer",
    "try_event_count_period_clarify",
    "period_assumed_needs_clarify",
    "axis_focus_plan",
    "warehouse_clarify",
    "arbitrate",
    "_fork_early",
    "fork_outcome_b",
    "fork_outcome_a",
}

HATCH_NAMES = (
    "measure_hatch",
    "measure_hatch_B",
    "measure_hatch_C",
    "_fork_headline",
    "_fork_headline_measure",
)


def _real_calls(src, sym):
    """Имя символа в коде строки (не в комментарии), как test_no_pre_wiki_reorders."""
    hits = []
    for m in re.finditer(r"\b%s\b" % re.escape(sym), src):
        line_start = src.rfind("\n", 0, m.start()) + 1
        line = src[line_start:src.find("\n", m.start())]
        code = line.split("#", 1)[0]
        if sym in code:
            hits.append(m.start())
    return hits


def _func_node(tree, name):
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def _call_name(node):
    """Имя вызываемой функции (Name или Attribute.attr)."""
    f = node.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return None


def _dict_has_kind_clarify(node):
    """ast.Dict с kind='clarify' (Constant или Str)."""
    if not isinstance(node, ast.Dict):
        return False
    for k, v in zip(node.keys, node.values):
        if k is None:
            continue
        key = None
        if isinstance(k, ast.Constant) and isinstance(k.value, str):
            key = k.value
        if key != "kind":
            continue
        if isinstance(v, ast.Constant) and v.value == "clarify":
            return True
    return False


def _is_builder_call(node):
    if not isinstance(node, ast.Call):
        return False
    return _call_name(node) in ALLOWED_CLARIFY_BUILDERS


def _bare_clarify_returns(answer_node):
    """Return Dict{kind:clarify} в answer без Call построителя."""
    bad = []
    for node in ast.walk(answer_node):
        if not isinstance(node, ast.Return) or node.value is None:
            continue
        val = node.value
        if _dict_has_kind_clarify(val):
            bad.append(getattr(node, "lineno", "?"))
        elif isinstance(val, ast.Call) and not _is_builder_call(val):
            # return some_fn(...) где some_fn не builder — не Dict; пропускаем
            # (wiki_primary / readings_menu уже проверены отдельно).
            pass
    return bad


# ── загрузка ─────────────────────────────────────────────────────────────────
t("новый z20 на диске", Z20_PATH.is_file(), str(Z20_PATH))
z20 = Z20_PATH.read_text(encoding="utf-8") if Z20_PATH.is_file() else ""
tree = None
if z20:
    try:
        tree = ast.parse(z20)
        t("ast.parse z20", True)
    except SyntaxError as e:
        t("ast.parse z20", False, str(e))
else:
    t("ast.parse z20", False, "empty")

answer_node = _func_node(tree, "answer") if tree else None
t("def answer есть", answer_node is not None)

# ── (г) чёрный список выбирателей: 0 call-site (не комментарий) ─────────────
for sym in sorted(FORBIDDEN_SELECTORS):
    hits = _real_calls(z20, sym)
    # call-site: имя + '(' в той же кодовой части строки
    real = []
    for h in hits:
        line_start = z20.rfind("\n", 0, h) + 1
        line = z20[line_start:z20.find("\n", h)]
        code = line.split("#", 1)[0]
        if re.search(r"\b%s\s*\(" % re.escape(sym), code):
            real.append(h)
        elif sym in ("_fork_early",) and re.search(
                r"\b%s\b\s*=" % re.escape(sym), code):
            # присваивание словаря-выбирателя тоже запрет
            real.append(h)
    t("0 call-site %s" % sym, not real, real[:3])

# hatch / fork-headline имена (строка целиком в файле)
for name in HATCH_NAMES:
    t("0 имя %s в новом z20" % name, name not in z20)

# доп. негатив из ТЗ B3 (не в FORBIDDEN_SELECTORS, но контракт волны)
for sym in ("apply_period_leader", "prefer_window_leader", "arb_pool",
            "_ec_atom_fps", "try_entity_form"):
    t("0 %s в новом z20" % sym, sym not in z20)

# ── часть (а): нет bare return {kind:clarify} в answer ─────────────────────────
if answer_node is not None:
    bare = _bare_clarify_returns(answer_node)
    t("answer: 0 bare return kind=clarify Dict", not bare, bare)
    # clarify только через readings_menu / clarify_opts_response (если есть Call)
    clarify_builders_used = []
    for node in ast.walk(answer_node):
        if isinstance(node, ast.Call) and _is_builder_call(node):
            clarify_builders_used.append(_call_name(node))
    t("answer: readings_menu зовётся",
      "readings_menu" in clarify_builders_used)
    t("readings_menu определён в модуле",
      _func_node(tree, "readings_menu") is not None)
else:
    t("answer: 0 bare return kind=clarify Dict", False, "no answer")
    t("answer: readings_menu зовётся", False)
    t("readings_menu определён в модуле", False)

# wiki — единственный выбор сущности в answer
if answer_node is not None:
    wiki_calls = [
        n for n in ast.walk(answer_node)
        if isinstance(n, ast.Call) and _call_name(n) == "wiki_primary_entity_cascade"
    ]
    t("answer зовёт wiki_primary_entity_cascade", len(wiki_calls) >= 1,
      len(wiki_calls))
else:
    t("answer зовёт wiki_primary_entity_cascade", False)


print()
total = PASS + len(FAIL)
if FAIL:
    print("ПРОВАЛЕНО: %s/%s" % (len(FAIL), total), FAIL)
    sys.exit(1)
print("%s/0 зелёные" % PASS)
sys.exit(0)
