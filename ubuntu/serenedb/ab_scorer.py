#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A/B модели ранжирования на золотом наборе вопросов.

Правило владельца: если у движка есть штатный механизм — берём его, потому что у них он
проверен на больших данных, а наша конструкция поверх — гипотеза. Спорить об этом нельзя,
можно только замерить: один и тот же набор вопросов прогоняется на каждой модели
ранжирования, ответы сверяются с независимым эталоном.

Запуск на сервере: python3 ab_scorer.py

Контуры (решение владельца 18.08):
  AB_GOLD_MODE=smoke AB_BASE=ut_test — до выката: 0 сбоев обращения, порог верных не нужен
  AB_CONTOUR=okna — после выката на okna: ab-gold-okna.tsv, числа + kind=no_data для склада
  AB_BASE=ut_test — прежний набор ab-gold.tsv (A/B или live по ASK_URL)
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONTOUR = os.environ.get("AB_CONTOUR", "").strip().lower()
GOLD_MODE = os.environ.get("AB_GOLD_MODE", "").strip().lower()
BASE = os.environ.get("AB_BASE", "ut_test" if GOLD_MODE == "smoke" else "postgres")
ENV_FILE = "/etc/1c-serene-ask-%s.env" % BASE
UNIT = "1c-serene-ask@%s.service" % BASE
ENV_COMMON = "/etc/1c-serene-ask.env"
ENV_PG = "/etc/1c-serene-ask-postgres.env"
ENV_MCP = "/etc/1c-mcp-reports.env"


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


def ensure_pgpassword():
    if os.environ.get("PGPASSWORD"):
        return
    pw = env_value("PGPASSWORD", ENV_MCP)
    if pw:
        os.environ["PGPASSWORD"] = pw


if CONTOUR == "okna":
    GOLD_FILE = os.environ.get(
        "AB_GOLD_FILE", os.path.join(_SCRIPT_DIR, "ab-gold-okna.tsv"))
    ensure_pgpassword()
    DSN = os.environ.get("AB_DSN") or env_value(
        "SERENEDB_DSN_RO", ENV_PG) or env_value("SERENEDB_DSN", ENV_PG)
    _ask = os.environ.get("ASK_URL", "").strip().rstrip("/") or "http://127.0.0.1:8091"
    URL = _ask if _ask.endswith("/ask") else _ask + "/ask"
    TOK = os.environ.get("ASK_TOKEN") or env_value("ASK_TOKEN", ENV_COMMON)
    LIVE_CONTOUR = True
    UNIT = "1c-serene-ask@okna.service"
    SCORERS = ["live"]
else:
    GOLD_FILE = os.environ.get(
        "AB_GOLD_FILE", os.path.join(_SCRIPT_DIR, "ab-gold.tsv"))
    ensure_pgpassword()
    DSN = os.environ.get(
        "AB_DSN", "host=127.0.0.1 port=7890 user=serene_ro dbname=%s" % BASE)
    _ask = os.environ.get("ASK_URL", "").strip().rstrip("/")
    LIVE_CONTOUR = bool(_ask) or GOLD_MODE == "smoke"
    if _ask:
        URL = _ask if _ask.endswith("/ask") else _ask + "/ask"
    else:
        URL = "http://127.0.0.1:%s/ask" % (
            env_value("ASK_LISTEN_PORT", ENV_COMMON, ENV_FILE) or "8091")
    SCORERS = [s for s in os.environ.get(
        "AB_SCORERS", "bm25,bm25_b0,tfidf,lm_jm,lm_dirichlet,dfi").split(",") if s]
    if GOLD_MODE == "smoke":
        LIVE_CONTOUR = True
        SCORERS = ["live"]
    if not os.environ.get("ASK_TOKEN"):
        TOK = env_value("ASK_TOKEN", ENV_COMMON, ENV_FILE)
    else:
        TOK = os.environ.get("ASK_TOKEN")


def load_gold(path):
    """Строки набора: sql-эталон или MODE=kind (без числового SQL)."""
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
            q, spec = line.split("\t", 1)
            spec = spec.strip()
            if spec == "MODE=kind":
                out.append({"q": q.strip(), "mode": "kind"})
            else:
                out.append({"q": q.strip(), "mode": "sql", "sql": spec})
    if not out:
        sys.stderr.write("набор вопросов пуст: %s\n" % path)
        sys.exit(1)
    return out


GOLD = load_gold(GOLD_FILE)


def truth(sql):
    p = subprocess.run(["psql", DSN, "-tA", "-c", sql], capture_output=True, text=True)
    if p.returncode:
        sys.stderr.write("psql: %s\n" % ((p.stderr or p.stdout or "").strip()[:200]))
    return (p.stdout or "").strip()


def ask(q):
    body = json.dumps({"question": q}).encode()
    req = urllib.request.Request(URL, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    if TOK:
        req.add_header("Authorization", "Bearer " + TOK)
    t = time.time()
    timeout = int(os.environ.get("AB_ASK_TIMEOUT", "600"))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read()), round(time.time() - t, 2)
    except Exception as e:                       # noqa: BLE001
        return {"text": "", "diag": {"error": str(e)[:80]}}, round(time.time() - t, 2)


def digits(text):
    """Цифровые последовательности ответа — сравниваем по ним, без учёта разрядки."""
    return {re.sub(r"\D", "", m) for m in re.findall(
        "[\\d\u0020\u00a0\u2007\u2009\u202f\u200b'.,]{1,}", text or "")
            if re.sub(r"\D", "", m)}


def aggregate_totals_in_text(text):
    """Числа итогов в text при kind=no_data — брак; годы и мелочь (минуты) — можно."""
    for tok in re.findall(r"[\d\u0020\u00a0\u2007\u2009\u202f\u200b'.,]+", text or ""):
        bare = re.sub(r"\D", "", tok)
        if not bare:
            continue
        if re.search(r"\d[\s\u00a0\u202f\u2009]\d{3}", tok):
            return True
        if re.search(r"[.,]\d", tok):
            return True
        try:
            n = int(bare)
        except ValueError:
            continue
        if 1900 <= n <= 2099:
            continue
        if n >= 1000:
            return True
    return False


def kind_row_ok(d):
    if (d.get("kind") or "") != "no_data":
        return False
    return not aggregate_totals_in_text(d.get("text") or "")


def restart(scorer):
    lines = [l for l in open(ENV_FILE, encoding="utf-8") if not l.startswith("ASK_SCORER=")]
    lines.append("ASK_SCORER=%s\n" % scorer)
    open(ENV_FILE, "w", encoding="utf-8").writelines(lines)
    subprocess.run(["systemctl", "restart", UNIT], check=True)
    time.sleep(4)


def mark_path(name):
    root = os.environ.get("AB_MARK_DIR") or os.environ.get("CLAUDE_PROJECT_DIR") or ""
    if not root:
        try:
            root = subprocess.run(
                ["git", "-C", _SCRIPT_DIR, "rev-parse", "--show-toplevel"],
                capture_output=True, text=True, check=True).stdout.strip()
        except Exception:                        # noqa: BLE001
            root = ""
    mark_dir = os.path.join(root, ".claude") if root else ""
    if not mark_dir or not os.path.isdir(mark_dir):
        return ""
    return os.path.join(mark_dir, name)


def write_mark(best_sc, hits, n, errs):
    if CONTOUR == "okna":
        if errs or hits < n:
            sys.stderr.write(
                "\n🔴 отметка .golden-okna-last-run НЕ поставлена: сбоев %d, верных %d из %d.\n"
                % (errs, hits, n))
            return None
        path = mark_path(".golden-okna-last-run")
        line = "okna %s %d/%d\n" % (best_sc, hits, n)
    elif GOLD_MODE == "smoke":
        if errs:
            sys.stderr.write(
                "\n🔴 отметка smoke НЕ поставлена: сбоев %d из %d вопросов.\n" % (errs, n))
            return None
        path = mark_path(".golden-last-run")
        line = "smoke %s %s 0err/%d\n" % (BASE, best_sc, n)
    else:
        if errs or not hits:
            sys.stderr.write(
                "\n🔴 отметка .golden-last-run НЕ поставлена: сбоев %d, верных %d из %d.\n"
                % (errs, hits, n))
            return None
        path = mark_path(".golden-last-run")
        line = "%s %s %d/%d\n" % (BASE, best_sc, hits, n)
    if not path:
        sys.stderr.write(
            "\n🔴 отметка НЕ поставлена: не найден каталог .claude репозитория.\n"
            "   AB_MARK_DIR=/путь/к/репозиторию\n")
        return None
    try:
        open(path, "w").write(line)
        print("отметка: %s" % line.strip())
    except Exception as e:                       # noqa: BLE001
        sys.stderr.write("отметку записать не удалось: %s\n" % e)
        return None
    return best_sc


def main():
    label = CONTOUR or GOLD_MODE or BASE
    print("контур %s, база %s, сервис %s, %s" % (label, BASE, URL, UNIT))
    if LIVE_CONTOUR:
        print("live: без рестарта юнита")
    gold = []
    for row in GOLD:
        if row["mode"] == "kind":
            gold.append((row["q"], None, "kind"))
        else:
            gold.append((row["q"], truth(row["sql"]), "sql"))
    shown = []
    for q, t, mode in gold:
        if mode == "kind":
            shown.append("%s:kind" % q[:24])
        else:
            shown.append(t or "?")
    print("эталоны: " + ", ".join(shown))
    blind = [q for q, t, mode in gold if mode == "sql" and not t]
    if blind:
        sys.stderr.write("эталон не посчитан у %d вопросов: %s\n"
                         % (len(blind), "; ".join(q[:40] for q in blind[:3])))
        return None
    table = {}
    scorers = ["live"] if LIVE_CONTOUR else SCORERS
    for sc in scorers:
        if not LIVE_CONTOUR:
            restart(sc)
        hits, secs, rows, errs = 0, 0.0, [], 0
        for q, want, mode in gold:
            d, sec = ask(q)
            text = d.get("text") or ""
            diag = d.get("diag") or {}
            if diag.get("error"):
                errs += 1
            if mode == "kind":
                ok = kind_row_ok(d)
            else:
                claims = diag.get("claims") or {}
                got = digits(text) | {re.sub(r"\D", "", str(v)) for v in claims.values()
                                      if v is not None}
                ok = re.sub(r"\D", "", want) in got
            hits += 1 if ok else 0
            secs += sec
            rows.append((q, ok, diag.get("focus") or d.get("kind"), sec))
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

    hits, _avg, _rows, errs = best[1]
    return write_mark(best[0], hits, len(gold), errs)


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
