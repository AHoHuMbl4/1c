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
# Шесть штатных моделей ранжирования движка. Седьмая, indri_dirichlet, исключена
# замером: в нашей сборке она в этой форме запроса молча отдаёт ноль строк.
# Список сужается окружением: правка, которая модель ранжирования не трогает (вес поля,
# бакеты булева запроса), проверяется прогоном на ОДНОЙ модели — иначе каждый замер
# стоит шести перезапусков боевого сервиса и меряет заодно то, что не менялось.
SCORERS = [s for s in os.environ.get(
    "AB_SCORERS", "bm25,bm25_b0,tfidf,lm_jm,lm_dirichlet,dfi").split(",") if s]

# Приёмочный набор лежит в ФАЙЛЕ ДАННЫХ, а не в коде. Прежде пары «вопрос → эталонный
# SQL» были записаны здесь же, и вместе с ними в программу попадали имена сущностей,
# реквизитов и значения конкретной базы («Ромашка», «КАЗАН», `СуммаДокумента`). На чужой
# конфигурации такой замер не воспроизводится, а править пришлось бы код — то есть это
# был хардкод, ничем не отличающийся от прочих.
GOLD_FILE = os.environ.get(
    "AB_GOLD_FILE", os.path.join(os.path.dirname(os.path.abspath(__file__)), "ab-gold.tsv"))


def load_gold(path):
    """Пары «вопрос → SQL» из файла. Строка: вопрос, табуляция, запрос."""
    out = []
    try:
        fh = open(path, encoding="utf-8")
    except OSError as e:
        sys.stderr.write("нет набора вопросов %s: %s\n" % (path, e))
        sys.exit(1)
    with fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            if "\t" not in line:
                sys.stderr.write("строка без табуляции пропущена: %s\n" % line[:60])
                continue
            q, sql = line.split("\t", 1)
            out.append((q.strip(), sql.strip()))
    if not out:
        sys.stderr.write("набор вопросов пуст: %s\n" % path)
        sys.exit(1)
    return out


GOLD = load_gold(GOLD_FILE)


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
    # Разделители разрядов — ТЕ ЖЕ, что понимает гейт (`serene_ask.NUMTOK`), включая
    # НЕРАЗРЫВНЫЙ пробел U+00A0. Иначе набор не видит числа, которые система отдаёт
    # правильно: [замер 28.07] после перехода на подстановку чисел кодом ответы стали
    # печататься с U+00A0, и набор показал 1 из 8 при восьми верных ответах.
    # Определение «что считается разделителем разрядов» обязано быть одно на проект.
    return {re.sub(r"\D", "", m) for m in re.findall(
        "[\\d\u0020\u00a0\u2007\u2009\u202f\u200b'.,]{1,}", text or "")
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
