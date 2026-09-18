"""Zone 06: Поиск сущностей (entity-search)."""
from __future__ import annotations

from ask._imports import *
from ask._wire import register_zone, apply_bindings

apply_bindings(globals())

def _predicates(intent):
    """Условия по дате — предикаты по INCLUDE-колонке индекса.

    Числовых условий здесь БОЛЬШЕ НЕТ: строка несёт все свои величины картой, и какая
    из них имеется в виду, зависит от вопроса и от сущности. Смешивать нельзя —
    «больше 500000» у документа про сумму, а у строки накладной могло бы оказаться
    про количество.
    """
    return period_preds((intent or {}).get("period"))


def _like_pattern(alt):
    """Слово вопроса -> образец `ts_like`, где знаки слова остаются знаками.

    🔴 ЗАЧЕМ. `ts_like` принимает SQL-образец: `%` значит «сколько угодно любых знаков»,
    `_` — «ровно один любой» (доки движка `sql/functions/search/full-text`, там же
    экранирование обратной косой: `\\%` и `\\_`). Слово в образец попадает из ВОПРОСА
    ЧЕЛОВЕКА, и эти знаки в нём встречаются: «какая наценка в %», код склада `A_12`,
    процент в названии тарифа. Без экранирования «%» превращался в «что угодно», образец
    вырождался в `%%%` и совпадал с каждым термом индекса — буквальный отбор возвращал
    ВСЕ сущности базы. Ошибки при этом не возникало ни одной: отбор просто переставал
    отбирать, а шаг выбора получал перечень, в котором нечего различать.

    Возвращает None, если после экранирования искать нечего (пустое слово): образец
    `%%` — это «любой терм», то есть тот же вырожденный случай, только тише.
    """
    s = (alt or "").lower()
    if not s.strip():
        return None
    # Порядок важен: сперва сама косая, иначе экранируется добавленное нами же.
    s = s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return "%" + s + "%"


# C4 / design-c §3: норм-склейка имён на входе probe (мин-длина, допуск).
# Дефолты — замер 18.09 (damerau=2) и канон §3 (3 при len>=16); пороги — env.
_PROBE_NORM_MIN_LEN = int(os.environ.get("PROBE_NORM_MIN_LEN", "8"))
_PROBE_NORM_DIST = int(os.environ.get("PROBE_NORM_DIST", "2"))
_PROBE_NORM_DIST_LONG = int(os.environ.get("PROBE_NORM_DIST_LONG", "3"))
_PROBE_NORM_LONG_AT = int(os.environ.get("PROBE_NORM_LONG_AT", "16"))


def _probe_norm(s):
    """lower + без пробелов (образец `_homonym_norm` z21)."""
    return "".join(str(s).lower().split())


def _probe_norm_dist(glue):
    """Допуск span-предиката: 2; 3 при длине склейки >=16 (канон §3)."""
    return (_PROBE_NORM_DIST_LONG
            if len(glue or "") >= _PROBE_NORM_LONG_AT else _PROBE_NORM_DIST)


def _probe_group_primary(group):
    if isinstance(group, (list, tuple)):
        for alt in group:
            s = str(alt or "").strip()
            if s:
                return s
        return ""
    return str(group or "").strip()


def _probe_tokens(text):
    return [t for t in re.findall(r"[0-9a-zA-Zа-яА-ЯёЁ]+", text or "") if t]


def _probe_src_targets(src=None, src_label=None):
    """Норм-хвост src_table и норм-label (длина >=8) — цели exclude-only гарда."""
    targets = []
    if src:
        raw = str(src)
        tail = raw.split("_", 1)[1] if "_" in raw else raw
        tn = _probe_norm(tail)
        if tn and len(tn) >= _PROBE_NORM_MIN_LEN:
            targets.append(tn)
    if src_label:
        ln = _probe_norm(src_label)
        if ln and len(ln) >= _PROBE_NORM_MIN_LEN and ln not in targets:
            targets.append(ln)
    return targets


def _probe_src_name_hit_glues(glues, src=None, src_label=None, diag=None):
    """ГАРД exclude-only: hit-склейки одним SQL (штатный damerau_levenshtein).

    unnest(склейки) × unnest(хвост/label src); length>=8; допуск 2 (3 при len>=16).
    Доки: Sql › Functions › Text Functions › damerau_levenshtein;
          Sql › Query syntax › SELECT › unnest.
    Fail-soft: сбой → пустой set (гард недоступен = как неизвестный src), diag-факт.
    Кэш — на один вызов probe (результат держит вызывающий).
    """
    glues = [g for g in (glues or []) if g and len(g) >= _PROBE_NORM_MIN_LEN]
    if not glues:
        return set()
    targets = _probe_src_targets(src, src_label)
    if not targets:
        return set()
    # Один SELECT: CASE-допуск по длине склейки (канон §3), без локального DL.
    glue_lit = "[%s]" % ", ".join(lit(g) for g in glues)
    target_lit = "[%s]" % ", ".join(lit(t) for t in targets)
    qsql = (
        "SELECT g.glue FROM unnest(%s) AS g(glue), unnest(%s) AS t(tgt) "
        "WHERE length(g.glue) >= %d AND length(t.tgt) >= %d "
        "AND damerau_levenshtein(g.glue, t.tgt) <= ("
        "CASE WHEN length(g.glue) >= %d THEN %d ELSE %d END)"
        % (glue_lit, target_lit,
           _PROBE_NORM_MIN_LEN, _PROBE_NORM_MIN_LEN,
           _PROBE_NORM_LONG_AT, _PROBE_NORM_DIST_LONG, _PROBE_NORM_DIST))
    try:
        rows = psql(qsql)
    except Exception:  # noqa: BLE001 — fail-soft: гард недоступен
        if diag is not None:
            diag["probe_src_name_sql_error"] = True
        return set()
    hits = set()
    for r in rows or []:
        if r and r[0]:
            hits.add(str(r[0]))
    return hits


def _probe_span_is_src_name(glue, hit_glues):
    """True, если склейка в hit-множестве гарда (exclude-only, без match-expr)."""
    return bool(glue) and glue in (hit_glues or ())


def _probe_iter_spans(groups, question=None):
    """Единая span-функция: непрерывные >=2 токена → (glue, n_toks, frozenset gis).

    С `question`: окна только по смежным токенам вопроса (эталон `_question_spans_glued`);
    токен вне term-групп — разрыв окна (не выкидывается из порядка). Span — только если
    все токены окна входят в term-группы (gis). Без `question`: span только внутри одной
    группы соседних токенов primary; чужие группы через пустоту не склеиваются.
    Склейка — `_probe_norm`; короче `_PROBE_NORM_MIN_LEN` отбрасываются.
    """
    groups = list(groups or [])
    g_primary_toks = [_probe_tokens(_probe_group_primary(g)) for g in groups]
    g_norm_sets = [set(_probe_norm(t) for t in toks) for toks in g_primary_toks]

    def _gi_of(nt):
        for gi, ns in enumerate(g_norm_sets):
            if nt in ns:
                return gi
        return None

    # Непрерывные пробеги in-group токенов: дыра рвёт окно (как z21 spans).
    runs = []
    if question:
        cur = []
        for tok in _probe_tokens(question):
            nt = _probe_norm(tok)
            gi = _gi_of(nt) if nt else None
            if gi is None:
                if cur:
                    runs.append(cur)
                    cur = []
                continue
            cur.append((tok, gi))
        if cur:
            runs.append(cur)
    else:
        # Без порядка вопроса непрерывность между группами недоступна —
        # span только внутри multi-token primary одной группы.
        for gi, toks in enumerate(g_primary_toks):
            if len(toks) >= 2:
                runs.append([(t, gi) for t in toks])

    # glue -> (n_toks, gis); при равной склейке держим кратчайший span (shortest-hit).
    best = {}
    for flat in runs:
        n = len(flat)
        for i in range(n):
            for j in range(i + 2, n + 1):
                toks = [flat[k][0] for k in range(i, j)]
                gis = frozenset(flat[k][1] for k in range(i, j))
                glue = _probe_norm(" ".join(toks))
                if not glue or len(glue) < _PROBE_NORM_MIN_LEN:
                    continue
                n_toks = j - i
                prev = best.get(glue)
                if prev is None or n_toks < prev[0]:
                    best[glue] = (n_toks, gis)
                elif n_toks == prev[0]:
                    best[glue] = (n_toks, prev[1] | gis)
    # shortest-hit: короче по токенам, затем по длине склейки
    return sorted(
        ((glue, n_toks, gis) for glue, (n_toks, gis) in best.items()),
        key=lambda x: (x[1], len(x[0]), x[0]))


def _probe_span_trigger(per_group, n_groups, span_hits, excluded_gis=None):
    """Триггер SUPERSEDE: ≥1 UNMATCHED ∨ у покрытой группы hit только fuzzy/part."""
    excluded = excluded_gis or frozenset()
    if any(gi not in per_group and gi not in excluded
           for gi in range(n_groups)):
        return True
    soft = {"fuzzy", "part"}
    for _glue, _n_toks, gis, _exprs in span_hits:
        for gi in gis:
            if gi in excluded:
                continue
            cur = per_group.get(gi)
            if cur is not None and cur[2] in soft:
                return True
    return False


def _probe_apply_span_supersede(per_group, n_groups, span_hits, diag,
                                excluded_gis=None):
    """SUPERSEDE: span перезаписывает unmatched/fuzzy/part; exact/slop не трогает.

    OR всех hit-exprs покрывающих spans (порядок — shortest-hit). diag-тег `norm`
    только при живом count(*)>0 (иначе группа остаётся unmatched).
    """
    excluded = excluded_gis or frozenset()
    if not span_hits or not _probe_span_trigger(
            per_group, n_groups, span_hits, excluded_gis=excluded):
        return
    soft = {"fuzzy", "part"}
    for gi in range(n_groups):
        if gi in excluded:
            continue
        cur = per_group.get(gi)
        if cur is not None and cur[2] not in soft:
            continue  # exact/slop/resolved/… — не трогаем; unmatched — cur is None
        covering = [h for h in span_hits if gi in h[2]]
        if not covering:
            continue
        exprs = []
        glues = []
        for glue, _n_toks, _gis, hit_exprs in covering:
            glues.append(glue)
            for e in hit_exprs:
                if e not in exprs:
                    exprs.append(e)
        if not exprs:
            continue
        per_group[gi] = (0, exprs, "norm")
        diag.setdefault("_norm", {})[gi] = list(glues)


def probe(groups, question=None, src=None, src_label=None):
    """Проверить все слова вопроса ОДНИМ запросом и вернуть выражение на каждое понятие.

    Три способа на каждое слово, по убыванию строгости:
      * `ts_phrase`      — точное совпадение, проходит через анализатор (регистр не важен);
      * `ts_levenshtein` — опечатки и словоформы, тоже через анализатор;
      * `ts_like`        — подстрока, для склеенных имён («поступления» в
                           «ПоступлениеТоваровУслуг»).
    Важно: `ts_like` и `ts_starts_with` — ТЕРМИННЫЕ функции, анализатор их не трогает и
    регистр не понижает. Проверено на инстансе: `ts_starts_with('Сбербан')` = 0, а
    `ts_starts_with('сбербан')` = 143. Поэтому для них слово приводится к нижнему регистру.
    Раньше здесь был цикл подбора длины префикса — до шести отдельных запросов на слово,
    и для имён собственных он не находил ничего вообще.

    C4 (design-c §3): в тот же UNION — span-склейки (>=2 токенов через границы групп);
    hit = `ts_levenshtein(склейка, допуск)` (+ `ts_like` только на точной склейке);
    при триггере SUPERSEDE перезаписывает unmatched/fuzzy/part тегом `norm` ДО
    resolve_values. Exclude-only по имени src — группа целиком вне матча (п.13).
    """
    groups = list(groups or [])
    diag = {}
    # Сначала spans + гард: hit-склейки → excluded_gis (понятие (iii)); для них
    # ни lit-, ни span-match-expr, SUPERSEDE запрещён; в unmatched не входят.
    span_list = list(_probe_iter_spans(groups, question=question))
    src_name_hits = _probe_src_name_hit_glues(
        [g for g, _n, _gis in span_list],
        src=src, src_label=src_label, diag=diag)
    excluded_gis = set()
    excluded_hit_glues = {}
    for glue, _n_toks, gis in span_list:
        if not _probe_span_is_src_name(glue, src_name_hits):
            continue
        for gi in gis:
            excluded_gis.add(gi)
            excluded_hit_glues.setdefault(gi, []).append(glue)
    if excluded_gis:
        diag["probe_src_name_excluded"] = sorted(excluded_gis)
        diag["_src_name"] = {
            gi: list(glues) for gi, glues in excluded_hit_glues.items()}
        for gi in excluded_gis:
            diag[gi] = "src_name"

    probes, meta = [], []
    for gi, group in enumerate(groups):
        if gi in excluded_gis:
            continue
        for ai_, alt in enumerate(group):
            variants = [("exact", "ts_phrase(%s)" % lit(alt))]
            words = alt.split()
            if len(words) > 1:
                # Многословное имя в данных часто разорвано: «Общество с ограниченной
                # ответственностью "Ромашка"». Точная фраза «Общество Ромашка» даёт 0,
                # фраза с окном — 9. Окно берём по самой фразе: сколько слов между
                # краями, столько и допускаем. Константа здесь означала бы «наши имена
                # такой длины» — на языке с длинными оборотами фраза перестаёт находиться.
                variants.append(("slop", "ts_phrase(%s, ARRAY[0,%d], %s)"
                                 % (lit(words[0]), len(words) - 1, lit(words[-1]))))
            # Расстояние опечатки — от длины слова, а не фиксированное. При 2 на слове из
            # трёх букв совпадает половина корпуса: замерено, 'tax' -> 2978 строк из
            # 97 085 при нуле точных. На кириллице не проявлялось только потому, что
            # значимые слова длинные.
            variants.append(("fuzzy", "ts_levenshtein(%s, %d)"
                             % (lit(alt), min(2, len(alt) // 4))))
            pat = _like_pattern(alt)
            if pat is not None:
                variants.append(("part", "ts_like(%s)" % lit(pat)))
            for kind, expr in variants:
                probes.append("SELECT %d i, count(*) n FROM %s WHERE doc @@ %s"
                              % (len(meta), INDEX, expr))
                meta.append(("lit", gi, kind, expr))
    # Span-arms того же UNION (Доки: Cookbook › Search › Fuzzy Search › ts_levenshtein;
    # Sql › Functions › Search › Full-Text — term predicates / ts_like).
    # Exclude-only гард: один SQL штатной damerau_levenshtein на вызов probe
    # (Доки: Sql › Functions › Text Functions › damerau_levenshtein;
    # Sql › Query syntax › SELECT › unnest).
    for glue, n_toks, gis in span_list:
        if _probe_span_is_src_name(glue, src_name_hits) or (gis & excluded_gis):
            continue
        dist = _probe_norm_dist(glue)
        span_variants = [
            ("ts_levenshtein(%s, %d)" % (lit(glue), dist)),
        ]
        pat = _like_pattern(glue)
        if pat is not None:
            span_variants.append("ts_like(%s)" % lit(pat))
        for expr in span_variants:
            probes.append("SELECT %d i, count(*) n FROM %s WHERE doc @@ %s"
                          % (len(meta), INDEX, expr))
            meta.append(("span", glue, n_toks, gis, expr))
    if not probes:
        return [], diag
    counts = {}
    for r in psql(" UNION ALL ".join(probes)):
        try:
            counts[int(r[0])] = int(r[1])
        except (ValueError, IndexError):
            pass
    per_group = {}
    # 1) буквальные kinds по группам
    for i, entry in enumerate(meta):
        if entry[0] != "lit":
            continue
        _tag, gi, kind, expr = entry
        if counts.get(i, 0) <= 0:
            continue
        rank = {"exact": 0, "slop": 1, "fuzzy": 2, "part": 3}[kind]
        cur = per_group.get(gi)
        if cur is None or rank < cur[0]:
            per_group[gi] = (rank, [expr], kind)
        elif rank == cur[0] and expr not in cur[1]:
            cur[1].append(expr)
    # 2) живые span-hits (count>0), shortest уже в порядке _probe_iter_spans
    span_acc = {}  # glue -> (n_toks, gis, [exprs])
    for i, entry in enumerate(meta):
        if entry[0] != "span":
            continue
        _tag, glue, n_toks, gis, expr = entry
        if counts.get(i, 0) <= 0:
            continue
        cur = span_acc.get(glue)
        if cur is None:
            span_acc[glue] = (n_toks, gis, [expr])
        else:
            if expr not in cur[2]:
                cur[2].append(expr)
            span_acc[glue] = (cur[0], cur[1] | gis, cur[2])
    span_hits = [
        (glue, n_toks, gis, exprs)
        for glue, (n_toks, gis, exprs) in sorted(
            span_acc.items(), key=lambda kv: (kv[1][0], len(kv[0]), kv[0]))
    ]
    # 3) SUPERSEDE до resolve_values (excluded_gis — вне матча)
    _probe_apply_span_supersede(
        per_group, len(groups), span_hits, diag, excluded_gis=excluded_gis)
    # РЕЗОЛВЕР — ФОЛЛБЭК ДЛЯ ГРУПП БЕЗ СОВПАДЕНИЯ. Если слово не нашлось ни точно, ни по
    # опечатке, ни подстрокой — оно записано в базе иначе (сокращение, разговорное имя).
    # Спрашиваем резолвер: слово -> конкретные значения базы, и ищем уже по ним, точной
    # фразой. Срабатывает ТОЛЬКО там, где буквальный поиск дал ноль, поэтому на работающие
    # вопросы не влияет — у них совпадение есть. Резолвленное значение видно в ответе:
    # человек проверит, то ли слово поняли.
    for gi, group in enumerate(groups):
        if gi in excluded_gis:
            continue
        if gi in per_group:
            continue                           # уже нашлось буквально — резолвить нечего
        vals = []
        for alt in group:
            vals = resolve_values(alt)
            if not vals:
                vals = _resolve_values_literal(alt)
            _resolved_kind = "resolved"
            if not vals:
                vals = _resolve_values_corpus(alt)
                _resolved_kind = "corpus_literal"
            if vals:
                break
        if vals:
            if _resolved_kind == "corpus_literal":
                exprs = ["ts_like(%s)" % lit(v) for v in vals]
            else:
                exprs = ["ts_phrase(%s)" % lit(v) for v in vals]
            per_group[gi] = (0, exprs, _resolved_kind)
            diag.setdefault("_resolved", {})[gi] = vals

    out = []
    for gi in sorted(k for k in per_group):
        rank, exprs, kind = per_group[gi]
        out.append(exprs[0] if len(exprs) == 1 else "ts_any([%s])" % ", ".join(exprs))
        # 🔴 РАЗРЕШЁННОЕ РЕЗОЛВЕРОМ ПОНЯТИЕ — НАЙДЕННОЕ. Прежде отметка ставилась всем,
        # КРОМЕ разрешённых резолвером, а вызывающий считает найденные понятия ровно по
        # этим отметкам (`matched_groups`). Выходило, что резолвер отрабатывал, значения
        # находил, выражение поиска возвращал — и тут же объявлялся неудачей: у вопроса из
        # одного понятия `matched_groups` = 0, и `answer` отдавал `no_data` ДО того, как
        # запрос вообще собирался. То есть путь, заведённый ради «Питера» (`resolve_values`:
        # подстрокой 0, в базе 180 записей про Санкт-Петербург), гасил сам себя на
        # единственном классе вопросов, ради которого сделан, — а отказ при наличии данных
        # это дефект (п. 21 `TARGET.md`), не осторожность.
        # Сами значения по-прежнему лежат отдельно, в `_resolved`: они уходят в ответ,
        # чтобы человек видел, каким словом его слово поняли (п. 13).
        diag[gi] = kind
    return out, diag


def matched_group_count(kinds):
    """Сколько понятий вопроса нашли себе совпадение — считая разрешённые резолвером.

    Отдельной функцией, а не строкой внутри `answer`, по одной причине: от этого числа
    зависит отказ («значения из вопроса не найдены в данных»), то есть решение не отвечать
    при живых данных. Прибор `test_step2.py` проверяет его без базы, сети и модели.

    Ключи-числа в `diag` ставит `probe` каждому найденному понятию; строковые ключи
    (`_resolved`) несут значения, а не отметки, и в счёт не идут.
    """
    return len([g for g in (kinds or {}) if isinstance(g, int)])


def with_refs(expr):
    """Искать по строке И по полю ссылок, ссылкам — вес.

    Множество строк от этого не меняется (см. REFS_BOOST): `refs` собран из тех же
    кусков, что и `doc`. Меняется порядок: совпадение в ссылке на другой объект весит
    больше случайного совпадения в тексте. Поле было построено и проиндексировано ровно
    ради этого, но в отборе не участвовало ни разу — платили за него и не пользовались.
    """
    return "(doc @@ %s OR refs @@ (%s ^ %s))" % (expr, expr, REFS_BOOST)


def match_expr(exprs, preds):
    """Собрать условие поиска с ГРАДИЕНТОМ: сперва все понятия, потом мягче.

    `ts_any(массив, k)` — «не меньше k из N». Прежний обрыв «всё → любое» на вопросе
    «поступления от ООО ТехноСнаб» давал либо ноль, либо всё, где есть «ООО».
    """
    n = len(exprs)
    if not n:
        return "", 0
    if n == 1:
        return with_refs(exprs[0]), 1
    # Один запрос вместо цикла по k: ts_compound(must, must_not, should, k) — штатный
    # булев запрос движка (замерено: 6.9 мс против 42.5 мс у цикла из трёх шагов).
    # Градиент сохраняем данными: берём наибольшее k, при котором есть совпадения.
    # Здесь СЧИТАЕМ, а не ранжируем, поэтому вес ссылок не нужен: множество строк у
    # `doc @@ X` и у `doc @@ X OR refs @@ (X^N)` одно и то же (замер в REFS_BOOST),
    # а лишний терм в запросе — лишняя работа на каждом из n шагов градиента.
    counts = psql(" UNION ALL ".join(
        "SELECT %d k, count(*) FROM %s WHERE %s" % (
            k, INDEX, " AND ".join(
                ["doc @@ ts_compound(NULL, NULL, [%s], %d)" % (", ".join(exprs), k)]
                + preds))
        for k in range(n, 0, -1)))
    best = 1
    for r in counts:
        try:
            if int(r[1]) > 0:
                best = max(best, int(r[0]))
        except (ValueError, IndexError):
            continue
    return with_refs("ts_compound(NULL, NULL, [%s], %d)" % (", ".join(exprs), best)), best


def tables_of(match, preds):
    """Разложить ВСЁ множество совпадений по источникам — группировкой в индексе.

    Раньше источники считались по 40 строкам, отобранным по рангу. BM25 штрафует
    длинные документы, поэтому справочник вытеснял документы из выдачи целиком:
    замерено — 74 строки из четырёх таблиц документов не попадали в кандидаты вовсе,
    и выбирать приходилось между неверными.
    """
    where = " AND ".join([w for w in ([match] + preds) if w]) or "TRUE"
    src = INDEX if match else CORPUS
    out = {}
    for r in psql("SELECT src_table, count(*) FROM %s WHERE %s GROUP BY 1" % (src, where)):
        try:
            out[r[0]] = int(r[1])
        except (ValueError, IndexError):
            pass
    return out


def keep_empty_period_opts(srcs, counted, preds):
    """Вилка прочтений в пустом окне: если все кандидаты пусты по дате — оставить.

    Иначе (кто-то жив) — прежнее: в перечень только живой счёт. counted is None
    — база не ответила, список не режем.
    """
    srcs = list(srcs or [])
    if counted is None:
        return srcs
    live = [s for s in srcs if counted.get(s, 0) > 0]
    if live:
        return live
    dated = any("doc_date" in str(p) for p in (preds or []))
    if dated:
        return srcs
    return live


def alias_hits(exprs, limit):
    """Сущности, чьи СИНОНИМЫ отвечают понятиям вопроса. Отбор ведёт база.

    🔴 ЭТО ПОИСКОВАЯ ПОВЕРХНОСТЬ, А НЕ ПОЗДНЯЯ ПРОВЕРКА. До 03.08 словарь синонимов
    (`search_entity_alias`, собирается один раз при установке штатным агентом) читался
    ТОЛЬКО в `_alias_verdict` — то есть после того, как сущность уже выбрана, и лишь
    затем, чтобы подтвердить или подобрать соперников. Знание при этом было верным и
    лежало без дела: [замер 03.08] у `document_реализациятоваровуслуг` синоним «продажа»
    в словаре есть, и по `alias_idx` эта сущность входит в тройку, тогда как буквальный
    отбор по тому же вопросу даёт её 272 совпадениями против 7 307 у регистра
    себестоимости — то есть топит верное в шуме.

    Условие берётся ТО ЖЕ, что и для корпуса (`probe` → `exprs`): ни одного нового
    способа сравнения, ни списка слов. `k=1` — «хотя бы одно понятие вопроса»: здесь мы
    не отвечаем, а лишь ДОБАВЛЯЕМ кандидата, которого дальше судят реранкер и модель.

    Разделитель равенства обязателен (`techContext` ловушка 30): без него `LIMIT`
    отрезает по порядку исполнения. [замер 03.08] по слову «продажа» четыре сущности
    имеют ровно одну оценку 4,6122875 — верный документ и три чужих (`F243`).
    """
    if not exprs:
        return []
    expr = exprs[0] if len(exprs) == 1 else \
        "ts_compound(NULL, NULL, [%s], 1)" % ", ".join(exprs)
    try:
        rs = psql("SELECT src_table, %s AS s FROM %s WHERE aliases @@ %s "
                  "ORDER BY s DESC, src_table LIMIT %d"
                  % (SCORERS.get(SCORER, SCORERS["bm25"]) % ALIAS_INDEX,
                     ALIAS_INDEX, expr, limit))
    except RuntimeError:
        return []                       # словаря нет (база без вики) — молча без него
    return [r[0] for r in rs if r and r[0]]


def card_hits(exprs, limit):
    """Сущности, чья КАРТОЧКА отвечает понятиям вопроса СЛОВАМИ. Отбор ведёт база.

    Четвёртая поверхность отбора (04.08). Карточка (`search_entity_card`) до сих пор
    служила только источником ВЕКТОРА, хотя такт строит по ней и инвертированный индекс:
    поверхность была построена и ни разу не спрошена. Спрашиваются все её поля разом —
    название, синонимы, описание, имена величин и имена реквизитов; движок допускает это
    одним запросом («a query may constrain any subset of the indexed fields, in any
    combination» — доки SereneDB, «Operator classes and fields»), а объединение через OR
    с одним скорером показано там же в разделе «Boosting».

    🔴 ЧТО ИМЕННО ОНА ДОБАВЛЯЕТ, ЧЕГО НЕТ У ОСТАЛЬНЫХ — имена реквизитов сущности.
    `[замер 04.08]` вопрос «Кто нам поставляет товар?» не доносила НИ ОДНА поверхность:
    в синонимах справочника партнёров слова «поставщик» нет, по смыслу он на 338-м месте
    (верх занят служебными «Использовать Соглашения СПоставщиками»), в корпусе тонет —
    164 его строки против 293 строк регистра себестоимости в первых четырёхстах по
    релевантности. А реквизит «Поставщик» у него есть, и по нему сущностей всего три.
    Своей поверхностью карточка доносит верную сущность в 32 случаях из 44 (73 %) — это
    больше любой другой лексической, — а в сумме с прочими закрывает последний вопрос
    набора: **44 из 44**.

    Цена `[замер 04.08]` — 63 мс на 1 502 карточки: индекс маленький, потому что в нём
    одна строка на сущность, а не на запись. Нет индекса (карточка не собрана, такт
    старый) — молча работаем без этой поверхности, как и без словаря синонимов.
    """
    if not exprs:
        return []
    expr = exprs[0] if len(exprs) == 1 else \
        "ts_compound(NULL, NULL, [%s], 1)" % ", ".join(exprs)
    cond = " OR ".join("%s @@ %s" % (f, expr) for f in CARD_FIELDS)
    try:
        rs = psql("SELECT src_table, %s AS s FROM %s WHERE %s "
                  # разделитель равенства — та же ловушка 30, что и у синонимов
                  "ORDER BY s DESC, src_table LIMIT %d"
                  % (SCORERS.get(SCORER, SCORERS["bm25"]) % CARD_INDEX,
                     CARD_INDEX, cond, limit))
    except RuntimeError:
        return []                       # индекса карточки нет — молча без него
    return [r[0] for r in rs if r and r[0]]


def question_exprs(exprs, kind_text):
    """ПОНЯТИЯ ВОПРОСА ЦЕЛИКОМ: значения из вопроса плюс род записей.

    Шаг 1 кладёт в `terms` ЗНАЧЕНИЯ (имя контрагента, товар), а род записей — в `kind`, и в
    `terms` его нет намеренно. `[замер 04.08]` у 47 вопросов из 58 `terms` пусты вовсе, то
    есть работая на одних `terms`, мы работаем на пустом месте. Понятия рода спрашиваются
    ОТДЕЛЬНЫМ `probe`, а не добавлением группы в общий: иначе изменились бы выражения
    буквального отбора, то есть тихо поменялся бы шаг 2.

    Вынесено отдельно, потому что этих понятий требуют ДВА разных места (отбор кандидатов
    смыслом и подтверждение выбора по словарю синонимов), а две копии неизбежно разошлись бы.
    """
    exprs_kind = []
    if kind_text:
        try:
            exprs_kind, _ = probe([[kind_text]])
        except RuntimeError:
            exprs_kind = []                 # база молчит — работаем на том, что есть
    return list(exprs) + [e for e in exprs_kind if e not in exprs]


def meaning_candidates(exprs, kind_text, question, limit, exclude=(), diag=None):
    """ШАГ 3 ЦЕЛИКОМ: кандидаты, добытые не буквальным совпадением слов записи.

    Собран в одном месте по двум причинам. Первая: у шага появился свой прибор
    (`work/acceptance/step3_bench.py`), и он зовёт этот код, а не свою копию, — прежний
    прибор приближал разбор вопроса словами самого вопроса и показывал у поверхности
    синонимов 43 % там, где в бою было 5 %. Вторая: четыре поверхности с двумя входами
    каждая перестали читаться внутри `answer`.

    Четыре независимых источника, ни один не закрывает остальные:
      1. синонимы сущности   — `alias_hits`, словарь, собранный при установке;
      2. слова карточки      — `card_hits`, включая ИМЕНА РЕКВИЗИТОВ сущности;
      3. смысл вопроса       — `near_tables` по тексту вопроса;
      4. смысл рода записей  — `near_tables` по `kind` шага 1.
    Буквальный отбор (`by`) сюда не входит: он делается шагом 2 и приходит в `exclude`.

    🔴 ДВА ВХОДА, А НЕ ОДИН. Шаг 1 кладёт в `terms` ЗНАЧЕНИЯ (имя контрагента, товар), а
    род записей — в `kind`, и в `terms` его нет намеренно. Лексические поверхности
    описывают как раз род, поэтому им идут оба входа; смысловые спрашиваются и вопросом,
    и родом. `[замер 04.08]`, 44 пары приёмки, настоящие разборы шага 1: синонимы на
    `terms` доносят верную сущность 2 раза (5 %), на `terms`+`kind` — 21 (48 %); смысл на
    «род ИЛИ вопрос» — 20 (45 %), по вопросу — 29 (66 %). Сумма всех поверхностей вместе
    с буквальным отбором: было **23 из 44 (52 %)**, стало **44 из 44 (100 %)**.

    Понятия рода спрашиваются ОТДЕЛЬНЫМ `probe`, а не добавлением группы в общий: иначе
    изменились бы выражения буквального отбора, то есть тихо поменялся бы шаг 2.
    """
    exprs_all = question_exprs(exprs, kind_text)
    out = _fused_candidates(exprs_all, kind_text, question, limit, diag=diag)
    if out is None:
        # Слияние не собралось (нет карточки, лёг эмбеддер, старая база) — прежний путь:
        # те же поверхности по отдельности, порядок «одна за другой».
        out = []
        for src_from in (alias_hits(exprs_all, limit),
                         card_hits(exprs_all, limit),
                         near_tables(question, limit),
                         near_tables(kind_text, limit) if kind_text else []):
            for t in src_from:
                if t not in out:
                    out.append(t)
    return [t for t in out if t not in exclude]


register_zone('ask.z06_entity_search', globals())
