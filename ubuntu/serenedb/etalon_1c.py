#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Эталоны из живой 1С (OData-шлюз) и генератор приёмочного набора.

Постоянный инструмент потока И (задача И0, docs/PLAN_TO_TARGET.md).
Считает эталон независимо: 1С по OData и корпус одним SQL на все срезы (UNION ALL скалярных подзапросов).
Расхождение помечается статусом и попадает в очередь независимого прочтения.
Адрес шлюза и DSN — из окружения или аргументов CLI.

Запуск:
  python3 etalon_1c.py verify --slices slices.json [--out report.json]
  python3 etalon_1c.py generate --out client-gold.tsv
      [--metadata-xml meta.xml | --from-gateway]
      [--journal-tsv questions.tsv | --from-journal]
      [--from-search-tables]
  python3 etalon_1c.py classify

Факт 1С в срезе: odata.entity (HTTP-шлюз) и/или fact.sql (витрина packet-режима).
Оба пути пишут odata_value; эталон в gold — источник 1c.

Env:
  ETL_ODATA_BASE / ETALON_ODATA_BASE — URL шлюза
  ODG_GATEWAY_TOKEN — Bearer шлюза
  SERENEDB_DSN / ETALON_DSN — DSN корпуса
  ETALON_HTTP_TIMEOUT — таймаут GET (умолч. 120)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Iterable, Optional

STATUS_PENDING = "pending"
STATUS_MATCH = "match"
STATUS_MISMATCH = "mismatch"
STATUS_FRESHNESS_LAG = "freshness_lag"
STATUS_DECLARED_WRONG = "declared_wrong"
STATUS_NEEDS_READ = "needs_independent_read"
STATUS_ERROR = "error"

ETALON_SOURCE_1C = "1c"
ETALON_SOURCE_CORPUS = "corpus"
ETALON_SOURCE_DECLARED = "declared"
ETALON_SOURCE_PENDING = "pending"
ETALON_SOURCE_JOURNAL = "ask_journal"
ETALON_SOURCE_METADATA = "metadata"
ETALON_SOURCE_SEARCH_TABLES = "search_tables"

# Словарь относительных окон — тот же файл, что грузит ask / такт (данные, не код).
_PERIOD_FORMS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "period_relative_forms.json",
)
_PERIOD_FORMS_CACHE = None  # type: Optional[dict]

# Литералы привязки к контуру (собраны по частям, чтобы сам список не
# выглядел как зашитый DSN в исходнике).
_BASE_LITERALS_FOR_LOCK = tuple("".join(parts) for parts in (
    ("ut", "_", "test"),
    ("klient", "-", "1"),
    ("klient", "_", "1"),
    ("dbname=", "ok", "na"),
    ("/", "ok", "na"),
    ("@", "ok", "na"),
    ("1c-serene-ask@", "ok", "na"),
    ("1c-odata-gateway@", "ut", "_", "test"),
    ("1c-odata-gateway@", "ok", "na"),
))

CLIENT_GOLD_HEADER = ("question", "etalon", "etalon_source", "verify_status")


def parse_odata_count(body: Any) -> int:
    """Разбор ответа /$count: plain int или JSON-обёртка."""
    if body is None:
        raise ValueError("пустой ответ $count")
    if isinstance(body, (int, float)) and not isinstance(body, bool):
        return int(body)
    if isinstance(body, bytes):
        body = body.decode("utf-8", "replace")
    text = str(body).strip()
    if not text:
        raise ValueError("пустой ответ $count")
    if text[0] in "{[":
        doc = json.loads(text)
        if isinstance(doc, dict):
            for key in ("value", "odata.count", "@odata.count", "count"):
                if key in doc:
                    return int(doc[key])
        if isinstance(doc, (int, float)):
            return int(doc)
        raise ValueError("неизвестный JSON $count: %r" % (text[:80],))
    if text[0] in "\"'":
        text = text.strip("\"'")
    return int(text)


def parse_odata_value_rows(doc: Any) -> list:
    """Достать value[] из JSON-документа коллекции OData."""
    if isinstance(doc, bytes):
        doc = json.loads(doc.decode("utf-8", "replace"))
    elif isinstance(doc, str):
        doc = json.loads(doc)
    if not isinstance(doc, dict):
        raise ValueError("OData JSON не является объектом")
    rows = doc.get("value")
    if rows is None:
        raise ValueError("нет поля value в ответе OData")
    if not isinstance(rows, list):
        raise ValueError("value не список")
    return rows


def parse_metadata_entity_sets(xml: str) -> list[str]:
    """Имена EntitySet из снимка $metadata."""
    if not xml:
        return []
    names = re.findall(r'<EntitySet\s+Name="([^"]+)"', xml)
    seen = set()
    out = []
    for n in names:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def to_decimal(v: Any) -> Decimal:
    if v is None or v == "":
        raise ValueError("пустое число")
    if isinstance(v, Decimal):
        return v
    if isinstance(v, bool):
        raise ValueError("bool не число эталона")
    if isinstance(v, int):
        return Decimal(v)
    if isinstance(v, float):
        return Decimal(str(v))
    s = str(v).strip().replace(" ", "").replace("\u00a0", "").replace(",", ".")
    try:
        return Decimal(s)
    except InvalidOperation as e:
        raise ValueError("не число: %r" % (v,)) from e


def numbers_equal(
    a: Any,
    b: Any,
    rel_tol: Decimal = Decimal("1e-9"),
    abs_tol: Decimal = Decimal("0.005"),
) -> bool:
    """Сравнение чисел эталона: допуск 0.005 или относительный 1e-9."""
    try:
        da, db = to_decimal(a), to_decimal(b)
    except ValueError:
        return False
    if da == db:
        return True
    diff = abs(da - db)
    if diff <= abs_tol:
        return True
    scale = max(abs(da), abs(db), Decimal(1))
    return diff / scale <= rel_tol


def period_relative_forms(path: Optional[str] = None) -> dict:
    """form_id → фразы из period_relative_forms.json (офлайн-источник как у ask)."""
    global _PERIOD_FORMS_CACHE
    if path is None and _PERIOD_FORMS_CACHE is not None:
        return _PERIOD_FORMS_CACHE
    src_path = path or _PERIOD_FORMS_PATH
    got = {}
    try:
        with open(src_path, encoding="utf-8") as f:
            parsed = json.load(f)
        if isinstance(parsed, dict):
            got = {
                str(k): [str(x) for x in (v or [])]
                for k, v in parsed.items()
            }
    except (OSError, ValueError, TypeError):
        got = {}
    if path is None:
        _PERIOD_FORMS_CACHE = got
    return got


def period_form_from_question(
    question: str,
    forms: Optional[dict] = None,
) -> Optional[str]:
    """form_id по фразам словаря. Иначе None — без языковой догадки в коде."""
    q = " ".join(str(question or "").lower().split())
    if not q:
        return None
    mapping = forms if forms is not None else period_relative_forms()
    for form_id, phrases in (mapping or {}).items():
        for ph in phrases or []:
            p = " ".join(str(ph).lower().split())
            if p and p in q:
                return str(form_id)
    return None


def is_relative_period(
    question: str = "",
    period_hint: Optional[str] = None,
    forms: Optional[dict] = None,
) -> bool:
    """Относительный срез — кандидат на freshness_lag.

    Фразы берутся из period_relative_forms.json (как serene_ask) либо из
    period_hint. Пока формы вроде «вчера» нет в словаре — только через hint.
    """
    hint = (period_hint or "").strip().lower()
    if hint in ("relative", "rel", "lag", "fresh"):
        return True
    if hint in ("stable", "closed", "absolute", "fixed"):
        return False
    return period_form_from_question(question, forms) is not None


@dataclass
class Classification:
    status: str
    reason: str
    needs_independent_read: bool = False
    odata_value: Any = None
    corpus_value: Any = None
    declared_value: Any = None


def classify_discrepancy(
    odata_value: Any,
    corpus_value: Any = None,
    declared_value: Any = None,
    *,
    question: str = "",
    period_hint: Optional[str] = None,
    just_after_tick: bool = False,
) -> Classification:
    """Классификация 1С ↔ корпус ↔ заявленный эталон.

    match — числа совпали;
    declared_wrong — заявленное значение расходится с фактом 1С;
    freshness_lag — относительный период и 1С≠корпус вне окна сразу-после-такта;
    mismatch — расхождение по существу (очередь независимого прочтения).
    """
    relative = is_relative_period(question, period_hint)

    if odata_value is None and corpus_value is None and declared_value is None:
        return Classification(STATUS_PENDING, "нет ни одного значения", False)

    if declared_value is not None and odata_value is not None:
        if not numbers_equal(declared_value, odata_value):
            return Classification(
                STATUS_DECLARED_WRONG,
                "заявленный эталон расходится с фактом 1С",
                needs_independent_read=True,
                odata_value=odata_value,
                corpus_value=corpus_value,
                declared_value=declared_value,
            )

    if odata_value is not None and corpus_value is not None:
        if numbers_equal(odata_value, corpus_value):
            return Classification(
                STATUS_MATCH,
                "1С и корпус совпали",
                False,
                odata_value,
                corpus_value,
                declared_value,
            )
        if relative and not just_after_tick:
            return Classification(
                STATUS_FRESHNESS_LAG,
                "относительный период: расхождение похоже на лаг такта корпуса",
                False,
                odata_value,
                corpus_value,
                declared_value,
            )
        return Classification(
            STATUS_MISMATCH,
            "расхождение 1С↔корпус по существу",
            True,
            odata_value,
            corpus_value,
            declared_value,
        )

    if odata_value is not None and corpus_value is None:
        return Classification(
            STATUS_PENDING,
            "есть только факт 1С; корпус не считался",
            False,
            odata_value,
            None,
            declared_value,
        )
    if corpus_value is not None and odata_value is None:
        return Classification(
            STATUS_PENDING,
            "есть только корпус; 1С не считалась",
            False,
            None,
            corpus_value,
            declared_value,
        )
    return Classification(STATUS_PENDING, "нечего сравнивать", False)


def humanize_entity_set(name: str) -> str:
    n = (name or "").strip()
    for prefix in (
        "Catalog_",
        "Document_",
        "InformationRegister_",
        "AccumulationRegister_",
        "AccountingRegister_",
        "CalculationRegister_",
        "ChartOfCharacteristicTypes_",
        "ChartOfAccounts_",
        "ChartOfCalculationTypes_",
        "ExchangePlan_",
        "BusinessProcess_",
        "Task_",
    ):
        if n.startswith(prefix):
            return n[len(prefix):]
    return n


def question_from_entity_set(entity_set: str) -> str:
    kind = entity_set.split("_", 1)[0] if "_" in entity_set else ""
    title = humanize_entity_set(entity_set)
    if kind == "Catalog":
        return "Сколько позиций в справочнике «%s» (без групп)?" % title
    if kind == "Document":
        return "Сколько документов «%s»?" % title
    if kind in ("AccumulationRegister", "InformationRegister", "AccountingRegister"):
        return "Сколько движений в «%s»?" % title
    return "Сколько записей в «%s»?" % title


def generate_questions_from_metadata(
    entity_sets: Iterable[str],
    *,
    kinds: Optional[Iterable[str]] = None,
    limit: int = 0,
) -> list[dict]:
    allow = set(kinds) if kinds else {"Catalog", "Document"}
    rows = []
    for es in entity_sets:
        prefix = es.split("_", 1)[0] if "_" in es else es
        if allow and prefix not in allow:
            continue
        rows.append({
            "question": question_from_entity_set(es),
            "etalon": "",
            "etalon_source": ETALON_SOURCE_METADATA,
            "verify_status": STATUS_PENDING,
            "entity_set": es,
        })
        if limit and len(rows) >= limit:
            break
    return rows


def question_from_search_table(src_table: str, label: str = "") -> str:
    """Вопрос покрытия по строке search_tables (корпус), без догадки по OData."""
    title = (label or "").strip() or humanize_entity_set(
        "_".join(p.capitalize() for p in (src_table or "").split("_"))
    )
    low = (src_table or "").lower()
    if low.startswith("catalog_"):
        return "Сколько позиций в справочнике «%s» (без групп)?" % title
    if low.startswith("document_"):
        return "Сколько документов «%s»?" % title
    if low.startswith("accumulationregister_"):
        return "Сколько движений в регистре «%s»?" % title
    if low.startswith("informationregister_"):
        return "Сколько записей в регистре сведений «%s»?" % title
    return "Сколько записей в «%s»?" % title


def generate_questions_from_search_tables(
    rows: Iterable[dict],
    *,
    prefixes: Optional[Iterable[str]] = None,
    limit: int = 0,
) -> list[dict]:
    """Покрытие сущностей из search_tables (src_table, label)."""
    allow = {p.lower().rstrip("_") for p in prefixes} if prefixes else {
        "catalog", "document", "accumulationregister",
    }
    out = []
    for row in rows:
        src = (row.get("src_table") or row.get("table") or "").strip()
        if not src:
            continue
        prefix = src.split("_", 1)[0].lower()
        if allow and prefix not in allow:
            continue
        out.append({
            "question": question_from_search_table(src, row.get("label") or ""),
            "etalon": "",
            "etalon_source": ETALON_SOURCE_SEARCH_TABLES,
            "verify_status": STATUS_PENDING,
            "src_table": src,
        })
        if limit and len(out) >= limit:
            break
    return out


def generate_questions_from_journal(
    questions: Iterable[str],
    *,
    limit: int = 0,
) -> list[dict]:
    rows = []
    seen = set()
    for q in questions:
        q = (q or "").strip()
        if not q:
            continue
        key = re.sub(r"\s+", " ", q.lower().replace("ё", "е"))
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            "question": q,
            "etalon": "",
            "etalon_source": ETALON_SOURCE_JOURNAL,
            "verify_status": STATUS_PENDING,
        })
        if limit and len(rows) >= limit:
            break
    return rows


def merge_gold_rows(*groups: list[dict]) -> list[dict]:
    out = []
    seen = set()
    for group in groups:
        for row in group:
            q = (row.get("question") or "").strip()
            if not q:
                continue
            key = re.sub(r"\s+", " ", q.lower().replace("ё", "е"))
            if key in seen:
                continue
            seen.add(key)
            out.append(dict(row))
    return out


def format_client_gold_tsv(rows: Iterable[dict]) -> str:
    lines = ["\t".join(CLIENT_GOLD_HEADER)]
    for row in rows:
        cells = [
            str(row.get("question") or "").replace("\t", " ").replace("\n", " "),
            str(row.get("etalon") if row.get("etalon") is not None else ""),
            str(row.get("etalon_source") or ETALON_SOURCE_PENDING),
            str(row.get("verify_status") or STATUS_PENDING),
        ]
        lines.append("\t".join(cells))
    return "\n".join(lines) + "\n"


def parse_client_gold_tsv(text: str) -> list[dict]:
    rows = []
    for i, line in enumerate(text.splitlines()):
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if i == 0 and parts and parts[0] == "question":
            continue
        while len(parts) < 4:
            parts.append("")
        rows.append({
            "question": parts[0],
            "etalon": parts[1],
            "etalon_source": parts[2],
            "verify_status": parts[3],
        })
    return rows


def source_has_hardcoded_base(source: str) -> list[str]:
    """Литералы контуров в исходнике (для замка отсутствия привязки)."""
    hits = []
    for lit in _BASE_LITERALS_FOR_LOCK:
        if lit in source:
            hits.append(lit)
    for m in re.finditer(r"dbname=([A-Za-z0-9_-]+)", source):
        name = m.group(1).lower()
        if name in ("postgres", "template1", "dbname", "name"):
            continue
        _named = {
            "".join(("ut", "_", "test")),
            "".join(("ok", "na")),
            "".join(("klient", "-", "1")),
            "".join(("klient", "_", "1")),
            "buh",
            "bp",
        }
        if name in _named:
            frag = "dbname=" + m.group(1)
            if frag not in hits:
                hits.append(frag)
    return hits


def sum_field_from_rows(rows: list, field_name: str) -> Decimal:
    total = Decimal(0)
    for row in rows:
        if not isinstance(row, dict):
            continue
        if field_name not in row or row[field_name] in (None, ""):
            continue
        total += to_decimal(row[field_name])
    return total


def filter_rows_local(rows: list, local_filter: Optional[dict]) -> list:
    if not local_filter:
        return rows
    field_name = local_filter.get("field")
    if not field_name:
        return rows
    if "equals" not in local_filter:
        return rows
    want = local_filter["equals"]
    out = []
    for row in rows:
        if _cell_equals(row.get(field_name), want):
            out.append(row)
    return out


def _cell_equals(got: Any, want: Any) -> bool:
    if want is True or want is False:
        if isinstance(got, bool):
            return got is want
        s = str(got).strip().lower()
        return s in ("true", "1", "t", "yes") if want else s in (
            "false", "0", "f", "no", "",
        )
    if want is None:
        return got is None or got == ""
    return str(got).strip() == str(want).strip()


@dataclass
class SliceSpec:
    question: str
    odata_entity: str = ""
    odata_op: str = "count"
    odata_filter: str = ""
    odata_field: str = ""
    odata_select: str = ""
    local_filter: Optional[dict] = None
    corpus_sql: str = ""
    # Факт 1С из витрины (packet-режим): один SQL, без HTTP-шлюза.
    # В отчёте пишется в odata_value / etalon_source=1c — это выгрузка 1С, не ответ бота.
    fact_sql: str = ""
    period: str = "stable"
    declared: Any = None
    id: str = ""
    extra: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict) -> "SliceSpec":
        odata = d.get("odata") or {}
        corpus = d.get("corpus") or {}
        fact = d.get("fact") or {}
        return cls(
            question=d.get("question") or "",
            odata_entity=odata.get("entity") or d.get("odata_entity") or "",
            odata_op=(odata.get("op") or d.get("odata_op") or "count").lower(),
            odata_filter=odata.get("filter") or d.get("odata_filter") or "",
            odata_field=odata.get("field") or d.get("odata_field") or "",
            odata_select=odata.get("select") or d.get("odata_select") or "",
            local_filter=odata.get("local_filter") or d.get("local_filter"),
            corpus_sql=corpus.get("sql") or d.get("corpus_sql") or "",
            fact_sql=(
                fact.get("sql") or d.get("fact_sql") or d.get("vitrine_sql") or ""
            ),
            period=(d.get("period") or "stable").lower(),
            declared=d.get("declared") if "declared" in d else d.get("etalon"),
            id=str(d.get("id") or ""),
            extra={
                k: v for k, v in d.items()
                if k not in (
                    "question", "odata", "corpus", "fact", "period", "declared",
                    "etalon", "id", "odata_entity", "odata_op", "odata_filter",
                    "odata_field", "odata_select", "local_filter", "corpus_sql",
                    "fact_sql", "vitrine_sql",
                )
            },
        )


@dataclass
class SliceResult:
    slice_id: str
    question: str
    odata_value: Any = None
    corpus_value: Any = None
    declared_value: Any = None
    classification: Optional[Classification] = None
    error: str = ""

    def to_dict(self) -> dict:
        d = {
            "id": self.slice_id,
            "question": self.question,
            "odata_value": _jsonable(self.odata_value),
            "corpus_value": _jsonable(self.corpus_value),
            "declared_value": _jsonable(self.declared_value),
            "error": self.error,
        }
        if self.classification:
            d["status"] = self.classification.status
            d["reason"] = self.classification.reason
            d["needs_independent_read"] = self.classification.needs_independent_read
        else:
            d["status"] = STATUS_ERROR if self.error else STATUS_PENDING
            d["reason"] = self.error or ""
            d["needs_independent_read"] = False
        return d


def _jsonable(v: Any) -> Any:
    if isinstance(v, Decimal):
        return str(v)
    return v


def _auth_request(url: str, token: str) -> urllib.request.Request:
    req = urllib.request.Request(url)
    if token:
        req.add_header("Authorization", "Bearer " + token)
    return req


@dataclass
class Config:
    odata_base: str
    dsn: str
    token: str = ""
    timeout: float = 120.0

    @classmethod
    def from_env(cls, args: Optional[argparse.Namespace] = None) -> "Config":
        odata = ""
        dsn = ""
        token = ""
        timeout = 120.0
        if args is not None:
            odata = (getattr(args, "odata_base", None) or "").strip()
            dsn = (getattr(args, "dsn", None) or "").strip()
            token = (getattr(args, "token", None) or "").strip()
            if getattr(args, "timeout", None):
                timeout = float(args.timeout)
        if not odata:
            odata = (
                os.environ.get("ETALON_ODATA_BASE")
                or os.environ.get("ETL_ODATA_BASE")
                or ""
            ).strip().rstrip("/")
        if not dsn:
            dsn = (
                os.environ.get("ETALON_DSN")
                or os.environ.get("SERENEDB_DSN")
                or ""
            ).strip()
        if not token:
            token = os.environ.get("ODG_GATEWAY_TOKEN", "").strip()
        if "ETALON_HTTP_TIMEOUT" in os.environ:
            timeout = float(os.environ["ETALON_HTTP_TIMEOUT"])
        return cls(odata_base=odata, dsn=dsn, token=token, timeout=timeout)

    def require_odata(self) -> None:
        if not self.odata_base:
            raise SystemExit(
                "нужен URL шлюза: --odata-base или ETL_ODATA_BASE / ETALON_ODATA_BASE"
            )
        if not (
            self.odata_base.startswith("http://")
            or self.odata_base.startswith("https://")
        ):
            raise SystemExit(
                "эталон 1С через HTTP-шлюз OData; передан не URL: %r"
                % (self.odata_base,)
            )

    def require_dsn(self) -> None:
        if not self.dsn:
            raise SystemExit(
                "нужен DSN корпуса: --dsn или SERENEDB_DSN / ETALON_DSN"
            )


class ODataClient:
    """GET-клиент шлюза. Подмена get_bytes — для офлайн-замка."""

    def __init__(
        self,
        base: str,
        token: str = "",
        timeout: float = 120.0,
        get_bytes: Optional[Callable[[str], bytes]] = None,
    ):
        self.base = base.rstrip("/")
        self.token = token
        self.timeout = timeout
        self._get_bytes = get_bytes

    def get_bytes(self, path_and_query: str) -> bytes:
        if self._get_bytes is not None:
            return self._get_bytes(path_and_query)
        url = self.base + (
            path_and_query if path_and_query.startswith("/") else "/" + path_and_query
        )
        req = _auth_request(url, self.token)
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return resp.read()

    def count(self, entity: str, odata_filter: str = "") -> int:
        q = {}
        if odata_filter:
            q["$filter"] = odata_filter
        path = "/%s/$count" % urllib.parse.quote(entity)
        if q:
            path += "?" + urllib.parse.urlencode(q)
        return parse_odata_count(self.get_bytes(path))

    def fetch_pages(
        self,
        entity: str,
        *,
        select: str = "",
        odata_filter: str = "",
        page_size: int = 1000,
        max_rows: int = 500_000,
    ) -> list:
        rows: list = []
        skip = 0
        while skip < max_rows:
            params = {
                "$format": "json",
                "$top": str(page_size),
                "$skip": str(skip),
            }
            if select:
                params["$select"] = select
            if odata_filter:
                params["$filter"] = odata_filter
            path = "/%s?%s" % (
                urllib.parse.quote(entity),
                urllib.parse.urlencode(params),
            )
            doc = json.loads(self.get_bytes(path).decode("utf-8", "replace"))
            page = parse_odata_value_rows(doc)
            if not page:
                break
            rows.extend(page)
            if len(page) < page_size:
                break
            skip += page_size
        return rows

    def metadata_xml(self) -> str:
        return self.get_bytes("/$metadata").decode("utf-8", "replace")

    def compute(self, spec: SliceSpec) -> Any:
        if not spec.odata_entity:
            raise ValueError("в срезе нет odata.entity")
        op = spec.odata_op or "count"
        if op == "count":
            if spec.local_filter:
                select = spec.odata_select or (spec.local_filter.get("field") or "")
                rows = self.fetch_pages(
                    spec.odata_entity,
                    select=select,
                    odata_filter=spec.odata_filter,
                )
                rows = filter_rows_local(rows, spec.local_filter)
                return len(rows)
            try:
                return self.count(spec.odata_entity, spec.odata_filter)
            except (urllib.error.HTTPError, urllib.error.URLError, ValueError):
                rows = self.fetch_pages(
                    spec.odata_entity,
                    select=spec.odata_select or "Ref_Key,IsFolder",
                    odata_filter="",
                )
                if spec.odata_filter and "IsFolder" in spec.odata_filter:
                    eq_true = re.search(
                        r"IsFolder\s+eq\s+true", spec.odata_filter, re.I
                    )
                    eq_false = re.search(
                        r"IsFolder\s+eq\s+false", spec.odata_filter, re.I
                    )
                    if eq_true:
                        rows = filter_rows_local(
                            rows, {"field": "IsFolder", "equals": True}
                        )
                    elif eq_false:
                        rows = filter_rows_local(
                            rows, {"field": "IsFolder", "equals": False}
                        )
                return len(rows)
        if op == "sum":
            if not spec.odata_field:
                raise ValueError("для op=sum нужно odata.field")
            select = spec.odata_select or spec.odata_field
            rows = self.fetch_pages(
                spec.odata_entity,
                select=select,
                odata_filter=spec.odata_filter,
            )
            rows = filter_rows_local(rows, spec.local_filter)
            return sum_field_from_rows(rows, spec.odata_field)
        raise ValueError("неизвестный odata.op: %r" % (op,))


def build_corpus_batch_sql(sqls: list[str]) -> str:
    """Один SELECT: N скалярных подзапросов через UNION ALL.

    Доки SereneDB: Scalar Subquery; UNION ALL (bag semantics).
    Каждый срез — CAST((<sql среза>) AS VARCHAR), индекс slice_i.
    """
    if not sqls:
        raise ValueError("build_corpus_batch_sql: пустой список sql")
    parts = []
    for i, raw in enumerate(sqls):
        inner = (raw or "").strip().rstrip(";")
        if not inner:
            raise ValueError("build_corpus_batch_sql: пустой sql у среза %d" % i)
        parts.append(
            "SELECT %d AS slice_i, CAST((%s) AS VARCHAR) AS v" % (i, inner)
        )
    return " UNION ALL ".join(parts) + " ORDER BY 1"


def parse_batch_scalar_rows(text: str, n: int) -> list[Any]:
    """Разбор ответа батч-SQL: строки `slice_i|value` → список длины n."""
    vals: list[Any] = [None] * n
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        if "|" not in line:
            continue
        idx_s, cell = line.split("|", 1)
        try:
            idx = int(idx_s.strip())
        except ValueError:
            continue
        if idx < 0 or idx >= n:
            continue
        cell = cell.strip()
        if cell == "" or cell.upper() == "NULL":
            vals[idx] = None
            continue
        try:
            vals[idx] = to_decimal(cell)
        except ValueError:
            vals[idx] = cell
    return vals


class CorpusClient:
    """Запросы к корпусу через psql. Подмена run_sql — для офлайн-замка.

    Счёт эталонов по срезам — одним вызовом scalars() (один процесс клиента).
    """

    def __init__(
        self,
        dsn: str,
        run_sql: Optional[Callable[[str], str]] = None,
    ):
        self.dsn = dsn
        self._run_sql = run_sql

    def scalars(self, sqls: list[str]) -> list[Any]:
        """N скаляров одним запросом (UNION ALL скалярных подзапросов)."""
        if not sqls:
            return []
        sql = build_corpus_batch_sql(sqls)
        return parse_batch_scalar_rows(self._exec(sql), len(sqls))

    def scalar(self, sql: str) -> Any:
        """Один скаляр — через тот же батч-путь (ровно один запуск клиента)."""
        return self.scalars([sql])[0]

    def journal_questions(self, limit: int = 500) -> list[str]:
        lim = max(1, int(limit))
        sql = (
            "SELECT t.q_text FROM ask_journal_text t "
            "JOIN ask_journal j ON j.id = t.id "
            "WHERE t.q_text IS NOT NULL AND length(t.q_text) > 0 "
            "ORDER BY j.id DESC LIMIT %d"
        ) % lim
        out = self._exec(sql)
        return [ln.strip() for ln in out.splitlines() if ln.strip()]

    def search_tables(
        self,
        *,
        prefixes: Optional[Iterable[str]] = None,
        limit: int = 0,
    ) -> list[dict]:
        """Список сущностей корпуса: search_tables (src_table, label)."""
        where = ""
        prefs = [p.lower().rstrip("_") for p in (prefixes or []) if p]
        if prefs:
            likes = " OR ".join(
                "src_table LIKE '%s_%%'" % p.replace("'", "''") for p in prefs
            )
            where = " WHERE (%s)" % likes
        lim = ""
        if limit and int(limit) > 0:
            lim = " LIMIT %d" % int(limit)
        sql = (
            "SELECT src_table, coalesce(label, '') FROM search_tables"
            "%s ORDER BY src_table%s"
        ) % (where, lim)
        out = []
        for line in self._exec(sql).splitlines():
            line = line.strip()
            if not line:
                continue
            if "|" in line:
                src, lab = line.split("|", 1)
            else:
                src, lab = line, ""
            out.append({"src_table": src.strip(), "label": lab.strip()})
        return out

    def _exec(self, sql: str) -> str:
        if self._run_sql is not None:
            return self._run_sql(sql)
        if not self.dsn:
            raise RuntimeError("DSN корпуса не задан")
        p = subprocess.run(
            ["psql", self.dsn, "-v", "ON_ERROR_STOP=1", "-tAc", sql],
            capture_output=True,
            text=True,
        )
        if p.returncode != 0:
            raise RuntimeError(
                (p.stderr or p.stdout or "psql error").strip()[:400]
            )
        return p.stdout


def verify_slices(
    specs: list[SliceSpec],
    odata: Optional[ODataClient] = None,
    corpus: Optional[CorpusClient] = None,
    *,
    just_after_tick: bool = False,
) -> list[SliceResult]:
    """Сверить список срезов: корпус — одним запросом на все corpus_sql.

    Факт 1С: OData (odata.entity) и/или fact_sql витрины. fact_sql и corpus_sql
    считаются одним батчем клиента (п. 20 — без цикла psql по срезам).
    """
    results: list[SliceResult] = []
    for spec in specs:
        results.append(
            SliceResult(
                slice_id=spec.id or spec.odata_entity or "",
                question=spec.question,
                declared_value=spec.declared,
            )
        )

    for i, spec in enumerate(specs):
        if odata is None or not spec.odata_entity:
            continue
        try:
            results[i].odata_value = odata.compute(spec)
        except Exception as e:  # noqa: BLE001
            results[i].error = "%s: %s" % (type(e).__name__, e)

    if corpus is not None:
        # Один батч: сначала fact_sql (→ odata_value), затем corpus_sql.
        fact_idx = [
            (i, spec.fact_sql)
            for i, spec in enumerate(specs)
            if spec.fact_sql and results[i].odata_value is None and not results[i].error
        ]
        corp_idx = [
            (i, spec.corpus_sql)
            for i, spec in enumerate(specs)
            if spec.corpus_sql
        ]
        batch_sqls = [sql for _, sql in fact_idx] + [sql for _, sql in corp_idx]
        if batch_sqls:
            try:
                values = corpus.scalars(batch_sqls)
                n_fact = len(fact_idx)
                for (i, _), val in zip(fact_idx, values[:n_fact]):
                    results[i].odata_value = val
                for (i, _), val in zip(corp_idx, values[n_fact:]):
                    if results[i].error:
                        continue
                    results[i].corpus_value = val
            except Exception as e:  # noqa: BLE001
                err = "%s: %s" % (type(e).__name__, e)
                for i, _ in fact_idx + corp_idx:
                    if not results[i].error:
                        results[i].error = err

    for i, spec in enumerate(specs):
        r = results[i]
        if r.error:
            r.classification = Classification(
                STATUS_ERROR,
                r.error,
                False,
                r.odata_value,
                r.corpus_value,
                r.declared_value,
            )
            continue
        r.classification = classify_discrepancy(
            r.odata_value,
            r.corpus_value,
            r.declared_value,
            question=spec.question,
            period_hint=spec.period,
            just_after_tick=just_after_tick,
        )
    return results


def verify_slice(
    spec: SliceSpec,
    odata: Optional[ODataClient] = None,
    corpus: Optional[CorpusClient] = None,
    *,
    just_after_tick: bool = False,
) -> SliceResult:
    return verify_slices(
        [spec], odata, corpus, just_after_tick=just_after_tick,
    )[0]


def load_slices(path: str) -> list[SliceSpec]:
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    if isinstance(raw, dict) and "slices" in raw:
        raw = raw["slices"]
    if not isinstance(raw, list):
        raise ValueError('slices.json: список или {"slices": [...]}')
    return [SliceSpec.from_dict(x) for x in raw]


def results_to_gold_rows(results: list[SliceResult]) -> list[dict]:
    """Строки client-gold: при наличии факта 1С источник эталона = 1c."""
    rows = []
    for r in results:
        cls = r.classification
        status = (
            cls.status if cls else (STATUS_ERROR if r.error else STATUS_PENDING)
        )
        if r.odata_value is not None:
            etalon = _jsonable(r.odata_value)
            source = ETALON_SOURCE_1C
        elif r.declared_value is not None:
            etalon = _jsonable(r.declared_value)
            source = ETALON_SOURCE_DECLARED
        elif r.corpus_value is not None:
            etalon = _jsonable(r.corpus_value)
            source = ETALON_SOURCE_CORPUS
        else:
            etalon = ""
            source = ETALON_SOURCE_PENDING
        if cls and cls.needs_independent_read and status == STATUS_MISMATCH:
            status = STATUS_NEEDS_READ
        rows.append({
            "question": r.question,
            "etalon": etalon,
            "etalon_source": source,
            "verify_status": status,
        })
    return rows


def independent_read_queue(results: list[SliceResult]) -> list[dict]:
    out = []
    for r in results:
        cls = r.classification
        if not cls:
            continue
        if cls.needs_independent_read or cls.status in (
            STATUS_MISMATCH,
            STATUS_DECLARED_WRONG,
            STATUS_NEEDS_READ,
        ):
            out.append(r.to_dict())
    return out


def _count_statuses(results: list[SliceResult]) -> dict:
    c: dict[str, int] = {}
    for r in results:
        st = r.classification.status if r.classification else STATUS_ERROR
        c[st] = c.get(st, 0) + 1
    return c


def cmd_verify(args: argparse.Namespace) -> int:
    cfg = Config.from_env(args)
    just_after = bool(args.just_after_tick)
    specs = load_slices(args.slices)
    need_odata = any(s.odata_entity for s in specs)
    need_sql = any(s.corpus_sql or s.fact_sql for s in specs)
    if need_odata:
        cfg.require_odata()
    elif not need_sql:
        raise SystemExit(
            "в срезах нет ни odata.entity, ни fact.sql / corpus.sql"
        )
    odata = (
        ODataClient(cfg.odata_base, cfg.token, cfg.timeout)
        if need_odata else None
    )
    corpus = None
    if need_sql:
        cfg.require_dsn()
        corpus = CorpusClient(cfg.dsn)
    results = verify_slices(
        specs, odata, corpus, just_after_tick=just_after,
    )
    report = {
        "results": [r.to_dict() for r in results],
        "independent_read": independent_read_queue(results),
        "counts": _count_statuses(results),
    }
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
    else:
        sys.stdout.write(text)
    if args.gold_out:
        gold = format_client_gold_tsv(results_to_gold_rows(results))
        with open(args.gold_out, "w", encoding="utf-8") as f:
            f.write(gold)
    errors = sum(1 for r in results if r.error)
    return 1 if errors else 0


def cmd_generate(args: argparse.Namespace) -> int:
    cfg = Config.from_env(args)
    meta_rows: list[dict] = []
    journal_rows: list[dict] = []
    table_rows: list[dict] = []

    if args.metadata_xml:
        xml = open(args.metadata_xml, encoding="utf-8", errors="replace").read()
        sets = parse_metadata_entity_sets(xml)
        kinds = [k.strip() for k in args.kinds.split(",") if k.strip()] if args.kinds else None
        meta_rows = generate_questions_from_metadata(
            sets, kinds=kinds, limit=int(args.limit_meta or 0),
        )
    elif args.from_gateway:
        cfg.require_odata()
        client = ODataClient(cfg.odata_base, cfg.token, cfg.timeout)
        sets = parse_metadata_entity_sets(client.metadata_xml())
        kinds = [k.strip() for k in args.kinds.split(",") if k.strip()] if args.kinds else None
        meta_rows = generate_questions_from_metadata(
            sets, kinds=kinds, limit=int(args.limit_meta or 0),
        )

    if args.journal_tsv:
        qs = []
        with open(args.journal_tsv, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                qs.append(line.split("\t", 1)[0].strip())
        journal_rows = generate_questions_from_journal(
            qs, limit=int(args.limit_journal or 0),
        )
    elif args.from_journal:
        cfg.require_dsn()
        corpus = CorpusClient(cfg.dsn)
        qs = corpus.journal_questions(limit=int(args.limit_journal or 500) or 500)
        journal_rows = generate_questions_from_journal(
            qs, limit=int(args.limit_journal or 0),
        )

    if args.from_search_tables:
        cfg.require_dsn()
        corpus = CorpusClient(cfg.dsn)
        prefs = [
            p.strip() for p in (args.table_prefixes or "").split(",") if p.strip()
        ] or None
        st_rows = corpus.search_tables(
            prefixes=prefs, limit=int(args.limit_tables or 0),
        )
        table_rows = generate_questions_from_search_tables(
            st_rows, prefixes=prefs, limit=int(args.limit_tables or 0),
        )

    if not meta_rows and not journal_rows and not table_rows:
        raise SystemExit(
            "нужен источник: --metadata-xml / --from-gateway "
            "и/или --journal-tsv / --from-journal "
            "и/или --from-search-tables"
        )

    rows = merge_gold_rows(journal_rows, table_rows, meta_rows)
    text = format_client_gold_tsv(rows)
    out = args.out or "client-gold.tsv"
    with open(out, "w", encoding="utf-8") as f:
        f.write(text)
    sys.stderr.write(
        "client-gold: строк %d (journal %d, search_tables %d, metadata %d) → %s\n"
        % (len(rows), len(journal_rows), len(table_rows), len(meta_rows), out)
    )
    return 0


def cmd_classify(_args: argparse.Namespace) -> int:
    samples = [
        classify_discrepancy(17, 17, 25, question="Сколько складов?"),
        classify_discrepancy(
            100, 90, question="Сколько продали вчера?", period_hint="relative",
        ),
        classify_discrepancy(100, 90, question="Сколько партнёров?"),
        classify_discrepancy(5, 5, 5, question="Сколько организаций?"),
    ]
    for c in samples:
        print(json.dumps(asdict(c), ensure_ascii=False, default=str))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Эталоны из 1С (OData) + генератор client-gold.tsv",
    )
    p.add_argument("--odata-base", default="", help="URL шлюза OData")
    p.add_argument("--dsn", default="", help="DSN корпуса SereneDB")
    p.add_argument("--token", default="", help="Bearer шлюза")
    p.add_argument("--timeout", type=float, default=0.0, help="таймаут HTTP")
    sub = p.add_subparsers(dest="cmd", required=True)

    v = sub.add_parser("verify", help="сверить срезы с 1С и корпусом")
    v.add_argument("--slices", required=True, help="JSON со списком срезов")
    v.add_argument("--out", default="", help="JSON-отчёт")
    v.add_argument("--gold-out", default="", help="записать client-gold.tsv")
    v.add_argument(
        "--just-after-tick",
        action="store_true",
        help="сразу после такта: relative mismatch считается substantive",
    )
    v.set_defaults(func=cmd_verify)

    g = sub.add_parser("generate", help="собрать client-gold.tsv")
    g.add_argument("--out", default="client-gold.tsv")
    g.add_argument("--metadata-xml", default="", help="снимок $metadata")
    g.add_argument("--from-gateway", action="store_true", help="$metadata со шлюза")
    g.add_argument("--journal-tsv", default="", help="файл вопросов")
    g.add_argument("--from-journal", action="store_true", help="из ask_journal")
    g.add_argument(
        "--from-search-tables",
        action="store_true",
        help="покрытие сущностей из search_tables корпуса",
    )
    g.add_argument(
        "--table-prefixes",
        default="catalog,document,accumulationregister",
        help="префиксы src_table для --from-search-tables",
    )
    g.add_argument("--kinds", default="Catalog,Document")
    g.add_argument("--limit-meta", type=int, default=0)
    g.add_argument("--limit-journal", type=int, default=0)
    g.add_argument("--limit-tables", type=int, default=0)
    g.set_defaults(func=cmd_generate)

    c = sub.add_parser("classify", help="примеры классификации")
    c.set_defaults(func=cmd_classify)
    return p


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "timeout", 0):
        args.timeout = 0.0
    return int(args.func(args) or 0)


if __name__ == "__main__":
    sys.exit(main())
