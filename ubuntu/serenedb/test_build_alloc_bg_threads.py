#!/usr/bin/env python3
"""Оффлайн-замок Скорость-II этап 4 + проводка этапа 3 / пост-стены в build.sh.

allocator_background_threads (SET GLOBAL, не serened.conf), resolver_skip_unpivot,
условный REFRESH search_idx. Без живого движка.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(ROOT, "build.sh")
TUNE = os.path.join(ROOT, "box_tune.sh")
PASS, FAIL = 0, []


def t(name: str, cond: bool, detail: str = "") -> None:
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + detail[:240]) if detail else "")


def main() -> int:
    build = open(BUILD, encoding="utf-8").read()
    tune = open(TUNE, encoding="utf-8").read()

    # --- 1. SET в главном пути ДО ветки SKIP-else, идемпотентен ---
    m_set = re.search(
        r"box_tune_allocator_bg_threads\s+\"\$DSN\"", build
    )
    m_skip = re.search(
        r'if \[ "\$\{FORCE_REBUILD:-0\}" != "1" \] && \[ "\$SKIP_BUILD" = "1" \]; then',
        build,
    )
    t(
        "SET allocator_background_threads в главном пути build.sh",
        bool(m_set),
        "нет вызова box_tune_allocator_bg_threads",
    )
    t(
        "SET стоит до ветки SKIP-else",
        bool(m_set and m_skip and m_set.start() < m_skip.start()),
        f"set@{getattr(m_set, 'start', lambda: -1)()} skip@{getattr(m_skip, 'start', lambda: -1)()}",
    )
    helper = re.search(
        r"box_tune_allocator_bg_threads\(\)\s*\{(.*?)\n\}",
        tune,
        re.S,
    )
    helper_body = helper.group(1) if helper else ""
    t(
        "форма SET GLOBAL allocator_background_threads = true",
        "SET GLOBAL allocator_background_threads = true" in helper_body
        or "SET GLOBAL allocator_background_threads = true" in tune,
    )
    t(
        "SET без имён баз (идемпотентен)",
        "dbname" not in helper_body.lower() and "LOCK_TAG" not in helper_body,
        helper_body[:120],
    )
    set_forms = re.findall(
        r"SET\s+GLOBAL\s+allocator_background_threads\s*=\s*true",
        tune,
        re.I,
    )
    t("одна форма SET в box_tune (не дубль разных вариантов)", len(set_forms) == 1, str(len(set_forms)))

    # --- 2. зеркало в box_tune_apply_first_build ---
    m_apply = re.search(
        r"box_tune_apply_first_build\(\)\s*\{(.*?)\n\}",
        tune,
        re.S,
    )
    apply_body = m_apply.group(1) if m_apply else ""
    t(
        "зеркало в box_tune_apply_first_build",
        "box_tune_allocator_bg_threads" in apply_body,
        apply_body[-200:] if apply_body else "нет функции",
    )
    t(
        "зеркало рядом с memory_limit firstbuild",
        "SET memory_limit" in apply_body
        and apply_body.find("SET memory_limit")
        < apply_body.find("box_tune_allocator_bg_threads"),
    )
    # Красная R4 (блокер): SET GLOBAL живёт до рестарта движка — зеркало ДО
    # box_tune_restart_engine сбрасывается рестартом, а метка search_quality
    # уже записала бы applied и врала (п. 13). Зеркало — ПОСЛЕ рестарта.
    t(
        "зеркало ПОСЛЕ box_tune_restart_engine",
        apply_body.find("box_tune_restart_engine")
        < apply_body.find("box_tune_allocator_bg_threads"),
        "вызов хелпера до рестарта движка",
    )

    # --- 3. ключ НЕ в serened.conf ---
    t(
        "нет box_tune_upsert_flag … allocator_background_threads",
        not re.search(
            r"box_tune_upsert_flag\s+[^\n]*allocator_background_threads",
            tune,
        ),
    )
    t(
        "allocator_background_threads не пишется в conf",
        "allocator_background_threads" not in apply_body
        or "upsert_flag" not in apply_body[
            max(0, apply_body.find("allocator_background_threads") - 80) : apply_body.find(
                "allocator_background_threads"
            )
            + 40
        ],
    )

    # --- 4. отказ SET не роняет такт ---
    t(
        "guard: отказ SET не роняет (return 0)",
        "return 0" in helper_body and ("v=0" in helper_body or 'v=0' in helper_body),
        helper_body[-200:],
    )
    t(
        "запись в search_quality ключом allocator_background_threads",
        "allocator_background_threads" in helper_body
        and "search_quality" in helper_body
        and ("v=1" in helper_body or "${v}" in helper_body or "${v}," in helper_body.replace(" ", "")),
    )
    t(
        "ошибка SET уходит в note, такт продолжается",
        "rejected" in helper_body and "|| true" in helper_body,
    )

    # --- 5. preserve_insertion_order / scheduler_process_partial не добавлены этапом 4 ---
    # preserve уже был на firstbuild — не дублировать в build.sh / хелпере.
    t(
        "preserve_insertion_order не в хелпере allocator",
        "preserve_insertion_order" not in helper_body,
    )
    t(
        "preserve_insertion_order не добавлен в build.sh этапом 4",
        "preserve_insertion_order" not in build,
    )
    t(
        "scheduler_process_partial не добавлен",
        "scheduler_process_partial" not in build
        and "scheduler_process_partial" not in tune,
    )

    # --- 6. resolver_skip_unpivot из SKIP_BUILD+FORCE_REBUILD ---
    t(
        "build.sh передаёт -v resolver_skip_unpivot",
        '-v resolver_skip_unpivot="$RESOLVER_SKIP_UNPIVOT"' in build
        or "-v resolver_skip_unpivot=" in build,
    )
    t(
        "RESOLVER_SKIP_UNPIVOT из SKIP_BUILD и FORCE_REBUILD",
        "RESOLVER_SKIP_UNPIVOT=0" in build
        and 'FORCE_REBUILD' in build[build.find("RESOLVER_SKIP_UNPIVOT") : build.find("RESOLVER_SKIP_UNPIVOT") + 200]
        and "SKIP_BUILD" in build[build.find("RESOLVER_SKIP_UNPIVOT") : build.find("RESOLVER_SKIP_UNPIVOT") + 200],
    )
    skip_block = build[build.find("RESOLVER_SKIP_UNPIVOT") : build.find("RESOLVER_SKIP_UNPIVOT") + 220]
    t(
        "skip=1 только при SKIP_BUILD=1 и FORCE_REBUILD≠1",
        'FORCE_REBUILD:-0' in skip_block and 'SKIP_BUILD" = "1"' in skip_block,
        skip_block,
    )
    # Красная R4: журнал обязан называть skip и причину — grep по журналу такта
    # восстанавливает «резолвер пропущен» без похода в search_quality.
    t(
        "журнал шага 4 называет skip_unpivot",
        "резолвер (skip_unpivot=$RESOLVER_SKIP_UNPIVOT)" in build,
        "нет echo с RESOLVER_SKIP_UNPIVOT",
    )
    t(
        "echo skip идёт после вычисления RESOLVER_SKIP_UNPIVOT",
        build.find("RESOLVER_SKIP_UNPIVOT=0")
        < build.find("резолвер (skip_unpivot="),
    )

    # --- 7. REFRESH search_idx условен ---
    refresh = ""
    m_ref = re.search(
        r"# Скорость-II пост-стена.*?VACUUM \(REFRESH_INDEX\) search_idx;.*?fi",
        build,
        re.S,
    )
    if m_ref:
        refresh = m_ref.group(0)
    else:
        # запасной якорь
        idx = build.find("VACUUM (REFRESH_INDEX) search_idx;")
        refresh = build[max(0, idx - 400) : idx + 120] if idx >= 0 else ""
    t(
        "REFRESH search_idx условен по пересборке корпуса",
        "_CORPUS_REBUILT" in refresh,
        refresh[:160],
    )
    t(
        "REFRESH search_idx условен по _emb5_done>0",
        "_emb5_done" in refresh and "-gt 0" in refresh,
        refresh[:160],
    )
    t(
        "обе стороны условия через ИЛИ",
        "||" in refresh
        and "_CORPUS_REBUILT" in refresh
        and "_emb5_done" in refresh,
    )
    t(
        "_CORPUS_REBUILT выставляется в else пересборки",
        "_CORPUS_REBUILT=1" in build and "_CORPUS_REBUILT=0" in build,
    )
    t(
        "search_entity_card REFRESH не тронут",
        "VACUUM (REFRESH_INDEX) search_entity_card;" in build,
    )

    r = subprocess.run(["bash", "-n", BUILD], capture_output=True, text=True)
    t("build.sh bash -n", r.returncode == 0, r.stderr[:120])
    r = subprocess.run(["bash", "-n", TUNE], capture_output=True, text=True)
    t("box_tune.sh bash -n", r.returncode == 0, r.stderr[:120])

    print("\nитог: %d ok, %d fail" % (PASS, len(FAIL)))
    if FAIL:
        print("FAIL:", ", ".join(FAIL))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
