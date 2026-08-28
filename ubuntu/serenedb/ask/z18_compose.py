"""Zone 18: Формулировка (compose)."""
from __future__ import annotations

from ask._imports import *
from ask._wire import register_zone, apply_bindings

apply_bindings(globals())

def merge_period2_groups(agg, agg2):
    """Второй срез по ключу группы. Нет пары — пусто, не ноль."""
    if not agg:
        return agg
    by2 = {}
    for g in (agg2 or {}).get("groups") or []:
        by2[g.get("name") or ""] = g
    for g in agg.get("groups") or []:
        other = by2.get(g.get("name") or "")
        g["value2"] = None if other is None else other.get("value")
        g["count2"] = None if other is None else other.get("count")
        g["missing2"] = other is None
    agg["period2"] = True
    agg["n_groups2"] = (agg2 or {}).get("n_groups")
    agg["n_rows2"] = (agg2 or {}).get("count")
    return agg


def axis_clarify_options(src, axes):
    """Подписи осей из меток target_src — не имена конфигурации в коде."""
    axes = [a for a in (axes or []) if a.get("col")]
    if not axes:
        return []
    labs = {}
    srcs = [a.get("target_src") for a in axes if a.get("target_src")]
    if srcs:
        try:
            for r in psql("SELECT src_table, label FROM %s WHERE src_table IN (%s)"
                          % (TABLES, ", ".join(lit(s) for s in srcs))) or []:
                if r and r[0]:
                    labs[r[0]] = (r[1] or r[0]).strip()
        except RuntimeError:
            pass
    opts = []
    seen = set()
    for a in axes:
        lab = labs.get(a.get("target_src") or "", a["col"])
        if lab in seen:
            continue
        seen.add(lab)
        opts.append({"src": src, "label": lab, "distinct_by": a["col"],
                     "entity_label": lab})
    return opts


# ----------------------------------------------------------------- 4. формулировка
ANSWER_SYS = """You answer an employee's question using ONLY the rows given to you.

Reply with JSON only, no text outside it:
{"text": "the answer for the user",
 "ask": "one clarifying question, or null",
 "claims": {"total": number|null, "count": number|null, "max": number|null, "min": number|null}}

"ask" is the middle road between answering and giving up. Fill it ONLY when the rows do
not answer exactly what was asked, but they DO answer a closely related question about
the same subject — a different direction of the same relation, a different period, a
different role of the same party. Then put in "text" what the rows DO show, and in "ask"
a single short question that would let you answer precisely. Do not ask when the rows
answer the question — answer it. Do not ask when the rows are unrelated — say there is
no data. Never ask about our database, tables or fields: ask about the person's intent,
in their own words.

🔴 NEVER WRITE A COMPUTED FIGURE YOURSELF. Not as digits, not in words, not even by
copying it from the figures below. The system substitutes the placeholders that are
listed later in the prompt under COMPUTED / GROUPS / PAIRS for this answer shape.

When several quantities are given by name, the named placeholders listed below keep the
same form: {total:NAME}, {max:NAME}, {min:NAME} — NAME exactly as given below.

Example: the COMPUTED sections below define which placeholders exist for this answer. The
final text is formed from those placeholders after the model replies.

Values that appear INSIDE a row — a document number, a tax id, a party's name, the date
of one specific record — you copy verbatim from the rows. Those are quotations, not
arithmetic. The distinction: anything computed over several rows is a placeholder,
anything read from one row is copied.

"claims" — leave every role null. It exists only for compatibility and is ignored.

- Reply in the SAME language the question was asked in — "ask" too.
- Never invent numbers, dates or names that are not in the rows.
- If the rows do not answer the question and nothing close to it, say plainly that there
  is no data. Silence is the last resort, not the first.
- When the question is about an amount or a quantity over several records, state the
  computed total with {total} — listing the records one by one instead of giving the
  total is not an answer to "how much in all". List them in addition to it, not instead.
- Be short and businesslike, no preamble."""


def _split_answer(raw):
    """Разделить ответ модели на текст и заявленные величины.

    🔴 Служебная обёртка НЕ ДОЛЖНА доезжать до человека. [замер 27.07] когда модель
    отвечает почти-JSON-ом (скобки есть, разбор падает), прежняя версия отдавала клиенту
    сырую строку целиком: в ответе про поставщика наружу уходило
    `{"text":":"В предоставленных данных нет информации…`. Это видно клиенту, значит
    дефект (п. 13), и чинится кодом, а не просьбой в промте отвечать правильным JSON.
    """
    raw = raw or ""
    m = re.search(r"\{.*\}", raw, re.S)
    if m:
        try:
            d = json.loads(m.group(0))
            if isinstance(d, dict) and "text" in d:
                return str(d.get("text") or "").strip(), (d.get("claims") or {})
        except ValueError:
            pass
    if '"text"' in raw:
        # Достаём поле текста из поломанной обёртки. Не вышло — отдаём пусто, и дальше
        # включается честный отказ: пустота лучше служебного мусора, а отказ лучше
        # пустоты (п. 18, п. 21).
        m2 = re.search(r'"text"\s*:\s*"?:?\s*"?(.*?)(?:"\s*,\s*"claims"|"\s*\}|\}\s*$)',
                       raw, re.S)
        if m2:
            return (m2.group(1).strip().strip('"').replace('\\"', '"')
                    .replace("\\n", " ").strip()), {}
        return "", {}
    if raw.lstrip().startswith("{"):
        return "", {}
    return raw.strip(), {}


# Место, оставленное моделью под посчитанное базой число. Разбирается ТЕРПИМО — регистр
# и пробелы внутри скобок значения не имеют, имя величины сверяется без учёта регистра.
# 🔴 Строгий разбор был не строгостью, а дырой: `{Total}` и `{ total }` не совпадали с
# `[a-z_]+` вовсе, поэтому место не попадало ни в подстановку, ни в список нераспознанных —
# и уезжало клиенту БУКВАЛЬНО, «Закуплено на {Total} руб.», без числа и без ошибки. Гейт
# такую строку пропускает: цифр в ней нет. Терпимый разбор + `LEFTOVER` ниже закрывают
# оба исхода: что распозналось — заполняется, что осталось — отказ формулировки.
# Цифра в имени роли допустима: `{in_1c}` — число переписи «сколько строк в 1С». Без неё
# место не совпадало с образцом вовсе и уезжало клиенту буквально — ровно тот же дефект,
# что и `{Total}`, только найденный уже своей же пробой.
SLOT = re.compile(r"\{\s*([A-Za-z_][A-Za-z_0-9]*)\s*(?::\s*([^}]*?)\s*)?\}")
# Незаполненное место в готовом тексте. Форма — «слово» или «слово:имя» в скобках; GUID
# 1С (`{a1b2c3d4-0000-…}`) под неё не подходит из-за дефисов, то есть цитата из данных
# отказом не становится.
LEFTOVER = re.compile(r"\{\s*[^\W\d_][\w ]*(?:\s*:[^}]*)?\}", re.UNICODE)


def _group_value_by_name(agg, name):
    """Итог группы по фрагменту имени — {total:код} из названия, не мера totals."""
    needle = (name or "").strip().lower()
    if not needle:
        return None
    hits = []
    for g in (agg or {}).get("groups") or []:
        gn = (g.get("name") or "").lower()
        if not gn:
            continue
        if needle == gn or (len(needle) >= 3 and needle in gn):
            hits.append(g.get("value"))
    if not hits:
        return None
    if len(hits) == 1:
        return hits[0]
    return hits[0]


def _fill_figures(text, agg, totals, has_measure=True, extra=None, slot_mode=None):
    """Подставить посчитанные базой числа на места, оставленные моделью.

    🔴 ЭТО ЗАМЕНА ПРОВЕРКИ УСТРОЙСТВОМ. Прежде модель писала число сама, а гейт ловил её
    за руку, сверяя каждую цифру с данными. Указание владельца 28.07: «нужен просто
    калькулятор для чисел, а не сложные системы».

    Разница не в объёме кода, а в том, что становится возможным. При проверке неверное
    число возможно и лишь отлавливается — а всякая проверка ошибается в обе стороны, и
    [замер 28.07] эта ошиблась дважды за день, уронив ВЕРНЫЕ ответы: сперва из-за функции
    ранжирования, потом склеив «36, 4» в несуществующее 36.4. При подстановке неверное
    число невозможно: модель его физически не пишет. Это то же правило проекта, что и
    везде, — «запреты держатся кодом, а не промтом», доведённое до конца.

    Возвращает (текст, список нераспознанных мест). Непустой список — отказ формулировки,
    а не тихая замена на пустоту: место, которому нечего подставить, означает, что модель
    сослалась на величину, которой мы не считали.
    """
    if not text:
        return text, []
    known = {k: v for k, v in (agg or {}).items()
             if k not in ("groups", "scope") and not isinstance(v, (list, dict))}
    if slot_mode is None:
        slot_mode = "rank" if (agg or {}).get("grain") == "group" else "list"
    if slot_mode == "count":
        for k in ("sum", "max", "min", "avg", "leader", "count_amount"):
            known.pop(k, None)
    elif slot_mode == "compare":
        known.pop("leader", None)
        known.pop("count", None)
        for k in ("max", "min", "avg"):
            known.pop(k, None)
    elif slot_mode == "sum":
        known.pop("leader", None)
        if known.get("count") not in (0, 0.0):
            known.pop("count", None)
    elif slot_mode == "rank":
        known.pop("leader", None)
        known.pop("count", None)
        _ng = (agg or {}).get("n_groups")
        _shown_g = len((agg or {}).get("groups") or [])
        if _ng is not None and _ng <= _shown_g:
            known.pop("sum", None)
        for k in ("max", "min", "avg"):
            known.pop(k, None)
    # 🔴 БЕЗ ВЫБРАННОЙ ВЕЛИЧИНЫ БЕЗЫМЯННОЕ МЕСТО НЕ ЗАПОЛНЯЕТСЯ. Когда вопрос не назвал,
    # какую величину считать, `agg` считает по пустому месту и его `sum` равен нулю.
    # [замер 28.07] на «какие поступления были от ООО ТехноСнаб» ответ так и вышел:
    # «Общая сумма поступлений — 0 руб.» при настоящих 2 088 800. Ноль — такое же неверное
    # число, как любое другое, и подстановка кодом сама по себе от него не спасает:
    # спасает только отказ подставлять там, где считать было нечего.
    # Итоги по каждой величине при этом есть — они адресуются по имени, `{total:ИМЯ}`.
    if not has_measure:
        for k in ("sum", "max", "min", "avg"):
            known.pop(k, None)
    # Зерно group: {max}/{min} одной строки — не итог объекта, на который строка ссылается.
    # Стоп 1: {leader} заливается только в режиме list (цитаты/полный набор);
    # rank — через {total:gN}; sum — только итог множества.
    if (agg or {}).get("grain") == "group":
        for k in ("max", "min"):
            known.pop(k, None)
    # Числа неполноты (`{missing}`, `{in_1c}`, `{in_search}`) — такие же места, как итоги:
    # они посчитаны переписью, и списывать их модели тоже неоткуда. Кладутся ПОСЛЕ снятия
    # величин, иначе отсутствие выбранной величины уносило бы и предупреждение о потере.
    for k, v in (extra or {}).items():
        if v is not None:
            known[k] = v
    by_name = {}
    for m, v, mx, mn in (totals or []):
        by_name[m] = {"total": v, "max": mx, "min": mn}
    # Стоп 1: именованные группы — только rank/list. На sum итог множества безымянный.
    if ((agg or {}).get("grain") == "group"
            and slot_mode in ("rank", "list")):
        for i, g in enumerate((agg.get("groups") or [])[:ROWS_TO_MODEL]):
            by_name["g%d" % i] = {"total": g.get("value"), "max": g.get("value"),
                                  "min": g.get("value")}
    bad = []

    def one(mt):
        # Роль — наше служебное слово, регистр в ней не значит ничего. Имя величины
        # приходит из данных: сперва ищем как есть, потом без учёта регистра — модель
        # переписывает имя от руки, и «количество» вместо «Количество» роняло верный
        # ответ на ровном месте.
        role, name = mt.group(1).lower(), mt.group(2)
        if role == "count_kind":
            got = known.get("count_kind")
            return got if got else ""
        if name:
            name = name.strip()
            got = by_name.get(name, {}).get(role)
            if got is None:
                for k, v in by_name.items():
                    if k.lower() == name.lower():
                        got = v.get(role)
                        break
            if got is None and (agg or {}).get("grain") == "group":
                got = _group_value_by_name(agg, name)
        elif ((agg or {}).get("grain") == "group"
              and role in ("max", "min", "avg", "leader")
              and slot_mode == "list"):
            # Только list: иначе rank заливает {total:gN}, sum — {total}=итог множества.
            got = known.get("leader")
        else:
            got = known.get({"total": "sum"}.get(role, role))
        # 🔴 ПУСТОЕ ЗНАЧЕНИЕ — ТАКОЙ ЖЕ ОТКАЗ, КАК ОТСУТСТВУЮЩЕЕ. У сущности может не быть
        # ни одной даты, и `aggregate` отдаёт тогда пустую строку, а не None. Подстановка
        # её на место `{date_min}` давала человеку дыру в тексте — «данные за  ..» — то
        # есть молчаливую потерю (п. 13) вместо честного «не считали».
        if got is None or (isinstance(got, str) and not got.strip()):
            # В отказе называем ДОСТУПНЫЕ имена: вторая попытка должна знать, чем
            # заменить, иначе она повторит ту же ошибку.
            bad.append("%s (есть: %s)" % (mt.group(0), ", ".join(sorted(by_name)) or "нет")
                       if not name else mt.group(0))
            return mt.group(0)
        if role in ("date_min", "date_max"):
            return str(got)
        # Тот же группировщик, что `_fmt_human`: `head[0]` на пустой строке —
        # IndexError, на float — TypeError not subscriptable (okna 18.08,
        # rid 2c934d58, сразу после model TOKENS).
        return _fmt_human(got)

    return SLOT.sub(one, text), bad


def ensure_n_groups_named(text, agg):
    """п. 13: n_groups > K названо числом, даже если модель место не поставила."""
    if (agg or {}).get("grain") != "group":
        return text
    ng = agg.get("n_groups")
    shown = len(agg.get("groups") or [])
    if ng is None or ng <= shown:
        return text
    have = _norm_numbers(text)
    try:
        nf = float(ng)
    except (TypeError, ValueError):
        return text
    if nf in have or round(nf, 2) in have:
        return text
    filled, bad = _fill_figures("{n_groups}", agg, [], True)
    if bad or not (filled or "").strip() or filled.strip().startswith("{"):
        filled = _fmt(ng)
    return ((text or "").rstrip() + " · всего позиций: " + filled).strip()


def ensure_count_named(text, agg, slot_mode=None):
    """Стоп 1: на sum/rank счёт строк дописывает код после гейта, не белый список.

    Пока счёт не в тексте — служебный хвост из базы (как n_groups). Модель его
    написать не может: слота нет, allow(count) на sum/rank закрыт.
    """
    if slot_mode not in ("sum", "rank"):
        return text
    cnt = (agg or {}).get("count")
    if cnt is None:
        return text
    have = _norm_numbers(text)
    try:
        nf = float(cnt)
    except (TypeError, ValueError):
        return text
    if nf in have or round(nf, 2) in have:
        return text
    return ((text or "").rstrip() + " · всего записей: " + _fmt(nf)).strip()




def _measure_dimension(measure, names=None, alias_by=None):
    """Роль выбранной меры у источника: money / qty / unknown.

    Спрашивает те же каноны, что выбор меры ответа (`sales_money_measure` /
    `sales_qty_measure` + алиасы из данных), а не want/compute и не валюту
    документа. Имя на одном языке не кодируется здесь: роль — совпадение с
    каноном пула мер источника.
    """
    if not measure:
        return "unknown"
    pool = list(names) if names else [measure]
    alias_by = alias_by or {}
    qty = sales_qty_measure(pool, alias_by)
    if qty is not None and measure == qty:
        return "qty"
    mon = sales_money_measure(pool, alias_by)
    if mon is not None and measure == mon:
        return "money"
    return "unknown"


def _unit_for_measure(measure, money=True, src=None, names=None, alias_by=None):
    """Единица — от выбранной меры (её роль), не от want/compute и не от валюты документа.

    `money` от `answer_money` нужен как «есть numeric поле» (на count единицы поля
    нет), но недостаточен: sum количества тоже даёт money=True. Валюта (ASK_MONEY_UNIT)
    — только если роль меры у источника денежная. Qty и неизвестная роль → пусто
    (п. 12: не выдумывать единицу; п. 10/13: не подменять смысл числа валютой).
    """
    if not money:
        return ""
    if names is None and src:
        got = measures_of(src)
        names = got or None
    if alias_by is None and src:
        got_a = measure_aliases_of(src)
        alias_by = got_a or None
    if _measure_dimension(measure, names=names, alias_by=alias_by) != "money":
        return ""
    return MONEY_UNIT


def postprocess_money_answer_text(text, unit=""):
    """Единица измерения: данные → атом → render_atom_pair.

    Перезапись прозы модели регулярками убрана: она работала только
    на русском, а на нераспознанной мере переписывала верное в неверное.
    Единица уходит в атом рядом с числом — `render_atom_pair`.
    Функция оставлена для обратной совместимости вызовов.
    """
    return text

def build_answer_passport(period=None, period_dropped=False, origin="",
                          src_label="", src_kind="", measure="",
                          grain="row", axis_label="", form="number",
                          text=""):
    """Паспорт скрытого набора решений: ISO + метки базы + ASCII-маркеры. Чистая.

    Слой 1 видимости (п. 13): человек видит, чем SQL отфильтровал. Не меняет счёт.
    Без прозы продукта и без имён конфигурации в коде — только переданные подписи.
    origin: ``prior`` | ``assumed`` | "" — машинный маркер рядом с окном, не фраза.
    period_dropped: снятый assumed-фильтр не выдавать как применённый.
    """
    fields = {}
    parts = []
    t = text or ""

    def _add(part, *needles):
        if not part:
            return
        for n in (needles or (part,)):
            if n and n in t:
                return
        parts.append(part)

    if not period_dropped:
        p = period or {}
        pf = str(p.get("from") or "").strip()
        pt = str(p.get("to") or "").strip()
        if pf or pt:
            if pf and pt:
                window = "%s..%s" % (pf, pt)
            else:
                window = pf or pt
            if origin in ("prior", "assumed"):
                window = "%s %s" % (window, origin)
            _add(window, pf, pt)
            if pf:
                fields["from"] = pf
            if pt:
                fields["to"] = pt

    lab = (src_label or "").strip()
    if lab:
        kind = (src_kind or "").strip()
        src_disp = "%s (%s)" % (lab, kind) if kind else lab
        _add(src_disp, lab)
        fields["label"] = lab

    meas = (measure or "").strip()
    if meas:
        _add(meas, meas)
        fields["measure"] = meas

    ax = (axis_label or "").strip()
    if ax and (grain or "row") in ("group", "axis"):
        _add(ax, ax)

    if form in ("rank", "compare"):
        _add(form, form)

    return (" · ".join(parts) if parts else ""), fields


def ensure_answer_passport(text, frag):
    """Дописать паспорт после цифр, до гейта (как ensure_n_groups_named)."""
    if not (frag or "").strip():
        return text or ""
    t = (text or "").rstrip()
    if not t:
        return frag.strip()
    if frag in t:
        return t
    return (t + " · " + frag.strip()).strip()


def measure_label_of(src_table, measure):
    """Проверенная человеческая подпись величины из данных (alias / разбор имени).

    Не проза модели: `measure_captions` + `measure_aliases_of`, как варианты уточнения.
    Пустая величина — метка источника (`_table_label`), иначе операция без подписи.
    """
    if not measure:
        return _table_label(src_table) or None
    caps = measure_captions([measure], measure_aliases_of(src_table) if src_table else {})
    return (caps.get(measure) or split_ident(measure) or measure).strip() or None


def _table_label(src_table):
    """Человеческая метка источника из search_tables. Пусто — не подставлять src."""
    if not src_table:
        return ""
    try:
        r = psql("SELECT label FROM %s WHERE src_table = %s LIMIT 1"
                 % (TABLES, lit(src_table)))
    except RuntimeError:
        return ""
    if not r or not r[0]:
        return ""
    return (r[0][0] or "").strip()


def _passport_axis_label(col, axes):
    """Подпись оси: label target_src из уже выбранных refcols. Нет метки — пусто."""
    if not col:
        return ""
    target = ""
    for a in axes or []:
        if a.get("col") == col:
            target = (a.get("target_src") or "").strip()
            break
    if not target:
        return ""
    return _table_label(target)


def _passport_axis_col(agg, grain_dec=None):
    """Колонка оси: distinct agg.axis или group col."""
    return ((agg or {}).get("axis") or (agg or {}).get("col")
            or (grain_dec or {}).get("col"))


def _passport_origin(intent, diag):
    """Маркер происхождения окна: prior / assumed / ничего. Не проза."""
    if (diag or {}).get("period_from_prior"):
        return "prior"
    assumed = ((intent or {}).get("parse") or {}).get("assumed") or []
    if any(str(a).startswith("period.") for a in assumed):
        return "assumed"
    return ""


def formulation_flaws(text, slots_bad=()):
    """Причины, по которым формулировка не доходит до человека (шаг 6, структурно).

    Это не проверка чисел — числами занят гейт (шаг 7). Здесь смотрим, что до человека
    доехал ТЕКСТ, а не заготовка: место без числа, пустая строка. Оба случая гейт
    пропускает по построению — цифр в них нет, значит и необоснованных цифр нет.

    🔴 Пустая формулировка. `_split_answer` отдаёт пустую строку намеренно («пустота
    лучше служебного мусора, а отказ лучше пустоты»), но вторую половину этого правила
    исполняла только вторая попытка: у неё стоит `and (text2 or "").strip()`, а у первой
    такой проверки не было. Оборванный по `max_tokens` ответ или обёртка без поля `text`
    доезжали до клиента ПУСТЫМ сообщением с видом `kind=answer` — при том что числа
    посчитаны и их было чем отдать структурой.

    🔴 Незаполненное место. `{Total}`, `{ total }`, `{Итого}` не совпадали с прежним
    строгим образцом и потому не попадали ни в подстановку, ни в список нераспознанных.
    Теперь разбор терпимый, а всё, что осталось в скобках, — отказ формулировки: вторая
    попытка, а если и она не сойдётся, числа уходят структурой (п. 21). Заготовка
    человеку при этом не показывается.
    """
    bad = ["нераспознанное место: %s" % x for x in list(slots_bad)[:3]]
    if not (text or "").strip():
        bad.append("пустая формулировка")
        return bad
    left = LEFTOVER.search(text)
    if left:
        bad.append("незаполненное место: %s" % left.group(0)[:40])
    return bad


def copied_figures(text, agg, rows):
    """Посчитанные числа, которые модель набрала цифрами вместо места под подстановку.

    🔴 Здесь правило «числа ставит код, а не модель» перестаёт быть строкой промта и
    становится кодом. В `ANSWER_SYS` оно записано словами, и `[замер 04.08,
    step6_live.py]` показал цену этих слов: на восьми вопросах модель семь раз оставила
    место — и один раз набрала 249 цифрами. Промт срабатывает почти на всех вопросах, а
    это «почти» и есть весь вопрос: пока число набирает модель, неверное число возможно, и
    защищает от него только гейт — а гейт смотрит лишь, ЕСТЬ ли такое число в данных, но
    не в своей ли оно роли. Ровно этот класс (`F285`: «три реализации на 1 236 800 поданы
    с итогом 925 000 — настоящее число, но из другой роли») калькулятор и закрывал: пока
    число ставит код, роль не перепутать. Рукопись возвращает класс обратно.

    Цитата из строки рукописью не считается: промт разрешает копировать номер документа,
    дату и имя из конкретной записи, а `min`/`max` по построению совпадают со значением
    какой-то строки. Поэтому число сверяется со ВСЕМИ показанными строками и попадает в
    находки, только если взять его было неоткуда, кроме нашего блока с итогами.

    Найденное уходит причиной второй попытки — той же, что и остальные изъяны, — а если и
    она наберёт число цифрами, числа отдаются структурой (п. 21). Ответ при этом не
    теряется: он и так весь состоит из посчитанных базой чисел.
    """
    if not agg or not (text or "").strip():
        return []
    in_rows = set()
    for r in (rows or []):
        try:
            doc, dt = r[5], r[3]
        except (TypeError, IndexError):
            continue
        in_rows |= _norm_numbers(doc) | _norm_numbers(dt)
        try:
            v = float(r[2])
            in_rows.add(round(v, 2))
            if v == int(v):
                in_rows.add(float(int(v)))
        except (TypeError, ValueError):
            pass
    # Имя места для второй попытки: у суммы оно отличается от имени роли в `agg`.
    slot_of = {"sum": "total", "avg": "avg", "min": "min", "max": "max", "count": "count"}
    computed = {}
    for k in ("sum", "avg", "min", "max", "count"):
        v = agg.get(k)
        if v is None:
            continue
        try:
            fv = round(float(v), 2)
        except (TypeError, ValueError):
            continue
        if fv in in_rows:
            continue                    # взято из строки — это цитата, а не рукопись
        computed.setdefault(fv, k)
        if float(v) == int(float(v)):
            computed.setdefault(float(int(float(v))), k)
    if not computed:
        return []
    out, seen = [], set()
    for readings in _tokens(text):
        hit = readings & set(computed)
        if not hit:
            continue
        v = sorted(hit)[0]
        if v in seen:
            continue
        seen.add(v)
        out.append("число %s набрано цифрами вместо места {%s}"
                   % (_fmt(v), slot_of[computed[v]]))
    return out


def _filled_ask(ask, agg, totals, money, diag=None, extra=None, slot_mode=None):
    """Уточняющий вопрос с подставленными числами — или пусто, если он вышел с изъяном.

    Разница с текстом ответа в том, чем платим за изъян. У ответа изъян ведёт ко второй
    попытке и дальше к числам структурой: там есть что отдать вместо. У вопроса отдавать
    нечего, и выбор простой — показать заготовку («за какой период, с {date_min}?») или
    не задавать вопроса вовсе. Второе честнее: ответ при этом остаётся целым и уходит
    человеку, а сорвавшийся вопрос виден в `diag`, а не в мессенджере.
    """
    ask, slots_bad = _fill_figures(ask, agg, totals, bool(money), extra,
                                     slot_mode=slot_mode)
    if not (ask or "").strip():
        return ""
    flaws = formulation_flaws(ask, slots_bad)
    if flaws:
        if isinstance(diag, dict):
            diag["ask_dropped"] = flaws[:2]
        return ""
    return ask


def _ask_back(raw):
    """Уточняющий вопрос модели, если она его задала.

    Отдельной функцией, а не третьим членом кортежа `_split_answer`: у того пять путей
    возврата, и добавлять элемент в каждый — способ ошибиться на ровном месте. Здесь
    отсутствие поля и поломанная обёртка дают одно и то же — пусто, то есть «не спросила».
    """
    m = re.search(r"\{.*\}", raw or "", re.S)
    if not m:
        return ""
    try:
        d = json.loads(m.group(0))
    except ValueError:
        return ""
    return str((d.get("ask") if isinstance(d, dict) else "") or "").strip()


def compose(question, rows, agg, corrections=None, totals=None, coverage=None,
            measure_used=None, folders=None, money=True, src=None, slot_mode=None,
            atom_pairs=None):
    payload = []
    shown = rows[:ROWS_TO_MODEL]
    if slot_mode == "rank" and (agg or {}).get("grain") == "group":
        shown = []
    # Бюджет делится на число показываемых строк: короткие строки не занимают чужого
    # места, длинные не режутся по произвольной границе.
    per_row = max(320, ROWS_BUDGET // max(1, len(shown)))
    if slot_mode is None:
        slot_mode = "rank" if (agg or {}).get("grain") == "group" else "list"
    # При нескольких парах одиночные числовые места закрыты структурно (план §5).
    pairs_only = pair_slots_only(len(atom_pairs or []))
    for r in shown:
        # Строка, не влезшая в бюджет, помечается обрезанной. Прежде она обрывалась молча,
        # и модель цитировала обрубок как целое значение — «ООО Ромашка-Тор» вместо
        # «ООО Ромашка-Торг». Числа так не портятся (их ставит код), а вот имя, номер или
        # адрес уходили человеку укороченными и выглядели настоящими (п. 13).
        try:
            doc, dt, amt = r[5], r[3], r[2]
        except (TypeError, IndexError):
            continue
        if not isinstance(doc, str):
            doc = "" if doc is None else str(doc)
        head = doc[:per_row] + ("…" if len(doc) > per_row else "")
        tail = []
        # Стоп 1: amount= строки — только list. На sum/count/rank число строки — чужая роль.
        if slot_mode == "list" and money and _num(amt):
            tail.append("amount=%s" % ("%d" % _num(amt) if _num(amt) == int(_num(amt))
                                       else "%.2f" % _num(amt)))
        if dt:
            tail.append("date=%s" % dt)
        payload.append(head + ((" | " + " | ".join(tail)) if tail else ""))
    # 🔴 ЧИСЛО ПОКАЗАННЫХ СТРОК — НЕ ЧИСЛО ЗАПИСЕЙ, и подавать его как число записей
    # нельзя. `rows` обрезаны выборкой (`TOPK`), показываются из них первые
    # `ROWS_TO_MODEL`, а записей в множестве столько, сколько посчитала база, — это
    # `{count}`. Прежде в задании стояло «ROWS FOUND (40)», и модель честно пересказывала
    # эти 40 как ответ на «сколько»: `[замер 04.08]` на вопросе про склады ответ вышел
    # «есть только три документа приобретения» при 249 записях в множестве — размер
    # выборки выдан за размер множества (п. 13, молчаливая подмена). Числа здесь больше
    # нет вовсе: строки названы примерами, а за счётом модель идёт на место `{count}`.
    # Когда счёта нет (агрегат не посчитан), остаётся прежний вид — лучше него ничего.
    if agg and agg.get("grain") == "group":
        if slot_mode in ("sum", "rank"):
            head_line = ("GROUPS (one row = one value of the grouping axis; totals are "
                         "computed in the database over all matching records, not a "
                         "single line):")
        elif pairs_only:
            head_line = ("GROUPS (one row = one value of the grouping axis; totals are "
                         "computed in the database over all matching records, not a "
                         "single line):")
        else:
            head_line = ("GROUPS (one row = one value of the grouping axis; totals are "
                         "computed in the database over all matching records, not a single "
                         "line — the number of records is {count}):")
    else:
        if pairs_only:
            head_line = ("ROWS (examples from the matching set, not the whole of it):")
        elif agg and slot_mode in ("sum", "rank"):
            head_line = ("ROWS (examples from the matching set, not the whole of it):")
        else:
            head_line = ("ROWS (examples from the matching set, not the whole of it — the number "
                         "of records is {count}):" if agg else "ROWS FOUND (%d):" % len(rows))
    body = "QUESTION: %s\n\n%s\n%s" % (
        question, head_line, "\n".join("- " + p for p in payload))
    # Стоп 1: места групп — rank/list. На sum только безымянный {total}=итог множества.
    # При нескольких парах одиночные числовые места закрыты (план §5).
    if (not pairs_only and agg and agg.get("grain") == "group"
            and slot_mode in ("rank", "list")):
        for i, g in enumerate((agg.get("groups") or [])[:ROWS_TO_MODEL]):
            if not isinstance(g, dict):
                continue
            nm = (g.get("name") or "").strip()
            if nm:
                body += "\n  %s: total -> {total:g%d}" % (nm, i)
    # 🔴 ЗНАЧЕНИЙ ПОСЧИТАННОГО МОДЕЛЬ НЕ ВИДИТ — ТОЛЬКО РОЛИ И ИМЕНА.
    #
    # Правило «числа ставит код» держалось двумя опорами: словами в промте и подстановкой
    # `{total}`. Первая опора замерена `[замер 04.08, step6_live.py]` и оказалась дырявой:
    # на восьми вопросах модель семь раз оставила место — и один раз набрала 249 цифрами,
    # а на повторных прогонах это было то 1, то 0 раз. То есть слова работают почти
    # всегда, а «почти» и есть весь вопрос: пока число можно СПИСАТЬ, оно рано или поздно
    # списывается, и тогда защищает только гейт — а он смотрит, ЕСТЬ ли такое число в
    # данных, но не в своей ли оно роли (`F285`).
    #
    # Вторая попытка это не лечит: `[замер 04.08]` из двух случаев она исправила один.
    # Проверка тут вообще бессильна по устройству — роль числа в прозе кодом не
    # определяется, а определять её разбором текста значит гадать (п. 12) и привязываться
    # к языку. Поэтому убран сам источник: списывать больше неоткуда. Модели даётся имя
    # величины, перечень ролей и МЕСТО под каждую; значения подставляет код после ответа.
    # Это то же решение, что и везде в проекте, — запрет держится устройством, а не
    # просьбой, — доведённое до конца.
    #
    # Значения СТРОК при этом остаются: цитата из записи (номер документа, дата, имя
    # стороны) моделью и должна копироваться, это не арифметика, а выписка.
    has_money = bool(money) and bool(agg) and (
        agg.get("sum") or agg.get("max") or agg.get("min"))
    if pairs_only:
        # Несколько пар: модель видит только непрозрачные места {pair:pN}.
        # Подпись и число подставляет код одной операцией — перепутать роли нечем.
        body += ("\n\nCOMPUTED ANSWER PAIRS. Values and labels are not shown; each "
                 "placeholder below is replaced by the system with the whole pair "
                 "(label + value + unit + completeness note):")
        for i, _a in enumerate(atom_pairs or []):
            body += "\n  pair %d -> {pair:p%d}" % (i, i)
    elif agg and not has_money:
        # Нет выбранного поля (A2: want=count|list) или нет денежной колонки.
        # Передать sum=0 нельзя: модель ответит «0», и гейт согласится.
        body += ("\n\nCOMPUTED OVER ALL MATCHING ROWS. The values are not shown; each "
                 "placeholder below is replaced by the system with the exact figure:")
        kw = kind_word(src) if src else ""
        if kw and slot_mode != "rank":
            body += "\n  count_kind (record type noun) -> {count_kind}"
        # sum=0.0 делает has_money ложным; {count} на sum/rank — дыра 5ca1b66.
        if slot_mode not in ("sum", "rank"):
            body += "\n  count (number of records) -> {count}"
        if agg.get("date_min"):
            body += "\n  period                    -> {date_min} .. {date_max}"
        if agg.get("undated"):
            body += "\n  records without a date (not in the period filter) -> {undated}"
        if agg.get("outside_period"):
            body += ("\n  records matching everything except the period "
                     "-> {outside_period}")
        if money and slot_mode not in ("sum", "rank"):
            body += ("\n  (no numeric quantity matches the question for this record type — "
                     "no placeholder other than {count} is available here)")
    elif agg:
        body += ("\n\nCOMPUTED OVER ALL MATCHING ROWS for the quantity «%s». The values "
                 "are not shown; each placeholder below is replaced by the system with "
                 "the exact figure:" % (agg.get("measure") or "-"))
        kw = kind_word(src) if src else ""
        if kw and slot_mode != "rank":
            body += "\n  count_kind (record type noun) -> {count_kind}"
        # Стоп 1: на sum/rank счёт не слот модели (код может дописать после гейта).
        if slot_mode in ("count", "list"):
            body += "\n  count (number of records) -> {count}"
        # 🔴 ПО СКОЛЬКИМ ЗАПИСЯМ ПОСЧИТАНЫ sum И avg. `aggregate` считает `count_amount`
        # отдельно именно для этого («иначе среднее по 31 строке уходит как среднее по
        # 1344»), но до модели число не доходило вовсе — комментарий в `aggregate`
        # описывал требование, которого в коде не было. Ответ «средний чек 293 900 по
        # 1344 документам» при 31 строке с суммой неверен, а гейт его пропускает: оба
        # числа посчитаны базой, каждое по отдельности верно. Показываем, только когда
        # числа расходятся, — иначе это лишняя строка на каждый вопрос.
        ca = agg.get("count_amount")
        if ca is not None and ca != agg["count"]:
            body += ("\n  count_amount (records having this quantity; sum and avg are "
                     "over these, and there are fewer of them than records) "
                     "-> {count_amount}")
        if slot_mode == "rank":
            _ng = agg.get("n_groups")
            _shown_g = len(agg.get("groups") or [])
            if _ng is not None and _ng > _shown_g:
                body += ("\n  sum (TOTAL of the whole matching set, not one group) "
                         "-> {total}")
        else:
            body += "\n  sum (TOTAL)               -> {total}"
        if agg.get("grain") != "group":
            body += "\n  max (largest single)      -> {max}"
            body += "\n  min (smallest single)     -> {min}"
            body += "\n  avg (average)             -> {avg}"
        elif (slot_mode in ("rank", "list")
              and agg.get("n_groups") is not None
              and agg["n_groups"] > len(agg.get("groups") or [])):
            body += ("\n  n_groups (distinct groups in the whole matching set; "
                     "only some are listed above) -> {n_groups}")
        if agg.get("date_min"):
            body += "\n  period                    -> {date_min} .. {date_max}"
    if totals and money and not pairs_only:
        # Итоги по каждой величине — с ИМЕНАМИ из базы, но опять же без значений. Модель
        # сама возьмёт подходящую под вопрос величину; списать её итог ей неоткуда.
        body += ("\n\nCOMPUTED OVER ALL MATCHING ROWS, by quantity name — values not "
                 "shown, address them by name:")
        for m, v, mx, mn in totals:
            if agg and agg.get("grain") == "group":
                body += "\n  %s: total -> {total:%s}" % (m, m)
            else:
                body += ("\n  %s: total -> {total:%s}, largest single -> {max:%s}, "
                         "smallest single -> {min:%s}" % (m, m, m, m))
    if coverage:
        # НЕПОЛНОТА ЭТОЙ СУЩНОСТИ. Модель обязана предупредить на языке вопроса — сами мы
        # приписать не можем: своя фраза была бы на одном языке независимо от вопроса.
        # Числа отсюда разрешены гейту явно, поэтому предупреждение не будет отвергнуто
        # как выдумка.
        body += ("\n\nDATA COMPLETENESS WARNING: this kind of records is INCOMPLETE in "
                 "the search: %s rows exist in the source system, %s reached the search, "
                 "%s are missing (%s). The figures above are computed over what reached "
                 "the search only. You MUST warn the user about this in your answer, in "
                 "their language, stating the number of missing rows in digits."
                 % ("{in_1c}", "{in_search}", "{missing}",
                    coverage.get("reason") or "reason unknown"))
    # 🔴 ОГОВОРКИ К ОТВЕТУ ГОВОРИТ МОДЕЛЬ, А НЕ МЫ. Прежде обе дописывались нашей прозой
    # ПОСЛЕ модели — по-русски, в файле, где от русских умолчаний отказались сознательно:
    # `NO_DATA_TEXT` пуст, отказ и уточнение формулирует модель именно потому, что своя
    # фраза была бы на одном языке независимо от языка вопроса. На англоязычном клиенте
    # ответ выходил смешанным. Механизм тот же, что у предупреждения о неполноте выше.
    # Числа отсюда разрешены гейту, поэтому оговорка не будет отвергнута как выдумка.
    if measure_used:
        body += ("\n\nQUANTITY USED: the figures above are computed over the quantity named "
                 "'%s'. Name that quantity in your answer, in the user's language, so they "
                 "know WHICH value was summed." % measure_used)
    if folders:
        body += ("\n\nGROUPS EXCLUDED: %s records were folders (grouping nodes of the "
                 "catalogue), not real items, and are NOT included in the count above. You "
                 "MUST say this in your answer, in the user's language, stating the number "
                 "%s in digits — otherwise a user who knows the raw record count will think "
                 "the figure is wrong." % ("{folders}", "{folders}"))
    if corrections:
        # ВТОРАЯ ПОПЫТКА. Первая формулировка не прошла проверку кодом — говорим модели,
        # что именно не сошлось, и требуем опираться только на посчитанные базой числа.
        # Это не «правило на промте»: результат второй попытки проверяется тем же
        # гейтом, что и первой. Смысл — не поверить модели, а дать ответу дойти до
        # клиента, если он есть (решение владельца 27.07).
        body += ("\n\nYOUR PREVIOUS ANSWER WAS REJECTED BY A VERIFIER: %s"
                 "\nAnswer again. Use ONLY the computed figures above, each in its own "
                 "role. If a figure is not given above, do not state it at all."
                 # Причины отказа приходят из двух источников: ролевые проверки дают
                 # строки, а `gate` — сами необоснованные ЧИСЛА. Склеивать надо через
                 # str(): [замер] иначе `TypeError: expected str instance, float found`
                 # и HTTP 500 на любом вопросе с порогом суммы.
                 % "; ".join(str(c) for c in corrections))
    return ds_chat([{"role": "system", "content": ANSWER_SYS},
                    {"role": "user", "content": body}], max_tokens=800)


# ----------------------------------------------------------------- 5. гейт (кодом)
# Разделитель разрядов — любой пробел, включая неразрывный и узкий. Но склеивать
# можно ТОЛЬКО правильные группы по три цифры: иначе «итого 10 20 30 шт» слипается
# в 102030, и три настоящих числа исчезают из проверки.
# Число может быть записано как угодно: «1 629 700», «1,629,700», «1.629.700»,
# «16,29,700». Разделитель разрядов — вопрос локали, а продукт коробочный. Поэтому
# токен разбирается во ВСЕ допустимые прочтения, и он считается обоснованным, если
# ХОТЯ БЫ ОДНО из них есть в данных. Прежняя версия читала «1,629,700» как 1.629
# и объявляла выдумкой весь правильный англоязычный ответ.
# \ud83d\udd34 \u0417\u0430 \u0437\u0430\u043f\u044f\u0442\u043e\u0439 \u0438\u043b\u0438 \u0442\u043e\u0447\u043a\u043e\u0439 \u041e\u0411\u042f\u0417\u0410\u041d\u0410 \u0438\u0434\u0442\u0438 \u0446\u0438\u0444\u0440\u0430. \u041f\u0440\u0435\u0436\u0434\u0435 \u043a\u043b\u0430\u0441\u0441 \u0441\u0438\u043c\u0432\u043e\u043b\u043e\u0432 \u0434\u043e\u043f\u0443\u0441\u043a\u0430\u043b \u0438 \u043f\u0440\u043e\u0431\u0435\u043b,
# \u0438 \u0437\u0430\u043f\u044f\u0442\u0443\u044e \u0432\u043f\u0435\u0440\u0435\u043c\u0435\u0448\u043a\u0443, \u043f\u043e\u044d\u0442\u043e\u043c\u0443 \u00ab\u043d\u0430\u0439\u0434\u0435\u043d\u043e 36, 4 \u043e\u0442\u0441\u0443\u0442\u0441\u0442\u0432\u0443\u044e\u0442\u00bb \u0441\u043a\u043b\u0435\u0438\u0432\u0430\u043b\u043e\u0441\u044c \u0432 \u043e\u0434\u043d\u043e \u0447\u0438\u0441\u043b\u043e
# 36.4 \u2014 \u043a\u043e\u0442\u043e\u0440\u043e\u0433\u043e \u043c\u043e\u0434\u0435\u043b\u044c \u043d\u0435 \u043f\u0438\u0441\u0430\u043b\u0430, \u2014 \u0438 \u0433\u0435\u0439\u0442 \u043e\u0442\u0432\u0435\u0440\u0433\u0430\u043b \u0412\u0415\u0420\u041d\u042b\u0419 \u043e\u0442\u0432\u0435\u0442 \u0446\u0435\u043b\u0438\u043a\u043e\u043c.
# [\u0437\u0430\u043c\u0435\u0440 28.07] \u043f\u0440\u0435\u0434\u0443\u043f\u0440\u0435\u0436\u0434\u0435\u043d\u0438\u0435 \u043e \u043d\u0435\u043f\u043e\u043b\u043d\u043e\u0442\u0435 \u0434\u0430\u043d\u043d\u044b\u0445 \u043d\u0435 \u043c\u043e\u0433\u043b\u043e \u0434\u043e\u0439\u0442\u0438 \u0434\u043e \u043a\u043b\u0438\u0435\u043d\u0442\u0430 \u043d\u0438 \u0440\u0430\u0437\u0443:
# \u043e\u043d\u043e \u0432\u0441\u0435\u0433\u0434\u0430 \u0441\u0442\u0430\u0432\u0438\u0442 \u0434\u0432\u0430 \u0447\u0438\u0441\u043b\u0430 \u0440\u044f\u0434\u043e\u043c \u0447\u0435\u0440\u0435\u0437 \u0437\u0430\u043f\u044f\u0442\u0443\u044e. \u041e\u0442\u0432\u0435\u0440\u0433\u043d\u0443\u0442\u044b\u0439 \u0432\u0435\u0440\u043d\u044b\u0439 \u043e\u0442\u0432\u0435\u0442 \u2014 \u0434\u0435\u0444\u0435\u043a\u0442
# \u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0438, \u0430 \u043d\u0435 \u043e\u0441\u0442\u043e\u0440\u043e\u0436\u043d\u043e\u0441\u0442\u044c (\u043f. 21).
# \u0417\u0430\u043f\u044f\u0442\u0430\u044f \u0441 \u043f\u0440\u043e\u0431\u0435\u043b\u043e\u043c \u043d\u0435 \u044f\u0432\u043b\u044f\u0435\u0442\u0441\u044f \u0434\u0435\u0441\u044f\u0442\u0438\u0447\u043d\u044b\u043c \u0440\u0430\u0437\u0434\u0435\u043b\u0438\u0442\u0435\u043b\u0435\u043c \u043d\u0438 \u0432 \u043e\u0434\u043d\u043e\u0439 \u0437\u0430\u043f\u0438\u0441\u0438 \u0447\u0438\u0441\u0435\u043b:
# \u00ab36,4\u00bb \u043f\u0438\u0448\u0443\u0442 \u0441\u043b\u0438\u0442\u043d\u043e, \u00ab36, 4\u00bb \u2014 \u044d\u0442\u043e \u043f\u0435\u0440\u0435\u0447\u0438\u0441\u043b\u0435\u043d\u0438\u0435.
NUMTOK = re.compile(r"\d(?:[ \u00a0\u2007\u2009\u202f\u200b']\d|[.,]\d|\d)*")
SEP = "  \u00a0\u2007\u2009\u202f\u200b',."
DATE3 = re.compile(r"\b(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})\b|\b(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})\b")
DATE2 = re.compile(r"\b(\d{1,2})[.\-/](\d{1,2})\b")



register_zone('ask.z18_compose', globals())
