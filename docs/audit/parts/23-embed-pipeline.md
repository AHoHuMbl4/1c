# 23. embed-pipeline

## Зачем участок нужен
`build.sh` — цикл такта: объекты, корпус (или пропуск), разметка, векторы меток/резолвера/корпуса, индекс, покрытие, алиасы, solr-словарь, карточки, постчек (`ubuntu/serenedb/build.sh:1-18`, `146-452`). `embed_missing.sh` досчитывает `emb` через `ai_embed` пачками в отдельные `_part_*` (`embed_missing.sh:1-16`, `337-346`). `wiki_alias.sh` заполняет словари синонимов сущностей/величин и подписи развилок через OpenClaw (`wiki_alias.sh:1-18`, `98-228`, `314-471`, `483-601`). `box_tune.sh` считает/применяет лимиты RAM/потоков и префлайт диска для слияния (`box_tune.sh:1-23`, `51-121`, `505-565`).

## Входы
- `build.sh`: `SERENEDB_DSN`, `ETL_ODATA_BASE`/`GATE`, `BUILD_EMBED_WORKERS`, `BUILD_THREAD_MIN`, `EMBED_MODEL` (обязателен), `EMBED_DIM`, `EMBED_MAXLEN`, `EMBED_API_KEYS`/`EMBED_API_KEY`/`ALIBABA_*`, `EMBED_HOSTS`/`EMBED_HOST`, `EMBED_PATH`, `ODG_GATEWAY_TOKEN`, `SEARCH_DICT_LOCALE`, `ASK_SOLR_SYNONYMS_DICT`/`SOLR_SYN_DICT`, `FORCE_REBUILD`, `EMBED_SERVICE`, `PACKET_BASE_ID`/`PACKET_BASES`/`PACKET_CONFIG_PY`, `WIKI_ALIAS_PER_TACT`, `ALIAS_TABLE`, `CSV_DIR`, `MERGE_CHUNK_ROWS` (`build.sh:30-54`, `95-131`, `247`, `259`, `305`, `393`, `421-434`).
- `embed_missing.sh`: argv `<таблица> <выражение-источник> [потоков] [ключ,…]`; `ROWS_WHERE`, `SERENEDB_DSN`, `EMBED_MODEL`, `EMBED_SECRETS`/`EMBED_SECRET`, `EMBED_DIM`, `EMBED_BATCH_ROWS`/`CHARS`, `EMBED_MAXLEN`, `EMBED_ROUNDS`, `EMBED_RETRY_PAUSE`, `EMBED_THREADS` (`embed_missing.sh:47-108`, `239-240`, `326`).
- `wiki_alias.sh`: `[CAP]` (0=все); `WIKI_ALIAS_*`, `ALIAS_TABLE`, `MEASURE_TABLE`, `OPENCLAW_*`, `CSV_DIR`, fork/solr env (`wiki_alias.sh:21-69`, `487-491`, `606`).
- `box_tune.sh`: аргументы `plan|disk|apply|restore|embed-form` или source; `BOX_TUNE_*`, `SERENEDB_DSN`, `BUILD_EMBED_WORKERS`, `EMBED_HOST(S)` (`box_tune.sh:28-29`, `641-665`).

## Порядок работы
1. `build.sh`: flock по `current_database()` (`73-76`); `embed_check.sh` (`144`); `corpus_init.sql` (`147-148`); TEMPORARY SECRET http+openai (`155-173`); `embed_secrets_base_url_check` (`176-179`); `corpus_precheck.sql` (`184-187`).
2. Пропуск корпуса при `FORCE_REBUILD≠1` и `SKIP_BUILD=1` (`233-248`); иначе `corpus_build.sql` → диск-префлайт/`MERGE_CHUNK_ROWS` → `corpus_merge.sql` → `corpus_built_ts` (`253-284`).
3. `classify_entities.py` fail-closed (`296-298`); опционально `packet_config.py` (`305-324`).
4. `embed_missing.sh search_tables label` с `ROWS_WHERE`≠service (`336-340`); `resolver_build.sql` + `embed_missing` resolver (`342-353`); корпус бизнес-проход (`377-380`); при `EMBED_SERVICE=1` — второй без фильтра (`394-399`).
5. `VACUUM (REFRESH_INDEX) search_idx` (`403-404`); `coverage_build.sql` (`411-412`); `wiki_alias.sh CAP`; `wiki_publish.sh` (`421-422`); `solr_synonyms_build.py compile --apply` fail-closed (`429-435`); `entity_card_build.sql` + `embed_all.sh` soft (`444-449`); `corpus_postcheck.sql` (`451-452`); cleanup секретов на EXIT (`132-137`).
6. Внутри `embed_missing`: `transfer` старых `_part_` → guard (`203-217`) → раунды: todo/chunk → N воркеров `ai_embed` → `transfer`/`drop_parts` → пауза/повтор (`242-399`).
7. Внутри `wiki_alias`: ensure_vllm → таблицы alias/measure → цикл близости → добор величин → collisions → day-basis fork → `branch_alias.sh` → solr compile soft (`72-611`).

## Выходы
- Таблицы с заполненным `emb`: `search_tables`, `resolver_index`, `search_corpus` (+карточки через `embed_all`) — потребители такта дальше и ask/поиск (`build.sh:336-449`).
- `search_entity_alias`, `search_measure_alias`, `search_alias_probe`, `search_fork_*`, словарь `SOLR_SYN_DICT` (`wiki_alias.sh:75-76`, `341`, `498-499`, `603-611`; `build.sh:429-435`).
- JSON stdout досчёта (`embed_missing.sh:223`, `402`); код 0/1/2 (`409-411`, guard `213-216`).
- `box_tune`: conf/env/swap/`SET memory_limit`, план `merge_chunk_rows` в stdout префлайта (`567-614`, `505-565`, `build.sh:273-276`).

## Обращения наружу
| Место | Что | Зачем |
|---|---|---|
| `embed_missing.sh:343-346` | SQL `ai_embed(txt, MODEL, secret)` | вектор строки |
| `embed_missing.sh:79,151-160,183-199,269-297,327,374` | `psql` / `duckdb_tables` / COUNT / CREATE todo / DROP | очередь, перенос, уборка |
| `build.sh:163-170` | CREATE SECRET http (`GATE`+token), openai (`base_url`+key) | `$metadata`/embed |
| `build.sh:155-256,279,343,404,412,445,452` | SQL-файлы корпуса/резолвера/индекса/покрытия/карточки/чеков | такт |
| `build.sh:144,297,318,448` | `embed_check`, `classify_entities`, `packet_config`, `embed_all` | модель/контур/карточки |
| `wiki_alias.sh:155-157,277-279,405-407,569-571` | `alias_infer_gateway.py` (OpenClaw/модель) | алиасы/разведение/fork |
| `wiki_alias.sh:110-128,185-221,238-309,350-450,543-593` | `psql` SELECT/INSERT/UPDATE/MERGE/`read_json` | словарь из ответа |
| `wiki_alias.sh:72,608-611` | `ensure_vllm_gateway.sh`, `solr_synonyms_build.py` | шлюз/словарь Solr |
| `box_tune.sh:225-227,323,371,385,399,349,548` | `psql`/`df`/`du`/`systemctl restart serenedb` | проверка секретов, SET, диск, рестарт |

HTTP к эмбеддеру — внутри `ai_embed` движка, не прямым curl в этих четырёх файлах. HTTP к OpenClaw — через `alias_infer_gateway.py`, не из shell напрямую.

## Переключатели
| Перем. | Умолч. | Где |
|---|---|---|
| `EMBED_MODEL` | пусто→exit 1 в build; `text-embedding-v4` в embed_missing | `build.sh:43-44`, `embed_missing.sh:53` |
| `BUILD_EMBED_WORKERS` / argv N | 8 | `build.sh:33`, `embed_missing.sh:49` |
| `EMBED_BATCH_ROWS`/`CHARS`/`MAXLEN` | 16 / 12000 / 20000 | `embed_missing.sh:102-108` |
| `EMBED_ROUNDS`/`RETRY_PAUSE` | 6 / 20 | `embed_missing.sh:239-240` |
| `EMBED_THREADS` | не задан→не трогает | `embed_missing.sh:326-334` |
| `EMBED_ALLOW_LARGE_TICK` / `EMBED_TICK_MAX_REMAINING` | 0 / 100000 (в guard) | `embed_missing.sh:210`, guard |
| `FORCE_REBUILD` / `EMBED_SERVICE` | 0 / 0 | `build.sh:247`, `394` |
| `WIKI_ALIAS_MAX_SEC`/`BATCH`/`PER_TACT`/`COLLISIONS`/`MODEL` | 120 / 20 / 100 / 1 / `vllm/Qwen3.8-27B` | `wiki_alias.sh:41,68,95,327`; `build.sh:421` |
| `WIKI_ALIAS_RETRY_H`/`WORD`/`COLLISION_ROUNDS` | 6 / '' / 40 | `wiki_alias.sh:49,54,344` |
| `WIKI_ALIAS_MEASURE=1` | 0→exec measure script | `wiki_alias.sh:22-24` |
| `ALIAS_TABLE`/`MEASURE_TABLE`/`SOLR_SYN_DICT` | `search_entity_alias` / `search_measure_alias` / `search_dict_syn` | `wiki_alias.sh:59-62,606`; `build.sh:49` |
| `BOX_TUNE_SMALL_RAM_KIB` | 16 GiB | `box_tune.sh:28` |
| `BOX_TUNE_SWAP_APPLY`/`SQL`/`RESTART`/`SKIP_RESTART` | применены / применены / рестарт / 0 | `box_tune.sh:267,318,301,610` |
| `MERGE_CHUNK_ROWS` / disk env | 1000000 / WAL 4096 B/row | `build.sh:259`; `box_tune.sh:338-341` |

## Развилки
- Пропуск корпуса vs полная сборка (`build.sh:247-285`).
- Нет `PACKET_BASE_ID` → шаг 2-тер не зовётся (`305`).
- `EMBED_SERVICE≠1` → служебный корпус без вектора (`394-399`).
- `left()=0` → JSON ноль и exit 0 (`221-224`); guard rc=2 → exit 2 (`213-214`); после раундов `after≥было` и `after>impossible` → exit 1 (`409-410`).
- Нет `openclaw` → `wiki_alias` exit 0 (`74`); осечка модели → пустые INSERT и continue (`157-180`); `WIKI_ALIAS_COLLISIONS≠1` → нет разведения (`327`); infra в day-fork → break (`572-582`); нет `branch_alias.sh` → skip (`598`).
- `box_tune_plan`: `ram≤16GiB` → phase=small (≤4 threads, swap) иначе large (`67-103`); `disk_ok≠1` → return 1 (`531-535`); CLI vs source (`641-665`).

## Чего здесь нет
- Разовой bulk-сборки миллионов строк (`embed_bulk.sh` только назван в комментарии/guard, в этих четырёх файлах не вызывается).
- Прямого HTTP/curl к эмбеддеру или LLM из shell (кроме делегирования в py/движок).
- Векторизации служебных строк корпуса по умолчанию.
- Записи ответов боту / ask-пути / выбора сущности в runtime.
- Разбора DSN руками для имени базы (спрашивается `current_database()`).
- Создания индекса BM25 с нуля здесь (публикация `VACUUM REFRESH_INDEX` после досчёта; init — в `corpus_init.sql`).
