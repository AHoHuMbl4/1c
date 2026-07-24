#!/usr/bin/env python3
"""Тесты ALLOW-LIST валидатора (serene_report.validate) — через AST (json_serialize_sql), поэтому
нужна БД: запускать в окружении reports на сервере (как probe.sh).
  • MUST_PASS — валидный одиночный SELECT по РЕАЛЬНЫМ таблицам витрины НЕ должен ложно отклоняться.
  • MUST_FAIL — запись/DDL/мульти/табличные-функции(файлы)/объекты-вне-схемы/служебные-функции — отклонены
    BY CONSTRUCTION (таблица не в схеме, или узел — не читающий запрос). Без списков имён/слов.
Предполагается наличие таблицы `banks` в витрине (или замените на любую реальную — тест схемо-агностичен
кроме имени в кейсах).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import serene_report as R  # noqa: E402

T = "banks"  # реальная таблица витрины для кейсов (есть в этой базе)
MUST_PASS = [
    f"SELECT * FROM {T}",
    f"select count(*) from {T} where city = 'Г. КАЗАНЬ'",
    f"WITH t AS (SELECT city, count(*) c FROM {T} GROUP BY city) SELECT * FROM t ORDER BY c DESC LIMIT 5",
    f"SELECT description FROM {T} ORDER BY code LIMIT 10",
    f"SELECT replace(description, 'Г.', '') FROM {T}",             # функция replace — не запись
    f"SELECT description FROM {T} WHERE description LIKE '%truncate%'",  # ключевое слово в СТРОКЕ
    f"SELECT * FROM {T} WHERE city = 'РОСТОВ; МОСКВА'",            # «;» внутри строки — один statement
    f"SELECT count(*) AS total_load FROM {T}",                    # 'load' в идентификаторе
    f"SELECT a.city FROM {T} a JOIN {T} b ON a.city=b.city GROUP BY a.city",  # join реальных таблиц
]
MUST_FAIL = [
    f"DELETE FROM {T}",
    f"DROP TABLE {T}",
    f"UPDATE {T} SET city='x'",
    f"INSERT INTO {T} (ref_key) VALUES ('x')",
    f"TRUNCATE {T}",
    f"SELECT 1; DROP TABLE {T}",                                  # несколько операторов
    "SELECT * FROM read_csv('/etc/passwd')",                     # табличная функция (файл)
    "SELECT * FROM read_text('/etc/shadow')",
    "SELECT * FROM glob('/etc/*')",
    "SELECT content FROM read_blob('/root/.ssh/id_rsa')",
    "SELECT * FROM resolver_index",                              # объект вне схемы витрины
    "SELECT * FROM pg_settings",
    "SELECT table_name FROM information_schema.tables",
    "SELECT * FROM duckdb_settings()",                           # табличная функция
    "SELECT current_setting('data_directory')",                 # служебная скалярная функция
    "SELECT * FROM totally_nonexistent_table",                  # выдуманная таблица (не в схеме)
    "WITH x AS (SELECT * FROM read_csv('/etc/passwd')) SELECT * FROM x",  # табл.функция внутри CTE
    "SELECT " + "1," * 4000 + f"1 FROM {T}",                     # патологически длинный
]


def main():
    fails = 0
    print("== ДОЛЖНЫ ПРОЙТИ (валидный SELECT по витрине) ==")
    for sql in MUST_PASS:
        err = R.validate(sql)
        ok = err is None
        if not ok:
            fails += 1
        print(f"  {'OK  ' if ok else 'БАГ✗'}  {('пропущен' if ok else 'ЛОЖНО ОТКЛОНЁН: ' + str(err)):<40}  {sql[:50]}")
    print("\n== ДОЛЖНЫ БЫТЬ ОТКЛОНЕНЫ ==")
    for sql in MUST_FAIL:
        err = R.validate(sql)
        ok = err is not None
        if not ok:
            fails += 1
        print(f"  {'OK  ' if ok else 'БАГ✗ ПРОСОЧИЛОСЬ':<8}  {sql[:52]:<54}  -> {err}")
    print(f"\nИТОГ: {'ВСЁ PASS ✅' if fails == 0 else str(fails) + ' БАГ(ов) ✗'}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
