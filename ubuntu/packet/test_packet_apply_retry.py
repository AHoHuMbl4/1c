#!/usr/bin/env python3
"""Офлайн-замок: повтор карантина после прогресса потока (packet_apply).

Сценарии: applied seq больше → quarantined→verified + attempts;
attempts ≥ max → attempts_exhausted, повтор не делается;
без прогресса потока — карантин не трогается.
Запуск: python3 ubuntu/packet/test_packet_apply_retry.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import packet_apply as A  # noqa: E402

FAILS: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("ok  " if cond else "FAIL") + f"  {name}"
          + (f"  ({detail})" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def _write(path: str, obj) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f)


def _setup(root: str, base: str, last_applied: int, packages: list) -> None:
    """packages: (pkg_id, seq, state, error, attempts|None)."""
    bdir = os.path.join(root, "inbox", base)
    os.makedirs(bdir, exist_ok=True)
    pkg_map = {}
    for pkg_id, seq, state, error, attempts in packages:
        pdir = os.path.join(bdir, pkg_id)
        st = {"state": state, "error": error, "seq": seq}
        if attempts is not None:
            st["attempts"] = attempts
        _write(os.path.join(pdir, "state.json"), st)
        _write(os.path.join(pdir, "manifest.json"), {
            "seq": seq, "package_id": "%s/%s" % (base, pkg_id), "chunks": [],
        })
        entry = {"state": state, "error": error}
        if attempts is not None:
            entry["attempts"] = attempts
        pkg_map[pkg_id] = entry
    _write(os.path.join(bdir, "state.json"), {
        "last_applied_seq": last_applied, "packages": pkg_map,
    })


def _pkg(root: str, base: str, pkg_id: str) -> dict:
    with open(os.path.join(root, "inbox", base, pkg_id, "state.json"),
              encoding="utf-8") as f:
        return json.load(f)


def main() -> int:
    root = tempfile.mkdtemp(prefix="pkt-retry-")
    old_root = A.PACKET_ROOT
    A.PACKET_ROOT = root
    try:
        # 1) прогресс потока → повтор
        _setup(root, "b1", last_applied=20, packages=[
            ("p010", 10, "quarantined", "delta_without_key", 0),
        ])
        n = A._retry_quarantined_after_progress(None)
        st = _pkg(root, "b1", "p010")
        check("прогресс: возврат 1", n == 1)
        check("прогресс: state verified", st.get("state") == "verified", repr(st))
        check("прогресс: attempts=1", st.get("attempts") == 1, repr(st))
        check("прогресс: error сброшен", st.get("error") is None, repr(st))

        # 2) без прогресса — не трогать
        _setup(root, "b2", last_applied=5, packages=[
            ("p010", 10, "quarantined", "delta_without_key", 0),
        ])
        n = A._retry_quarantined_after_progress("b2")
        st = _pkg(root, "b2", "p010")
        check("без прогресса: 0", n == 0)
        check("без прогресса: остался quarantined",
              st.get("state") == "quarantined", repr(st))

        # 3) attempts ≥ max → attempts_exhausted, без повторной попытки
        _setup(root, "b3", last_applied=50, packages=[
            ("p010", 10, "quarantined", "delta_without_key",
             A.QUARANTINE_RETRY_MAX),
        ])
        n = A._retry_quarantined_after_progress("b3")
        st = _pkg(root, "b3", "p010")
        check("exhausted: 0 промоутов", n == 0)
        check("exhausted: state quarantined",
              st.get("state") == "quarantined", repr(st))
        check("exhausted: error attempts_exhausted",
              isinstance(st.get("error"), str)
              and st["error"].startswith("attempts_exhausted"), repr(st))

        # 4) уже attempts_exhausted — идемпотентно
        n2 = A._retry_quarantined_after_progress("b3")
        st2 = _pkg(root, "b3", "p010")
        check("exhausted повтор: 0", n2 == 0)
        check("exhausted повтор: error стабилен",
              st2.get("error") == st.get("error"), repr(st2))

        # 5) порог из env читается
        check("QUARANTINE_RETRY_MAX int", isinstance(A.QUARANTINE_RETRY_MAX, int)
              and A.QUARANTINE_RETRY_MAX >= 1)
    finally:
        A.PACKET_ROOT = old_root

    if FAILS:
        print("FAIL %d" % len(FAILS))
        return 1
    print("OK %d" % (5 + 3 + 3 + 2 + 1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
