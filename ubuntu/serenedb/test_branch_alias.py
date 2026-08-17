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

# --- инфра/биллинг: не ответ модели, разбор → 0 строк ---
ERR_BILL = (
    "GatewayClientRequestError: FailoverError: deepseek returned a billing error "
    "— your API key has run out of credits"
)
ERR_LOCK = "SessionWriteLockTimeoutError: gateway write lock"
ERR_SUM = "Summarization failed: context too large"
t("billing error в stderr — инфра", P.is_infra_failure(ERR_BILL))
t("SessionWriteLock — инфра", P.is_infra_failure(ERR_LOCK))
t("Summarization failed — инфра", P.is_infra_failure(ERR_SUM))
t("обычный JSON ответ — не инфра", not P.is_infra_failure(ENV))
rows_err = P.parse_labels(ERR_BILL, PAY)
t("ответ-ошибка (текст billing) → ноль записей", rows_err == [], rows_err)
ENV_ERR = json.dumps({"result": {"payloads": [{"text": ERR_BILL}]}}, ensure_ascii=False)
rows_env_err = P.parse_labels(P.text_from_agent(ENV_ERR), PAY)
t("конверт со служебной ошибкой → ноль записей", rows_env_err == [], rows_env_err)

# --- vLLM/инфра (замер 17.08 okna: HTML/cooldown списывали пустышки) ---
ERR_HTML = (
    "GatewayClientRequestError: FailoverError: The provider returned an HTML "
    "error page instead of an API response."
)
ERR_MODEL = "Error: vllm can't find the model you're using right now."
ERR_COOL = (
    "FallbackSummaryError: All models failed (1): vllm/Qwen3.8-27B: "
    "Provider vllm is in cooldown"
)
ERR_PAGE = "<!DOCTYPE html><html><body>502 Bad Gateway</body></html>"
t("HTML error page — инфра", P.is_infra_failure(ERR_HTML))
t("model not found — инфра", P.is_infra_failure(ERR_MODEL))
t("vLLM cooldown — инфра", P.is_infra_failure(ERR_COOL))
t("сырой HTML вместо JSON — инфра", P.is_infra_failure(ERR_PAGE))
t("обычный JSON после vLLM-классов — не инфра", not P.is_infra_failure(ENV))

# --infra-check: нет файла ans → не исключение, классификация по stderr.
import tempfile as _tf  # noqa: E402
_err_p = _tf.NamedTemporaryFile("w", suffix=".err", delete=False)
_err_p.write(ERR_HTML)
_err_p.close()
_missing_ans = _err_p.name + ".no-ans"
rc_infra = P.main(["x", "--infra-check", _err_p.name, _missing_ans])
t("--infra-check HTML без ans → стоп (0)", rc_infra == 0, rc_infra)
os.unlink(_err_p.name)

import alias_infer_gateway as IG  # noqa: E402
t("транспорт умолчание — gateway", IG.infer_transport_flag({}) == "--gateway")
t("BRANCH_ALIAS_INFER=local — --local",
  IG.infer_transport_flag({"BRANCH_ALIAS_INFER": "local"}) == "--local")
t("неизвестное значение транспорта — gateway",
  IG.infer_transport_flag({"BRANCH_ALIAS_INFER": "rpc"}) == "--gateway")

print()
if FAIL:
    print("ИТОГ: FAIL — %d из %d: %s" % (len(FAIL), len(FAIL) + PASS, "; ".join(FAIL)))
    sys.exit(1)
print("ИТОГ: ok — все %d проверок прошли" % PASS)
