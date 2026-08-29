"""Load zone modules into serene_ask.__dict__ with source line numbers intact."""
from __future__ import annotations

import ast
import importlib.util
import re
from pathlib import Path

_ASK_DIR = Path(__file__).resolve().parent

_ZONE_FILES = [
    "z01_infra_trace_llm.py",
    "z02_intent.py",
    "z03_period_windows.py",
    "z04_calendar_axis.py",
    "z04b_currency_axis.py",
    "z05_entity_form.py",
    "z06_entity_search.py",
    "z07_rrf_vectors.py",
    "z08_measures_totals.py",
    "z09_fork_detector.py",
    "z10_rank.py",
    "z11_sales.py",
    "z12_stock_balance.py",
    "z13_fork_outcomes.py",
    "z14_clarify_memory.py",
    "z15_answer_atoms.py",
    "z16_veto_pick_entity.py",
    "z17_aggregate_groups.py",
    "z18_compose.py",
    "z19_answer_check.py",
    "z21_wiki_choice.py",
    "z20_ask_main_http.py",
]

_REGISTER_RE = re.compile(r"^register_zone\s*\(")


def _body_start_line(lines: list[str]) -> int:
    for i, ln in enumerate(lines):
        s = ln.strip()
        if s.startswith("apply_bindings("):
            continue
        if s.startswith("from ask.") or s.startswith('"""Zone'):
            continue
        if s.startswith("from __future__"):
            continue
        if not s:
            continue
        if (
            s.startswith("DSN =")
            or s.startswith("def ")
            or s.startswith("class ")
            or (s.startswith("_") and "=" in s)
            or s.startswith("#")
            or s.startswith("INTENT_")
            or s.startswith("SCORER")
        ):
            return i + 1  # 1-based
    raise RuntimeError("zone body start not found")


def _body_end_line(lines: list[str]) -> int:
    for i in range(len(lines) - 1, -1, -1):
        if _REGISTER_RE.match(lines[i].strip()):
            end = i
            while end > 0 and not lines[end - 1].strip():
                end -= 1
            return end  # exclusive 0-based slice end
    return len(lines)


def _exec_zone(path: Path, ns: dict) -> None:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(True)
    start = _body_start_line(lines)
    end = _body_end_line(lines)
    tree = ast.parse(text, filename=str(path))
    kept = [n for n in tree.body if getattr(n, "lineno", 0) >= start and getattr(n, "lineno", 0) <= end]
    if not kept:
        raise RuntimeError(f"no statements for {path.name} lines>={start}")
    mod = ast.Module(body=kept, type_ignores=[])
    ast.fix_missing_locations(mod)
    code = compile(mod, str(path), "exec")
    exec(code, ns)  # noqa: S102


def _seed_namespace(ns: dict) -> None:
    import ask._imports as _imp

    for k, v in vars(_imp).items():
        if k.startswith("_") and k not in ("__builtins__",):
            continue
        ns[k] = v


def load_all(target: dict | None = None) -> dict:
    ns: dict = target if target is not None else {
        "__builtins__": __builtins__,
        "__name__": "serene_ask",
    }
    _seed_namespace(ns)
    seen: set[str] = set()
    for fname in _ZONE_FILES:
        if fname in seen:
            continue
        seen.add(fname)
        _exec_zone(_ASK_DIR / fname, ns)
    return ns


def zone_paths() -> list[Path]:
    out: list[Path] = []
    seen: set[str] = set()
    for fname in _ZONE_FILES:
        if fname in seen:
            continue
        seen.add(fname)
        out.append(_ASK_DIR / fname)
    return out


def combined_source() -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in zone_paths())
