#!/usr/bin/env python3
"""Замок «один путь» (O5 §2.6 фаза «после сноса pre-wiki clarify»; волна B4).

Читает НОВЫЙ z20_ask_main_http.py по пути (не load_all / не pytest).
Фаза B4: (г) чёрный список; полная (а) clarify только через построитель;
(в) нет SQL-вызовов до wiki_primary (кроме trusted-билета).
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

SQL_CALLS = {
    "aggregate",
    "aggregate_groups",
    "rows_of",
    "totals_of",
    "aggregate_stock_net_distinct",
    "live_src_counts",
}

B4_FORBIDDEN = (
    "sales_compare_windows",  # как терминал — проверяем call в answer отдельно
    "pick_measure",
    "kind_axis_rerank",
    "max(by",
    "_fork_atom",
    "arb_pool",
    "entity_form_gate_open",
    "measure_in_kin",
)


def _real_calls(src, sym):
    """Имя символа в коде строки (не в комментарии)."""
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
    f = node.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return None


def _dict_has_kind_clarify(node):
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
    return bad


def _clarify_dict_assigns_outside_builder(tree, answer_node):
    """Полная (а): Dict kind=clarify в answer только как результат builder Call."""
    bad = []
    builder_names = set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in ALLOWED_CLARIFY_BUILDERS:
            builder_names.add(id(node))
    for node in ast.walk(answer_node):
        if isinstance(node, ast.Dict) and _dict_has_kind_clarify(node):
            bad.append(getattr(node, "lineno", "?"))
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Call):
            # return readings_menu(...) / clarify_opts_response(...) — ок
            pass
    return bad


def _lineno_of_first_call(answer_node, name):
    for node in ast.walk(answer_node):
        if isinstance(node, ast.Call) and _call_name(node) == name:
            return getattr(node, "lineno", None)
    return None


def _sql_calls_before_wiki(answer_node):
    """(в) SQL_CALLS строго до первого wiki_primary_entity_cascade."""
    wiki_line = _lineno_of_first_call(answer_node, "wiki_primary_entity_cascade")
    if wiki_line is None:
        return ["no wiki_primary_entity_cascade"]
    # Trusted-билет: SQL до wiki допустим только если wiki вообще не зовётся
    # в этой ветке. Здесь смотрим линейно по lineno всех Call в answer.
    bad = []
    for node in ast.walk(answer_node):
        if not isinstance(node, ast.Call):
            continue
        cn = _call_name(node)
        if cn not in SQL_CALLS:
            continue
        ln = getattr(node, "lineno", 0) or 0
        if ln < wiki_line:
            bad.append("%s@%s" % (cn, ln))
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

# ── (г) чёрный список выбирателей ────────────────────────────────────────────
for sym in sorted(FORBIDDEN_SELECTORS):
    hits = _real_calls(z20, sym)
    real = []
    for h in hits:
        line_start = z20.rfind("\n", 0, h) + 1
        line = z20[line_start:z20.find("\n", h)]
        code = line.split("#", 1)[0]
        if re.search(r"\b%s\s*\(" % re.escape(sym), code):
            real.append(h)
        elif sym in ("_fork_early",) and re.search(
                r"\b%s\b\s*=" % re.escape(sym), code):
            real.append(h)
    t("0 call-site %s" % sym, not real, real[:3])

for name in HATCH_NAMES:
    t("0 имя %s в новом z20" % name, name not in z20)

for sym in ("apply_period_leader", "prefer_window_leader", "arb_pool",
            "_ec_atom_fps", "try_entity_form"):
    t("0 %s в новом z20" % sym, sym not in z20)

# B4 grep-негатив (имена-выбиратели)
for sym in ("pick_measure", "kind_axis_rerank", "_fork_atom", "arb_pool",
            "entity_form_gate_open", "measure_in_kin"):
    t("B4: 0 %s" % sym, sym not in z20)
t("B4: 0 max(by в answer", "max(by" not in z20)

# sales_compare_windows — окна как readings ок; терминал-return до compose — нет.
# Допускаем вызов для получения окон, запрещаем имя-терминал в комментарии/коде
# как отдельный early-return path: проверяем, что нет return сразу после
# render_atom_pair compare (маркер legacy-терминала).
t("B4: 0 sales_compare-терминал (render_atom_pair+compare early)",
  "форма compare" not in z20 or "compose+gate" in z20)
# Явный запрет имени терминального маркера из ТЗ
if answer_node is not None:
    sc_calls = [
        n for n in ast.walk(answer_node)
        if isinstance(n, ast.Call) and _call_name(n) == "sales_compare_windows"
    ]
    # вызов для окон допустим; терминал — отдельный early return с render_atom_pair
    rap = [
        n for n in ast.walk(answer_node)
        if isinstance(n, ast.Call) and _call_name(n) == "render_atom_pair"
    ]
    t("B4: 0 render_atom_pair в answer (нет compare-терминала)", not rap, len(rap))
else:
    t("B4: 0 render_atom_pair в answer (нет compare-терминала)", False)

# ── полная (а): clarify только через построитель ─────────────────────────────
if answer_node is not None:
    bare = _bare_clarify_returns(answer_node)
    t("answer: 0 bare return kind=clarify Dict", not bare, bare)
    dict_in_answer = _clarify_dict_assigns_outside_builder(tree, answer_node)
    t("answer: 0 Dict kind=clarify вне builder", not dict_in_answer, dict_in_answer)
    clarify_builders_used = []
    for node in ast.walk(answer_node):
        if isinstance(node, ast.Call) and _is_builder_call(node):
            clarify_builders_used.append(_call_name(node))
    t("answer: readings_menu зовётся",
      "readings_menu" in clarify_builders_used)
    t("readings_menu определён в модуле",
      _func_node(tree, "readings_menu") is not None)
    # все return Call с kind-clarify-путём — либо builder, либо wiki/coverage/
    # calendar (не Dict). Уже покрыто bare Dict=0.
else:
    t("answer: 0 bare return kind=clarify Dict", False, "no answer")
    t("answer: 0 Dict kind=clarify вне builder", False)
    t("answer: readings_menu зовётся", False)
    t("readings_menu определён в модуле", False)

# wiki — единственный выбор сущности
if answer_node is not None:
    wiki_calls = [
        n for n in ast.walk(answer_node)
        if isinstance(n, ast.Call) and _call_name(n) == "wiki_primary_entity_cascade"
    ]
    t("answer зовёт wiki_primary_entity_cascade", len(wiki_calls) >= 1,
      len(wiki_calls))
else:
    t("answer зовёт wiki_primary_entity_cascade", False)

# ── (в) SQL строго до wiki — запрещены ───────────────────────────────────────
if answer_node is not None:
    bad_sql = _sql_calls_before_wiki(answer_node)
    t("answer: 0 SQL_CALLS до wiki_primary", not bad_sql, bad_sql)
else:
    t("answer: 0 SQL_CALLS до wiki_primary", False)

# B4: compose/gate и count_defer на месте
t("compose зовётся в модуле", "compose(" in z20)
t("count_defer_measure_clarify зовётся", "count_defer_measure_clarify" in z20)
t("OUR_PROMPTS содержит WIKI_PICK_SYS", "WIKI_PICK_SYS" in z20)
t("OUR_PROMPTS без CLARIFY_SYS", "CLARIFY_SYS" not in z20
  or "CLARIFY_SYS," not in z20.split("OUR_PROMPTS", 1)[-1][:200])


print()
total = PASS + len(FAIL)
if FAIL:
    print("ПРОВАЛЕНО: %s/%s" % (len(FAIL), total), FAIL)
    sys.exit(1)
print("%s/0 зелёные" % PASS)
sys.exit(0)
