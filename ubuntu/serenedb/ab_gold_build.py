#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Сборка золотого набора приёмки ИЗ ДАННЫХ базы (решение владельца 19.08).

Почему генератор, а не рукописный список: набор, написанный руками, стареет вместе с
базой и держится на именах конкретной конфигурации. Здесь имена сущностей, величин и
осей приходят из метаданных корпуса (`search_tables`, `search_refcols`,
`search_entity_alias`, `search_corpus`), а не из литералов, поэтому набор собирается на
любой базе; числа не пишутся никуда — эталон считает SQL при каждом прогоне
(`ab_scorer.py`).

Запуск на сервере базы:
    python3 ab_gold_build.py [путь/к/ab-gold-okna.tsv]

Классы вопросов — из живых дефектов, `docs/CLARIFY_JOURNAL_OKNA_2026-08-18.md`:
  1 итоги периодов (вчера / позавчера / сегодня / текущий месяц)
  2 пустой день (день без строк за последние 30) — честный ноль, не выдумка
  3 счёт справочника (крупнейшие catalog_* по строкам корпуса)
  4 rank top-1 и top-3 по количеству и по сумме, ось из данных
  5 top-1 по сумме на второй оси
  6 вилка регистр ↔ документ (обе подписи человеческие)
  7 величина-пустышка (sum = 0 по всей сущности) — честный пивот, не «0»
  8 остатки при обороте без признака прихода/расхода — no_data
  9 прошлый календарный месяц с данными

Доки SereneDB: Sql › Data types › Map (bracket-доступ к MAP),
Sql › Functions › Date Part Functions (`date_trunc`).
"""
import os
import subprocess
import sys

SEP = "\x1f"
ENV_PG = "/etc/1c-serene-ask-postgres.env"
ENV_MCP = "/etc/1c-mcp-reports.env"
# Префиксы платформы 1С (метаданные, а не имена конкретной базы): по ним определяется
# класс сущности. Сами сущности и поля берутся из корпуса.
P_REG = "accumulationregister_"
P_DOC = "document_"
P_CAT = "catalog_"


def env_value(key, *paths):
    out = ""
    for p in paths:
        try:
            for line in open(p, encoding="utf-8"):
                if line.startswith(key + "="):
                    out = line.split("=", 1)[1].strip().strip('"').strip("'")
        except OSError:
            continue
    return out


DSN = os.environ.get("AB_DSN") or env_value("SERENEDB_DSN_RO", ENV_PG) \
    or env_value("SERENEDB_DSN", ENV_PG)
if not os.environ.get("PGPASSWORD"):
    pw = env_value("PGPASSWORD", ENV_MCP)
    if pw:
        os.environ["PGPASSWORD"] = pw


def rows(sql):
    """Строки ответа базы. Считает и отбирает база: наружу выходит только готовое."""
    p = subprocess.run(["psql", DSN, "-tA", "-F", SEP, "-v", "ON_ERROR_STOP=1", "-c", sql],
                       capture_output=True, text=True)
    if p.returncode:
        sys.stderr.write("psql: %s\n" % ((p.stderr or p.stdout or "").strip()[:400]))
        sys.exit(1)
    return [r.split(SEP) for r in (p.stdout or "").strip().split("\n") if r.strip()]


def lit(s):
    return "'" + str(s).replace("'", "''") + "'"


def num(s, default=0.0):
    try:
        return float(s)
    except (TypeError, ValueError):
        return default


# ------------------------------------------------------------------ разведка базы
def entity_stats():
    """Сущности корпуса: строки, датированные строки, человеческая метка, писатель."""
    out = {}
    for r in rows("""
        SELECT c.src_table, coalesce(t.label,''), coalesce(t.written_by,''),
               c.n, c.dated
          FROM (SELECT src_table, count(*) n, count(doc_date) dated
                  FROM search_corpus GROUP BY 1) c
          LEFT JOIN search_tables t USING (src_table)
         ORDER BY c.n DESC"""):
        out[r[0]] = {"src": r[0], "label": r[1], "written_by": r[2],
                     "n": int(num(r[3])), "dated": int(num(r[4]))}
    return out


def measures_of(src):
    """Величины сущности: сколько ненулевых, сколько дробных, итог. Считает база."""
    return [{"name": r[0], "n": int(num(r[1])), "nz": int(num(r[2])),
             "frac": int(num(r[3])), "sum": num(r[4])}
            for r in rows("""
        SELECT k, count(*), sum(CASE WHEN v <> 0 THEN 1 ELSE 0 END),
               sum(CASE WHEN v <> floor(v) THEN 1 ELSE 0 END), sum(v)
          FROM (SELECT unnest(map_keys(nums)) k, unnest(map_values(nums)) v
                  FROM search_corpus WHERE src_table = %s)
         GROUP BY 1 ORDER BY 1""" % lit(src))]


def axes_of(src):
    """Оси сущности: мощность разреза и на какой справочник ось смотрит."""
    tgt = {r[0]: r[1] for r in rows(
        "SELECT col, coalesce(target_src,'') FROM search_refcols WHERE src_table = %s"
        % lit(src))}
    out = []
    for r in rows("""
        SELECT k, count(*), count(DISTINCT v)
          FROM (SELECT unnest(map_keys(refs_map)) k, unnest(map_values(refs_map)) v
                  FROM search_corpus WHERE src_table = %s)
         GROUP BY 1 ORDER BY 3 DESC""" % lit(src)):
        out.append({"col": r[0], "n": int(num(r[1])), "distinct": int(num(r[2])),
                    "target": tgt.get(r[0], "")})
    return out


def aliases_of(srcs):
    if not srcs:
        return {}
    inlist = ", ".join(lit(s) for s in srcs)
    return {r[0]: [a.strip() for a in (r[1] or "").split(",") if a.strip()]
            for r in rows("SELECT src_table, coalesce(aliases,'') FROM search_entity_alias"
                          " WHERE src_table IN (%s)" % inlist)}


def has_balance_flag(src):
    """Признак прихода/расхода у регистра (остатки) — колонка RecordType витрины.

    Есть — по регистру считаются остатки; нет — регистр оборотный, и вопрос об остатках
    честно закрывается `no_data`. Спрашивается у базы, а не выводится из имени.
    """
    r = rows("SELECT count(*) FROM duckdb_columns() WHERE table_name = %s"
             " AND lower(column_name) = 'recordtype'" % lit(src))
    return bool(r and int(num(r[0][0])))


def empty_day(src):
    """Последний разрыв в собственном ряду дат сущности: день без строк между двумя
    днями с данными. Окна в днях нет — ряд дат берётся у самой базы."""
    r = rows("""
        WITH d AS (SELECT DISTINCT doc_date::date dd FROM search_corpus
                    WHERE src_table = %s AND doc_date <= CURRENT_DATE),
             g AS (SELECT dd, lag(dd) OVER (ORDER BY dd) prev FROM d)
        SELECT strftime(dd - INTERVAL 1 day, '%%Y-%%m-%%d')
          FROM g WHERE prev IS NOT NULL AND dd - prev > 1
         ORDER BY dd DESC LIMIT 1""" % lit(src))
    return r[0][0] if r else ""


def prev_month_with_data(src):
    """Последний ПОЛНЫЙ месяц с данными (строго раньше текущего)."""
    r = rows("""
        SELECT strftime(date_trunc('month', doc_date), '%%Y-%%m'), count(*)
          FROM search_corpus
         WHERE src_table = %s AND doc_date < date_trunc('month', CURRENT_DATE)
         GROUP BY 1 HAVING count(*) > 0 ORDER BY 1 DESC LIMIT 1""" % lit(src))
    return r[0][0] if r else ""


# ------------------------------------------------------------------ выбор по классу
def pick_turnover_register(stats):
    """Главный оборотный регистр базы: больше всего датированных строк, есть денежная
    величина. Ни имени, ни языка конкретной базы в выборе нет."""
    best = None
    for src, e in stats.items():
        if not src.startswith(P_REG) or e["dated"] < 1:
            continue
        ms = measures_of(src)
        money = money_measure(ms)
        if not money:
            continue
        cand = dict(e, measures=ms, money=money)
        if best is None or cand["dated"] > best["dated"]:
            best = cand
    return best


def frac_share(m):
    """Доля дробных значений величины: у денег копейки, у штук их почти нет."""
    return m["frac"] / float(m["nz"]) if m["nz"] else 0.0


def money_measure(ms):
    """Денежный ИТОГ сущности: наибольший итог среди величин, у которых вообще бывают
    дробные значения (копейки). Ни порога, ни доли: «есть дробные» — факт, «больше
    всех» — сравнение. Себестоимость и сумма без налога дробнее итога, но меньше его,
    поэтому итогом не становятся."""
    live = [m for m in ms if m["nz"] and m["frac"]]
    return max(live, key=lambda m: abs(m["sum"])) if live else None


def qty_measure(ms, money=None):
    """Штучная величина: самая «целая» из живых, не совпадающая с денежной."""
    live = [m for m in ms if m["nz"] and (not money or m["name"] != money["name"])]
    return min(live, key=lambda m: (frac_share(m), -abs(m["sum"]))) if live else None


def empty_measure(ms):
    """Величина-пустышка: по всей сущности итог ноль и ни одного ненулевого значения."""
    for m in sorted(ms, key=lambda m: m["name"]):
        if m["n"] and not m["nz"] and abs(m["sum"]) < 1e-9:
            return m
    return None


def rank_axes(src):
    """Оси разреза: те, что база объявила ссылками на справочник (search_refcols) и у
    которых больше одного значения. `Recorder` — ссылка на сам документ, в refcols его
    нет, и разрезом он не становится; ось с одним значением разрезом не является
    по определению. Порогов тут нет."""
    return [a for a in axes_of(src)
            if a["distinct"] > 1 and a["target"].startswith(P_CAT)]


# Справочники для вопроса о счёте — те, на которые смотрит сама основная сущность
# базы (её оси). Это не порог и не список слов: если деятельность базы описывается
# продажами ТМЦ контрагентам, спрашивают про номенклатуру и контрагентов, а не про
# самый длинный классификатор.
def axis_catalogs(stats, axes, limit=2):
    """Справочники осей основной сущности, крупные — раньше."""
    seen, out = set(), []
    for a in axes:
        tgt = a["target"]
        if tgt in seen or tgt not in stats:
            continue
        seen.add(tgt)
        out.append(stats[tgt])
    return sorted(out, key=lambda e: -e["n"])[:limit]


MONTHS = ("января", "февраля", "марта", "апреля", "мая", "июня",
          "июля", "августа", "сентября", "октября", "ноября", "декабря")
MONTHS_NOM = ("январь", "февраль", "март", "апрель", "май", "июнь",
              "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь")


def say_day(iso):
    """«2026-08-16» → «16 августа 2026 года» — так дату называет человек."""
    y, m, d = iso.split("-")
    return "%d %s %s года" % (int(d), MONTHS[int(m) - 1], y)


def say_month(iso):
    """«2026-07» → «июль 2026»."""
    y, m = iso.split("-")
    return "%s %s" % (MONTHS_NOM[int(m) - 1], y)


# ------------------------------------------------------------------ эталонный SQL
def sql_period_sum(src, measure, since, until):
    return ("SELECT coalesce(round(sum(nums[%s]), 2), 0) FROM search_corpus"
            " WHERE src_table = %s AND doc_date >= %s AND doc_date < %s"
            % (lit(measure), lit(src), since, until))


def sql_catalog_count(src):
    """Счёт справочника без папок: папка — не запись справочника (признак платформы)."""
    return ("SELECT count(*) FROM search_corpus WHERE src_table = %s"
            " AND NOT coalesce(flags['IsFolder'], false)" % lit(src))


def sql_rank(src, measure, axis, offset=0):
    return ("SELECT round(sum(nums[%s]), 2) s FROM search_corpus WHERE src_table = %s"
            " GROUP BY refs_map[%s] ORDER BY s DESC LIMIT 1 OFFSET %d"
            % (lit(measure), lit(src), lit(axis), offset))


def sql_count_period(src, since, until):
    return ("SELECT count(*) FROM search_corpus WHERE src_table = %s"
            " AND doc_date >= %s AND doc_date < %s" % (lit(src), since, until))


# ------------------------------------------------------------------ сборка набора
def build():
    stats = entity_stats()
    reg = pick_turnover_register(stats)
    if not reg:
        sys.stderr.write("в корпусе нет оборотного регистра с денежной величиной\n")
        sys.exit(2)
    src = reg["src"]
    label = reg["label"] or src
    money = reg["money"]["name"]
    qty = qty_measure(reg["measures"], reg["money"])
    blank = empty_measure(reg["measures"])
    axes = rank_axes(src)
    doc = reg["written_by"] if reg["written_by"] in stats else ""
    al = aliases_of([s for s in (src, doc) if s])
    shared = [a for a in al.get(src, []) if a in al.get(doc, [])] if doc else []
    day0 = empty_day(src)
    month = prev_month_with_data(src)
    cats = axis_catalogs(stats, axes)

    lines = [
        "# Приёмочный набор: собран ИЗ ДАННЫХ базы генератором ab_gold_build.py.",
        "# Руками здесь ничего не правится — правится генератор и набор пересобирается.",
        "# Формат: вопрос <TAB> эталонный SQL или MODE=… <TAB> опции (PICK=, CLS=).",
        "# Числа не зашиты: эталон считает SQL при каждом прогоне (ab_scorer.py).",
        "# PICK — клик человека по развилке (то же, что кнопка в боте): src/measure/axis.",
        "# Сущность набора: %s (%s), денежная величина «%s»%s." % (
            src, label, money, ", штучная «%s»" % qty["name"] if qty else ""),
    ]
    add = lines.append

    def row(q, spec, cls, pick=None):
        opts = ["CLS=%s" % cls]
        if pick:
            opts.append("PICK=" + "|".join(pick))
        add("# класс %s" % cls)
        add("\t".join([q, spec, " ".join(opts)]))

    pick_reg = ["src:%s" % src, "measure:%s" % money]
    # --- класс 1: итоги периодов
    periods = [
        ("за вчера", "CURRENT_DATE - INTERVAL 1 day", "CURRENT_DATE"),
        ("за позавчера", "CURRENT_DATE - INTERVAL 2 day", "CURRENT_DATE - INTERVAL 1 day"),
        ("за сегодня", "CURRENT_DATE", "CURRENT_DATE + INTERVAL 1 day"),
        ("за текущий месяц", "date_trunc('month', CURRENT_DATE)",
         "CURRENT_DATE + INTERVAL 1 day"),
    ]
    for phrase, since, until in periods:
        row("Сколько всего по «%s» %s?" % (label, phrase),
            sql_period_sum(src, money, since, until),
            "1 итог периода", pick_reg)

    # --- класс 2: пустой день (честный ноль, не выдумка)
    if day0:
        row("Сколько всего по «%s» за %s?" % (label, say_day(day0)),
            sql_period_sum(src, money, lit(day0), "%s::date + INTERVAL 1 day" % lit(day0)),
            "2 пустой день", pick_reg)

    # --- класс 3: счёт справочников
    for c in cats:
        row("Сколько записей в справочнике «%s»?" % (c["label"] or c["src"]),
            sql_catalog_count(c["src"]), "3 счёт справочника", ["src:%s" % c["src"]])

    # --- класс 4: rank top-1 и top-3, ось и величина из данных
    if axes:
        a0 = axes[0]
        if qty:
            row("Покажи топ-1 по величине «%s» в разрезе «%s» за всё время по «%s»."
                % (qty["name"], a0["col"], label),
                sql_rank(src, qty["name"], a0["col"]), "4 rank top-1 по количеству",
                ["src:%s" % src, "axis:%s" % a0["col"], "measure:%s" % qty["name"]])
        row("Покажи топ-3 по величине «%s» в разрезе «%s» за всё время по «%s»."
            % (money, a0["col"], label),
            sql_rank(src, money, a0["col"], offset=2), "4 rank top-3 по сумме",
            ["src:%s" % src, "axis:%s" % a0["col"], "measure:%s" % money])
    # --- класс 5: top-1 по сумме на второй оси
    if len(axes) > 1:
        a1 = axes[1]
        row("Кто в лидерах по величине «%s» в разрезе «%s» за всё время по «%s»?"
            % (money, a1["col"], label),
            sql_rank(src, money, a1["col"]), "5 top-1 по сумме, вторая ось",
            ["src:%s" % src, "axis:%s" % a1["col"], "measure:%s" % money])

    # --- класс 6: вилка регистр ↔ документ (обе подписи человеческие)
    if doc and shared:
        row("Сколько было «%s» за %s?" % (shared[0], say_month(month) if month else "весь период"),
            "MODE=fork", "6 вилка регистр-документ")

    # --- класс 7: величина-пустышка
    if blank:
        row("Какой итог по величине «%s» в «%s» за всё время?" % (blank["name"], label),
            "MODE=pivot", "7 величина-пустышка", ["src:%s" % src])

    # --- класс 8: остатки у оборотного регистра — no_data
    if not has_balance_flag(src) and axes:
        tgt = stats.get(axes[0]["target"], {})
        row("Какие сейчас остатки по «%s» на складах?"
            % (tgt.get("label") or axes[0]["col"]), "MODE=kind", "8 остатки: no_data")

    # --- класс 9: прошлый календарный месяц с данными
    if month:
        since = "%s::date" % lit(month + "-01")
        until = "(%s::date + INTERVAL 1 month)" % lit(month + "-01")
        row("Сколько всего по «%s» за %s?" % (label, say_month(month)),
            sql_period_sum(src, money, since, until), "9 прошлый месяц", pick_reg)
        if doc:
            row("Сколько документов «%s» за %s?"
                % (stats.get(doc, {}).get("label") or doc, say_month(month)),
                sql_count_period(doc, since, until), "9 счёт документов за месяц",
                ["src:%s" % doc])

    return lines


MODE_MEANING = {
    "kind": "no_data: ответ без чисел итога («данных об остатках нет»)",
    "fork": "уточнение: спрошено, две ветки, обе подписи человеческие",
    "pivot": "честный пивот на живую величину — не «0» и не отказ",
}


def answers_snapshot(lines):
    """Снимок «вопрос → ответ»: числа считает база сейчас, для чтения человеком.

    В самом наборе чисел нет и не будет — эталон пересчитывается при каждом прогоне;
    снимок нужен, чтобы вопросы можно было прочитать и оценить без запуска сервиса.
    """
    out = ["# Золотой набор okna: вопросы и эталонные ответы",
           "",
           "Собран `ubuntu/serenedb/ab_gold_build.py` из данных базы. Числа ниже — **снимок**:",
           "в наборе (`ab-gold-okna.tsv`) их нет, эталон пересчитывается SQL при каждом прогоне.",
           "",
           "| # | Класс | Вопрос | Эталонный ответ |",
           "|---|---|---|---|"]
    i = 0
    for line in lines:
        if "\t" not in line:
            continue
        cols = line.split("\t")
        q, spec = cols[0], cols[1]
        opts = cols[2] if len(cols) > 2 else ""
        cls = opts.split("CLS=", 1)[1].split(" PICK=")[0].strip() if "CLS=" in opts else ""
        i += 1
        if spec.startswith("MODE="):
            val = MODE_MEANING.get(spec.split("=", 1)[1].strip(), spec)
        else:
            r = rows(spec)
            val = r[0][0] if r and r[0] else "—"
        out.append("| %d | %s | %s | %s |" % (i, cls, q.replace("|", "\\|"), val))
    return out


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    here = os.path.dirname(os.path.abspath(__file__))
    out = args[0] if args else os.path.join(here, "ab-gold-okna.tsv")
    ans = args[1] if len(args) > 1 else ""
    lines = build()
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    qn = sum(1 for l in lines if "\t" in l)
    print("набор собран: %s, вопросов %d" % (out, qn))
    if ans:
        with open(ans, "w", encoding="utf-8") as fh:
            fh.write("\n".join(answers_snapshot(lines)) + "\n")
        print("снимок ответов: %s" % ans)
    return 0


if __name__ == "__main__":
    sys.exit(main())
