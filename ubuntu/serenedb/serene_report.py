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


def gen_sql(question, schema):
    if not DS_KEY:
        raise RuntimeError("нет DEEPSEEK_API_KEY")
    sys_prompt = (
        "Ты SQL-аналитик для SereneDB (DuckDB-совместимый диалект, Postgres-протокол). "
        "По схеме и вопросу верни РОВНО ОДИН read-only SELECT (или WITH...SELECT). "
        "Только колонки из схемы — не выдумывай. Учитывай ФОРМАТ значений из примеров (e.g. ...). "
        "Без пояснений, без markdown, без ';' в конце. Разумные LIMIT для 'топ'."
    )
    body = json.dumps({
        "model": "deepseek-chat",
        "temperature": 0,
        "messages": [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": f"СХЕМА:\n{schema}\n\nВОПРОС: {question}\n\nSQL:"},
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
    sql = gen_sql(question, schema)
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
