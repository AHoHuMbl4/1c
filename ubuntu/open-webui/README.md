# Веб-фронт okna (Open WebUI + Caddy)

Домен **`baulogistic.timpul.pro`** → `openclaw-okna` (`2.28.49.158` / `10.3.0.2`).  
Бэкенд OpenClaw web-профиль → okna-юнит (`167.233.249.110` / `10.3.0.4` / `:18801`).

```
браузер → https://baulogistic.timpul.pro  (Caddy → Open WebUI :8080 loopback)
        → http://10.3.0.4:18801/v1  (OpenClaw web, bind=lan, ufw только с 10.3.0.2)
        → 1c-mcp-ask@postgres → 1c-serene-ask@postgres
```

На прод-юните dbname всегда `postgres` (слот `okna-1` — одна СУБД).

## Предусловия

1. DNS: `baulogistic.timpul.pro` A → `2.28.49.158`.
2. Deploy-ключ с дева на оба сервера (`~/.ssh/id_ed25519_deploy`).
3. На бэкенде: undebot + openclaw, `/etc/1c-serene-ask.env`, слот okna-1.
4. Скрипты: rsync `ubuntu/open-webui/` → `/opt/1c-open-webui/` на оба хоста.

## Установка (два шага)

### 1. Бэкенд (10.3.0.4)

```bash
bash /opt/1c-open-webui/setup-okna-backend-web.sh
```

Печатает `GATEWAY_TOKEN=…`. Поднимает `1c-serene-ask@postgres`, `1c-mcp-ask@postgres`,
`openclaw-gateway-web` (:18801, ufw с 10.3.0.2). Web-профиль включает
`agents.defaults.memorySearch` (openai-compatible на `/etc/1c-embed.env`) и
`EMBED_API_KEY` в env юнита — без этого memory-core шлёт `Memory index failed`.

### 2. Фронт (10.3.0.2)

```bash
GATEWAY_TOKEN='<из шага 1>' bash /opt/1c-open-webui/setup-okna-front.sh
```

Ubuntu 24.04 (Python 3.12) — обычный venv; Ubuntu 26.04 (3.14) — Python 3.12 через uv.
🔴 ufw: сначала `22/tcp`, потом 80/443 (иначе SSH отрежется — случай 13.08).
После старта WebUI — `systemctl reload caddy` (иначе LE не стартует).

## Вход

Админ: `anton@baulogistic.md` (пароль — у владельца, не в git).

## Приёмка

- `curl -sI https://baulogistic.timpul.pro/` → HTTP/2 200
- Вход админом → одна модель «Ассистент 1С»
- Брендинг: `configure-branding.py` (API 0.11: `OPENAI_API_CONFIGS["0"].model_ids`,
  `POST /api/v1/models/create` override, suggestions с `title: list[str]`).
  В env: `ENABLE_VERSION_UPDATE_CHECK=false` — без changelog-окна Open WebUI.
- UI: `static/brand-ui.css` скрывает Workspace и селектор моделей (`#model`).
- Вопрос по данным → уточнение → число
- Голос (STT): Whisper Large-v3 на GPU владельца (`AUDIO_STT_ENGINE=openai`,
  `AUDIO_STT_OPENAI_API_BASE_URL` → `/v1`, модель `whisper-large-v3`; язык не фиксируем — выбор в UI / авто Whisper).
  🔴 **`audio.stt.*` в `webui.db` перекрывает env** — при смене эндпоинта править БД
  (бэкап до правки) + env; см. `work/acceptance/okna-web-stt-fix.sh`.
  Ключ только в `/home/webui/.open-webui.env` (и Admin → Audio); не в git.
  Замер: `POST /api/v1/audio/transcriptions` через OWUI → 200, текст от Whisper.

## Один чат — одна сессия агента

🔴 Без этого гейтвей заводит НОВУЮ сессию на каждое сообщение: `[замер okna 13.08]`
52 сессии с ключами `agent:main:openai:<случайный uuid>` за один разговор. История в
чат всё равно доезжает текстом (её дописывает сам фронт), но бот не помнит СВОЕГО —
прошлый вызов инструмента, полученное уточнение, уже отвергнутые варианты.

Держится штатными механизмами обеих сторон:

- Open WebUI подставляет `{{CHAT_ID}}` в пользовательские заголовки соединения
  (`utils/headers.py`);
- гейтвей принимает `x-openclaw-session-key` — «explicit session routing»
  (`docs/gateway/openai-http-api.md`).

Настройка соединения (`openai.api_configs["0"].headers`, ставит `configure-branding.py`):

```
x-openclaw-session-key: chat-{{CHAT_ID}}{{TASK}}
```

`{{TASK}}` в хвосте уводит служебные вызовы фронта (заголовок чата, подсказки) в свои
ключи — у обычного сообщения он пуст, и разговор остаётся чистым. Зарезервированные
пространства (`subagent:`, `cron:`, `acp:`) не задеваются.

`[замер 13.08]` два запроса с одним ключом → **одна** сессия `agent:main:chat-…`.
Проверка на живом контуре: `openclaw --profile web sessions --json` на юните — ключи
разговоров выглядят как `agent:main:chat-<id чата>`, а не `openai:<uuid>`.

## Юниты

| Хост | Юнит | Пользователь |
|---|---|---|
| 10.3.0.4 | `openclaw-gateway-web.service` (user) | `undebot` |
| 10.3.0.4 | `1c-serene-ask@postgres`, `1c-mcp-ask@postgres` | system |
| 10.3.0.2 | `open-webui.service` (user) | `webui` |
| 10.3.0.2 | `caddy.service` | system |

Разбор — `docs/OPENCLAW_BOT.md` (раздел «Веб-фронт» / okna prod).
