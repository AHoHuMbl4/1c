#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""«Второй мозг»: отвечает на вопрос ПОИСКОМ В БАЗЕ, а не загрузкой схемы в модель.

Контракт намеренно совпадает с braine (`POST /ask` -> {kind, text, sources}), чтобы
переключение OpenClaw было обратимым одной строкой окружения (BRAINE_URL).

Пайплайн (docs/TARGET_ARCHITECTURE.md):

    вопрос
      │
      ├─ 1. РАЗБОР НАМЕРЕНИЯ — один вызов модели, которая видит ТОЛЬКО текст вопроса.
      │     Ни схемы, ни данных, ни имён таблиц в промте нет. На выходе — структура:
      │     что искать словами, какой порог по сумме, какой период, что хотят (список/сумма).
      │
      ├─ 2. ПОИСК В SereneDB — BM25 по словам вопроса + вектор по смыслу, а условия
      │     по числу и дате накладываются предикатами по INCLUDE-колонкам индекса.
      │
      ├─ 3. СЧЁТ В БАЗЕ — count/sum по всему найденному множеству, не по куску.
      │     Именно это отличает нас от чанкового RAG: он суммирует найденный фрагмент
      │     и уверенно выдаёт часть за целое (замер: docs/BENCH_BRAINE_VS_SERENE.md).
      │
      ├─ 4. ФОРМУЛИРОВКА — модель получает вопрос + строки результата (единицы строк).
      │
      └─ 5. ГЕЙТ — КОДОМ: каждое число из ответа обязано встречаться в результате запроса.
            Промт-правила не считаются защитой (требование владельца).

Env: SERENEDB_DSN, DEEPSEEK_*, ALIBABA_* (см. /etc/1c-mcp-reports.env), ASK_TOKEN.
Только stdlib.
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DSN = os.environ.get("SERENEDB_DSN_RO", "host=127.0.0.1 port=7890 user=serene_ro dbname=postgres")
PGPASSWORD = os.environ.get("PGPASSWORD", "")
LISTEN_HOST = os.environ.get("ASK_LISTEN_HOST", "127.0.0.1")
LISTEN_PORT = int(os.environ.get("ASK_LISTEN_PORT", "8091"))
ASK_TOKEN = os.environ.get("ASK_TOKEN", "")

CORPUS, INDEX, TABLES = "search_corpus", "search_idx", "search_tables"
TOPK = int(os.environ.get("ASK_TOPK", "40"))
ROWS_TO_MODEL = int(os.environ.get("ASK_ROWS_TO_MODEL", "25"))

DS_BASE = os.environ.get("DEEPSEEK_BASE", "https://api.deepseek.com").rstrip("/")
DS_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DS_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash")
DS_THINKING = os.environ.get("DEEPSEEK_THINKING", "disabled")

EMBED_URL = os.environ.get("ALIBABA_EMBED_URL", "").rstrip("/")
EMBED_KEY = os.environ.get("ALIBABA_API_KEY", "")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "text-embedding-v4")
EMBED_DIM = int(os.environ.get("EMBED_DIM", "1536"))


# ----------------------------------------------------------------- инфраструктура
def psql(sql):
    env = dict(os.environ)
    if PGPASSWORD:
        env["PGPASSWORD"] = PGPASSWORD
    p = subprocess.run(["psql", DSN, "-tA", "-F", "\x1f", "-c", sql],
                       capture_output=True, text=True, env=env)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or "psql failed")[:300])
    return [l.split("\x1f") for l in p.stdout.split("\n") if l != ""]


def lit(s):
    return "'" + str(s).replace("'", "''") + "'"


def ds_chat(messages, temperature=0, max_tokens=900):
    body = {"model": DS_MODEL, "temperature": temperature,
            "max_tokens": max_tokens, "messages": messages}
    if DS_THINKING:
        body["thinking"] = {"type": DS_THINKING}
    req = urllib.request.Request(DS_BASE + "/v1/chat/completions",
                                 data=json.dumps(body).encode(), method="POST")
    req.add_header("Authorization", "Bearer " + DS_KEY)
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())["choices"][0]["message"]["content"]


def embed_one(text):
    body = json.dumps({"model": EMBED_MODEL, "dimensions": EMBED_DIM, "input": [text]}).encode()
    req = urllib.request.Request(EMBED_URL + "/embeddings", data=body, method="POST")
    req.add_header("Authorization", "Bearer " + EMBED_KEY)
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())["data"][0]["embedding"]


# ----------------------------------------------------------------- 1. намерение
# Промт намеренно НЕ привязан к языку: продукт коробочный, база может быть любой —
# от продавца семечек до банка, на любом языке конфигурации. Инструкция описывает
# СМЫСЛ, а слова берутся из вопроса пользователя, каким бы он ни был.
INTENT_SYS = """Convert the user's question about company data into a structure.
Reply with JSON only.

{
  "terms":  ["words to search full-text: names of parties, goods, places, and the document
              kind if the user named it — taken FROM the question, in the question's own
              language; include natural inflections of the same word if useful"],
  "amount": {"op": ">"|"<"|">="|"<="|"between"|null, "value": number|null, "value2": number|null},
  "period": {"from": "YYYY-MM-DD"|null, "to": "YYYY-MM-DD"|null},
  "want":   "list" | "sum" | "count",
  "kind":   "ALWAYS fill this: a short noun naming WHAT kind of records the question is
             about, in the question's own language. If the user used a verb, give the
             corresponding noun. Only null if the question names no kind of records at all"
}

Rules:
- Never invent terms that are not in the question.
- want = "sum" when the user asks for a total money amount;
  "count" when they ask how many records; otherwise "list".
- A numeric threshold belongs in "amount", never in "terms".
- A time range belongs in "period" as dates; `today` is given below.
- Unknown fields are null. No text outside the JSON."""


def parse_intent(question, today):
    raw = ds_chat([{"role": "system", "content": INTENT_SYS},
                   {"role": "user", "content": "today=%s\n\nQuestion: %s" % (today, question)}],
                  max_tokens=400)
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        return {"terms": [], "amount": {}, "period": {}, "want": "list"}
    try:
        d = json.loads(m.group(0))
    except ValueError:
        return {"terms": [], "amount": {}, "period": {}, "want": "list"}
    d.setdefault("terms", [])
    d.setdefault("amount", {})
    d.setdefault("period", {})
    d["want"] = d.get("want") or "list"
    d["kind"] = (d.get("kind") or "").strip() or None
    d["terms"] = [str(t) for t in (d.get("terms") or []) if str(t).strip()][:8]
    return d


# ----------------------------------------------------------------- 2-3. поиск и счёт
def _predicates(intent):
    """Условия по числу и дате — предикаты по INCLUDE-колонкам индекса."""
    out = []
    a = intent.get("amount") or {}
    op, v, v2 = a.get("op"), a.get("value"), a.get("value2")
    if op and v is not None:
        if op == "between" and v2 is not None:
            out.append("amount BETWEEN %s AND %s" % (float(v), float(v2)))
        elif op in (">", "<", ">=", "<="):
            out.append("amount %s %s" % (op, float(v)))
    p = intent.get("period") or {}
    if p.get("from"):
        out.append("doc_date >= %s" % lit(p["from"]))
    if p.get("to"):
        out.append("doc_date < (%s::date + INTERVAL 1 day)" % lit(p["to"]))
    return out


def _fetch(match_sql, preds, order, limit):
    where = [w for w in ([match_sql] + preds) if w]
    src = INDEX if match_sql else CORPUS
    return psql(
        "SELECT row_key, src_table, coalesce(amount,0), coalesce(doc_date::date::text,''), "
        "       %s AS s, doc FROM %s%s ORDER BY s DESC LIMIT %d"
        % (order, src, (" WHERE " + " AND ".join(where)) if where else "", limit))


def search(question, intent):
    """Гибридный поиск: сначала строгое «И» по словам вопроса, потом «ИЛИ», потом вектор.

    Почему «И» первым: `ts_any` — это ИЛИ, и на вопросе «поступления от ООО ТехноСнаб»
    он тянет всё, где встречается «ООО». Строгое совпадение по всем словам даёт то самое
    множество, по которому потом честно считается сумма.
    """
    preds = _predicates(intent)
    terms = intent.get("terms") or []
    diag = {"terms": terms, "preds": preds}
    tq = "[" + ", ".join("ts_phrase(%s)" % lit(x) for x in terms) + "]" if terms else ""
    rank = "bm25(%s.tableoid)" % INDEX

    # Слово, которого в данных нет вообще («продажи» при таблице «реализациятоваровуслуг»),
    # обнуляет строгий поиск. Проверяем каждое слово по индексу и оставляем только живые —
    # это данные решают, а не список слов в коде.
    if terms:
        live, fuzzy = [], []
        for x in terms:
            n = psql("SELECT count(*) FROM %s WHERE doc @@ ts_phrase(%s)" % (INDEX, lit(x)))
            if n and n[0] and int(n[0][0]) > 0:
                live.append("ts_phrase(%s)" % lit(x))
                continue
            # Слово не нашлось целиком. Причина обычно морфологическая: спрашивают
            # «поступления», а в данных «ПоступлениеТоваровУслуг». Стемминг мы держим
            # выключенным (он привязан к языку), поэтому подбираем самый длинный
            # ПРЕФИКС, который что-то находит. Длину подбирает индекс, а не список
            # окончаний в коде: одинаково работает для любого языка.
            found = None
            for cut in range(len(x) - 1, max(3, int(len(x) * 0.5)) - 1, -1):
                p = x[:cut]
                n = psql("SELECT count(*) FROM %s WHERE doc @@ ts_starts_with(%s)"
                         % (INDEX, lit(p)))
                if n and n[0] and int(n[0][0]) > 0:
                    found = p
                    break
            if found:
                fuzzy.append("ts_starts_with(%s)" % lit(found))
                diag.setdefault("by_prefix", []).append("%s->%s" % (x, found))
        # Точное совпадение — ФИЛЬТР. Префиксное — только запасной вариант: «покупало»
        # обрезается до «покупа» и цепляет «Покупатель», а как обязательное условие
        # это уводит выборку не туда. Приблизительное годится, когда точного нет вовсе.
        diag["terms_exact"], diag["terms_fuzzy"] = len(live), len(fuzzy)
        use = live or fuzzy
        tq = "[" + ", ".join(use) + "]" if use else ""
        terms = use

    rows, match = [], ""
    t = time.time()
    if tq:
        match = "doc @@ ts_all(%s)" % tq
        rows = _fetch(match, preds, rank, TOPK)
        diag["mode"] = "all"
        if not rows:
            match = "doc @@ ts_any(%s)" % tq
            rows = _fetch(match, preds, rank, TOPK)
            diag["mode"] = "any"
    diag["bm25_ms"] = round((time.time() - t) * 1000, 1)
    diag["bm25_n"] = len(rows)

    # вектор — только когда словами не нашли НИЧЕГО. Одно точное попадание ценнее
    # сорока «похожих»: иначе релевантный результат тонет в шуме справочников.
    if not rows:
        t = time.time()
        vec = embed_one(question)
        vlit = "'[" + ",".join("%.6f" % x for x in vec) + "]'::FLOAT[%d]" % EMBED_DIM
        vrows = _fetch("", preds, "array_cosine_similarity(emb, %s)" % vlit, TOPK)
        seen = {r[0] for r in rows}
        rows += [r for r in vrows if r[0] not in seen]
        match, diag["vec_used"] = "", True
        diag["vec_ms"] = round((time.time() - t) * 1000, 1)

    # только условие, без слов («все документы больше 500 000»)
    if not rows and preds:
        rows = _fetch("", preds, "0", TOPK)
        diag["by_predicate_only"] = True
    return rows, match, diag


def widen_by_predicate(src_table, preds, rows):
    """Добрать ВСЕ строки фокусной таблицы, подходящие под условие.

    Вопрос «какие продажи больше 500 000» — это не «покажи похожие», а «покажи все».
    Вектор ранжирует, но не обязан вернуть полный список; условие возвращает.
    """
    if not (src_table and preds):
        return rows
    full = psql(
        "SELECT row_key, src_table, coalesce(amount,0), coalesce(doc_date::date::text,''), "
        "       0 AS s, doc FROM %s WHERE %s AND src_table = %s ORDER BY amount DESC LIMIT %d"
        % (CORPUS, " AND ".join(preds), lit(src_table), TOPK))
    seen = {r[0] for r in full}
    return full + [r for r in rows if r[0] not in seen]


def table_by_meaning(question, candidates):
    """Какая сущность ближе всего к вопросу по НАЗВАНИЮ. Пусто — если профиля нет."""
    if not candidates:
        return None
    try:
        vec = embed_one(question)
        vlit = "'[" + ",".join("%.6f" % x for x in vec) + "]'::FLOAT[%d]" % EMBED_DIM
        rs = psql("SELECT src_table, array_cosine_similarity(emb, %s) AS s FROM %s "
                  "WHERE src_table IN (%s) ORDER BY s DESC LIMIT 1"
                  % (vlit, TABLES, ", ".join(lit(c) for c in candidates)))
    except RuntimeError:
        return None
    return rs[0][0] if rs and rs[0] else None


def _vec(text):
    return "'[" + ",".join("%.6f" % x for x in embed_one(text)) + "]'::FLOAT[%d]" % EMBED_DIM


def focus(question, rows, want, kind=None, have_terms=False):
    """Из разнородных попаданий выбрать ОДНУ таблицу, по которой считать итог.

    Складывать суммы справочников, договоров и документов вместе — бессмыслица (именно
    так в первом прогоне получилось 7e20). Выбор источника — ПО СМЫСЛУ ВОПРОСА:
    считаем близость вопроса к строкам каждого источника вектором. Так «продали»
    приводит к реализациям, а не к поступлениям на счёт, без единого слова в коде.
    Для вопросов про сумму источники без денег отбрасываются: ответить они не могут.
    """
    by = {}
    for r in rows:
        by.setdefault(r[1], []).append(r)
    if not by:
        return None, []
    if len(by) == 1:
        src = next(iter(by))
        return src, by[src]

    # О ЧЁМ вопрос — решаем сравнением с НАЗВАНИЕМ сущности («продажи» ближе к
    # «Реализация Товаров Услуг», чем к «Поступление Товаров Услуг»). Сравнивать с
    # текстом строк нельзя: там доминируют имена контрагентов и числа, и вопрос
    # «за декабрь» уводит в соседнюю таблицу.
    sim = {}
    try:
        vlit = _vec(kind or question)
        for t_, c in psql("SELECT src_table, array_cosine_similarity(emb, %s) FROM %s"
                          % (vlit, TABLES)):
            sim[t_] = _num(c)
        keys = ", ".join(lit(r[0]) for r in rows if r[0])
        if keys:
            qlit = _vec(question)
            for t_, c in psql("SELECT src_table, max(array_cosine_similarity(emb, %s)) "
                              "FROM %s WHERE row_key IN (%s) GROUP BY 1"
                              % (qlit, CORPUS, keys)):
                sim[t_] = max(sim.get(t_, 0.0), _num(c))
    except RuntimeError:
        sim = {}                      # профиля ещё нет — решаем по числу попаданий

    def score(t_, rs):
        with_amt = sum(1 for r in rs if _num(r[2]))
        money_first = 1 if (want in ("sum", "count") and with_amt) else 0
        # Нашлись слова — верим попаданиям: имя контрагента точно указало на его
        # документы. Слов нет — верить нечему, кроме смысла.
        if have_terms:
            # Сила совпадения, ВЗВЕШЕННАЯ смыслом. По отдельности оба сигнала врут:
            # по количеству побеждает справочник статей (слово «поступления» там в
            # каждой строке), а по смыслу — таблица с похожим названием, где нужного
            # контрагента нет вовсе. Произведение требует и того, и другого.
            mass = sum(max(_num(r[4]), 0.0) for r in rs)
            return (money_first, round(mass * max(sim.get(t_, 0.0), 0.0), 4), len(rs))
        return (money_first, sim.get(t_, 0.0), len(rs))

    src, rs = max(by.items(), key=lambda kv: score(kv[0], kv[1]))
    return src, rs


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def aggregate(src_table, match, preds, want=None):
    """Итог считается В БАЗЕ по ВСЕМУ подходящему множеству, без LIMIT.

    Это ключевое отличие от чанкового RAG: тот суммирует то, что попало в выборку,
    и выдаёт часть за целое. Здесь LIMIT влияет только на то, что покажем модели,
    но не на цифру.
    """
    if not src_table:
        return None
    where = [w for w in ([match] + preds + ["src_table = %s" % lit(src_table)]) if w]
    src = INDEX if match else CORPUS
    r = psql("SELECT count(*), coalesce(sum(amount),0) FROM %s WHERE %s"
             % (src, " AND ".join(where)))
    if not r or not r[0] or r[0][0] == "":
        return None
    return {"count": int(r[0][0]), "sum": _num(r[0][1]), "src": src_table}


# ----------------------------------------------------------------- 4. формулировка
ANSWER_SYS = """You answer an employee's question using ONLY the rows given to you.

- Reply in the SAME language the question was asked in.
- Never invent numbers, dates or names that are not in the rows.
- If the rows do not answer the question, say plainly that there is no data.
- If a TOTAL is provided, it was computed over every matching row — use exactly that figure.
- Be short and businesslike, no preamble. Amounts as digits."""


def compose(question, rows, agg):
    payload = []
    for r in rows[:ROWS_TO_MODEL]:
        head = r[5][:320]
        tail = []
        if _num(r[2]):
            tail.append("amount=%s" % ("%d" % _num(r[2]) if _num(r[2]) == int(_num(r[2]))
                                       else "%.2f" % _num(r[2])))
        if r[3]:
            tail.append("date=%s" % r[3])
        payload.append(head + ((" | " + " | ".join(tail)) if tail else ""))
    body = "ВОПРОС: %s\n\nНАЙДЕННЫЕ СТРОКИ (%d):\n%s" % (
        question, len(rows), "\n".join("- " + p for p in payload))
    if agg:
        body += "\n\nИТОГ ПО ВСЕМ НАЙДЕННЫМ: количество=%d, сумма=%s" % (
            agg["count"], ("%d" % agg["sum"]) if agg["sum"] == int(agg["sum"]) else "%.2f" % agg["sum"])
    return ds_chat([{"role": "system", "content": ANSWER_SYS},
                    {"role": "user", "content": body}], max_tokens=800)


# ----------------------------------------------------------------- 5. гейт (кодом)
SPACE = re.compile(r"[^\S\n]+")
DATE = re.compile(r"\b(\d{1,4})[.\-/](\d{1,2})(?:[.\-/](\d{1,4}))?\b")
NUM = re.compile(r"\d+(?:[.,]\d+)?")


def _dates(text):
    """Даты как НАБОР компонент, без разбора формата.

    Человеку всё равно, «09.12», «9.12.2025» или «2025-12-09». Сравнивать форматы —
    значит зашивать локаль; сравниваем множества чисел: {9,12} входит в {2025,12,9}.
    """
    return [frozenset(int(x) for x in m.groups() if x) for m in DATE.finditer(str(text or ""))]


def _norm_numbers(text):
    """Числа из текста.

    Разделителем разрядов бывает любой пробел, включая неразрывный: без склейки
    «2 088 800» распадается на 2, 88 и 800, и гейт зря считает ответ выдумкой.
    Даты убираем — их проверяет `_dates`, иначе «9.12» выглядит числом 9.12.
    """
    if not text:
        return set()
    t = SPACE.sub("", DATE.sub(" ", str(text)))
    out = set()
    for m in NUM.finditer(t):
        try:
            v = float(m.group(0).replace(",", "."))
        except ValueError:
            continue
        out.add(round(v, 2))
        if v == int(v):
            out.add(float(int(v)))
    return out


def gate(answer, rows, agg, question=""):
    """Каждое число ответа обязано встречаться в данных, в итоге или в самом вопросе.

    Правило живёт в КОДЕ, а не в промте: промт — это пожелание, а не гарантия.
    Числа из вопроса разрешены отдельно (человек сам назвал порог «больше 500000»,
    и повторить его в ответе — не выдумка).
    """
    allowed = set()
    for r in rows:
        allowed |= _norm_numbers(r[5])
        allowed |= _norm_numbers(r[2])
        allowed |= _norm_numbers(r[3])
    if agg:
        allowed |= _norm_numbers(str(agg["count"]))
        allowed |= _norm_numbers("%.2f" % agg["sum"])
        allowed |= {round(agg["sum"], 2), float(agg["count"])}
    allowed |= _norm_numbers(question)

    bad = [n for n in _norm_numbers(answer) if n not in allowed]

    # Даты: компоненты названной даты обязаны входить в какую-то дату из данных.
    known = []
    for r in rows:
        known += _dates(r[3]) + _dates(r[5])
    for d in _dates(answer):
        if not any(d <= k for k in known):
            bad.append(tuple(sorted(d)))
    return (not bad), bad


# ----------------------------------------------------------------- HTTP
def answer(question):
    t0 = time.time()
    today = time.strftime("%Y-%m-%d")
    intent = parse_intent(question, today)
    rows, match, diag = search(question, intent)
    if not rows:
        return {"kind": "no_data", "text": "нет данных", "sources": [],
                "diag": dict(diag, sec=round(time.time() - t0, 2))}

    want = intent.get("want")
    src, focused = focus(question, rows, want, intent.get("kind"),
                         bool(diag.get("terms_exact")))
    diag["focus"], diag["kind"] = src, intent.get("kind")
    # Итог по фокусной таблице считаем ВСЕГДА, даже когда спросили список: иначе
    # модель складывает сама, а такое число гейт обязан отклонить — и вместе с ним
    # гибнет правильный ответ.
    if diag["preds"]:
        # Когда слов для полнотекста нет вовсе («какие продажи больше 500 000»),
        # нельзя наследовать источник от векторной выдачи: она вернула что попало,
        # и расширение по условию только закрепит ошибку. Выбираем сущность по
        # названию среди ВСЕХ, где условие вообще выполняется.
        if not diag.get("terms_exact"):
            cand = [r[0] for r in psql("SELECT DISTINCT src_table FROM %s WHERE %s"
                                       % (CORPUS, " AND ".join(diag["preds"])))]
            best = table_by_meaning(intent.get("kind") or question, cand)
            if best:
                src = best
                diag["focus_by_name"] = src
        rows = widen_by_predicate(src, diag["preds"], rows)
        focused = [r for r in rows if r[1] == src] or rows
    agg = aggregate(src, match if not diag.get("by_predicate_only") else "", diag["preds"])
    if want in ("sum", "count"):
        # Для арифметики нужен ОДИН источник: складывать справочник с документами нельзя.
        rows = focused or rows
    else:
        # Для списка сужать нельзя: ответ про контрагента складывается из его карточки
        # И его документов. Фокус здесь задаёт лишь порядок показа.
        rows = (focused or []) + [r for r in rows if r not in (focused or [])]
    text = compose(question, rows, agg)
    ok, bad = gate(text, rows, agg, question)
    if not ok:
        # Числа, которых нет в данных, наружу не выпускаем: отдаём проверяемый факт.
        sys.stderr.write("ask GATE: числа вне данных: %s\n" % bad[:6])
        if agg:
            text = ("Найдено %d записей; сумма %s." %
                    (agg["count"], ("%d" % agg["sum"]) if agg["sum"] == int(agg["sum"])
                     else "%.2f" % agg["sum"]))
        else:
            return {"kind": "no_data", "text": "нет данных", "sources": [],
                    "diag": dict(diag, gate_rejected=bad[:6])}

    srcs = []
    for r in rows[:5]:
        tag = r[1].split("_", 1)[1] if "_" in r[1] else r[1]
        if tag not in srcs:
            srcs.append(tag)
    return {"kind": "answer", "text": text.strip(), "sources": srcs,
            "diag": dict(diag, rows=len(rows), sec=round(time.time() - t0, 2),
                         gate_ok=ok)}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        sys.stderr.write("ask %s - %s\n" % (self.address_string(), fmt % args))

    def _send(self, code, obj):
        b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path.rstrip("/") == "/health":
            try:
                n = psql("SELECT count(*) FROM %s" % CORPUS)[0][0]
                return self._send(200, {"status": "serene-ask-ok", "corpus_rows": int(n)})
            except Exception as e:                      # noqa: BLE001
                return self._send(503, {"status": "degraded", "error": str(e)[:200]})
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path.rstrip("/") != "/ask":
            return self._send(404, {"error": "not found"})
        if ASK_TOKEN and self.headers.get("Authorization", "") != "Bearer " + ASK_TOKEN:
            return self._send(401, {"error": "unauthorized"})
        try:
            n = int(self.headers.get("Content-Length", "0"))
            req = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return self._send(400, {"error": "bad json"})
        question = (req.get("question") or "").strip()
        if not question:
            return self._send(400, {"error": "empty question"})
        try:
            return self._send(200, answer(question))
        except Exception as e:                          # noqa: BLE001
            sys.stderr.write("ask ERROR: %r\n" % (e,))
            return self._send(500, {"kind": "error", "text": "", "sources": [],
                                    "error": str(e)[:300]})


def main():
    srv = ThreadingHTTPServer((LISTEN_HOST, LISTEN_PORT), Handler)
    sys.stderr.write("serene-ask на http://%s:%d  (поиск в SereneDB, схема в модель не уходит)\n"
                     % (LISTEN_HOST, LISTEN_PORT))
    srv.serve_forever()


if __name__ == "__main__":
    main()
