"""Zone 03: Периоды и окна (period-windows)."""
from __future__ import annotations

from ask._imports import *
from ask._wire import register_zone, apply_bindings

apply_bindings(globals())

def _num_pred(intent, measure):
    """Условие по ЧИСЛУ — к названной величине, а не к единственной колонке.

    Величина известна только после выбора сущности (её имена лежат в самих данных),
    поэтому числовое условие отделено от датного: датное работает на отборе сущностей,
    числовое — уже внутри выбранной.
    """
    a = (intent or {}).get("amount") or {}
    op, v, v2 = a.get("op"), a.get("value"), a.get("value2")
    if not (op and v is not None and measure):
        return []
    m = "map_extract(nums, %s)[1]" % lit(measure)
    if op == "between" and v2 is not None:
        return ["%s BETWEEN %s AND %s" % (m, float(v), float(v2))]
    # «=» здесь наравне с остальными: [замер 04.08] «с нулевой суммой» разбирается
    # именно в него, а без него условие пропадало молча — см. `_AMOUNT_OPS`.
    if op in ("=", ">", "<", ">=", "<="):
        return ["%s %s %s" % (m, op, float(v))]
    return []


def period_preds(period):
    """Предикаты одного диапазона дат. Второй срез — тот же вызов с period2.

    🔴 ВЕРХНЯЯ ГРАНИЦА — ПОЛУСОТКРЫТЫЙ ИНТЕРВАЛ, НЕ `<= 'YYYY-MM-DD'`. Строка даты
    без времени приводится к полуночи; `doc_date <= '2026-08-17'` отбрасывает все
    отметки дня (15:53 и т.д.), а `doc_date < (to::date + INTERVAL 1 day)` включает
    весь день включительно. [замер 18.08, okna] 331 строка регистра vs 0 при `<=`.
    На корпусе полусоткрытый путь быстрее `::date` (1.3 мс vs 7.5 мс на том же WHERE).
    """
    out = []
    p = period or {}
    if p.get("from"):
        out.append("doc_date >= %s" % lit(p["from"]))
    if p.get("to"):
        out.append("doc_date < (%s::date + INTERVAL 1 day)" % lit(p["to"]))
    out.extend(_working_day_doc_preds(p))
    return out


# ── Окна периода W (план §3): форма по границам дат, не по лексике вопроса ──
_ORIGIN_ASSUMED = "assumed"
_ORIGIN_PRIOR = "prior"
_ORIGIN_EXPLICIT = "explicit"
_ORIGIN_NONE = "none"
_WINDOW_FORM_IDS = frozenset({
    "none", "explicit", "mtd", "full_month", "full_quarter", "rolling_12m",
    "wtd", "full_week", "prev_week", "drop_assumed", "prior",
})
# §7bis: day-basis окна. Env умолч. 0 — бой не включён.
ASK_CALENDAR_AXIS = os.environ.get("ASK_CALENDAR_AXIS", "0") == "1"
ASK_CURRENCY_AXIS = os.environ.get("ASK_CURRENCY_AXIS", "0") == "1"
# Rank×sales канон (E/M/W): умолч. 0 — бой не включён (work/rank-path-fix-design.md).
ASK_SALES_RANK_CANON = os.environ.get("ASK_SALES_RANK_CANON", "0") == "1"
# Computed-атом терминален (K5): умолч. 0 — бой не включён (work/silent-refusal-form-design.md).
ASK_ATOM_TERMINAL = os.environ.get("ASK_ATOM_TERMINAL", "0") == "1"
# Форма атома F ∈ {distinct_axis, complement, compare}: умолч. 0
# (work/entity-compare-form-design.md; K4/K6).
ASK_ENTITY_FORM = os.environ.get("ASK_ENTITY_FORM", "0") == "1"
_PERIOD_RELATIVE_FORMS = {"at": 0.0, "map": None}
_DAY_BASIS_CALENDAR = "calendar_days"
_DAY_BASIS_WORKING = "working_days"
_DAY_BASIS_IDS = frozenset({_DAY_BASIS_CALENDAR, _DAY_BASIS_WORKING})
_DAY_BASIS_LEADER_DEFAULT = _DAY_BASIS_CALENDAR
_CALENDAR_REGS = {"at": 0.0, "set": None}
_CALENDAR_WORK_KEYS = {"at": 0.0, "set": None}
_CALENDAR_MAP = {"at": 0.0, "rows": None}


def _calendar_date(iso):
    """YYYY-MM-DD → date. Иначе None."""
    try:
        return datetime.date.fromisoformat(str(iso or "")[:10])
    except (TypeError, ValueError):
        return None


def _month_range(d):
    """Первый и последний день календарного месяца d."""
    start = d.replace(day=1)
    if start.month == 12:
        end = start.replace(day=31)
    else:
        end = (start.replace(month=start.month + 1) - datetime.timedelta(days=1))
    return start, end


def _quarter_range(d):
    """Календарный квартал, содержащий d (структурно, без лексики)."""
    q = (d.month - 1) // 3
    start = datetime.date(d.year, q * 3 + 1, 1)
    if q == 3:
        end = datetime.date(d.year, 12, 31)
    else:
        end = (datetime.date(d.year, (q + 1) * 3 + 1, 1)
               - datetime.timedelta(days=1))
    return start, end


def _week_range_monday(d):
    """Неделя пн–вс (Europe/Chisinau: календарная дата без TZ-сдвига)."""
    start = d - datetime.timedelta(days=d.weekday())
    end = start + datetime.timedelta(days=6)
    return start, end


def _prev_week_range(d):
    """Предыдущая календарная неделя: [date_trunc(week)−7d, date_trunc(week)).

    Доки: sql/functions/date#date_truncpart-date (форма границ как в эталоне gold).
    """
    ws, _we = _week_range_monday(d)
    start = ws - datetime.timedelta(days=7)
    end = ws - datetime.timedelta(days=1)
    return start, end


def _is_seven_day_span(fr_d, to_d):
    """Ровно семь календарных дней (to − from == 6). Иначе False."""
    if not fr_d or not to_d:
        return False
    return (to_d - fr_d).days == 6


def _is_current_calendar_week(fr_d, to_d, td):
    """Окно совпадает с WTD или полной пн–вс текущей календарной недели."""
    if not td or not fr_d or not to_d:
        return False
    ws, we = _week_range_monday(td)
    if fr_d != ws:
        return False
    return to_d == td or to_d == we


def _assumed_sliding_week_not_calendar(fr_d, to_d, td):
    """assumed 7 дней (любое выравнивание), конец сегодня/вчера, ≠ календарной неделе.

    Два прочтения одной оси W (§2–3): календарная неделя (лидер) и скользящие
    7 дней (люк). Не лексика — только границы и длина. explicit/prior снаружи.
    """
    if not td or not _is_seven_day_span(fr_d, to_d):
        return False
    if to_d not in (td, td - datetime.timedelta(days=1)):
        return False
    return not _is_current_calendar_week(fr_d, to_d, td)


def _iso_date(d):
    return d.isoformat()


def _period_origin(intent, period_from_prior=False):
    """Машинный origin окна из parse/diag, не из прозы вопроса."""
    if period_from_prior:
        return _ORIGIN_PRIOR
    parse = (intent or {}).get("parse") or {}
    assumed = parse.get("assumed") or []
    if any(str(a).startswith("period.") for a in assumed):
        return _ORIGIN_ASSUMED
    p = (intent or {}).get("period") or {}
    if p.get("from") or p.get("to"):
        return _ORIGIN_EXPLICIT
    return _ORIGIN_NONE


def window_fp_of(period, origin=None):
    """Машинный отпечаток окна: from|to|origin[+|day_basis][+|amount_basis].

    day_basis / amount_basis пуст — тот же fp, что до осей (совместимость W).
    """
    p = period or {}
    o = origin if origin is not None else (p.get("origin") or _ORIGIN_NONE)
    base = "%s|%s|%s" % (p.get("from") or "", p.get("to") or "", o)
    db = (p.get("day_basis") or "").strip()
    ab = (p.get("amount_basis") or "").strip()
    suffix = []
    if db:
        suffix.append(db)
    if ab:
        suffix.append(ab)
    if suffix:
        return base + "|" + "|".join(suffix)
    return base


def _period_form_id(period, today):
    """Id формы окна — только сравнением границ с today."""
    td = _calendar_date(today)
    p = period or {}
    fr, to = p.get("from"), p.get("to")
    if not td or not fr or not to:
        return "explicit" if (fr or to) else "none"
    fr_d, to_d = _calendar_date(fr), _calendar_date(to)
    if not fr_d or not to_d:
        return "explicit"
    ms, me = _month_range(td)
    ws, we = _week_range_monday(td)
    if fr_d == ms and to_d == td and to_d != me:
        return "mtd"
    if fr_d == ms and to_d == me:
        return "full_month"
    if fr_d == ws and to_d == td and to_d != we:
        return "wtd"
    if fr_d == ws and to_d == we:
        return "full_week"
    if ASK_SALES_RANK_CANON:
        pws, pwe = _prev_week_range(td)
        if fr_d == pws and to_d == pwe:
            return "prev_week"
    return "explicit"


def _window_reading(period, origin, form_id=None, today=None, day_basis=None,
                    amount_basis=None):
    p = dict(period or {})
    o = origin or _ORIGIN_NONE
    if o:
        p["origin"] = o
    fid = form_id or _period_form_id(p, today)
    if fid in _WINDOW_FORM_IDS:
        p["interpretation_id"] = fid
    db = (day_basis if day_basis is not None else p.get("day_basis")) or ""
    db = str(db).strip()
    if db:
        p["day_basis"] = db
    else:
        p.pop("day_basis", None)
    ab = (amount_basis if amount_basis is not None else p.get("amount_basis")) or ""
    ab = str(ab).strip()
    if ab:
        p["amount_basis"] = ab
    else:
        p.pop("amount_basis", None)
    out = {
        "period": p,
        "origin": o,
        "window_fp": window_fp_of(p, o),
        "interpretation_id": fid,
    }
    if db:
        out["day_basis"] = db
    if ab:
        out["amount_basis"] = ab
    return out


def period_readings(intent, today=None, period_from_prior=False):
    """Конечный перечень прочтений W по форме диапазона (план §3).

    MTD vs полный месяц, WTD vs полная неделя — по форме границ относительно today
    (`_period_form_id`), без имён сущностей и без списков русских слов.

    «без окна» (`drop_assumed`) — только когда в разборе нет from/to: вопрос не
    назвал период. Явный/относительный период (есть from|to) — не ветка drop.
    """
    if not today:
        today = time.strftime("%Y-%m-%d")
    td = _calendar_date(today)
    if not td:
        return [_window_reading({}, _ORIGIN_NONE, "none", today)]

    p = dict((intent or {}).get("period") or {})
    fr, to = p.get("from"), p.get("to")
    origin = _period_origin(intent, period_from_prior)

    if not fr and not to:
        out = [_window_reading({}, _ORIGIN_NONE, "none", today)]
        if origin == _ORIGIN_ASSUMED:
            out.append(_window_reading({}, "drop_assumed", "drop_assumed", today))
        return out

    fr_d = _calendar_date(fr)
    to_d = _calendar_date(to)
    if not fr_d or not to_d:
        return [_window_reading(p, origin, "explicit", today)]

    ms, me = _month_range(td)
    ws, we = _week_range_monday(td)
    # origin=assumed + ровно 7 дней, конец сегодня/вчера, ≠ текущая календарная
    # неделя: в перечень — wtd/full_week (лидер) и исходное скользящее (люк).
    # explicit/prior не трогаем — «прошлая неделя» и follow-up держат своё окно.
    sliding_hatch = None
    if origin == _ORIGIN_ASSUMED and _assumed_sliding_week_not_calendar(fr_d, to_d, td):
        sliding_hatch = dict(p)
        p = dict(p)
        p["from"] = _iso_date(ws)
        p["to"] = _iso_date(we)
        fr_d, to_d = ws, we
    readings, seen = [], set()

    def _add(period, orig, fid):
        r = _window_reading(period, orig, fid, today)
        if r["window_fp"] in seen:
            return
        seen.add(r["window_fp"])
        readings.append(r)

    # Раскрытие только если разбор уже месяц/неделя текущего календаря
    # (mtd|full_month|wtd|full_week). Одиночный день на 1-е / пн — explicit.
    fid = _period_form_id(p, today)
    if fid in ("mtd", "full_month"):
        mtd = {"from": _iso_date(ms), "to": _iso_date(td)}
        full = {"from": _iso_date(ms), "to": _iso_date(me)}
        if mtd["to"] == full["to"]:
            _add(full, origin, "full_month")
        else:
            _add(mtd, origin, "mtd")
            _add(full, origin, "full_month")
    elif fid in ("wtd", "full_week"):
        wtd = {"from": _iso_date(ws), "to": _iso_date(td)}
        full = {"from": _iso_date(ws), "to": _iso_date(we)}
        if wtd["to"] == full["to"]:
            _add(full, origin, "full_week")
        else:
            _add(wtd, origin, "wtd")
            _add(full, origin, "full_week")
    elif fid == "prev_week":
        pws, pwe = _prev_week_range(td)
        _add({"from": _iso_date(pws), "to": _iso_date(pwe)}, origin, "prev_week")
    else:
        _add(p, origin, "explicit")

    # Люк: исходные скользящие 7 дней рядом с календарной неделей (§2–3).
    if sliding_hatch is not None:
        _add(sliding_hatch, origin, "explicit")

    # Rank-канон W: при текущей неделе добавить prev_week (форма gold, §2.3).
    if ASK_SALES_RANK_CANON:
        have = {r.get("interpretation_id") for r in readings}
        if have & {"wtd", "full_week"} and "prev_week" not in have:
            pws, pwe = _prev_week_range(td)
            _add({"from": _iso_date(pws), "to": _iso_date(pwe)}, origin, "prev_week")

    # from/to уже есть → период назван; drop_assumed сюда не входит (§3).
    return readings if readings else [_window_reading(p, origin, "explicit", today)]


def render_window_label(period, origin=None, today=None):
    """Подпись W-ветки: ISO-даты + машинный origin/id формы (план §7).

    Без кириллических литералов — только `_period_day_label` и ascii id формы.
    """
    p = period or {}
    fr, to = p.get("from"), p.get("to")
    if not fr and not to:
        o = origin or p.get("origin") or _ORIGIN_NONE
        return o if o != _ORIGIN_NONE else None
    dates = _period_day_label(fr, to)
    fid = p.get("interpretation_id") or _period_form_id(p, today)
    o = origin or p.get("origin") or _ORIGIN_NONE
    parts = [dates]
    if fid and fid not in ("explicit", "none"):
        parts.append(fid)
    if o in (_ORIGIN_ASSUMED, _ORIGIN_PRIOR):
        parts.append(o)
    return " · ".join(parts)


# Лидер оси W по умолчанию: MTD/WTD (с начала периода по сегодня), не полный календарь.
_WINDOW_LEADER_FORMS = ("mtd", "wtd")


def prefer_window_leader(readings, prefer_form=None):
    """Reading-лидер для основного ответа: mtd/wtd, иначе первое прочтение.

    prefer_form — ticket/словарь (например prev_week); иначе статус-кво §2.3.
    """
    readings = list(readings or [])
    if not readings:
        return None
    if prefer_form:
        for rd in readings:
            if (rd.get("interpretation_id") or "") == prefer_form:
                return rd
    for prefer in _WINDOW_LEADER_FORMS:
        for rd in readings:
            if (rd.get("interpretation_id") or "") == prefer:
                return rd
    return readings[0]


def period_relative_forms():
    """Словарь относительных окон: form_id → фразы (данные, не литералы ask)."""
    now = time.time()
    if (_PERIOD_RELATIVE_FORMS["map"] is not None
            and now - _PERIOD_RELATIVE_FORMS["at"] < 300):
        return _PERIOD_RELATIVE_FORMS["map"]
    got = {}
    try:
        r = psql("SELECT v FROM search_meta WHERE k = 'period_relative_forms' LIMIT 1")
        raw = (r[0][0] or "") if r and r[0] else ""
        if raw:
            parsed = json.loads(raw) if isinstance(raw, str) else raw
            if isinstance(parsed, dict):
                got = {str(k): [str(x) for x in (v or [])]
                       for k, v in parsed.items()}
    except (RuntimeError, ValueError, TypeError):
        got = {}
    if not got:
        try:
            p = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "period_relative_forms.json")
            with open(p, encoding="utf-8") as f:
                parsed = json.load(f)
            if isinstance(parsed, dict):
                got = {str(k): [str(x) for x in (v or [])]
                       for k, v in parsed.items()}
        except (OSError, ValueError, TypeError):
            got = {}
    _PERIOD_RELATIVE_FORMS.update({"at": now, "map": got})
    return got


def period_form_from_question(question):
    """form_id относительного окна по фразам словаря (данные). Иначе None."""
    q = " ".join(str(question or "").lower().split())
    if not q:
        return None
    for form_id, phrases in (period_relative_forms() or {}).items():
        for ph in phrases or []:
            p = " ".join(str(ph).lower().split())
            if p and p in q:
                return form_id
    return None


def apply_period_leader(intent, today=None, period_from_prior=False, question=""):
    """Подключить period_readings к основному ответу (фаза B, план §2/§3).

    Лидер по умолчанию — MTD/WTD; полный месяц/неделя остаются конкурирующим
    прочтением для детектора. Возвращает список readings (для diag / исходов).
    """
    intent = intent if isinstance(intent, dict) else {}
    prefer_form = None
    # Словарь relative period (prev_week) — для sum и rank; без конкурирующего
    # wtd при лидере prev (иначе figures B показывает чужое окно).
    if ASK_SALES_RANK_CANON:
        prefer_form = period_form_from_question(question)
        pr0 = intent.get("period") or {}
        if (pr0.get("interpretation_id") or "") == "prev_week":
            prefer_form = "prev_week"
        if prefer_form == "prev_week":
            td = _calendar_date(today) or _calendar_date(time.strftime("%Y-%m-%d"))
            if td:
                pws, pwe = _prev_week_range(td)
                origin = _period_origin(intent, period_from_prior)
                intent["period"] = {
                    "from": _iso_date(pws), "to": _iso_date(pwe),
                    "interpretation_id": "prev_week", "origin": origin,
                }
    readings = period_readings(intent, today, period_from_prior=period_from_prior)
    leader = prefer_window_leader(readings, prefer_form=prefer_form)
    if leader is None:
        return readings
    pr = dict(leader.get("period") or {})
    if leader.get("origin"):
        pr["origin"] = leader["origin"]
    if leader.get("interpretation_id"):
        pr["interpretation_id"] = leader["interpretation_id"]
    if pr.get("from") or pr.get("to") or leader.get("interpretation_id") in (
            "none", "drop_assumed"):
        intent["period"] = pr
    return readings



register_zone('ask.z03_period_windows', globals())
