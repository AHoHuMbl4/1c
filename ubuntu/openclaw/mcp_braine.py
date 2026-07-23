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


def _braine_ask(question: str, prev_turn: str | None = None) -> dict:
    body = json.dumps({"question": question, "prev_turn": prev_turn}).encode("utf-8")
    req = urllib.request.Request(f"{BRAINE_URL}/ask", data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    if BRAINE_TOKEN:
        req.add_header("Authorization", f"Bearer {BRAINE_TOKEN}")
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


@mcp.tool()
def ask_1c(question: str) -> str:
    """Задать вопрос «второму мозгу» компании по данным из 1С (контрагенты, продажи,
    склад, деньги, документы и т.п.). Возвращает ПРОВЕРЕННЫЙ ответ с фактами из 1С.

    ВАЖНО для бота: отвечай клиенту ТОЛЬКО фактами из результата этого инструмента —
    не добавляй и не меняй цифры/даты/имена. Если инструмент вернул маркер «НЕТ ДАННЫХ» —
    так и скажи клиенту, не выдумывай.

    :param question: вопрос на естественном языке о данных компании.
    """
    try:
        data = _braine_ask(question)
    except urllib.error.HTTPError as e:
        return f"[ОШИБКА второго мозга: HTTP {e.code}] — сообщи клиенту, что не удалось получить данные."
    except Exception as e:  # noqa: BLE001
        return f"[ОШИБКА второго мозга: {type(e).__name__}] — сообщи клиенту, что не удалось получить данные."

    kind = data.get("kind", "")
    text = (data.get("text") or "").strip()
    sources = data.get("sources") or []

    if kind == "no_data" or not text:
        return "[НЕТ ДАННЫХ во втором мозге по этому вопросу] — сообщи клиенту, что таких данных нет; НЕ выдумывай."

    out = text
    if sources:
        out += "\n\nИсточники: " + ", ".join(sources[:5])
    return out


if __name__ == "__main__":
    if not BRAINE_TOKEN:
        import sys
        sys.stderr.write("WARN: BRAINE_TOKEN пуст — braine ответит 401\n")
    # Streamable HTTP: эндпоинт /mcp на MCP_HOST:MCP_PORT
    mcp.run(transport="streamable-http")
