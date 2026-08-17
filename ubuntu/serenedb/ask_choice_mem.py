"""Память явного выбора человека (план §8 шаг 6, аудит §13).

Обычный клик (decision_id) сюда не пишет. Пишет только action=remember,
снимает action=forget. Первый режим — SHADOW: строка и коллизии видны в
diag, ответ (kind/text/figures) не меняется.
"""
import hashlib


def split_memory_action(question, explicit=None):
    """Вернуть (action, data_question). action: remember|forget|None.

    Смысл только из поля memory (remember|forget). Текст вопроса не разбирается.
    """
    exp = str(explicit or "").strip().lower()
    action = exp if exp in ("remember", "forget") else None
    return action, str(question or "").strip()


def user_hash_of(user):
    if not user:
        return ""
    return hashlib.sha256(str(user).encode("utf-8")).hexdigest()


def choice_class_key(readings, measure_ctx, window_fp):
    """Отпечаток неоднозначности СО ВХОДА: набор прочтений + величина + окно.

    Выбранный src в ключ не входит (аудит §13).
    """
    srcs = sorted({s for s in (readings or []) if s})
    payload = "\n".join((
        "|".join(srcs),
        str(measure_ctx or ""),
        str(window_fp or ""),
    ))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def choice_readings_of(out):
    srcs = []
    if not isinstance(out, dict):
        return []
    fork = (out.get("diag") or {}).get("fork") or {}
    for a in fork.get("atoms") or []:
        if isinstance(a, dict):
            srcs.extend(a.get("srcs") or [])
    if not srcs:
        for o in out.get("options") or []:
            if isinstance(o, dict) and o.get("src"):
                srcs.append(o["src"])
    return sorted({str(s) for s in srcs if s})


def choice_window_fp(out):
    """Окно периода со входа: from|to|origin|kept/dropped. Без окна — none."""
    if not isinstance(out, dict):
        return "none"
    d = out.get("diag") or {}
    period = None
    atom = out.get("atom")
    if isinstance(atom, dict):
        period = atom.get("period")
    if not isinstance(period, dict):
        for a in out.get("atoms") or []:
            if isinstance(a, dict) and isinstance(a.get("period"), dict):
                period = a["period"]
                break
    dropped = "dropped" if d.get("period_assumed_dropped") else "kept"
    if isinstance(period, dict):
        origin = period.get("origin") or "none"
        return "%s|%s|%s|%s" % (
            period.get("from") or "", period.get("to") or "", origin, dropped)
    if d.get("period_from_prior"):
        return "||prior|%s" % dropped
    assumed = str(d.get("intent_assumed") or "")
    if "period." in assumed:
        return "||assumed|%s" % dropped
    return "none"


def choice_measure_ctx(out):
    if not isinstance(out, dict):
        return ""
    d = out.get("diag") or {}
    return str(d.get("measure") or d.get("want") or "")


def class_meta_of(out):
    readings = choice_readings_of(out)
    measure = choice_measure_ctx(out)
    window = choice_window_fp(out)
    return {
        "class_key": choice_class_key(readings, measure, window),
        "readings": readings,
        "measure_ctx": measure,
        "window_fp": window,
    }


def would_apply_text(branch):
    """Формулировка для diag (и для будущего видимого применения)."""
    if not branch:
        return ""
    lab = (branch.get("label") or branch.get("src") or "").strip()
    bits = [lab] if lab else []
    if branch.get("measure"):
        bits.append(str(branch["measure"]))
    if branch.get("axis"):
        bits.append(str(branch["axis"]))
    return "память применилась бы: " + " / ".join(bits) if bits else ""


def _lit(s):
    return "'" + str(s).replace("'", "''") + "'"


def _sql_bool(v):
    return "TRUE" if v else "FALSE"


def choice_entity_ver(psql, tables, srcs):
    """Версии участвующих сущностей и набора величин. Нет таблицы — пусто."""
    srcs = sorted({s for s in (srcs or []) if s})
    if not srcs:
        return ""
    in_list = ", ".join(_lit(s) for s in srcs)
    parts = []
    try:
        rows = psql(
            "SELECT src_table, coalesce(label,''), coalesce(parent,''), "
            "coalesce(cast(last_built_at AS VARCHAR),'') "
            "FROM %s WHERE src_table IN (%s) ORDER BY 1" % (tables, in_list))
        for r in rows or []:
            parts.append("\t".join(str(x or "") for x in r))
    except (RuntimeError, TypeError, IndexError):
        try:
            rows = psql(
                "SELECT src_table, coalesce(label,'') FROM %s "
                "WHERE src_table IN (%s) ORDER BY 1" % (tables, in_list))
            for r in rows or []:
                parts.append("\t".join(str(x or "") for x in r))
        except (RuntimeError, TypeError, IndexError):
            return ""
    try:
        ms = psql(
            "SELECT src_table, measure FROM search_measure_alias "
            "WHERE src_table IN (%s) ORDER BY 1, 2" % in_list)
        for r in ms or []:
            parts.append("m\t" + "\t".join(str(x or "") for x in r))
    except (RuntimeError, TypeError, IndexError):
        pass
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()[:24]


def _memory_upsert(psql, row):
    """INSERT … ON CONFLICT DO UPDATE (доки: Sql › Statements › INSERT)."""
    nid = int(psql("SELECT nextval('ask_choice_memory_id_seq')")[0][0])
    sql = (
        "INSERT INTO ask_choice_memory ("
        "id, db_name, user_hash, class_key, readings_fp, measure_ctx, window_fp, "
        "chosen_src, chosen_measure, chosen_axis, chosen_label, entity_ver, "
        "ticket_id, active, cancelled, cancelled_at"
        ") VALUES ("
        "%d, current_database(), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
        "TRUE, FALSE, NULL) "
        "ON CONFLICT (user_hash, db_name, class_key) DO UPDATE SET "
        "ts = now(), readings_fp = EXCLUDED.readings_fp, "
        "measure_ctx = EXCLUDED.measure_ctx, window_fp = EXCLUDED.window_fp, "
        "chosen_src = EXCLUDED.chosen_src, chosen_measure = EXCLUDED.chosen_measure, "
        "chosen_axis = EXCLUDED.chosen_axis, chosen_label = EXCLUDED.chosen_label, "
        "entity_ver = EXCLUDED.entity_ver, ticket_id = EXCLUDED.ticket_id, "
        "active = TRUE, cancelled = FALSE, cancelled_at = NULL"
        % (nid,
           _lit(row["user_hash"]),
           _lit(row["class_key"]),
           _lit(row.get("readings_fp") or ""),
           _lit(row.get("measure_ctx") or ""),
           _lit(row.get("window_fp") or ""),
           _lit(row.get("chosen_src") or ""),
           _lit(row.get("chosen_measure") or ""),
           _lit(row.get("chosen_axis") or ""),
           _lit(row.get("chosen_label") or ""),
           _lit(row.get("entity_ver") or ""),
           _lit(row.get("ticket_id") or "")))
    try:
        psql(sql)
    except RuntimeError as e:
        if "Duplicate key" not in str(e):
            raise
        mx = psql("SELECT coalesce(max(id),0) FROM ask_choice_memory")
        top = int((mx[0][0] if mx and mx[0] else 0) or 0)
        psql("SELECT setval('ask_choice_memory_id_seq', %d)" % top)
        nid = int(psql("SELECT nextval('ask_choice_memory_id_seq')")[0][0])
        head, rest = sql.split("VALUES (", 1)
        rest = rest.split(",", 1)[1]
        psql("%sVALUES (%s,%s" % (head, nid, rest))
    return nid


def _memory_cancel(psql, user_hash, class_key):
    psql(
        "UPDATE ask_choice_memory SET active = FALSE, cancelled = TRUE, "
        "cancelled_at = now() WHERE user_hash = %s AND class_key = %s "
        "AND db_name = current_database() AND active AND NOT cancelled"
        % (_lit(user_hash), _lit(class_key)))


def _memory_lookup(psql, user_hash, class_key):
    rows = psql(
        "SELECT chosen_src, chosen_measure, chosen_axis, chosen_label, "
        "entity_ver, readings_fp, window_fp "
        "FROM ask_choice_memory WHERE user_hash = %s AND class_key = %s "
        "AND db_name = current_database() AND active AND NOT cancelled LIMIT 1"
        % (_lit(user_hash), _lit(class_key)))
    if not rows or not rows[0]:
        return None
    r = rows[0]
    return {
        "src": r[0] or "",
        "measure": r[1] or "",
        "axis": r[2] or "",
        "label": r[3] or "",
        "entity_ver": r[4] or "",
        "readings_fp": r[5] or "",
        "window_fp": r[6] or "",
    }


def _memory_collisions(psql, class_key):
    rows = psql(
        "SELECT chosen_src, chosen_measure, chosen_axis, "
        "count(DISTINCT user_hash) "
        "FROM ask_choice_memory WHERE class_key = %s "
        "AND db_name = current_database() AND active AND NOT cancelled "
        "GROUP BY 1, 2, 3" % _lit(class_key))
    branches = []
    users = 0
    for r in rows or []:
        n = int(r[3] or 0)
        users += n
        branches.append({
            "src": r[0] or "",
            "measure": r[1] or "",
            "axis": r[2] or "",
            "n_users": n,
        })
    if len(branches) < 2:
        return None
    return {"n_branches": len(branches), "n_users": users, "branches": branches}


def attach_choice_memory(out, *, psql, tables, peek_decision, user=None,
                         action=None, decision_id=None, enabled=True,
                         lost_box=None):
    """Дописать diag.memory. kind/text/figures не меняет (shadow)."""
    if not isinstance(out, dict):
        return out
    kind, text = out.get("kind"), out.get("text")
    figures, options = out.get("figures"), out.get("options")
    atom, atoms = out.get("atom"), out.get("atoms")
    mem = {"mode": "shadow"}
    if not enabled:
        mem["off"] = True
        return _stamp(out, mem, kind, text, figures, options, atom, atoms)
    try:
        uh = user_hash_of(user)
        meta = class_meta_of(out)
        ticket = None
        terr = None
        if decision_id:
            ticket, terr = peek_decision(decision_id, user=user)
        if action == "remember":
            if not uh:
                mem["action"] = "remember"
                mem["error"] = "need_user"
            elif not ticket:
                mem["action"] = "remember"
                mem["error"] = terr or "need_ticket"
            else:
                readings = list(ticket.get("readings") or meta["readings"])
                measure = ticket.get("measure_ctx") or meta["measure_ctx"]
                window = ticket.get("window_fp") or meta["window_fp"]
                ck = ticket.get("class_key") or choice_class_key(
                    readings, measure, window)
                ver = choice_entity_ver(psql, tables, readings)
                _memory_upsert(psql, {
                    "user_hash": uh,
                    "class_key": ck,
                    "readings_fp": "|".join(readings),
                    "measure_ctx": measure or "",
                    "window_fp": window or "",
                    "chosen_src": ticket.get("src") or "",
                    "chosen_measure": (ticket.get("measure")
                                       if ticket.get("measure") is not None
                                       else "") or "",
                    "chosen_axis": ticket.get("axis") or "",
                    "chosen_label": ticket.get("label") or "",
                    "entity_ver": ver,
                    "ticket_id": ticket.get("decision_id") or "",
                })
                mem["action"] = "remember"
                mem["stored"] = True
                mem["class_key"] = ck
                meta = {"class_key": ck, "readings": readings,
                        "measure_ctx": measure, "window_fp": window}
        elif action == "forget":
            ck = (ticket or {}).get("class_key") or ""
            if not ck and meta.get("readings"):
                ck = meta.get("class_key") or ""
            mem["action"] = "forget"
            if not uh:
                mem["error"] = "need_user"
            elif not ck:
                mem["error"] = "need_class"
            else:
                _memory_cancel(psql, uh, ck)
                mem["cancelled"] = True
                mem["class_key"] = ck
        ck = meta.get("class_key") or ""
        has_class = bool(meta.get("readings"))
        if uh and ck and has_class:
            hit = _memory_lookup(psql, uh, ck)
            if hit:
                live_src = hit["src"] in set(meta.get("readings") or [])
                live_ver = True
                if hit.get("entity_ver") and meta.get("readings"):
                    now_ver = choice_entity_ver(psql, tables, meta["readings"])
                    live_ver = (not now_ver) or now_ver == hit["entity_ver"]
                live = live_src and live_ver
                branch = {"src": hit["src"], "measure": hit["measure"],
                          "axis": hit["axis"], "label": hit["label"]}
                mem["would_apply"] = branch
                mem["would_apply_text"] = would_apply_text(branch)
                mem["live"] = live
                if not live:
                    mem["stale"] = True
        if ck and has_class:
            coll = _memory_collisions(psql, ck)
            if coll:
                mem["collision"] = coll
        if ck and has_class and "class_key" not in mem:
            mem["class_key"] = ck
    except Exception as e:  # noqa: BLE001 — ошибка памяти не роняет ответ
        if lost_box is not None:
            lost_box[0] = int(lost_box[0]) + 1
        mem["error"] = "unavailable"
        mem["detail"] = str(e)[:160]
    return _stamp(out, mem, kind, text, figures, options, atom, atoms)


def _stamp(out, mem, kind, text, figures, options, atom, atoms):
    out = dict(out)
    d = dict(out.get("diag") or {}) if isinstance(out.get("diag"), dict) else {}
    d["memory"] = mem
    out["diag"] = d
    out["kind"] = kind
    out["text"] = text
    if figures is not None:
        out["figures"] = figures
    if options is not None:
        out["options"] = options
    if atom is not None:
        out["atom"] = atom
    if atoms is not None:
        out["atoms"] = atoms
    return out
