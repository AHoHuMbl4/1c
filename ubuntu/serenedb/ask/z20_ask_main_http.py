"""Zone 20: ask / HTTP (ask-main-http)."""
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
    """Каждое число ответа обязано встречаться в данных, в итоге или в наших условиях.

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

    # Даты: названная дата обязана совпасть с датой из данных ПОКОМПОНЕНТНО.
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
        # 20.5 — то есть верное число, стоящее в данных, не заземлялось НИКОГДА, а
        # ответ отвергался целиком `[замер 02.08, test_gate.py]`. Ровно тот класс, что
        # п. 21 называет дефектом проверки.
        if not ok and y is None:
            ok = bool(_date2_readings(answer, d, mo) & allowed)
        if not ok:
            bad.append("%02d.%02d%s" % (d, mo, "" if y is None else ".%d" % y))
    return (not bad), bad


def count_figures(agg):
    """Числа ответа, когда величина не названа: счёт и — если было — отброшенное.

    🔴 `folders` уходит наружу вместе со счётом (`F249`). «Сколько записей» при
    отброшенных папках справочника — это ДВА числа, а не одно, и молчаливая потеря
    второго считается дефектом (п. 13). Прежде отброшенное держалось только прозой
    модели: не назвала — гейт отказывал в ответе целиком, и `[замер 04.08]` на живом
    вопросе «сколько всего контрагентов» это давало клиенту «проверенный ответ
    невозможен» при посчитанных 12 записях и 1 папке. Теперь число уходит полем, то
    есть доезжает и тогда, когда формулировка не сошлась.
    """
    out = {"count": (agg or {}).get("count")}
    if (agg or {}).get("folders"):
        out["folders"] = agg["folders"]
    return out


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
    stripped = [dict(o, hint="") for o in (opts or [])]
    return "\n".join(format_clarify_options(question, stripped))


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
    важно не общее число, а то, полны ли продажи. Отметка обязана быть про его вопрос,
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
OUR_PROMPTS = [INTENT_SYS, PICK_SYS, AXIS_PICK_SYS, CLARIFY_SYS, REFUSE_SYS, ANSWER_SYS, COVERAGE_SYS]

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
    # Гейт: заявленные числа обязаны совпасть с переписью. Роли те же, что у обычного
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


# ----------------------------------------------------------------- HTTP
# Опыт 30.07: нужно ли считать расхождение слабого сигнала (вектор вопроса) с выбором
# модели признаком неоднозначности. Решается замером, а не рассуждением.
SIGNAL_DISAGREE = os.environ.get("ASK_SIGNAL_DISAGREE", "1") == "1"
# Требовать подтверждения выбора сущности; иначе спрашивать человека.
REQUIRE_SUPPORT = os.environ.get("ASK_REQUIRE_SUPPORT", "1") == "1"
# Сколько готовых ответов отдавать арбитру. Больше двух-трёх не нужно: это
# столько же полных ответов, сколько кандидатов, и время ответа растёт.
ARBITER_MAX = int(os.environ.get("ASK_ARBITER_MAX", "3"))
# Бюджет пар исхода B — тот же порядок, что у круга арбитра ×4 (план §2, п. 13).
FORK_PAIR_MAX = max(ARBITER_MAX * 4, 16)
# Арбитр работает ДЕТЕКТОРОМ: разошлись посчитанные числа кандидатов — спрашиваем человека,
# а не даём модели выбрать между ними (задача 17). Выключатель нужен, чтобы прежнее
# поведение можно было вернуть одним значением, если приёмка покажет обратное.
ARBITER_DETECTS = os.environ.get("ASK_ARBITER_DETECTS", "1") == "1"
# Отсев кандидатов по знанию установки «на что НЕ отвечает» (`not_for_excludes`).
NOT_FOR = os.environ.get("ASK_NOT_FOR", "1") == "1"
# Словарь со стеммингом — им сравниваются слово человека и название сущности.
# Создаётся сборкой (`corpus_init.sql`), локаль наследует от основного словаря.
STEM_DICT = os.environ.get("ASK_STEM_DICT", "search_dict_stem")
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




def sales_period_empty(agg, act, intent, diag, question):
    """Нулевые продажи в названном окне — period_empty, даже если outside_period не посчитан."""
    if period_empty_outcome(agg, act, intent, diag):
        return True
    if not sales_sum_intent(intent, question):
        return False
    try:
        if int((agg or {}).get("count") or 0) != 0:
            return False
    except (TypeError, ValueError):
        return False
    if act in ("empty_period", "drop_assumed"):
        return bool(sales_canon_engaged(diag))
    if sales_canon_engaged(diag):
        return sales_period_window_active(intent, diag)
    return False


def sales_period_window_active(intent, diag=None, preds=None):
    """Окно периода задано: явно, assumed (parse/diag) или preds doc_date."""
    pr = (intent or {}).get("period") or {}
    if pr.get("from") or pr.get("to"):
        return True
    if empty_after_period_action(intent) in ("empty_period", "drop_assumed"):
        return True
    if preds and any("doc_date" in str(p) for p in (preds or [])):
        return True
    if "period." in str((diag or {}).get("intent_assumed") or ""):
        return True
    assumed = ((intent or {}).get("parse") or {}).get("assumed") or []
    return any(str(a).startswith("period.") for a in assumed)


def sales_fork_canon_empty_src(intent, diag, question, fork_diag, cands=None):
    """Канон продаж в fork excluded (no_live_cells) = нулевые продажи за период.

    Живой путь [замер 22.08 okna]: «почему… продаж ноль» — picked=[], fork pool=2,
    регистр реализации excluded, курсы валют live → clarify вместо period_empty.
    """
    if not sales_sum_intent(intent, question):
        return None
    if rank_intent_from(intent, question=question):
        return None
    if not sales_period_window_active(intent, diag):
        return None
    canon = sales_canon_engaged(diag) or sales_canon_src(list(cands or []),
                                                           intent, question)
    if not canon:
        return None
    fd = fork_diag or {}
    for item in (fd.get("excluded") or []):
        if isinstance(item, dict) and item.get("src") == canon:
            if item.get("reason") == "no_live_cells":
                return canon
    pool = fd.get("pool_srcs") or []
    live = set(fd.get("live_srcs") or [])
    if canon in pool and canon not in live:
        return canon
    return None


def try_sales_fork_period_empty_answer(question, intent, diag, cut, t0, cands,
                                       fork_diag):
    """Ответ 0.00 по канону продаж, если fork исключил его как no_live_cells."""
    canon = sales_fork_canon_empty_src(intent, diag, question, fork_diag, cands)
    if not canon and diag.get("period_window_empty"):
        _locked = sales_canon_engaged(diag) or diag.get("sales_canon_locked")
        if _locked and sales_period_window_active(intent, diag):
            canon = _locked
    if not canon:
        return None
    if not sales_canon_engaged(diag):
        diag["sales_canon_locked"] = canon
    agg = {"count": 0, "sum": 0.0, "grain": "row", "form": "number"}
    measure = None
    try:
        _mn = measures_of(canon)
        if sales_force_money_measure(intent, question):
            measure = sales_money_measure(_mn)
    except RuntimeError:
        pass
    money = answer_money(intent.get("want"), "sum", measure)
    diag["sales_fork_period_empty"] = canon
    return build_period_empty_answer(
        question, agg, intent, measure, canon, "", [], money, "sum",
        None, cut, diag, {"grain": "row", "form": "number"}, [], 0, [], t0,
        measure if money else None)


def sales_fork_blocks_clarify(outcome, payload, intent, diag, question, cands,
                              fork_diag):
    """Fork C/empty/unique по постороннему src — не вместо period_empty канона."""
    canon = sales_fork_canon_empty_src(intent, diag, question, fork_diag, cands)
    if not canon:
        return False
    if outcome in ("C", "empty"):
        return True
    if outcome == "unique":
        u_srcs = set((payload.get("class") or {}).get("srcs") or [])
        return bool(u_srcs) and canon not in u_srcs
    return False


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
    if agg.get("count") is not None:
        _figs["count"] = agg["count"]
    _figs.update(pass_fields or {})
    _atom = atom_from_agg(
        agg, operation=atom_operation(
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


def drop_period_preds(intent, preds):
    """Снять датные предикаты. Возвращает (intent без period, preds без дат)."""
    date_preds = set(_predicates(intent))
    new_preds = [p for p in preds if p not in date_preds]
    new_intent = dict(intent)
    new_intent["period"] = {}
    return new_intent, new_preds


def _term_stems(intent):
    """Основы слов из terms — для сопоставления с именем сущности."""
    stems = set()
    try:
        for g in (intent or {}).get("terms") or []:
            for alt in g or []:
                if not alt:
                    continue
                kr = psql("SELECT ts_lexize(%s, %s)" % (lit(STEM_DICT), lit(str(alt))))
                stems |= {s for s in _stem_set(kr[0][0] if kr else "") if len(s) >= 3}
                tail = str(alt).split("_", 1)[-1] if "_" in str(alt) else str(alt)
                kr2 = psql("SELECT ts_lexize(%s, %s)" % (lit(STEM_DICT), lit(tail)))
                stems |= {s for s in _stem_set(kr2[0][0] if kr2 else "") if len(s) >= 3}
    except RuntimeError:
        pass
    return stems


def _src_covers_term_stems(src, term_stems):
    if not src or not term_stems:
        return False
    parts = set()
    try:
        r = psql("SELECT label FROM %s WHERE src_table = %s LIMIT 1" % (TABLES, lit(src)))
        lab = (r[0][0] if r and r[0] else "") or src
        for chunk in (lab, _src_tag(src) or src):
            kr = psql("SELECT ts_lexize(%s, %s)" % (lit(STEM_DICT), lit(chunk)))
            parts |= {s for s in _stem_set(kr[0][0] if kr else "") if len(s) >= 3}
    except RuntimeError:
        return False
    return term_stems <= parts


def align_picked_to_terms(picked, cands, intent, diag):
    """B8-06: picked, не покрывающий stems terms, заменяется единственным cand, который покрывает."""
    if not picked or len(picked) != 1:
        return picked
    term_stems = _term_stems(intent)
    if not term_stems:
        return picked
    pool = list(dict.fromkeys(list(cands or []) + list(picked)))
    fits = [c for c in pool if _src_covers_term_stems(c, term_stems)]
    if not fits and term_stems:
        try:
            core = sorted(term_stems, key=len, reverse=True)[0]
            pat = "%%" + core + "%%"
            extra = [r[0] for r in psql(
                "SELECT src_table FROM %s WHERE lower(replace(label, ' ', '')) LIKE %s "
                "OR lower(src_table) LIKE %s LIMIT 12"
                % (TABLES, lit(pat), lit(pat))) if r and r[0]]
            pool = list(dict.fromkeys(pool + extra))
            fits = [c for c in pool if _src_covers_term_stems(c, term_stems)]
        except RuntimeError:
            pass
    if picked[0] in fits and _src_covers_term_stems(picked[0], term_stems):
        return picked
    if len(fits) == 1 and fits[0] != picked[0]:
        if diag is not None:
            diag["aligned_to_terms"] = {"was": picked[0], "became": fits[0]}
        return [fits[0]]
    return picked


def resolve_focus(focus, diag=None, opts=None):
    """Свести `focus` к ИМЕНИ ИСТОЧНИКА, как бы его ни назвали.

    🔴 ЗАЧЕМ. `focus` приходит от бота, а бот берёт название оттуда, где его увидел —
    и это **разные пространства имён**. Уточнение сервиса даёт внутреннее имя
    (`catalog_классификаторбанков`), а страница вики — человеческий заголовок
    («Классификатор Банков»). [замер 02.08] как только смысловой поиск по вики заработал,
    бот стал передавать заголовок, сервис его не узнавал и отвечал «нет данных» — при том
    что тот же вопрос без `focus` отвечался верно (37 банков). Отказ при наличии данных —
    дефект (п. 21), и чинится он здесь, а не просьбой к модели «передавай правильное имя»:
    правило на промте не работает.

    Сведение спрашивается У БАЗЫ (имя и метка лежат в `search_tables`), а не собирается
    разбором строки: разбор был бы догадкой и привязкой к языку (п. 9).

    Не свелось — возвращаем None, и вызывающий идёт обычным путём выбора сущности. Это
    лучше отказа: человек назвал что-то, чего мы не узнали, но данные могут быть.
    """
    if not focus:
        return None
    f = str(focus).strip()
    if not f:
        return None
    # Номер варианта из только что показанного уточнения — тот же порядок, что mk_opts.
    if opts:
        raw = f.rstrip(".)").strip()
        if raw.isdigit():
            n = int(raw)
            if 1 <= n <= len(opts):
                o = opts[n - 1] or {}
                src = (o.get("src") or "").strip()
                if src:
                    if diag is not None:
                        diag["focus_resolved"] = "%s -> %s" % (f, src)
                    return src
                lab = (o.get("label") or o.get("measure") or "").strip()
                if lab:
                    return resolve_focus(lab, diag, opts=None)
    try:
        rows = psql("SELECT src_table FROM %s WHERE src_table = %s LIMIT 1" % (TABLES, lit(f)))
        if rows and rows[0] and rows[0][0]:
            return rows[0][0]
        # По человеческому названию: регистр и пробелы не считаем — «Классификатор Банков»,
        # «классификатор банков» и «КлассификаторБанков» это одно и то же.
        rows = psql("SELECT src_table FROM %s WHERE lower(replace(label,' ','')) = "
                    "lower(replace(%s,' ','')) LIMIT 2" % (TABLES, lit(f)))
        if len(rows) == 1 and rows[0] and rows[0][0]:
            if diag is not None:
                diag["focus_resolved"] = "%s -> %s" % (f, rows[0][0])
            return rows[0][0]
        if len(rows) > 1:
            # Название неоднозначно — навязывать одно из двух нельзя (п. 12).
            if diag is not None:
                diag["focus_ambiguous"] = f
            return None
        # Подпись с видом записи: «Реализация ТМЦ (документ)». Сравниваем не разбором
        # строки, а СБОРКОЙ эталона у каждого кандидата — так же, как сведение по метке
        # спрашивается у базы. Кандидаты сужаются LIKE (доки: Sql › Functions › Text
        # Functions — string LIKE target), поэтому перебора всей карты сущностей нет.
        # Формы: точное равенство, начало подписи, подпись внутри строки-вопроса (чип).
        norm = lambda s: "".join(str(s or "").lower().split())
        nf = norm(f)
        try:
            rows = psql("SELECT src_table, label FROM %s WHERE %s LIKE "
                        "lower(replace(label,' ','')) || '%%' OR "
                        "lower(replace(label,' ','')) LIKE %s || '%%'"
                        % (TABLES, lit(nf), lit(nf)))
        except RuntimeError:
            rows = []
        hits = []
        for r in rows or []:
            if not (r and r[0]):
                continue
            src = r[0]
            lab = r[1] if len(r) > 1 else ""
            full = norm(label_with_kind(src, lab))
            nlab = norm(lab)
            if nf in (full, nlab):
                hits.append((src, 4, len(full)))
            elif (len(nf) >= 8 or "(" in f) and full.startswith(nf):
                hits.append((src, 3, len(full)))
            elif full and full in nf:
                hits.append((src, 2, len(full)))
            elif (len(nf) >= 8 or "(" in f) and nlab.startswith(nf):
                hits.append((src, 1, len(full)))
        if hits:
            hits.sort(key=lambda x: (x[1], x[2]), reverse=True)
            best = hits[0][1]
            srcs = []
            for src, rank, _ln in hits:
                if rank != best:
                    break
                if src not in srcs:
                    srcs.append(src)
            if len(srcs) == 1:
                if diag is not None:
                    diag["focus_resolved"] = "%s -> %s" % (f, srcs[0])
                return srcs[0]
            if len(srcs) > 1:
                if diag is not None:
                    diag["focus_ambiguous"] = f
                return None
        try:
            frows = psql(
                "SELECT src, label FROM search_fork_label "
                "WHERE coalesce(label,'') <> '' AND ("
                "lower(replace(label,' ','')) = %s OR "
                "lower(replace(label,' ','')) LIKE %s || '%%' OR "
                "%s LIKE '%%' || lower(replace(label,' ','')) || '%%')"
                % (lit(nf), lit(nf), lit(nf)))
        except RuntimeError:
            frows = []
        fhits = []
        for r in frows or []:
            if not (r and r[0] and r[1]):
                continue
            nlab = norm(r[1])
            if not nlab:
                continue
            if nf == nlab or ((len(nf) >= 8 or "(" in f) and nlab.startswith(nf)) or nlab in nf:
                fhits.append(r[0])
        fsrcs = list(dict.fromkeys(fhits))
        if len(fsrcs) == 1:
            if diag is not None:
                diag["focus_resolved"] = "%s -> %s" % (f, fsrcs[0])
            return fsrcs[0]
        if len(fsrcs) > 1:
            if diag is not None:
                diag["focus_ambiguous"] = f
            return None
    except RuntimeError:
        return None                     # база недоступна — пусть решает общий путь
    if diag is not None:
        diag["focus_unknown"] = f
    return None



def _word_hits_measure(names, word):
    """Слово меры совпало с полем nums. 'single' без совпадения — не попадание."""
    if not word or not names:
        return False
    _m, _alts, how = measure_choice(names, word)
    if how in ("exact", "substring", "alias", "base", "ask"):
        return True
    if how == "single":
        one = (names[0] or "").lower()
        wl = word.strip().lower()
        return bool(wl) and len(wl) >= 2 and (
            one == wl or wl in one or (len(one) >= 2 and one in wl))
    return False


def axis_focus_plan(focus, intent, measure_pick, match, preds, kid_pred, diag=None,
                    trusted=None, resolved=None):
    """Focus, сведящийся к target_src оси, — имя оси, пока вопрос не про каталог.

    None — прежний путь (focus = источник). Иначе ('holder', src, col) или
    ('clarify', srcs, live). При билете entity — None: документ реализации
    остаётся источником, ПКО по ДокументОснование — класс F.
    """
    if not focus or not serene_axis:
        return None
    if entity_choice_locked(trusted, resolved):
        if diag is not None:
            diag["focus_axis_keep"] = "entity_settled"
        return None
    holders = holders_of_target(focus)
    if not holders:
        return None
    col_by = {h["src"]: h["col"] for h in holders}
    holder_srcs = [h["src"] for h in holders]
    word = (measure_pick or (intent or {}).get("measure") or "").strip()
    want = (intent or {}).get("want") or ""
    amount = (intent or {}).get("amount") or {}
    nums_by = measures_of_many([focus] + holder_srcs)
    cat_names = nums_by.get(focus) or []
    word_on_catalog = _word_hits_measure(cat_names, word)
    word_on_holders = False
    if word:
        for s in holder_srcs:
            if _word_hits_measure(nums_by.get(s) or [], word):
                word_on_holders = True
                break
    asks = serene_axis.asks_movement_magnitude(
        want, word, amount, word_on_holders, word_on_catalog)
    self_q = serene_axis.catalog_self_question(
        want, asks, word_on_catalog, word_on_holders)
    if self_q:
        if diag is not None:
            diag["focus_axis_keep"] = "catalog_self"
        return None
    live = live_src_counts(holder_srcs, match, preds,
                           pred_by=kid_pred or {}, require_nums=asks)
    if live is None:
        return None
    zeros = [s for s in holder_srcs if live.get(s, 0) == 0]
    if zeros:
        childish = set()
        try:
            rs = psql("SELECT src_table, parent FROM %s WHERE src_table IN (%s)"
                      % (TABLES, ", ".join(lit(s) for s in zeros)))
            childish = {r[0] for r in (rs or [])
                        if r and r[0] and (r[1] or "").strip()}
        except RuntimeError:
            pass
        retry = [s for s in zeros if s in childish and s not in (kid_pred or {})]
        if retry:
            live2 = live_src_counts(retry, "", preds, require_nums=asks)
            if live2:
                live.update(live2)
    live_holders = [s for s in holder_srcs if live.get(s, 0) > 0]
    kind, payload = serene_axis.decide_axis_focus(True, False, live_holders)
    if kind == "keep":
        return None
    if kind == "holder":
        src = payload
        col = col_by.get(src, "")
        if diag is not None:
            diag["focus_was_axis"] = {"было": focus, "стало": src, "ось": col}
        return ("holder", src, col)
    return ("clarify", payload, {s: live.get(s, 0) for s in payload})


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


def period_assumed_needs_clarify(intent, today=None):
    """Assumed-окно длиной ≥ ~квартала без года в вопросе → уточнить период (K4-1).

    День/неделя/месяц (короткие относительные) — False: одно условное прочтение.
    Календарный/скользящий год и кварталоподобное окно — True (п. 12).
    K9-ф8: event+count с окном в intent — False (см. event_count_has_explicit_period).
    """
    if event_count_has_explicit_period(intent):
        return False
    if serene_enough is None or not serene_enough.period_assumed(intent):
        return False
    p = (intent or {}).get("period") or {}
    fr, to = p.get("from"), p.get("to")
    if not fr or not to:
        return False
    if not today:
        today = time.strftime("%Y-%m-%d")
    if period_is_canon_guess(p, today):
        return True
    od_fr, od_to = _day_ord(fr), _day_ord(to)
    if od_fr is None or od_to is None:
        return False
    span = od_to - od_fr
    # квартал ≈ 89..92; год уже покрыт canon_guess; короче месяца — нет
    return span >= 85


def stock_subject_needs_clarify(question, intent=None):
    """Остаток без названного товара → subject-clarify (K4-1 №12).

    Узко: склад снят («всех»/all) или маркер «леж*» — иначе прежний stock-path
    (bridge / склад), чтобы «какие остатки на складах» не уходили в subject.
    """
    if not question_asks_stock_balance(question):
        return False
    if stock_asks_named_product(question, intent):
        return False
    q = " ".join(str(question or "").lower().split())
    if "леж" in q:
        return True
    if any(w in q for w in ("всех", "всеми", "altogether", "all warehouses", "all stocks")):
        return True
    return False


def warehouse_axis_values(limit=20):
    """Человеческие имена складов: catalog по alias, ось по search_refcols.

    Каталог — entity_form_catalogs_for_kind (stem склад/warehouse ∩
    label|aliases|best_used_for). Колонка refs_map — из search_refcols по
    target_src (score: accumulationregister_* holders, затем max DISTINCT).
    Запасной путь — search_refmap.name WHERE owner=каталог. Пусто/оффлайн → [].
    Доки: map_extract_value (Map Functions); SELECT ORDER BY LIMIT.
    """
    cats = []
    for kind in ("склад", "warehouse"):
        try:
            found = entity_form_catalogs_for_kind(kind, allow_meaning=True) or []
        except RuntimeError:
            found = []
        for s in found:
            if s and s not in cats:
                cats.append(s)
    if not cats:
        return []
    cats_sql = ", ".join(lit(s) for s in cats)
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
    try:
        rows = psql(
            "SELECT DISTINCT name FROM search_refmap "
            "WHERE owner IN (%s) AND name IS NOT NULL AND trim(name) <> '' "
            "LIMIT %d" % (cats_sql, int(limit)))
    except RuntimeError:
        return out
    _take(rows)
    return out


def warehouse_clarify(question, diag, cut, t0, warehouses=None):
    """Уточнение склада-значения словами человека (K4-3 №11). None — не строить."""
    wh = list(warehouses if warehouses is not None else warehouse_axis_values())
    if len(wh) <= 1:
        return None
    opts = [{"src": "", "label": w, "hint": "", "distinct_by": "warehouse",
             "found": 0} for w in wh]
    d = dict(diag or {})
    d["warehouse_clarify"] = True
    cyr = any("\u0400" <= c <= "\u04ff" for c in (question or ""))
    text = ("На каком складе?" if cyr else "Which warehouse?")
    return {"partial": cut or None, "kind": "clarify", "text": text,
            "options": opts, "sources": [],
            "diag": _diag_pack(d, sec=round(time.time() - t0, 2),
                               reason="склад не назван, значений несколько")}


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
    """Вопрос -> поиск в базе -> счёт в базе -> формулировка -> гейт.

    `focus` — подсказка отбора (сужает кандидатов через resolve_focus). Доказанный выбор
    человека — только `trusted` из `decision_id` (план §6): сырой focus защиты не гасит.
    Когда вопрос неоднозначен, система отвечает kind=clarify с options[].decision_id;
    повтор с билетом снимает одну неоднозначность. Порядок п. 21 сохраняется.

    Порядок важен: сначала множество совпадений раскладывается по источникам ЦЕЛИКОМ,
    и только потом выбирается один источник и тянутся его строки. Обратный порядок
    (сперва top-N строк, потом группировка) терял целые таблицы.
    """
    if _token_acc.get() is None:
        _token_acc_start()
    resolved = dict(resolved or {})
    if resolved.get("src") and not focus:
        focus = resolved["src"]
    if "measure" in resolved and measure_pick is None:
        mp = resolved.get("measure")
        measure_pick = mp if mp not in (None, "") else measure_pick
    t0 = time.time()
    # 🔴 ПОШАГОВЫЙ СЛЕД: КОГДА, ЧТО СДЕЛАНО И ЧТО ПОЛУЧИЛОСЬ. Требование владельца 03.08:
    # «на каждом шагу логировать можно — время, что делается и что происходит».
    #
    # Заведён не для красоты. `[03.08]` за один день два диагноза пришлось выводить
    # запросами к базе задним числом, и один из них оказался неверным: почему ответ был
    # «88», выяснилось только перебором сущностей с таким числом строк (`HOW_NOT_TO §1.46`).
    # Ответ уже содержал `diag`, но в нём лежали ПОМЕТКИ, а не ход: не видно ни порядка, ни
    # времени, ни того, какой шаг сузил множество.
    #
    # След — часть ответа (`diag.шаги`), а не только журнал: прогонщик и приёмка получают
    # его тем же путём, что числа, и он не теряется при доставке. Ссылка на список лежит в
    # `diag`, поэтому все ветки возврата отдают его накопленным, без правки каждой из них.
    шаги = []

    def шаг(что, **чем):
        ms = int((time.time() - t0) * 1000)
        шаги.append(dict(шаг=что, мс=ms, **чем))
        status = (" ".join("%s=%s" % (k, v) for k, v in чем.items())
                  if чем else "ok")
        _trace_write("service", что, ms, status)

    today = time.strftime("%Y-%m-%d")
    intent = parse_intent(question, today)
    apply_proven_period(intent, trusted=trusted, resolved=resolved)
    period_from_prior = False
    if prior:
        period_from_prior = apply_prior_period(intent, parse_intent(prior, today), today)
    # P3: bare YoY without sales context -> clarify (not FX / entity search).
    # Ignore LLM-filled period unless it came from prior dialog (period_from_prior).
    if _yoy_compare_marker(question):
        _yp = intent.get("period") or {}
        _has_win = bool(_yp.get("from") or _yp.get("to"))
        if (not sales_sum_intent(intent, question)
                and not (period_from_prior and _has_win)):
            return {
                "partial": None, "kind": "clarify",
                "text": "Сравнить какие продажи?",
                "options": [], "sources": [],
                "diag": {"yoy_need_sales_context": True, "шаги": шаги},
            }
    # Фаза B: лидер окна MTD/WTD в основной preds; полный календарь — конкурент детектора.
    _w_readings = apply_period_leader(
        intent, today, period_from_prior=period_from_prior, question=question)
    _day_prefer = calendar_day_basis_prefer(intent, trusted=trusted)
    _curr_prefer = currency_amount_basis_prefer(intent, trusted=trusted)
    _ask_readings = expand_readings_calendar_axis(_w_readings, prefer=_day_prefer)
    _ask_readings = expand_readings_currency_axis(
        _ask_readings, prefer=_curr_prefer, intent=intent, trusted=trusted)
    # Ticket/словарь сдвинул day-basis на working — основной preds тоже фильтрует.
    if (_day_prefer == _DAY_BASIS_WORKING and calendar_axis_open()
            and isinstance(intent.get("period"), dict)
            and (intent["period"].get("from") or intent["period"].get("to"))):
        intent["period"] = dict(intent["period"])
        intent["period"]["day_basis"] = _DAY_BASIS_WORKING
    preds = _predicates(intent)
    разбор = intent.get("parse") or {}
    diag = {"terms": intent.get("terms"), "preds": preds, "kind": intent.get("kind"),
            "parse": разбор, "шаги": шаги}
    _fork_early = {"rows": None, "cls": None, "rel": None, "pool": None}
    if period_from_prior:
        diag["period_from_prior"] = True
    if _w_readings:
        diag["period_readings"] = len(_w_readings)
        _pf = None
        if ASK_SALES_RANK_CANON:
            _pf = period_form_from_question(question)
            pr0 = intent.get("period") or {}
            if (pr0.get("interpretation_id") or "") == "prev_week":
                _pf = "prev_week"
        _wl = prefer_window_leader(_w_readings, prefer_form=_pf)
        if _wl and _wl.get("interpretation_id"):
            diag["period_leader"] = _wl["interpretation_id"]
    if _ask_readings and len(_ask_readings) != len(_w_readings):
        diag["calendar_readings"] = len(_ask_readings)
        diag["day_basis_leader"] = _day_prefer
    if ASK_CURRENCY_AXIS and currency_axis_open():
        diag["amount_basis_leader"] = _curr_prefer
    шаг("разбор вопроса", тип=intent.get("kind"), понятий=len(intent.get("terms") or []),
        величина=(intent.get("measure") or "—"), считать=(intent.get("want") or "—"),
        потеряно=(",".join(разбор.get("lost") or []) or "—"))

    # ВОПРОС О САМИХ ДАННЫХ ИЛИ О ТОМ, ЧТО СИСТЕМА О НИХ ЗНАЕТ (п. 13).
    #
    # «То, что недоступно — закрыто правами, не загрузилось, не попало в индекс — видно
    # владельцу». До этого перепись считалась и не читалась никем: [замер 28.07] `grep`
    # по сервису ответов давал ноль совпадений с `search_coverage` и `base_profile`.
    # Владелец узнавал о 5 993 потерянных строках, только заглянув в таблицу руками.
    #
    # Различает вопросы МОДЕЛЬ, тем же разбором намерения, который и так делается на
    # каждый вопрос: ни второго обращения к модели, ни списка слов. Список вроде
    # «чего нет», «не загрузилось» был бы хардкодом под язык (`HOW_NOT_TO §3.9`), а
    # продукт коробочный и конфигурация может быть любой.
    if (intent.get("about") or "") == "coverage":
        # «почему продаж ноль, это сбой?» — не перепись системы, а period_empty
        # по продажам ([замер 21.08 okna] about=coverage → пустой figures).
        if period_zero_why_question(question):
            intent["about"] = "data"
            if (intent.get("want") or "") == "list":
                intent["want"] = "sum"
            diag["about_coverage_refused"] = "period_zero_why"
        else:
            diag["about"] = "coverage"
            return _coverage_answer(question, diag, t0)
    # Что не доехало до модели — уходит в ОТВЕТ, а не в журнал (п. 13). Объявлено здесь,
    # потому что ранние ветки возврата (нет совпадений) отвечают раньше выбора сущности.
    cut = {}
    # Именованный остаток без balance-источника — до отбора/модели/форка ([замер 22.08 okna]).
    if question_asks_stock_balance(question) and stock_asks_named_product(question, intent):
        _cap_early = balance_capable_or_registers()
        _goods_early = balance_registers_with_goods(_cap_early) if _cap_early else frozenset()
        if not _cap_early or not _goods_early:
            diag["stock_named_early"] = True
            return stock_balance_named_no_data(question, diag, cut, t0)
    # Условие вопроса, снятое на разборе (период не датой, порог не числом, понятие сверх
    # бюджета), расширяет множество ответа против того, о чём спросили. Такая потеря
    # выходит человеку тем же путём, что и остальные (п. 13), а не остаётся в журнале.
    if разбор.get("lost"):
        cut["intent_lost"] = ", ".join(разбор["lost"])
    # Условие, которого в вопросе не было (период, выведенный от сегодняшней даты), —
    # допущение системы. Оно применяется, но человек про него узнаёт: молчаливое
    # допущение неотличимо от того, что он спросил сам (п. 12).
    if разбор.get("assumed"):
        diag["intent_assumed"] = ", ".join(
            "%s=%s" % (a, (intent.get("period") or {}).get(a.split(".")[-1], ""))
            for a in разбор["assumed"])
    # K4-2: kind без опоры в корпусе — no_data до чужого src (№14 анкеты).
    # §4.3: канон, забравший вопрос, — сам поддержка; страж уступает канону.
    _kind_chk = (intent.get("kind") or "").strip()
    if (_kind_chk and not kind_has_corpus_support(_kind_chk)
            and not canon_claims_question(intent, question)):
        diag["kind_unsupported"] = _kind_chk
        return {"partial": cut or None, "kind": "no_data", "sources": [],
                "text": NO_DATA_TEXT or refuse_text(question),
                "diag": _diag_pack(diag, sec=round(time.time() - t0, 2),
                             reason="kind_unsupported_in_corpus")}
    # K4-2: off-topic / творческий запрос без учётного want (№17/18).
    if not question_expects_accounting_data(intent, question, diag):
        diag["non_accounting_question"] = True
        return {"partial": cut or None, "kind": "no_data", "sources": [],
                "text": NO_DATA_TEXT or refuse_text(question),
                "diag": _diag_pack(diag, sec=round(time.time() - t0, 2),
                             reason="non_accounting_question")}
    # K4-1 / п. 12: длинное assumed-окно — уточнение, не число наугад.
    # Не при period_from_prior и не при доказанном ticket (trusted/resolved period).
    _period_from_prior = bool((diag.get("prior") or {}).get("period")
                              or diag.get("period_from_prior"))
    if (not _period_from_prior
            and not (trusted or {}).get("period")
            and period_assumed_needs_clarify(intent, time.strftime("%Y-%m-%d"))):
        diag["period_assumed_clarify"] = True
        ask = _need_clarify(
            question, [{"kind": "period", "word": ""}],
            "период выведен системой, в вопросе не назван",
            dict(diag, шаг="assumed-period"))
        if ask:
            return ask

    # Сравнение A и B — члены одной оси, не AND в одной строке. Схлопываем ДО probe.
    terms_for_axis = [list(g) for g in (intent.get("terms") or [])]
    if serene_axis:
        try:
            _own = term_ref_owners(terms_for_axis)
            _merged, _sets = serene_axis.merge_compare_term_groups(
                intent.get("terms") or [], _own)
            if _sets:
                intent["terms"] = _merged
                diag["compare_merged"] = _sets
        except RuntimeError:
            pass
    exprs, kinds = probe(intent.get("terms") or [])
    diag["match_by"] = {k: v for k, v in kinds.items() if k != "_resolved"}
    # Разрешённые резолвером значения — В ОТВЕТ (п. 13): человек должен видеть, что «Питер»
    # поняли как «Санкт-Петербург», а не гадать. В тексте это и так всплывёт, но метка
    # даёт проверяемый след.
    if isinstance(kinds, dict) and kinds.get("_resolved"):
        diag["resolved"] = kinds["_resolved"]

    # 🔴 ЗНАЧЕНИЕ, КОТОРОГО НЕТ, НЕ ПРЕВРАЩАЕТСЯ В «ВСЁ». Термы `terms` — это ЗНАЧЕНИЯ,
    # которые обязаны стоять в записи (имя контрагента, товар). Если группа не нашлась ни
    # буквально, ни резолвером — такого значения в базе нет. Прежде группа молча
    # выбрасывалась, и «продали SanDisk» отвечало про ВСЕ продажи на 12 млн — неверный
    # ответ (п. 3), опаснее отказа. Считаем: сколько групп-значений осталось без совпадения.
    n_groups = len(intent.get("terms") or [])
    matched_groups = matched_group_count(kinds)
    if n_groups > 0 and matched_groups < n_groups:
        missing = n_groups - matched_groups
        diag["unmatched_terms"] = missing
        # K4-2 / п. 21: любая ненайденная группа-значение — отказ, не чужой src+меры.
        # Раньше отказ только при matched_groups==0; частичный промах уходил дальше.
        # Обрезанный резолв здесь не выделяется: «ПАНГЕЯ»→«П» не проходит гарду
        # резолвера (_shares_chars, пол 3) и значит unmatched — тот же отказ.
        return {"partial": cut or None, "kind": "no_data", "sources": [],
                "text": NO_DATA_TEXT or refuse_text(question),
                "diag": _diag_pack(diag, sec=round(time.time() - t0, 2),
                             reason="значения из вопроса не найдены в данных")}

    match, k = match_expr(exprs, preds)
    diag["min_should_match"] = k if exprs else 0

    by = tables_of(match, preds)
    # 🔴 ЧАСТИЧНО СОВПАВШИЕ — НЕ ПОТЕРЯННЫЕ (04.08). Общий порог `k` ставит та сущность,
    # где слова вопроса встретились гуще всего, и все, кто нашёл на одно понятие меньше,
    # исчезали молча. `[замер 04.08]` на 44 парах приёмки: при выбранном `k` эталон доходит
    # до кандидатов в 5 случаях (11 %), при «хотя бы одно понятие» — в 33 (75 %); порог
    # съедал 28 эталонов из 44. Разбор — `partial_tables`.
    #
    # Отбор прошедших порог НЕ меняется ни на знак: `by` и `match` те же, что были, а
    # частичные идут отдельным списком, без числа совпадений, со своим условием на случай,
    # если выберут именно их. Поэтому вопросы, работавшие вчера, работают ровно так же.
    part_lvl, part_pred = partial_tables(exprs, preds, k)
    шаг("отбор: буквально", сущностей=len(by), строк=sum(by.values()) if by else 0,
        частично=len(part_lvl))
    # 🔴 ТРИ ПОВЕРХНОСТИ ОТБОРА СКЛАДЫВАЮТСЯ, А НЕ ЗАМЕНЯЮТ ДРУГ ДРУГА (03.08).
    #
    # Как было: буквальный отбор служил ШЛЮЗОМ. Нашёл хоть что-нибудь — пусть мусор — и
    # ни смысл, ни синонимы не спрашивались вовсе (`if not by and match and emb_ready`).
    # А слово человека и слово базы не совпадают в принципе: в 1С продажа называется
    # «реализация». [замер 03.08] `ts_phrase('продали')` по всему корпусу — 4 строки в
    # трёх каталогах вариантов отчётов; ослабленный до подстроки `ts_like('%продаж%')`
    # даёт регистр себестоимости на 7 307 совпадений против 272 у верного документа, то
    # есть верное не отсутствует, а ТОНЕТ, и тонет ровно по тому признаку («сколько
    # совпадений»), который мы отдаём модели как различающий.
    #
    # Стало: кандидатов приносят три независимых источника, и ни один не имеет права
    # закрыть остальные —
    #   1. слова строки  — инвертированный индекс (`by`, выше);
    #   2. синонимы сущности — `alias_hits`, знание базы о себе, собранное при установке;
    #   3. смысл названия  — `near_tables`, kNN по меткам сущностей.
    # Добавленные приходят БЕЗ числа совпадений (`counts_for_model` остаётся буквальным):
    # выдумывать им счёт нельзя, а «0 совпадений» модель прочла бы как «здесь пусто».
    #
    # 🔴 ПОЧЕМУ КОРПУС ОСТАЁТСЯ ЗАПАСНЫМ ПУТЁМ, А НЕ ЧЕТВЁРТЫМ СЛАГАЕМЫМ. Цена замерена
    # `[замер 03.08]`: kNN по меткам — 52 мс на 1 502 строки, по алиасам — 53 мс, а по
    # КОРПУСУ — 4 642 мс на 623 565 строк, потому что векторного индекса нет ни одного
    # (`duckdb_indexes()` → только `search_idx` и `alias_idx`; `ivf` заблокирован,
    # `VECTOR_DECISION.md`) и запрос идёт полным сканом. Класть 4,6 с в КАЖДЫЙ вопрос
    # нельзя: это и время ответа, и единственное место, где цена вопроса растёт с
    # размером базы (п. 6 `TARGET_STATUS`). Как только векторный индекс появится —
    # сложить и его, разбор сложения тот же.
    #
    # 🔴 ВХОД ПОВЕРХНОСТЕЙ — РОД ЗАПИСЕЙ, А НЕ ТОЛЬКО ЗНАЧЕНИЯ (04.08, замер ниже).
    # Шаг 1 раскладывает вопрос на две разные вещи: `terms` — ЗНАЧЕНИЯ, которые обязаны
    # стоять в записи (имя контрагента, товар), и `kind` — РОД записей, «о чём вопрос».
    # Род в `terms` не кладётся намеренно (иначе отбор ищет слово «продажа» по всем
    # строкам). А словарь синонимов описывает ровно род: «как человек назвал бы такие
    # записи». То есть поверхность синонимов кормили тем, о чём она не знает.
    # `[замер 04.08]` на настоящих разборах шага 1 `terms` пусты у **47 вопросов из 58**,
    # и `alias_hits` на пустых выражениях выходит первой же строкой: верную сущность эта
    # поверхность доносила в **2 случаях из 44 (5 %)**, а на входе `kind`+`terms` —
    # в 21 (48 %). Смысловая поверхность спрашивалась «род ИЛИ вопрос», то есть у 57
    # вопросов из 58 — коротким родом вместо самого вопроса: 20 (45 %) против 29 (66 %)
    # по вопросу. Теперь обе спрашиваются обоими входами, и ни один не закрывает другой.
    # Прибор — `work/acceptance/step3_bench.py` (детерминирован, модель ответов не зовёт,
    # разбор вопроса берётся из прогона прибора шага 1, а не сочиняется приближением).
    kind_text = (intent.get("kind") or "").strip()
    # Понятия вопроса целиком (значения плюс род) — считаются ОДИН раз на вопрос: их просят
    # и отбор смыслом, и подтверждение выбора по словарю синонимов.
    exprs_all = question_exprs(exprs, kind_text)
    # Полный итог шага 3 — в порядке слияния мест, БЕЗ вычитания буквально найденных:
    # ниже он служит головой итогового порядка, а буквальный отбор при пустых понятиях
    # отдаёт ВСЕ сущности, и вычитание оставило бы голову пустой (`[замер 04.08]` живой
    # ответ: «шаг 3 добавил 0» при 1 502 буквальных кандидатах).
    found_by_meaning = meaning_candidates(exprs, kind_text, question, MEANING_TOP, diag=diag)
    if not match:
        by, _inc = date_only_kind_filter(by, match, found_by_meaning)
        if _inc:
            diag["date_incidental"] = _inc
    extra = [t for t in found_by_meaning if t not in by]
    if extra:
        diag["by_meaning"] = extra
    шаг("отбор: смысл и синонимы", добавлено=len(extra))
    # 🔴 ЧАСТИЧНО СОВПАВШИЕ ВСТАЮТ В САМЫЙ ХВОСТ, И ЭТО НЕ СКРОМНОСТЬ, А ГРАНИЦА ШАГОВ.
    # Их много (медиана около двухсот против восьми у смысловых), а у шага выбора перечень
    # ограничен бюджетом знаков. Поставить эту пачку впереди значило бы вытеснить из бюджета
    # кандидатов шага 3 — а там `[замер 04.08]` эталон доходит до модели 44 из 44, то есть
    # чужая, уже доказанная работа была бы испорчена молча и в чужом шаге.
    # Задача шага 2 здесь другая и она выполнена: сущность, найденную по словам вопроса,
    # больше не выбрасывают — она есть в кандидатах и её видно (`by_partial`).
    # Порядок внутри — по уровню, затем по имени: разделитель равенства обязателен, иначе
    # набор колеблется между одинаковыми вопросами (`techContext` ловушка 30).
    if part_lvl:
        part_order = sorted(part_lvl, key=lambda t: (-part_lvl[t], t))
        # 🔴 В КАНДИДАТЫ — НЕ БОЛЬШЕ БЮДЖЕТА (04.08, сессия шага 3). Сам список частичных
        # растёт с числом сущностей базы (медиана около двухсот по замечанию выше), и без
        # отсечки он уходил бы целиком в `cands`, оттуда в текст запроса `IN (…)` и в
        # перечень для модели — то есть цена вопроса росла бы с размером базы, чего
        # проект не допускает нигде (п. 9, `SCALE_BLOCKERS`). Отсечка та же, что у
        # остальных поверхностей (`MEANING_TOP`), и порядок тот же — по уровню.
        # `[замер 04.08]` на 44 парах приёмки с настоящими разборами шага 1 отсечка не
        # меняет ничего: частичных там 0 на каждом вопросе (эталон ими не приносится ни
        # разу), то есть это защита от роста, а не потеря сигнала.
        fit = [t for t in part_order if t not in by and t not in extra]
        taken = fit[:MEANING_TOP]
        extra = extra + taken
        # След тоже ограничен, и по той же причине: полный список растёт с числом
        # сущностей базы, а ответ сервиса — не место для того, что растёт. Показываются
        # дошедшие; сколько их было всего, видно в `partial` ответа — тем же полем, каким
        # система показывает всё недоехавшее, чтобы отсечка не стала молчаливой (п. 13).
        diag["by_partial"] = {t: part_lvl[t] for t in taken}
        if len(fit) > len(taken):
            sb = diag.setdefault("selection_budget", {})
            sb["partial_shown"] = len(taken)
            sb["partial_total"] = len(fit)
    # Табличные части попадают в кандидаты вместе со своей шапкой: искать их по словам
    # вопроса бесполезно — имени контрагента в строках товаров нет.
    # ⚠ ГРАНИЦА, ОСТАВЛЕННАЯ СОЗНАТЕЛЬНО: строки берутся у шапок, найденных СЛОВАМИ.
    # Отбор потомка по устройству опирается на буквальное совпадение владельца
    # (`kid_pred` — «владелец строки среди совпавших»), поэтому у сущности, пришедшей
    # только от смысла или синонима, табличных частей не будет. Расширять это тем же
    # заходом нельзя: у меры «сколько штук» и без того отдельный дефект выбора величины,
    # и смешивать две правки — значит не суметь сказать, которая подействовала.
    kids, kid_pred = children_by_parent(by, match, preds)
    if kids:
        by.update(kids)
        diag["children"] = kids
    # Ищем по смыслу, только если векторы корпуса посчитаны ТОЙ ЖЕ моделью (`emb_ready`).
    if not by and match and emb_ready(CORPUS):
        vec = _vec(question)
        # Оператор <=> — РОДНОЕ ядро движка (cosine_distance), а array_cosine_similarity
        # приходит из ядра DuckDB. Разница не только в скорости (замер 27.07: 583-627 мс
        # против 435-451 на 97 965 x 1536): только родные функции несут AnnFunctionInfo,
        # то есть array_* НИКОГДА не сможет воспользоваться векторным индексом. Выдача
        # не меняется — сверено топ-40, совпало 40 из 40 позиция в позицию.
        # <=> это РАССТОЯНИЕ: меньше = ближе, поэтому сортировка по возрастанию, без DESC.
        # 🔴 И ЗДЕСЬ РАЗДЕЛИТЕЛЬ РАВЕНСТВА. Это самое дорогое место: `LIMIT` отрезает
        # ближайшие строки, из них складывается САМ НАБОР сущностей-кандидатов, и без
        # разделителя набор колеблется. [замер 30.07] один вопрос пять раз — сущностей в
        # наборе 1 322, 1 322, 1 318, 1 318, 1 318, и вместе с набором менялся ответ.
        # `emb IS NOT NULL` — см. разбор в `resolve_near`: без него запрос при пустых
        # векторах отдаёт первые по алфавиту, выдавая их за ближайшие по смыслу.
        near = psql("SELECT src_table, count(*) FROM (SELECT src_table FROM %s "
                    "WHERE emb IS NOT NULL "
                    "ORDER BY emb <=> %s, src_table, row_key LIMIT %d) GROUP BY 1"
                    % (CORPUS, vec, TOPK))
        by = {r[0]: int(r[1]) for r in near if r and r[0]}
        match = ""
        diag["by_vector"] = True
    if not by and not extra:
        by = tables_of("", preds)
        if by:
            diag["by_period_fill"] = True
    # K4-3 №11: stock-вопрос с пустым отбором — не резать no_data до stock-path.
    if not by and not extra:
        if question_asks_stock_balance(question):
            diag["stock_bypass_empty_by"] = True
            # уйдём в stock-path ниже с пустыми cands → balance_bridge / warehouse
        else:
            return {"partial": cut or None, "kind": "no_data", "text": NO_DATA_TEXT or refuse_text(question), "sources": [],
                    "diag": _diag_pack(diag, sec=round(time.time() - t0, 2))}

    # Кандидаты: те, где поиск ЧТО-ТО нашёл, плюс ближайшие по смыслу названия.
    # Кандидаты — те сущности, где поиск ДЕЙСТВИТЕЛЬНО что-то нашёл. Без отсечки по
    # числу: любое «первые N» означает «на нашей базе нужное попадало в первые N», и на
    # базе другого размера нужная сущность просто выпадет из списка.
    #
    # «Совпадений N» имеет смысл, только если совпадение было по СЛОВАМ вопроса. Одно
    # условие по дате — не совпадение: группировка тогда возвращает размеры таблиц,
    # отфильтрованные по дате. Замерено на «сколько продали в декабре»: календарные
    # графики 62, регистр производственного календаря 31, нужный документ 6 — и модели
    # это подавалось как «столько записей совпало».
    signal = bool(match)
    # Число подошедших строк показывается модели ВСЕГДА, а не только при совпадении по
    # словам. Прежняя оговорка («без слов это просто размеры таблиц, отфильтрованные по
    # дате») верна лишь наполовину: отфильтрованное по дате число — это и есть данные о
    # вопросе. [замер 28.07] «сколько продали в декабре» уходило в регистр
    # `accumulationregister_реализацияуслуг_recordtype` с ОДНОЙ декабрьской записью
    # вместо документа продажи с шестью — по названию они почти неразличимы, а по числу
    # подошедших строк различаются вшестеро.
    counts_for_model = by
    # Кандидаты — ВСЕГДА те сущности, которые реально подошли: по словам вопроса, а
    # если слов нет — по его условиям (период, порог суммы). Раньше при отсутствии
    # слов список подходящих ВЫБРАСЫВАЛСЯ и модели отдавались все 226 сущностей
    # базы. Замерено: «продажи за декабрь» — нужный документ был среди подходящих по
    # дате (6 строк), но тонул в общем списке, и выбирались календарные графики.
    # ...и рядом с ними — пришедшие от синонимов и от смысла названия. Они идут ПОСЛЕ
    # буквально найденных и БЕЗ числа совпадений: буквальное совпадение — сигнал сильнее,
    # а выдуманный счёт был бы враньём в том самом поле, которым модель различает
    # кандидатов. Порядок ниже всё равно пересобирается по смыслу и реранкером.
    cands = list(by) + [t for t in extra if t not in by]
    if event_path_active(intent):
        _cands_pre_kind = len(cands)
        cands = event_kind_catalog_expand_pool(cands, intent)
        if len(cands) > _cands_pre_kind:
            diag["event_kind_pool_expand"] = cands[_cands_pre_kind:]
    cands = prefer_entity_for_rank(cands, intent, question)
    cands = prefer_entity_for_sales(cands, intent, question)
    cands = prefer_entity_for_catalog_count(cands, intent, question)
    if K6R:
        def _k6_mk_clarify(cat, holder, extra):
            return k6_dual_atom_clarify_return(
                cat, holder, question, diag, cut, t0, by, match, preds,
                diag.get("marks") or {}, extra)
        _period0 = (intent or {}).get("period") or {}
        _has_period0 = bool(_period0.get("from") or _period0.get("to"))

        def _catalogs_for_kind(axis_word):
            w = (axis_word or "").strip()
            if not w:
                return []
            return entity_form_catalogs_for_kind(w, allow_meaning=_has_period0)

        # K6 v2: при RuntimeError от psql порядок кандидатов прежний (diag answer_fit_v2_down)
        # (RuntimeError от psql без DSN в офлайн-замках, сбой соединения) —
        # порядок прежний, отметка в diag. Ранг не роняет ответ.
        try:
            _k6r = K6R.apply_to_candidates(
                psql, lit, cands, intent, question, today=today,
                stem_dict=STEM_DICT, corpus=CORPUS, tables=TABLES,
                sales_sum=sales_sum_intent(intent, question),
                rank_intent=rank_intent_from(intent, None, question),
                mk_clarify=_k6_mk_clarify,
                catalogs_for_kind=(
                    _catalogs_for_kind if event_path_active(intent) else None))
        except RuntimeError as _k6_err:
            _k6r = {}
            diag["answer_fit_v2_down"] = type(_k6_err).__name__
        if _k6r.get("diag"):
            diag.update(_k6r["diag"])
        if _k6r.get("clarify"):
            шаг("K6 v2", dual_atom=True)
            return _k6r["clarify"]
        cands = _k6r.get("cands") or cands
        counts_for_model = entity_pick_counts_for_model(
            by, diag, intent, question)
        шаг("K6 v2", кандидатов=len(cands))
    if question_asks_stock_balance(question):
        capable = balance_capable_or_registers()
        cands = filter_stock_balance_sales_noise(cands, question, diag)
        named = stock_asks_named_product(question, intent)
        # K4-1 №12: остаток без предмета — уточнение товара (не figures по продажам).
        if (not named and stock_subject_needs_clarify(question, intent)
                and not measure_pick
                and not (trusted or {}).get("subject")):
            q_low = " ".join(str(question or "").lower().split())
            # «всех складах» / all — склад снят; иначе тоже subject первее bridge.
            diag["stock_subject_clarify"] = True
            ask = _need_clarify(
                question, [{"kind": "subject", "word": "товар"}],
                "остаток без названного товара",
                dict(diag, шаг="stock-subject"))
            if ask:
                return ask
        if named:
            _goods_cap = balance_registers_with_goods(capable) if capable else frozenset()
            if not capable or not _goods_cap:
                return stock_balance_named_no_data(question, diag, cut, t0)
            cands = [c for c in cands if c in _goods_cap or c in capable]
            cands = filter_balance_structural(cands, diag)
            if not cands:
                return stock_balance_named_no_data(question, diag, cut, t0)
        else:
            # K4-3 №11: несколько складов-значений → clarify до bridge/no_data.
            wh_ask = warehouse_clarify(question, diag, cut, t0)
            if wh_ask:
                return wh_ask
            if capable:
                hit = [c for c in cands if c in capable]
                if not hit:
                    bridge = balance_bridge_clarify(
                        question, capable, diag, cut, t0)
                    if bridge:
                        return bridge
            cands = filter_balance_structural(cands, diag)
            if not cands and capable:
                bridge = balance_bridge_clarify(
                    question, capable, diag, cut, t0)
                if bridge:
                    return bridge
    шаг("кандидаты собраны", всего=len(cands))
    # 🔴 «НА ЧТО НЕ ОТВЕЧАЕТ» — ВТОРАЯ ПОЛОВИНА ЗНАНИЯ УСТАНОВКИ, И ОНА НАКОНЕЦ ЧИТАЕТСЯ.
    # Установочный агент пишет про каждую сущность две половины: «на что отвечает»
    # (`best_used_for`, она уезжает в карточку) и «на что НЕ отвечает» (`not_enough_for`).
    # До 06.08 вторая половина не читалась ни одной строкой сервиса — а это ровно то
    # знание, которое различает соседей, названных одним словом: у «Отчёта о розничных
    # продажах» там дословно «оптовые продажи — не в этом списке», и на вопрос «продажи»
    # он не годится, тогда как «Реализация Товаров Услуг» такого не пишет. Разбор и
    # вся линейка из восьми отвергнутых форм — `work/entity-choice/not_for_probe.py`:
    # выбранная форма (весь род вопроса ⊆ одна запись без указателя на соседа) отсекает
    # 6 из 9 подмен при НУЛЕ отсечённых эталонов; чистое пересечение основ убивало до
    # 26 эталонов из 44.
    # Форма — отсев ДО модели: кандидат не годится, и модель его не видит. Правило
    # не выбирает за неё никого, поэтому ошибка в собранном моделью знании стоит
    # лишнего уточнения (проверки ниже работают как прежде), а не неверного ответа.
    # Отсев НИКОГДА не опустошает круг: если записи отсекают ВСЕХ кандидатов, знанию
    # не верим и работаем с полным кругом — данные могут быть неверны, а ответить
    # по полному кругу система умеет.
    not_for = set()
    if NOT_FOR and kind_text and not focus and len(cands) > 1:
        try:
            kr = psql("SELECT ts_lexize(%s, %s)" % (lit(STEM_DICT), lit(kind_text)))
            k_stems = {s for s in _stem_set(kr[0][0] if kr else "") if len(s) >= 3}
        except RuntimeError:
            k_stems = set()
        нф = []
        if k_stems:
            try:
                # Базы без словаря синонимов (таблица пуста или её нет — первая база)
                # проходят молча: записей нет — отсекать нечем, поведение прежнее.
                нф = psql(
                    "SELECT a.src_table, trim(split_part(u.item, '—', 1)), "
                    "       trim(split_part(u.item, '—', 2)) "
                    "FROM search_entity_alias a, "
                    "     unnest(str_split(a.not_enough_for, ',')) AS u(item) "
                    "WHERE a.not_enough_for IS NOT NULL AND trim(u.item) <> '' "
                    "  AND a.src_table IN (%s)"
                    % ", ".join(lit(c) for c in cands))
            except RuntimeError:
                нф = []
        if нф:
            # Основы обеих частей каждой записи — ОДНИМ запросом, как у
            # `same_concept_groups`: словоформы сводит словарь движка, а не моё
            # сравнение строк. Служебные слова («в», «и», «не») отпадают длиной —
            # это факт языка, а не список слов.
            тексты = sorted({(r[1] or "") for r in нф} | {(r[2] or "") for r in нф})
            стемы = {}
            if тексты:
                sel = ", ".join("ts_lexize(%s, %s)" % (lit(STEM_DICT), lit(x))
                                for x in тексты)
                try:
                    row = psql("SELECT " + sel)[0]
                    стемы = {x: {s for s in _stem_set(row[i]) if len(s) >= 3}
                             for i, x in enumerate(тексты)}
                except (RuntimeError, IndexError):
                    стемы = {}
            # Указатель («аспект — Другая Сущность») проверяется СТРУКТУРНО:
            # правая часть называет существоующую сущность базы. Проверять её
            # против ВСЕХ названий нужно только для записей, прошедших подмножество,
            # а их на вопрос единицы — поэтому запрос на запись, а не на таблицу.
            указ = {}
            for rt in sorted({(r[2] or "") for r in нф
                              if k_stems <= стемы.get(r[1] or "", set())}):
                if not rt:
                    указ[rt] = False
                    continue
                try:
                    n = psql(
                        "SELECT count(*) FROM %s WHERE "
                        "  len(list_filter(ts_lexize(%s, label), x -> length(x) >= 3))"
                        "  > 0 AND list_has_all("
                        "    list_filter(ts_lexize(%s, %s), x -> length(x) >= 3),"
                        "    list_filter(ts_lexize(%s, label), x -> length(x) >= 3))"
                        % (TABLES, lit(STEM_DICT), lit(STEM_DICT), lit(rt),
                           lit(STEM_DICT)))
                    указ[rt] = bool(n and int(n[0][0] or 0))
                except RuntimeError:
                    # Сбой чтения — запись считается указателем, и отсев молчит:
                    # это направление ошибки стоит уточнение, а не выбор без соседа.
                    указ[rt] = True
            по_кандидатам = {}
            for r in нф:
                по_кандидатам.setdefault(r[0], []).append(
                    (стемы.get(r[1] or "", set()), указ.get(r[2] or "", True)))
            not_for = {t for t, its in по_кандидатам.items()
                       if not_for_excludes(k_stems, its)}
            if len(not_for) >= len(cands):
                # Знание отсекло бы ВЕСЬ круг — ему нельзя верить настолько.
                diag["not_for_all"] = len(not_for)
                not_for = set()
            elif not_for:
                cands = [c for c in cands if c not in not_for]
                diag["not_for"] = sorted(not_for)
                шаг("отсев «не отвечает»", отсеяно=len(not_for))
    # ВЕЛИЧИНА, О КОТОРОЙ СПРАШИВАЮТ, ДОЛЖНА У КАНДИДАТА СУЩЕСТВОВАТЬ.
    # Строка несёт ВСЕ свои числовые величины картой, поэтому проверка теперь общая:
    # у кандидата должна быть хоть одна величина. Какая именно нужна — решается уже
    # после выбора сущности (`pick_measure`), потому что имена величин у каждой свои.
    # Отбор идёт ДАННЫМИ: у сущности либо есть заполненная величина, либо нет. Ни порога,
    # ни числа, ни имени — размер и состав базы ничего не меняют (п. 9).
    # [замер 27.07] без этого правила «сколько продали в декабре» отвечалось
    # «100 000 рублей (1 запись)» вместо 2 456 400 на 6 документах: вопрос уходил
    # к сущности, у которой суммы нет вовсе. Реранкер этого не закрывает — он про то,
    # ЧТО спросили, а не про то, ЧЕМ сущность располагает.
    if intent.get("want") == "sum" and len(cands) > 1:
        try:
            with_value = {r[0] for r in psql(
                "SELECT src_table FROM %s WHERE src_table IN (%s) "
                "  AND nums IS NOT NULL AND len(map_keys(nums)) > 0 GROUP BY 1"
                % (CORPUS, ", ".join(lit(c) for c in cands))) if r and r[0]}
            if with_value:
                dropped = [c for c in cands if c not in with_value]
                cands = [c for c in cands if c in with_value]
                if dropped:
                    diag["without_value"] = len(dropped)
        except RuntimeError:
            pass
    # 🔴 ПРИЗНАК «У КАНДИДАТА ЕСТЬ СПРОШЕННОЕ ПОЛЕ» ПРОВЕРЕН И ОТКЛОНЁН — код убран.
    # Мысль была: если человек спрашивает «ИНН», то у верной сущности такое поле должно быть.
    # Признак строился штатно, словарём движка по основам слов (`ts_lexize` + `list_has_any`,
    # `techContext` возможность 35), то есть падежи ему не мешали.
    #
    # [замер 30.07, три прогона по восемь вопросов] он НЕ УЛУЧШИЛ результат ни в одной форме:
    #   отсевом      — выбросил `catalog_склады` (сам ответ) и дал 4 неверных на 24;
    #   перестановкой — сломал «сколько партнёров», 2/1/3 неверных;
    #   поднятием соперника к арбитру — тоже хуже, чем без него (1/0/1).
    # Причина: по основам совпадает МНОГО названий, круг соперников расширяется, и арбитр
    # выбирает из шума.
    #
    # Убран целиком, а не оставлен «наблюдением в diag»: запрос на каждый вопрос ради числа,
    # которое ни на что не влияет, — это время ответа и ложный след для следующего читателя
    # («значит, признак работает»). Разбор с числами — `docs/DEFECT_FOCUS_CHOICE.md §9`.
    # Порядок списка — ПО СМЫСЛУ вопроса, не по числу совпадений: модель тяготеет к
    # началу списка, а число совпадений врёт (значение встречается чаще в чужой
    # сущности). Порядок — это данные (эмбеддинг названия сущности против вопроса),
    # отсечки нет: список отдаётся модели целиком.
    # ПОРЯДОК КАНДИДАТОВ — В ДВА ШАГА, И ОБА ОГРАНИЧЕНЫ СВЕРХУ.
    # Шаг 1, в базе: грубый порядок по близости метки к слову вопроса. Сигнал слабый
    # (он не связывает «продажи» с «Реализация Товаров Услуг» и ставит выше «Склады»),
    # но он бесплатный и годится как СИТО.
    # Шаг 2, моделью: реранкер оценивает пару «вопрос ↔ название» и расставляет голову
    # списка правильно. [замер 27.07] «продажи» → «Реализация Товаров Услуг» первым
    # (0,585) там, где эмбеддинг давал «Склады» (0,521).
    # 🔴 Во внешнюю модель уходит НЕ БОЛЬШЕ RERANK_TOP названий — иначе объём растёт с
    # числом сущностей базы, а это п. 19. Отсечённое видно клиенту через `partial`.
    # 🔴 СИТО НЕ ИМЕЕТ ПРАВА ВИСЕТЬ НА ОДНОМ СЛОВЕ, КОТОРОЕ ПРИДУМАЛА МОДЕЛЬ.
    # [замер 30.07] на вопрос «На какую сумму мы закупили товаров и услуг?» модель выдаёт
    # `kind` то «закупки», то «закупка» — шесть вызовов подряд: закупки, закупка, закупки,
    # закупки, закупка, закупки. Множественное число ДОСЛОВНО совпадает с именем регистра
    # `accumulationregister_закупки`, тот встаёт первым и вытесняет документ за RERANK_TOP —
    # реранкер его уже не видит. Итог: четыре отказа и два верных ответа (73 181 157,68)
    # НА ОДИН И ТОТ ЖЕ ВОПРОС при неизменных данных.
    #
    # Это нарушение сразу трёх пунктов контракта, а не вопрос вкуса:
    #   п. 3  — «детерминированно на данных»: один вопрос обязан давать один ответ;
    #   п. 19 — «моделью не ищем»: отбор ведёт код, модель нужна только для смысла. Здесь
    #           же выбор сущности решался грамматической формой слова ОТ МОДЕЛИ;
    #   п. 12 — молчаливый выбор между правдоподобными вариантами запрещён.
    #
    # Как надо (`HOW_NOT_TO §3.16`): не подкручивать порядок, чтобы нужное «обычно
    # побеждало», а СДЕЛАТЬ ВЫТЕСНЕНИЕ НЕВОЗМОЖНЫМ. Сито считается по ДВУМ входам —
    # по самому вопросу (вход стабильный, это текст человека) и по слову модели, — и
    # голова списка берётся ОБЪЕДИНЕНИЕМ вперемежку. Тогда ни один вход в одиночку не
    # может выбросить кандидата: слово модели добавляет сигнал, но больше ничего не решает.
    # Верхняя граница прежняя (RERANK_TOP), то есть объём в модель не вырос — п. 19 цел.
    top_by_question = None
    order_by_question = []
    # 🔴 ПОРЯДОК СТРОИТСЯ ПО ТОЙ ЖЕ ПОВЕРХНОСТИ, ЧТО И ОТБОР — ПО КАРТОЧКЕ (04.08).
    # Здесь решается, что вообще ДОЙДЁТ до модели: набор кандидатов пересортировывается
    # целиком, и всё, что не попало в голову, обрезается бюджетом перечня. До 04.08
    # порядок строился по вектору МЕТКИ, тогда как отбор кандидатов уже с 03.08 идёт по
    # карточке, — то есть найденное одной поверхностью раскладывалось другой, заведомо
    # более слабой (`[замер 03.08]` до реранкера доходит 70 % против 52 %).
    # `[замер 04.08]`, 44 пары приёмки, настоящие разборы шага 1: эталон доходит до
    # модели (первые ~108 записей бюджета) — по метке **42 из 44**, по карточке
    # **44 из 44**; до реранкера (первые 60) — 34 против 42. Прибор — `step3_bench.py`,
    # раздел «доставка до шага 4».
    # Откат честный: нет карточки или её векторы посчитаны другой моделью — работаем по
    # метке, как раньше (`emb_ready` без отметки говорит «нет»).
    order_src = CARD if emb_ready(CARD) else (TABLES if emb_ready(TABLES) else "")
    # 🔴 ЭМБЕДДЕР УПАЛ — ЭТО СБОЙ, А НЕ «РАБОТАЕМ БЕЗ СМЫСЛА» (05.08).
    # Когда смысловой путь выключается, порядок кандидатов остаётся по ЧИСЛУ СОВПАДЕНИЙ, а
    # этот признак пропорционален размеру сущности, а не относимости. Ответ при этом уходил
    # человеку с прежней уверенностью. Поймано пробой: под тройной нагрузкой (опыт «круг
    # арбитра всегда») эмбеддер ответил `TimeoutError`, и начиная с девятого вопроса выбор
    # выродился в служебный `informationregister_замерывремени` — ЧЕТЫРЕ неверных ответа
    # подряд, все быстрые и все уверенные (`runs/2026-08-05-step4-J-alwaysarb.txt`).
    # П. 18 `TARGET.md` требует честного поведения при сбое, а не тихой деградации.
    #
    # Различать «упал» и «векторов нет по устройству» обязательно: на базе без собранных
    # векторов `emb_ready` тоже ложна, но это НЕ сбой, и превращать там каждый вопрос в
    # уточнение нельзя. Различает `embed_model_live()` — он спрашивает сам сервис.
    meaning_down = bool(ORDER_BY_MEANING and len(cands) > 1 and not order_src
                        and not embed_model_live())
    if meaning_down:
        diag["meaning_down"] = "эмбеддер не ответил — порядок кандидатов без смысла"
    if ORDER_BY_MEANING and len(cands) > 1 and order_src:
        orders = []
        for src_text in (question, intent.get("kind")):
            if not src_text:
                continue
            try:
                orders.append([r[0] for r in psql(
                    "SELECT src_table FROM %s WHERE src_table IN (%s) "
                    "AND emb IS NOT NULL "        # см. разбор в `resolve_near`
                    # разделитель равенства: ниже порядок режется по RERANK_TOP,
                    # и без него до реранкера доходят разные сущности
                    "ORDER BY emb <=> %s, src_table"
                    % (order_src, ", ".join(lit(c) for c in cands), _vec(src_text)))])
            except RuntimeError:
                pass
        if orders:
            # Вершина по САМОМУ ВОПРОСУ — независимый от модели сигнал. Ниже он служит
            # признаком неоднозначности: если он расходится с выбором модели, вопрос
            # честно допускает несколько прочтений, и по п. 12 мы обязаны спросить.
            # Весь порядок по вопросу, а не только его вершина: если вершиной оказалась
            # СЛУЖЕБНАЯ сущность, сигнал не выбрасывается, а берётся первый деловой —
            # разбор у `signals_disagree` ниже.
            order_by_question = list(orders[0])
            top_by_question = order_by_question[0] if order_by_question else None
            # Вперемежку: первый по вопросу, первый по слову, второй по вопросу, ...
            order, seen = [], set()
            for i in range(max(len(o) for o in orders)):
                for o in orders:
                    if i < len(o) and o[i] not in seen:
                        seen.add(o[i]); order.append(o[i])
            cands = order + [c for c in cands if c not in seen]
            diag["sieve"] = len(orders)
        else:
            # Эмбеддер молчит — порядок остаётся по числу совпадений, но круг кандидатов
            # не сужается: пришедшие от синонимов сохраняются, они добыты без вектора.
            cands = sorted(by, key=lambda t: -by[t]) + [t for t in extra if t not in by]
            # Отсев «не отвечает» держится и здесь: круг пересобран из `by`/`extra`,
            # и без вычитания отсеянный сосед вернулся бы в обход правила.
            if not_for and len(cands) > len(not_for):
                cands = [c for c in cands if c not in not_for]
            # 🔴 И ЭТО ТОЖЕ ОТКАЗ СМЫСЛОВОГО ПУТИ, А НЕ «ПОРЯДОК ПО СОВПАДЕНИЯМ» (05.08).
            # Здесь `/health` эмбеддера отвечает (иначе мы бы сюда не зашли), но САМ вызов
            # эмбеддинга упал или не уложился в таймаут, `orders` пуст, и порядок кандидатов
            # задаётся числом совпадений — признаком, пропорциональным РАЗМЕРУ сущности.
            # Прежде это проходило молча, и ответ уходил с обычной уверенностью.
            # `[замер 05.08]` пять вопросов подряд («контрагенты», «организации»,
            # «документы реализации», «строки товаров», «документы приобретения») ответили
            # служебным `informationregister_замерывремени` — быстро, уверенно и неверно.
            # Проверка по `/health` этот случай НЕ ловит: она была, и она сказала «жив».
            diag["meaning_down"] = "вектор вопроса не посчитан — порядок кандидатов без смысла"
        # 🔴 НАЙДЕННОЕ ШАГОМ 3 СТОИТ ВПЕРЕДИ (04.08). Выше набор пересортирован ОДНИМ
        # сигналом — близостью вектора, — и найденное четырьмя поверхностями сразу теряет
        # своё место. А режется список бюджетом перечня: `[замер 04.08]` живой ответ отдал
        # модели 100 записей из 1502, и верная сущность стояла 106-й — то есть ошибка
        # ответа была ошибкой ДОСТАВКИ, а не выбора. Порядок внутри головы — тот, в
        # котором его отдало слияние мест; всё остальное идёт следом, как и раньше.
        # `[замер 04.08]` на 44 парах приёмки при глубине перечня как в бою: эталон
        # доходит до модели 44 из 44 против 43, до реранкера 43 против 42, и верным
        # оказывается верхний кандидат 16 раз против 10.
        # Сигнал `top_by_question` НЕ ТРОГАЕТСЯ: он выше и остаётся вершиной чистого
        # вектора — на нём стоит признак неоднозначности шага 4, и менять его смысл
        # отсюда нельзя.
        if found_by_meaning:
            in_cands = set(cands)
            head3 = [t for t in found_by_meaning if t in in_cands]
            if head3:
                seen3 = set(head3)
                cands = head3 + [c for c in cands if c not in seen3]
                diag["order_head"] = len(head3)
        head, tail = cands[:RERANK_TOP], cands[RERANK_TOP:]
        if tail:
            sb = diag.setdefault("selection_budget", {})
            sb["reranked_of"] = len(cands)
            sb["reranked"] = len(head)
        try:
            lab = {r[0]: r[1] for r in psql(
                "SELECT src_table, label FROM %s WHERE src_table IN (%s)"
                % (TABLES, ", ".join(lit(c) for c in head))) if r and r[0]}
        except RuntimeError:
            lab = {}
        keys = [c for c in head if c in lab]
        idx = rerank(question, [lab[c] for c in keys]) if keys else []
        if idx:
            best = [keys[i] for i in idx if 0 <= i < len(keys)]
            cands = best + [c for c in head if c not in best] + tail
            diag["order_by"] = "rerank"
    # РЕБЁНОК НЕ МОЖЕТ СТОЯТЬ РАНЬШЕ РОДИТЕЛЯ. Табличная часть документа и сам документ —
    # разные источники, и итог живёт в ШАПКЕ, а не в строках. Порядок по смыслу этого не
    # знает: [замер 27.07] на вопросе «какая самая крупная продажа» метки табличных
    # частей оказались ближе к слову «продажа» (0,566-0,574), чем метка документа
    # (0,600), список пошёл модели с них, и ответом стала самая крупная СТРОКА
    # накладной — 1 550 000 вместо 1 629 700. Ответ верный по числу и неверный по сути.
    # Родитель берётся из КОНТРАКТА ПЛАТФОРМЫ (составной ключ), а не из имени: в
    # `search_tables.parent` его записывает сборщик. Оба источника остаются в списке —
    # мы не решаем за модель, мы лишь не ставим часть впереди целого.
    # 🔴 Правило применяется ТОЛЬКО когда спрашивают ЧИСЛО. Оно и заводилось ради этого:
    # итог документа живёт в шапке, а не в строках. Но на вопрос «что покупало ООО
    # Ромашка» ответ как раз в СТРОКАХ — там наименования, — и правило уводило на шапку,
    # где их нет. [замер 28.07] система честно отвечала «покупало товары и услуги,
    # наименований нет», то есть правило мешало ответить.
    wants_number = bool((intent.get("measure") or "").strip()) or \
        intent.get("want") in ("sum", "count")
    if wants_number and len(cands) > 1:
        try:
            par = {r[0]: r[1] for r in psql(
                "SELECT src_table, parent FROM %s WHERE src_table IN (%s)"
                % (TABLES, ", ".join(lit(c) for c in cands))) if r and r[0]}
            ordered, placed = [], set()
            for c in cands:
                if par.get(c) in cands and par.get(c) not in placed:
                    continue                    # ребёнок ждёт, пока встанет родитель
                ordered.append(c)
                placed.add(c)
                for ch in cands:                # сразу за родителем — его части
                    if ch not in placed and par.get(ch) == c:
                        ordered.append(ch)
                        placed.add(ch)
            cands = ordered + [c for c in cands if c not in placed]
        except RuntimeError:
            pass                                # порядок остаётся прежним
    # Не подошло ничего вовсе (чужой язык, иное написание) — только тогда идём от
    # смысла вопроса к названиям всех сущностей.
    if not cands and emb_ready(TABLES):
        try:
            # LIMIT в БАЗЕ: иначе в кандидаты, а следом в промпт, уезжает вся база.
            # Число получаем из бюджета промпта, а не задаём отдельно.
            cands = [r[0] for r in psql(
                "SELECT src_table FROM %s WHERE emb IS NOT NULL "   # см. `resolve_near`
                "ORDER BY emb <=> %s, src_table LIMIT %d"
                % (TABLES, _vec(intent.get("kind") or question),
                   max(1, PICK_BUDGET // 40))) if r and r[0]]
        except RuntimeError:
            cands = list(by)
    # ВЕЛИЧИНА, О КОТОРОЙ СПРАШИВАЮТ, ДОЛЖНА У КАНДИДАТА СУЩЕСТВОВАТЬ.
    # Строка несёт ВСЕ свои числовые величины картой, поэтому проверка теперь общая:
    # у кандидата должна быть хоть одна величина. Какая именно нужна — решается уже
    # после выбора сущности (`pick_measure`), потому что имена величин у каждой свои.
    # Отбор идёт ДАННЫМИ: у сущности либо есть заполненная величина, либо нет. Ни порога,
    # ни числа, ни имени — размер и состав базы ничего не меняют (п. 9).
    # [замер 27.07] без этого правила «сколько продали в декабре» отвечалось
    # «100 000 рублей (1 запись)» вместо 2 456 400 на 6 документах: вопрос уходил
    # к сущности, у которой суммы нет вовсе. Реранкер этого не закрывает — он про то,
    # ЧТО спросили, а не про то, ЧЕМ сущность располагает.
    if intent.get("want") == "sum" and len(cands) > 1:
        try:
            with_value = {r[0] for r in psql(
                "SELECT src_table FROM %s WHERE src_table IN (%s) "
                "  AND nums IS NOT NULL AND len(map_keys(nums)) > 0 GROUP BY 1"
                % (CORPUS, ", ".join(lit(c) for c in cands))) if r and r[0]}
            if with_value:
                dropped = [c for c in cands if c not in with_value]
                cands = [c for c in cands if c in with_value]
                if dropped:
                    diag["without_value"] = len(dropped)
        except RuntimeError:
            pass
    # ВОПРОС ПРО ДЕНЬГИ — ТОЛЬКО К ТЕМ, У КОГО ДЕНЬГИ ЕСТЬ. Это отбор ДАННЫМИ, а не
    # догадкой: у сущности либо есть заполненная денежная колонка, либо нет, и та, у
    # которой её нет, ответить про сумму не может в принципе.
    # Зачем: [замер 27.07] на «What is the total amount of all sales?» модель выбирала
    # из 238 названий и брала «Поступление На Расчетный Счет». Порядок перечня задаётся
    # близостью метки к слову вопроса, а этот сигнал негоден (у «sales» ближайшее —
    # «Склады»); выключить его нельзя — без порядка модель берёт первое попавшееся
    # (проверено: выбирала «Поля Форм Статистики»). Сужение круга бьёт в причину:
    # кандидатов становится меньше, и все они по существу пригодны.
    # Отсечка не по числу и не по порогу — по НАЛИЧИЮ величины, поэтому размер базы
    # ничего не меняет (п. 9).
    if intent.get("want") == "sum" and len(cands) > 1:
        try:
            with_money = {r[0] for r in psql(
                "SELECT src_table FROM %s WHERE src_table IN (%s) "
                "  AND nums IS NOT NULL AND len(map_keys(nums)) > 0 GROUP BY 1"
                % (CORPUS, ", ".join(lit(c) for c in cands))) if r and r[0]}
            if with_money:
                dropped = [c for c in cands if c not in with_money]
                cands = [c for c in cands if c in with_money]
                if dropped:
                    diag["without_value"] = len(dropped)
        except RuntimeError:
            pass
    # ДЕТЕКТОР РАЗВИЛКИ ИЗ ДАННЫХ (по умолчанию) — сразу после того, как круг
    # кандидатов собран окончательно и условия вопроса (`match`/`preds`) известны.
    # Полный круг считается одним SQL (`fork_scan`), классы — типизированным атомом
    # (`fork_classes`). При ASK_FORK_OUTCOMES=1 (умолчание) детектор — судья
    # неоднозначности (исходы A/B/C, план §2): круг под-вызовов арбитра не собирается.
    # ASK_FORK_OUTCOMES=0 — волна-1: только `diag.fork` + старые исходы. В под-вызовах
    # (`no_arbiter`) и после доказанного билета (`trusted`) исходы не перехватывают.
    if question_asks_stock_balance(question) and stock_asks_named_product(question, intent):
        _cap_pf = balance_capable_or_registers()
        _goods_pf = balance_registers_with_goods(_cap_pf) if _cap_pf else frozenset()
        if not _cap_pf or not _goods_pf:
            diag["stock_named_pre_fork"] = True
            return stock_balance_named_no_data(question, diag, cut, t0)
    if FORK_DETECT and not no_arbiter and len(cands) > 1:
        _t_fork = time.time()
        _scan_err = None
        _rows, _cls = {}, {}
        _mword = (intent.get("measure") or "").strip()
        _fwant = (intent.get("want") or "").strip()
        # Пространство исходов — голова списка кандидатов (тот же бюджет, что круг
        # арбитра ×4), не вся база: иначе сотни несвязанных src с живым счётом
        # дают C с сотнями вариантов и секунды на SQL. Полный перечень cands —
        # по-прежнему источник отбора; детектор судит неоднозначность в голове.
        _fork_pool = prefer_entity_for_catalog_count(
            prefer_entity_for_sales(
                prefer_entity_for_rank(
                    list(cands[:max(ARBITER_MAX * 4, 16)]), intent, question),
                intent, question),
            intent, question)
        _fork_pool = event_filter_pool(_fork_pool, intent, diag)
        try:
            _mbs = _measures_by_src(_fork_pool)
            _als = _aliases_by_src(_fork_pool)
            _rel = {c: _fork_relevant(_mword, _mbs.get(c) or [], _als.get(c) or {},
                                      want=_fwant or None)
                    for c in _fork_pool}
            _rows, _cls, _readings, _cells = fork_detector_scan(
                match, preds, intent, today, _rel,
                period_from_prior=period_from_prior,
                measure_word=_mword, want=_fwant or None,
                day_basis_prefer=_day_prefer,
                amount_basis_prefer=_curr_prefer, trusted=trusted)
            _meta = getattr(fork_classes, "_meta_by_fp", {}) or {}
            _atoms = []
            for fp, ss in sorted(_cls.items(), key=lambda kv: -len(kv[1])):
                m = _meta.get(fp) or {}
                rep = sorted(ss)[0]
                d0 = m.get("row") or _rows.get(rep) or {"count": 0, "folders": 0, "sums": {}}
                _built = _fork_atom_of(
                    d0, sorted(ss), _mword, want=_fwant,
                    rel_measures=_rel.get(rep), period=m.get("period"))
                _atoms.append({"atom": _built,
                               "fingerprint": _fork_fp_diag(fp),
                               "srcs": sorted(ss),
                               "window_fp": m.get("window_fp")})
            diag["fork"] = {"classes": len(_cls),
                            "srcs": sum(len(v) for v in _cls.values()),
                            "pool": len(_fork_pool),
                            "pool_srcs": list(_fork_pool),
                            "live_srcs": sorted(_rows.keys()),
                            "readings": len(_readings),
                            "window_cells": (len(_cells) if _cells else None),
                            "excluded": _fork_pool_excluded(_fork_pool, _rows) or None,
                            "atoms": _atoms[:10],
                            "atoms_truncated": max(0, len(_atoms) - 10) or None,
                            "cost_ms": int((time.time() - _t_fork) * 1000)}
            _fork_early["rows"] = _rows
            _fork_early["cls"] = _cls
            _fork_early["rel"] = _rel
            _fork_early["pool"] = _fork_pool
            шаг("детектор развилки", классов=len(_cls),
                веток=diag["fork"]["srcs"], счёт_мс=diag["fork"]["cost_ms"])
            if len(_cls) > 1:
                _fork_log(_cls, _mword or (intent.get("want") or ""))
        except Exception as _e:                         # noqa: BLE001
            _scan_err = _e
            diag["fork_error"] = str(_e)[:160]
            sys.stderr.write("ask FORK: детектор не сработал: %s\n" % str(_e)[:160])
    # ASK_ENTITY_FORM: форма F до выбора сущности моделью (K6).
    # pre_entity + classes>1 = молчаливый лидер — гейт в try_entity_form_answer.
    # Пул F — все catalog_/register_/document_ из cands (без head-среза круга).
    _ecp0 = try_event_count_period_clarify(
        question, intent, diag, cut, t0, today=today, pool=list(cands or []),
        trusted=trusted, resolved=resolved)
    if _ecp0 is not None:
        return _ecp0
    if ASK_ENTITY_FORM and not no_arbiter and not trusted and not focus:
        _ef_pool0 = list(dict.fromkeys(
            list((_fork_early.get("pool") or []))
            + [c for c in (cands or []) if str(c).startswith("catalog_")]
            + [c for c in (cands or [])
               if str(c).startswith("accumulationregister_")
               or str(c).startswith("document_")]))
        _ef0 = try_entity_form_answer(
            question, intent, _ef_pool0, match=match, diag=diag, cut=cut, t0=t0,
            today=today, when="pre_entity",
            early_classes=(diag.get("fork") or {}).get("classes") or 0)
        if _ef0 is not None:
            шаг("форма сущности", form=((_ef0.get("diag") or {}).get("entity_form")),
                when="pre_entity")
            return _ef0
    # «почему ноль / сбой» + канон excluded no_live_cells → period_empty ДО выбора
    # сущности/меры ([замер 22.08 okna]: курсы валют live, регистр пуст → clarify).
    if (not no_arbiter and not focus
            and not entity_choice_locked(trusted, resolved)
            and (period_zero_why_question(question)
                 or diag.get("about_coverage_refused") == "period_zero_why")
            and sales_sum_intent(intent, question)
            and (diag.get("fork") or {}).get("excluded")):
        _sfpe0 = try_sales_fork_period_empty_answer(
            question, intent, diag, cut, t0, cands, diag.get("fork"))
        if _sfpe0 is not None:
            шаг("канон продаж: fork excluded → period_empty (до выбора)",
                src=diag.get("sales_fork_period_empty"))
            return _sfpe0
    # Параметры подсчёта, названные моделью: сущность, величина, что считать. Объявляются
    # ДО ветвления, чтобы ни один путь не оставил их неопределёнными.
    plan = {}
    # sales_sum: sticky focus/память на документ ≠ канон — снять до focus_forced
    # ([замер 21.08] возврат 11: июль 0 на передаче ТМЦ при 2.7M на регистре).
    focus, trusted, resolved, _sales_clr = sales_refuse_sticky_focus(
        focus, trusted, resolved, intent, question, cands)
    if _sales_clr:
        diag["sales_canon_refused_focus"] = _sales_clr
        шаг("канон продаж: снят sticky focus", было=_sales_clr["было"],
            стало=_sales_clr["стало"])
    # ВЫБОР ЧЕЛОВЕКА ПОСЛЕ УТОЧНЕНИЯ важнее догадки: если задан `focus` и такая сущность
    # реально под условиями что-то содержит — берём её и не спрашиваем модель.
    if focus:
        focus = resolve_focus(focus, diag)
    _settled_src = (resolved or {}).get("src") or (
        (trusted or {}).get("src") if entity_choice_locked(trusted, resolved) else None)
    _hold_src = [h["src"] for h in holders_of_target(_settled_src or "")] if (
        entity_choice_locked(trusted, resolved) and _settled_src) else []
    _held = hold_settled_entity(
        focus, trusted, resolved, found_by=by, measure_pick=measure_pick,
        holder_srcs=_hold_src)
    if _held != focus:
        шаг("сущность снята — осталась", было=(focus or "—"), осталось=_held)
        diag["entity_held"] = {"было": focus, "осталось": _held}
        focus = _held
    axis_plan = None
    if focus:
        axis_plan = axis_focus_plan(
            focus, intent, measure_pick, match, preds, kid_pred, diag,
            trusted=trusted, resolved=resolved)
    if axis_plan and axis_plan[0] == "clarify":
        _srcs, _live = axis_plan[1], axis_plan[2]
        try:
            _lab = {r[0]: r[1] for r in psql(
                "SELECT src_table, label FROM %s WHERE src_table IN (%s)"
                % (TABLES, ", ".join(lit(c) for c in _srcs))) if r and r[0]}
        except RuntimeError:
            _lab = {}
        _opts = mk_opts(_srcs, _lab, {}, by, match=match, preds=preds, live=_live)
        if len(_opts) >= 2:
            шаг("focus был осью — уточнить держателя", сколько=len(_opts))
            return {"partial": cut or None, "kind": "clarify",
                    "text": clarify_say(question, _opts, diag)
                            or ", ".join("«%s»" % o["label"] for o in _opts),
                    "options": _opts, "sources": [o["label"] for o in _opts],
                    "diag": _diag_pack(diag, sec=round(time.time() - t0, 2))}
        if len(_opts) == 1:
            _s = _opts[0]["src"]
            _col = next((h["col"] for h in holders_of_target(focus) if h["src"] == _s),
                        "")
            axis_plan = ("holder", _s, _col)
        else:
            axis_plan = None
    if axis_plan and axis_plan[0] == "holder":
        if entity_choice_locked(trusted, resolved):
            axis_plan = None
        else:
            _hold, _acol = axis_plan[1], axis_plan[2]
            diag["focus_was_axis"] = {"было": focus, "стало": _hold, "ось": _acol}
            шаг("focus был осью", было=focus, стало=_hold, ось=(_acol or "—"))
            focus = _hold
    if focus:
        picked, marks, plan = [focus], {}, {}
        diag["focus_forced"] = focus
        # Код-терм (счёт, ОКВЭД) при ВЫБРАННОЙ сущности фильтруется иерархическим префиксом
        # безопасно: сущность уже определена, спутать её с чужой нельзя. Дот-граница
        # отсекает лишнее (счёт «62» ≠ сумма «624000»): [замер] по регистру ровно 147
        # движений, сумма сходится с 1С. В одношаговом ответе этот префикс давал ошибочный
        # выбор сущности — поэтому он живёт ТОЛЬКО на выбранной человеком.
        code_filter = None
        for group in (intent.get("terms") or []):
            for alt in group:
                a = alt.strip()
                if a and any(c.isdigit() for c in a) and "." not in a and len(a) <= 12:
                    code_filter = ("(doc @@ ts_starts_with(%s) OR doc @@ ts_phrase(%s))"
                                   % (lit(a.lower() + "."), lit(a)))
                    break
            if code_filter:
                break
        if code_filter:
            # Префикс кода СТАНОВИТСЯ `match`. Буквальный «62» точной фразой по выбранной
            # сущности дал бы ноль. `match` (а не `preds`) — потому что по нему запросы
            # идут по ИНДЕКСУ, где только и работают `ts_*`; с пустым match они ушли бы в
            # корпус и упали («TSQUERY outside @@ match»).
            match = code_filter
    else:
        _ev = try_event_code_entity_pick(
            question, intent, cands, diag, cut, t0, by, match, preds, {})
        if _ev and _ev.get("kind") in ("no_data", "clarify"):
            return _ev
        if _ev and _ev.get("picked"):
            picked, marks, plan = _ev["picked"], _ev.get("marks") or {}, _ev.get("plan") or {}
            diag["event_code_pick"] = True
        else:
            _ct = try_count_theme_code_pick(
                question, intent, cands, diag, cut, t0)
            if _ct and _ct.get("picked"):
                picked = _ct["picked"]
                marks, plan = {}, {}
                diag.update(_ct.get("diag") or {})
            else:
                try:
                    picked, marks, plan = pick_entity(question, intent.get("kind"), cands,
                                                      counts_for_model, match, diag)
                except RuntimeError:
                    picked, marks, plan = [], {}, {}
                    diag["degraded"] = "выбор сущности сделан без модели"

        # КОД С ИЕРАРХИЕЙ — НЕОДНОЗНАЧНОСТЬ, КОТОРУЮ РЕШАЕТ ЧЕЛОВЕК. «62» — это и номер
        # формы статистики, и счёт: буквальный поиск ведёт к форме, а иерархический
        # префикс `62.` — к регистру бухучёта. Судить, что имел в виду человек, по числу
        # нельзя. Раньше система молча брала форму и отвечала «нет оборотов». Теперь: если
        # у кода есть держатели через `62.`, которых буквальный поиск НЕ дал, — предлагаем
        # выбор (форма / регистр), и по выбору (`focus`) считаем верно. Порядок п. 21.
        code_terms = [a.strip() for g in (intent.get("terms") or []) for a in g
                      if a.strip() and any(c.isdigit() for c in a) and "." not in a
                      and len(a.strip()) <= 12]
        if code_terms and not focus:
            holders = {}
            for r in psql(" UNION ALL ".join(
                    "SELECT src_table, count(*) n FROM %s WHERE doc @@ ts_starts_with(%s) "
                    "GROUP BY 1" % (INDEX, lit(c.lower() + ".")) for c in code_terms[:2])):
                try:
                    holders[r[0]] = holders.get(r[0], 0) + int(r[1])
                except (ValueError, IndexError):
                    continue
            extra = [t for t in sorted(holders, key=lambda x: -holders[x])[:3]
                     if t not in by and t not in picked and t not in not_for]
            if extra:
                picked = list(dict.fromkeys((picked or []) + extra))
                diag["code_ambiguous"] = extra

    if picked and not entity_choice_locked(trusted, resolved):
        picked = align_picked_to_terms(picked, cands, intent, diag)

    # 🔴 РАСХОЖДЕНИЕ НЕЗАВИСИМЫХ СИГНАЛОВ — ЭТО И ЕСТЬ НЕОДНОЗНАЧНОСТЬ.
    # [замер 30.07] реранкер на вопрос «На какую сумму мы закупили товаров и услуг?»
    # пять раз подряд ставит первым «Суммы Документов В Валюте Регл» — по совпадению слов
    # «сумма»/«документов», — а верное «Приобретение Товаров Услуг» кладёт ПОСЛЕДНИМ.
    # При этом порядок хвоста у него от вызова к вызову разный (позиции 2-4 переставляются),
    # то есть на его единоличный выбор опираться нельзя ни по правильности, ни по
    # воспроизводимости (п. 3). Вектор при этом детерминирован: одно слово — один вектор.
    #
    # Отсюда правило, не требующее ни порога, ни знания базы: если вершина по САМОМУ
    # ВОПРОСУ (считает база) не совпала с выбором модели — это два равноправных прочтения,
    # и п. 12 прямо запрещает выбирать между ними молча. Спрашиваем человека готовым
    # механизмом уточнения (кнопки + «свой вариант», решение владельца 28.07).
    #
    # Это не «уточнять почаще на всякий случай»: пока оба сигнала согласны — ответ идёт
    # без вопроса, как и требует порядок п. 21 (ответ → уточнение → отказ).
    # 🔴 ОДНА СЕМЬЯ — ЭТО ОДНО ПРОЧТЕНИЕ, А НЕ ДВА. Табличная часть и её шапка (`Партнеры`
    # и `Партнеры_КонтактнаяИнформация`) — не два смысла вопроса, а одна сущность и её же
    # часть. Без этой оговорки система спрашивала лишнее: [замер 30.07] «Какой ИНН у
    # Нептун?» → «из карточки партнёра или из контактной информации?», хотя прочтение одно.
    # Родство приходит из данных (`search_tables.parent`), а не из разбора имени.
    # Указание владельца 30.07 требует спрашивать при СОМНЕНИИ; лишний вопрос там, где
    # сомнения нет, — не осторожность, а шум, и он обесценивает настоящие уточнения.
    # Родство нужно ДВУМ проверкам ниже — и признаку неоднозначности, и подбору соперника
    # для арбитра, — поэтому берётся один раз и на весь круг кандидатов, которых мы можем
    # рассматривать. Без этого `_family` молча возвращала бы саму сущность, и в соперники
    # арбитру попадала бы табличная часть той же шапки: два ответа об одном и том же.
    # Сомнение считается ниже, но объявляется здесь: его читает `_alias_verdict`, а тот
    # определён раньше по тексту. Так порядок определений не решает поведение молча.
    doubt = False
    par = {}
    writer = {}
    служебные = set()
    if picked:
        need = set(picked) | set(cands[:ARBITER_MAX * 4]) | set(order_by_question[:8])
        if top_by_question:
            need.add(top_by_question)
        # 🔴 СЛУЖЕБНАЯ СУЩНОСТЬ — НЕ ВТОРОЕ ПРОЧТЕНИЕ ДЕЛОВОГО ВОПРОСА (05.08).
        # Разметку делает такт (`classify_entities.py`, модель отвечает «о чём спрашивают»
        # или «служебное»), она лежит в базе на ВСЕ 1502 сущности и не зависит ни от языка,
        # ни от имён: списка слов и разбора имени («constant_…») здесь нет намеренно —
        # это была бы привязка к нашей конфигурации. Неразмеченное считается деловым, как и
        # в самой разметке, поэтому на базе без неё поведение прежнее.
        # Зачем: `[замер 05.08]` вопрос «Сколько у нас партнёров?» отвечался ВЕРНО (164),
        # но в круг арбитра попадали две константы настроек с ответом «1», числа честно
        # расходились (164 против 1 против 1), и детектор превращал верный ответ в
        # уточнение. Это и есть шум в круге соперников, а не два прочтения.
        try:
            служебные = {r[0] for r in psql(
                "SELECT src_table FROM %s WHERE cls = 'service' AND src_table IN (%s)"
                % (CLASS_TABLE, ", ".join(lit(c) for c in need))) if r and r[0]}
        except RuntimeError:
            служебные = set()          # базы без разметки — соперников не отсеиваем
        try:
            # `written_by` — «какой документ пишет этот источник», заведено подготовкой базы
            # 05.08 (`corpus_build.sql`, раздел 2-тер). Это ЕДИНСТВЕННЫЙ сигнал шага 4,
            # который не является названием: метка, вектор метки и карточки, реранкер и
            # словарь синонимов — все про имя, а регистр накопления в 1С назван деловым
            # языком («Закупки»), документ — канцелярским («Приобретение Товаров Услуг»), и
            # человек спрашивает деловым. Поэтому именные сигналы дружно подтверждали
            # регистр, а показ модели вида записи `[замер 04.08]` сделал хуже (3 → 6).
            par, writer = {}, {}
            for r in psql(
                "SELECT src_table, parent, written_by FROM %s WHERE src_table IN (%s)"
                    % (TABLES, ", ".join(lit(c) for c in need))):
                if not r or not r[0]:
                    continue
                par[r[0]] = (r[1] or "")
                if len(r) > 2 and r[2]:
                    writer[r[0]] = r[2]
        except RuntimeError:
            # Старая база без колонки — работаем как до 05.08, а не падаем.
            par, writer = {}, {}
            try:
                par = {r[0]: (r[1] or "") for r in psql(
                    "SELECT src_table, parent FROM %s WHERE src_table IN (%s)"
                    % (TABLES, ", ".join(lit(c) for c in need))) if r and r[0]}
            except RuntimeError:
                par = {}

    def _family(t):
        return par.get(t) or t

    def _alias_verdict(cand):
        """Подтверждает ли собственное знание базы, что отвечать надо ЭТОЙ сущностью.

        🔴 ПРОВЕРКА ОБЯЗАНА СТОЯТЬ НА ИТОГОВОМ ВЫБОРЕ, А НЕ НА ПРОМЕЖУТОЧНОМ. [замер 30.07]
        прежде она стояла ниже арбитра, а обе ветки арбитра возвращают ответ раньше — то
        есть на всяком пути, где ответ вообще собрался, проверка не выполнялась. Вместе с
        отсутствующим правом `SELECT` (см. `corpus_init.sql`) это давало защиту, не
        работавшую НИ РАЗУ.

        Опора относительная: подтверждена та сущность, чьи алиасы совпали с вопросом
        ЛУЧШЕ ВСЕХ, а не всякая, у которой нашлось общее слово. Разбор чисел — у места
        вызова. Поиск ведёт база (п. 19): алиасы — такая же поисковая поверхность, как
        названия, и до этой правки они никого не приводили, только проверяли.

        Возвращает (supported, alias_top). `supported=True` при отсутствии знания — это
        не одобрение, а признание, что проверять нечем.
        """
        try:
            # 🔴 СОБСТВЕННОЕ НАЗВАНИЕ СУЩНОСТИ — ТОЖЕ ЕЁ СЛОВО, И БРАТЬ ЕГО НАДО ИЗ ДАННЫХ.
            # [замер 30.07] после перегенерации алиасов модель описала справочник
            # номенклатуры по смыслу — «товар, услуга, работа, артикул, вес товара» — и
            # выкинула слово «номенклатура». Подтверждения не нашлось, и ВЕРНЫЙ ответ
            # «227 позиций» превратился в уточнение. Спрашивать модель о том, как
            # называется сущность, незачем: название лежит в `search_tables.label`.
            # Это устраняет целый класс провалов по построению: что бы модель ни забыла
            # написать, своё имя сущность не теряет.
            r = psql(
                "WITH w AS ("
                "  SELECT trim(u.w) AS t FROM search_entity_alias a, "
                "         unnest(str_split(a.aliases, ',')) AS u(w) WHERE a.src_table = %s"
                "  UNION ALL SELECT label FROM %s WHERE src_table = %s) "
                "SELECT count(*) FILTER (t <> ''), "
                "       count(*) FILTER (t <> '' "
                "         AND list_has_any(ts_lexize(%s, t), ts_lexize(%s, %s))) FROM w"
                % (lit(cand), TABLES, lit(cand),
                   lit(STEM_DICT), lit(STEM_DICT), lit(question)))
            known, hit = (int(r[0][0] or 0), int(r[0][1] or 0)) if r and r[0] else (0, 0)
        except RuntimeError as e:
            diag["alias_unreadable"] = str(e)[:120]
            return True, []
        if not known:
            # Про ЭТУ сущность знания нет — требовать подтверждения нечем. Так выглядит
            # база, где вики не собрана: [замер] в первой базе алиасов 0.
            diag["alias_no_evidence"] = True
            return True, []
        if hit and not ALIAS_VETO:
            return True, []
        # Соперников подбираем ПО ВОПРОСУ, штатным ранжированием движка
        # (`tfidf` учитывает редкость слова: «сколько» весит мало, «поставщикам» много).
        # Свой счёт совпадений здесь стоял и был отвергнут замером — он считал ВСЕ общие
        # слова, поэтому «сколько записей в справочнике» совпадало с чем угодно.
        # 🔴 РАЗДЕЛИТЕЛЬ РАВЕНСТВА — см. врезку у `_fetch`: без него `ORDER BY … LIMIT`
        # оставляет порядок равных на волю исполнения. Здесь это дороже, чем там: `top[0]`
        # решает вето, `top[:2]` становятся вариантами уточнения, то есть ничья решает
        # ВЫБОР СУЩНОСТИ. [замер 03.08] на боевом скорере (`tfidf`, `ut_test`) ничьих в
        # первой восьмёрке 3-5 на каждом из семи вопросов приёмки, и у шести из семи на
        # ничью попадает САМ СРЕЗ `LIMIT 8` — то есть произволен и состав восьмёрки.
        # Разделитель — `src_table`: ключ `alias_idx` уникален (697 строк, 697 значений),
        # значит порядок становится полным. Это штатное предписание движка, а не наш приём:
        # доки, Indexes › Inverted › Ranking › Tie-breaking — «Add further ORDER BY columns
        # after the scorer for a deterministic order — typically the primary key».
        # 🔴 ЛИДЕР ИЩЕТСЯ ПО ТЕКСТУ ВОПРОСА, И ЭТО ИЗВЕСТНАЯ СЛАБОСТЬ, А НЕ ЗАМЫСЕЛ.
        # Скорер считает совпадение по всем словам вопроса, включая «сколько», «у», «нас»:
        # `[замер 05.08]` лидером ТРЁХ разных вопросов («сколько у нас партнёров»,
        # «…организаций», «…складов») стал один и тот же регистр «Принятая Возвратная Тара» с
        # одинаковой оценкой 12,49 — в его словаре есть фраза «сколько тары у нас». Верные
        # ответы (164 партнёра, 5 организаций, 17 складов) вето отвергло именно так.
        # Форма «искать по ПОНЯТИЯМ вопроса» (та же поверхность, которой идёт отбор —
        # `alias_hits`) проверена и НЕ помогает: по понятию «партнёров» верный
        # `catalog_партнеры` не входит в восьмёрку вовсе, по «организаций» стоит седьмым.
        # Значит чинить надо словарь синонимов, а не запрос к нему (`ASK_ALIAS_BY_CONCEPTS`
        # оставлен, чтобы обе формы мерились одной командой; разбор — `HOW_NOT_TO §1.57`).
        try:
            if ALIAS_BY_CONCEPTS:
                top = [(t, 0.0) for t in alias_hits(exprs_all, ALIAS_TOP)]
            else:
                top = [(r[0], float(r[1])) for r in psql(
                    "SELECT src_table, %s FROM %s WHERE aliases @@ %s"
                    " ORDER BY 2 DESC, src_table LIMIT %d"
                    % (SCORERS.get(SCORER, SCORERS["bm25"]) % ALIAS_INDEX, ALIAS_INDEX,
                       lit(question), ALIAS_TOP)) if r and r[0]]
        except RuntimeError:
            top = []
        # 🔴 ОТСЕЯННЫЙ «НЕ ОТВЕЧАЕТ» НЕ МОЖЕТ БЫТЬ ЛИДЕРОМ СЛОВАРЯ (06.08, вечер).
        # Вето сравнивает выбор с лидером ранжирования, а лидера ВНЕ круга кандидатов
        # считает «словарь один против всех» и пропускает выбор. Отсев убирает сущность
        # из круга — и [замер 06.08] на вопросе «Кто нам поставляет товар?» это разоружило
        # проверку целиком: лидер «Заказы Поставщикам» был отсеян по делу (сам пишет, что
        # поставщиков не ведёт), его место в круге стало -1, вето молча пропустило, и
        # неверный ответ ушёл уверенным. Сущность, отсеянная как непригодная ОТВЕЧАТЬ,
        # непригодна и ЭТАЛОНОМ сравнения — лидер ищется среди оставшихся.
        if not_for:
            skipped = [t for t, _s in top if t in not_for]
            if skipped:
                diag["alias_top_not_for"] = skipped
                top = veto_top_without(top, not_for)
        miss = [t for t, _ in top if t not in par]
        if miss:
            try:
                par.update({r[0]: (r[1] or "") for r in psql(
                    "SELECT src_table, parent FROM %s WHERE src_table IN (%s)"
                    % (TABLES, ", ".join(lit(t) for t in miss))) if r and r[0]})
            except RuntimeError:
                pass
        diag["alias_top"] = [t for t, _ in top[:4]]

        # Места в ОБЩЕМ порядке кандидатов (шаг 3: буквальный отбор, смысл, карточка,
        # реранкер). Именно их сравнивает вето: место выбора против места лидера словаря.
        # Семьями, а не сущностями — шапка и её табличная часть это одно прочтение.
        _по_семьям = [_family(c) for c in cands]

        def _место(t):
            try:
                return _по_семьям.index(_family(t))
            except ValueError:
                return -1

        def _probe(ok, why):
            """След для замера: из чего СЧИТАЕТСЯ каждая форма правила. Решений не принимает."""
            if PROBE:
                diag.setdefault("alias_probe", []).append({
                    "cand": cand, "known": known, "hit": hit, "ok": bool(ok), "why": why,
                    "top": [[t, round(s, 3)] for t, s in top[:4]],
                    "leader": top[0][0] if top else "",
                    "место_выбора": _место(cand),
                    "место_лидера": _место(top[0][0]) if top else -1,
                    "cand_rank": next((i for i, (t, _s) in enumerate(top)
                                       if _family(t) == _family(cand)), -1)})
            return ok
        # 🔴 ЖЁСТКАЯ ФОРМА — ПОД ВЫКЛЮЧАТЕЛЕМ, И ЭТО НЕ ОСТОРОЖНОСТЬ, А ЗАМЕР.
        # Решение владельца 30.07: когда вопросу отвечает несколько РАЗНЫХ объектов —
        # всегда переспрашивать. Но [замер 30.07] на прежних алиасах жёсткая форма дала
        # 1 улучшение против 3 ухудшений: верный ответ «227 позиций» превращался в
        # уточнение, потому что данные были слабее механизма — на «сколько у нас
        # партнёров» лучшим совпадением шла «Принятая Возвратная Тара».
        # Включать только после замера, что база подсказывает верно.
        # Семьи схлопываются: шапка и её табличная часть — одно прочтение, а не два.
        # Числа тут НЕТ намеренно. Первая версия писала «среди трёх лучших семей», и это
        # подгонка: тройка взялась из нашей базы, а на чужой ничего не значит. Ревизор
        # поймал её до коммита. Согласие определяется без порога: подтверждает ЛИДЕР
        # ранжирования, и решает его база, а не константа в коде. Совпали семьи —
        # отвечаем; разошлись — объектов несколько, и человек выбирает сам.
        # Сама форма правила — в `alias_supported` (там же её таблица истинности, разбор
        # смягчения и числа, которыми оно отвергнуто). Здесь остаётся только то, что без
        # базы не делается: спросить знание и подобрать соперников для уточнения.
        # `сомнение` считается раньше по тексту (модель назвала несколько, сигналы
        # разошлись, нашлась пара «регистр ← документ», отказал смысловой путь). Здесь оно
        # решает, доступна ли вторая попытка: там, где спор ЕСТЬ, спрашивает п. 12.
        ok = alias_supported(known, hit, _family(cand),
                             _family(top[0][0]) if top else "",
                             rank_cand=_место(cand),
                             rank_leader=_место(top[0][0]) if top else -1,
                             undisputed=not doubt)
        return _probe(ok, "лидер" if top else "своё слово"), top

    def _alias_clarify(cand, top):
        """Список для человека: лучшие по вопросу, по одному представителю от семьи."""
        seen, rivals = {_family(cand)}, []
        for t, _n in top:
            if t == cand or _family(t) in seen:
                continue
            seen.add(_family(t)); rivals.append(t)
        opts_src = [cand] + rivals[:2]
        try:
            lab_by = {r[0]: r[1] for r in psql(
                "SELECT src_table, label FROM %s WHERE src_table IN (%s)"
                % (TABLES, ", ".join(lit(c) for c in opts_src))) if r and r[0]}
        except RuntimeError:
            return None
        if len(opts_src) < 2 or not lab_by:
            return None
        # `distinct_by` — обязательное поле: `clarify_text` читает его без `get`. Прежняя
        # копия правила его НЕ клала, то есть при первом же выполнении упала бы с
        # `KeyError('distinct_by')`. Это ещё одно доказательство, что она не работала ни
        # разу: путь, который никогда не исполнялся, донёс до продукта и дефект прав, и
        # дефект формы данных.
        opts = mk_opts([t for t in opts_src if t in lab_by], lab_by, marks, by, match=match, preds=preds)
        if len(opts) < 2:
            return None
        diag["unsupported_pick"] = cand
        return {"partial": cut or None, "kind": "clarify",
                "text": clarify_say(question, opts, diag),
                "options": opts, "sources": [o["label"] for o in opts],
                "diag": _diag_pack(diag, sec=round(time.time() - t0, 2))}
    # 🔴 ОДНА СЕМЬЯ — НЕ ОДНО ПРОЧТЕНИЕ. Здесь стояло `_family(top) not in {_family(x)…}`:
    # если вершина по вектору оказывалась ШАПКОЙ ИЛИ СОСЕДНЕЙ ТАБЛИЧНОЙ ЧАСТЬЮ того же
    # документа, расхождение сигналов не считалось расхождением вовсе, сомнение не
    # поднималось, арбитр не запускался — и ответ уходил человеку молча.
    #
    # Посылка «шапка и её табличная часть — одно прочтение» опровергнута замером `[03.08]`,
    # сплошной перебор по боевой базе: из 186 пар «семья + одноимённая величина» у двух и
    # более членов **126 (68 %) расходятся числом**. Порознь ещё хуже там, где ошиблись:
    #   шапка ↔ табличная часть  —  38 из 71  (54 %);
    #   табличная ↔ табличная    — 195 из 249 (**78 %**).
    # Вопрос 6 приёмки — ровно второй случай: «Виды Запасов» дали 327 против 92 683 у
    # «Товаров» ТОГО ЖЕ документа, и оба — одна семья.
    #
    # Поднять сомнение безопасно: оно лишь заводит второго кандидата в круг арбитра, а
    # арбитр-детектор (задача 17) спрашивает человека ТОЛЬКО если посчитанные числа
    # разошлись. Совпали — ответ уходит как прежде. То есть цена — счёт, а не лишние
    # уточнения. Замеры 30.07, на которых держится осторожность («партнёры», «организации»),
    # это не задевает: у справочников табличных частей нет, семья состоит из них одних.
    # 🔴 ОГОВОРКА `top_by_question in by` СНЯТА (04.08). Она осталась от той поры, когда
    # кандидаты приходили ТОЛЬКО буквальным отбором. С 03.08 поверхностей три, и пришедшие
    # смыслом или синонимом живут в `extra`, а в `by` не попадают никогда. Значит такого
    # кандидата модель выбрать могла, а ОСПОРИТЬ чужой выбор он не мог: сомнение не
    # поднималось, арбитр-детектор не запускался, человека не спрашивали — и неверный
    # ответ уходил уверенным. Это и есть `сомнение=False` у трёх ошибок прогона 03.08.
    # [замер 04.08] прибором `rival_reach_bench.py` на 44 парах приёмки: буквально эталон
    # находится у 5 (11 %), синонимом у 18 (41 %) — то есть у 39 из 44 (89 %) права
    # оспорить не было вовсе, при том что до перечня эталон доходит в 44 случаях из 44.
    # 🔴 И ЗДЕСЬ ТОЖЕ: СЛУЖЕБНАЯ СУЩНОСТЬ НЕ ОСПАРИВАЕТ ВЫБОР (05.08). Вершина по смыслу
    # вопроса — сигнал сильный, но `[замер 05.08]` в 9 случаях из 27 она указывала на
    # настройку («Использовать несколько складов» на вопрос «сколько у нас складов»):
    # слово в названии есть, прочтения — нет. Такое расхождение поднимало сомнение,
    # заводило настройку в круг арбитра ОТВЕЧАЮЩИМ кандидатом, её «1» расходилось с
    # настоящим числом, и верный ответ уходил уточнением. Правило то же, что у соперников
    # ниже, и держится теми же данными (`search_entity_class`).
    # 🔴 СЛУЖЕБНАЯ ВЕРШИНА ПО СМЫСЛУ ГАСИТ СИГНАЛ, А НЕ ЗАМЕНЯЕТСЯ СЛЕДУЮЩЕЙ (05.08, вечер).
    # Замена на первую ДЕЛОВУЮ запись того же порядка выглядела точнее — сигнал ведь звучит
    # «вершина по смыслу», а служебная сущность прочтением не является. Проверено прогоном и
    # ОТВЕРГНУТО: `[замер 05.08]` первой деловой оказывается очередная настройка, размеченная
    # `business` по ошибке разметки («Использовать партнёров как контрагентов» на вопрос
    # «сколько у нас партнёров», «Организация, на которую зарегистрирована программа» — на
    # «сколько у нас организаций»). Верные ответы №8, 10, 11, 12 из ВЕРНО снова стали
    # уточнением, а ни одной ошибки замена не поймала. Шум заменился шумом.
    if (SIGNAL_DISAGREE and top_by_question and picked and not focus
            and top_by_question not in picked
            and not (SKIP_SERVICE_RIVALS and top_by_question in служебные)):
        diag["signals_disagree"] = top_by_question
        if _family(top_by_question) in {_family(x) for x in picked if x != top_by_question}:
            diag["signals_disagree_same_family"] = True
        # При исходах A/B/C и одном классе детектора расхождение сигналов само по себе
        # не создаёт вопрос человеку (план §3 / шаг 4): класс один → ответ; несколько
        # уже ушли в B/C выше. Запись в diag — для замера шага 5.
        if not (FORK_OUTCOMES and (diag.get("fork") or {}).get("classes") == 1):
            picked = list(dict.fromkeys(picked + [top_by_question]))

    # НЕОДНОЗНАЧНЫЙ ВОПРОС — спрашиваем человека, а не угадываем за него.
    # Судья неоднозначности — модель: она видит и названия, и отличительные реквизиты
    # каждого источника, и сама говорит, когда вопрос честно допускает несколько
    # прочтений. Порога тут нет и быть не может: «одинаково ли подходят» — вопрос
    # языковой, а не числовой. Замеренный случай: «что покупало ООО Ромашка» — у двух
    # источников ровно по 3 совпадения, и оба ответа следуют из данных (контрагент и
    # покупал товары, и платил). Прежде система молча брала один.
    # 🔴 АРБИТРУ НУЖНЫ ДВА ОТВЕТА, А МОДЕЛЬ ЧАСТО УВЕРЕННО НАЗЫВАЕТ ОДИН — И ОШИБАЕТСЯ.
    # [замер 30.07] «сколько приобретений товаров и услуг»: `picked` из одного элемента, и
    # это то `Приобретение Товаров Услуг` (249, верно), то `Корректировка Приобретения`
    # (3, неверно). Арбитр в такой ветке не запускался вовсе и помочь не мог.
    # Поэтому соперник ДОБАВЛЯЕТСЯ: следующий по порядку отбора кандидат, у которого есть
    # свои совпадения и который не из той же семьи (шапка/табличная часть — одно прочтение).
    # Порядок отбора — данные (близость вектора, затем реранкер), а не список имён.
    # 🔴 АРБИТР — ТОЛЬКО ТАМ, ГДЕ ЕСТЬ СОМНЕНИЕ. Владелец 30.07: «лучше 1, 2, 3 раза уточнить,
    # ЕСЛИ НЕПОНЯТНО» и «в таких ситуациях даём арбитру выбор». Не в каждой ситуации.
    #
    # [замер 30.07] когда соперник придумывался ВСЕГДА, сломались вопросы, отвечавшие верно:
    # «сколько партнёров» и «сколько организаций». Арбитру подсовывали соперника там, где
    # выбор однозначен, и он иногда выбирал соперника. Сомнение обязано быть НАЙДЕНО, а не
    # создано мной ради запуска арбитра.
    #
    # Что считается сомнением (оба признака — из данных, ни одного порога):
    #   1. модель назвала БОЛЬШЕ ОДНОЙ сущности — она сама видит несколько прочтений;
    #   2. вершина по вектору САМОГО ВОПРОСА (считает база) не совпала с выбором модели и не
    #      из той же семьи (шапка и её табличная часть — одно прочтение).
    #   3. 🔴 (05.08) выбран источник, движения которого ПИШЕТ документ, и этот документ —
    #      не тот же источник. Регистр накопления и документ-регистратор это ОДИН факт,
    #      записанный дважды: «Закупки» пишет «Приобретение Товаров Услуг» (доля 0,759),
    #      «Заказы Клиентов» — «Заказ Клиента» (0,723). Ровно на этой паре шаг 4 ошибался
    #      молча: `[замер 05.08]` из трёх оставшихся неверных ответов боевой сборки два —
    #      она, и у обоих в следе «защита не сработала ни одна».
    #
    #      🔴 ПОРОГА ПО ДОЛЕ ЗДЕСЬ НЕТ НАМЕРЕННО. Доля преобладающего регистратора —
    #      число из данных (`[замер 05.08]` у 70 регистров из 81 регистраторов больше
    #      одного, медиана 0,56), и отсечка по ней была бы константой, подобранной под нашу
    #      базу (п. 9). Поэтому связь не решает, а лишь ЗАВОДИТ второе прочтение в круг
    #      арбитра: спрашивает человека арбитр-детектор и только тогда, когда посчитанные
    #      числа разошлись. Сошлись — ответ уходит как прежде, цена правила равна счёту.
    # Канон «продали»: регистр движений, не выбор модели и не книга НДС.
    # Документ-регистратор в writer_pair не заводим — люк только по focus.
    if (not focus and not no_arbiter
            and not entity_choice_locked(trusted, resolved)
            and (sales_sum_intent(intent, question)
                 or sales_rank_engaged(intent, plan, question, cands))):
        _canon = sales_canon_src(cands, intent, question, plan=plan)
        if _canon:
            _prev = list(picked or [])
            if not _prev or _prev[0] != _canon:
                diag["sales_canon_override"] = {"было": _prev, "стало": _canon}
                шаг("канон продаж", было=(_prev[0] if _prev else "—"),
                    стало=_canon)
            picked = [_canon]
            diag["sales_canon_locked"] = _canon
    if period_zero_why_question(question) and sales_sum_intent(intent, question):
        diag["period_zero_why"] = True
        if (intent.get("want") or "") == "list":
            intent["want"] = "sum"
    # «прайс» = справочник товаров; документ установки цен — шум ([замер 21.08] 321757).
    if (not focus and not no_arbiter and picked
            and not entity_choice_locked(trusted, resolved)
            and not diag.get("sales_canon_locked")):
        _cat = catalog_count_src(cands, intent, question)
        if _cat:
            if picked[0] != _cat:
                diag["catalog_count_override"] = {"было": list(picked), "стало": _cat}
                шаг("канон прайса", было=picked[0], стало=_cat)
            picked = [_cat]
            diag["catalog_count_locked"] = _cat
    writer_pair = writer.get(picked[0]) if picked else None
    if (writer_pair and picked and writer_pair not in picked
            and not diag.get("sales_canon_locked")
            and not diag.get("catalog_count_locked")):
        diag["writer_pair"] = writer_pair
    #   4. 🔴 (05.08) смысловой путь ОТКАЗАЛ (`meaning_down`). Тогда порядок кандидатов
    #      задаётся числом совпадений, то есть размером сущности, и уверенности в выборе у
    #      нас нет никакой — это сомнение по факту сбоя, а не по данным. Круг арбитра при
    #      этом собирается и сравнивает ЧИСЛА, которые считает база: она-то работает.
    if FORK_OUTCOMES and (diag.get("fork") or {}).get("classes") == 1:
        doubt = (len(picked) > 1 or bool(diag.get("writer_pair"))
                 or bool(diag.get("meaning_down")))
    else:
        doubt = (len(picked) > 1 or bool(diag.get("signals_disagree"))
                 or bool(diag.get("writer_pair")) or bool(diag.get("meaning_down")))
    arb_pool = list(picked)
    if event_path_active(intent):
        arb_pool = event_filter_pool(arb_pool, intent, diag)
        if len(arb_pool) == 1:
            picked = list(arb_pool)
            doubt = False
    # Документ-регистратор идёт в круг ПЕРВЫМ соперником: он и есть второе прочтение,
    # а не «следующий по порядку отбора». При каноне продаж документ — люк, не соперник.
    if (diag.get("writer_pair") and picked and not focus and not no_arbiter
            and not diag.get("sales_canon_locked")
            and not diag.get("catalog_count_locked")
            and len(arb_pool) < ARBITER_MAX):
        arb_pool.append(diag["writer_pair"])
    if (sales_sum_intent(intent, question)
            or sales_rank_engaged(intent, plan, question, arb_pool)):
        arb_pool = prefer_entity_for_sales(
            arb_pool, intent, question, plan=plan)
    arb_pool = prefer_entity_for_catalog_count(arb_pool, intent, question)
    # Lock канона: один источник → period_empty / ответ, не clarify соперников.
    picked, arb_pool, doubt = sales_canon_force_pool(
        diag.get("sales_canon_locked") or diag.get("catalog_count_locked"),
        picked, arb_pool, doubt)
    if doubt and picked and not focus and not no_arbiter and len(arb_pool) < ARBITER_MAX:
        fam = {_family(x) for x in arb_pool}
        # 🔴 СОПЕРНИК БЕРЁТСЯ ПО ПОРЯДКУ ОТБОРА, И ЭТО РЕШЕНО ЗАМЕРОМ, А НЕ ВКУСОМ.
        # Я попробовал подбирать соперника «по независимым признакам» — вершина по вектору
        # вопроса и кандидат с наибольшим числом совпадений. [замер 30.07] стало ХУЖЕ:
        # 0 верных из 3 против 3 из 5, и в пару попадали `Корректировка Приобретения` плюс
        # КОНСТАНТА, то есть верной сущности там не было вовсе. Правка откачена.
        # Порядок отбора (вектор, затем реранкер) хотя бы держит верную сущность в голове
        # списка; вершина по вопросу добавляется ПОСЛЕ него, как дополнение, а не вместо.
        # 🔴 ПРИЗНАК «ЕСТЬ СПРОШЕННОЕ ПОЛЕ» НЕ УЧАСТВУЕТ В ПОДБОРЕ СОПЕРНИКА. [замер 30.07]
        # когда он поднимал таких кандидатов вперёд, стало ХУЖЕ: 2, 1, 3 неверных ответа на
        # восьми вопросах против 1, 0, 1 без него. Со стеммингом по основам совпадает МНОГО
        # сущностей («организаций» -> «организац» есть у многих), круг соперников расширяется
        # и арбитр выбирает из шума. Признак остаётся в `diag` как наблюдение, но решения не
        # принимает: сигнал, который не улучшил замер, не имеет права менять поведение.
        order = list(cands) + ([top_by_question] if top_by_question else [])
        if event_path_active(intent):
            _ev_set = set(event_filter_pool(cands, intent, diag))
            order = [c for c in order if c in _ev_set]
        for c in order:
            if len(arb_pool) >= ARBITER_MAX:
                break
            # 🔴 `c not in by` СНЯТО 04.08 — по той же причине, что и у признака
            # расхождения выше: соперником мог стать только кандидат буквального отбора,
            # а он приносит эталон в 5 случаях из 44. Кандидат, у которого своих
            # совпадений нет, круг арбитра не засоряет: по нему собирается ПОЛНЫЙ ответ
            # тем же кодом, и пустой в `cand_ans` не попадает.
            if c in arb_pool or _family(c) in fam:
                continue
            if SKIP_SERVICE_RIVALS and c in служебные:
                # Служебная сущность соперником не становится: её число («1» у константы
                # настройки) расходится с ответом всегда, и расхождение это ничего не
                # значит. Выбор модели (`picked`) правило не трогает — отсеиваются только
                # соперники, которых в круг завожу я.
                diag.setdefault("rival_service_skipped", []).append(c)
                continue
            arb_pool.append(c); fam.add(_family(c))
        # 🔴 ВТОРЫМ ЗАХОДОМ — СОСЕДИ ПО СЕМЬЕ, если в круге осталось место. Первый заход
        # оставлен как был: порядок «сперва чужие семьи» решён замером 30.07, и трогать его
        # нельзя. Но выбрасывать соседей совсем — значит не видеть класс ошибки, который
        # `[замер 03.08]` расходится числом в **195 случаях из 249 (78 %)**: две табличные
        # части одного документа. Вопрос 6 приёмки проигран именно так.
        # Соседи добавляются ПОСЛЕ, то есть только в свободное место, и лишними уточнениями
        # это не оборачивается: арбитр-детектор спрашивает, лишь когда числа разошлись.
        for c in order:
            if len(arb_pool) >= ARBITER_MAX:
                break
            if c in arb_pool or (SKIP_SERVICE_RIVALS and c in служебные):
                continue
            arb_pool.append(c)
            diag["arbiter_kin_rival"] = c
        if len(arb_pool) > 1:
            diag["arbiter_rivals"] = arb_pool[1:]
        шаг("круг арбитра", всего=len(arb_pool),
            соперники=",".join(arb_pool[1:]) or "—")

    # Стоп 2: без focus/measure_pick ответ не уходит, пока посчитаны уже определённые
    # соперники (семья, writer_pair, лидер словаря другой семьи). Вторая попытка
    # (VETO_HEAD) не отменяется: вместо ответа вслепую соперник входит в круг.
    # При lock канона стоп2 не наращивает соперников ([замер 21.08] воскресенье
    # clarify после sales_canon_locked из-за stop2/src_conflict).
    if (picked and stop2_active(focus, measure_pick, no_arbiter, trusted)
            and not diag.get("sales_canon_locked")
            and not diag.get("catalog_count_locked")
            and len(arb_pool) < ARBITER_MAX):
        _lead = None
        _ok_s2, _top_s2 = _alias_verdict(picked[0])
        if _top_s2:
            _lead = _top_s2[0][0]
        _known = list(dict.fromkeys(
            list(picked) + list(cands[:ARBITER_MAX])
            + [t for t, _s in (_top_s2 or [])]
            + ([diag["writer_pair"]] if diag.get("writer_pair") else [])))
        _added = []
        for r in determined_answer_rivals(
                picked[0], par,
                writer_pair=diag.get("writer_pair"),
                alias_leader=_lead,
                known_src=_known):
            if len(arb_pool) >= ARBITER_MAX:
                break
            if r in arb_pool:
                continue
            if SKIP_SERVICE_RIVALS and r in служебные:
                diag.setdefault("rival_service_skipped", []).append(r)
                continue
            arb_pool.append(r)
            _added.append(r)
        if _added:
            diag["stop2_rivals"] = _added
            diag["arbiter_rivals"] = arb_pool[1:]
            шаг("стоп2 соперники", всего=len(arb_pool),
                соперники=",".join(_added) or "—")
    # Повторный singleton: стоп2/doubt могли добавить соперников после первого force.
    picked, arb_pool, doubt = sales_canon_force_pool(
        diag.get("sales_canon_locked") or diag.get("catalog_count_locked"),
        picked, arb_pool, doubt)
    # В diag для журнала (ask_journal.doubt) — после финального force.
    diag["doubt"] = bool(doubt)

    # ASK_ENTITY_FORM: distinct/complement до круга (K6), структура пула+окно.
    # Пул F — все catalog_/register_/document_ из cands (без head-среза круга).
    if ASK_ENTITY_FORM and not no_arbiter and not trusted:
        _ef_pool = list(dict.fromkeys(
            list(arb_pool or [])
            + list((_fork_early.get("pool") or []))
            + [c for c in (cands or []) if str(c).startswith("catalog_")]
            + [c for c in (cands or [])
               if str(c).startswith("accumulationregister_")
               or str(c).startswith("document_")]))
        _ecp1 = try_event_count_period_clarify(
            question, intent, diag, cut, t0, today=today,
            src=(arb_pool[0] if arb_pool else None), pool=_ef_pool,
            trusted=trusted, resolved=resolved)
        if _ecp1 is not None:
            return _ecp1
        _ef = try_entity_form_answer(
            question, intent, _ef_pool, match=match, diag=diag, cut=cut, t0=t0,
            today=today)
        if _ef is not None:
            шаг("форма сущности", form=((_ef.get("diag") or {}).get("entity_form")))
            return _ef

    def _checked(out):
        """Ответ уходит только если собственное знание базы подтверждает выбор сущности.

        Решение владельца 30.07: когда вопросу отвечает несколько РАЗНЫХ объектов —
        всегда переспрашивать, а не выбирать за человека.
        """
        if (not REQUIRE_SUPPORT or guards_skip_for_choice(focus, measure_pick, trusted)
                or diag.get("sales_canon_locked") or diag.get("catalog_count_locked")):
            return out
        w = (out.get("diag") or {}).get("focus")
        if not w or out.get("kind") not in ("answer", "figures"):
            return out
        ok, top = _alias_verdict(w)
        if ok:
            return out
        ask = _alias_clarify(w, top)
        return ask or out

    # Исходы A/B/C — после сборки arb_pool (writer_pair / стоп 2 / сомнение) и до
    # круга под-вызовов. Пространство = arb_pool: именно те прочтения, между которыми
    # иначе шёл бы арбитр (план §3). Сырой focus сюда не гасит (trusted уже выше).
    # Фаза B: при одном src (канон продаж) ось W всё равно открывает B/C, если
    # readings > 1; compare «лучше/больше чем» — отдельный путь diff, не W-люк.
    _window_fork = (len(_ask_readings) > 1
                    and not sales_compare_intent(intent, question))
    _ef_guard = entity_form_collapse_guard(
        early_classes=(diag.get("fork") or {}).get("classes") or 0,
        arb_pool_len=len(arb_pool or []),
        form_applicable=entity_form_applicable(
            intent, list(arb_pool or []) + list((_fork_early.get("pool") or []))))
    if _ef_guard.get("fork_outcome_skipped"):
        diag.setdefault("fork", {})["fork_outcome_skipped"] = (
            _ef_guard["fork_outcome_skipped"])
    _ef_early = (_ef_guard.get("action") == "resolve_early")
    if (FORK_OUTCOMES and FORK_DETECT and not no_arbiter and not trusted
            and (len(arb_pool) > 1 or _window_fork or _ef_early)):
        _t_out = time.time()
        _scan_err = None
        _rows, _cls = {}, {}
        _mword = (intent.get("measure") or "").strip()
        _fwant = (intent.get("want") or "").strip()
        try:
            # Исход B — по полному arb_pool (соперники развилки), не по cands[:16]:
            # ранний скан по отбору тянет посторонние классы (B8-01 регресс);
            # arb_pool[:3] отрезал эталонные пары — pair_budget снят в fork_outcome_b.
            _out_pool = list(arb_pool)
            if _ef_early and (_fork_early.get("pool") or []):
                _out_pool = list(dict.fromkeys(
                    list(_fork_early.get("pool") or []) + list(arb_pool)))
            _mbs = _measures_by_src(_out_pool)
            _als = _aliases_by_src(_out_pool)
            _rel = {c: _fork_relevant(_mword, _mbs.get(c) or [], _als.get(c) or {},
                                      want=_fwant or None)
                    for c in _out_pool}
            _rows, _cls, _readings, _cells = fork_detector_scan(
                match, preds, intent, today, _rel,
                period_from_prior=period_from_prior,
                measure_word=_mword, want=_fwant or None,
                day_basis_prefer=_day_prefer,
                amount_basis_prefer=_curr_prefer, trusted=trusted)
            if len(_cls) > 1:
                _fork_log(_cls, _mword or (intent.get("want") or ""))
            _prev = dict(diag.get("fork") or {})
            _meta = getattr(fork_classes, "_meta_by_fp", {}) or {}
            _atoms = []
            for fp, ss in sorted(_cls.items(), key=lambda kv: -len(kv[1])):
                m = _meta.get(fp) or {}
                rep = sorted(ss)[0]
                d0 = m.get("row") or _rows.get(rep) or {"count": 0, "folders": 0, "sums": {}}
                _built = _fork_atom_of(
                    d0, sorted(ss), _mword, want=_fwant,
                    rel_measures=_rel.get(rep), period=m.get("period"))
                _atoms.append({"atom": _built,
                               "fingerprint": _fork_fp_diag(fp),
                               "srcs": sorted(ss),
                               "window_fp": m.get("window_fp")})
            _excl = _fork_pool_excluded(_out_pool, _rows)
            diag["fork"] = dict(_prev,
                                classes=len(_cls),
                                srcs=sum(len(v) for v in _cls.values()),
                                pool=len(_out_pool),
                                pool_srcs=list(_out_pool),
                                live_srcs=sorted(_rows.keys()),
                                readings=len(_readings),
                                window_cells=(len(_cells) if _cells else None),
                                excluded=_excl or None,
                                atoms=_atoms[:10],
                                atoms_truncated=max(0, len(_atoms) - 10) or None,
                                cost_ms=int((_prev.get("cost_ms") or 0)
                                            + (time.time() - _t_out) * 1000),
                                outcome_pool="arb_pool")
            шаг("детектор исходов", классов=len(_cls), пул=len(_out_pool),
                счёт_мс=int((time.time() - _t_out) * 1000))
        except Exception as _e:                         # noqa: BLE001
            _scan_err = _e
            diag["fork_error"] = str(_e)[:160]
            sys.stderr.write("ask FORK outcome: %s\n" % str(_e)[:160])
        _outc, _pay = resolve_fork_outcome(
            _cls, _rows, measure_ctx=(_mword or _fwant or ""),
            scan_error=_scan_err, want=_fwant or None, rel_by_src=_rel,
            today=today)
        diag.setdefault("fork", {})["outcome"] = _outc
        if isinstance(_pay, dict):
            if _pay.get("reason"):
                diag["fork"]["outcome_reason"] = _pay["reason"]
            if "na_classes" in _pay:
                diag["fork"]["na_classes"] = _pay["na_classes"]
        if sales_fork_blocks_clarify(_outc, _pay, intent, diag, question, cands,
                                     diag.get("fork")):
            _sfpe = try_sales_fork_period_empty_answer(
                question, intent, diag, cut, t0, cands, diag.get("fork"))
            if _sfpe is not None:
                шаг("канон продаж: fork excluded → period_empty",
                    src=diag.get("sales_fork_period_empty"))
                return _sfpe
        _picked0 = picked[0] if picked else None
        if ASK_ATOM_TERMINAL and _outc == "unique":
            _uatom = ((_pay.get("class") or {}).get("atom") or {})
            if (_uatom.get("proof_status") == PROOF_COMPUTED
                    and _uatom.get("exact_value") is not None):
                _ures = fork_outcome_unique(
                    question, _pay.get("class"), diag, cut=cut, t0=t0)
                if _ures is not None:
                    шаг("исход unique→ответ",
                        value=_uatom.get("exact_value"))
                    return _ures
        if _outc == "A":
            шаг("исход A", srcs=len((_pay.get("class") or {}).get("srcs") or []))
            return fork_outcome_a(question, _pay.get("class"), diag, cut=cut, t0=t0)
        if _outc == "B":
            _b_classes = _pay.get("classes") or []
            if rank_defer_fork_outcome_b(intent, plan, question, _b_classes):
                diag.setdefault("fork", {})["outcome_b_deferred_rank"] = True
                шаг("исход B", отложен="rank", классов=len(_b_classes))
            else:
                _bres = fork_outcome_b(question, _pay, diag, cut=cut, t0=t0,
                                       picked_src=_picked0,
                                       day_basis_prefer=_day_prefer,
                                       amount_basis_prefer=_curr_prefer)
                if _bres is not None:
                    шаг("исход B", классов=len(_b_classes))
                    return _bres
                _outc, _pay = "C", {"reason": "uncounted_cell",
                                    "detail": "pair_render_failed"}
                diag["fork"]["outcome"] = "C"
        if _outc == "C":
            шаг("исход C", причина=_pay.get("reason") or "—")
            return fork_outcome_c(
                question, _pay, _cls, _rows, diag, cut=cut, t0=t0,
                marks=marks, by=by, match=match, preds=preds,
                picked_src=(picked[0] if picked else None),
                day_basis_prefer=_day_prefer,
                amount_basis_prefer=_curr_prefer)
        if _outc == "unavailable":
            return {"partial": cut or None, "kind": "unavailable",
                    "text": "Не удалось проверить все прочтения вопроса. "
                            "Повторите запрос.",
                    "sources": [], "retry": True,
                    "diag": _diag_pack(diag, fork_outcome="unavailable",
                                 sec=round(time.time() - t0, 2))}
        # unique / empty — ниже обычный круг или одиночный ответ

    if len(arb_pool) > 1 and not no_arbiter:
        # 🔴 СНАЧАЛА АРБИТР, ПОТОМ ЧЕЛОВЕК. Порядок п. 21: ответ → уточняющий вопрос →
        # отказ. Спрашивать человека, не попытавшись ответить, — значит переложить на него
        # работу, которую система может сделать сама. Поэтому по каждому кандидату
        # СОБИРАЕТСЯ ПОЛНЫЙ ОТВЕТ (тем же кодом, через `focus`, — то есть числа считает
        # база), и арбитр выбирает между готовыми ответами. Не выбрал — спрашиваем человека.
        cand_ans, cand_src = [], []
        mute = {}
        for c in arb_pool[:ARBITER_MAX]:
            try:
                # 🔴 `prior` ПРОБРАСЫВАЕТСЯ ВО ВСЕ ПОД-ВЫЗОВЫ КРУГА (15.08). Без него
                # кандидаты считались по РАЗНЫМ окнам периода: внешний вызов унаследовал
                # период из `prior`, а соперники — нет, и сравнение атомов шло по числам,
                # посчитанным за разное время. Развилка, «доказанная» таким сравнением,
                # была бы артефактом прибора, а не данных.
                sub = answer(question, focus=c, measure_pick=measure_pick,
                             context=context, no_arbiter=True, prior=prior)
            except Exception:                  # noqa: BLE001 — один кандидат не должен
                continue                       # ронять весь ответ
            if sub.get("kind") in ("answer", "figures") and (sub.get("text") or "").strip():
                cand_ans.append(sub["text"].split("⚠")[0].strip())
                cand_src.append(sub)
            else:
                # Не сложившийся кандидат хранится ЦЕЛИКОМ, а не одним именем: его числа
                # (посчитанные, но завёрнутые в уточнение) решают, есть ли расхождение.
                mute[c] = sub
            # 🔴 ПРИЧИНЫ partial СЛИВАЮТСЯ, А НЕ ЗАМЕНЯЮТСЯ (15.08). Под-ответ мог нести
            # свою потерю (неполнота своей сущности, отброшенные строки); прежде она
            # выбрасывалась вместе с под-ответом. Своя причина внешнего ответа старше:
            # `setdefault`, замены нет.
            for _k, _v in ((sub.get("partial") or {}).items()):
                cut.setdefault(_k, _v)
            if PROBE:
                sd = sub.get("diag") or {}
                diag.setdefault("arb_probe", []).append({
                    "src": c, "kind": sub.get("kind"), "fig": sub.get("figures"),
                    "почему": [k for k in ("measure_ambiguous", "measure_all_zero",
                                           "measure_no_values", "ambiguous",
                                           "unsupported_pick", "alias_no_evidence",
                                           "not_enough") if sd.get(k)],
                    "величины": sd.get("measure_ambiguous") or [],
                    "measure": sd.get("measure")})
        # 🔴 КАНДИДАТ, НЕ ДАВШИЙ ЧИСЛА, — ЭТО НЕ СОГЛАСИЕ (05.08).
        # Соперник считается тем же кодом, и он может вернуться не числом, а собственным
        # уточнением — например, когда у него самого несколько подходящих величин. Прежде
        # такой ответ просто выпадал из `cand_ans`, сравнивать становилось нечего, и молчание
        # засчитывалось за «числа сошлись»: ответ уходил по первому кандидату.
        # Живой случай `[замер 05.08]`: «Во что нам обошлись закупки?» — пара
        # «регистр ← документ» найдена, документ в круг попал, но его ответ пришёл
        # уточнением по величине, и система всё равно ответила по регистру.
        # Правило то же, что у `answers_diverge`: доказательства совпадения нет — спрашиваем.
        # Оговорка узкая: только пара «источник ← документ, который его пишет», то есть
        # структурная связь из данных, а не всякий не сложившийся кандидат — иначе вопрос
        # задавался бы там, где соперник просто пуст.
        #
        # 🔴 НО «НЕТ ЧИСЛА В ОТВЕТЕ» И «НЕТ ЧИСЛА ВОВСЕ» — РАЗНЫЕ ВЕЩИ (05.08, вечер).
        # Уточнение соперника бывает не о том, ЧТО отвечать, а о том, КАКОЙ ЕГО ВЕЛИЧИНОЙ
        # (`measure_ambiguous`) или с каким встречным вопросом (`asked_back`). Числа при
        # этом посчитаны базой — они лежат в его `figures` и в `measure_totals`. Делать из
        # неоднозначности ВЕЛИЧИНЫ соперника вывод о неоднозначности СУЩНОСТИ значит
        # спрашивать не о том: `[замер 05.08]` «Сколько денег нам должны клиенты?»
        # отвечалось верно (`accumulationregister_расчетысклиентами`) и стало уточнением
        # именно так. По п. 21 отвергнутый верный ответ — дефект проверки, а не осторожность.
        # Поэтому совпадение ищется ЧИСЛАМИ: наш итог сверяется со всеми числами соперника.
        # Нашлось равное — прочтения сошлись, вопрос был бы шумом; не нашлось (или числа у
        # соперника нет ни одного) — правило работает как прежде и спрашивает.
        # Порога и допуска нет намеренно, как и в `answers_diverge`: равенство или ничего.
        доказано = False
        if diag.get("writer_pair") in mute and picked and cand_src:
            # Сверяется ответ ИМЕННО ВЫБРАННОЙ сущности, а не первый сложившийся: круг
            # арбитра упорядочен, но выбор модели мог и не дать числа — тогда доказывать
            # нечего, и правило работает как прежде.
            свой = next((s for s in cand_src
                         if (s.get("diag") or {}).get("focus") == picked[0]), None)
            наше = (figures_numbers(свой) or [None])[0]
            доказано = same_number(наше, figures_numbers(mute[diag["writer_pair"]]))
            if доказано:
                diag["writer_pair_proven"] = {"число": наше,
                                              "у_соперника": diag["writer_pair"]}
        # 🔴 СОПЕРНИК, НЕ ДАВШИЙ ОТВЕТА ВОВСЕ, — ТОЖЕ НЕ СОГЛАСИЕ (06.08). Правило 05.08
        # смотрело только `mute` — соперника, чей ответ завернулся в уточнение. Но
        # под-вызов может и УПАСТЬ (исключение выше — `continue`), и тогда соперник не
        # попадает ни в ответы, ни в `mute`: круг «схлопывался» в одного, и путь
        # «сложился один кандидат» отпускал его ответ БЕЗ сравнения чисел. Живой случай
        # `[замер 06.08]`, приёмка №42 «Сколько документов реализации с нулевой суммой?»:
        # выбран регистр «НДС Состояние Реализации 0» (4 записи), документ-регистратор
        # в круге молчал — и неверный ответ ушёл уверенным, два прогона подряд. Это
        # прямое нарушение п. 12 (выбор наугад между прочтениями) и п. 10.
        if picked and not доказано and pair_unanswered(
                diag.get("writer_pair"),
                {(s.get("diag") or {}).get("focus") for s in cand_src}):
            opts_src = [picked[0], diag["writer_pair"]]
            try:
                lab_by = {r[0]: r[1] for r in psql(
                    "SELECT src_table, label FROM %s WHERE src_table IN (%s)"
                    % (TABLES, ", ".join(lit(c) for c in opts_src))) if r and r[0]}
            except RuntimeError:
                lab_by = {}
            opts = mk_opts([c for c in opts_src if c in lab_by], lab_by, marks, by, match=match, preds=preds)
            if len(opts) > 1:
                diag["writer_pair_unproven"] = diag["writer_pair"]
                return {"partial": cut or None, "kind": "clarify",
                        "text": clarify_say(question, opts, diag), "options": opts,
                        "sources": [o["label"] for o in opts],
                        "diag": _diag_pack(diag, sec=round(time.time() - t0, 2))}
        if len(cand_ans) > 1 and ARBITER_DETECTS:
            _figs = [arbiter_figures(s) for s in cand_src]
            _diverge = answers_diverge(_figs)
            _src_c = answers_src_conflict([
                {"src": (s.get("diag") or {}).get("focus"),
                 "kind": s.get("kind"),
                 "figures": f} for s, f in zip(cand_src, _figs)])
            # A3 — только когда diverge уже ложь: совпавший счётчик не доказывает
            # сущность (книга и реализации позавчера обе 19). Исключения «число
            # одно — согласие» нет: цена — «контрагенты 155=155» станет уточнением.
            if _diverge or _src_c:
                # Исход A на позднем пути: числа сошлись, src разные — источник-нейтрально
                # (тот же контракт, что ранний детектор). Расхождение чисел → C (clarify).
                # 🔴 АРБИТР — ДЕТЕКТОР НЕОДНОЗНАЧНОСТИ, А НЕ ВЫБИРАЮЩИЙ (задача 17 реестра).
                # Числа кандидатов посчитаны базой и РАЗОШЛИСЬ — значит вопросу отвечают разные
                # объекты с разными величинами, и это доказанная неоднозначность, а не повод
                # положиться на языковую догадку модели. Живой случай `[замер 03.08]`: на «на
                # какую сумму мы закупили» кандидатами идут документ приобретения
                # (`СуммаДокумента` 73 181 157,68) и регистр накопления «Закупки» (`Сумма`
                # 1 137 949,71) — прежде выбирал арбитр, и в последнем прогоне приёмки выбрал
                # регистр. Ошибка при этом честная по гейту: число посчитано верно, просто не по
                # той сущности, — поэтому ловится это только здесь.
                # Оба ответа уже собраны, то есть человеку предлагается выбор, за которым стоят
                # реальные числа, а не догадка о том, что он имел в виду.
                src_of = [s.get("diag", {}).get("focus") for s in cand_src]
                try:
                    lab_by = {r[0]: r[1] for r in psql(
                        "SELECT src_table, label FROM %s WHERE src_table IN (%s)"
                        % (TABLES, ", ".join(lit(c) for c in src_of if c))) if r and r[0]}
                except RuntimeError:
                    lab_by = {}
                opts = mk_opts([c for c in src_of if c], lab_by, marks, by, match=match, preds=preds)
                if len(opts) > 1:
                    if _diverge:
                        diag["arbiter_detected"] = {
                            "кандидаты": src_of,
                            "числа": [(s.get("figures") or {}).get("sum")
                                      if (s.get("figures") or {}).get("sum") is not None
                                      else (s.get("figures") or {}).get("count")
                                      for s in cand_src]}
                    if _src_c:
                        diag["arbiter_src_conflict"] = {"кандидаты": src_of}
                    _mute_term = prefer_mute_computed_over_clarify(
                        mute, (picked[0] if picked else None), _figs,
                        question=question, cut=cut, diag=diag, t0=t0)
                    if _mute_term is not None:
                        шаг("mute computed→ответ", src=picked[0] if picked else None)
                        return _mute_term
                    return {"partial": cut or None, "kind": "clarify",
                            "text": clarify_say(question, opts, diag), "options": opts,
                            "sources": [o["label"] for o in opts],
                            "diag": _diag_pack(diag, sec=round(time.time() - t0, 2))}
        if len(cand_ans) > 1:
            # Выбирающий arbitrate на ветке расхождения больше не зовётся (план §3):
            # diverge/src_conflict выше уже ушли в clarify/A. Здесь атомы сошлись —
            # выбирать моделью нечего. Код arbitrate сохранён; ASK_FORK_OUTCOMES=0
            # возвращает прежний вызов (эвакуация волны-1).
            if FORK_OUTCOMES:
                out = dict(cand_src[0])
                diag["arbiter"] = {"skipped": "fork_outcomes",
                                   "candidates": [s.get("diag", {}).get("focus")
                                                 for s in cand_src]}
                out["diag"] = dict(out.get("diag", {}), arbiter=diag["arbiter"])
                out["partial"] = cut or out.get("partial")
                return _checked(out)
            n = arbitrate(question, cand_ans, context)
            diag["arbiter"] = {"candidates": [s.get("diag", {}).get("focus") for s in cand_src],
                               "chose": None if n is None else
                                        cand_src[n].get("diag", {}).get("focus")}
            if n is not None:
                out = dict(cand_src[n])
                out["diag"] = dict(out.get("diag", {}), arbiter=diag["arbiter"])
                out["partial"] = cut or out.get("partial")
                return _checked(out)
        elif len(cand_ans) == 1:
            # Ответ смог собраться только у одного кандидата — остальные пусты. Выбирать не
            # из чего, но это НЕ повод не проверять: «остальные не собрались» говорит о
            # соперниках, а не о том, что этот верен.
            out = dict(cand_src[0])
            sole = (out.get("diag") or {}).get("focus")
            # 🔴 ОДИНОЧКА ОБЯЗАНА БЫТЬ ВЫБОРОМ МОДЕЛИ, А НЕ СОПЕРНИКОМ (06.08, вечер).
            # [замер 06.08], приёмка №42 «Сколько документов реализации с нулевой суммой?»:
            # модель выбрала ВЕРНЫЙ документ реализации, но его ответ завернулся в
            # уточнение о величине (пять суммовых полей), а собрался ответ соперника —
            # регистра «НДС Состояние Реализации 0» с числом 4 при эталоне 0. Путь
            # «сложился один» отпустил число СОПЕРНИКА как ответ на вопрос — выбор
            # наугад между прочтениями, замаскированный под согласие круга. Если выбор
            # модели молчит, а отвечает соперник, — прочтения два, и решает человек.
            blocked = mute_measure_blocks(sole, mute, cand_src)
            if picked and single_is_rival(picked[0], sole):
                opts_src = [picked[0], sole]
                try:
                    lab_by = {r[0]: r[1] for r in psql(
                        "SELECT src_table, label FROM %s WHERE src_table IN (%s)"
                        % (TABLES, ", ".join(lit(c) for c in opts_src))) if r and r[0]}
                except RuntimeError:
                    lab_by = {}
                opts = mk_opts([c for c in opts_src if c in lab_by], lab_by, marks, by, match=match, preds=preds)
                if len(opts) > 1:
                    diag["single_was_rival"] = {"выбор": picked[0], "ответил": sole}
                    return {"partial": cut or None, "kind": "clarify",
                            "text": clarify_say(question, opts, diag), "options": opts,
                            "sources": [o["label"] for o in opts],
                            "diag": _diag_pack(diag, sec=round(time.time() - t0, 2))}
            if blocked:
                opts_src = [x for x in (sole, blocked) if x]
                try:
                    lab_by = {r[0]: r[1] for r in psql(
                        "SELECT src_table, label FROM %s WHERE src_table IN (%s)"
                        % (TABLES, ", ".join(lit(c) for c in opts_src))) if r and r[0]}
                except RuntimeError:
                    lab_by = {}
                opts = mk_opts([c for c in opts_src if c in lab_by], lab_by, marks, by, match=match, preds=preds)
                if len(opts) > 1:
                    diag["mute_measure_rival"] = {"ответил": sole, "уточнение": blocked}
                    return {"partial": cut or None, "kind": "clarify",
                            "text": clarify_say(question, opts, diag), "options": opts,
                            "sources": [o["label"] for o in opts],
                            "diag": _diag_pack(diag, sec=round(time.time() - t0, 2))}
            out["diag"] = dict(out.get("diag", {}), arbiter={"single": True})
            out["partial"] = cut or out.get("partial")
            return _checked(out)

    if len(picked) > 1:
        try:
            lab_by = {r[0]: r[1] for r in psql(
                "SELECT src_table, label FROM %s WHERE src_table IN (%s)"
                % (TABLES, ", ".join(lit(c) for c in picked))) if r and r[0]}
        except RuntimeError:
            lab_by = {}
        opts = mk_opts(list(picked), lab_by, marks, by, match=match, preds=preds)
        if len(opts) > 1:
            diag["ambiguous"] = [o["src"] for o in opts]
            return {"partial": cut or None, "kind": "clarify",
                    "text": clarify_say(question, opts, diag),
                    "options": opts, "sources": [o["label"] for o in opts],
                    "diag": _diag_pack(diag, sec=round(time.time() - t0, 2))}
        if len(opts) == 1:
            picked = [opts[0]["src"]]
        # все живые счета 0 — не выбор из нулей; дальше страж пустого периода
    # 🔴 НЕ ОТВЕЧАТЬ, ПОКА ВЫБОР СУЩНОСТИ НЕ ПОДТВЕРЖДЁН. Решение владельца 30.07 — «правило в
    # сервисе в этом случае», — принято ПОСЛЕ того, как оба штатных средства движка были
    # проверены замером и оказались недостаточны:
    #
    #   `before_agent_finalize` → `{action:"revise"}` — движок честно отменил ход и прогнал
    #     модель заново («requested one more pass, attempt=1/3» в журнале шлюза), но модель
    #     указание ПРОИГНОРИРОВАЛА и повторила прежний ответ без обращения к данным;
    #   `tool_choice: "required"` — ушёл в ПЕТЛЮ: пять вызовов подряд, шесть минут вместо
    #     тридцати секунд, ответа нет. Модель обязана звать инструмент на каждом шаге и не
    #     может остановиться, чтобы ответить. Откачено.
    #
    # Вывод: заставить модель пойти за данными ИМЕННО ТОГДА, КОГДА НАДО, движок не умеет.
    # Гарантирует только запрет на выход — и он должен стоять там, где ответ рождается.
    #
    # Зачем правило нужно. Цель владельца: «100% правильных ответов, даже если для этого надо
    # 2-3 раза переспросить». Гейт исходящего этот класс не ловит по построению: число ЧЕСТНО
    # посчитано базой, просто не по той сущности — для гейта оно обосновано.
    # [замер 30.07, чистые сессии] из 10 вопросов 4 неверных, и во всех выбор был уверенным:
    # «НДС поставщикам» → регистр «уплаченный НДС» (2 719 573,23 вместо 11 036 086,09).
    #
    # Подтверждением считается ЛЮБОЕ из трёх, и все три — из данных, без порогов:
    #   1. человек выбрал сущность сам (`focus`) — спорить не с чем;
    #   2. сущность — ВЕРШИНА по вектору самого вопроса (считает база);
    #   3. слово вопроса совпало с ЕЁ АЛИАСОМ (`search_entity_alias`, собран один раз при
    #      установке штатным агентом OpenClaw). Сравнение — ПО ОСНОВАМ СЛОВ, штатным словарём
    #      движка (`search_dict_stem`, `techContext` возможность 35), а НЕ подстрокой:
    #      [замер 30.07] `contains('склады','складов')` ложна в обе стороны, и по подстроке
    #      верная сущность осталась бы неподтверждённой — система ушла бы в лишнее уточнение.
    #      Тот же приём уже применён в этом файле при отборе кандидатов.
    # Ни одно не выполнилось — система не знает, та ли это запись, и обязана спросить
    # (п. 12: догадка — ошибка; п. 21: уточнение стоит выше отказа).
    # Тот же контроль на пути БЕЗ арбитра: правило обязано быть одно, а не два похожих.
    # Прежде здесь лежала его собственная копия, и она разошлась с замыслом — проверяла
    # `list_has_any` (хоть одно общее слово), то есть пропускала 160 сущностей из 697.
    # 🔴 ОГОВОРКА `cand != top_by_question` ОСТАВЛЕНА — И ЭТО РЕШЕНО ЗАМЕРОМ, А НЕ ВКУСОМ.
    # Смысл её в том, что совпадение выбора модели с вершиной по вектору считается
    # подтверждением и отменяет проверку по синонимам. Опора слабая: вершина по вектору
    # верна `[замер 04.08, сессия шага 3]` в 10-13 случаях из 44. Я снял оговорку и
    # замерил: на всём наборе неверных стало меньше, но верных ответов не осталось почти
    # совсем — система начала спрашивать на 9 вопросах из 10 (в следе «выбор без опоры» у
    # вопросов 1, 3, 5, 13, 15, 17, 19, то есть в том числе у тех, что отвечались ВЕРНО).
    # Это ноль ошибок ценой отказа от ответов, а п. 21 `TARGET.md` ставит ответ выше
    # уточнения. Оговорка возвращена; разбор и числа — в `CHANGELOG` 04.08.
    # 🔴 `not no_arbiter` — ПРОВЕРКА СТОИТ НА ИТОГОВОМ ОТВЕТЕ, А НЕ НА КАЖДОМ ПОСЧИТАННОМ
    # КАНДИДАТЕ (05.08). Круг арбитра собирает ответы кандидатов ЭТИМ ЖЕ кодом
    # (`answer(..., focus=c, no_arbiter=True)`), и с включённым `ALIAS_VETO` подчинённый
    # вызов возвращал не число, а уточнение. Такой ответ в `cand_ans` не попадает, сравнивать
    # становится нечего, и арбитр-детектор молчал — то есть вето само гасило механизм,
    # который должен был поймать ошибку. Поймано пробой: на «Во что нам обошлись закупки?»
    # пара «регистр ← документ» нашлась (`writer_pair`), соперник в круг попал, а ответ всё
    # равно ушёл по регистру, потому что ответ документа не собрался.
    # Итоговый выбор по-прежнему проверяется — `_checked()` на всех ветках возврата арбитра.
    # Канон продаж/прайса уже зафиксировал src — ALIAS_VETO не должен уводить в
    # clarify соперников ([замер 21.08] возврат 12: воскресенье/прайс →
    # unsupported_pick на каноне при живом ответе на проде).
    if (REQUIRE_SUPPORT and picked
            and not guards_skip_for_choice(focus, measure_pick, trusted)
            and not no_arbiter
            and not diag.get("sales_canon_locked")
            and not diag.get("catalog_count_locked")):
        cand = picked[0]
        if cand != top_by_question:
            ok, top = _alias_verdict(cand)
            if not ok:
                ask = _alias_clarify(cand, top)
                if ask:
                    return ask
    src = picked[0] if picked else None
    # К9: событийный вопрос — сущность-ответ это ДВИЖЕНИЕ (вид объекта — первый
    # ключ ранга v2, OData-префикс из метаданных). Если модель выбрала картотеку,
    # а ранг при action_class=event даёт лидера-движение с осью — берём лидер:
    # «клиенты покупают» = регистр покупок, справочник карточек — не ответ (п. 21).
    if (not focus and event_path_active(intent)
            and not diag.get("sales_canon_locked")
            and not diag.get("catalog_count_locked")
            and not diag.get("event_code_lock")):
        _fe = event_movement_feats(diag)
        if K6R and _fe:
            _ev_src, _ = K6R.event_rank_pick(cands, _fe, intent, question)
        else:
            _ev_src = next((s for s in (diag.get("answer_fit_v2") or {})
                            if str(s).startswith(("document_", "accumulationregister_"))),
                           None)
        if _ev_src and src != _ev_src:
            src = _ev_src
            picked = [_ev_src] + [c for c in (picked or []) if c != _ev_src]
            diag["event_axis_lock"] = _ev_src
    # 🔴 ЧАСТИЧНО СОВПАВШЕЙ СУЩНОСТИ — ЕЁ СОБСТВЕННОЕ УСЛОВИЕ, И РАНЬШЕ ВСЕХ ПРОВЕРОК.
    # `match` собран под общий порог: столько понятий у этой сущности не нашлось, значит по
    # нему у неё ноль строк. Не подменив условие здесь, мы бы своей же проверкой ниже
    # («поиск сюда не попал») отбросили кандидата обратно к тому, что прошло порог, — и
    # правка отбора не дала бы ничего. Дальше по этому же условию считаются итоги
    # (`aggregate`, `totals_of`, `rows_of`), поэтому число будет посчитано по тем строкам,
    # которыми сущность и попала в кандидаты. Приём тот же, что у табличных частей.
    if src in part_pred:
        match = part_pred[src]
        diag["via_partial"] = part_lvl.get(src)
    if src not in by and not focus:
        # Модель назвала источник, куда поиск не попал: проверяем, есть ли там что-то
        # под наши условия, иначе остаёмся с тем, что реально нашлось. Выбор человека
        # (`focus`) так не перебиваем — он назвал сущность сам.
        probe_rows = rows_of(src, match, preds, 1) if src else []
        if not probe_rows and by:
            _hold_canon = (
                sales_sum_intent(intent, question)
                and empty_after_period_action(intent) in ("drop_assumed", "empty_period")
                and (diag.get("sales_canon_locked") == src
                     or sales_fork_canon_empty_src(
                         intent, diag, question, diag.get("fork"), cands) == src))
            if not _hold_canon:
                src = max(by.items(), key=lambda kv: kv[1])[0]
    # Выбрана табличная часть — отбор идёт ПО ШАПКЕ. Её собственный текст слов вопроса
    # не содержит (имя контрагента стоит в шапке), поэтому искать по нему нечего:
    # условие заменяется на «владелец строки попал в совпадения».
    if src in kid_pred:
        preds = preds + [kid_pred[src]]
        match = ""
        diag["via_parent"] = True
    elif ((diag.get("focus_was_axis") or {}).get("стало") == src
          and src_is_child(src)):
        # Строки ТЧ не несут слово «номенклатура»; период остаётся в preds.
        match = ""
        diag["axis_holder_cleared_match"] = True

    # Пустое окно (вчера/позавчера/названный день) не снимаем: иначе compose
    # видит all-time итог и врёт «за 16.08 = 79 млн» (okna 18.08, rid 2c934d58).
    # period_empty_outcome отвечает нулём за окно. Стоит до выбора величины,
    # чтобы пустышка меры из-за окна не уводила в пивот.
    if src and empty_after_period_action(intent) in ("drop_assumed", "empty_period"):
        _probe = rows_of(src, match, preds, 1)
        if not _probe:
            diag["period_window_empty"] = True
            _sfpe1 = try_sales_fork_period_empty_answer(
                question, intent, diag, cut, t0, cands, diag.get("fork"))
            if _sfpe1 is not None:
                шаг("канон продаж: period_window_empty → period_empty",
                    src=diag.get("sales_fork_period_empty"))
                return _sfpe1
    diag["focus"], diag["found"] = src, by.get(src, 0)
    if ((sales_sum_intent(intent, question)
             or sales_rank_engaged(intent, plan, question,
                                   list(cands or []) + [src]))
            and src
            and not diag.get("sales_canon_locked")
            and not diag.get("catalog_count_locked")):
        _canon_src = sales_canon_src(
            list(cands or []) + [src], intent, question, plan=plan)
        if _canon_src and src == _canon_src:
            diag["sales_canon_locked"] = _canon_src
    шаг("сущность выбрана", сущность=(src or "—"), совпадений=by.get(src, 0),
        выбрал=("человек" if focus else ("код" if diag.get("event_code_lock") else "модель")),
        сомнение=bool(diag.get("signals_disagree")))

    # НЕПОЛНОТА ИМЕННО ЭТОЙ СУЩНОСТИ (п. 13): «если из-за потери возможен неверный ответ,
    # система обязана уточнить или отказать, а не ответить по неполным данным». Первый шаг
    # — сказать. Отметка идёт ПОЛЕМ ответа, а не припиской в тексте: текст пишет модель на
    # языке вопроса, а проверяемым должно быть число.
    cov = _coverage_of(src)
    if cov:
        diag["incomplete"] = cov
        if cov.get("missing", 0) > 0:
            cut["coverage_missing"] = cov["missing"]

    # ВЕЛИЧИНА ВЫБИРАЕТСЯ ПО ВОПРОСУ — после того, как известна сущность: её величины
    # лежат в самих данных. Числовое условие («больше 500000») тоже применяется здесь,
    # а не на общем отборе: у документа оно про сумму, у строки накладной могло бы
    # оказаться про количество.
    # 🔴 ПЕРВЫМ ДЕЛОМ — ВЕЛИЧИНА, КОТОРУЮ НАЗВАЛА МОДЕЛЬ, ЧИТАВШАЯ ВОПРОС. Её имя уже
    # сверено со списком величин ЭТОЙ сущности (`pick_entity`), то есть выдуманное имя сюда
    # не доходит. Прежний путь (`pick_measure`) остаётся запасным: он выбирает по похожести
    # имён, не видя вопроса, и именно поэтому ошибался.
    # 🔴 ВЕЛИЧИНА ЖИВЁТ В ТАБЛИЧНОЙ ЧАСТИ, А НЕ В ШАПКЕ — И ЭТО НЕ ДВЕ СУЩНОСТИ, А ОДНА.
    # [замер 30.07] эталоны четырёх вопросов приёмки лежат ИМЕННО в табличной части, и в
    # шапке этих величин нет вовсе: «сколько НДС заплатили поставщикам» — 11 036 086,09 в
    # `..._товары.СуммаНДС`; «сколько штук закупили» — 92 683 в `..._товары.Количество`;
    # «цена за единицу» — 50 000 в `..._товары.Цена`. Шапка отвечала не тем или ничем.
    # Переход делается ПО ДАННЫМ: родство берётся из `search_tables.parent`, наличие
    # величины — из `map_keys(nums)`, сравнение имени — штатным словарём по основам.
    # Переходим ТОЛЬКО когда член семьи ровно один: два — это уже выбор, а выбор молча
    # делать нельзя (п. 12). Ни порога, ни имени конкретной базы здесь нет.
    want = (plan.get("quantity") or intent.get("measure") or "").strip()
    if want and not focus and not any(m.lower() == want.lower() for m in measures_of(src)):
        try:
            fam = _family(src)
            owners = [r[0] for r in psql(
                "WITH kin AS (SELECT src_table FROM %s WHERE src_table = %s OR parent = %s) "
                "SELECT DISTINCT m.src_table FROM (SELECT src_table, unnest(map_keys(nums)) AS k "
                "  FROM %s WHERE src_table IN (SELECT src_table FROM kin) AND nums IS NOT NULL) m "
                "WHERE list_has_any(ts_lexize(%s, m.k), ts_lexize(%s, %s))"
                % (TABLES, lit(fam), lit(fam), CORPUS,
                   lit(STEM_DICT), lit(STEM_DICT), lit(want))) if r and r[0]]
        except RuntimeError:
            owners = []
        if len(owners) == 1 and owners[0] != src:
            diag["measure_in_kin"] = {"было": src, "стало": owners[0], "величина": want}
            src = owners[0]
            match, preds = match, [p for p in preds if p]
            diag["focus"], diag["found"] = src, by.get(src, 0)

    measure, measure_alts = None, []
    how = ""
    _mnames = measures_of(src)
    _malias = measure_aliases_of(src)
    _rank_intent = rank_intent_from(intent, plan, question)
    _rank_sales_early = sales_rank_engaged(
        intent, plan, question, list(cands or []) + ([src] if src else []))
    _mhint = (rank_measure_hint(_mnames, intent, question, _malias)
              if not measure_pick and not _rank_sales_early else None)
    if plan.get("quantity") and plan["quantity"] in _mnames:
        measure = plan["quantity"]
        diag["measure_by_plan"] = True
        # 🔴 ГЕЙТ ВЕЛИЧИНЫ (задача 16 реестра «право на ответ (б)»). Имя, названное моделью,
        # проверялось ТОЛЬКО на существование у сущности — и этого мало: слову вопроса могут
        # отвечать несколько величин, и тогда модель выбрала одну из них молча, а п. 12
        # запрещает выбирать между правдоподобными вариантами за человека. Раньше правило
        # жило внутри `pick_measure`, то есть на этот путь не распространялось вовсе.
        #
        # Спрашиваем не всегда, когда подходящих несколько, а только когда выбор МЕНЯЕТ
        # ОТВЕТ (`measure_ambiguous`): у документа `СуммаДокумента` и `СуммаСНДС` его
        # табличной части дают одно и то же число, и вопрос о них был бы шумом, а шум
        # обесценивает настоящие уточнения.
        _word = (intent.get("measure") or "").strip()
        _malias = measure_aliases_of(src)
        _got, _alts, _how = measure_choice(measures_of(src), _word,
                                           alias_by=_malias)
        if _how == 'ask' and measure in _alts:
            _tot = {m: v for m, v, _mx, _mn in totals_of(src, match, preds, _alts)}
            if measure_ambiguous(_alts, _tot):
                measure, measure_alts = None, _alts
                diag["measure_gate"] = {"слово": _word, "подошли": _alts}
    elif _mhint:
        measure, measure_alts, how = _mhint, [], "rank_hint"
        diag["measure_rank_hint"] = _mhint
    else:
        measure, measure_alts, how = pick_measure(src, question,
                                                  (intent.get("measure") or ""))
        if (_rank_intent and not _mhint
                and _rank_wants_quantity(question)
                and len(_mnames) > 1):
            measure, measure_alts = None, _mnames
            how = "rank_no_quantity"
            diag["measure_rank_no_quantity"] = True
        elif _rank_intent and how == "rerank":
            _hint2 = _mhint or rank_measure_hint(_mnames, intent, question, _malias)
            if _hint2:
                measure, measure_alts, how = _hint2, [], "rank_hint"
                diag["measure_rank_hint"] = _hint2
            elif len(_mnames) > 1:
                measure, measure_alts = None, _mnames
                diag["measure_guess_refused"] = "rank_rerank"
        elif (_rank_intent and how == "rerank" and _mhint
                and measure and measure != _mhint):
            measure, how = _mhint, "rank_hint"
            diag["measure_rank_hint"] = _mhint
        # 🔴 ДОГАДКА РЕРАНКЕРА НЕ ГОДИТСЯ ТАМ, ГДЕ СПРАШИВАЮТ ВЕЛИЧИНУ. [замер 30.07]
        # «Сколько НДС мы заплатили поставщикам?» — модель не смогла назвать величину
        # (её у выбранного регистра нет), и прежний путь молча брал «КОплате»: ответ
        # 13 777 225,30 вместо 11 036 086,09. Три прогона из трёх.
        # Реранкер выбирает по похожести ИМЁН, не видя вопроса, — это ровно догадка, а
        # догадка запрещена (п. 12). Спрашиваем человека, какую величину считать.
        if how == "rerank" and (plan.get("compute") in ("sum", "max", "min", "avg")
                                or intent.get("want") == "sum"):
            alts = measures_of(src)
            if len(alts) > 1:
                measure, measure_alts = None, alts
                diag["measure_guess_refused"] = how
    if plan.get("compute"):
        diag["compute"] = plan["compute"]
    if not measure and not measure_alts:
        _qn = measures_of(src)
        _qt = {}
        _need_q = ((intent.get("want") or "") == "sum"
                   or (plan.get("compute") or "") in ("sum", "max", "min", "avg"))
        if _need_q and len(_qn) > 1:
            try:
                _qt = {m: v for m, v, _mx, _mn
                       in totals_of(src, match, preds, _qn)}
            except RuntimeError:
                _qt = {}
        measure, measure_alts = unresolved_quantity(
            measure, measure_alts, intent.get("want"), plan.get("compute"),
            _qn, _qt)
    if measure_pick:                           # человек уже выбрал величину кнопкой
        _names = measures_of(src)
        _resolved = resolve_measure(measure_pick, _names,
                                    measure_aliases_of(src), diag)
        if _resolved:
            measure, measure_alts = _resolved, []
        elif measure_pick in _names:
            measure, measure_alts = measure_pick, []
        else:
            diag["measure_pick_unresolved"] = measure_pick
    # Канон «продали»: итог «сколько» → деньги; ранг «что продавалось» → Количество.
    # Rank×sales (ASK_SALES_RANK_CANON): qty|money по роли оси/алиасов, не force_money.
    _rank_sales = sales_rank_engaged(
        intent, plan, question, list(cands or []) + ([src] if src else []))
    if ((sales_sum_intent(intent, question) or _rank_sales) and not measure_pick
            and (diag.get("sales_canon_locked") or src)):
        _names = measures_of(src)
        _als = measure_aliases_of(src)
        if _rank_sales:
            _axes_early = []
            try:
                _axes_early = refcols_of(src) if src else []
            except RuntimeError:
                _axes_early = []
            _sm, _how = sales_rank_resolve_measure(
                _names, intent, question, _als,
                src=src, axes=_axes_early, plan=plan, diag=diag)
            if _how == "role_ask":
                _sm = None
                _mc, _ma = measure_class_alts(_names, _als)
                if len(_ma) == 2:
                    measure, measure_alts = None, _ma
                    diag["measure_class_clarify"] = True
                    diag["sales_rank_role_ask"] = True
        elif sales_force_money_measure(intent, question):
            _sm = sales_money_measure(_names, _als)
            _how = "sales_canon"
        else:
            _sm = sales_qty_measure(_names, _als)
            _how = "sales_qty_canon"
        if _sm:
            if measure != _sm or measure_alts:
                diag["sales_measure_canon"] = {
                    "было": measure, "alts": list(measure_alts or []), "стало": _sm,
                    "how": _how}
            measure, measure_alts, how = _sm, [], _how
    diag["measure"] = measure
    шаг("величина выбрана", величина=(measure or "—"),
        подходящих=len(measure_alts or []))
    # 🔴 ТОЖДЕСТВЕННО НУЛЕВАЯ ВЕЛИЧИНА — ЭТО НЕЗАПОЛНЕННОЕ ПОЛЕ, А НЕ ОТВЕТ «НОЛЬ».
    #
    # [замер 03.08] «Сколько НДС в наших продажах?» — выбран регистр выручки и величина
    # `НДСРегл`. Она у сущности ЕСТЬ и заполнена во всех 3 878 строках, но во всех она
    # равна нулю. Система сложила и ответила «0 ₽» при эталоне 3 125 757,80. Ноль выглядит
    # как настоящий ответ — человек не отличит его от посчитанного, и это худший исход из
    # возможных (п. 21: неверный ответ хуже отказа и хуже уточнения).
    #
    # Явление не частное `[замер 03.08]`: из 1 928 пар «сущность-величина» боевой базы
    # **454 (23,5 %) тождественно нулевые**, они есть у 199 сущностей из 539. В самом этом
    # регистре нулевых 15 из 36 — то есть выбирая наугад, промахнуться легче, чем попасть.
    #
    # Признак — тождество, а не порог: `sum = max = min = 0` означает, что поле не несёт
    # ни одного значения ни в одной строке. Константы, подобранной под нашу базу, здесь
    # нет, слов и языка нет тоже, поэтому правило одинаково верно на любой конфигурации.
    #
    # Явный запрос (слова или билет) пустой величины — не ноль и не отказ, а пивот:
    # «по „Сумма“ нет значений; есть „Всего“ — N» (числа из базы, гейту разрешены).
    # Молчаливый выбор по-прежнему снимаем и предлагаем только живые. Один totals_of
    # на все имена сущности — не запрос на каждого кандидата.
    #
    # 🔴 ВТОРАЯ ДВЕРЬ К ТОМУ ЖЕ НУЛЮ: ВЕЛИЧИНЫ НЕТ НИ У ОДНОЙ ОТОБРАННОЙ СТРОКИ.
    # Правило 03.08 смотрело только в `totals_of`, а тот отдаёт пару, лишь когда строк со
    # значением больше нуля. Значит случай «ни одной строки со значением» страж не видел
    # вовсе — и он не редкость: имена величин (`measures_of`) берутся по ВСЕЙ сущности, а
    # считается ОТОБРАННОЕ подмножество, где выбранного поля может не быть ни разу.
    # [замер 04.08] прибор `step5_bench.py` показал это на 8 парах из 8: при нуле строк со
    # значением ответ содержал `sum=0, min=0, max=0, avg=0`. Такой ноль неотличим от
    # посчитанного и проходит гейт — тот же исход, ради которого правило 03.08 и заведено,
    # только через другую дверь. Отсюда одно условие на оба случая: считать было нечего
    # ЛИБО всё тождественно ноль.
    _all_tot = []
    if measure or measure_alts:
        try:
            _all_tot = totals_of(src, match, preds, measures_of(src))
        except RuntimeError:
            _all_tot = []
    if measure_alts:
        _kept = filter_dead_measure_alts(measure_alts, _all_tot)
        if _kept != list(measure_alts):
            diag["measure_alts_dead"] = [m for m in measure_alts if m not in set(_kept)]
        measure_alts = _kept
    if measure:
        _row = next((r for r in _all_tot if r and r[0] == measure), None)
        _мертва = (_row is None) or measure_row_all_zero(_row)
        if _мертва and not diag.get("period_window_empty"):
            _alive_rows = [r for r in _all_tot if r and r[0]
                           and not measure_row_all_zero(r)]
            _pick = None if diag.get("measure_pick_unresolved") else measure_pick
            _explicit = measure_asked_explicitly(
                (intent.get("measure") or "").strip(), measure, how, _pick)
            if _explicit:
                return build_measure_empty_pivot(
                    question, measure, src, _alive_rows, cut, diag, t0,
                    intent, how=how, measure_pick=measure_pick)
            # sales_sum: не уводить в measure-clarify; денежный канон держим
            # (пустой период → period_empty / 0, не «какую меру?»).
            if diag.get("sales_measure_canon"):
                _keep = sales_money_measure(
                    [r[0] for r in _alive_rows], measure_aliases_of(src))
                if _keep:
                    measure, measure_alts = _keep, []
                    diag["measure"] = _keep
                    diag["sales_measure_alive"] = _keep
                # иначе оставляем канон — дальше period/агрегат
            elif _alive_rows:
                diag["measure_all_zero" if _row is not None else "measure_no_values"] = measure
                measure, measure_alts = None, [r[0] for r in _alive_rows]
                diag["measure"] = None
    if SLOT_COVER and measure and not measure_pick and not diag.get("sales_measure_canon"):
        _unc, _cov = slot_measure_uncovered(
            (intent.get("measure") or "").strip(), measure,
            measures_of(src), measure_aliases_of(src))
        if _unc:
            diag["slot_uncovered"] = {"слово": intent.get("measure"),
                                       "выбрано": measure, "покрывают": _cov}
            measure, measure_alts = None, _cov
            diag["measure"] = None
    # Несколько величин подходят одинаково — спрашиваем, какую считать. Механизм тот же,
    # что для сущности: кнопки из ДАННЫХ плюс «свой вариант» (решение владельца 28.07).
    _ax_cd = []
    if src:
        try:
            _ax_cd = refcols_of(src)
        except RuntimeError:
            _ax_cd = []
    _ecp2 = try_event_count_period_clarify(
        question, intent, diag, cut, t0, today=today, src=src, axes=_ax_cd,
        trusted=trusted, resolved=resolved)
    if _ecp2 is not None:
        return _ecp2
    if (measure_alts and not measure_already_proven(trusted, resolved, measure_pick)
            and not diag.get("sales_measure_canon")
            and (not _rank_sales or diag.get("sales_rank_role_ask"))):
        if count_defer_measure_clarify(intent, src, _ax_cd):
            diag["count_axis_defer_measure"] = True
            measure_alts = []
    if (measure_alts and not measure_already_proven(trusted, resolved, measure_pick)
            and not diag.get("sales_measure_canon")
            and (not _rank_sales or diag.get("sales_rank_role_ask"))):
        # K4-2 / страж B: чужой src без поддержки предмета → no_data, не валюта/НДС.
        if not src_supports_question(src, intent, diag, by=by, question=question,
                                     match=match):
            diag["subject_unsupported_before_measure_clarify"] = True
            return {"partial": cut or None, "kind": "no_data", "sources": [],
                    "text": NO_DATA_TEXT or refuse_text(question),
                    "diag": _diag_pack(diag, sec=round(time.time() - t0, 2),
                                 reason="subject_unsupported_before_measure_clarify")}
        # K4-3 №7: при want=sum и двух классах money|qty — сначала класс, не все nums.
        if ((intent.get("want") or "") == "sum"
                and not ((intent.get("measure") or "").strip())
                and not measure_pick):
            _cls_m, _cls_alts = measure_class_alts(
                measure_alts, measure_aliases_of(src) if src else {})
            if len(_cls_alts) == 2:
                measure_alts = _cls_alts
                diag["measure_class_clarify"] = True
        diag["measure_ambiguous"] = measure_alts
        # 🔴 ЧИСЛА ПОДХОДЯЩИХ ВЕЛИЧИН СЧИТАЮТСЯ ЗДЕСЬ ЖЕ — ОНИ НУЖНЫ НЕ ЧЕЛОВЕКУ, А ПРОВЕРКЕ
        # НАД НАМИ (05.08). Этот же путь проходит КАНДИДАТ круга арбитра
        # (`answer(..., focus=c)`), и его уточнение о собственной величине наверху читалось
        # как «числа не сошлись» — хотя ни одного числа кандидата там не было вовсе.
        # Один запрос теми же условиями отбора даёт итог по каждой подходящей величине, и
        # совпадение становится ДОКАЗУЕМЫМ (разбор — у `writer_pair_unproven`).
        # В модель это не уходит: путь возвращает уточнение, а `diag` модели не показывают.
        try:
            diag["measure_totals"] = {m: v for m, v, _mx, _mn
                                      in totals_of(src, match, preds, measure_alts)}
        except RuntimeError:
            pass
        # 🔴 `entity_label` — человеческое имя ТОЙ ЖЕ сущности, отдельно от `label`, где
        # здесь лежит имя ВЕЛИЧИНЫ. Без него мост не мог назвать боту сущность иначе как
        # внутренним именем (`src`), а оно оттуда утекало человеку (03.08). Спрашивается у
        # базы, а не собирается разбором строки; не нашлось — поле пустое, и мост честно
        # обходится без него.
        try:
            _lab = psql("SELECT label FROM %s WHERE src_table = %s LIMIT 1"
                        % (TABLES, lit(src)))
            _ent = (_lab[0][0] or "") if _lab and _lab[0] else ""
        except RuntimeError:
            _ent = ""
        _caps = measure_captions(measure_alts, measure_aliases_of(src))
        opts = [{"src": src, "measure": m, "label": _caps[m], "distinct_by": "",
                 "entity_label": _ent}
                for m in measure_alts]
        # 🔴 ВОПРОС ЗАДАЁТ МОДЕЛЬ, НА ЯЗЫКЕ СПРАШИВАЮЩЕГО. Здесь стояла наша русская фраза
        # «Уточните, какую величину считать», и она составляла ВЕСЬ текст уточнения: на
        # англоязычном клиенте человек не понял бы, что у него спрашивают. Тот же
        # `clarify_text`, что и у выбора сущности; не смогла сформулировать — остаётся
        # перечень величин, по нему выбор всё равно возможен.
        return {"partial": cut or None, "kind": "clarify",
                "text": clarify_say(question, opts, diag)
                        or ", ".join("«%s»" % o["label"] for o in opts),
                "options": opts, "sources": [src],
                "diag": _diag_pack(diag, sec=round(time.time() - t0, 2))}
    # Величина не названа — считаем итоги по всем и показываем модели с именами.
    totals = [] if measure else totals_of(src, match, preds, measures_of(src))
    if totals:
        diag["totals"] = {m: [v, mx, mn] for m, v, mx, mn in totals}
    preds = preds + _num_pred(intent, measure)
    grain_dec = {"grain": "row", "col": None, "form": "number",
                 "named_gis": [], "clarify": None}
    axes = []
    if serene_axis and src:
        try:
            axes = refcols_of(src)
            _axis_word = (intent.get("action_axis") or "").strip() or intent.get("kind")
            _kh = kind_axis_hits(axes, _axis_word)
            _was = diag.get("focus_was_axis") or {}
            if _was.get("стало") == src and _was.get("ось"):
                _acol = _was["ось"]
                if any(a.get("col") == _acol for a in axes):
                    _kh = [_acol]
            _rank_intent = rank_intent_from(intent, plan, question)
            # Рейтинг: ось из refcols+kind до axis-clarify ([замер 23.08]/
            # [замер 24.08] не только ТМЦ — клиент/контрагент тем же путём).
            _rank_hatch = []
            if _rank_intent:
                _pcol, _rank_hatch = rank_axis_resolve(
                    src, axes, intent, question, plan)
                if _pcol:
                    _kh = [_pcol]
                    diag["rank_axis_auto"] = _pcol
                if _rank_hatch:
                    diag["rank_axis_alts"] = list(_rank_hatch)
            if (not _kh and (plan.get("compute") in ("max", "min")
                             or _rank_intent)):
                # Rank: порядок по вопросу, не по kind (kind = род источника).
                if _rank_intent and (question or "").strip():
                    _ord = rank_axes_rerank(question, axes)
                    _kh = _ord[:1] if _ord else []
                if not _kh:
                    _kh = kind_axis_rerank(axes, intent.get("kind"))
            _th = term_axis_hits(src, axes, terms_for_axis)
            if _kh and _rank_intent:
                _kh_set = set(_kh)
                _th = {gi: [c for c in (cs or []) if c in _kh_set]
                       for gi, cs in (_th or {}).items()}
                _th = {gi: cs for gi, cs in _th.items() if cs}
            grain_dec = serene_axis.decide_grain(
                axes, _kh, _th, plan.get("compute"), src_is_child(src),
                rank_intent=_rank_intent)
            if _rank_intent:
                diag["rank_axis_hatch_pending"] = list(_rank_hatch or [])
        except RuntimeError:
            pass
    diag["grain"] = grain_dec.get("grain")
    diag["axis_col"] = grain_dec.get("col")
    diag["axis_form"] = grain_dec.get("form")
    if count_question_skips_axis(intent, measure, grain_dec):
        grain_dec = {"grain": "row", "col": None, "form": "number",
                     "named_gis": [], "clarify": None}
        diag["axis_clarify_skipped"] = "count_without_measure"
    _prov_axis = None
    if choice_proven(trusted, "axis"):
        _prov_axis = (trusted or {}).get("axis")
    elif resolved.get("axis"):
        _prov_axis = resolved["axis"]
    if _prov_axis:
        grain_dec = grain_dec_from_axis_ticket(
            intent, plan, grain_dec, _prov_axis, question)
        diag["axis_from_choice"] = _prov_axis
    if total_question_skips_axis(intent, measure, grain_dec, plan, question,
                                 trusted=trusted, resolved=resolved):
        grain_dec = {"grain": "row", "col": None, "form": "number",
                     "named_gis": [], "clarify": None}
        diag["axis_clarify_skipped"] = "total_without_breakdown"
    if grain_dec.get("clarify") == "axis":
        if rank_intent_from(intent, plan, question):
            _pcol, _halts = rank_axis_resolve(
                src, axes, intent, question, plan)
            if _pcol:
                grain_dec = {"grain": "group", "col": _pcol, "form": "rank",
                             "named_gis": [], "clarify": None}
                diag["rank_axis_auto"] = _pcol
                if _halts:
                    diag["rank_axis_alts"] = list(_halts)
                    diag["rank_axis_hatch_pending"] = list(_halts)
                diag["grain"] = grain_dec["grain"]
                diag["axis_col"] = _pcol
                diag["axis_form"] = "rank"
        if grain_dec.get("clarify") != "axis":
            pass
        else:
            opts = axis_clarify_options(src, axes)
            return {"partial": cut or None, "kind": "clarify",
                "text": clarify_say(question, opts, diag)
                        or ", ".join("«%s»" % o["label"] for o in opts),
                "options": opts, "sources": [src] if src else [],
                "diag": _diag_pack(diag, sec=round(time.time() - t0, 2),
                             reason="уточните ось группы")}

    if (serene_axis and grain_dec.get("form") in ("rank", "compare")
            and not measure
            and not measure_already_proven(trusted, resolved, measure_pick)):
        _mhint_fold = rank_measure_hint(
            measures_of(src), intent, question, measure_aliases_of(src))
        if _mhint_fold:
            measure = _mhint_fold
            diag["measure_rank_hint"] = _mhint_fold
        _rn = [m for m, v, mx, mn in (totals or [])]
        if not _rn:
            _rn = measures_of(src)
        if _rn:
            _qt = {m: v for m, v, mx, mn in (totals or [])}
            _nr = None
            try:
                _srcq = INDEX if match else CORPUS
                _wq = [w for w in ([match] + list(preds or [])
                                   + ["src_table = %s" % lit(src)]) if w]
                _nfq = ("NOT coalesce(map_extract_value(flags, "
                        "'IsFolder'), false)")
                _cq = psql("SELECT count(*) FROM %s WHERE %s AND %s"
                           % (_srcq, " AND ".join(_wq), _nfq))
                _nr = int(_cq[0][0]) if _cq and _cq[0] else None
            except (RuntimeError, TypeError, ValueError, IndexError):
                _nr = None
            if not measure:
                measure, _rank_alts = serene_axis.rank_fold_choice(
                    measure, _rn, _qt, n_rows=_nr)
            else:
                _rank_alts = []
            if _rank_alts:
                names = [m for m in _rank_alts if m]
                try:
                    diag["measure_totals"] = {
                        m: v for m, v, _mx, _mn
                        in totals_of(src, match, preds, names)}
                except RuntimeError:
                    pass
                if _nr is not None and "" in _rank_alts:
                    diag.setdefault("measure_totals", {})[""] = _nr
                diag["measure_ambiguous"] = _rank_alts
                try:
                    _lab = psql("SELECT label FROM %s WHERE src_table = %s "
                                "LIMIT 1" % (TABLES, lit(src)))
                    _ent = (_lab[0][0] or "") if _lab and _lab[0] else ""
                except RuntimeError:
                    _ent = ""
                _caps = measure_captions(names, measure_aliases_of(src))
                opts = []
                for m in _rank_alts:
                    if m:
                        opts.append({"src": src, "measure": m,
                                     "label": _caps[m], "distinct_by": "",
                                     "entity_label": _ent})
                    elif _nr is not None:
                        opts.append({"src": src, "measure": "",
                                     "label": _fmt(_nr), "distinct_by": "",
                                     "entity_label": _ent})
                return {"partial": cut or None, "kind": "clarify",
                        "text": clarify_say(question, opts, diag)
                                or ", ".join("«%s»" % o["label"]
                                             for o in opts),
                        "options": opts, "sources": [src],
                        "diag": _diag_pack(diag, sec=round(time.time() - t0, 2))}
            if measure:
                diag["measure"] = measure
                for e in _num_pred(intent, measure):
                    if e not in preds:
                        preds.append(e)

    agg, rows = None, None
    if (sales_compare_intent(intent, question) and src and measure):
        _p1, _p2, _cmp_form = sales_compare_windows(intent, today, question)
        if ((_p1.get("from") or _p1.get("to"))
                and (_p2.get("from") or _p2.get("to"))):
            _cagg = aggregate_compare_sales(src, match, _p1, _p2, measure)
            if _cagg:
                agg, rows = _cagg, []
                intent["period"] = _p1
                intent["period2"] = _p2
                diag["compare_sales"] = _cmp_form
                grain_dec = {"grain": "row", "col": None, "form": "compare",
                             "named_gis": [], "clarify": None}
                diag["grain"] = "row"
                diag["axis_form"] = "compare"
                # P1: successful compare is terminal (no ASK_ENTITY_FORM gate).
                # P6: if diff != SQL pair — look for second src/measure/prior clip;
                # prior clip to today.day would break gold (sales_compare_windows).
                _catom = atom_from_agg(
                    agg, operation="compare",
                    measure_id=measure,
                    measure_label=measure_label_of(src, measure) if src else measure,
                    money=True, period=_p1, period2=_p2, form="compare",
                    compare_form=_cmp_form, src=src)
                _ctext = render_atom_pair(_catom) or _fmt(agg.get("sum"))
                if (_ctext or "").strip():
                    шаг("форма compare", diff=agg.get("sum"), windows=_cmp_form)
                    return {
                        "partial": cut or None, "kind": "answer",
                        "text": _ctext,
                        "figures": _fork_figures_of(_catom),
                        "atom": _catom, "atoms": [_catom],
                        "source_fixed": False, "memory_eligible": False,
                        "sources": [src.split("_", 1)[-1] if src and "_" in src
                                    else (src or "")],
                        "diag": _diag_pack(diag, sec=round(time.time() - t0, 2)),
                    }

    if agg is None and grain_dec.get("grain") == "group" and grain_dec.get("col") and serene_axis:
        _col = grain_dec["col"]
        _named = grain_dec.get("named_gis") or []
        _sales_rg = sales_rank_engaged(
            intent, plan, question, [src] if src else None)
        if _sales_rg and measure:
            _k = _sales_rank_top_n(intent, plan, question)
            _compute_g = "sum"
        else:
            _k = serene_axis.rank_k(intent.get("amount"), plan.get("compute"),
                                    len(_named), ROWS_TO_MODEL)
            _compute_g = plan.get("compute")
        _members = None
        if grain_dec.get("form") in ("compare", "number") and _named:
            _members = []
            for gi in _named:
                if 0 <= gi < len(terms_for_axis):
                    for a in terms_for_axis[gi] or []:
                        if a and a not in _members:
                            _members.append(str(a))
            if grain_dec.get("form") == "compare":
                _k = ROWS_TO_MODEL
        agg = aggregate_groups(src, match, preds, measure, _col, _k,
                               _compute_g, _members)
        if not agg or not agg.get("count"):
            act = empty_after_period_action(intent)
            if not _zero_period_not_missing(intent, diag, question, act, src):
                return {"partial": cut or None, "kind": "no_data",
                        "text": NO_DATA_TEXT or refuse_text(question),
                        "sources": [],
                        "diag": _diag_pack(diag, sec=round(time.time() - t0, 2))}
            if not agg:
                agg = {"count": 0, "sum": 0.0, "src": src, "measure": measure,
                       "folders": 0, "out_of_range": 0, "count_amount": 0,
                       "grain": "group", "col": _col}
        p2 = intent.get("period2") or {}
        if agg and (p2.get("from") or p2.get("to")):
            _d1 = period_preds(intent.get("period"))
            _rest = [p for p in preds if p not in _d1]
            agg2 = aggregate_groups(src, match, _rest + period_preds(p2),
                                    measure, _col, _k, plan.get("compute"),
                                    _members)
            agg = merge_period2_groups(agg, agg2)
        rows = serene_axis.group_rows((agg or {}).get("groups") or [])
        if (not rows and not (agg or {}).get("count")
                and not _zero_period_not_missing(
                    intent, diag, question, empty_after_period_action(intent), src)):
            return {"partial": cut or None, "kind": "no_data",
                    "text": NO_DATA_TEXT or refuse_text(question), "sources": [],
                    "diag": _diag_pack(diag, sec=round(time.time() - t0, 2))}
    elif agg is None and serene_axis and serene_axis.no_axis_member(grain_dec):
        rows = []
        _dac = live_axis_col_for_count(intent, src, axes)
        if _dac:
            agg = aggregate_distinct_axis(src, match, preds, _dac)
            if agg:
                diag["count_distinct_axis"] = _dac
        if agg is None:
            agg = aggregate(src, match, preds, measure)
        if not agg or not agg.get("count"):
            act = empty_after_period_action(intent)
            if not _zero_period_not_missing(intent, diag, question, act, src):
                return {"partial": cut or None, "kind": "no_data",
                        "text": NO_DATA_TEXT or refuse_text(question),
                        "sources": [],
                        "diag": _diag_pack(diag, sec=round(time.time() - t0, 2))}
            if not agg:
                agg = {"count": 0, "sum": 0.0, "src": src, "measure": measure,
                       "folders": 0, "out_of_range": 0, "count_amount": 0}
    elif agg is None:
        rows = rows_of(src, match, preds, TOPK, measure)
        if not rows:
            # Ранний no_data стоял ДО счёта undated: при 100% строк без даты
            # потеря была полной, и «данных нет» срабатывало про существование.
            act = empty_after_period_action(intent)
            if not _zero_period_not_missing(intent, diag, question, act, src):
                return {"partial": cut or None, "kind": "no_data",
                        "text": NO_DATA_TEXT or refuse_text(question),
                        "sources": [],
                        "diag": _diag_pack(diag, sec=round(time.time() - t0, 2))}
        _dac = live_axis_col_for_count(intent, src, axes)
        if _dac:
            agg = aggregate_distinct_axis(src, match, preds, _dac)
            if agg:
                diag["count_distinct_axis"] = _dac
        if agg is None:
            agg = aggregate(src, match, preds, measure)
        if not agg:
            act = empty_after_period_action(intent)
            if act in ("empty_period", "drop_assumed"):
                agg = {"count": 0, "sum": 0.0, "src": src, "measure": measure,
                       "folders": 0, "out_of_range": 0, "count_amount": 0}
            else:
                return {"partial": cut or None, "kind": "no_data",
                        "text": NO_DATA_TEXT or refuse_text(question),
                        "sources": [],
                        "diag": _diag_pack(diag, sec=round(time.time() - t0, 2))}
    шаг("посчитано базой", сущность=src, величина=(measure or "—"),
        строк=(agg or {}).get("count"), итог=(agg or {}).get("sum"),
        со_значением=(agg or {}).get("count_amount"),
        зерно=(agg or {}).get("grain") or "row",
        групп=(agg or {}).get("n_groups"))
    # Множество, по которому посчитано, объявляется наружу целиком (см. `aggregate`):
    # по нему посторонний прибор пересчитывает итог независимо, а не верит нашему числу.
    # До модели `diag` не доходит.
    if agg and agg.get("scope"):
        diag["счёт"] = dict(agg["scope"], величина=measure,
                            строк=agg["count"], со_значением=agg["count_amount"],
                            групп_отброшено=agg["folders"],
                            вне_разрядности=agg["out_of_range"])
    if agg:
        diag["n_rows"] = agg.get("count")
        if agg.get("n_groups") is not None:
            diag["n_groups"] = agg["n_groups"]
        if agg.get("grain"):
            diag["счёт"] = dict(diag.get("счёт") or {}, зерно=agg.get("grain"),
                                ось=agg.get("col"), форма=grain_dec.get("form"))
    # 🔴 ПЕРИОД ВЫБРАСЫВАЕТ СТРОКИ БЕЗ ДАТЫ — И ЭТО ОБЯЗАНО БЫТЬ ВИДНО ЧИСЛОМ (п. 13).
    #
    # Условие по периоду сравнивает `doc_date`, а строка без даты не проходит НИ ОДНО
    # сравнение: она исчезает из счёта молча, как будто её нет. Для табличных частей это
    # не редкость, а норма — дата стоит в шапке, и в строках её нет вовсе: `[замер 04.08]`
    # у `document_возвраттоваровотклиента_товары` без даты 54 строки из 55 (98 %), у
    # `..._расшифровкаплатежа` — 97 из 99, всего таких сущностей 22. То есть вопрос «за
    # 2019 год» по табличной части считает единицы строк вместо всех и об этом не говорит.
    #
    # Считаем ровно то, что отняло НАШЕ условие по дате: то же множество без датных
    # предикатов, строки без даты. Список датных предикатов берётся у того же
    # `_predicates`, что их и построил, — строку никто не разбирает.
    _date_preds = _predicates(intent)
    if _date_preds and agg:
        try:
            _kept = [p for p in preds if p not in _date_preds]
            _u = psql("SELECT count(*) FROM %s WHERE %s AND doc_date IS NULL"
                      % (INDEX if match else CORPUS,
                         " AND ".join([w for w in ([match] + _kept
                                       + ["src_table = %s" % lit(src)]) if w])))
            _undated = int(_u[0][0]) if _u and _u[0] else 0
        except (RuntimeError, ValueError, IndexError):
            _undated = 0
        if _undated:
            agg["undated"] = _undated
            cut["undated_excluded"] = _undated
            if "счёт" in diag:
                diag["счёт"]["без_даты_отброшено"] = _undated
            # 🔴 В `cov` это НЕ дописывается, хотя соблазн есть: у него читаются ИМЕННО
            # ключи `in_1c`/`in_search`/`missing` (ниже, в белом списке гейта и в местах
            # подстановки), и словарь с другим составом уронил бы ответ `KeyError`-ом на
            # каждом вопросе с периодом. Число живёт в самом счёте (`agg`) и в объявлении
            # множества; в белый список гейта оно попадает отдельной строкой ниже.
        try:
            _base = " AND ".join([w for w in ([match] + _kept
                                   + ["src_table = %s" % lit(src)]) if w])
            _period_ok = " AND ".join(_date_preds)
            _o = psql("SELECT count(*) FROM %s WHERE %s AND doc_date IS NOT NULL "
                      "AND NOT (%s)"
                      % (INDEX if match else CORPUS, _base, _period_ok))
            _outside = int(_o[0][0]) if _o and _o[0] else 0
        except (RuntimeError, ValueError, IndexError):
            _outside = 0
        if _outside:
            agg["outside_period"] = _outside
            if "счёт" in diag:
                diag["счёт"]["вне_периода"] = _outside
    # Числа неполноты разрешены гейту наравне с порогами вопроса: иначе фраза «не дошло
    # 104 строки» была бы отвергнута как выдумка, и система замолчала бы ровно там, где
    # обязана предупредить.
    # 🔴 РАЗРЕШЕНЫ ЧИСЛА НАШЕГО ОТБОРА, А НЕ ВСЕ ЧИСЛА ВОПРОСА (`F244`, правка 04.08).
    # Прежде сюда уходило `_norm_numbers(question)` целиком — «эхо числа из вопроса не
    # выдумка» (правило 28.07 ради «оборотов по счёту 62»). Но вопрос сочиняет модель
    # бота, и через этот список проходило любое её число: `[замер 04.08, probe_gate]`
    # выдуманный итог «7 777 777» проходил гейт, если он же стоял в вопросе. Класс,
    # который сама `gate()` называет недопустимым, а плагин закрыл ещё 02.08.
    # `_filter_values` оставляет то же самое ровно там, где это проверяемо: значение
    # применённого нами предиката и числовое понятие, по которому мы искали.
    # 🔴 ЧИСЛО ОТБРОШЕННЫХ ГРУПП — НА ТЕХ ЖЕ ПРАВАХ, ЧТО И ЧИСЛА ПЕРЕПИСИ. Оговорку про
    # папки задание требует назвать цифрами (иначе человек, знающий про 252 строки, не
    # поймёт, откуда 227), а гейт этого числа не знал — оно не приходит ни из строк, ни
    # из агрегатов, ни из вопроса. `[замер 04.08, step6_live.py]` три прогона из трёх:
    # «гейт: числа вне данных [25.0]» — то есть ответ, составленный ровно как велено,
    # отвергался собственной проверкой и уходил в `figures`. Ровно тот дефект проверки,
    # который п. 21 называет дефектом, а не осторожностью. `folders` посчитан базой тем же
    # запросом, что и `count`, — обоснован по построению.
    money = answer_money(intent.get("want"), plan.get("compute"), measure)
    _form = (agg or {}).get("form") or grain_dec.get("form") or "number"
    _grain = (agg or {}).get("grain") or grain_dec.get("grain") or "row"
    slot_mode = answer_slot_mode(intent.get("want"), plan.get("compute"),
                                 form=_form, grain=_grain)
    if (rank_intent_from(intent, plan, question) and slot_mode == "sum"
            and (_form or "").lower() != "compare"):
        slot_mode = "rank"
    diag["slot_mode"] = slot_mode
    _period_act = empty_after_period_action(intent)
    diag["empty_after_period_action"] = _period_act
    # 🔴 Имена для period_empty-ветки посчитаны ДО неё: ранний выход обязан видеть
    # те же значения, что и основной путь. [замер 18.08, okna] UnboundLocalError
    # `n_folders` → 503 на «позавчера» → документ → «итого»: присвоение стояло ниже.
    say_measure = measure if money else None
    n_folders = (agg or {}).get("folders") or 0
    if sales_period_empty(agg, _period_act, intent, diag, question):
        return build_period_empty_answer(
            question, agg, intent, measure, src, match, preds, money, slot_mode,
            cov, cut, diag, grain_dec, axes, n_folders, rows, t0, say_measure)
    # K9-ф6/ф7/ф8: mtd/event DISTINCT — пара «N · ось» кодом (как fork A), не compose.
    _want_count = (intent.get("want") or "").strip().lower() in ("count", "")
    if _want_count and event_path_active(intent) and src:
        _dac_t = diag.get("count_distinct_axis")
        if not _dac_t:
            _dac_t = live_axis_col_for_count(intent, src, axes)
            if _dac_t:
                diag["count_distinct_axis"] = _dac_t
        if _dac_t and (agg or {}).get("form") != "distinct_axis":
            _dagg = aggregate_distinct_axis(src, match, preds, _dac_t)
            if _dagg:
                agg = _dagg
                n_folders = (agg or {}).get("folders") or 0
    if (((agg or {}).get("form") == "distinct_axis" or diag.get("count_distinct_axis"))
            and _want_count):
        _ax_col = (agg or {}).get("axis") or diag.get("count_distinct_axis")
        _ax_lab = _passport_axis_label(_ax_col, axes) or (_ax_col or "")
        _dist_atom = atom_from_agg(
            agg, operation="count",
            money=False,
            period=(None if diag.get("period_assumed_dropped")
                    else (intent or {}).get("period")),
            period_origin=_passport_origin(intent, diag),
            grain="axis", form="distinct_axis",
            axis=_ax_lab or None,
            completeness=cov, folders=n_folders, src=src)
        _dist_text = render_atom_pair(_dist_atom)
        if (_dist_text or "").strip():
            _df = compose_slot_values(agg, measure=measure, folders=n_folders,
                                        money=money, slot_mode=slot_mode)
            _pass_d, _pf_d = build_answer_passport(
                period=(intent or {}).get("period"),
                period_dropped=bool(diag.get("period_assumed_dropped")),
                origin=_passport_origin(intent, diag),
                src_label=_table_label(src),
                src_kind=kind_word(src) if src else "",
                measure=measure or "",
                grain="axis",
                axis_label=_ax_lab,
                form="distinct_axis",
                text=_dist_text)
            _df.update(_pf_d or {})
            tag_d = _src_tag(src)
            шаг("distinct_axis terminal", text=_dist_text[:60])
            return {"partial": cut or None, "kind": "answer", "text": _dist_text,
                    "sources": [tag_d], "completeness": cov,
                    "measure": say_measure,
                    "figures": _df, "atom": _dist_atom, "atoms": [_dist_atom],
                    "diag": _diag_pack(diag, rows=len(rows or []),
                                       sec=round(time.time() - t0, 2),
                                       distinct_axis_terminal=True)}
    # Стоп 1: чужие итоги величин не расширяют белый список при монополии формы.
    _tot_extra = []
    if money and slot_mode == "list":
        for _tm in (totals or []):
            if (agg or {}).get("grain") == "group":
                _tot_extra.append(_tm[1])          # сумма поля, не max/min строки
            else:
                _tot_extra.extend(_tm[1:])
    extra_vals = _filter_values(intent) + _tot_extra \
                 + ([cov["in_1c"], cov["in_search"], cov["missing"]] if cov else []) \
                 + ([agg["undated"]] if (agg or {}).get("undated") else []) \
                 + ([agg["outside_period"]] if (agg or {}).get("outside_period") else []) \
                 + ([agg["folders"]] if (agg or {}).get("folders") else []) \
                 + ([agg["n_groups"]] if slot_mode in ("rank", "list")
                    and (agg or {}).get("grain") == "group"
                    and agg.get("n_groups") is not None else [])
    # Границы периода отбора — на тех же правах, но по датной ветке гейта.
    our_dates = _filter_dates(intent)
    # Оговорки к ответу — в промт, а не приписью после: язык берётся из вопроса.
    # (`say_measure`/`n_folders` посчитаны выше — до раннего выхода period_empty.)
    totals_shown = [] if (agg or {}).get("grain") == "group" else (totals if money else [])
    # Rank: имя лидера из GROUP BY кодом (§5 / п.19), до compose.
    # P1: compare already built diff — rank path skipped while compare locked (flag-independent).
    _cmp_form_locked = bool(
        diag.get("compare_sales")
        or (agg or {}).get("form") == "compare"
        or (grain_dec or {}).get("form") == "compare")
    if (rank_intent_from(intent, plan, question) and measure and src
            and not _cmp_form_locked):
        _pass_early, _pf = build_answer_passport(
            period=(intent or {}).get("period"),
            period_dropped=bool(diag.get("period_assumed_dropped")),
            origin=_passport_origin(intent, diag),
            src_label=_table_label(src),
            src_kind=kind_word(src) if src else "",
            measure=measure or "",
            grain=(agg or {}).get("grain") or grain_dec.get("grain") or "row",
            axis_label=_passport_axis_label(
                _passport_axis_col(agg, grain_dec), axes),
            form=(agg or {}).get("form") or grain_dec.get("form") or "number",
            text="")
        _det = rank_deterministic_answer(
            question, agg, src, match, preds, measure, money,
            intent, plan, diag, axes, cut, t0, _pass_early, say_measure,
            grain_dec=grain_dec, cov=cov,
            hatch_alts=(diag.get("rank_axis_hatch_pending")
                        or diag.get("rank_axis_alts")))
        if _det:
            if _det.get("figures") is None:
                _det["figures"] = compose_slot_values(
                    agg if (agg or {}).get("grain") == "group" else (
                        _det.get("atom") and agg) or agg,
                    measure=measure, folders=n_folders, money=money,
                    slot_mode="rank")
                _det["figures"].update(_pf or {})
            return _det
        # Нет оси — честный clarify по осям из данных, не «нет имени в строках».
        if ((agg or {}).get("grain") != "group"
                or not ((agg.get("groups") or [{}])[0].get("name") or "").strip()):
            _ax = axes or []
            if not _ax and src:
                try:
                    _ax = refcols_of(src)
                except RuntimeError:
                    _ax = []
            opts = axis_clarify_options(src, _ax)
            if opts:
                diag["rank_axis_missing"] = True
                return {"partial": cut or None, "kind": "clarify",
                        "text": clarify_say(question, opts, diag)
                                or ", ".join("«%s»" % o["label"] for o in opts),
                        "options": opts, "sources": [src] if src else [],
                        "diag": _diag_pack(diag, sec=round(time.time() - t0, 2),
                                           reason="уточните ось группы")}
    # Атом ответа — тем же строителем, что уходит в kind=answer/figures (план §5).
    _answer_pairs = [atom_from_agg(
        agg, operation=atom_operation(
            intent.get("want"), plan.get("compute"),
            form=_form, grain=_grain, slot_mode=slot_mode),
        measure_id=(say_measure or measure or None),
        measure_label=measure_label_of(src, say_measure or measure),
        money=money,
        period=(None if diag.get("period_assumed_dropped")
                else (intent or {}).get("period")),
        period_origin=_passport_origin(intent, diag),
        grain=_grain, form=_form,
        axis=_passport_axis_label(
            (agg or {}).get("axis") or (agg or {}).get("col")
            or grain_dec.get("col"), axes) or None,
        completeness=cov, folders=n_folders, src=src)]
    raw = compose(question, rows, agg, totals=totals_shown, coverage=cov,
                  measure_used=say_measure, folders=n_folders, money=money, src=src,
                  slot_mode=slot_mode, atom_pairs=_answer_pairs)
    text, claims = _split_answer(raw)
    ask_back = _ask_back(raw)
    # Рукопись ищется ДО подстановки: после неё посчитанное число стоит в тексте законно,
    # и отличить поставленное кодом от набранного моделью уже нельзя.
    by_hand = copied_figures(text, agg, rows)
    # КАЛЬКУЛЯТОР: числа ставит код, а не модель. Всё, что подставлено, посчитано базой,
    # поэтому проверять его не нужно — оно верно по построению.
    # Числа неполноты идут в подстановку наравне с итогами: их модель тоже не видит.
    cov_slots = ({"in_1c": cov["in_1c"], "in_search": cov["in_search"],
                  "missing": cov["missing"]} if cov else None)
    kw_src = kind_word(src) if src else ""
    if kw_src and slot_mode != "rank":
        cov_slots = dict(cov_slots or {})
        cov_slots["count_kind"] = kw_src
    text, slots_bad = _fill_figures(text, agg, totals_shown, money, cov_slots,
                                      slot_mode=slot_mode)
    # Пары атомов: {pair:pN} → целая пара одной операцией (план §5).
    if _answer_pairs:
        text, pair_bad = fill_atom_pairs(text, _answer_pairs)
        slots_bad = list(slots_bad) + list(pair_bad)
    text = ensure_n_groups_named(text, agg)
    # Паспорт набора решений — кодом, после цифр, до гейта (как n_groups). Слой 1
    # видимости: ISO фильтра + метки базы; счёт не меняет. clarify/no_data — ниже.
    _pass_frag, pass_fields = build_answer_passport(
        period=(intent or {}).get("period"),
        period_dropped=bool(diag.get("period_assumed_dropped")),
        origin=_passport_origin(intent, diag),
        src_label=_table_label(src),
        src_kind=kind_word(src) if src else "",
        measure=measure or "",
        grain=(agg or {}).get("grain") or grain_dec.get("grain") or "row",
        axis_label=_passport_axis_label(
            _passport_axis_col(agg, grain_dec), axes),
        form=(agg or {}).get("form") or grain_dec.get("form") or "number",
        text=text)
    text_core = text
    text = ensure_answer_passport(text, _pass_frag)
    ask_back = _filled_ask(ask_back, agg, totals_shown, money, diag, cov_slots,
                             slot_mode=slot_mode)
    # Место, которому нечего подставить, — отказ формулировки: модель сослалась на
    # величину, которой мы не считали. Это единственная проверка, оставшаяся от прежней
    # ролевой сверки, и она структурная, а не числовая.
    bad_roles = formulation_flaws(text, slots_bad) + by_hand
    ok_roles = not bad_roles

    # Проверка «ответ обязан объявить величину через claims» УБРАНА вместе с самими
    # claims (промт велит оставлять их пустыми). Её смысл держит `asked_figure_missing`:
    # спрошенная величина обязана стоять в ответе цифрами, а отброшенное — быть названо
    # числом. Это и роль (`F285`), и числа прописью (`F286`), и оговорка о потере (`№9`).
    miss = asked_figure_missing(text, agg, intent.get("want"), money, n_folders)
    if miss:
        ok_roles, bad_roles = False, bad_roles + [miss]
    leak = prompt_leak(text, OUR_PROMPTS)
    if leak:
        ok_roles, bad_roles = False, bad_roles + ["утечка инструкции: %s" % leak]
    # 🔴 ЗАЗЕМЛЯЕМ НА ТОМ, ЧТО МОДЕЛЬ ВИДЕЛА (`F247`): показанные строки и только до
    # обрезки бюджетом. Числа из непоказанных строк белым списком быть не могут —
    # скопировать их модели неоткуда, а разрешение они давали.
    seen = rows_seen(rows)
    ok_nums, bad_nums = gate(text, seen, agg, extra_vals, our_dates, money=money,
                               slot_mode=slot_mode)
    ok, bad = (ok_roles and ok_nums), (bad_roles + bad_nums)
    шаг("гейт исходящего", прошёл=bool(ok), причин=len(bad),
        первая=_gate_bad_preview(bad))
    if ok:
        text = ensure_count_named(text, agg, slot_mode)
    # ОТВЕТ ОБЯЗАН ДОЙТИ, ЕСЛИ ОН ЕСТЬ. Решение владельца 27.07: «если данные есть, но по
    # нашей системе мы их не отдали — пропадает смысл проекта». Первая формулировка могла
    # не пройти проверку по своей вине (модель объявила число строк суммой), а данные при
    # этом посчитаны и верны. Даём ровно одну вторую попытку, назвав причину отказа, и
    # проверяем её ТЕМ ЖЕ гейтом. Ослабления проверки здесь нет: если и второй ответ не
    # сходится с базой, он не уйдёт.
    if not ok and agg:
        diag["retry"] = [_fmt_gate_bad(x) for x in bad[:3]]
        raw2 = compose(question, rows, agg,
                       corrections=[_fmt_gate_bad(x) for x in bad[:3]],
                       totals=totals_shown,
                       coverage=cov, measure_used=say_measure, folders=n_folders,
                       money=money, src=src, slot_mode=slot_mode,
                       atom_pairs=_answer_pairs)
        text2, claims2 = _split_answer(raw2)
        by_hand2 = copied_figures(text2, agg, rows)
        text2, slots_bad2 = _fill_figures(text2, agg, totals_shown, money, cov_slots,
                                           slot_mode=slot_mode)
        if _answer_pairs:
            text2, pair_bad2 = fill_atom_pairs(text2, _answer_pairs)
            slots_bad2 = list(slots_bad2) + list(pair_bad2)
        text2 = ensure_n_groups_named(text2, agg)
        _pass_frag2, pass_fields2 = build_answer_passport(
            period=(intent or {}).get("period"),
            period_dropped=bool(diag.get("period_assumed_dropped")),
            origin=_passport_origin(intent, diag),
            src_label=_table_label(src),
            src_kind=kind_word(src) if src else "",
            measure=measure or "",
            grain=(agg or {}).get("grain") or grain_dec.get("grain") or "row",
            axis_label=_passport_axis_label(
                _passport_axis_col(agg, grain_dec), axes),
            form=(agg or {}).get("form") or grain_dec.get("form") or "number",
            text=text2)
        text_core = text2
        _pass_frag, pass_fields = _pass_frag2, pass_fields2
        text2 = ensure_answer_passport(text2, _pass_frag2)
        bad_roles2 = formulation_flaws(text2, slots_bad2) + by_hand2
        ok_roles2 = not bad_roles2
        bad_txt2 = []
        # Вторая попытка проверяется ТЕМ ЖЕ набором, что первая: иначе послабление
        # прокралось бы через ретрай — ответ, отвергнутый за неназванную величину,
        # проходил бы со второго раза, не назвав её снова.
        miss2 = asked_figure_missing(text2, agg, intent.get("want"), money, n_folders)
        if miss2:
            ok_roles2, bad_roles2 = False, bad_roles2 + [miss2]
        leak2 = prompt_leak(text2, OUR_PROMPTS)
        if leak2:
            ok_roles2, bad_roles2 = False, bad_roles2 + ["утечка инструкции: %s" % leak2]
        ok_nums2, bad_nums2 = gate(text2, seen, agg, extra_vals, our_dates,
                                          money=money, slot_mode=slot_mode)
        if ok_roles2 and ok_nums2 and (text2 or "").strip():
            # 🔴 УТОЧНЕНИЕ ВТОРОЙ ПОПЫТКИ ТОЖЕ ПРОХОДИТ ПОДСТАНОВКУ. Прежде здесь стояло
            # голое `_ask_back(raw2)`: числа в вопросе первой попытки подставлялись, а во
            # второй — нет, и человеку уходило «за какой период — с {date_min}?» с местом
            # вместо даты. Гейт этого не ловит (цифр в заготовке нет), и вопрос выглядел
            # как поломка системы ровно в тот момент, когда система переспрашивает.
            text, claims = text2, claims2
            text = ensure_count_named(text, agg, slot_mode)
            ask_back = _filled_ask(_ask_back(raw2), agg, totals_shown, money, diag, cov_slots,
                                    slot_mode=slot_mode)
            ok, bad = True, []
            diag["retry_ok"] = True
        else:
            bad = bad + (bad_roles2 + bad_txt2 + bad_nums2)[:3]
    diag["claims"] = claims or None
    if not ok:
        sys.stderr.write("ask GATE: числа вне данных: %s\n" % bad[:6])
        _rank_fb = rank_gate_fallback_answer(
            question, agg, src, match, preds, measure, money,
            intent, plan, diag, axes, cut, t0, _pass_frag, say_measure,
            serene_axis=serene_axis)
        if _rank_fb:
            return _rank_fb
        # Гейт отклонил формулировку модели. Числа при этом посчитаны базой и верны —
        # отдаём их СТРУКТУРОЙ, а не своей прозой: свой текст был бы на одном языке
        # независимо от языка вопроса. Вызывающий формулирует сам.
        if agg:
            _pe_act = empty_after_period_action(intent)
            diag["empty_after_period_action"] = _pe_act
            if sales_period_empty(agg, _pe_act, intent, diag, question):
                return build_period_empty_answer(
                    question, agg, intent, measure, src, match, preds, money,
                    slot_mode, cov, cut, diag, grain_dec, axes, n_folders, rows,
                    t0, say_measure)
            # Итога может не быть вовсе — считать было нечего (`sum is None`, см.
            # `aggregate`). Тогда своя фраза с суммой не собирается: ноль на этом месте
            # был бы выдуманным числом, а не пустым местом. Числа всё равно уходят
            # структурой ниже, и вызывающий формулирует по ним.
            _figs = compose_slot_values(agg, measure=measure,
                                         folders=n_folders, money=money,
                                         slot_mode=slot_mode)
            _figs.update(pass_fields or {})
            # Типизированный атом (план §5): kind=figures несёт тот же строитель, что answer.
            _atom = atom_from_agg(
                agg, operation=atom_operation(
                    intent.get("want"), plan.get("compute"),
                    form=_form, grain=_grain, slot_mode=slot_mode),
                measure_id=(say_measure or measure or None),
                measure_label=measure_label_of(src, say_measure or measure),
                money=money,
                period=(None if diag.get("period_assumed_dropped")
                        else (intent or {}).get("period")),
                period_origin=_passport_origin(intent, diag),
                grain=_grain, form=_form,
                axis=_passport_axis_label(
                    _passport_axis_col(agg, grain_dec), axes) or None,
                completeness=cov, folders=n_folders, src=src)
            return {"partial": cut or None, "kind": "figures",
                    "text": atom_terminal_gate_text(_atom, question, agg=agg),
                    "figures": _figs, "atom": _atom, "atoms": [_atom],
                    "sources": [_src_tag(src)],
                    "completeness": cov,
                    "diag": _diag_pack(diag, gate_rejected=bad[:6])}
        return {"partial": cut or None, "kind": "no_data", "text": NO_DATA_TEXT or refuse_text(question), "sources": [],
                "diag": _diag_pack(diag, gate_rejected=bad[:6])}

    tag = _src_tag(src)

    # СРЕДНЕЕ ЗВЕНО: ответ → УТОЧНЯЮЩИЙ ВОПРОС → отказ (п. 21).
    #
    # Прежде звеньев было два, и всё, что не отвечало на вопрос дословно, падало в отказ.
    # [замер 28.07] «Что покупало ООО Ромашка?»: в данных есть наши реализации в её адрес
    # на 1 236 800 руб., а её собственных закупок нет. Система отвечала «данных нет» —
    # формально верно, по делу бесполезно: спрашивавший почти наверняка имел в виду
    # именно эти продажи, а мы молчали, имея их посчитанными.
    #
    # Судья неоднозначности — МОДЕЛЬ, как и при выборе сущности. Порога здесь быть не
    # может: «отвечают ли эти строки на соседний вопрос» — суждение языковое, а не
    # числовое, и списком слов («покупало», «продали») оно не выражается — такой список
    # был бы хардкодом под русский язык и под эту конфигурацию.
    #
    # Уточнение возвращается ТОЛЬКО после гейта: числа в нём проверены базой наравне с
    # обычным ответом. Вопрос без данных не задаётся — иначе это переспрашивание вместо
    # работы, а не вместо молчания.
    # 🔴 ВСТРЕЧНЫЙ ВОПРОС ПРОВЕРЯЕТСЯ ТЕМ ЖЕ ГЕЙТОМ, ЧТО И ОТВЕТ (`F246`, правка 04.08).
    # Утверждение выше («уточнение возвращается только после гейта») было верно лишь
    # наполовину: гейт проходил `text`, а `ask` модели приклеивался к нему уже ПОСЛЕ
    # проверки и не сверялся ни с чем. Число, названное во встречном вопросе, доходило до
    # человека невыверенным — а он читает его как факт о своих данных. Не сошлось —
    # вопрос снимается, ответ уходит обычным: это ослабление уточнения, а не ответа.
    if ask_back:
        ok_ask, bad_ask = gate_out(ask_back, seen, agg, extra_vals, our_dates,
                                       money=money, slot_mode=slot_mode)
        if not ok_ask:
            sys.stderr.write("ask ASKBACK GATE: числа вне данных: %s\n" % bad_ask[:4])
            diag["ask_back_rejected"] = bad_ask[:4]
            ask_back = ""
    # Канон уже ответил числом — встречный вопрос модели («какой месяц?») превращает
    # kind=answer в clarify без options ([замер 21.08] июль 2.7M + ask_back → scorer FAIL).
    if ask_back and (diag.get("sales_canon_locked") or diag.get("catalog_count_locked")):
        diag["ask_back_dropped"] = "canon_locked"
        ask_back = ""
    if ask_back:
        diag["asked_back"] = True
        # kind=clarify — паспорт счёта не клеить (счёта для человека как ответа не было).
        return {"partial": cut or None, "kind": "clarify",
                "text": ((text_core or text).strip() + "\n\n" + ask_back).strip(),
                "question": ask_back, "options": [],
                # Величина не названа вопросом — тогда `agg` считает по пустому месту, и
                # `sum: 0` был бы не «нулём», а «не считали». Отдаём то же, что видела
                # модель: итоги по каждой величине сущности, с их именами из данных.
                "figures": compose_slot_values(agg, measure=measure,
                                               folders=n_folders, money=money,
                                               slot_mode=slot_mode),
                "totals": {m: {"sum": v, "max": mx, "min": mn} for m, v, mx, mn in (totals or [])},
                "sources": [tag],
                "diag": _diag_pack(diag, rows=len(rows), sec=round(time.time() - t0, 2), gate_ok=ok)}

    # 🔴 ОТВЕТ НАЗЫВАЕТ ВЕЛИЧИНУ, ПО КОТОРОЙ СЧИТАЛ. У сущности их бывает девять со словом
    # «сумма», и молчаливый выбор неотличим от догадки (п. 12). Дописывает КОД, а не модель:
    # имя приходит из данных, значит одинаково верно на любой конфигурации, и его нельзя
    # забыть. Приписка не дублируется, если модель уже назвала величину сама.
    text = text.strip()
    # 🔴 ОБЕ ОГОВОРКИ — КАКАЯ ВЕЛИЧИНА СЧИТАНА И СКОЛЬКО ГРУПП ОТБРОШЕНО — ушли в промт
    # (`compose`), потому что здесь они дописывались НАШЕЙ русской прозой после модели.
    # Требование не ослаблено: и то и другое названо в задании как обязательное, а числа
    # оговорок разрешены гейту, то есть не будут отвергнуты как выдумка. Смысл прежний:
    # папка — не запись и в счёт не идёт, но человек, знающий про 252 строки, обязан
    # понять, откуда 227 (п. 13: молчаливая потеря — дефект).
    # Поле человеку — то же say_measure, что compose: на count пусто, даже если
    # словарь свёл колонку. Иначе мост допишет [величина: ИМЯ] без числа.
    # diag.measure выше — сырое поле; живой обход читает его, не этот ключ.
    _figs = compose_slot_values(agg, measure=measure,
                                folders=n_folders, money=money,
                                slot_mode=slot_mode)
    _figs.update(pass_fields or {})
    # Типизированный атом (план §5 / аудит §17): одно место сборки, renderer отдельно.
    _atom = atom_from_agg(
        agg, operation=atom_operation(
            intent.get("want"), plan.get("compute"),
            form=_form, grain=_grain, slot_mode=slot_mode),
        measure_id=(say_measure or measure or None),
        measure_label=measure_label_of(src, say_measure or measure),
        money=money,
        period=(None if diag.get("period_assumed_dropped")
                else (intent or {}).get("period")),
        period_origin=_passport_origin(intent, diag),
        grain=_grain, form=_form,
        axis=_passport_axis_label(
            _passport_axis_col(agg, grain_dec), axes) or None,
        completeness=cov, folders=n_folders, src=src)
    if ASK_CURRENCY_AXIS:
        _cur_cl = currency_mismatch_blocks_answer(intent, question, src, trusted=trusted)
        if _cur_cl:
            _cur_cl["partial"] = cut or None
            _cur_cl["sources"] = [tag]
            _cur_cl["diag"] = _diag_pack(diag, sec=round(time.time() - t0, 2))
            return _cur_cl
    _money_unit = _unit_for_measure(measure, money, src=src)
    if ASK_CURRENCY_AXIS and money:
        _cu = currency_unit_for_reading((intent or {}).get("period"), src=src)
        if _cu:
            _money_unit = _cu
    if money:
        text = postprocess_money_answer_text(
            text, _money_unit)
    return {"partial": cut or None, "kind": "answer", "text": text, "sources": [tag],
            "completeness": cov, "measure": say_measure,
            # 🔴 ПОСЧИТАННЫЕ ЧИСЛА — ПОЛЕМ ОТВЕТА, А НЕ ТОЛЬКО ВНУТРИ ТЕКСТА (03.08).
            # Их читает арбитр-детектор (задача 17): чтобы сравнить ответы кандидатов, он
            # обязан сравнивать ЧИСЛА, посчитанные базой, а не разбирать прозу модели.
            # Разбор текста здесь был бы догадкой (п. 12) и ломался бы на каждом языке
            # ответа. Ветка уточнения отдаёт это поле с самого начала — теперь форма одна.
            # Паспорт набора (from/to/label/measure) — в figures тем же слоем видимости.
            "figures": _figs, "atom": _atom, "atoms": [_atom],
            "diag": _diag_pack(diag, rows=len(rows), sec=round(time.time() - t0, 2), gate_ok=ok)}


# ═══════════════ ШАГ «ДОСТАТОЧЕН ЛИ ВОПРОС ДЛЯ ОТВЕТА» (05.08) ═══════════════
#
# 🔴 ШАГ СТОИТ СНАРУЖИ `answer()`, И ЭТО НЕ УДОБСТВО, А УСЛОВИЕ ПРАВИЛЬНОСТИ. Круг арбитра
# собирает ответы кандидатов ТЕМ ЖЕ `answer(..., focus=c, no_arbiter=True)`, и проверка
# внутри превратила бы ответ кандидата в уточнение — тогда сравнивать стало бы нечего, и
# арбитр-детектор замолчал бы. Ровно так 05.08 само себя гасило вето по синонимам
# (разбор — врезка у `REQUIRE_SUPPORT` выше). Снаружи этой ошибки не бывает по построению:
# подчинённые вызовы шага не видят вовсе.
#
# Что шагу нужно от соседей и почему это ничего не стоит: разбор вопроса (`parse_intent`
# помнит ответ по ключу «вопрос + дата», поэтому вызов здесь отдаётся ДАРОМ — тот же
# разбор потом возьмёт `answer`) и числа из `diag` уже собранного ответа.
ENOUGH_ON = os.environ.get("ASK_ENOUGH", "1") not in ("0", "false", "no")
# Veto of uncovered measure slot. Default OFF: do not enable without answer-rate measure.
SLOT_COVER = os.environ.get("ASK_SLOT_COVER", "0") == "1"
# Память описаний вопроса — по тому же ключу и того же размера, что у шага 1: описание
# зависит ровно от текста вопроса, данных оно не видит.
_FACTS_MEMO = {}


def question_facts(question, today):
    """Описание вопроса моделью: на что он указывает, назван ли период и величина.

    Один вызов на вопрос, с памятью. Модель здесь — языковой инструмент: в её задании
    (`serene_enough.FACTS_SYS`) нет ни слова о том, отвечать или переспрашивать. Вердикт
    собирает код (`serene_enough.verdict_after`) из этого описания и из чисел базы.

    Не разобралось — `None`, и шаг молчит: сбой описания сам по себе уточнением не
    становится, иначе перебои у поставщика модели превращались бы в вопросы человеку.
    """
    key = (today, question)
    hit = _FACTS_MEMO.get(key)
    if hit is not None:
        return json.loads(hit)
    try:
        raw = ds_chat([{"role": "system", "content": serene_enough.FACTS_SYS},
                       {"role": "user", "content": "Question: %s" % question}],
                      max_tokens=200)
    except Exception:                              # noqa: BLE001 — сеть/квота поставщика
        return None
    got = serene_enough.parse_facts(raw)
    if got is None:
        return None
    if len(_FACTS_MEMO) >= max(1, INTENT_MEMO):
        _FACTS_MEMO.clear()
    _FACTS_MEMO[key] = json.dumps(got, ensure_ascii=False)
    return got


def entity_has_dates(src):
    """Есть ли у источника хоть одна дата — числом из базы, а не догадкой по имени.

    Нужно затем, чтобы вопрос о периоде задавался только там, где период у данных вообще
    бывает: у справочника дат нет, и «за какой период» там означало бы выбор, которого в
    данных не существует.

    Запрос дешёвый по построению: `LIMIT 1` во вложенном выборе — движку достаточно найти
    одну строку, полный проход сущности не делается. Не получилось — считаем, что дат нет:
    отсутствие сведений оставляет вопрос человеку прежним, а не расширяет его.
    """
    if not src:
        return False
    try:
        r = psql("SELECT count(*) FROM (SELECT 1 FROM %s WHERE src_table = %s "
                 "  AND doc_date IS NOT NULL LIMIT 1) x" % (CORPUS, lit(src)))
    except RuntimeError:
        return False
    try:
        return int(_num(r[0][0])) > 0 if r and r[0] else False
    except (TypeError, ValueError, IndexError):
        return False


def _gate_need(text, rows=(), agg=None, allowed=None, our_dates=None):
    """Гейт для текста уточнения этого шага: числа плюс утечка ЕГО СОБСТВЕННОГО задания.

    Общий `gate_out` сверяет утечку по списку `OUR_PROMPTS`, собранному до появления шага,
    и задания `NEED_SYS` там нет. Дописывать в чужой список отсюда — правка гейта (шаг 7,
    его ведёт другая сессия), поэтому недостающая проверка стоит своей строкой здесь, на
    том же штатном `prompt_leak`. Пересказанное человеку задание читается как факт о его
    данных ровно так же, как выдуманное число.
    """
    ok, bad = gate_out(text, rows, agg, allowed, our_dates)
    leak = prompt_leak(text, [serene_enough.NEED_SYS])
    if leak:
        return False, list(bad) + ["утечка инструкции: %s" % leak]
    return ok, bad


def _need_clarify(question, slots, why, diag):
    """Уточнение о недостающих параметрах вопроса. `None` — сформулировать не вышло.

    `options` пуст намеренно: выбирать здесь не из чего — кнопки предлагают ИСТОЧНИКИ, а
    спрашиваем мы про сам вопрос («какой товар, за какой период»). Человек отвечает новым,
    более полным вопросом, и на нём шаг уже молчит: значение названо. Протокол моста от
    этого не меняется — `[CLARIFICATION NEEDED]` он ставит по `kind`, а перечень вариантов
    у него необязателен.
    """
    txt = serene_enough.need_say(question, slots, ds_chat, _gate_need, diag)
    if not txt:
        return None
    d = _diag_pack(diag or {})
    d["not_enough"] = {"чего_нет": [s.get("kind") for s in slots if isinstance(s, dict)],
                       "почему": why}
    return {"partial": None, "kind": "clarify", "text": txt, "options": [],
            "sources": [], "diag": d}


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
        with open(os.path.abspath(__file__), "rb") as fh:
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
    def plain():
        return answer(question, focus=focus, measure_pick=measure_pick, context=context,
                      prior=prior, trusted=trusted, resolved=resolved)

    if not (ENOUGH_ON and serene_enough) or guards_skip_for_choice(
            focus, measure_pick, trusted):
        return plain()
    today = time.strftime("%Y-%m-%d")
    try:
        intent = parse_intent(question, today)
    except RuntimeError:
        return plain()                             # разбора нет — решает обычный путь
    need, slots, why = serene_enough.verdict_before(intent)
    if need:
        ask = _need_clarify(question, slots, why, {"шаг": "достаточность до поиска"})
        if ask:
            return ask
    out = plain()
    if not isinstance(out, dict) or out.get("kind") not in ("answer", "figures"):
        return out
    if not serene_enough.facts_wanted(intent):
        return out
    facts = question_facts(question, today)
    if not facts:
        return out
    d = out.get("diag") or {}
    счёт = d.get("счёт") or {}
    # Из скольких записей сложился итог. `со_значением` точнее `строк`: складываются
    # только записи с величиной, и именно их число решает, меняет ли выбор предмета ответ.
    counted = счёт.get("со_значением")
    if counted is None:
        counted = счёт.get("строк", d.get("rows", 0))
    need, slots, why = serene_enough.verdict_after(
        intent, facts, counted, entity_has_dates(d.get("focus")))
    if not need:
        return out
    ask = _need_clarify(question, slots, why,
                        dict(d, шаг="достаточность после счёта"))
    return ask or out




def _try_memory_apply(question, out, user, focus, measure_pick, context, prior,
                      trusted, mem_action):
    """Повторный прогон с веткой из памяти (ASK_MEMORY_APPLY=1)."""
    if (not ASK_MEMORY_APPLY or not ASK_CHOICE_MEMORY or not user or trusted
            or mem_action):
        return out, trusted
    probe = ACM.probe_memory_apply(
        out, psql=psql, tables=TABLES, user=user)
    if not probe.get("can_apply"):
        return out, trusted
    br = probe["branch"]
    mfocus = br.get("src") or None
    mmeas = br.get("measure") or None
    if mmeas == "":
        mmeas = None
    # sales_sum: память на документ/журнал/книгу не применяем — канон регистр
    # ([замер 21.08] память → передача ТМЦ → июль 0).
    if mfocus and sales_sum_intent({}, question) and sales_noncanon_focus(mfocus):
        return out, trusted
    mem_trusted = ACM.memory_trusted(br)
    out = _answer_checked_core(
        question, focus=mfocus, measure_pick=mmeas or measure_pick,
        context=context, prior=prior, trusted=mem_trusted,
        resolved=peek_resolved(question, user))
    out = ACM.finish_apply(out, probe)
    return out, mem_trusted

def answer_checked(question, focus=None, measure_pick=None, context="", prior=None,
                   trusted=None, decision_id=None, user=None, channel=None,
                   mem_action=None, rid=None):
    """Ответ вместе с шагом «достаточен ли вопрос». Точка входа сервиса.

    Порядок п. 21 сохранён: сперва пробуем ответить, уточняем только там, где ответа с
    одним смыслом не существует. Дешёвая половина стоит ДО поиска и экономит весь прогон,
    решающая — ПОСЛЕ счёта, потому что опирается на посчитанные числа.

    🔴 Доказанный выбор (`trusted` из decision_id) — шаг достаточности молчит целиком,
    иначе тот же выбор вернулся бы вопросом. Сырой focus/measure шаг не гасят (аудит §10),
    кроме аварийного ASK_RAW_FOCUS_TRUST=1.

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
        out, trusted = _try_memory_apply(
            question, out, user, focus, measure_pick, context, prior,
            trusted, mem_action)
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
            if gap and gap.get("kind") == "systemic":
                body = {"status": "degraded", "corpus_rows": int(n),
                        "coverage_gap": gap,
                        "period_relative_forms": prf}
                if ASK_HEALTH_NATIVE_FRESHNESS:
                    body["freshness"] = _attach_native_freshness(
                        {}, native, native_err)
                return self._send(503, body)
            if not prf.get("loaded"):
                body = {"status": "degraded", "corpus_rows": int(n),
                        "coverage_gap": gap or {"entities": 0,
                                                "rows_missing": 0,
                                                "kind": "none"},
                        "period_relative_forms": prf}
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
                                        "freshness": freshness})
            body = {"status": "serene-ask-ok", "corpus_rows": int(n),
                    "coverage_gap": gap or {"entities": 0,
                                            "rows_missing": 0,
                                            "kind": "none"},
                    "period_relative_forms": prf}
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
                # это не ответ по данным, и пустой text не должен обрастать оговоркой.
                if not (mem_action and not data_q):
                    out = stale_note(out, age, STALE_WARN_SEC, STALE_TEXT)
            _persist_ask_scope(out, question)
            return self._send(200, out)
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
