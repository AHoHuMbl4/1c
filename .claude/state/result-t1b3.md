# T1-B3: аудит аудита A3 (OOM слияния)

Дата: 02.09.2026. Контекст нулевой. Серверы не трогались. Файлы кода не правились.
Источники: `/srv/1c/.claude/state/result-t1a3.md`, код `/srv/1c/ubuntu/serenedb/{corpus_merge.sql,build.sh,serenedb.service,box_tune.sh,embed_*.sh,classify_entities.py}`, MCP `serenedb-docs` (+ WebFetch pragmas#memory-limit).

**Краткий вердикт:** отчёт A3 в целом верен по коду и докам; пригоден как основа плана **с обязательными поправками** (число анти = **6**, не 7; авто-restart **сносит TEMPORARY SECRET** и без пересоздания ломает шаги 3–5; рестарт не обязателен, если unmatched режется D/F).

---

## Таблица: утверждение → вердикт → доказательство

| # | Утверждение A3 | Вердикт | Доказательство |
|---|---|---|---|
| 1a | Упавший CTAS = `tmp3_merge_unmatched` в `corpus_merge.sql:162–199` | **ПОДТВЕРЖДЕНО** | `CREATE OR REPLACE TABLE tmp3_merge_unmatched AS` на `:162`; SELECT до `:199`. |
| 1b | В unmatched **семь** анти-условий `NOT EXISTS` | **ОПРОВЕРГНУТО** | В `:170–199` ровно **шесть** `NOT EXISTS` против `tmp3_corpus` (строки 170, 172, 175, 179, 183, 191). Вложенный `EXISTS` по `tmp3_key` (`:197–199`) — фильтр внутри 6-го анти, не седьмой anti-join. Сам файл пишет «все **6** анти-соединений» (`:109`). |
| 1c | Комментарий `:107–110` про OOM (замер 31.08) | **ПОДТВЕРЖДЕНО** | Текст: «Построение tmp3_merge_unmatched = перебор 1,43 млн × 400 тыс. → OOM» + rewrite wave. Совпадает с тем, что утверждает A3. |
| 2 | `MERGE_CHUNK_ROWS` / `tmp3_merge_cfg.chunk_rows` режет только фазу записи (миграция content_hash + MERGE/UPDATE), unmatched не чанкуется | **ПОДТВЕРЖДЕНО** | `chunk_rows` впервые читается на `:740+` (миграция) и `:815+` (MERGE-jobs). CTAS unmatched `:162–199` конфиг не трогает. `build.sh:332–337` пишет cfg и зовёт SQL. |
| 3a | `tmp3_merge_edited_delta` (`:154–160`) читает `tmp3_merge_unmatched` **до** CREATE (`:162`) — дефект порядка | **ПОДТВЕРЖДЕНО** | Буквально: `:154–160` → `FROM tmp3_merge_unmatched u`; CREATE unmatched только на `:162`. |
| 3b | Другого CREATE `tmp3_merge_unmatched` в репо нет (A3 не упустил) | **ПОДТВЕРЖДЕНО** (с оговоркой) | По всем `*.sql`: CREATE только в `ubuntu/serenedb/corpus_merge.sql:162` и копии `work/z21wt/...` (устаревшая, без edited_delta перед unmatched). Канон — один. |
| 3c | На повторных прогонах — старый unmatched; на свежей БД — «нет таблицы» | **ПОДТВЕРЖДЕНО** | `tmp3_*` обычные, переживают рестарт (`:19–21`). Повтор: edited_delta по прошлому unmatched. Свежая база без таблицы → ошибка catalog на `:154` до создания unmatched. |
| 4 | Вариант D: образец `\gexec` по сущностям уже есть у `:252–256` (collapse_dead) | **ПОДТВЕРЖДЕНО** | `PREPARE p_collapse_dead` + `SELECT 'EXECUTE …' … \gexec` на `:252–261`. Паттерн цикла по `src_table` в файле есть. |
| 5a | Нет checkpoint/restart между `corpus_build` и `corpus_merge` в `build.sh:296–337` | **ПОДТВЕРЖДЕНО** | Подряд: `corpus_build.sql` → cfg → `corpus_merge.sql`. В `build.sh` нет `systemctl`/`CHECKPOINT`/`restart` (rg пусто). |
| 5b | `MemoryMax` в `ubuntu/serenedb/serenedb.service` нет; есть `Restart=always`, CWD spill | **ПОДТВЕРЖДЕНО** | Файл: `WorkingDirectory=/var/lib/serenedb` (`:13`), `Restart=always` / `RestartSec=2` (`:15–16`); строки MemoryMax нет. |
| 6a | Default `memory_limit` = 80% RAM; только buffer manager | **ПОДТВЕРЖДЕНО** | https://docs.serenedb.com/configuration/limits#limit-values («Memory use · 80% of RAM · memory_limit · Note: This limit only applies to the buffer manager»); pragmas#memory-limit — actual consumption can be higher. |
| 6b | Cookbook OOM: опустить лимит до 50–60% | **ПОДТВЕРЖДЕНО** | https://docs.serenedb.com/cookbook/performance/oom#configuration-options — «set the memory limit to just 50-60% …» |
| 6c | `duckdb_memory()` / `duckdb_temporary_files()` для наблюдения | **ПОДТВЕРЖДЕНО** | https://docs.serenedb.com/sql/functions/duckdb_table_functions#duckdb_memory / `#duckdb_temporary_files` |
| 6d | Несколько blocking в одном запросе → возможен OOM | **ПОДТВЕРЖДЕНО** | how_to_tune_workloads › Limitations. |
| 7a | Защита №1: `SET memory_limit` 50–60% + `threads`↓ перед unmatched | **ПОДТВЕРЖДЕНО** как штатная рекомендация доков; **частично** как гарантия | Доки сами так советуют. Но pragmas прямо: часть аллокаций (векторы, join state) вне BM — лимит не ловит всё. Для unmatched без `string_agg` полезен как ранний spill/controlled OOM, не абсолютный щит. |
| 7b | Защита №4: авто-restart между build и merge; риск данных низкий (`tmp3_*` на диске) | **ПОДТВЕРЖДЕНО** для персистентных таблиц; **ОПРОВЕРГНУТО** как «безопасный без доп. правок build.sh» | См. раздел «Авто-restart» ниже: TEMPORARY SECRET живут до рестарта инстанса и будут снесены. |
| H1 | Пик = несколько anti-join HT в одном CTAS | **ПОДТВЕРЖДЕНО** как гипотеза по коду+докам | 6 (не 7) anti в одном statement; доки про multiple blocking. Живой EXPLAIN — **НЕПРОВЕРЯЕМО** (ssh запрещён). |
| H3 | Высокая базовая RSS после длинного p_doc / jemalloc | **НЕПРОВЕРЯЕМО** на живом | Согласуется с доками jemalloc/OOM cookbook и фактами ТЗ A3, но RSS до merge здесь не снимался. |

---

## Опровержения

1. **«Семь» NOT EXISTS → на деле шесть.**  
   A3 (и вводный промт) считают 7; код и комментарий `:109` — **6** anti к `tmp3_corpus`. Вложенный `EXISTS (tmp3_key…Period)` не отдельный anti. На план защиты (D/F) почти не влияет, но якоря «семь hash-таблиц» завышены.

2. **Авто-restart между build и merge без пересоздания секретов — ломает хвост такта.**  
   - `build.sh:177–187`: `CREATE OR REPLACE TEMPORARY SECRET` (odg + qwen_*).  
   - Доки: temporary secrets «live in memory for the lifespan of the SereneDB instance» (secrets_manager#temporary-secrets); код проекта то же фиксирует (`box_tune.sh:182`).  
   - Рестарт движка **убивает** эти секреты.  
   - `corpus_merge.sql` **не** зовёт `ai_embed` — самому merge секреты не нужны.  
   - После merge: `1-period` — SQL, ок; `classify_entities.py` — HTTP к DeepSeek из env, **не** секреты движка, ок; шаги **3–4** `embed_missing.sh` берут имена из `EMBED_SECRETS` и ждут секреты **в движке** → после голого restart: `secret … not found` (известный класс, `build.sh:86`). `embed_bulk` (шаг 5) часто сам создаёт `emb_*`, но шаги 3–4 и поздний `embed_missing` entity_card — нет.  
   - A3 этот риск **не назвал** (только downtime ask + сброс кэшей).

3. **flock не страдает от рестарта движка** — уточнение к «что переживает».  
   `build.sh:77–78`: `exec 9>/var/lock/1c-serene-build-*.lock` + `flock -n 9` — файловый замок процесса shell; рестарт `serenedb` его не снимает. A3 про flock молчит; ломает не замок, а секреты.

4. **Рестарт не обязателен как лечение unmatched, если сделаны D/F.**  
   A3 сам ранжирует D/F выше restart (#2 vs #4) и пишет, что restart «не чинит сам unmatched при холодном старте, если запрос всё ещё > RAM».  
   Оценка B3: при старте с высокой RSS (H3) D/F режет **инкремент** пика запроса (HT ≈ сущность / один anti за statement); этого обычно достаточно, чтобы не упереться в OS OOM на том же CTAS. Restart — гигиена jemalloc/RSS, **дополнение**, не замена D/F. Утверждать «D/F всегда хватает при любой базовой RSS» без замера — нельзя (**НЕПРОВЕРЯЕМО**), но план «сначала D/F (+ memory_limit), restart только если A/B покажет» согласуется с A3 лучше, чем делать restart №1.

---

## Авто-restart: цепочка после merge

| Шаг после merge | Нужны TEMPORARY SECRET? | Эффект голого restart до merge |
|---|---|---|
| `corpus_merge` сам | Нет | OK |
| 1-period (`period_relative_forms_load.sql`) | Нет | OK |
| 2-бис `classify_entities.py` | Нет (urllib + `DEEPSEEK_API_KEY`) | OK |
| 3–4 `embed_missing` (метки, резолвер) | **Да** (`EMBED_SECRETS`) | **СЛОМАЕТСЯ** без recreate |
| 5 `embed_bulk` | Создаёт свои `emb_*` | Обычно OK |
| wiki/entity_card `embed_missing` | **Да** | **СЛОМАЕТСЯ** |
| flock `/var/lock/1c-serene-build-*.lock` | n/a (файл) | Переживает |

**Вывод:** если вносить auto-restart в `build.sh`, обязателен блок **пересоздания секретов** (тот же SQL, что `:164–187`) **после** wait-ready и **до** любого embed. Иначе пункт 4 раздела 5 A3 нельзя брать в план «как есть».

---

## Ранжирование защит A3 (§5) — оценка B3

| # A3 | Оценка |
|---|---|
| 1 memory_limit 50–60% + threads↓ | Оставить высоко: дёшево, по докам; не единственная опора. |
| 2 D (per-src_table) / F (последовательные anti) | **Главный фикс пика unmatched**; образец `\gexec` есть. |
| 3 Pre-materialize keys (C) | Ок как усиление; приёмка md5 множества ключей — обязательна. |
| 4 Авто-restart | Допустим **только** с recreate secrets + wait port; иначе дефект такта на embed. Для H3 полезен; для семантики unmatched — нет. |
| 5 Ослабить rewrite_wave | Согласен с A3: опаснее для п.13/векторов. |
| 6 MemoryMax systemd | Согласен: внешний SIGKILL ≈ текущий сценарий; на mid-write опасно. |
| 7 BYPASS векторов | Согласен: не про OOM. |

Плюс обязательный фикс порядка: unmatched → затем `edited_delta` (A3 это уже сказал — верно).

---

## Вывод

**Отчёт A3 пригоден как основа плана — да**, с правками:

1. Считать **6** anti-join, не 7.  
2. В план: сначала **D и/или F** + `SET memory_limit`/threads; порядок edited_delta.  
3. Авто-restart — опциональная гигиена RSS **после** recreate TEMPORARY SECRET; не считать «безопасным без правок build.sh».  
4. H1/H3/H4 как гипотезы — ок; живые EXPLAIN/`duckdb_memory`/A/B на свежем рестарте остаются вне этого аудита (**НЕПРОВЕРЯЕМО** здесь).

Серверы не трогались. Код не менялся. Результат только этот файл.
