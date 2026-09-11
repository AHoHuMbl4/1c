# S3: ранний clarify и отмена бесполезной работы (обрыв клиента, хвосты)

Режим: только чтение. Дата: 11.09.2026.  
Опора: `docs/audit/webui-slow-w1..w4.md`, код `ubuntu/serenedb/ask/*.py`, мост `ubuntu/openclaw/mcp_ask.py`, CHANGELOG 11.09 (4) (ASK_TIMEOUT=90 / requestTimeoutMs=100000).

---

## Вердикт

1. Меню «3 ветки продаж» — **entity-clarify** после полного префикса и (часто) **круга арбитра ×N полных `answer`**. Дешёвого выхода «кандидаты >1 → меню» **до** отбора/реранков/арбитра нет. Калибр 15272 мс (вызов 3) доказывает коридор, не ранний выход на том же коде.
2. Обрыв клиента (urlopen моста) **не останавливает** поток `ThreadingHTTPServer`: rerank/LLM/арбитр крутятся orphan’ом. Внутреннего wall-timeout на `/ask` нет.
3. Цепочка таймаутов сейчас **мост 90 < шлюз 100** — порядок верный (шлюз не режет раньше моста). Race «шлюз ждёт 100, клиент ушёл на 90» = **мост уже отдал отказ на 90**; лишние 10 с — запас шлюза, не дыра. Дыра — **сервер продолжает работу после 90**.

---

## 1. Ранний clarify

### 1.1 Когда становится известно «кандидатов > 1 с подписями»

| Этап | Файл:строка | Что известно | Цена |
|---|---|---|---|
| Разбор | `z20` → `z02:668+` | intent (want/period/kind) | ~5× LLM (~12 с при SAMPLES=5) |
| Отбор буквально/смысл | `z20:2011+`, `2104+` | пул `cands` | SQL + embed |
| Entity-rerank | `z20:2556-2566` | упорядоченный `cands`, уже есть `lab` из `search_tables` | 1× rerank HTTP |
| Wiki-каскад | `z20:2829` → `z21:659` `wiki_primary_entity_cascade` | **единственный** выбор сущности; может сразу `kind=clarify` (`z21:970-989`, reason=`wiki_separability`) или `picked=[leader]` | wiki LLM pick+verify |
| Сборка `arb_pool` / `doubt` | `z20:3252-3404` | `len(arb_pool)>1`, rivals, writer_pair, stop2 | дёшево (SQL/метаданные) |
| Fork A/B/C | `z20:3473-3610` → `z13` | оси прочтения, не типы записей меню продаж | SQL fork |
| **Арбитр ×N** | `z20:3613-3629` | полный под-ответ на каждого из ≤`ARBITER_MAX` | **N× полный цикл** |
| Дешёвый `len(picked)>1` | `z20:3841-3854` | меню из labels | **только если арбитр не бегал** |

Живое меню «Оптовые продажи / Движения… / Реализация ТМЦ» = ветка **entity-clarify** (`clarify_say` + `mk_opts`), не fork B (`kind=figures`). См. W2 §1.2.

**z16** — выбор/вето **меры** (`pick_measure`, `measure_ambiguous`), не меню сущностей.  
**z21** — уже умеет ранний clarify по wiki (`outcome=="clarify"`), но в замере W2 путь был арбитр/ambiguous после полного круга, не этот выход.

### 1.2 Из чего строятся подписи меню (что теряем при раннем выходе)

Код сборки опций: `mk_opts` `z20:1075-1103` + `clarify_say` `z20:326-348`.

Данные для пункта меню:

| Поле | Источник | Нужно ли для читаемого меню |
|---|---|---|
| `label` | `SELECT src_table, label FROM search_tables WHERE src_table IN (…)`; при коллизии — `disambiguate_labels` / `label_with_kind` | **да** |
| `hint` | `opts_hints`: `search_entity_alias.best_used_for`, max `doc_date`, `last_built_at`, coverage gap (`z20:1013-1070`) | желательно, не обязательно |
| `found` | `live_src_counts` — `count(*)` по INDEX/CORPUS с `preds` периода (`z20:1106-1138`) | **нет** для текста меню; для фильтра пустого периода — да (`keep_empty_period_opts`) |
| `decision_id` | `seal_clarify` **после** ответа (`z20:6073-6074` → `z14:409`) | в HTTP-слое, не в `answer()` |

**Не нужны** для меню сущностей: полные агрегаты, compose списка, оси rank, арбитрные `figures`.  
При раннем выходе **теряем** доказательство «числа разошлись / сошлись» (класс A → ответ числом без вопроса; `wiki_clarify_collapsed` `z21:820+`). Это главный риск.

### 1.3 Точка вставки раннего выхода

**Рекомендуемая точка:** `z20_ask_main_http.py` **сразу перед** циклом арбитра `3613`, после финального `sales_canon_force_pool` / `diag["doubt"]` (`3400-3404`) и после попыток `try_entity_form_answer` / event-period (`3408-3427`).

Псевдо-порядок:

```text
# после 3404 / entity_form (~3427), до fork ИЛИ после fork unique/empty, до 3613:
if (len(arb_pool) > 1 and not no_arbiter and not trusted and not focus
    and not diag.get("sales_canon_locked")  # и др. locks
    and not diag.get("wiki_arbiter_locked")
    and _early_entity_clarify_allowed(intent, question, arb_pool, diag)):
    lab_by = SELECT label FROM search_tables …
    opts = mk_opts(arb_pool[:ARBITER_MAX], lab_by, …)  # preds=None → без live counts, ещё дешевле
    return clarify …
```

Альтернатива уже в коде: усилить/доверить **wiki clarify** (`z21:970-989`) — если verify даёт ≥2 tied, меню уходит **до** arbiter×N (префикс intent+search+rerank+wiki LLM всё равно платится).

Перенос «дешёвого» блока `3841-3854` **перед** `3613` (как предлагал W2) — минимальный дифф; условие безопасности ниже обязательно, иначе регресс match (ложный clarify там, где арбитр/fork схлопнул бы в answer).

### 1.4 Когда ранний clarify **запрещён** (условие безопасности)

Не выходить в меню, если ещё можно ответить без догадки (п.21 + п.12):

| Условие | Почему |
|---|---|
| `focus` / `trusted` / `decision_id` | выбор уже сделан |
| `sales_canon_locked` / `catalog_count_locked` / `stock_canon_locked` / `register_count_locked` | канон схлопывает пул (`sales_canon_force_pool` `z11:638`) |
| `wiki_arbiter_locked` / верифицированный wiki-лидер | один судья, соперников не спрашиваем (`z20:3266-3270`) |
| Fork исход A (числа равны) / B (лидер+люк) ещё не посчитан, а вопрос — простой sum/count **без** «и чего / полный отчёт / list» | иначе потеряем ответ числом |
| `writer_pair` в пуле и ещё не доказано расхождение | возможен `writer_pair_proven` без clarify (`z20:3680+`) |
| Односемейные tabpart/шапка без разных атомов | лишний вопрос (коммент `z20:2877+`) |
| Холодный sales-sum, где `prefer_entity_for_sales` уже выбрал один регистр и документы сняты (`z11:236-339`) | автоответ каноном, не меню из 3 |

**Разрешать ранний clarify**, когда:

- составной / отчётный запрос: `want=list` или лексика «и чего» / «полный отчёт» / rank-ось номенклатуры **и** `len(arb_pool)>1` с разными `label`; или
- `len(picked)>1` после wiki/cascade без lock; или
- wiki уже `outcome=clarify` (уже есть).

Для эталонного вопроса владельца («сколько продали вчера **и чего**. полный отчет») ранний clarify **согласован с п.21.2**: ответа с одним смыслом сущности нет, спрашивать до N×отчёта — правильно; «авторазвести по мере/периоду» здесь нельзя — период общий («вчера»), мера у sales-sum канонизируется в деньги (`sales_money_measure`), неоднозначность именно **источника**.

Оценка экономии на классе B: **~130–140 с** (153801→~15–20 с; калибр вызова 3 = 15272). Остаток ≈ intent + search + 1 entity-rerank ± wiki.

---

## 2. Отмена при обрыве

### 2.1 Как устроен сервер

| Слой | Факт |
|---|---|
| Процесс | `serene_ask.py` → зоны; `main()` = `ThreadingHTTPServer` (`z20:6120-6123`) |
| Запрос | `Handler.do_POST` `z20:6021-6112` — **синхронно** в потоке: `answer_checked` → `_send` |
| Async | нет |
| Wall-timeout `/ask` | **нет** |
| rid | `contextvars` `_rid_ctx` (`z01:67-88`); входит в journal |

Мост: `urlopen(..., timeout=ASK_TIMEOUT)` `mcp_ask.py:50,119`. При таймауте сокет клиента закрывается; **серверный поток не получает сигнал** и продолжает `rerank` / `ds_chat` / арбитр (W1: работа после TimeoutError).

`urlopen` внутри rerank (`z07:382`, timeout=30) и LLM (`z01`) — отдельные исходящие вызовы; обрыв **входящего** HTTP на них не влияет.

### 2.2 Можно ли увидеть «клиент ушёл» без переписывания сервера

| Способ | Реализуемость | Комментарий |
|---|---|---|
| Ловить `BrokenPipe`/`ConnectionReset` на `_send` | уже поздно | работа уже сделана |
| Poll `self.connection` (select/peek) между фазами | средне | нужен доступ к socket из `answer()`; сейчас Handler не прокидывает |
| **Cancel-флаг по rid** | **высокая, дешёвая** | `dict[rid]=Event` + проверка в `rerank` / цикле арбитра / `ds_chat` |
| Мост по TimeoutError → `POST /cancel {rid}` (fire-and-forget) | высокая | 10–20 строк в `mcp_ask` + endpoint в Handler |
| **Deadline = ASK_BUDGET_SEC** с старта `do_POST` | **самая дешёвая** | не детектит клиента, но режет orphan после того же бюджета, что мост (90 с) |

Рекомендация без переписывания на async: **(A) deadline по rid + (B) опциональный `/cancel`**. Точки check: `z07:rerank` перед urlopen; `z20:3621` перед каждым sub-`answer`; `z01:ds_chat` / embed. При флаге — `raise`/`return kind=unavailable` с коротким текстом; journal в `finally` `answer_checked` всё равно пишется.

Детект TCP RST без cancel-API возможен, но хрупче (нужен socket в глубокий стек) — вторично.

---

## 3. Хвосты после ответа / после обрыва

### 3.1 После успешного `answer_checked` (нужные)

В `do_POST` `6073-6094`:

| Шаг | Нужен клиенту / контракту |
|---|---|
| `seal_clarify` | **да** — `decision_id` на options |
| `attach_memory_shadow` | да (память) |
| `data_age_sec` + `stale_note` | **да** (п.18 свежесть) |
| `_persist_ask_scope` | только `answer`/`figures` с текстом → таблица `ask_scope` (кнопка дашборда); для clarify — no-op |
| `_send(200)` | ответ |

В `answer_checked` `finally` (`5840-5846`):

| Шаг | Назначение |
|---|---|
| `PV.ensure_partial_visible` | п.13 — partial клиенту |
| `_ask_journal_write` | качество/телеметрия (`ask_journal`) — **нужно даже при ошибке** |

### 3.2 Бесполезное после обрыва клиента

Всё, что крутится **после** того, как мост уже закрыл urlopen:

- оставшиеся `rerank` / arbiter sub-`answer` / OpenRouter tokens;
- дальнейший compose/list/rank-оси (вызов 2 — «полный отчёт»);
- `_persist_ask_scope` / `_send` — клиент не увидит (BrokenPipe на write);
- повторный полный префикс следующего ask, пока orphan держит GPU/CPU (W1 перемешивание TRACE).

**Не выкидывать при cancel:** запись journal (исход `unavailable`/частичный) — иначе слепая зона инцидентов.

---

## 4. Согласование таймаутов

Текущее (CHANGELOG 11.09 (4), замер):

| Слой | Значение |
|---|---|
| mcp-ask `ASK_TIMEOUT` | **90** |
| OpenClaw web `requestTimeoutMs` | **100000** (100 с) |
| serene-ask `/ask` | ∞ (пока не упадёт) |

```text
браузер/агент → gateway(100с) → mcp-ask urlopen(90с) → serene-ask(∞)
```

**Race «шлюз 100 / мост 90»:** на 90 с мост отдаёт `ERROR_REPLY` (русский); шлюз получает ответ инструмента и **не** ждёт до 100. Запас 10 с — нормально. Опасный порядок был бы **шлюз ≤ мост** (шлюз рвёт, мост ещё ждёт serene).

Рекомендации:

1. Держать **gateway ≥ ASK_TIMEOUT + 5…15 с** (сейчас 100 ≥ 90+10 ✓).
2. Ввести **ASK_BUDGET_SEC≈ASK_TIMEOUT** внутри serene-ask — иначе orphan после 90 с.
3. Не поднимать мост выше шлюза без пары.
4. После раннего clarify класс B укладывается в ≪90 с — таймаут остаётся страховкой тяжёлого отчёта после выбора опции (класс C в W4: 25–40 с цель; сейчас часто упирается в потолок).

---

## 5. План правок

| # | Правка | Файл:строка | Экономия | Риск | Приёмка |
|---|---|---|---|---|---|
| **S3-a** | Ранний entity-clarify перед арбитром (с гейтом §1.4) | `z20:3613` (вставка); переиспользовать `mk_opts`/`clarify_say` `:1075`/`:326`; diag `early_entity_clarify=1` | **−130…140 с** на составном → clarify (154→≤20) | ложный clarify вместо answer/figures (L-метрика wrong↑); смягчать гейтом locks/wiki/fork | тот же вопрос: `ask_reply kind=clarify <20000`; замки k4_clarify/fork/intent; L-срез wrong=0 |
| **S3-b** | Не гонять arbiter×N, если уже `len(picked)>1` и составной want | тот же блок; нынешний `:3841` фактически мёртв после арбитра | входит в S3-a | как выше | как выше |
| **S3-c** | `ASK_BUDGET_SEC` + check в `rerank` / arbiter loop | `z01` env; `z07:348+`; `z20:3621`; `answer_checked` t0 | режет orphan после ~90 с (токены/rerank впустую) | обрежет редкий тяжёлый отчёт → обязан `unavailable` по-русски | после TimeoutError моста — нет новых `rerank отработал` с тем rid |
| **S3-d** | `POST /cancel` + флаг по rid из моста при TimeoutError | `mcp_ask.py` except; `z20` Handler | точная отмена, не только deadline | лишний endpoint; нужен rid end-to-end (уже в payload) | journal: cancel; CPU/GPU idle |
| **S3-e** | Документировать цепочку 90/100 в RUNBOOK / openclaw web | docs + env comments | 0 с | путаница при ручном тюнинге | — |

**Не в этом пакете (соседние линзы):** S1 rerank ≤5; S2 INTENT_SAMPLES — дают ещё −30…90 с и −10 с на префиксе; усиливают S3-a.

**Порядок внедрения:** S3-c (дешёвый стоп orphan) → S3-a/b (ранний clarify, армия замков) → S3-d (если deadline мало) → S3-e.

**Связь с TARGET:** п.21 (уточнение при неоднозначности) — S3-a усиливает; п.12 (не угадывать сущность) — то же; п.10 — любой ранний выход только с прогоном wrong=0; п.18 — отказ по таймауту уже русский на мосте, сервер должен молчать работой, не только текстом.

---

## След кода (кратко)

```text
POST /ask (ThreadingHTTPServer)
  answer_checked          z20:5758  (journal finally)
    answer                z20:1808
      parse/search/rerank z20:1907…2566
      wiki_cascade        z20:2829 → z21:659  [может clarify]
      arb_pool/doubt      z20:3252…3404
      fork A/B/C          z20:3473
      ★ arbiter×N         z20:3613          ← сюда early-exit
      len(picked)>1       z20:3841          ← сейчас «дешёвый», но поздно
  seal_clarify            z14:409
  stale + ask_scope + _send
```

Мост: `ASK_TIMEOUT` → urlopen; при обрыве serene **не** узнаёт — пока нет cancel/deadline.
