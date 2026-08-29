#!/usr/bin/env python3
"""К8 compound-ask: таблица атомов и сборка ответа без пересчёта чисел.

Слой снаружи serene_ask. Модель даёт план атомов; код зовёт ask (в тестах —
мок), заполняет таблицу и собирает prose только из полей ответов ask_1c.
Сравнение «больше/меньше/равно» — по уже посчитанным числам, без разности
и процентов (п. 19 TARGET, atom-table.md).
"""
from __future__ import annotations

import json
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Dict, List, Optional, Sequence, Union

AskFn = Callable[[str], Union[dict, str]]
SplitFn = Callable[[str], Union[dict, "SplitPlan"]]


@dataclass
class AtomSpec:
    atom_id: str
    question: str
    label: str = ""


@dataclass
class CompareSpec:
    left_id: str
    right_id: str
    relation: str = "more_than"


@dataclass
class SplitPlan:
    composite: bool
    synthesis: str = "none"
    atoms: List[AtomSpec] = field(default_factory=list)
    compare: Optional[CompareSpec] = None

    @classmethod
    def simple(cls) -> "SplitPlan":
        return cls(composite=False, synthesis="none", atoms=[])


@dataclass
class AtomRow:
    atom_id: str
    question: str
    label: str
    kind: str
    body: str
    value: Optional[float] = None
    raw: Any = None


@dataclass
class HandleResult:
    decomposed: bool
    text: str
    rows: List[AtomRow] = field(default_factory=list)
    plan: Optional[SplitPlan] = None
    raw: Any = None


def _as_dict(raw: Union[dict, str]) -> dict:
    if isinstance(raw, str):
        raw = raw.strip()
        if raw.startswith("```"):
            lines = raw.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            raw = "\n".join(lines).strip()
        return json.loads(raw)
    if isinstance(raw, dict):
        return raw
    raise TypeError("unexpected split plan type: %s" % type(raw).__name__)


def parse_split_plan(raw: Union[dict, str, SplitPlan]) -> SplitPlan:
    if isinstance(raw, SplitPlan):
        return raw
    data = _as_dict(raw)
    if not data.get("composite"):
        return SplitPlan.simple()
    atoms_in = data.get("atoms") or []
    atoms: List[AtomSpec] = []
    for i, item in enumerate(atoms_in):
        if not isinstance(item, dict):
            continue
        aid = str(item.get("id") or ("a%d" % (i + 1))).strip()
        q = str(item.get("question") or "").strip()
        if not q:
            continue
        atoms.append(
            AtomSpec(
                atom_id=aid,
                question=q,
                label=str(item.get("label") or aid).strip(),
            )
        )
    if not atoms:
        return SplitPlan.simple()
    cmp_raw = data.get("compare")
    compare = None
    if isinstance(cmp_raw, dict):
        compare = CompareSpec(
            left_id=str(cmp_raw.get("left_id") or "").strip(),
            right_id=str(cmp_raw.get("right_id") or "").strip(),
            relation=str(cmp_raw.get("relation") or "more_than").strip(),
        )
    synthesis = str(data.get("synthesis") or "table").strip() or "table"
    return SplitPlan(
        composite=True,
        synthesis=synthesis,
        atoms=atoms,
        compare=compare,
    )


def normalize_ask_payload(payload: Union[dict, str]) -> dict:
    if isinstance(payload, str):
        return {"kind": "answer", "text": payload}
    if isinstance(payload, dict):
        return payload
    return {"kind": "error", "text": str(payload)}


def _num_from_atom(atom: dict) -> Optional[float]:
    for key in ("exact_value", "value", "display_value"):
        v = atom.get(key)
        if v is None or v == "":
            continue
        try:
            return float(Decimal(str(v).replace(" ", "").replace(",", ".")))
        except (InvalidOperation, ValueError):
            continue
    return None


def extract_primary_value(data: dict) -> Optional[float]:
    if not isinstance(data, dict):
        return None
    kind = data.get("kind") or ""
    if kind in ("no_data", "clarify", "unavailable", "choice_error"):
        return None
    atom = data.get("atom")
    if isinstance(atom, dict):
        n = _num_from_atom(atom)
        if n is not None:
            return n
    atoms = data.get("atoms")
    if isinstance(atoms, list):
        for a in atoms:
            if isinstance(a, dict):
                n = _num_from_atom(a)
                if n is not None:
                    return n
    figures = data.get("figures")
    if isinstance(figures, dict):
        for key in ("sum", "count", "value", "total", "exact_value"):
            if key in figures and figures[key] is not None:
                try:
                    return float(figures[key])
                except (TypeError, ValueError):
                    pass
    return None


def _fmt_num(n: float) -> str:
    if abs(n - round(n)) < 1e-9:
        return str(int(round(n)))
    return ("%.2f" % n).rstrip("0").rstrip(".")


def body_from_payload(data: dict) -> str:
    """Фрагмент для таблицы: текст ответа или число из структуры, без парсинга прозы."""
    kind = str(data.get("kind") or "answer")
    text = str(data.get("text") or "").strip()
    if kind == "no_data":
        return text or "нет таких данных"
    if kind == "clarify":
        return text or "нужно уточнение"
    if kind in ("unavailable", "error", "choice_error"):
        return text or kind
    if text:
        return text
    val = extract_primary_value(data)
    if val is not None:
        return _fmt_num(val)
    return ""


def row_from_payload(spec: AtomSpec, payload: Union[dict, str]) -> AtomRow:
    data = normalize_ask_payload(payload)
    kind = str(data.get("kind") or "answer")
    body = body_from_payload(data)
    return AtomRow(
        atom_id=spec.atom_id,
        question=spec.question,
        label=spec.label or spec.atom_id,
        kind=kind,
        body=body,
        value=extract_primary_value(data),
        raw=data,
    )


def relation_phrase(left: float, right: float, relation: str) -> str:
    """Вердикт по двум готовым числам — без разности и процентов."""
    rel = (relation or "more_than").strip().lower()
    if math.isclose(left, right, rel_tol=0, abs_tol=1e-9):
        return "равно"
    if rel in ("equal", "eq"):
        return "равно" if math.isclose(left, right, rel_tol=0, abs_tol=1e-9) else "не равно"
    if rel in ("less_than", "lt"):
        if left < right:
            return "да, меньше"
        return "нет, не меньше"
    if left > right:
        return "да, больше"
    return "нет, не больше"


def _status_line(row: AtomRow) -> str:
    if row.kind == "no_data":
        return "%s: нет данных" % row.label
    if row.kind == "clarify":
        return "%s: нужно уточнение — %s" % (row.label, row.body or "clarify")
    if row.kind in ("unavailable", "error", "choice_error"):
        return "%s: недоступно — %s" % (row.label, row.body or row.kind)
    if row.body:
        return "%s: %s" % (row.label, row.body)
    return "%s: (нет ответа)" % row.label


def _row_map(rows: Sequence[AtomRow]) -> Dict[str, AtomRow]:
    return {r.atom_id: r for r in rows}


def synthesize_compare(rows: Sequence[AtomRow], plan: SplitPlan) -> str:
    cmap = _row_map(rows)
    cmp = plan.compare
    if not cmp and len(rows) >= 2:
        cmp = CompareSpec(
            left_id=rows[0].atom_id,
            right_id=rows[1].atom_id,
            relation="more_than",
        )
    lines = [_status_line(r) for r in rows]
    table = ["| Подпись | Результат |", "|---------|-----------|"]
    for r in rows:
        cell = r.body if r.body else ("нет данных" if r.kind == "no_data" else "—")
        table.append("| %s | %s |" % (r.label, cell))
    if not cmp:
        return "\n".join(table + [""] + lines)
    left = cmap.get(cmp.left_id)
    right = cmap.get(cmp.right_id)
    if not left or not right:
        return "\n".join(table + ["", "Сравнение неполное: не найдены атомы."] + lines)
    blocked = [
        r
        for r in (left, right)
        if r.kind in ("no_data", "clarify", "unavailable", "error")
    ]
    if blocked:
        return "\n".join(
            table
            + ["", "Сравнение пока неполное — по одному из срезов нет готового числа."]
            + lines
        )
    if left.value is None or right.value is None:
        return "\n".join(
            table
            + ["", "Сравнение пока неполное — нет пары чисел из ответов ask_1c."]
            + lines
        )
    verdict = relation_phrase(left.value, right.value, cmp.relation)
    left_show = left.body if left.body else _fmt_num(left.value)
    right_show = right.body if right.body else _fmt_num(right.value)
    summary = (
        "Вердикт (%s): %s — %s; %s — %s."
        % (verdict, left.label, left_show, right.label, right_show)
    )
    return "\n".join(table + ["", summary])


def synthesize_top_n(rows: Sequence[AtomRow], plan: SplitPlan) -> str:
    del plan
    out = ["| # | Позиция | Значение |", "|---|---------|----------|"]
    blocked = 0
    for i, r in enumerate(rows, 1):
        if r.kind == "no_data":
            val = "нет данных"
            blocked += 1
        elif r.kind == "clarify":
            val = "уточнение: " + (r.body or "")
            blocked += 1
        elif r.body:
            val = r.body
        elif r.value is not None:
            val = _fmt_num(r.value)
        else:
            val = "—"
            blocked += 1
        out.append("| %d | %s | %s |" % (i, r.label, val))
    if blocked:
        out.append("")
        out.append(
            "Часть позиций без числа — ответ неполный (%d из %d)."
            % (blocked, len(rows))
        )
    return "\n".join(out)


def synthesize_table(rows: Sequence[AtomRow], plan: SplitPlan) -> str:
    del plan
    return "\n".join(_status_line(r) for r in rows)


def synthesize(rows: Sequence[AtomRow], plan: SplitPlan) -> str:
    syn = (plan.synthesis or "table").strip().lower()
    if syn == "compare":
        return synthesize_compare(rows, plan)
    if syn == "top_n":
        return synthesize_top_n(rows, plan)
    return synthesize_table(rows, plan)


def run_atoms(
    atoms: Sequence[AtomSpec],
    ask_fn: AskFn,
    *,
    parallel: bool = True,
    max_workers: Optional[int] = None,
) -> List[AtomRow]:
    if not atoms:
        return []
    if not parallel or len(atoms) == 1:
        return [row_from_payload(a, ask_fn(a.question)) for a in atoms]
    workers = max_workers or min(8, len(atoms))
    out: Dict[str, AtomRow] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(ask_fn, a.question): a for a in atoms}
        for fut in as_completed(futs):
            spec = futs[fut]
            try:
                payload = fut.result()
            except Exception as exc:
                payload = {"kind": "error", "text": str(exc)}
            out[spec.atom_id] = row_from_payload(spec, payload)
    return [out[a.atom_id] for a in atoms if a.atom_id in out]


def handle(
    question: str,
    split_fn: SplitFn,
    ask_fn: AskFn,
    *,
    parallel: bool = True,
) -> HandleResult:
    q = (question or "").strip()
    if not q:
        return HandleResult(decomposed=False, text="", rows=[], plan=None)
    raw_plan = split_fn(q)
    plan = parse_split_plan(raw_plan)
    if not plan.composite or not plan.atoms:
        payload = ask_fn(q)
        data = normalize_ask_payload(payload)
        text = str(data.get("text") or "")
        if data.get("kind") == "no_data" and not text:
            text = "нет таких данных"
        return HandleResult(
            decomposed=False,
            text=text,
            rows=[],
            plan=plan,
            raw=data,
        )
    rows = run_atoms(plan.atoms, ask_fn, parallel=parallel)
    summary = synthesize(rows, plan)
    return HandleResult(
        decomposed=True,
        text=summary,
        rows=rows,
        plan=plan,
        raw=None,
    )


def contains_derived_arithmetic(text: str) -> bool:
    """True, если в тексте есть маркеры производной арифметики (разность, процент)."""
    low = (text or "").lower()
    banned = (
        "разница:",
        "разность:",
        "на сколько:",
        "− ",
        "percent",
        "процент",
    )
    return any(b in low for b in banned)
