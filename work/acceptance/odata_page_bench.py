#!/usr/bin/env python3
"""ПРИБОР: во что обходится размер страницы OData при чтении из 1С.

Зачем. [замер 05.08] такт свежести боевой базы шёл 2 ч 18 мин при норме 20 минут
(п. 17 `TARGET.md`), и 2940 с из них — чтение источников из 1С. Подозрение было на объём
данных, а оказалось — на ЧИСЛО ОБРАЩЕНИЙ: каждый заход к 1С стоит несколько секунд сам по
себе, и с ростом `$skip` дорожает ещё. Прибор меряет это на живой 1С и на настоящем коде
загрузчика (`fetch_all`), а не на упрощённой пробе.

🔴 Прибор ТОЛЬКО ЧИТАЕТ: ни витрина, ни 1С не меняются. Сверку числа строк между
размерами страницы прибор делает сам (`main`, сравнение `set(seen.values())`) и при
расхождении возвращает ненулевой код возврата — быстрее и верно это разные вещи.

Использование:
    python3 odata_page_bench.py <сущность> [<сущность> …]      # страницы 1000 и 10000
    ETL_PAGE_LIST=1000,5000,20000 python3 odata_page_bench.py <сущность>

Окружение берётся как у конвейера: /etc/1c-mcp-reports.env + /etc/1c-serene-pipeline-<база>.env
"""
import os, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
LOADER_DIR = os.environ.get("SERENE_SRC_DIR", "/srv/1c/ubuntu/serenedb")

CHILD = r'''
import os, sys, time
sys.path.insert(0, %r)
import poc_load_entity as L
es = sys.argv[1]
t0 = time.time()
rows = L.fetch_all(es)
print("%%d\t%%.2f" %% (len(rows), time.time() - t0))
'''


def measure(entity, page):
    """Один прогон в отдельном процессе: PAGE читается загрузчиком при импорте."""
    env = dict(os.environ, ETL_PAGE=str(page))
    r = subprocess.run([sys.executable, "-c", CHILD % LOADER_DIR, entity],
                       capture_output=True, text=True, env=env)
    if r.returncode != 0:
        return None, None, r.stderr.strip().splitlines()[-1][:120] if r.stderr else "ошибка"
    n, sec = r.stdout.strip().split("\t")
    return int(n), float(sec), ""


def main():
    ents = sys.argv[1:]
    if not ents:
        print(__doc__)
        return 2
    pages = [int(p) for p in os.environ.get("ETL_PAGE_LIST", "1000,10000").split(",")]
    bad = 0
    print("%-52s %8s %10s %10s %12s" % ("сущность", "страница", "строк", "секунд", "строк/с"))
    for es in ents:
        seen = {}
        for p in pages:
            n, sec, err = measure(es, p)
            if n is None:
                print("%-52s %8d   ОШИБКА: %s" % (es[:52], p, err))
                bad += 1
                continue
            seen[p] = n
            print("%-52s %8d %10d %10.2f %12.0f"
                  % (es[:52], p, n, sec, n / sec if sec else 0))
        # 🔴 Сверка держится здесь, кодом: расхождение числа строк между размерами
        # страницы поднимает `bad` и уводит код возврата в ненулевой.
        if len(set(seen.values())) > 1:
            print("   🔴 РАСХОЖДЕНИЕ ЧИСЛА СТРОК между размерами страницы: %s" % seen)
            bad += 1
    print("\nрасхождений и ошибок: %d" % bad)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
