#!/usr/bin/env python3
"""Оффлайн-замок: WIKI_ALIAS_MODE=tick|cycle (plan-cycle-mode.md §4).

Статический разбор wiki_alias.sh. Без базы, модели и юнитов.
Запуск: python3 ubuntu/serenedb/test_wiki_alias_cycle.py
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WIKI = ROOT / "wiki_alias.sh"
PASS, FAIL = 0, []


def t(name: str, cond: bool, detail: str = "") -> None:
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + detail[:240]) if detail else "")


def _split_cycle_tick(body: str) -> tuple[str, str]:
    """Cycle-ветка до раннего exit; tick — после маркера умолчания."""
    m = re.search(
        r"if \[ \"\$WIKI_ALIAS_MODE\" = \"cycle\" \]; then\n"
        r"  wiki_alias_run_cycle\n"
        r"  exit \$\?\n"
        r"fi\n",
        body,
    )
    if not m:
        return "", body
    # Функции cycle объявлены перед if; берём от wiki_alias_run_cycle / _cycle_
    start = body.find("# ── WIKI_ALIAS_MODE=cycle:")
    if start < 0:
        start = body.find("wiki_alias_run_cycle()")
    cycle = body[start:m.end()] if start >= 0 else body[:m.end()]
    tick = body[m.end():]
    return cycle, tick


def main() -> int:
    t("wiki_alias.sh exists", WIKI.is_file())
    body = WIKI.read_text(encoding="utf-8") if WIKI.is_file() else ""

    r = subprocess.run(["bash", "-n", str(WIKI)], capture_output=True, text=True)
    t("bash -n wiki_alias.sh", r.returncode == 0, (r.stderr or r.stdout)[:200])

    cycle, tick = _split_cycle_tick(body)

    # ── 1) MODE нет → tick; tick-маркеры не изменились ──────────────────────
    t(
        "1 MODE default tick",
        'WIKI_ALIAS_MODE="${WIKI_ALIAS_MODE:-tick}"' in body,
    )
    t(
        "1 early if cycle → run + exit",
        'if [ "$WIKI_ALIAS_MODE" = "cycle" ]; then' in body
        and "wiki_alias_run_cycle" in body
        and "exit $?" in body,
    )
    t(
        "1 tick: collision while на ROUNDS:-40 (не CEILING)",
        'while [ "$rounds" -lt "${WIKI_ALIAS_COLLISION_ROUNDS:-40}" ]; do' in tick,
        "missing tick ROUNDS while",
    )
    t(
        "1 tick: red5-сборка очереди тоже на ROUNDS:-40",
        tick.count('"$rounds" -lt "${WIKI_ALIAS_COLLISION_ROUNDS:-40}"') >= 2,
        str(tick.count('"$rounds" -lt "${WIKI_ALIAS_COLLISION_ROUNDS:-40}"')),
    )
    t(
        "1 tick: CEILING-лифта нет",
        "CEILING=" not in tick and "ROUNDS_STEP" not in tick and "ROUNDS_MAX" not in tick,
    )
    t(
        "1 tick: reask-ветка на месте",
        'if [ "$REASK_EVERY" -gt 0 ]' in tick and "wiki_alias_reask_init.sql" in tick,
    )
    t(
        "1 tick: solr хвост alias_table=search_entity_alias",
        '-v alias_table="search_entity_alias"' in tick
        and "solr_synonyms_compile.sql" in tick,
    )

    # ── 2) cycle: порядок фаз init→collision→promote→migrate→solr→A3 ────────
    t("2 cycle-блок выделен", bool(cycle) and "wiki_alias_run_cycle" in cycle)
    # Позиции ключевых вызовов в cycle
    pos = {
        "init": cycle.find("_cycle_run_init_pass"),
        "collision": cycle.find("_cycle_run_collision"),
        "promote": cycle.find("wiki_alias_promote.sql"),
        "migrate": cycle.find("wiki_alias_migrate_sep.sql"),
        "solr": cycle.find("solr_synonyms_compile.sql"),
        "A3": cycle.find("wiki_alias_metric_a3.sql"),
    }
    order_ok = all(pos[k] > 0 for k in pos) and (
        pos["init"]
        < pos["collision"]
        < pos["promote"]
        < pos["migrate"]
        < pos["solr"]
        < pos["A3"]
    )
    t(
        "2 порядок init→collision→promote→migrate→solr→A3",
        order_ok,
        str(pos),
    )
    for letter in ("а", "б", "в", "г", "д", "е", "ж"):
        t(
            f"2 фаза {letter} START/END",
            f"_cycle_phase {letter} START" in cycle
            and f"_cycle_phase {letter} END" in cycle,
        )

    # ── 3) PROBE изолирован ─────────────────────────────────────────────────
    t(
        "3 cycle: PROBE_TABLE=${ALIAS_TABLE}_probe",
        'PROBE_TABLE="${ALIAS_TABLE}_probe"' in cycle,
    )
    # В cycle-ветке нет присвоения боевой probe и нет литерала INSERT в неё.
    probe_assign_battle = bool(
        re.search(r'PROBE_TABLE="search_alias_probe"', cycle)
        or re.search(r"PROBE_TABLE=search_alias_probe", cycle)
    )
    t(
        "3 cycle: нет PROBE_TABLE=search_alias_probe",
        not probe_assign_battle,
    )
    t(
        "3 cycle: комментарий/код не пишет в боевую probe как цель",
        "INSERT INTO search_alias_probe" not in cycle
        and "-v probe_table=\"search_alias_probe\"" not in cycle,
    )

    # ── 4) promote fail-closed ──────────────────────────────────────────────
    t(
        "4 BATTLE_TABLE ветка",
        "WIKI_ALIAS_BATTLE_TABLE" in cycle and "WIKI_ALIAS_BATTLE_MEASURE" in cycle,
    )
    t(
        "4 PROMOTE_BATTLE=1 → search_entity_alias",
        'WIKI_ALIAS_PROMOTE_BATTLE:-0}" = "1"' in cycle
        and "BATTLE_E=search_entity_alias" in cycle,
    )
    stop_needle = "promote не выполнен: задай BATTLE_TABLE или PROMOTE_BATTLE=1"
    t("4 стоп без цели: задай BATTLE_TABLE или PROMOTE_BATTLE=1", stop_needle in cycle)
    # red10c-6(а): в одном окне и ABORT, и return 1 (не только текст).
    stop_win = ""
    si = cycle.find(stop_needle)
    if si >= 0:
        stop_win = cycle[max(0, si - 120) : si + len(stop_needle) + 80]
    t(
        "4 стоп без цели: ABORT+return 1 в одном окне",
        "_cycle_phase д ABORT" in stop_win and "return 1" in stop_win,
        stop_win[:200],
    )
    t(
        "4 snap_suffix = суффикс (а)",
        '-v snap_suffix="$CYCLE_SUFFIX"' in cycle
        and "CYCLE_SUFFIX=$(date +%Y%m%d)" in cycle,
    )
    # P3: BATTLE_TABLE=канон боя без PROMOTE_BATTLE → ABORT
    t(
        "P3 BATTLE_TABLE=бой без PROMOTE_BATTLE → ABORT",
        "BATTLE_TABLE указывает на бой — нужен PROMOTE_BATTLE=1" in cycle,
    )

    # ── 5) CEILING / лифт / MAX / стоп без прогресса ─────────────────────────
    t(
        "5 CEILING из COLLISION_ROUNDS",
        'CEILING="${WIKI_ALIAS_COLLISION_ROUNDS:-40}"' in cycle,
    )
    ceil_cmp = cycle.count('[ "$rounds" -lt "$CEILING" ]')
    t(
        "5 оба сравнения while/red5 читают CEILING (ровно 2)",
        ceil_cmp == 2,
        str(ceil_cmp),
    )
    t(
        "5 лифт STEP + MAX",
        'ROUNDS_STEP="${WIKI_ALIAS_ROUNDS_STEP:-40}"' in cycle
        and 'ROUNDS_MAX="${WIKI_ALIAS_ROUNDS_MAX:-400}"' in cycle
        and "CEILING=$((CEILING + ROUNDS_STEP))" in cycle,
    )
    t(
        "5 стоп без прогресса (left / Q=0)",
        "лифт CEILING стоп: нет прогресса" in cycle
        and "лифт CEILING стоп: Q=0" in cycle,
    )
    # red10c-6(в): break в том же блоке, что проверка left>=left_at_window
    no_prog = re.search(
        r'if \[ "\$left" -ge "\$left_at_window" \]; then\n'
        r'[^\n]*\n'
        r'\s*break\n'
        r'\s*fi',
        cycle,
    )
    t(
        "5 стоп лифта «нет прогресса»: break в том же блоке",
        bool(no_prog),
        "block missing break",
    )
    t(
        "5 стоп на MAX",
        "достигнут MAX=" in cycle or "CEILING стоп: достигнут MAX" in cycle,
    )
    # P5: CAP>0 → min(CEILING, CAP)
    t(
        "P5 CAP>0 → CEILING=min(CEILING,CAP)",
        'CEILING=$CAP' in cycle
        and '[ "$CAP" -gt 0 ]' in cycle
        and '[ "$CEILING" -gt "$CAP" ]' in cycle,
    )

    # ── 6) FORCE сброшен до collision; reask выключен ────────────────────────
    # Определение _cycle_run_collision() выше по файлу — ищем ВЫЗОВ после FORCE=0.
    run_fn = cycle.find("wiki_alias_run_cycle()")
    run_body = cycle[run_fn:] if run_fn >= 0 else cycle
    force0 = run_body.find("WIKI_ALIAS_FORCE=0")
    coll_call = run_body.find("_cycle_run_collision", force0 if force0 >= 0 else 0)
    t(
        "6 FORCE=0 до collision",
        force0 > 0 and coll_call > force0,
        f"force0={force0} coll_call={coll_call}",
    )
    t(
        "6 WORKERS=1 после init",
        "FORCE=0 WORKERS=1" in cycle
        or ("WIKI_ALIAS_FORCE=0" in run_body and "WORKERS=1" in run_body[force0:force0 + 80]),
    )
    t(
        "6 reask выключен явно REASK_EVERY=0",
        "REASK_EVERY=0" in cycle
        and "wiki_alias_reask_init.sql" not in cycle,
    )

    # ── 7) нет слов конкретной базы (п.0) ───────────────────────────────────
    # Исторические комментарии tick («okna») не трогаем — смотрим cycle-блок.
    banned = (
        "alias_okna",
        "okna_c5",
        "okna-1",
        "Document_Реализация",
        "Справочник.Номенклатура",
        "bpmonline",
        "ut11",
        "УТ11",
    )
    hits = [w for w in banned if w.lower() in cycle.lower()]
    t("7 cycle: нет имён/слов конкретной базы", not hits, f"hits={hits}")

    # Бюджет / расхождение (план §3) — держим маркеры рядом с фазами.
    t(
        "§3 модельный бюджет → ABORT до promote (left>0)",
        "модельный бюджет" in cycle and "promote не выполняем" in cycle,
    )
    t(
        "§3 бюджет не рвёт готовый черновик (фаза б → гейт г)",
        "бюджет модельных фаз исчерпан; полноту черновика проверит фаза г" in cycle,
    )
    t(
        "§3 расхождение solr/A3 → exit≠0 текст",
        "словарь боя и Solr разошлись" in cycle,
    )
    t(
        "P4 solr skip песочница",
        "solr: пропуск (цель — песочница)" in cycle,
    )
    t(
        "P4 migrate ABORT без Solr",
        'ABORT "migrate_sep rc=$migrate_rc"' in cycle
        and "migrate_sep rc=$migrate_rc — словарь боя и Solr" not in cycle,
    )
    t(
        "P2 fail-closed draft check",
        "не удалось проверить $exists" in cycle
        and "2>/dev/null | tr -d" not in cycle.split("wiki_alias_run_cycle()")[1].split(
            "wiki_alias_init.sql"
        )[0],
    )
    t(
        "P6 б END have=/have_m=",
        "have=$have have_m=$have_m" in cycle,
    )
    t(
        "P6 ж END корзины КАША/ОК/ПРОБЕЛ",
        "КАША=$a3_kasha ОК=$a3_ok ПРОБЕЛ=$a3_prob" in cycle,
    )
    # G1 (red12b-1): нечитаемый collision_left ≠ 0 — fail-closed к promote.
    t(
        "G1 left fail-closed: ABORT + left_read_error",
        '_cycle_phase в ABORT "collision_left не читается' in cycle
        and "left_read_error" in cycle,
    )
    t(
        "G1 нет левена нечитаемого в ноль внутри cycle",
        "left_at_window=0" not in cycle and "*) left=0" not in cycle,
    )
    # G3 (red12b-3): ранний DDL не выполняется в cycle.
    head = body[: body.find("# ── WIKI_ALIAS_MODE=cycle:")]
    t(
        "G3 ранний init.sql gated на MODE=tick",
        '[ "$WIKI_ALIAS_MODE" != "cycle" ] && psql_wa -f "$HERE/wiki_alias_init.sql"' in head,
    )
    # G2 (red12b-2): корзины A3 при сбое разбора — «?», не ноль.
    t(
        "G2 A3 нечитаемое → ?",
        'a3_kasha="?"' in cycle and 'a3_ok="?"' in cycle and 'a3_prob="?"' in cycle,
    )

    print()
    if FAIL:
        print("ИТОГО: %d ok, %d FAIL" % (PASS, len(FAIL)))
        print("FAILED:", ", ".join(FAIL))
        return 1
    print("ИТОГО: %d/0" % PASS)
    return 0


if __name__ == "__main__":
    sys.exit(main())
