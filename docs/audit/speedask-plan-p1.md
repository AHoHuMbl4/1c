# P1

Аудит плана Speed-Ask v1 — пункты **A** (ранний clarify) и **B** (deadline).  
Режим: только чтение. Дата: 11.09.2026.  
Объект: `docs/audit/SPEED_ASK_PLAN_2026-09-11.md` §0, §1.A, §1.B, §2, §3.  
Код: `z20_ask_main_http.py`, `z07_rrf_vectors.py`, `z02_intent.py`, `z01_infra_trace_llm.py`, `serene_ask.py`, `mcp_ask.py`.

---

## Сверка

### С предшественником `speed-s3.md` — **не дословно**

План сжимает S3-a/S3-c, но **размывает** обязательные находки:

| S3 (дословно / таблица) | План v1 | Статус |
|---|---|---|
| Точка: сразу перед `3613`, после force/doubt **и** после `entity_form`/`event-period` (`3408–3427`); fork A/B — до вставки или уже отработал | «после locks/doubt (`:3404`)» → перед арбитром | **сжато опасно**: между `3404` и `3613` ещё entity_form + fork |
| Запреты: `focus`/`trusted`/`decision_id`; `sales/catalog/stock/register_*_locked`; `wiki_arbiter_locked`; fork A/B; `writer_pair`; односемейные tabpart; cold `prefer_entity_for_sales` | 5 пунктов: sales_canon; wiki; fork A/B; writer_pair; doubt | **неполный** |
| Условие **разрешения**: `want=list` / «и чего» / полный отчёт / rank-ось | только запреты (fail-closed) | **потеряно allow-условие** |
| Имя `ASK_BUDGET_SEC`; порядок **S3-c → S3-a** | `ASK_DEADLINE_SEC`; порядок **A → B** | переименовано; порядок **перевёрнут** |
| `mk_opts`/`clarify_say`; diag `early_entity_clarify=1`; опционально `preds=None` | «те же подписи… mk_opts»; diag в §E | частично; `preds=None` vs «те же» — **конфликт** |
| Чек: `rerank` + arbiter + рекомендация `ds_chat`/embed | только rerank + цикл арбитра | **урезано** |
| S3-d `/cancel`, S3-e docs 90/100 | нет (скоуп) | ок как вне пакета, но цепочка таймаутов в плане не зафиксирована |
| «русский» на мосте = env `MCP_ERROR_REPLY` (CHANGELOG 11.09) | «русский уже есть через MCP_ERROR_REPLY» | верно для **прод-env**; дефолт в коде `mcp_ask.py:132–133` — EN-инструкция модели |

### 1. Точка вставки A перед `:3613`

**Исполнима без перестройки потока**, если вставка — **буквально перед** `if len(arb_pool) > 1 and not no_arbiter:` (`z20:3613`), а не «сразу после `3404`».

Что уже прошло до `3613` (пропускать нельзя):

| Блок | Строки | Зачем |
|---|---|---|
| locks / `doubt` / `arb_pool` / writer_pair / stop2 / force_pool | `3252–3404` | каноны схлопывают пул; `diag["doubt"]` |
| `try_event_count_period_clarify` / `try_entity_form_answer` | `3408–3427` | могут **вернуть ответ** до арбитра |
| Fork A/B/C/unique/empty/unavailable | `3473–3610` | A/B → число/люк **без** меню; C → clarify; unique → ответ |
| Только потом арбитр ×N | `3613–3629` | полный `answer(focus=c)` |

Псевдо «после `:3404`» из плана, прочитанное буквально, **ломает** entity_form и fork. Правильная формулировка S3: после `3427` **и** после исходов fork, которые уже `return`, — то есть **на строке 3613**.

Условие плана `len(picked)>1` **не совпадает** с гейтом арбитра `len(arb_pool)>1` (`3613`). После doubt/stop2 `arb_pool` часто шире `picked`; дешёвый хвост `3841` смотрит `picked`. Ранний выход обязан ориентироваться на **`arb_pool`** (и тот же срез `[:ARBITER_MAX]`), иначе мимо живого пути.

### 2. Запреты раннего выхода — список плана **неполон**

План: `sales_canon_locked`; wiki-лидер; fork A/B; writer_pair; doubt.

По коду до/на гейте арбитра дополнительно **обязательны** (уже используются как гасители круга):

| Условие | Где в коде | Почему |
|---|---|---|
| `no_arbiter` / `trusted` (`decision_id`) | `3613`, `guards_skip_for_choice` | выбор уже доказан |
| сырой `focus` не гасит защиту | коммент `1813`, `6042` | не путать с trusted |
| `catalog_count_locked` / `stock_canon_locked` / `register_count_locked` | `3298–3300`, `3400–3402`, `_checked` | тот же `sales_canon_force_pool` |
| `wiki_arbiter_locked` (verify == pick) | `3266–3270`, `3473–3480` | doubt снят, fork/стоп2 гасятся |
| fork уже вернул A/B/C/unavailable | `3573–3610` | на точке `3613` «ещё возможен» — только если fork **не** гоняли |
| `writer_pair` без `writer_pair_proven` | `3680–3717` | арбитр может **ответить без меню** |
| односемейные tabpart/шапка (`parent`) | `2877–2887`, фильтр `_family` в круге | лишний вопрос при одном прочтении |
| cold/locked sales: `prefer_entity_for_sales` + `sales_canon_locked` | `z11:236+`, force_pool | автоответ каноном, не меню из 3 |
| уже ушли wiki `outcome=clarify` | `z21:970–989` | другой ранний путь; не дублировать логику гейта |

**«Безопасное меню» vs «нужен арбитр»** (проверка кодом, не догадка):

- Арбитр нужен, когда ещё можно **схлопнуть в ответ без человека**: числа сошлись (`answers_diverge` ложь → путь `3770–3782`), `writer_pair_proven`, sole cand_ans + не rival, mute computed → ответ (`3760–3765`).
- Меню безопасно, когда неоднозначность **источника** уже зафиксирована данными и **не** лечится каноном/wiki/fork A/B — типично составной/list («и чего»), `len(arb_pool)>1`, разные labels после `mk_opts`.
- **Measure-неоднозначность внутри одной сущности** (`measure_ambiguous` / `z16`, ветка после выбора `src`, ~`4327`) — **другой слой**. Она не открывает entity-меню на `3613` и **не заменяется** ранним entity-clarify. Гейт A про источники, не про меры. Отдельный запрет «measure ambiguous» на точке A **не требуется**; путать слои — дефект плана.

Не хватает в плане явного запрета: **«не ранний clarify, если при полном круге арбитр имел бы единственный исход»** (числа/sole/`writer_pair_proven`) — см. атаки.

### 3. Подписи меню

Полный путь clarify (`3841–3854` и ветки арбитра `3749+`):

```text
lab_by ← search_tables.label
opts  ← mk_opts(..., marks, by, match, preds=preds)  # live_src_counts при preds
text  ← clarify_say → format_clarify_options → label + hint (found в текст НЕ идёт)
```

`mk_opts` (`1075–1103`): всегда `opts_hints` (alias / max date / last_built / coverage); `found` = live counts или `by`.

Клиент/модель:

- Текст меню: **label + hint** (`clarify_choice_line`).
- JSON options в мост: `_OPT_PUBLIC` включает **`found`** (`mcp_ask.py:255`).

Если ранний путь сделает `preds=None` (как допускал S3 «дешевле») — **`found` в options разойдётся** с полным путём → модель видит разные OPTIONS; fingerprint pending **не** включает `found`, но контракт плана «клиент не видит разницы» **нарушен** для публичных options.

**Вердикт по подписям:** тот же `mk_opts` + те же `preds`/`marks`/`match` + тот же пул (`arb_pool[:ARBITER_MAX]`), иначе дефект. Текст label/hint совпадёт при тех же src; `found` — только при тех же `preds`.

`seal_clarify` (`do_POST:6073–6074` → `z14:409`) — **после** возврата из `answer_checked`; ранний return `kind=clarify` с `options` идёт тем же путём. A сам по себе билеты не ломает.

### 4. B (deadline)

| Вопрос | Факт по коду |
|---|---|
| Сервер | `ThreadingHTTPServer` + синхронный `do_POST` (`6120`, `6021–6094`); async нет |
| Старт часов | план: приём POST — ок; `t0` уже есть в `answer_checked` (`5774`) |
| Чек только `rerank` (`z07:348`) + цикл арбитра (`3621`) | **не покрывает** долгие пути без rerank: `ds_chat` / intent samples (`z02`/`z01`), wiki pick+verify (`z21`), compose (`z18`), fork_detector_scan SQL (`3487–3540`), embed в поиске. `resolve_values` зовёт `rerank` (`z07:559`) — **покрыт на входе в rerank**, не на SQL/embed до него |
| `88 < 90` | запас на отправку ответа; **не** спасает от гонки **внутри** уже начатого `urlopen(..., timeout=30)` в rerank или `ds_chat` (timeout до 120 на embed-пути): чек на **входе**, обрыв mid-call нет → orphan до конца HTTP |
| Медленный первый rerank | старт в t=70, deadline 88, urlopen 30с → конец ~100 > мост 90; `88` не помогает без cancel mid-call или чека **перед каждым** исходящим вызовом |
| Memo / билеты / quality — граница фазы | **INTENT_MEMO**: пишется атомарно в конце успешного `parse_intent` (`z02:682–685`) после всех samples — фаза = «intent завершён». Обрыв mid-sample → memo нет (верно). **Билеты**: `seal_clarify` только после возврата clarify в `do_POST` — фаза = «answer вернул options». **Journal**: `answer_checked` `finally` — даже на ошибке. План обязан запретить запись memo от **частичных** samples и seal при `unavailable` |

Русский `unavailable` на serene-ask: тексты в `do_POST` except (`6105–6110`) и fork (`3605–3607`). Мост при timeout — `ERROR_REPLY` (прод: русский из env). План путает слои: deadline должен отдавать **свой** русский `kind=unavailable` из ask, не полагаться на MCP_ERROR_REPLY (тот срабатывает, когда мост **уже** оборвал urlopen).

---

## Атаки (≥4)

1. **Раннее меню там, где арбитр схлопнул бы в ответ.**  
   `len(arb_pool)>1`, но числа совпадут / `writer_pair_proven` / sole → `answer`/`figures`. План запрещает «writer_pair не проверен» и «doubt», но **не** запрещает явно исход «арбитр имел бы единственный ответ». Нужен запрет или allow только на доказанной неоднозначности источника (составной/list + разные atoms) — иначе L wrong↑ / п.21 (отказ от ответа при данных).

2. **Deadline обрывает «пишущийся» INTENT_MEMO.**  
   Сейчас запись одна, после merge — гонки записи нет. Риск внедрения: чек внутри цикла samples + запись memo от урезанного набора → нестабильный intent. План «не рвать фазу» верен; дописать: **memo только после полного `_merge_intents`; при abort mid-intent — не писать**.

3. **A ломает замки intent/compose?**  
   A не трогает `parse_intent`/compose-код. Риск — **поведенческий**: clarify раньше → другие `kind`/timing на замках k4_clarify/fork/intent; fork A/B, если вставка до fork, — регресс замков fork. При вставке строго на `3613` после fork — замки fork целы; intent/compose — нужны до/после прогоны §0.1.

4. **B отдаёт `unavailable`, пока «clarify в полёте».**  
   Один поток на запрос: либо `answer` ещё не вернул, либо уже вернул. Опасная реализация — обернуть **весь** `do_POST` дедлайном **после** `answer_checked` (между clarify и `seal_clarify`/`_send`) → клиент вместо меню получит отказ. Чек-пойнты только внутри `answer`/rerank/арбитр; **после** успешного return clarify дедлайн не переписывает исход. Связка A+B: ранний clarify ~15с << 88 — конфликта нет; конфликт только если A запрещён и крутится полный путь до 88.

5. **(доп.) Чекпойнты без `ds_chat`:** orphan/токены после обрыва моста на intent/wiki/compose — дыра S3, план её сузил; 88≠закрытие orphan.

6. **(доп.) `len(picked)>1` вместо `arb_pool`:** ранний путь молчит, арбитр×N всё равно бежит (или наоборот — меню на пуле rivals при `picked==1` без allow) — рассинхрон с `3613`.

---

## Вердикт

**A и B к внедрению как в плане v1 — не готовы.** Идея S3 верна и точка `3613` исполнимо; текст плана **недоопределён** (точка, запреты, пул, подписи/`found`, покрытие deadline, порядок A↔B). Сначала правки плана, потом код.

### Правки плана (дословно внести)

1. **Точка A:** «вставка **непосредственно перед** `z20:3613` (`len(arb_pool)>1 and not no_arbiter`), **после** `entity_form`/`event-period` (`3408–3427`) и после ветки fork, которая уже сделала `return` на A/B/C/unavailable/unique. Не после `:3404`.»

2. **Условие пула:** `len(arb_pool)>1` (не `len(picked)>1`); меню из `arb_pool[:ARBITER_MAX]`; тот же `mk_opts(..., match=match, preds=preds)` что у `3848`/`3749` — **`preds=None` запрещён**, пока контракт «те же options».

3. **Запреты A (полный список):** `no_arbiter`; `trusted`/`decision_id`; `sales_canon_locked` **и** `catalog_count_locked` / `stock_canon_locked` / `register_count_locked`; `wiki_arbiter_locked` (или verify==pick); односемейный tabpart/шапка без разных атомов; cold/locked sales-canon уже выбрал один регистр; `writer_pair` без доказанного расхождения чисел; fork-исход A/B ещё не вычислен **если** вставка когда-либо раньше fork (при вставке на `3613` — N/A); плюс **запрет**, если полный круг арбитра дал бы единственный `answer`/`figures` (числа сошлись / proven / sole).

4. **Allow A (вернуть из S3):** составной/отчётный (`want=list` или лексика полного отчёта / rank-ось) **или** уже доказанная неоднозначность источника без lock; иначе прежний путь.

5. **Measure:** явно: «ранний entity-clarify **не** закрывает `measure_ambiguous` внутри одной сущности — слой z16 после выбора src.»

6. **B чек-пойнты:** кроме `rerank` входа и цикла арбитра — **вход в `ds_chat`** (`z01`) и перед каждым sub-`answer` (уже цикл); желательно перед `fork_detector_scan`. Зафиксировать: mid-`urlopen` не отменяется; `88` — запас до моста 90, **не** гарантия обрыва mid-call.

7. **B текст отказа:** русский `kind=unavailable` **из serene-ask** (как `6105–6110` / аналог); не ссылаться на `MCP_ERROR_REPLY` как на текст ответа ask.

8. **Фазы «не рвать»:** INTENT_MEMO — только после полного `parse_intent`; билеты — только `seal_clarify` после успешного clarify-return; journal — `finally` всегда; abort → memo/билеты не писать.

9. **Порядок внедрения:** вернуть рекомендацию S3 **B (deadline) → A (early clarify)** *или* явно обосновать A→B (сейчас противоречие S3 без аргумента).

10. **§0 / diag:** `early_clarify_path` + замер: тот же вопрос → `kind=clarify`, options fingerprint (label/hint/src) ≡ контрольному полному clarify; L67 wrong=0 на ослаблении A отдельно до общего прогона.

11. **Имя env:** либо `ASK_DEADLINE_SEC`, либо сохранить `ASK_BUDGET_SEC` из S3 — одно имя + «дефолт < ASK_TIMEOUT моста»; инвариант `DEADLINE < ASK_TIMEOUT` в комментарии env.

---

Конец P1.
