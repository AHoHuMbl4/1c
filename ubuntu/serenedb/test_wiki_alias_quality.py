#!/usr/bin/env python3
"""Оффлайн-замок: авто-отчёт качества init (plan-quality-report.md v2).

Статический разбор wiki_alias_quality_report.sql / wiki_alias.sh / deploy.
Без базы, модели и юнитов.
Запуск: python3 ubuntu/serenedb/test_wiki_alias_quality.py
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WIKI = ROOT / "wiki_alias.sh"
SQL = ROOT / "wiki_alias_quality_report.sql"
DEPLOY = ROOT / "deploy_wiki_alias.sh"
PASS, FAIL = 0, []

KEYS = (
    "entities",
    "empty_aliases",
    "empty_best",
    "empty_nef",
    "measures",
    "measures_nonempty",
    "measure_tokens",
    "need_event",
    "has_event",
    "event_gap",
)

# Целые слова / лексемы фикстуры — в детекторе аффиксов быть не должны (инверсия).
WHOLE_WORDS = (
    "продали",
    "купили",
    "сделали",
    "отгрузили",
    "дай",
    "бей",
    "возьми",
    "наторговали",
)


def t(name: str, cond: bool, detail: str = "") -> None:
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + detail[:240]) if detail else "")


def _split_cycle_tick(body: str) -> tuple[str, str]:
    m = re.search(
        r"if \[ \"\$WIKI_ALIAS_MODE\" = \"cycle\" \]; then\n"
        r"  wiki_alias_run_cycle\n"
        r"  exit \$\?\n"
        r"fi\n",
        body,
    )
    if not m:
        return "", body
    start = body.find("# ── WIKI_ALIAS_MODE=cycle:")
    if start < 0:
        start = body.find("wiki_alias_run_cycle()")
    cycle = body[start : m.end()] if start >= 0 else body[: m.end()]
    tick = body[m.end() :]
    return cycle, tick


def _affixes_from_sql(sql: str) -> list[str]:
    """Аффиксы из комментария «-али -или …» (ведущий минус = незавершённая форма)."""
    m = re.search(
        r"эвристика event-аффиксов[^:\n]*:\s*((?:-\S+\s*)+)",
        sql,
    )
    if not m:
        return []
    raw = re.findall(r"-([A-Za-zА-Яа-яЁё]+)", m.group(1))
    return [a for a in raw if len(a) >= 3]


def main() -> int:
    t("quality SQL exists", SQL.is_file())
    t("wiki_alias.sh exists", WIKI.is_file())
    sql = SQL.read_text(encoding="utf-8") if SQL.is_file() else ""
    body = WIKI.read_text(encoding="utf-8") if WIKI.is_file() else ""
    deploy = DEPLOY.read_text(encoding="utf-8") if DEPLOY.is_file() else ""

    r = subprocess.run(["bash", "-n", str(WIKI)], capture_output=True, text=True)
    t("bash -n wiki_alias.sh", r.returncode == 0, (r.stderr or r.stdout)[:200])

    # ── SQL: параметры, канон, без имён базы ───────────────────────────────
    t("SQL: -v alias_table (плейсхолдер :alias_table)", ":alias_table" in sql)
    t("SQL: -v measure_table (плейсхолдер :measure_table)", ":measure_table" in sql)
    t(
        "SQL: канон regexp_split_to_array ',| [|] '",
        "regexp_split_to_array" in sql and ",| [|] " in sql,
    )
    t(
        "SQL: потоки через search_refcols EXISTS",
        "search_refcols" in sql and "EXISTS" in sql and "target_src" in sql,
    )
    t("SQL: эвристика в комментарии", "эвристика" in sql)
    t(
        "SQL: одна команда SELECT (конкатенация key=value)",
        sql.count("SELECT 'entities='") == 1 and "FROM base" in sql,
    )
    for bad in (
        "search_entity_alias",
        "search_measure_alias",
        "alias_okna",
        "okna",
        "wa_p4_",
    ):
        # «okna» в комментарии к докам не ожидаем; имена боевых таблиц — запрет.
        if bad == "okna":
            t(
                f"SQL: нет имени базы «{bad}»",
                not re.search(r"\bokna\b", sql, re.I),
            )
        else:
            t(f"SQL: нет имени «{bad}»", bad not in sql)

    # Ключи кортежа — в конкатенации по порядку (printf с BIGINT в SereneDB
    # падает «invalid format specifier» — живая проба 15.09; канон — || с кастами).
    fmt_s = sql
    t("SQL: строка key=value конкатенацией", "'entities=' ||" in sql and "::VARCHAR" in sql)
    for k in KEYS:
        t(f"SQL: ключ {k}=", f"' {k}=' ||" in sql or f"'{k}=' ||" in sql)
    # Порядок ключей
    positions = [fmt_s.find(f"{k}=") for k in KEYS]
    t(
        "SQL: порядок ключей кортежа",
        all(p >= 0 for p in positions) and positions == sorted(positions),
        str(positions),
    )
    t("SQL: нет elapsed в строке", "elapsed" not in fmt_s)

    # ── аффикс-детектор ────────────────────────────────────────────────────
    aff = _affixes_from_sql(sql)
    t("аффиксы: комментарий с ведущим «-» разобран", len(aff) >= 4, str(aff))
    t(
        "аффиксы: все элементы — незавершённые формы (минус + len≥3)",
        all(len(a) >= 3 for a in aff) and len(aff) > 0,
        str(aff),
    )
    whole_hit = [w for w in WHOLE_WORDS if w in aff or f"|{w}|" in sql or f"|{w})" in sql or f"({w}|" in sql]
    # Также целый токен в regex без якоря-суффикса списка: ищем альтернативы regex.
    rx = re.search(r"~\s*'\(([^']+)\)\$'", sql)
    alts = rx.group(1).split("|") if rx else []
    t("аффиксы: regex-суффикс $ совпадает с комментарием", set(alts) == set(aff), f"alts={alts} aff={aff}")
    whole_in_alts = [w for w in WHOLE_WORDS if w in alts]
    t(
        "аффиксы: нет целых слов (инверсия продали/дай/…)",
        not whole_hit and not whole_in_alts,
        f"hit={whole_hit or whole_in_alts}",
    )
    # Инверсия критерия: если бы в списке было целое слово — замок красный.
    t(
        "аффиксы: критерий инверсии (целое слово → fail)",
        "продали" not in alts and "продали" not in aff,
    )
    t(
        "аффиксы: «продали» матчится окончанием али (поверхность)",
        any("продали".endswith(a) for a in aff),
        str(aff),
    )
    t(
        "аффиксы: форма длиннее суффикса (length(trim(tok)) > 3)",
        "length(trim(tok)) > 3" in sql,
    )

    # ── sh: функция, оба режима, префикс, ABORT, heartbeat ─────────────────
    t("sh: wa_quality_report()", "wa_quality_report()" in body)
    t(
        "sh: SQL-файл wiki_alias_quality_report.sql",
        "wiki_alias_quality_report.sql" in body,
    )
    t(
        "sh: heartbeat quality до SQL",
        'wa_progress_write "$TMP/.progress_main" 0 "quality"' in body,
    )
    fn = ""
    fi = body.find("wa_quality_report()")
    if fi >= 0:
        fn = body[fi : body.find("\n}\n", fi) + 3]
    t(
        "sh: префикс «отчёт качества init:»",
        "отчёт качества init:" in fn,
    )
    t(
        "sh: ABORT-ветка fail-closed",
        "ABORT (сбой SQL" in fn and "return 1" in fn,
        fn[:200],
    )
    t(
        "sh: ABORT печатает stderr SQL (head -c 120 → $err)",
        "head -c 120" in fn
        and "$err" in fn
        and re.search(r'ABORT \(сбой SQL: \$err\)', fn) is not None,
        fn[:280],
    )
    t("sh: вывод в stderr", ">&2" in fn)

    cycle, tick = _split_cycle_tick(body)
    t(
        "tick: вызов wa_quality_report до wa_probe_purge",
        "wa_quality_report" in tick
        and tick.find("wa_quality_report") < tick.find("wa_probe_purge"),
    )
    t(
        "tick: exit 1 при сбое отчёта",
        "if ! wa_quality_report; then" in tick and "exit 1" in tick[tick.find("wa_quality_report") : tick.find("wa_probe_purge") + 1],
    )
    t(
        "cycle: вызов после б END, до в START",
        "wa_quality_report" in cycle
        and cycle.find("_cycle_phase б END")
        < cycle.find("wa_quality_report")
        < cycle.find("_cycle_phase в START"),
    )
    t(
        "cycle: return 1 при сбое отчёта",
        "if ! wa_quality_report; then" in cycle
        and "return 1" in cycle[cycle.find("wa_quality_report") : cycle.find("_cycle_phase в START")],
    )

    # ── deploy ─────────────────────────────────────────────────────────────
    t(
        "deploy FILES += wiki_alias_quality_report.sql",
        "wiki_alias_quality_report.sql" in deploy,
    )

    print(f"\n{PASS} ok, {len(FAIL)} fail")
    if FAIL:
        print("FAILED:", ", ".join(FAIL))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
