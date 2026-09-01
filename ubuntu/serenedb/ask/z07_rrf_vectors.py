"""Zone 07: RRF и векторы (rrf-vectors)."""
from __future__ import annotations

from ask._imports import *
from ask._wire import register_zone, apply_bindings

apply_bindings(globals())

def _corpus_ivf_ready():
    """Есть ли IVF по корпусу и векторы той же модели — для ветви Ф6.1."""
    hit = _CORPUS_IVF_CACHE.get("ok")
    if hit is not None and time.time() - hit[1] < 60:
        return hit[0]
    ok = False
    if emb_ready(CORPUS):
        try:
            ok = bool(psql(
                "SELECT 1 FROM duckdb_indexes() WHERE index_name = %s LIMIT 1"
                % lit(CORPUS_IVF_IDX)))
        except RuntimeError:
            ok = False
    _CORPUS_IVF_CACHE["ok"] = (ok, time.time())
    return ok


def _resolver_ivf_ready():
    """Есть ли IVF по резолверу значений — для пути Ф6.2.

    Спрашиваем через `_resolver_psql` (роль `serene_resolver`), не через
    `psql`/`serene_ro`: к `resolver_index` / его IVF у `serene_ro` доступа нет.
    Нет индекса или роли — False, вызывающий тихо уходит в exact.
    """
    hit = _RESOLVER_IVF_CACHE.get("ok")
    if hit is not None and time.time() - hit[1] < 60:
        return hit[0]
    ok = False
    if emb_ready("resolver_index"):
        try:
            ok = bool(_resolver_psql(
                "SELECT 1 FROM duckdb_indexes() WHERE index_name = %s LIMIT 1"
                % lit(RESOLVER_IVF_IDX)))
        except RuntimeError:
            ok = False
    _RESOLVER_IVF_CACHE["ok"] = (ok, time.time())
    return ok


def _rrf_entity_branches(exprs, kind_text, question, limit):
    """Четыре ветви сущностей для RRF — alias, card, near(question), near(kind)."""
    expr = None
    if exprs:
        expr = exprs[0] if len(exprs) == 1 else             "ts_compound(NULL, NULL, [%s], 1)" % ", ".join(exprs)
    branches = []
    if expr:
        branches.append(
            "SELECT src_table, RANK() OVER (ORDER BY s DESC, src_table) AS rank FROM ("
            "SELECT src_table, %s AS s FROM %s WHERE aliases @@ %s "
            "ORDER BY s DESC, src_table LIMIT %d) t"
            % (SCORERS.get(SCORER, SCORERS["bm25"]) % ALIAS_INDEX, ALIAS_INDEX, expr, limit))
        branches.append(
            "SELECT src_table, RANK() OVER (ORDER BY s DESC, src_table) AS rank FROM ("
            "SELECT src_table, %s AS s FROM %s WHERE %s "
            "ORDER BY s DESC, src_table LIMIT %d) t"
            % (SCORERS.get(SCORER, SCORERS["bm25"]) % CARD_INDEX, CARD_INDEX,
               " OR ".join("%s @@ %s" % (f, expr) for f in CARD_FIELDS), limit))
    src = CARD if emb_ready(CARD) else (TABLES if emb_ready(TABLES) else "")
    if src:
        for text in (question, kind_text):
            if not text:
                continue
            try:
                vec = _vec(text)
            except RuntimeError:
                continue
            branches.append(
                "SELECT src_table, RANK() OVER (ORDER BY d, src_table) AS rank FROM ("
                "SELECT src_table, emb <=> %s AS d FROM %s WHERE emb IS NOT NULL "
                "ORDER BY d, src_table LIMIT %d) t" % (vec, src, limit))
    return branches


def _rrf_corpus_branch(vec, limit):
    """Пятая ветвь: kNN по corpus_ivf_idx, агрегат по src_table (без WHERE emb)."""
    return (
        "SELECT src_table, RANK() OVER (ORDER BY cnt DESC, src_table) AS rank FROM ("
        "SELECT src_table, count(*) AS cnt FROM ("
        "SELECT src_table FROM %s ORDER BY emb <#> %s, src_table, row_key LIMIT %d"
        ") t GROUP BY src_table ORDER BY cnt DESC, src_table LIMIT %d) t2"
        % (CORPUS_IVF_IDX, vec, TOPK, limit))


def _fused_sql_rrf(branches, limit):
    """Oneshot SQL-RRF по шаблону доков (Hybrid Search › Score fusion)."""
    sql = ("WITH fused AS (%s) SELECT src_table, SUM(1.0/(%d + rank)) AS rrf "
           "FROM fused GROUP BY src_table ORDER BY rrf DESC, src_table LIMIT %d"
           % (" UNION ALL ".join(branches), RRF_K, limit * len(branches)))
    return [r[0] for r in psql(sql) if r and r[0]]


def _fused_python_rrf(branches, limit):
    """Python-RRF: каждая ветвь отдельно, слияние SUM(1/(k+rank)) — этalon/fallback."""
    scores = {}
    for branch in branches:
        try:
            rows = psql(
                "SELECT src_table FROM (%s) b ORDER BY rank, src_table" % branch)
        except RuntimeError:
            continue
        for rank, row in enumerate(rows or [], start=1):
            if row and row[0]:
                src = row[0]
                scores[src] = scores.get(src, 0) + 1.0 / (RRF_K + rank)
    if not scores:
        return None
    cap = limit * len(branches)
    return sorted(scores, key=lambda t: (-scores[t], t))[:cap]


def _fused_candidates(exprs, kind_text, question, limit, diag=None):
    """Те же четыре поверхности, но СЛИТЫЕ ПО МЕСТАМ и ОДНИМ ЗАПРОСОМ внутри движка.

    🔴 Зачем слияние. Порядок, в котором кандидаты уходят дальше, решает, что вообще
    увидит модель: набор режется бюджетом перечня (`[замер 04.08]` живой ответ показал
    100 записей из 1502). Простая склейка «одна поверхность за другой» ставит вперёд ту,
    что оказалась первой в коде, а слияние ставит вперёд то, на чём поверхности СОШЛИСЬ.
    `[замер 04.08]`, 44 пары приёмки, настоящие разборы шага 1, глубина перечня как в бою:
    эталон доходит до модели 43 из 44 при склейке и **44 из 44** при слиянии, а верхним
    кандидатом оказывается верный 16 раз против 10.

    🔴 Считает БАЗА, а не питон: ранги ветвей и их сумма — один SQL по шаблону доков
    SereneDB («Cookbook → Search → Reciprocal Rank Fusion»): `RANK()` в каждой ветви,
    `SUM(1.0/(k + rank))` снаружи. Оттуда же `k = 60` — умолчание исходной статьи и
    Elasticsearch, а не подобранное нами число. Скорер стоит во ВЛОЖЕННОМ запросе, а
    агрегат снаружи: движок не даёт считать `bm25`/`tfidf` в одном запросе с `GROUP BY`
    (`techContext`, разбор у `serene_ask`).

    Ветвей четыре, каждая со своим окном `limit`: синонимы, слова карточки, смысл вопроса,
    смысл рода записей. Отсутствующая ветвь просто не даёт слагаемых — как и написано в
    доках («A document missing from a branch contributes nothing»).

    Возвращает `None`, если ни одна ветвь не собралась: тогда зовущий откатывается на
    прежний путь, а не остаётся без кандидатов.
    """
    branches = _rrf_entity_branches(exprs, kind_text, question, limit)
    if not branches:
        return None
    if ASK_SQL_RRF and _corpus_ivf_ready():
        try:
            qvec = _vec(question)
        except RuntimeError:
            qvec = None
        if qvec:
            branches = list(branches) + [_rrf_corpus_branch(qvec, limit)]
            try:
                out = _fused_sql_rrf(branches, limit)
                if diag is not None:
                    diag["sql_rrf"] = True
                return out
            except RuntimeError:
                if diag is not None:
                    diag["sql_rrf_fallback"] = True
                branches = _rrf_entity_branches(exprs, kind_text, question, limit)
                try:
                    return _fused_python_rrf(branches, limit)
                except RuntimeError:
                    return None
    try:
        return _fused_sql_rrf(branches, limit)
    except RuntimeError:
        return None


def near_tables(text, limit):
    """Сущности, чьи НАЗВАНИЯ ближе всего к вопросу по смыслу. Ранжирует движок.

    Мост через словарный разрыв: в 1С продажа называется «реализация», и буквально эти
    слова не совпадут никогда. [замер 03.08] `ts_phrase('продали')` по всему корпусу даёт
    4 строки в трёх каталогах вариантов отчётов — чистый шум.

    Сигнал сам по себе слабый (эмбеддинг не связывает «продажи» с «Реализация Товаров
    Услуг» и ставит выше «Склады»), поэтому он и НЕ РЕШАЕТ: он только доносит кандидата
    до реранкера, который силён именно на паре «вопрос ↔ название» ([замер 02.08] верная
    сущность первой в 14 % случаев без него и в 36 % с ним).

    Цена замерена и она решает, что можно складывать, а что нет `[замер 03.08]`:
    здесь 52 мс на 1 502 метки, а тот же приём по КОРПУСУ — 4,6 с на 623 565 строк,
    потому что векторного индекса нет ни одного (`ivf` заблокирован,
    `VECTOR_DECISION.md`) и kNN идёт полным сканом. Поэтому по меткам складываем всегда,
    а по корпусу оставляем запасным путём — см. разбор у места вызова.
    """
    if not text:
        return []
    # 🔴 КАРТОЧКА ПРЕДПОЧТИТЕЛЬНЕЕ МЕТКИ — ПО ЗАМЕРУ, А НЕ ПО ВКУСУ.
    # [замер 03.08] `entity_choice_bench.py`, 44 пары, реранкер включён в обоих прогонах,
    # отличается только таблица вектора: до реранкера верная сущность доходит **31 из 44
    # (70 %)** против **23 из 44 (52 %)** у метки, в первой пятёрке 27 против 22. Верх
    # списка почти не сдвинулся (+1) — там распоряжается реранкер; выросла именно ГЛУБИНА
    # отбора, то есть та половина дефекта, где реранкер бессилен: он выбирает только из
    # того, что ему дали. Прибор детерминирован, разброса у него нет.
    # Нет карточки или её векторы посчитаны другой моделью — работаем по метке, как
    # раньше. Ни падения, ни молчаливой подмены: `emb_ready` без отметки говорит «нет».
    src = CARD if emb_ready(CARD) else (TABLES if emb_ready(TABLES) else "")
    if not src:
        return []
    try:
        return [r[0] for r in psql(
            "SELECT src_table FROM %s WHERE emb IS NOT NULL "   # см. `resolve_near`
            "ORDER BY emb <=> %s, src_table LIMIT %d"
            % (src, _vec(text), limit)) if r and r[0]]
    except RuntimeError:
        return []                       # эмбеддер лёг — остаётся буквальный отбор


def rows_of(src_table, match, preds, limit, measure=None):
    """Строки одного источника: САМА строка, а рядом — подсветка совпадения.

    Раньше модели уходила ТОЛЬКО подсветка. Она по устройству отдаёт фрагменты вокруг
    совпавших слов, а не строку: замерено — 144 символа при длине строки 398. Реквизит,
    оказавшийся дальше от совпадения, до модели не доходил вовсе. Живая проверка: ИНН
    контрагента стоит на 367-м символе, вопрос «какой ИНН у Дон-Агро» получал ответ
    «данных нет» при том, что значение есть и в витрине, и в корпусе, и в индексе.
    Подсветка остаётся — она показывает, ГДЕ совпало, — но данные берутся из строки.

    🔴 ПОКАЗАНО = ПОСЧИТАНО. Строки уходят модели, а числа считает `aggregate`; множество у
    них одно. Здесь папки справочника прежде не отбрасывались, а в счёте отбрасываются, и
    множества расходились молча: [замер 04.08] на отборе из 94 строк-групп модели ушло 40
    записей, а счёт по ним дал `count=0, sum=0`. Хуже самого нуля то, что гейт такую
    подмену пропускает по построению: он сверяет названное число со строками, а строки —
    вот они, показаны. Значит модель могла процитировать величину записи, которой в счёте
    нет. Признак тот же, что в счёте (`IsFolder`, поле платформы 1С), и разойтись они
    больше не могут. Число отброшенных групп называет ответ — его считает `aggregate`
    (`folders`), а требует `asked_figure_missing`.
    """
    where = [w for w in ([match] + preds) if w] + ["src_table = %s" % lit(src_table),
             "NOT coalesce(map_extract_value(flags, 'IsFolder'), false)"]
    src = INDEX if match else CORPUS
    frag = ("ts_highlight(doc, 'MaxWords=14,MaxFragments=2,StartSel=[,StopSel=]') "
            "|| ' | ' || doc" if match else "doc")
    order = ((SCORERS.get(SCORER, SCORERS["bm25"]) % INDEX) + " DESC") if match \
        else (("map_extract(nums, %s)[1] DESC NULLS LAST" % lit(measure)) if measure
              else "row_key")
    return psql(
        "SELECT row_key, src_table, coalesce(%s,0), coalesce(doc_date::date::text,''), "
        "       0 AS s, %s FROM %s WHERE %s ORDER BY %s LIMIT %d"
        % (("map_extract(nums, %s)[1]" % lit(measure)) if measure else "NULL::DOUBLE",
           frag, src, " AND ".join(where), order + ", row_key", limit))


def signal_terms(src_table, match, top):
    """Чем ЭТОТ источник отличается от базы в целом — по его совпадениям.

    Штатный рецепт движка (cookbook/search/significant-terms.test): частота терма в
    подмножестве против ожидаемой по фону. Считаем по полю `refs` — это ссылки на
    другие объекты, их словарь в шесть раз меньше словаря всей строки (11 744 против
    71 604 термов) и в пять раз дешевле при том же разделении.

    Зачем: два источника могут иметь ОДИНАКОВОЕ число совпадений по имени контрагента,
    и выбирать модели не из чего. Отличительные реквизиты дают ей то, чего нет в
    названии: у реализации это склад и расчёты с покупателями, у поступления на счёт —
    банк и счёт организации. Это данные из индекса, а не правило в подсказке.
    """
    where = " AND ".join([w for w in [match, "src_table @@ %s" % lit(src_table)] if w])
    try:
        rs = psql(
            "WITH bg AS (SELECT unnest(ts_dict_agg(refs)) t, unnest(ts_dict_count(refs)) b"
            "            FROM %(i)s),"
            "     fg AS (SELECT unnest(ts_dict_agg(refs)) t, unnest(ts_dict_count(refs)) f"
            "            FROM %(i)s WHERE %(w)s),"
            "     n  AS (SELECT (SELECT count(*) FROM %(i)s WHERE %(w)s) ft,"
            "                   (SELECT count(*) FROM %(i)s) bt)"
            # Разделитель равенства `fg.t` обязателен по той же причине, что у `_fetch`:
            # отобранные термы уходят в подсказку модели («typical for these records») и в
            # варианты уточнения, поэтому ничья на срезе меняла бы ВХОД выбора сущности.
            # [замер 03.08] на семи соперниках вопроса «сколько всего мы продали» ничьи
            # нашлись у двух (1 и 2 в первой шестёрке). Терм уникален в `fg` (`ts_dict_agg`
            # отдаёт словарь), значит порядок полный.
            " SELECT fg.t FROM fg JOIN bg USING (t) CROSS JOIN n"
            " ORDER BY fg.f - bg.b * n.ft::DOUBLE / nullif(n.bt,0) DESC, fg.t LIMIT %(k)d"
            % {"i": INDEX, "w": where, "k": top})
    except RuntimeError:
        return []
    return [r[0] for r in rs if r and r[0]]


CLARIFY_SYS = """The question can be answered from several kinds of records, and the
answers would differ. Ask the person ONE short question to find out which they meant.

Rules:
- Ask in the SAME language the question was asked in.
- Describe each option in plain business words, using its name and what is typical for
  its records. Never show table names, codes or internal identifiers.
- One sentence, no preamble, no apology. End with a question mark."""


def clarify_text(question, opts):
    """Уточняющий вопрос формулирует МОДЕЛЬ — на языке спрашивающего.

    Своей прозой это писать нельзя: она была бы на одном языке независимо от языка
    вопроса (тот же дефект, что и с русскими умолчаниями ответа). Данные для фразы
    уже посчитаны — названия источников и их отличительные реквизиты, — выдумывать
    модели нечего.
    """
    body = "Question: %s\n\nOptions:\n" % question + "\n".join(
        "- %s%s" % (o["label"],
                    "" if not o["distinct_by"] else " (typical: %s)" % o["distinct_by"])
        for o in opts)
    try:
        return (ds_chat([{"role": "system", "content": CLARIFY_SYS},
                         {"role": "user", "content": body}], max_tokens=120) or "").strip()
    except Exception:                          # noqa: BLE001 — сеть/квота
        return ""                              # вызывающий сформулирует сам по options


# Формулировка нарочно НЕ говорит «данных нет»: этот же отказ уходит и там, где данные
# есть и посчитаны, а не прошла проверку формулировка модели. Сказать «нет данных» в
# таком случае — соврать клиенту.
REFUSE_SYS = """The system could not produce a verified answer to the user's question.
Write ONE short sentence, in the SAME LANGUAGE as the question, saying that a verified
answer to it cannot be given right now. State no facts, no figures, no reasons, no
apologies. Reply with that sentence only."""


def refuse_text(question):
    """Отказ формулирует МОДЕЛЬ — на языке спрашивающего.

    Пункт 18 `TARGET.md`: при отказе бот обязан СКАЗАТЬ, что не может ответить, а не
    промолчать. Раньше здесь уходила пустая строка, и клиент видел пустоту — замерено
    на вопросах «какие дополнительные условия продажи есть» и «покажи статистические
    показатели» (гейт зарубал формулировку модели, а сказать об этом было некому).

    Своей прозой писать нельзя: она была бы на одном языке независимо от языка вопроса —
    тот же дефект, что и русские умолчания ответа (п. 9). Модель здесь ничего не решает
    и не считает: ей нечего выдумывать, потому что данных ей не дают вовсе (п. 19).

    Цифры из отказа вырезаются КОДОМ, а не просьбой в промте: любая цифра в отказе —
    это уже утверждение о данных, а «правила на промте не работают».
    """
    if not question:
        return ""
    try:
        t = (ds_chat([{"role": "system", "content": REFUSE_SYS},
                      {"role": "user", "content": question}], max_tokens=60) or "").strip()
    except Exception:                          # noqa: BLE001 — сеть/квота поставщика
        return ""                              # модель недоступна — формулирует вызывающий
    return "" if _norm_numbers(t) else t


def rerank(query, docs):
    """Упорядочить названия по близости к вопросу — моделью-реранкером.

    Возвращает порядок индексов. Пусто — значит не получилось, и вызывающий остаётся
    на прежнем порядке: отсутствие сигнала не должно превращаться в отказ (п. 21).
    """
    if not query or not docs or not RERANK_KEY:
        return []
    # 🔴 ФОРМАТ ЗАПРОСА — НАСТРОЙКА, А НЕ КОНСТАНТА. Прежде тут был зашит вид одного
    # облачного поставщика (`input`/`parameters`/`output.results`), и на любом другом
    # реранкере — включая свой, поднятый рядом с эмбеддером, — вызов молча падал бы в
    # «не получилось», а выдача оставалась бы в прежнем порядке. Заметить это по ответу
    # бота нельзя: сигнала просто нет.
    # Умолчание — общий вид `/v1/rerank` (`model`/`query`/`documents`/`top_n`, ответ
    # `results[].index`), его отдают llama.cpp, TEI и совместимые. Прежний вид доступен
    # как `RERANK_API=dashscope`.
    if RERANK_API == "dashscope":
        body = json.dumps({"model": RERANK_MODEL,
                           "input": {"query": query, "documents": docs},
                           "parameters": {"return_documents": False,
                                          "top_n": len(docs)}}).encode()
    elif RERANK_API == "texts":
        # Схема сервиса объявляет ровно query/documents/instruction/top_n — лишних полей
        # не шлём: молча проглоченное поле сегодня завтра станет ошибкой валидации.
        body = json.dumps({"query": query, "documents": docs, "top_n": len(docs)}).encode()
    else:
        body = json.dumps({"model": RERANK_MODEL, "query": query,
                           "documents": docs, "top_n": len(docs)}).encode()
    req = urllib.request.Request(RERANK_URL, data=body, method="POST")
    if RERANK_KEY:
        req.add_header("Authorization", "Bearer " + RERANK_KEY)
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", EMBED_UA)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            out = json.loads(r.read())
        out = out["output"]["results"] if RERANK_API == "dashscope" else out["results"]
        order = [int(x["index"]) for x in out]
        # 🔴 УСПЕХ ТОЖЕ ПИШЕТСЯ В ЖУРНАЛ. Прежде отмечался только сбой, и «реранкер
        # отработал» было неотличимо от «реранкер не звался вовсе»: обе картины дают в
        # журнале пустоту. [замер 02.08] на этом я и ошибся — счёл прогон идущим без
        # реранкера по строкам 401, снятым до смены настроек. Теперь по журналу видно,
        # участвовал ли он в КАЖДОМ ответе и переставил ли он что-нибудь.
        sys.stderr.write("rerank отработал: %d кандидатов, порядок %s\n"
                         % (len(docs),
                            "изменён" if order[:len(docs)] != list(range(len(docs)))
                            else "без изменений"))
        return order
    except Exception as e:                     # noqa: BLE001 — сеть/квота поставщика
        # 🔴 МОЛЧА ТЕРЯТЬ СИГНАЛ НЕЛЬЗЯ (п. 13). Отказ реранкера не роняет ответ — и это
        # верно (п. 21), — но он ухудшает ровно то, что и так главная открытая проблема:
        # выбор сущности. [замер 02.08] поставщик реранкера отвечал `Arrearage` на все
        # запросы, и по журналу это было не видно ничем: выдача просто оставалась в
        # прежнем порядке. Теперь причина видна в журнале службы.
        sys.stderr.write("rerank НЕ ОТРАБОТАЛ (порядок остаётся прежним): %r\n" % (e,))
        return []


def _resolver_psql(sql):
    """Запрос к резолверу — ОТДЕЛЬНОЙ ролью `serene_resolver`. Не через общий `psql`:
    та роль (`serene_ro`) к `resolver_index` доступа не имеет по замыслу. Ошибка (нет
    настроек, роль недоступна) гасится в пустой список — резолв отключается, а не роняет
    ответ (п. 21)."""
    if not RESOLVER_DSN:
        return []
    env = dict(os.environ)
    if RESOLVER_PW:
        env["PGPASSWORD"] = RESOLVER_PW
    try:
        p = subprocess.run(["psql", RESOLVER_DSN, "-tA", "--csv", "-v", "ON_ERROR_STOP=1", "-f", "-"],
                           input=sql, capture_output=True, text=True, env=env)
    except OSError:
        return []
    if p.returncode != 0:
        sys.stderr.write("resolver query failed: %s\n" % (p.stderr or "")[:160])
        return []
    return [r for r in csv.reader(io.StringIO(p.stdout)) if r]


RESOLVE_NEAR = int(os.environ.get("ASK_RESOLVE_NEAR", "12"))
RESOLVE_KEEP = int(os.environ.get("ASK_RESOLVE_KEEP", "3"))


def _resolve_values_literal(term):
    """Подстрока в значениях резолвера — когда вектор недоступен или не нашёл.

    «Казань» → «Г. КАЗАНЬ» в колонке Город: в doc-индексе города нет, а в
    resolver_index значение лежит. Без этого probe объявляет no_data при живых
    данных (B8-03).
    """
    core = re.sub(r"[^0-9a-zа-яё]", "", (term or "").lower())
    if len(core) < 3:
        return []
    try:
        rows = _resolver_psql(
            "SELECT DISTINCT value FROM resolver_index "
            "WHERE lower(value) LIKE '%%' || %s || '%%' "
            "ORDER BY length(value), value LIMIT %d"
            % (lit(core), RESOLVE_KEEP * 4))
        prefixes = {core}
        if len(core) >= 5:
            prefixes.add(core[:5])
        if len(core) >= 4:
            prefixes.add(core[:4])
        out = []
        for r in rows or []:
            if not r or not r[0]:
                continue
            words = re.findall(r"[0-9a-zа-яё]+", str(r[0]).lower())
            hit = False
            for w in words:
                if len(w) < 3:
                    continue
                for pref in prefixes:
                    if len(pref) < 3:
                        continue
                    if w.startswith(pref) or pref.startswith(w[: len(pref)]):
                        hit = True
                        break
                if hit:
                    break
            if hit:
                out.append(r[0])
            if len(out) >= RESOLVE_KEEP:
                break
        return out
    except RuntimeError:
        return []


def _resolve_values_corpus(term):
    """Подстрока в doc-индексе — когда резолвер не знает город (B8-03)."""
    core = re.sub(r"[^0-9a-zа-яё]", "", (term or "").lower())
    if len(core) < 3:
        return []
    prefixes = {core}
    if len(core) >= 5:
        prefixes.add(core[:5])
    if len(core) >= 4:
        prefixes.add(core[:4])
    try:
        for pref in sorted(prefixes, key=len, reverse=True):
            if len(pref) < 3:
                continue
            pat = "%" + pref + "%"
            r = psql("SELECT count(*) FROM %s WHERE doc @@ ts_like(%s)"
                     % (INDEX, lit(pat)))
            if r and int(r[0][0]) > 0:
                return [pat]
    except RuntimeError:
        return []
    return []




def resolve_values(term):
    """Слово человека -> конкретные значения в базе («Питер» -> «Санкт-Петербург»).

    🔴 ЭТО РЕЗОЛВЕР. Он закрывает класс вопросов, где спрошенное слово в данных записано
    ИНАЧЕ и ни точным совпадением, ни опечаткой, ни подстрокой не находится: сокращение,
    разговорное имя, другой падеж основы. [замер 28.07] «Питер» подстрокой даёт 0, а в
    базе 180 записей про Санкт-Петербург.

    Механизм — тот же, что везде в проекте: близость считает БАЗА (вектор значения к
    вектору слова, `emb <=> vec`), а какой из близких верен, решает РЕРАНКЕР. Порога
    близости НЕТ и быть не может: «то же это слово или нет» — вопрос языковой. Реранкер
    уже используется для выбора сущности; здесь та же роль.

    Границы (п. 19): смотрим не больше `RESOLVE_NEAR` ближайших и оставляем не больше
    `RESOLVE_KEEP` — объём во внешнюю модель не растёт с размером базы.
    """
    # Векторы резолвера посчитаны другой моделью — сравнивать с ними нельзя (`emb_ready`).
    if not emb_ready("resolver_index"):
        return []
    try:
        vec = _vec(term)
    except Exception:                          # noqa: BLE001 — эмбеддер недоступен
        return []
    # Ф6.2: при ASK_RESOLVER_IVF=1 и готовом индексе — ANN через IVF (metric=ip → `<#>`),
    # без `WHERE emb IS NOT NULL` (ловушка латентности на IVF, как у корпуса Ф6.1).
    # Флаг выключен или индекса нет — бит-в-бит прежний exact по `resolver_index`.
    if ASK_RESOLVER_IVF and _resolver_ivf_ready():
        near = _resolver_psql(
            "SELECT DISTINCT value FROM %s "
            "ORDER BY emb <#> %s, value LIMIT %d"
            % (RESOLVER_IVF_IDX, vec, RESOLVE_NEAR))
    else:
        near = _resolver_psql(
            # 🔴 ТОЛЬКО СТРОКИ С ВЕКТОРОМ. Без этого условия запрос не отдаёт «ничего», когда
            # векторов нет: `<=>` от NULL даёт NULL, такие строки уходят в конец, и когда
            # вектора нет НИ У КОГО, порядок целиком решает разделитель равенства — то есть
            # возвращается первое по алфавиту под видом «ближайшего по смыслу». Это молчаливо
            # неверный ответ (п. 10), а не пустой. Условие делает случай честным: нет
            # векторов — нет и близких, вызывающий остаётся без подсказки и спрашивает.
            "SELECT DISTINCT value FROM resolver_index WHERE emb IS NOT NULL "
            "ORDER BY emb <=> %s, value LIMIT %d"
            % (vec, RESOLVE_NEAR))
    vals = [r[0] for r in near if r and r[0]]
    if not vals:
        return []
    # 🔴 ГАРДА ОТ РАЗРЕШЕНИЯ В МУСОР. Вектор ВСЕГДА отдаёт ближайшее, а реранкер всегда
    # даёт порядок — поэтому у значения, которого в базе НЕТ, они находят случайное:
    # [замер 28.07] «SanDisk» (нет в данных) разрешался в коды занятий «5920», и ответ
    # уходил про «уличных торговцев». Оценка реранкера не спасает (мусору давал 0.55 при
    # 0.67 у верного). Признак структурный и без порога: слово человека и значение базы
    # обязаны делить кусочек букв — «Питер»/«Петербург» делят «тер», а «SanDisk»/«5920» —
    # ничего. Работает на любом языке: это буквы, а не список синонимов.
    keep = [v for v in vals if _shares_chars(term, v)]
    if not keep:
        return []
    order = rerank(term, keep)
    picked = [keep[i] for i in order[:RESOLVE_KEEP]] if order else keep[:RESOLVE_KEEP]
    return picked


def _ngrams(s, n=3):
    s = re.sub(r"[^0-9a-zа-яё]", "", (s or "").lower())
    if len(s) < n:
        return {s} if s else set()
    return {s[i:i + n] for i in range(len(s) - n + 1)}



register_zone('ask.z07_rrf_vectors', globals())
