#!/usr/bin/env python3
"""Оффлайн-проба разбора подписей веток развилок: БЕЗ базы, БЕЗ сети, БЕЗ модели.

Имена выдуманы: проба не знает ни одной настоящей базы. Держит инварианты, без
которых словарь развилок врёт с первого такта:

  * пара (fork_key, src), которой не было во входе, в таблицу не попадает —
    ни чужой класс, ни чужая ветка известного класса;
  * пустая подпись — не ответ;
  * битый JSON — пустой разбор, а не исключение (класс не хоронится: заглушку
    ставит скрипт, переспрос идёт не чаще RETRY_H);
  * пропуск ветки в ответе — её просто нет в строках, остальные пишутся.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import branch_alias_parse as P  # noqa: E402

PASS, FAIL = 0, []


def t(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + str(detail)[:160]) if detail else "")


PAY = [{"fork_key": "k_zakupki", "measure": "СуммаПробная",
        "sources": [{"src": "register_закупкипробные", "title": "Закупки Пробные",
                     "bestUsedFor": "анализ закупок"},
                    {"src": "document_поступлениепробное", "title": "Поступление Пробное",
                     "bestUsedFor": "оформление закупки"}]},
       {"fork_key": "k_prodazhi", "measure": "СуммаПробная",
        "sources": [{"src": "document_отгрузкапробная", "title": "Отгрузка Пробная",
                     "bestUsedFor": "выручка"},
                    {"src": "register_расчетыпробные", "title": "Расчёты Пробные",
                     "bestUsedFor": "долг клиентов"}]}]

# Полный верный ответ в конверте `openclaw agent --json`.
ENV = json.dumps({"result": {"payloads": [{"text": """
{"forks":[
 {"fork_key":"k_zakupki","labels":{
   "register_закупкипробные":"аналитика закупок: суммы и себестоимость поставок",
   "document_поступлениепробное":"документы поступления от поставщиков"}},
 {"fork_key":"k_prodazhi","labels":{
   "document_отгрузкапробная":"оформленные отгрузки клиентам (выручка)",
   "register_расчетыпробные":"долг и предоплата клиентов, а не факт отгрузки"}}
]}"""}]}}, ensure_ascii=False)

rows = P.parse_labels(P.text_from_agent(ENV), PAY)
by = {(r["fork_key"], r["src"]): r["label"] for r in rows}
t("конверт агента разобран, все четыре ветки на месте",
  len(rows) == 4 and by.get(("k_prodazhi", "register_расчетыпробные"))
  == "долг и предоплата клиентов, а не факт отгрузки", rows)

# Лишние поля: чужой класс, чужая ветка, посторонние ключи — отбрасываются.
TEXT_EXTRA = """
{"forks":[
 {"fork_key":"k_zakupki","labels":{
   "register_закупкипробные":"аналитика закупок",
   "document_чужойдокумент":"выдуманная мусорная подпись"},
  "unexpected":"поле"},
 {"fork_key":"k_chuzhoy","labels":{"register_закупкипробные":"выдуманная мусорная подпись"}}
],"extra":42}
"""
rows2 = P.parse_labels(TEXT_EXTRA, PAY)
keys2 = {(r["fork_key"], r["src"]) for r in rows2}
t("чужая ветка известного класса отброшена",
  ("k_zakupki", "document_чужойдокумент") not in keys2, rows2)
t("чужой fork_key отброшен целиком",
  not any(k[0] == "k_chuzhoy" for k in keys2), rows2)
t("известная ветка при мусоре вокруг выжила",
  ("k_zakupki", "register_закупкипробные") in keys2, rows2)

# Пропуск src: вторая ветка класса не названа — её нет, первая пишется.
TEXT_MISS = """
{"forks":[{"fork_key":"k_prodazhi","labels":{
  "document_отгрузкапробная":"оформленные отгрузки клиентам"}}]}
"""
rows3 = P.parse_labels(TEXT_MISS, PAY)
t("пропущенная ветка отсутствует, названная пишется",
  {(r["fork_key"], r["src"]) for r in rows3}
  == {("k_prodazhi", "document_отгрузкапробная")}, rows3)

# Пустая подпись — не ответ.
rows4 = P.parse_labels(
    '{"forks":[{"fork_key":"k_zakupki","labels":{'
    '"register_закупкипробные":"  ",'
    '"document_поступлениепробное":"документы поступления"}}]}', PAY)
t("пустая подпись отброшена, соседняя цела",
  {(r["fork_key"], r["src"]) for r in rows4}
  == {("k_zakupki", "document_поступлениепробное")}, rows4)

# Битый JSON и не-словарь labels — пустой разбор без исключения.
t("битый JSON — пустой разбор, не падение",
  P.parse_labels("not json at all", PAY) == [])
t("обрезанный JSON — пустой разбор, не падение",
  P.parse_labels('{"forks":[{"fork_key":"k_zakupki","labels":{"reg', PAY) == [])
t("labels не словарём — класс пропущен, не падение",
  P.parse_labels('{"forks":[{"fork_key":"k_zakupki","labels":["x"]}]}', PAY) == [])

# Сырой JSON без конверта `openclaw --json` — через main() (запасной путь: [замер
# 15.08] text_from_agent такой ответ отдавал пустым, и дым словил цикл ретрая).
import tempfile  # noqa: E402
with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
    f.write(TEXT_MISS)
    raw_path = f.name
with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
    json.dump(PAY, f)
    pay_path = f.name
rows_path = raw_path + ".rows"
P.main(["x", raw_path, pay_path, rows_path])
got = {(r["fork_key"], r["src"]) for r in json.load(open(rows_path))}
t("сырой JSON без конверта разбирается (запасной путь main)",
  got == {("k_prodazhi", "document_отгрузкапробная")}, got)
for p in (raw_path, pay_path, rows_path):
    os.unlink(p)

print()
if FAIL:
    print("ИТОГ: FAIL — %d из %d: %s" % (len(FAIL), len(FAIL) + PASS, "; ".join(FAIL)))
    sys.exit(1)
print("ИТОГ: ok — все %d проверок прошли" % PASS)
