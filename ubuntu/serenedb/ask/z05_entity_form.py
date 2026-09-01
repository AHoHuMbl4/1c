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
            "  list_filter(ts_lexize(%s, concat_ws(' ', %s),"
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


def register_count_src(cands, intent, question):
    """Count строк именованного регистра: kind → movement ∩ pool.

    Структурно: entity_form_movements_for_kind + префикс register_*.
    Документ в пуле не перекрывает регистр с тем же kind-stem.
    """
    intent = intent or {}
    want = (intent.get("want") or "").strip().lower()
    if want not in ("count", ""):
        return None
    kind = (intent.get("kind") or "").strip()
    if not kind:
        return None
    if not entity_form_count_target_is_movement(intent, list(cands or [])):
        return None
    period = intent.get("period") or {}
    has_period = bool(period.get("from") or period.get("to"))
    found = entity_form_movements_for_kind(kind, allow_meaning=has_period)
    if not found:
        return None
    pool = set(cands or [])
    regs = [
        s for s in found
        if str(s).startswith((
            "accumulationregister_", "informationregister_", "accountingregister_"))]
    if pool:
        in_pool = [s for s in regs if s in pool]
        if in_pool:
            regs = in_pool
    if not regs:
        return None
    for pref in ("accumulationregister_", "informationregister_",
                 "accountingregister_"):
        hit = [s for s in regs if str(s).startswith(pref)]
        if hit:
            return sorted(hit)[0]
    return sorted(regs)[0]


def entity_form_count_target_is_movement(intent, pool):
    """Гейт A: счёт-цель — движение (kind → document_/accumulationregister_*).

    Структура: intent.kind + классы пула/поиска, не слова вопроса.
    """
    if not ASK_ENTITY_FORM:
        return False
    intent = intent or {}
    want = (intent.get("want") or "").strip().lower()
    if want not in ("count", ""):
        return False
    kind = (intent.get("kind") or "").strip()
    if not kind:
        return False
    raw = [str(s) for s in (pool or [])]
    move_pool = [
        s for s in raw
        if s.startswith("document_")
        or (s.startswith("accumulationregister_") and not sales_noncanon_focus(s))]
    # Явное окно: счёт документов/движений за период — F не подменяет.
    period = intent.get("period") or {}
    has_period = bool(period.get("from") or period.get("to"))
    found = entity_form_movements_for_kind(kind, allow_meaning=has_period)
    if not found:
        return False
    # kind указывает на движение: пересечение с пулом или найденный класс.
    if move_pool and any(s in set(move_pool) for s in found):
        return True
    if any(str(s).startswith("document_") for s in found):
        return True
    if move_pool and any(str(s).startswith("document_") for s in move_pool):
        # в пуле есть document_* и kind резолвится в движение — счёт документов
        return any(
            str(s).startswith("document_") or str(s).startswith("accumulationregister_")
            for s in found)
    return bool(found)


def entity_form_expand_pool(pool, intent=None):
    """Каталоги из kind + sales-держатели осей (search_refcols / основы)."""
    out = list(pool or [])
    seen = set(out)
    kind = ((intent or {}).get("kind") or "").strip()
    if kind:
        for s in entity_form_catalogs_for_kind(kind):
            if s not in seen:
                seen.add(s)
                out.append(s)
    for cat in [s for s in list(out) if str(s).startswith("catalog_")]:
        for h in holders_of_target(cat) or []:
            hs = (h.get("src") or "").strip()
            if not hs.startswith("accumulationregister_"):
                continue
            if sales_noncanon_focus(hs):
                continue
            if hs not in seen:
                seen.add(hs)
                out.append(hs)
    return out


def event_kind_catalog_expand_pool(pool, intent=None):
    """K9-ф9: event+count — kind-каталог → осевые движения в пул до выбора.

    Тот же путь, что `_pick_kind_axis_col` / ф6: `entity_form_catalogs_for_kind`
    (stem/alias из `search_entity_alias`, запасной — meaning_candidates) →
    `holders_of_target` по refcol. Без kind→catalog — пул не меняем.
    """
    pool = list(pool or [])
    if not event_path_active(intent):
        return pool
    want = (intent.get("want") or "").strip().lower()
    if want not in ("count", ""):
        return pool
    axis_word = (intent.get("action_axis") or "").strip()
    if not axis_word:
        axis_word = (intent.get("kind") or "").strip()
    if not axis_word:
        return pool
    period = (intent or {}).get("period") or {}
    has_period = bool(period.get("from") or period.get("to"))
    cats = entity_form_catalogs_for_kind(axis_word, allow_meaning=has_period)
    if not cats:
        return pool
    out = list(pool)
    seen = set(out)
    for cat in cats:
        if cat not in seen:
            seen.add(cat)
            out.append(cat)
        for h in holders_of_target(cat) or []:
            hs = (h.get("src") or "").strip()
            if not hs or hs in seen:
                continue
            pre = hs.split("_", 1)[0].lower()
            if pre not in ("document", "accumulationregister"):
                continue
            if pre == "accumulationregister" and sales_noncanon_focus(hs):
                continue
            seen.add(hs)
            out.append(hs)
    return out


def entity_form_rolling_year(today):
    """Окно «год назад → today» для distinct без явного period (форма границ)."""
    td = _calendar_date(today) or _calendar_date(time.strftime("%Y-%m-%d"))
    if not td:
        return {}
    try:
        start = td.replace(year=td.year - 1)
    except ValueError:
        start = td - datetime.timedelta(days=365)
    return {"from": _iso_date(start), "to": _iso_date(td),
            "origin": _ORIGIN_ASSUMED, "interpretation_id": "rolling_12m"}


def entity_form_gate_open(intent=None, diag=None):
    """True: ASK_ENTITY_FORM=1 или event+count с period.origin=assumed.

    try_event_count_period_clarify на флаге 0 уже пишет rolling_year
    (origin=assumed); без этого гейта F не вызывается и путь уходит в
    event_code_pick ([замер :8092] покупатели → distinct 144 через F).
    """
    if ASK_ENTITY_FORM:
        return True
    intent = intent or {}
    want = (intent.get("want") or "").strip().lower()
    if want not in ("count", ""):
        return False
    if not event_path_active(intent):
        return False
    period = intent.get("period") or {}
    if period.get("origin") == "assumed":
        return True
    if (diag or {}).get("event_count_period_assumed"):
        return True
    return False


def entity_form_applicable(intent, pool):
    """F открыта: want=count + catalog + sales.

    Явное окно — для complement. Distinct без окна — только если в сыром пуле
    уже есть движение (document_/register), иначе «всего клиентов» остаётся
    счётом справочника.
    Гейт A: kind → document_/accumulationregister_* (счёт движения) — F закрыта.
    """
    if not entity_form_gate_open(intent):
        return False
    intent = intent or {}
    want = (intent.get("want") or "").strip().lower()
    if want not in ("count", ""):
        return False
    raw = list(pool or [])
    # Гейт A: счёт-цель — само движение, не ось catalog×sales.
    if entity_form_count_target_is_movement(intent, raw):
        return False
    has_movement = any(
        (str(s).startswith("accumulationregister_") and not sales_noncanon_focus(s))
        or str(s).startswith("document_")
        for s in raw)
    pool = entity_form_expand_pool(raw, intent)
    has_cat = any(str(s).startswith("catalog_") for s in pool)
    has_sales = any(
        str(s).startswith("accumulationregister_") and not sales_noncanon_focus(s)
        for s in pool)
    if not (has_cat and has_sales):
        return False
    period = intent.get("period") or {}
    # Event+count без окна: F всё ещё применима для non-product catalog —
    # entity_form_structs подставит rolling year (distinct_axis). Ранний
    # event_count_period_clarify иначе режет до F/wiki ([замер :8092] Q4).
    # Product-catalog без окна structs сам отсекает — ложного complement нет.
    if period.get("from") or period.get("to"):
        return True
    if event_path_active(intent):
        return bool(has_cat and has_sales)
    return bool(has_movement)


def entity_form_collapse_guard(early_classes=0, arb_pool_len=1,
                               form_applicable=False):
    """Early classes>1 при схлопнутом arb_pool: исход на пуле или метка пропуска."""
    try:
        early_classes = int(early_classes or 0)
        arb_pool_len = int(arb_pool_len or 0)
    except (TypeError, ValueError):
        early_classes, arb_pool_len = 0, 0
    if early_classes <= 1 or arb_pool_len > 1:
        return {"silent_unique": False, "action": "none"}
    if form_applicable:
        return {"silent_unique": False, "action": "resolve_early"}
    return {"silent_unique": False, "action": "skip",
            "fork_outcome_skipped": "arb_pool_collapsed"}


def entity_form_pre_entity_ok(early_classes=0, form_n=1):
    """True: один класс развилки и ровно одна форма по пулу (шаг pre_entity)."""
    try:
        early_classes = int(early_classes or 0)
    except (TypeError, ValueError):
        early_classes = 0
    try:
        form_n = int(form_n if form_n is not None else 0)
    except (TypeError, ValueError):
        form_n = 0
    if early_classes > 1:
        return False
    if form_n != 1:
        return False
    return True


def entity_form_atom_distinct(src="", axis="", value=None, period=None):
    """AnswerAtom формы distinct_axis (COUNT DISTINCT по оси ссылки)."""
    try:
        ev = None if value is None else round(float(value), 2)
    except (TypeError, ValueError):
        ev = value
    return build_answer_atom(
        operation="count", exact_value=ev, measure_id=None,
        measure_label=None, axis=(axis or None), form="distinct_axis",
        proof_status=(PROOF_COMPUTED if ev is not None else PROOF_UNCOUNTED),
        period=period, src=(src or None), grain="axis")


def entity_form_atom_complement(catalog_src="", sales_src="", axis="",
                                catalog_n=None, distinct_n=None, period=None):
    """AnswerAtom формы complement = |catalog| − distinct_axis(sales)."""
    try:
        c = float(catalog_n) if catalog_n is not None else None
        d = float(distinct_n) if distinct_n is not None else None
        ev = None if c is None or d is None else round(c - d, 2)
    except (TypeError, ValueError):
        ev = None
    return build_answer_atom(
        operation="count", exact_value=ev, measure_id=None,
        measure_label=None, axis=(axis or None), form="complement",
        proof_status=(PROOF_COMPUTED if ev is not None else PROOF_UNCOUNTED),
        period=period, src=(sales_src or catalog_src or None), grain="axis",
        excluded=({"catalog": catalog_src, "sales": sales_src,
                   "catalog_n": catalog_n, "distinct_n": distinct_n}
                  if (catalog_src or sales_src) else None))




def _pick_kind_axis_col(ax, axis_word, intent):
    """K9-ф6: kind/action_axis → catalog target_src → col refcols.

    Порядок как entity_form_axis_on_sales / rank_axis_resolve (kind-only):
    каталоги по stem/alias (`entity_form_catalogs_for_kind`), refcol с
    target_src ∈ kind_cats; при нескольких — `kind_axis_rerank`; иначе
    `kind_axis_hits` + rerank; нет соответствия — None.
    """
    axis_word = (axis_word or "").strip()
    ax = [a for a in (ax or []) if a.get("col")]
    if not axis_word or not ax:
        return None
    period = ((intent or {}).get("period") or {})
    has_period = bool(period.get("from") or period.get("to"))
    kind_cats = set(entity_form_catalogs_for_kind(
        axis_word, allow_meaning=has_period))
    if kind_cats:
        matched = [a for a in ax if (a.get("target_src") or "") in kind_cats]
        if matched:
            if len(matched) == 1:
                return matched[0]["col"]
            reranked = kind_axis_rerank(matched, axis_word)
            if reranked:
                return reranked[0]
            return matched[0]["col"]
    hits = kind_axis_hits(ax, axis_word)
    if not hits:
        return None
    if len(hits) == 1:
        return hits[0]
    sub = [a for a in ax if a.get("col") in hits]
    reranked = kind_axis_rerank(sub, axis_word) if sub else []
    return reranked[0] if reranked else hits[0]


def live_axis_col_for_count(intent, src, axes=None):
    """want=count + живая ось search_refcols на движении → COUNT(DISTINCT ось).

    Структурно: document_/accumulationregister_ + refcol на kind/action_axis.
    action_class=object — счёт карточек/строк, без DISTINCT. Без списков слов.
    """
    intent = intent or {}
    want = (intent.get("want") or "").strip().lower()
    if want not in ("count", ""):
        return None
    ac = (intent.get("action_class") or "none").strip().lower()
    if ac == "object":
        return None
    src = (src or "").strip()
    if not src:
        return None
    pre = src.split("_", 1)[0].lower()
    if pre not in ("document", "accumulationregister"):
        return None
    axis_word = (intent.get("action_axis") or "").strip()
    if not axis_word:
        axis_word = (intent.get("kind") or "").strip()
    if not axis_word:
        return None
    ax = axes if axes is not None else refcols_of(src)
    return _pick_kind_axis_col(ax, axis_word, intent)


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
            return bool(live_axis_col_for_count(intent, src, axes))
        return True
    return False


def event_count_has_explicit_period(intent, diag=None):
    """K9-ф8: event+count, окно from/to уже в intent — без assumed-clarify."""
    if not event_path_active(intent):
        return False
    want = (intent.get("want") or "").strip().lower()
    if want not in ("count", ""):
        return False
    if (diag or {}).get("period_assumed_dropped"):
        return False
    p = (intent or {}).get("period") or {}
    return bool(p.get("from") or p.get("to"))


def event_count_period_unspecified(intent, diag=None):
    """K9-ф7: период не назван — пустой intent.period или drop_assumed."""
    if (diag or {}).get("period_assumed_dropped"):
        return True
    p = (intent or {}).get("period") or {}
    return not (p.get("from") or p.get("to"))


def event_count_has_live_axis(intent, src=None, axes=None, pool=None):
    """event+count: есть живая ось DISTINCT на движении (src или пул)."""
    intent = intent or {}
    if not event_path_active(intent):
        return False
    want = (intent.get("want") or "").strip().lower()
    if want not in ("count", ""):
        return False
    if src:
        ax = axes if axes is not None else refcols_of(src)
        return bool(live_axis_col_for_count(intent, src, ax))
    for s in pool or []:
        pre = str(s).split("_", 1)[0].lower()
        if pre not in ("document", "accumulationregister"):
            continue
        try:
            ax = refcols_of(s)
        except RuntimeError:
            ax = []
        if live_axis_col_for_count(intent, s, ax):
            return True
    return False


def event_count_period_clarify_applies(intent, diag=None, src=None, axes=None,
                                       pool=None, trusted=None, resolved=None):
    """K9-ф7: event+count+ось+нет периода → переспрос (не угадывать окно)."""
    if not event_count_has_live_axis(intent, src=src, axes=axes, pool=pool):
        return False
    if not event_count_period_unspecified(intent, diag):
        return False
    for prov in (trusted, resolved):
        if isinstance(prov, dict) and prov.get("period") is not None:
            return False
    return True


def event_count_period_option_readings(today=None):
    """Варианты окна для event-count: месяц/квартал/год/всё — форма дат, не слова."""
    if not today:
        today = time.strftime("%Y-%m-%d")
    td = _calendar_date(today)
    if not td:
        return [_window_reading({}, _ORIGIN_NONE, "none", today)]
    out = []
    ms, me = _month_range(td)
    out.append(_window_reading(
        {"from": _iso_date(ms), "to": _iso_date(me)},
        _ORIGIN_EXPLICIT, "full_month", today))
    qs, qe = _quarter_range(td)
    out.append(_window_reading(
        {"from": _iso_date(qs), "to": _iso_date(qe)},
        _ORIGIN_EXPLICIT, "full_quarter", today))
    ry = entity_form_rolling_year(today)
    if ry.get("from") or ry.get("to"):
        out.append(_window_reading(dict(ry), _ORIGIN_EXPLICIT, "rolling_12m", today))
    out.append(_window_reading({}, _ORIGIN_NONE, "none", today))
    return out


def event_count_period_clarify(question, intent, diag, cut, t0, today=None):
    """Clarify с кнопками-периодами (render_window_label + period в option)."""
    readings = event_count_period_option_readings(today)
    opts = []
    for rd in readings:
        pr = dict(rd.get("period") or {})
        if rd.get("origin"):
            pr["origin"] = rd["origin"]
        if rd.get("interpretation_id"):
            pr["interpretation_id"] = rd["interpretation_id"]
        lab = render_window_label(pr, origin=rd.get("origin"), today=today)
        if not lab:
            lab = str(rd.get("interpretation_id") or "none")
        opts.append({"src": "", "label": lab, "hint": "",
                     "distinct_by": "period", "period": pr,
                     "window_fp": rd.get("window_fp") or ""})
    cyr = any("\u0400" <= c <= "\u04ff" for c in (question or ""))
    text = ("За какой период считать?" if cyr else "Which period?")
    d = dict(diag or {})
    d["event_count_period_clarify"] = True
    return {"partial": cut or None, "kind": "clarify", "text": text,
            "options": opts, "sources": [],
            "diag": _diag_pack(d, sec=round(time.time() - t0, 2),
                               reason="event count: период не назван")}


def try_event_count_period_clarify(question, intent, diag, cut, t0, today=None,
                                   src=None, axes=None, pool=None,
                                   trusted=None, resolved=None):
    """None — не clarify; иначе ответ clarify с period-options.

    Если kind→catalog с держателем-движением — подставляем rolling year
    (assumed) и НЕ clarify. Не зависит от ASK_ENTITY_FORM: иначе при флаге=0
    _ecp0 режет до wiki ([замер :8092] «реально покупают»).
    """
    if not event_count_period_clarify_applies(
            intent, diag, src=src, axes=axes, pool=pool,
            trusted=trusted, resolved=resolved):
        return None
    _sci = globals().get("sales_canon_intent")
    if callable(_sci) and _sci(intent, question, list(pool or [])):
        return None
    if (diag or {}).get("sales_canon_locked"):
        return None
    intent = intent if intent is not None else {}
    ry = entity_form_rolling_year(today)
    if ry.get("from") or ry.get("to"):
        kind = (intent.get("kind") or "").strip()
        axis = (intent.get("action_axis") or "").strip() or kind
        cats = []
        if kind or axis:
            try:
                cats = list(entity_form_catalogs_for_kind(kind or axis) or [])
            except RuntimeError:
                cats = []
        has_holder = False
        for cat in cats:
            try:
                holders = holders_of_target(cat) or []
            except RuntimeError:
                holders = []
            for h in holders:
                hs = (h.get("src") or "").strip()
                if hs.startswith("accumulationregister_") and not sales_noncanon_focus(hs):
                    has_holder = True
                    break
            if has_holder:
                break
        if not has_holder:
            for s in list(pool or []) + ([src] if src else []):
                if (str(s).startswith("accumulationregister_")
                        and not sales_noncanon_focus(str(s))):
                    has_holder = True
                    break
        if has_holder:
            intent["period"] = dict(ry)
            intent["period"]["origin"] = "assumed"
            if diag is not None:
                diag["event_count_period_assumed"] = "rolling_year"
            return None
    return event_count_period_clarify(
        question, intent, diag, cut, t0, today=today)


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


def event_duel_applies(intent, pool):

    """K9-ф5: event+count+>=2 осевых движений -> fork A/B/C, не clarify сущности."""
    if not event_path_active(intent) or len(pool or []) < 2:
        return False
    want = (intent.get("want") or "").strip().lower()
    if want not in ("count", ""):
        return False
    n_axis = 0
    for src in pool:
        try:
            ax = refcols_of(src)
        except RuntimeError:
            ax = []
        if live_axis_col_for_count(intent, src, ax):
            n_axis += 1
    return n_axis >= 2


def _event_distinct_fork_rows(intent, match, preds, rows, rel_by_src):
    """K9-ф5: event+count+ось -> COUNT(DISTINCT) в fork_scan для исходов A/B/C."""
    if not event_path_active(intent):
        return rows
    want = (intent.get("want") or "").strip().lower()
    if want not in ("count", ""):
        return rows
    out = dict(rows or {})
    for src in list(rel_by_src or {}):
        if src not in out:
            continue
        try:
            axes = refcols_of(src)
        except RuntimeError:
            axes = []
        col = live_axis_col_for_count(intent, src, axes)
        if not col:
            continue
        agg = aggregate_distinct_axis(src, match, preds, col)
        if not agg or agg.get("count") is None:
            continue
        ax_lab = _passport_axis_label(col, axes)
        d = dict(out[src])
        d["count"] = agg["count"]
        d["distinct_axis"] = col
        d["distinct_axis_label"] = ax_lab
        out[src] = d
    return out


def event_path_active(intent):
    return (intent or {}).get("action_class", "").strip().lower() == "event"


def event_movement_feats(diag):
    return (diag or {}).get("answer_fit_v2_full") or {}


def event_filter_pool(cands, intent, diag):
    if not event_path_active(intent) or not K6R:
        return list(cands or [])
    return K6R.event_movement_pool(cands, event_movement_feats(diag), intent)


def try_event_code_entity_pick(question, intent, cands, diag, cut, t0, by, match, preds,
                               marks):
    if not event_path_active(intent) or not K6R:
        return None
    feats = event_movement_feats(diag)
    if not feats:
        return None
    leader, tied = K6R.event_rank_pick(cands, feats, intent, question)
    if leader:
        diag["event_code_lock"] = leader
        return {"picked": [leader], "marks": marks or {}, "plan": {}}
    pool = K6R.event_movement_pool(cands, feats, intent)
    if not pool:
        diag["event_code_empty_pool"] = True
        if K6R.event_movement_any(cands):
            return None
        return {"kind": "no_data",
                "partial": cut or None,
                "text": NO_DATA_TEXT or refuse_text(question),
                "sources": [],
                "diag": _diag_pack(diag, sec=round(time.time() - t0, 2),
                                   reason="event_no_axis_movement")}
    if tied:
        if event_duel_applies(intent, tied):
            form = K6R.infer_rank_form(intent, question) if K6R else "distinct"
            pos = {s: i for i, s in enumerate(cands or [])}
            ordered = sorted(
                tied,
                key=lambda s: K6R.rank_key_v2(
                    s, feats.get(s), intent, form, pos.get(s, 10**6))
                if K6R else s)
            diag["event_duel_pool"] = list(ordered)
            diag["event_code_lock"] = ordered[0]
            return {"picked": ordered, "marks": marks or {}, "plan": {}}
        try:
            lab_by = {r[0]: r[1] for r in psql(
                "SELECT src_table, label FROM %s WHERE src_table IN (%s)"
                % (TABLES, ", ".join(lit(c) for c in tied))) if r and r[0]}
        except RuntimeError:
            lab_by = {}
        opts = mk_opts([t for t in tied if t in lab_by], lab_by, marks or {}, by,
                       match=match, preds=preds)
        if len(opts) >= 2:
            diag["event_code_tie"] = tied
            return {"partial": cut or None, "kind": "clarify",
                    "text": clarify_say(question, opts, diag)
                            or ", ".join("«%s»" % o["label"] for o in opts),
                    "options": opts, "sources": [o["label"] for o in opts],
                    "diag": _diag_pack(diag, sec=round(time.time() - t0, 2))}
    diag["event_code_ambiguous"] = tied or pool[:4]
    return {"kind": "no_data",
            "partial": cut or None,
            "text": NO_DATA_TEXT or refuse_text(question),
            "sources": [],
            "diag": _diag_pack(diag, sec=round(time.time() - t0, 2),
                               reason="event_rank_tie")}


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


def entity_form_axis_on_sales(catalog_src, sales_srcs):
    """Ось refs_map на sales, чей target_src = catalog (search_refcols).

    Среди держателей — канон продаж по _sales_register_score (не книга/импорт).
    """
    catalog_src = (catalog_src or "").strip()
    sales_srcs = [s for s in (sales_srcs or []) if s]
    if not catalog_src or not sales_srcs:
        return None, None
    pairs = []
    for s in sales_srcs:
        for a in (refcols_of(s) or []):
            if (a.get("target_src") or "") == catalog_src and a.get("col"):
                pairs.append((s, a["col"]))
                break
    if not pairs:
        for h in holders_of_target(catalog_src) or []:
            if h.get("src") in sales_srcs and h.get("col"):
                pairs.append((h["src"], h["col"]))
    if not pairs:
        return None, None
    mbs = {}
    try:
        mbs = _measures_by_src([s for s, _c in pairs]) or {}
    except RuntimeError:
        mbs = {}
    pairs.sort(key=lambda sc: (
        -_sales_register_score(sc[0], mbs.get(sc[0]) or []),
        sc[0]))
    return pairs[0][0], pairs[0][1]


def entity_form_structs(intent, pool, today=None):
    """Все структурные кандидаты F по пулу (form+meta), без SQL-счёта.

    Порядок как у entity_form_pick: сырой пул, затем kind. Нужен для
    pre_entity: «форма по пулу не единственная» = len>1.
    """
    if not entity_form_applicable(intent, pool):
        return []
    raw = list(pool or [])
    raw_set = set(raw)
    period0 = dict((intent or {}).get("period") or {})
    has_period0 = bool(period0.get("from") or period0.get("to"))
    pool = entity_form_expand_pool(raw, intent)
    cats = [s for s in pool if str(s).startswith("catalog_")]
    sales = [s for s in pool
             if str(s).startswith("accumulationregister_")
             and not sales_noncanon_focus(s)]
    period = dict(period0)
    has_period = has_period0
    kind = ((intent or {}).get("kind") or "").strip()
    # Без окна — только stem/label SQL; meaning оставляем для complement с окном.
    found = set(entity_form_catalogs_for_kind(
        kind, allow_meaning=has_period0)) if kind else set()
    # Без окна: только kind→catalog. Dump соседних catalog_* не повод для F.
    if not has_period:
        if not found:
            return []
        cats = [c for c in cats if c in found]
        if not cats:
            return []
        # kind → товарный catalog: счёт строк справочника, не DISTINCT sales
        if all(_is_product_catalog(c) for c in cats):
            return []
    # сначала каталоги из сырого пула/cands, затем совпавшие с kind
    cats.sort(key=lambda c: (
        0 if c in raw_set else 1,
        0 if c in found else 1,
        c))
    out = []
    for cat in cats:
        src_s, axis = entity_form_axis_on_sales(cat, sales)
        if not src_s or not axis:
            continue
        if _is_product_catalog(cat):
            if not has_period:
                continue
            out.append(("complement", {
                "catalog_src": cat, "sales_src": src_s, "axis": axis,
                "period": dict(period)}))
            continue
        per = dict(period)
        if not has_period:
            per = entity_form_rolling_year(today)
            if not (per.get("from") or per.get("to")):
                continue
        out.append(("distinct_axis", {
            "catalog_src": cat, "sales_src": src_s, "axis": axis,
            "period": per}))
    return out


def entity_form_pick(intent, pool, today=None):
    """Выбрать (form, meta) из структуры пула: complement | distinct_axis | None.

    Без явного окна F смотрит только catalog, на который указывает kind
    (не весь dump развилки): иначе счёт справочника уходит в distinct по
    соседней оси, которую держат те же строки sales.
    """
    structs = entity_form_structs(intent, pool, today=today)
    if not structs:
        return None, {}
    return structs[0][0], structs[0][1]


def entity_form_compute(form, meta, match=""):
    """Посчитать атом выбранной формы F внутри движка."""
    if not form or not meta:
        return None
    period = meta.get("period") or {}
    preds = period_preds(period) if (period.get("from") or period.get("to")) else []
    axis = meta.get("axis") or ""
    sales = meta.get("sales_src") or ""
    cat = meta.get("catalog_src") or ""
    if form == "distinct_axis":
        agg = aggregate_distinct_axis(sales, match, preds, axis)
        if not agg:
            return None
        try:
            _ax_cols = refcols_of(sales)
        except RuntimeError:
            _ax_cols = []
        _ax_lab = _passport_axis_label(axis, _ax_cols) or axis
        return entity_form_atom_distinct(
            src=sales, axis=_ax_lab, value=agg.get("count"), period=period)
    if form == "complement":
        cat_agg = aggregate(cat, "", [], None)  # каталог без date-pred
        dist = aggregate_distinct_axis(sales, match, preds, axis)
        if not cat_agg or dist is None:
            return None
        return entity_form_atom_complement(
            catalog_src=cat, sales_src=sales, axis=axis,
            catalog_n=cat_agg.get("count"), distinct_n=dist.get("count"),
            period=period)
    return None


def try_entity_form_answer(question, intent, pool, match="", diag=None,
                          cut=None, t0=None, today=None, when=None,
                          early_classes=0):
    """Ответ формой F или None. На when=pre_entity зовёт entity_form_pre_entity_ok."""
    if not entity_form_gate_open(intent, diag):
        return None
    pool = entity_form_expand_pool(pool, intent)
    structs = entity_form_structs(intent, pool, today=today)
    if not structs:
        return None
    if when == "pre_entity":
        if not entity_form_pre_entity_ok(
                early_classes=early_classes, form_n=len(structs)):
            return None
    form, meta = structs[0][0], structs[0][1]
    atom = entity_form_compute(form, meta, match=match)
    if not atom or atom.get("exact_value") is None:
        return None
    text = render_atom_pair(atom) or _fmt(atom.get("exact_value"))
    if not (text or "").strip():
        return None
    d = _diag_pack(diag or {}, entity_form=form,
                   entity_form_axis=meta.get("axis"),
                   entity_form_sales=meta.get("sales_src"),
                   entity_form_catalog=meta.get("catalog_src"))
    if t0 is not None:
        d["sec"] = round(time.time() - t0, 2)
    figs = _fork_figures_of(atom)
    return {"partial": cut or None, "kind": "answer", "text": text,
            "figures": figs, "atom": atom, "atoms": [atom],
            "source_fixed": False, "memory_eligible": False,
            "sources": [], "diag": d}


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
