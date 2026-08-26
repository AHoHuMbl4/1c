#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Офлайн-замок И2а: правила docs/ACCEPTANCE_OKNA_LIVE.md в run_okna_live.py.

Без сети и без базы. Проверяет:
  1) «сегодня» — Europe/Chisinau против UTC, окно 00:00–03:00;
  2) верхняя граница today+1 в эталонах открытых периодов;
  3) приём числа с разрядкой/валютой и отказ от подмены дня (пн-«вчера» ≠ пт);
  4) ничья в топ-3 принимается с оговоркой;
  5) контрольные числа 19.08 не зашиты в раннере (только в спеке / списке замка).

Порча копии: те же проверки на заведомо сломанной реализации — замок краснеет
(числа fail до/после).
"""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RUNNER = REPO / "work" / "acceptance" / "run_okna_live.py"

PASS = 0
FAIL: list[str] = []

# Контрольные числа спека §C / таблиц B на 19.08 — только здесь и в спеке,
# не в раннере (docs/ACCEPTANCE_OKNA_LIVE.md).
CONTROL_19_08 = frozenset({
    "49155.96", "49155,96", "49 155,96", "49 155.96",
    "693688.38", "693688,38", "693 688,38",
    "479710.42", "479710,42", "479 710,42",
    "1222554.76", "1 222 554,76", "1222554,76",
    "445660.89", "445 660,89", "445660,89",
    "3306225.01", "3 306 225,01", "3306225,01",
    "2767450.98", "2 767 450,98", "2767450,98",
    "2798536.20", "2 798 536,20", "2798536,20",
    "1489612.94", "1 489 612,94", "1489612,94",
    "844394.27", "844 394,27",
    "134757.70", "134 757,70",
    "75405.91", "75 405,91",
    "52825.25", "52 825,25",
    "119847.15", "119 847,15",
    "6797.25", "6 797,25",
    "1944", "1884",
    "125646.31",
})


def runner_source_has_control_numbers(source: str) -> list[str]:
    """Любой литерал §C в теле раннера — дефект (числа только в спеке)."""
    import re
    found = []
    for num in CONTROL_19_08:
        if re.search(re.escape(num), source):
            # комментарий «не хранятся / только в спеке» — не литерал эталона
            for m in re.finditer(re.escape(num), source):
                window = source[max(0, m.start() - 80): m.start() + 80]
                if "не хранятся" in window or "только в спеке" in window:
                    continue
                found.append(num)
                break
    return found


def t(name: str, cond: bool, detail: str = "") -> None:
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + str(detail)[:220]) if detail else "")


def load_runner(path: Path, modname: str = "run_okna_live_under_test"):
    spec = importlib.util.spec_from_file_location(modname, str(path))
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    # dataclass смотрит sys.modules[cls.__module__] при создании класса
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod


def run_suite(R, label: str) -> tuple[int, int, list[str]]:
    """Возвращает (pass, fail_count, fail_names). Не пишет в глобальный счётчик."""
    ok = 0
    fails: list[str] = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        nonlocal ok
        full = "%s: %s" % (label, name)
        if cond:
            ok += 1
        else:
            fails.append(full)
            if detail:
                fails[-1] = full + " | " + str(detail)[:160]

    # ── 1. «сегодня» Кишинёв vs UTC, окно 00:00–03:00 (A1) ──────────────────
    check(
        "SQL today = timezone('Europe/Chisinau', now())::date",
        R.today_sql_fragment() == "timezone('Europe/Chisinau', now())::date",
        R.today_sql_fragment(),
    )
    # 26.08 01:30 Кишинёв = 25.08 22:30 UTC (EEST UTC+3)
    when = datetime(2026, 8, 25, 22, 30, tzinfo=timezone.utc)
    split = R.utc_vs_chisinau_split(when)
    check("окно split: in_split_window", split["in_split_window"] is True, split)
    check("окно split: даты разошлись", split["split"] is True, split)
    check(
        "chisinau_today в окне = 26.08, не UTC 25.08",
        R.chisinau_today(when).isoformat() == "2026-08-26"
        and split["utc_date"].isoformat() == "2026-08-25",
        (R.chisinau_today(when), split["utc_date"]),
    )
    # Днём расхождения нет
    day = datetime(2026, 8, 26, 10, 0, tzinfo=timezone.utc)  # 13:00 Кишинёв
    day_split = R.utc_vs_chisinau_split(day)
    check(
        "днём split-окна нет",
        day_split["in_split_window"] is False
        and R.chisinau_today(day).isoformat() == "2026-08-26",
        day_split,
    )

    # ── 2. верхняя граница today+1 (A5.3) ────────────────────────────────────
    open_ok = True
    for q in R.QUESTIONS:
        if q.period in R.open_period_kinds() or q.kind in ("unsold", "compare", "furniture"):
            if q.kind == "furniture":
                sqls = R.build_etalon_sql(q)
                if not any(R.sql_has_today_plus_one(s) for s in sqls):
                    open_ok = False
                    break
            elif not R.period_sql_uses_today_plus_one(q):
                open_ok = False
                break
    check("открытые периоды: today.d + INTERVAL 1 day", open_ok)

    # закрытый «вчера» — верхней границы today+1 в hi быть не должно как конца периода
    y = next(q for q in R.QUESTIONS if q.period == "yesterday")
    ysql = R.build_etalon_sql(y)[0]
    # у вчера hi = today.d (без +1); в SQL CTE today есть, но doc_date < today.d
    check(
        "вчера: верх = today.d, не today+1 как конец периода",
        "doc_date < today.d" in ysql.replace(" ", "")
        or "doc_date < today.d;" in ysql
        or "doc_date < today.d\n" in ysql
        or "AND doc_date < today.d" in ysql,
        ysql[:200],
    )
    check(
        "вчера: нет doc_date < today.d + INTERVAL 1 day",
        "doc_date < today.d + INTERVAL 1 day" not in ysql,
        ysql[:200],
    )

    # ── 3. число с разрядкой/валютой; подмена дня ────────────────────────────
    check(
        "разрядка «49 155,96» = 49155.96",
        R.number_in_answer("Вчера продали на 49 155,96 лей", 49155.96),
    )
    check(
        "валютный хвост не мешает",
        R.number_in_answer("Итого 479\u00a0710.42 MDL", 479710.42),
    )
    check(
        "чужое число не принимается",
        not R.number_in_answer("Продали 12 345,00", 49155.96),
    )
    # пн «вчера» = вс = 0; ответ с пятницей без оговорки — подмена
    fri = 125646.31
    sub = R.looks_like_day_substitution(
        "Вчера продали на 125 646,31 лей",
        etalon_zero=True,
        friday_value=fri,
    )
    check("подмена дня: пн→пт без оговорки ловится", sub is True)
    honest = R.looks_like_day_substitution(
        "В воскресенье продаж не было (выходной). В пятницу было 125 646,31",
        etalon_zero=True,
        friday_value=fri,
    )
    check("честный ноль с оговоркой — не подмена", honest is False)
    q_sun = next(q for q in R.QUESTIONS if q.kind == "sunday_zero")
    et0 = R.Etalon(raw=0.0, display="0", meta={"friday_value": fri})
    v_bad = R.accept_answer(
        q_sun, et0, "В воскресенье наторговали 125 646,31", kind="answer")
    check("sunday_zero: подмена → fail", v_bad.ok is False, v_bad.how)
    v_good = R.accept_answer(
        q_sun, et0, "В воскресенье продаж не было — 0, выходной", kind="answer")
    check("sunday_zero: честный ноль → ok", v_good.ok is True, v_good.how)

    # прошлое: отгружено
    q_ship = next(q for q in R.QUESTIONS if q.kind == "period_shipped")
    et_s = R.Etalon(
        raw=2767450.98,
        meta={"net": 2767450.98, "shipped": 2798536.20},
    )
    v_ship = R.accept_answer(
        q_ship, et_s,
        "В прошлом месяце отгружено 2 798 536,20 лей",
        kind="answer",
    )
    check("прошлый месяц: «отгружено» принято", v_ship.ok is True, v_ship.how)
    v_net = R.accept_answer(
        q_ship, et_s,
        "Всего чистыми 2 767 450,98",
        kind="answer",
    )
    check("прошлый месяц: чистыми принято", v_net.ok is True, v_net.how)

    # ── 4. ничья в топ-3 ─────────────────────────────────────────────────────
    # лидер 115, затем пять по 106 — любые две из пяти + оговорка
    rows = [
        ("Piesa inchidere toc HG VEKA 0,5 mm / 1 / x", 115.0),
        ("Capac balama cercevea sus alb / 2 / x", 106.0),
        ("Capac balama toc sus alb / 3 / x", 106.0),
        ("Capac lung balama toc jos alb / 4 / x", 106.0),
        ("Capac scurt balama toc jos alb / 5 / x", 106.0),
        ("Capac balama cercevea jos alb / 6 / x", 106.0),
    ]
    ans_tie = (
        "Топ-3 за вчера: Piesa inchidere toc HG VEKA 0,5 mm — 115 шт; "
        "далее ничья по 106: Capac balama cercevea sus alb и Capac balama toc sus alb"
    )
    ok_tie, how_tie = R.accept_top_n(ans_tie, rows, n=3)
    check("ничья топ-3 с оговоркой принята", ok_tie is True, how_tie)

    ans_no_note = (
        "1) Piesa inchidere toc HG VEKA 0,5 mm 115; "
        "2) Capac balama cercevea sus alb 106; "
        "3) Capac balama toc sus alb 106"
    )
    ok_no, how_no = R.accept_top_n(ans_no_note, rows, n=3)
    check("ничья без оговорки — отказ", ok_no is False, how_no)

    # ── 5. нет хардкода контрольных чисел 19.08 в коде раннера ───────────────
    src = Path(R.__file__).read_text(encoding="utf-8")
    leaked = runner_source_has_control_numbers(src)
    check("нет контрольных чисел 19.08 в раннере", leaked == [], leaked[:5])

    # CTE today в каждом period SQL
    for q in R.QUESTIONS:
        if q.kind in ("period", "period_shipped", "leader", "top", "compare",
                      "sunday_zero", "unsold", "furniture"):
            for s in R.build_etalon_sql(q):
                if "timezone('Europe/Chisinau', now())" not in s:
                    check("CTE Chisinau в SQL %s" % q.q[:40], False, s[:120])
                    break
            else:
                continue
            break
    else:
        check("все period/leader SQL с Chisinau CTE", True)

    # класс С/Д на месте
    classes = {q.klass for q in R.QUESTIONS}
    check("классы С и Д есть", classes == {"С", "Д"}, classes)
    check("вопросов ≥ 25 (раздел B)", len(R.QUESTIONS) >= 25, len(R.QUESTIONS))

    return ok, len(fails), fails


def make_broken_copy(src: Path, dst: Path) -> None:
    """Заведомо неверная реализация: UTC вместо Кишинёва, без today+1,
    принимает подмену дня, ничью без оговорки, зашивает число 19.08.
    """
    text = src.read_text(encoding="utf-8")
    # 1) «сегодня» = UTC date
    text = text.replace(
        "return when.astimezone(CHISINAU).date()",
        "return when.astimezone(UTC).date()  # BROKEN: UTC instead of Chisinau",
        1,
    )
    text = text.replace(
        'SPEC_TODAY_SQL = "timezone(\'Europe/Chisinau\', now())::date"',
        'SPEC_TODAY_SQL = "CURRENT_DATE"  # BROKEN',
        1,
    )
    # 2) убрать today+1 у открытых периодов
    text = text.replace(
        '"today": (d, f"{d} + INTERVAL 1 day")',
        '"today": (d, f"{d} + INTERVAL 2 day"),  # BROKEN bound',
        1,
    )
    # сломанный кортеж выше даёт лишнюю запятую у исходного — чиним пару строк целиком
    text = text.replace(
        '"today": (d, f"{d} + INTERVAL 2 day"),  # BROKEN bound,',
        '"today": (d, f"{d} + INTERVAL 2 day"),  # BROKEN bound',
        1,
    )
    text = text.replace(
        '"this_week": (tw, f"{d} + INTERVAL 1 day")',
        '"this_week": (tw, f"{d}"),  # BROKEN no +1',
        1,
    )
    text = text.replace(
        '"this_week": (tw, f"{d}"),  # BROKEN no +1,',
        '"this_week": (tw, f"{d}"),  # BROKEN no +1',
        1,
    )
    text = text.replace(
        '"this_month": (tm, f"{d} + INTERVAL 1 day")',
        '"this_month": (tm, f"{d}"),  # BROKEN no +1',
        1,
    )
    text = text.replace(
        '"this_month": (tm, f"{d}"),  # BROKEN no +1,',
        '"this_month": (tm, f"{d}"),  # BROKEN no +1',
        1,
    )
    # 3) подмена дня не ловится
    text = text.replace(
        "if friday_value is not None and any(numbers_close(n, friday_value) for n in nonzero):\n"
        "        return True\n"
        "    # Любое ненулевое без оговорки при эталоне 0 — подозрение на подмену.\n"
        "    return True",
        "if friday_value is not None and any(numbers_close(n, friday_value) for n in nonzero):\n"
        "        return False  # BROKEN: ignore substitution\n"
        "    return False  # BROKEN",
        1,
    )
    # 4) ничья без оговорки проходит
    text = text.replace(
        'if not any(w in low for w in ("ничь", "равн", "одинаков", "поровну", "tie")):\n'
        '            return False, "ничья без оговорки"',
        'if not any(w in low for w in ("ничь", "равн", "одинаков", "поровну", "tie")):\n'
        '            return True, "BROKEN accept without tie note"',
        1,
    )
    # 5) зашить контрольное число 19.08
    text = text.replace(
        'ASK_USER = os.environ.get("AB_ASK_USER", "gold-v2")'
        if False else 'user": "okna-live"',
        'user": "okna-live", "control_19_08": 479710.42',
        1,
    )
    # если предыдущая замена не сработала — вставим литерал иначе
    if "479710.42" not in text:
        text = text.replace(
            'SPEC = "docs/ACCEPTANCE_OKNA_LIVE.md"',
            'SPEC = "docs/ACCEPTANCE_OKNA_LIVE.md"\nHARDCODED_19_08 = 479710.42  # BROKEN',
            1,
        )
    dst.write_text(text, encoding="utf-8")


def main() -> int:
    if not RUNNER.is_file():
        print("FAIL- нет файла", RUNNER)
        return 1

    R = load_runner(RUNNER, "run_okna_live_good")
    ok_good, nfail_good, fails_good = run_suite(R, "good")
    for name in fails_good:
        print("FAIL-", name)
    print("--- эталонная реализация: pass=%d fail=%d ---" % (ok_good, nfail_good))
    global PASS, FAIL
    PASS = ok_good
    FAIL = list(fails_good)

    # порча копии
    with tempfile.TemporaryDirectory(prefix="okna-live-broken-") as td:
        broken_path = Path(td) / "run_okna_live_broken.py"
        make_broken_copy(RUNNER, broken_path)
        Rb = load_runner(broken_path, "run_okna_live_broken")
        ok_bad, nfail_bad, fails_bad = run_suite(Rb, "broken")
        print("--- порченая копия: pass=%d fail=%d ---" % (ok_bad, nfail_bad))
        print("первые провалы порчи:")
        for line in fails_bad[:12]:
            print("  ", line)

    # замок краснеет на порче: fail_broken > fail_good и fail_broken заметный
    t("эталон: fail=0", nfail_good == 0, "fails=%s" % fails_good[:5])
    t("порча: fail > 0", nfail_bad > 0, "fail=%d" % nfail_bad)
    t(
        "порча краснеет сильнее эталона (fail_broken > fail_good)",
        nfail_bad > nfail_good,
        "good=%d broken=%d" % (nfail_good, nfail_bad),
    )
    t(
        "порча ломает ≥5 проверок",
        nfail_bad >= 5,
        "fail_broken=%d" % nfail_bad,
    )

    print()
    print("ИТОГО замок: pass=%d fail=%d | эталон suite pass/fail=%d/%d | "
          "порча suite pass/fail=%d/%d"
          % (PASS, len(FAIL), ok_good, nfail_good, ok_bad, nfail_bad))
    if FAIL:
        print("🔴", "; ".join(FAIL))
        return 1
    print("Замок run_okna_live пройден.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
