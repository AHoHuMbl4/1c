#!/usr/bin/env python3
"""К8: декомпозитор составных вопросов — движок скилла OpenClaw над /ask.

Слой снаружи serene_ask: модель решает, составной ли вопрос и как его
разложить; код зовёт ask по атомам и сводит числа детерминированно (п. 19).
Контракт A/B/C и люк остаются в serene_ask — здесь не дублируются.
"""
from __future__ import annotations

import json
import math
import os
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Dict, List, Optional, Sequence, Union

# --- типы ---------------------------------------------------------------------

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
    relation: str = "more_than"  # more_than | less_than | equal


@dataclass
class SplitPlan:
    composite: bool
    synthesis: str = "none"  # none | compare | top_n | table
    atoms: List[AtomSpec] = field(default_factory=list)
    compare: Optional[CompareSpec] = None

    @classmethod
    def simple(cls) -> "SplitPlan":
        return cls(composite=False, synthesis="none", atoms=[])


@dataclass
class AtomResult:
    atom_id: str
    question: str
    label: str
    kind: str
    text: str
    value: Optional[float]
    raw: Any = None


@dataclass
class HandleResult:
    decomposed: bool
    text: str
    atoms: List[AtomResult] = field(default_factory=list)
    plan: Optional[SplitPlan] = None
    raw: Any = None


# --- промпт разбития (модель, не списки слов в коде) --------------------------

SPLIT_SYSTEM = """\
Ты разбираешь вопросы к учётной системе 1С. Ответь ТОЛЬКО JSON-объектом.

Если вопрос простой (один период, одна мера, без сравнения и без перечисления
«топ-N и сколько у каждого») — верни:
{"composite": false}

Если вопрос составной — верни:
{
  "composite": true,
  "synthesis": "compare" | "top_n" | "table",
  "atoms": [
    {"id": "a1", "question": "самостоятельный простой вопрос", "label": "краткая подпись"}
  ],
  "compare": {"left_id": "a1", "right_id": "a2", "relation": "more_than"}
}

Правила:
- Каждый атом — полный вопрос со своим периодом/срезом, без местоимений «там»,
  «в прошлом» без дат — замени на явный период.
- synthesis=compare — ровно два числовых атома; relation: more_than | less_than | equal.
- synthesis=top_n — несколько атомов «сколько у <имя>» или один атом с rank, если
  ядро само отдаёт топ; предпочитай отдельный атом на каждую позицию, если в
  вопросе перечисление.
- Не угадывай сущности — формулируй вопрос так, как спросил человек.
"""


def split_prompt(question: str) -> str:
    return SPLIT_SYSTEM + "\n\nВопрос:\n" + question.strip()


# --- разбор плана модели ------------------------------------------------------

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
    raise TypeError(f"unexpected split plan type: {type(raw).__name__}")


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
        atoms.append(AtomSpec(
            atom_id=aid,
            question=q,
            label=str(item.get("label") or aid).strip(),
        ))
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


# --- извлечение числа из ответа /ask -----------------------------------------

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
        for key in ("sum", "count", "value", "total"):
            if key in figures and figures[key] is not None:
                try:
                    return float(figures[key])
                except (TypeError, ValueError):
                    pass
    text = (data.get("text") or "").strip()
    if text and kind == "answer":
        # Текстовый ответ без структуры — число не извлекаем (не парсим прозу).
        return None
    return None


def normalize_ask_payload(payload: Union[dict, str]) -> dict:
    if isinstance(payload, str):
        return {"kind": "answer", "text": payload}
    if isinstance(payload, dict):
        return payload
    return {"kind": "error", "text": str(payload)}


def atom_result_from_payload(spec: AtomSpec, payload: Union[dict, str]) -> AtomResult:
    data = normalize_ask_payload(payload)
    kind = str(data.get("kind") or "answer")
    text = str(data.get("text") or "").strip()
    return AtomResult(
        atom_id=spec.atom_id,
        question=spec.question,
        label=spec.label or spec.atom_id,
        kind=kind,
        text=text,
        value=extract_primary_value(data),
        raw=data,
    )


# --- сравнение и сводка (код, не модель) --------------------------------------

def compare_values(
    left: float,
    right: float,
    relation: str = "more_than",
) -> tuple[Optional[bool], str]:
    """Арифметика сравнения. Возвращает (вердикт для more_than/less_than, фраза)."""
    rel = (relation or "more_than").strip().lower()
    if math.isclose(left, right, rel_tol=0, abs_tol=1e-9):
        return None, "равно: %s = %s" % (_fmt_num(left), _fmt_num(right))
    if rel in ("equal", "eq"):
        ok = math.isclose(left, right, rel_tol=0, abs_tol=1e-9)
        return ok, ("равно: %s = %s" if ok else "не равно: %s ≠ %s") % (
            _fmt_num(left), _fmt_num(right))
    if rel in ("less_than", "lt"):
        if left < right:
            return True, "да, меньше: %s < %s" % (_fmt_num(left), _fmt_num(right))
        return False, "нет, больше или равно: %s ≥ %s" % (_fmt_num(left), _fmt_num(right))
    # more_than по умолчанию
    if left > right:
        return True, "да, больше: %s > %s" % (_fmt_num(left), _fmt_num(right))
    return False, "нет, не больше: %s ≤ %s" % (_fmt_num(left), _fmt_num(right))


def _fmt_num(n: float) -> str:
    if abs(n - round(n)) < 1e-9:
        return str(int(round(n)))
    s = ("%.2f" % n).rstrip("0").rstrip(".")
    return s


def _result_map(results: Sequence[AtomResult]) -> Dict[str, AtomResult]:
    return {r.atom_id: r for r in results}


def _atom_status_line(r: AtomResult) -> str:
    if r.kind == "no_data":
        return "%s: нет данных" % (r.label or r.atom_id)
    if r.kind == "clarify":
        return "%s: нужно уточнение — %s" % (r.label or r.atom_id, r.text or "clarify")
    if r.kind in ("unavailable", "error", "choice_error"):
        return "%s: недоступно — %s" % (r.label or r.atom_id, r.text or r.kind)
    if r.value is not None:
        return "%s: %s" % (r.label or r.atom_id, _fmt_num(r.value))
    if r.text:
        return "%s: %s" % (r.label or r.atom_id, r.text)
    return "%s: (нет числа)" % (r.label or r.atom_id)


def synthesize_compare(
    results: Sequence[AtomResult],
    plan: SplitPlan,
) -> str:
    cmap = _result_map(results)
    cmp = plan.compare
    if not cmp:
        if len(results) >= 2:
            cmp = CompareSpec(
                left_id=results[0].atom_id,
                right_id=results[1].atom_id,
                relation="more_than",
            )
        else:
            return "\n".join(_atom_status_line(r) for r in results)
    left = cmap.get(cmp.left_id)
    right = cmap.get(cmp.right_id)
    lines = [_atom_status_line(r) for r in results]
    if not left or not right:
        return "Сводка сравнения невозможна: не найдены атомы.\n" + "\n".join(lines)
    for r in (left, right):
        if r.kind in ("no_data", "clarify", "unavailable", "error"):
            return (
                "Сравнение невозможно — по одному из периодов нет готового числа.\n"
                + "\n".join(lines)
            )
    if left.value is None or right.value is None:
        return (
            "Сравнение невозможно — не удалось извлечь числа из ответов.\n"
            + "\n".join(lines)
        )
    _verdict, phrase = compare_values(left.value, right.value, cmp.relation)
    diff = left.value - right.value
    return (
        "\n".join(lines)
        + "\n\nРазница: %s − %s = %s"
        % (_fmt_num(left.value), _fmt_num(right.value), _fmt_num(diff))
        + "\nВердикт: " + phrase
    )


def synthesize_top_n(results: Sequence[AtomResult], plan: SplitPlan) -> str:
    lines = ["| # | Позиция | Значение |", "|---|---------|----------|"]
    for i, r in enumerate(results, 1):
        if r.kind == "no_data":
            val = "нет данных"
        elif r.kind == "clarify":
            val = "уточнение"
        elif r.value is not None:
            val = _fmt_num(r.value)
        elif r.text:
            val = r.text[:80]
        else:
            val = "—"
        lines.append("| %d | %s | %s |" % (i, r.label or r.atom_id, val))
    blocked = [r for r in results if r.kind in ("no_data", "clarify", "unavailable")]
    if blocked:
        lines.append("")
        lines.append(
            "Часть позиций без числа — ответ неполный (%d из %d)."
            % (len(blocked), len(results))
        )
    return "\n".join(lines)


def synthesize_table(results: Sequence[AtomResult], plan: SplitPlan) -> str:
    return "\n".join(_atom_status_line(r) for r in results)


def synthesize(results: Sequence[AtomResult], plan: SplitPlan) -> str:
    syn = (plan.synthesis or "table").strip().lower()
    if syn == "compare":
        return synthesize_compare(results, plan)
    if syn == "top_n":
        return synthesize_top_n(results, plan)
    return synthesize_table(results, plan)


# --- выполнение атомов --------------------------------------------------------

def run_atoms(
    atoms: Sequence[AtomSpec],
    ask_fn: AskFn,
    *,
    parallel: bool = True,
    max_workers: Optional[int] = None,
) -> List[AtomResult]:
    if not atoms:
        return []
    if not parallel or len(atoms) == 1:
        return [atom_result_from_payload(a, ask_fn(a.question)) for a in atoms]

    workers = max_workers or min(8, len(atoms))
    out: Dict[str, AtomResult] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(ask_fn, a.question): a for a in atoms}
        for fut in as_completed(futs):
            spec = futs[fut]
            try:
                payload = fut.result()
            except Exception as exc:
                payload = {"kind": "error", "text": str(exc)}
            out[spec.atom_id] = atom_result_from_payload(spec, payload)
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
        return HandleResult(decomposed=False, text="", atoms=[], plan=None)
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
            atoms=[],
            plan=plan,
            raw=data,
        )
    results = run_atoms(plan.atoms, ask_fn, parallel=parallel)
    summary = synthesize(results, plan)
    return HandleResult(
        decomposed=True,
        text=summary,
        atoms=results,
        plan=plan,
        raw=None,
    )


# --- HTTP-клиент /ask (тесты и живой прогон) ----------------------------------

def http_ask(
    question: str,
    *,
    url: Optional[str] = None,
    token: Optional[str] = None,
    timeout: float = 300.0,
) -> dict:
    base = (url or os.environ.get("ASK_URL") or "http://127.0.0.1:8091/ask").rstrip("/")
    if not base.endswith("/ask"):
        base = base + "/ask"
    tok = token if token is not None else os.environ.get("ASK_TOKEN", "")
    body = json.dumps({"question": question}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        base,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + tok,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            detail = e.read().decode("utf-8")
        except Exception:
            detail = str(e)
        return {"kind": "error", "text": detail, "http_status": e.code}


def make_http_ask_fn(**kwargs) -> AskFn:
    return lambda q: http_ask(q, **kwargs)


# --- CLI ----------------------------------------------------------------------

def _main() -> int:
    import argparse
    import sys

    p = argparse.ArgumentParser(description="К8 ask-decomposer (нужен split JSON на stdin)")
    p.add_argument("question", help="исходный вопрос")
    p.add_argument(
        "--plan",
        help="JSON плана разбития (иначе простой вопрос → один /ask)",
    )
    p.add_argument("--ask-url", default=os.environ.get("ASK_URL", ""))
    p.add_argument("--sequential", action="store_true")
    args = p.parse_args()

    if args.plan:
        plan_data = json.loads(args.plan)
        split_fn = lambda _q: plan_data  # noqa: E731
    else:
        split_fn = lambda _q: SplitPlan.simple()  # noqa: E731

    ask_fn = make_http_ask_fn(url=args.ask_url or None)
    result = handle(args.question, split_fn, ask_fn, parallel=not args.sequential)
    sys.stdout.write(result.text + "\n")
    if result.decomposed and result.atoms:
        sys.stdout.write("\n--- atoms ---\n")
        for a in result.atoms:
            sys.stdout.write(
                "%s kind=%s value=%s\n"
                % (a.atom_id, a.kind, a.value)
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
