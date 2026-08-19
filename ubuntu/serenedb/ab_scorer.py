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


MODES = ("sql", "kind", "fork", "pivot")


def parse_opts(text):
    """Третье поле строки набора: CLS=<класс> PICK=<клик>|<клик>… (порядок кликов важен)."""
    chunk = text or ""
    picks = []
    head = chunk
    if "PICK=" in chunk:
        head, tail = chunk.split("PICK=", 1)
        picks = [p.strip() for p in tail.split("|") if p.strip()]
    cls = head.split("CLS=", 1)[1].strip() if "CLS=" in head else ""
    return cls, picks


def load_gold(path):
    """Строки набора: sql-эталон или MODE=… плюс опции (класс и клики по развилке)."""
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
            cols = line.split("\t")
            q, spec = cols[0].strip(), cols[1].strip()
            cls, picks = parse_opts(cols[2] if len(cols) > 2 else "")
            row = {"q": q, "cls": cls, "picks": picks}
            if spec.startswith("MODE="):
                row["mode"] = spec.split("=", 1)[1].strip()
                if row["mode"] not in MODES or row["mode"] == "sql":
                    sys.stderr.write("неизвестный режим строки: %s\n" % spec[:40])
                    sys.exit(1)
            else:
                row["mode"], row["sql"] = "sql", spec
            out.append(row)
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


def ask(q, decision_id=None):
    """Заход в сервис. `decision_id` — билет выбранного варианта: то же, что клик
    человека по кнопке уточнения (мост шлёт тот же вопрос и билет)."""
    payload = {"question": q}
    if decision_id:
        payload["decision_id"] = decision_id
    body = json.dumps(payload).encode()
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


def norm_name(s):
    """Имя поля и его человеческая подпись — одно и то же с точностью до пробелов."""
    return "".join(str(s or "").lower().split())


def option_matches(opt, pick):
    """Совпадает ли вариант уточнения с кликом набора.

    Клик задаётся тем, что база знает о себе сама: `src:` — имя сущности, `axis:` —
    колонка разреза (`distinct_by`), `measure:` — имя величины (подпись сервиса —
    та же строка с пробелами), `label:` — кусок подписи.
    """
    if ":" not in pick:
        return False
    what, val = pick.split(":", 1)
    what, val = what.strip(), val.strip()
    if what == "src":
        return (opt.get("src") or "") == val
    if what == "axis":
        return (opt.get("distinct_by") or "") == val
    if what == "measure":
        return norm_name(opt.get("label")) == norm_name(val)
    if what == "label":
        return norm_name(val) in norm_name(opt.get("label"))
    return False


def clickable(d):
    """Ответ, где человеку предложен выбор: уточнение или пары исхода B."""
    return (d.get("kind") in ("clarify", "figures")) and bool(d.get("options"))


def pick_option(d, picks):
    """Первый непотраченный клик, для которого есть вариант. (билет, метка, остаток)."""
    opts = [o for o in (d.get("options") or []) if isinstance(o, dict)]
    for i, pick in enumerate(picks):
        for o in opts:
            if option_matches(o, pick) and (o.get("decision_id") or ""):
                return o["decision_id"], pick, picks[i + 1:]
    return None, "", picks


def leaks_internal_name(d):
    """Утечка внутреннего имени сущности в подписи варианта (человеку это не имя)."""
    marks = ("catalog_", "document_", "accumulationregister_", "informationregister_",
             "accountingregister_", "calculationregister_", "documentjournal_",
             "chartofaccounts_", "chartofcharacteristictypes_", "exchangeplan_",
             "constant_", "src_table")
    blobs = [str(o.get("label") or "") for o in (d.get("options") or [])
             if isinstance(o, dict)] + [str(d.get("text") or "")]
    return any(m in b.lower() for b in blobs for m in marks)


def fork_row_ok(d):
    """Класс «вилка»: спрошено, а не угадано, и обе подписи человеческие."""
    if d.get("kind") != "clarify":
        return False, "не уточнение (%s)" % (d.get("kind") or "—")
    opts = [o for o in (d.get("options") or []) if isinstance(o, dict)]
    if len(opts) < 2:
        return False, "вариантов меньше двух"
    if any(not str(o.get("label") or "").strip() for o in opts):
        return False, "вариант без подписи"
    if leaks_internal_name(d):
        return False, "в подписи внутреннее имя сущности"
    return True, ""


def zero_claimed(d):
    """Ответ подан как ноль: ноль в разобранном значении или голый 0 в тексте."""
    atoms = [a for a in ([d.get("atom")] + list(d.get("atoms") or [])) if isinstance(a, dict)]
    for a in atoms:
        v = a.get("exact_value")
        if isinstance(v, (int, float)) and float(v) == 0.0:
            return True
    claims = ((d.get("diag") or {}).get("claims") or {})
    for v in claims.values():
        try:
            if v is not None and float(v) == 0.0:
                return True
        except (TypeError, ValueError):
            continue
    return bool(re.search(r"(?<![\d,.])0(?:[.,]0+)?(?![\d,.])", d.get("text") or ""))


def pivot_row_ok(d):
    """Класс «величина-пустышка»: пустую величину не выдают за ответ «0».

    Годится и честный пивот на живую величину, и уточнение с перечнем величин;
    негодно — «0» как ответ и отказ при данных в сущности (п. 21)."""
    if d.get("kind") == "no_data":
        return False, "отказ при данных в сущности"
    if zero_claimed(d):
        return False, "пустая величина подана как «0»"
    return True, ""


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


MAX_CLICKS = int(os.environ.get("AB_MAX_CLICKS", "3"))


def number_ok(d, want):
    """Число эталона встретилось в ответе: в тексте или в разобранных значениях."""
    claims = ((d.get("diag") or {}).get("claims") or {})
    got = digits(d.get("text") or "") | {re.sub(r"\D", "", str(v))
                                         for v in claims.values() if v is not None}
    return re.sub(r"\D", "", want) in got


def check_row(row, d):
    """Годен ли ответ по классу строки набора. Возвращает (годен, причина)."""
    mode = row["mode"]
    if mode == "kind":
        if (d.get("kind") or "") != "no_data":
            return False, "не no_data (%s)" % (d.get("kind") or "—")
        if aggregate_totals_in_text(d.get("text") or ""):
            return False, "в отказе есть число итога"
        return True, ""
    if mode == "fork":
        return fork_row_ok(d)
    if mode == "pivot":
        return pivot_row_ok(d)
    if number_ok(d, row["want"]):
        return True, ""
    return False, "нет числа эталона (%s)" % (d.get("kind") or "—")


def run_row(row):
    """Заход и, если сервис спросил, клики по развилке — как это делает человек."""
    picks = list(row.get("picks") or [])
    secs, clicks, did = 0.0, 0, None
    d, sec = ask(row["q"])
    secs += sec
    err = ((d.get("diag") or {}).get("error") or "")
    ok, why = check_row(row, d)
    while not ok and not err and clickable(d) and clicks < MAX_CLICKS:
        did, pick, rest = pick_option(d, picks)
        if not did:
            why = why or "нет варианта под клик"
            break
        picks = rest
        clicks += 1
        d, sec = ask(row["q"], decision_id=did)
        secs += sec
        err = ((d.get("diag") or {}).get("error") or "")
        ok, why = check_row(row, d)
        if (d.get("kind") or "") == "choice_error":
            why = "билет не принят (choice_error)"
            break
    return {"ok": ok, "why": "" if ok else (why or "—"), "clicks": clicks,
            "sec": round(secs, 2), "err": bool(err),
            "kind": d.get("kind"), "focus": (d.get("diag") or {}).get("focus"),
            "rid": (d.get("diag") or {}).get("rid") or ""}


def main():
    label = CONTOUR or GOLD_MODE or BASE
    print("контур %s, база %s, сервис %s, %s" % (label, BASE, URL, UNIT))
    if LIVE_CONTOUR:
        print("live: без рестарта юнита")
    gold = []
    for row in GOLD:
        r = dict(row)
        r["want"] = truth(row["sql"]) if row["mode"] == "sql" else None
        gold.append(r)
    print("эталоны: " + ", ".join(
        (r["want"] or "?") if r["mode"] == "sql" else "%s:%s" % (r["q"][:20], r["mode"])
        for r in gold))
    blind = [r["q"] for r in gold if r["mode"] == "sql" and not r["want"]]
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
        for r in gold:
            res = run_row(r)
            errs += 1 if res["err"] else 0
            hits += 1 if res["ok"] else 0
            secs += res["sec"]
            rows.append((r, res))
        table[sc] = (hits, round(secs / len(gold), 2), rows, errs)
        print("\n== %s: верных %d/%d, средняя %.2f с%s"
              % (sc, hits, len(gold), secs / len(gold),
                 ", СБОЕВ %d" % errs if errs else ""))
        for r, res in rows:
            print("   %s %-52s %-26s кликов %d  %s%s  %.1fс"
                  % ("+" if res["ok"] else "-", r["q"][:52], (r["cls"] or "—")[:26],
                     res["clicks"], (res["kind"] or "—"),
                     "" if res["ok"] else "  ← %s" % res["why"][:60], res["sec"]))
            if not res["ok"] and res["rid"]:
                print("       rid %s" % res["rid"])

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
