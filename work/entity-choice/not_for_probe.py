#!/usr/bin/env python3
"""ПРИБОР ПРАВИЛА «НЕ ОТВЕЧАЕТ»: кого отсекает каждая форма — БЕЗ модели и без денег.

Зачем. Установочный агент пишет про каждую сущность `not_enough_for` («на что НЕ
отвечает»), и это знание не читается ни одной строкой сервиса ответов. Прежде чем
ставить отсев кандидатов в шаг 4, надо знать числом: какая форма сравнения отсекает
соседей-подмен из `SPEC_RETAIL_VS_SALES.md` и при этом не отсекает эталонную сущность
вопроса ни разу. Подстрока тут лжёт в обе стороны (`contains('склады','складов')`
ложна), поэтому сравнение — только словарём основ движка.

Что считает. Для каждой из 44 пар приёмки (вопрос → эталон из `entity_choice_bench`):
множество сущностей, отсекаемых каждой формой правила. Основы считает ДВИЖОК
(`ts_lexize` по `search_dict_stem`) — прибор лишь сравнивает множества. Печатает:
сколько эталонов отсечено (красная линия — ноль), сколько из 8 целевых
подмен отсечено, и медиану «залпа» (сколько сущностей форма выбрасывает на вопрос).

Формы (все — по левой части записи, до «—»: правая называет ЧУЖИЕ сущности и дала бы
переток по именам вроде «Приобретение Товаров Услуг»):
    A  любая общая основа (сырые основы вопроса, включая «и», «в», «не»)
    B  любая общая основа длиной >= 3 (служебные слова коротки — это факт языка,
       а не список слов и не порог по данным базы)
    C  не меньше ДВУХ общих основ длиной >= 3
    D  как B, но общая основа без вхождения в собственные `aliases` кандидата
       (прогноз по данным: убьёт и целевые случаи — у розницы «продаж» есть
       и в aliases; включена, чтобы отвергнуть замером, а не рассуждением)
    E  как B, но берётся только общая основа, не подтверждённая ПОЗИТИВНЫМ
       знанием кандидата целиком (`aliases` + собственное название +
       `best_used_for`). Смысл формы: «не отвечает» работает против слова,
       которое сущность сама о себе не заявляет; совпадение, заявленное и там,
       и там, — внутреннее противоречие данных, и такая запись в отсев не идёт.
       Никаких списков и порогов: оба множества приходят из данных самой базы.
    K1 пересечение записи с РОДОМ вопроса (`kind` шага 1 — модель описывает
       вопрос, и это единственный канал, сводящий «продали» и «продажа» к одному
       слову; живые kind взяты из следа боевого прогона)
    K4 предмет вопроса ЦЕЛИКОМ входит в одну отрицаемую запись (основы kind —
       подмножество основ левой части записи). Срабатывает ровно там, где
       вопрос ПОЛНОСТЬЮ про то, чего у сущности нет; многословный род
       («документы реализации товаров и услуг») защищён требованием всего
       подмножества — случайное слово вроде «услуг» отсев не даёт.
    K5 как K4, но запись берётся только когда её правая часть НЕ называет
       существоующую сущность базы. Форма записи у агента две: «аспект —
       Другая Сущность» (узкое: аспект живёт по соседству, а родовой вопрос
       сущность отвечает) и «тема — не в этом списке» (широкое: темы в записях
       нет вовсе). Указатель определяется СТРУКТУРНО, а не по фразе: правая
       часть сопоставляется с названиями из `search_tables` по основам.

Использование:
    ASK_ENV_FILES=… python3 work/entity-choice/not_for_probe.py [от] [до]
"""
import importlib
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "ubuntu/serenedb"))
sys.path.insert(0, os.path.join(ROOT, "work/acceptance"))
os.environ.setdefault("EMBED_BASE_URL", "-")
os.environ.setdefault("EMBED_MODEL", "-")
os.environ.setdefault("ASK_TOKEN", "bench")
SET_FILE = os.environ.get("SET_FILE", os.path.join(ROOT, "docs/ACCEPTANCE_UT.md"))

A = importlib.import_module("serene_ask")
B_ = importlib.import_module("entity_choice_bench")

TABLE = os.environ.get("ALIAS_TABLE", "search_entity_alias")
SPEC = os.environ.get("SPEC_FILE",
                     os.path.join(ROOT, "work/entity-choice/SPEC_RETAIL_VS_SALES.md"))


def _норм(текст):
    """Сравнение названий без регистра, пробелов и ё/е — метки из 1С пишутся иначе."""
    return re.sub(r"\s+", "", (текст or "").lower().replace("ё", "е"))


def _подмены():
    """Пары подмен — ИЗ ДОКУМЕНТА РАЗБОРА, а не из кода: таблица «что выбрано» в SPEC.

    Имён сущностей в коде нет: таблица читается из `SPEC_RETAIL_VS_SALES.md` (§1, «что
    выбрано» против эталона), а название сводится к src_table метками самой базы — так
    прибор переносим между базами. Счёт на уровне СУЩНОСТИ, а не семьи: отсев в бою
    убирает из перечня конкретную таблицу, и урон эталону — отсев его собственной
    таблицы, а не соседа.
    """
    метки = {r[0]: _норм(r[1]) for r in A.psql(
        "SELECT src_table, label FROM %s" % A.TABLES) if r and r[0]}
    цели = {}
    for ln in open(SPEC, encoding="utf-8"):
        ячейки = [c.strip() for c in ln.strip().strip("|").split("|")]
        if len(ячейки) != 4 or not ячейки[0].isdigit():
            continue
        выбрано = _норм(ячейки[2])
        нашлось = [t for t, nm in метки.items() if nm == выбрано]
        if нашлось:
            цели[int(ячейки[0])] = нашлось[0]
        else:
            print("⚠ подмена №%s: «%s» меткой не свелась — не считается"
                  % (ячейки[0], ячейки[2]))
    return цели


def основы(текст, мин=1):
    """Множество основ по словарю движка. `мин` — минимальная длина основы."""
    rs = A.psql("SELECT ts_lexize(%s, %s)" % (A.lit(A.STEM_DICT), A.lit(текст)))
    return {s for s in A._stem_set(rs[0][0] if rs else "") if len(s) >= мин}


def main():
    pairs = B_.pairs(SET_FILE)
    args = [a for a in sys.argv[1:] if a.isdigit()]
    lo = int(args[0]) if args else 1
    hi = int(args[1]) if len(args) > 1 else len(pairs)
    pairs = pairs[lo - 1:hi]
    fam = {r[0]: (r[1] or r[0]) for r in A.psql(
        "SELECT src_table, coalesce(nullif(parent,''), src_table) FROM %s" % A.TABLES)
        if r and r[0]}
    # Записи «не отвечает» — ОДНИМ запросом; берём и левую, и правую части:
    # правая нужна форме K5, чтобы отличить «аспект у соседа» от «темы нет вовсе».
    items = {}          # src_table -> [(левая, правая)]
    positive = {}       # src_table -> позитивное знание: aliases + label + best_used_for
    for r in A.psql(
            "SELECT a.src_table, trim(split_part(u.item, '—', 1)), "
            "       trim(split_part(u.item, '—', 2)), "
            "       a.aliases || ' ' || coalesce(t.label, '') || ' ' || a.best_used_for "
            "FROM %s a LEFT JOIN %s t ON t.src_table = a.src_table, "
            "     unnest(str_split(a.not_enough_for, ',')) AS u(item) "
            "WHERE a.not_enough_for IS NOT NULL AND trim(u.item) <> ''" % (TABLE, A.TABLES)):
        if not r or not r[0]:
            continue
        items.setdefault(r[0], []).append((r[1] or "", r[2] or ""))
        positive.setdefault(r[0], r[3] or "")
    # Названия сущностей базы — чем проверяется «правая часть называет соседа».
    label_stems = []
    for r in A.psql("SELECT label FROM %s WHERE label IS NOT NULL" % A.TABLES):
        if r and r[0]:
            st = основы(r[0], 3)
            if st:
                label_stems.append(st)
    item_stems = {}     # src_table -> [(основы левой, есть_указатель)]
    for t, пары in items.items():
        готовое = []
        for левая, правая in пары:
            правые = основы(правая, 3)
            указатель = any(st <= правые for st in label_stems) if правые else False
            готовое.append((основы(левая, 3), указатель))
        item_stems[t] = готовое
    alias_stems = {}
    for r in A.psql("SELECT src_table, aliases FROM %s" % TABLE):
        if r and r[0]:
            alias_stems[r[0]] = основы(r[1] or "", 3)
    pos_stems = {t: основы(x, 3) for t, x in positive.items()}
    # Живые `kind` шага 1 из следа боевого прогона: ровно те разборы, с которыми
    # система отвечала на этот набор. Для форм K* это честнее человеческой разметки.
    kinds = {}
    след = os.environ.get(
        "TRACE", os.path.join(ROOT, "work/acceptance/runs/2026-08-06-p21-F-headwins.jsonl"))
    if os.path.exists(след):
        import json
        for ln in open(след, encoding="utf-8"):
            try:
                d = json.loads(ln)
            except ValueError:
                continue
            k = (d.get("diag") or {}).get("kind") or ""
            if d.get("n") and k:
                kinds[int(d["n"])] = k

    формы = ("A", "B", "C", "D", "E", "K1", "K4", "K5")
    TARGETS = _подмены()
    счёт = {f: {"эталон": 0, "цель": 0, "залп": []} for f in формы}
    разбор_эталонов = []
    пойманные = {f: [] for f in формы}
    for i, (q, want) in enumerate(pairs, lo):
        q_all, q_long = основы(q, 1), основы(q, 3)
        k_stems = основы(kinds.get(i, ""), 3)
        эталон = fam.get(want, want)
        отсечено = {f: set() for f in формы}
        for t, стемы_записей in item_stems.items():
            for st, указатель in стемы_записей:
                if not st:
                    continue
                общие = st & q_long
                if st & q_all:
                    отсечено["A"].add(t)
                if общие:
                    отсечено["B"].add(t)
                    if общие - alias_stems.get(t, set()):
                        отсечено["D"].add(t)
                    if общие - pos_stems.get(t, set()):
                        отсечено["E"].add(t)
                if len(общие) >= 2:
                    отсечено["C"].add(t)
                if k_stems:
                    if st & k_stems:
                        отсечено["K1"].add(t)
                    if k_stems <= st:
                        отсечено["K4"].add(t)
                        if not указатель:
                            отсечено["K5"].add(t)
        семьи = {f: {fam.get(t, t) for t in отсечено[f]} for f in формы}
        for f in формы:
            счёт[f]["залп"].append(len(отсечено[f]))
            if want in отсечено[f]:              # урон = отсев САМОЙ эталонной таблицы
                счёт[f]["эталон"] += 1
                if f in ("B", "K4", "K5"):
                    разбор_эталонов.append((f, i, q, want))
            if i in TARGETS and TARGETS[i] in отсечено[f]:
                счёт[f]["цель"] += 1
                пойманные[f].append(i)
    print("словарь: %s, вопросов: %d, целевых подмен: %d\n" % (TABLE, len(pairs), len(TARGETS)))
    for f in формы:
        з = sorted(счёт[f]["залп"])
        медиана = з[len(з) // 2] if з else 0
        print("форма %-2s: эталонов отсечено %2d | целей поймано %2d/%d %-14s | залп медиана %d, макс %d"
              % (f, счёт[f]["эталон"], счёт[f]["цель"], len(TARGETS),
                 str(sorted(пойманные[f])), медиана, max(з) if з else 0))
    if разбор_эталонов:
        print("\nЭТАЛОНЫ, ОТСЕЧЁННЫЕ ФОРМАМИ B/K4 (красная линия):")
        for f, i, q, t in разбор_эталонов:
            print("  %-2s %2d. %-50s %s" % (f, i, q[:50], t))
    return 0


if __name__ == "__main__":
    sys.exit(main())
