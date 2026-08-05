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
        print("перепись схемы…")
        rows = C.census()
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
    ok = empty = err = touched = unchanged = 0
    for es in ents:
        try:
            r = L.load_entity_delta(es)
            if r is None:
                r = L.load_entity(es)
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
                    changed = r.get("changed", r["rows"])
                    touched += changed
                    if changed:
                        print(f"  {es}: {r['rows']} строк -> {r['table']} (полная, {r['sec']}s)")
                    else:
                        unchanged += 1
            else:
                ok += 1
                if r.get("changed") or r.get("gone"):
                    touched += r.get("changed", 0) + r.get("gone", 0)
                    print(f"  {es}: дельта +{r.get('changed',0)}/-{r.get('gone',0)} "
                          f"({r['sec']}s)")
        except Exception as e:  # noqa: BLE001 — одна сущность не должна валить весь синк
            err += 1
            print(f"  {es}: ОШИБКА {e}")
    # 🔴 «Прочитали, но содержимое то же» — отдельным числом, а не молчанием. Иначе
    # неотличимо «источник не менялся» от «источник забыли», а это и есть та самая
    # молчаливая потеря свежести, из-за которой п. 17 не выполнялся (п. 13).
    print(f"витрина: сущностей {ok}, пусто {empty}, ошибок {err}; "
          f"изменённых строк {touched}; источников без изменений {unchanged}")

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
