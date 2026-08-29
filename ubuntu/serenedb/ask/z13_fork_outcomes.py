"""Zone 13: Исходы развилки (fork-outcomes)."""
from __future__ import annotations

from ask._imports import *
from ask._wire import register_zone, apply_bindings

apply_bindings(globals())

def stock_balance_is_sales_noise(src):
    """Признак «регистр продаж/сверки», не складской остаток (по имени src)."""
    s = (src or "").lower()
    if "книгапродаж" in s:
        return True
    if "актсверки" in s or "reconciliation" in s:
        return True
    if "реализац" in s and s.startswith("accumulationregister_"):
        return True
    return False


def filter_stock_balance_sales_noise(cands, question, diag=None):
    """Негативный отсев: продажи/акт сверки не отвечают на остатки."""
    if not question_asks_stock_balance(question):
        return cands
    out = [c for c in (cands or []) if not stock_balance_is_sales_noise(c)]
    if diag is not None and len(out) < len(cands or []):
        diag["stock_sales_noise_drop"] = sorted(set(cands or []) - set(out))
    return out



def _dedupe_fork_classes(ordered):
    """Одинаковые подпись+атом → одна пара (план §2, п. 13)."""
    seen, out = {}, []
    for it in ordered or []:
        atom = it.get("atom") or {}
        fp = it.get("fingerprint") or ()
        if isinstance(fp, tuple) and fp and not (
                isinstance(fp[0], (list, tuple)) and len(fp[0]) == 2):
            fp_key = fp
        else:
            fp_key = tuple((str(k), v) for k, v in fp)
        key = ((it.get("label") or "").strip(), fp_key,
               atom.get("operation"),
               round(float(atom.get("exact_value")), 2)
               if atom.get("exact_value") is not None else None)
        if key in seen:
            prev = seen[key]
            prev["srcs"] = sorted(set(prev.get("srcs") or []) | set(it.get("srcs") or []))
            continue
        seen[key] = it
        out.append(it)
    return out


# Контракт 23.08 исход C (неподписанные ветки): число лидера + фраза, без имён веток.
FORK_OTHER_READING = "есть другое прочтение"


def _class_window_form(it):
    """interpretation_id окна класса (ось W) — из period/atom, не из прозы."""
    p = (it or {}).get("period") or {}
    if not (p.get("from") or p.get("to") or p.get("interpretation_id")):
        p = ((it or {}).get("atom") or {}).get("period") or {}
    return (p.get("interpretation_id")
            or ((it or {}).get("atom") or {}).get("interpretation_id") or "")


def _class_day_basis(it):
    """day_basis класса (§7bis) — из period/atom, не из прозы."""
    p = (it or {}).get("period") or {}
    if not p.get("day_basis"):
        p = ((it or {}).get("atom") or {}).get("period") or {}
    return (p.get("day_basis")
            or ((it or {}).get("atom") or {}).get("day_basis")
            or (it or {}).get("day_basis") or "").strip()


def fork_leader_class(picked_src, classes, day_basis_prefer=None,
                      amount_basis_prefer=None):
    """Класс лидера люка: эквивалентность, содержащая picked[0] конвейера.

    Не новая лестница — повторное использование победителя шага 4 до детектора.
    Возвращает (leader_item, rest_items) или None, если picked не в live-классе.
    Журнал/разметка: atoms[0] = лидер при порядке [leader] + rest (см. fork_outcome_b).

    Ось W: один src в нескольких классах (mtd vs full_month) — лидер = mtd/wtd
    (фаза B). Ось day-basis (§2.4): среди оставшихся — calendar_days (или ticket).
    Ось amount-basis: doc_amount (status quo) или ticket.
    Без формы окна и без day_basis неоднозначность остаётся None, как раньше.
    """
    src = str(picked_src or "").strip()
    if not src or not classes:
        return None
    matching, rest = [], []
    for it in classes:
        if src in (it.get("srcs") or []):
            matching.append(it)
        else:
            rest.append(it)
    if not matching:
        return None
    if len(matching) == 1:
        return matching[0], rest
    preferred = [it for it in matching
                 if _class_window_form(it) in _WINDOW_LEADER_FORMS]
    pool = preferred if preferred else list(matching)
    prefer_db = (day_basis_prefer if day_basis_prefer in _DAY_BASIS_IDS
                 else _DAY_BASIS_LEADER_DEFAULT)
    has_db = any(_class_day_basis(it) for it in pool)
    if has_db:
        db_pref = [it for it in pool if _class_day_basis(it) == prefer_db]
        if db_pref:
            pool = db_pref
    prefer_ab = (amount_basis_prefer if amount_basis_prefer in _AMOUNT_BASIS_IDS
                 else _AMOUNT_BASIS_LEADER_DEFAULT)
    has_ab = any(_class_amount_basis(it) for it in pool)
    if has_ab:
        ab_pref = [it for it in pool if _class_amount_basis(it) == prefer_ab]
        if ab_pref:
            pool = ab_pref
    if len(pool) == 1:
        leader = pool[0]
        rest2 = [it for it in matching if it is not leader] + rest
        return leader, rest2
    if preferred and not has_db and not has_ab:
        leader = preferred[0]
        rest2 = [it for it in matching if it is not leader] + rest
        return leader, rest2
    if (has_db or has_ab) and pool:
        leader = pool[0]
        rest2 = [it for it in matching if it is not leader] + rest
        return leader, rest2
    return None

def fork_classes_window_only(classes):
    """Исход B: классы различаются только окном W, src одни и те же."""
    items = list(classes or [])
    if len(items) < 2:
        return False
    src_sets = {frozenset(it.get("srcs") or []) for it in items}
    return len(src_sets) == 1 and bool(next(iter(src_sets)))


def rank_defer_fork_outcome_b(intent, plan, question, classes):
    """Rank: исход B по окнам — люк; лидер собирает rank-путь, не сумма периода."""
    return (rank_intent_from(intent, plan, question)
            and fork_classes_window_only(classes))


def ordered_fork_classes(classes, rows, measure_word="", want=None, rel_by_src=None):
    """Классы в детерминированном порядке: по отпечатку атома (не по размеру/лидеру)."""
    rel_by_src = rel_by_src or {}
    meta = getattr(fork_classes, "_meta_by_fp", {}) or {}
    items = []
    for atom_fp, ss in (classes or {}).items():
        srcs = sorted(ss)
        m = meta.get(atom_fp) or {}
        d0 = m.get("row") or ((rows or {}).get(srcs[0]) if srcs else None)
        rep = srcs[0] if srcs else ""
        rel = rel_by_src.get(rep) if rep in rel_by_src else None
        period = m.get("period")
        built = _fork_atom_of(
            d0, srcs, measure_word, want=want, rel_measures=rel, period=period)
        items.append({"fingerprint": atom_fp, "srcs": srcs, "atom": built,
                      "row": d0 or {"count": 0, "folders": 0, "sums": {}},
                      "period": period, "window_fp": m.get("window_fp")})
    items.sort(key=lambda it: (it["fingerprint"], tuple(it["srcs"])))
    return items


def _fork_applicable_classes(ordered):
    """Классы, относящиеся к вопросу: NA (доказанно не относится) не конкурируют."""
    return [it for it in (ordered or [])
            if (it.get("atom") or {}).get("proof_status") != PROOF_NA]


def _fork_complement_outcome_block(intent, question, applicable):
    """Отрицание без complement-атома: позитивное число — не ответ (п.12/13)."""
    if not intent_fact_complement(intent, question):
        return None
    comp = [it for it in (applicable or [])
            if ((it.get("atom") or {}).get("form") or "").lower() == "complement"
            and (it.get("atom") or {}).get("proof_status") == PROOF_COMPUTED
            and (it.get("atom") or {}).get("exact_value") is not None]
    if comp:
        return None
    wrong = [it for it in (applicable or [])
             if (it.get("atom") or {}).get("proof_status") == PROOF_COMPUTED
             and (it.get("atom") or {}).get("exact_value") is not None]
    if not wrong:
        return None
    return "C", {
        "reason": "complement_unresolved",
        "classes": len(applicable or []),
        "positive_misread": [it.get("srcs") for it in wrong],
    }


def resolve_fork_outcome(classes, rows, measure_ctx="", scan_error=None, want=None,
                         rel_by_src=None, today=None, intent=None, question=""):
    """Исход A/B/C/unique/empty/unavailable по классам (план §2). Чистая логика.

    A — один класс, src несколько, все ячейки посчитаны.
    B — классов несколько, все посчитаны и у каждого класса есть подпись (представитель).
    C — иначе (непосчитанное / неподписанное); unique — один класс и один src.
    Статус NA (величина вопроса к источнику не относится) не блокирует A/B.
    """
    if scan_error:
        return "unavailable", {"reason": "scan_error", "detail": str(scan_error)[:160]}
    if not classes:
        return "empty", {"reason": "no_live_cells"}
    ordered = ordered_fork_classes(classes, rows, measure_ctx, want=want,
                                   rel_by_src=rel_by_src)
    applicable = _fork_applicable_classes(ordered)
    if not applicable:
        return "empty", {"reason": "no_applicable_cells",
                         "na_classes": len(ordered)}
    uncounted = [it for it in applicable
                 if (it["atom"] or {}).get("proof_status") != PROOF_COMPUTED
                 or (it["atom"] or {}).get("exact_value") is None]
    if uncounted:
        return "C", {"reason": "uncounted_cell",
                     "classes": len(applicable),
                     "na_classes": len(ordered) - len(applicable),
                     "uncounted": [it["srcs"] for it in uncounted]}
    _comp = _fork_complement_outcome_block(intent, question, applicable)
    if _comp:
        return _comp
    if len(applicable) == 1:
        it = applicable[0]
        if len(it["srcs"]) == 1:
            return "unique", {"class": it}
        return "A", {"class": it, "srcs": it["srcs"]}
    missing, fk_seen = [], None
    for it in applicable:
        lab, fk = _class_label_lookup(it["srcs"], measure_ctx,
                                      atom=it.get("atom"), today=today)
        if fk and not fk_seen:
            fk_seen = fk
        if not lab:
            missing.append(it["srcs"])
        else:
            it["label"] = lab
    applicable = _dedupe_fork_classes(applicable)
    if missing:
        return "C", {"reason": "unsigned_class", "fork_key": fk_seen,
                     "classes": len(applicable),
                     "na_classes": len(ordered) - len(applicable),
                     "unsigned": missing}
    return "B", {"fork_key": fk_seen, "classes": applicable,
                 "na_classes": len(ordered) - len(applicable)}


def _fork_figures_of(atom):
    """Плоские figures из атома класса — без метки источника."""
    if not isinstance(atom, dict):
        return {}
    out = {}
    if atom.get("operation") == "count" or atom.get("measure_id") is None:
        if atom.get("exact_value") is not None:
            out["count"] = atom["exact_value"]
    else:
        if atom.get("exact_value") is not None:
            out["sum"] = atom["exact_value"]
        excl = atom.get("excluded") or {}
        if isinstance(excl, dict) and excl.get("folders") is not None:
            out["folders"] = excl["folders"]
    # P1/P5: compare figures carry base/other/diff explicitly.
    if atom.get("compare_base") is not None:
        out["compare_base"] = atom["compare_base"]
    if atom.get("compare_other") is not None:
        out["compare_other"] = atom["compare_other"]
    if ((atom.get("form") or "").lower() == "compare"
            or (atom.get("operation") or "").lower() == "compare"):
        if atom.get("exact_value") is not None:
            out["diff"] = atom["exact_value"]
    return out


def fork_outcome_a(question, class_item, diag, cut=None, t0=None):
    """Исход A: источник-нейтральный ответ. Src не закреплять (аудит §5.3)."""
    atom = dict((class_item or {}).get("atom") or {})
    atom.pop("src", None)
    # Метка таблицы — производная src; в A её нет (паспорт без src_label).
    mid = atom.get("measure_id")
    if mid:
        atom["measure_label"] = split_ident(mid) or mid
    else:
        atom["measure_label"] = None
    text = render_atom_pair(atom) or (_fmt(atom.get("exact_value"))
                                      if atom.get("exact_value") is not None else "")
    figs = _fork_figures_of(atom)
    d = _diag_pack(diag, fork_outcome="A",
             fork_srcs=list((class_item or {}).get("srcs") or []))
    if t0 is not None:
        d["sec"] = round(time.time() - t0, 2)
    return {"partial": cut or None, "kind": "answer", "text": text,
            "figures": figs, "atom": atom, "atoms": [atom],
            "source_fixed": False, "memory_eligible": False,
            "sources": [], "diag": d}



def fork_outcome_unique(question, class_item, diag, cut=None, t0=None):
    """Исход unique: один класс, один src, atom computed → ответ (K5a).

    Тот же строитель, что исход A (`render_atom_pair`); в diag — `fork_outcome=unique`.
    """
    atom = dict((class_item or {}).get("atom") or {})
    mid = atom.get("measure_id")
    if mid and not (atom.get("measure_label") or "").strip():
        atom["measure_label"] = split_ident(mid) or mid
    text = render_atom_pair(atom) or (_fmt(atom.get("exact_value"))
                                      if atom.get("exact_value") is not None else "")
    if not (text or "").strip():
        return None
    figs = _fork_figures_of(atom)
    srcs = list((class_item or {}).get("srcs") or [])
    tag = ""
    if srcs:
        s0 = srcs[0]
        tag = s0.split("_", 1)[1] if "_" in s0 else s0
    d = _diag_pack(diag, fork_outcome="unique", fork_srcs=srcs)
    if t0 is not None:
        d["sec"] = round(time.time() - t0, 2)
    return {"partial": cut or None, "kind": "answer", "text": text,
            "figures": figs, "atom": atom, "atoms": [atom],
            "source_fixed": False, "memory_eligible": False,
            "sources": [tag] if tag else [], "diag": d}


def _rivals_figures_empty(figures_list):
    """Соперники без ненулевого числового отпечатка (пустые / нули)."""
    if not figures_list:
        return True
    for f in figures_list:
        if not isinstance(f, dict):
            return False
        for k, v in f.items():
            if k in ("in_1c", "in_search", "missing", "_totals", "label") or str(k).startswith("_") or str(k).startswith("date"):
                continue
            if k in ("from", "to", "measure"):
                continue
            try:
                if round(float(v), 2) != 0.0:
                    return False
            except (TypeError, ValueError):
                if v is not None and str(v).strip():
                    return False
    return True


def prefer_mute_computed_over_clarify(mute, picked_src, figures_list,
                                      question="", cut=None, diag=None, t0=None):
    """Mute-лидер с computed atom вместо entity-clarify по пустым соперникам (K5a).

    При выключенном ASK_ATOM_TERMINAL возвращает None.
    """
    if not ASK_ATOM_TERMINAL or not picked_src or not mute:
        return None
    if not _rivals_figures_empty(figures_list):
        return None
    sub = mute.get(picked_src)
    if not isinstance(sub, dict):
        return None
    atom = dict(sub.get("atom") or {})
    if (atom.get("proof_status") != PROOF_COMPUTED
            or atom.get("exact_value") is None):
        return None
    text = render_atom_pair(atom)
    if not (text or "").strip():
        return None
    figs = dict(sub.get("figures") or {}) or _fork_figures_of(atom)
    d = _diag_pack(diag or {}, mute_computed_terminal=picked_src)
    if t0 is not None:
        d["sec"] = round(time.time() - t0, 2)
    return {"partial": cut or sub.get("partial"),
            "kind": "figures", "text": text,
            "figures": figs, "atom": atom, "atoms": [atom],
            "sources": list(sub.get("sources") or []),
            "diag": d}


def atom_terminal_gate_text(atom, question, agg=None):
    """Текст после отклонения прозы гейтом: пара атома или TOTAL_TEXT/refuse (K5b)."""
    if ASK_ATOM_TERMINAL and isinstance(atom, dict):
        if (atom.get("proof_status") == PROOF_COMPUTED
                and atom.get("exact_value") is not None):
            pair = render_atom_pair(atom)
            if pair:
                return pair
    if TOTAL_TEXT and agg is not None and agg.get("sum") is not None:
        return TOTAL_TEXT.format(count=agg.get("count"), sum=_fmt(agg["sum"]))
    return refuse_text(question)



def fork_outcome_b(question, payload, diag, cut=None, t0=None, picked_src=None,
                   day_basis_prefer=None, amount_basis_prefer=None):
    """Исход B: ответ лидера (picked[0]→класс) + люк с остальными ветками."""
    classes = list((payload or {}).get("classes") or [])
    total = len(classes)
    split = fork_leader_class(picked_src, classes,
                              day_basis_prefer=day_basis_prefer,
                              amount_basis_prefer=amount_basis_prefer)
    if split is None:
        return None
    leader_it, rest = split
    shown = [leader_it] + rest
    atoms, opts = [], []
    for it in shown:
        lab = (it.get("label") or "").strip()
        atom = dict(it.get("atom") or {})
        atom.pop("src", None)
        if lab:
            atom["measure_label"] = lab
        atoms.append(atom)
    leader_atom = atoms[0] if atoms else None
    text = render_atom_pair(leader_atom) if leader_atom else None
    if text is None:
        return None
    for it in rest:
        lab = (it.get("label") or "").strip()
        srcs = list(it.get("srcs") or [])
        rep = sorted(srcs)[0] if srcs else ""
        row = it.get("row") or {}
        db = _class_day_basis(it)
        ab = _class_amount_basis(it)
        opt = {"src": (ab or db or rep), "label": lab or rep,
               "found": int(row.get("count") or 0),
               "distinct_by": lab or ""}
        if db:
            opt["day_basis"] = db
        if ab:
            opt["amount_basis"] = ab
        opts.append(opt)
    partial = dict(cut or {})
    d = _diag_pack(diag, fork_outcome="B",
             fork_key=(payload or {}).get("fork_key"),
             fork_classes=total, fork_pairs_shown=len(shown),
             fork_pairs_hidden=None,
             fork_leader_src=str(picked_src or "")[:200] or None)
    if t0 is not None:
        d["sec"] = round(time.time() - t0, 2)
    return {"partial": partial or None, "kind": "figures", "text": text,
            "figures": {"pairs": len(atoms), "pairs_total": total,
                        "pairs_hidden": None},
            "atom": leader_atom, "atoms": atoms,
            "options": opts,
            "source_fixed": False, "memory_eligible": False,
            "sources": [o["label"] for o in opts], "diag": d}


def _fork_question_cyrillic(question):
    return any("\u0400" <= c <= "\u04ff" for c in (question or ""))


def _fork_applicable_ordered(ordered):
    return [it for it in (ordered or [])
            if (it.get("atom") or {}).get("proof_status") != PROOF_NA]


def _fork_clarify_axis_kind(ordered, question, want=None):
    """Тип человеческой оси clarify: measure / place / period или None.

    Из структуры классов развилки и формы вопроса — не из имён таблиц базы.
    """
    items = _fork_applicable_ordered(ordered)
    if len(items) < 2:
        return None
    ops, dims, abs_, dbs, win_period = set(), set(), set(), set(), set()
    for it in items:
        atom = it.get("atom") or {}
        op = (atom.get("operation") or "count").lower()
        ops.add(op)
        row = it.get("row") or {}
        mid = atom.get("measure_id")
        names = list((row.get("sums") or {}).keys())
        if mid and mid not in names:
            names.append(mid)
        if op == "count":
            dims.add("qty")
        elif op == "sum":
            dims.add(_measure_dimension(mid, names=names or None))
        ab = _class_amount_basis(it)
        if ab in _AMOUNT_BASIS_IDS:
            abs_.add(ab)
        db = _class_day_basis(it)
        if db in _DAY_BASIS_IDS:
            dbs.add(db)
        p = it.get("period") or atom.get("period") or {}
        if p.get("from") or p.get("to") or p.get("interpretation_id"):
            win_period.add((p.get("interpretation_id") or "",
                            p.get("from") or "", p.get("to") or ""))
    if len(ops) > 1:
        return "measure"
    if len(dims) > 1 and not (dims <= {"unknown"}):
        return "measure"
    if len(abs_) > 1:
        return "measure"
    if len(dbs) > 1:
        return "period"
    if question_asks_stock_balance(question):
        return "place"
    if len(win_period) > 1:
        return "period"
    _ = want
    return None


def _fork_human_measure_label(atom, question="", row=None, class_item=None):
    """Подпись оси меры: сумма/количество — из operation и роли поля."""
    cyr = _fork_question_cyrillic(question)
    it = class_item or {}
    ab = _class_amount_basis(it)
    if ab in _AMOUNT_BASIS_IDS:
        lab = (it.get("label") or "").strip()
        if lab:
            return lab
        if ab == _AMOUNT_BASIS_DOC:
            return "сумма документа" if cyr else "document amount"
        return "учётная сумма" if cyr else "accounting amount"
    atom = atom or {}
    op = (atom.get("operation") or "count").lower()
    if op == "count":
        return "количество" if cyr else "quantity"
    if op != "sum":
        return ""
    mid = atom.get("measure_id")
    names = list((row or {}).get("sums") or {})
    if mid and mid not in names:
        names.append(mid)
    dim = _measure_dimension(mid, names=names or None)
    if dim == "qty":
        return "количество" if cyr else "quantity"
    unit = (MONEY_UNIT or "").strip()
    if unit:
        return ("сумма (%s)" % unit) if cyr else ("amount (%s)" % unit)
    return "сумма" if cyr else "amount"


def _fork_human_place_label(question=""):
    return "склад" if _fork_question_cyrillic(question) else "warehouse"


def _fork_axis_option_label(axis_kind, it, base_lab, question, today=None):
    """Человеческая подпись варианта: ось + ветка (если есть)."""
    atom = it.get("atom") or {}
    row = it.get("row") or {}
    if axis_kind == "measure":
        axis_lab = _fork_human_measure_label(atom, question, row, class_item=it)
    elif axis_kind == "place":
        axis_lab = _fork_human_place_label(question)
    elif axis_kind == "period":
        db = _class_day_basis(it)
        if db in _DAY_BASIS_IDS and (it.get("label") or "").strip():
            axis_lab = (it.get("label") or "").strip()
        else:
            p = it.get("period") or atom.get("period") or {}
            axis_lab = render_window_label(p, today=today) if p else ""
    else:
        axis_lab = ""
    base = (base_lab or "").strip()
    if axis_lab and base and base.lower() not in axis_lab.lower():
        return "%s — %s" % (axis_lab, base)
    return axis_lab or base


def _fork_clarify_opts(ordered, lab_by, marks, by, match, preds, live,
                       axis_kind, question, today=None):
    """Варианты clarify: по классам развилки, с подписью человеческой оси."""
    applicable = _fork_applicable_ordered(ordered)
    if axis_kind and len(applicable) >= 2:
        marks = marks or {}
        by = by or {}
        live = live or {}
        hints = opts_hints([s for it in applicable for s in (it.get("srcs") or [])])
        opts = []
        for it in applicable:
            srcs = list(it.get("srcs") or [])
            rep = sorted(srcs)[0] if srcs else ""
            db = _class_day_basis(it)
            ab = _class_amount_basis(it)
            base = (it.get("label") or "").strip()
            if not base and rep:
                base = human_table_label(rep, (lab_by or {}).get(rep))
            lab = _fork_axis_option_label(axis_kind, it, base, question, today=today)
            if not lab:
                lab = base or rep
            opt = {"src": ab or db or rep,
                   "label": lab,
                   "hint": hints.get(rep, "") if rep else "",
                   "distinct_by": marks.get(rep, "") if rep else "",
                   "found": live.get(rep, by.get(rep, 0)) if rep else 0}
            if db:
                opt["day_basis"] = db
            if ab:
                opt["amount_basis"] = ab
            opts.append(opt)
        return opts
    srcs = []
    for it in ordered or []:
        srcs.extend(it.get("srcs") or [])
    srcs = list(dict.fromkeys(srcs))
    return mk_opts(srcs, lab_by or {}, marks or {}, by or {}, match=match,
                   preds=preds, live=live)


def fork_outcome_c(question, payload, classes, rows, diag, cut=None, t0=None,
                   lab_by=None, marks=None, by=None, match="", preds=None,
                   picked_src=None, day_basis_prefer=None,
                   amount_basis_prefer=None):
    """Исход C: непосчитанное/неподписанное видно клиенту (п. 13).

    Контракт 23.08 (unsigned): число лидера + FORK_OTHER_READING, без имён веток.
    """
    c_why = (payload or {}).get("reason") or "fork"
    if c_why == "unsigned_class" and picked_src:
        applicable = _fork_applicable_classes(
            ordered_fork_classes(classes, rows))
        split = fork_leader_class(picked_src, applicable,
                                  day_basis_prefer=day_basis_prefer,
                                  amount_basis_prefer=amount_basis_prefer)
        if split is None:
            d = _diag_pack(diag, fork_outcome="C", fork_c_reason="leader_missing")
            if t0 is not None:
                d["sec"] = round(time.time() - t0, 2)
            return {"partial": cut or None, "kind": "unavailable",
                    "text": "Не удалось проверить все прочтения вопроса. "
                            "Повторите запрос.",
                    "sources": [], "retry": True, "diag": d}
        leader_it, _rest = split
        leader_atom = dict(leader_it.get("atom") or {})
        leader_atom.pop("src", None)
        pair = render_atom_pair(leader_atom)
        if pair is None:
            d = _diag_pack(diag, fork_outcome="C", fork_c_reason="leader_render")
            if t0 is not None:
                d["sec"] = round(time.time() - t0, 2)
            return {"partial": cut or None, "kind": "unavailable",
                    "text": "Не удалось проверить все прочтения вопроса. "
                            "Повторите запрос.",
                    "sources": [], "retry": True, "diag": d}
        text = "%s · %s" % (pair, FORK_OTHER_READING)
        partial = dict(cut or {})
        lim = {"reason": c_why}
        if payload.get("unsigned"):
            lim["unsigned_classes"] = len(payload["unsigned"])
        partial["fork_limitation"] = lim
        d = _diag_pack(diag, fork_outcome="C", fork_c_reason=c_why,
                 fork_leader_src=str(picked_src or "")[:200] or None)
        if t0 is not None:
            d["sec"] = round(time.time() - t0, 2)
        return {"partial": partial or None, "kind": "figures", "text": text,
                "atom": leader_atom, "atoms": [leader_atom],
                "options": [],
                "source_fixed": False, "memory_eligible": False,
                "sources": [], "diag": d}
    ordered = ordered_fork_classes(classes, rows)
    srcs = []
    for it in ordered:
        srcs.extend(it["srcs"])
    srcs = list(dict.fromkeys(srcs))
    lab_by = dict(lab_by or {})
    if not lab_by and srcs:
        try:
            lab_by = {r[0]: r[1] for r in psql(
                "SELECT src_table, label FROM %s WHERE src_table IN (%s)"
                % (TABLES, ", ".join(lit(c) for c in srcs))) if r and r[0]}
        except RuntimeError:
            lab_by = {}
    fk = (payload or {}).get("fork_key") or (fork_key_of(srcs, "") if srcs else "")
    flab = fork_labels_of(fk, srcs) if srcs and fk else {}
    for s, lab in flab.items():
        if lab:
            lab_by[s] = lab
    live = {s: ((rows or {}).get(s) or {}).get("count", 0) for s in srcs}
    axis_kind = _fork_clarify_axis_kind(ordered, question)
    opts = _fork_clarify_opts(ordered, lab_by, marks, by, match, preds, live,
                              axis_kind, question)
    partial = dict(cut or {})
    lim = {"reason": c_why}
    if payload.get("unsigned"):
        lim["unsigned_classes"] = len(payload["unsigned"])
    if payload.get("uncounted"):
        lim["uncounted_classes"] = len(payload["uncounted"])
    partial["fork_limitation"] = lim
    d = _diag_pack(diag, fork_outcome="C", fork_c_reason=c_why)
    if axis_kind:
        d["fork_clarify_axis"] = axis_kind
    if t0 is not None:
        d["sec"] = round(time.time() - t0, 2)
    text = clarify_say(question, opts, d) if opts else ""
    if not (text or "").strip() and opts:
        text = ", ".join("«%s»" % (o.get("label") or "") for o in opts)
    if c_why == "uncounted_cell":
        note = "часть прочтений не удалось посчитать"
        text = (text + ("\n" if text else "") + note).strip()
    elif c_why == "unsigned_class":
        note = "есть ветка без проверенной подписи"
        text = (text + ("\n" if text else "") + note).strip()
    elif c_why == "complement_unresolved":
        note = "есть прочтение без формы дополнения"
        text = (text + ("\n" if text else "") + note).strip()
    return {"partial": partial or None, "kind": "clarify", "text": text or "?",
            "options": opts, "sources": [o["label"] for o in opts],
            "diag": d}



register_zone('ask.z13_fork_outcomes', globals())
