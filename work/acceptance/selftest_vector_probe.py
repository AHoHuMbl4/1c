#!/usr/bin/env python3
"""ДОСЧЁТ СРЕДНЕЙ КОНФИГУРАЦИИ postgres: «вектор есть, словаря нет».

Зачем отдельный прибор. Живой прогон `selftest_surfaces.py` на postgres стартовал
ДО построения словаря синонимов, но прочитал его УЖЕ построенным (окно 3 успело
раньше сигнала) — и дал число конфигурации «словарь + вектор». Средняя
конфигурация «вектор без словаря» прогоном не снялась, а замок требует три числа.

Почему досчёт честный, а не новое измерение «примерно того же». В конфигурации
без словаря лексические поверхности уже измерены первым прогоном (он зафиксирован
в git, файл `…-surfaces-novector.jsonl`): поверхность `alias` при пустой таблице
по построению возвращает ноль, `card` и `literal` от словаря не зависят
(`wiki_alias.sh` пишет только в `search_entity_alias`/`search_measure_alias`,
карточки и корпус не трогает — проверено чтением скрипта). Слов у сущности в той
конфигурации одно — метка. Значит, средняя конфигурация отличается от первого
прогона ровно векторной фазой по этому же единственному слову — её и считает
этот прибор, той же продуктовой функцией `near_tables` и тем же боевым порогом
`MEANING_TOP`, что и основной прибор.

Вход: `runs/selftest-postgres-surfaces-novector.jsonl` (извлечён из коммита
первого замера, 43 недостигнутые сущности). Выход:
`runs/selftest-postgres-surfaces-vector-only.jsonl` — сущность, её метка, место
в полном векторном порядке, флаг достижимости вектором.

Использование:
    ASK_BASE=postgres python3 work/acceptance/selftest_vector_probe.py
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BASE = os.environ.get("ASK_BASE", "postgres")
RUNS = os.path.join(ROOT, "work", "acceptance", "runs")
SRC = os.path.join(RUNS, "selftest-%s-surfaces-novector.jsonl" % BASE)
OUT = os.path.join(RUNS, "selftest-%s-surfaces-vector-only.jsonl" % BASE)


def load_env(path):
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


load_env("/etc/1c-serene-ask-%s.env" % BASE)
load_env("/etc/1c-serene-ask.env")
load_env("/etc/1c-embed.env")
load_env("/etc/1c-mcp-reports.env")

sys.path.insert(0, os.path.join(ROOT, "ubuntu", "serenedb"))
import serene_ask as A  # noqa: E402

TOP = A.MEANING_TOP
FULL = 1000000


def main():
    rows = [json.loads(l) for l in open(SRC, encoding="utf-8")]
    misses = [r for r in rows if not r["reachable"]]
    par = {}
    for r in A.psql("SELECT src_table, coalesce(nullif(parent,''), src_table) "
                    "FROM %s" % A.TABLES):
        if r and r[0]:
            par[r[0]] = r[1]
    if not A.embed_model_live():
        raise SystemExit("эмбеддер не отвечает — досчёт бессмыслен, вектор не снять")
    out = []
    for r in misses:
        fam = par.get(r["src_table"]) or r["src_table"]
        word = (r["label"] or "").strip()
        rank = None
        if word:
            order = A.near_tables(word, FULL)
            seen = {}
            for i, t in enumerate(order):
                f = par.get(t) or t
                if f not in seen:
                    seen[f] = i + 1
            rank = seen.get(fam)
        out.append({"base": BASE, "src_table": r["src_table"], "label": r["label"],
                    "word": word, "vector_rank": rank,
                    "vector_reachable": bool(rank is not None and rank <= TOP)})
    with open(OUT, "w", encoding="utf-8") as fh:
        for rec in out:
            fh.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")
    got = sum(1 for r in out if r["vector_reachable"])
    print("%s: средняя конфигурация «вектор без словаря», порог топ-%d" % (BASE, TOP))
    print("  недостигнутых лексикой в первом прогоне: %d" % len(out))
    print("  из них вектор ДОСТАЛ: %d, осталось слепых: %d (%.1f%% от всех деловых)"
          % (got, len(out) - got, 100.0 * (len(out) - got) / len(rows)))
    for r in out:
        mark = "ДОСТИГНУТА" if r["vector_reachable"] else "мимо"
        print("  %-60s %-11s место=%s" % (r["src_table"], mark, r["vector_rank"]))
    print("-> %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
