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


def _preflight(ents):
    """Защита от рассинхрона выбора с реальностью (слои 1+2), БЕЗ хардкода имён.
    Слой 1 — сверяем ВЕСЬ выбор с ЖИВЫМ OData (источник правды): несуществующее имя → громко,
    а не молчаливый 404 в логе. Слой 2 — для мёртвого имени подсказываем ближайшее реальное
    (лексический fuzzy — тот же принцип, что в резолвере; не подменяем молча, а показываем).
    Возвращает список невалидных имён (для итога и кода выхода)."""
    published = L.published_entity_sets()
    if not published:
        print("  ⚠ преполёт пропущен: не удалось получить список сущностей OData (не поднимаю ложную тревогу)")
        return []
    missing = [e for e in ents if e not in published]
    if missing:
        print(f"  ⚠ ВНИМАНИЕ: {len(missing)} выбранных сущностей НЕ опубликованы в OData этой базы:")
        for m in missing:
            near = difflib.get_close_matches(m, published, n=1, cutoff=0.6)
            print(f"     ✗ {m}  →  ближайшее реальное: {near[0] if near else '— (похожего нет)'}")
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
