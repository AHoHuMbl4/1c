#!/usr/bin/env python3
"""S1 некролог: early-clarify + _fork_fp_diag снесены вместе с fork-зонами.

Прежний дефект (list в set) жил в legacy-тракте. На одном пути маркеров
`_ec_atom_fps` / `_fork_fp_diag` нет — проверяем отсутствие.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
Z20 = ROOT / "ask" / "z20_ask_main_http.py"

PASS, FAIL = 0, []


def t(name: str, cond: bool, detail: str = "") -> None:
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + str(detail)[:240]) if detail else "")


def main() -> int:
    text = Z20.read_text(encoding="utf-8")
    t("z20 readable", Z20.is_file() and len(text) > 1000)
    t("S1: _ec_atom_fps снесён из z20", "_ec_atom_fps" not in text)
    t("S1: _fork_fp_diag снесён из z20", "_fork_fp_diag" not in text)

    import os
    os.environ.setdefault("ASK_TOKEN", "test")
    os.environ.setdefault("EMBED_BASE_URL", "-")
    os.environ.setdefault("EMBED_MODEL", "-")
    sys.path.insert(0, str(ROOT))
    import serene_ask as A  # noqa: E402
    t("S1: _fork_fp_diag отсутствует в ns",
      not hasattr(A, "_fork_fp_diag"))

    print("PASS %d FAIL %d" % (PASS, len(FAIL)))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
