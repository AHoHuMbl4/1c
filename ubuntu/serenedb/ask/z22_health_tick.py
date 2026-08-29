"""Zone 22: tick_status для GET /health (PLAN_WIKI_CHOICE §7)."""
from __future__ import annotations

from ask._imports import *
from ask._wire import register_zone, apply_bindings

apply_bindings(globals())

_TICK_STATUS_NOTE_RE = re.compile(r"^fail=(\d+)\|reason=(.*)$")


def _parse_tick_status_note(note):
    """Разбор note k=tick_status: fail=<epoch>|reason=<step>:<category>."""
    if not note:
        return 0, ""
    m = _TICK_STATUS_NOTE_RE.match(str(note).strip())
    if not m:
        return 0, ""
    return int(m.group(1)), (m.group(2) or "").strip()


def _measure_tick_status():
    """Статус последнего такта из search_quality.k=tick_status."""
    try:
        r = psql("SELECT v, note FROM search_quality WHERE k='tick_status'")
    except RuntimeError as e:
        return {"known": False, "error": str(e)[:200]}
    if not r or not r[0]:
        return {"known": False}
    last_ok = int(_num(r[0][0]) or 0)
    note = r[0][1] if len(r[0]) > 1 else ""
    last_fail, reason = _parse_tick_status_note(note)
    now = int(time.time())
    out = {
        "known": True,
        "last_ok_age_sec": None,
        "last_fail_age_sec": None,
        "had_recent_fail": False,
        "fail_reason": reason or None,
    }
    if last_ok > 0:
        out["last_ok_age_sec"] = max(0, now - last_ok)
    if last_fail > 0:
        out["last_fail_age_sec"] = max(0, now - last_fail)
        out["had_recent_fail"] = last_fail > last_ok
    parts = []
    if out["last_ok_age_sec"] is not None:
        parts.append("\u0441\u0432\u0435\u0436\u0435\u0441\u0442\u044c+%d \u043c\u0438\u043d"
                       % (out["last_ok_age_sec"] // 60))
    elif last_ok == 0:
        parts.append("\u0441\u0432\u0435\u0436\u0435\u0441\u0442\u044c \u043d\u0435\u0438\u0437\u0432\u0435\u0441\u0442\u043d\u0430")
    if out["had_recent_fail"] and reason:
        parts.append(reason)
    out["summary"] = ", ".join(parts)
    return out


register_zone()
