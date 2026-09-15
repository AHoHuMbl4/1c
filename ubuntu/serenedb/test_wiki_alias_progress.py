#!/usr/bin/env python3
"""Оффлайн-замок: прогресс-репорт + стоп-при-тишине (plan-progress-stall.md).

Статический разбор wiki_alias.sh и env.example. Без базы, модели и юнитов.
Запуск: python3 ubuntu/serenedb/test_wiki_alias_progress.py
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WIKI = ROOT / "wiki_alias.sh"
ENV = ROOT / "systemd" / "1c-wiki-alias.env.example"
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
    t("wiki_alias.sh exists", WIKI.is_file())
    t("env.example exists", ENV.is_file())
    body = WIKI.read_text(encoding="utf-8") if WIKI.is_file() else ""
    env = ENV.read_text(encoding="utf-8") if ENV.is_file() else ""

    r = subprocess.run(["bash", "-n", str(WIKI)], capture_output=True, text=True)
    t("bash -n wiki_alias.sh", r.returncode == 0, (r.stderr or r.stdout)[:200])

    # ── ручки + умолчания + 0=выкл ──────────────────────────────────────────
    t(
        "REPORT_EVERY default 300",
        'WIKI_ALIAS_REPORT_EVERY_SEC="${WIKI_ALIAS_REPORT_EVERY_SEC:-300}"' in body,
    )
    t(
        "STALL default 8100",
        'WIKI_ALIAS_STALL_SEC="${WIKI_ALIAS_STALL_SEC:-8100}"' in body,
    )
    t(
        "POLL default 10",
        'WIKI_ALIAS_POLL_SEC="${WIKI_ALIAS_POLL_SEC:-10}"' in body,
    )
    t(
        "санитайз non-digit → умолчания",
        "WIKI_ALIAS_REPORT_EVERY_SEC=300;;" in body
        and "WIKI_ALIAS_STALL_SEC=8100;;" in body
        and "WIKI_ALIAS_POLL_SEC=10;;" in body,
    )
    t(
        "0=выкл: REPORT/STALL гейтят наблюдателя",
        '[ "$WIKI_ALIAS_REPORT_EVERY_SEC" -gt 0 ] || [ "$WIKI_ALIAS_STALL_SEC" -gt 0 ]'
        in body,
    )
    t(
        "STALL формула 1.5 × (retry+1) × ALIAS_AGENT_TIMEOUT_SEC",
        "1.5 × (retry+1) × ALIAS_AGENT_TIMEOUT_SEC" in body
        and "1.5 × (retry+1) × ALIAS_AGENT_TIMEOUT_SEC" in env,
    )
    t(
        "env.example: REPORT_EVERY=300 + 0=выкл",
        "WIKI_ALIAS_REPORT_EVERY_SEC=300" in env and "0 = выкл" in env,
    )
    t(
        "env.example: STALL_SEC=8100 + смысл",
        "WIKI_ALIAS_STALL_SEC=8100" in env
        and "ALIAS_AGENT_TIMEOUT_SEC" in env,
    )

    # ── писатели ent/meas/coll ──────────────────────────────────────────────
    t(
        "писатель ent_$w",
        'WA_PROGRESS_FILE="$TMP/.progress_ent_$w"' in body
        and 'wa_progress_write "$WA_PROGRESS_FILE"' in body
        and '"ent"' in body,
    )
    t(
        "писатель meas",
        'wa_progress_write "$TMP/.progress_meas"' in body
        and body.count('"$TMP/.progress_meas"') >= 2,
    )
    t(
        "писатель col_$iq",
        'WA_PROGRESS_FILE="$TMP/.progress_col_$iq"' in body
        and body.count('"$TMP/.progress_col_$iq"') >= 2,
    )

    # ── infer-heartbeat ─────────────────────────────────────────────────────
    infer_fn = body.split("wa_infer_field()", 1)
    t("wa_infer_field объявлен", len(infer_fn) == 2)
    infer_body = infer_fn[1].split("\n}\n", 1)[0] if len(infer_fn) == 2 else ""
    t(
        "heartbeat перед попыткой infer:<field>",
        'wa_progress_write "$WA_PROGRESS_FILE"' in infer_body
        and '"infer:$field"' in infer_body
        and "for attempt in 0 1 2" in infer_body,
    )
    # heartbeat внутри цикла попыток, до gateway
    att = infer_body.find("for attempt in 0 1 2")
    hb = infer_body.find('"infer:$field"', att if att >= 0 else 0)
    gw = infer_body.find("alias_infer_gateway.py", hb if hb >= 0 else 0)
    t(
        "heartbeat внутри for attempt, до gateway",
        att >= 0 and hb > att and gw > hb,
        f"att={att} hb={hb} gw={gw}",
    )

    # ── метки немодельных фаз ───────────────────────────────────────────────
    for lab in (
        "ddl",
        "sel",
        "pub",
        "promote",
        "migrate",
        "solr",
        "branch",
        "a3",
        "dayfork",
    ):
        t(
            f"метка немодельной фазы {lab}",
            f'"{lab}"' in body and "wa_progress_write" in body,
            "missing quote-label near progress",
        )
        # точная форма метки в третьем аргументе
        t(
            f"wa_progress_write … \"{lab}\"",
            bool(re.search(rf'wa_progress_write\s+"[^"]+"\s+\S+\s+"{lab}"', body)),
        )

    # ── один наблюдатель; seed; POLL≠REPORT; TERM; trap; старт/финал ────────
    t(
        "один фоновый наблюдатель (_PROGRESS_OBS_PID)",
        "_PROGRESS_OBS_PID=$!" in body
        and body.count("_PROGRESS_OBS_PID=$!") == 1,
    )
    t(
        "seed t_start (max_ts / (seed))",
        "_pg_max_ts=$t_start" in body
        and '_pg_last_lab="(seed)"' in body
        and "[ \"$max_ts\" -lt \"$t_start\" ] && max_ts=$t_start" in body,
    )
    t(
        "POLL отдельный от REPORT (sleep POLL)",
        'sleep "$WIKI_ALIAS_POLL_SEC"' in body
        and 'WIKI_ALIAS_REPORT_EVERY_SEC' in body
        and 'WIKI_ALIAS_POLL_SEC' in body,
    )
    t(
        "TERM/KILL через setsid-киллер (не одиночный TERM $PPID)",
        "setsid bash -c" in body
        and "стоп-при-тишине:" in body
        and 'kill -TERM "$PPID"' not in body
        and "_stall_main=$$" in body,
    )
    t(
        "setsid-киллер: TERM группе (минус-PGID)",
        'kill -TERM -- -"$pgid"' in body
        and "(TERM группе" in body,
    )
    t(
        "KILL_GRACE_SEC default 15 + санитайз",
        'WIKI_ALIAS_KILL_GRACE_SEC="${WIKI_ALIAS_KILL_GRACE_SEC:-15}"' in body
        and "WIKI_ALIAS_KILL_GRACE_SEC=15;;" in body,
    )
    t(
        "эскалация KILL после паузы grace",
        'sleep "$grace"' in body
        and 'kill -KILL -- -"$pgid"' in body
        and "(KILL группе" in body,
    )
    t(
        "env.example: KILL_GRACE_SEC=15",
        "WIKI_ALIAS_KILL_GRACE_SEC=15" in env,
    )
    t(
        "чужая PGID → дерево /proc-детей (не чужая группа)",
        '[ "$pgid" = "$main" ]' in body
        and 'task/*/children' in body
        and "wa_kill_tree" in body,
    )
    t(
        "trap EXIT гасит наблюдателя + финальный репорт",
        "trap '_wiki_alias_on_exit' EXIT" in body
        and "kill \"$_PROGRESS_OBS_PID\"" in body
        and 'wa_progress_report "финал"' in body
        and 'rm -rf "$TMP"' in body,
    )
    _fin = re.search(r'wa_progress_report\s+"финал"[^\n]*', body)
    t(
        "финал: вызов НЕ подавлен (нет 2>/dev/null)",
        _fin is not None and "2>/dev/null" not in _fin.group(0),
        (_fin.group(0) if _fin else "нет вызова финал")[:240],
    )
    # reask-select: метка sel до SELECT пачки (как measure).
    _reask_sel = body.find("wiki_alias_reask_select_entity_batch.sql")
    _reask_write = body.rfind(
        'wa_progress_write "$TMP/.progress_main"', 0, _reask_sel if _reask_sel >= 0 else 0
    )
    t(
        "reask: sel перед select пачки",
        _reask_sel > 0
        and _reask_write >= 0
        and '"sel"' in body[_reask_write:_reask_sel],
        f"write={_reask_write} sel_sql={_reask_sel}",
    )
    t(
        "репорт на старте",
        'wa_progress_report "старт"' in body,
    )
    t(
        "атомарная запись >tmp && mv",
        'printf \'%s\\t%s\\t%s\\n\' "$now" "$c" "$lab" > "${f}.tmp" && mv -f "${f}.tmp" "$f"'
        in body
        or (
            '>"${f}.tmp"' in body.replace(" ", "")
            and 'mv -f "${f}.tmp" "$f"' in body
        ),
    )
    # атомарность — проще
    t(
        "wa_progress_write: .tmp && mv",
        ".tmp" in body
        and 'mv -f "${f}.tmp" "$f"' in body,
    )
    t(
        "наблюдатель до cycle/tick работы (после TMP)",
        body.find("TMP=$(mktemp") < body.find("_PROGRESS_OBS_PID=$!")
        and body.find("_PROGRESS_OBS_PID=$!")
        < body.find('if [ "$WIKI_ALIAS_MODE" = "cycle" ]; then'),
    )
    t(
        "DDL tick после наблюдателя",
        body.find("_PROGRESS_OBS_PID=$!")
        < body.find(
            '[ "$WIKI_ALIAS_MODE" != "cycle" ] && psql_wa -f "$HERE/wiki_alias_init.sql"'
        ),
    )
    t(
        "collision_left из echo-файла (не новый psql в репорте)",
        ".collision_left_echo" in body
        and "collision_left" in body
        and "wa_progress_report" in body,
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
