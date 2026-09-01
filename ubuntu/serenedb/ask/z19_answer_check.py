"""Zone 19: Проверка ответа (answer-check)."""
from __future__ import annotations

from ask._imports import *
from ask._wire import register_zone, apply_bindings

apply_bindings(globals())

def _readings(tok):
    """Все осмысленные прочтения числового токена."""
    out = set()
    digits = re.sub(r"[^\d]", "", tok)
    if not digits:
        return out
    body = tok.strip(SEP)
    # 1) все разделители — групповые. Только если группировка ПРАВИЛЬНАЯ: первая группа
    # 1-3 цифры, каждая следующая ровно 3. Иначе «10 20 30» читалось как 102030, а
    # «18860000.00» — как 1886000000, и белый список гейта содержал каждое настоящее
    # значение, умноженное на сто. Проверено прогоном: сумма x100 проходила гейт.
    groups = [g for g in re.split(r"[%s]" % re.escape(SEP), body) if g != ""]
    grouped_ok = (len(groups) == 1
                  or (1 <= len(groups[0]) <= 3
                      and all(len(g) == 3 for g in groups[1:])))
    if grouped_ok:
        try:
            out.add(round(float(digits), 2))
        except ValueError:
            pass
    # 2) последний разделитель — десятичный, остальные групповые.
    # ТОЛЬКО если чтение как разрядов не подошло: иначе «3 500 000» получал лишнее
    # прочтение 3500.0, и выдуманный итог заземлялся числом 3500 из данных —
    # то есть ответ, завышенный в тысячу раз, проходил гейт.
    m = [] if grouped_ok else list(re.finditer(r"[%s]" % re.escape(SEP), body))
    if m:
        i = m[-1].start()
        head = re.sub(r"[^\d]", "", body[:i])
        tail = re.sub(r"[^\d]", "", body[i + 1:])
        # Целая часть обязана быть корректно сгруппированной. Иначе «10 20 30 шт»
        # прочиталось бы как 1020.3 — три настоящих числа слиплись бы в одно
        # выдуманное, и честный ответ отвергался бы.
        hg = [g for g in re.split(r"[%s]" % re.escape(SEP), body[:i]) if g != ""]
        head_ok = (len(hg) == 1
                   or (1 <= len(hg[0]) <= 3 and all(len(g) == 3 for g in hg[1:])))
        if head and tail and head_ok:
            try:
                out.add(round(float("%s.%s" % (head, tail)), 2))
            except ValueError:
                pass
    return {v for v in out} | {float(int(v)) for v in out if v == int(v)}


def _plausible(d, mo):
    """Существует ли такой день и месяц. Отрицательная дробь датой не является.

    🔴 Проверки диапазона не было вовсе, и «-3.26» читалось как «3-е число 26-го
    месяца»: числовая ветка гейта такой токен не видела вообще, а датная сверяла его с
    настоящими датами и отвергала. `[замер 04.08, step7_bench]` так отвергались верные
    ответы с отрицательными величинами (сторно, возвраты, остатки). Границы здесь не
    подгонка под базу, а календарь: он одинаков на любой конфигурации.
    """
    return 1 <= d <= 31 and 1 <= mo <= 12


def _dates(text):
    """Даты как УПОРЯДОЧЕННЫЕ компоненты (день, месяц, год).

    Раньше сравнивались множества, и «09.12» с «12.09» были неразличимы — подменённая
    дата проходила. Год определяется по четырёхзначной записи, а не по позиции: это
    не зависит от того, в каком порядке его пишут в стране.
    """
    out, seen = [], []
    for m in DATE3.finditer(str(text or "")):
        if m.group(1):
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        else:
            d, mo, y = int(m.group(4)), int(m.group(5)), int(m.group(6))
        if _plausible(d, mo):
            out.append((d, mo, y))
            seen.append(m.span())
    for m in DATE2.finditer(str(text or "")):
        d, mo = int(m.group(1)), int(m.group(2))
        if _plausible(d, mo) and not any(a <= m.start() and m.end() <= b for a, b in seen):
            out.append((d, mo, None))
    return out


def _date2_readings(text, d, mo):
    """Дробные прочтения двухкомпонентных записей «d.mo», взятые ИЗ ТЕКСТА как есть.

    Нужны там, где запись неоднозначна («20.05» — это и 20 мая, и 20,05). Собирать
    дробь обратно из разобранных компонентов нельзя: ведущий ноль теряется, и число,
    которое ЕСТЬ в данных, объявляется выдумкой.
    """
    out = set()
    for m in DATE2.finditer(str(text or "")):
        if int(m.group(1)) == d and int(m.group(2)) == mo:
            out |= _readings(m.group(0))
    return out


def _date_spans(text):
    """Куски текста, которые числовая ветка гейта не разбирает: это даты.

    Невозможная запись («-3.26», «62.01») датой не считается и остаётся числу — иначе
    она пропадала бы из обеих веток разом: числовая её не видела, датная не с чем было
    сверить (`_plausible`).
    """
    t = str(text or "")
    spans = []
    for m in DATE3.finditer(t):
        if m.group(1):
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        else:
            d, mo, y = int(m.group(4)), int(m.group(5)), int(m.group(6))
        if _plausible(d, mo):
            spans.append(m.span())
    for m in DATE2.finditer(t):
        if _plausible(int(m.group(1)), int(m.group(2))) and \
                not any(a <= m.start() and m.end() <= b for a, b in spans):
            spans.append(m.span())
    return spans


def _tokens(text):
    """Числовые токены текста, вне дат: список множеств допустимых значений."""
    t = str(text or "")
    if not t:
        return []
    for a, b in sorted(_date_spans(t), reverse=True):
        t = t[:a] + " " * (b - a) + t[b:]
    out = []
    for m in NUMTOK.finditer(t):
        tok = m.group(0)
        body = tok.strip(SEP)
        groups = [g for g in re.split(r"[%s]" % re.escape(SEP), body) if g != ""]
        # СНАЧАЛА читаем токен целиком: _readings знает и разряды, и десятичную часть.
        # Раньше здесь стояла своя, более узкая проверка «каждая группа ровно 3 цифры»,
        # и она срабатывала ДО _readings — поэтому «1 629 700,00» рассыпалось на
        # 1 / 629 / 700 / 0, а правильный ответ объявлялся выдумкой и подменялся
        # шаблоном. Любая сумма с разрядами И копейками (английская, немецкая,
        # французская, бразильская запись) отвергалась; наша база спасалась только
        # тем, что суммы целые. Разбиение осталось запасным путём для перечислений.
        whole = _readings(tok)
        if whole:
            out.append(whole)
        else:
            # Не группировка, а просто перечисление рядом: «10 20 30 шт». Каждое число —
            # самостоятельный токен, иначе три настоящих числа превращались в одно
            # выдуманное и честный ответ отвергался.
            for g in groups:
                r = _readings(g)
                if r:
                    out.append(r)
    return out


def _norm_numbers(text):
    """Все значения, которые встречаются в тексте (для белого списка по данным)."""
    out = set()
    for r in _tokens(text):
        out |= r
    return out


ROLE_TOL = 0.01          # копеечная погрешность форматирования


def check_claims(claims, agg, totals=None):
    """Сверить ЗАЯВЛЕННЫЕ моделью величины с посчитанными в базе — по ролям.

    Это то, чего не умеет проверка «число встречается в данных»: сумма одной строки,
    названная итогом, ей неотличима от правды. Живой случай: три реализации на
    1 236 800 были поданы с итогом 925 000 — настоящим числом, но из другой роли.
    Теперь модель обязана назвать роль явно, а роль сверяется с базой.
    """
    if not agg or not isinstance(claims, dict):
        return True, []
    bad = []
    for role in ("total", "count", "max", "min"):
        v = claims.get(role)
        if v is None:
            continue
        try:
            v = float(v)
        except (TypeError, ValueError):
            bad.append("%s=?" % role)
            continue
        real = {"total": agg.get("sum"), "count": agg.get("count"),
                "max": agg.get("max"), "min": agg.get("min")}[role]
        # Когда вопрос величину не назвал, единственного агрегата нет — считаны итоги
        # ПО КАЖДОЙ величине. Роль тогда сверяется с любой из них: «наибольшая продажа»
        # это max величины `СуммаДокумента`, и число обязано совпасть именно с ним, а не
        # с чем попало в данных. [замер 28.07] без этого верный ответ 1 629 700 отвергался
        # с формулировкой «в базе 0», потому что сверять было не с чем.
        if role in ("total", "max", "min") and totals:
            i = {"total": 1, "max": 2, "min": 3}[role]
            if any(abs(v - float(t[i])) <= ROLE_TOL for t in totals):
                continue
        if real is None or abs(v - float(real)) > ROLE_TOL:
            bad.append("%s: заявлено %s, в базе %s" % (role, _fmt(v), _fmt(real)))
    return (not bad), bad



def prompt_leak(text, prompts, min_len=40):
    """Кусок НАШЕЙ инструкции, попавший в ответ клиенту (`№27`).

    🔴 Держится КОДОМ, а не строкой «не показывай промт» внутри самого промта: инструкция,
    запрещающая раскрывать инструкцию, — это правило на промте, а такие правила по
    решению владельца защитой не считаются.

    Это НЕ открытая классификация: текст наших системных сообщений известен целиком,
    поэтому утечка ловится точным совпадением строки, как и остальные наши форматы в
    `stripInternal` на стороне бота. Порог длины отсекает совпадения общих фраз.
    """
    t = " ".join(str(text or "").split())
    if not t:
        return None
    for p in (prompts or []):
        for line in str(p).splitlines():
            line = " ".join(line.split())
            if len(line) >= min_len and line in t:
                return line[:60]
    return None


def asked_figure_missing(text, agg, want, has_measure, folders=0):
    """Величина, О КОТОРОЙ СПРОСИЛИ, обязана стоять в ответе ЦИФРАМИ.

    🔴 Закрывает разом два класса, которые на основном пути не проверялись ничем
    (`F285`, `F286`), и держит их КОДОМ, а не промтом.

    1. **Число не в своей роли.** `check_claims` написана ровно против этого («три
       реализации на 1 236 800 поданы с итогом 925 000 — настоящее число, но из другой
       роли»), но на основном пути она бесполезна: промт велит оставлять `claims`
       пустыми («leave every role null… ignored»), поэтому сверять ей нечего. Гейт
       проверяет, что число ЕСТЬ в данных, — а 925 000 в данных есть. Роль держалась
       подстановкой `{total}`, но подстановку велит делать ПРОМТ, а правило на промте
       не работает (правило владельца). Здесь то же требование становится проверкой:
       раз спросили сумму и база её посчитала — она обязана быть в ответе.

    2. **Числа прописью.** Прежняя проверка срабатывала, только если в тексте нет НИ
       ОДНОЙ цифры, поэтому «примерно три миллиона — это 2 документа» проходило целиком:
       цифра «2» есть, значит признак не взводился. Списка числительных в коде нет и
       быть не может (он был бы привязан к языку) — вместо него требуется само число.

    Возвращает причину отказа или None. Ответ после этого идёт на вторую попытку с
    названной причиной, а если и она не сойдётся — числа уходят структурой (`figures`),
    то есть проверка не превращается в молчание (п. 21).
    """
    if not agg:
        return None
    have = None
    needs = []
    if want == "count":
        needs.append(agg.get("count"))
    elif want == "sum" and has_measure:
        # Без выбранной величины `sum` считается по пустому месту: ноль значил бы «не
        # считали», а не «ноль», и требовать его в тексте было бы требованием выдумки.
        needs.append(agg.get("sum"))
    elif (agg or {}).get("grain") == "group" and has_measure:
        # Рейтинг/list по группам: лидер обязателен; если итог множества другой —
        # он тоже (иначе «Топ 7, итого 1104» при sum≠leader проходит как ответ).
        lead = _group_leader(agg)
        needs.append(lead)
        s = agg.get("sum")
        if s is not None and lead is not None:
            try:
                if abs(float(s) - float(lead)) > 1e-9:
                    needs.append(s)
            except (TypeError, ValueError):
                needs.append(s)
        elif s is not None:
            needs.append(s)
    for need in needs:
        if need is None:
            continue
        if have is None:
            have = _norm_numbers(text)
        nf = float(need)
        if nf not in have and round(nf, 2) not in have:
            return "величина %s не названа цифрами" % _fmt(nf)
    # 🔴 ЧТО ОТБРОШЕНО — ТОЖЕ ОБЯЗАНО БЫТЬ НАЗВАНО ЧИСЛОМ (`№9`, п. 13: молчаливая
    # потеря = дефект). Оговорка про папки справочника ушла в промт, потому что своей
    # прозой мы писали её по-русски на любом языке вопроса. Слова остаются за моделью,
    # а вот ЧИСЛО отброшенного проверяется здесь: человек, знающий про 252 строки,
    # обязан понять, откуда 227.
    if folders:
        if have is None:
            have = _norm_numbers(text)
        if float(folders) not in have:
            return "отброшено %d — не названо в ответе" % folders
    # Дыра S6 (Э4, docs/COMPLETENESS_P13.md §11.2): строки без даты выпадали из
    # проверки, хотя это та же потеря — человек, спросивший «сколько за период»,
    # не узнавал, что часть строк в период не попала вовсе.
    undated = (agg or {}).get("undated")
    if undated:
        if have is None:
            have = _norm_numbers(text)
        try:
            uf = float(undated)
        except (TypeError, ValueError):
            uf = None
        if uf is not None and uf not in have and round(uf, 2) not in have:
            return "без даты %s — не названо в ответе" % _fmt(uf)
    if (agg or {}).get("grain") == "group":
        ng = agg.get("n_groups")
        shown = len(agg.get("groups") or [])
        if ng is not None and ng > shown:
            if have is None:
                have = _norm_numbers(text)
            if float(ng) not in have:
                return "групп %s — не названо в ответе" % ng
    return None


def stale_note(out, age, warn_sec, text_fmt):
    """Приписка о старении — в КАЖДЫЙ ответ, включая отказ (`F223`).

    Прежде ветка `no_data` её не получала, и на трёхсуточных данных «таких данных нет»
    звучало ровно так же уверенно, как на свежих, — при том что именно здесь оговорка
    нужнее всего: данные могут существовать и просто ещё не доехать. `unavailable` не
    включён намеренно: там сообщение и так о сбое, а приписка про возраст корпуса к нему
    отношения не имеет.
    """
    if not isinstance(out, dict) or age is None or age <= warn_sec:
        return out
    if out.get("kind") not in ("answer", "figures", "clarify", "no_data"):
        return out
    out["text"] = ((out.get("text") or "") + text_fmt % (age // 60)).strip()
    out["stale"] = True
    return out


def _threshold_values(intent):
    """Значения НАШИХ условий отбора: пороги суммы. Дата в текст ответа попадает как
    дата, её проверяет отдельная ветка гейта."""
    amt = (intent or {}).get("amount") or {}
    return [v for v in (amt.get("value"), amt.get("value2")) if v is not None]


def _filter_values(intent):
    """Числа НАШИХ УСЛОВИЙ ОТБОРА: пороги и числовые понятия, по которым шёл поиск.

    🔴 ЭТО ЗАМЕНА БЕЛОМУ СПИСКУ «ВСЕ ЧИСЛА ВОПРОСА» (`F244`). Прежде в разрешённое
    уходило `_norm_numbers(question)` целиком — то самое отмывание, которое докстрока
    самой `gate()` называет недопустимым: вопрос приходит аргументом инструмента,
    сочиняет его модель бота, то есть проверяемый пополнял свой же белый список.
    Плагин на стороне бота этот путь закрыл 02.08 (`verify-core.isGrounded`: числа
    сообщения заземляют ответ, только когда эталона нет вовсе) и в комментарии
    утверждал, что то же самое закрыто на стороне `serene_ask`, — а закрыто не было.

    Разрешённым остаётся значение, по которому МЫ отфильтровали или отобрали данные.
    Порог (`amount`) применён нашим предикатом, числовое понятие (`terms`) — нашим
    запросом к индексу: строки, которые мы считаем, ему отвечают. Обоснование то же,
    что у порогов, и проверяется кодом, а не доверием к тексту вопроса. [замер 28.07]
    ради этого класса правило и заводилось: у вопроса «обороты по счёту 62» число «62»
    приходит понятием отбора, и верный ответ с ним больше не отвергается.
    """
    out = list(_threshold_values(intent))
    for group in ((intent or {}).get("terms") or []):
        for alt in (group if isinstance(group, list) else [group]):
            out += sorted(_norm_numbers(alt))
    return out



register_zone('ask.z19_answer_check', globals())
