"""Zone 04b: Ось amount-basis (валюта документа vs валюта учёта)."""
from __future__ import annotations

from ask._imports import *
from ask._wire import register_zone, apply_bindings

apply_bindings(globals())

_AMOUNT_BASIS_DOC = "doc_amount"
_AMOUNT_BASIS_ACCOUNTING = "accounting_amount"
_AMOUNT_BASIS_IDS = frozenset({_AMOUNT_BASIS_DOC, _AMOUNT_BASIS_ACCOUNTING})
_AMOUNT_BASIS_LEADER_DEFAULT = _AMOUNT_BASIS_DOC
_CURRENCY_REGS = {"at": 0.0, "set": None}
_CURRENCY_ACCT = {"at": 0.0, "val": None}
_CURRENCY_MAP = {"at": 0.0, "rows": None}
_CURRENCY_RATE_MAP = {"at": 0.0, "rows": None}
_CURRENCY_CATALOGS = {"at": 0.0, "set": None}


def _sql_ident(name):
    return '"' + str(name).replace('"', '""') + '"'


def currency_catalogs():
    """Справочники валют из search_meta (§1.4)."""
    now = time.time()
    if (_CURRENCY_CATALOGS["set"] is not None
            and now - _CURRENCY_CATALOGS["at"] < 300):
        return _CURRENCY_CATALOGS["set"]
    try:
        r = psql("SELECT v FROM search_meta WHERE k = 'currency_catalogs' LIMIT 1")
    except RuntimeError:
        r = []
    raw = (r[0][0] or "") if r and r[0] else ""
    got = frozenset(x.strip() for x in str(raw).split(",") if x.strip())
    _CURRENCY_CATALOGS.update({"at": now, "set": got})
    return got


def currency_rate_registers():
    """Регистры курсов из search_meta."""
    now = time.time()
    if (_CURRENCY_REGS["set"] is not None
            and now - _CURRENCY_REGS["at"] < 300):
        return _CURRENCY_REGS["set"]
    try:
        r = psql("SELECT v FROM search_meta WHERE k = 'currency_rate_registers' LIMIT 1")
    except RuntimeError:
        r = []
    raw = (r[0][0] or "") if r and r[0] else ""
    got = frozenset(x.strip() for x in str(raw).split(",") if x.strip())
    _CURRENCY_REGS.update({"at": now, "set": got})
    return got


def accounting_currency_key():
    """Ref валюты учёта из search_meta.accounting_currency_constant."""
    now = time.time()
    if (_CURRENCY_ACCT["val"] is not None
            and now - _CURRENCY_ACCT["at"] < 300):
        return _CURRENCY_ACCT["val"]
    try:
        r = psql(
            "SELECT v FROM search_meta WHERE k = 'accounting_currency_constant' LIMIT 1")
    except RuntimeError:
        r = []
    val = (r[0][0] or "").strip() if r and r[0] else ""
    _CURRENCY_ACCT.update({"at": now, "val": val or None})
    return val or None


def currency_map_rows():
    """Карта search_currency_map: src, cols, grain."""
    now = time.time()
    if (_CURRENCY_MAP["rows"] is not None
            and now - _CURRENCY_MAP["at"] < 300):
        return _CURRENCY_MAP["rows"]
    try:
        rows = psql(
            "SELECT src_table, curr_col, amount_col, date_col, grain, "
            "grain_col, rate_col, posted_col, deleted_col "
            "FROM search_currency_map")
    except RuntimeError as e:
        msg = str(e).lower()
        if "search_currency_map" in msg and (
                "does not exist" in msg or "catalog" in msg
                or "not found" in msg or "не существует" in msg):
            rows = []
        else:
            raise
    clean = []
    for r in rows or []:
        if not r or not r[0] or not r[1] or not r[2] or not r[3]:
            continue
        clean.append({
            "src": str(r[0]),
            "curr_col": str(r[1]),
            "amount_col": str(r[2]),
            "date_col": str(r[3]),
            "grain": str(r[4] or "").strip(),
            "grain_col": str(r[5] or "Ref_Key").strip(),
            "rate_col": str(r[6] or "").strip(),
            "posted_col": str(r[7] or "").strip(),
            "deleted_col": str(r[8] or "").strip(),
        })
    _CURRENCY_MAP.update({"at": now, "rows": clean})
    return clean


def currency_rate_map_rows():
    """Карта join регистра курсов: reg_table, period_col, curr_col, rate_col."""
    now = time.time()
    if (_CURRENCY_RATE_MAP["rows"] is not None
            and now - _CURRENCY_RATE_MAP["at"] < 300):
        return _CURRENCY_RATE_MAP["rows"]
    try:
        rows = psql(
            "SELECT reg_table, period_col, curr_col, rate_col, denom_col "
            "FROM search_currency_rate_map")
    except RuntimeError as e:
        msg = str(e).lower()
        if "search_currency_rate_map" in msg and (
                "does not exist" in msg or "catalog" in msg
                or "not found" in msg or "не существует" in msg):
            rows = []
        else:
            raise
    clean = []
    for r in rows or []:
        if not r or not r[0] or not r[1] or not r[2] or not r[3]:
            continue
        clean.append({
            "reg": str(r[0]),
            "period_col": str(r[1]),
            "curr_col": str(r[2]),
            "rate_col": str(r[3]),
            "denom_col": str(r[4] or "").strip(),
        })
    _CURRENCY_RATE_MAP.update({"at": now, "rows": clean})
    return clean


def currency_map_for_src(src):
    for row in currency_map_rows() or []:
        if row.get("src") == src:
            return row
    return None


def currency_axis_open():
    """Ось открыта: флаг + карта + якорь учёта + регистр курсов."""
    if not ASK_CURRENCY_AXIS:
        return False
    return bool(currency_map_rows() and accounting_currency_key()
                and currency_rate_map_rows())


def currency_amount_basis_prefer(intent=None, trusted=None):
    """Лидер amount-basis: ticket/intent/словарь, иначе doc_amount (§2.4)."""
    if isinstance(trusted, dict):
        ab = (trusted.get("amount_basis") or "").strip()
        if ab in _AMOUNT_BASIS_IDS:
            return ab
        for k in ("amount_basis", "currency_basis", "src", "label"):
            v = str(trusted.get(k) or "").strip()
            if v in _AMOUNT_BASIS_IDS:
                return v
            if v == "accounting":
                return _AMOUNT_BASIS_ACCOUNTING
            if v == "doc":
                return _AMOUNT_BASIS_DOC
    intent = intent or {}
    ab = str(intent.get("amount_basis") or "").strip()
    if ab in _AMOUNT_BASIS_IDS:
        return ab
    pr = intent.get("period") or {}
    ab = str(pr.get("amount_basis") or "").strip()
    if ab in _AMOUNT_BASIS_IDS:
        return ab
    hit = currency_basis_from_labels(intent)
    if hit in _AMOUNT_BASIS_IDS:
        return hit
    return _AMOUNT_BASIS_LEADER_DEFAULT


def currency_basis_from_labels(intent=None):
    """Подпись словаря currency_basis=doc|accounting из search_fork_label."""
    intent = intent or {}
    ctx = (intent.get("measure") or intent.get("want") or "").strip()
    if not ctx:
        return ""
    try:
        rows = psql(
            "SELECT src, label FROM search_fork_label "
            "WHERE src IN (%s) AND coalesce(label,'') <> ''"
            % ", ".join(lit(x) for x in _AMOUNT_BASIS_IDS))
    except RuntimeError:
        return ""
    for r in rows or []:
        if not r or not r[0]:
            continue
        if r[0] in _AMOUNT_BASIS_IDS:
            return str(r[0])
    return ""


def _amount_basis_reading(base_rd, amount_basis):
    base = base_rd or {}
    pr = dict(base.get("period") or {})
    origin = base.get("origin") or pr.get("origin") or _ORIGIN_NONE
    fid = base.get("interpretation_id") or pr.get("interpretation_id")
    db = base.get("day_basis") or pr.get("day_basis")
    return _window_reading(pr, origin, form_id=fid, day_basis=db,
                           amount_basis=amount_basis)


def currency_axis_applies(base_reading, rel_by_src=None, preds=None,
                          intent=None, trusted=None):
    """Нужна ли ось: карта, окно, FX или hit словаря (§2.1)."""
    if not currency_axis_open():
        return False
    pr = (base_reading or {}).get("period") or {}
    if not (pr.get("from") and pr.get("to")):
        return False
    rel_by_src = rel_by_src or {}
    mapped = [s for s in rel_by_src if currency_map_for_src(s)]
    if not mapped:
        return False
    if currency_basis_from_labels(intent) in _AMOUNT_BASIS_IDS:
        return True
    if isinstance(trusted, dict):
        for k in ("amount_basis", "currency_basis"):
            if str(trusted.get(k) or "").strip() in _AMOUNT_BASIS_IDS:
                return True
    preds_w = period_preds(pr) if (pr.get("from") or pr.get("to")) else list(preds or [])
    for src in mapped:
        fx = currency_fx_probe(src, preds_w)
        if fx and fx.get("has_fx"):
            return True
    return False


def currency_axis_readings(base_reading, prefer=None, rel_by_src=None,
                           preds=None, intent=None, trusted=None):
    """0..2 amount-basis reading одного окна."""
    if not currency_axis_applies(base_reading, rel_by_src, preds, intent, trusted):
        return []
    prefer = prefer if prefer in _AMOUNT_BASIS_IDS else _AMOUNT_BASIS_LEADER_DEFAULT
    order = [_AMOUNT_BASIS_DOC, _AMOUNT_BASIS_ACCOUNTING]
    if prefer == _AMOUNT_BASIS_ACCOUNTING:
        order = [_AMOUNT_BASIS_ACCOUNTING, _AMOUNT_BASIS_DOC]
    return [_amount_basis_reading(base_reading, ab) for ab in order]


def expand_readings_currency_axis(readings, prefer=None, rel_by_src=None,
                                  preds=None, intent=None, trusted=None):
    """Подмешать amount-basis к readings. Флаг off — тот же список."""
    readings = list(readings or [])
    if not ASK_CURRENCY_AXIS or not currency_axis_open():
        return readings
    out = []
    for rd in readings:
        cur = currency_axis_readings(
            rd, prefer=prefer, rel_by_src=rel_by_src, preds=preds,
            intent=intent, trusted=trusted)
        if cur:
            out.extend(cur)
        else:
            out.append(rd)
    return out


def prefer_amount_basis_leader(readings, prefer=None):
    readings = list(readings or [])
    if not readings:
        return None
    prefer = prefer if prefer in _AMOUNT_BASIS_IDS else _AMOUNT_BASIS_LEADER_DEFAULT
    for rd in readings:
        ab = (rd.get("amount_basis")
              or (rd.get("period") or {}).get("amount_basis") or "").strip()
        if ab == prefer:
            return rd
    return readings[0]


def _currency_period_where(map_row, preds):
    parts = list(preds or [])
    pc = map_row.get("posted_col")
    dc = map_row.get("deleted_col")
    if pc:
        parts.append("coalesce(try_cast(d.%s AS BOOLEAN), false)" % _sql_ident(pc))
    if dc:
        parts.append("NOT coalesce(try_cast(d.%s AS BOOLEAN), false)" % _sql_ident(dc))
    return " AND ".join(p for p in parts if p) or "TRUE"


def _currency_rate_subquery(map_row, rate_map, hdr_alias="h"):
    rate_map = rate_map or {}
    reg = rate_map.get("reg")
    if not reg:
        regs = list(currency_rate_registers() or [])
        reg = regs[0] if regs else ""
    if not reg:
        return "NULL"
    rc = _sql_ident(rate_map.get("curr_col") or "Валюта_Key")
    rp = _sql_ident(rate_map.get("period_col") or "Period")
    rv = _sql_ident(rate_map.get("rate_col") or "Курс")
    denom = rate_map.get("denom_col")
    num = "try_cast(r.%s AS DOUBLE)" % rv
    if denom:
        num = "(%s / NULLIF(try_cast(r.%s AS DOUBLE), 0))" % (
            num, _sql_ident(denom))
    return (
        "(SELECT %s FROM query_table(%s) r "
        "WHERE r.%s = %s.%s "
        "  AND try_cast(r.%s AS DATE) <= try_cast(%s.%s AS DATE) "
        "ORDER BY try_cast(r.%s AS DATE) DESC LIMIT 1)"
        % (num, lit(reg), rc, hdr_alias,
           _sql_ident(map_row.get("curr_col")),
           rp, hdr_alias, _sql_ident(map_row.get("date_col")),
           rp))


def currency_fx_probe(src, preds):
    """FX в окне: doc_amount ≠ accounting_amount или n_fx>0."""
    m = currency_map_for_src(src)
    if not m:
        return None
    acct = accounting_currency_key()
    if not acct:
        return None
    rate_rows = currency_rate_map_rows() or []
    rate_map = rate_rows[0] if rate_rows else {}
    grain = (m.get("grain") or "").strip().lower()
    gc = _sql_ident(m.get("grain_col") or "Ref_Key")
    where = _currency_period_where(m, preds)
    date_pred = []
    for p in preds or []:
        if "doc_date" in p:
            date_pred.append(p.replace("doc_date", "try_cast(d.%s AS DATE)"
                                       % _sql_ident(m.get("date_col"))))
    if date_pred:
        where = where + " AND " + " AND ".join(date_pred)
    rate_sql = _currency_rate_subquery(m, rate_map, "h")
    if grain == "header":
        hdr = (
            "WITH hdr AS ("
            "  SELECT DISTINCT ON (d.%s) "
            "    try_cast(d.%s AS DATE) AS doc_date, "
            "    d.%s AS curr_key, "
            "    try_cast(d.%s AS DOUBLE) AS amount "
            "  FROM query_table(%s) d "
            "  WHERE %s "
            "  ORDER BY d.%s"
            ") " % (gc, _sql_ident(m.get("date_col")), _sql_ident(m.get("curr_col")),
                    _sql_ident(m.get("amount_col")), lit(src), where, gc))
    else:
        hdr = (
            "WITH hdr AS ("
            "  SELECT try_cast(d.%s AS DATE) AS doc_date, "
            "    d.%s AS curr_key, "
            "    try_cast(d.%s AS DOUBLE) AS amount "
            "  FROM query_table(%s) d "
            "  WHERE %s"
            ") " % (_sql_ident(m.get("date_col")), _sql_ident(m.get("curr_col")),
                    _sql_ident(m.get("amount_col")), lit(src), where))
    rated = hdr + (
        ", rated AS ("
        "  SELECT h.*, %s AS rate_on_date FROM hdr h"
        ") SELECT "
        "round(coalesce(sum(amount),0), 2), "
        "round(coalesce(sum(CASE WHEN curr_key = %s OR rate_on_date IS NULL "
        "  OR rate_on_date = 1 THEN amount "
        "  ELSE amount * rate_on_date END), 0), 2), "
        "count(*) FILTER (WHERE curr_key IS DISTINCT FROM %s "
        "  AND rate_on_date IS NOT NULL AND rate_on_date <> 1) "
        "FROM rated"
        % (rate_sql, lit(acct), lit(acct)))
    try:
        rows = psql(rated)
    except RuntimeError:
        return None
    if not rows or not rows[0]:
        return None
    doc_a = _num(rows[0][0])
    acct_a = _num(rows[0][1])
    n_fx = int(_num(rows[0][2]) or 0)
    return {
        "doc_amount": doc_a,
        "accounting_amount": acct_a,
        "n_fx": n_fx,
        "has_fx": (n_fx > 0 or round(doc_a, 2) != round(acct_a, 2)),
    }


def currency_sum_for_basis(src, preds, amount_basis):
    """Сумма по ветке amount-basis — один SQL §1.3."""
    probe = currency_fx_probe(src, preds)
    if not probe:
        return None
    if amount_basis == _AMOUNT_BASIS_ACCOUNTING:
        return probe.get("accounting_amount")
    return probe.get("doc_amount")


def currency_patch_fork_scan(scan, preds, rel_by_src, period):
    """Подмена sums в fork_scan для amount-basis reading."""
    ab = (period or {}).get("amount_basis") or ""
    if ab not in _AMOUNT_BASIS_IDS or not scan:
        return scan
    for src, row in list(scan.items()):
        if src not in (rel_by_src or {}):
            continue
        if not currency_map_for_src(src):
            continue
        rel = rel_by_src.get(src) or []
        new_sums = dict(row.get("sums") or {})
        val = currency_sum_for_basis(src, preds, ab)
        if val is not None:
            for m in rel or list(new_sums.keys()):
                if round(val, 2) != 0.0:
                    new_sums[m] = val
        row["sums"] = new_sums
        scan[src] = row
    return scan


def currency_unit_for_ref(ref_key):
    """Подпись валюты из справочника по Ref (Code или Description)."""
    ref_key = (ref_key or "").strip()
    if not ref_key:
        return ""
    catalogs = list(currency_catalogs() or [])
    if not catalogs:
        return ""
    for cat in catalogs:
        try:
            rows = psql(
                "SELECT Code, Description FROM query_table(%s) "
                "WHERE Ref_Key = %s LIMIT 1" % (lit(cat), lit(ref_key)))
        except RuntimeError:
            continue
        if rows and rows[0]:
            code = (rows[0][0] or "").strip()
            desc = (rows[0][1] or "").strip() if len(rows[0]) > 1 else ""
            return code or desc or ""
    return ""


def currency_unit_for_reading(period, src=None):
    """Единица ответа: валюта ветки из данных, не env."""
    ab = (period or {}).get("amount_basis") or _AMOUNT_BASIS_LEADER_DEFAULT
    acct = accounting_currency_key()
    if ab == _AMOUNT_BASIS_ACCOUNTING and acct:
        u = currency_unit_for_ref(acct)
        if u:
            return u
    if src:
        m = currency_map_for_src(src)
        if m:
            try:
                rows = psql(
                    "SELECT DISTINCT d.%s FROM query_table(%s) d "
                    "WHERE d.%s IS NOT NULL LIMIT 3"
                    % (_sql_ident(m.get("curr_col")), lit(src),
                       _sql_ident(m.get("curr_col"))))
            except RuntimeError:
                rows = []
            refs = [r[0] for r in (rows or []) if r and r[0]]
            if len(refs) == 1:
                u = currency_unit_for_ref(refs[0])
                if u:
                    return u
    if acct:
        return currency_unit_for_ref(acct)
    return ""


def currency_ref_requested(intent=None, question="", trusted=None):
    """Ref валюты из словаря (src ∈ currency_catalogs), не списки слов."""
    catalogs = list(currency_catalogs() or [])
    if not catalogs:
        return ""
    if isinstance(trusted, dict):
        cr = (trusted.get("currency_ref") or trusted.get("currency") or "").strip()
        if cr:
            return cr
    try:
        rows = psql(
            "SELECT DISTINCT src FROM search_fork_label "
            "WHERE src IN (%s) AND coalesce(label,'') <> ''"
            % ", ".join(lit(c) for c in catalogs))
    except RuntimeError:
        return ""
    cat_refs = set()
    for cat in catalogs:
        try:
            for r in psql("SELECT Ref_Key FROM query_table(%s)" % lit(cat)):
                if r and r[0]:
                    cat_refs.add(str(r[0]))
        except RuntimeError:
            pass
    q = (question or "").strip().lower()
    if not q:
        return ""
    try:
        labs = psql(
            "SELECT src, label FROM search_fork_label "
            "WHERE coalesce(label,'') <> ''")
    except RuntimeError:
        labs = []
    for r in labs or []:
        if not r or len(r) < 2:
            continue
        lab = str(r[1] or "").strip().lower()
        src = str(r[0] or "").strip()
        if lab and lab in q and src in cat_refs:
            return src
    return ""


def currency_mismatch_blocks_answer(intent, question, src, trusted=None):
    """Запрошенная валюта ≠ фактам — не отдавать чужое число (п. 10/13)."""
    if not ASK_CURRENCY_AXIS or not currency_axis_open():
        return None
    want_ref = currency_ref_requested(intent, question, trusted=trusted)
    if not want_ref:
        return None
    acct = accounting_currency_key()
    if not acct:
        return None
    if want_ref == acct:
        return None
    m = currency_map_for_src(src)
    if not m:
        return None
    unit_w = currency_unit_for_ref(want_ref)
    unit_a = currency_unit_for_ref(acct)
    if not unit_w:
        return None
    return {
        "kind": "clarify",
        "text": ("Запрошена валюта %s; в учётных данных сумма в %s. "
                 "Уточните: в валюте документа или в валюте учёта?")
        % (unit_w, unit_a or "учёте"),
        "options": [
            {"amount_basis": _AMOUNT_BASIS_DOC,
             "label": fork_labels_of("", [_AMOUNT_BASIS_DOC]).get(
                 _AMOUNT_BASIS_DOC) or _AMOUNT_BASIS_DOC},
            {"amount_basis": _AMOUNT_BASIS_ACCOUNTING,
             "label": fork_labels_of("", [_AMOUNT_BASIS_ACCOUNTING]).get(
                 _AMOUNT_BASIS_ACCOUNTING) or _AMOUNT_BASIS_ACCOUNTING},
        ],
    }


def _class_amount_basis(it):
    """amount_basis класса — из period/atom."""
    p = (it or {}).get("period") or {}
    if not p.get("amount_basis"):
        p = ((it or {}).get("atom") or {}).get("period") or {}
    return (p.get("amount_basis")
            or ((it or {}).get("atom") or {}).get("amount_basis")
            or (it or {}).get("amount_basis") or "").strip()


register_zone('ask.z04b_currency_axis', globals())
