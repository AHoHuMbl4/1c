#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Сборка поискового корпуса и гибридного индекса над витриной SereneDB.

Зачем: чтобы отвечать на вопрос, система должна НАЙТИ нужные строки в базе, а не грузить
схему в модель (см. docs/TARGET_ARCHITECTURE.md). Индекс — один на всю витрину:
текст (BM25) + вектор (смысл) + числовые/датовые колонки в INCLUDE для условий и агрегатов.

Коробочность: ни одного имени сущности, колонки или ключа в коде. Всё определяется
ПО СТРУКТУРЕ значений:
  * GUID  -> ссылка, резолвится в наименование по общей карте;
  * base64/URL -> машинный токен, в поиск не идёт;
  * колонка-наименование -> самая «человекочитаемая» по форме значений (слова x доля букв),
    поэтому наименование выигрывает у кода (00-000006) без единого имени в коде;
  * число для агрегатов -> колонка с наибольшим максимумом;
  * дата -> первая временная колонка.

Инкремент: эмбеддинг считается ТОЛЬКО для новых и изменившихся строк (сверка по hash текста).
Это делает такт обновления минутами, а не 8 минутами полного пересчёта.

Запуск: под RW (postgres). Env — /etc/1c-serene-sync.env + /etc/1c-mcp-reports.env.
"""
import concurrent.futures as cf
import csv
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

DSN = os.environ.get("SERENEDB_DSN", "host=127.0.0.1 port=7890 user=postgres dbname=postgres")
EMBED_DIM = int(os.environ.get("EMBED_DIM", "1536"))
EMBED_MODEL = os.environ.get("EMBED_MODEL", "text-embedding-v4")
BATCH = 10          # лимит DashScope на батч
# Строк на INSERT. Раньше 20 из-за длины argv, но запись давно идёт через stdin, и
# ограничения нет. При 20 запись блокировала главный поток каждые две пачки, и пул
# эмбеддинга простаивал: замерено 43 с против 29 с на том же корпусе.
INS = int(os.environ.get("BUILD_INSERT_ROWS", "200"))
# Одновременных пачек эмбеддинга. Значение выбрано ЗАМЕРОМ на полном корпусе, а не
# наугад: 1 -> 0.151 с/строка, 8 -> 0.019, 16 -> 0.0098, 24 -> 0.008. На 16 полная
# сборка 2882 строк прошла за 28 с эмбеддингов без единой ошибки; 24 проверялось только
# коротким всплеском, поэтому умолчанием не ставим — лимиты поставщика считаются в
# запросах в минуту, и на многочасовой сборке всплеск не показателен.
PARALLEL = int(os.environ.get("BUILD_EMBED_PARALLEL", "16"))
CORPUS = "search_corpus"
INDEX = "search_idx"
DICT = "search_dict"
TABLES = "search_tables"

GUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
NULL_GUID = "00000000-0000-0000-0000-000000000000"
B64 = re.compile(r"^[A-Za-z0-9+/]{8,}={0,2}$")
URLISH = re.compile(r"^(https?://|/)")


def env_from(path):
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k, v)
    except IOError:
        pass


for _f in ("/etc/1c-serene-sync.env", "/etc/1c-mcp-reports.env"):
    env_from(_f)


def machine_token(v):
    """Значение машинное: ссылка. Только это можно утверждать по ФОРМЕ.

    Раньше здесь угадывались ещё и идентификаторы («латиница + цифры + заглавные»),
    и под это правило попадали настоящие данные бизнеса: `INV000000021`,
    `WVWZZZ1JZXW000001` (VIN), `NKE2024AM270BLK` (артикул), `DE89…` (IBAN).
    На нашей базе это не проявлялось только потому, что её номера содержат кириллицу.
    Версия записи теперь отбрасывается по контракту (`STANDARD_SERVICE_PROPS`).
    """
    return bool(v) and bool(URLISH.match(v))


_META_CACHE = {}


def odata_types():
    """Объявленные типы свойств из `$metadata` самой базы: {сущность_lower: {свойство: Edm-тип}}.

    Это единственный правильный источник: 1С сама говорит, что `ИНН` и `КПП` — `Edm.String`
    (код, а не число), а `СуммаДокумента` — `Edm.Double` (деньги). Угадывать по форме
    значений нельзя: витрина строится через CSV, а сниффер типов превращает ИНН в число,
    после чего «сумма документа» находится в паспортных данных контрагента.

    Работает для любой конфигурации и языка — имена свойств не важны, важен объявленный тип.
    Если метаданные недоступны — возвращаем пусто, вызывающий переходит на разбор по форме.
    """
    if _META_CACHE:
        return _META_CACHE                  # 15 МБ и 16 с за загрузку — тянем один раз
    base = os.environ.get("ETL_ODATA_BASE", "http://127.0.0.1:6011").rstrip("/")
    req = urllib.request.Request(base + "/$metadata")
    tok = os.environ.get("ODG_GATEWAY_TOKEN", "")
    if tok:
        req.add_header("Authorization", "Bearer " + tok)
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            xml = r.read().decode("utf-8", "replace")
    except Exception as e:                      # noqa: BLE001
        sys.stderr.write("metadata недоступны (%s) — типы будут определяться по форме\n" % e)
        return {}
    out = {}
    for m in re.finditer(r'<EntityType\s+Name="([^"]+)"(.*?)</EntityType>', xml, re.S):
        name, body = m.group(1), m.group(2)
        ENTITY_NAMES[name.lower()] = name      # оригинальный регистр нужен для подписей
        # Ключ объявлен явно и бывает СОСТАВНЫМ. «Первая Guid-колонка» — неверно:
        # у регистров Guid-колонок нет вовсе, и все строки таблицы получали пустой
        # ключ, схлопываясь в одну запись корпуса.
        km = re.search(r"<Key>(.*?)</Key>", body, re.S)
        if km:
            ENTITY_KEYS[name.lower()] = re.findall(r'<PropertyRef\s+Name="([^"]+)"', km.group(1))
        props = {}
        for p in re.finditer(r'<Property\s+Name="([^"]+)"\s+Type="([^"]+)"', body):
            props[p.group(1)] = p.group(2)
        if props:
            out[name.lower()] = props
    _META_CACHE.update(out)
    return out


ENTITY_NAMES = {}          # сущность_lower -> оригинальное имя из $metadata
ENTITY_KEYS = {}           # сущность_lower -> список свойств объявленного ключа

# Служебное свойство OData-интерфейса 1С: версия записи. Отбрасываем ПО КОНТРАКТУ,
# а не по форме значения. Прежний разбор «латиница+цифры+заглавные = мусор» выбрасывал
# заодно настоящие бизнес-идентификаторы: номера документов вида INV000000021, VIN,
# артикулы, IBAN — на чужой конфигурации их просто не было бы в поиске.
STANDARD_SERVICE_PROPS = ("DataVersion",)

# Служебные свойства OData-интерфейса 1С: одинаковы в любой конфигурации и на любом
# языке (сама конфигурация может быть хоть японской — эти имена задаёт платформа).
# Мы их НЕ предполагаем: используем только если сущность объявила их в своих метаданных.
STANDARD_NAME_PROPS = ("Description", "Code")
STANDARD_DATE_PROPS = ("Date",)

# Локаль словаря. Замерено: на регистр и на результат поиска не влияет (ru_RU, en_US и
# несуществующая xx_XX дают одинаковые совпадения), но это единственный языковой литерал
# в исполняемом DDL — выносим в настройку, чтобы он не выглядел допущением о языке базы.
DICT_LOCALE = os.environ.get("BUILD_DICT_LOCALE", "ru_RU.UTF-8")

SAMPLE = int(os.environ.get("BUILD_SAMPLE", "20"))   # сколько значений смотреть при разборе
NAME_COLS = int(os.environ.get("BUILD_NAME_COLS", "2"))  # сколько наименований склеивать

NUMERIC_EDM = ("Edm.Double", "Edm.Decimal", "Edm.Int16", "Edm.Int32", "Edm.Int64", "Edm.Byte")


# У csv-разбора Python лимит поля 128 КБ. На реальной базе есть хранилища и вложения
# заметно больше — сборка падала «field larger than field limit». Значение поднимаем,
# но главная защита не в нём, а в обрезке текста на стороне базы (см. TEXT_CLIP).
csv.field_size_limit(50 * 1024 * 1024)

# Предел длины ОДНОГО значения при чтении. Раньше в корпус попадало 200 символов —
# длинный комментарий искался только по началу, то есть часть информации была
# недоступна поиску. Движок индексирует длинный текст нормально, а модель видит
# подсвеченный фрагмент, а не строку целиком, поэтому режем только патологические
# случаи: хранилища и вложения, которые всё равно не текст.
TEXT_CLIP = int(os.environ.get("BUILD_TEXT_CLIP", "20000"))


def clip(col, is_text=True):
    """Выражение выборки колонки с обрезкой длинного текста прямо в базе."""
    return ('substr(CAST("%s" AS VARCHAR), 1, %d)' % (col, TEXT_CLIP)) if is_text else '"%s"' % col


def q(sql):
    """Выполнить SQL. Читаем CSV, а не «строка = запись».

    В комментарии или адресе доставки бывает перевод строки — при построчном разборе
    колонки съезжают, ключом становится обрывок текста, а короткая строка роняет
    сервис. CSV-разбор это исключает: кавычки и переводы строк внутри значений
    обрабатывает сам формат.
    """
    p = subprocess.run(["psql", DSN, "-tA", "--csv", "-c", sql],
                       capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError("SQL: %s\n%s" % (sql[:200], (p.stderr or "")[:400]))
    return [r for r in csv.reader(io.StringIO(p.stdout)) if r]


def ddl(sql):
    """DDL/INSERT через stdin: длинные вектора не помещаются в argv."""
    p = subprocess.run(["psql", DSN, "-v", "ON_ERROR_STOP=1", "-f", "-"],
                       input=sql, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError("DDL: %s\n%s" % (sql[:200], (p.stderr or "")[:400]))


def embed(texts):
    url = os.environ.get("ALIBABA_EMBED_URL", "").rstrip("/") + "/embeddings"
    body = json.dumps({"model": EMBED_MODEL, "dimensions": EMBED_DIM, "input": texts}).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Authorization", "Bearer " + os.environ.get("ALIBABA_API_KEY", ""))
    req.add_header("Content-Type", "application/json")
    last = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return [d["embedding"] for d in json.loads(r.read())["data"]]
        except Exception as e:          # noqa: BLE001 — сеть/квоты, ретраим
            last = e
            time.sleep(1.5 * (attempt + 1))
    raise last


MONEY_SYS = """You are given the numeric field names of one record type in an ERP database.
Pick the ONE field that holds the record's monetary total — the amount of money the
document is for. Answer with the NUMBER of that field only. If none of them is a money
total (they are counters, order indices, ordinal numbers, quantities, rates), answer 0."""


def money_column(entity_label, names):
    """Какая из числовых колонок — деньги. Спрашиваем модель по ИМЕНАМ.

    Почему не «самая большая по величине»: это правило уже промахнулось на нашей же
    базе — в справочниках «суммой» стал служебный реквизит упорядочивания, а на рознице
    номер чека ККМ (тоже целое, тоже объявлен рядом с суммой) обогнал бы средний чек.
    Отличить деньги от счётчика по величине нельзя; по имени — можно, и это чисто
    языковая задача. Кандидаты приходят из метаданных базы, а не из кода.
    """
    if not names:
        return None
    if len(names) == 1:
        return names[0]
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not key:
        return None
    listing = "\n".join("%d. %s" % (i + 1, n) for i, n in enumerate(names))
    body = json.dumps({
        "model": os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash"),
        "temperature": 0, "max_tokens": 8,
        "thinking": {"type": "disabled"},
        "messages": [{"role": "system", "content": MONEY_SYS},
                     {"role": "user", "content": "Record type: %s\n\nFields:\n%s"
                      % (entity_label, listing)}]}).encode()
    req = urllib.request.Request(
        os.environ.get("DEEPSEEK_BASE", "https://api.deepseek.com").rstrip("/")
        + "/v1/chat/completions", data=body, method="POST")
    req.add_header("Authorization", "Bearer " + key)
    req.add_header("Content-Type", "application/json")
    raw = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                raw = json.loads(r.read())["choices"][0]["message"]["content"]
            break
        except Exception:                   # noqa: BLE001 — сеть/квота поставщика
            # Сборка обходит сотни сущностей подряд; одиночный отказ по лимиту не должен
            # превращаться в «сущность без денег» на весь следующий такт.
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
    if raw is None:
        return None
    m = re.search(r"\d+", raw or "")
    if not m:
        return None
    i = int(m.group(0))
    if i == 0:
        return ""                      # модель прямо сказала: денежной колонки нет
    return names[i - 1] if 1 <= i <= len(names) else ""


def num_cols_of(tcols, declared):
    """Числовые колонки: по объявленному типу, иначе по типу в витрине."""
    if declared:
        return [c for c, _dt in tcols if declared.get(c) in NUMERIC_EDM]
    return [c for c, dt in tcols
            if dt in ("BIGINT", "DOUBLE", "DECIMAL", "INTEGER", "HUGEINT")]


def profile_table(t, tcols, txt_candidates, num_candidates):
    """Профиль таблицы ОДНИМ запросом вместо запроса на каждую колонку.

    Было: на каждую колонку отдельный процесс `psql` — счёт различных значений,
    выборка образцов, максимум по числовой. На 19 таблицах это 1073 запуска процесса
    по 39 мс каждый, то есть почти минута чистых накладных расходов. На витрине с
    тысячами таблиц счёт пошёл бы на часы.

    Стало: два запроса на таблицу — агрегаты и образцы.
    """
    prof = {"distinct": {}, "maxabs": {}, "samples": {}}
    aggs = []
    for c in txt_candidates:
        aggs.append('count(DISTINCT "%s")' % c)
    for c in num_candidates:
        # TRY_CAST: тип объявлен базой, но в витрине значение могло приехать текстом
        # (CSV-сниффер). Без него abs() падает на несовместимом типе и роняет сборку.
        aggs.append('coalesce(max(abs(TRY_CAST("%s" AS DOUBLE))),0)' % c)
    if aggs:
        row = q("SELECT %s FROM \"%s\"" % (", ".join(aggs), t))
        vals = row[0] if row else []
        for i, c in enumerate(txt_candidates):
            try:
                prof["distinct"][c] = int(vals[i])
            except (ValueError, IndexError):
                prof["distinct"][c] = 0
        for j, c in enumerate(num_candidates):
            k = len(txt_candidates) + j
            try:
                prof["maxabs"][c] = float(vals[k])
            except (ValueError, IndexError):
                prof["maxabs"][c] = 0.0
    sample_cols = list(txt_candidates) + [c for c in num_candidates if c not in txt_candidates]
    if sample_cols:
        sel = ", ".join(clip(c) for c in sample_cols)
        rows = q("SELECT %s FROM \"%s\" LIMIT %d" % (sel, t, SAMPLE))
        for i, c in enumerate(sample_cols):
            prof["samples"][c] = [r[i] for r in rows if i < len(r) and r[i]]
    return prof


def split_camel(name):
    """«ПоступлениеТоваровУслуг» -> «Поступление Товаров Услуг».

    Слитое имя эмбеддится плохо, разделённое — как обычная фраза. Разрыв ставим по
    смене регистра средствами самого Unicode (`isupper`/`islower`), а не диапазоном
    букв: диапазон пришлось бы писать под каждый алфавит, и для греческой или любой
    другой конфигурации имя осталось бы слитным.
    """
    out = []
    for i, ch in enumerate(name):
        if i and ch.isupper() and name[i - 1].islower():
            out.append(" ")
        out.append(ch)
    return "".join(out)


def lit(s):
    return "'" + s.replace("'", "''") + "'"


def build_corpus():
    """Совместимость: собрать весь корпус списком (используется проверками и замерами)."""
    out, nt, nref = [], 0, 0
    for t, rows, nt, nref in iter_corpus():
        out.extend(rows)
    return out, nt, nref


def iter_corpus():
    """Отдавать корпус ПО ТАБЛИЦАМ, а не одним списком.

    Иначе память растёт линейно с размером базы: на миллион строк это сотни мегабайт
    текста, которые держатся всё время сборки без всякой нужды — каждая таблица
    обрабатывается независимо. Общей остаётся только карта ссылок, она нужна всем.
    Возвращает (таблица, строки, всего_таблиц, размер_карты_ссылок).
    """
    tables = [r[0] for r in q(
        "SELECT table_name FROM duckdb_tables() WHERE database_name='postgres' "
        "  AND table_name NOT LIKE 'duckdb%%' AND table_name NOT LIKE '%s%%' "
        "  AND table_name<>'resolver_index'" % CORPUS.split("_")[0])]
    live = []
    for t in tables:
        n = int(q('SELECT count(*) FROM "%s"' % t)[0][0])
        if n:
            live.append((t, n))

    cols = {t: q("SELECT column_name, data_type FROM duckdb_columns() "
                 "WHERE table_name=%s ORDER BY column_index" % lit(t)) for t, _ in live}

    # Источник — только бизнес-данные. Таблицы с колонкой-вектором (наш же корпус,
    # резолвер, отладочные копии) исключаем ПО СТРУКТУРЕ, а не по имени: иначе
    # индекс начинает индексировать сам себя.
    live = [(t, n) for t, n in live
            if not any("[" in dt for _c, dt in cols[t])]
    cols = {t: cols[t] for t, _ in live}

    meta = odata_types()
    if meta:
        print("типы взяты из $metadata базы: %d сущностей" % len(meta))

    def split_cols(t):
        """Разделить колонки таблицы на ССЫЛКИ и ТЕКСТ по объявленному типу.

        Ключ строки и ссылки на другие объекты — `Edm.Guid`; свободный текст — `Edm.String`.
        Без этого разделения `Ref_Key` пропадает из обработки (он не String), и все строки
        таблицы получают пустой ключ — корпус схлопывается.
        """
        declared = meta.get(t.lower(), {})
        if declared:
            guid_cols = [c for c, _dt in cols[t] if declared.get(c) == "Edm.Guid"]
            txt = [c for c, _dt in cols[t] if declared.get(c) == "Edm.String"
                   and c not in STANDARD_SERVICE_PROPS]
        else:
            # Запасной разбор (метаданных нет): образцы всех текстовых колонок берём
            # ОДНИМ запросом, а не запросом на колонку.
            vcols = [c for c, dt in cols[t] if "VARCHAR" in dt]
            guid_cols, txt = [], []
            if vcols:
                sel = ", ".join(clip(c) for c in vcols)
                rows = q("SELECT %s FROM \"%s\" LIMIT %d" % (sel, t, SAMPLE))
                for i, c in enumerate(vcols):
                    smp = [r[i] for r in rows if i < len(r) and r[i]]
                    (guid_cols if smp and all(GUID.match(v) for v in smp) else txt).append(c)
        return declared, guid_cols, txt

    # --- карта ссылок: GUID -> человекочитаемое наименование
    refmap = {}
    for t, n in live:
        declared, gcols, ccols = split_cols(t)
        key_col, scored = (gcols[0] if gcols else None), []
        prof = profile_table(t, cols[t], ccols, [])

        # Сначала — КОНТРАКТ ПЛАТФОРМЫ. OData-интерфейс 1С объявляет служебные свойства
        # одинаково в любой конфигурации и на любом языке. Мы их не предполагаем: берём
        # только те, что сущность РЕАЛЬНО объявила в своих метаданных. Документы,
        # например, наименования не имеют — там сработает разбор ниже.
        # Контракт платформы — первым, ранжирование — дополнением. Так не теряется
        # полное наименование (по нему тоже ищут), и при этом не нужен порог.
        std = [c for c in STANDARD_NAME_PROPS if c in declared]
        name_cols = list(std)
        if True:
            for c in ccols:
                if c in std:
                    continue
                vals = prof["samples"].get(c) or []
                if not vals or any(machine_token(v) for v in vals):
                    continue
                # Порогов нет — только СРАВНЕНИЕ кандидатов между собой. Отсечка вида
                # «уникальность выше половины» требовала бы подбора под каждую базу;
                # ранжирование самокалибруется: побеждает лучший из того, что есть.
                words = sum(len(v.split()) for v in vals) / len(vals)
                alpha = sum(sum(ch.isalpha() for ch in v) / max(len(v), 1) for v in vals) / len(vals)
                uniq = prof["distinct"].get(c, 0) / max(n, 1)
                scored.append((words * alpha * uniq, c))
            extra = [c for _s, c in sorted(scored, reverse=True)]
            name_cols += extra[:max(0, NAME_COLS + 1 - len(name_cols))]
        if key_col and name_cols:
            sel = ", ".join(clip(c) for c in name_cols)
            for row in q('SELECT "%s", %s FROM "%s" WHERE "%s" IS NOT NULL'
                         % (key_col, sel, t, key_col)):
                g, names = row[0], [x for x in row[1:] if x]
                if not g or g == NULL_GUID or not names:
                    continue
                uniq = []
                for nm in names:               # краткое и полное; дубли не плодим
                    if nm not in uniq and not any(nm in u for u in uniq):
                        uniq.append(nm)
                refmap[g] = " / ".join(uniq)

    # --- тексты строк
    for t, n in live:
        corpus = []
        tcols = cols[t]
        declared, guid_cols, cand_txt = split_cols(t)
        prof = profile_table(t, tcols, cand_txt, num_cols_of(tcols, declared))
        key_props = [c for c in ENTITY_KEYS.get(t.lower(), [])
                     if any(c == cn for cn, _dt in tcols)]

        # ЧИСЛО ДЛЯ АГРЕГАТОВ. Правильный источник — объявленный тип: 1С сама говорит,
        # что ИНН/КПП/счёт это строки-коды, а сумма документа — Edm.Double. Витрина
        # приезжает через CSV, и её сниффер типов этого не знает: ИНН становится BIGINT.
        # Поэтому доверяем метаданным, а форму значений используем только как запасной
        # вариант, когда метаданные недоступны.
        # num_cols вычисляется БЕЗУСЛОВНО. Раньше присваивание стояло внутри
        # `if declared:` — и при отсутствии метаданных ветка падала UnboundLocalError,
        # то есть весь заявленный «запасной разбор по форме» не исполнялся никогда.
        # Хуже промежуточный случай: часть сущностей в метаданных есть, часть нет —
        # тогда num_cols ПРОТЕКАЛ с предыдущей итерации цикла, и колонкой денег
        # становилась колонка чужой сущности. Это не отказ и не падение, а тихо
        # неверные агрегаты.
        num_cols = num_cols_of(tcols, declared)
        picked_money = money_column(split_camel(ENTITY_NAMES.get(t.lower(), t)),
                                    num_cols) if declared else None
        amount_col = picked_money or None
        # Запасной разбор по форме — ТОЛЬКО когда метаданных нет вовсе. Если метаданные
        # есть, а модель недоступна, лучше остаться БЕЗ суммы, чем подставить «самое
        # большое число»: на нашей же базе это правило выбирало служебный реквизит
        # упорядочивания и процент комиссии. Неверное число хуже отсутствующего —
        # отсутствие видно, неверное уходит клиенту как факт.
        fallback = (picked_money is None) and not declared
        if picked_money is None and declared:
            sys.stderr.write("%s: денежная колонка не определена (модель недоступна) — "
                             "агрегаты по этой сущности считаться не будут\n" % t)
        best = 1e18 if amount_col else -1
        for c in (num_cols if fallback else []):
            vals = []
            for r in q('SELECT "%s" FROM "%s" WHERE "%s" IS NOT NULL AND "%s"<>0 LIMIT 50'
                       % (c, t, c, c)):
                try:
                    vals.append(abs(float(r[0])))
                except (TypeError, ValueError, IndexError):
                    pass
            if not vals:
                continue
            if not declared and len({len("%d" % int(v)) for v in vals}) == 1:
                continue          # запасной разбор: постоянная длина в цифрах = код
            mx = max(vals)
            if mx > best:
                best, amount_col = mx, c
        if not declared and best <= 1:
            # Запасной разбор: без типов колонка 0/1 неотличима от флага. При типах
            # из метаданных отсечка не нужна и была бы вредна — в базе с мелкими
            # суммами (копейки, граммы) она выбросила бы настоящие деньги.
            amount_col = None
        if declared:
            dcols = [c for c, _dt in tcols if declared.get(c) == "Edm.DateTime"]
            # У документа дата документа объявлена платформой отдельным свойством.
            # «Первая по порядку» — неверно: в сотнях типов первой идёт дата
            # доверенности или дата начала, и «за декабрь» фильтровалось бы по ней.
            std_date = [c for c in STANDARD_DATE_PROPS if c in declared and c in dcols]
            date_cols = std_date or dcols or [c for c, dt in tcols
                                              if "TIMESTAMP" in dt or dt == "DATE"]
        else:
            date_cols = [c for c, dt in tcols if "TIMESTAMP" in dt or dt == "DATE"]
        date_col = date_cols[0] if date_cols else None

        txt_cols = []
        for c, dt in tcols:
            # В поиск идёт всё, что база объявила строкой (коды, номера, названия) —
            # даже если витрина сохранила это числом.
            if declared:
                if declared.get(c) != "Edm.String":
                    continue
            elif "VARCHAR" not in dt:
                continue
            if prof["distinct"].get(c, 0) < 2 and n != 1:
                continue
            smp = prof["samples"].get(c) or []
            if smp and sum(1 for v in smp if machine_token(v)) > len(smp) * 0.5:
                continue
            txt_cols.append(c)

        # Колонки-ссылки читаем отдельно от текстовых: первая — собственный ключ строки,
        # остальные резолвятся в наименования.
        all_cols = guid_cols + txt_cols
        # Объявленный ключ читаем отдельно: он бывает составным и не обязан быть Guid.
        key_extra = [c for c in key_props if c not in all_cols]
        extra = ([('"%s"' % amount_col)] if amount_col else []) + \
                ([('"%s"' % date_col)] if date_col else []) + \
                [('"%s"' % c) for c in key_extra]
        # Заглушки NULL быть не должно. Когда у сущности нет ни текстовых, ни ссылочных
        # колонок (обычное дело для регистров: только Period и число), пустой список
        # подменялся на «NULL», и ВСЕ значения сдвигались на позицию — число попадало в
        # колонку даты. Проверено: 7 регистров писали в дату «116.49», «912000», «16».
        # Собираем список выборки как есть и режем результат по его длине.
        sel_parts = [clip(c) for c in all_cols] + extra
        if not sel_parts:
            continue                            # нечего брать из этой сущности
        rows = q("SELECT %s FROM \"%s\"" % (", ".join(sel_parts), t))

        label = t.split("_", 1)[1] if "_" in t else t
        for r in rows:
            tv = r[:len(all_cols)] if all_cols else []
            rest = r[len(all_cols):]
            amt = dt_ = None
            i = 0
            if amount_col:
                try:
                    amt = float(rest[i])
                except (ValueError, IndexError, TypeError):
                    amt = None
                i += 1
            if date_col and i < len(rest):
                dt_ = rest[i] or None
                i += 1
            declared_key = None
            if key_props:
                vals = {}
                for c, v in zip(all_cols, tv):
                    if c in key_props:
                        vals[c] = v
                for c in key_extra:
                    if i < len(rest):
                        vals[c] = rest[i]
                        i += 1
                parts_k = [vals.get(c, "") for c in key_props]
                if any(parts_k):
                    declared_key = "|".join(parts_k)

            parts, key = [label], None
            for c, v in zip(all_cols, tv):
                if not v:
                    continue
                if c in guid_cols or GUID.match(v):
                    if key is None:
                        key = v
                        continue                    # собственный ключ в текст не пишем
                    nm = refmap.get(v)
                    if nm:
                        parts.append("%s: %s" % (c.replace("_Key", ""), nm))
                    continue
                if machine_token(v):
                    continue
                parts.append("%s: %s" % (c, v))
            # Подписи берём ИЗ БАЗЫ (имя колонки), а не придумываем слова: в англоязычной
            # или иной конфигурации русские «сумма»/«дата» были бы чужеродны.
            if amt is not None:
                parts.append("%s: %s" % (amount_col,
                                         "%d" % amt if amt == int(amt) else "%.2f" % amt))
            if dt_:
                parts.append("%s: %s" % (date_col, dt_[:10]))
            corpus.append((t, declared_key or key or "", " | ".join(parts), amt, dt_))
        yield t, corpus, len(live), len(refmap)


def _flush(buf, pending):
    conds = " OR ".join("(src_table=%s AND row_key=%s)" % (lit(s), lit(k)) for s, k in pending)
    if conds:
        ddl("DELETE FROM %s WHERE %s;" % (CORPUS, conds))
    ddl("INSERT INTO %s VALUES %s;" % (CORPUS, ",".join(buf)))


def _row_sql(item, vec):
    src, key, doc, h, amt, dtv = item
    return "(%s,%s,%s,%s,%s,%s,%s::FLOAT[%d])" % (
        lit(src), lit(key), lit(doc), lit(h),
        "NULL" if amt is None else repr(amt),
        "NULL" if not dtv else lit(dtv),
        "'[" + ",".join("%.6f" % x for x in vec) + "]'", EMBED_DIM)


def main():
    t0 = time.time()
    ddl("CREATE TABLE IF NOT EXISTS %s (src_table TEXT, row_key TEXT, doc TEXT, doc_hash TEXT, "
        "amount DOUBLE, doc_date TIMESTAMP, emb FLOAT[%d]);" % (CORPUS, EMBED_DIM))

    have = {}
    for src, key, h in q("SELECT src_table, row_key, doc_hash FROM %s" % CORPUS):
        have[(src, key)] = h

    # Обработка ПО ТАБЛИЦАМ (память не зависит от размера базы), но пул эмбеддинга —
    # ОДИН на весь прогон. Пул на таблицу сбрасывал параллельность на каждой мелкой
    # сущности: замерено 71 с против 29 с на том же корпусе.
    seen, total_rows, n_tables, n_ref, done, failed = set(), 0, 0, 0, 0, 0
    buf, pending, inflight = [], [], {}
    t1 = time.time()

    def harvest(fut):
        nonlocal buf, pending, done, failed
        items = inflight.pop(fut)
        try:
            vecs = fut.result()
        except Exception as e:                  # noqa: BLE001 — сеть/квота поставщика
            failed += 1
            sys.stderr.write("пачка эмбеддинга не посчитана: %s\n" % str(e)[:120])
            return
        for item, vec in zip(items, vecs):
            buf.append(_row_sql(item, vec))
            pending.append((item[0], item[1]))
        done += len(items)
        if len(buf) >= INS:
            _flush(buf, pending)
            buf, pending = [], []

    with cf.ThreadPoolExecutor(max_workers=PARALLEL) as pool:
        for t, rows, n_tables, n_ref in iter_corpus():
            total_rows += len(rows)
            todo = []
            for src, key, doc, amt, dtv in rows:
                h = hashlib.sha1(doc.encode("utf-8")).hexdigest()
                seen.add((src, key))
                if have.get((src, key)) != h:
                    todo.append((src, key, doc, h, amt, dtv))
            for i in range(0, len(todo), BATCH):
                ch = todo[i:i + BATCH]
                inflight[pool.submit(embed, [x[2] for x in ch])] = ch
                # Держим очередь ограниченной: иначе в память уедет весь корпус разом
                # и потоковая обработка потеряет смысл.
                while len(inflight) >= PARALLEL * 4:
                    for f in cf.wait(list(inflight), return_when=cf.FIRST_COMPLETED)[0]:
                        harvest(f)
                        if done % 500 < BATCH:
                            print("  эмбеддинги: %d (%.0f с)" % (done, time.time() - t1))
        while inflight:
            for f in cf.wait(list(inflight), return_when=cf.FIRST_COMPLETED)[0]:
                harvest(f)
    if buf:
        _flush(buf, pending)
    embed_sec = time.time() - t1

    if failed:
        # Частичный корпус + индекс от прошлого прогона = витрина отвечает по
        # рассогласованным данным и не сообщает об этом. Индекс пересобираем в любом
        # случае, но прогон помечаем проваленным.
        sys.stderr.write("ВНИМАНИЕ: %d пачек не посчитаны — корпус неполный\n" % failed)

    gone = [k for k in have if k not in seen]
    if gone:
        conds = " OR ".join("(src_table=%s AND row_key=%s)" % (lit(s), lit(k)) for s, k in gone)
        ddl("DELETE FROM %s WHERE %s;" % (CORPUS, conds))
    print("витрина: %d таблиц, %d строк | ссылок: %d | новых/изменённых: %d | удалено: %d"
          % (n_tables, total_rows, n_ref, done, len(gone)))

    try:
        ddl("CREATE TEXT SEARCH DICTIONARY %s (template='text', locale=%s, "
            "case='lower', stemming=false, accent=false, frequency=true, position=true, "
            "norm=true);" % (DICT, lit(DICT_LOCALE)))
    except RuntimeError:
        pass                                   # словарь уже создан прошлым прогоном

    t2 = time.time()
    ddl("DROP INDEX IF EXISTS %s;" % INDEX)
    # ВАЖНО: индекс — снимок. Пересобираем каждый прогон; на наших объёмах это <1 с.
    ddl("CREATE INDEX %s ON %s USING inverted(doc %s, emb ivf (metric='cosine')) "
        "INCLUDE (src_table, row_key, amount, doc_date);" % (INDEX, CORPUS, DICT))
    idx_sec = time.time() - t2

    # --- профиль таблиц: по нему выбирается, О ЧЁМ вопрос
    odata_types()                       # заполняет ENTITY_NAMES оригинальными именами
    meta_names = dict(ENTITY_NAMES)
    ddl("DROP TABLE IF EXISTS %s;" % TABLES)
    ddl("CREATE TABLE %s (src_table TEXT, label TEXT, emb FLOAT[%d]);" % (TABLES, EMBED_DIM))
    srcs = [r[0] for r in q("SELECT DISTINCT src_table FROM %s" % CORPUS)]
    labels = []
    for t in srcs:
        raw = t.split("_", 1)[1] if "_" in t else t
        orig = meta_names.get(t.lower(), raw)
        orig = orig.split("_", 1)[1] if "_" in orig else orig
        labels.append((t, split_camel(orig)))
    for i in range(0, len(labels), BATCH):
        part = labels[i:i + BATCH]
        vecs = embed([lb for _t, lb in part])
        vals = ",".join("(%s,%s,%s::FLOAT[%d])" % (
            lit(t), lit(lb), "'[" + ",".join("%.6f" % x for x in v) + "]'", EMBED_DIM)
            for (t, lb), v in zip(part, vecs))
        ddl("INSERT INTO %s VALUES %s;" % (TABLES, vals))
    print("профиль таблиц: %d" % len(labels))

    # Читающая роль сервиса ответов должна видеть корпус и индекс. Делаем это здесь,
    # чтобы на чистой установке ничего не нужно было раздавать руками.
    for role in [r[0] for r in q("SELECT usename FROM pg_user WHERE usename<>'postgres'")]:
        try:
            ddl("GRANT SELECT ON %s TO %s;" % (CORPUS, role))
            ddl("GRANT SELECT ON %s TO %s;" % (TABLES, role))
        except RuntimeError:
            pass

    total = int(q("SELECT count(*) FROM %s" % CORPUS)[0][0])
    if failed:
        print(json.dumps({"rows": total, "embedded": done, "failed_batches": failed,
                          "status": "неполный корпус"}, ensure_ascii=False))
        return 3
    print(json.dumps({"rows": total, "embedded": done, "deleted": len(gone),
                      "embed_sec": round(embed_sec, 1), "index_sec": round(idx_sec, 2),
                      "total_sec": round(time.time() - t0, 1)}, ensure_ascii=False))


if __name__ == "__main__":
    sys.exit(main())
