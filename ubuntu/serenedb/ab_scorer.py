#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A/B модели ранжирования на золотом наборе вопросов.

Правило владельца: если у движка есть штатный механизм — берём его, потому что у них он
проверен на больших данных, а наша конструкция поверх — гипотеза. Спорить об этом нельзя,
можно только замерить: один и тот же набор вопросов прогоняется на каждой модели
ранжирования, ответы сверяются с независимым эталоном.

Запуск на сервере: python3 ab_scorer.py
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

DSN = "host=127.0.0.1 port=7890 user=postgres dbname=postgres"
URL = "http://127.0.0.1:8091/ask"
SCORERS = ["bm25", "bm25_b0", "tfidf"]

# Вопрос -> SQL, считающий правду независимо от системы поиска.
GOLD = [
    ("Сколько всего мы продали?",
     "SELECT sum(\"СуммаДокумента\")::BIGINT FROM document_реализациятоваровуслуг"),
    ("What is the total amount of all sales?",
     "SELECT sum(\"СуммаДокумента\")::BIGINT FROM document_реализациятоваровуслуг"),
    ("На какую сумму мы продали ООО Северный Ветер?",
     "SELECT sum(d.\"СуммаДокумента\")::BIGINT FROM document_реализациятоваровуслуг d "
     "JOIN catalog_контрагенты k ON k.\"Ref_Key\"=d.\"Контрагент_Key\" "
     "WHERE k.\"Description\" LIKE '%Северный Ветер%'"),
    ("Какие поступления были от ООО ТехноСнаб?",
     "SELECT sum(d.\"СуммаДокумента\")::BIGINT FROM document_поступлениетоваровуслуг d "
     "JOIN catalog_контрагенты k ON k.\"Ref_Key\"=d.\"Контрагент_Key\" "
     "WHERE k.\"Description\" LIKE '%ТехноСнаб%'"),
    ("Покажи продажи за декабрь 2025 года",
     "SELECT sum(\"СуммаДокумента\")::BIGINT FROM document_реализациятоваровуслуг "
     "WHERE \"Date\">='2025-12-01' AND \"Date\"<'2026-01-01'"),
    ("Какие продажи были на сумму больше 500000 рублей?",
     "SELECT sum(\"СуммаДокумента\")::BIGINT FROM document_реализациятоваровуслуг "
     "WHERE \"СуммаДокумента\">500000"),
    ("Сколько банков в Казани?",
     "SELECT count(*) FROM catalog_классификаторбанков WHERE upper(\"Город\") LIKE '%КАЗАН%'"),
    ("Что покупало ООО Ромашка?",
     "SELECT sum(d.\"СуммаДокумента\")::BIGINT FROM document_реализациятоваровуслуг d "
     "JOIN catalog_контрагенты k ON k.\"Ref_Key\"=d.\"Контрагент_Key\" "
     "WHERE k.\"Description\" LIKE '%Ромашка%'"),
]


def truth(sql):
    p = subprocess.run(["psql", DSN, "-tA", "-c", sql], capture_output=True, text=True)
    return (p.stdout or "").strip()


def token(path="/etc/1c-serene-ask.env"):
    for line in open(path, encoding="utf-8"):
        if line.startswith("ASK_TOKEN="):
            return line.split("=", 1)[1].strip()
    return ""


TOK = token()


def ask(q):
    body = json.dumps({"question": q}).encode()
    req = urllib.request.Request(URL, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    if TOK:
        req.add_header("Authorization", "Bearer " + TOK)
    t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return json.loads(r.read()), round(time.time() - t, 2)
    except Exception as e:                       # noqa: BLE001
        return {"text": "", "diag": {"error": str(e)[:80]}}, round(time.time() - t, 2)


def digits(text):
    """Цифровые последовательности ответа — сравниваем по ним, без учёта разрядки."""
    return {re.sub(r"\D", "", m) for m in re.findall(r"[\d   .,]{1,}", text or "")
            if re.sub(r"\D", "", m)}


def restart(scorer):
    conf = "/etc/1c-serene-ask.env"
    lines = [l for l in open(conf, encoding="utf-8") if not l.startswith("ASK_SCORER=")]
    lines.append("ASK_SCORER=%s\n" % scorer)
    open(conf, "w", encoding="utf-8").writelines(lines)
    subprocess.run(["systemctl", "restart", "1c-serene-ask.service"], check=True)
    time.sleep(4)


def main():
    gold = [(q, truth(sql)) for q, sql in GOLD]
    print("эталоны: " + ", ".join("%s" % t for _q, t in gold))
    table = {}
    for sc in SCORERS:
        restart(sc)
        hits, secs, rows = 0, 0.0, []
        for q, want in gold:
            d, sec = ask(q)
            text = d.get("text") or ""
            claims = (d.get("diag") or {}).get("claims") or {}
            got = digits(text) | {re.sub(r"\D", "", str(v)) for v in claims.values()
                                  if v is not None}
            ok = re.sub(r"\D", "", want) in got
            hits += 1 if ok else 0
            secs += sec
            rows.append((q, ok, (d.get("diag") or {}).get("focus"), sec))
        table[sc] = (hits, round(secs / len(gold), 2), rows)
        print("\n== %s: верных %d/%d, средняя %.2f с" % (sc, hits, len(gold), secs / len(gold)))
        for q, ok, focus, sec in rows:
            print("   %s %-46s %-38s %.1fс" % ("+" if ok else "-", q[:46], (focus or "—")[:38], sec))

    print("\n" + "=" * 62)
    best = max(table.items(), key=lambda kv: (kv[1][0], -kv[1][1]))
    for sc, (hits, avg, _r) in table.items():
        print("  %-9s верных %d/%d  средняя %.2f с%s"
              % (sc, hits, len(gold), avg, "   <= лучший" if sc == best[0] else ""))
    # Отметка о прогоне: по ней хук перед выкатом понимает, был ли замер ПОСЛЕ
    # последней правки исходников. Ставится только реальным прогоном, не руками.
    try:
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        open(os.path.join(root, ".claude", ".golden-last-run"), "w").write(
            "%s %d/%d\n" % (best[0], best[1][0], len(gold)))
    except Exception:                            # noqa: BLE001
        pass
    return best[0]


if __name__ == "__main__":
    sys.exit(0 if main() else 0)
