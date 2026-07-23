#!/usr/bin/env python3
"""
Штатный синк витрины SereneDB: выбранные сущности 1С (OData) -> таблицы SereneDB + пересборка
семантического индекса резолвера (resolver_index). Под RW (postgres). Конфиг-нейтрально —
список сущностей из /etc/1c-etl-selected.txt (те же галочки, что и ETL braine).

Сейчас — ПОЛНАЯ идемпотентная перезагрузка каждой таблицы (просто и надёжно). Инкремент по дате —
оптимизация позже (для больших документов). Запуск — systemd-таймер (ночью, после 1c-etl).

Env: SERENEDB_DSN (rw=postgres), ETL_ODATA_BASE, CSV_DIR, ALIBABA_* (для резолвера) — см. serene_report.
"""
import difflib
import os
import sys

import build_resolver_index as R
import poc_load_entity as L
import rebuild_banks as RB

SELECTED = os.environ.get("SELECTED_FILE", "/etc/1c-etl-selected.txt")


def _core(name):
    """Ядро имени сущности без типа-префикса (Catalog_/Document_/…) — чтобы общий префикс не забивал
    сигнал сходства."""
    return name.split("_", 1)[1] if "_" in name else name


def _suggest(name, published):
    """Ближайшее РЕАЛЬНОЕ имя для мёртвого (слой 2). Сравниваем по ядру и по длине наибольшего общего
    фрагмента (устойчивее ratio: не штрафует длину — длинное верное не проигрывает короткому чужому),
    в пределах того же типа (каталог ищем среди каталогов). Слабое совпадение → молчим, чтобы не
    вводить в заблуждение. Тот же лексический принцип, что в резолвере; без имён-констант."""
    pref = name.split("_", 1)[0] if "_" in name else ""
    cq = _core(name)
    same = [c for c in published if c.startswith(pref + "_")] or list(published)
    best, best_key = None, (0, 0.0)
    for c in same:
        cc = _core(c)
        sm = difflib.SequenceMatcher(None, cq, cc)
        key = (sm.find_longest_match(0, len(cq), 0, len(cc)).size, sm.ratio())
        if key > best_key:
            best, best_key = c, key
    return best if best_key[0] >= max(4, len(cq) // 3) else None


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
            print(f"     ✗ {m}  →  ближайшее реальное: {near or '— (похожего нет)'}")
        print("     имена не выдумывать — чинить по живому OData у источника выбора")
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

    # Справочная витрина-проекция `banks` (БИК-классификатор) — вне списка сущностей (это ПРОЕКЦИЯ
    # значимых полей на англ. схему, а не сырьё), поэтому обновляем отдельным шагом тем же стабильным
    # конвейером. Иначе banks обновлялся бы только вручную и со временем расходился бы с 1С.
    try:
        RB.main()
    except Exception as e:  # noqa: BLE001 — не должна валить синк
        print(f"  banks: ОШИБКА пересборки {e}")

    # пересборка семантического индекса резолвера (Qwen text-embedding-v4 @ 1536) — ПОСЛЕ banks,
    # чтобы индекс увидел свежие города справочника
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
