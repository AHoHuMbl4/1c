"""Zone 20: ask / HTTP (ask-main-http) — новый тракт «один путь» (волна B2).

Инфраструктура перенесена bit-identical из z20_ask_main_http_legacy.py.
Тело answer() — временная заглушка unavailable до волны B3.
В runtime/_bootstrap не грузится до flip (B6). Эскиз: docs/audit/onepath/O2-project.md §2.1.
"""
from __future__ import annotations

from ask._imports import *
from ask._wire import register_zone, apply_bindings

apply_bindings(globals())

def _filter_dates(intent):
    """Границы периода, по которому МЫ отобрали строки: «с 01.01.2019 по 31.12.2019».

    Они верны по построению — фильтр применён нами, — но в данных такой строки может и
    не быть (никто не продавал ровно 1 января), и тогда гейт отвергал верный ответ,
    назвавший период отбора. Тот же случай, что и с порогом суммы 27.07, только про дату.
    """
    p = (intent or {}).get("period") or {}
    p2 = (intent or {}).get("period2") or {}
    return [str(x) for x in (p.get("from"), p.get("to"), p2.get("from"), p2.get("to")) if x]


LIST_MARKER = re.compile(r"^[ \t]*\d+[.)][ \t]+", re.M)
# Перечисление внутри строки: «Итого 5: 1) первая, 2) вторая». Номер пункта здесь тоже
# разметка, а не число из данных, — но опознаётся он уже, чем в начале строки: не больше
# двух цифр и сразу после двоеточия, точки с запятой или запятой. `[замер 04.08]` без
# этого прибор шага 7 отвергал 7 верных ответов из 44 вопросов на одной лишь нумерации.
INLINE_MARKER = re.compile(r"(?<=[:;,])[ \t]*\d{1,2}[.)][ \t]+")


def without_list_markers(text):
    """Разметка списка — не утверждение о данных (`F248`).

    «1.», «2)» в начале строки нумеруют пункты. Гейт считал их наравне с суммами, и
    любой перечисленный ответ («Итого 5: 1) первая, 2) вторая») объявлялся выдумкой —
    `[замер 04.08, step7_bench]` 4 верных ответа из 44 вопросов отвергнуты только за
    нумерацию. Плагин на стороне бота снимает их с 02.08 (`withoutListMarkers`), а
    сервис — нет: одна и та же разметка на двух половинах шага 7 значила разное.
    Снимается ТОЛЬКО маркер пункта, содержимое пункта проверяется как обычно. Маркеров
    два вида: в начале строки (номер любой длины — так пишут списки) и внутри строки
    после двоеточия или запятой (не больше двух цифр — так пишут перечисление в прозе).
    Асимметрия намеренная: в начале строки «103.» — почти наверняка нумерация, а в
    середине предложения такое число скорее величина, и снимать его было бы послаблением.
    """
    return INLINE_MARKER.sub("", LIST_MARKER.sub("", str(text or "")))


def rows_seen(rows):
    """Строки в том виде, в каком их ВИДЕЛА модель: показанные и обрезанные (`F247`).

    🔴 Гейт заземлял ответ на ВСЕХ добытых строках (`TOPK` = 40), тогда как модели
    показывается `ROWS_TO_MODEL` = 25, и каждая ещё режется бюджетом. Числа из
    непоказанных строк и из отрезанных хвостов служили белым списком для того, чего
    модель не видела: `[замер 04.08, step7_bench]` подменённые крайние значения (31, 7)
    проходили гейт, потому что где-то в невидимой строке такие числа есть.

    Скопировать модель может только то, что ей дали, поэтому сужение не может отвергнуть
    верный ответ — оно лишь снимает лишнее разрешение. Срез и бюджет считаются теми же
    правилами, что в `compose`: одна граница на оба места.
    """
    shown = list(rows or [])[:ROWS_TO_MODEL]
    per_row = max(320, ROWS_BUDGET // max(1, len(shown)))
    out = []
    for r in shown:
        try:
            doc = r[5]
        except (TypeError, IndexError):
            continue
        if not isinstance(doc, str):
            doc = "" if doc is None else str(doc)
        out.append(list(r[:5]) + [doc[:per_row]])
    return out


def gate(answer, rows, agg, thresholds=None, our_dates=None, money=True,
         slot_mode=None):
    """Числа ответа сверяются кодом с данными, итогом и нашими условиями.

    Правило живёт в КОДЕ, а не в промте: промт — это пожелание, а не гарантия.
    Числа из вопроса НЕ разрешаются: «вопрос» приходит как аргумент инструмента,
    и составляет его модель бота — то есть проверяемый сам пополнял бы белый список.

    🔴 ИСКЛЮЧЕНИЕ — пороги НАШИХ СОБСТВЕННЫХ условий (`thresholds`). Это не число из
    текста вопроса, а значение, по которому МЫ отфильтровали данные: оно верно по
    построению, потому что фильтр применён нами и проверен кодом. [замер 27.07] без
    этого исключения вопрос «какие продажи были на сумму больше 500000» получал отказ,
    хотя ответ был верен целиком: сумма 9 101 800 на 11 документов, максимум 1 629 700 —
    всё сошлось с базой. Не пустило единственное число — 500 000, наш же порог,
    названный в ответе как описание отбора. Это ровно п. 21 TARGET.md: данные есть,
    ответ верен, а не отдала его собственная проверка.
    """
    allowed = set()

    def allow(v):
        """Значение и все его равнозначные прочтения: округление, целое, БЕЗ ЗНАКА.

        🔴 Минус в числовой токен не входит (`NUMTOK` начинается с цифры), поэтому
        посчитанное базой отрицательное значение не совпадало с тем, что читает
        гейт из текста: ответ «наименьшая -70 552,79» отвергался, хотя это ровно `min`
        из агрегата `[замер 04.08, step7_bench, 21 случай из 1484]`. Возвраты, сторно и
        отрицательные остатки — обычные данные 1С, и отказ на них означал отказ при
        наличии данных (п. 21). Знак при этом ничего не разрешает лишнего: величина всё
        равно сверяется с данными, а «-5» и «5» гейт и так не различал бы.
        """
        try:
            f = float(v)
        except (TypeError, ValueError):
            return
        for x in (f, abs(f)):
            allowed.add(round(x, 2))
            if x == int(x):
                allowed.add(float(int(x)))

    for t in (thresholds or []):
        allow(t)
    group_grain = bool(agg) and agg.get("grain") == "group"
    if slot_mode is None:
        slot_mode = "rank" if group_grain else "list"
    # Стоп 1: цифры показанных строк — только list. Иначе счёт/лидер/сумма строки
    # подписываются чужой ролью.
    row_nums = slot_mode == "list"
    for r in rows:
        if row_nums:
            allowed |= _norm_numbers(r[5])
            allowed |= _norm_numbers(r[3])
        # amount приходит из psql как «5000000.00» — через текстовый разбор это давало
        # ещё и 500000000. Берём числом.
        # Зерно group: число строки корпуса — не итог объекта. Белый список — группы.
        if money and not group_grain and row_nums:
            allow(r[2])
    if agg:
        # ЧИСЛАМИ, а не текстом: прогон "%.2f" через разбор давал ещё и значение,
        # умноженное на 100 (дробная часть склеивалась с целой).
        if slot_mode == "count":
            pass
        elif slot_mode == "compare":
            if money:
                allow(agg.get("sum"))
        elif slot_mode == "sum":
            if money:
                if group_grain:
                    allow(agg.get("sum"))
                    allow(agg.get("n_groups"))  # служебное множество, не роль итога
                else:
                    for key in ("sum", "min", "max", "avg"):
                        if agg.get(key) is not None:
                            allow(agg[key])
        elif slot_mode == "rank" and group_grain:
            for k in ("sum", "leader", "count", "count_amount",
                      "n_groups", "min", "max", "avg"):
                allow(agg.get(k))
            for g in agg.get("groups") or []:
                for gk in ("value", "count", "value2", "count2",
                            "sum", "avg"):
                    allow(g.get(gk))
                allowed |= _norm_numbers(g.get("name") or "")
        elif group_grain:
            allow(agg.get("sum"))
            allow(agg.get("n_groups"))
            allow(agg.get("leader"))
            for g in agg.get("groups") or []:
                allow(g.get("value"))
                allow(g.get("count"))
                allow(g.get("value2"))
                allow(g.get("count2"))
                if money:
                    allow(g.get("sum"))
        elif money:
            for key in ("sum", "min", "max", "avg"):
                if agg.get(key) is not None:
                    allow(agg[key])
        # Стоп 1: счёт строк — не свободный токен sum/rank (класс «15 рядом с суммой»).
        # На count/list — слот формы. Показать счёт на sum/rank может код после гейта.
        if slot_mode in ("count", "list"):
            allow(agg["count"])
    # Числа из ВОПРОСА в белый список больше не идут. Вопрос — это аргумент, который
    # сочиняет модель бота: она сама пополняла список того, что ей разрешено сказать,
    # и через это проходило любое выдуманное число.

    # Даты: названная дата сверяется с датой из данных покомпонентно.
    known = []
    for r in rows:
        try:
            known += _dates(r[3]) + _dates(r[5])
        except (TypeError, IndexError):
            continue
    # Границы периода (`date_min`/`date_max`) посчитаны базой по ВСЕМУ множеству, а `rows`
    # — лишь показанная выборка (LIMIT): строки с крайней датой в ней может не быть.
    # [замер 28.07] из-за этого верный ответ с «28.02.2026» (это `date_max`) отвергался
    # через раз. Даты-агрегаты разрешены наравне со строчными — они проверены базой.
    if agg:
        known += _dates(agg.get("date_min") or "") + _dates(agg.get("date_max") or "")
    # Границы НАШЕГО периода отбора — на тех же правах, что порог суммы: фильтр применён
    # нами, значит дата верна по построению, даже если ровно в этот день строк нет.
    for s in (our_dates or []):
        known += _dates(s)
        # День и месяц границ нашего периода — те же числа фильтра, что год (F245):
        # «с 7 по 14 августа» иначе режет ответ, где модель повторила период.
        for _kd, _kmo, _ky in _dates(s):
            if _kd is not None:
                allowed.add(float(_kd))
            if _kmo is not None:
                allowed.add(float(_kmo))

    # 🔴 ГОД ИЗВЕСТНОЙ ДАТЫ — ЭТО ЧИСЛО ИЗ ДАННЫХ (`F245`). Дата в строке (`2019-11-18`)
    # вырезается токенайзером как дата, поэтому «2019» отдельным числом в разрешённое не
    # попадало ниоткуда: ответ «за 2019 год продано на 1 236 800» отвергался целиком —
    # из-за года, стоящего в данных `[замер 04.08, probe_gate]`. Год берётся только из
    # ИЗВЕСТНЫХ дат (строки, границы агрегата, наш период), то есть выдуманный «2035» не
    # проходит. Отвергать верный ответ — такой же дефект, как пропустить неверный (п. 21).
    for _kd, _kmo, _ky in known:
        if _ky is not None:
            allowed.add(float(_ky))

    # Токен обоснован, если ХОТЯ БЫ ОДНО его прочтение есть в данных. Нумерация пунктов
    # утверждением о данных не является и снимается до разбора (`F248`).
    answer = without_list_markers(answer)
    bad = [_fmt_gate_bad(sorted(r)[0])
           for r in _tokens(answer) if not (r & allowed)]

    for d, mo, y in _dates(answer):
        ok = any(kd == d and kmo == mo and (y is None or ky is None or ky == y)
                 for kd, kmo, ky in known)
        # Двухкомпонентная запись без года неоднозначна: «10.5» — это и дата, и дробь.
        # Разрешаем, если такое ЧИСЛО есть в данных; выдуманное не пройдёт ни как дата,
        # ни как число.
        # 🔴 Дробь берётся ИЗ ИСХОДНОГО ТЕКСТА, а не собирается обратно из компонентов
        # `"%d.%d" % (d, mo)`: та сборка теряла ведущий ноль, и «20.05» превращалась в
        # 20.5 — то есть верное число, стоящее в данных, не заземлялось ни разу, а
        # ответ отвергался целиком `[замер 02.08, test_gate.py]`. Ровно тот класс, что
        # п. 21 называет дефектом проверки.
        if not ok and y is None:
            ok = bool(_date2_readings(answer, d, mo) & allowed)
        if not ok:
            bad.append("%02d.%02d%s" % (d, mo, "" if y is None else ".%d" % y))
    return (not bad), bad


def gate_out(text, rows=(), agg=None, allowed=None, our_dates=None, money=True,
             slot_mode=None):
    """Один гейт на ВСЁ, что уходит человеку словами модели: числа + утечка инструкции.

    🔴 Заведён 04.08 (`F246`), потому что гейт стоял только на одной ветке из пяти.
    Числа проверялись у `kind=answer`, а уходящий человеку текст сочиняет модель ещё в
    четырёх местах: три уточнения о выборе сущности, уточнение о выборе величины и
    встречный вопрос модели (`ask`). Ни одно из них не проверялось ничем — при том что
    `HOW_IT_WORKS` про уточнение прямо утверждал обратное («уточнение возвращается
    только после гейта — числа в нём проверены базой наравне с обычным ответом»).
    Человеку разница не видна: «Вы про закупки на 73 млн или про регистр?» читается как
    факт о его данных независимо от того, вопрос это или ответ.
    """
    ok, bad = gate(text, list(rows or []), agg, allowed or [], our_dates,
                   money=money, slot_mode=slot_mode)
    leak = prompt_leak(text, OUR_PROMPTS)
    if leak:
        ok, bad = False, list(bad) + ["утечка инструкции: %s" % leak]
    return ok, bad


def _opt_values(opts):
    """Числа, которые модель ВИДЕЛА, сочиняя уточнение: имена вариантов и их приметы.

    Больше ей ничего не давали (`clarify_text` кладёт в задание только вопрос, метки и
    `distinct_by`), поэтому всё остальное числовое в уточнении — сочинённое.
    """
    out = []
    for o in (opts or []):
        for k in ("label", "distinct_by", "measure", "entity_label"):
            out += sorted(_norm_numbers(o.get(k) or ""))
        if o.get("found") is not None:
            try:
                out.append(float(o["found"]))
            except (TypeError, ValueError):
                pass
    return out


def clarify_choice_prompt(question, label):
    """Короткая строка-вопрос варианта — форма, которую follow-up WebUI берёт чипом.

    Вопрос человека (язык спрашивающего) + человеческая подпись. Предлог не
    зашивается: двоеточие не привязано к языку. Подпись, уже входящая в вопрос,
    второй раз не дублируется.
    """
    stem = (question or "").strip().rstrip("?").strip()
    lab = (label or "").strip()
    if not lab:
        return (stem + "?") if stem else ""
    if lab.lower() in stem.lower():
        return stem + "?"
    if stem:
        return "%s: %s?" % (stem, lab)
    return lab + "?"


def clarify_choice_line(n, question, opt):
    """Одна строка выбора: «N. вопрос: Подпись? — описание»."""
    lab = (opt.get("label") or opt.get("measure") or "").strip()
    prompt = clarify_choice_prompt(question, lab)
    hint = (opt.get("hint") or "").strip()
    if hint:
        return "%d. %s — %s" % (n, prompt, hint)
    return "%d. %s" % (n, prompt)


def format_clarify_options(question, opts):
    """Все варианты уточнения одним видом строк. Пустых пунктов нет."""
    lines, n = [], 0
    for o in opts or []:
        oo = o
        lab = (o.get("label") or "")
        if lab and label_has_meta_src(lab):
            oo = dict(o)
            oo["label"] = human_table_label(o.get("src"), lab)
        hint = (oo.get("hint") or "")
        if hint and label_has_meta_src(hint):
            if oo is o:
                oo = dict(o)
            oo["hint"] = ""
        if not (oo.get("label") or oo.get("measure")):
            continue
        n += 1
        lines.append(clarify_choice_line(n, question, oo))
    return lines


def clarify_say(question, opts, diag=None):
    """Уточнение — нумерованные строки-вопросы из ДАННЫХ, не проза модели.

    Каждый пункт виден целиком (подпись + hint) и сам является коротким вопросом,
    который follow-up-генератор WebUI может скопировать в чип. Молчания нет: пустой
    перечень — пустая строка, вызывающий подставит свой fallback.
    """
    lines = format_clarify_options(question, opts)
    body = "\n".join(lines)
    if not body:
        return ""
    hint_dates = []
    for o in (opts or []):
        for k in ("label", "distinct_by", "hint", "entity_label"):
            hint_dates.append(str(o.get(k) or ""))
    ok, bad = gate_out(body, [], None, _opt_values(opts), hint_dates)
    if ok:
        return body
    sys.stderr.write("ask CLARIFY GATE: числа вне вариантов: %s\n" % bad[:4])
    if isinstance(diag, dict):
        diag["clarify_gate_rejected"] = bad[:4]
    stripped = [dict(o, hint="", found=0) for o in (opts or [])]
    return "\n".join(format_clarify_options(question, stripped))


def clarify_opts_response(question, opts, diag, cut, t0, *, reason="", gate_ok=False,
                          partial=None, sources=None, extra_diag=None):
    clean = []
    for o in opts or []:
        if not o:
            continue
        co = dict(o)
        co["found"] = 0
        if co.get("label") or co.get("measure"):
            clean.append(co)
    if len(clean) < 2:
        return None
    d = dict(diag or {})
    if extra_diag:
        d.update(extra_diag)
    text = clarify_say(question, clean, d)
    if not text:
        text = ", ".join("«%s»" % (o.get("label") or o.get("measure") or "")
                         for o in clean)
    srcs = sources if sources is not None else [o.get("label") or "" for o in clean]
    return {"partial": partial if partial is not None else (cut or None),
            "kind": "clarify", "text": text, "options": clean,
            "sources": srcs,
            "diag": _diag_pack(d, sec=round(time.time() - t0, 2),
                               gate_ok=gate_ok, reason=reason or None)}


# 🔴 ВИТРИНА ИЗМЕРЯЕТСЯ ЖИВЬЁМ, А НЕ ПО ПЕРЕПИСИ (15.08, аудит §3). Перепись
# (`search_coverage`) считает витрину только своим тактом; когда таймер сборки
# остановлен, а витрина уже восстановлена, перепись показывает «полно» при разрыве в
# сотни тысяч строк — прод был ложно зелёный. Поэтому самый полный слой считается
# СЕЙЧАС штатным `query_table` (доки SereneDB: «SQL › Functions › Utility Functions —
# query_table(tbl_name)»; имя — литерал, как в `coverage_build`).
# Сравнение — по ОБЪЕКТАМ, а не по строкам: у ссылочного объекта табличная часть
# развёрнута в витрине в несколько строк, а в корпусе объект — одна строка (та же
# поправка, что `объектов_витрины` в переписи). Объект определяется ключом `Ref_Key`,
# где такая колонка есть; где её нет (регистры) — строка и есть объект.
def _entity_counts_objects(src_table):
    """Сущность считается по Ref_Key — как `coverage_build` / tmp3_key, не duckdb_columns."""
    try:
        r = psql("SELECT count(*) FROM tmp3_key "
                 "WHERE entity = lower(%s) AND key_cols = ['Ref_Key']"
                 % lit(src_table))
        if int(_num(r[0][0])) > 0:
            return True
    except RuntimeError:
        pass
    try:
        r = psql("SELECT count(*) FROM duckdb_columns() "
                 "WHERE database_name = current_database() "
                 "  AND table_name = %s AND column_name = 'Ref_Key'"
                 % lit(src_table))
        return int(_num(r[0][0])) > 0
    except RuntimeError:
        return False


def _vitrina_objects(src_table):
    """Число объектов сущности в витрине. None — витрины нет или она не читается."""
    try:
        r = psql("SELECT count(*) FROM duckdb_tables() "
                 "WHERE database_name = current_database() AND table_name = %s"
                 % lit(src_table))
        if int(_num(r[0][0])) == 0:
            return None
        has_rk = _table_has_ref_key(src_table)
        q = ("SELECT count(DISTINCT \"Ref_Key\") FROM query_table(%s)" if has_rk
             else "SELECT count(*) FROM query_table(%s)") % lit(src_table)
        return int(_num(psql(q)[0][0]))
    except (RuntimeError, TypeError, ValueError, IndexError):
        return None


# 🔴 FAIL-CLOSED ПО САМОМУ ПОЛНОМУ СЛОЮ (15.08, аудит §3). Прежде неполнота
# объявлялась только при `в_1С > в_корпусе` — по ДЕКЛАРАЦИИ источника из переписи.
# После восстановления витрины декларация устарела (витрина полнее неё), перепись не
# пересчитана, и ответы шли по заведомо неполному корпусу как полные: `в_1С` 8 295 =
# `в_корпусе` 8 295 при 77 179 строках в витрине. Теперь неполнота — разрыв ЛЮБОГО
# более полного доступного слоя с корпусом: декларация переписи, объекты витрины по
# переписи и живое число объектов витрины (`_vitrina_objects`). Корпус считается так
# же живьём — перепись здесь не аргумент ровно в той же мере.
def _coverage_of(src_table):
    """Неполнота ИМЕННО ТОЙ сущности, по которой отвечаем (п. 13).

    Общая перепись говорит «потеряно 5 993 строки», но человеку, спросившему про продажи,
    важно не общее число, а то, полны ли продажи. Отметка строится про его вопрос,
    иначе она превращается в шум, который перестают читать.
    """
    if not src_table:
        return None
    in_1c, obj_vit, corpus_n, reason = None, None, None, ""
    try:
        r = psql("SELECT в_1С, в_корпусе, объектов_витрины, coalesce(причина,'') "
                 "FROM search_coverage WHERE entity = %s" % lit(src_table))
        if r:
            in_1c = int(_num(r[0][0]))
            corpus_n = int(_num(r[0][1]))
            obj_vit = int(_num(r[0][2])) if len(r[0]) > 2 else None
            reason = r[0][3] if len(r[0]) > 3 else ""
    except RuntimeError:
        pass                                 # переписи нет — решают живые слои
    try:
        corpus_n = int(_num(psql(
            "SELECT count(*) FROM %s WHERE src_table = %s"
            % (CORPUS, lit(src_table)))[0][0]))
    except (RuntimeError, TypeError, ValueError, IndexError):
        pass                                 # живого счёта нет — остаётся перепись
    live_vit = _vitrina_objects(src_table)
    layers = []
    # в_1С часто = строки разворота, корпус = объекты. [замер 21.08 okna]
    # document_реализациятмц: в_1С=71601 vs объектов=8297 → ложный incomplete.
    if in_1c is not None and in_1c > 0:
        obj_ref = obj_vit or live_vit
        if obj_ref is None or in_1c <= obj_ref:
            layers.append((in_1c, "декларация 1С"))
    if obj_vit:
        layers.append((obj_vit, "витрина (перепись)"))
    if live_vit is not None:
        layers.append((live_vit, "витрина"))
    if not layers or corpus_n is None:
        return None                          # полноту оценить нечем — молчим, не выдумываем
    fuller, layer = max(layers, key=lambda x: x[0])
    if fuller <= corpus_n:
        return None
    gap = {"in_1c": fuller, "in_search": corpus_n,
           "missing": fuller - corpus_n, "layer": layer,
           "reason": reason or "более полный слой (%s) новее корпуса" % layer}
    build_ts = mart_ts = None
    try:
        for r in psql("SELECT k, v FROM search_quality "
                      "WHERE k IN ('build_ts','mart_changed_ts')"):
            if r and r[0] == "build_ts":
                build_ts = float(r[1])
            elif r and r[0] == "mart_changed_ts":
                mart_ts = float(r[1])
    except RuntimeError:
        pass
    if mart_ts and build_ts and mart_ts > build_ts:
        gap["kind"] = "freshness_lag"
        gap["merge_pending_sec"] = int(mart_ts - build_ts)
    else:
        gap["kind"] = "systemic"
    return gap


# 🔴 /health ВИДИТ ИЗВЕСТНЫЙ РАЗРЫВ ПОЛНОТЫ (15.08, аудит §3). До этого дверь
# проверяла только доступность корпуса и число его строк: на проде она отвечала
# `serene-ask-ok` при 590 955 строках, лежащих в витрине и не дошедших до корпуса.
# Живой обход `query_table` по каждой сущности на GET /health растёт с базой (п. 20)
# и не укладывается в таймаут сторожа: `[замер 24.08]` 3 таблицы × `_vitrina_objects`
# = 26 с (по 4 `psql()` на сущность); локальные `:8091`/`:8099` — 0 байт / curl 28
# при том, что журнал потом пишет 200 + BrokenPipe. Перепись `search_coverage`
# считает те же объекты внутри движка (`coverage_build.sql`, `query_table` + `Ref_Key`).
# Дверь читает её одним SQL. Живой `_vitrina_objects` остаётся у `_coverage_of`
# отвечаемой сущности, не у сторожа. Кэш — на TTL и под замком (без него повтор
# сторожа, пока первый замер ещё идёт, запускал бы второй полный обход).
_HEALTH_GAP_TTL = int(os.environ.get("ASK_HEALTH_GAP_TTL", "300"))
_health_gap_cache = {"at": 0.0, "gap": None}
_health_gap_lock = threading.Lock()
# Ф6.4: штатная свежесть inverted через sdb_metrics (num_buffered_docs и пр.).
# Выключен по умолчанию — прежняя эвристика mart/build; включён — native-поля
# рядом с merge_pending_sec, эвристика вторым рубежом. VACUUM из /health не зовём.
# Имя индекса — из env/конфига, не хардкод базы (умолч. search_idx = INDEX).
ASK_HEALTH_NATIVE_FRESHNESS = (
    os.environ.get("ASK_HEALTH_NATIVE_FRESHNESS", "0") == "1")
ASK_HEALTH_SEARCH_IDX = os.environ.get("ASK_HEALTH_SEARCH_IDX", "search_idx")
_HEALTH_RELNAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _assemble_health_gap(total_gaps, day_gaps):
    """Собрать coverage_gap из итогов и дневных разниц. None — разрыва нет."""
    rows_missing = 0
    rows_extra = 0
    worst_candidates = []
    seen_dated = {src for src, _d, _v, _c in (day_gaps or [])}
    for src, d, v, c in day_gaps or []:
        v, c = int(v), int(c)
        if v > c:
            rows_missing += v - c
        elif c > v:
            rows_extra += c - v
        if v != c:
            worst_candidates.append(
                (abs(v - c), {"src": src, "d": str(d) if d is not None else "",
                              "витрина": v, "корпус": c}))
    for src, (v, c) in (total_gaps or {}).items():
        if src in seen_dated:
            continue
        v, c = int(v), int(c)
        if v > c:
            rows_missing += v - c
        elif c > v:
            rows_extra += c - v
        if v != c:
            worst_candidates.append(
                (abs(v - c), {"src": src, "витрина": v, "корпус": c}))
    if rows_missing == 0 and rows_extra == 0:
        return None
    ents = {item["src"] for _n, item in worst_candidates}
    worst = [item for _n, item in sorted(worst_candidates, key=lambda x: x[0],
                                         reverse=True)[:5]]
    out = {"entities": len(ents), "rows_missing": rows_missing, "worst": worst}
    if rows_extra:
        out["rows_extra"] = rows_extra
    return out


def _table_has_ref_key(src_table):
    """Есть ли Ref_Key у сущности (делегат `_entity_counts_objects`)."""
    return _entity_counts_objects(src_table)


def _measure_health_gap():
    """Разрыв витрина↔корпус из переписи — один SQL, не цикл по сущностям.

    Перепись считает объекты витрины тем же `query_table`/`Ref_Key`, что
    `_vitrina_objects` (`coverage_build.sql`). Дверь не повторяет этот обход
    на каждый GET /health: это N×`psql()` и N полных count, и растёт с базой.
    """
    r = psql("SELECT entity, объектов_витрины, в_корпусе FROM search_coverage")
    total_gaps = {}
    for x in r or []:
        if not x or not x[0]:
            continue
        v, c = int(_num(x[1])), int(_num(x[2]))
        if v != c:
            total_gaps[x[0]] = (v, c)
    return _assemble_health_gap(total_gaps, [])


def _real_corpus_object_gaps():
    """Есть ли сущности с объектами витрины > в корпусе — реальный долг, не index publish.

    [замер 23.08 okna] 423k «missing» были строки разворота vs объекты корпуса.
    «не опубликовано в индекс» при полном корпусе — publish search_idx, не потеря данных;
    такой разрыв не оправдывает systemic 503.
    """
    try:
        r = psql("SELECT count(*) FROM search_coverage "
                 "WHERE объектов_витрины > в_корпусе "
                 "  AND coalesce(причина,'') <> %s"
                 % lit("не опубликовано в индекс"))
        return int(_num(r[0][0])) > 0
    except RuntimeError:
        return None


def _classify_health_gap(gap):
    """Различение лага свежести и системной дыры для /health (п. 13, [замер 17.08 okna]).

    Лаг: витрина новее последнего такта сборки (`mart_changed_ts` > `build_ts`) —
    разрыв догоняется таймером merge, 503 не нужен. Системная: сборка уже прошла после
    изменения витрины, а разрыв остался — только при объектном долге корпуса.
    """
    if not gap:
        return None
    out = dict(gap)
    build_ts = mart_ts = None
    try:
        for r in psql("SELECT k, v FROM search_quality "
                      "WHERE k IN ('build_ts','mart_changed_ts')"):
            if r and r[0] == "build_ts":
                build_ts = float(r[1])
            elif r and r[0] == "mart_changed_ts":
                mart_ts = float(r[1])
    except RuntimeError:
        pass
    if mart_ts and build_ts and mart_ts > build_ts:
        out["kind"] = "freshness_lag"
        out["merge_pending_sec"] = int(mart_ts - build_ts)
        out["build_age_sec"] = int(time.time() - build_ts)
        return out
    real = _real_corpus_object_gaps()
    if real is False:
        out["kind"] = "index_publish"
        return out
    out["kind"] = "systemic"
    return out


def _health_search_idx_name():
    """Имя inverted-индекса для native freshness — из env, не из конкретной базы."""
    name = ASK_HEALTH_SEARCH_IDX or "search_idx"
    if not _HEALTH_RELNAME_RE.match(name):
        raise ValueError("ASK_HEALTH_SEARCH_IDX: bad identifier")
    return name


def _measure_native_index_freshness():
    """Штатные метрики inverted: buffer/failed по индексу + process refresh_*.

    Один SELECT (UNION): per-index num_buffered_docs / num_failed_commits и
    process gauges refresh_pending / refresh_active. Без VACUUM (REFRESH_*).
    Доки: Maintenance › sdb_metrics; фактура docs/F6_FRESHNESS_FACTS.md §6.
    """
    idx = _health_search_idx_name()
    sql = (
        "SELECT 'index' AS kind,"
        " MAX(CASE WHEN m.metric = 'num_buffered_docs' THEN m.value END),"
        " MAX(CASE WHEN m.metric = 'num_failed_commits' THEN m.value END),"
        " NULL, NULL"
        " FROM sdb_metrics m"
        " JOIN pg_class c ON c.oid = m.relation_id"
        " WHERE c.relname = %s"
        " GROUP BY 1"
        " UNION ALL"
        " SELECT 'process', NULL, NULL,"
        " MAX(CASE WHEN metric = 'refresh_pending' THEN value END),"
        " MAX(CASE WHEN metric = 'refresh_active' THEN value END)"
        " FROM sdb_metrics"
        " WHERE relation_id IS NULL"
        "   AND metric IN ('refresh_pending', 'refresh_active')"
        % lit(idx)
    )
    rows = psql(sql)
    out = {
        "index_buffered_docs": None,
        "index_failed_commits": None,
        "refresh_pending": None,
        "refresh_active": None,
    }
    for r in rows or []:
        if not r:
            continue
        kind = r[0]
        if kind == "index":
            b, f = _numN(r[1]), _numN(r[2])
            if b is not None:
                out["index_buffered_docs"] = int(b)
            if f is not None:
                out["index_failed_commits"] = int(f)
        elif kind == "process":
            p, a = _numN(r[3]), _numN(r[4])
            if p is not None:
                out["refresh_pending"] = int(p)
            if a is not None:
                out["refresh_active"] = int(a)
    return out


def _attach_native_freshness(freshness, native=None, native_error=None):
    """Дописать native-поля; ошибка чтения — явный degraded, не подмена merge_pending."""
    if freshness is None:
        freshness = {}
    if native is not None:
        freshness["index_buffered_docs"] = native.get("index_buffered_docs")
        freshness["index_failed_commits"] = native.get("index_failed_commits")
        freshness["refresh_pending"] = native.get("refresh_pending")
        freshness["refresh_active"] = native.get("refresh_active")
    elif native_error is not None:
        freshness["index_metrics"] = "unknown"
        freshness["error"] = str(native_error)[:200]
    return freshness


def _health_gap():
    """Кэш замера разрыва для /health. Ошибка замера — исключение: дверь «не знает»."""
    now = time.time()
    if _health_gap_cache["at"] and now - _health_gap_cache["at"] < _HEALTH_GAP_TTL:
        return _health_gap_cache["gap"]
    with _health_gap_lock:
        now = time.time()
        if _health_gap_cache["at"] and now - _health_gap_cache["at"] < _HEALTH_GAP_TTL:
            return _health_gap_cache["gap"]
        gap = _measure_health_gap()
        _health_gap_cache["at"] = now
        _health_gap_cache["gap"] = gap
        return gap


def _health_period_relative_forms():
    """Готовность словаря относительных окон (meta или запасной файл).

    Пустой словарь → loaded=False: иначе «прошлая неделя» молча становится
    текущей (п. 13). Фразы не в коде — только факт «словарь есть/нет».
    """
    forms = period_relative_forms() or {}
    n = len(forms) if isinstance(forms, dict) else 0
    return {"loaded": n > 0, "forms": n}


COVERAGE_SYS = """You answer an employee's question about how complete the company's data
is inside this system. You get a census: for each kind of records, how many rows exist in
the source system and how many reached the search, plus the reason when they differ.

Reply with JSON only, no text outside it:
{"text": "the answer for the user",
 "claims": {"total": number|null, "count": number|null, "max": number|null, "min": number|null}}

- Reply in the SAME language the question was asked in.
- Name the kinds of records that are missing, and say WHY, using the reason given.
- State figures in DIGITS, copied from the census — never recompute, never estimate.
- Put the number of missing rows in "claims.total" and the number of affected kinds of
  records in "claims.count", both only if they appear in your text in digits.
- Say plainly if nothing is missing.
- Be short and businesslike, no preamble."""


# Все НАШИ системные сообщения в одном месте: по ним `prompt_leak` ловит утечку
# инструкции в ответ клиенту точным совпадением строки (`№27`).
OUR_PROMPTS = [INTENT_SYS, AXIS_PICK_SYS, CLARIFY_SYS, REFUSE_SYS, ANSWER_SYS, COVERAGE_SYS]

def _coverage_answer(question, diag, t0):
    """Ответ о полноте данных — из переписи, а не из корпуса (п. 13).

    Числа сюда приходят посчитанными базой и проходят ТОТ ЖЕ гейт, что обычный ответ:
    «сколько данных мы потеряли» — такое же число, как «на какую сумму продано», и
    ошибиться в нём так же нельзя. Отдельного, более мягкого пути для служебных ответов
    нет и быть не должно.
    """
    try:
        tot = psql(
            "SELECT coalesce(sum(в_1С) FILTER (WHERE в_1С > 0), 0),"
            "       coalesce(sum(в_корпусе), 0),"
            "       coalesce(sum(в_1С - в_корпусе) FILTER (WHERE в_1С > в_корпусе), 0),"
            "       count(*) FILTER (WHERE в_1С > 0 AND в_корпусе = 0),"
            "       count(*) FILTER (WHERE в_1С = -1) FROM search_coverage")
        # Поимённо — только то, что ПОТЕРЯНО. Список закрытых правами не перечисляется:
        # их 934, и он рос бы с размером базы, нарушая п. 19. Их число названо, состав
        # доступен запросом.
        lost = psql(
            "SELECT entity, в_1С, в_корпусе, причина FROM search_coverage "
            "WHERE в_1С > 0 AND в_1С > в_корпусе ORDER BY в_1С - в_корпусе DESC LIMIT %d"
            % COVERAGE_TOP)
    except RuntimeError as e:
        sys.stderr.write("ask COVERAGE: перепись недоступна: %s\n" % str(e)[:160])
        return {"partial": None, "kind": "no_data", "sources": [],
                "text": NO_DATA_TEXT or refuse_text(question),
                "diag": _diag_pack(diag, error="перепись недоступна")}
    if not tot:
        return {"partial": None, "kind": "no_data", "sources": [],
                "text": NO_DATA_TEXT or refuse_text(question),
                "diag": _diag_pack(diag, error="перепись пуста — такт ещё не считал полноту")}
    in_1c, in_search, n_lost, ent_lost, ent_denied = (int(_num(x)) for x in tot[0][:5])
    census = ["rows in source system: %d" % in_1c, "rows reached search: %d" % in_search,
              "rows missing: %d" % n_lost, "kinds of records fully missing: %d" % ent_lost,
              "kinds of records closed by permissions in the source system: %d" % ent_denied]
    for r in lost:
        census.append("%s: %s in source, %s in search — %s"
                      % (r[0], r[1], r[2], r[3] if len(r) > 3 else ""))
    raw = ds_chat([{"role": "system", "content": COVERAGE_SYS},
                   {"role": "user",
                    "content": "%s\n\nCensus:\n%s" % (question, "\n".join(census))}])
    text, claims = _split_answer(raw)
    # Гейт: заявленные числа сверяются с переписью. Роли те же, что у обычного
    # ответа, поэтому проверка переиспользуется без послаблений.
    agg = {"sum": float(n_lost), "count": ent_lost}
    ok_roles, bad = check_claims(claims, agg, [])
    diag["claims"] = claims or None
    # 🔴 ЧИСЛОВОЙ ГЕЙТ — И ЗДЕСЬ (`F128`). Докстрока этой функции обещает «тот же гейт,
    # что обычный ответ», но `gate()` тут не звалась ни разу: проверялись только `claims`,
    # а промт велит оставлять их пустыми, то есть не проверялось НИЧЕГО. Любое число,
    # которое модель напишет в ответе о полноте, уходило клиенту без сверки с переписью —
    # при том что «сколько данных потеряно» такое же число, как «на какую сумму продано»
    # (п. 13 и п. 10 контракта). Разрешённое — сама перепись: итоги и строки поимённо.
    allowed = [float(in_1c), float(in_search), float(n_lost), float(ent_lost),
               float(ent_denied)]
    for r in lost:
        for cell in r[1:3]:
            try:
                allowed.append(float(_num(cell)))
            except (TypeError, ValueError):
                pass
    ok_nums, bad_nums = gate(text, [], None, allowed)
    if not ok_nums:
        sys.stderr.write("ask COVERAGE GATE: числа вне переписи: %s\n" % bad_nums[:4])
    leak = prompt_leak(text, OUR_PROMPTS)
    if leak:
        bad_nums, ok_nums = bad_nums + ["утечка инструкции: %s" % leak], False
    ok_roles, bad = (ok_roles and ok_nums), (bad + bad_nums)
    if not ok_roles or not (text or "").strip():
        sys.stderr.write("ask COVERAGE GATE: %s\n" % bad[:4])
        # Числа посчитаны и верны — отдаём их структурой, как и на обычном пути.
        # 🔴 Текст, ОТВЕРГНУТЫЙ гейтом, наружу не идёт: прежде он возвращался полем
        # `text` как есть, то есть проверка срабатывала, а забракованная формулировка
        # всё равно доходила до клиента. Формулирует вызывающий — по числам.
        return {"partial": None, "kind": "figures", "text": "",
                "figures": {"rows_in_1c": in_1c, "rows_in_search": in_search,
                            "rows_missing": n_lost, "entities_missing": ent_lost,
                            "entities_denied": ent_denied},
                "sources": [], "diag": _diag_pack(diag, gate_rejected=bad[:4],
                                            sec=round(time.time() - t0, 2))}
    return {"partial": None, "kind": "answer", "text": text.strip(), "sources": [],
            "figures": {"rows_in_1c": in_1c, "rows_in_search": in_search,
                        "rows_missing": n_lost, "entities_missing": ent_lost,
                        "entities_denied": ent_denied},
            "diag": _diag_pack(diag, sec=round(time.time() - t0, 2), gate_ok=True)}


# Сколько секунд держать в процессе перечень неоднозначных меток: он меняется тактом
# сборки, а не между вопросами. Это бюджет обращений к базе, а не порог правильности.
AMBIG_TTL = int(os.environ.get("ASK_AMBIG_TTL", "300"))

# 🔴 ВИД ЗАПИСИ — ЕДИНСТВЕННОЕ, ЧТО РАЗЛИЧАЕТ ОДНОИМЁННЫЕ ИСТОЧНИКИ. Метка собирается
# срезанием типа (`corpus_build.sql`: `regexp_replace(orig,'^[^_]+_','')`), поэтому
# документ и одноимённый регистр получают ОДНУ строку. Живой прогон okna 13.08: человек
# 23 раза уточнял «продажи за неделю» и не получил числа — в списке стояли два
# неразличимых «Реализация ТМЦ» (документ и регистр накопления), выбор возвращался той
# же строкой, `resolve_focus` честно не сводил её (п. 12) и круг замыкался.
#
# Вид берётся ИЗ ИМЕНИ ТИПА OData, то есть от ПЛАТФОРМЫ, а не от конкретной базы: набор
# типов один у всех конфигураций 1С, поэтому это не привязка (девиз 29.07). Слово для
# человека — перевод платформенного термина, не имя таблицы: `document_реализациятмц`
# наружу по-прежнему не уходит (решение 03.08).
_KIND_WORD = {
    "catalog": "справочник",
    "document": "документ",
    "documentjournal": "журнал документов",
    "accumulationregister": "регистр накопления",
    "informationregister": "регистр сведений",
    "accountingregister": "регистр бухгалтерии",
    "calculationregister": "регистр расчёта",
    "chartofaccounts": "план счетов",
    "chartofcharacteristictypes": "план видов характеристик",
    "chartofcalculationtypes": "план видов расчёта",
    "businessprocess": "бизнес-процесс",
    "task": "задача",
    "exchangeplan": "план обмена",
    "constant": "константа",
    "enum": "перечисление",
}

# OData-префиксы src_table: для экрана заменяются хвостом через human_table_label (K4-3).
_META_SRC_PREFIXES = tuple(k + "_" for k in sorted(_KIND_WORD, key=len, reverse=True))


def looks_like_src_table(s):
    """Строка похожа на служебное имя src_table (тип_хвост)."""
    sl = (s or "").strip().lower()
    if "_" not in sl:
        return False
    return sl.split("_", 1)[0] in _KIND_WORD


def human_table_label(src_table, label=None):
    """Подпись источника словами человека; пустая/служебная метка → хвост после типа."""
    lab = (label or "").strip()
    if lab and not looks_like_src_table(lab):
        return lab
    s = str(src_table or "").strip()
    if not s:
        return ""
    parts = s.split("_", 1)
    if len(parts) == 2 and parts[0].lower() in _KIND_WORD:
        tail = split_ident(parts[1])
        return (tail or kind_word(s) or "источник")
    return split_ident(s) or "источник"


def label_has_meta_src(text):
    """True, если в тексте есть OData-префикс или токен вида тип_хвост."""
    t = (text or "").strip()
    if not t:
        return False
    low = t.lower()
    for p in _META_SRC_PREFIXES:
        if p in low:
            return True
    for tok in re.findall(r"[A-Za-zА-Яа-яЁё0-9_]+", t):
        if looks_like_src_table(tok):
            return True
    return False


def kind_word(src_table):
    """Вид записи словом человека. Неизвестный тип — пустая строка (молча не гадаем)."""
    head = str(src_table or "").split("_", 1)[0].lower()
    return _KIND_WORD.get(head, "")


def label_with_kind(src_table, label):
    """Подпись, различающая одноимённые источники: «Реализация ТМЦ (документ)».

    🔴 ПОДПИСЬ И `focus` — ОДНА СТРОКА. Отдельный «ключ выбора», не совпадающий с тем,
    что видит человек, уже проходили 03.08: бот пересказывает клиенту всё, что видит в
    ответе инструмента, и внутреннее имя утекало в чат мимо зачистки плагина. Поэтому
    различитель кладётся В ТУ ЖЕ строку, которую человек читает и которую бот вернёт
    в `focus`.
    """
    k = kind_word(src_table)
    lab = human_table_label(src_table, label)
    return "%s (%s)" % (lab, k) if k else lab


_AMBIG_CACHE = {"at": 0.0, "set": frozenset()}


def ambiguous_labels():
    """Метки, которые в БАЗЕ носит больше одного источника.

    🔴 Считается по всей карте сущностей, а не по показанному списку. Живой замер okna
    13.08: в вариантах стояла одна «Реализация ТМЦ», подпись выглядела однозначной — а
    `resolve_focus` сводит по базе, где их две (документ и регистр), и выбор человека
    снова отбрасывался. Различитель нужен там, где строка НЕ УНИКАЛЬНА В БАЗЕ, иначе
    круг замыкается на сущности, которой в списке даже не было.

    Ответ живёт в процессе несколько минут: карта сущностей меняется тактом сборки,
    а не между вопросами.
    """
    now = time.time()
    if now - _AMBIG_CACHE["at"] < AMBIG_TTL and _AMBIG_CACHE["set"]:
        return _AMBIG_CACHE["set"]
    try:
        rows = psql("SELECT lower(replace(label,' ','')) FROM %s "
                    "GROUP BY 1 HAVING count(*) > 1" % TABLES)
    except RuntimeError:
        return _AMBIG_CACHE["set"]
    got = frozenset(r[0] for r in rows or [] if r and r[0])
    _AMBIG_CACHE.update({"at": now, "set": got})
    return got


def disambiguate_labels(pairs, ambiguous=None):
    """[(src, label)] -> {src: подпись}. Вид дописывается там, где метка неоднозначна.

    Неоднозначной считается метка, совпавшая внутри списка ИЛИ носимая несколькими
    источниками в базе. Где неоднозначности нет — подпись прежняя, а с ней и прежние
    замеры выбора сущности.
    """
    if ambiguous is None:
        ambiguous = ambiguous_labels()
    norm = lambda s: "".join(str(s or "").lower().split())
    seen = {}
    for src, lab in pairs:
        seen.setdefault(norm(lab), []).append(src)
    out = {}
    for src, lab in pairs:
        many = len(seen.get(norm(lab), [])) > 1 or norm(lab) in ambiguous
        out[src] = label_with_kind(src, lab) if many else human_table_label(src, lab)
    return out


# Пояснение к варианту уточнения: «для чего годится» из словаря синонимов плюс дата
# актуальности данных. Различает варианты не оно, а вид записи (`label_with_kind`) —
# пояснение добавлено сверх него, чтобы человеку было понятно, что он выбирает.
# «Для чего годится» пишет модель один раз при сборке словаря на языке базы, поэтому на
# чужой базе оно появляется само; пока словарь пуст (первые такты новой базы), подпись
# остаётся с одним видом записи, и выбор всё равно однозначен.
# Дата ставится только там, где она РАЗЛИЧАЕТ: одинаковое «по 13.08» у всех вариантов
# строку удлиняет и ничего не разводит. Берётся из корпуса, где её разобрала сборка;
# у справочников даты нет по природе — тогда её просто не показываем.
def opts_hints(srcs):
    """Для каждого источника — короткое пояснение или ничего."""
    srcs = [s for s in srcs if s]
    if len(srcs) < 2:
        return {}
    lst = ", ".join(lit(s) for s in srcs)
    what, when = {}, {}
    try:
        for r in psql("SELECT src_table, best_used_for FROM search_entity_alias "
                      "WHERE src_table IN (%s)" % lst) or []:
            if r and r[0] and len(r) > 1 and (r[1] or "").strip():
                what[r[0]] = r[1].strip()
    except RuntimeError:
        pass
    try:
        for r in psql("SELECT src_table, max(doc_date)::VARCHAR FROM %s WHERE src_table IN (%s) "
                      "AND doc_date IS NOT NULL GROUP BY 1" % (CORPUS, lst)) or []:
            if r and r[0] and len(r) > 1 and (r[1] or "").strip():
                when[r[0]] = r[1].strip()[:10]
    except RuntimeError:
        pass
    if len(set(when.values())) < 2:      # дата одна на всех — не различает
        when = {}
    built, miss = {}, {}
    try:
        for r in psql("SELECT src_table, last_built_at::VARCHAR FROM %s "
                      "WHERE src_table IN (%s) AND last_built_at IS NOT NULL"
                      % (TABLES, lst)) or []:
            if r and r[0] and len(r) > 1 and (r[1] or "").strip():
                built[r[0]] = r[1].strip()[:16]
    except RuntimeError:
        pass
    if len(set(built.values())) < 2:
        built = {}
    try:
        for r in psql("SELECT entity, (в_1С - в_корпусе) FROM search_coverage "
                      "WHERE entity IN (%s) AND в_1С > в_корпусе" % lst) or []:
            if r and r[0] and len(r) > 1:
                try:
                    miss[r[0]] = int(r[1])
                except (TypeError, ValueError):
                    pass
    except RuntimeError:
        pass
    if not miss or len(set(miss.values())) < 2:
        miss = {}
    out = {}
    for s in srcs:
        parts = []
        if what.get(s):
            parts.append(what[s][:90])
        if when.get(s):
            parts.append("данные по %s" % when[s])
        if built.get(s):
            parts.append("в поиске с %s" % built[s])
        if miss.get(s):
            parts.append("не в поиске %s" % miss[s])
        if parts:
            out[s] = "; ".join(parts)
    return out


def mk_opts(srcs, lab_by, marks=None, by=None, match="", preds=None, live=None):
    """Варианты уточнения одним видом на все пять веток ответа.

    Здесь же дописывается вид записи одноимённым источникам: подпись, которую читает
    человек, и значение `focus`, которое возвращает бот, — одна и та же строка, поэтому
    различитель ставится в этой точке, а не в мосте.

    В перечень идёт источник с живым счётом по тем же предикатам, что и ответ
    (период). Если в датированном окне пусты ВСЕ кандидаты — оставляем их:
    вилка прочтений, после выбора отвечает period_empty.
    """
    marks, by = marks or {}, by or {}
    counted = live
    if counted is None and preds is not None:
        counted = live_src_counts(srcs, match, preds)
    if counted is not None:
        srcs = keep_empty_period_opts(srcs, counted, preds)
    cov, _fk = fork_labels_covering(srcs)
    if cov:
        lab_by = dict(lab_by or {})
        for src in srcs:
            if cov.get(src):
                lab_by[src] = cov[src]
    dis = disambiguate_labels([(s, lab_by.get(s) or "") for s in srcs])
    hint = opts_hints(srcs)
    found_of = counted if counted is not None else by
    return [{"src": s, "label": dis.get(s) or human_table_label(s, lab_by.get(s)),
             "hint": hint.get(s, ""),
             "distinct_by": marks.get(s, ""), "found": found_of.get(s, 0)} for s in srcs]


def live_src_counts(srcs, match, preds, pred_by=None, require_nums=False):
    """Живой счёт строк по тем же предикатам, что и ответ. None — база не ответила.

    pred_by: у табличной части — своё условие владельца (как via_parent), match
    не кладётся. require_nums: строки с заполненной картой величин (мера ответа).
    Источник: INDEX если у этой таблицы есть match, иначе CORPUS.
    """
    if not srcs:
        return {}
    pred_by = pred_by or {}
    folder = "NOT coalesce(map_extract_value(flags, 'IsFolder'), false)"
    nums = "nums IS NOT NULL AND len(map_keys(nums)) > 0" if require_nums else ""
    parts = []
    for s in srcs:
        m = "" if s in pred_by else match
        extra = pred_by.get(s)
        where = [w for w in ([m] + list(preds or []) + ([extra] if extra else [])
                             + ["src_table = %s" % lit(s), folder, nums]) if w]
        src = INDEX if m else CORPUS
        parts.append("SELECT %s AS t, count(*) AS n FROM %s WHERE %s"
                     % (lit(s), src, " AND ".join(where)))
    try:
        rows = psql(" UNION ALL ".join(parts))
    except RuntimeError:
        return None
    out = {}
    for r in rows or []:
        try:
            if r and r[0]:
                out[r[0]] = int(r[1])
        except (TypeError, ValueError, IndexError):
            continue
    return out


def empty_after_period_action(intent):
    """Что делать, когда после фильтра rows пуст. Кодом, не промтом.

    Пустое после фильтра не равно «данных нет». Выведенный период не имеет права
    отказать. Названный период с нулём внутри — речь про пустой период, не
    kind=no_data про существование.
    """
    if serene_enough is None:
        return "no_data"
    p = (intent or {}).get("period") or {}
    has_period = bool(p.get("from") or p.get("to"))
    if serene_enough.period_assumed(intent) and has_period:
        return "drop_assumed"
    if serene_enough.period_given(intent):
        return "empty_period"
    return "no_data"


def period_empty_outcome(agg, act, intent=None, diag=None):
    """Нулевой итог в заданном окне — честный ответ, не отказ (план §5, п. 21).

    `empty_period` — период назван в вопросе (`period_given`). «Вчера» и прочие
    относительные окна помечаются `parse.assumed` → `drop_assumed`, но окно
    задано явно: count=0 при outside_period>0 — тот же исход «пусто за период».
    """
    if not agg:
        return False
    try:
        if int(agg.get("count") or 0) != 0:
            return False
    except (TypeError, ValueError):
        return False
    if act == "empty_period":
        return True
    if (diag or {}).get("period_assumed_dropped"):
        return False
    pr = (intent or {}).get("period") or {}
    if not (pr.get("from") or pr.get("to")):
        return False
    try:
        return int(agg.get("outside_period") or 0) > 0
    except (TypeError, ValueError):
        return False


def _period_day_label(pf, pt):
    """ISO YYYY-MM-DD → DD.MM.YYYY; один день — DD.MM.YYYY."""
    def one(iso):
        s = str(iso or "").strip()
        if len(s) < 10 or s[4:5] != "-":
            return s
        y, m, d = s[:10].split("-")
        return "%s.%s.%s" % (d, m, y)

    pf = str(pf or "").strip()
    pt = str(pt or "").strip()
    if pf and pt and pf[:10] == pt[:10]:
        return one(pf)
    if pf and pt:
        return "%s–%s" % (one(pf), one(pt))
    return one(pf or pt)


def dates_outside_period_filter(src, match, preds, intent):
    """Крайние doc_date по тем же условиям, но без фильтра периода."""
    date_preds = set(_predicates(intent))
    kept = [p for p in (preds or []) if p not in date_preds]
    where = [w for w in ([match] + kept + ["src_table = %s" % lit(src),
                        "doc_date IS NOT NULL"]) if w]
    src_tbl = INDEX if match else CORPUS
    try:
        r = psql("SELECT min(doc_date), max(doc_date) FROM %s WHERE %s"
                 % (src_tbl, " AND ".join(where)))
        if r and r[0]:
            return r[0][0], r[0][1]
    except RuntimeError:
        pass
    return None, None


def format_period_empty_text(question, agg, intent, measure, src, money,
                             near_min=None, near_max=None):
    """Текст «пусто за период»: ноль цифрами, outside_period, ближайшие даты."""
    p = (intent or {}).get("period") or {}
    pf = str(p.get("from") or "").strip()
    pt = str(p.get("to") or "").strip()
    window = _period_day_label(pf, pt)
    outside = int(agg.get("outside_period") or 0)
    mlabel = (measure_label_of(src, measure) if (measure and src) else "") or measure
    cyr = any('\u0400' <= c <= '\u04ff' for c in (question or ''))
    parts = []
    if cyr:
        if window:
            parts.append("За %s записей в выбранном периоде нет" % window)
        else:
            parts.append("За выбранный период записей нет")
        if money and measure:
            # 0.00 — ключ digits эталона SUM()::text «0.00» → «000» (AB_PROBE)
            parts.append("итог по «%s» — 0.00" % (mlabel or measure))
        else:
            parts.append("количество — 0")
        if outside:
            parts.append("вне периода в базе %s %s"
                         % (_fmt(outside), kind_word(src) or "записей"))
        if near_min or near_max:
            if near_min and near_max and str(near_min)[:10] == str(near_max)[:10]:
                parts.append("ближайшие данные за %s"
                             % _period_day_label(str(near_min), str(near_min)))
            elif near_min and near_max:
                parts.append("ближайшие данные с %s по %s"
                             % (_period_day_label(str(near_min), str(near_min)),
                                _period_day_label(str(near_max), str(near_max))))
            elif near_max:
                parts.append("ближайшие данные за %s"
                             % _period_day_label(str(near_max), str(near_max)))
    else:
        if window:
            parts.append("No records in the selected period (%s)" % window)
        else:
            parts.append("No records in the selected period")
        if money and measure:
            parts.append("total for «%s» is 0.00" % (mlabel or measure))
        else:
            parts.append("count is 0")
        if outside:
            parts.append("%s records exist outside the period" % _fmt(outside))
        if near_min or near_max:
            parts.append("nearest data: %s .. %s" % (near_min or "—", near_max or "—"))
    return ". ".join(parts) + "."


def build_period_empty_answer(question, agg, intent, measure, src, match, preds,
                              money, slot_mode, cov, cut, diag, grain_dec, axes,
                              n_folders, rows, t0, say_measure):
    """kind=answer при нуле в названном периоде — без compose/гейта."""
    near_min, near_max = dates_outside_period_filter(src, match, preds, intent)
    if near_min and not agg.get("date_min"):
        agg = dict(agg, date_min=near_min, date_max=near_max or near_min)
    text = format_period_empty_text(question, agg, intent, measure, src, money,
                                    near_min, near_max)
    _form = (agg or {}).get("form") or grain_dec.get("form") or "number"
    _grain = (agg or {}).get("grain") or grain_dec.get("grain") or "row"
    _pass_frag, pass_fields = build_answer_passport(
        period=(intent or {}).get("period"),
        period_dropped=bool(diag.get("period_assumed_dropped")),
        origin=_passport_origin(intent, diag),
        src_label=_table_label(src),
        src_kind=kind_word(src) if src else "",
        measure=measure or "",
        grain=_grain,
        axis_label=_passport_axis_label(
            _passport_axis_col(agg, grain_dec), axes) or "",
        form=_form,
        text=text)
    text = ensure_answer_passport(text, _pass_frag)
    _figs = compose_slot_values(agg, measure=measure, folders=n_folders,
                                money=money, slot_mode=slot_mode)
    if money and measure:
        _figs["sum"] = "0.00"
    _figs["count"] = agg.get("count") if agg.get("count") is not None else 0
    _figs.update(pass_fields or {})
    _agg_atom = dict(agg)
    if _agg_atom.get("count") is None:
        _agg_atom["count"] = 0
    _atom = atom_from_agg(
        _agg_atom, operation=atom_operation(
            intent.get("want"), None,
            form=_form, grain=_grain, slot_mode=slot_mode),
        measure_id=(say_measure or measure or None),
        measure_label=measure_label_of(src, say_measure or measure),
        money=money,
        period=(intent or {}).get("period"),
        period_origin=_passport_origin(intent, diag),
        grain=_grain, form=_form,
        axis=_passport_axis_label(
            _passport_axis_col(agg, grain_dec), axes) or None,
        completeness=cov, folders=n_folders, src=src)
    tag = src.split("_", 1)[1] if src and "_" in src else (src or "")
    diag = dict(diag or {})
    diag["period_empty"] = True
    return {"partial": cut or None, "kind": "answer", "text": text,
            "sources": [tag] if tag else [],
            "completeness": cov, "measure": say_measure,
            "figures": _figs, "atom": _atom, "atoms": [_atom],
            "diag": _diag_pack(diag, rows=len(rows or []),
                               sec=round(time.time() - t0, 2), gate_ok=True)}


def _day_ord(iso):
    """YYYY-MM-DD → порядковый день, иначе None. Без календаря языка."""
    try:
        return int(time.mktime(time.strptime(str(iso), "%Y-%m-%d"))) // 86400
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def period_is_canon_guess(period, today):
    """Канон-догадка по форме окна: to ≈ today и (год-от-today или Jan 1..to).

    Не лексика и не parse.assumed. Известная коллизия: честный «~год → сегодня»
    той же формы неотличим — слот для наследования пуст.
    """
    p = period or {}
    fr, to = p.get("from"), p.get("to")
    if not fr or not to:
        return False
    od_fr, od_to, od_today = _day_ord(fr), _day_ord(to), _day_ord(today)
    if od_fr is None or od_to is None or od_today is None:
        return False
    if abs(od_to - od_today) > 1:
        return False
    span = od_to - od_fr
    if 364 <= span <= 367:
        return True
    try:
        _y, m, d = str(fr).split("-", 2)
        if int(m) == 1 and int(d) == 1 and str(fr)[:4] == str(to)[:4]:
            return True
    except (TypeError, ValueError):
        pass
    return False


def period_slot_for_inherit(period, today):
    """Слот периода для наследования: задан текстом (True) или пуст (False).

    Пуст: нет from/to, либо окно — канон-догадка. Иначе задан текстом.
    """
    p = period or {}
    fr, to = p.get("from"), p.get("to")
    if not fr and not to:
        return False
    if fr and to and period_is_canon_guess(p, today):
        return False
    return True


def apply_prior_period(intent, prior_intent, today=None):
    """Слот периода из prior по форме окна, не по parse.assumed. Не want/ось/зерно.

    1) текущий задан текстом → не трогать; 2) текущий пуст и prior задан текстом →
    копировать period и assumed-метки периода; 3) prior пуст/канон-догадка → нет.
    Датчик снятия фильтра (drop_assumed) — отдельно, здесь не меняется.
    """
    if not today:
        today = time.strftime("%Y-%m-%d")
    if period_slot_for_inherit(intent.get("period"), today):
        return False
    prior_p = (prior_intent or {}).get("period") or {}
    if not period_slot_for_inherit(prior_p, today):
        return False
    src = {}
    for k, v in prior_p.items():
        if k in ("from", "to") and v:
            src[k] = v
    if not src:
        return False
    intent["period"] = src
    parse = dict(intent.get("parse") or {})
    rest = [a for a in (parse.get("assumed") or [])
            if not str(a).startswith("period.")]
    prior_assumed = [a for a in ((prior_intent.get("parse") or {}).get("assumed") or [])
                     if str(a).startswith("period.")]
    parse["assumed"] = rest + prior_assumed
    intent["parse"] = parse
    return True


def answer(question, focus=None, measure_pick=None, context="", no_arbiter=False,
            prior=None, trusted=None, resolved=None):
    """Временная заглушка волны B2: тракт answer переписывается в B3+.

    Инфраструктура (gate/health/journal/Handler) уже на месте; логики тракта здесь нет.
    """
    return {
        "kind": "unavailable",
        "text": "тракт переписывается (волна B3)",
        "sources": [],
        "partial": None,
        "options": [],
        "diag": {"onepath_stub": "B2"},
    }


SLOT_COVER = os.environ.get("ASK_SLOT_COVER", "0") == "1"

def _journal_keep_n():
    """N последних строк: count(search_tables) × 6 видов × 2 (вопрос + клик)."""
    global _JOURNAL_KEEP
    env = os.environ.get("ASK_JOURNAL_KEEP")
    if env and str(env).isdigit() and int(env) > 0:
        return int(env)
    if _JOURNAL_KEEP is not None:
        return _JOURNAL_KEEP
    try:
        r = psql("SELECT count(*) FROM %s" % TABLES)
        n = int(r[0][0]) if r and r[0] else 0
        _JOURNAL_KEEP = max(n * 12, 72)
    except (RuntimeError, ValueError, TypeError, IndexError):
        _JOURNAL_KEEP = 72
    return _JOURNAL_KEEP


def _journal_code_md5():
    global _JOURNAL_CODE_MD5
    if _JOURNAL_CODE_MD5 is None:
        h = hashlib.md5()
        with open(ASK_ROOT / "serene_ask.py", "rb") as fh:
            h.update(fh.read())
        _JOURNAL_CODE_MD5 = h.hexdigest()
    return _JOURNAL_CODE_MD5


def _journal_build_ts():
    global _JOURNAL_BUILD_TS, _JOURNAL_BUILD_TS_AT
    now = time.time()
    if _JOURNAL_BUILD_TS is not None and now - _JOURNAL_BUILD_TS_AT < 60:
        return _JOURNAL_BUILD_TS
    try:
        r = psql("SELECT v FROM search_quality WHERE k='build_ts'")
        _JOURNAL_BUILD_TS = str(r[0][0]) if r and r[0] else ""
    except RuntimeError:
        _JOURNAL_BUILD_TS = ""
    _JOURNAL_BUILD_TS_AT = now
    return _JOURNAL_BUILD_TS


def _journal_alias_ver():
    global _JOURNAL_ALIAS_VER
    if _JOURNAL_ALIAS_VER is not None:
        return _JOURNAL_ALIAS_VER
    try:
        r = psql(
            "SELECT concat_ws('|',"
            "(SELECT count(*)::VARCHAR FROM search_entity_alias),"
            "(SELECT count(*)::VARCHAR FROM search_measure_alias),"
            "(SELECT count(*)::VARCHAR FROM search_fork_label))")
        _JOURNAL_ALIAS_VER = (r[0][0] if r and r[0] else "") or ""
    except RuntimeError:
        _JOURNAL_ALIAS_VER = ""
    return _JOURNAL_ALIAS_VER


def _journal_sql_int(v):
    if v is None:
        return "NULL"
    try:
        return str(int(v))
    except (TypeError, ValueError):
        return "NULL"


def _journal_sql_bool(v):
    if v is None:
        return "NULL"
    return "TRUE" if v else "FALSE"


def _journal_atoms_slim(out):
    """Различные атомы ответа или детектора (diag.fork.atoms) — slim JSON."""
    atoms = []
    if not isinstance(out, dict):
        return atoms
    raw = out.get("atoms") or ([out["atom"]] if out.get("atom") else [])
    if not raw:
        # На clarify out.atoms пуст; ветки живут в детекторе (разметка 339 clarify).
        fork = (out.get("diag") or {}).get("fork") or {}
        raw = []
        for item in (fork.get("atoms") or []):
            if not isinstance(item, dict):
                continue
            raw.append(item["atom"] if isinstance(item.get("atom"), dict) else item)
    seen = set()
    for a in raw[:20]:
        if not isinstance(a, dict):
            continue
        slim = {k: a.get(k) for k in (
            "operation", "exact_value", "measure_id", "measure_label",
            "unit", "proof_status") if k in a}
        if not slim:
            continue
        fp = tuple(sorted((k, str(v)) for k, v in slim.items()))
        if fp in seen:
            continue
        seen.add(fp)
        atoms.append(slim)
    return atoms


def _journal_clarify_options(out):
    """Варианты слоя 2 — clarify или B-люк (kind=figures с options).

    B-люк: только не-лидерские варианты; лидер = atoms[0] (порядок [leader]+rest).
    """
    if not isinstance(out, dict):
        return None
    kind = out.get("kind")
    if kind not in ("clarify", "figures"):
        return None
    opts = out.get("options") or []
    if not opts:
        return None
    slim = []
    for o in opts[:40]:
        if not isinstance(o, dict):
            continue
        row = {k: o.get(k) for k in (
            "label", "src", "measure", "hint", "distinct_by", "decision_id")
            if o.get(k) not in (None, "")}
        if row:
            slim.append(row)
    return slim or None


def _journal_doubt(out):
    """Признак сомнения модели из diag (ставится в конвейере)."""
    if not isinstance(out, dict):
        return None
    d = out.get("diag") or {}
    if "doubt" in d:
        return bool(d.get("doubt"))
    if "сомнение" in d:
        return bool(d.get("сомнение"))
    return None


def _journal_ticket_variant(out, trusted=None):
    """Какой вариант погашен билетом (label/src из trusted или diag)."""
    if isinstance(trusted, dict):
        lab = trusted.get("label") or trusted.get("src") or ""
        if lab:
            return str(lab)[:500]
    if not isinstance(out, dict):
        return None
    d = out.get("diag") or {}
    for k in ("ticket_variant", "chosen_label", "focus_forced"):
        v = d.get(k)
        if v not in (None, ""):
            return str(v)[:500]
    return None


def _journal_intent(out):
    d = (out.get("diag") or {}) if isinstance(out, dict) else {}
    return {k: d.get(k) for k in ("kind", "terms", "measure", "want") if d.get(k) not in (None, "", [])}


def _journal_fork_keys(out):
    d = (out.get("diag") or {}) if isinstance(out, dict) else {}
    fork = d.get("fork") or {}
    keys = fork.get("keys") or fork.get("fork_keys") or []
    if not keys and fork.get("classes"):
        keys = list(fork.get("src_set") or [])[:40]
    if isinstance(keys, str):
        return keys
    return json.dumps(keys, ensure_ascii=False)[:2000]


def _journal_uncounted_truncated(out):
    d = (out.get("diag") or {}) if isinstance(out, dict) else {}
    fork = d.get("fork") or {}
    partial = (out.get("partial") or {}) if isinstance(out, dict) else {}
    lim = partial.get("fork_limitation") or {}
    unc = lim.get("uncounted_classes")
    if unc is None:
        unc = len(fork.get("uncounted") or [])
    trn = fork.get("atoms_truncated")
    if trn is None:
        trn = lim.get("truncated") or 0
    try:
        unc = int(unc or 0)
    except (TypeError, ValueError):
        unc = 0
    try:
        trn = int(trn or 0)
    except (TypeError, ValueError):
        trn = 0
    return unc, trn


def _ask_journal_write(question, out, t0, trusted=None, user=None, channel=None,
                       decision_id=None, rid=None):
    """Одна запись журнала. Текст вопроса — в ask_journal_text, не в ask_journal."""
    global _JOURNAL_LOST
    if not ASK_JOURNAL:
        return
    try:
        kind = (out or {}).get("kind") if isinstance(out, dict) else "unavailable"
        if not kind:
            kind = "unavailable"
        d = (out.get("diag") or {}) if isinstance(out, dict) else {}
        tokens = d.get("tokens") or {}
        q = question if isinstance(question, str) else ""
        q_hash = hashlib.sha256(q.encode("utf-8")).hexdigest()
        user_hash = ""
        if user:
            user_hash = hashlib.sha256(str(user).encode("utf-8")).hexdigest()
        ticket_used = bool(trusted) or bool(decision_id and kind != "choice_error")
        ticket_error = ""
        if kind == "choice_error":
            ticket_error = str((out or {}).get("error") or "")
            ticket_used = False
        elif isinstance(d, dict):
            ticket_error = str(d.get("ticket_reissued") or d.get("ticket_error") or "")
            if ticket_error:
                ticket_used = False
        unc, trn = _journal_uncounted_truncated(out if isinstance(out, dict) else {})
        age = d.get("data_age_sec")
        partial = bool((out or {}).get("partial")) if isinstance(out, dict) else False
        fork_out = d.get("fork_outcome") or (d.get("fork") or {}).get("outcome") or ""
        atoms = json.dumps(_journal_atoms_slim(out if isinstance(out, dict) else {}),
                           ensure_ascii=False)
        intent = json.dumps(_journal_intent(out if isinstance(out, dict) else {}),
                            ensure_ascii=False)
        clarify_opts = _journal_clarify_options(out if isinstance(out, dict) else {})
        clarify_json = (json.dumps(clarify_opts, ensure_ascii=False)
                        if clarify_opts is not None else None)
        doubt = _journal_doubt(out if isinstance(out, dict) else {})
        ticket_var = _journal_ticket_variant(
            out if isinstance(out, dict) else {}, trusted=trusted)
        latency = int((time.monotonic() - t0) * 1000) if t0 else 0
        nid = int(psql("SELECT nextval('ask_journal_id_seq')")[0][0])
        jr = _rid_norm(rid or _rid_get())

        def _insert_row(nid):
            sql = (
                "INSERT INTO ask_journal ("
                "id, db_name, channel, user_hash, q_hash, q_len, intent_json, outcome, "
                "fork_outcome, atoms, fork_keys, ticket_used, ticket_error, code_md5, "
                "build_ts, alias_ver, tokens_in, tokens_out, tokens_calls, latency_ms, "
                "partial_flag, freshness_age_sec, uncounted, truncated, discarded_before, "
                "rid, doubt, clarify_options, ticket_variant"
                ") VALUES (%s, current_database(), %s, %s, %s, %s, %s, %s, %s, %s::JSON, "
                "%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
                "%s, %s)"
                % (nid,
                   lit(channel or ""),
                   lit(user_hash),
                   lit(q_hash),
                   int(len(q)),
                   lit(intent),
                   lit(kind),
                   lit(str(fork_out or "")),
                   lit(atoms),
                   lit(_journal_fork_keys(out if isinstance(out, dict) else {})),
                   _journal_sql_bool(ticket_used),
                   lit(ticket_error),
                   lit(_journal_code_md5()),
                   lit(_journal_build_ts()),
                   lit(_journal_alias_ver()),
                   _journal_sql_int(tokens.get("in")),
                   _journal_sql_int(tokens.get("out")),
                   _journal_sql_int(tokens.get("calls")),
                   _journal_sql_int(latency),
                   _journal_sql_bool(partial),
                   _journal_sql_int(age),
                   _journal_sql_int(unc),
                   _journal_sql_int(trn),
                   _journal_sql_int(_JOURNAL_LOST),
                   lit(jr),
                   _journal_sql_bool(doubt) if doubt is not None else "NULL",
                   ("%s::JSON" % lit(clarify_json)) if clarify_json is not None else "NULL",
                   lit(ticket_var) if ticket_var is not None else "NULL"))
            # Не `q in sql`: короткое «q» ложно совпадает с q_hash/q_len.
            if q and (lit(q) in sql or lit(q[:8000]) in sql):
                raise RuntimeError("ask_journal: текст вопроса попал в SQL")
            psql(sql)
            # Текст — best-effort: сбой text не откатывает журнал и ротацию (шаг 5).
            if q:
                try:
                    psql("INSERT INTO ask_journal_text (id, q_text) VALUES (%s, %s)"
                         % (nid, lit(q[:8000])))
                except RuntimeError as te:
                    sys.stderr.write("ask_journal_text LOST: %s\n" % str(te)[:120])

        try:
            _insert_row(nid)
        except RuntimeError as e:
            if "Duplicate key" not in str(e):
                raise
            mx = psql("SELECT coalesce(max(id),0) FROM ask_journal")
            top = int((mx[0][0] if mx and mx[0] else 0) or 0)
            psql("SELECT setval('ask_journal_id_seq', %d)" % top)
            nid = int(psql("SELECT nextval('ask_journal_id_seq')")[0][0])
            _insert_row(nid)
        keep = _journal_keep_n()
        if nid > keep:
            psql("DELETE FROM ask_journal WHERE id <= %d" % (nid - keep))
            try:
                psql("DELETE FROM ask_journal_text WHERE id <= %d" % (nid - keep))
            except RuntimeError:
                pass
    except Exception as e:                          # noqa: BLE001
        _JOURNAL_LOST += 1
        sys.stderr.write("ask journal LOST %d: %s\n" % (_JOURNAL_LOST, str(e)[:160]))


def _answer_checked_core(question, focus=None, measure_pick=None, context="", prior=None,
                         trusted=None, resolved=None):
    """Тело ответа без журнала — все return идут через обёртку answer_checked."""
    _token_acc_start()
    return answer(question, focus=focus, measure_pick=measure_pick, context=context,
                  prior=prior, trusted=trusted, resolved=resolved)

def answer_checked(question, focus=None, measure_pick=None, context="", prior=None,
                   trusted=None, decision_id=None, user=None, channel=None,
                   mem_action=None, rid=None):
    """Точка входа сервиса: билеты decision_id → trusted, затем answer.

    Журнал (шаг 5): одна точка на всех исходах, включая choice_error и unavailable.
    """
    rid = _rid_enter(rid)
    t0 = time.monotonic()
    out = None
    # Без user — анонимный вызов: prior и память сессии не влияют на исход.
    if not user:
        prior = None
    try:
        resolved = peek_resolved(question, user)
        if decision_id and trusted is None:
            ticket, err = consume_decision(decision_id, question, user=user)
            if err:
                batch = lookup_clarify_batch(decision_id, question, user, err)
                recovered = reissue_clarify(batch, err) if batch else None
                if recovered and recovered.get("options"):
                    out = recovered
                    return out
                focus = hold_settled_entity(
                    focus, None, resolved, found_by=None,
                    measure_pick=measure_pick)
                out = _answer_checked_core(
                    question, focus=focus, measure_pick=measure_pick,
                    context=context, prior=prior, trusted=None,
                    resolved=resolved)
                if isinstance(out, dict):
                    diag = dict(out.get("diag") or {})
                    diag["ticket_reissued"] = err
                    diag["ticket_fallback"] = "general"
                    out = dict(out, diag=diag)
                return out
            if ticket.get("src"):
                focus = ticket["src"]
            if ticket.get("ambiguity") == "measure" and "measure" in ticket:
                measure_pick = ticket.get("measure") or None
            if ticket.get("ambiguity") == "axis" and ticket.get("axis"):
                focus = ticket.get("src") or focus
            if ticket.get("ambiguity") == "period" and ticket.get("period") is not None:
                resolved = dict(resolved or {})
                resolved["period"] = dict(ticket.get("period") or {})
            trusted = ticket
            accumulate_resolution(question, user, ticket)
            resolved = peek_resolved(question, user)
        if resolved.get("src") and not focus:
            focus = resolved["src"]
        if "measure" in resolved and measure_pick is None:
            mp = resolved.get("measure")
            measure_pick = mp if mp not in (None, "") else measure_pick
        _pin = hold_settled_entity(
            focus, trusted, resolved, found_by=None,
            measure_pick=measure_pick)
        if _pin != focus:
            focus = _pin
        out = _answer_checked_core(question, focus=focus, measure_pick=measure_pick,
                                   context=context, prior=prior, trusted=trusted,
                                   resolved=resolved)
        if isinstance(out, dict) and isinstance(trusted, dict):
            _tv = trusted.get("label") or trusted.get("src")
            if _tv:
                _d = dict(out.get("diag") or {})
                _d.setdefault("ticket_variant", _tv)
                out = dict(out, diag=_d)
        return out
    except Exception:
        out = {"kind": "unavailable", "text": "", "sources": [], "retry": True, "partial": None}
        raise
    finally:
        # П. 13: обрезанное/непосчитанное видно КЛИЕНТУ, а не только в diag.
        # Единая пост-обработка (docs/COMPLETENESS_P13.md §11.1, дыры 1-4).
        if isinstance(out, dict):
            PV.ensure_partial_visible(out)
        _ask_journal_write(question, out, t0, trusted=trusted, user=user,
                           channel=channel, decision_id=decision_id, rid=rid)
        # Часы rid: снять старт, чтобы _REQ_T0 не тёк между запросами.
        _req_t0_clear(rid)


def _build_ask_scope(out, question):
    """Извлечь спецификацию счёта из diag и вернуть dict для панели дашборда."""
    if not isinstance(out, dict):
        return None
    kind = out.get('kind', '')
    if kind not in ('answer', 'figures'):
        return None
    d = (out.get('diag') or {}).get('счёт')
    if not d or not d.get('src'):
        return None
    src_base = d.get('src')
    where = (d.get('where') or '').strip()
    folder_pred = (d.get('folder_pred') or '').strip()
    if folder_pred:
        where = (where + " AND " if where else "") + folder_pred

    measure_key = (d.get('величина') or '').strip()
    if not measure_key:
        return None

    axis_key = (d.get('ось') or '').strip() or None

    measure_col = "__ask_value"
    axis_col = "__ask_axis"
    select_parts = [
        "*",
        "map_extract(nums, %s)[1] AS %s" % (lit(measure_key), measure_col),
    ]
    if axis_key:
        select_parts.append(
            "map_extract_value(refs_map, %s) AS %s" % (lit(axis_key), axis_col)
        )

    src = "(SELECT %s FROM %s)" % (", ".join(select_parts), src_base)
    return {
        'src': src,
        'where': where,
        'measure': measure_col,
        'axis': axis_col if axis_key else None,
        'period_col': 'doc_date',
        'title': (question or '')[:120].strip() or 'panel',
    }


def _persist_ask_scope(out, question):
    """Сохранить ask_scope в ответе и в таблице ask_scope (для кнопки дашборда)."""
    scope = _build_ask_scope(out, question)
    if not scope:
        return
    text = (out.get('text') or '').strip()
    if not text:
        return
    import hashlib
    h = hashlib.sha256(text.encode('utf-8')).hexdigest()
    out['ask_scope'] = scope
    out['ask_scope_sha256'] = h
    spec_json = json.dumps(scope, ensure_ascii=False, separators=(',', ':'))
    try:
        _resolver_psql("INSERT INTO ask_scope (answer_sha256, spec, created_at) "
                       "VALUES (%s, %s, now()) "
                       "ON CONFLICT (answer_sha256) DO UPDATE SET spec = EXCLUDED.spec, "
                       "created_at = EXCLUDED.created_at" % (lit(h), lit(spec_json)))
    except Exception:
        pass


def _ensure_ask_scope_table():
    """Создать таблицу ask_scope если не существует (при старте сервиса)."""
    if not RESOLVER_DSN:
        return
    try:
        _resolver_psql("CREATE TABLE IF NOT EXISTS ask_scope ("
                       "answer_sha256 VARCHAR PRIMARY KEY, "
                       "spec VARCHAR NOT NULL, "
                       "created_at TIMESTAMP NOT NULL DEFAULT now())")
        _resolver_psql("GRANT SELECT ON ask_scope TO serene_ro")
    except Exception:
        sys.stderr.write('WARN: ask_scope table creation failed (non-fatal)\n')


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        sys.stderr.write("ask %s - %s\n" % (self.address_string(), fmt % args))

    def _send(self, code, obj):
        b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path.rstrip("/") == "/health":
            try:
                n = psql("SELECT count(*) FROM %s" % CORPUS)[0][0]
            except Exception as e:                      # noqa: BLE001
                return self._send(503, {"status": "degraded", "error": str(e)[:200]})
            # Известный разрыв полноты — дверь НЕ зелёная (аудит §3, п. 13/18).
            # Формат ответа прежний (status + corpus_rows), поля добавляются: вызывающий
            # (`1c-bot-monitor`) читает только HTTP-код, а разбор разрыва видит человек.
            try:
                gap = _health_gap()
            except Exception as e:                      # noqa: BLE001 — дверь «не знает»,
                return self._send(503, {"status": "degraded",  # а незнание ≠ зелёный
                                        "corpus_rows": int(n),
                                        "coverage_gap": "unknown",
                                        "error": str(e)[:200]})
            gap = _classify_health_gap(gap)
            # Словарь относительных окон: пустой = нехватка слоя (п. 13), видна в /health.
            try:
                prf = _health_period_relative_forms()
            except Exception as e:                      # noqa: BLE001
                prf = {"loaded": False, "forms": 0, "error": str(e)[:200]}
            # Ф6.4: при флаге — штатные sdb_metrics рядом с эвристикой; VACUUM не зовём.
            native = native_err = None
            if ASK_HEALTH_NATIVE_FRESHNESS:
                try:
                    native = _measure_native_index_freshness()
                except Exception as e:                      # noqa: BLE001
                    native_err = str(e)[:200]
            try:
                tick = _measure_tick_status()
            except Exception as e:                      # noqa: BLE001
                tick = {"known": False, "error": str(e)[:200]}
            if gap and gap.get("kind") == "systemic":
                body = {"status": "degraded", "corpus_rows": int(n),
                        "coverage_gap": gap,
                        "period_relative_forms": prf,
                        "tick": tick}
                if ASK_HEALTH_NATIVE_FRESHNESS:
                    body["freshness"] = _attach_native_freshness(
                        {}, native, native_err)
                return self._send(503, body)
            if not prf.get("loaded"):
                body = {"status": "degraded", "corpus_rows": int(n),
                        "coverage_gap": gap or {"entities": 0,
                                                "rows_missing": 0,
                                                "kind": "none"},
                        "period_relative_forms": prf,
                        "tick": tick}
                if ASK_HEALTH_NATIVE_FRESHNESS:
                    body["freshness"] = _attach_native_freshness(
                        {}, native, native_err)
                return self._send(503, body)
            if gap and gap.get("kind") == "freshness_lag":
                freshness = {"merge_pending_sec": gap.get("merge_pending_sec")}
                if ASK_HEALTH_NATIVE_FRESHNESS:
                    freshness = _attach_native_freshness(
                        freshness, native, native_err)
                return self._send(200, {"status": "serene-ask-ok",
                                        "corpus_rows": int(n),
                                        "coverage_gap": gap,
                                        "period_relative_forms": prf,
                                        "freshness": freshness,
                                        "tick": tick})
            body = {"status": "serene-ask-ok", "corpus_rows": int(n),
                    "coverage_gap": gap or {"entities": 0,
                                            "rows_missing": 0,
                                            "kind": "none"},
                    "period_relative_forms": prf,
                    "tick": tick}
            if ASK_HEALTH_NATIVE_FRESHNESS:
                body["freshness"] = _attach_native_freshness(
                    {}, native, native_err)
            return self._send(200, body)
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path.rstrip("/") != "/ask":
            return self._send(404, {"error": "not found"})
        # Fail-closed: без токена сервис не стартует (см. main), поэтому здесь
        # проверка безусловная. Раньше пустая переменная окружения молча открывала
        # доступ — та же дыра, что была у OData-шлюза.
        if self.headers.get("Authorization", "") != "Bearer " + ASK_TOKEN:
            return self._send(401, {"error": "unauthorized"})
        try:
            n = int(self.headers.get("Content-Length", "0"))
            req = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return self._send(400, {"error": "bad json"})
        raw_q = (req.get("question") or "").strip()
        mem_explicit = (req.get("memory") or "").strip().lower() or None
        mem_action, question = ACM.split_memory_action(raw_q, mem_explicit)
        if not question and not mem_action:
            return self._send(400, {"error": "empty question"})
        if not question and mem_action:
            question = raw_q
        # `focus` — подсказка отбора (модель/свободный текст). Доказанный выбор —
        # только `decision_id` (план §6); сырой focus защиты не гасит.
        focus = (req.get("focus") or "").strip() or None
        # Выбор величины текстом — подсказка; билет меры тоже через decision_id.
        measure_pick = (req.get("measure") or "").strip() or None
        # Предыдущий разговор ведёт OpenClaw; сюда он приходит строкой и
        # используется ТОЛЬКО арбитром. В отбор данных не попадает.
        context = (req.get("context") or "")[:4000]
        # `prior` — канал одного вызова (хук замка), не память сессии.
        prior = (req.get("prior") or "").strip() or None
        decision_id = (req.get("decision_id") or "").strip() or None
        user = (req.get("user") or "").strip() or None
        channel = (req.get("channel") or "http").strip() or "http"
        rid = (req.get("rid") or "").strip() or None
        try:
            # Команда «запомни»/«забудь» без вопроса данных: не гоняем разбор,
            # клик сам по себе память не пишет (нужен mem_action).
            data_q = ACM.split_memory_action(raw_q, mem_explicit)[1]
            if mem_action and not data_q:
                out = {"kind": "answer", "text": "", "sources": [],
                       "partial": None, "diag": {}, "options": []}
                out = attach_memory_shadow(out, user=user, action=mem_action,
                                           decision_id=decision_id)
            else:
                question = data_q or question
                # `answer_checked`, а не `answer`: вокруг ответа стоит шаг «достаточен ли
                # вопрос» (05.08). Он же зовёт `answer` внутри, поэтому путь ответа прежний.
                # decision_id потребляется там же — иначе choice_error минует журнал.
                out = answer_checked(question, focus=focus, measure_pick=measure_pick,
                                     context=context, prior=prior,
                                     decision_id=decision_id, user=user, channel=channel,
                                     mem_action=mem_action, rid=rid)
                # Фаза «не рвать»: билеты только после успешного clarify-return;
                # AskDeadline до seal_clarify → билетов нет. Journal — в finally.
                if isinstance(out, dict) and out.get("options"):
                    out = seal_clarify(out, question, user=user)
                out = attach_memory_shadow(out, user=user, action=mem_action,
                                           decision_id=decision_id)
            # СВЕЖЕСТЬ ДАННЫХ — В КАЖДЫЙ ОТВЕТ (п. 18). Если 1С недоступна или такт падает,
            # корпус остаётся консистентным (защиты сборки), но СТАРЕЕТ, а бот об этом
            # молчал бы. Возраст последнего успешного такта делает старение видимым, а при
            # сильном отставании (сверх `ASK_STALE_WARN_SEC`, вдвое больше цикла и выше) —
            # явная приписка к ответу. Один дешёвый запрос, не на каждую ветку `answer`.
            try:
                r = psql("SELECT round(epoch(now()) - v) FROM search_quality WHERE k='build_ts'")
                age = int(_num(r[0][0])) if r and r[0] else None
            except RuntimeError:
                age = None
            if age is not None and isinstance(out, dict):
                out.setdefault("diag", {})["data_age_sec"] = age
                # Команда запомни/забудь без вопроса данных — не приписка свежести:
                # это не ответ по данным, и пустой text не получает оговорки.
                if not (mem_action and not data_q):
                    out = stale_note(out, age, STALE_WARN_SEC, STALE_TEXT)
            _persist_ask_scope(out, question)
            return self._send(200, out)
        except AskDeadline:
            # Бюджет ASK_DEADLINE_SEC истёк: честный unavailable из ask (не текст моста).
            # Готовое меню досюда не доходит — seal_clarify не звался; memo/билеты не пишем.
            return self._send(503, {
                "kind": "unavailable",
                "text": ("Отвечаю дольше обычного — вопрос слишком широкий или система "
                         "занята. Повторите вопрос или сузьте его (например, один вид "
                         "продаж и период)."),
                "sources": [],
                "retry": True,
                "diag": {"deadline_aborted": 1},
            })
        except Exception as e:                          # noqa: BLE001
            # 🔴 ЧЕСТНЫЙ ОТКАЗ ПРИ СБОЕ (п. 18), А НЕ ВЫДУМАННЫЙ ОТВЕТ. Любое исключение
            # по дороге (модель молчит, база/движок недоступны, эмбеддер не отвечает)
            # доходит СЮДА, а не превращается в ответ по частичным данным: `answer`
            # либо возвращает результат целиком, либо падает. Пользователю — понятное
            # сообщение по типу сбоя, БЕЗ внутренностей (`psql`, стек): их видит только
            # журнал. Класс сбоя определяем по тексту исключения, без утечки деталей.
            txt = str(e)
            sys.stderr.write("ask ERROR: %r\n" % (e,))
            low = txt.lower()
            if any(w in low for w in ("psql", "connection to server", "port", "postgres")):
                msg = "База данных временно недоступна. Повторите запрос через минуту."
            elif any(w in low for w in ("urlopen", "http", "timed out", "connection refused")):
                msg = "Языковая модель сейчас не отвечает. Повторите запрос через минуту."
            else:
                msg = "Сервис временно недоступен. Повторите запрос через минуту."
            return self._send(503, {"kind": "unavailable", "text": msg, "sources": [],
                                    "retry": True})


def main():
    if not ASK_TOKEN:
        sys.stderr.write("FATAL: ASK_TOKEN не задан — сервис без авторизации отдавал бы "
                         "данные витрины кому угодно. Задайте токен в окружении.\n")
        return 2
    srv = ThreadingHTTPServer((LISTEN_HOST, LISTEN_PORT), Handler)
    sys.stderr.write("serene-ask на http://%s:%d  (поиск в SereneDB, схема в модель не уходит)\n"
                     % (LISTEN_HOST, LISTEN_PORT))
    srv.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)

register_zone('ask.z20_ask_main_http', globals())

