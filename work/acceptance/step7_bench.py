#!/usr/bin/env python3
"""ПРИБОР ШАГА 7 (гейт исходящего): проверяет гейт НА ЖИВЫХ ДАННЫХ, без вызовов модели.

Зачем отдельно от `test_gate.py`. Тот прибор держит правила на заготовленных строках —
он ловит поломку логики, но не отвечает на вопрос владельца: «шаг работает на 100 % на
всех вопросах?». Здесь берутся НАСТОЯЩИЕ строки и НАСТОЯЩИЕ посчитанные величины боевой
базы по каждому вопросу приёмочного набора, и по каждому проверяются обе стороны сразу:

  A. **пропуск** — подменённое число, прошедшее гейт (клиент
     получает неверный ответ: п. 10 контракта);
  B. **ложное срабатывание** — верный ответ, собранный из посчитанных базой величин тем
     же кодом подстановки, что и в продукте, — и отвергнутый гейтом (отказ при
     наличии данных — дефект п. 21, а не осторожность).

Обе стороны — ошибки. Мерило шага: **ноль ошибок обоих классов на 100 % вопросов**.

Модель не зовётся ни разу: ни разбор вопроса, ни выбор сущности, ни формулировка сюда не
входят — сущность берётся из эталона набора (владелец 04.08: «представь, что другие шаги
работают правильно»). Поэтому прибор детерминирован и бесплатен, а его число сравнимо
между прогонами.

Использование:
    python3 work/acceptance/step7_bench.py [файл_набора]
Окружение сервиса читается из /etc/1c-serene-ask-<база>.env (ASK_BASE, умолчание ut_test).
"""
import importlib
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SET_FILE = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "docs/ACCEPTANCE_UT.md")
BASE = os.environ.get("ASK_BASE", "ut_test")


def load_env(path):
    """Окружение юнита читается КАК EnvironmentFile, а не через оболочку.

    `set -a; . файл` рвёт значения с пробелами (`SERENEDB_DSN_RO="host=… dbname=…"`) и
    молча уводит прибор в другую базу — записано в activeContext 04.08.
    """
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


# Порядок — как `EnvironmentFile` в юните: побазовый файл сильнее общего.
load_env("/etc/1c-serene-ask-%s.env" % BASE)
load_env("/etc/1c-serene-ask.env")
load_env("/etc/1c-embed.env")
load_env("/etc/1c-mcp-reports.env")     # PGPASSWORD/RESOLVER_PW живут здесь
os.environ.setdefault("ASK_TOKEN", "bench")

sys.path.insert(0, os.path.join(ROOT, "ubuntu/serenedb"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
A = importlib.import_module("serene_ask")
B = importlib.import_module("entity_choice_bench")

NBSP = " "


def fmt(v):
    """Число в том виде, в каком его ставит в текст САМ продукт (`_fill_figures`)."""
    out = A._fmt(v)
    head, _, frac = out.partition(".")
    neg, head = (head[:1] == "-"), head.lstrip("-")
    grouped = NBSP.join([head[:len(head) % 3 or 3]]
                        + [head[i:i + 3] for i in range(len(head) % 3 or 3, len(head), 3)])
    return ("-" if neg else "") + grouped + ("." + frac if frac else "")


def measure_of(src):
    """Величина, по которой есть что считать. Имя приходит из данных, не из кода."""
    try:
        ms = A.measures_of(src)
    except RuntimeError:
        return None
    for m in ms:
        try:
            a = A.aggregate(src, "", [], m)
        except RuntimeError:
            continue
        if a and a.get("sum"):
            return m
    return None


CASES_PASS = "пропустить"
CASES_STOP = "остановить"


def absent(value, allowed):
    """Сдвинуть число так, чтобы в данных его не оказалось; не вышло — вернуть None.

    🔴 Первая редакция прибора меняла крайние значения на «+7» и ждала отказа. Но
    небольшое число легко встречается где-то в данных (номер строки, количество, часть
    кода), и гейт пропускал его законно: он обещает «число встречается в данных», а не
    «число стоит в своей роли» — роль держит подстановка кодом (`_fill_figures`).
    `[замер 04.08]` так набралось 8 «пропусков», которые пропусками не были: прибор мерил
    не то, что проверяет шаг. Сдвиг идёт, пока значение не окажется вне данных; за 40
    попыток не нашлось — случай не ставится, чтобы нарушение не бралось из воздуха.
    """
    v = float(value)
    for i in range(1, 41):
        cand = round(v + i * 7919, 2)          # шаг простым числом: реже совпадает
        if cand not in allowed and float(int(cand)) not in allowed:
            return cand
    return None


def data_values(rows, agg):
    """Числа, которые ЕСТЬ в данных: показанные строки и посчитанные величины.

    Собирается теми же разборщиками, что у гейта (`_norm_numbers`), — иначе прибор
    считал бы выдумкой то, что гейт видит числом из данных, и мерил бы расхождение
    двух разборов, а не работу шага.
    """
    al = set()
    for r in rows:
        al |= A._norm_numbers(r[5] or "")
        al |= A._norm_numbers(r[3] or "")
        try:
            v = float(r[2])
            al.add(round(v, 2))
            if v == int(v):
                al.add(float(int(v)))
        except (TypeError, ValueError):
            pass
    for k in ("sum", "min", "max", "avg"):
        v = (agg or {}).get(k)
        if v is not None:
            al.add(round(float(v), 2))
            if float(v) == int(float(v)):
                al.add(float(int(float(v))))
    if agg and agg.get("count") is not None:
        al.add(float(agg["count"]))
    return al


def cases(agg, rows, measure, allowed):
    """Тексты двух родов: собранные из данных и собранные подменой.

    Все «верные» собираются из ПОСЧИТАННЫХ базой чисел, все «выдуманные» — подменой
    ровно одного числа в них. Языковых списков здесь нет: слова вокруг чисел не влияют
    ни на одну проверку гейта.
    """
    out = []
    s, c = agg.get("sum"), agg.get("count")
    mx, mn = agg.get("max"), agg.get("min")
    dmin, dmax = (agg.get("date_min") or ""), (agg.get("date_max") or "")
    year = None
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", str(dmax))
    if m:
        year = m.group(1)

    def stop(name, tmpl, *vals):
        """Случай «выдумка» ставится, только если подмены в данных действительно нет."""
        got = [absent(v, allowed) for v in vals]
        if any(g is None for g in got):
            return
        out.append((CASES_STOP, name, tmpl % tuple(fmt(g) for g in got)))

    if c is not None:
        out.append((CASES_PASS, "счёт", "Найдено %s записей." % fmt(c)))
        stop("счёт подменён", "Найдено %s записей.", c)
    if s:
        out.append((CASES_PASS, "итог", "Итого %s." % fmt(s)))
        stop("итог подменён", "Итого %s.", s)
        if round(s * 100, 2) not in allowed:
            out.append((CASES_STOP, "итог×100", "Итого %s." % fmt(round(s * 100, 2))))
        div = round(s / 1000, 2)
        # 🔴 Запись вида «1.01» неоднозначна: это и число, и первое января. Такой случай
        # ставить нельзя — гейт законно засчитает её как дату, если такая дата в данных
        # есть, и прибор объявил бы дефектом собственную двусмысленность записи
        # (`[замер 04.08]`, третий «пропуск» из трёх на 400 сущностях). Неоднозначность
        # разбирается отдельно и описана в HOW_IT_WORKS, а не прячется в число прибора.
        if div not in allowed and not A._dates(fmt(div)):
            out.append((CASES_STOP, "итог÷1000", "Итого %s." % fmt(div)))
    if s and c is not None:
        out.append((CASES_PASS, "итог+счёт",
                    "Итого %s по %s записям." % (fmt(s), fmt(c))))
        out.append((CASES_PASS, "перечисление",
                    "Итого %s: 1) первая, 2) вторая, 3) третья." % fmt(s)))
    if mx is not None and mn is not None and mx != mn:
        out.append((CASES_PASS, "крайние", "Наибольшая %s, наименьшая %s." % (fmt(mx), fmt(mn))))
        stop("крайние подменены", "Наибольшая %s, наименьшая %s.", mx, mn)
    if dmin and dmax:
        d1, d2 = str(dmin)[:10], str(dmax)[:10]
        out.append((CASES_PASS, "период",
                    "Данные с %s по %s." % (".".join(reversed(d1.split("-"))),
                                            ".".join(reversed(d2.split("-"))))))
        # Подменённая дата берётся ТОЛЬКО такая, какой в данных нет: в выборке из сотен
        # строк соседний день сплошь и рядом встречается, и отказывать в нём было бы
        # неверно — `[замер 04.08]` два «пропуска» из трёх на 400 сущностях оказались
        # именно этим. Известные даты собираются так же, как их видит гейт.
        known = set()
        for r in rows:
            known |= {(d, m) for d, m, _y in A._dates(r[3] or "")}
            known |= {(d, m) for d, m, _y in A._dates(r[5] or "")}
        for s_ in (dmin, dmax):
            known |= {(d, m) for d, m, _y in A._dates(str(s_))}
        y2, m2, day2 = d2.split("-")
        for shift in range(1, 28):
            nd = (int(day2) + shift - 1) % 28 + 1
            if (nd, int(m2)) not in known:
                out.append((CASES_STOP, "дата подменена",
                            "Последняя запись %02d.%s.%s." % (nd, m2, y2)))
                break
    if year:
        out.append((CASES_PASS, "год из данных", "За %s год всё сходится." % year))
        out.append((CASES_STOP, "год выдуман", "За %d год всё сходится." % (int(year) + 9)))
    # Число из ВОПРОСА, не бывшее понятием отбора (F244): в данных его нет.
    out.append((CASES_STOP, "число вопроса", "Итого 7 777 777."))
    # Утечка нашей инструкции (№27).
    leak = [l for p in A.OUR_PROMPTS for l in str(p).splitlines() if len(l.strip()) >= 60]
    if leak:
        out.append((CASES_STOP, "утечка инструкции", "Вот ответ. " + leak[0].strip()))
    # Число из показанной строки (реквизит, номер документа) — оно из данных.
    for r in rows[:1]:
        t = A._norm_numbers(r[5] or "")
        big = sorted(v for v in t if v >= 1000)
        if big:
            out.append((CASES_PASS, "число строки", "Например, %s." % fmt(big[0])))
    return out


def wide_pairs(limit):
    """Сущности ИЗ САМОЙ БАЗЫ, а не только те 44, что попали в приёмочный набор.

    «Ноль ошибок на всех вопросах» проверяется тем шире, чем больше разных данных
    прошло через гейт: у сущностей разные величины, разряды, даты и мусор в реквизитах.
    Отбор делает база одним запросом (п. 20), порядок — по числу строк, чтобы в выборку
    попадало то, о чём вообще спрашивают.
    """
    rs = A.psql("SELECT src_table, count(*) c FROM %s GROUP BY 1 "
                "ORDER BY c DESC, src_table LIMIT %d" % (A.CORPUS, int(limit)))
    return [("(сущность %s)" % r[0], r[0]) for r in rs if r and r[0]]


def main():
    wide = int(os.environ.get("STEP7_WIDE", "0"))
    gold = wide_pairs(wide) if wide else B.pairs(SET_FILE)
    print("набор: %s, пар: %d, база: %s"
          % ("сущности базы" if wide else os.path.basename(SET_FILE), len(gold), BASE))
    n_q = n_case = 0
    miss, false_stop = [], []
    for q, src in gold:
        try:
            measure = measure_of(src)
            agg = A.aggregate(src, "", [], measure)
            rows = A.rows_of(src, "", [], A.TOPK, measure)
        except RuntimeError as e:
            print("  ⚠ %-44s пропущен: %s" % (q[:44], str(e)[:60]))
            continue
        if not agg or agg.get("count") is None:
            continue
        n_q += 1
        # Гейт заземляет ответ на том, что видела модель (`rows_seen`, `F247`), — прибор
        # спрашивает ровно тот же набор, иначе мерил бы другую границу.
        seen = A.rows_seen(rows)
        for want, name, text in cases(agg, seen, measure, data_values(seen, agg)):
            n_case += 1
            ok, bad = A.gate_out(text, seen, agg, [], [])
            if want == CASES_PASS and not ok:
                false_stop.append((q, src, name, text[:60], bad[:2]))
            if want == CASES_STOP and ok:
                miss.append((q, src, name, text[:60]))
    print("\nвопросов %d, проверок %d" % (n_q, n_case))
    print("🔴 ПРОПУЩЕНО выдуманных чисел: %d" % len(miss))
    for q, src, name, text in miss[:12]:
        print("   %-30s %-18s %s" % (q[:30], name, text))
    print("🔴 ОТВЕРГНУТО верных ответов: %d" % len(false_stop))
    for q, src, name, text, bad in false_stop[:12]:
        print("   %-30s %-18s %-40s %s" % (q[:30], name, text, bad))
    # 🔴 ЗАМЕР, КОТОРЫЙ НИЧЕГО НЕ ПРОВЕРИЛ, — НЕ «В ПОРЯДКЕ». Первая редакция печатала
    # «ноль ошибок обоих классов» на нуле вопросов (база не пустила по паролю), то есть
    # прибор объявлял шаг исправным, ни разу его не позвав. Та же ловушка, что у отметки
    # золотого набора (`F172`): гейт, засчитывающий несостоявшийся прогон, замером не
    # является (п. 11 контракта).
    if n_q < max(5, len(gold) // 2):
        print("\n🔴 ЗАМЕР НЕ СОСТОЯЛСЯ: разобрано вопросов %d из %d — сравнивать не с чем."
              % (n_q, len(gold)))
        return 2
    print("\nШАГ 7 %s" % ("В ПОРЯДКЕ: ноль ошибок обоих классов"
                          if not miss and not false_stop else "НЕИСПРАВЕН"))
    return 1 if (miss or false_stop) else 0


if __name__ == "__main__":
    raise SystemExit(main())
