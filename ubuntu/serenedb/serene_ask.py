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
import csv
import io
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
# 🔴 РЕЗОЛВЕР ЧИТАЕТСЯ ОТДЕЛЬНОЙ РОЛЬЮ. `serene_ro`, которой исполняется SQL по данным,
# к `resolver_index` доступа НЕ имеет — это positive control: SQL, который пишет модель,
# не должен дотягиваться до служебных эмбеддингов. Резолвер спрашивает СИСТЕМА фиксированным
# запросом, поэтому у неё своя роль `serene_resolver`. Разойдётся — резолв просто отключится
# (лог, не падение): ответ без него хуже, но не неверен.
RESOLVER_DSN = os.environ.get("RESOLVER_DSN", "")
RESOLVER_PW = os.environ.get("RESOLVER_PW", "")
LISTEN_HOST = os.environ.get("ASK_LISTEN_HOST", "127.0.0.1")
LISTEN_PORT = int(os.environ.get("ASK_LISTEN_PORT", "8091"))
ASK_TOKEN = os.environ.get("ASK_TOKEN", "")

CORPUS, INDEX, TABLES = "search_corpus", "search_idx", "search_tables"
# Сколько символов перечня сущностей отдавать модели. Это бюджет КОНТЕКСТА МОДЕЛИ,
# а не порог правильности: он не зависит от базы и не подбирается под неё. Порядок
# перечня уже задан данными (близость метки сущности к тому, о чём спросили), поэтому
# граница режет ХВОСТ, а не смысл. Без границы перечень рос с числом сущностей: на
# 4585 типах это ~267 КБ в каждый вопрос.
PICK_BUDGET = int(os.environ.get("ASK_PICK_BUDGET_CHARS", "8000"))
# Сколько символов СТРОК отдавать модели. Это тоже бюджет контекста, а не решение о
# том, что важно в строке: бюджет делится между показанными строками поровну, а не
# режет каждую по фиксированной длине. Раньше здесь стояло «первые 320 символов
# строки» без единого слова обоснования — и замер показал, что у 12 контрагентов из
# 13 ИНН стоит на 367-м символе, КПП на 385-м. То есть данные доезжали до последнего
# шага целыми, а вопрос «какой ИНН у контрагента» получал «данных нет».
ROWS_BUDGET = int(os.environ.get("ASK_ROWS_BUDGET_CHARS", "24000"))
# Бюджеты ВРЕМЕНИ на отличительные реквизиты: сколько кандидатов считать и сколько
# термов показывать. Один расчёт ~50 мс. На правильность выбора не влияют — влияют
# на то, скольким кандидатам мы успеваем дать эту подсказку.
TERMS_FOR = int(os.environ.get("ASK_TERMS_FOR", "3"))
# Сколько потерянных сущностей называется поимённо в ответе о полноте. Это БЮДЖЕТ
# КОНТЕКСТА (п. 19), а не порог правильности: общее число потерянных строк и сущностей
# называется всегда и целиком, поимённый список ограничен, чтобы не расти с базой.
COVERAGE_TOP = int(os.environ.get("ASK_COVERAGE_TOP", "15"))
# Сверх этого возраста данных (сек) ответ несёт приписку о старении. По умолчанию
# час — заведомо больше цикла такта (~6 мин), то есть срабатывает только когда
# обновление реально встало (1С недоступна, такт падает), а не в норме.
STALE_WARN_SEC = int(os.environ.get("ASK_STALE_WARN_SEC", "3600"))
TERMS_TOP = int(os.environ.get("ASK_TERMS_TOP", "6"))
TOPK = int(os.environ.get("ASK_TOPK", "40"))
ROWS_TO_MODEL = int(os.environ.get("ASK_ROWS_TO_MODEL", "25"))

# Модель ранжирования — штатная функция движка, а не наша сортировка. Выбирается
# окружением, чтобы сравнивать варианты A/B на одном наборе вопросов, а не спорить.
#   bm25     — по умолчанию у движка (k1=1.2, b=0.75): штрафует длинные документы;
#   bm25_b0  — без нормализации по длине: строки документов длиннее строк справочников,
#              и штраф по длине систематически задвигает документы вниз;
#   tfidf    — классика без нормализации по длине.
#   lm_jm, lm_dirichlet, dfi — ещё три штатные модели движка (demo3 [5c,5d],
#              inverted_index_lm.test). Замерено 27.07 на нашем корпусе, запрос
#              «ромашка»: bm25 ставит первым РЕГИСТР (состоянияконтрагентов), а
#              bm25_b0, tfidf, lm_dirichlet и dfi — справочник контрагентов, то есть
#              верный ответ. Это и есть та самая болезнь: строки документов в 10 раз
#              длиннее строк справочников (334 символа против 33), и нормализация по
#              длине у bm25 систематически задвигает нужное вниз.
# ⛔ indri_dirichlet НЕ включена: [замер 27.07] в нашей сборке она в этой же форме
#              запроса молча отдаёт НОЛЬ строк, а в агрегате сообщает
#              «indri_dirichlet() requires an inverted index scan in the same
#              sub-query». Молчаливый пустой ответ опаснее ошибки — в список не берём.
# ⚠ Движок допускает ОДНУ модель ранжирования на инвертированный индекс
#              («Only one scorer function is allowed per inverted index»,
#              inverted_index_lm.test) — смешивать в одном скане нельзя, поэтому
#              выбор делается A/B на приёмочном наборе, а не «по ситуации».
SCORERS = {
    "bm25": "bm25(%s.tableoid)",
    "bm25_b0": "bm25(%s.tableoid, 1.2, 0.0)",
    "tfidf": "tfidf(%s.tableoid)",
    "lm_jm": "lm_jm(%s.tableoid)",
    "lm_dirichlet": "lm_dirichlet(%s.tableoid)",
    "dfi": "dfi(%s.tableoid)",
}
SCORER = os.environ.get("ASK_SCORER", "bm25")

# ВЕС ПОЛЯ ССЫЛОК. Поле `refs` собирается сборщиком из тех же кусков, что и `doc`
# («Контрагент: Ромашка» пишется в оба, serene_search_build.py:684-690), поэтому по
# термам refs ⊆ doc: добавление `OR refs @@ …` строк НЕ добавляет и не убирает.
# [замер 27.07] на двух терминах: doc=29/refs∪doc=29/в refs, но не в doc=0; то же
# 56/56/0. Меняется только ВЕС: строка, где слово стоит в ссылке на другой объект,
# поднимается над строкой, где оно попало в текст случайно. Ради этого поле и заводилось —
# чтобы «Контрагент: Ромашка» не был неотличим от «Склад: Ромашка».
# [замер] EXPLAIN: `Boost: 8` остаётся внутри Index Filter, скорер и Top: N по-прежнему
# уходят внутрь IRESEARCH_SCAN — план не портится.
# Штатность: веса полей — `cookbook/search/boosting.test`, `ranking.test:example_004`.
REFS_BOOST = os.environ.get("ASK_REFS_BOOST", "8.0")

# Упорядочивать ли перечень сущностей по близости метки к слову вопроса. Переключатель
# заведён, чтобы это можно было ЗАМЕРИТЬ, а не обсуждать: сам код в `pick_entity` уже
# признаёт сигнал негодным («эмбеддинг не связывает „продажи“ с „Реализация Товаров
# Услуг“ и ставит выше „Склады“»), и [замер 27.07] это подтвердился и на 1024:
# у «продажи» и у «sales» ближайшая метка — `catalog_склады`.
ORDER_BY_MEANING = os.environ.get("ASK_ORDER_BY_MEANING", "1") not in ("0", "false", "no")

# РЕРАНКЕР — модель, которая оценивает пару «вопрос ↔ название», а не расстояние между
# двумя векторами. Для сопоставления слова человека с названием сущности это и есть
# нужный инструмент, и п. 19 такую работу модели разрешает прямо: «сопоставить слово
# человека с названием в базе».
# [замер 27.07] на 226 названиях нашей базы: «продажи» → «Реализация Товаров Услуг»
# (0,585) первым, тогда как эмбеддинг метки ставил первым «Склады» (0,521). На «sales»
# реранкер даёт верное семейство, а правило «родитель раньше ребёнка» доворачивает на
# шапку документа.
# Честная оговорка: панацеей он не является — «сколько штук продано» он тоже не
# сопоставляет (первым идёт «Расходный Кассовый Ордер»), потому что нужного числа нет
# в корпусе вовсе (работа 3 в PRODUCTION_PLAN).
RERANK_URL = os.environ.get("ALIBABA_RERANK_URL",
                            "https://dashscope-intl.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank")
RERANK_MODEL = os.environ.get("ALIBABA_RERANK_MODEL", "qwen3-rerank")
# Сколько названий уходит в реранкер за один вопрос. Это БЮДЖЕТ КОНТЕКСТА, а не порог
# правильности: он не подбирается под базу и не зависит от неё. Без него объём, уходящий
# во внешнюю модель, рос бы с числом сущностей — прямое нарушение п. 19.
RERANK_TOP = int(os.environ.get("ASK_RERANK_TOP", "60"))

# У csv-разбора Python предел поля 128 КБ. Сборщик режет значения на 20 000 символов,
# но строка корпуса склеивается из многих значений и предел перекрывает, а падение
# было бы на редких длинных строках — то есть незаметным до клиента. Тот же лимит,
# что в сборщике (`serene_search_build.py`).
csv.field_size_limit(50 * 1024 * 1024)

DS_BASE = os.environ.get("DEEPSEEK_BASE", "https://api.deepseek.com").rstrip("/")
DS_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
# 🔴 PRO, А НЕ FLASH. Указание владельца 30.07: «не Флэш, а v4 pro».
# Почему это важно, а не вкус: выбор сущности и формулировка параметров подсчёта — задачи
# СМЫСЛОВЫЕ, и они целиком на модели (п. 19 разрешает ей ровно это). [замер 30.07] весь день
# приёмка мерилась на `deepseek-v4-flash` с выключенным размышлением, и главным остатком
# дефектов был именно выбор сущности — 10 провалов из 11. Замер на Flash не отвечает на
# вопрос «умеет ли система выбирать сущность», он отвечает «умеет ли это Flash».
# У провайдера доступны ровно два: `deepseek-v4-flash` и `deepseek-v4-pro`.
DS_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-pro")
DS_THINKING = os.environ.get("DEEPSEEK_THINKING", "disabled")

EMBED_URL = os.environ.get("ALIBABA_EMBED_URL", "").rstrip("/")
EMBED_KEY = os.environ.get("ALIBABA_API_KEY", "")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "text-embedding-v4")
# Размерность вектора. 1024 — это то, что отдаёт модель, а не наш выбор: корпус теперь
# эмбеддится ШТАТНОЙ функцией движка `ai_embed`, у которой параметра размерности нет и
# не нужно — длину определяет модель, а колонка объявляется под неё (`VECTOR_DECISION §6`).
# Прежние 1536 были взяты по образцу выведенного слоя braine, а не замером. Побочно:
# перебор читает 401 МБ вместо 602, то есть быстрее на треть.
# 🔴 Значение обязано совпадать с размерностью колонок `search_corpus.emb` и
# `search_tables.emb`. Разойдётся — сравнение векторов упадёт, а не ошибётся молча.
EMBED_DIM = int(os.environ.get("EMBED_DIM", "1024"))

# Единственные две строки, которые уходят человеку от НАС, а не от модели: ответ модели
# всегда на языке вопроса. Вынесены в окружение, чтобы локализовать без правки кода.
# Две строки, уходящие человеку не от модели. Умолчания НЕТ намеренно: русский текст
# по умолчанию — это настройка, которую обязан заполнить человек, знающий язык базы,
# то есть такой же дефект, как имя в коде. Когда переменные не заданы, ответ уходит
# структурой (kind + числа), а формулировку делает вызывающий на языке вопроса.
NO_DATA_TEXT = os.environ.get("ASK_NO_DATA_TEXT", "")
TOTAL_TEXT = os.environ.get("ASK_TOTAL_TEXT", "")


# ----------------------------------------------------------------- инфраструктура
def psql(sql):
    env = dict(os.environ)
    if PGPASSWORD:
        env["PGPASSWORD"] = PGPASSWORD
    # SQL идёт в stdin, а НЕ аргументом `-c`. У одного аргумента командной строки
    # жёсткий предел 131 072 байта, и запрос с перечислением кандидатов плюс вектором
    # вопроса (1536 чисел ≈ 14.6 КБ) его перекрывал. Замерено запуском: на 1712
    # сущностях ответ приходит, на 1713 — OSError «Argument list too long», и он не
    # RuntimeError, поэтому не ловился НИ ОДНОЙ защитой вокруг: сервис отдавал HTTP 500
    # на каждый вопрос. У сборщика этот путь через stdin с самого начала.
    # Разбор — CSV, а НЕ «строка вывода = запись». В комментарии, адресе доставки или
    # назначении платежа бывает перевод строки, и построчный разбор тогда рассыпает
    # колонки: обрывок текста становится ключом, а короткая строка роняет сервис.
    # [замер 27.07] запрос, вернувший из базы 40 строк, при разборе по `\n` давал 799
    # «строк», из них 759 короче шести полей, и первое же обращение к полю `doc` —
    # `IndexError: list index out of range`. В корпусе таких строк 4 009 по `doc`
    # и ещё 2 361 по `refs` — то есть падало на 4 % данных.
    # Починка не новая: ровно это уже сделано в сборщике (`serene_search_build.py:190`),
    # но при переходе на подачу SQL через stdin взяли `-F "\x1f"` вместо `--csv`, и
    # вторая починка затёрла первую. Здесь они сложены: и stdin, и `--csv`.
    try:
        # 🔴 `ON_ERROR_STOP=1` обязателен, и проверка кода возврата ниже без него
        # БЕСПОЛЕЗНА: psql завершается с нулём даже после ошибки SQL, отдав пустой вывод.
        # [замер 28.07] из-за этого ошибка запроса была неотличима от «ничего не нашлось»:
        # вопрос «Что покупало ООО Ромашка?» получал честный отказ при трёх найденных
        # документах и посчитанных итогах. Отказ при наличии данных — дефект (п. 21).
        p = subprocess.run(["psql", DSN, "-tA", "--csv", "-v", "ON_ERROR_STOP=1", "-f", "-"],
                           input=sql, capture_output=True, text=True, env=env)
    except OSError as e:
        raise RuntimeError("psql не запущен: %s" % str(e)[:160])
    if p.returncode != 0:
        raise RuntimeError((p.stderr or "psql failed")[:300])
    return [r for r in csv.reader(io.StringIO(p.stdout)) if r]


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


# 🔴 АРБИТР: ВЫБИРАЕТ ИЗ ГОТОВЫХ ОТВЕТОВ, А НЕ СОЧИНЯЕТ СВОЙ.
# Замысел владельца 30.07: «даём 2 ответа, и ллм просто должен прочесть вопрос или контекст…
# его задача просто выбрать из составленных ответов системы».
#
# Почему это лучше моих правил. Прежде выбор сущности решался по её НАЗВАНИЮ: «Приобретение
# Товаров Услуг» и «Корректировка Приобретения» по названию почти неразличимы, и оба
# независимых сигнала соглашались на неверном — [замер 30.07] «сколько приобретений товаров
# и услуг» отвечал то 249 (верно), то «3 корректировки, 152 800» (неверно), 2 раза из 3.
# Арбитр видит не названия, а ГОТОВЫЕ ОТВЕТЫ С ЧИСЛАМИ — «Всего найдено 249 документов
# приобретения товаров и услуг» против «Найдено 3 корректировок приобретения» — и это уже
# различимо языковым способом, без всякого знания конкретной базы.
#
# П. 19 соблюдён: арбитр НЕ считает и НЕ ищет. Числа посчитаны базой и уже стоят в ответах;
# он только сопоставляет вопрос человека с готовым текстом — чисто языковая задача.
#
# Запрет «не пересказывать» держится КОДОМ, а не просьбой в промте (правило владельца:
# «любые правила, основанные на промте, НЕ РАБОТАЮТ»): от арбитра принимается ТОЛЬКО номер.
# Всё, что не разбирается в номер из предложенного списка, считается «не выбрал», и тогда
# вопрос уходит человеку. Пересказать ответ он физически не может — его текст не попадает
# в выдачу ни при каком исходе.
def arbitrate(question, answers, context=""):
    """Номер ответа, который действительно отвечает на вопрос; None — не выбрал."""
    if len(answers) < 2:
        return 0 if answers else None
    listing = "\n\n".join("%d) %s" % (i + 1, a) for i, a in enumerate(answers))
    sys_msg = ("You are given a user question and several ready answers produced by a "
               "database system. The numbers in them are already computed and correct. "
               "Choose the ONE answer that actually answers the question that was asked. "
               "Do not rewrite, summarise or explain anything. "
               "Reply with a single digit: the number of the answer. "
               "If none of them answers the question, or two answer it equally well, "
               "reply 0.")
    user = ("%sQuestion: %s\n\nAnswers:\n%s\n\nNumber:"
            % (("Conversation so far:\n%s\n\n" % context[-2000:]) if context else "",
               question, listing))
    try:
        out = ds_chat([{"role": "system", "content": sys_msg},
                       {"role": "user", "content": user}], max_tokens=8)
    except Exception:                          # noqa: BLE001 — сеть/квота поставщика
        return None
    digits = "".join(ch for ch in (out or "") if ch.isdigit())[:2]
    if not digits:
        return None
    n = int(digits)
    if n == 0 or n > len(answers):             # «не выбрал» либо выдумал номер
        return None
    return n - 1


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
  "measure": "the word from the question naming WHICH quantity is asked about
             (money total, pieces, weight, price, …), in the question's own language.
             null if the question asks about no quantity",
  "kind":   "ALWAYS fill this: a short noun naming WHAT kind of records the question is
             about, in the question's own language. If the user used a verb, give the
             corresponding noun. Only null if the question names no kind of records at all",
  "about":  "\\"data\\" when the question asks about the company's records themselves —
             how many, how much, which ones. \\"coverage\\" when it asks about the SYSTEM's
             knowledge instead: what data is missing, what failed to load, what is closed
             by permissions, how complete or fresh the data is. Default to \\"data\\""
}

Rules:
- "terms" holds only VALUES that should literally appear in a record: names of parties,
  goods, places, document numbers. NEVER put the KIND of records there — that goes to
  "kind". A record about a bank in Moscow need not contain the word "bank".
- Group alternatives for the same concept together: expand abbreviations to their full
  form and add the inflections a record would realistically use. Example shape:
  [["Moscow", "MSK"], ["Acme"]] — matching is AND between groups, OR inside a group.
- Never invent concepts that are not in the question.
- want = "sum" when the user asks for a total of ANY quantity, not only money;
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
def _num_pred(intent, measure):
    """Условие по ЧИСЛУ — к названной величине, а не к единственной колонке.

    Величина известна только после выбора сущности (её имена лежат в самих данных),
    поэтому числовое условие отделено от датного: датное работает на отборе сущностей,
    числовое — уже внутри выбранной.
    """
    a = (intent or {}).get("amount") or {}
    op, v, v2 = a.get("op"), a.get("value"), a.get("value2")
    if not (op and v is not None and measure):
        return []
    m = "map_extract(nums, %s)[1]" % lit(measure)
    if op == "between" and v2 is not None:
        return ["%s BETWEEN %s AND %s" % (m, float(v), float(v2))]
    if op in (">", "<", ">=", "<="):
        return ["%s %s %s" % (m, op, float(v))]
    return []


def _predicates(intent):
    """Условия по дате — предикаты по INCLUDE-колонке индекса.

    Числовых условий здесь БОЛЬШЕ НЕТ: строка несёт все свои величины картой, и какая
    из них имеется в виду, зависит от вопроса и от сущности. Смешивать нельзя —
    «больше 500000» у документа про сумму, а у строки накладной могло бы оказаться
    про количество.
    """
    out = []
    p = intent.get("period") or {}
    if p.get("from"):
        out.append("doc_date >= %s" % lit(p["from"]))
    if p.get("to"):
        out.append("doc_date < (%s::date + INTERVAL 1 day)" % lit(p["to"]))
    return out


def _fetch(match_sql, preds, order, limit):
    where = [w for w in ([match_sql] + preds) if w]
    src = INDEX if match_sql else CORPUS
    # 🔴 РАЗДЕЛИТЕЛЬ РАВЕНСТВА ОБЯЗАТЕЛЕН. `ORDER BY … LIMIT` без него делает ОТВЕТ
    # невоспроизводимым: у равных оценок порядок задаётся ходом исполнения, а `LIMIT`
    # отрезает по этому порядку — в модель уезжают РАЗНЫЕ строки при одном и том же
    # вопросе и неизменных данных. [замер 30.07] один вопрос пять раз: дважды ответ
    # «невозможно», трижды верные 73 181 157,68. Это `techContext` ловушка 30, уже
    # укусившая сборку корпуса; здесь она кусала ответы.
    return psql(
        "SELECT row_key, src_table, 0, coalesce(doc_date::date::text,''), "
        "       %s AS s, doc FROM %s%s ORDER BY s DESC, src_table, row_key LIMIT %d"
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
                # фраза с окном — 9. Окно берём по самой фразе: сколько слов между
                # краями, столько и допускаем. Константа здесь означала бы «наши имена
                # такой длины» — на языке с длинными оборотами фраза перестаёт находиться.
                variants.append(("slop", "ts_phrase(%s, ARRAY[0,%d], %s)"
                                 % (lit(words[0]), len(words) - 1, lit(words[-1]))))
            # Расстояние опечатки — от длины слова, а не фиксированное. При 2 на слове из
            # трёх букв совпадает половина корпуса: замерено, 'tax' -> 2978 строк из
            # 97 085 при нуле точных. На кириллице не проявлялось только потому, что
            # значимые слова длинные.
            variants += [("fuzzy", "ts_levenshtein(%s, %d)"
                          % (lit(alt), min(2, len(alt) // 4))),
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
    # РЕЗОЛВЕР — ФОЛЛБЭК ДЛЯ ГРУПП БЕЗ СОВПАДЕНИЯ. Если слово не нашлось ни точно, ни по
    # опечатке, ни подстрокой — оно записано в базе иначе (сокращение, разговорное имя).
    # Спрашиваем резолвер: слово -> конкретные значения базы, и ищем уже по ним, точной
    # фразой. Срабатывает ТОЛЬКО там, где буквальный поиск дал ноль, поэтому на работающие
    # вопросы не влияет — у них совпадение есть. Резолвленное значение видно в ответе:
    # человек проверит, то ли слово поняли.
    for gi, group in enumerate(groups):
        if gi in per_group:
            continue                           # уже нашлось буквально — резолвить нечего
        vals = []
        for alt in group:
            vals = resolve_values(alt)
            if vals:
                break
        if vals:
            exprs = ["ts_phrase(%s)" % lit(v) for v in vals]
            per_group[gi] = (0, exprs, "resolved")
            diag.setdefault("_resolved", {})[gi] = vals

    out = []
    for gi in sorted(k for k in per_group):
        rank, exprs, kind = per_group[gi]
        out.append(exprs[0] if len(exprs) == 1 else "ts_any([%s])" % ", ".join(exprs))
        if kind != "resolved":
            diag[gi] = kind
    return out, diag


def with_refs(expr):
    """Искать по строке И по полю ссылок, ссылкам — вес.

    Множество строк от этого не меняется (см. REFS_BOOST): `refs` собран из тех же
    кусков, что и `doc`. Меняется порядок: совпадение в ссылке на другой объект весит
    больше случайного совпадения в тексте. Поле было построено и проиндексировано ровно
    ради этого, но в отборе не участвовало ни разу — платили за него и не пользовались.
    """
    return "(doc @@ %s OR refs @@ (%s ^ %s))" % (expr, expr, REFS_BOOST)


def match_expr(exprs, preds):
    """Собрать условие поиска с ГРАДИЕНТОМ: сперва все понятия, потом мягче.

    `ts_any(массив, k)` — «не меньше k из N». Прежний обрыв «всё → любое» на вопросе
    «поступления от ООО ТехноСнаб» давал либо ноль, либо всё, где есть «ООО».
    """
    n = len(exprs)
    if not n:
        return "", 0
    if n == 1:
        return with_refs(exprs[0]), 1
    # Один запрос вместо цикла по k: ts_compound(must, must_not, should, k) — штатный
    # булев запрос движка (замерено: 6.9 мс против 42.5 мс у цикла из трёх шагов).
    # Градиент сохраняем данными: берём наибольшее k, при котором есть совпадения.
    # Здесь СЧИТАЕМ, а не ранжируем, поэтому вес ссылок не нужен: множество строк у
    # `doc @@ X` и у `doc @@ X OR refs @@ (X^N)` одно и то же (замер в REFS_BOOST),
    # а лишний терм в запросе — лишняя работа на каждом из n шагов градиента.
    counts = psql(" UNION ALL ".join(
        "SELECT %d k, count(*) FROM %s WHERE %s" % (
            k, INDEX, " AND ".join(
                ["doc @@ ts_compound(NULL, NULL, [%s], %d)" % (", ".join(exprs), k)]
                + preds))
        for k in range(n, 0, -1)))
    best = 1
    for r in counts:
        try:
            if int(r[1]) > 0:
                best = max(best, int(r[0]))
        except (ValueError, IndexError):
            continue
    return with_refs("ts_compound(NULL, NULL, [%s], %d)" % (", ".join(exprs), best)), best


def children_by_parent(by, match, preds):
    """Табличные части сущностей, в которых нашлись совпадения (п. 3, п. 21).

    🔴 ЗАЧЕМ. Бот отвечал по ОДНОЙ сущности и не умел связывать их между собой. Всё, что
    лежит в табличной части, оказывалось недостижимо: [замер 28.07] на «какие товары мы
    продали ООО Ромашка» система перечисляла ДОКУМЕНТЫ И СУММЫ, а не товары — ответ
    выглядел уверенно и отвечал не на тот вопрос, что хуже отказа. Сами товары лежали
    рядом, в `…_товары`, 76 строк.

    Почему поиск их не находил: имя контрагента стоит в ШАПКЕ, в строках товаров его нет,
    поэтому по словам вопроса они не совпадают никогда и в кандидаты не попадают.

    Связь берётся СТРУКТУРНО, а не по именам: `parent` посчитан при сборке по составному
    ключу (`$metadata` объявляет ключ табличной части как ссылка на владельца + номер
    строки), а ключ строки-потомка начинается с ключа шапки. Отсюда отбор:
    «строки потомка, чей владелец попал в совпадения». Считает база, одним запросом.
    """
    if not by or not match:
        return {}, {}
    parents = [t for t in by if by.get(t)]
    if not parents:
        return {}, {}
    try:
        rs = psql("SELECT src_table, parent FROM %s WHERE parent IN (%s)"
                  % (TABLES, ", ".join(lit(p) for p in parents)))
    except RuntimeError:
        return {}, {}
    pred_by = {}
    for r in rs:
        if not r or not r[0]:
            continue
        pred_by[r[0]] = ("split_part(row_key, '|', 1) IN (SELECT row_key FROM %s "
                         "WHERE src_table = %s AND %s)" % (INDEX, lit(r[1]), match))
    if not pred_by:
        return {}, {}
    # ОДИН запрос на все табличные части, а не по запросу на каждую: число обращений к
    # базе не должно расти с числом сущностей (п. 20).
    parts = " UNION ALL ".join(
        "SELECT %s AS t, count(*) AS n FROM %s WHERE src_table = %s AND %s"
        % (lit(c), CORPUS, lit(c), pred) for c, pred in pred_by.items())
    out = {}
    try:
        for r in psql(parts):
            try:
                if int(r[1]) > 0:
                    out[r[0]] = int(r[1])
            except (ValueError, IndexError):
                continue
    except RuntimeError:
        return {}, {}
    return out, {c: pred_by[c] for c in out}


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


def rows_of(src_table, match, preds, limit, measure=None):
    """Строки одного источника: САМА строка, а рядом — подсветка совпадения.

    Раньше модели уходила ТОЛЬКО подсветка. Она по устройству отдаёт фрагменты вокруг
    совпавших слов, а не строку: замерено — 144 символа при длине строки 398. Реквизит,
    оказавшийся дальше от совпадения, до модели не доходил вовсе. Живая проверка: ИНН
    контрагента стоит на 367-м символе, вопрос «какой ИНН у Дон-Агро» получал ответ
    «данных нет» при том, что значение есть и в витрине, и в корпусе, и в индексе.
    Подсветка остаётся — она показывает, ГДЕ совпало, — но данные берутся из строки.
    """
    where = [w for w in ([match] + preds) if w] + ["src_table = %s" % lit(src_table)]
    src = INDEX if match else CORPUS
    frag = ("ts_highlight(doc, 'MaxWords=14,MaxFragments=2,StartSel=[,StopSel=]') "
            "|| ' | ' || doc" if match else "doc")
    order = ((SCORERS.get(SCORER, SCORERS["bm25"]) % INDEX) + " DESC") if match \
        else (("map_extract(nums, %s)[1] DESC NULLS LAST" % lit(measure)) if measure
              else "row_key")
    return psql(
        "SELECT row_key, src_table, coalesce(%s,0), coalesce(doc_date::date::text,''), "
        "       0 AS s, %s FROM %s WHERE %s ORDER BY %s LIMIT %d"
        % (("map_extract(nums, %s)[1]" % lit(measure)) if measure else "NULL::DOUBLE",
           frag, src, " AND ".join(where), order + ", row_key", limit))


PICK_SYS = """You map a user's question to a record type.

You get the question and a numbered list of record types that exist in this database.
Answer with the NUMBER only — the type whose records would ANSWER the question.
If the question genuinely fits SEVERAL types and the answers would be DIFFERENT — the
asker could reasonably have meant either — answer with their numbers separated by a
comma (at most three). Do that only for real ambiguity, not for uncertainty: if one
type clearly answers the question better, give that one number.
Some entries list what is typical for their records — the attributes that set them
apart from the rest of the database. Use them to tell apart types whose names sound
alike: they describe what the records actually are about.
Entries marked as line items are the rows INSIDE another record: a question about a
total, a sum or "how much in all" belongs to the record that owns them, not to the rows.
Some entries show how many records already match the question; prefer a type that
actually has matches over a same-sounding one that has none.
If none of them fits, answer 0.
Judge by meaning, across languages and wording: a question about sales belongs to the
type that records sales even if the words differ.

Then state WHAT has to be computed. Reply with one JSON object and nothing else:
  {"types": [numbers], "quantity": "<exact name from that entry's list, or null>",
   "compute": "count" | "sum" | "max" | "min" | "avg"}
Rules for these fields:
- "quantity" MUST be copied character for character from the "quantities recorded here"
  list of the type you chose. Never invent a name, never translate it, never reshape it.
  Use null when the question asks how MANY records there are rather than about a value.
- "compute" is what the question asks for: how many records -> "count"; a total or
  "how much in all" -> "sum"; the largest/smallest -> "max"/"min"; the average -> "avg".
- If the type you chose has no quantity that the question is about, still name the type
  and put null: the system will ask the user rather than guess."""


def signal_terms(src_table, match, top):
    """Чем ЭТОТ источник отличается от базы в целом — по его совпадениям.

    Штатный рецепт движка (cookbook/search/significant-terms.test): частота терма в
    подмножестве против ожидаемой по фону. Считаем по полю `refs` — это ссылки на
    другие объекты, их словарь в шесть раз меньше словаря всей строки (11 744 против
    71 604 термов) и в пять раз дешевле при том же разделении.

    Зачем: два источника могут иметь ОДИНАКОВОЕ число совпадений по имени контрагента,
    и выбирать модели не из чего. Отличительные реквизиты дают ей то, чего нет в
    названии: у реализации это склад и расчёты с покупателями, у поступления на счёт —
    банк и счёт организации. Это данные из индекса, а не правило в подсказке.
    """
    where = " AND ".join([w for w in [match, "src_table @@ %s" % lit(src_table)] if w])
    try:
        rs = psql(
            "WITH bg AS (SELECT unnest(ts_dict_agg(refs)) t, unnest(ts_dict_count(refs)) b"
            "            FROM %(i)s),"
            "     fg AS (SELECT unnest(ts_dict_agg(refs)) t, unnest(ts_dict_count(refs)) f"
            "            FROM %(i)s WHERE %(w)s),"
            "     n  AS (SELECT (SELECT count(*) FROM %(i)s WHERE %(w)s) ft,"
            "                   (SELECT count(*) FROM %(i)s) bt)"
            " SELECT fg.t FROM fg JOIN bg USING (t) CROSS JOIN n"
            " ORDER BY fg.f - bg.b * n.ft::DOUBLE / nullif(n.bt,0) DESC LIMIT %(k)d"
            % {"i": INDEX, "w": where, "k": top})
    except RuntimeError:
        return []
    return [r[0] for r in rs if r and r[0]]


CLARIFY_SYS = """The question can be answered from several kinds of records, and the
answers would differ. Ask the person ONE short question to find out which they meant.

Rules:
- Ask in the SAME language the question was asked in.
- Describe each option in plain business words, using its name and what is typical for
  its records. Never show table names, codes or internal identifiers.
- One sentence, no preamble, no apology. End with a question mark."""


def clarify_text(question, opts):
    """Уточняющий вопрос формулирует МОДЕЛЬ — на языке спрашивающего.

    Своей прозой это писать нельзя: она была бы на одном языке независимо от языка
    вопроса (тот же дефект, что и с русскими умолчаниями ответа). Данные для фразы
    уже посчитаны — названия источников и их отличительные реквизиты, — выдумывать
    модели нечего.
    """
    body = "Question: %s\n\nOptions:\n" % question + "\n".join(
        "- %s%s" % (o["label"],
                    "" if not o["distinct_by"] else " (typical: %s)" % o["distinct_by"])
        for o in opts)
    try:
        return (ds_chat([{"role": "system", "content": CLARIFY_SYS},
                         {"role": "user", "content": body}], max_tokens=120) or "").strip()
    except Exception:                          # noqa: BLE001 — сеть/квота
        return ""                              # вызывающий сформулирует сам по options


# Формулировка нарочно НЕ говорит «данных нет»: этот же отказ уходит и там, где данные
# есть и посчитаны, а не прошла проверку формулировка модели. Сказать «нет данных» в
# таком случае — соврать клиенту.
REFUSE_SYS = """The system could not produce a verified answer to the user's question.
Write ONE short sentence, in the SAME LANGUAGE as the question, saying that a verified
answer to it cannot be given right now. State no facts, no figures, no reasons, no
apologies. Reply with that sentence only."""


def refuse_text(question):
    """Отказ формулирует МОДЕЛЬ — на языке спрашивающего.

    Пункт 18 `TARGET.md`: при отказе бот обязан СКАЗАТЬ, что не может ответить, а не
    промолчать. Раньше здесь уходила пустая строка, и клиент видел пустоту — замерено
    на вопросах «какие дополнительные условия продажи есть» и «покажи статистические
    показатели» (гейт зарубал формулировку модели, а сказать об этом было некому).

    Своей прозой писать нельзя: она была бы на одном языке независимо от языка вопроса —
    тот же дефект, что и русские умолчания ответа (п. 9). Модель здесь ничего не решает
    и не считает: ей нечего выдумывать, потому что данных ей не дают вовсе (п. 19).

    Цифры из отказа вырезаются КОДОМ, а не просьбой в промте: любая цифра в отказе —
    это уже утверждение о данных, а «правила на промте не работают».
    """
    if not question:
        return ""
    try:
        t = (ds_chat([{"role": "system", "content": REFUSE_SYS},
                      {"role": "user", "content": question}], max_tokens=60) or "").strip()
    except Exception:                          # noqa: BLE001 — сеть/квота поставщика
        return ""                              # модель недоступна — формулирует вызывающий
    return "" if _norm_numbers(t) else t


def rerank(query, docs):
    """Упорядочить названия по близости к вопросу — моделью-реранкером.

    Возвращает порядок индексов. Пусто — значит не получилось, и вызывающий остаётся
    на прежнем порядке: отсутствие сигнала не должно превращаться в отказ (п. 21).
    """
    if not query or not docs or not EMBED_KEY:
        return []
    body = json.dumps({"model": RERANK_MODEL,
                       "input": {"query": query, "documents": docs},
                       "parameters": {"return_documents": False, "top_n": len(docs)}}).encode()
    req = urllib.request.Request(RERANK_URL, data=body, method="POST")
    req.add_header("Authorization", "Bearer " + EMBED_KEY)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            out = json.loads(r.read())["output"]["results"]
        return [int(x["index"]) for x in out]
    except Exception:                          # noqa: BLE001 — сеть/квота поставщика
        return []


def _resolver_psql(sql):
    """Запрос к резолверу — ОТДЕЛЬНОЙ ролью `serene_resolver`. Не через общий `psql`:
    та роль (`serene_ro`) к `resolver_index` доступа не имеет по замыслу. Ошибка (нет
    настроек, роль недоступна) гасится в пустой список — резолв отключается, а не роняет
    ответ (п. 21)."""
    if not RESOLVER_DSN:
        return []
    env = dict(os.environ)
    if RESOLVER_PW:
        env["PGPASSWORD"] = RESOLVER_PW
    try:
        p = subprocess.run(["psql", RESOLVER_DSN, "-tA", "--csv", "-v", "ON_ERROR_STOP=1", "-f", "-"],
                           input=sql, capture_output=True, text=True, env=env)
    except OSError:
        return []
    if p.returncode != 0:
        sys.stderr.write("resolver query failed: %s\n" % (p.stderr or "")[:160])
        return []
    return [r for r in csv.reader(io.StringIO(p.stdout)) if r]


RESOLVE_NEAR = int(os.environ.get("ASK_RESOLVE_NEAR", "12"))
RESOLVE_KEEP = int(os.environ.get("ASK_RESOLVE_KEEP", "3"))


def resolve_values(term):
    """Слово человека -> конкретные значения в базе («Питер» -> «Санкт-Петербург»).

    🔴 ЭТО РЕЗОЛВЕР. Он закрывает класс вопросов, где спрошенное слово в данных записано
    ИНАЧЕ и ни точным совпадением, ни опечаткой, ни подстрокой не находится: сокращение,
    разговорное имя, другой падеж основы. [замер 28.07] «Питер» подстрокой даёт 0, а в
    базе 180 записей про Санкт-Петербург.

    Механизм — тот же, что везде в проекте: близость считает БАЗА (вектор значения к
    вектору слова, `emb <=> vec`), а какой из близких верен, решает РЕРАНКЕР. Порога
    близости НЕТ и быть не может: «то же это слово или нет» — вопрос языковой. Реранкер
    уже используется для выбора сущности; здесь та же роль.

    Границы (п. 19): смотрим не больше `RESOLVE_NEAR` ближайших и оставляем не больше
    `RESOLVE_KEEP` — объём во внешнюю модель не растёт с размером базы.
    """
    try:
        vec = _vec(term)
    except Exception:                          # noqa: BLE001 — эмбеддер недоступен
        return []
    near = _resolver_psql(
        "SELECT DISTINCT value FROM resolver_index ORDER BY emb <=> %s, value LIMIT %d"
        % (vec, RESOLVE_NEAR))
    vals = [r[0] for r in near if r and r[0]]
    if not vals:
        return []
    # 🔴 ГАРДА ОТ РАЗРЕШЕНИЯ В МУСОР. Вектор ВСЕГДА отдаёт ближайшее, а реранкер всегда
    # даёт порядок — поэтому у значения, которого в базе НЕТ, они находят случайное:
    # [замер 28.07] «SanDisk» (нет в данных) разрешался в коды занятий «5920», и ответ
    # уходил про «уличных торговцев». Оценка реранкера не спасает (мусору давал 0.55 при
    # 0.67 у верного). Признак структурный и без порога: слово человека и значение базы
    # обязаны делить кусочек букв — «Питер»/«Петербург» делят «тер», а «SanDisk»/«5920» —
    # ничего. Работает на любом языке: это буквы, а не список синонимов.
    keep = [v for v in vals if _shares_chars(term, v)]
    if not keep:
        return []
    order = rerank(term, keep)
    picked = [keep[i] for i in order[:RESOLVE_KEEP]] if order else keep[:RESOLVE_KEEP]
    return picked


def _ngrams(s, n=3):
    s = re.sub(r"[^0-9a-zа-яё]", "", (s or "").lower())
    if len(s) < n:
        return {s} if s else set()
    return {s[i:i + n] for i in range(len(s) - n + 1)}


def _shares_chars(term, value):
    """Слово и значение делят хотя бы один буквенный триграмм (или одно — подстрока
    другого). Структурная проверка «это то же слово, пусть и искажённое», без списка
    синонимов и без числового порога."""
    t = re.sub(r"[^0-9a-zа-яё]", "", (term or "").lower())
    v = re.sub(r"[^0-9a-zа-яё]", "", (value or "").lower())
    if not t or not v:
        return False
    if t in v or v in t:
        return True
    return bool(_ngrams(term) & _ngrams(value))


def measures_of(src_table):
    """Какие величины есть у сущности — ИЗ ДАННЫХ, а не из кода.

    Имена величин — это имена числовых колонок 1С, попавшие в строку корпуса. Список
    короткий (величины ОДНОЙ сущности), поэтому его можно показать модели, не нарушая
    п. 19: он не растёт с размером базы.
    """
    try:
        return [r[0] for r in psql(
            "SELECT DISTINCT u.k FROM %s, unnest(map_keys(nums)) AS u(k) "
            "WHERE src_table = %s AND nums IS NOT NULL ORDER BY 1"
            % (CORPUS, lit(src_table))) if r and r[0]]
    except RuntimeError:
        return []


def totals_of(src_table, match, preds, measures):
    """Итоги ПО КАЖДОЙ величине сущности — одним запросом.

    Нужно там, где вопрос величину не называет («что покупало ООО Ромашка»). Заставлять
    выбирать одну в таком случае нельзя: [замер 28.07] реранкер на таком вопросе выбрал
    `НомерЧекаККМ` — номер чека вместо суммы. Отдаём модели ВСЕ итоги с именами, пусть
    берёт подходящий; каждое число всё равно сверяется гейтом с базой.

    Размер ограничен природой данных: величин у сущности единицы (у нас максимум 12), и
    их число не растёт с размером базы — п. 19 соблюдён.
    """
    if not measures:
        return []
    where = [w for w in ([match] + preds + ["src_table = %s" % lit(src_table)]) if w]
    src = INDEX if match else CORPUS
    # По каждой величине — итог, наибольшее и наименьшее. Иначе вопрос «какая самая
    # крупная продажа» отвечать нечем: величину он не называет, а максимум ему нужен.
    cols = ", ".join(
        "coalesce(sum(map_extract(nums, %(m)s)[1]),0), count(map_extract(nums, %(m)s)[1]), "
        "coalesce(max(map_extract(nums, %(m)s)[1]),0), coalesce(min(map_extract(nums, %(m)s)[1]),0)"
        % {"m": lit(m)} for m in measures)
    try:
        r = psql("SELECT %s FROM %s WHERE %s" % (cols, src, " AND ".join(where)))
    except RuntimeError:
        return []
    if not r or not r[0]:
        return []
    row = r[0]
    out = []
    for i, m in enumerate(measures):
        b = 4 * i
        if b + 3 < len(row) and int(row[b + 1] or 0) > 0:
            out.append((m, _num(row[b]), _num(row[b + 2]), _num(row[b + 3])))
    return out


def pick_measure(src_table, question, word):
    """Какую величину считать — решается ПО ВОПРОСУ.

    🔴 Здесь больше нет понятия «деньги». Прежде сборщик выбирал одну колонку на
    сущность и объявлял её суммой; из-за этого на «сколько ШТУК продано» отвечать было
    нечем — количества в корпусе не существовало (работа 3 в PRODUCTION_PLAN). Замечание
    владельца 28.07: «это не универсально, базы разные бывают».
    Теперь строка несёт все свои величины, а сопоставить слово человека с именем
    величины — языковая задача, и её делает модель (п. 19). Список имён короткий и
    приходит из данных.
    """
    names = measures_of(src_table)
    if not names:
        return (None, [], 'none')
    if not word:
        # Вопрос не называет величину — НЕ выбираем за него. Иначе получается
        # «что покупало Ромашка» → `НомерЧекаККМ`. Итоги по всем величинам отдадим
        # модели отдельно (`totals_of`).
        return (None, [], 'none')
    if len(names) == 1:
        return (names[0], [], 'single')        # выбора нет — и спрашивать не о чем
    # Имя величины ТОЧНО совпало со словом вопроса — брать его, не гадая реранкером.
    # «сумма» → «Сумма», а не «СуммаНУDr»: точное совпадение сильнее близости.
    wl = word.lower()
    exact = [n for n in names if n.lower() == wl]
    if exact:
        return (exact[0], [], 'exact')
    # 🔴 НЕСКОЛЬКО ВЕЛИЧИН ОДИНАКОВО ПОДХОДЯТ — ЭТО ВОПРОС ЧЕЛОВЕКУ, А НЕ ЗАДАЧА РЕРАНКЕРУ.
    # Указание владельца 30.07: «давать юзеру неверный ответ — самое страшное, что мы можем
    # сделать. лучше 1, 2, 3 раза уточнить, если непонятно, чем дать не то».
    # [замер 30.07] у `document_приобретениетоваровуслуг` слово «сумма» несут ЧЕТЫРЕ
    # величины: СуммаДокумента, СуммаВзаиморасчетов, СуммаВзаиморасчетовПоЗаказу,
    # СуммаВзаиморасчетовПоТаре. Реранкер выбирал молча и ошибался: на выбранной человеком
    # сущности ответ дал 71 045 277,59 вместо 73 181 157,68 — сущность верная, величина нет.
    # Отбор здесь — ПОДСТРОКА имени величины, то есть само слово человека против имён из
    # данных: ни списка слов, ни порога, работает на любом языке и любой конфигурации.
    same = [n for n in names if wl in n.lower()]
    if len(same) > 1:
        # Базовая величина снимает неоднозначность, если её частные виды — её же префиксы
        # (правило ниже): тогда спрашивать не о чем. Иначе — спрашиваем.
        base_of = [n for n in same
                   if sum(1 for m in same if m != n and m.startswith(n)) >= len(same) - 1]
        if len(base_of) == 1 and base_of[0].lower() != wl:
            return (base_of[0], [], 'base')
        return (None, sorted(same), 'ask')
    if len(same) == 1:
        return (same[0], [], 'substring')
    idx = rerank(word, names)
    ranked = [names[i] for i in idx] if idx else names
    # БАЗОВАЯ ВЕЛИЧИНА ПРЕДПОЧТИТЕЛЬНЕЕ УТОЧНЁННОЙ, когда слово общее. У регистра бухучёта
    # величины вложены: «Сумма» — база, «СуммаВРDr»/«СуммаНУCr» — её частные виды (разницы,
    # налоговый учёт, дебет/кредит). Имя базы — ПРЕФИКС имён частных, это структурный факт,
    # а не список. На «обороты»/«сумма» реранкер путался и брал частный вид — [замер 28.07]
    # «обороты» → «СуммаВРDr». Если верхний по рангу — частный вид, а его база тоже в
    # списке и в вопросе нет её уточнителя, берём базу.
    top = ranked[0]
    base = next((n for n in names if n != top and top.startswith(n)
                 and sum(1 for m in names if m != n and m.startswith(n)) >= 2), None)
    if base and base.lower() not in wl:
        qualifier = top[len(base):].lower()
        if qualifier and qualifier not in wl:
            return (base, [], 'base')
    return (top, [], 'rerank')


def pick_entity(question, kind, cands, counts=None, match="", cut=None):
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
        # 🔴 ДЛИНА ВЫХОДА ОДНА НА ВСЕ ВЕТКИ. [замер 30.07] этот выход остался двухместным
        # после добавления плана, и на вопросе с единственным кандидатом сервис отдал 503
        # (`not enough values to unpack`). Отказ честный (п. 18 сработал), но это дефект.
        return (cands[:1], {}, {})
    try:
        rs = psql("SELECT src_table, label, parent FROM %s WHERE src_table IN (%s)"
                  % (TABLES, ", ".join(lit(c) for c in cands)))
    except RuntimeError:
        return ([], {}, {})
    # ПОРЯДОК КАНДИДАТОВ ОБЯЗАН СОХРАНИТЬСЯ. `IN (...)` возвращает строки в порядке
    # хранения, а не в порядке списка — и смысловой порядок, посчитанный выше, молча
    # терялся. Модель тяготеет к началу списка, поэтому она получала 226 названий
    # вперемешку. Замерено: «сколько всего мы продали» выбирало регистр бухучёта
    # зарплаты, «продажи за декабрь» — календарные графики.
    label_by = {r[0]: r[1] for r in rs if r and r[0]}
    # `parent` определён при сборке ПО КОНТРАКТУ метаданных: у табличной части ключ
    # составной (ссылка на владельца + номер строки), а сам владелец найден по данным.
    # Это структурный факт, который модели неоткуда узнать из названия.
    parent_by = {r[0]: (r[2] if len(r) > 2 else "") for r in rs if r and r[0]}
    names = [(c, label_by[c]) for c in cands if c in label_by]
    if len(names) < 2:
        return ([names[0][0]] if names else [], {}, {})
    # Рядом с названием — СКОЛЬКО СОВПАДЕНИЙ там нашлось. Это данные, а не схема, и
    # именно они снимают неоднозначность: справочник «Банки» на 1 запись и
    # «Классификатор Банков» на 680 по названию неразличимы, по числу — очевидны.
    counts = counts or {}
    # Отличительные реквизиты считаем ТОЛЬКО верхним кандидатам: каждый расчёт стоит
    # ~50 мс, и это бюджет времени ответа, а не порог правильности — порядок уже задан
    # данными, поэтому счёт идёт для тех, между кем модель и выбирает.
    # ВЕЛИЧИНЫ КАНДИДАТА — рядом с его названием. Без них модель выбирала сущность, у
    # которой нужной величины нет вовсе: [замер 28.07] «сколько штук товара продано»
    # выбирало шапку документа и сопоставляло «штук» с `СуммаДокумента`, потому что
    # количества у шапки не существует — оно лежит в табличной части. Названия величин
    # приходят ИЗ ДАННЫХ (`map_keys(nums)`), а не из кода, и считаются ОДНИМ запросом
    # только для верхних кандидатов: это бюджет контекста, а не порог правильности.
    meas = {}
    if len(names) > 1:
        top = [t for t, _ in names[:TERMS_FOR * 4]]
        try:
            for r in psql(
                "SELECT src_table, string_agg(DISTINCT u.k, ', ' ORDER BY u.k) FROM %s, "
                "unnest(map_keys(nums)) AS u(k) WHERE nums IS NOT NULL AND src_table IN (%s) "
                "GROUP BY 1" % (CORPUS, ", ".join(lit(t) for t in top))):
                if r and r[0] and len(r) > 1 and r[1]:
                    meas[r[0]] = r[1][:160]
        except RuntimeError:
            meas = {}

    # 🔴 ЗНАНИЕ О СУЩНОСТИ В ЭТОТ ПЕРЕЧЕНЬ НЕ ВСТАВЛЯЕТСЯ — ПРОВЕРЕНО И ОТКЛОНЕНО.
    # Я попробовал показывать модели рядом с названием слова, которыми люди спрашивают об этой
    # сущности (`search_entity_alias`). [замер 30.07, 3 повтора на вопрос] стало ХУЖЕ: верных
    # 2 из 12 против 5 без вставки, и во ВСЕХ прогонах пропал план параметров подсчёта
    # (`план=None`) — удлинившийся перечень сбил шаг, который до того давал верную величину.
    # Выбор сущности при этом улучшился («на какую сумму закупили» — верный документ 3 раза из
    # 3), но ценой потери величины, то есть в сумме хуже.
    #
    # Вторая причина, важнее замера: устройство. Владелец 30.07: «wiki нужно только для
    # ПЕРЕФРАЗИРОВАНИЯ, а не для точного поиска. вопрос — перефразирование по wiki, поиск через
    # нашу систему — переспрашиваем, если необходимо — ответ». То есть знание о названиях
    # работает ДО нас, в шаге перефразирования у бота (`ubuntu/openclaw/instance/AGENTS.md`), а
    # сюда приходит вопрос, уже названный словами базы. Дублировать это знание в наш промт
    # значит держать два места правды.
    marks = {}
    if match and len(names) > 1:
        raw = {}
        for t, _nm in names[:TERMS_FOR]:
            tt = signal_terms(t, match, TERMS_TOP)
            if tt:
                raw[t] = tt
        # Терм, который есть у ВСЕХ рассмотренных кандидатов, ничего не различает —
        # это само искомое имя и общие коды. Убираем: подсказка должна нести только
        # то, чем источники ОТЛИЧАЮТСЯ. Отбор по данным, без списка слов в коде.
        common = set.intersection(*(set(v) for v in raw.values())) if len(raw) > 1 else set()
        for t, tt in raw.items():
            uniq = [x for x in tt if x not in common]
            if uniq:
                marks[t] = ", ".join(uniq)
    lines_out, used = [], 0
    for i, (t, nm) in enumerate(names):
        row = "%d. %s%s%s%s%s" % (
            i + 1, nm,
            "" if t not in counts else " — %d matching records" % counts[t],
            "" if not parent_by.get(t) else
            " [line items of «%s»]" % label_by.get(parent_by[t], parent_by[t]),
            "" if t not in meas else "\n     quantities recorded here: %s" % meas[t],
            "" if t not in marks else "\n     typical for these records: %s" % marks[t])
        if used + len(row) > PICK_BUDGET and lines_out:
            # П. 13 TARGET.md: обрезал — покажи это КЛИЕНТУ, а не в журнале. Раньше
            # запись уходила только в stderr, и 11-12 сущностей из 226 не доходили до
            # выбора на КАЖДОМ вопросе, а спрашивающий об этом не знал. Сам бюджет
            # снимать нельзя — перечень рос бы с числом сущностей базы (п. 19).
            sys.stderr.write("ask: перечень сущностей обрезан по бюджету промпта "
                             "(%d из %d, порядок по смыслу)\n" % (len(lines_out), len(names)))
            if cut is not None:
                cut["entities_shown"] = len(lines_out)
                cut["entities_total"] = len(names)
            break
        lines_out.append(row)
        used += len(row) + 1
    names = names[:len(lines_out)]
    listing = "\n".join(lines_out)
    ask_text = question if not kind else "%s (%s)" % (question, kind)
    try:
        raw = ds_chat([{"role": "system", "content": PICK_SYS},
                       {"role": "user", "content": "%s\n\nTypes:\n%s" % (ask_text, listing)}],
                      max_tokens=120)
    except Exception as e:                     # noqa: BLE001 — сеть/квота
        # Не молча: выбор сущности — решение, влияющее на правильность ответа. Если
        # модель недоступна, вызывающий обязан узнать об этом и пометить ответ, а не
        # тихо взять «источник, где больше совпадений».
        sys.stderr.write("ask DEGRADED: выбор сущности без модели (%s)\n" % str(e)[:80])
        raise RuntimeError("entity-pick-unavailable")
    # Модель может назвать несколько типов — тогда вопрос неоднозначен, и правильный
    # ход не угадывать за человека, а спросить его. Возвращаем список: один элемент —
    # выбор сделан, несколько — нужно уточнение.
    # 🔴 МОДЕЛЬ ФОРМУЛИРУЕТ ПАРАМЕТРЫ, СЧИТАЕТ КОД. Замысел владельца 30.07: «сначала
    # сформулировать, какие именно параметры вытягивать для подсчёта, а потом уже из них
    # включается калькулятор».
    #
    # Зачем это лучше прежнего. Прежде модель отдавала ТОЛЬКО номер типа, а величину потом
    # угадывал реранкер по похожести имён — уже НЕ ВИДЯ вопроса. Отсюда [замер 30.07]
    # «на какую сумму мы закупили» при верно выбранной сущности давало 70 902 572,21
    # (`Сумма` строк, без НДС) вместо 73 181 157,68 (`СуммаДокумента`): имя похоже, смысл
    # другой. Теперь величину называет тот, кто читал вопрос.
    #
    # П. 19 соблюдён: модель не считает и не ищет — она описывает, ЧТО посчитать. Считает
    # база, число подставляет код.
    #
    # 🔴 ПАРАМЕТРЫ ПРОВЕРЯЮТСЯ ПО ДАННЫМ, А НЕ ПРИНИМАЮТСЯ НА СЛОВО. Имя величины обязано
    # существовать у выбранной сущности (`measures_of`), иначе оно отбрасывается и система
    # спрашивает человека. Запрет держится кодом, а не просьбой в промте: выдуманное имя
    # физически не может дойти до калькулятора.
    plan = {}
    txt = (raw or "").strip()
    try:
        j = json.loads(txt[txt.index("{"):txt.rindex("}") + 1])
        if isinstance(j, dict):
            got = [int(x) for x in (j.get("types") or []) if str(x).strip().isdigit()]
            q = j.get("quantity")
            if isinstance(q, str) and q.strip():
                plan["quantity"] = q.strip()
            c = (j.get("compute") or "").strip().lower()
            if c in ("count", "sum", "max", "min", "avg"):
                plan["compute"] = c
        else:
            got = []
    except (ValueError, KeyError, TypeError):
        # Не JSON — остаёмся на прежнем разборе: номера типов из текста. Отсутствие
        # параметров не должно ронять ответ (п. 21), просто величину выберем как раньше.
        got = [int(x) for x in re.findall(r"\d+", txt)]
    picked = [names[i - 1][0] for i in got if 1 <= i <= len(names)]
    if picked and plan.get("quantity"):
        # Имя величины — только из данных ЭТОЙ сущности. Иначе выбрасываем.
        if plan["quantity"] not in measures_of(picked[0]):
            plan["quantity_rejected"] = plan.pop("quantity")
    return ([], marks, plan) if not picked else (picked, marks, plan)


def _vec(text):
    return "'[" + ",".join("%.6f" % x for x in embed_one(text)) + "]'::FLOAT[%d]" % EMBED_DIM


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def aggregate(src_table, match, preds, measure=None):
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
    # Величина названа по имени из данных. Нет величины — нет и агрегатов: пустой
    # результат честнее нуля, потому что ноль неотличим от «посчитано и получилось 0».
    m = ("map_extract(nums, %s)[1]" % lit(measure)) if measure else "NULL::DOUBLE"
    r = psql("SELECT count(*), coalesce(sum(%(m)s),0), coalesce(min(%(m)s),0), "
             "       coalesce(max(%(m)s),0), coalesce(avg(%(m)s),0), "
             "       coalesce(min(doc_date)::date::text,''), "
             "       coalesce(max(doc_date)::date::text,''), "
             "       count(%(m)s) "
             "FROM %(src)s WHERE %(w)s"
             % {"m": m, "src": src, "w": " AND ".join(where)})
    if not r or not r[0] or r[0][0] == "":
        return None
    row = r[0] + [""] * (8 - len(r[0]))
    # count_amount отдельно от count: avg/sum посчитаны по строкам с суммой, и модель
    # обязана знать, по скольким. Иначе среднее по 31 строке уходит как среднее по 1344.
    return {"count": int(row[0]), "sum": _num(row[1]), "min": _num(row[2]),
            "max": _num(row[3]), "avg": round(_num(row[4]), 2),
            "date_min": row[5], "date_max": row[6],
            "count_amount": int(row[7] or 0), "src": src_table,
            "measure": measure}


# ----------------------------------------------------------------- 4. формулировка
ANSWER_SYS = """You answer an employee's question using ONLY the rows given to you.

Reply with JSON only, no text outside it:
{"text": "the answer for the user",
 "ask": "one clarifying question, or null",
 "claims": {"total": number|null, "count": number|null, "max": number|null, "min": number|null}}

"ask" is the middle road between answering and giving up. Fill it ONLY when the rows do
not answer exactly what was asked, but they DO answer a closely related question about
the same subject — a different direction of the same relation, a different period, a
different role of the same party. Then put in "text" what the rows DO show, and in "ask"
a single short question that would let you answer precisely. Do not ask when the rows
answer the question — answer it. Do not ask when the rows are unrelated — say there is
no data. Never ask about our database, tables or fields: ask about the person's intent,
in their own words.

🔴 NEVER WRITE A COMPUTED FIGURE YOURSELF. Not as digits, not in words, not even by
copying it from the figures below. Write a PLACEHOLDER instead, and the exact value will
be substituted by the system:

  {total}  {count}  {max}  {min}  {avg}  {date_min}  {date_max}

When several quantities are given by name, address one of them: {total:NAME},
{max:NAME}, {min:NAME} — NAME exactly as given below.

Example: "Sold for {total} across {count} documents, the largest being {max}."

Values that appear INSIDE a row — a document number, a tax id, a party's name, the date
of one specific record — you copy verbatim from the rows. Those are quotations, not
arithmetic. The distinction: anything computed over several rows is a placeholder,
anything read from one row is copied.

"claims" — leave every role null. It exists only for compatibility and is ignored.

- Reply in the SAME language the question was asked in — "ask" too.
- Never invent numbers, dates or names that are not in the rows.
- If the rows do not answer the question and nothing close to it, say plainly that there
  is no data. Silence is the last resort, not the first.
- When the question is about an amount or a quantity over several records, state the
  computed total with {total} — listing the records one by one instead of giving the
  total is not an answer to "how much in all". List them in addition to it, not instead.
- Be short and businesslike, no preamble."""


def _split_answer(raw):
    """Разделить ответ модели на текст и заявленные величины.

    🔴 Служебная обёртка НЕ ДОЛЖНА доезжать до человека. [замер 27.07] когда модель
    отвечает почти-JSON-ом (скобки есть, разбор падает), прежняя версия отдавала клиенту
    сырую строку целиком: в ответе про поставщика наружу уходило
    `{"text":":"В предоставленных данных нет информации…`. Это видно клиенту, значит
    дефект (п. 13), и чинится кодом, а не просьбой в промте отвечать правильным JSON.
    """
    raw = raw or ""
    m = re.search(r"\{.*\}", raw, re.S)
    if m:
        try:
            d = json.loads(m.group(0))
            if isinstance(d, dict) and "text" in d:
                return str(d.get("text") or "").strip(), (d.get("claims") or {})
        except ValueError:
            pass
    if '"text"' in raw:
        # Достаём поле текста из поломанной обёртки. Не вышло — отдаём пусто, и дальше
        # включается честный отказ: пустота лучше служебного мусора, а отказ лучше
        # пустоты (п. 18, п. 21).
        m2 = re.search(r'"text"\s*:\s*"?:?\s*"?(.*?)(?:"\s*,\s*"claims"|"\s*\}|\}\s*$)',
                       raw, re.S)
        if m2:
            return (m2.group(1).strip().strip('"').replace('\\"', '"')
                    .replace("\\n", " ").strip()), {}
        return "", {}
    if raw.lstrip().startswith("{"):
        return "", {}
    return raw.strip(), {}


SLOT = re.compile(r"\{([a-z_]+)(?::([^}]+))?\}")


def _fill_figures(text, agg, totals, has_measure=True):
    """Подставить посчитанные базой числа на места, оставленные моделью.

    🔴 ЭТО ЗАМЕНА ПРОВЕРКИ УСТРОЙСТВОМ. Прежде модель писала число сама, а гейт ловил её
    за руку, сверяя каждую цифру с данными. Указание владельца 28.07: «нужен просто
    калькулятор для чисел, а не сложные системы».

    Разница не в объёме кода, а в том, что становится возможным. При проверке неверное
    число возможно и лишь отлавливается — а всякая проверка ошибается в обе стороны, и
    [замер 28.07] эта ошиблась дважды за день, уронив ВЕРНЫЕ ответы: сперва из-за функции
    ранжирования, потом склеив «36, 4» в несуществующее 36.4. При подстановке неверное
    число невозможно: модель его физически не пишет. Это то же правило проекта, что и
    везде, — «запреты держатся кодом, а не промтом», доведённое до конца.

    Возвращает (текст, список нераспознанных мест). Непустой список — отказ формулировки,
    а не тихая замена на пустоту: место, которому нечего подставить, означает, что модель
    сослалась на величину, которой мы не считали.
    """
    if not text:
        return text, []
    known = dict(agg or {})
    # 🔴 БЕЗ ВЫБРАННОЙ ВЕЛИЧИНЫ БЕЗЫМЯННОЕ МЕСТО НЕ ЗАПОЛНЯЕТСЯ. Когда вопрос не назвал,
    # какую величину считать, `agg` считает по пустому месту и его `sum` равен нулю.
    # [замер 28.07] на «какие поступления были от ООО ТехноСнаб» ответ так и вышел:
    # «Общая сумма поступлений — 0 руб.» при настоящих 2 088 800. Ноль — такое же неверное
    # число, как любое другое, и подстановка кодом сама по себе от него не спасает:
    # спасает только отказ подставлять там, где считать было нечего.
    # Итоги по каждой величине при этом есть — они адресуются по имени, `{total:ИМЯ}`.
    if not has_measure:
        for k in ("sum", "max", "min", "avg"):
            known.pop(k, None)
    by_name = {}
    for m, v, mx, mn in (totals or []):
        by_name[m] = {"total": v, "max": mx, "min": mn}
    bad = []

    def one(mt):
        role, name = mt.group(1), mt.group(2)
        if name:
            got = by_name.get(name.strip(), {}).get(role)
        else:
            got = known.get({"total": "sum"}.get(role, role))
        if got is None:
            # В отказе называем ДОСТУПНЫЕ имена: вторая попытка должна знать, чем
            # заменить, иначе она повторит ту же ошибку.
            bad.append("%s (есть: %s)" % (mt.group(0), ", ".join(sorted(by_name)) or "нет")
                       if not name else mt.group(0))
            return mt.group(0)
        if role in ("date_min", "date_max"):
            return str(got)
        # Вид числа теперь наш, а не модели: разряды разделяем НЕРАЗРЫВНЫМ пробелом.
        # Обычный пробел переносится по строке и рвёт число пополам, а гейт разбирает
        # оба одинаково ([замер] `NUMTOK` включает U+00A0).
        out = _fmt(got)
        head, _, frac = out.partition(".")
        neg, head = (head[0] == "-"), head.lstrip("-")
        grouped = "\u00a0".join(
            [head[:len(head) % 3 or 3]] + [head[i:i + 3] for i in
                                           range(len(head) % 3 or 3, len(head), 3)])
        return ("-" if neg else "") + grouped + ("." + frac if frac else "")

    return SLOT.sub(one, text), bad


def _ask_back(raw):
    """Уточняющий вопрос модели, если она его задала.

    Отдельной функцией, а не третьим членом кортежа `_split_answer`: у того пять путей
    возврата, и добавлять элемент в каждый — способ ошибиться на ровном месте. Здесь
    отсутствие поля и поломанная обёртка дают одно и то же — пусто, то есть «не спросила».
    """
    m = re.search(r"\{.*\}", raw or "", re.S)
    if not m:
        return ""
    try:
        d = json.loads(m.group(0))
    except ValueError:
        return ""
    return str((d.get("ask") if isinstance(d, dict) else "") or "").strip()


def compose(question, rows, agg, corrections=None, totals=None, coverage=None):
    payload = []
    shown = rows[:ROWS_TO_MODEL]
    # Бюджет делится на число показываемых строк: короткие строки не занимают чужого
    # места, длинные не режутся по произвольной границе.
    per_row = max(320, ROWS_BUDGET // max(1, len(shown)))
    for r in shown:
        head = r[5][:per_row]
        tail = []
        if _num(r[2]):
            tail.append("amount=%s" % ("%d" % _num(r[2]) if _num(r[2]) == int(_num(r[2]))
                                       else "%.2f" % _num(r[2])))
        if r[3]:
            tail.append("date=%s" % r[3])
        payload.append(head + ((" | " + " | ".join(tail)) if tail else ""))
    body = "QUESTION: %s\n\nROWS FOUND (%d):\n%s" % (
        question, len(rows), "\n".join("- " + p for p in payload))
    has_money = bool(agg) and (agg.get("sum") or agg.get("max") or agg.get("min"))
    if agg and not has_money:
        # Денежной колонки у этой сущности нет. Передать sum=0 нельзя: модель ответит
        # «0», и гейт согласится — ноль ведь посчитан. Отсутствие суммы и сумма,
        # равная нулю, — разные вещи, и путать их нельзя.
        body += "\n\nCOMPUTED OVER ALL MATCHING ROWS: count = %d" % agg["count"]
        body += ("\n  (no numeric quantity matches the question for this record type — "
                 "do not state any figure other than the count)")
    elif agg:
        body += ("\n\nCOMPUTED OVER ALL MATCHING ROWS for the quantity «%s» "
                 "(use these exact figures, each in its own role):" % (agg.get("measure") or "-"))
        body += "\n  count (number of records) = %d" % agg["count"]
        body += "\n  sum (TOTAL)               = %s" % _fmt(agg["sum"])
        body += "\n  max (largest single)      = %s" % _fmt(agg["max"])
        body += "\n  min (smallest single)     = %s" % _fmt(agg["min"])
        body += "\n  avg (average)             = %s" % _fmt(agg["avg"])
        if agg.get("date_min"):
            body += "\n  period                    = %s .. %s" % (agg["date_min"], agg["date_max"])
        body += "%s" % (
            "")
    if totals:
        # Итоги по каждой величине — с ИМЕНАМИ из базы. Модель сама возьмёт подходящую
        # под вопрос; выдумать она их не может, а гейт всё равно сверит с данными.
        body += ("\n\nCOMPUTED OVER ALL MATCHING ROWS, by quantity name "
                 "(total / largest single / smallest single):")
        for m, v, mx, mn in totals:
            body += "\n  %s: total = %s, max = %s, min = %s" % (m, _fmt(v), _fmt(mx), _fmt(mn))
    if coverage:
        # НЕПОЛНОТА ЭТОЙ СУЩНОСТИ. Модель обязана предупредить на языке вопроса — сами мы
        # приписать не можем: своя фраза была бы на одном языке независимо от вопроса.
        # Числа отсюда разрешены гейту явно, поэтому предупреждение не будет отвергнуто
        # как выдумка.
        body += ("\n\nDATA COMPLETENESS WARNING: this kind of records is INCOMPLETE in "
                 "the search: %d rows exist in the source system, %d reached the search, "
                 "%d are missing (%s). The figures above are computed over what reached "
                 "the search only. You MUST warn the user about this in your answer, in "
                 "their language, stating the number of missing rows in digits."
                 % (coverage["in_1c"], coverage["in_search"], coverage["missing"],
                    coverage.get("reason") or "reason unknown"))
    if corrections:
        # ВТОРАЯ ПОПЫТКА. Первая формулировка не прошла проверку кодом — говорим модели,
        # что именно не сошлось, и требуем опираться только на посчитанные базой числа.
        # Это не «правило на промте»: результат второй попытки проверяется тем же
        # гейтом, что и первой. Смысл — не поверить модели, а дать ответу дойти до
        # клиента, если он есть (решение владельца 27.07).
        body += ("\n\nYOUR PREVIOUS ANSWER WAS REJECTED BY A VERIFIER: %s"
                 "\nAnswer again. Use ONLY the computed figures above, each in its own "
                 "role. If a figure is not given above, do not state it at all."
                 # Причины отказа приходят из двух источников: ролевые проверки дают
                 # строки, а `gate` — сами необоснованные ЧИСЛА. Склеивать надо через
                 # str(): [замер] иначе `TypeError: expected str instance, float found`
                 # и HTTP 500 на любом вопросе с порогом суммы.
                 % "; ".join(str(c) for c in corrections))
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
# \ud83d\udd34 \u0417\u0430 \u0437\u0430\u043f\u044f\u0442\u043e\u0439 \u0438\u043b\u0438 \u0442\u043e\u0447\u043a\u043e\u0439 \u041e\u0411\u042f\u0417\u0410\u041d\u0410 \u0438\u0434\u0442\u0438 \u0446\u0438\u0444\u0440\u0430. \u041f\u0440\u0435\u0436\u0434\u0435 \u043a\u043b\u0430\u0441\u0441 \u0441\u0438\u043c\u0432\u043e\u043b\u043e\u0432 \u0434\u043e\u043f\u0443\u0441\u043a\u0430\u043b \u0438 \u043f\u0440\u043e\u0431\u0435\u043b,
# \u0438 \u0437\u0430\u043f\u044f\u0442\u0443\u044e \u0432\u043f\u0435\u0440\u0435\u043c\u0435\u0448\u043a\u0443, \u043f\u043e\u044d\u0442\u043e\u043c\u0443 \u00ab\u043d\u0430\u0439\u0434\u0435\u043d\u043e 36, 4 \u043e\u0442\u0441\u0443\u0442\u0441\u0442\u0432\u0443\u044e\u0442\u00bb \u0441\u043a\u043b\u0435\u0438\u0432\u0430\u043b\u043e\u0441\u044c \u0432 \u043e\u0434\u043d\u043e \u0447\u0438\u0441\u043b\u043e
# 36.4 \u2014 \u043a\u043e\u0442\u043e\u0440\u043e\u0433\u043e \u043c\u043e\u0434\u0435\u043b\u044c \u043d\u0435 \u043f\u0438\u0441\u0430\u043b\u0430, \u2014 \u0438 \u0433\u0435\u0439\u0442 \u043e\u0442\u0432\u0435\u0440\u0433\u0430\u043b \u0412\u0415\u0420\u041d\u042b\u0419 \u043e\u0442\u0432\u0435\u0442 \u0446\u0435\u043b\u0438\u043a\u043e\u043c.
# [\u0437\u0430\u043c\u0435\u0440 28.07] \u043f\u0440\u0435\u0434\u0443\u043f\u0440\u0435\u0436\u0434\u0435\u043d\u0438\u0435 \u043e \u043d\u0435\u043f\u043e\u043b\u043d\u043e\u0442\u0435 \u0434\u0430\u043d\u043d\u044b\u0445 \u043d\u0435 \u043c\u043e\u0433\u043b\u043e \u0434\u043e\u0439\u0442\u0438 \u0434\u043e \u043a\u043b\u0438\u0435\u043d\u0442\u0430 \u043d\u0438 \u0440\u0430\u0437\u0443:
# \u043e\u043d\u043e \u0432\u0441\u0435\u0433\u0434\u0430 \u0441\u0442\u0430\u0432\u0438\u0442 \u0434\u0432\u0430 \u0447\u0438\u0441\u043b\u0430 \u0440\u044f\u0434\u043e\u043c \u0447\u0435\u0440\u0435\u0437 \u0437\u0430\u043f\u044f\u0442\u0443\u044e. \u041e\u0442\u0432\u0435\u0440\u0433\u043d\u0443\u0442\u044b\u0439 \u0432\u0435\u0440\u043d\u044b\u0439 \u043e\u0442\u0432\u0435\u0442 \u2014 \u0434\u0435\u0444\u0435\u043a\u0442
# \u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0438, \u0430 \u043d\u0435 \u043e\u0441\u0442\u043e\u0440\u043e\u0436\u043d\u043e\u0441\u0442\u044c (\u043f. 21).
# \u0417\u0430\u043f\u044f\u0442\u0430\u044f \u0441 \u043f\u0440\u043e\u0431\u0435\u043b\u043e\u043c \u043d\u0435 \u044f\u0432\u043b\u044f\u0435\u0442\u0441\u044f \u0434\u0435\u0441\u044f\u0442\u0438\u0447\u043d\u044b\u043c \u0440\u0430\u0437\u0434\u0435\u043b\u0438\u0442\u0435\u043b\u0435\u043c \u043d\u0438 \u0432 \u043e\u0434\u043d\u043e\u0439 \u0437\u0430\u043f\u0438\u0441\u0438 \u0447\u0438\u0441\u0435\u043b:
# \u00ab36,4\u00bb \u043f\u0438\u0448\u0443\u0442 \u0441\u043b\u0438\u0442\u043d\u043e, \u00ab36, 4\u00bb \u2014 \u044d\u0442\u043e \u043f\u0435\u0440\u0435\u0447\u0438\u0441\u043b\u0435\u043d\u0438\u0435.
NUMTOK = re.compile(r"\d(?:[ \u00a0\u2007\u2009\u202f\u200b']\d|[.,]\d|\d)*")
SEP = "  \u00a0\u2007\u2009\u202f\u200b',."
DATE3 = re.compile(r"\b(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})\b|\b(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})\b")
DATE2 = re.compile(r"\b(\d{1,2})[.\-/](\d{1,2})\b")


def _readings(tok):
    """Все осмысленные прочтения числового токена."""
    out = set()
    digits = re.sub(r"[^\d]", "", tok)
    if not digits:
        return out
    body = tok.strip(SEP)
    # 1) все разделители — групповые. Только если группировка ПРАВИЛЬНАЯ: первая группа
    # 1-3 цифры, каждая следующая ровно 3. Иначе «10 20 30» читалось как 102030, а
    # «18860000.00» — как 1886000000, и белый список гейта содержал каждое настоящее
    # значение, умноженное на сто. Проверено прогоном: сумма x100 проходила гейт.
    groups = [g for g in re.split(r"[%s]" % re.escape(SEP), body) if g != ""]
    grouped_ok = (len(groups) == 1
                  or (1 <= len(groups[0]) <= 3
                      and all(len(g) == 3 for g in groups[1:])))
    if grouped_ok:
        try:
            out.add(round(float(digits), 2))
        except ValueError:
            pass
    # 2) последний разделитель — десятичный, остальные групповые.
    # ТОЛЬКО если чтение как разрядов не подошло: иначе «3 500 000» получал лишнее
    # прочтение 3500.0, и выдуманный итог заземлялся числом 3500 из данных —
    # то есть ответ, завышенный в тысячу раз, проходил гейт.
    m = [] if grouped_ok else list(re.finditer(r"[%s]" % re.escape(SEP), body))
    if m:
        i = m[-1].start()
        head = re.sub(r"[^\d]", "", body[:i])
        tail = re.sub(r"[^\d]", "", body[i + 1:])
        # Целая часть обязана быть корректно сгруппированной. Иначе «10 20 30 шт»
        # прочиталось бы как 1020.3 — три настоящих числа слиплись бы в одно
        # выдуманное, и честный ответ отвергался бы.
        hg = [g for g in re.split(r"[%s]" % re.escape(SEP), body[:i]) if g != ""]
        head_ok = (len(hg) == 1
                   or (1 <= len(hg[0]) <= 3 and all(len(g) == 3 for g in hg[1:])))
        if head and tail and head_ok:
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
    out = []
    for m in NUMTOK.finditer(t):
        tok = m.group(0)
        body = tok.strip(SEP)
        groups = [g for g in re.split(r"[%s]" % re.escape(SEP), body) if g != ""]
        # СНАЧАЛА читаем токен целиком: _readings знает и разряды, и десятичную часть.
        # Раньше здесь стояла своя, более узкая проверка «каждая группа ровно 3 цифры»,
        # и она срабатывала ДО _readings — поэтому «1 629 700,00» рассыпалось на
        # 1 / 629 / 700 / 0, а правильный ответ объявлялся выдумкой и подменялся
        # шаблоном. Любая сумма с разрядами И копейками (английская, немецкая,
        # французская, бразильская запись) отвергалась; наша база спасалась только
        # тем, что суммы целые. Разбиение осталось запасным путём для перечислений.
        whole = _readings(tok)
        if whole:
            out.append(whole)
        else:
            # Не группировка, а просто перечисление рядом: «10 20 30 шт». Каждое число —
            # самостоятельный токен, иначе три настоящих числа превращались в одно
            # выдуманное и честный ответ отвергался.
            for g in groups:
                r = _readings(g)
                if r:
                    out.append(r)
    return out


def _norm_numbers(text):
    """Все значения, которые встречаются в тексте (для белого списка по данным)."""
    out = set()
    for r in _tokens(text):
        out |= r
    return out


ROLE_TOL = 0.01          # копеечная погрешность форматирования


def check_claims(claims, agg, totals=None):
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
        # Когда вопрос величину не назвал, единственного агрегата нет — считаны итоги
        # ПО КАЖДОЙ величине. Роль тогда сверяется с любой из них: «наибольшая продажа»
        # это max величины `СуммаДокумента`, и число обязано совпасть именно с ним, а не
        # с чем попало в данных. [замер 28.07] без этого верный ответ 1 629 700 отвергался
        # с формулировкой «в базе 0», потому что сверять было не с чем.
        if role in ("total", "max", "min") and totals:
            i = {"total": 1, "max": 2, "min": 3}[role]
            if any(abs(v - float(t[i])) <= ROLE_TOL for t in totals):
                continue
        if real is None or abs(v - float(real)) > ROLE_TOL:
            bad.append("%s: заявлено %s, в базе %s" % (role, _fmt(v), _fmt(real)))
    return (not bad), bad


ASKED_ROLE = {"sum": "total", "count": "count"}


def claims_in_text(claims, text, want=None):
    """Величина, О КОТОРОЙ СПРОСИЛИ, обязана стоять в тексте цифрами.

    Закрывает единственный класс выдумки, который гейт не видел: число, написанное
    СЛОВАМИ («два миллиона восемьсот тысяч»). Списка числительных в коде нет и быть не
    может — он был бы привязан к языку. Вместо этого требуем совпадения: раз модель
    ответила на вопрос про сумму, пусть сумма стоит в тексте цифрами, а цифры мы уже
    умеем сверять.

    🔴 Проверяется ТОЛЬКО запрошенная величина, а не все заявленные. Решение владельца
    27.07: «надо же дать ответ, если он есть. а так выходит, что если данные есть, но по
    нашей системе мы их не отдали, мы не отвечаем — пропадает смысл проекта».

    Замер, который к этому привёл: на «на какую сумму продано за год» модель написала
    верный ответ (сумма 12 326 000 цифрами), но ДОПОЛНИТЕЛЬНО заявила count=36,
    max=1629700, min=1500, не написав их в тексте. Прежнее правило отвергало ответ
    целиком, и клиент получал отказ вместо верного числа — на каждом третьем прогоне.

    Почему это безопасно: заявление, которого в тексте НЕТ, клиенту ничего не
    утверждает — он его не видит. А каждое число, которое в тексте ЕСТЬ, по-прежнему
    сверяется с базой гейтом (`gate`) и по ролям (`check_roles`). То есть ослаблена
    не проверка чисел, а блокировка ответа тем, чего в ответе нет.
    """
    if not isinstance(claims, dict):
        return True, []
    have = _norm_numbers(text)
    need = ASKED_ROLE.get(want)
    bad = []
    for role, v in claims.items():
        if v is None or (need is not None and role != need):
            continue
        if need is None:
            continue                   # вопрос не про величину — блокировать нечем
        try:
            fv = float(v)
        except (TypeError, ValueError):
            continue
        if fv not in have and round(fv, 2) not in have:
            bad.append("%s=%s названо не цифрами" % (role, _fmt(fv)))
    return (not bad), bad


def _threshold_values(intent):
    """Значения НАШИХ условий отбора: пороги суммы. Дата в текст ответа попадает как
    дата, её проверяет отдельная ветка гейта."""
    amt = (intent or {}).get("amount") or {}
    return [v for v in (amt.get("value"), amt.get("value2")) if v is not None]


def gate(answer, rows, agg, thresholds=None):
    """Каждое число ответа обязано встречаться в данных, в итоге или в наших условиях.

    Правило живёт в КОДЕ, а не в промте: промт — это пожелание, а не гарантия.
    Числа из вопроса НЕ разрешаются: «вопрос» приходит как аргумент инструмента,
    и составляет его модель бота — то есть проверяемый сам пополнял бы белый список.

    🔴 ИСКЛЮЧЕНИЕ — пороги НАШИХ СОБСТВЕННЫХ условий (`thresholds`). Это не число из
    текста вопроса, а значение, по которому МЫ отфильтровали данные: оно верно по
    построению, потому что фильтр применён нами и проверен кодом. [замер 27.07] без
    этого исключения вопрос «какие продажи были на сумму больше 500000» получал отказ,
    хотя ответ был верен целиком: сумма 9 101 800 на 11 документов, максимум 1 629 700 —
    всё сошлось с базой. Не пустило единственное число — 500 000, наш же порог,
    названный в ответе как описание отбора. Это ровно п. 21 TARGET.md: данные есть,
    ответ верен, а не отдала его собственная проверка.
    """
    allowed = set()
    for t in (thresholds or []):
        try:
            v = float(t)
        except (TypeError, ValueError):
            continue
        allowed.add(round(v, 2))
        if v == int(v):
            allowed.add(float(int(v)))
    for r in rows:
        allowed |= _norm_numbers(r[5])
        allowed |= _norm_numbers(r[3])
        # amount приходит из psql как «5000000.00» — через текстовый разбор это давало
        # ещё и 500000000. Берём числом.
        try:
            v = float(r[2])
            allowed.add(round(v, 2))
            if v == int(v):
                allowed.add(float(int(v)))
        except (TypeError, ValueError):
            pass
    if agg:
        # ЧИСЛАМИ, а не текстом: прогон "%.2f" через разбор давал ещё и значение,
        # умноженное на 100 (дробная часть склеивалась с целой).
        for key in ("sum", "min", "max", "avg"):
            v = agg.get(key)
            if v is not None:
                allowed.add(round(float(v), 2))
                if float(v) == int(float(v)):
                    allowed.add(float(int(float(v))))
        allowed.add(float(agg["count"]))
    # Числа из ВОПРОСА в белый список больше не идут. Вопрос — это аргумент, который
    # сочиняет модель бота: она сама пополняла список того, что ей разрешено сказать,
    # и через это проходило любое выдуманное число.

    # Токен обоснован, если ХОТЯ БЫ ОДНО его прочтение есть в данных.
    bad = [sorted(r)[0] for r in _tokens(answer) if not (r & allowed)]

    # Даты: названная дата обязана совпасть с датой из данных ПОКОМПОНЕНТНО.
    known = []
    for r in rows:
        known += _dates(r[3]) + _dates(r[5])
    # Границы периода (`date_min`/`date_max`) посчитаны базой по ВСЕМУ множеству, а `rows`
    # — лишь показанная выборка (LIMIT): строки с крайней датой в ней может не быть.
    # [замер 28.07] из-за этого верный ответ с «28.02.2026» (это `date_max`) отвергался
    # через раз. Даты-агрегаты разрешены наравне со строчными — они проверены базой.
    if agg:
        known += _dates(agg.get("date_min") or "") + _dates(agg.get("date_max") or "")
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


def _coverage_of(src_table):
    """Неполнота ИМЕННО ТОЙ сущности, по которой отвечаем (п. 13).

    Общая перепись говорит «потеряно 5 993 строки», но человеку, спросившему про продажи,
    важно не общее число, а то, полны ли продажи. Отметка обязана быть про его вопрос,
    иначе она превращается в шум, который перестают читать.
    """
    if not src_table:
        return None
    try:
        r = psql("SELECT в_1С, в_корпусе, coalesce(причина,'') FROM search_coverage "
                 "WHERE entity = %s AND в_1С > в_корпусе" % lit(src_table))
    except RuntimeError:
        return None                            # переписи нет — молчим, а не выдумываем
    if not r:
        return None
    return {"in_1c": int(_num(r[0][0])), "in_search": int(_num(r[0][1])),
            "missing": int(_num(r[0][0])) - int(_num(r[0][1])),
            "reason": r[0][2] if len(r[0]) > 2 else ""}


COVERAGE_SYS = """You answer an employee's question about how complete the company's data
is inside this system. You get a census: for each kind of records, how many rows exist in
the source system and how many reached the search, plus the reason when they differ.

Reply with JSON only, no text outside it:
{"text": "the answer for the user",
 "claims": {"total": number|null, "count": number|null, "max": number|null, "min": number|null}}

- Reply in the SAME language the question was asked in.
- Name the kinds of records that are missing, and say WHY, using the reason given.
- State figures in DIGITS, copied from the census — never recompute, never estimate.
- Put the number of missing rows in "claims.total" and the number of affected kinds of
  records in "claims.count", both only if they appear in your text in digits.
- Say plainly if nothing is missing.
- Be short and businesslike, no preamble."""


def _coverage_answer(question, diag, t0):
    """Ответ о полноте данных — из переписи, а не из корпуса (п. 13).

    Числа сюда приходят посчитанными базой и проходят ТОТ ЖЕ гейт, что обычный ответ:
    «сколько данных мы потеряли» — такое же число, как «на какую сумму продано», и
    ошибиться в нём так же нельзя. Отдельного, более мягкого пути для служебных ответов
    нет и быть не должно.
    """
    try:
        tot = psql(
            "SELECT coalesce(sum(в_1С) FILTER (WHERE в_1С > 0), 0),"
            "       coalesce(sum(в_корпусе), 0),"
            "       coalesce(sum(в_1С - в_корпусе) FILTER (WHERE в_1С > в_корпусе), 0),"
            "       count(*) FILTER (WHERE в_1С > 0 AND в_корпусе = 0),"
            "       count(*) FILTER (WHERE в_1С = -1) FROM search_coverage")
        # Поимённо — только то, что ПОТЕРЯНО. Список закрытых правами не перечисляется:
        # их 934, и он рос бы с размером базы, нарушая п. 19. Их число названо, состав
        # доступен запросом.
        lost = psql(
            "SELECT entity, в_1С, в_корпусе, причина FROM search_coverage "
            "WHERE в_1С > 0 AND в_1С > в_корпусе ORDER BY в_1С - в_корпусе DESC LIMIT %d"
            % COVERAGE_TOP)
    except RuntimeError as e:
        sys.stderr.write("ask COVERAGE: перепись недоступна: %s\n" % str(e)[:160])
        return {"partial": None, "kind": "no_data", "sources": [],
                "text": NO_DATA_TEXT or refuse_text(question),
                "diag": dict(diag, error="перепись недоступна")}
    if not tot:
        return {"partial": None, "kind": "no_data", "sources": [],
                "text": NO_DATA_TEXT or refuse_text(question),
                "diag": dict(diag, error="перепись пуста — такт ещё не считал полноту")}
    in_1c, in_search, n_lost, ent_lost, ent_denied = (int(_num(x)) for x in tot[0][:5])
    census = ["rows in source system: %d" % in_1c, "rows reached search: %d" % in_search,
              "rows missing: %d" % n_lost, "kinds of records fully missing: %d" % ent_lost,
              "kinds of records closed by permissions in the source system: %d" % ent_denied]
    for r in lost:
        census.append("%s: %s in source, %s in search — %s"
                      % (r[0], r[1], r[2], r[3] if len(r) > 3 else ""))
    raw = ds_chat([{"role": "system", "content": COVERAGE_SYS},
                   {"role": "user",
                    "content": "%s\n\nCensus:\n%s" % (question, "\n".join(census))}])
    text, claims = _split_answer(raw)
    # Гейт: заявленные числа обязаны совпасть с переписью. Роли те же, что у обычного
    # ответа, поэтому проверка переиспользуется без послаблений.
    agg = {"sum": float(n_lost), "count": ent_lost}
    ok_roles, bad = check_claims(claims, agg, [])
    diag["claims"] = claims or None
    if not ok_roles or not (text or "").strip():
        sys.stderr.write("ask COVERAGE GATE: %s\n" % bad[:4])
        # Числа посчитаны и верны — отдаём их структурой, как и на обычном пути.
        return {"partial": None, "kind": "figures", "text": text.strip(),
                "figures": {"rows_in_1c": in_1c, "rows_in_search": in_search,
                            "rows_missing": n_lost, "entities_missing": ent_lost,
                            "entities_denied": ent_denied},
                "sources": [], "diag": dict(diag, gate_rejected=bad[:4],
                                            sec=round(time.time() - t0, 2))}
    return {"partial": None, "kind": "answer", "text": text.strip(), "sources": [],
            "figures": {"rows_in_1c": in_1c, "rows_in_search": in_search,
                        "rows_missing": n_lost, "entities_missing": ent_lost,
                        "entities_denied": ent_denied},
            "diag": dict(diag, sec=round(time.time() - t0, 2), gate_ok=True)}


# ----------------------------------------------------------------- HTTP
# Опыт 30.07: нужно ли считать расхождение слабого сигнала (вектор вопроса) с выбором
# модели признаком неоднозначности. Решается замером, а не рассуждением.
SIGNAL_DISAGREE = os.environ.get("ASK_SIGNAL_DISAGREE", "1") == "1"
# Требовать подтверждения выбора сущности; иначе спрашивать человека.
REQUIRE_SUPPORT = os.environ.get("ASK_REQUIRE_SUPPORT", "1") == "1"
# Сколько готовых ответов отдавать арбитру. Больше двух-трёх не нужно: это
# столько же полных ответов, сколько кандидатов, и время ответа растёт.
ARBITER_MAX = int(os.environ.get("ASK_ARBITER_MAX", "3"))
# Словарь со стеммингом — им сравниваются слово человека и название сущности.
# Создаётся сборкой (`corpus_init.sql`), локаль наследует от основного словаря.
STEM_DICT = os.environ.get("ASK_STEM_DICT", "search_dict_stem")


def answer(question, focus=None, measure_pick=None, context="", no_arbiter=False):
    """Вопрос -> поиск в базе -> счёт в базе -> формулировка -> гейт.

    `focus` — сущность, ВЫБРАННАЯ человеком после уточнения (кнопкой или словом). Когда
    вопрос неоднозначен, система отвечает `kind=clarify` со списком сущностей; бот
    показывает их кнопками, и выбор возвращается сюда как `focus`. Тогда выбор сущности не
    гадается — берётся заданный, и ответ считается по нему. Так замыкается порядок п. 21:
    ответ → уточняющий вопрос → ответ по выбору (решение владельца 28.07: «если после
    уточнения даётся верный ответ, это ок»).

    Порядок важен: сначала множество совпадений раскладывается по источникам ЦЕЛИКОМ,
    и только потом выбирается один источник и тянутся его строки. Обратный порядок
    (сперва top-N строк, потом группировка) терял целые таблицы.
    """
    t0 = time.time()
    intent = parse_intent(question, time.strftime("%Y-%m-%d"))
    preds = _predicates(intent)
    diag = {"terms": intent.get("terms"), "preds": preds, "kind": intent.get("kind")}

    # ВОПРОС О САМИХ ДАННЫХ ИЛИ О ТОМ, ЧТО СИСТЕМА О НИХ ЗНАЕТ (п. 13).
    #
    # «То, что недоступно — закрыто правами, не загрузилось, не попало в индекс — видно
    # владельцу». До этого перепись считалась и не читалась никем: [замер 28.07] `grep`
    # по сервису ответов давал ноль совпадений с `search_coverage` и `base_profile`.
    # Владелец узнавал о 5 993 потерянных строках, только заглянув в таблицу руками.
    #
    # Различает вопросы МОДЕЛЬ, тем же разбором намерения, который и так делается на
    # каждый вопрос: ни второго обращения к модели, ни списка слов. Список вроде
    # «чего нет», «не загрузилось» был бы хардкодом под язык (`HOW_NOT_TO §3.9`), а
    # продукт коробочный и конфигурация может быть любой.
    if (intent.get("about") or "") == "coverage":
        diag["about"] = "coverage"
        return _coverage_answer(question, diag, t0)
    # Что не доехало до модели — уходит в ОТВЕТ, а не в журнал (п. 13). Объявлено здесь,
    # потому что ранние ветки возврата (нет совпадений) отвечают раньше выбора сущности.
    cut = {}

    exprs, kinds = probe(intent.get("terms") or [])
    diag["match_by"] = {k: v for k, v in kinds.items() if k != "_resolved"}
    # Разрешённые резолвером значения — В ОТВЕТ (п. 13): человек должен видеть, что «Питер»
    # поняли как «Санкт-Петербург», а не гадать. В тексте это и так всплывёт, но метка
    # даёт проверяемый след.
    if isinstance(kinds, dict) and kinds.get("_resolved"):
        diag["resolved"] = kinds["_resolved"]

    # 🔴 ЗНАЧЕНИЕ, КОТОРОГО НЕТ, НЕ ПРЕВРАЩАЕТСЯ В «ВСЁ». Термы `terms` — это ЗНАЧЕНИЯ,
    # которые обязаны стоять в записи (имя контрагента, товар). Если группа не нашлась ни
    # буквально, ни резолвером — такого значения в базе нет. Прежде группа молча
    # выбрасывалась, и «продали SanDisk» отвечало про ВСЕ продажи на 12 млн — неверный
    # ответ (п. 3), опаснее отказа. Считаем: сколько групп-значений осталось без совпадения.
    n_groups = len(intent.get("terms") or [])
    matched_groups = len([g for g in (kinds or {}) if isinstance(g, int)])
    if n_groups > 0 and matched_groups < n_groups:
        missing = n_groups - matched_groups
        diag["unmatched_terms"] = missing
        # Не нашли ни одного значения из вопроса — отвечать не о чем, это честный отказ,
        # а НЕ агрегат по всей сущности.
        if matched_groups == 0:
            return {"partial": cut or None, "kind": "no_data", "sources": [],
                    "text": NO_DATA_TEXT or refuse_text(question),
                    "diag": dict(diag, sec=round(time.time() - t0, 2),
                                 reason="значения из вопроса не найдены в данных")}

    match, k = match_expr(exprs, preds)
    diag["min_should_match"] = k if exprs else 0

    by = tables_of(match, preds)
    # Табличные части попадают в кандидаты вместе со своей шапкой: искать их по словам
    # вопроса бесполезно — имени контрагента в строках товаров нет.
    kids, kid_pred = children_by_parent(by, match, preds)
    if kids:
        by.update(kids)
        diag["children"] = kids
    if not by and match:                       # слова не дали ничего — ищем по смыслу
        vec = _vec(question)
        # Оператор <=> — РОДНОЕ ядро движка (cosine_distance), а array_cosine_similarity
        # приходит из ядра DuckDB. Разница не только в скорости (замер 27.07: 583-627 мс
        # против 435-451 на 97 965 x 1536): только родные функции несут AnnFunctionInfo,
        # то есть array_* НИКОГДА не сможет воспользоваться векторным индексом. Выдача
        # не меняется — сверено топ-40, совпало 40 из 40 позиция в позицию.
        # <=> это РАССТОЯНИЕ: меньше = ближе, поэтому сортировка по возрастанию, без DESC.
        # 🔴 И ЗДЕСЬ РАЗДЕЛИТЕЛЬ РАВЕНСТВА. Это самое дорогое место: `LIMIT` отрезает
        # ближайшие строки, из них складывается САМ НАБОР сущностей-кандидатов, и без
        # разделителя набор колеблется. [замер 30.07] один вопрос пять раз — сущностей в
        # наборе 1 322, 1 322, 1 318, 1 318, 1 318, и вместе с набором менялся ответ.
        near = psql("SELECT src_table, count(*) FROM (SELECT src_table FROM %s "
                    "ORDER BY emb <=> %s, src_table, row_key LIMIT %d) GROUP BY 1"
                    % (CORPUS, vec, TOPK))
        by = {r[0]: int(r[1]) for r in near if r and r[0]}
        match = ""
        diag["by_vector"] = True
    if not by:
        by = tables_of("", preds)
    if not by:
        return {"partial": cut or None, "kind": "no_data", "text": NO_DATA_TEXT or refuse_text(question), "sources": [],
                "diag": dict(diag, sec=round(time.time() - t0, 2))}

    # Кандидаты: те, где поиск ЧТО-ТО нашёл, плюс ближайшие по смыслу названия.
    # Кандидаты — те сущности, где поиск ДЕЙСТВИТЕЛЬНО что-то нашёл. Без отсечки по
    # числу: любое «первые N» означает «на нашей базе нужное попадало в первые N», и на
    # базе другого размера нужная сущность просто выпадет из списка.
    #
    # «Совпадений N» имеет смысл, только если совпадение было по СЛОВАМ вопроса. Одно
    # условие по дате — не совпадение: группировка тогда возвращает размеры таблиц,
    # отфильтрованные по дате. Замерено на «сколько продали в декабре»: календарные
    # графики 62, регистр производственного календаря 31, нужный документ 6 — и модели
    # это подавалось как «столько записей совпало».
    signal = bool(match)
    # Число подошедших строк показывается модели ВСЕГДА, а не только при совпадении по
    # словам. Прежняя оговорка («без слов это просто размеры таблиц, отфильтрованные по
    # дате») верна лишь наполовину: отфильтрованное по дате число — это и есть данные о
    # вопросе. [замер 28.07] «сколько продали в декабре» уходило в регистр
    # `accumulationregister_реализацияуслуг_recordtype` с ОДНОЙ декабрьской записью
    # вместо документа продажи с шестью — по названию они почти неразличимы, а по числу
    # подошедших строк различаются вшестеро.
    counts_for_model = by
    # Кандидаты — ВСЕГДА те сущности, которые реально подошли: по словам вопроса, а
    # если слов нет — по его условиям (период, порог суммы). Раньше при отсутствии
    # слов список подходящих ВЫБРАСЫВАЛСЯ и модели отдавались все 226 сущностей
    # базы. Замерено: «продажи за декабрь» — нужный документ был среди подходящих по
    # дате (6 строк), но тонул в общем списке, и выбирались календарные графики.
    cands = list(by)
    # ВЕЛИЧИНА, О КОТОРОЙ СПРАШИВАЮТ, ДОЛЖНА У КАНДИДАТА СУЩЕСТВОВАТЬ.
    # Строка несёт ВСЕ свои числовые величины картой, поэтому проверка теперь общая:
    # у кандидата должна быть хоть одна величина. Какая именно нужна — решается уже
    # после выбора сущности (`pick_measure`), потому что имена величин у каждой свои.
    # Отбор идёт ДАННЫМИ: у сущности либо есть заполненная величина, либо нет. Ни порога,
    # ни числа, ни имени — размер и состав базы ничего не меняют (п. 9).
    # [замер 27.07] без этого правила «сколько продали в декабре» отвечалось
    # «100 000 рублей (1 запись)» вместо 2 456 400 на 6 документах: вопрос уходил
    # к сущности, у которой суммы нет вовсе. Реранкер этого не закрывает — он про то,
    # ЧТО спросили, а не про то, ЧЕМ сущность располагает.
    if intent.get("want") == "sum" and len(cands) > 1:
        try:
            with_value = {r[0] for r in psql(
                "SELECT src_table FROM %s WHERE src_table IN (%s) "
                "  AND nums IS NOT NULL AND len(map_keys(nums)) > 0 GROUP BY 1"
                % (CORPUS, ", ".join(lit(c) for c in cands))) if r and r[0]}
            if with_value:
                dropped = [c for c in cands if c not in with_value]
                cands = [c for c in cands if c in with_value]
                if dropped:
                    diag["without_value"] = len(dropped)
        except RuntimeError:
            pass
    # 🔴 ПРИЗНАК «У КАНДИДАТА ЕСТЬ СПРОШЕННОЕ ПОЛЕ» ПРОВЕРЕН И ОТКЛОНЁН — код убран.
    # Мысль была: если человек спрашивает «ИНН», то у верной сущности такое поле должно быть.
    # Признак строился штатно, словарём движка по основам слов (`ts_lexize` + `list_has_any`,
    # `techContext` возможность 35), то есть падежи ему не мешали.
    #
    # [замер 30.07, три прогона по восемь вопросов] он НЕ УЛУЧШИЛ результат ни в одной форме:
    #   отсевом      — выбросил `catalog_склады` (сам ответ) и дал 4 неверных на 24;
    #   перестановкой — сломал «сколько партнёров», 2/1/3 неверных;
    #   поднятием соперника к арбитру — тоже хуже, чем без него (1/0/1).
    # Причина: по основам совпадает МНОГО названий, круг соперников расширяется, и арбитр
    # выбирает из шума.
    #
    # Убран целиком, а не оставлен «наблюдением в diag»: запрос на каждый вопрос ради числа,
    # которое ни на что не влияет, — это время ответа и ложный след для следующего читателя
    # («значит, признак работает»). Разбор с числами — `docs/DEFECT_FOCUS_CHOICE.md §9`.
    # Порядок списка — ПО СМЫСЛУ вопроса, не по числу совпадений: модель тяготеет к
    # началу списка, а число совпадений врёт (значение встречается чаще в чужой
    # сущности). Порядок — это данные (эмбеддинг названия сущности против вопроса),
    # отсечки нет: список отдаётся модели целиком.
    # ПОРЯДОК КАНДИДАТОВ — В ДВА ШАГА, И ОБА ОГРАНИЧЕНЫ СВЕРХУ.
    # Шаг 1, в базе: грубый порядок по близости метки к слову вопроса. Сигнал слабый
    # (он не связывает «продажи» с «Реализация Товаров Услуг» и ставит выше «Склады»),
    # но он бесплатный и годится как СИТО.
    # Шаг 2, моделью: реранкер оценивает пару «вопрос ↔ название» и расставляет голову
    # списка правильно. [замер 27.07] «продажи» → «Реализация Товаров Услуг» первым
    # (0,585) там, где эмбеддинг давал «Склады» (0,521).
    # 🔴 Во внешнюю модель уходит НЕ БОЛЬШЕ RERANK_TOP названий — иначе объём растёт с
    # числом сущностей базы, а это п. 19. Отсечённое видно клиенту через `partial`.
    # 🔴 СИТО НЕ ИМЕЕТ ПРАВА ВИСЕТЬ НА ОДНОМ СЛОВЕ, КОТОРОЕ ПРИДУМАЛА МОДЕЛЬ.
    # [замер 30.07] на вопрос «На какую сумму мы закупили товаров и услуг?» модель выдаёт
    # `kind` то «закупки», то «закупка» — шесть вызовов подряд: закупки, закупка, закупки,
    # закупки, закупка, закупки. Множественное число ДОСЛОВНО совпадает с именем регистра
    # `accumulationregister_закупки`, тот встаёт первым и вытесняет документ за RERANK_TOP —
    # реранкер его уже не видит. Итог: четыре отказа и два верных ответа (73 181 157,68)
    # НА ОДИН И ТОТ ЖЕ ВОПРОС при неизменных данных.
    #
    # Это нарушение сразу трёх пунктов контракта, а не вопрос вкуса:
    #   п. 3  — «детерминированно на данных»: один вопрос обязан давать один ответ;
    #   п. 19 — «моделью не ищем»: отбор ведёт код, модель нужна только для смысла. Здесь
    #           же выбор сущности решался грамматической формой слова ОТ МОДЕЛИ;
    #   п. 12 — молчаливый выбор между правдоподобными вариантами запрещён.
    #
    # Как надо (`HOW_NOT_TO §3.16`): не подкручивать порядок, чтобы нужное «обычно
    # побеждало», а СДЕЛАТЬ ВЫТЕСНЕНИЕ НЕВОЗМОЖНЫМ. Сито считается по ДВУМ входам —
    # по самому вопросу (вход стабильный, это текст человека) и по слову модели, — и
    # голова списка берётся ОБЪЕДИНЕНИЕМ вперемежку. Тогда ни один вход в одиночку не
    # может выбросить кандидата: слово модели добавляет сигнал, но больше ничего не решает.
    # Верхняя граница прежняя (RERANK_TOP), то есть объём в модель не вырос — п. 19 цел.
    top_by_question = None
    if ORDER_BY_MEANING and len(cands) > 1:
        orders = []
        for src_text in (question, intent.get("kind")):
            if not src_text:
                continue
            try:
                orders.append([r[0] for r in psql(
                    "SELECT src_table FROM %s WHERE src_table IN (%s) "
                    # разделитель равенства: ниже порядок режется по RERANK_TOP,
                    # и без него до реранкера доходят разные сущности
                    "ORDER BY emb <=> %s, src_table"
                    % (TABLES, ", ".join(lit(c) for c in cands), _vec(src_text)))])
            except RuntimeError:
                pass
        if orders:
            # Вершина по САМОМУ ВОПРОСУ — независимый от модели сигнал. Ниже он служит
            # признаком неоднозначности: если он расходится с выбором модели, вопрос
            # честно допускает несколько прочтений, и по п. 12 мы обязаны спросить.
            top_by_question = orders[0][0] if orders[0] else None
            # Вперемежку: первый по вопросу, первый по слову, второй по вопросу, ...
            order, seen = [], set()
            for i in range(max(len(o) for o in orders)):
                for o in orders:
                    if i < len(o) and o[i] not in seen:
                        seen.add(o[i]); order.append(o[i])
            cands = order + [c for c in cands if c not in seen]
            diag["sieve"] = len(orders)
        else:
            cands = sorted(by, key=lambda t: -by[t])
        head, tail = cands[:RERANK_TOP], cands[RERANK_TOP:]
        if tail:
            cut["reranked_of"] = len(cands)
            cut["reranked"] = len(head)
        try:
            lab = {r[0]: r[1] for r in psql(
                "SELECT src_table, label FROM %s WHERE src_table IN (%s)"
                % (TABLES, ", ".join(lit(c) for c in head))) if r and r[0]}
        except RuntimeError:
            lab = {}
        keys = [c for c in head if c in lab]
        idx = rerank(question, [lab[c] for c in keys]) if keys else []
        if idx:
            best = [keys[i] for i in idx if 0 <= i < len(keys)]
            cands = best + [c for c in head if c not in best] + tail
            diag["order_by"] = "rerank"
    # РЕБЁНОК НЕ МОЖЕТ СТОЯТЬ РАНЬШЕ РОДИТЕЛЯ. Табличная часть документа и сам документ —
    # разные источники, и итог живёт в ШАПКЕ, а не в строках. Порядок по смыслу этого не
    # знает: [замер 27.07] на вопросе «какая самая крупная продажа» метки табличных
    # частей оказались ближе к слову «продажа» (0,566-0,574), чем метка документа
    # (0,600), список пошёл модели с них, и ответом стала самая крупная СТРОКА
    # накладной — 1 550 000 вместо 1 629 700. Ответ верный по числу и неверный по сути.
    # Родитель берётся из КОНТРАКТА ПЛАТФОРМЫ (составной ключ), а не из имени: в
    # `search_tables.parent` его записывает сборщик. Оба источника остаются в списке —
    # мы не решаем за модель, мы лишь не ставим часть впереди целого.
    # 🔴 Правило применяется ТОЛЬКО когда спрашивают ЧИСЛО. Оно и заводилось ради этого:
    # итог документа живёт в шапке, а не в строках. Но на вопрос «что покупало ООО
    # Ромашка» ответ как раз в СТРОКАХ — там наименования, — и правило уводило на шапку,
    # где их нет. [замер 28.07] система честно отвечала «покупало товары и услуги,
    # наименований нет», то есть правило мешало ответить.
    wants_number = bool((intent.get("measure") or "").strip()) or \
        intent.get("want") in ("sum", "count")
    if wants_number and len(cands) > 1:
        try:
            par = {r[0]: r[1] for r in psql(
                "SELECT src_table, parent FROM %s WHERE src_table IN (%s)"
                % (TABLES, ", ".join(lit(c) for c in cands))) if r and r[0]}
            ordered, placed = [], set()
            for c in cands:
                if par.get(c) in cands and par.get(c) not in placed:
                    continue                    # ребёнок ждёт, пока встанет родитель
                ordered.append(c)
                placed.add(c)
                for ch in cands:                # сразу за родителем — его части
                    if ch not in placed and par.get(ch) == c:
                        ordered.append(ch)
                        placed.add(ch)
            cands = ordered + [c for c in cands if c not in placed]
        except RuntimeError:
            pass                                # порядок остаётся прежним
    # Не подошло ничего вовсе (чужой язык, иное написание) — только тогда идём от
    # смысла вопроса к названиям всех сущностей.
    if not cands:
        try:
            # LIMIT в БАЗЕ: иначе в кандидаты, а следом в промпт, уезжает вся база.
            # Число получаем из бюджета промпта, а не задаём отдельно.
            cands = [r[0] for r in psql(
                "SELECT src_table FROM %s ORDER BY emb <=> %s, src_table LIMIT %d"
                % (TABLES, _vec(intent.get("kind") or question),
                   max(1, PICK_BUDGET // 40))) if r and r[0]]
        except RuntimeError:
            cands = list(by)
    # ВЕЛИЧИНА, О КОТОРОЙ СПРАШИВАЮТ, ДОЛЖНА У КАНДИДАТА СУЩЕСТВОВАТЬ.
    # Строка несёт ВСЕ свои числовые величины картой, поэтому проверка теперь общая:
    # у кандидата должна быть хоть одна величина. Какая именно нужна — решается уже
    # после выбора сущности (`pick_measure`), потому что имена величин у каждой свои.
    # Отбор идёт ДАННЫМИ: у сущности либо есть заполненная величина, либо нет. Ни порога,
    # ни числа, ни имени — размер и состав базы ничего не меняют (п. 9).
    # [замер 27.07] без этого правила «сколько продали в декабре» отвечалось
    # «100 000 рублей (1 запись)» вместо 2 456 400 на 6 документах: вопрос уходил
    # к сущности, у которой суммы нет вовсе. Реранкер этого не закрывает — он про то,
    # ЧТО спросили, а не про то, ЧЕМ сущность располагает.
    if intent.get("want") == "sum" and len(cands) > 1:
        try:
            with_value = {r[0] for r in psql(
                "SELECT src_table FROM %s WHERE src_table IN (%s) "
                "  AND nums IS NOT NULL AND len(map_keys(nums)) > 0 GROUP BY 1"
                % (CORPUS, ", ".join(lit(c) for c in cands))) if r and r[0]}
            if with_value:
                dropped = [c for c in cands if c not in with_value]
                cands = [c for c in cands if c in with_value]
                if dropped:
                    diag["without_value"] = len(dropped)
        except RuntimeError:
            pass
    # ВОПРОС ПРО ДЕНЬГИ — ТОЛЬКО К ТЕМ, У КОГО ДЕНЬГИ ЕСТЬ. Это отбор ДАННЫМИ, а не
    # догадкой: у сущности либо есть заполненная денежная колонка, либо нет, и та, у
    # которой её нет, ответить про сумму не может в принципе.
    # Зачем: [замер 27.07] на «What is the total amount of all sales?» модель выбирала
    # из 238 названий и брала «Поступление На Расчетный Счет». Порядок перечня задаётся
    # близостью метки к слову вопроса, а этот сигнал негоден (у «sales» ближайшее —
    # «Склады»); выключить его нельзя — без порядка модель берёт первое попавшееся
    # (проверено: выбирала «Поля Форм Статистики»). Сужение круга бьёт в причину:
    # кандидатов становится меньше, и все они по существу пригодны.
    # Отсечка не по числу и не по порогу — по НАЛИЧИЮ величины, поэтому размер базы
    # ничего не меняет (п. 9).
    if intent.get("want") == "sum" and len(cands) > 1:
        try:
            with_money = {r[0] for r in psql(
                "SELECT src_table FROM %s WHERE src_table IN (%s) "
                "  AND nums IS NOT NULL AND len(map_keys(nums)) > 0 GROUP BY 1"
                % (CORPUS, ", ".join(lit(c) for c in cands))) if r and r[0]}
            if with_money:
                dropped = [c for c in cands if c not in with_money]
                cands = [c for c in cands if c in with_money]
                if dropped:
                    diag["without_value"] = len(dropped)
        except RuntimeError:
            pass
    # Параметры подсчёта, названные моделью: сущность, величина, что считать. Объявляются
    # ДО ветвления, чтобы ни один путь не оставил их неопределёнными.
    plan = {}
    # ВЫБОР ЧЕЛОВЕКА ПОСЛЕ УТОЧНЕНИЯ важнее догадки: если задан `focus` и такая сущность
    # реально под условиями что-то содержит — берём её и не спрашиваем модель.
    if focus:
        picked, marks, plan = [focus], {}, {}
        diag["focus_forced"] = focus
        # Код-терм (счёт, ОКВЭД) при ВЫБРАННОЙ сущности фильтруется иерархическим префиксом
        # безопасно: сущность уже определена, спутать её с чужой нельзя. Дот-граница
        # отсекает лишнее (счёт «62» ≠ сумма «624000»): [замер] по регистру ровно 147
        # движений, сумма сходится с 1С. В одношаговом ответе этот префикс давал ошибочный
        # выбор сущности — поэтому он живёт ТОЛЬКО на выбранной человеком.
        code_filter = None
        for group in (intent.get("terms") or []):
            for alt in group:
                a = alt.strip()
                if a and any(c.isdigit() for c in a) and "." not in a and len(a) <= 12:
                    code_filter = ("(doc @@ ts_starts_with(%s) OR doc @@ ts_phrase(%s))"
                                   % (lit(a.lower() + "."), lit(a)))
                    break
            if code_filter:
                break
        if code_filter:
            # Префикс кода СТАНОВИТСЯ `match`. Буквальный «62» точной фразой по выбранной
            # сущности дал бы ноль. `match` (а не `preds`) — потому что по нему запросы
            # идут по ИНДЕКСУ, где только и работают `ts_*`; с пустым match они ушли бы в
            # корпус и упали («TSQUERY outside @@ match»).
            match = code_filter
    else:
        try:
            picked, marks, plan = pick_entity(question, intent.get("kind"), cands,
                                              counts_for_model, match, cut)
        except RuntimeError:
            picked, marks, plan = [], {}, {}
            diag["degraded"] = "выбор сущности сделан без модели"

        # КОД С ИЕРАРХИЕЙ — НЕОДНОЗНАЧНОСТЬ, КОТОРУЮ РЕШАЕТ ЧЕЛОВЕК. «62» — это и номер
        # формы статистики, и счёт: буквальный поиск ведёт к форме, а иерархический
        # префикс `62.` — к регистру бухучёта. Судить, что имел в виду человек, по числу
        # нельзя. Раньше система молча брала форму и отвечала «нет оборотов». Теперь: если
        # у кода есть держатели через `62.`, которых буквальный поиск НЕ дал, — предлагаем
        # выбор (форма / регистр), и по выбору (`focus`) считаем верно. Порядок п. 21.
        code_terms = [a.strip() for g in (intent.get("terms") or []) for a in g
                      if a.strip() and any(c.isdigit() for c in a) and "." not in a
                      and len(a.strip()) <= 12]
        if code_terms and not focus:
            holders = {}
            for r in psql(" UNION ALL ".join(
                    "SELECT src_table, count(*) n FROM %s WHERE doc @@ ts_starts_with(%s) "
                    "GROUP BY 1" % (INDEX, lit(c.lower() + ".")) for c in code_terms[:2])):
                try:
                    holders[r[0]] = holders.get(r[0], 0) + int(r[1])
                except (ValueError, IndexError):
                    continue
            extra = [t for t in sorted(holders, key=lambda x: -holders[x])[:3]
                     if t not in by and t not in picked]
            if extra:
                picked = list(dict.fromkeys((picked or []) + extra))
                diag["code_ambiguous"] = extra

    # 🔴 РАСХОЖДЕНИЕ НЕЗАВИСИМЫХ СИГНАЛОВ — ЭТО И ЕСТЬ НЕОДНОЗНАЧНОСТЬ.
    # [замер 30.07] реранкер на вопрос «На какую сумму мы закупили товаров и услуг?»
    # пять раз подряд ставит первым «Суммы Документов В Валюте Регл» — по совпадению слов
    # «сумма»/«документов», — а верное «Приобретение Товаров Услуг» кладёт ПОСЛЕДНИМ.
    # При этом порядок хвоста у него от вызова к вызову разный (позиции 2-4 переставляются),
    # то есть на его единоличный выбор опираться нельзя ни по правильности, ни по
    # воспроизводимости (п. 3). Вектор при этом детерминирован: одно слово — один вектор.
    #
    # Отсюда правило, не требующее ни порога, ни знания базы: если вершина по САМОМУ
    # ВОПРОСУ (считает база) не совпала с выбором модели — это два равноправных прочтения,
    # и п. 12 прямо запрещает выбирать между ними молча. Спрашиваем человека готовым
    # механизмом уточнения (кнопки + «свой вариант», решение владельца 28.07).
    #
    # Это не «уточнять почаще на всякий случай»: пока оба сигнала согласны — ответ идёт
    # без вопроса, как и требует порядок п. 21 (ответ → уточнение → отказ).
    # 🔴 ОДНА СЕМЬЯ — ЭТО ОДНО ПРОЧТЕНИЕ, А НЕ ДВА. Табличная часть и её шапка (`Партнеры`
    # и `Партнеры_КонтактнаяИнформация`) — не два смысла вопроса, а одна сущность и её же
    # часть. Без этой оговорки система спрашивала лишнее: [замер 30.07] «Какой ИНН у
    # Нептун?» → «из карточки партнёра или из контактной информации?», хотя прочтение одно.
    # Родство приходит из данных (`search_tables.parent`), а не из разбора имени.
    # Указание владельца 30.07 требует спрашивать при СОМНЕНИИ; лишний вопрос там, где
    # сомнения нет, — не осторожность, а шум, и он обесценивает настоящие уточнения.
    # Родство нужно ДВУМ проверкам ниже — и признаку неоднозначности, и подбору соперника
    # для арбитра, — поэтому берётся один раз и на весь круг кандидатов, которых мы можем
    # рассматривать. Без этого `_family` молча возвращала бы саму сущность, и в соперники
    # арбитру попадала бы табличная часть той же шапки: два ответа об одном и том же.
    par = {}
    if picked:
        need = set(picked) | set(cands[:ARBITER_MAX * 4])
        if top_by_question:
            need.add(top_by_question)
        try:
            par = {r[0]: (r[1] or "") for r in psql(
                "SELECT src_table, parent FROM %s WHERE src_table IN (%s)"
                % (TABLES, ", ".join(lit(c) for c in need))) if r and r[0]}
        except RuntimeError:
            par = {}

    def _family(t):
        return par.get(t) or t
    if (SIGNAL_DISAGREE and top_by_question and picked and not focus
            and top_by_question not in picked and top_by_question in by
            and _family(top_by_question) not in {_family(x) for x in picked}):
        picked = list(dict.fromkeys(picked + [top_by_question]))
        diag["signals_disagree"] = top_by_question

    # НЕОДНОЗНАЧНЫЙ ВОПРОС — спрашиваем человека, а не угадываем за него.
    # Судья неоднозначности — модель: она видит и названия, и отличительные реквизиты
    # каждого источника, и сама говорит, когда вопрос честно допускает несколько
    # прочтений. Порога тут нет и быть не может: «одинаково ли подходят» — вопрос
    # языковой, а не числовой. Замеренный случай: «что покупало ООО Ромашка» — у двух
    # источников ровно по 3 совпадения, и оба ответа следуют из данных (контрагент и
    # покупал товары, и платил). Прежде система молча брала один.
    # 🔴 АРБИТРУ НУЖНЫ ДВА ОТВЕТА, А МОДЕЛЬ ЧАСТО УВЕРЕННО НАЗЫВАЕТ ОДИН — И ОШИБАЕТСЯ.
    # [замер 30.07] «сколько приобретений товаров и услуг»: `picked` из одного элемента, и
    # это то `Приобретение Товаров Услуг` (249, верно), то `Корректировка Приобретения`
    # (3, неверно). Арбитр в такой ветке не запускался вовсе и помочь не мог.
    # Поэтому соперник ДОБАВЛЯЕТСЯ: следующий по порядку отбора кандидат, у которого есть
    # свои совпадения и который не из той же семьи (шапка/табличная часть — одно прочтение).
    # Порядок отбора — данные (близость вектора, затем реранкер), а не список имён.
    # 🔴 АРБИТР — ТОЛЬКО ТАМ, ГДЕ ЕСТЬ СОМНЕНИЕ. Владелец 30.07: «лучше 1, 2, 3 раза уточнить,
    # ЕСЛИ НЕПОНЯТНО» и «в таких ситуациях даём арбитру выбор». Не в каждой ситуации.
    #
    # [замер 30.07] когда соперник придумывался ВСЕГДА, сломались вопросы, отвечавшие верно:
    # «сколько партнёров» и «сколько организаций». Арбитру подсовывали соперника там, где
    # выбор однозначен, и он иногда выбирал соперника. Сомнение обязано быть НАЙДЕНО, а не
    # создано мной ради запуска арбитра.
    #
    # Что считается сомнением (оба признака — из данных, ни одного порога):
    #   1. модель назвала БОЛЬШЕ ОДНОЙ сущности — она сама видит несколько прочтений;
    #   2. вершина по вектору САМОГО ВОПРОСА (считает база) не совпала с выбором модели и не
    #      из той же семьи (шапка и её табличная часть — одно прочтение).
    doubt = len(picked) > 1 or bool(diag.get("signals_disagree"))
    arb_pool = list(picked)
    if doubt and picked and not focus and not no_arbiter and len(arb_pool) < ARBITER_MAX:
        fam = {_family(x) for x in arb_pool}
        # 🔴 СОПЕРНИК БЕРЁТСЯ ПО ПОРЯДКУ ОТБОРА, И ЭТО РЕШЕНО ЗАМЕРОМ, А НЕ ВКУСОМ.
        # Я попробовал подбирать соперника «по независимым признакам» — вершина по вектору
        # вопроса и кандидат с наибольшим числом совпадений. [замер 30.07] стало ХУЖЕ:
        # 0 верных из 3 против 3 из 5, и в пару попадали `Корректировка Приобретения` плюс
        # КОНСТАНТА, то есть верной сущности там не было вовсе. Правка откачена.
        # Порядок отбора (вектор, затем реранкер) хотя бы держит верную сущность в голове
        # списка; вершина по вопросу добавляется ПОСЛЕ него, как дополнение, а не вместо.
        # 🔴 ПРИЗНАК «ЕСТЬ СПРОШЕННОЕ ПОЛЕ» НЕ УЧАСТВУЕТ В ПОДБОРЕ СОПЕРНИКА. [замер 30.07]
        # когда он поднимал таких кандидатов вперёд, стало ХУЖЕ: 2, 1, 3 неверных ответа на
        # восьми вопросах против 1, 0, 1 без него. Со стеммингом по основам совпадает МНОГО
        # сущностей («организаций» -> «организац» есть у многих), круг соперников расширяется
        # и арбитр выбирает из шума. Признак остаётся в `diag` как наблюдение, но решения не
        # принимает: сигнал, который не улучшил замер, не имеет права менять поведение.
        for c in list(cands) + ([top_by_question] if top_by_question else []):
            if len(arb_pool) >= ARBITER_MAX:
                break
            if c in arb_pool or c not in by or _family(c) in fam:
                continue
            arb_pool.append(c); fam.add(_family(c))
        if len(arb_pool) > 1:
            diag["arbiter_rivals"] = arb_pool[1:]

    if len(arb_pool) > 1 and not no_arbiter:
        # 🔴 СНАЧАЛА АРБИТР, ПОТОМ ЧЕЛОВЕК. Порядок п. 21: ответ → уточняющий вопрос →
        # отказ. Спрашивать человека, не попытавшись ответить, — значит переложить на него
        # работу, которую система может сделать сама. Поэтому по каждому кандидату
        # СОБИРАЕТСЯ ПОЛНЫЙ ОТВЕТ (тем же кодом, через `focus`, — то есть числа считает
        # база), и арбитр выбирает между готовыми ответами. Не выбрал — спрашиваем человека.
        cand_ans, cand_src = [], []
        for c in arb_pool[:ARBITER_MAX]:
            try:
                sub = answer(question, focus=c, measure_pick=measure_pick,
                             context=context, no_arbiter=True)
            except Exception:                  # noqa: BLE001 — один кандидат не должен
                continue                       # ронять весь ответ
            if sub.get("kind") in ("answer", "figures") and (sub.get("text") or "").strip():
                cand_ans.append(sub["text"].split("⚠")[0].strip())
                cand_src.append(sub)
        if len(cand_ans) > 1:
            n = arbitrate(question, cand_ans, context)
            diag["arbiter"] = {"candidates": [s.get("diag", {}).get("focus") for s in cand_src],
                               "chose": None if n is None else
                                        cand_src[n].get("diag", {}).get("focus")}
            if n is not None:
                out = dict(cand_src[n])
                out["diag"] = dict(out.get("diag", {}), arbiter=diag["arbiter"])
                out["partial"] = cut or out.get("partial")
                return out
        elif len(cand_ans) == 1:
            # Ответ смог собраться только у одного кандидата — остальные пусты. Выбирать не
            # из чего, и спрашивать человека не о чем: у прочих ответа нет.
            out = dict(cand_src[0])
            out["diag"] = dict(out.get("diag", {}), arbiter={"single": True})
            out["partial"] = cut or out.get("partial")
            return out

    if len(picked) > 1:
        try:
            lab_by = {r[0]: r[1] for r in psql(
                "SELECT src_table, label FROM %s WHERE src_table IN (%s)"
                % (TABLES, ", ".join(lit(c) for c in picked))) if r and r[0]}
        except RuntimeError:
            lab_by = {}
        opts = [{"src": t, "label": lab_by.get(t, t), "distinct_by": marks.get(t, ""),
                 "found": by.get(t, 0)} for t in picked]
        diag["ambiguous"] = [o["src"] for o in opts]
        return {"partial": cut or None, "kind": "clarify", "text": clarify_text(question, opts),
                "options": opts, "sources": [o["label"] for o in opts],
                "diag": dict(diag, sec=round(time.time() - t0, 2))}
    # 🔴 НЕ ОТВЕЧАТЬ, ПОКА ВЫБОР СУЩНОСТИ НЕ ПОДТВЕРЖДЁН. Решение владельца 30.07 — «правило в
    # сервисе в этом случае», — принято ПОСЛЕ того, как оба штатных средства движка были
    # проверены замером и оказались недостаточны:
    #
    #   `before_agent_finalize` → `{action:"revise"}` — движок честно отменил ход и прогнал
    #     модель заново («requested one more pass, attempt=1/3» в журнале шлюза), но модель
    #     указание ПРОИГНОРИРОВАЛА и повторила прежний ответ без обращения к данным;
    #   `tool_choice: "required"` — ушёл в ПЕТЛЮ: пять вызовов подряд, шесть минут вместо
    #     тридцати секунд, ответа нет. Модель обязана звать инструмент на каждом шаге и не
    #     может остановиться, чтобы ответить. Откачено.
    #
    # Вывод: заставить модель пойти за данными ИМЕННО ТОГДА, КОГДА НАДО, движок не умеет.
    # Гарантирует только запрет на выход — и он должен стоять там, где ответ рождается.
    #
    # Зачем правило нужно. Цель владельца: «100% правильных ответов, даже если для этого надо
    # 2-3 раза переспросить». Гейт исходящего этот класс не ловит по построению: число ЧЕСТНО
    # посчитано базой, просто не по той сущности — для гейта оно обосновано.
    # [замер 30.07, чистые сессии] из 10 вопросов 4 неверных, и во всех выбор был уверенным:
    # «НДС поставщикам» → регистр «уплаченный НДС» (2 719 573,23 вместо 11 036 086,09).
    #
    # Подтверждением считается ЛЮБОЕ из трёх, и все три — из данных, без порогов:
    #   1. человек выбрал сущность сам (`focus`) — спорить не с чем;
    #   2. сущность — ВЕРШИНА по вектору самого вопроса (считает база);
    #   3. слово вопроса совпало с ЕЁ АЛИАСОМ (`search_entity_alias`, собран один раз при
    #      установке штатным агентом OpenClaw). Сравнение — ПО ОСНОВАМ СЛОВ, штатным словарём
    #      движка (`search_dict_stem`, `techContext` возможность 35), а НЕ подстрокой:
    #      [замер 30.07] `contains('склады','складов')` ложна в обе стороны, и по подстроке
    #      верная сущность осталась бы неподтверждённой — система ушла бы в лишнее уточнение.
    #      Тот же приём уже применён в этом файле при отборе кандидатов.
    # Ни одно не выполнилось — система не знает, та ли это запись, и обязана спросить
    # (п. 12: догадка — ошибка; п. 21: уточнение стоит выше отказа).
    if REQUIRE_SUPPORT and picked and not focus:
        cand = picked[0]
        supported = (cand == top_by_question)
        if not supported:
            try:
                supported = bool(psql(
                    "SELECT 1 FROM search_entity_alias a, unnest(str_split(a.aliases, ',')) AS u(w) "
                    "WHERE a.src_table = %s AND trim(u.w) <> '' "
                    "  AND list_has_any(ts_lexize(%s, trim(u.w)), ts_lexize(%s, %s)) LIMIT 1"
                    % (lit(cand), lit(STEM_DICT), lit(STEM_DICT), lit(question))))
            except RuntimeError:
                # Знания нет вовсе (вики не собрана) — требовать подтверждения нечем, и
                # молчать система не должна: это не защита от выдумки, а требование опоры.
                supported = True
        if not supported:
            rivals = [c for c in ([top_by_question] if top_by_question else []) + list(cands)
                      if c and c != cand][:2]
            opts_src = [cand] + rivals
            try:
                lab_by = {r[0]: r[1] for r in psql(
                    "SELECT src_table, label FROM %s WHERE src_table IN (%s)"
                    % (TABLES, ", ".join(lit(c) for c in opts_src))) if r and r[0]}
            except RuntimeError:
                lab_by = {}
            if len(opts_src) > 1 and lab_by:
                opts = [{"src": t, "label": lab_by.get(t, t), "found": by.get(t, 0)}
                        for t in opts_src if t in lab_by]
                diag["unsupported_pick"] = cand
                return {"partial": cut or None, "kind": "clarify",
                        "text": clarify_text(question, opts),
                        "options": opts, "sources": [o["label"] for o in opts],
                        "diag": dict(diag, sec=round(time.time() - t0, 2))}

    src = picked[0] if picked else None
    if src not in by and not focus:
        # Модель назвала источник, куда поиск не попал: проверяем, есть ли там что-то
        # под наши условия, иначе остаёмся с тем, что реально нашлось. Выбор человека
        # (`focus`) так не перебиваем — он назвал сущность сам.
        probe_rows = rows_of(src, match, preds, 1) if src else []
        if not probe_rows and by:
            src = max(by.items(), key=lambda kv: kv[1])[0]
    # Выбрана табличная часть — отбор идёт ПО ШАПКЕ. Её собственный текст слов вопроса
    # не содержит (имя контрагента стоит в шапке), поэтому искать по нему нечего:
    # условие заменяется на «владелец строки попал в совпадения».
    if src in kid_pred:
        preds = preds + [kid_pred[src]]
        match = ""
        diag["via_parent"] = True

    diag["focus"], diag["found"] = src, by.get(src, 0)

    # НЕПОЛНОТА ИМЕННО ЭТОЙ СУЩНОСТИ (п. 13): «если из-за потери возможен неверный ответ,
    # система обязана уточнить или отказать, а не ответить по неполным данным». Первый шаг
    # — сказать. Отметка идёт ПОЛЕМ ответа, а не припиской в тексте: текст пишет модель на
    # языке вопроса, а проверяемым должно быть число.
    cov = _coverage_of(src)
    if cov:
        diag["incomplete"] = cov

    # ВЕЛИЧИНА ВЫБИРАЕТСЯ ПО ВОПРОСУ — после того, как известна сущность: её величины
    # лежат в самих данных. Числовое условие («больше 500000») тоже применяется здесь,
    # а не на общем отборе: у документа оно про сумму, у строки накладной могло бы
    # оказаться про количество.
    # 🔴 ПЕРВЫМ ДЕЛОМ — ВЕЛИЧИНА, КОТОРУЮ НАЗВАЛА МОДЕЛЬ, ЧИТАВШАЯ ВОПРОС. Её имя уже
    # сверено со списком величин ЭТОЙ сущности (`pick_entity`), то есть выдуманное имя сюда
    # не доходит. Прежний путь (`pick_measure`) остаётся запасным: он выбирает по похожести
    # имён, не видя вопроса, и именно поэтому ошибался.
    measure, measure_alts = None, []
    if plan.get("quantity") and plan["quantity"] in measures_of(src):
        measure = plan["quantity"]
        diag["measure_by_plan"] = True
    else:
        measure, measure_alts, how = pick_measure(src, question,
                                                  (intent.get("measure") or ""))
        # 🔴 ДОГАДКА РЕРАНКЕРА НЕ ГОДИТСЯ ТАМ, ГДЕ СПРАШИВАЮТ ВЕЛИЧИНУ. [замер 30.07]
        # «Сколько НДС мы заплатили поставщикам?» — модель не смогла назвать величину
        # (её у выбранного регистра нет), и прежний путь молча брал «КОплате»: ответ
        # 13 777 225,30 вместо 11 036 086,09. Три прогона из трёх.
        # Реранкер выбирает по похожести ИМЁН, не видя вопроса, — это ровно догадка, а
        # догадка запрещена (п. 12). Спрашиваем человека, какую величину считать.
        if how == "rerank" and (plan.get("compute") in ("sum", "max", "min", "avg")
                                or intent.get("want") == "sum"):
            alts = measures_of(src)
            if len(alts) > 1:
                measure, measure_alts = None, alts
                diag["measure_guess_refused"] = how
    if plan.get("compute"):
        diag["compute"] = plan["compute"]
    if measure_pick:                           # человек уже выбрал величину кнопкой
        measure, measure_alts = measure_pick, []
    diag["measure"] = measure
    # Несколько величин подходят одинаково — спрашиваем, какую считать. Механизм тот же,
    # что для сущности: кнопки из ДАННЫХ плюс «свой вариант» (решение владельца 28.07).
    if measure_alts:
        diag["measure_ambiguous"] = measure_alts
        opts = [{"src": src, "measure": m, "label": m} for m in measure_alts]
        return {"partial": cut or None, "kind": "clarify",
                "text": "Уточните, какую величину считать: %s."
                        % ", ".join("«%s»" % m for m in measure_alts),
                "options": opts, "sources": [src],
                "diag": dict(diag, sec=round(time.time() - t0, 2))}
    # Величина не названа — считаем итоги по всем и показываем модели с именами.
    totals = [] if measure else totals_of(src, match, preds, measures_of(src))
    if totals:
        diag["totals"] = {m: [v, mx, mn] for m, v, mx, mn in totals}
    preds = preds + _num_pred(intent, measure)
    rows = rows_of(src, match, preds, TOPK, measure)
    if not rows:
        return {"partial": cut or None, "kind": "no_data", "text": NO_DATA_TEXT or refuse_text(question), "sources": [],
                "diag": dict(diag, sec=round(time.time() - t0, 2))}

    agg = aggregate(src, match, preds, measure)
    # Числа неполноты разрешены гейту наравне с порогами вопроса: иначе фраза «не дошло
    # 104 строки» была бы отвергнута как выдумка, и система замолчала бы ровно там, где
    # обязана предупредить.
    # Числа ИЗ САМОГО ВОПРОСА разрешены в ответе: если человек спросил «обороты по счёту
    # 62», модель эхом называет «62» — это не выдуманная величина, а его же слово. Прежде
    # гейт отвергал верный ответ (сумма 23 742 200 посчитана верно) только из-за «62» в
    # тексте [замер 28.07]. Берём числа из вопроса как ещё один разрешённый набор.
    q_nums = [float(re.sub(r"[^\d]", "", n)) for n in re.findall(r"\d[\d.]*", question)
              if re.sub(r"[^\d]", "", n)]
    extra_vals = _threshold_values(intent) + [x for t in (totals or []) for x in t[1:]] \
                 + ([cov["in_1c"], cov["in_search"], cov["missing"]] if cov else []) \
                 + q_nums
    raw = compose(question, rows, agg, totals=totals, coverage=cov)
    text, claims = _split_answer(raw)
    ask_back = _ask_back(raw)
    # КАЛЬКУЛЯТОР: числа ставит код, а не модель. Всё, что подставлено, посчитано базой,
    # поэтому проверять его не нужно — оно верно по построению.
    text, slots_bad = _fill_figures(text, agg, totals, bool(measure))
    ask_back, _ = _fill_figures(ask_back, agg, totals, bool(measure))
    # Место, которому нечего подставить, — отказ формулировки: модель сослалась на
    # величину, которой мы не считали. Это единственная проверка, оставшаяся от прежней
    # ролевой сверки, и она структурная, а не числовая.
    ok_roles = not slots_bad
    bad_roles = ["нераспознанное место: %s" % x for x in slots_bad[:3]]

    # Проверка «ответ обязан объявить величину через claims» УБРАНА вместе с самими
    # claims: теперь величина попадает в текст подстановкой, и объявлять её отдельно
    # незачем. Осталась одна проверка того же смысла — ниже.
    #
    # Числа словами: если величина посчитана, а в тексте НЕТ НИ ОДНОЙ цифры — значит
    # модель написала «примерно три миллиона» вместо места под подстановку. Признак
    # детерминируемый, списка числительных не нужно.
    if agg and intent.get("want") in ("sum", "count") and not _norm_numbers(text):
        ok_roles, bad_roles = False, bad_roles + ["величина названа не цифрами"]
    ok_nums, bad_nums = gate(text, rows, agg, extra_vals)
    ok, bad = (ok_roles and ok_nums), (bad_roles + bad_nums)
    # ОТВЕТ ОБЯЗАН ДОЙТИ, ЕСЛИ ОН ЕСТЬ. Решение владельца 27.07: «если данные есть, но по
    # нашей системе мы их не отдали — пропадает смысл проекта». Первая формулировка могла
    # не пройти проверку по своей вине (модель объявила число строк суммой), а данные при
    # этом посчитаны и верны. Даём ровно одну вторую попытку, назвав причину отказа, и
    # проверяем её ТЕМ ЖЕ гейтом. Ослабления проверки здесь нет: если и второй ответ не
    # сходится с базой, он не уйдёт.
    if not ok and agg:
        diag["retry"] = bad[:3]
        raw2 = compose(question, rows, agg, corrections=bad[:3], totals=totals, coverage=cov)
        text2, claims2 = _split_answer(raw2)
        text2, slots_bad2 = _fill_figures(text2, agg, totals, bool(measure))
        ok_roles2 = not slots_bad2
        bad_roles2 = ["нераспознанное место: %s" % x for x in slots_bad2[:3]]
        bad_txt2 = []
        ok_nums2, bad_nums2 = gate(text2, rows, agg, extra_vals)
        if ok_roles2 and ok_nums2 and (text2 or "").strip():
            text, claims, ask_back = text2, claims2, _ask_back(raw2)
            ok, bad = True, []
            diag["retry_ok"] = True
        else:
            bad = bad + (bad_roles2 + bad_txt2 + bad_nums2)[:3]
    diag["claims"] = claims or None
    if not ok:
        sys.stderr.write("ask GATE: числа вне данных: %s\n" % bad[:6])
        # Гейт отклонил формулировку модели. Числа при этом посчитаны базой и верны —
        # отдаём их СТРУКТУРОЙ, а не своей прозой: свой текст был бы на одном языке
        # независимо от языка вопроса. Вызывающий формулирует сам.
        if agg:
            return {"partial": cut or None, "kind": "figures", "text": (TOTAL_TEXT.format(
                        count=agg["count"],
                        sum=("%d" % agg["sum"]) if agg["sum"] == int(agg["sum"])
                            else "%.2f" % agg["sum"]) if TOTAL_TEXT
                        else refuse_text(question)),
                    "figures": {k: agg[k] for k in
                                ("count", "count_amount", "sum", "min", "max", "avg",
                                 "date_min", "date_max") if k in agg},
                    "sources": [src.split("_", 1)[1] if "_" in src else src],
                    "completeness": cov,
                    "diag": dict(diag, gate_rejected=bad[:6])}
        return {"partial": cut or None, "kind": "no_data", "text": NO_DATA_TEXT or refuse_text(question), "sources": [],
                "diag": dict(diag, gate_rejected=bad[:6])}

    tag = src.split("_", 1)[1] if "_" in src else src

    # СРЕДНЕЕ ЗВЕНО: ответ → УТОЧНЯЮЩИЙ ВОПРОС → отказ (п. 21).
    #
    # Прежде звеньев было два, и всё, что не отвечало на вопрос дословно, падало в отказ.
    # [замер 28.07] «Что покупало ООО Ромашка?»: в данных есть наши реализации в её адрес
    # на 1 236 800 руб., а её собственных закупок нет. Система отвечала «данных нет» —
    # формально верно, по делу бесполезно: спрашивавший почти наверняка имел в виду
    # именно эти продажи, а мы молчали, имея их посчитанными.
    #
    # Судья неоднозначности — МОДЕЛЬ, как и при выборе сущности. Порога здесь быть не
    # может: «отвечают ли эти строки на соседний вопрос» — суждение языковое, а не
    # числовое, и списком слов («покупало», «продали») оно не выражается — такой список
    # был бы хардкодом под русский язык и под эту конфигурацию.
    #
    # Уточнение возвращается ТОЛЬКО после гейта: числа в нём проверены базой наравне с
    # обычным ответом. Вопрос без данных не задаётся — иначе это переспрашивание вместо
    # работы, а не вместо молчания.
    if ask_back:
        diag["asked_back"] = True
        return {"partial": cut or None, "kind": "clarify",
                "text": (text.strip() + "\n\n" + ask_back).strip(),
                "question": ask_back, "options": [],
                # Величина не названа вопросом — тогда `agg` считает по пустому месту, и
                # `sum: 0` был бы не «нулём», а «не считали». Отдаём то же, что видела
                # модель: итоги по каждой величине сущности, с их именами из данных.
                "figures": ({k: agg[k] for k in
                             ("count", "count_amount", "sum", "min", "max", "avg",
                              "date_min", "date_max") if k in agg} if (agg and measure)
                            else {"count": (agg or {}).get("count")}),
                "totals": {m: {"sum": v, "max": mx, "min": mn} for m, v, mx, mn in (totals or [])},
                "sources": [tag],
                "diag": dict(diag, rows=len(rows), sec=round(time.time() - t0, 2), gate_ok=ok)}

    # 🔴 ОТВЕТ НАЗЫВАЕТ ВЕЛИЧИНУ, ПО КОТОРОЙ СЧИТАЛ. У сущности их бывает девять со словом
    # «сумма», и молчаливый выбор неотличим от догадки (п. 12). Дописывает КОД, а не модель:
    # имя приходит из данных, значит одинаково верно на любой конфигурации, и его нельзя
    # забыть. Приписка не дублируется, если модель уже назвала величину сама.
    text = text.strip()
    if measure and measure.lower() not in text.lower():
        text = "%s\n\nСчитано по величине «%s»." % (text, measure)
    return {"partial": cut or None, "kind": "answer", "text": text, "sources": [tag],
            "completeness": cov, "measure": measure,
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
        # `focus` — сущность, выбранная человеком после уточнения (кнопка/слово).
        focus = (req.get("focus") or "").strip() or None
        # Выбор величины кнопкой — такой же вход, как `focus`. Без него уточнение о
        # величине было бы вопросом, на который нечем ответить.
        measure_pick = (req.get("measure") or "").strip() or None
        # Предыдущий разговор ведёт OpenClaw; сюда он приходит строкой и
        # используется ТОЛЬКО арбитром. В отбор данных не попадает.
        context = (req.get("context") or "")[:4000]
        try:
            out = answer(question, focus=focus, measure_pick=measure_pick,
                         context=context)
            # СВЕЖЕСТЬ ДАННЫХ — В КАЖДЫЙ ОТВЕТ (п. 18). Если 1С недоступна или такт падает,
            # корпус остаётся консистентным (защиты сборки), но СТАРЕЕТ, а бот об этом
            # молчал бы. Возраст последнего успешного такта делает старение видимым, а при
            # сильном отставании (сверх `ASK_STALE_WARN_SEC`, вдвое больше цикла и выше) —
            # явная приписка к ответу. Один дешёвый запрос, не на каждую ветку `answer`.
            try:
                r = psql("SELECT round(epoch(now()) - v) FROM search_quality WHERE k='build_ts'")
                age = int(_num(r[0][0])) if r and r[0] else None
            except RuntimeError:
                age = None
            if age is not None and isinstance(out, dict):
                out.setdefault("diag", {})["data_age_sec"] = age
                if age > STALE_WARN_SEC and out.get("kind") in ("answer", "figures", "clarify"):
                    mins = age // 60
                    out["text"] = (out.get("text", "") +
                                   "\n\n⚠ Данные могли устареть: последнее обновление из 1С "
                                   "было %d мин назад." % mins).strip()
                    out["stale"] = True
            return self._send(200, out)
        except Exception as e:                          # noqa: BLE001
            # 🔴 ЧЕСТНЫЙ ОТКАЗ ПРИ СБОЕ (п. 18), А НЕ ВЫДУМАННЫЙ ОТВЕТ. Любое исключение
            # по дороге (модель молчит, база/движок недоступны, эмбеддер не отвечает)
            # доходит СЮДА, а не превращается в ответ по частичным данным: `answer`
            # либо возвращает результат целиком, либо падает. Пользователю — понятное
            # сообщение по типу сбоя, БЕЗ внутренностей (`psql`, стек): их видит только
            # журнал. Класс сбоя определяем по тексту исключения, без утечки деталей.
            txt = str(e)
            sys.stderr.write("ask ERROR: %r\n" % (e,))
            low = txt.lower()
            if any(w in low for w in ("psql", "connection to server", "port", "postgres")):
                msg = "База данных временно недоступна. Повторите запрос через минуту."
            elif any(w in low for w in ("urlopen", "http", "timed out", "connection refused")):
                msg = "Языковая модель сейчас не отвечает. Повторите запрос через минуту."
            else:
                msg = "Сервис временно недоступен. Повторите запрос через минуту."
            return self._send(503, {"kind": "unavailable", "text": msg, "sources": [],
                                    "retry": True})


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
