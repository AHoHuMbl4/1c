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
# 🔴 ЭТИ СТРОКИ ЧИТАЕТ МОДЕЛЬ, А НЕ ЧЕЛОВЕК, поэтому они по-английски. Русский текст
# здесь тянул модель ответить клиенту по-русски — ровно в той ветке, ради которой ниже по
# стеку заведён `clarify_text` на языке вопроса.
NO_DATA_REPLY = os.environ.get(
    "MCP_NO_DATA_REPLY", "[NO DATA] Tell the user there is no such data.")
ERROR_REPLY = os.environ.get(
    "MCP_ERROR_REPLY", "[SERVICE ERROR: {detail}] Tell the user the data is unavailable.")
CLARIFY_LABEL = os.environ.get("MCP_CLARIFY_LABEL", "OPTIONS")
# 🔴 ГЕЙТ ОТКЛОНИЛ ФОРМУЛИРОВКУ — НО ЧИСЛА ПОСЧИТАНЫ И ВЕРНЫ. Сервис отдаёт их
# `kind=figures` отдельным полем и прямо говорит в коде: «отдаём структурой, а не своей
# прозой… вызывающий формулирует сам». Мост этого не делал: он брал `text`, а там в этой
# ветке лежит ОТКАЗ (`ASK_TOTAL_TEXT` пуст по умолчанию и не задан ни в одном env, значит
# `refuse_text(question)`). Итог — отказ при наличии посчитанных данных, то есть ровно
# то, что п. 21 контракта называет дефектом, а не осторожностью.
FIGURES_HINT = os.environ.get(
    "MCP_FIGURES_HINT",
    "[FIGURES] The wording of the draft answer could not be verified, so it was dropped. "
    "The values below ARE computed by the database and are correct. Answer the user's "
    "question from these values, copying the digits exactly. Do not add any other figure.")
# Что не поместилось/не дошло (п. 13: молчаливая потеря = дефект). До 02.08 поле
# `partial` мост не передавал вовсе, хотя `API_ASK` обещает его как видимое клиенту.
PARTIAL_HINT = os.environ.get(
    "MCP_PARTIAL_HINT",
    "[PARTIAL] Not everything was taken into account. Tell the user so in one short "
    "sentence, using the figures below as they are.")
CLARIFY_HINT = os.environ.get(
    "MCP_CLARIFY_HINT",
    "[CLARIFICATION NEEDED] Put the question below to the user in your own words with the "
    "options. Then call this tool again with the same question and `focus` (and `measure` "
    "if a quantity was chosen), copied verbatim from the list.")


def _num(v):
    """Число для модели: без хвоста .0 у целых — иначе гейт сверяет «1236800.0» с «1236800».

    Формат тот же, что у `serene_ask` в его собственных подстановках, и это не косметика:
    белый список гейта собирается из ТЕКСТА, который ушёл боту.
    """
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return str(v)
    return "%d" % v if float(v) == int(v) else "%.2f" % v


def _kv_block(label, d):
    """Плоский блок `ключ=значение` — машинный, без прозы: язык клиента неизвестен."""
    if not isinstance(d, dict):
        return ""
    lines = ["- %s=%s" % (k, _num(v)) for k, v in d.items() if v is not None]
    return ("%s:\n%s" % (label, "\n".join(lines))) if lines else ""


def _with_partial(out, data):
    """Дописать, что учтено не всё (п. 13). Числа отсюда уходят боту, значит гейт их видит."""
    block = _kv_block("PARTIAL", data.get("partial"))
    return out + "\n\n" + PARTIAL_HINT + "\n\n" + block if block else out


@mcp.tool()
def ask_1c(question: str, focus: str = "", measure: str = "",
           context: str = "") -> str:
    """Ask about data stored in the company's ERP system.

    Figures come from the database and are checked before they are returned; pass them
    on as they are.

    The reply may instead ask to CLARIFY, when the question fits several record types or
    several quantities. Then put that question to the user and call this tool again with
    the same question plus `focus` (and `measure` if a quantity was chosen), copied
    verbatim from the list given.

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
        return _with_partial(out, data)

    # 🔴 ГЕЙТ ОТКЛОНИЛ ПРОЗУ, ЧИСЛА ПОСЧИТАНЫ. `text` в этой ветке — НЕ ответ: это либо
    # отказ (`refuse_text`), либо та самая непрошедшая формулировка. Пересылать его боту
    # значит отдать отказ, имея данные. Отдаём то, ради чего ветка и заведена, — числа.
    if kind == "figures":
        block = _kv_block("FIGURES", data.get("figures"))
        if block:
            return _with_partial(FIGURES_HINT + "\n\n" + block, data)

    if kind == "no_data" or not text:
        return NO_DATA_REPLY

    # Величина, по которой считали, названа рядом с ответом: у сущности бывает девять
    # величин со словом «сумма», и молчаливый выбор неотличим от догадки (п. 12).
    # `serene_ask` уже дописывает это в текст, если модель не назвала сама, — здесь
    # поле пробрасывается отдельно, чтобы бот мог сказать это своими словами.
    m = (data.get("measure") or "").strip()
    if m and m.lower() not in text.lower():
        text += "\n\n[величина: %s]" % m
    return _with_partial(text, data)


if __name__ == "__main__":
    if not ASK_TOKEN:
        sys.stderr.write("WARN: ASK_TOKEN пуст — сервис ответов вернёт 401\n")
    _serve_with_auth(mcp)
