#!/usr/bin/env python3
"""ЧТО БЫЛО БЫ, ЕСЛИ: разбор потерянных ответов по следу прогона, без единого вызова модели.

Читает JSONL прибора `answer_rate_probe.py` и отвечает на два вопроса п. 21:

  1. **Поимённо: какая проверка съела ответ.** Каждое уточнение относится к своему
     механизму по пометке следа, а не по догадке: `unsupported_pick` (вето по синонимам),
     `writer_pair_unproven` (пара «регистр ← документ»), `arbiter_detected` (числа
     кандидатов разошлись), `measure_ambiguous` (величина, шаг 5), `not_enough` (шаг 8),
     `ambiguous` (модель назвала несколько).
  2. **Чем кончилась бы другая ФОРМА правила.** Для вето по синонимам след несёт всё, из
     чего форма считается: своё совпадение (`hit`), лидер словаря, попал ли лидер в круг
     кандидатов, на каком месте сам выбор. Поэтому три формы сравниваются задним числом.

🔴 ЧТО ЭТОТ ПРИБОР ДОКАЗАТЬ НЕ МОЖЕТ. Снятое вето не гарантирует ответа: дальше по пути
стоят выбор величины и гейт, и вопрос может стать уточнением уже там. Поэтому исход
«стал бы ответом» здесь — ВЕРХНЯЯ ГРАНИЦА, а не замер: он говорит, сколько ответов правило
съело, и какой из них был бы верным. Решает живой прогон `step4_bench.py`.

Использование:
    ASK_ENV_FILES=… python3 work/entity-choice/answer_rate_what_if.py <файл.jsonl>
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "ubuntu/serenedb"))
os.environ.setdefault("EMBED_BASE_URL", "-")
os.environ.setdefault("EMBED_MODEL", "-")
os.environ.setdefault("ASK_TOKEN", "probe")
import serene_ask as A  # noqa: E402

МЕХАНИЗМЫ = [("вето по синонимам", "unsupported_pick"),
             ("пара «регистр ← документ»", "writer_pair_unproven"),
             ("арбитр-детектор", "arbiter_detected"),
             ("величина (шаг 5)", "measure_ambiguous"),
             ("вопрос неполон (шаг 8)", "not_enough"),
             ("модель назвала несколько", "ambiguous")]


def main(path):
    fam = {}
    for r in A.psql("SELECT src_table, coalesce(nullif(parent,''), src_table) FROM %s"
                    % A.TABLES):
        if r and r[0]:
            fam[r[0]] = r[1]
    f = lambda t: fam.get(t, t)                                          # noqa: E731

    rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    счёт = {}
    вето, пара = [], []
    for d in rows:
        счёт[d["исход"]] = счёт.get(d["исход"], 0) + 1
        g = d.get("diag") or {}
        if d["исход"] != "СПРОСИЛ":
            continue
        имя = next((n for n, k in МЕХАНИЗМЫ if g.get(k)), "прочее")
        d["механизм"] = имя
        if g.get("unsupported_pick"):
            вето.append(d)
        if g.get("writer_pair_unproven"):
            пара.append(d)

    print("ИСХОДЫ ПРОГОНА: " + ", ".join("%s %d" % kv for kv in sorted(счёт.items())))
    print("\nПОИМЁННО, ЧЬЁ УТОЧНЕНИЕ (п. 21 требует разбора каждого):")
    по_мех = {}
    for d in rows:
        if d.get("механизм"):
            по_мех.setdefault(d["механизм"], []).append(d["n"])
    for имя, ns in sorted(по_мех.items(), key=lambda kv: -len(kv[1])):
        print("  %-28s %2d   вопросы: %s" % (имя, len(ns), ",".join(map(str, ns))))

    # ── Вето по синонимам: три формы правила, посчитанные по одному и тому же следу ──
    print("\nВЕТО ПО СИНОНИМАМ — что съедено и чем кончилась бы другая форма")
    print("  %-3s %-34s %-34s %s" % ("№", "выбор, который отвергли", "лидер словаря", "своё/лидер в круге/место"))
    формы = {"как сейчас (только лидер)": 0, "своё слово": 0,
             "лидер — из круга кандидатов": 0, "своё слово ИЛИ лидер из круга": 0}
    верно = dict.fromkeys(формы, 0)
    for d in вето:
        g = d["diag"]
        cand = g["unsupported_pick"]
        p = next((x for x in (g.get("alias_probe") or []) if x["cand"] == cand), None)
        if not p:
            print("  %-3d %-34s СЛЕДА НЕТ" % (d["n"], cand[:34]))
            continue
        совпал = f(cand) == f(d["эталон"])
        print("  %-3d %-34s %-34s hit=%s лидер_в_круге=%s место=%s %s"
              % (d["n"], cand[:34], (p["leader"] or "—")[:34], p["hit"],
                 p["leader_in_cands"], p["cand_rank"], "ЭТАЛОН" if совпал else "чужая"))
        исходы = {"как сейчас (только лидер)": False,
                  "своё слово": bool(p["hit"]),
                  "лидер — из круга кандидатов": not p["leader_in_cands"],
                  "своё слово ИЛИ лидер из круга": bool(p["hit"]) or not p["leader_in_cands"]}
        for k, ответил in исходы.items():
            if ответил:
                формы[k] += 1
                верно[k] += 1 if совпал else 0
    print("\n  форма правила                       ответов вернулось / из них верных / НЕВЕРНЫХ")
    for k in формы:
        print("    %-32s %2d / %2d / %d" % (k, формы[k], верно[k], формы[k] - верно[k]))

    # ── Арбитр-детектор: не шум ли развёл числа ──
    # Служебность сущности спрашивается у базы (`search_entity_class`, разметка тактом),
    # а не угадывается по имени: «constant_» — это наша конфигурация, а не свойство мира.
    cls = {r[0]: r[1] for r in A.psql("SELECT src_table, cls FROM search_entity_class")
           if r and r[0]}
    print("\nАРБИТР-ДЕТЕКТОР — из чего сложилось расхождение")
    сняли, осталось = 0, 0
    for d in rows:
        g = d.get("diag") or {}
        det = g.get("arbiter_detected")
        if not det:
            continue
        деловые = [(s, n) for s, n in zip(det["кандидаты"], det["числа"])
                   if cls.get(s) != "service"]
        служебные = [s for s in det["кандидаты"] if cls.get(s) == "service"]
        print("  %-3d %s" % (d["n"], d["вопрос"][:56]))
        for s, n in zip(det["кандидаты"], det["числа"]):
            print("      %-8s %-52s %s" % (cls.get(s, "?"), s[:52], n))
        if служебные and len(деловые) == 1:
            верно = f(деловые[0][0]) == f(d["эталон"])
            сняли += 1
            print("      → без служебных остаётся ОДИН: %s (%s)"
                  % (деловые[0][0], "ЭТАЛОН" if верно else "чужая"))
        elif служебные:
            осталось += 1
            print("      → без служебных остаётся %d деловых, расхождение %s"
                  % (len(деловые), A.answers_diverge(
                      [{"sum": n} if isinstance(n, float) else {"count": n}
                       for _s, n in деловые])))
    print("  ИТОГО: уточнений, где расхождение создавала служебная сущность и без неё "
          "остаётся один деловой кандидат — %d; где деловых остаётся больше одного — %d"
          % (сняли, осталось))

    # ── Пара «регистр ← документ» ──
    print("\nПАРА «РЕГИСТР ← ДОКУМЕНТ» — чем ответил соперник и совпало ли бы число")
    for d in пара:
        g = d["diag"]
        поч = {x["src"]: x for x in (g.get("arb_probe") or [])}
        свой = next((x for x in поч.values() if x["kind"] in ("answer", "figures")), None)
        соперник = поч.get(g["writer_pair_unproven"])
        print("  %-3d эталон %-40s" % (d["n"], f(d["эталон"])[:40]))
        print("      ответил : %s %s" % ((свой or {}).get("src", "—"),
                                         json.dumps((свой or {}).get("fig") or {},
                                                    ensure_ascii=False)[:110]))
        print("      соперник: %s kind=%s почему=%s величины=%s"
              % ((соперник or {}).get("src", "—"), (соперник or {}).get("kind"),
                 (соперник or {}).get("почему"), (соперник or {}).get("величины")))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
