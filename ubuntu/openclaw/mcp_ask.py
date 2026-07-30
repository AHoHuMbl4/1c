#!/usr/bin/env python3
"""
MCP-сервер поверх `serene_ask` — даёт OpenClaw-боту инструмент `ask_1c`, которым он
черпает факты из данных 1С через SereneDB.

Роль в интеграции:
  человек → OpenClaw-бот (перефразирует вопрос по вики) → инструмент `ask_1c` (этот
  сервер) → `serene_ask` (поиск в SereneDB, счёт в базе, гейт чисел) → бот формулирует
  живой ответ → verify-плагин сверяет числа → клиент

🔴 ЗАЧЕМ НОВЫЙ МОСТ, А НЕ ПРАВКА СТАРОГО. Прежний `mcp_braine.py` обращается к
`BRAINE_URL` (:8090) — к слою braine, выведенному из продукта; [замер 30.07] порт не
слушает вовсе, и бот на любой вопрос отвечал «сервер 1С не отвечает». Это второй раз
класс `HOW_NOT_TO §2.14`: вывод компонента не закончен, пока не убраны его связки.
Решение владельца 30.07: новый мост, бот отвечает по второй базе (`ut_test`).

🔴 ЧЕМ ЭТОТ МОСТ ОТЛИЧАЕТСЯ ПО СУТИ: он пробрасывает `focus`, `measure` и `context`,
поэтому работает ЦЕПОЧКА, а не один выстрел:

  вопрос → (если сомнение) уточнение о сущности → уточнение о величине → ответ

Без этих полей уточнение оставалось односторонним: сервис спрашивал, а ответ человека
вернуть было нечем. Порядок задан п. 21 контракта: ответ → уточняющий вопрос → отказ.

`context` — предыдущий разговор; его ведёт OpenClaw. Он используется ТОЛЬКО арбитром
внутри `serene_ask` (выбор между готовыми ответами) и в отбор данных не попадает.

Транспорт — Streamable HTTP (официальный MCP SDK `mcp`, FastMCP). Конфиг — env:
  ASK_URL    (default http://127.0.0.1:8099)
  ASK_TOKEN  (Bearer сервиса ответов; обязателен, иначе он вернёт 401)
  MCP_HOST/MCP_PORT (default 127.0.0.1:6016)
  MCP_TOKEN  (Bearer этого сервера; без него сервис НЕ стартует)
"""
import json
import os
import sys
import urllib.error
import urllib.request

from mcp.server.fastmcp import FastMCP

ASK_URL = os.environ.get("ASK_URL", "http://127.0.0.1:8099").rstrip("/")
ASK_TOKEN = os.environ.get("ASK_TOKEN", "")
MCP_HOST = os.environ.get("MCP_HOST", "127.0.0.1")
MCP_PORT = int(os.environ.get("MCP_PORT", "6016"))
TIMEOUT = float(os.environ.get("ASK_TIMEOUT", "300"))

mcp = FastMCP("serene-ask", host=MCP_HOST, port=MCP_PORT)

# --- авторизация MCP -------------------------------------------------------------
# Сервис отдаёт данные 1С, поэтому дверь закрыта. fail-closed: пустой токен не должен
# молча открывать доступ — эту ошибку мы уже проходили на шлюзе и на прежнем мосте.
# Заголовок передаётся штатным механизмом OpenClaw: `mcp.servers.<имя>.headers`.
MCP_TOKEN = os.environ.get("MCP_TOKEN", "")


def _serve_with_auth(mcp_obj):
    import uvicorn
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import JSONResponse

    if not MCP_TOKEN:
        sys.stderr.write("FATAL: MCP_TOKEN не задан — сервис отдавал бы данные 1С без "
                         "авторизации. Задайте токен в окружении.\n")
        raise SystemExit(2)

    class Auth(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            if request.headers.get("authorization", "") != "Bearer " + MCP_TOKEN:
                return JSONResponse({"error": "unauthorized"}, status_code=401)
            return await call_next(request)

    app = mcp_obj.streamable_http_app()
    app.add_middleware(Auth)
    uvicorn.run(app, host=MCP_HOST, port=MCP_PORT, log_level="warning")


def _ask(question, focus=None, measure=None, context=None):
    payload = {"question": question}
    if focus:
        payload["focus"] = focus
    if measure:
        payload["measure"] = measure
    if context:
        payload["context"] = context
    req = urllib.request.Request(ASK_URL + "/ask",
                                 data=json.dumps(payload).encode("utf-8"),
                                 method="POST")
    req.add_header("Content-Type", "application/json")
    if ASK_TOKEN:
        req.add_header("Authorization", "Bearer " + ASK_TOKEN)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


# Тексты, которые видит человек, вынесены в окружение: продукт коробочный, и язык
# клиента заранее неизвестен. Описание инструмента (его читает модель бота) — на
# английском и без предметных примеров, чтобы не тянуть ответ в конкретный язык и не
# предполагать торговую конфигурацию.
NO_DATA_REPLY = os.environ.get(
    "MCP_NO_DATA_REPLY",
    "[НЕТ ДАННЫХ по этому вопросу] — сообщи клиенту, что таких данных нет; НЕ выдумывай.")
ERROR_REPLY = os.environ.get(
    "MCP_ERROR_REPLY",
    "[ОШИБКА сервиса данных: {detail}] — сообщи клиенту, что не удалось получить данные.")
CLARIFY_LABEL = os.environ.get("MCP_CLARIFY_LABEL", "ВАРИАНТЫ")
CLARIFY_HINT = os.environ.get(
    "MCP_CLARIFY_HINT",
    "[НУЖНО УТОЧНЕНИЕ] Задай клиенту вопрос ниже своими словами и по-человечески, "
    "перечислив варианты. Получив выбор, вызови инструмент СНОВА с тем же вопросом и "
    "полем focus (и measure, если выбиралась величина) — значения бери ДОСЛОВНО из "
    "перечня. Ничего из служебных имён клиенту не показывай.")


@mcp.tool()
def ask_1c(question: str, focus: str = "", measure: str = "",
           context: str = "") -> str:
    """Ask about data stored in the company's ERP system.

    Every figure comes from the database itself and is checked before it is returned.
    Answer the user with these facts only — do not add, recompute or reword numbers,
    dates or names.

    The answer may instead be a request to CLARIFY: the question fits several record
    types, or several different quantities. In that case ask the user which one they
    mean, then call this tool again with the same question plus `focus` (and `measure`
    when a quantity was being chosen), copying those values verbatim from the list you
    were given. Never pick one yourself and never invent such a value.

    :param question: the user's question, in their own language, about company data.
    :param focus: record type chosen by the user after a clarification, verbatim.
    :param measure: quantity chosen by the user after a clarification, verbatim.
    :param context: the conversation so far, used only to disambiguate the question.
    """
    try:
        data = _ask(question, focus or None, measure or None, context or None)
    except urllib.error.HTTPError as e:
        return ERROR_REPLY.format(detail="HTTP %d" % e.code)
    except Exception as e:                     # noqa: BLE001 — сеть/таймаут
        return ERROR_REPLY.format(detail=type(e).__name__)

    kind = data.get("kind", "")
    text = (data.get("text") or "").strip()

    # Отказ сервиса — НЕ то же самое, что отсутствие данных (п. 18): клиенту надо
    # сказать про сбой, а не про пустую базу, иначе он решит, что данных нет.
    if kind == "unavailable":
        return ERROR_REPLY.format(detail=text[:120] or "unavailable")

    if kind == "clarify":
        opts = data.get("options") or []
        lines = []
        for o in opts:
            if not isinstance(o, dict):
                continue
            # `measure` заполнено — выбирается величина; иначе выбирается сущность.
            if o.get("measure"):
                lines.append("- %s | measure=%s | focus=%s"
                             % (o.get("label") or o["measure"], o["measure"],
                                o.get("src") or ""))
            elif o.get("src"):
                lines.append("- %s | focus=%s" % (o.get("label") or o["src"], o["src"]))
        out = CLARIFY_HINT
        if text:
            out += "\n\n" + text
        if lines:
            out += "\n\n%s:\n%s" % (CLARIFY_LABEL, "\n".join(lines))
        return out

    if kind == "no_data" or not text:
        return NO_DATA_REPLY

    # Величина, по которой считали, названа рядом с ответом: у сущности бывает девять
    # величин со словом «сумма», и молчаливый выбор неотличим от догадки (п. 12).
    # `serene_ask` уже дописывает это в текст, если модель не назвала сама, — здесь
    # поле пробрасывается отдельно, чтобы бот мог сказать это своими словами.
    m = (data.get("measure") or "").strip()
    if m and m.lower() not in text.lower():
        text += "\n\n[величина: %s]" % m
    return text


if __name__ == "__main__":
    if not ASK_TOKEN:
        sys.stderr.write("WARN: ASK_TOKEN пуст — сервис ответов вернёт 401\n")
    _serve_with_auth(mcp)
