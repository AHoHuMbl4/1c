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

# Шаг «достаточен ли вопрос для ответа» вынесен ОТДЕЛЬНЫМ файлом (05.08): его правила —
# чистые функции от разбора вопроса и от посчитанных чисел, и такие проверяются оффлайн,
# без базы, сети и денег (`test_enough.py`). Здесь остаётся только то, чего в чистой
# функции быть не может: обращение к модели, к базе и к гейту.
# Отсутствие файла (раскладка прежним `deploy.sh`) гасит шаг, а не роняет сервис: отказ
# при живых данных — дефект (п. 21), и он был бы куда хуже отключённой проверки.
try:
    import serene_enough
except ImportError:                                # noqa: F401 — шаг просто выключен
    serene_enough = None

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
# Разметка сущностей «о чём спрашивают / служебное» — её кладёт такт (`classify_entities.py`)
# и ею же задаёт очерёдность векторизации. Значения `business` / `service` — договор с той
# сборкой; неразмеченное считается деловым и там, и здесь.
CLASS_TABLE = "search_entity_class"
# Поверхность отбора «одна строка = одна сущность» (`entity_card_build.sql`): метка плюс
# синонимы, описание и имена величин. Вектор считается по ней целиком, а не по одной метке.
# Её может не быть вовсе (свежая база, старый такт) — тогда всё честно откатывается на
# метку: решает `emb_ready`, который без отметки модели возвращает «не готово».
CARD = os.environ.get("ASK_CARD_TABLE", "search_entity_card")
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
# След хода ответа в журнал сервиса (`journalctl -u 1c-serene-ask@…`). В самом ответе след
# лежит всегда (`diag.шаги`) — переключатель только про вывод в поток ошибок, чтобы его
# можно было погасить, не теряя следа там, где его читает прогонщик.
TRACE = os.environ.get("ASK_TRACE", "1") not in ("0", "false", "no")
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
# 🔴 Имена настроек не называют поставщика (как и у эмбеддера): реранкер переезжает в свой
# контур следом. `RERANK_API` выбирает вид запроса — `openai` (общий `/v1/rerank`,
# умолчание) или `dashscope` (прежний облачный). Прежние `ALIBABA_*` читаются как запасные.
RERANK_URL = (os.environ.get("RERANK_URL")
              or os.environ.get("ALIBABA_RERANK_URL")
              or "https://dashscope-intl.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank")
RERANK_MODEL = (os.environ.get("RERANK_MODEL")
                or os.environ.get("ALIBABA_RERANK_MODEL") or "qwen3-rerank")
RERANK_API = os.environ.get("RERANK_API",
                            "dashscope" if "dashscope" in RERANK_URL else "openai")
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

# 🔴 ИМЯ НАСТРОЙКИ НЕ НАЗЫВАЕТ ПОСТАВЩИКА. Прежние `ALIBABA_*` читаются, но только как
# запасной вариант: 02.08 эмбеддер переехал с dashscope на свой (Qwen3-Embedding-4B,
# OpenAI-совместимый), и имя переменной стало враньём. Поставщик — настройка, а не свойство
# кода: тот же путь работает с любым сервисом с совместимым API, включая внутренний
# (п. 16 `TARGET.md` — целевое состояние «модели внутри контура»).
# Умолчания НЕТ намеренно: адрес и модель эмбеддера человек обязан задать явно, иначе
# вопрос уйдёт в чужое облако молча.
EMBED_URL = (os.environ.get("EMBED_BASE_URL")
             or os.environ.get("ALIBABA_EMBED_URL", "")).rstrip("/")
# 🔴 ВОПРОС И ДОКУМЕНТ СЧИТАЮТСЯ ПО-РАЗНОМУ. Qwen3 обучен так, что запрос идёт с
# инструкцией, а документ без неё; звать их одинаково — молча потерять часть качества,
# и заметить это по ответу бота нельзя. Документы считает движок (`ai_embed` через
# OpenAI-совместимый путь, там всегда «документ»), а вопрос — мы, здесь, и обязаны
# сказать об этом явно. `EMBED_API=texts` — вид API, где такой признак есть.
EMBED_API = os.environ.get("EMBED_API", "openai")
EMBED_QUERY_PATH = os.environ.get("EMBED_QUERY_PATH", "/embed")
# Cloudflare перед сервисом режет клиента по подписи (`error code: 1010`): curl проходит,
# python — нет. Подпись задаётся настройкой, а не зашита: это свойство чужого периметра.
EMBED_UA = os.environ.get("EMBED_UA", "curl/8.5.0")
# Дверь, называющая РЕАЛЬНО загруженную модель. Открыта без ключа.
EMBED_HEALTH_URL = os.environ.get("EMBED_HEALTH_URL") or (EMBED_URL + "/health")
EMBED_KEY = os.environ.get("EMBED_API_KEY") or os.environ.get("ALIBABA_API_KEY", "")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "text-embedding-v4")
# Ключ реранкера может быть свой (он и живёт отдельным сервисом), а может совпадать с
# ключом эмбеддера, если они за одной дверью. Умолчание — второе, потому что так и было.
RERANK_KEY = os.environ.get("RERANK_API_KEY") or EMBED_KEY  # ключ реранкера может быть свой
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
# Приписка о старении. Ставится КОДОМ, поэтому написана на одном языке — настройкой
# выносится наружу по тому же образцу, что и две строки выше. Ровно один `%d` — минуты.
STALE_TEXT = os.environ.get(
    "ASK_STALE_TEXT",
    "\n\n⚠ Данные могли устареть: последнее обновление из 1С было %d мин назад.")


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


# 🔴 ВЕКТОРЫ РАЗНЫХ МОДЕЛЕЙ НЕСРАВНИМЫ, И ЭТО НЕ ВИДНО НИОТКУДА.
# [замер 02.08] эмбеддер переехал с `text-embedding-v4` на свой `Qwen3-Embedding-4B`.
# Вектор вопроса от новой модели и вектор строки от старой сравниваются БЕЗ ЕДИНОЙ ОШИБКИ
# и дают бессмысленную близость: система не падает, она начинает тихо выбирать не то.
# Это худший исход по контракту (п. 10, п. 12) — хуже отказа.
#
# Держать это правилом «не забыть перевекторизовать» нельзя: перевекторизация боевой базы
# идёт ЧАСАМИ ([замер 02.08] 4,6 строки/с — корпус около суток), и всё это время таблицы
# заведомо в разных состояниях. Поэтому запрет держится КОДОМ: каждая таблица с векторами
# несёт в переписи отметку, КАКОЙ моделью они посчитаны, и путь «по смыслу» включается
# только там, где отметка совпадает с моделью, которой считается вопрос. Не совпала или
# её нет — таблица для смыслового поиска не существует, работает буквальный отбор.
# Отметку ставит перевекторизация (`embed_all.sh`, `EMBED_RESET=1`), а не человек.
_EMB_OK_CACHE = {}
_EMB_LIVE_CACHE = [None, 0.0]


def embed_model_live():
    """Эмбеддер отдаёт ИМЕННО ту модель, которую мы просим?

    🔴 Спрашивать надо ответ, а не собственную настройку. [замер 02.08] наш эндпоинт при
    незнакомом имени модели молча подставляет свою: запрос с `model=…-Q8_0` возвращает
    HTTP 200 и вектор `…-Q6_K`. То есть смена модели на сервере — а она делается за
    секунды и без предупреждения — превращает вопрос и корпус в несравнимые величины,
    и ни одна ошибка об этом не скажет. Тот же разбор, что в `embed_check.sh`, только
    здесь он на живом пути ответа: сборку он остановить успевает, а бота — нет.
    """
    if _EMB_LIVE_CACHE[0] is not None and time.time() - _EMB_LIVE_CACHE[1] < 300:
        return _EMB_LIVE_CACHE[0]
    ok = False
    try:
        # 🔴 Имя модели берём из `/health`, а не из ответа на запрос. [замер 02.08] два
        # сервиса подряд соврали по-разному и оба молча: llama.cpp при незнакомом имени
        # подставлял своё, нынешний — возвращает ЭХОМ то, что попросили, и подтвердил
        # даже несуществующую модель. Поле `model` в ответе свидетельством не является.
        req = urllib.request.Request(EMBED_HEALTH_URL)
        req.add_header("User-Agent", EMBED_UA)
        with urllib.request.urlopen(req, timeout=20) as r:
            got = (json.loads(r.read()).get("model") or "").strip()
        ok = (got == EMBED_MODEL)
        if not ok:
            sys.stderr.write("🔴 ЭМБЕДДЕР ОТДАЁТ ДРУГУЮ МОДЕЛЬ: просим «%s», получаем «%s». "
                             "Поиск по смыслу выключен — векторы несравнимы.\n"
                             % (EMBED_MODEL, got))
    except Exception as e:                     # noqa: BLE001 — сеть/квота поставщика
        sys.stderr.write("эмбеддер не отвечает, поиск по смыслу выключен: %r\n" % (e,))
    _EMB_LIVE_CACHE[0], _EMB_LIVE_CACHE[1] = ok, time.time()
    return ok


def emb_ready(table):
    """Векторы этой таблицы посчитаны ТОЙ ЖЕ моделью, что считает вопрос?"""
    hit = _EMB_OK_CACHE.get(table)
    if hit is not None and time.time() - hit[1] < 60:
        return hit[0]
    if not embed_model_live():
        # Модель на сервере не та, что мы просим (или он молчит). Смысловой путь
        # выключается ЦЕЛИКОМ: буквальный отбор работает, догадки по чужим векторам нет.
        _EMB_OK_CACHE[table] = (False, time.time())
        return False
    try:
        rows = psql("SELECT note FROM search_quality WHERE k = %s" % lit("emb_model_" + table))
        ok = bool(rows) and (rows[0][0] or "").strip() == EMBED_MODEL
    except RuntimeError:
        # Не смогли спросить — считаем, что не совпало. Ошибка в эту сторону стоит
        # потери подсказки, в обратную — неверного ответа.
        ok = False
    _EMB_OK_CACHE[table] = (ok, time.time())
    return ok


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


def _embed_request(text, as_query):
    """Запрос к эмбеддеру. `as_query` — считать ВОПРОСОМ, а не документом (см. EMBED_API)."""
    if EMBED_API == "texts":
        url = EMBED_URL + EMBED_QUERY_PATH
        body = {"texts": [text], "is_query": bool(as_query), "dim": EMBED_DIM}
    else:
        url = EMBED_URL + "/embeddings"
        body = {"model": EMBED_MODEL, "dimensions": EMBED_DIM, "input": [text]}
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST")
    if EMBED_KEY:
        req.add_header("Authorization", "Bearer " + EMBED_KEY)
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", EMBED_UA)
    return req


# Вектор одного и того же текста за время ответа спрашивают несколько раз — разбор в
# `embed_one`. Это кэш ПРОЦЕССА, ограниченный размером: не хранилище, а защита от
# повтора внутри одного вопроса.
_EMB_ONE_CACHE = {}
EMB_ONE_CACHE_MAX = int(os.environ.get("ASK_EMB_CACHE", "256"))
# Сколько раз ПОВТОРИТЬ обращение к эмбеддеру, прежде чем считать его упавшим, и сколько
# ждать ответа. Это бюджет ожидания, а не порог правильности: числа влияют на то, сколько
# времени мы даём сервису, и ни на один выбор в ответе. Разбор — в `embed_one`.
EMB_RETRY = int(os.environ.get("ASK_EMB_RETRY", "2"))
EMB_RETRY_PAUSE = float(os.environ.get("ASK_EMB_RETRY_PAUSE", "0.4"))
EMB_TIMEOUT = int(os.environ.get("ASK_EMB_TIMEOUT", "60"))


def embed_one(text):
    """Вектор ВОПРОСА. Документы считает движок, сюда они не попадают.

    🔴 СБОЙ ОТДАЁТСЯ `RuntimeError` — ТЕМ ЖЕ КЛАССОМ, ЧТО И СБОЙ `psql` (`№26`). Иначе
    наружу летело сетевое исключение `urllib`, а места, где откат УЖЕ НАПИСАН, ловят
    `except RuntimeError` (порядок кандидатов по смыслу — `pass`; кандидаты от смысла —
    `cands = list(by)`). То есть откат не срабатывал ни разу, и недоступность эмбеддера
    роняла в 503 ровно там, где код собирался спокойно деградировать до буквального
    отбора. Там же, где вектор РЕШАЕТ выбор (поиск по смыслу при пустом буквальном
    отборе), обработчика нет намеренно: молча ответить «данных нет» было бы хуже отказа,
    потому что данные могли найтись по смыслу (п. 18).

    🔴 ОДИН ТЕКСТ — ОДИН ПОХОД К ЭМБЕДДЕРУ (04.08). За один ответ путь просит вектор
    одного и того же текста несколько раз: отбор по смыслу берёт вопрос и род записей,
    и следом их же берёт упорядочивание кандидатов. `[замер 04.08]` поход стоит **0,45 с**
    (сам kNN по меткам — 0,07 с), то есть повторы были самой дорогой частью шага 3.
    Кэш держится в пределах процесса и ограничен по размеру: вектор зависит только от
    текста и модели, а модель у процесса одна и проверяется отдельно (`emb_ready`).
    Ошибка не кэшируется — эмбеддер мог лечь на секунду.
    """
    hit = _EMB_ONE_CACHE.get(text)
    if hit is not None:
        return hit
    # 🔴 ПОВТОР ПЕРЕД ТЕМ, КАК СЧИТАТЬ ЭМБЕДДЕР УПАВШИМ (05.08, решение владельца).
    # Сбой эмбеддера теперь не проходит молча: смысловой путь выключается, и ответ уходит
    # в уточнение (`meaning_down`). Это верно для настоящего отказа и неверно для секундной
    # заминки — `[замер 05.08]` эмбеддер отдавал `TimeoutError` трижды за 25 минут на
    # боевых юнитах, и каждое такое событие превращало годный ответ в вопрос человеку.
    # Владелец 05.08: «надо для эмбеддинга просто защиту поставить, чтобы ретраи делал, а
    # не просто всё уходило на уточнение».
    #
    # Повтор ТОЛЬКО на сетевых сбоях и таймаутах: ответ с чужой моделью или сломанным
    # телом повторять бессмысленно — там не заминка, а несовместимость, и её ловит
    # `embed_model_live()`. Пауза растёт (0,4 с, 0,8 с) — иначе три подряд обращения к уже
    # перегруженному сервису делают хуже, а не лучше. Числа — бюджет ожидания, а не порог
    # правильности: они не решают, каким будет ответ, только сколько его ждать.
    last = None
    for attempt in range(EMB_RETRY + 1):
        try:
            with urllib.request.urlopen(_embed_request(text, True), timeout=EMB_TIMEOUT) as r:
                out = json.loads(r.read())
            vec = out["embeddings"][0] if EMBED_API == "texts" else out["data"][0]["embedding"]
            if attempt:
                sys.stderr.write("эмбеддер ответил с попытки %d\n" % (attempt + 1))
            break
        except RuntimeError:
            raise
        except Exception as e:                 # noqa: BLE001 — сеть/формат/таймаут
            last = e
            if attempt < EMB_RETRY:
                time.sleep(EMB_RETRY_PAUSE * (2 ** attempt))
    else:
        raise RuntimeError("эмбеддер недоступен: %s" % type(last).__name__)
    if len(_EMB_ONE_CACHE) >= EMB_ONE_CACHE_MAX:
        _EMB_ONE_CACHE.clear()                 # без вытеснения по одному: словарь мал
    _EMB_ONE_CACHE[text] = vec
    return vec


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
  "kind". A record need not contain the word naming its own kind.
- A word for a ROLE of a party (supplier, customer, employee, payer) names a kind of
  party, not a particular one. It belongs to "kind" or nowhere — a role word in "terms"
  narrows the search to records containing that word, and records rarely contain it.
- Group alternatives for the same concept together: expand abbreviations to their full
  form and add the inflections a record would realistically use. Example shape:
  [["X", "X-abbrev"], ["Y"]] — matching is AND between groups, OR inside a group.
- Never invent concepts that are not in the question.
- want = "sum" when the user asks for a total of ANY quantity, not only money;
  "count" when they ask how many records; otherwise "list".
- A numeric threshold belongs in "amount", never in "terms".
- A time range belongs in "period" as dates; `today` is given below.
- Unknown fields are null. No text outside the JSON."""


# 🔴 РАЗБОР ОТВЕТА МОДЕЛИ ДЕРЖИТСЯ КОДОМ, А НЕ ПРОСЬБОЙ В ПРОМТЕ.
#
# Промт выше описывает форму JSON — и это всё, на что он влияет. Что модель пришлёт на
# самом деле, промт не решает: `kind` приходит списком, `measure` числом, `period.from`
# словом «мая», `terms` строкой вместо списка списков. Проверка формы — работа кода
# (правило владельца 03.08 про промты), и здесь она сделана типами, а не пожеланием.
#
# Что было до 04.08 и чем это кончалось (пробы — `test_intent.py`, 60 случаев):
#   * `kind` списком или числом — `AttributeError` на `.strip()`, вопрос получал 503
#     «Сервис временно недоступен» на ровном месте (п. 21: отказ при наличии данных);
#   * `measure` не строкой — то же падение, но ПОСЛЕ выбора сущности и счёта, то есть
#     после самой дорогой части ответа (11,8 с) и после трат на модель;
#   * `period` строкой — падение в `_predicates`; `period.from = "2024"` или «мая» —
#     без падения: строка уходила в SQL как есть, и вопрос получал либо ошибку движка,
#     либо ЧУЖОЙ период. Второе хуже: это неверный ответ, а не отказ (п. 3, п. 10);
#   * `amount.value = "500 000"` — `ValueError` в `_num_pred`;
#   * `terms` строкой «Ромашка» — раскладывалось В БУКВЫ: `[["Р"],["о"],["м"],…]`, и
#     буквальный отбор шёл по подстроке «р» AND «о» AND «м», то есть по всему корпусу.
#     Ответ при этом выдавался — посчитанный по мусорному множеству;
#   * болтливый ответ («Sure! Here is the JSON: …») — жадное `{.*}` захватывало скобки
#     рассуждения, разбор молча вырождался в пустой, и вопрос отвечался вслепую.
#
# Общее у всех восьми — сбой разбора был НЕОТЛИЧИМ от честного «в вопросе нет понятий».
# Поэтому здесь два выхода вместо одного: структура с пометкой, что из вопроса потерялось
# (уходит человеку через `partial`, п. 13), и `RuntimeError`, когда разбора нет вовсе.
_WANT_OK = ("list", "sum", "count")
_ABOUT_OK = ("data", "coverage")
# 🔴 «=» СТОИТ ЗДЕСЬ ПО ЗАМЕРУ, А НЕ ДЛЯ ПОЛНОТЫ. [замер 04.08] вопрос приёмки №55
# «Сколько документов реализации с нулевой суммой?» модель разбирает в `op: "="`,
# `value: 0` — знак, которого в перечне не было. Условие пропадало МОЛЧА, и вопрос про
# нулевые документы получал счёт ВСЕХ документов реализации: неверный ответ, ничем не
# отличимый от верного (п. 3, п. 10).
_AMOUNT_OPS = ("=", ">", "<", ">=", "<=", "between")
_INTENT_FIELDS = ("terms", "kind", "measure", "want", "period", "amount", "about")
# Сколько прогонов разбора допустимо на один вопрос и какой отрыв лидера считается
# согласием. 1 прогон — прежнее поведение. Это бюджет ТОЧНОСТИ входа, а не подстройка
# под базу: от данных и от языка он не зависит.
INTENT_SAMPLES = int(os.environ.get("ASK_INTENT_SAMPLES", "5"))
INTENT_LEAD = int(os.environ.get("ASK_INTENT_LEAD", "3"))
# Память разобранных вопросов: ключ — текст вопроса и дата, значение — готовый разбор.
INTENT_MEMO = int(os.environ.get("ASK_INTENT_MEMO", "512"))
_INTENT_MEMO = {}
# Сколько понятий вопроса и сколько написаний одного понятия доходит до отбора. Это
# БЮДЖЕТ запроса (`probe` строит по четыре проверки на каждое написание, все в одном
# SQL), а не суждение о вопросе: он не зависит от базы и не подбирается под неё. Всё,
# что срезано бюджетом, попадает в `lost` и видно человеку — иначе снятое условие
# молча расширяет ответ (п. 13).
INTENT_GROUPS = int(os.environ.get("ASK_INTENT_GROUPS", "6"))
INTENT_ALTS = int(os.environ.get("ASK_INTENT_ALTS", "6"))
# Словарь, которым движок приводит написания к одному терму. Заводится сборкой
# (`corpus_init.sql`), локаль берёт из настройки базы — своего разбора слов у нас нет.
STEM_DICT = os.environ.get("ASK_STEM_DICT", "search_dict_stem")


def _json_blocks(raw):
    """Сбалансированные объекты `{...}` из ответа модели, в порядке появления.

    Скобки внутри строковых значений и экранирование учитываются, поэтому текст вокруг
    JSON (заборы ```json, вступление, рассуждение со скобками) на разбор не влияет.
    """
    out, depth, start, in_str, esc = [], 0, None, False, False
    for i, ch in enumerate(raw or ""):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}" and depth:
            depth -= 1
            if depth == 0 and start is not None:
                out.append(raw[start:i + 1])
                start = None
    return out


def _intent_text(v):
    """Значение поля как непустая строка. Список — первый непустой элемент; иначе None."""
    if isinstance(v, (list, tuple)):
        for item in v:
            s = _intent_text(item)
            if s:
                return s
        return None
    if v is None or isinstance(v, (dict, bool)):
        return None
    s = str(v).strip()
    return s or None


def _intent_number(v):
    """Число из значения любого вида: «500 000», «1 234,56» → float. None — числа нет."""
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if not isinstance(v, str):
        return None
    s = v.replace(" ", "").replace(" ", "").replace(" ", "")
    if s.count(",") == 1 and "." not in s:
        s = s.replace(",", ".")
    else:
        s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def _intent_date(v):
    """Дата вида YYYY-MM-DD (и только такая) — приведённая к канону. Иначе None.

    Другие написания сюда не пускаются намеренно. «01.02.2024» — это и 1 февраля, и
    2 января: разобрать его значило бы выбрать наугад между двумя прочтениями, а это
    п. 12 контракта. Отброшенная граница периода видна человеку через `lost`.
    """
    s = _intent_text(v)
    if not s:
        return None
    try:
        return time.strftime("%Y-%m-%d", time.strptime(s, "%Y-%m-%d"))
    except ValueError:
        return None


def _intent_terms(raw_terms, lost, fixed):
    """Понятия вопроса: список групп написаний. Мусор отбрасывается, потери — в `lost`."""
    if raw_terms is None:
        return []
    if isinstance(raw_terms, (str, int, float)):
        # Одно понятие, присланное строкой. Раньше строка попадала в цикл как
        # последовательность и рассыпалась на буквы.
        fixed.append("terms as text")
        raw_terms = [[raw_terms]]
    if not isinstance(raw_terms, (list, tuple)):
        lost.append("terms")
        return []
    groups, dropped_alts = [], 0
    for item in raw_terms:
        alts_in = item if isinstance(item, (list, tuple)) else [item]
        alts = []
        for a in alts_in:
            s = _intent_text(a)
            if s is None:
                dropped_alts += 1
                continue
            if s not in alts:
                alts.append(s)
        if not alts:
            continue
        if len(alts) > INTENT_ALTS:
            dropped_alts += len(alts) - INTENT_ALTS
            alts = alts[:INTENT_ALTS]
        groups.append(alts)
    if len(groups) > INTENT_GROUPS:
        # Срезанное понятие — это снятое условие отбора: ответ считается по более
        # широкому множеству, чем спросили. Молчать об этом нельзя (п. 13).
        lost.append("concepts:%d" % (len(groups) - INTENT_GROUPS))
        groups = groups[:INTENT_GROUPS]
    if dropped_alts:
        fixed.append("spellings:%d" % dropped_alts)
    return groups


def _intent_word(s):
    """Слово для сравнения: только буквы и цифры, нижний регистр. Списка слов здесь нет."""
    return re.sub(r"[^\w]+", " ", (s or ""), flags=re.U).lower().strip()


# 🔴 ОДНО ПОНЯТИЕ, РАЗЛОЖЕННОЕ ПО РАЗНЫМ ГРУППАМ, — ЭТО ЛИШНЕЕ УСЛОВИЕ «И».
# Между группами отбор идёт «И», внутри группы — «ИЛИ» (`probe`, `match_expr`).
# [замер 04.08] вопрос приёмки №40 «Сколько мы продали Альтаиру?» разбирается в ДВЕ
# группы — «Альтаир» и «Альтаиру», — и строка обязана содержать оба написания сразу.
# Такого не бывает: строка несёт одно из них, и вопрос про существующего клиента уходил
# в отказ «значения из вопроса не найдены» (п. 21).
#
# 🔴 РОДСТВО РЕШАЕТ ДВИЖОК, А НЕ МОЁ СРАВНЕНИЕ СТРОК. Первая редакция считала родными
# написания, входящие одно в другое, — то есть свой разбор слова поверх движка, у
# которого для этого есть штатное средство (доки SereneDB, `sql/functions/search/full-text`
# → `ts_lexize(dictionary, text)`; шаблоны словарей — `sql/statements/
# create_text_search_dictionary`). Словарь со стеммингом в проекте УЖЕ ЗАВЕДЁН —
# `search_dict_stem` (`corpus_init.sql`), ровно для сопоставления слова человека с
# названием. Проверено на живой сборке 26.07.3 `[замер 04.08]`:
# «Альтаир»/«Альтаиру» → `{альтаир}` оба, «товар»/«товаров» → `{товар}` оба,
# «Ромашка»/«Сбербанк» → `{ромашк}`/`{сбербанк}` (разные), «BOSCH»/«техника» — разные.
# Подмножество считается родством: «ООО "Ромашка"» → `{оо,ромашк}` ⊇ `{ромашк}`.
#
# Ошибка в сторону слияния расширяет отбор (то же понятие, больше написаний), в обратную —
# отбирает пустоту, поэтому при недоступности словаря группы остаются как есть.
def same_concept_groups(groups):
    """Свести группы, которые движок считает одним понятием. (группы, сколько сведено)."""
    if len(groups) < 2:
        return groups, 0
    flat = [a for g in groups for a in g]
    sel = ", ".join("ts_lexize(%s, %s)" % (lit(STEM_DICT), lit(a)) for a in flat)
    try:
        row = psql("SELECT " + sel)[0]
    except RuntimeError:
        return groups, 0
    merged, stems, k = [], [], 0
    for g in groups:
        merged.append(list(g))
        stems.append([frozenset(_stem_set(row[k + n])) for n in range(len(g))])
        k += len(g)
    i = 0
    while i < len(merged):
        j = i + 1
        while j < len(merged):
            родня = any(sa and sb and (sa <= sb or sb <= sa)
                        for sa in stems[i] for sb in stems[j])
            if родня:
                merged[i] += [b for b in merged.pop(j) if b not in merged[i]]
                stems[i] += stems.pop(j)
            else:
                j += 1
        i += 1
    return merged, len(groups) - len(merged)


def _stem_set(v):
    """Ответ `ts_lexize` — список термов. psql отдаёт его строкой вида `{a,b}`."""
    if isinstance(v, (list, tuple)):
        return {str(x) for x in v if str(x)}
    s = str(v or "").strip()
    if s.startswith("{") and s.endswith("}"):
        s = s[1:-1]
    return {p.strip().strip('"') for p in s.split(",") if p.strip()}


def _normalize_intent(d, question=""):
    """Ответ модели → структура шага 1 с пометкой, что из вопроса не доехало."""
    lost, fixed = [], []
    out = {"terms": _intent_terms(d.get("terms"), lost, fixed)}

    kind_raw, measure_raw = d.get("kind"), d.get("measure")
    if isinstance(kind_raw, (list, tuple)) and len(kind_raw) > 1:
        fixed.append("kind alternatives:%d" % (len(kind_raw) - 1))
    out["kind"] = _intent_text(kind_raw)
    if isinstance(measure_raw, (list, tuple)) and len(measure_raw) > 1:
        fixed.append("measure alternatives:%d" % (len(measure_raw) - 1))
    out["measure"] = _intent_text(measure_raw)

    # 🔴 РОД ЗАПИСЕЙ И ИМЯ ВЕЛИЧИНЫ — НЕ ЗНАЧЕНИЯ, И В `terms` ИМ НЕ МЕСТО.
    # `terms` — то, что стоит В САМОЙ ЗАПИСИ (имя контрагента, товар, номер документа);
    # по ним идёт буквальный отбор строк. Род записей туда попадать не может: запись не
    # содержит слова, называющего её род (об этом же говорит промт — и одного промта, как
    # обычно, недостаточно). [замер 04.08] на приёмочном наборе модель кладёт в `terms`
    # имя величины у вопроса 2 («НДС» при `measure`=«НДС»): буквальный отбор сужается до
    # строк со словом «НДС», а не найдя таких, система отвечает «значения из вопроса не
    # найдены» — ОТКАЗ при наличии данных (п. 21).
    # Сравнение — по совпадению целиком, а не по вхождению: «Приобретение товаров» при
    # роде «приобретение» — законное значение, и вырезать его значило бы снять условие.
    названо = {_intent_word(x) for x in (out["kind"], out["measure"]) if x}
    if названо:
        groups, dropped = [], 0
        for g in out["terms"]:
            keep = [a for a in g if _intent_word(a) not in названо]
            dropped += len(g) - len(keep)
            if keep:
                groups.append(keep)
        if dropped:
            fixed.append("kind/measure in terms:%d" % dropped)
        out["terms"] = groups

    want = (_intent_text(d.get("want")) or "").lower()
    if want and want not in _WANT_OK:
        # Чужое значение — не отказ: счёт величины решается шагом 4 по самому вопросу.
        fixed.append("want:" + want[:16])
        want = ""
    out["want"] = want or "list"

    about = (_intent_text(d.get("about")) or "").lower()
    out["about"] = about if about in _ABOUT_OK else "data"

    period, p_in = {}, d.get("period")
    if isinstance(p_in, dict):
        for edge in ("from", "to"):
            raw_edge = p_in.get(edge)
            if raw_edge is None:
                continue
            iso = _intent_date(raw_edge)
            if iso:
                period[edge] = iso
            else:
                lost.append("period." + edge)
    elif p_in:
        lost.append("period")
    if period.get("from") and period.get("to") and period["from"] > period["to"]:
        # Перевёрнутый период даёт пустое множество, то есть «данных нет» на вопрос,
        # у которого данные есть. Менять границы местами — догадка (п. 12).
        lost.append("period.order")
        period = {}
    out["period"] = period

    amount, a_in = {}, d.get("amount")
    if isinstance(a_in, dict):
        op = _intent_text(a_in.get("op"))
        val = _intent_number(a_in.get("value"))
        val2 = _intent_number(a_in.get("value2"))
        if op and op not in _AMOUNT_OPS:
            lost.append("amount.op")
        elif op and val is None:
            lost.append("amount.value")
        elif op == "between" and val2 is None:
            lost.append("amount.value2")
        elif op:
            amount = {"op": op, "value": val, "value2": val2}
    elif a_in:
        lost.append("amount")
    out["amount"] = amount

    # 🔴 УСЛОВИЕ, КОТОРОГО В ВОПРОСЕ НЕ БЫЛО, — ДОГАДКА, И ОНА ВИДНА (п. 12).
    # [замер 04.08] «Сколько мы продали за год?» разбирается в период
    # 2025-08-04…2026-08-04 — год НАЗАД ОТ СЕГОДНЯ. В вопросе такого года нет, данные
    # кончаются 2019-11-18, и отбор по этому периоду даёт пустоту: система отвечает
    # «данных нет» на вопрос, у которого данные есть за пять лет. Приёмка ждёт здесь
    # уточнения (`ACCEPTANCE_UT` №28) — «за год» это и календарный год, и последние
    # двенадцать месяцев, и любой из пяти.
    # Признак считается кодом и без языка: цифры года ищутся в самом вопросе.
    цифры = set(re.findall(r"\d+", (question or "").replace(" ", "").replace(" ", "")))
    assumed = [e for e, v in period.items()
               if not any(v[:4] in x for x in цифры)]
    out["parse"] = {"ok": True, "lost": lost, "fixed": fixed,
                    "assumed": ["period." + e for e in sorted(assumed)]}
    return out


def _one_intent(msgs, question):
    """Один разбор вопроса моделью, проверенный по типам."""
    raw = ds_chat(msgs, max_tokens=400)
    d = _first_intent_object(raw)
    if d is None:
        # 🔴 ВТОРАЯ ПОПЫТКА, А НЕ ПУСТОЙ РАЗБОР. Прежняя редакция при неразобранном
        # ответе возвращала `{"terms": [], …}` — то есть тот же вид, что и у честного
        # «в вопросе нет понятий», и вопрос отвечался вслепую по вектору. Разница
        # между «модель не ответила» и «спросили без условий» стоит одного повтора:
        # шаг 1 занимает 1,6 с из 17,6 с ответа.
        raw2 = ds_chat(msgs + [{"role": "assistant", "content": (raw or "")[:400]},
                               {"role": "user", "content": "Return the JSON object."}],
                       max_tokens=400)
        d = _first_intent_object(raw2)
    if d is None:
        raise RuntimeError("модель не вернула разбор вопроса")
    return _normalize_intent(d, question)


def _field_key(v):
    return json.dumps(v, ensure_ascii=False, sort_keys=True)


def _field_lead(samples, f):
    """(победитель, отрыв от второго) по полю. Отрыв — насколько согласие устойчиво."""
    keys = [_field_key(s.get(f)) for s in samples]
    counts = {}
    for k in keys:
        counts[k] = counts.get(k, 0) + 1
    order = sorted(counts, key=lambda k: (-counts[k], keys.index(k)))
    lead = counts[order[0]] - (counts[order[1]] if len(order) > 1 else 0)
    return order[0], lead, len(counts)


def _merge_intents(samples):
    """Согласие нескольких разборов ОДНОГО вопроса, поле за полем.

    Побеждает значение, встретившееся чаще; при равенстве — то, что пришло раньше.
    Поля, по которым согласия не было, перечислены в `parse.unstable`: это не отказ,
    а след, по которому видно, какой вопрос система читает по-разному.
    """
    if len(samples) == 1:
        one = dict(samples[0])
        one["parse"] = dict(one.get("parse") or {}, unstable=[], samples=1)
        return one
    out, unstable = {}, []
    for f in _INTENT_FIELDS:
        best, _, distinct = _field_lead(samples, f)
        if distinct > 1:
            unstable.append(f)
        out[f] = json.loads(best)
    # Пометки разбора (что потерялось, что чинилось, что додумано) берутся у того
    # образца, который ближе всех к итогу: они описывают переход «ответ модели →
    # структура», и складывать их от разных образцов значило бы описывать разбор,
    # которого не было.
    near = max(samples, key=lambda s: sum(1 for f in _INTENT_FIELDS
                                          if _field_key(s.get(f)) == _field_key(out[f])))
    out["parse"] = dict(near.get("parse") or {}, unstable=unstable, samples=len(samples))
    return out


def parse_intent(question, today):
    """Текст вопроса → структура отбора. К базе и к данным этот шаг не обращается.

    Модель видит только вопрос: ни схемы, ни имён таблиц, ни строк (п. 19). Ответ
    модели проверяется здесь по типам; когда разобрать нечего — `RuntimeError`, и
    сервис отвечает честным отказом вместо ответа вслепую (п. 18).

    🔴 РАЗБОР БЕРЁТСЯ ПО СОГЛАСИЮ НЕСКОЛЬКИХ ПРОГОНОВ, А НЕ ОДНОГО.
    [замер 04.08, `intent_parse_bench.py`, 58 вопросов по 3 повтора] один и тот же
    вопрос при `temperature=0` разбирается по-разному в **18 случаях из 58**: расходятся
    `kind` («выручка»/«продажи», «номенклатура»/«позиции номенклатуры») и состав `terms`.
    Это нижняя граница разброса всего ответа: разный `kind` — это разный вектор на шаге 3,
    разные кандидаты на шаге 4 и, в конце, разное число. Прежде разброс приписывали одному
    шагу 4 (11,8 с), а его половина заводилась здесь, на самом дешёвом шаге (1,6 с).

    🔴 РАЗНИЦА СЛОВОФОРМ — НЕ МЕЛОЧЬ, И ЭТО ЗАМЕРЕНО. [замер 04.08] «товар» и «товаров»
    как запрос по смыслу дают из 32 кандидатов лишь 22 общих, а «выручка» и «продажи» —
    5 из 32. То есть согласие тут не про красоту разбора: от него зависит, какие сущности
    вообще доедут до выбора.

    Сколько прогонов делать, решает ОТРЫВ, а не постоянное число: прогоны идут, пока
    лидирующее значение не оторвётся от второго на `INTENT_LEAD`. [замер 04.08, по 9
    прогонов на вопрос] расклад расходящихся полей — 7:2, а не пополам: «отгрузка»×7 /
    «отгрузки»×2, «товаров»×7 / «товар»×2, «продажи»×6 / «выручка»×3. При таком раскладе
    отрыв в два прогона набирается за три-четыре обращения, а решает большинство, а не
    случайный первый ответ.

    🔴 ОДИН И ТОТ ЖЕ ВОПРОС РАЗБИРАЕТСЯ ОДИНАКОВО — ЭТО ДЕРЖИТСЯ ПАМЯТЬЮ, А НЕ
    ВЕЗЕНИЕМ. Даже отрыв оставляет несколько процентов на случай, а п. 3 контракта требует
    детерминированности. Разбор зависит ровно от двух вещей — текста вопроса и сегодняшней
    даты, — поэтому повтор берётся из памяти по этому ключу. Данные в ключ не входят и
    входить не могут: шаг 1 их не видит. Память чистится сменой даты и держит `INTENT_MEMO`
    последних вопросов; `ASK_INTENT_MEMO=0` выключает её — этим прибор меряет согласие
    модели, а не работу памяти.
    """
    memo_key = (today, question)
    if INTENT_MEMO > 0:
        hit = _INTENT_MEMO.get(memo_key)
        if hit is not None:
            return json.loads(hit)
    msgs = [{"role": "system", "content": INTENT_SYS},
            {"role": "user", "content": "today=%s\n\nQuestion: %s" % (today, question)}]
    samples = [_one_intent(msgs, question)]
    while len(samples) < max(1, INTENT_SAMPLES):
        if min(_field_lead(samples, f)[1] for f in _INTENT_FIELDS) >= INTENT_LEAD:
            break
        samples.append(_one_intent(msgs, question))
    out = _merge_intents(samples)
    # Сведение словоформ в одно понятие — после согласия и один раз на вопрос: словарь
    # спрашивается у движка, и делать это на каждый прогон разбора незачем.
    groups, сведено = same_concept_groups(out.get("terms") or [])
    if сведено:
        out["terms"] = groups
        out["parse"]["fixed"] = list(out["parse"].get("fixed") or []) + [
            "same concept groups:%d" % сведено]
    if INTENT_MEMO > 0:
        if len(_INTENT_MEMO) >= INTENT_MEMO:
            _INTENT_MEMO.clear()
        _INTENT_MEMO[memo_key] = json.dumps(out, ensure_ascii=False)
    return out


def _first_intent_object(raw):
    """Объект ответа, больше других похожий на разбор вопроса. None — такого нет.

    Похожесть считается по числу полей разбора: болтливый ответ может нести и обрывок
    вида `{"terms": []}`, и полный объект следом, а взятый по порядку первый обрывок
    потерял бы `kind` — то самое поле, по которому идут шаги 3 и 4.
    """
    best, best_score = None, -1
    for block in _json_blocks(raw):
        try:
            d = json.loads(block)
        except ValueError:
            continue
        if not isinstance(d, dict):
            continue
        score = sum(1 for k in ("terms", "kind", "want", "measure", "period",
                                "amount", "about") if k in d)
        if score > best_score:
            best, best_score = d, score
    return best


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
    # «=» здесь наравне с остальными: [замер 04.08] «с нулевой суммой» разбирается
    # именно в него, а без него условие пропадало молча — см. `_AMOUNT_OPS`.
    if op in ("=", ">", "<", ">=", "<="):
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


def _like_pattern(alt):
    """Слово вопроса -> образец `ts_like`, где знаки слова остаются знаками.

    🔴 ЗАЧЕМ. `ts_like` принимает SQL-образец: `%` значит «сколько угодно любых знаков»,
    `_` — «ровно один любой» (доки движка `sql/functions/search/full-text`, там же
    экранирование обратной косой: `\\%` и `\\_`). Слово в образец попадает из ВОПРОСА
    ЧЕЛОВЕКА, и эти знаки в нём встречаются: «какая наценка в %», код склада `A_12`,
    процент в названии тарифа. Без экранирования «%» превращался в «что угодно», образец
    вырождался в `%%%` и совпадал с каждым термом индекса — буквальный отбор возвращал
    ВСЕ сущности базы. Ошибки при этом не возникало ни одной: отбор просто переставал
    отбирать, а шаг выбора получал перечень, в котором нечего различать.

    Возвращает None, если после экранирования искать нечего (пустое слово): образец
    `%%` — это «любой терм», то есть тот же вырожденный случай, только тише.
    """
    s = (alt or "").lower()
    if not s.strip():
        return None
    # Порядок важен: сперва сама косая, иначе экранируется добавленное нами же.
    s = s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return "%" + s + "%"


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
            variants.append(("fuzzy", "ts_levenshtein(%s, %d)"
                             % (lit(alt), min(2, len(alt) // 4))))
            pat = _like_pattern(alt)
            if pat is not None:
                variants.append(("part", "ts_like(%s)" % lit(pat)))
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
        # 🔴 РАЗРЕШЁННОЕ РЕЗОЛВЕРОМ ПОНЯТИЕ — НАЙДЕННОЕ. Прежде отметка ставилась всем,
        # КРОМЕ разрешённых резолвером, а вызывающий считает найденные понятия ровно по
        # этим отметкам (`matched_groups`). Выходило, что резолвер отрабатывал, значения
        # находил, выражение поиска возвращал — и тут же объявлялся неудачей: у вопроса из
        # одного понятия `matched_groups` = 0, и `answer` отдавал `no_data` ДО того, как
        # запрос вообще собирался. То есть путь, заведённый ради «Питера» (`resolve_values`:
        # подстрокой 0, в базе 180 записей про Санкт-Петербург), гасил сам себя на
        # единственном классе вопросов, ради которого сделан, — а отказ при наличии данных
        # это дефект (п. 21 `TARGET.md`), не осторожность.
        # Сами значения по-прежнему лежат отдельно, в `_resolved`: они уходят в ответ,
        # чтобы человек видел, каким словом его слово поняли (п. 13).
        diag[gi] = kind
    return out, diag


def matched_group_count(kinds):
    """Сколько понятий вопроса нашли себе совпадение — считая разрешённые резолвером.

    Отдельной функцией, а не строкой внутри `answer`, по одной причине: от этого числа
    зависит отказ («значения из вопроса не найдены в данных»), то есть решение не отвечать
    при живых данных. Прибор `test_step2.py` проверяет его без базы, сети и модели.

    Ключи-числа в `diag` ставит `probe` каждому найденному понятию; строковые ключи
    (`_resolved`) несут значения, а не отметки, и в счёт не идут.
    """
    return len([g for g in (kinds or {}) if isinstance(g, int)])


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


def partial_tables(exprs, preds, best):
    """Сущности, у которых нашлась ЧАСТЬ понятий вопроса, — с их собственным уровнем.

    🔴 ЗАЧЕМ. `match_expr` выбирает ОДИН порог `k` на всю базу: наибольшее число понятий,
    при котором хоть где-то есть совпадения. Порог глобальный, а ставит его та сущность,
    где слова вопроса встретились гуще всего, — обычно это служебный справочник, в котором
    помянуты все слова сразу. Все, кто нашёл на одно понятие меньше, отсекаются НАЦЕЛО:
    их не видит ни шаг выбора, ни арбитр, ни человек.

    `[замер 04.08]` на 44 парах приёмки: при выбранном `k` эталонная сущность доходит до
    кандидатов в 5 случаях (11 %), а при «хотя бы одно понятие» — в 33 (75 %).
    **28 эталонов из 44 теряет сам порог**, и потеря молчаливая (п. 13): в ответе о ней
    нет ни слова, в журнале — тоже.

    Поэтому уровень считается ПО КАЖДОЙ СУЩНОСТИ ОТДЕЛЬНО: сколько понятий вопроса нашлось
    именно у неё. Один запрос на все понятия — число обращений к базе не растёт ни с числом
    понятий, ни с числом сущностей (п. 20).

    Возвращает ({сущность: уровень}, {сущность: своё условие поиска}) и только для тех,
    кто НЕ прошёл общий порог: прошедшие уже лежат в `by`, их отбор не меняется ни на знак.

    Число совпадений этим сущностям НЕ приписывается — как и кандидатам от синонимов и
    смысла. Строки у них есть, но посчитаны они по более мягкому условию, и подавать это
    тем же полем, которым модель различает кандидатов, значило бы сравнивать несравнимое.

    Своё условие нужно потому, что `match` живёт дальше отбора: по нему считаются итоги
    выбранной сущности (`aggregate`, `totals_of`, `rows_of`). Сущности, попавшей сюда,
    общий строгий `match` не отвечает — у неё столько понятий и нет. Приём тот же, что у
    табличных частей (`kid_pred`): у кандидата своё условие, и оно применяется, когда
    выбрали именно его.
    """
    n = len(exprs or [])
    if n < 2 or best <= 1:
        return {}, {}                  # порогу нечего отсекать — и терять нечего
    # 🔴 УРОВЕНЬ СЧИТАЕТСЯ ПО СТРОКЕ, А НЕ ПО СУЩНОСТИ ЦЕЛИКОМ. Считать «сколько понятий
    # встретилось где-нибудь у этой сущности» — заманчиво и неверно: понятие А может стоять
    # в одной строке, Б в другой, и тогда уровень 2 есть, а строки, отвечающей обоим,
    # нет ни одной. Условие `ts_compound(…, 2)` по такой сущности даёт ПУСТО, и кандидат,
    # добравшийся до выбора, посчитался бы нулём. Поймано собственным замером 04.08 на
    # четырёх сущностях (`document_приобретениетоваровуслуг_товары` и др.).
    # Поэтому спрашиваем базу прямо: при каком наибольшем `k` у сущности ЕСТЬ строка.
    # Столько же обращений, сколько понятий, и все — одним запросом (п. 20).
    # 🔴 Спрашиваем и САМ `best`, а не только уровни ниже. Иначе сущность, прошедшая общий
    # порог, получает здесь уровень `best-1` (строка, отвечающая `best` понятиям, отвечает
    # и `best-1`), попадает в частичные и уносит с собой СВОЁ, более мягкое условие — а по
    # нему потом считаются итоги. То есть сущность, честно совпавшая по всем понятиям,
    # посчиталась бы по ослабленному условию и дала бы завышенное число. Поймано собственным
    # прибором 04.08: `catalog_новости` — 1 строка по общему условию против 3 по мягкому.
    parts = []
    for k in range(best, 0, -1):
        where = " AND ".join(
            [with_refs("ts_compound(NULL, NULL, [%s], %d)" % (", ".join(exprs), k))]
            + [w for w in preds if w])
        parts.append("SELECT src_table AS t, %d AS k FROM %s WHERE %s GROUP BY 1"
                     % (k, INDEX, where))
    if not parts:
        return {}, {}
    level = {}
    try:
        for r in psql(" UNION ALL ".join(parts)):
            if not r or not r[0]:
                continue
            try:
                k = int(r[1])
            except (ValueError, IndexError):
                continue
            if k > level.get(r[0], 0):
                level[r[0]] = k
    except RuntimeError:
        return {}, {}                  # отбор без этой подсказки остаётся прежним
    out, pred_by = {}, {}
    for t, lvl in level.items():
        if lvl >= best or lvl < 1:
            continue                   # прошёл общий порог — он уже в `by`
        out[t] = lvl
        pred_by[t] = with_refs("ts_compound(NULL, NULL, [%s], %d)"
                               % (", ".join(exprs), lvl))
    return out, pred_by


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


def alias_hits(exprs, limit):
    """Сущности, чьи СИНОНИМЫ отвечают понятиям вопроса. Отбор ведёт база.

    🔴 ЭТО ПОИСКОВАЯ ПОВЕРХНОСТЬ, А НЕ ПОЗДНЯЯ ПРОВЕРКА. До 03.08 словарь синонимов
    (`search_entity_alias`, собирается один раз при установке штатным агентом) читался
    ТОЛЬКО в `_alias_verdict` — то есть после того, как сущность уже выбрана, и лишь
    затем, чтобы подтвердить или подобрать соперников. Знание при этом было верным и
    лежало без дела: [замер 03.08] у `document_реализациятоваровуслуг` синоним «продажа»
    в словаре есть, и по `alias_idx` эта сущность входит в тройку, тогда как буквальный
    отбор по тому же вопросу даёт её 272 совпадениями против 7 307 у регистра
    себестоимости — то есть топит верное в шуме.

    Условие берётся ТО ЖЕ, что и для корпуса (`probe` → `exprs`): ни одного нового
    способа сравнения, ни списка слов. `k=1` — «хотя бы одно понятие вопроса»: здесь мы
    не отвечаем, а лишь ДОБАВЛЯЕМ кандидата, которого дальше судят реранкер и модель.

    Разделитель равенства обязателен (`techContext` ловушка 30): без него `LIMIT`
    отрезает по порядку исполнения. [замер 03.08] по слову «продажа» четыре сущности
    имеют ровно одну оценку 4,6122875 — верный документ и три чужих (`F243`).
    """
    if not exprs:
        return []
    expr = exprs[0] if len(exprs) == 1 else \
        "ts_compound(NULL, NULL, [%s], 1)" % ", ".join(exprs)
    try:
        rs = psql("SELECT src_table, %s AS s FROM %s WHERE aliases @@ %s "
                  "ORDER BY s DESC, src_table LIMIT %d"
                  % (SCORERS.get(SCORER, SCORERS["bm25"]) % ALIAS_INDEX,
                     ALIAS_INDEX, expr, limit))
    except RuntimeError:
        return []                       # словаря нет (база без вики) — молча без него
    return [r[0] for r in rs if r and r[0]]


def card_hits(exprs, limit):
    """Сущности, чья КАРТОЧКА отвечает понятиям вопроса СЛОВАМИ. Отбор ведёт база.

    Четвёртая поверхность отбора (04.08). Карточка (`search_entity_card`) до сих пор
    служила только источником ВЕКТОРА, хотя такт строит по ней и инвертированный индекс:
    поверхность была построена и ни разу не спрошена. Спрашиваются все её поля разом —
    название, синонимы, описание, имена величин и имена реквизитов; движок допускает это
    одним запросом («a query may constrain any subset of the indexed fields, in any
    combination» — доки SereneDB, «Operator classes and fields»), а объединение через OR
    с одним скорером показано там же в разделе «Boosting».

    🔴 ЧТО ИМЕННО ОНА ДОБАВЛЯЕТ, ЧЕГО НЕТ У ОСТАЛЬНЫХ — имена реквизитов сущности.
    `[замер 04.08]` вопрос «Кто нам поставляет товар?» не доносила НИ ОДНА поверхность:
    в синонимах справочника партнёров слова «поставщик» нет, по смыслу он на 338-м месте
    (верх занят служебными «Использовать Соглашения СПоставщиками»), в корпусе тонет —
    164 его строки против 293 строк регистра себестоимости в первых четырёхстах по
    релевантности. А реквизит «Поставщик» у него есть, и по нему сущностей всего три.
    Своей поверхностью карточка доносит верную сущность в 32 случаях из 44 (73 %) — это
    больше любой другой лексической, — а в сумме с прочими закрывает последний вопрос
    набора: **44 из 44**.

    Цена `[замер 04.08]` — 63 мс на 1 502 карточки: индекс маленький, потому что в нём
    одна строка на сущность, а не на запись. Нет индекса (карточка не собрана, такт
    старый) — молча работаем без этой поверхности, как и без словаря синонимов.
    """
    if not exprs:
        return []
    expr = exprs[0] if len(exprs) == 1 else \
        "ts_compound(NULL, NULL, [%s], 1)" % ", ".join(exprs)
    cond = " OR ".join("%s @@ %s" % (f, expr) for f in CARD_FIELDS)
    try:
        rs = psql("SELECT src_table, %s AS s FROM %s WHERE %s "
                  # разделитель равенства — та же ловушка 30, что и у синонимов
                  "ORDER BY s DESC, src_table LIMIT %d"
                  % (SCORERS.get(SCORER, SCORERS["bm25"]) % CARD_INDEX,
                     CARD_INDEX, cond, limit))
    except RuntimeError:
        return []                       # индекса карточки нет — молча без него
    return [r[0] for r in rs if r and r[0]]


def question_exprs(exprs, kind_text):
    """ПОНЯТИЯ ВОПРОСА ЦЕЛИКОМ: значения из вопроса плюс род записей.

    Шаг 1 кладёт в `terms` ЗНАЧЕНИЯ (имя контрагента, товар), а род записей — в `kind`, и в
    `terms` его нет намеренно. `[замер 04.08]` у 47 вопросов из 58 `terms` пусты вовсе, то
    есть работая на одних `terms`, мы работаем на пустом месте. Понятия рода спрашиваются
    ОТДЕЛЬНЫМ `probe`, а не добавлением группы в общий: иначе изменились бы выражения
    буквального отбора, то есть тихо поменялся бы шаг 2.

    Вынесено отдельно, потому что этих понятий требуют ДВА разных места (отбор кандидатов
    смыслом и подтверждение выбора по словарю синонимов), а две копии неизбежно разошлись бы.
    """
    exprs_kind = []
    if kind_text:
        try:
            exprs_kind, _ = probe([[kind_text]])
        except RuntimeError:
            exprs_kind = []                 # база молчит — работаем на том, что есть
    return list(exprs) + [e for e in exprs_kind if e not in exprs]


def meaning_candidates(exprs, kind_text, question, limit, exclude=()):
    """ШАГ 3 ЦЕЛИКОМ: кандидаты, добытые не буквальным совпадением слов записи.

    Собран в одном месте по двум причинам. Первая: у шага появился свой прибор
    (`work/acceptance/step3_bench.py`), и он зовёт этот код, а не свою копию, — прежний
    прибор приближал разбор вопроса словами самого вопроса и показывал у поверхности
    синонимов 43 % там, где в бою было 5 %. Вторая: четыре поверхности с двумя входами
    каждая перестали читаться внутри `answer`.

    Четыре независимых источника, ни один не закрывает остальные:
      1. синонимы сущности   — `alias_hits`, словарь, собранный при установке;
      2. слова карточки      — `card_hits`, включая ИМЕНА РЕКВИЗИТОВ сущности;
      3. смысл вопроса       — `near_tables` по тексту вопроса;
      4. смысл рода записей  — `near_tables` по `kind` шага 1.
    Буквальный отбор (`by`) сюда не входит: он делается шагом 2 и приходит в `exclude`.

    🔴 ДВА ВХОДА, А НЕ ОДИН. Шаг 1 кладёт в `terms` ЗНАЧЕНИЯ (имя контрагента, товар), а
    род записей — в `kind`, и в `terms` его нет намеренно. Лексические поверхности
    описывают как раз род, поэтому им идут оба входа; смысловые спрашиваются и вопросом,
    и родом. `[замер 04.08]`, 44 пары приёмки, настоящие разборы шага 1: синонимы на
    `terms` доносят верную сущность 2 раза (5 %), на `terms`+`kind` — 21 (48 %); смысл на
    «род ИЛИ вопрос» — 20 (45 %), по вопросу — 29 (66 %). Сумма всех поверхностей вместе
    с буквальным отбором: было **23 из 44 (52 %)**, стало **44 из 44 (100 %)**.

    Понятия рода спрашиваются ОТДЕЛЬНЫМ `probe`, а не добавлением группы в общий: иначе
    изменились бы выражения буквального отбора, то есть тихо поменялся бы шаг 2.
    """
    exprs_all = question_exprs(exprs, kind_text)
    out = _fused_candidates(exprs_all, kind_text, question, limit)
    if out is None:
        # Слияние не собралось (нет карточки, лёг эмбеддер, старая база) — прежний путь:
        # те же поверхности по отдельности, порядок «одна за другой».
        out = []
        for src_from in (alias_hits(exprs_all, limit),
                         card_hits(exprs_all, limit),
                         near_tables(question, limit),
                         near_tables(kind_text, limit) if kind_text else []):
            for t in src_from:
                if t not in out:
                    out.append(t)
    return [t for t in out if t not in exclude]


def _fused_candidates(exprs, kind_text, question, limit):
    """Те же четыре поверхности, но СЛИТЫЕ ПО МЕСТАМ и ОДНИМ ЗАПРОСОМ внутри движка.

    🔴 Зачем слияние. Порядок, в котором кандидаты уходят дальше, решает, что вообще
    увидит модель: набор режется бюджетом перечня (`[замер 04.08]` живой ответ показал
    100 записей из 1502). Простая склейка «одна поверхность за другой» ставит вперёд ту,
    что оказалась первой в коде, а слияние ставит вперёд то, на чём поверхности СОШЛИСЬ.
    `[замер 04.08]`, 44 пары приёмки, настоящие разборы шага 1, глубина перечня как в бою:
    эталон доходит до модели 43 из 44 при склейке и **44 из 44** при слиянии, а верхним
    кандидатом оказывается верный 16 раз против 10.

    🔴 Считает БАЗА, а не питон: ранги ветвей и их сумма — один SQL по шаблону доков
    SereneDB («Cookbook → Search → Reciprocal Rank Fusion»): `RANK()` в каждой ветви,
    `SUM(1.0/(k + rank))` снаружи. Оттуда же `k = 60` — умолчание исходной статьи и
    Elasticsearch, а не подобранное нами число. Скорер стоит во ВЛОЖЕННОМ запросе, а
    агрегат снаружи: движок не даёт считать `bm25`/`tfidf` в одном запросе с `GROUP BY`
    (`techContext`, разбор у `serene_ask`).

    Ветвей четыре, каждая со своим окном `limit`: синонимы, слова карточки, смысл вопроса,
    смысл рода записей. Отсутствующая ветвь просто не даёт слагаемых — как и написано в
    доках («A document missing from a branch contributes nothing»).

    Возвращает `None`, если ни одна ветвь не собралась: тогда зовущий откатывается на
    прежний путь, а не остаётся без кандидатов.
    """
    expr = None
    if exprs:
        expr = exprs[0] if len(exprs) == 1 else \
            "ts_compound(NULL, NULL, [%s], 1)" % ", ".join(exprs)
    branches = []
    if expr:
        branches.append(
            "SELECT src_table, RANK() OVER (ORDER BY s DESC, src_table) AS rank FROM ("
            "SELECT src_table, %s AS s FROM %s WHERE aliases @@ %s "
            "ORDER BY s DESC, src_table LIMIT %d) t"
            % (SCORERS.get(SCORER, SCORERS["bm25"]) % ALIAS_INDEX, ALIAS_INDEX, expr, limit))
        branches.append(
            "SELECT src_table, RANK() OVER (ORDER BY s DESC, src_table) AS rank FROM ("
            "SELECT src_table, %s AS s FROM %s WHERE %s "
            "ORDER BY s DESC, src_table LIMIT %d) t"
            % (SCORERS.get(SCORER, SCORERS["bm25"]) % CARD_INDEX, CARD_INDEX,
               " OR ".join("%s @@ %s" % (f, expr) for f in CARD_FIELDS), limit))
    src = CARD if emb_ready(CARD) else (TABLES if emb_ready(TABLES) else "")
    if src:
        for text in (question, kind_text):
            if not text:
                continue
            try:
                vec = _vec(text)            # кэшируется на текст: см. `embed_one`
            except RuntimeError:
                continue                    # эмбеддер лёг — остаются лексические ветви
            branches.append(
                "SELECT src_table, RANK() OVER (ORDER BY d, src_table) AS rank FROM ("
                "SELECT src_table, emb <=> %s AS d FROM %s WHERE emb IS NOT NULL "
                "ORDER BY d, src_table LIMIT %d) t" % (vec, src, limit))
    if not branches:
        return None
    sql = ("WITH fused AS (%s) SELECT src_table, SUM(1.0/(%d + rank)) AS rrf "
           "FROM fused GROUP BY src_table ORDER BY rrf DESC, src_table LIMIT %d"
           % (" UNION ALL ".join(branches), RRF_K, limit * len(branches)))
    try:
        return [r[0] for r in psql(sql) if r and r[0]]
    except RuntimeError:
        return None                         # слияние не прошло — зовущий откатится


def near_tables(text, limit):
    """Сущности, чьи НАЗВАНИЯ ближе всего к вопросу по смыслу. Ранжирует движок.

    Мост через словарный разрыв: в 1С продажа называется «реализация», и буквально эти
    слова не совпадут никогда. [замер 03.08] `ts_phrase('продали')` по всему корпусу даёт
    4 строки в трёх каталогах вариантов отчётов — чистый шум.

    Сигнал сам по себе слабый (эмбеддинг не связывает «продажи» с «Реализация Товаров
    Услуг» и ставит выше «Склады»), поэтому он и НЕ РЕШАЕТ: он только доносит кандидата
    до реранкера, который силён именно на паре «вопрос ↔ название» ([замер 02.08] верная
    сущность первой в 14 % случаев без него и в 36 % с ним).

    Цена замерена и она решает, что можно складывать, а что нет `[замер 03.08]`:
    здесь 52 мс на 1 502 метки, а тот же приём по КОРПУСУ — 4,6 с на 623 565 строк,
    потому что векторного индекса нет ни одного (`ivf` заблокирован,
    `VECTOR_DECISION.md`) и kNN идёт полным сканом. Поэтому по меткам складываем всегда,
    а по корпусу оставляем запасным путём — см. разбор у места вызова.
    """
    if not text:
        return []
    # 🔴 КАРТОЧКА ПРЕДПОЧТИТЕЛЬНЕЕ МЕТКИ — ПО ЗАМЕРУ, А НЕ ПО ВКУСУ.
    # [замер 03.08] `entity_choice_bench.py`, 44 пары, реранкер включён в обоих прогонах,
    # отличается только таблица вектора: до реранкера верная сущность доходит **31 из 44
    # (70 %)** против **23 из 44 (52 %)** у метки, в первой пятёрке 27 против 22. Верх
    # списка почти не сдвинулся (+1) — там распоряжается реранкер; выросла именно ГЛУБИНА
    # отбора, то есть та половина дефекта, где реранкер бессилен: он выбирает только из
    # того, что ему дали. Прибор детерминирован, разброса у него нет.
    # Нет карточки или её векторы посчитаны другой моделью — работаем по метке, как
    # раньше. Ни падения, ни молчаливой подмены: `emb_ready` без отметки говорит «нет».
    src = CARD if emb_ready(CARD) else (TABLES if emb_ready(TABLES) else "")
    if not src:
        return []
    try:
        return [r[0] for r in psql(
            "SELECT src_table FROM %s WHERE emb IS NOT NULL "   # см. `resolve_near`
            "ORDER BY emb <=> %s, src_table LIMIT %d"
            % (src, _vec(text), limit)) if r and r[0]]
    except RuntimeError:
        return []                       # эмбеддер лёг — остаётся буквальный отбор


def rows_of(src_table, match, preds, limit, measure=None):
    """Строки одного источника: САМА строка, а рядом — подсветка совпадения.

    Раньше модели уходила ТОЛЬКО подсветка. Она по устройству отдаёт фрагменты вокруг
    совпавших слов, а не строку: замерено — 144 символа при длине строки 398. Реквизит,
    оказавшийся дальше от совпадения, до модели не доходил вовсе. Живая проверка: ИНН
    контрагента стоит на 367-м символе, вопрос «какой ИНН у Дон-Агро» получал ответ
    «данных нет» при том, что значение есть и в витрине, и в корпусе, и в индексе.
    Подсветка остаётся — она показывает, ГДЕ совпало, — но данные берутся из строки.

    🔴 ПОКАЗАНО = ПОСЧИТАНО. Строки уходят модели, а числа считает `aggregate`; множество у
    них одно. Здесь папки справочника прежде не отбрасывались, а в счёте отбрасываются, и
    множества расходились молча: [замер 04.08] на отборе из 94 строк-групп модели ушло 40
    записей, а счёт по ним дал `count=0, sum=0`. Хуже самого нуля то, что гейт такую
    подмену пропускает по построению: он сверяет названное число со строками, а строки —
    вот они, показаны. Значит модель могла процитировать величину записи, которой в счёте
    нет. Признак тот же, что в счёте (`IsFolder`, поле платформы 1С), и разойтись они
    больше не могут. Число отброшенных групп называет ответ — его считает `aggregate`
    (`folders`), а требует `asked_figure_missing`.
    """
    where = [w for w in ([match] + preds) if w] + ["src_table = %s" % lit(src_table),
             "NOT coalesce(map_extract_value(flags, 'IsFolder'), false)"]
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
            # Разделитель равенства `fg.t` обязателен по той же причине, что у `_fetch`:
            # отобранные термы уходят в подсказку модели («typical for these records») и в
            # варианты уточнения, поэтому ничья на срезе меняла бы ВХОД выбора сущности.
            # [замер 03.08] на семи соперниках вопроса «сколько всего мы продали» ничьи
            # нашлись у двух (1 и 2 в первой шестёрке). Терм уникален в `fg` (`ts_dict_agg`
            # отдаёт словарь), значит порядок полный.
            " SELECT fg.t FROM fg JOIN bg USING (t) CROSS JOIN n"
            " ORDER BY fg.f - bg.b * n.ft::DOUBLE / nullif(n.bt,0) DESC, fg.t LIMIT %(k)d"
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
    if not query or not docs or not RERANK_KEY:
        return []
    # 🔴 ФОРМАТ ЗАПРОСА — НАСТРОЙКА, А НЕ КОНСТАНТА. Прежде тут был зашит вид одного
    # облачного поставщика (`input`/`parameters`/`output.results`), и на любом другом
    # реранкере — включая свой, поднятый рядом с эмбеддером, — вызов молча падал бы в
    # «не получилось», а выдача оставалась бы в прежнем порядке. Заметить это по ответу
    # бота нельзя: сигнала просто нет.
    # Умолчание — общий вид `/v1/rerank` (`model`/`query`/`documents`/`top_n`, ответ
    # `results[].index`), его отдают llama.cpp, TEI и совместимые. Прежний вид доступен
    # как `RERANK_API=dashscope`.
    if RERANK_API == "dashscope":
        body = json.dumps({"model": RERANK_MODEL,
                           "input": {"query": query, "documents": docs},
                           "parameters": {"return_documents": False,
                                          "top_n": len(docs)}}).encode()
    elif RERANK_API == "texts":
        # Схема сервиса объявляет ровно query/documents/instruction/top_n — лишних полей
        # не шлём: молча проглоченное поле сегодня завтра станет ошибкой валидации.
        body = json.dumps({"query": query, "documents": docs, "top_n": len(docs)}).encode()
    else:
        body = json.dumps({"model": RERANK_MODEL, "query": query,
                           "documents": docs, "top_n": len(docs)}).encode()
    req = urllib.request.Request(RERANK_URL, data=body, method="POST")
    if RERANK_KEY:
        req.add_header("Authorization", "Bearer " + RERANK_KEY)
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", EMBED_UA)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            out = json.loads(r.read())
        out = out["output"]["results"] if RERANK_API == "dashscope" else out["results"]
        order = [int(x["index"]) for x in out]
        # 🔴 УСПЕХ ТОЖЕ ПИШЕТСЯ В ЖУРНАЛ. Прежде отмечался только сбой, и «реранкер
        # отработал» было неотличимо от «реранкер не звался вовсе»: обе картины дают в
        # журнале пустоту. [замер 02.08] на этом я и ошибся — счёл прогон идущим без
        # реранкера по строкам 401, снятым до смены настроек. Теперь по журналу видно,
        # участвовал ли он в КАЖДОМ ответе и переставил ли он что-нибудь.
        sys.stderr.write("rerank отработал: %d кандидатов, порядок %s\n"
                         % (len(docs),
                            "изменён" if order[:len(docs)] != list(range(len(docs)))
                            else "без изменений"))
        return order
    except Exception as e:                     # noqa: BLE001 — сеть/квота поставщика
        # 🔴 МОЛЧА ТЕРЯТЬ СИГНАЛ НЕЛЬЗЯ (п. 13). Отказ реранкера не роняет ответ — и это
        # верно (п. 21), — но он ухудшает ровно то, что и так главная открытая проблема:
        # выбор сущности. [замер 02.08] поставщик реранкера отвечал `Arrearage` на все
        # запросы, и по журналу это было не видно ничем: выдача просто оставалась в
        # прежнем порядке. Теперь причина видна в журнале службы.
        sys.stderr.write("rerank НЕ ОТРАБОТАЛ (порядок остаётся прежним): %r\n" % (e,))
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
    # Векторы резолвера посчитаны другой моделью — сравнивать с ними нельзя (`emb_ready`).
    if not emb_ready("resolver_index"):
        return []
    try:
        vec = _vec(term)
    except Exception:                          # noqa: BLE001 — эмбеддер недоступен
        return []
    near = _resolver_psql(
        # 🔴 ТОЛЬКО СТРОКИ С ВЕКТОРОМ. Без этого условия запрос не отдаёт «ничего», когда
        # векторов нет: `<=>` от NULL даёт NULL, такие строки уходят в конец, и когда
        # вектора нет НИ У КОГО, порядок целиком решает разделитель равенства — то есть
        # возвращается первое по алфавиту под видом «ближайшего по смыслу». Это молчаливо
        # неверный ответ (п. 10), а не пустой. Условие делает случай честным: нет
        # векторов — нет и близких, вызывающий остаётся без подсказки и спрашивает.
        "SELECT DISTINCT value FROM resolver_index WHERE emb IS NOT NULL "
        "ORDER BY emb <=> %s, value LIMIT %d"
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


# Сколько лучших совпадений по алиасам поднимать. Не отсечка данных, а размер списка,
# который уйдёт ЧЕЛОВЕКУ: показывать больше нескольких вариантов бессмысленно, а
# отброшенные ничего не теряют — они и так слабее победителя по совпадению фразы.
ALIAS_TOP = int(os.environ.get('ASK_ALIAS_TOP', '8'))
# Индекс по алиасам — чтобы соперников по вопросу ранжировал ДВИЖОК, а не мой счёт
# совпадений: у словаря включена частота, и редкое слово весит больше частого.
ALIAS_INDEX = os.environ.get('ASK_ALIAS_INDEX', 'alias_idx')
# Индекс по карточке сущности и её поля. Строится тактом (`entity_card_build.sql`),
# спрашивается `card_hits`. Поля перечислены здесь, а не собираются из схемы: их состав —
# договор с той сборкой, а не свойство базы, и молчаливое расхождение имён полей должно
# быть видно ошибкой запроса, а не пустой выдачей.
CARD_INDEX = os.environ.get('ASK_CARD_INDEX', 'entity_card_idx')
CARD_FIELDS = ("label", "aliases", "about", "quantities", "attrs")
# Слияние мест (Reciprocal Rank Fusion) при сборе кандидатов. `k` НЕ подбиралось нами:
# 60 — умолчание исходной статьи и Elasticsearch, названное в доках SereneDB
# («Cookbook → Search → Reciprocal Rank Fusion», раздел «k — top-rank weight»).
RRF_K = int(os.environ.get('ASK_RRF_K', '60'))
# Жёсткая проверка выбора сущности по подсказке базы: подтверждает ЛИДЕР ранжирования
# синонимов, а не всякое общее слово.
# 🔴 ВКЛЮЧЕНА 04.08 — и это смена МЕРИЛА, а не пересмотр прежнего замера.
# [замер 30.07] дал «1 улучшение против 3 ухудшений» и правило выключили. Но ухудшением
# там считался верный ответ, ставший уточнением, — по мерилу «сколько верных». Владелец
# 03.08 мерило переопределил: считаются ОШИБКИ, цель ноль, а переспросить разрешено. По
# этому мерилу те три «ухудшения» ошибками не являются вовсе.
# [замер 04.08] на вопросах 1-23 приёмки, живой сервис, отдельный экземпляр, при прочих
# правках дня: неверных 6 → 3, уточнений 14 → 17. Там, где о сущности нет знания
# (`known = 0` — так выглядит база без собранной вики, на первой базе алиасов ноль),
# `_alias_verdict` по-прежнему отвечает «проверять нечем», и поведение не меняется.
ALIAS_VETO = os.environ.get('ASK_ALIAS_VETO', '1') == '1'
# 🔴 ЗАМЕРНЫЙ СЛЕД ЗАЩИТ ШАГА 4 — ТОЛЬКО НАБЛЮДЕНИЕ, НИ ОДНОГО РЕШЕНИЯ (05.08).
# Прогон приёмки платный и идёт 35 минут, а форм у правила «подтверждает ли база выбор»
# несколько, и выбирать между ними надо ЧИСЛАМИ. Поэтому один прогон складывает в след всё,
# из чего каждая форма считается задним числом: чем подтверждён выбор, кто лидер словаря,
# попал ли он вообще в круг кандидатов, чем ответил каждый соперник арбитра. Поведение при
# этом не меняется ни на знак — иначе замер мерил бы не то, что выкатывается.
PROBE = os.environ.get('ASK_PROBE', '0') == '1'
# Служебная сущность не оспаривает выбор: ни соперником арбитра, ни вершиной по смыслу.
# Выключатель нужен, чтобы цену правила можно было снять тем же кодом, а не сборкой
# «до»: `ASK_SKIP_SERVICE_RIVALS=0` возвращает поведение 05.08 целиком.
SKIP_SERVICE_RIVALS = os.environ.get('ASK_SKIP_SERVICE_RIVALS', '1') == '1'
# Искать лидера словаря синонимов по ПОНЯТИЯМ вопроса (значения шага 1 плюс род записей)
# вместо его текста целиком. 🔴 ВЫКЛЮЧЕНО, И ЭТО ЗАМЕР, А НЕ ОСТОРОЖНОСТЬ (05.08).
# Поводом была настоящая беда поиска по тексту: слова «сколько», «у», «нас» участвуют в
# оценке наравне с предметом, и `[замер 05.08]` лидером ТРЁХ разных вопросов стал один и тот
# же регистр «Принятая Возвратная Тара» (оценка 12,49 у всех трёх) — в его словаре есть
# фраза «сколько тары у нас». Но проба по понятиям показала, что дело не в служебных словах:
# по понятию «партнёров» верный `catalog_партнеры` не входит в восьмёрку вовсе (лидер —
# «Иерархия Партнёров»), по «организаций» стоит седьмым в ничьей из четырёх. То есть
# ранжирование словаря синонимов не годится в СУДЬИ ни в той форме, ни в другой — чинить
# надо сам словарь (`wiki_alias.sh`), а не запрос к нему. Переключатель оставлен, чтобы
# следующий заход померил обе формы одной командой, а не переписывал код заново.
ALIAS_BY_CONCEPTS = os.environ.get('ASK_ALIAS_BY_CONCEPTS', '0') == '1'
# Вето отменяет выбор, только если лидер словаря стоит ВЫШЕ выбранной сущности в общем
# порядке кандидатов.
# 🔴 ВЫКЛЮЧЕНО, И ЭТО САМОЕ ВАЖНОЕ ЧИСЛО РАБОТЫ (`[замер 05.08]`, 44 вопроса, боевая база).
# Форма включена: неверных **0 → 8**, верных **6 → 15**. То есть вето держит СЕМНАДЦАТЬ
# ответов сразу — девять верных и восемь неверных, — и по мерилу владельца («годным
# считается только результат, где неверных по-прежнему 0») эта форма негодна. Оставлена
# выключателем, потому что числа за ней стоят и решение о размене «+9 верных за +8 неверных»
# принимает владелец, а не разработка.
# 🔴 И главное, что показал тот же прогон: РАЗЛИЧАЕТ вето эти две группы не по делу.
# У верно отвергнутых лидер словаря стоит в общем порядке кандидатов на 68-69 месте, у
# неверно отвергнутых — на 13-545. Разницы нет: проверка гасит ошибку сигналом, не связанным
# с причиной ошибки. Пять ошибок из восьми — один и тот же промах ВЫБОРА («Отчёт о розничных
# продажах» вместо «Реализации товаров и услуг»), и чинить его надо там, где сущность
# выбирается, а не здесь.
VETO_NEEDS_RANK = os.environ.get('ASK_VETO_NEEDS_RANK', '0') == '1'
# 🔴 ВТОРАЯ ПОПЫТКА ПОДТВЕРЖДЕНИЯ — ТРЕБОВАНИЕ КОНТРАКТА, А НЕ ПОСЛАБЛЕНИЕ (п. 21):
# «если проверка не пропустила ответ — система обязана попробовать сформулировать его заново
# и проверить снова, а не сдаться с первой попытки». Первая попытка спрашивает одну
# поверхность (словарь синонимов), вторая — итог всех: возглавляет ли выбор общий порядок
# кандидатов, и только там, где сомнения не поднималось.
# `[замер 06.08]` 44 вопроса приёмки, боевая база: **неверных 0 → 0, верных 6 → 10,
# уточнений 38 → 34**. Широкая форма (без оговорки «спора не было») давала 11 верных при
# ОДНОЙ ошибке и по п. 21 негодна — разбор в `alias_supported`.
# `ASK_VETO_HEAD_WINS=0` оставляет только первую попытку, как было до 06.08.
VETO_HEAD_WINS = os.environ.get('ASK_VETO_HEAD_WINS', '1') == '1'
# Сколько кандидатов добавляют поверхности, не связанные с буквальным совпадением слов
# (синонимы сущности и близость названия по смыслу). Это БЮДЖЕТ, а не порог
# правильности: добавленные ничего не решают — их судят реранкер и модель, — но и
# заливать список сотней названий нельзя, иначе буквально найденные вытесняются за
# `RERANK_TOP` и реранкер их уже не видит (та же ловушка вытеснения, что в `HOW_NOT_TO
# §3.16`). Размера базы число не касается: оно про длину списка, а не про её состав.
#
# 🔴 ЧИСЛО ВЫВОДИТСЯ ИЗ БЮДЖЕТА ПЕРЕЧНЯ, А НЕ ПОДБИРАЕТСЯ ЗАМЕРОМ (04.08). Прежде здесь
# стояла восьмёрка, и её легко было заменить другой цифрой, «которая лучше меряется на
# нашем наборе», — но это ровно подгонка под конкретную базу (п. 9), а не бюджет.
# Единственная настоящая граница здесь одна: сколько записей вмещает перечень, который
# читает шаг 4. Она уже выражена в `PICK_BUDGET` (знаки) и в оценке длины одной записи,
# по которой считается запасной путь ниже (`PICK_BUDGET // 40`). Поверхностей четыре, и
# каждая получает равную долю: ни одна не имеет права занять перечень целиком.
# Ни размера базы, ни имён, ни слов конкретной конфигурации в этом расчёте нет: изменится
# бюджет промта — изменится и отсечка, сама собой.
#
# Что это даёт по замеру (`work/acceptance/step3_bench.py`, 44 пары приёмки, настоящие
# разборы шага 1): полнота растёт до насыщения — k=4 → 30 (68 %), k=8 → 36 (82 %),
# k=16 → 40 (91 %), k=24 → 41 (93 %), k=32 → 43 (98 %), k=50 → 43 (98 %). Замер здесь
# ПРОВЕРЯЕТ выведенное число, а не выбирает его.
#
# Полнота этого шага — потолок всей системы: чего он не принёс, того шаг 4 не выберет
# никогда, а у вопросов с пустыми `terms` (47 из 58 по настоящим разборам) кандидаты
# состоят только из принесённого здесь.
MEANING_TOP = int(os.environ.get('ASK_MEANING_TOP', '0')) or \
    max(1, PICK_BUDGET // 40 // 4)



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


def measure_aliases_of(src_table):
    # Нет таблицы или права -- пусто, путь прежний (подстрока имени колонки).
    try:
        rows = psql(
            "SELECT measure, aliases FROM search_measure_alias "
            "WHERE src_table = %s AND coalesce(aliases,'') <> ''"
            % lit(src_table))
        return {r[0]: r[1] for r in rows or [] if r and r[0]}
    except RuntimeError:
        return {}


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
    # 🔴 ТО ЖЕ МНОЖЕСТВО, ЧТО И У `aggregate`, И ТЕ ЖЕ ПРАВИЛА СЛОЖЕНИЯ. Оба числа
    # уходят модели рядом и оба разрешены гейту, поэтому разойтись они не имеют права:
    #   · папки исключаются тем же признаком платформы — иначе `{total}` считается без
    #     групп, а `{total:ИМЯ}` с ними, и два числа одного ответа противоречат друг другу;
    #   · сложение идёт в DECIMAL — по той же причине, что в `aggregate` (доки SereneDB,
    #     «Fixed-Point Decimals» против «Floating-Point Aggregate Operations with
    #     Multi-Threading»): иначе итог по имени невоспроизводим.
    nf = "NOT coalesce(map_extract_value(flags, 'IsFolder'), false)"
    cols = ", ".join(
        "coalesce(sum(TRY_CAST(map_extract(nums, %(m)s)[1] AS DECIMAL(38,10))) FILTER (%(nf)s),0), "
        "count(map_extract(nums, %(m)s)[1]) FILTER (%(nf)s), "
        "coalesce(max(TRY_CAST(map_extract(nums, %(m)s)[1] AS DECIMAL(38,10))) FILTER (%(nf)s),0), "
        "coalesce(min(TRY_CAST(map_extract(nums, %(m)s)[1] AS DECIMAL(38,10))) FILTER (%(nf)s),0)"
        % {"m": lit(m), "nf": nf} for m in measures)
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


def _alias_parts(raw):
    """Алиасы поля: список или строка через запятую, как кладёт `wiki_alias.sh`."""
    if isinstance(raw, (list, tuple)):
        return [str(a).strip() for a in raw if str(a).strip()]
    return [a.strip() for a in str(raw or "").split(",") if a.strip()]


def _word_hits_text(wl, text):
    t = (text or "").strip().lower()
    if not t or len(wl) < 2 or len(t) < 2:
        return False
    return wl == t or wl in t or t in wl


def split_ident(name):
    """CamelCase и подчёркивания — в слова через пробел. Без знания конкретной базы."""
    s = (name or "").replace("_", " ")
    s = re.sub(r"([a-zа-яё0-9])([A-ZА-ЯЁ])", r"\1 \2", s)
    return " ".join(s.split())


def measure_choice(names, word, alias_by=None):
    """Чистая часть выбора величины: слово человека против имён величин ИЗ ДАННЫХ.

    Вынесена из `pick_measure` отдельной функцией по двум причинам, и обе — не про красоту:
      1. её можно проверять ОФФЛАЙН (`test_gate.py`), без базы, сети и денег;
      2. то же правило нужно ВТОРОМУ месту — гейту величины (задача 16), где величину
         назвала модель. Пока правило жило внутри `pick_measure`, этот путь его не
         проходил вовсе: имя от модели принималось, если оно просто есть у сущности.

    Возвращает `(величина, альтернативы, как)`. `как='ask'` — подходящих несколько, и
    выбирать между ними молча нельзя (п. 12). `как='rerank'` — правилами не решается,
    решает вызывающий.
    """
    wl = (word or "").strip().lower()
    if not names:
        return (None, [], 'none')
    if not wl:
        return (None, [], 'none')
    if len(names) == 1:
        return (names[0], [], 'single')        # выбора нет — и спрашивать не о чем
    # Имя величины ТОЧНО совпало со словом вопроса — брать его, не гадая реранкером.
    # «сумма» → «Сумма», а не «СуммаНУDr»: точное совпадение сильнее близости.
    exact = [n for n in names if n.lower() == wl]
    if exact:
        return (exact[0], [], 'exact')
    if alias_by:
        covered = [n for n in names
                   if any(_word_hits_text(wl, a) for a in _alias_parts(alias_by.get(n)))]
        if len(covered) == 1:
            return (covered[0], [], 'alias')
        if len(covered) > 1:
            base_of = [n for n in covered
                       if sum(1 for m in covered if m != n and m.startswith(n))
                       >= len(covered) - 1]
            if len(base_of) == 1 and base_of[0].lower() != wl:
                return (base_of[0], [], 'base')
            return (None, covered, 'ask')
    same = sorted(n for n in names if wl in n.lower())
    if len(same) > 1:
        # Базовая величина снимает неоднозначность, если её частные виды — её же префиксы
        # (правило ниже): тогда спрашивать не о чем. Иначе — спрашиваем.
        base_of = [n for n in same
                   if sum(1 for m in same if m != n and m.startswith(n)) >= len(same) - 1]
        if len(base_of) == 1 and base_of[0].lower() != wl:
            return (base_of[0], [], 'base')
        # Раз уж спрашиваем человека — показываются ВСЕ величины сущности, совпавшие
        # со словом — первыми. Подстрока слепа к именованию базы: живой диалог okna
        # 14.08 — на «сумму продаж» совпали только СуммаНДС и СуммаОплатыКарточкой,
        # человек выбрал из двух неверных, а общий итог в этой базе зовётся «Всего»
        # и в варианты не попал вовсе. Список короткий и приходит из данных.
        return (None, same + [n for n in names if n not in same], 'ask')
    if len(same) == 1:
        return (same[0], [], 'substring')
    return (None, [], 'rerank')


def measure_captions(measures, alias_by=None):
    """Человеческая подпись величины. Одинаковые имена различаются разбором поля."""
    alias_by = alias_by or {}
    prim = {}
    for m in measures:
        parts = _alias_parts(alias_by.get(m))
        prim[m] = parts[0] if parts else (split_ident(m) or m)
    seen = {}
    for v in prim.values():
        seen[v.lower()] = seen.get(v.lower(), 0) + 1
    out = {}
    for m in measures:
        cap = prim[m]
        if seen.get(cap.lower(), 0) > 1:
            extra = split_ident(m) or m
            if extra.lower() != cap.lower():
                cap = "%s (%s)" % (cap, extra)
        out[m] = cap
    return out


def resolve_measure(text, measures, alias_by=None, diag=None):
    """Свести выбор человека к имени поля. Неоднозначно или не узнали — None (п. 12)."""
    if not text:
        return None
    t = str(text).strip()
    if not t:
        return None
    if t in (measures or []):
        return t
    alias_by = alias_by or {}
    caps = measure_captions(measures, alias_by)
    norm = lambda s: "".join(str(s or "").lower().split())
    nt = norm(t)
    hit = [m for m, c in caps.items() if norm(c) == nt]
    if len(hit) == 1:
        return hit[0]
    if len(hit) > 1:
        if diag is not None:
            diag["measure_ambiguous_pick"] = t
        return None
    hit = []
    for m in measures:
        if any(norm(a) == nt for a in _alias_parts(alias_by.get(m))):
            hit.append(m)
    if len(hit) == 1:
        return hit[0]
    if len(hit) > 1:
        if diag is not None:
            diag["measure_ambiguous_pick"] = t
        return None
    if diag is not None:
        diag["measure_unknown"] = t
    return None


def slot_measure_uncovered(word, selected, names, alias_by=None):
    """Вопрос назвал величину, выбранное поле её не покрывает, другое из names — покрывает."""
    if not word or not selected or not names:
        return False, []
    got, alts, how = measure_choice(names, word, alias_by=alias_by)
    covering = list(alts) if how == "ask" else ([got] if got else [])
    if covering and selected not in covering:
        return True, covering
    return False, []


def clarify_complete(txt, opts):
    """Код не имеет права выкинуть пункт уточнения: чего нет в тексте модели — дописать."""
    labels = [(o.get("label") or o.get("measure") or "").strip()
              for o in (opts or [])]
    labels = [x for x in labels if x]
    if not labels:
        return txt or ""
    low = (txt or "").lower()
    if all(lab.lower() in low for lab in labels):
        return txt or ""
    extra = ", ".join("«%s»" % lab for lab in labels)
    body = (txt or "").rstrip()
    return extra if not body else body + "\n" + extra


def _slot_fp(f):
    """Отпечаток плейсхолдеров одного кандидата. Покрытие в сравнение не входит."""
    if not isinstance(f, dict):
        return None
    skip = {"in_1c", "in_search", "missing", "_totals"}
    fp = []
    for k in sorted(f):
        if k in skip or str(k).startswith("_"):
            continue
        v = f.get(k)
        if v is None or (isinstance(v, str) and not str(v).strip()):
            continue
        if str(k).startswith("date"):
            fp.append((k, str(v)))
            continue
        try:
            fp.append((k, round(float(v), 2)))
        except (TypeError, ValueError):
            return None
    return tuple(fp)


def answers_diverge(figures):
    """Сошлись ли ПОСЧИТАННЫЕ ответы кандидатов на одном числе (задача 17).

    Сравнивается отпечаток плейсхолдеров compose, не заранее названное поле. Порога нет.
    Совпали — выбирать не из чего. Сравнить нечем — расхождение, не согласие.
    """
    if len(figures) < 2:
        return False
    fps = []
    for f in figures:
        fp = _slot_fp(f)
        if not fp:
            return True
        fps.append(fp)
    return len(set(fps)) > 1


def answers_src_conflict(cands):
    """Разные src при совпавшем отпечатке — не согласие (A3).

    Список из двух и больше `{src, kind, figures}`. Отпечаток — тот же
    `answers_diverge` по `figures` (слоты compose, не голое count).
    True = спрашивать. Один src, меньше двух `answer`, или отпечатки
    разошлись — False (расхождение чисел — ветка `answers_diverge`).
    Соперника в круг не заводит: смотрит тех, кто уже дал `kind=answer`.
    """
    ans = [c for c in (cands or [])
           if (c.get("kind") == "answer") and c.get("src")]
    if len(ans) < 2:
        return False
    if answers_diverge([c.get("figures") or {} for c in ans]):
        return False
    return len({c["src"] for c in ans}) > 1


def answer_money(want, compute, measure):
    """Нужны ли в этом ответе денежные числа.

    Поле, которое модель назвала, само по себе денег не открывает: на «сколько»
    (`want`/`compute` = count) их нет, даже если словарь свёл «всего» к колонке.
    `want=list` сюда не входит: пустой want в разборе становится list, и иначе
    деньги выключатся на вопросах про сумму, где разбор не сказал sum.
    """
    counting = (compute or "") == "count" or (want or "") == "count"
    return bool(measure) and not counting


def compose_slot_values(agg, measure=None, folders=0, money=None):
    """Числа, которые compose подставит в плейсхолдеры этого ответа.

    Не `amount=` примеров строк и не покрытие (`in_1c` / `missing`): они не итог.
    Вызов из answer передаёт `money=` явно (тот же флаг, что compose и гейт).
    `money=None` — как `bool(measure)`, только для проб без оси вопроса.
    """
    if money is None:
        money = bool(measure)
    slots = {}
    if not agg:
        return slots
    if agg.get("count") is not None:
        slots["count"] = agg["count"]
    if money:
        ca = agg.get("count_amount")
        if ca is not None and ca != agg.get("count"):
            slots["count_amount"] = ca
        for k in ("sum", "max", "min", "avg"):
            if agg.get(k) is not None:
                slots[k] = agg[k]
    dmin = agg.get("date_min")
    if dmin:
        slots["date_min"] = dmin
        if agg.get("date_max"):
            slots["date_max"] = agg["date_max"]
    nfold = folders if folders else (agg.get("folders") or 0)
    if nfold:
        slots["folders"] = nfold
    if agg.get("undated"):
        slots["undated"] = agg["undated"]
    if agg.get("outside_period"):
        slots["outside_period"] = agg["outside_period"]
    return slots


def arbiter_figures(sub):
    """Отпечаток кандидата = его `figures`, уже собранные как плейсхолдеры compose."""
    f = dict((sub or {}).get("figures") or {})
    for k in ("in_1c", "in_search", "missing"):
        f.pop(k, None)
    f.pop("_totals", None)
    return f


def alias_supported(known, hit, cand_family, leader_family, veto=None,
                    rank_cand=None, rank_leader=None, undisputed=False):
    """Подтверждает ли словарь синонимов выбор сущности. Форма правила — здесь и только здесь.

    Правило одно, а форм у него несколько, и выбирать между ними можно только замером —
    поэтому оно вынуто из `_alias_verdict` отдельной функцией: у неё есть оффлайн-проба
    (`test_step4_guards.py`), и её таблица истинности читается без базы.

      · знания об этой сущности нет (`known = 0`) — проверять нечем, выбор проходит. Так
        выглядит база, где вики не собрана (на первой базе алиасов ноль);
      · жёсткая форма (`ALIAS_VETO`, она же боевая): подтверждает ЛИДЕР ранжирования по
        вопросу — совпала его семья с семьёй выбора, значит прочтение одно;
      · мягкая форма: довольно того, что слово вопроса совпало с СОБСТВЕННЫМ синонимом
        выбранной сущности.

    🔴 ЭТО ПРАВИЛО ДЕРЖИТ СЕМНАДЦАТЬ ОТВЕТОВ (`[замер 05.08]`, 44 вопроса приёмки, боевая
    база; разбор — `work/entity-choice/ANSWER_RATE_P21.md`). В форме «лидер выше выбора по
    общему порядку кандидатов» числа такие: неверных 0 → 8, верных 6 → 15. То есть девять
    верных ответов и восемь неверных держатся одной и той же проверкой. Мягкая форма
    («довольно своего совпадения») отвергнута отдельно: 7 вернувшихся ответов, из них 6
    неверных. Прежний замер 30.07 («1 улучшение против 3 ухудшений») этому не противоречит:
    он снят на ПЕРВОЙ базе и на прежнем словаре синонимов.

    🔴 И различает правило эти две группы НЕ ПО ДЕЛУ: у верно отвергнутых лидер словаря стоит
    в общем порядке кандидатов на 68-69 месте, у неверно отвергнутых — на 13-545. Значит
    «ноль ошибок» держится не точностью проверки, а её слепотой; пять ошибок из восьми — один
    и тот же промах ВЫБОРА («Отчёт о розничных продажах» вместо «Реализации товаров и
    услуг»), и лечится он не здесь.
    """
    if not known:
        return True
    if veto is None:
        veto = ALIAS_VETO
    if not veto:
        return bool(hit)
    if not leader_family:
        return bool(hit)
    if VETO_HEAD_WINS and undisputed and rank_cand == 0:
        # 🔴 ВТОРАЯ ПОПЫТКА, ПРЕДПИСАННАЯ КОНТРАКТОМ (п. 21): «если проверка не пропустила
        # ответ — система обязана попробовать сформулировать его заново и проверить снова,
        # а не сдаться с первой попытки». Первая попытка спрашивает ОДНУ поверхность —
        # словарь синонимов. Вторая спрашивает итог ВСЕХ: голову общего порядка кандидатов,
        # который шаг 3 сложил из буквального отбора, смысла, карточки и словаря и уточнил
        # реранкером. Совпал выбор с этой головой — подтверждение есть, и оно независимо от
        # словаря. Порога тут нет: «первый» — это место в порядке, а не подобранное число.
        #
        # 🔴 И ТОЛЬКО ТАМ, ГДЕ СОМНЕНИЯ НЕ БЫЛО ВОВСЕ (`undisputed`). Это не осторожность,
        # а замер: `[замер 06.08]` вторая попытка без этой оговорки вернула 6 ответов, из
        # них 5 верных и 1 неверный — «Сколько мы продали в декабре 2017 года?» ушло по
        # «Отчёту о розничных продажах» вместо «Реализации». Оба спорных случая (и ошибка,
        # и один верный) отличались от прочих одним: там ПОДНИМАЛОСЬ сомнение и работал
        # арбитр. Где спор есть, решает п. 12 — спрашиваем человека; вторая попытка нужна
        # там, где проверка отвергла ответ, которого никто не оспаривал.
        return True
    if VETO_NEEDS_RANK and rank_leader is not None:
        rank_cand = -1 if rank_cand is None else rank_cand
        # 🔴 СЛОВАРЬ ОДИН ПРОТИВ ВСЕХ ОСТАЛЬНЫХ СИГНАЛОВ — ЭТО НЕ ПОВОД ОТМЕНИТЬ ВЫБОР.
        # Лидер словаря отменяет выбор, только если общий порядок кандидатов (буквальный
        # отбор, смысл, карточка, реранкер — всё, что сложено шагом 3) ставит его ВЫШЕ
        # выбранной сущности. Ниже или вовсе вне круга — значит за него говорит одна
        # поверхность из четырёх, и она же `[замер 05.08]` ошибается системно: фраза
        # «сколько тары у нас» в словаре делает регистр тары лидером ЛЮБОГО вопроса,
        # начинающегося со «сколько у нас». Порога тут нет: сравниваются два места в одном
        # и том же порядке, а не оценка с константой.
        if rank_leader < 0:
            return True
        if 0 <= rank_cand < rank_leader:
            return True
    return cand_family == leader_family


def not_for_excludes(kind_stems, items):
    """Отсекает ли кандидата собственное «на что НЕ отвечает» из словаря установки.

    Форма правила — здесь и только здесь, чтобы её таблица истинности читалась без базы
    (`test_step4_guards.py`), а входы от базы собирал один заход в `answer`.

    Входы: `kind_stems` — основы РОДА записей из шага 1 (модель описывает вопрос — это
    её единственная роль; решает код), `items` — записи `not_enough_for` кандидата в
    виде `(основы левой части, есть_указатель)`. Всё по основам словаря движка:
    подстрока тут лжёт в обе стороны — `contains('склады','складов')` ложна.

    Отсев — ровно один случай из двух условий сразу:
      · весь предмет вопроса накрыт ОДНОЙ записью (`kind_stems <= основы записи`).
        Вопрос «продажа» целиком входит в «оптовые продажи — не в этом списке», а
        многословный род («документы реализации товаров и услуг») случайным словом
        вроде «услуг» не накрывается — требование ВСЕГО подмножества и есть защита
        от случайных совпадений;
      · запись НЕ отсылает к соседней сущности (`не есть_указатель`). У записи две
        формы: «аспект — Другая Сущность» (узкое: аспект живёт по соседству, а
        родовой вопрос сущность отвечает) и «тема — не в этом списке» (широкое:
        темы в записях нет вовсе). Отсекает только вторая.

    Почему отсев, а не подсказка модели: в перечень знание не вставляется (проверено
    и отвергнуто замером 30.07 — стало хуже), а решает код по данным — объём в модель
    не растёт (п. 19). Ошибка в данных стоит лишнего уточнения, а не неверного
    ответа: отсеянного кандидата модель просто не видит, все проверки выбора ниже
    работают как прежде.

    Форма выбрана замером среди восьми (`work/entity-choice/not_for_probe.py`, 44
    вопроса приёмки, боевая база): пересечение с сырым текстом вопроса отсекает 15-26
    эталонов из 44 (служебные слова и случайные совпадения), пересечение с родом без
    требования всего подмножества — 12, подмножество без учёта указателя — 7, среди
    них ВЕРНЫЙ ответ про новости. Эта форма — 0 эталонов при 6 из 9 целевых подмен.
    """
    return bool(kind_stems) and any(
        kind_stems <= st and not ptr for st, ptr in items if st)


def pair_unanswered(writer, answered):
    """Соперник из связи «кто пишет этот источник» НЕ дал ответа в круге арбитра.

    `answered` — фокусы кандидатов, чьи ответы собрались. Соперника там может не быть
    по двум причинам: его ответ завернулся в его собственное уточнение (`mute`) или
    под-вызов упал (исключение — он тогда не попадает ни в ответы, ни в `mute`).
    Обе причины означают одно: его число с нашим НЕ сравнивалось, и молчание — это
    не согласие. Форма вынесена отдельной функцией, чтобы её таблица истинности
    читалась без базы (`test_step4_guards.py`).
    """
    return bool(writer) and writer not in answered


def single_is_rival(picked_first, sole):
    """Собравшийся одиночный ответ круга — от соперника, а не от выбора модели.

    Круг собирается ради сомнения; если выбор модели молчит (уточнение о величине,
    пусто, падение), а отвечает соперник, то отдать его число как ответ — скрытый
    выбор наугад между двумя прочтениями (п. 12). Живой случай — приёмка №42
    `[замер 06.08]`: выбран верный документ, он молчит, ответил регистр с чужим числом.
    """
    return bool(picked_first) and bool(sole) and sole != picked_first


def veto_top_without(top, excluded):
    """Лидер словаря синонимов ищется среди НЕ отсеянных «не отвечает».

    Сущность, отсеянная как непригодная отвечать на этот род вопроса, непригодна и
    эталоном сравнения для вето: `[замер 06.08]` лидер «Заказы Поставщикам» был отсеян
    по делу, а его место в круге стало -1 — и правило «лидер вне круга → выбор
    проходит» молча пропустило неверный ответ.
    """
    return [(t, s) for t, s in top if t not in excluded]


def figures_numbers(out):
    """ВСЕ числа, которые кандидат ПОСЧИТАЛ, — даже если ответом они не стали.

    Кандидат круга арбитра возвращается не только ответом: он может завернуть посчитанное
    в уточнение о собственной величине (`measure_totals` — итог по каждой подходящей) или
    во встречный вопрос (`asked_back` — числа при этом в `figures`). Числа от этого не
    перестают быть посчитанными базой, и сравнивать их можно так же, как обычный ответ.
    """
    out = out or {}
    f = out.get("figures") or {}
    nums = []
    if f.get("sum") is not None:
        nums.append(f["sum"])
    elif f.get("count") is not None:
        nums.append(f["count"])
    nums += [v for v in ((out.get("diag") or {}).get("measure_totals") or {}).values()
             if v is not None]
    return nums


def same_number(ours, theirs):
    """Сошлись ли прочтения на ОДНОМ числе. Равенство или ничего — ни порога, ни допуска.

    Правило зеркально `answers_diverge`: там расхождение доказывают разные числа, здесь
    совпадение доказывает равное. Сравнить нечем (у нас числа нет, у соперника ни одного) —
    доказательства НЕТ, и вызывающая сторона спрашивает человека, как и прежде.
    """
    if ours is None:
        return False
    try:
        return any(float(x) == float(ours) for x in theirs if x is not None)
    except (TypeError, ValueError):
        return False


def unresolved_quantity(measure, alts, want, compute, names, totals_by=None):
    """Свести поле, когда вопрос про итог/max/min/avg, а величина ещё не выбрана.

    `want=count|list` сюда не входит: там в compose нет денег, уточнение полей
    было бы «НДС или карта» на «сколько продаж». Одна величина — брать её;
    несколько с разными итогами — спрашивать тем же перечнем, что уже есть;
    итоги совпали — брать первую, вопрос был бы шумом.
    """
    if measure or alts:
        return measure, list(alts or [])
    need = (want or "") == "sum" or (compute or "") in ("sum", "max", "min", "avg")
    if not need:
        return None, []
    names = list(names or [])
    if not names:
        return None, []
    if len(names) == 1:
        return names[0], []
    if measure_ambiguous(names, totals_by or {}):
        return None, names
    return names[0], []


def mute_measure_blocks(sole, mute, cand_src):
    """Одиночный ответ круга не отпускать, если соперник ушёл в уточнение полей
    с другими итогами. Иначе A2 делает документ немым, а книгу с одним полем —
    ответом. Совпадение чисел — как у writer_pair: вопрос был бы шумом.
    """
    свой = next((s for s in (cand_src or [])
                 if (s.get("diag") or {}).get("focus") == sole), None)
    наше = (figures_numbers(свой) or [None])[0]
    for src, sub in (mute or {}).items():
        if src == sole:
            continue
        if not (sub.get("diag") or {}).get("measure_ambiguous"):
            continue
        if not same_number(наше, figures_numbers(sub)):
            return src
    return None


def measure_ambiguous(fits, totals):
    """Меняет ли выбор величины ОТВЕТ. Иначе неоднозначности нет, а вопрос был бы шумом.

    Подходящих больше одной — само по себе ещё не сомнение: у документа `СуммаДокумента` и
    `СуммаСНДС` его табличной части дают одно и то же число, и спрашивать «какую из них»
    значит требовать от человека выбора, который ни на что не влияет. Сомнение есть, когда
    итоги РАЗНЫЕ. Ни порога, ни допуска: сравниваются сами числа, посчитанные базой.
    """
    if len(fits) < 2:
        return False
    seen = set()
    for m in fits:
        try:
            seen.add(float(totals.get(m, 0.0)))
        except (TypeError, ValueError):
            seen.add(0.0)
    return len(seen) > 1


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
    # Правило целиком живёт в `measure_choice` — ЧИСТОЙ функции, которую проверяет
    # оффлайн-проба. Здесь остаётся только то, чего в ней быть не может: обращение к
    # данным за именами величин и запасной путь через реранкер (сеть).
    # Что делает правило и почему именно так:
    #   * вопрос не называет величину — НЕ выбираем за него, иначе «что покупало Ромашка»
    #     превращается в `НомерЧекаККМ`; итоги по всем величинам уйдут модели (`totals_of`);
    #   * 🔴 несколько величин одинаково подходят — это ВОПРОС ЧЕЛОВЕКУ, а не задача
    #     реранкеру. Указание владельца 30.07: «давать юзеру неверный ответ — самое страшное,
    #     что мы можем сделать. лучше 1, 2, 3 раза уточнить, если непонятно, чем дать не то».
    #     [замер 30.07] у `document_приобретениетоваровуслуг` слово «сумма» несут ЧЕТЫРЕ
    #     величины: СуммаДокумента, СуммаВзаиморасчетов, СуммаВзаиморасчетовПоЗаказу,
    #     СуммаВзаиморасчетовПоТаре. Реранкер выбирал молча и ошибался: на верно выбранной
    #     сущности ответ дал 71 045 277,59 вместо 73 181 157,68 — сущность та, величина нет.
    names = measures_of(src_table)
    wl = (word or "").strip().lower()
    got, alts, how = measure_choice(names, word,
                                    alias_by=measure_aliases_of(src_table))
    if how != 'rerank':
        return (got, alts, how)
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


def pick_entity(question, kind, cands, counts=None, match="", diag=None):
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
    # Одноимённым кандидатам дописывается вид записи: иначе в перечне стоят две
    # неотличимые строки, и выбор модели между ними — догадка, а не выбор (п. 12).
    # Ответ модели приходит НОМЕРОМ строки, поэтому подпись сопоставление не задевает.
    _dis = disambiguate_labels([(c, label_by[c]) for c in cands if c in label_by])
    names = [(c, _dis.get(c, label_by[c])) for c in cands if c in label_by]
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
            if diag is not None:
                sb = diag.setdefault("selection_budget", {})
                sb["entities_shown"] = len(lines_out)
                sb["entities_total"] = len(names)
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


def _numN(x):
    """Число или ОТСУТСТВИЕ числа — в отличие от `_num`, который отсутствие обращает в ноль.

    Нужен там, где разница между «посчитано и вышло 0» и «считать было нечего» — это
    разница между ответом и неверным ответом (п. 21). Пустое поле CSV означает NULL из
    базы, то есть агрегат по пустому множеству; `_num` вернул бы 0.0, и ноль стал бы
    неотличим от посчитанного.
    """
    if x is None or (isinstance(x, str) and not x.strip()):
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


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
    # 🔴 ПАПКА — НЕ ЗАПИСЬ. В справочнике 1С группа служит для раскладки по полкам, а не
    # описывает вещь: спрашивая «сколько позиций номенклатуры», человек считает товары, а не
    # папки. [замер 30.07] у `catalog_номенклатура` 252 строки, из них 25 групп → 227, ровно
    # столько, сколько объявляет приёмка. Прежде система отвечала 252 и была неверна.
    #
    # Признак — `IsFolder`, поле САМОЙ ПЛАТФОРМЫ 1С, того же класса, что `Ref_Key` и
    # `DataVersion`: одинаково на любой конфигурации и языке, это не слово о нашей базе.
    #
    # Безопасность правки проверена, а не предположена: [замер] группы есть всего у 26 из 697
    # сущностей; у партнёров и контрагентов их НОЛЬ, поэтому проверенные ответы 164 и 155 не
    # сдвигаются. Отдельным числом возвращается, сколько групп отброшено, — молчать об этом
    # нельзя (п. 13), и ответ обязан их назвать.
    # Обращение к РЕКВИЗИТУ по имени, а не поиск подстроки в тексте документа.
    # `flags` — типизированная карта булевых реквизитов, собирается движком при сборке
    # корпуса из колонок с kind='flag' (`corpus_build.sql`, is_flag). Отбор трёхзначный:
    # `coalesce(..., false)` означает «реквизита нет» = «не папка», и это верно как для
    # пустой карты, так и для NULL у сущностей, собранных упрощённым путём.
    # `IsFolder` — поле платформы 1С того же класса, что `Ref_Key`: не хардкод, а контракт
    # платформы. Механизм извлечения общий для ЛЮБОГО булева реквизита любой базы.
    folder_pred = "NOT coalesce(map_extract_value(flags, 'IsFolder'), false)"
    # 🔴 СЛОЖЕНИЕ DOUBLE НЕ ВОСПРОИЗВОДИМО, И ЭТО СВОЙСТВО ДВИЖКА, А НЕ НАШ НЕДОСМОТР.
    # Доки SereneDB, «Non-Deterministic Behavior → Floating-Point Aggregate Operations with
    # Multi-Threading»: «when the aggregation is split across multiple threads, the order in
    # which floating-point values are summed is not deterministic, so the low-order digits
    # vary»; там же у `sum(arg)` — «the floating-point versions of this function are affected
    # by ordering». То есть один и тот же вопрос к НЕИЗМЕННЫМ данным даёт разные числа, а
    # п. 3 контракта требует ровно обратного — «детерминированно на данных».
    #
    # [замер 04.08] `aggregate` вызван пять раз подряд без единой правки: у трёх пар из шести
    # сумма отличалась, и у одной РАЗНИЦА ДОХОДИЛА ДО ЧЕЛОВЕКА — четыре разных числа из пяти
    # прогонов (…771 648 / …774 720 / …778 816 / …796 224). Это не «последние разряды»: у
    # величин крупнее 2^53 разряд double грубее единицы, и расходятся видимые цифры ответа.
    #
    # Лечится штатной фиксированной запятой движка (доки, «Numeric → Fixed-Point Decimals»):
    # DECIMAL — «exact fixed-point decimal value», сложение точное и от порядка не зависит.
    # Выбор ширины и точности сделан ЗАМЕРОМ, а не на глаз [замер 04.08, 60 пар]:
    #   · DECIMAL(38,10) и DECIMAL(38,15) совпали на всех 60 парах — десяти знаков хватает,
    #     дальше уточнять нечего;
    #   · с DOUBLE разошлись ровно те 3 пары, где он и не воспроизводится, — то есть меняем
    #     мы только неверное;
    #   · цена: 39 мс против 12 мс у DOUBLE и 109 мс у штатного же `sum(x ORDER BY x)`,
    #     который тоже чинит порядок, но втрое дороже.
    # Запас разрядности: 28 цифр до запятой (1e28). Наибольшее значение базы 6,4e13, всех
    # значений 1,9 млн — до предела двенадцать порядков.
    #
    # `TRY_CAST`, а не `CAST`: значение, не влезшее в разрядность, обязано стать NULL, а не
    # уронить ответ целиком. Но молчать о нём нельзя (п. 13) — оно считается отдельно и
    # возвращается числом (`out_of_range`).
    d = ("TRY_CAST(%s AS DECIMAL(38,10))" % m) if measure else "NULL::DECIMAL(38,10)"
    # 🔴 `coalesce(…, 0)` УБРАН НАМЕРЕННО. Пустой агрегат — это «считать было нечего», и
    # ноль на его месте неотличим от посчитанного ответа. Требование записано прямо в
    # описании этой функции («пустой результат честнее нуля»), но в коде его не было:
    # множество, где величины нет ни у одной строки, давало `sum=min=max=avg=0`, и ответ
    # «0 ₽» проходил гейт — ноль ведь честно лежит в `agg`. Тот же класс, что и
    # тождественно нулевая величина (03.08), только через другую дверь: страж того правила
    # смотрит в `totals_of`, а тот при нуле строк со значением молчит.
    # Среднее считается ЗДЕСЬ ЖЕ из суммы и числа строк со значением, а не отдельным `avg`:
    # так оно по построению не может оказаться посчитанным по другому множеству.
    r = psql("SELECT count(*) FILTER (%(nf)s), sum(%(d)s) FILTER (%(nf)s), "
             "       min(%(d)s) FILTER (%(nf)s), "
             "       max(%(d)s) FILTER (%(nf)s), "
             "       CASE WHEN count(%(d)s) FILTER (%(nf)s) > 0 "
             "            THEN sum(%(d)s) FILTER (%(nf)s) "
             "                 / count(%(d)s) FILTER (%(nf)s) END, "
             "       coalesce(min(doc_date)::date::text,''), "
             "       coalesce(max(doc_date)::date::text,''), "
             "       count(%(d)s) FILTER (%(nf)s), "
             "       count(*) FILTER (NOT (%(nf)s)), "
             "       count(*) FILTER (%(nf)s AND %(m)s IS NOT NULL AND %(d)s IS NULL) "
             "FROM %(src)s WHERE %(w)s"
             % {"m": m, "d": d, "src": src, "w": " AND ".join(where), "nf": folder_pred})
    if not r or not r[0] or r[0][0] == "":
        return None
    row = r[0] + [""] * (10 - len(r[0]))
    # count_amount отдельно от count: avg/sum посчитаны по строкам с суммой, и модель
    # обязана знать, по скольким. Иначе среднее по 31 строке уходит как среднее по 1344.
    n_amount = int(row[7] or 0)
    return {"count": int(row[0]), "sum": _numN(row[1]), "min": _numN(row[2]),
            "max": _numN(row[3]),
            "avg": None if _numN(row[4]) is None else round(_numN(row[4]), 2),
            "date_min": row[5], "date_max": row[6],
            "count_amount": n_amount, "src": src_table,
            "measure": measure,
            # Значения, не влезшие в разрядность DECIMAL: в сумму они не вошли. Ноль у
            # любых мыслимых данных; не ноль — молчать нельзя (п. 13).
            "out_of_range": int(row[9] or 0),
            # 🔴 ШАГ ОБЪЯВЛЯЕТ, ПО КАКОМУ МНОЖЕСТВУ ПОСЧИТАЛ. Без этого число проверить
            # нечем: гейт сверяет ответ с ЭТИМ ЖЕ agg, то есть своё же число и подтвердит,
            # а живой замер вынужден верить на слово. Здесь лежит ровно то, что ушло в базу:
            # источник и полное условие вместе с отбрасыванием групп. По нему любой
            # посторонний прибор пересчитывает итог независимо и сравнивает (п. 3 —
            # «детерминированно на данных», п. 13 — потеря обязана быть видна).
            # Модели это не уходит: `diag` до неё не доходит вовсе (`mcp_ask.py` его не
            # читает), а внутренние имена таблиц туда и не должны попадать.
            "scope": {"src": src, "where": " AND ".join(where), "folder_pred": folder_pred},
            # Сколько групп отброшено из счёта. Ноль у подавляющего большинства сущностей;
            # где не ноль — ответ обязан это назвать, иначе получится молчаливая подмена
            # множества (п. 13).
            "folders": int(row[8] or 0)}


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

  {total}  {count}  {count_amount}  {max}  {min}  {avg}  {date_min}  {date_max}

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


# Место, оставленное моделью под посчитанное базой число. Разбирается ТЕРПИМО — регистр
# и пробелы внутри скобок значения не имеют, имя величины сверяется без учёта регистра.
# 🔴 Строгий разбор был не строгостью, а дырой: `{Total}` и `{ total }` не совпадали с
# `[a-z_]+` вовсе, поэтому место не попадало ни в подстановку, ни в список нераспознанных —
# и уезжало клиенту БУКВАЛЬНО, «Закуплено на {Total} руб.», без числа и без ошибки. Гейт
# такую строку пропускает: цифр в ней нет. Терпимый разбор + `LEFTOVER` ниже закрывают
# оба исхода: что распозналось — заполняется, что осталось — отказ формулировки.
# Цифра в имени роли допустима: `{in_1c}` — число переписи «сколько строк в 1С». Без неё
# место не совпадало с образцом вовсе и уезжало клиенту буквально — ровно тот же дефект,
# что и `{Total}`, только найденный уже своей же пробой.
SLOT = re.compile(r"\{\s*([A-Za-z_][A-Za-z_0-9]*)\s*(?::\s*([^}]*?)\s*)?\}")
# Незаполненное место в готовом тексте. Форма — «слово» или «слово:имя» в скобках; GUID
# 1С (`{a1b2c3d4-0000-…}`) под неё не подходит из-за дефисов, то есть цитата из данных
# отказом не становится.
LEFTOVER = re.compile(r"\{\s*[^\W\d_][\w ]*(?:\s*:[^}]*)?\}", re.UNICODE)


def _fill_figures(text, agg, totals, has_measure=True, extra=None):
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
    # Числа неполноты (`{missing}`, `{in_1c}`, `{in_search}`) — такие же места, как итоги:
    # они посчитаны переписью, и списывать их модели тоже неоткуда. Кладутся ПОСЛЕ снятия
    # величин, иначе отсутствие выбранной величины уносило бы и предупреждение о потере.
    for k, v in (extra or {}).items():
        if v is not None:
            known[k] = v
    by_name = {}
    for m, v, mx, mn in (totals or []):
        by_name[m] = {"total": v, "max": mx, "min": mn}
    bad = []

    def one(mt):
        # Роль — наше служебное слово, регистр в ней не значит ничего. Имя величины
        # приходит из данных: сперва ищем как есть, потом без учёта регистра — модель
        # переписывает имя от руки, и «количество» вместо «Количество» роняло верный
        # ответ на ровном месте.
        role, name = mt.group(1).lower(), mt.group(2)
        if name:
            name = name.strip()
            got = by_name.get(name, {}).get(role)
            if got is None:
                for k, v in by_name.items():
                    if k.lower() == name.lower():
                        got = v.get(role)
                        break
        else:
            got = known.get({"total": "sum"}.get(role, role))
        # 🔴 ПУСТОЕ ЗНАЧЕНИЕ — ТАКОЙ ЖЕ ОТКАЗ, КАК ОТСУТСТВУЮЩЕЕ. У сущности может не быть
        # ни одной даты, и `aggregate` отдаёт тогда пустую строку, а не None. Подстановка
        # её на место `{date_min}` давала человеку дыру в тексте — «данные за  ..» — то
        # есть молчаливую потерю (п. 13) вместо честного «не считали».
        if got is None or (isinstance(got, str) and not got.strip()):
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


def formulation_flaws(text, slots_bad=()):
    """Причины, по которым формулировка не доходит до человека (шаг 6, структурно).

    Это не проверка чисел — числами занят гейт (шаг 7). Здесь смотрим, что до человека
    доехал ТЕКСТ, а не заготовка: место без числа, пустая строка. Оба случая гейт
    пропускает по построению — цифр в них нет, значит и необоснованных цифр нет.

    🔴 Пустая формулировка. `_split_answer` отдаёт пустую строку намеренно («пустота
    лучше служебного мусора, а отказ лучше пустоты»), но вторую половину этого правила
    исполняла только вторая попытка: у неё стоит `and (text2 or "").strip()`, а у первой
    такой проверки не было. Оборванный по `max_tokens` ответ или обёртка без поля `text`
    доезжали до клиента ПУСТЫМ сообщением с видом `kind=answer` — при том что числа
    посчитаны и их было чем отдать структурой.

    🔴 Незаполненное место. `{Total}`, `{ total }`, `{Итого}` не совпадали с прежним
    строгим образцом и потому не попадали ни в подстановку, ни в список нераспознанных.
    Теперь разбор терпимый, а всё, что осталось в скобках, — отказ формулировки: вторая
    попытка, а если и она не сойдётся, числа уходят структурой (п. 21). Заготовка
    человеку при этом не показывается.
    """
    bad = ["нераспознанное место: %s" % x for x in list(slots_bad)[:3]]
    if not (text or "").strip():
        bad.append("пустая формулировка")
        return bad
    left = LEFTOVER.search(text)
    if left:
        bad.append("незаполненное место: %s" % left.group(0)[:40])
    return bad


def copied_figures(text, agg, rows):
    """Посчитанные числа, которые модель набрала цифрами вместо места под подстановку.

    🔴 Здесь правило «числа ставит код, а не модель» перестаёт быть строкой промта и
    становится кодом. В `ANSWER_SYS` оно записано словами, и `[замер 04.08,
    step6_live.py]` показал цену этих слов: на восьми вопросах модель семь раз оставила
    место — и один раз набрала 249 цифрами. Промт срабатывает почти на всех вопросах, а
    это «почти» и есть весь вопрос: пока число набирает модель, неверное число возможно, и
    защищает от него только гейт — а гейт смотрит лишь, ЕСТЬ ли такое число в данных, но
    не в своей ли оно роли. Ровно этот класс (`F285`: «три реализации на 1 236 800 поданы
    с итогом 925 000 — настоящее число, но из другой роли») калькулятор и закрывал: пока
    число ставит код, роль не перепутать. Рукопись возвращает класс обратно.

    Цитата из строки рукописью не считается: промт разрешает копировать номер документа,
    дату и имя из конкретной записи, а `min`/`max` по построению совпадают со значением
    какой-то строки. Поэтому число сверяется со ВСЕМИ показанными строками и попадает в
    находки, только если взять его было неоткуда, кроме нашего блока с итогами.

    Найденное уходит причиной второй попытки — той же, что и остальные изъяны, — а если и
    она наберёт число цифрами, числа отдаются структурой (п. 21). Ответ при этом не
    теряется: он и так весь состоит из посчитанных базой чисел.
    """
    if not agg or not (text or "").strip():
        return []
    in_rows = set()
    for r in (rows or []):
        in_rows |= _norm_numbers(r[5]) | _norm_numbers(r[3])
        try:
            v = float(r[2])
            in_rows.add(round(v, 2))
            if v == int(v):
                in_rows.add(float(int(v)))
        except (TypeError, ValueError):
            pass
    # Имя места для второй попытки: у суммы оно отличается от имени роли в `agg`.
    slot_of = {"sum": "total", "avg": "avg", "min": "min", "max": "max", "count": "count"}
    computed = {}
    for k in ("sum", "avg", "min", "max", "count"):
        v = agg.get(k)
        if v is None:
            continue
        try:
            fv = round(float(v), 2)
        except (TypeError, ValueError):
            continue
        if fv in in_rows:
            continue                    # взято из строки — это цитата, а не рукопись
        computed.setdefault(fv, k)
        if float(v) == int(float(v)):
            computed.setdefault(float(int(float(v))), k)
    if not computed:
        return []
    out, seen = [], set()
    for readings in _tokens(text):
        hit = readings & set(computed)
        if not hit:
            continue
        v = sorted(hit)[0]
        if v in seen:
            continue
        seen.add(v)
        out.append("число %s набрано цифрами вместо места {%s}"
                   % (_fmt(v), slot_of[computed[v]]))
    return out


def _filled_ask(ask, agg, totals, money, diag=None, extra=None):
    """Уточняющий вопрос с подставленными числами — или пусто, если он вышел с изъяном.

    Разница с текстом ответа в том, чем платим за изъян. У ответа изъян ведёт ко второй
    попытке и дальше к числам структурой: там есть что отдать вместо. У вопроса отдавать
    нечего, и выбор простой — показать заготовку («за какой период, с {date_min}?») или
    не задавать вопроса вовсе. Второе честнее: ответ при этом остаётся целым и уходит
    человеку, а сорвавшийся вопрос виден в `diag`, а не в мессенджере.
    """
    ask, slots_bad = _fill_figures(ask, agg, totals, bool(money), extra)
    if not (ask or "").strip():
        return ""
    flaws = formulation_flaws(ask, slots_bad)
    if flaws:
        if isinstance(diag, dict):
            diag["ask_dropped"] = flaws[:2]
        return ""
    return ask


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


def compose(question, rows, agg, corrections=None, totals=None, coverage=None,
            measure_used=None, folders=None, money=True):
    payload = []
    shown = rows[:ROWS_TO_MODEL]
    # Бюджет делится на число показываемых строк: короткие строки не занимают чужого
    # места, длинные не режутся по произвольной границе.
    per_row = max(320, ROWS_BUDGET // max(1, len(shown)))
    for r in shown:
        # Строка, не влезшая в бюджет, помечается обрезанной. Прежде она обрывалась молча,
        # и модель цитировала обрубок как целое значение — «ООО Ромашка-Тор» вместо
        # «ООО Ромашка-Торг». Числа так не портятся (их ставит код), а вот имя, номер или
        # адрес уходили человеку укороченными и выглядели настоящими (п. 13).
        head = r[5][:per_row] + ("…" if len(r[5]) > per_row else "")
        tail = []
        if money and _num(r[2]):
            tail.append("amount=%s" % ("%d" % _num(r[2]) if _num(r[2]) == int(_num(r[2]))
                                       else "%.2f" % _num(r[2])))
        if r[3]:
            tail.append("date=%s" % r[3])
        payload.append(head + ((" | " + " | ".join(tail)) if tail else ""))
    # 🔴 ЧИСЛО ПОКАЗАННЫХ СТРОК — НЕ ЧИСЛО ЗАПИСЕЙ, и подавать его как число записей
    # нельзя. `rows` обрезаны выборкой (`TOPK`), показываются из них первые
    # `ROWS_TO_MODEL`, а записей в множестве столько, сколько посчитала база, — это
    # `{count}`. Прежде в задании стояло «ROWS FOUND (40)», и модель честно пересказывала
    # эти 40 как ответ на «сколько»: `[замер 04.08]` на вопросе про склады ответ вышел
    # «есть только три документа приобретения» при 249 записях в множестве — размер
    # выборки выдан за размер множества (п. 13, молчаливая подмена). Числа здесь больше
    # нет вовсе: строки названы примерами, а за счётом модель идёт на место `{count}`.
    # Когда счёта нет (агрегат не посчитан), остаётся прежний вид — лучше него ничего.
    head_line = ("ROWS (examples from the matching set, not the whole of it — the number "
                 "of records is {count}):" if agg else "ROWS FOUND (%d):" % len(rows))
    body = "QUESTION: %s\n\n%s\n%s" % (
        question, head_line, "\n".join("- " + p for p in payload))
    # 🔴 ЗНАЧЕНИЙ ПОСЧИТАННОГО МОДЕЛЬ НЕ ВИДИТ — ТОЛЬКО РОЛИ И ИМЕНА.
    #
    # Правило «числа ставит код» держалось двумя опорами: словами в промте и подстановкой
    # `{total}`. Первая опора замерена `[замер 04.08, step6_live.py]` и оказалась дырявой:
    # на восьми вопросах модель семь раз оставила место — и один раз набрала 249 цифрами,
    # а на повторных прогонах это было то 1, то 0 раз. То есть слова работают почти
    # всегда, а «почти» и есть весь вопрос: пока число можно СПИСАТЬ, оно рано или поздно
    # списывается, и тогда защищает только гейт — а он смотрит, ЕСТЬ ли такое число в
    # данных, но не в своей ли оно роли (`F285`).
    #
    # Вторая попытка это не лечит: `[замер 04.08]` из двух случаев она исправила один.
    # Проверка тут вообще бессильна по устройству — роль числа в прозе кодом не
    # определяется, а определять её разбором текста значит гадать (п. 12) и привязываться
    # к языку. Поэтому убран сам источник: списывать больше неоткуда. Модели даётся имя
    # величины, перечень ролей и МЕСТО под каждую; значения подставляет код после ответа.
    # Это то же решение, что и везде в проекте, — запрет держится устройством, а не
    # просьбой, — доведённое до конца.
    #
    # Значения СТРОК при этом остаются: цитата из записи (номер документа, дата, имя
    # стороны) моделью и должна копироваться, это не арифметика, а выписка.
    has_money = bool(money) and bool(agg) and (
        agg.get("sum") or agg.get("max") or agg.get("min"))
    if agg and not has_money:
        # Нет выбранного поля (A2: want=count|list) или нет денежной колонки.
        # Передать sum=0 нельзя: модель ответит «0», и гейт согласится.
        body += ("\n\nCOMPUTED OVER ALL MATCHING ROWS. The values are not shown; each "
                 "placeholder below is replaced by the system with the exact figure:")
        body += "\n  count (number of records) -> {count}"
        if agg.get("date_min"):
            body += "\n  period                    -> {date_min} .. {date_max}"
        if agg.get("undated"):
            body += "\n  records without a date (not in the period filter) -> {undated}"
        if agg.get("outside_period"):
            body += ("\n  records matching everything except the period "
                     "-> {outside_period}")
        if money:
            body += ("\n  (no numeric quantity matches the question for this record type — "
                     "no placeholder other than {count} is available here)")
    elif agg:
        body += ("\n\nCOMPUTED OVER ALL MATCHING ROWS for the quantity «%s». The values "
                 "are not shown; each placeholder below is replaced by the system with "
                 "the exact figure:" % (agg.get("measure") or "-"))
        body += "\n  count (number of records) -> {count}"
        # 🔴 ПО СКОЛЬКИМ ЗАПИСЯМ ПОСЧИТАНЫ sum И avg. `aggregate` считает `count_amount`
        # отдельно именно для этого («иначе среднее по 31 строке уходит как среднее по
        # 1344»), но до модели число не доходило вовсе — комментарий в `aggregate`
        # описывал требование, которого в коде не было. Ответ «средний чек 293 900 по
        # 1344 документам» при 31 строке с суммой неверен, а гейт его пропускает: оба
        # числа посчитаны базой, каждое по отдельности верно. Показываем, только когда
        # числа расходятся, — иначе это лишняя строка на каждый вопрос.
        ca = agg.get("count_amount")
        if ca is not None and ca != agg["count"]:
            body += ("\n  count_amount (records having this quantity; sum and avg are "
                     "over these, and there are fewer of them than records) "
                     "-> {count_amount}")
        body += "\n  sum (TOTAL)               -> {total}"
        body += "\n  max (largest single)      -> {max}"
        body += "\n  min (smallest single)     -> {min}"
        body += "\n  avg (average)             -> {avg}"
        if agg.get("date_min"):
            body += "\n  period                    -> {date_min} .. {date_max}"
    if totals and money:
        # Итоги по каждой величине — с ИМЕНАМИ из базы, но опять же без значений. Модель
        # сама возьмёт подходящую под вопрос величину; списать её итог ей неоткуда.
        body += ("\n\nCOMPUTED OVER ALL MATCHING ROWS, by quantity name — values not "
                 "shown, address them by name:")
        for m, v, mx, mn in totals:
            body += ("\n  %s: total -> {total:%s}, largest single -> {max:%s}, "
                     "smallest single -> {min:%s}" % (m, m, m, m))
    if coverage:
        # НЕПОЛНОТА ЭТОЙ СУЩНОСТИ. Модель обязана предупредить на языке вопроса — сами мы
        # приписать не можем: своя фраза была бы на одном языке независимо от вопроса.
        # Числа отсюда разрешены гейту явно, поэтому предупреждение не будет отвергнуто
        # как выдумка.
        body += ("\n\nDATA COMPLETENESS WARNING: this kind of records is INCOMPLETE in "
                 "the search: %s rows exist in the source system, %s reached the search, "
                 "%s are missing (%s). The figures above are computed over what reached "
                 "the search only. You MUST warn the user about this in your answer, in "
                 "their language, stating the number of missing rows in digits."
                 % ("{in_1c}", "{in_search}", "{missing}",
                    coverage.get("reason") or "reason unknown"))
    # 🔴 ОГОВОРКИ К ОТВЕТУ ГОВОРИТ МОДЕЛЬ, А НЕ МЫ. Прежде обе дописывались нашей прозой
    # ПОСЛЕ модели — по-русски, в файле, где от русских умолчаний отказались сознательно:
    # `NO_DATA_TEXT` пуст, отказ и уточнение формулирует модель именно потому, что своя
    # фраза была бы на одном языке независимо от языка вопроса. На англоязычном клиенте
    # ответ выходил смешанным. Механизм тот же, что у предупреждения о неполноте выше.
    # Числа отсюда разрешены гейту, поэтому оговорка не будет отвергнута как выдумка.
    if measure_used:
        body += ("\n\nQUANTITY USED: the figures above are computed over the quantity named "
                 "'%s'. Name that quantity in your answer, in the user's language, so they "
                 "know WHICH value was summed." % measure_used)
    if folders:
        body += ("\n\nGROUPS EXCLUDED: %s records were folders (grouping nodes of the "
                 "catalogue), not real items, and are NOT included in the count above. You "
                 "MUST say this in your answer, in the user's language, stating the number "
                 "%s in digits — otherwise a user who knows the raw record count will think "
                 "the figure is wrong." % ("{folders}", "{folders}"))
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


def _plausible(d, mo):
    """Существует ли такой день и месяц. Отрицательная дробь датой не является.

    🔴 Проверки диапазона не было вовсе, и «-3.26» читалось как «3-е число 26-го
    месяца»: числовая ветка гейта такой токен не видела вообще, а датная сверяла его с
    настоящими датами и отвергала. `[замер 04.08, step7_bench]` так отвергались верные
    ответы с отрицательными величинами (сторно, возвраты, остатки). Границы здесь не
    подгонка под базу, а календарь: он одинаков на любой конфигурации.
    """
    return 1 <= d <= 31 and 1 <= mo <= 12


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
        if _plausible(d, mo):
            out.append((d, mo, y))
            seen.append(m.span())
    for m in DATE2.finditer(str(text or "")):
        d, mo = int(m.group(1)), int(m.group(2))
        if _plausible(d, mo) and not any(a <= m.start() and m.end() <= b for a, b in seen):
            out.append((d, mo, None))
    return out


def _date2_readings(text, d, mo):
    """Дробные прочтения двухкомпонентных записей «d.mo», взятые ИЗ ТЕКСТА как есть.

    Нужны там, где запись неоднозначна («20.05» — это и 20 мая, и 20,05). Собирать
    дробь обратно из разобранных компонентов нельзя: ведущий ноль теряется, и число,
    которое ЕСТЬ в данных, объявляется выдумкой.
    """
    out = set()
    for m in DATE2.finditer(str(text or "")):
        if int(m.group(1)) == d and int(m.group(2)) == mo:
            out |= _readings(m.group(0))
    return out


def _date_spans(text):
    """Куски текста, которые числовая ветка гейта не разбирает: это даты.

    Невозможная запись («-3.26», «62.01») датой не считается и остаётся числу — иначе
    она пропадала бы из обеих веток разом: числовая её не видела, датная не с чем было
    сверить (`_plausible`).
    """
    t = str(text or "")
    spans = []
    for m in DATE3.finditer(t):
        if m.group(1):
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        else:
            d, mo, y = int(m.group(4)), int(m.group(5)), int(m.group(6))
        if _plausible(d, mo):
            spans.append(m.span())
    for m in DATE2.finditer(t):
        if _plausible(int(m.group(1)), int(m.group(2))) and \
                not any(a <= m.start() and m.end() <= b for a, b in spans):
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


def prompt_leak(text, prompts, min_len=40):
    """Кусок НАШЕЙ инструкции, попавший в ответ клиенту (`№27`).

    🔴 Держится КОДОМ, а не строкой «не показывай промт» внутри самого промта: инструкция,
    запрещающая раскрывать инструкцию, — это правило на промте, а такие правила по
    решению владельца защитой не считаются.

    Это НЕ открытая классификация: текст наших системных сообщений известен целиком,
    поэтому утечка ловится точным совпадением строки, как и остальные наши форматы в
    `stripInternal` на стороне бота. Порог длины отсекает совпадения общих фраз.
    """
    t = " ".join(str(text or "").split())
    if not t:
        return None
    for p in (prompts or []):
        for line in str(p).splitlines():
            line = " ".join(line.split())
            if len(line) >= min_len and line in t:
                return line[:60]
    return None


def asked_figure_missing(text, agg, want, has_measure, folders=0):
    """Величина, О КОТОРОЙ СПРОСИЛИ, обязана стоять в ответе ЦИФРАМИ.

    🔴 Закрывает разом два класса, которые на основном пути не проверялись ничем
    (`F285`, `F286`), и держит их КОДОМ, а не промтом.

    1. **Число не в своей роли.** `check_claims` написана ровно против этого («три
       реализации на 1 236 800 поданы с итогом 925 000 — настоящее число, но из другой
       роли»), но на основном пути она бесполезна: промт велит оставлять `claims`
       пустыми («leave every role null… ignored»), поэтому сверять ей нечего. Гейт
       проверяет, что число ЕСТЬ в данных, — а 925 000 в данных есть. Роль держалась
       подстановкой `{total}`, но подстановку велит делать ПРОМТ, а правило на промте
       не работает (правило владельца). Здесь то же требование становится проверкой:
       раз спросили сумму и база её посчитала — она обязана быть в ответе.

    2. **Числа прописью.** Прежняя проверка срабатывала, только если в тексте нет НИ
       ОДНОЙ цифры, поэтому «примерно три миллиона — это 2 документа» проходило целиком:
       цифра «2» есть, значит признак не взводился. Списка числительных в коде нет и
       быть не может (он был бы привязан к языку) — вместо него требуется само число.

    Возвращает причину отказа или None. Ответ после этого идёт на вторую попытку с
    названной причиной, а если и она не сойдётся — числа уходят структурой (`figures`),
    то есть проверка не превращается в молчание (п. 21).
    """
    if not agg:
        return None
    have = None
    if want == "count":
        need = agg.get("count")
    elif want == "sum" and has_measure:
        # Без выбранной величины `sum` считается по пустому месту: ноль значил бы «не
        # считали», а не «ноль», и требовать его в тексте было бы требованием выдумки.
        need = agg.get("sum")
    else:
        need = None
    if need is not None:
        have = _norm_numbers(text)
        nf = float(need)
        if nf not in have and round(nf, 2) not in have:
            return "величина %s не названа цифрами" % _fmt(nf)
    # 🔴 ЧТО ОТБРОШЕНО — ТОЖЕ ОБЯЗАНО БЫТЬ НАЗВАНО ЧИСЛОМ (`№9`, п. 13: молчаливая
    # потеря = дефект). Оговорка про папки справочника ушла в промт, потому что своей
    # прозой мы писали её по-русски на любом языке вопроса. Слова остаются за моделью,
    # а вот ЧИСЛО отброшенного проверяется здесь: человек, знающий про 252 строки,
    # обязан понять, откуда 227.
    if folders:
        if have is None:
            have = _norm_numbers(text)
        if float(folders) not in have:
            return "отброшено %d — не названо в ответе" % folders
    return None


def stale_note(out, age, warn_sec, text_fmt):
    """Приписка о старении — в КАЖДЫЙ ответ, включая отказ (`F223`).

    Прежде ветка `no_data` её не получала, и на трёхсуточных данных «таких данных нет»
    звучало ровно так же уверенно, как на свежих, — при том что именно здесь оговорка
    нужнее всего: данные могут существовать и просто ещё не доехать. `unavailable` не
    включён намеренно: там сообщение и так о сбое, а приписка про возраст корпуса к нему
    отношения не имеет.
    """
    if not isinstance(out, dict) or age is None or age <= warn_sec:
        return out
    if out.get("kind") not in ("answer", "figures", "clarify", "no_data"):
        return out
    out["text"] = ((out.get("text") or "") + text_fmt % (age // 60)).strip()
    out["stale"] = True
    return out


def _threshold_values(intent):
    """Значения НАШИХ условий отбора: пороги суммы. Дата в текст ответа попадает как
    дата, её проверяет отдельная ветка гейта."""
    amt = (intent or {}).get("amount") or {}
    return [v for v in (amt.get("value"), amt.get("value2")) if v is not None]


def _filter_values(intent):
    """Числа НАШИХ УСЛОВИЙ ОТБОРА: пороги и числовые понятия, по которым шёл поиск.

    🔴 ЭТО ЗАМЕНА БЕЛОМУ СПИСКУ «ВСЕ ЧИСЛА ВОПРОСА» (`F244`). Прежде в разрешённое
    уходило `_norm_numbers(question)` целиком — то самое отмывание, которое докстрока
    самой `gate()` называет недопустимым: вопрос приходит аргументом инструмента,
    сочиняет его модель бота, то есть проверяемый пополнял свой же белый список.
    Плагин на стороне бота этот путь закрыл 02.08 (`verify-core.isGrounded`: числа
    сообщения заземляют ответ, только когда эталона нет вовсе) и в комментарии
    утверждал, что то же самое закрыто на стороне `serene_ask`, — а закрыто не было.

    Разрешённым остаётся значение, по которому МЫ отфильтровали или отобрали данные.
    Порог (`amount`) применён нашим предикатом, числовое понятие (`terms`) — нашим
    запросом к индексу: строки, которые мы считаем, ему отвечают. Обоснование то же,
    что у порогов, и проверяется кодом, а не доверием к тексту вопроса. [замер 28.07]
    ради этого класса правило и заводилось: у вопроса «обороты по счёту 62» число «62»
    приходит понятием отбора, и верный ответ с ним больше не отвергается.
    """
    out = list(_threshold_values(intent))
    for group in ((intent or {}).get("terms") or []):
        for alt in (group if isinstance(group, list) else [group]):
            out += sorted(_norm_numbers(alt))
    return out


def _filter_dates(intent):
    """Границы периода, по которому МЫ отобрали строки: «с 01.01.2019 по 31.12.2019».

    Они верны по построению — фильтр применён нами, — но в данных такой строки может и
    не быть (никто не продавал ровно 1 января), и тогда гейт отвергал верный ответ,
    назвавший период отбора. Тот же случай, что и с порогом суммы 27.07, только про дату.
    """
    p = (intent or {}).get("period") or {}
    return [str(x) for x in (p.get("from"), p.get("to")) if x]


LIST_MARKER = re.compile(r"^[ \t]*\d+[.)][ \t]+", re.M)
# Перечисление внутри строки: «Итого 5: 1) первая, 2) вторая». Номер пункта здесь тоже
# разметка, а не число из данных, — но опознаётся он уже, чем в начале строки: не больше
# двух цифр и сразу после двоеточия, точки с запятой или запятой. `[замер 04.08]` без
# этого прибор шага 7 отвергал 7 верных ответов из 44 вопросов на одной лишь нумерации.
INLINE_MARKER = re.compile(r"(?<=[:;,])[ \t]*\d{1,2}[.)][ \t]+")


def without_list_markers(text):
    """Разметка списка — не утверждение о данных (`F248`).

    «1.», «2)» в начале строки нумеруют пункты. Гейт считал их наравне с суммами, и
    любой перечисленный ответ («Итого 5: 1) первая, 2) вторая») объявлялся выдумкой —
    `[замер 04.08, step7_bench]` 4 верных ответа из 44 вопросов отвергнуты только за
    нумерацию. Плагин на стороне бота снимает их с 02.08 (`withoutListMarkers`), а
    сервис — нет: одна и та же разметка на двух половинах шага 7 значила разное.
    Снимается ТОЛЬКО маркер пункта, содержимое пункта проверяется как обычно. Маркеров
    два вида: в начале строки (номер любой длины — так пишут списки) и внутри строки
    после двоеточия или запятой (не больше двух цифр — так пишут перечисление в прозе).
    Асимметрия намеренная: в начале строки «103.» — почти наверняка нумерация, а в
    середине предложения такое число скорее величина, и снимать его было бы послаблением.
    """
    return INLINE_MARKER.sub("", LIST_MARKER.sub("", str(text or "")))


def rows_seen(rows):
    """Строки в том виде, в каком их ВИДЕЛА модель: показанные и обрезанные (`F247`).

    🔴 Гейт заземлял ответ на ВСЕХ добытых строках (`TOPK` = 40), тогда как модели
    показывается `ROWS_TO_MODEL` = 25, и каждая ещё режется бюджетом. Числа из
    непоказанных строк и из отрезанных хвостов служили белым списком для того, чего
    модель не видела: `[замер 04.08, step7_bench]` подменённые крайние значения (31, 7)
    проходили гейт, потому что где-то в невидимой строке такие числа есть.

    Скопировать модель может только то, что ей дали, поэтому сужение не может отвергнуть
    верный ответ — оно лишь снимает лишнее разрешение. Срез и бюджет считаются теми же
    правилами, что в `compose`: одна граница на оба места.
    """
    shown = list(rows or [])[:ROWS_TO_MODEL]
    per_row = max(320, ROWS_BUDGET // max(1, len(shown)))
    return [list(r[:5]) + [(r[5] or "")[:per_row]] for r in shown]


def gate(answer, rows, agg, thresholds=None, our_dates=None, money=True):
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

    def allow(v):
        """Значение и все его равнозначные прочтения: округление, целое, БЕЗ ЗНАКА.

        🔴 Минус в числовой токен не входит (`NUMTOK` начинается с цифры), поэтому
        посчитанное базой отрицательное значение не совпадало с тем, что читает
        гейт из текста: ответ «наименьшая -70 552,79» отвергался, хотя это ровно `min`
        из агрегата `[замер 04.08, step7_bench, 21 случай из 1484]`. Возвраты, сторно и
        отрицательные остатки — обычные данные 1С, и отказ на них означал отказ при
        наличии данных (п. 21). Знак при этом ничего не разрешает лишнего: величина всё
        равно сверяется с данными, а «-5» и «5» гейт и так не различал бы.
        """
        try:
            f = float(v)
        except (TypeError, ValueError):
            return
        for x in (f, abs(f)):
            allowed.add(round(x, 2))
            if x == int(x):
                allowed.add(float(int(x)))

    for t in (thresholds or []):
        allow(t)
    for r in rows:
        allowed |= _norm_numbers(r[5])
        allowed |= _norm_numbers(r[3])
        # amount приходит из psql как «5000000.00» — через текстовый разбор это давало
        # ещё и 500000000. Берём числом.
        if money:
            allow(r[2])
    if agg:
        # ЧИСЛАМИ, а не текстом: прогон "%.2f" через разбор давал ещё и значение,
        # умноженное на 100 (дробная часть склеивалась с целой).
        if money:
            for key in ("sum", "min", "max", "avg"):
                if agg.get(key) is not None:
                    allow(agg[key])
        allow(agg["count"])
    # Числа из ВОПРОСА в белый список больше не идут. Вопрос — это аргумент, который
    # сочиняет модель бота: она сама пополняла список того, что ей разрешено сказать,
    # и через это проходило любое выдуманное число.

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
    # Границы НАШЕГО периода отбора — на тех же правах, что порог суммы: фильтр применён
    # нами, значит дата верна по построению, даже если ровно в этот день строк нет.
    for s in (our_dates or []):
        known += _dates(s)

    # 🔴 ГОД ИЗВЕСТНОЙ ДАТЫ — ЭТО ЧИСЛО ИЗ ДАННЫХ (`F245`). Дата в строке (`2019-11-18`)
    # вырезается токенайзером как дата, поэтому «2019» отдельным числом в разрешённое не
    # попадало ниоткуда: ответ «за 2019 год продано на 1 236 800» отвергался целиком —
    # из-за года, стоящего в данных `[замер 04.08, probe_gate]`. Год берётся только из
    # ИЗВЕСТНЫХ дат (строки, границы агрегата, наш период), то есть выдуманный «2035» не
    # проходит. Отвергать верный ответ — такой же дефект, как пропустить неверный (п. 21).
    for _kd, _kmo, _ky in known:
        if _ky is not None:
            allowed.add(float(_ky))

    # Токен обоснован, если ХОТЯ БЫ ОДНО его прочтение есть в данных. Нумерация пунктов
    # утверждением о данных не является и снимается до разбора (`F248`).
    answer = without_list_markers(answer)
    bad = [sorted(r)[0] for r in _tokens(answer) if not (r & allowed)]

    for d, mo, y in _dates(answer):
        ok = any(kd == d and kmo == mo and (y is None or ky is None or ky == y)
                 for kd, kmo, ky in known)
        # Двухкомпонентная запись без года неоднозначна: «10.5» — это и дата, и дробь.
        # Разрешаем, если такое ЧИСЛО есть в данных; выдуманное не пройдёт ни как дата,
        # ни как число.
        # 🔴 Дробь берётся ИЗ ИСХОДНОГО ТЕКСТА, а не собирается обратно из компонентов
        # `"%d.%d" % (d, mo)`: та сборка теряла ведущий ноль, и «20.05» превращалась в
        # 20.5 — то есть верное число, стоящее в данных, не заземлялось НИКОГДА, а
        # ответ отвергался целиком `[замер 02.08, test_gate.py]`. Ровно тот класс, что
        # п. 21 называет дефектом проверки.
        if not ok and y is None:
            ok = bool(_date2_readings(answer, d, mo) & allowed)
        if not ok:
            bad.append("%02d.%02d%s" % (d, mo, "" if y is None else ".%d" % y))
    return (not bad), bad


def count_figures(agg):
    """Числа ответа, когда величина не названа: счёт и — если было — отброшенное.

    🔴 `folders` уходит наружу вместе со счётом (`F249`). «Сколько записей» при
    отброшенных папках справочника — это ДВА числа, а не одно, и молчаливая потеря
    второго считается дефектом (п. 13). Прежде отброшенное держалось только прозой
    модели: не назвала — гейт отказывал в ответе целиком, и `[замер 04.08]` на живом
    вопросе «сколько всего контрагентов» это давало клиенту «проверенный ответ
    невозможен» при посчитанных 12 записях и 1 папке. Теперь число уходит полем, то
    есть доезжает и тогда, когда формулировка не сошлась.
    """
    out = {"count": (agg or {}).get("count")}
    if (agg or {}).get("folders"):
        out["folders"] = agg["folders"]
    return out


def gate_out(text, rows=(), agg=None, allowed=None, our_dates=None, money=True):
    """Один гейт на ВСЁ, что уходит человеку словами модели: числа + утечка инструкции.

    🔴 Заведён 04.08 (`F246`), потому что гейт стоял только на одной ветке из пяти.
    Числа проверялись у `kind=answer`, а уходящий человеку текст сочиняет модель ещё в
    четырёх местах: три уточнения о выборе сущности, уточнение о выборе величины и
    встречный вопрос модели (`ask`). Ни одно из них не проверялось ничем — при том что
    `HOW_IT_WORKS` про уточнение прямо утверждал обратное («уточнение возвращается
    только после гейта — числа в нём проверены базой наравне с обычным ответом»).
    Человеку разница не видна: «Вы про закупки на 73 млн или про регистр?» читается как
    факт о его данных независимо от того, вопрос это или ответ.
    """
    ok, bad = gate(text, list(rows or []), agg, allowed or [], our_dates,
                   money=money)
    leak = prompt_leak(text, OUR_PROMPTS)
    if leak:
        ok, bad = False, list(bad) + ["утечка инструкции: %s" % leak]
    return ok, bad


def _opt_values(opts):
    """Числа, которые модель ВИДЕЛА, сочиняя уточнение: имена вариантов и их приметы.

    Больше ей ничего не давали (`clarify_text` кладёт в задание только вопрос, метки и
    `distinct_by`), поэтому всё остальное числовое в уточнении — сочинённое.
    """
    out = []
    for o in (opts or []):
        for k in ("label", "distinct_by", "measure", "entity_label"):
            out += sorted(_norm_numbers(o.get(k) or ""))
        if o.get("found") is not None:
            try:
                out.append(float(o["found"]))
            except (TypeError, ValueError):
                pass
    return out


def clarify_say(question, opts, diag=None):
    """Уточняющий вопрос — от модели, но через гейт; не прошёл — перечень из ДАННЫХ.

    Молчания здесь не возникает: отвергнутая фраза заменяется перечислением меток
    вариантов, то есть данными без прозы. Так уже сделано в уточнении о величине —
    теперь это общий путь для всех уточнений, а не одна ветка из пяти.
    """
    fallback = ", ".join("«%s»" % (o.get("label") or o.get("measure") or "")
                         for o in (opts or []) if (o.get("label") or o.get("measure")))
    txt = clarify_text(question, opts)
    if not (txt or "").strip():
        return fallback
    ok, bad = gate_out(txt, [], None, _opt_values(opts))
    if ok:
        return clarify_complete(txt, opts)
    sys.stderr.write("ask CLARIFY GATE: числа вне вариантов: %s\n" % bad[:4])
    if isinstance(diag, dict):
        diag["clarify_gate_rejected"] = bad[:4]
    return fallback


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


# Все НАШИ системные сообщения в одном месте: по ним `prompt_leak` ловит утечку
# инструкции в ответ клиенту точным совпадением строки (`№27`).
OUR_PROMPTS = [INTENT_SYS, PICK_SYS, CLARIFY_SYS, REFUSE_SYS, ANSWER_SYS, COVERAGE_SYS]

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
    # 🔴 ЧИСЛОВОЙ ГЕЙТ — И ЗДЕСЬ (`F128`). Докстрока этой функции обещает «тот же гейт,
    # что обычный ответ», но `gate()` тут не звалась ни разу: проверялись только `claims`,
    # а промт велит оставлять их пустыми, то есть не проверялось НИЧЕГО. Любое число,
    # которое модель напишет в ответе о полноте, уходило клиенту без сверки с переписью —
    # при том что «сколько данных потеряно» такое же число, как «на какую сумму продано»
    # (п. 13 и п. 10 контракта). Разрешённое — сама перепись: итоги и строки поимённо.
    allowed = [float(in_1c), float(in_search), float(n_lost), float(ent_lost),
               float(ent_denied)]
    for r in lost:
        for cell in r[1:3]:
            try:
                allowed.append(float(_num(cell)))
            except (TypeError, ValueError):
                pass
    ok_nums, bad_nums = gate(text, [], None, allowed)
    if not ok_nums:
        sys.stderr.write("ask COVERAGE GATE: числа вне переписи: %s\n" % bad_nums[:4])
    leak = prompt_leak(text, OUR_PROMPTS)
    if leak:
        bad_nums, ok_nums = bad_nums + ["утечка инструкции: %s" % leak], False
    ok_roles, bad = (ok_roles and ok_nums), (bad + bad_nums)
    if not ok_roles or not (text or "").strip():
        sys.stderr.write("ask COVERAGE GATE: %s\n" % bad[:4])
        # Числа посчитаны и верны — отдаём их структурой, как и на обычном пути.
        # 🔴 Текст, ОТВЕРГНУТЫЙ гейтом, наружу не идёт: прежде он возвращался полем
        # `text` как есть, то есть проверка срабатывала, а забракованная формулировка
        # всё равно доходила до клиента. Формулирует вызывающий — по числам.
        return {"partial": None, "kind": "figures", "text": "",
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
# Арбитр работает ДЕТЕКТОРОМ: разошлись посчитанные числа кандидатов — спрашиваем человека,
# а не даём модели выбрать между ними (задача 17). Выключатель нужен, чтобы прежнее
# поведение можно было вернуть одним значением, если приёмка покажет обратное.
ARBITER_DETECTS = os.environ.get("ASK_ARBITER_DETECTS", "1") == "1"
# Отсев кандидатов по знанию установки «на что НЕ отвечает» (`not_for_excludes`).
NOT_FOR = os.environ.get("ASK_NOT_FOR", "1") == "1"
# Словарь со стеммингом — им сравниваются слово человека и название сущности.
# Создаётся сборкой (`corpus_init.sql`), локаль наследует от основного словаря.
STEM_DICT = os.environ.get("ASK_STEM_DICT", "search_dict_stem")
# Сколько секунд держать в процессе перечень неоднозначных меток: он меняется тактом
# сборки, а не между вопросами. Это бюджет обращений к базе, а не порог правильности.
AMBIG_TTL = int(os.environ.get("ASK_AMBIG_TTL", "300"))

# 🔴 ВИД ЗАПИСИ — ЕДИНСТВЕННОЕ, ЧТО РАЗЛИЧАЕТ ОДНОИМЁННЫЕ ИСТОЧНИКИ. Метка собирается
# срезанием типа (`corpus_build.sql`: `regexp_replace(orig,'^[^_]+_','')`), поэтому
# документ и одноимённый регистр получают ОДНУ строку. Живой прогон okna 13.08: человек
# 23 раза уточнял «продажи за неделю» и не получил числа — в списке стояли два
# неразличимых «Реализация ТМЦ» (документ и регистр накопления), выбор возвращался той
# же строкой, `resolve_focus` честно не сводил её (п. 12) и круг замыкался.
#
# Вид берётся ИЗ ИМЕНИ ТИПА OData, то есть от ПЛАТФОРМЫ, а не от конкретной базы: набор
# типов один у всех конфигураций 1С, поэтому это не привязка (девиз 29.07). Слово для
# человека — перевод платформенного термина, не имя таблицы: `document_реализациятмц`
# наружу по-прежнему не уходит (решение 03.08).
_KIND_WORD = {
    "catalog": "справочник",
    "document": "документ",
    "documentjournal": "журнал документов",
    "accumulationregister": "регистр накопления",
    "informationregister": "регистр сведений",
    "accountingregister": "регистр бухгалтерии",
    "calculationregister": "регистр расчёта",
    "chartofaccounts": "план счетов",
    "chartofcharacteristictypes": "план видов характеристик",
    "chartofcalculationtypes": "план видов расчёта",
    "businessprocess": "бизнес-процесс",
    "task": "задача",
    "exchangeplan": "план обмена",
    "constant": "константа",
    "enum": "перечисление",
}


def kind_word(src_table):
    """Вид записи словом человека. Неизвестный тип — пустая строка (молча не гадаем)."""
    head = str(src_table or "").split("_", 1)[0].lower()
    return _KIND_WORD.get(head, "")


def label_with_kind(src_table, label):
    """Подпись, различающая одноимённые источники: «Реализация ТМЦ (документ)».

    🔴 ПОДПИСЬ И `focus` — ОДНА СТРОКА. Отдельный «ключ выбора», не совпадающий с тем,
    что видит человек, уже проходили 03.08: бот пересказывает клиенту всё, что видит в
    ответе инструмента, и внутреннее имя утекало в чат мимо зачистки плагина. Поэтому
    различитель кладётся В ТУ ЖЕ строку, которую человек читает и которую бот вернёт
    в `focus`.
    """
    k = kind_word(src_table)
    lab = (label or "").strip() or str(src_table)
    return "%s (%s)" % (lab, k) if k else lab


_AMBIG_CACHE = {"at": 0.0, "set": frozenset()}


def ambiguous_labels():
    """Метки, которые в БАЗЕ носит больше одного источника.

    🔴 Считается по всей карте сущностей, а не по показанному списку. Живой замер okna
    13.08: в вариантах стояла одна «Реализация ТМЦ», подпись выглядела однозначной — а
    `resolve_focus` сводит по базе, где их две (документ и регистр), и выбор человека
    снова отбрасывался. Различитель нужен там, где строка НЕ УНИКАЛЬНА В БАЗЕ, иначе
    круг замыкается на сущности, которой в списке даже не было.

    Ответ живёт в процессе несколько минут: карта сущностей меняется тактом сборки,
    а не между вопросами.
    """
    now = time.time()
    if now - _AMBIG_CACHE["at"] < AMBIG_TTL and _AMBIG_CACHE["set"]:
        return _AMBIG_CACHE["set"]
    try:
        rows = psql("SELECT lower(replace(label,' ','')) FROM %s "
                    "GROUP BY 1 HAVING count(*) > 1" % TABLES)
    except RuntimeError:
        return _AMBIG_CACHE["set"]
    got = frozenset(r[0] for r in rows or [] if r and r[0])
    _AMBIG_CACHE.update({"at": now, "set": got})
    return got


def disambiguate_labels(pairs, ambiguous=None):
    """[(src, label)] -> {src: подпись}. Вид дописывается там, где метка неоднозначна.

    Неоднозначной считается метка, совпавшая внутри списка ИЛИ носимая несколькими
    источниками в базе. Где неоднозначности нет — подпись прежняя, а с ней и прежние
    замеры выбора сущности.
    """
    if ambiguous is None:
        ambiguous = ambiguous_labels()
    norm = lambda s: "".join(str(s or "").lower().split())
    seen = {}
    for src, lab in pairs:
        seen.setdefault(norm(lab), []).append(src)
    out = {}
    for src, lab in pairs:
        many = len(seen.get(norm(lab), [])) > 1 or norm(lab) in ambiguous
        out[src] = label_with_kind(src, lab) if many else ((lab or "").strip() or src)
    return out


# Пояснение к варианту уточнения: «для чего годится» из словаря синонимов плюс дата
# актуальности данных. Различает варианты не оно, а вид записи (`label_with_kind`) —
# пояснение добавлено сверх него, чтобы человеку было понятно, что он выбирает.
# «Для чего годится» пишет модель один раз при сборке словаря на языке базы, поэтому на
# чужой базе оно появляется само; пока словарь пуст (первые такты новой базы), подпись
# остаётся с одним видом записи, и выбор всё равно однозначен.
# Дата ставится только там, где она РАЗЛИЧАЕТ: одинаковое «по 13.08» у всех вариантов
# строку удлиняет и ничего не разводит. Берётся из корпуса, где её разобрала сборка;
# у справочников даты нет по природе — тогда её просто не показываем.
def opts_hints(srcs):
    """Для каждого источника — короткое пояснение или ничего."""
    srcs = [s for s in srcs if s]
    if len(srcs) < 2:
        return {}
    lst = ", ".join(lit(s) for s in srcs)
    what, when = {}, {}
    try:
        for r in psql("SELECT src_table, best_used_for FROM search_entity_alias "
                      "WHERE src_table IN (%s)" % lst) or []:
            if r and r[0] and len(r) > 1 and (r[1] or "").strip():
                what[r[0]] = r[1].strip()
    except RuntimeError:
        pass
    try:
        for r in psql("SELECT src_table, max(doc_date)::VARCHAR FROM %s WHERE src_table IN (%s) "
                      "AND doc_date IS NOT NULL GROUP BY 1" % (CORPUS, lst)) or []:
            if r and r[0] and len(r) > 1 and (r[1] or "").strip():
                when[r[0]] = r[1].strip()[:10]
    except RuntimeError:
        pass
    if len(set(when.values())) < 2:      # дата одна на всех — не различает
        when = {}
    built, miss = {}, {}
    try:
        for r in psql("SELECT src_table, last_built_at::VARCHAR FROM %s "
                      "WHERE src_table IN (%s) AND last_built_at IS NOT NULL"
                      % (TABLES, lst)) or []:
            if r and r[0] and len(r) > 1 and (r[1] or "").strip():
                built[r[0]] = r[1].strip()[:16]
    except RuntimeError:
        pass
    if len(set(built.values())) < 2:
        built = {}
    try:
        for r in psql("SELECT entity, (в_1С - в_корпусе) FROM search_coverage "
                      "WHERE entity IN (%s) AND в_1С > в_корпусе" % lst) or []:
            if r and r[0] and len(r) > 1:
                try:
                    miss[r[0]] = int(r[1])
                except (TypeError, ValueError):
                    pass
    except RuntimeError:
        pass
    if not miss or len(set(miss.values())) < 2:
        miss = {}
    out = {}
    for s in srcs:
        parts = []
        if what.get(s):
            parts.append(what[s][:90])
        if when.get(s):
            parts.append("данные по %s" % when[s])
        if built.get(s):
            parts.append("в поиске с %s" % built[s])
        if miss.get(s):
            parts.append("не в поиске %s" % miss[s])
        if parts:
            out[s] = "; ".join(parts)
    return out


def mk_opts(srcs, lab_by, marks=None, by=None, match="", preds=None, live=None):
    """Варианты уточнения одним видом на все пять веток ответа.

    Здесь же дописывается вид записи одноимённым источникам: подпись, которую читает
    человек, и значение `focus`, которое возвращает бот, — одна и та же строка, поэтому
    различитель ставится в этой точке, а не в мосте.

    В перечень идёт только источник с живым счётом по тем же предикатам, что и ответ
    (период). Поле `found` — лексические попадания, для этого не годится.
    """
    marks, by = marks or {}, by or {}
    counted = live
    if counted is None and preds is not None:
        counted = live_src_counts(srcs, match, preds)
    if counted is not None:
        srcs = [s for s in srcs if counted.get(s, 0) > 0]
    dis = disambiguate_labels([(s, lab_by.get(s, s)) for s in srcs])
    hint = opts_hints(srcs)
    found_of = counted if counted is not None else by
    return [{"src": s, "label": dis.get(s, lab_by.get(s, s)), "hint": hint.get(s, ""),
             "distinct_by": marks.get(s, ""), "found": found_of.get(s, 0)} for s in srcs]


def live_src_counts(srcs, match, preds):
    """Живой счёт строк по тем же предикатам, что и ответ. None — база не ответила."""
    if not srcs:
        return {}
    src = INDEX if match else CORPUS
    folder = "NOT coalesce(map_extract_value(flags, 'IsFolder'), false)"
    parts = []
    for s in srcs:
        where = [w for w in ([match] + list(preds or [])
                             + ["src_table = %s" % lit(s), folder]) if w]
        parts.append("SELECT %s AS t, count(*) AS n FROM %s WHERE %s"
                     % (lit(s), src, " AND ".join(where)))
    try:
        rows = psql(" UNION ALL ".join(parts))
    except RuntimeError:
        return None
    out = {}
    for r in rows or []:
        try:
            if r and r[0]:
                out[r[0]] = int(r[1])
        except (TypeError, ValueError, IndexError):
            continue
    return out


def empty_after_period_action(intent):
    """Что делать, когда после фильтра rows пуст. Кодом, не промтом.

    Пустое после фильтра не равно «данных нет». Выведенный период не имеет права
    отказать. Названный период с нулём внутри — речь про пустой период, не
    kind=no_data про существование.
    """
    if serene_enough is None:
        return "no_data"
    p = (intent or {}).get("period") or {}
    has_period = bool(p.get("from") or p.get("to"))
    if serene_enough.period_assumed(intent) and has_period:
        return "drop_assumed"
    if serene_enough.period_given(intent):
        return "empty_period"
    return "no_data"


def drop_period_preds(intent, preds):
    """Снять датные предикаты. Возвращает (intent без period, preds без дат)."""
    date_preds = set(_predicates(intent))
    new_preds = [p for p in preds if p not in date_preds]
    new_intent = dict(intent)
    new_intent["period"] = {}
    return new_intent, new_preds


def resolve_focus(focus, diag=None):
    """Свести `focus` к ИМЕНИ ИСТОЧНИКА, как бы его ни назвали.

    🔴 ЗАЧЕМ. `focus` приходит от бота, а бот берёт название оттуда, где его увидел —
    и это **разные пространства имён**. Уточнение сервиса даёт внутреннее имя
    (`catalog_классификаторбанков`), а страница вики — человеческий заголовок
    («Классификатор Банков»). [замер 02.08] как только смысловой поиск по вики заработал,
    бот стал передавать заголовок, сервис его не узнавал и отвечал «нет данных» — при том
    что тот же вопрос без `focus` отвечался верно (37 банков). Отказ при наличии данных —
    дефект (п. 21), и чинится он здесь, а не просьбой к модели «передавай правильное имя»:
    правило на промте не работает.

    Сведение спрашивается У БАЗЫ (имя и метка лежат в `search_tables`), а не собирается
    разбором строки: разбор был бы догадкой и привязкой к языку (п. 9).

    Не свелось — возвращаем None, и вызывающий идёт обычным путём выбора сущности. Это
    лучше отказа: человек назвал что-то, чего мы не узнали, но данные могут быть.
    """
    if not focus:
        return None
    f = str(focus).strip()
    if not f:
        return None
    try:
        rows = psql("SELECT src_table FROM %s WHERE src_table = %s LIMIT 1" % (TABLES, lit(f)))
        if rows and rows[0] and rows[0][0]:
            return rows[0][0]
        # По человеческому названию: регистр и пробелы не считаем — «Классификатор Банков»,
        # «классификатор банков» и «КлассификаторБанков» это одно и то же.
        rows = psql("SELECT src_table FROM %s WHERE lower(replace(label,' ','')) = "
                    "lower(replace(%s,' ','')) LIMIT 2" % (TABLES, lit(f)))
        if len(rows) == 1 and rows[0] and rows[0][0]:
            if diag is not None:
                diag["focus_resolved"] = "%s -> %s" % (f, rows[0][0])
            return rows[0][0]
        if len(rows) > 1:
            # Название неоднозначно — навязывать одно из двух нельзя (п. 12).
            if diag is not None:
                diag["focus_ambiguous"] = f
            return None
        # Подпись с видом записи: «Реализация ТМЦ (документ)». Сравниваем не разбором
        # строки, а СБОРКОЙ эталона у каждого кандидата — так же, как сведение по метке
        # спрашивается у базы. Кандидаты сужаются по началу строки, поэтому перебора
        # всей карты сущностей нет.
        norm = lambda s: "".join(str(s or "").lower().split())
        try:
            rows = psql("SELECT src_table, label FROM %s WHERE %s LIKE "
                        "lower(replace(label,' ','')) || '%%'"
                        % (TABLES, lit(norm(f))))
        except RuntimeError:
            rows = []
        for r in rows or []:
            if r and r[0] and norm(label_with_kind(r[0], r[1] if len(r) > 1 else "")) == norm(f):
                if diag is not None:
                    diag["focus_resolved"] = "%s -> %s" % (f, r[0])
                return r[0]
    except RuntimeError:
        return None                     # база недоступна — пусть решает общий путь
    if diag is not None:
        diag["focus_unknown"] = f
    return None


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
    # 🔴 ПОШАГОВЫЙ СЛЕД: КОГДА, ЧТО СДЕЛАНО И ЧТО ПОЛУЧИЛОСЬ. Требование владельца 03.08:
    # «на каждом шагу логировать можно — время, что делается и что происходит».
    #
    # Заведён не для красоты. `[03.08]` за один день два диагноза пришлось выводить
    # запросами к базе задним числом, и один из них оказался неверным: почему ответ был
    # «88», выяснилось только перебором сущностей с таким числом строк (`HOW_NOT_TO §1.46`).
    # Ответ уже содержал `diag`, но в нём лежали ПОМЕТКИ, а не ход: не видно ни порядка, ни
    # времени, ни того, какой шаг сузил множество.
    #
    # След — часть ответа (`diag.шаги`), а не только журнал: прогонщик и приёмка получают
    # его тем же путём, что числа, и он не теряется при доставке. Ссылка на список лежит в
    # `diag`, поэтому все ветки возврата отдают его накопленным, без правки каждой из них.
    шаги = []

    def шаг(что, **чем):
        шаги.append(dict(шаг=что, мс=int((time.time() - t0) * 1000), **чем))
        if TRACE:
            sys.stderr.write("ask СЛЕД %6d мс  %-18s %s\n" % (
                шаги[-1]["мс"], что,
                " ".join("%s=%s" % (k, v) for k, v in чем.items())))

    intent = parse_intent(question, time.strftime("%Y-%m-%d"))
    preds = _predicates(intent)
    разбор = intent.get("parse") or {}
    diag = {"terms": intent.get("terms"), "preds": preds, "kind": intent.get("kind"),
            "parse": разбор, "шаги": шаги}
    шаг("разбор вопроса", тип=intent.get("kind"), понятий=len(intent.get("terms") or []),
        величина=(intent.get("measure") or "—"), считать=(intent.get("want") or "—"),
        потеряно=(",".join(разбор.get("lost") or []) or "—"))

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
    # Условие вопроса, снятое на разборе (период не датой, порог не числом, понятие сверх
    # бюджета), расширяет множество ответа против того, о чём спросили. Такая потеря
    # выходит человеку тем же путём, что и остальные (п. 13), а не остаётся в журнале.
    if разбор.get("lost"):
        cut["intent_lost"] = ", ".join(разбор["lost"])
    # Условие, которого в вопросе не было (период, выведенный от сегодняшней даты), —
    # допущение системы. Оно применяется, но человек про него узнаёт: молчаливое
    # допущение неотличимо от того, что он спросил сам (п. 12).
    if разбор.get("assumed"):
        diag["intent_assumed"] = ", ".join(
            "%s=%s" % (a, (intent.get("period") or {}).get(a.split(".")[-1], ""))
            for a in разбор["assumed"])

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
    matched_groups = matched_group_count(kinds)
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
    # 🔴 ЧАСТИЧНО СОВПАВШИЕ — НЕ ПОТЕРЯННЫЕ (04.08). Общий порог `k` ставит та сущность,
    # где слова вопроса встретились гуще всего, и все, кто нашёл на одно понятие меньше,
    # исчезали молча. `[замер 04.08]` на 44 парах приёмки: при выбранном `k` эталон доходит
    # до кандидатов в 5 случаях (11 %), при «хотя бы одно понятие» — в 33 (75 %); порог
    # съедал 28 эталонов из 44. Разбор — `partial_tables`.
    #
    # Отбор прошедших порог НЕ меняется ни на знак: `by` и `match` те же, что были, а
    # частичные идут отдельным списком, без числа совпадений, со своим условием на случай,
    # если выберут именно их. Поэтому вопросы, работавшие вчера, работают ровно так же.
    part_lvl, part_pred = partial_tables(exprs, preds, k)
    шаг("отбор: буквально", сущностей=len(by), строк=sum(by.values()) if by else 0,
        частично=len(part_lvl))
    # 🔴 ТРИ ПОВЕРХНОСТИ ОТБОРА СКЛАДЫВАЮТСЯ, А НЕ ЗАМЕНЯЮТ ДРУГ ДРУГА (03.08).
    #
    # Как было: буквальный отбор служил ШЛЮЗОМ. Нашёл хоть что-нибудь — пусть мусор — и
    # ни смысл, ни синонимы не спрашивались вовсе (`if not by and match and emb_ready`).
    # А слово человека и слово базы не совпадают в принципе: в 1С продажа называется
    # «реализация». [замер 03.08] `ts_phrase('продали')` по всему корпусу — 4 строки в
    # трёх каталогах вариантов отчётов; ослабленный до подстроки `ts_like('%продаж%')`
    # даёт регистр себестоимости на 7 307 совпадений против 272 у верного документа, то
    # есть верное не отсутствует, а ТОНЕТ, и тонет ровно по тому признаку («сколько
    # совпадений»), который мы отдаём модели как различающий.
    #
    # Стало: кандидатов приносят три независимых источника, и ни один не имеет права
    # закрыть остальные —
    #   1. слова строки  — инвертированный индекс (`by`, выше);
    #   2. синонимы сущности — `alias_hits`, знание базы о себе, собранное при установке;
    #   3. смысл названия  — `near_tables`, kNN по меткам сущностей.
    # Добавленные приходят БЕЗ числа совпадений (`counts_for_model` остаётся буквальным):
    # выдумывать им счёт нельзя, а «0 совпадений» модель прочла бы как «здесь пусто».
    #
    # 🔴 ПОЧЕМУ КОРПУС ОСТАЁТСЯ ЗАПАСНЫМ ПУТЁМ, А НЕ ЧЕТВЁРТЫМ СЛАГАЕМЫМ. Цена замерена
    # `[замер 03.08]`: kNN по меткам — 52 мс на 1 502 строки, по алиасам — 53 мс, а по
    # КОРПУСУ — 4 642 мс на 623 565 строк, потому что векторного индекса нет ни одного
    # (`duckdb_indexes()` → только `search_idx` и `alias_idx`; `ivf` заблокирован,
    # `VECTOR_DECISION.md`) и запрос идёт полным сканом. Класть 4,6 с в КАЖДЫЙ вопрос
    # нельзя: это и время ответа, и единственное место, где цена вопроса растёт с
    # размером базы (п. 6 `TARGET_STATUS`). Как только векторный индекс появится —
    # сложить и его, разбор сложения тот же.
    #
    # 🔴 ВХОД ПОВЕРХНОСТЕЙ — РОД ЗАПИСЕЙ, А НЕ ТОЛЬКО ЗНАЧЕНИЯ (04.08, замер ниже).
    # Шаг 1 раскладывает вопрос на две разные вещи: `terms` — ЗНАЧЕНИЯ, которые обязаны
    # стоять в записи (имя контрагента, товар), и `kind` — РОД записей, «о чём вопрос».
    # Род в `terms` не кладётся намеренно (иначе отбор ищет слово «продажа» по всем
    # строкам). А словарь синонимов описывает ровно род: «как человек назвал бы такие
    # записи». То есть поверхность синонимов кормили тем, о чём она не знает.
    # `[замер 04.08]` на настоящих разборах шага 1 `terms` пусты у **47 вопросов из 58**,
    # и `alias_hits` на пустых выражениях выходит первой же строкой: верную сущность эта
    # поверхность доносила в **2 случаях из 44 (5 %)**, а на входе `kind`+`terms` —
    # в 21 (48 %). Смысловая поверхность спрашивалась «род ИЛИ вопрос», то есть у 57
    # вопросов из 58 — коротким родом вместо самого вопроса: 20 (45 %) против 29 (66 %)
    # по вопросу. Теперь обе спрашиваются обоими входами, и ни один не закрывает другой.
    # Прибор — `work/acceptance/step3_bench.py` (детерминирован, модель ответов не зовёт,
    # разбор вопроса берётся из прогона прибора шага 1, а не сочиняется приближением).
    kind_text = (intent.get("kind") or "").strip()
    # Понятия вопроса целиком (значения плюс род) — считаются ОДИН раз на вопрос: их просят
    # и отбор смыслом, и подтверждение выбора по словарю синонимов.
    exprs_all = question_exprs(exprs, kind_text)
    # Полный итог шага 3 — в порядке слияния мест, БЕЗ вычитания буквально найденных:
    # ниже он служит головой итогового порядка, а буквальный отбор при пустых понятиях
    # отдаёт ВСЕ сущности, и вычитание оставило бы голову пустой (`[замер 04.08]` живой
    # ответ: «шаг 3 добавил 0» при 1 502 буквальных кандидатах).
    found_by_meaning = meaning_candidates(exprs, kind_text, question, MEANING_TOP)
    extra = [t for t in found_by_meaning if t not in by]
    if extra:
        diag["by_meaning"] = extra
    шаг("отбор: смысл и синонимы", добавлено=len(extra))
    # 🔴 ЧАСТИЧНО СОВПАВШИЕ ВСТАЮТ В САМЫЙ ХВОСТ, И ЭТО НЕ СКРОМНОСТЬ, А ГРАНИЦА ШАГОВ.
    # Их много (медиана около двухсот против восьми у смысловых), а у шага выбора перечень
    # ограничен бюджетом знаков. Поставить эту пачку впереди значило бы вытеснить из бюджета
    # кандидатов шага 3 — а там `[замер 04.08]` эталон доходит до модели 44 из 44, то есть
    # чужая, уже доказанная работа была бы испорчена молча и в чужом шаге.
    # Задача шага 2 здесь другая и она выполнена: сущность, найденную по словам вопроса,
    # больше не выбрасывают — она есть в кандидатах и её видно (`by_partial`).
    # Порядок внутри — по уровню, затем по имени: разделитель равенства обязателен, иначе
    # набор колеблется между одинаковыми вопросами (`techContext` ловушка 30).
    if part_lvl:
        part_order = sorted(part_lvl, key=lambda t: (-part_lvl[t], t))
        # 🔴 В КАНДИДАТЫ — НЕ БОЛЬШЕ БЮДЖЕТА (04.08, сессия шага 3). Сам список частичных
        # растёт с числом сущностей базы (медиана около двухсот по замечанию выше), и без
        # отсечки он уходил бы целиком в `cands`, оттуда в текст запроса `IN (…)` и в
        # перечень для модели — то есть цена вопроса росла бы с размером базы, чего
        # проект не допускает нигде (п. 9, `SCALE_BLOCKERS`). Отсечка та же, что у
        # остальных поверхностей (`MEANING_TOP`), и порядок тот же — по уровню.
        # `[замер 04.08]` на 44 парах приёмки с настоящими разборами шага 1 отсечка не
        # меняет ничего: частичных там 0 на каждом вопросе (эталон ими не приносится ни
        # разу), то есть это защита от роста, а не потеря сигнала.
        fit = [t for t in part_order if t not in by and t not in extra]
        taken = fit[:MEANING_TOP]
        extra = extra + taken
        # След тоже ограничен, и по той же причине: полный список растёт с числом
        # сущностей базы, а ответ сервиса — не место для того, что растёт. Показываются
        # дошедшие; сколько их было всего, видно в `partial` ответа — тем же полем, каким
        # система показывает всё недоехавшее, чтобы отсечка не стала молчаливой (п. 13).
        diag["by_partial"] = {t: part_lvl[t] for t in taken}
        if len(fit) > len(taken):
            sb = diag.setdefault("selection_budget", {})
            sb["partial_shown"] = len(taken)
            sb["partial_total"] = len(fit)
    # Табличные части попадают в кандидаты вместе со своей шапкой: искать их по словам
    # вопроса бесполезно — имени контрагента в строках товаров нет.
    # ⚠ ГРАНИЦА, ОСТАВЛЕННАЯ СОЗНАТЕЛЬНО: строки берутся у шапок, найденных СЛОВАМИ.
    # Отбор потомка по устройству опирается на буквальное совпадение владельца
    # (`kid_pred` — «владелец строки среди совпавших»), поэтому у сущности, пришедшей
    # только от смысла или синонима, табличных частей не будет. Расширять это тем же
    # заходом нельзя: у меры «сколько штук» и без того отдельный дефект выбора величины,
    # и смешивать две правки — значит не суметь сказать, которая подействовала.
    kids, kid_pred = children_by_parent(by, match, preds)
    if kids:
        by.update(kids)
        diag["children"] = kids
    # Ищем по смыслу, только если векторы корпуса посчитаны ТОЙ ЖЕ моделью (`emb_ready`).
    if not by and match and emb_ready(CORPUS):
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
        # `emb IS NOT NULL` — см. разбор в `resolve_near`: без него запрос при пустых
        # векторах отдаёт первые по алфавиту, выдавая их за ближайшие по смыслу.
        near = psql("SELECT src_table, count(*) FROM (SELECT src_table FROM %s "
                    "WHERE emb IS NOT NULL "
                    "ORDER BY emb <=> %s, src_table, row_key LIMIT %d) GROUP BY 1"
                    % (CORPUS, vec, TOPK))
        by = {r[0]: int(r[1]) for r in near if r and r[0]}
        match = ""
        diag["by_vector"] = True
    if not by and not extra:
        by = tables_of("", preds)
    if not by and not extra:
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
    # ...и рядом с ними — пришедшие от синонимов и от смысла названия. Они идут ПОСЛЕ
    # буквально найденных и БЕЗ числа совпадений: буквальное совпадение — сигнал сильнее,
    # а выдуманный счёт был бы враньём в том самом поле, которым модель различает
    # кандидатов. Порядок ниже всё равно пересобирается по смыслу и реранкером.
    cands = list(by) + [t for t in extra if t not in by]
    шаг("кандидаты собраны", всего=len(cands))
    # 🔴 «НА ЧТО НЕ ОТВЕЧАЕТ» — ВТОРАЯ ПОЛОВИНА ЗНАНИЯ УСТАНОВКИ, И ОНА НАКОНЕЦ ЧИТАЕТСЯ.
    # Установочный агент пишет про каждую сущность две половины: «на что отвечает»
    # (`best_used_for`, она уезжает в карточку) и «на что НЕ отвечает» (`not_enough_for`).
    # До 06.08 вторая половина не читалась ни одной строкой сервиса — а это ровно то
    # знание, которое различает соседей, названных одним словом: у «Отчёта о розничных
    # продажах» там дословно «оптовые продажи — не в этом списке», и на вопрос «продажи»
    # он не годится, тогда как «Реализация Товаров Услуг» такого не пишет. Разбор и
    # вся линейка из восьми отвергнутых форм — `work/entity-choice/not_for_probe.py`:
    # выбранная форма (весь род вопроса ⊆ одна запись без указателя на соседа) отсекает
    # 6 из 9 подмен при НУЛЕ отсечённых эталонов; чистое пересечение основ убивало до
    # 26 эталонов из 44.
    # Форма — отсев ДО модели: кандидат не годится, и модель его не видит. Правило
    # не выбирает за неё никого, поэтому ошибка в собранном моделью знании стоит
    # лишнего уточнения (проверки ниже работают как прежде), а не неверного ответа.
    # Отсев НИКОГДА не опустошает круг: если записи отсекают ВСЕХ кандидатов, знанию
    # не верим и работаем с полным кругом — данные могут быть неверны, а ответить
    # по полному кругу система умеет.
    not_for = set()
    if NOT_FOR and kind_text and not focus and len(cands) > 1:
        try:
            kr = psql("SELECT ts_lexize(%s, %s)" % (lit(STEM_DICT), lit(kind_text)))
            k_stems = {s for s in _stem_set(kr[0][0] if kr else "") if len(s) >= 3}
        except RuntimeError:
            k_stems = set()
        нф = []
        if k_stems:
            try:
                # Базы без словаря синонимов (таблица пуста или её нет — первая база)
                # проходят молча: записей нет — отсекать нечем, поведение прежнее.
                нф = psql(
                    "SELECT a.src_table, trim(split_part(u.item, '—', 1)), "
                    "       trim(split_part(u.item, '—', 2)) "
                    "FROM search_entity_alias a, "
                    "     unnest(str_split(a.not_enough_for, ',')) AS u(item) "
                    "WHERE a.not_enough_for IS NOT NULL AND trim(u.item) <> '' "
                    "  AND a.src_table IN (%s)"
                    % ", ".join(lit(c) for c in cands))
            except RuntimeError:
                нф = []
        if нф:
            # Основы обеих частей каждой записи — ОДНИМ запросом, как у
            # `same_concept_groups`: словоформы сводит словарь движка, а не моё
            # сравнение строк. Служебные слова («в», «и», «не») отпадают длиной —
            # это факт языка, а не список слов.
            тексты = sorted({(r[1] or "") for r in нф} | {(r[2] or "") for r in нф})
            стемы = {}
            if тексты:
                sel = ", ".join("ts_lexize(%s, %s)" % (lit(STEM_DICT), lit(x))
                                for x in тексты)
                try:
                    row = psql("SELECT " + sel)[0]
                    стемы = {x: {s for s in _stem_set(row[i]) if len(s) >= 3}
                             for i, x in enumerate(тексты)}
                except (RuntimeError, IndexError):
                    стемы = {}
            # Указатель («аспект — Другая Сущность») проверяется СТРУКТУРНО:
            # правая часть называет существоующую сущность базы. Проверять её
            # против ВСЕХ названий нужно только для записей, прошедших подмножество,
            # а их на вопрос единицы — поэтому запрос на запись, а не на таблицу.
            указ = {}
            for rt in sorted({(r[2] or "") for r in нф
                              if k_stems <= стемы.get(r[1] or "", set())}):
                if not rt:
                    указ[rt] = False
                    continue
                try:
                    n = psql(
                        "SELECT count(*) FROM %s WHERE "
                        "  len(list_filter(ts_lexize(%s, label), x -> length(x) >= 3))"
                        "  > 0 AND list_has_all("
                        "    list_filter(ts_lexize(%s, %s), x -> length(x) >= 3),"
                        "    list_filter(ts_lexize(%s, label), x -> length(x) >= 3))"
                        % (TABLES, lit(STEM_DICT), lit(STEM_DICT), lit(rt),
                           lit(STEM_DICT)))
                    указ[rt] = bool(n and int(n[0][0] or 0))
                except RuntimeError:
                    # Сбой чтения — запись считается указателем, и отсев молчит:
                    # это направление ошибки стоит уточнение, а не выбор без соседа.
                    указ[rt] = True
            по_кандидатам = {}
            for r in нф:
                по_кандидатам.setdefault(r[0], []).append(
                    (стемы.get(r[1] or "", set()), указ.get(r[2] or "", True)))
            not_for = {t for t, its in по_кандидатам.items()
                       if not_for_excludes(k_stems, its)}
            if len(not_for) >= len(cands):
                # Знание отсекло бы ВЕСЬ круг — ему нельзя верить настолько.
                diag["not_for_all"] = len(not_for)
                not_for = set()
            elif not_for:
                cands = [c for c in cands if c not in not_for]
                diag["not_for"] = sorted(not_for)
                шаг("отсев «не отвечает»", отсеяно=len(not_for))
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
    order_by_question = []
    # 🔴 ПОРЯДОК СТРОИТСЯ ПО ТОЙ ЖЕ ПОВЕРХНОСТИ, ЧТО И ОТБОР — ПО КАРТОЧКЕ (04.08).
    # Здесь решается, что вообще ДОЙДЁТ до модели: набор кандидатов пересортировывается
    # целиком, и всё, что не попало в голову, обрезается бюджетом перечня. До 04.08
    # порядок строился по вектору МЕТКИ, тогда как отбор кандидатов уже с 03.08 идёт по
    # карточке, — то есть найденное одной поверхностью раскладывалось другой, заведомо
    # более слабой (`[замер 03.08]` до реранкера доходит 70 % против 52 %).
    # `[замер 04.08]`, 44 пары приёмки, настоящие разборы шага 1: эталон доходит до
    # модели (первые ~108 записей бюджета) — по метке **42 из 44**, по карточке
    # **44 из 44**; до реранкера (первые 60) — 34 против 42. Прибор — `step3_bench.py`,
    # раздел «доставка до шага 4».
    # Откат честный: нет карточки или её векторы посчитаны другой моделью — работаем по
    # метке, как раньше (`emb_ready` без отметки говорит «нет»).
    order_src = CARD if emb_ready(CARD) else (TABLES if emb_ready(TABLES) else "")
    # 🔴 ЭМБЕДДЕР УПАЛ — ЭТО СБОЙ, А НЕ «РАБОТАЕМ БЕЗ СМЫСЛА» (05.08).
    # Когда смысловой путь выключается, порядок кандидатов остаётся по ЧИСЛУ СОВПАДЕНИЙ, а
    # этот признак пропорционален размеру сущности, а не относимости. Ответ при этом уходил
    # человеку с прежней уверенностью. Поймано пробой: под тройной нагрузкой (опыт «круг
    # арбитра всегда») эмбеддер ответил `TimeoutError`, и начиная с девятого вопроса выбор
    # выродился в служебный `informationregister_замерывремени` — ЧЕТЫРЕ неверных ответа
    # подряд, все быстрые и все уверенные (`runs/2026-08-05-step4-J-alwaysarb.txt`).
    # П. 18 `TARGET.md` требует честного поведения при сбое, а не тихой деградации.
    #
    # Различать «упал» и «векторов нет по устройству» обязательно: на базе без собранных
    # векторов `emb_ready` тоже ложна, но это НЕ сбой, и превращать там каждый вопрос в
    # уточнение нельзя. Различает `embed_model_live()` — он спрашивает сам сервис.
    meaning_down = bool(ORDER_BY_MEANING and len(cands) > 1 and not order_src
                        and not embed_model_live())
    if meaning_down:
        diag["meaning_down"] = "эмбеддер не ответил — порядок кандидатов без смысла"
    if ORDER_BY_MEANING and len(cands) > 1 and order_src:
        orders = []
        for src_text in (question, intent.get("kind")):
            if not src_text:
                continue
            try:
                orders.append([r[0] for r in psql(
                    "SELECT src_table FROM %s WHERE src_table IN (%s) "
                    "AND emb IS NOT NULL "        # см. разбор в `resolve_near`
                    # разделитель равенства: ниже порядок режется по RERANK_TOP,
                    # и без него до реранкера доходят разные сущности
                    "ORDER BY emb <=> %s, src_table"
                    % (order_src, ", ".join(lit(c) for c in cands), _vec(src_text)))])
            except RuntimeError:
                pass
        if orders:
            # Вершина по САМОМУ ВОПРОСУ — независимый от модели сигнал. Ниже он служит
            # признаком неоднозначности: если он расходится с выбором модели, вопрос
            # честно допускает несколько прочтений, и по п. 12 мы обязаны спросить.
            # Весь порядок по вопросу, а не только его вершина: если вершиной оказалась
            # СЛУЖЕБНАЯ сущность, сигнал не выбрасывается, а берётся первый деловой —
            # разбор у `signals_disagree` ниже.
            order_by_question = list(orders[0])
            top_by_question = order_by_question[0] if order_by_question else None
            # Вперемежку: первый по вопросу, первый по слову, второй по вопросу, ...
            order, seen = [], set()
            for i in range(max(len(o) for o in orders)):
                for o in orders:
                    if i < len(o) and o[i] not in seen:
                        seen.add(o[i]); order.append(o[i])
            cands = order + [c for c in cands if c not in seen]
            diag["sieve"] = len(orders)
        else:
            # Эмбеддер молчит — порядок остаётся по числу совпадений, но круг кандидатов
            # не сужается: пришедшие от синонимов сохраняются, они добыты без вектора.
            cands = sorted(by, key=lambda t: -by[t]) + [t for t in extra if t not in by]
            # Отсев «не отвечает» держится и здесь: круг пересобран из `by`/`extra`,
            # и без вычитания отсеянный сосед вернулся бы в обход правила.
            if not_for and len(cands) > len(not_for):
                cands = [c for c in cands if c not in not_for]
            # 🔴 И ЭТО ТОЖЕ ОТКАЗ СМЫСЛОВОГО ПУТИ, А НЕ «ПОРЯДОК ПО СОВПАДЕНИЯМ» (05.08).
            # Здесь `/health` эмбеддера отвечает (иначе мы бы сюда не зашли), но САМ вызов
            # эмбеддинга упал или не уложился в таймаут, `orders` пуст, и порядок кандидатов
            # задаётся числом совпадений — признаком, пропорциональным РАЗМЕРУ сущности.
            # Прежде это проходило молча, и ответ уходил с обычной уверенностью.
            # `[замер 05.08]` пять вопросов подряд («контрагенты», «организации»,
            # «документы реализации», «строки товаров», «документы приобретения») ответили
            # служебным `informationregister_замерывремени` — быстро, уверенно и неверно.
            # Проверка по `/health` этот случай НЕ ловит: она была, и она сказала «жив».
            diag["meaning_down"] = "вектор вопроса не посчитан — порядок кандидатов без смысла"
        # 🔴 НАЙДЕННОЕ ШАГОМ 3 СТОИТ ВПЕРЕДИ (04.08). Выше набор пересортирован ОДНИМ
        # сигналом — близостью вектора, — и найденное четырьмя поверхностями сразу теряет
        # своё место. А режется список бюджетом перечня: `[замер 04.08]` живой ответ отдал
        # модели 100 записей из 1502, и верная сущность стояла 106-й — то есть ошибка
        # ответа была ошибкой ДОСТАВКИ, а не выбора. Порядок внутри головы — тот, в
        # котором его отдало слияние мест; всё остальное идёт следом, как и раньше.
        # `[замер 04.08]` на 44 парах приёмки при глубине перечня как в бою: эталон
        # доходит до модели 44 из 44 против 43, до реранкера 43 против 42, и верным
        # оказывается верхний кандидат 16 раз против 10.
        # Сигнал `top_by_question` НЕ ТРОГАЕТСЯ: он выше и остаётся вершиной чистого
        # вектора — на нём стоит признак неоднозначности шага 4, и менять его смысл
        # отсюда нельзя.
        if found_by_meaning:
            in_cands = set(cands)
            head3 = [t for t in found_by_meaning if t in in_cands]
            if head3:
                seen3 = set(head3)
                cands = head3 + [c for c in cands if c not in seen3]
                diag["order_head"] = len(head3)
        head, tail = cands[:RERANK_TOP], cands[RERANK_TOP:]
        if tail:
            sb = diag.setdefault("selection_budget", {})
            sb["reranked_of"] = len(cands)
            sb["reranked"] = len(head)
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
    if not cands and emb_ready(TABLES):
        try:
            # LIMIT в БАЗЕ: иначе в кандидаты, а следом в промпт, уезжает вся база.
            # Число получаем из бюджета промпта, а не задаём отдельно.
            cands = [r[0] for r in psql(
                "SELECT src_table FROM %s WHERE emb IS NOT NULL "   # см. `resolve_near`
                "ORDER BY emb <=> %s, src_table LIMIT %d"
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
        focus = resolve_focus(focus, diag)
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
                                              counts_for_model, match, diag)
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
                     if t not in by and t not in picked and t not in not_for]
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
    # Сомнение считается ниже, но объявляется здесь: его читает `_alias_verdict`, а тот
    # определён раньше по тексту. Так порядок определений не решает поведение молча.
    doubt = False
    par = {}
    writer = {}
    служебные = set()
    if picked:
        need = set(picked) | set(cands[:ARBITER_MAX * 4]) | set(order_by_question[:8])
        if top_by_question:
            need.add(top_by_question)
        # 🔴 СЛУЖЕБНАЯ СУЩНОСТЬ — НЕ ВТОРОЕ ПРОЧТЕНИЕ ДЕЛОВОГО ВОПРОСА (05.08).
        # Разметку делает такт (`classify_entities.py`, модель отвечает «о чём спрашивают»
        # или «служебное»), она лежит в базе на ВСЕ 1502 сущности и не зависит ни от языка,
        # ни от имён: списка слов и разбора имени («constant_…») здесь нет намеренно —
        # это была бы привязка к нашей конфигурации. Неразмеченное считается деловым, как и
        # в самой разметке, поэтому на базе без неё поведение прежнее.
        # Зачем: `[замер 05.08]` вопрос «Сколько у нас партнёров?» отвечался ВЕРНО (164),
        # но в круг арбитра попадали две константы настроек с ответом «1», числа честно
        # расходились (164 против 1 против 1), и детектор превращал верный ответ в
        # уточнение. Это и есть шум в круге соперников, а не два прочтения.
        try:
            служебные = {r[0] for r in psql(
                "SELECT src_table FROM %s WHERE cls = 'service' AND src_table IN (%s)"
                % (CLASS_TABLE, ", ".join(lit(c) for c in need))) if r and r[0]}
        except RuntimeError:
            служебные = set()          # базы без разметки — соперников не отсеиваем
        try:
            # `written_by` — «какой документ пишет этот источник», заведено подготовкой базы
            # 05.08 (`corpus_build.sql`, раздел 2-тер). Это ЕДИНСТВЕННЫЙ сигнал шага 4,
            # который не является названием: метка, вектор метки и карточки, реранкер и
            # словарь синонимов — все про имя, а регистр накопления в 1С назван деловым
            # языком («Закупки»), документ — канцелярским («Приобретение Товаров Услуг»), и
            # человек спрашивает деловым. Поэтому именные сигналы дружно подтверждали
            # регистр, а показ модели вида записи `[замер 04.08]` сделал хуже (3 → 6).
            par, writer = {}, {}
            for r in psql(
                "SELECT src_table, parent, written_by FROM %s WHERE src_table IN (%s)"
                    % (TABLES, ", ".join(lit(c) for c in need))):
                if not r or not r[0]:
                    continue
                par[r[0]] = (r[1] or "")
                if len(r) > 2 and r[2]:
                    writer[r[0]] = r[2]
        except RuntimeError:
            # Старая база без колонки — работаем как до 05.08, а не падаем.
            par, writer = {}, {}
            try:
                par = {r[0]: (r[1] or "") for r in psql(
                    "SELECT src_table, parent FROM %s WHERE src_table IN (%s)"
                    % (TABLES, ", ".join(lit(c) for c in need))) if r and r[0]}
            except RuntimeError:
                par = {}

    def _family(t):
        return par.get(t) or t

    def _alias_verdict(cand):
        """Подтверждает ли собственное знание базы, что отвечать надо ЭТОЙ сущностью.

        🔴 ПРОВЕРКА ОБЯЗАНА СТОЯТЬ НА ИТОГОВОМ ВЫБОРЕ, А НЕ НА ПРОМЕЖУТОЧНОМ. [замер 30.07]
        прежде она стояла ниже арбитра, а обе ветки арбитра возвращают ответ раньше — то
        есть на всяком пути, где ответ вообще собрался, проверка не выполнялась. Вместе с
        отсутствующим правом `SELECT` (см. `corpus_init.sql`) это давало защиту, не
        работавшую НИ РАЗУ.

        Опора относительная: подтверждена та сущность, чьи алиасы совпали с вопросом
        ЛУЧШЕ ВСЕХ, а не всякая, у которой нашлось общее слово. Разбор чисел — у места
        вызова. Поиск ведёт база (п. 19): алиасы — такая же поисковая поверхность, как
        названия, и до этой правки они никого не приводили, только проверяли.

        Возвращает (supported, alias_top). `supported=True` при отсутствии знания — это
        не одобрение, а признание, что проверять нечем.
        """
        try:
            # 🔴 СОБСТВЕННОЕ НАЗВАНИЕ СУЩНОСТИ — ТОЖЕ ЕЁ СЛОВО, И БРАТЬ ЕГО НАДО ИЗ ДАННЫХ.
            # [замер 30.07] после перегенерации алиасов модель описала справочник
            # номенклатуры по смыслу — «товар, услуга, работа, артикул, вес товара» — и
            # выкинула слово «номенклатура». Подтверждения не нашлось, и ВЕРНЫЙ ответ
            # «227 позиций» превратился в уточнение. Спрашивать модель о том, как
            # называется сущность, незачем: название лежит в `search_tables.label`.
            # Это устраняет целый класс провалов по построению: что бы модель ни забыла
            # написать, своё имя сущность не теряет.
            r = psql(
                "WITH w AS ("
                "  SELECT trim(u.w) AS t FROM search_entity_alias a, "
                "         unnest(str_split(a.aliases, ',')) AS u(w) WHERE a.src_table = %s"
                "  UNION ALL SELECT label FROM %s WHERE src_table = %s) "
                "SELECT count(*) FILTER (t <> ''), "
                "       count(*) FILTER (t <> '' "
                "         AND list_has_any(ts_lexize(%s, t), ts_lexize(%s, %s))) FROM w"
                % (lit(cand), TABLES, lit(cand),
                   lit(STEM_DICT), lit(STEM_DICT), lit(question)))
            known, hit = (int(r[0][0] or 0), int(r[0][1] or 0)) if r and r[0] else (0, 0)
        except RuntimeError as e:
            diag["alias_unreadable"] = str(e)[:120]
            return True, []
        if not known:
            # Про ЭТУ сущность знания нет — требовать подтверждения нечем. Так выглядит
            # база, где вики не собрана: [замер] в первой базе алиасов 0.
            diag["alias_no_evidence"] = True
            return True, []
        if hit and not ALIAS_VETO:
            return True, []
        # Соперников подбираем ПО ВОПРОСУ, штатным ранжированием движка
        # (`tfidf` учитывает редкость слова: «сколько» весит мало, «поставщикам» много).
        # Свой счёт совпадений здесь стоял и был отвергнут замером — он считал ВСЕ общие
        # слова, поэтому «сколько записей в справочнике» совпадало с чем угодно.
        # 🔴 РАЗДЕЛИТЕЛЬ РАВЕНСТВА — см. врезку у `_fetch`: без него `ORDER BY … LIMIT`
        # оставляет порядок равных на волю исполнения. Здесь это дороже, чем там: `top[0]`
        # решает вето, `top[:2]` становятся вариантами уточнения, то есть ничья решает
        # ВЫБОР СУЩНОСТИ. [замер 03.08] на боевом скорере (`tfidf`, `ut_test`) ничьих в
        # первой восьмёрке 3-5 на каждом из семи вопросов приёмки, и у шести из семи на
        # ничью попадает САМ СРЕЗ `LIMIT 8` — то есть произволен и состав восьмёрки.
        # Разделитель — `src_table`: ключ `alias_idx` уникален (697 строк, 697 значений),
        # значит порядок становится полным. Это штатное предписание движка, а не наш приём:
        # доки, Indexes › Inverted › Ranking › Tie-breaking — «Add further ORDER BY columns
        # after the scorer for a deterministic order — typically the primary key».
        # 🔴 ЛИДЕР ИЩЕТСЯ ПО ТЕКСТУ ВОПРОСА, И ЭТО ИЗВЕСТНАЯ СЛАБОСТЬ, А НЕ ЗАМЫСЕЛ.
        # Скорер считает совпадение по всем словам вопроса, включая «сколько», «у», «нас»:
        # `[замер 05.08]` лидером ТРЁХ разных вопросов («сколько у нас партнёров»,
        # «…организаций», «…складов») стал один и тот же регистр «Принятая Возвратная Тара» с
        # одинаковой оценкой 12,49 — в его словаре есть фраза «сколько тары у нас». Верные
        # ответы (164 партнёра, 5 организаций, 17 складов) вето отвергло именно так.
        # Форма «искать по ПОНЯТИЯМ вопроса» (та же поверхность, которой идёт отбор —
        # `alias_hits`) проверена и НЕ помогает: по понятию «партнёров» верный
        # `catalog_партнеры` не входит в восьмёрку вовсе, по «организаций» стоит седьмым.
        # Значит чинить надо словарь синонимов, а не запрос к нему (`ASK_ALIAS_BY_CONCEPTS`
        # оставлен, чтобы обе формы мерились одной командой; разбор — `HOW_NOT_TO §1.57`).
        try:
            if ALIAS_BY_CONCEPTS:
                top = [(t, 0.0) for t in alias_hits(exprs_all, ALIAS_TOP)]
            else:
                top = [(r[0], float(r[1])) for r in psql(
                    "SELECT src_table, %s FROM %s WHERE aliases @@ %s"
                    " ORDER BY 2 DESC, src_table LIMIT %d"
                    % (SCORERS.get(SCORER, SCORERS["bm25"]) % ALIAS_INDEX, ALIAS_INDEX,
                       lit(question), ALIAS_TOP)) if r and r[0]]
        except RuntimeError:
            top = []
        # 🔴 ОТСЕЯННЫЙ «НЕ ОТВЕЧАЕТ» НЕ МОЖЕТ БЫТЬ ЛИДЕРОМ СЛОВАРЯ (06.08, вечер).
        # Вето сравнивает выбор с лидером ранжирования, а лидера ВНЕ круга кандидатов
        # считает «словарь один против всех» и пропускает выбор. Отсев убирает сущность
        # из круга — и [замер 06.08] на вопросе «Кто нам поставляет товар?» это разоружило
        # проверку целиком: лидер «Заказы Поставщикам» был отсеян по делу (сам пишет, что
        # поставщиков не ведёт), его место в круге стало -1, вето молча пропустило, и
        # неверный ответ ушёл уверенным. Сущность, отсеянная как непригодная ОТВЕЧАТЬ,
        # непригодна и ЭТАЛОНОМ сравнения — лидер ищется среди оставшихся.
        if not_for:
            skipped = [t for t, _s in top if t in not_for]
            if skipped:
                diag["alias_top_not_for"] = skipped
                top = veto_top_without(top, not_for)
        miss = [t for t, _ in top if t not in par]
        if miss:
            try:
                par.update({r[0]: (r[1] or "") for r in psql(
                    "SELECT src_table, parent FROM %s WHERE src_table IN (%s)"
                    % (TABLES, ", ".join(lit(t) for t in miss))) if r and r[0]})
            except RuntimeError:
                pass
        diag["alias_top"] = [t for t, _ in top[:4]]

        # Места в ОБЩЕМ порядке кандидатов (шаг 3: буквальный отбор, смысл, карточка,
        # реранкер). Именно их сравнивает вето: место выбора против места лидера словаря.
        # Семьями, а не сущностями — шапка и её табличная часть это одно прочтение.
        _по_семьям = [_family(c) for c in cands]

        def _место(t):
            try:
                return _по_семьям.index(_family(t))
            except ValueError:
                return -1

        def _probe(ok, why):
            """След для замера: из чего СЧИТАЕТСЯ каждая форма правила. Решений не принимает."""
            if PROBE:
                diag.setdefault("alias_probe", []).append({
                    "cand": cand, "known": known, "hit": hit, "ok": bool(ok), "why": why,
                    "top": [[t, round(s, 3)] for t, s in top[:4]],
                    "leader": top[0][0] if top else "",
                    "место_выбора": _место(cand),
                    "место_лидера": _место(top[0][0]) if top else -1,
                    "cand_rank": next((i for i, (t, _s) in enumerate(top)
                                       if _family(t) == _family(cand)), -1)})
            return ok
        # 🔴 ЖЁСТКАЯ ФОРМА — ПОД ВЫКЛЮЧАТЕЛЕМ, И ЭТО НЕ ОСТОРОЖНОСТЬ, А ЗАМЕР.
        # Решение владельца 30.07: когда вопросу отвечает несколько РАЗНЫХ объектов —
        # всегда переспрашивать. Но [замер 30.07] на прежних алиасах жёсткая форма дала
        # 1 улучшение против 3 ухудшений: верный ответ «227 позиций» превращался в
        # уточнение, потому что данные были слабее механизма — на «сколько у нас
        # партнёров» лучшим совпадением шла «Принятая Возвратная Тара».
        # Включать только после замера, что база подсказывает верно.
        # Семьи схлопываются: шапка и её табличная часть — одно прочтение, а не два.
        # Числа тут НЕТ намеренно. Первая версия писала «среди трёх лучших семей», и это
        # подгонка: тройка взялась из нашей базы, а на чужой ничего не значит. Ревизор
        # поймал её до коммита. Согласие определяется без порога: подтверждает ЛИДЕР
        # ранжирования, и решает его база, а не константа в коде. Совпали семьи —
        # отвечаем; разошлись — объектов несколько, и человек выбирает сам.
        # Сама форма правила — в `alias_supported` (там же её таблица истинности, разбор
        # смягчения и числа, которыми оно отвергнуто). Здесь остаётся только то, что без
        # базы не делается: спросить знание и подобрать соперников для уточнения.
        # `сомнение` считается раньше по тексту (модель назвала несколько, сигналы
        # разошлись, нашлась пара «регистр ← документ», отказал смысловой путь). Здесь оно
        # решает, доступна ли вторая попытка: там, где спор ЕСТЬ, спрашивает п. 12.
        ok = alias_supported(known, hit, _family(cand),
                             _family(top[0][0]) if top else "",
                             rank_cand=_место(cand),
                             rank_leader=_место(top[0][0]) if top else -1,
                             undisputed=not doubt)
        return _probe(ok, "лидер" if top else "своё слово"), top

    def _alias_clarify(cand, top):
        """Список для человека: лучшие по вопросу, по одному представителю от семьи."""
        seen, rivals = {_family(cand)}, []
        for t, _n in top:
            if t == cand or _family(t) in seen:
                continue
            seen.add(_family(t)); rivals.append(t)
        opts_src = [cand] + rivals[:2]
        try:
            lab_by = {r[0]: r[1] for r in psql(
                "SELECT src_table, label FROM %s WHERE src_table IN (%s)"
                % (TABLES, ", ".join(lit(c) for c in opts_src))) if r and r[0]}
        except RuntimeError:
            return None
        if len(opts_src) < 2 or not lab_by:
            return None
        # `distinct_by` — обязательное поле: `clarify_text` читает его без `get`. Прежняя
        # копия правила его НЕ клала, то есть при первом же выполнении упала бы с
        # `KeyError('distinct_by')`. Это ещё одно доказательство, что она не работала ни
        # разу: путь, который никогда не исполнялся, донёс до продукта и дефект прав, и
        # дефект формы данных.
        opts = mk_opts([t for t in opts_src if t in lab_by], lab_by, marks, by, match=match, preds=preds)
        if len(opts) < 2:
            return None
        diag["unsupported_pick"] = cand
        return {"partial": cut or None, "kind": "clarify",
                "text": clarify_say(question, opts, diag),
                "options": opts, "sources": [o["label"] for o in opts],
                "diag": dict(diag, sec=round(time.time() - t0, 2))}
    # 🔴 ОДНА СЕМЬЯ — НЕ ОДНО ПРОЧТЕНИЕ. Здесь стояло `_family(top) not in {_family(x)…}`:
    # если вершина по вектору оказывалась ШАПКОЙ ИЛИ СОСЕДНЕЙ ТАБЛИЧНОЙ ЧАСТЬЮ того же
    # документа, расхождение сигналов не считалось расхождением вовсе, сомнение не
    # поднималось, арбитр не запускался — и ответ уходил человеку молча.
    #
    # Посылка «шапка и её табличная часть — одно прочтение» опровергнута замером `[03.08]`,
    # сплошной перебор по боевой базе: из 186 пар «семья + одноимённая величина» у двух и
    # более членов **126 (68 %) расходятся числом**. Порознь ещё хуже там, где ошиблись:
    #   шапка ↔ табличная часть  —  38 из 71  (54 %);
    #   табличная ↔ табличная    — 195 из 249 (**78 %**).
    # Вопрос 6 приёмки — ровно второй случай: «Виды Запасов» дали 327 против 92 683 у
    # «Товаров» ТОГО ЖЕ документа, и оба — одна семья.
    #
    # Поднять сомнение безопасно: оно лишь заводит второго кандидата в круг арбитра, а
    # арбитр-детектор (задача 17) спрашивает человека ТОЛЬКО если посчитанные числа
    # разошлись. Совпали — ответ уходит как прежде. То есть цена — счёт, а не лишние
    # уточнения. Замеры 30.07, на которых держится осторожность («партнёры», «организации»),
    # это не задевает: у справочников табличных частей нет, семья состоит из них одних.
    # 🔴 ОГОВОРКА `top_by_question in by` СНЯТА (04.08). Она осталась от той поры, когда
    # кандидаты приходили ТОЛЬКО буквальным отбором. С 03.08 поверхностей три, и пришедшие
    # смыслом или синонимом живут в `extra`, а в `by` не попадают никогда. Значит такого
    # кандидата модель выбрать могла, а ОСПОРИТЬ чужой выбор он не мог: сомнение не
    # поднималось, арбитр-детектор не запускался, человека не спрашивали — и неверный
    # ответ уходил уверенным. Это и есть `сомнение=False` у трёх ошибок прогона 03.08.
    # [замер 04.08] прибором `rival_reach_bench.py` на 44 парах приёмки: буквально эталон
    # находится у 5 (11 %), синонимом у 18 (41 %) — то есть у 39 из 44 (89 %) права
    # оспорить не было вовсе, при том что до перечня эталон доходит в 44 случаях из 44.
    # 🔴 И ЗДЕСЬ ТОЖЕ: СЛУЖЕБНАЯ СУЩНОСТЬ НЕ ОСПАРИВАЕТ ВЫБОР (05.08). Вершина по смыслу
    # вопроса — сигнал сильный, но `[замер 05.08]` в 9 случаях из 27 она указывала на
    # настройку («Использовать несколько складов» на вопрос «сколько у нас складов»):
    # слово в названии есть, прочтения — нет. Такое расхождение поднимало сомнение,
    # заводило настройку в круг арбитра ОТВЕЧАЮЩИМ кандидатом, её «1» расходилось с
    # настоящим числом, и верный ответ уходил уточнением. Правило то же, что у соперников
    # ниже, и держится теми же данными (`search_entity_class`).
    # 🔴 СЛУЖЕБНАЯ ВЕРШИНА ПО СМЫСЛУ ГАСИТ СИГНАЛ, А НЕ ЗАМЕНЯЕТСЯ СЛЕДУЮЩЕЙ (05.08, вечер).
    # Замена на первую ДЕЛОВУЮ запись того же порядка выглядела точнее — сигнал ведь звучит
    # «вершина по смыслу», а служебная сущность прочтением не является. Проверено прогоном и
    # ОТВЕРГНУТО: `[замер 05.08]` первой деловой оказывается очередная настройка, размеченная
    # `business` по ошибке разметки («Использовать партнёров как контрагентов» на вопрос
    # «сколько у нас партнёров», «Организация, на которую зарегистрирована программа» — на
    # «сколько у нас организаций»). Верные ответы №8, 10, 11, 12 из ВЕРНО снова стали
    # уточнением, а ни одной ошибки замена не поймала. Шум заменился шумом.
    if (SIGNAL_DISAGREE and top_by_question and picked and not focus
            and top_by_question not in picked
            and not (SKIP_SERVICE_RIVALS and top_by_question in служебные)):
        picked = list(dict.fromkeys(picked + [top_by_question]))
        diag["signals_disagree"] = top_by_question
        if _family(top_by_question) in {_family(x) for x in picked if x != top_by_question}:
            diag["signals_disagree_same_family"] = True

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
    #   3. 🔴 (05.08) выбран источник, движения которого ПИШЕТ документ, и этот документ —
    #      не тот же источник. Регистр накопления и документ-регистратор это ОДИН факт,
    #      записанный дважды: «Закупки» пишет «Приобретение Товаров Услуг» (доля 0,759),
    #      «Заказы Клиентов» — «Заказ Клиента» (0,723). Ровно на этой паре шаг 4 ошибался
    #      молча: `[замер 05.08]` из трёх оставшихся неверных ответов боевой сборки два —
    #      она, и у обоих в следе «защита не сработала ни одна».
    #
    #      🔴 ПОРОГА ПО ДОЛЕ ЗДЕСЬ НЕТ НАМЕРЕННО. Доля преобладающего регистратора —
    #      число из данных (`[замер 05.08]` у 70 регистров из 81 регистраторов больше
    #      одного, медиана 0,56), и отсечка по ней была бы константой, подобранной под нашу
    #      базу (п. 9). Поэтому связь не решает, а лишь ЗАВОДИТ второе прочтение в круг
    #      арбитра: спрашивает человека арбитр-детектор и только тогда, когда посчитанные
    #      числа разошлись. Сошлись — ответ уходит как прежде, цена правила равна счёту.
    writer_pair = writer.get(picked[0]) if picked else None
    if writer_pair and picked and writer_pair not in picked:
        diag["writer_pair"] = writer_pair
    #   4. 🔴 (05.08) смысловой путь ОТКАЗАЛ (`meaning_down`). Тогда порядок кандидатов
    #      задаётся числом совпадений, то есть размером сущности, и уверенности в выборе у
    #      нас нет никакой — это сомнение по факту сбоя, а не по данным. Круг арбитра при
    #      этом собирается и сравнивает ЧИСЛА, которые считает база: она-то работает.
    doubt = (len(picked) > 1 or bool(diag.get("signals_disagree"))
             or bool(diag.get("writer_pair")) or bool(diag.get("meaning_down")))
    arb_pool = list(picked)
    # Документ-регистратор идёт в круг ПЕРВЫМ соперником: он и есть второе прочтение,
    # а не «следующий по порядку отбора».
    if (diag.get("writer_pair") and picked and not focus and not no_arbiter
            and len(arb_pool) < ARBITER_MAX):
        arb_pool.append(diag["writer_pair"])
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
        order = list(cands) + ([top_by_question] if top_by_question else [])
        for c in order:
            if len(arb_pool) >= ARBITER_MAX:
                break
            # 🔴 `c not in by` СНЯТО 04.08 — по той же причине, что и у признака
            # расхождения выше: соперником мог стать только кандидат буквального отбора,
            # а он приносит эталон в 5 случаях из 44. Кандидат, у которого своих
            # совпадений нет, круг арбитра не засоряет: по нему собирается ПОЛНЫЙ ответ
            # тем же кодом, и пустой в `cand_ans` не попадает.
            if c in arb_pool or _family(c) in fam:
                continue
            if SKIP_SERVICE_RIVALS and c in служебные:
                # Служебная сущность соперником не становится: её число («1» у константы
                # настройки) расходится с ответом всегда, и расхождение это ничего не
                # значит. Выбор модели (`picked`) правило не трогает — отсеиваются только
                # соперники, которых в круг завожу я.
                diag.setdefault("rival_service_skipped", []).append(c)
                continue
            arb_pool.append(c); fam.add(_family(c))
        # 🔴 ВТОРЫМ ЗАХОДОМ — СОСЕДИ ПО СЕМЬЕ, если в круге осталось место. Первый заход
        # оставлен как был: порядок «сперва чужие семьи» решён замером 30.07, и трогать его
        # нельзя. Но выбрасывать соседей совсем — значит не видеть класс ошибки, который
        # `[замер 03.08]` расходится числом в **195 случаях из 249 (78 %)**: две табличные
        # части одного документа. Вопрос 6 приёмки проигран именно так.
        # Соседи добавляются ПОСЛЕ, то есть только в свободное место, и лишними уточнениями
        # это не оборачивается: арбитр-детектор спрашивает, лишь когда числа разошлись.
        for c in order:
            if len(arb_pool) >= ARBITER_MAX:
                break
            if c in arb_pool or (SKIP_SERVICE_RIVALS and c in служебные):
                continue
            arb_pool.append(c)
            diag["arbiter_kin_rival"] = c
        if len(arb_pool) > 1:
            diag["arbiter_rivals"] = arb_pool[1:]
        шаг("круг арбитра", всего=len(arb_pool),
            соперники=",".join(arb_pool[1:]) or "—")

    def _checked(out):
        """Ответ уходит только если собственное знание базы подтверждает выбор сущности.

        Решение владельца 30.07: когда вопросу отвечает несколько РАЗНЫХ объектов —
        всегда переспрашивать, а не выбирать за человека.
        """
        if not REQUIRE_SUPPORT or focus:
            return out
        w = (out.get("diag") or {}).get("focus")
        if not w or out.get("kind") not in ("answer", "figures"):
            return out
        ok, top = _alias_verdict(w)
        if ok:
            return out
        ask = _alias_clarify(w, top)
        return ask or out

    if len(arb_pool) > 1 and not no_arbiter:
        # 🔴 СНАЧАЛА АРБИТР, ПОТОМ ЧЕЛОВЕК. Порядок п. 21: ответ → уточняющий вопрос →
        # отказ. Спрашивать человека, не попытавшись ответить, — значит переложить на него
        # работу, которую система может сделать сама. Поэтому по каждому кандидату
        # СОБИРАЕТСЯ ПОЛНЫЙ ОТВЕТ (тем же кодом, через `focus`, — то есть числа считает
        # база), и арбитр выбирает между готовыми ответами. Не выбрал — спрашиваем человека.
        cand_ans, cand_src = [], []
        mute = {}
        for c in arb_pool[:ARBITER_MAX]:
            try:
                sub = answer(question, focus=c, measure_pick=measure_pick,
                             context=context, no_arbiter=True)
            except Exception:                  # noqa: BLE001 — один кандидат не должен
                continue                       # ронять весь ответ
            if sub.get("kind") in ("answer", "figures") and (sub.get("text") or "").strip():
                cand_ans.append(sub["text"].split("⚠")[0].strip())
                cand_src.append(sub)
            else:
                # Не сложившийся кандидат хранится ЦЕЛИКОМ, а не одним именем: его числа
                # (посчитанные, но завёрнутые в уточнение) решают, есть ли расхождение.
                mute[c] = sub
            if PROBE:
                sd = sub.get("diag") or {}
                diag.setdefault("arb_probe", []).append({
                    "src": c, "kind": sub.get("kind"), "fig": sub.get("figures"),
                    "почему": [k for k in ("measure_ambiguous", "measure_all_zero",
                                           "measure_no_values", "ambiguous",
                                           "unsupported_pick", "alias_no_evidence",
                                           "not_enough") if sd.get(k)],
                    "величины": sd.get("measure_ambiguous") or [],
                    "measure": sd.get("measure")})
        # 🔴 КАНДИДАТ, НЕ ДАВШИЙ ЧИСЛА, — ЭТО НЕ СОГЛАСИЕ (05.08).
        # Соперник считается тем же кодом, и он может вернуться не числом, а собственным
        # уточнением — например, когда у него самого несколько подходящих величин. Прежде
        # такой ответ просто выпадал из `cand_ans`, сравнивать становилось нечего, и молчание
        # засчитывалось за «числа сошлись»: ответ уходил по первому кандидату.
        # Живой случай `[замер 05.08]`: «Во что нам обошлись закупки?» — пара
        # «регистр ← документ» найдена, документ в круг попал, но его ответ пришёл
        # уточнением по величине, и система всё равно ответила по регистру.
        # Правило то же, что у `answers_diverge`: доказательства совпадения нет — спрашиваем.
        # Оговорка узкая: только пара «источник ← документ, который его пишет», то есть
        # структурная связь из данных, а не всякий не сложившийся кандидат — иначе вопрос
        # задавался бы там, где соперник просто пуст.
        #
        # 🔴 НО «НЕТ ЧИСЛА В ОТВЕТЕ» И «НЕТ ЧИСЛА ВОВСЕ» — РАЗНЫЕ ВЕЩИ (05.08, вечер).
        # Уточнение соперника бывает не о том, ЧТО отвечать, а о том, КАКОЙ ЕГО ВЕЛИЧИНОЙ
        # (`measure_ambiguous`) или с каким встречным вопросом (`asked_back`). Числа при
        # этом посчитаны базой — они лежат в его `figures` и в `measure_totals`. Делать из
        # неоднозначности ВЕЛИЧИНЫ соперника вывод о неоднозначности СУЩНОСТИ значит
        # спрашивать не о том: `[замер 05.08]` «Сколько денег нам должны клиенты?»
        # отвечалось верно (`accumulationregister_расчетысклиентами`) и стало уточнением
        # именно так. По п. 21 отвергнутый верный ответ — дефект проверки, а не осторожность.
        # Поэтому совпадение ищется ЧИСЛАМИ: наш итог сверяется со всеми числами соперника.
        # Нашлось равное — прочтения сошлись, вопрос был бы шумом; не нашлось (или числа у
        # соперника нет ни одного) — правило работает как прежде и спрашивает.
        # Порога и допуска нет намеренно, как и в `answers_diverge`: равенство или ничего.
        доказано = False
        if diag.get("writer_pair") in mute and picked and cand_src:
            # Сверяется ответ ИМЕННО ВЫБРАННОЙ сущности, а не первый сложившийся: круг
            # арбитра упорядочен, но выбор модели мог и не дать числа — тогда доказывать
            # нечего, и правило работает как прежде.
            свой = next((s for s in cand_src
                         if (s.get("diag") or {}).get("focus") == picked[0]), None)
            наше = (figures_numbers(свой) or [None])[0]
            доказано = same_number(наше, figures_numbers(mute[diag["writer_pair"]]))
            if доказано:
                diag["writer_pair_proven"] = {"число": наше,
                                              "у_соперника": diag["writer_pair"]}
        # 🔴 СОПЕРНИК, НЕ ДАВШИЙ ОТВЕТА ВОВСЕ, — ТОЖЕ НЕ СОГЛАСИЕ (06.08). Правило 05.08
        # смотрело только `mute` — соперника, чей ответ завернулся в уточнение. Но
        # под-вызов может и УПАСТЬ (исключение выше — `continue`), и тогда соперник не
        # попадает ни в ответы, ни в `mute`: круг «схлопывался» в одного, и путь
        # «сложился один кандидат» отпускал его ответ БЕЗ сравнения чисел. Живой случай
        # `[замер 06.08]`, приёмка №42 «Сколько документов реализации с нулевой суммой?»:
        # выбран регистр «НДС Состояние Реализации 0» (4 записи), документ-регистратор
        # в круге молчал — и неверный ответ ушёл уверенным, два прогона подряд. Это
        # прямое нарушение п. 12 (выбор наугад между прочтениями) и п. 10.
        if picked and not доказано and pair_unanswered(
                diag.get("writer_pair"),
                {(s.get("diag") or {}).get("focus") for s in cand_src}):
            opts_src = [picked[0], diag["writer_pair"]]
            try:
                lab_by = {r[0]: r[1] for r in psql(
                    "SELECT src_table, label FROM %s WHERE src_table IN (%s)"
                    % (TABLES, ", ".join(lit(c) for c in opts_src))) if r and r[0]}
            except RuntimeError:
                lab_by = {}
            opts = mk_opts([c for c in opts_src if c in lab_by], lab_by, marks, by, match=match, preds=preds)
            if len(opts) > 1:
                diag["writer_pair_unproven"] = diag["writer_pair"]
                return {"partial": cut or None, "kind": "clarify",
                        "text": clarify_say(question, opts, diag), "options": opts,
                        "sources": [o["label"] for o in opts],
                        "diag": dict(diag, sec=round(time.time() - t0, 2))}
        if len(cand_ans) > 1 and ARBITER_DETECTS:
            _figs = [arbiter_figures(s) for s in cand_src]
            _diverge = answers_diverge(_figs)
            _src_c = answers_src_conflict([
                {"src": (s.get("diag") or {}).get("focus"),
                 "kind": s.get("kind"),
                 "figures": f} for s, f in zip(cand_src, _figs)])
            # A3 — только когда diverge уже ложь: совпавший счётчик не доказывает
            # сущность (книга и реализации позавчера обе 19). Исключения «число
            # одно — согласие» нет: цена — «контрагенты 155=155» станет уточнением.
            if _diverge or _src_c:
                # 🔴 АРБИТР — ДЕТЕКТОР НЕОДНОЗНАЧНОСТИ, А НЕ ВЫБИРАЮЩИЙ (задача 17 реестра).
                # Числа кандидатов посчитаны базой и РАЗОШЛИСЬ — значит вопросу отвечают разные
                # объекты с разными величинами, и это доказанная неоднозначность, а не повод
                # положиться на языковую догадку модели. Живой случай `[замер 03.08]`: на «на
                # какую сумму мы закупили» кандидатами идут документ приобретения
                # (`СуммаДокумента` 73 181 157,68) и регистр накопления «Закупки» (`Сумма`
                # 1 137 949,71) — прежде выбирал арбитр, и в последнем прогоне приёмки выбрал
                # регистр. Ошибка при этом честная по гейту: число посчитано верно, просто не по
                # той сущности, — поэтому ловится это только здесь.
                # Оба ответа уже собраны, то есть человеку предлагается выбор, за которым стоят
                # реальные числа, а не догадка о том, что он имел в виду.
                src_of = [s.get("diag", {}).get("focus") for s in cand_src]
                try:
                    lab_by = {r[0]: r[1] for r in psql(
                        "SELECT src_table, label FROM %s WHERE src_table IN (%s)"
                        % (TABLES, ", ".join(lit(c) for c in src_of if c))) if r and r[0]}
                except RuntimeError:
                    lab_by = {}
                opts = mk_opts([c for c in src_of if c], lab_by, marks, by, match=match, preds=preds)
                if len(opts) > 1:
                    if _diverge:
                        diag["arbiter_detected"] = {
                            "кандидаты": src_of,
                            "числа": [(s.get("figures") or {}).get("sum")
                                      if (s.get("figures") or {}).get("sum") is not None
                                      else (s.get("figures") or {}).get("count")
                                      for s in cand_src]}
                    if _src_c:
                        diag["arbiter_src_conflict"] = {"кандидаты": src_of}
                    return {"partial": cut or None, "kind": "clarify",
                            "text": clarify_say(question, opts, diag), "options": opts,
                            "sources": [o["label"] for o in opts],
                            "diag": dict(diag, sec=round(time.time() - t0, 2))}
        if len(cand_ans) > 1:
            n = arbitrate(question, cand_ans, context)
            diag["arbiter"] = {"candidates": [s.get("diag", {}).get("focus") for s in cand_src],
                               "chose": None if n is None else
                                        cand_src[n].get("diag", {}).get("focus")}
            if n is not None:
                out = dict(cand_src[n])
                out["diag"] = dict(out.get("diag", {}), arbiter=diag["arbiter"])
                out["partial"] = cut or out.get("partial")
                return _checked(out)
        elif len(cand_ans) == 1:
            # Ответ смог собраться только у одного кандидата — остальные пусты. Выбирать не
            # из чего, но это НЕ повод не проверять: «остальные не собрались» говорит о
            # соперниках, а не о том, что этот верен.
            out = dict(cand_src[0])
            sole = (out.get("diag") or {}).get("focus")
            # 🔴 ОДИНОЧКА ОБЯЗАНА БЫТЬ ВЫБОРОМ МОДЕЛИ, А НЕ СОПЕРНИКОМ (06.08, вечер).
            # [замер 06.08], приёмка №42 «Сколько документов реализации с нулевой суммой?»:
            # модель выбрала ВЕРНЫЙ документ реализации, но его ответ завернулся в
            # уточнение о величине (пять суммовых полей), а собрался ответ соперника —
            # регистра «НДС Состояние Реализации 0» с числом 4 при эталоне 0. Путь
            # «сложился один» отпустил число СОПЕРНИКА как ответ на вопрос — выбор
            # наугад между прочтениями, замаскированный под согласие круга. Если выбор
            # модели молчит, а отвечает соперник, — прочтения два, и решает человек.
            blocked = mute_measure_blocks(sole, mute, cand_src)
            if picked and single_is_rival(picked[0], sole):
                opts_src = [picked[0], sole]
                try:
                    lab_by = {r[0]: r[1] for r in psql(
                        "SELECT src_table, label FROM %s WHERE src_table IN (%s)"
                        % (TABLES, ", ".join(lit(c) for c in opts_src))) if r and r[0]}
                except RuntimeError:
                    lab_by = {}
                opts = mk_opts([c for c in opts_src if c in lab_by], lab_by, marks, by, match=match, preds=preds)
                if len(opts) > 1:
                    diag["single_was_rival"] = {"выбор": picked[0], "ответил": sole}
                    return {"partial": cut or None, "kind": "clarify",
                            "text": clarify_say(question, opts, diag), "options": opts,
                            "sources": [o["label"] for o in opts],
                            "diag": dict(diag, sec=round(time.time() - t0, 2))}
            if blocked:
                opts_src = [x for x in (sole, blocked) if x]
                try:
                    lab_by = {r[0]: r[1] for r in psql(
                        "SELECT src_table, label FROM %s WHERE src_table IN (%s)"
                        % (TABLES, ", ".join(lit(c) for c in opts_src))) if r and r[0]}
                except RuntimeError:
                    lab_by = {}
                opts = mk_opts([c for c in opts_src if c in lab_by], lab_by, marks, by, match=match, preds=preds)
                if len(opts) > 1:
                    diag["mute_measure_rival"] = {"ответил": sole, "уточнение": blocked}
                    return {"partial": cut or None, "kind": "clarify",
                            "text": clarify_say(question, opts, diag), "options": opts,
                            "sources": [o["label"] for o in opts],
                            "diag": dict(diag, sec=round(time.time() - t0, 2))}
            out["diag"] = dict(out.get("diag", {}), arbiter={"single": True})
            out["partial"] = cut or out.get("partial")
            return _checked(out)

    if len(picked) > 1:
        try:
            lab_by = {r[0]: r[1] for r in psql(
                "SELECT src_table, label FROM %s WHERE src_table IN (%s)"
                % (TABLES, ", ".join(lit(c) for c in picked))) if r and r[0]}
        except RuntimeError:
            lab_by = {}
        opts = mk_opts(list(picked), lab_by, marks, by, match=match, preds=preds)
        if len(opts) > 1:
            diag["ambiguous"] = [o["src"] for o in opts]
            return {"partial": cut or None, "kind": "clarify",
                    "text": clarify_say(question, opts, diag),
                    "options": opts, "sources": [o["label"] for o in opts],
                    "diag": dict(diag, sec=round(time.time() - t0, 2))}
        if len(opts) == 1:
            picked = [opts[0]["src"]]
        # все живые счета 0 — не выбор из нулей; дальше страж пустого периода
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
    # Тот же контроль на пути БЕЗ арбитра: правило обязано быть одно, а не два похожих.
    # Прежде здесь лежала его собственная копия, и она разошлась с замыслом — проверяла
    # `list_has_any` (хоть одно общее слово), то есть пропускала 160 сущностей из 697.
    # 🔴 ОГОВОРКА `cand != top_by_question` ОСТАВЛЕНА — И ЭТО РЕШЕНО ЗАМЕРОМ, А НЕ ВКУСОМ.
    # Смысл её в том, что совпадение выбора модели с вершиной по вектору считается
    # подтверждением и отменяет проверку по синонимам. Опора слабая: вершина по вектору
    # верна `[замер 04.08, сессия шага 3]` в 10-13 случаях из 44. Я снял оговорку и
    # замерил: на всём наборе неверных стало меньше, но верных ответов не осталось почти
    # совсем — система начала спрашивать на 9 вопросах из 10 (в следе «выбор без опоры» у
    # вопросов 1, 3, 5, 13, 15, 17, 19, то есть в том числе у тех, что отвечались ВЕРНО).
    # Это ноль ошибок ценой отказа от ответов, а п. 21 `TARGET.md` ставит ответ выше
    # уточнения. Оговорка возвращена; разбор и числа — в `CHANGELOG` 04.08.
    # 🔴 `not no_arbiter` — ПРОВЕРКА СТОИТ НА ИТОГОВОМ ОТВЕТЕ, А НЕ НА КАЖДОМ ПОСЧИТАННОМ
    # КАНДИДАТЕ (05.08). Круг арбитра собирает ответы кандидатов ЭТИМ ЖЕ кодом
    # (`answer(..., focus=c, no_arbiter=True)`), и с включённым `ALIAS_VETO` подчинённый
    # вызов возвращал не число, а уточнение. Такой ответ в `cand_ans` не попадает, сравнивать
    # становится нечего, и арбитр-детектор молчал — то есть вето само гасило механизм,
    # который должен был поймать ошибку. Поймано пробой: на «Во что нам обошлись закупки?»
    # пара «регистр ← документ» нашлась (`writer_pair`), соперник в круг попал, а ответ всё
    # равно ушёл по регистру, потому что ответ документа не собрался.
    # Итоговый выбор по-прежнему проверяется — `_checked()` на всех ветках возврата арбитра.
    if REQUIRE_SUPPORT and picked and not focus and not no_arbiter:
        cand = picked[0]
        if cand != top_by_question:
            ok, top = _alias_verdict(cand)
            if not ok:
                ask = _alias_clarify(cand, top)
                if ask:
                    return ask
    src = picked[0] if picked else None
    # 🔴 ЧАСТИЧНО СОВПАВШЕЙ СУЩНОСТИ — ЕЁ СОБСТВЕННОЕ УСЛОВИЕ, И РАНЬШЕ ВСЕХ ПРОВЕРОК.
    # `match` собран под общий порог: столько понятий у этой сущности не нашлось, значит по
    # нему у неё ноль строк. Не подменив условие здесь, мы бы своей же проверкой ниже
    # («поиск сюда не попал») отбросили кандидата обратно к тому, что прошло порог, — и
    # правка отбора не дала бы ничего. Дальше по этому же условию считаются итоги
    # (`aggregate`, `totals_of`, `rows_of`), поэтому число будет посчитано по тем строкам,
    # которыми сущность и попала в кандидаты. Приём тот же, что у табличных частей.
    if src in part_pred:
        match = part_pred[src]
        diag["via_partial"] = part_lvl.get(src)
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

    # Выведенный период обнулил выборку — снять догадку и считать снова.
    # Догадка не имеет права отказать (п. 12 + п. 21). Стоит до выбора величины:
    # иначе все величины выглядят пустыми из-за чужого окна дат.
    if src and empty_after_period_action(intent) == "drop_assumed":
        _probe = rows_of(src, match, preds, 1)
        if not _probe:
            intent, preds = drop_period_preds(intent, preds)
            diag["period_assumed_dropped"] = True
    diag["focus"], diag["found"] = src, by.get(src, 0)
    шаг("сущность выбрана", сущность=(src or "—"), совпадений=by.get(src, 0),
        выбрал=("человек" if focus else "модель"),
        сомнение=bool(diag.get("signals_disagree")))

    # НЕПОЛНОТА ИМЕННО ЭТОЙ СУЩНОСТИ (п. 13): «если из-за потери возможен неверный ответ,
    # система обязана уточнить или отказать, а не ответить по неполным данным». Первый шаг
    # — сказать. Отметка идёт ПОЛЕМ ответа, а не припиской в тексте: текст пишет модель на
    # языке вопроса, а проверяемым должно быть число.
    cov = _coverage_of(src)
    if cov:
        diag["incomplete"] = cov
        if cov.get("missing", 0) > 0:
            cut["coverage_missing"] = cov["missing"]

    # ВЕЛИЧИНА ВЫБИРАЕТСЯ ПО ВОПРОСУ — после того, как известна сущность: её величины
    # лежат в самих данных. Числовое условие («больше 500000») тоже применяется здесь,
    # а не на общем отборе: у документа оно про сумму, у строки накладной могло бы
    # оказаться про количество.
    # 🔴 ПЕРВЫМ ДЕЛОМ — ВЕЛИЧИНА, КОТОРУЮ НАЗВАЛА МОДЕЛЬ, ЧИТАВШАЯ ВОПРОС. Её имя уже
    # сверено со списком величин ЭТОЙ сущности (`pick_entity`), то есть выдуманное имя сюда
    # не доходит. Прежний путь (`pick_measure`) остаётся запасным: он выбирает по похожести
    # имён, не видя вопроса, и именно поэтому ошибался.
    # 🔴 ВЕЛИЧИНА ЖИВЁТ В ТАБЛИЧНОЙ ЧАСТИ, А НЕ В ШАПКЕ — И ЭТО НЕ ДВЕ СУЩНОСТИ, А ОДНА.
    # [замер 30.07] эталоны четырёх вопросов приёмки лежат ИМЕННО в табличной части, и в
    # шапке этих величин нет вовсе: «сколько НДС заплатили поставщикам» — 11 036 086,09 в
    # `..._товары.СуммаНДС`; «сколько штук закупили» — 92 683 в `..._товары.Количество`;
    # «цена за единицу» — 50 000 в `..._товары.Цена`. Шапка отвечала не тем или ничем.
    # Переход делается ПО ДАННЫМ: родство берётся из `search_tables.parent`, наличие
    # величины — из `map_keys(nums)`, сравнение имени — штатным словарём по основам.
    # Переходим ТОЛЬКО когда член семьи ровно один: два — это уже выбор, а выбор молча
    # делать нельзя (п. 12). Ни порога, ни имени конкретной базы здесь нет.
    want = (plan.get("quantity") or intent.get("measure") or "").strip()
    if want and not focus and not any(m.lower() == want.lower() for m in measures_of(src)):
        try:
            fam = _family(src)
            owners = [r[0] for r in psql(
                "WITH kin AS (SELECT src_table FROM %s WHERE src_table = %s OR parent = %s) "
                "SELECT DISTINCT m.src_table FROM (SELECT src_table, unnest(map_keys(nums)) AS k "
                "  FROM %s WHERE src_table IN (SELECT src_table FROM kin) AND nums IS NOT NULL) m "
                "WHERE list_has_any(ts_lexize(%s, m.k), ts_lexize(%s, %s))"
                % (TABLES, lit(fam), lit(fam), CORPUS,
                   lit(STEM_DICT), lit(STEM_DICT), lit(want))) if r and r[0]]
        except RuntimeError:
            owners = []
        if len(owners) == 1 and owners[0] != src:
            diag["measure_in_kin"] = {"было": src, "стало": owners[0], "величина": want}
            src = owners[0]
            match, preds = match, [p for p in preds if p]
            diag["focus"], diag["found"] = src, by.get(src, 0)

    measure, measure_alts = None, []
    if plan.get("quantity") and plan["quantity"] in measures_of(src):
        measure = plan["quantity"]
        diag["measure_by_plan"] = True
        # 🔴 ГЕЙТ ВЕЛИЧИНЫ (задача 16 реестра «право на ответ (б)»). Имя, названное моделью,
        # проверялось ТОЛЬКО на существование у сущности — и этого мало: слову вопроса могут
        # отвечать несколько величин, и тогда модель выбрала одну из них молча, а п. 12
        # запрещает выбирать между правдоподобными вариантами за человека. Раньше правило
        # жило внутри `pick_measure`, то есть на этот путь не распространялось вовсе.
        #
        # Спрашиваем не всегда, когда подходящих несколько, а только когда выбор МЕНЯЕТ
        # ОТВЕТ (`measure_ambiguous`): у документа `СуммаДокумента` и `СуммаСНДС` его
        # табличной части дают одно и то же число, и вопрос о них был бы шумом, а шум
        # обесценивает настоящие уточнения.
        _word = (intent.get("measure") or "").strip()
        _malias = measure_aliases_of(src)
        _got, _alts, _how = measure_choice(measures_of(src), _word,
                                           alias_by=_malias)
        if _how == 'ask' and measure in _alts:
            _tot = {m: v for m, v, _mx, _mn in totals_of(src, match, preds, _alts)}
            if measure_ambiguous(_alts, _tot):
                measure, measure_alts = None, _alts
                diag["measure_gate"] = {"слово": _word, "подошли": _alts}
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
    if not measure and not measure_alts:
        _qn = measures_of(src)
        _qt = {}
        _need_q = ((intent.get("want") or "") == "sum"
                   or (plan.get("compute") or "") in ("sum", "max", "min", "avg"))
        if _need_q and len(_qn) > 1:
            try:
                _qt = {m: v for m, v, _mx, _mn
                       in totals_of(src, match, preds, _qn)}
            except RuntimeError:
                _qt = {}
        measure, measure_alts = unresolved_quantity(
            measure, measure_alts, intent.get("want"), plan.get("compute"),
            _qn, _qt)
    if measure_pick:                           # человек уже выбрал величину кнопкой
        _names = measures_of(src)
        _resolved = resolve_measure(measure_pick, _names,
                                    measure_aliases_of(src), diag)
        if _resolved:
            measure, measure_alts = _resolved, []
        elif measure_pick in _names:
            measure, measure_alts = measure_pick, []
        else:
            diag["measure_pick_unresolved"] = measure_pick
    diag["measure"] = measure
    шаг("величина выбрана", величина=(measure or "—"),
        подходящих=len(measure_alts or []))
    # 🔴 ТОЖДЕСТВЕННО НУЛЕВАЯ ВЕЛИЧИНА — ЭТО НЕЗАПОЛНЕННОЕ ПОЛЕ, А НЕ ОТВЕТ «НОЛЬ».
    #
    # [замер 03.08] «Сколько НДС в наших продажах?» — выбран регистр выручки и величина
    # `НДСРегл`. Она у сущности ЕСТЬ и заполнена во всех 3 878 строках, но во всех она
    # равна нулю. Система сложила и ответила «0 ₽» при эталоне 3 125 757,80. Ноль выглядит
    # как настоящий ответ — человек не отличит его от посчитанного, и это худший исход из
    # возможных (п. 21: неверный ответ хуже отказа и хуже уточнения).
    #
    # Явление не частное `[замер 03.08]`: из 1 928 пар «сущность-величина» боевой базы
    # **454 (23,5 %) тождественно нулевые**, они есть у 199 сущностей из 539. В самом этом
    # регистре нулевых 15 из 36 — то есть выбирая наугад, промахнуться легче, чем попасть.
    #
    # Признак — тождество, а не порог: `sum = max = min = 0` означает, что поле не несёт
    # ни одного значения ни в одной строке. Константы, подобранной под нашу базу, здесь
    # нет, слов и языка нет тоже, поэтому правило одинаково верно на любой конфигурации.
    #
    # Выбор человека (`measure_pick`) не перебиваем: спросил именно это поле — считаем его
    # и отвечаем нулём честно. Заменяем только МОЛЧАЛИВЫЙ выбор — модели или реранкера.
    # Альтернативы берём из данных: величины той же сущности, у которых значения есть.
    #
    # 🔴 ВТОРАЯ ДВЕРЬ К ТОМУ ЖЕ НУЛЮ: ВЕЛИЧИНЫ НЕТ НИ У ОДНОЙ ОТОБРАННОЙ СТРОКИ.
    # Правило 03.08 смотрело только в `totals_of`, а тот отдаёт пару, лишь когда строк со
    # значением больше нуля. Значит случай «ни одной строки со значением» страж не видел
    # вовсе — и он не редкость: имена величин (`measures_of`) берутся по ВСЕЙ сущности, а
    # считается ОТОБРАННОЕ подмножество, где выбранного поля может не быть ни разу.
    # [замер 04.08] прибор `step5_bench.py` показал это на 8 парах из 8: при нуле строк со
    # значением ответ содержал `sum=0, min=0, max=0, avg=0`. Такой ноль неотличим от
    # посчитанного и проходит гейт — тот же исход, ради которого правило 03.08 и заведено,
    # только через другую дверь. Отсюда одно условие на оба случая: считать было нечего
    # ЛИБО всё тождественно ноль.
    if measure and not measure_pick:
        _t1 = totals_of(src, match, preds, [measure])
        _пусто = not _t1                                   # ни одной строки со значением
        _ноль = bool(_t1) and _t1[0][1] == 0 and _t1[0][2] == 0 and _t1[0][3] == 0
        if _пусто or _ноль:
            _alive = [m for m, v, mx, mn in totals_of(src, match, preds, measures_of(src))
                      if not (v == 0 and mx == 0 and mn == 0)]
            if _alive:
                diag["measure_all_zero" if _ноль else "measure_no_values"] = measure
                measure, measure_alts = None, _alive
                diag["measure"] = None
    if SLOT_COVER and measure and not measure_pick:
        _unc, _cov = slot_measure_uncovered(
            (intent.get("measure") or "").strip(), measure,
            measures_of(src), measure_aliases_of(src))
        if _unc:
            diag["slot_uncovered"] = {"слово": intent.get("measure"),
                                       "выбрано": measure, "покрывают": _cov}
            measure, measure_alts = None, _cov
            diag["measure"] = None
    # Несколько величин подходят одинаково — спрашиваем, какую считать. Механизм тот же,
    # что для сущности: кнопки из ДАННЫХ плюс «свой вариант» (решение владельца 28.07).
    if measure_alts:
        diag["measure_ambiguous"] = measure_alts
        # 🔴 ЧИСЛА ПОДХОДЯЩИХ ВЕЛИЧИН СЧИТАЮТСЯ ЗДЕСЬ ЖЕ — ОНИ НУЖНЫ НЕ ЧЕЛОВЕКУ, А ПРОВЕРКЕ
        # НАД НАМИ (05.08). Этот же путь проходит КАНДИДАТ круга арбитра
        # (`answer(..., focus=c)`), и его уточнение о собственной величине наверху читалось
        # как «числа не сошлись» — хотя ни одного числа кандидата там не было вовсе.
        # Один запрос теми же условиями отбора даёт итог по каждой подходящей величине, и
        # совпадение становится ДОКАЗУЕМЫМ (разбор — у `writer_pair_unproven`).
        # В модель это не уходит: путь возвращает уточнение, а `diag` модели не показывают.
        try:
            diag["measure_totals"] = {m: v for m, v, _mx, _mn
                                      in totals_of(src, match, preds, measure_alts)}
        except RuntimeError:
            pass
        # 🔴 `entity_label` — человеческое имя ТОЙ ЖЕ сущности, отдельно от `label`, где
        # здесь лежит имя ВЕЛИЧИНЫ. Без него мост не мог назвать боту сущность иначе как
        # внутренним именем (`src`), а оно оттуда утекало человеку (03.08). Спрашивается у
        # базы, а не собирается разбором строки; не нашлось — поле пустое, и мост честно
        # обходится без него.
        try:
            _lab = psql("SELECT label FROM %s WHERE src_table = %s LIMIT 1"
                        % (TABLES, lit(src)))
            _ent = (_lab[0][0] or "") if _lab and _lab[0] else ""
        except RuntimeError:
            _ent = ""
        _caps = measure_captions(measure_alts, measure_aliases_of(src))
        opts = [{"src": src, "measure": m, "label": _caps[m], "distinct_by": "",
                 "entity_label": _ent}
                for m in measure_alts]
        # 🔴 ВОПРОС ЗАДАЁТ МОДЕЛЬ, НА ЯЗЫКЕ СПРАШИВАЮЩЕГО. Здесь стояла наша русская фраза
        # «Уточните, какую величину считать», и она составляла ВЕСЬ текст уточнения: на
        # англоязычном клиенте человек не понял бы, что у него спрашивают. Тот же
        # `clarify_text`, что и у выбора сущности; не смогла сформулировать — остаётся
        # перечень величин, по нему выбор всё равно возможен.
        return {"partial": cut or None, "kind": "clarify",
                "text": clarify_say(question, opts, diag)
                        or ", ".join("«%s»" % o["label"] for o in opts),
                "options": opts, "sources": [src],
                "diag": dict(diag, sec=round(time.time() - t0, 2))}
    # Величина не названа — считаем итоги по всем и показываем модели с именами.
    totals = [] if measure else totals_of(src, match, preds, measures_of(src))
    if totals:
        diag["totals"] = {m: [v, mx, mn] for m, v, mx, mn in totals}
    preds = preds + _num_pred(intent, measure)
    rows = rows_of(src, match, preds, TOPK, measure)
    if not rows:
        # Ранний no_data стоял ДО счёта undated: при 100% строк без даты
        # потеря была полной, и «данных нет» срабатывало про существование.
        act = empty_after_period_action(intent)
        if act == "drop_assumed":
            intent, preds = drop_period_preds(intent, preds)
            diag["period_assumed_dropped"] = True
            rows = rows_of(src, match, preds, TOPK, measure)
            act = empty_after_period_action(intent)
        if not rows and act != "empty_period":
            return {"partial": cut or None, "kind": "no_data",
                    "text": NO_DATA_TEXT or refuse_text(question), "sources": [],
                    "diag": dict(diag, sec=round(time.time() - t0, 2))}

    agg = aggregate(src, match, preds, measure)
    шаг("посчитано базой", сущность=src, величина=(measure or "—"),
        строк=(agg or {}).get("count"), итог=(agg or {}).get("sum"),
        со_значением=(agg or {}).get("count_amount"))
    # Множество, по которому посчитано, объявляется наружу целиком (см. `aggregate`):
    # по нему посторонний прибор пересчитывает итог независимо, а не верит нашему числу.
    # До модели `diag` не доходит.
    if agg and agg.get("scope"):
        diag["счёт"] = dict(agg["scope"], величина=measure,
                            строк=agg["count"], со_значением=agg["count_amount"],
                            групп_отброшено=agg["folders"],
                            вне_разрядности=agg["out_of_range"])
    # 🔴 ПЕРИОД ВЫБРАСЫВАЕТ СТРОКИ БЕЗ ДАТЫ — И ЭТО ОБЯЗАНО БЫТЬ ВИДНО ЧИСЛОМ (п. 13).
    #
    # Условие по периоду сравнивает `doc_date`, а строка без даты не проходит НИ ОДНО
    # сравнение: она исчезает из счёта молча, как будто её нет. Для табличных частей это
    # не редкость, а норма — дата стоит в шапке, и в строках её нет вовсе: `[замер 04.08]`
    # у `document_возвраттоваровотклиента_товары` без даты 54 строки из 55 (98 %), у
    # `..._расшифровкаплатежа` — 97 из 99, всего таких сущностей 22. То есть вопрос «за
    # 2019 год» по табличной части считает единицы строк вместо всех и об этом не говорит.
    #
    # Считаем ровно то, что отняло НАШЕ условие по дате: то же множество без датных
    # предикатов, строки без даты. Список датных предикатов берётся у того же
    # `_predicates`, что их и построил, — строку никто не разбирает.
    _date_preds = _predicates(intent)
    if _date_preds and agg:
        try:
            _kept = [p for p in preds if p not in _date_preds]
            _u = psql("SELECT count(*) FROM %s WHERE %s AND doc_date IS NULL"
                      % (INDEX if match else CORPUS,
                         " AND ".join([w for w in ([match] + _kept
                                       + ["src_table = %s" % lit(src)]) if w])))
            _undated = int(_u[0][0]) if _u and _u[0] else 0
        except (RuntimeError, ValueError, IndexError):
            _undated = 0
        if _undated:
            agg["undated"] = _undated
            cut["undated_excluded"] = _undated
            if "счёт" in diag:
                diag["счёт"]["без_даты_отброшено"] = _undated
            # 🔴 В `cov` это НЕ дописывается, хотя соблазн есть: у него читаются ИМЕННО
            # ключи `in_1c`/`in_search`/`missing` (ниже, в белом списке гейта и в местах
            # подстановки), и словарь с другим составом уронил бы ответ `KeyError`-ом на
            # каждом вопросе с периодом. Число живёт в самом счёте (`agg`) и в объявлении
            # множества; в белый список гейта оно попадает отдельной строкой ниже.
        try:
            _o = psql("SELECT count(*) FROM %s WHERE %s AND doc_date IS NOT NULL"
                      % (INDEX if match else CORPUS,
                         " AND ".join([w for w in ([match] + _kept
                                       + ["src_table = %s" % lit(src)]) if w])))
            _outside = int(_o[0][0]) if _o and _o[0] else 0
        except (RuntimeError, ValueError, IndexError):
            _outside = 0
        if _outside:
            agg["outside_period"] = _outside
            if "счёт" in diag:
                diag["счёт"]["вне_периода"] = _outside
    # Числа неполноты разрешены гейту наравне с порогами вопроса: иначе фраза «не дошло
    # 104 строки» была бы отвергнута как выдумка, и система замолчала бы ровно там, где
    # обязана предупредить.
    # 🔴 РАЗРЕШЕНЫ ЧИСЛА НАШЕГО ОТБОРА, А НЕ ВСЕ ЧИСЛА ВОПРОСА (`F244`, правка 04.08).
    # Прежде сюда уходило `_norm_numbers(question)` целиком — «эхо числа из вопроса не
    # выдумка» (правило 28.07 ради «оборотов по счёту 62»). Но вопрос сочиняет модель
    # бота, и через этот список проходило любое её число: `[замер 04.08, probe_gate]`
    # выдуманный итог «7 777 777» проходил гейт, если он же стоял в вопросе. Класс,
    # который сама `gate()` называет недопустимым, а плагин закрыл ещё 02.08.
    # `_filter_values` оставляет то же самое ровно там, где это проверяемо: значение
    # применённого нами предиката и числовое понятие, по которому мы искали.
    # 🔴 ЧИСЛО ОТБРОШЕННЫХ ГРУПП — НА ТЕХ ЖЕ ПРАВАХ, ЧТО И ЧИСЛА ПЕРЕПИСИ. Оговорку про
    # папки задание требует назвать цифрами (иначе человек, знающий про 252 строки, не
    # поймёт, откуда 227), а гейт этого числа не знал — оно не приходит ни из строк, ни
    # из агрегатов, ни из вопроса. `[замер 04.08, step6_live.py]` три прогона из трёх:
    # «гейт: числа вне данных [25.0]» — то есть ответ, составленный ровно как велено,
    # отвергался собственной проверкой и уходил в `figures`. Ровно тот дефект проверки,
    # который п. 21 называет дефектом, а не осторожностью. `folders` посчитан базой тем же
    # запросом, что и `count`, — обоснован по построению.
    money = answer_money(intent.get("want"), plan.get("compute"), measure)
    extra_vals = _filter_values(intent) + (
        [x for t in (totals or []) for x in t[1:]] if money else []) \
                 + ([cov["in_1c"], cov["in_search"], cov["missing"]] if cov else []) \
                 + ([agg["undated"]] if (agg or {}).get("undated") else []) \
                 + ([agg["outside_period"]] if (agg or {}).get("outside_period") else []) \
                 + ([agg["folders"]] if (agg or {}).get("folders") else [])
    # Границы периода отбора — на тех же правах, но по датной ветке гейта.
    our_dates = _filter_dates(intent)
    # Оговорки к ответу — в промт, а не приписью после: язык берётся из вопроса.
    say_measure = measure if money else None
    n_folders = (agg or {}).get("folders") or 0
    totals_shown = totals if money else []
    raw = compose(question, rows, agg, totals=totals_shown, coverage=cov,
                  measure_used=say_measure, folders=n_folders, money=money)
    text, claims = _split_answer(raw)
    ask_back = _ask_back(raw)
    # Рукопись ищется ДО подстановки: после неё посчитанное число стоит в тексте законно,
    # и отличить поставленное кодом от набранного моделью уже нельзя.
    by_hand = copied_figures(text, agg, rows)
    # КАЛЬКУЛЯТОР: числа ставит код, а не модель. Всё, что подставлено, посчитано базой,
    # поэтому проверять его не нужно — оно верно по построению.
    # Числа неполноты идут в подстановку наравне с итогами: их модель тоже не видит.
    cov_slots = ({"in_1c": cov["in_1c"], "in_search": cov["in_search"],
                  "missing": cov["missing"]} if cov else None)
    text, slots_bad = _fill_figures(text, agg, totals_shown, money, cov_slots)
    ask_back = _filled_ask(ask_back, agg, totals_shown, money, diag, cov_slots)
    # Место, которому нечего подставить, — отказ формулировки: модель сослалась на
    # величину, которой мы не считали. Это единственная проверка, оставшаяся от прежней
    # ролевой сверки, и она структурная, а не числовая.
    bad_roles = formulation_flaws(text, slots_bad) + by_hand
    ok_roles = not bad_roles

    # Проверка «ответ обязан объявить величину через claims» УБРАНА вместе с самими
    # claims (промт велит оставлять их пустыми). Её смысл держит `asked_figure_missing`:
    # спрошенная величина обязана стоять в ответе цифрами, а отброшенное — быть названо
    # числом. Это и роль (`F285`), и числа прописью (`F286`), и оговорка о потере (`№9`).
    miss = asked_figure_missing(text, agg, intent.get("want"), money, n_folders)
    if miss:
        ok_roles, bad_roles = False, bad_roles + [miss]
    leak = prompt_leak(text, OUR_PROMPTS)
    if leak:
        ok_roles, bad_roles = False, bad_roles + ["утечка инструкции: %s" % leak]
    # 🔴 ЗАЗЕМЛЯЕМ НА ТОМ, ЧТО МОДЕЛЬ ВИДЕЛА (`F247`): показанные строки и только до
    # обрезки бюджетом. Числа из непоказанных строк белым списком быть не могут —
    # скопировать их модели неоткуда, а разрешение они давали.
    seen = rows_seen(rows)
    ok_nums, bad_nums = gate(text, seen, agg, extra_vals, our_dates, money=money)
    ok, bad = (ok_roles and ok_nums), (bad_roles + bad_nums)
    шаг("гейт исходящего", прошёл=bool(ok), причин=len(bad),
        первая=(bad[0][:60] if bad else "—"))
    # ОТВЕТ ОБЯЗАН ДОЙТИ, ЕСЛИ ОН ЕСТЬ. Решение владельца 27.07: «если данные есть, но по
    # нашей системе мы их не отдали — пропадает смысл проекта». Первая формулировка могла
    # не пройти проверку по своей вине (модель объявила число строк суммой), а данные при
    # этом посчитаны и верны. Даём ровно одну вторую попытку, назвав причину отказа, и
    # проверяем её ТЕМ ЖЕ гейтом. Ослабления проверки здесь нет: если и второй ответ не
    # сходится с базой, он не уйдёт.
    if not ok and agg:
        diag["retry"] = bad[:3]
        raw2 = compose(question, rows, agg, corrections=bad[:3], totals=totals_shown,
                       coverage=cov, measure_used=say_measure, folders=n_folders,
                       money=money)
        text2, claims2 = _split_answer(raw2)
        by_hand2 = copied_figures(text2, agg, rows)
        text2, slots_bad2 = _fill_figures(text2, agg, totals_shown, money, cov_slots)
        bad_roles2 = formulation_flaws(text2, slots_bad2) + by_hand2
        ok_roles2 = not bad_roles2
        bad_txt2 = []
        # Вторая попытка проверяется ТЕМ ЖЕ набором, что первая: иначе послабление
        # прокралось бы через ретрай — ответ, отвергнутый за неназванную величину,
        # проходил бы со второго раза, не назвав её снова.
        miss2 = asked_figure_missing(text2, agg, intent.get("want"), money, n_folders)
        if miss2:
            ok_roles2, bad_roles2 = False, bad_roles2 + [miss2]
        leak2 = prompt_leak(text2, OUR_PROMPTS)
        if leak2:
            ok_roles2, bad_roles2 = False, bad_roles2 + ["утечка инструкции: %s" % leak2]
        ok_nums2, bad_nums2 = gate(text2, seen, agg, extra_vals, our_dates,
                                          money=money)
        if ok_roles2 and ok_nums2 and (text2 or "").strip():
            # 🔴 УТОЧНЕНИЕ ВТОРОЙ ПОПЫТКИ ТОЖЕ ПРОХОДИТ ПОДСТАНОВКУ. Прежде здесь стояло
            # голое `_ask_back(raw2)`: числа в вопросе первой попытки подставлялись, а во
            # второй — нет, и человеку уходило «за какой период — с {date_min}?» с местом
            # вместо даты. Гейт этого не ловит (цифр в заготовке нет), и вопрос выглядел
            # как поломка системы ровно в тот момент, когда система переспрашивает.
            text, claims = text2, claims2
            ask_back = _filled_ask(_ask_back(raw2), agg, totals_shown, money, diag, cov_slots)
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
            # Итога может не быть вовсе — считать было нечего (`sum is None`, см.
            # `aggregate`). Тогда своя фраза с суммой не собирается: ноль на этом месте
            # был бы выдуманным числом, а не пустым местом. Числа всё равно уходят
            # структурой ниже, и вызывающий формулирует по ним.
            return {"partial": cut or None, "kind": "figures", "text": (TOTAL_TEXT.format(
                        count=agg["count"], sum=_fmt(agg["sum"]))
                        if (TOTAL_TEXT and agg.get("sum") is not None)
                        else refuse_text(question)),
                    "figures": compose_slot_values(agg, measure=measure,
                                                    folders=n_folders, money=money),
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
    # 🔴 ВСТРЕЧНЫЙ ВОПРОС ПРОВЕРЯЕТСЯ ТЕМ ЖЕ ГЕЙТОМ, ЧТО И ОТВЕТ (`F246`, правка 04.08).
    # Утверждение выше («уточнение возвращается только после гейта») было верно лишь
    # наполовину: гейт проходил `text`, а `ask` модели приклеивался к нему уже ПОСЛЕ
    # проверки и не сверялся ни с чем. Число, названное во встречном вопросе, доходило до
    # человека невыверенным — а он читает его как факт о своих данных. Не сошлось —
    # вопрос снимается, ответ уходит обычным: это ослабление уточнения, а не ответа.
    if ask_back:
        ok_ask, bad_ask = gate_out(ask_back, seen, agg, extra_vals, our_dates,
                                       money=money)
        if not ok_ask:
            sys.stderr.write("ask ASKBACK GATE: числа вне данных: %s\n" % bad_ask[:4])
            diag["ask_back_rejected"] = bad_ask[:4]
            ask_back = ""
    if ask_back:
        diag["asked_back"] = True
        return {"partial": cut or None, "kind": "clarify",
                "text": (text.strip() + "\n\n" + ask_back).strip(),
                "question": ask_back, "options": [],
                # Величина не названа вопросом — тогда `agg` считает по пустому месту, и
                # `sum: 0` был бы не «нулём», а «не считали». Отдаём то же, что видела
                # модель: итоги по каждой величине сущности, с их именами из данных.
                "figures": compose_slot_values(agg, measure=measure,
                                               folders=n_folders, money=money),
                "totals": {m: {"sum": v, "max": mx, "min": mn} for m, v, mx, mn in (totals or [])},
                "sources": [tag],
                "diag": dict(diag, rows=len(rows), sec=round(time.time() - t0, 2), gate_ok=ok)}

    # 🔴 ОТВЕТ НАЗЫВАЕТ ВЕЛИЧИНУ, ПО КОТОРОЙ СЧИТАЛ. У сущности их бывает девять со словом
    # «сумма», и молчаливый выбор неотличим от догадки (п. 12). Дописывает КОД, а не модель:
    # имя приходит из данных, значит одинаково верно на любой конфигурации, и его нельзя
    # забыть. Приписка не дублируется, если модель уже назвала величину сама.
    text = text.strip()
    # 🔴 ОБЕ ОГОВОРКИ — КАКАЯ ВЕЛИЧИНА СЧИТАНА И СКОЛЬКО ГРУПП ОТБРОШЕНО — ушли в промт
    # (`compose`), потому что здесь они дописывались НАШЕЙ русской прозой после модели.
    # Требование не ослаблено: и то и другое названо в задании как обязательное, а числа
    # оговорок разрешены гейту, то есть не будут отвергнуты как выдумка. Смысл прежний:
    # папка — не запись и в счёт не идёт, но человек, знающий про 252 строки, обязан
    # понять, откуда 227 (п. 13: молчаливая потеря — дефект).
    # Поле человеку — то же say_measure, что compose: на count пусто, даже если
    # словарь свёл колонку. Иначе мост допишет [величина: ИМЯ] без числа.
    # diag.measure выше — сырое поле; живой обход читает его, не этот ключ.
    return {"partial": cut or None, "kind": "answer", "text": text, "sources": [tag],
            "completeness": cov, "measure": say_measure,
            # 🔴 ПОСЧИТАННЫЕ ЧИСЛА — ПОЛЕМ ОТВЕТА, А НЕ ТОЛЬКО ВНУТРИ ТЕКСТА (03.08).
            # Их читает арбитр-детектор (задача 17): чтобы сравнить ответы кандидатов, он
            # обязан сравнивать ЧИСЛА, посчитанные базой, а не разбирать прозу модели.
            # Разбор текста здесь был бы догадкой (п. 12) и ломался бы на каждом языке
            # ответа. Ветка уточнения отдаёт это поле с самого начала — теперь форма одна.
            "figures": compose_slot_values(agg, measure=measure,
                                           folders=n_folders, money=money),
            "diag": dict(diag, rows=len(rows), sec=round(time.time() - t0, 2), gate_ok=ok)}


# ═══════════════ ШАГ «ДОСТАТОЧЕН ЛИ ВОПРОС ДЛЯ ОТВЕТА» (05.08) ═══════════════
#
# 🔴 ШАГ СТОИТ СНАРУЖИ `answer()`, И ЭТО НЕ УДОБСТВО, А УСЛОВИЕ ПРАВИЛЬНОСТИ. Круг арбитра
# собирает ответы кандидатов ТЕМ ЖЕ `answer(..., focus=c, no_arbiter=True)`, и проверка
# внутри превратила бы ответ кандидата в уточнение — тогда сравнивать стало бы нечего, и
# арбитр-детектор замолчал бы. Ровно так 05.08 само себя гасило вето по синонимам
# (разбор — врезка у `REQUIRE_SUPPORT` выше). Снаружи этой ошибки не бывает по построению:
# подчинённые вызовы шага не видят вовсе.
#
# Что шагу нужно от соседей и почему это ничего не стоит: разбор вопроса (`parse_intent`
# помнит ответ по ключу «вопрос + дата», поэтому вызов здесь отдаётся ДАРОМ — тот же
# разбор потом возьмёт `answer`) и числа из `diag` уже собранного ответа.
ENOUGH_ON = os.environ.get("ASK_ENOUGH", "1") not in ("0", "false", "no")
# Veto of uncovered measure slot. Default OFF: do not enable without answer-rate measure.
SLOT_COVER = os.environ.get("ASK_SLOT_COVER", "0") == "1"
# Память описаний вопроса — по тому же ключу и того же размера, что у шага 1: описание
# зависит ровно от текста вопроса, данных оно не видит.
_FACTS_MEMO = {}


def question_facts(question, today):
    """Описание вопроса моделью: на что он указывает, назван ли период и величина.

    Один вызов на вопрос, с памятью. Модель здесь — языковой инструмент: в её задании
    (`serene_enough.FACTS_SYS`) нет ни слова о том, отвечать или переспрашивать. Вердикт
    собирает код (`serene_enough.verdict_after`) из этого описания и из чисел базы.

    Не разобралось — `None`, и шаг молчит: сбой описания сам по себе уточнением не
    становится, иначе перебои у поставщика модели превращались бы в вопросы человеку.
    """
    key = (today, question)
    hit = _FACTS_MEMO.get(key)
    if hit is not None:
        return json.loads(hit)
    try:
        raw = ds_chat([{"role": "system", "content": serene_enough.FACTS_SYS},
                       {"role": "user", "content": "Question: %s" % question}],
                      max_tokens=200)
    except Exception:                              # noqa: BLE001 — сеть/квота поставщика
        return None
    got = serene_enough.parse_facts(raw)
    if got is None:
        return None
    if len(_FACTS_MEMO) >= max(1, INTENT_MEMO):
        _FACTS_MEMO.clear()
    _FACTS_MEMO[key] = json.dumps(got, ensure_ascii=False)
    return got


def entity_has_dates(src):
    """Есть ли у источника хоть одна дата — числом из базы, а не догадкой по имени.

    Нужно затем, чтобы вопрос о периоде задавался только там, где период у данных вообще
    бывает: у справочника дат нет, и «за какой период» там означало бы выбор, которого в
    данных не существует.

    Запрос дешёвый по построению: `LIMIT 1` во вложенном выборе — движку достаточно найти
    одну строку, полный проход сущности не делается. Не получилось — считаем, что дат нет:
    отсутствие сведений оставляет вопрос человеку прежним, а не расширяет его.
    """
    if not src:
        return False
    try:
        r = psql("SELECT count(*) FROM (SELECT 1 FROM %s WHERE src_table = %s "
                 "  AND doc_date IS NOT NULL LIMIT 1) x" % (CORPUS, lit(src)))
    except RuntimeError:
        return False
    try:
        return int(_num(r[0][0])) > 0 if r and r[0] else False
    except (TypeError, ValueError, IndexError):
        return False


def _gate_need(text, rows=(), agg=None, allowed=None, our_dates=None):
    """Гейт для текста уточнения этого шага: числа плюс утечка ЕГО СОБСТВЕННОГО задания.

    Общий `gate_out` сверяет утечку по списку `OUR_PROMPTS`, собранному до появления шага,
    и задания `NEED_SYS` там нет. Дописывать в чужой список отсюда — правка гейта (шаг 7,
    его ведёт другая сессия), поэтому недостающая проверка стоит своей строкой здесь, на
    том же штатном `prompt_leak`. Пересказанное человеку задание читается как факт о его
    данных ровно так же, как выдуманное число.
    """
    ok, bad = gate_out(text, rows, agg, allowed, our_dates)
    leak = prompt_leak(text, [serene_enough.NEED_SYS])
    if leak:
        return False, list(bad) + ["утечка инструкции: %s" % leak]
    return ok, bad


def _need_clarify(question, slots, why, diag):
    """Уточнение о недостающих параметрах вопроса. `None` — сформулировать не вышло.

    `options` пуст намеренно: выбирать здесь не из чего — кнопки предлагают ИСТОЧНИКИ, а
    спрашиваем мы про сам вопрос («какой товар, за какой период»). Человек отвечает новым,
    более полным вопросом, и на нём шаг уже молчит: значение названо. Протокол моста от
    этого не меняется — `[CLARIFICATION NEEDED]` он ставит по `kind`, а перечень вариантов
    у него необязателен.
    """
    txt = serene_enough.need_say(question, slots, ds_chat, _gate_need, diag)
    if not txt:
        return None
    d = dict(diag or {})
    d["not_enough"] = {"чего_нет": [s.get("kind") for s in slots if isinstance(s, dict)],
                       "почему": why}
    return {"partial": None, "kind": "clarify", "text": txt, "options": [],
            "sources": [], "diag": d}


def answer_checked(question, focus=None, measure_pick=None, context=""):
    """Ответ вместе с шагом «достаточен ли вопрос». Точка входа сервиса.

    Порядок п. 21 сохранён: сперва пробуем ответить, уточняем только там, где ответа с
    одним смыслом не существует. Дешёвая половина стоит ДО поиска и экономит весь прогон,
    решающая — ПОСЛЕ счёта, потому что опирается на посчитанные числа.

    🔴 Человек уже уточнял (`focus`, `measure`) — шаг молчит целиком. Иначе его же выбор
    вернулся бы ему вопросом, и разговор не сходился бы ни на одном круге.
    """
    def plain():
        return answer(question, focus=focus, measure_pick=measure_pick, context=context)

    if not (ENOUGH_ON and serene_enough) or focus or measure_pick:
        return plain()
    today = time.strftime("%Y-%m-%d")
    try:
        intent = parse_intent(question, today)
    except RuntimeError:
        return plain()                             # разбора нет — решает обычный путь
    need, slots, why = serene_enough.verdict_before(intent)
    if need:
        ask = _need_clarify(question, slots, why, {"шаг": "достаточность до поиска"})
        if ask:
            return ask
    out = plain()
    if not isinstance(out, dict) or out.get("kind") not in ("answer", "figures"):
        return out
    if not serene_enough.facts_wanted(intent):
        return out
    facts = question_facts(question, today)
    if not facts:
        return out
    d = out.get("diag") or {}
    счёт = d.get("счёт") or {}
    # Из скольких записей сложился итог. `со_значением` точнее `строк`: складываются
    # только записи с величиной, и именно их число решает, меняет ли выбор предмета ответ.
    counted = счёт.get("со_значением")
    if counted is None:
        counted = счёт.get("строк", d.get("rows", 0))
    need, slots, why = serene_enough.verdict_after(
        intent, facts, counted, entity_has_dates(d.get("focus")))
    if not need:
        return out
    ask = _need_clarify(question, slots, why,
                        dict(d, шаг="достаточность после счёта"))
    return ask or out


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
            # `answer_checked`, а не `answer`: вокруг ответа стоит шаг «достаточен ли
            # вопрос» (05.08). Он же зовёт `answer` внутри, поэтому путь ответа прежний.
            out = answer_checked(question, focus=focus, measure_pick=measure_pick,
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
                out = stale_note(out, age, STALE_WARN_SEC, STALE_TEXT)
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
