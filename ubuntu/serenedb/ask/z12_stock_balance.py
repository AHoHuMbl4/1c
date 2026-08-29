"""Zone 12: Остатки (stock-balance)."""
from __future__ import annotations

from ask._imports import *
from ask._wire import register_zone, apply_bindings

apply_bindings(globals())

def grain_dec_from_axis_ticket(intent, plan, grain_dec, prov_axis, question=""):
    """Билет оси: grain=group сохраняется; form=rank при рейтинговом вопросе."""
    rankish = rank_intent_from(intent, plan, question) or (
        (grain_dec or {}).get("form") in ("rank", "compare"))
    form = "rank" if rankish else ((grain_dec or {}).get("form") or "number")
    return {"grain": "group", "col": prov_axis, "form": form,
            "named_gis": [], "clarify": None}


def _rank_wants_quantity(question):
    q = (question or "").lower()
    return (any(w in q for w in ("товар", "номенклатур", "product", "item", "goods"))
            and any(w in q for w in ("больше всего", "сколько", "top", "most",
                                     "maximum", "лидер", "leader")))


def rank_measure_hint(names, intent, question, alias_by=None):
    """Рейтинг без явной меры: количество товара, не себестоимость/сумма."""
    names = list(names or [])
    if not names:
        return None
    if (intent or {}).get("measure"):
        return None
    if not rank_intent_from(intent, question=question):
        return None
    q = (question or "").lower()
    kind = ((intent or {}).get("kind") or "").lower()
    hints = []
    if any(w in q for w in ("сколько", "больше всего", "top", "most", "maximum",
                            "лидер", "leader")):
        hints.append("количество")
    if any(w in kind for w in ("товар", "номенклатур", "product", "item", "goods")):
        hints.append("количество")
    if any(w in q for w in ("товар", "номенклатур", "product", "item", "goods")):
        hints.append("количество")
    seen = set()
    for hint in hints:
        if hint in seen:
            continue
        seen.add(hint)
        got, _alts, how = measure_choice(names, hint, alias_by=alias_by or {})
        if got and how in ("exact", "substring", "alias", "base", "single"):
            return got
    return None


_BALANCE_REGS = {"at": 0.0, "set": None}
_BALANCE_MAP = {"at": 0.0, "rows": None}

_STOCK_MARKERS = (
    "остат", "на складе", "in stock", "on warehouse", "inventory balance",
    "stoc", "depozit", "magazin", "inventar",
    # K4-1 №12: «лежит» (складах/вместе закрывает subject-clarify, не голый «склад»).
    "леж",
)

# Класс оси места хранения в вопросе (ru+en), не имя реквизита базы.
_WAREHOUSE_AXIS_MARKERS = (
    "склад", "warehouse", "storage", "depot", "depozit", "magazin",
)

# Класс маркеров итога без разреза (ru+en), не список фраз конкретного диалога.
_AGGREGATE_TOTAL_MARKERS = (
    "всего", "итого", "итог ", " overall", " in total", " total ",
    "grand total", "на всех", " together", " altogether",
)

# «вместе» — итог только при оси места хранения (не «работаем вместе»).
_AGGREGATE_TOGETHER_MARKERS = ("вместе", " together")

# Класс явного разреза «пo каждому …» (ru+en), не привязка к оси склада.
_PER_AXIS_BREAKDOWN_MARKERS = (
    "по кажд", " each ", " per ", "отдельно", " separately",
    "разбив", " breakdown", " split by", "разрез",
)

# Рейтинговые «… всего» — не маркер суммарного итога (ловушка подстроки «всего»).
_RANK_NOT_AGGREGATE = (
    "больше всего", "меньше всего", "лучше всего", "хуже всего",
    "больше всех", "меньше всех", "лучше всех", "хуже всех",
    "most ", " least ", "best selling", "top seller",
)


def question_mentions_warehouse_axis(question):
    """Вопрос про ось места хранения — класс слов, не список складов базы."""
    q = " ".join(str(question or "").lower().split())
    if not q:
        return False
    return any(m in q for m in _WAREHOUSE_AXIS_MARKERS)


def question_has_aggregate_total_marker(question, intent=None, plan=None):
    """Итог «всего»/total — развилка по измерению (склад и др.) не задаётся."""
    if rank_intent_from(intent or {}, plan or {}, question):
        return False
    q = " ".join(str(question or "").lower().split())
    if not q:
        return False
    if any(m in q for m in _RANK_NOT_AGGREGATE):
        return False
    if any(m in q for m in _AGGREGATE_TOTAL_MARKERS):
        return True
    if question_mentions_warehouse_axis(question):
        return any(m in q for m in _AGGREGATE_TOGETHER_MARKERS)
    return False


def stock_question_engaged(question, intent=None, plan=None):
    """Stock-path: остатки или ось склада с суммарным итогом / явным разрезом."""
    if question_asks_stock_balance(question):
        return True
    if not question_mentions_warehouse_axis(question):
        return False
    return (question_has_aggregate_total_marker(question, intent, plan)
            or question_wants_per_axis_breakdown(question, intent, plan))


def question_wants_per_axis_breakdown(question, intent=None, plan=None):
    """Явный разрез по оси (список/пo каждому), не суммарный итог."""
    if question_wants_breakdown(intent, plan):
        return True
    q = " ".join(str(question or "").lower().split())
    if not q:
        return False
    return any(m in q for m in _PER_AXIS_BREAKDOWN_MARKERS)


def warehouse_axis_is_live():
    """Живая ось места хранения: несколько значений из базы (K7)."""
    try:
        wh = warehouse_axis_values()
    except RuntimeError:
        return False
    return len(wh or []) >= 2


def stock_skips_warehouse_clarify(question, intent=None, plan=None):
    """Не уточнять склад: итог без разреза, явный разрез, или все склады названы."""
    stockish = question_asks_stock_balance(question)
    wh_axis = question_mentions_warehouse_axis(question)
    if not stockish and not wh_axis:
        return False
    if question_has_aggregate_total_marker(question, intent, plan):
        return True
    if question_wants_per_axis_breakdown(question, intent, plan):
        return True
    q = " ".join(str(question or "").lower().split())
    if q and any(w in q for w in ("всех", "всеми", "all warehouses", "all stocks")):
        return True
    return False


def _resolve_breakdown_balance_src(src, cands=None):
    """Balance-регистр с товарной осью для итога+люка; каталог складов не годится."""
    try:
        cap = balance_capable_or_registers()
        goods = stock_goods_pool(cap)
    except RuntimeError:
        return src or None
    goods = {c for c in (goods or []) if not stock_balance_is_sales_noise(c)}
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
    """Исход B при живой оси и запросе разреза, если GROUP BY ещё недоступен (K7, не K8).

    Считаемый лидер-итог + люк из значений оси склада; пустой отказ не отдаём.
    """
    if not question_wants_per_axis_breakdown(question, intent, plan):
        return None
    if not warehouse_axis_is_live():
        return None
    wh = []
    try:
        wh = list(warehouse_axis_values() or [])
    except RuntimeError:
        return None
    if len(wh) < 2:
        return None
    src = _resolve_breakdown_balance_src(src, cands)
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


def question_asks_stock_balance(question):
    """Вопрос про остаток на складе — триггер универсального пути остатков."""
    q = " ".join(str(question or "").lower().split())
    if not q:
        return False
    return any(m in q for m in _STOCK_MARKERS)


def balance_registers_with_goods(regs=None):
    """Остаточные регистры, у которых в корпусе есть ось ТМЦ (склады/товары).

    `balance_registers` из $metadata включает RecordType-регистры без товарной оси
    (зарплата, ОС, номера БСО) — их наличие не значит «есть остатки на складе».
    """
    regs = regs if regs is not None else balance_registers()
    if not regs:
        return frozenset()
    rows = psql(
        "SELECT DISTINCT src_table FROM %s WHERE src_table IN (%s) "
        "AND map_extract_value(refs_map, 'ТМЦ') IS NOT NULL"
        % (CORPUS, ", ".join(lit(r) for r in regs)))
    return frozenset(r[0] for r in (rows or []) if r and r[0])


def stock_goods_pool(capable=None):
    """Регистры движения с товарной осью: balance_map + fallback по search_refcols.

    На okna `импорттмц` есть в корпусе, но не в balance_registers $metadata —
    без fallback stock-path пустой и вопрос уходит в каталог/документ.
    """
    capable = capable if capable is not None else balance_capable_or_registers()
    goods = balance_registers_with_goods(capable) if capable else frozenset()
    if goods:
        return goods
    try:
        rows = psql(
            "SELECT DISTINCT c.src_table FROM %s c "
            "WHERE c.src_table LIKE 'accumulationregister_%%' "
            "  AND c.nums IS NOT NULL AND len(map_keys(c.nums)) > 0 "
            "  AND EXISTS ("
            "    SELECT 1 FROM search_refcols r "
            "    WHERE r.src_table = c.src_table "
            "      AND r.target_src LIKE 'catalog_%%' "
            "      AND (r.target_src LIKE '%%номенклатур%%' "
            "           OR r.target_src LIKE '%%nomencl%%' "
            "           OR r.target_src LIKE '%%товар%%' "
            "           OR r.target_src LIKE '%%product%%')) "
            "GROUP BY 1 HAVING count(*) > 0" % CORPUS)
    except RuntimeError:
        return frozenset()
    return frozenset(r[0] for r in (rows or []) if r and r[0])


def _stock_register_rank_key(src, capable=None):
    """Порядок выбора balance-источника без имён конкретной базы."""
    s = str(src or "").lower()
    return (
        1 if stock_balance_is_sales_noise(s) else 0,
        0 if capable and src in capable else 1,
        0 if s.startswith("accumulationregister_") else 1,
        s)


def stock_canon_src(cands, question, intent=None, plan=None):
    """Src канона остатков: accumulation с товарной осью, не каталог/табчасть."""
    if not stock_question_engaged(question, intent, plan):
        return None
    capable = balance_capable_or_registers()
    pool = [c for c in stock_goods_pool(capable)
            if not stock_balance_is_sales_noise(c)]
    if not pool:
        return None
    pool.sort(key=lambda s: _stock_register_rank_key(s, capable))
    in_cands = [c for c in (cands or []) if c in pool]
    if in_cands:
        in_cands.sort(key=lambda s: _stock_register_rank_key(s, capable))
        return in_cands[0]
    return pool[0]


def prefer_entity_for_stock(cands, question, intent=None, plan=None):
    """Stock-path: balance-регистр в голове, каталоги/документы вне пула."""
    canon = stock_canon_src(cands, question, intent, plan)
    if not canon:
        return cands
    capable = balance_capable_or_registers()
    pool = {c for c in stock_goods_pool(capable)
            if not stock_balance_is_sales_noise(c)}
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
    """Основы «темы» остатков: kind + маркеры вопроса; measure — отдельно (именованность).

    🔴 В СКАФФОЛД ИДЁТ ТОЛЬКО РОД, ИЗВЕСТНЫЙ БАЗЕ (28.08). [замер AB_PROBE okna]
    парсер назвал родом «петли» — такого рода в базе нет, но стемы kind попадали
    в скаффолд «темы», и предмет вопроса сам себе становился темой: именованный
    товар не опознавался, «сколько петель осталось на складе» шло в уточнение
    склада вместо честного «нет данных». Неизвестное слово — догадка о предмете
    (п. 12), темой его делает только словарь базы.
    """
    parts = []
    v = (intent or {}).get("kind") or ""
    if v and _base_knows_kind_or_measure(v):
        parts.append(str(v))
    q = " ".join(str(question or "").lower().split())
    for m in _STOCK_MARKERS:
        if m in q:
            parts.append(m)
    out = set()
    for part in parts:
        out |= _stems_of_text(part)
    return out


def stock_asks_named_product(question, intent=None):
    """Именованный товар — terms разбора и measure (live: «петли» часто в measure)."""
    if not question_asks_stock_balance(question):
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
