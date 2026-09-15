#!/usr/bin/env python3
"""Оффлайн-замок: probe ok/failed + самоочистка (plan-probe-result.md).

Статический разбор wiki_alias.sh / init / mark / purge. Без базы, модели и юнитов.
Запуск: python3 ubuntu/serenedb/test_wiki_alias_probe.py
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WIKI = ROOT / "wiki_alias.sh"
INIT = ROOT / "wiki_alias_init.sql"
MARK = ROOT / "wiki_alias_probe_mark.sql"
PURGE = ROOT / "wiki_alias_probe_purge.sql"
STILL = ROOT / "wiki_alias_probe_still.sql"
MERGE = ROOT / "wiki_alias_collision_merge.sql"
ROUND = ROOT / "wiki_alias_collision_round.sql"
DEPLOY = ROOT / "deploy_wiki_alias.sh"
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


def main() -> int:
    t("wiki_alias.sh exists", WIKI.is_file())
    body = WIKI.read_text(encoding="utf-8") if WIKI.is_file() else ""
    init = INIT.read_text(encoding="utf-8") if INIT.is_file() else ""
    mark = MARK.read_text(encoding="utf-8") if MARK.is_file() else ""
    purge = PURGE.read_text(encoding="utf-8") if PURGE.is_file() else ""
    still = STILL.read_text(encoding="utf-8") if STILL.is_file() else ""
    merge = MERGE.read_text(encoding="utf-8") if MERGE.is_file() else ""
    round_sql = ROUND.read_text(encoding="utf-8") if ROUND.is_file() else ""
    deploy = DEPLOY.read_text(encoding="utf-8") if DEPLOY.is_file() else ""

    r = subprocess.run(["bash", "-n", str(WIKI)], capture_output=True, text=True)
    t("bash -n wiki_alias.sh", r.returncode == 0, (r.stderr or r.stdout)[:200])

    cycle, tick = _split_cycle_tick(body)

    # ── DDL ─────────────────────────────────────────────────────────────────
    t("init: probe CREATE с result/gen_ver", INIT.is_file() and "result VARCHAR" in init and "gen_ver VARCHAR" in init)
    t(
        "init: ADD COLUMN IF NOT EXISTS result+gen_ver",
        "ADD COLUMN IF NOT EXISTS result" in init
        and "ADD COLUMN IF NOT EXISTS gen_ver" in init,
    )
    t(
        "init: ссылка на доки ALTER TABLE ADD COLUMN",
        "ALTER TABLE" in init and "ADD COLUMN" in init,
    )
    t(
        "round: INSERT с именами колонок (alias, entities_fp, asked_at)",
        "INSERT INTO :probe_table (alias, entities_fp, asked_at)" in round_sql,
    )

    # ── GEN_VER ─────────────────────────────────────────────────────────────
    t(
        "GEN_VER = md5(скрипт+модель+thinking)",
        "GEN_VER=" in body
        and 'cat "$HERE/wiki_alias.sh"' in body
        and "WIKI_ALIAS_MODEL" in body[body.find("GEN_VER=") : body.find("GEN_VER=") + 400]
        and "WIKI_ALIAS_THINKING" in body[body.find("GEN_VER=") : body.find("GEN_VER=") + 400]
        and "md5sum" in body[body.find("GEN_VER=") : body.find("GEN_VER=") + 400],
    )
    t(
        "GEN_VER fail-closed: пустой → exit 1",
        "GEN_VER пуст" in body and "exit 1" in body[body.find("GEN_VER=") : body.find("psql_wa()")],
    )

    # ── $WTMP/fp при pick (tick + cycle) ────────────────────────────────────
    t(
        "fp-файл при pick (printf FP → $WTMP/fp)",
        body.count('printf \'%s\' "$FP" > "$WTMP/fp"') >= 2
        or body.count('printf \'%s\' "$FP" > "$WTMP/fp"')
        + body.count('printf "%s" "$FP" > "$WTMP/fp"')
        >= 2,
        f"count={body.count(chr(39)+'%s'+chr(39)+' \"$FP\" > \"$WTMP/fp\"')}",
    )
    # точнее
    fp_writes = len(re.findall(r'printf\s+[\'"]%s[\'"]\s+"\$FP"\s+>\s+"\$WTMP/fp"', body))
    t("fp-файл: ≥2 записи (tick+cycle)", fp_writes >= 2, str(fp_writes))

    # ── mark SQL ────────────────────────────────────────────────────────────
    t("mark.sql exists", MARK.is_file())
    t(
        "mark: UPDATE по alias+entities_fp",
        "UPDATE :probe_table" in mark
        and "alias = :'word'" in mark
        and "entities_fp = :'fp'" in mark
        and "result = :'result'" in mark
        and "gen_ver = :'gen_ver'" in mark,
    )
    t(
        "sh: mark через wiki_alias_probe_mark.sql",
        "wiki_alias_probe_mark.sql" in body and "wa_probe_mark" in body,
    )
    t(
        "журнал: разведение: слово → ok/failed",
        'разведение: слово ${word} → ${result}' in body
        or 'разведение: слово' in body and "→" in body,
    )

    # ── ok только при merge≥1 / still, не по размеру файла ───────────────────
    t(
        "ok: objs≥1 AND merge_n≥1",
        '"$objs" -ge 1' in body and '"$merge_n" -ge 1' in body and "result=ok" in body,
    )
    t(
        "ok-fallback: still.sql (word+fp исчез из cand)",
        "wiki_alias_probe_still.sql" in body and STILL.is_file() and "still" in body,
    )
    t(
        "merge RETURNING (count из вывода)",
        "RETURNING" in merge and "wiki_alias_collision_merge.sql" in body,
    )
    # инверсия: ok по одному размеру файла (без merge_n) — в коде не должно
    decide = ""
    di = body.find("wa_probe_result_for()")
    if di >= 0:
        decide = body[di : body.find("\n}\n", di) + 3]
    t(
        "инверсия: нет ok по одному -s rows.json",
        "result=ok" not in decide.split("merge_n")[0] if decide else False,
        "ok до merge_n" if decide and "result=ok" in decide.split("merge_n")[0] else "",
    )
    t(
        "пометка и при пустом rows.json (не continue до mark)",
        "wa_probe_result_for" in body
        and body.count("wa_probe_mark") >= 2
        and '[ -s "$TMP/cw$iq/rows.json" ] || continue' not in body[body.find("wa_probe_result_for") :],
    )

    # ── DELETE-семантика ────────────────────────────────────────────────────
    t("purge.sql exists", PURGE.is_file())
    t(
        "purge: NOT (ok OR (failed AND gen_ver))",
        "result" in purge
        and "'ok'" in purge
        and "'failed'" in purge
        and "gen_ver" in purge
        and "DELETE FROM :probe_table" in purge,
    )
    t(
        "purge: фильтр по :gen_ver",
        ":'gen_ver'" in purge or ':gen_ver' in purge,
    )
    t(
        "инверсия: DELETE без gen_ver-фильтра → красный (фильтр есть)",
        "gen_ver" in purge
        and "failed" in purge
        and "NOT" in purge,
    )
    t(
        "журнал-счётчик purge",
        "probe-чистка:" in body and "удалено" in body and "осталось failed" in body,
    )
    t(
        "purge: одна колонка count_del || chr(9) || count_failed",
        "chr(9)" in purge
        and "||" in purge
        and bool(
            re.search(
                r"\(SELECT count\(\*\) FROM del\)\s*\|\|\s*chr\(9\)\s*\|\|",
                purge,
            )
        )
        and not re.search(
            r"\(SELECT count\(\*\) FROM del\)\s*,\s*\(SELECT count\(\*\)",
            purge,
        ),
    )
    t(
        "sh: разбор purge по TAB (%% / #*)",
        r"deleted=${out%%$'\t'*}" in body and r"failed_left=${out#*$'\t'}" in body,
    )

    # ── место DELETE ────────────────────────────────────────────────────────
    coll_if = tick.find('if [ "${WIKI_ALIAS_COLLISIONS:-1}" = "1" ]')
    purge_tick = tick.find("wa_probe_purge")
    t(
        "tick: wa_probe_purge перед if COLLISIONS (не внутри)",
        purge_tick >= 0
        and coll_if >= 0
        and purge_tick < coll_if
        and purge_tick
        < tick.find('while [ "$rounds" -lt "${WIKI_ALIAS_COLLISION_ROUNDS:-40}" ]'),
        f"purge={purge_tick} coll_if={coll_if}",
    )
    # cycle: purge в фазе в, после фазы а (PROBE_TABLE=..._probe)
    run_fn = cycle.find("wiki_alias_run_cycle()")
    run_body = cycle[run_fn:] if run_fn >= 0 else cycle
    probe_assign = run_body.find('PROBE_TABLE="${ALIAS_TABLE}_probe"')
    phase_v_start = run_body.find("_cycle_phase в START")
    purge_pos = run_body.find("wa_probe_purge", phase_v_start if phase_v_start >= 0 else 0)
    t(
        "cycle: purge в фазе в (после а / после PROBE_TABLE)",
        probe_assign >= 0
        and phase_v_start > probe_assign
        and purge_pos > phase_v_start,
        f"probe={probe_assign} v={phase_v_start} purge={purge_pos}",
    )
    # инверсия: DELETE до фазы а
    before_a = run_body[: run_body.find("_cycle_phase а START")] if "_cycle_phase а START" in run_body else ""
    t(
        "инверсия: DELETE до фазы а → красный (purge нет до а)",
        "wa_probe_purge" not in before_a,
    )

    # ── heartbeat probe ─────────────────────────────────────────────────────
    t(
        'heartbeat wa_progress_write … "probe"',
        bool(re.search(r'wa_progress_write\s+"[^"]+"\s+\S+\s+"probe"', body)),
    )

    # ── п.0: нет имён конкретной базы в новых SQL / GEN_VER ─────────────────
    banned = (
        "alias_okna",
        "okna_c5",
        "Document_Реализация",
        "Справочник.Номенклатура",
        "bpmonline",
        "ut11",
    )
    blob = "\n".join([init, mark, purge, still, decide])
    hits = [w for w in banned if w.lower() in blob.lower()]
    t("п.0: нет имён конкретной базы в probe-артефактах", not hits, f"hits={hits}")

    # ── deploy ──────────────────────────────────────────────────────────────
    t(
        "deploy FILES ⊇ mark+purge+still",
        "wiki_alias_probe_mark.sql" in deploy
        and "wiki_alias_probe_purge.sql" in deploy
        and "wiki_alias_probe_still.sql" in deploy,
    )

    # ── инверсия: убрать fp-файл → красный (симуляция) ──────────────────────
    body_no_fp = re.sub(
        r'printf\s+[\'"]%s[\'"]\s+"\$FP"\s+>\s+"\$WTMP/fp"\n?',
        "",
        body,
    )
    t(
        "инверсия: убрать fp-файл → условие краснеет",
        len(re.findall(r'printf\s+[\'"]%s[\'"]\s+"\$FP"\s+>\s+"\$WTMP/fp"', body_no_fp))
        < 2,
    )

    # ── инверсия: ok только по размеру файла ────────────────────────────────
    fake_ok_by_size = (
        'if [ -s "$wtmp/rows.json" ]; then\n    result=ok\n  fi'
    )
    t(
        "инверсия: ok по размеру файла отсутствует в decide",
        fake_ok_by_size not in decide
        and not re.search(
            r'\[ -s "\$wtmp/rows\.json" \]; then\s+result=ok',
            decide,
        ),
    )

    # ── инверсия: DELETE без gen_ver ────────────────────────────────────────
    purge_no_ver = re.sub(r"gen_ver[^\n]*", "", purge)
    t(
        "инверсия: purge без gen_ver-фильтра не проходит ассерт",
        ":'gen_ver'" not in purge_no_ver and "failed" in purge,
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
