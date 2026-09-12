"""Zone 12: Остатки (stock-balance). K9-ф3: маршрутизация по осям метаданных."""
from __future__ import annotations

from ask._imports import *
from ask._wire import register_zone, apply_bindings

apply_bindings(globals())

_BALANCE_REGS = {"at": 0.0, "set": None}
_BALANCE_MAP = {"at": 0.0, "rows": None}
_STOCK_PLACE_AXIS = {"at": 0.0, "set": None}
_STOCK_PLACE_REF = {"at": 0.0, "set": None}


def _intent_period_has_meaning(intent):
    period = (intent or {}).get("period") or {}
    return bool(period.get("from") or period.get("to"))


def _catalogs_for_axis_word(word, intent=None, allow_meaning=None):
    word = _intent_text(word)
    if not word:
        return []
    if allow_meaning is None:
        allow_meaning = _intent_period_has_meaning(intent)
    try:
        # [замер 01.09 okna] ось места — только label+aliases: best_used_for
        # держит примеры вопросов («сколько сотрудников»), и вопросительное
        # слово из любого количественного вопроса ложно резолвилось осью.
        return (entity_form_catalogs_for_kind(word, allow_meaning=allow_meaning,
                                              include_examples=False) or [])
    except RuntimeError:
        return []


def _non_product_ref_targets(targets):
    """Ref-targets кроме product-catalog и document_* (структурный признак затрат)."""
    return sum(
        1 for t in (targets or ())
        if t and not _is_product_catalog_target(t)
        and not str(t).startswith("document_"))


def _stock_eligible_product_registers():
    """Product-axis balance-регистры без sales/reversal noise."""
    try:
        capable = balance_capable_or_registers()
    except RuntimeError:
        return frozenset()
    product = _stock_registers_with_product_axis(capable)
    return frozenset(s for s in product if not register_is_balance_noise(s))


def _stock_place_axis_catalogs():
    """Каталоги-оси места: ref на stock-eligible register с product-ref."""
    now = time.time()
    if (_STOCK_PLACE_AXIS["set"] is not None
            and now - _STOCK_PLACE_AXIS["at"] < 300):
        return _STOCK_PLACE_AXIS["set"]
    regs = list(_stock_eligible_product_registers())
    if not regs:
        _STOCK_PLACE_AXIS.update({"at": now, "set": frozenset()})
        return frozenset()
    try:
        rows = psql(
            "SELECT DISTINCT r1.target_src FROM search_refcols r1 "
            "WHERE r1.src_table IN (%s) "
            "  AND r1.col IS NOT NULL AND r1.col <> '' "
            "  AND EXISTS ("
            "    SELECT 1 FROM search_refcols r2 "
            "    WHERE r2.src_table = r1.src_table "
            "      AND r2.target_src LIKE 'catalog_%%' "
            "      AND r2.target_src <> r1.target_src"
            "  )" % ", ".join(lit(s) for s in regs))
    except RuntimeError:
        rows = []
    got = frozenset(
        r[0] for r in (rows or []) if r and r[0]
        and not _is_product_catalog_target(r[0]))
    _STOCK_PLACE_AXIS.update({"at": now, "set": got})
    return got


def _catalog_on_stock_eligible_register(cat):
    """Каталог — ref-ось на stock-eligible register с product-ref."""
    cat = (cat or "").strip()
    if not cat or _is_product_catalog_target(cat):
        return False
    now = time.time()
    refs = _STOCK_PLACE_REF.get("set")
    if refs is None or now - _STOCK_PLACE_REF["at"] >= 300:
        refs = set()
        _STOCK_PLACE_REF.update({"at": now, "set": refs})
    if cat in refs:
        return True
    regs = list(_stock_eligible_product_registers())
    if not regs:
        return False
    try:
        hit = psql(
            "SELECT 1 FROM search_refcols r "
            "WHERE r.target_src = %s AND r.src_table IN (%s) "
            "  AND r.col IS NOT NULL AND r.col <> '' LIMIT 1"
            % (lit(cat), ", ".join(lit(s) for s in regs)))
    except RuntimeError:
        return False
    ok = bool(hit)
    if ok:
        refs.add(cat)
    return ok


def _kind_is_stock_scoped(intent, question=""):
    """Kind относится к остаткам: product-catalog или ось места на stock-register."""
    intent = intent or {}
    kind = _intent_text(intent.get("kind"))
    if not kind:
        return False
    has_period = _intent_period_has_meaning(intent)
    cats = _catalogs_for_axis_word(kind, intent, has_period)
    if any(_is_product_catalog_target(c) for c in cats):
        return True
    place = _stock_place_axis_catalogs()
    if place and any(c in place for c in cats):
        return True
    return False


def _catalogs_are_warehouse_axis(cats, intent=None, kind_cats=None):
    """Каталог — ось места (ref на product-register), не эхо kind и не product."""
    intent = intent or {}
    cats = [c for c in (cats or []) if c and not _is_product_catalog_target(c)]
    if not cats:
        return False
    kind_cats = kind_cats if kind_cats is not None else set()
    if kind_cats and set(cats) <= kind_cats:
        return False
    place = _stock_place_axis_catalogs()
    if place and any(c in place for c in cats):
        return True
    if any(_catalog_on_stock_eligible_register(c) for c in cats):
        return True
    return False


def _catalogs_for_warehouse_axis_word(word, intent=None, allow_meaning=None):
    cats = _catalogs_for_axis_word(word, intent, allow_meaning)
    if not cats:
        return []
    intent = intent or {}
    kind = _intent_text(intent.get("kind"))
    has_period = (allow_meaning if allow_meaning is not None
                  else _intent_period_has_meaning(intent))
    kind_cats = (set(_catalogs_for_axis_word(kind, intent, has_period))
                 if kind else set())
    if _catalogs_are_warehouse_axis(cats, intent, kind_cats):
        return cats
    return []


def _question_dictionary_axis_candidates(question, intent=None):
    """Слова вопроса и terms для резолва оси через словарь базы (не kind/measure)."""
    intent = intent or {}
    skip = set()
    for key in ("kind", "measure", "action_axis"):
        w = _intent_text(intent.get(key))
        if w:
            skip.add(w.lower())
    out, seen = [], set()

    def _push(raw):
        w = _intent_text(raw)
        if not w:
            return
        wl = w.lower()
        if wl in skip or wl in seen or len(wl) < 3:
            return
        seen.add(wl)
        out.append(w)

    for group in intent.get("terms") or []:
        alts = group if isinstance(group, (list, tuple)) else [group]
        for alt in alts:
            _push(alt)
    for m in re.finditer(r"[\w\u0400-\u04ff]+", str(question or ""), re.UNICODE):
        _push(m.group(0))
    return out


def resolved_warehouse_axis_word(question, intent=None):
    """Ось места: ref-ось product-register, не любой резолв kind→catalog."""
    intent = intent or {}
    has_period = _intent_period_has_meaning(intent)
    ax = _intent_text(intent.get("action_axis"))
    if ax and _catalogs_for_warehouse_axis_word(ax, intent, has_period):
        return ax
    for w in _question_dictionary_axis_candidates(question, intent):
        if _catalogs_for_warehouse_axis_word(w, intent, has_period):
            return w
    return ""


def _word_names_documentjournal(word):
    """Слово именует journal в метаданных: stem по label+aliases documentjournal_%."""
    word = _intent_text(word)
    if not word:
        return False
    try:
        rs = psql(
            "SELECT t.src_table FROM %s t "
            "LEFT JOIN search_entity_alias a ON a.src_table = t.src_table "
            "WHERE t.src_table LIKE 'documentjournal_%%' AND list_has_any("
            "  list_filter(ts_lexize(%s, %s), x -> length(x) >= 3),"
            "  list_filter(ts_lexize(%s, concat_ws(' ', t.label, a.aliases)),"
            "              x -> length(x) >= 3)) LIMIT 1"
            % (TABLES, lit(STEM_DICT), lit(word), lit(STEM_DICT)))
    except RuntimeError:
        return False
    return bool(rs)


def resolved_unaccounted_slice_axis_word(question, intent=None):
    """Journal-ghost ось: catalog-слово именует journal, учёта остатков по оси нет.

    Слово → catalog (не kind/product), stem-матч documentjournal_% (label+aliases),
    и ось не place/не stock-eligible. Ошибка метаданных → "".
    """
    intent = intent or {}
    try:
        kind = _intent_text(intent.get("kind"))
        if not kind:
            return ""
        has_period = _intent_period_has_meaning(intent)
        kind_cats = set(_catalogs_for_axis_word(kind, intent, has_period) or [])
        if not kind_cats:
            return ""
        place = _stock_place_axis_catalogs()
        for w in _question_dictionary_axis_candidates(question, intent):
            cats = [c for c in (_catalogs_for_axis_word(w, intent, False) or [])
                    if c and c not in kind_cats
                    and not _is_product_catalog_target(c)]
            if not cats:
                continue
            if not _word_names_documentjournal(w):
                continue
            if any(c in place for c in cats):
                continue
            if any(_catalog_on_stock_eligible_register(c) for c in cats):
                continue
            return w
        return ""
    except RuntimeError:
        return ""


def intent_axis_words(intent, question=""):
    """Оси из разбора + ось места из словаря по термам вопроса."""
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
    rw = resolved_warehouse_axis_word(question, intent)
    if rw:
        wl = rw.lower()
        if wl not in seen:
            words.append(rw)
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


def secondary_axis_known(intent, question=""):
    """Вторичная ось (action_axis или словарь по термам) ≠ kind."""
    intent = intent or {}
    ax = _intent_text(intent.get("action_axis")) or resolved_warehouse_axis_word(
        question, intent)
    kind = _intent_text(intent.get("kind"))
    if not ax:
        return False
    if not kind:
        return True
    return ax.lower() != kind.lower()


def balance_axis_registers_confirmed(intent, question=""):
    """Остатковый маршрут подтверждается ref-осями в метаданных, не action_class."""
    broad = registers_for_kind_axes(intent, None, question)
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
        return balance_axis_registers_confirmed(intent, question)
    if question_wants_breakdown(intent, plan) and intent_axis_words(intent, question):
        return True
    return False


def _stock_intent_signal(intent, plan=None, question=""):
    """Сигнал остатка из разбора модели — без подтверждения метаданными."""
    intent = intent or {}
    if event_path_active(intent) or sales_kind_in_intent(intent):
        return False
    if state_path_active(intent) and intent_axis_words(intent, question):
        return True
    if question_wants_breakdown(intent, plan) and intent_axis_words(intent, question):
        return True
    return False


def balance_path_engaged(intent, plan=None, question=""):
    """Balance-path: routing по intent; sales-sum исключается."""
    if sales_sum_intent(intent or {}, question):
        return False
    return balance_routing_core(intent, plan, question)


def question_mentions_warehouse_axis(question, intent=None, plan=None):
    """Ось места: ref-ось product-register, не catalog kind-echo."""
    intent = intent or {}
    ax = resolved_warehouse_axis_word(question, intent)
    if not ax:
        return False
    return bool(_catalogs_for_warehouse_axis_word(ax, intent))


def question_has_aggregate_total_marker(question, intent=None, plan=None):
    """Итог без разреза по оси — из intent, не маркеры вопроса."""
    if not balance_routing_core(intent, plan, question):
        return False
    return aggregate_count_intent(intent, plan, question)


def question_wants_per_axis_breakdown(question, intent=None, plan=None):
    """Явный разрез по оси — want=list / max|min / порог без op."""
    return question_wants_breakdown(intent, plan)


def stock_question_engaged(question, intent=None, plan=None):
    """Stock-path: product/stock kind или ref-ось места, не справочник kind."""
    intent = intent or {}
    plan = plan or {}
    _ccq = globals().get("catalog_count_question")
    if callable(_ccq) and _ccq(intent, question):
        return False
    _ckt = globals().get("catalog_kind_total_question")
    if callable(_ckt) and _ckt(intent, question):
        return False
    stock_kind = _kind_is_stock_scoped(intent, question)
    wh = question_mentions_warehouse_axis(question, intent, plan)
    if not stock_kind and not wh:
        return False
    if balance_routing_core(intent, plan, question):
        return stock_kind or wh
    if _stock_intent_signal(intent, plan, question):
        return stock_kind or wh
    if not wh:
        return False
    return (question_has_aggregate_total_marker(question, intent, plan)
            or question_wants_per_axis_breakdown(question, intent, plan))


def registers_for_kind_axes(intent, regs=None, question=""):
    """accumulationregister_* с refcol на каталоги kind/action_axis/словарь."""
    intent = intent or {}
    has_period = _intent_period_has_meaning(intent)
    cats = set()
    for w in intent_axis_words(intent, question):
        for c in _catalogs_for_axis_word(w, intent, has_period):
            if c:
                cats.add(c)
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


def stock_count_aggregate_without_subject(intent, plan=None, question=""):
    """Count + ось места + kind-каталог без именованного предмета → distinct-агрегат.

    Структурно: want=count, action_axis≠kind, обе оси живые в метаданных,
    terms/measure вне скаффолда нет — не subject-clarify (K9).
    """
    intent = intent or {}
    want = (intent.get("want") or "").strip().lower()
    if want not in ("count", ""):
        return False
    if not balance_path_engaged(intent, plan, question):
        return False
    if stock_asks_named_product(question, intent):
        return False
    if not aggregate_count_intent(intent, plan, question):
        return False
    if not secondary_axis_known(intent, question):
        return False
    if not question_mentions_warehouse_axis(question, intent, plan):
        return False
    kind = _intent_text(intent.get("kind"))
    if not kind:
        return False
    period = intent.get("period") or {}
    has_period = bool(period.get("from") or period.get("to"))
    try:
        if not entity_form_catalogs_for_kind(kind, allow_meaning=has_period):
            return False
    except RuntimeError:
        return False
    return True


def grain_dec_from_axis_ticket(intent, plan, grain_dec, prov_axis, question=""):
    """Билет оси: grain=group сохраняется; form=rank при рейтинговом вопросе."""
    rankish = rank_intent_from(intent, plan, question) or (
        (grain_dec or {}).get("form") in ("rank", "compare"))
    form = "rank" if rankish else ((grain_dec or {}).get("form") or "number")
    return {"grain": "group", "col": prov_axis, "form": form,
            "named_gis": [], "clarify": None}


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


def _is_product_catalog_target(target):
    fn = globals().get("_is_product_catalog")
    if callable(fn):
        return bool(fn(target))
    return False


def _stock_registers_with_product_axis(regs):
    """accumulationregister_* с refcol на товарный catalog (ось ТМЦ)."""
    pool = list(regs or [])
    if not pool:
        return frozenset()
    try:
        rows = psql(
            "SELECT DISTINCT r.src_table, r.target_src FROM search_refcols r "
            "WHERE r.src_table IN (%s) AND r.col IS NOT NULL AND r.col <> ''"
            % ", ".join(lit(s) for s in pool))
    except RuntimeError:
        return frozenset()
    by_src = {}
    for r in rows or []:
        if not r or not r[0]:
            continue
        by_src.setdefault(r[0], set()).add((r[1] if len(r) > 1 else "") or "")
    return frozenset(
        src for src, tgts in by_src.items()
        if any(_is_product_catalog_target(t) for t in tgts if t))


def _stock_product_targets_by_src(pool):
    pool = list(pool or [])
    if not pool:
        return {}
    try:
        rows = psql(
            "SELECT DISTINCT r.src_table, r.target_src FROM search_refcols r "
            "WHERE r.src_table IN (%s) AND r.col IS NOT NULL AND r.col <> ''"
            % ", ".join(lit(s) for s in pool))
    except RuntimeError:
        return {}
    out = {}
    for r in rows or []:
        if not r or not r[0]:
            continue
        t = (r[1] if len(r) > 1 else "") or ""
        if _is_product_catalog_target(t):
            out.setdefault(r[0], set()).add(t)
    return {k: frozenset(v) for k, v in out.items()}


def _stock_refs_by_src(pool):
    pool = list(pool or [])
    if not pool:
        return {}
    try:
        rows = psql(
            "SELECT DISTINCT r.src_table, r.target_src FROM search_refcols r "
            "WHERE r.src_table IN (%s) AND r.col IS NOT NULL AND r.col <> ''"
            % ", ".join(lit(s) for s in pool))
    except RuntimeError:
        return {}
    out = {}
    for r in rows or []:
        if not r or not r[0]:
            continue
        out.setdefault(r[0], set()).add((r[1] if len(r) > 1 else "") or "")
    return out


def _stock_cost_side_penalty(src, pool, product_targets_by_src, refs_by_src):
    """Больше non-product ref при той же товарной оси — затратная сторона."""
    pt = (product_targets_by_src or {}).get(src) or frozenset()
    if not pt:
        return 0
    my_n = _non_product_ref_targets((refs_by_src or {}).get(src))
    sibs = [s for s in (pool or []) if s != src
            and ((product_targets_by_src or {}).get(s) or frozenset()) == pt]
    if not sibs:
        return 0
    min_n = min([my_n] + [_non_product_ref_targets((refs_by_src or {}).get(s))
                            for s in sibs])
    return 1 if my_n > min_n else 0


def _stock_corpus_receipt_side_penalty(src, pool, corpus_counts, product_targets_by_src):
    """При той же товарной оси меньше строк корпуса — приход, не затраты (okna live)."""
    pt = (product_targets_by_src or {}).get(src) or frozenset()
    if not pt:
        return 0
    my_n = int((corpus_counts or {}).get(src) or 0)
    sibs = [s for s in (pool or []) if s != src
            and ((product_targets_by_src or {}).get(s) or frozenset()) == pt]
    if not sibs:
        return 0
    min_n = min([my_n] + [int((corpus_counts or {}).get(s) or 0) for s in sibs])
    return 0 if my_n == min_n else 1


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


def _stock_register_rank_key(src, capable=None, corpus_counts=None,
                               product_targets_by_src=None, pool=None,
                               refs_by_src=None):
    s = str(src or "").lower()
    cc = corpus_counts or {}
    return (
        1 if stock_balance_is_sales_noise(s) else 0,
        1 if stock_balance_is_reversal_noise(s) else 0,
        _stock_cost_side_penalty(src, pool, product_targets_by_src, refs_by_src),
        _stock_corpus_receipt_side_penalty(src, pool, cc, product_targets_by_src),
        0 if capable and src in capable else 1,
        0 if s.startswith("accumulationregister_") else 1,
        s)


def _sort_stock_pool(pool, capable=None):
    pool = list(pool or [])
    snap = list(pool)
    counts = _stock_corpus_counts(pool)
    pt_map = _stock_product_targets_by_src(pool)
    refs_map = _stock_refs_by_src(pool)
    pool.sort(key=lambda s: _stock_register_rank_key(
        s, capable, counts, pt_map, snap, refs_map))
    return pool


def _stock_product_axis_cols(src):
    """Все product-catalog refcol регистра (без silent first)."""
    src = (src or "").strip()
    if not src:
        return []
    try:
        ax = refcols_of(src) or []
    except RuntimeError:
        return []
    cols, seen = [], set()
    for a in ax:
        if _is_product_catalog_target(a.get("target_src") or ""):
            col = (a.get("col") or "").strip()
            if col and col not in seen:
                seen.add(col)
                cols.append(col)
    return cols


def _stock_product_axis_col(src):
    """Колонка refs_map на product-catalog: ровно одна → взять; >1 → None."""
    cols = _stock_product_axis_cols(src)
    return cols[0] if len(cols) == 1 else None


def _stock_qty_measure_candidates(src):
    """Кандидаты qty-меры регистра: sole → [got]; >1 → alts; silent names[0] нет."""
    src = (src or "").strip()
    if not src:
        return []
    try:
        names = list(measures_of(src) or [])
    except RuntimeError:
        return []
    if not names:
        return []
    if len(names) == 1:
        return names
    try:
        alias_by = measure_aliases_of(src) or {}
    except RuntimeError:
        alias_by = {}
    got, alts, how = measure_choice(names, "колич", alias_by=alias_by)
    if got and how in ("exact", "substring", "alias", "single"):
        return [got]
    if how == "ask" and alts:
        return list(alts)
    return []


def _stock_qty_measure_name(src):
    """Количественная мера регистра — sole после measure_choice; >1 → None."""
    cands = _stock_qty_measure_candidates(src)
    return cands[0] if len(cands) == 1 else None


def _stock_receipt_candidates(active, pt_map, refs_map, corpus_counts):
    """Не-sales регистры; cost/corpus — отсев классификатором, не silent max."""
    active = list(active or [])
    non_sales = [s for s in active if not stock_balance_is_sales_noise(s)]
    if len(non_sales) <= 1:
        return non_sales
    snap = list(active)
    no_cost = [s for s in non_sales
               if _stock_cost_side_penalty(s, snap, pt_map, refs_map) == 0]
    pool = no_cost if no_cost else non_sales
    if len(pool) == 1:
        return pool
    no_corp = [s for s in pool
               if _stock_corpus_receipt_side_penalty(
                   s, snap, corpus_counts, pt_map) == 0]
    if len(no_corp) == 1:
        return no_corp
    return pool


def stock_net_pair_candidates(intent, question=""):
    """Уникальные пары + неоднозначные регистры (S2-c: >1 → меню, не silent).

    Возвращает (pairs, ambiguous_regs):
      pairs — list[(receipt, expense, prod_col, qty)]
      ambiguous_regs — регистры, где роль/пара не единственна.
    """
    intent = intent or {}
    try:
        capable = balance_capable_or_registers()
    except RuntimeError:
        return [], []
    broad = registers_for_kind_axes(intent, None, question)
    if not broad:
        return [], []
    pool = list(_stock_registers_with_product_axis(broad))
    if len(pool) < 2:
        return [], []
    pt_map = _stock_product_targets_by_src(pool)
    cc = _stock_corpus_counts(pool)
    refs_map = _stock_refs_by_src(pool)
    by_pt = {}
    for src in pool:
        pt = pt_map.get(src)
        if pt:
            by_pt.setdefault(pt, []).append(src)
    pairs = []
    ambiguous = []
    for _pt, siblings in by_pt.items():
        if len(siblings) < 2:
            continue
        active = [s for s in siblings if not stock_balance_is_reversal_noise(s)]
        if len(active) < 2:
            continue
        expenses = [s for s in active if stock_balance_is_sales_noise(s)]
        receipts = _stock_receipt_candidates(active, pt_map, refs_map, cc)
        # capable — отсев непригодных, не выбор среди равных
        if capable:
            receipts = [s for s in receipts if s in capable] or receipts
            expenses = [s for s in expenses if s in capable] or expenses
        if len(receipts) == 1 and len(expenses) == 1 and receipts[0] != expenses[0]:
            receipt, expense = receipts[0], expenses[0]
            prod_col = (_stock_product_axis_col(receipt)
                        or _stock_product_axis_col(expense))
            qty = (_stock_qty_measure_name(receipt)
                   or _stock_qty_measure_name(expense))
            if prod_col and qty:
                pairs.append((receipt, expense, prod_col, qty))
            else:
                ambiguous.extend(active)
        else:
            ambiguous.extend(active)
    # дедуп ambiguous, порядок стабильный
    seen = set()
    amb_out = []
    for s in ambiguous:
        if s not in seen:
            seen.add(s)
            amb_out.append(s)
    return pairs, amb_out


def stock_net_register_menu_opts(intent, question=""):
    """Options[] регистров для readings_menu при неоднозначной паре/роли."""
    pairs, ambig = stock_net_pair_candidates(intent, question)
    regs = list(ambig)
    if len(pairs) > 1:
        for receipt, expense, _pc, _q in pairs:
            for s in (receipt, expense):
                if s not in regs:
                    regs.append(s)
    if len(regs) < 2 and len(pairs) > 1:
        # пары однозначны по роли, но их несколько — меню пар по receipt-src
        opts = []
        lab_by = {}
        srcs = []
        for receipt, expense, _pc, _q in pairs:
            srcs.extend([receipt, expense])
        srcs = list(dict.fromkeys(srcs))
        if srcs:
            try:
                for r in psql(
                        "SELECT src_table, label FROM %s WHERE src_table IN (%s)"
                        % (TABLES, ", ".join(lit(s) for s in srcs))) or []:
                    if r and r[0]:
                        lab_by[r[0]] = (r[1] or "").strip()
            except RuntimeError:
                pass
        for receipt, expense, _pc, _q in pairs:
            lr = human_table_label(receipt, lab_by.get(receipt))
            le = human_table_label(expense, lab_by.get(expense))
            kw = kind_word(receipt) or "регистр"
            opts.append({
                "src": receipt,
                "label": "%s − %s (%s)" % (lr, le, kw),
                "entity_label": lr,
            })
        return opts if len(opts) >= 2 else []
    if len(regs) < 2:
        return []
    lab_by = {}
    try:
        for r in psql(
                "SELECT src_table, label FROM %s WHERE src_table IN (%s)"
                % (TABLES, ", ".join(lit(s) for s in regs))) or []:
            if r and r[0]:
                lab_by[r[0]] = (r[1] or "").strip()
    except RuntimeError:
        pass
    opts = []
    for reg in regs:
        lab = human_table_label(reg, lab_by.get(reg))
        kw = kind_word(reg) or "регистр"
        role = ("расход" if stock_balance_is_sales_noise(reg) else "приход")
        opts.append({
            "src": reg,
            "label": "%s (%s, %s)" % (lab, kw, role),
            "entity_label": lab,
        })
    return opts


def stock_net_register_pair(intent, question=""):
    """Пара приход/расход одной товарной оси — sole; >1 → None (меню выше)."""
    pairs, ambig = stock_net_pair_candidates(intent, question)
    if ambig or len(pairs) != 1:
        return None
    return pairs[0]


def aggregate_stock_net_distinct(intent, question, match, preds, diag=None):
    """COUNT(DISTINCT product) WHERE net qty > 0: приход − расход по паре регистров.

    Доки: Sql › Functions › Aggregate Functions › DISTINCT Clause in Aggregate
    Functions; try_cast — Sql › Functions › Conversion Functions.
    """
    pair = stock_net_register_pair(intent, question)
    if not pair:
        return None
    receipt, expense, prod_col, qty_measure = pair
    diag = dict(diag or {})
    diag["stock_net_pair"] = {
        "receipt": receipt, "expense": expense,
        "axis": prod_col, "measure": qty_measure}

    def _side_where(src_table):
        parts = [w for w in (
            [match] + list(preds or [])
            + ["src_table = %s" % lit(src_table),
               "map_extract_value(refs_map, %s) IS NOT NULL" % lit(prod_col),
               "map_extract(nums, %s)[1] IS NOT NULL" % lit(qty_measure)]) if w]
        return " AND ".join(parts)

    qty_expr = "try_cast(map_extract(nums, %s)[1] AS DOUBLE)" % lit(qty_measure)
    prod_expr = "map_extract_value(refs_map, %s)" % lit(prod_col)
    sql = (
        "WITH receipt AS ("
        "  SELECT %s AS prod, sum(%s) AS qty FROM %s WHERE %s GROUP BY 1"
        "), expense AS ("
        "  SELECT %s AS prod, sum(%s) AS qty FROM %s WHERE %s GROUP BY 1"
        "), net AS ("
        "  SELECT coalesce(r.prod, e.prod) AS prod,"
        "         coalesce(r.qty, 0) - coalesce(e.qty, 0) AS net_qty"
        "    FROM receipt r FULL OUTER JOIN expense e ON r.prod = e.prod"
        ") SELECT count(DISTINCT prod) FROM net WHERE net_qty > 0"
    ) % (prod_expr, qty_expr, CORPUS, _side_where(receipt),
         prod_expr, qty_expr, CORPUS, _side_where(expense))
    try:
        rows = psql(sql)
    except RuntimeError:
        return None
    if not rows or not rows[0] or rows[0][0] in ("", None):
        return None
    try:
        n = int(float(rows[0][0]))
    except (TypeError, ValueError):
        return None
    return {"count": n, "sum": None, "src": receipt, "form": "distinct_axis",
            "axis": prod_col, "grain": "axis", "net_expense_src": expense}


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


register_zone('ask.z12_stock_balance', globals())
