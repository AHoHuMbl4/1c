#!/usr/bin/env python3
"""
Штатный синк витрины SereneDB: выбранные сущности 1С (OData) -> таблицы SereneDB + пересборка
семантического индекса резолвера (resolver_index). Под RW (postgres). Конфиг-нейтрально —
список сущностей из serene-entities.txt (СОБСТВЕННЫЙ список serene рядом со скриптом, НЕ копия braine).

Сейчас — ПОЛНАЯ идемпотентная перезагрузка каждой таблицы (просто и надёжно). Инкремент по дате —
оптимизация позже (для больших документов). Запуск — systemd-таймер (ночью, после 1c-etl).

Env: SERENEDB_DSN (rw=postgres), ETL_ODATA_BASE, CSV_DIR, ALIBABA_* (для резолвера) — см. serene_report.
"""
import difflib
import json
import os
import sys
import time

# build_resolver_index больше не нужен: резолвер строит build.sh (см. main())
import odata_census as C
import subprocess
import poc_load_entity as L

# Список сущностей — СОБСТВЕННЫЙ у serene (версионируется в git, деплоится рядом со скриптом),
# НЕ копия braine: две копии разъезжаются. Все имена в нём заведомо из живого OData (+ преполёт
# сверяет каждый прогон). Переопределяется env SELECTED_FILE при необходимости.
SELECTED = os.environ.get(
    "SELECTED_FILE", os.path.join(os.path.dirname(os.path.abspath(__file__)), "serene-entities.txt")
)


def _core(name):
    """Ядро имени сущности без типа-префикса (Catalog_/Document_/…) — чтобы общий префикс не забивал
    сигнал сходства."""
    return name.split("_", 1)[1] if "_" in name else name


def _selectable(c):
    """Кандидат пригоден как БИЗНЕС-выбор: не табличная часть (в ядре нет '_', иначе это `X_Товары`)
    и не 1С-служебное (присоединённые файлы, помеченные на удаление). Это платформенные соглашения
    1С (общие для любой конфигурации), а не имена-константы — как исключение navigation-колонок в
    резолвере. Убирает мусор из подсказок (напр. `…ПрисоединенныеФайлы_УдалитьЭлектронныеПодписи`)."""
    core = _core(c)
    if "_" in core:
        return False
    low = core.lower()
    return "присоединенныефайлы" not in low and not low.startswith("удалить")


def _suggest(name, published, k=3):
    """Ближайшие РЕАЛЬНЫЕ имена для мёртвого (слой 2). Сравниваем по ядру; метрика — длина наибольшего
    общего фрагмента (устойчивее ratio: не штрафует длину, длинное верное не проигрывает короткому
    чужому), ratio — тай-брейк. В пределах того же типа (каталог ищем среди каталогов), только среди
    пригодных для выбора (без служебных/табличных — см. `_selectable`).
    ВАЖНО про неоднозначность: если несколько кандидатов равно-близки (одинаковая длина общего
    фрагмента, напр. десятки «Договор…») — возвращаем НЕСКОЛЬКО, а не один наугад: выбор за человеком.
    Слабое совпадение → пусто (не вводим в заблуждение). Без имён-констант."""
    pref = name.split("_", 1)[0] if "_" in name else ""
    cq = _core(name)
    same = [c for c in published if c.startswith(pref + "_") and _selectable(c)] or list(published)
    scored = []
    for c in same:
        cc = _core(c)
        sm = difflib.SequenceMatcher(None, cq, cc)
        scored.append((sm.find_longest_match(0, len(cq), 0, len(cc)).size, round(sm.ratio(), 3), c))
    scored = [s for s in scored if s[0] >= max(4, len(cq) // 3)]  # отсечь слабое
    if not scored:
        return []
    scored.sort(reverse=True)
    top = scored[0][0]  # лучшая длина общего фрагмента
    band = [c for sz, _r, c in scored if sz == top]  # все равно-близкие по главной метрике
    return band[:k]


def _preflight(ents):
    """Защита от рассинхрона выбора с реальностью (слои 1+2), БЕЗ хардкода имён.
    Слой 1 — сверяем ВЕСЬ выбор с ЖИВЫМ OData (источник правды): несуществующее имя → громко,
    а не молчаливый 404 в логе. Слой 2 — для мёртвого имени подсказываем ближайшее реальное
    (не подменяем молча, а показываем). Возвращает список невалидных имён (для итога и кода выхода)."""
    published = L.published_entity_sets()
    if not published:
        print("  ⚠ преполёт пропущен: не удалось получить список сущностей OData (не поднимаю ложную тревогу)")
        return []
    missing = [e for e in ents if e not in published]
    if missing:
        print(f"  ⚠ ВНИМАНИЕ: {len(missing)} выбранных сущностей НЕ опубликованы в OData этой базы:")
        for m in missing:
            near = _suggest(m, published)
            hint = " | ".join(near) + (" …" if len(near) == 3 else "") if near else "— (похожего нет)"
            print(f"     ✗ {m}  →  похоже на: {hint}")
        print("     имена не выдумывать; при неоднозначности выбрать нужное из показанных — по живому OData")
    return missing


def save_profile(rows):
    """Профиль базы в витрину: что нашли, что взяли, чего не видим из-за прав.

    Раньше закрытая правами сущность и пустая выглядели одинаково — обе просто
    исчезали, и клиент не знал, что часть его данных системе недоступна. Молчать об
    этом нельзя: он вправе знать, о чём бот принципиально не сможет ответить.
    """
    dsn = os.environ.get("SERENEDB_DSN", "host=127.0.0.1 port=7890 user=postgres dbname=postgres")

    def run(sql):
        subprocess.run(["psql", dsn, "-v", "ON_ERROR_STOP=1", "-f", "-"],
                       input=sql, capture_output=True, text=True)

    def lit(v):
        return "'" + str(v).replace("'", "''") + "'"

    run("DROP TABLE IF EXISTS base_profile;")
    run("CREATE TABLE base_profile (entity TEXT, rows BIGINT, problem TEXT, key_props TEXT);")
    vals = []
    for r in rows:
        vals.append("(%s,%d,%s,%s)" % (lit(r["entity"]), r["rows"],
                                       lit(r["problem"]), lit(",".join(r["key"]))))
        if len(vals) >= 200:
            run("INSERT INTO base_profile VALUES " + ",".join(vals) + ";")
            vals = []
    if vals:
        run("INSERT INTO base_profile VALUES " + ",".join(vals) + ";")
    for role in ("serene_ro", "serene_resolver"):
        run("GRANT SELECT ON base_profile TO %s;" % role)


def _profile_age():
    """Возраст base_profile в секундах, или большое число, если её нет/пуста.
    По нему решаем, пора ли переписывать СХЕМУ заново."""
    dsn = os.environ.get("SERENEDB_DSN", "host=127.0.0.1 port=7890 user=postgres dbname=postgres")
    p = subprocess.run(["psql", dsn, "-tA", "-c",
                        "SELECT coalesce(epoch(now()-max(seen)),1e9) FROM base_profile_meta"],
                       capture_output=True, text=True)
    try:
        return float(p.stdout.strip())
    except ValueError:
        return 1e9


def _service_skip(ents):
    """Что не грузим вовсе и почему. Возвращает {сущность: причина}.

    Решение владельца 06.08: служебные источники из загрузки убрать. `[замер 05.08]` они
    стоили 379 с каждого такта на 712 источниках — телеметрия платформы (замеры времени,
    204 тыс. строк пятью источниками), права доступа, статистика, лента новостей
    платформы, обмены, версии объектов. Для ответа о бизнесе там нет ничего.

    🔴 ТРЕБОВАНИЕ ВЛАДЕЛЬЦА — НАДЁЖНАЯ МЕТКА НА ЛЮБОЙ БАЗЕ. Структурного признака, который
    сам по себе отделял бы служебное, в 1С нет, и это замерено, а не предположено: у 129
    служебных источников (216 с) человеческий текст есть, а у 57 деловых его нет. Поэтому
    признаков три, и они разной природы:

      1. `only_binary` — объективный, из `$metadata`, ничьего суждения не требует;
      2. разметка `search_entity_class = 'service'` — смысловая, её кладёт модель один раз
         на сущность и хранит в базе; та же, по которой владелец 29.07 отменил векторы
         служебным;
      3. `search_entity_force` — слово владельца, перебивает оба: строка `skip` убирает
         источник, строка `load` возвращает его, что бы ни решили первые два.

    Осторожность в одну сторону: неразмеченное грузится. Ошибка «не загрузили нужное»
    видна числом (таблица `search_entity_skipped` и строка в журнале) и лечится одной
    строкой в `search_entity_force` — без правки кода и на любой базе.
    """
    if os.environ.get("SYNC_SKIP_SERVICE", "1") != "1":
        return {}
    dsn = os.environ.get("SERENEDB_DSN", "host=127.0.0.1 port=7890 user=postgres dbname=postgres")

    def rows(sql):
        p = subprocess.run(["psql", dsn, "-tA", "-F", "\t", "-c", sql],
                           capture_output=True, text=True)
        return [l.split("\t") for l in p.stdout.splitlines() if l] if p.returncode == 0 else []

    subprocess.run(["psql", dsn, "-q", "-c",
                    "CREATE TABLE IF NOT EXISTS search_entity_force "
                    "(src_table VARCHAR, mode VARCHAR, why VARCHAR)"],
                   capture_output=True, text=True)
    cls = {r[0]: r[1] for r in rows("SELECT src_table, cls FROM search_entity_class") if len(r) > 1}
    force = {r[0]: r[1] for r in rows("SELECT src_table, mode FROM search_entity_force") if len(r) > 1}

    skip = {}
    for es in ents:
        t = L.safe_col(es).lower()
        m = (force.get(t) or "").strip().lower()
        if m == "load":
            continue                            # слово владельца сильнее любого признака
        if m == "skip":
            skip[es] = "решение владельца (search_entity_force)"
        elif cls.get(t) == "service":
            skip[es] = "размечено служебным (search_entity_class)"
        elif L.only_binary(es):
            skip[es] = "всё содержимое двоичное, текста нет ($metadata)"
    return skip


def _profile_rows():
    """Прошлая перепись из витрины: {сущность: (строк, беда)}.

    Нужна, чтобы не спрашивать `$count` у тех, кого мы и так грузим: их число вернёт сама
    загрузка. Разделитель взят табуляцией — в именах сущностей 1С её не бывает, а вот
    вертикальная черта и запятая встречаются в тексте беды.
    """
    dsn = os.environ.get("SERENEDB_DSN", "host=127.0.0.1 port=7890 user=postgres dbname=postgres")
    p = subprocess.run(["psql", dsn, "-tA", "-F", "\t", "-c",
                        "SELECT entity, rows, coalesce(problem,'') FROM base_profile"],
                       capture_output=True, text=True)
    out = {}
    if p.returncode != 0:
        return out                              # переписи ещё не было — спросим всех
    for line in p.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        try:
            out[parts[0]] = (int(parts[1]), parts[2])
        except ValueError:
            continue
    return out


def _cached_entities():
    """Список непустых сущностей из base_profile — БЕЗ повторной переписи."""
    dsn = os.environ.get("SERENEDB_DSN", "host=127.0.0.1 port=7890 user=postgres dbname=postgres")
    p = subprocess.run(["psql", dsn, "-tA", "-c", "SELECT entity FROM base_profile WHERE rows>0"],
                       capture_output=True, text=True)
    return [e for e in p.stdout.splitlines() if e.strip()]


def main():
    # 🔴 ПЕРЕПИСЬ СХЕМЫ — ПЕРИОДИЧЕСКИ, ДАННЫЕ — КАЖДЫЙ ТАКТ. Перепись `C.census()` дёргает
    # `$count` у ВСЕХ 4585 типов 1С — [замер 28.07] это ~10 минут и почти всё время такта.
    # Но перепись про СХЕМУ (какие сущности есть, где нет прав), а она меняется на
    # КОНФИГУРАЦИИ 1С, не на данных. Данные же тянет дельта на каждом такте. Поэтому полная
    # перепись — раз в `CENSUS_MAX_AGE` (по умолчанию час), а между — берём список сущностей
    # из base_profile и сразу идём в дельту. Это не ограничение свежести ДАННЫХ (они
    # каждый такт), а лишь темп обнаружения НОВЫХ сущностей — событие редкое.
    dsn = os.environ.get("SERENEDB_DSN", "host=127.0.0.1 port=7890 user=postgres dbname=postgres")
    max_age = int(os.environ.get("CENSUS_MAX_AGE", "3600"))
    if _profile_age() > max_age:
        # 🔴 `$COUNT` НЕ СПРАШИВАЕТСЯ У ТЕХ, КОГО МЫ И ТАК ГРУЗИМ. Их число вернёт сама
        # загрузка — а перепись спрашивала его вторым заходом, то есть делала работу
        # дважды. [замер 05.08] перепись занимает ~815 с внутри такта свежести при норме
        # такта 20 минут (п. 17), и непустых среди 2795 типов — 1589, то есть больше
        # половины запросов были лишними.
        #
        # Спрашиваем ровно тех, про кого иначе не узнаем: новые типы, пустые в прошлый раз
        # и закрытые правами. Для известных непустых число берётся из прошлой переписи и
        # ниже, после загрузки, переписывается ФАКТИЧЕСКИМ — так профиль становится даже
        # свежее, чем был: раньше он обновлялся раз в час, теперь каждый такт.
        #
        # ⚠ Цена: если известная непустая сущность вдруг закроется правами, перепись этого
        # сама не заметит — заметит загрузка, и скажет ошибкой в журнал и в перепись
        # полноты. Молчания не возникает, поэтому цена принята.
        print("перепись схемы…")
        t_census = time.time()
        prev = _profile_rows()
        all_sets = set(C.entity_sets())
        meta = C.metadata()
        known = {e for e, r in prev.items() if r[0] > 0 and e in all_sets}
        ask = [e for e in sorted(all_sets) if e not in known]
        rows = C.census(sets=ask, meta=meta)
        rows += [{"entity": e, "rows": prev[e][0], "problem": prev[e][1],
                  "key": (meta.get(e, {}).get("key") or []),
                  "props": len(meta.get(e, {}).get("props") or {})}
                 for e in sorted(known)]
        print("  перепись: спрошено %d из %d типов (у %d непустых число даст сама загрузка), %.0f с"
              % (len(ask), len(all_sets), len(known), time.time() - t_census))
        s = C.summary(rows)
        print("  " + json.dumps(s, ensure_ascii=False))
        save_profile(rows)
        subprocess.run(["psql", dsn, "-v", "ON_ERROR_STOP=1", "-c",
                        "CREATE TABLE IF NOT EXISTS base_profile_meta(seen TIMESTAMP); "
                        "DELETE FROM base_profile_meta; INSERT INTO base_profile_meta VALUES (now());"],
                       capture_output=True, text=True)
        ents = C.to_load(rows)
        if s["закрыто_правами"]:
            print("  ⚠ закрыто правами читателя: %d сущностей — бот о них ответить не сможет"
                  % s["закрыто_правами"])
    else:
        ents = _cached_entities()
        print("перепись свежая (%.0f с) — беру %d сущностей из base_profile, сразу дельта"
              % (_profile_age(), len(ents)))

    # 🔴 ПОРЯДОК ОБХОДА ЗАДАЁТСЯ ЯВНО. От него зависит пропуск табличных частей: владелец
    # (`Document_X`) обязан быть обработан раньше своей части (`Document_X_Товары`), иначе
    # вывод «владелец не менялся» просто не успеет сложиться. По алфавиту это так всегда —
    # имя части начинается с имени владельца. Само по себе это не выполнялось: список
    # приходит то из переписи, то из витрины (`base_profile`), и во втором случае порядок
    # какой отдала база. Опираться на удачу тут нельзя — сортируем.
    ents = sorted(ents)

    limit = int(os.environ.get("SYNC_MAX_ENTITIES", "0"))
    if limit:
        ents = sorted(ents, key=lambda e: -next(r["rows"] for r in rows if r["entity"] == e))[:limit]
        print("  ограничение SYNC_MAX_ENTITIES=%d: грузим %d крупнейших" % (limit, len(ents)))

    # 🔴 СНАЧАЛА ДЕЛЬТА, ПОТОМ ПОЛНАЯ. Для сущности с уникальным Ref_Key тянем из 1С
    # только изменившиеся записи (по `DataVersion`), а не всю таблицу — иначе каждый такт
    # это трафик и повторный эмбеддинг (указание владельца 28.07). Дельта неприменима
    # (табличная часть, регистр, первая загрузка) → `load_entity_delta` вернёт None, и
    # грузим полностью. Итог считаем по фактически затронутым строкам, чтобы было видно,
    # СКОЛЬКО работы такт реально сделал.
    # 🔴 ЧТО НЕ ГРУЗИМ ВОВСЕ — РЕШАЕТСЯ ДО ЦИКЛА И ЗАПИСЫВАЕТСЯ В БАЗУ. Молчаливого
    # отсутствия быть не должно: исключённое лежит в `search_entity_skipped` с причиной по
    # каждому источнику, а в журнал идёт сводка. Это и есть то, чем «убрали служебное»
    # отличается от «источник потерялся» (п. 13).
    service_skip = _service_skip(ents)
    if service_skip:
        vals = ",".join("(%s,%s)" % ("'" + e.replace("'", "''") + "'",
                                     "'" + w.replace("'", "''") + "'")
                        for e, w in sorted(service_skip.items()))
        try:
            subprocess.run(["psql", dsn, "-q", "-v", "ON_ERROR_STOP=1", "-f", "-"],
                           input="CREATE TABLE IF NOT EXISTS search_entity_skipped "
                                 "(entity VARCHAR, why VARCHAR, seen_at TIMESTAMP);\n"
                                 "DELETE FROM search_entity_skipped;\n"
                                 "INSERT INTO search_entity_skipped "
                                 "SELECT e, w, now() FROM (VALUES %s) AS s(e, w);" % vals,
                           capture_output=True, text=True, check=True)
        except Exception as e:                  # noqa: BLE001
            # Перечень не записался — значит исключённое стало невидимым, а это ровно то,
            # чего быть не должно. Говорим вслух.
            print("⚠ перечень неисключаемых источников не записан: %s" % str(e)[:120])
        by_why = {}
        for w in service_skip.values():
            by_why[w] = by_why.get(w, 0) + 1
        print("не грузим %d источников (перечень с причинами — search_entity_skipped): %s"
              % (len(service_skip),
                 "; ".join("%s — %d" % (w, n) for w, n in sorted(by_why.items()))))

    ok = empty = err = touched = unchanged = skipped_owner = skipped_service = 0
    seen_rows = {}                              # фактическое число строк по каждой сущности
    # 🔴 ЧЕЙ ВЛАДЕЛЕЦ НЕ МЕНЯЛСЯ, ТОТ И САМ НЕ МЕНЯЛСЯ. У табличной части своей версии нет,
    # поэтому она читалась целиком каждый такт: [замер 05.08] 272 источника, 472 с, из них
    # 313 с — одна `Document_ПланПродаж_Товары`. Но её строки принадлежат документу, и
    # если у документа за этот такт не изменилось и не пропало НИ ОДНОГО объекта, то и
    # строк его табличной части измениться не могло.
    #
    # Хранить для этого ничего не нужно: вывод делается внутри одного такта, а сущности
    # идут по алфавиту, поэтому владелец (`Document_X`) всегда обрабатывается раньше своей
    # части (`Document_X_Товары`).
    #
    # Осторожность в одну сторону: в множество попадают только те, про кого мы ЗНАЕМ, что
    # изменений нет. Загрузка с ошибкой, полная загрузка с изменениями, отсутствие
    # владельца в списке — всё это оставляет часть на обычной полной загрузке.
    quiet = set()
    for es in ents:
        try:
            if es in service_skip:
                skipped_service += 1
                continue                        # причина уже записана в search_entity_skipped
            owner = L.owner_of(es)
            if owner and owner in quiet:
                # Витрина не трогается: у владельца за этот такт не изменилось ничего.
                # Число строк в профиле остаётся прежним — оно и есть верное.
                skipped_owner += 1
                unchanged += 1
                quiet.add(es)                   # части этой части (если есть) тоже тихи
                print("  %s: не читаем — владелец %s не менялся" % (es, owner))
                continue
            r = L.load_entity_delta(es)
            full = r is None
            if full:
                r = L.load_entity(es)
            # Фактическое число строк знает тот, кто загрузил, — оно и уедет в профиль
            # вместо `$count`, которого перепись у этих сущностей больше не спрашивает.
            seen_rows[es] = r.get("rows", 0)
            if full:
                if r["rows"] == 0:
                    empty += 1
                else:
                    ok += 1
                    # 🔴 ПОЛНАЯ ЗАГРУЗКА СЧИТАЕТСЯ ИЗМЕНЕНИЕМ, ТОЛЬКО ЕСЛИ СОДЕРЖИМОЕ
                    # ДРУГОЕ. Прежде здесь стояло `touched += r["rows"]` безусловно — с
                    # оговоркой «знать, совпало ли содержимое, мы дешёвым способом не
                    # можем». Способ нашёлся, и он штатный: сравнение делает движок одним
                    # запросом (`EXCEPT ALL` в обе стороны, `poc_load_entity.load_entity`).
                    # [замер 05.08] пока сравнения не было, строка «изменённых строк
                    # 732475» повторялась ДОСЛОВНО четырнадцать тактов подряд за двое
                    # суток при полном отсутствии изменений в 1С — и каждый такт заново
                    # пересобирался корпус (780 с).
                    #
                    # Обратная ошибка (не заметить изменение) невозможна по построению:
                    # любая осечка сравнения означает «изменилось», а не «совпало».
                    # 🔴 СТРОКА ПЕЧАТАЕТСЯ ВСЕГДА, И ВЕРДИКТ В НЕЙ — ТОЖЕ. Первая попытка
                    # печатать только изменившиеся вышла боком: из журнала пропали времена
                    # по каждому источнику, а именно по ним видно, куда уходит такт, и
                    # именно они дали все находки этого дня. Тишина вместо строки — это и
                    # «источник не менялся», и «источник забыли», неотличимо (п. 13).
                    changed = r.get("changed", r["rows"])
                    touched += changed
                    if not changed:
                        unchanged += 1
                        quiet.add(es)           # его части читать незачем
                    print("  %s: %s строк -> %s (полная, %ss%s)"
                          % (es, r["rows"], r["table"], r["sec"],
                             "" if changed else ", без изменений"))
            else:
                ok += 1
                if r.get("changed") or r.get("gone"):
                    touched += r.get("changed", 0) + r.get("gone", 0)
                    print(f"  {es}: дельта +{r.get('changed',0)}/-{r.get('gone',0)} "
                          f"({r['sec']}s)")
                else:
                    quiet.add(es)               # его части читать незачем
        except Exception as e:  # noqa: BLE001 — одна сущность не должна валить весь синк
            err += 1
            print(f"  {es}: ОШИБКА {e}")
    # 🔴 «Прочитали, но содержимое то же» — отдельным числом, а не молчанием. Иначе
    # неотличимо «источник не менялся» от «источник забыли», а это и есть та самая
    # молчаливая потеря свежести, из-за которой п. 17 не выполнялся (п. 13).
    print(f"витрина: сущностей {ok}, пусто {empty}, ошибок {err}; "
          f"изменённых строк {touched}; источников без изменений {unchanged} "
          f"(из них не читали вовсе, потому что не менялся владелец: {skipped_owner}); "
          f"не грузим по решению: {skipped_service}")

    # 🔴 ФАКТИЧЕСКОЕ ЧИСЛО СТРОК — В ПРОФИЛЬ, КАЖДЫЙ ТАКТ. Перепись больше не спрашивает
    # `$count` у тех, кого мы грузим, поэтому число обязан вернуть тот, кто их загрузил.
    # Профиль от этого не беднеет, а свежеет: раньше он обновлялся раз в час переписью,
    # теперь — каждый такт по факту. Читает его перепись полноты (п. 13), и врать ей
    # нельзя.
    if seen_rows:
        vals = ",".join("(%s,%d)" % ("'" + e.replace("'", "''") + "'", n)
                        for e, n in seen_rows.items())
        try:
            subprocess.run(["psql", dsn, "-q", "-v", "ON_ERROR_STOP=1", "-f", "-"],
                           input="UPDATE base_profile SET rows = v.n FROM (VALUES %s) "
                                 "AS v(e, n) WHERE base_profile.entity = v.e;" % vals,
                           capture_output=True, text=True, check=True)
        except Exception as e:                  # noqa: BLE001
            print(f"⚠ не удалось обновить число строк в профиле: {str(e)[:120]}")

    # 🔴 ОТМЕТКА «ВИТРИНА МЕНЯЛАСЬ» — ДЛЯ СБОРКИ. Только синк знает, тронул ли он данные:
    # у движка отметки времени изменения таблицы нет, а `search_sources.seen_at` пишется
    # лишь при ПЕРВОМ появлении источника и для этого не годится.
    # [замер 29.07] пока сборка сверялась с `seen_at`, она после первого успешного такта
    # пропускала пересборку НАВСЕГДА: данные из 1С попадали в витрину и не доходили до
    # поиска. Молчаливая потеря свежести (п. 17).
    # Ставим отметку и при ошибках: часть данных могла загрузиться, и корпус обязан их
    # увидеть. Ставим и при `touched == 0`? Нет — тогда пропуск не сработает никогда;
    # но если ошибка была, признак недостоверен, и мы намеренно просим пересборку.
    if touched or err:
        try:
            subprocess.run(["psql", dsn, "-q", "-v", "ON_ERROR_STOP=1", "-f", "-"],
                           input="DELETE FROM search_quality WHERE k='mart_changed_ts';\n"
                                 "INSERT INTO search_quality VALUES "
                                 "('mart_changed_ts', epoch(now())::BIGINT, "
                                 "'витрина менялась: сборка обязана пересобрать корпус');",
                           capture_output=True, text=True, check=True)
        except Exception as e:                  # noqa: BLE001
            # Не смогли поставить отметку — это НЕ повод продолжать молча: без неё сборка
            # решит, что менять нечего. Говорим явно, такт увидит в журнале.
            print(f"⚠ не удалось записать отметку об изменении витрины: {str(e)[:120]}")

    # 🔴 РЕЗОЛВЕР ЗДЕСЬ БОЛЬШЕ НЕ СТРОИТСЯ. Прежде синк вызывал `build_resolver_index`
    # (питон), а тот пересобирал резолвер ЦЕЛИКОМ — [замер 27.07] 7 ч 34 мин. Теперь
    # резолвер строит `build.sh` штатными средствами движка, инкрементально (векторы
    # только новым значениям). Синк отвечает ТОЛЬКО за витрину (1С → таблицы); корпус,
    # индекс, резолвер и векторы — за `build.sh`. Разделение слоёв, п. 20.

    # Ошибки загрузки не глотаем: прогон помечается проваленным, systemd покажет failed.
    if err:
        print(f"⚠ ИТОГ: {err} сущностей не загрузились")
        sys.exit(3)


if __name__ == "__main__":
    main()
