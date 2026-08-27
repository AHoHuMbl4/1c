#!/usr/bin/env python3
"""Мера answer_fit v2: live-сигнал и вид объекта раньше лексики.

Без порогов/весов, подобранных под базу: порядок = лексикографический ключ
из структурных признаков (вид OData-префикса, business/service, живые ячейки,
doc_date, ось search_refcols). Лексическая позиция — последний ключ.

v1 (entity_answer_fit): fit∈{0,1,2} только для count+kind; sum не трогает;
держатель с 0<distinct<cards получает fit=2, каталог — 1, поэтому на вопросе
«всего клиентов» регистр оказывается выше справочника.
"""
from __future__ import annotations

import datetime

# Object-kind prefixes (universal OData / 1C metadata — not base-specific names).
_PREFIX_CATALOG = "catalog"
_PREFIX_ACCUM = "accumulationregister"
_PREFIX_DOC = "document"
_PREFIX_INFO = "informationregister"
_PREFIX_ACCT = "accountingregister"


def _iso(d):
    if d is None:
        return None
    if isinstance(d, datetime.date):
        return d.isoformat()
    return str(d)[:10]


def rolling_year_bounds(today):
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


def object_prefix(src):
    return str(src or "").split("_", 1)[0].lower()


def is_noncanon_sales(src):
    s = (src or "").lower()
    if not str(src).startswith("accumulationregister_"):
        return True
    return ("книга" in s or "ндс" in s or "vat" in s)


def _question_overlap_batch(psql, lit, cands, question, stem_dict,
                            tables="search_tables", corpus="search_corpus",
                            corp_rows=None):
    """Доля строк / метаданные: слова вопроса в label/aliases vs сырой n_rows."""
    out = {}
    cands = [c for c in (cands or []) if c]
    question = (question or "").strip()
    if not cands or not question:
        return out
    in_list = ", ".join(lit(c) for c in cands)
    sd = stem_dict if str(stem_dict).startswith("'") else lit(stem_dict)
    q_lit = lit(question)
    corp_rows = corp_rows or {}
    meta = {}
    try:
        for r in psql(
                "SELECT t.src_table,"
                "  CASE WHEN list_has_any("
                "    list_filter(ts_lexize(%s, %s), x -> length(x) >= 3),"
                "    list_filter(ts_lexize(%s, concat_ws(' ', t.label,"
                "      coalesce(a.aliases,''))),"
                "      x -> length(x) >= 3)) THEN 1 ELSE 0 END "
                "FROM %s t LEFT JOIN search_entity_alias a "
                "ON a.src_table = t.src_table "
                "WHERE t.src_table IN (%s)"
                % (sd, q_lit, sd, tables, in_list)) or []:
            if r and r[0]:
                meta[r[0]] = int(r[1] or 0)
    except Exception:  # noqa: BLE001
        meta = {}
    row_ov = {}
    meta_hits = [s for s in cands if meta.get(s)]
    small_meta = [s for s in meta_hits
                  if int((corp_rows.get(s) or {}).get("n_rows") or 0) <= 1000]
    if small_meta:
        sub = ", ".join(lit(c) for c in small_meta)
        try:
            for r in psql(
                    "SELECT src_table,"
                    " count(*) FILTER (WHERE list_has_any("
                    "   list_filter(ts_lexize(%s, %s), x -> length(x) >= 3),"
                    "   list_filter(ts_lexize(%s, coalesce(doc,'')),"
                    "     x -> length(x) >= 3)))::BIGINT,"
                    " count(*)::BIGINT "
                    "FROM %s WHERE src_table IN (%s) GROUP BY 1"
                    % (sd, q_lit, sd, corpus, sub)) or []:
                if r and r[0]:
                    row_ov[r[0]] = (int(r[1] or 0), int(r[2] or 0))
        except Exception:  # noqa: BLE001
            row_ov = {}
    for src in cands:
        n_q, n_all = row_ov.get(src, (0, 0))
        if not n_all:
            n_all = int((corp_rows.get(src) or {}).get("n_rows") or 0)
        if meta.get(src) and src not in row_ov:
            # q_meta без дорогого doc-прохода на гигантах: метаданные уже несут тему
            ratio = 1000 if n_all else 0
            n_q = n_all if n_all else 0
        else:
            ratio = (n_q * 1000 // max(n_all, 1)) if n_all else 0
            if meta.get(src) and ratio <= 0:
                ratio = 1
        out[src] = {
            "q_meta_overlap": meta.get(src, 0),
            "q_row_overlap": n_q,
            "q_row_ratio": ratio,
        }
    return out


def features_table(psql, lit, cands, intent, today=None,
                   question=None,
                   stem_dict="'search_dict_stem'",
                   corpus="search_corpus", tables="search_tables"):
    """Один проход агрегатов по корпусу + class + refcols → dict src→features.

    Наружу только итоги GROUP BY; без цикла psql по сущностям.
    """
    cands = [c for c in (cands or []) if c]
    empty = {}
    if not cands:
        return empty
    intent = intent or {}
    kind = (intent.get("kind") or "").strip()
    fr, to = period_bounds(intent, today=today)
    in_list = ", ".join(lit(c) for c in cands)

    # corpus aggregates — one query
    corp = {}
    for r in psql(
            "SELECT src_table,"
            " count(*)::BIGINT,"
            " count(*) FILTER (WHERE doc_date IS NOT NULL)::BIGINT,"
            " count(*) FILTER (WHERE NOT coalesce("
            "   map_extract_value(flags,'IsFolder'), false))::BIGINT,"
            " count(*) FILTER (WHERE nums IS NOT NULL"
            "   AND len(map_keys(nums)) > 0)::BIGINT "
            "FROM %s WHERE src_table IN (%s) GROUP BY 1"
            % (corpus, in_list)) or []:
        if not r or not r[0]:
            continue
        corp[r[0]] = {
            "n_rows": int(r[1] or 0),
            "n_dated": int(r[2] or 0),
            "n_cards": int(r[3] or 0),
            "n_with_nums": int(r[4] or 0),
        }

    # class business/service — one query
    cls = {}
    for r in psql(
            "SELECT src_table, cls FROM search_entity_class "
            "WHERE src_table IN (%s)" % in_list) or []:
        if r and r[0]:
            cls[r[0]] = (r[1] or "").strip().lower()

    # kind catalogs via stem overlap (structure of label/aliases, not word list)
    kind_cats = set()
    if kind:
        try:
            for r in psql(
                    "SELECT t.src_table FROM %s t "
                    "LEFT JOIN search_entity_alias a ON a.src_table = t.src_table "
                    "WHERE t.src_table LIKE 'catalog_%%' AND list_has_any("
                    "  list_filter(ts_lexize(%s, %s), x -> length(x) >= 3),"
                    "  list_filter(ts_lexize(%s, concat_ws(' ', t.label, a.aliases, "
                    "                        coalesce(a.best_used_for,''))),"
                    "              x -> length(x) >= 3))"
                    % (tables, stem_dict, lit(kind), stem_dict)) or []:
                if r and r[0]:
                    kind_cats.add(r[0])
        except Exception:  # noqa: BLE001
            kind_cats = set()

    # holders of kind catalogs among candidates — one query
    holders = {}  # src -> (cat, col)
    if kind_cats:
        cats_list = ", ".join(lit(c) for c in sorted(kind_cats))
        for r in psql(
                "SELECT src_table, target_src, col FROM search_refcols "
                "WHERE target_src IN (%s) "
                "AND src_table LIKE 'accumulationregister_%%' "
                "AND col IS NOT NULL AND col <> '' "
                "AND src_table IN (%s)"
                % (cats_list, in_list)) or []:
            if r and r[0] and r[0] not in holders:
                holders[r[0]] = (r[1], r[2])

    # axis DISTINCT + card counts: один JOIN, GROUP BY (не цикл по сущностям)
    # Доки: Aggregate DISTINCT; refcols — штатная ось.
    axis_n = {}  # src -> (cat, n_ax, n_cards)
    if holders and kind_cats:
        cats_list = ", ".join(lit(c) for c in sorted(kind_cats))
        hold_list = ", ".join(lit(s) for s in holders)
        try:
            for r in psql(
                    "WITH cards AS ("
                    "  SELECT src_table AS cat,"
                    "    count(*) FILTER (WHERE NOT coalesce("
                    "      map_extract_value(flags,'IsFolder'), false))::BIGINT AS n_cards"
                    "  FROM %s WHERE src_table IN (%s) GROUP BY 1"
                    "), axes AS ("
                    "  SELECT r.src_table, r.target_src AS cat, r.col,"
                    "    count(DISTINCT map_extract_value(c.refs_map, r.col))::BIGINT AS n_ax"
                    "  FROM search_refcols r"
                    "  JOIN %s c ON c.src_table = r.src_table"
                    "  WHERE r.target_src IN (%s)"
                    "    AND r.src_table IN (%s)"
                    "    AND r.col IS NOT NULL AND r.col <> ''"
                    "    AND c.doc_date >= %s::DATE"
                    "    AND c.doc_date < (%s::DATE + INTERVAL 1 day)"
                    "  GROUP BY 1, 2, 3"
                    ") "
                    "SELECT a.src_table, a.cat, a.n_ax, coalesce(cards.n_cards, 0) "
                    "FROM axes a LEFT JOIN cards ON cards.cat = a.cat"
                    % (corpus, cats_list, corpus, cats_list, hold_list,
                       lit(_iso(fr)), lit(_iso(to)))) or []:
                if r and r[0]:
                    # один col на src — берём первую/макс n_ax
                    prev = axis_n.get(r[0])
                    n_ax = int(r[2] or 0)
                    if prev is None or n_ax > prev[1]:
                        axis_n[r[0]] = (r[1], n_ax, int(r[3] or 0))
        except Exception:  # noqa: BLE001
            axis_n = {}

    out = {}
    for src in cands:
        c = corp.get(src, {})
        n_cards_cat = 0
        axis_fit = 0
        holds = src in holders
        if holds and src in axis_n:
            cat, n_ax, n_cards_cat = axis_n[src]
            if n_ax <= 0:
                axis_fit = 0
            elif n_cards_cat > 0 and n_ax < n_cards_cat:
                axis_fit = 2
            elif n_cards_cat > 0 and n_ax == n_cards_cat:
                axis_fit = 1
            elif n_ax > 0:
                axis_fit = 1
        v1_fit = 0
        if src in kind_cats and c.get("n_cards", 0) > 0:
            v1_fit = 1
        if axis_fit > v1_fit:
            v1_fit = axis_fit
        out[src] = {
            "prefix": object_prefix(src),
            "cls": cls.get(src, ""),
            "n_rows": c.get("n_rows", 0),
            "n_dated": c.get("n_dated", 0),
            "n_cards": c.get("n_cards", 0),
            "n_with_nums": c.get("n_with_nums", 0),
            "is_kind_catalog": src in kind_cats,
            "holds_kind_axis": holds,
            "axis_fit": axis_fit,
            "v1_fit": v1_fit,
            "n_cards_of_axis": n_cards_cat if holds else 0,
        }
    if question:
        q_ov = _question_overlap_batch(
            psql, lit, cands, question, stem_dict,
            tables=tables, corpus=corpus,
            corp_rows={s: out.get(s) for s in cands})
        for src, qf in q_ov.items():
            out.setdefault(src, {}).update(qf)
    return out


def rank_key_v2(src, feat, intent, form, lexical_pos):
    """Лексикографический ключ: меньше = лучше. Без весов/порогов.

    Порядок признаков:
      1) не service
      2) live-ярус (форма ответа)
      3) вид объекта согласован с формой
      4) есть doc_date, когда форме нужны движения
      5) лексическая позиция
    """
    feat = feat or {}
    intent = intent or {}
    form = (form or "").lower()
    want = (intent.get("want") or "").strip().lower()
    prefix = feat.get("prefix") or object_prefix(src)
    service = 0 if feat.get("cls") != "service" else 1
    has_period = bool(((intent.get("period") or {}).get("from")
                       or (intent.get("period") or {}).get("to")))
    # movement-shaped count: distinct form OR explicit period
    movement = form in ("distinct", "complement") or (
        form == "count" and has_period)
    sales_shaped = form in ("sum", "name") or want == "sum"

    if sales_shaped:
        # live: dated cells with nums
        if feat.get("n_dated", 0) > 0 and feat.get("n_with_nums", 0) > 0:
            live = 2
        elif feat.get("n_dated", 0) > 0 or feat.get("n_with_nums", 0) > 0:
            live = 1
        else:
            live = 0
        # object kind: register/document before catalog/info
        if prefix == _PREFIX_ACCUM and not is_noncanon_sales(src):
            kind_ok = 0
        elif prefix == _PREFIX_DOC:
            kind_ok = 1
        elif prefix == _PREFIX_ACCUM:
            kind_ok = 2  # noncanon book
        else:
            kind_ok = 3
        # popularity = число живых датированных ячеек (док SereneDB business signal),
        # не порог: больший поток раньше при равном live/kind
        return (service, -live, kind_ok,
                -int(feat.get("n_dated") or 0),
                int(lexical_pos or 10**6))

    if movement:
        live = int(feat.get("axis_fit") or 0)
        if prefix == _PREFIX_ACCUM and feat.get("holds_kind_axis"):
            kind_ok = 0
        elif prefix == _PREFIX_ACCUM:
            kind_ok = 1
        elif feat.get("is_kind_catalog"):
            kind_ok = 2
        else:
            kind_ok = 3
        dated = 0 if feat.get("n_dated", 0) > 0 else 1
        return (service, -live, kind_ok, dated, int(lexical_pos or 10**6))

    # card-count (count without period): kind catalog with cards is the live answer;
    # K6a: метаданные несут слова вопроса — выше «гиганта» без q_meta (план счетов).
    q_meta = int(feat.get("q_meta_overlap") or 0)
    q_ratio = int(feat.get("q_row_ratio") or 0)
    if q_meta and prefix == _PREFIX_INFO:
        live = 3
        kind_ok = 0
    elif q_meta and feat.get("is_kind_catalog") and feat.get("n_cards", 0) > 0:
        live = 3
        kind_ok = 0
    elif q_meta and prefix == _PREFIX_CATALOG:
        live = 3
        kind_ok = 1
    elif q_meta and prefix == _PREFIX_DOC:
        live = 3
        kind_ok = 2
    elif feat.get("is_kind_catalog") and feat.get("n_cards", 0) > 0:
        live = 2
        kind_ok = 0
    elif prefix == _PREFIX_DOC and feat.get("n_dated", 0) > 0:
        live = 2
        kind_ok = 1
    elif prefix == _PREFIX_CATALOG and feat.get("n_cards", 0) > 0:
        live = 1
        kind_ok = 2
    elif int(feat.get("axis_fit") or 0) >= 2:
        live = 1
        kind_ok = 3
    elif q_meta and prefix not in (_PREFIX_ACCT,):
        live = 1
        kind_ok = 4
    elif feat.get("n_rows", 0) > 0:
        live = 0
        kind_ok = 5 if prefix == _PREFIX_ACCT else 4
    else:
        live = -1
        kind_ok = 6
    # popularity: q_row_ratio при q_meta; иначе меньший регистр лучше (не сырой max)
    if q_meta:
        pop = (-q_ratio, int(feat.get("n_rows") or 0))
    else:
        pop = (int(feat.get("n_rows") or 0),)
    return (service, -live, kind_ok, pop, int(lexical_pos or 10**6))


def reorder_v2(cands, features, intent, form):
    cands = list(cands or [])
    features = features or {}
    pos = {s: i for i, s in enumerate(cands)}
    return sorted(
        cands,
        key=lambda s: rank_key_v2(s, features.get(s), intent, form, pos.get(s, 10**6)))


def reorder_v1(cands, features):
    """Эмуляция v1: больший v1_fit раньше, иначе прежний порядок."""
    cands = list(cands or [])
    features = features or {}
    pos = {s: i for i, s in enumerate(cands)}
    return sorted(
        cands,
        key=lambda s: (-int((features.get(s) or {}).get("v1_fit") or 0),
                       pos.get(s, 10**6)))


def stem_overlap_srcs(psql, lit, question, prefix_like, stem_dict="search_dict_stem",
                      tables="search_tables"):
    rows = psql(
        "SELECT t.src_table FROM %s t "
        "LEFT JOIN search_entity_alias a ON a.src_table = t.src_table "
        "WHERE t.src_table LIKE %s AND list_has_any("
        "  list_filter(ts_lexize(%s, %s), x -> length(x) >= 3),"
        "  list_filter(ts_lexize(%s, concat_ws(' ', t.label, a.aliases, "
        "                        coalesce(a.best_used_for,''))),"
        "              x -> length(x) >= 3))"
        % (tables, lit(prefix_like), lit(stem_dict), lit(question), lit(stem_dict)))
    return [r[0] for r in (rows or []) if r and r[0]]


def kind_from_alias_overlap(psql, lit, question, stem_dict="search_dict_stem"):
    """Kind для features: лидер catalog по aliases@@вопрос, не count(holders)."""
    rows = psql(
        "SELECT src_table, tfidf(alias_idx.tableoid) AS s "
        "FROM alias_idx "
        "WHERE aliases @@ %s AND src_table LIKE 'catalog_%%' "
        "ORDER BY s DESC NULLS LAST, src_table LIMIT 3"
        % lit(question))
    cats = [r[0] for r in (rows or []) if r and r[0]]
    if not cats:
        cats = stem_overlap_srcs(psql, lit, question, "catalog_%", stem_dict=stem_dict)
    if not cats:
        return ""
    src = cats[0]
    lab = psql(
        "SELECT coalesce(nullif(trim(split_part(a.aliases, ',', 1)), ''), t.label) "
        "FROM search_entity_alias a JOIN search_tables t ON t.src_table = a.src_table "
        "WHERE a.src_table = %s LIMIT 1" % lit(src))
    if lab and lab[0] and lab[0][0]:
        return str(lab[0][0]).strip().split()[0].lower()
    return src.replace("catalog_", "")


def expand_holders(order, kind, psql, lit, stem_dict="search_dict_stem",
                   tables="search_tables"):
    out = list(order)
    seen = set(out)
    if not kind:
        return out
    cats = stem_overlap_srcs(psql, lit, kind, "catalog_%", stem_dict=stem_dict,
                             tables=tables)
    for cat in cats:
        if cat not in seen:
            seen.add(cat)
            out.append(cat)
    if not cats:
        return out
    for cat in cats:
        for h in psql(
                "SELECT src_table FROM search_refcols "
                "WHERE target_src = %s AND src_table LIKE 'accumulationregister_%%'"
                % lit(cat)) or []:
            if h and h[0] and h[0] not in seen:
                seen.add(h[0])
                out.append(h[0])
    return out


def expand_stem_and_live(order, question, form, want_agg, psql, lit,
                         stem_dict="search_dict_stem", tables="search_tables",
                         corpus="search_corpus"):
    out = list(order)
    seen = set(out)
    for prefix in ("catalog_%", "accumulationregister_%", "document_%",
                   "informationregister_%"):
        for src in stem_overlap_srcs(psql, lit, question, prefix,
                                     stem_dict=stem_dict, tables=tables):
            if src not in seen:
                seen.add(src)
                out.append(src)
    sales_shaped = form in ("sum", "name") or want_agg == "sum"
    movement = form in ("distinct", "complement")
    if sales_shaped or movement:
        rows = psql(
            "SELECT c.src_table "
            "FROM %s c "
            "WHERE c.src_table LIKE 'accumulationregister_%%' "
            "AND c.doc_date IS NOT NULL "
            "AND c.nums IS NOT NULL AND len(map_keys(c.nums)) > 0 "
            "AND EXISTS ("
            "  SELECT 1 FROM search_refcols r "
            "  WHERE r.src_table = c.src_table "
            "  AND r.target_src LIKE 'catalog_%%' AND r.col IS NOT NULL)"
            "GROUP BY c.src_table" % corpus)
        for r in rows or []:
            src = r[0]
            if not src or src in seen or is_noncanon_sales(src):
                continue
            seen.add(src)
            out.append(src)
    return out


def infer_rank_form(intent, question, sales_sum=False, rank_intent=False):
    intent = intent or {}
    want = (intent.get("want") or "").strip().lower()
    if sales_sum or want == "sum" or rank_intent:
        return "sum" if want == "sum" or sales_sum else "name"
    period = intent.get("period") or {}
    if period.get("from") or period.get("to"):
        return "distinct"
    return "count"


def dual_atom_pair(cands, features, intent):
    """Catalog cards + holder axis_fit>=2 — два атома, п.12 clarify."""
    intent = intent or {}
    want = (intent.get("want") or "").strip().lower()
    if want not in ("count", ""):
        return None, None
    kind = (intent.get("kind") or "").strip()
    if not kind:
        return None, None
    cat = holder = None
    for s in (cands or [])[:16]:
        f = (features or {}).get(s) or {}
        if (not cat and f.get("is_kind_catalog")
                and int(f.get("n_cards") or 0) > 0):
            cat = s
        if (not holder and f.get("holds_kind_axis")
                and int(f.get("axis_fit") or 0) >= 2):
            holder = s
        if cat and holder:
            break
    if cat and holder and cat != holder:
        return cat, holder
    return None, None


def apply_to_candidates(psql, lit, cands, intent, question, today=None,
                        stem_dict="search_dict_stem", corpus="search_corpus",
                        tables="search_tables", sales_sum=False,
                        rank_intent=False, mk_clarify=None):
    """K6 v2: расширить пул, reorder_v2, diag; опционально clarify двух атомов.

    mk_clarify(cat, holder, diag_extra) -> dict ответа или None.
    """
    cands = list(cands or [])
    diag_out = {}
    kind = (intent or {}).get("kind") or ""
    if not kind.strip():
        kind = kind_from_alias_overlap(psql, lit, question, stem_dict=stem_dict)
        if kind:
            intent = dict(intent or {})
            intent["kind"] = kind
            diag_out["k6_kind_alias"] = kind
    form = infer_rank_form(intent, question, sales_sum=sales_sum,
                           rank_intent=rank_intent)
    want_agg = "sum" if form in ("sum", "name") else "count"
    pool = expand_holders(cands, kind, psql, lit, stem_dict=stem_dict,
                          tables=tables)
    pool = expand_stem_and_live(pool, question, form, want_agg, psql, lit,
                                stem_dict=stem_dict, tables=tables,
                                corpus=corpus)
    seen = set()
    merged = []
    for s in pool:
        if s and s not in seen:
            seen.add(s)
            merged.append(s)
    intent_fit = dict(intent or {})
    if form in ("distinct", "complement"):
        fr, to = period_bounds(intent_fit, today=today)
        intent_fit["period"] = {"from": fr.isoformat(), "to": to.isoformat()}
    feats = features_table(
        psql, lit, merged, intent_fit, today=today, question=question,
        stem_dict=lit(stem_dict), corpus=corpus, tables=tables)
    reordered = reorder_v2(merged, feats, intent_fit, form)
    diag_out["answer_fit_v2"] = {
        s: {
            "prefix": (feats.get(s) or {}).get("prefix"),
            "axis_fit": (feats.get(s) or {}).get("axis_fit"),
            "n_dated": (feats.get(s) or {}).get("n_dated"),
            "n_cards": (feats.get(s) or {}).get("n_cards"),
            "is_kind_catalog": (feats.get(s) or {}).get("is_kind_catalog"),
            "q_meta": (feats.get(s) or {}).get("q_meta_overlap"),
            "q_row_ratio": (feats.get(s) or {}).get("q_row_ratio"),
        }
        for s in reordered[:12]
    }
    cat, holder = dual_atom_pair(reordered, feats, intent_fit)
    if cat and holder and mk_clarify:
        clar = mk_clarify(cat, holder, {"answer_fit_v2_dual": [cat, holder]})
        if clar:
            return {"cands": reordered, "diag": diag_out, "clarify": clar}
    return {"cands": reordered, "diag": diag_out, "clarify": None}
