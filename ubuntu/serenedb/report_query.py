#!/usr/bin/env python3
"""
Умный NL->запрос по витрине SereneDB (Этап 2, ядро «системы без хардкода»).

Идея (см. docs/SERENEDB.md): LLM НЕ пишет числа — он превращает вопрос в SELECT по РЕАЛЬНОЙ
(интроспектированной) схеме; код валидирует, что это только чтение; SereneDB считает; наверх
отдаём и результат, и САМ запрос (прозрачность трактовки — страховка от «понял не так»).
Ничего не хардкодим: схема берётся из БД, вопрос — на естественном языке.

Запуск:  python3 report_query.py "топ-5 городов по числу банков"
Env:     SERENEDB_DSN (default 'host=127.0.0.1 port=7890 user=postgres')
         DEEPSEEK_API_KEY (обяз.), DEEPSEEK_BASE (default https://api.deepseek.com)
"""
import json, os, re, subprocess, sys, urllib.request

DSN = os.environ.get("SERENEDB_DSN", "host=127.0.0.1 port=7890 user=postgres")
DS_BASE = os.environ.get("DEEPSEEK_BASE", "https://api.deepseek.com").rstrip("/")
DS_KEY = os.environ.get("DEEPSEEK_API_KEY", "")

# только чтение: разрешаем один SELECT/WITH; запрещаем изменяющее/опасное
FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|grant|revoke|copy|attach|"
    r"detach|pragma|call|merge|replace|vacuum|install|load)\b",
    re.I,
)


def psql(sql, dsn=DSN, extra=None):
    cmd = ["psql", dsn, "-v", "ON_ERROR_STOP=1"] + (extra or [])
    return subprocess.run(cmd, input=sql, text=True, capture_output=True)


def sample_values(table, col, n=5):
    """Примеры значений колонки — чтобы LLM знал ФОРМАТ данных ('Г. МОСКВА', а не 'Москва').
    Авто из данных, без хардкода. На больших таблицах в проде — кэшировать профиль/резолвер."""
    q = f'SELECT DISTINCT "{col}" FROM "{table}" WHERE "{col}" IS NOT NULL LIMIT {n};'
    r = psql(q, extra=["-tA"])
    if r.returncode != 0:
        return []
    return [v for v in (line.strip() for line in r.stdout.splitlines()) if v][:n]


def get_schema():
    """Интроспекция: таблицы + колонки + типы + примеры значений текстовых колонок."""
    sql = (
        "SELECT table_name, column_name, data_type FROM information_schema.columns "
        "WHERE table_schema NOT IN ('information_schema','pg_catalog') "
        "ORDER BY table_name, ordinal_position;"
    )
    r = psql(sql, extra=["-tAF", "\t"])
    if r.returncode != 0:
        sys.exit(f"schema error: {r.stderr}")
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
        sys.exit("нет DEEPSEEK_API_KEY")
    sys_prompt = (
        "Ты SQL-аналитик для SereneDB (DuckDB-совместимый диалект, Postgres-протокол). "
        "По схеме и вопросу верни РОВНО ОДИН read-only SELECT (или WITH...SELECT). "
        "Только колонки из схемы — не выдумывай. Без пояснений, без markdown, без ';' в конце. "
        "Разумные LIMIT для 'топ'. Строки сравнивай регистронезависимо где уместно."
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
    sql = re.sub(r"^```[a-z]*\s*|\s*```$", "", sql, flags=re.I).strip().rstrip(";").strip()
    return sql


def validate(sql):
    if not re.match(r"^\s*(select|with)\b", sql, re.I):
        return "не SELECT/WITH"
    if ";" in sql:
        return "несколько операторов (';')"
    if FORBIDDEN.search(sql):
        return "запрещённое ключевое слово (изменение данных)"
    return None


def main():
    if len(sys.argv) < 2:
        sys.exit('usage: report_query.py "<вопрос>"')
    question = sys.argv[1]
    schema = get_schema()
    sql = gen_sql(question, schema)
    err = validate(sql)
    print(f"Вопрос: {question}")
    print(f"Трактовка (SQL):\n  {sql}")
    if err:
        sys.exit(f"ОТКЛОНЕНО валидатором ({err}) — не выполняю.")
    r = psql(sql)
    if r.returncode != 0:
        sys.exit(f"ошибка выполнения: {r.stderr}")
    print("Результат:")
    print(r.stdout)


if __name__ == "__main__":
    main()
