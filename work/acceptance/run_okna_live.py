#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Приёмочный прогон okna по живым правилам docs/ACCEPTANCE_OKNA_LIVE.md.

И2а: только измеряет. Ничего не правит. Эталон — одним SQL к корпусу okna
в момент вопроса (класс Д — обязательно корпус, A2; класс С — тот же SQL).

Окружение:
  OKNA_DSN   — строка подключения к движку okna
  ASK_URL    — URL эндпоинта /ask
  ASK_TOKEN  — Bearer-токен

Вопросы — список QUESTIONS ниже, дословно из раздела B спека
(docs/ACCEPTANCE_OKNA_LIVE.md §B1–B7). Контрольные числа 19.08 в этом файле
не хранятся: они только в спеке для сверки реализации.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Optional
from zoneinfo import ZoneInfo

SPEC = "docs/ACCEPTANCE_OKNA_LIVE.md"
SPEC_TODAY_SQL = "timezone('Europe/Chisinau', now())::date"
CHISINAU = ZoneInfo("Europe/Chisinau")
UTC = timezone.utc

# Разделители разрядов (типографика, не база) — как в run_acceptance / гейте.
_SP = " \u00a0\u2007\u2009\u202f\u200b"
_NUM_RE = re.compile(
    r"\d{1,3}(?:[%s]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?" % _SP
)
_CURRENCY_TAIL = re.compile(
    r"(?:\s*(?:лей|леев|молдавск\w*|mdl|lei|eur|евро|руб\.?|₽))?\s*$",
    re.I,
)

TODAY_CTE = "WITH today AS (SELECT timezone('Europe/Chisinau', now())::date AS d)"
SRC_SALES = "accumulationregister_реализациятмц"
NUM_TOTAL = "nums['Всего']"
NUM_QTY = "nums['Количество']"
REF_CLIENT = "refs_map['Контрагент']"
REF_SKU = "refs_map['ТМЦ']"


# ── календарь / «сегодня» (A1) ───────────────────────────────────────────────

def chisinau_today(when: Optional[datetime] = None) -> date:
    """«Сегодня» как у сервиса: Europe/Chisinau, не CURRENT_DATE по UTC (A1)."""
    if when is None:
        when = datetime.now(tz=UTC)
    elif when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return when.astimezone(CHISINAU).date()


def utc_vs_chisinau_split(when_utc: datetime) -> dict:
    """Окно 00:00–03:00 Кишинёв: UTC-дата и кишинёвская расходятся на день (A1)."""
    if when_utc.tzinfo is None:
        when_utc = when_utc.replace(tzinfo=UTC)
    chi = when_utc.astimezone(CHISINAU)
    return {
        "utc_date": when_utc.astimezone(UTC).date(),
        "chisinau_date": chi.date(),
        "chisinau_hour": chi.hour,
        "split": when_utc.astimezone(UTC).date() != chi.date(),
        "in_split_window": 0 <= chi.hour < 3,
    }


def today_sql_fragment() -> str:
    """Фрагмент SQL «сегодня» — совпадает со спеком A1 (проверяется замком)."""
    return SPEC_TODAY_SQL


# ── числа из ответа (B: разрядка и копейки не важны) ─────────────────────────

def numify_token(tok: str) -> Optional[float]:
    s = re.sub(r"[%s]" % _SP, "", tok.strip())
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


def numbers_close(a: float, b: float) -> bool:
    """Совпадение до копейки или целой части (разрядка/копейки не важны, §B1)."""
    if a is None or b is None:
        return False
    return round(float(a), 2) == round(float(b), 2) or round(float(a)) == round(float(b))


def number_in_answer(answer: str, expected: float, *, allow_currency_noise: bool = True) -> bool:
    """Цифра эталона встречается в ответе; валютный хвост не мешает."""
    _ = allow_currency_noise  # хвост снимается в numify_token
    return any(numbers_close(n, expected) for n in extract_numbers(answer))


def looks_like_day_substitution(answer: str, *, etalon_zero: bool, friday_value: Optional[float] = None) -> bool:
    """Понедельник «вчера»=0: пятница молча вместо нуля — подмена дня (A4 / §B1 ложь).

    Если эталон — честный ноль, а в ответе названо число пятницы без оговорки
    про выходной/воскресенье — это подмена дня.
    """
    if not etalon_zero:
        return False
    text = (answer or "").lower()
    honest = any(
        w in text
        for w in (
            "выходн", "воскресень", "суббот", "не работал", "продаж не было",
            "нулев", "нет продаж", "без продаж",
        )
    )
    if honest:
        return False
    nums = extract_numbers(answer)
    nonzero = [n for n in nums if abs(n) > 0.009]
    if not nonzero:
        return False
    if friday_value is not None and any(numbers_close(n, friday_value) for n in nonzero):
        return True
    # Любое ненулевое без оговорки при эталоне 0 — подозрение на подмену.
    return True


# ── имена по префиксу (A5.6) ─────────────────────────────────────────────────

def name_core(ref: str) -> str:
    """refs_map: «Имя / код / адрес» → имя до первого « / »."""
    s = (ref or "").strip()
    if " / " in s:
        s = s.split(" / ", 1)[0]
    elif "/" in s:
        s = s.split("/", 1)[0]
    return s.strip()


def name_prefix_match(answer: str, ref_or_name: str, *, min_len: int = 8) -> bool:
    """Сравнение по префиксу имени (без кода/адреса)."""
    core = name_core(ref_or_name)
    if not core or not answer:
        return False
    a = answer.lower()
    c = core.lower()
    if c in a:
        return True
    # короткий префикс — не меньше min_len символов значимого начала
    pref = c[: max(min_len, min(len(c), 12))]
    return len(pref) >= 4 and pref in a


# ── ничьи в топ-N (A5.7 / B2) ────────────────────────────────────────────────

def group_ties(rows: list[tuple[str, float]]) -> list[list[tuple[str, float]]]:
    """Группы равных величин в порядке убывания."""
    groups: list[list[tuple[str, float]]] = []
    for name, val in rows:
        if groups and numbers_close(groups[-1][0][1], val):
            groups[-1].append((name, val))
        else:
            groups.append([(name, val)])
    return groups


def accept_top_n(
    answer: str,
    rows: list[tuple[str, float]],
    n: int = 3,
) -> tuple[bool, str]:
    """Топ-N: n имён; при ничьей — любые из равных + оговорка (A5.7).

    `rows` уже с запасом (LIMIT n+2), чтобы увидеть ничью.
    """
    if not rows:
        return False, "эталон пуст"
    groups = group_ties(rows)
    # Набираем слоты топ-n с учётом ничьих
    selected: list[tuple[str, float]] = []
    tie_note_needed = False
    for g in groups:
        if len(selected) >= n:
            break
        need = n - len(selected)
        if len(g) > need:
            # ничья пересекает границу топа
            tie_note_needed = True
            matched = [r for r in g if name_prefix_match(answer, r[0])]
            if len(matched) < need:
                return False, "ничья: мало имён из равных (есть %d, нужно %d)" % (
                    len(matched), need)
            if not number_in_answer(answer, g[0][1]):
                return False, "ничья: число %s не в ответе" % g[0][1]
            for r in matched[:need]:
                selected.append(r)
        else:
            if len(g) > 1:
                tie_note_needed = True
            for r in g:
                if len(selected) >= n:
                    break
                selected.append(r)
                if not name_prefix_match(answer, r[0]):
                    return False, "нет имени %s" % name_core(r[0])[:40]
                if not number_in_answer(answer, r[1]):
                    return False, "нет числа %s у %s" % (r[1], name_core(r[0])[:30])

    if len(selected) < n and len(rows) >= n:
        return False, "набрано имён %d < %d" % (len(selected), n)

    if tie_note_needed:
        low = (answer or "").lower()
        if not any(w in low for w in ("ничь", "равн", "одинаков", "поровну", "tie")):
            return False, "ничья без оговорки"
    return True, "топ-%d + ничья" % n if tie_note_needed else "топ-%d" % n


# ── SQL-шаблоны корпуса (A2 / B1–B5); верхняя граница today+1 (A5.3) ─────────

def period_bounds(kind: str) -> tuple[str, str]:
    """Границы [от, до) в терминах today.d. Open-периоды — до today+1 (A5.3)."""
    d = "today.d"
    tw = "date_trunc('week', today.d)"
    tm = "date_trunc('month', today.d)"
    table = {
        "yesterday": (f"{d} - INTERVAL 1 day", d),
        "day_before_yesterday": (f"{d} - INTERVAL 2 day", f"{d} - INTERVAL 1 day"),
        "today": (d, f"{d} + INTERVAL 1 day"),
        "this_week": (tw, f"{d} + INTERVAL 1 day"),
        "last_week": (f"{tw} - INTERVAL 7 day", tw),
        "this_month": (tm, f"{d} + INTERVAL 1 day"),
        "last_month": (f"{tm} - INTERVAL 1 month", tm),
        "last_sunday": (f"{tw} - INTERVAL 1 day", tw),
        "buyers_12m": (f"{d} - INTERVAL 12 month", f"{d} + INTERVAL 1 day"),
    }
    if kind not in table:
        raise KeyError(kind)
    return table[kind]


def open_period_kinds() -> frozenset:
    """Периоды с обязательной верхней границей today+1 (A5.3)."""
    return frozenset({"today", "this_week", "this_month", "buyers_12m"})


def sql_has_today_plus_one(sql: str) -> bool:
    return bool(re.search(
        r"today\.d\s*\+\s*INTERVAL\s+1\s+day", sql, re.I
    ))


def corpus_sum_sql(lo: str, hi: str, *, only_shipped: bool = False) -> str:
    filt = f" AND {NUM_TOTAL} >= 0" if only_shipped else ""
    return (
        f"{TODAY_CTE}\n"
        f"SELECT coalesce(round(sum({NUM_TOTAL}), 2), 0)\n"
        f"FROM search_corpus, today\n"
        f"WHERE src_table = '{SRC_SALES}'\n"
        f"  AND doc_date >= {lo} AND doc_date < {hi}{filt};"
    )


def corpus_leader_sql(
    axis: str,
    measure: str,
    lo: str,
    hi: str,
    *,
    limit: int = 1,
    exclude_returns: bool = True,
) -> str:
    ref = REF_SKU if axis == "sku" else REF_CLIENT
    num = NUM_QTY if measure == "qty" else NUM_TOTAL
    ret = f" AND {NUM_TOTAL} >= 0" if exclude_returns else ""
    return (
        f"{TODAY_CTE}\n"
        f"SELECT {ref}, round(sum({num}), 2) AS s\n"
        f"FROM search_corpus, today\n"
        f"WHERE src_table = '{SRC_SALES}'\n"
        f"  AND doc_date >= {lo} AND doc_date < {hi}{ret}\n"
        f"GROUP BY 1 ORDER BY s DESC NULLS LAST LIMIT {limit};"
    )


def corpus_unsold_sql() -> str:
    lo, hi = period_bounds("this_month")
    return (
        f"{TODAY_CTE}\n"
        f"SELECT (\n"
        f"  SELECT count(*) FROM search_corpus\n"
        f"  WHERE src_table = 'catalog_номенклатура'\n"
        f"    AND NOT coalesce(flags['IsFolder'], false)\n"
        f"    AND NOT coalesce(flags['DeletionMark'], false)\n"
        f") - (\n"
        f"  SELECT count(DISTINCT {REF_SKU}) FROM search_corpus, today\n"
        f"  WHERE src_table = '{SRC_SALES}'\n"
        f"    AND doc_date >= {lo} AND doc_date < {hi}\n"
        f"    AND {NUM_TOTAL} >= 0\n"
        f");"
    )


def corpus_catalog_count_sql(src: str) -> str:
    return (
        f"SELECT count(*) FROM search_corpus\n"
        f"WHERE src_table = '{src}'\n"
        f"  AND NOT coalesce(flags['IsFolder'], false)\n"
        f"  AND NOT coalesce(flags['DeletionMark'], false);"
    )


def corpus_buyers_sql() -> str:
    lo, hi = period_bounds("buyers_12m")
    return (
        f"{TODAY_CTE}\n"
        f"SELECT count(DISTINCT {REF_CLIENT})\n"
        f"FROM search_corpus, today\n"
        f"WHERE src_table = '{SRC_SALES}'\n"
        f"  AND doc_date >= {lo} AND doc_date < {hi}\n"
        f"  AND {NUM_TOTAL} >= 0;"
    )


# ── описание вопроса ─────────────────────────────────────────────────────────

@dataclass
class Question:
    q: str
    section: str          # B1..B7
    klass: str            # С | Д
    kind: str             # period|period_shipped|leader|top|compare|sunday_zero|
                          # sunday_why|count|unsold|no_data|clarify|furniture
    period: Optional[str] = None
    axis: Optional[str] = None       # sku|client
    measure: Optional[str] = None    # money|qty|any
    top_n: int = 0
    compare_a: Optional[str] = None
    compare_b: Optional[str] = None
    note: str = ""


# Вопросы — docs/ACCEPTANCE_OKNA_LIVE.md §B (дословно формулировки из таблиц).
QUESTIONS: list[Question] = [
    # B1
    Question("вчера сколько продали", "B1", "С", "period", period="yesterday"),
    Question("позавчера сколько было продаж", "B1", "С", "period", period="day_before_yesterday"),
    Question("сегодня сколько уже наотгружали", "B1", "Д", "period", period="today"),
    Question("сколько сделали за эту неделю", "B1", "Д", "period", period="this_week"),
    Question("а на прошлой неделе сколько наторговали", "B1", "С", "period", period="last_week"),
    Question("сколько за этот месяц уже вышло", "B1", "Д", "period", period="this_month"),
    Question(
        "сколько было в прошлом месяце всего", "B1", "С", "period_shipped",
        period="last_month",
        note="чистыми + принять «отгружено» (§B1)",
    ),
    # B2
    Question(
        "что лучше всего продавалось на этой неделе", "B2", "Д", "leader",
        period="this_week", axis="sku", measure="any",
        note="штуки или деньги, если мера названа",
    ),
    Question(
        "какой клиент больше всех купил в этом месяце", "B2", "Д", "leader",
        period="this_month", axis="client", measure="money",
    ),
    Question(
        "дай топ-3 товара за вчера", "B2", "С", "top",
        period="yesterday", axis="sku", measure="qty", top_n=3,
        note="ничьи A5.7; деньги — если назвал",
    ),
    Question(
        "кто из клиентов молодец за прошлую неделю, три лучших", "B2", "С", "top",
        period="last_week", axis="client", measure="money", top_n=3,
    ),
    Question(
        "дай топ-3 по деньгам за месяц среди покупателей", "B2", "Д", "top",
        period="this_month", axis="client", measure="money", top_n=3,
    ),
    Question(
        "какая фурнитура сейчас лучше всего идёт", "B2", "Д", "furniture",
        note="переспросить ИЛИ назвать период и лидера",
    ),
    Question(
        "что у нас совсем не продаётся в этом месяце", "B2", "Д", "unsold",
    ),
    # B3
    Question(
        "эта неделя лучше прошлой или хуже", "B3", "Д", "compare",
        compare_a="this_week", compare_b="last_week",
        note="оба числа или разница+направление; оговорить неполный период",
    ),
    Question(
        "в этом месяце больше продали чем в прошлом?", "B3", "Д", "compare",
        compare_a="this_month", compare_b="last_month",
    ),
    Question(
        "сегодня лучше вчерашнего или нет", "B3", "Д", "compare",
        compare_a="today", compare_b="yesterday",
    ),
    Question(
        "мы просели или выросли", "B3", "Д", "compare",
        compare_a="this_month", compare_b="last_month",
        note="то же, что про месяц, словами",
    ),
    # B4
    Question(
        "а сколько наторговали в воскресенье", "B4", "С", "sunday_zero",
        period="last_sunday",
    ),
    Question(
        "почему в воскресенье продаж ноль, сбой какой-то?", "B4", "С", "sunday_why",
    ),
    # B5
    Question(
        "сколько у нас вообще клиентов сейчас", "B5", "С", "count",
        note="catalog_контрагенты без папок/удалённых",
    ),
    Question(
        "сколько позиций у нас в прайсе всего", "B5", "С", "count",
        note="номенклатура; законно и «с ценой»",
    ),
    Question(
        "сколько из клиентов реально покупают", "B5", "С", "count",
        note="DISTINCT за 12 мес, без возвратов",
    ),
    # B6
    Question("сколько у нас петель осталось на складе", "B6", "С", "no_data"),
    Question("ручки есть в наличии, сколько штук?", "B6", "С", "no_data"),
    Question("профиль весь распродали или что-то ещё лежит", "B6", "С", "no_data"),
    Question("сколько крепежа осталось на сегодня", "B6", "С", "no_data"),
    # B7
    Question("как у нас дела", "B7", "Д", "clarify"),
    Question("покажи по механизмам", "B7", "Д", "clarify"),
    Question("сравни с прошлым разом", "B7", "Д", "clarify"),
]


def build_etalon_sql(q: Question) -> list[str]:
    """Один или несколько SQL эталона (например net + shipped)."""
    if q.kind in ("period", "sunday_zero"):
        lo, hi = period_bounds(q.period or "")
        return [corpus_sum_sql(lo, hi)]
    if q.kind == "period_shipped":
        lo, hi = period_bounds(q.period or "")
        return [
            corpus_sum_sql(lo, hi, only_shipped=False),
            corpus_sum_sql(lo, hi, only_shipped=True),
        ]
    if q.kind == "leader":
        lo, hi = period_bounds(q.period or "")
        if q.measure == "any":
            return [
                corpus_leader_sql(q.axis or "sku", "qty", lo, hi, limit=1),
                corpus_leader_sql(q.axis or "sku", "money", lo, hi, limit=1),
            ]
        m = "qty" if q.measure == "qty" else "money"
        return [corpus_leader_sql(q.axis or "client", m, lo, hi, limit=1)]
    if q.kind == "top":
        lo, hi = period_bounds(q.period or "")
        m = "qty" if q.measure == "qty" else "money"
        # +2 к N, чтобы увидеть ничью (B2)
        sqls = [corpus_leader_sql(
            q.axis or "sku", m, lo, hi, limit=(q.top_n or 3) + 2)]
        # §B2 «штуки (деньги — если назвал)»: второй эталон по деньгам
        if q.measure == "qty" and "деньги" in (q.note or "").lower():
            sqls.append(corpus_leader_sql(
                q.axis or "sku", "money", lo, hi, limit=(q.top_n or 3) + 2))
        return sqls
    if q.kind == "compare":
        lo_a, hi_a = period_bounds(q.compare_a or "")
        lo_b, hi_b = period_bounds(q.compare_b or "")
        return [corpus_sum_sql(lo_a, hi_a), corpus_sum_sql(lo_b, hi_b)]
    if q.kind == "unsold":
        return [corpus_unsold_sql()]
    if q.kind == "count":
        if "клиентов сейчас" in q.q:
            return [corpus_catalog_count_sql("catalog_контрагенты")]
        if "прайсе" in q.q:
            return [corpus_catalog_count_sql("catalog_номенклатура")]
        if "покупают" in q.q:
            return [corpus_buyers_sql()]
    if q.kind == "furniture":
        lo, hi = period_bounds("this_week")
        return [corpus_leader_sql("sku", "qty", lo, hi, limit=1)]
    if q.kind in ("sunday_why", "no_data", "clarify"):
        return []
    return []


def period_sql_uses_today_plus_one(q: Question) -> bool:
    """Проверка A5.3 для открытых периодов (офлайн-замок)."""
    if q.period and q.period in open_period_kinds():
        for sql in build_etalon_sql(q):
            if not sql_has_today_plus_one(sql):
                return False
        return True
    if q.kind == "compare":
        for p in (q.compare_a, q.compare_b):
            if p in open_period_kinds():
                lo, hi = period_bounds(p)
                if "+ INTERVAL 1 day" not in hi:
                    return False
        return True
    if q.kind == "unsold":
        return sql_has_today_plus_one(corpus_unsold_sql())
    return True


# ── приём ответа ─────────────────────────────────────────────────────────────

@dataclass
class Etalon:
    raw: Any = None
    display: str = ""
    meta: dict = field(default_factory=dict)


@dataclass
class Verdict:
    ok: bool
    code: str          # ok|fail|broken|unchecked
    how: str


def _parse_scalar(cell: str) -> Optional[float]:
    cell = (cell or "").strip()
    if cell == "" or cell.upper() == "NULL":
        return 0.0
    try:
        return float(cell.replace(",", "."))
    except ValueError:
        return None


def _parse_leader_rows(tsv: str) -> list[tuple[str, float]]:
    rows: list[tuple[str, float]] = []
    for line in (tsv or "").splitlines():
        line = line.strip()
        if not line:
            continue
        # psql -tA: name|value или name\tvalue
        if "|" in line:
            parts = line.split("|", 1)
        else:
            parts = line.split("\t", 1)
        if len(parts) != 2:
            continue
        name, val = parts[0].strip(), _parse_scalar(parts[1])
        if name and val is not None:
            rows.append((name, val))
    return rows


def accept_answer(q: Question, etalon: Etalon, answer: str, *, kind: str = "") -> Verdict:
    """Правила приёма раздела B."""
    text = answer or ""
    low = text.lower()
    k = kind.lower()

    if q.kind == "no_data":
        # без чисел итогов; kind no_data / «остатки не веду»
        if k in ("no_data", "unavailable") or any(
            w in low for w in ("остатк", "не веду", "нет данных", "не хран", "не учет")
        ):
            # если назвали складское число без оговорки — провал
            if extract_numbers(text) and "отгруз" not in low and "продаж" not in low:
                # пивот на отгрузку с оговоркой допустим (§B6)
                if "оговор" in low or "не остат" in low or "по отгруз" in low:
                    return Verdict(True, "ok", "no_data + пивот с оговоркой")
                return Verdict(False, "fail", "остатки: число без no_data")
            return Verdict(True, "ok", "no_data / остатки не веду")
        if extract_numbers(text):
            return Verdict(False, "fail", "остатки: выдуманное число")
        return Verdict(False, "fail", "ждали no_data")

    if q.kind == "clarify":
        if k == "clarify" or any(
            w in low for w in ("уточн", "какой период", "какую мер", "что имеете", "укажите")
        ):
            return Verdict(True, "ok", "clarify")
        # допустимо: ответ с явно названным допущением (§B7)
        if any(w in low for w in ("если имели в виду", "за эту неделю", "допустим", "предполож")):
            return Verdict(True, "ok", "ответ с явным допущением")
        if extract_numbers(text):
            return Verdict(False, "fail", "число без уточнения")
        return Verdict(False, "fail", "ждали clarify")

    if q.kind == "sunday_why":
        if any(w in low for w in ("выходн", "не сбой", "не работает", "воскресень")) and not (
            "сбой" in low and "да" in low and "выходн" not in low
        ):
            # объяснение выходной, не сбой
            if "сбой" in low and any(x in low for x in ("не сбой", "не из-за сбой", "не полом")):
                return Verdict(True, "ok", "выходной, не сбой")
            if "выходн" in low or "не работа" in low:
                return Verdict(True, "ok", "выходной, не сбой")
        if "сбой" in low and "выходн" not in low:
            return Verdict(False, "fail", "списал на сбой")
        return Verdict(False, "fail", "нет объяснения про выходной")

    if q.kind == "furniture":
        if k == "clarify" or any(w in low for w in ("уточн", "за какой период", "недел", "месяц")):
            # переспросил ИЛИ назвал период+лидера
            if name_prefix_match(text, str((etalon.meta or {}).get("leader_name") or "")) or (
                k == "clarify" or "уточн" in low
            ):
                if k == "clarify" or "уточн" in low:
                    return Verdict(True, "ok", "переспросил период")
                if any(w in low for w in ("недел", "месяц", "сегодня", "период")):
                    return Verdict(True, "ok", "период назван + лидер")
        if any(w in low for w in ("недел", "месяц")) and etalon.meta.get("leader_name"):
            if name_prefix_match(text, etalon.meta["leader_name"]):
                return Verdict(True, "ok", "период + лидер")
        return Verdict(False, "fail", "фурнитура: ни clarify, ни период+лидер")

    if q.kind == "sunday_zero":
        val = etalon.raw if isinstance(etalon.raw, (int, float)) else 0.0
        if looks_like_day_substitution(text, etalon_zero=numbers_close(val, 0.0),
                                       friday_value=etalon.meta.get("friday_value")):
            return Verdict(False, "fail", "подмена дня (вс→пт) без оговорки")
        if number_in_answer(text, float(val)):
            return Verdict(True, "ok", "воскресенье=0 / честный ноль")
        if numbers_close(float(val), 0.0) and any(
            w in low for w in ("ноль", "нул", "не было", "0", "выходн")
        ):
            return Verdict(True, "ok", "честный ноль словами")
        return Verdict(False, "fail", "воскресенье: эталон не в ответе")

    if q.kind in ("period", "period_shipped", "unsold", "count"):
        if q.kind == "period_shipped":
            net = etalon.meta.get("net")
            shipped = etalon.meta.get("shipped")
            ok_net = net is not None and number_in_answer(text, float(net))
            ok_ship = (
                shipped is not None
                and number_in_answer(text, float(shipped))
                and any(w in low for w in (
                    "отгруж", "отгруз", "без возврат", "валовая",
                ))
            )
            if ok_net:
                return Verdict(True, "ok", "прошлое: чистыми")
            if ok_ship:
                return Verdict(True, "ok", "прошлое: отгружено (принято)")
            return Verdict(False, "fail", "нет ни чистыми, ни отгружено")
        val = etalon.raw
        if val is None:
            return Verdict(False, "unchecked", "эталон не посчитан")
        # честный ноль выходных (A4)
        if numbers_close(float(val), 0.0):
            if looks_like_day_substitution(
                text, etalon_zero=True,
                friday_value=etalon.meta.get("friday_value"),
            ):
                return Verdict(False, "fail", "подмена дня при нуле эталона")
        if number_in_answer(text, float(val)):
            return Verdict(True, "ok", "цифра эталона в ответе")
        return Verdict(False, "fail", "цифра эталона не найдена")

    if q.kind == "leader":
        name = etalon.meta.get("name") or ""
        val = etalon.meta.get("value")
        alts = etalon.meta.get("alts") or []
        candidates = [(name, val)] + list(alts)
        for nm, vv in candidates:
            if not nm or vv is None:
                continue
            if name_prefix_match(text, nm) and number_in_answer(text, float(vv)):
                how = "имя+число"
                if q.measure == "any":
                    how += " (мера any)"
                return Verdict(True, "ok", how)
        return Verdict(False, "fail", "лидер: имя/число не сошлись")

    if q.kind == "top":
        rows = etalon.meta.get("rows") or []
        ok, how = accept_top_n(text, rows, n=q.top_n or 3)
        if ok:
            return Verdict(True, "ok", how)
        # §B2: топ по деньгам, если бот назвал денежную меру
        alt = etalon.meta.get("rows_money") or []
        if alt and any(w in low for w in ("лей", "денег", "сумм", "выручк", "mdl")):
            ok2, how2 = accept_top_n(text, alt, n=q.top_n or 3)
            if ok2:
                return Verdict(True, "ok", "топ по деньгам (мера названа): " + how2)
        return Verdict(False, "fail", how)

    if q.kind == "compare":
        a = etalon.meta.get("a")
        b = etalon.meta.get("b")
        if a is None or b is None:
            return Verdict(False, "unchecked", "эталон сравнения пуст")
        diff = round(float(a) - float(b), 2)
        has_a = number_in_answer(text, float(a))
        has_b = number_in_answer(text, float(b))
        has_diff = number_in_answer(text, abs(diff))
        direction_up = diff > 0
        dir_ok = False
        if direction_up:
            dir_ok = any(w in low for w in (
                "лучше", "больше", "вырос", "выросл", "выше", "да", "больше продали",
            ))
        else:
            dir_ok = any(w in low for w in (
                "хуже", "меньше", "просел", "ниже", "упал", "нет",
            ))
        # неполный период
        open_a = (q.compare_a or "") in open_period_kinds()
        if open_a and not any(w in low for w in (
            "ещё идёт", "неполн", "текущ", "пока", "на сегодня", "уже",
        )):
            # не стоп-критерий жёсткий, но желательно; не валим, если числа верны
            pass
        if (has_a and has_b) or (has_diff and dir_ok):
            if not dir_ok and has_a and has_b:
                # оба числа есть — направление можно вывести; требуем явное
                if direction_up and ("лучше" in low or "больше" in low or "да" in low or "вырос" in low):
                    dir_ok = True
                elif (not direction_up) and ("хуже" in low or "меньше" in low or "просел" in low):
                    dir_ok = True
            if (has_a and has_b and dir_ok) or (has_diff and dir_ok):
                return Verdict(True, "ok", "сравнение: числа/разница+направление")
            if has_a and has_b:
                return Verdict(False, "fail", "числа есть, направление неверное/нет")
        return Verdict(False, "fail", "сравнение не сошлось")

    return Verdict(False, "unchecked", "неизвестный kind=%s" % q.kind)


# ── I/O: psql + /ask ─────────────────────────────────────────────────────────

def run_sql(dsn: str, sql: str, timeout: int = 120) -> str:
    p = subprocess.run(
        ["psql", dsn, "-tA", "-v", "ON_ERROR_STOP=1", "-c", sql],
        capture_output=True, text=True, timeout=timeout,
    )
    if p.returncode != 0:
        raise RuntimeError("psql: %s" % (p.stderr or p.stdout)[:400])
    return (p.stdout or "").strip()


def ask_bot(url: str, token: str, question: str, timeout: int = 600) -> dict:
    body = json.dumps({"question": question, "user": "okna-live"}, ensure_ascii=False).encode()
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + token,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except Exception as e:  # noqa: BLE001
        return {"text": "", "kind": "unavailable", "diag": {"error": str(e)[:200]}}


def compute_etalon(q: Question, dsn: str) -> Etalon:
    sqls = build_etalon_sql(q)
    et = Etalon(meta={"sqls": sqls})

    if q.kind in ("sunday_why", "no_data", "clarify"):
        et.display = q.kind
        return et

    if q.kind == "period_shipped":
        net = _parse_scalar(run_sql(dsn, sqls[0]))
        shipped = _parse_scalar(run_sql(dsn, sqls[1]))
        et.raw = net
        et.meta["net"] = net
        et.meta["shipped"] = shipped
        et.display = "чистыми=%s отгружено=%s" % (net, shipped)
        return et

    if q.kind in ("period", "sunday_zero", "unsold", "count"):
        val = _parse_scalar(run_sql(dsn, sqls[0]))
        et.raw = val
        et.display = str(val)
        return et

    if q.kind == "leader":
        if q.measure == "any":
            rows_q = _parse_leader_rows(run_sql(dsn, sqls[0]))
            rows_m = _parse_leader_rows(run_sql(dsn, sqls[1]))
            primary = rows_q[0] if rows_q else ("", None)
            alt = rows_m[0] if rows_m else ("", None)
            et.meta["name"], et.meta["value"] = primary[0], primary[1]
            if alt[0]:
                et.meta["alts"] = [alt]
            et.display = "%s = %s (qty); alt money %s = %s" % (
                name_core(primary[0]), primary[1], name_core(alt[0]), alt[1])
            return et
        rows = _parse_leader_rows(run_sql(dsn, sqls[0]))
        if rows:
            et.meta["name"], et.meta["value"] = rows[0]
            et.display = "%s = %s" % (name_core(rows[0][0]), rows[0][1])
        else:
            et.display = "пусто"
        return et

    if q.kind == "top":
        rows = _parse_leader_rows(run_sql(dsn, sqls[0]))
        et.meta["rows"] = rows
        if len(sqls) > 1:
            et.meta["rows_money"] = _parse_leader_rows(run_sql(dsn, sqls[1]))
        et.display = " | ".join(
            "%s=%s" % (name_core(n)[:40], v) for n, v in rows[: (q.top_n or 3) + 2]
        )
        return et

    if q.kind == "compare":
        a = _parse_scalar(run_sql(dsn, sqls[0]))
        b = _parse_scalar(run_sql(dsn, sqls[1]))
        et.meta["a"], et.meta["b"] = a, b
        et.raw = (a, b)
        et.display = "a=%s b=%s Δ=%s" % (
            a, b, None if a is None or b is None else round(a - b, 2))
        return et

    if q.kind == "furniture":
        rows = _parse_leader_rows(run_sql(dsn, sqls[0]))
        if rows:
            et.meta["leader_name"], et.meta["leader_value"] = rows[0]
            et.meta["name"], et.meta["value"] = rows[0]
            et.display = "неделя: %s = %s" % (name_core(rows[0][0]), rows[0][1])
        else:
            et.display = "лидер недели пуст"
        return et

    et.display = "—"
    return et


def answer_text(out: dict) -> str:
    if not isinstance(out, dict):
        return ""
    return (out.get("text") or out.get("answer") or "")[:8000]


# ── прогон ───────────────────────────────────────────────────────────────────

@dataclass
class Row:
    question: str
    klass: str
    section: str
    etalon: str
    answer: str
    verdict: str
    how: str


def run_all(
    dsn: str,
    ask_url: str,
    ask_token: str,
    *,
    questions: Optional[list[Question]] = None,
    ask_fn: Optional[Callable] = None,
    sql_fn: Optional[Callable] = None,
) -> tuple[list[Row], dict]:
    """Приёмочный прогон. ask_fn/sql_fn — только для офлайн-подмен в замке."""
    qs = questions if questions is not None else QUESTIONS
    rows: list[Row] = []
    ok_c = ok_d = fail_c = fail_d = broken = 0

    for q in qs:
        try:
            if sql_fn:
                # подмена: sql_fn(q) → Etalon
                et = sql_fn(q)
            else:
                et = compute_etalon(q, dsn)
        except Exception as e:  # noqa: BLE001
            rows.append(Row(q.q, q.klass, q.section, "ERR:%s" % e, "", "broken", "эталон"))
            broken += 1
            continue

        try:
            if ask_fn:
                out = ask_fn(q)
            else:
                out = ask_bot(ask_url, ask_token, q.q)
        except Exception as e:  # noqa: BLE001
            rows.append(Row(
                q.q, q.klass, q.section, et.display, "", "broken", "ask:%s" % e))
            broken += 1
            continue

        text = answer_text(out)
        kind = (out or {}).get("kind") or ""
        if (out or {}).get("diag", {}).get("error") and not text:
            v = Verdict(False, "broken", "ask error")
        else:
            v = accept_answer(q, et, text, kind=kind)

        rows.append(Row(q.q, q.klass, q.section, et.display, text[:200], v.code, v.how))
        if v.code == "ok":
            if q.klass == "С":
                ok_c += 1
            else:
                ok_d += 1
        elif v.code == "broken":
            broken += 1
        else:
            if q.klass == "С":
                fail_c += 1
            else:
                fail_d += 1

    stats = {
        "ok_C": ok_c,
        "ok_D": ok_d,
        "fail_C": fail_c,
        "fail_D": fail_d,
        "broken": broken,
        "total": len(qs),
    }
    return rows, stats


def print_report(rows: list[Row], stats: dict) -> None:
    print("вопрос\tкласс\tэталон\tответ\tвердикт\tчем сверялось")
    for r in rows:
        print("%s\t%s\t%s\t%s\t%s\t%s" % (
            r.question.replace("\t", " "),
            r.klass,
            (r.etalon or "").replace("\t", " ")[:80],
            (r.answer or "").replace("\t", " ").replace("\n", " ")[:80],
            r.verdict,
            r.how,
        ))
    print()
    print("верных С: %d | верных Д: %d | провалов С: %d | провалов Д: %d | broken: %d | всего: %d"
          % (stats["ok_C"], stats["ok_D"], stats["fail_C"], stats["fail_D"],
             stats["broken"], stats["total"]))


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    dsn = os.environ.get("OKNA_DSN", "").strip()
    url = os.environ.get("ASK_URL", "").strip()
    token = os.environ.get("ASK_TOKEN", "").strip()
    if not dsn or not url or not token:
        print(
            "Нужны OKNA_DSN, ASK_URL, ASK_TOKEN. Живой прогон — за оркестратором.",
            file=sys.stderr,
        )
        return 2
    rows, stats = run_all(dsn, url, token)
    print_report(rows, stats)
    print("спека: %s | today: %s" % (SPEC, today_sql_fragment()), file=sys.stderr)
    return 0 if (stats["fail_C"] + stats["fail_D"] + stats["broken"]) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
