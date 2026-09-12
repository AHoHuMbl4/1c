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
