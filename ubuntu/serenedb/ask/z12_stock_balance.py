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
