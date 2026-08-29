"""Zone 02: Intent (intent)."""
from __future__ import annotations

from ask._imports import *
from ask._wire import register_zone, apply_bindings

apply_bindings(globals())

def _json_blocks(raw):
    """Сбалансированные объекты `{...}` из ответа модели, в порядке появления.

    Скобки внутри строковых значений и экранирование учитываются, поэтому текст вокруг
    JSON (заборы ```json, вступление, рассуждение со скобками) на разбор не влияет.
    """
    out, depth, start, in_str, esc = [], 0, None, False, False
    for i, ch in enumerate(raw or ""):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}" and depth:
            depth -= 1
            if depth == 0 and start is not None:
                out.append(raw[start:i + 1])
                start = None
    return out


def _intent_text(v):
    """Значение поля как непустая строка. Список — первый непустой элемент; иначе None."""
    if isinstance(v, (list, tuple)):
        for item in v:
            s = _intent_text(item)
            if s:
                return s
        return None
    if v is None or isinstance(v, (dict, bool)):
        return None
    s = str(v).strip()
    return s or None


def _intent_number(v):
    """Число из значения любого вида: «500 000», «1 234,56» → float. None — числа нет."""
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if not isinstance(v, str):
        return None
    s = v.replace(" ", "").replace(" ", "").replace(" ", "")
    if s.count(",") == 1 and "." not in s:
        s = s.replace(",", ".")
    else:
        s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def _intent_date(v):
    """Дата вида YYYY-MM-DD (и только такая) — приведённая к канону. Иначе None.

    Другие написания сюда не пускаются намеренно. «01.02.2024» — это и 1 февраля, и
    2 января: разобрать его значило бы выбрать наугад между двумя прочтениями, а это
    п. 12 контракта. Отброшенная граница периода видна человеку через `lost`.
    """
    s = _intent_text(v)
    if not s:
        return None
    try:
        return time.strftime("%Y-%m-%d", time.strptime(s, "%Y-%m-%d"))
    except ValueError:
        return None


def _intent_terms(raw_terms, lost, fixed):
    """Понятия вопроса: список групп написаний. Мусор отбрасывается, потери — в `lost`."""
    if raw_terms is None:
        return []
    if isinstance(raw_terms, (str, int, float)):
        # Одно понятие, присланное строкой. Раньше строка попадала в цикл как
        # последовательность и рассыпалась на буквы.
        fixed.append("terms as text")
        raw_terms = [[raw_terms]]
    if not isinstance(raw_terms, (list, tuple)):
        lost.append("terms")
        return []
    groups, dropped_alts = [], 0
    for item in raw_terms:
        alts_in = item if isinstance(item, (list, tuple)) else [item]
        alts = []
        for a in alts_in:
            s = _intent_text(a)
            if s is None:
                dropped_alts += 1
                continue
            if s not in alts:
                alts.append(s)
        if not alts:
            continue
        if len(alts) > INTENT_ALTS:
            dropped_alts += len(alts) - INTENT_ALTS
            alts = alts[:INTENT_ALTS]
        groups.append(alts)
    if len(groups) > INTENT_GROUPS:
        # Срезанное понятие — это снятое условие отбора: ответ считается по более
        # широкому множеству, чем спросили. Молчать об этом нельзя (п. 13).
        lost.append("concepts:%d" % (len(groups) - INTENT_GROUPS))
        groups = groups[:INTENT_GROUPS]
    if dropped_alts:
        fixed.append("spellings:%d" % dropped_alts)
    return groups


def _intent_word(s):
    """Слово для сравнения: только буквы и цифры, нижний регистр. Списка слов здесь нет."""
    return re.sub(r"[^\w]+", " ", (s or ""), flags=re.U).lower().strip()


# 🔴 ОДНО ПОНЯТИЕ, РАЗЛОЖЕННОЕ ПО РАЗНЫМ ГРУППАМ, — ЭТО ЛИШНЕЕ УСЛОВИЕ «И».
# Между группами отбор идёт «И», внутри группы — «ИЛИ» (`probe`, `match_expr`).
# [замер 04.08] вопрос приёмки №40 «Сколько мы продали Альтаиру?» разбирается в ДВЕ
# группы — «Альтаир» и «Альтаиру», — и строка обязана содержать оба написания сразу.
# Такого не бывает: строка несёт одно из них, и вопрос про существующего клиента уходил
# в отказ «значения из вопроса не найдены» (п. 21).
#
# 🔴 РОДСТВО РЕШАЕТ ДВИЖОК, А НЕ МОЁ СРАВНЕНИЕ СТРОК. Первая редакция считала родными
# написания, входящие одно в другое, — то есть свой разбор слова поверх движка, у
# которого для этого есть штатное средство (доки SereneDB, `sql/functions/search/full-text`
# → `ts_lexize(dictionary, text)`; шаблоны словарей — `sql/statements/
# create_text_search_dictionary`). Словарь со стеммингом в проекте УЖЕ ЗАВЕДЁН —
# `search_dict_stem` (`corpus_init.sql`), ровно для сопоставления слова человека с
# названием. Проверено на живой сборке 26.07.3 `[замер 04.08]`:
# «Альтаир»/«Альтаиру» → `{альтаир}` оба, «товар»/«товаров» → `{товар}` оба,
# «Ромашка»/«Сбербанк» → `{ромашк}`/`{сбербанк}` (разные), «BOSCH»/«техника» — разные.
# Подмножество считается родством: «ООО "Ромашка"» → `{оо,ромашк}` ⊇ `{ромашк}`.
#
# Ошибка в сторону слияния расширяет отбор (то же понятие, больше написаний), в обратную —
# отбирает пустоту, поэтому при недоступности словаря группы остаются как есть.
#
# Ф6.3: при ASK_SOLR_SYNONYMS=1 и имени ASK_SOLR_SYNONYMS_DICT — дополнительно
# `ts_lexize` по словарю синонимов; термы объединяются со стеммом (фактура §3.2/§6:
# стемминг до класса, не вместо; списков слов в коде нет).
def same_concept_groups(groups):
    """Свести группы, которые движок считает одним понятием. (группы, сколько сведено)."""
    if len(groups) < 2:
        return groups, 0
    flat = [a for g in groups for a in g]
    use_syn = ASK_SOLR_SYNONYMS and bool(ASK_SOLR_SYNONYMS_DICT)
    cols = []
    for a in flat:
        cols.append("ts_lexize(%s, %s)" % (lit(STEM_DICT), lit(a)))
        if use_syn:
            cols.append("ts_lexize(%s, %s)" % (lit(ASK_SOLR_SYNONYMS_DICT), lit(a)))
    try:
        row = psql("SELECT " + ", ".join(cols))[0]
    except RuntimeError:
        return groups, 0
    merged, stems, k = [], [], 0
    for g in groups:
        merged.append(list(g))
        g_stems = []
        for _n in range(len(g)):
            s = _stem_set(row[k])
            k += 1
            if use_syn:
                s = s | _stem_set(row[k])
                k += 1
            g_stems.append(frozenset(s))
        stems.append(g_stems)
    i = 0
    while i < len(merged):
        j = i + 1
        while j < len(merged):
            родня = any(sa and sb and (sa <= sb or sb <= sa)
                        for sa in stems[i] for sb in stems[j])
            if родня:
                merged[i] += [b for b in merged.pop(j) if b not in merged[i]]
                stems[i] += stems.pop(j)
            else:
                j += 1
        i += 1
    return merged, len(groups) - len(merged)


def _stem_set(v):
    """Ответ `ts_lexize` — список термов. psql отдаёт его строкой вида `{a,b}`."""
    if isinstance(v, (list, tuple)):
        return {str(x) for x in v if str(x)}
    s = str(v or "").strip()
    if s.startswith("{") and s.endswith("}"):
        s = s[1:-1]
    return {p.strip().strip('"') for p in s.split(",") if p.strip()}


_NON_DATA_MARKERS = (
    "напиши", "расскаж", "стих", "poem", "шутк", "анекдот", "придумай",
    "сочини", "опиши красив", "рифм",
)

# Разговорный «как …» (how), не «кто/что …» (who/what) — грамматический класс,
# не список предметных слов.
_CONVERSATIONAL_HOW = re.compile(
    r"(?:^|[\s,.;:!?«\"(])как(?:[\s,.;:!?»\")]|$)", re.I | re.U)


def _creative_non_data_question(question):
    q = " ".join(str(question or "").lower().split())
    return bool(q) and any(m in q for m in _NON_DATA_MARKERS)


def _accounting_word_known_to_base(word):
    """Слово — род или величина, которые ЭТА база знает (не метка модели)."""
    w = (word or "").strip()
    if not w:
        return False
    return _base_knows_kind_or_measure(w)


def _intent_has_known_accounting_anchor(intent):
    """Учётная опора в интенте: значения, род или ось, известные словарю базы."""
    if not isinstance(intent, dict):
        return False
    if intent.get("terms"):
        return True
    kind = _intent_text(intent.get("kind"))
    if kind and _accounting_word_known_to_base(kind):
        return True
    axis = _intent_text(intent.get("action_axis"))
    if axis and _accounting_word_known_to_base(axis):
        return True
    measure = _intent_text(intent.get("measure"))
    if measure and _accounting_word_known_to_base(measure):
        return True
    return False


def _intent_coordinates_empty(intent):
    """Нет значений, величины и числового порога — только форма вопроса."""
    if not isinstance(intent, dict):
        return False
    if intent.get("terms"):
        return False
    measure = _intent_text(intent.get("measure"))
    if measure and _accounting_word_known_to_base(measure):
        return False
    amt = intent.get("amount") or {}
    if amt.get("op") and amt.get("value") is not None:
        return False
    if not amt.get("op") and amt.get("value") is not None:
        return False
    return True


def _base_business_topic_words(limit=5):
    """Живые учётные темы ЭТОЙ базы — ярлыки business-сущностей слоя поиска.

    Источник: `search_entity_alias` × `search_entity_class.cls=business`, не
    зашитый перечень «продажи/остатки». Без базы (офлайн) — пусто: переспрос
  не поднимаем без доказанных тем (п. 12).
    """
    lim = max(1, min(int(limit or 5), 12))
    topics, seen = [], set()
    try:
        rows = psql(
            "SELECT DISTINCT ON (a.src_table) a.aliases, a.best_used_for "
            "FROM search_entity_alias a "
            "INNER JOIN %s c ON c.src_table = a.src_table AND c.cls = 'business' "
            "WHERE coalesce(a.aliases, '') <> '' "
            "   OR coalesce(a.best_used_for, '') <> '' "
            "ORDER BY a.src_table LIMIT %d"
            % (CLASS_TABLE, lim * 4))
    except RuntimeError:
        return []
    for row in rows or []:
        for raw in (row[1], row[0]) if len(row) > 1 else (row[0],):
            for part in re.split(r"[,;|/]", str(raw or "")):
                w = part.strip()
                key = w.lower()
                if len(w) < 3 or key in seen:
                    continue
                seen.add(key)
                topics.append(w)
                if len(topics) >= lim:
                    return topics
    return topics


def conversational_business_vague(intent, question):
    """Разговорный вопрос о делах компании без координат учёта.

    Отличается от внешнего факта («кто президент») классом вопроса how, не who,
    и от творческого запроса маркерами содержания. Именованный род записей,
    которого база не знает, — не «как дела», а чужая тема (no_data).
    """
    if _creative_non_data_question(question):
        return False
    if not isinstance(intent, dict):
        return False
    q = " ".join(str(question or "").split())
    conv_how = bool(_CONVERSATIONAL_HOW.search(q))
    about = (intent.get("about") or "data").strip().lower()
    if about != "data":
        # coverage от модели на разговорном «как …» без координат — догадка (п. 12).
        if not (conv_how
                and _intent_coordinates_empty(intent)
                and not _intent_has_known_accounting_anchor(intent)):
            return False
    want = (intent.get("want") or "list").strip().lower()
    if want not in ("list", ""):
        # want модели без учётных координат не гасит разговорный переспрос.
        if _intent_has_known_accounting_anchor(intent) or not _intent_coordinates_empty(intent):
            return False
    if not _intent_coordinates_empty(intent):
        return False
    kind = _intent_text(intent.get("kind"))
    if kind and _accounting_word_known_to_base(kind):
        return False
    ac = (intent.get("action_class") or "none").strip().lower()
    if ac in ("event", "object") and _intent_has_known_accounting_anchor(intent):
        return False
    axis = _intent_text(intent.get("action_axis"))
    if axis and _accounting_word_known_to_base(axis):
        return False
    return conv_how


def _enrich_conversational_business(intent, question):
    """Разговорный вопрос с темами базы → координата для переспроса, не no_data.

    want=count без kind/terms — штатный путь `serene_enough.verdict_before`
    (уточнение темы/периода), а `question_expects_accounting_data` пропускает
    вопрос дальше non_accounting_question.
    """
    if not conversational_business_vague(intent, question):
        return intent
    topics = _base_business_topic_words(3)
    if not topics:
        return intent
    out = dict(intent)
    parse = dict(out.get("parse") or {})
    parse["conversational_topics"] = topics
    parse["fixed"] = list(parse.get("fixed") or []) + ["conversational:count"]
    out["parse"] = parse
    out["want"] = "count"
    return out


def question_expects_accounting_data(intent, question, diag=None):
    """Вопрос про учётные данные, а не off-topic / творческий запрос (K4-2).

    Разговорный «как дела» с живыми business-темами базы — учётный (переспрос),
    внешний факт без темы в базе и творческий запрос — нет.
    """
    diag = diag or {}
    intent = intent or {}
    q = " ".join(str(question or "").lower().split())
    if not q:
        return False
    if _creative_non_data_question(question):
        return False
    want = (intent.get("want") or "").strip().lower()
    if want in ("count", "sum", "max", "min", "avg"):
        return True
    if want == "list":
        if (intent.get("kind") or "").strip() or intent.get("terms"):
            return True
    elif want:
        return True
    if intent.get("terms"):
        return True
    if diag.get("sales_canon_locked") or diag.get("sales_measure_canon"):
        return True
    if sales_sum_intent(intent, question) or rank_question_text(question):
        return True
    if question_asks_stock_balance(question):
        return True
    if re.search(r"\b(сколько|покажи|дай|топ|сумм|выруч|продаж|остат|заказ)\b", q):
        return True
    if conversational_business_vague(intent, question) and _base_business_topic_words(1):
        return True
    return False


def _base_knows_kind_or_measure(word):
    """Знает ли ЭТА база слово родом записей или именем величины.

    Источник — словарь базы, не метка парсера: каталоги/движения по стемам
    `label|aliases|best_used_for`, величины — `search_measure_alias`.
    Офлайн (psql недоступен) — прежнее поведение: считать известным,
    чтобы замки без базы видели то же правило, что и раньше.
    """
    w = (word or "").strip()
    if not w:
        return True
    try:
        if entity_form_catalogs_for_kind(w, allow_meaning=False):
            return True
        if entity_form_movements_for_kind(w, allow_meaning=False):
            return True
        row = psql(
            "SELECT count(*) FROM search_measure_alias WHERE list_has_any("
            " list_filter(ts_lexize(%s, %s), x -> length(x) >= 3),"
            " list_filter(ts_lexize(%s, concat_ws(' ', measure, aliases)),"
            "             x -> length(x) >= 3))"
            % (lit(STEM_DICT), lit(w), lit(STEM_DICT)))
        return bool(row and row[0] and int(row[0][0] or 0) > 0)
    except RuntimeError:
        return True


def _normalize_intent(d, question=""):
    """Ответ модели → структура шага 1 с пометкой, что из вопроса не доехало."""
    lost, fixed = [], []
    out = {"terms": _intent_terms(d.get("terms"), lost, fixed)}

    kind_raw, measure_raw = d.get("kind"), d.get("measure")
    if isinstance(kind_raw, (list, tuple)) and len(kind_raw) > 1:
        fixed.append("kind alternatives:%d" % (len(kind_raw) - 1))
    out["kind"] = _intent_text(kind_raw)
    if isinstance(measure_raw, (list, tuple)) and len(measure_raw) > 1:
        fixed.append("measure alternatives:%d" % (len(measure_raw) - 1))
    out["measure"] = _intent_text(measure_raw)

    # 🔴 РОД ЗАПИСЕЙ И ИМЯ ВЕЛИЧИНЫ — НЕ ЗНАЧЕНИЯ, И В `terms` ИМ НЕ МЕСТО.
    # `terms` — то, что стоит В САМОЙ ЗАПИСИ (имя контрагента, товар, номер документа);
    # по ним идёт буквальный отбор строк. Род записей туда попадать не может: запись не
    # содержит слова, называющего её род (об этом же говорит промт — и одного промта, как
    # обычно, недостаточно). [замер 04.08] на приёмочном наборе модель кладёт в `terms`
    # имя величины у вопроса 2 («НДС» при `measure`=«НДС»): буквальный отбор сужается до
    # строк со словом «НДС», а не найдя таких, система отвечает «значения из вопроса не
    # найдены» — ОТКАЗ при наличии данных (п. 21).
    # Сравнение — по совпадению целиком, а не по вхождению: «Приобретение товаров» при
    # роде «приобретение» — законное значение, и вырезать его значило бы снять условие.
    #
    # 🔴 РЕШАЕТ СЛОВАРЬ БАЗЫ, А НЕ МЕТКА ПАРСЕРА (28.08, вечер). [замер AB_PROBE okna]
    # парсер назвал родом «петли» (такого рода в базе нет), прежнее правило вынуло
    # слово из терминов — и предмет вопроса исчез: «сколько петель осталось на складе»
    # пошло в уточнение склада вместо честного «нет данных» (бой на терминах=[Петля]
    # отвечал no_data). Вынимаем слово только когда ЭТА база знает его родом записей
    # (каталог/движение по стемам label|aliases|best_used_for) или именем величины
    # (`search_measure_alias`). Незнакомое слово остаётся значением: словарь базы —
    # источник истины, метка модели — догадка (п. 12).
    названо = {_intent_word(x) for x in (out["kind"], out["measure"]) if x}
    if названо:
        known = {w for w in названо if _base_knows_kind_or_measure(w)}
        groups, dropped = [], 0
        for g in out["terms"]:
            keep = [a for a in g if _intent_word(a) not in known]
            dropped += len(g) - len(keep)
            if keep:
                groups.append(keep)
        if dropped:
            fixed.append("kind/measure in terms:%d" % dropped)
        out["terms"] = groups

    want = (_intent_text(d.get("want")) or "").lower()
    if want and want not in _WANT_OK:
        # Чужое значение — не отказ: счёт величины решается шагом 4 по самому вопросу.
        fixed.append("want:" + want[:16])
        want = ""
    out["want"] = want or "list"

    about = (_intent_text(d.get("about")) or "").lower()
    out["about"] = about if about in _ABOUT_OK else "data"

    period, p_in = {}, d.get("period")
    if isinstance(p_in, dict):
        for edge in ("from", "to"):
            raw_edge = p_in.get(edge)
            if raw_edge is None:
                continue
            iso = _intent_date(raw_edge)
            if iso:
                period[edge] = iso
            else:
                lost.append("period." + edge)
    elif p_in:
        lost.append("period")
    if period.get("from") and period.get("to") and period["from"] > period["to"]:
        # Перевёрнутый период даёт пустое множество, то есть «данных нет» на вопрос,
        # у которого данные есть. Менять границы местами — догадка (п. 12).
        lost.append("period.order")
        period = {}
    out["period"] = period

    amount, a_in = {}, d.get("amount")
    if isinstance(a_in, dict):
        op = _intent_text(a_in.get("op"))
        val = _intent_number(a_in.get("value"))
        val2 = _intent_number(a_in.get("value2"))
        if op and op not in _AMOUNT_OPS:
            lost.append("amount.op")
        elif op and val is None:
            lost.append("amount.value")
        elif op == "between" and val2 is None:
            lost.append("amount.value2")
        elif op:
            amount = {"op": op, "value": val, "value2": val2}
        elif val is not None:
            # Число без порога — K рейтинга, не условие отбора. _num_pred требует op.
            amount = {"op": None, "value": val, "value2": val2}
    elif a_in:
        lost.append("amount")
    out["amount"] = amount

    period2, p2_in = {}, d.get("period2")
    if isinstance(p2_in, dict):
        for edge in ("from", "to"):
            raw_edge = p2_in.get(edge)
            if raw_edge is None:
                continue
            iso = _intent_date(raw_edge)
            if iso:
                period2[edge] = iso
            else:
                lost.append("period2." + edge)
    elif p2_in:
        lost.append("period2")
    if period2.get("from") and period2.get("to") and period2["from"] > period2["to"]:
        lost.append("period2.order")
        period2 = {}
    out["period2"] = period2

    ac = (_intent_text(d.get("action_class")) or "").lower()
    out["action_class"] = ac if ac in _ACTION_CLASS_OK else "none"
    out["action_axis"] = _intent_text(d.get("action_axis")) or ""

    # 🔴 УСЛОВИЕ, КОТОРОГО В ВОПРОСЕ НЕ БЫЛО, — ДОГАДКА, И ОНА ВИДНА (п. 12).
    # [замер 04.08] «Сколько мы продали за год?» разбирается в период
    # 2025-08-04…2026-08-04 — год НАЗАД ОТ СЕГОДНЯ. В вопросе такого года нет, данные
    # кончаются 2019-11-18, и отбор по этому периоду даёт пустоту: система отвечает
    # «данных нет» на вопрос, у которого данные есть за пять лет. Приёмка ждёт здесь
    # уточнения (`ACCEPTANCE_UT` №28) — «за год» это и календарный год, и последние
    # двенадцать месяцев, и любой из пяти.
    # Признак считается кодом и без языка: цифры года ищутся в самом вопросе.
    цифры = set(re.findall(r"\d+", (question or "").replace(" ", "").replace(" ", "")))
    assumed = [e for e, v in period.items()
               if not any(v[:4] in x for x in цифры)]
    out["parse"] = {"ok": True, "lost": lost, "fixed": fixed,
                    "assumed": ["period." + e for e in sorted(assumed)]}
    return out


def _one_intent(msgs, question):
    """Один разбор вопроса моделью, проверенный по типам."""
    raw = ds_chat(msgs, max_tokens=INTENT_MAX_TOKENS)
    d = _first_intent_object(raw)
    if d is None:
        # 🔴 ВТОРАЯ ПОПЫТКА, А НЕ ПУСТОЙ РАЗБОР. Прежняя редакция при неразобранном
        # ответе возвращала `{"terms": [], …}` — то есть тот же вид, что и у честного
        # «в вопросе нет понятий», и вопрос отвечался вслепую по вектору. Разница
        # между «модель не ответила» и «спросили без условий» стоит одного повтора:
        # шаг 1 занимает 1,6 с из 17,6 с ответа.
        raw2 = ds_chat(msgs + [{"role": "assistant", "content": (raw or "")[:400]},
                               {"role": "user", "content": "Return the JSON object."}],
                       max_tokens=INTENT_MAX_TOKENS)
        d = _first_intent_object(raw2)
    if d is None:
        raise RuntimeError("модель не вернула разбор вопроса")
    return _normalize_intent(d, question)


def _field_key(v):
    return json.dumps(v, ensure_ascii=False, sort_keys=True)


def _field_lead(samples, f):
    """(победитель, отрыв от второго) по полю. Отрыв — насколько согласие устойчиво."""
    keys = [_field_key(s.get(f)) for s in samples]
    counts = {}
    for k in keys:
        counts[k] = counts.get(k, 0) + 1
    order = sorted(counts, key=lambda k: (-counts[k], keys.index(k)))
    lead = counts[order[0]] - (counts[order[1]] if len(order) > 1 else 0)
    return order[0], lead, len(counts)


def _merge_intents(samples):
    """Согласие нескольких разборов ОДНОГО вопроса, поле за полем.

    Побеждает значение, встретившееся чаще; при равенстве — то, что пришло раньше.
    Поля, по которым согласия не было, перечислены в `parse.unstable`: это не отказ,
    а след, по которому видно, какой вопрос система читает по-разному.
    """
    if len(samples) == 1:
        one = dict(samples[0])
        one["parse"] = dict(one.get("parse") or {}, unstable=[], samples=1)
        return one
    out, unstable = {}, []
    for f in _INTENT_FIELDS:
        best, _, distinct = _field_lead(samples, f)
        if distinct > 1:
            unstable.append(f)
        out[f] = json.loads(best)
    # Пометки разбора (что потерялось, что чинилось, что додумано) берутся у того
    # образца, который ближе всех к итогу: они описывают переход «ответ модели →
    # структура», и складывать их от разных образцов значило бы описывать разбор,
    # которого не было.
    near = max(samples, key=lambda s: sum(1 for f in _INTENT_FIELDS
                                          if _field_key(s.get(f)) == _field_key(out[f])))
    out["parse"] = dict(near.get("parse") or {}, unstable=unstable, samples=len(samples))
    return out


def parse_intent(question, today):
    """Текст вопроса → структура отбора. К базе и к данным этот шаг не обращается.

    Модель видит только вопрос: ни схемы, ни имён таблиц, ни строк (п. 19). Ответ
    модели проверяется здесь по типам; когда разобрать нечего — `RuntimeError`, и
    сервис отвечает честным отказом вместо ответа вслепую (п. 18).

    🔴 РАЗБОР БЕРЁТСЯ ПО СОГЛАСИЮ НЕСКОЛЬКИХ ПРОГОНОВ, А НЕ ОДНОГО.
    [замер 04.08, `intent_parse_bench.py`, 58 вопросов по 3 повтора] один и тот же
    вопрос при `temperature=0` разбирается по-разному в **18 случаях из 58**: расходятся
    `kind` («выручка»/«продажи», «номенклатура»/«позиции номенклатуры») и состав `terms`.
    Это нижняя граница разброса всего ответа: разный `kind` — это разный вектор на шаге 3,
    разные кандидаты на шаге 4 и, в конце, разное число. Прежде разброс приписывали одному
    шагу 4 (11,8 с), а его половина заводилась здесь, на самом дешёвом шаге (1,6 с).

    🔴 РАЗНИЦА СЛОВОФОРМ — НЕ МЕЛОЧЬ, И ЭТО ЗАМЕРЕНО. [замер 04.08] «товар» и «товаров»
    как запрос по смыслу дают из 32 кандидатов лишь 22 общих, а «выручка» и «продажи» —
    5 из 32. То есть согласие тут не про красоту разбора: от него зависит, какие сущности
    вообще доедут до выбора.

    Сколько прогонов делать, решает ОТРЫВ, а не постоянное число: прогоны идут, пока
    лидирующее значение не оторвётся от второго на `INTENT_LEAD`. [замер 04.08, по 9
    прогонов на вопрос] расклад расходящихся полей — 7:2, а не пополам: «отгрузка»×7 /
    «отгрузки»×2, «товаров»×7 / «товар»×2, «продажи»×6 / «выручка»×3. При таком раскладе
    отрыв в два прогона набирается за три-четыре обращения, а решает большинство, а не
    случайный первый ответ.

    🔴 ОДИН И ТОТ ЖЕ ВОПРОС РАЗБИРАЕТСЯ ОДИНАКОВО — ЭТО ДЕРЖИТСЯ ПАМЯТЬЮ, А НЕ
    ВЕЗЕНИЕМ. Даже отрыв оставляет несколько процентов на случай, а п. 3 контракта требует
    детерминированности. Разбор зависит ровно от двух вещей — текста вопроса и сегодняшней
    даты, — поэтому повтор берётся из памяти по этому ключу. Данные в ключ не входят и
    входить не могут: шаг 1 их не видит. Память чистится сменой даты и держит `INTENT_MEMO`
    последних вопросов; `ASK_INTENT_MEMO=0` выключает её — этим прибор меряет согласие
    модели, а не работу памяти.
    """
    memo_key = (today, question)
    if INTENT_MEMO > 0:
        hit = _INTENT_MEMO.get(memo_key)
        if hit is not None:
            return json.loads(hit)
    msgs = [{"role": "system", "content": INTENT_SYS},
            {"role": "user", "content": "today=%s\n\nQuestion: %s" % (today, question)}]
    samples = [_one_intent(msgs, question)]
    while len(samples) < max(1, INTENT_SAMPLES):
        if min(_field_lead(samples, f)[1] for f in _INTENT_FIELDS) >= INTENT_LEAD:
            break
        samples.append(_one_intent(msgs, question))
    out = _merge_intents(samples)
    # Сведение словоформ в одно понятие — после согласия и один раз на вопрос: словарь
    # спрашивается у движка, и делать это на каждый прогон разбора незачем.
    groups, сведено = same_concept_groups(out.get("terms") or [])
    if сведено:
        out["terms"] = groups
        out["parse"]["fixed"] = list(out["parse"].get("fixed") or []) + [
            "same concept groups:%d" % сведено]
    out = _enrich_conversational_business(out, question)
    if INTENT_MEMO > 0:
        if len(_INTENT_MEMO) >= INTENT_MEMO:
            _INTENT_MEMO.clear()
        _INTENT_MEMO[memo_key] = json.dumps(out, ensure_ascii=False)
    return out


def _first_intent_object(raw):
    """Объект ответа, больше других похожий на разбор вопроса. None — такого нет.

    Похожесть считается по числу полей разбора: болтливый ответ может нести и обрывок
    вида `{"terms": []}`, и полный объект следом, а взятый по порядку первый обрывок
    потерял бы `kind` — то самое поле, по которому идут шаги 3 и 4.
    """
    best, best_score = None, -1
    for block in _json_blocks(raw):
        try:
            d = json.loads(block)
        except ValueError:
            continue
        if not isinstance(d, dict):
            continue
        score = sum(1 for k in ("terms", "kind", "want", "measure", "period",
                                "amount", "about", "action_class", "action_axis") if k in d)
        if score > best_score:
            best, best_score = d, score
    return best


# ----------------------------------------------------------------- 2-3. поиск и счёт

register_zone('ask.z02_intent', globals())
