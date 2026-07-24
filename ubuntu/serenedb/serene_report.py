#!/usr/bin/env python3
"""
serene_report — чистая логика умного NL->запрос по витрине SereneDB (без хардкода отчётов).
Делится между CLI (report_query.py) и MCP-сервером (mcp_reports.py).

Принцип (docs/SERENEDB.md): LLM НЕ пишет числа — он превращает вопрос в read-only SELECT по
РЕАЛЬНОЙ (интроспектированной) схеме с примерами значений; код валидирует read-only; SereneDB
считает; наверх — результат + САМ SQL (прозрачность трактовки, страховка от «понял не так»).

Env: SERENEDB_DSN (default 'host=127.0.0.1 port=7890 user=postgres'),
     DEEPSEEK_API_KEY (обяз.), DEEPSEEK_BASE (default https://api.deepseek.com).
"""
import json, os, re, subprocess, urllib.error, urllib.request

DSN = os.environ.get("SERENEDB_DSN", "host=127.0.0.1 port=7890 user=postgres")
DS_BASE = os.environ.get("DEEPSEEK_BASE", "https://api.deepseek.com").rstrip("/")
# Каталог для запирания ФС в сессии выполнения LLM-SQL (защита в глубину под FS-денайлистом валидатора).
# РЕАЛЬНЫЙ каталог данных: движок игнорирует несуществующий путь (→ allow-all), а каталог данных всегда
# есть → блокирует /etc//root/секреты; загрузчик-CSV в нём — та же витрина (безвредно). enable_external_access
# НЕ трогаем: он ГЛОБАЛЬНЫЙ one-way латч (ломает загрузчик), проверено. allowed_directories — сессионный.
# Движковый лимит доступа к ФС (allowed_directories/enable_external_access) НЕДОСТИЖИМ для роли serene_ro
# на этой сборке SereneDB: enable_external_access — глобальный one-way латч (ломает загрузчик); allowed_
# directories под ro — no-op, SET GLOBAL не держит на свежих коннектах, ALTER ROLE не применяется, флага
# конфига нет. Энфорсмент доступа к файлам — ТОЛЬКО валидатор (FS_ACCESS денайлист, проверено). Пункт для
# фаундеров SereneDB — см. docs. Разнос ролей (positive control) над resolver_index — рабочий, ниже.
# Отдельная роль serene_resolver читает resolver_index, а не serene_ro → LLM-SQL под serene_ro не дотянется
# к служебному индексу даже в обход валидатора. Пароль — через env подпроцесса (не в conninfo/ps).
# Фолбэк на DSN — обратная совместимость (если роль не заведена, семантика тихо деградирует до лексики).
RESOLVER_DSN = os.environ.get("RESOLVER_DSN", DSN)
RESOLVER_PW = os.environ.get("RESOLVER_PW")

# Qwen-эмбеддер — РОВНО как в braine: DashScope text-embedding-v4 @ 1536 (ollama не используем).
EMBED_URL = os.environ.get("ALIBABA_EMBED_URL", "").rstrip("/")
EMBED_KEY = os.environ.get("ALIBABA_API_KEY", "")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "text-embedding-v4")
EMBED_DIM = int(os.environ.get("EMBED_DIM", "1536"))


def embed(texts):
    """Векторизация Qwen text-embedding-v4 @ EMBED_DIM (как braine). texts: list[str] -> list[vec]."""
    if not EMBED_URL or not EMBED_KEY or not texts:
        return []
    body = json.dumps({"model": EMBED_MODEL, "dimensions": EMBED_DIM, "input": texts}).encode()
    req = urllib.request.Request(
        f"{EMBED_URL}/embeddings", data=body,
        headers={"Authorization": f"Bearer {EMBED_KEY}", "Content-Type": "application/json"},
    )
    try:
        d = json.load(urllib.request.urlopen(req, timeout=40))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"embed HTTP {e.code}: {e.read().decode('utf-8', 'ignore')[:200]}")
    return [x["embedding"] for x in d.get("data", [])]


def _vec_literal(v):
    return "ARRAY[" + ",".join(f"{x:.6f}" for x in v) + f"]::FLOAT[{len(v)}]"
DS_KEY = os.environ.get("DEEPSEEK_API_KEY", "")

FORBIDDEN = re.compile(
    # 'replace' УБРАН — это строковая функция replace(), не запись (REPLACE INTO не начинается с SELECT,
    # его ловит структурная проверка + read-only роль). Остальное — операторы изменения/DDL/расширений.
    r"\b(insert|update|delete|drop|alter|create|truncate|grant|revoke|copy|attach|"
    r"detach|pragma|call|merge|vacuum|install|load)\b",
    re.I,
)
# Файловый доступ DuckDB: технически read-only, но читает ФАЙЛОВУЮ СИСТЕМУ сервера (утечка /etc/passwd,
# ключей и т.п.). Витрина — только опубликованные таблицы; табличные функции чтения файлов боту не нужны.
FS_ACCESS = re.compile(
    r"\b(read_csv|read_csv_auto|read_parquet|read_json|read_json_auto|read_json_objects|read_ndjson|"
    r"read_text|read_blob|sniff_csv|glob|parquet_scan|parquet_metadata|csv_scan|delta_scan|iceberg_scan)\b",
    re.I,
)


# Служебные/системные объекты: read-only роль имеет SELECT и на внутренний индекс резолвера, и на
# системные каталоги. Бизнес-бот их не запрашивает; LLM-запрос к ним = утечка внутренней структуры
# (resolver_index c эмбеддингами, конфиг движка, пути на диске, имя сервис-аккаунта). Режем на
# валидаторе. Внутренние запросы резолвера/get_schema идут МИМО validate() (это код, не LLM), поэтому
# продолжают работать.
INTERNAL_OBJECTS = re.compile(
    r"\b(resolver_index|information_schema|pg_settings|pg_catalog|pg_stat\w*|pg_roles|pg_authid|"
    r"pg_shadow|pg_user|pg_database|pg_tables|pg_read\w*|current_setting|current_database|"
    r"duckdb_settings|duckdb_secrets|duckdb_columns|duckdb_tables)\b",
    re.I,
)


def _strip_literals(sql):
    """Убрать содержимое строковых литералов, чтобы ключевое слово/«;» ВНУТРИ строки
    (LIKE '%truncate%', city='РОСТОВ; МОСКВА') не считалось оператором."""
    return re.sub(r"'(?:[^']|'')*'", "''", sql)


def psql(sql, extra=None, dsn=None, pgpass=None):
    cmd = ["psql", dsn or DSN, "-v", "ON_ERROR_STOP=1"] + (extra or [])
    env = {**os.environ, "PGPASSWORD": pgpass} if pgpass is not None else None  # пароль в env, не в ps
    return subprocess.run(cmd, input=sql, text=True, capture_output=True, env=env)


def sample_values(table, col, n=5):
    q = f'SELECT DISTINCT "{col}" FROM "{table}" WHERE "{col}" IS NOT NULL LIMIT {n};'
    r = psql(q, extra=["-tA"])
    if r.returncode != 0:
        return []
    return [v for v in (ln.strip() for ln in r.stdout.splitlines()) if v][:n]


def get_schema():
    # duckdb_columns(), а НЕ information_schema.columns: под read-only ролью SereneDB
    # information_schema.columns пуста, а duckdb_columns доступна. Таблицы витрины — в схеме public.
    sql = (
        "SELECT table_name, column_name, data_type FROM duckdb_columns() "
        "WHERE schema_name = 'public' AND table_name <> 'resolver_index' "  # служебный индекс резолвера скрыт от LLM
        "ORDER BY table_name, column_index;"
    )
    r = psql(sql, extra=["-tAF", "\t"])
    if r.returncode != 0:
        raise RuntimeError(f"schema error: {r.stderr}")
    cols_by_table = {}
    for line in r.stdout.splitlines():
        if not line.strip():
            continue
        t, c, dt = line.split("\t")
        cols_by_table.setdefault(t, []).append((c, dt))
    out = []
    for t, cols in cols_by_table.items():
        # число строк — фактические метаданные (как примеры значений), не хардкод. Помогает LLM
        # выбрать НУЖНУЮ таблицу при похожих именах (banks 2779 vs catalog_банки 1) и честно видеть,
        # что таблица пустая (не выдумывать данные, которых нет).
        n = psql(f'SELECT count(*) FROM "{t}"', ["-tA"]).stdout.strip() or "?"
        parts = []
        for c, dt in cols:
            desc = f"{c} {dt}"
            if any(k in dt.lower() for k in ("char", "text", "string")):
                ex = sample_values(t, c)
                if ex:
                    desc += " e.g. " + "|".join(ex)
            parts.append(desc)
        out.append(f"- {t} [строк: {n}]({', '.join(parts)})")
    return "\n".join(out)


# Резолвер: фаззи-термин вопроса -> ТОЧНОЕ значение колонки-измерения, чтобы LLM фильтровал точно даже
# на больших справочниках. Два ЯЗЫКО-НЕЙТРАЛЬНЫХ слоя (Фаза 4 — БЕЗ стоп-слов/стемминга под язык):
#   • лексический — подстрока (LIKE, кириллица работает через lower()) + jaro_winkler (опечатки/морфология
#     по общей похожести символов, префикс-взвешен);
#   • семантический — эмбеддинги Qwen (смысл/падежи/любой язык), порог косинуса (см. _semantic_into).
# Оба фильтруются порогами (лучше не подсказать, чем подставить чужое). Стоп-слова НЕ нужны: не-энтити
# слова не проходят порог. Никаких языковых списков/правил — переносится на любую базу/язык.


UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-")


def dim_columns(max_distinct=1500):
    """Низко-кардинальные текстовые колонки-ИЗМЕРЕНИЯ (city…), а не сущности-имена (description)
    и не GUID-ссылки (Ref_Key/Parent_Key — бессмысленны для фильтра по термину)."""
    r = psql(
        "SELECT table_name, column_name FROM duckdb_columns() "
        "WHERE schema_name='public' AND table_name <> 'resolver_index' AND lower(data_type) LIKE '%char%';",
        ["-tAF", "\t"],
    )
    out = []
    for line in r.stdout.splitlines():
        if not line.strip():
            continue
        t, c = line.split("\t")
        cnt = psql(f'SELECT count(DISTINCT "{c}") FROM "{t}";', ["-tA"]).stdout.strip()
        if not (cnt.isdigit() and 0 < int(cnt) <= max_distinct):
            continue
        sample = psql(f'SELECT "{c}" FROM "{t}" WHERE "{c}" IS NOT NULL LIMIT 1;', ["-tA"]).stdout.strip()
        if UUID_RE.match(sample):
            continue  # GUID-колонка — не измерение
        out.append((t, c))
    return out


def _lexical_into(hints, words, max_per_col, min_sim):
    for t, c in dim_columns():
        conds = []
        for w in words[:8]:
            wq = w.replace("'", "''")
            conds.append(f"lower(\"{c}\") LIKE '%{wq}%'")                            # подстрока (кириллица ок)
            conds.append(f"jaro_winkler_similarity(lower(\"{c}\"), '{wq}') > {min_sim}")  # фаззи (опечатки/морфология)
        q = f'SELECT DISTINCT "{c}" FROM "{t}" WHERE "{c}" IS NOT NULL AND ({" OR ".join(conds)}) LIMIT {max_per_col};'
        for v in psql(q, ["-tA"]).stdout.splitlines():
            if v.strip():
                hints.setdefault((t, c), []).append(v)


def _semantic_into(hints, words, min_cos=0.70):
    """Qwen-вектор: слово -> БЛИЖАЙШЕЕ значение-измерение в resolver_index (косинус, перебор).
    Порог 0.70 ВЫСОКИЙ намеренно (замер measure_resolver.py): на коротких токенах эмбеддинг ловит
    больше орфографию, чем гео-смысл, и низкий порог давал ЛОЖНЫЕ разрешения («Йоркшир»→Новошахтинск
    0.51, «казань»→Кандалакша 0.62). Верные совпадения — ≥0.72 (спб/москва/пятигорск), ложные ≤0.63,
    между ними и ставим отсечку. Легит-случаи («казань»/«питере») закрывают лексика + знания самой LLM.
    Лучше НЕ подсказать, чем подсказать ЧУЖОЙ город (тихо неверный ответ)."""
    if not EMBED_URL:
        return
    chk = psql("SELECT count(*) FROM resolver_index;", ["-tA"], dsn=RESOLVER_DSN, pgpass=RESOLVER_PW)
    if chk.returncode != 0 or not chk.stdout.strip().isdigit() or int(chk.stdout.strip()) == 0:
        return  # индекс не построен/нет доступа — тихо пропускаем (лексика всё равно работает)
    vecs = embed(words[:8])
    for w, v in zip(words[:8], vecs):
        q = (
            f"SELECT table_name, column_name, value, array_cosine_similarity(emb, {_vec_literal(v)}) sim "
            f"FROM resolver_index ORDER BY sim DESC LIMIT 1;"
        )
        for line in psql(q, ["-tAF", "\t"], dsn=RESOLVER_DSN, pgpass=RESOLVER_PW).stdout.splitlines():
            if not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) != 4:
                continue
            t, c, val, sim = parts
            try:
                if float(sim) >= min_cos:
                    lst = hints.setdefault((t, c), [])
                    if val not in lst:
                        lst.append(val)
            except ValueError:
                pass


def resolve_hints(question, max_per_col=5, min_sim=0.9):
    """Термины вопроса -> ТОЧНЫЕ значения колонок-измерений. Лексика (падежи/опечатки) + Qwen-вектор
    (смысл: «питер»->«Санкт-Петербург»). Подсказка для LLM. Векторный слой активен, если построен
    resolver_index (build_resolver_index.py); иначе — только лексика."""
    # ≥3 word-символа ЛЮБОГО языка (\w unicode) — ловим и «спб»/«мск». Без стоп-листов: не-энтити слова
    # не проходят порог (jaro/cosine). Язык-нейтрально.
    words = re.findall(r"\w{3,}", str(question).lower(), re.UNICODE)
    if not words:
        return ""
    hints = {}
    try:
        _lexical_into(hints, words, max_per_col, min_sim)
    except Exception:  # noqa: BLE001
        pass
    try:
        _semantic_into(hints, words)
    except Exception:  # noqa: BLE001
        pass
    return "\n".join(f"{t}.{c}: " + ", ".join(dict.fromkeys(vals)) for (t, c), vals in hints.items())


def text_columns():
    """Имена ТЕКСТОВЫХ колонок витрины (нижним регистром). Идентификаторы/реквизиты/метки (номер счёта,
    ИНН, БИК, код, название…) — числовая свёртка таких полей БЕССМЫСЛЕННА как показатель. Тип берём из
    интроспекции (факт схемы), не из имён — общий сигнал без сопоставления бизнес-терминов."""
    # lower() делаем в Python: DuckDB lower() НЕ лоуэркейсит кириллицу (ASCII-only), а имена колонок 1С
    # кириллические (НомерСчета) — иначе сравнение с Python-.lower() промахивается.
    r = psql(
        "SELECT DISTINCT column_name FROM duckdb_columns() WHERE schema_name='public' "
        "AND lower(data_type) ~ 'char|text|string|varchar';", ["-tA"])
    return {v.strip().lower() for v in r.stdout.splitlines() if v.strip()}


_NUM = r"(?:\w*int\w*|double|float|real|decimal|numeric|dec|hugeint)"


def measure_caveat(sql, text_cols=None):
    """Прозрачность трактовки против «выдуманной метрики»: если запрос ЧИСЛОВО сворачивает (SUM/AVG)
    или приводит-к-числу (CAST/::) ТЕКСТОВУЮ колонку-реквизит — итог не является достоверным денежным/
    количественным показателем (напр. AVG(CAST(НомерСчёта AS HUGEINT)) выдаётся за «оборот»). Возвращаем
    ПРЕДУПРЕЖДЕНИЕ (не блок — число «настоящее», врёт лишь трактовка), чтобы человек видел подмену.
    Схемо-типовой сигнал, БЕЗ карты «прибыль→колонка» (не хардкод). LENGTH(...)/COUNT(...) не триггерят."""
    cols = text_cols if text_cols is not None else text_columns()
    if not cols:
        return ""
    s = _strip_literals(sql)
    hits = set()
    pats = [
        rf"\b(?:sum|avg)\(\s*(?:\w+\.)?\"?(\w+)\"?\s*\)",          # SUM/AVG(текст_колонка)
        rf"cast\(\s*(?:\w+\.)?\"?(\w+)\"?\s+as\s+{_NUM}\b",        # CAST(текст AS число)
        rf"(?:\w+\.)?\"?(\w+)\"?::\s*{_NUM}\b",                    # текст::число
    ]
    for p in pats:
        for m in re.finditer(p, s, re.I):
            if m.group(1).lower() in cols:
                hits.add(m.group(1))
    if not hits:
        return ""
    return ("⚠ Внимание: показатель посчитан по текстовому полю (" + ", ".join(sorted(hits)) +
            ") — это реквизит/идентификатор, а не числовая величина; как денежный/количественный "
            "показатель результат недостоверен.")


def metric_critic(question, schema, sql):
    """Grounding-критик выдуманной метрики (Фаза 3.2): 2-й LLM-проход судит, посчитан ли ответ по РЕАЛЬНОЙ
    величине из схемы, или подставлен суррогат (усреднение/сумма идентификатора; подмена метрики на COUNT
    элемента справочника — при том что колонки-величины под запрос в схеме НЕТ). Общий — LLM рассуждает о
    ФАКТИЧЕСКОЙ схеме, без карты «термин→колонка». Возвращает caveat или ''. Env `METRIC_CRITIC=0` выключает.
    Дешёвая первая линия — детерминированный measure_caveat; критик добивает семантические подмены."""
    if os.environ.get("METRIC_CRITIC", "1") == "0" or not DS_KEY:
        return ""
    sysp = (
        "Ты аудитор SQL-аналитики. Дана СХЕМА, ВОПРОС и SQL. Ответь СТРОГО JSON "
        '{"grounded":true|false,"why":"кратко"}. grounded=false ТОЛЬКО когда запрошена числовая ВЕЛИЧИНА '
        "(сумма/оборот/прибыль/выручка/остаток/средний чек…), а SQL считает её по НЕподходящему полю — "
        "усредняет/суммирует идентификатор (номер счёта/ИНН/код) ИЛИ подменяет на COUNT элемента справочника, "
        "и при этом реальной колонки-величины под запрос в схеме НЕТ. Если метрика адекватна данным ИЛИ "
        "вопрос не про числовую величину — grounded=true. Без объяснений вне JSON."
    )
    user = f"СХЕМА:\n{schema}\n\nВОПРОС: {question}\n\nSQL:\n{sql}\n\nJSON:"
    try:
        body = json.dumps({"model": "deepseek-chat", "temperature": 0, "messages": [
            {"role": "system", "content": sysp}, {"role": "user", "content": user}]}).encode()
        req = urllib.request.Request(
            f"{DS_BASE}/chat/completions", data=body,
            headers={"Authorization": f"Bearer {DS_KEY}", "Content-Type": "application/json"})
        txt = json.load(urllib.request.urlopen(req, timeout=40))["choices"][0]["message"]["content"]
        m = re.search(r"\{.*\}", txt, re.S)
        d = json.loads(m.group(0)) if m else {}
        if d.get("grounded") is False:
            return ("⚠ Внимание: показатель, вероятно, не отражает запрошенную величину ("
                    + str(d.get("why", ""))[:150] + ") — проверьте трактовку.")
    except Exception:  # noqa: BLE001 — критик не должен ронять отчёт
        return ""
    return ""


def gen_sql(question, schema, hints=""):
    if not DS_KEY:
        raise RuntimeError("нет DEEPSEEK_API_KEY")
    # Промт ЯЗЫКО-НЕЙТРАЛЬНЫЙ (Фаза 4.2): инструкции на English (LLM их понимает лучше всего), а ВОПРОС
    # может быть на любом языке. Никаких допущений про язык базы — переносится на любую 1С/локаль.
    sys_prompt = (
        "You are a SQL analyst for SereneDB (DuckDB-compatible dialect, Postgres wire protocol). "
        "Given the SCHEMA and QUESTION, return EXACTLY ONE read-only SELECT (or WITH...SELECT). "
        "Use ONLY tables and columns present in the SCHEMA — never invent them. Respect the VALUE "
        "FORMAT shown in examples (e.g. ...). If RELEVANT VALUES are provided, filter EXACTLY by them "
        "(question term → exact stored value). No prose, no markdown, no trailing ';'. Reasonable LIMIT "
        "for 'top N'. The question may be in any language; reply with the SQL only."
    )
    user = f"SCHEMA:\n{schema}\n"
    if hints:
        user += f"\nRELEVANT VALUES (question term → exact stored values in data, use them to filter):\n{hints}\n"
    user += f"\nQUESTION: {question}\n\nSQL:"
    body = json.dumps({
        "model": "deepseek-chat",
        "temperature": 0,
        "messages": [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user},
        ],
    }).encode()
    req = urllib.request.Request(
        f"{DS_BASE}/chat/completions", data=body,
        headers={"Authorization": f"Bearer {DS_KEY}", "Content-Type": "application/json"},
    )
    resp = json.load(urllib.request.urlopen(req, timeout=60))
    sql = resp["choices"][0]["message"]["content"].strip()
    return re.sub(r"^```[a-z]*\s*|\s*```$", "", sql, flags=re.I).strip().rstrip(";").strip()


MAX_SQL_LEN = 6000  # патологическая генерация LLM (repetition-loop, тысячи вложенных функций) роняла
# соединение SereneDB. Осмысленный аналитический SELECT в это укладывается с запасом; всё длиннее —
# почти наверняка деградация, до БД НЕ пускаем (защита от падения сервера).


# Скалярные служебные функции (утечка конфигурации/окружения). AST-allow-list проверяет ТАБЛИЦЫ, а это
# скалярные функции (могут быть в SELECT без FROM) — их allow-list не покрывает, поэтому тонкий денайлист.
# Это ФУНКЦИИ движка, не бизнес-логика (бизнес-запрос их не использует) — не «хардкод под базу».
_INTERNAL_FUNCS = re.compile(r"\b(current_setting|current_database|getenv|pg_read\w*)\b", re.I)


def _validate_fallback(sql):
    """Запасной валидатор на денайлистах — если AST-разбор (json_serialize_sql) недоступен."""
    if not re.match(r"^\s*(select|with)\b", sql, re.I):
        return "не SELECT/WITH"
    bare = _strip_literals(sql)
    if ";" in bare:
        return "несколько операторов"
    if FORBIDDEN.search(bare):
        return "запрещённое ключевое слово (изменение данных)"
    if FS_ACCESS.search(bare):
        return "запрещён доступ к файловой системе (табличная функция чтения файлов)"
    if INTERNAL_OBJECTS.search(bare):
        return "запрещён доступ к служебным/системным объектам"
    return None


def _schema_tables():
    """Имена таблиц ВИТРИНЫ (allow-list). lower() в Python (DuckDB lower() не трогает кириллицу)."""
    r = psql("SELECT DISTINCT table_name FROM duckdb_columns() WHERE schema_name='public' "
             "AND table_name <> 'resolver_index'", ["-tA"])
    return {t.strip().lower() for t in r.stdout.splitlines() if t.strip()}


def _ast_relations(sql):
    """Разбор SQL в AST (json_serialize_sql) — БЕЗ regex. Возвращает:
      None                         — функция недоступна/сбой вызова → caller делает fallback;
      {'error': True}              — не одиночный читающий запрос (DML/DDL/несколько операторов/синтаксис);
      {'tables','tf','ctes'}       — множество BASE_TABLE, флаг табличной функции, имена CTE."""
    lit = "'" + sql.replace("'", "''") + "'"
    r = psql(f"SELECT json_serialize_sql({lit})", ["-tA"])
    if r.returncode != 0 or not r.stdout.strip():
        return None
    try:
        doc = json.loads(r.stdout.strip())
    except Exception:  # noqa: BLE001
        return None
    if doc.get("error"):
        return {"error": True}
    tables, ctes, tf = set(), set(), [False]

    def walk(n):
        if isinstance(n, dict):
            t = n.get("type")
            if t == "BASE_TABLE" and n.get("table_name"):
                tables.add(str(n["table_name"]).lower())
            elif t == "TABLE_FUNCTION":
                tf[0] = True
            cm = n.get("cte_map")
            if isinstance(cm, dict):
                for e in cm.get("map", []):
                    if isinstance(e, dict) and e.get("key"):
                        ctes.add(str(e["key"]).lower())
            for v in n.values():
                walk(v)
        elif isinstance(n, list):
            for v in n:
                walk(v)

    walk(doc)
    return {"tables": tables, "tf": tf[0], "ctes": ctes}


def validate(sql):
    """ALLOW-LIST через AST (Фаза 3.1): по построению пропускаем ТОЛЬКО одиночный SELECT/WITH, читающий
    ИСКЛЮЧИТЕЛЬНО таблицы витрины (+ свои CTE), без табличных функций (файлы/внешнее) и служебных объектов.
    Общий контроль без списков имён/слов — переносится на любую базу. Денайлисты — только fallback."""
    if len(sql) > MAX_SQL_LEN:
        return f"SQL слишком длинный ({len(sql)}>{MAX_SQL_LEN}) — вероятно патологическая генерация"
    info = _ast_relations(sql)
    if info is None:
        return _validate_fallback(sql)  # AST недоступен — запасной денайлист
    if info.get("error"):
        return "не одиночный читающий запрос (DML/DDL/несколько операторов/синтаксис)"
    if info["tf"]:
        return "запрещена табличная функция (доступ к файлам/внешнему)"
    allowed = _schema_tables() | info["ctes"]
    bad = sorted(t for t in info["tables"] if t not in allowed)
    if bad:
        return "обращение к объекту вне схемы витрины: " + ", ".join(bad)
    if _INTERNAL_FUNCS.search(_strip_literals(sql)):
        return "запрещена служебная функция (утечка конфигурации)"
    return None


def run_report(question, max_rows=50):
    """NL -> {question, sql, error?, columns, rows, n}. Числа — из SQL, не из LLM."""
    schema = get_schema()
    if not schema.strip():
        return {"question": question, "sql": None, "error": "витрина пуста (нет таблиц)"}
    try:
        hints = resolve_hints(question)  # Этап 3: фаззи-резолвер терминов -> точные значения
    except Exception:  # noqa: BLE001
        hints = ""
    sql = gen_sql(question, schema, hints)
    err = validate(sql)
    if err:
        return {"question": question, "sql": sql, "error": f"отклонено валидатором: {err}"}
    # подмена метрики: дешёвый детерминированный measure_caveat (типовой), иначе — grounding-критик (LLM)
    caveat = measure_caveat(sql) or metric_critic(question, schema, sql)
    # обёртка-подзапрос: стабильные заголовки + LIMIT независимо от формы sql. Тянем max_rows+1, чтобы
    # ЗАМЕТИТЬ обрезку и честно о ней сообщить (а не молча показать часть как всё — баг «50 из 77»).
    wrapped = f"SELECT * FROM (\n{sql}\n) _q LIMIT {max_rows + 1}"
    r = psql(wrapped, extra=["-A", "-F", "\t"])  # без -t: первая строка = заголовки
    if r.returncode != 0:
        return {"question": question, "sql": sql, "error": f"ошибка выполнения: {r.stderr.strip()[:300]}"}
    data = [ln for ln in r.stdout.splitlines() if ln != "" and not re.match(r"^\(\d+ rows?\)$", ln.strip())]
    if not data:
        return {"question": question, "sql": sql, "columns": [], "rows": [], "n": 0, "caveat": caveat}
    columns = data[0].split("\t")
    rows = [ln.split("\t") for ln in data[1:]]
    truncated = len(rows) > max_rows
    if truncated:
        rows = rows[:max_rows]
    return {"question": question, "sql": sql, "columns": columns, "rows": rows, "n": len(rows),
            "truncated": truncated, "caveat": caveat}


def _num(x):
    try:
        return float(str(x).replace(" ", "").replace(" ", "").replace(",", "."))
    except Exception:
        return None


def render_chart(result, max_bars=25):
    """Числа отчёта -> PNG (bar). Матч: >=2 колонки, последняя числовая, немного строк.
    Числа берём из результата SQL (достоверны). matplotlib импортируем лениво (CLI не тянет его)."""
    rows = result.get("rows") or []
    cols = result.get("columns") or []
    if result.get("error") or len(cols) < 2 or not rows or len(rows) > max_bars:
        return None
    labels = [str(r[0]) for r in rows]
    vals = [_num(r[-1]) for r in rows]
    if any(v is None for v in vals):
        return None  # не числовой срез — график не строим (отдадим таблицей)
    import io
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8, max(2.2, 0.45 * len(rows) + 1)))
    ax.barh(range(len(rows)), vals, color="#4C78A8")
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels(labels)
    ax.invert_yaxis()
    ax.set_xlabel(cols[-1])
    title = (result.get("question") or "").strip()
    if title:
        ax.set_title(title[:90])
    for i, v in enumerate(vals):
        ax.text(v, i, f" {v:g}", va="center", fontsize=9)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120)
    plt.close(fig)
    return buf.getvalue()


def format_table(result, show=30, show_sql=True):
    """show_sql=True — для CLI/владельца (видно SQL-трактовку). show_sql=False — клиентский
    вывод бота: только чистая таблица, без SQL/служебного (SQL логируется серверно отдельно)."""
    if result.get("error"):
        base = f"[ОТЧЁТ НЕ ВЫПОЛНЕН: {result['error']}]"
        return base + (f"\nТрактовка (SQL): {result.get('sql') or '—'}" if show_sql else "")
    cols = result.get("columns") or []
    grid = ([cols] if cols else []) + result["rows"][:show]
    widths = []
    for r in grid:
        for i, c in enumerate(r):
            w = len(str(c))
            widths.append(w) if i >= len(widths) else widths.__setitem__(i, max(widths[i], w))
    lines = ["  ".join(str(c).ljust(widths[i]) for i, c in enumerate(r)) for r in grid]
    if cols and lines:
        lines.insert(1, "  ".join("-" * w for w in widths))
    more = "" if result["n"] <= show else f"\n… ещё {result['n'] - show} строк"
    if result.get("truncated"):  # выборка была обрезана лимитом — честно сообщаем, а не выдаём часть за всё
        more += f"\n⚠ показаны первые {result['n']} — в выборке есть ещё строки (уточните фильтр/период)"
    if result.get("caveat"):  # подмена метрики — предупреждаем и клиента (не только владельца в логе SQL)
        more += "\n" + result["caveat"]
    body = "\n".join(lines) + more
    if show_sql:
        body += f"\n\nСтрок: {result['n']}\nТрактовка (SQL): {result['sql']}"
    return body
