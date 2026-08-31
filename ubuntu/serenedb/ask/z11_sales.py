"""Zone 11: Продажи (sales)."""
from __future__ import annotations

from ask._imports import *
from ask._wire import register_zone, apply_bindings

apply_bindings(globals())


def sales_kind_in_intent(intent):
    """Kind/measure из разбора несёт sales-семантику — не остатковый state-path."""
    intent = intent or {}
    kind = (intent.get("kind") or "").strip().lower()
    measure = (intent.get("measure") or "").strip().lower()
    if any(w in kind for w in ("продаж", "торг", "выруч", "sale", "revenue")):
        return True
    return any(w in measure for w in (
        "продали", "продал", "продаж", "наторговали", "торги", "sold", "sales"))


def sales_sum_intent(intent, question=""):
    """Вопрос про сумму/оборот продаж («продали», «наторговали») — не остаток/прайс."""
    intent = intent or {}
    q = " ".join(str(question or "").lower().split())
    want = (intent.get("want") or "").strip().lower()
    kind = (intent.get("kind") or "").strip().lower()
    measure = (intent.get("measure") or "").strip().lower()
    if any(w in q for w in ("прайс", "price list", "в прайсе")):
        return False
    sale_q = any(w in q for w in (
        "продали", "продал", "продаж", "наторговали", "наторгова",
        "выручк", "оборот", "sold", "sales", "revenue"))
    sale_k = any(w in kind for w in ("продаж", "торг", "выруч", "sale", "revenue"))
    sale_m = any(w in measure for w in (
        "продали", "продал", "продаж", "наторговали", "торги", "sold", "sales"))
    _period_hint = (
        any(w in q for w in ("недел", "месяц", "квартал", "week", "month", "прошл"))
        or bool(_months_mentioned(q)))
    # Superlative/top-N is axis rank, not two-window compare (same gate as
    # sales_compare_intent). Bare "больше"+"месяц" without pair marker stays out.
    _superl = any(w in q for w in (
        "лучше всего", "хуже всего", "лучше всех", "хуже всех",
        "больше всего", "меньше всего", "больше всех", "меньше всех",
        "топ-", "топ ", " top", "лидер", "рейтинг", "leader", "ranking"))
    compare_period = (
        (not _superl)
        and (
            any(w in q for w in ("лучше", "хуже", "больше чем", "меньше чем",
                                 "больше, чем", "меньше, чем"))
            or any(w in q for w in (
                "насколько", "на сколько", "сравни", "против", "по сравнению"))
            or (any(w in q for w in ("больше", "меньше"))
                and ("прошл" in q or len(_months_mentioned(q)) >= 1)
                and any(w in q for w in (
                    "чем", "против", "сравни", "насколько", "на сколько",
                    "эт", "текущ", "this", "current")))
        )
        and _period_hint
        and not any(w in q for w in (
            "сотрудник", "табель", "зарплат", "фота", "отработ", "employee", "payroll"))
    )
    sale_signal = sale_q or sale_k or sale_m
    if not (sale_signal or compare_period):
        return False
    # Sale в вопросе/kind/measure сильнее balance_routing_core: иначе «продали»
    # + object-ось → qty вместо денег ([замер :8092] 99898 vs money).
    if (not sale_signal) and balance_routing_core(intent, None, question):
        return False
    if want in ("sum", "count", "list", ""):
        return True
    return want not in ("avg",)


def _sales_register_score(src, measures):
    """Движения с количеством+итого выше книги НДС/VAT по тому же регистратору."""
    s = (src or "").lower()
    ms = {(m or "").lower() for m in (measures or [])}
    score = 0
    if any("количество" in m or m in ("quantity", "qty", "count") for m in ms):
        score += 10
    if any(m in ("всего", "сумма", "total", "amount") or "всего" in m for m in ms):
        score += 3
    if any("ндс" in m or "vat" in m for m in ms) and score < 10:
        score -= 4
    if "книга" in s or "ндс" in s or "vat" in s:
        score -= 8
    if "реализац" in s or "продаж" in s or "sale" in s:
        score += 2
    return score


def sales_lift_possible(cands):
    """Структурный подъём sales-register по written_by из кандидатов (без cold).

    True, если в cands уже есть не-книга accumulationregister_* либо document_*
    (или parent/written_by → document), с которого поднимается регистр движений.
    """
    cands = list(cands or [])
    if not cands:
        return False
    for c in cands:
        if (str(c).startswith("accumulationregister_")
                and not sales_noncanon_focus(c)):
            return True
    try:
        rs = psql(
            "SELECT src_table, parent, written_by FROM %s WHERE src_table IN (%s)"
            % (TABLES, ", ".join(lit(c) for c in cands)))
    except RuntimeError:
        return False
    docs = set()
    for r in rs or []:
        if not r or not r[0]:
            continue
        c = r[0]
        if str(c).startswith("document_"):
            docs.add(c)
        p = (r[1] if len(r) > 1 else "") or ""
        if p.startswith("document_"):
            docs.add(p)
        w = (r[2] if len(r) > 2 else "") or ""
        if w.startswith("document_"):
            docs.add(w)
    for c in cands:
        if str(c).startswith("document_"):
            docs.add(c)
    if not docs:
        return False
    try:
        lifted = psql(
            "SELECT src_table FROM %s WHERE src_table LIKE "
            "'accumulationregister_%%' AND written_by IN (%s) LIMIT 1"
            % (TABLES, ", ".join(lit(d) for d in docs)))
    except RuntimeError:
        return False
    return bool(lifted and lifted[0] and lifted[0][0])


def sales_rank_engaged(intent, plan=None, question="", cands=None):
    """Gate rank×sales: флаг ∧ сильная форма rank ∧ structural lift (§2.1/§9).

    Сильная форма — уже существующие детекторы: фраза рейтинга, sales_sum,
    max/min или amount без порога. Голый want=list («как у нас дела?») —
    не включает канон.

    Compare двух окон продаж — не rank: want=list + compare_period давал
    engaged и уводил меру в sales_rank_resolve_measure ([замер 26.08 okna]).
    """
    if not ASK_SALES_RANK_CANON:
        return False
    if sales_compare_intent(intent, question):
        return False
    if not rank_intent_from(intent, plan, question):
        return False
    intent = intent or {}
    plan = plan or {}
    amt = intent.get("amount") or {}
    strong = (
        sales_sum_intent(intent, question)
        or rank_question_text(question)
        or (plan.get("compute") or "") in ("max", "min")
        or (not amt.get("op") and amt.get("value") is not None)
    )
    if not strong:
        return False
    return sales_lift_possible(cands)



def _sales_rank_top_n(intent, plan, question):
    """K для rank×sales: amount / топ-N в тексте / иначе 1."""
    intent = intent or {}
    plan = plan or {}
    amt = intent.get("amount") or {}
    if not amt.get("op") and amt.get("value") is not None:
        try:
            n = int(float(amt["value"]))
            if float(amt["value"]) == float(n) and 1 <= n <= ROWS_TO_MODEL:
                return n
        except (TypeError, ValueError):
            pass
    q = " ".join(str(question or "").lower().split())
    m = re.search(r"(?:топ|top)\s*-?\s*(\d+)", q)
    if m:
        return max(1, min(int(m.group(1)), ROWS_TO_MODEL))
    m = re.search(r"\b(\d+)\s*(?:лучш|best)\b", q)
    if m:
        return max(1, min(int(m.group(1)), ROWS_TO_MODEL))
    if any(w in q for w in ("лучших", "лучший", "лучшие", "лучшего")) and any(
            w in q for w in ("три ", "трое ", "трёх ", "трех ")):
        return 3
    if (plan.get("compute") or "") in ("max", "min"):
        return 1
    if serene_axis:
        try:
            k = serene_axis.rank_k(
                intent.get("amount"), plan.get("compute"), 0, ROWS_TO_MODEL)
            if isinstance(k, int) and 2 <= k < ROWS_TO_MODEL:
                return k
        except Exception:
            pass
    return 1


def rank_groups_answer_text(agg, measure_label=None, unit="", k=None):
    """Текст топ-K: «имя»: n · «имя2»: n2 … (скорер name/top-3)."""
    if not agg or agg.get("grain") != "group":
        return None
    gs = [g for g in (agg.get("groups") or []) if isinstance(g, dict)]
    if not gs:
        return None
    try:
        lim = int(k) if k is not None else len(gs)
    except (TypeError, ValueError):
        lim = len(gs)
    lim = max(1, min(lim, len(gs), ROWS_TO_MODEL))
    u = (unit or "").strip()
    suffix = (" " + u) if u and u != UNIT_UNKNOWN else ""
    parts = []
    for g in gs[:lim]:
        nm = (g.get("name") or "").strip()
        val = g.get("value")
        if val is None:
            continue
        if nm:
            parts.append("«%s»: %s%s" % (nm, _fmt_human(val), suffix))
        else:
            parts.append("%s%s" % (_fmt_human(val), suffix))
    if not parts:
        return None
    if len(parts) == 1:
        return parts[0]
    return " · ".join(parts)


def prefer_entity_for_sales(cands, intent, question, plan=None, allow_cold=None):
    """Канон «продали»: регистр движений по written_by; документ — люк (план §2/§7).

    Gold/okna и A2: эталон — accumulationregister_* регистратора продажи.
    Документ↔регистр при расхождении атомов (внутридневная доставка) не развилка:
    отвечаем регистром. Документ остаётся в пуле только если регистра нет.
    Среди регистров одного регистратора — с Количество+Всего, не книга НДС.
    Rank-канон (ASK_SALES_RANK_CANON): вход без sales_sum_intent; cold-lift выкл.
    """
    rank_gate = sales_rank_engaged(intent, plan, question, cands)
    if not sales_sum_intent(intent, question) and not rank_gate:
        return cands
    cands = list(cands or [])
    if not cands:
        return cands
    if allow_cold is None:
        allow_cold = not rank_gate
    try:
        rs = psql(
            "SELECT src_table, parent, written_by FROM %s WHERE src_table IN (%s)"
            % (TABLES, ", ".join(lit(c) for c in cands)))
    except RuntimeError:
        return cands
    parent_by, writer_by = {}, {}
    for r in rs or []:
        if not r or not r[0]:
            continue
        parent_by[r[0]] = (r[1] if len(r) > 1 else "") or ""
        writer_by[r[0]] = (r[2] if len(r) > 2 else "") or ""
    docs = set()
    for c in cands:
        if str(c).startswith("document_"):
            docs.add(c)
        p = parent_by.get(c) or ""
        if p.startswith("document_"):
            docs.add(p)
        w = writer_by.get(c) or ""
        if w.startswith("document_"):
            docs.add(w)
    lifted = []
    if docs:
        try:
            for r in psql(
                    "SELECT src_table FROM %s WHERE src_table LIKE "
                    "'accumulationregister_%%' AND written_by IN (%s)"
                    % (TABLES, ", ".join(lit(d) for d in docs))) or []:
                if r and r[0] and r[0] not in lifted:
                    lifted.append(r[0])
        except RuntimeError:
            pass
    # Холодный подъём: BM25 увёл на журналы/кассу — канон продаж всё равно из written_by.
    # Rank-путь: только lift из cands (риск ложного cold на справочнике) — §9 проекта.
    if not lifted and allow_cold:
        try:
            cold = [r[0] for r in psql(
                "SELECT src_table FROM %s WHERE src_table LIKE "
                "'accumulationregister_%%' AND coalesce(written_by,'') "
                "LIKE 'document_%%'" % TABLES) or [] if r and r[0]]
        except RuntimeError:
            cold = []
        if cold:
            try:
                m_cold = _measures_by_src(cold)
            except Exception:  # noqa: BLE001
                m_cold = {}
            cold.sort(key=lambda s: (-_sales_register_score(s, m_cold.get(s) or []), s))
            # >=8 — есть Количество+итог; иначе при пустых measures имя движения
            # (реализац/продаж) всё равно канон: иначе воскресенье остаётся на журналах.
            _sc0 = _sales_register_score(cold[0], m_cold.get(cold[0]) or [])
            _nm0 = (cold[0] or "").lower()
            if _sc0 >= 8 or (
                    _sc0 >= 2 and any(k in _nm0 for k in ("реализац", "продаж", "sale"))):
                lifted = [cold[0]]
                try:
                    wb = psql("SELECT written_by FROM %s WHERE src_table=%s LIMIT 1"
                              % (TABLES, lit(cold[0])))
                    if wb and wb[0] and wb[0][0]:
                        docs = set(docs) | {wb[0][0]}
                except RuntimeError:
                    pass
    if not lifted:
        return cands
    mbs = {}
    try:
        mbs = _measures_by_src(lifted + [c for c in cands if c not in lifted])
    except Exception:  # noqa: BLE001
        mbs = {}
    lifted.sort(key=lambda s: (-_sales_register_score(s, mbs.get(s) or []), s))
    canon = lifted[0]
    drop_docs = set(docs)
    # Соседи по регистратору (книга НДС и пр.) — не в авто-пуле: иначе модель
    # выбирает книгу, а канон движений молчит ([замер 21.08] июль B doc+книга).
    demote_regs = set(lifted[1:])
    out, seen = [], set()
    for c in [canon] + [x for x in cands if x not in drop_docs and x not in demote_regs
                        and x != canon]:
        if c and c not in seen:
            if c in drop_docs:
                continue
            seen.add(c)
            out.append(c)
    if canon not in seen:
        out.insert(0, canon)
    return out or cands


def sales_canon_intent(intent, question="", cands=None):
    """Канон продаж: явная sale-лексика или период+lift без catalog/stock/register."""
    if sales_sum_intent(intent, question):
        return True
    intent = intent or {}
    if not sales_lift_possible(list(cands or [])):
        return False
    period = intent.get("period") or {}
    if not (period.get("from") or period.get("to")):
        return False
    if catalog_count_question(intent, question):
        return False
    if catalog_kind_total_question(intent, question):
        return False
    _ect = globals().get("entity_form_count_target_is_movement")
    if callable(_ect) and _ect(intent, list(cands or [])):
        return False
    _rcs = globals().get("register_count_src")
    if callable(_rcs) and _rcs(list(cands or []), intent, question):
        return False
    _sq = globals().get("stock_question_engaged")
    if callable(_sq) and _sq(question, intent):
        return False
    if rank_intent_from(intent, question=question):
        return False
    want = (intent.get("want") or "").strip().lower()
    return want in ("sum", "count", "")


def sales_canon_src(cands, intent, question, plan=None):
    """Src канона продаж после prefer — или None."""
    rank_gate = sales_rank_engaged(intent, plan, question, cands)
    if not sales_canon_intent(intent, question, cands) and not rank_gate:
        return None
    preferred = prefer_entity_for_sales(
        list(cands or []), intent, question, plan=plan)
    if not preferred:
        return None
    top = preferred[0]
    if not str(top).startswith("accumulationregister_"):
        return None
    return top


def sales_money_measure(names, alias_by=None):
    """Канон меры «сколько продали» — денежная сумма регистра (Всего / *Документа).

    Clarify по мере здесь недопустим: слово «продали» фиксирует денежный итог,
    не количество и не себестоимость ([замер 21.08 okna] возврат 10).
    """
    names = list(names or [])
    if not names:
        return None
    pool = _fork_sum_headline_pool(names)
    if pool:
        return pool[0]
    alias_by = alias_by or {}
    for n in names:
        blob = " ".join([str(n)] + list(alias_by.get(n) or [])).lower()
        if any(h in blob for h in ("всего", "сумм", "amount", "total", "выруч", "оборот")):
            if "колич" in blob or "себестоим" in blob or "quantity" in blob:
                continue
            return n
    # Fallback: measure_choice по денежному слову (когда имя поля не «Всего»).
    for word in ("всего", "сумм", "total", "amount"):
        got, _, how = measure_choice(names, word, alias_by=alias_by)
        if got and how in ("exact", "substring", "alias", "base", "single"):
            blob = " ".join([str(got)] + list(alias_by.get(got) or [])).lower()
            if "колич" in blob or "себестоим" in blob:
                continue
            return got
    return None



def sales_qty_measure(names, alias_by=None):
    """Мера лидера продаж — количество, не деньги (эталон name SQL okna)."""
    names = list(names or [])
    alias_by = alias_by or {}
    for n in names:
        blob = " ".join([str(n)] + list(alias_by.get(n) or [])).lower()
        if any(h in blob for h in ("колич", "quantity", "qty", "шт", "единиц")):
            if any(x in blob for x in ("сумм", "всего", "amount", "total", "себестоим")):
                continue
            return n
    return None


def _alias_role_in_question(question, measure_name, alias_by):
    """Алиас меры (из данных) попал в текст — без имени поля (ловушка «лучше всего»)."""
    q = " ".join(str(question or "").lower().split())
    if not q or not measure_name:
        return False
    parts = [str(a) for a in (alias_by or {}).get(measure_name) or []]
    words = q.split()
    for raw in parts:
        a = "".join(str(raw).lower().split())
        if len(a) < 3:
            continue
        if a in q:
            return True
        stem = a[:max(4, len(a) - 2)] if len(a) >= 4 else a
        for w in words:
            if len(w) < 3:
                continue
            if w.startswith(stem) or stem.startswith(w[:max(3, len(w) - 2)]):
                return True
    return False


def _sales_product_rank_qty(intent, question):
    """Товарный рейтинг продаж → Количество (те же фразы, что force_money=False).

    Запасной сигнал без осей; канон qty на rank — `sales_rank_product_axis`
    (роль оси из target_src + aliases в БД), не расширение списков слов.
    """
    if _rank_wants_quantity(question):
        return True
    if not sales_sum_intent(intent, question):
        return False
    q = " ".join(str(question or "").lower().split())
    if any(w in q for w in (
            "лучше всего", "хуже всего", "топ продаж", "лидер продаж",
            "best sell", "top sell", "most sold")):
        return True
    if (("что " in q or q.startswith("что") or "какой " in q or "какая " in q
         or "какие " in q or "which " in q or "what " in q)
            and any(w in q for w in ("продава", "продало", "продали", "sold", "sales"))):
        return True
    return False


def sales_rank_product_axis(src, intent, question, axes=None, diag=None, plan=None):
    """Rank по оси, чей target_src — товарный catalog (данные, не слова вопроса).

    Ось узнаём так же, как выбор GROUP BY: stem/alias target_src (`kind_axis_hits`)
    по вопросу и kind; если пусто — уже выбранный `diag.rank_axis_auto` или
    `rank_axis_resolve` (метки осей из search_tables). Товарность — `_is_product_catalog`
    по target_src (структура catalog_*, не перечень фраз вопроса).
    """
    axes = list(axes or [])
    if not axes and src:
        try:
            axes = refcols_of(src)
        except RuntimeError:
            axes = []
    if not axes:
        return False
    hit = set()
    q = (question or "").strip()
    kind = ((intent or {}).get("kind") or "").strip()
    for text in (q, kind):
        if not text:
            continue
        for col in (kind_axis_hits(axes, text) or []):
            if col:
                hit.add(col)
    if not hit:
        col = ((diag or {}).get("rank_axis_auto") or "").strip()
        if not col:
            try:
                col, alts = rank_axis_resolve(
                    src, axes, intent, question, plan=plan)
            except RuntimeError:
                col, alts = None, []
            if diag is not None and col:
                diag["rank_axis_auto"] = col
                if alts:
                    diag.setdefault("rank_axis_alts", list(alts))
        if col:
            hit.add(col)
    if not hit:
        return False
    for a in axes:
        if a.get("col") in hit and _is_product_catalog(a.get("target_src") or ""):
            return True
    return False


def sales_rank_resolve_measure(names, intent, question, alias_by=None,
                               src=None, axes=None, plan=None, diag=None):
    """Единая точка меры rank×sales: canon → qty на product_axis → money на client.

    При sales_rank_engaged живой путь answer() приходит сюда: вызов стоит после
    раннего rank_measure_hint, поэтому money-fallback не перебивает qty
    ([замер 25.08 okna]).
    """
    names = list(names or [])
    alias_by = alias_by or {}
    axes = list(axes or [])
    if not names:
        return None, None
    if not axes and src:
        try:
            axes = refcols_of(src)
        except RuntimeError:
            axes = []
    product_axis = sales_rank_product_axis(
        src, intent, question, axes=axes, diag=diag, plan=plan)
    if product_axis and diag is not None:
        diag["sales_rank_product_axis"] = True
    sm, how = sales_rank_canon_measure(
        names, intent, question, alias_by,
        axes=axes, src=src, product_axis=product_axis, diag=diag)
    if how == "role_ask":
        return None, "role_ask"
    # K4-1 / Э3 №8: топ без «деньги|штуки» — уточнение, не money/qty-догадка.
    _money = sales_money_measure(names, alias_by)
    _qty = sales_qty_measure(names, alias_by)
    _word = ((intent or {}).get("measure") or "").strip()
    _named = bool(_word) or (
        (_money and _alias_role_in_question(question, _money, alias_by))
        or (_qty and _alias_role_in_question(question, _qty, alias_by)))
    if not _named and _money and _qty and _money != _qty:
        return None, "role_ask"
    # Клиентский rank без названной меры → money; товарная qty — rank_measure_hint
    # (тот же сигнал, что раньше ставился в answer() до money-fallback).
    if not sm and not product_axis:
        _hint = rank_measure_hint(names, intent, question, alias_by)
        _qty = sales_qty_measure(names, alias_by)
        if _hint and _qty and _hint == _qty:
            sm, how = _hint, "sales_rank_hint_canon"
        else:
            sm = sales_money_measure(names, alias_by)
            if sm:
                how = "sales_rank_money"
    if not sm:
        sm = sales_qty_measure(names, alias_by)
        if sm:
            how = "sales_qty_canon"
        elif not product_axis:
            sm = sales_money_measure(names, alias_by)
            if sm:
                how = "sales_rank_money"
    return sm, how


def sales_rank_canon_measure(names, intent, question, alias_by=None,
                             axes=None, src=None, product_axis=None, diag=None):
    """Мера rank×sales: роль из measure_choice/алиасов и роли оси, не force_money.

    money — алиас из данных в слове/вопросе; qty — rank по товарной оси (или
    запасной `_sales_product_rank_qty`), если qty есть у источника; иначе None
    (ответный путь добирает money для клиентского rank без qty).
    """
    names = list(names or [])
    alias_by = alias_by or {}
    if not names:
        return None, None
    word = ((intent or {}).get("measure") or "").strip()
    if word:
        got, alts, how = measure_choice(names, word, alias_by=alias_by)
        if got and how in ("exact", "substring", "alias", "base", "single"):
            return got, "role_choice"
        if how == "ask" and alts:
            return None, "role_ask"
    m = sales_money_measure(names, alias_by)
    if m and (
            (word and _alias_role_in_question(word, m, alias_by))
            or _alias_role_in_question(question, m, alias_by)):
        return m, "sales_money_role"
    if product_axis is None:
        product_axis = sales_rank_product_axis(
            src, intent, question, axes=axes, diag=diag)
    if product_axis or _sales_product_rank_qty(intent, question):
        q = sales_qty_measure(names, alias_by)
        if q:
            return q, "sales_qty_canon"
    return None, None


def sales_force_money_measure(intent, question=""):
    """Денежный канон меры — только итог «сколько», не ранг «что/какой продавался».

    [замер 21.08] «что лучше всего продавалось» + sales_money_measure→Всего давало
    чужого лидера (деньги); эталон name — ORDER BY Количество.
    При ASK_SALES_RANK_CANON денежный force на rank×sales выкл. (§2.4).
    Compare двух окон — sum-путь (деньги), не rank: want=list не отключает force.
    """
    if (ASK_SALES_RANK_CANON and rank_intent_from(intent, question=question)
            and not sales_compare_intent(intent, question)):
        return False
    if not sales_sum_intent(intent, question):
        return False
    q = " ".join(str(question or "").lower().split())
    if any(w in q for w in (
            "лучше всего", "хуже всего", "топ продаж", "лидер продаж",
            "best sell", "top sell", "most sold")):
        return False
    if (("что " in q or q.startswith("что") or "какой " in q or "какая " in q
         or "какие " in q or "which " in q or "what " in q)
            and any(w in q for w in ("продава", "продало", "продали", "sold", "sales"))):
        return False
    return True


def sales_canon_force_pool(locked, picked=None, arb_pool=None, doubt=False):
    """После lock канона — один источник, без развилки соперников.

    Живой путь воскресенья [замер 21.08]: lock есть, fork empty, а arb_pool
    снова обрастал tabpart/журналами → clarify источников вместо period_empty.
    """
    if not locked:
        return list(picked or []), list(arb_pool or picked or []), bool(doubt)
    return [locked], [locked], False


def sales_canon_engaged(diag, src=None):
    """Канон продаж зафиксирован или фактически выбран (lock мог не успеть).

    Живой путь [замер 22.08 okna]: override пересадил на регистр, но
    sales_canon_locked не попал в diag → sales_period_empty не срабатывал.
    """
    d = diag or {}
    locked = d.get("sales_canon_locked")
    if locked:
        return locked
    ov = d.get("sales_canon_override") or {}
    if isinstance(ov, dict) and ov.get("стало"):
        return ov["стало"]
    s = src or d.get("focus")
    if (s and str(s).startswith("accumulationregister_")
            and not sales_noncanon_focus(s)):
        return s
    return None


def _zero_period_not_missing(intent, diag, question, act, src=None):
    """Пустое окно при каноне продаж — period_empty, не no_data про отсутствие базы."""
    if act in ("empty_period", "drop_assumed"):
        return True
    if sales_sum_intent(intent, question) and sales_canon_engaged(diag, src):
        pr = (intent or {}).get("period") or {}
        return bool(pr.get("from") or pr.get("to"))
    return False


def sales_ticket_hatch(trusted):
    """Явный люк документа: decision_id без from_memory (не sticky/память)."""
    if not isinstance(trusted, dict) or not trusted.get("src"):
        return False
    if trusted.get("from_memory"):
        return False
    return bool(choice_proven(trusted, "entity") or trusted.get("ambiguity") == "entity")


def sales_noncanon_focus(src):
    """Focus, который для sales_sum не канон (док/журнал/книга/ТЧ передачи)."""
    s = str(src or "")
    if not s:
        return False
    low = s.lower()
    if s.startswith("accumulationregister_"):
        return ("книга" in low or "ндс" in low or "vat" in low)
    return True


def sales_refuse_sticky_focus(focus, trusted, resolved, intent, question, cands):
    """Снять sticky focus/память/resolved, если это не канон продаж.

    [замер 21.08 okna возврат 11]: «прошлый месяц» → focus_forced=
    document_передачатмц… (данные до 2024) при живом регистре июль 2.7M.
    Память/resolved без decision_id не люк §6bis.
    Возвращает (focus, trusted, resolved, cleared_diag|None).
    """
    if not sales_sum_intent(intent, question):
        return focus, trusted, resolved, None
    if sales_ticket_hatch(trusted):
        return focus, trusted, resolved, None
    pool = list(cands or [])
    if focus and focus not in pool:
        pool = [focus] + pool
    canon = sales_canon_src(pool, intent, question)
    if not canon:
        return focus, trusted, resolved, None
    sticky = focus or (resolved or {}).get("src") or (
        (trusted or {}).get("src") if isinstance(trusted, dict) else None)
    if not sticky or sticky == canon:
        return focus, trusted, resolved, None
    if not sales_noncanon_focus(sticky):
        return focus, trusted, resolved, None
    cleared = {"было": sticky, "стало": canon,
               "from_memory": bool(isinstance(trusted, dict)
                                   and trusted.get("from_memory")),
               "had_resolved": bool((resolved or {}).get("src"))}
    if isinstance(trusted, dict) and trusted.get("from_memory"):
        trusted = None
    if isinstance(resolved, dict) and resolved.get("src"):
        resolved = {k: v for k, v in resolved.items() if k != "src"}
    return None, trusted, resolved, cleared


def _is_price_list_noise(src):
    s = str(src or "").lower()
    return ("установкацен" in s or "ценыноменклатур" in s
            or s.startswith("informationregister_цены")
            or (s.startswith("document_") and "цен" in s and "номенклатур" in s))


def _is_product_catalog(src):
    s = str(src or "").lower()
    if not s.startswith("catalog_"):
        return False
    if any(x in s for x in ("вид", "тип", "групп", "type", "kind", "group")):
        return False
    return any(k in s for k in ("номенклатур", "nomencl", "товар", "product", "goods"))


def catalog_kind_total_question(intent, question):
    """count + kind→справочник (не product) + без периода + не stock-path."""
    intent = intent or {}
    _wh = globals().get("question_mentions_warehouse_axis")
    if callable(_wh) and _wh(question, intent):
        return False
    _br = globals().get("balance_routing_core")
    if callable(_br) and _br(intent, {}, question):
        return False
    want = (intent.get("want") or "").strip().lower()
    if want not in ("count", ""):
        return False
    period = intent.get("period") or {}
    if period.get("from") or period.get("to"):
        return False
    kind = (intent.get("kind") or "").strip()
    if not kind:
        return False
    try:
        cats = entity_form_catalogs_for_kind(kind, allow_meaning=False) or []
    except RuntimeError:
        return False
    if not cats or any(_is_product_catalog(c) for c in cats):
        return False
    return True


def catalog_count_question(intent, question):
    """Канон count по справочнику: прайс (лексика) или kind→catalog без stock-path."""
    if catalog_kind_total_question(intent, question):
        return True
    intent = intent or {}
    q = " ".join(str(question or "").lower().split())
    want = (intent.get("want") or "").strip().lower()
    if want not in ("count", ""):
        return False
    if not any(w in q for w in ("прайс", "price list", "в прайсе", "номенклатур")):
        return False
    if any(w in q for w in ("прода", "куп", "остат", "склад")):
        return False
    return True


def prefer_entity_for_catalog_count(cands, intent, question):
    """Справочник в голове: прайс (product) или kind→catalog (контрагенты и т.п.)."""
    if not catalog_count_question(intent, question):
        return cands
    cands = list(cands or [])
    if catalog_kind_total_question(intent, question):
        kind = (intent.get("kind") or "").strip()
        try:
            cats = entity_form_catalogs_for_kind(kind, allow_meaning=False) or []
        except RuntimeError:
            cats = []
        cats = [c for c in cats if c and str(c).startswith("catalog_")]
        if cats:
            head = cats[0]
            rest = [c for c in cands if c != head]
            return [head] + rest
        return cands
    cats = [c for c in cands if _is_product_catalog(c)]
    if not cats:
        try:
            rows = psql(
                "SELECT src_table FROM %s WHERE src_table LIKE 'catalog_%%' "
                "AND (src_table LIKE '%%номенклатур%%' OR src_table LIKE '%%nomencl%%' "
                "OR src_table LIKE '%%товар%%' OR src_table LIKE '%%product%%') "
                "ORDER BY src_table LIMIT 24" % TABLES)
            cats = [r[0] for r in (rows or []) if r and r[0] and _is_product_catalog(r[0])]
        except RuntimeError:
            cats = []
    if not cats:
        return cands
    cats.sort(key=lambda s: (0 if str(s).lower() in (
        "catalog_номенклатура", "catalog_nomenclature", "catalog_товары",
        "catalog_products", "catalog_goods") else 1, str(s)))
    head = cats[0]
    rest = [c for c in cands if c != head and not _is_price_list_noise(c)]
    return [head] + rest


def catalog_count_src(cands, intent, question):
    """Src канона count по справочнику — catalog_* в голове пула."""
    preferred = prefer_entity_for_catalog_count(list(cands or []), intent, question)
    if not preferred:
        return None
    top = preferred[0]
    if str(top or "").startswith("catalog_"):
        return top
    if not _is_product_catalog(top):
        return None
    return top


def period_zero_why_question(question):
    """«Почему в воскресенье ноль / это сбой?» — не figures, а period_empty."""
    q = " ".join(str(question or "").lower().split())
    if not q:
        return False
    why = any(w in q for w in ("почему", "зачем", "сбой", "ошибк", "why", "broken", "bug"))
    zero = any(w in q for w in ("ноль", "нуль", "нуле", "zero", "empty", "нет продаж",
                                  "продаж нет"))
    day = any(w in q for w in ("воскресен", "sunday", "недел", "день", "вчера"))
    return bool(why and (zero or day))




register_zone('ask.z11_sales', globals())
