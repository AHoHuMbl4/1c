"""Zone 01: Инфра, TRACE, LLM (infra-trace-llm)."""
from __future__ import annotations

from ask._imports import *
from ask._wire import register_zone, apply_bindings

DSN = os.environ.get("SERENEDB_DSN_RO")
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
MONEY_UNIT = os.environ.get("ASK_MONEY_UNIT", "")

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

# Сквозной request-id: один на пользовательский вопрос (включая decision_id/memory).
# Рождается на краю (verify-плагин); без него сервис генерирует сам. В stderr — только
# rid+слой+шаг+мс+статус, без текста вопроса (приватность).
_rid_ctx = contextvars.ContextVar("ask_rid", default="")


def _new_rid():
    return secrets.token_hex(8)[:16]


def _rid_norm(rid):
    rid = (rid or "").strip()
    if not rid:
        return _new_rid()
    rid = "".join(c for c in rid if c.isalnum())[:16]
    return rid or _new_rid()


def _rid_get():
    return _rid_ctx.get() or ""


def _rid_enter(rid=None):
    rid = _rid_norm(rid)
    _rid_ctx.set(rid)
    return rid


def _trace_write(layer, step, ms, status="ok"):
    if not TRACE:
        return
    sys.stderr.write("TRACE %s %s %s %d %s\n" % (
        _rid_get() or "-", layer, step, int(ms), status))

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
# vLLM/Qwen: thinking выключается через extra_body, а не полем DeepSeek.
# Включать только на инстансе с ASK-моделью qwen — DeepSeek extra_body игнорирует.
ASK_THINKING_OFF_BODY = os.environ.get("ASK_THINKING_OFF_BODY", "") in ("1", "true", "yes")

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

# Штатный путь вопрос-эмбеддинга через ai_embed (п. 7 TARGET). Умолч. 0 — прежний HTTP.
# Имя секрета — из env (как embed_missing.sh / build.sh), не из кода.
def _embed_secret_name_from_env():
    raw = (os.environ.get("EMBED_SECRET") or os.environ.get("EMBED_SECRETS") or "").strip()
    if raw:
        return raw.split()[0]
    return "ask_embed"


EMBED_SECRET_NAME = _embed_secret_name_from_env()
EMBED_PATH = os.environ.get("EMBED_PATH", "/v1/embeddings")
ASK_EMBED_NATIVE = os.environ.get("ASK_EMBED_NATIVE", "0") == "1"
_EMBED_SECRET_LOCK = threading.Lock()
_EMBED_SECRET_READY = False


def _reload_embed_native_env():
    global EMBED_SECRET_NAME, EMBED_PATH, ASK_EMBED_NATIVE, _EMBED_SECRET_READY, EMBED_DIM
    EMBED_SECRET_NAME = _embed_secret_name_from_env()
    EMBED_PATH = os.environ.get("EMBED_PATH", "/v1/embeddings")
    ASK_EMBED_NATIVE = os.environ.get("ASK_EMBED_NATIVE", "0") == "1"
    EMBED_DIM = int(os.environ.get("EMBED_DIM", "1024"))
    _EMBED_SECRET_READY = False


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
    if not DSN:
        raise RuntimeError("SERENEDB_DSN_RO is required")
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


def _embed_host_base():
    raw = (os.environ.get("EMBED_HOST") or EMBED_URL or "").strip()
    raw = raw.strip('"').strip("'")
    return raw.rstrip("/")


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


def _src_tag(src):
    """Короткое имя сущности для sources; безопасно при src=None (post-gate)."""
    if not src:
        return ""
    return src.split("_", 1)[1] if "_" in src else src


def _fmt_gate_bad(v):
    """Строковое представление элемента отказа гейтa (float → _fmt)."""
    if isinstance(v, float):
        return _fmt(v)
    if isinstance(v, int):
        return str(v)
    return str(v)


def _gate_bad_preview(bad, limit=60):
    """Срез первой причины гейта для шага/журнала (str + limit)."""
    if not bad:
        return "—"
    return _fmt_gate_bad(bad[0])[:limit]


def _fmt_human(v):
    """То же _fmt, разряды неразрывным пробелом — как подстановка гейта."""
    if isinstance(v, (list, dict, tuple)):
        return str(v)
    out = _fmt(v)
    if not isinstance(out, str):
        out = str(out)
    head, _, frac = out.partition(".")
    neg, head = (head[:1] == "-"), head.lstrip("-")
    if not head:
        head = "0"
    grouped = "\u00a0".join(
        [head[:len(head) % 3 or 3]] + [head[i:i + 3] for i in
                                       range(len(head) % 3 or 3, len(head), 3)])
    return ("-" if neg else "") + grouped + (("." + frac) if frac else "")


_token_acc = contextvars.ContextVar("token_acc", default=None)


class _TokenAcc:
    __slots__ = ("calls", "in_t", "out_t", "cache_hit", "cache_miss",
                 "has_hit", "has_miss")

    def __init__(self):
        self.calls = 0
        self.in_t = 0
        self.out_t = 0
        self.cache_hit = 0
        self.cache_miss = 0
        self.has_hit = False
        self.has_miss = False

    def add(self, usage):
        self.calls += 1
        self.in_t += int(usage.get("prompt_tokens") or 0)
        self.out_t += int(usage.get("completion_tokens") or 0)
        if "prompt_cache_hit_tokens" in usage:
            self.has_hit = True
            self.cache_hit += int(usage.get("prompt_cache_hit_tokens") or 0)
        if "prompt_cache_miss_tokens" in usage:
            self.has_miss = True
            self.cache_miss += int(usage.get("prompt_cache_miss_tokens") or 0)

    def diag_dict(self):
        d = {"calls": self.calls, "in": self.in_t, "out": self.out_t}
        if self.has_hit:
            d["cache_hit"] = self.cache_hit
        if self.has_miss:
            d["cache_miss"] = self.cache_miss
        return d


def _token_acc_start():
    _token_acc.set(_TokenAcc())


def _token_acc_record(usage):
    """Один вызов ds_chat: накопить usage и строку в journald (без текста вопроса)."""
    if not isinstance(usage, dict):
        return
    acc = _token_acc.get()
    if acc is None:
        return
    acc.add(usage)
    parts = ["in=%d" % int(usage.get("prompt_tokens") or 0),
             "out=%d" % int(usage.get("completion_tokens") or 0)]
    if "prompt_cache_hit_tokens" in usage:
        parts.append("hit=%d" % int(usage.get("prompt_cache_hit_tokens") or 0))
    if "prompt_cache_miss_tokens" in usage:
        parts.append("miss=%d" % int(usage.get("prompt_cache_miss_tokens") or 0))
    _trace_write("model", "TOKENS", 0, " ".join(parts))


def _diag_pack(diag, **extra):
    """Копия diag для ответа; сумма токенов ds_chat за один answer/answer_checked."""
    d = dict(diag or {}, **extra)
    acc = _token_acc.get()
    if acc and acc.calls:
        d["tokens"] = acc.diag_dict()
    return d


def _ds_chat_content(data):
    """Текст ответа модели; usage учитывается, отсутствие choices/usage — не ошибка."""
    if not isinstance(data, dict):
        return None
    usage = data.get("usage")
    if isinstance(usage, dict):
        _token_acc_record(usage)
    choices = data.get("choices")
    if not choices or not isinstance(choices, list):
        return None
    msg = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(msg, dict):
        return None
    return msg.get("content")


def _ds_chat_body(messages, temperature=0, max_tokens=900):
    body = {"model": DS_MODEL, "temperature": temperature,
            "max_tokens": max_tokens, "messages": messages}
    if DS_THINKING:
        body["thinking"] = {"type": DS_THINKING}
    if ASK_THINKING_OFF_BODY:
        # vLLM Qwen: kwargs на верхнем уровне тела; extra_body игнорируется [замер 17.08].
        body["chat_template_kwargs"] = {"enable_thinking": False}
    return body


def ds_chat_post(body):
    req = urllib.request.Request(DS_BASE + "/v1/chat/completions",
                                 data=json.dumps(body).encode(), method="POST")
    req.add_header("Authorization", "Bearer " + DS_KEY)
    req.add_header("Content-Type", "application/json")
    if EMBED_UA:
        req.add_header("User-Agent", EMBED_UA)
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())


def ds_chat(messages, temperature=0, max_tokens=900):
    return _ds_chat_content(ds_chat_post(_ds_chat_body(messages, temperature, max_tokens)))


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


def _ensure_embed_secret():
    """TEMPORARY SECRET openai из env, если в движке ещё нет имени EMBED_SECRET_NAME."""
    global _EMBED_SECRET_READY
    if _EMBED_SECRET_READY:
        return
    with _EMBED_SECRET_LOCK:
        if _EMBED_SECRET_READY:
            return
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", EMBED_SECRET_NAME or ""):
            raise RuntimeError("ASK_EMBED_NATIVE: недопустимое EMBED_SECRET")
        try:
            rows = psql("SELECT 1 FROM duckdb_secrets() WHERE name = %s LIMIT 1"
                          % lit(EMBED_SECRET_NAME))
            if rows:
                _EMBED_SECRET_READY = True
                return
        except RuntimeError:
            pass
        host = _embed_host_base()
        if not host:
            raise RuntimeError("ASK_EMBED_NATIVE: не задан EMBED_HOST/EMBED_BASE_URL")
        path = (EMBED_PATH or "/v1/embeddings").strip()
        sec_sql = ("CREATE OR REPLACE TEMPORARY SECRET %s "
                   "(TYPE openai, api_key %s, base_url %s, embeddings_path %s)"
                   % (EMBED_SECRET_NAME, lit(EMBED_KEY or ""), lit(host), lit(path)))
        try:
            psql(sec_sql)
        except RuntimeError as e:
            msg = str(e)
            raise RuntimeError("ASK_EMBED_NATIVE: секрет эмбеддера недоступен: %s"
                               % msg[:200]) from e
        _EMBED_SECRET_READY = True


def _embed_one_native(text):
    """Один вектор вопроса через ai_embed; secret/model — литералы (требование движка)."""
    _ensure_embed_secret()
    model_lit = EMBED_MODEL.replace("'", "''")
    secret_lit = EMBED_SECRET_NAME.replace("'", "''")
    sql = ("SELECT to_json(ai_embed(%s, '%s', '%s')::FLOAT[%d])"
           % (lit(text), model_lit, secret_lit, EMBED_DIM))
    last = None
    rows = None
    for attempt in range(EMB_RETRY + 1):
        try:
            rows = psql(sql)
            break
        except RuntimeError as e:
            last = e
            msg = str(e).lower()
            if attempt < EMB_RETRY and ("timeout" in msg or "connect" in msg
                                        or "temporarily" in msg):
                time.sleep(EMB_RETRY_PAUSE * (2 ** attempt))
                continue
            raise
    else:
        raise RuntimeError("ai_embed недоступен: %s" % type(last).__name__)
    if not rows or not rows[0]:
        raise RuntimeError("ai_embed вернул пустой ответ")
    try:
        vec = json.loads(rows[0][0])
    except (json.JSONDecodeError, TypeError, IndexError) as e:
        raise RuntimeError("ai_embed: битый JSON вектора") from e
    if not isinstance(vec, list):
        raise RuntimeError("ai_embed: ожидали массив FLOAT")
    if len(vec) != EMBED_DIM:
        raise RuntimeError("ai_embed: размерность %d, ожидали %d"
                           % (len(vec), EMBED_DIM))
    return [float(x) for x in vec]


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
    if ASK_EMBED_NATIVE:
        vec = _embed_one_native(text)
        if len(_EMB_ONE_CACHE) >= EMB_ONE_CACHE_MAX:
            _EMB_ONE_CACHE.clear()
        _EMB_ONE_CACHE[text] = vec
        return vec
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
             by permissions, how complete or fresh the data is. Default to \\"data\\"",
  "action_class": "\\"event\\" when the question is about actions, transactions or
             movements that happen over time (buying, selling, shipping, paying,
             hiring, producing, writing off) — even without an explicit verb, if the
             question asks WHO or WHAT participated in such activity. \\"object\\" when
             it asks about a static set of records (how many items/parties exist,
             are listed, are in a catalog). \\"none\\" when neither applies",
  "action_axis": "short noun naming who or what acts in the question, in its language, or null"
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
_ACTION_CLASS_OK = ("event", "object", "none")
_INTENT_FIELDS = ("terms", "kind", "measure", "want", "period", "period2", "amount",
                  "about", "action_class", "action_axis")
# Сколько прогонов разбора допустимо на один вопрос и какой отрыв лидера считается
# согласием. 1 прогон — прежнее поведение. Это бюджет ТОЧНОСТИ входа, а не подстройка
# под базу: от данных и от языка он не зависит.
INTENT_MAX_TOKENS = int(os.environ.get("ASK_INTENT_MAX_TOKENS", "400"))
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
# Ф6.3: query-side `solr_synonyms` рядом со стеммингом (docs/F6_SYNONYMS_FACTS.md §6).
# Умолч. выкл.; имя словаря без дефолта — карта правил в БД, не списки слов в коде.
ASK_SOLR_SYNONYMS = os.environ.get("ASK_SOLR_SYNONYMS", "0") == "1"
ASK_SOLR_SYNONYMS_DICT = os.environ.get("ASK_SOLR_SYNONYMS_DICT", "")



register_zone('ask.z01_infra_trace_llm', globals())
