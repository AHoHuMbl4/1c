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
import json, os, re, subprocess, urllib.request

DSN = os.environ.get("SERENEDB_DSN", "host=127.0.0.1 port=7890 user=postgres")
DS_BASE = os.environ.get("DEEPSEEK_BASE", "https://api.deepseek.com").rstrip("/")
DS_KEY = os.environ.get("DEEPSEEK_API_KEY", "")

FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|grant|revoke|copy|attach|"
    r"detach|pragma|call|merge|replace|vacuum|install|load)\b",
    re.I,
)


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
        "WHERE schema_name = 'public' "
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
        parts = []
        for c, dt in cols:
            desc = f"{c} {dt}"
            if any(k in dt.lower() for k in ("char", "text", "string")):
                ex = sample_values(t, c)
                if ex:
                    desc += " e.g. " + "|".join(ex)
            parts.append(desc)
        out.append(f"- {t}({', '.join(parts)})")
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


def resolve_hints(question, max_per_col=5, max_distinct=1500, min_sim=0.9):
    """Термины вопроса -> точные значения КОЛОНОК-ИЗМЕРЕНИЙ витрины (fuzzy). Строка-подсказка для LLM.
    Берём только низко-кардинальные текстовые колонки (справочные измерения вроде city), а не
    высоко-кардинальные сущности (имена — description) — чтобы не шуметь. Падежи ловим стеммингом.
    На больших измерениях чистую семантику даст векторный слой (HNSW) — TODO, нужен reachable-эмбеддер."""
    words = [w for w in re.findall(r"[0-9A-Za-zА-Яа-яёЁ-]{4,}", str(question).lower()) if w not in RU_STOP]
    if not words:
        return ""
    r = psql(
        "SELECT table_name, column_name FROM duckdb_columns() "
        "WHERE schema_name='public' AND lower(data_type) LIKE '%char%';",
        ["-tAF", "\t"],
    )
    if r.returncode != 0:
        return ""
    hints = []
    for line in r.stdout.splitlines():
        if not line.strip():
            continue
        t, c = line.split("\t")
        cnt = psql(f'SELECT count(DISTINCT "{c}") FROM "{t}";', ["-tA"]).stdout.strip()
        if not cnt.isdigit() or int(cnt) > max_distinct:
            continue  # высоко-кардинальная (сущность) — не измерение для фильтра по термину
        conds = []
        for w in words[:8]:
            wq = w.replace("'", "''")
            sq = _stem(w).replace("'", "''")
            conds.append(f"lower(\"{c}\") LIKE '%{wq}%'")
            conds.append(f"lower(\"{c}\") LIKE '%{sq}%'")
            conds.append(f"jaro_winkler_similarity(lower(\"{c}\"), '{wq}') > {min_sim}")
        q = (
            f'SELECT DISTINCT "{c}" FROM "{t}" '
            f'WHERE "{c}" IS NOT NULL AND ({" OR ".join(conds)}) LIMIT {max_per_col};'
        )
        vals = [v for v in psql(q, ["-tA"]).stdout.splitlines() if v.strip()][:max_per_col]
        if vals:
            hints.append(f"{t}.{c}: " + ", ".join(vals))
    return "\n".join(hints)


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


def validate(sql):
    if not re.match(r"^\s*(select|with)\b", sql, re.I):
        return "не SELECT/WITH"
    if ";" in sql:
        return "несколько операторов"
    if FORBIDDEN.search(sql):
        return "запрещённое ключевое слово (изменение данных)"
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
