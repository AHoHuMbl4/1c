#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Оффлайн-замок ubuntu/serenedb/f6_rollout_measure.sh (без сети и живой базы)."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(ROOT, "f6_rollout_measure.sh")
PASS, FAIL = 0, []


def t(name: str, cond: bool, detail: str = "") -> None:
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + str(detail)[:200]) if detail else "")


def run(env: dict, timeout: int = 30) -> subprocess.CompletedProcess:
    e = os.environ.copy()
    e.update(env)
    # оффлайн: короткий curl, без реальных сервисов
    e.setdefault("F6_CURL_MAX", "2")
    e.setdefault("F6_ASK_SMOKE_MAX", "2")
    return subprocess.run(
        ["bash", SCRIPT],
        capture_output=True,
        text=True,
        env=e,
        timeout=timeout,
    )


def main() -> int:
    st = os.stat(SCRIPT)
    t("chmod +x", bool(st.st_mode & 0o111))
    r = subprocess.run(["bash", "-n", SCRIPT], capture_output=True, text=True)
    t("bash -n", r.returncode == 0, r.stderr[:120])

    body = open(SCRIPT, encoding="utf-8").read()
    # скрипт меряет; строк включения флагов Ф6 в env юнита в нём нет
    toggle = re.findall(
        r"(?:^|\n)\s*(?:export\s+)?ASK_(?:SQL_RRF|RESOLVER_IVF|HEALTH_NATIVE_FRESHNESS|"
        r"SOLR_SYNONYMS|CALENDAR_AXIS)\s*=\s*1",
        body,
    )
    t("нет ASK_*=1 включения флагов", not toggle, toggle)
    t("нет systemctl в скрипте", "systemctl" not in body)
    t("нет правки /etc/1c-serene", "/etc/1c-serene" not in body)
    t("фаза compare есть", "compare" in body and "F6_PHASE" in body)

    # недоступный контур → ненулевой код + сообщение
    dead = "http://127.0.0.1:1/ask"
    with tempfile.TemporaryDirectory() as td:
        r = run({
            "ASK_URL": dead,
            "F6_FLAG": "ASK_HEALTH_NATIVE_FRESHNESS",
            "F6_PHASE": "before",
            "F6_MARK_DIR": td,
            "F6_SKIP_PROBE": "1",
            "F6_SKIP_GOLDEN": "1",
        })
        err = (r.stderr or "") + (r.stdout or "")
        t("dead URL → rc != 0", r.returncode != 0, "rc=%s" % r.returncode)
        t("dead URL → сообщение о контуре",
          "контур недоступен" in err or "модель или база недоступны" in err,
          err[:240])

    # compare без пары → ненулевой
    with tempfile.TemporaryDirectory() as td:
        r = run({
            "F6_FLAG": "ASK_RESOLVER_IVF",
            "F6_PHASE": "compare",
            "F6_MARK_DIR": td,
        })
        err = (r.stderr or "") + (r.stdout or "")
        t("compare без снимков → rc != 0", r.returncode != 0, "rc=%s" % r.returncode)
        t("compare без снимков → текст", "нет пары снимков" in err, err[:200])

    # разбор compare на пустом/битом наборе не падает исключением — rc и текст
    with tempfile.TemporaryDirectory() as td:
        for phase in ("before", "after"):
            d = os.path.join(td, "ASK_SOLR_SYNONYMS", phase)
            os.makedirs(d)
            # оба skipped → код 4, таблица при этом может напечататься до проверки
            summary = {
                "flag": "ASK_SOLR_SYNONYMS",
                "phase": phase,
                "health_ms": 0,
                "ask_smoke_ms": 0,
                "ask_smoke_kind": "",
                "probe": {"skipped": True, "ok_parse": False},
                "golden": {"skipped": True, "n": None},
            }
            with open(os.path.join(d, "summary.json"), "w", encoding="utf-8") as f:
                json.dump(summary, f)
        r = run({
            "F6_FLAG": "ASK_SOLR_SYNONYMS",
            "F6_PHASE": "compare",
            "F6_MARK_DIR": td,
        })
        err = (r.stderr or "") + (r.stdout or "")
        t("compare skipped-пара → rc != 0", r.returncode != 0, "rc=%s" % r.returncode)
        t("compare skipped → не traceback",
          "Traceback" not in err and "пуст" in err,
          err[:240])

    # нормальная пара снимков → таблица и rc 0
    with tempfile.TemporaryDirectory() as td:
        for phase, hits, secs in (("before", 8, 55.9), ("after", 8, 44.1)):
            d = os.path.join(td, "ASK_RESOLVER_IVF", phase)
            os.makedirs(d)
            summary = {
                "flag": "ASK_RESOLVER_IVF",
                "phase": phase,
                "health_ms": 50 if phase == "before" else 130,
                "ask_smoke_ms": 1000,
                "ask_smoke_kind": "answer",
                "probe": {
                    "hits": hits, "total": 8, "errs": 0, "secs": secs,
                    "ok_parse": True, "rc": 0,
                },
                "golden": {"n": 8, "expected_n": 8, "ok_parse": True, "rc": 0},
            }
            with open(os.path.join(d, "summary.json"), "w", encoding="utf-8") as f:
                json.dump(summary, f)
        r = run({
            "F6_FLAG": "ASK_RESOLVER_IVF",
            "F6_PHASE": "compare",
            "F6_MARK_DIR": td,
        })
        out = (r.stdout or "") + (r.stderr or "")
        t("compare ok → rc 0", r.returncode == 0, "rc=%s %s" % (r.returncode, out[:160]))
        t("compare ok → markdown table",
          "| metric | before | after |" in out and "probe hits" in out,
          out[:300])

    # F6_PHASE пуст → rc != 0
    r = run({"F6_PHASE": "", "F6_FLAG": "X"})
    t("пустая фаза → rc != 0", r.returncode != 0, "rc=%s" % r.returncode)

    print("\nитог: %d ok, %d fail" % (PASS, len(FAIL)))
    if FAIL:
        print("FAIL:", ", ".join(FAIL))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
