#!/usr/bin/env python3
"""ПРОГОН НАБОРА САМОПРОВЕРКИ ЧЕРЕЗ ЖИВОЙ /ask (план §4: прогон через боевой сервис).

Читает список `runs/selftest-<база>.jsonl` (его строит `selftest_generate.py`),
задаёт каждый вопрос работающему сервису `1c-serene-ask@<база>` и дописывает
результат в `runs/selftest-<база>-results.jsonl`.

🔴 ДИСЦИПЛИНА НАГРУЗКИ (указание к задаче): строго ПОСЛЕДОВАТЕЛЬНО, пауза между
вопросами (`SELFTEST_PAUSE_SEC`, молча 1 с), ОДИН вызов /ask на вопрос — без
ретраев «добиться» и без параллельных вееров (девовский эмбеддер слабый, модель
ответов платная). Состояние сервиса не меняется: только POST /ask.

Возобновляем: идентификаторы, уже лежащие в файле результатов, пропускаются —
прерванный прогон продолжается с места обрыва.

На каждый вопрос фиксируется: kind, diag.focus, варианты уточнения (options),
числа ответа (figures/totals), diag.fork (может отсутствовать — другой трек),
diag.measure, grain и клиентское время ответа.

Использование:
    ASK_BASE=ut_test python3 work/acceptance/selftest_run.py [сколько]
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BASE = os.environ.get("ASK_BASE") or (sys.argv[1] if len(sys.argv) > 1 else "ut_test")
LIMIT = int(sys.argv[2]) if len(sys.argv) > 2 else 0
RUNS = os.path.join(ROOT, "work", "acceptance", "runs")
# SELFTEST_LIST / SELFTEST_OUT — ярус 2 (стратифицированные 10 %) пишет в
# отдельные файлы, полный набор не затирается; без переменных — прежние пути.
LIST = os.environ.get("SELFTEST_LIST") or os.path.join(RUNS, "selftest-%s.jsonl" % BASE)
OUT = os.environ.get("SELFTEST_OUT") or os.path.join(RUNS, "selftest-%s-results.jsonl" % BASE)
PAUSE = float(os.environ.get("SELFTEST_PAUSE_SEC", "1"))
# Живой ответ идёт 15-60 с (замер 15.08: clarify 38 с, answer 15 с), запас на
# арбитра. Это бюджет ожидания прибора, а не порог правильности.
TIMEOUT = int(os.environ.get("SELFTEST_TIMEOUT", "180"))


def load_env(path):
    try:
        fh = open(path, encoding="utf-8")
    except OSError:
        return
    with fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            v = v.strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                v = v[1:-1]
            os.environ.setdefault(k.strip(), v)


load_env("/etc/1c-serene-ask-%s.env" % BASE)
load_env("/etc/1c-serene-ask.env")
load_env("/etc/1c-mcp-reports.env")

PORT = os.environ.get("ASK_LISTEN_PORT", "")
ASK_URL = os.environ.get("ASK_URL") or ("http://127.0.0.1:%s/ask" % PORT)
TOKEN = os.environ.get("ASK_TOKEN", "")

# Поля figures, которые сверяет проверка, — остальное в сверке не участвует.
FIG_KEYS = ("count", "sum", "count_amount", "folders")
DIAG_KEYS = ("focus", "fork", "measure", "grain", "found")


def ask(question):
    body = json.dumps({"question": question}).encode()
    req = urllib.request.Request(ASK_URL, data=body,
                                 headers={"Content-Type": "application/json",
                                          "Authorization": "Bearer " + TOKEN})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.status, json.loads(r.read().decode())


def trim(resp):
    diag = resp.get("diag") or {}
    figs = resp.get("figures") or {}
    totals = resp.get("totals") or {}
    return {
        "kind": resp.get("kind"),
        "text": (resp.get("text") or "")[:400],
        "focus": diag.get("focus"),
        "options": [o.get("src") for o in (resp.get("options") or []) if o.get("src")],
        "figures": {k: figs.get(k) for k in FIG_KEYS if figs.get(k) is not None},
        "totals": {m: (t or {}).get("sum") for m, t in totals.items()
                   if isinstance(t, dict) and t.get("sum") is not None},
        "diag": {k: diag.get(k) for k in DIAG_KEYS if diag.get(k) is not None},
    }


def done_ids():
    out = set()
    try:
        fh = open(OUT, encoding="utf-8")
    except OSError:
        return out
    with fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.add(json.loads(line)["id"])
            except (ValueError, KeyError):
                continue  # оборванный хвост файла — перезапишется новой записью
    return out


def main():
    if not TOKEN:
        sys.stderr.write("FATAL: ASK_TOKEN пуст — живая проверка без авторизации "
                         "невозможна (источник: /etc/1c-serene-ask.env).\n")
        return 2
    questions = [json.loads(line) for line in open(LIST, encoding="utf-8") if line.strip()]
    done = done_ids()
    todo = [q for q in questions if q["id"] not in done]
    if LIMIT:
        todo = todo[:LIMIT]
    sys.stderr.write("%s: всего %d, сделано %d, к прогону %d, сервис %s\n"
                     % (BASE, len(questions), len(done), len(todo), ASK_URL))
    t_start = time.time()
    with open(OUT, "a", encoding="utf-8") as fh:
        for i, q in enumerate(todo, 1):
            t0 = time.time()
            rec = {"id": q["id"], "question": q["question"]}
            try:
                status, resp = ask(q["question"])
                rec.update(trim(resp))
                rec["http"] = status
            except urllib.error.HTTPError as e:
                rec["http"] = e.code
                rec["error"] = (e.read() or b"").decode("utf-8", "replace")[:200]
            except Exception as e:  # noqa: BLE001 — сбой фиксируется классом, прогон идёт дальше
                rec["http"] = 0
                rec["error"] = str(e)[:200]
            rec["sec"] = round(time.time() - t0, 2)
            fh.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")
            fh.flush()
            if i % 25 == 0 or i == len(todo):
                done_sec = time.time() - t_start
                eta = done_sec / i * (len(todo) - i)
                sys.stderr.write("  %d/%d, %.0f с прогона, осталось ~%.0f с\n"
                                 % (i, len(todo), done_sec, eta))
            time.sleep(PAUSE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
