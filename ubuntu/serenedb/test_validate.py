#!/usr/bin/env python3
"""Изощрённые тесты валидатора read-only SQL (serene_report.validate) — чистая функция, без БД/LLM.
Две стороны:
  • MUST_PASS — валидные read-only SELECT НЕ должны ложно отклоняться (иначе ломаем аналитику).
  • MUST_FAIL — запись/инъекция/ЧТЕНИЕ ФАЙЛОВ сервера должны отклоняться (иначе бота можно раскрутить).
Запуск: python3 test_validate.py   (локально — импортит serene_report из этой папки)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import serene_report as R  # noqa: E402

MUST_PASS = [
    "SELECT * FROM banks",
    "select count(*) from banks where city = 'Г. КАЗАНЬ'",
    "WITH t AS (SELECT city, count(*) c FROM banks GROUP BY city) SELECT * FROM t ORDER BY c DESC LIMIT 5",
    "SELECT description FROM banks ORDER BY code LIMIT 10",
    "SELECT date_trunc('month', period) m, sum(amount) s FROM sales GROUP BY m ORDER BY m",
    "SELECT city, count(*) FROM banks GROUP BY city HAVING count(*) > 100",
    "SELECT replace(description, 'Г.', '') FROM banks",          # replace() — строковая функция, НЕ запись
    "SELECT description FROM banks WHERE description LIKE '%truncate%'",  # ключевое слово в СТРОКЕ-литерале
    "SELECT * FROM banks WHERE city = 'РОСТОВ; МОСКВА'",         # «;» внутри строки — не «несколько операторов»
    "SELECT count(*) AS total_load FROM banks",                 # 'load' как часть идентификатора — не оператор
]

MUST_FAIL = [
    "DELETE FROM banks",
    "DROP TABLE banks",
    "UPDATE banks SET city='x'",
    "INSERT INTO banks VALUES (1)",
    "TRUNCATE banks",
    "SELECT 1; DROP TABLE banks",                                # несколько операторов
    "select * from banks; delete from banks",
    "WITH x AS (DELETE FROM banks RETURNING *) SELECT * FROM x",  # DML в CTE
    "ATTACH 'evil.db' AS e",
    "COPY banks TO '/tmp/leak.csv'",
    "SELECT * FROM read_csv('/etc/passwd')",                     # чтение файла сервера
    "SELECT * FROM read_text('/etc/shadow')",
    "SELECT * FROM glob('/etc/*')",
    "SELECT content FROM read_blob('/root/.ssh/id_rsa')",
    "SELECT * FROM read_parquet('/var/lib/serenedb/secret.parquet')",
    "SELECT " + "1," * 4000 + "1 FROM banks",  # патологически длинный (repetition-loop) — ронял SereneDB
    "SELECT * FROM resolver_index",                      # внутренний RAG-индекс (эмбеддинги)
    "SELECT * FROM pg_settings",                         # конфиг движка + внутренние пути
    "SELECT table_name FROM information_schema.tables",  # раскрытие служебных объектов
    "SELECT current_setting('data_directory')",          # внутренний путь через current_setting
    "SELECT * FROM duckdb_settings()",                   # интроспекция движка
]


def main():
    fails = 0
    print("== ДОЛЖНЫ ПРОЙТИ (валидный read-only SELECT) ==")
    for sql in MUST_PASS:
        err = R.validate(sql)
        ok = err is None
        if not ok:
            fails += 1
        print(f"  {'OK  ' if ok else 'БАГ✗'}  {('пропущен' if ok else 'ЛОЖНО ОТКЛОНЁН: ' + str(err)):<34}  {sql[:58]}")
    print("\n== ДОЛЖНЫ БЫТЬ ОТКЛОНЕНЫ (запись / инъекция / чтение файлов) ==")
    for sql in MUST_FAIL:
        err = R.validate(sql)
        ok = err is not None
        if not ok:
            fails += 1
        print(f"  {'OK  ' if ok else 'БАГ✗ ПРОСОЧИЛОСЬ':<8}  {sql[:56]:<58}  -> {err}")
    print(f"\nИТОГ: {'ВСЁ PASS ✅' if fails == 0 else str(fails) + ' БАГ(ов) ✗'}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
