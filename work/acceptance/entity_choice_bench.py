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
import time
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
# Вид API эмбеддера: `openai` — общий /v1/embeddings; `texts` — {texts:[…], is_query}.
# 🔴 `is_query` не украшение: Qwen3 считает вопрос и документ ПО-РАЗНОМУ, и если звать
# одинаково, часть качества теряется молча.
EMBED_API = os.environ.get("EMBED_API", "openai")
RERANK_URL = os.environ.get("RERANK_URL", "")
RERANK_TOP = int(os.environ.get("RERANK_TOP", "10"))
# Таблица меток для замера. Нужна, когда размерность модели не совпадает с боевой
# колонкой (у 8B она 4096 против наших 1024) — трогать боевую ради замера нельзя.
BENCH_TABLE = os.environ.get("BENCH_TABLE", "")
# 🔴 Cloudflare перед сервисом режет клиента по подписи (`error code: 1010`): curl
# проходит, python — нет. Заголовок ставится явно, иначе замер упирается в 403.
UA = os.environ.get("EMBED_UA", "curl/8.5.0")

# Ключ обязателен не везде: сервис в своём контуре может стоять без него.
if not EMBED_URL or not EMBED_MODEL:
    sys.exit("не заданы EMBED_BASE_URL / EMBED_MODEL")


def _post(url, obj, timeout=600):
    req = urllib.request.Request(url, data=json.dumps(obj).encode(), method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", UA)
    if EMBED_KEY:
        req.add_header("Authorization", "Bearer " + EMBED_KEY)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def embed_many(texts, is_query):
    """Векторы пачкой. `is_query` различает вопрос и документ — см. EMBED_API."""
    if EMBED_API == "texts":
        out = _post(EMBED_URL, {"texts": texts, "is_query": bool(is_query), "dim": EMBED_DIM})
        return out["embeddings"]
    out = _post(EMBED_URL + "/embeddings",
                {"model": EMBED_MODEL, "dimensions": EMBED_DIM, "input": texts})
    got = (out.get("model") or "").strip()
    if got and got != EMBED_MODEL:
        sys.exit("эмбеддер отдаёт «%s», просили «%s» — замер бессмыслен" % (got, EMBED_MODEL))
    return [d["embedding"] for d in out["data"]]


def rerank(query, docs):
    """Порядок индексов от реранкера; пусто — не сработал."""
    try:
        out = _post(RERANK_URL, {"query": query, "documents": docs})
        return [int(x["index"]) for x in out["results"]]
    except Exception as e:                      # noqa: BLE001
        sys.stderr.write("реранкер не отработал: %r\n" % (e,))
        return []


def embed(text):
    if EMBED_API == "texts":
        return embed_many([text], True)[0]
    body = json.dumps({"model": EMBED_MODEL, "dimensions": EMBED_DIM,
                       "input": [text]}).encode()
    req = urllib.request.Request(EMBED_URL + "/embeddings", data=body, method="POST")
    req.add_header("Authorization", "Bearer " + EMBED_KEY)
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", UA)
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


def fill_bench_table():
    """Заполнить таблицу меток векторами ЭТОЙ модели.

    Нужна, когда размерность модели не совпадает с боевой колонкой: у 8B она 4096
    против наших 1024, и мерить, ломая боевую таблицу, нельзя. Метки считаются как
    ДОКУМЕНТЫ (`is_query=false`) — вопрос считается иначе, и путать их нельзя.
    """
    names = psql_raw("SELECT src_table || chr(31) || label FROM search_tables ORDER BY src_table")
    pairs_ = [r.split("\x1f", 1) for r in names if "\x1f" in r]
    dim = len(embed_many([pairs_[0][1]], False)[0])
    psql_raw("DROP TABLE IF EXISTS %s; CREATE TABLE %s (src_table TEXT, emb FLOAT[%d]);"
             % (BENCH_TABLE, BENCH_TABLE, dim))
    B = int(os.environ.get("BENCH_BATCH", "32"))
    t0 = time.time()
    for i in range(0, len(pairs_), B):
        part = pairs_[i:i + B]
        vecs = embed_many([p[1] for p in part], False)
        vals = ", ".join("(%s, %s::FLOAT[%d])"
                         % ("'" + p[0].replace("'", "''") + "'",
                            "[" + ",".join("%.7g" % x for x in v) + "]", dim)
                         for p, v in zip(part, vecs))
        psql_raw("INSERT INTO %s VALUES %s;" % (BENCH_TABLE, vals))
        sys.stderr.write("  метки %d/%d, %.0f с\n" % (min(i + B, len(pairs_)), len(pairs_), time.time() - t0))
    return dim


def main():
    data = pairs(SET_FILE)
    if not data:
        sys.exit("в наборе не нашлось пар «вопрос → эталонная сущность»")
    global EMBED_DIM
    table = "search_tables"
    if BENCH_TABLE:
        table = BENCH_TABLE
        if os.environ.get("BENCH_FILL", "1") == "1":
            EMBED_DIM = fill_bench_table()
        else:
            EMBED_DIM = int(psql_raw("SELECT array_length(emb) FROM %s LIMIT 1" % BENCH_TABLE)[0])
    fam_of = family_map()
    def family(name):
        return fam_of.get(name, name)
    hit1 = hit3 = hit5 = hitN = 0
    misses = []
    for q, want in data:
        vec = "[" + ",".join("%.7g" % x for x in embed(q)) + "]"
        # `EXCLUDE_SERVICE=1` — отсев служебных сущностей из соперников. Вынесен в ручку
        # именно для того, чтобы разница мерилась, а не утверждалась: [замер 02.08] из
        # 1502 меток боевой базы 805 помечены служебными (константы, настройки, права,
        # замеры времени платформы), и они участвуют в выборе на равных с данными —
        # «Сколько у нас партнёров?» проигрывает константе «ИспользоватьПартнеровИКонтрагентов».
        want_n = max(5, RERANK_TOP if RERANK_URL else 5)
        top = psql("SELECT t.src_table FROM %s t " % table
                   + ("LEFT JOIN search_entity_class e ON e.src_table = t.src_table "
                      if EXCLUDE_SERVICE else "")
                   + "WHERE t.emb IS NOT NULL "
                   + ("AND coalesce(e.cls,'') <> 'service' " if EXCLUDE_SERVICE else "")
                   + "ORDER BY t.emb <=> %s::FLOAT[%d], t.src_table LIMIT %d"
                   % (vec, EMBED_DIM, want_n))
        # Дошла ли верная сущность до реранкера вообще: это и есть требование к первой
        # ступени. Реранкер выбирает ТОЛЬКО из того, что ему дали, — если верного в
        # списке нет, никакая его точность не поможет.
        if family(want) in [family(t) for t in top]:
            hitN += 1
        # 🔴 Реранкер — ВТОРАЯ половина пути. Эмбеддер отбирает кандидатов, а кто из них
        # верный, решает он; мерить одного эмбеддера значит мерить полдела.
        if RERANK_URL and len(top) > 1:
            lbl = {r.split("\x1f")[0]: r.split("\x1f")[1]
                   for r in psql_raw("SELECT src_table || chr(31) || label FROM search_tables "
                                     "WHERE src_table IN (%s)"
                                     % ", ".join("'" + t.replace("'", "''") + "'" for t in top))}
            order = rerank(q, [lbl.get(t, t) for t in top])
            if order:
                top = [top[i] for i in order if 0 <= i < len(top)]
        top = top[:5]
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
    print("  дошла до реранкера (в первых %d): %2d из %d  (%.0f%%)"
          % (max(5, RERANK_TOP), hitN, n, 100.0 * hitN / n))
    if misses:
        print("\nне попало в пятёрку (вопрос → эталон / что встало первым):")
        for q, want, got in misses[:15]:
            print("  «%s…» → %s / %s" % (q, want, got))


if __name__ == "__main__":
    main()
