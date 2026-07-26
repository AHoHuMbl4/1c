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
SLOP_SPAN = int(os.environ.get("ASK_SLOP_SPAN", "8"))   # окно между краями фразы

# Модель ранжирования — штатная функция движка, а не наша сортировка. Выбирается
# окружением, чтобы сравнивать варианты A/B на одном наборе вопросов, а не спорить.
#   bm25     — по умолчанию у движка (k1=1.2, b=0.75): штрафует длинные документы;
#   bm25_b0  — без нормализации по длине: строки документов длиннее строк справочников,
#              и штраф по длине систематически задвигает документы вниз;
#   tfidf    — классика без нормализации по длине.
SCORERS = {
    "bm25": "bm25(%s.tableoid)",
    "bm25_b0": "bm25(%s.tableoid, 1.2, 0.0)",
    "tfidf": "tfidf(%s.tableoid)",
}
SCORER = os.environ.get("ASK_SCORER", "bm25")

DS_BASE = os.environ.get("DEEPSEEK_BASE", "https://api.deepseek.com").rstrip("/")
DS_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DS_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash")
DS_THINKING = os.environ.get("DEEPSEEK_THINKING", "disabled")

EMBED_URL = os.environ.get("ALIBABA_EMBED_URL", "").rstrip("/")
EMBED_KEY = os.environ.get("ALIBABA_API_KEY", "")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "text-embedding-v4")
EMBED_DIM = int(os.environ.get("EMBED_DIM", "1536"))

# Единственные две строки, которые уходят человеку от НАС, а не от модели: ответ модели
# всегда на языке вопроса. Вынесены в окружение, чтобы локализовать без правки кода.
NO_DATA_TEXT = os.environ.get("ASK_NO_DATA_TEXT", "нет данных")
TOTAL_TEXT = os.environ.get("ASK_TOTAL_TEXT", "Найдено {count} записей; сумма {sum}.")


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


def _fmt(v):
    """Число для человека и для сверки: без хвоста .0 у целых."""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "0"
    return "%d" % v if v == int(v) else "%.2f" % v


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
  "terms":  [["alternatives for ONE concept"], ["alternatives for the NEXT concept"]],
  "amount": {"op": ">"|"<"|">="|"<="|"between"|null, "value": number|null, "value2": number|null},
  "period": {"from": "YYYY-MM-DD"|null, "to": "YYYY-MM-DD"|null},
  "want":   "list" | "sum" | "count",
  "kind":   "ALWAYS fill this: a short noun naming WHAT kind of records the question is
             about, in the question's own language. If the user used a verb, give the
             corresponding noun. Only null if the question names no kind of records at all"
}

Rules:
- "terms" holds only VALUES that should literally appear in a record: names of parties,
  goods, places, document numbers. NEVER put the KIND of records there — that goes to
  "kind". A record about a bank in Moscow need not contain the word "bank".
- Group alternatives for the same concept together: expand abbreviations to their full
  form and add the inflections a record would realistically use. Example shape:
  [["Moscow", "MSK"], ["Acme"]] — matching is AND between groups, OR inside a group.
- Never invent concepts that are not in the question.
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
    # Поддерживаем и плоский список (старый вид), и группы синонимов
    groups = []
    for item in (d.get("terms") or []):
        alts = item if isinstance(item, list) else [item]
        alts = [str(a).strip() for a in alts if str(a).strip()]
        if alts:
            groups.append(alts[:6])
    d["terms"] = groups[:6]
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


def probe(groups):
    """Проверить все слова вопроса ОДНИМ запросом и вернуть выражение на каждое понятие.

    Три способа на каждое слово, по убыванию строгости:
      * `ts_phrase`      — точное совпадение, проходит через анализатор (регистр не важен);
      * `ts_levenshtein` — опечатки и словоформы, тоже через анализатор;
      * `ts_like`        — подстрока, для склеенных имён («поступления» в
                           «ПоступлениеТоваровУслуг»).
    Важно: `ts_like` и `ts_starts_with` — ТЕРМИННЫЕ функции, анализатор их не трогает и
    регистр не понижает. Проверено на инстансе: `ts_starts_with('Сбербан')` = 0, а
    `ts_starts_with('сбербан')` = 143. Поэтому для них слово приводится к нижнему регистру.
    Раньше здесь был цикл подбора длины префикса — до шести отдельных запросов на слово,
    и для имён собственных он не находил ничего вообще.
    """
    probes, meta = [], []
    for gi, group in enumerate(groups):
        for ai_, alt in enumerate(group):
            variants = [("exact", "ts_phrase(%s)" % lit(alt))]
            words = alt.split()
            if len(words) > 1:
                # Многословное имя в данных часто разорвано: «Общество с ограниченной
                # ответственностью "Ромашка"». Точная фраза «Общество Ромашка» даёт 0,
                # фраза с окном — 9. Окно берём по числу пропущенных слов, а не по
                # магической константе: сколько слов между краями, столько и допускаем.
                variants.append(("slop", "ts_phrase(%s, ARRAY[0,%d], %s)"
                                 % (lit(words[0]), SLOP_SPAN, lit(words[-1]))))
            variants += [("fuzzy", "ts_levenshtein(%s, 2)" % lit(alt)),
                         ("part", "ts_like(%s)" % lit("%" + alt.lower() + "%"))]
            for kind, expr in variants:
                probes.append("SELECT %d i, count(*) n FROM %s WHERE doc @@ %s"
                              % (len(meta), INDEX, expr))
                meta.append((gi, kind, expr))
    if not probes:
        return [], {}
    counts = {}
    for r in psql(" UNION ALL ".join(probes)):
        try:
            counts[int(r[0])] = int(r[1])
        except (ValueError, IndexError):
            pass
    per_group, diag = {}, {}
    for i, (gi, kind, expr) in enumerate(meta):
        if counts.get(i, 0) <= 0:
            continue
        rank = {"exact": 0, "slop": 1, "fuzzy": 2, "part": 3}[kind]
        cur = per_group.get(gi)
        if cur is None or rank < cur[0]:
            per_group[gi] = (rank, [expr], kind)
        elif rank == cur[0] and expr not in cur[1]:
            cur[1].append(expr)
    out = []
    for gi in sorted(per_group):
        rank, exprs, kind = per_group[gi]
        out.append(exprs[0] if len(exprs) == 1 else "ts_any([%s])" % ", ".join(exprs))
        diag[gi] = kind
    return out, diag


def match_expr(exprs, preds):
    """Собрать условие поиска с ГРАДИЕНТОМ: сперва все понятия, потом мягче.

    `ts_any(массив, k)` — «не меньше k из N». Прежний обрыв «всё → любое» на вопросе
    «поступления от ООО ТехноСнаб» давал либо ноль, либо всё, где есть «ООО».
    """
    n = len(exprs)
    if not n:
        return "", 0
    for k in range(n, 0, -1):
        expr = exprs[0] if (n == 1) else (
            "ts_all([%s])" % ", ".join(exprs) if k == n
            else "ts_any([%s], %d)" % (", ".join(exprs), k))
        cond = " AND ".join(["doc @@ %s" % expr] + preds)
        r = psql("SELECT count(*) FROM %s WHERE %s" % (INDEX, cond))
        if r and r[0] and int(r[0][0]) > 0:
            return "doc @@ %s" % expr, k
    return "doc @@ %s" % (exprs[0] if n == 1 else "ts_any([%s], 1)" % ", ".join(exprs)), 1


def tables_of(match, preds):
    """Разложить ВСЁ множество совпадений по источникам — группировкой в индексе.

    Раньше источники считались по 40 строкам, отобранным по рангу. BM25 штрафует
    длинные документы, поэтому справочник вытеснял документы из выдачи целиком:
    замерено — 74 строки из четырёх таблиц документов не попадали в кандидаты вовсе,
    и выбирать приходилось между неверными.
    """
    where = " AND ".join([w for w in ([match] + preds) if w]) or "TRUE"
    src = INDEX if match else CORPUS
    out = {}
    for r in psql("SELECT src_table, count(*) FROM %s WHERE %s GROUP BY 1" % (src, where)):
        try:
            out[r[0]] = int(r[1])
        except (ValueError, IndexError):
            pass
    return out


def rows_of(src_table, match, preds, limit):
    """Строки одного источника. Модели отдаём подсвеченный фрагмент, а не начало строки."""
    where = [w for w in ([match] + preds) if w] + ["src_table = %s" % lit(src_table)]
    src = INDEX if match else CORPUS
    frag = ("ts_highlight(doc, 'MaxWords=14,MaxFragments=2,StartSel=[,StopSel=]')"
            if match else "doc")
    order = ((SCORERS.get(SCORER, SCORERS["bm25"]) % INDEX) + " DESC") if match \
        else "amount DESC NULLS LAST"
    return psql(
        "SELECT row_key, src_table, coalesce(amount,0), coalesce(doc_date::date::text,''), "
        "       0 AS s, %s FROM %s WHERE %s ORDER BY %s LIMIT %d"
        % (frag, src, " AND ".join(where), order, limit))


PICK_SYS = """You map a user's question to ONE record type.

You get the question and a numbered list of record types that exist in this database.
Answer with the NUMBER only — the type whose records would ANSWER the question.
Some entries show how many records already match the question; prefer a type that
actually has matches over a same-sounding one that has none.
If none of them fits, answer 0.
Judge by meaning, across languages and wording: a question about sales belongs to the
type that records sales even if the words differ.
Records are kept from the company's own point of view, so a counterparty's purchase is
the company's sale, and a counterparty's sale is the company's receipt."""


def pick_entity(question, kind, cands, counts=None):
    """Какая сущность имеется в виду — спрашиваем модель, но даём ей ТОЛЬКО НАЗВАНИЯ.

    Почему не вектором: замерено на живых данных — эмбеддинг не связывает «продажи» с
    «Реализация Товаров Услуг» (0.419) и ставит выше «Склады» (0.465), а для «покупки»
    сигнала нет вовсе. Короткие названия дают ложное сходство с любым коротким запросом.
    Наращивать эвристику здесь — значит подбирать её под конкретную базу.

    Модель для этого и нужна: сопоставить слово человека с названием сущности — чисто
    языковая задача. Данные ей не показываем, схему тоже: только список названий тех
    сущностей, где ПОИСК УЖЕ ЧТО-ТО НАШЁЛ. Список приходит из данных, а не из кода,
    поэтому одинаково работает на базе любого размера и на любом языке.
    """
    if len(cands) < 2:
        return cands[0] if cands else None
    try:
        rs = psql("SELECT src_table, label FROM %s WHERE src_table IN (%s)"
                  % (TABLES, ", ".join(lit(c) for c in cands)))
    except RuntimeError:
        return None
    names = [(r[0], r[1]) for r in rs if r and r[0]]
    if len(names) < 2:
        return names[0][0] if names else None
    # Рядом с названием — СКОЛЬКО СОВПАДЕНИЙ там нашлось. Это данные, а не схема, и
    # именно они снимают неоднозначность: справочник «Банки» на 1 запись и
    # «Классификатор Банков» на 680 по названию неразличимы, по числу — очевидны.
    counts = counts or {}
    listing = "\n".join(
        "%d. %s%s" % (i + 1, nm,
                      "" if t not in counts else " — %d matching records" % counts[t])
        for i, (t, nm) in enumerate(names))
    ask_text = question if not kind else "%s (%s)" % (question, kind)
    try:
        raw = ds_chat([{"role": "system", "content": PICK_SYS},
                       {"role": "user", "content": "%s\n\nTypes:\n%s" % (ask_text, listing)}],
                      max_tokens=8)
    except Exception:                          # noqa: BLE001 — сеть/квота
        return None
    m = re.search(r"\d+", raw or "")
    if not m:
        return None
    i = int(m.group(0))
    return names[i - 1][0] if 1 <= i <= len(names) else None


def _vec(text):
    return "'[" + ",".join("%.6f" % x for x in embed_one(text)) + "]'::FLOAT[%d]" % EMBED_DIM


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def aggregate(src_table, match, preds):
    """Итог считается В БАЗЕ по ВСЕМУ подходящему множеству, без LIMIT.

    Это ключевое отличие от чанкового RAG: тот суммирует то, что попало в выборку,
    и выдаёт часть за целое. Здесь LIMIT влияет только на то, что покажем модели,
    но не на цифру.
    """
    if not src_table:
        return None
    where = [w for w in ([match] + preds + ["src_table = %s" % lit(src_table)]) if w]
    src = INDEX if match else CORPUS
    # Считаем не только итог: у каждой величины будет СВОЯ РОЛЬ, и гейт сверяет
    # число именно с той ролью, в которой оно названо. Иначе «настоящее число не от
    # тех строк» проходит: сумма одной строки, выданная за итог, гейту неотличима.
    r = psql("SELECT count(*), coalesce(sum(amount),0), coalesce(min(amount),0), "
             "       coalesce(max(amount),0), coalesce(avg(amount),0), "
             "       coalesce(min(doc_date)::date::text,''), "
             "       coalesce(max(doc_date)::date::text,'') "
             "FROM %s WHERE %s" % (src, " AND ".join(where)))
    if not r or not r[0] or r[0][0] == "":
        return None
    row = r[0] + [""] * (7 - len(r[0]))
    return {"count": int(row[0]), "sum": _num(row[1]), "min": _num(row[2]),
            "max": _num(row[3]), "avg": round(_num(row[4]), 2),
            "date_min": row[5], "date_max": row[6], "src": src_table}


# ----------------------------------------------------------------- 4. формулировка
ANSWER_SYS = """You answer an employee's question using ONLY the rows given to you.

Reply with JSON only, no text outside it:
{"text": "the answer for the user",
 "claims": {"total": number|null, "count": number|null, "max": number|null, "min": number|null}}

"claims" is where you state figures BY ROLE. Fill a role ONLY if that exact figure appears
in your "text" written in DIGITS; otherwise leave the role null. Never spell figures out in
words — a figure written in words cannot be checked and the answer will be discarded.
The figures given to you below are computed over every matching row — copy them, do not
recompute. Claims are checked against the database and a wrong claim discards your answer.

- Reply in the SAME language the question was asked in.
- Never invent numbers, dates or names that are not in the rows.
- If the rows do not answer the question, say plainly that there is no data.
- If a TOTAL is provided, it was computed over every matching row — use exactly that figure.
- Records are kept from the company's own point of view. What the company sells is what
  the counterparty buys, and what the company receives is what the counterparty supplied.
  Answer from the perspective the question takes instead of refusing over wording.
- Be short and businesslike, no preamble. Amounts as digits."""


def _split_answer(raw):
    """Разделить ответ модели на текст и заявленные величины."""
    m = re.search(r"\{.*\}", raw or "", re.S)
    if m:
        try:
            d = json.loads(m.group(0))
            if isinstance(d, dict) and "text" in d:
                return str(d.get("text") or "").strip(), (d.get("claims") or {})
        except ValueError:
            pass
    return (raw or "").strip(), {}


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
    body = "QUESTION: %s\n\nROWS FOUND (%d):\n%s" % (
        question, len(rows), "\n".join("- " + p for p in payload))
    if agg:
        body += "\n\nCOMPUTED OVER ALL MATCHING ROWS (use these exact figures, each in its own role):"
        body += "\n  count (number of records) = %d" % agg["count"]
        body += "\n  sum (TOTAL amount)        = %s" % _fmt(agg["sum"])
        body += "\n  max (largest single)      = %s" % _fmt(agg["max"])
        body += "\n  min (smallest single)     = %s" % _fmt(agg["min"])
        body += "\n  avg (average)             = %s" % _fmt(agg["avg"])
        if agg.get("date_min"):
            body += "\n  period                    = %s .. %s" % (agg["date_min"], agg["date_max"])
        body += "%s" % (
            "")
    return ds_chat([{"role": "system", "content": ANSWER_SYS},
                    {"role": "user", "content": body}], max_tokens=800)


# ----------------------------------------------------------------- 5. гейт (кодом)
# Разделитель разрядов — любой пробел, включая неразрывный и узкий. Но склеивать
# можно ТОЛЬКО правильные группы по три цифры: иначе «итого 10 20 30 шт» слипается
# в 102030, и три настоящих числа исчезают из проверки.
# Число может быть записано как угодно: «1 629 700», «1,629,700», «1.629.700»,
# «16,29,700». Разделитель разрядов — вопрос локали, а продукт коробочный. Поэтому
# токен разбирается во ВСЕ допустимые прочтения, и он считается обоснованным, если
# ХОТЯ БЫ ОДНО из них есть в данных. Прежняя версия читала «1,629,700» как 1.629
# и объявляла выдумкой весь правильный англоязычный ответ.
NUMTOK = re.compile(r"\d[\d  \u2009\u202f.,]*\d|\d")
SEP = "  \u2009\u202f,."
DATE3 = re.compile(r"\b(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})\b|\b(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})\b")
DATE2 = re.compile(r"\b(\d{1,2})[.\-/](\d{1,2})\b")


def _readings(tok):
    """Все осмысленные прочтения числового токена."""
    out = set()
    digits = re.sub(r"[^\d]", "", tok)
    if not digits:
        return out
    body = tok.strip(SEP)
    # 1) все разделители — групповые
    try:
        out.add(round(float(digits), 2))
    except ValueError:
        pass
    # 2) последний разделитель — десятичный, остальные групповые
    m = list(re.finditer(r"[%s]" % re.escape(SEP), body))
    if m:
        i = m[-1].start()
        head = re.sub(r"[^\d]", "", body[:i])
        tail = re.sub(r"[^\d]", "", body[i + 1:])
        if head and tail:
            try:
                out.add(round(float("%s.%s" % (head, tail)), 2))
            except ValueError:
                pass
    return {v for v in out} | {float(int(v)) for v in out if v == int(v)}


def _dates(text):
    """Даты как УПОРЯДОЧЕННЫЕ компоненты (день, месяц, год).

    Раньше сравнивались множества, и «09.12» с «12.09» были неразличимы — подменённая
    дата проходила. Год определяется по четырёхзначной записи, а не по позиции: это
    не зависит от того, в каком порядке его пишут в стране.
    """
    out, seen = [], []
    for m in DATE3.finditer(str(text or "")):
        if m.group(1):
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        else:
            d, mo, y = int(m.group(4)), int(m.group(5)), int(m.group(6))
        out.append((d, mo, y))
        seen.append(m.span())
    for m in DATE2.finditer(str(text or "")):
        if not any(a <= m.start() and m.end() <= b for a, b in seen):
            out.append((int(m.group(1)), int(m.group(2)), None))
    return out


def _date_spans(text):
    t = str(text or "")
    spans = [m.span() for m in DATE3.finditer(t)]
    for m in DATE2.finditer(t):
        if not any(a <= m.start() and m.end() <= b for a, b in spans):
            spans.append(m.span())
    return spans


def _tokens(text):
    """Числовые токены текста, вне дат: список множеств допустимых значений."""
    t = str(text or "")
    if not t:
        return []
    for a, b in sorted(_date_spans(t), reverse=True):
        t = t[:a] + " " * (b - a) + t[b:]
    return [r for r in (_readings(m.group(0)) for m in NUMTOK.finditer(t)) if r]


def _norm_numbers(text):
    """Все значения, которые встречаются в тексте (для белого списка по данным)."""
    out = set()
    for r in _tokens(text):
        out |= r
    return out


ROLE_TOL = 0.01          # копеечная погрешность форматирования


def check_claims(claims, agg):
    """Сверить ЗАЯВЛЕННЫЕ моделью величины с посчитанными в базе — по ролям.

    Это то, чего не умеет проверка «число встречается в данных»: сумма одной строки,
    названная итогом, ей неотличима от правды. Живой случай: три реализации на
    1 236 800 были поданы с итогом 925 000 — настоящим числом, но из другой роли.
    Теперь модель обязана назвать роль явно, а роль сверяется с базой.
    """
    if not agg or not isinstance(claims, dict):
        return True, []
    bad = []
    for role in ("total", "count", "max", "min"):
        v = claims.get(role)
        if v is None:
            continue
        try:
            v = float(v)
        except (TypeError, ValueError):
            bad.append("%s=?" % role)
            continue
        real = {"total": agg.get("sum"), "count": agg.get("count"),
                "max": agg.get("max"), "min": agg.get("min")}[role]
        if real is None or abs(v - float(real)) > ROLE_TOL:
            bad.append("%s: заявлено %s, в базе %s" % (role, _fmt(v), _fmt(real)))
    return (not bad), bad


def claims_in_text(claims, text):
    """Заявленная величина обязана присутствовать в тексте ЦИФРАМИ.

    Закрывает единственный класс выдумки, который гейт не видел: число, написанное
    СЛОВАМИ («два миллиона восемьсот тысяч»). Списка числительных в коде нет и быть не
    может — он был бы привязан к языку. Вместо этого требуем совпадения: раз модель
    заявила величину, пусть она стоит в тексте цифрами, а цифры мы уже умеем сверять.
    """
    if not isinstance(claims, dict):
        return True, []
    have = _norm_numbers(text)
    bad = []
    for role, v in claims.items():
        if v is None:
            continue
        try:
            fv = float(v)
        except (TypeError, ValueError):
            continue
        if fv not in have and round(fv, 2) not in have:
            bad.append("%s=%s названо не цифрами" % (role, _fmt(fv)))
    return (not bad), bad


def gate(answer, rows, agg):
    """Каждое число ответа обязано встречаться в данных, в итоге или в самом вопросе.

    Правило живёт в КОДЕ, а не в промте: промт — это пожелание, а не гарантия.
    Числа из вопроса НЕ разрешаются: «вопрос» приходит как аргумент инструмента,
    и составляет его модель бота — то есть проверяемый сам пополнял бы белый список.
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
    # Числа из ВОПРОСА в белый список больше не идут. Вопрос — это аргумент, который
    # сочиняет модель бота: она сама пополняла список того, что ей разрешено сказать,
    # и через это проходило любое выдуманное число.

    # Токен обоснован, если ХОТЯ БЫ ОДНО его прочтение есть в данных.
    bad = [sorted(r)[0] for r in _tokens(answer) if not (r & allowed)]

    # Даты: названная дата обязана совпасть с датой из данных ПОКОМПОНЕНТНО.
    known = []
    for r in rows:
        known += _dates(r[3]) + _dates(r[5])
    for d, mo, y in _dates(answer):
        ok = any(kd == d and kmo == mo and (y is None or ky is None or ky == y)
                 for kd, kmo, ky in known)
        # Двухкомпонентная запись без года неоднозначна: «10.5» — это и дата, и дробь.
        # Разрешаем, если такое ЧИСЛО есть в данных; выдуманное не пройдёт ни как дата,
        # ни как число.
        if not ok and y is None:
            ok = float("%d.%d" % (d, mo)) in allowed
        if not ok:
            bad.append("%02d.%02d%s" % (d, mo, "" if y is None else ".%d" % y))
    return (not bad), bad


# ----------------------------------------------------------------- HTTP
def answer(question):
    """Вопрос -> поиск в базе -> счёт в базе -> формулировка -> гейт.

    Порядок важен: сначала множество совпадений раскладывается по источникам ЦЕЛИКОМ,
    и только потом выбирается один источник и тянутся его строки. Обратный порядок
    (сперва top-N строк, потом группировка) терял целые таблицы.
    """
    t0 = time.time()
    intent = parse_intent(question, time.strftime("%Y-%m-%d"))
    preds = _predicates(intent)
    diag = {"terms": intent.get("terms"), "preds": preds, "kind": intent.get("kind")}

    exprs, kinds = probe(intent.get("terms") or [])
    diag["match_by"] = kinds
    match, k = match_expr(exprs, preds)
    diag["min_should_match"] = k if exprs else 0

    by = tables_of(match, preds)
    if not by and match:                       # слова не дали ничего — ищем по смыслу
        vec = _vec(question)
        near = psql("SELECT src_table, count(*) FROM (SELECT src_table FROM %s "
                    "ORDER BY array_cosine_similarity(emb, %s) DESC LIMIT %d) GROUP BY 1"
                    % (CORPUS, vec, TOPK))
        by = {r[0]: int(r[1]) for r in near if r and r[0]}
        match = ""
        diag["by_vector"] = True
    if not by:
        by = tables_of("", preds)
    if not by:
        return {"kind": "no_data", "text": NO_DATA_TEXT, "sources": [],
                "diag": dict(diag, sec=round(time.time() - t0, 2))}

    # Кандидаты — все источники витрины, а не только попавшие в выдачу: на вопросе
    # на другом языке нужная сущность в выдачу не попадает, и выбирать не из чего.
    try:
        cands = [r[0] for r in psql("SELECT src_table FROM %s" % TABLES)] or list(by)
    except RuntimeError:
        cands = list(by)
    src = pick_entity(question, intent.get("kind"), cands, by)
    if src not in by:
        # Модель назвала источник, куда поиск не попал: проверяем, есть ли там что-то
        # под наши условия, иначе остаёмся с тем, что реально нашлось.
        probe_rows = rows_of(src, match, preds, 1) if src else []
        if not probe_rows:
            src = max(by.items(), key=lambda kv: kv[1])[0]
    diag["focus"], diag["found"] = src, by.get(src, 0)

    rows = rows_of(src, match, preds, TOPK)
    if not rows:
        return {"kind": "no_data", "text": NO_DATA_TEXT, "sources": [],
                "diag": dict(diag, sec=round(time.time() - t0, 2))}

    agg = aggregate(src, match, preds)
    raw = compose(question, rows, agg)
    text, claims = _split_answer(raw)
    ok_roles, bad_roles = check_claims(claims, agg)
    ok_txt, bad_txt = claims_in_text(claims, text)
    ok_roles, bad_roles = (ok_roles and ok_txt), (bad_roles + bad_txt)
    ok_nums, bad_nums = gate(text, rows, agg)
    ok, bad = (ok_roles and ok_nums), (bad_roles + bad_nums)
    diag["claims"] = claims or None
    if not ok:
        sys.stderr.write("ask GATE: числа вне данных: %s\n" % bad[:6])
        if agg:
            text = TOTAL_TEXT.format(
                count=agg["count"],
                sum=("%d" % agg["sum"]) if agg["sum"] == int(agg["sum"])
                    else "%.2f" % agg["sum"])
        else:
            return {"kind": "no_data", "text": NO_DATA_TEXT, "sources": [],
                    "diag": dict(diag, gate_rejected=bad[:6])}

    tag = src.split("_", 1)[1] if "_" in src else src
    return {"kind": "answer", "text": text.strip(), "sources": [tag],
            "diag": dict(diag, rows=len(rows), sec=round(time.time() - t0, 2), gate_ok=ok)}


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
        # Fail-closed: без токена сервис не стартует (см. main), поэтому здесь
        # проверка безусловная. Раньше пустая переменная окружения молча открывала
        # доступ — та же дыра, что была у OData-шлюза.
        if self.headers.get("Authorization", "") != "Bearer " + ASK_TOKEN:
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
    if not ASK_TOKEN:
        sys.stderr.write("FATAL: ASK_TOKEN не задан — сервис без авторизации отдавал бы "
                         "данные витрины кому угодно. Задайте токен в окружении.\n")
        return 2
    srv = ThreadingHTTPServer((LISTEN_HOST, LISTEN_PORT), Handler)
    sys.stderr.write("serene-ask на http://%s:%d  (поиск в SereneDB, схема в модель не уходит)\n"
                     % (LISTEN_HOST, LISTEN_PORT))
    srv.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
