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
  AB_CALENDAR_AXIS=okna|1 — набор оси календаря ab-calendar-axis-okna.tsv (§7bis §5.2);
    умолчание пусто: набор не подключён. Вместе с AB_CONTOUR/AB_PROBE=okna.
  AB_AMBIGUOUS=okna|1 — приёмка неоднозначности ab-ambiguous-okna.tsv (И1 / Э3);
    умолчание пусто. Один флаг включает live-контур okna (DSN/URL как у CONTOUR).
    AB_GOLD_FILE перекрывает любой выбор.
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
CALENDAR_AXIS = os.environ.get("AB_CALENDAR_AXIS", "").strip().lower()
AMBIGUOUS = os.environ.get("AB_AMBIGUOUS", "").strip().lower()
BASE = os.environ.get("AB_BASE", "ut_test" if GOLD_MODE == "smoke" else "postgres")
ENV_FILE = "/etc/1c-serene-ask-%s.env" % BASE
UNIT = "1c-serene-ask@%s.service" % BASE
ENV_COMMON = "/etc/1c-serene-ask.env"
ENV_PG = "/etc/1c-serene-ask-postgres.env"
ENV_MCP = "/etc/1c-mcp-reports.env"
ASK_USER = os.environ.get("AB_ASK_USER", "gold-v2")
CALENDAR_AXIS_ON = frozenset(("1", "okna", "yes", "true"))
AMBIGUOUS_ON = frozenset(("1", "okna", "yes", "true"))


def resolve_gold_file(environ=None, script_dir=None):
    """Путь к TSV. AB_GOLD_FILE > AB_AMBIGUOUS > AB_CALENDAR_AXIS > AB_PROBE/AB_CONTOUR > ab-gold.tsv.

    AB_AMBIGUOUS / AB_CALENDAR_AXIS пусты — соответствующие наборы не выбираются.
    """
    env = environ if environ is not None else os.environ
    sd = script_dir if script_dir is not None else _SCRIPT_DIR
    explicit = (env.get("AB_GOLD_FILE") or "").strip()
    if explicit:
        return explicit
    amb = (env.get("AB_AMBIGUOUS") or "").strip().lower()
    if amb in AMBIGUOUS_ON:
        return os.path.join(sd, "ab-ambiguous-okna.tsv")
    cal = (env.get("AB_CALENDAR_AXIS") or "").strip().lower()
    if cal in CALENDAR_AXIS_ON:
        return os.path.join(sd, "ab-calendar-axis-okna.tsv")
    probe = (env.get("AB_PROBE") or "").strip().lower()
    contour = (env.get("AB_CONTOUR") or "").strip().lower()
    if probe == "okna" or contour == "okna":
        name = "ab-probe-okna.tsv" if probe == "okna" else "ab-gold-okna.tsv"
        return os.path.join(sd, name)
    return os.path.join(sd, "ab-gold.tsv")


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


GOLD_FILE = resolve_gold_file()
if PROBE == "okna" or CONTOUR == "okna" or AMBIGUOUS in AMBIGUOUS_ON:
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


def _is_sql_spec(spec):
    """Средняя колонка — SQL-эталон (WITH/SELECT), а не литерал иглы clarify."""
    s = (spec or "").strip()
    if not s:
        return False
    return bool(re.match(r"(?is)^\s*(with\b|select\b)", s))


def load_gold(path):
    """Строки набора:
    - v2: вопрос<TAB>SQL<TAB>режим (digits/kind/clarify/name)
    - clarify: средняя колонка — SELECT… или литерал иглы люка (без WITH/SELECT)
    - legacy: вопрос<TAB>SQL (digits) или вопрос<TAB>MODE=kind

    Пустой файл и файл без ни одной разобранной строки — sys.exit(1) с текстом в stderr.
    """
    out = []
    bad = 0
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
                bad += 1
                sys.stderr.write("строка без табуляции: %s\n" % line[:60])
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
                bad += 1
                sys.stderr.write("слишком много колонок: %s\n" % line[:120])
                continue
    if not out:
        why = "битый набор (%d строк без разбора)" % bad if bad else "набор вопросов пуст"
        sys.stderr.write("%s: %s\n" % (why, path))
        sys.exit(1)
    return out


def row_want_spec(row):
    """Что уходит в truth()/score: SQL или литерал иглы clarify."""
    mode = (row.get("mode") or "").strip().lower()
    spec = row.get("sql")
    if mode == "clarify" and spec and not _is_sql_spec(spec):
        return ("needle", spec.strip())
    if spec:
        return ("sql", spec)
    return ("empty", "")


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
    # таймаут одного хопа цепочки; умолчание 100 с (полное окно вопроса — сумма хопов)
    timeout = int(os.environ.get("AB_ASK_TIMEOUT", "100"))
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


def extract_clarify_options(out):
    """options[] ответа /ask; запасной разбор ATOM_JSON из text (формат моста)."""
    if not isinstance(out, dict):
        return []
    opts = out.get("options")
    if isinstance(opts, list) and opts:
        return opts
    text = out.get("text") or ""
    marker = "ATOM_JSON:"
    idx = text.find(marker)
    if idx < 0:
        return []
    raw = text[idx + len(marker):].strip()
    for stop in ("\nPRESENTATION_JSON:", "\n\nPRESENTATION_JSON:"):
        cut = raw.find(stop)
        if cut >= 0:
            raw = raw[:cut].strip()
            break
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        brace = raw.find("{")
        if brace < 0:
            return []
        try:
            payload = json.loads(raw[brace:])
        except (TypeError, ValueError, json.JSONDecodeError):
            return []
    if isinstance(payload, dict):
        inner = payload.get("options")
        if isinstance(inner, list):
            return inner
    return []


def first_option_decision_id(out):
    """decision_id верхней опции (порядок меню уже отсортирован системой)."""
    for o in extract_clarify_options(out):
        if not isinstance(o, dict):
            continue
        did = (o.get("decision_id") or "").strip()
        if did:
            return did
    return None


# Стоп-слова русского вопросного синтаксиса (не домен базы): значимые токены
# вопроса для клика по подписи меню — без «сколько/всего/у нас/…».
_QUESTION_STOP_WORDS = frozenset((
    "сколько", "скольки", "всего", "всей", "всему", "всем", "всех", "все", "всё",
    "у", "нас", "нам", "нами", "наш", "наша", "наши", "нашего", "нашей",
    "дай", "дайте", "давай", "покажи", "покажите", "скажи", "скажите",
    "какой", "какая", "какие", "какое", "каков", "какова", "каково", "каковы",
    "что", "чего", "чему", "чем", "это", "этот", "эта", "эти", "этого", "этой",
    "как", "где", "когда", "кто", "кого", "кому", "чей", "чья", "чье", "чьё",
    "есть", "был", "была", "было", "были", "будет", "будут", "быть",
    "и", "а", "но", "или", "либо", "да", "нет", "не", "ни", "же", "ли", "бы",
    "в", "во", "на", "по", "из", "за", "к", "ко", "от", "до", "для", "при",
    "про", "об", "о", "с", "со", "без", "над", "под", "между", "через",
    "то", "та", "те", "тот", "туда", "там", "тут", "здесь", "сейчас", "теперь",
    "уже", "еще", "ещё", "только", "просто", "очень", "вообще", "нужно", "надо",
    "можно", "пожалуйста", "мне", "меня", "мной", "мы", "вы", "вас", "вам",
    "они", "он", "она", "оно", "их", "его", "ее", "её", "мне", "мои", "моих",
    "ваш", "ваши", "твои", "сей", "сих",
))
_TOKEN_RE = re.compile(r"[0-9a-zA-Zа-яА-ЯёЁ]+", re.UNICODE)
# Окончания русского вопросного/именного склонения (длинные раньше коротких).
_RU_SUFFIXES = (
    "ями", "ами", "ого", "ему", "ими", "ыми", "ах", "ях",
    "ов", "ев", "ей", "ом", "ем", "ам", "ям",
    "ые", "ие", "ое", "ее", "ых", "их", "ым", "им",
    "ой", "ий", "ый", "ая", "яя", "ою", "ею",
    "ы", "и", "а", "я", "у", "ю", "е", "о",
)


def significant_tokens(text):
    """Значимые токены: lower, без стоп-слов вопроса, длина ≥ 3, не чистая цифра."""
    out = []
    raw = str(text or "").lower().replace("ё", "е")
    for tok in _TOKEN_RE.findall(raw):
        if len(tok) < 3 or tok.isdigit() or tok in _QUESTION_STOP_WORDS:
            continue
        out.append(tok)
    return out


def _ru_stem(tok):
    """Грубый стем: снять одно типичное окончание, корень ≥4."""
    w = tok or ""
    for suf in _RU_SUFFIXES:
        if len(w) >= len(suf) + 4 and w.endswith(suf):
            return w[:-len(suf)]
    return w


def _tokens_soft_match(a, b):
    """Равенство, префикс ≥4 или общий стем после снятия окончания."""
    if a == b:
        return True
    if len(a) < 4 or len(b) < 4:
        return False
    if a.startswith(b) or b.startswith(a):
        return True
    sa, sb = _ru_stem(a), _ru_stem(b)
    if len(sa) < 4 or len(sb) < 4:
        return False
    if sa == sb:
        return True
    return sa.startswith(sb) or sb.startswith(sa)


def token_overlap_count(query_tokens, hay_tokens):
    """Сколько токенов вопроса имеют мягкое совпадение в hay."""
    if not query_tokens or not hay_tokens:
        return 0
    n = 0
    for qt in query_tokens:
        if any(_tokens_soft_match(qt, ht) for ht in hay_tokens):
            n += 1
    return n


def option_click_label(o):
    """Подпись опции для отчёта о клике (label[:40])."""
    if not isinstance(o, dict):
        return ""
    lab = (o.get("label") or o.get("text") or "").strip()
    return lab[:40]


def choose_click_option(options, question):
    """Клик как у человека: max совпадений токенов вопроса с label, затем hint.

    Эталон не используется. Ноль совпадений у всех — первая опция с decision_id
    (как прежний click_first). При равном числе совпадений предпочитаем более
    плотное покрытие токенов опции (короткая подпись / hint с нужным словом
    сильнее длинного имени, где слово встретилось случайно).
    """
    if not isinstance(options, list) or not options:
        return None
    opts = [o for o in options if isinstance(o, dict)]
    if not opts:
        return None
    q_toks = significant_tokens(question)
    best = None
    best_key = None  # (hits, density, label_hits, -index)
    for i, o in enumerate(opts):
        label_t = significant_tokens(
            (o.get("label") or o.get("text") or ""))
        hint_t = significant_tokens(o.get("hint") or "")
        # label затем hint — один мешок подписи, которую видит человек
        bag = label_t + [t for t in hint_t if t not in label_t]
        hits = token_overlap_count(q_toks, bag)
        label_hits = token_overlap_count(q_toks, label_t)
        density = (float(hits) / float(len(bag))) if (hits and bag) else 0.0
        key = (hits, density, label_hits, -i)
        if best is None or key > best_key:
            best = o
            best_key = key
    if not best_key or best_key[0] <= 0:
        for o in opts:
            if (o.get("decision_id") or "").strip():
                return o
        return opts[0]
    return best


# Финал цепочки кликов (TARGET п.12/п.21): ответ или честный отказ.
_CHAIN_DONE = frozenset(("answer", "no_data", "figures", "unavailable"))


def ask_with_clarify_follow(question, branch_needle=None, max_steps=4,
                            user=None, rid=None, click_first=False):
    """Цепочка /ask: clarify → клик decision_id → … до answer/no_data.

    click_first=True (digits/name): клик по смыслу подписи (токены вопроса vs
    label/hint), до max_steps кликов; при нуле совпадений — первая опция.
    branch_needle (legacy clarify/name): выбор по подстроке; без needle и без
    click_first — один запрос (kind: кликов нет).
    Возвращает (out0, out_final, hops, total_sec, click_labels);
    hops — число кликов; click_labels — label[:40] каждой выбранной опции.
    """
    user = user or ASK_USER
    out0, out = None, None
    decision_id = None
    hops = 0
    total_sec = 0.0
    click_labels = []
    # max_steps кликов ⇒ до max_steps+1 запросов
    for _step in range(max_steps + 1):
        out, sec = ask(question, decision_id=decision_id, user=user, rid=rid)
        total_sec += float(sec or 0)
        if out0 is None:
            out0 = out
        kind = (out or {}).get("kind") or ""
        if kind in _CHAIN_DONE:
            break
        if kind != "clarify":
            break
        if not click_first and not branch_needle:
            break
        opts = extract_clarify_options(out)
        if click_first:
            chosen = choose_click_option(opts, question)
        else:
            chosen = choose_clarify_option(opts, branch_needle)
        if not chosen:
            break
        decision_id = (chosen.get("decision_id") or "").strip()
        if not decision_id:
            break
        if hops >= max_steps:
            break
        lab = option_click_label(chosen)
        if lab:
            click_labels.append(lab)
        hops += 1
    return out0, out, hops, round(total_sec, 2), click_labels


def want_is_live_number(want):
    """Эталон-число есть (включая 0): no_data при нём — дефект п.21."""
    return bool(want_number_digits(want))


def verdict_digits(want, out, *, stuck_on_clarify=False):
    """Вердикт digits по TARGET: OK/WRONG/HONEST_NO/REFUSAL_WITH_DATA."""
    kind = (out or {}).get("kind") or ""
    if stuck_on_clarify or kind == "clarify":
        return ("REFUSAL_WITH_DATA", "меню без ответа после кликов",
                "kind=clarify")
    if kind == "no_data":
        if want_is_live_number(want):
            return ("REFUSAL_WITH_DATA", "no_data при живом эталоне",
                    "want=%s" % want_number_digits(want))
        return "HONEST_NO", "", "no_data"
    if kind in ("answer", "figures"):
        ok, defect, fact = score_digits(want, out)
        if ok:
            return "OK", "", fact
        return "WRONG", defect or "число не сошлось", fact
    if kind == "unavailable":
        return "REFUSAL_WITH_DATA", "сервис unavailable", "kind=unavailable"
    return ("REFUSAL_WITH_DATA", "нет финального ответа",
            "kind=%s" % (kind or "—"))


def verdict_name(want, out, *, stuck_on_clarify=False):
    """Вердикт name по TARGET: OK/WRONG/HONEST_NO/REFUSAL_WITH_DATA."""
    kind = (out or {}).get("kind") or ""
    if stuck_on_clarify or kind == "clarify":
        return ("REFUSAL_WITH_DATA", "меню без ответа после кликов",
                "kind=clarify")
    if kind == "no_data":
        # имя в эталоне — «живые данные»; no_data при них — дефект п.21
        pairs = parse_name_pairs(want)
        if pairs and any((nm or "").strip() for nm, _nn in pairs):
            return ("REFUSAL_WITH_DATA", "no_data при живом эталоне-имени",
                    "no_data")
        return "HONEST_NO", "", "no_data"
    if kind in ("answer", "figures"):
        ok, defect, fact = score_name(want, out)
        if ok:
            return "OK", "", fact
        return "WRONG", defect or "имя/число не сошлись", fact
    if kind == "unavailable":
        return "REFUSAL_WITH_DATA", "сервис unavailable", "kind=unavailable"
    return ("REFUSAL_WITH_DATA", "нет финального ответа",
            "kind=%s" % (kind or "—"))


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


# Число возраста/свежести в приписке сопровождается единицей времени («N мин»),
# а не величиной: 1439 мин — лаг, не итог ([замер 25.08]).
_AGE_UNIT_NUM = re.compile(
    r"[\d\u0020\u00a0\u2007\u2009\u202f\u200b'.,]+"
    r"\s*(?:мин(?:ут(?:а|ы)?)?|сек(?:унд(?:а|ы)?)?)\b",
    re.IGNORECASE,
)


def aggregate_totals_in_text(text):
    """Числа итогов в text при kind=no_data — брак.

    Возраст/свежесть снимается по единице времени рядом с числом (структура
    приписки), а не по порогу величины. Порог n≥1000 убран: он путал минуты
    лага с итогом. Итог в тексте продукта — с группировкой разрядов или с
    дробной частью; голое целое без того и другого сюда не относится.
    """
    scrubbed = _AGE_UNIT_NUM.sub(" ", text or "")
    for tok in re.findall(r"[\d\u0020\u00a0\u2007\u2009\u202f\u200b'.,]+", scrubbed):
        bare = re.sub(r"\D", "", tok)
        if not bare:
            continue
        if re.search(r"\d[\s\u00a0\u202f\u2009]\d{3}", tok):
            return True
        if re.search(r"[.,]\d", tok):
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
    if AMBIGUOUS in AMBIGUOUS_ON and PROBE != "okna" and CONTOUR != "okna":
        # приёмка неоднозначности — не пишет .golden-*/.probe-* (не smoke-гейт)
        if errs:
            sys.stderr.write(
                "\n🔴 ambiguous: сбоев %d из %d; отметка не ставится.\n" % (errs, n))
            return None
        if hits < n:
            sys.stderr.write(
                "\nambiguous: верных %d из %d (отметка gold/probe не ставится).\n"
                % (hits, n))
            return None
        print("ambiguous okna: %d/%d (без отметки gold/probe)" % (hits, n))
        return best_sc
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
    if AMBIGUOUS in AMBIGUOUS_ON:
        label = "ambiguous-" + (AMBIGUOUS if AMBIGUOUS not in ("1", "yes", "true") else "okna")
    else:
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
        kind, spec = row_want_spec(row)
        if kind == "needle":
            want = spec
        elif kind == "sql":
            # digits/kind: пустой SUM = 0 продаж (валидный эталон), не blind
            # clarify: CAST(NULL)/пустой — sentinel «любой clarify», не blind
            want = truth(spec, empty_as_zero=(mode in ("digits", "kind")))
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
        hits, wrongs, honest_nos, refusals = 0, 0, 0, 0
        secs, errs = 0.0, 0
        rows = []
        failures = []

        for q, sql, mode, want in computed:
            ask_rid = (
                _probe_protocol.new_rid("ab") if _probe_protocol and (PROBE or LIVE_CONTOUR)
                else None)
            # digits/name: клик по смыслу подписи до ответа (п.12/п.21).
            # kind: без кликов (проверка исхода). clarify: без кликов (меню = эталон).
            if mode in ("digits", "name"):
                out0, outf, hops, sec, clicks = ask_with_clarify_follow(
                    q, click_first=True, max_steps=4, user=ASK_USER, rid=ask_rid)
            elif mode == "clarify":
                out0, outf, hops, sec, clicks = ask_with_clarify_follow(
                    q, branch_needle=None, click_first=False, max_steps=0,
                    user=ASK_USER, rid=ask_rid)
            else:
                # kind и прочие: один запрос, кликов нет
                out0, outf, hops, sec, clicks = ask_with_clarify_follow(
                    q, branch_needle=None, click_first=False, max_steps=0,
                    user=ASK_USER, rid=ask_rid)

            if (out0 or {}).get("diag", {}).get("error") or (
                    outf or {}).get("diag", {}).get("error"):
                errs += 1

            defect = ""
            fact = ""
            final_kind = (outf or {}).get("kind") or (out0 or {}).get("kind") or "—"
            stuck = (final_kind == "clarify")
            if mode == "digits":
                verdict, defect, fact = verdict_digits(
                    want, outf, stuck_on_clarify=stuck)
            elif mode == "name":
                verdict, defect, fact = verdict_name(
                    want, outf, stuck_on_clarify=stuck)
            elif mode == "kind":
                ok, defect, fact = score_kind(sql, want, out0, question=q)
                verdict = "OK" if ok else "FAIL"
            elif mode == "clarify":
                ok, defect, fact = score_clarify(want, out0)
                verdict = "OK" if ok else "FAIL"
            else:
                verdict, defect, fact = (
                    "FAIL", "неизвестный режим", "mode=%s" % mode)
            if clicks:
                click_fact = "click=" + " → ".join(clicks)
                fact = ("%s; %s" % (fact, click_fact)) if fact else click_fact

            if verdict == "OK":
                hits += 1
            elif verdict == "WRONG":
                wrongs += 1
            elif verdict == "HONEST_NO":
                honest_nos += 1
            elif verdict == "REFUSAL_WITH_DATA":
                refusals += 1
            else:
                wrongs += 1  # FAIL kind/clarify и прочее → неверных

            secs += sec
            rows.append((q, mode, verdict, defect, final_kind, fact, hops, sec))
            if verdict != "OK":
                failures.append((q, mode, verdict, defect or "FAIL",
                                 final_kind, fact, hops))
                sys.stderr.write(
                    "🔴 %s %s | %s | %s (got %s hops=%d) %s\n"
                    % (verdict, mode, (q or "")[:60], defect or verdict,
                       final_kind, hops, fact or ""))

        n = len(computed)
        avg = round(secs / n, 2) if n else 0.0
        table[sc] = (hits, avg, rows, errs, wrongs, honest_nos, refusals)
        print("\n== %s: верных %d / неверных %d / honest_no %d / "
              "refusal_defect %d  (из %d), средняя цепочка %.2f с%s"
              % (sc, hits, wrongs, honest_nos, refusals, n, avg,
                 ", СБОЕВ %d" % errs if errs else ""))

        print("\n| question | verdict | hops | time | fact |")
        print("|---|---|---|---|---|")
        for q, mode, verdict, defect, got_kind, fact, hops, sec in rows:
            kind_part = "kind=%s" % got_kind
            fact_part = fact or ""
            if verdict == "OK":
                cell = "%s; %s" % (kind_part, fact_part)
            else:
                cell = "%s; %s; class=%s" % (kind_part, fact_part, defect or verdict)
            if mode and mode != "digits":
                cell = "mode=%s; %s" % (mode, cell)
            q_cell = (q or "").replace("\n", " ").replace("|", "\\|")
            cell = cell.replace("\n", " ").replace("|", "\\|")
            print("| %s | %s | %d | %.1fs | %s |"
                  % (q_cell[:120], verdict, hops, sec, cell[:160]))

        if failures:
            print("\nПровалы (всего %d):" % len(failures))
            for q, mode, verdict, defect, got_kind, fact, hops in failures:
                print("- %s | %s | %s | %s (got %s hops=%d)"
                      % (verdict, mode, q[:60], defect, got_kind, hops))

    print("\n" + "=" * 62)
    best = max(table.items(), key=lambda kv: (kv[1][0], -kv[1][1]))
    for sc, (hits, avg, _r, errs, wrongs, honest_nos, refusals) in table.items():
        print("  %-9s верных %d / неверных %d / honest_no %d / "
              "refusal_defect %d  из %d  средняя %.2f с%s%s"
              % (sc, hits, wrongs, honest_nos, refusals, len(gold), avg,
                 "  сбоев %d" % errs if errs else "",
                 "   <= лучший" if sc == best[0] else ""))

    hits, _avg, _rows, errs = best[1][:4]
    return write_mark(best[0], hits, len(gold), errs)


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
