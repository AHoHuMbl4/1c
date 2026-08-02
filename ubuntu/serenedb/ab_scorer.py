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

# 🔴 НАБОР ПРИВЯЗАН К ИМЕНОВАННОЙ БАЗЕ, а не к одному юниту. 02.08 сервис ответов стал
# шаблонным (`1c-serene-ask@<база>`) с побазовым `/etc/1c-serene-ask-<база>.env`, и прежняя
# редакция этого не знала: она писала `ASK_SCORER` в ОБЩИЙ env (где его перекрывает
# побазовый — то есть замер молча мерил неизменённый скорер) и рестартовала нешаблонный
# юнит, чей порт держит уже поднятый экземпляр. Прогон либо падал, либо врал.
BASE = os.environ.get("AB_BASE", "postgres")
ENV_FILE = "/etc/1c-serene-ask-%s.env" % BASE
UNIT = "1c-serene-ask@%s.service" % BASE
# Общий env: там лежит только то, что одинаково для всех баз (`ASK_TOKEN`).
ENV_COMMON = "/etc/1c-serene-ask.env"


def env_value(key, *paths):
    """Значение настройки. Побазовый файл сильнее общего — тот же порядок, что в юните."""
    out = ""
    for p in paths:
        try:
            for line in open(p, encoding="utf-8"):
                if line.startswith(key + "="):
                    out = line.split("=", 1)[1].strip()
        except OSError:
            continue
    return out


DSN = os.environ.get(
    "AB_DSN", "host=127.0.0.1 port=7890 user=postgres dbname=%s" % BASE)
URL = "http://127.0.0.1:%s/ask" % (
    env_value("ASK_LISTEN_PORT", ENV_COMMON, ENV_FILE) or "8091")
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


TOK = env_value("ASK_TOKEN", ENV_COMMON, ENV_FILE)


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
    """Сменить функцию ранжирования у сервиса ИМЕНОВАННОЙ базы и перезапустить его.

    Пишем в побазовый env: он последний в списке `EnvironmentFile` юнита, то есть
    перекрывает общий. Запись в общий не имела бы никакого действия — и не имела.
    """
    lines = [l for l in open(ENV_FILE, encoding="utf-8") if not l.startswith("ASK_SCORER=")]
    lines.append("ASK_SCORER=%s\n" % scorer)
    open(ENV_FILE, "w", encoding="utf-8").writelines(lines)
    subprocess.run(["systemctl", "restart", UNIT], check=True)
    time.sleep(4)


def main():
    print("база %s, сервис %s, %s" % (BASE, URL, UNIT))
    gold = [(q, truth(sql)) for q, sql in GOLD]
    print("эталоны: " + ", ".join("%s" % t for _q, t in gold))
    # 🔴 Эталон, который не посчитался, — это молчащий прогон: сравнивать не с чем, и
    # «верных 0 из 8» означало бы не качество ответов, а неработающий psql.
    blind = [q for q, t in gold if not t]
    if blind:
        sys.stderr.write("эталон не посчитан у %d вопросов: %s\n"
                         % (len(blind), "; ".join(q[:40] for q in blind[:3])))
        return None
    table = {}
    for sc in SCORERS:
        restart(sc)
        hits, secs, rows, errs = 0, 0.0, [], 0
        for q, want in gold:
            d, sec = ask(q)
            text = d.get("text") or ""
            diag = d.get("diag") or {}
            if diag.get("error"):
                errs += 1
            claims = diag.get("claims") or {}
            got = digits(text) | {re.sub(r"\D", "", str(v)) for v in claims.values()
                                  if v is not None}
            ok = re.sub(r"\D", "", want) in got
            hits += 1 if ok else 0
            secs += sec
            rows.append((q, ok, diag.get("focus"), sec))
        table[sc] = (hits, round(secs / len(gold), 2), rows, errs)
        print("\n== %s: верных %d/%d, средняя %.2f с%s"
              % (sc, hits, len(gold), secs / len(gold),
                 ", СБОЕВ %d" % errs if errs else ""))
        for q, ok, focus, sec in rows:
            print("   %s %-46s %-38s %.1fс" % ("+" if ok else "-", q[:46], (focus or "—")[:38], sec))

    print("\n" + "=" * 62)
    best = max(table.items(), key=lambda kv: (kv[1][0], -kv[1][1]))
    for sc, (hits, avg, _r, errs) in table.items():
        print("  %-9s верных %d/%d  средняя %.2f с%s%s"
              % (sc, hits, len(gold), avg, "  сбоев %d" % errs if errs else "",
                 "   <= лучший" if sc == best[0] else ""))

    # 🔴 ОТМЕТКА СТАВИТСЯ ТОЛЬКО ЗА СОСТОЯВШИЙСЯ ЗАМЕР (`№4`, `F172`). Прежде она
    # писалась безусловно, в самом конце, — и хук «замер до выката» закрывался прогоном,
    # где сервис не отвечал вовсе, а верных было 0 из 8. Гейт, засчитывающий провальный
    # прогон, замером не является (п. 11 контракта).
    #
    # «Состоялся» — это ни одного сбоя обращения и хоть один верный ответ. Порог качества
    # тут намеренно не ставится: решать «выкатывать ли при 6/8» — не дело отметки, это
    # видно в её тексте и в выводе выше.
    hits, _avg, _rows, errs = best[1]
    if errs or not hits:
        sys.stderr.write(
            "\n🔴 отметка .golden-last-run НЕ поставлена: сбоев %d, верных %d из %d.\n"
            "   Это не замер, а неудавшийся прогон — хук перед выкатом обязан спросить.\n"
            % (errs, hits, len(gold)))
        return None
    # 🔴 ОТМЕТКУ ЧИТАЕТ КОММИТ-ХУК, А ОН ЖИВЁТ В РЕПОЗИТОРИИ. Прежде путь считался как
    # «три каталога вверх от скрипта»: из репозитория это давало корень, а из рабочего
    # каталога `/opt/1c-mcp-reports` — **корень файловой системы**, то есть
    # `/.claude/.golden-last-run`. А запускать велено именно из рабочего каталога
    # (`REGRESSION_BASE1 §0`), значит в документированном способе отметка не ставилась
    # НИКОГДА и гейт перед выкатом её не видел. Тот же класс, что «хуки не вызывались
    # вовсе» (`HOW_NOT_TO §1.42`): защита, которая молча не срабатывает.
    root = os.environ.get("AB_MARK_DIR") or os.environ.get("CLAUDE_PROJECT_DIR") or ""
    if not root:
        try:
            root = subprocess.run(
                ["git", "-C", os.path.dirname(os.path.abspath(__file__)),
                 "rev-parse", "--show-toplevel"],
                capture_output=True, text=True, check=True).stdout.strip()
        except Exception:                        # noqa: BLE001 — вне репозитория
            root = ""
    mark_dir = os.path.join(root, ".claude") if root else ""
    if not mark_dir or not os.path.isdir(mark_dir):
        # Молча не пишем — говорим. Иначе прогон выглядит удавшимся, а гейт остаётся слеп.
        sys.stderr.write(
            "\n🔴 отметка НЕ поставлена: не найден репозиторий (запуск из %s).\n"
            "   Замер СОСТОЯЛСЯ (%s, верных %d из %d) — не поставлена только отметка для\n"
            "   коммит-хука. Укажите каталог: AB_MARK_DIR=/путь/к/репозиторию\n"
            % (os.path.dirname(os.path.abspath(__file__)), best[0], hits, len(gold)))
        return best[0]
    try:
        open(os.path.join(mark_dir, ".golden-last-run"), "w").write(
            "%s %s %d/%d\n" % (BASE, best[0], hits, len(gold)))
    except Exception as e:                       # noqa: BLE001
        sys.stderr.write("отметку записать не удалось: %s\n" % e)
        return None
    return best[0]


if __name__ == "__main__":
    # 🔴 Код возврата ведём от РЕЗУЛЬТАТА (`№4`). Прежде здесь стояло `0 if main() else 0`
    # — то есть успех при любом исходе, включая молчащий сервис. Всё, что смотрит на код
    # возврата (руки, юниты, хуки), считало неудавшийся прогон удавшимся.
    sys.exit(0 if main() else 1)
