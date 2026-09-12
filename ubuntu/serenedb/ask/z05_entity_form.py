"""Zone 05: Форма сущности (entity-form)."""
from __future__ import annotations

from ask._imports import *
from ask._wire import register_zone, apply_bindings

apply_bindings(globals())

# Суперлатив сравнения (больше/меньше/лучше/хуже + всего/всех) — rank, не compare.
_RANK_SUPERLATIVE = re.compile(
    r"(?:^|[\s,.;:!?«\"(\[])(?:больше|меньше|лучше|хуже)\s+(?:всего|всех)\b",
    re.UNICODE | re.IGNORECASE)


def entity_form_rank_single_window(intent, question=""):
    """Гейт B: rank/top-N + одна точка окна (нет period2) — не пара compare.

    Структура intent (amount / rank-текст / top-N>1), не списки сущностей.
    Голый want=list без top-N — не блокирует K4 (сравнение двух окон).
    """
    if not ASK_ENTITY_FORM:
        return False
    intent = intent or {}
    p2 = intent.get("period2") or {}
    if p2.get("from") or p2.get("to"):
        return False
    amt = intent.get("amount") or {}
    if rank_question_text(question):
        return True
    if amt.get("value") is not None:
        try:
            n = int(float(amt["value"]))
            if float(amt["value"]) == float(n) and 1 <= n <= ROWS_TO_MODEL:
                return True
        except (TypeError, ValueError):
            pass
    try:
        if _sales_rank_top_n(intent, {}, question) > 1:
            return True
    except (TypeError, ValueError):
        pass
    return False


# Calendar month name forms (date language, not DB metadata). Longer forms first.
_MONTH_NAME_FORMS = (
    (1, ("января", "январе", "январь", "январ")),
    (2, ("февраля", "феврале", "февраль", "феврал")),
    (3, ("марте", "марта", "март")),
    (4, ("апреля", "апреле", "апрель", "апрел")),
    (5, (" мае", " мая", " май", "мае ", "мая ", "май ")),
    (6, ("июня", "июне", "июнь", "июн")),
    (7, ("июля", "июле", "июль", "июл")),
    (8, ("августа", "августе", "август")),
    (9, ("сентября", "сентябре", "сентябрь", "сентябр")),
    (10, ("октября", "октябре", "октябрь", "октябр")),
    (11, ("ноября", "ноябре", "ноябрь", "ноябр")),
    (12, ("декабря", "декабре", "декабрь", "декабр")),
)


def _months_mentioned(question):
    """Month numbers in question text, first-hit order."""
    q = " " + " ".join(str(question or "").lower().split()) + " "
    hits = []
    for num, forms in _MONTH_NAME_FORMS:
        best = -1
        for form in forms:
            idx = q.find(form)
            if idx >= 0 and (best < 0 or idx < best):
                best = idx
        if best >= 0:
            hits.append((best, num))
    hits.sort()
    out, seen = [], set()
    for _, num in hits:
        if num not in seen:
            seen.add(num)
            out.append(num)
    return out


def _yoy_compare_marker(question):
    """YoY follow-up marker ('a year ago'), not FX rates."""
    q = " ".join(str(question or "").lower().split())
    return any(w in q for w in (
        "год назад", "годом ранее", "годом раньше", "year ago",
        "прошлый год", "прошлого года", " versus year", "vs year"))


def _shift_date_years(d, years):
    """Window edge +/- N years (same as DATE - INTERVAL N YEAR in SereneDB)."""
    try:
        return d.replace(year=d.year + years)
    except ValueError:
        return d.replace(year=d.year + years, day=28)


def _shift_period_years(period, years=-1):
    """Same from/to minus (or plus) N years — interval arithmetic on Python dates."""
    p = period or {}
    out = {}
    fr = _calendar_date(p.get("from")) if p.get("from") else None
    to = _calendar_date(p.get("to")) if p.get("to") else None
    if fr:
        out["from"] = _iso_date(_shift_date_years(fr, years))
    if to:
        out["to"] = _iso_date(_shift_date_years(to, years))
    return out


def sales_compare_split_month_pair(question, today):
    """P4: month-pair marker -> two full calendar months, not glued preds."""
    q = " ".join(str(question or "").lower().split())
    if not any(w in q for w in (
            "против", "сравни", "сравнение", " vs", "vs ", "versus",
            "по сравнению")):
        return None
    months = _months_mentioned(q)
    if len(months) < 2:
        return None
    td = _calendar_date(today) or _calendar_date(time.strftime("%Y-%m-%d"))
    if not td:
        return None
    m1, m2 = months[0], months[1]

    def _full(m):
        y = td.year if m <= td.month else td.year - 1
        start = datetime.date(y, m, 1)
        _s, end = _month_range(start)
        return {"from": _iso_date(start), "to": _iso_date(end)}

    return _full(m1), _full(m2)


def sales_compare_intent(intent, question=""):
    """Two-window sales compare (better/more than), not axis rank.

    [measure 24.08 okna] 'what sold best this week' has 'better' + period ->
    old path went to compare (diff of two WTD), grain=row, no leader name
    when GROUP BY goods has live data. Superlative/top -> rank.

    K2/P2: structural entry — period2 from parse; pair-window markers;
    more/less + prior*/month without required 'than'; YoY follow-up when
    dialog window already filled.
    """
    intent = intent or {}
    q = " ".join(str(question or "").lower().split())
    p1 = intent.get("period") or {}
    p2 = intent.get("period2") or {}
    has_p1 = bool(p1.get("from") or p1.get("to"))
    has_p2 = bool(p2.get("from") or p2.get("to"))
    yoy = _yoy_compare_marker(q)
    # YoY with window (incl. from prior): continue compare even without 'sales' words.
    if not sales_sum_intent(intent, question):
        if not (yoy and has_p1):
            return False
    # Superlative / top-N: axis, not two windows.
    if (_RANK_SUPERLATIVE.search(" " + q + " ")
            or rank_question_text(question)
            or any(w in q for w in (
                "топ-", "топ ", " top", "лидер", "рейтинг", "leader", "ranking"))):
        return False
    _vs = any(w in q for w in (" чем", "чем ", " vs", "против", "по сравнению",
                               "сравни", "сравнение", "насколько", "на сколько",
                               "compared", " versus"))
    _pair_mark = any(w in q for w in (
        "сравни", "сравнение", "против", " vs", "vs ", "versus",
        "по сравнению", "насколько", "на сколько", "compared"))
    _two_windows = (
        has_p2
        or len(_months_mentioned(q)) >= 2
        or ("прошл" in q and any(w in q for w in (
            "эт", "текущ", "этот", "эта ", "это ", "этом", "этой", "эту ",
            "месяц", "недел", "this ", "current")))
        or any(w in q for w in (
            "прошлым месяцем", "прошлый месяц", "прошлого месяца",
            "прошлой недел", "прошлая недел", "прошлой недели")))
    # better/worse + prior/week/month is pair compare, not axis rank (K2 Q6).
    _better_prior = (
        any(w in q for w in ("больше", "меньше", "лучше", "хуже"))
        and ("прошл" in q or _months_mentioned(q)
             or any(w in q for w in ("недел", "месяц", "week", "month"))))
    # Rank does not override YoY / pair / better-prior before structural checks.
    _cmp_over_rank = bool(yoy or (_pair_mark and _two_windows) or _better_prior
                          or (has_p2 and has_p1) or _vs)
    if ASK_ENTITY_FORM:
        if entity_form_rank_single_window(intent, question) and not _cmp_over_rank:
            return False
    elif rank_intent_from(intent, question=question) and not _cmp_over_rank:
        return False
    if has_p2 and has_p1:
        return True
    if yoy:
        return True
    if _pair_mark and _two_windows:
        return True
    if _better_prior:
        return True
    return any(w in q for w in (
        "лучше", "хуже", "больше чем", "меньше чем",
        "больше, чем", "меньше, чем"))


def sales_compare_windows(intent, today, question=""):
    """Two windows for sales compare: current vs prior (week/month by form).

    Returns (period, period2, form_id). Boundaries only — no lexicon.
    Cur = WTD/MTD (from grain start to today). Prior = FULL previous
    calendar period (Mon-Sun week / month 1..last), not clipped to today.day:
    else mid-week/mid-month diff != 'this vs previous' (gold).
    P3: form yoy — prior = same bounds - INTERVAL 1 year (full prior, unclipped).
    P4: two month names + pair marker -> two full calendar months.
    ASK_ENTITY_FORM: period = previous full week/month -> same pair.
    Gate B: rank top-N + one window — leave period point, skip pair.
    """
    td = _calendar_date(today)
    # P4: named month pair — before glue into one preds.
    _split = sales_compare_split_month_pair(question, today)
    if _split:
        return _split[0], _split[1], "explicit"
    if not td:
        p = (intent or {}).get("period") or {}
        p2 = (intent or {}).get("period2") or {}
        return p, p2, "explicit"
    p = dict((intent or {}).get("period") or {})
    fr_d = _calendar_date(p.get("from")) if p.get("from") else None
    to_d = _calendar_date(p.get("to")) if p.get("to") else None
    ms, _me = _month_range(td)
    ws, _we = _week_range_monday(td)
    pws, pwe = _prev_week_range(td)
    if ms.month == 1:
        prev_ms = ms.replace(year=ms.year - 1, month=12, day=1)
    else:
        prev_ms = ms.replace(month=ms.month - 1, day=1)
    _pms, prev_me = _month_range(prev_ms)

    # P3: YoY — cur = question window (or MTD), prior = same bounds - 1 year.
    # Prior is not clipped to today.day (see full-prior comment above).
    if _yoy_compare_marker(question):
        if not (p.get("from") or p.get("to")):
            p = {"from": _iso_date(ms), "to": _iso_date(td)}
        prev = _shift_period_years(p, -1)
        if prev.get("from") or prev.get("to"):
            return p, prev, "yoy"
        return p, {}, "yoy"

    if fr_d and fr_d == ws:
        cur = {"from": _iso_date(ws), "to": _iso_date(td)}
        prev = {"from": _iso_date(pws), "to": _iso_date(pwe)}
        return cur, prev, "wtd"

    if fr_d and fr_d == ms:
        cur = {"from": _iso_date(ms), "to": _iso_date(td)}
        prev = {"from": _iso_date(prev_ms), "to": _iso_date(prev_me)}
        return cur, prev, "mtd"

    # Prior full week/month as sole period -> cur WTD/MTD vs that prior.
    # Same expansion without ASK_ENTITY_FORM (K2 Q1/Q3 on battle flag=0).
    if fr_d and to_d:
        _gate_b = (ASK_ENTITY_FORM
                   and entity_form_rank_single_window(intent, question))
        if _gate_b:
            p2 = dict((intent or {}).get("period2") or {})
            if p2.get("from") or p2.get("to"):
                return p, p2, "explicit"
            return p, {}, "explicit"
        if fr_d == pws and to_d == pwe:
            cur = {"from": _iso_date(ws), "to": _iso_date(td)}
            prev = {"from": _iso_date(pws), "to": _iso_date(pwe)}
            return cur, prev, "wtd"
        if fr_d == prev_ms and to_d == prev_me:
            cur = {"from": _iso_date(ms), "to": _iso_date(td)}
            prev = {"from": _iso_date(prev_ms), "to": _iso_date(prev_me)}
            return cur, prev, "mtd"
        # Named prior month alone while today is later: MTD vs that full month.
        qlow = " ".join(str(question or "").lower().split())
        _cmp_q = any(w in qlow for w in (
            "сравни", "против", "насколько", "на сколько", "больше", "меньше",
            "лучше", "хуже", "чем ", " чем"))
        if _cmp_q and fr_d.day == 1 and to_d == _month_range(fr_d)[1] and fr_d < ms:
            cur = {"from": _iso_date(ms), "to": _iso_date(td)}
            prev = {"from": _iso_date(fr_d), "to": _iso_date(to_d)}
            return cur, prev, "mtd"

    p2 = dict((intent or {}).get("period2") or {})
    if p2.get("from") or p2.get("to"):
        return p, p2, "explicit"
    return p, {}, "explicit"


def entity_form_catalogs_for_kind(kind, allow_meaning=True, *, include_examples=True):
    """catalog_* по основам label/alias; запасной — meaning_candidates.

    allow_meaning=False: только stem/label SQL. Без явного окна F не берёт
    fuzzy meaning (иначе «прайс» → catalog_договоры и distinct чужой оси).

    include_examples=False — НЕ звать best_used_for в совпадение: там лежат
    ПРИМЕРЫ вопросов («сколько часов…», «сколько сотрудников»), и любое
    вопросительное слово матчитось с чужими сущностями как «ось»
    ([замер 01.09 okna] «сколько организаций» → ось «сколько» →
    каталоги нормативов/физлиц → stock_override задушил верифицированного
    лидера). Ось места — имя сущности (label+aliases), пример вопроса осью
    быть не может. Осевые резолвы зовут с False; для kind-резолвов
    умолчание True — прежнее поведение.
    """
    kind = (kind or "").strip()
    if not kind:
        return []
    alias_fields = ("t.label, a.aliases, a.best_used_for"
                    if include_examples else "t.label, a.aliases")
    out = []
    try:
        rs = psql(
            "SELECT t.src_table FROM %s t "
            "LEFT JOIN search_entity_alias a ON a.src_table = t.src_table "
            "WHERE t.src_table LIKE 'catalog_%%' AND list_has_any("
            "  list_filter(ts_lexize(%s, %s), x -> length(x) >= 3),"
            "  list_filter(ts_lexize(%s, concat_ws(' ', %s)),"
            "              x -> length(x) >= 3))"
            % (TABLES, lit(STEM_DICT), lit(kind), lit(STEM_DICT),
               alias_fields))
        out = [r[0] for r in (rs or []) if r and r[0]]
    except RuntimeError:
        out = []
    if out:
        return out
    if not allow_meaning:
        return []
    try:
        found = meaning_candidates([], kind, kind, MEANING_TOP) or []
    except (RuntimeError, ValueError, TypeError):
        found = []
    return [s for s in found if str(s).startswith("catalog_")]


def entity_form_movements_for_kind(kind, allow_meaning=True):
    """document_*/accumulationregister_* по stem/label; запасной — meaning.

    Гейт A: если kind указывает на движение — счёт-цель сам документ/регистр,
    не ось catalog×sales (форма F закрыта).
    """
    kind = (kind or "").strip()
    if not kind:
        return []
    out = []
    try:
        rs = psql(
            "SELECT t.src_table FROM %s t "
            "LEFT JOIN search_entity_alias a ON a.src_table = t.src_table "
            "WHERE (t.src_table LIKE 'document_%%' "
            "    OR t.src_table LIKE 'accumulationregister_%%') "
            "AND list_has_any("
            "  list_filter(ts_lexize(%s, %s), x -> length(x) >= 3),"
            "  list_filter(ts_lexize(%s, concat_ws(' ', t.label, a.aliases, "
            "                                      a.best_used_for)),"
            "              x -> length(x) >= 3))"
            % (TABLES, lit(STEM_DICT), lit(kind), lit(STEM_DICT)))
        out = [r[0] for r in (rs or []) if r and r[0]]
    except RuntimeError:
        out = []
    if out:
        return [s for s in out if not (
            str(s).startswith("accumulationregister_") and sales_noncanon_focus(s))]
    if not allow_meaning:
        return []
    try:
        found = meaning_candidates([], kind, kind, MEANING_TOP) or []
    except (RuntimeError, ValueError, TypeError):
        found = []
    return [s for s in found
            if str(s).startswith("document_")
            or (str(s).startswith("accumulationregister_")
                and not sales_noncanon_focus(s))]


def _kind_axis_col_candidates(ax, axis_word, intent, meaning_ok=True):
    """K9-ф6: кандидаты col по kind/action_axis — без silent winner / rerank.

    Порядок как прежде: каталоги по stem/alias → matched cols; иначе
    kind_axis_hits. При >1 — список для меню выше по тракту.
    """
    axis_word = (axis_word or "").strip()
    ax = [a for a in (ax or []) if a.get("col")]
    if not axis_word or not ax:
        return []
    period = ((intent or {}).get("period") or {})
    has_period = bool(period.get("from") or period.get("to"))
    kind_cats = set(entity_form_catalogs_for_kind(
        axis_word, allow_meaning=has_period))
    if kind_cats:
        matched = [a for a in ax if (a.get("target_src") or "") in kind_cats]
        if matched:
            cols, seen = [], set()
            for a in matched:
                c = a["col"]
                if c not in seen:
                    seen.add(c)
                    cols.append(c)
            return cols
    hits = kind_axis_hits(ax, axis_word, meaning_ok=meaning_ok)
    if not hits:
        return []
    cols, seen = [], set()
    for c in hits:
        if c not in seen:
            seen.add(c)
            cols.append(c)
    return cols


def _pick_kind_axis_col(ax, axis_word, intent, meaning_ok=True):
    """Ровно один кандидат → col; 0 или >1 → None (меню/строки выше)."""
    cands = _kind_axis_col_candidates(ax, axis_word, intent, meaning_ok=meaning_ok)
    if len(cands) == 1:
        return cands[0]
    return None


def live_axis_col_candidates(intent, src, axes=None, named_entity=False):
    """Кандидаты DISTINCT-оси для count — без выбора победителя."""
    intent = intent or {}
    want = (intent.get("want") or "").strip().lower()
    if want not in ("count", ""):
        return []
    ac = (intent.get("action_class") or "none").strip().lower()
    if ac == "object":
        return []
    src = (src or "").strip()
    if not src:
        return []
    pre = src.split("_", 1)[0].lower()
    if pre not in ("document", "accumulationregister"):
        return []
    axis_word = (intent.get("action_axis") or "").strip()
    if not axis_word:
        if named_entity:
            return []
        axis_word = (intent.get("kind") or "").strip()
    if not axis_word:
        return []
    ax = axes if axes is not None else refcols_of(src)
    return _kind_axis_col_candidates(
        ax, axis_word, intent,
        meaning_ok=bool((intent or {}).get("action_class") and
                        (intent or {}).get("action_axis")))


def live_axis_col_for_count(intent, src, axes=None, named_entity=False):
    """want=count + живая ось search_refcols на движении → COUNT(DISTINCT ось).

    Структурно: document_/accumulationregister_ + refcol на kind/action_axis.
    action_class=object — счёт карточек/строк, без DISTINCT. Без списков слов.

    [01.09, ночь] named_entity=True (сущность названа и верифицирована по
    имени): род записей (kind) осью не становится — вопрос о записях названной
    сущности, COUNT идёт по строкам (замер L12: «движений в регистре
    реализациятмц» при верном COUNT=2240 рендерилось «2 · Виды Деятельности» —
    distinct по случайному носителю рода «движения»). Названная человеком ось
    (action_axis) работает и для названной сущности.

    S2-c: ровно один кандидат → взять; >1 → None (меню axis до SQL).
    """
    cands = live_axis_col_candidates(intent, src, axes, named_entity=named_entity)
    return cands[0] if len(cands) == 1 else None


def count_defer_measure_clarify(intent, src, axes=None):
    """K9-ф2: want=count → мера по умолчанию count, не развилка полей (п. 21).

    Переспрос меры только при want=sum и реальной развилке денежных величин.
    Rank с явной осью DISTINCT — прежний defer по live_axis_col_for_count.
    """
    intent = intent or {}
    want = (intent.get("want") or "").strip().lower()
    if want == "sum":
        return False
    if want in ("count", ""):
        if rank_intent_from(intent):
            if not (src or "").strip():
                return False
            # S2-c: defer по наличию кандидатов, не по silent-победителю.
            return bool(live_axis_col_candidates(intent, src, axes))
        return True
    return False


def apply_proven_period(intent, trusted=None, resolved=None):
    """Билет/resolved с period → intent.period (существующий путь preds)."""
    intent = intent if isinstance(intent, dict) else {}
    for prov in (trusted, resolved):
        if not isinstance(prov, dict) or prov.get("period") is None:
            continue
        pr = dict(prov.get("period") or {})
        if pr.get("from") or pr.get("to"):
            intent["period"] = pr
        elif (pr.get("interpretation_id") or "") == "none":
            intent["period"] = {}
        else:
            continue
        parse = dict(intent.get("parse") or {})
        parse["assumed"] = [a for a in (parse.get("assumed") or [])
                            if not str(a).startswith("period.")]
        intent["parse"] = parse
        return True
    return False


def event_path_active(intent):
    return (intent or {}).get("action_class", "").strip().lower() == "event"


def aggregate_distinct_axis(src_table, match, preds, axis_col):
    """COUNT DISTINCT refs_map[axis] в движке.

    Доки: Sql › Functions › Aggregate Functions › DISTINCT Clause in Aggregate
    Functions (count(DISTINCT …)).
    """
    if not src_table or not axis_col:
        return None
    where = [w for w in (
        [match] + list(preds or [])
        + ["src_table = %s" % lit(src_table),
           "map_extract_value(refs_map, %s) IS NOT NULL" % lit(axis_col)]) if w]
    folder_pred = "NOT coalesce(map_extract_value(flags, 'IsFolder'), false)"
    try:
        r = psql(
            "SELECT count(DISTINCT map_extract_value(refs_map, %s)) "
            "FILTER (%s) FROM %s WHERE %s"
            % (lit(axis_col), folder_pred, CORPUS, " AND ".join(where)))
    except RuntimeError:
        return None
    if not r or not r[0] or r[0][0] in ("", None):
        return None
    try:
        n = int(_num(r[0][0]))
    except (TypeError, ValueError):
        return None
    return {"count": n, "sum": None, "src": src_table, "form": "distinct_axis",
            "axis": axis_col, "grain": "axis"}


def aggregate_compare_sales(src, match, period1, period2, measure):
    """Diff двух сумм продаж (form=compare). Один src, два окна."""
    if not src or not measure:
        return None
    a1 = aggregate(src, match, period_preds(period1 or {}), measure)
    a2 = aggregate(src, match, period_preds(period2 or {}), measure)
    if not a1 or not a2:
        return None
    s1, s2 = a1.get("sum"), a2.get("sum")
    if s1 is None or s2 is None:
        return None
    try:
        diff = round(float(s1) - float(s2), 2)
    except (TypeError, ValueError):
        return None
    out = dict(a1)
    out.update({
        "sum": diff,
        "form": "compare",
        "grain": "row",
        "compare_base": s1,
        "compare_other": s2,
        "period2": True,
    })
    return out


register_zone('ask.z05_entity_form', globals())
