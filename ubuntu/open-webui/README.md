# Веб-фронт okna (Open WebUI + Caddy)

Домен **`baulogistic.timpul.pro`** → `openclaw-okna` (`2.28.49.158` / `10.3.0.2`).  
Бэкенд — контейнер **okna** на хосте gpu-1c, снаружи через vSwitch-адрес хоста
**10.3.1.11:18801** (LXD proxy). Схема сети — §«Сеть» ниже.

```
браузер → https://baulogistic.timpul.pro  (Caddy → Open WebUI :8080 loopback, хост 10.3.0.2)
        → http://10.3.1.11:18801/v1  (vSwitch → LXD proxy nat=true на хосте gpu-1c)
        → контейнер okna 10.10.10.12:18801  (OpenClaw web, undebot, --bind lan)
        → 1c-mcp-ask@postgres → 1c-serene-ask@postgres
```

## Сеть (зафиксировано 29.08, всё измерено живьём)

| Что | Адрес |
|---|---|
| Хост **gpu-1c** (= `gpu-erw.timpul.pro`) | публичный `178.63.211.188`; vSwitch `eno1.4003` = **10.3.1.11/24** (mtu 1400, маршрут `10.3.0.0/16 via 10.3.1.1`); LXD-мост `lxdbr0` = 10.10.10.1/24 |
| Контейнер **okna** (прод: serenedb, ask, openclaw) | 10.10.10.12 (eth0, DHCP от lxdbr0); ssh снаружи `178.63.211.188:2202` |
| Контейнер klient1 | 10.10.10.11, ssh `:2201` |
| Фронт **openclaw-okna** | 2.28.49.158 / **10.3.0.2**, маршрут `10.3.0.0/16 via 10.3.0.1` |
| pro-router | 2.28.54.129 / 10.3.0.3 |

vSwitch Hetzner (внутренняя сеть) маршрутизирует **10.3.0.0/24 ↔ 10.3.1.0/24** —
фронт и хост gpu-1c видят друг друга напрямую (замер 29.08: `10.3.1.11:18801` с
фронта → 200).

LXD proxy на хосте (`nat=true`): `10.3.1.11:6090 → okna:6090`,
`10.3.1.11:18090 → okna:18090`, **`10.3.1.11:18801 → okna:18801`** (добавлен
29.08), публичный `178.63.211.188:2202 → okna:22`.

🔴 **10.3.0.4 / 167.233.249.110 — старый бэкенд до переезда 22.08, НЕ существует.**
Любая ссылка на него = поломка. Внутри okna: ask `:8091` loopback; web-шлюз
`:18801` `--bind lan` + `gateway.http.endpoints.chatCompletions.enabled=true`
(❗ не `gateway.http.enabled` — невалидный путь, шлюз падает 78/CONFIG);
телеграм-шлюз `:18800` **остановлен и disable 29.08** (решение владельца,
возврат `systemctl --user enable --now openclaw-gateway`).
Дефолтный агент web-профиля — явный `{"id":"main","default":true}` в
`agents.list` (иначе дефолт = первый элемент списка, им стал сервисный dict).
Плагин verify: `npm pack` в `ubuntu/openclaw/verify-plugin/` → `openclaw
plugins install npm-pack:<tgz> --force` в каждый профиль (+`--profile web`).

На прод-юните dbname всегда `postgres` (слот `okna-1` — одна СУБД).

## Предусловия

1. DNS: `baulogistic.timpul.pro` A → `2.28.49.158`.
2. Deploy-ключ с дева на оба сервера (`~/.ssh/id_ed25519_deploy`).
3. На бэкенде: undebot + openclaw, `/etc/1c-serene-ask.env`, слот okna-1.
4. Скрипты: rsync `ubuntu/open-webui/` → `/opt/1c-open-webui/` на оба хоста.

## Установка (два шага)

### 1. Бэкенд (контейнер okna на gpu-1c, снаружи 10.3.1.11)

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

## Дашборды (Grafana)

Решение владельца 18.08: страница дашбордов — Grafana на **этом же фронте**
(10.3.0.2), подпуть `https://baulogistic.timpul.pro/dash/`. Дизайн и замеры —
[`docs/DASHBOARD_GRAFANA.md`](../../docs/DASHBOARD_GRAFANA.md).

```
браузер → /dash/enter → 1c-dash-enter (:3002, dash_adapter.py)
                          │ проверяет cookie `token` у OWUI (GET /api/v1/auths/),
                          │ ставит cookie gf_jwt (RS256 JWT, 12 ч), 302
        → Caddy handle /dash/* → Grafana (:3001, loopback)
                          │ header_up X-JWT-Assertion = cookie gf_jwt → вход без формы
Grafana → SereneDB бэкенда через 1c-serene-lan-relay — 🔴 мёртв после переезда
22.08: relay слушал 10.3.0.4:7890, адреса нет, юнит на okna не поднимался. Не
чинено (владелец не просил); когда понадобится — тот же способ, что и 18801:
LXD proxy `10.3.1.11:7890 → okna:7890` + правка datasource Grafana.
```

Установка:

```bash
# бэкенд (контейнер okna) — релей SereneDB на LAN (systemd-socket-proxyd, движок не трогаем):
bash /opt/1c-open-webui/setup-okna-backend-serene-lan.sh
# фронт (10.3.0.2):
SERENE_RO_PW=<PGPASSWORD из /etc/1c-mcp-reports.env бэкенда> \
  bash /opt/1c-open-webui/setup-okna-grafana.sh
```

- Вход — только сквозной: пользователь чата открывает `/dash/enter` и попадает
  на дашборды без второго логина (роль: admin чата → Admin Grafana, остальные
  Viewer). Нативный логин Grafana (admin, пароль в `/etc/1c-grafana.env`) —
  запасной, для администрирования.
- Ключи: приватный `/etc/1c-grafana-jwt-private.pem` (640 root:dashenter,
  читает только адаптер), публичный у Grafana.
- Пароль `serene_ro` — в `/etc/1c-grafana.env` (640 root:root) на фронте;
  datasource создаётся скриптом через API.

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

## Follow-up чипы (Tasks)

Чипы под ответом рисует Open WebUI своим генератором, не шлюзом OpenClaw.
В установленной сборке (venv `/home/claudedev/open-webui-venv`):

- UI: Admin → Settings → Tasks → Follow-up;
- чтение: `GET /api/v1/tasks/config` (Bearer после `POST /api/v1/auths/signin`);
- запись: `POST /api/v1/tasks/config/update` (роль админа), поля
  `ENABLE_FOLLOW_UP_GENERATION` и `FOLLOW_UP_GENERATION_PROMPT_TEMPLATE`
  (storage `task.follow_up.enable` / `task.follow_up.prompt_template`);
- сам чип: `POST /api/v1/tasks/follow_up/completions` — отдельный вызов модели
  по последним сообщениям (`{{MESSAGES:END:6}}`).

Auth тот же, что у `configure-branding.py`: `ADMIN_EMAIL` / `ADMIN_PASS` →
signin → Bearer. Скрипт ставит шаблон «скопировать нумерованные вопросы
`1. …?` из последнего ответа ассистента и добавить «свой вариант»». Это не
детерминированный канал: модель генератора может перефразировать или
выкинуть пункт. Надёжный путь выбора — нумерованные строки в тексте +
`resolve_focus` / замок плагина. Статические suggestions на экране чата
для развилок не подходят (набор вариантов зависит от вопроса).

Живой POST на прод-фронт этим шагом не делали — выкат оркестратору.

## Юниты

| Хост | Юнит | Пользователь |
|---|---|---|
| okna (контейнер, 10.10.10.12) | `openclaw-gateway-web.service` (user) | `undebot` |
| okna (контейнер, 10.10.10.12) | `1c-serene-ask@postgres`, `1c-mcp-ask@postgres` | system |
| okna (контейнер, 10.10.10.12) | `1c-serene-lan-relay.socket/.service` (SereneDB → LAN для Grafana; 🔴 не поднят после переезда) | system |
| gpu-1c (хост) | LXD proxy `10.3.1.11:18801 → okna:18801` | root |
| 10.3.0.2 (фронт) | `open-webui.service` (user) | `webui` |
| 10.3.0.2 | `caddy.service` | system |
| 10.3.0.2 | `1c-grafana.service` (:3001, подпуть /dash/) | `grafana` |
| 10.3.0.2 | `1c-dash-enter.service` (:3002, сквозной вход) | `dashenter` |

Разбор — `docs/OPENCLAW_BOT.md` (раздел «Веб-фронт» / okna prod).
