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


def _catalogs_joint_with_kind(cats, kind_cats):
    """Есть ли носитель (регистр/документ) с refcol и на cats, и на kind_cats.

    Тот же EXISTS-паттерн, что у _stock_place_axis_catalogs, но без пула
    stock-eligible: совместный учёт kind×ось по любому движению.
    Доки: Sql › Expressions › Subqueries › EXISTS.
    """
    cats = [c for c in (cats or []) if c]
    kind_cats = [c for c in (kind_cats or []) if c]
    if not cats or not kind_cats:
        return False
    rows = psql(
        "SELECT 1 FROM search_refcols r1 "
        "WHERE r1.target_src IN (%s) "
        "  AND r1.col IS NOT NULL AND r1.col <> '' "
        "  AND (r1.src_table LIKE 'accumulationregister_%%' "
        "       OR r1.src_table LIKE 'document_%%') "
        "  AND EXISTS ("
        "    SELECT 1 FROM search_refcols r2 "
        "    WHERE r2.src_table = r1.src_table "
        "      AND r2.target_src IN (%s) "
        "      AND r2.col IS NOT NULL AND r2.col <> ''"
        "  ) LIMIT 1"
        % (", ".join(lit(c) for c in cats),
           ", ".join(lit(c) for c in kind_cats)))
    return bool(rows)


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


def question_asks_stock_balance(question, intent=None, plan=None):
    """Вопрос про остаток — триггер balance-path (intent, не слова вопроса)."""
    return balance_path_engaged(intent, plan, question)


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


def warehouse_axis_values(limit=20, intent=None, question=""):
    """Имена складов: axis_catalog_values по action_axis/kind/словарю."""
    intent = intent or {}
    for w in intent_axis_words(intent, question):
        vals = axis_catalog_values(w, limit=limit, intent=intent)
        if vals:
            return vals
    ax = resolved_warehouse_axis_word(question, intent)
    if ax:
        return axis_catalog_values(ax, limit=limit, intent=intent)
    return []


def warehouse_axis_is_live(intent=None, question=""):
    """Живая ось места хранения: ≥2 значений из метаданных."""
    try:
        wh = warehouse_axis_values(intent=intent, question=question)
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
    if aggregate_count_intent(intent, plan, question) and secondary_axis_known(
            intent, question):
        return True
    return False


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


def stock_subject_needs_clarify(question, intent=None):
    if not balance_path_engaged(intent, None, question):
        return False
    if stock_asks_named_product(question, intent):
        return False
    if stock_count_aggregate_without_subject(intent, None, question):
        return False
    if aggregate_count_intent(intent, None, question):
        return True
    if not secondary_axis_known(intent, question) and not (intent or {}).get("terms"):
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


def _stock_expense_side_penalty(src, pool, corpus_counts, product_targets_by_src):
    """Corpus-count не различает приход/затраты на okna — см. _stock_cost_side_penalty."""
    return 0


def stock_goods_pool(capable=None, intent=None, question=""):
    """Пул товарных balance-регистров: оси intent + ref на catalog ТМЦ."""
    capable = capable if capable is not None else balance_capable_or_registers()
    if not intent:
        return frozenset()
    broad = registers_for_kind_axes(intent, None, question)
    if not broad:
        return frozenset()
    clean = {s for s in broad if not register_is_balance_noise(s)}
    product_axis = _stock_registers_with_product_axis(clean)
    if product_axis:
        clean = {s for s in clean if s in product_axis}
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


def _stock_product_axis_col(src):
    """Колонка refs_map на product-catalog для регистра."""
    src = (src or "").strip()
    if not src:
        return None
    try:
        ax = refcols_of(src) or []
    except RuntimeError:
        return None
    for a in ax:
        if _is_product_catalog_target(a.get("target_src") or ""):
            col = (a.get("col") or "").strip()
            if col:
                return col
    return None


def _stock_qty_measure_name(src):
    """Количественная мера регистра — measure_choice, не имя поля."""
    src = (src or "").strip()
    if not src:
        return None
    try:
        names = list(measures_of(src) or [])
    except RuntimeError:
        return None
    if not names:
        return None
    try:
        alias_by = measure_aliases_of(src) or {}
    except RuntimeError:
        alias_by = {}
    got, _, how = measure_choice(names, "колич", alias_by=alias_by)
    if got and how in ("exact", "substring", "alias", "base", "single"):
        return got
    return names[0] if names else None


def stock_net_register_pair(intent, question=""):
    """Пара приход/расход одной товарной оси — по метаданным refcols и роли."""
    intent = intent or {}
    try:
        capable = balance_capable_or_registers()
    except RuntimeError:
        return None
    broad = registers_for_kind_axes(intent, None, question)
    if not broad:
        return None
    pool = list(_stock_registers_with_product_axis(broad))
    if len(pool) < 2:
        return None
    pt_map = _stock_product_targets_by_src(pool)
    cc = _stock_corpus_counts(pool)
    by_pt = {}
    for src in pool:
        pt = pt_map.get(src)
        if pt:
            by_pt.setdefault(pt, []).append(src)
    for _pt, siblings in by_pt.items():
        if len(siblings) < 2:
            continue
        active = [s for s in siblings if not stock_balance_is_reversal_noise(s)]
        if len(active) < 2:
            continue
        sorted_s = _sort_stock_pool(list(active), capable)
        receipt = None
        expense = None
        for s in sorted_s:
            if not stock_balance_is_sales_noise(s):
                receipt = s
                break
        for s in sorted_s:
            if stock_balance_is_sales_noise(s):
                expense = s
                break
        if not receipt:
            receipt = sorted_s[0]
        if not expense:
            others = [s for s in sorted_s if s != receipt]
            if others:
                expense = max(others, key=lambda s: cc.get(s, 0))
        if not receipt or not expense or receipt == expense:
            continue
        prod_col = _stock_product_axis_col(receipt) or _stock_product_axis_col(expense)
        qty = _stock_qty_measure_name(receipt) or _stock_qty_measure_name(expense)
        if prod_col and qty:
            return receipt, expense, prod_col, qty
    return None


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
    if not warehouse_axis_is_live(intent, question):
        return None
    intent = intent or {}
    axis_word = (resolved_warehouse_axis_word(question, intent)
                 or _intent_text(intent.get("action_axis"))
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
