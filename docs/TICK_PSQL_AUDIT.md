# Аудит psql за такт (п. 20 TARGET.md)

Статический разбор цепочки `ubuntu/serenedb/build.sh` и всего, что он зовёт.
Замер живым прогоном — `work/pipeline/count_psql_per_tick.sh` (обёртка PATH, такт
не меняется). Дата разбора: 26.08.2026.

**Считается:** каждый отдельный процесс `psql` (в т.ч. фоновые в `embed_missing.sh`,
пайпы `\gexec`, вызовы из Python через `subprocess`).

**Не считается:** SQL внутри одного `-f file.sql` (один процесс psql).

---

## Сводка

| Показатель | Число |
|---|---|
| **Нижняя граница psql за такт (SKIP_BUILD, дельта векторов 0, alias/solr без работы)** | **≈ 75** |
| **Типичный такт с пересборкой корпуса и дельтой embed (1 раунд × 3 цели, WORKERS=8)** | **≈ 150–220** |
| **Верхняя граница по статике (полная сборка + classify max + embed 6 раундов × 3 + wiki collision 40 + branch)** | **до ≈ 800+** |

Формула верхней границы embed-ветки за один вызов `embed_missing.sh`:

```
7 (старт: db + transfer + guard + left; при n=0 — только это)
+ R × (21 + WORKERS + [2 если ключей > 1])
```

где `R ≤ EMBED_ROUNDS` (умолч. 6), `WORKERS = BUILD_EMBED_WORKERS` (умолч. 8).

---

## Таблица: шаг такта → psql → данные наружу → обработка вне базы

Условные обозначения:

- **DDL/метаданные** — счётчики, `current_database`, секреты, `VACUUM`, без строк данных.
- **Δ** — зависит от остатка работы / бюджетов / `SKIP_BUILD`.

| Шаг | Файл:строка | psql (статика) | Что уезжает наружу | Обработка вне базы |
|---|---|---:|---|---|
| **лок** | `build.sh:73` | 1 | имя базы (1 строка) | нет |
| **0 init** | `build.sh:147-148` | 1 | DDL/служебный вывод `-q` | нет (внутри `-f corpus_init.sql`) |
| **секреты** | `build.sh:173` | 1 | DDL, вывод подавлен | нет |
| **precheck** | `build.sh:184-187` | 1 | проверки, `-q` | нет |
| **пропуск корпуса?** | `build.sh:233-245` | 1 | 0/1 | нет |
| **1 corpus_build** | `build.sh:256` | 0–1 | внутри SQL (`read_text` OData) | **нет** (сборка в движке) |
| **merge baseline** | `build.sh:265-268` | 0–1 | INSERT метки | нет |
| **disk preflight** | `box_tune.sh:371,385,399` | 0–3 | count (числа) | нет |
| **merge cfg** | `build.sh:277-278` | 0–1 | DDL | нет |
| **2 merge** | `build.sh:279` | 0–1 | внутри `corpus_merge.sql` | нет |
| **corpus_built_ts** | `build.sh:281-283` | 0–1 | INSERT | нет |
| **1-period** | `build.sh:299-301` | 1 | JSON из файла → `search_meta` | нет (файл — только транспорт в `read_json`) |
| **embed_check** | `build.sh:144` | 0 | — | curl к эмбеддеру (не psql) |
| **2-бис classify** | `classify_entities.py:143-207` | 4–20 | CSV: метаданные сущностей (имена, колонки, count) | **да** → LLM; запись `INSERT` одним SQL |
| **2-тер packet** | `packet_config.py:281-417` | 2–3 | CSV контур; `$metadata` из **файла** на диске | **да** → Python; конфиг в JSON-файл (не psql) |
| **3 embed labels** | `embed_missing.sh` | **Δ 7–179** | при работе: stderr длин; count | **нет** (`ai_embed` внутри) |
| **4 resolver build** | `build.sh:359` | 1 | внутри SQL | нет |
| **4 embed resolver** | `embed_missing.sh` | **Δ 7–179** | то же | нет |
| **5 embed corpus** | `embed_missing.sh` | **Δ 7–179** | то же | нет |
| **6 VACUUM index** | `build.sh:420` | 1 | служебный | нет |
| **7 coverage** | `build.sh:428` | 1 | агрегаты переписи | нет |
| **7 wiki_alias** | `wiki_alias.sh` | **Δ ≈ 16–260+** | JSON пачек в `$CSV_DIR`; collision до 40× | **да** → LLM + Python parse |
| **7 wiki_publish** | `wiki_publish.sh:51,69,74` | 3 | **все `page_id, body` вики** в файл | **да** → Python → `.md` на диск (не обратно в БД) |
| **7-solr (build)** | `solr_synonyms_build.py` compile | 1–2 | JSON alias; DDL-файл | **да** → Python compile → `psql -f` |
| **7-solr (wiki_alias)** | `wiki_alias.sh:610-613` | 0–3 | дубль шага выше, если alias уже вызвал compile | **да** (тот же) |
| **7-бис card SQL** | `build.sh:461` | 1 | внутри SQL | нет |
| **7-бис card embed** | `embed_all.sh:47-228` | 5–8 + **Δ embed** | stats counts | нет (embed через `ai_embed`) |
| **7-бис branch** | `branch_alias.sh` (из wiki_alias:600) | **Δ ≈ 5–30+** | JSON пачек | **да** → LLM + Python |
| **8 postcheck** | `build.sh:468` | 1 | проверки | нет |
| **cleanup secrets** | `build.sh:135` | 1 | DDL | нет |
| **base_url секретов** | `box_tune.sh:225-227` | 0–1 | строки секретов (без ключей в норме) | нет |

### Детализация `embed_missing.sh` (один вызов)

| Подшаг | Строки | psql | Данные |
|---|---|---:|---|
| имя базы | 79 | 1 | 1 строка |
| transfer (старт) | 183-188 | 2 | SQL-текст UPDATE |
| tick guard | `embed_tick_guard.sh:51,59` | 1 | count / NULL |
| left() | 161 | 1 | одно число |
| **если n=0** | 222-224 | 2 | drop DDL |
| **на раунд** transfer×2, left×2, drop×2, todo, impossible×2, threads 0–2, **WORKERS параллельно**, stats 0–2 | 255-387 | **21+WORKERS** (+0–4) | векторы **не** наружу; stderr ошибок embed |

При `WORKERS=8`, `EMBED_ROUNDS=6`, трёх целях (labels, resolver, corpus):  
**3 × (7 + 6×29) ≈ 537** psql только embed-путь (верхняя граница).

### Детализация `wiki_alias.sh` (бюджет `WIKI_ALIAS_MAX_SEC`, CAP=`WIKI_ALIAS_PER_TACT`)

| Подшаг | psql за итерацию | Макс. итераций | Примечание |
|---|---:|---:|---|
| DDL/GRANT | 3 | 1 | |
| проход сущностей | 3 (+2 при сбое) | ⌈CAP/BATCH⌉, BATCH=20 | JSON → файл |
| добор величин | 3 (+1 при сбое) | ⌈CAP/BATCH⌉ | |
| разведение столкновений | 4 | 40 | JSON → файл |
| day-basis fork | 4 (+mark) | по классам | |
| `branch_alias.sh` | 4–6 | ⌈CAP/BATCH⌉ | |
| итоговая статистика | 1 | 1 | |
| solr compile | 2–3 | 1 | см. кандидаты |

---

## Шаги с обработкой данных вне базы

| # | Шаг | Суть |
|---|---|---|
| 1 | `classify_entities.py` | метаданные таблиц → LLM → `search_entity_class` |
| 2 | `wiki_alias.sh` / `branch_alias.sh` | JSON пачек → LLM → parse Python → `read_json` |
| 3 | `solr_synonyms_build.py` | JSON alias → Python Solr-map → файл DDL → apply |
| 4 | `wiki_publish.sh` | все тела wiki-страниц → файлы OpenClaw |
| 5 | `packet_config.py` (опц.) | контур из БД + `$metadata` с диска → JSON конфиг агента |

**Про эмбеддинг (п. 20, строка 26.08):** сам счёт вектора — штатный `ai_embed` внутри
движка (доки: Sql › Functions › AI Functions). Это **не** «свой процесс эмбеддинга».
Но **веер параллельных `psql` и раундовый цикл** в `embed_missing.sh` — запрещённый
п. 20 цикл клиента; решение по нему — в таблице ниже и в § «embed_missing».

---

## Решения Э1 (26.08): заход → решение → основание

Исходы по плану (`PLAN_TO_TARGET.md` Э1), уточнение Ф2 26.08:

- **(а)** убирается / уже внутри движка — штатное средство и форма «один запрос/скрипт»;
- **(б)** остаётся как разрешённый остаток — только пункт исчерпывающего перечня п. 20:
  OData в 1С · вызов языковой модели · отрисовка изображений · проверка ответа модели;
- **долг** — вне перечня п. 20 и без доказанной замены штатным средством (не маскировать под **(б)**).

Доки SereneDB, на которые опираются отрицательные и положительные выводы этого раздела
(MCP `serenedb-docs`, перепроверка 26.08 Ф2):

| Тема | Раздел |
|---|---|
| `ai_embed`, провайдеры, performance | Sql › Functions › AI Functions (`/sql/functions/ai`) — в т.ч. «Each ai_embed call is a network request to the provider» |
| один INSERT/UPDATE с `ai_embed` по колонке | Quick Start › Generate embeddings |
| `SET threads` | Sql › Statements › SET / RESET; Configuration › Configuration (примеры / `duckdb_settings`). **Было неверно:** путь «Configuration › Pragmas › threads» — отдельного § threads на странице Pragmas при `read_section` нет; якорь поиска `#threads` не заменяет раздел |
| sync IO / один HTTP на поток при **чтении remote files** | Cookbook › Performance › Tuning Workloads › Querying Remote Files — цитата про remote files, **не** про `ai_embed` |
| `CREATE`/`DROP` SECRET | Configuration › Secrets Manager; Sql › Statements › CREATE SECRET |
| `solr_synonyms` + inline `SYNONYMS` | Sql › Statements › Create text search dictionary › solr_synonyms |
| `string_agg` | Sql › Functions › Aggregate Functions › string_agg |
| `MERGE INTO` | Sql › Statements › MERGE INTO |
| `read_json` | Data import and export › Json › Loading JSON |
| `COPY ... TO` / partitioned writes | Sql › Statements › COPY; Data import and export › Partitioning › Partitioned Writes (Hive-иерархия / `data_N` / `FILENAME_PATTERN` — не `{page_id}.md`) |
| `VACUUM (REFRESH_INDEX)` | Sql › Statements › VACUUM › Inverted Index Maintenance |

Штатного планировщика SQL-джоб / «векторайзера» / retry HTTP 429 в доках **нет**
(поиск по docs: scheduled/cron job, vectorizer — пусто относительно встроенного досчёта;
AI Functions сегодня = только `ai_embed`).

### Таблица решений по заходам такта

| Заход | Решение | Основание |
|---|---|---|
| лок `current_database` | **(а)** уже внутри | Один `SELECT current_database()`. Клиент — транспорт метки лока. |
| cleanup / CREATE SECRET | **(а)** уже внутри | Sql › CREATE SECRET / Secrets Manager. Один `-f`/`-c`. |
| 0 init `corpus_init.sql` | **(а)** уже внутри | DDL словарей/схемы одним `-f`. |
| precheck `corpus_precheck.sql` | **(а)** уже внутри | Проверки одним `-f`. |
| пропуск корпуса? (0/1) | **(а)** уже внутри | Один `SELECT` условия skip. |
| 1 corpus_build | **(а)** уже внутри | Сборка в SQL; OData — `read_text`+HTTP SECRET движка (не свой клиент 1С в этом шаге). |
| merge baseline / cfg / merge / ts | **(а)** уже внутри | `INSERT`/`CREATE`/`corpus_merge.sql` — SQL внутри движка. |
| disk preflight (`box_tune`) | **(а)** уже внутри | Счётчики/`count` без выноса строк данных. |
| 1-period → `search_meta` | **(а)** уже внутри | Файл — транспорт; запись — `read_json` (доки JSON Loading). |
| 2-бис classify | **(б)** + узкий SQL | **(б)** вызов языковой модели (класс сущности по смыслу). SQL: один SELECT метаданных + batch `INSERT` — уже близко к норме; смысл классификации в SQL **не** переносится (`ai_embed` не классифицирует — AI Functions). |
| 2-тер packet_config | **(а)** + **долг** | Контур витрины — **(а)** одним SQL. Разбор `$metadata` в такте — чтение **локального файла** `<PACKET_META_DIR>/<base_id>/$metadata` (`packet_config.py`, без OData). **Было неверно:** ярлык **(б)** «поход в 1С за метаданными» — в перечень п. 20 («поход в 1С … по OData») этот шаг **не** садится: живой 1С здесь не зовётся. Итог: **долг**, не разрешённый остаток. Закрытие — **(а)** через штатный `read_text` того же снимка (как уже делает `corpus_build`), если разбор свойств укладывается в SQL; иначе долг висит до доказательства. |
| 3/4/5 `embed_missing` ×3 | **(а) сделано 27.08** | Одна сессия `part_0`+`\gexec`; `EMBED_ROUNDS` умолч. **1**; argv WORKERS игнорируется. Параллель — `SET threads`. Замок `test_embed_missing_single_session` **11/0**. [замер 27.08] 26.08.1: ai_embed×256 без SetSize. |
| 4 resolver_build | **(а)** уже внутри | Один `-f resolver_build.sql`. |
| 6 VACUUM index | **(а)** уже внутри | `VACUUM (REFRESH_INDEX)` — Sql › VACUUM. |
| 7 coverage | **(а)** уже внутри | Агрегаты переписи одним `-f`. |
| 7 wiki_alias / branch_alias | **(б)** + **(а)** | Генерация алиасов — **(б)** вызов языковой модели. Вынос JSON файлом и обратная запись через Python — **(а)** убрать: пачка в TEMP/`COPY`/`read_json` + `MERGE INTO` (доки MERGE / JSON). |
| 7 wiki_publish | **(а)** + **долг** | Сборка тел — уже `wiki_build.sql` **(а)**. Выгрузка сейчас: `SELECT page_id, body` → Python → `{page_id}.md` + purge устаревших (`wiki_publish.sh`). **Было неверно:** «заменить на `COPY … TO` / PARTITION_BY» как эквивалент — в доках COPY/Partitioned Writes дают Hive-каталоги и `data_N`/`FILENAME_PATTERN`, не раскладку vault OpenClaw и не удаление устаревших `.md`. Штатное средство выгрузки **есть**, эквивалентность текущему шагу **не** доказана → dump+purge = **долг** (в перечень п. 20 не входит; «отрисовка изображений» — про графики, не vault). CLI `openclaw wiki` — не клиент SereneDB. |
| 7-solr compile | **(а)** убрать Python | Штатные куски: `string_agg` + `DROP`/`CREATE TEXT SEARCH DICTIONARY … template='solr_synonyms'` (доки solr_synonyms + Aggregate Functions). **Было неверно:** «Python `compile_rules` = один `string_agg`» — в коде ещё escape `,`/`\`, dedupe, skip однотермных, sort, `check_limits` (`solr_synonyms_build.py`). Закрытие **(а)** = один SQL-скрипт, который **воспроизводит** эти шаги штатными средствами движка и затем CREATE DICTIONARY; не «достаточно одного агрегата». |
| 7-бис card SQL | **(а)** уже внутри | `entity_card_build.sql`. |
| 7-бис card embed | **(а)** как embed_missing | Тот же `ai_embed`; веер/`embed_all` — под то же решение **(а)**. |
| 8 postcheck | **(а)** уже внутри | Один `-f corpus_postcheck.sql`. |
| base_url check секретов | **(а)** уже внутри | Служебный SELECT/`CREATE OR REPLACE SECRET`, без строк корпуса. |

### `embed_missing.sh` и новая строка п. 20 про `ai_embed`

**Что уже соответствует контракту:** текст не эмбеддится своим процессом; наружу уходит
HTTP провайдера изнутри `ai_embed` (Sql › Functions › AI Functions › Performance:
«Each ai_embed call is a network request to the provider»). Это ровно добавленная 26.08
строка п. 20.

**Что нарушает п. 20:** запуск `psql` в цикле раундов и веер `WORKERS` фоновых `psql` с
`\gexec` по пачкам (до ≈ 7 + R×(21+WORKERS) процессов на цель). Запрет контракта —
«не запускать процесс psql в цикле», не «не вызывать ai_embed».

**Почему сейчас нельзя одним запросом (не «наверное», а замер + доки):**

1. **Канон доков — один оператор на набор.** Quick Start / AI Functions показывают
   `INSERT … SELECT … ai_embed(col, …)` / `UPDATE … SET emb = ai_embed(...)` по таблице целиком.
2. **Наша сборка этот канон ломает на `FLOAT[1024]`:** оператор с ≳16–32 строками падает
   `Vector::SetSize out of range` (`docs/EMBED_BULK_HOWTO.md`, комментарий
   `embed_missing.sh`; замер на **26.07.3**). Живой перезамер пачки на **26.08.1** в Э1
   не снимался (офлайн-граница задачи) — до доказательства обратного предел считается
   действующим.
3. **Параллельный `UPDATE … ai_embed` в одну таблицу** — `SIGSEGV` движка (techContext,
   замер 28.07). Обход скрипта: своя `_part_N` на поток + `transfer` — отсюда веер `psql`.
4. **Потолок одновременных HTTP при досчёте ≈ `threads`** — это **наш замер**
   (`docs/EMBED_BULK_HOWTO.md`, techContext ловушка 51: in-flight ≈ `SHOW threads`,
   воркеры сверх того стоят в очереди). AI Functions говорят только: каждый `ai_embed` =
   network request to the provider (без потолка = `threads`). Цитата Cookbook › Tuning
   Workloads › Querying Remote Files («each SereneDB thread can make at most one HTTP
   request at a time») — про **synchronous IO при чтении remote files**, не про `ai_embed`.
   **Было неверно:** растягивать эту цитату как док-основание потолка для embed.
   Практический вывод замера тот же: внешние воркеры сверх `threads` только размножают
   процессы `psql`.
5. **Retry 429 раундами** — в доках AI Functions retry/очереди эмбеддинга нет; раунды —
   shell вокруг отказа провайдера, не штатное средство.

**Чтобы заход исчез (критерий закрытия):**

1. Движок принимает крупный `UPDATE`/`INSERT` с `ai_embed(...)::FLOAT[1024]` без
   `Vector::SetSize` (или появляется ручка размера пачки/`row group` для AI) — тогда
   досчёт = **один SQL на таблицу** по канону доков.
2. Либо, пока (1) нет: **одна** psql-сессия, пачки ≤ рабочего предела **внутри** одного
   скрипта (`\gexec`/серия операторов), без N внешних процессов; параллельность — только
   `SET threads` (Sql › SET / RESET; Configuration overview), не веер клиентов.
   `SIGSEGV` на параллельной записи в одну таблицу обязан быть снят вендором или обойдён
   записью в staging **тем же** сеансом.
3. Раунды 429 — либо терпимы как повтор **того же** одного SQL следующим тактом (без
   внутреннего `while` в shell), либо появятся в движке; своего эмбеддера не писать.

Итог по трём целям такта (labels / resolver / corpus): решение **(а)** на все три;
остаётся только транспорт SQL к уже штатному `ai_embed`, не «разрешённый остаток» из
перечня (перечень не содержит «оркестрация psql»).

---

## Итог Э1 (замер + решение)

| Метрика | Значение |
|---|---|
| **Живой last-OK такт okna** | **2026-08-24 05:37:55 → 05:40:32 UTC** (157 с; после — failed / нет `$metadata`) |
| **Путь такта** | SKIP_BUILD; embed n=0×3; wiki dump **254** стр; alias mktemp fail; card |
| **psql за тот такт (реконструкция по маркерам+код)** | **≈ 49** |
| **Нижняя граница (unique PID в journal)** | **≥ 19** |
| **Строк/байт наружу (wiki SELECT)** | **254** стр, **≈314 130** байт body (живой `sum(length(body))` 27.08) |
| **Векторы наружу** | **0** (`ai_embed` внутри; остаток 0) |
| **psql за такт (статика, минимум после Э1)** | **≈ 40–55** (без веера WORKERS; единицы на SQL-шаг + LLM-обвязка) |
| **psql за такт (было, верх веера embed)** | **до ≈ 800+** (формула R×(21+WORKERS)×3) — **снято** с tact-path |
| **Заходов с решением (а)** | SQL-шаги + **embed_missing одна сессия** (27.08) + solr compile как долг SQL |
| **Заходов с решением (б)** | classify / wiki_alias / branch_alias (LLM) |
| **Долг (закрыт Э6/Э7 27.08)** | packet `$metadata` → `read_text` (`e1056c7`); wiki dump → VIEW only (`5633514`) |

**[замер 27.08, okna SereneDB 26.08.1]** боковая таблица: `UPDATE … ai_embed(…)::FLOAT[1024]` на
**8, 16, 32, 48, 64, 96, 128, 256** строк — **без** `Vector::SetSize` (предел 26.07.3 на этой
сборке не воспроизведён). Пачки в tact-path сохранены (бюджет символов / дельта).

Живой замер после первого прогона с `count_psql_per_tick.sh` дополняет колонку
«факт» в `summary.json`. Решение Э1 от числа факта не зависит: оно фиксирует судьбу
каждого захода; снятие веера — доказано замком + живым SetSize-пробом.
