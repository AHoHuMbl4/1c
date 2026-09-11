#!/usr/bin/env python3
"""Замок: ранний entity-clarify не кладёт отпечаток класса развилки в множество.

`_fork_fp_diag` (z09) отдаёт отпечаток СПИСКОМ пар, а z20 строит из отпечатков
множество `_ec_atom_fps`. Список в множество не кладётся: вопрос «Сколько банков
в справочнике?» на :8092 (Python 3.14) отдавал
`TypeError: cannot use 'list' as a set element (unhashable type: 'list')` → 503
вместо меню уточнения. Ключ — хешируемая форма отпечатка, и
повторный отпечаток схлопывается в один (иначе `same_fam_no_atoms` врёт).
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
Z20 = ROOT / "ask" / "z20_ask_main_http.py"
Z09 = ROOT / "ask" / "z09_fork_detector.py"

PASS, FAIL = 0, []

FP_SAMPLE = (("op", "count"), ("period", "2026-01-01"),
             (("axis", "warehouse"), "storage"))


def t(name: str, cond: bool, detail: str = "") -> None:
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + str(detail)[:240]) if detail else "")


def _atom_fps_block(text: str) -> str:
    m = text.find("_ec_atom_fps = {")
    if m < 0:
        return ""
    end = text.find("_ec_atom_fps.discard(None)", m)
    return text[m:end if end > 0 else m + 400]


def _fork_fp_diag():
    """Живая функция из z09 — отпечаток класса развилки."""
    tree = ast.parse(Z09.read_text(encoding="utf-8"))
    fn = [n for n in tree.body
          if isinstance(n, ast.FunctionDef) and n.name == "_fork_fp_diag"]
    if not fn:
        return None
    ns: dict = {}
    exec(compile(ast.Module(body=fn, type_ignores=[]), str(Z09), "exec"), ns)  # noqa: S102
    return ns["_fork_fp_diag"]


def _coerced(fp):
    """Та же форма ключа, что в z20: сериализация отпечатка."""
    return json.dumps(fp, sort_keys=True, default=str, ensure_ascii=False)


def main() -> int:
    text = Z20.read_text(encoding="utf-8")
    block = _atom_fps_block(text)

    t("z20 readable", Z20.is_file() and len(text) > 1000)
    t("anchor _ec_atom_fps found", bool(block), "anchor not found")

    t("fingerprint coerced to hashable key",
      "json.dumps(" in block or "tuple(" in block, block[:200])
    raw_element = re.compile(
        r'^\s*\(?a\.get\("fingerprint"\) if isinstance\(a, dict\) else None\)?\s*$')
    t("raw fingerprint not used as set element",
      not any(raw_element.match(ln) for ln in block.splitlines()), block[:200])

    fp_diag = _fork_fp_diag()
    t("_fork_fp_diag lives in z09", callable(fp_diag))
    if not callable(fp_diag):
        print("PASS %d FAIL %d" % (PASS, len(FAIL)))
        return 1
    raw = fp_diag(FP_SAMPLE)
    t("fingerprint is a list (reason for coercion)", isinstance(raw, list), type(raw))
    try:
        {raw}
        t("raw fingerprint unhashable (crash reproduced)", False, "set() accepted list")
    except TypeError:
        t("raw fingerprint unhashable (crash reproduced)", True)

    keys = {_coerced(a.get("fingerprint"))
            for a in ({"fingerprint": raw}, {"fingerprint": fp_diag(FP_SAMPLE)})}
    t("equal fingerprints collapse to one key", keys == {_coerced(raw)}, keys)
    other = fp_diag((("op", "sum"), ("period", "2026-01-01")))
    t("different fingerprints stay distinct",
      len({_coerced(raw), _coerced(other)}) == 2)

    print("PASS %d FAIL %d" % (PASS, len(FAIL)))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
