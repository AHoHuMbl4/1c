"""
title: Добавить в дашборд
author: 1c
version: 0.1.0
required_open_webui_version: 0.5.0
description: Кнопка под ответом: закрепляет посчитанное базой в личном дашборде Grafana.
"""

# Action-функция Open WebUI: кнопка под сообщением ассистента.
#
# 🔴 Кнопка НИЧЕГО не сочиняет. Она берёт спецификацию счёта, которую объявил
# сам serene_ask (источник, условие, величина, ось), и отдаёт её адаптеру
# `/dash/add`; SQL панели собирается детерминированно там. Модель в этой
# дороге не участвует: она не пишет запрос и не видит схему (п. 19, 20
# TARGET.md, docs/DASHBOARD_GRAFANA.md §2).
#
# Спецификация приходит в метаданных сообщения (ключ `ask_scope`). Пока
# бэкенд её не отдаёт, кнопка честно говорит, что закреплять нечего, —
# и НЕ пытается угадать источник по тексту ответа: догадка здесь была бы
# ровно тем дефектом, ради которого числа считает база (п. 12).

from typing import Optional

import requests
from pydantic import BaseModel, Field


class Action:
    class Valves(BaseModel):
        adapter_url: str = Field(
            default="http://127.0.0.1:3002/dash/add",
            description="Ручка адаптера дашбордов (loopback фронта)")
        timeout_sec: int = Field(default=20, description="Потолок ожидания адаптера")

    def __init__(self):
        self.valves = self.Valves()

    async def action(self, body: dict, __user__: Optional[dict] = None,
                     __request__=None, __event_emitter__=None, **_) -> Optional[dict]:
        async def say(text: str, done: bool = True):
            if __event_emitter__:
                await __event_emitter__(
                    {"type": "status", "data": {"description": text, "done": done}})

        messages = body.get("messages") or []
        message = messages[-1] if messages else {}
        scope = ((message.get("metadata") or {}).get("ask_scope")
                 or (body.get("metadata") or {}).get("ask_scope"))
        if not scope:
            await say("Закреплять нечего: в ответе нет спецификации счёта "
                      "(источник и величина). Кнопка работает на ответах с числом.")
            return None

        await say("Добавляю панель…", done=False)
        cookie = ""
        if __request__ is not None:
            cookie = __request__.headers.get("cookie", "")
        try:
            resp = requests.post(self.valves.adapter_url, json=scope,
                                 headers={"Cookie": cookie},
                                 timeout=self.valves.timeout_sec)
        except requests.RequestException as exc:
            await say(f"Адаптер дашбордов недоступен: {exc}")
            return None
        if resp.status_code != 200:
            await say(f"Панель не добавлена ({resp.status_code}): {resp.text.strip()}")
            return None

        out = resp.json()
        await say(f"Панель «{out.get('title')}» добавлена: {out.get('url')}")
        return {"content": f"[Открыть панель «{out.get('title')}»]({out.get('url')})"}
