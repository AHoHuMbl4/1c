#!/usr/bin/env python3
"""
Веб-страница настройки ETL: «галочки — что тянуть из 1С».

Показывает список всех непустых сущностей 1С (справочники/документы) с числом
записей; человек отмечает бизнес-разделы (продажи, склад, деньги, контрагенты…)
и сохраняет. Выбор пишется в /etc/1c-etl-selected.txt — ETL тянет только его.

Разовая настройка под конкретный бизнес: открыл страницу → отметил → сохранил →
дальше всё автоматически (ночной ETL по выбору). Отдельный лёгкий инструмент,
не трогает RAG-бота. Только stdlib.
"""
import html
import json
import os
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import oc_discover  # noqa: E402

LISTEN_HOST = os.environ.get("UI_HOST", "0.0.0.0")
LISTEN_PORT = int(os.environ.get("UI_PORT", "6012"))
CACHE = os.environ.get("UI_CACHE", "/var/lib/1c-config-ui/entities.json")
SELECTED = os.environ.get("ETL_SELECTED_FILE", "/etc/1c-etl-selected.txt")


def load_cache():
    try:
        return json.load(open(CACHE, encoding="utf-8"))
    except Exception:
        return []


def load_selected():
    try:
        return {l.strip() for l in open(SELECTED, encoding="utf-8") if l.strip()}
    except Exception:
        return set()


def save_selected(sets):
    os.makedirs(os.path.dirname(SELECTED), exist_ok=True)
    with open(SELECTED, "w", encoding="utf-8") as f:
        f.write("\n".join(sorted(sets)) + "\n")


PAGE = """<!doctype html><html lang=ru><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Настройка выгрузки 1С → второй мозг</title>
<style>
 body{{font:15px/1.4 system-ui,sans-serif;margin:0;background:#f6f7f9;color:#1a1a1a}}
 header{{background:#1a2b4a;color:#fff;padding:14px 20px}}
 header b{{font-size:18px}} .sub{{opacity:.8;font-size:13px;margin-top:3px}}
 .bar{{position:sticky;top:0;background:#fff;border-bottom:1px solid #ddd;padding:10px 20px;display:flex;gap:10px;align-items:center;flex-wrap:wrap}}
 input[type=search]{{padding:7px 10px;border:1px solid #ccc;border-radius:6px;min-width:220px}}
 button{{padding:8px 14px;border:0;border-radius:6px;cursor:pointer;font-size:14px}}
 .save{{background:#2563eb;color:#fff}} .gh{{background:#e5e7eb}} .scan{{background:#0a7}}
 table{{border-collapse:collapse;width:100%;background:#fff}}
 td,th{{padding:7px 12px;border-bottom:1px solid #eee;text-align:left}}
 th{{background:#fafafa;position:sticky;top:57px}}
 tr.sys{{color:#999}} tr:hover{{background:#f0f6ff}}
 .cnt{{text-align:right;font-variant-numeric:tabular-nums;color:#555}}
 .tag{{font-size:11px;padding:1px 6px;border-radius:4px;background:#eee;color:#777}}
 .biz{{background:#dcfce7;color:#166534}}
 .wrap{{padding:0 20px 40px}}
</style></head><body>
<header><b>Настройка выгрузки 1С → «второй мозг»</b>
<div class=sub>Отметь бизнес-разделы, которые нужны боту. Служебные классификаторы (серые) обычно не нужны. Сохрани — дальше выгрузка сама.</div></header>
<form method=post action=/save>
<div class=bar>
 <input type=search id=q placeholder="поиск по имени…" oninput=flt()>
 <button type=button class=gh onclick="pick(true)">отметить видимые</button>
 <button type=button class=gh onclick="pick(false)">снять видимые</button>
 <span id=stat></span>
 <span style=flex:1></span>
 <button class=save type=submit>💾 Сохранить выбор ({sel_n})</button>
 <button class=scan formaction=/scan formmethod=post>🔄 Пересканировать 1С</button>
</div>
<div class=wrap><table id=t>
<tr><th></th><th>тип</th><th>сущность</th><th class=cnt>записей</th><th></th></tr>
{rows}
</table>
<p style=color:#777>Список сущностей с данными: {total}. Пусто? Нажми «Пересканировать 1С» (~несколько минут).</p>
</div></form>
<script>
function flt(){{let s=q.value.toLowerCase();for(let r of t.rows)if(r.dataset.n!==undefined)r.style.display=r.dataset.n.includes(s)?'':'none';cnt()}}
function pick(v){{for(let r of t.rows)if(r.style.display!=='none'&&r.querySelector)r.querySelector('input')&&(r.querySelector('input').checked=v);cnt()}}
function cnt(){{let n=[...t.querySelectorAll('input:checked')].length;stat.textContent=n+' отмечено'}}
t.addEventListener('change',cnt);cnt();
</script></body></html>"""


def render():
    data = load_cache()
    sel = load_selected()
    rows = []
    for r in data:
        es = r["set"]
        checked = "checked" if es in sel else ""
        cls = "sys" if r.get("system") else ""
        tag = '<span class="tag">служебн</span>' if r.get("system") else '<span class="tag biz">данные</span>'
        rows.append(
            f'<tr class="{cls}" data-n="{html.escape(r["name"].lower())}">'
            f'<td><input type=checkbox name=sel value="{html.escape(es)}" {checked}></td>'
            f'<td>{"Спр" if r["kind"]=="Catalog" else "Док"}</td>'
            f'<td>{html.escape(r["name"])}</td>'
            f'<td class=cnt>{r.get("count","?")}</td><td>{tag}</td></tr>')
    return PAGE.format(rows="\n".join(rows), total=len(data), sel_n=len(sel))


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _html(self, body, code=200):
        b = body.encode("utf-8")
        self.send_response(code); self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        if self.path.rstrip("/") in ("", "/"):
            return self._html(render())
        self._html("<h1>404</h1>", 404)

    def do_POST(self):
        n = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(n).decode("utf-8") if n else ""
        if self.path == "/save":
            sets = urllib.parse.parse_qs(body).get("sel", [])
            save_selected(sets)
            return self._html(f"<meta http-equiv=refresh content='1;url=/'>Сохранено: {len(sets)} сущностей → {SELECTED}. <a href=/>назад</a>")
        if self.path == "/scan":
            data = oc_discover.discover()
            os.makedirs(os.path.dirname(CACHE), exist_ok=True)
            json.dump(data, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)
            return self._html("<meta http-equiv=refresh content='0;url=/'>Просканировано.")
        self._html("<h1>404</h1>", 404)


if __name__ == "__main__":
    srv = ThreadingHTTPServer((LISTEN_HOST, LISTEN_PORT), H)
    sys.stderr.write(f"config-ui на http://{LISTEN_HOST}:{LISTEN_PORT}  (кэш {CACHE}, выбор {SELECTED})\n")
    srv.serve_forever()
