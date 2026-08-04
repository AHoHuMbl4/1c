#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ПРИБОР ШАГА 3 (отбор смыслом и синонимами): доносит ли шаг верную сущность — НА ТОМ
ВХОДЕ, КАКОЙ ШАГ 3 ПОЛУЧАЕТ В БОЮ.

Зачем отдельный прибор, если есть `candidate_surfaces_bench`. Тот приближает шаг 1
словами самого вопроса — честно и бесплатно, но это НЕ ТОТ вход. В бою шаг 1 отдаёт
`terms` (значения, которые стоят в записи: имя контрагента, товар) и `kind` (род записей,
«о чём вопрос»), и род записей в `terms` намеренно НЕ кладётся. `[замер 04.08]` на
настоящих разборах (`runs/2026-08-04-intent-1-58-before.json`, прибор шага 1 соседней
сессии) `terms` пусты у **47 вопросов из 58**. А поверхность синонимов получает именно
`terms`: `alias_hits` на пустых выражениях возвращает пустоту первой же строкой. Отсюда и
расхождение: приближение прибора показывало у этой поверхности 43 %, а в бою она давала
5 % — восьмикратный разрыв между тем, что мерилось, и тем, что исполнялось.

Разбор вопроса здесь НЕ ПЕРЕСЧИТЫВАЕТСЯ: он читается из файла прогона прибора шага 1.
Поэтому прибор детерминирован и бесплатен, а числа сняты на настоящем входе. Файл
задаётся `INTENTS=<путь>`; вопросы, которых в нём нет, пропускаются и считаются отдельно.

🔴 Прибор НЕ повторяет логику продукта там, где она есть: `probe`, `match_expr`,
`tables_of`, `alias_hits`, `near_tables` зовутся из `serene_ask`. Своей здесь только та
логика, которой в продукте ЕЩЁ НЕТ, — испытываемые варианты входа и отсечки; выигравший
переносится в продукт, а не остаётся жить в приборе.

🔴 Табличная часть засчитывается за свой документ (`search_tables.parent`) — как и в
`entity_choice_bench` и `candidate_surfaces_bench`.

Запуск:
    sg 1c-secrets -c 'withenv.sh ut_test python3 work/acceptance/step3_bench.py'
Окружение: как у сервиса ответов нужной базы (DSN, PGPASSWORD, эмбеддер).
           INTENTS — файл разборов, DEEP — глубина для замера «насколько ниже отсечки».
"""
import importlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SET_FILE = os.environ.get("ACCEPTANCE_DOC", os.path.join(ROOT, "docs/ACCEPTANCE_UT.md"))
INTENTS = os.environ.get("INTENTS", os.path.join(
    ROOT, "work/acceptance/runs/2026-08-04-intent-1-58-before.json"))
DEEP = int(os.environ.get("DEEP", "50"))

sys.path.insert(0, os.path.join(ROOT, "ubuntu/serenedb"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.argv = [sys.argv[0], SET_FILE]

A = importlib.import_module("serene_ask")
B = importlib.import_module("entity_choice_bench")

TOP = A.MEANING_TOP
CARD_FIELDS = ("label", "aliases", "about", "quantities", "attrs")
ATTR_FIELDS = ("attrs",)


def intents_by_question(path):
    """Разборы шага 1 из файла прогона: вопрос → intent. Ключ — текст вопроса."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    out = {}
    for r in data.get("rows", []):
        q = (r.get("q") or "").strip()
        p = r.get("parse") or {}
        if q:
            out[q] = p
    return out


def groups_of(intent, use_terms=True, use_kind=False):
    """Понятия для отбора: значения из вопроса и/или род записей."""
    groups = []
    if use_terms:
        for g in (intent.get("terms") or []):
            g = [str(x) for x in (g if isinstance(g, list) else [g]) if str(x).strip()]
            if g:
                groups.append(g)
    if use_kind:
        kind = (intent.get("kind") or "").strip()
        if kind:
            groups.append([kind])
    return groups


def exprs_for(groups):
    """Выражения продуктовой функцией: отсечка по корпусу, как сегодня в бою."""
    if not groups:
        return []
    try:
        exprs, _ = A.probe(groups)
    except RuntimeError:
        return []
    return exprs


def hits(index, fields, exprs, limit):
    """Кандидаты по инвертированному индексу поверхности. Отбор и порядок ведёт движок.

    Форма запроса — штатная: `WHERE <поле> @@ <выражение>` по индексу как по отношению,
    скорер в `ORDER BY` (доки SereneDB, «Querying an inverted index» и «Ranking»:
    несколько полей в одном запросе объединяются через OR, скорер на индекс один).
    Разделитель равенства обязателен — иначе `LIMIT` режет по порядку исполнения.
    """
    if not exprs:
        return []
    expr = exprs[0] if len(exprs) == 1 else \
        "ts_compound(NULL, NULL, [%s], 1)" % ", ".join(exprs)
    cond = " OR ".join("%s @@ %s" % (f, expr) for f in fields)
    scorer = A.SCORERS.get(A.SCORER, A.SCORERS["bm25"]) % index
    try:
        return [r[0] for r in A.psql(
            "SELECT src_table, %s AS s FROM %s WHERE %s ORDER BY s DESC, src_table LIMIT %d"
            % (scorer, index, cond, limit)) if r and r[0]]
    except RuntimeError:
        return []



# --------------------------------------------------------------- доставка до шага 4
# 🔴 ЗАЧЕМ ОТДЕЛЬНЫЙ РАЗДЕЛ. Полнота поверхностей — ещё не доставка. При пустых `terms`
# буквальный отбор отдаёт НЕ пусто, а ВСЕ сущности (`tables_of` с пустым условием — это
# `GROUP BY` по всему корпусу), и дальше весь набор пересортировывается по близости
# ВЕКТОРА МЕТКИ к вопросу и роду. Порядок, добытый поверхностями шага 3, при этом
# теряется, а до модели доходит только голова списка. Значит мерить надо место эталона
# в ИТОГОВОМ порядке, а не факт «поверхность его нашла».
RRF_K = int(os.environ.get("RRF_K", "60"))


def interleave(orders):
    """Вперемежку: первый по вопросу, первый по роду, второй по вопросу… — как в продукте."""
    out, seen = [], set()
    if not orders:
        return out
    for i in range(max(len(o) for o in orders)):
        for o in orders:
            if i < len(o) and o[i] not in seen:
                seen.add(o[i])
                out.append(o[i])
    return out


def vec_order(table, cands, text):
    """Порядок кандидатов по близости вектора — тем же запросом, что в продукте."""
    if not text or not cands:
        return []
    try:
        return [r[0] for r in A.psql(
            "SELECT src_table FROM %s WHERE src_table IN (%s) AND emb IS NOT NULL "
            "ORDER BY emb <=> %s, src_table"
            % (table, ", ".join(A.lit(c) for c in cands), A._vec(text))) if r and r[0]]
    except RuntimeError:
        return []


def rrf(lists, extra_ranked=()):
    """Слияние рангов (Reciprocal Rank Fusion): 1/(k+место). Сравнивает МЕСТА, а не
    оценки разной природы — иначе счёт совпадений и косинус несопоставимы."""
    score = {}
    for lst in list(lists) + list(extra_ranked):
        for i, t in enumerate(lst):
            score[t] = score.get(t, 0.0) + 1.0 / (RRF_K + i + 1)
    return [t for t, _ in sorted(score.items(), key=lambda kv: (-kv[1], kv[0]))]


def main():
    par = {}
    for r in A.psql("SELECT src_table, coalesce(nullif(parent,''), src_table) FROM %s"
                    % A.TABLES):
        if r and r[0]:
            par[r[0]] = r[1]
    fam = lambda t: par.get(t) or t

    intents = intents_by_question(INTENTS)
    pairs = B.pairs(SET_FILE)

    # Каждый столбец — ОДИН вариант входа шага 3. «сегодня» — то, что исполняется в бою.
    names = [
        "буквально",              # tables_of по terms — не шаг 3, но нужен для суммы
        "синонимы:terms",         # сегодня
        "синонимы:kind",
        "синонимы:kind+terms",
        "карточка:все поля",
        "карточка:реквизиты",
        "смысл:kind|вопрос",      # сегодня
        "смысл:вопрос",
        "смысл:kind",
    ]
    hit = {n: 0 for n in names}
    deep_hit = {n: 0 for n in names}
    # Отсечка `MEANING_TOP` — бюджет, а не порог правильности: сколько кандидатов шаг 3
    # передаёт дальше. Меряем, где польза насыщается, вместо того чтобы назначить число.
    SWEEP = [int(x) for x in os.environ.get("SWEEP", "4,8,12,16,24,32,50").split(",")]
    SWEEP = [k for k in SWEEP if 0 < k <= DEEP]
    sweep_hit = {k: 0 for k in SWEEP}
    sweep_card = {k: 0 for k in SWEEP}
    sweep_added = {k: 0 for k in SWEEP}
    sweep_attr = {k: 0 for k in SWEEP}
    now_sum = new_sum = 0
    prod_hit = [0, 0]
    prod_added = [0]
    DELIVERY = os.environ.get('DELIVERY', '1') not in ('0', 'no')
    SHOWN = int(os.environ.get('SHOWN', '108'))   # сколько записей влезает в бюджет перечня
    deliv = {n: [0, 0] for n in ('метка (как в бою)', 'карточка', 'слияние рангов',
                                 'поверхности впереди', 'слияние без буквального',
                                 'слияние 4 + хвост по карточке',
                                 'ПРОДУКТ (как в бою)')}
    deliv_miss = {n: [] for n in deliv}
    deliv_top1 = {n: 0 for n in deliv}
    total = skipped = 0
    misses_now, rescued = [], []

    print("%-46s %s" % ("вопрос", " ".join("%d" % i for i in range(1, len(names) + 1))))
    for q, want in pairs:
        intent = intents.get(q.strip())
        if intent is None:
            skipped += 1
            continue
        total += 1
        wf = fam(want)
        g_terms = groups_of(intent, use_terms=True, use_kind=False)
        g_kind = groups_of(intent, use_terms=False, use_kind=True)
        g_both = groups_of(intent, use_terms=True, use_kind=True)
        e_terms, e_kind, e_both = exprs_for(g_terms), exprs_for(g_kind), exprs_for(g_both)
        preds = A._predicates(intent)
        match, km = A.match_expr(e_terms, preds)
        by_prod = A.tables_of(match, preds)
        kind = (intent.get("kind") or "").strip()

        # Каждая поверхность спрашивается ОДИН раз на глубину DEEP, а отсечка считается
        # префиксом этого списка. Так и дешевле (эмбеддинг вопроса не пересчитывается на
        # каждое k), и честнее: сравниваются одни и те же выдачи.
        deep_list = {
            # 🔴 РОВНО КАК В ПРОДУКТЕ: `tables_of` зовётся ВСЕГДА, и при пустом условии
            # это `GROUP BY` по всему корпусу, то есть ВСЕ сущности, а не пусто.
            "буквально": list(by_prod),
            "синонимы:terms": A.alias_hits(e_terms, DEEP),
            "синонимы:kind": A.alias_hits(e_kind, DEEP),
            "синонимы:kind+terms": A.alias_hits(e_both, DEEP),
            "карточка:все поля": hits("entity_card_idx", CARD_FIELDS, e_both, DEEP),
            "карточка:реквизиты": hits("entity_card_idx", ATTR_FIELDS, e_both, DEEP),
            "смысл:kind|вопрос": A.near_tables(kind or q, DEEP),
            "смысл:вопрос": A.near_tables(q, DEEP),
            "смысл:kind": A.near_tables(kind, DEEP) if kind else [],
        }
        # 🔴 ПРОДУКТОВЫЙ ПУТЬ ЦЕЛИКОМ: то же, что исполняет `answer`, тем же кодом.
        prod_full = A.meaning_candidates(e_terms, kind, q, TOP)
        prod = [t for t in prod_full if t not in by_prod]
        prod_ok = any(fam(t) == wf for t in prod) or any(fam(t) == wf for t in by_prod)
        # Частично совпавшие — поверхность ШАГА 2 (соседняя сессия, 04.08). В сумму она
        # входит, но к шагу 3 не относится: считаем её отдельно, чтобы не приписать себе
        # чужой прирост.
        try:
            part_lvl, _ = A.partial_tables(e_terms, preds, km)
        except Exception:                      # noqa: BLE001 — прибор не падает из-за соседей
            part_lvl = {}
        prod_all = prod_ok or any(fam(t) == wf for t in part_lvl)
        prod_hit[0] += 1 if prod_ok else 0
        prod_hit[1] += 1 if prod_all else 0
        prod_added[0] += len(prod)

        if DELIVERY:
            cands = list(dict.fromkeys(list(by_prod) + list(prod)))
            if not cands:
                cands = list(prod)
            lit_by_count = [t for t, _ in sorted(by_prod.items(),
                                                 key=lambda kv: (-kv[1], kv[0]))]
            variants = {
                "метка (как в бою)": interleave([vec_order(A.TABLES, cands, q),
                                                 vec_order(A.TABLES, cands, kind)]),
                "карточка": interleave([vec_order(A.CARD, cands, q),
                                        vec_order(A.CARD, cands, kind)]),
                "слияние рангов": rrf([
                    A.alias_hits(e_both, A.MEANING_TOP),
                    deep_list["карточка:все поля"][:A.MEANING_TOP],
                    deep_list["смысл:вопрос"][:A.MEANING_TOP],
                    deep_list["смысл:kind"][:A.MEANING_TOP],
                ], extra_ranked=[lit_by_count[:A.MEANING_TOP]] if lit_by_count else []),
            }
            # Поверхности шага 3 идут ВПЕРЕДИ своим порядком (слияние рангов), а всё
            # остальное — за ними по близости карточки. Смысл: то, что поверхность
            # НАШЛА, не должно вылетать из головы списка из-за пересортировки всего
            # набора по одному сигналу.
            # Слияние ТОЛЬКО четырёх поверхностей шага 3, без буквального счёта: ровно
            # то, что можно посчитать одним SQL внутри движка.
            four = rrf([
                A.alias_hits(e_both, A.MEANING_TOP),
                deep_list["карточка:все поля"][:A.MEANING_TOP],
                deep_list["смысл:вопрос"][:A.MEANING_TOP],
                deep_list["смысл:kind"][:A.MEANING_TOP],
            ])
            variants["слияние без буквального"] = four
            variants["слияние 4 + хвост по карточке"] = four + [
                t for t in variants["карточка"] if t not in set(four)]
            # Ровно то, что делает продукт после правки 04.08: голова — итог шага 3 в
            # порядке слияния (те из него, кто есть среди кандидатов), хвост — прежний
            # порядок по вектору карточки.
            in_c = set(cands)
            head_prod = [t for t in prod_full if t in in_c]
            variants["ПРОДУКТ (как в бою)"] = head_prod + [
                t for t in variants["карточка"] if t not in set(head_prod)]
            head = variants["слияние рангов"]
            variants["поверхности впереди"] = head + [
                t for t in variants["карточка"] if t not in set(head)]
            for vn, order_list in variants.items():
                pos = next((i for i, t in enumerate(order_list) if fam(t) == wf), None)
                if pos == 0:
                    deliv_top1[vn] += 1
                if pos is not None and pos < A.RERANK_TOP:
                    deliv[vn][0] += 1
                if pos is not None and pos < SHOWN:
                    deliv[vn][1] += 1
                else:
                    deliv_miss[vn].append((q, want, pos, len(order_list)))

        rank = {}
        for n in names:
            rank[n] = next((i for i, t in enumerate(deep_list[n]) if fam(t) == wf), None)
        # 🔴 Буквальный отбор отсечки НЕ ИМЕЕТ: в бою кандидатами становятся ВСЕ сущности,
        # где нашлись совпадения (`tables_of` отдаёт их множеством, без `LIMIT`). Считать
        # его префиксом ранжированного списка — значит мерить порядок, которого у него нет.
        if rank["буквально"] is not None:
            rank["буквально"] = 0
        got = {n: (rank[n] is not None and rank[n] < TOP) for n in names}
        deep = {n: (rank[n] is not None) for n in names}
        for n in names:
            hit[n] += 1 if got[n] else 0
            deep_hit[n] += 1 if deep[n] else 0
        for k in SWEEP:
            # Отсечка k у КАЖДОЙ поверхности испытываемого набора; буквальный отбор в
            # него не входит — он не шаг 3, но в сумму как слагаемое идёт всегда.
            ok = got["буквально"] or any(
                rank[n] is not None and rank[n] < k
                for n in ("синонимы:kind+terms", "смысл:вопрос", "смысл:kind"))
            sweep_hit[k] += 1 if ok else 0
            ok_card = ok or any(rank[n] is not None and rank[n] < k
                                for n in ("карточка:все поля",))
            sweep_card[k] += 1 if ok_card else 0
            ok_attr = ok or (rank["карточка:реквизиты"] is not None
                             and rank["карточка:реквизиты"] < k)
            sweep_attr[k] += 1 if ok_attr else 0
            # Цена отсечки: сколько сущностей шаг 3 ДОБАВЛЯЕТ к буквально найденным.
            # Именно они удлиняют перечень, который читает шаг 4, поэтому число нужно
            # назвать, а не оставить «где-то там подрастёт».
            lit_set = set(deep_list["буквально"])
            added = set()
            for n in ("синонимы:kind+terms", "смысл:вопрос", "смысл:kind"):
                added.update(t for t in deep_list[n][:k] if t not in lit_set)
            sweep_added[k] += len(added)

        now = got["буквально"] or got["синонимы:terms"] or got["смысл:kind|вопрос"]
        new = (now or got["синонимы:kind+terms"] or got["смысл:вопрос"]
               or got["смысл:kind"] or got["карточка:все поля"])
        now_sum += 1 if now else 0
        new_sum += 1 if new else 0
        if not now:
            misses_now.append((q, want))
            if new:
                rescued.append((q, want))
        print("%-46s %s" % (q[:46], " ".join("+" if got[n] else "." for n in names)))

    print("\nвопросов с эталонной сущностью и разбором: %d (пропущено без разбора: %d)"
          % (total, skipped))
    if not total:
        return 1
    print("\n%-22s %-14s %s" % ("поверхность", "в первых %d" % TOP, "в первых %d" % DEEP))
    for i, n in enumerate(names, 1):
        print("%d. %-19s %2d (%3d%%)     %2d (%3d%%)"
              % (i, n, hit[n], round(100.0 * hit[n] / total),
                 deep_hit[n], round(100.0 * deep_hit[n] / total)))
    print("\n🔴 ПРОДУКТОВЫМ КОДОМ (`meaning_candidates`, отсечка %d)" % TOP)
    print("  шаг 3 + буквальный отбор:            %d (%d%%)"
          % (prod_hit[0], round(100.0 * prod_hit[0] / total)))
    print("  он же вместе с частичными (шаг 2):   %d (%d%%)"
          % (prod_hit[1], round(100.0 * prod_hit[1] / total)))
    print("  кандидатов добавляет шаг 3 на вопрос: %.1f" % (1.0 * prod_added[0] / total))

    if DELIVERY:
        print("\n🔴 ДОСТАВКА ДО ШАГА 4: место эталона в ИТОГОВОМ порядке кандидатов")
        print("   (до реранкера доходит первых %d, до модели — около %d записей)"
              % (A.RERANK_TOP, SHOWN))
        for vn, (a, b) in deliv.items():
            print("  %-18s верхний: %2d (%3d%%)   в первых %d: %2d (%3d%%)   "
                  "в первых %d: %2d (%3d%%)"
                  % (vn, deliv_top1[vn], round(100.0 * deliv_top1[vn] / total),
                     A.RERANK_TOP, a, round(100.0 * a / total),
                     SHOWN, b, round(100.0 * b / total)))
            for q_, want_, pos_, ln_ in deliv_miss[vn]:
                print("        не доехал: %-46s → %-40s место %s из %d"
                      % (q_[:46], want_, pos_ if pos_ is not None else "нет", ln_))

    print("\nСУММА ПОВЕРХНОСТЕЙ ПО ОТДЕЛЬНЫМ ВАРИАНТАМ ВХОДА")
    print("  как в бою сегодня (буквально + синонимы:terms + смысл:kind|вопрос): %d (%d%%)"
          % (now_sum, round(100.0 * now_sum / total)))
    print("  с испытываемыми входами (+ синонимы:kind+terms + смысл:вопрос):     %d (%d%%)"
          % (new_sum, round(100.0 * new_sum / total)))
    print("\nОТСЕЧКА: сколько кандидатов шаг 3 отдаёт с каждой поверхности")
    print("  (сумма с буквальным отбором; «+карточка» — если добавить и её)")
    for k in SWEEP:
        print("  k=%-3d %2d (%3d%%)   +карточка целиком: %2d (%3d%%)   "
              "+только реквизиты: %2d (%3d%%)   добавлено сущностей: %.1f"
              % (k, sweep_hit[k], round(100.0 * sweep_hit[k] / total),
                 sweep_card[k], round(100.0 * sweep_card[k] / total),
                 sweep_attr[k], round(100.0 * sweep_attr[k] / total),
                 1.0 * sweep_added[k] / total))

    print("\nне доходили в бою (%d), из них спасены (%d):" % (len(misses_now), len(rescued)))
    res = {q for q, _ in rescued}
    for q, want in misses_now:
        print("   %-52s → %-42s %s" % (q[:52], want, "СПАСЁН" if q in res else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
