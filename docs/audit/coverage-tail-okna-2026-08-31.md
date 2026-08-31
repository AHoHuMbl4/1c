# Coverage-хвост okna: 15 строк / 5 сущностей (2026-08-31)

Окно: `gpu-erw` / LXC okna. DSN: `host=127.0.0.1 port=7890`. Только SELECT (+ временные diag-таблицы сняты). Метки UTC как на сервере.

## Контекст

| | |
|---|---|
| `/health` | `degraded` ← `coverage_gap` 5 сущностей / 15 строк |
| Такт | зелёный `build_ts` = **2026-08-30 16:37:05 UTC** (236 с) |
| Витрина | `mart_changed_ts` = **2026-08-29 15:01:44 UTC** |
| Лаг? | **нет**: build новее mart → не `freshness_lag` |

Перепись на момент замера:

| src | объектов_витрины (coverage) | в_корпусе | health gap |
|---|---:|---:|---:|
| catalog_договоры | 713 | 704 | 9 |
| catalog_валюты | 8 | 6 | 2 |
| catalog_контрагенты | 367 | 365 | 2 |
| catalog_расходыопердеятельности | 93 | 92 | 1 |
| document_приходныйкассовыйордер | 3423 | 3422 | 1 |
| **итого** | | | **15** |

## Корневая причина (общая)

### 1. Ложный счётчик объектов в выкате coverage (главное)

На okna в `/opt/1c-mcp-reports/coverage_build.sql`:

```sql
PREPARE p_cov_obj AS INSERT INTO cov_mart_obj
       SELECT $1::VARCHAR, count(*) FROM query_table($1);
       -- okna-pcov-hotfix: Ref_Key mismatch in vitrine
```

То есть «объектов витрины» = **число строк**, не `count(DISTINCT ref_key)`.

В репозитории (`ubuntu/serenedb/coverage_build.sql`) задумано `count(DISTINCT "<физическая ref_key>")`. Хотфикс обошёл case-mismatch метаданных/`Ref_Key` vs витрины/`ref_key`, ценой ложных дыр.

### 2. Пустые `ref_key` в витрине

Во всех пяти таблицах есть строки с `ref_key = ''` (и обычно пустыми прочими полями) — мусор транспорта/разворота, не бизнес-объекты.

| src | rows | empty_key | dist_nonempty | corp | corp − nonempty |
|---|---:|---:|---:|---:|---:|
| catalog_договоры | 713 | 12 | 701 | 704 | +3 |
| catalog_валюты | 8 | 4 | 4 | 6 | +2 |
| catalog_контрагенты | 367 | 12 | 355 | 365 | +10 |
| catalog_расходыопердеятельности | 93 | 1 | 92 | 92 | 0 |
| document_приходныйкассовыйордер | 3423 | 16 | 3407 | 3422 | +15 |

**Ни у одной сущности корпус не меньше числа непустых ключей.** Health «недостача» — следствие `count(*)` + empty rows. По живым объектам корпус ≥ витрины (часто есть **сироты** корпуса).

### 3. Case `Ref_Key` vs `ref_key` в сборке корпуса (смежный дефект)

- `$metadata` / `tmp3_key.key_cols` = `{Ref_Key}`
- физическая колонка витрины = `ref_key`
- `list_position(['Ref_Key'], 'ref_key')` → NULL → `row_key` падает в `sha1(doc)`  
  [замер] у всех 5 сущностей **0 GUID-ключей, 100% sha1** в `search_corpus`
- join метаданных к колонкам по имени без `lower()` → platform-колонки часто `kind='skip'`

Это **не** объясняет health gap 15 как «потерянные живые строки», но ломает тождество ключа, анти-join по GUID и чистку сирот. Фильтры `resolver_build.sql` (`^\{`, substr 20000) к этому хвосту **не относятся** (резолвер ≠ корпус).

---

## По сущностям

### catalog_договоры — потеря health 9

| | |
|---|---|
| Вердикт | **ложная тревога coverage** (не дефект merge живых строк) |
| Доказательство | empty_key=12; dist_nonempty=701; corp=704 (+3 к nonempty). Все 701 nonempty находятся в корпусе (по GUID в `doc` / совпадению содержания). |
| SQL | см. блок «Сводка» ниже; `count(*) FILTER (WHERE coalesce(ref_key,'')='')` → 12 |
| Что «недосчитано» health | 9 из 12 пустых строк витрины, которых в корпусе нет как отдельных объектов (и не должно) |
| Чинить gap? | coverage: вернуть DISTINCT; корпус: case ключа (сироты +3 отдельно) |

### catalog_валюты — потеря health 2

| | |
|---|---|
| Вердикт | **ложная тревога** + **2 сироты корпуса** (лишние, не недостача) |
| Витрина | 4 nonempty (MDL/EUR/EUR com 2/USD) + 4 empty |
| Корпус | 6 строк: 4 текущих + 2 GUID'а, которых нет в витрине (`8a996167-…` EUR energbank, `fcecf2cb-…` Евро ком.) — видны в `…navigationLinkUrl…guid'…'` |
| Все 4 живых | `in_corp_by_guid = true` |
| Лаг | нет (`build_ts` > `mart_changed_ts`) |
| Чинить | coverage DISTINCT; после починки ключа — пересборка/delete сирот |

### catalog_контрагенты — потеря health 2

| | |
|---|---|
| Вердикт | **ложная тревога coverage** |
| empty_key | 12 |
| nonempty | 355 (в т.ч. 4 папки `IsFolder`); corp=365 |
| Папки Покупатели / Поставщики / Ministerul Finantelor | **есть** собственные строки корпуса (`контрагенты \| ref_key: Покупатели / …` и т.д.); ложный «missing» был только у anti-join по GUID в `doc` (GUID в текст не попадает из‑за refmap + case) |
| Чинить | coverage; case ключа (сироты +10) |

### catalog_расходыопердеятельности — потеря health 1

| | |
|---|---|
| Вердикт | **фильтр/учёт — норм для корпуса; дефект — в coverage** |
| empty_key | **1** строка: все поля пустые |
| dist_nonempty | 92 = corp 92 |
| Критерий | пустой `ref_key` / пустой объект → в корпус отдельной карточкой не ложится (нечего индексировать). Health считает её объектом из‑за `count(*)`. |
| Доказательство | одна пустая строка в витрине; `объектов_витрины−в_корпусе = 1` |

### document_приходныйкассовыйордер — потеря health 1

| | |
|---|---|
| Вердикт | **ложная тревога coverage** |
| empty_key | 16; dist_nonempty=3407; corp=3422 (+15) |
| Nonempty anti-join по GUID в doc | missing_live = **0** |
| Health gap 1 | артефакт `count(*)` на фоне 16 пустых ключей и лишних corp-строк |

---

## Сводка доказательств (SQL + результат)

```sql
-- 1) Health vs живые ключи (результат — таблица выше)
SELECT count(*), count(*) FILTER (WHERE coalesce(ref_key,'')='') AS empty_key,
       count(DISTINCT NULLIF(ref_key,'')) AS dist_nonempty
FROM query_table('<src>');
SELECT count(*) FROM search_corpus WHERE src_table='<src>';
SELECT объектов_витрины, в_корпусе FROM search_coverage WHERE entity='<src>';

-- 2) Хотфикс на выкате
-- /opt/1c-mcp-reports/coverage_build.sql:29-30
-- PREPARE p_cov_obj … count(*) … -- okna-pcov-hotfix

-- 3) Case ключа
SELECT list_position(['Ref_Key']::VARCHAR[], 'ref_key');  -- NULL
SELECT count(*) FILTER (WHERE regexp_full_match(row_key,'[0-9a-fA-F]{40}'))
FROM search_corpus WHERE src_table='catalog_валюты';       -- 6 = все sha1

-- 4) Не лаг
SELECT k, to_timestamp(v) AT TIME ZONE 'UTC' FROM search_quality
WHERE k IN ('build_ts','mart_changed_ts');
-- build 2026-08-30 16:37:05 > mart 2026-08-29 15:01:44
```

---

## Итог по 15 строкам

| Категория | Строк из 15 | Смысл |
|---|---:|---|
| Осознанный «не объект» / пустой `ref_key`, раздутый `count(*)` | **15** | ложная недостача health |
| Лаг такта | **0** | build после mart |
| Дефект merge: живая nonempty строка не в корпусе | **0** | nonempty ≤ corp по всем 5 |

Дополнительно (не входят в «15 missing», но рядом): **сироты корпуса** (corp − nonempty): договоры +3, валюты +2, контрагенты +10, ПКО +15 — следствие sha1-ключей / неполной чистки; чинятся вместе с case `Ref_Key`/`ref_key`.

## Рекомендация

**Чинить — да**, но не «догонять 15 строк в merge».

1. **Срочно (снимает degraded):** выкат `coverage_build.sql` — убрать `okna-pcov-hotfix` `count(*)`; вернуть `count(DISTINCT)` по физической колонке с `lower(column_name)='ref_key'` (как в репо `ubuntu/serenedb/coverage_build.sql` ~44–60). Файл на окне: `/opt/1c-mcp-reports/coverage_build.sql:29-30`.
2. **Корпус (ключ):** `ubuntu/serenedb/corpus_build.sql` — сравнивать ключ/колонки case-insensitive (`lower(col)` ↔ `lower(unnest(key_cols))`, литералы `col='Ref_Key'` → `lower(col)='ref_key'`): ~827 (`own_ref`), ~1435–1437 (`keyed`/`list_position`), ~1539 (`col='Ref_Key'`), зеркала в chunk-ветке ~1670+. После выката — такт с полной пересборкой затронутых (или сброс sha1-ключей) и DELETE сирот.
3. **Витрина (желательно):** источник пустых `ref_key` в packet/apply — отдельно; на coverage после п.1 они перестанут открывать 503.
4. **Не чинить** «фильтром резолвера» и **не ждать** следующего такта ради этих 15 — лаг не при чём; следующий такт с тем же hotfix снова покажет дыру.

После п.1 ожидаемый `/health`: `coverage_gap` по этим 5 исчезнет или сменится на сигнал «corp > vit» (сироты) — его уже честно чинить п.2.
