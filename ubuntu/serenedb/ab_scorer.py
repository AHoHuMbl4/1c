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
  AB_CONTOUR=okna — после выката на okna: ab-gold-okna.tsv (v2: digits/kind/clarify/name)
  AB_PROBE=okna — до коммита serene_ask.py: ab-probe-okna.tsv (~8), отметка .probe-okna-last-run
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
_ACCEPTANCE = os.path.normpath(os.path.join(_SCRIPT_DIR, "..", "..", "work", "acceptance"))
if os.path.isdir(_ACCEPTANCE) and _ACCEPTANCE not in sys.path:
    sys.path.insert(0, _ACCEPTANCE)
try:
    import probe_protocol as _probe_protocol
except ImportError:
    _probe_protocol = None
CONTOUR = os.environ.get("AB_CONTOUR", "").strip().lower()
PROBE = os.environ.get("AB_PROBE", "").strip().lower()
GOLD_MODE = os.environ.get("AB_GOLD_MODE", "").strip().lower()
BASE = os.environ.get("AB_BASE", "ut_test" if GOLD_MODE == "smoke" else "postgres")
ENV_FILE = "/etc/1c-serene-ask-%s.env" % BASE
UNIT = "1c-serene-ask@%s.service" % BASE
ENV_COMMON = "/etc/1c-serene-ask.env"
ENV_PG = "/etc/1c-serene-ask-postgres.env"
ENV_MCP = "/etc/1c-mcp-reports.env"
ASK_USER = os.environ.get("AB_ASK_USER", "gold-v2")


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


if PROBE == "okna" or CONTOUR == "okna":
    _probe_gold = os.path.join(_SCRIPT_DIR, "ab-probe-okna.tsv")
    _okna_gold = os.path.join(_SCRIPT_DIR, "ab-gold-okna.tsv")
    GOLD_FILE = os.environ.get(
        "AB_GOLD_FILE",
        _probe_gold if PROBE == "okna" else _okna_gold)
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
    """Строки набора:
    - v2: вопрос<TAB>SQL<TAB>режим (digits/kind/clarify/name)
    - legacy: вопрос<TAB>SQL (digits) или вопрос<TAB>MODE=kind
    """
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
            parts = line.split("\t")
            if len(parts) == 2:
                q, spec = parts
                spec = spec.strip()
                if spec == "MODE=kind":
                    out.append({"q": q.strip(), "mode": "kind", "sql": None})
                else:
                    out.append({"q": q.strip(), "mode": "digits", "sql": spec})
            elif len(parts) == 3:
                q, sql, mode = parts
                out.append({
                    "q": q.strip(),
                    "sql": sql.strip(),
                    "mode": (mode or "").strip().lower(),
                })
            else:
                sys.stderr.write("слишком много колонок пропущено: %s\n" % line[:120])
                continue
    if not out:
        sys.stderr.write("набор вопросов пуст: %s\n" % path)
        sys.exit(1)
    return out


def truth(sql, empty_as_zero=False):
    """Эталон из SQL. Пустой SUM (нет строк) — валидный 0 при empty_as_zero (digits/kind)."""
    p = subprocess.run(["psql", DSN, "-tA", "-c", sql], capture_output=True, text=True)
    if p.returncode:
        sys.stderr.write("psql: %s\n" % ((p.stderr or p.stdout or "").strip()[:200]))
    out = (p.stdout or "").strip()
    if not out and empty_as_zero:
        return "0"
    return out


def _probe_port_from_url():
    m = re.search(r":(\d+)(?:/ask)?$", (URL or "").rstrip("/"))
    return m.group(1) if m else "?"


def _probe_emit_ask(question, out, rid=None):
    if _probe_protocol is None:
        return
    record = os.environ.get("PROBE_RECORD", "").strip()
    try:
        _probe_protocol.emit(
            rid=rid or _probe_protocol.new_rid("ab"),
            port=_probe_port_from_url(),
            code_md5_val=_probe_protocol.code_md5(
                os.environ.get("PROBE_CODE_PATH", "/opt/1c-mcp-reports/serene_ask.py"),
                short=True,
            ),
            question=question,
            outcome=(out or {}).get("kind") or "—",
            record_path=record or None,
        )
    except Exception:                            # noqa: BLE001
        pass


def ask(q, decision_id=None, user=None, rid=None):
    body = {"question": q, "user": user or ASK_USER}
    if decision_id:
        body["decision_id"] = decision_id
    if rid:
        body["rid"] = rid
    body = json.dumps(body).encode()
    req = urllib.request.Request(URL, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    if TOK:
        req.add_header("Authorization", "Bearer " + TOK)
    t = time.time()
    timeout = int(os.environ.get("AB_ASK_TIMEOUT", "600"))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            out = json.loads(r.read())
            _probe_emit_ask(q, out, rid=rid)
            return out, round(time.time() - t, 2)
    except Exception as e:                       # noqa: BLE001
        out = {"text": "", "diag": {"error": str(e)[:80]}}
        _probe_emit_ask(q, out, rid=rid)
        return out, round(time.time() - t, 2)


def digits(text):
    """Цифровые последовательности ответа — сравниваем по ним, без учёта разрядки."""
    return {re.sub(r"\D", "", m) for m in re.findall(
        "[\\d\u0020\u00a0\u2007\u2009\u202f\u200b'.,]{1,}", text or "")
            if re.sub(r"\D", "", m)}


def extract_number_digits_candidates(d):
    """Из ответа: собираем все числа, которые могут быть в text/claims/figures/totals."""
    got = set()
    if not isinstance(d, dict):
        return got
    got |= digits(d.get("text") or "")
    diag = d.get("diag") or {}
    if isinstance(diag, dict):
        claims = diag.get("claims") or {}
        if isinstance(claims, dict):
            for v in claims.values():
                if v is not None:
                    got |= digits(str(v))
    figures = d.get("figures") or {}
    if isinstance(figures, dict):
        for v in figures.values():
            if v is not None:
                got |= digits(str(v))
    totals = d.get("totals") or {}
    if isinstance(totals, dict):
        for v in totals.values():
            if v is not None:
                got |= digits(str(v))
    return got


def want_number_digits(want):
    """Нормализуем эталонную строку в 'ключ' для digits()."""
    if want is None:
        return ""
    return re.sub(r"\D", "", str(want))


def number_digit_keys(want):
    """Эквиваленты числа для digits: 1668.00 ≡ 1668.0 ≡ 1668 ([замер 21.08] name)."""
    keys = set()
    raw = want_number_digits(want)
    if raw:
        keys.add(raw)
    f = parse_float_or_none(want)
    if f is None:
        return keys
    if abs(f - round(f)) < 1e-9:
        keys.add(str(int(round(f))))
    s = ("%f" % f).rstrip("0").rstrip(".")
    k = want_number_digits(s)
    if k:
        keys.add(k)
    keys.add(want_number_digits("%.2f" % f))
    return {k for k in keys if k}


def parse_float_or_none(s):
    s = str(s).strip() if s is not None else ""
    if not s:
        return None
    s = s.replace("\u00a0", " ").replace(" ", "")
    s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def option_text(o):
    """Какой текст вариантов используем для поиска подстроки."""
    if not isinstance(o, dict):
        return ""
    parts = []
    for k in ("label", "text", "focus", "src", "measure", "grain", "distinct_by"):
        v = o.get(k)
        if v:
            parts.append(str(v))
    return " ".join(parts).strip()


def choose_clarify_option(options, needle):
    """Выбираем вариант clarify по подстроке (case-insensitive)."""
    needle = str(needle or "").strip().lower()
    if not needle or not isinstance(options, list):
        return None
    for o in options:
        if not isinstance(o, dict):
            continue
        hay = option_text(o).lower()
        if needle in hay:
            return o
    return None


def ask_with_clarify_follow(question, branch_needle=None, max_steps=6, user=None, rid=None):
    """Если сервис ответил clarify и варианты можно однозначно выбрать — идём дальше.

    Важно: для digits/kind ветвление отключается (branch_needle=None), иначе появится
    "ремонт" провалов.
    """
    user = user or ASK_USER
    out0, out = None, None
    decision_id = None
    for _step in range(max_steps):
        out, _sec = ask(question, decision_id=decision_id, user=user, rid=rid)
        if out0 is None:
            out0 = out
        if (out or {}).get("kind") != "clarify":
            break
        if not branch_needle:
            break
        opts = out.get("options") or []
        chosen = choose_clarify_option(opts, branch_needle)
        if not chosen:
            break
        decision_id = chosen.get("decision_id")
        if not decision_id:
            break
    return out0, out


def kind_expected_for_kind_mode(sql, want, question=""):
    """Выводим ожидаемый d.kind для режима kind из SQL-эталона.

    В v2 у режима kind SQL часто возвращает 0, а точный d.kind определяется
    типом вопроса: период/счёт vs наличие складских остатков.
    Диагностика нуля («почему… сбой?») — answer/no_data, не figures ([замер 21.08]).
    """
    if not sql:
        return "no_data"  # legacy
    w = parse_float_or_none(want)
    is_zero = (w == 0.0)
    ql = (question or "").lower()
    if is_zero and any(x in ql for x in ("почему", "сбой", "ошибк", "баг")):
        return "diagnostic_zero"
    if is_zero:
        # по okna-live: период с нулём отдаёт figures (сравните с no_data на складе)
        if "accumulationregister_реализациятмц" in sql or "doc_date" in sql:
            return "figures"
        return "no_data"
    # при ненулевом эталоне вопрос должен закончиться обычным ответом
    return "answer"


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


def score_digits(want, out):
    want_key = want_number_digits(want)
    if not want_key:
        return False, "число не сошлось", "пустой эталон"
    got = extract_number_digits_candidates(out)
    ok = want_key in got
    if ok:
        return True, "", "ok"
    return False, "число не сошлось", "want=%s got=%s" % (want_key, ",".join(sorted(got))[:120])


def score_digits_probe(want, out):
    """Проба okna: kind answer|figures + число эталона (ловит clarify и чужое число)."""
    got_kind = (out or {}).get("kind") or ""
    if got_kind not in ("answer", "figures"):
        return False, "kind не тот", "want kind=answer|figures got kind=%s" % (got_kind or "—")
    return score_digits(want, out)


def score_kind(sql, want, out, question=""):
    expected = kind_expected_for_kind_mode(sql, want, question=question)
    got_kind = (out or {}).get("kind") or ""
    if expected == "diagnostic_zero":
        if got_kind in ("answer", "no_data"):
            if got_kind == "no_data" and not kind_row_ok(out):
                return False, "число/итоги в no_data", "text has totals"
            return True, "", "ok"
        return False, "kind не тот", "want kind=answer|no_data got kind=%s" % (got_kind or "—")
    if got_kind == "clarify" and expected != "clarify":
        return False, "лишний clarify", "want kind=%s got kind=clarify" % expected
    if got_kind != expected:
        return False, "kind не тот", "want kind=%s got kind=%s" % (expected, got_kind or "—")
    if expected == "no_data":
        if not kind_row_ok(out):
            return False, "число/итоги в no_data", "text has totals"
    return True, "", "ok"


def parse_name_pairs(want_str):
    """Разбираем SQL-эталон для name в список пар (имя, число|None).

    Форматы в реальном v2:
    - top-1: "<name>|<number>" (или другой разделитель колонок psql)
    - top-3: "name = num | name2 = num2 | ..."
    """
    s = (want_str or "").strip()
    if not s:
        return []

    pairs = []
    # top-3 style
    for m in re.finditer(r"(?P<name>[^=|]+?)\s*=\s*(?P<num>-?\d+(?:[.,]\d+)?)", s):
        nm = m.group("name").strip()
        nn = m.group("num").strip().replace(",", ".")
        if nm and nn:
            pairs.append((nm, nn))
    if pairs:
        return pairs

    # top-1 style: <name><sep><number>
    m = re.match(r"^(?P<name>.+?)\s*(?:[\t| ]+)\s*(?P<num>-?\d+(?:[.,]\d+)?)\s*$", s)
    if m:
        nm = m.group("name").strip()
        nn = m.group("num").strip().replace(",", ".")
        return [(nm, nn)]

    return [(s, None)]


def score_clarify(want, out):
    if (out or {}).get("kind") != "clarify":
        got_kind = (out or {}).get("kind") or ""
        return False, "kind не тот", "want kind=clarify got kind=%s" % got_kind
    opts = (out or {}).get("options") or []
    if not opts:
        return True, "", "clarify without options"
    needle = str(want or "").strip()
    if not needle:
        return True, "", "clarify options ok"
    for o in opts:
        if needle.lower() in (option_text(o).lower() or ""):
            return True, "", "ok"
    return False, "подстрока clarify не найдена", "needle=%s" % needle


def score_name(want, out):
    text = (out or {}).get("text") or ""
    got_kind = (out or {}).get("kind") or ""
    pairs = parse_name_pairs(want)
    if not pairs:
        return False, "имя не найдено", "empty name etalon"

    # ожидаемое имя: хотя бы по одной подстроке
    names_missing = []
    nums_missing = []
    got_digits = extract_number_digits_candidates(out)
    for nm, nn in pairs:
        if nm:
            if str(nm).strip().lower() not in str(text).lower():
                names_missing.append(nm)
        if nn is not None:
            if number_digit_keys(nn) and not (number_digit_keys(nn) & got_digits):
                nums_missing.append(nn)

    if names_missing:
        return False, "имя не найдено", "missing=%s got_kind=%s" % (",".join(names_missing)[:80], got_kind)
    if nums_missing:
        return False, "число не сошлось", "missing nums=%s got_kind=%s" % (",".join(nums_missing)[:80], got_kind)
    return True, "", "ok"


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
    if PROBE == "okna":
        if errs or hits < n:
            sys.stderr.write(
                "\n🔴 отметка .probe-okna-last-run НЕ поставлена: сбоев %d, верных %d из %d.\n"
                % (errs, hits, n))
            return None
        path = mark_path(".probe-okna-last-run")
        line = "okna probe live 0err/%d\n" % n
    elif CONTOUR == "okna":
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
    gold = load_gold(GOLD_FILE)
    label = ("probe-" + PROBE) if PROBE else (CONTOUR or GOLD_MODE or BASE)
    print("контур %s, база %s, сервис %s, %s" % (label, BASE, URL, UNIT))
    if LIVE_CONTOUR:
        print("live: без рестарта юнита")

    # предвычислим эталоны: они задают проверку и, для clarify/name, ветку.
    computed = []
    shown = []
    blind = []
    for row in gold:
        q = row["q"]
        mode = row["mode"]
        if row.get("sql"):
            # digits/kind: пустой SUM = 0 продаж (валидный эталон), не blind
            # clarify: CAST(NULL)/пустой — sentinel «любой clarify», не blind
            want = truth(row["sql"], empty_as_zero=(mode in ("digits", "kind")))
            if not want:
                if mode == "clarify":
                    want = ""
                else:
                    blind.append(q)
        else:
            want = None
        computed.append((q, row.get("sql"), row.get("mode"), want))
        shown.append("%s:%s=%s" % (mode, q[:18], (want or "")[:18]))

    if blind:
        sys.stderr.write("эталон не посчитан у %d вопросов: %s\n"
                         % (len(blind), "; ".join(q[:40] for q in blind[:3])))
        return None

    print("эталоны: " + ", ".join(shown))
    table = {}
    scorers = ["live"] if LIVE_CONTOUR else SCORERS
    for sc in scorers:
        if not LIVE_CONTOUR:
            restart(sc)
        hits, secs, errs = 0, 0.0, 0
        rows = []
        failures = []

        for q, sql, mode, want in computed:
            branch_needle = None
            if mode in ("clarify", "name"):
                branch_needle = want
                if mode == "name" and want:
                    # для ветки уточнения по имени берем первое имя
                    np = parse_name_pairs(want)
                    if np and np[0][0]:
                        branch_needle = np[0][0]

            t0 = time.time()
            out0 = outf = None
            ask_rid = (
                _probe_protocol.new_rid("ab") if _probe_protocol and (PROBE or LIVE_CONTOUR)
                else None)
            if mode in ("digits", "kind"):
                out0, outf = ask_with_clarify_follow(
                    q, branch_needle=None, user=ASK_USER, rid=ask_rid)
            elif mode == "clarify":
                out0, outf = ask_with_clarify_follow(
                    q, branch_needle=want, user=ASK_USER, rid=ask_rid)
            elif mode == "name":
                out0, outf = ask_with_clarify_follow(
                    q, branch_needle=branch_needle, user=ASK_USER, rid=ask_rid)
            else:
                out0, outf = ask_with_clarify_follow(
                    q, branch_needle=None, user=ASK_USER, rid=ask_rid)

            sec = round(time.time() - t0, 2)
            if (out0 or {}).get("diag", {}).get("error"):
                errs += 1

            ok = False
            defect = ""
            fact = ""
            if mode == "digits":
                if PROBE == "okna":
                    ok, defect, fact = score_digits_probe(want, out0)
                else:
                    ok, defect, fact = score_digits(want, out0)
            elif mode == "kind":
                ok, defect, fact = score_kind(sql, want, out0, question=q)
            elif mode == "clarify":
                ok, defect, fact = score_clarify(want, out0)
            elif mode == "name":
                ok, defect, fact = score_name(want, outf)
                # если в финале всё равно clarify — это "лишний clarify"
                if not ok and (outf or {}).get("kind") == "clarify":
                    defect = defect or "лишний clarify"
            else:
                ok, defect, fact = False, "неизвестный режим", "mode=%s" % mode

            hits += 1 if ok else 0
            secs += sec
            got_kind = (out0 or {}).get("kind") or "—"
            rows.append((q, mode, ok, defect, got_kind, fact, sec))
            if not ok:
                failures.append((q, mode, defect or "FAIL", got_kind, fact))
                # красная строка для отчёта гейта / живой самопроверки
                sys.stderr.write(
                    "🔴 FAIL %s | %s | %s (got %s) %s\n"
                    % (mode, (q or "")[:60], defect or "FAIL", got_kind, fact or ""))

        table[sc] = (hits, round(secs / len(computed), 2), rows, errs)
        print("\n== %s: верных %d/%d, средняя %.2f с%s"
              % (sc, hits, len(computed), secs / len(computed),
                 ", СБОЕВ %d" % errs if errs else ""))

        # Markdown-таблица на отчёт.
        print("\n| question | mode | verdict | fact |")
        print("|---|---|---|---|")
        for q, mode, ok, defect, got_kind, fact, sec in rows:
            verdict = "OK" if ok else "FAIL"
            # fact: компактно, но с достаточным контекстом
            kind_part = "kind=%s" % got_kind
            fact_part = fact or ""
            time_part = "%.1fs" % sec
            if ok:
                cell = "%s; %s; %s" % (kind_part, time_part, fact_part)
            else:
                cell = "%s; %s; %s; class=%s" % (kind_part, time_part, fact_part, defect)
            q_cell = (q or "").replace("\n", " ").replace("|", "\\|")
            cell = cell.replace("\n", " ").replace("|", "\\|")
            print("| %s | %s | %s | %s |" % (q_cell[:120], mode, verdict, cell[:160]))

        if failures:
            print("\nПровалы (всего %d):" % len(failures))
            for q, mode, defect, got_kind, fact in failures:
                print("- %s | %s | %s (got %s)" % (mode, q[:60], defect, got_kind))

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
