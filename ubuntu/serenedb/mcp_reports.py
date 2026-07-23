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
import hashlib
import os

from mcp.server.fastmcp import FastMCP

from serene_report import format_table, render_chart, run_report

MCP_HOST = os.environ.get("MCP_HOST", "127.0.0.1")
MCP_PORT = int(os.environ.get("MCP_PORT", "6015"))
# ВАЖНО: график-файл движок отдаёт клиенту только из РАЗРЕШЁННОЙ директории медиа
# (workspace бота / media-store). Иначе OutboundDeliveryError «not under an allowed directory».
# Поэтому CHART_DIR = <workspace бота>/charts, задаётся env (конфиг-нейтрально, на деплой).
CHART_DIR = os.environ.get("CHART_DIR", "/var/lib/serenedb-charts")

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
    # прозрачность — СЕРВЕРНО (владельцу в журнал), в чат клиенту SQL не уходит
    print(f"[report_1c] q={question!r} sql={res.get('sql')!r} n={res.get('n')} err={res.get('error')!r}", flush=True)
    text = format_table(res, show_sql=False)
    try:
        png = render_chart(res)
    except Exception:  # noqa: BLE001
        png = None  # график не критичен — таблица всё равно уйдёт
    if png:
        try:
            os.makedirs(CHART_DIR, exist_ok=True)
            os.chmod(CHART_DIR, 0o755)
            path = os.path.join(CHART_DIR, "chart_" + hashlib.md5(png).hexdigest()[:12] + ".png")
            with open(path, "wb") as f:
                f.write(png)
            os.chmod(path, 0o644)
            # штатный паттерн доставки: агент отправит файл клиенту инструментом message
            text += (
                f"\n\n[ГРАФИК-ФАЙЛ: {path}]\n"
                "(Отправь этот файл клиенту как изображение через инструмент message. "
                "Сам путь клиенту НЕ показывай — дай таблицу и график.)"
            )
        except Exception:  # noqa: BLE001
            pass
    return text


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
