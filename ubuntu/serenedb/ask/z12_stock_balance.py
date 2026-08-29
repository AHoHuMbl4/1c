"""Zone 12: Остатки (stock-balance). K9-ф3: маршрутизация по осям метаданных."""
from __future__ import annotations

from ask._imports import *
from ask._wire import register_zone, apply_bindings

apply_bindings(globals())

_BALANCE_REGS = {"at": 0.0, "set": None}
_BALANCE_MAP = {"at": 0.0, "rows": None}


def intent_axis_words(intent):
    """Оси из разбора: action_axis и kind, без текста вопроса."""
    intent = intent or {}
    words, seen = [], set()
    for key in ("action_axis", "kind"):
        w = _intent_text(intent.get(key))
        if not w:
            continue
        wl = w.lower()
        if wl in seen:
            continue
        seen.add(wl)
        words.append(w)
    return words


def state_path_active(intent):
    """Путь состояния/остатка: action_class=object."""
    return (intent or {}).get("action_class", "").strip().lower() == "object"


def aggregate_count_intent(intent, plan=None, question=""):
    """Итог count/sum без разреза по оси (не rank, не breakdown)."""
    intent = intent or {}
    plan = plan or {}
    if rank_intent_from(intent, plan, question):
        return False
    if question_wants_breakdown(intent, plan):
        return False
    want = (intent.get("want") or "").strip().lower()
    amt = intent.get("amount") or {}
    if want in ("count", ""):
        if not amt.get("op") and amt.get("value") is None:
            return True
    if want == "sum":
        return True
    return False


def secondary_axis_known(intent):
    """Вторичная ось (action_axis) задана и не совпадает с kind."""
    intent = intent or {}
    ax = _intent_text(intent.get("action_axis"))
    kind = _intent_text(intent.get("kind"))
    if not ax:
        return False
    if not kind:
        return True
    return ax.lower() != kind.lower()


def balance_axis_registers_confirmed(intent):
    """Остатковый маршрут подтверждается ref-осями в метаданных, не action_class."""
    broad = registers_for_kind_axes(intent, None)
    clean = frozenset(s for s in broad if not register_is_balance_noise(s))
    if not clean:
        return False
    capable = balance_capable_or_registers()
    if capable:
        return bool(clean & capable)
    return bool(clean)


def balance_routing_core(intent, plan=None, question=""):
    """Остатковый маршрут: object-path или breakdown/list с осями из intent."""
    intent = intent or {}
    plan = plan or {}
    if event_path_active(intent):
        return False
    if sales_kind_in_intent(intent):
        return False
    if rank_intent_from(intent, plan, question):
        if not question_wants_breakdown(intent, plan):
            return False
    if state_path_active(intent):
        return balance_axis_registers_confirmed(intent)
    if question_wants_breakdown(intent, plan) and intent_axis_words(intent):
        return True
    return False


def _stock_intent_signal(intent, plan=None, question=""):
    """Сигнал остатка из разбора модели — без подтверждения метаданными."""
    intent = intent or {}
    if event_path_active(intent) or sales_kind_in_intent(intent):
        return False
    if state_path_active(intent) and intent_axis_words(intent):
        return True
    if question_wants_breakdown(intent, plan) and intent_axis_words(intent):
        return True
    return False


def balance_path_engaged(intent, plan=None, question=""):
    """Balance-path: routing по intent; sales-sum исключается."""
    if sales_sum_intent(intent or {}, question):
        return False
    return balance_routing_core(intent, plan, question)


def question_asks_stock_balance(question, intent=None, plan=None):
    """Вопрос про остаток — триггер balance-path (intent, не слова вопроса)."""
    return balance_path_engaged(intent, plan, question)


def question_mentions_warehouse_axis(question, intent=None, plan=None):
    """Ось места хранения из action_axis → каталоги метаданных."""
    intent = intent or {}
    ax = _intent_text(intent.get("action_axis"))
    if not ax:
        return False
    period = intent.get("period") or {}
    has_period = bool(period.get("from") or period.get("to"))
    try:
        cats = entity_form_catalogs_for_kind(ax, allow_meaning=has_period) or []
    except RuntimeError:
        cats = []
    return bool(cats)


def question_has_aggregate_total_marker(question, intent=None, plan=None):
    """Итог без разреза по оси — из intent, не маркеры вопроса."""
    if not balance_routing_core(intent, plan, question):
        return False
    return aggregate_count_intent(intent, plan, question)


def question_wants_per_axis_breakdown(question, intent=None, plan=None):
    """Явный разрез по оси — want=list / max|min / порог без op."""
    return question_wants_breakdown(intent, plan)


def stock_question_engaged(question, intent=None, plan=None):
    """Stock-path: balance или ось склада с итогом / разрезом."""
    if balance_routing_core(intent, plan, question):
        return True
    if _stock_intent_signal(intent, plan, question):
        return True
    if not question_mentions_warehouse_axis(question, intent, plan):
        return False
    return (question_has_aggregate_total_marker(question, intent, plan)
            or question_wants_per_axis_breakdown(question, intent, plan))


def registers_for_kind_axes(intent, regs=None):
    """accumulationregister_* с refcol на каталоги kind/action_axis."""
    intent = intent or {}
    period = intent.get("period") or {}
    has_period = bool(period.get("from") or period.get("to"))
    cats = set()
    for w in intent_axis_words(intent):
        try:
            for c in entity_form_catalogs_for_kind(w, allow_meaning=has_period) or []:
                if c:
                    cats.add(c)
        except RuntimeError:
            pass
    if not cats:
        return frozenset()
    scope = list(regs) if regs is not None else None
    where_scope = ""
    if scope:
        where_scope = " AND r.src_table IN (%s)" % ", ".join(lit(r) for r in scope)
    cats_sql = ", ".join(lit(c) for c in sorted(cats))
    try:
        rows = psql(
            "SELECT DISTINCT r.src_table FROM search_refcols r "
            "WHERE r.src_table LIKE 'accumulationregister_%%' "
            "  AND r.col IS NOT NULL AND r.col <> '' "
            "  AND r.target_src IN (%s) %s "
            "  AND EXISTS ("
            "    SELECT 1 FROM %s c "
            "    WHERE c.src_table = r.src_table "
            "      AND c.nums IS NOT NULL AND len(map_keys(c.nums)) > 0"
            "  )" % (cats_sql, where_scope, CORPUS))
    except RuntimeError:
        return frozenset()
    return frozenset(r[0] for r in (rows or []) if r and r[0])


def axis_catalog_values(axis_word, limit=20, intent=None):
    """Значения оси: каталог по stem + refcol + map_extract_value(refs_map)."""
    axis_word = (axis_word or "").strip()
    if not axis_word:
        return []
    intent = intent or {}
    period = intent.get("period") or {}
    has_period = bool(period.get("from") or period.get("to"))
    cats = []
    try:
        found = entity_form_catalogs_for_kind(axis_word, allow_meaning=has_period) or []
    except RuntimeError:
        found = []
    for s in found:
        if s and s not in cats:
            cats.append(s)
    if not cats:
        return []
    out, seen = [], set()

    def _take(rows):
        for r in rows or []:
            w = (r[0] if r else None)
            if w is None:
                continue
            s = str(w).strip()
            if not s or s in seen or looks_like_src_table(s):
                continue
            seen.add(s)
            out.append(s)
            if len(out) >= int(limit):
                return True
        return False

    try:
        rows = psql(
            "WITH cats(src) AS (VALUES %s), "
            "cand AS ("
            "  SELECT r.col,"
            "         sum(CASE WHEN r.src_table LIKE 'accumulationregister_%%' "
            "                  THEN 1 ELSE 0 END) AS on_accum,"
            "         count(*) AS holders "
            "  FROM search_refcols r "
            "  WHERE r.target_src IN (SELECT src FROM cats) "
            "    AND r.col IS NOT NULL AND r.col <> '' "
            "  GROUP BY r.col), "
            "scored AS ("
            "  SELECT c.col, c.on_accum, c.holders,"
            "         (SELECT count(DISTINCT map_extract_value(refs_map, c.col)) "
            "          FROM %s "
            "          WHERE map_extract_value(refs_map, c.col) IS NOT NULL) AS n_vals "
            "  FROM cand c), "
            "best AS ("
            "  SELECT col FROM scored "
            "  ORDER BY on_accum DESC, n_vals DESC, holders DESC "
            "  LIMIT 1) "
            "SELECT DISTINCT map_extract_value(c.refs_map, b.col) AS w "
            "FROM %s c, best b "
            "WHERE map_extract_value(c.refs_map, b.col) IS NOT NULL "
            "LIMIT %d"
            % (", ".join("(%s)" % lit(s) for s in cats), CORPUS, CORPUS,
               int(limit)))
    except RuntimeError:
        rows = []
    if _take(rows):
        return out
    if out:
        return out
    cats_sql = ", ".join(lit(s) for s in cats)
    try:
        rows = psql(
            "SELECT DISTINCT name FROM search_refmap "
            "WHERE owner IN (%s) AND name IS NOT NULL AND trim(name) <> '' "
            "LIMIT %d" % (cats_sql, int(limit)))
    except RuntimeError:
        return out
    _take(rows)
    return out


def warehouse_axis_values(limit=20, intent=None):
    """Имена складов: axis_catalog_values по action_axis/kind из intent."""
    intent = intent or {}
    for w in intent_axis_words(intent):
        vals = axis_catalog_values(w, limit=limit, intent=intent)
        if vals:
            return vals
    ax = _intent_text(intent.get("action_axis"))
    if ax:
        return axis_catalog_values(ax, limit=limit, intent=intent)
    return []


def warehouse_axis_is_live(intent=None):
    """Живая ось места хранения: ≥2 значений из метаданных."""
    try:
        wh = warehouse_axis_values(intent=intent)
    except RuntimeError:
        return False
    return len(wh or []) >= 2


def stock_skips_warehouse_clarify(question, intent=None, plan=None):
    """Не уточнять склад: итог, разрез, или ось+итог по всем."""
    if not stock_question_engaged(question, intent, plan):
        if not question_mentions_warehouse_axis(question, intent, plan):
            return False
    if question_has_aggregate_total_marker(question, intent, plan):
        return True
    if question_wants_per_axis_breakdown(question, intent, plan):
        return True
    if aggregate_count_intent(intent, plan, question) and secondary_axis_known(intent):
        return True
    return False


def grain_dec_from_axis_ticket(intent, plan, grain_dec, prov_axis, question=""):
    """Билет оси: grain=group сохраняется; form=rank при рейтинговом вопросе."""
    rankish = rank_intent_from(intent, plan, question) or (
        (grain_dec or {}).get("form") in ("rank", "compare"))
    form = "rank" if rankish else ((grain_dec or {}).get("form") or "number")
    return {"grain": "group", "col": prov_axis, "form": form,
            "named_gis": [], "clarify": None}


def _rank_wants_quantity(question, intent=None):
    """Рейтинг количества — из intent/rank_intent_from, не слова вопроса."""
    intent = intent or {}
    if not rank_intent_from(intent, question=question):
        return False
    want = (intent.get("want") or "").strip().lower()
    if want not in ("count", "list", ""):
        return False
    for w in intent_axis_words(intent):
        if w and _base_knows_kind_or_measure(w):
            return True
    kind = intent.get("kind") or ""
    return bool(kind and _base_knows_kind_or_measure(kind))


def rank_measure_hint(names, intent, question, alias_by=None):
    """Рейтинг без явной меры: количество из intent, не из текста вопроса."""
    names = list(names or [])
    if not names:
        return None
    if (intent or {}).get("measure"):
        return None
    if not rank_intent_from(intent, question=question):
        return None
    if not _rank_wants_quantity(question, intent):
        return None
    got, _, how = measure_choice(names, "колич", alias_by=alias_by or {})
    if got and how in ("exact", "substring", "alias", "base", "single"):
        return got
    return None


def balance_registers():
    """Регистры остатков из search_meta (RecordType в $metadata при сборке).

    RuntimeError при чтении — сбой контура (п. 18), не «пустой реестр».
    """
    now = time.time()
    if (_BALANCE_REGS["set"] is not None
            and now - _BALANCE_REGS["at"] < 300):
        return _BALANCE_REGS["set"]
    r = psql("SELECT v FROM search_meta WHERE k = 'balance_registers' LIMIT 1")
    raw = (r[0][0] or "") if r and r[0] else ""
    got = frozenset(x.strip() for x in str(raw).split(",") if x.strip())
    _BALANCE_REGS.update({"at": now, "set": got})
    return got


def balance_map_rows():
    """Карта баланс-источников из search_balance_map ($metadata при сборке).

    Таблицы ещё нет (corpus_init не выкатили) — пустая карта, не сбой.
    RuntimeError на отказ доступа / обрыв — сбой контура (п. 18), не no_data.
    """
    now = time.time()
    if (_BALANCE_MAP["rows"] is not None
            and now - _BALANCE_MAP["at"] < 300):
        return _BALANCE_MAP["rows"]
    try:
        rows = psql(
            "SELECT src_table, form, has_record_type, has_debit_credit, "
            "has_period, has_ext_dimension FROM search_balance_map")
    except RuntimeError as e:
        msg = str(e).lower()
        if "search_balance_map" in msg and (
                "does not exist" in msg or "catalog" in msg
                or "not found" in msg or "не существует" in msg):
            rows = []
        else:
            raise
    _BALANCE_MAP.update({"at": now, "rows": rows or []})
    return _BALANCE_MAP["rows"]


def balance_capable_sources():
    """Множество src_table, пригодных для остатков по карте метаданных."""
    return frozenset(r[0] for r in (balance_map_rows() or []) if r and r[0])


def balance_capable_or_registers():
    """Карта баланс-источников; если corpus_init ещё не выкатили — реестр $metadata."""
    cap = balance_capable_sources()
    if cap:
        return cap
    return balance_registers()


def register_is_balance_noise(src):
    """Структурный отсев: продажи/сторно — не остатковый регистр."""
    return stock_balance_is_sales_noise(src) or stock_balance_is_reversal_noise(src)


def stock_balance_is_reversal_noise(src):
    s = (src or "").lower()
    return any(x in s for x in (
        "сторн", "storno", "reverse", "reversal", "cancel",
        "коррект", "adjust", "исправ"))


def stock_goods_pool(capable=None, intent=None):
    """Пул товарных balance-регистров по осям intent (search_refcols)."""
    capable = capable if capable is not None else balance_capable_or_registers()
    if not intent:
        return frozenset()
    broad = registers_for_kind_axes(intent, None)
    if not broad:
        return frozenset()
    clean = {s for s in broad if not register_is_balance_noise(s)}
    if not clean:
        return frozenset()
    if capable:
        in_cap = {s for s in clean if s in capable}
        if in_cap:
            return frozenset(in_cap)
    return frozenset(clean)


def filter_stock_goods_registers(cands, question, diag=None, intent=None, plan=None):
    if not stock_question_engaged(question, intent, plan):
        return cands
    pool = stock_goods_pool(None, intent)
    if not pool:
        return cands
    out, dropped = [], []
    for c in list(cands or []):
        if c and c.startswith("accumulationregister_") and c not in pool:
            dropped.append(c)
        else:
            out.append(c)
    if diag is not None and dropped:
        diag["stock_non_goods_drop"] = sorted(set(dropped))
    return out or list(pool)


def _stock_corpus_counts(pool):
    pool = list(pool or [])
    if not pool:
        return {}
    try:
        rows = psql(
            "SELECT src_table, count(*) FROM %s WHERE src_table IN (%s) GROUP BY 1"
            % (CORPUS, ", ".join(lit(s) for s in pool)))
    except RuntimeError:
        return {}
    return {r[0]: int(r[1]) for r in (rows or []) if r and r[0]}


def _stock_register_rank_key(src, capable=None, corpus_counts=None):
    s = str(src or "").lower()
    cc = corpus_counts or {}
    return (
        1 if stock_balance_is_sales_noise(s) else 0,
        1 if stock_balance_is_reversal_noise(s) else 0,
        0 if capable and src in capable else 1,
        0 if s.startswith("accumulationregister_") else 1,
        -int(cc.get(src) or 0),
        s)


def _sort_stock_pool(pool, capable=None):
    pool = list(pool or [])
    counts = _stock_corpus_counts(pool)
    pool.sort(key=lambda s: _stock_register_rank_key(s, capable, counts))
    return pool


def stock_canon_src(cands, question, intent=None, plan=None):
    if not stock_question_engaged(question, intent, plan):
        return None
    capable = balance_capable_or_registers()
    pool = [c for c in stock_goods_pool(capable, intent)
            if not register_is_balance_noise(c)]
    if not pool:
        return None
    pool = _sort_stock_pool(pool, capable)
    in_cands = [c for c in (cands or []) if c in pool]
    if in_cands:
        return _sort_stock_pool(in_cands, capable)[0]
    return pool[0]


def prefer_entity_for_stock(cands, question, intent=None, plan=None):
    """Stock-path: balance-регистр в голове, каталоги/документы вне пула."""
    canon = stock_canon_src(cands, question, intent, plan)
    if not canon:
        return cands
    capable = balance_capable_or_registers()
    pool = {c for c in stock_goods_pool(capable, intent)
            if not register_is_balance_noise(c)}
    pool.add(canon)
    out, seen = [], set()
    for c in [canon] + [x for x in (cands or []) if x in pool and x != canon]:
        if c and c not in seen:
            seen.add(c)
            out.append(c)
    return out or [canon]


def try_balance_code_entity_pick(question, intent, cands, diag, cut, t0, marks,
                                 plan=None):
    """K9-ф3: balance-path — лидер из registers_for_kind_axes до модели."""
    intent = intent or {}
    if not balance_path_engaged(intent, plan, question):
        return None
    capable = balance_capable_or_registers()
    scoped = [c for c in (cands or []) if c]
    pool = [c for c in registers_for_kind_axes(intent, scoped)
            if c in capable and not register_is_balance_noise(c)]
    if not pool:
        pool = [c for c in stock_goods_pool(capable, intent) if c in scoped]
    if not pool:
        diag["balance_code_empty_pool"] = True
        return {"kind": "no_data",
                "partial": cut or None,
                "text": NO_DATA_TEXT or refuse_text(question),
                "sources": [],
                "diag": _diag_pack(diag, sec=round(time.time() - t0, 2),
                                   reason="balance_no_axis_register")}
    pool = _sort_stock_pool(pool, capable)
    leader = pool[0]
    if len(pool) == 1:
        diag["balance_code_lock"] = leader
        return {"picked": [leader], "marks": marks or {}, "plan": plan or {}}
    keys = {s: _stock_register_rank_key(s, capable) for s in pool}
    best = min(keys.values())
    leaders = [s for s in pool if keys[s] == best]
    if len(leaders) == 1:
        diag["balance_code_lock"] = leaders[0]
        return {"picked": leaders, "marks": marks or {}, "plan": plan or {}}
    try:
        lab_by = {r[0]: r[1] for r in psql(
            "SELECT src_table, label FROM %s WHERE src_table IN (%s)"
            % (TABLES, ", ".join(lit(c) for c in leaders))) if r and r[0]}
    except RuntimeError:
        lab_by = {}
    opts = mk_opts([t for t in leaders if t in lab_by], lab_by, marks or {}, {},
                   match="", preds="")
    if len(opts) >= 2:
        diag["balance_code_tie"] = leaders
        return {"partial": cut or None, "kind": "clarify",
                "text": clarify_say(question, opts, diag)
                        or ", ".join("«%s»" % o["label"] for o in opts),
                "options": opts, "sources": [o["label"] for o in opts],
                "diag": _diag_pack(diag, sec=round(time.time() - t0, 2))}
    diag["balance_code_lock"] = leader
    return {"picked": [leader], "marks": marks or {}, "plan": plan or {}}


def _stems_of_text(s):
    """Основы текста через STEM_DICT; оффлайн/сбой — одно слово _intent_word."""
    s = (s or "").strip()
    if not s:
        return set()
    stems = set()
    try:
        kr = psql("SELECT ts_lexize(%s, %s)" % (lit(STEM_DICT), lit(s)))
        stems = {x for x in _stem_set(kr[0][0] if kr else "") if len(x) >= 3}
    except RuntimeError:
        stems = set()
    if not stems:
        w = _intent_word(s)
        if len(w) >= 3:
            stems = {w}
    return stems


def _stock_scaffold_stems(intent, question):
    """Основы темы остатков: kind + action_axis (без маркеров вопроса)."""
    parts = []
    intent = intent or {}
    for key in ("kind", "action_axis"):
        v = intent.get(key) or ""
        if v and _base_knows_kind_or_measure(v):
            parts.append(str(v))
    out = set()
    for part in parts:
        out |= _stems_of_text(part)
    return out


def stock_asks_named_product(question, intent=None):
    """Именованный товар — terms/measure вне скаффолда kind+action_axis."""
    if not balance_path_engaged(intent, None, question):
        return False
    intent = intent or {}
    scaffold = _stock_scaffold_stems(intent, question)
    kind_known = _base_knows_kind_or_measure(
        _intent_text((intent or {}).get("kind") or ""))

    def _is_named_term(text):
        s = _intent_text(text)
        if not s:
            return False
        kind = (_intent_text((intent or {}).get("kind") or "") or "").lower()
        sl = s.lower()
        if kind_known and kind and (kind in sl or sl in kind):
            return False
        t_st = _stems_of_text(s)
        return bool(t_st and not (t_st <= scaffold))

    if _is_named_term((intent or {}).get("measure")):
        return True
    for group in (intent.get("terms") or []):
        alts = group if isinstance(group, (list, tuple)) else [group]
        for alt in alts:
            if _is_named_term(alt):
                return True
    return False


def stock_balance_named_no_data(question, diag, cut, t0):
    """Именованный остаток без баланс-источника — no_data после пустого поиска (п. 21)."""
    d = dict(diag or {})
    d["stock_named_absent"] = True
    return {"partial": cut or None, "kind": "no_data", "text": NO_DATA_TEXT or refuse_text(question),
            "sources": [],
            "diag": _diag_pack(d, sec=round(time.time() - t0, 2),
                               reason="именованный товар не в баланс-источниках")}


def _resolve_breakdown_balance_src(src, cands=None, intent=None):
    """Balance-регистр с товарной осью для итога+люка."""
    try:
        cap = balance_capable_or_registers()
        goods = stock_goods_pool(cap, intent)
    except RuntimeError:
        return src or None
    goods = {c for c in (goods or []) if not register_is_balance_noise(c)}
    if src and src in goods:
        return src
    for c in (cands or []):
        if c in goods:
            return c
    if goods:
        return sorted(goods, key=lambda s: _stock_register_rank_key(s, cap))[0]
    if src and src in cap:
        return src
    if cap:
        return sorted(cap)[0]
    return src or None


def _breakdown_fallback_measure(src, measure, intent=None):
    """Мера count/sum для fallback — из intent или количественного поля регистра."""
    if measure:
        return measure
    want = ((intent or {}).get("want") or "").strip().lower()
    if want == "sum":
        return measure
    if not src:
        return measure
    try:
        names = list(measures_of(src) or [])
    except RuntimeError:
        return measure
    if not names:
        return measure
    got, _, how = measure_choice(names, "колич", alias_by={})
    if got and how in ("exact", "substring", "alias", "base", "single"):
        return got
    return measure


def stock_breakdown_leader_fallback(question, src, match, preds, measure, diag,
                                    cut, t0, intent=None, plan=None, agg=None,
                                    cands=None):
    """Исход B: лидер-итог + люк значений оси из метаданных."""
    if not question_wants_per_axis_breakdown(question, intent, plan):
        return None
    if not warehouse_axis_is_live(intent):
        return None
    intent = intent or {}
    axis_word = (_intent_text(intent.get("action_axis"))
                 or _intent_text(intent.get("kind")) or "")
    wh = []
    try:
        wh = list(axis_catalog_values(axis_word, intent=intent) or [])
    except RuntimeError:
        return None
    if len(wh) < 2:
        return None
    src = _resolve_breakdown_balance_src(src, cands, intent)
    measure = _breakdown_fallback_measure(src, measure, intent)
    if agg is None and src:
        try:
            agg = aggregate(src, match, preds, measure)
        except RuntimeError:
            agg = None
    if not agg or agg.get("count") is None:
        return None
    want = ((intent or {}).get("want") or "").strip().lower()
    op = "count" if want in ("count", "list", "") else "sum"
    val = agg.get("count") if op == "count" else agg.get("sum")
    if val is None:
        return None
    atom = atom_from_agg(
        agg, operation=op,
        measure_id=(measure or None),
        measure_label=measure_label_of(src, measure) if src else measure,
        money=(op == "sum"), src=src or None)
    text = render_atom_pair(atom)
    if not (text or "").strip():
        return None
    opts = [{"src": "", "label": w, "hint": "", "distinct_by": "warehouse",
             "found": 0} for w in wh]
    d = dict(diag or {})
    d["stock_breakdown_fallback"] = "leader_plus_axis_loophole"
    d["warehouse_axis_values"] = len(wh)
    return {"partial": cut or None, "kind": "figures", "text": text,
            "figures": _fork_figures_of(atom),
            "atom": atom, "atoms": [atom],
            "options": opts,
            "source_fixed": False, "memory_eligible": False,
            "sources": [src] if src else [],
            "diag": _diag_pack(d, sec=round(time.time() - t0, 2),
                               reason="разрез по оси: итог+люк")}


def _balance_map_by_src():
    """src → строка карты (form, структурные признаки)."""
    out = {}
    for r in balance_map_rows() or []:
        if r and r[0]:
            out[r[0]] = r
    return out


def filter_balance_structural(cands, diag=None):
    """Отсев кандидатов без структурной пригодности для остатков (план §2).

    Фильтрует, не добавляет. Требует: мера в nums, непустота, Period, баланс-структура
    (RecordType или Дт/Кт) по карте $metadata.
    """
    cands = list(cands or [])
    if not cands:
        return cands
    bm = _balance_map_by_src()
    if not bm:
        return cands
    in_map = [c for c in cands if c in bm]
    if not in_map:
        return cands
    rows = psql(
        "SELECT src_table FROM %s WHERE src_table IN (%s) "
        "  AND nums IS NOT NULL AND len(map_keys(nums)) > 0 "
        "GROUP BY 1 HAVING count(*) > 0"
        % (CORPUS, ", ".join(lit(c) for c in in_map)))
    live = {r[0] for r in (rows or []) if r and r[0]}
    kept = []
    dropped = []
    for c in cands:
        if c not in bm:
            kept.append(c)
            continue
        row = bm[c]
        form = (row[1] or "").strip()
        has_rt = bool(row[2]) if len(row) > 2 else False
        has_dk = bool(row[3]) if len(row) > 3 else False
        has_period = bool(row[4]) if len(row) > 4 else False
        struct_ok = has_period and (has_rt or has_dk or form == "accumulation_warehouse")
        if c in live and struct_ok:
            kept.append(c)
        else:
            dropped.append(c)
    if diag is not None and dropped:
        diag["balance_structural_drop"] = sorted(dropped)
    return kept


def balance_bridge_clarify(question, capable, diag, cut, t0, labels=None):
    """Словарный мост не принёс баланс-источник — clarify со списком пригодных."""
    labels = labels or {}
    srcs = sorted(capable)
    if not srcs:
        return None
    lab_by = {}
    missing = [s for s in srcs if s not in labels]
    if missing:
        for r in psql(
                "SELECT src_table, label FROM %s WHERE src_table IN (%s)"
                % (TABLES, ", ".join(lit(s) for s in missing))):
            if r and r[0]:
                lab_by[r[0]] = (r[1] or "").strip()
    lab_by.update(labels)
    opts = [{"src": s, "label": human_table_label(s, lab_by.get(s)), "hint": "",
             "distinct_by": "", "found": 0} for s in srcs]
    dis = disambiguate_labels([(o["src"], o["label"]) for o in opts])
    for o in opts:
        o["label"] = dis.get(o["src"], o["label"])
    cyr = any("\u0400" <= c <= "\u04ff" for c in (question or ""))
    if cyr:
        text = ("Вопрос про остатки — уточните источник из списка "
                "(без разреза по складам/товарам, если не указано иное).")
    else:
        text = ("Stock balance question — pick a source from the list "
                "(aggregate, no warehouse/item breakdown unless specified).")
    d = dict(diag or {})
    d["balance_bridge"] = "clarify"
    d["balance_capable"] = srcs
    return {"partial": cut or None, "kind": "clarify", "text": text,
            "options": opts, "sources": [o["label"] for o in opts],
            "diag": _diag_pack(d, sec=round(time.time() - t0, 2),
                               reason="мост не принёс баланс-источник")}


register_zone('ask.z12_stock_balance', globals())
