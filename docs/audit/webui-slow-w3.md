# W3: веб-агент — вики-ключ 401, утечка thinking, агентная модель

Срезы: `.claude/state/webui-slow/{web-profile-config.txt,gateway-extract.txt,gateway.log}`.  
Код: `ubuntu/openclaw/verify-plugin/`, `ubuntu/open-webui/setup-okna-backend-web.sh`.  
Режим: только чтение. Хост аудита: `lxc-claude-1c` (живой `~/.openclaw-web` на okna отсюда не читается — 700 undebot; факты по ключу 401 — замер оркестратора + канон setup). Дата: 11.09.

---

## 1. Ходы агента (gateway.log)

Вопрос владельца, sess=`agent:main:chat-aa3d9b69-…`, run=`chatcmpl_282236a6`.

| t UTC | событие | исход |
|---|---|---|
| 06:33:51 | `agent_start` + model-fetch deepseek-v4-pro | **200**, ~405–472 мс |
| 06:33:54 | `wiki_search` | **block side** (braine-verify) → снова LLM |
| 06:33:56 | `wiki_search` | block side → LLM |
| 06:33:57 | `wiki_get` | block side → LLM |
| 06:33:59 | `wiki_search` | block side → LLM |
| 06:34:02 | `serene-ask__ask_1c` старт | (см. W1: **153801 мс**, clarify) |
| 06:36:08 | stalled session age=137s | `lastProgress=model_call:ended` (ждёт ask) |
| 06:36:36 | `after_tool_call ask_1c` | refDigits=18, noData=false; clarify_lock opts=3 |
| 06:36:36–39 | model-fetch + finalize | revise `why=figures` → **finalizing** (без нового model) |
| 06:36:39 | ответ в логе | русское уточнение (3 отчёта) |

Параллельно крутятся служебные прогоны OWUI (`…title_generation`, `…follow_up_generation`, `…tags_generation`) — каждый со своим `agent_start` / model-fetch / revise `no-data-tool`.

**Хорды LLM на вопрос владельца (основной run):**  
**4** (wiki blocked) + **1** (до ask) + **1** (после ask → clarify) = **6** вызовов `deepseek-v4-pro` до ответа.  
Плюс ≥4 служебных model-fetch (title/follow_up/tags) в том же окне.

**«verification message» в логе как текст инструмента нет.** Есть только  
`[braine-verify] before_tool_call block side tool=wiki_*`  
и код: `return { block: true, blockReason: "braine-verify: data turn uses ask_1c only" }`  
(`verify-plugin/index.js:275-278`, список `wiki_` / `memory_search` / OWUI knowledge — `verify-core.js:286-294`).  
Агент в следующем ходе сам называет это «verification message» (см. §3) — это **отражённый blockReason**, не ответ эмбеддера.

Короткий смок раньше (sess `…dc6bc207…`, 06:27): 2× wiki block → ask_1c ~108 с → «За вчерашний день — 107 продаж» (figures-ok). Тот же паттерн.

---

## 2. Агентная модель / DEEPSEEK_API_KEY

| Проверка | Результат |
|---|---|
| `model-fetch` → `https://api.deepseek.com/chat/completions` | **19/19 status=200**, elapsed ~399–511 мс |
| status≠200 в срезе | **0** |
| `/etc/1c-serene-ask-postgres.env` | **DEEPSEEK_API_KEY отсутствует** (гипотеза «sk-or в ask-postgres» на этом хосте не подтверждается) |
| `/etc/1c-mcp-reports.env` `DEEPSEEK_API_KEY` | `uAI_…` sha16=`0e3b01faabe47343` (= `EMBED_API_KEY`); `DEEPSEEK_BASE=http://gpu-27b.timpul.pro:8000` — это **vLLM ask-контура**, не api.deepseek.com |
| setup web | копирует `DEEPSEEK_API_KEY` из `~/.openclaw/gateway.systemd.env` → `~/.openclaw-web/…`; baseUrl в генераторе = `api.deepseek.com` |

**Вывод:** гипотеза «OpenRouter-ключ на api.deepseek.com → агент 401 на каждом шаге» — **опровергнута логом**. Агент **работает на своей модели**; ask_1c — отдельный контур (vLLM/OpenRouter внутри serene-ask), не «спасает» упавший deepseek.com.

`~/.openclaw-web/gateway.systemd.env` с этой LXC не прочитан (нет каталога / 700). Отпечаток live DEEPSEEK на okna — только через замер на okna; по HTTP-статусам ключ для api.deepseek.com **валиден**.

---

## 3. Утечка «thinking» (EN в чат)

Факт: в контексте следующего `ask_1c` (timeout 06:42:23) в `Assistant:` лежит склеенное:

`The wiki tools are returning a verification message rather than actual results. Let me proceed with the data tool…` + русское «Уточню…».

При этом `thinkingDefault: off` (срез конфига + setup:152). В gateway в момент finalize в `message` попало только русское уточнение — EN уже сидит в **истории сессии** как content ассистента.

### Гипотезы (с проверкой)

| # | Гипотеза | Проверка | Статус |
|---|---|---|---|
| H1 | Это не канал `thinking`/`reasoning`, а **content**: модель пишет meta-рассуждение про tools в обычный текст ответа (thinkingDefault=off как раз отключает отдельный thinking-канал, но не запрещает болтовню в content) | Текст — про wiki/tools; нет `<think>`/reasoning-полей в логе; deepseek stream `text/event-stream` | **наиболее вероятно** |
| H2 | OpenClaw/OWUI **стримит промежуточный** assistant-текст до tool_call; EN ушёл в UI/историю до finalize; braine `revise figures` + `finalizing` правит только финальную доставку | Gateway на 06:36:39 логирует только RU; следующий ход видит EN+RU в Assistant | **совместимо с логом**; нужна стенограмма SSE OWUI |
| H3 | braine `stripInternal` / `hasProtocolLeak` **не ловят** эту фразу | Паттерны режут `decision_id` / ticket / `ask_1c`; «wiki tools…verification message» — **мимо** (тест-кейсы `test-verify.mjs:717-725` про другое) | **подтверждено кодом** |

`ASK_THINKING_OFF_BODY` / `reasoning.enabled=false` в ask (`z01_infra_trace_llm.py:526-532`) на **агентный** deepseek-v4-pro не действуют — другой контур.

---

## 4. Вики / EMBED 401

**Замер оркестратора (принять как факт):** ключ из web `gateway.systemd.env` → эмбеддер **401**; ключ ask-контура → **200**. Вики-поиск по memorySearch на каждом ходе мёртв.

На аудиторе (`lxc-claude-1c`):

| Источник | EMBED отпечаток |
|---|---|
| `/etc/1c-embed.env` `EMBED_API_KEY` | sha16=`0e3b01faabe47343`, prefix=`uAI_1I…` |
| `EMBED_HOSTS` (оба хоста) | **тот же** sha |
| `/etc/1c-mcp-reports.env` `DEEPSEEK_API_KEY` (vLLM) | **тот же** sha |

Канон setup (`setup-okna-backend-web.sh:117-128,156-164`):

1. `source /etc/1c-embed.env` → дописывает `EMBED_API_KEY=` в `~/.openclaw-web/gateway.systemd.env`;
2. в `openclaw.json` кладёт `"apiKey": "${EMBED_API_KEY}"` (SecretRef/env-шаблон OpenClaw);
3. unit: `EnvironmentFile=…/gateway.systemd.env` + `OPENCLAW_SERVICE_MANAGED_ENV_KEYS=…,EMBED_API_KEY`.

**Почему на okna мог оказаться неверный ключ (без живого файла — по механике):**

1. env на okna правили руками / старый файл переживает setup (скрипт не всегда перезаписывает целиком — сначала DEEPSEEK-строка, потом append EMBED);
2. юнит не перезапускали после смены ключа → managed env держит старое;
3. `${EMBED_API_KEY}` не резолвится (ключ не в managed env) → на эмбеддер уходит буквальный мусор → 401;
4. реже: `/etc/1c-embed.env` на okna расходится с тем ключом, которым ask реально ходит на gpu-erw (на этом хосте sha совпадает с mcp-reports).

**Однострочный фикс (на okna, root/undebot):**

```bash
grep -E '^EMBED_API_KEY=' /etc/1c-embed.env | sudo tee -a /home/undebot/.openclaw-web/gateway.systemd.env >/dev/null; sudo sed -i '/^EMBED_API_KEY=/!b;:a;n;/^EMBED_API_KEY=/{d;ba}' /home/undebot/.openclaw-web/gateway.systemd.env 2>/dev/null; true
```

Практичнее и безопаснее (оставить одну строку):

```bash
f=/home/undebot/.openclaw-web/gateway.systemd.env; k=$(grep -E '^EMBED_API_KEY=' /etc/1c-embed.env | tail -1); grep -v '^EMBED_API_KEY=' "$f" >"$f.tmp"; printf '%s\n' "$k" >>"$f.tmp"; mv "$f.tmp" "$f"; chown undebot:undebot "$f"; chmod 600 "$f"; systemctl restart openclaw-gateway-web
```

Проверка: `curl -sS -o /dev/null -w '%{http_code}\n' -H "Authorization: Bearer $(grep EMBED_API_KEY /home/undebot/.openclaw-web/gateway.systemd.env|cut -d= -f2-)" -H 'Content-Type: application/json' -d '{"model":"Qwen3-Embedding-4B","input":"ping"}' http://gpu-erw.timpul.pro:8000/v1/embeddings` → ожидать **200**.

Отдельно: даже с живым эмбеддером на **data-turn** `wiki_*` всё равно режет braine-verify (§1) — 401 объясняет memory index / фоновый поиск; **«verification message» в этом замере — блок плагина**, не HTTP 401.

---

## 5. Итог: что чинить

| Проблема | Фикс | Порядок | Риск |
|---|---|---|---|
| EMBED 401 в web env | Переписать `EMBED_API_KEY` из `/etc/1c-embed.env` в `~/.openclaw-web/gateway.systemd.env` + restart `openclaw-gateway-web` | **1** | Низкий: только web-профиль; сверить 200 на `/v1/embeddings` |
| 4 пустых wiki-хорды / «verification message» | Убрать `wiki_search`/`wiki_get` из `tools.allow` **или** не блокировать wiki до первого ask (продуктовое решение: сейчас wiki в allow, но side-block на data-turn) | **2** | Средний: без wiki агент не знает имён сущностей базы → больше clarify/ошибочный focus; с wiki без блока — риск обхода ask |
| EN meta в content | Кодом: расширить `hasProtocolLeak`/`stripInternal` на фразы про tools/verification **или** не стримить промежуточный assistant-text до финала (OWUI/OpenClaw stream policy); `thinkingDefault=off` **уже стоит и не лечит** | **3** | Низкий для strip; средний если резать стрим — UX «молчание» дольше |
| Модель агента deepseek-v4-pro | **Не чинить по 401** — работает. Отдельно: flash в генераторе setup vs pro в live-срезе — рассинхрон конфига, на скорость/цену влияет, не на auth | по желанию | Низкий |
| Двойной LLM (агент + ask) + 30k prompt | Вне W3 (см. W1/W4); здесь лишь усиливает цену каждой лишней wiki-хорды | после 1–2 | — |

**Порядок внедрения:** ключ (1) → сократить бесполезные wiki-итерации (2) → заткнуть утечку content (3).  
Пункт 2 даёт больше выигрыша по времени, чем 401: в этом замере wiki и так не исполнялся (block), а **~8 с** ушли на 4× model round-trip до ask; 401 бьёт memorySearch/индекс, не эти block-хорды.
