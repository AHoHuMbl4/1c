#!/usr/bin/env python3
"""
MCP-сервер поверх «второго мозга» (braine) — даёт OpenClaw-боту нативный инструмент
`ask_1c`, которым он черпает факты из данных 1С.

Роль в интеграции (см. docs/OPENCLAW_BOT.md):
  человек → OpenClaw-бот → инструмент ask_1c (этот сервер) → braine /ask (факты+цитаты)
  → бот формулирует живой ответ → verify-плагин сверяет факты с ответом braine → клиент

Это ВНЕШНИЙ сервис (не кастом OpenClaw): OpenClaw подключает его штатно —
  openclaw mcp add second-brain --url http://127.0.0.1:6014/mcp --transport streamable-http

braine остаётся источником истины: у него внутри anti-hallucination (гейты, дословная
сверка, обязательные цитаты). Инструмент возвращает проверенный text braine + kind +
источники. `kind=no_data` пробрасывается явным маркером, чтобы бот не сочинял.

Транспорт — Streamable HTTP (официальный MCP SDK `mcp`, FastMCP). Конфиг — env:
  BRAINE_URL   (default http://127.0.0.1:8090)
  BRAINE_TOKEN (Bearer API_TOKEN braine; обязателен)
  MCP_HOST/MCP_PORT (default 127.0.0.1:6014)
"""
import json
import os
import urllib.error
import urllib.request

from mcp.server.fastmcp import FastMCP

BRAINE_URL = os.environ.get("BRAINE_URL", "http://127.0.0.1:8090").rstrip("/")
BRAINE_TOKEN = os.environ.get("BRAINE_TOKEN", "")
MCP_HOST = os.environ.get("MCP_HOST", "127.0.0.1")
MCP_PORT = int(os.environ.get("MCP_PORT", "6014"))
TIMEOUT = float(os.environ.get("BRAINE_TIMEOUT", "180"))

mcp = FastMCP("second-brain", host=MCP_HOST, port=MCP_PORT)


# --- авторизация MCP -------------------------------------------------------------
# Сервис отдаёт данные 1С. До этой правки он слушал без всякой проверки: любой
# локальный процесс получал ответы, не зная ни одного токена, — то есть ASK_TOKEN у
# сервиса ответов и токен OData-шлюза защищали двери, рядом с которыми стояла
# открытая. Проверено прогоном: initialize + tools/call без единого заголовка
# возвращали данные витрины.
# Заголовок передаётся штатным механизмом OpenClaw: mcp.servers.<имя>.headers.
MCP_TOKEN = os.environ.get("MCP_TOKEN", "")


def _serve_with_auth(mcp_obj):
    """Поднять MCP поверх Starlette с обязательной проверкой Bearer.

    fail-closed: без токена в окружении сервис не стартует. Пустая переменная не
    должна молча открывать доступ — эту ошибку мы уже проходили на шлюзе.
    """
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


def _braine_ask(question: str, prev_turn: str | None = None) -> dict:
    body = json.dumps({"question": question, "prev_turn": prev_turn}).encode("utf-8")
    req = urllib.request.Request(f"{BRAINE_URL}/ask", data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    if BRAINE_TOKEN:
        req.add_header("Authorization", f"Bearer {BRAINE_TOKEN}")
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


# Тексты, которые видит человек, вынесены в окружение: продукт коробочный, и язык
# клиента заранее неизвестен. Описание инструмента (его читает модель бота) — на
# английском и без предметных примеров, чтобы не тянуть ответ в конкретный язык и
# не предполагать торговую конфигурацию.
NO_DATA_REPLY = os.environ.get(
    "MCP_NO_DATA_REPLY",
    "[НЕТ ДАННЫХ во втором мозге по этому вопросу] — сообщи клиенту, что таких данных "
    "нет; НЕ выдумывай.")
ERROR_REPLY = os.environ.get(
    "MCP_ERROR_REPLY",
    "[ОШИБКА второго мозга: {detail}] — сообщи клиенту, что не удалось получить данные.")
SOURCES_LABEL = os.environ.get("MCP_SOURCES_LABEL", "Источники")


@mcp.tool()
def ask_1c(question: str) -> str:
    """Ask the company's second brain about data stored in its ERP system.

    Returns a VERIFIED answer: every figure in it is checked against the database
    before it is returned. Answer the user with these facts only — do not add,
    recompute or reword numbers, dates or names. If the result carries a no-data
    marker, say so plainly instead of inventing anything.

    :param question: the user's question, in their own language, about company data.
    """
    try:
        data = _braine_ask(question)
    except urllib.error.HTTPError as e:
        return ERROR_REPLY.format(detail="HTTP %d" % e.code)
    except Exception as e:  # noqa: BLE001
        return ERROR_REPLY.format(detail=type(e).__name__)

    kind = data.get("kind", "")
    text = (data.get("text") or "").strip()
    sources = data.get("sources") or []

    if kind == "no_data" or not text:
        return NO_DATA_REPLY

    out = text
    if sources:
        out += "\n\n%s: %s" % (SOURCES_LABEL, ", ".join(sources[:5]))
    return out


if __name__ == "__main__":
    if not BRAINE_TOKEN:
        import sys
        sys.stderr.write("WARN: BRAINE_TOKEN пуст — braine ответит 401\n")
    # Streamable HTTP: эндпоинт /mcp на MCP_HOST:MCP_PORT
    _serve_with_auth(mcp)
