"""Zone 11: Продажи (sales).

В2 (СНОС-15): prefer/force/lock/canon-выборы сущности снесены.
Классификаторы (sales_sum_intent / sales_rank_engaged / sales_noncanon_focus
и тела) и measure-helpers до В3 — остаются.
"""
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
    engaged и уводил меру в rank-resolve ([замер 26.08 okna]).
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


def _fork_headline_doc_measures(names):
    """Итог шапки document_* — поля *Документа (метаданные платформы).

    S1/B7: щель onepath (бывш. fork-детектор; W2-R2; кормит sales_money_measure).
    """
    return sorted(n for n in (names or []) if n and str(n).lower().endswith("документа"))


def _fork_sum_headline_pool(names):
    """Headline-меры sum-вопроса: *Документа и Всего (план §3, замер 17–21.08).

    S1/B7: щель onepath (бывш. fork-детектор; W2-R2).
    """
    out = []
    for h in _fork_headline_doc_measures(names):
        if h not in out:
            out.append(h)
    for n in names or []:
        if (n or "").strip().lower() == "всего" and n not in out:
            out.append(n)
            break
    return out


def sales_money_measure(names, alias_by=None):
    """Денежная мера среди имён полей (класс money для меню/мер до В3)."""
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
    for word in ("всего", "сумм", "total", "amount"):
        got, _, how = measure_choice(names, word, alias_by=alias_by)
        if got and how in ("exact", "substring", "alias", "base", "single"):
            blob = " ".join([str(got)] + list(alias_by.get(got) or [])).lower()
            if "колич" in blob or "себестоим" in blob:
                continue
            return got
    return None


def sales_qty_measure(names, alias_by=None):
    """Мера количества среди имён полей (класс qty для меню/мер до В3)."""
    names = list(names or [])
    alias_by = alias_by or {}
    for n in names:
        blob = " ".join([str(n)] + list(alias_by.get(n) or [])).lower()
        if any(h in blob for h in ("колич", "quantity", "qty", "шт", "единиц")):
            if any(x in blob for x in ("сумм", "всего", "amount", "total", "себестоим")):
                continue
            return n
    return None


def _zero_period_not_missing(intent, diag, question, act, src=None):
    """Пустое окно при sales-sum — period_empty, не no_data про отсутствие базы."""
    if act in ("empty_period", "drop_assumed"):
        return True
    if sales_sum_intent(intent, question):
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
    """Count по справочнику: прайс (лексика) или kind→catalog без stock-path."""
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


register_zone('ask.z11_sales', globals())
