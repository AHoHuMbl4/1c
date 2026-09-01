"""Zone 16: Вето и выбор сущности (veto-pick-entity)."""
from __future__ import annotations

from ask._imports import *
from ask._wire import register_zone, apply_bindings

apply_bindings(globals())

def pair_slots_only(n_pairs):
    """При нескольких парах одиночные числовые места закрыты структурно."""
    return int(n_pairs or 0) > 1


def atom_whitelist_labels(atoms):
    """Подписи из данных, разрешённые гейту/verify (как метки вариантов уточнения)."""
    out = []
    for a in atoms or []:
        if not isinstance(a, dict):
            continue
        lab = (a.get("measure_label") or "").strip()
        if lab:
            out.append(lab)
    return out


def atom_whitelist_numbers(atoms):
    """Числа пар для белого списка гейта — только из атомов, не из прозы."""
    out = []
    for a in atoms or []:
        if not isinstance(a, dict):
            continue
        if a.get("exact_value") is not None:
            out.append(a["exact_value"])
        excl = a.get("excluded") or {}
        if isinstance(excl, dict):
            for k in ("folders", "undated", "outside_period"):
                if excl.get(k) is not None:
                    out.append(excl[k])
        comp = a.get("completeness") or {}
        if isinstance(comp, dict) and comp.get("missing") is not None:
            out.append(comp["missing"])
    return out


def arbiter_figures(sub):
    """Отпечаток кандидата = его `figures`, уже собранные как плейсхолдеры compose."""
    f = dict((sub or {}).get("figures") or {})
    for k in ("in_1c", "in_search", "missing"):
        f.pop(k, None)
    f.pop("_totals", None)
    return f


def alias_supported(known, hit, cand_family, leader_family, veto=None,
                    rank_cand=None, rank_leader=None, undisputed=False):
    """Подтверждает ли словарь синонимов выбор сущности. Форма правила — здесь и только здесь.

    Правило одно, а форм у него несколько, и выбирать между ними можно только замером —
    поэтому оно вынуто из `_alias_verdict` отдельной функцией: у неё есть оффлайн-проба
    (`test_step4_guards.py`), и её таблица истинности читается без базы.

      · знания об этой сущности нет (`known = 0`) — проверять нечем, выбор проходит. Так
        выглядит база, где вики не собрана (на первой базе алиасов ноль);
      · жёсткая форма (`ALIAS_VETO`, она же боевая): подтверждает ЛИДЕР ранжирования по
        вопросу — совпала его семья с семьёй выбора, значит прочтение одно;
      · мягкая форма: довольно того, что слово вопроса совпало с СОБСТВЕННЫМ синонимом
        выбранной сущности.

    🔴 ЭТО ПРАВИЛО ДЕРЖИТ СЕМНАДЦАТЬ ОТВЕТОВ (`[замер 05.08]`, 44 вопроса приёмки, боевая
    база; разбор — `work/entity-choice/ANSWER_RATE_P21.md`). В форме «лидер выше выбора по
    общему порядку кандидатов» числа такие: неверных 0 → 8, верных 6 → 15. То есть девять
    верных ответов и восемь неверных держатся одной и той же проверкой. Мягкая форма
    («довольно своего совпадения») отвергнута отдельно: 7 вернувшихся ответов, из них 6
    неверных. Прежний замер 30.07 («1 улучшение против 3 ухудшений») этому не противоречит:
    он снят на ПЕРВОЙ базе и на прежнем словаре синонимов.

    🔴 И различает правило эти две группы НЕ ПО ДЕЛУ: у верно отвергнутых лидер словаря стоит
    в общем порядке кандидатов на 68-69 месте, у неверно отвергнутых — на 13-545. Значит
    «ноль ошибок» держится не точностью проверки, а её слепотой; пять ошибок из восьми — один
    и тот же промах ВЫБОРА («Отчёт о розничных продажах» вместо «Реализации товаров и
    услуг»), и лечится он не здесь.
    """
    if not known:
        return True
    if veto is None:
        veto = ALIAS_VETO
    if not veto:
        return bool(hit)
    if not leader_family:
        return bool(hit)
    if VETO_HEAD_WINS and undisputed and rank_cand == 0:
        # 🔴 ВТОРАЯ ПОПЫТКА, ПРЕДПИСАННАЯ КОНТРАКТОМ (п. 21): «если проверка не пропустила
        # ответ — система обязана попробовать сформулировать его заново и проверить снова,
        # а не сдаться с первой попытки». Первая попытка спрашивает ОДНУ поверхность —
        # словарь синонимов. Вторая спрашивает итог ВСЕХ: голову общего порядка кандидатов,
        # который шаг 3 сложил из буквального отбора, смысла, карточки и словаря и уточнил
        # реранкером. Совпал выбор с этой головой — подтверждение есть, и оно независимо от
        # словаря. Порога тут нет: «первый» — это место в порядке, а не подобранное число.
        #
        # 🔴 И ТОЛЬКО ТАМ, ГДЕ СОМНЕНИЯ НЕ БЫЛО ВОВСЕ (`undisputed`). Это не осторожность,
        # а замер: `[замер 06.08]` вторая попытка без этой оговорки вернула 6 ответов, из
        # них 5 верных и 1 неверный — «Сколько мы продали в декабре 2017 года?» ушло по
        # «Отчёту о розничных продажах» вместо «Реализации». Оба спорных случая (и ошибка,
        # и один верный) отличались от прочих одним: там ПОДНИМАЛОСЬ сомнение и работал
        # арбитр. Где спор есть, решает п. 12 — спрашиваем человека; вторая попытка нужна
        # там, где проверка отвергла ответ, которого никто не оспаривал.
        return True
    if VETO_NEEDS_RANK and rank_leader is not None:
        rank_cand = -1 if rank_cand is None else rank_cand
        # 🔴 СЛОВАРЬ ОДИН ПРОТИВ ВСЕХ ОСТАЛЬНЫХ СИГНАЛОВ — ЭТО НЕ ПОВОД ОТМЕНИТЬ ВЫБОР.
        # Лидер словаря отменяет выбор, только если общий порядок кандидатов (буквальный
        # отбор, смысл, карточка, реранкер — всё, что сложено шагом 3) ставит его ВЫШЕ
        # выбранной сущности. Ниже или вовсе вне круга — значит за него говорит одна
        # поверхность из четырёх, и она же `[замер 05.08]` ошибается системно: фраза
        # «сколько тары у нас» в словаре делает регистр тары лидером ЛЮБОГО вопроса,
        # начинающегося со «сколько у нас». Порога тут нет: сравниваются два места в одном
        # и том же порядке, а не оценка с константой.
        if rank_leader < 0:
            return True
        if 0 <= rank_cand < rank_leader:
            return True
    return cand_family == leader_family


def not_for_excludes(kind_stems, items):
    """Отсекает ли кандидата собственное «на что НЕ отвечает» из словаря установки.

    Форма правила — здесь и только здесь, чтобы её таблица истинности читалась без базы
    (`test_step4_guards.py`), а входы от базы собирал один заход в `answer`.

    Входы: `kind_stems` — основы РОДА записей из шага 1 (модель описывает вопрос — это
    её единственная роль; решает код), `items` — записи `not_enough_for` кандидата в
    виде `(основы левой части, есть_указатель)`. Всё по основам словаря движка:
    подстрока тут лжёт в обе стороны — `contains('склады','складов')` ложна.

    Отсев — ровно один случай из двух условий сразу:
      · весь предмет вопроса накрыт ОДНОЙ записью (`kind_stems <= основы записи`).
        Вопрос «продажа» целиком входит в «оптовые продажи — не в этом списке», а
        многословный род («документы реализации товаров и услуг») случайным словом
        вроде «услуг» не накрывается — требование ВСЕГО подмножества и есть защита
        от случайных совпадений;
      · запись НЕ отсылает к соседней сущности (`не есть_указатель`). У записи две
        формы: «аспект — Другая Сущность» (узкое: аспект живёт по соседству, а
        родовой вопрос сущность отвечает) и «тема — не в этом списке» (широкое:
        темы в записях нет вовсе). Отсекает только вторая.

    Почему отсев, а не подсказка модели: в перечень знание не вставляется (проверено
    и отвергнуто замером 30.07 — стало хуже), а решает код по данным — объём в модель
    не растёт (п. 19). Ошибка в данных стоит лишнего уточнения, а не неверного
    ответа: отсеянного кандидата модель просто не видит, все проверки выбора ниже
    работают как прежде.

    Форма выбрана замером среди восьми (`work/entity-choice/not_for_probe.py`, 44
    вопроса приёмки, боевая база): пересечение с сырым текстом вопроса отсекает 15-26
    эталонов из 44 (служебные слова и случайные совпадения), пересечение с родом без
    требования всего подмножества — 12, подмножество без учёта указателя — 7, среди
    них ВЕРНЫЙ ответ про новости. Эта форма — 0 эталонов при 6 из 9 целевых подмен.
    """
    return bool(kind_stems) and any(
        kind_stems <= st and not ptr for st, ptr in items if st)


def pair_unanswered(writer, answered):
    """Соперник из связи «кто пишет этот источник» НЕ дал ответа в круге арбитра.

    `answered` — фокусы кандидатов, чьи ответы собрались. Соперника там может не быть
    по двум причинам: его ответ завернулся в его собственное уточнение (`mute`) или
    под-вызов упал (исключение — он тогда не попадает ни в ответы, ни в `mute`).
    Обе причины означают одно: его число с нашим НЕ сравнивалось, и молчание — это
    не согласие. Форма вынесена отдельной функцией, чтобы её таблица истинности
    читалась без базы (`test_step4_guards.py`).
    """
    return bool(writer) and writer not in answered


def single_is_rival(picked_first, sole):
    """Собравшийся одиночный ответ круга — от соперника, а не от выбора модели.

    Круг собирается ради сомнения; если выбор модели молчит (уточнение о величине,
    пусто, падение), а отвечает соперник, то отдать его число как ответ — скрытый
    выбор наугад между двумя прочтениями (п. 12). Живой случай — приёмка №42
    `[замер 06.08]`: выбран верный документ, он молчит, ответил регистр с чужим числом.
    """
    return bool(picked_first) and bool(sole) and sole != picked_first


def veto_top_without(top, excluded):
    """Лидер словаря синонимов ищется среди НЕ отсеянных «не отвечает».

    Сущность, отсеянная как непригодная отвечать на этот род вопроса, непригодна и
    эталоном сравнения для вето: `[замер 06.08]` лидер «Заказы Поставщикам» был отсеян
    по делу, а его место в круге стало -1 — и правило «лидер вне круга → выбор
    проходит» молча пропустило неверный ответ.
    """
    return [(t, s) for t, s in top if t not in excluded]


def figures_numbers(out):
    """ВСЕ числа, которые кандидат ПОСЧИТАЛ, — даже если ответом они не стали.

    Кандидат круга арбитра возвращается не только ответом: он может завернуть посчитанное
    в уточнение о собственной величине (`measure_totals` — итог по каждой подходящей) или
    во встречный вопрос (`asked_back` — числа при этом в `figures`). Числа от этого не
    перестают быть посчитанными базой, и сравнивать их можно так же, как обычный ответ.
    """
    out = out or {}
    f = out.get("figures") or {}
    nums = []
    if f.get("sum") is not None:
        nums.append(f["sum"])
    elif f.get("count") is not None:
        nums.append(f["count"])
    nums += [v for v in ((out.get("diag") or {}).get("measure_totals") or {}).values()
             if v is not None]
    return nums


def same_number(ours, theirs):
    """Сошлись ли прочтения на ОДНОМ числе. Равенство или ничего — ни порога, ни допуска.

    Правило зеркально `answers_diverge`: там расхождение доказывают разные числа, здесь
    совпадение доказывает равное. Сравнить нечем (у нас числа нет, у соперника ни одного) —
    доказательства НЕТ, и вызывающая сторона спрашивает человека, как и прежде.
    """
    if ours is None:
        return False
    try:
        ours_f = _intent_number(ours)
        if ours_f is None:
            return False
        ours_f = round(float(ours_f), 2)
        for x in (theirs or []):
            if x is None:
                continue
            x_f = _intent_number(x)
            if x_f is None:
                continue
            if round(float(x_f), 2) == ours_f:
                return True
        return False
    except (TypeError, ValueError):
        return False



def src_supports_question(src, intent, diag, by=None, question="", match=None):
    """Есть ли у выбранного src поддержка предмета вопроса (K4-2 страж B).

    Без поддержки measure-clarify по чужому live-src (валюта/НДС) режется в no_data.
    """
    diag = diag or {}
    intent = intent or {}
    by = by or {}
    if not src:
        return False
    terms = intent.get("terms") or []
    kind = (intent.get("kind") or "").strip()
    if terms:
        # Сюда доходим только если все группы matched (место A уже отказал иначе);
        # обрезанных резолвов («ПАНГЕЯ»→«П») не даёт сама гарда резолвера
        # (_shares_chars, подстроке нужен ≥3 знака) — отдельного порога не нужно.
        if diag.get("sales_canon_locked") or diag.get("catalog_count_locked") or diag.get("stock_canon_locked"):
            return True
        if diag.get("sales_measure_canon"):
            return True
        meaning = diag.get("by_meaning") or []
        if src in meaning:
            return True
        alias_hit = diag.get("by_alias") or []
        if src in alias_hit:
            return True
        if kind:
            return False
        if (src in by and not diag.get("by_period_fill")
                and not diag.get("by_vector")):
            return True
        return False
    if diag.get("sales_canon_locked") or diag.get("catalog_count_locked") or diag.get("stock_canon_locked"):
        return True
    if diag.get("sales_measure_canon"):
        return True
    if stock_question_engaged(question, intent):
        return True
    meaning = diag.get("by_meaning") or []
    if src in meaning:
        return True
    alias_hit = diag.get("by_alias") or []
    if src in alias_hit:
        return True
    # Буквальный сигнал — непустой match ИЛИ сам src в живом буквальном отборе by
    # (K4-2: живой by без fill — поддержка; контроль B5/B-ctrl замка).
    literal_signal = bool(match and str(match).strip()) or bool(by.get(src))
    pool_weak = bool(diag.get("by_period_fill") or diag.get("by_vector")
                     or (not literal_signal and not meaning and not alias_hit))
    if pool_weak:
        kind = (intent.get("kind") or "").strip()
        if kind and not kind_has_corpus_support(kind):
            return False
        if not question_expects_accounting_data(intent, question, diag):
            return False
        return False
    # Буквальный by при непустом match — поддержка; period-fill / vector — нет.
    if (src in by and not diag.get("by_period_fill")
            and not diag.get("by_vector")):
        return True
    return False


def any_live_src_supports_question(intent, diag, by, question, match, src,
                                   live_srcs=None):
    """Поддерживает ли предмет вопроса хотя бы один live-src кандидата (K4-2 B)."""
    pool = list(live_srcs or [])
    if src and src not in pool:
        pool.insert(0, src)
    if not pool:
        return src_supports_question(src, intent, diag, by=by,
                                   question=question, match=match)
    return any(src_supports_question(s, intent, diag, by=by,
                                       question=question, match=match)
                for s in pool)


_NON_DATA_MARKERS = (
    "напиши", "расскаж", "стих", "poem", "шутк", "анекдот", "придумай",
    "сочини", "опиши красив", "рифм",
)


def question_expects_accounting_data(intent, question, diag=None):
    """Вопрос про учётные данные, а не off-topic / творческий запрос (K4-2)."""
    diag = diag or {}
    intent = intent or {}
    q = " ".join(str(question or "").lower().split())
    if not q:
        return False
    if any(m in q for m in _NON_DATA_MARKERS):
        return False
    want = (intent.get("want") or "").strip().lower()
    if want in ("count", "sum", "max", "min", "avg"):
        return True
    if want == "list":
        if (intent.get("kind") or "").strip() or intent.get("terms"):
            return True
    elif want:
        return True
    if intent.get("terms"):
        return True
    if diag.get("sales_canon_locked") or diag.get("sales_measure_canon"):
        return True
    if sales_sum_intent(intent, question) or rank_question_text(question):
        return True
    if stock_question_engaged(question, intent):
        return True
    if re.search(r"\b(сколько|покажи|дай|топ|сумм|выруч|продаж|остат|заказ)\b", q):
        return True
    return False


def canon_claims_question(intent, question=""):
    """Канон, забравший вопрос, — поддержка (К4-2 §4.3), страж kind уступает.

    «наторговали» разбирается в kind «торги», которого в корпусе нет, но
    канон продаж сам ведёт вопрос в регистр реализации: отказ «kind без
    опоры» раньше канона — дефект п. 21 (отказ при наличии данных).
    Замер: проба okna 27.08, «сколько наторговали в прошедшее воскресенье»
    падала в no_data (kind_unsupported_in_corpus) при живом каноне.
    """
    if sales_sum_intent(intent, question):
        return True
    _sci = globals().get("sales_canon_intent")
    if callable(_sci) and _sci(intent, question):
        return True
    if catalog_count_question(intent, question):
        return True
    return False


def kind_has_corpus_support(kind):
    """Есть ли kind в корпусе (alias @@ или stem пересечение с catalog).

    База недоступна (офлайн-замки, DSN не задан) — поддержан: отказ «kind
    неподдержан» требует ДОКАЗАННОГО отсутствия в корпусе, иначе офлайн-среда
    превращает каждый вопрос с kind в no_data (п. 21: отказ при наличии
    данных — дефект).
    """
    kind = (kind or "").strip().lower()
    if not kind:
        return True
    try:
        if psql("SELECT 1 FROM alias_idx WHERE aliases @@ %s LIMIT 1" % lit(kind)):
            return True
        if K6R:
            return bool(K6R.stem_overlap_srcs(
                psql, lit, kind, "catalog_%", stem_dict=STEM_DICT))
    except RuntimeError:
        return True
    return False


def measure_class_alts(names, alias_by=None):
    """Два класса меры money|qty вместо полного списка nums (K4-3 №7).

    Возвращает (поле_или_None, alts_классов). alts — имена полей-представителей
    классов, если оба живы и мера не названа; иначе (None, []).
    """
    names = list(names or [])
    alias_by = alias_by or {}
    money = sales_money_measure(names, alias_by)
    qty = sales_qty_measure(names, alias_by)
    if money and qty and money != qty:
        return None, [money, qty]
    return None, []


def unresolved_quantity(measure, alts, want, compute, names, totals_by=None):
    """Свести поле, когда вопрос про итог/max/min/avg, а величина ещё не выбрана.

    `want=count|list` сюда не входит: там в compose нет денег, уточнение полей
    было бы «НДС или карта» на «сколько продаж». Одна величина — брать её;
    несколько с разными итогами — спрашивать тем же перечнем, что уже есть;
    итоги совпали — брать первую, вопрос был бы шумом.
    """
    if measure or alts:
        return measure, list(alts or [])
    need = (want or "") == "sum" or (compute or "") in ("sum", "max", "min", "avg")
    if not need:
        return None, []
    names = list(names or [])
    if not names:
        return None, []
    if len(names) == 1:
        return names[0], []
    if measure_ambiguous(names, totals_by or {}):
        return None, names
    return names[0], []


def mute_measure_blocks(sole, mute, cand_src):
    """Одиночный ответ круга не отпускать, если соперник ушёл в уточнение полей
    с другими итогами. Иначе A2 делает документ немым, а книгу с одним полем —
    ответом. Совпадение чисел — как у writer_pair: вопрос был бы шумом.
    """
    свой = next((s for s in (cand_src or [])
                 if (s.get("diag") or {}).get("focus") == sole), None)
    наше = (figures_numbers(свой) or [None])[0]
    for src, sub in (mute or {}).items():
        if src == sole:
            continue
        if not (sub.get("diag") or {}).get("measure_ambiguous"):
            continue
        if not same_number(наше, figures_numbers(sub)):
            return src
    return None


def measure_row_all_zero(row):
    """Итог totals_of (имя, sum, max, min) тождественно нулевой. Нет строки — тоже пусто."""
    if not row or len(row) < 4:
        return True
    try:
        return float(row[1]) == 0 and float(row[2]) == 0 and float(row[3]) == 0
    except (TypeError, ValueError, IndexError):
        return True


def alive_measure_names(totals):
    """Имена величин с хотя бы одним ненулевым значением. Один список из totals_of."""
    return [r[0] for r in (totals or []) if r and r[0] and not measure_row_all_zero(r)]


def filter_dead_measure_alts(alts, totals):
    """Опции меры: не предлагать величину, у которой по сущности ноль ненулевых.

    Пустой totals — база не ответила, резать нечем: оставляем как было.
    """
    if not totals:
        return list(alts or [])
    alive = set(alive_measure_names(totals))
    return [m for m in (alts or []) if m in alive]


def measure_asked_explicitly(word, measure, how, measure_pick=None):
    """Человек назвал эту величину словами или старым билетом — не молчаливый выбор."""
    if measure_pick and measure:
        return True
    if not measure:
        return False
    if (how or "") not in ("exact", "substring", "alias", "base", "single"):
        return False
    return bool((word or "").strip())


def format_measure_empty_pivot(dead, dead_label, alive_totals, captions=None,
                               question=""):
    """Пивот: спрошенная величина пуста, живые — цифрами из базы (гейт их видит)."""
    captions = captions or {}
    dlab = dead_label or dead or ""
    bits = []
    for m, v, _mx, _mn in (alive_totals or []):
        lab = captions.get(m) or m
        bits.append("«%s» — %s" % (lab, _fmt_human(v)))
    cyr = any('\u0400' <= c <= '\u04ff' for c in (question or "") + dlab)
    if cyr:
        text = "По «%s» нет значений ни в одной записи" % dlab
        if bits:
            text += "; есть " + ", ".join(bits)
        return text + "."
    text = "No values in any record for «%s»" % dlab
    if bits:
        text += "; available: " + ", ".join(bits)
    return text + "."


def build_measure_empty_pivot(question, dead, src, alive_totals, cut, diag, t0,
                              intent, how="", measure_pick=None):
    """kind=answer: спрошенная величина пуста, живые цифрами из базы."""
    names = [dead] + [r[0] for r in (alive_totals or []) if r and r[0]]
    try:
        caps = measure_captions(names, measure_aliases_of(src) if src else {})
    except RuntimeError:
        caps = {n: n for n in names if n}
    dead_label = (caps.get(dead) if caps else None) or dead
    text = format_measure_empty_pivot(dead, dead_label, alive_totals, caps, question)
    _pass_frag, pass_fields = build_answer_passport(
        period=(intent or {}).get("period"),
        period_dropped=False,
        origin=_passport_origin(intent, diag),
        src_label=_table_label(src) if src else "",
        src_kind=kind_word(src) if src else "",
        measure=dead_label or dead or "",
        grain="row",
        axis_label="",
        form="number",
        text=text)
    text = ensure_answer_passport(text, _pass_frag)
    figs = {}
    if alive_totals:
        figs["sum"] = alive_totals[0][1]
        for m, v, _mx, _mn in alive_totals:
            if m:
                figs["total:%s" % m] = v
    figs.update(pass_fields or {})
    first = alive_totals[0] if alive_totals else None
    fake_agg = {
        "count": 0, "sum": (first[1] if first else 0.0),
        "min": None, "max": None, "avg": None,
        "measure": (first[0] if first else dead), "src": src,
        "grain": "row", "form": "number",
    }
    _atom = atom_from_agg(
        fake_agg, operation="sum",
        measure_id=(first[0] if first else dead),
        measure_label=(caps.get(first[0]) if first and caps else None) or (first[0] if first else dead),
        money=True,
        period=(intent or {}).get("period"),
        period_origin=_passport_origin(intent, diag),
        grain="row", form="number",
        axis=None, completeness=None, folders=0, src=src)
    tag = src.split("_", 1)[1] if src and "_" in src else (src or "")
    diag = dict(diag or {})
    diag["measure_empty_pivot"] = dead
    return {"partial": cut or None, "kind": "answer", "text": text,
            "sources": [tag] if tag else [],
            "measure": dead_label or dead,
            "figures": figs, "atom": _atom, "atoms": [_atom],
            "diag": _diag_pack(diag, rows=0,
                               sec=round(time.time() - t0, 2), gate_ok=True)}


def measure_ambiguous(fits, totals):
    """Меняет ли выбор величины ОТВЕТ. Иначе неоднозначности нет, а вопрос был бы шумом.

    Подходящих больше одной — само по себе ещё не сомнение: у документа `СуммаДокумента` и
    `СуммаСНДС` его табличной части дают одно и то же число, и спрашивать «какую из них»
    значит требовать от человека выбора, который ни на что не влияет. Сомнение есть, когда
    итоги РАЗНЫЕ. Ни порога, ни допуска: сравниваются сами числа, посчитанные базой.
    """
    if len(fits) < 2:
        return False
    seen = set()
    for m in fits:
        try:
            seen.add(float(totals.get(m, 0.0)))
        except (TypeError, ValueError):
            seen.add(0.0)
    return len(seen) > 1


def pick_measure(src_table, question, word):
    """Какую величину считать — решается ПО ВОПРОСУ.

    🔴 Здесь больше нет понятия «деньги». Прежде сборщик выбирал одну колонку на
    сущность и объявлял её суммой; из-за этого на «сколько ШТУК продано» отвечать было
    нечем — количества в корпусе не существовало (работа 3 в PRODUCTION_PLAN). Замечание
    владельца 28.07: «это не универсально, базы разные бывают».
    Теперь строка несёт все свои величины, а сопоставить слово человека с именем
    величины — языковая задача, и её делает модель (п. 19). Список имён короткий и
    приходит из данных.
    """
    # Правило целиком живёт в `measure_choice` — ЧИСТОЙ функции, которую проверяет
    # оффлайн-проба. Здесь остаётся только то, чего в ней быть не может: обращение к
    # данным за именами величин и запасной путь через реранкер (сеть).
    # Что делает правило и почему именно так:
    #   * вопрос не называет величину — НЕ выбираем за него, иначе «что покупало Ромашка»
    #     превращается в `НомерЧекаККМ`; итоги по всем величинам уйдут модели (`totals_of`);
    #   * 🔴 несколько величин одинаково подходят — это ВОПРОС ЧЕЛОВЕКУ, а не задача
    #     реранкеру. Указание владельца 30.07: «давать юзеру неверный ответ — самое страшное,
    #     что мы можем сделать. лучше 1, 2, 3 раза уточнить, если непонятно, чем дать не то».
    #     [замер 30.07] у `document_приобретениетоваровуслуг` слово «сумма» несут ЧЕТЫРЕ
    #     величины: СуммаДокумента, СуммаВзаиморасчетов, СуммаВзаиморасчетовПоЗаказу,
    #     СуммаВзаиморасчетовПоТаре. Реранкер выбирал молча и ошибался: на верно выбранной
    #     сущности ответ дал 71 045 277,59 вместо 73 181 157,68 — сущность та, величина нет.
    names = measures_of(src_table)
    wl = (word or "").strip().lower()
    got, alts, how = measure_choice(names, word,
                                    alias_by=measure_aliases_of(src_table))
    if how != 'rerank':
        return (got, alts, how)
    idx = rerank(word, names)
    ranked = [names[i] for i in idx] if idx else names
    # БАЗОВАЯ ВЕЛИЧИНА ПРЕДПОЧТИТЕЛЬНЕЕ УТОЧНЁННОЙ, когда слово общее. У регистра бухучёта
    # величины вложены: «Сумма» — база, «СуммаВРDr»/«СуммаНУCr» — её частные виды (разницы,
    # налоговый учёт, дебет/кредит). Имя базы — ПРЕФИКС имён частных, это структурный факт,
    # а не список. На «обороты»/«сумма» реранкер путался и брал частный вид — [замер 28.07]
    # «обороты» → «СуммаВРDr». Если верхний по рангу — частный вид, а его база тоже в
    # списке и в вопросе нет её уточнителя, берём базу.
    top = ranked[0]
    base = next((n for n in names if n != top and top.startswith(n)
                 and sum(1 for m in names if m != n and m.startswith(n)) >= 2), None)
    if base and base.lower() not in wl:
        qualifier = top[len(base):].lower()
        if qualifier and qualifier not in wl:
            return (base, [], 'base')
    return (top, [], 'rerank')


register_zone('ask.z16_veto_pick_entity', globals())
