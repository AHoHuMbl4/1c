#!/usr/bin/env python3
"""ГЕНЕРАТОР НАБОРА САМОПРОВЕРКИ — вопросы строятся ИЗ ДАННЫХ БАЗЫ.

План `docs/PLAN_ANSWER_CONTRACT.md` §4 (слепое пятно — число) и фаза 4
`docs/PLAN_AUTONOMY.md` (приёмочный набор строится из базы, п. 15 TARGET).

Слова вопросов — ТОЛЬКО из слоёв самой базы:
  · метка сущности      — `search_tables.label`;
  · человеческие алиасы — `search_entity_alias.aliases` (может отсутствовать
    целиком на свежей базе — тогда поверхность одна, метка);
  · величины            — ключи карты `nums` корпуса (та же выборка, что
    `measures_of` в `serene_ask.py`), человеческое слово величины —
    `search_measure_alias.aliases`, если таблица есть и заполнена.

Сущности — деловые: всё из `search_tables`, кроме размеченных `service` в
`search_entity_class` (неразмеченное считается деловым — то же умолчание, что
у сборки, `classify_entities.py`).

Значений данных в вопросах нет (п. 19): вопрос называет сущность и величину,
не строки. Имён конфигурации в коде нет: всё перечислено запросами.

Формы намеренно простые — их задача ДОСТИЖИМОСТЬ сущности конвейером, а не
естественность («Сколько {label}?», «{label}: {measure} всего?»).

🔴 ДЕТЕРМИНИЗМ (замок): на неизменной базе два прогона дают БАЙТ-В-БАЙТ один
файл — сортировка по (src_table, вид, поверхность, величина), алиас берётся
лексикографически первым, дат и случайности в файле нет.

Использование:
    ASK_BASE=ut_test python3 work/acceptance/selftest_generate.py
    ASK_BASE=postgres python3 work/acceptance/selftest_generate.py

Пишет `work/acceptance/runs/selftest-<база>.jsonl` (одна запись = один вопрос).
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BASE = os.environ.get("ASK_BASE") or (sys.argv[1] if len(sys.argv) > 1 else "ut_test")
OUT = os.path.join(ROOT, "work", "acceptance", "runs", "selftest-%s.jsonl" % BASE)


def load_env(path):
    """Окружение юнита читается КАК EnvironmentFile, а не через оболочку
    (тот же приём, что `step5_live.py`: `set -a; . файл` рвёт DSN с пробелами)."""
    try:
        fh = open(path, encoding="utf-8")
    except OSError:
        return
    with fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            v = v.strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                v = v[1:-1]
            os.environ.setdefault(k.strip(), v)


# Порядок — как `EnvironmentFile` в юните `1c-serene-ask@`: побазовый сильнее общего.
load_env("/etc/1c-serene-ask-%s.env" % BASE)
load_env("/etc/1c-serene-ask.env")
load_env("/etc/1c-mcp-reports.env")

sys.path.insert(0, os.path.join(ROOT, "ubuntu", "serenedb"))
import serene_ask as A  # noqa: E402


def business_entities():
    """Деловые сущности: всё из search_tables, кроме cls='service'."""
    return [(r[0], r[1] or "") for r in A.psql(
        "SELECT t.src_table, coalesce(t.label,'') FROM %s t "
        "WHERE NOT EXISTS (SELECT 1 FROM search_entity_class c "
        "                  WHERE c.src_table = t.src_table AND c.cls = 'service') "
        "ORDER BY t.src_table" % A.TABLES)]


def aliases_of():
    """Первый (лексикографически) алиас сущности. Таблицы может не быть вовсе."""
    try:
        rows = A.psql(
            "SELECT src_table, aliases FROM search_entity_alias "
            "WHERE coalesce(aliases,'') <> ''")
    except RuntimeError:
        return {}
    out = {}
    for r in rows:
        if not r or not r[0]:
            continue
        words = [a.strip() for a in (r[1] or "").split(",") if a.strip()]
        if words:
            out[r[0]] = sorted(words)[0]
    return out


def measures_of_corpus():
    """Величины сущности — ключи карты nums (та же выборка, что measures_of)."""
    rows = A.psql(
        "SELECT DISTINCT src_table, u.k FROM %s, unnest(map_keys(nums)) AS u(k) "
        "WHERE nums IS NOT NULL" % A.CORPUS)
    out = {}
    for r in rows:
        if r and r[0] and len(r) > 1 and r[1]:
            out.setdefault(r[0], set()).add(r[1])
    return out


def measure_words():
    """Человеческое слово величины из search_measure_alias; таблицы может не быть."""
    try:
        rows = A.psql(
            "SELECT src_table, measure, aliases FROM search_measure_alias "
            "WHERE coalesce(aliases,'') <> ''")
    except RuntimeError:
        return {}
    out = {}
    for r in rows:
        if not r or len(r) < 3 or not r[0] or not r[1]:
            continue
        words = [a.strip() for a in (r[2] or "").split(",") if a.strip()]
        if words:
            out[(r[0], r[1])] = sorted(words)[0]
    return out


def main():
    ents = business_entities()
    alias = aliases_of()
    meas = measures_of_corpus()
    mword = measure_words()
    records = []
    for src, label in sorted(ents):
        records.append({"base": BASE, "src_table": src, "label": label,
                        "qkind": "count", "surface": "label", "measure": None,
                        "question": "Сколько %s?" % label})
        if alias.get(src):
            records.append({"base": BASE, "src_table": src, "label": label,
                            "qkind": "count", "surface": "alias", "measure": None,
                            "question": "Сколько %s?" % alias[src]})
        for m in sorted(meas.get(src) or ()):
            records.append({"base": BASE, "src_table": src, "label": label,
                            "qkind": "sum", "surface": "label", "measure": m,
                            "question": "%s: %s всего?" % (label, mword.get((src, m), m))})
    records.sort(key=lambda r: (r["src_table"], r["qkind"], r["surface"],
                                r["measure"] or ""))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        for i, rec in enumerate(records, 1):
            rec["id"] = "%s-%05d" % (BASE, i)
            fh.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")
    n_count = sum(1 for r in records if r["qkind"] == "count")
    print("%s: сущностей деловых %d, вопросов %d (счёт %d, величины %d) -> %s"
          % (BASE, len(ents), len(records), n_count, len(records) - n_count, OUT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
