#!/usr/bin/env python3
"""Замок «один путь» — полный (а)(б)(в)(г)(д). S2-d / E2.

Читает диск: z20/z21 (+ z05/z12/z14 для silent-контракта).
Не load_all / не pytest / не SQL.
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ASK = ROOT / "ask"
Z20_PATH = ASK / "z20_ask_main_http.py"
Z21_PATH = ASK / "z21_wiki_choice.py"
Z05_PATH = ASK / "z05_entity_form.py"
Z12_PATH = ASK / "z12_stock_balance.py"
Z14_PATH = ASK / "z14_clarify_memory.py"

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

JOURNAL_FUNCS = {
    "_journal_clarify_options", "_journal_doubt", "_journal_ticket_variant",
    "_journal_atoms", "_ask_journal_write", "_ask_journal_row",
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
    "pick_measure",
    "kind_axis_rerank",
    "_fork_atom",
    "arb_pool",
    "entity_form_gate_open",
    "measure_in_kin",
    "apply_period_leader",
    "prefer_window_leader",
    "_ec_atom_fps",
    "try_entity_form",
}

HATCH_NAMES = (
    "measure_hatch", "measure_hatch_B", "measure_hatch_C",
    "_fork_headline", "_fork_headline_measure", "FORK_OTHER_READING",
)

SQL_CALLS = {
    "aggregate",
    "aggregate_groups",
    "rows_of",
    "totals_of",
    "aggregate_stock_net_distinct",
    "aggregate_compare_sales",
    "aggregate_distinct_axis",
    "live_src_counts",
    "tables_of",
}

TICKET_GUARDS = {
    "entity_choice_locked",
    "hold_settled_entity",
}

SECOND_KEYS = frozenset({
    "other_reading", "secondary", "alts", "alt_figures",
    "fork_other", "unsigned", "FORK_OTHER_READING",
})

HOMO_GUARD_MARKERS = (
    "same_label", "homonym", "ambiguous_label", "label_tie",
    "disambiguate_labels", "norm_label", "equal_label",
    "wiki_homonym_kind_peers",
)


def _real_calls(src, sym):
    hits = []
    for m in re.finditer(r"\b%s\b" % re.escape(sym), src):
        line_start = src.rfind("\n", 0, m.start()) + 1
        line = src[line_start:src.find("\n", m.start())]
        code = line.split("#", 1)[0]
        if sym in code:
            hits.append(m.start())
    return hits


def _call_sites(src, sym):
    real = []
    for h in _real_calls(src, sym):
        line_start = src.rfind("\n", 0, h) + 1
        line = src[line_start:src.find("\n", h)]
        code = line.split("#", 1)[0]
        if re.search(r"\b%s\s*\(" % re.escape(sym), code):
            real.append(h)
        elif sym in ("_fork_early",) and re.search(
                r"\b%s\b\s*=" % re.escape(sym), code):
            real.append(h)
    return real


def _func_node(tree, name):
    if tree is None:
        return None
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


def _dict_kind(node):
    if not isinstance(node, ast.Dict):
        return None
    for k, v in zip(node.keys, node.values):
        if k is None:
            continue
        if isinstance(k, ast.Constant) and k.value == "kind":
            if isinstance(v, ast.Constant):
                return v.value
    return None


def _is_clarify_dict(node):
    return isinstance(node, ast.Dict) and _dict_kind(node) == "clarify"


def _parent_map(tree):
    parents = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent
    return parents


def _enclosing_func(parents, node):
    cur = node
    while cur in parents:
        cur = parents[cur]
        if isinstance(cur, ast.FunctionDef):
            return cur
    return None


def _clarify_dict_ok(parents, node):
    fn = _enclosing_func(parents, node)
    if fn is None:
        return False
    if fn.name in ALLOWED_CLARIFY_BUILDERS:
        return True
    if fn.name in JOURNAL_FUNCS:
        return True
    return False


def _second_number_hits(fn_node):
    bad = []
    for n in ast.walk(fn_node):
        if not isinstance(n, ast.Dict):
            continue
        k = _dict_kind(n)
        if k not in ("answer", "figures"):
            continue
        keys = []
        for key in n.keys:
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                keys.append(key.value)
        if any(x in SECOND_KEYS for x in keys):
            bad.append((n.lineno, "second_key"))
        if k == "figures" and "options" in keys:
            bad.append((n.lineno, "figures+options"))
        for key, val in zip(n.keys, n.values):
            if (isinstance(key, ast.Constant) and key.value == "atoms"
                    and isinstance(val, ast.List) and len(val.elts) > 1):
                bad.append((n.lineno, "atoms>1"))
    return bad


def _sql_before_wiki(answer_node):
    wiki_line = None
    for n in ast.walk(answer_node):
        if isinstance(n, ast.Call) and _call_name(n) == "wiki_primary_entity_cascade":
            wiki_line = n.lineno
            break
    ticket_ok = all(
        any(isinstance(n, ast.Call) and _call_name(n) == g
            for n in ast.walk(answer_node))
        for g in TICKET_GUARDS
    )
    if wiki_line is None:
        return ([] if ticket_ok else ["no wiki_primary_entity_cascade"]), None, ticket_ok
    bad = []
    for n in ast.walk(answer_node):
        if isinstance(n, ast.Call) and _call_name(n) in SQL_CALLS:
            if (n.lineno or 0) < wiki_line:
                bad.append("%s@%s" % (_call_name(n), n.lineno))
    return bad, wiki_line, ticket_ok


# ── загрузка ─────────────────────────────────────────────────────────────────
t("новый z20 на диске", Z20_PATH.is_file(), str(Z20_PATH))
t("z21 на диске", Z21_PATH.is_file())
t("z05/z12/z14 на диске",
  Z05_PATH.is_file() and Z12_PATH.is_file() and Z14_PATH.is_file())

z20 = Z20_PATH.read_text(encoding="utf-8") if Z20_PATH.is_file() else ""
z21 = Z21_PATH.read_text(encoding="utf-8") if Z21_PATH.is_file() else ""
z05 = Z05_PATH.read_text(encoding="utf-8") if Z05_PATH.is_file() else ""
z12 = Z12_PATH.read_text(encoding="utf-8") if Z12_PATH.is_file() else ""
z14 = Z14_PATH.read_text(encoding="utf-8") if Z14_PATH.is_file() else ""

z20_tree = z21_tree = z05_tree = z12_tree = z14_tree = None
for label, src, slot in (
    ("z20", z20, "z20_tree"), ("z21", z21, "z21_tree"),
    ("z05", z05, "z05_tree"), ("z12", z12, "z12_tree"),
    ("z14", z14, "z14_tree"),
):
    try:
        tree = ast.parse(src) if src else None
        t("ast.parse %s" % label, tree is not None)
        if label == "z20":
            z20_tree = tree
        elif label == "z21":
            z21_tree = tree
        elif label == "z05":
            z05_tree = tree
        elif label == "z12":
            z12_tree = tree
        else:
            z14_tree = tree
    except SyntaxError as e:
        t("ast.parse %s" % label, False, str(e))

answer = _func_node(z20_tree, "answer")
t("def answer есть", answer is not None)

# ── (г) чёрный список ─────────────────────────────────────────────────────────
for sym in sorted(FORBIDDEN_SELECTORS):
    t("0 call-site %s" % sym, not _call_sites(z20, sym))

for name in HATCH_NAMES:
    t("0 имя %s в z20" % name, name not in z20)

t("B4: 0 max(by в z20", "max(by" not in z20)
t("B4: 0 sales_compare-терминал",
  "форма compare" not in z20 or "compose+gate" in z20)

if answer is not None:
    rap = [
        n for n in ast.walk(answer)
        if isinstance(n, ast.Call) and _call_name(n) == "render_atom_pair"
    ]
    t("B4: 0 render_atom_pair в answer", not rap, len(rap))
else:
    t("B4: 0 render_atom_pair в answer", False)

# ── (г-silent) тройка ─────────────────────────────────────────────────────────
pick_fn = _func_node(z05_tree, "_pick_kind_axis_col")
src_pick = (ast.get_source_segment(z05, pick_fn) or "") if pick_fn else ""
t("z05: _pick_kind_axis_col определён", pick_fn is not None)
t("z05: _pick_kind_axis_col без matched[0]/hits[0]/reranked[0] winner",
  "matched[0]" not in src_pick and "hits[0]" not in src_pick
  and "reranked[0]" not in src_pick)
t("z05: _pick_kind_axis_col при >1 → None|ask",
  "len(matched) > 1" in src_pick or "len(hits) > 1" in src_pick
  or "return None" in src_pick)
t("z05: 0 kind_axis_rerank call", not _call_sites(z05, "kind_axis_rerank"))

pair_fn = _func_node(z12_tree, "stock_net_register_pair")
src_pair = (ast.get_source_segment(z12, pair_fn) or "") if pair_fn else ""
t("z12: stock_net_register_pair определён", pair_fn is not None)
t("z12: stock_net_register_pair без silent sorted_s[0]/max(others)",
  "sorted_s[0]" not in src_pair and "max(others" not in src_pair)

mc = _func_node(z14_tree, "measure_choice")
src_mc = (ast.get_source_segment(z14, mc) or "") if mc else ""
t("z14: measure_choice определён", mc is not None)
t("z14: measure_choice отдаёт ask при >1",
  "'ask'" in src_mc or '"ask"' in src_mc)
t("z14: measure_choice single только при len==1",
  "len(names) == 1" in src_mc)

t("answer: _settle_measure + readings_menu(measure)",
  "_settle_measure" in z20
  and "readings_menu" in z20
  and '"measure"' in z20)

# ── (а) clarify только через builder ──────────────────────────────────────────
if answer is not None:
    bare_ret = [
        n.lineno for n in ast.walk(answer)
        if isinstance(n, ast.Return) and n.value is not None
        and _is_clarify_dict(n.value)
    ]
    t("answer: 0 bare return Dict kind=clarify", not bare_ret, bare_ret)
    bad_dicts = [n.lineno for n in ast.walk(answer) if _is_clarify_dict(n)]
    t("answer: 0 Dict kind=clarify (только builder снаружи)", not bad_dicts)
    used = {
        _call_name(n) for n in ast.walk(answer)
        if isinstance(n, ast.Call) and _call_name(n) in ALLOWED_CLARIFY_BUILDERS
    }
    t("answer: readings_menu зовётся", "readings_menu" in used)
else:
    t("answer: 0 bare return Dict kind=clarify", False)
    t("answer: 0 Dict kind=clarify (только builder снаружи)", False)
    t("answer: readings_menu зовётся", False)

t("readings_menu / clarify_opts_response определены",
  _func_node(z20_tree, "readings_menu") is not None
  and _func_node(z20_tree, "clarify_opts_response") is not None)

if z20_tree is not None:
    parents = _parent_map(z20_tree)
    bad_mod = [
        getattr(n, "lineno", "?")
        for n in ast.walk(z20_tree)
        if _is_clarify_dict(n) and not _clarify_dict_ok(parents, n)
    ]
    t("z20: clarify-Dict только builder|journal", not bad_mod, bad_mod)
else:
    t("z20: clarify-Dict только builder|journal", False)

hybrid = _func_node(z21_tree, "try_wiki_hybrid_entity_pick")
if hybrid is not None:
    z21_bare = [n.lineno for n in ast.walk(hybrid) if _is_clarify_dict(n)]
    t("z21 hybrid: 0 bare Dict kind=clarify", not z21_bare, z21_bare)
    z21_builder = any(
        isinstance(n, ast.Call) and _call_name(n) in ALLOWED_CLARIFY_BUILDERS
        for n in ast.walk(hybrid)
    )
    t("z21 hybrid: зовёт readings_menu|clarify_opts_response", z21_builder)
else:
    t("z21 hybrid: 0 bare Dict kind=clarify", False, "no hybrid")
    t("z21 hybrid: зовёт readings_menu|clarify_opts_response", False)

# ── (б) вторые числа ──────────────────────────────────────────────────────────
for name in HATCH_NAMES:
    t("0 имя %s (б)" % name,
      name not in z20 or not _real_calls(z20, name))

if answer is not None:
    t("answer: 0 render_atom_pair (б)",
      not any(isinstance(n, ast.Call) and _call_name(n) == "render_atom_pair"
              for n in ast.walk(answer)))
    hits = _second_number_hits(answer)
    t("answer/finalize: 0 second-number payload", not hits, hits)
else:
    t("answer: 0 render_atom_pair (б)", False)
    t("answer/finalize: 0 second-number payload", False)

# ── (в) SQL только после wiki ─────────────────────────────────────────────────
if answer is not None:
    bad_sql, wiki_line, ticket_ok = _sql_before_wiki(answer)
    t("answer: wiki_primary зовётся", wiki_line is not None, wiki_line)
    t("answer: ticket-guards на месте", ticket_ok)
    t("answer: 0 SQL_CALLS до wiki_primary", not bad_sql, bad_sql)
else:
    t("answer: wiki_primary зовётся", False)
    t("answer: ticket-guards на месте", False)
    t("answer: 0 SQL_CALLS до wiki_primary", False)

# ── (д) одноимённые ───────────────────────────────────────────────────────────
t("z21: есть guard одноимённых label",
  any(m in z21 for m in HOMO_GUARD_MARKERS))

outcome_fn = _func_node(z21_tree, "wiki_outcome_from_verify")
src_out = (ast.get_source_segment(z21, outcome_fn) or "") if outcome_fn else ""
t("z21: wiki_outcome_from_verify определён", outcome_fn is not None)
t("z21: wiki_homonym_kind_peers вызывается в wiki_outcome_from_verify",
  "wiki_homonym_kind_peers" in src_out)
t("z21: wiki_outcome_from_verify не лидер при label-tie",
  any(m in src_out for m in HOMO_GUARD_MARKERS)
  or "len(passports) == 1" in src_out)

hybrid_src = (ast.get_source_segment(z21, hybrid) or "") if hybrid else ""
t("z21: mk_opts на clarify-tie (различитель вида)",
  "mk_opts" in hybrid_src)

t("z20: label_with_kind / disambiguate_labels живы",
  "def label_with_kind" in z20 and "def disambiguate_labels" in z20)

# ── sanity ────────────────────────────────────────────────────────────────────
t("compose зовётся в модуле", "compose(" in z20)
t("count_defer_measure_clarify зовётся", "count_defer_measure_clarify" in z20)
t("OUR_PROMPTS содержит WIKI_PICK_SYS", "WIKI_PICK_SYS" in z20)
t("OUR_PROMPTS без CLARIFY_SYS",
  "CLARIFY_SYS" not in z20
  or "CLARIFY_SYS," not in z20.split("OUR_PROMPTS", 1)[-1][:200])

# (е) identity-патч bootstrap
boot = (ASK / "_bootstrap.py").read_text(encoding="utf-8")
t("bootstrap: _patch_z20_wiki_primary identity",
  "def _patch_z20_wiki_primary" in boot)
try:
    sys.path.insert(0, str(ROOT))
    from ask._bootstrap import _patch_z20_wiki_primary
    t("патч-функция identity", _patch_z20_wiki_primary(z20) == z20)
except Exception as e:
    t("патч-функция identity", False, str(e))

print()
total = PASS + len(FAIL)
if FAIL:
    print("ПРОВАЛЕНО: %s/%s" % (len(FAIL), total), FAIL)
    sys.exit(1)
print("%s/0 зелёные" % PASS)
sys.exit(0)
