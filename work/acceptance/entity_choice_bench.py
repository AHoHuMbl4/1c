#!/usr/bin/env python3
"""ПРИБОР: ставит ли эмбеддер верную сущность первой.

Зачем отдельный прибор. Главная открытая проблема продукта — выбор сущности, и он
опирается на близость вектора вопроса к вектору названия сущности. Когда меняется модель
эмбеддинга (или её квантование), «стало лучше или хуже» нельзя решать по близости
перефразировок: это чужая мера, не наша задача. Здесь меряется наша.

Что делает:
  1. берёт пары «вопрос → эталонная сущность» ИЗ ПРИЁМОЧНОГО НАБОРА — имя таблицы
     вынимается из эталонного SQL, а не пишется руками (иначе прибор мерил бы мои
     представления, а не эталон);
  2. считает вектор вопроса той моделью, что задана в окружении;
  3. **ранжирование делает движок**: `ORDER BY emb <=> вектор` по `search_tables`.
     Наружу не уезжает ни одна строка данных (п. 20 TARGET.md);
  4. печатает долю попаданий в первую позицию, в тройку и в пятёрку.

🔴 Табличная часть засчитывается за свой документ: `..._товары` — это тот же объект,
разложенный по строкам, и выбрать шапку вместо табличной части (или наоборот) — не та
ошибка, которую меряет этот прибор.

Использование: python3 work/acceptance/entity_choice_bench.py [файл_набора]
Окружение:     SERENEDB_DSN_RO (или SERENEDB_DSN), EMBED_BASE_URL, EMBED_API_KEY,
               EMBED_MODEL, EMBED_DIM
"""
import json
import os
import re
import subprocess
import sys
import urllib.request

DSN = (os.environ.get("SERENEDB_DSN_RO")
       or os.environ.get("SERENEDB_DSN")
       or "host=127.0.0.1 port=7890 user=serene_ro dbname=ut_test")
EMBED_URL = (os.environ.get("EMBED_BASE_URL") or "").rstrip("/")
EMBED_KEY = os.environ.get("EMBED_API_KEY", "")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "")
EMBED_DIM = int(os.environ.get("EMBED_DIM", "1024"))
SET_FILE = sys.argv[1] if len(sys.argv) > 1 else "docs/ACCEPTANCE_UT.md"
EXCLUDE_SERVICE = os.environ.get("EXCLUDE_SERVICE", "0") == "1"

if not (EMBED_URL and EMBED_KEY and EMBED_MODEL):
    sys.exit("не заданы EMBED_BASE_URL / EMBED_API_KEY / EMBED_MODEL")


def embed(text):
    body = json.dumps({"model": EMBED_MODEL, "dimensions": EMBED_DIM,
                       "input": [text]}).encode()
    req = urllib.request.Request(EMBED_URL + "/embeddings", data=body, method="POST")
    req.add_header("Authorization", "Bearer " + EMBED_KEY)
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=300) as r:
        out = json.loads(r.read())
    # 🔴 Сверяем модель В ОТВЕТЕ: эндпоинт при незнакомом имени молча подставляет свою
    # ([замер 02.08]), и тогда прибор мерил бы не ту модель, которую называет в отчёте.
    got = (out.get("model") or "").strip()
    if got != EMBED_MODEL:
        sys.exit("эмбеддер отдаёт «%s», просили «%s» — замер бессмыслен" % (got, EMBED_MODEL))
    return out["data"][0]["embedding"]


def psql_raw(sql):
    p = subprocess.run(["psql", DSN, "-tA", "-v", "ON_ERROR_STOP=1", "-f", "-"],
                       input=sql, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or "psql failed")[:300])
    return [ln for ln in p.stdout.splitlines() if ln.strip()]


def psql(sql):
    return [ln.split(",")[0] for ln in psql_raw(sql)]


def pairs(path):
    """Вопрос → эталонная сущность, вынутая из эталонного SQL набора."""
    text = open(path, encoding="utf-8").read()
    out = []
    # Вопрос: строка вида **N. «...»** — хвост в скобках допустим (у 27, 56-58 он есть,
    # и прежний прогонщик молча терял эти четыре вопроса).
    blocks = re.split(r"\n(?=\*\*\d+\.\s*«)", text)
    for b in blocks:
        m = re.match(r"\*\*\d+\.\s*«(.+?)»", b, re.S)
        if not m:
            continue
        q = m.group(1).strip()
        t = re.search(r"\bfrom\s+([a-zа-яё0-9_]+)", b, re.I)
        if not t:
            continue
        want = t.group(1).lower()
        # Вопросы, где эталонный SQL идёт по НАШИМ таблицам (`search_corpus`,
        # `search_coverage`), выбор сущности 1С не проверяют вовсе — это вопросы про
        # содержимое корпуса и про полноту. Оставлять их значило бы записать в промахи
        # то, чего прибор не меряет.
        if want.startswith(("search_", "resolver_")):
            continue
        out.append((q, want))
    return out


def family_map():
    """Шапка документа и его табличная часть — один объект, а не два.

    🔴 Кто чей — СПРАШИВАЕМ У БАЗЫ, а не разбираем имя. Первая редакция прибора сводила
    табличную часть к владельцу регулярным выражением со списком суффиксов
    («товары», «услуги», «состав»…) — то есть держала в исполняемом коде реквизиты
    КОНКРЕТНОЙ конфигурации 1С. На англоязычной базе список молча не сработал бы, и
    верный ответ засчитался бы промахом. Штатное средство есть и заполняется на сборке:
    колонка `search_tables.parent`.
    """
    return {r.split("\x1f")[0]: r.split("\x1f")[1]
            for r in psql_raw("SELECT src_table || chr(31) || "
                              "coalesce(nullif(parent,''), src_table) FROM search_tables")}


def main():
    data = pairs(SET_FILE)
    if not data:
        sys.exit("в наборе не нашлось пар «вопрос → эталонная сущность»")
    fam_of = family_map()
    def family(name):
        return fam_of.get(name, name)
    hit1 = hit3 = hit5 = 0
    misses = []
    for q, want in data:
        vec = "[" + ",".join("%.7g" % x for x in embed(q)) + "]"
        # `EXCLUDE_SERVICE=1` — отсев служебных сущностей из соперников. Вынесен в ручку
        # именно для того, чтобы разница мерилась, а не утверждалась: [замер 02.08] из
        # 1502 меток боевой базы 805 помечены служебными (константы, настройки, права,
        # замеры времени платформы), и они участвуют в выборе на равных с данными —
        # «Сколько у нас партнёров?» проигрывает константе «ИспользоватьПартнеровИКонтрагентов».
        top = psql("SELECT t.src_table FROM search_tables t "
                   + ("LEFT JOIN search_entity_class e ON e.src_table = t.src_table "
                      if EXCLUDE_SERVICE else "")
                   + "WHERE t.emb IS NOT NULL "
                   + ("AND coalesce(e.cls,'') <> 'service' " if EXCLUDE_SERVICE else "")
                   + "ORDER BY t.emb <=> %s::FLOAT[%d], t.src_table LIMIT 5" % (vec, EMBED_DIM))
        fam = [family(t) for t in top]
        w = family(want)
        if fam[:1] == [w]:
            hit1 += 1
        if w in fam[:3]:
            hit3 += 1
        if w in fam[:5]:
            hit5 += 1
        else:
            misses.append((q[:52], want, top[0] if top else "-"))
    n = len(data)
    print("модель: %s   вопросов: %d   служебные сущности: %s"
          % (EMBED_MODEL, n, "ОТСЕЯНЫ" if EXCLUDE_SERVICE else "участвуют"))
    print("  верная сущность ПЕРВОЙ : %2d из %d  (%.0f%%)" % (hit1, n, 100.0 * hit1 / n))
    print("  в первой тройке        : %2d из %d  (%.0f%%)" % (hit3, n, 100.0 * hit3 / n))
    print("  в первой пятёрке       : %2d из %d  (%.0f%%)" % (hit5, n, 100.0 * hit5 / n))
    if misses:
        print("\nне попало в пятёрку (вопрос → эталон / что встало первым):")
        for q, want, got in misses[:15]:
            print("  «%s…» → %s / %s" % (q, want, got))


if __name__ == "__main__":
    main()
