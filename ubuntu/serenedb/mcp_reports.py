#!/usr/bin/env python3
"""
MCP-сервер `report_1c` — умная аналитика/отчёты по витрине SereneDB для OpenClaw-бота.
Рядом с `ask_1c` (RAG/факты): `report_1c` — точные агрегации/срезы/«топы» по ВСЕМ строкам.

Роль (docs/SERENEDB.md): человек → бот → инструмент report_1c → NL превращается в read-only
SELECT по реальной схеме (LLM понимает намерение, код строит/валидирует запрос) → SereneDB
считает → таблица + САМ SQL (прозрачность трактовки). Числа — из SQL, не из LLM.

Подключение штатно: openclaw mcp add second-brain-reports
  --url http://127.0.0.1:6015/mcp --transport streamable-http --include report_1c

Env: MCP_HOST/MCP_PORT (default 127.0.0.1:6015) + см. serene_report.py.
"""
import os

from mcp.server.fastmcp import FastMCP

from serene_report import format_table, run_report

MCP_HOST = os.environ.get("MCP_HOST", "127.0.0.1")
MCP_PORT = int(os.environ.get("MCP_PORT", "6015"))

mcp = FastMCP("second-brain-reports", host=MCP_HOST, port=MCP_PORT)


@mcp.tool()
def report_1c(question: str) -> str:
    """Аналитика/отчёт по данным 1С: точные агрегации, суммы, счётчики, «топы», срезы по
    периодам — по ВСЕМ строкам витрины (не по образцу). Используй для вопросов «сколько»,
    «сумма», «топ», «по месяцам/городам/контрагентам», «динамика», таблицы и графики.

    Возвращает готовую ТАБЛИЦУ + сам SQL-запрос (для прозрачности). Числа посчитаны запросом
    к базе — переноси их клиенту точь-в-точь, не меняй и не добавляй свои. Если вернулась
    ошибка/[ОТЧЁТ НЕ ВЫПОЛНЕН] — так и скажи, не выдумывай цифры.

    :param question: вопрос-отчёт на естественном языке (напр. «топ-5 городов по числу банков»).
    """
    try:
        res = run_report(question)
    except Exception as e:  # noqa: BLE001
        return f"[ОШИБКА ОТЧЁТА: {type(e).__name__}] — сообщи клиенту, что отчёт не удалось построить."
    return format_table(res)


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
