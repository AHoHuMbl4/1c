#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Какая из числовых колонок сущности содержит ДЕНЬГИ — единственный шаг сборки,
которого у движка нет.

Почему это вообще наш код. Пункт 20 `TARGET.md` разрешает своим кодом ровно то, чего у
движка нет, и называет это поимённо: «вызов языковой модели и решения, требующие
смысла». У SereneDB есть `ai_embed` (вектор), но вызова языковой модели нет —
проверено: в `duckdb_functions()` из семейства `ai%` только `ai_embed`. Всё остальное
в сборке корпуса делает движок (`corpus_build.sql`).

Почему не правилом. «Деньги — самое большое число» уже промахивалось на нашей же базе:
так деньгами становились служебный реквизит упорядочивания и процент комиссии, а на
рознице номер чека ККМ обогнал бы средний чек. Отличить деньги от счётчика по величине
нельзя; по имени — можно, и это чисто языковая задача.

🔴 Решение КЭШИРУЕТСЯ, и это главное отличие от прежнего кода. Раньше модель
спрашивали на каждую сущность в каждом такте: [замер 27.07] от 121 до 226 обращений за
прогон, и число растёт с числом сущностей базы — то есть нарушение п. 19 по духу и
лишние минуты в такте (п. 17). Ответ зависит ТОЛЬКО от списка имён числовых колонок,
поэтому ключом кэша служит его отпечаток: имена не изменились — модель не спрашиваем.

Запуск: между `corpus_build.sql` (он строит классификацию) и слиянием в корпус.
"""
import hashlib
import json
import os
import subprocess
import sys
import urllib.request

DSN = os.environ.get("SERENEDB_DSN", "host=127.0.0.1 port=7890 user=postgres dbname=postgres")
DS_BASE = os.environ.get("DEEPSEEK_BASE", "https://api.deepseek.com").rstrip("/")
DS_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DS_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash")

SYS = """You are given the numeric field names of one record type in an ERP database.
Pick the ONE field that holds the record's monetary total — the amount of money the
document is for. Answer with the NUMBER of that field only. If none of them is a money
total (they are counters, order indices, ordinal numbers, quantities, rates), answer 0."""


def q(sql):
    p = subprocess.run(["psql", DSN, "-tA", "--csv", "-c", sql],
                       capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError("SQL: %s" % (p.stderr or "")[:300])
    import csv as _csv
    import io as _io
    return [r for r in _csv.reader(_io.StringIO(p.stdout)) if r]


def ddl(sql):
    p = subprocess.run(["psql", DSN, "-v", "ON_ERROR_STOP=1", "-f", "-"],
                       input=sql, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError("DDL: %s" % (p.stderr or "")[:300])


def lit(s):
    return "'" + str(s).replace("'", "''") + "'"


def ask(entity_label, names):
    """Спросить модель. Возвращает имя колонки, '' если денег нет, None если не ответила.

    Разница между '' и None существенна: пусто — это ОТВЕТ «денежной колонки нет», и его
    можно закэшировать; None — отказ модели, кэшировать нельзя, иначе один сетевой сбой
    навсегда лишит сущность агрегатов.
    """
    if not names:
        return ""                              # числовых колонок нет — это ответ, не отказ
    if not DS_KEY:
        return None
    listing = "\n".join("%d. %s" % (i + 1, n) for i, n in enumerate(names))
    body = json.dumps({
        "model": DS_MODEL, "temperature": 0, "max_tokens": 8,
        "thinking": {"type": "disabled"},
        "messages": [{"role": "system", "content": SYS},
                     {"role": "user", "content": "Record type: %s\n\nFields:\n%s"
                      % (entity_label, listing)}]}).encode()
    req = urllib.request.Request(DS_BASE + "/v1/chat/completions", data=body, method="POST")
    req.add_header("Authorization", "Bearer " + DS_KEY)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = json.loads(r.read())["choices"][0]["message"]["content"]
    except Exception:                          # noqa: BLE001 — сеть/квота поставщика
        return None
    digits = "".join(c for c in (raw or "") if c.isdigit())
    if not digits:
        return None
    i = int(digits)
    if i == 0:
        return ""                              # модель прямо сказала: денег нет
    return names[i - 1] if 1 <= i <= len(names) else ""


def main():
    ddl("CREATE TABLE IF NOT EXISTS search_amount_col "
        "(tbl TEXT, col TEXT, fp TEXT);")
    # Числовые колонки берём из классификации, построенной ДВИЖКОМ по `$metadata`
    # (`corpus_build.sql`), а не из своего разбора: тип объявляет 1С.
    rows = q("SELECT c.tbl, string_agg(c.col, ',' ORDER BY c.ord) "
             "FROM tmp3_cls c JOIN tmp3_src s ON s.tbl = c.tbl "
             "WHERE c.kind = 'num' GROUP BY c.tbl")
    known = {r[0]: (r[1], r[2]) for r in q("SELECT tbl, col, fp FROM search_amount_col")}
    # Метки — ОДНИМ запросом, а не запросом на сущность. Запрос в цикле по строкам
    # запрещён п. 20, и запрещён по делу: на базе с тысячами типов это тысячи запусков
    # процесса ради одной строки каждый.
    labels = {r[0]: r[1] for r in q("SELECT src_table, label FROM search_tables")}
    asked = cached = failed = 0
    fresh = []
    for tbl, cols in rows:
        names = [c for c in (cols or "").split(",") if c]
        fp = hashlib.sha1(",".join(names).encode("utf-8")).hexdigest()
        if known.get(tbl, ("", ""))[1] == fp:
            cached += 1
            continue                           # имена колонок не менялись — ответ прежний
        # Метка сущности — человеческое имя из профиля, а не имя таблицы: модели легче
        # понять «Реализация Товаров Услуг», чем `document_реализациятоваровуслуг`.
        col = ask(labels.get(tbl, tbl), names)
        if col is None:
            failed += 1
            sys.stderr.write("%s: модель не ответила — агрегаты по этой сущности не "
                             "считаются до следующего прогона\n" % tbl)
            continue                           # НЕ кэшируем отказ
        asked += 1
        fresh.append((tbl, col, fp))
    # Запись — ОДНОЙ командой, а не строкой за раз. Тот же запрет п. 20: процесс `psql`
    # в цикле. На базе с тысячами типов построчная запись — тысячи запусков процесса.
    if fresh:
        ddl("DELETE FROM search_amount_col WHERE tbl IN (%s);"
            "INSERT INTO search_amount_col VALUES %s;"
            % (", ".join(lit(t) for t, _c, _f in fresh),
               ", ".join("(%s,%s,%s)" % (lit(t), lit(c), lit(f)) for t, c, f in fresh)))
    print(json.dumps({"сущностей": len(rows), "спрошено": asked, "из кэша": cached,
                      "модель не ответила": failed}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
