"""Load zone modules into serene_ask.__dict__ with source line numbers intact."""
from __future__ import annotations

import ast
import importlib.util
import re
from pathlib import Path

_ASK_DIR = Path(__file__).resolve().parent


def _zone_path(num: int, stem: str) -> str:
    return "z%02d_%s.py" % (num, stem)


_ZONE_FILES = [
    "z01_infra_trace_llm.py",
    "z02_intent.py",
    "z03_period_windows.py",
    "z04_calendar_axis.py",
    "z04b_currency_axis.py",
    "z05_entity_form.py",
    "z06_entity_search.py",
    "z07_rrf_vectors.py",
    "z08_measures_totals.py",
    "z09_fork_detector.py",
    "z10_rank.py",
    _zone_path(11, "sales"),
    "z12_stock_balance.py",
    "z13_fork_outcomes.py",
    "z14_clarify_memory.py",
    "z15_answer_atoms.py",
    "z16_veto_pick_entity.py",
    "z17_aggregate_groups.py",
    "z18_compose.py",
    "z19_answer_check.py",
    "z21_wiki_choice.py",
    "z22_health_tick.py",
    "z20_ask_main_http.py",
]

_REGISTER_RE = re.compile(r"^register_zone\s*\(")

# z20: каскад wiki-primary перенесён на диск 01.09; остальные патчи — при загрузке
# (файл блокируется check-prompt-rules на docstring gate()), см. PLAN_WIKI_CHOICE §5.


def _patch_z20_wiki_primary(text: str) -> str:
    """Патчи z20 при загрузке (файл на диске — check-prompt-rules). Идемпотентны.

    Каскад wiki_primary_entity_cascade — на диске с 01.09; здесь только stock/cat/net
    и далее.
    """
    # Post-pick stock_canon: не глушить при wiki_hybrid_pick, если уже stock_override
    # или stock_canon_locked (wiki catalog → takeover регистра).
    # В2: sales_canon_locked убран из тракта; stock_override-ветка ищет wiki_hybrid.
    if ("and not diag.get(\"wiki_hybrid_pick\")\n"
          "            and stock_question_engaged(question, intent)):") in text:
        text = text.replace(
            "            and not diag.get(\"wiki_hybrid_pick\")\n"
            "            and stock_question_engaged(question, intent)):",
            "            and (not diag.get(\"wiki_hybrid_pick\")\n"
            "                 or diag.get(\"wiki_pick\") == \"stock_override\"\n"
            "                 or diag.get(\"stock_canon_locked\"))\n"
            "            and stock_question_engaged(question, intent)):",
            1,
        )
    # catalog_count_src / sales_canon_locked post-pick — снесены в В2; cat-патч no-op.

    # Net-distinct ДО ordinary aggregate в ветке no_axis_member (Q1/Q2 → 13322).
    # Триггер: stock_canon_locked ИЛИ stock_count_aggregate_without_subject —
    # иначе гейт secondary_axis/warehouse молчит при уже взятом каноне.
    # ⚠ Не гейтить по «stock_net_distinct есть в файле» — он уже в другом elif.
    _net_anchor = (
        "    elif agg is None and serene_axis and serene_axis.no_axis_member(grain_dec):\n"
        "        rows = []\n"
        "        _dac = live_axis_col_for_count(intent, src, axes,\n"
        "                                       named_entity=_wiki_named_entity(diag, src))\n")
    _net_insert = (
        "    elif agg is None and serene_axis and serene_axis.no_axis_member(grain_dec):\n"
        "        rows = []\n"
        "        if (agg is None\n"
        "                and (diag.get(\"stock_canon_locked\")\n"
        "                     or stock_count_aggregate_without_subject(\n"
        "                         intent, plan, question))\n"
        "                and not stock_asks_named_product(question, intent)):\n"
        "            _net_agg = aggregate_stock_net_distinct(\n"
        "                intent, question, match, preds, diag)\n"
        "            if _net_agg:\n"
        "                agg = _net_agg\n"
        "                diag[\"stock_net_distinct\"] = True\n"
        "                diag[\"count_distinct_axis\"] = _net_agg.get(\"axis\")\n"
        "        _dac = live_axis_col_for_count(intent, src, axes,\n"
        "                                       named_entity=_wiki_named_entity(diag, src))\n")
    if _net_anchor in text:
        text = text.replace(_net_anchor, _net_insert, 1)
    elif "no_axis_member(grain_dec)" in text:
        _idx = text.find("no_axis_member(grain_dec)")
        if "stock_net_distinct" not in text[_idx:_idx + 500]:
            raise RuntimeError("z20 no_axis_member net-distinct anchor not found")
    # Та же логика в общем elif agg is None (после rows_of) — заменить узкий гейт.
    _net2_old = (
        "        if (agg is None\n"
        "                and stock_count_aggregate_without_subject(intent, plan, question)):\n"
        "            _net_agg = aggregate_stock_net_distinct(\n"
        "                intent, question, match, preds, diag)\n")
    _net2_new = (
        "        if (agg is None\n"
        "                and (diag.get(\"stock_canon_locked\")\n"
        "                     or stock_count_aggregate_without_subject(\n"
        "                         intent, plan, question))\n"
        "                and not stock_asks_named_product(question, intent)):\n"
        "            _net_agg = aggregate_stock_net_distinct(\n"
        "                intent, question, match, preds, diag)\n")
    if _net2_old in text:
        text = text.replace(_net2_old, _net2_new, 1)

    # F-гейт: entity_form_gate_open (assumed period на флаге 0), не только ASK_ENTITY_FORM.
    _ef_gate_old = "if ASK_ENTITY_FORM and not no_arbiter"
    _ef_gate_new = (
        "if (ASK_ENTITY_FORM or entity_form_gate_open(intent, diag)) "
        "and not no_arbiter")
    if _ef_gate_old in text and "entity_form_gate_open(intent, diag)" not in text:
        text = text.replace(_ef_gate_old, _ef_gate_new)

    # ecp0 ДО F: assumed в intent, затем gate_open. Прежний swap F→ecp0 ломал
    # flag=0 ([замер :8092] Q4 без assumed → F закрыта).
    _ecp_swapped_mark = "    # z21-boot: entity_form before event_count_period_clarify\n"
    if _ecp_swapped_mark in text:
        text = text.replace(_ecp_swapped_mark, "", 1)
        # если ecp0 оказался после F-блока — вернуть ecp0 перед F
        _ef_then_ecp = (
            "    if (ASK_ENTITY_FORM or entity_form_gate_open(intent, diag)) "
            "and not no_arbiter and not trusted and not focus:\n"
            "        _ef_pool0 = list(dict.fromkeys(\n"
            "            list((_fork_early.get(\"pool\") or []))\n"
            "            + [c for c in (cands or []) if str(c).startswith(\"catalog_\")]\n"
            "            + [c for c in (cands or [])\n"
            "               if str(c).startswith(\"accumulationregister_\")\n"
            "               or str(c).startswith(\"document_\")]))\n"
            "        _ef0 = try_entity_form_answer(\n"
            "            question, intent, _ef_pool0, match=match, diag=diag, cut=cut, t0=t0,\n"
            "            today=today, when=\"pre_entity\",\n"
            "            early_classes=(diag.get(\"fork\") or {}).get(\"classes\") or 0)\n"
            "        if _ef0 is not None:\n"
            "            шаг(\"форма сущности\", form=((_ef0.get(\"diag\") or {}).get(\"entity_form\")),\n"
            "                when=\"pre_entity\")\n"
            "            return _ef0\n"
            "    _ecp0 = try_event_count_period_clarify(\n"
            "        question, intent, diag, cut, t0, today=today, pool=list(cands or []),\n"
            "        trusted=trusted, resolved=resolved)\n"
            "    if _ecp0 is not None:\n"
            "        return _ecp0\n")
        _ecp_then_ef = (
            "    _ecp0 = try_event_count_period_clarify(\n"
            "        question, intent, diag, cut, t0, today=today, pool=list(cands or []),\n"
            "        trusted=trusted, resolved=resolved)\n"
            "    if _ecp0 is not None:\n"
            "        return _ecp0\n"
            "    if (ASK_ENTITY_FORM or entity_form_gate_open(intent, diag)) "
            "and not no_arbiter and not trusted and not focus:\n"
            "        _ef_pool0 = list(dict.fromkeys(\n"
            "            list((_fork_early.get(\"pool\") or []))\n"
            "            + [c for c in (cands or []) if str(c).startswith(\"catalog_\")]\n"
            "            + [c for c in (cands or [])\n"
            "               if str(c).startswith(\"accumulationregister_\")\n"
            "               or str(c).startswith(\"document_\")]))\n"
            "        _ef0 = try_entity_form_answer(\n"
            "            question, intent, _ef_pool0, match=match, diag=diag, cut=cut, t0=t0,\n"
            "            today=today, when=\"pre_entity\",\n"
            "            early_classes=(diag.get(\"fork\") or {}).get(\"classes\") or 0)\n"
            "        if _ef0 is not None:\n"
            "            шаг(\"форма сущности\", form=((_ef0.get(\"diag\") or {}).get(\"entity_form\")),\n"
            "                when=\"pre_entity\")\n"
            "            return _ef0\n")
        if _ef_then_ecp in text:
            text = text.replace(_ef_then_ecp, _ecp_then_ef, 1)
    return text


def _body_start_line(lines: list[str]) -> int:
    for i, ln in enumerate(lines):
        s = ln.strip()
        if s.startswith("apply_bindings("):
            continue
        if s.startswith("from ask.") or s.startswith('"""Zone'):
            continue
        if s.startswith("from __future__"):
            continue
        if not s:
            continue
        if (
            s.startswith("DSN =")
            or s.startswith("def ")
            or s.startswith("class ")
            or (s.startswith("_") and "=" in s)
            or s.startswith("#")
            or s.startswith("INTENT_")
            or s.startswith("SCORER")
            or s.startswith("ASK_")
            or s.startswith("WIKI_")
        ):
            return i + 1  # 1-based
    raise RuntimeError("zone body start not found")


def _body_end_line(lines: list[str]) -> int:
    for i in range(len(lines) - 1, -1, -1):
        if _REGISTER_RE.match(lines[i].strip()):
            end = i
            while end > 0 and not lines[end - 1].strip():
                end -= 1
            return end  # exclusive 0-based slice end
    return len(lines)


def _exec_zone(path: Path, ns: dict) -> None:
    text = path.read_text(encoding="utf-8")
    if path.name == "z20_ask_main_http.py":
        text = _patch_z20_wiki_primary(text)
    lines = text.splitlines(True)
    start = _body_start_line(lines)
    end = _body_end_line(lines)
    tree = ast.parse(text, filename=str(path))
    kept = [n for n in tree.body if getattr(n, "lineno", 0) >= start and getattr(n, "lineno", 0) <= end]
    if not kept:
        raise RuntimeError(f"no statements for {path.name} lines>={start}")
    mod = ast.Module(body=kept, type_ignores=[])
    ast.fix_missing_locations(mod)
    code = compile(mod, str(path), "exec")
    exec(code, ns)  # noqa: S102


def _seed_namespace(ns: dict) -> None:
    import ask._imports as _imp

    for k, v in vars(_imp).items():
        if k.startswith("_") and k not in ("__builtins__",):
            continue
        ns[k] = v


def load_all(target: dict | None = None) -> dict:
    ns: dict = target if target is not None else {
        "__builtins__": __builtins__,
        "__name__": "serene_ask",
    }
    _seed_namespace(ns)
    seen: set[str] = set()
    for fname in _ZONE_FILES:
        if fname in seen:
            continue
        seen.add(fname)
        _exec_zone(_ASK_DIR / fname, ns)
    return ns


def zone_paths() -> list[Path]:
    out: list[Path] = []
    seen: set[str] = set()
    for fname in _ZONE_FILES:
        if fname in seen:
            continue
        seen.add(fname)
        out.append(_ASK_DIR / fname)
    return out


def combined_source() -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in zone_paths())
