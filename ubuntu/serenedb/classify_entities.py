#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Разметка сущностей: о чём человек спрашивает, а что служебное.

🔴 ЗАЧЕМ. На чужой базе корпус оказался 632 683 строки, и крупнейшие сущности —
[замер 29.07, УТ 11.4.9] `замерывремени` (97 834), `удалитьзамерывремени3` (52 153),
`удалитьзамерывремени2` (17 311): технические замеры производительности и объекты,
помеченные в конфигурации на удаление. Считать по ним векторы — 5,9 часа и живые деньги
почти целиком впустую. Без этой разметки полный такт на незнакомой базе неподъёмен, а
значит недостижима и автономность («поставил и работает»).

🔴 ЭТО ПРИОРИТЕТ, А НЕ ИСКЛЮЧЕНИЕ. Ни одна строка не выбрасывается:
  * текстовый индекс (BM25) строится по ВСЕМУ корпусу — он дёшев;
  * векторы считаются бизнес-сущностям; служебным — НЕ считаются вовсе
    (решение владельца 29.07 «да, не нужны они в векторе»);
  * отсутствие вектора у служебных названо в переписи причиной (`cov_noemb_service`)
    отдельно от «ещё в очереди» (`cov_noemb_pending`) — это разные вещи.
Полнота (п. 13) не страдает, а отсутствие вектора видно в переписи.

🔴 РЕШАЕТ МОДЕЛЬ, А НЕ СПИСОК СЛОВ В КОДЕ. Список вроде «замеры», «удалить», «служебный»
был бы хардкодом под язык и под конфигурацию (`HOW_NOT_TO §3.9`): на другой базе те же
понятия названы иначе. Модели уходят ТОЛЬКО имена — сущности, её человеческая метка,
имена колонок и число строк. Данные наружу не уходят (п. 16, п. 19).

Про п. 19 и п. 3: это разметка НА СБОРКЕ, разовая на сущность, с кэшем в базе. Повторно
спрашиваем только про НОВЫЕ сущности — но одного этого мало: на первом такте незнакомой
базы новыми являются ВСЕ, и объём рос бы с её размером. Поэтому есть жёсткий потолок за
прогон (`CLASSIFY_MAX_PER_RUN`): величина, уходящая в модель, постоянна, а остаток
достаётся следующими тактами и называется числом в выводе.

Про п. 20: своим кодом здесь остаётся ровно то, что разрешено, — вызов языковой модели и
решение, требующее смысла. Данные читаются одним запросом и пишутся одним запросом.

Env: SERENEDB_DSN, DEEPSEEK_API_KEY (+ DEEPSEEK_BASE, DEEPSEEK_MODEL), CLASSIFY_BATCH.
"""
import csv
import io
import json
import os
import subprocess
import sys
import urllib.request

DSN = os.environ.get("SERENEDB_DSN", "host=127.0.0.1 port=7890 user=postgres dbname=postgres")
DS_BASE = os.environ.get("DEEPSEEK_BASE", "https://api.deepseek.com").rstrip("/")
DS_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash")
DS_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
# Сколько сущностей в одном обращении к модели. Это БЮДЖЕТ ОБРАЩЕНИЯ, а не порог
# правильности: меньше — больше вызовов, больше — риск, что модель заторопится.
BATCH = int(os.environ.get("CLASSIFY_BATCH", "25"))
# Сколько имён колонок показывать. Тоже бюджет: по десятку колонок смысл сущности уже
# понятен, а полный список у широких таблиц раздул бы обращение.
COLS_SHOWN = int(os.environ.get("CLASSIFY_COLS", "12"))
# Потолок сущностей за ОДИН прогон. Держит объём, уходящий в модель, постоянным вне
# зависимости от размера базы (п. 3). 400 при пачке 25 — шестнадцать обращений, минуты;
# на базе в 1 501 сущность разметка завершится за четыре такта, а такты идут подряд.
MAX_PER_RUN = int(os.environ.get("CLASSIFY_MAX_PER_RUN", "400"))

SYS = """You sort database tables of a business system into two buckets.

For each table you get: its technical name, a human label, up to a dozen column names and
how many rows it holds. You never get the data itself.

Answer JSON only: {"items": [{"n": "<technical name>", "c": "business"|"service"}]}

"business" — records a person in the company would ask questions about: customers, goods,
orders, invoices, payments, stock, employees, contracts, prices, accounts.

"service" — everything that exists for the system itself and nobody asks about in words:
performance measurements and timings, technical logs, exchange/sync bookkeeping, access
rights and roles, UI settings and layouts, caches, versioning, predefined classifiers used
only internally, and anything the configuration marks as deleted or obsolete.

Judge by meaning, not by wording — the same idea is named differently in different
configurations and languages. When a table plainly holds real business facts, say
business. When genuinely unsure, say business: a wrong "service" costs the user an answer,
a wrong "business" costs only compute."""


def psql(sql):
    p = subprocess.run(["psql", DSN, "-tA", "--csv", "-v", "ON_ERROR_STOP=1", "-f", "-"],
                       input=sql, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or "psql failed")[:300])
    return [r for r in csv.reader(io.StringIO(p.stdout)) if r]


def psql_exec(sql):
    p = subprocess.run(["psql", DSN, "-v", "ON_ERROR_STOP=1", "-f", "-"],
                       input=sql, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or "psql failed")[:300])


def lit(s):
    return "'" + str(s).replace("'", "''") + "'"


def ask(items):
    """Один батч в модель. Пусто — значит не получилось; вызывающий не падает."""
    if not DS_KEY:
        return {}
    body_obj = {
        "model": DS_MODEL, "temperature": 0, "max_tokens": 4000,
        "messages": [{"role": "system", "content": SYS},
                     {"role": "user", "content": json.dumps(items, ensure_ascii=False)}],
    }
    # vLLM/Qwen: как serene_ask (ASK_THINKING_OFF_BODY). Иначе timeout на gpu-27b [замер 21.08].
    if os.environ.get("ASK_THINKING_OFF_BODY", "") in ("1", "true", "yes") or \
       os.environ.get("DEEPSEEK_THINKING", "disabled") == "disabled":
        body_obj["chat_template_kwargs"] = {"enable_thinking": False}
        body_obj["thinking"] = {"type": "disabled"}
    body = json.dumps(body_obj).encode()
    req = urllib.request.Request(DS_BASE + "/v1/chat/completions", data=body, method="POST")
    req.add_header("Authorization", "Bearer " + DS_KEY)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            txt = json.loads(r.read())["choices"][0]["message"]["content"]
    except Exception as e:                      # noqa: BLE001 — сеть/квота
        sys.stderr.write("classify: модель недоступна: %s\n" % str(e)[:160])
        return {}
    m = txt[txt.find("{"):txt.rfind("}") + 1] if "{" in txt else ""
    try:
        out = json.loads(m).get("items", [])
    except ValueError:
        # 🔴 НЕ ОШИБКА, А ДРУГОЙ ЗАХОД. Ответ рвётся по пределу длины, когда сущностей в
        # обращении много: [замер 29.07] при 40 не разобралось 920 из 1501, при этом на
        # трёх сущностях модель отвечает верно. Значит дело не в модели, а в размере
        # обращения — делим пополам и пробуем снова, пока не станет разбираемо.
        if len(items) > 1:
            half = len(items) // 2
            left = ask(items[:half])
            right = ask(items[half:])
            left.update(right)
            return left
        sys.stderr.write("classify: ответ модели не разобран на одной сущности\n")
        return {}
    return {i.get("n"): i.get("c") for i in out if i.get("n") and i.get("c") in ("business", "service")}


def main():
    psql_exec("CREATE TABLE IF NOT EXISTS search_entity_class ("
              "src_table VARCHAR, cls VARCHAR, seen_at TIMESTAMP);")

    # Спрашиваем только про НОВОЕ: разметка кэшируется в базе и переживает такты.
    #
    # 🔴 ПОТОЛОК ЗА ПРОГОН ОБЯЗАТЕЛЕН (п. 3). «Только новые» — не ограничение: на первом
    # такте незнакомой базы новыми являются ВСЕ сущности, и объём, уходящий в модель, рос
    # бы с размером базы без потолка сверху. `LIMIT` делает величину постоянной.
    # Остаток — следующими тактами (потолок CLASSIFY_MAX_PER_RUN не ошибка). Пока
    # метки нет, сущность идёт в первый проход как «не service». Полный провал модели
    # (0 размеченных при attempted>0) — код 2: build.sh останавливает такт (fail-closed).
    # Сначала крупные (`ORDER BY 4 DESC`) — от них и экономия наибольшая.
    rows = psql("""
        SELECT s.src_table,
               coalesce(t.label, s.src_table),
               coalesce((SELECT string_agg(c.col, ',' ORDER BY c.ord)
                         FROM (SELECT col, ord FROM tmp3_cls
                               WHERE tbl = s.src_table AND kind <> 'skip'
                               ORDER BY ord LIMIT %d) c), ''),
               coalesce((SELECT count(*) FROM search_corpus x WHERE x.src_table = s.src_table), 0)
        FROM search_sources s
        LEFT JOIN search_tables t ON t.src_table = s.src_table
        WHERE NOT EXISTS (SELECT 1 FROM search_entity_class e WHERE e.src_table = s.src_table)
        ORDER BY 4 DESC
        LIMIT %d
    """ % (COLS_SHOWN, MAX_PER_RUN))

    if not rows:
        print(json.dumps({"новых_сущностей": 0}, ensure_ascii=False))
        return 0

    # Сколько осталось на следующие такты — НАЗЫВАЕМ ЧИСЛОМ, а не умалчиваем (п. 13):
    # молча обрезанная работа неотличима от законченной.
    left = psql("""SELECT count(*) FROM search_sources s
                   WHERE NOT EXISTS (SELECT 1 FROM search_entity_class e
                                     WHERE e.src_table = s.src_table)""")
    left = max(0, int(left[0][0]) - len(rows)) if left else 0

    done, failed = 0, 0
    for i in range(0, len(rows), BATCH):
        chunk = rows[i:i + BATCH]
        items = [{"n": r[0], "label": r[1], "cols": r[2][:300], "rows": int(r[3] or 0)}
                 for r in chunk]
        got = ask(items)
        if not got:
            failed += len(chunk)
            continue
        # 🔴 Неотвеченное считаем БИЗНЕСОМ. Ошибка в сторону «служебное» стоит человеку
        # ответа, ошибка в сторону «бизнес» — только счёта за вектора.
        vals = ",".join("(%s,%s,now())" % (lit(r[0]), lit(got.get(r[0], "business")))
                        for r in chunk)
        psql_exec("INSERT INTO search_entity_class VALUES " + vals + ";")
        done += len(chunk)

    stat = psql("""SELECT e.cls, count(*), coalesce(sum(c.n), 0)
                   FROM search_entity_class e
                   LEFT JOIN (SELECT src_table, count(*) AS n FROM search_corpus GROUP BY 1) c
                          ON c.src_table = e.src_table
                   GROUP BY 1 ORDER BY 1""")
    print(json.dumps({
        "размечено_за_прогон": done,
        "не_удалось": failed,
        "осталось_на_следующие_такты": left,
        "итого": {r[0]: {"сущностей": int(r[1]), "строк": int(r[2])} for r in stat},
    }, ensure_ascii=False))
    # 0 — успех или штатный потолок; 2 — модель не ответила ни на один батч.
    return classify_exit_code(done, failed, len(rows))


def classify_exit_code(done, failed, attempted):
    """Код выхода прогона разметки.

    attempted — сколько сущностей взяли в этот прогон (после LIMIT).
    Полный провал модели (ни одной метки при ненулевой работе) → 2.
    Потолок CLASSIFY_MAX_PER_RUN (есть остаток, но done>0) → 0.
    """
    if attempted > 0 and done == 0 and failed > 0:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
