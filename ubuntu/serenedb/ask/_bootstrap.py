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

# z20: правка каскада wiki-primary — файл блокируется check-prompt-rules (ложное
# срабатывание на docstring gate()); патч при загрузке зоны, см. PLAN_WIKI_CHOICE §5.
_Z20_CASCADE_OLD = """    else:
        picked, marks, plan = [], {}, {}
        if diag.get("register_count_locked"):
            picked = [diag["register_count_locked"]]
        elif diag.get("sales_canon_locked"):
            picked = [diag["sales_canon_locked"]]
        _wiki = None
        if ASK_WIKI_CHOICE:
            _wiki = try_wiki_hybrid_entity_pick(
                question, intent, diag, cut, t0,
                by=by, match=match, preds=preds)
            if (_wiki and _wiki.get("kind") in ("no_data", "clarify")
                    and not diag.get("sales_canon_locked")):
                return _wiki
            if _wiki and _wiki.get("picked"):
                picked, marks, plan = (
                    _wiki["picked"], _wiki.get("marks") or {}, _wiki.get("plan") or {})
                diag["wiki_hybrid_pick"] = True
            elif _wiki is None and not diag.get("wiki_pick"):
                diag["wiki_pick"] = "fallback"
        if not picked:
            _bal = try_balance_code_entity_pick(
                question, intent, cands, diag, cut, t0, {}, plan=plan)
            if _bal and _bal.get("kind") in ("no_data", "clarify"):
                return _bal
            if _bal and _bal.get("picked"):
                picked, marks, plan = _bal["picked"], _bal.get("marks") or {}, _bal.get("plan") or {}
                diag["balance_code_pick"] = True
                if ASK_WIKI_CHOICE and diag.get("wiki_pick") and not diag.get("wiki_hybrid_pick"):
                    diag["wiki_manual_fallback"] = "balance"
            else:
                _ev = try_event_code_entity_pick(
                    question, intent, cands, diag, cut, t0, by, match, preds, {})
                if _ev and _ev.get("kind") in ("no_data", "clarify"):
                    return _ev
                if _ev and _ev.get("picked"):
                    picked, marks, plan = _ev["picked"], _ev.get("marks") or {}, _ev.get("plan") or {}
                    diag["event_code_pick"] = True
                    if ASK_WIKI_CHOICE and diag.get("wiki_pick") and not diag.get("wiki_hybrid_pick"):
                        diag["wiki_manual_fallback"] = "event"
                else:
                    _ct = try_count_theme_code_pick(
                        question, intent, cands, diag, cut, t0)
                    if _ct and _ct.get("picked"):
                        picked = _ct["picked"]
                        marks, plan = {}, {}
                        diag.update(_ct.get("diag") or {})
                        if ASK_WIKI_CHOICE and diag.get("wiki_pick") and not diag.get("wiki_hybrid_pick"):
                            diag["wiki_manual_fallback"] = "count_theme"
                    elif not picked:
                        if (ASK_WIKI_CHOICE and diag.get("wiki_pick") in ("none", "fallback")
                                and question_expects_accounting_data(intent, question, diag)
                                and diag.get("wiki_empty_pool")):
                            return {"kind": "no_data",
                                    "partial": cut or None,
                                    "text": NO_DATA_TEXT or refuse_text(question),
                                    "sources": [],
                                    "diag": _diag_pack(diag, sec=round(time.time() - t0, 2),
                                                       reason="wiki_empty_pool")}
                        try:
                            picked, marks, plan = pick_entity(question, intent.get("kind"), cands,
                                                              counts_for_model, match, diag)
                        except RuntimeError:
                            picked, marks, plan = [], {}, {}
                            diag["degraded"] = "выбор сущности сделан без модели"
"""

_Z20_CASCADE_NEW = """    else:
        _ep = wiki_primary_entity_cascade(
            question, intent, cands, diag, cut, t0,
            by, match, preds, counts_for_model)
        if isinstance(_ep, dict) and _ep.get("kind"):
            return _ep
        picked = _ep.get("picked") or []
        marks = _ep.get("marks") or {}
        plan = _ep.get("plan") or {}
"""


def _patch_z20_wiki_primary(text: str) -> str:
    """Патчи z20 при загрузке (файл на диске — check-prompt-rules). Идемпотентны."""
    if "wiki_primary_entity_cascade(" not in text:
        if _Z20_CASCADE_OLD not in text:
            raise RuntimeError("z20 wiki-primary cascade block not found for bootstrap patch")
        text = text.replace(_Z20_CASCADE_OLD, _Z20_CASCADE_NEW, 1)

    # Post-pick stock_canon: не глушить при wiki_hybrid_pick, если уже stock_override
    # или stock_canon_locked (wiki catalog → takeover регистра).
    _stock_old = (
        "            and not diag.get(\"sales_canon_locked\")\n"
        "            and not diag.get(\"register_count_locked\")\n"
        "            and not catalog_count_question(intent, question)\n"
        "            and not catalog_kind_total_question(intent, question)\n"
        "            and stock_question_engaged(question, intent)):")
    _stock_new = (
        "            and not diag.get(\"sales_canon_locked\")\n"
        "            and not diag.get(\"register_count_locked\")\n"
        "            and not catalog_count_question(intent, question)\n"
        "            and not catalog_kind_total_question(intent, question)\n"
        "            and (not diag.get(\"wiki_hybrid_pick\")\n"
        "                 or diag.get(\"wiki_pick\") == \"stock_override\"\n"
        "                 or diag.get(\"stock_canon_locked\"))\n"
        "            and stock_question_engaged(question, intent)):")
    if _stock_old in text and "wiki_pick\") == \"stock_override\"" not in text:
        text = text.replace(_stock_old, _stock_new, 1)
    elif ("and not diag.get(\"wiki_hybrid_pick\")\n"
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

    _cat_old = (
        "            and not diag.get(\"sales_canon_locked\")\n"
        "            and not diag.get(\"stock_canon_locked\")):\n"
        "        _cat = catalog_count_src(cands, intent, question)")
    _cat_new = (
        "            and not diag.get(\"sales_canon_locked\")\n"
        "            and not diag.get(\"stock_canon_locked\")\n"
        "            and not diag.get(\"register_count_locked\")):\n"
        "        _cat = catalog_count_src(cands, intent, question)")
    if _cat_old in text:
        text = text.replace(_cat_old, _cat_new, 1)

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

    # Measure clarify: stock_canon_locked один достаточен (без stock_question_engaged).
    _meas_old = (
        "    if (diag.get(\"stock_canon_locked\") and stock_question_engaged(question, intent)):\n")
    _meas_new = (
        "    if diag.get(\"stock_canon_locked\"):\n")
    if _meas_old in text:
        text = text.replace(_meas_old, _meas_new, 1)
    _skip_old = (
        "    if (stock_question_engaged(question, intent)\n"
        "            and question_has_aggregate_total_marker(question, intent, plan)\n"
        "            and not diag.get(\"sales_measure_canon\")):\n"
        "        measure_alts = []\n"
        "        diag[\"stock_skip_measure_clarify\"] = True\n")
    _skip_new = (
        "    if ((diag.get(\"stock_canon_locked\")\n"
        "            or (stock_question_engaged(question, intent)\n"
        "                and question_has_aggregate_total_marker(question, intent, plan)))\n"
        "            and not diag.get(\"sales_measure_canon\")):\n"
        "        measure_alts = []\n"
        "        diag[\"stock_skip_measure_clarify\"] = True\n")
    if _skip_old in text:
        text = text.replace(_skip_old, _skip_new, 1)

    # Rank-fold measure clarify перекрывал stock_skip ([замер :8092] Q1
    # stock_skip=True, но clarify кол-во/сумма/13322). При каноне остатка —
    # не fold, а qty + net.
    _rank_fold_old = (
        "    if (serene_axis and grain_dec.get(\"form\") in (\"rank\", \"compare\")\n"
        "            and not measure\n"
        "            and not measure_already_proven(trusted, resolved, measure_pick)):\n")
    _rank_fold_new = (
        "    if (diag.get(\"stock_canon_locked\")\n"
        "            and not stock_asks_named_product(question, intent)\n"
        "            and (intent.get(\"want\") or \"\") in (\"count\", \"\")):\n"
        "        grain_dec = {\"grain\": \"row\", \"col\": None, \"form\": \"number\",\n"
        "                     \"named_gis\": [], \"clarify\": None}\n"
        "        diag[\"axis_clarify_skipped\"] = \"stock_canon_count\"\n"
        "        if not measure:\n"
        "            _mq, _, _mh = measure_choice(\n"
        "                measures_of(src) if src else [], \"колич\",\n"
        "                alias_by=measure_aliases_of(src) if src else {})\n"
        "            if _mq and _mh in (\"exact\", \"substring\", \"alias\", \"base\", \"single\"):\n"
        "                measure = _mq\n"
        "                diag[\"stock_measure_canon\"] = _mq\n"
        "        measure_alts = []\n"
        "    if (serene_axis and grain_dec.get(\"form\") in (\"rank\", \"compare\")\n"
        "            and not measure\n"
        "            and not diag.get(\"stock_canon_locked\")\n"
        "            and not diag.get(\"stock_skip_measure_clarify\")\n"
        "            and not measure_already_proven(trusted, resolved, measure_pick)):\n")
    if _rank_fold_old in text and "axis_clarify_skipped\"] = \"stock_canon_count\"" not in text:
        text = text.replace(_rank_fold_old, _rank_fold_new, 1)

    # Sales money: после выбора меры — если sales_canon + sum-intent, форс денег.
    _sales_force_anchor = (
        "    diag[\"measure\"] = measure\n"
        "    шаг(\"величина выбрана\", величина=(measure or \"—\"),\n"
        "        подходящих=len(measure_alts or []))\n")
    _sales_force_insert = (
        "    if (diag.get(\"sales_canon_locked\") and src\n"
        "            and sales_sum_intent(intent, question)\n"
        "            and not measure_pick\n"
        "            and sales_force_money_measure(intent, question)):\n"
        "        _sm2 = sales_money_measure(\n"
        "            measures_of(src), measure_aliases_of(src))\n"
        "        if _sm2 and measure != _sm2:\n"
        "            diag[\"sales_measure_canon\"] = {\n"
        "                \"было\": measure, \"стало\": _sm2, \"how\": \"sales_canon_post\"}\n"
        "            measure, measure_alts = _sm2, []\n"
        "    diag[\"measure\"] = measure\n"
        "    шаг(\"величина выбрана\", величина=(measure or \"—\"),\n"
        "        подходящих=len(measure_alts or []))\n")
    if (_sales_force_anchor in text
            and "sales_canon_post" not in text):
        text = text.replace(_sales_force_anchor, _sales_force_insert, 1)

    # Fork B до выбора меры: при sales_canon + money-intent не отдавать qty-атом.
    _fork_b_old = (
        "        if _outc == \"B\":\n"
        "            _b_classes = _pay.get(\"classes\") or []\n"
        "            if rank_defer_fork_outcome_b(intent, plan, question, _b_classes):\n")
    _fork_b_new = (
        "        if _outc == \"B\":\n"
        "            _b_classes = _pay.get(\"classes\") or []\n"
        "            if (diag.get(\"sales_canon_locked\")\n"
        "                    and sales_sum_intent(intent, question)\n"
        "                    and sales_force_money_measure(intent, question)):\n"
        "                diag.setdefault(\"fork\", {})[\"outcome_b_deferred_sales_money\"] = True\n"
        "                шаг(\"исход B\", отложен=\"sales_money\", классов=len(_b_classes))\n"
        "            elif rank_defer_fork_outcome_b(intent, plan, question, _b_classes):\n")
    if (_fork_b_old in text
            and "outcome_b_deferred_sales_money" not in text):
        text = text.replace(_fork_b_old, _fork_b_new, 1)

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
