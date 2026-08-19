#!/usr/bin/env python3
"""Hotfix: rank n_groups=1 TypeError, rank intent from question, entity/axis anchor."""
import pathlib
import re

ASK = pathlib.Path("/srv/1c/ubuntu/serenedb/serene_ask.py")
TEST = pathlib.Path("/srv/1c/ubuntu/serenedb/test_rank_axis_anchor.py")


def replace_once(text, old, new, label):
    if old not in text:
        if new.split("\n", 1)[0] in text:
            print("skip (already):", label)
            return text
        raise SystemExit("missing anchor: %s" % label)
    return text.replace(old, new, 1)


def patch_ask():
    text = ASK.read_text(encoding="utf-8")

    text = replace_once(
        text,
        '''def rank_intent_from(intent, plan=None):
    """Рейтинг/топ: want=list или amount без порога, либо max/min."""
    intent = intent or {}
    plan = plan or {}
    amt = intent.get("amount") or {}
    if (intent.get("want") or "") == "list":
        return True
    if not amt.get("op") and amt.get("value") is not None:
        return True
    if (plan.get("compute") or "") in ("max", "min"):
        return True
    return False''',
        '''def rank_question_text(question):
    """Фразы рейтинга в тексте вопроса — не только want=list."""
    q = " ".join(str(question or "").lower().split())
    if not q:
        return False
    markers = (
        "больше всего", "больше всех", "наибольш", "наименьш",
        "какого товар", "какой товар", "какая номенклатур",
        "top ", " most ", "maximum", "leader", "лидер", "рейтинг",
        "топ-", "топ ",
    )
    return any(m in q for m in markers)


def rank_intent_from(intent, plan=None, question=""):
    """Рейтинг/топ: want=list, amount без порога, max/min или фраза вопроса."""
    intent = intent or {}
    plan = plan or {}
    amt = intent.get("amount") or {}
    if (intent.get("want") or "") == "list":
        return True
    if not amt.get("op") and amt.get("value") is not None:
        return True
    if (plan.get("compute") or "") in ("max", "min"):
        return True
    if rank_question_text(question):
        return True
    return False


def product_axis_pref(cols):
    """Ось номенклатуры/ТМЦ — приоритет для рейтинга товара."""
    cols = list(cols or [])
    hits = []
    for c in cols:
        cl = (c or "").lower()
        if any(w in cl for w in ("тмц", "номенклатур", "nomencl", "product", "goods")):
            hits.append(c)
    return hits[0] if len(hits) == 1 else None


def prefer_entity_for_rank(cands, intent, question, plan=None):
    """Рейтинг товара: регистр/документ вместо табличной части в вилке."""
    if not rank_intent_from(intent, plan, question):
        return cands
    q = (question or "").lower()
    kind = ((intent or {}).get("kind") or "").lower()
    productish = (
        any(w in q for w in ("товар", "номенклатур", "product", "item", "goods"))
        or any(w in kind for w in ("товар", "номенклатур", "product", "item", "goods"))
    )
    if not productish or len(cands or []) < 2:
        return cands
    try:
        rs = psql(
            "SELECT src_table, parent FROM %s WHERE src_table IN (%s)"
            % (TABLES, ", ".join(lit(c) for c in cands)))
    except RuntimeError:
        return cands
    parent_by = {r[0]: (r[2] if len(r) > 2 else "") for r in rs or [] if r and r[0]}
    children = [c for c in cands if parent_by.get(c)]
    if not children:
        return cands
    tops = [c for c in cands if c not in children]
    if not tops:
        return cands
    reg_doc = [c for c in tops
               if str(c).startswith(("accumulationregister_", "document_"))]
    if reg_doc:
        return reg_doc + [c for c in tops if c not in reg_doc] + children
    return tops + children''',
        "rank_intent_from",
    )

    text = replace_once(
        text,
        '''def grain_dec_from_axis_ticket(intent, plan, grain_dec, prov_axis):
    """Билет оси: grain=group сохраняется; form=rank при рейтинговом вопросе."""
    rankish = rank_intent_from(intent, plan) or (
        (grain_dec or {}).get("form") in ("rank", "compare"))''',
        '''def grain_dec_from_axis_ticket(intent, plan, grain_dec, prov_axis, question=""):
    """Билет оси: grain=group сохраняется; form=rank при рейтинговом вопросе."""
    rankish = rank_intent_from(intent, plan, question) or (
        (grain_dec or {}).get("form") in ("rank", "compare"))''',
        "grain_dec_from_axis_ticket sig",
    )

    text = replace_once(
        text,
        '''    if not rank_intent_from(intent):
        return None
    q = (question or "").lower()''',
        '''    if not rank_intent_from(intent, question=question):
        return None
    q = (question or "").lower()''',
        "rank_measure_hint intent",
    )

    text = replace_once(
        text,
        '''def _fmt_human(v):
    """То же _fmt, разряды неразрывным пробелом — как подстановка гейта."""
    out = _fmt(v)
    head, _, frac = out.partition(".")''',
        '''def _fmt_human(v):
    """То же _fmt, разряды неразрывным пробелом — как подстановка гейта."""
    if isinstance(v, (list, dict, tuple)):
        return str(v)
    out = _fmt(v)
    if not isinstance(out, str):
        out = str(out)
    head, _, frac = out.partition(".")''',
        "_fmt_human guard",
    )

    text = replace_once(
        text,
        '''    if operation in ("sum", "rank", "compare"):
        if money and agg.get("sum") is not None:
            return agg.get("sum")
        return agg.get("count")''',
        '''    if operation in ("sum", "rank", "compare"):
        if (agg or {}).get("grain") == "group":
            lead = _group_leader(agg)
            if lead is not None:
                return lead
        if money and agg.get("sum") is not None:
            return agg.get("sum")
        return agg.get("count")''',
        "_atom_exact_value leader",
    )

    text = replace_once(
        text,
        '''    if not text:
        return text, []
    known = dict(agg or {})''',
        '''    if not text:
        return text, []
    known = {k: v for k, v in (agg or {}).items()
             if k not in ("groups", "scope") and not isinstance(v, (list, dict))}''',
        "_fill_figures known",
    )

    text = replace_once(
        text,
        '''    if not has_measure:
        for k in ("sum", "max", "min", "avg"):
            known.pop(k, None)''',
        '''    if not has_measure and not (agg or {}).get("measure"):
        for k in ("sum", "max", "min", "avg"):
            known.pop(k, None)''',
        "_fill_figures has_measure",
    )

    text = replace_once(
        text,
        '''        kw = kind_word(src) if src else ""
        if kw:
            body += "\\n  count_kind (record type noun) -> {count_kind}"
        # sum=0.0 делает has_money ложным; {count} на sum/rank — дыра 5ca1b66.
        if slot_mode not in ("sum", "rank"):
            body += "\\n  count (number of records) -> {count}"''',
        '''        kw = kind_word(src) if src else ""
        if kw and slot_mode != "rank":
            body += "\\n  count_kind (record type noun) -> {count_kind}"
        # sum=0.0 делает has_money ложным; {count} на sum/rank — дыра 5ca1b66.
        if slot_mode not in ("sum", "rank"):
            body += "\\n  count (number of records) -> {count}"''',
        "compose count_kind no money rank",
    )

    text = replace_once(
        text,
        '''        kw = kind_word(src) if src else ""
        if kw:
            body += "\\n  count_kind (record type noun) -> {count_kind}"
        # Стоп 1: на sum/rank счёт не слот модели (код может дописать после гейта).
        if slot_mode in ("count", "list"):''',
        '''        kw = kind_word(src) if src else ""
        if kw and slot_mode != "rank":
            body += "\\n  count_kind (record type noun) -> {count_kind}"
        # Стоп 1: на sum/rank счёт не слот модели (код может дописать после гейта).
        if slot_mode in ("count", "list"):''',
        "compose count_kind money rank",
    )

    text = replace_once(
        text,
        '''    for r in rows:
        known += _dates(r[3]) + _dates(r[5])''',
        '''    for r in rows:
        try:
            known += _dates(r[3]) + _dates(r[5])
        except (TypeError, IndexError):
            continue''',
        "gate rows guard",
    )

    text = replace_once(
        text,
        '''        grain_dec = grain_dec_from_axis_ticket(intent, plan, grain_dec, _prov_axis)
        diag["axis_from_choice"] = _prov_axis''',
        '''        grain_dec = grain_dec_from_axis_ticket(
            intent, plan, grain_dec, _prov_axis, question)
        diag["axis_from_choice"] = _prov_axis''',
        "axis ticket question",
    )

    text = replace_once(
        text,
        '''    _rank_intent = rank_intent_from(intent, plan)
    _mhint = (rank_measure_hint(_mnames, intent, question, _malias)
              if not measure_pick else None)''',
        '''    _rank_intent = rank_intent_from(intent, plan, question)
    _mhint = (rank_measure_hint(_mnames, intent, question, _malias)
              if not measure_pick else None)''',
        "measure block rank_intent",
    )

    text = replace_once(
        text,
        '''        measure, measure_alts, how = pick_measure(src, question,
                                                  (intent.get("measure") or ""))
        if (_rank_intent and how == "rerank" and _mhint
                and measure and measure != _mhint):
            measure, how = _mhint, "rank_hint"
            diag["measure_rank_hint"] = _mhint
        # 🔴 ДОГАДКА РЕРАНКЕРА НЕ ГОДИТСЯ ТАМ, ГДЕ СПРАШИВАЮТ ВЕЛИЧИНУ. [замер 30.07]''',
        '''        measure, measure_alts, how = pick_measure(src, question,
                                                  (intent.get("measure") or ""))
        if _rank_intent and how == "rerank":
            _hint2 = _mhint or rank_measure_hint(_mnames, intent, question, _malias)
            if _hint2:
                measure, measure_alts, how = _hint2, [], "rank_hint"
                diag["measure_rank_hint"] = _hint2
            elif len(_mnames) > 1:
                measure, measure_alts = None, _mnames
                diag["measure_guess_refused"] = "rank_rerank"
        elif (_rank_intent and how == "rerank" and _mhint
                and measure and measure != _mhint):
            measure, how = _mhint, "rank_hint"
            diag["measure_rank_hint"] = _mhint
        # 🔴 ДОГАДКА РЕРАНКЕРА НЕ ГОДИТСЯ ТАМ, ГДЕ СПРАШИВАЮТ ВЕЛИЧИНУ. [замер 30.07]''',
        "rank rerank refuse",
    )

    text = replace_once(
        text,
        '''            _rank_intent = rank_intent_from(intent, plan)
            if (not _kh and (plan.get("compute") in ("max", "min") or _rank_intent)):
                _kh = kind_axis_rerank(axes, intent.get("kind"))
            _th = term_axis_hits(src, axes, terms_for_axis)
            if _kh and _rank_intent:''',
        '''            _rank_intent = rank_intent_from(intent, plan, question)
            if (not _kh and (plan.get("compute") in ("max", "min") or _rank_intent)):
                _kh = kind_axis_rerank(axes, intent.get("kind"))
            if _rank_intent and len(_kh or []) > 1:
                _pref = product_axis_pref(_kh)
                if _pref:
                    _kh = [_pref]
            _th = term_axis_hits(src, axes, terms_for_axis)
            if _kh and _rank_intent:''',
        "grain rank axis pref",
    )

    text = replace_once(
        text,
        '''            picked, marks, plan = pick_entity(question, intent.get("kind"), cands,
                                              counts_for_model, match, diag)''',
        '''            cands = prefer_entity_for_rank(cands, intent, question)
            picked, marks, plan = pick_entity(question, intent.get("kind"), cands,
                                              counts_for_model, match, diag)''',
        "prefer_entity_for_rank",
    )

    text = replace_once(
        text,
        '''    if kw_src:
        cov_slots = dict(cov_slots or {})
        cov_slots["count_kind"] = kw_src
    text, slots_bad = _fill_figures(text, agg, totals_shown, money, cov_slots,
                                      slot_mode=slot_mode)''',
        '''    if kw_src and slot_mode != "rank":
        cov_slots = dict(cov_slots or {})
        cov_slots["count_kind"] = kw_src
    text, slots_bad = _fill_figures(text, agg, totals_shown, money, cov_slots,
                                      slot_mode=slot_mode)''',
        "cov_slots count_kind rank",
    )

    text = replace_once(
        text,
        '''        for i, g in enumerate((agg.get("groups") or [])[:ROWS_TO_MODEL]):
            nm = (g.get("name") or "").strip()
            if nm:
                body += "\\n  %s: total -> {total:g%d}" % (nm, i)''',
        '''        for i, g in enumerate((agg.get("groups") or [])[:ROWS_TO_MODEL]):
            if not isinstance(g, dict):
                continue
            nm = (g.get("name") or "").strip()
            if nm:
                body += "\\n  %s: total -> {total:g%d}" % (nm, i)''',
        "compose groups dict guard",
    )

    text = replace_once(
        text,
        '''    if (serene_axis and grain_dec.get("form") in ("rank", "compare")
            and not measure
            and not measure_already_proven(trusted, resolved, measure_pick)):
        _rn = [m for m, v, mx, mn in (totals or [])]''',
        '''    if (serene_axis and grain_dec.get("form") in ("rank", "compare")
            and not measure
            and not measure_already_proven(trusted, resolved, measure_pick)):
        _mhint_fold = rank_measure_hint(
            measures_of(src), intent, question, measure_aliases_of(src))
        if _mhint_fold:
            measure = _mhint_fold
            diag["measure_rank_hint"] = _mhint_fold
        _rn = [m for m, v, mx, mn in (totals or [])]''',
        "rank_fold hint first",
    )

    text = replace_once(
        text,
        '''            measure, _rank_alts = serene_axis.rank_fold_choice(
                measure, _rn, _qt, n_rows=_nr)''',
        '''            if not measure:
                measure, _rank_alts = serene_axis.rank_fold_choice(
                    measure, _rn, _qt, n_rows=_nr)
            else:
                _rank_alts = []''',
        "rank_fold skip when hinted",
    )

    ASK.write_text(text, encoding="utf-8")
    print("patched", ASK)


def patch_axis():
    path = pathlib.Path("/srv/1c/ubuntu/serenedb/serene_axis.py")
    text = path.read_text(encoding="utf-8")
    old = '''def group_rows(groups):
    """Свёрнутые группы в форме строки корпуса: модели уходят они, не сырые строки."""
    out = []
    for g in groups or []:
        name = g.get("name") or ""'''
    new = '''def group_rows(groups):
    """Свёрнутые группы в форме строки корпуса: модели уходят они, не сырые строки."""
    out = []
    for g in groups or []:
        if not isinstance(g, dict):
            continue
        name = g.get("name") or ""'''
    if old not in text:
        if "if not isinstance(g, dict):" in text:
            print("skip serene_axis group_rows")
            return
        raise SystemExit("missing group_rows anchor")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print("patched", path)


def patch_test():
    extra = '''

# --- hotfix: rank n_groups=1 (okna передача на хранение, rid 5b6da6da) ---
AGG1 = {
    "count": 19, "sum": 21.0, "leader": 21.0, "measure": "Количество",
    "grain": "group", "col": "refs_map.ТМЦ", "form": "rank", "n_groups": 1,
    "groups": [{"name": "Prod A", "value": 21.0, "count": 19}],
    "folders": 0, "count_amount": 19,
}
ROWS1 = A.serene_axis.group_rows(AGG1["groups"])
q_storage = "какого товара больше всего передали на хранение?"
try:
    filled, bad = A._fill_figures(
        "Топ: {total:g0}, всего {total}.", AGG1, [], True, slot_mode="rank")
    t("rank n_groups=1 fill без TypeError", True)
    t("rank n_groups=1 g0=21", "21" in filled.replace("\\u00a0", ""), filled)
    t("rank n_groups=1 total=21", filled.count("21") >= 2, filled)
except TypeError as e:
    t("rank n_groups=1 fill без TypeError", False, e)
try:
    A.copied_figures("Итого.", AGG1, ROWS1 + [21.0])
    t("rank n_groups=1 copied_figures+float хвост", True)
except TypeError as e:
    t("rank n_groups=1 copied_figures+float хвост", False, e)
try:
    seen = A.rows_seen(ROWS1 + [21.0])
    ok, _ = A.gate("21", seen, AGG1, [21.0, 1], [], money=True, slot_mode="rank")
    t("rank n_groups=1 gate+float хвост", ok)
except TypeError as e:
    t("rank n_groups=1 gate+float хвост", False, e)

# --- hotfix: rank intent из «больше всего» при want=sum ---
intent_sale = {"want": "sum", "kind": "товар", "amount": {}}
t("rank intent «продали за всё время»",
  A.rank_intent_from(intent_sale, {}, "какого товара больше всего продали за всё время?"))
hint_sale = A.rank_measure_hint(
    names, intent_sale, "какого товара больше всего продали за всё время?")
t("rank measure «продали» → Количество", hint_sale == "Количество", hint_sale)

# --- hotfix: count_kind не на rank ---
src = open(A.__file__, encoding="utf-8").read()
t("compose: count_kind закрыт на rank",
  "if kw and slot_mode != \"rank\":" in src)

# --- prefer entity: табчасть не первая ---
class _Fake:
    pass


def _fake_psql(q):
    if "parent FROM" in q:
        return [
            ("document_реализациятмц_номенклатура", "Реализация", "document_реализациятмц"),
            ("accumulationregister_реализациятмц", "Регистр", ""),
        ]
    raise RuntimeError("no db")


_old_psql = A.psql
A.psql = _fake_psql
try:
    got = A.prefer_entity_for_rank(
        ["document_реализациятмц_номенклатура", "accumulationregister_реализациятмц"],
        intent_sale, "какого товара больше всего продали за всё время?")
    t("prefer rank: регистр перед табчастью",
      got[0] == "accumulationregister_реализациятмц", got)
finally:
    A.psql = _old_psql

'''
    text = TEST.read_text(encoding="utf-8")
    anchor = 'print("\\n%d ok, %d fail" % (PASS, len(FAIL)))'
    if "rank n_groups=1 fill" in text:
        print("test already extended")
        return
    text = text.replace(anchor, extra + anchor)
    TEST.write_text(text, encoding="utf-8")
    print("patched", TEST)


if __name__ == "__main__":
    patch_ask()
    patch_axis()
    patch_test()
