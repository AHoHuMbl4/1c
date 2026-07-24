#!/usr/bin/env python3
"""
Построитель семантического индекса резолвера (Этап 3 v2). Эмбеддит DISTINCT значения
низко-кардинальных текстовых колонок-измерений (city…) моделью Qwen text-embedding-v4 @ 1536
(РОВНО как braine) и кладёт в таблицу SereneDB `resolver_index(table_name,column_name,value,emb)`.
Потом резолвер ищет ближайшее значение к термину вопроса (косинус) → «питер»→«Г. САНКТ-ПЕТЕРБУРГ».

Запуск под RW (postgres): SERENEDB_DSN=host=127.0.0.1 port=7890 user=postgres + ALIBABA_* в env.
Пересобирает индекс с нуля. На больших справочниках HNSW ускорит поиск (в этой версии SereneDB
CREATE INDEX USING HNSW недоступен — перебор косинуса; для сотен-тысяч значений добавить индекс).
"""
import sys
import serene_report as S

BATCH = 10  # размер батча эмбеддинга (лимит DashScope text-embedding-v4)
INS = 50    # строк на один INSERT


def sql_or_die(sql, extra=None):
    r = S.psql(sql, extra)
    if r.returncode != 0:
        sys.exit(f"SQL error: {r.stderr.strip()[:300]}\n{sql[:200]}")
    return r


def main():
    if not S.EMBED_URL or not S.EMBED_KEY:
        sys.exit("нет ALIBABA_EMBED_URL/ALIBABA_API_KEY — эмбеддер Qwen не сконфигурирован")
    sql_or_die(
        f"CREATE TABLE IF NOT EXISTS resolver_index"
        f"(table_name TEXT, column_name TEXT, value TEXT, emb FLOAT[{S.EMBED_DIM}]);"
    )
    # resolver_index читает ОТДЕЛЬНАЯ роль serene_resolver (positive control), НЕ serene_ro — тогда
    # LLM-SQL под serene_ro не дотянется до служебного индекса даже в обход валидатора.
    S.psql("GRANT SELECT ON resolver_index TO serene_resolver;")
    S.psql("REVOKE SELECT ON resolver_index FROM serene_ro;")  # идемпотентно закрываем ro-доступ
    sql_or_die("DELETE FROM resolver_index;")
    total = 0
    for t, c in S.dim_columns():
        vals = [v for v in S.psql(f'SELECT DISTINCT "{c}" FROM "{t}" WHERE "{c}" IS NOT NULL;', ["-tA"]).stdout.splitlines() if v.strip()]
        rows = []
        for i in range(0, len(vals), BATCH):
            batch = vals[i:i + BATCH]
            vecs = S.embed(batch)
            for val, v in zip(batch, vecs):
                vq = val.replace("'", "''")
                rows.append(f"('{t}','{c}','{vq}',{S._vec_literal(v)})")
        for i in range(0, len(rows), INS):
            chunk = rows[i:i + INS]
            sql_or_die("INSERT INTO resolver_index VALUES " + ",".join(chunk) + ";")
        print(f"{t}.{c}: {len(vals)} значений")
        total += len(vals)
    print(f"resolver_index построен: {total} значений (Qwen {S.EMBED_MODEL} @ {S.EMBED_DIM})")


if __name__ == "__main__":
    main()
