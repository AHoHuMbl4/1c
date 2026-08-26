# S2. Путь данных: из 1С до готового поискового слоя

## Коротко

Данные 1С уходят в SereneDB двумя взаимоисключающими ветками витрины: пакетным агентом Windows→Ubuntu или HTTP-синком через OData-шлюз. Apply/sync заполняют таблицы сущностей и отметки изменений. Таймер конвейера по готовности гоняет `pipeline.sh`: синк витрины, затем `build.sh`. Сборка читает `$metadata` и витрину, кладёт текст в `tmp3_corpus`, сливает в `search_corpus`, строит резолвер, досчитывает векторы через `ai_embed`, обновляет текстовый индекс `search_idx`, словари алиасов/solr и карточки. Отдельный ETL в markdown/git KB в витрину и поисковый слой не пишет. Прежний питоновский `serene_search_build.py` в боевом такте не участвует — его заменил `build.sh`.

## Схема пути

1. **Публикация 1С (разово)** — `windows/odata-setup`: IIS + `standardOdata`, состав, опц. `packet-agent` + `agent.ini` (`26`, `Program.cs`/`Packet.cs`). Выход: URL OData и/или агент на Windows.
2. **Ветка A — пакет в витрину** — агент: цикл тактов `Tact.Run`, пауза `tact_seconds` (умолч. 1200 с; с сервера `params`) (`PacketAgent.cs:41,3177-3180`; `packet_config.py:61,399`). Читает OData → CSV-чанки zstd±age → HTTPS PUT на приёмник (`21`).
3. **Приёмник** — `packet_server.py`, юнит `1c-packet-server` (always), слушает `PACKET_LISTEN` умолч. `127.0.0.1:6021` (`21:47`; `1c-packet-server.service`). Выход: `PACKET_ROOT/inbox/<base>/<pkg>/` до `state=verified`.
4. **Apply** — `packet_apply.py`, таймер `OnBootSec=2min` + `OnUnitActiveSec=2min` (`1c-packet-apply.timer:6-7`). verified→таблицы сущностей, `search_changed_sources`, `PACKET_META_DIR/<base>/$metadata` (`21:23`).
5. **Ветка B — HTTP в витрину** — `odata_gateway@` → upstream 1С (`ODG_LISTEN` умолч. `:6011`) (`25`). `serene_sync.py` → `poc_load_entity` (полная/дельта по OData) пишет таблицы витрины (`22`; `serene_sync.py:408-411`).
6. **Конвейер такта** — `1c-serene-pipeline[.timer]`: `OnBootSec=3min`, `OnUnitInactiveSec=1min` (`pipeline.timer:8-10`) → `pipeline.sh`: при каталоге `ETL_ODATA_BASE` — keep `search_changed_sources` → `serene_sync.py` (код≠0 не стопит) → `exec build.sh` (`pipeline.sh:42-57`). Альтернатива: `1c-serene-index.service` только `build.sh` (`ubuntu/systemd/…:38`).
7. **Корпус внутри движка** — `build.sh`: `corpus_init.sql` → при необходимости `corpus_build.sql` (`:gate` = `ETL_ODATA_BASE`, URL или каталог meta) → `tmp3_corpus` + карты `search_*` → `corpus_merge.sql` → `search_corpus` + индекс (`build.sh:147-279`; `corpus_init.sql:209-210`; `23`).
8. **Разметка и контур** — `classify_entities.py` fail-closed; при `PACKET_BASE_ID` — `packet_config.py` в `PACKET_BASES` (`build.sh:296-320`).
9. **Векторы** — `embed_missing.sh` + `ai_embed`: `search_tables.label` → `resolver_index` → `search_corpus.doc` (не-service; service только при `EMBED_SERVICE=1`) (`build.sh:336-399`; `23`).
10. **Индекс и словари** — `VACUUM (REFRESH_INDEX) search_idx` → `coverage_build.sql` → `wiki_alias.sh` / `wiki_publish.sh` → `solr_synonyms_build.py compile --apply` → `entity_card_build.sql` + `embed_all` → `corpus_postcheck.sql` (`build.sh:403-452`). Готовый слой: витрина + `search_corpus`/`search_idx`/`emb` + `resolver_index` + alias/solr/карточки.

**Вне тракта SereneDB:** `oc_etl.py` — GET OData → markdown → git KB; таймер `OnCalendar=03:00` (`26`; `1c-etl.timer:5`).

## Точки принятия решений

| Условие | Куда сворачивает | Где |
|---|---|---|
| `ETL_ODATA_BASE` — каталог vs URL | packet-skip HTTP в load; keep-marks в pipeline; `:gate` файл meta | `poc_load_entity.py:82-85,321-329`; `pipeline.sh:43-54`; `build.sh:32,256` |
| Агент: firstRun/Resync / индекс+версии / пустой контур | full / delta / meta-пакет `$metadata` | `21` развилки; `PacketAgent` Tact |
| Manifest age vs plain | decrypt vs JSON | `21`; Cfg `recipient_pubkey` пуст → plain |
| Apply op `full`/`full_entity` vs `delta` | CREATE vs TEMP+DELETE+INSERT | `21:71` |
| `FORCE_REBUILD≠1` и `SKIP_BUILD=1` | корпус не пересобирается | `build.sh:233-248` |
| `PACKET_BASE_ID` пуст | шаг `packet_config` не зовётся | `build.sh:305` |
| `EMBED_SERVICE≠1` | служебный корпус без `emb` | `build.sh:394-399` |
| `flock` занят | второй `build.sh` exit 0 | `build.sh:76` |
| Нет `packet-setup` / `--skip-packet` | агент не ставится (только OData/HTTP) | `26` |
| Список ETL INCLUDE / file / discover | разный набор markdown | `oc_etl.py:114-122` |

## Что участвует снаружи

- **Базы/движок:** SereneDB по `SERENEDB_DSN` (умолч. `127.0.0.1:7890`); таблицы витрины = имена EntitySet; поисковые `search_corpus`, `search_idx`, `search_dict`(+stem/syn), `search_tables`, `resolver_index`, `search_changed_sources`, `search_*_map`/`meta`/`quality`, alias/fork/card.
- **Сервисы/порты:** OData IIS на Windows; `odata_gateway` `:6011`; `packet_server` `:6021`; таймеры pipeline / packet-apply / etl-03:00; schtasks агента.
- **Файлы env:** `/etc/1c-serene-sync.env`, `1c-mcp-reports.env`, `1c-embed.env`, `1c-packet.env`, `1c-packet-bases.json`, `1c-odata-gateway-%i.env`, `1c-etl.env`; Windows `agent.ini`.
- **Диск:** `PACKET_ROOT` `/var/lib/1c-packet`; `PACKET_META_DIR` `/var/lib/serenedb/packet-meta`; `CSV_DIR` `/var/lib/serenedb`.
- **Модели:** эмбеддер через `ai_embed`/секреты `EMBED_*` (`build.sh`); classify + `wiki_alias` → OpenClaw/`alias_infer_gateway` (умолч. модель вики `vllm/Qwen3.8-27B` в `wiki_alias.sh`); в packet/ETL LLM нет. В снятом `serene_search_build.py` — ещё HTTP Alibaba embed + DeepSeek money_column (`22`).

## Расхождения между отчётами уровня 1

- **расхождение: кто пишет боевой `search_corpus`/`search_idx` в текущем такте** — отчёт 22 ставит рядом `serene_search_build.py` как сборщик с MERGE/эмбед; отчёты 23/25 — `build.sh` → `corpus_merge` + `embed_missing`. **Верно текущий такт = `build.sh`**, источник `ubuntu/serenedb/build.sh:4` («вместо serene_search_build.py») и `ubuntu/systemd/1c-serene-index.service:38` (`ExecStart=…/build.sh`). Файл `serene_search_build.py` в дереве есть; репозиторный `ubuntu/serenedb/systemd/1c-serene-index.service:22` всё ещё зовёт его — это второй шаблон юнита, не путь `ubuntu/systemd` из отчёта 25.
- **расхождение: default `EMBED_DIM`** — 22: `1536` в `serene_search_build.py:36`; 25/23: `1024` в `build.sh:45`. **Оба верны для своих файлов**; боевой такт читает default из `build.sh`.
- **расхождение/пропуск: systemd apply** — 21 относит unit-файлы packet к «не тракту»; по коду apply в витрину будит именно `1c-packet-apply.timer` (`OnUnitActiveSec=2min`). Для сквозного пути расписание берём из unit-файлов, не из «Чего здесь нет» отчёта 21.

## Белые пятна

- Живые значения `/etc/1c-*.env` и какой контур (packet vs HTTP) включён на конкретной базе — с диска в уровне 1 не снимались (`25`).
- Фактический `tact_seconds`/`page_size` у агента после GET config — только defaults в коде; содержимое `PACKET_BASES` на хосте не читалось.
- Запускается ли где-либо ещё `ubuntu/serenedb/systemd/1c-serene-index.service` (со старым `serene_search_build.py`) на живой машине — по репозиторию двух шаблонов недостаточно.
- Связь ETL-KB с любым потребителем внутри `/srv/1c` поискового слоя — в участках 21–26 вызовов нет; дальнейшие потребители KB вне сырья не проверялись.
