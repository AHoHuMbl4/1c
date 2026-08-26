# 22. corpus-index

## Зачем участок нужен
Три файла закрывают цепочку «сущность 1С → таблица витрины → поисковый текст / структуры».
`poc_load_entity.py` пишет строки OData в таблицы SereneDB. `corpus_build.sql` внутри движка
собирает текст строк, карты ссылок/величин и служебные карты в `tmp3_*` и связанные
`search_*` (без эмбеддингов и без записи в боевой `search_corpus`). `serene_search_build.py`
собирает корпус с векторами, делает `MERGE` в `search_corpus` и создаёт текстовый индекс
`search_idx`.

## Входы
- **poc_load_entity.py**: `sys.argv[1]` — имя EntitySet (`943:947`); env `ETL_ODATA_BASE`
  (default `http://127.0.0.1:6011`, `32`), `SERENEDB_DSN` (`33`), `CSV_DIR` (`34`),
  `ETL_PAGE`/`ETL_PAGE_MIN` (`49:50`), `ETL_HTTP_TIMEOUT` (`60`), `ODG_GATEWAY_TOKEN` (`26:28`),
  `ETL_CSV_MAX_LINE` (`795`, `858`); аргумент `ro_role` у `load_entity`/`load_entity_delta`
  (default `serene_ro`, `630`, `817`).
- **corpus_build.sql**: psql-переменная `:gate` — база URL/путь к `$metadata`
  (`35: read_text(:'gate' || '/$metadata')`); читает таблицы витрины через `query_table`,
  каталоги `duckdb_tables`/`duckdb_columns`, таблицы `search_*` прошлого такта.
- **serene_search_build.py**: env из `/etc/1c-serene-sync.env` и `/etc/1c-mcp-reports.env`
  (`81:82`); `SERENEDB_DSN` (`35`), `EMBED_*`/`BUILD_*`/`ALIBABA_*`/`DEEPSEEK_*`/`ETL_ODATA_BASE`/
  `ODG_GATEWAY_TOKEN` (см. «Переключатели»); вход — живые таблицы витрины без вектор-колонок
  (`395:416`).

## Порядок работы
1. **poc**: `main` → `load_entity` (`943:947`). Полная: `fetch_all` (страницы OData,
   `$inlinecount`, при необходимости `$orderby`/`$select`, `_flatten_nested`) → CSV →
   сравнение `EXCEPT ALL` с витриной (`906:919`) → при отличии `DROP`/`CREATE TABLE AS`
   + `GRANT` (`921:940`). Дельта (`load_entity_delta`, `630`): проба `Ref_Key,DataVersion` →
   прямые GET по ключу → upsert/delete. Packet-режим (`_is_local_base`): без HTTP-данных,
   только счёт строк витрины (`321:329`, `822:823`).
2. **corpus_build.sql** (один прогон psql): (1) `$metadata` → `tmp3_ent/prop/key` + гейты
   пустоты/усыхания (`32:87`); (1-бис…кватер) карты остатков/баланса/календаря в
   `search_meta`/`search_balance_map`/`search_calendar_map` (`90:388`); (2) классификация
   колонок `tmp3_cls`, перечень `search_sources`/`tmp3_src` (`405:515`); (2-quater) флаг
   инкремента `tmp3_inc`/`tmp3_changed` (`538:552`); (2-бис) `MERGE` меток в `search_tables`
   (`569:585`); (2-тер) `written_by*` по `Recorder_Type` (`629:697`); (3) имена + `search_refmap`
   (`725:839`); (3-бис) список `tmp3_build` (`870:881`); (4–5) дата/`nums` без выбора «денег»
   (`888:911`); (5-бис/6) `p_doc` / chunk / `p_doc_plain` → `tmp3_corpus` (`999:1575`);
   (6-тер) `search_refcols` (`1593:1613`); (7–9) сверка/качество/`tmp3_run` (`1631:1724`).
3. **serene_search_build.py** `main` (`749`): создать/пересоздать `search_corpus` (`760:769`) →
   `search_seen` (`776:777`) → по таблицам `iter_corpus` (`387:712`): refmap, тексты, сумма
   через `money_column`, дата → эмбеддинг пачками → `MERGE` (`715:737`) → удаление gone
   (`853:859`) → словарь `search_dict` (`863:868`) → индекс `search_idx` или `VACUUM
   (REFRESH_INDEX)` (`883:915`) → пересоздание `search_tables` с эмбеддингами меток
   (`921:967`) → `GRANT` (`971:976`) → JSON-итог (`979:986`).

## Выходы
- **poc**: таблица витрины `"safe_col(entity).lower()"` + dict-статистика в stdout
  (`946:947`); docstring: переиспользуется `serene_sync.py` (`820`).
- **corpus_build.sql**: `tmp3_corpus` (+ `tmp3_run`); обновления `search_tables`,
  `search_refmap`, `search_sources`, `search_balance_map`, `search_calendar_map`,
  `search_meta`, `search_quality`, `search_refcols`. В боевой `search_corpus` этот файл
  не пишет; комментарий указывает перенос в `corpus_merge.sql` (`19:21`, `1720:1721`).
- **serene_search_build.py**: строки в `search_corpus` (с `emb`), индекс `search_idx`,
  `search_dict`, `search_meta.index_ddl`, `search_tables` с `emb`; JSON на stdout
  (`984:986`); при `failed>0` код выхода 3 (`980:983`).

## Обращения наружу
| Место | Что | Назначение |
|---|---|---|
| poc `123:125`, `198:212`, `240:242`, `459:461`, `705:`, `753:` | HTTP OData (`/$metadata`, entity, `/$count`, root `/?`) | метаданные и данные 1С |
| poc `488:499`, `801:`, `908:928` | `psql` stdin/`-tAc` | витрина SereneDB |
| corpus `35` | `read_text(:'gate'/$metadata)` | HTTP/файл метаданных через движок |
| corpus `644`, `999+`, `gexec` | `query_table(имя)` | чтение витрины |
| serene `113:120` | HTTP `ETL_ODATA_BASE/$metadata` | типы/ключи сущностей |
| serene `213:227` | HTTP `ALIBABA_EMBED_URL/embeddings` | векторы строк и меток |
| serene `257:278` | HTTP DeepSeek `/v1/chat/completions` | выбор денежной колонки |
| serene `198:210` | `psql` | SELECT/DDL/MERGE |

Языковая модель в `corpus_build.sql`: **нет**. В `poc_load_entity.py`: **нет**.

## Переключатели
| Имя | Где | Default |
|---|---|---|
| `ETL_ODATA_BASE` | poc `32`, serene `113` | `http://127.0.0.1:6011` |
| `SERENEDB_DSN` | poc `33`, serene `35` | host/port 7890, user postgres |
| `CSV_DIR` | poc `34` | `/var/lib/serenedb` |
| `ETL_PAGE` / `ETL_PAGE_MIN` | poc `49:50` | `10000` / `250` |
| `ETL_HTTP_TIMEOUT` | poc `60` | `600` |
| `ETL_CSV_MAX_LINE` | poc `795`,`858` | `200*1024*1024` |
| `ODG_GATEWAY_TOKEN` | poc `26`, serene `115` | `""` |
| `EMBED_DIM` / `EMBED_MODEL` | serene `36:37` | `1536` / `text-embedding-v4` |
| `BUILD_INSERT_ROWS` / `BUILD_EMBED_PARALLEL` | serene `42`,`48` | `200` / `16` |
| `BUILD_DICT_LOCALE` / `BUILD_SAMPLE` / `BUILD_TEXT_CLIP` | serene `165`,`167`,`182` | `ru_RU.UTF-8` / `20` / `20000` |
| `ALIBABA_EMBED_URL` / `ALIBABA_API_KEY` | serene `214:217` | URL+`""` (пустое → сбой embed) |
| `DEEPSEEK_API_KEY` / `DEEPSEEK_MODEL` / `DEEPSEEK_BASE` | serene `253:266` | нет ключа→`None`; model `deepseek-v4-flash`; base `https://api.deepseek.com` |
| `:gate` | corpus `35` | задаётся снаружи файла (в файле default нет) |
| `memory_limit` (движок) | corpus `928:941` | читается `current_setting` для размера чанка |

## Развилки
- poc: HTTP vs packet-каталог (`82:85`); дельта vs полная (`658:659`, `677:678`);
  retry→`$select` без Stream/Binary (`198:212`); уменьшение `$top` (`406:416`);
  nested flatten object vs register (`283:307`); `same`→без `DROP` (`911:919`);
  `only_binary` (`514:547`) — функция есть, из `main`/`load_entity` не вызывается.
- corpus: инкремент `tmp3_inc.on_` (`538:541`) vs полный проход; `tmp3_build` расширяется
  rename>200 / lag / refs (`870:881`); мелкие сущности `p_doc`, крупные chunk+finalize,
  провал→`p_doc_plain` (`1523:1574`); `ON_ERROR_STOP off` на циклах сущностей
  (`650:653`, `1519:1575`).
- serene: `$metadata` есть/нет (`419:461`); `money_column` → колонка / `""` / `None`
  (`245:288`, `573:579`); схема корпуса ≠ want → DROP (`763:766`); индекс отсутствует
  или DDL изменился → recreate, иначе `REFRESH_INDEX` (`902:915`); `failed`→status
  неполный, exit 3 (`843:847`, `980:983`).

## Чего здесь нет
- В `corpus_build.sql`: эмбеддинги, `MERGE`/`INSERT` в `search_corpus`, создание
  `search_idx` / IVF, выбор одной «денежной» колонки (есть карта `nums`).
- В `serene_search_build.py`: карты `nums`/`flags`/`refs_map`, чанкование крупных
  сущностей, `search_balance_map`/`search_calendar_map`/`search_refcols`, запасной
  `p_doc_plain`.
- В `poc_load_entity.py`: сборка корпуса, индекс, эмбеддинги, вызов
  `corpus_build`/`serene_search_build`.
- Вызов `corpus_merge.sql` / `build.sh` из этих трёх файлов: **нет** (только упоминание
  в комментариях corpus `19:21`).
- Векторный IVF-индекс в `serene_search_build.py`: **нет** (явно не создаётся, `870:875`).
