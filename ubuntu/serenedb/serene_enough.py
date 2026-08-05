#!/usr/bin/env python3
"""ШАГ «ДОСТАТОЧЕН ЛИ ВОПРОС ДЛЯ ОТВЕТА» — отдельный шаг конвейера, до и после поиска.

Зачем он заведён (05.08). Сегодня система узнаёт, что у вопроса нет одного верного
ответа, на шаге 4 — после трёх вызовов модели и всего поиска, — и переспрашивает в НАШИХ
терминах: «Закупки или Приобретение Товаров Услуг?». Владелец 05.08 сформулировал иначе,
на вопросе приёмки №5 «Сколько штук товара мы продали?»: «такой вопрос непонятен вообще.
нужно в таких случаях отправить на уточнения. что за товар вы имеете ввиду, за какой
период». То есть неоднозначность бывает не в кандидатах, а в самом вопросе, и спрашивать
о ней надо словами человека («какой товар, за какой период»), а не именами источников.

🔴 РЕШАЕТ КОД, А НЕ МНЕНИЕ МОДЕЛИ. «Спроси модель, достаточен ли вопрос» — это правило в
промте, а такие правила по закону проекта не работают (указание владельца 03.08, хук
`check-prompt-rules.sh`). Поэтому здесь разделены две вещи:
  * модель — языковой инструмент: она ОПИСЫВАЕТ вопрос (на что он указывает, назван ли
    период, названа ли величина). Ни одного слова о том, отвечать или переспрашивать, в
    её задании нет;
  * вердикт собирает код — из этого описания и из чисел, посчитанных базой.

🔴 ПРИЗНАК «ПОЛЕ РАЗБОРА ПУСТО» САМ ПО СЕБЕ НЕГОДЕН. «Сколько у нас контрагентов?» — тоже
без периода и без предмета, и это нормальный вопрос с одним верным ответом. Различает не
пустота поля, а то, на что вопрос указывает: у №5 «товара» — ОДИН неназванный предмет из
многих, у №9 «контрагентов» — весь класс целиком. Первое требует выбора, которого человек
не сделал; второе выбора не требует.

🔴 ЦЕНА ПРОВЕРЯЕТСЯ ДВУМЯ ЧИСЛАМИ, А НЕ ОДНИМ. Замер владельца 05.08: крайняя форма
«сомнительно — спроси» даёт 1 неверный ответ при 2 верных и 41 уточнении из 44. По счёту
ошибок это лучший результат за всё время, а продукта нет: система перестала отвечать
(п. 21 `TARGET.md` ставит ответ выше уточнения). Поэтому у шага узкий вход, и оба числа —
неверные и верные — снимаются вместе.

Устройство — две половины:
  1. `verdict_before` — до поиска, по одному разбору шага 1, без базы и без модели.
     Ловит вырожденный случай: вопрос просит итог, но не называет ни рода записей, ни
     значений — искать нечего, и весь прогон экономится целиком;
  2. `verdict_after` — после отбора и счёта, по ЧИСЛАМ, которые посчитала база: указан ли
     вопросом один неназванный предмет и складывается ли итог больше чем из одной записи.
     Итог из одной записи выбором предмета не меняется, и вопрос там был бы шумом.

⚠ ГРАНИЦА, ОСТАВЛЕННАЯ СОЗНАТЕЛЬНО. Точная форма проверки — «совпадает ли неназванный
предмет с ИЗМЕРЕНИЕМ отобранного множества» — сегодня не собирается: слово человека
(«товар») и имя колонки базы («Номенклатура») родством написаний не связаны, а вектора у
отдельной колонки сборка не считает — только у метки сущности, карточки и значений
резолвера. Сводить их вектором значений резолвера — лишнее обращение к эмбеддеру на каждый
вопрос, а он `[замер 05.08]` отвечал `TimeoutError` трижды за 25 минут. Поэтому измерением
служит то, что уже посчитано: из скольких записей сложился итог.

Приборы: `test_enough.py` (оффлайн, без базы, сети и модели) и `work/acceptance/step4_bench.py`
(живой, печатает неверные И верные).
"""
import json

# Описание вопроса, которое даёт модель. Здесь нет ни одного слова о том, что системе
# делать с этим описанием: вердикт собирает код ниже.
FACTS_SYS = """Describe a question that an employee asked about company data.
Reply with JSON only.

{
  "one_of_many": "a noun for a thing the question points at as ONE unspecified instance
                  of a class — 'a product', 'the item', 'some warehouse' — while leaving
                  out which one it is. Give the noun in the question's own language, as
                  the question itself words it. Use null when the question points at no
                  such thing, and also when it asks about a whole class taken as a whole
                  ('how many customers do we have') rather than about one member of it",
  "period_named": true when the question states a time range or a moment, false otherwise,
  "measure_named": true when the question names which quantity it asks about, false otherwise
}

No text outside the JSON."""


# Задание уточнения. Слова про недостающие параметры сюда кладёт КОД (`slots` ниже),
# модель их только переводит в живую фразу на языке вопроса — тот же приём, что у
# `clarify_text` и `refuse_text` в сервисе ответов.
NEED_SYS = """The employee's question about company data leaves some parameters open, and
the figure changes with them. Ask the person one short question about exactly the
parameters listed below, so that they can restate what they meant.

- Ask in the SAME language the question was asked in.
- Plain business words. No table names, no column names, no codes, no identifiers.
- One sentence, no preamble, no apology, no figures. End with a question mark."""


def _s(v):
    """Строка или пусто: ответ модели приходит чем угодно, и тип проверяет код."""
    if isinstance(v, str):
        return v.strip()
    return ""


def _b(v):
    """Булево или None. Строки «true»/«false» модель шлёт наравне с настоящими булевыми."""
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        t = v.strip().lower()
        if t in ("true", "yes", "1"):
            return True
        if t in ("false", "no", "0"):
            return False
    return None


def normalize_facts(d):
    """Ответ модели -> описание вопроса заданных типов. `None` — разбора нет.

    Проверка типами, а не просьбой в промте: тот же урок, что у шага 1 (`_normalize_intent`),
    где ответ модели принимался как есть и давал шесть падений на тридцати пробах.
    Неразобранное поле становится «сведений нет», и вердикт ниже читает это как «повода
    переспрашивать нет» — сбой описания сам по себе уточнением не становится.
    """
    if not isinstance(d, dict):
        return None
    subj = _s(d.get("one_of_many"))
    # Слово длиной со страницу — это уже не существительное, а пересказ вопроса; такое
    # описание в текст уточнения не годится, и код его отбрасывает.
    if len(subj) > 60:
        subj = ""
    return {"one_of_many": subj or None,
            "period_named": _b(d.get("period_named")),
            "measure_named": _b(d.get("measure_named"))}


def facts_wanted(intent):
    """Стоит ли вообще спрашивать модель об этом вопросе. Решает КОД, по разбору шага 1.

    Вход у шага узкий по замеру, а не из осторожности: описание запрашивается там, где
    неполнота вопроса может изменить ЧИСЛО, — когда просят итог величины и при этом не
    названо ни одного значения. Вопрос со значением («сколько продали Альтаиру») предмет
    уже назвал; вопрос-перечень и вопрос-счёт записей итогом по многим предметам не
    складывается.

    Побочно это ограничивает и цену: лишнего обращения к модели на вопросах, которых
    правило не касается, не возникает.
    """
    if not isinstance(intent, dict):
        return False
    if (intent.get("about") or "data") != "data":
        return False                     # вопрос о самих данных — другой путь ответа
    if intent.get("want") != "sum":
        return False
    if intent.get("terms"):
        return False                     # значение в вопросе названо — предмет задан
    return True


def period_given(intent):
    """Назван ли период В ВОПРОСЕ. Выведенный системой период за названный не считается.

    `parse.assumed` — это допущение шага 1 (например, период от сегодняшней даты), и оно
    как раз тот случай, о котором стоит переспросить: человек его не задавал.
    """
    if not isinstance(intent, dict):
        return False
    assumed = set((intent.get("parse") or {}).get("assumed") or [])
    if any(a.startswith("period") for a in assumed):
        return False
    p = intent.get("period") or {}
    return bool(p.get("from") or p.get("to"))


def verdict_before(intent):
    """ДЕШЁВАЯ ПОЛОВИНА, до поиска: (спросить, слоты, причина).

    Ловит вырожденный случай — вопрос просит число, но не называет НИ рода записей, ни
    значений. Тогда искать нечего и считать нечего: любой источник будет догадкой (п. 12).
    Это единственная недостаточность, видная из одного разбора: во всех прочих случаях
    ответ зависит от данных, и решает вторая половина.

    Данные тут не спрашиваются намеренно — спрашивать их не о чем: у вопроса нет ни одной
    координаты, по которой их можно было бы спросить.
    """
    if not isinstance(intent, dict):
        return (False, [], "")
    if (intent.get("about") or "data") != "data":
        return (False, [], "")
    wants_number = intent.get("want") in ("sum", "count") or bool(
        _s(intent.get("measure")))
    if not wants_number:
        return (False, [], "")
    if _s(intent.get("kind")) or intent.get("terms"):
        return (False, [], "")
    slots = [{"kind": "subject", "word": ""}]
    if not period_given(intent):
        slots.append({"kind": "period"})
    return (True, slots, "вопрос не называет ни рода записей, ни значений")


def verdict_after(intent, facts, counted, has_dates):
    """РЕШАЮЩАЯ ПОЛОВИНА, после отбора и счёта: (спросить, слоты, причина).

    `counted` — из скольких записей сложился итог (число посчитано базой, `aggregate`).
    `has_dates` — есть ли у отобранного множества даты (тоже число из базы).

    Условие складывается из двух половин, и каждая закрывает изъян другой:
      * языковая: вопрос указал на ОДИН неназванный предмет из класса. Без неё правило
        сработало бы на «сколько у нас контрагентов» — там тоже нет ни предмета, ни
        периода, а вопрос полный;
      * числовая: итог сложился больше чем из одной записи. Без неё вопрос задавался бы
        там, где выбор предмета ничего не меняет, — а лишнее уточнение обесценивает
        настоящие (то же соображение, что у `measure_ambiguous` и `answers_diverge`).

    Порога тут нет: сравнивается «больше одной записи», а не подобранное число. Имён
    сущностей, слов языка и списков в правиле тоже нет, поэтому на чужой конфигурации оно
    значит ровно то же самое.
    """
    if not isinstance(facts, dict):
        return (False, [], "")
    subj = _s(facts.get("one_of_many"))
    if not subj:
        return (False, [], "")
    try:
        n = int(counted)
    except (TypeError, ValueError):
        return (False, [], "")
    if n <= 1:
        return (False, [], "")
    slots = [{"kind": "subject", "word": subj}]
    # Период попадает в уточнение ТОЛЬКО как спутник предмета и только если у отобранного
    # множества даты вообще есть. Сам по себе отсутствующий период поводом не служит:
    # у справочника дат нет, и вопрос о периоде был бы вопросом ни о чём.
    if has_dates and not period_given(intent) and facts.get("period_named") is not True:
        slots.append({"kind": "period"})
    return (True, slots, "вопрос указывает на один неназванный предмет из многих; "
                         "итог сложен из %d записей" % n)


def slots_text(slots):
    """Перечень недостающих параметров ДЛЯ МОДЕЛИ — собран кодом, а не ею.

    Существительное берётся из самого вопроса (его вернуло описание), поэтому язык
    уточнения задаётся вопросом, а не нашим кодом. Слот периода передаётся признаком, а не
    русским словом: своё слово сделало бы уточнение одноязычным (п. 9).
    """
    out = []
    for s in (slots or []):
        if not isinstance(s, dict):
            continue
        if s.get("kind") == "subject":
            w = _s(s.get("word"))
            out.append("which particular «%s» is meant" % w if w
                       else "what kind of records the question is about")
        elif s.get("kind") == "period":
            out.append("what time period is meant")
    return out


def need_say(question, slots, ds_chat, gate_out, diag=None):
    """Текст уточнения: формулирует МОДЕЛЬ, пропускает ГЕЙТ, не вышло — молчим.

    Пустая строка — законный исход: вызывающий тогда остаётся на прежнем ответе, и
    молчаливой подмены ответа уточнением без вопроса не возникает. Своей прозой писать
    нечего: она была бы на одном языке при любом языке вопроса (п. 9), и это тот самый
    дефект, ради которого в сервисе заведены `clarify_text` и `refuse_text`.

    Числа в уточнении проверяются тем же гейтом, что и везде: их источник — сам вопрос,
    больше модели ничего не дают, значит любое иное число в тексте сочинено.
    """
    parts = slots_text(slots)
    if not parts:
        return ""
    body = "Question: %s\n\nOpen parameters:\n%s" % (
        question, "\n".join("- " + p for p in parts))
    try:
        txt = (ds_chat([{"role": "system", "content": NEED_SYS},
                        {"role": "user", "content": body}], max_tokens=120) or "").strip()
    except Exception:                              # noqa: BLE001 — сеть/квота поставщика
        return ""
    if not txt:
        return ""
    ok, bad = gate_out(txt, [], None, [])
    if ok:
        return txt
    if isinstance(diag, dict):
        diag["need_gate_rejected"] = bad[:4]
    return ""


def parse_facts(raw):
    """Первый объект ответа модели, разобранный по типам. `None` — объекта нет.

    Разбор сбалансированными скобками (а не жадным `{.*}`) — тот же приём, что в шаге 1:
    болтливый ответ со скобками внутри рассуждения иначе разбирается в мусор молча.
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
    for block in out:
        try:
            d = json.loads(block)
        except ValueError:
            continue
        got = normalize_facts(d)
        if got is not None:
            return got
    return None
