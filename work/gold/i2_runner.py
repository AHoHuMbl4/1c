#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""И2: прогон client-gold двумя путями (движок /ask, веб chatCompletions).

Универсальный измеритель: вопросы и эталоны из TSV, вердикты — механические.
Живой прогон не обязателен для разработки: classify_verdict покрывается моками.

Пути:
  engine — POST /ask (:8091 по умолчанию), JSON kind/text/diag/atom;
  web    — POST /v1/chat/completions (:18801); те же поля, если шлюз их донёс,
           иначе только choices[0].message.content (без kind → unresolved).

Вердикт читает поля решения ask (kind, diag.found, diag.doubt, atom/figures),
не словари фраз в тексте.

Опционально --reshoot-rules + I2_RESHOOT_DSN: эталон «Д»-вопросов пересчитывается
по корпусу тем же SQL в момент прогона (Europe/Chisinau). Без правил — эталоны из TSV.

Env:
  I2_IN              — TSV-набор (умолч. ubuntu/serenedb/client-gold-okna.tsv)
  I2_OUT             — каталог отчёта (умолч. work/gold/runs/i2-<tag>)
  I2_TAG             — метка прогона
  I2_ASK_URL         — URL /ask (engine)
  ASK_TOKEN          — Bearer для engine
  I2_WEB_URL         — URL chatCompletions (web)
  WEB_TOKEN          — Bearer для web (ключ морды)
  I2_ENGINE_TIMEOUT  — сек на вопрос engine (умолч. 120)
  I2_WEB_TIMEOUT     — сек на вопрос web (умолч. 200)
  I2_RETRIES         — ретраи транспорта (умолч. 3)
  I2_RESHOOT_DSN     — DSN корпуса для живой пересъёмки эталонов
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Callable, Optional
from zoneinfo import ZoneInfo

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_SERENEDB = os.path.join(_REPO, "ubuntu", "serenedb")
_GOLD_DIR = os.path.dirname(os.path.abspath(__file__))
if _SERENEDB not in sys.path:
    sys.path.insert(0, _SERENEDB)
if _GOLD_DIR not in sys.path:
    sys.path.insert(0, _GOLD_DIR)

import etalon_1c as E  # noqa: E402

from client_gold import (  # noqa: E402
    fetch_freshness_lag_sec,
    normalize_question,
    parse_client_gold_tsv,
)

CHISINAU = ZoneInfo("Europe/Chisinau")
ETALON_ORIGIN_TSV = "tsv"
ETALON_ORIGIN_LIVE = "live"
ETALON_ORIGIN_ERROR = "reshoot_error"
_MONEY_RULES = frozenset({"sales_sum"})

PATH_ENGINE = "engine"
PATH_WEB = "web"

VERDICT_MATCH = "match"
VERDICT_HONEST_NO = "honest_no"
VERDICT_CONFIDENT_WRONG = "confident_wrong"
VERDICT_UNRESOLVED = "unresolved"

_ALL_VERDICTS = (
    VERDICT_MATCH,
    VERDICT_HONEST_NO,
    VERDICT_CONFIDENT_WRONG,
    VERDICT_UNRESOLVED,
)

_SP = " \u00a0\u2007\u2009\u202f\u200b"
_NUM_RE = re.compile(
    r"\d{1,3}(?:[%s]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?" % _SP
)
_CURRENCY_TAIL = re.compile(r"\s*(?:₽|руб\.?|р\.?|€|\$|usd|eur)\s*$", re.I)

# Значения поля kind ответа /ask (PIPELINE.md §«kind HTTP-ответа»), не словари фраз.
_KIND_HONEST = frozenset({"clarify", "no_data", "unavailable"})
_KIND_ANSWER = frozenset({"answer", "figures"})


def numify_token(tok: str) -> Optional[float]:
    s = re.sub(r"[%s]" % _SP, "", (tok or "").strip())
    s = _CURRENCY_TAIL.sub("", s)
    s = s.replace(",", ".")
    if not s or not re.search(r"\d", s):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def extract_numbers(text: str) -> list[float]:
    if not text:
        return []
    out: list[float] = []
    for m in _NUM_RE.findall(text):
        v = numify_token(m)
        if v is not None:
            out.append(v)
    return out


def _num_from_atom_field(v: Any) -> Optional[float]:
    if v is None or v == "" or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    return numify_token(str(v))


def structured_nums(data: dict) -> list[float]:
    """Числа из полей atom/atoms/figures ответа /ask — без разбора прозы."""
    if not isinstance(data, dict):
        return []
    out: list[float] = []
    atoms: list = []
    raw_atoms = data.get("atoms")
    if isinstance(raw_atoms, list) and raw_atoms:
        atoms = [a for a in raw_atoms if isinstance(a, dict)]
    one = data.get("atom")
    if isinstance(one, dict):
        atoms = atoms or [one]
    for a in atoms:
        for key in ("exact_value", "display_value", "value"):
            n = _num_from_atom_field(a.get(key))
            if n is not None:
                out.append(n)
                break
    figs = data.get("figures")
    if isinstance(figs, dict):
        for key in ("sum", "count", "value", "total", "rows_in_1c", "rows_in_search"):
            n = _num_from_atom_field(figs.get(key))
            if n is not None:
                out.append(n)
    return out


def numbers_match_etalon(nums: list[float], etalon: str) -> bool:
    et = (etalon or "").strip()
    if not et or et.lower() == "no_data":
        return False
    if not nums:
        return False
    try:
        ev = E.to_decimal(et.replace(" ", "").replace(",", "."))
    except ValueError:
        return False
    return any(E.numbers_equal(n, ev) for n in nums)


def ask_fields_from_payload(data: Any) -> tuple[str, dict, list[float], str]:
    """Достать kind/diag/nums из JSON /ask или вложенного конверта шлюза.

    Возвращает (kind, diag, nums, text). Пустой kind — полей решения в полезной
    нагрузке нет (типичный chatCompletions: только choices[].message.content).
    """
    if not isinstance(data, dict):
        return "", {}, [], ""

    # Прямой ответ /ask или явный вложенный конверт.
    candidates: list[dict] = [data]
    for key in ("ask", "ask_result", "result", "data"):
        nested = data.get(key)
        if isinstance(nested, dict):
            candidates.append(nested)

    for cand in candidates:
        k = cand.get("kind")
        if isinstance(k, str) and k.strip():
            diag = cand.get("diag") if isinstance(cand.get("diag"), dict) else {}
            text = str(cand.get("text") or cand.get("answer") or "")
            nums = structured_nums(cand) or extract_numbers(text)
            return k.strip(), diag, nums, text

    # OpenAI-стиль: только текст ассистента — структурных полей ask нет.
    text = ""
    try:
        choices = data.get("choices") or []
        if choices:
            msg = choices[0].get("message") or {}
            text = msg.get("content") or ""
    except (AttributeError, IndexError, TypeError):
        text = ""
    return "", {}, extract_numbers(text), text


def classify_verdict(
    *,
    text: str = "",
    etalon: str = "",
    kind: str = "",
    diag: Optional[dict] = None,
    transport_error: str = "",
    nums: Optional[list[float]] = None,
) -> str:
    """Механический вердикт И2 по полям ответа /ask, не по фразам текста.

    kind ∈ {clarify, no_data, unavailable} → honest_no;
    kind ∈ {answer, figures} + число = эталон → match, иначе confident_wrong;
    diag.found == 0 или diag.doubt is True при числе → confident_wrong;
    нет kind / транспорт / пусто → unresolved.
    """
    if transport_error:
        return VERDICT_UNRESOLVED

    diag = diag or {}
    t = (text or "").strip()
    k = (kind or "").strip().lower()
    et = (etalon or "").strip()
    if nums is None:
        nums = extract_numbers(t)
    else:
        nums = list(nums)

    if not t and not k and not nums:
        return VERDICT_UNRESOLVED

    matches_raw = diag.get("found")
    if matches_raw is not None and nums:
        try:
            if int(matches_raw) == 0:
                return VERDICT_CONFIDENT_WRONG
        except (TypeError, ValueError):
            pass

    if diag.get("doubt") is True and nums:
        return VERDICT_CONFIDENT_WRONG

    if k in _KIND_HONEST:
        return VERDICT_HONEST_NO

    if k in _KIND_ANSWER:
        if not nums:
            return VERDICT_UNRESOLVED
        if et.lower() == "no_data":
            return VERDICT_CONFIDENT_WRONG
        if et:
            if numbers_match_etalon(nums, et):
                return VERDICT_MATCH
            return VERDICT_CONFIDENT_WRONG
        return VERDICT_UNRESOLVED

    # Без поля kind (веб-шлюз не доносит конверт ask) вердикт не вывести.
    return VERDICT_UNRESOLVED


@dataclass
class PathAnswer:
    path: str
    text: str = ""
    kind: str = ""
    diag: dict = field(default_factory=dict)
    nums: list[float] = field(default_factory=list)
    latency_s: float = 0.0
    transport_error: str = ""
    verdict: str = VERDICT_UNRESOLVED

    def __post_init__(self) -> None:
        if not self.nums and self.text:
            self.nums = extract_numbers(self.text)


@dataclass
class QuestionRow:
    question: str
    etalon: str
    engine: Optional[PathAnswer] = None
    web: Optional[PathAnswer] = None
    etalon_origin: str = ETALON_ORIGIN_TSV
    reshoot_error: str = ""


def chisinau_today(now: Optional[datetime] = None) -> date:
    """«Сегодня» сервиса: Europe/Chisinau, не CURRENT_DATE базы (UTC)."""
    if now is None:
        now = datetime.now(CHISINAU)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=CHISINAU)
    else:
        now = now.astimezone(CHISINAU)
    return now.date()


def week_start(d: date) -> date:
    """Понедельник календарной недели (как date_trunc('week', …))."""
    return d - timedelta(days=d.weekday())


def last_sunday(d: date) -> date:
    """Последнее прошедшее воскресенье: today - (isodow % 7)."""
    return d - timedelta(days=(d.isoweekday() % 7))


def month_start(d: date) -> date:
    return d.replace(day=1)


def month_start_prev(d: date) -> date:
    ms = month_start(d)
    return (ms - timedelta(days=1)).replace(day=1)


def eval_bound_expr(expr: Optional[str], d: date) -> Optional[date]:
    """Выражение границы из правил → дата относительно Chisinau-сегодня d."""
    if expr is None or expr == "":
        return None
    e = str(expr).strip()
    if e == "today":
        return d
    if e == "today-1":
        return d - timedelta(days=1)
    if e == "today-2":
        return d - timedelta(days=2)
    if e == "today+1":
        return d + timedelta(days=1)
    if e == "today-30":
        return d - timedelta(days=30)
    if e == "today-365":
        return d - timedelta(days=365)
    if e == "week_start":
        return week_start(d)
    if e == "week_start-7":
        return week_start(d) - timedelta(days=7)
    if e == "month_start":
        return month_start(d)
    if e == "month_start-1m":
        return month_start_prev(d)
    if e == "last_sunday":
        return last_sunday(d)
    if e == "last_sunday+1":
        return last_sunday(d) + timedelta(days=1)
    raise ValueError("unknown bound expr: %r" % (expr,))


def load_reshoot_rules(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)
    if not isinstance(raw, dict) or "rules" not in raw or "bindings" not in raw:
        raise ValueError("reshoot-rules: нужен объект {rules, bindings}")
    return raw


def fill_rule_sql(
    sql: str,
    *,
    from_d: Optional[date] = None,
    to_d: Optional[date] = None,
    table: Optional[str] = None,
) -> str:
    """Подстановка {from}/{to}/{table} в SQL правила."""
    out = sql
    if table is not None:
        out = out.replace("{table}", table)
    if from_d is not None:
        out = out.replace("{from}", from_d.isoformat())
    if to_d is not None:
        out = out.replace("{to}", to_d.isoformat())
    return out


def format_reshoot_etalon(value: Any, *, money: bool) -> str:
    """Формат эталона как в TSV: money → 2 знака, счёт → целое."""
    if value is None or str(value).strip() == "":
        return "0.00" if money else "0"
    if money:
        try:
            d = E.to_decimal(value)
        except ValueError:
            d = Decimal("0")
        q = d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return format(q, "f")
    try:
        d = E.to_decimal(value)
        return str(int(d))
    except (ValueError, OverflowError):
        return str(value).strip()


@dataclass
class ReshootStats:
    live: int = 0
    tsv: int = 0
    reshoot_error: int = 0
    freshness_lag_sec: Optional[int] = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "live": self.live,
            "tsv": self.tsv,
            "reshoot_error": self.reshoot_error,
            "freshness_lag_sec": self.freshness_lag_sec,
        }


def reshoot_row_etalon(
    row: QuestionRow,
    rules_doc: dict,
    client: E.CorpusClient,
    *,
    today: Optional[date] = None,
) -> str:
    """Переснять эталон одной строки. Возвращает origin: live|tsv|reshoot_error."""
    bindings = rules_doc.get("bindings") or {}
    rules = rules_doc.get("rules") or {}
    key = normalize_question(row.question)
    binding = bindings.get(key)
    if not binding:
        row.etalon_origin = ETALON_ORIGIN_TSV
        row.reshoot_error = ""
        return ETALON_ORIGIN_TSV

    rule_id = binding.get("rule") or ""
    rule = rules.get(rule_id) or {}
    if rule.get("no_data"):
        row.etalon = "no_data"
        row.etalon_origin = ETALON_ORIGIN_LIVE
        row.reshoot_error = ""
        return ETALON_ORIGIN_LIVE

    sql_tpl = rule.get("sql") or ""
    if not sql_tpl:
        row.etalon_origin = ETALON_ORIGIN_ERROR
        row.reshoot_error = "empty sql for rule %s" % rule_id
        return ETALON_ORIGIN_ERROR

    d = today or chisinau_today()
    bounds = binding.get("bounds") or [None, None]
    if len(bounds) < 2:
        bounds = list(bounds) + [None] * (2 - len(bounds))
    try:
        from_d = eval_bound_expr(bounds[0], d)
        to_d = eval_bound_expr(bounds[1], d)
    except ValueError as exc:
        row.etalon_origin = ETALON_ORIGIN_ERROR
        row.reshoot_error = str(exc)
        return ETALON_ORIGIN_ERROR

    table = binding.get("table")
    sql = fill_rule_sql(sql_tpl, from_d=from_d, to_d=to_d, table=table)
    if "{from}" in sql or "{to}" in sql or "{table}" in sql:
        row.etalon_origin = ETALON_ORIGIN_ERROR
        row.reshoot_error = "unfilled placeholder in sql"
        return ETALON_ORIGIN_ERROR

    try:
        raw = client.scalar(sql)
    except Exception as exc:  # noqa: BLE001 — прибор фиксирует любую ошибку SQL
        row.etalon_origin = ETALON_ORIGIN_ERROR
        row.reshoot_error = "%s: %s" % (type(exc).__name__, exc)
        return ETALON_ORIGIN_ERROR

    money = rule_id in _MONEY_RULES
    row.etalon = format_reshoot_etalon(raw, money=money)
    row.etalon_origin = ETALON_ORIGIN_LIVE
    row.reshoot_error = ""
    return ETALON_ORIGIN_LIVE


def apply_reshoot(
    rows: list[QuestionRow],
    rules_doc: dict,
    client: E.CorpusClient,
    *,
    today: Optional[date] = None,
) -> ReshootStats:
    """Один раз на вопрос до HTTP: живой эталон для обоих путей."""
    stats = ReshootStats()
    try:
        lag = fetch_freshness_lag_sec(client)
        stats.freshness_lag_sec = lag
    except Exception:  # noqa: BLE001
        stats.freshness_lag_sec = None

    d = today or chisinau_today()
    for row in rows:
        origin = reshoot_row_etalon(row, rules_doc, client, today=d)
        if origin == ETALON_ORIGIN_LIVE:
            stats.live += 1
        elif origin == ETALON_ORIGIN_ERROR:
            stats.reshoot_error += 1
        else:
            stats.tsv += 1
    return stats


def force_reshoot_error_verdicts(rows: list[QuestionRow]) -> None:
    """Строки с ошибкой пересъёмки → unresolved (оба пути), прогон не рвётся."""
    for row in rows:
        if row.etalon_origin != ETALON_ORIGIN_ERROR:
            continue
        reason = "reshoot_error: %s" % (row.reshoot_error or "unknown")
        for ans in (row.engine, row.web):
            if ans is None:
                continue
            ans.verdict = VERDICT_UNRESOLVED
            if not ans.transport_error:
                ans.transport_error = reason


def _http_post_json(
    url: str,
    token: str,
    body: dict,
    *,
    timeout: int,
    retries: int,
) -> tuple[Optional[Any], str]:
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + (token or ""),
    }
    last_err = ""
    for attempt in range(max(1, retries)):
        req = urllib.request.Request(url, data=payload, method="POST", headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw), ""
        except Exception as exc:  # noqa: BLE001 — прибор фиксирует любую ошибку
            last_err = "%s: %s" % (type(exc).__name__, exc)
            if attempt + 1 < retries:
                time.sleep(min(3 * (attempt + 1), 10))
    return None, last_err


def ask_engine(
    question: str,
    *,
    url: str,
    token: str,
    timeout: int,
    retries: int,
) -> PathAnswer:
    t0 = time.time()
    data, err = _http_post_json(
        url,
        token,
        {"question": question},
        timeout=timeout,
        retries=retries,
    )
    lat = round(time.time() - t0, 2)
    if data is None:
        return PathAnswer(
            path=PATH_ENGINE,
            transport_error=err,
            latency_s=lat,
        )
    kind, diag, nums, text = ask_fields_from_payload(data)
    return PathAnswer(
        path=PATH_ENGINE,
        text=text,
        kind=kind,
        diag=diag,
        nums=nums,
        latency_s=lat,
    )


def ask_web(
    question: str,
    *,
    url: str,
    token: str,
    timeout: int,
    retries: int,
    model: str = "",
) -> PathAnswer:
    t0 = time.time()
    body = {
        "model": model or os.environ.get("I2_WEB_MODEL", "main"),
        "messages": [{"role": "user", "content": question}],
    }
    data, err = _http_post_json(url, token, body, timeout=timeout, retries=retries)
    lat = round(time.time() - t0, 2)
    if data is None:
        return PathAnswer(
            path=PATH_WEB,
            transport_error=err,
            latency_s=lat,
        )
    kind, diag, nums, text = ask_fields_from_payload(data)
    if not text.strip() and not kind:
        return PathAnswer(
            path=PATH_WEB,
            transport_error="empty web content",
            latency_s=lat,
        )
    return PathAnswer(
        path=PATH_WEB,
        text=text,
        kind=kind,
        diag=diag,
        nums=nums,
        latency_s=lat,
    )


def _apply_verdict(row: QuestionRow, ans: PathAnswer) -> PathAnswer:
    ans.verdict = classify_verdict(
        text=ans.text,
        etalon=row.etalon,
        kind=ans.kind,
        diag=ans.diag,
        transport_error=ans.transport_error,
        nums=ans.nums if ans.nums else None,
    )
    return ans


def run_path(
    rows: list[QuestionRow],
    path: str,
    ask_fn: Callable[[str], PathAnswer],
    workers: int = 1,
) -> None:
    """Прогон одного пути. workers>1 — пул потоков: каждый вопрос пишет только
    свой row (row.engine/row.web), общих мутаций нет; ответ порядка не требует
    (summarize идёт после join). [01.09] последовательный прогон 67×2 занимал
    часы; параллель 6 держится и движком (ThreadingHTTPServer), и vLLM
    (max-num-seqs 8)."""
    def _one(row: QuestionRow) -> None:
        ans = ask_fn(row.question)
        ans = _apply_verdict(row, ans)
        if path == PATH_ENGINE:
            row.engine = ans
        else:
            row.web = ans

    if workers <= 1:
        for row in rows:
            _one(row)
        return
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(_one, rows))


def summarize(rows: list[QuestionRow], path: str) -> dict[str, Any]:
    n = len(rows)
    counts = {v: 0 for v in _ALL_VERDICTS}
    for row in rows:
        ans = row.engine if path == PATH_ENGINE else row.web
        if ans is None:
            counts[VERDICT_UNRESOLVED] += 1
        else:
            counts[ans.verdict] = counts.get(ans.verdict, 0) + 1
    honest = counts.get(VERDICT_HONEST_NO, 0)
    return {
        "path": path,
        "total": n,
        "counts": counts,
        "confident_wrong": counts.get(VERDICT_CONFIDENT_WRONG, 0),
        "honest_no": honest,
        "honest_no_share": round(honest / n, 4) if n else 0.0,
    }


def format_report(
    rows: list[QuestionRow],
    summaries: dict[str, dict],
    *,
    reshoot: Optional[ReshootStats] = None,
) -> str:
    lines: list[str] = []
    lines.append("# И2 client-gold: два пути")
    lines.append("")
    if reshoot is not None:
        lag = reshoot.freshness_lag_sec
        lag_s = str(lag) if lag is not None else "?"
        lines.append("## эталоны")
        lines.append(
            "эталоны: live %d / tsv %d; reshoot_error %d; freshness_lag_sec=%s"
            % (reshoot.live, reshoot.tsv, reshoot.reshoot_error, lag_s)
        )
        lines.append("")
    for key in (PATH_ENGINE, PATH_WEB):
        s = summaries.get(key)
        if not s:
            continue
        cw = s["confident_wrong"]
        n = s["total"]
        lines.append(
            "## %s: уверенно неверных = %d из %d; honest_no = %d (%.1f%%)"
            % (
                key,
                cw,
                n,
                s["honest_no"],
                100.0 * s["honest_no_share"],
            )
        )
        lines.append("вердикты: " + json.dumps(s["counts"], ensure_ascii=False))
        lines.append("")

    lines.append("## построчная разница путей")
    lines.append(
        "question\tetalon\tetalon_origin\tverdict_engine\tverdict_web\t"
        "nums_engine\tnums_web\tlatency_engine_s\tlatency_web_s"
    )
    for row in rows:
        e = row.engine
        w = row.web
        ne = ";".join(
            ("%.4g" % x).rstrip("0").rstrip(".") for x in (e.nums[:4] if e else [])
        )
        nw = ";".join(
            ("%.4g" % x).rstrip("0").rstrip(".") for x in (w.nums[:4] if w else [])
        )
        lines.append(
            "\t".join(
                [
                    row.question.replace("\t", " ").replace("\n", " "),
                    str(row.etalon or ""),
                    row.etalon_origin or ETALON_ORIGIN_TSV,
                    (e.verdict if e else "—"),
                    (w.verdict if w else "—"),
                    ne or "—",
                    nw or "—",
                    str(e.latency_s if e else ""),
                    str(w.latency_s if w else ""),
                ]
            )
        )
    return "\n".join(lines) + "\n"


def load_gold_rows(tsv_path: str) -> list[QuestionRow]:
    with open(tsv_path, encoding="utf-8") as fh:
        raw = parse_client_gold_tsv(fh.read())
    out: list[QuestionRow] = []
    for r in raw:
        q = (r.get("question") or "").strip()
        if not q:
            continue
        out.append(QuestionRow(question=q, etalon=str(r.get("etalon") or "")))
    return out


def default_out_dir(tag: Optional[str] = None) -> str:
    base = os.path.join(_REPO, "work", "gold", "runs")
    if tag:
        return os.path.join(base, "i2-%s" % tag)
    n = 1
    if os.path.isdir(base):
        existing = [d for d in os.listdir(base) if d.startswith("i2-")]
        n = len(existing) + 1
    return os.path.join(base, "i2-run%d" % n)


def run_i2(
    rows: list[QuestionRow],
    *,
    paths: list[str],
    engine_ask: Optional[Callable[[str], PathAnswer]] = None,
    web_ask: Optional[Callable[[str], PathAnswer]] = None,
    out_dir: Optional[str] = None,
    reshoot_stats: Optional[ReshootStats] = None,
    workers: int = 1,
) -> tuple[list[QuestionRow], dict[str, dict], str]:
    """Прогон набора. ask_* — подмена для тестов.

    reshoot_stats — уже посчитанные живые эталоны (один раз на вопрос до HTTP).
    workers>1 — вопросы пути идут параллельно (пул потоков, см. run_path).
    """
    summaries: dict[str, dict] = {}
    if PATH_ENGINE in paths:
        fn = engine_ask or (lambda q: PathAnswer(path=PATH_ENGINE, transport_error="no engine mock"))
        run_path(rows, PATH_ENGINE, fn, workers=workers)
        summaries[PATH_ENGINE] = summarize(rows, PATH_ENGINE)
    if PATH_WEB in paths:
        fn = web_ask or (lambda q: PathAnswer(path=PATH_WEB, transport_error="no web mock"))
        run_path(rows, PATH_WEB, fn, workers=workers)
        summaries[PATH_WEB] = summarize(rows, PATH_WEB)

    force_reshoot_error_verdicts(rows)
    # пересчёт counts после принудительного unresolved на reshoot_error
    for p in list(summaries):
        summaries[p] = summarize(rows, p)

    if reshoot_stats is not None:
        summaries["etalons"] = {
            "live": reshoot_stats.live,
            "tsv": reshoot_stats.tsv,
            "reshoot_error": reshoot_stats.reshoot_error,
            "freshness_lag_sec": reshoot_stats.freshness_lag_sec,
            "summary": "эталоны: live %d / tsv %d"
            % (reshoot_stats.live, reshoot_stats.tsv),
        }

    report = format_report(rows, summaries, reshoot=reshoot_stats)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, "i2-report.md"), "w", encoding="utf-8") as fh:
            fh.write(report)
        with open(os.path.join(out_dir, "i2-summary.json"), "w", encoding="utf-8") as fh:
            json.dump(summaries, fh, ensure_ascii=False, indent=2)
        jl = os.path.join(out_dir, "i2-answers.jsonl")
        with open(jl, "w", encoding="utf-8") as fh:
            for row in rows:
                rec = {
                    "question": row.question,
                    "etalon": row.etalon,
                    "etalon_origin": row.etalon_origin,
                    "reshoot_error": row.reshoot_error,
                    "engine": None,
                    "web": None,
                }
                if row.engine:
                    rec["engine"] = {
                        "verdict": row.engine.verdict,
                        "kind": row.engine.kind,
                        "text": row.engine.text[:500],
                        "nums": row.engine.nums[:8],
                        "latency_s": row.engine.latency_s,
                        "error": row.engine.transport_error,
                    }
                if row.web:
                    rec["web"] = {
                        "verdict": row.web.verdict,
                        "text": row.web.text[:500],
                        "nums": row.web.nums[:8],
                        "latency_s": row.web.latency_s,
                        "error": row.web.transport_error,
                    }
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rows, summaries, report


def cmd_run(args: argparse.Namespace) -> int:
    tsv = args.tsv or os.environ.get(
        "I2_IN",
        os.path.join(_REPO, "ubuntu", "serenedb", "client-gold-okna.tsv"),
    )
    paths = args.paths or [PATH_ENGINE, PATH_WEB]
    out_dir = args.out or os.environ.get("I2_OUT") or default_out_dir(
        os.environ.get("I2_TAG")
    )

    rows = load_gold_rows(tsv)
    if not rows:
        print("пустой набор: %s" % tsv, file=sys.stderr)
        return 2

    rules_path = (args.reshoot_rules or "").strip()
    reshoot_dsn = (
        os.environ.get("I2_RESHOOT_DSN")
        or os.environ.get("SERENEDB_DSN")
        or ""
    ).strip()
    reshoot_stats: Optional[ReshootStats] = None
    rules_doc: Optional[dict] = None
    if rules_path:
        rules_doc = load_reshoot_rules(rules_path)
        if not reshoot_dsn and not args.dry:
            print(
                "нужен I2_RESHOOT_DSN (или SERENEDB_DSN) при --reshoot-rules",
                file=sys.stderr,
            )
            return 2

    engine_url = (
        args.engine_url
        or os.environ.get("I2_ASK_URL")
        or os.environ.get("ASK_URL")
        or "http://127.0.0.1:8091/ask"
    ).rstrip("/")
    if not engine_url.endswith("/ask"):
        engine_url = engine_url + "/ask"

    web_url = (
        args.web_url
        or os.environ.get("I2_WEB_URL")
        or "http://127.0.0.1:18801/v1/chat/completions"
    )
    engine_token = args.engine_token or os.environ.get("ASK_TOKEN", "")
    web_token = args.web_token or os.environ.get("WEB_TOKEN", "")
    engine_timeout = int(
        args.engine_timeout
        or os.environ.get("I2_ENGINE_TIMEOUT")
        or 120
    )
    web_timeout = int(
        args.web_timeout or os.environ.get("I2_WEB_TIMEOUT") or 200
    )
    retries = int(args.retries or os.environ.get("I2_RETRIES") or 3)
    workers = int(
        getattr(args, "workers", 0) or os.environ.get("I2_WORKERS") or 1
    )

    engine_ask = None
    web_ask = None
    if PATH_ENGINE in paths:
        if not engine_token and not args.dry:
            print("нужен ASK_TOKEN для engine", file=sys.stderr)
            return 2
        engine_ask = lambda q, u=engine_url, t=engine_token: ask_engine(  # noqa: E731
            q, url=u, token=t, timeout=engine_timeout, retries=retries,
        )
    if PATH_WEB in paths:
        if not web_token and not args.dry:
            print("нужен WEB_TOKEN для web", file=sys.stderr)
            return 2
        web_ask = lambda q, u=web_url, t=web_token: ask_web(  # noqa: E731
            q, url=u, token=t, timeout=web_timeout, retries=retries,
        )

    if args.dry:
        extra = ""
        if rules_path:
            extra = "; reshoot-rules=%s dsn=%s" % (
                rules_path,
                "set" if reshoot_dsn else "unset",
            )
        print(
            "dry-run: %d вопросов, paths=%s → %s%s"
            % (len(rows), paths, out_dir, extra)
        )
        return 0

    if rules_doc is not None:
        client = E.CorpusClient(reshoot_dsn)
        reshoot_stats = apply_reshoot(rows, rules_doc, client)
        sys.stderr.write(
            "эталоны: live %d / tsv %d (reshoot_error %d)\n"
            % (
                reshoot_stats.live,
                reshoot_stats.tsv,
                reshoot_stats.reshoot_error,
            )
        )

    _, summaries, report = run_i2(
        rows,
        paths=paths,
        engine_ask=engine_ask,
        web_ask=web_ask,
        out_dir=out_dir,
        reshoot_stats=reshoot_stats,
        workers=workers,
    )
    print(report)
    sys.stderr.write("отчёт: %s\n" % out_dir)
    for p, s in summaries.items():
        if p == "etalons":
            sys.stderr.write("%s\n" % s.get("summary", s))
            continue
        sys.stderr.write(
            "%s: уверенно неверных = %d из %d\n"
            % (p, s["confident_wrong"], s["total"])
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="И2: client-gold × engine/web")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="прогон набора двумя путями")
    r.add_argument(
        "--tsv",
        default="",
        help="client-gold TSV (умолч. ubuntu/serenedb/client-gold-okna.tsv)",
    )
    r.add_argument(
        "--path",
        dest="paths",
        action="append",
        choices=[PATH_ENGINE, PATH_WEB],
        help="путь (можно дважды: engine и web)",
    )
    r.add_argument("--out", default="", help="каталог отчёта")
    r.add_argument("--engine-url", default="")
    r.add_argument("--web-url", default="")
    r.add_argument("--engine-token", default="")
    r.add_argument("--web-token", default="")
    r.add_argument("--engine-timeout", type=int, default=0)
    r.add_argument("--web-timeout", type=int, default=0)
    r.add_argument("--retries", type=int, default=0)
    r.add_argument(
        "--reshoot-rules",
        default="",
        help="JSON правил живой пересъёмки эталонов (корпус); без него — TSV",
    )
    r.add_argument(
        "--dry",
        action="store_true",
        help="только проверка env/набора, без HTTP",
    )
    r.add_argument(
        "--workers",
        type=int,
        default=0,
        help="параллельных вопросов на путь (умолч. 1; env I2_WORKERS)",
    )
    r.set_defaults(func=cmd_run)
    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    sys.exit(main())
