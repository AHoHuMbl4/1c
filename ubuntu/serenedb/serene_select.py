#!/usr/bin/env python3
"""ВЫВЕДЕН ИЗ КОНТУРА 28.07.2026. Не запускать, не импортировать.

Файл делал «дискавери и ручной отбор бизнес-сущностей» — шаг, которого больше нет:
состав витрины определяет ПЕРЕПИСЬ базы, а не человек (`serene_sync.py`, «берём всё
непустое и доступное»). Ручной отбор был главным ручным шагом установки и прямым
нарушением п. 14 TARGET.md.

Почему не просто «не используется», а выведен: его правило отбора содержало ХАРДКОД —
русские подстроки «присоединенныефайлы» и «удалить» — при том что комментарий рядом
уверял «структурно, без списка имён». На конфигурации 1С с другим языком интерфейса эти
слова другие, и отбор молча выбросил бы не то. Документ, который уверенно врёт о коде,
опаснее отсутствующего (`HOW_NOT_TO §4.6`).

Ни один рабочий файл его не импортирует; ссылка из `setup.sh` убрана.
"""

import concurrent.futures
import json
import os
import sys
import urllib.parse
import urllib.request

import poc_load_entity as L

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


OUT = os.environ.get("SELECTED_FILE",
                     os.path.join(os.path.dirname(os.path.abspath(__file__)), "serene-entities.txt"))


def _is_business_toplevel(name):
    """Бизнес-объект верхнего уровня: Catalog_/Document_, без табличной части (X_Y), не системный.
    Структурно, без списка имён — платформенные соглашения 1С."""
    if not (name.startswith("Catalog_") or name.startswith("Document_")):
        return False
    core = name.split("_", 1)[1]
    if "_" in core:  # табличная часть (Document_X_Товары / Catalog_X_ДопРеквизиты)
        return False
    low = core.lower()
    return "присоединенныефайлы" not in low and not low.startswith("удалить")


def _count(es):
    try:
        u = L.ODATA + "/" + urllib.parse.quote(es) + "?" + urllib.parse.urlencode(
            {"$format": "json", "$top": "1", "$inlinecount": "allpages"})
        d = json.load(urllib.request.urlopen(_odata_auth(u), timeout=60))
        c = d.get("odata.count")
        return es, (int(c) if c is not None else len(d.get("value", [])))
    except Exception:  # noqa: BLE001
        return es, -1


def main():
    args = sys.argv[1:]
    review = "--review" in args  # Фаза 2.2 picker: кандидаты закомментированы, владелец отбирает
    nums = [a for a in args if a.isdigit()]
    min_rows = int(nums[0]) if nums else 1
    pub = L.published_entity_sets()
    if not pub:
        sys.exit("не получил список сущностей OData")
    cands = sorted(n for n in pub if _is_business_toplevel(n))
    print(f"бизнес-сущностей верхнего уровня: {len(cands)}; считаю непустые (порог {min_rows})…")
    keep = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as ex:
        for es, n in ex.map(_count, cands):
            if isinstance(n, int) and n >= min_rows:
                keep.append((es, n))
    if review:
        # PICKER: все кандидаты ЗАКОММЕНТИРОВАНЫ, по убыванию count. Владелец раскомментирует нужные
        # (авто-дискавери тащит и платформенные справочники — метаданные/НДФЛ/варианты отчётов — их отсеять
        # алгоритмически без хардкода нельзя, потому решает человек). Отобранное → serene-entities.txt.
        keep.sort(key=lambda x: (-x[1], x[0]))
        rf = OUT + ".review"
        with open(rf, "w", encoding="utf-8") as f:
            f.write("# PICKER (serene_select --review): НЕПУСТЫЕ бизнес-сущности из ЖИВОГО OData, по убыванию строк.\n")
            f.write("# Раскомментируй нужные БИЗНЕС-сущности (аналитику), сохрани отобранное как serene-entities.txt.\n")
            f.write("# Имена — из реальности; преполёт сверяет каждый прогон синка.\n\n")
            for es, n in keep:
                f.write(f"# {es}\t({n})\n")
        print(f"picker: {len(keep)} кандидатов -> {rf}. Раскомментируй бизнес-сущности, сохрани как {OUT}.")
    else:
        keep.sort()
        with open(OUT, "w", encoding="utf-8") as f:
            f.write("# СГЕНЕРИРОВАНО serene_select.py из ЖИВОГО OData — при желании сузить используй --review (picker).\n")
            f.write("# Только НЕПУСТЫЕ бизнес-сущности верхнего уровня; имена — из реальности, преполёт сверяет каждый прогон.\n\n")
            f.write("\n".join(es for es, _ in keep) + "\n")
        print(f"записано непустых: {len(keep)} -> {OUT}")
        for es, n in sorted(keep, key=lambda x: -x[1])[:50]:
            print(f"  {es}  ({n})")


if __name__ == "__main__":
    main()
