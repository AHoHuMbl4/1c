"""Zone 14: Уточнение и память (clarify-memory)."""
from __future__ import annotations

from ask._imports import *
from ask._wire import register_zone, apply_bindings

apply_bindings(globals())

def _alias_parts(raw):
    """Алиасы поля: список или строка через запятую, как кладёт `wiki_alias.sh`."""
    if isinstance(raw, (list, tuple)):
        return [str(a).strip() for a in raw if str(a).strip()]
    return [a.strip() for a in str(raw or "").split(",") if a.strip()]


def _word_hits_text(wl, text):
    t = (text or "").strip().lower()
    if not t or len(wl) < 2 or len(t) < 2:
        return False
    return wl == t or wl in t or t in wl


def split_ident(name):
    """CamelCase и подчёркивания — в слова через пробел. Без знания конкретной базы."""
    s = (name or "").replace("_", " ")
    s = re.sub(r"([a-zа-яё0-9])([A-ZА-ЯЁ])", r"\1 \2", s)
    return " ".join(s.split())


def measure_choice(names, word, alias_by=None):
    """Чистая часть выбора величины: слово человека против имён величин ИЗ ДАННЫХ.

    Вынесена из `pick_measure` отдельной функцией по двум причинам, и обе — не про красоту:
      1. её можно проверять ОФФЛАЙН (`test_gate.py`), без базы, сети и денег;
      2. то же правило нужно ВТОРОМУ месту — гейту величины (задача 16), где величину
         назвала модель. Пока правило жило внутри `pick_measure`, этот путь его не
         проходил вовсе: имя от модели принималось, если оно просто есть у сущности.

    Возвращает `(величина, альтернативы, как)`. `как='ask'` — подходящих несколько, и
    выбирать между ними молча нельзя (п. 12). `как='rerank'` — правилами не решается,
    решает вызывающий.
    """
    wl = (word or "").strip().lower()
    if not names:
        return (None, [], 'none')
    if not wl:
        return (None, [], 'none')
    if len(names) == 1:
        return (names[0], [], 'single')        # выбора нет — и спрашивать не о чем
    # Имя величины ТОЧНО совпало со словом вопроса — брать его, не гадая реранкером.
    # «сумма» → «Сумма», а не «СуммаНУDr»: точное совпадение сильнее близости.
    exact = [n for n in names if n.lower() == wl]
    if exact:
        return (exact[0], [], 'exact')
    if alias_by:
        covered = [n for n in names
                   if any(_word_hits_text(wl, a) for a in _alias_parts(alias_by.get(n)))]
        if len(covered) == 1:
            return (covered[0], [], 'alias')
        if len(covered) > 1:
            base_of = [n for n in covered
                       if sum(1 for m in covered if m != n and m.startswith(n))
                       >= len(covered) - 1]
            if len(base_of) == 1 and base_of[0].lower() != wl:
                return (base_of[0], [], 'base')
            return (None, covered, 'ask')
    same = sorted(n for n in names if wl in n.lower())
    if len(same) > 1:
        # Базовая величина снимает неоднозначность, если её частные виды — её же префиксы
        # (правило ниже): тогда спрашивать не о чем. Иначе — спрашиваем.
        base_of = [n for n in same
                   if sum(1 for m in same if m != n and m.startswith(n)) >= len(same) - 1]
        if len(base_of) == 1 and base_of[0].lower() != wl:
            return (base_of[0], [], 'base')
        # Раз уж спрашиваем человека — показываются ВСЕ величины сущности, совпавшие
        # со словом — первыми. Подстрока слепа к именованию базы: живой диалог okna
        # 14.08 — на «сумму продаж» совпали только СуммаНДС и СуммаОплатыКарточкой,
        # человек выбрал из двух неверных, а общий итог в этой базе зовётся «Всего»
        # и в варианты не попал вовсе. Список короткий и приходит из данных.
        return (None, same + [n for n in names if n not in same], 'ask')
    if len(same) == 1:
        return (same[0], [], 'substring')
    return (None, [], 'rerank')


def measure_captions(measures, alias_by=None):
    """Человеческая подпись величины. Одинаковые имена различаются разбором поля."""
    alias_by = alias_by or {}
    prim = {}
    for m in measures:
        parts = _alias_parts(alias_by.get(m))
        prim[m] = parts[0] if parts else (split_ident(m) or m)
    seen = {}
    for v in prim.values():
        seen[v.lower()] = seen.get(v.lower(), 0) + 1
    out = {}
    for m in measures:
        cap = prim[m]
        if seen.get(cap.lower(), 0) > 1:
            extra = split_ident(m) or m
            if extra.lower() != cap.lower():
                cap = "%s (%s)" % (cap, extra)
        out[m] = cap
    return out


def resolve_measure(text, measures, alias_by=None, diag=None):
    """Свести выбор человека к имени поля. Неоднозначно или не узнали — None (п. 12)."""
    if not text:
        return None
    t = str(text).strip()
    if not t:
        return None
    if t in (measures or []):
        return t
    alias_by = alias_by or {}
    caps = measure_captions(measures, alias_by)
    norm = lambda s: "".join(str(s or "").lower().split())
    nt = norm(t)
    hit = [m for m, c in caps.items() if norm(c) == nt]
    if len(hit) == 1:
        return hit[0]
    if len(hit) > 1:
        if diag is not None:
            diag["measure_ambiguous_pick"] = t
        return None
    hit = []
    for m in measures:
        if any(norm(a) == nt for a in _alias_parts(alias_by.get(m))):
            hit.append(m)
    if len(hit) == 1:
        return hit[0]
    if len(hit) > 1:
        if diag is not None:
            diag["measure_ambiguous_pick"] = t
        return None
    if diag is not None:
        diag["measure_unknown"] = t
    return None


def slot_measure_uncovered(word, selected, names, alias_by=None):
    """Вопрос назвал величину, выбранное поле её не покрывает, другое из names — покрывает."""
    if not word or not selected or not names:
        return False, []
    got, alts, how = measure_choice(names, word, alias_by=alias_by)
    covering = list(alts) if how == "ask" else ([got] if got else [])
    if covering and selected not in covering:
        return True, covering
    return False, []


# 🔴 ОТПЕЧАТОК ТИПИЗИРОВАН (15.08, аудит §5.2). Боевая форма `figures` — это
# `compose_slot_values` ПЛЮС паспорт набора (`from`/`to`/`label`/`measure`,
# `build_answer_passport`). Прежний отпечаток приводил к числу всё, что не `date*`,
# и на строковых `label`/`measure` возвращал `None`; `answers_diverge` читал это как
# расхождение, и ветка A3 (`answers_src_conflict`) на боевой форме была НЕДОСТИЖНА
# (замер аудита на проде: `passport_A3=False`). Поэтому: числовые слоты — числами
# (round 2), квалификаторы паспорта — строками, а `label` исключён вовсе — это метка
# источника, производная `src`, и по ней совпавшие по числам прочтения различались бы
# всегда. Нечисловое значение в непаспортном слоте сравнивается строкой: `None` от
# паспорта больше не возникает, а разное по-прежнему даёт расхождение.
_FP_SKIP = {"in_1c", "in_search", "missing", "_totals", "label"}
_FP_STR = {"from", "to", "measure"}            # квалификаторы паспорта — строки


def _slot_fp(f):
    """Отпечаток плейсхолдеров одного кандидата. Покрытие и метка не входят."""
    if not isinstance(f, dict):
        return None
    fp = []
    for k in sorted(f):
        if k in _FP_SKIP or str(k).startswith("_"):
            continue
        v = f.get(k)
        if v is None or (isinstance(v, str) and not str(v).strip()):
            continue
        if str(k).startswith("date") or k in _FP_STR:
            fp.append((k, str(v)))
            continue
        try:
            fp.append((k, round(float(v), 2)))
        except (TypeError, ValueError):
            fp.append((k, str(v)))
    return tuple(fp)


def answers_diverge(figures):
    """Сошлись ли ПОСЧИТАННЫЕ ответы кандидатов на одном числе (задача 17).

    Сравнивается отпечаток плейсхолдеров compose, не заранее названное поле. Порога нет.
    Совпали — выбирать не из чего. Сравнить нечем — расхождение, не согласие.
    """
    if len(figures) < 2:
        return False

    # Контракт: для суммовых вопросов важна финальная цифра, а не служебные
    # поля (например `count_amount`). Разные src могут по-разному заполнять
    # вспомогательные слоты при совпавшем итоговом числе — тогда арбитраж
    # ошибочно уходил в `clarify`.
    if isinstance(figures[0], dict) and figures[0].get("sum") is not None:
        try:
            sums = []
            for f in figures:
                if not isinstance(f, dict):
                    return True
                v = _intent_number(f.get("sum"))
                if v is None:
                    return True
                sums.append(round(float(v), 2))
            return len(set(sums)) > 1
        except Exception:  # noqa: BLE001
            pass

    fps = []
    for f in figures:
        fp = _slot_fp(f)
        if not fp:
            return True
        fps.append(fp)
    return len(set(fps)) > 1

def answers_src_conflict(cands):
    """Разные src при совпавшем отпечатке — не согласие (A3).

    Список из двух и больше `{src, kind, figures}`. Отпечаток — тот же
    `answers_diverge` по `figures` (слоты compose, не голое count).
    True = спрашивать. Один src, меньше двух `answer`, или отпечатки
    разошлись — False (расхождение чисел — ветка `answers_diverge`).
    Соперника в круг не заводит: смотрит тех, кто уже дал `kind=answer`.
    """
    ans = [c for c in (cands or [])
           if (c.get("kind") == "answer") and c.get("src")]
    if len(ans) < 2:
        return False
    if answers_diverge([c.get("figures") or {} for c in ans]):
        return False
    return len({c["src"] for c in ans}) > 1


# ----------------------------------------------------------------- decision_id
# Одноразовый билет выбора (план §6, аудит §10). Хранение — в процессе сервиса:
# рестарт → старые билеты неизвестны. Сырой focus больше не доказывает выбор.
RAW_FOCUS_TRUST = os.environ.get("ASK_RAW_FOCUS_TRUST", "0") == "1"
DECISION_TTL_SEC = int(os.environ.get("ASK_DECISION_TTL_SEC", "3600"))
_DECISION_LOCK = threading.Lock()
_DECISIONS = {}  # id -> ticket
_CLARIFY_BATCHES = {}  # batch_id -> snapshot options/text for reissue
# Снятые неоднозначности в рамках одного вопроса (план §6, терминальный второй круг).
_RESOLVED_CHOICES = {}  # (question_fp, user) -> {src, measure, axis, expires_at}


def question_fingerprint(question):
    """Отпечаток вопроса для сверки билета с повторным запросом."""
    q = " ".join(str(question or "").strip().lower().split())
    return hashlib.sha256(q.encode("utf-8")).hexdigest()[:32]


def db_fingerprint(dsn=None):
    """Имя базы через current_database(), без парсинга DSN.

    В оффлайн-тестах (где DSN не задан) возвращаем '' и не делаем сравнение
    по db-фингерпринту.
    """
    use_dsn = dsn if dsn is not None else DSN
    if not use_dsn:
        return ''
    try:
        rows = psql("SELECT lower(current_database())")
        return (rows[0][0] if rows and rows[0] and rows[0][0] else '').lower()
    except Exception:
        # Fail-open: без доступа к БД сравнение билетов по базе не делаем.
        return ''


def options_version(opts):
    """Версия набора вариантов: стабильный хеш состава."""
    rows = []
    for o in opts or []:
        if not isinstance(o, dict):
            continue
        rows.append("|".join([
            str(o.get("src") or ""),
            str(o.get("measure") if "measure" in o else ""),
            str(o.get("label") or ""),
            str(o.get("distinct_by") or ""),
        ]))
    rows.sort()
    return hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest()[:16]


def ambiguity_of_options(opts):
    """Предмет clarify: сущность / величина / ось / период."""
    opts = [o for o in (opts or []) if isinstance(o, dict)]
    if not opts:
        return "entity"
    if any(isinstance(o.get("period"), dict) for o in opts):
        return "period"
    if any("measure" in o for o in opts):
        return "measure"
    if all("found" not in o for o in opts) and any(o.get("distinct_by") for o in opts):
        return "axis"
    return "entity"


def _new_decision_id():
    # opaque, короткий: Telegram callback ≤ 64 байт.
    return secrets.token_urlsafe(12)  # ~16 символов


def _purge_decisions(now=None):
    """Срок жизни — единственный вычиститель. used остаётся до TTL, чтобы
    повторный клик видел ошибку used, а не unknown."""
    now = now if now is not None else time.time()
    dead = [k for k, t in _DECISIONS.items()
            if float(t.get("expires_at") or 0) <= now]
    for k in dead:
        _DECISIONS.pop(k, None)
    dead_b = [k for k, b in _CLARIFY_BATCHES.items()
              if float(b.get("expires_at") or 0) <= now]
    for k in dead_b:
        _CLARIFY_BATCHES.pop(k, None)
    dead_r = [k for k, v in _RESOLVED_CHOICES.items()
              if float(v.get("expires_at") or 0) <= now]
    for k in dead_r:
        _RESOLVED_CHOICES.pop(k, None)


def _resolved_key(question, user):
    return (question_fingerprint(question),
            (str(user).strip() if user else None) or None)


def peek_resolved(question, user=None):
    """Накопленные снятые уровни (entity/measure/axis) для этого вопроса."""
    key = _resolved_key(question, user)
    with _DECISION_LOCK:
        _purge_decisions()
        acc = _RESOLVED_CHOICES.get(key)
        return dict(acc) if acc else {}


def accumulate_resolution(question, user, ticket):
    """После успешного consume — запомнить снятый уровень до конца вопроса."""
    if not ticket:
        return
    key = _resolved_key(question, user)
    with _DECISION_LOCK:
        _purge_decisions()
        acc = dict(_RESOLVED_CHOICES.get(key) or {})
        amb = ticket.get("ambiguity") or ""
        if ticket.get("src"):
            acc["src"] = ticket["src"]
        if amb == "measure" and "measure" in ticket:
            acc["measure"] = ticket.get("measure")
        if amb == "axis" and ticket.get("axis"):
            acc["axis"] = ticket.get("axis")
        if amb == "period" and ticket.get("period") is not None:
            acc["period"] = dict(ticket.get("period") or {})
        acc["expires_at"] = float(ticket.get("expires_at") or 0) or (
            time.time() + max(60, DECISION_TTL_SEC))
        _RESOLVED_CHOICES[key] = acc


def issue_decision(question, option, ambiguity, options_ver, user=None, parse=None,
                   class_meta=None, batch_id=None):
    """Выпустить билет на один вариант clarify. Возвращает decision_id."""
    now = time.time()
    tid = _new_decision_id()
    meta = class_meta if isinstance(class_meta, dict) else {}
    ticket = {
        "decision_id": tid,
        "question_fp": question_fingerprint(question),
        "question": str(question or "")[:2000],
        "parse": parse,
        "ambiguity": ambiguity,
        "src": (option or {}).get("src"),
        "measure": (option or {}).get("measure") if option and "measure" in option else None,
        "grain": (option or {}).get("grain"),
        "axis": (option or {}).get("distinct_by") if ambiguity == "axis" else None,
        "day_basis": ((option or {}).get("day_basis")
                      if (option or {}).get("day_basis") in _DAY_BASIS_IDS
                      else None),
        "amount_basis": ((option or {}).get("amount_basis")
                         if (option or {}).get("amount_basis") in _AMOUNT_BASIS_IDS
                         else None),
        "period": ((option or {}).get("period")
                   if ambiguity == "period" else None),
        "label": (option or {}).get("label"),
        "db": db_fingerprint(),
        "user": (str(user).strip() if user else None) or None,
        "options_version": options_ver,
        "class_key": meta.get("class_key"),
        "readings": list(meta.get("readings") or []),
        "window_fp": meta.get("window_fp") or "",
        "measure_ctx": meta.get("measure_ctx") or "",
        "nonce": secrets.token_hex(8),
        "created_at": now,
        "expires_at": now + max(60, DECISION_TTL_SEC),
        "used": False,
        "batch_id": batch_id,
    }
    with _DECISION_LOCK:
        _purge_decisions(now)
        _DECISIONS[tid] = ticket
    return tid


def seal_clarify(out, question, user=None, parse=None):
    """В каждый options[] — decision_id; билеты в процессном хранилище.

    Работает для clarify и для figures с вариантами (исход B: пары + выбор класса).
    """
    if not isinstance(out, dict):
        return out
    if out.get("kind") not in ("clarify", "figures", "answer"):
        return out
    opts = out.get("options") or []
    if not opts:
        return out
    amb = ambiguity_of_options(opts)
    ver = options_version(opts)
    class_meta = ACM.class_meta_of(out)
    batch_id = secrets.token_hex(8)
    now = time.time()
    plain = []
    sealed = []
    for o in opts:
        if not isinstance(o, dict):
            continue
        row = dict(o)
        snap = dict(o)
        snap.pop("decision_id", None)
        plain.append(snap)
        row["decision_id"] = issue_decision(
            question, row, amb, ver, user=user, parse=parse,
            class_meta=class_meta, batch_id=batch_id)
        sealed.append(row)
    with _DECISION_LOCK:
        _CLARIFY_BATCHES[batch_id] = {
            "kind": out.get("kind"),
            "text": out.get("text"),
            "options": plain,
            "atoms": out.get("atoms"),
            "atom": out.get("atom"),
            "figures": out.get("figures"),
            "partial": out.get("partial"),
            "sources": out.get("sources") or [],
            "question": str(question or "")[:2000],
            "question_fp": question_fingerprint(question),
            "user": (str(user).strip() if user else None) or None,
            "parse": parse,
            "expires_at": now + max(60, DECISION_TTL_SEC),
        }
    out = dict(out)
    out["options"] = sealed
    out.setdefault("diag", {})
    if isinstance(out["diag"], dict):
        out["diag"] = dict(out["diag"], decisions_sealed=len(sealed),
                           ambiguity=amb, options_version=ver)
    return out


def consume_decision(decision_id, question, user=None):
    """Проверить и погасить билет. (ticket, None) или (None, error_code)."""
    tid = str(decision_id or "").strip()
    if not tid:
        return None, "unknown"
    now = time.time()
    with _DECISION_LOCK:
        ticket = _DECISIONS.get(tid)
        if not ticket:
            _purge_decisions(now)
            return None, "unknown"
        if ticket.get("used"):
            return None, "used"
        if float(ticket.get("expires_at") or 0) <= now:
            _DECISIONS.pop(tid, None)
            _purge_decisions(now)
            return None, "expired"
        if ticket.get("db") and ticket["db"] != db_fingerprint():
            return None, "mismatch"
        if ticket.get("question_fp") != question_fingerprint(question):
            return None, "mismatch"
        if ticket.get("user"):
            if not user or str(user).strip() != ticket["user"]:
                return None, "user_mismatch"
        ticket = dict(ticket)
        ticket["used"] = True
        _DECISIONS[tid] = ticket
        return ticket, None


def peek_decision(decision_id, user=None):
    """Прочитать билет без погашения. «Запомни» после клика: used до TTL жив."""
    tid = str(decision_id or "").strip()
    if not tid:
        return None, "unknown"
    now = time.time()
    with _DECISION_LOCK:
        ticket = _DECISIONS.get(tid)
        if not ticket:
            _purge_decisions(now)
            return None, "unknown"
        if float(ticket.get("expires_at") or 0) <= now:
            _DECISIONS.pop(tid, None)
            _purge_decisions(now)
            return None, "expired"
        if ticket.get("db") and ticket["db"] != db_fingerprint():
            return None, "mismatch"
        if ticket.get("user"):
            if not user or str(user).strip() != ticket["user"]:
                return None, "user_mismatch"
        return dict(ticket), None


def lookup_clarify_batch(decision_id, question, user=None, err=None):
    """Снимок уточнения, из которого выпущен билет. user_mismatch — None."""
    if err == "user_mismatch":
        return None
    now = time.time()
    tid = str(decision_id or "").strip()
    with _DECISION_LOCK:
        _purge_decisions(now)
        ticket = _DECISIONS.get(tid) if tid else None
        if ticket:
            bid = ticket.get("batch_id")
            batch = _CLARIFY_BATCHES.get(bid) if bid else None
            if batch and float(batch.get("expires_at") or 0) > now:
                return dict(batch)
        qfp = question_fingerprint(question)
        user_n = (str(user).strip() if user else None) or None
        for batch in _CLARIFY_BATCHES.values():
            if batch.get("question_fp") != qfp:
                continue
            if batch.get("user") and batch["user"] != user_n:
                continue
            if float(batch.get("expires_at") or 0) <= now:
                continue
            return dict(batch)
    return None


def reissue_clarify(batch, err=None):
    """Свежие options без билетов: Handler/seal_clarify выпустит новые id."""
    if not isinstance(batch, dict):
        return None
    kind = batch.get("kind") or "clarify"
    if kind not in ("clarify", "figures"):
        kind = "clarify"
    out = {
        "kind": kind,
        "text": batch.get("text") or "",
        "options": [dict(o) for o in (batch.get("options") or []) if isinstance(o, dict)],
        "sources": batch.get("sources") or [],
        "partial": batch.get("partial"),
        "diag": {"ticket_reissued": err or "unknown"},
    }
    for k in ("atoms", "atom", "figures"):
        if batch.get(k) is not None:
            out[k] = batch[k]
    return out


def reset_decisions_for_tests():
    """Только оффлайн-пробы: очистить хранилище билетов."""
    with _DECISION_LOCK:
        _DECISIONS.clear()
        _CLARIFY_BATCHES.clear()
        _RESOLVED_CHOICES.clear()


def attach_memory_shadow(out, user=None, action=None, decision_id=None):
    """Shadow-память: diag.memory, ответ не меняет. Ошибка не роняет ответ."""
    global _MEMORY_LOST
    box = [_MEMORY_LOST]
    out = ACM.attach_choice_memory(
        out, psql=psql, tables=TABLES, peek_decision=peek_decision,
        user=user, action=action, decision_id=decision_id,
        enabled=ASK_CHOICE_MEMORY, lost_box=box)
    if box[0] != _MEMORY_LOST:
        _MEMORY_LOST = box[0]
        sys.stderr.write("ask memory LOST %d\n" % _MEMORY_LOST)
    return out


def choice_proven(trusted, ambiguity=None):
    """Билет доказал выбор человека (и при необходимости — предмет неоднозначности)."""
    if not trusted or not isinstance(trusted, dict):
        return False
    if ambiguity is None:
        return True
    return trusted.get("ambiguity") == ambiguity


def choice_levels_proven(trusted=None, resolved=None):
    """Какие уровни неоднозначности уже сняты билетами в этом вопросе."""
    levels = set()
    if resolved:
        if resolved.get("src"):
            levels.add("entity")
        if "measure" in resolved:
            levels.add("measure")
        if resolved.get("axis"):
            levels.add("axis")
        if resolved.get("period") is not None:
            levels.add("period")
    if isinstance(trusted, dict):
        amb = trusted.get("ambiguity")
        if amb in ("entity", "measure", "axis", "period"):
            levels.add(amb)
    return levels


def measure_already_proven(trusted=None, resolved=None, measure_pick=None):
    """True, если measure уже выбран билетом или measure_pick."""
    if measure_pick:
        return True
    return "measure" in choice_levels_proven(trusted, resolved)


def entity_choice_locked(trusted=None, resolved=None):
    """True, если в resolved/trusted уже есть src сущности."""
    return "entity" in choice_levels_proven(trusted, resolved)


def hold_settled_entity(focus, trusted=None, resolved=None, found_by=None,
                        measure_pick=None, holder_srcs=None):
    """Какой src считать после билета: settled или пришедший focus.

    entity+measure в resolved → settled. Focus из держателей оси settled
    (ПКО при ДокументОснование) → settled. Settled с found>0 и focus с 0
    → settled. Иначе focus. Класс F okna 18.08.
    """
    settled = (resolved or {}).get("src") or None
    if not settled and isinstance(trusted, dict) and trusted.get("src"):
        if entity_choice_locked(trusted, resolved):
            settled = trusted.get("src")
    if not settled:
        return focus
    if measure_already_proven(trusted, resolved, measure_pick):
        return settled
    if not entity_choice_locked(trusted, resolved):
        return focus if focus else settled
    if not focus or focus == settled:
        return settled
    if focus in set(holder_srcs or ()):
        return settled
    if found_by is None:
        return focus
    try:
        settled_n = int(found_by.get(settled, 0) or 0)
    except (TypeError, ValueError):
        settled_n = 0
    try:
        new_n = int(found_by.get(focus, 0) or 0)
    except (TypeError, ValueError):
        new_n = 0
    if settled_n > 0 and new_n == 0:
        return settled
    return focus


def guards_skip_for_choice(focus=None, measure_pick=None, trusted=None):
    """Защиты гасит только доказанный билет или аварийный ASK_RAW_FOCUS_TRUST.

    Сырой focus/measure сами по себе сюда не проходят (аудит §10).
    """
    if isinstance(trusted, dict) and trusted.get("from_memory"):
        return True
    if choice_proven(trusted, "entity") or choice_proven(trusted, "measure") \
            or choice_proven(trusted, "axis"):
        return True
    if RAW_FOCUS_TRUST and (focus or measure_pick):
        return True
    return False



register_zone('ask.z14_clarify_memory', globals())
