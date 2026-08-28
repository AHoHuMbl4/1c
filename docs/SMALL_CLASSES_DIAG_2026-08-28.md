# Диагностика трёх малых классов (28.08.2026)

**Статус:** только диагноз и план фикса. Код не менялся (параллельная сессия правит `serene_ask.py`).

**Трассы:** `.claude/state/k6traces/` — кандидат `:8096`, полный набор флагов Ф6 + K6b, код `e239e62`.

**Мерило:** [`PLAN_ANSWER_CONTRACT.md`](PLAN_ANSWER_CONTRACT.md), [`K6_ENTITY_RANK.md`](K6_ENTITY_RANK.md) §7.10–7.11, п. 17 [`TARGET.md`](../TARGET.md).

---

## 1. §10 — «как у нас дела?»

### Трасса (`s10-delа.txt`)

| Поле | Значение |
|---|---|
| `kind` | `figures` |
| `text` | только приписка свежести (пустой ответ + `stale_note`) |
| `diag.about` | `coverage` |
| `diag.claims` | `total=423234`, `count=15` |
| `gate_rejected` | `count: заявлено 15, в базе 0` |
| `figures` | перепись: `rows_missing=423234`, `entities_missing=0` |

Журнал скачет `no_data` ↔ `figures`: нестабилен **разбор** (`about`), не счёт.

### Почему так

**Ветка A — `no_data`:** модель ставит `about=data` (или поле пустое → default `data`). Дальше `question_expects_accounting_data` (`serene_ask.py:8429–8456`) для `want=list` без `kind`, `terms`, `measure` и без маркеров «сколько/продаж/…» возвращает `False` → ранний `no_data` с `reason=non_accounting_question` (`12787–12792`).

**Ветка B — `figures` (трасса):** модель ставит `about=coverage`. Ранний выход в `_coverage_answer` (`12743–12753`, `11440–11524`):

1. Модель формулирует ответ по переписи (`COVERAGE_SYS`, `ds_chat`).
2. `check_claims` сверяет `claims` с `agg={"sum": n_lost, "count": ent_lost}` (`11484–11485`).
3. Модель пишет `count=15` (число строк в census = `COVERAGE_TOP`, env `ASK_COVERAGE_TOP=15`, строка `111`), а `ent_lost=0` → гейт падает.
4. Fallback при провале гейта (`11508–11518`): `kind=figures`, **`text=""`**, цифры только в `figures` — «мусорные figures» без человеческого ответа.

`serene_enough.verdict_before` (`serene_enough.py:174–198`) **не** ловит вопрос: требует `want in (sum, count)` или `measure`; при `want=list` и пустых координатах clarify не вызывается (`16293–16305`). Путь `about=coverage` обходит и `verdict_before` (`about != "data"` → `(False, [], "")`).

### Правильный исход по контракту

**`clarify`** (слоты: род записей / величина / период — что спросить). Вопрос не называет ни сущность, ни меру, ни окно; это не вопрос о переписи системы (п. 12, п. 21 — отказ при наличии данных не нужен, но и выдуманный ответ недопустим). Перепись (`about=coverage`) здесь — **ошибочная интерпретация** разбора, не контрактный ответ.

`no_data` допустим только как худший из двух нестабильных веток; целевой — уточнение до счёта.

### Предлагаемый фикс (класс, не под фразу)

| # | Место | Что сделать |
|---|---|---|
| 1 | `serene_enough.verdict_before` (`serene_enough.py:189–198`) | Расширить: `want=list` без `kind`/`terms`/`measure` и без явного `about=coverage` → clarify «что именно: продажи, остатки, полнота загрузки…». Не хардкод «дела» — проверка на **отсутствие координат**. |
| 2 | `answer()` до `about=coverage` (`12743–12753`) | Страж: `about=coverage` только если в вопросе есть опора в словаре относительных форм **или** детектор фраз полноты из `period_relative_forms`/meta (аналог `period_form_from_question`, но для coverage-лексики) — иначе сброс `about→data` и п.1. |
| 3 | `_coverage_answer` fallback (`11508–11518`) | При провале гейта собирать **детерминированный** `text` из census (как `format_period_empty_text`), не пустой `figures`. Класс «coverage gate fallback», не «как у нас дела». |

### Риск регрессии

- П.1: легитимные `want=list` с явным `kind` («топ клиентов») не должны попадать — условие «нет kind И нет terms».
- П.2: не сломать живые вопросы «всё ли загрузилось» — только явная coverage-лексика.
- П.3: только ветка coverage; основной гейт не трогать.

### Проверка

| Прибор | Ожидание |
|---|---|
| `test_enough.py` | новые кейсы: bare `want=list` → `verdict_before=True` |
| Живой / AB_PROBE | «как у нас дела?» → `kind=clarify`, не `figures`/`no_data` |
| `test_check_deploy_gate.py` (уже есть фраза) | зафиксировать исход после фикса |
| Контур-24 | строка §10 из 20/24 → pass |

---

## 2. §7.10 — «продажи позавчера» на пустом окне

### Трасса (`s710-pozavchera.txt`) — сегодня OK

`kind=answer`, `period_empty`, окно `2026-08-26 assumed`, TRACE: `канон продаж: period_window_empty → period_empty`. На кандидате с K6b путь **иногда** работает.

### Замер K6 §7.10 (регрессия)

При **одинаково пустых** днях «вчера» → честный `period_empty`, «позавчера» → паспорт-мусор (`00,08,1,107468,2026,25,252026…`), `want=0`.

### Почему так

**Ранний выход `period_empty`** завязан на цепочку:

1. `empty_after_period_action` (`11827–11842`) → `drop_assumed`, только если в `intent.period` есть `from`/`to` **и** `parse.assumed` содержит `period.*` (`serene_enough.period_assumed`, `serene_enough.py:162–171`).
2. Проба пустого окна (`14754–14763`): `rows_of(..., 1)==0` → `period_window_empty` → `try_sales_fork_period_empty_answer` → `build_period_empty_answer`.
3. Поздний выход (`15486–15489`, `15728–15732`): `sales_period_empty` + `build_period_empty_answer`.

**Асимметрия «вчера» / «позавчера»:** словарь `period_relative_forms` в репозитории (`work/acceptance/period_relative_forms.json`) содержит `yesterday` и `day_before`, но **код** использует `period_form_from_question` (`1770–1780`) в `apply_period_leader` (`1783–1819`) **только** для `prev_week` (строки `1793–1806`, флаг `ASK_SALES_RANK_CANON`). Формы `day_before`/`yesterday` **не** превращаются в ISO-даты кодом — только разбор модели.

Если модель для «позавчера»:

- не заполняет `period.from/to`, или
- заполняет без `parse.assumed`,

то `empty_after_period_action` → `no_data` (`11842`), проба `14754` **не срабатывает**, периодный фильтр снимается/не ставится → агрегат **all-time** → `compose` → гейт отклоняет прозу → fallback `kind=figures` (`15715–15761`) с `atom_terminal_gate_text` / незаполненными слотами → **паспорт-мусор** в `text` (`build_answer_passport` `15605–15618`, `ensure_answer_passport` `9856–9865`).

На трассе сегодня модель дала период + assumed — поэтому `period_empty` сработал.

### Правильный исход

`kind=answer` с `period_empty` / нулём за день (как «вчера»), не `figures` с мусором.

### Предлагаемый фикс (класс)

| # | Место | Что сделать |
|---|---|---|
| 1 | `apply_period_leader` или новый хук сразу после `parse_intent` (`12728+`) | Для **всех** `form_id` из `period_relative_forms` с однодневными окнами (`yesterday`, `day_before`, `today`) — детерминированно выставить `intent.period` (ISO от `today`) и `parse.assumed`, по тому же принципу, что `prev_week` (`1798–1806`). Источник фраз — `search_meta` / файл, не литералы в коде. |
| 2 | `14754–14763` | Запасной триггер: если `period_form_from_question(q)` ∈ {`yesterday`,`day_before`,`today`} и `sales_sum_intent` — форсировать пробу окна даже при неполном разборе модели. |
| 3 | Fallback гейта (`15725–15761`) | Если `sales_period_empty` / `period_window_empty` — не отдавать `figures` с паспортом; только `build_period_empty_answer`. Класс «gate fallback respects empty window». |

**Данные:** доставить полный `period_relative_forms.json` в `search_meta` (сейчас в бою **1 форма**, `prev_week` — `TARGET_STATUS`, Д4); без `day_before` в meta код из п.1 не увидит «позавчера».

### Риск регрессии

- П.1: не перетирать явный `period` из вопроса (`period_given`); только при `parse.assumed` или пустом периоде + совпадении фразы.
- П.3: rank/compare с пустым окном — проверить `test_period_empty.py`, `test_compare_sales.py`.

### Проверка

| Прибор | Ожидание |
|---|---|
| `test_period_empty.py` | уже есть «позавчера» (`89–152`); добавить `want=list`, «продажи позавчера» без period в intent |
| Живой okna | «сколько продали вчера?» / «позавчера?» при пустых днях — оба `period_empty`, без all-time в text |
| Контур-24 | стабильность пары вчера/позавчера |

---

## 3. Свежесть — «⚠ Данные могли устареть… 5648 мин»

### Наблюдение (все три трассы)

`data_age_sec=338894` ≈ **5648 мин**; приписка из `STALE_TEXT` (`325–327`).

### От чего считается

**Источник приписки в `/ask` — последний успешный такт сборки корпуса, не meta Windows и не витрина напрямую.**

```16672:16682:ubuntu/serenedb/serene_ask.py
r = psql("SELECT round(epoch(now()) - v) FROM search_quality WHERE k='build_ts'")
...
out.setdefault("diag", {})["data_age_sec"] = age
out = stale_note(out, age, STALE_WARN_SEC, STALE_TEXT)
```

| Слой | Ключ / метрика | Где используется |
|---|---|---|
| Возраст в ответе `/ask` | `search_quality.build_ts` → `data_age_sec` | каждый ответ, порог `ASK_STALE_WARN_SEC` (умолч. 3600 с) |
| Лаг пайплайна | `mart_changed_ts > build_ts` → `merge_pending_sec` | `_coverage_of` (`11174–11176`), `/health` `_classify_health_gap` (`11305–11308`) |
| Native индекс | `sdb_metrics`: `num_buffered_docs`, `refresh_pending`, … | только `/health` при `ASK_HEALTH_NATIVE_FRESHNESS=1` (`11326+`, `16569+`) |

**5648 мин** = корпус не пересобирался ~3,9 сут (`build_ts` старый). Это согласуется с внешним блокером Д5 (meta/`--smoke` на Windows): такт не бежит → `build_ts` не обновляется → приписка честная.

`ASK_HEALTH_NATIVE_FRESHNESS` **в бою включён** (В2, 28.08) для `/health`, но **не** подключён к `stale_note` в `/ask` — ответы не читают `num_buffered_docs`.

### Что нужно для п. 17 TARGET (без правки сейчас)

1. **Разблокировать такт:** Windows-агент ≥1.1.3, `--smoke`, meta → обновление `build_ts` / слияние витрины с корпусом (владелец, Д5).
2. **Данные:** полный `period_relative_forms` и регулярный `mart_changed_ts` — косвенно, через живой такт.
3. **Опционально (код позже):** второй рубеж `stale_note` — `merge_pending_sec` или native `num_buffered_docs` при `ASK_HEALTH_NATIVE_FRESHNESS=1` (фактура [`F6_FRESHNESS_FACTS.md`](F6_FRESHNESS_FACTS.md) §2: слои разные; на sandbox 137 с vs buffered=0).
4. **Не путать:** приписка ≠ `freshness_lag` в эталонах (`client-gold-okna.tsv`, `freshness_lag` — ожидаемая метка при лаге, не баг класса).

### Проверка

| Прибор | Ожидание |
|---|---|
| `SELECT v, round(epoch(now())-v)/60 FROM search_quality WHERE k='build_ts'` | минуты ≈ приписке |
| `/health` с `ASK_HEALTH_NATIVE_FRESHNESS=1` | `freshness.merge_pending_sec` + native поля |
| После успешного такта | `data_age_sec` < `STALE_WARN_SEC`, приписка исчезает |

---

## Сводка

| Класс | Файл:строка (корень) | Причина | Фикс-класс | Замок |
|---|---|---|---|---|
| §10 «как у нас дела?» | `12743–12753`, `11508–11518`, `8429–8456` | Нестабильный `about=coverage` vs `non_accounting`; нет clarify для bare `want=list`; пустой coverage fallback | `verdict_before` для безкоординатных list; страж `about=coverage`; текст из census при gate fail | `test_enough`, контур §10 |
| §7.10 позавчера | `14754–14763`, `1770–1806`, `15725–15761` | `day_before` не резолвится кодом; проба окна только при `drop_assumed`; gate fallback → figures+паспорт | Резолв однодневных form_id из `period_relative_forms`; запасная проба; gate fallback → period_empty | `test_period_empty`, вчера/позавчера live |
| Свежесть 5648 мин | `16672–16682`, `11164–11176` | `build_ts` старше порога; не meta Windows | Такт сборки (внешний); опционально native/merge в `stale_note` | `build_ts` SQL, `/health` |

---

## Связанные находки

- `HOW_IT_WORKS.md` §8: у coverage указано, что `gate()` не вызывается — **устарело** относительно кода: `gate()` добавлен (`11401–11507`), но fallback при провале остаётся пустым `figures`.
- `period_relative_forms.json` в `ubuntu/serenedb/` содержит только `prev_week`; полный словарь в `work/acceptance/period_relative_forms.json` — для такта 1-period, в meta пока 1 форма.
- Класс «молодец»-ранг (§7.11) и K6-двойка — вне этого документа; трассы `slang-molodets.txt`, `k6-dead.txt` не разбирались.
