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


def _strip_literals(sql):
    """Убрать содержимое строковых литералов, чтобы ключевое слово/«;» ВНУТРИ строки
    (LIKE '%truncate%', city='РОСТОВ; МОСКВА') не считалось оператором."""
    return re.sub(r"'(?:[^']|'')*'", "''", sql)


def psql(sql, extra=None):
    cmd = ["psql", DSN, "-v", "ON_ERROR_STOP=1"] + (extra or [])
    return subprocess.run(cmd, input=sql, text=True, capture_output=True)


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


# Семантический резолвер (Этап 3), v1 — ЛЕКСИЧЕСКИЙ (fuzzy) поверх SereneDB.
# Задача: фаззи-термин из вопроса («ростов», «москвы») -> ТОЧНОЕ значение в данных («Г. РОСТОВ-НА-ДОНУ»),
# чтобы LLM фильтровал по точному значению даже на больших справочниках (когда sample-values не влезут).
# Ловит опечатки/падежи/частичные/регистр (LIKE + jaro_winkler). Чисто-семантику («питер»→«СПб»)
# закроет слой на эмбеддингах+HNSW, когда будет reachable-эмбеддер (сейчас .38:8083 с .42 недоступен).
RU_STOP = {
    "сколько", "покажи", "дай", "топ", "самых", "больше", "меньше", "какой", "какие", "что",
    "как", "все", "всего", "по", "за", "на", "из", "для", "это", "есть", "нет", "мне", "отчет",
    "отчёт", "график", "таблицу", "таблица", "список", "штук", "года", "год", "лет", "месяц",
    "месяцев", "город", "городов", "городам", "количество", "число", "сумма", "итого",
}


def _stem(w):
    return w[:-2] if len(w) > 5 else w  # грубый стем под русские падежи (ростове->росто, москвы->моск)


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
            sq = _stem(w).replace("'", "''")
            conds.append(f"lower(\"{c}\") LIKE '%{wq}%'")
            conds.append(f"lower(\"{c}\") LIKE '%{sq}%'")
            conds.append(f"jaro_winkler_similarity(lower(\"{c}\"), '{wq}') > {min_sim}")
        q = f'SELECT DISTINCT "{c}" FROM "{t}" WHERE "{c}" IS NOT NULL AND ({" OR ".join(conds)}) LIMIT {max_per_col};'
        for v in psql(q, ["-tA"]).stdout.splitlines():
            if v.strip():
                hints.setdefault((t, c), []).append(v)


def _semantic_into(hints, words, min_cos=0.5):
    """Qwen-вектор (v2): слово -> БЛИЖАЙШЕЕ значение-измерение в resolver_index (косинус, перебор).
    Ловит смысл: «питер»/«спб» -> «Г. САНКТ-ПЕТЕРБУРГ». Порог отсекает не-сущностные слова."""
    if not EMBED_URL:
        return
    chk = psql("SELECT count(*) FROM resolver_index;", ["-tA"])
    if chk.returncode != 0 or not chk.stdout.strip().isdigit() or int(chk.stdout.strip()) == 0:
        return  # индекс не построен — тихо пропускаем (лексика всё равно работает)
    vecs = embed(words[:8])
    for w, v in zip(words[:8], vecs):
        q = (
            f"SELECT table_name, column_name, value, array_cosine_similarity(emb, {_vec_literal(v)}) sim "
            f"FROM resolver_index ORDER BY sim DESC LIMIT 1;"
        )
        for line in psql(q, ["-tAF", "\t"]).stdout.splitlines():
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
    # ≥3 символа — ловим короткие аббревиатуры (спб, мск); стоп-слова отфильтрованы ниже
    words = [w for w in re.findall(r"[0-9A-Za-zА-Яа-яёЁ-]{3,}", str(question).lower()) if w not in RU_STOP]
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


def gen_sql(question, schema, hints=""):
    if not DS_KEY:
        raise RuntimeError("нет DEEPSEEK_API_KEY")
    sys_prompt = (
        "Ты SQL-аналитик для SereneDB (DuckDB-совместимый диалект, Postgres-протокол). "
        "По схеме и вопросу верни РОВНО ОДИН read-only SELECT (или WITH...SELECT). "
        "Только колонки из схемы — не выдумывай. Учитывай ФОРМАТ значений из примеров (e.g. ...). "
        "Если даны РЕЛЕВАНТНЫЕ ЗНАЧЕНИЯ — фильтруй ТОЧНО по ним (термин из вопроса → точное значение). "
        "Без пояснений, без markdown, без ';' в конце. Разумные LIMIT для 'топ'."
    )
    user = f"СХЕМА:\n{schema}\n"
    if hints:
        user += f"\nРЕЛЕВАНТНЫЕ ЗНАЧЕНИЯ (термин вопроса → точные значения в данных, используй их):\n{hints}\n"
    user += f"\nВОПРОС: {question}\n\nSQL:"
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


def validate(sql):
    if len(sql) > MAX_SQL_LEN:
        return f"SQL слишком длинный ({len(sql)}>{MAX_SQL_LEN}) — вероятно патологическая генерация"
    if not re.match(r"^\s*(select|with)\b", sql, re.I):
        return "не SELECT/WITH"
    bare = _strip_literals(sql)  # ключевые слова/«;» проверяем ВНЕ строковых литералов
    if ";" in bare:
        return "несколько операторов"
    if FORBIDDEN.search(bare):
        return "запрещённое ключевое слово (изменение данных)"
    if FS_ACCESS.search(bare):
        return "запрещён доступ к файловой системе (табличная функция чтения файлов)"
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
    # обёртка-подзапрос: стабильные заголовки + гарантированный LIMIT независимо от формы sql
    wrapped = f"SELECT * FROM (\n{sql}\n) _q LIMIT {max_rows}"
    r = psql(wrapped, extra=["-A", "-F", "\t"])  # без -t: первая строка = заголовки
    if r.returncode != 0:
        return {"question": question, "sql": sql, "error": f"ошибка выполнения: {r.stderr.strip()[:300]}"}
    data = [ln for ln in r.stdout.splitlines() if ln != "" and not re.match(r"^\(\d+ rows?\)$", ln.strip())]
    if not data:
        return {"question": question, "sql": sql, "columns": [], "rows": [], "n": 0}
    columns = data[0].split("\t")
    rows = [ln.split("\t") for ln in data[1:]]
    return {"question": question, "sql": sql, "columns": columns, "rows": rows, "n": len(rows)}


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
    body = "\n".join(lines) + more
    if show_sql:
        body += f"\n\nСтрок: {result['n']}\nТрактовка (SQL): {result['sql']}"
    return body
