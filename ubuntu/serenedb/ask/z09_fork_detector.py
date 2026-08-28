"""Zone 09: Детектор развилки (fork-detector)."""
from __future__ import annotations

from ask._imports import *
from ask._wire import register_zone, apply_bindings

apply_bindings(globals())

def _measures_by_src(cands):
    """{сущность: [величины]} для всего круга — одним запросом, как `measures_of`.

    По одному обращению на сущность — это рост числа обращений с размером базы (п. 20),
    поэтому карта строится одним проходом и кэшируется на `_FORK_MEAS_TTL` секунд.
    """
    now = time.time()
    full = _fork_meas_cache["by_src"]
    if full and now - _fork_meas_cache["at"] < _FORK_MEAS_TTL:
        return {c: full.get(c, []) for c in cands}
    try:
        rows = psql("SELECT DISTINCT src_table, u.k FROM %s, unnest(map_keys(nums)) AS u(k) "
                    "WHERE nums IS NOT NULL" % CORPUS)
    except RuntimeError:
        return {c: [] for c in cands}
    full = {}
    for r in rows:
        if r and r[0] and r[1]:
            full.setdefault(r[0], []).append(r[1])
    _fork_meas_cache["at"] = now
    _fork_meas_cache["by_src"] = full
    return {c: full.get(c, []) for c in cands}


def _aliases_by_src(cands):
    """Алиасы величин для всего круга одним запросом. Нет таблицы — пусто (как у
    `measure_aliases_of`): сведение идёт по именам, без словаря."""
    if not cands:
        return {}
    try:
        rows = psql(
            "SELECT src_table, measure, aliases FROM search_measure_alias "
            "WHERE src_table IN (%s) AND coalesce(aliases,'') <> ''"
            % ", ".join(lit(c) for c in cands))
    except RuntimeError:
        return {}
    out = {}
    for r in rows:
        if r and r[0] and r[1]:
            out.setdefault(r[0], {})[r[1]] = r[2]
    return out


def _fork_headline_doc_measures(names):
    """Итог шапки document_* — поля *Документа (метаданные платформы)."""
    return sorted(n for n in (names or []) if n and str(n).lower().endswith("документа"))


def _fork_word_names_measure(wl):
    """Слово вопроса называет величину (поле), а не глагол действия («продали»).

    Нужно отличить «себестоимость» (мера названа → NA, если поля нет) от
    «продали» (глагол вопроса, measure_choice → rerank/[] → не доказательство NA;
    [замер 21.08 okna] intent.величина=продали, want=sum, SQL Всего посчитан).
    Морфемы — общие имена величин платформы, не привязка к базе.
    """
    if not wl:
        return False
    hints = ("сумм", "колич", "цен", "стоим", "себестоим", "всего", "итог",
             "оборот", "остат", "ндс", "аванс", "скид", "нацен", "выруч",
             "оплат", "задолж", "прибыл", "убыт")
    return any(h in wl for h in hints)


def _fork_sum_headline_pool(names):
    """Headline-меры sum-вопроса: *Документа и Всего (план §3, замер 17–21.08)."""
    out = []
    for h in _fork_headline_doc_measures(names):
        if h not in out:
            out.append(h)
    for n in names or []:
        if (n or "").strip().lower() == "всего" and n not in out:
            out.append(n)
            break
    return out


def _fork_relevant(word, names, alias_by, want=None):
    """Величины сущности, относящиеся к слову вопроса — тем же правилом, что выбор
    величины ответа (`measure_choice`, он же кормит `unresolved_quantity`/`measure_alts`).
    Слова нет и want≠sum — величин в атоме нет, атом сводится к счёту.
    want=sum и слово не разрешилось ни в одну меру источника — headline-pool
    (Всего, *Документа): глагол «продали» ≠ доказательство NA ([замер 21.08 okna]
    rel=[] → empty/no_applicable_cells при SQL Всего=49155.96). NA — только когда
    мера названа явно и её у источника нет («себестоимость» вне names).
    Для sum-вопроса у document_* в пул добавляются поля *Документа: иначе в rel
    остаётся только СуммаНДС и `_fork_headline_measure` не находит итог
    ([замер 17.08 okna]: document_реализациятмц → uncounted → C вместо B).
    """
    if not names:
        return []
    wl = (word or "").strip().lower()
    w = (want or "").strip().lower()

    def _sum_fallback():
        pool = _fork_sum_headline_pool(names)
        return pool if pool else list(names)

    if not wl:
        if w == "sum":
            return _sum_fallback()
        return []
    got, alts, how = measure_choice(names, word, alias_by=alias_by)

    def _with_doc_hdr(pool):
        if not ("сумм" in wl or wl == "sum"):
            return pool
        out = list(pool)
        for h in _fork_sum_headline_pool(names):
            if h not in out:
                out.append(h)
        return out

    if got:
        return _with_doc_hdr([got])
    if how == "ask":
        same = [n for n in alts if wl in n.lower()]
        return _with_doc_hdr(same or list(alts))
    # не разрешилось: want=sum + не имя меры → headline; имя меры без поля → []
    if w == "sum" and not alts:
        if _fork_word_names_measure(wl):
            return []
        return _sum_fallback()
    return _with_doc_hdr(list(alts))


def _fork_pool_excluded(pool, rows):
    """Src из пула без живой ячейки скана — явная причина (п. 13), не молчание."""
    rows = rows or {}
    return [{"src": s, "reason": "no_live_cells"}
            for s in (pool or []) if s and s not in rows]


def fork_scan(match, preds, rel_by_src):
    """Полный круг: счёт и суммы по preds + src пула, в движке.

    Два штатных запроса вместо сотен агрегатных колонок (доки SereneDB: «SQL ›
    Functions › Map Functions — map_entries(map)», «SQL › Query syntax › FILTER»):
      1. счёт и папки (`IsFolder` — признак платформы, тот же, что в `totals_of`) —
         один GROUP BY по общему WHERE;
      2. суммы относящихся величин — одним проходом `unnest(map_entries(nums))`,
         только по сущностям, у которых такие величины есть.
    Форма через колонки-FILTER замерена и отвергнута: 258 колонок × 623 тыс. строк —
    22 с; unnest по тем же данным — 1,75 с (`[замер 15.08]`). Сложение — DECIMAL, как
    в `aggregate`.

    🔴 `match` в скан НЕ входит. Пул уже отобран (cands / arb_pool); повторный text-match
    по корпусу асимметричен: документ и регистр одной продажи индексируются разным
    текстом, и ветка регистра молча получает count=0 при живом SQL по периоду
    ([замер 21.08 okna] «на этой неделе»: pool=3, register SUM=1.4M, fork.srcs=1).
    Параметр `match` сохранён в сигнатуре для совместимости вызовов; на WHERE не влияет.
    Отдельной колонки «вид записи» у `_RecordType`-сестёр в корпусе нет (замер 15.08:
    ключей вида в `flags`/`nums` регистров нет) — сёстры разводятся самим GROUP BY:
    каждая — свой src и свой атом.

    Возвращает {src: {"count": N, "folders": F, "sums": {величина: сумма}}} и только
    для сущностей с живым счётом: пустая ячейка пространства — не ветка развилки.
    """
    if not rel_by_src:
        return {}
    nf = "NOT coalesce(map_extract_value(flags, 'IsFolder'), false)"
    isf = "coalesce(map_extract_value(flags, 'IsFolder'), false)"
    _ = match  # см. docstring: match не в WHERE
    where = " AND ".join([w for w in ([p for p in preds if p] +
                         ["src_table IN (%s)" % ", ".join(lit(t) for t in rel_by_src)])
                         if w]) or "TRUE"
    out = {}
    try:
        rows = psql("SELECT src_table, count(*) FILTER (%s), count(*) FILTER (%s) "
                    "FROM %s WHERE %s GROUP BY 1" % (nf, isf, CORPUS, where))
    except RuntimeError:
        return {}
    for r in rows:
        if not r or not r[0]:
            continue
        try:
            n = int(_num(r[1]))
        except (TypeError, ValueError, IndexError):
            continue
        if n > 0:
            out[r[0]] = {"count": n, "folders": int(_num(r[2])), "sums": {}}
    if not out:
        return {}
    measures = sorted({m for ms in rel_by_src.values() for m in ms})
    with_val = [t for t, ms in rel_by_src.items() if ms and t in out]
    if measures and with_val:
        where2 = " AND ".join([w for w in (
            [p for p in preds if p]
            + ["src_table IN (%s)" % ", ".join(lit(t) for t in with_val),
               "nums IS NOT NULL", nf]) if w])
        try:
            for r in psql(
                    "SELECT src_table, u.e.key, "
                    "coalesce(sum(TRY_CAST(u.e.value AS DECIMAL(38,10))),0) "
                    "FROM %s, unnest(map_entries(nums)) AS u(e) "
                    "WHERE %s AND u.e.key IN (%s) GROUP BY 1, 2"
                    % (CORPUS, where2, ", ".join(lit(m) for m in measures))):
                if r and r[0] in out and r[1] in (rel_by_src.get(r[0]) or []):
                    val = _numN(r[2])
                    # тождественный ноль / пустой агрегат — не сумма (03.08);
                    # coalesce в SELECT оставлен, отсев здесь, чтобы отпечаток
                    # класса не нёс мёртвую величину.
                    if val is None or round(val, 2) == 0.0:
                        continue
                    out[r[0]]["sums"][r[1]] = val
        except RuntimeError:
            pass                            # без сумм атом остаётся по счёту
    return out


def fork_scan_readings(match, readings, rel_by_src):
    """Мульти-скан: readings × fork_scan; ячейки (src, window_fp) со статусом.

    ASK_ENTITY_FORM: catalog_* сканируется без date-pred (иначе ложный
    no_live_cells на справочнике без doc_date в корпусе — K6.1).
    """
    rel_by_src = rel_by_src or {}
    readings = readings or [{}]
    cells = []
    merged_rows = {}
    period_by_src = {}
    for rd in readings:
        pr = dict(rd.get("period") or {})
        if rd.get("origin"):
            pr["origin"] = rd["origin"]
        if rd.get("interpretation_id"):
            pr["interpretation_id"] = rd["interpretation_id"]
        if rd.get("day_basis"):
            pr["day_basis"] = rd["day_basis"]
        if rd.get("amount_basis"):
            pr["amount_basis"] = rd["amount_basis"]
        preds_w = (period_preds(pr) if (pr.get("from") or pr.get("to")) else [])
        if ASK_ENTITY_FORM and preds_w:
            cat_rel = {s: m for s, m in rel_by_src.items()
                       if str(s).startswith("catalog_")}
            dated_rel = {s: m for s, m in rel_by_src.items() if s not in cat_rel}
            scan = {}
            if dated_rel:
                scan.update(fork_scan(match, preds_w, dated_rel))
            if cat_rel:
                scan.update(fork_scan(match, [], cat_rel))
        else:
            scan = fork_scan(match, preds_w, rel_by_src)
        if ASK_CURRENCY_AXIS and pr.get("amount_basis"):
            scan = currency_patch_fork_scan(scan, preds_w, rel_by_src, pr)
        wfp = rd.get("window_fp") or window_fp_of(pr, rd.get("origin"))
        for src in rel_by_src:
            if src in scan:
                row = scan[src]
                cells.append({"src": src, "window_fp": wfp, "period": pr,
                              "row": row, "status": "computed"})
                merged_rows[(src, wfp)] = row
                period_by_src[(src, wfp)] = pr
            else:
                cells.append({"src": src, "window_fp": wfp, "period": pr,
                              "row": None, "status": "no_live_cells"})
    return cells, merged_rows, period_by_src


def fork_classes_windowed(merged_rows, period_by_src, measure_word="", want=None,
                          rel_by_src=None):
    """Классы по ячейкам (src, window_fp); один src — несколько окон."""
    rel_by_src = rel_by_src if rel_by_src is not None else {}
    by_atom = {}
    meta_by_fp = {}
    for key, d in (merged_rows or {}).items():
        src, wfp = key
        rel = rel_by_src.get(src)
        period = period_by_src.get(key)
        built = _fork_atom_of(d, [src], measure_word, want=want, rel_measures=rel,
                              period=period)
        fp = _fork_atom_equiv_fp(built)
        if fp is None:
            continue
        bucket = by_atom.setdefault(fp, [])
        if src not in bucket:
            bucket.append(src)
        if fp not in meta_by_fp:
            meta_by_fp[fp] = {"row": d, "period": period, "window_fp": wfp,
                              "atom": built}
        else:
            # при слиянии равных атомов day-basis — держать лидера calendar в meta
            cur = meta_by_fp[fp].get("period") or {}
            if ((period or {}).get("day_basis") == _DAY_BASIS_CALENDAR
                    and cur.get("day_basis") != _DAY_BASIS_CALENDAR):
                meta_by_fp[fp] = {"row": d, "period": period, "window_fp": wfp,
                                  "atom": built}
            elif ((period or {}).get("amount_basis") == _AMOUNT_BASIS_DOC
                  and cur.get("amount_basis") != _AMOUNT_BASIS_DOC):
                meta_by_fp[fp] = {"row": d, "period": period, "window_fp": wfp,
                                  "atom": built}
    fork_classes._meta_by_fp = meta_by_fp
    return by_atom


def fork_detector_scan(match, preds, intent, today, rel_by_src,
                         period_from_prior=False, measure_word="", want=None,
                         day_basis_prefer=None, amount_basis_prefer=None,
                         trusted=None):
    """Один или несколько readings → rows + classes + cells для diag."""
    readings = period_readings(intent, today, period_from_prior=period_from_prior)
    prefer = day_basis_prefer
    if prefer is None:
        prefer = calendar_day_basis_prefer(intent, trusted=trusted)
    readings = expand_readings_calendar_axis(readings, prefer=prefer)
    curr_prefer = amount_basis_prefer
    if curr_prefer is None:
        curr_prefer = currency_amount_basis_prefer(intent, trusted=trusted)
    readings = expand_readings_currency_axis(
        readings, prefer=curr_prefer, rel_by_src=rel_by_src, preds=preds,
        intent=intent, trusted=trusted)
    if len(readings) <= 1:
        rd = readings[0] if readings else {"period": {}}
        pr = rd.get("period") or {}
        use_preds = (period_preds(pr) if (pr.get("from") or pr.get("to"))
                     else list(preds or []))
        if ASK_ENTITY_FORM and use_preds:
            cat_rel = {s: m for s, m in (rel_by_src or {}).items()
                       if str(s).startswith("catalog_")}
            dated_rel = {s: m for s, m in (rel_by_src or {}).items()
                         if s not in cat_rel}
            rows = {}
            if dated_rel:
                rows.update(fork_scan(match, use_preds, dated_rel))
            if cat_rel:
                rows.update(fork_scan(match, [], cat_rel))
        else:
            rows = fork_scan(match, use_preds, rel_by_src)
        rows = _event_distinct_fork_rows(intent, match, use_preds, rows, rel_by_src)
        pmeta = {}
        if pr.get("from") or pr.get("to"):
            for s in rows:
                pmeta[s] = pr
        cls = fork_classes(rows, measure_word, want=want, rel_by_src=rel_by_src,
                           period_meta=pmeta)
        return rows, cls, readings, []
    cells, merged, pby = fork_scan_readings(match, readings, rel_by_src)
    rows = {s: merged[(s, w)] for (s, w) in merged}
    rows = _event_distinct_fork_rows(intent, match, preds, rows, rel_by_src)
    merged_dist = {(s, w): rows[s] for (s, w) in merged if s in rows}
    cls = fork_classes_windowed(merged_dist, pby, measure_word, want=want,
                                  rel_by_src=rel_by_src)
    return rows, cls, readings, cells


def _window_tuple_from_period(period):
    """(origin, from, to) для отпечатка класса — окно W входит в эквивалентность.

    day_basis в fp НЕ входит: равные числа calendar/working → один класс → A (§3.4);
    разные числа разводит exact_value. day_basis живёт в window_fp / period / labels.
    """
    pr = period or {}
    return (
        pr.get("origin") or pr.get("interpretation_id") or _ORIGIN_NONE,
        pr.get("from") or "",
        pr.get("to") or "",
    )


def _fork_atom_equiv_fp(atom):
    """Отпечаток AnswerAtom для классов эквивалентности — без src-шелухи (план §3, §5).

    Не входят: measure_label, display_value, unit, completeness, freshness, src.
    Для sum — не count/folders строк (документ vs регистр при том же итоге).
    Для count — folders остаётся дискриминатором (записи vs группы).
    Окно W (origin, from, to) — дискриминатор класса при разных прочтениях периода.
    """
    if not isinstance(atom, dict):
        return None
    op = (atom.get("operation") or "count").lower()
    status = atom.get("proof_status") or PROOF_UNCOUNTED
    if status == PROOF_NA:
        return (op, status) + (_window_tuple_from_period(atom.get("period")),)
    ev = atom.get("exact_value")
    if ev is not None:
        try:
            ev = round(float(ev), 2)
        except (TypeError, ValueError):
            ev = str(ev)
    mid = atom.get("measure_id")
    fp = (op, status, ev, mid)
    if op == "count":
        excl = atom.get("excluded") or {}
        if isinstance(excl, dict) and excl.get("folders") is not None:
            fp = fp + (("folders", int(excl["folders"])),)
    if ASK_ENTITY_FORM:
        fp = fp + ((atom.get("form") or ""), (atom.get("axis") or ""))
    fp = fp + (_window_tuple_from_period(atom.get("period")),)
    return fp


def _fork_fp_diag(fp):
    if not isinstance(fp, tuple):
        return []
    out = []
    for i, x in enumerate(fp):
        if isinstance(x, tuple) and len(x) == 2:
            out.append([str(x[0]), x[1]])
        else:
            out.append(["%d" % i, x])
    return out


def fork_classes(rows, measure_word="", want=None, rel_by_src=None,
                   period_meta=None):
    """Классы эквивалентности по полному AnswerAtom без src (план §3, §5)."""
    rel_by_src = rel_by_src if rel_by_src is not None else {}
    period_meta = period_meta or {}
    by_atom = {}
    meta_by_fp = {}
    for src, d in (rows or {}).items():
        rel = rel_by_src[src] if src in rel_by_src else None
        period = period_meta.get(src)
        built = _fork_atom_of(d, [src], measure_word, want=want, rel_measures=rel,
                              period=period)
        fp = _fork_atom_equiv_fp(built)
        if fp is None:
            continue
        by_atom.setdefault(fp, []).append(src)
        if fp not in meta_by_fp:
            meta_by_fp[fp] = {"row": d, "period": period, "atom": built}
    fork_classes._meta_by_fp = meta_by_fp
    return by_atom


def fork_key_of(src_set, measure_ctx, window_fp=""):
    """Отпечаток класса развилки: sha1(sorted src + measure_ctx [+ window_fp]).

    window_fp пуст — совместимость с подписями src-пар волны-1.
    """
    srcs = sorted({s for s in (src_set or []) if s})
    payload = "|".join(srcs) + "¦" + (measure_ctx or "")
    if window_fp:
        payload += "¦" + str(window_fp)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def _window_fp_base(period, origin=None):
    """Отпечаток окна без day_basis / amount_basis — ключ веток в словаре."""
    p = dict(period or {})
    p.pop("day_basis", None)
    p.pop("amount_basis", None)
    return window_fp_of(p, origin if origin is not None else p.get("origin"))


def _fork_key_for_period(srcs, measure_ctx, period):
    """fork_key класса: для day-basis — базовое окно + src таблицы, не id ветки."""
    pr = period or {}
    db = (pr.get("day_basis") or "").strip()
    if db in _DAY_BASIS_IDS:
        wfp = _window_fp_base(pr, pr.get("origin"))
    ab = (pr.get("amount_basis") or "").strip()
    if ab in _AMOUNT_BASIS_IDS:
        wfp = _window_fp_base(pr, pr.get("origin"))
    elif pr.get("from") or pr.get("to") or pr.get("origin"):
        wfp = window_fp_of(pr, pr.get("origin"))
    else:
        wfp = ""
    return fork_key_of(sorted(s for s in (srcs or []) if s), measure_ctx, window_fp=wfp)


def _fork_amount_basis_groups(classes, meta_by_fp):
    """(data_srcs, base_wfp) → множество id веток amount-basis."""
    groups = {}
    fp_to_gkey = {}
    for fp, srcs in (classes or {}).items():
        meta = (meta_by_fp or {}).get(fp) or {}
        period = meta.get("period") or {}
        ab = (period.get("amount_basis") or "").strip()
        if ab not in _AMOUNT_BASIS_IDS:
            continue
        base_wfp = _window_fp_base(period, period.get("origin"))
        ds = tuple(sorted(s for s in (srcs or []) if s))
        if not ds:
            continue
        gkey = (ds, base_wfp)
        groups.setdefault(gkey, set()).add(ab)
        fp_to_gkey[fp] = gkey
    return groups, fp_to_gkey


def _fork_log_amount_basis(classes, measure_ctx, meta_by_fp):
    groups, _ = _fork_amount_basis_groups(classes, meta_by_fp)
    for (data_srcs, base_wfp), abs_ in groups.items():
        if len(abs_) < 2:
            continue
        branch_set = sorted(abs_)
        fork_key = fork_key_of(list(data_srcs), measure_ctx, window_fp=base_wfp)
        try:
            psql("INSERT INTO search_fork_class (fork_key, src_set, measure_ctx, seen_at, "
                 "seen_count) VALUES (%s, %s, %s, now(), 1) "
                 "ON CONFLICT (fork_key) DO UPDATE "
                 "SET seen_at = now(), seen_count = search_fork_class.seen_count + 1, "
                 "src_set = EXCLUDED.src_set, measure_ctx = EXCLUDED.measure_ctx"
                 % (lit(fork_key), lit("{%s}" % ",".join(branch_set)),
                    lit(measure_ctx or "")))
        except RuntimeError:
            pass


def _fork_day_basis_groups(classes, meta_by_fp):
    """(data_srcs, base_wfp) → множество id веток day-basis; fp → ключ группы."""
    groups = {}
    fp_to_gkey = {}
    for fp, srcs in (classes or {}).items():
        meta = (meta_by_fp or {}).get(fp) or {}
        period = meta.get("period") or {}
        db = (period.get("day_basis") or "").strip()
        if db not in _DAY_BASIS_IDS:
            continue
        base_wfp = _window_fp_base(period, period.get("origin"))
        ds = tuple(sorted(s for s in (srcs or []) if s))
        if not ds:
            continue
        gkey = (ds, base_wfp)
        groups.setdefault(gkey, set()).add(db)
        fp_to_gkey[fp] = gkey
    return groups, fp_to_gkey


def _fork_log_day_basis(classes, measure_ctx, meta_by_fp):
    """§7bis: класс day-basis → очередь подписей с id веток calendar_days/working_days."""
    groups, _fp_to_gkey = _fork_day_basis_groups(classes, meta_by_fp)
    for (data_srcs, base_wfp), dbs in groups.items():
        if len(dbs) < 2:
            continue
        branch_set = sorted(dbs)
        fork_key = fork_key_of(list(data_srcs), measure_ctx, window_fp=base_wfp)
        try:
            psql("INSERT INTO search_fork_class (fork_key, src_set, measure_ctx, seen_at, "
                 "seen_count) VALUES (%s, %s, %s, now(), 1) "
                 "ON CONFLICT (fork_key) DO UPDATE "
                 "SET seen_at = now(), seen_count = search_fork_class.seen_count + 1, "
                 "src_set = EXCLUDED.src_set, measure_ctx = EXCLUDED.measure_ctx"
                 % (lit(fork_key), lit("{%s}" % ",".join(branch_set)),
                    lit(measure_ctx or "")))
        except RuntimeError:
            pass


def _fork_log(classes, measure_ctx):
    """Класс атомов — в журнал `search_fork_class` (план §7).

    Каждая запись — один класс эквивалентности (src с одинаковым типизированным
    атомом), а не весь набор конкурирующих веток разом: подписи в
    `search_fork_label` привязаны к (fork_key, src) внутри класса. Волна-1 писала
    sha1 от всех src сразу — branch_alias подписывал источники, а исход B шага 4
    читал их как конкурирующие пары ([замер 17.08 okna]: 129 пар count вместо 2 sum).

    §7bis day-basis: при нескольких классах одного src/окна с разным day_basis —
    одна запись с src_set=id веток (_DAY_BASIS_*), не дубли по таблице данных.
    """
    if len(classes or {}) < 2:
        return
    meta_by_fp = getattr(fork_classes, "_meta_by_fp", {}) or {}
    groups, fp_to_gkey = _fork_day_basis_groups(classes, meta_by_fp)
    ab_groups, ab_fp_to_gkey = _fork_amount_basis_groups(classes, meta_by_fp)
    day_variant_fps = {fp for fp, gk in fp_to_gkey.items()
                       if len(groups.get(gk, ())) >= 2}
    ab_variant_fps = {fp for fp, gk in ab_fp_to_gkey.items()
                      if len(ab_groups.get(gk, ())) >= 2}
    _fork_log_day_basis(classes, measure_ctx, meta_by_fp)
    _fork_log_amount_basis(classes, measure_ctx, meta_by_fp)
    for fp, srcs in classes.items():
        if fp in day_variant_fps or fp in ab_variant_fps:
            continue
        src_set = sorted(s for s in (srcs or []) if s)
        if len(src_set) < 1:
            continue
        meta = meta_by_fp.get(fp) or {}
        period = meta.get("period") or {}
        fork_key = _fork_key_for_period(src_set, measure_ctx, period)
        try:
            psql("INSERT INTO search_fork_class (fork_key, src_set, measure_ctx, seen_at, "
                 "seen_count) VALUES (%s, %s, %s, now(), 1) "
                 "ON CONFLICT (fork_key) DO UPDATE "
                 "SET seen_at = now(), seen_count = search_fork_class.seen_count + 1, "
                 "src_set = EXCLUDED.src_set, measure_ctx = EXCLUDED.measure_ctx"
                 % (lit(fork_key), lit("{%s}" % ",".join(src_set)),
                    lit(measure_ctx or "")))
        except RuntimeError:
            pass


def fork_labels_of(fork_key, srcs):
    """Проверенные подписи веток из `search_fork_label`: {src: label}. Пустые — пропуск.

    Таблицы нет / права нет — пусто (как у алиасов): исход B тогда недостижим → C.
    """
    srcs = [s for s in (srcs or []) if s]
    if not fork_key or not srcs:
        return {}
    try:
        rows = psql(
            "SELECT src, label FROM search_fork_label "
            "WHERE fork_key = %s AND src IN (%s) AND coalesce(label,'') <> ''"
            % (lit(fork_key), ", ".join(lit(s) for s in srcs)))
    except RuntimeError:
        return {}
    out = {}
    for r in rows or []:
        if r and r[0] and r[1] and str(r[1]).strip():
            out[r[0]] = str(r[1]).strip()
    return out




def fork_labels_covering(srcs):
    """Подписи для набора src: ключ словаря, покрывающий все src, иначе частичный.

    Возвращает ({src: label}, fork_key|None). Нужен, когда sha1(src_set¦ctx)
    детектора не совпал с ключом, под которым агент писал подписи.
    """
    srcs = sorted({s for s in (srcs or []) if s})
    if not srcs:
        return {}, None
    try:
        rows = psql(
            "SELECT fork_key, src, label FROM search_fork_label "
            "WHERE src IN (%s) AND coalesce(label,'') <> ''"
            % ", ".join(lit(s) for s in srcs))
    except RuntimeError:
        return {}, None
    by_fk = {}
    for r in rows or []:
        if r and r[0] and r[1] and r[2] and str(r[2]).strip():
            by_fk.setdefault(r[0], {})[r[1]] = str(r[2]).strip()
    for k, m in by_fk.items():
        if all(s in m for s in srcs):
            return m, k
    merged = {}
    for m in by_fk.values():
        merged.update(m)
    return ({s: merged[s] for s in srcs if s in merged},
            next(iter(by_fk), None))


def fork_label_siblings(srcs):
    """Устаревшее расширение пула (волна-1): все src одного fork_key из словаря.

    Шаг 4 не использует: fork_key волны-1 = sha1 всех src развилки, JOIN раздувает
    arb_pool до сотен подписанных источников ([замер 17.08 okna]). Исходы B/C — только
    arb_pool.
    """
    return []


def _fork_answering_sums(sums, rel_measures=None):
    """Суммы, которыми атом sum-вопроса может ответить.

    Тождественный ноль — незаполненное поле (правило 03.08, HOW_IT_WORKS), не
    кандидат headline и не «0» в паре. Мера вне rel (без лексики слова вопроса)
    в атом не входит: иначе регистр с мёртвой `Сумма` и живым `Количество`
    отвечал бы нулём ([замер 17.08 okna] accumulationregister_реализациятмц).
    """
    rel = set(rel_measures) if rel_measures is not None else None
    out = {}
    for k, v in (sums or {}).items():
        if not k:
            continue
        if rel is not None and k not in rel:
            continue
        try:
            if round(float(v), 2) == 0.0:
                continue
        except (TypeError, ValueError):
            continue
        out[k] = v
    return out


def _fork_headline_measure(src, sums, measure_word, alias_by=None, want=None):
    """Одна «головная» величина класса — для exact_value атома и сверки с `aggregate`.

    Алфавитный первый ключ в `sums` давал 71 045 277,59 (`СуммаВзаиморасчетов`)
    вместо эталона 73 181 157,68 (`СуммаДокумента`) на document_* при слове «сумма»
    ([замер 17.08]). Правило — `measure_choice`, плюс структурный приоритет: у
    document_* итог шапки — поле *Документа* (имя из метаданных платформы), а не
    варианты взаиморасчётов с тем же словом вопроса. Несколько подходящих с разными
    итогами без такого приоритета — не выбираем молча (п. 12) → None.
    """
    sums = sums or {}
    names = [n for n in sums if n]
    if not names:
        return None
    if len(names) == 1:
        return names[0]
    wl = (measure_word or "").strip()
    w = (want or "").strip().lower()
    wl_l = wl.lower()

    def _pick_sum_headline():
        if (src or "").startswith("document_"):
            hdr = sorted(n for n in names if n.lower().endswith("документа"))
            if len(hdr) == 1:
                return hdr[0]
            if hdr:
                hdr.sort(key=lambda n: (float(sums.get(n) or 0) == 0, len(n), n))
                return hdr[0]
        vsego = [n for n in names if (n or "").strip().lower() == "всего"]
        if len(vsego) == 1:
            return vsego[0]
        if len(names) == 1:
            return names[0]
        return None

    if not wl:
        if w == "sum":
            return _pick_sum_headline()
        return None
    # Sum-вопрос: итог шапки раньше лексического частичного (СуммаНДС /
    # СуммаБезНДС / точное «Сумма»=0). Иначе один substring-хит блокирует
    # «Всего» ([замер 17.08 okna] физлицо 1 310 413,93 вместо 1 572 493,22;
    # регистр реализациятмц → 0 при SQL 79 925 955,81). Не-sum слово
    # («количество») до шапки не доходит — иначе Всего перебило бы штуки.
    # Глагол вопроса («продали») при want=sum — тот же headline, что пустое слово
    # ([замер 21.08 okna]); явная мера («себестоимость») сюда не входит.
    if w == "sum" and not _fork_word_names_measure(wl_l) and "сумм" not in wl_l and wl_l != "sum":
        picked = _pick_sum_headline()
        if picked is not None:
            return picked
    if "сумм" in wl_l or wl_l == "sum":
        if (src or "").startswith("document_"):
            hdr = sorted(n for n in names if n.lower().endswith("документа"))
            if len(hdr) == 1:
                return hdr[0]
            if hdr:
                hdr.sort(key=lambda n: (float(sums.get(n) or 0) == 0, len(n), n))
                return hdr[0]
        vsego = [n for n in names if (n or "").strip().lower() == "всего"]
        if len(vsego) == 1:
            return vsego[0]
    got, alts, how = measure_choice(names, wl, alias_by=alias_by or {})
    if got and got in sums:
        return got
    pool = list(alts) if how == "ask" and alts else names
    if pool and not measure_ambiguous(pool, sums):
        return sorted(pool)[0]
    return None


def _fork_atom_of(row, srcs, measure_word="", alias_by=None, want=None,
                  rel_measures=None, period=None):
    """AnswerAtom класса из строки `fork_scan` (без src). Непосчитанное — PROOF_UNCOUNTED.

    `want=sum` — только сумма по величине вопроса; без подходящей величины атом
    непосчитан, а не count ([замер 17.08]: «на какую сумму» → 129× count).
    `want=count` — счёт строк; суммы в атом не входят.
    `rel_measures=[]` при sum-вопросе — доказанно не относится (план §3.3, §7.3):
    величин вопроса у источника нет, хотя строки под WHERE есть; не блокирует A/B.
    Непустое rel, из которого после отсечения тождественного нуля ничего не
    осталось (лексическая мера мертва, живая — вне rel) — тоже NA, не «0».
    """
    d0 = row or {"count": 0, "folders": 0, "sums": {}}
    src0 = sorted(srcs)[0] if srcs else ""
    w = (want or "").strip().lower()
    if alias_by is None and src0:
        try:
            alias_by = measure_aliases_of(src0)
        except RuntimeError:
            alias_by = {}
    sum_q = w == "sum" or (bool((measure_word or "").strip()) and w != "count")
    if sum_q and rel_measures is not None and not rel_measures:
        return build_answer_atom(
            operation="sum", exact_value=None, measure_id=None, measure_label=None,
            excluded=({"folders": d0["folders"]} if d0.get("folders") else None),
            proof_status=PROOF_NA)
    sums = (_fork_answering_sums(d0.get("sums") or {}, rel_measures)
            if sum_q else (d0.get("sums") or {}))
    if sum_q and rel_measures is not None and not sums:
        return build_answer_atom(
            operation="sum", exact_value=None, measure_id=None, measure_label=None,
            excluded=({"folders": d0["folders"]} if d0.get("folders") else None),
            proof_status=PROOF_NA)
    if w == "count" and d0.get("distinct_axis"):
        exact = d0.get("count")
        ax_lab = (d0.get("distinct_axis_label") or "").strip()
        if not ax_lab:
            ax_lab = d0.get("distinct_axis")
        return build_answer_atom(
            operation="count", exact_value=exact, measure_id=None,
            measure_label=None, axis=ax_lab, form="distinct_axis",
            grain="axis",
            excluded=({"folders": d0["folders"]} if d0.get("folders") else None),
            proof_status=(PROOF_COMPUTED if exact is not None else PROOF_UNCOUNTED),
            period=period,
            interpretation_id=(period or {}).get("interpretation_id"))
    if w == "count":
        exact = d0.get("count")
        op, mid, lab = "count", None, measure_label_of(src0, None) if src0 else None
    elif sum_q:
        mid = _fork_headline_measure(src0, sums, measure_word, alias_by, want=w)
        if mid is None:
            exact, op, lab = None, "sum", None
        else:
            exact, op = sums[mid], "sum"
            lab = measure_label_of(src0, mid) if src0 else (split_ident(mid) or mid)
    else:
        mid = _fork_headline_measure(src0, sums, measure_word, alias_by, want=w)
        if mid is None:
            if not sums:
                exact, op, mid = d0.get("count"), "count", None
                lab = measure_label_of(src0, None) if src0 else None
            else:
                exact, op, lab = None, "sum", None
        else:
            exact, op = sums[mid], "sum"
            lab = measure_label_of(src0, mid) if src0 else (split_ident(mid) or mid)
    status = PROOF_COMPUTED if exact is not None else PROOF_UNCOUNTED
    return build_answer_atom(
        operation=op, exact_value=exact, measure_id=mid, measure_label=lab,
        excluded=({"folders": d0["folders"]} if d0.get("folders") else None),
        proof_status=status, period=period,
        interpretation_id=(period or {}).get("interpretation_id"))


def _class_branch_label(srcs, labels_by_src):
    """Подпись класса: первая непустая по отсортированным src. Нет — None."""
    for s in sorted(srcs or []):
        lab = (labels_by_src or {}).get(s)
        if lab:
            return lab
    return None


def _class_label_lookup(srcs, measure_ctx, atom=None, today=None):
    """Подпись класса по представителю (первый src после sort). B — по классу, не по src_set."""
    srcs = sorted(s for s in (srcs or []) if s)
    if not srcs:
        return None, None
    period = (atom or {}).get("period") if isinstance(atom, dict) else None
    rep = srcs[0]
    fk_cls = _fork_key_for_period(srcs, measure_ctx, period)
    db = ((period or {}).get("day_basis") or "").strip()
    if db in _DAY_BASIS_IDS:
        # §7bis: подписи day-basis по (fork_key базового окна, id ветки) из §7.
        labs = fork_labels_of(fk_cls, [db])
        if labs.get(db):
            return labs[db], fk_cls
        cov, fk = fork_labels_covering([db])
        if cov.get(db):
            return cov[db], fk or fk_cls
        return None, fk_cls
    ab = ((period or {}).get("amount_basis") or "").strip()
    if ab in _AMOUNT_BASIS_IDS:
        labs = fork_labels_of(fk_cls, [ab])
        if labs.get(ab):
            return labs[ab], fk_cls
        cov, fk = fork_labels_covering([ab])
        if cov.get(ab):
            return cov[ab], fk or fk_cls
        return None, fk_cls
    wlab = render_window_label(period, today=today) if period else None
    if wlab:
        return wlab, fk_cls
    labs = fork_labels_of(fk_cls, srcs)
    lab = _class_branch_label(srcs, labs)
    if lab:
        return lab, fk_cls
    cov, fk = fork_labels_covering([rep])
    if cov.get(rep):
        return cov[rep], fk or fk_cls
    cov_all, fk2 = fork_labels_covering(srcs)
    lab = _class_branch_label(srcs, cov_all)
    return lab, (fk2 or fk_cls)



register_zone('ask.z09_fork_detector', globals())
