# -*- coding: utf-8 -*-
"""Зерно счёта: row | parent | group. Чистые функции — оффлайн-проба без базы.

Три оси ответа — комбинации, не список слов. parent-вперёд (27.07) живёт в
serene_ask (выбор источника) и здесь не повторяется. Здесь — когда объект счёта
есть ссылка строки, а не сама строка.
"""


def rank_k(amount, compute, n_named, rows_to_model=25):
    """K рейтинга: число из amount без порога, иначе LIMIT 1 при max/min, иначе cap."""
    try:
        cap = int(rows_to_model)
    except (TypeError, ValueError):
        cap = 25
    try:
        n_named = int(n_named or 0)
    except (TypeError, ValueError):
        n_named = 0
    if n_named >= 2:
        return n_named
    a = amount or {}
    if not a.get("op") and a.get("value") is not None:
        try:
            n = int(float(a["value"]))
        except (TypeError, ValueError):
            n = None
        if n is not None and float(a["value"]) == float(n) and 1 <= n <= cap:
            return n
    if (compute or "") in ("max", "min") and n_named <= 1:
        return 1
    return cap


def groups_on_same_axis(term_hits):
    """term_hits {gi: [col, ...]} → (col, [gi, ...]) если две+ группы на одной оси."""
    by_col = {}
    for gi, cols in (term_hits or {}).items():
        for c in cols or []:
            by_col.setdefault(c, []).append(gi)
    shared = [(c, gis) for c, gis in by_col.items() if len(set(gis)) >= 2]
    if not shared:
        return None, []
    shared.sort(key=lambda x: (-len(set(x[1])), x[0]))
    col, gis = shared[0]
    return col, sorted(set(gis))


def collapse_and_groups(owners_by_gi):
    """Индексы групп, которые делят owner — члены сравнения, не AND."""
    by_owner = {}
    for gi, owners in (owners_by_gi or {}).items():
        for o in owners or []:
            by_owner.setdefault(o, []).append(gi)
    out, seen = [], set()
    for gis in by_owner.values():
        u = tuple(sorted(set(gis)))
        if len(u) >= 2 and u not in seen:
            seen.add(u)
            out.append(list(u))
    return out


def merge_compare_term_groups(groups, owners_by_gi):
    """Две+ группы с одним owner → одна группа (OR написаний). Остальные как были."""
    groups = list(groups or [])
    sets = collapse_and_groups(owners_by_gi)
    if not sets:
        return groups, []
    skip, merged = set(), []
    for gis in sets:
        alts = []
        for gi in gis:
            if 0 <= gi < len(groups):
                for a in groups[gi]:
                    if a not in alts:
                        alts.append(a)
        if alts:
            merged.append(alts)
        skip.update(gis)
    kept = [g for gi, g in enumerate(groups) if gi not in skip]
    return merged + kept, sets


def decide_grain(axes, kind_hits, term_hits, compute=None, is_child=False,
                 rank_intent=False):
    """Зерно и форма ответа по структуре осей, не по словам «товар»/«топ».

    axes: [{col, target_src}, ...] выбранного источника
    kind_hits: колонки, на которые kind свёл как на target_src
    term_hits: {gi: [col, ...]}
    is_child: источник — табличная часть (parent не пуст)
    rank_intent: want=list или amount без порога — рейтинг, даже если compute пуст (focus)
    """
    axes = list(axes or [])
    cols = []
    for a in axes:
        if isinstance(a, dict):
            cols.append(a.get("col"))
        elif isinstance(a, (list, tuple)) and a:
            cols.append(a[0])
    cols = [c for c in cols if c]
    kind_hits = [c for c in (kind_hits or []) if c in cols]
    same_col, named_gis = groups_on_same_axis(term_hits)
    if same_col and same_col in cols:
        return {"grain": "group", "col": same_col, "form": "compare",
                "named_gis": named_gis, "clarify": None}
    if len(kind_hits) > 1:
        return {"grain": "row", "col": None, "form": "number",
                "named_gis": [], "clarify": "axis"}
    if len(kind_hits) == 1:
        col = kind_hits[0]
        named = [gi for gi, cs in (term_hits or {}).items() if col in (cs or [])]
        if len(named) >= 2:
            form = "compare"
        elif len(named) == 1:
            form = "number"
        else:
            form = "rank"
        return {"grain": "group", "col": col, "form": form,
                "named_gis": named, "clarify": None}
    n_named = len(term_hits or {})
    rankish = (compute or "") in ("max", "min") or rank_intent
    if rankish and n_named == 0:
        if is_child and len(cols) == 1:
            return {"grain": "group", "col": cols[0], "form": "rank",
                    "named_gis": [], "clarify": None}
        if is_child and len(cols) > 1:
            return {"grain": "row", "col": None, "form": "number",
                    "named_gis": [], "clarify": "axis"}
        if rank_intent and not cols:
            # Рейтинг без колонки оси: не grain=row с именем из строки как «лидером».
            return {"grain": "row", "col": None, "form": "rank",
                    "named_gis": [], "clarify": None}
    return {"grain": "row", "col": None, "form": "number",
            "named_gis": [], "clarify": None}


def no_axis_member(dec):
    """form=rank|compare без колонки оси — итог множества, не объект-имя из строки."""
    dec = dec or {}
    return (dec.get("form") in ("rank", "compare")
            and not (dec.get("col") or "").strip())


def rank_fold_choice(measure, names, totals, orders=None, n_rows=None):
    """Рейтинг без выбранного поля: при живых nums у источника fold=count строк молча не берётся.

    Кандидаты — имена полей из nums плюс счёт строк, если он материально другой
    (итоги или порядок групп расходятся). Как measure_ambiguous: разные ответы →
    уточнение. Пустой measure в alts — счёт строк (fold=count), не словарь слов.
    """
    if measure:
        return measure, []
    names = [n for n in (names or []) if n]
    if not names:
        return None, []
    COUNT = ""
    totals = dict(totals or {})
    orders = dict(orders or {})
    candidates = list(names)

    def _tot(m):
        if m == COUNT:
            if n_rows is None:
                return None
            try:
                return float(n_rows)
            except (TypeError, ValueError):
                return None
        try:
            return float(totals.get(m))
        except (TypeError, ValueError):
            return None

    def _ord(m):
        if m not in orders:
            return None
        return tuple(orders[m])

    if n_rows is not None:
        nr = _tot(COUNT)
        different = False
        if nr is None:
            different = True
        else:
            for n in names:
                t = _tot(n)
                if t is None or t != nr:
                    different = True
                o, oc = _ord(n), _ord(COUNT)
                if o is not None and oc is not None and o != oc:
                    different = True
        if different:
            candidates = names + [COUNT]
            totals[COUNT] = n_rows

    if len(candidates) == 1:
        return candidates[0], []
    tot_seen, ord_seen = set(), set()
    for c in candidates:
        tot_seen.add(_tot(c))
        o = _ord(c)
        if o is not None:
            ord_seen.add(o)
    if len(tot_seen) > 1 or len(ord_seen) > 1:
        return None, candidates
    return candidates[0], []


def asks_movement_magnitude(want, measure_word="", amount=None,
                            word_on_holders=False, word_on_catalog=False):
    """Величина движений, а не счёт записей каталога. Без списка слов «справочник».

    want=sum — итог поля. Слово меры совпало с nums держателя — то же.
    Amount без порога — рейтинг (топ-N). Слово меры названо, но его нет в nums
    каталога (чип «сумма»/«топ-5») — не счёт позиций справочника.
    """
    want = want or ""
    word = (measure_word or "").strip()
    amt = amount or {}
    if want == "sum":
        return True
    if word_on_holders:
        return True
    if not amt.get("op") and amt.get("value") is not None:
        return True
    if word and not word_on_catalog:
        return True
    return False


def catalog_self_question(want, asks_movement, catalog_has_measure,
                          holders_have_measure):
    """Каталог — верный источник, только если вопрос про ЕГО записи."""
    want = want or ""
    if want in ("count", "list") and not asks_movement:
        return True
    if catalog_has_measure and not holders_have_measure:
        return True
    return False


def decide_axis_focus(is_axis, catalog_self, live_holders):
    """Что делать с focus, который свелся к target_src оси.

    keep — прежний путь (focus = источник). holder — один живой держатель.
    clarify — несколько, спрашиваем, не no_data по справочнику.
    """
    if not is_axis or catalog_self:
        return ("keep", None)
    live = [h for h in (live_holders or []) if h]
    if len(live) == 1:
        return ("holder", live[0])
    if len(live) > 1:
        return ("clarify", list(live))
    return ("keep", None)


def group_rows(groups):
    """Свёрнутые группы в форме строки корпуса: модели уходят они, не сырые строки."""
    out = []
    for g in groups or []:
        if not isinstance(g, dict):
            continue
        name = g.get("name") or ""
        val = g.get("value")
        n = g.get("count")
        amt = 0 if val is None else val
        head = name
        if n is not None:
            head = "%s | rows=%s" % (name, n)
        if g.get("missing2"):
            head = "%s | period2=empty" % head
        elif g.get("value2") is not None:
            head = "%s | period2=%s" % (head, g["value2"])
        out.append(["", "", amt, "", 0, head])
    return out


def group_values(agg):
    """Числа групп — белый список гейта на зерне group. Row-level max сюда не входит."""
    out = []
    for g in (agg or {}).get("groups") or []:
        for k in ("value", "sum", "count"):
            v = g.get(k)
            if v is None:
                continue
            try:
                out.append(float(v))
            except (TypeError, ValueError):
                pass
    if (agg or {}).get("n_groups") is not None:
        try:
            out.append(float(agg["n_groups"]))
        except (TypeError, ValueError):
            pass
    return out
