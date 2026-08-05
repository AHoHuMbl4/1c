#!/usr/bin/env python3
"""
POC-загрузчик: любая сущность 1С (OData) -> CSV -> SereneDB -> проба агрегации.

Конфиг-нейтрально: имя сущности — аргумент, колонки берём АВТОМАТИЧЕСКИ (union полей),
ничего не хардкодим. Это доказательство конвейера и заготовка под Этап 2 (штатный
инкрементальный ETL->SereneDB). Прод-загрузчик заменит этот POC.

Запуск:  python3 poc_load_entity.py Catalog_КлассификаторБанков
Env:     ETL_ODATA_BASE (default http://127.0.0.1:6011)
         SERENEDB_DSN   (default 'host=127.0.0.1 port=7890 user=postgres')
         CSV_DIR        (default /var/lib/serenedb  — читаемо процессом serened)
"""
import csv, io, json, os, re, subprocess, sys, time, urllib.parse, urllib.request

def _odata_auth(req):
    """Добавить Bearer шлюза. Один способ на всех клиентов OData.

    Шлюз стал fail-closed (без токена не стартует и отвечает 401). Токен был роздан
    только сборщику индекса — остальные клиенты продолжали ходить без заголовка, и
    канал к 1С молча разорвался: преполёт возвращал None, синк грузил ноль сущностей,
    юнит при этом не падал. Поэтому заголовок ставится здесь, а не в каждом вызове.
    """
    if isinstance(req, str):
        req = urllib.request.Request(req)      # вызывают и строкой, и объектом
    tok = os.environ.get("ODG_GATEWAY_TOKEN", "")
    if tok:
        req.add_header("Authorization", "Bearer " + tok)
    return req


ODATA = os.environ.get("ETL_ODATA_BASE", "http://127.0.0.1:6011").rstrip("/")
DSN = os.environ.get("SERENEDB_DSN", "host=127.0.0.1 port=7890 user=postgres")
CSV_DIR = os.environ.get("CSV_DIR", "/var/lib/serenedb")
# 🔴 РАЗМЕР СТРАНИЦЫ РЕШАЕТ БОЛЬШЕ, ЧЕМ ОБЪЁМ ДАННЫХ. [замер 05.08, боевая база] на одном
# и том же регистре: `$top=1000` — **165 строк/с**, `$top=5000` — 411, `$top=20000` —
# **1316**. Восьмикратная разница, потому что время уходит не на строки, а на ОБРАЩЕНИЯ:
# каждый заход к 1С стоит несколько секунд сам по себе, и с ростом `$skip` дорожает ещё.
# При странице 1000 регистр из 97 834 строк читался 888 с — почти четверть такта на одну
# сущность, из-за чего не выполнялся п. 17 `TARGET.md` (свежесть ≤ 20 мин).
#
# Крупная страница — это МЕНЬШЕ нагрузки на 1С, а не больше (второе предложение п. 17):
# меньше запросов и меньше повторных проходов по `$skip`.
#
# 🔴 ЧИСЛО НЕ ЗАШИТО И НЕ ПОДОБРАНО ПОД ЭТУ БАЗУ. Страница самонастраивается: начинаем
# крупно и уменьшаем вчетверо, если 1С не справилась, — до `ETL_PAGE_MIN`. Так на чужой
# базе с тяжёлыми строками (у нас есть справочник с 19 МБ в одной строке) загрузка не
# падает и не требует ручной настройки, а на обычной идёт в разы быстрее.
PAGE = int(os.environ.get("ETL_PAGE", "10000"))
PAGE_MIN = int(os.environ.get("ETL_PAGE_MIN", "250"))
# Сущности, у которых выборка пришла вложенной. Для них объявленный ключ — ключ ОБЁРТКИ.
_NESTED_SEEN = set()
# Предел ожидания одного запроса к 1С. Это БЮДЖЕТ ВРЕМЕНИ, а не порог правильности:
# при его превышении загрузка падает с ошибкой, а не отбрасывает данные молча.
# [замер 28.07] жёсткие 120 с не были ни на чём основаны и роняли загрузку целой
# сущности: `Catalog_ИдентификаторыОбъектовМетаданных` отдаёт страницу в 1 000 строк за
# 84-89 секунд — то есть вторая же страница не укладывалась. Сортировка тут ни при чём:
# без `$orderby` те же 84 с. Сущность просто медленная на стороне 1С, и наш предел
# объявлял её несуществующей: 5 881 строка молча отсутствовала в поиске.
HTTP_TIMEOUT = int(os.environ.get("ETL_HTTP_TIMEOUT", "600"))


_KEYS_CACHE = {}
# Поля сущности и их типы — оттуда же, из `$metadata`. Нужны, чтобы не просить у 1С то,
# что она физически не может отдать (см. `_select_of`).
_PROPS_CACHE = {}

# 🔴 ТИПЫ, КОТОРЫЕ ШТАТНЫЙ OData 1С НЕ ОТДАЁТ В JSON. Это не наша догадка и не список
# имён полей: тип объявлен в `$metadata` самой платформой.
# [замер 29.07, УТ 11.4.9] `InformationRegister_ИсточникиДанныхВариантовАнализаЦелевых-
# Показателей` отвечал `HTTP 500` при ЛЮБОМ размере страницы, вплоть до `$top=1`, при
# этом `$count` честно говорил 37. Причина — поля `ИсточникДанных` (`Edm.Stream`) и
# `ИсточникДанных_Base64Data` (`Edm.Binary`): хранилище значения. Стоило перечислить в
# `$select` остальные поля — те же 37 строк пришли с кодом 200.
# 🔴 МАСШТАБ: таких типов в этой конфигурации **470 из 2 795** — присоединённые файлы,
# подписи, сертификаты. В демо-базе они почти пусты, и упала ровно одна сущность; на
# базе клиента с приложенными файлами так молча отвалились бы сотни.
UNSERVABLE_TYPES = ("Edm.Stream", "Edm.Binary")
_SELECT_WARNED = set()


def _load_metadata():
    """Один разбор `$metadata` на процесс: ключи и типы полей."""
    if _KEYS_CACHE or _PROPS_CACHE:
        return
    try:
        xml = urllib.request.urlopen(
            _odata_auth(ODATA + "/$metadata"), timeout=HTTP_TIMEOUT).read().decode("utf-8", "replace")
    except Exception:                           # noqa: BLE001
        return
    for m in re.finditer(r'<EntityType\s+Name="([^"]+)"(.*?)</EntityType>', xml, re.S):
        km = re.search(r"<Key>(.*?)</Key>", m.group(2), re.S)
        _KEYS_CACHE[m.group(1)] = (
            re.findall(r'<PropertyRef\s+Name="([^"]+)"', km.group(1)) if km else [])
        _PROPS_CACHE[m.group(1)] = re.findall(
            r'<Property\s+Name="([^"]+)"\s+Type="([^"]+)"', m.group(2))


def declared_key(entity_set):
    """Объявленный ключ сущности из `$metadata` — источник правды, в т.ч. составной."""
    _load_metadata()
    return _KEYS_CACHE.get(entity_set, [])


def _select_of(entity_set):
    """`$select` из полей, которые 1С способна отдать. Пусто — значит нечего сужать.

    🔴 ЭТО ЗАПАСНОЙ ВАРИАНТ, А НЕ ОСНОВНОЙ. Применяется только после того, как обычный
    запрос дважды ответил ошибкой (`_get_json`). Причина: [замер 29.07] наличие
    двоичного поля само по себе выдачу НЕ ломает — `Catalog_ШаблоныПоясненийДляФНС`
    имеет те же `Edm.Stream`/`Edm.Binary`, 35 строк, и отдаётся с кодом 200. Ломает,
    судя по всему, непустое хранилище. Таких типов на первой базе 961 из 4 585, и
    сужать их все означало бы выбросить колонки там, где сейчас всё работает, — то есть
    сменить схему таблиц витрины и переписать ключи строк корпуса (`ловушка 22`).
    Поэтому: обычный запрос → повтор → и только потом сужение.

    Табличные части при этом не теряются: в 1С они **отдельные наборы**
    (`Document_X_Товары`), и грузятся своими запросами, а не внутри этого.
    """
    _load_metadata()
    props = _PROPS_CACHE.get(entity_set) or []
    bad = [n for n, t in props if t in UNSERVABLE_TYPES]
    if not bad:
        return ""
    keep = [n for n, t in props if t not in UNSERVABLE_TYPES]
    if not keep:                                # сущность вся из двоичных полей
        return ""
    # 🔴 Потеря НАЗВАНА, а не проглочена (п. 13). Двоичному содержимому в текстовом
    # корпусе делать нечего, но человек должен видеть, что именно не взято и почему.
    # Один раз на сущность: иначе в дельте это печаталось бы на каждую изменённую запись.
    if entity_set not in _SELECT_WARNED:
        _SELECT_WARNED.add(entity_set)
        print("    %s: пропущены поля, которые OData 1С не отдаёт (%s): %s"
              % (entity_set, "/".join(UNSERVABLE_TYPES), ", ".join(bad)), flush=True)
    return ",".join(keep)


def _get_json(entity_set, params, timeout=None, key=None):
    """Запрос к OData с ПЕРЕБОРОМ ВАРИАНТОВ вместо падения.

    Указание владельца 29.07: «ошибку надо попробовать закрыть — ещё раз сделать запрос
    на неё, например, или по-другому. иначе это будут не все данные». Порядок:

      1. как обычно — так работает подавляющее большинство сущностей;
      2. **повтор** — часть отказов 1С разовые (нагрузка, фоновое задание);
      3. **без неотдаваемых полей** (`$select` по `$metadata`) — [замер 29.07]
         `InformationRegister_ИсточникиДанныхВариантовАнализаЦелевыхПоказателей` отвечал
         `HTTP 500` при любом размере страницы, вплоть до `$top=1`, тогда как `$count`
         честно говорил 37. Стоило исключить `Edm.Stream`/`Edm.Binary` — пришли все 37
         строк с кодом 200.

    Порядок именно такой, потому что вариант 3 меняет СОСТАВ КОЛОНОК, а значит и схему
    таблицы витрины. Применять его к тем, кто и так отвечает, — самому себе устроить
    массовую смену ключей строк (`techContext` ловушка 22). Запасной вариант должен
    включаться после отказа, а не вместо основного пути.

    Если не помог ни один — исключение уходит наверх, и сущность честно считается
    незагруженной: перепись полноты покажет её числом, а не умолчит (п. 13).
    """
    t = timeout or HTTP_TIMEOUT
    seg = urllib.parse.quote(entity_set) + ("(guid'%s')" % key if key else "")
    url = "%s/%s?%s" % (ODATA, seg, urllib.parse.urlencode(params))
    try:
        return json.load(urllib.request.urlopen(_odata_auth(url), timeout=t))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise
        first = e
    try:                                        # 2. просто ещё раз
        return json.load(urllib.request.urlopen(_odata_auth(url), timeout=t))
    except urllib.error.HTTPError:
        pass
    sel = _select_of(entity_set)                # 3. по-другому: без неотдаваемых полей
    if not sel:
        raise first
    p2 = dict(params, **{"$select": sel})
    url2 = "%s/%s?%s" % (ODATA, seg, urllib.parse.urlencode(p2))
    return json.load(urllib.request.urlopen(_odata_auth(url2), timeout=t))


def _order_by(entity_set):
    """Порядок страниц — по ОБЪЯВЛЕННОМУ ключу, а не по предположению про `Ref_Key`.

    Без сортировки `$skip/$top` не гарантирует одинаковый порядок между страницами:
    строки перекрываются, а часть теряется НАВСЕГДА — витрина тихо неполная, суммы
    тихо заниженные. Прежний вариант знал только `Ref_Key`; у 3121 типа из 4585 ключ
    составной, а у 497 нет ни одной Guid-колонки, и для них сортировки не было вовсе.
    """
    key = declared_key(entity_set)
    if key:
        # `*_Type` — служебные спутники ссылок, сортировать по ним смысла нет
        cols = [k for k in key if not k.endswith("_Type")] or key
        return ",".join(cols)
    url = f"{ODATA}/{urllib.parse.quote(entity_set)}?" + urllib.parse.urlencode(
        {"$format": "json", "$top": "1"}
    )
    try:
        v = json.load(urllib.request.urlopen(_odata_auth(url), timeout=HTTP_TIMEOUT)).get("value", [])
    except Exception:
        return None
    return "Ref_Key" if v and "Ref_Key" in v[0] else None


def count_of(entity_set):
    """Сколько строк в 1С. Нужно, чтобы сверить выгрузку и не принять неполную за полную."""
    url = "%s/%s/$count" % (ODATA, urllib.parse.quote(entity_set))
    try:
        return int(urllib.request.urlopen(_odata_auth(url), timeout=HTTP_TIMEOUT).read().decode().strip())
    except Exception:                           # noqa: BLE001
        return -1


def own_props(entity_set):
    """Свойства, объявленные САМОЙ сущностью в `$metadata` (не вложенным типом).

    Нужно, чтобы при разворачивании вложенного набора реквизит ШАПКИ не затирался
    одноимённым реквизитом строки. [замер 29.07] пересечений имён 719; подмен —
    551 значение на 3 116 объектов, из них 309 подменены на пустое. Пример:
    `Document_ЗаказНаПеремещение` ТД00-000001 — в 1С `Назначение_Key` шапки
    `b5d6e2f4-…`, в витрине у всех строк нули: значение шапки исчезло. У
    `document_счетфактуравыданныйаванс` ТД00-А000003 в 1С `Сумма = 77 187,50`, в
    витрине только суммы строк — собственной суммы документа нет вовсе.
    """
    _load_metadata()
    return {n for n, _t in (_PROPS_CACHE.get(entity_set) or [])}


def _flatten_nested(rows, entity_set=None):
    """Развернуть ВЛОЖЕННЫЙ набор записей в обычные строки.

    Регистры 1С приходят по OData не плоским списком, а обёрткой: одна запись на
    регистратор, а сами движения лежат внутри списком (`RecordSet`). Загрузчик видел
    ОДНУ строку вместо всех и объявлял выгрузку неполной — [замер 28.07]
    `AccountingRegister_Хозрасчетный`: «выгружено 1 строк, в 1С 104». Так молча
    отсутствовала главная книга: на «обороты по счёту» отвечать было нечем.

    Правило СТРУКТУРНОЕ, без единого имени: если у записи ровно одно поле, значение
    которого — непустой список объектов, то настоящие строки лежат в нём, а внешние
    скалярные поля общие для всех. Имя поля роли не играет и в коде не упоминается.
    """
    # 🔴 РАЗВОРАЧИВАЕМ ТОЛЬКО ОБЁРТКИ НАБОРОВ ЗАПИСЕЙ. Признак — объявленный ключ: у
    # ссылочного объекта он `['Ref_Key']` (у объекта есть собственная идентичность), у
    # обёртки набора — регистратор (`Recorder…`). Разделение платформы, проверено по двум
    # базам: владельцы вложенных типов делятся ровно на два класса, третьего нет.
    #
    # Прежде разворот шёл у всех, и у ссылочных объектов реквизит ШАПКИ затирался
    # одноимённым реквизитом строки — [замер 29.07] 551 подменённое значение.
    own = own_props(entity_set) if entity_set else set()
    is_object = bool(entity_set) and declared_key(entity_set) == ['Ref_Key']
    # 🔴 FAIL-CLOSED. Если `$metadata` недоступна, `own` пуст и `is_object` ложно — то есть
    # мы молча вернулись бы к прежнему поведению и записали отравленную витрину. Лучше
    # честно отказаться: пустой перечень свойств при заданной сущности — это сбой.
    if entity_set and not own:
        raise RuntimeError("нет свойств %s в $metadata — загрузка отменена, "
                           "иначе реквизиты шапки будут затёрты значениями строк" % entity_set)

    out, changed = [], False
    for r in rows:
        nested = [k for k, v in r.items()
                  if isinstance(v, list) and v and isinstance(v[0], dict)]
        if len(nested) != 1:
            out.append(r)
            continue
        k = nested[0]
        outer = {kk: vv for kk, vv in r.items() if kk != k}
        for inner in r[k]:
            merged = dict(outer)
            if is_object:
                # Реквизит, объявленный САМОЙ сущностью, значением строки не затирается.
                merged.update({kk: vv for kk, vv in inner.items() if kk not in own})
            else:
                merged.update(inner)           # обёртка набора: строка и есть данные
            out.append(merged)
        changed = True
    return out, changed


def fetch_all(entity_set):
    """Выгрузить сущность целиком, со сверкой количества.

    Короткая страница НЕ означает конец данных: замерено — под нагрузкой (сразу после
    переписи из 4585 запросов) 1С вернула 517 строк вместо 1000 в середине выгрузки, и
    прежний код на этом останавливался. Итог: 19 517 строк из 23 878, витрина тихо
    неполная, суммы тихо заниженные, ошибок в журнале ноль. Повторный прогон отдал все
    23 878 — то есть дефект плавающий, а такой опаснее постоянного.

    Поэтому: идём до ПУСТОЙ страницы и сверяем итог с `$count`. Расхождение — ошибка,
    а не «загрузили сколько получилось».
    """
    # 🔴 СЧЁТ ПРИХОДИТ ВМЕСТЕ С ДАННЫМИ, А НЕ ОТДЕЛЬНЫМ ЗАПРОСОМ. `$inlinecount=allpages` —
    # штатная возможность OData 3.0, которую 1С поддерживает: в ответе появляется поле
    # `odata.count` (проверено на живой 1С — 176 в `odata.count` при `$top=2`, и ровно
    # столько же отдаёт `/$count`). Прежде на КАЖДУЮ сущность уходил лишний заход за
    # `/$count`: [замер 05.08] 1589 сущностей за такт по 0,13 с медианы — сотни секунд
    # такта свежести (п. 17) на то, что и так приезжает вместе с первой страницей.
    #
    # Крупная первая страница мелкую сущность не удорожает — проверено: те же 176 строк
    # приходят за 0,08-0,11 с и при `$top=176`, и при `$top=10000`.
    #
    # 🔴 СОРТИРОВКА НУЖНА ТОЛЬКО ДЛЯ ПОСТРАНИЧНОГО ЧТЕНИЯ. Она держит порядок между
    # страницами, чтобы строки не перекрывались и не терялись. Если сущность целиком
    # помещается в одну страницу, страниц нет — и сортировать нечего.
    # [замер 28.07] пять информационных регистров по одной строке 1С отдавала с
    # `HTTP 500 Internal Server Error` ИМЕННО на `$orderby` по объявленному ключу; без
    # него те же адреса отвечают 200. Так молча терялись пять сущностей: ошибка печаталась
    # в поток и нигде не сохранялась, а в переписи стояло «не загрузилось» без причины.
    #
    # Отсюда порядок действий: первая страница идёт БЕЗ порядка и со счётом. Если по счёту
    # видно, что одной страницей не обойтись, — начинаем сначала уже с `$orderby`. Лишняя
    # страница платится только крупными сущностями, которых единицы, а сотни мелких
    # экономят по заходу каждая.
    expected = -1
    page = PAGE
    order = ""
    rows, skip, short_pages, first = [], 0, 0, True
    while True:
        params = {"$format": "json", "$top": str(page), "$skip": str(skip)}
        if first:
            params["$inlinecount"] = "allpages"
        if order:
            params["$orderby"] = order  # стабильный порядок → страницы не перекрываются
        try:
            doc = _get_json(entity_set, params)
            v = doc.get("value", [])
            if first:
                first = False
                try:
                    expected = int(doc.get("odata.count", doc.get("__count", -1)))
                except (TypeError, ValueError):
                    expected = -1
                # Одной страницей не обошлось, а читали БЕЗ порядка — начинаем сначала.
                # Иначе `$skip/$top` пойдут по нестабильному порядку и молча потеряют
                # часть строк (тот самый дефект, ради которого `$orderby` и заведён).
                if len(v) >= page and (expected < 0 or expected > page):
                    order = _order_by(entity_set)
                    if order:
                        rows, skip, short_pages = [], 0, 0
                        continue
                # Счёта не дали — спрашиваем по-старому, иначе нечем сверить полноту.
                if expected < 0:
                    expected = count_of(entity_set)
        except Exception:                       # noqa: BLE001
            # 🔴 СТРАНИЦА УМЕНЬШАЕТСЯ, А НЕ СУЩНОСТЬ ТЕРЯЕТСЯ. `_get_json` уже перебрал
            # свои варианты (повтор, `$select` без неотдаваемых полей) — значит дело в
            # размере: у сущности тяжёлые строки. Уменьшаем вчетверо и НАЧИНАЕМ СНАЧАЛА:
            # продолжать с середины нельзя, потому что при меньшей странице появляется
            # постраничность, а с ней обязателен `$orderby` — смешивать упорядоченные
            # страницы с уже прочитанными неупорядоченными значило бы терять и дублировать
            # строки молча (п. 13).
            if page <= PAGE_MIN:
                raise
            page = max(PAGE_MIN, page // 4)
            order = _order_by(entity_set) if (expected < 0 or expected > page) else ""
            # Начинаем сущность заново — значит и счёт спросим заново вместе с первой
            # страницей: `first` сбрасывается, иначе счёта не будет вовсе и сверять
            # полноту будет нечем.
            rows, skip, short_pages, first = [], 0, 0, True
            print("    %s: страница уменьшена до %d — 1С не отдала крупную"
                  % (entity_set, page), file=sys.stderr)
            continue
        if not v:
            break
        rows.extend(v)
        skip += len(v)
        if len(v) < page:
            short_pages += 1
            # Короткая страница в середине — признак нагрузки, а не конца. Продолжаем,
            # пока не придёт пустая или пока не набрали ожидаемое количество.
            if expected >= 0 and len(rows) >= expected:
                break
            if expected < 0 and short_pages > 1:
                break
    rows, nested = _flatten_nested(rows, entity_set)
    # 🔴 СВЕРКА С `$count` ПРИМЕНИМА ТОЛЬКО К ПЛОСКОЙ ВЫБОРКЕ. У вложенной формы эти
    # числа считают РАЗНОЕ и сравнению не подлежат: [замер 28.07]
    # `AccountingRegister_Хозрасчетный` — `$count` даёт 104, коллекция возвращает ОДНУ
    # обёртку, а внутри неё 280 движений. Прежний код сравнивал 1 со 104, объявлял
    # выгрузку неполной и выбрасывал сущность целиком — так молча отсутствовала главная
    # книга. Проверка, отвергающая верные данные, защитой не является.
    # Несопоставимость не заминается: она печатается, и число строк уходит в перепись,
    # где расхождение с 1С видно владельцу (п. 13).
    if nested:
        print("    %s: вложенный набор развёрнут -> %d строк (в 1С $count=%d — формы разные,"
              " сравнению не подлежат)" % (entity_set, len(rows), expected))
        _NESTED_SEEN.add(entity_set)
    elif expected >= 0 and len(rows) != expected:
        raise RuntimeError(
            "%s: выгружено %d строк, в 1С %d — выгрузка неполная" % (entity_set, len(rows), expected))
    return rows


def published_entity_sets():
    """Множество имён entity set, РЕАЛЬНО опубликованных в OData (служебный документ) — источник
    правды об именах сущностей. Нужен, чтобы валидировать рукописный выбор против реальности, а не
    верить памяти. Возвращает None при сетевой ошибке (тогда преполёт пропускается — без ложной тревоги)."""
    try:
        url = f"{ODATA}/?" + urllib.parse.urlencode({"$format": "json"})
        doc = json.load(urllib.request.urlopen(_odata_auth(url), timeout=60))
        return {e.get("name", "") for e in doc.get("value", []) if e.get("name")}
    except Exception:
        return None


def safe_col(name):
    """Безопасное имя колонки для ЛЮБОГО алфавита.

    Раньше здесь был диапазон «латиница + русская кириллица»: на японской, китайской
    или греческой конфигурации ВСЕ имена схлопывались в одно (`catalog`, `col`), и
    каждая следующая сущность затирала предыдущую. Проверять принадлежность к алфавиту
    надо средствами Unicode, а не перечислением букв.
    """
    out = []
    for ch in str(name):
        out.append(ch if (ch.isalnum() or ch == "_") else "_")
    s = "".join(out).strip("_")
    if not s or s[0].isdigit():
        s = "c_" + s
    return s


def _psql_rows(sql):
    """Строки запроса к витрине списком кортежей. SQL идёт ЧЕРЕЗ STDIN, а не аргументом
    `-c`: у аргумента командной строки жёсткий предел (~128 КБ), и запрос с длинным
    списком ключей его перекрывал — [замер 28.07] `Argument list too long` на справочнике
    в 23 878 строк. Служебное для дельта-загрузки."""
    p = subprocess.run(["psql", DSN, "-tA", "--csv", "-v", "ON_ERROR_STOP=1", "-f", "-"],
                       input=sql, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip()[:200])
    return [tuple(r) for r in csv.reader(io.StringIO(p.stdout)) if r]


def _psql_exec(sql):
    p = subprocess.run(["psql", DSN, "-v", "ON_ERROR_STOP=1", "-f", "-"],
                       input=sql, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip()[:200])


def _lit(v):
    return "'" + str(v).replace("'", "''") + "'"


def _mart_has(table, col):
    try:
        return bool(_psql_rows("SELECT 1 FROM duckdb_columns() WHERE table_name=%s "
                               "AND column_name=%s" % (_lit(table), _lit(col))))
    except RuntimeError:
        return False


_OWNER_CACHE = {}


def owner_of(entity_set):
    """Владелец набора строк: объект, чья версия решает, менялись ли эти строки.

    Зачем. У табличной части своей версии нет, и до сих пор она грузилась ЦЕЛИКОМ каждый
    такт: [замер 05.08] 272 таких источника, 472 с, из них 313 с — одна
    `Document_ПланПродаж_Товары` (5 357 строк). А менялись они ровно тогда, когда менялся
    их документ, у которого `DataVersion` есть.

    🔴 ГИПОТЕЗУ ДАЁТ УСТРОЙСТВО ПЛАТФОРМЫ, А ПОДТВЕРЖДАЮТ ЕЁ `$metadata` И ДАННЫЕ.
    Табличная часть публикуется адресом `<Владелец>_<ИмяЧасти>` — это строение
    стандартного интерфейса OData, одинаковое на любой конфигурации и не зависящее от
    языка, как и сами `Ref_Key`/`DataVersion`. Связи «часть → владелец» в `$metadata` нет
    (проверено: навигация объявлена только на реквизиты-ссылки), поэтому имя даёт лишь
    кандидата, а решают две проверки ниже по коду:

      * у кандидата в `$metadata` есть `Ref_Key` и `DataVersion`;
      * у самой части есть `Ref_Key`, а своей `DataVersion` нет — иначе она сама себе
        владелец и дельта у неё работает напрямую.

    Не сошлось — возвращается `None`, и источник грузится полностью. Ошибка возможна
    только в сторону лишней работы. Имя разбирается по `_` от длинного к короткому,
    поэтому имя части с подчёркиванием внутри тоже находит своего владельца.
    """
    if entity_set in _OWNER_CACHE:
        return _OWNER_CACHE[entity_set]
    _load_metadata()
    own = dict(_PROPS_CACHE.get(entity_set) or [])
    res = None
    if "Ref_Key" in own and "DataVersion" not in own:
        parts = entity_set.split("_")
        for cut in range(len(parts) - 1, 0, -1):
            cand = "_".join(parts[:cut])
            props = dict(_PROPS_CACHE.get(cand) or [])
            if "Ref_Key" in props and "DataVersion" in props:
                res = cand
                break
    _OWNER_CACHE[entity_set] = res
    return res


def _fetch_page_doc(es, params):
    """Ответ целиком — нужен, когда вместе со строками читается и `odata.count`.

    🔴 Намеренно БЕЗ перебора вариантов из `_get_json`. Тот при отказе подставляет свой
    `$select` по `$metadata` — и подменил бы узкий `$select=Ref_Key,DataVersion` пробы
    версий полным списком полей, то есть проба перестала бы быть дешёвой и делала бы ровно
    ту работу, которой дельта и избегает.
    """
    url = f"{ODATA}/{urllib.parse.quote(es)}?" + urllib.parse.urlencode(params)
    return json.load(urllib.request.urlopen(_odata_auth(url), timeout=HTTP_TIMEOUT))


def _fetch_page(es, params):
    return _fetch_page_doc(es, params).get("value", [])


def _cell(v):
    """Значение для CSV в том же виде, в каком его отдал 1С. 🔴 json в Python делает из
    `false`/`true` булевы `False`/`True`, а `csv.writer` пишет их с БОЛЬШОЙ буквы. Витрина
    тогда несёт `False`, а 1С — `false`; у регистров без уникального ключа `row_key` =
    `sha1(doc)`, и смена регистра буквы ПЕРЕКЛЮЧАЕТ ключ у всех строк — [замер 28.07]
    слияние хотело удалить 22 042 строки при неизменных данных. Пишем как в JSON 1С."""
    if v is True:
        return "true"
    if v is False:
        return "false"
    # Дата-время 1С приходит в ISO с `T` (`2022-02-07T00:00:00`), а движок и корпус
    # хранят её с пробелом (`2022-02-07 00:00:00`). Разница в одном символе так же
    # переключает `row_key` регистров без уникального ключа, как и регистр буквы в
    # булевом [замер 28.07: ещё 22 267 ложных удалений]. Приводим к виду корпуса.
    if isinstance(v, str):
        m = re.match(r"^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2})$", v)
        if m:
            return m.group(1) + " " + m.group(2)
    return v


def load_entity_delta(es, ro_role="serene_ro"):
    """ИНКРЕМЕНТАЛЬНАЯ загрузка: тянем из 1С только ИЗМЕНЁННОЕ, не всю сущность.

    🔴 ЗАЧЕМ. Полная перезагрузка каждой сущности каждый такт — это трафик и, главное,
    повторный ЭМБЕДДИНГ. Указание владельца 28.07: «научиться заливать из 1С только
    изменения, иначе будет постоянный эмбеддинг».

    Как ловим изменения БЕЗ даты и без полной вычитки: у каждой записи 1С есть `DataVersion`
    — токен версии. [замер 28.07] его берут отдельным дешёвым `$select=Ref_Key,DataVersion`
    (два поля на строку). Сравниваем с витриной: версия иная/ключа нет → изменилось, тянем
    целиком; ключ в витрине есть, а в 1С нет → удалено, чистим. Ничего не изменилось —
    НУЛЕВАЯ работа: ни полной вычитки, ни одного вектора.

    Применимо к сущностям с УНИКАЛЬНЫМ `Ref_Key` (справочники, шапки документов). Табличные
    части и регистры (составной ключ, вложенная форма) — полной загрузкой. Возвращает None,
    когда дельта неприменима: тогда вызывающий грузит полностью.

    🔴 ЭТО НЕ ХАРДКОД ПОД БАЗУ. `Ref_Key` и `DataVersion` — СТАНДАРТНЫЕ технические поля
    платформы 1С, которые она генерирует сама на ЛЮБОЙ конфигурации и по-английски
    независимо от языка (как `id`/версия строки в СУБД). [замер 28.07] их объявляют 2969 и
    1129 РАЗНЫХ типов из 4585 — это платформа, а не бизнес-поле этой базы. И мы их не
    предполагаем вслепую: `_mart_has` проверяет наличие, при отсутствии — полная загрузка
    (1616 типов без `Ref_Key`). Формы `guid'…'`, `$select`, `$count` — стандарт OData;
    `false`/дата — формат JSON 1С. Ни одного имени и ни одного порога под конкретную базу.
    """
    table = safe_col(es).lower()
    if not (_mart_has(table, "Ref_Key") and _mart_has(table, "DataVersion")):
        return None
    # 🔴 РАЗВЁРНУТЫЙ НАБОР ДЕЛЬТЕ НЕ ПОМЕХА — И ЭТО БЫЛА ГЛАВНАЯ ПРИЧИНА, ПО КОТОРОЙ ЕЁ
    # ПОЧТИ НИКОГДА НЕ БЫЛО. [замер 05.08] за такт боевой базы 172 источника пришли
    # вложенной формой (документ с табличной частью внутри), после разворота `Ref_Key`
    # перестаёт быть уникальным — и обе проверки ниже отправляли источник на ПОЛНУЮ
    # загрузку, хотя `DataVersion` у документа есть. Это 85 источников и 331 с каждого
    # такта на данных, которые не менялись.
    #
    # Замена работает и для многострочных: слияние ниже удаляет ВСЕ строки изменившегося
    # `Ref_Key` и вставляет новые — то есть заменяет документ целиком вместе с его
    # строками. Ровно это и нужно, когда у документа поменялась табличная часть.
    #
    # Осталась одна проверка, и она по существу: у всех строк одного `Ref_Key` версия
    # обязана быть одна. Если это не так — витрина собрана не так, как мы думаем, и
    # сравнивать версии нельзя: уходим на полную загрузку.
    try:
        mix = _psql_rows('SELECT count(*) FROM (SELECT "Ref_Key" FROM "%s" '
                         'GROUP BY 1 HAVING count(DISTINCT "DataVersion")>1)' % table)
        if mix and int(mix[0][0]) > 0:
            return None
    except RuntimeError:
        return None

    t0 = time.time()
    # Проба версий — до ПУСТОЙ страницы, а не до короткой: под нагрузкой 1С отдаёт неполную
    # страницу в середине (тот же дефект, что у полной выгрузки). Затем сверяем со счётом.
    #
    # Счёт приезжает ВМЕСТЕ с первой страницей (`$inlinecount=allpages`), а не отдельным
    # заходом за `/$count` — разбор в `fetch_all`. Проба берёт два узких поля на строку,
    # поэтому крупная страница здесь безопаснее всего и выигрывает больше всего: именно
    # эта проба и решает, будет ли дельта дешевле полной загрузки. Уменьшение при отказе —
    # тем же правилом, что и у полной выгрузки.
    expected = -1
    top = PAGE
    probe, skip, first = [], 0, True
    while True:
        params = {"$format": "json", "$select": "Ref_Key,DataVersion",
                  "$top": str(top), "$skip": str(skip)}
        if first:
            params["$inlinecount"] = "allpages"
        # Сортировка по ключу нужна ТОЛЬКО при постраничности: без неё `$skip/$top`
        # перекрываются и теряют строки. На одной странице сортировать нечего (и это
        # снимает `HTTP 500` на сущностях, где `$orderby` капризничает).
        if not first and (expected < 0 or expected > top):
            params["$orderby"] = "Ref_Key"
        try:
            doc = _fetch_page_doc(es, params)
            page = doc.get("value", [])
            if first:
                first = False
                try:
                    expected = int(doc.get("odata.count", doc.get("__count", -1)))
                except (TypeError, ValueError):
                    expected = -1
                if expected < 0:
                    expected = count_of(es)
                # Одной страницей не обошлось, а читали без порядка — начинаем сначала.
                if len(page) >= top and (expected < 0 or expected > top):
                    probe, skip = [], 0
                    continue
        except Exception:                       # noqa: BLE001
            if top <= PAGE_MIN:
                raise
            top = max(PAGE_MIN, top // 4)
            probe, skip, first = [], 0, True    # см. разбор в `fetch_all`: начинаем сначала
            continue
        if not page:
            break
        probe.extend(page)
        skip += len(page)
        if expected >= 0 and len(probe) >= expected:
            break
    ver_1c = {r.get("Ref_Key"): r.get("DataVersion") for r in probe if r.get("Ref_Key")}
    # 🔴 НЕПОЛНАЯ ПРОБА — НЕ ДЕЛЬТА. Если снимок версий короче, чем сущность в 1С, часть
    # живых записей выглядела бы «удалённой» и была бы стёрта. Лучше отдать на полную
    # загрузку (она сверяется с `$count` и не удаляет по неполному снимку).
    if expected >= 0 and len(ver_1c) < expected:
        return None
    # `DISTINCT` обязателен: у развёрнутого документа строк столько, сколько в его
    # табличной части, а версия у них одна на всех. Без него мы тянули бы из движка
    # десятки тысяч одинаковых пар вместо нескольких сотен.
    mart = dict(_psql_rows('SELECT DISTINCT "Ref_Key","DataVersion" FROM "%s"' % table))
    changed = [k for k, v in ver_1c.items() if mart.get(k) != v]
    gone = [k for k in mart if k not in ver_1c]
    if not changed and not gone:
        return {"entity": es, "table": table, "rows": len(mart), "delta": True,
                "changed": 0, "gone": 0, "sec": round(time.time() - t0, 2)}

    # Изменённые тянем ПРЯМЫМ ДОСТУПОМ по ключу: `Сущность(guid'KEY')`. `$filter` по
    # `Ref_Key` 1С не поддерживает — [замер 28.07] отдаёт HTTP 500, а прямой доступ 200.
    # По запросу на ключ, но каждый крошечный (одна запись) и только для изменившихся.
    new_rows = []
    for k in changed:
        try:
            obj = _get_json(es, {"$format": "json"}, key=k)
        except urllib.error.HTTPError as e:
            if e.code == 404:                  # запись успели удалить между пробой и тягой
                gone.append(k)
                continue
            raise
        if isinstance(obj, dict) and obj.get("Ref_Key"):
            new_rows.append(obj)

    # 🔴 ВЫТЯНУТЫЙ ОБЪЕКТ РАЗВОРАЧИВАЕТСЯ ТАК ЖЕ, КАК ПРИ ПОЛНОЙ ЗАГРУЗКЕ. Прямой доступ
    # по ключу отдаёт документ во вложенной форме — с табличной частью массивом внутри.
    # Витрина же хранит его развёрнутым (строка на строку табличной части). Положи мы
    # сюда объект как есть — в таблицу уехал бы один ряд с массивом в ячейке вместо
    # десятка строк, то есть молчаливая потеря данных (п. 13) ровно в тех документах,
    # которые ИЗМЕНИЛИСЬ. У плоской сущности разворот ничего не делает.
    if new_rows:
        new_rows, _ = _flatten_nested(new_rows, es)

    if new_rows:
        cols = [c[0] for c in _psql_rows(
            "SELECT column_name FROM duckdb_columns() WHERE table_name=%s "
            "ORDER BY column_index" % _lit(table))]
        # 🔴 КОЛОНКА ВИТРИНЫ И ПОЛЕ 1С НАЗЫВАЮТСЯ ПО-РАЗНОМУ, И ИСКАТЬ НАДО ПО СООТВЕТСТВИЮ.
        # Имена колонок приходят из движка уже безопасными (`safe_col`), а в ответе 1С поле
        # зовётся как есть. Пока значение искали прямо по имени колонки, всякое поле, чьё
        # имя `safe_col` меняет, доставалось как пустое: 1С отдаёт ссылки парой
        # `Партнер_Key` и `Партнер@navigationLinkUrl`, и второе в витрине зовётся
        # `Партнер_navigationLinkUrl` — по этому имени в ответе нет ничего. То есть
        # изменившийся объект дописывался с пустыми ссылками, и это молчаливо (п. 13).
        # Соответствие строим по самим данным, а не по догадке об именах.
        raw_by_safe = {}
        for r in new_rows:
            for k in r:
                raw_by_safe.setdefault(safe_col(k), k)
        csv_path = os.path.join(CSV_DIR, f"{table}__delta.csv")
        with open(csv_path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(cols)
            for r in new_rows:
                w.writerow([_cell(r.get(raw_by_safe.get(c, c))) for c in cols])
        subprocess.run(["chown", "serenedb:serenedb", csv_path], check=False)
        csv_opts = ("header=true, all_varchar=true, quote='\"', escape='\"', "
                    "maximum_line_size=%d" % int(os.environ.get("ETL_CSV_MAX_LINE", 200 * 1024 * 1024)))
        merge = (
            'CREATE OR REPLACE TEMP TABLE "d_%s" AS SELECT * FROM read_csv(\'%s\', %s);\n'
            'DELETE FROM "%s" WHERE "Ref_Key" IN (SELECT "Ref_Key" FROM "d_%s");\n'
            'INSERT INTO "%s" SELECT * FROM "d_%s";\n'
            % (table, csv_path, csv_opts, table, table, table, table))
        r = subprocess.run(["psql", DSN, "-v", "ON_ERROR_STOP=1"], input=merge,
                           text=True, capture_output=True)
        if r.returncode != 0:
            raise RuntimeError("delta upsert error: %s" % r.stderr.strip()[:200])
    if gone:
        # Удаление через VALUES-набор в stdin, а не `IN (…)` аргументом: тысячи ключей
        # не влезают в командную строку. Ключи — литералами внутри тела запроса.
        vals = ",".join("(%s)" % _lit(k) for k in gone)
        _psql_exec('DELETE FROM "%s" WHERE "Ref_Key" IN '
                   '(SELECT k FROM (VALUES %s) AS g(k));' % (table, vals))
    n = _psql_rows('SELECT count(*) FROM "%s"' % table)
    return {"entity": es, "table": table, "rows": int(n[0][0]) if n else len(ver_1c),
            "delta": True, "changed": len(changed), "gone": len(gone),
            "sec": round(time.time() - t0, 2)}


def load_entity(es, ro_role="serene_ro"):
    """Сущность 1С (OData) -> CSV -> таблица SereneDB (полная идемпотентная перезагрузка) +
    GRANT SELECT ro-роли (default privileges на SereneDB не всегда покрывают новые таблицы).
    Возвращает dict со статистикой. Переиспользуется штатным синком (serene_sync.py)."""
    table = safe_col(es).lower()
    csv_path = os.path.join(CSV_DIR, f"{table}.csv")
    t0 = time.time()
    rows = fetch_all(es)
    dt = round(time.time() - t0, 2)
    if not rows:
        return {"entity": es, "table": table, "rows": 0, "sec": dt}
    cols = list(dict.fromkeys(k for r in rows for k in r.keys()))  # union полей, порядок стабильный
    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow([safe_col(c) for c in cols])
        for r in rows:
            w.writerow([_cell(r.get(c)) for c in cols])
    subprocess.run(["chown", "serenedb:serenedb", csv_path], check=False)
    grant = f'GRANT SELECT ON "{table}" TO {ro_role};\n' if ro_role else ""
    # Grain-инвариант: одна строка на ОБЪЯВЛЕННЫЙ КЛЮЧ, а не на Ref_Key.
    #
    # Раньше здесь стояло PARTITION BY ref_key. Для справочника и шапки документа это
    # верно, для ТАБЛИЧНОЙ ЧАСТИ — нет: её ключ составной (Ref_Key + LineNumber), и все
    # строки одной накладной имеют один Ref_Key. Дедуп оставлял из них ОДНУ.
    # Замерено против 1С: Document_РеализацияТоваровУслуг_Товары — 76 строк в базе, 30 в
    # витрине; количество 499 штук -> 213, сумма 12 052 500 -> 7 856 600.
    # Сверка с $count это не ловила: fetch_all сверяет ДО дедупа и честно видит 76 == 76.
    # Поэтому теперь: ключ берём объявленный, а снятое дедупом — считаем и показываем.

    # 🔴 ФОРМАТ ЗАДАЁМ ЯВНО, А НЕ УГАДЫВАЕМ. CSV пишем мы сами, поэтому сообщать читателю
    # его устройство обязаны тоже мы. С авторазбором сущность с вложением молча не
    # грузилась вовсе: [замер 28.07] `Catalog_ВнешниеКомпоненты` — 19 МБ на ОДНУ строку
    # (внутри base64-архив с переносами строк), читатель упирался в предел длины строки и
    # отдавал `CSV Error on Line: 1`. Ошибка печаталась в поток и нигде не сохранялась,
    # поэтому в переписи стояло «не загрузилось» без причины, а сущность отсутствовала в
    # поиске. С явным пределом строка читается: замерено, 1 из 1.
    # Предел берётся из окружения: это БЮДЖЕТ ПАМЯТИ, а не порог правильности — при
    # нехватке загрузка падает с ошибкой, а не отбрасывает данные молча.
    csv_opts = ("header=true, all_varchar=true, quote='\"', escape='\"', "
                "maximum_line_size=%d" % int(os.environ.get("ETL_CSV_MAX_LINE", 200 * 1024 * 1024)))

    key_cols = [safe_col(k) for k in declared_key(es)]
    key_cols = [k for k in key_cols if any(safe_col(c) == k for c in cols)]
    # 🔴 У ВЛОЖЕННОЙ ФОРМЫ ОБЪЯВЛЕННЫЙ КЛЮЧ — КЛЮЧ ОБЁРТКИ, А НЕ СТРОКИ. Дедуп по нему
    # оставляет одну строку на обёртку и выбрасывает остальные: [замер 28.07]
    # `AccountingRegister_Хозрасчетный` — 280 движений, ключ обёртки `Recorder`,
    # после дедупа 104, молча потеряно 176 проводок. Это ровно тот дефект зерна, что
    # разобран выше для табличных частей, только пришедший с другой стороны.
    # Развёрнутые строки уже различны по устройству, поэтому снимаем только полностью
    # одинаковые — без ключа, а значит и без возможности выбросить лишнее.
    if es in _NESTED_SEEN:
        key_cols = []
    # Узлы-ПАПКИ иерархии (группы номенклатуры, категории, регионы) раньше отбрасывались
    # как «не бизнес-строки». Для коробки это неверно: требование владельца — «информация
    # должна быть вся», а про группы спрашивают ровно так же, как про элементы («что в
    # группе Электроника», «какие группы товаров есть»). Замерено: на одном справочнике
    # это 4361 строка из 23 878 — 18% данных, выброшенных молча.
    # Папки остаются различимы: колонка IsFolder есть в витрине, поиск её видит.
    where = ""
    if key_cols:
        part = ", ".join('"%s"' % k for k in key_cols)
        select = (f"SELECT * FROM read_csv('{csv_path}', {csv_opts}){where} "
                  f"QUALIFY row_number() OVER (PARTITION BY {part} ORDER BY {part}) = 1")
    else:
        # Ключа не объявлено — снимаем только полностью идентичные строки.
        select = f"SELECT DISTINCT * FROM read_csv('{csv_path}', {csv_opts}){where}"
    # 🔴 ПОЛНАЯ ЗАГРУЗКА — ЕЩЁ НЕ ИЗМЕНЕНИЕ. Прежде здесь безусловно шло
    # `DROP TABLE; CREATE TABLE AS …`, и любая полная загрузка объявляла витрину
    # изменённой. Цена этого замерена и она не косвенная: [замер 05.08] строка
    # «изменённых строк 732475» повторилась в журнале ДОСЛОВНО в четырнадцати тактах
    # подряд за двое суток — в 1С за это время не менялось ничего, а такт каждый раз
    # пересобирал корпус (780 с) и заново публиковал индекс. Указание владельца 05.08:
    # «надо смотреть, какие были изменения, и отрабатывать только изменённые записи».
    #
    # Признака изменения у 843 источников платформа не даёт вовсе (независимые регистры
    # сведений, константы) — узнать, менялись ли они, можно только прочитав. Но
    # ПРОЧИТАТЬ и ПЕРЕПИСАТЬ — разные вещи: прочитав, мы можем сравнить и не переписывать.
    #
    # Сравнение делает ДВИЖОК одним запросом (п. 20): симметричная разность через
    # `EXCEPT ALL` в обе стороны. `ALL` обязателен — у мешочной семантики одинаковые
    # строки не схлопываются, а у витрины дубли законны (регистры без уникального ключа).
    # Доки: Sql › Query syntax › Set Operations.
    #
    # Любая ошибка сравнения (таблицы ещё нет, изменился состав колонок — набор операций
    # сверяет по ПОЗИЦИИ и требует одинакового числа колонок) означает «считаем
    # изменившимся»: ошибка в сторону лишней работы, а не в сторону потери свежести.
    same = False
    q = (f'SELECT (SELECT count(*) FROM (({select}) EXCEPT ALL (SELECT * FROM "{table}"))) '
         f'     + (SELECT count(*) FROM ((SELECT * FROM "{table}") EXCEPT ALL ({select})))')
    c0 = subprocess.run(["psql", DSN, "-tAc", q], text=True, capture_output=True)
    if c0.returncode == 0 and c0.stdout.strip() == "0":
        same = True
    if same:
        # Витрина не переписывается: ни `DROP`, ни `CREATE`, ни выдача прав заново.
        n = len(rows)
        c = subprocess.run(["psql", DSN, "-tAc", f'SELECT count(*) FROM "{table}";'],
                           text=True, capture_output=True)
        if c.returncode == 0 and c.stdout.strip().isdigit():
            n = int(c.stdout.strip())
        return {"entity": es, "table": table, "rows": n, "rows_raw": len(rows),
                "dropped": len(rows) - n, "cols": len(cols), "sec": dt, "changed": 0}

    sql = (
        f'DROP TABLE IF EXISTS "{table}";\n'
        f'CREATE TABLE "{table}" AS {select};\n' + grant
    )
    r = subprocess.run(["psql", DSN, "-v", "ON_ERROR_STOP=1"], input=sql, text=True, capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(f"load error: {r.stderr.strip()[:200]}")
    c = subprocess.run(["psql", DSN, "-tAc", f'SELECT count(*) FROM "{table}";'], text=True, capture_output=True)
    n = int(c.stdout.strip()) if c.returncode == 0 and c.stdout.strip().isdigit() else len(rows)
    # rows = grain витрины (после дедупа), rows_raw = сколько строк отдал OData.
    # Расхождение между ними — ВСЕГДА в журнал. Дедуп законен только когда страницы
    # OData перекрылись; любое другое расхождение означает, что мы выбросили данные,
    # и молчать о нём нельзя: именно так 61% строк накладных пропали незаметно, потому
    # что rows_raw никуда не выводился.
    if len(rows) != n:
        sys.stderr.write("%s: OData отдал %d строк, в витрине %d — дедуп снял %d "
                         "(ключ: %s)\n" % (es, len(rows), n, len(rows) - n,
                                           ",".join(key_cols) or "не объявлен"))
    return {"entity": es, "table": table, "rows": n, "rows_raw": len(rows),
            "dropped": len(rows) - n, "cols": len(cols), "sec": dt, "changed": n}


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: poc_load_entity.py <EntitySet>  (напр. Catalog_КлассификаторБанков)")
    res = load_entity(sys.argv[1])
    print(res)


if __name__ == "__main__":
    main()
