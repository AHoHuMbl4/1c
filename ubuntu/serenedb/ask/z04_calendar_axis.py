"""Zone 04: Календарная ось (calendar-axis)."""
from __future__ import annotations

from ask._imports import *
from ask._wire import register_zone, apply_bindings

apply_bindings(globals())

def _sql_ident(name):
    """Идентификатор колонки/таблицы в SQL (двойные кавычки)."""
    return '"' + str(name).replace('"', '""') + '"'


def calendar_registers():
    """Регистры календаря из search_meta (сборка §1-кватер). Как balance_registers."""
    now = time.time()
    if (_CALENDAR_REGS["set"] is not None
            and now - _CALENDAR_REGS["at"] < 300):
        return _CALENDAR_REGS["set"]
    try:
        r = psql("SELECT v FROM search_meta WHERE k = 'calendar_registers' LIMIT 1")
    except RuntimeError:
        r = []
    raw = (r[0][0] or "") if r and r[0] else ""
    got = frozenset(x.strip() for x in str(raw).split(",") if x.strip())
    _CALENDAR_REGS.update({"at": now, "set": got})
    return got


def calendar_working_day_keys():
    """Ref_Key видов day-basis=working из search_meta (витрина, не литералы)."""
    now = time.time()
    if (_CALENDAR_WORK_KEYS["set"] is not None
            and now - _CALENDAR_WORK_KEYS["at"] < 300):
        return _CALENDAR_WORK_KEYS["set"]
    try:
        r = psql(
            "SELECT v FROM search_meta WHERE k = 'calendar_working_day_keys' LIMIT 1")
    except RuntimeError:
        r = []
    raw = (r[0][0] or "") if r and r[0] else ""
    got = frozenset(x.strip() for x in str(raw).split(",") if x.strip())
    _CALENDAR_WORK_KEYS.update({"at": now, "set": got})
    return got


def calendar_map_rows():
    """Карта search_calendar_map: (src_table, date_col, day_key_col, hours_col).

    Таблицы нет / пусто — [] (ось честно выключена), не сбой контура.
    """
    now = time.time()
    if (_CALENDAR_MAP["rows"] is not None
            and now - _CALENDAR_MAP["at"] < 300):
        return _CALENDAR_MAP["rows"]
    try:
        rows = psql(
            "SELECT src_table, date_col, day_key_col, hours_col "
            "FROM search_calendar_map")
    except RuntimeError as e:
        msg = str(e).lower()
        if "search_calendar_map" in msg and (
                "does not exist" in msg or "catalog" in msg
                or "not found" in msg or "не существует" in msg):
            rows = []
        else:
            raise
    clean = []
    for r in rows or []:
        if not r or not r[0] or not r[1] or not r[2]:
            continue
        clean.append((str(r[0]), str(r[1]), str(r[2]),
                      str(r[3]) if len(r) > 3 and r[3] else ""))
    _CALENDAR_MAP.update({"at": now, "rows": clean})
    return clean


_DAY_BASIS_HOLIDAY = "holiday"
_DAY_BASIS_NEED_MAP = frozenset({_DAY_BASIS_WORKING, _DAY_BASIS_HOLIDAY})
_CALENDAR_DAY_BASIS_PHRASES = {"at": 0.0, "map": None}


def calendar_axis_map_ready():
    """Карта календаря в meta непуста (независимо от ASK_CALENDAR_AXIS)."""
    return bool(calendar_registers() and calendar_working_day_keys()
                and calendar_map_rows())


def calendar_day_basis_phrases():
    """Словарь phrase → day_basis id (search_meta, не литералы ask)."""
    now = time.time()
    if (_CALENDAR_DAY_BASIS_PHRASES["map"] is not None
            and now - _CALENDAR_DAY_BASIS_PHRASES["at"] < 300):
        return _CALENDAR_DAY_BASIS_PHRASES["map"]
    got = {}
    try:
        r = psql(
            "SELECT v FROM search_meta WHERE k = 'calendar_day_basis_phrases' LIMIT 1")
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
            p = str(ASK_ROOT / "calendar_day_basis_phrases.json")
            with open(p, encoding="utf-8") as f:
                parsed = json.load(f)
            if isinstance(parsed, dict):
                got = {str(k): [str(x) for x in (v or [])]
                       for k, v in parsed.items()}
        except (OSError, ValueError, TypeError):
            got = {}
    _CALENDAR_DAY_BASIS_PHRASES.update({"at": now, "map": got})
    return got


def day_basis_from_question(question):
    """day_basis из словаря meta по фразам вопроса. Иначе None."""
    q = " ".join(str(question or "").lower().split())
    if not q:
        return None
    for basis_id, phrases in (calendar_day_basis_phrases() or {}).items():
        bid = str(basis_id).strip()
        if bid not in _DAY_BASIS_NEED_MAP:
            continue
        for ph in phrases or []:
            p = " ".join(str(ph).lower().split())
            if p and p in q:
                return bid
    return None


def calendar_day_basis_needed(question, intent=None, trusted=None):
    """Вопрос/ticket требует карту графика (day_basis id из search_meta)."""
    if isinstance(trusted, dict):
        db = (trusted.get("day_basis") or "").strip()
        if db in _DAY_BASIS_NEED_MAP:
            return db
    need = day_basis_from_question(question)
    if need:
        return need
    intent = intent or {}
    db = str(intent.get("day_basis") or "").strip()
    if db in _DAY_BASIS_NEED_MAP:
        return db
    pr = intent.get("period") or {}
    db = str(pr.get("day_basis") or "").strip()
    if db in _DAY_BASIS_NEED_MAP:
        return db
    return None


def calendar_axis_unavailable_block(question, intent=None, trusted=None,
                                  diag=None, cut=None, t0=None):
    """day_basis из meta при пустой карте — no_data, не подмена числом (§5.2)."""
    need = calendar_day_basis_needed(question, intent=intent, trusted=trusted)
    if not need:
        return None
    if ASK_CALENDAR_AXIS and calendar_axis_map_ready():
        return None
    out_diag = dict(diag or {})
    out_diag["calendar_axis_unavailable"] = need
    sec = round(time.time() - t0, 2) if t0 else None
    packed = _diag_pack(out_diag, sec=sec, reason="calendar_axis_unavailable")
    return {
        "partial": cut or None,
        "kind": "no_data",
        "sources": [],
        "text": NO_DATA_TEXT or refuse_text(question),
        "diag": packed,
    }


def calendar_axis_open():
    """Ось открыта: флаг + непустые registers/keys + карта (как balance_registers)."""
    if not ASK_CALENDAR_AXIS:
        return False
    return bool(calendar_registers() and calendar_working_day_keys()
                and calendar_map_rows())


def calendar_day_basis_prefer(intent=None, trusted=None, question=None):
    """Лидер day-basis: ticket/intent, словарь meta, иначе calendar_days (§2.4)."""
    if isinstance(trusted, dict):
        db = (trusted.get("day_basis") or "").strip()
        if db in _DAY_BASIS_IDS:
            return db
        for k in ("day_basis", "src", "label"):
            v = str(trusted.get(k) or "").strip()
            if v in _DAY_BASIS_IDS:
                return v
    intent = intent or {}
    db = str(intent.get("day_basis") or "").strip()
    if db in _DAY_BASIS_IDS:
        return db
    pr = intent.get("period") or {}
    db = str(pr.get("day_basis") or "").strip()
    if db in _DAY_BASIS_IDS:
        return db
    need = day_basis_from_question(question or "")
    if need == _DAY_BASIS_WORKING:
        return _DAY_BASIS_WORKING
    return _DAY_BASIS_LEADER_DEFAULT


def _day_basis_reading(base_rd, day_basis):
    """Одно прочтение окна с координатой day_basis (тот же from/to/origin/form)."""
    base = base_rd or {}
    pr = dict(base.get("period") or {})
    origin = base.get("origin") or pr.get("origin") or _ORIGIN_NONE
    fid = base.get("interpretation_id") or pr.get("interpretation_id")
    return _window_reading(pr, origin, form_id=fid, day_basis=day_basis)


def calendar_axis_readings(base_reading, prefer=None):
    """0..2 day-basis reading одного окна. Флаг off / нет карты → [].

    Открытая ось даёт оба прочтения сразу: calendar_days + working_days (§2.1).
    Лидер порядка — prefer (§2.4); default = calendar_days.
    """
    if not calendar_axis_open():
        return []
    pr = (base_reading or {}).get("period") or {}
    if not (pr.get("from") and pr.get("to")):
        return []
    prefer = prefer if prefer in _DAY_BASIS_IDS else _DAY_BASIS_LEADER_DEFAULT
    order = [_DAY_BASIS_CALENDAR, _DAY_BASIS_WORKING]
    if prefer == _DAY_BASIS_WORKING:
        order = [_DAY_BASIS_WORKING, _DAY_BASIS_CALENDAR]
    return [_day_basis_reading(base_reading, db) for db in order]


def expand_readings_calendar_axis(readings, prefer=None):
    """Подмешать day-basis к period_readings. Флаг off — бит-в-бит тот же список."""
    readings = list(readings or [])
    if not ASK_CALENDAR_AXIS or not calendar_axis_open():
        return readings
    out = []
    for rd in readings:
        cal = calendar_axis_readings(rd, prefer=prefer)
        if cal:
            out.extend(cal)
        else:
            out.append(rd)
    return out


def prefer_day_basis_leader(readings, prefer=None):
    """Reading-лидер по day_basis (§2.4); иначе первое прочтение с окном."""
    readings = list(readings or [])
    if not readings:
        return None
    prefer = prefer if prefer in _DAY_BASIS_IDS else _DAY_BASIS_LEADER_DEFAULT
    for rd in readings:
        if (rd.get("day_basis") or (rd.get("period") or {}).get("day_basis")
                ) == prefer:
            return rd
    return readings[0]


def _working_day_doc_preds(period):
    """Предикат корпуса: doc_date ∈ дат day-basis=working из карты (один SQL, §1.3).

    Доки: sql/functions/utility#utility-table-functions (query_table).
    """
    p = period or {}
    if not ASK_CALENDAR_AXIS or p.get("day_basis") != _DAY_BASIS_WORKING:
        return []
    keys = list(calendar_working_day_keys() or [])
    rows = calendar_map_rows() or []
    fr, to = p.get("from"), p.get("to")
    if not keys or not rows or not fr or not to:
        return []
    key_sql = ", ".join(lit(k) for k in keys)
    parts = []
    for src, date_col, day_key_col, _hours in rows:
        parts.append(
            "SELECT DISTINCT try_cast(k.%s AS DATE) "
            "FROM query_table(%s) k "
            "WHERE k.%s IN (%s) "
            "  AND try_cast(k.%s AS DATE) >= %s::date "
            "  AND try_cast(k.%s AS DATE) <= %s::date"
            % (_sql_ident(date_col), lit(src), _sql_ident(day_key_col), key_sql,
               _sql_ident(date_col), lit(fr),
               _sql_ident(date_col), lit(to)))
    if not parts:
        return []
    union = " UNION ".join(parts)
    return ["try_cast(doc_date AS DATE) IN (%s)" % union]



register_zone('ask.z04_calendar_axis', globals())
