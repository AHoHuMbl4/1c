"""Мера answer_fit: «отвечает ли сущность на вопрос данными», не словами.

K6: ранг кандидатов в serene_ask — лексика/смысл/реранкер; признака
«в сущности есть живые ячейки нужной формы ответа» в порядке нет.
Справочник «Контрагенты» побеждает на «клиентах», хотя продаж у карточек нет.

Мера (штатный приём SereneDB Relevance Tuning — business signal в ORDER BY):
  fit(src) считает ДВИЖОК по структуре корпуса + search_refcols, без списка слов.

  want=count, kind → catalog C (основы label/aliases, как entity_form_catalogs):
    • C: fit = 1, если в корпусе есть карточки (не папки);
    • H = accumulationregister_*, держащий ось refs → C:
        fit = 2, если count(DISTINCT axis) в окне > 0 и < числа карточек
        (живое собственное подмножество участников движений);
        fit = 1, если distinct == cards (все «покупают» — атомы совпали);
        fit = 0, если движений нет.

  Перестановка: больший fit раньше; при равенстве — прежний порядок.
  Ничего не зная об okna/именах: нужны только refcols, flags.IsFolder, refs_map, doc_date.

Патч в serene_ask (НЕ здесь): после prefer_entity_* вызвать
  cands = reorder_by_answer_fit(cands, intent, today=…).
serene_ask.py этой задачей не трогаем (К5).
"""
from __future__ import annotations

import datetime


def _iso(d):
    if d is None:
        return None
    if isinstance(d, datetime.date):
        return d.isoformat()
    return str(d)[:10]


def rolling_year_bounds(today):
    """Окно «сегодня−1 год … сегодня» — то же, что entity_form_rolling_year по смыслу."""
    if isinstance(today, str):
        today = datetime.date.fromisoformat(today[:10])
    if not isinstance(today, datetime.date):
        today = datetime.date.today()
    try:
        start = today.replace(year=today.year - 1)
    except ValueError:
        start = today - datetime.timedelta(days=365)
    return start, today


def period_bounds(intent, today=None):
    """Явное окно из intent.period, иначе rolling year."""
    today = today or datetime.date.today()
    if isinstance(today, str):
        today = datetime.date.fromisoformat(today[:10])
    p = (intent or {}).get("period") or {}
    fr, to = p.get("from"), p.get("to")
    if fr or to:
        try:
            a = datetime.date.fromisoformat(str(fr)[:10]) if fr else today.replace(
                year=today.year - 1)
        except ValueError:
            a, _ = rolling_year_bounds(today)
        try:
            b = datetime.date.fromisoformat(str(to)[:10]) if to else today
        except ValueError:
            _, b = rolling_year_bounds(today)
        return a, b
    return rolling_year_bounds(today)


def is_noncanon_sales(src):
    """Книга НДС/VAT — не держатель «продаж» для fit (как sales_noncanon_focus)."""
    s = (src or "").lower()
    if not str(src).startswith("accumulationregister_"):
        return True
    return ("книга" in s or "ндс" in s or "vat" in s)


def catalogs_for_kind_sql(kind, stem_dict, tables="search_tables"):
    """SQL: catalog_* по основам kind ↔ label|aliases|best_used_for."""
    kind = (kind or "").strip()
    if not kind:
        return None
    # lit через % — вызывающий подставляет через psql/lit сам; здесь плейсхолдеры.
    return (
        "SELECT t.src_table FROM {tables} t "
        "LEFT JOIN search_entity_alias a ON a.src_table = t.src_table "
        "WHERE t.src_table LIKE 'catalog_%%' AND list_has_any("
        "  list_filter(ts_lexize({stem}, {kind}), x -> length(x) >= 3),"
        "  list_filter(ts_lexize({stem}, concat_ws(' ', t.label, a.aliases, "
        "                                      a.best_used_for)),"
        "              x -> length(x) >= 3))"
    ).format(tables=tables, stem=stem_dict, kind=kind)


def answer_fit_table(psql, lit, cands, intent, today=None,
                     stem_dict="'search_dict_stem'",
                     corpus="search_corpus", tables="search_tables"):
    """Словарь src → fit (int) для кандидатов. Считает база.

    psql(sql) → rows; lit(s) → SQL-литерал.
    """
    cands = [c for c in (cands or []) if c]
    if not cands:
        return {}
    intent = intent or {}
    want = (intent.get("want") or "").strip().lower()
    kind = (intent.get("kind") or "").strip()
    scores = {c: 0 for c in cands}
    if want not in ("count", ""):
        # sum/list: лёгкий сигнал «есть nums» — без смены семантики count/K6.
        if want == "sum":
            rows = psql(
                "SELECT src_table FROM %s WHERE src_table IN (%s) "
                "AND nums IS NOT NULL AND len(map_keys(nums)) > 0 GROUP BY 1"
                % (corpus, ", ".join(lit(c) for c in cands)))
            for r in rows or []:
                if r and r[0] in scores:
                    scores[r[0]] = 1
        return scores
    if not kind:
        return scores
    # kind → catalogs (структура, не слова вопроса в коде)
    try:
        found = [r[0] for r in (psql(
            "SELECT t.src_table FROM %s t "
            "LEFT JOIN search_entity_alias a ON a.src_table = t.src_table "
            "WHERE t.src_table LIKE 'catalog_%%' AND list_has_any("
            "  list_filter(ts_lexize(%s, %s), x -> length(x) >= 3),"
            "  list_filter(ts_lexize(%s, concat_ws(' ', t.label, a.aliases, "
            "                                      coalesce(a.best_used_for,''))),"
            "              x -> length(x) >= 3))"
            % (tables, stem_dict, lit(kind), stem_dict)) or []) if r and r[0]]
    except Exception:  # noqa: BLE001 — при сбое словаря fit остаётся 0
        found = []
    kind_cats = [c for c in found if c in set(cands)] or [
        c for c in cands if c in found]
    if not kind_cats:
        # каталог kind вне пула — всё равно ищем держателей по found
        kind_cats = list(found)
    if not kind_cats:
        return scores
    fr, to = period_bounds(intent, today=today)
    for cat in kind_cats:
        if cat in scores:
            scores[cat] = max(scores[cat], 1)
        try:
            cards_row = psql(
                "SELECT count(*) FROM %s WHERE src_table = %s "
                "AND NOT coalesce(map_extract_value(flags, 'IsFolder'), false)"
                % (corpus, lit(cat)))
            n_cards = int(cards_row[0][0]) if cards_row and cards_row[0] else 0
        except Exception:  # noqa: BLE001
            n_cards = 0
        if n_cards <= 0:
            continue
        try:
            holders = psql(
                "SELECT src_table, col FROM search_refcols "
                "WHERE target_src = %s AND src_table LIKE 'accumulationregister_%%' "
                "AND col IS NOT NULL AND col <> ''"
                % lit(cat))
        except Exception:  # noqa: BLE001
            holders = []
        for h in holders or []:
            src, col = (h[0] if h else None), (h[1] if h and len(h) > 1 else None)
            if not src or not col or src not in scores:
                continue
            if is_noncanon_sales(src):
                continue
            try:
                dist = psql(
                    "SELECT count(DISTINCT map_extract_value(refs_map, %s)) "
                    "FROM %s WHERE src_table = %s "
                    "AND doc_date >= %s::DATE AND doc_date < (%s::DATE + INTERVAL 1 day)"
                    % (lit(col), corpus, lit(src), lit(_iso(fr)), lit(_iso(to))))
                n_ax = int(dist[0][0]) if dist and dist[0] else 0
            except Exception:  # noqa: BLE001
                n_ax = 0
            if n_ax <= 0:
                fit = 0
            elif n_ax < n_cards:
                fit = 2
            else:
                fit = 1
            if fit > scores.get(src, 0):
                scores[src] = fit
            # карточке при живом собственном подмножестве — не выше держателя
            if fit == 2 and cat in scores and scores[cat] < 2:
                scores[cat] = 1
    return scores


def reorder_by_answer_fit(cands, scores):
    """Стабильная перестановка: больший fit раньше."""
    cands = list(cands or [])
    scores = scores or {}
    return sorted(cands, key=lambda s: (-int(scores.get(s) or 0), cands.index(s)))


def prefer_holder_over_kind_catalog(cands, scores, intent):
    """Тот же порядок, что reorder_by_answer_fit (fit=2 держателя раньше fit=1 каталога).

    Идемпотентно; явная точка для теста/патча.
    """
    return reorder_by_answer_fit(cands, scores)
