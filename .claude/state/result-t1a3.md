# Аудит T1-A3: OOM на слиянии корпуса — причина и штатная защита

Дата: 02.09.2026. Контекст нулевой. Серверы не трогались. Источники: репозиторий `/srv/1c` + MCP `serenedb-docs` (search_docs → read_section / WebFetch). Сборка движка в фактах: **26.07.3**. Доки — текущие (новее сборки); где фича могла появиться позже 26.07.3 — помечено явно; на живом инстансе okna **не проверялось** (ssh запрещён).

---

## 0. Картина в коде (что реально падает)

### Упавший statement

`CREATE OR REPLACE TABLE tmp3_merge_unmatched AS …` — `ubuntu/serenedb/corpus_merge.sql:162–199`.

Семантика: строки боевого `search_corpus` по сущностям, которые есть в стейдже `tmp3_corpus`, **кроме** сущностей из `tmp3_merge_rewrite_wave`, которые **не** сопоставились ни одним из **семи** анти-условий с стейджем (exact key, `#sha1`-хвост, `split_part('#')`, префикс `|`, кросс `#`/`|`, хвост после Recorder при Period в ключе).

Комментарий в том же файле уже фиксирует класс аварии:  
`corpus_merge.sql:107–110` — «Построение tmp3_merge_unmatched = перебор … → OOM» (замер 31.08 okna).

### Что `MERGE_CHUNK_ROWS` режет — и чего не режет

| Место | Режет ли unmatched? |
|---|---|
| `build.sh:302–337` — пишет `tmp3_merge_cfg.chunk_rows` (умолч. 1_000_000), зовёт `corpus_merge.sql` | конфиг есть до SQL |
| `corpus_merge.sql:162–199` unmatched CTAS | **НЕТ** |
| `corpus_merge.sql:739–789` миграция `content_hash` пачками + `checkpoint()` | да, позже |
| `corpus_merge.sql:811–882` MERGE/UPDATE пачками + `checkpoint()` | да, позже |
| `box_tune_disk_*` (`box_tune.sh:434–489`) | только **WAL/диск** пачки MERGE, не RAM анти-джойнов |

**Вывод:** чанкование слияния — защита диска/WAL на **фазе записи**. Фаза гварда (unmatched) — один монолитный CTAS без `chunk_rows`.

### Порядок `edited_delta` vs `unmatched` (побочная находка)

`tmp3_merge_edited_delta` (`:154–160`) читает `tmp3_merge_unmatched` **до** его создания (`:162`). Таблицы `tmp3_*` — обычные и переживают рестарт (`:19–21`). Значит на повторных прогонах `edited_delta` считает по **прошлому** unmatched, а не по текущему. На свежей БД без таблицы — ошибка «нет таблицы». К OOM 02.09 это не причина (упал сам unmatched), но это дефект корректности гварда «правок».

### Рестарт между шагами такта

`build.sh:296–337`: `corpus_build.sql` → сразу конфиг merge → `corpus_merge.sql`. **Нет** checkpoint/restart между шагами. Юнит `ubuntu/serenedb/serenedb.service:15–16`: `Restart=always`, `RestartSec=2`; **MemoryMax в unit-файле репозитория нет** (согласуется с фактом MemoryMax=infinity). Spill-cwd зафиксирован в unit (`:8–13`, WorkingDirectory=/var/lib/serenedb).

---

## 1. Почему statement 162–199 ест память

### Что материализуется (модель по докам + тексту SQL)

Доки: JOIN/GROUP BY — **blocking operators**, требуют буферизации входа; larger-than-memory для join есть, но  
«If multiple blocking operators appear in the same query, SereneDB may still throw an out-of-memory exception»  
— https://docs.serenedb.com/cookbook/performance/how_to_tune_workloads (Limitations).

В unmatched **семь** коррелированных `NOT EXISTS` подряд (`:170–198`) = до семи anti-join операторов в одном плане. Каждый equality-анти обычно строится как hash anti-join: **build-side hash table** по ключу(ам) из `tmp3_corpus` (~1.44M строк) + probe по `search_corpus` (~1.66M, уже отфильтрованному по src_table / rewrite_wave).

Дополнительно:

- Ключи — `VARCHAR` (GUID/sha/составные `|`); hash table держит строки, не int.
- Часть предикатов — выражения на **обеих** сторонах (`split_part`, `substr`, `regexp_replace`, `length`) — `:172–198`. Equality по выражениям всё ещё hashable, но дороже (материализация вычисленных ключей) и хуже для pushdown.
- Вложенный `EXISTS` на `tmp3_key` внутри 7-го анти (`:197–199`) — ещё один оператор на каждую кандидатную пару.
- Комментарий `:167–169` сознательно держит **раздельные** анти-соединения (один `IN` убивал equality → перебор; замер 30.07). Цена: несколько HT вместо одной.

**ГИПОТЕЗА H1 (главная):** пик RAM на unmatched = одновременные hash-таблицы / spill-буферы нескольких anti-join + промежуточные пайпы в одном CTAS; при высокой базовой RSS (см. H3) OS OOM наступает раньше, чем движок успевает spill/abort.  
**Проверка:** на копии/стейдже `EXPLAIN` и `EXPLAIN ANALYZE` (или profiling json) только unmatched; смотреть число HASH_JOIN/ANTI и estimated memory; параллельно `SELECT * FROM duckdb_memory()` и `duckdb_temporary_files()` во время прогона (доки: duckdb_memory, duckdb_temporary_files). Сравнить RSS процесса до/после одного CTAS.

**ГИПОТЕЗА H2:** rewrite_wave не покрыл крупные сущности (порог ≥90% unmatched exact + |Δ|≤5%, `:146–148`) → probe почти весь корпус × полный стейдж; при покрытии wave unmatched был бы маленьким.  
**Проверка:** `SELECT * FROM tmp3_merge_ent_counts` / `tmp3_merge_rewrite_wave` после шагов `:123–148` (до OOM — отдельным прогоном только до unmatched); доля `(было - matched_exact)/было` по топ-сущностям.

**ГИПОТЕЗА H3 (пик «копился весь день»):** RSS движка после 5 ч монолитного `p_doc` + аптайм 26 ч уже высок (буферный кэш до `memory_limit`, jemalloc не отдаёт арены OS). Unmatched стартует не с «чистых» гигабайт, а с базы ~десятки ГиБ. Пик MemoryPeak=91.7 ГиБ — кумулятив процесса, не только 2 мин merge.  
**Проверка:** до merge снять `systemctl show serenedb -p MemoryCurrent` / RSS + `SHOW memory_limit` + `PRAGMA database_size` (колонка memory_usage); после одного лёгкого `SELECT 1` и после `CHECKPOINT` — не падает ли RSS (обычно нет у jemalloc без flush/restart). Сравнить тот же unmatched на **свежеперезапущенном** движке при том же корпусе/стейдже.

**ГИПОТЕЗА H4:** allocations **мимо** buffer manager (векторы, состояния join) + default `memory_limit` ≈ 80% RAM (~100 ГиБ на 125 ГиБ) → движок не начинает агрессивный spill / не бросает свой OOM, пока ядро не убьёт.  
Источник доков: https://docs.serenedb.com/configuration/pragmas#memory-limit (лимит только buffer manager; actual consumption can be higher); https://docs.serenedb.com/cookbook/performance/oom (рекомендация опустить лимит до 50–60%, иначе OS/OOM-reaper).  
**Проверка:** при том же запросе `SET memory_limit='60GB'` (или 50–60% RAM) — ожидаем либо spill в `.tmp` (`duckdb_temporary_files()`), либо controlled Out of Memory Error движка **без** kernel kill; журнал юнита без «Killed».

**ГИПОТЕЗА H5 (слабее):** один из expression-анти деградирует в nested loop / плохой порядок join → взрыв промежуточной кардинальности.  
**Проверка:** `EXPLAIN` — Nested Loop vs Hash; `SET disabled_optimizers=…` только для диагностики (доки предупреждают: не для прода).

---

## 2. Что ШТАТНО ограничивает/делит память (26.07.3 vs доки «сейчас»)

| Механизм | Есть в доках | Роль | Примечание к 26.07.3 |
|---|---|---|---|
| `SET memory_limit` / default **80% RAM** | да, pragmas + limits | потолок **buffer manager**, не всего процесса | используется проектом (`box_tune.sh`, `corpus_build` chunk от `SHOW memory_limit`). На живой 26.07.3 — **есть** (код опирается). |
| Per-query / per-statement memory cap | **не найдено** в limits/pragmas | — | **НЕТ** как отдельной фичи в доках. Один глобальный/сессионный `memory_limit`. |
| Spill-to-disk (join/group/sort/window) | да, how_to_tune_workloads | out-of-core при давлении на buffer manager | заявлено штатно; **ограничение:** несколько blocking в одном запросе → всё равно OOM. |
| `temp_directory` | pragmas | куда Spill | unit уже чинит CWD (`serenedb.service:8–13`). |
| `max_temp_directory_size` | limits: default **unlimited** | потолок spill на диске | в доках есть; наличие в 26.07.3 — **проверить** `SELECT current_setting('max_temp_directory_size')` на живом (здесь не делалось). |
| `SET threads` | pragmas + OOM cookbook | ↓ параллелизм → ↓ пик RAM (~125 MB/thread min; 1–4 ГиБ/thread ideal) | есть; build/embed уже крутят threads. |
| jemalloc + `allocator_background_threads` (default **false**), `allocator_flush_threshold` (128 MiB), `allocator_bulk_deallocation_flush_threshold` (512 MiB) | configuration overview | возврат/сброс арен аллокатора | имена в текущих доках; на 26.07.3 — **пометить «проверить SHOW/duckdb_settings»**; факт юнита «jemalloc» согласуется с поставкой. |
| `preserve_insertion_order=false` | OOM cookbook | меньше RAM на крупные import/export | к unmatched CTAS слабо релевантно; в `box_tune` уже в плане. |
| `duckdb_memory()` / `PRAGMA database_size` | metadata | наблюдение, не лимит | |
| systemd `MemoryMax` | **не** доки SereneDB | внешний рубеж → SIGKILL → `Restart=always` | в репо unit **не задан**; доки рекомендуют снизить **внутренний** `memory_limit`, а не опираться на kernel kill. |
| Батчирование CTAS по ключам | не отдельная фича движка | делается **SQL-ом приложения** | `MERGE_CHUNK_ROWS` так делает для MERGE; для unmatched — **не применяется**. |
| Авто-restart между шагами пайплайна | нет | — | только ручной/`systemctl` из скриптов онбординга (`box_tune.sh:309` — apply first build, не такт). |

WAL при abort/kill: транзакция откатывается (`sql/statements/transactions`); незакоммиченные изменения не видны. Факт 02.09 (корпус 1_665_427 / emb 1_657_724 целы) согласуется: OOM был **до** фазы записи MERGE (`:794+`). `CHECKPOINT` сбрасывает WAL в файл (`utility#checkpoint`); `enable_checkpoint_on_shutdown` — на штатном shutdown, не на SIGKILL.

---

## 3. Эквивалентные переписывания unmatched (дешевле по RAM)

Критерий п.13: молча потерять строку в «уйдёт» / не увидеть удаление = дефект. Семантика unmatched: строка корпуса «сирота» относительно **всех** семи правил сопоставления.

| Вариант | Эквивалентность | Память | Риск п.13 / векторов |
|---|---|---|---|
| **A. Один `LEFT JOIN … WHERE right IS NULL` / `ANTI JOIN` на exact `row_key`** вместо 7 NOT EXISTS | **НЕ эквивалентно** — отбросит остальные 6 правил форм ключа | ниже | Ложные «уйдёт» → ложный STOP гварда или (если гвард обойти) лишний DELETE ключей → **векторы/строки**. |
| **B. Штатный `ANTI JOIN` синтаксис** (= NOT EXISTS / LEFT IS NULL по тому же предикату) | да, для одного предиката | обычно ≈ NOT EXISTS | Низкий, если предикат тот же. Доки: https://docs.serenedb.com/sql/query_syntax/from_and_join#semi-and-anti-joins |
| **C. Pre-materialize мини-таблицы ключей стейджа** (`src_table, row_key, k_exact, k_nosha, k_split_hash, k_rec, k_tail, …`) одним проходом по `tmp3_corpus`, затем **последовательные** ANTI/LEFT IS NULL к корпусу | да, если все 7 предикатов сохранены и NULL/''-гардные условия те же (`position('#')`, `split_part <> ''`, Period в `tmp3_key`) | **пик ниже**: один build HT за шаг; промежуточные таблицы на диске | Семантика ок при побайтовом совпадении условий. Риск — ошибка в формуле ключа. |
| **D. Резать по `src_table`** (десятки сущностей): `CREATE unmatched; INSERT…SELECT … WHERE c.src_table = ?` в цикле/`\gexec`, как collapse_dead | да при UNION всех сущностей из фильтра | резко ниже (HT ≈ размер сущности) | Низкий. Не забыть сущности вне цикла. |
| **E. Sequence-of-batches по hash(row_key)%N** | да, если покрыть 0..N-1 без пропуска | ниже | Низкий при полном покрытии; иначе silently недосчёт «уйдёт». |
| **F. Оставить 7 NOT EXISTS, но 7 отдельных CTAS** («остаток после анти-1», затем анти-2, …) | да | ниже пика (один join за statement) | Низкий. Ближе всего к текущей семантике. |
| **G. Свести 7 ключей к одной колонке через OR в одном JOIN** | опасно: OR часто ломает hash → nested loop (уже жгли на IN, `:167–169`) | может **вырасти** | Риск таймаута/OOM и неверного плана. |

**Нельзя** «просто один LEFT JOIN IS NULL»: текущие 6 дополнительных правил — как раз защита от ложных удалений при смене формы ключа (комментарии `:76–105`, замер 21.08 / 29.08 / 31.08). Упрощение до exact-only **меняет семантику** в сторону ложных потерь.

Исправление порядка: сначала unmatched (C/D/F), потом `edited_delta` по **свежему** unmatched.

---

## 4. Рестарт движка между шагами такта

| Вопрос | Ответ |
|---|---|
| Штатный механизм «checkpoint + restart между corpus_build и corpus_merge» в движке? | **Нет.** Есть `CHECKPOINT` / `force_checkpoint`, `enable_checkpoint_on_shutdown`, WAL rollback. Перезапуск процесса — снаружи (systemd). |
| Есть ли в такте `build.sh`? | **Нет** (`:296–337` подряд). |
| «Руками» между шагами? | Нарушает TARGET п.0 / автономию, если оператор обязан. **Автоматизировать** в `build.sh` (checkpoint → `systemctl restart serenedb` → wait port → merge) — уже «из коробки», не ручная работа; цена: downtime ask на секунды–минуты, сброс кэшей. |
| Нужен ли для корректности данных? | Для ACID — нет (WAL). Для **RAM/jemalloc** после длинного p_doc — часто единственный надёжный сброс RSS (H3). |

---

## 5. Ранжированные варианты защиты от OOM (простота ↓, с риском для векторов/строк)

Условие №1: **векторы не терять**. OOM на unmatched сейчас **до** MERGE/DELETE — корпус/emb целы после WAL rollback. Опасно любое «лечение», которое ослабляет гвард или доходит до DELETE без карты/гейта.

1. **Перед unmatched: `SET memory_limit` на 50–60% RAM + при необходимости `SET threads`↓** (как Cookbook › OOM).  
   - Простота: высокая (сессия merge / несколько строк в `build.sh` перед `-f corpus_merge.sql`).  
   - Риск векторов/строк: **низкий**, если падаем controlled error до записи.  
   - Риск: запрос упрётся в SereneDB OOM вместо kill — такт fail, нужен retry после (2)/(3).

2. **Разбить unmatched на per-`src_table` INSERT’ы (вариант D) или 7 последовательных анти (F), не меняя предикаты.**  
   - Простота: средняя (SQL + `\gexec`, образец уже в файле `:252–256`).  
   - Риск п.13: низкий при полном перечне сущностей и тех же условиях.  
   - Векторы: не затрагивает, пока до MERGE не дошли; гвард остаётся честным.

3. **Pre-materialize таблицы ключей стейджа (C), затем один/несколько ANTI JOIN.**  
   - Простота: средняя.  
   - Риск: ошибка в производном ключе → ложные сироты/пропуски. Приёмка: md5 множества `(src_table,row_key)` vs старый unmatched на фикстуре.

4. **Авто-restart движка между build и merge в `build.sh`:** `CHECKPOINT` → restart unit → wait → merge.  
   - Простота: средняя (systemd уже Restart=always; нужен wait-ready).  
   - Риск данных: низкий (стейдж/корпус на диске переживают — так задумано `:19–21`).  
   - Риск продукта: краткий простой ask; не чинит сам unmatched при холодном старте, если запрос всё ещё > RAM.

5. **Расширить rewrite_wave / не строить unmatched для сущностей с огромным exact-miss, опираясь на xfer+гейт.**  
   - Уже частично есть (`:143–148`, `:166`).  
   - Риск: ослабление порогов → недооценка «уйдёт» → дыры до DELETE; векторы спасает только `tmp3_merge_emb_xfer` + `MERGE_VECTOR_LOSS_*` (`:570–714`). **Опаснее (1)–(3)** без жёсткой приёмки md5/emb.

6. **systemd `MemoryMax` (например 100G) как внешний рубеж.**  
   - Простота: высокая на юните.  
   - Эффект: гарантированный SIGKILL ≈ текущий сценарий; движок поднимается `Restart=always`.  
   - Риск векторов: низкий **на фазе гварда**; **высокий**, если Max сработает на MERGE/UPDATE/DELETE mid-write до commit пачки (хотя пачки+checkpoint уменьшают окно). Доки движка рекомендуют внутренний limit, не kernel kill.

7. **`MERGE_VECTOR_LOSS_BYPASS=1` / поднять tolerance как «защита от OOM».**  
   - **Не защита от OOM.** Только обход гейта векторов при записи.  
   - Риск векторов: **высокий**. Не использовать для этой аварии.

---

## 6. Краткие ответы на вопросы ТЗ

1. **Почему ест память / пик за день:** семь anti-join в одном CTAS (H1) на ~1.6M×1.4M + высокая базовая RSS после длинного p_doc/jemalloc (H3) при `memory_limit`≈80% и аллокациях вне buffer manager (H4) → kernel OOM за ~2 мин merge. Проверки — EXPLAIN/ANALYZE, duckdb_memory/temporary_files, A/B на свежем рестарте, сниженный memory_limit.

2. **Штатные лимиты:** `memory_limit` (buffer manager, default 80%), spill+`temp_directory`, `threads`, jemalloc flush/background (доки; 26.07.3 — verify SHOW). **Нет** отдельного per-query cap в доках. `MERGE_CHUNK_ROWS` — только запись MERGE/миграции, **не** unmatched.

3. **Перепись:** один LEFT/ANTI на exact — **меняет семантику**. Безопасно: per-entity / sequence of antis / pre-materialized keys с теми же 7 правилами; синтаксис `ANTI JOIN` ок как замена NOT EXISTS 1:1.

4. **Рестарт между шагами:** штатного «checkpoint+restart» в движке нет; в такте нет; руками — против п.0; автоматизировать в build.sh — допустимый продуктовый рычаг для сброса RSS, не замена (2).

---

## Источники (якоря)

- `ubuntu/serenedb/corpus_merge.sql:19–21, 107–110, 123–219, 570–714, 739–882`
- `ubuntu/serenedb/build.sh:300–337`
- `ubuntu/serenedb/box_tune.sh:5–11, 105–109, 434–489`
- `ubuntu/serenedb/serenedb.service:8–16`
- https://docs.serenedb.com/configuration/pragmas#memory-limit  
- https://docs.serenedb.com/cookbook/performance/oom  
- https://docs.serenedb.com/cookbook/performance/how_to_tune_workloads (spill, multiple blocking operators)  
- https://docs.serenedb.com/cookbook/performance/environment (jemalloc, memory/thread)  
- https://docs.serenedb.com/configuration/overview#global-configuration-options (`allocator_*`)  
- https://docs.serenedb.com/configuration/limits#limit-values (80% RAM, max_temp_directory_size unlimited)  
- https://docs.serenedb.com/sql/query_syntax/from_and_join#semi-and-anti-joins  
- https://docs.serenedb.com/sql/statements/transactions  
- https://docs.serenedb.com/sql/functions/utility#checkpointdatabase  

**Не проверено на живом 26.07.3 (ssh запрещён):** точное значение `SHOW memory_limit` / `allocator_background_threads` / `max_temp_directory_size` на okna; план EXPLAIN упавшего statement.
