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
import os
import sys

import build_resolver_index as R
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


def main():
    if not os.path.exists(SELECTED):
        sys.exit(f"нет файла выбора сущностей: {SELECTED}")
    ents = [ln.strip() for ln in open(SELECTED, encoding="utf-8") if ln.strip() and not ln.lstrip().startswith("#")]

    missing = _preflight(ents)  # слой 1+2: валидация выбора против живого OData
    to_load = [e for e in ents if e not in set(missing)]  # заведомо-невалидные не грузим (это 404)

    ok = empty = err = 0
    for es in to_load:
        try:
            r = L.load_entity(es)
            if r["rows"] == 0:
                empty += 1
                print(f"  {es}: пусто")
            else:
                ok += 1
                print(f"  {es}: {r['rows']} строк -> {r['table']} ({r['sec']}s)")
        except Exception as e:  # noqa: BLE001 — одна сущность не должна валить весь синк
            err += 1
            print(f"  {es}: ОШИБКА {e}")
    skipped = len(ents) - len(to_load)
    print(f"витрина: загружено {ok}, пусто {empty}, ошибок {err}, пропущено-невалидных {skipped} из {len(ents)}")

    # пересборка семантического индекса резолвера (Qwen text-embedding-v4 @ 1536) — по свежим
    # значениям колонок-измерений всех загруженных таблиц
    try:
        R.main()
    except SystemExit as e:
        print(f"resolver_index: {e}")
    except Exception as e:  # noqa: BLE001
        print(f"resolver_index: ошибка пересборки {e}")

    # Слой 1: невалидные имена НЕ глотаем молча. Валидные данные уже загружены выше, но прогон
    # помечаем как проваленный (ненулевой код) — systemd покажет unit failed, и это точно не упустить.
    if missing:
        print(f"⚠ ИТОГ: {len(missing)} невалидных имён в списке выбора — см. преполёт выше. Чинить у источника.")
        sys.exit(3)


if __name__ == "__main__":
    main()
