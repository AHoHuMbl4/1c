#!/usr/bin/env python3
"""Брендинг Open WebUI 0.11 для okna — по замеру 08.08 (OPENCLAW_BOT.md).

Исправляет форматы API, которые в первой версии скрипта были неверны:
- /openai/config/update: полный OpenAIConfigForm + OPENAI_API_CONFIGS["0"].model_ids
- модель: /api/v1/models/create (override по id), не update несуществующей
- suggestions.title — list[str], не строка
- /api/v1/configs/models — полный ModelsConfigForm
- arena off, code interpreter off (полный CodeInterpreterConfigForm)
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.environ.get("OWUI_URL", "http://127.0.0.1:8080").rstrip("/")
EMAIL = os.environ.get("ADMIN_EMAIL", "admin@okna.local")
PASSWORD = os.environ.get("ADMIN_PASS") or ""
MODEL_ID = "openclaw/default"
DISPLAY = "Ассистент 1С"
# 🔴 Дефолт — vSwitch gpu-1c (LXD proxy → okna). 10.3.0.4 — мёртвый старый бэкенд.
OPENAI_URL = os.environ.get("OPENAI_API_BASE_URL", "http://10.3.1.11:18801/v1")
OPENAI_KEY = os.environ.get("OPENAI_API_KEY") or os.environ.get("GATEWAY_TOKEN") or ""

# Open WebUI 0.11: Admin → Settings → Tasks → Follow-up.
# Штатный endpoint POST /api/v1/tasks/config/update, поле
# FOLLOW_UP_GENERATION_PROMPT_TEMPLATE (storage task.follow_up.prompt_template).
# Генератор чипов — отдельный вызов модели; извлечь нумерованные вопросы из
# последнего ответа ассистента. Детерминизм этим шаблоном не держится: если
# чип не совпал, выбор идёт номером/подписью в тексте (resolve_focus).
FOLLOW_UP_PROMPT = """### Task:
The last assistant message may list numbered questions a person can send next (lines like «1. …?»). Put those questions into follow_ups in the same order and wording, without the leading number. When numbered questions are present, add «свой вариант» as the last follow_up.

When the last assistant message has no numbered questions, suggest 3-5 follow-up questions from the user's point of view, in the conversation language.

### Output:
JSON format: { "follow_ups": ["Question 1?", "Question 2?", "Question 3?"] }
### Chat History:
<chat_history>
{{MESSAGES:END:6}}
</chat_history>"""

SUGGESTIONS = [
    {"title": ["Сколько контрагентов?", "всего в базе"], "content": "Сколько всего контрагентов в базе?"},
    {"title": ["Номенклатура", "сколько позиций"], "content": "Сколько всего номенклатуры в базе?"},
    {"title": ["Остатки", "на складах"], "content": "Какие остатки товаров на складах?"},
    {"title": ["Продажи", "за месяц"], "content": "Сколько продаж было за последний месяц?"},
]


def req(method, path, body=None, token=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = urllib.request.Request(f"{BASE}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            raw = resp.read()
            if not raw:
                return resp.status, {}
            ct = resp.headers.get("content-type", "")
            if "json" not in ct:
                return resp.status, {"_non_json": raw[:200].decode(errors="replace")}
            return resp.status, json.loads(raw)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {"raw": raw.decode(errors="replace")[:400]}
        return e.code, payload


def must_ok(label, st, body, ok=(200, 201)):
    if st not in ok:
        print(f"FAIL {label}: {st} {body}", file=sys.stderr)
        return False
    print(f"OK {label}: {st}")
    return True


def main():
    if not PASSWORD:
        print("ADMIN_PASS обязателен", file=sys.stderr)
        return 1
    if not OPENAI_KEY:
        print("OPENAI_API_KEY / GATEWAY_TOKEN обязателен", file=sys.stderr)
        return 1

    st, cfg = req("GET", "/api/config")
    if st != 200:
        print(f"OWUI недоступен: {st}", file=sys.stderr)
        return 1
    print(f"name={cfg.get('name')!r} version={cfg.get('version')!r}")

    st, reg = req("POST", "/api/v1/auths/signup", {"email": EMAIL, "password": PASSWORD, "name": "Admin"})
    print(f"signup: {st}")

    st, tok = req("POST", "/api/v1/auths/signin", {"email": EMAIL, "password": PASSWORD})
    if st != 200 or "token" not in tok:
        print(f"signin failed: {st} {tok}", file=sys.stderr)
        return 1
    auth = tok["token"]
    print(f"signed in as {tok.get('role')} {tok.get('email')}")

    # 1) OpenAI connection — только openclaw/default
    st, body = req(
        "POST",
        "/openai/config/update",
        {
            "ENABLE_OPENAI_API": True,
            "OPENAI_API_BASE_URLS": [OPENAI_URL],
            "OPENAI_API_KEYS": [OPENAI_KEY],
            "OPENAI_API_CONFIGS": {
                "0": {
                    "enable": True,
                    "tags": [],
                    "prefix_id": "",
                    "model_ids": [MODEL_ID],
                    "connection_type": "external",
                    # 🔴 ОДИН ЧАТ — ОДНА СЕССИЯ АГЕНТА. Без этого заголовка гейтвей на
                    # КАЖДОЕ сообщение заводит новую сессию (замер okna 13.08: 52 сессии
                    # с ключами `openai:<случайный uuid>` за один разговор), и бот не
                    # помнит своих прошлых вызовов инструмента — только текст истории,
                    # который дописывает сам фронт. Штатные механизмы обеих сторон:
                    # Open WebUI подставляет `{{CHAT_ID}}` в заголовки соединения
                    # (utils/headers.py), гейтвей принимает `x-openclaw-session-key`
                    # (docs/gateway/openai-http-api.md, «Explicit session routing»).
                    # `{{TASK}}` в хвосте разводит служебные вызовы фронта (заголовок
                    # чата, подсказки) в свои ключи: у обычного сообщения он пуст, и
                    # разговор остаётся чистым. Зарезервированные пространства
                    # (`subagent:`, `cron:`, `acp:`) не задеваются.
                    "headers": {"x-openclaw-session-key": "chat-{{CHAT_ID}}{{TASK}}"},
                }
            },
        },
        token=auth,
    )
    must_ok("openai/config/update", st, body)

    # 2) Override-модель «Ассистент 1С» (create; если уже есть — update)
    model_body = {
        "id": MODEL_ID,
        "base_model_id": None,
        "name": DISPLAY,
        "meta": {
            "profile_image_url": "/static/favicon.png",
            "description": "Ответы по данным учётной системы",
            "capabilities": {
                "vision": False,
                "file_upload": False,
                "web_search": False,
                "image_generation": False,
                "code_interpreter": False,
                "citations": False,
            },
            # OWUI builtin tools (search_knowledge_files, list_automations, …) —
            # не путь к данным 1С; модель уходит в RAG после сбоев билета (okna 19.08).
            "builtinTools": {
                "knowledge": False,
                "automations": False,
                "chats": False,
                "memory": False,
                "web_search": False,
                "notes": False,
                "channels": False,
                "calendar": False,
                "tasks": False,
                "files": False,
                "subagents": False,
            },
        },
        "params": {},
        "access_grants": [{"principal_type": "user", "principal_id": "*", "permission": "read"}],
        "is_active": True,
    }
    st, body = req("POST", "/api/v1/models/create", model_body, token=auth)
    if st in (200, 201):
        print(f"OK models/create: {st}")
    else:
        st2, body2 = req("POST", "/api/v1/models/model/update", model_body, token=auth)
        must_ok("models/model/update", st2, body2)

    # 3) default model + order
    st, body = req(
        "POST",
        "/api/v1/configs/models",
        {
            "DEFAULT_MODELS": MODEL_ID,
            "DEFAULT_PINNED_MODELS": MODEL_ID,
            "MODEL_ORDER_LIST": [MODEL_ID],
            "DEFAULT_MODEL_METADATA": None,
            "DEFAULT_MODEL_PARAMS": None,
        },
        token=auth,
    )
    must_ok("configs/models", st, body)

    # 4) suggestions (title = list[str])
    st, body = req("POST", "/api/v1/configs/suggestions", {"suggestions": SUGGESTIONS}, token=auth)
    must_ok("configs/suggestions", st, body)

    # 5) banners empty
    st, body = req("POST", "/api/v1/configs/banners", {"banners": []}, token=auth)
    must_ok("configs/banners", st, body)

    # 6) arena off
    st, body = req(
        "POST",
        "/api/v1/evaluations/config",
        {"ENABLE_EVALUATION_ARENA_MODELS": False, "EVALUATION_ARENA_MODELS": []},
        token=auth,
    )
    must_ok("evaluations/config", st, body)

    # 7) code interpreter / execution off (полный form)
    st, cur = req("GET", "/api/v1/configs/code_execution", token=auth)
    if st == 200 and isinstance(cur, dict):
        cur["ENABLE_CODE_EXECUTION"] = False
        cur["ENABLE_CODE_INTERPRETER"] = False
        st, body = req("POST", "/api/v1/configs/code_execution", cur, token=auth)
        must_ok("configs/code_execution", st, body)
    else:
        print(f"skip code_execution get: {st} {cur}", file=sys.stderr)

    # 8) admin: без community sharing / overlay
    st, adm = req("GET", "/api/v1/auths/admin/config", token=auth)
    if st == 200 and isinstance(adm, dict):
        adm["SHOW_ADMIN_DETAILS"] = False
        adm["ENABLE_COMMUNITY_SHARING"] = False
        adm["ENABLE_MESSAGE_RATING"] = False
        if os.environ.get("WEBUI_URL"):
            adm["WEBUI_URL"] = os.environ["WEBUI_URL"]
        st, body = req("POST", "/api/v1/auths/admin/config", adm, token=auth)
        must_ok("auths/admin/config", st, body)

    # 9) права обычного юзера: без выбора нескольких моделей и «интеграций»
    st, perms = req("GET", "/api/v1/users/default/permissions", token=auth)
    if st == 200 and isinstance(perms, dict):
        perms.setdefault("chat", {})
        perms["chat"]["multiple_models"] = False
        perms["chat"]["system_prompt"] = False
        perms["chat"]["params"] = False
        perms["chat"]["controls"] = False
        perms["chat"]["valves"] = False
        perms.setdefault("features", {})
        perms["features"]["code_interpreter"] = False
        perms["features"]["web_search"] = False
        perms["features"]["image_generation"] = False
        perms["features"]["direct_tool_servers"] = False
        st, body = req("POST", "/api/v1/users/default/permissions", perms, token=auth)
        must_ok("users/default/permissions", st, body)

    # 10) follow-up chips: copy numbered questions from last assistant message
    st, tasks = req("GET", "/api/v1/tasks/config", token=auth)
    if st == 200 and isinstance(tasks, dict):
        tasks["ENABLE_FOLLOW_UP_GENERATION"] = True
        tasks["FOLLOW_UP_GENERATION_PROMPT_TEMPLATE"] = FOLLOW_UP_PROMPT
        st, body = req("POST", "/api/v1/tasks/config/update", tasks, token=auth)
        must_ok("tasks/config/update", st, body)
    else:
        print(f"skip tasks/config get: {st} {tasks}", file=sys.stderr)

    # Проверка: список моделей для админа
    st, models = req("GET", "/api/models", token=auth)
    if st == 200 and isinstance(models, dict):
        names = [(m.get("id"), m.get("name")) for m in models.get("data", [])]
        print("models:", names)
        ids = {m.get("id") for m in models.get("data", [])}
        if "openclaw" in ids or "openclaw/main" in ids:
            print("WARN: лишние openclaw-модели ещё видны админу", file=sys.stderr)
        if MODEL_ID not in ids:
            print("WARN: openclaw/default нет в списке", file=sys.stderr)
        renamed = next((n for i, n in names if i == MODEL_ID), None)
        if renamed != DISPLAY:
            print(f"WARN: имя модели {renamed!r}, ждали {DISPLAY!r}", file=sys.stderr)
        else:
            print(f"OK display name = {DISPLAY}")

    print(f"DONE admin={EMAIL}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
