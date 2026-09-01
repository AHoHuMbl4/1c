"""Zone 17: Агрегаты и группы (aggregate-groups)."""
from __future__ import annotations

from ask._imports import *
from ask._wire import register_zone, apply_bindings

apply_bindings(globals())

def _vec(text):
    return "'[" + ",".join("%.6f" % x for x in embed_one(text)) + "]'::FLOAT[%d]" % EMBED_DIM


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def _numN(x):
    """Число или ОТСУТСТВИЕ числа — в отличие от `_num`, который отсутствие обращает в ноль.

    Нужен там, где разница между «посчитано и вышло 0» и «считать было нечего» — это
    разница между ответом и неверным ответом (п. 21). Пустое поле CSV означает NULL из
    базы, то есть агрегат по пустому множеству; `_num` вернул бы 0.0, и ноль стал бы
    неотличим от посчитанного.
    """
    if x is None or (isinstance(x, str) and not x.strip()):
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _sql_ident_col(name):
    return '"' + str(name).replace('"', '""') + '"'


def _live_measure_date_col(src_table):
    """Колонка даты витрины: Period (регистр) / Date / DateTime — имена платформы."""
    if not src_table:
        return None
    try:
        rows = psql(
            "SELECT column_name FROM duckdb_columns() "
            "WHERE table_name = %s AND lower(column_name) IN "
            "('period', 'date', 'datetime') "
            "ORDER BY CASE lower(column_name) "
            "WHEN 'period' THEN 0 WHEN 'date' THEN 1 ELSE 2 END"
            % lit(src_table))
    except RuntimeError:
        return None
    if rows and rows[0] and rows[0][0]:
        return rows[0][0]
    return None


def _live_column_exists(src_table, col):
    if not src_table or not col:
        return False
    try:
        r = psql(
            "SELECT 1 FROM duckdb_columns() "
            "WHERE table_name = %s AND column_name = %s LIMIT 1"
            % (lit(src_table), lit(col)))
    except RuntimeError:
        return False
    return bool(r and r[0])


def _live_std_excl_preds(src_table):
    """Предикаты isfolder/deletionmark — только при наличии колонки (duckdb_columns).

    Доки: Cookbook › Meta › duckdb_columns. Регистры колонок не имеют — список пуст.
    """
    out = []
    for flag in ("isfolder", "deletionmark"):
        if _live_column_exists(src_table, flag):
            out.append(
                "lower(cast(%s AS VARCHAR)) NOT IN ('true','t','1')"
                % _sql_ident_col(flag))
    return out


def _live_ref_key_col(src_table):
    """Фактическое имя колонки Ref_Key (регистр из duckdb_columns)."""
    if not src_table:
        return None
    try:
        r = psql(
            "SELECT column_name FROM duckdb_columns() "
            "WHERE table_name = %s AND lower(column_name) = 'ref_key' "
            "LIMIT 1" % lit(src_table))
    except RuntimeError:
        return None
    if r and r[0] and r[0][0]:
        return r[0][0]
    return None


def aggregate_live_row_count(src_table):
    """Живой count(*) строк витрины движения (регистр/документ).

    Доки: Sql › Functions › Utility › query_table.
    """
    if not src_table:
        return None
    pre = str(src_table).split("_", 1)[0].lower()
    if pre not in (
            "accumulationregister", "informationregister",
            "accountingregister", "document"):
        return None
    folder_pred = _live_std_excl_preds(src_table)
    wsql = (" WHERE " + " AND ".join(folder_pred)) if folder_pred else ""
    try:
        r = psql(
            "SELECT count(*) FROM query_table(%s)%s"
            % (lit(src_table), wsql))
    except RuntimeError:
        return None
    if not r or not r[0] or r[0][0] is None or r[0][0] == "":
        return None
    try:
        return int(_num(r[0][0]))
    except (TypeError, ValueError):
        return None


def aggregate_live_header_count(src_table):
    """Живой счёт строк каталога (grain=header при наличии Ref_Key) с исключениями 1С.

    Условие применимости — класс catalog + колонка ref_key (header). Счёт —
    count(*) витрины с isfolder/deletionmark (guarded), не корпусные counts
    детектора и не DISTINCT: [замер :8092] корпус 365, DISTINCT+excl 352,
    count(*)+excl 363 = SQL-эталон. Доки: Sql › Functions › Utility › query_table;
    Cookbook › Meta › duckdb_columns.
    """
    if not src_table:
        return None
    pre = str(src_table).split("_", 1)[0].lower()
    if pre != "catalog":
        return None
    if not _live_ref_key_col(src_table):
        return None
    folder_pred = _live_std_excl_preds(src_table)
    wsql = (" WHERE " + " AND ".join(folder_pred)) if folder_pred else ""
    try:
        r = psql(
            "SELECT count(*) FROM query_table(%s)%s"
            % (lit(src_table), wsql))
    except RuntimeError:
        return None
    if not r or not r[0] or r[0][0] is None or r[0][0] == "":
        return None
    try:
        return int(_num(r[0][0]))
    except (TypeError, ValueError):
        return None


def aggregate_live_column(src_table, preds, measure):
    """Итог по колонке витрины через query_table, когда nums корпуса пуст.

    Доки: Sql › Functions › Utility › query_table; Cookbook › Meta › duckdb_columns.
    Preds корпуса (doc_date) переписываются на try_cast(date_col).
    """
    if not src_table or not measure:
        return None
    if not _live_column_exists(src_table, measure):
        return None
    date_col = _live_measure_date_col(src_table)
    where = []
    for p in preds or []:
        ps = str(p)
        if "doc_date" in ps and date_col:
            where.append(ps.replace(
                "doc_date",
                "try_cast(%s AS TIMESTAMP)" % _sql_ident_col(date_col)))
        elif "doc_date" in ps:
            continue
        elif "src_table" in ps:
            continue
        else:
            # tsquery/match на витрине не работает — пропускаем
            if "@@" in ps or "ts_" in ps:
                continue
            where.append(ps)
    # Стандартные реквизиты 1С: группы и помеченные на удаление — не объекты
    # счёта. Колонки есть не во всех таблицах (регистры их не имеют), поэтому
    # каждый флаг добавляется только при наличии колонки (duckdb_columns).
    # Замер okna 30.08: count контрагентов 365 → 363 = живому SQL-эталону.
    folder_pred = _live_std_excl_preds(src_table)
    where.extend(folder_pred)
    m = "try_cast(%s AS DECIMAL(38,10))" % _sql_ident_col(measure)
    wsql = (" WHERE " + " AND ".join(where)) if where else ""
    try:
        r = psql(
            "SELECT count(*), sum(%(m)s), min(%(m)s), max(%(m)s), "
            "       CASE WHEN count(%(m)s) > 0 "
            "            THEN sum(%(m)s) / count(%(m)s) END, "
            "       count(%(m)s) "
            "FROM query_table(%(src)s)%(w)s"
            % {"m": m, "src": lit(src_table), "w": wsql})
    except RuntimeError:
        return None
    if not r or not r[0]:
        return None
    n_amount = int(r[0][5] or 0)
    if n_amount <= 0:
        return None
    return {
        "count": int(r[0][0] or 0),
        "sum": _numN(r[0][1]),
        "min": _numN(r[0][2]),
        "max": _numN(r[0][3]),
        "avg": None if _numN(r[0][4]) is None else round(_numN(r[0][4]), 2),
        "date_min": "",
        "date_max": "",
        "count_amount": n_amount,
        "src": src_table,
        "measure": measure,
        "out_of_range": 0,
        "folders": len(folder_pred),
        "scope": {"src": "query_table", "where": " AND ".join(where),
                  "folder_pred": " AND ".join(folder_pred),
                  "via": "live_column"},
    }


def aggregate(src_table, match, preds, measure=None):
    """Итог считается В БАЗЕ по ВСЕМУ подходящему множеству, без LIMIT.

    Это ключевое отличие от чанкового RAG: тот суммирует то, что попало в выборку,
    и выдаёт часть за целое. Здесь LIMIT влияет только на то, что покажем модели,
    но не на цифру.
    """
    if not src_table:
        return None
    where = [w for w in ([match] + preds + ["src_table = %s" % lit(src_table)]) if w]
    src = INDEX if match else CORPUS
    # Считаем не только итог: у каждой величины будет СВОЯ РОЛЬ, и гейт сверяет
    # число именно с той ролью, в которой оно названо. Иначе «настоящее число не от
    # тех строк» проходит: сумма одной строки, выданная за итог, гейту неотличима.
    # Величина названа по имени из данных. Нет величины — нет и агрегатов: пустой
    # результат честнее нуля, потому что ноль неотличим от «посчитано и получилось 0».
    m = ("map_extract(nums, %s)[1]" % lit(measure)) if measure else "NULL::DOUBLE"
    # 🔴 ПАПКА — НЕ ЗАПИСЬ. В справочнике 1С группа служит для раскладки по полкам, а не
    # описывает вещь: спрашивая «сколько позиций номенклатуры», человек считает товары, а не
    # папки. [замер 30.07] у `catalog_номенклатура` 252 строки, из них 25 групп → 227, ровно
    # столько, сколько объявляет приёмка. Прежде система отвечала 252 и была неверна.
    #
    # Признак — `IsFolder`, поле САМОЙ ПЛАТФОРМЫ 1С, того же класса, что `Ref_Key` и
    # `DataVersion`: одинаково на любой конфигурации и языке, это не слово о нашей базе.
    #
    # Безопасность правки проверена, а не предположена: [замер] группы есть всего у 26 из 697
    # сущностей; у партнёров и контрагентов их НОЛЬ, поэтому проверенные ответы 164 и 155 не
    # сдвигаются. Отдельным числом возвращается, сколько групп отброшено, — молчать об этом
    # нельзя (п. 13), и ответ обязан их назвать.
    # Обращение к РЕКВИЗИТУ по имени, а не поиск подстроки в тексте документа.
    # `flags` — типизированная карта булевых реквизитов, собирается движком при сборке
    # корпуса из колонок с kind='flag' (`corpus_build.sql`, is_flag). Отбор трёхзначный:
    # `coalesce(..., false)` означает «реквизита нет» = «не папка», и это верно как для
    # пустой карты, так и для NULL у сущностей, собранных упрощённым путём.
    # `IsFolder` — поле платформы 1С того же класса, что `Ref_Key`: не хардкод, а контракт
    # платформы. Механизм извлечения общий для ЛЮБОГО булева реквизита любой базы.
    folder_pred = "NOT coalesce(map_extract_value(flags, 'IsFolder'), false)"
    # 🔴 СЛОЖЕНИЕ DOUBLE НЕ ВОСПРОИЗВОДИМО, И ЭТО СВОЙСТВО ДВИЖКА, А НЕ НАШ НЕДОСМОТР.
    # Доки SereneDB, «Non-Deterministic Behavior → Floating-Point Aggregate Operations with
    # Multi-Threading»: «when the aggregation is split across multiple threads, the order in
    # which floating-point values are summed is not deterministic, so the low-order digits
    # vary»; там же у `sum(arg)` — «the floating-point versions of this function are affected
    # by ordering». То есть один и тот же вопрос к НЕИЗМЕННЫМ данным даёт разные числа, а
    # п. 3 контракта требует ровно обратного — «детерминированно на данных».
    #
    # [замер 04.08] `aggregate` вызван пять раз подряд без единой правки: у трёх пар из шести
    # сумма отличалась, и у одной РАЗНИЦА ДОХОДИЛА ДО ЧЕЛОВЕКА — четыре разных числа из пяти
    # прогонов (…771 648 / …774 720 / …778 816 / …796 224). Это не «последние разряды»: у
    # величин крупнее 2^53 разряд double грубее единицы, и расходятся видимые цифры ответа.
    #
    # Лечится штатной фиксированной запятой движка (доки, «Numeric → Fixed-Point Decimals»):
    # DECIMAL — «exact fixed-point decimal value», сложение точное и от порядка не зависит.
    # Выбор ширины и точности сделан ЗАМЕРОМ, а не на глаз [замер 04.08, 60 пар]:
    #   · DECIMAL(38,10) и DECIMAL(38,15) совпали на всех 60 парах — десяти знаков хватает,
    #     дальше уточнять нечего;
    #   · с DOUBLE разошлись ровно те 3 пары, где он и не воспроизводится, — то есть меняем
    #     мы только неверное;
    #   · цена: 39 мс против 12 мс у DOUBLE и 109 мс у штатного же `sum(x ORDER BY x)`,
    #     который тоже чинит порядок, но втрое дороже.
    # Запас разрядности: 28 цифр до запятой (1e28). Наибольшее значение базы 6,4e13, всех
    # значений 1,9 млн — до предела двенадцать порядков.
    #
    # `TRY_CAST`, а не `CAST`: значение, не влезшее в разрядность, обязано стать NULL, а не
    # уронить ответ целиком. Но молчать о нём нельзя (п. 13) — оно считается отдельно и
    # возвращается числом (`out_of_range`).
    d = ("TRY_CAST(%s AS DECIMAL(38,10))" % m) if measure else "NULL::DECIMAL(38,10)"
    # 🔴 `coalesce(…, 0)` УБРАН НАМЕРЕННО. Пустой агрегат — это «считать было нечего», и
    # ноль на его месте неотличим от посчитанного ответа. Требование записано прямо в
    # описании этой функции («пустой результат честнее нуля»), но в коде его не было:
    # множество, где величины нет ни у одной строки, давало `sum=min=max=avg=0`, и ответ
    # «0 ₽» проходил гейт — ноль ведь честно лежит в `agg`. Тот же класс, что и
    # тождественно нулевая величина (03.08), только через другую дверь: страж того правила
    # смотрит в `totals_of`, а тот при нуле строк со значением молчит.
    # Среднее считается ЗДЕСЬ ЖЕ из суммы и числа строк со значением, а не отдельным `avg`:
    # так оно по построению не может оказаться посчитанным по другому множеству.
    r = psql("SELECT count(*) FILTER (%(nf)s), sum(%(d)s) FILTER (%(nf)s), "
             "       min(%(d)s) FILTER (%(nf)s), "
             "       max(%(d)s) FILTER (%(nf)s), "
             "       CASE WHEN count(%(d)s) FILTER (%(nf)s) > 0 "
             "            THEN sum(%(d)s) FILTER (%(nf)s) "
             "                 / count(%(d)s) FILTER (%(nf)s) END, "
             "       coalesce(min(doc_date)::date::text,''), "
             "       coalesce(max(doc_date)::date::text,''), "
             "       count(%(d)s) FILTER (%(nf)s), "
             "       count(*) FILTER (NOT (%(nf)s)), "
             "       count(*) FILTER (%(nf)s AND %(m)s IS NOT NULL AND %(d)s IS NULL) "
             "FROM %(src)s WHERE %(w)s"
             % {"m": m, "d": d, "src": src, "w": " AND ".join(where), "nf": folder_pred})
    if not r or not r[0] or r[0][0] == "":
        live0 = aggregate_live_column(src_table, preds, measure) if measure else None
        return live0
    row = r[0] + [""] * (10 - len(r[0]))
    # count_amount отдельно от count: avg/sum посчитаны по строкам с суммой, и модель
    # обязана знать, по скольким. Иначе среднее по 31 строке уходит как среднее по 1344.
    n_amount = int(row[7] or 0)
    out = {"count": int(row[0]), "sum": _numN(row[1]), "min": _numN(row[2]),
            "max": _numN(row[3]),
            "avg": None if _numN(row[4]) is None else round(_numN(row[4]), 2),
            "date_min": row[5], "date_max": row[6],
            "count_amount": n_amount, "src": src_table,
            "measure": measure,
            # Значения, не влезшие в разрядность DECIMAL: в сумму они не вошли. Ноль у
            # любых мыслимых данных; не ноль — молчать нельзя (п. 13).
            "out_of_range": int(row[9] or 0),
            # 🔴 ШАГ ОБЪЯВЛЯЕТ, ПО КАКОМУ МНОЖЕСТВУ ПОСЧИТАЛ. Без этого число проверить
            # нечем: гейт сверяет ответ с ЭТИМ ЖЕ agg, то есть своё же число и подтвердит,
            # а живой замер вынужден верить на слово. Здесь лежит ровно то, что ушло в базу:
            # источник и полное условие вместе с отбрасыванием групп. По нему любой
            # посторонний прибор пересчитывает итог независимо и сравнивает (п. 3 —
            # «детерминированно на данных», п. 13 — потеря обязана быть видна).
            # Модели это не уходит: `diag` до неё не доходит вовсе (`mcp_ask.py` его не
            # читает), а внутренние имена таблиц туда и не должны попадать.
            "scope": {"src": src, "where": " AND ".join(where), "folder_pred": folder_pred},
            # Сколько групп отброшено из счёта. Ноль у подавляющего большинства сущностей;
            # где не ноль — ответ обязан это назвать, иначе получится молчаливая подмена
            # множества (п. 13).
            "folders": int(row[8] or 0)}
    # Мера есть в алиасах/витрине, в nums — NULL: fallback query_table
    # ([замер :8092] Всего на витрине, nums только Сумма=0).
    if measure and n_amount <= 0:
        live = aggregate_live_column(src_table, preds, measure)
        if live:
            return live
    return out



def src_is_child(src_table):
    """Табличная часть: у источника заполнен parent. Не имя, а контракт сборки."""
    if not src_table:
        return False
    try:
        r = psql("SELECT parent FROM %s WHERE src_table = %s LIMIT 1"
                 % (TABLES, lit(src_table)))
    except RuntimeError:
        return False
    return bool(r and r[0] and (r[0][0] or "").strip())


def refcols_of(src_table):
    """Оси группы выбранного источника: col → target_src. Нет таблицы — пусто."""
    if not src_table:
        return []
    try:
        rs = psql("SELECT col, target_src FROM search_refcols "
                  "WHERE src_table = %s AND col IS NOT NULL AND col <> '' "
                  "ORDER BY col" % lit(src_table))
    except RuntimeError:
        return []
    out = []
    for r in rs or []:
        if r and r[0]:
            out.append({"col": r[0], "target_src": (r[1] or "") if len(r) > 1 else ""})
    return out


def holders_of_target(target_src):
    """Держатели оси: src_table из search_refcols, где target_src = этот каталог."""
    if not target_src:
        return []
    try:
        rs = psql("SELECT src_table, col FROM search_refcols "
                  "WHERE target_src = %s AND src_table IS NOT NULL AND src_table <> '' "
                  "AND src_table <> %s AND col IS NOT NULL AND col <> '' "
                  "ORDER BY src_table, col"
                  % (lit(target_src), lit(target_src)))
    except RuntimeError:
        return []
    out, seen = [], set()
    for r in rs or []:
        if r and r[0] and r[1] and r[0] not in seen:
            seen.add(r[0])
            out.append({"src": r[0], "col": r[1]})
    return out


def measures_of_many(srcs):
    """Ключи nums по нескольким источникам — один запрос."""
    if not srcs:
        return {}
    try:
        rs = psql(
            "SELECT src_table, u.k FROM %s, unnest(map_keys(nums)) AS u(k) "
            "WHERE nums IS NOT NULL AND src_table IN (%s) GROUP BY 1, 2"
            % (CORPUS, ", ".join(lit(s) for s in srcs)))
    except RuntimeError:
        return {}
    out = {}
    for r in rs or []:
        if r and r[0] and len(r) > 1 and r[1]:
            out.setdefault(r[0], []).append(r[1])
    return out


def kind_axis_hits(axes, kind_text, meaning_ok=True):
    """kind → оси, чей target_src сходится с родом тем же путём, что выбор сущности.

    meaning_ok=False — только совпадение ПО ИМЕНАМ (label/aliases/best_used_for):
    смысловой мост («движения» ≈ «деятельности» по вектору) допустим, когда ось
    НАЗВАНА человеком (action_axis); для fallback-оси из рода записей он брал
    случайную ось регистра (замер 01.09: «движений в регистре реализациятмц» —
    ось «ВидДеятельности» по смыслу → «3 · Виды Деятельности» при эталоне
    78 537 строк).
    """
    kind_text = (kind_text or "").strip()
    axes = [a for a in (axes or []) if a.get("col")]
    if not kind_text or not axes:
        return []
    vals = ", ".join("(%s, %s)" % (lit(a["col"]), lit(a.get("target_src") or ""))
                     for a in axes)
    try:
        rs = psql(
            "WITH ax(col, target_src) AS (VALUES %s) "
            "SELECT DISTINCT ax.col FROM ax "
            "LEFT JOIN %s t ON t.src_table = ax.target_src "
            "LEFT JOIN search_entity_alias a ON a.src_table = ax.target_src "
            "WHERE list_has_any("
            "        list_filter(ts_lexize(%s, %s), x -> length(x) >= 3),"
            "        list_filter(ts_lexize(%s, concat_ws(' ', t.label, a.aliases, "
            "                                            a.best_used_for, ax.col)),"
            "                    x -> length(x) >= 3))"
            % (vals, TABLES, lit(STEM_DICT), lit(kind_text), lit(STEM_DICT)))
    except RuntimeError:
        rs = []
    hits = [r[0] for r in rs or [] if r and r[0]]
    if hits:
        return hits
    if not meaning_ok:
        return []
    # Основы не сошлись (товар ↛ номенклатура). Дальше — тот же путь, что выбор
    # сущности: смысл и словарь, пересечённые с target_src осей выбранного источника.
    try:
        found = set(meaning_candidates([], kind_text, kind_text, MEANING_TOP))
    except RuntimeError:
        found = set()
    return [a["col"] for a in axes if a.get("target_src") in found]


def kind_axis_rerank(axes, kind_text):
    """Род не сошёлся основами — реранкер по меткам target_src (тот же, что выбор сущности)."""
    kind_text = (kind_text or "").strip()
    axes = [a for a in (axes or []) if a.get("col")]
    if not kind_text or not axes:
        return []
    srcs = [a.get("target_src") for a in axes if a.get("target_src")]
    labs = {}
    if srcs:
        try:
            for r in psql("SELECT src_table, label FROM %s WHERE src_table IN (%s)"
                          % (TABLES, ", ".join(lit(s) for s in srcs))) or []:
                if r and r[0]:
                    labs[r[0]] = (r[1] or r[0]).strip()
        except RuntimeError:
            return []
    docs, cols = [], []
    for a in axes:
        docs.append(labs.get(a.get("target_src") or "", a["col"]))
        cols.append(a["col"])
    order = rerank(kind_text, docs)
    if not order:
        return []
    return [cols[order[0]]]


def term_ref_owners(groups):
    """Для каждой группы terms — owner'ы search_refmap, чьё имя совпало."""
    groups = list(groups or [])
    parts = []
    for gi, g in enumerate(groups):
        for alt in (g or []):
            if alt:
                parts.append("SELECT %d AS gi, %s AS alt" % (gi, lit(str(alt))))
    if not parts:
        return {}
    try:
        rs = psql(
            "WITH q AS (%s) "
            "SELECT DISTINCT q.gi, m.owner FROM q "
            "JOIN search_refmap m ON m.owner IS NOT NULL AND m.owner <> '' "
            " AND (lower(m.name) = lower(q.alt) "
            "      OR (length(q.alt) >= 3 AND lower(m.name) LIKE '%%' || lower(q.alt) || '%%') "
            "      OR list_has_any(list_filter(ts_lexize(%s, m.name), x -> length(x) >= 3),"
            "                      list_filter(ts_lexize(%s, q.alt), x -> length(x) >= 3)))"
            % (" UNION ALL ".join(parts), lit(STEM_DICT), lit(STEM_DICT)))
    except RuntimeError:
        return {}
    out = {}
    for r in rs or []:
        if r and r[1]:
            out.setdefault(int(r[0]), []).append(r[1])
    return out


def term_axis_hits(src_table, axes, groups):
    """Какие группы terms попали в какие оси выбранного источника."""
    groups = list(groups or [])
    axes = [a for a in (axes or []) if a.get("col")]
    if not src_table or not axes or not groups:
        return {}
    parts = []
    for gi, g in enumerate(groups):
        for alt in (g or []):
            if alt:
                parts.append("SELECT %d AS gi, %s AS alt" % (gi, lit(str(alt))))
    if not parts:
        return {}
    ax_sql = ", ".join("(%s, %s)" % (lit(a["col"]), lit(a.get("target_src") or ""))
                       for a in axes)
    try:
        rs = psql(
            "WITH q AS (%s), ax(col, target_src) AS (VALUES %s) "
            "SELECT DISTINCT q.gi, ax.col FROM q CROSS JOIN ax "
            "WHERE EXISTS ("
            "  SELECT 1 FROM search_refmap m "
            "  WHERE m.owner = ax.target_src AND ax.target_src <> '' "
            "    AND (lower(m.name) = lower(q.alt) "
            "         OR (length(q.alt) >= 3 AND lower(m.name) LIKE '%%' || lower(q.alt) || '%%') "
            "         OR list_has_any("
            "              list_filter(ts_lexize(%s, m.name), x -> length(x) >= 3),"
            "              list_filter(ts_lexize(%s, q.alt), x -> length(x) >= 3)))) "
            " OR EXISTS ("
            "  SELECT 1 FROM %s c "
            "  WHERE c.src_table = %s "
            "    AND lower(coalesce(map_extract_value(c.refs_map, ax.col), '')) = lower(q.alt))"
            % (" UNION ALL ".join(parts), ax_sql, lit(STEM_DICT), lit(STEM_DICT),
               CORPUS, lit(src_table)))
    except RuntimeError:
        return {}
    out = {}
    for r in rs or []:
        if r and r[1]:
            out.setdefault(int(r[0]), []).append(r[1])
    return out



def _group_leader(agg):
    """Значение первой группы после ORDER — лидер, не итог множества."""
    if not agg or agg.get("grain") != "group":
        return None
    if agg.get("leader") is not None:
        return agg["leader"]
    gs = agg.get("groups") or []
    if not gs:
        return None
    return gs[0].get("value")


def _group_fold(compute, measure):
    """Внутри группы: сумма меры (или счёт строк). max/min — порядок групп, не строка."""
    if (compute or "") == "count" or not measure:
        return "count"
    if (compute or "") == "avg":
        return "avg"
    return "sum"


def aggregate_groups(src_table, match, preds, measure, col, k, compute=None,
                     members=None):
    """GROUP BY оси ссылки. Тот же WHERE, что у aggregate. Без выгрузки строк.

    n_groups — по всему множеству, не K. sum — итог свёртки по всему base
    (stats.fold_sum), не значение первой группы. Лидер — поле leader.
    members — ровно эти ключи, без «топ остальных».
    """
    if not src_table or not col:
        return None
    try:
        k = int(k)
    except (TypeError, ValueError):
        k = ROWS_TO_MODEL
    k = max(1, min(k, ROWS_TO_MODEL))
    # Сравнение: члены оси — сам фильтр. match по тексту иначе оставляет одно имя
    # (11 строк Piesa) и второе имя в GROUP BY не входит.
    where = [w for w in (
        ([] if members else [match]) + list(preds or [])
        + ["src_table = %s" % lit(src_table)]) if w]
    # refs_map живёт на корпусе; search_idx INCLUDE его не несёт (corpus_init.sql).
    src = CORPUS
    folder_pred = "NOT coalesce(map_extract_value(flags, 'IsFolder'), false)"
    m = ("map_extract(nums, %s)[1]" % lit(measure)) if measure else "NULL::DOUBLE"
    d = ("TRY_CAST(%s AS DECIMAL(38,10))" % m) if measure else "NULL::DECIMAL(38,10)"
    gexpr = "map_extract_value(refs_map, %s)" % lit(col)
    mem_pred = "TRUE"
    if members:
        parts = []
        for x in members:
            if not str(x).strip():
                continue
            parts.append(
                "list_has_all("
                "list_filter(ts_lexize(%s, coalesce(g, '')), s -> length(s) >= 3),"
                "list_filter(ts_lexize(%s, %s), s -> length(s) >= 3))"
                % (lit(STEM_DICT), lit(STEM_DICT), lit(str(x))))
        if parts:
            mem_pred = "(" + " OR ".join(parts) + ")"
    fold = _group_fold(compute, measure)
    if fold == "count":
        ord_expr = "n"
    elif fold == "avg":
        ord_expr = "a"
    else:
        ord_expr = "s"
    direction = "ASC" if (compute or "") == "min" else "DESC"
    sql = (
        "WITH base AS ("
        "  SELECT %(g)s AS g, %(d)s AS d, %(m)s AS mraw FROM %(src)s "
        "  WHERE %(w)s AND %(nf)s"
        "), stats AS ("
        "  SELECT count(*) AS n_rows, count(DISTINCT g) AS n_groups,"
        "         count(d) AS n_amt, sum(d) AS fold_sum FROM base"
        "), folded AS ("
        "  SELECT g, count(*) AS n, sum(d) AS s, min(d) AS mn, max(d) AS mx,"
        "         CASE WHEN count(d) > 0 THEN sum(d) / count(d) END AS a,"
        "         count(d) AS n_amt,"
        "         count(*) FILTER (mraw IS NOT NULL AND d IS NULL) AS oor "
        "  FROM base WHERE %(mem)s GROUP BY g"
        ") "
        "SELECT f.g, f.n, f.s, f.mn, f.mx, f.a, f.n_amt, f.oor, "
        "       st.n_rows, st.n_groups, st.n_amt, st.fold_sum "
        "FROM folded f, stats st "
        "ORDER BY %(ord)s %(dir)s NULLS LAST, f.g "
        "LIMIT %(k)d"
        % {"g": gexpr, "d": d, "m": m, "src": src, "w": " AND ".join(where),
           "nf": folder_pred, "mem": mem_pred, "ord": ord_expr, "dir": direction,
           "k": k})
    try:
        rs = psql(sql)
    except RuntimeError:
        return None
    groups = []
    n_rows = n_groups = n_amt_all = 0
    oor = 0
    fold_sum = None
    for row in rs or []:
        row = list(row) + [None] * (12 - len(row))
        n_rows = int(row[8] or 0)
        n_groups = int(row[9] or 0)
        n_amt_all = int(row[10] or 0)
        fold_sum = _numN(row[11])
        oor += int(row[7] or 0)
        val = _numN(row[2]) if fold == "sum" else (
            _numN(row[5]) if fold == "avg" else int(row[1] or 0))
        if fold == "avg" and val is not None:
            val = round(val, 2)
        groups.append({"name": row[0] or "", "value": val, "count": int(row[1] or 0),
                       "sum": _numN(row[2]), "avg": None if _numN(row[5]) is None
                       else round(_numN(row[5]), 2)})
    leader = groups[0]["value"] if groups else None
    if fold == "sum":
        total = fold_sum
    elif fold == "avg" and fold_sum is not None and n_amt_all:
        total = round(fold_sum / n_amt_all, 2)
    else:
        total = None
    return {"count": n_rows, "n_groups": n_groups, "groups": groups,
            "sum": total, "leader": leader,
            "min": None, "max": None, "avg": None,
            "count_amount": n_amt_all,
            "src": src_table, "measure": measure, "out_of_range": oor,
            "grain": "group", "col": col, "k": k,
            "scope": {"src": src, "where": " AND ".join(where),
                      "folder_pred": folder_pred, "group_col": col},
            "folders": 0}



register_zone('ask.z17_aggregate_groups', globals())
